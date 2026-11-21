import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from common import ai
from learning.models import Enrollment, Formation
from notifications.models import Notification

from config.asgi import application

from . import consumers, services
from .calls import make_ticket
from .models import Meeting, RecordingConsent, RecordingSession

INVITATION = "Invitation à une réunion"
TRANSCRIPT = (
    "Ali : on valide le sujet du projet de fin d'études. Sara : je rédige le cahier des charges "
    "pour vendredi 23 octobre. Ali : je prépare la maquette."
)
MEDIA_ROOT = tempfile.mkdtemp()
AUDIO_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_ROOT, MEETINGS_AUDIO_ROOT=AUDIO_ROOT)
class MeetingTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)
        shutil.rmtree(AUDIO_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(email="etudiant@example.com", password="password123")
        self.other = user_model.objects.create_user(email="autre@example.com", password="password123")
        self.meeting = Meeting.objects.create(owner=self.user, title="Réunion PFE", transcript=TRANSCRIPT)
        self.foreign = Meeting.objects.create(owner=self.other, title="Réunion privée", transcript=TRANSCRIPT)
        self.client.force_authenticate(self.user)

    def url(self, meeting, action=""):
        return f"/api/meetings/{meeting.id}/{action + '/' if action else ''}"

    # ------------------------------------------------------------ access
    def test_authentication_is_required(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/meetings/").status_code, 401)

    def test_list_only_contains_own_meetings(self):
        response = self.client.get("/api/meetings/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([m["id"] for m in response.data], [self.meeting.id])

    def test_other_users_meetings_are_not_accessible(self):
        self.assertEqual(self.client.get(self.url(self.foreign)).status_code, 404)
        self.assertEqual(self.client.patch(self.url(self.foreign), {"title": "Piraté"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(self.url(self.foreign)).status_code, 404)
        with patch("common.ai.generate_json") as generate:
            for action in ("transcribe", "summarize", "extract"):
                self.assertEqual(self.client.post(self.url(self.foreign, action)).status_code, 404)
            generate.assert_not_called()
        self.foreign.refresh_from_db()
        self.assertEqual(self.foreign.title, "Réunion privée")

    # ------------------------------------------------------------ creation
    def test_create_with_pasted_text_is_transcribed(self):
        response = self.client.post(
            "/api/meetings/", {"title": "Point d'équipe", "date": "2026-10-19", "transcript": TRANSCRIPT}, format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], Meeting.TRANSCRIBED)
        self.assertEqual(Meeting.objects.get(pk=response.data["id"]).owner, self.user)

    def test_audio_requires_consent(self):
        audio = SimpleUploadedFile("reunion.mp3", b"ID3fake", content_type="audio/mpeg")
        response = self.client.post("/api/meetings/", {"title": "Audio", "audio_file": audio}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertIn("consent_confirmed", response.data)

        audio = SimpleUploadedFile("reunion.mp3", b"ID3fake", content_type="audio/mpeg")
        response = self.client.post(
            "/api/meetings/", {"title": "Audio", "audio_file": audio, "consent_confirmed": "true"}, format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], Meeting.DRAFT)

    def test_audio_format_is_checked(self):
        audio = SimpleUploadedFile("reunion.flac", b"fake", content_type="audio/flac")
        response = self.client.post(
            "/api/meetings/", {"title": "Audio", "audio_file": audio, "consent_confirmed": "true"}, format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("audio_file", response.data)

    # ------------------------------------------------------------ transcription
    def test_transcribe_without_faster_whisper_asks_to_paste_text(self):
        meeting = Meeting.objects.create(
            owner=self.user, title="Audio", consent_confirmed=True,
            audio_file=SimpleUploadedFile("reunion.wav", b"RIFFfake"),
        )
        with patch.dict(sys.modules, {"faster_whisper": None}):  # makes the import fail
            response = self.client.post(self.url(meeting, "transcribe"))
        self.assertEqual(response.status_code, 503)
        self.assertIn("Collez le texte", response.data["detail"])

    def test_transcribe_without_audio(self):
        response = self.client.post(self.url(self.meeting, "transcribe"))
        self.assertEqual(response.status_code, 400)

    # ------------------------------------------------------------ AI
    def test_summarize_saves_the_summary(self):
        ai_result = {
            "summary": "Le sujet du PFE est validé.",
            "topics": ["Sujet du PFE", " Cahier des charges ", "", "Sujet du PFE"],
            "key_points": ["Sara rédige le cahier des charges pour le 23 octobre."],
        }
        with patch("common.ai.generate_json", return_value=ai_result) as generate:
            response = self.client.post(self.url(self.meeting, "summarize"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"], "Le sujet du PFE est validé.")
        # Blanks and duplicates are dropped by SummaryResponseSerializer.
        self.assertEqual(response.data["topics"], ["Sujet du PFE", "Cahier des charges"])
        self.assertEqual(response.data["key_points"], ["Sara rédige le cahier des charges pour le 23 octobre."])
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.topics, ["Sujet du PFE", "Cahier des charges"])
        self.assertIn('"topics"', generate.call_args.args[0])
        self.assertEqual(response.data["status"], Meeting.ANALYZED)
        self.assertIn(TRANSCRIPT, generate.call_args.args[0])

    def test_extract_saves_decisions_and_tasks(self):
        ai_result = {
            "decisions": ["Le sujet du PFE est validé."],
            "tasks": [
                {"title": "Rédiger le cahier des charges", "assignee": "Sara", "due_date": "2026-10-23"},
                {"title": "Préparer la maquette", "assignee": "Ali", "due_date": "bientôt"},
                {"title": "", "assignee": "Personne"},
            ],
        }
        with patch("common.ai.generate_json", return_value=ai_result):
            response = self.client.post(self.url(self.meeting, "extract"))
        self.assertEqual(response.status_code, 200)
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.decisions, ["Le sujet du PFE est validé."])
        self.assertEqual(self.meeting.tasks, [
            {"title": "Rédiger le cahier des charges", "assignee": "Sara", "due_date": "2026-10-23"},
            {"title": "Préparer la maquette", "assignee": "Ali", "due_date": None},
        ])
        self.assertEqual(self.meeting.status, Meeting.ANALYZED)

    def test_ai_not_configured_returns_503_and_marks_failed(self):
        with patch("common.ai.generate_json", side_effect=ai.AINotConfigured("Aucune clé GEMINI_API_KEY.")):
            response = self.client.post(self.url(self.meeting, "summarize"))
        self.assertEqual(response.status_code, 503)
        self.assertIn("GEMINI_API_KEY", response.data["detail"])
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, Meeting.FAILED)

    def test_ai_service_error_returns_502_and_marks_failed(self):
        with patch("common.ai.generate_json", side_effect=ai.AIError("Le service d'IA a renvoyé HTTP 503.")):
            response = self.client.post(self.url(self.meeting, "summarize"))
        self.assertEqual(response.status_code, 502)
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, Meeting.FAILED)

    def test_ai_error_keeps_an_analyzed_meeting_analyzed(self):
        self.meeting.summary = "Le sujet du PFE est validé."
        self.meeting.status = Meeting.ANALYZED
        self.meeting.save()
        with patch("common.ai.generate_json", side_effect=ai.AIError("Le service d'IA a renvoyé HTTP 503.")):
            response = self.client.post(self.url(self.meeting, "summarize"))
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["detail"], "Le service d'IA a renvoyé HTTP 503.")
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, Meeting.ANALYZED)
        self.assertEqual(self.meeting.summary, "Le sujet du PFE est validé.")

    def test_invalid_ai_response_returns_502_and_marks_failed(self):
        with patch("common.ai.generate_json", return_value={"decisions": "pas une liste"}):
            response = self.client.post(self.url(self.meeting, "extract"))
        self.assertEqual(response.status_code, 502)
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, Meeting.FAILED)
        self.assertEqual(self.meeting.tasks, [])

    def test_ai_requires_a_transcript(self):
        empty = Meeting.objects.create(owner=self.user, title="Vide")
        with patch("common.ai.generate_json") as generate:
            response = self.client.post(self.url(empty, "summarize"))
        self.assertEqual(response.status_code, 400)
        generate.assert_not_called()

    def test_editing_the_transcript_resets_a_failed_status(self):
        self.meeting.status = Meeting.FAILED
        self.meeting.save()
        response = self.client.patch(self.url(self.meeting), {"transcript": TRANSCRIPT + " Fin."}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], Meeting.TRANSCRIBED)


