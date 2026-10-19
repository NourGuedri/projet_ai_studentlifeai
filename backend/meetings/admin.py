from django.contrib import admin

from .models import Meeting


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "date", "status", "consent_confirmed", "created_at")
    list_filter = ("status", "consent_confirmed")
    search_fields = ("title", "owner__email")
    readonly_fields = ("created_at", "updated_at")
