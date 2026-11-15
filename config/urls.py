from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("world.urls")),
    path("", include("hydro.urls")),
    path("api/pilot/", include("core.urls")),
    path("pilot/", include("dashboard.urls")),
]
