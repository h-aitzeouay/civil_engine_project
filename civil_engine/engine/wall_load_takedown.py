"""
Descente de charges lineaire des voiles (semelles filantes).

Methode (validee) :
- Le voile est defini par un axe (x1,y1)->(x2,y2) + epaisseur saisie.
- Bande tributaire de largeur fixe de chaque cote de l'axe.
- Largeur de chaque demi-bande = demi-portee du plancher adjacent,
  c'est-a-dire la demi-distance jusqu'au prochain appui parallele
  (poteau ou voile) de ce cote, bornee par l'emprise.
- Charge lineaire q_lin (kN/ml) = largeur_bande_totale * charge_surfacique
  des niveaux portes, cumulee sur tous les niveaux.
"""
from __future__ import annotations

from typing import Any

from civil_engine.engine.load_takedown import (
    level_sort_key,
    is_top_structural_level,
)


def _wall_orientation(x1: float, y1: float, x2: float, y2: float) -> str:
    """Retourne 'H' (horizontal) ou 'V' (vertical) selon la dominante."""
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    return "H" if dx >= dy else "V"


def _half_span_each_side(
    axis: str,
    x1: float, y1: float, x2: float, y2: float,
    emprise_bbox: dict,
    other_supports: list[tuple[float, float]],
    default_half_span_m: float = 2.0,
    max_half_span_m: float = 4.0,
) -> tuple[float, float]:
    """
    Calcule la demi-portee de chaque cote du voile.

    Pour un voile vertical (axe selon Y) : on regarde a gauche (x plus petit)
    et a droite (x plus grand) le prochain appui parallele.
    Pour un voile horizontal (axe selon X) : on regarde en bas et en haut.

    La demi-portee = (distance au prochain appui) / 2, bornee.
    Si aucun appui de ce cote : on prend la distance jusqu'au bord d'emprise / 2.
    """
    if axis == "V":
        x_wall = 0.5 * (x1 + x2)
        ymin_wall = min(y1, y2)
        ymax_wall = max(y1, y2)

        # Appuis "paralleles" = ceux dont la projection Y recouvre le voile
        left_xs = []
        right_xs = []
        for (sx, sy) in other_supports:
            if ymin_wall - 0.5 <= sy <= ymax_wall + 0.5:
                if sx < x_wall - 1e-6:
                    left_xs.append(sx)
                elif sx > x_wall + 1e-6:
                    right_xs.append(sx)

        # Cote gauche
        if left_xs:
            d_left = x_wall - max(left_xs)
        else:
            d_left = x_wall - emprise_bbox["xmin"]
        # Cote droit
        if right_xs:
            d_right = min(right_xs) - x_wall
        else:
            d_right = emprise_bbox["xmax"] - x_wall

    else:  # axis == "H"
        y_wall = 0.5 * (y1 + y2)
        xmin_wall = min(x1, x2)
        xmax_wall = max(x1, x2)

        down_ys = []
        up_ys = []
        for (sx, sy) in other_supports:
            if xmin_wall - 0.5 <= sx <= xmax_wall + 0.5:
                if sy < y_wall - 1e-6:
                    down_ys.append(sy)
                elif sy > y_wall + 1e-6:
                    up_ys.append(sy)

        if down_ys:
            d_left = y_wall - max(down_ys)
        else:
            d_left = y_wall - emprise_bbox["ymin"]
        if up_ys:
            d_right = min(up_ys) - y_wall
        else:
            d_right = emprise_bbox["ymax"] - y_wall

    half_left = max(0.0, min(d_left / 2.0, max_half_span_m))
    half_right = max(0.0, min(d_right / 2.0, max_half_span_m))

    # garde-fou si valeurs nulles
    if half_left <= 1e-6:
        half_left = default_half_span_m
    if half_right <= 1e-6:
        half_right = default_half_span_m

    return half_left, half_right


