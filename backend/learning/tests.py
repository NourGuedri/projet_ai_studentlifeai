from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from common import ai

from .models import Course, Formation, Lesson, LessonMaterial, Quiz


class QuizRolePermissionTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.student = user_model.objects.create_user(email="student@example.com", password="password123", role="student")
        self.teacher = user_model.objects.create_user(email="teacher@example.com", password="password123", role="teacher")
        self.client = APIClient()
        self.quiz = Quiz.objects.create(owner=self.teacher, title="Quiz de test")
        self.quiz.questions.create(
            text="Question ?", choices=["A", "B"], correct_index=1, explanation="La réponse est B."
        )
        self.quiz_url = f"/api/learning/quizzes/{self.quiz.id}/"
        self.quiz_data = {
            "title": "Nouveau quiz",
            "questions": [{
                "text": "Nouvelle question ?",
                "choices": ["Oui", "Non"],
                "correct_index": 0,
                "explanation": "",
            }],
        }

    def test_students_cannot_create_update_or_delete_saved_quizzes(self):
        self.client.force_authenticate(self.student)

        response = self.client.post("/api/learning/quizzes/", self.quiz_data, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Quiz.objects.count(), 1)

        response = self.client.patch(self.quiz_url, {"title": "Modifié"}, format="json")
        self.assertEqual(response.status_code, 403)
        response = self.client.delete(self.quiz_url)
        self.assertEqual(response.status_code, 403)

        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.title, "Quiz de test")

    def test_teachers_can_create_and_edit_their_quizzes(self):
        self.client.force_authenticate(self.teacher)

        response = self.client.post("/api/learning/quizzes/", self.quiz_data, format="json")
        self.assertEqual(response.status_code, 201)
        created_id = response.data["id"]

        response = self.client.patch(
            f"/api/learning/quizzes/{created_id}/", {"title": "Quiz mis à jour"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["title"], "Quiz mis à jour")

    def test_students_can_generate_practice_questions_without_saving_a_quiz(self):
        self.client.force_authenticate(self.student)
        questions = [{
            "text": "Question ?",
            "choices": ["Oui", "Non"],
            "correct_index": 0,
            "explanation": "Oui.",
        }]
        with patch("learning.views.services.generate_questions", return_value=questions):
            response = self.client.post(
                "/api/learning/quizzes/generate/",
                {"text": "Un texte de cours assez long pour générer des questions de pratique.", "num_questions": 1},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["questions"], questions)
        self.assertEqual(Quiz.objects.count(), 1)

    @patch("learning.views.services.generate_questions", return_value=[{"text": "Question"}])
    @patch(
        "learning.views.QuizViewSet._read_text_file",
        return_value="Texte suffisamment long extrait du fichier PDF du cours pour générer des questions.",
    )
    def test_course_file_text_is_included_when_generating_questions(self, read_file, generate):
        course = Course.objects.create(owner=self.student, title="Cours PDF", file="courses/document.pdf")
        self.client.force_authenticate(self.student)

        response = self.client.post(
            "/api/learning/quizzes/generate/",
            {"course": course.id, "num_questions": 1},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Texte suffisamment long extrait du fichier PDF du cours", generate.call_args.args[0])
        read_file.assert_called_once()

    @patch("learning.views.services.generate_questions", return_value=[{"text": "Question"}])
    @patch(
        "learning.views.QuizViewSet._read_text_file",
        return_value="Texte suffisamment long extrait du support PDF de la leçon pour générer des questions.",
    )
    def test_formation_quiz_generation_includes_lesson_documents(self, read_file, generate):
        formation = Formation.objects.create(teacher=self.teacher, title="Formation PDF")
        lesson = Lesson.objects.create(formation=formation, title="Leçon")
        LessonMaterial.objects.create(lesson=lesson, file="materials/document.pdf", name="document.pdf")
        self.client.force_authenticate(self.teacher)

        response = self.client.post(
            "/api/learning/quizzes/generate/",
            {"formation": formation.id, "num_questions": 1},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Texte suffisamment long extrait du support PDF de la leçon", generate.call_args.args[0])
        read_file.assert_called_once()

    def test_students_do_not_receive_answers_before_submitting_a_quiz(self):
        student_quiz = Quiz.objects.create(owner=self.student, title="Ancien quiz étudiant")
        student_quiz.questions.create(
            text="Question ?", choices=["A", "B"], correct_index=1, explanation="Réponse B."
        )
        self.client.force_authenticate(self.student)

        response = self.client.get(f"/api/learning/quizzes/{student_quiz.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("correct_index", response.data["questions"][0])
        self.assertNotIn("explanation", response.data["questions"][0])

    def test_teachers_can_add_quizzes_to_their_formations(self):
        formation = Formation.objects.create(teacher=self.teacher, title="Formation de test")
        self.client.force_authenticate(self.teacher)

        response = self.client.post(
            "/api/learning/quizzes/",
            {**self.quiz_data, "formation": formation.id},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["formation"], formation.id)

    def test_teachers_cannot_submit_quizzes(self):
        self.client.force_authenticate(self.teacher)

        response = self.client.post(
            f"{self.quiz_url}submit/",
            {"answers": {str(self.quiz.questions.first().id): 1}},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.quiz.attempts.count(), 0)

    @patch("common.ai.time.sleep")
    @patch("common.ai.requests.post")
    def test_ai_retries_once_after_a_read_timeout(self, post, sleep):
        response = type("Response", (), {
            "ok": True,
            "json": lambda self: {
                "candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]
            },
        })()
        post.side_effect = [requests.exceptions.ReadTimeout(), response]
        with patch.dict("common.ai.os.environ", {"GEMINI_API_KEY": "test-key", "GEMINI_TIMEOUT": "90"}):
            result = ai.generate_json("test prompt")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args.kwargs["timeout"], 90.0)
        sleep.assert_called_once_with(1)

    @patch("common.ai.time.sleep")
    @patch("common.ai.requests.post", side_effect=requests.exceptions.ReadTimeout())
    def test_ai_reports_a_clear_error_after_two_read_timeouts(self, post, sleep):
        with patch.dict("common.ai.os.environ", {"GEMINI_API_KEY": "test-key"}):
            with self.assertRaisesRegex(ai.AIError, "après deux tentatives"):
                ai.generate_json("test prompt", timeout=1)

        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(1)
