from django.urls import path

from hydro import views

urlpatterns = [
    path("", views.index, name="index"),
    path("switch/", views.switch_country, name="switch_country"),
    path("water/<str:iso2>/", views.dashboard, name="dashboard"),
    path("api/country/<str:iso2>/", views.api_country, name="api_country"),
    path("api/country/<str:iso2>/audit/", views.api_audit, name="api_audit"),
    path("api/country/<str:iso2>/refresh/", views.refresh_country, name="api_refresh"),
    path("api/country/<str:iso2>/import-osm/", views.import_osm, name="api_import_osm"),
    path("api/countries/", views.api_countries, name="api_countries"),
    path("api/ai/slots/", views.api_ai_slots, name="api_ai_slots"),
    path("methodology/", views.methodology, name="methodology"),
    path("sources/", views.sources_page, name="sources"),
    path("health/", views.health, name="health"),
]
