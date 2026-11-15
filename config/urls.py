from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    # Browsers ask for /favicon.ico even when the page links an SVG icon.
    path("favicon.ico", RedirectView.as_view(url=settings.STATIC_URL + "ds/favicon.svg", permanent=True)),
    path("admin/", admin.site.urls),
    path("", include("world.urls")),
    path("", include("hydro.urls")),
    path("api/pilot/", include("core.urls")),
    path("pilot/", include("dashboard.urls")),
]
