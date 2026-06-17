from __future__ import annotations

"""
Dimensionnement des poteaux (predimensionnement).

Ferraillage longitudinal calcule par le module poteaux_ba (analyse de section
EC2 par fibres, interaction N-M biaxiale, excentricite minimale, elancement),
complete par les dispositions parasismiques RPS 2000 (ed. 2011) pour les cadres :
- zone critique L.C = max(He/6, plus grande dimension, 45 cm) ;
- espacements crit/courant.

Charge axiale N_ELU issue de la descente de charges (cumul de tous les niveaux).
"""

import math
from typing import Any

from civil_engine.design.poteaux_ba import (
    Concrete, Steel, ColumnForces, suggest_reinforcement,
)

PI = math.pi


def design_columns(
    model: dict[str, Any],
    fck_mpa: float = 25.0,
    fyk_mpa: float = 500.0,
    gamma_s: float = 1.15,
    gamma_c: float = 1.50,
    storey_height_m: float = 3.00,
    buckling_coeff: float = 0.70,
    cover_m: float = 0.025,
    g_floor_kN_m2: float = 5.00,
    q_floor_kN_m2: float = 1.50,
    g_terrace_kN_m2: float = 6.00,
    q_terrace_kN_m2: float = 1.00,
    rho_min: float = 0.008,
    rho_max: float = 0.04,
    phi_stirrup_mm: float = 8.0,
    mesh: int = 20,
) -> dict[str, Any]:
    from civil_engine.engine.load_takedown import compute_load_takedown
    from civil_engine.foundations.column_effective import get_effective_column_boxes

    lt = compute_load_takedown(
        model=model, g_floor_kN_m2=g_floor_kN_m2, q_floor_kN_m2=q_floor_kN_m2,
        g_terrace_kN_m2=g_terrace_kN_m2, q_terrace_kN_m2=q_terrace_kN_m2)
    loads = {c["column_id"]: c for c in lt.get("foundation_columns", [])}
    boxes = get_effective_column_boxes(model)

    concrete = Concrete(fck_mpa=fck_mpa, gamma_c=gamma_c)
    steel = Steel(fyk_mpa=fyk_mpa, gamma_s=gamma_s)
    lf = buckling_coeff * storey_height_m

    columns: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    cache: dict[tuple, Any] = {}

    for cid, box in sorted(boxes.items()):
        a = round(max(float(box.get("c1_m", 0.25)), 0.20), 3)
        b = round(max(float(box.get("c2_m", 0.25)), 0.20), 3)
        amin = min(a, b)
        Nu = float(loads.get(cid, {}).get("sum_N_ELU_kN", 0.0))

        # Cache : poteaux de meme section et meme charge -> meme dimensionnement.
        key = (a, b, round(Nu, 0))
        if key in cache:
            proposal = cache[key]
        else:
            forces = ColumnForces.from_kN_kNm(NEd_kN=Nu, MEd_y_kNm=0.0, MEd_z_kNm=0.0)
            proposal = suggest_reinforcement(
                b=a, h=b, forces=forces, concrete=concrete, steel=steel,
                cover=cover_m, link_phi_mm=phi_stirrup_mm, l0_y=lf, l0_z=lf, mesh=mesh)
            cache[key] = proposal

        if proposal is None:
            warnings.append({"code": "NO_SOLUTION",
                             "message": f"{cid} : aucune section/ferraillage verifie (augmenter la section)."})
            columns.append({
                "id": cid, "a_m": a, "b_m": b, "N_ELU_kN": round(Nu, 2),
                "levels_supported": loads.get(cid, {}).get("levels_supported", []),
                "slenderness_lambda": round(lf / (amin / math.sqrt(12.0)), 1),
                "bars_long": "-", "As_provided_cm2": 0.0, "rho_percent": 0.0,
                "utilization": None,
                "zone_critique_lc_m": round(max(storey_height_m / 6.0, max(a, b), 0.45), 2),
                "stirrup_spacing_crit_m": 0.10, "stirrup_spacing_cour_m": 0.15,
                "stirrups": "HA8 e=10 / e=15", "status": "SECTION_INSUFFISANTE",
                "note": "Aucune solution dans les candidats. Augmenter la section du poteau.",
            })
            continue

        r = proposal.result
        n, phi = proposal.n_bars, proposal.phi_mm
        lam = lf / (amin / math.sqrt(12.0))

        # Cadres RPS 2000
        lc = round(max(storey_height_m / 6.0, max(a, b), 0.45), 2)
        s_crit = round(max(0.07, math.floor(min(8 * phi / 1000.0, 0.25 * amin, 0.15) / 0.05) * 0.05), 2)
        s_cour = round(max(0.10, math.floor(min(12 * phi / 1000.0, 0.5 * amin, 0.30) / 0.05) * 0.05), 2)

        status = "OK"
        if r.rho_percent / 100.0 > rho_max:
            status = "SECTION_INSUFFISANTE"
            warnings.append({"code": "RHO_MAX", "message": f"{cid} : rho {r.rho_percent:.1f}% > rho_max."})

        columns.append({
            "id": cid, "a_m": a, "b_m": b,
            "N_ELU_kN": round(Nu, 2),
            "levels_supported": loads.get(cid, {}).get("levels_supported", []),
            "slenderness_lambda": round(lam, 1),
            "bars_long": f"{n}HA{int(phi)}",
            "As_provided_cm2": round(r.As_cm2, 2),
            "rho_percent": round(r.rho_percent, 2),
            "utilization": round(r.utilization, 3),
            "MRd_y_kNm": round(r.MRd_y_kNm, 1),
            "MRd_z_kNm": round(r.MRd_z_kNm, 1),
            "stirrup_diameter_mm": phi_stirrup_mm,
            "zone_critique_lc_m": lc,
            "stirrup_spacing_crit_m": s_crit,
            "stirrup_spacing_cour_m": s_cour,
            "stirrups": f"HA{int(phi_stirrup_mm)} e={int(s_crit*100)} (zone critique L.C) / e={int(s_cour*100)} (courant)",
            "status": status,
            "note": "Predimensionnement EC2 (interaction N-M biaxiale + exc. mini + flambement) + cadres RPS 2000. A verifier (sisme, 2e ordre).",
        })

    by_status: dict[str, int] = {}
    for c in columns:
        by_status[c["status"]] = by_status.get(c["status"], 0) + 1

    return {
        "status": "OK" if all(c["status"] == "OK" for c in columns) else "WARNING",
        "method": "column_design_poteaux_ba_ec2_rps2000_v2",
        "hypotheses": {
            "fck_mpa": fck_mpa, "fyk_mpa": fyk_mpa, "gamma_s": gamma_s, "gamma_c": gamma_c,
            "storey_height_m": storey_height_m, "buckling_coeff": buckling_coeff,
            "cover_m": cover_m, "rho_min": rho_min, "rho_max": rho_max,
            "method_note": "Section EC2 (poteaux_ba) + excentricite minimale + flambement ; cadres RPS 2000.",
        },
        "columns": columns,
        "summary": {"count": len(columns), "by_status": by_status},
        "warnings": warnings,
    }
