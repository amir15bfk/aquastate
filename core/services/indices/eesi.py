"""EESI — Evaporative & Ecological Stress Index."""
from __future__ import annotations

from core.services.contracts import IndexContext, IndexEvaluationResult, clamp
from core.services.indices.base import BaseIndexProvider
from core.services.stats import percentile_score
from core.services.units import surface_area_at_volume_m2


class EESIProvider(BaseIndexProvider):
    index_id = "EESI"
    version = "1.0"

    def _compute(self, ctx: IndexContext) -> IndexEvaluationResult:
        latest = ctx.current_climate()
        components = {"week": ctx.week}
        if latest is None or latest.pet_mm is None or latest.et_mm is None:
            return IndexEvaluationResult(
                index_id=self.index_id,
                score=0.0,
                status="NO_DATA",
                available=False,
                data_status="NO_DATA",
                confidence=0.0,
                components=components,
                explanation="Current ET/PET is missing; EESI is unavailable.",
                proof_steps=["ET or PET missing → NO_DATA"],
            )
        pet_mm_day = float(latest.pet_mm)
        if pet_mm_day <= 0:
            return IndexEvaluationResult(
                index_id=self.index_id,
                score=0.0,
                status="NO_DATA",
                available=False,
                data_status="INVALID",
                confidence=0.0,
                components={**components, "pet_mm_day": pet_mm_day},
                explanation="PET must be positive.",
                proof_steps=["PET <= 0 → INVALID"],
            )
        et_mm_day = float(latest.et_mm)
        esi = et_mm_day / pet_mm_day
        esi_scored = clamp(esi, 0.0, 1.0)

        volume = float(ctx.dam.current_volume_m3 or 0.0)
        area_m2 = surface_area_at_volume_m2(volume, ctx.dam.bathymetry)
        e_loss = area_m2 * pet_mm_day * 1e-3 * 1.0
        usable_volume = max(0.0, volume - ctx.dam.dead_storage_m3)
        v_floor = max(1.0, ctx.dam.usable_capacity_m3 * 1e-6)
        evap_ratio = e_loss / max(usable_volume, v_floor)

        esi_base = ctx.climatology_values("eesi_esi")
        evap_base = ctx.climatology_values("eesi_evap_ratio")
        lst_base = ctx.climatology_values("eesi_lst_anom")

        p_esi = percentile_score(esi_base, esi_scored)
        p_evap_directional = percentile_score(
            evap_base, evap_ratio, higher_is_better=False
        )
        components.update(
            {
                "pet_mm_day": pet_mm_day,
                "a_surface_m2": area_m2,
                "e_loss_m3_day": e_loss,
                "usable_volume_m3": usable_volume,
                "v_floor_m3": v_floor,
                "evap_ratio": evap_ratio,
                "esi": esi,
                "esi_scored": esi_scored,
                "esi_flagged": esi > 1.0,
                "p_esi": round(p_esi.score, 6),
                "p_evap": round(p_evap_directional.score, 6),
                "raw_p_evap": round(100.0 - p_evap_directional.score, 6),
                "p_evap_n": p_evap_directional.n,
                "p_esi_n": p_esi.n,
            }
        )

        lst_mean = ctx.dam.metadata.get("lst_mean_k")
        if latest.lst_k is not None and lst_mean is not None:
            anomaly = float(latest.lst_k) - float(lst_mean)
        else:
            anomaly = None
        components["lst_anomaly"] = anomaly

        if anomaly is not None and lst_base:
            p_lst_directional = percentile_score(
                lst_base, anomaly, higher_is_better=False
            )
            weights = [0.55, 0.30, 0.15]
            terms = [p_esi.score, p_evap_directional.score, p_lst_directional.score]
            components.update(
                {
                    "p_lst": round(p_lst_directional.score, 6),
                    "raw_p_lst": round(100.0 - p_lst_directional.score, 6),
                    "p_lst_n": p_lst_directional.n,
                }
            )
            lst_confidence = p_lst_directional.confidence
        else:
            weights = [0.65, 0.35]
            terms = [p_esi.score, p_evap_directional.score]
            components["p_lst"] = None
            components["lst_missing"] = True
            lst_confidence = 1.0

        available = p_esi.n > 0 and p_evap_directional.n > 0
        if not available:
            return IndexEvaluationResult(
                index_id=self.index_id,
                score=0.0,
                status="NO_DATA",
                available=False,
                data_status="NO_DATA",
                confidence=0.0,
                components={**components, "weights": weights},
                explanation="An EESI baseline is empty; EESI is unavailable.",
                proof_steps=["N=0 in an EESI baseline → NO_DATA"],
            )

        score = clamp(sum(weight * term for weight, term in zip(weights, terms)))
        confidence = min(p_esi.confidence, p_evap_directional.confidence, lst_confidence)
        if esi > 1.0:
            confidence *= 0.8
        if anomaly is None or not lst_base:
            confidence *= 0.8
        components.update(
            {
                "weights": weights,
                "terms": [round(term, 6) for term in terms],
                "lst_confidence": lst_confidence,
            }
        )
        return IndexEvaluationResult(
            index_id=self.index_id,
            score=round(score, 6),
            status="OK",
            available=True,
            data_status="OK",
            confidence=round(confidence, 6),
            components=components,
            explanation=(
                f"E_loss={e_loss:,.0f} m³/day over {area_m2:,.0f} m²; "
                f"EESI = {' + '.join(f'{w:.2f}·{t:.1f}' for w, t in zip(weights, terms))}"
                f" = {score:.2f}."
            ),
            proof_steps=[
                f"E_loss = A_surface·PET·10⁻³·K_ow = {area_m2:,.0f}·"
                f"{pet_mm_day:.2f}·10⁻³ = {e_loss:,.1f} m³/day",
                f"ESI = ET/PET = {et_mm_day:.3f}/{pet_mm_day:.3f} = {esi:.3f}"
                + (" (clamped to 1.0)" if esi > 1.0 else ""),
                f"Evap ratio = E_loss/max(V_u, V_floor) = {evap_ratio:.8f}",
                f"EESI = {score:.3f} with weights {weights}",
            ],
        )
