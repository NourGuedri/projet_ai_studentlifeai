"""Moteur de recommandation de tenue : règles météo + harmonie des couleurs.

Volontairement simple et explicable (règles métier, pas de ML) : la météo décide des couches
et des chaussures, les couleurs neutres servent de liant. Résultat reproductible avec `seed`.
"""
import random

from .ml.labels import JACKET_TYPES, KNIT_TYPES, LIGHT_BOTTOMS, NEUTRAL_COLORS, OPEN_SHOES


def _temperature_band(feels_like):
    if feels_like < 12:
        return "cold"
    if feels_like < 18:
        return "cool"
    if feels_like < 24:
        return "mild"
    return "hot"


def recommend(items, weather, style=None, seed=None):
    rng = random.Random(seed)
    band = _temperature_band(weather["feels_like"])
    rain = weather["rain"]
    advice, missing, chosen = [], [], []

    by_cat = {}
    for item in items:
        by_cat.setdefault(item.category, []).append(item)

    def pick(candidates):
        """Meilleur candidat : style demandé + couleur qui s'accorde avec ce qui est déjà choisi."""
        if not candidates:
            return None
        colored = {c.color for c in chosen if c.color not in NEUTRAL_COLORS}

        def score(it):
            s = rng.random()
            if style and it.style == style:
                s += 1.5
            if it.color in NEUTRAL_COLORS:
                s += 1
            elif not colored or it.color in colored:
                s += 0.5          # une seule couleur vive à la fois
            else:
                s -= 1
            return s
        best = max(candidates, key=score)
        chosen.append(best)
        return best

    def pool(category, exclude_types=(), only_types=None):
        out = [i for i in by_cat.get(category, [])
               if i.item_type not in exclude_types and (only_types is None or i.item_type in only_types)]
        return out

    # --- base : robe, ou haut + bas
    use_dress = bool(by_cat.get("Robe")) and (band in ("mild", "hot") and not rain) and rng.random() < 0.4
    if use_dress:
        pick(pool("Robe"))
    else:
        pick(pool("Haut"))
        bottoms = pool("Bas", exclude_types=LIGHT_BOTTOMS if band in ("cold", "cool") else ())
        if not bottoms and band in ("cold", "cool") and by_cat.get("Bas"):
            bottoms = pool("Bas")
            advice.append("Il fait frais : prévoyez des collants ou un vêtement chaud avec ce bas léger.")
        pick(bottoms)

    # --- couches selon la température et la pluie
    knits, jackets = pool("Couche", only_types=KNIT_TYPES), pool("Couche", only_types=JACKET_TYPES)
    need = {"cold": 2, "cool": 1, "mild": 1 if rain else 0, "hot": 1 if rain else 0}[band]
    placed = 0
    if band == "cold":
        placed += pick(knits) is not None      # pull d'abord, veste par-dessus
        placed += pick(jackets) is not None
    elif band == "cool":
        placed += pick(jackets if rain and jackets else knits + jackets) is not None
    elif rain:
        placed += pick(jackets) is not None
    if placed < need:
        missing.append("Aucune veste ou aucun pull adapté dans votre dressing : "
                       "ajoutez-en un pour les jours de froid ou de pluie.")

    # --- chaussures
    avoid_open = rain or band in ("cold", "cool")
    shoes = pool("Chaussures", exclude_types=OPEN_SHOES if avoid_open else ())
    if not shoes and by_cat.get("Chaussures"):
        shoes = pool("Chaussures")
        advice.append("Vos chaussures ouvertes ne sont pas idéales par ce temps.")
    pick(shoes)

    required = [("Robe", "une robe")] if use_dress else [("Haut", "un haut"), ("Bas", "un bas")]
    for cat, label in required + [("Chaussures", "des chaussures")]:
        if not by_cat.get(cat):
            missing.append(f"Ajoutez {label} à votre dressing pour obtenir une tenue complète.")

    if rain:
        advice.append("Il pleut : pensez au parapluie.")
    if band == "hot":
        advice.append("Il fait chaud : privilégiez des vêtements légers et pensez à vous hydrater.")
    if band == "cold":
        advice.append("Il fait froid : superposez les couches.")

    return {"items": chosen, "advice": advice, "missing": list(dict.fromkeys(missing))}
