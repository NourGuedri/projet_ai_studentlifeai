from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .incidents import choices_for, label
from .models import PREDICTABLE_MODES, Incident, Trip

MAX_SEATS = 8


class TripSerializer(serializers.ModelSerializer):
    mode_label = serializers.CharField(source="get_mode_display", read_only=True)

    class Meta:
        model = Trip
        fields = ["id", "departure", "destination", "departure_time", "mode", "mode_label",
                  "line", "seats_available", "created_at"]
        read_only_fields = ["created_at"]

    def validate_departure_time(self, value):
        if self.instance is None and value < timezone.now():
            raise serializers.ValidationError("L'heure de départ est déjà passée.")
        return value

    def validate(self, attrs):
        mode = attrs.get("mode", getattr(self.instance, "mode", None))
        seats = attrs.get("seats_available", getattr(self.instance, "seats_available", 0))
        if mode != "voiture":
            attrs["seats_available"] = 0          # seules les voitures proposent des places
        elif seats > MAX_SEATS:
            raise serializers.ValidationError({"seats_available": f"Maximum {MAX_SEATS} places."})
        return attrs


class CarpoolSerializer(serializers.ModelSerializer):
    """Places de voiture proposées par d'autres étudiants (exigence 7.11)."""

    driver = serializers.SerializerMethodField()

    class Meta:
        model = Trip
        fields = ["id", "departure", "destination", "departure_time", "line", "seats_available", "driver"]

    def get_driver(self, trip):
        return trip.student.get_full_name() or "Étudiant"


class IncidentSerializer(serializers.ModelSerializer):
    mode_label = serializers.CharField(source="get_mode_display", read_only=True)
    incident_label = serializers.SerializerMethodField()

    class Meta:
        model = Incident
        fields = ["id", "mode", "mode_label", "line", "incident_type", "incident_label", "description",
                  "occurred_at", "estimated_delay_min", "long_delay_probability", "is_long_delay",
                  "notified_count", "created_at"]
        read_only_fields = ["estimated_delay_min", "long_delay_probability", "is_long_delay",
                            "notified_count", "created_at"]

    def get_incident_label(self, incident):
        return label(incident.incident_type)

    def validate_occurred_at(self, value):
        if value > timezone.now() + timedelta(minutes=5):
            raise serializers.ValidationError("Un incident ne peut pas être dans le futur.")
        return value

    def validate(self, attrs):
        allowed = {value for value, _ in choices_for(attrs["mode"])}
        if attrs["incident_type"] not in allowed:
            raise serializers.ValidationError({"incident_type": "Type d'incident inconnu pour ce moyen de transport."})
        return attrs


class PredictSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=PREDICTABLE_MODES)
    incident_type = serializers.CharField(max_length=40)
    when = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        allowed = {value for value, _ in choices_for(attrs["mode"])}
        if attrs["incident_type"] not in allowed:
            raise serializers.ValidationError({"incident_type": "Type d'incident inconnu pour ce moyen de transport."})
        return attrs