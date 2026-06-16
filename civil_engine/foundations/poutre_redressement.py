from __future__ import annotations

"""
Poutre de redressement (PR) — predimensionnement.

Une semelle excentree (de rive) porte un poteau dont la charge N est decalee
de l'excentricite e par rapport au centre de la semelle (semelle recalee vers
l'interieur de l'emprise). La poutre de redressement relie cette semelle a une
semelle interieure voisine et reprend le moment d'excentricite M = N * e,
empechant le basculement de la semelle de rive.

Hypotheses (preliminaire, a verifier par l'ingenieur) :
- PR consideree rigide, ne s'appuyant pas sur le sol (effort repris par flexion) ;
- moment de dimensionnement M_Ed ~ 1.35 * N_ELS * e (estimation ELU) ;
- bras de levier interne z ~ 0.9 d ;
- aciers principaux en fibre superieure (traction au droit de la semelle de rive).
"""

import math
from typing import Any


PI = math.pi


def _bar_area_cm2(diameter_mm: float, count: int) -> float:
    return round(count * PI * (diameter_mm / 10.0) ** 2 / 4.0, 3)


def _select_bars(as_required_cm2: float, candidates_mm=(12, 14, 16, 20, 25),
                 min_count: int = 2, max_count: int = 6) -> dict[str, Any]:
    """
    Choisit (nombre, diametre) en privilegiant le MOINS de barres possible
    (barres plus grosses) — realiste pour une poutre etroite (b ~ 0.30 m) ou
    l'on ne peut pas aligner beaucoup de barres en une nappe. A nombre egal,
    on prend le plus petit diametre suffisant.
    """
    for n in range(min_count, max_count + 1):
        for phi in candidates_mm:               # diametre croissant
            a = _bar_area_cm2(phi, n)
            if a >= as_required_cm2:
                return {"label": f"{n}HA{phi}", "count": n,
                        "diameter_mm": phi, "As_cm2": a}
    phi = candidates_mm[-1]
    return {"label": f"{max_count}HA{phi}", "count": max_count,
            "diameter_mm": phi, "As_cm2": _bar_area_cm2(phi, max_count)}


def round_up(value: float, step: float = 0.05) -> float:
    return round(math.ceil(value / step) * step, 3)


