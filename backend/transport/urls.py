from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("trips", views.TripViewSet, basename="trip")
router.register("incidents", views.IncidentViewSet, basename="incident")

urlpatterns = [
    path("", include(router.urls)),
    path("predict/", views.PredictView.as_view(), name="transport-predict"),
    path("options/", views.OptionsView.as_view(), name="transport-options"),
]