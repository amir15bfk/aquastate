from django.contrib import admin

from .models import (
    Basin,
    BathymetryPoint,
    ClimatologyBin,
    ClimateObservation,
    Country,
    Dam,
    DemandObservation,
    ForecastObservation,
    GraceObservation,
    IndexSnapshot,
    ReservoirObservation,
    ScenarioRun,
)


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("iso3", "name", "data_provider")
    search_fields = ("iso3", "name")


@admin.register(Basin)
class BasinAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "area_km2")
    list_filter = ("country",)
    search_fields = ("name", "hydrosheds_id")


@admin.register(Dam)
class DamAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "capacity_m3", "dead_storage_m3")
    list_filter = ("country", "dam_type")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(BathymetryPoint)
class BathymetryPointAdmin(admin.ModelAdmin):
    list_display = ("dam", "order", "elevation_m", "area_km2", "volume_m3")
    list_filter = ("dam",)


@admin.register(ReservoirObservation)
class ReservoirObservationAdmin(admin.ModelAdmin):
    list_display = ("dam", "date", "fill_pct", "volume_m3", "quality")
    list_filter = ("dam", "quality")
    date_hierarchy = "date"


@admin.register(ClimateObservation)
class ClimateObservationAdmin(admin.ModelAdmin):
    list_display = ("basin", "date", "precip_mm", "et_mm", "pet_mm")
    list_filter = ("basin",)
    date_hierarchy = "date"


@admin.register(ForecastObservation)
class ForecastObservationAdmin(admin.ModelAdmin):
    list_display = ("basin", "date", "precip_mm", "confidence")
    list_filter = ("basin",)


@admin.register(GraceObservation)
class GraceObservationAdmin(admin.ModelAdmin):
    list_display = ("basin", "month", "twsa_mm", "smsa_mm", "swsa_mm")
    list_filter = ("basin",)


@admin.register(DemandObservation)
class DemandObservationAdmin(admin.ModelAdmin):
    list_display = ("dam", "date", "demand_m3_day")
    list_filter = ("dam",)


@admin.register(ClimatologyBin)
class ClimatologyBinAdmin(admin.ModelAdmin):
    list_display = ("scope_type", "scope_id", "metric", "week", "n", "mean")
    list_filter = ("metric", "scope_type")


@admin.register(IndexSnapshot)
class IndexSnapshotAdmin(admin.ModelAdmin):
    list_display = ("dam", "as_of", "hri", "status", "phi", "data_mode")
    list_filter = ("status", "data_mode", "dam")
    date_hierarchy = "as_of"


@admin.register(ScenarioRun)
class ScenarioRunAdmin(admin.ModelAdmin):
    list_display = ("dam", "as_of", "created_at")
    list_filter = ("dam",)
