from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("courses", views.CourseViewSet, basename="course")
router.register("quizzes", views.QuizViewSet, basename="quiz")
router.register("attempts", views.AttemptViewSet, basename="attempt")
router.register("formations", views.FormationViewSet, basename="formation")
router.register("lessons", views.LessonViewSet, basename="lesson")
router.register("materials", views.LessonMaterialViewSet, basename="material")

urlpatterns = [
    path("recommendations/", views.RecommendationsView.as_view()),
    path("", include(router.urls)),
]
