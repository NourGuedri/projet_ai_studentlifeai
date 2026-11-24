# 06_evaluation.py — Étape 6 du ML Pipeline : Evaluation
# 1) K-fold (5 folds) pour la régression et la classification
# 2) Choix du seuil de décision sur le train uniquement, puis vérification sur le test
# 3) Taille des modèles (pour le déploiement dans Django)

# %% [1] Imports et chargement
from pathlib import Path
import io
import json
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import joblib
from sklearn.base import clone
from sklearn.model_selection import (KFold, StratifiedKFold, cross_validate,
                                     cross_val_predict, train_test_split)
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline as SkPipeline
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.metrics import precision_recall_curve, precision_score, recall_score, f1_score
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

data = pd.read_csv(DATA_DIR / "transport_features.csv")
CAT = ["mode", "incident_grp", "day"]
NUM = ["hour", "month"]
X = data[CAT + NUM]
y_reg = data["min_delay"]
y_clf = data["long_delay"]


def make_pre():
    return ColumnTransformer(
        [("cat", OneHotEncoder(handle_unknown="ignore"), CAT),
         ("num", StandardScaler(), NUM)],
        sparse_threshold=0,
    )


def size_mb(model):
    buf = io.BytesIO()
    joblib.dump(model, buf)
    return buf.tell() / 1e6


# %% [2] K-fold (5 folds) — Régression
REG = {
    "Random Forest": RandomForestRegressor(n_estimators=200, max_depth=15, min_samples_leaf=5,
                                           n_jobs=-1, random_state=42),
    "XGBoost": XGBRegressor(n_estimators=300, max_depth=6, learning_rate=0.1, random_state=42),
}
kf = KFold(n_splits=5, shuffle=True, random_state=42)
rows = []
for name, model in REG.items():
    pipe = SkPipeline([("pre", make_pre()), ("model", model)])
    t0 = time.time()
    cv = cross_validate(pipe, X, y_reg, cv=kf, return_estimator=True,
                        scoring={"MAE": "neg_mean_absolute_error",
                                 "RMSE": "neg_root_mean_squared_error",
                                 "R2": "r2"})
    rows.append({
        "modèle": name,
        "MAE": -cv["test_MAE"].mean(), "MAE ±": cv["test_MAE"].std(),
        "RMSE": -cv["test_RMSE"].mean(),
        "R²": cv["test_R2"].mean(), "R² ±": cv["test_R2"].std(),
        "temps (s)": time.time() - t0,
        "taille (Mo)": size_mb(cv["estimator"][0]),
    })
    print(f"Régression — {name} : 5 folds terminés")
reg_cv = pd.DataFrame(rows).set_index("modèle").round(3)
print("\nRégression (K-fold, 5 folds) :\n", reg_cv)

# %% [3] K-fold stratifié (5 folds) — Classification
# SMOTE est dans le pipeline : appliqué seulement sur les folds d'entraînement.
CLF = {
    "Régression logistique": LogisticRegression(max_iter=1000),
    "Random Forest": RandomForestClassifier(n_estimators=200, max_depth=15, min_samples_leaf=5,
                                            n_jobs=-1, random_state=42),
    "XGBoost": XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.1,
                             eval_metric="logloss", random_state=42),
}
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
rows = []
for name, model in CLF.items():
    pipe = Pipeline([("pre", make_pre()), ("smote", SMOTE(random_state=42)), ("model", model)])
    t0 = time.time()
    cv = cross_validate(pipe, X, y_clf, cv=skf, return_estimator=True,
                        scoring=["accuracy", "precision", "recall", "f1", "roc_auc"])
    rows.append({
        "modèle": name,
        "Accuracy": cv["test_accuracy"].mean(),
        "Precision": cv["test_precision"].mean(),
        "Recall": cv["test_recall"].mean(),
        "F1": cv["test_f1"].mean(), "F1 ±": cv["test_f1"].std(),
        "AUC": cv["test_roc_auc"].mean(), "AUC ±": cv["test_roc_auc"].std(),
        "temps (s)": time.time() - t0,
        "taille (Mo)": size_mb(cv["estimator"][0]),
    })
    print(f"Classification — {name} : 5 folds terminés")
clf_cv = pd.DataFrame(rows).set_index("modèle").round(3)
print("\nClassification (K-fold stratifié, 5 folds, seuil 0.5) :\n", clf_cv)

# %% [4] Choix du seuil de décision (sans jamais toucher au test)
X_train, X_test, y_train, y_test = train_test_split(
    X, y_clf, test_size=0.2, stratify=y_clf, random_state=42)

thr_rows, pr_curves = [], {}
for name, model in CLF.items():
    pipe = Pipeline([("pre", make_pre()), ("smote", SMOTE(random_state=42)), ("model", clone(model))])
    # Probabilités "hors fold" sur le train -> choix du seuil qui maximise F1
    proba_oof = cross_val_predict(pipe, X_train, y_train, cv=skf, method="predict_proba")[:, 1]
    prec, rec, thr = precision_recall_curve(y_train, proba_oof)
    f1 = 2 * prec[:-1] * rec[:-1] / (prec[:-1] + rec[:-1] + 1e-9)
    best_thr = float(thr[np.argmax(f1)])
    pr_curves[name] = (thr, prec[:-1], rec[:-1], best_thr)

    # Vérification sur le test avec le seuil 0.5 et le seuil choisi
    pipe.fit(X_train, y_train)
    proba_test = pipe.predict_proba(X_test)[:, 1]
    for label, t in [("0.50 (défaut)", 0.5), ("optimisé", best_thr)]:
        pred = (proba_test >= t).astype(int)
        thr_rows.append({
            "modèle": name, "seuil": label, "valeur": round(t, 3),
            "Precision": precision_score(y_test, pred, zero_division=0),
            "Recall": recall_score(y_test, pred),
            "F1": f1_score(y_test, pred),
        })
    print(f"Seuil — {name} : {best_thr:.3f}")

thr_df = pd.DataFrame(thr_rows).set_index(["modèle", "seuil"]).round(3)
print("\nEffet du seuil sur le test :\n", thr_df)

# %% [5] Graphique : Precision et Recall selon le seuil
fig, axes = plt.subplots(1, len(pr_curves), figsize=(17, 5), sharey=True)
for ax, (name, (thr, prec, rec, best_thr)) in zip(axes, pr_curves.items()):
    ax.plot(thr, prec, label="Precision")
    ax.plot(thr, rec, label="Recall")
    ax.axvline(best_thr, color="k", linestyle="--", label=f"seuil choisi = {best_thr:.2f}")
    ax.set(title=name, xlabel="seuil de décision")
    ax.legend()
axes[0].set_ylabel("score")
plt.tight_layout()
plt.show()

# %% [6] Sauvegarde des résultats d'évaluation
report = {
    "regression_kfold": reg_cv.reset_index().to_dict(orient="records"),
    "classification_kfold": clf_cv.reset_index().to_dict(orient="records"),
    "thresholds": thr_df.reset_index().to_dict(orient="records"),
}
with open(MODELS_DIR / "evaluation.json", "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print("\nRésultats enregistrés :", MODELS_DIR / "evaluation.json")