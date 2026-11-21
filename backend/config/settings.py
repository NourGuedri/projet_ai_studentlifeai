import json
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-change-me-in-production")
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "daphne",  # must come first: its runserver serves HTTP and WebSocket
    "channels",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    # project modules
    "accounts",
    "profiles",
    "learning",

    "notifications",
    "administration",
    "meetings",
    "mails",
    "closet",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Tunis"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_RATES": {"password_reset": "5/hour"},
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

CORS_ALLOWED_ORIGINS = os.getenv(
    "CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",")

# Largest file a teacher can attach to a lesson (videos included), in megabytes.
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "300"))

# Password recovery. By default the e-mail is printed in the runserver terminal (no SMTP needed).
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
PASSWORD_RESET_TIMEOUT = 3600  # reset links are valid for 1 hour
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "1") == "1"
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "StudentLife AI <no-reply@studentlife.local>")

# Video calls of the Meetings module: WebRTC inside the app, signaling over WebSocket (Django Channels).
# In-memory layer: one server process only (enough for SQLite / development).
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
# STUN/TURN servers given to the browsers, as JSON, e.g.
# WEBRTC_ICE_SERVERS=[{"urls": "stun:stun.example.org:3478"}]. Empty list: same machine / local network only.
WEBRTC_ICE_SERVERS = json.loads(os.getenv("WEBRTC_ICE_SERVERS", "") or "[]")

# Meeting recordings: kept outside MEDIA_ROOT (never public), served by GET /api/meetings/<id>/audio/.
MEETINGS_AUDIO_ROOT = Path(os.getenv("MEETINGS_AUDIO_ROOT", "") or BASE_DIR / "private_media")
MEETING_MAX_AUDIO_MB = int(os.getenv("MEETING_MAX_AUDIO_MB", "100"))
# Most people one meeting can invite (e-mails and students of a formation together). It is not the number of
# people connected to a call at the same time (MAX_PEERS in meetings/consumers.py).
MEETING_MAX_INVITES = int(os.getenv("MEETING_MAX_INVITES", "50"))
# Transcription and AI analysis run in a background thread after a recording is sent. "1" runs them in the
# request itself (the tests set it with override_settings).
MEETINGS_SYNC_PROCESSING = os.getenv("MEETINGS_SYNC_PROCESSING", "0") == "1"
# faster-whisper model: tiny, base, small, medium... (bigger = more accurate but slower on CPU).
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
# Language of the meetings, forced instead of detected (detection is unreliable on short or noisy recordings).
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "fr")

# Gmail connection of the E-mails module (US 32 to 34): OAuth 2.0 Google, scopes gmail.readonly and gmail.compose.
# Without GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET the Gmail features answer 503 (manual import keeps working).
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
# Must be listed as an authorised redirect URI of the OAuth client in the Google Cloud console.
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "") or "http://localhost:8000/api/mails/gmail/callback/"
# Fernet key used to encrypt the Gmail refresh tokens in the database. Empty: derived from SECRET_KEY
# (changing SECRET_KEY then makes the stored tokens unreadable: the users have to reconnect Gmail).
GMAIL_TOKEN_KEY = os.getenv("GMAIL_TOKEN_KEY", "")
# Number of most recent inbox messages imported by one synchronisation.
GMAIL_SYNC_LIMIT = int(os.getenv("GMAIL_SYNC_LIMIT", "20"))
