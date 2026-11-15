from django.urls import path

from core import api

app_name = "core_api"

urlpatterns = [
    path("health/", api.health, name="health"),
    path("countries/", api.countries, name="countries"),
    path("countries/<str:iso3>/dams/", api.country_dams, name="country_dams"),
    path("dams/<slug:dam_slug>/", api.dam_detail, name="dam_detail"),
    path("dams/<slug:dam_slug>/scenario/", api.dam_scenario, name="dam_scenario"),
    path("dams/<slug:dam_slug>/timeseries/", api.dam_timeseries, name="dam_timeseries"),
    path("dams/<slug:dam_slug>/map/", api.dam_map, name="dam_map"),
]
