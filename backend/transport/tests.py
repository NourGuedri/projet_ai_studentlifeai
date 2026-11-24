import importlib.util
from datetime import datetime, timedelta
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from notifications.models import Notification

from . import predictor
from .models import Incident, Trip

ML_INSTALLED = all(importlib.util.find_spec(m) for m in ("pandas", "sklearn", "xgboost", "imblearn"))

LONG = {"mode": "bus", "incident": "DIVERSION", "estimated_delay_min": 30,
        "long_delay_probability": 0.69, "is_long_delay": True, "threshold": 0.29}
SHORT = {**LONG, "estimated_delay_min": 5, "long_delay_probability": 0.05, "is_long_delay": False}


def alerts():
    """Notifications de transport (les comptes reçoivent aussi une notification de bienvenue)."""
    return Notification.objects.filter(link="/transport")


def in_hours(h):
    return timezone.now() + timedelta(hours=h)


class TransportApiTests(APITestCase):
    def setUp(self):
        users = get_user_model().objects
        self.student = users.create_user(email="etudiant@example.com", password="password123",
                                         first_name="Ayoub", last_name="D")
        self.other = users.create_user(email="autre@example.com", password="password123",
                                       first_name="Nour", last_name="G")
        self.client.force_authenticate(self.student)

    def trip(self, user, mode="bus", hours=1, **extra):
        return Trip.objects.create(student=user, departure="Ariana", destination="TEK-UP",
                                   departure_time=in_hours(hours), mode=mode, **extra)

    # ------------------------------------------------------------ US 35 : trajets
    def test_create_trip(self):
        r = self.client.post("/api/transport/trips/", {
            "departure": "Ariana", "destination": "TEK-UP", "departure_time": in_hours(2).isoformat(),
            "mode": "metro", "line": "Ligne 4"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(Trip.objects.get().student, self.student)
        self.assertEqual(r.data["mode_label"], "Métro")

    def test_departure_in_the_past_is_refused(self):
        r = self.client.post("/api/transport/trips/", {
            "departure": "A", "destination": "B", "departure_time": in_hours(-1).isoformat(),
            "mode": "bus"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_only_cars_offer_seats(self):
        r = self.client.post("/api/transport/trips/", {
            "departure": "A", "destination": "B", "departure_time": in_hours(1).isoformat(),
            "mode": "bus", "seats_available": 3}, format="json")
        self.assertEqual(r.data["seats_available"], 0)

    def test_student_only_sees_own_trips(self):
        self.trip(self.student)
        self.trip(self.other)
        r = self.client.get("/api/transport/trips/")
        self.assertEqual(len(r.data), 1)

    def test_carpool_lists_other_students_cars_with_seats(self):
        self.trip(self.other, mode="voiture", seats_available=2)
        self.trip(self.other, mode="voiture", seats_available=0)
        self.trip(self.other, mode="voiture", hours=-2, seats_available=2)
        self.trip(self.student, mode="voiture", seats_available=3)
        r = self.client.get("/api/transport/trips/carpool/")
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]["driver"], "Nour G")
        self.assertNotIn("email", r.data[0])

    # ------------------------------------------------------------ US 36 : incidents et notifications
    def report(self, **extra):
        payload = {"mode": "bus", "incident_type": "DIVERSION", **extra}
        return self.client.post("/api/transport/incidents/", payload, format="json")

    @patch("transport.predictor.estimate", return_value=LONG)
    def test_long_delay_notifies_affected_travellers(self, _):
        self.trip(self.other, mode="bus", hours=1)                 # concerné
        self.trip(self.other, mode="bus", hours=2)                 # même étudiant : une seule notification
        third = get_user_model().objects.create_user(email="c@example.com", password="x")
        self.trip(third, mode="metro", hours=1)                    # autre moyen de transport
        self.trip(third, mode="bus", hours=10)                     # trop tard
        self.trip(self.student, mode="bus", hours=1)               # celui qui signale
        r = self.report()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data["is_long_delay"])
        self.assertEqual(r.data["estimated_delay_min"], 30)
        self.assertEqual(r.data["notified_count"], 1)
        note = alerts().get()
        self.assertEqual(note.user, self.other)
        self.assertEqual(note.kind, "warning")
        self.assertEqual(note.link, "/transport")
        self.assertIn("30 min", note.message)

    @patch("transport.predictor.estimate", return_value=LONG)
    def test_line_must_match_when_given(self, _):
        self.trip(self.other, mode="bus", line="32")
        self.trip(self.other, mode="bus", line="")
        third = get_user_model().objects.create_user(email="c@example.com", password="x")
        self.trip(third, mode="bus", line="45")
        r = self.report(line="32")
        self.assertEqual(r.data["notified_count"], 1)
        self.assertFalse(alerts().filter(user=third).exists())

    @patch("transport.predictor.estimate", return_value=SHORT)
    def test_short_delay_sends_no_notification(self, _):
        self.trip(self.other, mode="bus")
        r = self.report()
        self.assertFalse(r.data["is_long_delay"])
        self.assertEqual(alerts().count(), 0)

    @patch("transport.predictor.estimate", side_effect=predictor.PredictorUnavailable("indisponible"))
    def test_incident_is_saved_even_without_model(self, _):
        self.trip(self.other, mode="bus")
        r = self.report()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["prediction_error"], "indisponible")
        self.assertIsNone(Incident.objects.get().estimated_delay_min)
        self.assertEqual(alerts().count(), 0)

    def test_unknown_incident_type_is_refused(self):
        r = self.report(mode="metro", incident_type="DIVERSION")   # pas un code métro
        self.assertEqual(r.status_code, 400)

    def test_future_incident_is_refused(self):
        r = self.report(occurred_at=in_hours(2).isoformat())
        self.assertEqual(r.status_code, 400)

    @patch("transport.predictor.estimate", side_effect=predictor.PredictorUnavailable("indisponible"))
    def test_predict_returns_503_when_unavailable(self, _):
        r = self.client.post("/api/transport/predict/", {"mode": "bus", "incident_type": "MECHANICAL"}, format="json")
        self.assertEqual(r.status_code, 503)

    def test_options(self):
        r = self.client.get("/api/transport/options/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("MUIS", [i["value"] for i in r.data["incidents"]["metro"]])
        self.assertIn("DIVERSION", [i["value"] for i in r.data["incidents"]["bus"]])

    def test_authentication_required(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/transport/trips/").status_code, 401)


@skipUnless(ML_INSTALLED, "bibliothèques ML non installées")
class RealModelTests(SimpleTestCase):
    """Vérifie les vrais modèles entraînés (transport/ml/models/)."""

    def test_diversion_on_bus_is_a_long_delay(self):
        result = predictor.estimate("bus", "DIVERSION", datetime(2026, 11, 23, 8, 0))
        self.assertTrue(result["is_long_delay"])
        self.assertGreater(result["estimated_delay_min"], 15)

    def test_delay_is_never_negative(self):
        result = predictor.estimate("metro", "MUIS", datetime(2026, 7, 12, 14, 0))
        self.assertGreaterEqual(result["estimated_delay_min"], 0)

    def test_unknown_incident_becomes_autre(self):
        self.assertEqual(predictor.estimate("tramway", "???", datetime(2026, 3, 6, 17))["incident"], "AUTRE")

    def test_model_card(self):
        card = predictor.model_card()
        self.assertEqual(card["long_delay_minutes"], 15)
        self.assertGreater(card["classification"]["recall"], 0.5)