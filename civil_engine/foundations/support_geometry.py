from __future__ import annotations

import math
from typing import Any

from civil_engine.foundations.column_effective import get_effective_column_boxes


def round_up(value: float, step: float = 0.05) -> float:
    return round(math.ceil(value / step) * step, 3)


def clamp(value: float, vmin: float, vmax: float) -> float:
    return min(max(value, vmin), vmax)


def get_foundation_level(model: dict[str, Any]) -> dict[str, Any] | None:
    for level in model.get("levels", []):
        if level.get("name") == "FONDATION":
            return level
    return None


def bbox_from_points(points: list[list[float]]) -> dict[str, float] | None:
    if not points:
        return None

    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]

    return {
        "xmin": min(xs),
        "xmax": max(xs),
        "ymin": min(ys),
        "ymax": max(ys),
    }


def get_foundation_bbox(model: dict[str, Any]) -> dict[str, float] | None:
    foundation = get_foundation_level(model)

    if foundation is None:
        return None

    points = []

    for footprint in foundation.get("footprints", []):
        points.extend(footprint.get("points", []))

    return bbox_from_points(points)


def get_property_limit_bbox(model: dict[str, Any]) -> dict[str, float] | None:
    """
    Limite constructive réelle.

    Priorité :
    - LIMITE-PROPRIETE si elle existe ;
    - sinon FONDATION-EMPRISE.

    Cela évite de prendre un axe de façade comme une vraie limite physique.
    """
    points = []

    global_layers = model.get("global_layers", {})

    for item in global_layers.get("limite_propriete", []):
        points.extend(item.get("points", []))

    bbox = bbox_from_points(points)

    if bbox is not None:
        return bbox

    return get_foundation_bbox(model)


def get_column_boxes(model: dict[str, Any]) -> dict[str, dict[str, float]]:
    foundation = get_foundation_level(model)

    if foundation is None:
        return {}

    result = {}

    for column in foundation.get("columns", []):
        column_id = column["id"]
        cx = float(column.get("cx", 0.0))
        cy = float(column.get("cy", 0.0))

        points = column.get("points", [])

        if points:
            xs = [float(p[0]) for p in points]
            ys = [float(p[1]) for p in points]

            xmin = min(xs)
            xmax = max(xs)
            ymin = min(ys)
            ymax = max(ys)
        else:
            xmin = cx - 0.125
            xmax = cx + 0.125
            ymin = cy - 0.125
            ymax = cy + 0.125

        result[column_id] = {
            "cx": cx,
            "cy": cy,
            "xmin": xmin,
            "xmax": xmax,
            "ymin": ymin,
            "ymax": ymax,
            "c1_m": xmax - xmin,
            "c2_m": ymax - ymin,
        }

    return result


def bbox_inside(bbox: dict[str, float], limit: dict[str, float] | None) -> bool:
    if limit is None:
        return True

    return (
        float(bbox["xmin"]) >= float(limit["xmin"]) - 1e-6
        and float(bbox["xmax"]) <= float(limit["xmax"]) + 1e-6
        and float(bbox["ymin"]) >= float(limit["ymin"]) - 1e-6
        and float(bbox["ymax"]) <= float(limit["ymax"]) + 1e-6
    )


def interval_containing_required_box(
    required_min: float,
    required_max: float,
    current_min: float,
    current_max: float,
    limit_min: float,
    limit_max: float,
    step_m: float = 0.05,
) -> tuple[float, float, bool]:
    """
    Trouve un intervalle final qui :
    - contient required_min / required_max ;
    - reste dans limit_min / limit_max ;
    - garde au maximum la largeur actuelle ;
    - décale vers l'intérieur si nécessaire.
    """
    required_len = required_max - required_min
    current_len = current_max - current_min

    length = round_up(max(required_len, current_len, step_m), step_m)

    available = limit_max - limit_min

    if length > available + 1e-9:
        return current_min, current_max, False

    start_min = max(limit_min, required_max - length)
    start_max = min(required_min, limit_max - length)

    if start_min > start_max + 1e-9:
        return current_min, current_max, False

    current_center = (current_min + current_max) / 2.0
    preferred_start = current_center - length / 2.0

    start = clamp(preferred_start, start_min, start_max)
    end = start + length

    return round(start, 4), round(end, 4), True


