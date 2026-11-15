from __future__ import annotations

from django.conf import settings

from hydro.ai.contracts import BUILTIN_SLOTS
from hydro.models import AIAgentSlot


def ensure_slots() -> list[AIAgentSlot]:
    slots = []
    for row in BUILTIN_SLOTS:
        slot, _ = AIAgentSlot.objects.update_or_create(
            name=row["name"],
            defaults={
                "stage": row["stage"],
                "description": row["description"],
                "enabled": False,
                "max_delta": row["max_delta"],
                "weight": row["weight"],
                "contract_version": row["contract_version"],
                "metadata": row["metadata"],
            },
        )
        slots.append(slot)
    return slots


def slots_payload() -> list[dict]:
    if not AIAgentSlot.objects.exists():
        ensure_slots()
    return [
        {
            "id": slot.id,
            "name": slot.name,
            "stage": slot.stage,
            "description": slot.description,
            "enabled": slot.enabled,
            "max_delta": slot.max_delta,
            "weight": slot.weight,
            "contract_version": slot.contract_version,
            "endpoint": slot.endpoint,
            "metadata": slot.metadata,
        }
        for slot in AIAgentSlot.objects.all()
    ]


def enabled_slots() -> list[AIAgentSlot]:
    return list(AIAgentSlot.objects.filter(enabled=True))


def effective_policy() -> dict:
    return {
        "enabled": bool(settings.AI_AGENTS_ENABLED),
        "allow_subindex_adjustment": bool(settings.AI_ALLOW_SUBINDEX_ADJUSTMENT),
        "max_adjustment": settings.AI_MAX_ADJUSTMENT,
        "core_formula_mutable": False,
        "default_behavior": "advisory-only",
    }
