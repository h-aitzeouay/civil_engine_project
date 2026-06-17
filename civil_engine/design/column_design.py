from __future__ import annotations

"""
Dimensionnement des poteaux (predimensionnement).

Methode BAEL simplifiee (compression centree avec flambement) pour le ferraillage
longitudinal, completee par les dispositions parasismiques RPS 2000 (ed. 2011) :
- pourcentage d'acier minimal/maximal,
- cadres : zone critique L.C = max(He/6, plus grande dimension, 45 cm),
- espacements crit/courant.

Charge axiale N_ELU issue de la descente de charges (cumul de tous les niveaux).
Increment 1 : dimensionnement au pied (section et charge a la base).
"""

import math
from typing import Any

PI = math.pi


def _bar_area_cm2(diameter_mm: float, count: int) -> float:
    return round(count * PI * (diameter_mm / 10.0) ** 2 / 4.0, 3)


def _select_long_bars(as_req_cm2: float, candidates_mm=(12, 14, 16, 20, 25),
                      min_count: int = 4, max_count: int = 12) -> dict[str, Any]:
    """Choisit (nombre pair >=4, diametre) couvrant As, en limitant le nombre."""
    best = None
    for n in range(min_count, max_count + 1, 2):  # nombre pair (symetrie)
        for phi in candidates_mm:
            a = _bar_area_cm2(phi, n)
            if a >= as_req_cm2:
                if best is None:
                    best = {"count": n, "diameter_mm": phi, "As_cm2": a}
                break
        if best is not None:
            break
    if best is None:
        best = {"count": max_count, "diameter_mm": candidates_mm[-1],
                "As_cm2": _bar_area_cm2(candidates_mm[-1], max_count)}
    return {"label": f"{best['count']}HA{best['diameter_mm']}", **best}


def _alpha_buckling(lam: float) -> float:
    """Coefficient de flambement BAEL alpha(lambda)."""
    if lam <= 50.0:
        return 0.85 / (1.0 + 0.2 * (lam / 35.0) ** 2)
    return 0.60 * (50.0 / lam) ** 2


def design_columns(
    model: dict[str, Any],
    fck_mpa: float = 25.0,
    fyk_mpa: float = 500.0,
    gamma_s: float = 1.15,
    gamma_c: float = 1.50,
    storey_height_m: float = 3.00,
    buckling_coeff: float = 0.70,
    g_floor_kN_m2: float = 5.00,
    q_floor_kN_m2: float = 1.50,
    g_terrace_kN_m2: float = 6.00,
    q_terrace_kN_m2: float = 1.00,
    rho_min: float = 0.008,
    rho_max: float = 0.04,
    phi_stirrup_mm: float = 8.0,
) -> dict[str, Any]:
    from civil_engine.engine.load_takedown import compute_load_takedown
    from civil_engine.foundations.column_effective import get_effective_column_boxes

    lt = compute_load_takedown(
        model=model, g_floor_kN_m2=g_floor_kN_m2, q_floor_kN_m2=q_floor_kN_m2,
        g_terrace_kN_m2=g_terrace_kN_m2, q_terrace_kN_m2=q_terrace_kN_m2)
    loads = {c["column_id"]: c for c in lt.get("foundation_columns", [])}
    boxes = get_effective_column_boxes(model)

    fc28, fe = fck_mpa, fyk_mpa
    columns: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []

    for cid, box in sorted(boxes.items()):
        a = round(max(float(box.get("c1_m", 0.25)), 0.20), 3)   # plus petit cote >= 20cm
        b = round(max(float(box.get("c2_m", 0.25)), 0.20), 3)
        amin = min(a, b)
        Nu = float(loads.get(cid, {}).get("sum_N_ELU_kN", 0.0))  # kN
        Nu_MN = Nu / 1000.0

        # Flambement
        lf = buckling_coeff * storey_height_m
        i = amin / math.sqrt(12.0)
        lam = lf / i if i > 0 else 0.0
        alpha = _alpha_buckling(lam)

        # BAEL : As >= gamma_s/fe * (Nu/alpha - Br*fc28/(0.9*gamma_c))
        Br = (a - 0.02) * (b - 0.02)            # section reduite (m2)
        B = a * b                                # section brute (m2)
        as_bael_m2 = (Nu_MN / alpha - Br * fc28 / (0.9 * gamma_c)) / (fe / gamma_s)
        as_bael_cm2 = max(0.0, as_bael_m2 * 1e4)

        as_min_cm2 = round(rho_min * B * 1e4, 2)
        as_max_cm2 = round(rho_max * B * 1e4, 2)
        as_design = max(as_bael_cm2, as_min_cm2)

        status = "OK"
        if as_design > as_max_cm2:
            status = "SECTION_INSUFFISANTE"
            warnings.append({"code": "RHO_MAX_DEPASSE",
                             "message": f"{cid} : acier requis {as_design:.1f} cm2 > rho_max ({as_max_cm2} cm2). Augmenter la section."})

        bars = _select_long_bars(as_design)

        # Cadres RPS 2000
        phi_l = bars["diameter_mm"]
        lc = round(max(storey_height_m / 6.0, max(a, b), 0.45), 2)   # L.C poteau
        s_crit = round(max(0.07, math.floor(min(8 * phi_l / 1000.0, 0.25 * amin, 0.15) / 0.05) * 0.05), 2)
        s_cour = round(max(0.10, math.floor(min(12 * phi_l / 1000.0, 0.5 * amin, 0.30) / 0.05) * 0.05), 2)

        rho = round(bars["As_cm2"] / (B * 1e4) * 100, 2)

        columns.append({
            "id": cid,
            "a_m": a, "b_m": b,
            "N_ELU_kN": round(Nu, 2),
            "levels_supported": loads.get(cid, {}).get("levels_supported", []),
            "slenderness_lambda": round(lam, 1),
            "alpha": round(alpha, 3),
            "As_required_cm2": round(as_design, 2),
            "As_min_cm2": as_min_cm2,
            "As_max_cm2": as_max_cm2,
            "bars_long": bars["label"],
            "As_provided_cm2": bars["As_cm2"],
            "rho_percent": rho,
            "stirrup_diameter_mm": phi_stirrup_mm,
            "zone_critique_lc_m": lc,
            "stirrup_spacing_crit_m": s_crit,
            "stirrup_spacing_cour_m": s_cour,
            "stirrups": f"HA{int(phi_stirrup_mm)} e={int(s_crit*100)} (zone critique L.C) / e={int(s_cour*100)} (courant)",
            "status": status,
            "note": "Predimensionnement BAEL (compression + flambement) + detailing RPS 2000. A verifier (moments, sisme).",
        })

    by_status: dict[str, int] = {}
    for c in columns:
        by_status[c["status"]] = by_status.get(c["status"], 0) + 1

    return {
        "status": "OK" if all(c["status"] == "OK" for c in columns) else "WARNING",
        "method": "column_design_bael_rps2000_v1",
        "hypotheses": {
            "fck_mpa": fck_mpa, "fyk_mpa": fyk_mpa, "gamma_s": gamma_s, "gamma_c": gamma_c,
            "storey_height_m": storey_height_m, "buckling_coeff": buckling_coeff,
            "rho_min": rho_min, "rho_max": rho_max,
            "method_note": "BAEL compression centree avec flambement ; L.C=max(He/6,dim,45cm) (RPS 2000).",
        },
        "columns": columns,
        "summary": {"count": len(columns), "by_status": by_status},
        "warnings": warnings,
    }
