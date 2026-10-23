from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("", views.EmailMessageViewSet, basename="email")

urlpatterns = [
    path("", include(router.urls)),
]
