from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from common import ai

from . import services
from .models import EmailMessage
from .serializers import EmailMessageSerializer


# ------------------------------------------------------------------ e-mails (US 32 to 34)
class EmailMessageViewSet(viewsets.ModelViewSet):
    """E-mails pasted by the user. The AI only suggests: replies are drafts and are never sent."""

    serializer_class = EmailMessageSerializer

    def get_queryset(self):
        qs = EmailMessage.objects.filter(owner=self.request.user)
        important = self.request.query_params.get("important", "").lower()
        if important in ("true", "1"):
            qs = qs.filter(is_important=True)
        elif important in ("false", "0"):
            qs = qs.filter(is_important=False)
        return qs

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def _run_ai(self, func, apply):
        email = self.get_object()
        try:
            result = func(email)
        except ai.AINotConfigured as exc:
            return Response({"detail": f"{exc} L'analyse par IA est indisponible pour le moment."}, status=503)
        except ai.AIError as exc:
            return Response({"detail": str(exc)}, status=502)
        apply(email, result)
        email.save()
        return Response(self.get_serializer(email).data)

    @action(detail=True, methods=["post"])
    def classify(self, request, pk=None):
        def apply(email, result):
            email.is_important, email.importance_reason = result
        return self._run_ai(services.classify, apply)

    @action(detail=True, methods=["post"])
    def summarize(self, request, pk=None):
        return self._run_ai(services.summarize, lambda email, summary: setattr(email, "summary", summary))

    @action(detail=True, methods=["post"], url_path="extract-tasks")
    def extract_tasks(self, request, pk=None):
        return self._run_ai(services.extract_tasks, lambda email, tasks: setattr(email, "tasks", tasks))

    @action(detail=True, methods=["post"], url_path="draft-reply")
    def draft_reply(self, request, pk=None):
        return self._run_ai(
            lambda email: services.draft_reply(email, request.user),
            lambda email, reply: setattr(email, "draft_reply", reply),
        )
