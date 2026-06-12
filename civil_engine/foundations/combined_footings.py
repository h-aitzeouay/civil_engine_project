from __future__ import annotations

import math
from typing import Any

from civil_engine.foundations.footing_predim import predimension_isolated_footings


def round_up(value: float, step: float = 0.05) -> float:
    return round(math.ceil(value / step) * step, 3)


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


def build_interference_graph(footings: list[dict[str, Any]]) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {
        footing["id"]: set()
        for footing in footings
    }

    for i in range(len(footings)):
        for j in range(i + 1, len(footings)):
            footing_a = footings[i]
            footing_b = footings[j]

            if rectangles_intersect(footing_a["bbox"], footing_b["bbox"]):
                graph[footing_a["id"]].add(footing_b["id"])
                graph[footing_b["id"]].add(footing_a["id"])

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

        components.append(component)

    return components


def design_combined_footing(
    component_ids: list[str],
    footings_by_id: dict[str, dict[str, Any]],
    q_allowable_kPa: float,
    dimension_step_m: float = 0.05,
    edge_margin_m: float = 0.40,
) -> dict[str, Any]:
    """
    Prédimensionnement simple d'une semelle combinée.

    Convention :
    - Bx_m = dimension dans X ;
    - Ly_m = dimension dans Y.

    La géométrie couvre les poteaux du groupe + marge constructive.
    Si l'aire est insuffisante vis-à-vis de N_ELS / q_sol,
    les dimensions sont majorées.
    """
    involved = [
        footings_by_id[item_id]
        for item_id in component_ids
    ]

    column_xs = [
        float(footing.get("column_cx", footing["cx"]))
        for footing in involved
    ]

    column_ys = [
        float(footing.get("column_cy", footing["cy"]))
        for footing in involved
    ]

    min_x = min(column_xs)
    max_x = max(column_xs)
    min_y = min(column_ys)
    max_y = max(column_ys)

    span_x = max_x - min_x
    span_y = max_y - min_y

    total_n_els = round(
        sum(float(footing["N_ELS_kN"]) for footing in involved),
        3,
    )

    total_n_elu = round(
        sum(float(footing["N_ELU_kN"]) for footing in involved),
        3,
    )

    required_area = total_n_els / q_allowable_kPa

    bx = max(span_x + 2.0 * edge_margin_m, 0.80)
    ly = max(span_y + 2.0 * edge_margin_m, 0.80)

    # Si les poteaux sont alignés suivant X, on impose une largeur minimale en Y.
    if span_x >= span_y:
        ly = max(ly, 1.00)
    else:
        bx = max(bx, 1.00)

    bx = round_up(bx, dimension_step_m)
    ly = round_up(ly, dimension_step_m)

    provided_area = bx * ly

    if provided_area < required_area:
        scale = math.sqrt(required_area / provided_area)
        bx = round_up(bx * scale, dimension_step_m)
        ly = round_up(ly * scale, dimension_step_m)

    provided_area = round(bx * ly, 4)
    soil_pressure = round(total_n_els / provided_area, 3)

    cx = round((min_x + max_x) / 2.0, 4)
    cy = round((min_y + max_y) / 2.0, 4)

    bbox = {
        "xmin": round(cx - bx / 2.0, 4),
        "xmax": round(cx + bx / 2.0, 4),
        "ymin": round(cy - ly / 2.0, 4),
        "ymax": round(cy + ly / 2.0, 4),
    }

    return {
        "id": "SC_" + "_".join(component_ids),
        "type": "COMBINED_FOOTING_PRELIMINARY",
        "merged_footings": component_ids,
        "columns": [footing["column_id"] for footing in involved],
        "cx": cx,
        "cy": cy,
        "Bx_m": bx,
        "Ly_m": ly,
        "area_required_m2": round(required_area, 4),
        "area_provided_m2": provided_area,
        "q_allowable_kPa": q_allowable_kPa,
        "soil_pressure_ELS_kPa": soil_pressure,
        "N_ELS_kN": total_n_els,
        "N_ELU_kN": total_n_elu,
        "bbox": bbox,
        "status": "PRELIMINARY",
        "required_checks": [
            "soil_pressure_ELS",
            "eccentricity_resultant",
            "punching_each_column",
            "flexure_bottom_reinforcement",
            "top_reinforcement_over_columns",
            "shear",
            "constructability",
        ],
        "required_layers": [
            "SEMELLES_COMBINEES",
            "ARM_INF",
            "ARM_SUP",
            "MASSIF",
        ],
    }


def generate_combined_footings(
    model: dict[str, Any],
    q_allowable_kPa: float = 200.0,
) -> dict[str, Any]:
    """
    Génère des semelles combinées si les semelles isolées se chevauchent.

    Remarque :
    - avec q_sol = 200 kPa sur ton exemple, il est possible qu'il n'y ait aucune interférence ;
    - pour tester, utilise q_allowable_kPa = 50 ou 75 kPa.
    """
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
            "message": "Impossible de générer les semelles combinées.",
            "isolated_report": isolated_report,
            "combined_footings": [],
            "warnings": isolated_report.get("warnings", []),
            "errors": isolated_report.get("errors", []),
        }

    footings = isolated_report.get("footings", [])
    footings_by_id = {
        footing["id"]: footing
        for footing in footings
    }

    graph = build_interference_graph(footings)
    components = connected_components(graph)

    combined_footings = []
    isolated_kept = []
    merged_ids: set[str] = set()

    for component in components:
        if len(component) >= 2:
            combined = design_combined_footing(
                component_ids=component,
                footings_by_id=footings_by_id,
                q_allowable_kPa=q_allowable_kPa,
            )
            combined_footings.append(combined)
            merged_ids.update(component)

    for footing in footings:
        if footing["id"] in merged_ids:
            footing_copy = dict(footing)
            footing_copy["status"] = "MERGED_IN_COMBINED_FOOTING"
            isolated_kept.append(footing_copy)
        else:
            isolated_kept.append(footing)

    warnings = list(isolated_report.get("warnings", []))

    if combined_footings:
        warnings.append({
            "code": "COMBINED_FOOTINGS_CREATED",
            "message": "Des semelles combinées préliminaires ont été générées.",
            "count": len(combined_footings),
        })

    status = "OK"

    if isolated_report.get("errors"):
        status = "ERROR"
    elif warnings:
        status = "WARNING"

    return {
        "status": status,
        "method": "combined_footing_generation_from_interference_v0_11",
        "hypotheses": {
            "q_allowable_kPa": q_allowable_kPa,
            "note": (
                "Prédimensionnement seulement. Les semelles combinées doivent être vérifiées "
                "en pression de sol, poinçonnement, flexion, cisaillement et ferraillage."
            ),
        },
        "isolated_footings": isolated_kept,
        "combined_footings": combined_footings,
        "interference_components": [
            component
            for component in components
            if len(component) >= 2
        ],
        "warnings": warnings,
        "errors": isolated_report.get("errors", []),
        "summary": {
            "isolated_footings_count": len(isolated_kept),
            "combined_footings_count": len(combined_footings),
            "merged_isolated_footings_count": len(merged_ids),
            "warnings_count": len(warnings),
            "errors_count": len(isolated_report.get("errors", [])),
        },
    }
