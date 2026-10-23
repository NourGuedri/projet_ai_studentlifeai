from rest_framework import serializers

from common.tasks import clean_tasks

from .models import Meeting

MAX_AUDIO_FILE = 25 * 1024 * 1024


class MeetingSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Meeting
        fields = (
            "id", "title", "date", "audio_file", "consent_confirmed", "transcript", "summary", "decisions",
            "tasks", "status", "status_label", "created_at", "updated_at",
        )
        read_only_fields = ("summary", "decisions", "tasks", "status")

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
        return attrs


# ------------------------------------------------------------------ AI responses
class SummaryResponseSerializer(serializers.Serializer):
    summary = serializers.CharField()


class ExtractResponseSerializer(serializers.Serializer):
    decisions = serializers.ListField(child=serializers.CharField(max_length=500), allow_empty=True)
    tasks = serializers.ListField(child=serializers.DictField(), allow_empty=True)

    def validate_tasks(self, value):
        return clean_tasks(value)
