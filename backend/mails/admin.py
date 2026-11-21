from django.contrib import admin

from .models import EmailMessage, GmailAccount


@admin.register(EmailMessage)
class EmailMessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "sender", "owner", "source", "received_at", "is_important", "created_at")
    list_filter = ("is_important", "source")
    search_fields = ("subject", "sender", "owner__email")
    readonly_fields = ("created_at", "gmail_id", "gmail_thread_id")


@admin.register(GmailAccount)
class GmailAccountAdmin(admin.ModelAdmin):
    list_display = ("email", "user", "connected_at", "last_synced_at")
    search_fields = ("email", "user__email")
    exclude = ("refresh_token_encrypted",)  # the encrypted token is never displayed
    readonly_fields = ("email", "user", "connected_at", "last_synced_at")
