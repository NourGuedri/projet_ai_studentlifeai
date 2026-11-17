import secrets
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

from .storage import audio_storage

User = settings.AUTH_USER_MODEL
# webm and ogg: what the browsers produce when the call is recorded (MediaRecorder).
AUDIO_EXTENSIONS = ["mp3", "wav", "m4a", "webm", "ogg"]
# A processing still "running" after this long was interrupted (server restarted): it may be launched again.
PROCESSING_STALE_AFTER = timedelta(hours=2)


def new_call_room():
    """Unpredictable internal room id of a call, letters and digits only."""
    token = "".join(c for c in secrets.token_urlsafe(24) if c.isalnum())
    return f"StudentLife-{token}"


def audio_path(instance, filename):
    # Random name: the file name cannot be guessed.
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
    # Automatic processing after a recording is sent: transcription, then summary and extraction.
    IDLE, TRANSCRIBING, ANALYZING, DONE, ERROR = "idle", "transcribing", "analyzing", "done", "error"
    PROCESSING_STATUSES = [
        (IDLE, "Aucun traitement"),
        (TRANSCRIBING, "Transcription en cours"),
        (ANALYZING, "Analyse en cours"),
        (DONE, "Traitement terminé"),
        (ERROR, "Échec du traitement"),
    ]

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="meetings")
    title = models.CharField(max_length=200)
    date = models.DateField(default=timezone.localdate)
    # Private storage (outside MEDIA_ROOT): served only by GET /api/meetings/<id>/audio/.
    audio_file = models.FileField(
        upload_to=audio_path, storage=audio_storage, blank=True,
        validators=[FileExtensionValidator(AUDIO_EXTENSIONS)],
    )
    consent_confirmed = models.BooleanField(default=False)
    transcript = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    topics = models.JSONField(default=list, blank=True)  # ["..."]: subjects discussed
    key_points = models.JSONField(default=list, blank=True)  # ["..."]: important points
    decisions = models.JSONField(default=list, blank=True)
    tasks = models.JSONField(default=list, blank=True)  # [{"title", "assignee", "due_date"}], see common/tasks.py
    status = models.CharField(max_length=12, choices=STATUSES, default=DRAFT)
    processing_status = models.CharField(max_length=12, choices=PROCESSING_STATUSES, default=IDLE)
    processing_error = models.TextField(blank=True)
    # In-app audio/video call (WebRTC, see consumers.py): the room exists only for meetings planned as a call.
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

    def has_results(self):
        return bool(self.summary.strip() or self.topics or self.key_points or self.decisions or self.tasks)

    @property
    def is_processing(self):
        running = self.processing_status in (self.TRANSCRIBING, self.ANALYZING)
        return running and (not self.updated_at or timezone.now() - self.updated_at < PROCESSING_STALE_AFTER)

    def ensure_call_room(self):
        """Give the meeting a call room if it has none yet (not saved)."""
        if not self.call_room:
            room = new_call_room()
            while Meeting.objects.filter(call_room=room).exists():
                room = new_call_room()
            self.call_room = room


class RecordingSession(models.Model):
    """A recording asked by the organizer during a call (exigence 8.1). It starts only once every person
    connected to the call has accepted; each answer is a RecordingConsent (who, when, yes or no)."""

    PENDING, RECORDING, STOPPED, UPLOADED, REFUSED, CANCELLED = (
        "pending", "recording", "stopped", "uploaded", "refused", "cancelled",
    )
    STATUSES = [
        (PENDING, "En attente des consentements"),
        (RECORDING, "Enregistrement en cours"),
        (STOPPED, "Arrêté"),
        (UPLOADED, "Envoyé"),
        (REFUSED, "Refusé par un participant"),
        (CANCELLED, "Annulé"),
    ]

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="recordings")
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING)
    requested_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]
        verbose_name = "demande d'enregistrement"

    def __str__(self):
        return f"{self.meeting} ({self.get_status_display()})"


class RecordingConsent(models.Model):
    session = models.ForeignKey(RecordingSession, on_delete=models.CASCADE, related_name="consents")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    accepted = models.BooleanField()
    answered_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["answered_at"]
        verbose_name = "consentement à l'enregistrement"
        constraints = [models.UniqueConstraint(fields=["session", "user"], name="recording_consent_once_per_user")]

    def __str__(self):
        return f"{self.user} : {'accepté' if self.accepted else 'refusé'}"


@receiver(post_delete, sender=Meeting)
def delete_audio_file(sender, instance, **kwargs):
    if instance.audio_file:
        instance.audio_file.delete(save=False)
