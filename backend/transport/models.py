from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL

PREDICTABLE_MODES = [("bus", "Bus"), ("metro", "Métro"), ("tramway", "Tramway")]
ALL_MODES = PREDICTABLE_MODES + [("voiture", "Voiture"), ("marche", "À pied")]


class Trip(models.Model):
    """Trajet renseigné par un étudiant : trajet, heure de départ, moyen de transport (US 35)."""

    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="trips")
    departure = models.CharField(max_length=120)
    destination = models.CharField(max_length=120)
    departure_time = models.DateTimeField()
    mode = models.CharField(max_length=10, choices=ALL_MODES)
    line = models.CharField(max_length=30, blank=True)               # ex. "Ligne 4", "TGM"
    seats_available = models.PositiveSmallIntegerField(default=0)    # voiture : places proposées (exigence 7.11)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["departure_time"]
        verbose_name = "trajet"

    def __str__(self):
        return f"{self.departure} → {self.destination} ({self.get_mode_display()})"


class Incident(models.Model):
    """Incident de transport signalé (US 36). Le modèle ML estime le retard au moment du signalement."""

    reporter = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="transport_incidents")
    mode = models.CharField(max_length=10, choices=PREDICTABLE_MODES)
    line = models.CharField(max_length=30, blank=True)
    incident_type = models.CharField(max_length=40)
    description = models.TextField(blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    # Résultat des modèles ML (vide si la prédiction est indisponible)
    estimated_delay_min = models.PositiveSmallIntegerField(null=True, blank=True)
    long_delay_probability = models.FloatField(null=True, blank=True)
    is_long_delay = models.BooleanField(default=False)
    notified_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        verbose_name = "incident de transport"

    def __str__(self):
        return f"{self.incident_type} — {self.get_mode_display()} ({self.occurred_at:%d/%m %H:%M})" 