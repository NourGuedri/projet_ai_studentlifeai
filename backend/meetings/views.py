from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from common import ai
from learning.models import Formation
from notifications.services import notify_many

from . import services
from .calls import make_ticket
from .models import Meeting, RecordingSession
from .serializers import MeetingSerializer, RecordingUploadSerializer, display_name

AUDIO_CONTENT_TYPES = {
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".webm": "audio/webm", ".ogg": "audio/ogg",
}
BUSY = "Un traitement automatique de cette réunion est en cours. Attendez qu'il se termine."


# ------------------------------------------------------------------ meetings (US 28 to 31)
class MeetingViewSet(viewsets.ModelViewSet):
    serializer_class = MeetingSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        # The organizer and the invited participants see the meeting.
        user = self.request.user
        return (
            Meeting.objects.filter(Q(owner=user) | Q(participants=user)).distinct()
            .select_related("owner").prefetch_related("participants")
        )

    def get_object(self):
        # Participants only read: editing, deleting and the AI actions belong to the organizer.
        meeting = super().get_object()
        if self.request.method not in permissions.SAFE_METHODS and meeting.owner_id != self.request.user.id:
            raise PermissionDenied("Seul l'organisateur de la réunion peut effectuer cette action.")
        return meeting

    def _notify_invited(self, meeting, users):
        if not users:
            return
        when = meeting.scheduled_at and timezone.localtime(meeting.scheduled_at)
        when_text = when.strftime("le %d/%m/%Y à %H:%M") if when else meeting.date.strftime("le %d/%m/%Y")
        message = f"{display_name(meeting.owner)} vous invite à la réunion « {meeting.title} » {when_text}."
        notify_many(users, "Invitation à une réunion", message, link=f"/reunions/{meeting.id}")

    @staticmethod
    def _status_from_transcript(meeting):
        return Meeting.TRANSCRIBED if meeting.transcript.strip() else Meeting.DRAFT

    def perform_create(self, serializer):
        meeting = serializer.save(owner=self.request.user)
        if meeting.transcript.strip():
            meeting.status = Meeting.TRANSCRIBED
            meeting.save(update_fields=["status"])
        self._notify_invited(meeting, serializer.new_participants)

    def update(self, request, *args, **kwargs):
        meeting = self.get_object()
        if meeting.is_processing and ("transcript" in request.data or "audio_file" in request.data):
            return Response({"detail": BUSY}, status=409)
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        meeting = serializer.save()
        if "transcript" in serializer.validated_data:
            meeting.status = self._status_from_transcript(meeting)
            meeting.save(update_fields=["status"])
        self._notify_invited(meeting, serializer.new_participants)

    # ------------------------------------------------------------ manual steps (organizer only)
    def _fail(self, meeting, message, status=400):
        # A failed retry must not hide results the meeting already has.
        if not meeting.has_results():
            meeting.status = Meeting.FAILED
            meeting.save(update_fields=["status", "updated_at"])
        return Response({"detail": message}, status=status)

    def _manual_step(self, request):
        """The meeting for a manual step, or an error Response."""
        meeting = self.get_object()
        if meeting.is_processing:
            return None, Response({"detail": BUSY}, status=409)
        return meeting, None

    def _done(self, meeting, fields):
        # A manual step that succeeds clears a previous automatic failure.
        if meeting.processing_status == Meeting.ERROR:
            meeting.processing_status, meeting.processing_error = Meeting.IDLE, ""
            fields += ["processing_status", "processing_error"]
        meeting.save(update_fields=[*fields, "updated_at"])
        return Response(self.get_serializer(meeting).data)

    def _run_ai(self, meeting, func):
        try:
            services.check_transcript(meeting)
        except services.TranscriptTooShort as exc:
            return None, Response({"detail": str(exc)}, status=400)
        try:
            return func(meeting), None
        except ai.AINotConfigured as exc:
            return None, self._fail(meeting, services.ai_error_message(exc), status=503)
        except ai.AIError as exc:
            return None, self._fail(meeting, str(exc), status=502)

    @action(detail=True, methods=["post"])
    def transcribe(self, request, pk=None):
        meeting, error = self._manual_step(request)
        if error:
            return error
        if not meeting.audio_file:
            return Response({"detail": "Aucun fichier audio. Collez directement le texte de la réunion."}, status=400)
        if not meeting.consent_confirmed:
            return Response({"detail": "Le consentement des participants n'a pas été confirmé."}, status=400)
        try:
            meeting.transcript = services.transcribe_audio(meeting.audio_file.path)
        except services.TranscriptionUnavailable as exc:
            return Response({"detail": str(exc)}, status=503)
        except services.TranscriptionError as exc:
            return self._fail(meeting, str(exc))
        meeting.status = Meeting.TRANSCRIBED
        return self._done(meeting, ["transcript", "status"])

    @action(detail=True, methods=["post"])
    def summarize(self, request, pk=None):
        meeting, error = self._manual_step(request)
        if error:
            return error
        result, error = self._run_ai(meeting, services.summarize)
        if error:
            return error
        meeting.summary, meeting.topics, meeting.key_points = result["summary"], result["topics"], result["key_points"]
        meeting.status = Meeting.ANALYZED
        return self._done(meeting, ["summary", "topics", "key_points", "status"])

    @action(detail=True, methods=["post"])
    def extract(self, request, pk=None):
        meeting, error = self._manual_step(request)
        if error:
            return error
        result, error = self._run_ai(meeting, services.extract)
        if error:
            return error
        meeting.decisions, meeting.tasks = result
        meeting.status = Meeting.ANALYZED
        return self._done(meeting, ["decisions", "tasks", "status"])

    # ------------------------------------------------------------ automatic processing
    @action(detail=True, methods=["post"])
    def process(self, request, pk=None):
        """Transcription (if there is audio), summary and extraction in the background."""
        meeting, error = self._manual_step(request)
        if error:
            return error
        if meeting.audio_file and not meeting.consent_confirmed:
            return Response({"detail": "Le consentement des participants n'a pas été confirmé."}, status=400)
        if not meeting.audio_file and len(meeting.transcript.strip()) < services.MIN_TRANSCRIPT_CHARS:
            return Response({"detail": "Ajoutez un enregistrement ou le texte de la réunion avant de lancer l'analyse."}, status=400)
        services.queue_processing(meeting)
        return Response(self.get_serializer(meeting).data, status=202)

    @action(detail=True, methods=["post"])
    def recording(self, request, pk=None):
        """Recording of the call, sent by the organizer's browser when it stops (US 28).

        Accepted only for a recording that really started, i.e. that every connected person accepted
        (see consumers.py); the processing starts right after."""
        meeting, error = self._manual_step(request)
        if error:
            return error
        upload = RecordingUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        with transaction.atomic():
            session = (
                RecordingSession.objects.select_for_update()
                .filter(meeting=meeting, pk=upload.validated_data["session"]).first()
            )
            if session is None:
                return Response({"session": ["Enregistrement inconnu pour cette réunion."]}, status=400)
            if session.started_at is None or session.status not in (RecordingSession.RECORDING, RecordingSession.STOPPED):
                return Response({
                    "detail": "Cet enregistrement n'a pas été accepté par tous les participants connectés : il ne peut pas être envoyé.",
                }, status=400)
            old_file = meeting.audio_file.name if meeting.audio_file else ""
            meeting.audio_file = upload.validated_data["audio_file"]
            meeting.consent_confirmed = True
            meeting.save(update_fields=["audio_file", "consent_confirmed", "updated_at"])
            session.status = RecordingSession.UPLOADED
            session.stopped_at = session.stopped_at or timezone.now()
            session.save(update_fields=["status", "stopped_at"])
            if old_file:
                storage = meeting.audio_file.storage
                transaction.on_commit(lambda: storage.delete(old_file))
            services.queue_processing(meeting)
        return Response(self.get_serializer(meeting).data, status=202)

    @action(detail=True, methods=["get"])
    def audio(self, request, pk=None):
        """The recording, for the organizer and the participants only (no public /media/ URL)."""
        meeting = get_object_or_404(self.get_queryset(), pk=pk)
        if not meeting.audio_file:
            raise Http404
        try:
            handle = meeting.audio_file.open("rb")
        except FileNotFoundError:
            raise Http404
        suffix = Path(meeting.audio_file.name).suffix.lower()
        response = FileResponse(
            handle, content_type=AUDIO_CONTENT_TYPES.get(suffix, "application/octet-stream"),
            filename=f"reunion-{meeting.id}{suffix}",
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @action(detail=False, methods=["get"], url_path="my-formations")
    def my_formations(self, request):
        """Formations taught by the user, for the "invite the students of a formation" list (read only)."""
        user = request.user
        enrolled = Q(enrollments__user__is_active=True) & ~Q(enrollments__user=user)
        formations = (
            Formation.objects.filter(teacher=user)
            .annotate(enrolled_count=Count("enrollments", filter=enrolled))
            .order_by("title", "id")
        )
        return Response([{"id": f.id, "title": f.title, "enrolled_count": f.enrolled_count} for f in formations])

    @action(detail=True, methods=["post"], url_path="call-ticket")
    def call_ticket(self, request, pk=None):
        """Short-lived ticket to open the call WebSocket (organizer and participants, like reading)."""
        # Not get_object(): it reserves POST to the organizer, while every participant may join the call.
        meeting = get_object_or_404(self.get_queryset(), pk=pk)
        if not meeting.call_room:
            return Response({"detail": "Cette réunion n'est pas un appel audio/vidéo."}, status=400)
        return Response({
            "ticket": make_ticket(request.user, meeting), "ice_servers": settings.WEBRTC_ICE_SERVERS,
            "max_peers": settings.MEETING_MAX_PEERS,
        })
