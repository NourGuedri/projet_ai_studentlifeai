# Module `closet` : Garde-robe intelligente (Vie quotidienne)

User stories couvertes : **37** (ajouter des vêtements à partir d'une photo) et **38** (suggestion de tenue selon la météo, l'occasion et les vêtements).

## Fonctionnement

```
Photo ──► POST /api/closet/items/analyze/ ──► extraction de caractéristiques ──► SVC / KNN / arbres / Random Forest / XGBoost
                                                │  type · couleur · style · confiance
          l'étudiant VÉRIFIE / CORRIGE  ◄───────┘
              │
              ▼
          POST /api/closet/items/ ──► ClothingItem (base Django)

GET /api/closet/items/outfit/?city=Tunis ──► météo (Open-Meteo) + règles ──► tenue du jour
```

- **Machine learning classique** (celui du cours), sans réseau de neurones : chaque photo est transformée en un vecteur de 554 nombres (voir `ml/feature_extraction.py`), puis classée par le meilleur modèle trouvé par comparaison.
- **L'IA propose, l'étudiant valide** (exigence 8.5) : `analyze` n'enregistre rien ; l'enregistrement est une 2ᵉ requête faite après correction éventuelle.
- La **catégorie** (Haut / Bas / Vestes et pulls / Robe / Chaussures) est toujours déduite du type côté serveur.
- Sans scikit-learn ou sans modèle entraîné, `analyze` répond **503** avec un message clair et l'ajout manuel continue de fonctionner.
- La recommandation de tenue est **à base de règles** (explicable, testable) ; le ML sert à la reconnaissance d'image.

## API (JWT requis, chaque étudiant ne voit que ses vêtements)

| Route | Rôle |
|---|---|
| `GET /api/closet/items/?category=Haut` | liste du dressing |
| `POST /api/closet/items/` (multipart : `image`, `item_type`, `color`, `style`, `name?`, `ai_detected?`, `ai_confidence?`) | ajouter |
| `PATCH /api/closet/items/<id>/` | corriger |
| `DELETE /api/closet/items/<id>/` | supprimer (et le fichier image) |
| `GET /api/closet/items/options/` | types par catégorie, couleurs, styles (pour les formulaires) |
| `POST /api/closet/items/analyze/` (multipart : `image`) | détection IA, sans enregistrer |
| `GET /api/closet/items/outfit/?city=&style=&seed=` | tenue du jour (ville par défaut : celle du profil, sinon Tunis) |

## Installation

```bash
pip install -r requirements.txt          # Pillow est requis
cd backend && python manage.py migrate   # migration closet.0001
```

Sans modèle entraîné tout fonctionne en saisie manuelle. Pour activer la détection automatique :

```bash
pip install -r backend/closet/ml/requirements-ml.txt
```

puis entraîner le modèle (ci-dessous). Aucun GPU n'est nécessaire.

## Entraîner le modèle (ML classique)

1. Télécharger le dataset Kaggle **Fashion Product Images (Small)** (`paramaggarwal/fashion-product-images-small`) et le décompresser dans `backend/closet/ml/dataset/` (il doit contenir `styles.csv` et `images/`). Ce dossier est ignoré par git.
2. Entraîner :
   ```bash
   cd backend/closet/ml
   python train.py --data dataset                          # standard
   python train.py --data dataset --tune --full-compare    # + réglage des hyperparamètres + tableau final
   python train.py --data dataset --limit 3000 --cv-samples 1500   # essai rapide (quelques minutes)
   ```
3. Tester : `python predict.py ma_photo.jpg` (un seul vêtement, centré, fond uni).
4. Évaluer et produire les matrices de confusion : `python evaluate.py --data dataset` (images dans `models/reports/`).

Le script compare **SVC, KNN, arbre de décision, Random Forest et XGBoost** pour chaque cible (type, couleur, style) par validation croisée, garde le meilleur (F1 macro), puis l'évalue une seule fois sur 20 % de données de test. Tous les scores sont dans `models/metrics.json`.

À savoir :
- La **première extraction** des caractéristiques de ~21 000 images prend quelques minutes ; elle est ensuite mise en cache (`dataset/processed/`).
- **XGBoost est de loin le plus lent** (surtout avec `--tune`). Pour aller plus vite : `--models SVC KNN DecisionTree RandomForest`, ou diminuer `--cv-samples`. Option `--jobs` pour limiter les cœurs utilisés.
- Les fichiers produits sont `models/clothing_classifier.joblib` (+ `metrics.json`). **Vérifiez sa taille** à la fin de l'entraînement : GitHub refuse > 100 Mo. Si c'est trop gros (forêt volumineuse), réduisez `n_estimators` dans `make_model` ou partagez le fichier hors de git.

### Notebooks (`ml/notebooks/`), à lancer dans l'ordre
1. `01_dataset_exploration.ipynb` : distribution des classes, exemples d'images, constat sur le déséquilibre.
2. `02_feature_extraction.ipynb` : chaque étape de l'extraction (masque, HOG, couleur), projection PCA.
3. `03_model_comparison.ipynb` : tableaux de scores, matrice de confusion, classes les plus difficiles, test sur vos photos.

### Choix techniques
- **Caractéristiques** : HOG (forme), histogramme de teinte + moyennes HSV/Lab **calculés sur le vêtement uniquement** (le fond est détecté et ignoré), silhouette en grille, texture LBP. Les mêmes fonctions servent à l'entraînement et à la prédiction.
- **Recadrage** sur le vêtement puis réduction à 64×80 : les photos nettes d'un téléphone ressemblent ainsi aux petites images du dataset.
- **Déséquilibre des classes** : `class_weight="balanced"` (poids d'échantillons pour XGBoost) et métrique F1 macro.
- **Pas de fuite de données** : le jeu de test n'est jamais utilisé pour choisir le modèle.
- Le SVC final est calibré (`CalibratedClassifierCV`) pour pouvoir afficher une confiance.

### Limites connues
- Photo idéale : **un seul vêtement, centré, fond uni**. Un fond chargé ou plusieurs vêtements sur l'image dégradent surtout la couleur.
- Un vêtement blanc sur fond blanc n'est pas détecté comme distinct du fond : l'extraction utilise alors le centre de l'image.
- Les classes proches (Pantalon / Jogging, Chemise / Top, Pull / Sweat) se confondent plus que les autres : c'est visible dans la matrice de confusion.


## Tests
```bash
cd backend && python manage.py test closet
```
Les tests ML tournent sur un mini dataset synthétique généré à la volée (aucun téléchargement) et sont ignorés si scikit-learn n'est pas installé.
