from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from learning.models import Enrollment, Formation, Quiz, QuizAttempt
from notifications.models import Notification

from .models import Report

User = get_user_model()
PASSWORD = "S3cure-pass-42"


def make(email, role="student", **extra):
    return User.objects.create_user(email=email, password=PASSWORD, role=role, **extra)


class AdminTestCase(TestCase):
    def setUp(self):
        self.admin = make("admin@example.com", "admin")
        self.teacher = make("teacher@example.com", "teacher", first_name="Tara", last_name="Prof")
        self.student = make("student@example.com", "student")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)


class PermissionTests(AdminTestCase):
    URLS = [
        "/api/admin/stats/", "/api/admin/users/", "/api/admin/formations/", "/api/admin/reports/",
    ]

    def test_only_admins_reach_admin_endpoints(self):
        for user in (self.student, self.teacher):
            self.client.force_authenticate(user)
            for url in self.URLS:
                self.assertEqual(self.client.get(url).status_code, 403, f"{user.role} on {url}")
            self.assertEqual(self.client.post("/api/admin/announcements/", {"title": "x"}, format="json").status_code, 403)

    def test_anonymous_gets_401(self):
        self.client.force_authenticate(None)
        for url in self.URLS:
            self.assertEqual(self.client.get(url).status_code, 401)

    def test_admin_reaches_everything(self):
        for url in self.URLS:
            self.assertEqual(self.client.get(url).status_code, 200, url)


