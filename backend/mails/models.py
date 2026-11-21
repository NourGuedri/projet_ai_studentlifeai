from django.conf import settings
from django.db import models
from django.db.models import Q

User = settings.AUTH_USER_MODEL


class EmailMessage(models.Model):
    """An e-mail pasted by hand or imported from Gmail. Nothing is ever sent from the application."""

    SOURCE_MANUAL = "manual"
    SOURCE_GMAIL = "gmail"
    SOURCES = [(SOURCE_MANUAL, "Ajout manuel"), (SOURCE_GMAIL, "Gmail")]

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_messages")
    sender = models.CharField(max_length=255, blank=True)
    subject = models.CharField(max_length=300, blank=True)
    body = models.TextField()
    received_at = models.DateTimeField(null=True, blank=True)
    is_important = models.BooleanField(null=True, blank=True)  # None: not analysed yet
    importance_reason = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    tasks = models.JSONField(default=list, blank=True)  # [{"title", "assignee", "due_date"}], see common/tasks.py
    draft_reply = models.TextField(blank=True)
    source = models.CharField(max_length=10, choices=SOURCES, default=SOURCE_MANUAL)
    gmail_id = models.CharField(max_length=64, blank=True, default="")  # Gmail message id ("" if manual)
    gmail_thread_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at", "-created_at"]
        verbose_name = "e-mail"
        constraints = [
            # A Gmail message is imported only once per user.
            models.UniqueConstraint(fields=["owner", "gmail_id"], condition=~Q(gmail_id=""),
                                    name="mails_unique_gmail_id_per_owner"),
        ]

    def __str__(self):
        return self.subject or f"E-mail de {self.sender or 'expéditeur inconnu'}"


class GmailAccount(models.Model):
    """The Gmail account a user connected. Only the refresh token is kept, encrypted (see mails/gmail.py)."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="gmail_account")
    email = models.EmailField()
    refresh_token_encrypted = models.TextField()  # Fernet token, never sent to the frontend
    connected_at = models.DateTimeField(auto_now_add=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "compte Gmail"
        verbose_name_plural = "comptes Gmail"

    def __str__(self):
        return f"{self.email} ({self.user})"

    def __repr__(self):  # never show the encrypted token in logs or tracebacks
        return f"<GmailAccount {self.pk} {self.email}>"
