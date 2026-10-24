"""Entraînement (fine-tuning d'EfficientNet-B0 pré-entraîné sur ImageNet).

Dataset Kaggle « Fashion Product Images (Small) » (paramaggarwal/fashion-product-images-small) :
un dossier contenant styles.csv et images/<id>.jpg (peu importe où, il est cherché récursivement).

    python train.py --data dataset --epochs 6
    python train.py --data dataset --epochs 1 --limit 3000      # test rapide

Sortie : models/clothing_model.pth (poids + liste des classes).
"""
import argparse
from pathlib import Path

import pandas as pd
import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset, random_split
from torchvision import transforms

try:  # exécuté en script (cd ml && python train.py) ou comme module Django
    from .labels import ARTICLE_TO_CATEGORY, COLOR_FR, STYLE_FR
    from .model import IMG_SIZE, MEAN, STD, ClothingNet
except ImportError:
    from labels import ARTICLE_TO_CATEGORY, COLOR_FR, STYLE_FR
    from model import IMG_SIZE, MEAN, STD, ClothingNet

HERE = Path(__file__).parent
OUT = HERE / "models" / "clothing_model.pth"


def build_dataframe(data_dir, min_color_count=200, limit=None):
    csv = next(Path(data_dir).rglob("styles.csv"))
    images = csv.parent / "images"
    df = pd.read_csv(csv, on_bad_lines="skip")  # quelques lignes du CSV sont mal formées
    df = df[df.articleType.isin(ARTICLE_TO_CATEGORY) & df.usage.isin(STYLE_FR) & df.baseColour.isin(COLOR_FR)]
    counts = df.baseColour.value_counts()
    df = df[df.baseColour.isin(counts[counts >= min_color_count].index)]
    df = df[df.id.apply(lambda i: (images / f"{i}.jpg").exists())]
    if limit:
        df = df.sample(min(limit, len(df)), random_state=0)
    return df.reset_index(drop=True), images


class ClothesDS(Dataset):
    def __init__(self, df, images, maps, tf):
        self.df, self.images, self.maps, self.tf = df, images, maps, tf

    def __len__(self):
        return len(self.df)

    def __getitem__(self, i):
        r = self.df.iloc[i]
        img = Image.open(self.images / f"{r.id}.jpg").convert("RGB")
        return (self.tf(img), self.maps["article"][r.articleType],
                self.maps["color"][r.baseColour], self.maps["style"][r.usage])


def main(a):
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    df, images = build_dataframe(a.data, a.min_color_count, a.limit)
    print(f"{len(df)} images utilisées, appareil : {dev}")
    classes = {"article": sorted(df.articleType.unique()),
               "color": sorted(df.baseColour.unique()),
               "style": sorted(df.usage.unique())}
    maps = {k: {c: i for i, c in enumerate(v)} for k, v in classes.items()}
    print({k: len(v) for k, v in classes.items()}, "classes")

    tf = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)), transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(brightness=0.15, contrast=0.15),   # pas de hue : la couleur doit rester fiable
        transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
    ds = ClothesDS(df, images, maps, tf)
    n_val = max(1, int(0.15 * len(ds)))
    train_set, val_set = random_split(ds, [len(ds) - n_val, n_val], generator=torch.Generator().manual_seed(42))
    train_dl = DataLoader(train_set, batch_size=a.bs, shuffle=True, num_workers=a.workers)
    val_dl = DataLoader(val_set, batch_size=a.bs, num_workers=a.workers)

    model = ClothingNet(len(classes["article"]), len(classes["color"]), len(classes["style"]),
                        pretrained=not a.no_pretrained).to(dev)
    ce = nn.CrossEntropyLoss()

    for epoch in range(a.epochs):
        frozen = epoch == 0 and a.epochs > 1   # 1re epoch : seulement les têtes, ensuite fine-tuning complet
        for p in model.features.parameters():
            p.requires_grad = not frozen
        opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=1e-3 if frozen else 1e-4)

        model.train()
        for x, ya, yc, ys in train_dl:
            x, ya, yc, ys = x.to(dev), ya.to(dev), yc.to(dev), ys.to(dev)
            oa, oc, os_ = model(x)
            loss = ce(oa, ya) + ce(oc, yc) + 0.5 * ce(os_, ys)
            opt.zero_grad()
            loss.backward()
            opt.step()

        model.eval()
        ok, n = [0, 0, 0], 0
        with torch.no_grad():
            for x, ya, yc, ys in val_dl:
                for i, (o, y) in enumerate(zip(model(x.to(dev)), (ya, yc, ys))):
                    ok[i] += (o.argmax(1).cpu() == y).sum().item()
                n += len(x)
        print(f"epoch {epoch + 1}/{a.epochs} | précision validation : "
              f"type={ok[0] / n:.3f}  couleur={ok[1] / n:.3f}  style={ok[2] / n:.3f}")

    OUT.parent.mkdir(exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "classes": classes}, OUT)
    print("Modèle sauvegardé :", OUT)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", default=str(HERE / "dataset"))
    p.add_argument("--epochs", type=int, default=6)
    p.add_argument("--bs", type=int, default=64)
    p.add_argument("--workers", type=int, default=2, help="mettre 0 sous Windows en cas d'erreur")
    p.add_argument("--limit", type=int, default=None, help="nombre max d'images (tests rapides)")
    p.add_argument("--min-color-count", type=int, default=200)
    p.add_argument("--no-pretrained", action="store_true", help="sans poids ImageNet (tests hors-ligne)")
    main(p.parse_args())