def union_column_box(
    column_ids: list[str],
    column_boxes: dict[str, dict[str, float]],
    margin_m: float,
) -> tuple[dict[str, float] | None, list[str]]:
    missing = []
    boxes = []

    for column_id in column_ids:
        col = column_boxes.get(column_id)

        if col is None:
            missing.append(column_id)
            continue

        boxes.append(col)

    if not boxes:
        return None, missing

    return {
        "xmin": min(float(col["xmin"]) for col in boxes) - margin_m,
        "xmax": max(float(col["xmax"]) for col in boxes) + margin_m,
        "ymin": min(float(col["ymin"]) for col in boxes) - margin_m,
        "ymax": max(float(col["ymax"]) for col in boxes) + margin_m,
    }, missing


def check_columns_supported(
    element: dict[str, Any],
    column_boxes: dict[str, dict[str, float]],
    margin_m: float,
) -> tuple[bool, list[str]]:
    bbox = element["bbox"]
    bad = []

    for column_id in element.get("columns", []):
        col = column_boxes.get(column_id)

        if col is None:
            bad.append(column_id)
            continue

        if (
            float(col["xmin"]) - margin_m < float(bbox["xmin"]) - 1e-6
            or float(col["xmax"]) + margin_m > float(bbox["xmax"]) + 1e-6
            or float(col["ymin"]) - margin_m < float(bbox["ymin"]) - 1e-6
            or float(col["ymax"]) + margin_m > float(bbox["ymax"]) + 1e-6
        ):
            bad.append(column_id)

    return len(bad) == 0, bad


