from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("items", views.ClothingItemViewSet, basename="clothing-item")

urlpatterns = [
    path("", include(router.urls)),
]
