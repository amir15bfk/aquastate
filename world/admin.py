from django.contrib import admin

from world.models import (
    CountryIndexSnapshot,
    CountryProfile,
    DamAtlas,
    HazardCountryScore,
    HazardEvent,
    RefreshRun,
    SourceStatus,
    WorldSnapshot,
)


@admin.register(CountryProfile)
class CountryProfileAdmin(admin.ModelAdmin):
    list_display = ("iso2", "score", "status", "confidence", "rank", "updated_at")
    list_filter = ("status", "data_mode")
    search_fields = ("iso2", "iso3", "country__name")


@admin.register(CountryIndexSnapshot)
class CountryIndexSnapshotAdmin(admin.ModelAdmin):
    list_display = ("iso2", "as_of", "score", "status", "rank")
    list_filter = ("status", "version")
    search_fields = ("iso2",)


@admin.register(DamAtlas)
class DamAtlasAdmin(admin.ModelAdmin):
    list_display = ("name", "country_iso2", "capacity_m3", "height_m", "is_monitored")
    list_filter = ("is_monitored", "country_iso2")
    search_fields = ("name", "country_name", "wikidata_id")


@admin.register(HazardEvent)
class HazardEventAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "country_iso2", "event_date", "source")
    list_filter = ("category",)
    search_fields = ("title",)


@admin.register(HazardCountryScore)
class HazardCountryScoreAdmin(admin.ModelAdmin):
    list_display = ("iso2", "category", "pressure", "value", "confidence", "as_of")
    list_filter = ("category",)
    search_fields = ("iso2",)


@admin.register(SourceStatus)
class SourceStatusAdmin(admin.ModelAdmin):
    list_display = ("key", "label", "kind", "last_success", "records", "latency_ms")
    list_filter = ("kind",)


@admin.register(RefreshRun)
class RefreshRunAdmin(admin.ModelAdmin):
    list_display = ("started_at", "trigger", "status", "countries_updated")
    list_filter = ("status", "trigger")


@admin.register(WorldSnapshot)
class WorldSnapshotAdmin(admin.ModelAdmin):
    list_display = ("version", "as_of", "is_current", "created_at")
    list_filter = ("is_current",)
