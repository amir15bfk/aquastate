import importlib

import pytest
from django.core.management import call_command


def test_settings_module_loads():
    settings = importlib.import_module("config.settings")
    assert settings.BASE_DIR.exists()
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"
    assert "core" in settings.INSTALLED_APPS
    assert "dashboard" in settings.INSTALLED_APPS


@pytest.mark.django_db
def test_system_check_passes():
    call_command("check")