# ------------------------------------------------------------------ video calls (planning)
class VideoCallTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            email="orga@example.com", password="password123", first_name="Sara", last_name="Ben Ali",
        )
        self.guest = user_model.objects.create_user(email="invite@example.com", password="password123")
        self.guest2 = user_model.objects.create_user(email="invite2@example.com", password="password123")
        self.outsider = user_model.objects.create_user(email="externe@example.com", password="password123")
        user_model.objects.create_user(email="inactif@example.com", password="password123", is_active=False)
        self.client.force_authenticate(self.owner)

    def plan_call(self, emails=("invite@example.com",), **extra):
        payload = {
            "title": "Point PFE en visio", "video_call": True,
            "scheduled_at": "2026-11-20T14:30:00+01:00", "participant_emails": list(emails), **extra,
        }
        return self.client.post("/api/meetings/", payload, format="json")

    def test_create_call_with_participants(self):
        response = self.plan_call(["INVITE@example.com", "invite2@example.com"])
        self.assertEqual(response.status_code, 201, response.data)
        meeting = Meeting.objects.get(pk=response.data["id"])
        self.assertEqual(set(meeting.participants.all()), {self.guest, self.guest2})
        self.assertRegex(meeting.call_room, r"^StudentLife-[A-Za-z0-9]{20,}$")
        self.assertNotIn("call_url", response.data)  # no external call service any more
        self.assertTrue(response.data["is_call"])
        self.assertTrue(response.data["is_owner"])
        self.assertEqual(response.data["owner_name"], "Sara Ben Ali")
        self.assertEqual(response.data["status"], Meeting.DRAFT)  # no transcript nor audio needed
        self.assertEqual(str(meeting.date), "2026-11-20")
        self.assertEqual(
            sorted(p["email"] for p in response.data["participants"]), ["invite2@example.com", "invite@example.com"],
        )

    def test_call_requires_date_and_time(self):
        response = self.plan_call(scheduled_at=None)
        self.assertEqual(response.status_code, 400)
        self.assertIn("scheduled_at", response.data)

    def test_call_rooms_are_unique(self):
        first = Meeting.objects.get(pk=self.plan_call().data["id"])
        second = Meeting.objects.get(pk=self.plan_call().data["id"])
        self.assertTrue(first.call_room)
        self.assertNotEqual(first.call_room, second.call_room)

    def test_regular_meeting_is_not_a_call(self):
        response = self.client.post("/api/meetings/", {"title": "Notes", "transcript": TRANSCRIPT}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data["is_call"])
        self.assertEqual(Meeting.objects.get(pk=response.data["id"]).call_room, "")

    def test_invited_participants_are_notified(self):
        meeting_id = self.plan_call().data["id"]
        notification = Notification.objects.get(user=self.guest, title=INVITATION)
        self.assertIn("Sara Ben Ali", notification.message)
        self.assertIn("Point PFE en visio", notification.message)
        self.assertIn("20/11/2026 à 14:30", notification.message)
        self.assertEqual(notification.link, f"/reunions/{meeting_id}")
        self.assertFalse(Notification.objects.filter(user=self.owner, title=INVITATION).exists())

    def test_only_new_participants_are_notified(self):
        meeting_id = self.plan_call().data["id"]
        response = self.client.patch(
            f"/api/meetings/{meeting_id}/",
            {"participant_emails": ["invite@example.com", "invite2@example.com"]}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Notification.objects.filter(user=self.guest, title=INVITATION).count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.guest2, title=INVITATION).count(), 1)

    def test_participant_can_read_but_not_modify(self):
        meeting_id = self.plan_call().data["id"]
        Meeting.objects.filter(pk=meeting_id).update(transcript=TRANSCRIPT)
        self.client.force_authenticate(self.guest)

        listed = self.client.get("/api/meetings/")
        self.assertEqual([m["id"] for m in listed.data], [meeting_id])
        detail = self.client.get(f"/api/meetings/{meeting_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertFalse(detail.data["is_owner"])
        self.assertTrue(detail.data["is_call"])

        response = self.client.patch(f"/api/meetings/{meeting_id}/", {"title": "Modifié"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.delete(f"/api/meetings/{meeting_id}/").status_code, 403)
        with patch("common.ai.generate_json") as generate:
            for action in ("transcribe", "summarize", "extract"):
                self.assertEqual(self.client.post(f"/api/meetings/{meeting_id}/{action}/").status_code, 403)
            generate.assert_not_called()
        self.assertEqual(Meeting.objects.get(pk=meeting_id).title, "Point PFE en visio")

    def test_unknown_or_inactive_email_is_rejected(self):
        for email in ("personne@example.com", "inactif@example.com"):
            response = self.plan_call([email])
            self.assertEqual(response.status_code, 400)
            self.assertIn(email, str(response.data["participant_emails"]))
        self.assertFalse(Meeting.objects.exists())
        self.assertFalse(Notification.objects.filter(title=INVITATION).exists())

    def test_cannot_invite_yourself(self):
        response = self.plan_call(["orga@example.com"])
        self.assertEqual(response.status_code, 400)
        self.assertIn("vous-même", str(response.data["participant_emails"]))

    def test_participant_limit(self):
        self.assertEqual(settings.MEETING_MAX_INVITES, 50)  # default, MEETING_MAX_INVITES in the environment
        response = self.plan_call([f"p{i}@example.com" for i in range(51)])
        self.assertEqual(response.status_code, 400)
        self.assertIn("50", str(response.data["participant_emails"]))
        with override_settings(MEETING_MAX_INVITES=1):
            response = self.plan_call(["invite@example.com", "invite2@example.com"])
        self.assertEqual(response.status_code, 400)
        self.assertIn("1 participants", str(response.data["participant_emails"]))
        self.assertFalse(Meeting.objects.exists())

    def test_uninvited_user_cannot_see_the_meeting(self):
        meeting_id = self.plan_call().data["id"]
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(f"/api/meetings/{meeting_id}/").status_code, 404)
        self.assertEqual(self.client.get("/api/meetings/").data, [])


class TeacherInvitationTests(APITestCase):
    """Teachers use the meetings too: they invite students (one by one or a whole formation) and are invited."""

    def setUp(self):
        user_model = get_user_model()
        self.teacher = user_model.objects.create_user(
            email="prof@example.com", password="password123", role="teacher", first_name="Amel", last_name="Trabelsi",
        )
        self.other_teacher = user_model.objects.create_user(
            email="prof2@example.com", password="password123", role="teacher",
        )
        self.student = user_model.objects.create_user(email="etu1@example.com", password="password123")
        self.student2 = user_model.objects.create_user(email="etu2@example.com", password="password123")
        self.student3 = user_model.objects.create_user(email="etu3@example.com", password="password123")
        inactive = user_model.objects.create_user(email="etu-inactif@example.com", password="password123", is_active=False)
        self.formation = Formation.objects.create(teacher=self.teacher, title="Django avancé", is_published=True)
        self.other_formation = Formation.objects.create(teacher=self.other_teacher, title="Réseaux")
        for user in (self.student, self.student2, inactive):
            Enrollment.objects.create(user=user, formation=self.formation)
        Enrollment.objects.create(user=self.student3, formation=self.other_formation)
        self.client.force_authenticate(self.teacher)

    def plan_call(self, emails=(), **extra):
        payload = {
            "title": "Séance de questions", "video_call": True,
            "scheduled_at": "2026-12-01T10:00:00+01:00", "participant_emails": list(emails), **extra,
        }
        return self.client.post("/api/meetings/", payload, format="json")

    def test_teacher_invites_a_student(self):
        response = self.plan_call(["etu1@example.com"])
        self.assertEqual(response.status_code, 201, response.data)
        meeting = Meeting.objects.get(pk=response.data["id"])
        self.assertEqual(meeting.owner, self.teacher)
        self.assertTrue(meeting.call_room)

        notification = Notification.objects.get(user=self.student, title=INVITATION)
        self.assertIn("Amel Trabelsi", notification.message)
        self.assertEqual(notification.link, f"/reunions/{meeting.id}")

        self.client.force_authenticate(self.student)
        self.assertEqual([m["id"] for m in self.client.get("/api/meetings/").data], [meeting.id])
        detail = self.client.get(f"/api/meetings/{meeting.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertFalse(detail.data["is_owner"])
        self.assertEqual(self.client.post(f"/api/meetings/{meeting.id}/call-ticket/").status_code, 200)

    def test_student_invites_a_teacher(self):
        self.client.force_authenticate(self.student)
        response = self.plan_call(["prof@example.com"])
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(Notification.objects.filter(user=self.teacher, title=INVITATION).exists())
        self.client.force_authenticate(self.teacher)
        self.assertEqual([m["id"] for m in self.client.get("/api/meetings/").data], [response.data["id"]])
        self.assertEqual(self.client.post(f"/api/meetings/{response.data['id']}/call-ticket/").status_code, 200)

    def test_invite_formation_adds_every_enrolled_student(self):
        Enrollment.objects.create(user=self.teacher, formation=self.formation)  # never invites oneself
        response = self.plan_call(["etu1@example.com", "etu3@example.com"], invite_formation=self.formation.id)
        self.assertEqual(response.status_code, 201, response.data)
        meeting = Meeting.objects.get(pk=response.data["id"])
        # etu1 is in both the e-mails and the formation: invited once; the inactive student is left out.
        self.assertEqual(set(meeting.participants.all()), {self.student, self.student2, self.student3})
        self.assertNotIn("invite_formation", response.data)
        for user in (self.student, self.student2, self.student3):
            self.assertEqual(Notification.objects.filter(user=user, title=INVITATION).count(), 1)
        self.assertFalse(Notification.objects.filter(user=self.teacher, title=INVITATION).exists())

    def test_invite_formation_on_update_keeps_the_invited_and_notifies_the_new_ones(self):
        meeting_id = self.plan_call(["etu3@example.com"]).data["id"]
        response = self.client.patch(
            f"/api/meetings/{meeting_id}/", {"invite_formation": self.formation.id}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        meeting = Meeting.objects.get(pk=meeting_id)
        self.assertEqual(set(meeting.participants.all()), {self.student, self.student2, self.student3})
        self.assertEqual(Notification.objects.filter(user=self.student3, title=INVITATION).count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.student, title=INVITATION).count(), 1)

    def test_invite_formation_of_another_teacher_is_forbidden(self):
        response = self.plan_call(invite_formation=self.other_formation.id)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Meeting.objects.exists())
        self.assertFalse(Notification.objects.filter(title=INVITATION).exists())

    def test_invite_formation_by_a_student_is_forbidden(self):
        self.client.force_authenticate(self.student)
        response = self.plan_call(invite_formation=self.formation.id)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Meeting.objects.exists())

    def test_invite_formation_on_update_is_forbidden_for_another_formation(self):
        meeting_id = self.plan_call(["etu1@example.com"]).data["id"]
        response = self.client.patch(
            f"/api/meetings/{meeting_id}/", {"invite_formation": self.other_formation.id}, format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(list(Meeting.objects.get(pk=meeting_id).participants.all()), [self.student])

    def test_unknown_formation_is_rejected(self):
        response = self.plan_call(invite_formation=999999)
        self.assertEqual(response.status_code, 400)
        self.assertIn("invite_formation", response.data)

    def test_invite_formation_respects_the_invitation_limit(self):
        with override_settings(MEETING_MAX_INVITES=2):
            response = self.plan_call(["etu3@example.com"], invite_formation=self.formation.id)
            self.assertEqual(response.status_code, 400)
            self.assertIn("2 au maximum", str(response.data["invite_formation"]))
            self.assertFalse(Meeting.objects.exists())
            self.assertFalse(Notification.objects.filter(title=INVITATION).exists())
            # Exactly at the limit: accepted.
            response = self.plan_call(invite_formation=self.formation.id)
            self.assertEqual(response.status_code, 201, response.data)

    def test_my_formations_lists_only_the_user_formations(self):
        algo = Formation.objects.create(teacher=self.teacher, title="Algorithmique")
        response = self.client.get("/api/meetings/my-formations/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [
            {"id": algo.id, "title": "Algorithmique", "enrolled_count": 0},
            {"id": self.formation.id, "title": "Django avancé", "enrolled_count": 2},  # inactive student not counted
        ])
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get("/api/meetings/my-formations/").data, [])
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/meetings/my-formations/").status_code, 401)


