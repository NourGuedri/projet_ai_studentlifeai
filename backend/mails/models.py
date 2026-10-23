from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class EmailMessage(models.Model):
    """An e-mail imported by hand (copy-paste). Nothing is ever sent from the application."""

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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at", "-created_at"]
        verbose_name = "e-mail"

    def __str__(self):
        return self.subject or f"E-mail de {self.sender or 'expéditeur inconnu'}"
