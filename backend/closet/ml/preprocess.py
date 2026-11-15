"""Préparation des données : lecture de styles.csv, nettoyage, features en cache, découpage train/test."""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

try:  # importé comme module Django (closet.ml.preprocess) ou lancé comme script (cd ml)
    from .feature_extraction import FEATURE_VERSION, N_FEATURES, extract_many
    from .labels import ARTICLE_TO_CATEGORY, COLOR_FR, STYLE_FR
except ImportError:
    from feature_extraction import FEATURE_VERSION, N_FEATURES, extract_many
    from labels import ARTICLE_TO_CATEGORY, COLOR_FR, STYLE_FR

HERE = Path(__file__).parent
DEFAULT_DATA = HERE / "dataset"

# cible du modèle -> colonne de styles.csv
TARGET_COLUMNS = {"type": "articleType", "color": "baseColour", "style": "usage"}


def build_dataframe(data_dir=DEFAULT_DATA, min_color_count=200, limit=None):
    """Retourne (df nettoyé, dossier des images). Garde uniquement les classes utiles à l'application."""
    csv = next(Path(data_dir).rglob("styles.csv"))
    images = csv.parent / "images"
    df = pd.read_csv(csv, on_bad_lines="skip")             # quelques lignes du CSV sont mal formées
    df = df[df.articleType.isin(ARTICLE_TO_CATEGORY) & df.usage.isin(STYLE_FR) & df.baseColour.isin(COLOR_FR)]
    counts = df.baseColour.value_counts()
    df = df[df.baseColour.isin(counts[counts >= min_color_count].index)]
    df = df[df.id.apply(lambda i: (images / f"{i}.jpg").exists())]
    if limit:
        df = df.sample(min(limit, len(df)), random_state=0)
    return df.sort_values("id").reset_index(drop=True), images


def load_features(df, images, cache_dir=None, n_jobs=-1, use_cache=True):
    """Matrice X (n_images, 554). Mise en cache : l'extraction ne se refait pas à chaque entraînement."""
    cache = None
    if cache_dir is not None:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        cache = Path(cache_dir) / f"features_{FEATURE_VERSION}.npz"
    ids = df.id.to_numpy()
    if use_cache and cache is not None and cache.exists():
        saved = np.load(cache)
        if saved["X"].shape == (len(ids), N_FEATURES) and np.array_equal(saved["ids"], ids):
            print(f"Features chargées depuis le cache : {cache.name}")
            return saved["X"]
    print(f"Extraction des caractéristiques de {len(ids)} images (quelques minutes)...", flush=True)
    X = extract_many([images / f"{i}.jpg" for i in ids], n_jobs=n_jobs)
    if cache is not None:
        np.savez_compressed(cache, X=X, ids=ids)
    return X


def split_indices(df, test_size=0.2, seed=42):
    """Même découpage partout (train.py, evaluate.py, notebooks) : le jeu de test n'est jamais utilisé pour choisir."""
    idx = np.arange(len(df))
    return train_test_split(idx, test_size=test_size, random_state=seed, stratify=df["articleType"])