# ------------------------------------------------------------------ in-app calls: ticket and WebSocket signaling
ICE_SERVERS = [{"urls": "stun:stun.example.org:3478"}]


@override_settings(WEBRTC_ICE_SERVERS=ICE_SERVERS)
class CallTicketTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(email="orga@example.com", password=None)
        self.guest = user_model.objects.create_user(email="invite@example.com", password=None)
        self.outsider = user_model.objects.create_user(email="externe@example.com", password=None)
        self.call = Meeting.objects.create(owner=self.owner, title="Appel", call_room="StudentLife-room1")
        self.call.participants.add(self.guest)
        self.url = f"/api/meetings/{self.call.id}/call-ticket/"

    def test_organizer_and_participant_get_a_ticket(self):
        for user in (self.owner, self.guest):
            self.client.force_authenticate(user)
            response = self.client.post(self.url)
            self.assertEqual(response.status_code, 200, response.data)
            self.assertTrue(response.data["ticket"])
            self.assertEqual(response.data["ice_servers"], ICE_SERVERS)
            self.assertEqual(response.data["max_peers"], settings.MEETING_MAX_PEERS)

    def test_ticket_gives_the_configured_limit(self):
        self.client.force_authenticate(self.guest)
        with override_settings(MEETING_MAX_PEERS=12):
            self.assertEqual(self.client.post(self.url).data["max_peers"], 12)
        self.assertEqual(self.client.get(f"/api/meetings/{self.call.id}/").data["call_max_peers"], settings.MEETING_MAX_PEERS)

    def test_uninvited_user_gets_404(self):
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.post(self.url).status_code, 404)

    def test_authentication_is_required(self):
        self.assertEqual(self.client.post(self.url).status_code, 401)

    def test_meeting_without_call_has_no_ticket(self):
        notes = Meeting.objects.create(owner=self.owner, title="Notes")
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(f"/api/meetings/{notes.id}/call-ticket/").status_code, 400)


