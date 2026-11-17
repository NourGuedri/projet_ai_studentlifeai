from django.contrib import admin

from .models import Meeting, RecordingConsent, RecordingSession


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "date", "status", "processing_status", "consent_confirmed", "created_at")
    list_filter = ("status", "processing_status", "consent_confirmed")
    search_fields = ("title", "owner__email")
    readonly_fields = ("call_room", "processing_status", "processing_error", "created_at", "updated_at")
    filter_horizontal = ("participants",)


class RecordingConsentInline(admin.TabularInline):
    model = RecordingConsent
    extra = 0
    can_delete = False
    readonly_fields = ("user", "accepted", "answered_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(RecordingSession)
class RecordingSessionAdmin(admin.ModelAdmin):
    """Read-only trace of who accepted or refused each recording, and when (exigence 8.1)."""
    list_display = ("meeting", "requested_by", "status", "requested_at", "started_at", "stopped_at")
    list_filter = ("status",)
    search_fields = ("meeting__title", "requested_by__email")
    readonly_fields = ("meeting", "requested_by", "status", "requested_at", "started_at", "stopped_at")
    inlines = [RecordingConsentInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
