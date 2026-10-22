from django.conf import settings
from django.db import models


class Notification(models.Model):
    """A message shown in the bell / notifications page of one user.

    Other modules create them with `notifications.services.notify(...)`.
    """

    KINDS = [
        ("info", "Information"),
        ("success", "Succès"),
        ("warning", "Avertissement"),
        ("announcement", "Annonce"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=12, choices=KINDS, default="info")
    title = models.CharField(max_length=150)
    message = models.TextField(blank=True)
    link = models.CharField(max_length=200, blank=True, help_text="Chemin interne du frontend, ex. /learning/formations/3")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "is_read"])]

    def __str__(self):
        return f"{self.title} → {self.user}"
