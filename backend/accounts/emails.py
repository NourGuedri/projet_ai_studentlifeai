import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

logger = logging.getLogger(__name__)


def send_password_reset_email(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
    minutes = settings.PASSWORD_RESET_TIMEOUT // 60
    body = (
        f"Bonjour {user.first_name or ''},\n\n"
        "Vous avez demandé à réinitialiser votre mot de passe StudentLife AI.\n"
        f"Ouvrez ce lien pour en choisir un nouveau (valable {minutes} minutes) :\n\n{link}\n\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez simplement cet e-mail : votre mot de passe ne changera pas.\n"
    )
    try:
        send_mail("Réinitialisation de votre mot de passe", body, settings.DEFAULT_FROM_EMAIL, [user.email])
    except Exception:
        logger.exception("Could not send the password reset e-mail")
