from django import template

register = template.Library()


@register.filter
def abs_value(value):
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return 0


@register.filter
def signed_one(value):
    try:
        return f"{float(value):+.1f}"
    except (TypeError, ValueError):
        return "—"


@register.filter
def bar_width(value):
    try:
        return min(100.0, abs(float(value)) * 4.2)
    except (TypeError, ValueError):
        return 0


@register.filter
def volume_mm3(value):
    try:
        return f"{float(value) / 1_000_000:,.1f}"
    except (TypeError, ValueError):
        return "—"


@register.filter
def percent(value):
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "—"
