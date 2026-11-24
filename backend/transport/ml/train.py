# train.py — Entraînement final des modèles choisis à l'étape 6 + sauvegarde (joblib)
# A : XGBoost Regressor (minutes de retard)
# B : XGBoost Classifier + SMOTE (retard long > 15 min), seuil optimisé à l'étape 6
# Source : TTC Delay Data 2024, City of Toronto Open Data.
# Contains information licensed under the Open Government Licence – Toronto.

# %% [1] Imports et chemins
from pathlib import Path
from datetime import date
import json
import pandas as pd
import joblib
import sklearn
import xgboost
import imblearn
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline as SkPipeline
from imblearn.pipeline import Pipeline
from imblearn.over_sampling import SMOTE
from xgboost import XGBRegressor, XGBClassifier

try:
    BASE = Path(__file__).resolve().parent
except NameError:                      # exécution cellule par cellule
    BASE = Path.cwd()
DATA_DIR = BASE / "dataset"
MODELS_DIR = BASE / "models"
MODELS_DIR.mkdir(exist_ok=True)

CAT = ["mode", "incident_grp", "day"]
NUM = ["hour", "month"]
LONG_DELAY_MIN = 15


def make_pre():
    return ColumnTransformer(
        [("cat", OneHotEncoder(handle_unknown="ignore"), CAT),
         ("num", StandardScaler(), NUM)],
        sparse_threshold=0,
    )


# %% [2] Données + résultats de l'évaluation (étape 6)
data = pd.read_csv(DATA_DIR / "transport_features.csv")
X = data[CAT + NUM]

with open(MODELS_DIR / "evaluation.json", encoding="utf-8") as f:
    evaluation = json.load(f)

reg_eval = next(r for r in evaluation["regression_kfold"] if r["modèle"] == "XGBoost")
clf_eval = next(r for r in evaluation["classification_kfold"] if r["modèle"] == "XGBoost")
thr_eval = next(r for r in evaluation["thresholds"]
                if r["modèle"] == "XGBoost" and r["seuil"] == "optimisé")
DECISION_THRESHOLD = round(thr_eval["valeur"], 2)
print("Seuil de décision retenu :", DECISION_THRESHOLD)

# %% [3] Modèle A : régression (minutes de retard)
regressor = SkPipeline([
    ("pre", make_pre()),
    ("model", XGBRegressor(n_estimators=300, max_depth=6, learning_rate=0.1, random_state=42)),
])
regressor.fit(X, data["min_delay"])
joblib.dump(regressor, MODELS_DIR / "delay_regressor.joblib")
print("Modèle A enregistré : delay_regressor.joblib")

# %% [4] Modèle B : classification (retard long), SMOTE dans le pipeline
classifier = Pipeline([
    ("pre", make_pre()),
    ("smote", SMOTE(random_state=42)),
    ("model", XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.1,
                            eval_metric="logloss", random_state=42)),
])
classifier.fit(X, data["long_delay"])
joblib.dump(classifier, MODELS_DIR / "delay_classifier.joblib")
print("Modèle B enregistré : delay_classifier.joblib")

# %% [5] Fiche des modèles (metrics.json)
metrics = {
    "trained_on": date.today().isoformat(),
    "dataset": "TTC Delay Data 2024 — City of Toronto Open Data "
               "(Open Government Licence – Toronto)",
    "n_rows": int(len(data)),
    "features": CAT + NUM,
    "long_delay_minutes": LONG_DELAY_MIN,
    "decision_threshold": DECISION_THRESHOLD,
    "regression": {"model": "XGBoost Regressor", "kfold_5": reg_eval},
    "classification": {"model": "XGBoost Classifier + SMOTE", "kfold_5": clf_eval,
                       "test_with_threshold": thr_eval},
    "categories": {col: sorted(data[col].unique().tolist()) for col in CAT},
    "versions": {"scikit-learn": sklearn.__version__, "xgboost": xgboost.__version__,
                 "imbalanced-learn": imblearn.__version__},
}
with open(MODELS_DIR / "metrics.json", "w", encoding="utf-8") as f:
    json.dump(metrics, f, ensure_ascii=False, indent=2)
print("Fiche enregistrée : metrics.json")

# %% [6] Vérification : rechargement + 3 prédictions
reg = joblib.load(MODELS_DIR / "delay_regressor.joblib")
clf = joblib.load(MODELS_DIR / "delay_classifier.joblib")

examples = pd.DataFrame([
    {"mode": "bus", "incident_grp": "DIVERSION", "day": "MONDAY", "hour": 8, "month": 11},
    {"mode": "tramway", "incident_grp": "MECHANICAL", "day": "FRIDAY", "hour": 17, "month": 3},
    {"mode": "metro", "incident_grp": "MUIS", "day": "SUNDAY", "hour": 14, "month": 7},
])
examples["retard estimé (min)"] = reg.predict(examples[CAT + NUM]).round(1)
examples["proba retard long"] = clf.predict_proba(examples[CAT + NUM])[:, 1].round(2)
examples["notification"] = examples["proba retard long"] >= DECISION_THRESHOLD
print("\n", examples.to_string(index=False))