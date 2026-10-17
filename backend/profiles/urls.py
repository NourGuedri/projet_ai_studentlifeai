from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("educations", views.EducationViewSet, basename="education")
router.register("skills", views.SkillViewSet, basename="skill")
router.register("projects", views.ProjectViewSet, basename="project")
router.register("experiences", views.ExperienceViewSet, basename="experience")
router.register("certifications", views.CertificationViewSet, basename="certification")
router.register("languages", views.LanguageViewSet, basename="language")

urlpatterns = [
    path("", views.ProfileView.as_view()),
    path("cv/", views.CVUploadView.as_view()),
    path("cv/apply/", views.CVApplyView.as_view()),
    path("", include(router.urls)),
]
