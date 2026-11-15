from __future__ import annotations

from django.db import models
from django.utils import timezone


class Country(models.Model):
    iso2 = models.CharField(max_length=2, unique=True, db_index=True)
    iso3 = models.CharField(max_length=3, blank=True)
    name = models.CharField(max_length=120)
    official_name = models.CharField(max_length=200, blank=True)
    continent = models.CharField(max_length=60, blank=True)
    region = models.CharField(max_length=80, blank=True)
    subregion = models.CharField(max_length=80, blank=True)
    area_km2 = models.FloatField(default=0)
    population = models.BigIntegerField(default=0)
    lat = models.FloatField(default=0)
    lon = models.FloatField(default=0)
    bbox = models.JSONField(default=list, blank=True)
    has_outline = models.BooleanField(default=False)
    reservoir_demand_mm3_day = models.FloatField(
        default=0, help_text="Reservoir-fed demand allocated to this country, Mm3/day"
    )
    data_mode = models.CharField(
        max_length=20,
        default="pending",
        choices=[
            ("pending", "Pending"),
            ("live", "Live"),
            ("cached", "Cached"),
            ("reference", "Reference"),
            ("fallback", "Fallback"),
        ],
    )
    profile = models.JSONField(default=dict, blank=True)
    last_refresh = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "countries"

    def __str__(self) -> str:
        return f"{self.name} ({self.iso2})"

    def touch_refresh(self) -> None:
        self.last_refresh = timezone.now()
        self.save(update_fields=["last_refresh"])


class Reservoir(models.Model):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="reservoirs")
    name = models.CharField(max_length=160)
    lat = models.FloatField()
    lon = models.FloatField()
    capacity_mm3 = models.FloatField(help_text="Total live capacity, Mm3")
    storage_mm3 = models.FloatField(default=0, help_text="Current live storage, Mm3")
    dead_storage_mm3 = models.FloatField(default=0, help_text="Dead storage, Mm3")
    surface_area_km2 = models.FloatField(default=0)
    inflow_mm3_day = models.FloatField(default=0)
    demand_mm3_day = models.FloatField(default=0)
    reference_storage_pct = models.FloatField(
        default=0, help_text="Screening reference storage percent, when available"
    )
    storage_source = models.CharField(
        max_length=30,
        default="modeled",
        choices=[
            ("reference", "Reference inventory"),
            ("modeled", "Modeled reconstruction"),
            ("blended", "Blended reference + reconstruction"),
            ("osm", "OpenStreetMap inventory"),
            ("synthetic", "Synthetic reference pool"),
        ],
    )
    is_reference_pool = models.BooleanField(
        default=False,
        help_text="A national screening pool, not a physical dam",
    )
    source_name = models.CharField(max_length=200, blank=True)
    source_url = models.URLField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-capacity_mm3", "name"]
        unique_together = [("country", "name", "lat", "lon")]

    def __str__(self) -> str:
        return f"{self.name} — {self.country.iso2}"

    @property
    def live_capacity(self) -> float:
        return max(0.0, self.capacity_mm3 - self.dead_storage_mm3)

    @property
    def storage_pct(self) -> float:
        if self.capacity_mm3 <= 0:
            return 0.0
        return max(0.0, min(100.0, 100.0 * self.storage_mm3 / self.capacity_mm3))


class Aquifer(models.Model):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="aquifers")
    name = models.CharField(max_length=200)
    lat = models.FloatField(default=0)
    lon = models.FloatField(default=0)
    volume_km3 = models.FloatField(default=0)
    recharge_mm3_day = models.FloatField(default=0)
    extraction_mm3_day = models.FloatField(default=0)
    trend_m_per_year = models.FloatField(
        default=0, help_text="Positive = recovering water table; negative = declining"
    )
    is_fossil = models.BooleanField(default=False)
    shared_with = models.CharField(max_length=120, blank=True)
    source_name = models.CharField(max_length=240, blank=True)
    source_url = models.URLField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-volume_km3", "name"]

    def __str__(self) -> str:
        return self.name


