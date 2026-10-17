import uuid
from pathlib import Path

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver

User = settings.AUTH_USER_MODEL
LEVELS = [("beginner", "Débutant"), ("intermediate", "Intermédiaire"), ("advanced", "Avancé")]


class Course(models.Model):
    """A course (matière) owned by a student. `content` is the text used to generate quizzes."""

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="courses")
    title = models.CharField(max_length=200)
    subject = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    content = models.TextField(blank=True)
    file = models.FileField(
        upload_to="courses/%Y/%m/", blank=True,
        validators=[FileExtensionValidator(["pdf", "docx", "txt", "md"])],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["subject", "title"]

    def __str__(self):
        return self.title


class Formation(models.Model):
    """A training published by a teacher."""

    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name="formations")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, blank=True)
    level = models.CharField(max_length=15, choices=LEVELS, default="beginner")
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Lesson(models.Model):
    formation = models.ForeignKey(Formation, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=200)
    content = models.TextField(blank=True)
    video_url = models.URLField(blank=True)
    resource_url = models.URLField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title


MATERIAL_KINDS = {
    "video": {".mp4", ".webm", ".mov", ".m4v", ".mkv", ".avi"},
    "audio": {".mp3", ".wav", ".m4a"},
    "pdf": {".pdf"},
    "document": {".doc", ".docx", ".odt", ".txt", ".md"},
    "slides": {".ppt", ".pptx", ".odp"},
    "sheet": {".xls", ".xlsx", ".csv"},
    "image": {".png", ".jpg", ".jpeg", ".gif", ".webp"},
    "archive": {".zip"},
}
ALLOWED_MATERIAL_EXT = set().union(*MATERIAL_KINDS.values())


def material_kind(filename):
    ext = Path(filename).suffix.lower()
    return next((kind for kind, exts in MATERIAL_KINDS.items() if ext in exts), "other")


def material_path(instance, filename):
    # Random name: the URL cannot be guessed. The original name is kept in `name`.
    return f"materials/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class LessonMaterial(models.Model):
    """A file attached to a lesson: course PDF, Word/PowerPoint document, video..."""

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="materials")
    file = models.FileField(upload_to=material_path)
    name = models.CharField(max_length=255)
    size = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    @property
    def kind(self):
        return material_kind(self.name)

    def __str__(self):
        return self.name


@receiver(post_delete, sender=LessonMaterial)
def delete_material_file(sender, instance, **kwargs):
    instance.file.delete(save=False)


class Enrollment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="enrollments")
    formation = models.ForeignKey(Formation, on_delete=models.CASCADE, related_name="enrollments")
    completed_lessons = models.ManyToManyField(Lesson, blank=True, related_name="completed_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "formation")


class Quiz(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="quizzes")
    course = models.ForeignKey(Course, null=True, blank=True, on_delete=models.SET_NULL, related_name="quizzes")
    formation = models.ForeignKey(Formation, null=True, blank=True, on_delete=models.CASCADE, related_name="quizzes")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    ai_generated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "quizzes"

    def __str__(self):
        return self.title


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    choices = models.JSONField(default=list)
    correct_index = models.PositiveSmallIntegerField()
    explanation = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]


class QuizAttempt(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="attempts")
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    score = models.PositiveSmallIntegerField()
    total = models.PositiveSmallIntegerField()
    answers = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
