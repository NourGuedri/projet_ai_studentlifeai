import secrets
import uuid
from pathlib import Path

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

User = settings.AUTH_USER_MODEL
AUDIO_EXTENSIONS = ["mp3", "wav", "m4a"]


def new_call_room():
    """Unpredictable Jitsi room name, letters and digits only."""
    token = "".join(c for c in secrets.token_urlsafe(24) if c.isalnum())
    return f"StudentLife-{token}"


def audio_path(instance, filename):
    # Random name: the URL cannot be guessed.
    return f"meetings/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class Meeting(models.Model):
    """A meeting: optional audio recording, its transcript and what the AI extracted from it."""

    DRAFT, TRANSCRIBED, ANALYZED, FAILED = "DRAFT", "TRANSCRIBED", "ANALYZED", "FAILED"
    STATUSES = [
        (DRAFT, "Brouillon"),
        (TRANSCRIBED, "Transcrite"),
        (ANALYZED, "Analysée"),
        (FAILED, "Échec"),
    ]

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="meetings")
    title = models.CharField(max_length=200)
    date = models.DateField(default=timezone.localdate)
    audio_file = models.FileField(
        upload_to=audio_path, blank=True, validators=[FileExtensionValidator(AUDIO_EXTENSIONS)],
    )
    consent_confirmed = models.BooleanField(default=False)
    transcript = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    decisions = models.JSONField(default=list, blank=True)
    tasks = models.JSONField(default=list, blank=True)  # [{"title", "assignee", "due_date"}], see common/tasks.py
    status = models.CharField(max_length=12, choices=STATUSES, default=DRAFT)
    # Video call (Jitsi): the room exists only for meetings planned as a call.
    scheduled_at = models.DateTimeField(null=True, blank=True)
    participants = models.ManyToManyField(User, related_name="invited_meetings", blank=True)
    call_room = models.CharField(max_length=80, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "réunion"
        constraints = [
            # Unique among meetings that have a call; many meetings can have no room ("").
            models.UniqueConstraint(fields=["call_room"], condition=~Q(call_room=""), name="meeting_unique_call_room"),
        ]

    def __str__(self):
        return self.title

    @property
    def call_url(self):
        if not self.call_room:
            return ""
        return f"{settings.JITSI_BASE_URL.rstrip('/')}/{self.call_room}"

    def ensure_call_room(self):
        """Give the meeting a Jitsi room if it has none yet (not saved)."""
        if not self.call_room:
            room = new_call_room()
            while Meeting.objects.filter(call_room=room).exists():
                room = new_call_room()
            self.call_room = room


@receiver(post_delete, sender=Meeting)
def delete_audio_file(sender, instance, **kwargs):
    if instance.audio_file:
        instance.audio_file.delete(save=False)
