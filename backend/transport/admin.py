from django.contrib import admin

from .models import Incident, Trip


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ("__str__", "student", "departure_time", "mode", "seats_available")
    list_filter = ("mode",)
    search_fields = ("departure", "destination", "student__email")


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ("__str__", "reporter", "estimated_delay_min", "long_delay_probability",
                    "is_long_delay", "notified_count")
    list_filter = ("mode", "is_long_delay")