from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # Importing the registry registers every deterministic index provider.
        from core.services.indices import registry  # noqa: F401
