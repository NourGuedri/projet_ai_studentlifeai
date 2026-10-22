from django.contrib import admin

from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("target_title", "target_type", "reason", "status", "reporter", "created_at")
    list_filter = ("status", "target_type", "reason")
    search_fields = ("target_title", "reporter__email")
