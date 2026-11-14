"""Entraînement et comparaison des modèles de classification du cours.

Pour chaque cible (type de vêtement, couleur, style) :
  1. validation croisée (3 plis) de SVC, KNN, arbre de décision, Random Forest, XGBoost ;
  2. choix du meilleur par F1 macro (option --tune : GridSearchCV sur le gagnant) ;
  3. ré-entraînement du gagnant sur tout le jeu d'entraînement ;
  4. évaluation UNE SEULE FOIS sur le jeu de test (20 %) : accuracy, précision, rappel, F1, matrice de confusion.

    python train.py --data dataset                      # entraînement standard
    python train.py --data dataset --tune --full-compare   # + réglage d'hyperparamètres + tableau final sur le test
    python train.py --data dataset --limit 3000 --cv-samples 1500   # essai rapide

Sorties dans models/ : clothing_classifier.joblib (modèles) et metrics.json (tous les scores).
"""
import argparse
import json
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (accuracy_score, classification_report, confusion_matrix,
                             f1_score, precision_score, recall_score)
from sklearn.model_selection import GridSearchCV, StratifiedKFold, train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier
from sklearn.utils.class_weight import compute_sample_weight

try:
    from xgboost import XGBClassifier
except ImportError:  # xgboost est facultatif
    XGBClassifier = None

try:
    from .feature_extraction import FEATURE_GROUPS, FEATURE_VERSION, N_FEATURES
    from .preprocess import TARGET_COLUMNS, build_dataframe, load_features, split_indices
except ImportError:
    from feature_extraction import FEATURE_GROUPS, FEATURE_VERSION, N_FEATURES
    from preprocess import TARGET_COLUMNS, build_dataframe, load_features, split_indices

HERE = Path(__file__).parent

# Quelles caractéristiques utiliser pour quelle cible : la couleur n'a pas besoin des contours.
TARGET_GROUPS = {
    "type": ["hog", "shape", "texture", "color"],
    "color": ["color"],
    "style": ["hog", "shape", "texture", "color"],
}

PARAM_GRIDS = {
    "SVC": {"clf__C": [1, 10, 50], "clf__gamma": ["scale", 0.001]},
    "KNN": {"clf__n_neighbors": [3, 5, 7, 11], "clf__weights": ["uniform", "distance"]},
    "DecisionTree": {"max_depth": [10, 18, None], "min_samples_leaf": [1, 3, 5]},
    "RandomForest": {"n_estimators": [100, 200], "max_depth": [16, 24, None]},
    "XGBoost": {"max_depth": [4, 6, 8], "learning_rate": [0.05, 0.1]},
}


def make_model(name, n_jobs=-1):
    if name == "SVC":
        return Pipeline([("scale", StandardScaler()),
                         ("clf", SVC(kernel="rbf", C=10, gamma="scale", class_weight="balanced", random_state=0))])
    if name == "KNN":
        return Pipeline([("scale", StandardScaler()),
                         ("clf", KNeighborsClassifier(n_neighbors=7, weights="distance", n_jobs=n_jobs))])
    if name == "DecisionTree":
        return DecisionTreeClassifier(max_depth=18, min_samples_leaf=3, class_weight="balanced", random_state=0)
    if name == "RandomForest":
        return RandomForestClassifier(n_estimators=150, max_depth=24, min_samples_leaf=2, n_jobs=n_jobs,
                                      class_weight="balanced_subsample", random_state=0)
    if name == "XGBoost":
        return XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.1, subsample=0.8,
                             colsample_bytree=0.5, tree_method="hist", n_jobs=n_jobs, random_state=0,
                             eval_metric="mlogloss")
    raise ValueError(f"Modèle inconnu : {name}")


def with_probabilities(model, name):
    """Le SVC ne donne pas de probabilités : pour le modèle final on le calibre, afin d'afficher une
    confiance à l'étudiant. Les autres modèles en fournissent déjà."""
    if name != "SVC":
        return model
    scaler, svc = model.named_steps["scale"], model.named_steps["clf"]
    return Pipeline([("scale", clone(scaler)),
                     ("clf", CalibratedClassifierCV(clone(svc), method="sigmoid", cv=3, ensemble=False))])


