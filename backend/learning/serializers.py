from pathlib import Path

from django.conf import settings
from rest_framework import serializers

from common.permissions import is_teacher

from .models import (
    ALLOWED_MATERIAL_EXT,
    Course,
    Enrollment,
    Formation,
    Lesson,
    LessonMaterial,
    Question,
    Quiz,
    QuizAttempt,
)

MAX_COURSE_FILE = 10 * 1024 * 1024


class CourseSerializer(serializers.ModelSerializer):
    quiz_count = serializers.IntegerField(source="quizzes.count", read_only=True)

    class Meta:
        model = Course
        fields = ("id", "title", "subject", "description", "content", "file", "quiz_count", "created_at")

    def validate_file(self, value):
        if value and value.size > MAX_COURSE_FILE:
            raise serializers.ValidationError("Fichier trop volumineux (10 Mo maximum).")
        return value


class QuestionSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)  # present when editing an existing question

    class Meta:
        model = Question
        fields = ("id", "text", "choices", "correct_index", "explanation")

    def validate_choices(self, value):
        choices = [str(c).strip() for c in value] if isinstance(value, list) else []
        if not 2 <= len(choices) <= 6 or not all(choices):
            raise serializers.ValidationError("Chaque question doit avoir entre 2 et 6 choix non vides.")
        return choices

    def validate(self, attrs):
        if not 0 <= attrs["correct_index"] < len(attrs["choices"]):
            raise serializers.ValidationError("La bonne réponse doit être l'un des choix.")
        return attrs


class QuizSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True)
    question_count = serializers.IntegerField(source="questions.count", read_only=True)
    is_owner = serializers.SerializerMethodField()
    course_title = serializers.CharField(source="course.title", read_only=True, default=None)
    formation_title = serializers.CharField(source="formation.title", read_only=True, default=None)
    my_last_percent = serializers.SerializerMethodField()

    class Meta:
        model = Quiz
        fields = (
            "id", "title", "description", "course", "course_title", "formation", "formation_title",
            "ai_generated", "questions", "question_count", "is_owner", "my_last_percent", "created_at",
        )

    def _user(self):
        return self.context["request"].user

    def get_is_owner(self, obj):
        return obj.owner_id == self._user().id

    def get_my_last_percent(self, obj):
        attempt = obj.attempts.filter(user=self._user()).first()
        return round(100 * attempt.score / attempt.total) if attempt and attempt.total else None

    def validate_questions(self, value):
        if not value:
            raise serializers.ValidationError("Ajoutez au moins une question.")
        return value

    def validate(self, attrs):
        user = self._user()
        course, formation = attrs.get("course"), attrs.get("formation")
        if course and course.owner_id != user.id:
            raise serializers.ValidationError({"course": "Ce cours ne vous appartient pas."})
        if formation and (formation.teacher_id != user.id or not is_teacher(user)):
            raise serializers.ValidationError({"formation": "Vous ne pouvez ajouter un quiz qu'à vos propres formations."})
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not is_teacher(self._user()) or instance.owner_id != self._user().id:
            for question in data["questions"]:
                question.pop("correct_index", None)
                question.pop("explanation", None)
        return data

    @staticmethod
    def _create_questions(quiz, questions, start=0):
        Question.objects.bulk_create(
            [Question(quiz=quiz, order=start + i, **{k: v for k, v in q.items() if k != "id"}) for i, q in enumerate(questions)]
        )

    def create(self, validated_data):
        questions = validated_data.pop("questions")
        quiz = Quiz.objects.create(owner=self._user(), **validated_data)
        self._create_questions(quiz, questions)
        return quiz

    def update(self, instance, validated_data):
        questions = validated_data.pop("questions", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        if questions is not None:
            # Keep existing questions (same id) so past attempts and recommendations stay consistent.
            existing = {q.id: q for q in instance.questions.all()}
            kept = set()
            for order, data in enumerate(questions):
                question = existing.get(data.get("id"))
                if question:
                    for key in ("text", "choices", "correct_index", "explanation"):
                        setattr(question, key, data[key] if key in data else getattr(question, key))
                    question.order = order
                    question.save()
                    kept.add(question.id)
                else:
                    Question.objects.create(quiz=instance, order=order, **{k: v for k, v in data.items() if k != "id"})
            instance.questions.filter(id__in=[i for i in existing if i not in kept]).delete()
        return instance


class GenerateQuizSerializer(serializers.Serializer):
    text = serializers.CharField(required=False, allow_blank=True)
    course = serializers.IntegerField(required=False)
    formation = serializers.IntegerField(required=False)
    num_questions = serializers.IntegerField(min_value=1, max_value=20, default=5)
    difficulty = serializers.ChoiceField(choices=["easy", "medium", "hard"], default="medium")


class AttemptSerializer(serializers.ModelSerializer):
    quiz_title = serializers.CharField(source="quiz.title", read_only=True)
    course_title = serializers.CharField(source="quiz.course.title", read_only=True, default=None)
    percent = serializers.SerializerMethodField()

    class Meta:
        model = QuizAttempt
        fields = ("id", "quiz", "quiz_title", "course_title", "score", "total", "percent", "created_at")

    def get_percent(self, obj):
        return round(100 * obj.score / obj.total) if obj.total else 0


class LessonMaterialSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True)
    kind = serializers.CharField(read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = LessonMaterial
        fields = ("id", "lesson", "file", "name", "kind", "size", "url", "created_at")
        read_only_fields = ("name", "size")

    def get_url(self, obj):
        request = self.context.get("request")
        return request.build_absolute_uri(obj.file.url) if request else obj.file.url

    def validate_lesson(self, value):
        if value.formation.teacher_id != self.context["request"].user.id:
            raise serializers.ValidationError("Cette leçon ne vous appartient pas.")
        return value

    def validate_file(self, value):
        if Path(value.name).suffix.lower() not in ALLOWED_MATERIAL_EXT:
            raise serializers.ValidationError(
                "Format non pris en charge. Acceptés : PDF, Word, PowerPoint, Excel, texte, images, audio, vidéo (MP4, WebM, MOV) et ZIP."
            )
        if value.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise serializers.ValidationError(f"Fichier trop volumineux ({settings.MAX_UPLOAD_MB} Mo maximum).")
        return value

    def create(self, validated_data):
        upload = validated_data["file"]
        return LessonMaterial.objects.create(
            lesson=validated_data["lesson"], file=upload, name=upload.name[:255], size=upload.size
        )


class LessonSerializer(serializers.ModelSerializer):
    materials = LessonMaterialSerializer(many=True, read_only=True)

    class Meta:
        model = Lesson
        fields = ("id", "formation", "title", "content", "video_url", "resource_url", "order", "materials")

    def validate_formation(self, value):
        if value.teacher_id != self.context["request"].user.id:
            raise serializers.ValidationError("Cette formation ne vous appartient pas.")
        return value


class FormationSerializer(serializers.ModelSerializer):
    teacher_name = serializers.SerializerMethodField()
    is_owner = serializers.SerializerMethodField()
    enrolled = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    completed_lessons = serializers.SerializerMethodField()
    lessons = serializers.SerializerMethodField()
    lessons_count = serializers.IntegerField(source="lessons.count", read_only=True)
    quizzes = serializers.SerializerMethodField()
    enrollments_count = serializers.IntegerField(source="enrollments.count", read_only=True)

    class Meta:
        model = Formation
        fields = (
            "id", "title", "description", "category", "level", "is_published", "teacher_name", "is_owner",
            "enrolled", "progress", "completed_lessons", "lessons", "lessons_count", "quizzes",
            "enrollments_count", "created_at",
        )

    def _user(self):
        return self.context["request"].user

    def _enrollment(self, obj):
        return Enrollment.objects.filter(user=self._user(), formation=obj).first()

    def _has_access(self, obj):
        return obj.teacher_id == self._user().id or self._enrollment(obj) is not None

    def get_teacher_name(self, obj):
        return obj.teacher.get_full_name() or obj.teacher.email

    def get_is_owner(self, obj):
        return obj.teacher_id == self._user().id

    def get_enrolled(self, obj):
        return self._enrollment(obj) is not None

    def get_completed_lessons(self, obj):
        enrollment = self._enrollment(obj)
        return list(enrollment.completed_lessons.values_list("id", flat=True)) if enrollment else []

    def get_progress(self, obj):
        total = obj.lessons.count()
        enrollment = self._enrollment(obj)
        if not total or not enrollment:
            return 0
        return round(100 * enrollment.completed_lessons.count() / total)

    def get_lessons(self, obj):
        if self._has_access(obj):
            return LessonSerializer(obj.lessons.all(), many=True, context=self.context).data
        return [{"id": l.id, "title": l.title, "order": l.order} for l in obj.lessons.all()]

    def get_quizzes(self, obj):
        if not self._has_access(obj):
            return []
        return [{"id": q.id, "title": q.title, "question_count": q.questions.count()} for q in obj.quizzes.all()]
