from django.db.models import Q
from django.shortcuts import get_object_or_404
from pathlib import Path
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common import ai
from common.permissions import IsTeacher, is_teacher
from common.text import TextExtractionError, extract_text, extract_text_from_bytes

from . import services
from .models import Course, Enrollment, Formation, Lesson, LessonMaterial, Quiz, QuizAttempt
from .serializers import (
    AttemptSerializer,
    CourseSerializer,
    FormationSerializer,
    GenerateQuizSerializer,
    LessonMaterialSerializer,
    LessonSerializer,
    QuizSerializer,
)

QUIZ_TEXT_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


# ------------------------------------------------------------------ courses (US 22)
class CourseViewSet(viewsets.ModelViewSet):
    serializer_class = CourseSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        qs = Course.objects.filter(owner=self.request.user)
        subject = self.request.query_params.get("subject")
        return qs.filter(subject=subject) if subject else qs

    @action(detail=False, methods=["get"])
    def subjects(self, request):
        subjects = Course.objects.filter(owner=request.user).exclude(subject="").order_by("subject")
        return Response(list(subjects.values_list("subject", flat=True).distinct()))

    def _extract_from_file(self, serializer, instance):
        if "file" in serializer.validated_data and instance.file and not serializer.validated_data.get("content"):
            try:
                text = extract_text(instance.file.path)
            except Exception:
                return
            if text.strip():
                instance.content = text
                instance.save(update_fields=["content"])

    def perform_create(self, serializer):
        self._extract_from_file(serializer, serializer.save(owner=self.request.user))

    def perform_update(self, serializer):
        self._extract_from_file(serializer, serializer.save())


# ------------------------------------------------------------------ quizzes (US 23, 24, 27)
class QuizViewSet(viewsets.ModelViewSet):
    serializer_class = QuizSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAuthenticated(), IsTeacher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = Quiz.objects.select_related("course", "formation", "owner").prefetch_related("questions")
        if self.action in ("update", "partial_update", "destroy"):
            return qs.filter(owner=user)
        qs = qs.filter(Q(owner=user) | Q(formation__is_published=True, formation__enrollments__user=user)).distinct()
        params = self.request.query_params
        if params.get("course", "").isdigit():
            qs = qs.filter(course_id=params["course"])
        if params.get("formation", "").isdigit():
            qs = qs.filter(formation_id=params["formation"])
        return qs

    @staticmethod
    def _read_text_file(file_field):
        if not file_field or Path(file_field.name).suffix.lower() not in QUIZ_TEXT_EXTENSIONS:
            return ""
        try:
            file_field.open("rb")
            try:
                content = file_field.read()
            finally:
                file_field.close()
        except OSError as exc:
            raise TextExtractionError(
                "Impossible d'ouvrir un document du cours. Vérifiez que le fichier est toujours disponible."
            ) from exc
        return extract_text_from_bytes(content, Path(file_field.name).suffix)

    @action(detail=False, methods=["post"])
    def generate(self, request):
        """Return AI-generated questions without saving them."""
        serializer = GenerateQuizSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        sources = [data.get("text", "").strip()]
        try:
            if data.get("course"):
                course = get_object_or_404(Course, pk=data["course"], owner=request.user)
                sources.extend([course.content.strip(), self._read_text_file(course.file).strip()])
            if data.get("formation"):
                if not is_teacher(request.user):
                    return Response({"detail": "Seul le formateur peut générer un quiz à partir de ses formations."}, status=403)
                formation = get_object_or_404(
                    Formation.objects.prefetch_related("lessons__materials"),
                    pk=data["formation"],
                    teacher=request.user,
                )
                for lesson in formation.lessons.all():
                    sources.append(lesson.content.strip())
                    sources.extend(self._read_text_file(material.file).strip() for material in lesson.materials.all())
        except TextExtractionError as exc:
            return Response({"detail": str(exc)}, status=400)

        unique_sources = list(dict.fromkeys(source for source in sources if source))
        text = "\n\n".join(unique_sources)
        if len(text) < 50:
            return Response({
                "detail": "Aucun texte exploitable n'a été trouvé. Fournissez au moins 50 caractères de texte "
                "ou un document PDF, DOCX, TXT ou MD lisible.",
            }, status=400)
        try:
            questions = services.generate_questions(text, data["num_questions"], data["difficulty"])
        except ai.AINotConfigured as exc:
            return Response({"detail": f"{exc} Vous pouvez saisir les questions manuellement."}, status=503)
        except ai.AIError as exc:
            return Response({"detail": str(exc)}, status=502)
        return Response({"questions": questions})

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        if is_teacher(request.user):
            return Response({"detail": "Les formateurs peuvent consulter et gérer les quiz, mais pas les passer."}, status=403)
        quiz = self.get_object()
        answers = request.data.get("answers") or {}
        results, score, kept = [], 0, {}
        for question in quiz.questions.all():
            try:
                chosen = int(answers.get(str(question.id)))
            except (TypeError, ValueError):
                chosen = None
            correct = chosen == question.correct_index
            score += int(correct)
            if chosen is not None:
                kept[str(question.id)] = chosen
            results.append({
                "question_id": question.id, "chosen": chosen, "correct_index": question.correct_index,
                "correct": correct, "explanation": question.explanation,
            })
        attempt = QuizAttempt.objects.create(user=request.user, quiz=quiz, score=score, total=len(results), answers=kept)
        percent = round(100 * score / len(results)) if results else 0
        return Response({"attempt_id": attempt.id, "score": score, "total": len(results), "percent": percent, "results": results})


