from django.conf import settings
from django.db import models


class Report(models.Model):
    """A user flags a formation or a quiz; an administrator reviews it (BF51)."""

    TARGETS = [("formation", "Formation"), ("quiz", "Quiz")]
    REASONS = [
        ("inappropriate", "Contenu inapproprié"),
        ("copyright", "Droits d'auteur"),
        ("incorrect", "Informations erronées"),
        ("spam", "Spam ou publicité"),
        ("other", "Autre"),
    ]
    STATUSES = [("open", "Ouvert"), ("resolved", "Traité"), ("dismissed", "Rejeté")]

    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports_made")
    target_type = models.CharField(max_length=10, choices=TARGETS)
    target_id = models.PositiveIntegerField()
    target_title = models.CharField(max_length=200, help_text="Titre au moment du signalement (le contenu peut être supprimé ensuite).")
    reason = models.CharField(max_length=15, choices=REASONS, default="other")
    details = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default="open")
    resolution_note = models.TextField(blank=True)
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reports_handled")
    handled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["status"]), models.Index(fields=["target_type", "target_id"])]

    def __str__(self):
        return f"Signalement {self.target_type} #{self.target_id} ({self.status})"
