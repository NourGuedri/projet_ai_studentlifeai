from rest_framework import serializers

from .ml.labels import COLORS, STYLES, TYPE_TO_CATEGORY
from .models import ClothingItem

MAX_IMAGE_MB = 10


def check_image(image):
    if image.size > MAX_IMAGE_MB * 1024 * 1024:
        raise serializers.ValidationError(f"Image trop lourde (maximum {MAX_IMAGE_MB} Mo).")
    return image


class ClothingItemSerializer(serializers.ModelSerializer):
    item_type = serializers.ChoiceField(choices=sorted(TYPE_TO_CATEGORY))
    color = serializers.ChoiceField(choices=COLORS)
    style = serializers.ChoiceField(choices=STYLES)

    class Meta:
        model = ClothingItem
        fields = ["id", "image", "name", "item_type", "category", "color", "style",
                  "ai_detected", "ai_confidence", "created_at"]
        read_only_fields = ["category", "created_at"]

    def validate_image(self, image):
        return check_image(image)

    def validate(self, attrs):
        # la catégorie découle toujours du type : l'étudiant ne peut pas les rendre incohérents
        if "item_type" in attrs:
            attrs["category"] = TYPE_TO_CATEGORY[attrs["item_type"]]
        return attrs


class AnalyzeSerializer(serializers.Serializer):
    image = serializers.ImageField()

    def validate_image(self, image):
        return check_image(image)
