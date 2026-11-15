from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from common import ai
from notifications.services import notify_many

from . import services
from .models import Meeting
from .serializers import MeetingSerializer, display_name

MIN_TRANSCRIPT_CHARS = 30


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

    def perform_update(self, serializer):
        meeting = serializer.save()
        if "transcript" in serializer.validated_data:
            meeting.status = self._status_from_transcript(meeting)
            meeting.save(update_fields=["status"])
        self._notify_invited(meeting, serializer.new_participants)

    def _fail(self, meeting, message, status=400):
        # A failed retry must not hide results the meeting already has.
        has_results = meeting.summary.strip() or meeting.decisions or meeting.tasks
        if not has_results:
            meeting.status = Meeting.FAILED
            meeting.save(update_fields=["status", "updated_at"])
        return Response({"detail": message}, status=status)

    def _check_transcript(self, meeting):
        if len(meeting.transcript.strip()) < MIN_TRANSCRIPT_CHARS:
            return Response({
                "detail": "La transcription est vide ou trop courte. Transcrivez l'audio ou collez le texte de la réunion.",
            }, status=400)
        return None

    def _run_ai(self, meeting, func):
        try:
            return func(meeting), None
        except ai.AINotConfigured as exc:
            return None, self._fail(meeting, f"{exc} L'analyse par IA est indisponible pour le moment.", status=503)
        except ai.AIError as exc:
            return None, self._fail(meeting, str(exc), status=502)

    @action(detail=True, methods=["post"])
    def transcribe(self, request, pk=None):
        meeting = self.get_object()
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
        meeting.save()
        return Response(self.get_serializer(meeting).data)

    @action(detail=True, methods=["post"])
    def summarize(self, request, pk=None):
        meeting = self.get_object()
        if error := self._check_transcript(meeting):
            return error
        summary, error = self._run_ai(meeting, services.summarize)
        if error:
            return error
        meeting.summary = summary
        meeting.status = Meeting.ANALYZED
        meeting.save()
        return Response(self.get_serializer(meeting).data)

    @action(detail=True, methods=["post"])
    def extract(self, request, pk=None):
        meeting = self.get_object()
        if error := self._check_transcript(meeting):
            return error
        result, error = self._run_ai(meeting, services.extract)
        if error:
            return error
        meeting.decisions, meeting.tasks = result
        meeting.status = Meeting.ANALYZED
        meeting.save()
        return Response(self.get_serializer(meeting).data)
