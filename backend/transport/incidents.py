"""Types d'incidents connus des modèles ML (voir ml/models/metrics.json).

Bus et tramway : catégories lisibles de la TTC, traduites en français.
Métro : la TTC n'utilise que des codes internes ; on les affiche tels quels.
"""

LABELS = {
    "MECHANICAL": "Panne mécanique",
    "OPERATIONS - OPERATOR": "Problème lié au conducteur",
    "OPERATIONS": "Problème d'exploitation",
    "GENERAL DELAY": "Retard général",
    "DIVERSION": "Déviation",
    "COLLISION - TTC": "Collision",
    "EMERGENCY SERVICES": "Intervention des secours",
    "SECURITY": "Sécurité",
    "CLEANING - UNSANITARY": "Nettoyage / insalubrité",
    "INVESTIGATION": "Enquête / contrôle",
    "UTILIZED OFF ROUTE": "Véhicule retiré de la ligne",
    "VISION": "Panne du système embarqué",
    "AUTRE": "Autre",
}

METRO_CODES = ["SUDP", "MUIS", "SUO", "MUPAA", "MUIRS", "PUOPO", "MUO", "PUMEL"]


def choices_for(mode):
    """Liste (valeur, libellé) des incidents proposés pour un moyen de transport."""
    if mode == "metro":
        return [(code, f"Code TTC {code}") for code in METRO_CODES] + [("AUTRE", "Autre")]
    return list(LABELS.items())


def label(incident):
    return LABELS.get(incident) or f"Code TTC {incident}"