# The consumer reads the database through database_sync_to_async, which closes the connection when it is inside
# the transaction that TestCase wraps around each test: TransactionTestCase is required here.
class CallTestCase(TransactionTestCase):
    ORIGIN = settings.CORS_ALLOWED_ORIGINS[0]

    def setUp(self):
        consumers.ROOMS.clear()
        consumers.RECORDINGS.clear()
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            email="orga@example.com", password=None, first_name="Sara", last_name="Ben Ali",
        )
        self.guests = [user_model.objects.create_user(email=f"invite{i}@example.com", password=None) for i in range(4)]
        self.guest = self.guests[0]
        self.outsider = user_model.objects.create_user(email="externe@example.com", password=None)
        self.call = Meeting.objects.create(owner=self.owner, title="Appel", call_room="StudentLife-room1")
        self.call.participants.set(self.guests)
        self.other_call = Meeting.objects.create(owner=self.owner, title="Autre appel", call_room="StudentLife-room2")
        self.open = []

    async def connect(self, user=None, ticket=None, meeting=None, origin=None):
        meeting = meeting or self.call
        if ticket is None and user is not None:
            ticket = make_ticket(user, meeting)
        query = f"?ticket={ticket}" if ticket else ""
        communicator = WebsocketCommunicator(
            application, f"/ws/meetings/{meeting.id}/call/{query}",
            headers=[(b"origin", (origin or self.ORIGIN).encode()), (b"host", b"localhost:8000")],
        )
        connected, code = await communicator.connect()
        if connected:
            self.open.append(communicator)
        return communicator, connected, code

    async def join(self, user):
        """Connect and return (communicator, my peer id), after reading the welcome message."""
        communicator, connected, _code = await self.connect(user)
        self.assertTrue(connected)
        welcome = await communicator.receive_json_from()
        self.assertEqual(welcome["type"], "peers")
        return communicator, welcome["you"]["id"]

    async def close_all(self):
        for communicator in self.open:
            await communicator.disconnect()
        self.open = []


