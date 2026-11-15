from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from common.tasks import clean_tasks

from .models import Meeting

MAX_AUDIO_FILE = 25 * 1024 * 1024
MAX_PARTICIPANTS = 20


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
    # Video call: "video_call": true gives the meeting a Jitsi room.
    video_call = serializers.BooleanField(write_only=True, required=False, default=False)
    is_call = serializers.SerializerMethodField()
    call_url = serializers.CharField(read_only=True)
    participant_emails = serializers.ListField(
        child=serializers.EmailField(), write_only=True, required=False, allow_empty=True,
    )
    participants = ParticipantSerializer(many=True, read_only=True)
    owner_name = serializers.SerializerMethodField()
    is_owner = serializers.SerializerMethodField()

    class Meta:
        model = Meeting
        fields = (
            "id", "title", "date", "audio_file", "consent_confirmed", "transcript", "summary", "decisions",
            "tasks", "status", "status_label", "created_at", "updated_at",
            "scheduled_at", "video_call", "is_call", "call_url", "participant_emails", "participants",
            "owner_name", "is_owner",
        )
        read_only_fields = ("summary", "decisions", "tasks", "status")

    def _user(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

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
        if value and value.size > MAX_AUDIO_FILE:
            raise serializers.ValidationError("Fichier audio trop volumineux (25 Mo maximum).")
        return value

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


# ------------------------------------------------------------------ AI responses
class SummaryResponseSerializer(serializers.Serializer):
    summary = serializers.CharField()


class ExtractResponseSerializer(serializers.Serializer):
    decisions = serializers.ListField(child=serializers.CharField(max_length=500), allow_empty=True)
    tasks = serializers.ListField(child=serializers.DictField(), allow_empty=True)

    def validate_tasks(self, value):
        return clean_tasks(value)
