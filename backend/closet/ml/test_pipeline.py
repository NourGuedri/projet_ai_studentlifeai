"""Tests du pipeline ML classique sur un mini dataset synthétique (aucun téléchargement nécessaire).
Ignorés automatiquement si scikit-learn / scikit-image ne sont pas installés (dépendances facultatives)."""
import csv
import io
import json
import random
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from django.test import SimpleTestCase
from PIL import Image, ImageDraw, ImageFilter

try:
    import joblib, skimage, sklearn  # noqa: F401, E401
    from . import feature_extraction as fe, predict, train
    HAS_ML = True
except ImportError:  # pragma: no cover
    HAS_ML = False

COLORS = {"Black": (25, 25, 25), "Red": (205, 35, 35), "Blue": (35, 70, 200), "Green": (40, 150, 60)}
TYPES = ["Tshirts", "Jeans", "Sports Shoes"]


def draw_item(item_type, rgb, rng, size=(60, 80)):
    img = Image.new("RGB", size, (245, 245, 245))
    d = ImageDraw.Draw(img)
    color = tuple(max(0, min(255, c + rng.randint(-12, 12))) for c in rgb)
    j = rng.randint(-3, 3)
    if item_type == "Tshirts":
        d.rectangle([17 + j, 18, 43 + j, 62], fill=color)
        d.rectangle([6 + j, 18, 54 + j, 32], fill=color)
    elif item_type == "Jeans":
        d.rectangle([16 + j, 8, 29 + j, 72], fill=color)
        d.rectangle([31 + j, 8, 44 + j, 72], fill=color)
        d.rectangle([16 + j, 8, 44 + j, 22], fill=color)
    else:
        d.ellipse([4 + j, 38, 56 + j, 62], fill=color)
    return img.filter(ImageFilter.GaussianBlur(0.6))


def make_dataset(root: Path, n=360, seed=0):
    rng = random.Random(seed)
    (root / "images").mkdir(parents=True)
    rows = []
    for i in range(n):
        item_type, color = rng.choice(TYPES), rng.choice(list(COLORS))
        usage = "Sports" if item_type == "Sports Shoes" else rng.choice(["Casual", "Formal"])
        draw_item(item_type, COLORS[color], rng).save(root / "images" / f"{1000 + i}.jpg")
        rows.append((1000 + i, item_type, usage, color))
    with open(root / "styles.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "articleType", "usage", "baseColour"])
        writer.writerows(rows)


def png_bytes(img):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf


@unittest.skipUnless(HAS_ML, "scikit-learn / scikit-image non installés")
class FeatureExtractionTests(SimpleTestCase):
    def test_groups_cover_the_whole_vector_without_overlap(self):
        covered = np.concatenate([np.arange(fe.N_FEATURES)[s] for s in fe.FEATURE_GROUPS.values()])
        self.assertEqual(sorted(covered), list(range(fe.N_FEATURES)))

    def test_vector_has_expected_size_and_is_finite_and_deterministic(self):
        img = draw_item("Jeans", COLORS["Blue"], random.Random(1))
        a, b = fe.extract_features(png_bytes(img)), fe.extract_features(png_bytes(img))
        self.assertEqual(a.shape, (fe.N_FEATURES,))
        self.assertTrue(np.isfinite(a).all())
        np.testing.assert_array_equal(a, b)

    def test_handles_large_photos_transparency_and_blank_images(self):
        big = draw_item("Tshirts", COLORS["Red"], random.Random(2), size=(1200, 1600))
        rgba = draw_item("Tshirts", COLORS["Red"], random.Random(2)).convert("RGBA")
        blank = Image.new("RGB", (80, 60), (255, 255, 255))
        for image in (big, rgba, blank):
            self.assertEqual(fe.extract_features(png_bytes(image)).shape, (fe.N_FEATURES,))

    def test_color_features_ignore_the_background(self):
        # même vêtement noir sur fond blanc ou fond gris clair : la couleur mesurée reste « noire »
        for bg in ((255, 255, 255), (225, 225, 225)):
            img = Image.new("RGB", (60, 80), bg)
            ImageDraw.Draw(img).rectangle([15, 15, 45, 65], fill=(20, 20, 20))
            color = fe.extract_features(png_bytes(img))[fe.FEATURE_GROUPS["color"]]
            self.assertGreater(color[13], 0.9)        # part de pixels noirs (V < 0.2)


@unittest.skipUnless(HAS_ML, "scikit-learn / scikit-image non installés")
class TrainPredictTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = Path(tempfile.mkdtemp())
        make_dataset(cls.tmp / "data")
        args = train.parse_args(["--data", str(cls.tmp / "data"), "--out", str(cls.tmp / "models"),
                                 "--models", "SVC", "KNN", "DecisionTree", "RandomForest",
                                 "--cv-samples", "200", "--min-color-count", "5", "--jobs", "1"])
        with patch("builtins.print"):
            train.main(args)
        cls.model_path = cls.tmp / "models" / "clothing_classifier.joblib"
        cls.metrics = json.loads((cls.tmp / "models" / "metrics.json").read_text())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        super().tearDownClass()

    def test_outputs_are_written(self):
        self.assertTrue(self.model_path.exists())
        self.assertEqual(set(self.metrics["targets"]), {"type", "color", "style"})

    def test_cv_compares_all_requested_models_and_picks_the_best(self):
        for target in self.metrics["targets"].values():
            self.assertEqual(set(target["cv"]), {"SVC", "KNN", "DecisionTree", "RandomForest"})
            best = max(target["cv"], key=lambda n: target["cv"][n]["f1_macro"])
            self.assertEqual(target["best"], best)

    def test_test_scores_are_good_on_easy_synthetic_data(self):
        self.assertGreater(self.metrics["targets"]["color"]["test"]["accuracy"], 0.9)
        self.assertGreater(self.metrics["targets"]["type"]["test"]["accuracy"], 0.85)
        matrix = np.array(self.metrics["targets"]["type"]["test"]["confusion_matrix"])
        self.assertEqual(matrix.sum(), self.metrics["n_test"])

    def test_predict_image_returns_the_api_format(self):
        img = draw_item("Jeans", COLORS["Blue"], random.Random(99))
        result = predict.predict_image(png_bytes(img), model_path=self.model_path)
        self.assertEqual({"item_type", "category", "color", "style", "confidence", "color_confidence",
                          "style_confidence", "alternatives"}, set(result))
        self.assertEqual((result["item_type"], result["category"], result["color"]), ("Jean", "Bas", "Bleu"))
        self.assertEqual(len(result["alternatives"]), 3)
        self.assertAlmostEqual(sum(a["confidence"] for a in result["alternatives"]), 1.0, delta=0.01)

    def test_django_classifier_uses_the_new_model(self):
        from closet import classifier
        img = draw_item("Tshirts", COLORS["Red"], random.Random(5))
        with patch.object(predict, "MODEL_PATH", self.model_path):
            result = classifier.analyze(png_bytes(img))
        self.assertEqual((result["item_type"], result["color"]), ("T-shirt", "Rouge"))
        self.assertIn("uncertain", result)

    def test_xgboost_runs_when_installed(self):
        if train.XGBClassifier is None:
            self.skipTest("xgboost non installé")
        rng = np.random.RandomState(0)
        X, y = rng.rand(120, 8), rng.randint(0, 3, 120)
        model = train.fit(train.make_model("XGBoost", n_jobs=1), "XGBoost", X, y)
        self.assertEqual(model.predict(X).shape, (120,))