def fit(model, name, X, y):
    """XGBoost n'a pas de class_weight : on lui passe des poids d'échantillons équilibrés."""
    if name == "XGBoost":
        model.fit(X, y, sample_weight=compute_sample_weight("balanced", y))
    else:
        model.fit(X, y)
    return model


def cross_validate_model(name, X, y, n_jobs, folds=3):
    accuracies, f1s = [], []
    start = time.time()
    for tr, va in StratifiedKFold(folds, shuffle=True, random_state=0).split(X, y):
        model = fit(make_model(name, n_jobs), name, X[tr], y[tr])
        pred = model.predict(X[va])
        accuracies.append(accuracy_score(y[va], pred))
        f1s.append(f1_score(y[va], pred, average="macro"))
    return {"accuracy": float(np.mean(accuracies)), "f1_macro": float(np.mean(f1s)),
            "f1_macro_std": float(np.std(f1s)), "seconds": round(time.time() - start, 1)}


def test_metrics(model, X, y, class_names):
    pred = model.predict(X)
    labels = list(range(len(class_names)))
    return {
        "accuracy": float(accuracy_score(y, pred)),
        "precision_macro": float(precision_score(y, pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y, pred, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(y, pred, average="macro", zero_division=0)),
        "f1_weighted": float(f1_score(y, pred, average="weighted", zero_division=0)),
        "per_class": classification_report(y, pred, labels=labels, target_names=class_names,
                                           output_dict=True, zero_division=0),
        "confusion_matrix": confusion_matrix(y, pred, labels=labels).tolist(),
        "classes": list(class_names),
    }


def columns_for(target):
    return np.concatenate([np.arange(N_FEATURES)[FEATURE_GROUPS[g]] for g in TARGET_GROUPS[target]])


def main(a):
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    df, images = build_dataframe(a.data, a.min_color_count, a.limit)
    print(f"{len(df)} images retenues")
    X_all = load_features(df, images, cache_dir=Path(a.data) / "processed", n_jobs=a.jobs, use_cache=not a.no_cache)
    train_idx, test_idx = split_indices(df)
    print(f"entraînement : {len(train_idx)} images | test : {len(test_idx)} images (mis de côté)\n")

    names = [m for m in a.models if m != "XGBoost" or XGBClassifier is not None]
    if "XGBoost" in a.models and XGBClassifier is None:
        print("XGBoost non installé : ignoré (pip install xgboost)")

    metrics = {"feature_version": FEATURE_VERSION, "n_train": int(len(train_idx)), "n_test": int(len(test_idx)),
               "targets": {}}
    bundle = {"version": FEATURE_VERSION, "targets": {}}

    for target in a.targets:
        print(f"{'=' * 70}\nCIBLE : {target}  (colonne {TARGET_COLUMNS[target]}; "
              f"caractéristiques : {', '.join(TARGET_GROUPS[target])})\n{'=' * 70}")
        encoder = LabelEncoder().fit(df[TARGET_COLUMNS[target]])
        y = encoder.transform(df[TARGET_COLUMNS[target]])
        X = X_all[:, columns_for(target)]
        X_train, y_train, X_test, y_test = X[train_idx], y[train_idx], X[test_idx], y[test_idx]

        # sous-échantillon pour la validation croisée (SVC et XGBoost seraient lents sinon)
        if len(train_idx) > a.cv_samples:
            cv_rows, _ = train_test_split(np.arange(len(train_idx)), train_size=a.cv_samples,
                                          random_state=0, stratify=y_train)
        else:
            cv_rows = np.arange(len(train_idx))
        Xc, yc = X_train[cv_rows], y_train[cv_rows]

        cv = {}
        print(f"Validation croisée (3 plis) sur {len(cv_rows)} images :")
        for name in names:
            cv[name] = cross_validate_model(name, Xc, yc, a.jobs)
            r = cv[name]
            print(f"  {name:13s} accuracy={r['accuracy']:.3f}  F1 macro={r['f1_macro']:.3f} "
                  f"(±{r['f1_macro_std']:.3f})  {r['seconds']}s", flush=True)
        best = max(cv, key=lambda n: cv[n]["f1_macro"])
        print(f"-> meilleur modèle : {best}")

        best_params = None
        tuned = make_model(best, a.jobs)
        if a.tune:
            print(f"Réglage des hyperparamètres de {best} (GridSearchCV, 3 plis)...", flush=True)
            search = GridSearchCV(make_model(best, a.jobs), PARAM_GRIDS[best], cv=3, scoring="f1_macro", n_jobs=1)
            search.fit(Xc, yc)
            best_params = {k: (v if v is None or isinstance(v, (int, float, str)) else str(v))
                           for k, v in search.best_params_.items()}
            print(f"   meilleurs paramètres : {best_params} (F1 macro CV = {search.best_score_:.3f})")
            tuned.set_params(**search.best_params_)
        final = with_probabilities(tuned, best)

        print(f"Entraînement final de {best} sur {len(y_train)} images...", flush=True)
        fit(final, best, X_train, y_train)
        result = test_metrics(final, X_test, y_test, encoder.classes_)
        print(f"TEST ({len(y_test)} images jamais vues) : accuracy={result['accuracy']:.3f}  "
              f"précision={result['precision_macro']:.3f}  rappel={result['recall_macro']:.3f}  "
              f"F1 macro={result['f1_macro']:.3f}\n")

        entry = {"cv": cv, "best": best, "best_params": best_params, "test": result}
        if a.full_compare:
            print("Comparaison de tous les modèles sur le jeu de test :")
            entry["test_all"] = {}
            for name in names:
                model = fit(make_model(name, a.jobs), name, X_train, y_train)
                entry["test_all"][name] = {k: v for k, v in test_metrics(model, X_test, y_test, encoder.classes_).items()
                                           if k in ("accuracy", "precision_macro", "recall_macro", "f1_macro", "f1_weighted")}
                print(f"  {name:13s} accuracy={entry['test_all'][name]['accuracy']:.3f}  "
                      f"F1 macro={entry['test_all'][name]['f1_macro']:.3f}", flush=True)
            print()
        metrics["targets"][target] = entry
        bundle["targets"][target] = {"pipeline": final, "classes": [str(c) for c in encoder.classes_],
                                     "groups": TARGET_GROUPS[target], "best": best}

    model_path = out_dir / "clothing_classifier.joblib"
    joblib.dump(bundle, model_path, compress=3)
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False))
    size = model_path.stat().st_size / 1e6
    print(f"Modèle sauvegardé : {model_path} ({size:.1f} Mo)")
    print(f"Scores détaillés : {out_dir / 'metrics.json'}")
    if size > 90:
        print("ATTENTION : GitHub refuse les fichiers > 100 Mo. Réduisez n_estimators (Random Forest) "
              "ou ne commitez pas ce fichier (voir README).")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", default=str(HERE / "dataset"), help="dossier contenant styles.csv et images/")
    p.add_argument("--out", default=str(HERE / "models"))
    p.add_argument("--targets", nargs="+", default=["type", "color", "style"], choices=list(TARGET_COLUMNS))
    p.add_argument("--models", nargs="+", default=["SVC", "KNN", "DecisionTree", "RandomForest", "XGBoost"],
                   choices=list(PARAM_GRIDS))
    p.add_argument("--cv-samples", type=int, default=8000, help="images utilisées pour la validation croisée")
    p.add_argument("--tune", action="store_true", help="GridSearchCV sur le meilleur modèle")
    p.add_argument("--full-compare", action="store_true", help="évaluer TOUS les modèles sur le jeu de test")
    p.add_argument("--limit", type=int, default=None, help="nombre max d'images (essais rapides)")
    p.add_argument("--jobs", type=int, default=-1, help="cœurs CPU (-1 = tous)")
    p.add_argument("--min-color-count", type=int, default=200)
    p.add_argument("--no-cache", action="store_true", help="recalculer les caractéristiques")
    return p.parse_args(argv)


if __name__ == "__main__":
    main(parse_args())
