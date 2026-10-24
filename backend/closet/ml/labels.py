"""Vocabulaire partagé entre l'entraînement, la prédiction et l'API Django.

Aucune dépendance (ni torch ni Django) : ce fichier peut être importé partout.
Les clés anglaises sont celles de la colonne `articleType` du dataset
« Fashion Product Images (Small) » ; les valeurs françaises sont ce que voit l'étudiant.
"""

# type de vêtement (dataset, anglais) -> catégorie
ARTICLE_TO_CATEGORY = {
    "Tshirts": "Haut", "Shirts": "Haut", "Tops": "Haut",
    "Sweaters": "Couche", "Sweatshirts": "Couche", "Jackets": "Couche",
    "Jeans": "Bas", "Trousers": "Bas", "Shorts": "Bas", "Skirts": "Bas", "Track Pants": "Bas",
    "Dresses": "Robe",
    "Casual Shoes": "Chaussures", "Sports Shoes": "Chaussures",
    "Heels": "Chaussures", "Flats": "Chaussures", "Sandals": "Chaussures",
}

ARTICLE_FR = {
    "Tshirts": "T-shirt", "Shirts": "Chemise", "Tops": "Top",
    "Sweaters": "Pull", "Sweatshirts": "Sweat", "Jackets": "Veste",
    "Jeans": "Jean", "Trousers": "Pantalon", "Shorts": "Short", "Skirts": "Jupe", "Track Pants": "Jogging",
    "Dresses": "Robe",
    "Casual Shoes": "Chaussures casual", "Sports Shoes": "Baskets",
    "Heels": "Talons", "Flats": "Ballerines", "Sandals": "Sandales",
}

COLOR_FR = {
    "White": "Blanc", "Black": "Noir", "Grey": "Gris", "Charcoal": "Anthracite",
    "Blue": "Bleu", "Navy Blue": "Bleu marine", "Turquoise Blue": "Turquoise", "Teal": "Sarcelle",
    "Red": "Rouge", "Maroon": "Bordeaux", "Pink": "Rose", "Magenta": "Magenta",
    "Green": "Vert", "Olive": "Olive", "Khaki": "Kaki",
    "Yellow": "Jaune", "Mustard": "Moutarde", "Orange": "Orange", "Rust": "Rouille",
    "Brown": "Marron", "Tan": "Camel", "Beige": "Beige", "Cream": "Crème",
    "Purple": "Violet", "Lavender": "Lavande", "Peach": "Pêche",
    "Silver": "Argent", "Gold": "Doré", "Multi": "Multicolore",
}

STYLE_FR = {"Casual": "Casual", "Formal": "Formel", "Sports": "Sport"}

# ---- vocabulaire exposé à l'API / au frontend
CATEGORIES = [
    ("Haut", "Hauts"), ("Bas", "Bas"), ("Couche", "Vestes et pulls"),
    ("Robe", "Robes"), ("Chaussures", "Chaussures"),
]
TYPE_TO_CATEGORY = {ARTICLE_FR[a]: c for a, c in ARTICLE_TO_CATEGORY.items()}
TYPES_BY_CATEGORY = {c: [t for t, cat in TYPE_TO_CATEGORY.items() if cat == c] for c, _ in CATEGORIES}
COLORS = list(COLOR_FR.values())
STYLES = list(STYLE_FR.values())

# ---- règles de recommandation
NEUTRAL_COLORS = {"Blanc", "Noir", "Gris", "Anthracite", "Beige", "Crème", "Bleu marine", "Argent", "Camel"}
LIGHT_BOTTOMS = {"Short", "Jupe"}                       # trop léger quand il fait frais
OPEN_SHOES = {"Sandales", "Talons", "Ballerines"}       # à éviter sous la pluie / par temps frais
JACKET_TYPES = {"Veste"}
KNIT_TYPES = {"Pull", "Sweat"}
