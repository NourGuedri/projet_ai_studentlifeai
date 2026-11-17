from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from rest_framework import serializers

from common.tasks import clean_tasks

from .models import AUDIO_EXTENSIONS, Meeting

MAX_PARTICIPANTS = 20
MAX_AI_ITEMS = 20  # topics / key points kept from one AI answer


def validate_audio(value):
    """Format and size of a meeting recording (MEETING_MAX_AUDIO_MB, 100 MB by default)."""
    FileExtensionValidator(AUDIO_EXTENSIONS)(value)
    limit_mb = settings.MEETING_MAX_AUDIO_MB
    if value and value.size > limit_mb * 1024 * 1024:
        raise serializers.ValidationError(f"Fichier audio trop volumineux ({limit_mb} Mo maximum).")
    return value


def display_name(user):
    return user.get_full_name().strip() or user.email


class ParticipantSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    full_name = serializers.SerializerMethodField()
    email = serializers.EmailField(read_only=True)

    def get_full_name(self, user):
        return display_name(user)


class MeetingSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    # Video call: "video_call": true makes the meeting an in-app call (it gets an internal room id).
    video_call = serializers.BooleanField(write_only=True, required=False, default=False)
    is_call = serializers.SerializerMethodField()
    participant_emails = serializers.ListField(
        child=serializers.EmailField(), write_only=True, required=False, allow_empty=True,
    )
    participants = ParticipantSerializer(many=True, read_only=True)
    owner_name = serializers.SerializerMethodField()
    is_owner = serializers.SerializerMethodField()
    # The file has no public URL: it is read through GET /api/meetings/<id>/audio/ (audio_url).
    audio_file = serializers.FileField(write_only=True, required=False, allow_null=True)
    has_audio = serializers.SerializerMethodField()
    audio_url = serializers.SerializerMethodField()
    processing_label = serializers.CharField(source="get_processing_status_display", read_only=True)
    is_processing = serializers.BooleanField(read_only=True)

    class Meta:
        model = Meeting
        fields = (
            "id", "title", "date", "audio_file", "has_audio", "audio_url", "consent_confirmed", "transcript",
            "summary", "topics", "key_points", "decisions", "tasks", "status", "status_label",
            "processing_status", "processing_label", "processing_error", "is_processing", "created_at", "updated_at",
            "scheduled_at", "video_call", "is_call", "participant_emails", "participants",
            "owner_name", "is_owner",
        )
        read_only_fields = (
            "summary", "topics", "key_points", "decisions", "tasks", "status", "processing_status", "processing_error",
        )

    def _user(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    def get_has_audio(self, meeting):
        return bool(meeting.audio_file)

    def get_audio_url(self, meeting):
        # Relative to the API base URL (the frontend adds the JWT, see api.blob()).
        return f"/meetings/{meeting.id}/audio/" if meeting.audio_file else None

    def get_is_call(self, meeting):
        return bool(meeting.call_room)

    def get_owner_name(self, meeting):
        return display_name(meeting.owner)

    def get_is_owner(self, meeting):
        user = self._user()
        return bool(user and meeting.owner_id == user.id)

    def validate_participant_emails(self, value):
        emails = list(dict.fromkeys(e.strip().lower() for e in value if e.strip()))  # dedupe, keep order
        if len(emails) > MAX_PARTICIPANTS:
            raise serializers.ValidationError(f"Vous pouvez inviter {MAX_PARTICIPANTS} participants au maximum.")
        user = self._user()
        if user and user.email.lower() in emails:
            raise serializers.ValidationError("Vous ne pouvez pas vous inviter vous-même.")
        users = {u.email.lower(): u for u in get_user_model().objects.filter(email__in=emails, is_active=True)}
        unknown = [e for e in emails if e not in users]
        if unknown:
            raise serializers.ValidationError(f"Aucun compte actif ne correspond à : {', '.join(unknown)}.")
        return [users[e] for e in emails]

    def validate_audio_file(self, value):
        return validate_audio(value) if value else value

    def validate(self, attrs):
        has_audio = attrs["audio_file"] if "audio_file" in attrs else bool(self.instance and self.instance.audio_file)
        consent = attrs.get("consent_confirmed", self.instance.consent_confirmed if self.instance else False)
        if has_audio and not consent:
            raise serializers.ValidationError({
                "consent_confirmed": "Confirmez que tous les participants ont accepté l'enregistrement.",
            })
        is_call = attrs.get("video_call") or bool(self.instance and self.instance.call_room)
        scheduled_at = attrs["scheduled_at"] if "scheduled_at" in attrs else getattr(self.instance, "scheduled_at", None)
        if is_call and not scheduled_at:
            raise serializers.ValidationError({"scheduled_at": "Indiquez la date et l'heure de l'appel."})
        if attrs.get("scheduled_at"):
            # The meeting day follows the planned date and time (list sorting, AI prompts).
            attrs["date"] = timezone.localtime(attrs["scheduled_at"]).date()
        return attrs

    # The view reads this after save() to notify only the people who were just invited.
    new_participants = ()

    def _save_call(self, meeting, video_call, participants):
        if video_call and not meeting.call_room:
            meeting.ensure_call_room()
            meeting.save(update_fields=["call_room"])
        if participants is not None:
            before = set(meeting.participants.values_list("id", flat=True))
            meeting.participants.set(participants)
            self.new_participants = [u for u in participants if u.id not in before]
        return meeting

    def create(self, validated_data):
        video_call = validated_data.pop("video_call", False)
        participants = validated_data.pop("participant_emails", None)
        return self._save_call(super().create(validated_data), video_call, participants)

    def update(self, instance, validated_data):
        video_call = validated_data.pop("video_call", False)
        participants = validated_data.pop("participant_emails", None)
        return self._save_call(super().update(instance, validated_data), video_call, participants)


class RecordingUploadSerializer(serializers.Serializer):
    """Recording of a call, sent by the organizer's browser when the recording stops."""
    session = serializers.IntegerField()
    audio_file = serializers.FileField()

    def validate_audio_file(self, value):
        return validate_audio(value)


# ------------------------------------------------------------------ AI responses
def clean_items(raw, max_length):
    """Short sentences from the AI: stripped, without blanks nor duplicates, MAX_AI_ITEMS at most."""
    items = []
    for item in raw:
        text = " ".join(str(item).split())[:max_length]
        if text and text not in items:
            items.append(text)
    return items[:MAX_AI_ITEMS]


class SummaryResponseSerializer(serializers.Serializer):
    summary = serializers.CharField()
    topics = serializers.ListField(child=serializers.CharField(allow_blank=True), allow_empty=True)
    key_points = serializers.ListField(child=serializers.CharField(allow_blank=True), allow_empty=True)

    def validate_topics(self, value):
        return clean_items(value, 200)

    def validate_key_points(self, value):
        return clean_items(value, 500)


class ExtractResponseSerializer(serializers.Serializer):
    decisions = serializers.ListField(child=serializers.CharField(max_length=500), allow_empty=True)
    tasks = serializers.ListField(child=serializers.DictField(), allow_empty=True)

    def validate_tasks(self, value):
        return clean_tasks(value)
