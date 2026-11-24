# 05_classification.py — Étape 5 du ML Pipeline : Training (B) — Classification « retard long » (> 15 min)
# Entrée : dataset/transport_features.csv
# Règles : baseline d'abord, SMOTE sur le train uniquement, évaluation avec Recall / F1 (pas l'Accuracy seule).

# %% [1] Imports et chargement
from pathlib import Path
import time
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.base import clone
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import LinearSVC
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (accuracy_score, precision_score, recall_score, f1_score,
                             roc_auc_score, roc_curve, ConfusionMatrixDisplay)
from imblearn.pipeline import Pipeline
from imblearn.over_sampling import SMOTE
from xgboost import XGBClassifier

try:
    BASE = Path(__file__).resolve().parent
except NameError:                      # exécution cellule par cellule
    BASE = Path.cwd()
DATA_DIR = BASE / "dataset"
MODELS_DIR = BASE / "models"
MODELS_DIR.mkdir(exist_ok=True)

data = pd.read_csv(DATA_DIR / "transport_features.csv")

CAT = ["mode", "incident_grp", "day"]
NUM = ["hour", "month"]          # rush_hour et is_weekend retirés : importance < 1 % (étape 4)
X = data[CAT + NUM]
y = data["long_delay"]

# %% [2] Holdout stratifié : même proportion de retards longs dans train et test
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, stratify=y, random_state=42)
print("Train :", X_train.shape, "| Test :", X_test.shape)
print("Part des retards longs — train :", round(y_train.mean(), 3), "| test :", round(y_test.mean(), 3))

# %% [3] Prétraitement (One-Hot + standardisation)
pre = ColumnTransformer(
    [("cat", OneHotEncoder(handle_unknown="ignore"), CAT),
     ("num", StandardScaler(), NUM)],
    sparse_threshold=0,
)
# SMOTE est placé DANS le pipeline : il n'est appliqué que pendant fit() sur le train,
# jamais sur le test.

# %% [4] Les modèles à comparer
MODELS = {
    "Baseline (classe majoritaire)": DummyClassifier(strategy="most_frequent"),
    "Régression logistique": LogisticRegression(max_iter=1000),
    "KNN (k=15)": KNeighborsClassifier(n_neighbors=15, n_jobs=-1),
    "SVM linéaire": LinearSVC(C=1.0, max_iter=5000, random_state=42),
    "Decision Tree": DecisionTreeClassifier(max_depth=10, min_samples_leaf=20, random_state=42),
    "Random Forest": RandomForestClassifier(n_estimators=200, max_depth=15, min_samples_leaf=5,
                                            n_jobs=-1, random_state=42),
    "XGBoost": XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.1,
                             eval_metric="logloss", random_state=42),
}

# %% [5] Entraînement et évaluation sur le test
rows, fitted, curves = [], {}, {}
for name, model in MODELS.items():
    steps = [("pre", clone(pre))]
    if not name.startswith("Baseline"):          # la baseline reste sur les données réelles
        steps.append(("smote", SMOTE(random_state=42)))
    steps.append(("model", model))
    pipe = Pipeline(steps)

    t0 = time.time()
    pipe.fit(X_train, y_train)
    pred = pipe.predict(X_test)
    if hasattr(pipe, "predict_proba"):
        score = pipe.predict_proba(X_test)[:, 1]
    else:                                        # LinearSVC n'a pas de probabilités
        score = pipe.decision_function(X_test)

    rows.append({
        "modèle": name,
        "Accuracy": accuracy_score(y_test, pred),
        "Precision": precision_score(y_test, pred, zero_division=0),
        "Recall": recall_score(y_test, pred),
        "F1": f1_score(y_test, pred),
        "AUC": roc_auc_score(y_test, score),
        "temps (s)": time.time() - t0,
    })
    curves[name] = roc_curve(y_test, score)
    fitted[name] = pipe
    print(f"{name} : entraîné ({time.time() - t0:.1f} s)")

results = pd.DataFrame(rows).set_index("modèle").round(3)
print("\nRésultats sur le test :\n", results)

# %% [6] Courbes ROC + matrice de confusion du meilleur modèle (selon F1)
best = results["F1"].idxmax()
fig, axes = plt.subplots(1, 2, figsize=(15, 6))
for name, (fpr, tpr, _) in curves.items():
    axes[0].plot(fpr, tpr, label=f"{name} (AUC = {results.loc[name, 'AUC']:.2f})")
axes[0].plot([0, 1], [0, 1], "k--")
axes[0].set(title="Courbes ROC", xlabel="Taux de faux positifs", ylabel="Taux de vrais positifs (Recall)")
axes[0].legend(fontsize=8)

ConfusionMatrixDisplay.from_predictions(
    y_test, fitted[best].predict(X_test),
    display_labels=["court (≤ 15 min)", "long (> 15 min)"], ax=axes[1], colorbar=False)
axes[1].set_title(f"Matrice de confusion — {best}")
plt.tight_layout()
plt.show()

# %% [7] Sauvegarde des résultats
results.to_csv(MODELS_DIR / "classification_results.csv")
print("\nRésultats enregistrés :", MODELS_DIR / "classification_results.csv")