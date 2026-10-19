from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from common import ai

from .models import EmailMessage

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