class CallSignalingTests(CallTestCase):
    async def test_refused_without_ticket(self):
        _c, connected, _code = await self.connect()
        self.assertFalse(connected)
        _c, connected, _code = await self.connect(ticket="faux-ticket")
        self.assertFalse(connected)

    async def test_refused_with_expired_ticket(self):
        with patch("django.core.signing.time.time", return_value=time.time() - 120):
            ticket = make_ticket(self.owner, self.call)
        _c, connected, _code = await self.connect(ticket=ticket)
        self.assertFalse(connected)

    async def test_refused_with_ticket_of_another_meeting(self):
        ticket = make_ticket(self.owner, self.other_call)
        _c, connected, _code = await self.connect(ticket=ticket)
        self.assertFalse(connected)

    async def test_refused_when_not_invited(self):
        _c, connected, _code = await self.connect(self.outsider)
        self.assertFalse(connected)

    async def test_refused_from_an_unknown_origin(self):
        _c, connected, _code = await self.connect(self.owner, origin="https://evil.example.com")
        self.assertFalse(connected)

    async def test_organizer_and_guest_are_accepted(self):
        owner, owner_id = await self.join(self.owner)
        guest, connected, _code = await self.connect(self.guest)
        self.assertTrue(connected)
        welcome = await guest.receive_json_from()
        self.assertEqual([(p["id"], p["name"]) for p in welcome["peers"]], [(owner_id, "Sara Ben Ali")])
        joined = await owner.receive_json_from()
        self.assertEqual(joined["type"], "join")
        self.assertEqual(joined["peer"]["id"], welcome["you"]["id"])
        self.assertEqual(joined["peer"]["name"], "invite0@example.com")
        await self.close_all()

    async def test_offer_is_relayed_to_the_recipient_only(self):
        owner, owner_id = await self.join(self.owner)
        guest, _guest_id = await self.join(self.guests[0])
        guest2, guest2_id = await self.join(self.guests[1])
        await owner.receive_json_from()  # join of guest
        await owner.receive_json_from()  # join of guest2
        await guest.receive_json_from()  # join of guest2

        await guest2.send_json_to({"type": "offer", "to": owner_id, "sdp": "v=0 fake-sdp"})
        offer = await owner.receive_json_from()
        self.assertEqual(offer, {"type": "offer", "from": guest2_id, "name": "invite1@example.com", "sdp": "v=0 fake-sdp"})
        self.assertTrue(await guest.receive_nothing())
        self.assertTrue(await guest2.receive_nothing())
        await self.close_all()

    async def test_media_state_and_leave_are_broadcast(self):
        owner, _owner_id = await self.join(self.owner)
        guest, guest_id = await self.join(self.guest)
        await owner.receive_json_from()  # join
        await guest.send_json_to({"type": "media", "mic": False, "cam": True})
        self.assertEqual(await owner.receive_json_from(), {"type": "media", "id": guest_id, "mic": False, "cam": True})
        await guest.send_json_to({"type": "leave"})
        self.assertEqual(await owner.receive_json_from(), {"type": "leave", "id": guest_id})
        await self.close_all()
        self.assertEqual(consumers.ROOMS, {})

    def test_default_limit_is_8(self):
        """Without MEETING_MAX_PEERS in the environment (nor in .env), the limit is 8."""
        import importlib.util
        import os

        path = Path(settings.BASE_DIR) / "config" / "settings.py"
        spec = importlib.util.spec_from_file_location("settings_without_env", path)
        module = importlib.util.module_from_spec(spec)
        env = {k: v for k, v in os.environ.items() if k != "MEETING_MAX_PEERS"}
        with patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"):
            spec.loader.exec_module(module)
        self.assertEqual(module.MEETING_MAX_PEERS, 8)

    async def test_person_above_the_limit_is_refused(self):
        with override_settings(MEETING_MAX_PEERS=3):
            for user in [self.owner, *self.guests[:2]]:
                await self.join(user)
            extra, connected, _code = await self.connect(self.guests[2])
            self.assertTrue(connected)  # accepted only to explain the refusal
            error = await extra.receive_json_from()
            self.assertEqual(error["code"], "call_full")
            self.assertIn("3 participants maximum", error["detail"])
            closed = await extra.receive_output()
            self.assertEqual(closed, {"type": "websocket.close", "code": consumers.CLOSE_FULL})
            self.assertEqual(len(consumers.ROOMS[self.call.id]), 3)
        await self.close_all()

    async def test_more_than_four_people_can_join_by_default(self):
        # 5 people (more than the old limit of 4) are all admitted with the default limit.
        for user in [self.owner, *self.guests]:
            await self.join(user)
        self.assertEqual(len(consumers.ROOMS[self.call.id]), 5)
        await self.close_all()


