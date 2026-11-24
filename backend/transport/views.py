from datetime import timedelta

from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from . import predictor, services
from .incidents import choices_for, label
from .models import ALL_MODES, PREDICTABLE_MODES, Incident, Trip
from .serializers import CarpoolSerializer, IncidentSerializer, PredictSerializer, TripSerializer

RECENT_DAYS = 7


class TripViewSet(viewsets.ModelViewSet):
    """Trajets de l'étudiant connecté (US 35). ?upcoming=1 : seulement ceux à venir."""

    serializer_class = TripSerializer

    def get_queryset(self):
        qs = Trip.objects.filter(student=self.request.user)
        if self.request.query_params.get("upcoming"):
            qs = qs.filter(departure_time__gte=timezone.now())
        return qs

    def perform_create(self, serializer):
        serializer.save(student=self.request.user)

    @action(detail=False, methods=["get"])
    def carpool(self, request):
        """Places de voiture proposées par les autres étudiants (exigence 7.11)."""
        qs = (Trip.objects.filter(mode="voiture", seats_available__gt=0, departure_time__gte=timezone.now())
              .exclude(student=request.user).select_related("student"))
        return Response(CarpoolSerializer(qs, many=True).data)


class IncidentViewSet(mixins.CreateModelMixin, mixins.ListModelMixin,
                      mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Incidents signalés ces 7 derniers jours (US 36). À la création, le retard est estimé par les modèles ML."""

    serializer_class = IncidentSerializer

    def get_queryset(self):
        since = timezone.now() - timedelta(days=RECENT_DAYS)
        return Incident.objects.filter(occurred_at__gte=since)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        incident = serializer.save(reporter=request.user)
        error = services.apply_prediction(incident)
        data = self.get_serializer(incident).data
        data["prediction_error"] = error
        return Response(data, status=status.HTTP_201_CREATED)


class PredictView(APIView):
    """Estime le retard d'un incident sans rien enregistrer."""

    def post(self, request):
        ser = PredictSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        when = timezone.localtime(data.get("when") or timezone.now())
        try:
            result = predictor.estimate(data["mode"], data["incident_type"], when)
        except predictor.PredictorUnavailable as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        result["incident_label"] = label(data["incident_type"])
        return Response(result)


class OptionsView(APIView):
    """Listes de choix pour les formulaires + fiche des modèles ML."""

    def get(self, request):
        return Response({
            "modes": [{"value": v, "label": l} for v, l in ALL_MODES],
            "predictable_modes": [v for v, _ in PREDICTABLE_MODES],
            "incidents": {v: [{"value": c, "label": l} for c, l in choices_for(v)] for v, _ in PREDICTABLE_MODES},
            "alert_window_hours": services.window_hours(),
            "model": predictor.model_card(),
        })