def _foundation_columns(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    for level in model.get("levels", []):
        if level.get("name") == "FONDATION":
            return {c["id"]: c for c in level.get("columns", [])}
    return {}


def design_strap_beams(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    fck_mpa: float = 25.0,
    fyk_mpa: float = 500.0,
    gamma_s: float = 1.15,
    cover_m: float = 0.05,
    default_width_m: float = 0.30,
    min_height_m: float = 0.40,
    gamma_g_estimate: float = 1.35,
    gamma_concrete_kN_m3: float = 25.0,
) -> dict[str, Any]:
    """
    Genere les poutres de redressement pour les semelles excentrees (type 'SE').

    Pour chaque semelle SE :
    - calcule l'excentricite e entre le poteau et le centre de la semelle ;
    - relie a la semelle non-excentree la plus proche (point d'ancrage) ;
    - dimensionne section (b x h) et aciers principaux pour M = gamma * N * e.
    """
    final_foundations = strategy_report.get("final_foundations", [])
    cols_geom = _foundation_columns(model)
    fyd = fyk_mpa / gamma_s  # MPa

    se_footings = [f for f in final_foundations if f.get("type") == "SE"]
    anchor_candidates = [f for f in final_foundations if f.get("type") != "SE"]
    # repli : si aucune semelle non-SE, on autorise n'importe quelle autre semelle
    if not anchor_candidates:
        anchor_candidates = list(final_foundations)

    beams: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    counter = 0

    for f in se_footings:
        col_id = (f.get("columns") or [None])[0]
        col = cols_geom.get(col_id, {})
        if not col:
            warnings.append({"code": "COLUMN_GEOM_MISSING",
                             "message": f"Geometrie du poteau {col_id} introuvable pour PR de {f.get('id')}."})
            continue

        col_x, col_y = float(col["cx"]), float(col["cy"])
        fc_x, fc_y = float(f["cx"]), float(f["cy"])

        # Excentricite = decalage poteau <-> centre semelle
        ex, ey = col_x - fc_x, col_y - fc_y
        e = math.hypot(ex, ey)
        if e < 1e-3:
            # SE sans excentricite mesurable : pas de PR utile
            continue

        # Direction "vers l'interieur" figee sur l'axe DOMINANT de l'excentricite,
        # pour obtenir une PR la plus perpendiculaire possible (alignee X ou Y)
        # plutot qu'une diagonale.
        if abs(ex) >= abs(ey):
            sdx, sdy = (-1.0 if ex > 0 else 1.0), 0.0   # horizontale
        else:
            sdx, sdy = 0.0, (-1.0 if ey > 0 else 1.0)   # verticale

        # Semelle d'ancrage : uniquement si une semelle interieure est atteignable
        # ORTHOGONALEMENT vers l'interieur (perp faible). On ne genere PAS de PR
        # diagonale : les semelles d'angle, sans ancrage orthogonal, sont
        # stabilisees par le L des longrines peripheriques.
        anchor = None
        best_score = None
        ortho_tol = 0.40  # tolerance perp/along (~22 deg) pour rester "perpendiculaire"
        for a in anchor_candidates:
            if a.get("id") == f.get("id"):
                continue
            dx, dy = float(a["cx"]) - fc_x, float(a["cy"]) - fc_y
            d = math.hypot(dx, dy)
            if d < 1e-6:
                continue
            along = dx * sdx + dy * sdy          # avancee le long de l'axe interieur
            perp = abs(dx * (-sdy) + dy * sdx)   # decalage perpendiculaire (diagonalite)
            if along <= 0:                       # doit aller vers l'interieur
                continue
            if perp > ortho_tol * along:         # trop diagonal -> rejete
                continue
            score = along + 3.0 * perp
            if best_score is None or score < best_score:
                best_score, anchor = score, a
        if anchor is None:
            # Pas d'ancrage orthogonal (cas des coins) : liaison assuree par
            # l'anneau de longrines peripheriques, pas de PR diagonale.
            warnings.append({"code": "NO_ORTHO_ANCHOR_TIE_BY_LONGRINE",
                             "message": f"{f.get('id')} : pas de semelle interieure orthogonale ; "
                                        f"liaison assuree par les longrines peripheriques (pas de PR diagonale)."})
            continue

        # Geometrie PR : du poteau de rive vers le centre de la semelle d'ancrage
        start = (round(col_x, 4), round(col_y, 4))
        end = (round(float(anchor["cx"]), 4), round(float(anchor["cy"]), 4))
        L = round(math.hypot(end[0] - start[0], end[1] - start[1]), 3)

        N_els = float(f.get("N_ELS_kN") or 0.0)
        M_ed = gamma_g_estimate * N_els * e  # kN.m (estimation ELU)

        # Section : largeur = max(largeur poteau perpendiculaire, defaut)
        b = max(float(col.get("bx", default_width_m) or default_width_m), default_width_m)
        b = round(round_up(b, 0.05), 3)

        # Hauteur : poutre rigide ~ L/10, puis on l'augmente tant que le taux
        # d'acier reste excessif (cible rho <= 1.5 %), plafond a 1.00 m.
        h = max(min_height_m, round_up(L / 10.0, 0.05))
        h_cap = 1.00
        as_req_cm2 = 0.0
        d_eff = h - cover_m - 0.012
        while True:
            d_eff = h - cover_m - 0.012
            z = 0.9 * d_eff
            as_req_cm2 = (M_ed * 1e3) / (z * fyd * 1e2) if z > 0 else 0.0
            rho = as_req_cm2 / (b * d_eff * 1e4) if d_eff > 0 else 1.0
            if rho <= 0.015 or h >= h_cap:
                break
            h = round(h + 0.05, 3)
        h = round(min(h, h_cap), 3)

        # Acier minimal de poutre (~0.13% b d, simplifie)
        as_min_cm2 = round(0.0013 * b * d_eff * 1e4, 2)
        as_design = max(as_req_cm2, as_min_cm2)

        top = _select_bars(as_design)
        bottom = _select_bars(as_min_cm2)  # nappe inferieure = mini constructif

        # Metre
        concrete_m3 = round(b * h * L, 3)
        steel_kg = round(
            (top["count"] * (top["diameter_mm"] / 1000.0) ** 2 * PI / 4.0
             + bottom["count"] * (bottom["diameter_mm"] / 1000.0) ** 2 * PI / 4.0)
            * L * 7850.0, 2)

        counter += 1
        beams.append({
            "id": f"PR{counter:02d}",
            "eccentric_footing_id": f.get("id"),
            "eccentric_column_id": col_id,
            "anchor_footing_id": anchor.get("id"),
            "start": list(start),
            "end": list(end),
            "length_m": L,
            "eccentricity_m": round(e, 4),
            "N_ELS_kN": round(N_els, 2),
            "M_Ed_kNm": round(M_ed, 2),
            "b_m": b,
            "h_m": h,
            "d_eff_m": round(d_eff, 3),
            "As_required_cm2": round(as_design, 2),
            "As_min_cm2": as_min_cm2,
            "bars_top": top["label"],
            "As_top_cm2": top["As_cm2"],
            "bars_bottom": bottom["label"],
            "As_bottom_cm2": bottom["As_cm2"],
            "stirrups": "HA8 e=15 cm",
            "concrete_m3": concrete_m3,
            "steel_kg": steel_kg,
            "status": "PRELIMINARY",
            "note": "PR preliminaire : reprend M = gamma*N*e. A verifier (rigidite, fleche, ancrages).",
        })

    totals = {
        "count": len(beams),
        "concrete_m3": round(sum(b["concrete_m3"] for b in beams), 3),
        "steel_kg": round(sum(b["steel_kg"] for b in beams), 2),
        "total_length_m": round(sum(b["length_m"] for b in beams), 2),
    }

    return {
        "status": "OK" if beams else ("WARNING" if warnings else "OK"),
        "method": "poutre_redressement_preliminaire_v1",
        "hypotheses": {
            "fck_mpa": fck_mpa, "fyk_mpa": fyk_mpa, "gamma_s": gamma_s,
            "cover_m": cover_m, "default_width_m": default_width_m,
            "min_height_m": min_height_m,
            "M_Ed": "1.35 * N_ELS * e (estimation ELU)",
            "lever_arm": "z = 0.9 d",
            "note": "Predimensionnement. La PR doit etre verifiee (rigidite relative semelle/PR, fleche, ancrage des aciers superieurs, effort tranchant).",
        },
        "strap_beams": beams,
        "warnings": warnings,
        "totals": totals,
    }
