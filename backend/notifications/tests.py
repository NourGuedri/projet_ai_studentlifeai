from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from learning.models import Enrollment, Formation

from .models import Notification
from .services import notify, notify_many

User = get_user_model()


class NotificationApiTests(TestCase):
    def setUp(self):
        self.ana = User.objects.create_user(email="ana@example.com", password="x", first_name="Ana")
        self.bob = User.objects.create_user(email="bob@example.com", password="x")
        Notification.objects.all().delete()  # drop the welcome messages
        self.client = APIClient()
        self.client.force_authenticate(self.ana)

    def test_list_only_my_notifications_newest_first(self):
        first = notify(self.ana, "Première")
        second = notify(self.ana, "Seconde", "détail", "/profile", "success")
        notify(self.bob, "Pour Bob")
        rows = self.client.get("/api/notifications/").json()
        self.assertEqual([r["title"] for r in rows], ["Seconde", "Première"])
        self.assertEqual(rows[0]["link"], "/profile")
        self.assertIn(second.id, [r["id"] for r in rows])
        self.assertIn(first.id, [r["id"] for r in rows])

    def test_unread_count_filter_and_mark_read(self):
        a, b = notify(self.ana, "A"), notify(self.ana, "B")
        self.assertEqual(self.client.get("/api/notifications/unread-count/").json(), {"count": 2})
        self.assertEqual(self.client.post(f"/api/notifications/{a.id}/read/").status_code, 200)
        self.assertEqual(self.client.get("/api/notifications/unread-count/").json(), {"count": 1})
        self.assertEqual([r["title"] for r in self.client.get("/api/notifications/?unread=1").json()], ["B"])
        self.assertEqual(self.client.post("/api/notifications/read-all/").json(), {"updated": 1})
        self.assertEqual(self.client.get("/api/notifications/unread-count/").json(), {"count": 0})
        b.refresh_from_db()
        self.assertTrue(b.is_read)

    def test_cannot_touch_someone_elses_notification(self):
        theirs = notify(self.bob, "Secret")
        self.assertEqual(self.client.post(f"/api/notifications/{theirs.id}/read/").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/notifications/{theirs.id}/").status_code, 404)
        theirs.refresh_from_db()
        self.assertFalse(theirs.is_read)

    def test_delete_my_notification(self):
        mine = notify(self.ana, "À supprimer")
        self.assertEqual(self.client.delete(f"/api/notifications/{mine.id}/").status_code, 204)
        self.assertFalse(Notification.objects.filter(pk=mine.pk).exists())

    def test_anonymous_is_refused(self):
        self.assertEqual(APIClient().get("/api/notifications/").status_code, 401)

    def test_read_only_api_cannot_create(self):
        self.assertEqual(self.client.post("/api/notifications/", {"title": "x"}, format="json").status_code, 405)


class ServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="u@example.com", password="x")

    def test_links_must_be_internal_and_kind_valid(self):
        self.assertEqual(notify(self.user, "t", link="/planning").link, "/planning")
        for bad in ("https://evil.example", "//evil.example", "javascript:alert(1)", ""):
            self.assertEqual(notify(self.user, "t", link=bad).link, "")
        self.assertEqual(notify(self.user, "t", kind="weird").kind, "info")

    def test_title_is_truncated(self):
        self.assertEqual(len(notify(self.user, "x" * 500).title), 150)

    def test_notify_many(self):
        other = User.objects.create_user(email="o@example.com", password="x")
        self.assertEqual(notify_many([self.user, other], "Annonce"), 2)
        self.assertEqual(Notification.objects.filter(title="Annonce").count(), 2)


class SignalTests(TestCase):
    def test_welcome_message_on_registration(self):
        user = User.objects.create_user(email="new@example.com", password="x")
        self.assertEqual(Notification.objects.filter(user=user).count(), 1)
        user.first_name = "Changed"
        user.save()
        self.assertEqual(Notification.objects.filter(user=user).count(), 1)  # only on creation

    def test_teacher_is_told_about_new_enrollment(self):
        teacher = User.objects.create_user(email="t@example.com", password="x", role="teacher")
        student = User.objects.create_user(email="s@example.com", password="x", first_name="Sam", last_name="Lee")
        formation = Formation.objects.create(teacher=teacher, title="Python", is_published=True)
        Enrollment.objects.create(user=student, formation=formation)
        note = Notification.objects.get(user=teacher, title="Nouvelle inscription")
        self.assertIn("Sam Lee", note.message)
        self.assertEqual(note.link, f"/learning/formations/{formation.id}")
