# Module `closet` : Garde-robe intelligente (Vie quotidienne)

User stories couvertes : **37** (ajouter des vêtements à partir d'une photo) et **38** (suggestion de tenue selon la météo, l'occasion et les vêtements).

## Fonctionnement

```
Photo ──► POST /api/closet/items/analyze/ ──► EfficientNet-B0 (fine-tuné)
                                                │  type · couleur · style · confiance
          l'étudiant VÉRIFIE / CORRIGE  ◄───────┘
              │
              ▼
          POST /api/closet/items/ ──► ClothingItem (base Django)

GET /api/closet/items/outfit/?city=Tunis ──► météo (Open-Meteo) + règles ──► tenue du jour
```

- **L'IA propose, l'étudiant valide** (exigence 8.5) : `analyze` n'enregistre rien ; l'enregistrement est une 2ᵉ requête faite après correction éventuelle.
- La **catégorie** (Haut / Bas / Vestes et pulls / Robe / Chaussures) est toujours déduite du type côté serveur.
- Sans PyTorch ou sans modèle entraîné, `analyze` répond **503** avec un message clair et l'ajout manuel continue de fonctionner : le reste du site n'est jamais bloqué par le ML.
- La recommandation de tenue est volontairement **à base de règles** (explicable, testable) ; le ML sert à la reconnaissance d'image.

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
pip install -r requirements.txt          # Pillow est maintenant requis
cd backend && python manage.py migrate   # nouvelle migration closet.0001
```

Sans modèle entraîné tout fonctionne en saisie manuelle. Pour activer la détection automatique :

```bash
pip install -r backend/closet/ml/requirements-ml.txt
```
puis placer `clothing_model.pth` dans `backend/closet/ml/models/` (voir ci-dessous).

## Entraîner le modèle

**Option conseillée : Google Colab (GPU gratuit)** : ouvrir `ml/notebooks/train_colab.ipynb`.

**En local :**
```bash
pip install -r backend/closet/ml/requirements-ml.txt
# télécharger le dataset Kaggle « paramaggarwal/fashion-product-images-small » dans ml/dataset/
cd backend/closet/ml
python train.py --data dataset --epochs 6            # --workers 0 sous Windows si erreur
python predict.py ma_photo.jpg                       # test
```

Le dataset est ignoré par git (`.gitignore`) ; le fichier `models/clothing_model.pth` (≈ 17 Mo) est, lui, à commiter pour que toute l'équipe ait la détection.

### Choix techniques
- **Un seul réseau, 3 têtes** (type, couleur, style) : une seule inférence par photo.
- **Transfert d'apprentissage** : epoch 1 = têtes seules (backbone gelé), epochs suivantes = fine-tuning complet (lr plus faible).
- Pas de variation de teinte dans l'augmentation de données : elle fausserait la couleur.
- Limites : le dataset contient des photos de catalogue (fond clair). Sur des photos prises au téléphone, la précision baisse un peu ; en dessous de 60 % de confiance l'interface affiche « L'IA n'est pas sûre ».

## Tests
```bash
cd backend && python manage.py test closet
```
