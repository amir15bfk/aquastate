"""Django settings for AquaState — the merged water & climate observatory."""
from pathlib import Path
import mimetypes
import os

# Windows' registry often has no type for .mjs, so the dev static server sent the MapLibre
# module worker as text/plain and browsers refused to start it (the /pilot/ map stayed blank).
mimetypes.add_type("text/javascript", ".mjs", True)

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.environ.get(
    "SECRET_KEY", "django-insecure-aquastate-world-change-me-in-production"
)
DEBUG = env_bool("DEBUG", True)
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "hydro",
    "core",
    "dashboard",
    "world",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Outside CommonMiddleware so APPEND_SLASH redirects still happen first.
    "world.middleware.FriendlyNotFoundMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.template.context_processors.csrf",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "world.context.site_nav",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": 20},
    }
}

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "hydro" / "static",
    BASE_DIR / "static",
]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# AquaState data & index settings
# ---------------------------------------------------------------------------
DATA_DIR = BASE_DIR / "hydro" / "data"
COUNTRIES_FILE = DATA_DIR / "countries.json"
WORLD_DATA_DIR = BASE_DIR / "world" / "data"
WORLD_GEOJSON = BASE_DIR / "static" / "data" / "countries-world.geojson"
WORLD_SEED_FILE = WORLD_DATA_DIR / "world_seed.json"

AI_AGENTS_ENABLED = False
AI_ALLOW_SUBINDEX_ADJUSTMENT = False
AI_MAX_ADJUSTMENT = 5.0

# All sources are keyless.
LIVE_DATA_ENABLED = env_bool("LIVE_DATA_ENABLED", True)
DATA_CACHE_HOURS = 12
OPEN_METEO_TIMEOUT = 20
NASA_POWER_TIMEOUT = 60
WORLD_BANK_TIMEOUT = 60
OVERPASS_TIMEOUT = 20

# WRI-2.0 (country water state) — documented in docs/INDEX_MATH.md.
INDEX_VERSION = "WRI-2.0"
INDEX_WEIGHTS = {
    "buffer": 0.34,
    "soil": 0.18,
    "groundwater": 0.14,
    "forecast": 0.14,
    "trend": 0.20,
}
HORIZON_EMERGENCY_RATIO = 0.03
HORIZON_PER_RESERVOIR_MIN_RATIO = 0.01
DEFAULT_HORIZON_DAYS = 14

# WCRI-2.0 (world country index).
WCRI_VERSION = "WCRI-2.0"
WCRI_WEIGHTS = {
    "water": 0.22,
    "drought": 0.20,
    "groundwater": 0.14,
    "flood": 0.14,
    "fire": 0.14,
    "desertification": 0.16,
}
WCRI_REFRESH_MINUTES = int(os.environ.get("WCRI_REFRESH_MINUTES", "30"))
WCRI_FORECAST_TTL_MINUTES = int(os.environ.get("WCRI_FORECAST_TTL_MINUTES", "30"))
WCRI_FLOOD_TTL_MINUTES = int(os.environ.get("WCRI_FLOOD_TTL_MINUTES", "60"))
WCRI_CLIMATE_TTL_HOURS = int(os.environ.get("WCRI_CLIMATE_TTL_HOURS", "24"))
WCRI_BANK_TTL_HOURS = int(os.environ.get("WCRI_BANK_TTL_HOURS", "168"))

# Space app pilot configuration.
HYDRO_DATA_PROVIDER = os.environ.get("HYDRO_DATA_PROVIDER", "seeded")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "hydro": {"handlers": ["console"], "level": "INFO"},
        "world": {"handlers": ["console"], "level": "INFO"},
        "core": {"handlers": ["console"], "level": "INFO"},
    },
}
