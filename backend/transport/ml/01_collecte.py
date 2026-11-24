# 01_collecte.py — Étape 1 du ML Pipeline : Data collection
# Source : TTC Delay Data 2024 (bus, tramway, métro), City of Toronto Open Data.
# Contains information licensed under the Open Government Licence – Toronto.

# %% [1] Imports et chemins
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

try:
    BASE = Path(__file__).resolve().parent
except NameError:                      # exécution cellule par cellule
    BASE = Path.cwd()
DATA_DIR = BASE / "dataset"

FILES = {
    "bus":     next(DATA_DIR.glob("*bus*.xlsx")),
    "tramway": next(DATA_DIR.glob("*streetcar*.xlsx")),
    "metro":   next(DATA_DIR.glob("*subway*.xlsx")),
}

# %% [2] Chargement et premier aperçu de chaque fichier
frames = {}
for mode, path in FILES.items():
    df = pd.read_excel(path)
    print(f"\n=== {mode} : {df.shape[0]} lignes, {df.shape[1]} colonnes")
    print(list(df.columns))
    frames[mode] = df

# %% [3] Harmoniser les noms de colonnes
RENAME = {
    "route": "line", "line": "line",
    "station": "location", "location": "location",
    "code": "incident", "incident": "incident",
    "min_delay": "min_delay", "min_gap": "min_gap",
    "date": "date", "time": "time", "day": "day",
}
KEEP = ["date", "time", "day", "line", "location", "incident", "min_delay", "min_gap"]

clean = []
for mode, df in frames.items():
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    df = df.rename(columns={c: RENAME[c] for c in df.columns if c in RENAME})
    df = df[[c for c in KEEP if c in df.columns]]
    df.insert(0, "mode", mode)
    clean.append(df)

data = pd.concat(clean, ignore_index=True)

# %% [4] Description du jeu de données fusionné
print("\nTaille :", data.shape)
print("\nLignes par moyen de transport :\n", data["mode"].value_counts())
print("\nTypes :\n", data.dtypes)
print("\nValeurs manquantes :\n", data.isna().sum())
print("\nMinutes de retard :\n", data["min_delay"].describe())
print("\nAperçu :\n", data.head())

# %% [5] Distribution des retards par moyen de transport
data[data["min_delay"] <= 60].boxplot(column="min_delay", by="mode")
plt.title("Minutes de retard par moyen de transport (≤ 60 min)")
plt.suptitle("")
plt.ylabel("minutes")
plt.show()

# %% [6] Sauvegarde du jeu fusionné pour l'étape suivante
data.to_csv(DATA_DIR / "transport_2024.csv", index=False)
print("\nFichier enregistré :", DATA_DIR / "transport_2024.csv")