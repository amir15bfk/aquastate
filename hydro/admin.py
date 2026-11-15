from django.contrib import admin

from hydro.models import (
    AIAgentSlot,
    AIContribution,
    Aquifer,
    ClimateDay,
    Country,
    ForecastDay,
    IndexSnapshot,
    Reservoir,
    StorageYear,
)


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("iso2", "name", "region", "data_mode", "last_refresh")
    search_fields = ("iso2", "name")
    list_filter = ("data_mode", "region")


@admin.register(Reservoir)
class ReservoirAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "capacity_mm3", "storage_pct", "storage_source", "is_reference_pool")
    list_filter = ("country", "storage_source", "is_reference_pool")
    search_fields = ("name",)


@admin.register(Aquifer)
class AquiferAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "volume_km3", "trend_m_per_year", "is_fossil")
    list_filter = ("country", "is_fossil")


@admin.register(IndexSnapshot)
class IndexSnapshotAdmin(admin.ModelAdmin):
    list_display = ("country", "created_at", "final_index", "status", "verdict", "confidence")
    list_filter = ("country", "status", "verdict")
    readonly_fields = ("created_at",)


@admin.register(AIAgentSlot)
class AIAgentSlotAdmin(admin.ModelAdmin):
    list_display = ("name", "stage", "enabled", "max_delta", "contract_version")
    list_filter = ("stage", "enabled")


@admin.register(AIContribution)
class AIContributionAdmin(admin.ModelAdmin):
    list_display = ("slot", "snapshot", "stage", "applied", "delta", "created_at")
    list_filter = ("applied", "stage")


admin.site.register(ClimateDay)
admin.site.register(ForecastDay)
admin.site.register(StorageYear)