class UserManagementTests(AdminTestCase):
    def test_list_search_and_filters(self):
        data = self.client.get("/api/admin/users/").json()
        self.assertEqual(data["count"], 3)
        self.assertEqual(self.client.get("/api/admin/users/?role=teacher").json()["count"], 1)
        self.assertEqual(self.client.get("/api/admin/users/?q=tara").json()["results"][0]["email"], "teacher@example.com")
        self.student.is_active = False
        self.student.save()
        self.assertEqual(self.client.get("/api/admin/users/?active=0").json()["count"], 1)

    def test_counts_are_returned(self):
        formation = Formation.objects.create(teacher=self.teacher, title="Python", is_published=True)
        Enrollment.objects.create(user=self.student, formation=formation)
        rows = {r["email"]: r for r in self.client.get("/api/admin/users/").json()["results"]}
        self.assertEqual(rows["teacher@example.com"]["formations_count"], 1)
        self.assertEqual(rows["student@example.com"]["enrollments_count"], 1)

    def test_change_role_and_deactivate(self):
        url = f"/api/admin/users/{self.student.id}/"
        r = self.client.patch(url, {"role": "teacher", "is_active": False}, format="json")
        self.assertEqual(r.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual((self.student.role, self.student.is_active), ("teacher", False))
        self.assertEqual(r.json()["formations_count"], 0)

    def test_email_cannot_be_changed(self):
        self.client.patch(f"/api/admin/users/{self.student.id}/", {"email": "other@example.com"}, format="json")
        self.student.refresh_from_db()
        self.assertEqual(self.student.email, "student@example.com")

    def test_admin_cannot_demote_deactivate_or_delete_themselves(self):
        url = f"/api/admin/users/{self.admin.id}/"
        self.assertEqual(self.client.patch(url, {"role": "student"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"is_active": False}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(url).status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.admin.pk, role="admin", is_active=True).exists())

    def test_an_admin_can_demote_another_admin_when_one_stays(self):
        other = make("admin2@example.com", "admin")
        r = self.client.patch(f"/api/admin/users/{other.id}/", {"role": "teacher"}, format="json")
        self.assertEqual(r.status_code, 200)

    def test_last_active_admin_cannot_be_demoted_deactivated_or_deleted(self):
        # The acting account is itself inactive (a stale token), so `self.admin` is the only active admin.
        ghost = make("ghost@example.com", "admin", is_active=False)
        self.client.force_authenticate(ghost)
        url = f"/api/admin/users/{self.admin.id}/"
        self.assertEqual(self.client.patch(url, {"role": "student"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"is_active": False}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(url).status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.admin.pk, role="admin", is_active=True).exists())

    def test_delete_user(self):
        self.assertEqual(self.client.delete(f"/api/admin/users/{self.student.id}/").status_code, 204)
        self.assertFalse(User.objects.filter(pk=self.student.pk).exists())

    def test_create_user_with_role_and_password_rules(self):
        body = {"email": "New@Example.com", "password": PASSWORD, "role": "admin", "first_name": "Neo"}
        r = self.client.post("/api/admin/users/", body, format="json")
        self.assertEqual(r.status_code, 201)
        created = User.objects.get(email="new@example.com")
        self.assertEqual(created.role, "admin")
        self.assertTrue(created.check_password(PASSWORD))
        self.assertNotIn("password", r.json())
        self.assertEqual(self.client.post("/api/admin/users/", body, format="json").status_code, 400)  # duplicate
        self.assertEqual(self.client.post("/api/admin/users/", {**body, "email": "b@example.com", "password": "123"}, format="json").status_code, 400)

    def test_deactivated_user_cannot_log_in(self):
        self.client.patch(f"/api/admin/users/{self.student.id}/", {"is_active": False}, format="json")
        r = APIClient().post("/api/auth/login/", {"email": "student@example.com", "password": PASSWORD}, format="json")
        self.assertEqual(r.status_code, 401)


class ReportTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.formation = Formation.objects.create(teacher=self.teacher, title="Cours douteux", is_published=True)
        self.quiz = Quiz.objects.create(owner=self.teacher, formation=self.formation, title="Quiz douteux")
        self.student_client = APIClient()
        self.student_client.force_authenticate(self.student)

    def report(self, **extra):
        body = {"target_type": "formation", "target_id": self.formation.id, "reason": "spam", **extra}
        return self.student_client.post("/api/reports/", body, format="json")

    def test_student_reports_a_formation_and_admins_are_notified(self):
        r = self.report(details="publicité")
        self.assertEqual(r.status_code, 201)
        report = Report.objects.get()
        self.assertEqual((report.reporter, report.status, report.target_title), (self.student, "open", "Cours douteux"))
        self.assertTrue(Notification.objects.filter(user=self.admin, title="Nouveau signalement").exists())
        self.assertFalse(Notification.objects.filter(user=self.student, title="Nouveau signalement").exists())

    def test_report_a_quiz_of_a_published_formation(self):
        self.assertEqual(self.report(target_type="quiz", target_id=self.quiz.id).status_code, 201)

    def test_cannot_report_duplicates_own_content_unpublished_or_unknown(self):
        self.assertEqual(self.report().status_code, 201)
        self.assertEqual(self.report().status_code, 400)
        teacher_client = APIClient()
        teacher_client.force_authenticate(self.teacher)
        own = teacher_client.post("/api/reports/", {"target_type": "formation", "target_id": self.formation.id, "reason": "spam"}, format="json")
        self.assertEqual(own.status_code, 400)
        draft = Formation.objects.create(teacher=self.teacher, title="Brouillon")
        self.assertEqual(self.report(target_id=draft.id).status_code, 400)
        self.assertEqual(self.report(target_id=99999).status_code, 400)
        self.assertEqual(self.report(reason="nope").status_code, 400)

    def test_anonymous_cannot_report(self):
        self.assertEqual(APIClient().post("/api/reports/", {}, format="json").status_code, 401)

    def test_resolve_and_unpublish_notifies_everyone(self):
        self.report()
        other = make("other@example.com")
        oc = APIClient()
        oc.force_authenticate(other)
        oc.post("/api/reports/", {"target_type": "formation", "target_id": self.formation.id, "reason": "other"}, format="json")
        first = Report.objects.filter(reporter=self.student).get()
        r = self.client.post(f"/api/admin/reports/{first.id}/resolve/", {"status": "resolved", "action": "unpublish", "note": "Spam"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.formation.refresh_from_db()
        self.assertFalse(self.formation.is_published)
        first.refresh_from_db()
        self.assertEqual((first.status, first.handled_by), ("resolved", self.admin))
        # the duplicate report about the same content is settled too
        self.assertFalse(Report.objects.filter(status="open").exists())
        self.assertTrue(Notification.objects.filter(user=self.teacher, title="Contenu dépublié", message__contains="Spam").exists())
        self.assertTrue(Notification.objects.filter(user=self.student, title="Votre signalement a été traité").exists())

    def test_resolve_with_delete_removes_content_and_report_survives(self):
        self.report()
        report = Report.objects.get()
        r = self.client.post(f"/api/admin/reports/{report.id}/resolve/", {"status": "resolved", "action": "delete"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Formation.objects.filter(pk=self.formation.pk).exists())
        data = self.client.get(f"/api/admin/reports/{report.id}/").json()
        self.assertEqual((data["target_title"], data["target_exists"]), ("Cours douteux", False))

    def test_dismiss_changes_nothing_on_the_content_and_rules(self):
        self.report()
        report = Report.objects.get()
        url = f"/api/admin/reports/{report.id}/resolve/"
        self.assertEqual(self.client.post(url, {"status": "dismissed", "action": "delete"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {"status": "dismissed"}, format="json").status_code, 200)
        self.assertTrue(Formation.objects.get(pk=self.formation.pk).is_published)
        self.assertEqual(self.client.post(url, {"status": "resolved"}, format="json").status_code, 400)  # already handled

    def test_quiz_cannot_be_unpublished(self):
        self.report(target_type="quiz", target_id=self.quiz.id)
        report = Report.objects.get()
        r = self.client.post(f"/api/admin/reports/{report.id}/resolve/", {"status": "resolved", "action": "unpublish"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertTrue(Quiz.objects.filter(pk=self.quiz.pk).exists())

    def test_list_filter_by_status(self):
        self.report()
        self.assertEqual(self.client.get("/api/admin/reports/?status=open").json()["count"], 1)
        self.assertEqual(self.client.get("/api/admin/reports/?status=resolved").json()["count"], 0)


class FormationModerationTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.formation = Formation.objects.create(teacher=self.teacher, title="Django", is_published=True)

    def test_list_includes_counts_and_open_reports(self):
        Report.objects.create(reporter=self.student, target_type="formation", target_id=self.formation.id, target_title="Django")
        row = self.client.get("/api/admin/formations/").json()["results"][0]
        self.assertEqual((row["title"], row["open_reports"], row["teacher_name"]), ("Django", 1, "Tara Prof"))
        self.assertEqual(self.client.get("/api/admin/formations/?published=0").json()["count"], 0)

    def test_unpublish_and_delete_notify_the_teacher(self):
        r = self.client.post(f"/api/admin/formations/{self.formation.id}/unpublish/", {"reason": "Hors sujet"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Formation.objects.get(pk=self.formation.pk).is_published)
        self.assertTrue(Notification.objects.filter(user=self.teacher, title="Formation dépubliée", message__contains="Hors sujet").exists())
        self.assertEqual(self.client.delete(f"/api/admin/formations/{self.formation.id}/").status_code, 204)
        self.assertTrue(Notification.objects.filter(user=self.teacher, title="Formation supprimée").exists())


class StatsAndAnnouncementTests(AdminTestCase):
    def test_stats_numbers(self):
        formation = Formation.objects.create(teacher=self.teacher, title="Django", is_published=True)
        Formation.objects.create(teacher=self.teacher, title="Brouillon")
        Enrollment.objects.create(user=self.student, formation=formation)
        quiz = Quiz.objects.create(owner=self.teacher, formation=formation, title="Q", ai_generated=True)
        QuizAttempt.objects.create(user=self.student, quiz=quiz, score=3, total=4)
        QuizAttempt.objects.create(user=self.student, quiz=quiz, score=1, total=4)
        Report.objects.create(reporter=self.student, target_type="formation", target_id=formation.id, target_title="Django")

        data = self.client.get("/api/admin/stats/").json()
        self.assertEqual(data["users"]["total"], 3)
        self.assertEqual(data["users"]["by_role"], {"student": 1, "teacher": 1, "admin": 1})
        self.assertEqual(data["users"]["new_30d"], 3)
        self.assertEqual(sum(w["count"] for w in data["users"]["signups_by_week"]), 3)
        self.assertEqual(len(data["users"]["signups_by_week"]), 8)
        self.assertEqual(data["learning"]["formations_total"], 2)
        self.assertEqual(data["learning"]["formations_published"], 1)
        self.assertEqual(data["learning"]["enrollments"], 1)
        self.assertEqual((data["learning"]["quizzes"], data["learning"]["ai_quizzes"]), (1, 1))
        self.assertEqual(data["learning"]["attempts"], 2)
        self.assertEqual(data["learning"]["success_rate"], 50)
        self.assertEqual(sum(d["count"] for d in data["learning"]["attempts_by_day"]), 2)
        self.assertEqual(len(data["learning"]["attempts_by_day"]), 14)
        self.assertEqual(data["moderation"]["open_reports"], 1)
        self.assertEqual(data["top_formations"][0]["title"], "Django")

    def test_stats_with_no_activity(self):
        data = self.client.get("/api/admin/stats/").json()
        self.assertIsNone(data["learning"]["success_rate"])
        self.assertEqual(data["top_formations"], [])

    def test_announcement_to_one_role_only(self):
        r = self.client.post("/api/admin/announcements/", {"title": "Maintenance", "message": "Ce soir", "audience": "student", "link": "/dashboard"}, format="json")
        self.assertEqual((r.status_code, r.json()["sent"]), (201, 1))
        note = Notification.objects.get(title="Maintenance")
        self.assertEqual((note.user, note.kind), (self.student, "announcement"))

    def test_announcement_ignores_inactive_users_and_external_links(self):
        self.student.is_active = False
        self.student.save()
        r = self.client.post("/api/admin/announcements/", {"title": "Hello", "link": "https://evil.example"}, format="json")
        self.assertEqual(r.json()["sent"], 2)  # admin + teacher
        self.assertEqual(Notification.objects.get(title="Hello", user=self.teacher).link, "")
        self.assertEqual(self.client.post("/api/admin/announcements/", {"title": ""}, format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/admin/announcements/", {"title": "x", "audience": "ghosts"}, format="json").status_code, 400)
