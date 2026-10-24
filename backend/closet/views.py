from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from . import classifier, outfit
from .ml import labels
from .models import ClothingItem
from .serializers import AnalyzeSerializer, ClothingItemSerializer
from .weather import WeatherError, get_weather

DEFAULT_CITY = "Tunis"


class ClothingItemViewSet(viewsets.ModelViewSet):
    """Garde-robe de l'étudiant connecté. L'IA propose, l'étudiant valide et peut corriger."""

    serializer_class = ClothingItemSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        qs = ClothingItem.objects.filter(owner=self.request.user)
        category = self.request.query_params.get("category")
        return qs.filter(category=category) if category else qs

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_destroy(self, instance):
        instance.image.delete(save=False)
        instance.delete()

    @action(detail=False, methods=["get"])
    def options(self, request):
        """Listes de choix pour les formulaires (types par catégorie, couleurs, styles)."""
        return Response({
            "categories": [{"value": v, "label": l} for v, l in labels.CATEGORIES],
            "types": labels.TYPES_BY_CATEGORY,
            "colors": labels.COLORS,
            "styles": labels.STYLES,
        })

    @action(detail=False, methods=["post"])
    def analyze(self, request):
        """Détecte type / couleur / style d'une photo SANS rien enregistrer (US 37)."""
        ser = AnalyzeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            result = classifier.analyze(ser.validated_data["image"])
        except classifier.ClassifierUnavailable as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(result)

    @action(detail=False, methods=["get"])
    def outfit(self, request):
        """Tenue du jour selon la météo (US 38). ?city=Tunis&style=Casual&seed=42"""
        profile = getattr(request.user, "profile", None)
        city = (request.query_params.get("city") or getattr(profile, "city", "") or DEFAULT_CITY).strip()
        style = request.query_params.get("style") or None
        if style and style not in labels.STYLES:
            return Response({"detail": "Style inconnu."}, status=400)
        try:
            weather = get_weather(city)
        except WeatherError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        result = outfit.recommend(list(self.get_queryset()), weather, style, request.query_params.get("seed"))
        return Response({
            "weather": weather,
            "items": self.get_serializer(result["items"], many=True).data,
            "advice": result["advice"],
            "missing": result["missing"],
            "generated": True,   # suggestion automatique, clairement identifiée (exigence 8.5)
        })