class ClimateDay(models.Model):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="climate_days")
    date = models.DateField(db_index=True)
    precip_mm = models.FloatField(default=0)
    soil_surface = models.FloatField(null=True, blank=True)
    soil_root = models.FloatField(null=True, blank=True)
    et0_mm = models.FloatField(null=True, blank=True)
    source = models.CharField(max_length=80, default="NASA POWER")
    fetched_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [("country", "date")]
        ordering = ["date"]

    def __str__(self) -> str:
        return f"{self.country.iso2} {self.date}"


class ForecastDay(models.Model):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="forecast_days")
    reservoir = models.ForeignKey(
        Reservoir, on_delete=models.CASCADE, null=True, blank=True, related_name="forecast_days"
    )
    date = models.DateField(db_index=True)
    precip_mm = models.FloatField(default=0)
    et0_mm = models.FloatField(null=True, blank=True)
    temp_max_c = models.FloatField(null=True, blank=True)
    source = models.CharField(max_length=80, default="Open-Meteo")
    fetched_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [("country", "reservoir", "date")]
        ordering = ["date"]

    def __str__(self) -> str:
        return f"{self.country.iso2} {self.date}"


class StorageYear(models.Model):
    reservoir = models.ForeignKey(Reservoir, on_delete=models.CASCADE, related_name="storage_years")
    year = models.IntegerField()
    end_storage_pct = models.FloatField()
    source = models.CharField(max_length=80, default="Modeled reconstruction")

    class Meta:
        unique_together = [("reservoir", "year")]
        ordering = ["year"]

    def __str__(self) -> str:
        return f"{self.reservoir.name} {self.year}: {self.end_storage_pct:.0f}%"


class IndexSnapshot(models.Model):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="snapshots")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    scenario = models.JSONField(default=dict, blank=True)
    base_index = models.FloatField(default=0)
    final_index = models.FloatField(default=0)
    status = models.CharField(max_length=20, default="unknown")
    verdict = models.CharField(max_length=40, default="unknown")
    horizon_state = models.CharField(max_length=20, default="unknown")
    pillars = models.JSONField(default=list, blank=True)
    horizon = models.JSONField(default=dict, blank=True)
    narrative = models.TextField(blank=True)
    confidence = models.FloatField(default=0)
    data_quality = models.JSONField(default=dict, blank=True)
    formula_version = models.CharField(max_length=20, default="WRI-1.0")
    ai_trace = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        get_latest_by = "created_at"

    def __str__(self) -> str:
        return f"{self.country.iso2} {self.final_index:.1f} {self.status}"


class AIAgentSlot(models.Model):
    STAGES = [
        ("post_subindex_advice", "Post sub-index advice"),
        ("horizon_narrative", "Horizon narrative"),
        ("confidence_calibration", "Confidence calibration"),
        ("anomaly_explanation", "Anomaly explanation"),
    ]

    name = models.CharField(max_length=120, unique=True)
    stage = models.CharField(max_length=40, choices=STAGES)
    description = models.TextField(blank=True)
    enabled = models.BooleanField(default=False)
    max_delta = models.FloatField(default=5.0)
    weight = models.FloatField(default=0.0)
    contract_version = models.CharField(max_length=20, default="1.0")
    endpoint = models.CharField(max_length=240, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["stage", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.stage}{' on' if self.enabled else ' off'})"


class AIContribution(models.Model):
    snapshot = models.ForeignKey(
        IndexSnapshot, on_delete=models.CASCADE, related_name="ai_contributions"
    )
    slot = models.ForeignKey(AIAgentSlot, on_delete=models.PROTECT, related_name="contributions")
    stage = models.CharField(max_length=40)
    proposed = models.JSONField(default=dict, blank=True)
    applied = models.BooleanField(default=False)
    delta = models.FloatField(default=0)
    confidence = models.FloatField(default=0)
    rationale = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.slot.name} → {self.snapshot_id} ({'applied' if self.applied else 'held'})"
