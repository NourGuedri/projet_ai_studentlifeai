"""Extraction de caractéristiques (feature extraction) : photo -> vecteur de nombres.

Les algorithmes du cours (SVC, KNN, arbres, Random Forest, XGBoost) travaillent sur un tableau de
nombres, pas sur une image. Chaque photo est donc transformée en un vecteur de 554 valeurs :

    1. Prétraitement : transparence -> fond blanc, réduction, détection du fond, recadrage sur le
       vêtement, redimensionnement 64 x 80 (la taille des images du dataset).
    2. HOG (432)     : contours et orientations, pour reconnaître la forme (pantalon, robe, chemise...).
    3. Couleur (27)  : histogramme de teinte, proportions noir/blanc/gris, moyennes en HSV et Lab,
                       calculés UNIQUEMENT sur les pixels du vêtement (pas sur le fond).
    4. Forme (83)    : silhouette en grille 8 x 10, rapport largeur/hauteur, taux de remplissage.
    5. Texture (12)  : histogramme LBP (motifs locaux) et force des gradients.

Les mêmes fonctions servent à l'entraînement et à la prédiction : c'est indispensable.
"""
import numpy as np
from PIL import Image
from scipy import ndimage
from skimage.color import rgb2gray, rgb2hsv, rgb2lab
from skimage.feature import hog, local_binary_pattern

FEATURE_VERSION = "v1"

CANON_W, CANON_H = 64, 80            # taille canonique (portrait, comme le dataset)
MAX_SIDE = 160                       # les grandes photos sont réduites d'abord
BG_DISTANCE = 40                     # écart de couleur (0-255) au fond pour être « vêtement »

HOG_ORIENTATIONS, HOG_CELL, HOG_BLOCK = 9, (16, 16), (2, 2)
HUE_BINS = 12
GRID_W, GRID_H = 8, 10
LBP_POINTS, LBP_RADIUS = 8, 1

HOG_DIM, COLOR_DIM, SHAPE_DIM, TEXTURE_DIM = 432, 27, 83, 12
FEATURE_GROUPS = {
    "hog": slice(0, HOG_DIM),
    "color": slice(HOG_DIM, HOG_DIM + COLOR_DIM),
    "shape": slice(HOG_DIM + COLOR_DIM, HOG_DIM + COLOR_DIM + SHAPE_DIM),
    "texture": slice(HOG_DIM + COLOR_DIM + SHAPE_DIM, HOG_DIM + COLOR_DIM + SHAPE_DIM + TEXTURE_DIM),
}
N_FEATURES = HOG_DIM + COLOR_DIM + SHAPE_DIM + TEXTURE_DIM


# ------------------------------------------------------------------ 1. prétraitement
def load_rgb(file) -> np.ndarray:
    """Ouvre une image (chemin ou fichier) -> tableau uint8 (H, W, 3). La transparence devient du blanc."""
    img = Image.open(file)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        img = Image.alpha_composite(background, rgba)
    img = img.convert("RGB")
    if max(img.size) > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    return np.asarray(img, dtype=np.uint8)


def foreground_mask(rgb: np.ndarray) -> np.ndarray:
    """Masque du vêtement : tout ce qui diffère nettement de la couleur du fond (estimée sur les bords)."""
    border = np.concatenate([rgb[:2].reshape(-1, 3), rgb[-2:].reshape(-1, 3),
                             rgb[:, :2].reshape(-1, 3), rgb[:, -2:].reshape(-1, 3)])
    background = np.median(border, axis=0)
    distance = np.sqrt(((rgb.astype(np.float32) - background) ** 2).sum(axis=2))
    mask = distance > BG_DISTANCE
    mask = ndimage.binary_opening(mask, iterations=1)
    mask = ndimage.binary_fill_holes(mask)
    fraction = mask.mean()
    if fraction < 0.03 or fraction > 0.92:   # fond non uniforme ou vêtement blanc sur fond blanc
        h, w = mask.shape
        mask = np.zeros_like(mask)
        mask[int(h * .15):int(h * .85), int(w * .15):int(w * .85)] = True
    return mask


