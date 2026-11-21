"""Gmail connection (US 32 to 34): OAuth 2.0 Google and the Gmail REST API, called with requests.

Scopes: gmail.readonly (import the inbox) and gmail.compose (create drafts). Nothing is ever sent: the application
only creates drafts that the user reviews and sends from Gmail.
Security: the refresh token is stored encrypted (Fernet) and is never returned to the frontend nor logged;
access tokens are short-lived and only kept in memory for the current request.
"""
import base64
import hashlib
import logging
import re
import secrets
from datetime import datetime, timezone as dt_timezone
from email.message import EmailMessage as MimeMessage
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlencode

import requests
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core import signing
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import EmailMessage, GmailAccount
from .services import MAX_BODY_CHARS

logger = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API_URL = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.compose"]
TIMEOUT = 15  # seconds, for every call to Google

STATE_SALT = "mails.gmail.oauth-state"
STATE_MAX_AGE = 600  # the authorisation must be completed within 10 minutes


class GoogleNotConfigured(Exception):
    """GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are missing (503)."""


class GoogleError(Exception):
    """Google refused or could not be reached (502). The message is in French and safe to show."""


def is_configured():
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


def require_configured():
    if not is_configured():
        raise GoogleNotConfigured("La connexion à Gmail n'est pas configurée sur le serveur (identifiants Google manquants).")


# ------------------------------------------------------------------ token encryption
def _fernet():
    key = settings.GMAIL_TOKEN_KEY
    if key:
        try:
            return Fernet(key)
        except ValueError:  # not a Fernet key: derive one from the given secret
            pass
    secret = key or settings.SECRET_KEY
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(f"gmail-token:{secret}".encode()).digest()))


def encrypt_token(token):
    return _fernet().encrypt(token.encode()).decode()


def decrypt_token(value):
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        raise GoogleError("Le jeton Gmail enregistré est illisible. Déconnectez puis reconnectez votre compte Gmail.")


# ------------------------------------------------------------------ OAuth
def make_state(user):
    return signing.dumps({"uid": user.pk, "nonce": secrets.token_urlsafe(16)}, salt=STATE_SALT)


def read_state(state):
    """User id carried by a signed state, or None if it is invalid, tampered with or expired."""
    try:
        data = signing.loads(state or "", salt=STATE_SALT, max_age=STATE_MAX_AGE)
    except signing.BadSignature:  # SignatureExpired is a subclass
        return None
    return data.get("uid") if isinstance(data, dict) else None


def authorization_url(user):
    require_configured()
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "false",
        "state": make_state(user),
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _google_error_code(response):
    try:
        data = response.json()
    except ValueError:
        return ""
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return str(error.get("status") or error.get("code") or "")
    return str(error or "")


def _call(method, url, **kwargs):
    """HTTP call to Google. Only the status and Google's error code are logged, never the payloads (tokens)."""
    try:
        response = requests.request(method, url, timeout=TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        logger.warning("Google unreachable (%s %s): %s", method, url.split("?")[0], type(exc).__name__)
        raise GoogleError("Impossible de joindre Google. Réessayez dans quelques instants.")
    if response.status_code >= 400:
        logger.warning("Google answered %s to %s %s (%s)", response.status_code, method, url.split("?")[0],
                       _google_error_code(response))
    return response


def _token_request(data):
    require_configured()
    response = _call("POST", TOKEN_URL, data={
        "client_id": settings.GOOGLE_CLIENT_ID, "client_secret": settings.GOOGLE_CLIENT_SECRET, **data,
    })
    if response.status_code == 400 and _google_error_code(response) == "invalid_grant":
        raise GoogleError("L'accès à Gmail a expiré ou a été retiré. Déconnectez puis reconnectez votre compte Gmail.")
    if response.status_code != 200:
        raise GoogleError("Google a refusé l'authentification. Réessayez.")
    return response.json()


def exchange_code(code):
    """Authorisation code -> (refresh_token, access_token)."""
    data = _token_request({"code": code, "grant_type": "authorization_code", "redirect_uri": settings.GOOGLE_REDIRECT_URI})
    if not data.get("refresh_token") or not data.get("access_token"):
        raise GoogleError("Google n'a pas fourni d'accès hors ligne. Recommencez la connexion.")
    return data["refresh_token"], data["access_token"]


def access_token(account):
    return _token_request({"refresh_token": decrypt_token(account.refresh_token_encrypted),
                           "grant_type": "refresh_token"})["access_token"]


def _api(method, path, token, **kwargs):
    response = _call(method, f"{API_URL}{path}", headers={"Authorization": f"Bearer {token}"}, **kwargs)
    if response.status_code == 403:
        raise GoogleError("Google refuse l'accès à Gmail (autorisation insuffisante). Reconnectez votre compte Gmail.")
    if response.status_code >= 400:
        raise GoogleError("Gmail a renvoyé une erreur. Réessayez dans quelques instants.")
    return response.json()


def connect(user, code):
    """Finishes the OAuth flow: exchanges the code and stores the (encrypted) refresh token."""
    refresh_token, token = exchange_code(code)
    address = _api("GET", "/profile", token).get("emailAddress", "")
    account, _ = GmailAccount.objects.update_or_create(user=user, defaults={
        "email": address, "refresh_token_encrypted": encrypt_token(refresh_token),
    })
    return account


def disconnect(account):
    """Revokes the token at Google, then deletes the account. Returns False if Google could not revoke it."""
    revoked = False
    try:
        token = decrypt_token(account.refresh_token_encrypted)
        response = _call("POST", REVOKE_URL, data={"token": token})
        # 400 invalid_token: already revoked by the user from their Google account.
        revoked = response.status_code == 200 or _google_error_code(response) == "invalid_token"
    except GoogleError:
        pass
    account.delete()
    return revoked


# ------------------------------------------------------------------ import
class _HTMLToText(HTMLParser):
    BLOCKS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol", "blockquote", "hr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.skip += 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html):
    parser = _HTMLToText()
    parser.feed(html)
    parser.close()
    text = unescape("".join(parser.parts)).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _decode(data):
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _find_part(part, mime):
    if part.get("mimeType") == mime and part.get("body", {}).get("data") and not part.get("filename"):
        return part["body"]["data"]
    for child in part.get("parts") or []:
        found = _find_part(child, mime)
        if found:
            return found
    return None


