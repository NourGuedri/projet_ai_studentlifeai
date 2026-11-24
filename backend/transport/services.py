"""US 36 : un incident est signalé -> les modèles ML estiment le retard
-> si le retard sera long, les étudiants qui voyagent bientôt sur ce moyen de transport sont prévenus."""

from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from notifications.services import notify

from . import predictor
from .incidents import label
from .models import Trip


def window_hours():
    return getattr(settings, "TRANSPORT_ALERT_WINDOW_HOURS", 3)


def apply_prediction(incident):
    """Remplit les champs ML de l'incident et prévient les voyageurs concernés.
    Retourne un message d'erreur si la prédiction est indisponible, sinon None."""
    try:
        result = predictor.estimate(incident.mode, incident.incident_type,
                                    timezone.localtime(incident.occurred_at))
    except predictor.PredictorUnavailable as exc:
        return str(exc)

    incident.estimated_delay_min = result["estimated_delay_min"]
    incident.long_delay_probability = result["long_delay_probability"]
    incident.is_long_delay = result["is_long_delay"]
    if incident.is_long_delay:
        incident.notified_count = notify_travellers(incident)
    incident.save(update_fields=["estimated_delay_min", "long_delay_probability",
                                 "is_long_delay", "notified_count"])
    return None


def affected_trips(incident):
    """Trajets sur le même moyen de transport, partis il y a moins de 30 min
    ou qui partent dans les prochaines heures. Si une ligne est précisée des deux côtés, elle doit correspondre."""
    start = incident.occurred_at - timedelta(minutes=30)
    end = incident.occurred_at + timedelta(hours=window_hours())
    trips = Trip.objects.filter(mode=incident.mode, departure_time__range=(start, end))
    if incident.line:
        trips = trips.filter(Q(line__iexact=incident.line) | Q(line=""))
    if incident.reporter_id:
        trips = trips.exclude(student_id=incident.reporter_id)
    return trips.select_related("student").order_by("departure_time")


def notify_travellers(incident):
    """Une notification par étudiant concerné. Retourne le nombre d'étudiants prévenus."""
    line = f" {incident.line}" if incident.line else ""
    proba = round((incident.long_delay_probability or 0) * 100)
    notified = set()
    for trip in affected_trips(incident):
        if trip.student_id in notified:
            continue
        notified.add(trip.student_id)
        when = timezone.localtime(trip.departure_time).strftime("%H:%M")
        notify(
            trip.student,
            title=f"Retard probable : {incident.get_mode_display()}{line}",
            message=(f"Incident signalé : {label(incident.incident_type)}. Retard estimé : environ "
                     f"{incident.estimated_delay_min} min (risque de retard de plus de 15 min : {proba} %). "
                     f"Votre trajet {trip.departure} → {trip.destination} de {when} est concerné : "
                     f"pensez à partir plus tôt ou à changer de moyen de transport."),
            link="/transport",
            kind="warning",
        )
    return len(notified)