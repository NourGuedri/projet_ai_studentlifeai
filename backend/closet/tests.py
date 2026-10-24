import io
import shutil
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from PIL import Image
from rest_framework.test import APITestCase

from . import classifier, outfit
from .ml.labels import TYPE_TO_CATEGORY
from profiles.models import StudentProfile

from .models import ClothingItem
from .weather import WeatherError

MEDIA_ROOT = tempfile.mkdtemp()


def png(color=(255, 255, 255)):
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), color).save(buf, "PNG")
    return SimpleUploadedFile("photo.png", buf.getvalue(), content_type="image/png")


def weather(feels=20, rain=False):
    return {"city": "Tunis", "country": "Tunisie", "temp": feels, "feels_like": feels,
            "rain": rain, "description": "Test", "code": 0}


def fake(item_type, color, style="Casual"):
    return SimpleNamespace(item_type=item_type, color=color, style=style, category=TYPE_TO_CATEGORY[item_type])


WARDROBE = [fake("T-shirt", "Blanc"), fake("Jean", "Bleu"), fake("Short", "Beige"), fake("Baskets", "Blanc"),
            fake("Sandales", "Noir"), fake("Veste", "Noir"), fake("Pull", "Gris")]


# ------------------------------------------------------------------ moteur de tenue (sans base de données)
class OutfitEngineTests(SimpleTestCase):
    def types(self, result):
        return {i.item_type for i in result["items"]}

    def test_rain_adds_jacket_and_closed_shoes(self):
        for seed in range(15):
            result = outfit.recommend(WARDROBE, weather(feels=20, rain=True), seed=seed)
            self.assertIn("Veste", self.types(result))
            self.assertNotIn("Sandales", self.types(result))
            self.assertIn("Il pleut : pensez au parapluie.", result["advice"])

    def test_cold_layers_knit_and_jacket_without_shorts(self):
        for seed in range(15):
            result = outfit.recommend(WARDROBE, weather(feels=5), seed=seed)
            self.assertTrue({"Pull", "Veste"} <= self.types(result))
            self.assertNotIn("Short", self.types(result))

    def test_hot_day_has_no_layer(self):
        result = outfit.recommend(WARDROBE, weather(feels=30), seed=1)
        self.assertFalse(self.types(result) & {"Pull", "Veste"})

    def test_same_seed_gives_same_outfit(self):
        a = outfit.recommend(WARDROBE, weather(), seed=7)["items"]
        b = outfit.recommend(WARDROBE, weather(), seed=7)["items"]
        self.assertEqual(a, b)

    def test_style_filter_is_preferred(self):
        wardrobe = WARDROBE + [fake("Chemise", "Blanc", "Formel"), fake("Pantalon", "Noir", "Formel")]
        result = outfit.recommend(wardrobe, weather(feels=20), style="Formel", seed=3)
        formal = {i.item_type for i in result["items"] if i.style == "Formel"}
        self.assertEqual(formal, {"Chemise", "Pantalon"})

    def test_missing_pieces_are_reported(self):
        result = outfit.recommend([], weather(feels=5, rain=True))
        self.assertEqual(result["items"], [])
        self.assertTrue(result["missing"])

    def test_missing_jacket_is_reported_when_raining(self):
        result = outfit.recommend([fake("T-shirt", "Blanc"), fake("Jean", "Bleu"), fake("Baskets", "Blanc")],
                                  weather(feels=20, rain=True))
        self.assertTrue(any("veste" in m for m in result["missing"]))


