from django import template

register = template.Library()


@register.filter
def volume_mm3(value):
    try:
        return f"{float(value) / 1_000_000:,.1f} Mm³"
    except (TypeError, ValueError):
        return "—"


@register.filter
def installed_mw(value):
    try:
        return f"{float(value):,.0f} MW"
    except (TypeError, ValueError):
        return "—"


@register.filter
def height_m(value):
    try:
        return f"{float(value):,.0f} m"
    except (TypeError, ValueError):
        return "—"


@register.filter
def absolute(value):
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return 0


@register.filter
def bar_pct(value, scale=3.0):
    try:
        return min(100.0, max(0.0, abs(float(value)) * float(scale)))
    except (TypeError, ValueError):
        return 0
