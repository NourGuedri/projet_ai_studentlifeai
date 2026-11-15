from django.conf import settings
from django.db import models

from .ml.labels import CATEGORIES

User = settings.AUTH_USER_MODEL


class ClothingItem(models.Model):
    """Un vêtement de la garde-robe numérique d'un étudiant (US 37)."""

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="clothing_items")
    image = models.ImageField(upload_to="closet/%Y/%m/")
    name = models.CharField(max_length=80, blank=True)
    item_type = models.CharField(max_length=40)                    # T-shirt, Jean, Baskets...
    category = models.CharField(max_length=12, choices=CATEGORIES)  # déduit de item_type
    color = models.CharField(max_length=30)
    style = models.CharField(max_length=12)                        # Casual / Formel / Sport
    ai_detected = models.BooleanField(default=False)               # proposé par l'IA (puis validé par l'étudiant)
    ai_confidence = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "vêtement"

    def __str__(self):
        return self.name or f"{self.item_type} {self.color.lower()}"