def _crop_and_resize(rgb, mask):
    ys, xs = np.where(mask)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    crop, crop_mask = rgb[y0:y1, x0:x1], mask[y0:y1, x0:x1]
    canon = np.asarray(Image.fromarray(crop).resize((CANON_W, CANON_H), Image.Resampling.BILINEAR))
    canon_mask = np.asarray(Image.fromarray((crop_mask * 255).astype(np.uint8))
                            .resize((CANON_W, CANON_H), Image.Resampling.BILINEAR)) > 127
    bbox_w, bbox_h = x1 - x0, y1 - y0
    return canon, canon_mask, bbox_w / bbox_h, crop_mask.mean(), mask.mean()


# ------------------------------------------------------------------ 2-5. caractéristiques
def hog_features(gray: np.ndarray) -> np.ndarray:
    return hog(gray, orientations=HOG_ORIENTATIONS, pixels_per_cell=HOG_CELL,
               cells_per_block=HOG_BLOCK, block_norm="L2-Hys", feature_vector=True)


def color_features(canon: np.ndarray, mask: np.ndarray) -> np.ndarray:
    pixels = canon[mask] if mask.sum() >= 20 else canon.reshape(-1, 3)
    rgb = (pixels / 255.0).reshape(-1, 1, 3)
    hsv = rgb2hsv(rgb).reshape(-1, 3)
    lab = rgb2lab(rgb).reshape(-1, 3)
    h, s, v = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    n = len(hsv)

    chromatic = (s > 0.2) & (v > 0.2)
    hue_hist = np.histogram(h[chromatic], bins=HUE_BINS, range=(0, 1))[0] / n        # 12
    shares = [chromatic.mean(),                                                      # 4
              (v < 0.2).mean(),
              ((s < 0.15) & (v > 0.85)).mean(),
              ((s < 0.2) & (v >= 0.2) & (v <= 0.85)).mean()]
    lab_mean = lab.mean(axis=0) / np.array([100, 128, 128])                          # 3
    lab_std = lab.std(axis=0) / np.array([100, 128, 128])                            # 3
    rgb_median = np.median(pixels, axis=0) / 255.0                                   # 3
    sv_mean = [s.mean(), v.mean()]                                                   # 2
    return np.concatenate([hue_hist, shares, lab_mean, lab_std, rgb_median, sv_mean])


def shape_features(mask, aspect, fill, foreground_share) -> np.ndarray:
    cell_h, cell_w = CANON_H // GRID_H, CANON_W // GRID_W
    grid = mask.reshape(GRID_H, cell_h, GRID_W, cell_w).mean(axis=(1, 3)).ravel()    # 80
    return np.concatenate([grid, [aspect, fill, foreground_share]])                  # 83


def texture_features(gray: np.ndarray, mask: np.ndarray) -> np.ndarray:
    lbp = local_binary_pattern((gray * 255).astype(np.uint8), LBP_POINTS, LBP_RADIUS, method="uniform")
    region = mask if mask.sum() >= 20 else np.ones_like(mask)
    hist = np.histogram(lbp[region], bins=LBP_POINTS + 2, range=(0, LBP_POINTS + 2))[0]
    hist = hist / max(hist.sum(), 1)                                                 # 10
    gy, gx = np.gradient(gray)
    magnitude = np.sqrt(gx ** 2 + gy ** 2)[region]
    return np.concatenate([hist, [magnitude.mean(), magnitude.std()]])               # 12


def extract_features(file) -> np.ndarray:
    """Photo -> vecteur de N_FEATURES (554) valeurs (float32)."""
    rgb = load_rgb(file)
    canon, mask, aspect, fill, share = _crop_and_resize(rgb, foreground_mask(rgb))
    gray = rgb2gray(canon / 255.0)
    vector = np.concatenate([hog_features(gray), color_features(canon, mask),
                             shape_features(mask, aspect, fill, share), texture_features(gray, mask)])
    return vector.astype(np.float32)


def extract_many(paths, n_jobs=-1) -> np.ndarray:
    """Extraction en parallèle pour tout le dataset."""
    from joblib import Parallel, delayed
    rows = Parallel(n_jobs=n_jobs, batch_size=64)(delayed(extract_features)(p) for p in paths)
    return np.vstack(rows)
