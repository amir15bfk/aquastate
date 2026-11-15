"""Pilot country and dam specifications.

Capacities and coordinates are best-available literature values except where
marked. Beni Haroun is deliberately seeded at the signed-off Case B fixture
scale (100 Mm³ / 10 Mm³ dead / 2,000 km² basin) so the demo reproduces the
signed HRI exactly; its metadata records the calibration. Oued El
Tlelat/Tafraoui is marked LOW because its capacity varies across sources.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CountrySeedSpec:
    iso3: str
    name: str
    bbox: tuple[float, float, float, float]
    timezone: str
    baseline_start_year: int = 2000
    baseline_end_year: int = 2025


@dataclass(frozen=True)
class BathymetrySpec:
    max_level_m: float
    levels_m: tuple[float, ...]
    area_fractions: tuple[float, ...]
    max_area_km2: float
    shape_note: str = ""


@dataclass(frozen=True)
class ClimateProfile:
    annual_rain_mm: float
    wet_months: tuple[int, ...]
    pet_mean_mm_day: float
    lst_mean_k: float
    cn_ii: float
    soil_saturation: float
    et_pet_ratio: float
    rain_days_per_year: int = 55


@dataclass(frozen=True)
class CurrentStateSpec:
    fill_pct: float
    demand_m3_day: float
    dry_spell_days: int = 30
    lst_anomaly_k: float = 1.0
    grace_trend_mm_yr: float = -2.0
    design_storm_mm: float | None = None
    storm_total_mm: float = 0.0
    storm_days: int = 0


@dataclass(frozen=True)
class DamSeedSpec:
    slug: str
    name: str
    name_ar: str
    name_fr: str
    country_iso3: str
    basin_name: str
    hydrosheds_id: str
    basin_area_km2: float
    lat: float
    lon: float
    capacity_m3: float
    dead_storage_m3: float
    max_surface_area_km2: float
    dam_type: str
    year_built: int | None
    purposes: tuple[str, ...]
    capacity_confidence: str
    bathymetry: BathymetrySpec
    climate: ClimateProfile
    current: CurrentStateSpec
    metadata: dict = field(default_factory=dict)


PILOT_COUNTRIES: dict[str, CountrySeedSpec] = {
    "DZA": CountrySeedSpec(
        iso3="DZA",
        name="Algeria",
        bbox=(-8.7, 18.9, 12.0, 37.1),
        timezone="Africa/Algiers",
    ),
    "TUN": CountrySeedSpec(
        iso3="TUN",
        name="Tunisia",
        bbox=(7.5, 30.2, 11.6, 37.6),
        timezone="Africa/Tunis",
    ),
}

_DEFAULT_BATHY = BathymetrySpec(
    max_level_m=40.0,
    levels_m=(0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0),
    area_fractions=(0.0, 0.03, 0.08, 0.15, 0.25, 0.45, 0.70, 0.90, 1.0),
    max_area_km2=8.0,
    shape_note="generic widening bowl",
)

# Upper-basin widening is intentional: it lets the projected surface area grow
# faster than projected usable volume, reproducing the signed Case B EESI.
_BENI_BATHY = BathymetrySpec(
    max_level_m=40.0,
    levels_m=(0.0, 10.0, 20.0, 24.0, 28.0, 32.0, 36.0, 40.0),
    area_fractions=(0.0, 0.05, 0.10, 0.15, 0.40, 0.70, 0.90, 1.0),
    max_area_km2=12.0,
    shape_note="steep low stage, wide upper basin",
)


PILOT_DAMS: tuple[DamSeedSpec, ...] = (
    DamSeedSpec(
        slug="beni-haroun",
        name="Beni Haroun",
        name_ar="بني هارون",
        name_fr="Beni Haroun",
        country_iso3="DZA",
        basin_name="Beni Haroun Basin",
        hydrosheds_id="DZA-BENI-HAROUN",
        basin_area_km2=2_000.0,
        lat=36.552,
        lon=6.283,
        capacity_m3=100_000_000.0,
        dead_storage_m3=10_000_000.0,
        max_surface_area_km2=12.0,
        dam_type="embankment",
        year_built=2003,
        purposes=("irrigation", "drinking water", "hydropower"),
        capacity_confidence="CALIBRATED_FIXTURE",
        bathymetry=_BENI_BATHY,
        climate=ClimateProfile(
            annual_rain_mm=650.0,
            wet_months=(10, 11, 12, 1, 2, 3, 4),
            pet_mean_mm_day=4.0,
            lst_mean_k=313.0,
            cn_ii=72.5,
            soil_saturation=1.0,
            et_pet_ratio=0.135,
            rain_days_per_year=95,
        ),
        current=CurrentStateSpec(
            fill_pct=18.0,
            demand_m3_day=600_000.0,
            dry_spell_days=13,
            lst_anomaly_k=2.0,
            grace_trend_mm_yr=-1.5,
            design_storm_mm=65.0,
            storm_total_mm=65.0,
            storm_days=4,
        ),
        metadata={
            "capacity_confidence": "CALIBRATED_FIXTURE",
            "fixture": "MATH_SPEC Case B production fixture",
            "real_capacity_note": "Literature capacity is ~960 Mm³; the MVP uses "
            "the signed-off 100 Mm³ demonstrator scale so the HRI audit fixture "
            "reproduces exactly.",
            "calibration": {"V_max_m3": 100_000_000, "V_dead_m3": 10_000_000,
                            "V_t_m3": 26_200_000, "A_basin_km2": 2_000},
        },
    ),
    DamSeedSpec(
        slug="keddara",
        name="Keddara",
        name_ar="قدارة",
        name_fr="Keddara",
        country_iso3="DZA",
        basin_name="Keddara Basin",
        hydrosheds_id="DZA-KEDDARA",
        basin_area_km2=1_500.0,
        lat=36.650,
        lon=3.417,
        capacity_m3=142_500_000.0,
        dead_storage_m3=14_250_000.0,
        max_surface_area_km2=8.0,
        dam_type="rockfill",
        year_built=1987,
        purposes=("drinking water", "irrigation"),
        capacity_confidence="HIGH",
        bathymetry=_DEFAULT_BATHY,
        climate=ClimateProfile(560.0, (10, 11, 12, 1, 2, 3, 4), 4.2, 312.0, 70.0, 0.72, 0.42, 80),
        current=CurrentStateSpec(54.0, 350_000.0, 21, 0.8, -2.0, 45.0),
    ),
    DamSeedSpec(
        slug="taksebt",
        name="Taksebt",
        name_ar="تاقصبت",
        name_fr="Taksebt",
        country_iso3="DZA",
        basin_name="Taksebt Basin",
        hydrosheds_id="DZA-TAKSEBT",
        basin_area_km2=2_000.0,
        lat=36.783,
        lon=4.150,
        capacity_m3=175_000_000.0,
        dead_storage_m3=17_500_000.0,
        max_surface_area_km2=9.0,
        dam_type="rockfill",
        year_built=2007,
        purposes=("drinking water", "irrigation"),
        capacity_confidence="HIGH",
        bathymetry=_DEFAULT_BATHY,
        climate=ClimateProfile(720.0, (10, 11, 12, 1, 2, 3, 4), 3.9, 311.0, 68.0, 0.80, 0.48, 100),
        current=CurrentStateSpec(61.0, 420_000.0, 18, 0.6, -1.0, 55.0),
    ),
    DamSeedSpec(
        slug="bakhadda",
        name="Bakhadda",
        name_ar="بخدة",
        name_fr="Bakhadda",
        country_iso3="DZA",
        basin_name="Bakhadda Basin",
        hydrosheds_id="DZA-BAKHADDA",
        basin_area_km2=4_500.0,
        lat=35.350,
        lon=1.317,
        capacity_m3=45_000_000.0,
        dead_storage_m3=4_500_000.0,
        max_surface_area_km2=6.0,
        dam_type="earthfill",
        year_built=1986,
        purposes=("irrigation",),
        capacity_confidence="HIGH",
        bathymetry=_DEFAULT_BATHY,
        climate=ClimateProfile(310.0, (10, 11, 12, 1, 2, 3), 5.1, 316.0, 76.0, 0.25, 0.24, 42),
        current=CurrentStateSpec(9.0, 800_000.0, 74, 2.6, -4.0, 25.0),
    ),
    DamSeedSpec(
        slug="oued-el-tlelat-tafraoui",
        name="Oued El Tlelat / Tafraoui",
        name_ar="وادي التلات / تافراوي",
        name_fr="Oued El Tlelat / Tafraoui",
        country_iso3="DZA",
        basin_name="Oued El Tlelat Basin",
        hydrosheds_id="DZA-TLELAT",
        basin_area_km2=1_200.0,
        lat=35.550,
        lon=-0.533,
        capacity_m3=41_000_000.0,
        dead_storage_m3=4_100_000.0,
        max_surface_area_km2=5.0,
        dam_type="earthfill",
        year_built=1988,
        purposes=("irrigation", "drinking water"),
        capacity_confidence="LOW",
        bathymetry=_DEFAULT_BATHY,
        climate=ClimateProfile(340.0, (10, 11, 12, 1, 2, 3), 5.0, 318.0, 78.0, 0.35, 0.28, 38),
        current=CurrentStateSpec(23.0, 180_000.0, 51, 2.1, -3.2, 30.0),
        metadata={"capacity_note": "Capacity varies by source; LOW confidence."},
    ),
    DamSeedSpec(
        slug="brezina",
        name="Brezina",
        name_ar="بريزينة",
        name_fr="Brezina",
        country_iso3="DZA",
        basin_name="Brezina Basin",
        hydrosheds_id="DZA-BREZINA",
        basin_area_km2=3_000.0,
        lat=33.100,
        lon=0.550,
        capacity_m3=125_000_000.0,
        dead_storage_m3=12_500_000.0,
        max_surface_area_km2=7.0,
        dam_type="earthfill",
        year_built=1996,
        purposes=("irrigation",),
        capacity_confidence="HIGH",
        bathymetry=_DEFAULT_BATHY,
        climate=ClimateProfile(220.0, (10, 11, 12, 1, 2, 3), 5.6, 319.0, 80.0, 0.22, 0.20, 30),
        current=CurrentStateSpec(16.0, 300_000.0, 88, 2.9, -4.5, 20.0),
    ),
    DamSeedSpec(
        slug="sidi-salem",
        name="Sidi Salem",
        name_ar="سيدي سالم",
        name_fr="Sidi Salem",
        country_iso3="TUN",
        basin_name="Medjerda Downstream Basin",
        hydrosheds_id="TUN-SIDI-SALEM",
        basin_area_km2=8_000.0,
        lat=36.733,
        lon=9.183,
        capacity_m3=555_000_000.0,
        dead_storage_m3=55_500_000.0,
        max_surface_area_km2=20.0,
        dam_type="earthfill",
        year_built=1981,
        purposes=("irrigation", "drinking water", "flood control"),
        capacity_confidence="HIGH",
        bathymetry=_DEFAULT_BATHY,
        climate=ClimateProfile(470.0, (10, 11, 12, 1, 2, 3, 4), 4.4, 314.0, 74.0, 0.62, 0.38, 62),
        current=CurrentStateSpec(43.0, 1_150_000.0, 34, 1.4, -2.4, 55.0),
    ),
    DamSeedSpec(
        slug="sejnane",
        name="Sejnane",
        name_ar="سجنان",
        name_fr="Sejnane",
        country_iso3="TUN",
        basin_name="Sejnane Basin",
        hydrosheds_id="TUN-SEJNANE",
        basin_area_km2=1_100.0,
        lat=37.050,
        lon=9.233,
        capacity_m3=70_000_000.0,
        dead_storage_m3=7_000_000.0,
        max_surface_area_km2=6.0,
        dam_type="earthfill",
        year_built=2001,
        purposes=("drinking water", "irrigation"),
        capacity_confidence="HIGH",
        bathymetry=_DEFAULT_BATHY,
        climate=ClimateProfile(680.0, (10, 11, 12, 1, 2, 3, 4), 3.7, 310.0, 67.0, 0.85, 0.50, 105),
        current=CurrentStateSpec(58.0, 180_000.0, 12, 0.4, -1.0, 48.0),
    ),
    DamSeedSpec(
        slug="bou-heurtma",
        name="Bou Heurtma",
        name_ar="بوهرتمة",
        name_fr="Bou Heurtma",
        country_iso3="TUN",
        basin_name="Bou Heurtma Basin",
        hydrosheds_id="TUN-BOU-HEURTMA",
        basin_area_km2=1_400.0,
        lat=36.600,
        lon=8.433,
        capacity_m3=117_000_000.0,
        dead_storage_m3=11_700_000.0,
        max_surface_area_km2=7.0,
        dam_type="earthfill",
        year_built=1977,
        purposes=("irrigation", "drinking water", "flood control"),
        capacity_confidence="HIGH",
        bathymetry=_DEFAULT_BATHY,
        climate=ClimateProfile(740.0, (10, 11, 12, 1, 2, 3, 4), 3.8, 310.0, 69.0, 0.88, 0.52, 112),
        current=CurrentStateSpec(64.0, 300_000.0, 10, 0.3, -0.8, 52.0),
    ),
    DamSeedSpec(
        slug="nebhana",
        name="Nebhana",
        name_ar="النبهانة",
        name_fr="Nebhana",
        country_iso3="TUN",
        basin_name="Nebhana Basin",
        hydrosheds_id="TUN-NEBHANA",
        basin_area_km2=2_200.0,
        lat=35.750,
        lon=9.850,
        capacity_m3=78_000_000.0,
        dead_storage_m3=7_800_000.0,
        max_surface_area_km2=6.0,
        dam_type="earthfill",
        year_built=1965,
        purposes=("irrigation",),
        capacity_confidence="HIGH",
        bathymetry=_DEFAULT_BATHY,
        climate=ClimateProfile(360.0, (10, 11, 12, 1, 2, 3), 5.2, 317.0, 77.0, 0.30, 0.26, 40),
        current=CurrentStateSpec(19.0, 250_000.0, 66, 2.3, -3.6, 25.0),
    ),
)

PILOT_DAMS_BY_SLUG = {dam.slug: dam for dam in PILOT_DAMS}
