"""Évalue le modèle sauvegardé sur le jeu de test (même découpage que train.py) et sauvegarde les
matrices de confusion en images dans models/reports/.

    python evaluate.py --data dataset
"""
import argparse
from pathlib import Path

import numpy as np
from sklearn.metrics import classification_report, confusion_matrix

try:
    from .predict import MODEL_PATH, _columns, load_bundle
    from .preprocess import TARGET_COLUMNS, build_dataframe, load_features, split_indices
except ImportError:
    from predict import MODEL_PATH, _columns, load_bundle
    from preprocess import TARGET_COLUMNS, build_dataframe, load_features, split_indices

HERE = Path(__file__).parent


def plot_confusion(matrix, classes, title, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    matrix = np.asarray(matrix, dtype=float)
    normalized = matrix / np.maximum(matrix.sum(axis=1, keepdims=True), 1)
    fig, ax = plt.subplots(figsize=(0.6 * len(classes) + 3, 0.6 * len(classes) + 2.5))
    ax.imshow(normalized, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(classes)), classes, rotation=60, ha="right")
    ax.set_yticks(range(len(classes)), classes)
    ax.set_xlabel("Prédit")
    ax.set_ylabel("Réel")
    ax.set_title(title)
    for i in range(len(classes)):
        for j in range(len(classes)):
            if matrix[i, j]:
                ax.text(j, i, int(matrix[i, j]), ha="center", va="center",
                        color="white" if normalized[i, j] > 0.5 else "black", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main(a):
    bundle = load_bundle(a.model)
    df, images = build_dataframe(a.data, a.min_color_count, a.limit)
    X_all = load_features(df, images, cache_dir=Path(a.data) / "processed", use_cache=True)
    _, test_idx = split_indices(df)
    reports = Path(a.model).parent / "reports"
    reports.mkdir(exist_ok=True)
    for target, entry in bundle["targets"].items():
        classes = entry["classes"]
        lookup = {c: i for i, c in enumerate(classes)}
        y = df[TARGET_COLUMNS[target]].map(lookup).to_numpy()[test_idx]
        pred = entry["pipeline"].predict(X_all[test_idx][:, _columns(entry["groups"])])
        print(f"\n===== {target} ({entry['best']}) =====")
        print(classification_report(y, pred, labels=range(len(classes)), target_names=classes, zero_division=0))
        path = reports / f"confusion_{target}.png"
        plot_confusion(confusion_matrix(y, pred, labels=range(len(classes))), classes,
                       f"Matrice de confusion : {target} ({entry['best']})", path)
        print("Image :", path)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", default=str(HERE / "dataset"))
    p.add_argument("--model", default=str(MODEL_PATH))
    p.add_argument("--limit", type=int, default=None, help="doit être identique à celui de train.py")
    p.add_argument("--min-color-count", type=int, default=200)
    main(p.parse_args())
