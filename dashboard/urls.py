from django.urls import path

from dashboard import views

app_name = "dashboard"

urlpatterns = [
    path("", views.dashboard, name="index"),
    path(
        "dashboard/partials/panel/<slug:dam_slug>/",
        views.panel_partial,
        name="panel_partial",
    ),
    path(
        "dashboard/partials/scenario/<slug:dam_slug>/",
        views.scenario_partial,
        name="scenario_partial",
    ),
    path(
        "dashboard/partials/country/<str:iso3>/",
        views.country_partial,
        name="country_partial",
    ),
]