# ------------------------------------------------------------------ recording consent (exigence 8.1)
class RecordingConsentTests(CallTestCase):
    async def start_call(self):
        """Organizer and one guest in the call; returns (owner, guest) communicators."""
        owner, _owner_id = await self.join(self.owner)
        guest, _guest_id = await self.join(self.guest)
        await owner.receive_json_from()  # join of the guest
        return owner, guest

    async def request(self, owner, guest):
        await owner.send_json_to({"type": "recording-request"})
        for communicator in (owner, guest):
            state = await communicator.receive_json_from()
            self.assertEqual(state["type"], "recording")
            self.assertEqual(state["state"], "pending")
            self.assertEqual(state["waiting"], ["invite0@example.com"])
        return state["session"]

    async def start_recording(self):
        owner, guest = await self.start_call()
        session = await self.request(owner, guest)
        await guest.send_json_to({"type": "recording-consent", "accepted": True})
        for communicator in (owner, guest):
            self.assertEqual((await communicator.receive_json_from())["state"], "recording")
        return owner, guest, session

    @database_sync_to_async
    def consents(self, session):
        return {c.user_id: c.accepted for c in RecordingConsent.objects.filter(session_id=session)}

    @database_sync_to_async
    def session(self, session):
        return RecordingSession.objects.get(pk=session)

    async def test_recording_starts_when_everybody_accepted(self):
        owner, guest = await self.start_call()
        session_id = await self.request(owner, guest)
        session = await self.session(session_id)
        self.assertEqual(session.status, RecordingSession.PENDING)
        self.assertIsNone(session.started_at)  # nothing recorded before the guest's answer

        await guest.send_json_to({"type": "recording-consent", "accepted": True})
        for communicator in (owner, guest):
            state = await communicator.receive_json_from()
            self.assertEqual(state["state"], "recording")  # the indicator everybody sees
            self.assertEqual(state["waiting"], [])
        session = await self.session(session_id)
        self.assertEqual(session.status, RecordingSession.RECORDING)
        self.assertIsNotNone(session.started_at)
        # Who accepted, saved on the server (the organizer consents by asking), and when.
        self.assertEqual(await self.consents(session_id), {self.owner.id: True, self.guest.id: True})
        answered = await database_sync_to_async(
            lambda: RecordingConsent.objects.get(session_id=session_id, user=self.guest).answered_at
        )()
        self.assertIsNotNone(answered)

        await owner.send_json_to({"type": "recording-stop"})
        self.assertEqual((await guest.receive_json_from())["state"], "idle")
        self.assertEqual((await self.session(session_id)).status, RecordingSession.STOPPED)
        await self.close_all()

    async def test_one_refusal_cancels_the_request(self):
        owner, guest = await self.start_call()
        session_id = await self.request(owner, guest)
        await guest.send_json_to({"type": "recording-consent", "accepted": False})
        for communicator in (owner, guest):
            state = await communicator.receive_json_from()
            self.assertEqual((state["state"], state["reason"], state["by"]), ("idle", "refused", "invite0@example.com"))
        session = await self.session(session_id)
        self.assertEqual(session.status, RecordingSession.REFUSED)
        self.assertIsNone(session.started_at)
        self.assertEqual(await self.consents(session_id), {self.owner.id: True, self.guest.id: False})
        await self.close_all()

    async def test_only_the_organizer_can_ask(self):
        _owner, guest = await self.start_call()
        await guest.send_json_to({"type": "recording-request"})
        self.assertEqual((await guest.receive_json_from())["code"], "forbidden")
        self.assertEqual(consumers.RECORDINGS, {})
        await self.close_all()

    async def test_newcomer_must_accept_to_join_a_recorded_call(self):
        owner, _guest, session_id = await self.start_recording()
        newcomer, connected, _code = await self.connect(self.guests[1])
        self.assertTrue(connected)
        message = await newcomer.receive_json_from()
        self.assertEqual(message["type"], "consent-required")
        self.assertEqual(message["recording"]["state"], "recording")
        self.assertTrue(await owner.receive_nothing())  # not announced before accepting

        await newcomer.send_json_to({"type": "recording-consent", "accepted": True})
        welcome = await newcomer.receive_json_from()
        self.assertEqual(welcome["type"], "peers")
        self.assertEqual(len(welcome["peers"]), 2)
        self.assertEqual((await owner.receive_json_from())["type"], "join")
        self.assertEqual(
            await self.consents(session_id), {self.owner.id: True, self.guest.id: True, self.guests[1].id: True},
        )
        await self.close_all()

    async def test_newcomer_who_refuses_is_disconnected(self):
        owner, _guest, session_id = await self.start_recording()
        newcomer, _connected, _code = await self.connect(self.guests[1])
        await newcomer.receive_json_from()  # consent-required
        await newcomer.send_json_to({"type": "recording-consent", "accepted": False})
        self.assertEqual((await newcomer.receive_json_from())["code"], "consent_refused")
        closed = await newcomer.receive_output()
        self.assertEqual(closed, {"type": "websocket.close", "code": consumers.CLOSE_CONSENT_REFUSED})
        self.assertTrue(await owner.receive_nothing())
        self.assertEqual((await self.session(session_id)).status, RecordingSession.RECORDING)  # goes on
        self.assertFalse((await self.consents(session_id))[self.guests[1].id])
        await self.close_all()

    async def test_newcomer_cannot_signal_before_accepting(self):
        owner, _guest, _session = await self.start_recording()
        newcomer, _connected, _code = await self.connect(self.guests[1])
        you = (await newcomer.receive_json_from())["you"]
        owner_id = next(p["id"] for p in consumers.ROOMS[self.call.id].values() if p["user_id"] == self.owner.id)
        await newcomer.send_json_to({"type": "offer", "to": owner_id, "sdp": "v=0 fake"})
        self.assertTrue(await owner.receive_nothing())
        self.assertFalse(consumers.ROOMS[self.call.id][you["id"]]["admitted"])
        await self.close_all()

    async def test_recorder_leaving_stops_the_recording(self):
        owner, guest, session_id = await self.start_recording()
        await owner.send_json_to({"type": "leave"})
        self.assertEqual((await guest.receive_json_from())["type"], "leave")
        state = await guest.receive_json_from()
        self.assertEqual((state["state"], state["reason"]), ("idle", "recorder_left"))
        self.assertEqual((await self.session(session_id)).status, RecordingSession.STOPPED)
        await self.close_all()


