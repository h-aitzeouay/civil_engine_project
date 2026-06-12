from __future__ import annotations

import math
from typing import Any

from civil_engine.engine.load_takedown import compute_load_takedown


def round_up(value: float, step: float = 0.05) -> float:
    return round(math.ceil(value / step) * step, 3)


def get_foundation_level(model: dict[str, Any]) -> dict[str, Any] | None:
    for level in model.get("levels", []):
        if level.get("name") == "FONDATION":
            return level
    return None


def get_foundation_columns(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    foundation = get_foundation_level(model)
    if not foundation:
        return {}
    return {column["id"]: column for column in foundation.get("columns", [])}


def get_building_centroid(model: dict[str, Any]) -> tuple[float, float]:
    foundation = get_foundation_level(model)
    if not foundation:
        return (0.0, 0.0)

    points = []
    for footprint in foundation.get("footprints", []):
        points.extend(footprint.get("points", []))

    if not points:
        return (0.0, 0.0)

    cx = sum(float(p[0]) for p in points) / len(points)
    cy = sum(float(p[1]) for p in points) / len(points)

    return (cx, cy)


def point_to_segment_distance(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> float:
    dx = bx - ax
    dy = by - ay

    if dx == 0 and dy == 0:
        return math.sqrt((px - ax) ** 2 + (py - ay) ** 2)

    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))

    qx = ax + t * dx
    qy = ay + t * dy

    return math.sqrt((px - qx) ** 2 + (py - qy) ** 2)


def distance_to_property_limit(
    x: float,
    y: float,
    model: dict[str, Any],
) -> float | None:
    limit_items = model.get("global_layers", {}).get("limite_propriete", [])

    distances = []

    for item in limit_items:
        points = item.get("points", [])

        if len(points) < 2:
            continue

        if item.get("closed", False) and points[0] != points[-1]:
            points = points + [points[0]]

        for index in range(len(points) - 1):
            ax, ay = points[index]
            bx, by = points[index + 1]

            distances.append(
                point_to_segment_distance(
                    px=x,
                    py=y,
                    ax=float(ax),
                    ay=float(ay),
                    bx=float(bx),
                    by=float(by),
                )
            )

    if not distances:
        return None

    return round(min(distances), 4)


def normalize(dx: float, dy: float) -> tuple[float, float]:
    length = math.sqrt(dx * dx + dy * dy)

    if length < 1e-9:
        return (0.0, 0.0)

    return (dx / length, dy / length)


def footing_bbox(cx: float, cy: float, b: float, l: float) -> dict[str, float]:
    return {
        "xmin": round(cx - b / 2.0, 4),
        "xmax": round(cx + b / 2.0, 4),
        "ymin": round(cy - l / 2.0, 4),
        "ymax": round(cy + l / 2.0, 4),
    }


def rectangles_intersect(rect_a: dict[str, float], rect_b: dict[str, float]) -> bool:
    if rect_a["xmax"] <= rect_b["xmin"]:
        return False
    if rect_a["xmin"] >= rect_b["xmax"]:
        return False
    if rect_a["ymax"] <= rect_b["ymin"]:
        return False
    if rect_a["ymin"] >= rect_b["ymax"]:
        return False
    return True


