from __future__ import annotations

import math
from typing import Any

from civil_engine.foundations.footing_predim import predimension_isolated_footings


def round_up(value: float, step: float = 0.05) -> float:
    return round(math.ceil(value / step) * step, 3)


def bbox_area(bbox: dict[str, float]) -> float:
    return max(0.0, float(bbox["xmax"]) - float(bbox["xmin"])) * max(
        0.0,
        float(bbox["ymax"]) - float(bbox["ymin"]),
    )


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


def bbox_from_center(cx: float, cy: float, bx: float, ly: float) -> dict[str, float]:
    return {
        "xmin": round(cx - bx / 2.0, 4),
        "xmax": round(cx + bx / 2.0, 4),
        "ymin": round(cy - ly / 2.0, 4),
        "ymax": round(cy + ly / 2.0, 4),
    }


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


def clamp(value: float, min_value: float, max_value: float) -> float:
    return min(max(value, min_value), max_value)


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


def build_interference_graph(footings: list[dict[str, Any]]) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {
        footing["id"]: set()
        for footing in footings
    }

    for i in range(len(footings)):
        for j in range(i + 1, len(footings)):
            a = footings[i]
            b = footings[j]

            if bbox_intersects(a["bbox"], b["bbox"]):
                graph[a["id"]].add(b["id"])
                graph[b["id"]].add(a["id"])

    return graph


def connected_components(graph: dict[str, set[str]]) -> list[list[str]]:
    visited: set[str] = set()
    components: list[list[str]] = []

    for node in graph:
        if node in visited:
            continue

        stack = [node]
        component = []

        while stack:
            current = stack.pop()

            if current in visited:
                continue

            visited.add(current)
            component.append(current)

            for neighbor in graph[current]:
                if neighbor not in visited:
                    stack.append(neighbor)

        components.append(sorted(component))

    return components


def compute_load_resultant(involved: list[dict[str, Any]]) -> dict[str, float]:
    total_n = sum(float(f["N_ELS_kN"]) for f in involved)

    if total_n <= 0:
        return {
            "N_ELS_kN": 0.0,
            "xR": 0.0,
            "yR": 0.0,
        }

    xR = sum(
        float(f["N_ELS_kN"]) * float(f.get("column_cx", f["cx"]))
        for f in involved
    ) / total_n

    yR = sum(
        float(f["N_ELS_kN"]) * float(f.get("column_cy", f["cy"]))
        for f in involved
    ) / total_n

    return {
        "N_ELS_kN": round(total_n, 3),
        "xR": round(xR, 4),
        "yR": round(yR, 4),
    }


