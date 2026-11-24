# 02_nettoyage.py — Étape 2 du ML Pipeline : Data cleansing
# Entrée : dataset/transport_2024.csv (créé par 01_collecte.py)
# Sortie : dataset/transport_clean.csv

# %% [1] Imports et chargement
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

try:
    BASE = Path(__file__).resolve().parent
except NameError:                      # exécution cellule par cellule
    BASE = Path.cwd()
DATA_DIR = BASE / "dataset"

data = pd.read_csv(DATA_DIR / "transport_2024.csv", dtype={"line": str})
n0 = len(data)
print("Lignes au départ :", n0)

# %% [2] Doublons
dups = data.duplicated().sum()
data = data.drop_duplicates()
print("Doublons supprimés :", dups)

# %% [3] Valeurs manquantes
# line et location sont des catégories : on ne peut pas les deviner -> suppression (< 1 %)
print("Valeurs manquantes avant :\n", data.isna().sum())
data = data.dropna(subset=["line", "location"])
print("Lignes après suppression :", len(data))

# %% [4] Standardisation des textes
for col in ["line", "location", "incident", "day"]:
    data[col] = data[col].astype(str).str.strip().str.upper()
print("Lignes les plus fréquentes :", data["line"].value_counts().head(10).to_dict())

# %% [5] Date et heure
data["date"] = pd.to_datetime(data["date"], errors="coerce")
data["hour"] = pd.to_datetime(data["time"], format="%H:%M", errors="coerce").dt.hour
bad = data[["date", "hour"]].isna().any(axis=1).sum()
data = data.dropna(subset=["date", "hour"])
data["hour"] = data["hour"].astype(int)
data["month"] = data["date"].dt.month
print("Lignes avec date/heure invalide supprimées :", bad)

# %% [6] Valeurs aberrantes (outliers) de min_delay
print("Quantiles :\n", data["min_delay"].quantile([0.90, 0.95, 0.99]))
SEUIL_MAX = 120   # au-delà de 2 h : fermeture ou détournement exceptionnel
outliers = (data["min_delay"] > SEUIL_MAX).sum()
data = data[data["min_delay"] <= SEUIL_MAX]
print(f"Outliers supprimés (> {SEUIL_MAX} min) : {outliers} ({outliers / n0:.2%})")

# %% [7] Vérification après nettoyage
print("\nTaille finale :", data.shape, f"({len(data) / n0:.1%} des lignes gardées)")
print("\nMinutes de retard :\n", data["min_delay"].describe())
print("\nPart des retards > 15 min :", f"{(data['min_delay'] > 15).mean():.1%}")
print("\nPar mode :\n", data.groupby("mode")["min_delay"].agg(["count", "mean", "median"]))

# %% [8] Histogramme après nettoyage
data["min_delay"].hist(bins=60)
plt.title("Distribution des minutes de retard après nettoyage")
plt.xlabel("minutes")
plt.ylabel("nombre d'incidents")
plt.show()

# %% [9] Sauvegarde
data.to_csv(DATA_DIR / "transport_clean.csv", index=False)
print("\nFichier enregistré :", DATA_DIR / "transport_clean.csv")