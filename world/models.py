"""World-scale models: country profiles, snapshots, hazards and the dam atlas."""
from __future__ import annotations

from django.db import models
from django.utils import timezone


class CountryProfile(models.Model):
    country = models.OneToOneField(
        "hydro.Country", on_delete=models.CASCADE, related_name="world_profile"
    )
    iso2 = models.CharField(max_length=2, db_index=True)
    iso3 = models.CharField(max_length=3, blank=True)
    region = models.CharField(max_length=80, blank=True)
    subregion = models.CharField(max_length=120, blank=True)
    population = models.BigIntegerField(default=0)
    area_km2 = models.FloatField(default=0)

    climate = models.JSONField(default=dict, blank=True)
    hazards = models.JSONField(default=dict, blank=True)
    index = models.JSONField(default=dict, blank=True)
    score = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20, default="no_data")
    confidence = models.FloatField(default=0.0)
    coverage = models.FloatField(default=0.0)
    rank = models.PositiveIntegerField(null=True, blank=True)
    as_of = models.DateField(null=True, blank=True)
    data_mode = models.CharField(max_length=30, default="pending")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-score", "country__name"]
        indexes = [
            models.Index(fields=["score"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.iso2} WCRI={self.score}"


class CountryIndexSnapshot(models.Model):
    country = models.ForeignKey(
        "hydro.Country", on_delete=models.CASCADE, related_name="world_snapshots"
    )
    iso2 = models.CharField(max_length=2, db_index=True)
    as_of = models.DateField(db_index=True)
    score = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20, default="no_data")
    confidence = models.FloatField(default=0.0)
    coverage = models.FloatField(default=0.0)
    rank = models.PositiveIntegerField(null=True, blank=True)
    pillars = models.JSONField(default=dict, blank=True)
    hazards = models.JSONField(default=dict, blank=True)
    index = models.JSONField(default=dict, blank=True)
    version = models.CharField(max_length=20, default="WCRI-2.0")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-as_of", "-id"]
        indexes = [
            models.Index(fields=["iso2", "-as_of"]),
            models.Index(fields=["-score"]),
        ]

    def __str__(self) -> str:
        return f"{self.iso2} {self.as_of} {self.score}"


class DamAtlas(models.Model):
    """A global catalogue row. Inventory only unless `is_monitored` is true."""

    wikidata_id = models.CharField(max_length=40, unique=True, db_index=True)
    name = models.CharField(max_length=240, db_index=True)
    country_iso2 = models.CharField(max_length=2, blank=True, db_index=True)
    country_name = models.CharField(max_length=160, blank=True, db_index=True)
    lat = models.FloatField(db_index=True)
    lon = models.FloatField(db_index=True)
    capacity_m3 = models.FloatField(null=True, blank=True)
    installed_mw = models.FloatField(null=True, blank=True)
    height_m = models.FloatField(null=True, blank=True)
    year_built = models.PositiveIntegerField(null=True, blank=True)
    dam_type = models.CharField(max_length=80, blank=True)
    source = models.CharField(max_length=60, default="Wikidata")
    source_url = models.URLField(blank=True)
    is_monitored = models.BooleanField(default=False, db_index=True)
    pilot_slug = models.CharField(max_length=80, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["country_name", "name"]
        indexes = [
            models.Index(fields=["country_iso2", "name"]),
            models.Index(fields=["lat", "lon"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.country_iso2})"


class HazardEvent(models.Model):
    CATEGORIES = [
        ("drought", "Drought"),
        ("floods", "Flood"),
        ("wildfires", "Wildfire"),
        ("dustHaze", "Dust & haze"),
        ("tempExtremes", "Temperature extreme"),
    ]

    eonet_id = models.CharField(max_length=60, unique=True, db_index=True)
    category = models.CharField(max_length=30, db_index=True)
    title = models.CharField(max_length=300)
    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)
    event_date = models.DateTimeField(null=True, blank=True, db_index=True)
    source = models.CharField(max_length=80, default="NASA EONET")
    source_url = models.URLField(blank=True)
    country_iso2 = models.CharField(max_length=2, blank=True, db_index=True)
    magnitude = models.FloatField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-event_date"]
        indexes = [models.Index(fields=["category", "-event_date"])]

    def __str__(self) -> str:
        return f"{self.category}: {self.title}"


class SourceStatus(models.Model):
    key = models.CharField(max_length=60, unique=True)
    label = models.CharField(max_length=160)
    kind = models.CharField(max_length=30, default="live")
    last_attempt = models.DateTimeField(null=True, blank=True)
    last_success = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    ttl_seconds = models.PositiveIntegerField(default=1800)
    records = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["key"]
        verbose_name_plural = "source statuses"

    def __str__(self) -> str:
        return self.key

    @property
    def is_due(self) -> bool:
        if not self.last_success:
            return True
        return (timezone.now() - self.last_success).total_seconds() >= self.ttl_seconds


class RefreshRun(models.Model):
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    trigger = models.CharField(max_length=30, default="manual")
    status = models.CharField(max_length=20, default="running")
    sources = models.JSONField(default=dict, blank=True)
    countries_updated = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"{self.started_at:%Y-%m-%d %H:%M} {self.status}"


class WorldSnapshot(models.Model):
    version = models.CharField(max_length=40, unique=True)
    as_of = models.DateTimeField(default=timezone.now)
    payload = models.JSONField(default=dict, blank=True)
    summary = models.JSONField(default=dict, blank=True)
    is_current = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"world {self.version}"


class HazardCountryScore(models.Model):
    """Per-country hazard pressure, kept separately for fast layer queries."""

    iso2 = models.CharField(max_length=2, db_index=True)
    category = models.CharField(max_length=30, db_index=True)
    pressure = models.FloatField(default=0.0)
    value = models.FloatField(null=True, blank=True)
    unit = models.CharField(max_length=30, blank=True)
    confidence = models.FloatField(default=0.0)
    source = models.CharField(max_length=160, blank=True)
    as_of = models.DateField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["iso2", "category"]
        unique_together = [("iso2", "category")]
        indexes = [models.Index(fields=["category", "-pressure"])]

    def __str__(self) -> str:
        return f"{self.iso2} {self.category} {self.pressure:.0f}"


class RegionSnapshot(models.Model):
    """Sub-national layers (e.g. Algeria's wilayas) computed with the WCRI-2.0 mathematics."""

    region = models.CharField(max_length=8, db_index=True)
    version = models.CharField(max_length=40, unique=True)
    as_of = models.DateTimeField(default=timezone.now)
    payload = models.JSONField(default=dict, blank=True)
    is_current = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.region} {self.version}"