def design_local_raft(
    component_ids: list[str],
    footings_by_id: dict[str, dict[str, Any]],
    q_allowable_kPa: float,
    foundation_bbox: dict[str, float] | None,
    edge_margin_m: float = 0.60,
    min_width_m: float = 1.20,
    dimension_step_m: float = 0.05,
) -> dict[str, Any]:
    involved = [
        footings_by_id[item_id]
        for item_id in component_ids
    ]

    xs = [
        float(f.get("column_cx", f["cx"]))
        for f in involved
    ]

    ys = [
        float(f.get("column_cy", f["cy"]))
        for f in involved
    ]

    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    span_x = max_x - min_x
    span_y = max_y - min_y

    resultant = compute_load_resultant(involved)

    required_area = resultant["N_ELS_kN"] / q_allowable_kPa
    required_area = required_area * 1.05  # marge préliminaire 5 %

    bx = max(span_x + 2.0 * edge_margin_m, min_width_m)
    ly = max(span_y + 2.0 * edge_margin_m, min_width_m)

    bx = round_up(bx, dimension_step_m)
    ly = round_up(ly, dimension_step_m)

    area = bx * ly

    if area < required_area:
        # Si groupe plutôt vertical, on évite d'allonger Y et on augmente X.
        if span_y >= span_x:
            bx = round_up(required_area / ly, dimension_step_m)
        else:
            ly = round_up(required_area / bx, dimension_step_m)

    area = round(bx * ly, 4)

    cx = float(resultant["xR"])
    cy = float(resultant["yR"])

    inside_emprise = True
    constructability_status = "OK_PRELIMINARY"

    if foundation_bbox is not None:
        max_bx = float(foundation_bbox["xmax"]) - float(foundation_bbox["xmin"]) - 0.10
        max_ly = float(foundation_bbox["ymax"]) - float(foundation_bbox["ymin"]) - 0.10

        if bx > max_bx or ly > max_ly:
            inside_emprise = False
            constructability_status = "LOCAL_RAFT_TOO_LARGE_FOR_EMPRISE"
        else:
            min_cx = float(foundation_bbox["xmin"]) + bx / 2.0 + 0.05
            max_cx = float(foundation_bbox["xmax"]) - bx / 2.0 - 0.05
            min_cy = float(foundation_bbox["ymin"]) + ly / 2.0 + 0.05
            max_cy = float(foundation_bbox["ymax"]) - ly / 2.0 - 0.05

            cx = clamp(cx, min_cx, max_cx)
            cy = clamp(cy, min_cy, max_cy)

    bbox = bbox_from_center(cx, cy, bx, ly)

    if foundation_bbox is not None:
        inside_emprise = bbox_inside_boundary(bbox, foundation_bbox)

        if not inside_emprise:
            constructability_status = "LOCAL_RAFT_OUTSIDE_EMPRISE"

    soil_pressure = round(resultant["N_ELS_kN"] / area, 3) if area > 0 else None

    return {
        "id": "RL_" + "_".join(component_ids),
        "type": "LOCAL_RAFT_PRELIMINARY",
        "merged_footings": component_ids,
        "columns": [f["column_id"] for f in involved],
        "cx": round(cx, 4),
        "cy": round(cy, 4),
        "Bx_m": round(bx, 3),
        "Ly_m": round(ly, 3),
        "area_required_m2": round(required_area, 4),
        "area_provided_m2": area,
        "q_allowable_kPa": q_allowable_kPa,
        "soil_pressure_ELS_kPa": soil_pressure,
        "N_ELS_kN": resultant["N_ELS_kN"],
        "bbox": bbox,
        "inside_emprise": inside_emprise,
        "constructability_status": constructability_status,
        "recommended_layer": "RADIER_LOCAL",
        "required_checks": [
            "soil_pressure_ELS",
            "punching_each_column",
            "flexure_x",
            "flexure_y",
            "shear",
            "settlement",
            "uplift_if_water",
            "constructability",
        ],
        "status": "PRELIMINARY",
    }


def rafts_intersect_or_close(
    raft_a: dict[str, Any],
    raft_b: dict[str, Any],
    distance_limit_m: float = 0.50,
) -> bool:
    a = raft_a["bbox"]
    b = raft_b["bbox"]

    if bbox_intersects(a, b):
        return True

    dx = max(float(b["xmin"]) - float(a["xmax"]), float(a["xmin"]) - float(b["xmax"]), 0.0)
    dy = max(float(b["ymin"]) - float(a["ymax"]), float(a["ymin"]) - float(b["ymax"]), 0.0)

    distance = (dx * dx + dy * dy) ** 0.5

    return distance <= distance_limit_m


