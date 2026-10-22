from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("admin/users", views.AdminUserViewSet, basename="admin-user")
router.register("admin/formations", views.AdminFormationViewSet, basename="admin-formation")
router.register("admin/reports", views.AdminReportViewSet, basename="admin-report")

urlpatterns = [
    path("admin/stats/", views.AdminStatsView.as_view()),
    path("admin/announcements/", views.AnnouncementView.as_view()),
    path("reports/", views.ReportCreateView.as_view()),
    path("", include(router.urls)),
]
