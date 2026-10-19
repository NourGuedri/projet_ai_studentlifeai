from rest_framework import serializers

from common.tasks import clean_tasks

from .models import EmailMessage


class EmailMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailMessage
        fields = (
            "id", "sender", "subject", "body", "received_at", "is_important", "importance_reason", "summary",
            "tasks", "draft_reply", "created_at",
        )
        read_only_fields = ("is_important", "importance_reason", "summary", "tasks")

    def validate_body(self, value):
        if not value.strip():
            raise serializers.ValidationError("Collez le contenu de l'e-mail.")
        return value


# ------------------------------------------------------------------ AI responses
class ClassifyResponseSerializer(serializers.Serializer):
    is_important = serializers.BooleanField()
    reason = serializers.CharField()


class SummaryResponseSerializer(serializers.Serializer):
    summary = serializers.CharField()


class TasksResponseSerializer(serializers.Serializer):
    tasks = serializers.ListField(child=serializers.DictField(), allow_empty=True)

    def validate_tasks(self, value):
        return clean_tasks(value)


class DraftReplyResponseSerializer(serializers.Serializer):
    reply = serializers.CharField()
