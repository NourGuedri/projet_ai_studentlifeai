"""Shared format for AI-extracted tasks: {"title", "assignee", "due_date" (YYYY-MM-DD or null)}.
Kept deliberately simple so a future Planning module can import these tasks as they are."""
from rest_framework import serializers


class TaskSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=300)
    assignee = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    due_date = serializers.DateField(required=False, allow_null=True, default=None)


def clean_tasks(raw):
    """Validate a list of tasks returned by the AI. Raises serializers.ValidationError if it is not a list.
    Items without a title are dropped; an unreadable due date becomes null instead of losing the task."""
    if not isinstance(raw, list):
        raise serializers.ValidationError("La liste des tâches est invalide.")
    tasks = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        data = {
            "title": str(item.get("title") or "").strip()[:300],
            "assignee": str(item.get("assignee") or "").strip()[:150],
            "due_date": item.get("due_date") or None,
        }
        serializer = TaskSerializer(data=data)
        if not serializer.is_valid() and "due_date" in serializer.errors:
            serializer = TaskSerializer(data={**data, "due_date": None})
        if serializer.is_valid():
            tasks.append(dict(serializer.data))
    return tasks
