"""Country-agnostic domain models for the hydrological resilience MVP.

All physical quantities are stored in SI units: metres, square metres, cubic
metres, cubic metres per day, millimetres and millimetres per day. GeoJSON is
kept in JSONField so the project needs no GeoDjango/GDAL dependency.
"""
from django.db import models


class Country(models.Model):
    iso3 = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=120)
    bbox = models.JSONField(default=list, blank=True)
    timezone = models.CharField(max_length=64, default="UTC")
    baseline_start = models.DateField()
    baseline_end = models.DateField()
    data_provider = models.CharField(max_length=40, default="seeded")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["iso3"]
        verbose_name_plural = "countries"

    def __str__(self):
        return f"{self.iso3} — {self.name}"


class Basin(models.Model):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="basins")
    hydrosheds_id = models.CharField(max_length=40)
    name = models.CharField(max_length=160)
    area_km2 = models.FloatField()
    geometry = models.JSONField(default=dict, blank=True)
    centroid_lat = models.FloatField()
    centroid_lon = models.FloatField()
    source = models.CharField(max_length=80, default="seeded")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["country__iso3", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["country", "hydrosheds_id"], name="unique_basin_per_country"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.area_km2:,.0f} km²)"


class Dam(models.Model):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="dams")
    basin = models.ForeignKey(Basin, on_delete=models.PROTECT, related_name="dams")
    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    name_ar = models.CharField(max_length=160, blank=True)
    name_fr = models.CharField(max_length=160, blank=True)
    lat = models.FloatField()
    lon = models.FloatField()
    capacity_m3 = models.FloatField()
    dead_storage_m3 = models.FloatField(default=0.0)
    max_surface_area_km2 = models.FloatField(null=True, blank=True)
    dam_type = models.CharField(max_length=60, blank=True)
    year_built = models.PositiveIntegerField(null=True, blank=True)
    purposes = models.JSONField(default=list, blank=True)
    source_ids = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["country__iso3", "name"]

    @property
    def usable_capacity_m3(self) -> float:
        return self.capacity_m3 - self.dead_storage_m3

    def __str__(self):
        return self.name


class BathymetryPoint(models.Model):
    dam = models.ForeignKey(Dam, on_delete=models.CASCADE, related_name="bathymetry")
    elevation_m = models.FloatField()
    area_km2 = models.FloatField()
    volume_m3 = models.FloatField()
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ["dam", "order"]
        constraints = [
            models.UniqueConstraint(fields=["dam", "order"], name="unique_bathymetry_order")
        ]

    def __str__(self):
        return f"{self.dam} @ {self.elevation_m:.1f} m"


class ReservoirObservation(models.Model):
    dam = models.ForeignKey(Dam, on_delete=models.CASCADE, related_name="observations")
    date = models.DateField()
    water_area_km2 = models.FloatField(null=True, blank=True)
    water_level_m = models.FloatField(null=True, blank=True)
    volume_m3 = models.FloatField(null=True, blank=True)
    fill_pct = models.FloatField(null=True, blank=True)
    source = models.CharField(max_length=80, default="seeded")
    quality = models.CharField(max_length=20, default="OK")

    class Meta:
        ordering = ["dam", "date"]
        constraints = [
            models.UniqueConstraint(fields=["dam", "date"], name="unique_reservoir_obs")
        ]

    def __str__(self):
        return f"{self.dam} {self.date}"


class ClimateObservation(models.Model):
    basin = models.ForeignKey(Basin, on_delete=models.CASCADE, related_name="climate")
    date = models.DateField()
    precip_mm = models.FloatField(null=True, blank=True)
    et_mm = models.FloatField(null=True, blank=True)
    pet_mm = models.FloatField(null=True, blank=True)
    lst_k = models.FloatField(null=True, blank=True)
    soil_moisture_m3m3 = models.FloatField(null=True, blank=True)
    source = models.CharField(max_length=80, default="seeded")

    class Meta:
        ordering = ["basin", "date"]
        constraints = [
            models.UniqueConstraint(fields=["basin", "date"], name="unique_climate_obs")
        ]

    def __str__(self):
        return f"{self.basin} {self.date}"


