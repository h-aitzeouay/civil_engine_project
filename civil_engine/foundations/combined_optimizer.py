from __future__ import annotations

import math
from typing import Any

from civil_engine.foundations.combined_footings import generate_combined_footings
from civil_engine.foundations.combined_eccentricity import (
    compute_resultant_for_combined,
    compute_soil_pressures_biaxial,
)


def round_up(value: float, step: float = 0.05) -> float:
    return round(math.ceil(value / step) * step, 3)


def bbox_from_center(cx: float, cy: float, bx: float, ly: float) -> dict[str, float]:
    return {
        "xmin": round(cx - bx / 2.0, 4),
        "xmax": round(cx + bx / 2.0, 4),
        "ymin": round(cy - ly / 2.0, 4),
        "ymax": round(cy + ly / 2.0, 4),
    }


def get_foundation_level(model: dict[str, Any]) -> dict[str, Any] | None:
    for level in model.get("levels", []):
        if level.get("name") == "FONDATION":
            return level
    return None


def get_foundation_bbox(model: dict[str, Any]) -> dict[str, float] | None:
    foundation = get_foundation_level(model)

    if not foundation:
        return None

    points: list[list[float]] = []

    for footprint in foundation.get("footprints", []):
        points.extend(footprint.get("points", []))

    if not points:
        return None

    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]

    return {
        "xmin": round(min(xs), 4),
        "xmax": round(max(xs), 4),
        "ymin": round(min(ys), 4),
        "ymax": round(max(ys), 4),
    }


