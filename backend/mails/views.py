from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common import ai

from . import gmail, services
from .models import EmailMessage, GmailAccount
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

    @action(detail=True, methods=["post"], url_path="gmail-draft")
    def gmail_draft(self, request, pk=None):
        """Puts draft_reply in the user's Gmail drafts, in the same thread. Nothing is sent."""
        email = self.get_object()
        if not email.draft_reply.strip():
            return Response({"detail": "Générez ou écrivez d'abord un brouillon de réponse."}, status=400)
        account = GmailAccount.objects.filter(user=request.user).first()
        if account is None:
            return Response({"detail": "Connectez d'abord votre compte Gmail."}, status=400)
        return _google_call(lambda: Response({
            "draft_id": gmail.create_draft(account, email),
            "detail": f"Brouillon créé dans Gmail ({account.email}). Rien n'a été envoyé : relisez-le et envoyez-le depuis Gmail.",
        }))


# ------------------------------------------------------------------ Gmail connection
def _google_call(func):
    try:
        return func()
    except gmail.GoogleNotConfigured as exc:
        return Response({"detail": str(exc)}, status=503)
    except gmail.GoogleError as exc:
        return Response({"detail": str(exc)}, status=502)


def _status(user):
    account = GmailAccount.objects.filter(user=user).first()
    return {
        "configured": gmail.is_configured(),
        "connected": account is not None,
        "email": account.email if account else "",
        "connected_at": account.connected_at if account else None,
        "last_synced_at": account.last_synced_at if account else None,
    }


class GmailStatusView(APIView):
    def get(self, request):
        return Response(_status(request.user))


class GmailConnectView(APIView):
    def post(self, request):
        return _google_call(lambda: Response({"url": gmail.authorization_url(request.user)}))


class GmailCallbackView(APIView):
    """Google redirects the browser here: no JWT, the user is identified by the signed state."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        def back(result):
            return HttpResponseRedirect(f"{settings.FRONTEND_URL.rstrip('/')}/emails?gmail={result}")

        uid = gmail.read_state(request.query_params.get("state"))
        user = get_user_model().objects.filter(pk=uid, is_active=True).first() if uid else None
        code = request.query_params.get("code")
        if user is None or not code or request.query_params.get("error"):
            return back("error")
        try:
            gmail.connect(user, code)
        except (gmail.GoogleNotConfigured, gmail.GoogleError):
            return back("error")
        return back("connected")


class GmailSyncView(APIView):
    def post(self, request):
        def run():
            gmail.require_configured()
            account = GmailAccount.objects.filter(user=request.user).first()
            if account is None:
                return Response({"detail": "Connectez d'abord votre compte Gmail."}, status=400)
            return Response({"imported": gmail.sync(account), **_status(request.user)})
        return _google_call(run)


class GmailDisconnectView(APIView):
    def post(self, request):
        account = GmailAccount.objects.filter(user=request.user).first()
        if account is None:
            return Response({"detail": "Aucun compte Gmail n'est connecté."}, status=400)
        revoked = gmail.disconnect(account)
        detail = "Compte Gmail déconnecté. Les e-mails déjà importés restent dans StudentLife." if revoked else (
            "Compte Gmail déconnecté de StudentLife, mais Google n'a pas confirmé la révocation : retirez l'accès "
            "depuis https://myaccount.google.com/permissions."
        )
        return Response({"revoked": revoked, "detail": detail, **_status(request.user)})
