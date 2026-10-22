from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from learning.models import Formation

from .models import Report
from .targets import get_target, target_owner

User = get_user_model()


def display_name(user):
    return user.get_full_name() or user.email


# ------------------------------------------------------------------ users
class AdminUserSerializer(serializers.ModelSerializer):
    formations_count = serializers.SerializerMethodField()
    enrollments_count = serializers.SerializerMethodField()
    attempts_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "email", "first_name", "last_name", "phone", "role", "is_active", "date_joined", "last_login",
            "formations_count", "enrollments_count", "attempts_count",
        )
        read_only_fields = ("id", "email", "date_joined", "last_login")

    # The list view annotates these counts (one query); a freshly created/updated user falls back to a count.
    def _count(self, obj, name, related):
        value = getattr(obj, name, None)
        return value if value is not None else getattr(obj, related).count()

    def get_formations_count(self, obj):
        return self._count(obj, "formations_count", "formations")

    def get_enrollments_count(self, obj):
        return self._count(obj, "enrollments_count", "enrollments")

    def get_attempts_count(self, obj):
        return self._count(obj, "attempts_count", "attempts")

    def validate(self, attrs):
        user, me = self.instance, self.context["request"].user
        changes_role = "role" in attrs and attrs["role"] != user.role
        deactivates = attrs.get("is_active") is False and user.is_active
        if user.pk == me.pk and (changes_role or deactivates):
            raise serializers.ValidationError("Vous ne pouvez pas modifier votre propre rôle ni désactiver votre propre compte.")
        if user.role == "admin" and user.is_active and (changes_role or deactivates):
            if not User.objects.filter(role="admin", is_active=True).exclude(pk=user.pk).exists():
                raise serializers.ValidationError("Il doit rester au moins un administrateur actif.")
        return attrs


class AdminUserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ("id", "email", "password", "first_name", "last_name", "role")
        read_only_fields = ("id",)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Un compte existe déjà avec cette adresse e-mail.")
        return value

    def validate(self, attrs):
        validate_password(attrs["password"], User(email=attrs.get("email")))
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


# ------------------------------------------------------------------ formations
class AdminFormationSerializer(serializers.ModelSerializer):
    teacher_name = serializers.SerializerMethodField()
    teacher_email = serializers.CharField(source="teacher.email", read_only=True)
    lessons_count = serializers.IntegerField(read_only=True)
    enrollments_count = serializers.IntegerField(read_only=True)
    open_reports = serializers.IntegerField(read_only=True)

    class Meta:
        model = Formation
        fields = (
            "id", "title", "category", "level", "is_published", "created_at",
            "teacher_name", "teacher_email", "lessons_count", "enrollments_count", "open_reports",
        )

    def get_teacher_name(self, obj):
        return display_name(obj.teacher)


# ------------------------------------------------------------------ reports
class ReportCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = ("id", "target_type", "target_id", "reason", "details", "status", "created_at")
        read_only_fields = ("id", "status", "created_at")
        extra_kwargs = {"details": {"max_length": 1000}}

    def validate(self, attrs):
        user = self.context["request"].user
        target = get_target(attrs["target_type"], attrs["target_id"])
        formation = target if isinstance(target, Formation) else getattr(target, "formation", None)
        if target is None or formation is None or not formation.is_published:
            raise serializers.ValidationError("Ce contenu est introuvable.")
        if target_owner(target).pk == user.pk:
            raise serializers.ValidationError("Vous ne pouvez pas signaler votre propre contenu.")
        if Report.objects.filter(reporter=user, status="open", target_type=attrs["target_type"], target_id=attrs["target_id"]).exists():
            raise serializers.ValidationError("Vous avez déjà signalé ce contenu, il est en cours d'examen.")
        attrs["target_title"] = target.title[:200]
        return attrs


class ReportSerializer(serializers.ModelSerializer):
    reporter_name = serializers.SerializerMethodField()
    reporter_email = serializers.CharField(source="reporter.email", read_only=True)
    reason_label = serializers.CharField(source="get_reason_display", read_only=True)
    handled_by_name = serializers.SerializerMethodField()
    target_exists = serializers.SerializerMethodField()
    target_published = serializers.SerializerMethodField()
    owner_name = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = (
            "id", "target_type", "target_id", "target_title", "reason", "reason_label", "details", "status",
            "resolution_note", "created_at", "handled_at", "handled_by_name", "reporter_name", "reporter_email",
            "target_exists", "target_published", "owner_name",
        )

    def _target(self, obj):
        cache = self.context.setdefault("_targets", {})
        key = (obj.target_type, obj.target_id)
        if key not in cache:
            cache[key] = get_target(*key)
        return cache[key]

    def get_reporter_name(self, obj):
        return display_name(obj.reporter)

    def get_handled_by_name(self, obj):
        return display_name(obj.handled_by) if obj.handled_by else ""

    def get_target_exists(self, obj):
        return self._target(obj) is not None

    def get_target_published(self, obj):
        target = self._target(obj)
        if target is None:
            return None
        formation = target if isinstance(target, Formation) else target.formation
        return bool(formation and formation.is_published)

    def get_owner_name(self, obj):
        target = self._target(obj)
        return display_name(target_owner(target)) if target else ""


class ReportResolveSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["resolved", "dismissed"])
    action = serializers.ChoiceField(choices=["none", "unpublish", "delete"], default="none")
    note = serializers.CharField(max_length=500, allow_blank=True, required=False, default="")

    def validate(self, attrs):
        if attrs["status"] == "dismissed" and attrs["action"] != "none":
            raise serializers.ValidationError("Un signalement rejeté ne peut pas entraîner d'action sur le contenu.")
        return attrs


class AnnouncementSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=150)
    message = serializers.CharField(max_length=1000, allow_blank=True, required=False, default="")
    audience = serializers.ChoiceField(choices=["all", "student", "teacher", "admin"], default="all")
    link = serializers.CharField(max_length=200, allow_blank=True, required=False, default="")