def fix_one_foundation(
    element: dict[str, Any],
    column_boxes: dict[str, dict[str, float]],
    limit_bbox: dict[str, float] | None,
    support_margin_m: float,
    step_m: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    item = dict(element)
    warnings = []

    if "bbox" not in item:
        item["support_status"] = "REVIEW"
        item["note"] = "bbox fondation manquant"
        return item, warnings

    bbox = dict(item["bbox"])

    if limit_bbox is None:
        limit_bbox = {
            "xmin": -1_000_000.0,
            "xmax": 1_000_000.0,
            "ymin": -1_000_000.0,
            "ymax": 1_000_000.0,
        }

    # 1. Essai avec marge constructive.
    required, missing = union_column_box(
        item.get("columns", []),
        column_boxes,
        margin_m=support_margin_m,
    )

    margin_used = support_margin_m

    # 2. Si la marge ne rentre pas dans la limite, essai sans marge.
    if required is None:
        item["support_status"] = "REVIEW"
        item["support_bad_columns"] = missing
        item["note"] = "poteau introuvable dans le modele"
        return item, warnings

    if not bbox_inside(required, limit_bbox):
        required, missing = union_column_box(
            item.get("columns", []),
            column_boxes,
            margin_m=0.0,
        )
        margin_used = 0.0

    if required is None:
        item["support_status"] = "REVIEW"
        item["support_bad_columns"] = missing
        item["note"] = "poteau introuvable dans le modele"
        return item, warnings

    # 3. L'intervalle final doit contenir le poteau complet.
    xmin, xmax, ok_x = interval_containing_required_box(
        required_min=float(required["xmin"]),
        required_max=float(required["xmax"]),
        current_min=float(bbox["xmin"]),
        current_max=float(bbox["xmax"]),
        limit_min=float(limit_bbox["xmin"]),
        limit_max=float(limit_bbox["xmax"]),
        step_m=step_m,
    )

    ymin, ymax, ok_y = interval_containing_required_box(
        required_min=float(required["ymin"]),
        required_max=float(required["ymax"]),
        current_min=float(bbox["ymin"]),
        current_max=float(bbox["ymax"]),
        limit_min=float(limit_bbox["ymin"]),
        limit_max=float(limit_bbox["ymax"]),
        step_m=step_m,
    )

    # 4. Si impossible, on garde la fondation mais on alerte.
    if not ok_x or not ok_y:
        item["support_status"] = "REVIEW"
        item["support_bad_columns"] = item.get("columns", [])
        item["note"] = "support poteau impossible dans la limite actuelle"
        warnings.append({
            "code": "SUPPORT_COLUMN_TO_REVIEW",
            "foundation_id": item.get("id"),
            "message": "Poteau non supportable dans la limite actuelle. Reprendre en PR / SC / RL.",
        })
        return item, warnings

    new_bbox = {
        "xmin": round(xmin, 4),
        "xmax": round(xmax, 4),
        "ymin": round(ymin, 4),
        "ymax": round(ymax, 4),
    }

    item["bbox"] = new_bbox
    item["cx"] = round((xmin + xmax) / 2.0, 4)
    item["cy"] = round((ymin + ymax) / 2.0, 4)
    item["A_m"] = round(xmax - xmin, 3)
    item["B_m"] = round(ymax - ymin, 3)
    item["area_provided_m2"] = round((xmax - xmin) * (ymax - ymin), 4)

    n_els = item.get("N_ELS_kN")

    if n_els is not None and item["area_provided_m2"] > 0:
        item["soil_pressure_ELS_kPa"] = round(float(n_els) / item["area_provided_m2"], 3)

    supported, bad_cols = check_columns_supported(
        item,
        column_boxes,
        margin_m=margin_used,
    )

    item["inside_emprise"] = bbox_inside(new_bbox, limit_bbox)
    item["columns_inside"] = supported
    item["support_margin_m"] = margin_used
    item["support_bad_columns"] = bad_cols

    if supported and item["inside_emprise"]:
        item["support_status"] = "OK"

        if margin_used == 0.0:
            item["note"] = "poteau porte sans marge constructive complete"
            warnings.append({
                "code": "SUPPORT_MARGIN_REDUCED",
                "foundation_id": item.get("id"),
                "message": "Le poteau est supporte, mais la marge constructive est reduite par la limite.",
            })
        else:
            item["note"] = item.get("note") or "support poteau verifie"
    else:
        item["support_status"] = "REVIEW"
        item["note"] = "support poteau a reprendre"
        warnings.append({
            "code": "SUPPORT_COLUMN_TO_REVIEW",
            "foundation_id": item.get("id"),
            "columns": bad_cols,
            "message": "Fondation conservee, mais support poteau a reprendre.",
        })

    # On ne change jamais item["status"] en ALTERNATIVE_REQUIRED ici.
    return item, warnings


def fix_support_geometry_non_destructive(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    support_margin_m: float = 0.05,
    step_m: float = 0.05,
) -> dict[str, Any]:
    """
    Correction non destructive.

    Le programme ne supprime aucune fondation.
    Il recale les fondations pour porter les poteaux complets.
    Si impossible, il conserve la fondation et ajoute une alerte.
    """
    report = dict(strategy_report)

    limit_bbox = get_property_limit_bbox(model)
    column_boxes = get_effective_column_boxes(model)

    final = []
    warnings = list(report.get("warnings", []))

    for element in report.get("final_foundations", []):
        fixed, local_warnings = fix_one_foundation(
            element=element,
            column_boxes=column_boxes,
            limit_bbox=limit_bbox,
            support_margin_m=support_margin_m,
            step_m=step_m,
        )

        final.append(fixed)
        warnings.extend(local_warnings)

    report["final_foundations"] = final
    report["warnings"] = warnings

    report["combined_footings"] = [item for item in final if item.get("type") == "SC"]
    report["local_rafts"] = [item for item in final if item.get("type") == "RL"]

    report["support_geometry_check"] = {
        "method": "column_box_support_non_destructive_v0_21_4",
        "constraint": "LIMITE-PROPRIETE si disponible, sinon FONDATION-EMPRISE",
        "support_margin_m": support_margin_m,
        "final_foundations_count": len(final),
        "warnings_count": len(warnings),
    }

    return report
