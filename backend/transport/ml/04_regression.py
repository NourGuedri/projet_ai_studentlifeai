# 04_regression.py — Étape 4 du ML Pipeline : Training (A) — Régression sur min_delay
# Entrée : dataset/transport_features.csv
# On compare 5 modèles sur le même holdout 80/20, en commençant par une baseline.

# %% [1] Imports et chargement
from pathlib import Path
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.base import clone
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import LinearRegression
from sklearn.tree import DecisionTreeRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

try:
    BASE = Path(__file__).resolve().parent
except NameError:                      # exécution cellule par cellule
    BASE = Path.cwd()
DATA_DIR = BASE / "dataset"
MODELS_DIR = BASE / "models"
MODELS_DIR.mkdir(exist_ok=True)

data = pd.read_csv(DATA_DIR / "transport_features.csv")

CAT = ["mode", "incident_grp", "day"]
NUM = ["hour", "month", "is_weekend", "rush_hour"]
X = data[CAT + NUM]
y = data["min_delay"]

# %% [2] Holdout : 80 % train, 20 % test
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
print("Train :", X_train.shape, "| Test :", X_test.shape)

# %% [3] Prétraitement : One-Hot Encoding des colonnes catégorielles
pre = ColumnTransformer(
    [("cat", OneHotEncoder(handle_unknown="ignore"), CAT)],
    remainder="passthrough",
)

# %% [4] Les modèles à comparer (baseline d'abord)
MODELS = {
    "Baseline (moyenne)": DummyRegressor(strategy="mean"),
    "Régression linéaire": LinearRegression(),
    "Decision Tree": DecisionTreeRegressor(max_depth=10, min_samples_leaf=20, random_state=42),
    "Random Forest": RandomForestRegressor(n_estimators=200, max_depth=15, min_samples_leaf=5,
                                           n_jobs=-1, random_state=42),
    "XGBoost": XGBRegressor(n_estimators=300, max_depth=6, learning_rate=0.1, random_state=42),
}

# %% [5] Entraînement et évaluation sur le test (holdout)
rows, fitted = [], {}
for name, model in MODELS.items():
    pipe = Pipeline([("pre", clone(pre)), ("model", model)])
    t0 = time.time()
    pipe.fit(X_train, y_train)
    pred = pipe.predict(X_test)
    mse = mean_squared_error(y_test, pred)
    rows.append({
        "modèle": name,
        "MAE": mean_absolute_error(y_test, pred),
        "MSE": mse,
        "RMSE": np.sqrt(mse),
        "R²": r2_score(y_test, pred),
        "temps (s)": time.time() - t0,
    })
    fitted[name] = pipe
    print(f"{name} : entraîné")

results = pd.DataFrame(rows).set_index("modèle").round(3)
print("\nRésultats sur le test :\n", results)

# %% [6] Importance des features (Random Forest)
rf = fitted["Random Forest"]
names = rf.named_steps["pre"].get_feature_names_out()
imp = pd.Series(rf.named_steps["model"].feature_importances_, index=names)
print("\nTop 15 des features :\n", imp.sort_values(ascending=False).head(15).round(3))

# Importance regroupée par feature d'origine
groups = {f: imp[[n for n in names if f in n]].sum() for f in CAT + NUM}
print("\nImportance par feature d'origine :\n",
      pd.Series(groups).sort_values(ascending=False).round(3))

# %% [7] Graphiques : MAE par modèle + réel vs prédit
best = results["MAE"].idxmin()
pred_best = fitted[best].predict(X_test)

fig, axes = plt.subplots(1, 2, figsize=(14, 5))
results["MAE"].sort_values().plot.barh(ax=axes[0], title="MAE par modèle (minutes, plus bas = mieux)")
axes[1].scatter(y_test, pred_best, s=4, alpha=0.2)
axes[1].plot([0, 120], [0, 120], "r--", label="prédiction parfaite")
axes[1].set(title=f"{best} : réel vs prédit", xlabel="retard réel (min)", ylabel="retard prédit (min)")
axes[1].legend()
plt.tight_layout()
plt.show()

# %% [8] Sauvegarde des résultats
results.to_csv(MODELS_DIR / "regression_results.csv")
print("\nRésultats enregistrés :", MODELS_DIR / "regression_results.csv")