def compute_footing_center_with_eccentricity(
    column_x: float,
    column_y: float,
    side: float,
    model: dict[str, Any],
    property_limit_margin_m: float,
) -> dict[str, Any]:
    """
    Décale la semelle vers l'intérieur si elle est proche de LIMITE-PROPRIETE.
    """
    distance = distance_to_property_limit(column_x, column_y, model)

    if distance is None:
        return {
            "is_eccentric": False,
            "footing_cx": column_x,
            "footing_cy": column_y,
            "distance_to_property_m": None,
            "shift_x_m": 0.0,
            "shift_y_m": 0.0,
            "eccentricity_x_m": 0.0,
            "eccentricity_y_m": 0.0,
        }

    half_side = side / 2.0
    required_distance = half_side + property_limit_margin_m

    if distance >= required_distance:
        return {
            "is_eccentric": False,
            "footing_cx": column_x,
            "footing_cy": column_y,
            "distance_to_property_m": distance,
            "shift_x_m": 0.0,
            "shift_y_m": 0.0,
            "eccentricity_x_m": 0.0,
            "eccentricity_y_m": 0.0,
        }

    building_cx, building_cy = get_building_centroid(model)

    ux, uy = normalize(
        building_cx - column_x,
        building_cy - column_y,
    )

    if ux == 0.0 and uy == 0.0:
        ux, uy = (1.0, 0.0)

    shift = required_distance - distance

    footing_cx = column_x + ux * shift
    footing_cy = column_y + uy * shift

    return {
        "is_eccentric": True,
        "footing_cx": round(footing_cx, 4),
        "footing_cy": round(footing_cy, 4),
        "distance_to_property_m": round(distance, 4),
        "shift_x_m": round(ux * shift, 4),
        "shift_y_m": round(uy * shift, 4),
        "eccentricity_x_m": round(column_x - footing_cx, 4),
        "eccentricity_y_m": round(column_y - footing_cy, 4),
    }


