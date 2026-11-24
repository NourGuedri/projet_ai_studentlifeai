# 03_features.py — Étape 3 du ML Pipeline : Feature extraction & selection
# Entrée : dataset/transport_clean.csv  ->  Sortie : dataset/transport_features.csv
# Cas d'usage (US 36) : un incident est signalé -> on estime le retard -> notification si > 15 min.

# %% [1] Imports et chargement
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

try:
    BASE = Path(__file__).resolve().parent
except NameError:                      # exécution cellule par cellule
    BASE = Path.cwd()
DATA_DIR = BASE / "dataset"

data = pd.read_csv(DATA_DIR / "transport_clean.csv", dtype={"line": str})
print("Taille :", data.shape)

# %% [2] Cardinalité des colonnes catégorielles
print("\nNombre de valeurs différentes :\n",
      data[["mode", "line", "location", "incident", "day"]].nunique())
for mode, g in data.groupby("mode"):
    print(f"\n{mode} — incidents les plus fréquents :\n", g["incident"].value_counts().head(8))

# %% [3] Extraction de nouvelles features
data["is_weekend"] = data["day"].isin(["SATURDAY", "SUNDAY"]).astype(int)
data["rush_hour"] = (data["hour"].between(6, 9) | data["hour"].between(15, 19)).astype(int)

# %% [4] Regrouper les incidents rares
TOP_N = 20
top = data["incident"].value_counts().nlargest(TOP_N).index
data["incident_grp"] = data["incident"].where(data["incident"].isin(top), "AUTRE")
print("\nIncidents regroupés :\n", data["incident_grp"].value_counts())

# %% [5] Les deux cibles
THRESHOLD = 15                                   # minutes
data["long_delay"] = (data["min_delay"] > THRESHOLD).astype(int)
print("\nRépartition des classes (long_delay) :\n",
      data["long_delay"].value_counts(normalize=True).round(3))

# %% [6] Effet de chaque feature sur le retard (justification de la sélection)
DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
fig, axes = plt.subplots(1, 3, figsize=(16, 5))
data.groupby("hour")["min_delay"].mean().plot(ax=axes[0], marker="o", title="Retard moyen par heure")
data.groupby("day")["min_delay"].mean().reindex(DAYS).plot.bar(ax=axes[1], title="Retard moyen par jour")
data.groupby("incident_grp")["min_delay"].mean().sort_values().plot.barh(ax=axes[2], title="Retard moyen par incident")
for ax in axes:
    ax.set_ylabel("")
plt.tight_layout()
plt.show()

# %% [7] Sélection finale des features
FEATURES = ["mode", "incident_grp", "hour", "day", "month", "is_weekend", "rush_hour"]
TARGETS = ["min_delay", "long_delay"]
# Exclues : min_gap (fuite de données : connu après l'incident),
#           line / location (propres à Toronto, des centaines de valeurs),
#           date / time (remplacées par hour, day, month).
final = data[FEATURES + TARGETS]
print("\nJeu final :", final.shape)
print(final.head())

# %% [8] Sauvegarde
final.to_csv(DATA_DIR / "transport_features.csv", index=False)
print("\nFichier enregistré :", DATA_DIR / "transport_features.csv")