# ------------------------------------------------------------------ results & recommendations (US 24, 25)
class AttemptViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AttemptSerializer

    def get_queryset(self):
        qs = QuizAttempt.objects.filter(user=self.request.user).select_related("quiz__course")
        quiz = self.request.query_params.get("quiz", "")
        return qs.filter(quiz_id=quiz) if quiz.isdigit() else qs


def _missed_questions(attempt):
    missed = []
    for question in attempt.quiz.questions.all():
        chosen = attempt.answers.get(str(question.id))
        if chosen is None or int(chosen) != question.correct_index:
            missed.append(question.text)
    return missed[:3]


class RecommendationsView(APIView):
    """Courses to revise, ranked by the student's recent average (last 3 attempts per course)."""

    def get(self, request):
        attempts = (
            QuizAttempt.objects.filter(user=request.user, quiz__course__isnull=False)
            .select_related("quiz__course")
            .order_by("-created_at")
        )
        by_course = {}
        for attempt in attempts:
            by_course.setdefault(attempt.quiz.course_id, []).append(attempt)

        recommendations = []
        for items in by_course.values():
            recent = items[:3]
            average = round(sum(100 * a.score / a.total for a in recent if a.total) / len(recent))
            course = items[0].quiz.course
            recommendations.append({
                "course_id": course.id, "course_title": course.title, "subject": course.subject,
                "average": average, "attempts": len(items),
                "level": "review" if average < 60 else "practice" if average < 80 else "mastered",
                "missed_questions": _missed_questions(items[0]),
            })
        recommendations.sort(key=lambda r: r["average"])
        return Response(recommendations)


# ------------------------------------------------------------------ formations (US 26)
class FormationViewSet(viewsets.ModelViewSet):
    serializer_class = FormationSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAuthenticated(), IsTeacher()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = Formation.objects.select_related("teacher").prefetch_related("lessons", "quizzes")
        if self.action in ("update", "partial_update", "destroy"):
            return qs.filter(teacher=user)
        if self.request.query_params.get("mine") and is_teacher(user):
            return qs.filter(teacher=user)
        return qs.filter(Q(is_published=True) | Q(teacher=user))

    def perform_create(self, serializer):
        serializer.save(teacher=self.request.user)

    @action(detail=True, methods=["post"])
    def enroll(self, request, pk=None):
        formation = self.get_object()
        if not formation.is_published:
            return Response({"detail": "Cette formation n'est pas encore publiée."}, status=400)
        Enrollment.objects.get_or_create(user=request.user, formation=formation)
        return Response(self.get_serializer(formation).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="toggle-lesson")
    def toggle_lesson(self, request, pk=None):
        formation = self.get_object()
        enrollment = get_object_or_404(Enrollment, user=request.user, formation=formation)
        lesson = get_object_or_404(Lesson, pk=request.data.get("lesson_id"), formation=formation)
        if enrollment.completed_lessons.filter(pk=lesson.pk).exists():
            enrollment.completed_lessons.remove(lesson)
        else:
            enrollment.completed_lessons.add(lesson)
        return Response(self.get_serializer(formation).data)


class LessonViewSet(viewsets.ModelViewSet):
    serializer_class = LessonSerializer
    permission_classes = [IsAuthenticated, IsTeacher]

    def get_queryset(self):
        qs = Lesson.objects.filter(formation__teacher=self.request.user).prefetch_related("materials")
        formation = self.request.query_params.get("formation", "")
        return qs.filter(formation_id=formation) if formation.isdigit() else qs


class LessonMaterialViewSet(mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Teachers attach files (PDF, Word, PowerPoint, video...) to their lessons."""

    serializer_class = LessonMaterialSerializer
    permission_classes = [IsAuthenticated, IsTeacher]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        return LessonMaterial.objects.filter(lesson__formation__teacher=self.request.user)