class ForecastObservation(models.Model):
    basin = models.ForeignKey(Basin, on_delete=models.CASCADE, related_name="forecasts")
    issued_at = models.DateTimeField()
    date = models.DateField()
    precip_mm = models.FloatField(null=True, blank=True)
    source = models.CharField(max_length=80, default="seeded")
    confidence = models.FloatField(default=1.0)

    class Meta:
        ordering = ["basin", "issued_at", "date"]
        constraints = [
            models.UniqueConstraint(
                fields=["basin", "issued_at", "date"], name="unique_forecast_obs"
            )
        ]

    def __str__(self):
        return f"{self.basin} {self.date}"


class GraceObservation(models.Model):
    basin = models.ForeignKey(Basin, on_delete=models.CASCADE, related_name="grace")
    month = models.DateField()
    twsa_mm = models.FloatField(null=True, blank=True)
    smsa_mm = models.FloatField(null=True, blank=True)
    swsa_mm = models.FloatField(null=True, blank=True)
    source = models.CharField(max_length=80, default="seeded")

    class Meta:
        ordering = ["basin", "month"]
        constraints = [
            models.UniqueConstraint(fields=["basin", "month"], name="unique_grace_month")
        ]

    def __str__(self):
        return f"{self.basin} {self.month:%Y-%m}"


class DemandObservation(models.Model):
    dam = models.ForeignKey(Dam, on_delete=models.CASCADE, related_name="demands")
    date = models.DateField()
    demand_m3_day = models.FloatField()
    source = models.CharField(max_length=80, default="seeded")

    class Meta:
        ordering = ["dam", "date"]
        constraints = [
            models.UniqueConstraint(fields=["dam", "date"], name="unique_demand_obs")
        ]

    def __str__(self):
        return f"{self.dam} {self.date}"


class ClimatologyBin(models.Model):
    scope_type = models.CharField(max_length=20, default="basin")
    scope_id = models.CharField(max_length=80)
    metric = models.CharField(max_length=40)
    week = models.PositiveSmallIntegerField()
    values = models.JSONField(default=list, blank=True)
    n = models.PositiveIntegerField(default=0)
    mean = models.FloatField(null=True, blank=True)
    std = models.FloatField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scope_type", "scope_id", "metric", "week"]
        constraints = [
            models.UniqueConstraint(
                fields=["scope_type", "scope_id", "metric", "week"],
                name="unique_climatology_bin",
            )
        ]

    def __str__(self):
        return f"{self.scope_id} {self.metric} w{self.week}"


class IndexSnapshot(models.Model):
    dam = models.ForeignKey(Dam, on_delete=models.CASCADE, related_name="snapshots")
    as_of = models.DateField()
    week = models.PositiveSmallIntegerField(null=True, blank=True)
    hri = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20, default="NO_DATA")
    confidence = models.FloatField(default=0.0)
    phi = models.FloatField(default=0.0)
    sub_indices = models.JSONField(default=dict, blank=True)
    contributions = models.JSONField(default=dict, blank=True)
    components = models.JSONField(default=dict, blank=True)
    explanation = models.TextField(blank=True)
    analog_years = models.JSONField(default=list, blank=True)
    data_mode = models.CharField(max_length=40, default="seeded")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-as_of", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["dam", "as_of", "data_mode"], name="unique_snapshot_per_day_mode"
            )
        ]

    def __str__(self):
        return f"{self.dam} {self.as_of} HRI={self.hri}"


class ScenarioRun(models.Model):
    dam = models.ForeignKey(Dam, on_delete=models.CASCADE, related_name="scenario_runs")
    as_of = models.DateField()
    overrides = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    session_key = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Scenario {self.dam} {self.as_of}"
