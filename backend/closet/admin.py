from django.contrib import admin

from .models import ClothingItem


@admin.register(ClothingItem)
class ClothingItemAdmin(admin.ModelAdmin):
    list_display = ("__str__", "owner", "category", "color", "style", "ai_detected", "created_at")
    list_filter = ("category", "style", "ai_detected")
    search_fields = ("name", "item_type", "owner__email")
