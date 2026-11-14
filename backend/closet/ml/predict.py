"""Prédiction à partir d'une photo (même extraction de caractéristiques qu'à l'entraînement).

    python predict.py photo.jpg                      # en ligne de commande
    from closet.ml.predict import predict_image      # depuis Django
"""
from pathlib import Path

import joblib
import numpy as np

try:
    from .feature_extraction import FEATURE_GROUPS, FEATURE_VERSION, N_FEATURES, extract_features
    from .labels import ARTICLE_FR, ARTICLE_TO_CATEGORY, COLOR_FR, STYLE_FR
except ImportError:
    from feature_extraction import FEATURE_GROUPS, FEATURE_VERSION, N_FEATURES, extract_features
    from labels import ARTICLE_FR, ARTICLE_TO_CATEGORY, COLOR_FR, STYLE_FR

MODEL_PATH = Path(__file__).parent / "models" / "clothing_classifier.joblib"
_cache = {}


def model_available() -> bool:
    return MODEL_PATH.exists()


def load_bundle(path=None):
    path = Path(path or MODEL_PATH)
    key = str(path)
    if key not in _cache:
        if not path.exists():
            raise FileNotFoundError(f"Modèle introuvable : {path}. Lancez d'abord : python train.py --data dataset")
        bundle = joblib.load(path)
        if bundle.get("version") != FEATURE_VERSION:
            raise RuntimeError("Modèle entraîné avec une autre version de l'extraction : relancez train.py.")
        _cache[key] = bundle
    return _cache[key]


def _probabilities(pipeline, x):
    if hasattr(pipeline, "predict_proba"):
        return pipeline.predict_proba(x)[0]
    scores = np.asarray(pipeline.decision_function(x))[0]      # modèle sans probabilités : softmax des scores
    e = np.exp(scores - scores.max())
    return e / e.sum()


def _columns(groups):
    return np.concatenate([np.arange(N_FEATURES)[FEATURE_GROUPS[g]] for g in groups])


def predict_image(file, model_path=None) -> dict:
    """file : chemin ou fichier ouvert. Retourne type / catégorie / couleur / style (en français) + confiances."""
    bundle = load_bundle(model_path)
    vector = extract_features(file).reshape(1, -1)
    out = {}
    for target, entry in bundle["targets"].items():
        probs = _probabilities(entry["pipeline"], vector[:, _columns(entry["groups"])])
        out[target] = (entry["classes"], probs)

    classes, probs = out["type"]
    article = classes[int(probs.argmax())]
    top = np.argsort(probs)[::-1][:3]
    color_classes, color_probs = out["color"]
    style_classes, style_probs = out["style"]
    color, style = color_classes[int(color_probs.argmax())], style_classes[int(style_probs.argmax())]
    return {
        "item_type": ARTICLE_FR.get(article, article),
        "category": ARTICLE_TO_CATEGORY[article],
        "color": COLOR_FR.get(color, color),
        "style": STYLE_FR.get(style, style),
        "confidence": round(float(probs.max()), 3),                  # confiance sur le type de vêtement
        "color_confidence": round(float(color_probs.max()), 3),
        "style_confidence": round(float(style_probs.max()), 3),
        "alternatives": [{"item_type": ARTICLE_FR.get(classes[i], classes[i]), "confidence": round(float(probs[i]), 3)}
                         for i in top],
    }


if __name__ == "__main__":
    import argparse
    import json
    parser = argparse.ArgumentParser(description="Reconnaît un vêtement à partir d'une photo.")
    parser.add_argument("photo", help="chemin de l'image (un seul vêtement, fond uni)")
    parser.add_argument("--model", default=None, help="fichier .joblib (défaut : models/clothing_classifier.joblib)")
    args = parser.parse_args()
    print(json.dumps(predict_image(args.photo, args.model), ensure_ascii=False, indent=2))