# ------------------------------------------------------------------ API
@override_settings(MEDIA_ROOT=MEDIA_ROOT, PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ClosetApiTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(email="etudiant@example.com", password="password123")
        self.other = user_model.objects.create_user(email="autre@example.com", password="password123")
        self.client.force_authenticate(self.user)

    def make(self, owner=None, **kwargs):
        data = dict(item_type="T-shirt", category="Haut", color="Blanc", style="Casual")
        data.update(kwargs)
        return ClothingItem.objects.create(owner=owner or self.user, image=png(), **data)

    def create(self, **fields):
        body = {"image": png(), "item_type": "T-shirt", "color": "Blanc", "style": "Casual"}
        body.update(fields)
        return self.client.post("/api/closet/items/", body, format="multipart")

    def test_authentication_is_required(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/closet/items/").status_code, 401)

    def test_create_derives_category_from_type(self):
        response = self.create(item_type="Jean", color="Bleu")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["category"], "Bas")
        self.assertEqual(ClothingItem.objects.get().owner, self.user)

    def test_create_rejects_unknown_values_and_non_images(self):
        self.assertEqual(self.create(item_type="Cape").status_code, 400)
        self.assertEqual(self.create(color="Licorne").status_code, 400)
        bad = SimpleUploadedFile("x.png", b"pas une image", content_type="image/png")
        self.assertEqual(self.create(image=bad).status_code, 400)

    def test_list_only_contains_own_items_and_filters_by_category(self):
        mine = self.make()
        self.make(item_type="Jean", category="Bas")
        self.make(owner=self.other)
        ids = [i["id"] for i in self.client.get("/api/closet/items/").data]
        self.assertEqual(len(ids), 2)
        only_tops = self.client.get("/api/closet/items/?category=Haut").data
        self.assertEqual([i["id"] for i in only_tops], [mine.id])

    def test_other_users_items_are_not_accessible(self):
        foreign = self.make(owner=self.other)
        self.assertEqual(self.client.get(f"/api/closet/items/{foreign.id}/").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/closet/items/{foreign.id}/").status_code, 404)
        self.assertTrue(ClothingItem.objects.filter(id=foreign.id).exists())

    def test_student_can_correct_ai_prediction(self):
        item = self.make(ai_detected=True, ai_confidence=0.5)
        response = self.client.patch(f"/api/closet/items/{item.id}/", {"item_type": "Chemise", "color": "Rose"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        item.refresh_from_db()
        self.assertEqual((item.item_type, item.category, item.color), ("Chemise", "Haut", "Rose"))

    def test_delete_removes_item_and_file(self):
        item = self.make()
        path = item.image.path
        self.assertEqual(self.client.delete(f"/api/closet/items/{item.id}/").status_code, 204)
        self.assertFalse(ClothingItem.objects.exists())
        import os
        self.assertFalse(os.path.exists(path))

    def test_options_endpoint(self):
        data = self.client.get("/api/closet/items/options/").data
        self.assertIn("Jean", data["types"]["Bas"])
        self.assertIn("Blanc", data["colors"])
        self.assertIn("Formel", data["styles"])

    # ---- détection automatique
    def test_analyze_returns_prediction_without_saving(self):
        prediction = {"item_type": "T-shirt", "category": "Haut", "color": "Blanc", "style": "Casual",
                      "confidence": 0.93, "color_confidence": 0.9, "uncertain": False}
        with patch("closet.views.classifier.analyze", return_value=prediction):
            response = self.client.post("/api/closet/items/analyze/", {"image": png()}, format="multipart")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["item_type"], "T-shirt")
        self.assertFalse(ClothingItem.objects.exists())

    def test_analyze_503_when_model_unavailable(self):
        with patch("closet.views.classifier.analyze", side_effect=classifier.ClassifierUnavailable("Pas de modèle.")):
            response = self.client.post("/api/closet/items/analyze/", {"image": png()}, format="multipart")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["detail"], "Pas de modèle.")

    def test_classifier_reports_missing_model(self):
        fake_predict = SimpleNamespace(model_available=lambda: False)
        with patch.dict(sys.modules, {"closet.ml.predict": fake_predict}):
            with self.assertRaisesMessage(classifier.ClassifierUnavailable, "pas encore entraîné"):
                classifier.analyze(png())

    def test_classifier_reports_missing_pytorch(self):
        with patch.dict(sys.modules, {"closet.ml.predict": None}):   # simule « import torch impossible »
            with self.assertRaisesMessage(classifier.ClassifierUnavailable, "PyTorch manquant"):
                classifier.analyze(png())

    def test_classifier_flags_low_confidence(self):
        low = {"item_type": "Top", "category": "Haut", "color": "Noir", "style": "Casual",
               "confidence": 0.4, "color_confidence": 0.9}
        fake_predict = SimpleNamespace(model_available=lambda: True, predict_image=lambda f: dict(low))
        with patch.dict(sys.modules, {"closet.ml.predict": fake_predict}):
            self.assertTrue(classifier.analyze(png())["uncertain"])

    # ---- tenue du jour
    def test_outfit_uses_weather_and_wardrobe(self):
        for t, c, color in [("T-shirt", "Haut", "Blanc"), ("Jean", "Bas", "Bleu"),
                            ("Baskets", "Chaussures", "Blanc"), ("Veste", "Couche", "Noir")]:
            self.make(item_type=t, category=c, color=color)
        self.make(owner=self.other, item_type="Pull", category="Couche")
        with patch("closet.views.get_weather", return_value=weather(feels=14, rain=True)):
            response = self.client.get("/api/closet/items/outfit/?city=Tunis&seed=1")
        self.assertEqual(response.status_code, 200, response.data)
        types = {i["item_type"] for i in response.data["items"]}
        self.assertEqual(types, {"T-shirt", "Jean", "Baskets", "Veste"})
        self.assertTrue(response.data["generated"])
        self.assertEqual(response.data["weather"]["city"], "Tunis")

    def test_outfit_defaults_to_profile_city(self):
        StudentProfile.objects.create(user=self.user, city="Sfax")
        with patch("closet.views.get_weather", return_value=weather()) as mocked:
            self.client.get("/api/closet/items/outfit/")
        mocked.assert_called_once_with("Sfax")

    def test_outfit_weather_error_is_502(self):
        with patch("closet.views.get_weather", side_effect=WeatherError("Ville introuvable : « zzz ».")):
            response = self.client.get("/api/closet/items/outfit/?city=zzz")
        self.assertEqual(response.status_code, 502)

    def test_outfit_rejects_unknown_style(self):
        with patch("closet.views.get_weather", return_value=weather()):
            self.assertEqual(self.client.get("/api/closet/items/outfit/?style=Gothique").status_code, 400)