# ------------------------------------------------------------------ recording upload, audio access, processing
SUMMARY = {
    "summary": "Le sujet du PFE est validé et le travail est réparti.",
    "topics": ["Sujet du PFE", "Répartition du travail"],
    "key_points": ["Le cahier des charges est attendu le 23 octobre."],
}
EXTRACTION = {
    "decisions": ["Le sujet du PFE est validé."],
    "tasks": [{"title": "Rédiger le cahier des charges", "assignee": "Sara", "due_date": "2026-10-23"}],
}


def fake_ai(prompt, *args, **kwargs):
    return SUMMARY if '"topics"' in prompt else EXTRACTION


def webm(size=64, name="appel.webm"):
    return SimpleUploadedFile(name, b"\x1aE\xdf\xa3" + b"0" * (size - 4), content_type="audio/webm")


@override_settings(MEDIA_ROOT=MEDIA_ROOT, MEETINGS_AUDIO_ROOT=AUDIO_ROOT, MEETINGS_SYNC_PROCESSING=True)
class RecordingProcessingTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(email="orga@example.com", password=None)
        self.guest = user_model.objects.create_user(email="invite@example.com", password=None)
        self.outsider = user_model.objects.create_user(email="externe@example.com", password=None)
        self.call = Meeting.objects.create(owner=self.owner, title="Point PFE", call_room="StudentLife-room1")
        self.call.participants.add(self.guest)
        self.client.force_authenticate(self.owner)

    def recording_session(self, status=RecordingSession.STOPPED, started=True):
        session = RecordingSession.objects.create(
            meeting=self.call, requested_by=self.owner, status=status, started_at=timezone.now() if started else None,
        )
        RecordingConsent.objects.create(session=session, user=self.owner, accepted=True)
        return session

    def upload(self, session, audio=None):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                f"/api/meetings/{self.call.id}/recording/",
                {"session": session.id, "audio_file": audio or webm()}, format="multipart",
            )

    # ------------------------------------------------------------ consent and upload
    def test_recording_upload_runs_transcription_then_analysis(self):
        session = self.recording_session()
        with patch("meetings.services.transcribe_audio", return_value=TRANSCRIPT) as transcribe, \
                patch("common.ai.generate_json", side_effect=fake_ai) as generate:
            response = self.upload(session)
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(response.data["processing_status"], Meeting.TRANSCRIBING)  # shown while it runs
        transcribe.assert_called_once()
        self.assertEqual(generate.call_count, 2)  # summary, then decisions and tasks

        self.call.refresh_from_db()
        self.assertEqual(self.call.processing_status, Meeting.DONE)
        self.assertEqual(self.call.status, Meeting.ANALYZED)
        self.assertTrue(self.call.consent_confirmed)
        self.assertEqual(self.call.transcript, TRANSCRIPT)
        self.assertEqual(self.call.summary, SUMMARY["summary"])
        self.assertEqual(self.call.topics, SUMMARY["topics"])
        self.assertEqual(self.call.key_points, SUMMARY["key_points"])
        self.assertEqual(self.call.decisions, EXTRACTION["decisions"])
        self.assertEqual(self.call.tasks, EXTRACTION["tasks"])
        session.refresh_from_db()
        self.assertEqual(session.status, RecordingSession.UPLOADED)

        detail = self.client.get(f"/api/meetings/{self.call.id}/").data
        self.assertEqual((detail["topics"], detail["key_points"]), (SUMMARY["topics"], SUMMARY["key_points"]))
        self.assertEqual(detail["audio_url"], f"/meetings/{self.call.id}/audio/")
        self.assertNotIn("audio_file", detail)  # no public URL any more

    def test_upload_refused_without_the_consent_of_everybody(self):
        for status, started in ((RecordingSession.PENDING, False), (RecordingSession.REFUSED, False),
                                (RecordingSession.CANCELLED, False), (RecordingSession.UPLOADED, True)):
            with patch("meetings.services.transcribe_audio") as transcribe:
                response = self.upload(self.recording_session(status, started))
            self.assertEqual(response.status_code, 400, status)
            transcribe.assert_not_called()
        self.call.refresh_from_db()
        self.assertFalse(self.call.audio_file)
        self.assertFalse(self.call.consent_confirmed)

    def test_upload_with_the_session_of_another_meeting_is_refused(self):
        other = Meeting.objects.create(owner=self.owner, title="Autre", call_room="StudentLife-room2")
        session = RecordingSession.objects.create(
            meeting=other, requested_by=self.owner, status=RecordingSession.STOPPED, started_at=timezone.now(),
        )
        response = self.upload(session)
        self.assertEqual(response.status_code, 400)
        self.assertIn("session", response.data)

    def test_only_the_organizer_uploads(self):
        self.client.force_authenticate(self.guest)
        self.assertEqual(self.upload(self.recording_session()).status_code, 403)

    @override_settings(MEETING_MAX_AUDIO_MB=1)
    def test_audio_size_limit(self):
        response = self.upload(self.recording_session(), webm(size=1024 * 1024 + 1))
        self.assertEqual(response.status_code, 400)
        self.assertIn("1 Mo", str(response.data["audio_file"]))

    def test_webm_and_ogg_uploads_are_accepted(self):
        for name in ("reunion.webm", "reunion.ogg"):
            response = self.client.post(
                "/api/meetings/", {"title": "Audio", "audio_file": webm(name=name), "consent_confirmed": "true"},
                format="multipart",
            )
            self.assertEqual(response.status_code, 201, response.data)
            self.assertTrue(response.data["has_audio"])

    # ------------------------------------------------------------ private audio
    def test_audio_is_served_to_members_only(self):
        with patch("meetings.services.transcribe_audio", return_value=TRANSCRIPT), \
                patch("common.ai.generate_json", side_effect=fake_ai):
            self.upload(self.recording_session(), webm(size=100))
        self.call.refresh_from_db()
        name = self.call.audio_file.name
        self.assertFalse(Path(MEDIA_ROOT, name).exists())  # not reachable through /media/
        self.assertTrue(Path(AUDIO_ROOT, name).exists())

        url = f"/api/meetings/{self.call.id}/audio/"
        for user in (self.owner, self.guest):
            self.client.force_authenticate(user)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "audio/webm")
            self.assertEqual(len(b"".join(response.streaming_content)), 100)
            response.close()
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(url).status_code, 401)

    def test_audio_of_meeting_without_recording(self):
        self.assertEqual(self.client.get(f"/api/meetings/{self.call.id}/audio/").status_code, 404)

    # ------------------------------------------------------------ processing failures
    def test_transcription_failure_sets_error(self):
        with patch("meetings.services.transcribe_audio",
                   side_effect=services.TranscriptionError("Aucune parole détectée.")), \
                patch("common.ai.generate_json") as generate:
            self.assertEqual(self.upload(self.recording_session()).status_code, 202)
        generate.assert_not_called()
        self.call.refresh_from_db()
        self.assertEqual(self.call.processing_status, Meeting.ERROR)
        self.assertEqual(self.call.processing_error, "Aucune parole détectée.")
        self.assertEqual(self.call.status, Meeting.FAILED)

    def test_ai_not_configured_sets_error(self):
        with patch("meetings.services.transcribe_audio", return_value=TRANSCRIPT), \
                patch("common.ai.generate_json", side_effect=ai.AINotConfigured("Aucune clé GEMINI_API_KEY.")):
            self.upload(self.recording_session())
        self.call.refresh_from_db()
        self.assertEqual(self.call.processing_status, Meeting.ERROR)
        self.assertIn("GEMINI_API_KEY", self.call.processing_error)
        self.assertEqual(self.call.transcript, TRANSCRIPT)  # the transcription is kept

    def test_extraction_failure_keeps_the_summary(self):
        def summary_then_error(prompt, *args, **kwargs):
            if '"topics"' in prompt:
                return SUMMARY
            raise ai.AIError("Le service d'IA a renvoyé HTTP 503.")
        with patch("meetings.services.transcribe_audio", return_value=TRANSCRIPT), \
                patch("common.ai.generate_json", side_effect=summary_then_error):
            self.upload(self.recording_session())
        self.call.refresh_from_db()
        self.assertEqual(self.call.processing_status, Meeting.ERROR)
        self.assertEqual(self.call.status, Meeting.ANALYZED)  # results exist: not FAILED
        self.assertEqual(self.call.summary, SUMMARY["summary"])
        self.assertEqual(self.call.topics, SUMMARY["topics"])

    def test_invalid_summary_format_sets_error(self):
        with patch("meetings.services.transcribe_audio", return_value=TRANSCRIPT), \
                patch("common.ai.generate_json", return_value={"summary": "Résumé", "topics": "pas une liste"}):
            self.upload(self.recording_session())
        self.call.refresh_from_db()
        self.assertEqual(self.call.processing_status, Meeting.ERROR)
        self.assertEqual(self.call.topics, [])

    # ------------------------------------------------------------ process action and concurrency
    def test_process_analyses_a_pasted_transcript(self):
        Meeting.objects.filter(pk=self.call.pk).update(transcript=TRANSCRIPT)
        with patch("common.ai.generate_json", side_effect=fake_ai), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"/api/meetings/{self.call.id}/process/")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["processing_status"], Meeting.ANALYZING)
        self.call.refresh_from_db()
        self.assertEqual(self.call.processing_status, Meeting.DONE)
        self.assertEqual(self.call.key_points, SUMMARY["key_points"])

    def test_steps_are_refused_while_processing(self):
        Meeting.objects.filter(pk=self.call.pk).update(transcript=TRANSCRIPT, processing_status=Meeting.ANALYZING)
        with patch("common.ai.generate_json") as generate:
            for action in ("summarize", "extract", "process"):
                self.assertEqual(self.client.post(f"/api/meetings/{self.call.id}/{action}/").status_code, 409)
            generate.assert_not_called()

    def test_participant_cannot_launch_processing(self):
        self.client.force_authenticate(self.guest)
        self.assertEqual(self.client.post(f"/api/meetings/{self.call.id}/process/").status_code, 403)

    def test_transcription_forces_the_configured_language(self):
        class FakeSegment:
            text = " Bonjour à tous. "

        class FakeModel:
            def __init__(self, *args, **kwargs):
                self.calls = []

            def transcribe(self, path, **kwargs):
                self.calls.append(kwargs)
                return [FakeSegment()], None

        fake_module = type(sys)("faster_whisper")
        fake_module.WhisperModel = FakeModel
        services._whisper_model = None
        try:
            with patch.dict(sys.modules, {"faster_whisper": fake_module}):
                self.assertEqual(services.transcribe_audio("reunion.webm"), "Bonjour à tous.")
                self.assertEqual(services._whisper_model.calls, [{"language": "fr"}])  # default WHISPER_LANGUAGE
                with override_settings(WHISPER_LANGUAGE="en"):
                    services.transcribe_audio("reunion.webm")
                self.assertEqual(services._whisper_model.calls[-1], {"language": "en"})
        finally:
            services._whisper_model = None

    def test_whisper_model_is_loaded_once(self):
        loaded = []

        class FakeModel:
            def __init__(self, *args, **kwargs):
                time.sleep(0.05)  # slow load: the other threads wait for the lock
                loaded.append(self)

        services._whisper_model = None
        try:
            threads = [threading.Thread(target=services._get_whisper_model, args=(FakeModel,)) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(len(loaded), 1)
        finally:
            services._whisper_model = None