def decide_foundation_strategy(
    model: dict[str, Any],
    q_allowable_kPa: float = 200.0,
    local_raft_min_group_size: int = 3,
    general_raft_area_ratio_limit: float = 0.55,
    general_raft_conflict_column_ratio_limit: float = 0.60,
) -> dict[str, Any]:
    isolated_report = predimension_isolated_footings(
        model=model,
        q_allowable_kPa=q_allowable_kPa,
        min_side_m=0.80,
        thickness_m=0.35,
        dimension_step_m=0.05,
        property_limit_margin_m=0.05,
    )

    if isolated_report.get("status") == "ERROR":
        return {
            "status": "ERROR",
            "message": "Impossible de décider le système de fondation.",
            "isolated_report": isolated_report,
            "warnings": isolated_report.get("warnings", []),
            "errors": isolated_report.get("errors", []),
        }

    footings = isolated_report.get("footings", [])

    footings_by_id = {
        footing["id"]: footing
        for footing in footings
    }

    foundation_bbox = get_foundation_bbox(model)
    foundation_area = bbox_area(foundation_bbox) if foundation_bbox else 0.0

    graph = build_interference_graph(footings)
    components = connected_components(graph)

    conflict_components = [
        component
        for component in components
        if len(component) >= 2
    ]

    pair_groups = []
    local_raft_groups = []
    isolated_groups = []

    for component in components:
        if len(component) == 1:
            isolated_groups.append(component)

        elif len(component) == 2:
            pair_groups.append(component)

        elif len(component) >= local_raft_min_group_size:
            local_raft_groups.append(component)

    local_rafts = []

    for component in local_raft_groups:
        raft = design_local_raft(
            component_ids=component,
            footings_by_id=footings_by_id,
            q_allowable_kPa=q_allowable_kPa,
            foundation_bbox=foundation_bbox,
        )

        local_rafts.append(raft)

    raft_groups_close = False

    for i in range(len(local_rafts)):
        for j in range(i + 1, len(local_rafts)):
            if rafts_intersect_or_close(local_rafts[i], local_rafts[j]):
                raft_groups_close = True

    conflict_footing_ids: set[str] = set()

    for component in conflict_components:
        conflict_footing_ids.update(component)

    conflict_column_ids = {
        footings_by_id[item_id]["column_id"]
        for item_id in conflict_footing_ids
        if item_id in footings_by_id
    }

    total_columns_count = len(footings)
    conflict_column_ratio = (
        len(conflict_column_ids) / total_columns_count
        if total_columns_count
        else 0.0
    )

    total_isolated_area = sum(
        float(f["area_provided_m2"])
        for f in footings
    )

    total_local_raft_area = sum(
        float(r["area_provided_m2"])
        for r in local_rafts
    )

    isolated_area_ratio = (
        total_isolated_area / foundation_area
        if foundation_area > 0
        else 0.0
    )

    local_raft_area_ratio = (
        total_local_raft_area / foundation_area
        if foundation_area > 0
        else 0.0
    )

    global_area_ratio = max(isolated_area_ratio, local_raft_area_ratio)

    general_raft_recommended = False
    general_raft_reasons = []

    if global_area_ratio >= general_raft_area_ratio_limit:
        general_raft_recommended = True
        general_raft_reasons.append(
            "La surface des fondations couvre une grande partie de l'emprise."
        )

    if conflict_column_ratio >= general_raft_conflict_column_ratio_limit:
        general_raft_recommended = True
        general_raft_reasons.append(
            "Une proportion importante des poteaux appartient à des groupes en conflit."
        )

    if raft_groups_close:
        general_raft_recommended = True
        general_raft_reasons.append(
            "Des radiers locaux sont proches ou se recoupent."
        )

    foundation_system = "MIXED_FOUNDATION_SYSTEM_PRELIMINARY"

    if general_raft_recommended:
        foundation_system = "GENERAL_RAFT_RECOMMENDED"
    elif local_rafts:
        foundation_system = "LOCAL_RAFTS_WITH_ISOLATED_AND_COMBINED_FOOTINGS"
    elif pair_groups:
        foundation_system = "ISOLATED_AND_COMBINED_FOOTINGS"
    else:
        foundation_system = "ISOLATED_FOOTINGS"

    recommendations = []

    for component in isolated_groups:
        footing = footings_by_id[component[0]]

        recommendations.append({
            "group_id": "G_" + "_".join(component),
            "foundation_system": "ISOLATED_OR_ECCENTRIC_FOOTING",
            "footings": component,
            "columns": [footing["column_id"]],
            "recommended_layer": "SEMELLES_EXCENTREES" if footing.get("requires_pr_layer") else "SEMELLES",
            "reason": "Semelle indépendante sans interférence détectée.",
        })

    for component in pair_groups:
        columns = [
            footings_by_id[item_id]["column_id"]
            for item_id in component
        ]

        recommendations.append({
            "group_id": "G_" + "_".join(component),
            "foundation_system": "COMBINED_FOOTING_OR_PR",
            "footings": component,
            "columns": columns,
            "recommended_layer": "SEMELLES_COMBINEES",
            "alternative_layer": "PR",
            "reason": (
                "Deux semelles interfèrent localement. "
                "Étudier semelle combinée compacte ou poutre de redressement PR."
            ),
            "required_checks": [
                "soil_pressure",
                "eccentricity_resultant",
                "punching_each_column",
                "flexure",
                "constructability",
            ],
        })

    for raft in local_rafts:
        recommendations.append({
            "group_id": raft["id"],
            "foundation_system": "LOCAL_RAFT_REQUIRED",
            "footings": raft["merged_footings"],
            "columns": raft["columns"],
            "recommended_layer": "RADIER_LOCAL",
            "reason": (
                "Plusieurs semelles interfèrent dans une même zone. "
                "Une semelle combinée unique risquerait d'être non constructible."
            ),
            "local_raft": raft,
            "required_checks": raft["required_checks"],
        })

    if general_raft_recommended:
        recommendations.append({
            "group_id": "GENERAL",
            "foundation_system": "GENERAL_RAFT_RECOMMENDED",
            "recommended_layer": "RADIER_GENERAL",
            "reason": general_raft_reasons,
            "required_checks": [
                "global_soil_pressure",
                "settlement",
                "punching_all_columns",
                "raft_flexure_x_y",
                "uplift_if_water",
                "seismic_tie_and_rigidity",
                "constructability",
            ],
        })

    warnings = list(isolated_report.get("warnings", []))

    if local_rafts:
        warnings.append({
            "code": "LOCAL_RAFTS_RECOMMENDED",
            "message": "Des radiers locaux sont recommandés pour éviter des semelles combinées non constructibles.",
            "count": len(local_rafts),
        })

    if general_raft_recommended:
        warnings.append({
            "code": "GENERAL_RAFT_RECOMMENDED",
            "message": "Un radier général doit être étudié.",
            "reasons": general_raft_reasons,
        })

    status = "OK"

    if isolated_report.get("errors"):
        status = "ERROR"
    elif warnings:
        status = "WARNING"

    return {
        "status": status,
        "method": "foundation_strategy_decision_engine_v0_16",
        "foundation_system": foundation_system,
        "hypotheses": {
            "q_allowable_kPa": q_allowable_kPa,
            "local_raft_min_group_size": local_raft_min_group_size,
            "general_raft_area_ratio_limit": general_raft_area_ratio_limit,
            "general_raft_conflict_column_ratio_limit": general_raft_conflict_column_ratio_limit,
            "note": (
                "Moteur de décision préliminaire. Les radiers locaux/généraux doivent être "
                "vérifiés en poinçonnement, flexion, tassement et pression de sol."
            ),
        },
        "foundation_bbox": foundation_bbox,
        "foundation_area_m2": round(foundation_area, 4),
        "interference_components": conflict_components,
        "pair_groups": pair_groups,
        "local_raft_groups": local_raft_groups,
        "local_rafts": local_rafts,
        "recommendations": recommendations,
        "ratios": {
            "isolated_area_ratio": round(isolated_area_ratio, 4),
            "local_raft_area_ratio": round(local_raft_area_ratio, 4),
            "conflict_column_ratio": round(conflict_column_ratio, 4),
        },
        "warnings": warnings,
        "errors": isolated_report.get("errors", []),
        "summary": {
            "columns_count": total_columns_count,
            "interference_components_count": len(conflict_components),
            "pair_groups_count": len(pair_groups),
            "local_raft_groups_count": len(local_raft_groups),
            "local_rafts_count": len(local_rafts),
            "general_raft_recommended": general_raft_recommended,
            "warnings_count": len(warnings),
            "errors_count": len(isolated_report.get("errors", [])),
        },
        "isolated_report": isolated_report,
    }