def predimension_isolated_footings(
    model: dict[str, Any],
    q_allowable_kPa: float = 200.0,
    min_side_m: float = 0.80,
    thickness_m: float = 0.35,
    dimension_step_m: float = 0.05,
    property_limit_margin_m: float = 0.05,
) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    if q_allowable_kPa <= 0:
        return {
            "status": "ERROR",
            "message": "q_allowable_kPa doit être > 0.",
            "warnings": [],
            "errors": [
                {
                    "code": "INVALID_SOIL_PRESSURE",
                    "message": "La contrainte admissible du sol doit être positive.",
                }
            ],
        }

    load_report = compute_load_takedown(model=model)
    foundation_columns_geom = get_foundation_columns(model)

    if load_report.get("status") == "ERROR":
        return {
            "status": "ERROR",
            "message": "Descente de charges impossible.",
            "load_report": load_report,
            "warnings": load_report.get("warnings", []),
            "errors": load_report.get("errors", []),
        }

    if not foundation_columns_geom:
        return {
            "status": "ERROR",
            "message": "Aucun poteau trouvé dans FONDATION-POTEAUX.",
            "warnings": [],
            "errors": [
                {
                    "code": "NO_FOUNDATION_COLUMNS",
                    "message": "Le niveau FONDATION ne contient pas de poteaux.",
                }
            ],
        }

    footings = []

    for item in load_report.get("foundation_columns", []):
        column_id = item["column_id"]
        column_geom = foundation_columns_geom.get(column_id)

        if column_geom is None:
            errors.append({
                "code": "COLUMN_LOAD_WITHOUT_GEOMETRY",
                "column_id": column_id,
                "message": f"Charge trouvée pour {column_id}, mais géométrie absente.",
            })
            continue

        n_els = float(item["sum_N_ELS_kN"])
        n_elu = float(item["sum_N_ELU_kN"])

        required_area = n_els / q_allowable_kPa

        side = math.sqrt(required_area)
        side = max(side, min_side_m)
        side = round_up(side, dimension_step_m)

        area_provided = round(side * side, 4)
        soil_pressure_els = round(n_els / area_provided, 3)

        column_x = float(column_geom["cx"])
        column_y = float(column_geom["cy"])

        eccentric = compute_footing_center_with_eccentricity(
            column_x=column_x,
            column_y=column_y,
            side=side,
            model=model,
            property_limit_margin_m=property_limit_margin_m,
        )

        footing_cx = float(eccentric["footing_cx"])
        footing_cy = float(eccentric["footing_cy"])

        if eccentric["is_eccentric"]:
            footing_type = "ECCENTRIC_FOOTING_PRELIMINARY"
            constructability_status = "PR_REQUIRED"
            requires_pr = True

            warnings.append({
                "code": "ECCENTRIC_FOOTING_CREATED",
                "column_id": column_id,
                "message": (
                    f"La semelle {column_id} a été décalée vers l'intérieur. "
                    f"Une poutre de redressement PR est nécessaire."
                ),
                "shift_x_m": eccentric["shift_x_m"],
                "shift_y_m": eccentric["shift_y_m"],
                "eccentricity_x_m": eccentric["eccentricity_x_m"],
                "eccentricity_y_m": eccentric["eccentricity_y_m"],
            })
        else:
            footing_type = "ISOLATED_CENTERED_PRELIMINARY"
            constructability_status = "OK_PRELIMINARY"
            requires_pr = False

        bbox = footing_bbox(
            cx=footing_cx,
            cy=footing_cy,
            b=side,
            l=side,
        )

        footings.append({
            "id": f"S{column_id.replace('P', '')}",
            "column_id": column_id,
            "type": footing_type,

            "column_cx": round(column_x, 4),
            "column_cy": round(column_y, 4),

            "cx": round(footing_cx, 4),
            "cy": round(footing_cy, 4),
            "footing_cx": round(footing_cx, 4),
            "footing_cy": round(footing_cy, 4),

            "B_m": side,
            "L_m": side,
            "thickness_m": thickness_m,

            "area_required_m2": round(required_area, 4),
            "area_provided_m2": area_provided,
            "q_allowable_kPa": q_allowable_kPa,
            "soil_pressure_ELS_kPa": soil_pressure_els,

            "N_ELS_kN": round(n_els, 3),
            "N_ELU_kN": round(n_elu, 3),

            "bbox": bbox,
            "distance_to_property_m": eccentric["distance_to_property_m"],
            "shift_x_m": eccentric["shift_x_m"],
            "shift_y_m": eccentric["shift_y_m"],
            "eccentricity_x_m": eccentric["eccentricity_x_m"],
            "eccentricity_y_m": eccentric["eccentricity_y_m"],

            "requires_pr_layer": requires_pr,
            "required_layer": "PR" if requires_pr else "SEMELLES",
            "constructability_status": constructability_status,
            "status": "PRELIMINARY",
        })

    interferences = []

    for i in range(len(footings)):
        for j in range(i + 1, len(footings)):
            a = footings[i]
            b = footings[j]

            if rectangles_intersect(a["bbox"], b["bbox"]):
                interferences.append({
                    "footing_a": a["id"],
                    "footing_b": b["id"],
                    "column_a": a["column_id"],
                    "column_b": b["column_id"],
                    "recommended_action": "COMBINED_FOOTING_REQUIRED",
                    "message": f"Les semelles {a['id']} et {b['id']} se chevauchent.",
                })

    if interferences:
        warnings.append({
            "code": "FOOTING_INTERFERENCE_DETECTED",
            "message": "Des semelles se chevauchent. Semelle combinée à prévoir.",
            "count": len(interferences),
        })

    status = "OK"
    if errors:
        status = "ERROR"
    elif warnings:
        status = "WARNING"

    return {
        "status": status,
        "method": "isolated_and_eccentric_footing_preliminary_v0_10",
        "hypotheses": {
            "q_allowable_kPa": q_allowable_kPa,
            "min_side_m": min_side_m,
            "thickness_m": thickness_m,
            "dimension_step_m": dimension_step_m,
            "property_limit_margin_m": property_limit_margin_m,
            "bearing_check": "N_ELS / A <= q_allowable",
            "note": (
                "Prédimensionnement seulement. Les semelles excentrées nécessitent "
                "une poutre de redressement PR calculée."
            ),
        },
        "footings": footings,
        "interferences": interferences,
        "warnings": warnings,
        "errors": errors,
        "summary": {
            "footings_count": len(footings),
            "total_footings_area_m2": round(sum(f["area_provided_m2"] for f in footings), 4),
            "interferences_count": len(interferences),
            "warnings_count": len(warnings),
            "errors_count": len(errors),
        },
    }
