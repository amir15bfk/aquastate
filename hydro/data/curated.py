"""Curated screening inventories for the two demo countries.

Capacity figures are public, screening-level values compiled from dam
inventories and public reference pages. They are not operational telemetry.
Storage percentages are deliberately reference estimates and are blended with
a mass-balance reconstruction from NASA POWER precipitation.
"""
from __future__ import annotations

CURATED_COUNTRIES = {
    "DZ": {
        "demand_mm3_day": 13.8,
        "note": "Reservoir-fed municipal, industrial and irrigation demand allocation.",
        "source": "Public dam inventories / ANBT screening compilation",
    },
    "TN": {
        "demand_mm3_day": 4.2,
        "note": "Reservoir-fed demand allocation for the northern dam system.",
        "source": "Public dam inventories / DGRE screening compilation",
    },
}

# name, lat, lon, capacity Mm3, reference storage %, source slug
RESERVOIRS = {
    "DZ": [
        ("Beni Haroun", 36.55, 6.28, 960, 18, "Beni_Haroun_Dam"),
        ("Koudiat Acerdoune", 36.36, 3.88, 640, 16, "Koudiat_Acerdoune_Dam"),
        ("Gargar", 35.85, 0.58, 450, 14, "Gargar_Dam"),
        ("Djorf Torba", 31.50, -2.55, 360, 12, "Djorf_Torba_Dam"),
        ("Ghrib", 36.18, 2.23, 280, 17, "Ghrib_Dam"),
        ("Oued Fodda", 36.25, 1.55, 228, 21, "Oued_Fodda_Dam"),
        ("Hammam Boughrara", 34.93, -1.38, 177, 26, "Hammam_Boughrara_Dam"),
        ("Taksebt", 36.72, 4.05, 175, 23, "Taksebt_Dam"),
        ("Cheffia", 36.70, 8.30, 171, 28, "Cheffia_Dam"),
        ("Keddara", 36.64, 3.42, 146, 25, "Keddara_Dam"),
        ("Bakhadda", 35.42, 1.30, 105, 15, "Bakhadda_Dam"),
        ("Tichy Haf", 36.55, 5.10, 81, 19, "Tichy_Haf_Dam"),
        ("Mexa", 36.76, 8.08, 70, 27, "Mexa_Dam"),
        ("Beni Bahdel", 34.68, -1.57, 64, 20, "Beni_Bahdel_Dam"),
        ("Bougous", 36.65, 8.45, 60, 24, "Bougous_Dam"),
        ("Foum El Gherza", 34.90, 5.90, 47, 11, "Foum_El_Gherza_Dam"),
    ],
    "TN": [
        ("Sidi Salem", 36.72, 9.15, 555, 24, "Sidi_Salem_Dam"),
        ("Sidi Saad", 35.38, 9.70, 240, 19, "Sidi_Saad_Dam"),
        ("Joumine", 36.95, 9.42, 130, 28, "Joumine_Dam"),
        ("Sejnane", 37.10, 9.22, 124, 31, "Sejnane_Dam"),
        ("Bouhertma", 36.55, 8.58, 112, 27, "Bouhertma_Dam"),
        ("El Houareb", 35.60, 9.85, 100, 21, "El_Houareb_Dam"),
        ("Kasseb", 36.62, 8.90, 90, 29, "Kasseb_Dam"),
        ("Ichkeul", 37.16, 9.65, 84, 35, "Ichkeul_Dam"),
        ("Bir M'Cherga", 36.38, 9.90, 80, 23, "Bir_M'Cherga_Dam"),
        ("Zarga", 37.18, 9.35, 80, 26, "Zarga_Dam"),
        ("Beni Mtir", 36.58, 8.75, 77, 30, "Beni_Mtir_Dam"),
        ("Nebhana", 35.70, 10.40, 65, 17, "Nebhana_Dam"),
    ],
}

# name, volume km3, recharge km3/yr, extraction km3/yr, trend m/yr, fossil, shared_with
AQUIFERS = {
    "DZ": [
        (
            "Continental Intercalaire (SASS)",
            30000,
            0.45,
            2.40,
            -1.10,
            True,
            "Algeria · Tunisia · Libya",
        ),
        (
            "Complexe Terminal (SASS)",
            10000,
            0.30,
            1.40,
            -0.75,
            True,
            "Algeria · Tunisia · Libya",
        ),
        (
            "Chelif alluvial aquifer",
            120,
            0.12,
            0.35,
            -0.60,
            False,
            "Algeria",
        ),
    ],
    "TN": [
        (
            "Continental Intercalaire (SASS)",
            30000,
            0.15,
            0.90,
            -1.20,
            True,
            "Algeria · Tunisia · Libya",
        ),
        (
            "Cap Bon aquifer",
            70,
            0.06,
            0.14,
            -1.10,
            False,
            "Tunisia",
        ),
        (
            "Sahel aquifer",
            150,
            0.10,
            0.20,
            -0.80,
            False,
            "Tunisia",
        ),
    ],
}

KM3_YEAR_TO_MM3_DAY = 1000.0 / 365.0

# Approximate centroid of each mapped system, for the map's groundwater layer.
AQUIFER_COORDS = {
    ("DZ", "Continental Intercalaire (SASS)"): (30.2, 2.8),
    ("DZ", "Complexe Terminal (SASS)"): (33.4, 6.1),
    ("DZ", "Chelif alluvial aquifer"): (36.2, 1.3),
    ("TN", "Continental Intercalaire (SASS)"): (32.8, 9.2),
    ("TN", "Cap Bon aquifer"): (36.7, 10.7),
    ("TN", "Sahel aquifer"): (35.6, 10.5),
}
