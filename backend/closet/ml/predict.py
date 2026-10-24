"""Prédiction à partir d'une photo.

    python predict.py photo.jpg            # en ligne de commande
    from closet.ml.predict import predict_image   # depuis Django
"""
import sys
from pathlib import Path

import torch
from PIL import Image
from torchvision import transforms

try:
    from .labels import ARTICLE_FR, ARTICLE_TO_CATEGORY, COLOR_FR, STYLE_FR
    from .model import IMG_SIZE, MEAN, STD, ClothingNet
except ImportError:
    from labels import ARTICLE_FR, ARTICLE_TO_CATEGORY, COLOR_FR, STYLE_FR
    from model import IMG_SIZE, MEAN, STD, ClothingNet

MODEL_PATH = Path(__file__).parent / "models" / "clothing_model.pth"
_TF = transforms.Compose([transforms.Resize((IMG_SIZE, IMG_SIZE)), transforms.ToTensor(),
                          transforms.Normalize(MEAN, STD)])
_cache = {}


def model_available() -> bool:
    return MODEL_PATH.exists()


def _load():
    if "model" not in _cache:
        ck = torch.load(MODEL_PATH, map_location="cpu", weights_only=True)
        c = ck["classes"]
        m = ClothingNet(len(c["article"]), len(c["color"]), len(c["style"]), pretrained=False)
        m.load_state_dict(ck["state_dict"])
        m.eval()
        _cache["model"], _cache["classes"] = m, c
    return _cache["model"], _cache["classes"]


def predict_image(file) -> dict:
    """file : chemin ou fichier ouvert. Retourne type / catégorie / couleur / style (en français) + confiance."""
    model, c = _load()
    img = Image.open(file).convert("RGB")
    with torch.no_grad():
        oa, oc, os_ = model(_TF(img).unsqueeze(0))
    pa, pc, ps = (o.softmax(1)[0] for o in (oa, oc, os_))
    art, col, sty = c["article"][int(pa.argmax())], c["color"][int(pc.argmax())], c["style"][int(ps.argmax())]
    return {
        "item_type": ARTICLE_FR.get(art, art),
        "category": ARTICLE_TO_CATEGORY[art],
        "color": COLOR_FR.get(col, col),
        "style": STYLE_FR.get(sty, sty),
        "confidence": round(float(pa.max()), 3),                 # confiance sur le type de vêtement
        "color_confidence": round(float(pc.max()), 3),
    }


if __name__ == "__main__":
    print(predict_image(sys.argv[1]))