def compute_wall_load_takedown(
    model: dict[str, Any],
    wall_thickness_m: float = 0.20,
    storey_height_m: float = 3.0,
    g_floor_kN_m2: float = 5.0,
    q_floor_kN_m2: float = 1.5,
    g_terrace_kN_m2: float = 6.0,
    q_terrace_kN_m2: float = 1.0,
    gamma_g: float = 1.35,
    gamma_q: float = 1.5,
    gamma_wall_kN_m3: float = 25.0,
) -> dict[str, Any]:
    """
    Calcule la charge lineaire ELS/ELU (kN/ml) de chaque voile, par bande
    tributaire (demi-portee de chaque cote), cumulee sur les niveaux portes.

    Retourne un dict avec, par voile (identifie par son id au niveau FONDATION) :
    - largeur de bande tributaire,
    - charge lineaire G, Q, ELS, ELU,
    - niveaux portes.
    Inclut le poids propre du voile (epaisseur * hauteur d'etage * gamma).
    """
    levels = model.get("levels", [])
    if not levels:
        return {"status": "NOT_OK", "message": "Aucun niveau dans le modele.", "walls": []}

    # Niveaux structurels tries
    level_names = [lvl["name"] for lvl in levels]
    structural = sorted(level_names, key=level_sort_key)

    # Emprise de reference (niveau FONDATION sinon premier)
    fondation = next((l for l in levels if l["name"] == "FONDATION"), levels[0])
    footprints = fondation.get("footprints", [])
    if footprints:
        emp = footprints[0]["bbox"]
    else:
        emp = {"xmin": 0, "ymin": 0, "xmax": 0, "ymax": 0}

    # Appuis (poteaux) de reference pour les portees, depuis FONDATION
    supports = [(c["cx"], c["cy"]) for c in fondation.get("columns", [])]

    # Voiles au niveau FONDATION (ce sont eux qui portent les semelles filantes)
    wall_axes = fondation.get("wall_axes", [])
    if not wall_axes:
        return {"status": "OK", "message": "Aucun voile (VOILE-AXE) trouve.", "walls": []}

    walls_result = []

    for wa in wall_axes:
        x1, y1, x2, y2 = wa["x1"], wa["y1"], wa["x2"], wa["y2"]
        length = wa["length_m"]
        axis = _wall_orientation(x1, y1, x2, y2)

        half_l, half_r = _half_span_each_side(
            axis, x1, y1, x2, y2, emp, supports
        )
        band_width = half_l + half_r

        # Cumul des charges surfaciques sur les niveaux portes (hors FONDATION)
        sum_g_lin = 0.0
        sum_q_lin = 0.0
        levels_supported = []

        for lvl in levels:
            name = lvl["name"]
            if name == "FONDATION":
                continue
            if is_top_structural_level(name, structural):
                g_used, q_used = g_terrace_kN_m2, q_terrace_kN_m2
            else:
                g_used, q_used = g_floor_kN_m2, q_floor_kN_m2

            # charge lineaire de ce niveau = bande * charge surfacique
            g_lin = band_width * g_used
            q_lin = band_width * q_used
            sum_g_lin += g_lin
            sum_q_lin += q_lin
            levels_supported.append(name)

        # Poids propre du voile (par metre lineaire) : ep * hauteur etage * gamma * nb niveaux
        n_levels = max(1, len(levels_supported))
        wall_self_weight_lin = wall_thickness_m * storey_height_m * n_levels * gamma_wall_kN_m3
        sum_g_lin += wall_self_weight_lin

        n_els_lin = sum_g_lin + sum_q_lin
        n_uls_lin = gamma_g * sum_g_lin + gamma_q * sum_q_lin

        walls_result.append({
            "id": wa["id"],
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "length_m": length,
            "axis": axis,
            "thickness_m": wall_thickness_m,
            "tributary_half_left_m": round(half_l, 3),
            "tributary_half_right_m": round(half_r, 3),
            "tributary_band_width_m": round(band_width, 3),
            "levels_supported": levels_supported,
            "wall_self_weight_kN_per_m": round(wall_self_weight_lin, 2),
            "g_lin_kN_per_m": round(sum_g_lin, 2),
            "q_lin_kN_per_m": round(sum_q_lin, 2),
            "n_sls_kN_per_m": round(n_els_lin, 2),
            "n_uls_kN_per_m": round(n_uls_lin, 2),
            "combination_elu": f"{gamma_g}G + {gamma_q}Q",
        })

    return {
        "status": "OK",
        "method": "wall_tributary_half_span_v1",
        "wall_thickness_m": wall_thickness_m,
        "walls": walls_result,
    }
