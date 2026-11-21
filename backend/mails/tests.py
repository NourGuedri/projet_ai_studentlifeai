import base64
import email as email_lib
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import override_settings
from rest_framework.test import APITestCase

from common import ai

from . import gmail
from .models import EmailMessage, GmailAccount

BODY = "Bonjour, merci de rendre votre rapport de stage avant le 30 octobre 2026. Cordialement, Mme Ben Ali."


class EmailMessageTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(email="etudiant@example.com", password="password123")
        self.other = user_model.objects.create_user(email="autre@example.com", password="password123")
        self.email = EmailMessage.objects.create(
            owner=self.user, sender="scolarite@univ.tn", subject="Rapport de stage", body=BODY,
        )
        self.foreign = EmailMessage.objects.create(owner=self.other, sender="x@y.tn", subject="Privé", body="Secret")
        self.client.force_authenticate(self.user)

    def url(self, email, action=""):
        return f"/api/mails/{email.id}/{action + '/' if action else ''}"

    # ------------------------------------------------------------ access
    def test_authentication_is_required(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/mails/").status_code, 401)

    def test_list_only_contains_own_emails(self):
        response = self.client.get("/api/mails/")
        self.assertEqual([e["id"] for e in response.data], [self.email.id])

    def test_other_users_emails_are_not_accessible(self):
        self.assertEqual(self.client.get(self.url(self.foreign)).status_code, 404)
        self.assertEqual(self.client.patch(self.url(self.foreign), {"draft_reply": "x"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(self.url(self.foreign)).status_code, 404)
        with patch("common.ai.generate_json") as generate:
            for action in ("classify", "summarize", "extract-tasks", "draft-reply"):
                self.assertEqual(self.client.post(self.url(self.foreign, action)).status_code, 404)
            generate.assert_not_called()
        self.assertTrue(EmailMessage.objects.filter(pk=self.foreign.pk).exists())

    # ------------------------------------------------------------ CRUD
    def test_manual_import_and_important_filter(self):
        response = self.client.post("/api/mails/", {
            "sender": "promo@shop.tn", "subject": "Soldes", "body": "-50 % sur tout !",
            "received_at": "2026-10-18T09:30:00+01:00",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.data["is_important"])
        EmailMessage.objects.filter(pk=self.email.pk).update(is_important=True)

        response = self.client.get("/api/mails/?important=true")
        self.assertEqual([e["id"] for e in response.data], [self.email.id])

    def test_body_is_required(self):
        response = self.client.post("/api/mails/", {"subject": "Vide", "body": "   "}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_ai_fields_are_read_only_but_draft_is_editable(self):
        response = self.client.patch(self.url(self.email), {"is_important": True, "draft_reply": "Merci !"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.email.refresh_from_db()
        self.assertIsNone(self.email.is_important)
        self.assertEqual(self.email.draft_reply, "Merci !")

    # ------------------------------------------------------------ AI
    def test_classify(self):
        result = {"is_important": True, "reason": "Échéance universitaire à respecter."}
        with patch("common.ai.generate_json", return_value=result) as generate:
            response = self.client.post(self.url(self.email, "classify"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_important"])
        self.assertEqual(response.data["importance_reason"], "Échéance universitaire à respecter.")
        self.assertIn(BODY, generate.call_args.args[0])

    def test_summarize(self):
        with patch("common.ai.generate_json", return_value={"summary": "Rapport à rendre avant le 30/10."}):
            response = self.client.post(self.url(self.email, "summarize"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"], "Rapport à rendre avant le 30/10.")

    def test_extract_tasks(self):
        result = {"tasks": [{"title": "Rendre le rapport de stage", "assignee": None, "due_date": "2026-10-30"}]}
        with patch("common.ai.generate_json", return_value=result):
            response = self.client.post(self.url(self.email, "extract-tasks"))
        self.assertEqual(response.status_code, 200)
        self.email.refresh_from_db()
        self.assertEqual(self.email.tasks, [{"title": "Rendre le rapport de stage", "assignee": "", "due_date": "2026-10-30"}])

    def test_draft_reply_is_only_saved(self):
        self.user.first_name, self.user.last_name = "Ayoub", "Dhieb"
        self.user.save()
        with patch("common.ai.generate_json", return_value={"reply": "Bonjour Madame, c'est noté."}) as generate, \
                patch("django.core.mail.send_mail") as send_mail:
            response = self.client.post(self.url(self.email, "draft-reply"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["draft_reply"], "Bonjour Madame, c'est noté.")
        self.assertIn("signature : Ayoub Dhieb", generate.call_args.args[0])
        send_mail.assert_not_called()

    def test_ai_errors_follow_learning_status_codes(self):
        with patch("common.ai.generate_json", side_effect=ai.AINotConfigured("Aucune clé GEMINI_API_KEY.")):
            response = self.client.post(self.url(self.email, "classify"))
        self.assertEqual(response.status_code, 503)
        self.assertIn("GEMINI_API_KEY", response.data["detail"])

        with patch("common.ai.generate_json", side_effect=ai.AIError("HTTP 503")):
            response = self.client.post(self.url(self.email, "summarize"))
        self.assertEqual(response.status_code, 502)

        with patch("common.ai.generate_json", return_value=["pas", "un", "objet"]):
            response = self.client.post(self.url(self.email, "draft-reply"))
        self.assertEqual(response.status_code, 502)
        self.email.refresh_from_db()
        self.assertEqual(self.email.draft_reply, "")


# ====================================================================== Gmail (Google entirely simulated)
GOOGLE = {"GOOGLE_CLIENT_ID": "client-id.apps.googleusercontent.com", "GOOGLE_CLIENT_SECRET": "client-secret",
          "GOOGLE_REDIRECT_URI": "http://localhost:8000/api/mails/gmail/callback/", "GMAIL_TOKEN_KEY": "",
          "GMAIL_SYNC_LIMIT": 20, "FRONTEND_URL": "http://localhost:3000"}
REFRESH_TOKEN = "1//refresh-token-secret-value"
ACCESS_TOKEN = "ya29.access-token-value"


def b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


class FakeResponse:
    def __init__(self, status, data=None):
        self.status_code, self._data = status, data

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data


class FakeGoogle:
    """Replaces requests.request in mails.gmail and records every call."""

    def __init__(self, messages=None):
        self.calls = []
        self.messages = messages or {}  # gmail id -> message resource
        self.drafts = []
        self.token_status = 200
        self.revoke_status = 200

    def __call__(self, method, url, timeout=None, **kwargs):
        self.calls.append((method, url, kwargs))
        path = url.replace(gmail.API_URL, "")
        if url == gmail.TOKEN_URL:
            if self.token_status != 200:
                return FakeResponse(self.token_status, {"error": "invalid_grant"})
            data = {"access_token": ACCESS_TOKEN, "expires_in": 3599}
            if kwargs["data"]["grant_type"] == "authorization_code":
                data["refresh_token"] = REFRESH_TOKEN
            return FakeResponse(200, data)
        if url == gmail.REVOKE_URL:
            return FakeResponse(self.revoke_status, {} if self.revoke_status == 200 else {"error": "server_error"})
        assert kwargs["headers"]["Authorization"] == f"Bearer {ACCESS_TOKEN}"
        if path == "/profile":
            return FakeResponse(200, {"emailAddress": "ayoub@gmail.com"})
        if path == "/messages":
            ids = list(self.messages)[: kwargs["params"]["maxResults"]]
            return FakeResponse(200, {"messages": [{"id": i, "threadId": self.messages[i]["threadId"]} for i in ids]})
        if path.startswith("/messages/"):
            return FakeResponse(200, self.messages[path.split("/")[2]])
        if path == "/drafts" and method == "POST":
            self.drafts.append(kwargs["json"])
            return FakeResponse(200, {"id": "draft-1", "message": {"id": "m-draft"}})
        return FakeResponse(404, {"error": {"code": 404, "status": "NOT_FOUND"}})

    def count(self, url_part):
        return sum(1 for _, url, _ in self.calls if url_part in url)


def gmail_message(gmail_id, subject, plain=None, html=None):
    parts = []
    if plain is not None:
        parts.append({"mimeType": "text/plain", "filename": "", "body": {"data": b64(plain)}})
    if html is not None:
        parts.append({"mimeType": "text/html", "filename": "", "body": {"data": b64(html)}})
    return {
        "id": gmail_id, "threadId": f"thread-{gmail_id}", "internalDate": "1792000000000", "snippet": "aperçu",
        "payload": {"mimeType": "multipart/alternative", "parts": parts, "headers": [
            {"name": "From", "value": "Mme Ben Ali <benali@univ.tn>"},
            {"name": "Subject", "value": subject},
            {"name": "Date", "value": "Mon, 19 Oct 2026 09:30:00 +0100"},
            {"name": "Message-ID", "value": f"<{gmail_id}@mail.univ.tn>"},
        ]},
    }


@override_settings(**GOOGLE)
class GmailTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(email="etudiant@example.com", password="password123")
        self.other = user_model.objects.create_user(email="autre@example.com", password="password123")
        self.client.force_authenticate(self.user)
        self.google = FakeGoogle({
            "g1": gmail_message("g1", "Rapport de stage", plain="Rendez le rapport avant le 30 octobre."),
            "g2": gmail_message("g2", "Newsletter", html="<html><head><style>p{}</style></head><body>"
                                "<p>Bonjour&nbsp;!</p><p>Nouveaut&eacute;s <b>du mois</b></p><script>x()</script></body></html>"),
        })
        patcher = patch("mails.gmail.requests.request", side_effect=self.google)
        patcher.start()
        self.addCleanup(patcher.stop)

    def connect(self, user=None):
        return GmailAccount.objects.create(user=user or self.user, email="ayoub@gmail.com",
                                           refresh_token_encrypted=gmail.encrypt_token(REFRESH_TOKEN))

    def callback(self, **params):
        self.client.force_authenticate(None)  # Google redirects the browser: no JWT
        return self.client.get("/api/mails/gmail/callback/", params)

    # ------------------------------------------------------------ state
    def test_connect_returns_google_url_with_signed_state(self):
        response = self.client.post("/api/mails/gmail/connect/")
        self.assertEqual(response.status_code, 200)
        url = urlparse(response.data["url"])
        params = {k: v[0] for k, v in parse_qs(url.query).items()}
        self.assertEqual(url.netloc, "accounts.google.com")
        self.assertEqual(params["scope"], " ".join(gmail.SCOPES))
        self.assertEqual((params["access_type"], params["prompt"]), ("offline", "consent"))
        self.assertEqual(params["redirect_uri"], GOOGLE["GOOGLE_REDIRECT_URI"])
        self.assertNotIn("client-secret", response.data["url"])
        self.assertEqual(gmail.read_state(params["state"]), self.user.pk)

    def test_expired_or_forged_state_is_rejected(self):
        state = gmail.make_state(self.user)
        with patch("django.core.signing.time.time", return_value=signing.time.time() + gmail.STATE_MAX_AGE + 1):
            self.assertIsNone(gmail.read_state(state))
            response = self.callback(state=state, code="auth-code")
            self.assertEqual(response["Location"], "http://localhost:3000/emails?gmail=error")
        forged = signing.dumps({"uid": self.other.pk, "nonce": "x"}, salt="another-salt")
        for bad in (forged, state[:-2] + "xx", "", None):
            self.assertIsNone(gmail.read_state(bad))

        for bad in (forged, state[:-2] + "xx"):
            response = self.callback(state=bad, code="auth-code")
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response["Location"], "http://localhost:3000/emails?gmail=error")
        self.assertFalse(GmailAccount.objects.exists())
        self.assertEqual(self.google.count(gmail.TOKEN_URL), 0)

    # ------------------------------------------------------------ callback
    def test_callback_creates_account_with_encrypted_token(self):
        response = self.callback(state=gmail.make_state(self.user), code="auth-code")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "http://localhost:3000/emails?gmail=connected")
        account = GmailAccount.objects.get(user=self.user)
        self.assertEqual(account.email, "ayoub@gmail.com")
        self.assertNotIn(REFRESH_TOKEN, account.refresh_token_encrypted)
        self.assertEqual(gmail.decrypt_token(account.refresh_token_encrypted), REFRESH_TOKEN)
        token_call = next(kw for _, url, kw in self.google.calls if url == gmail.TOKEN_URL)
        self.assertEqual(token_call["data"]["code"], "auth-code")

        self.client.force_authenticate(self.user)
        status = self.client.get("/api/mails/gmail/status/")
        self.assertEqual(status.data["email"], "ayoub@gmail.com")
        self.assertTrue(status.data["connected"] and status.data["configured"])
        self.assertNotIn(REFRESH_TOKEN, status.content.decode())
        self.assertNotIn(account.refresh_token_encrypted, status.content.decode())

    def test_callback_errors_redirect_with_error(self):
        self.assertEqual(self.callback(state=gmail.make_state(self.user), error="access_denied")["Location"],
                         "http://localhost:3000/emails?gmail=error")
        self.google.token_status = 400
        self.assertEqual(self.callback(state=gmail.make_state(self.user), code="bad")["Location"],
                         "http://localhost:3000/emails?gmail=error")
        self.assertFalse(GmailAccount.objects.exists())

    def test_secrets_are_never_logged(self):
        self.connect()
        self.google.token_status = 400
        with self.assertLogs("mails.gmail", level="WARNING") as logs:
            self.callback(state=gmail.make_state(self.user), code="auth-code")
            self.client.force_authenticate(self.user)
            self.client.post("/api/mails/gmail/sync/")
        output = "".join(logs.output)
        for secret in ("auth-code", "client-secret", REFRESH_TOKEN, ACCESS_TOKEN):
            self.assertNotIn(secret, output)

    # ------------------------------------------------------------ sync
    def test_sync_imports_without_duplicates(self):
        self.connect()
        response = self.client.post("/api/mails/gmail/sync/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["imported"], 2)
        self.assertIsNotNone(response.data["last_synced_at"])

        first = EmailMessage.objects.get(gmail_id="g1")
        self.assertEqual((first.owner, first.source, first.gmail_thread_id), (self.user, "gmail", "thread-g1"))
        self.assertEqual(first.sender, "Mme Ben Ali <benali@univ.tn>")
        self.assertEqual(first.subject, "Rapport de stage")
        self.assertEqual(first.body, "Rendez le rapport avant le 30 octobre.")
        self.assertIsNotNone(first.received_at)
        self.assertEqual(EmailMessage.objects.get(gmail_id="g2").body, "Bonjour !\n\nNouveautés du mois")

        self.google.messages["g3"] = gmail_message("g3", "Nouveau", plain="x" * 30000)
        response = self.client.post("/api/mails/gmail/sync/")
        self.assertEqual(response.data["imported"], 1)
        self.assertEqual(EmailMessage.objects.filter(owner=self.user).count(), 3)
        self.assertEqual(len(EmailMessage.objects.get(gmail_id="g3").body), 20000)
        self.assertEqual(self.client.get("/api/mails/").data[0]["source"], "gmail")
        # Messages already imported are not downloaded again.
        self.assertEqual(self.google.count("/messages/g1"), 1)

    @override_settings(GMAIL_SYNC_LIMIT=1)
    def test_sync_limit(self):
        self.connect()
        self.assertEqual(self.client.post("/api/mails/gmail/sync/").data["imported"], 1)

    def test_sync_requires_account_and_reports_google_errors(self):
        self.assertEqual(self.client.post("/api/mails/gmail/sync/").status_code, 400)
        self.connect()
        self.google.token_status = 400
        response = self.client.post("/api/mails/gmail/sync/")
        self.assertEqual(response.status_code, 502)
        self.assertIn("reconnectez", response.data["detail"])

    # ------------------------------------------------------------ drafts
    def test_gmail_draft_replies_in_thread(self):
        self.connect()
        self.client.post("/api/mails/gmail/sync/")
        mail = EmailMessage.objects.get(gmail_id="g1")
        mail.draft_reply = "Bonjour Madame, c'est noté. Cordialement."
        mail.save()
        with patch("django.core.mail.send_mail") as send_mail:
            response = self.client.post(f"/api/mails/{mail.id}/gmail-draft/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["draft_id"], "draft-1")
        send_mail.assert_not_called()

        draft = self.google.drafts[0]["message"]
        self.assertEqual(draft["threadId"], "thread-g1")
        mime = email_lib.message_from_bytes(base64.urlsafe_b64decode(draft["raw"]))
        self.assertEqual(mime["To"], "Mme Ben Ali <benali@univ.tn>")
        self.assertEqual(mime["Subject"], "Re: Rapport de stage")
        self.assertEqual(mime["In-Reply-To"], "<g1@mail.univ.tn>")
        self.assertEqual(mime["References"], "<g1@mail.univ.tn>")
        self.assertIn("c'est noté", mime.get_payload(decode=True).decode())
        self.assertFalse(any("/send" in url for _, url, _ in self.google.calls))

    def test_gmail_draft_for_manual_email(self):
        self.connect()
        mail = EmailMessage.objects.create(owner=self.user, sender="scolarite@univ.tn", subject="Re: Inscription",
                                           body="...", draft_reply="Merci.")
        self.assertEqual(self.client.post(f"/api/mails/{mail.id}/gmail-draft/").status_code, 200)
        draft = self.google.drafts[0]["message"]
        self.assertNotIn("threadId", draft)
        mime = email_lib.message_from_bytes(base64.urlsafe_b64decode(draft["raw"]))
        self.assertEqual(mime["To"], "scolarite@univ.tn")
        self.assertEqual(mime["Subject"], "Re: Inscription")
        self.assertIsNone(mime["In-Reply-To"])

    def test_gmail_draft_is_refused_without_draft_or_account(self):
        mail = EmailMessage.objects.create(owner=self.user, sender="a@b.tn", body="...")
        self.connect()
        self.assertEqual(self.client.post(f"/api/mails/{mail.id}/gmail-draft/").status_code, 400)
        mail.draft_reply = "Merci."
        mail.save()
        GmailAccount.objects.all().delete()
        response = self.client.post(f"/api/mails/{mail.id}/gmail-draft/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Gmail", response.data["detail"])
        self.assertEqual(self.google.drafts, [])

    # ------------------------------------------------------------ disconnect
    def test_disconnect_revokes_and_keeps_imported_emails(self):
        self.connect()
        self.client.post("/api/mails/gmail/sync/")
        response = self.client.post("/api/mails/gmail/disconnect/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["revoked"])
        self.assertFalse(response.data["connected"])
        revoke = next(kw for _, url, kw in self.google.calls if url == gmail.REVOKE_URL)
        self.assertEqual(revoke["data"]["token"], REFRESH_TOKEN)
        self.assertFalse(GmailAccount.objects.exists())
        self.assertEqual(EmailMessage.objects.filter(owner=self.user, source="gmail").count(), 2)

    def test_disconnect_deletes_account_even_if_google_fails(self):
        self.connect()
        self.google.revoke_status = 500
        response = self.client.post("/api/mails/gmail/disconnect/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["revoked"])
        self.assertFalse(GmailAccount.objects.exists())

    # ------------------------------------------------------------ configuration
    @override_settings(GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET="")
    def test_503_without_configuration(self):
        self.assertFalse(self.client.get("/api/mails/gmail/status/").data["configured"])
        self.assertEqual(self.client.post("/api/mails/gmail/connect/").status_code, 503)
        self.assertEqual(self.client.post("/api/mails/gmail/sync/").status_code, 503)
        self.connect()
        mail = EmailMessage.objects.create(owner=self.user, body="...", draft_reply="Merci.")
        self.assertEqual(self.client.post(f"/api/mails/{mail.id}/gmail-draft/").status_code, 503)
        self.assertEqual(self.google.calls, [])

    def test_token_key_falls_back_to_secret_key(self):
        token = gmail.encrypt_token("abc")
        with override_settings(SECRET_KEY="another-secret"):
            with self.assertRaises(gmail.GoogleError):
                gmail.decrypt_token(token)
        with override_settings(GMAIL_TOKEN_KEY="any passphrase"):
            self.assertEqual(gmail.decrypt_token(gmail.encrypt_token("abc")), "abc")

    # ------------------------------------------------------------ isolation
    def test_users_are_isolated(self):
        self.connect(self.other)
        foreign = EmailMessage.objects.create(owner=self.other, body="...", draft_reply="Merci.")
        status = self.client.get("/api/mails/gmail/status/").data
        self.assertFalse(status["connected"])
        self.assertEqual(status["email"], "")
        self.assertEqual(self.client.post("/api/mails/gmail/sync/").status_code, 400)
        self.assertEqual(self.client.post("/api/mails/gmail/disconnect/").status_code, 400)
        self.assertEqual(self.client.post(f"/api/mails/{foreign.id}/gmail-draft/").status_code, 404)
        self.assertTrue(GmailAccount.objects.filter(user=self.other).exists())
        self.assertEqual(self.google.calls, [])

        self.connect()
        self.client.post("/api/mails/gmail/sync/")
        self.assertEqual(EmailMessage.objects.filter(owner=self.other, source="gmail").count(), 0)

    def test_same_gmail_message_can_be_imported_by_two_users(self):
        self.connect()
        self.connect(self.other)
        self.client.post("/api/mails/gmail/sync/")
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post("/api/mails/gmail/sync/").data["imported"], 2)

    def test_gmail_endpoints_require_authentication(self):
        self.client.force_authenticate(None)
        for method, url in (("get", "status"), ("post", "connect"), ("post", "sync"), ("post", "disconnect")):
            self.assertEqual(getattr(self.client, method)(f"/api/mails/gmail/{url}/").status_code, 401)