def message_body(payload):
    """Plain text of a Gmail message: the text/plain part, else the text/html part converted to text."""
    plain = _find_part(payload, "text/plain")
    if plain:
        text = _decode(plain).replace("\r\n", "\n").strip()
    else:
        html = _find_part(payload, "text/html")
        text = html_to_text(_decode(html)) if html else ""
    return text[:MAX_BODY_CHARS]


def _headers(payload):
    return {h.get("name", "").lower(): h.get("value", "") for h in payload.get("headers") or []}


def _received_at(message, headers):
    if message.get("internalDate"):
        return datetime.fromtimestamp(int(message["internalDate"]) / 1000, tz=dt_timezone.utc)
    try:
        return parsedate_to_datetime(headers.get("date", ""))
    except (TypeError, ValueError):
        return None


def sync(account):
    """Imports the GMAIL_SYNC_LIMIT most recent inbox messages that are not imported yet. Returns the count."""
    token = access_token(account)
    listing = _api("GET", "/messages", token, params={"labelIds": "INBOX", "maxResults": settings.GMAIL_SYNC_LIMIT})
    ids = [m["id"] for m in listing.get("messages") or [] if m.get("id")]
    known = set(EmailMessage.objects.filter(owner=account.user, gmail_id__in=ids).values_list("gmail_id", flat=True))

    imported = 0
    for gmail_id in ids:
        if gmail_id in known:
            continue
        message = _api("GET", f"/messages/{gmail_id}", token, params={"format": "full"})
        payload = message.get("payload") or {}
        headers = _headers(payload)
        try:
            with transaction.atomic():
                EmailMessage.objects.create(
                    owner=account.user, source=EmailMessage.SOURCE_GMAIL,
                    gmail_id=gmail_id, gmail_thread_id=message.get("threadId", ""),
                    sender=headers.get("from", "")[:255], subject=headers.get("subject", "")[:300],
                    received_at=_received_at(message, headers),
                    body=message_body(payload) or message.get("snippet", "") or "(e-mail sans contenu texte)",
                )
        except IntegrityError:  # imported meanwhile by a concurrent synchronisation
            continue
        imported += 1

    account.last_synced_at = timezone.now()
    account.save(update_fields=["last_synced_at"])
    return imported


# ------------------------------------------------------------------ drafts
def _reply_subject(subject):
    subject = subject.strip()
    return subject if subject.lower().startswith("re:") else f"Re: {subject or '(sans objet)'}"


def create_draft(account, email):
    """Creates in Gmail a draft replying to `email` with its draft_reply. The draft is never sent."""
    token = access_token(account)
    mime = MimeMessage()
    if email.sender:
        mime["To"] = email.sender
    mime["Subject"] = _reply_subject(email.subject)
    message = {}
    if email.source == EmailMessage.SOURCE_GMAIL and email.gmail_id:
        original = _api("GET", f"/messages/{email.gmail_id}", token, params={
            "format": "metadata", "metadataHeaders": ["Message-ID", "References"],
        })
        headers = _headers(original.get("payload") or {})
        if headers.get("message-id"):
            mime["In-Reply-To"] = headers["message-id"]
            mime["References"] = f"{headers.get('references', '')} {headers['message-id']}".strip()
        if email.gmail_thread_id or original.get("threadId"):
            message["threadId"] = email.gmail_thread_id or original["threadId"]
    mime.set_content(email.draft_reply)
    message["raw"] = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    return _api("POST", "/drafts", token, json={"message": message}).get("id", "")
