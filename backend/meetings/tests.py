import shutil
import sys
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from common import ai

from .models import Meeting

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
