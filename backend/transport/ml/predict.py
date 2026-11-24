# predict.py — Chargement des modèles et prédiction du retard
# Utilisé par Django via transport/predictor.py (import paresseux).
# Les modèles sont produits par train.py (dossier models/).

from datetime import datetime
from functools import lru_cache
from pathlib import Path
import json

import joblib
import pandas as pd

MODELS_DIR = Path(__file__).resolve().parent / "models"
FEATURES = ["mode", "incident_grp", "day", "hour", "month"]
DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]


@lru_cache(maxsize=1)
def load():
    """Charge les deux modèles et leur fiche une seule fois."""
    regressor = joblib.load(MODELS_DIR / "delay_regressor.joblib")
    classifier = joblib.load(MODELS_DIR / "delay_classifier.joblib")
    with open(MODELS_DIR / "metrics.json", encoding="utf-8") as f:
        metrics = json.load(f)
    return regressor, classifier, metrics


def categories():
    """Valeurs acceptées par les modèles (pour les formulaires du frontend)."""
    return load()[2]["categories"]


def predict_delay(mode, incident, when=None, threshold=None):
    """
    mode     : "bus", "metro" ou "tramway"
    incident : type d'incident (inconnu -> "AUTRE")
    when     : datetime de l'incident (par défaut : maintenant)
    threshold: seuil de décision (par défaut : celui de metrics.json)
    """
    regressor, classifier, metrics = load()
    cats = metrics["categories"]

    mode = str(mode).strip().lower()
    if mode not in cats["mode"]:
        raise ValueError(f"Moyen de transport non pris en charge : {mode}")

    incident = str(incident).strip().upper()
    if incident not in cats["incident_grp"]:
        incident = "AUTRE"

    when = when or datetime.now()
    row = pd.DataFrame([{
        "mode": mode,
        "incident_grp": incident,
        "day": DAYS[when.weekday()],
        "hour": when.hour,
        "month": when.month,
    }])[FEATURES]

    minutes = max(0.0, float(regressor.predict(row)[0]))       # un retard n'est jamais négatif
    proba = float(classifier.predict_proba(row)[0, 1])
    thr = metrics["decision_threshold"] if threshold is None else float(threshold)

    return {
        "mode": mode,
        "incident": incident,
        "estimated_delay_min": round(minutes),
        "long_delay_probability": round(proba, 2),
        "is_long_delay": proba >= thr,
        "threshold": thr,
    }


if __name__ == "__main__":
    print("Catégories :", categories())
    print(predict_delay("bus", "Diversion", datetime(2026, 11, 23, 8, 0)))
    print(predict_delay("metro", "MUIS", datetime(2026, 7, 12, 14, 0)))
    print(predict_delay("tramway", "incident inconnu", datetime(2026, 3, 6, 17, 0)))
    try:
        predict_delay("voiture", "MECHANICAL")
    except ValueError as e:
        print("Erreur attendue :", e)