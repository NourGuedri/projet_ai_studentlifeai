from django.contrib import admin

from .models import EmailMessage


@admin.register(EmailMessage)
class EmailMessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "sender", "owner", "received_at", "is_important", "created_at")
    list_filter = ("is_important",)
    search_fields = ("subject", "sender", "owner__email")
    readonly_fields = ("created_at",)
