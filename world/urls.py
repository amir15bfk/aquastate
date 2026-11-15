from django.urls import path

from world import views

app_name = "world"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("country/<str:iso2>/", views.country, name="country"),
    path("dams/", views.dams, name="dams"),
    path("dam/<str:slug>/", views.dam, name="dam"),
    path("hazards/", views.hazards, name="hazards"),
    path("methodology/", views.methodology, name="methodology"),
    path("sources/", views.sources_page, name="sources"),
    path("api/world/", views.api_world, name="api_world"),
    path("api/world/meta/", views.api_meta, name="api_meta"),
    path("api/world/refresh/", views.api_refresh, name="api_refresh"),
    path("api/world/country/<str:iso2>/", views.api_country, name="api_country"),
    path("api/dams/", views.api_dams, name="api_dams"),
    path("api/events/", views.api_events, name="api_events"),
]
