"""Pont entre Django et les modèles ML du transport (même principe que closet/classifier.py).

Les bibliothèques ML (pandas, scikit-learn, xgboost, imbalanced-learn) ne sont importées
qu'ici, à la demande : sans elles ou sans modèles entraînés, les trajets fonctionnent quand même.
"""

import importlib

from django.conf import settings


class PredictorUnavailable(Exception):
    pass


def _module():
    try:
        return importlib.import_module(f"{__package__}.ml.predict")
    except ImportError as exc:
        raise PredictorUnavailable(
            "Prédiction indisponible : bibliothèques ML manquantes "
            "(pandas, scikit-learn, xgboost, imbalanced-learn).") from exc


def estimate(mode, incident, when):
    """Retard estimé (modèle A) + probabilité de retard long (modèle B)."""
    predict = _module()
    threshold = getattr(settings, "TRANSPORT_ALERT_THRESHOLD", None)
    try:
        return predict.predict_delay(mode, incident, when, threshold=threshold)
    except FileNotFoundError as exc:
        raise PredictorUnavailable(
            "Les modèles ne sont pas encore entraînés (lancer transport/ml/train.py).") from exc
    except ValueError as exc:
        raise PredictorUnavailable(str(exc)) from exc


def model_card():
    """Résumé des performances des modèles, affiché sur la page Transport."""
    try:
        metrics = _module().load()[2]
    except (PredictorUnavailable, FileNotFoundError):
        return None
    reg = metrics["regression"]["kfold_5"]
    auc = metrics["classification"]["kfold_5"]["AUC"]
    clf = metrics["classification"]["test_with_threshold"]   # scores au seuil retenu (étape 6)
    return {
        "dataset": metrics["dataset"],
        "n_rows": metrics["n_rows"],
        "long_delay_minutes": metrics["long_delay_minutes"],
        "threshold": getattr(settings, "TRANSPORT_ALERT_THRESHOLD", None) or metrics["decision_threshold"],
        "regression": {"model": metrics["regression"]["model"],
                       "mae": reg["MAE"], "r2": reg["R²"]},
        "classification": {"model": metrics["classification"]["model"],
                           "f1": clf["F1"], "recall": clf["Recall"],
                           "precision": clf["Precision"], "auc": auc},
    }