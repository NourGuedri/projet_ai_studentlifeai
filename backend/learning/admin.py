from django.contrib import admin

from .models import Course, Enrollment, Formation, Lesson, LessonMaterial, Question, Quiz, QuizAttempt


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "course", "formation", "ai_generated")
    inlines = [QuestionInline]


for model in (Course, Formation, Lesson, LessonMaterial, Enrollment, QuizAttempt):
    admin.site.register(model)