def get_involved_isolated_footings(
    combined: dict[str, Any],
    isolated_footings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    columns = set(combined.get("columns", []))

    return [
        footing for footing in isolated_footings
        if footing.get("column_id") in columns
    ]


def get_column_extents(
    combined: dict[str, Any],
    isolated_footings: list[dict[str, Any]],
) -> dict[str, float]:
    involved = get_involved_isolated_footings(
        combined=combined,
        isolated_footings=isolated_footings,
    )

    xs = [
        float(footing.get("column_cx", footing["cx"]))
        for footing in involved
    ]

    ys = [
        float(footing.get("column_cy", footing["cy"]))
        for footing in involved
    ]

    return {
        "min_x": min(xs),
        "max_x": max(xs),
        "min_y": min(ys),
        "max_y": max(ys),
    }


def center_interval_for_emprise_and_columns(
    bx: float,
    ly: float,
    foundation_bbox: dict[str, float],
    column_extents: dict[str, float],
    column_margin_m: float = 0.25,
    emprise_margin_m: float = 0.05,
) -> dict[str, Any]:
    """
    Centre admissible = intersection entre :
    - rester dans l'emprise ;
    - englober tous les poteaux avec une marge.
    """
    xmin = float(foundation_bbox["xmin"]) + emprise_margin_m
    xmax = float(foundation_bbox["xmax"]) - emprise_margin_m
    ymin = float(foundation_bbox["ymin"]) + emprise_margin_m
    ymax = float(foundation_bbox["ymax"]) - emprise_margin_m

    cx_min_emprise = xmin + bx / 2.0
    cx_max_emprise = xmax - bx / 2.0
    cy_min_emprise = ymin + ly / 2.0
    cy_max_emprise = ymax - ly / 2.0

    cx_min_columns = float(column_extents["max_x"]) + column_margin_m - bx / 2.0
    cx_max_columns = float(column_extents["min_x"]) - column_margin_m + bx / 2.0
    cy_min_columns = float(column_extents["max_y"]) + column_margin_m - ly / 2.0
    cy_max_columns = float(column_extents["min_y"]) - column_margin_m + ly / 2.0

    cx_min = max(cx_min_emprise, cx_min_columns)
    cx_max = min(cx_max_emprise, cx_max_columns)
    cy_min = max(cy_min_emprise, cy_min_columns)
    cy_max = min(cy_max_emprise, cy_max_columns)

    return {
        "can_place": cx_min <= cx_max and cy_min <= cy_max,
        "cx_min": cx_min,
        "cx_max": cx_max,
        "cy_min": cy_min,
        "cy_max": cy_max,
    }


def clamp(value: float, min_value: float, max_value: float) -> float:
    return min(max(value, min_value), max_value)


def bbox_intersects(a: dict[str, float], b: dict[str, float]) -> bool:
    if a["xmax"] <= b["xmin"]:
        return False
    if a["xmin"] >= b["xmax"]:
        return False
    if a["ymax"] <= b["ymin"]:
        return False
    if a["ymin"] >= b["ymax"]:
        return False
    return True


def bbox_inside_boundary(
    bbox: dict[str, float],
    boundary: dict[str, float],
    tolerance_m: float = 1e-6,
) -> bool:
    return (
        float(bbox["xmin"]) >= float(boundary["xmin"]) - tolerance_m
        and float(bbox["xmax"]) <= float(boundary["xmax"]) + tolerance_m
        and float(bbox["ymin"]) >= float(boundary["ymin"]) - tolerance_m
        and float(bbox["ymax"]) <= float(boundary["ymax"]) + tolerance_m
    )


def candidate_intersects_unmerged_isolated(
    candidate_bbox: dict[str, float],
    current_component_ids: list[str],
    isolated_footings: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Refuse une semelle combinée qui interfère avec une semelle isolée conservée.
    Exemple : la semelle combinée bleue ne doit pas toucher une semelle verte non fusionnée.
    """
    ignored = set(current_component_ids)

    collisions = []

    for footing in isolated_footings:
        if footing.get("id") in ignored:
            continue

        if footing.get("merged"):
            continue

        if "bbox" not in footing:
            continue

        if bbox_intersects(candidate_bbox, footing["bbox"]):
            collisions.append({
                "footing_id": footing.get("id"),
                "column_id": footing.get("column_id"),
                "message": "Interférence avec une semelle isolée conservée.",
            })

    return {
        "has_collision": len(collisions) > 0,
        "collisions": collisions,
    }


def make_candidate(
    label: str,
    bx: float,
    ly: float,
    desired_cx: float,
    desired_cy: float,
    area_required: float,
    foundation_bbox: dict[str, float],
    column_extents: dict[str, float],
    dimension_step_m: float = 0.05,
) -> dict[str, Any] | None:
    bx = round_up(bx, dimension_step_m)
    ly = round_up(ly, dimension_step_m)

    area = bx * ly

    if area < area_required:
        return None

    interval = center_interval_for_emprise_and_columns(
        bx=bx,
        ly=ly,
        foundation_bbox=foundation_bbox,
        column_extents=column_extents,
    )

    if not interval["can_place"]:
        return None

    cx = clamp(desired_cx, interval["cx_min"], interval["cx_max"])
    cy = clamp(desired_cy, interval["cy_min"], interval["cy_max"])

    candidate_bbox = bbox_from_center(cx, cy, bx, ly)

    if not bbox_inside_boundary(candidate_bbox, foundation_bbox):
        return None

    if current_component_ids is not None and isolated_footings is not None:
        collision_report = candidate_intersects_unmerged_isolated(
            candidate_bbox=candidate_bbox,
            current_component_ids=current_component_ids,
            isolated_footings=isolated_footings,
        )

        if collision_report["has_collision"]:
            return None

    candidate_bbox = bbox_from_center(cx, cy, bx, ly)

    if not bbox_inside_boundary(candidate_bbox, foundation_bbox):
        return None

    if current_component_ids is not None and isolated_footings is not None:
        collision_report = candidate_intersects_unmerged_isolated(
            candidate_bbox=candidate_bbox,
            current_component_ids=current_component_ids,
            isolated_footings=isolated_footings,
        )

        if collision_report["has_collision"]:
            return None

    return {
        "label": label,
        "Bx_m": round(bx, 3),
        "Ly_m": round(ly, 3),
        "cx": round(cx, 4),
        "cy": round(cy, 4),
        "area_provided_m2": round(area, 4),
        "bbox": candidate_bbox,
        "center_interval": {
            "cx_min": round(interval["cx_min"], 4),
            "cx_max": round(interval["cx_max"], 4),
            "cy_min": round(interval["cy_min"], 4),
            "cy_max": round(interval["cy_max"], 4),
        },
    }


def redesign_combined_footing_inside_emprise(
    combined: dict[str, Any],
    isolated_footings: list[dict[str, Any]],
    foundation_bbox: dict[str, float] | None,
    q_allowable_kPa: float,
) -> dict[str, Any]:
    """
    Redimensionne une semelle combinée pour rester dans l'emprise.

    Règle ajoutée :
    Si la semelle déborde dans un sens, on essaye d'augmenter
    l'autre dimension pour conserver la surface nécessaire.
    """
    if foundation_bbox is None:
        return {
            "status": "NO_EMPRISE",
            "message": "Emprise introuvable.",
            "selected_candidate": None,
        }

    resultant = compute_resultant_for_combined(
        combined=combined,
        isolated_footings=isolated_footings,
    )

    if resultant["status"] == "ERROR":
        return {
            "status": "ERROR",
            "message": resultant["message"],
            "selected_candidate": None,
        }

    desired_cx = float(resultant["xR"])
    desired_cy = float(resultant["yR"])

    total_n_els = float(resultant["N_ELS_kN"])
    area_required = total_n_els / q_allowable_kPa

    original_bx = float(combined["Bx_m"])
    original_ly = float(combined["Ly_m"])

    column_extents = get_column_extents(
        combined=combined,
        isolated_footings=isolated_footings,
    )

    span_x = float(column_extents["max_x"]) - float(column_extents["min_x"])
    span_y = float(column_extents["max_y"]) - float(column_extents["min_y"])

    column_margin_m = 0.25
    emprise_margin_m = 0.05

    min_bx_cover = max(0.80, span_x + 2.0 * column_margin_m)
    min_ly_cover = max(0.80, span_y + 2.0 * column_margin_m)

    max_bx = (
        float(foundation_bbox["xmax"])
        - float(foundation_bbox["xmin"])
        - 2.0 * emprise_margin_m
    )

    max_ly = (
        float(foundation_bbox["ymax"])
        - float(foundation_bbox["ymin"])
        - 2.0 * emprise_margin_m
    )

    if min_bx_cover > max_bx or min_ly_cover > max_ly:
        return {
            "status": "CANNOT_FIT_COLUMNS_WITHIN_EMPRISE",
            "message": "Les poteaux du groupe ne peuvent pas être englobés dans l'emprise avec les marges minimales.",
            "min_bx_cover": round(min_bx_cover, 3),
            "min_ly_cover": round(min_ly_cover, 3),
            "max_bx_available": round(max_bx, 3),
            "max_ly_available": round(max_ly, 3),
            "selected_candidate": None,
        }

    candidates: list[dict[str, Any]] = []

    def add_candidate(label: str, bx: float, ly: float) -> None:
        candidate = make_candidate(
            label=label,
            bx=max(bx, min_bx_cover),
            ly=max(ly, min_ly_cover),
            desired_cx=desired_cx,
            desired_cy=desired_cy,
            area_required=area_required,
            foundation_bbox=foundation_bbox,
            column_extents=column_extents,
        )

        if candidate is not None:
            if candidate["Bx_m"] <= max_bx and candidate["Ly_m"] <= max_ly:
                candidates.append(candidate)

    # 1. Solution originale si elle rentre.
    add_candidate(
        label="ORIGINAL_IF_FITS",
        bx=original_bx,
        ly=original_ly,
    )

    # 2. Si la longueur Y est trop grande, on limite Y et on part en largeur X.
    ly_limited = min(original_ly, max_ly)
    bx_needed_for_limited_y = area_required / max(ly_limited, 1e-9)

    add_candidate(
        label="WIDTH_INCREASED_X_TO_AVOID_Y_OVERFLOW",
        bx=max(original_bx, bx_needed_for_limited_y),
        ly=ly_limited,
    )

    # 3. Variante plus large : on réduit davantage Y si possible et on augmente X.
    ly_compact = max(min_ly_cover, min(max_ly, original_ly * 0.70))
    bx_needed_for_compact_y = area_required / max(ly_compact, 1e-9)

    add_candidate(
        label="COMPACT_Y_AND_WIDEN_X",
        bx=max(min_bx_cover, bx_needed_for_compact_y),
        ly=ly_compact,
    )

    # 4. Si X déborde, on fait l'inverse : limiter X et augmenter Y.
    bx_limited = min(original_bx, max_bx)
    ly_needed_for_limited_x = area_required / max(bx_limited, 1e-9)

    add_candidate(
        label="LENGTH_INCREASED_Y_TO_AVOID_X_OVERFLOW",
        bx=bx_limited,
        ly=max(original_ly, ly_needed_for_limited_x),
    )

    # 5. Semelle équilibrée sur la surface nécessaire.
    side = math.sqrt(area_required)

    add_candidate(
        label="BALANCED_RECTANGLE",
        bx=max(side, min_bx_cover),
        ly=max(side, min_ly_cover),
    )

    if not candidates:
        return {
            "status": "NO_CONSTRUCTIBLE_RECTANGLE_FOUND",
            "message": (
                "Impossible de trouver une semelle combinée rectangulaire dans l'emprise "
                "avec la surface et les marges demandées. Alternative : PR, radier local, "
                "semelle filante ou reprise du groupe."
            ),
            "area_required_m2": round(area_required, 4),
            "min_bx_cover": round(min_bx_cover, 3),
            "min_ly_cover": round(min_ly_cover, 3),
            "max_bx_available": round(max_bx, 3),
            "max_ly_available": round(max_ly, 3),
            "selected_candidate": None,
        }

    # Choix : surface la plus faible, mais en privilégiant les solutions qui partent en largeur.
    priority = {
        "WIDTH_INCREASED_X_TO_AVOID_Y_OVERFLOW": 0,
        "COMPACT_Y_AND_WIDEN_X": 1,
        "ORIGINAL_IF_FITS": 2,
        "BALANCED_RECTANGLE": 3,
        "LENGTH_INCREASED_Y_TO_AVOID_X_OVERFLOW": 4,
    }

    candidates = sorted(
        candidates,
        key=lambda c: (
            priority.get(c["label"], 99),
            c["area_provided_m2"],
        ),
    )

    selected = candidates[0]

    return {
        "status": "OK",
        "message": "Semelle combinée redimensionnée dans l'emprise.",
        "area_required_m2": round(area_required, 4),
        "original_dimensions": {
            "Bx_m": original_bx,
            "Ly_m": original_ly,
            "area_m2": round(original_bx * original_ly, 4),
        },
        "selected_candidate": selected,
        "all_candidates_count": len(candidates),
    }


def check_one_combined_footing(
    combined: dict[str, Any],
    isolated_footings: list[dict[str, Any]],
    q_allowable_kPa: float,
) -> dict[str, Any]:
    resultant = compute_resultant_for_combined(
        combined=combined,
        isolated_footings=isolated_footings,
    )

    if resultant["status"] == "ERROR":
        return {
            "status": "ERROR",
            "message": resultant["message"],
        }

    bx = float(combined["Bx_m"])
    ly = float(combined["Ly_m"])

    cx = float(combined["cx"])
    cy = float(combined["cy"])

    xR = float(resultant["xR"])
    yR = float(resultant["yR"])

    ex = round(xR - cx, 4)
    ey = round(yR - cy, 4)

    pressures = compute_soil_pressures_biaxial(
        N_ELS_kN=float(resultant["N_ELS_kN"]),
        Bx_m=bx,
        Ly_m=ly,
        ex_m=ex,
        ey_m=ey,
    )

    qmin = pressures["qmin_kPa"]
    qmax = pressures["qmax_kPa"]

    kern_limit_x = round(bx / 6.0, 4)
    kern_limit_y = round(ly / 6.0, 4)

    kern_ok = abs(ex) <= kern_limit_x and abs(ey) <= kern_limit_y
    no_tension_ok = qmin is not None and qmin >= 0.0
    bearing_ok = qmax is not None and qmax <= q_allowable_kPa

    status = "OK" if kern_ok and no_tension_ok and bearing_ok else "WARNING"

    return {
        "status": status,
        "N_ELS_kN": resultant["N_ELS_kN"],
        "xR": xR,
        "yR": yR,
        "ex_m": ex,
        "ey_m": ey,
        "kern_limit_x_m": kern_limit_x,
        "kern_limit_y_m": kern_limit_y,
        "kern_ok": kern_ok,
        "qmin_kPa": qmin,
        "qmax_kPa": qmax,
        "bearing_ok": bearing_ok,
        "no_tension_ok": no_tension_ok,
        "corner_pressures_kPa": pressures["corner_pressures_kPa"],
    }


def optimize_combined_footings(
    model: dict[str, Any],
    q_allowable_kPa: float = 200.0,
) -> dict[str, Any]:
    combined_report = generate_combined_footings(
        model=model,
        q_allowable_kPa=q_allowable_kPa,
    )

    isolated_footings = combined_report.get("isolated_footings", [])
    combined_footings = combined_report.get("combined_footings", [])

    foundation_bbox = get_foundation_bbox(model)

    optimized_combined_footings = []
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    if not combined_footings:
        return {
            "status": "OK",
            "method": "combined_footing_width_expansion_inside_emprise_v0_15_3",
            "message": "Aucune semelle combinée à optimiser.",
            "q_allowable_kPa": q_allowable_kPa,
            "foundation_bbox": foundation_bbox,
            "isolated_footings": isolated_footings,
            "optimized_combined_footings": [],
            "warnings": [],
            "errors": [],
            "summary": {
                "combined_footings_optimized": 0,
                "warnings_count": 0,
                "errors_count": 0,
            },
            "combined_report": combined_report,
        }

    for combined in combined_footings:
        before = check_one_combined_footing(
            combined=combined,
            isolated_footings=isolated_footings,
            q_allowable_kPa=q_allowable_kPa,
        )

        redesign = redesign_combined_footing_inside_emprise(
            combined=combined,
            isolated_footings=isolated_footings,
            foundation_bbox=foundation_bbox,
            q_allowable_kPa=q_allowable_kPa,
        )

        optimized = dict(combined)

        if redesign["status"] != "OK":
            optimized["status"] = "ALTERNATIVE_REQUIRED"
            optimized["redesign"] = redesign

            warnings.append({
                "code": "COMBINED_FOOTING_ALTERNATIVE_REQUIRED",
                "combined_id": combined["id"],
                "message": redesign.get("message", "Alternative nécessaire."),
            })

            optimized_combined_footings.append(optimized)
            continue

        candidate = redesign["selected_candidate"]

        old_cx = float(combined["cx"])
        old_cy = float(combined["cy"])

        optimized["Bx_m"] = candidate["Bx_m"]
        optimized["Ly_m"] = candidate["Ly_m"]
        optimized["cx"] = candidate["cx"]
        optimized["cy"] = candidate["cy"]
        optimized["bbox"] = candidate["bbox"]
        optimized["area_provided_m2"] = candidate["area_provided_m2"]

        optimized["redesign"] = redesign

        optimized["optimization"] = {
            "old_center": {
                "x": round(old_cx, 4),
                "y": round(old_cy, 4),
            },
            "new_center": {
                "x": candidate["cx"],
                "y": candidate["cy"],
            },
            "move_x_m": round(candidate["cx"] - old_cx, 4),
            "move_y_m": round(candidate["cy"] - old_cy, 4),
            "dimension_strategy": candidate["label"],
            "reason": (
                "Semelle redimensionnée pour rester dans l'emprise. "
                "Si nécessaire, augmentation de la largeur pour compenser la réduction de longueur."
            ),
        }

        after = check_one_combined_footing(
            combined=optimized,
            isolated_footings=isolated_footings,
            q_allowable_kPa=q_allowable_kPa,
        )

        optimized["eccentricity_check_before"] = before
        optimized["eccentricity_check_after"] = after
        optimized["status"] = "OPTIMIZED_PRELIMINARY"

        if after["status"] != "OK":
            warnings.append({
                "code": "OPTIMIZED_COMBINED_FOOTING_STILL_WARNING",
                "combined_id": combined["id"],
                "message": "La semelle redimensionnée reste à vérifier/corriger.",
                "qmin_kPa": after.get("qmin_kPa"),
                "qmax_kPa": after.get("qmax_kPa"),
                "ex_m": after.get("ex_m"),
                "ey_m": after.get("ey_m"),
            })

        optimized_combined_footings.append(optimized)

    all_warnings = warnings + combined_report.get("warnings", [])
    all_errors = errors + combined_report.get("errors", [])

    status = "OK"

    if all_errors:
        status = "ERROR"
    elif all_warnings:
        status = "WARNING"

    return {
        "status": status,
        "method": "combined_footing_width_expansion_inside_emprise_v0_15_3",
        "q_allowable_kPa": q_allowable_kPa,
        "foundation_bbox": foundation_bbox,
        "isolated_footings": isolated_footings,
        "optimized_combined_footings": optimized_combined_footings,
        "warnings": all_warnings,
        "errors": all_errors,
        "summary": {
            "combined_footings_optimized": len(optimized_combined_footings),
            "warnings_count": len(all_warnings),
            "errors_count": len(all_errors),
        },
        "combined_report": combined_report,
    }




