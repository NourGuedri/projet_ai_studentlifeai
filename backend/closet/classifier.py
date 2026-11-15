"""Pont entre Django et le modèle ML. scikit-learn est importé seulement ici, à la demande :
sans scikit-learn ou sans modèle entraîné, le reste de l'application (ajout manuel, tenues) fonctionne."""

import importlib

LOW_CONFIDENCE = 0.6


class ClassifierUnavailable(Exception):
    pass


def analyze(file) -> dict:
    try:
        predict = importlib.import_module(f"{__package__}.ml.predict")
    except ImportError as exc:
        raise ClassifierUnavailable(
            "La détection automatique n'est pas installée (scikit-learn manquant). "
            "Renseignez le vêtement manuellement.") from exc
    if not predict.model_available():
        raise ClassifierUnavailable(
            "Le modèle de détection n'est pas encore entraîné. Renseignez le vêtement manuellement.")
    try:
        result = predict.predict_image(file)
    except Exception as exc:  # image illisible, poids corrompus...
        raise ClassifierUnavailable(f"Analyse impossible : {exc}") from exc
    result["uncertain"] = result["confidence"] < LOW_CONFIDENCE
    return result
