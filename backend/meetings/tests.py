import shutil
import sys
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from common import ai
from notifications.models import Notification

from .models import Meeting

INVITATION = "Invitation à une réunion"
TRANSCRIPT = (
    "Ali : on valide le sujet du projet de fin d'études. Sara : je rédige le cahier des charges "
    "pour vendredi 23 octobre. Ali : je prépare la maquette."
)
MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class MeetingTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)
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
        audio = SimpleUploadedFile("reunion.ogg", b"fake", content_type="audio/ogg")
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
        with patch("common.ai.generate_json", return_value={"summary": "Le sujet du PFE est validé."}) as generate:
            response = self.client.post(self.url(self.meeting, "summarize"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"], "Le sujet du PFE est validé.")
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


# ------------------------------------------------------------------ video calls (Jitsi)
@override_settings(JITSI_BASE_URL="https://meet.example.org")
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
        self.assertEqual(response.data["call_url"], f"https://meet.example.org/{meeting.call_room}")
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

    def test_call_links_are_unique(self):
        first = self.plan_call().data
        second = self.plan_call().data
        self.assertTrue(first["call_url"])
        self.assertNotEqual(first["call_url"], second["call_url"])

    def test_regular_meeting_has_no_call_link(self):
        response = self.client.post("/api/meetings/", {"title": "Notes", "transcript": TRANSCRIPT}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["call_url"], "")
        self.assertFalse(response.data["is_call"])

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
        self.assertTrue(detail.data["call_url"])

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
        response = self.plan_call([f"p{i}@example.com" for i in range(21)])
        self.assertEqual(response.status_code, 400)
        self.assertIn("20", str(response.data["participant_emails"]))

    def test_uninvited_user_cannot_see_the_meeting(self):
        meeting_id = self.plan_call().data["id"]
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(f"/api/meetings/{meeting_id}/").status_code, 404)
        self.assertEqual(self.client.get("/api/meetings/").data, [])
