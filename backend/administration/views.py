from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsAdminRole
from learning.models import Course, Enrollment, Formation, Quiz, QuizAttempt
from notifications.services import notify, notify_many

from .models import Report
from .serializers import (
    AdminFormationSerializer,
    AdminUserCreateSerializer,
    AdminUserSerializer,
    AnnouncementSerializer,
    ReportCreateSerializer,
    ReportResolveSerializer,
    ReportSerializer,
    display_name,
)
from .targets import get_target, target_link, target_owner

User = get_user_model()


class AdminPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class AdminOnly:
    permission_classes = [IsAuthenticated, IsAdminRole]
    pagination_class = AdminPagination


# ------------------------------------------------------------------ users
class AdminUserViewSet(AdminOnly, mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                       mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_serializer_class(self):
        return AdminUserCreateSerializer if self.action == "create" else AdminUserSerializer

    def get_queryset(self):
        qs = User.objects.annotate(
            formations_count=Count("formations", distinct=True),
            enrollments_count=Count("enrollments", distinct=True),
            attempts_count=Count("attempts", distinct=True),
        ).order_by("-date_joined", "-id")
        params = self.request.query_params
        q = params.get("q", "").strip()
        if q:
            qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
        if params.get("role") in dict(User.ROLES):
            qs = qs.filter(role=params["role"])
        if params.get("active") in ("0", "1"):
            qs = qs.filter(is_active=params["active"] == "1")
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(AdminUserSerializer(user, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        if instance.pk == self.request.user.pk:
            raise ValidationError("Vous ne pouvez pas supprimer votre propre compte.")
        if instance.role == "admin" and instance.is_active and not User.objects.filter(role="admin", is_active=True).exclude(pk=instance.pk).exists():
            raise ValidationError("Il doit rester au moins un administrateur actif.")
        instance.delete()


# ------------------------------------------------------------------ formations (moderation)
class AdminFormationViewSet(AdminOnly, mixins.ListModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = AdminFormationSerializer

    def get_queryset(self):
        open_reports = (
            Report.objects.filter(status="open", target_type="formation", target_id=OuterRef("pk"))
            .order_by().values("target_id").annotate(n=Count("id")).values("n")
        )
        qs = Formation.objects.select_related("teacher").annotate(
            lessons_count=Count("lessons", distinct=True),
            enrollments_count=Count("enrollments", distinct=True),
            open_reports=Coalesce(Subquery(open_reports, output_field=IntegerField()), 0),
        ).order_by("-created_at", "-id")
        params = self.request.query_params
        q = params.get("q", "").strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(teacher__email__icontains=q)
                           | Q(teacher__first_name__icontains=q) | Q(teacher__last_name__icontains=q))
        if params.get("published") in ("0", "1"):
            qs = qs.filter(is_published=params["published"] == "1")
        return qs

    def perform_destroy(self, instance):
        teacher, title = instance.teacher, instance.title
        instance.delete()
        notify(teacher, "Formation supprimée", f"Votre formation « {title} » a été supprimée par un administrateur.", "/dashboard", "warning")

    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        formation = self.get_object()
        formation.is_published = False
        formation.save(update_fields=["is_published"])
        reason = str(request.data.get("reason", "")).strip()[:500]
        notify(formation.teacher, "Formation dépubliée",
               f"« {formation.title} » a été dépubliée par un administrateur." + (f" Motif : {reason}" if reason else ""),
               f"/learning/formations/{formation.id}", "warning")
        return Response({"id": formation.id, "is_published": False})


# ------------------------------------------------------------------ reports
class ReportCreateView(generics.CreateAPIView):
    """Any signed-in user can flag a published formation or one of its quizzes."""

    serializer_class = ReportCreateSerializer

    def perform_create(self, serializer):
        report = serializer.save(reporter=self.request.user)
        admins = User.objects.filter(role="admin", is_active=True)
        notify_many(admins, "Nouveau signalement", f"« {report.target_title} » a été signalé ({report.get_reason_display().lower()}).", "/admin/content", "warning")


class AdminReportViewSet(AdminOnly, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = ReportSerializer

    def get_queryset(self):
        qs = Report.objects.select_related("reporter", "handled_by")
        if self.request.query_params.get("status") in dict(Report.STATUSES):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def resolve(self, request, pk=None):
        report = self.get_object()
        if report.status != "open":
            raise ValidationError("Ce signalement a déjà été traité.")
        data = ReportResolveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        new_status, act, note = data.validated_data["status"], data.validated_data["action"], data.validated_data["note"].strip()

        target = get_target(report.target_type, report.target_id)
        if act != "none":
            if target is None:
                raise ValidationError("Ce contenu n'existe plus.")
            if act == "unpublish" and report.target_type != "formation":
                raise ValidationError("Seule une formation peut être dépubliée ; supprimez le quiz à la place.")
            owner, link = target_owner(target), target_link(report, target)
            if act == "unpublish":
                target.is_published = False
                target.save(update_fields=["is_published"])
                verb = "dépublié"
            else:
                target.delete()
                verb, link = "supprimé", "/dashboard"
            notify(owner, f"Contenu {verb}", f"« {report.target_title} » a été {verb} par un administrateur suite à un signalement." + (f" Motif : {note}" if note else ""), link, "warning")
            # Other open reports on the same content are settled by the same decision.
            Report.objects.filter(status="open", target_type=report.target_type, target_id=report.target_id).exclude(pk=report.pk).update(
                status="resolved", handled_by=request.user, handled_at=timezone.now(), resolution_note=f"Contenu {verb} (signalement n°{report.pk}).")

        report.status, report.resolution_note = new_status, note
        report.handled_by, report.handled_at = request.user, timezone.now()
        report.save()
        outcome = "a été pris en compte" if new_status == "resolved" else "a été examiné et n'a pas donné lieu à une action"
        notify(report.reporter, "Votre signalement a été traité", f"Votre signalement sur « {report.target_title} » {outcome}. Merci de votre aide.", "", "info")
        return Response(ReportSerializer(report, context=self.get_serializer_context()).data)


# ------------------------------------------------------------------ statistics (BF52)
def _week_start(day):
    return day - timedelta(days=day.weekday())


def _aware(day):
    return timezone.make_aware(datetime.combine(day, time.min))


class AdminStatsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]
    WEEKS = 8
    DAYS = 14

    def get(self, request):
        today = timezone.localdate()

        by_role = {role: 0 for role, _ in User.ROLES}
        for row in User.objects.values("role").annotate(n=Count("id")):
            by_role[row["role"]] = row["n"]

        first_week = _week_start(today) - timedelta(weeks=self.WEEKS - 1)
        weeks = {first_week + timedelta(weeks=i): 0 for i in range(self.WEEKS)}
        for joined in User.objects.filter(date_joined__gte=_aware(first_week)).values_list("date_joined", flat=True):
            weeks[_week_start(timezone.localtime(joined).date())] += 1

        first_day = today - timedelta(days=self.DAYS - 1)
        days = {first_day + timedelta(days=i): 0 for i in range(self.DAYS)}
        for created in QuizAttempt.objects.filter(created_at__gte=_aware(first_day)).values_list("created_at", flat=True):
            days[timezone.localtime(created).date()] += 1

        totals = QuizAttempt.objects.aggregate(score=Sum("score"), total=Sum("total"), n=Count("id"))
        success = round(100 * totals["score"] / totals["total"]) if totals["total"] else None

        top = Formation.objects.select_related("teacher").annotate(n=Count("enrollments")).filter(n__gt=0).order_by("-n", "title")[:5]
        return Response({
            "generated_at": timezone.now(),
            "users": {
                "total": sum(by_role.values()),
                "active": User.objects.filter(is_active=True).count(),
                "inactive": User.objects.filter(is_active=False).count(),
                "by_role": by_role,
                "new_30d": User.objects.filter(date_joined__gte=timezone.now() - timedelta(days=30)).count(),
                "signups_by_week": [{"start": d.isoformat(), "count": n} for d, n in weeks.items()],
            },
            "learning": {
                "formations_total": Formation.objects.count(),
                "formations_published": Formation.objects.filter(is_published=True).count(),
                "enrollments": Enrollment.objects.count(),
                "courses": Course.objects.count(),
                "quizzes": Quiz.objects.count(),
                "ai_quizzes": Quiz.objects.filter(ai_generated=True).count(),
                "attempts": totals["n"],
                "success_rate": success,
                "attempts_by_day": [{"date": d.isoformat(), "count": n} for d, n in days.items()],
            },
            "moderation": {"open_reports": Report.objects.filter(status="open").count()},
            "top_formations": [
                {"id": f.id, "title": f.title, "teacher_name": display_name(f.teacher), "enrollments": f.n} for f in top
            ],
        })


# ------------------------------------------------------------------ announcements
class AnnouncementView(APIView):
    """An administrator sends a notification to everybody, or to one role."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request):
        data = AnnouncementSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        d = data.validated_data
        users = User.objects.filter(is_active=True)
        if d["audience"] != "all":
            users = users.filter(role=d["audience"])
        sent = notify_many(users, d["title"], d["message"], d["link"], "announcement")
        return Response({"sent": sent}, status=status.HTTP_201_CREATED)
