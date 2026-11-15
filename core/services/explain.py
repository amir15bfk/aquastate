"""Human-readable and machine-checkable explanations for HRI results."""
from __future__ import annotations

from core.services.buffer import BufferResult


def build_proof_steps(
    buffer: BufferResult,
    weights: dict[str, float],
    scores_now: dict[str, float],
    scores_proj: dict[str, float],
    hri_now: float,
    hri_proj: float,
    hri: float,
) -> list[str]:
    steps = [
        f"ε = max(1, V_uc/3650) = {buffer.epsilon_m3_day:,.1f} m³/day",
        f"Q_out = {buffer.q_out_m3_day:,.1f} m³/day ({buffer.demand_source})",
        f"D_autonomy = {'0' if buffer.v_u_m3 <= 0 else f'min(3650, V_u/Q_out) = {buffer.d_autonomy_days:.2f} d'}",
        f"D_until_rain = {buffer.d_until_rain_days if buffer.d_until_rain_days is not None else 'none'}",
        f"V_in14 = {buffer.v_in14_m3:,.0f} m³ over {buffer.event_count} storm event(s)",
        f"V_proj14 = clamp(V_u - 14·Q_out + V_in, 0, V_uc) = "
        f"{buffer.v_proj14_m3:,.0f} m³",
        f"Φ = {buffer.phi:.5f}",
        f"HRI_now = Σw·s_now = {hri_now:.3f}",
        f"HRI_proj = Σw·s_proj = {hri_proj:.3f}",
        "HRI = (1-Φ)·HRI_now + Φ·HRI_proj = "
        f"{(1 - buffer.phi) * hri_now + buffer.phi * hri_proj:.3f}",
    ]
    for index, weight in weights.items():
        steps.append(
            f"δ_{index} = {weight:.5f}·((1-Φ)·{scores_now.get(index, 0):.3f} "
            f"+ Φ·{scores_proj.get(index, 0):.3f} - 50)"
        )
    return steps


def build_explanation(
    status: str,
    hri: float,
    phi: float,
    hri_now: float,
    hri_proj: float,
    buffer: BufferResult,
    cap_reason: str | None,
) -> str:
    if cap_reason == "invalid_storage":
        return "Usable storage is invalid; the HRI cannot be computed."
    if cap_reason == "no_data":
        return "No participating sub-index has data; the HRI is not a real score."
    trend = "improving toward recharge" if hri_proj > hri_now else "not projected to improve"
    text = (
        f"The reservoir scores {hri:.1f} ({status}). Current stress is "
        f"{hri_now:.1f}; the 14-day projection is {hri_proj:.1f}, and the "
        f"buffer-bridge factor Φ is {phi:.3f}. Storage is {trend}. "
    )
    if cap_reason == "autonomy_cap":
        text += (
            f"Autonomy is only {buffer.d_autonomy_days:.2f} days, so the score is "
            "capped at 19.9 until the immediate supply constraint eases. "
        )
    elif cap_reason == "dry_low_storage_cap":
        text += (
            "Low storage, weak forecast recharge, and limited autonomy cap the "
            "score at 24.9. "
        )
    elif cap_reason == "soft_override":
        text += "A continuous low-storage override reduced the blended score. "
    return text
