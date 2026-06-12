from __future__ import annotations

import math
from typing import Any


from civil_engine.foundations.footing_predim import predimension_isolated_footings


def round_up(value: float, step: float = 0.05) -> float:
    return round(math.ceil(value / step) * step, 3)


def sort_ids(ids: list[str]) -> list[str]:
    def key(item: str) -> tuple[str, int]:
        prefix = "".join(ch for ch in item if not ch.isdigit())
        digits = "".join(ch for ch in item if ch.isdigit())
        return prefix, int(digits) if digits else 0

    return sorted(ids, key=key)


def bbox_area(bbox: dict[str, float] | None) -> float:
    if bbox is None:
        return 0.0

    return max(0.0, float(bbox["xmax"]) - float(bbox["xmin"])) * max(
        0.0,
        float(bbox["ymax"]) - float(bbox["ymin"]),
    )


def bbox_intersects(a: dict[str, float], b: dict[str, float]) -> bool:
    return not (
        float(a["xmax"]) <= float(b["xmin"])
        or float(a["xmin"]) >= float(b["xmax"])
        or float(a["ymax"]) <= float(b["ymin"])
        or float(a["ymin"]) >= float(b["ymax"])
    )


def bbox_inside_boundary(bbox: dict[str, float], boundary: dict[str, float] | None) -> bool:
    if boundary is None:
        return True

    return (
        float(bbox["xmin"]) >= float(boundary["xmin"]) - 1e-6
        and float(bbox["xmax"]) <= float(boundary["xmax"]) + 1e-6
        and float(bbox["ymin"]) >= float(boundary["ymin"]) - 1e-6
        and float(bbox["ymax"]) <= float(boundary["ymax"]) + 1e-6
    )


def get_foundation_level(model: dict[str, Any]) -> dict[str, Any] | None:
    for level in model.get("levels", []):
        if level.get("name") == "FONDATION":
            return level

    return None


def get_foundation_bbox(model: dict[str, Any]) -> dict[str, float] | None:
    foundation = get_foundation_level(model)

    if foundation is None:
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


def clamp(value: float, vmin: float, vmax: float) -> float:
    return min(max(value, vmin), vmax)


def interval_for_rect_containing_points(
    min_point: float,
    max_point: float,
    length: float,
    bound_min: float,
    bound_max: float,
    preferred_center: float,
) -> tuple[float, float, bool]:
    """
    Retourne [min,max] d'un rectangle de longueur donnée :
    - entièrement dans les bornes ;
    - contenant tous les points ;
    - le plus proche possible du centre préféré.
    """
    available = bound_max - bound_min

    if length > available + 1e-9:
        return bound_min, bound_max, False

    lower_start = max(bound_min, max_point - length)
    upper_start = min(min_point, bound_max - length)

    if lower_start > upper_start + 1e-9:
        return bound_min, bound_min + length, False

    preferred_start = preferred_center - length / 2.0
    start = clamp(preferred_start, lower_start, upper_start)
    end = start + length

    return round(start, 4), round(end, 4), True


def compute_resultant(footings: list[dict[str, Any]]) -> dict[str, float]:
    n_total = sum(float(f["N_ELS_kN"]) for f in footings)

    if n_total <= 0.0:
        return {
            "N_ELS_kN": 0.0,
            "xR": 0.0,
            "yR": 0.0,
        }

    x_r = sum(
        float(f["N_ELS_kN"]) * float(f.get("column_cx", f["cx"]))
        for f in footings
    ) / n_total

    y_r = sum(
        float(f["N_ELS_kN"]) * float(f.get("column_cy", f["cy"]))
        for f in footings
    ) / n_total

    return {
        "N_ELS_kN": round(n_total, 3),
        "xR": round(x_r, 4),
        "yR": round(y_r, 4),
    }


def design_isolated_final(
    footing: dict[str, Any],
    foundation_bbox: dict[str, float] | None,
) -> dict[str, Any]:
    """
    Semelle isolée finale :
    - si elle est intérieure, elle reste centrée ;
    - si elle est en périphérie, elle est recalée dans l'emprise ;
    - elle ne déborde jamais.
    """
    col_x = float(footing.get("column_cx", footing["cx"]))
    col_y = float(footing.get("column_cy", footing["cy"]))

    a = float(footing.get("B_m", footing.get("A_m", 0.80)))
    b = float(footing.get("L_m", footing.get("B_m", 0.80)))
    h = float(footing.get("thickness_m", footing.get("H_m", 0.35)))

    if foundation_bbox is None:
        xmin = col_x - a / 2.0
        xmax = col_x + a / 2.0
        ymin = col_y - b / 2.0
        ymax = col_y + b / 2.0
        can_fit = True
    else:
        xmin_bound = float(foundation_bbox["xmin"])
        xmax_bound = float(foundation_bbox["xmax"])
        ymin_bound = float(foundation_bbox["ymin"])
        ymax_bound = float(foundation_bbox["ymax"])

        xmin, xmax, ok_x = interval_for_rect_containing_points(
            min_point=col_x,
            max_point=col_x,
            length=a,
            bound_min=xmin_bound,
            bound_max=xmax_bound,
            preferred_center=col_x,
        )

        ymin, ymax, ok_y = interval_for_rect_containing_points(
            min_point=col_y,
            max_point=col_y,
            length=b,
            bound_min=ymin_bound,
            bound_max=ymax_bound,
            preferred_center=col_y,
        )

        can_fit = ok_x and ok_y

    bbox = {
        "xmin": round(xmin, 4),
        "xmax": round(xmax, 4),
        "ymin": round(ymin, 4),
        "ymax": round(ymax, 4),
    }

    shifted = (
        abs(float(footing["bbox"]["xmin"]) - bbox["xmin"]) > 1e-6
        or abs(float(footing["bbox"]["ymin"]) - bbox["ymin"]) > 1e-6
    )

    columns_inside = (
        bbox["xmin"] <= col_x <= bbox["xmax"]
        and bbox["ymin"] <= col_y <= bbox["ymax"]
    )

    inside = bbox_inside_boundary(bbox, foundation_bbox)

    status = "OK_PRELIMINARY" if can_fit and columns_inside and inside else "ALTERNATIVE_REQUIRED"

    footing_type = "SE" if shifted or footing.get("requires_pr_layer") else "SI"

    return {
        "id": footing["id"],
        "type": footing_type,
        "source": "ISOLATED_FINAL",
        "columns": [footing["column_id"]],
        "merged_footings": [footing["id"]],
        "cx": round((bbox["xmin"] + bbox["xmax"]) / 2.0, 4),
        "cy": round((bbox["ymin"] + bbox["ymax"]) / 2.0, 4),
        "A_m": round(bbox["xmax"] - bbox["xmin"], 3),
        "B_m": round(bbox["ymax"] - bbox["ymin"], 3),
        "H_m": h,
        "area_provided_m2": round((bbox["xmax"] - bbox["xmin"]) * (bbox["ymax"] - bbox["ymin"]), 4),
        "area_required_m2": footing.get("area_required_m2"),
        "soil_pressure_ELS_kPa": footing.get("soil_pressure_ELS_kPa"),
        "N_ELS_kN": footing.get("N_ELS_kN"),
        "bbox": bbox,
        "inside_emprise": inside,
        "columns_inside": columns_inside,
        "status": status,
        "note": "semelle excentree recalee dans emprise" if footing_type == "SE" else "semelle conservee",
    }


def build_graph_from_candidates(candidates: dict[str, dict[str, Any]]) -> dict[str, set[str]]:
    ids = list(candidates.keys())
    graph: dict[str, set[str]] = {item_id: set() for item_id in ids}

    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a = candidates[ids[i]]
            b = candidates[ids[j]]

            if bbox_intersects(a["bbox"], b["bbox"]):
                graph[ids[i]].add(ids[j])
                graph[ids[j]].add(ids[i])

    return graph


def connected_components(graph: dict[str, set[str]]) -> list[list[str]]:
    visited: set[str] = set()
    components: list[list[str]] = []

    for node in graph:
        if node in visited:
            continue

        stack = [node]
        component: list[str] = []

        while stack:
            current = stack.pop()

            if current in visited:
                continue

            visited.add(current)
            component.append(current)

            for neighbor in graph[current]:
                if neighbor not in visited:
                    stack.append(neighbor)

        components.append(sort_ids(component))

    return components


def design_group_final(
    component_ids: list[str],
    footings_by_id: dict[str, dict[str, Any]],
    q_allowable_kPa: float,
    foundation_bbox: dict[str, float] | None,
    group_type: str,
) -> dict[str, Any]:
    involved = [footings_by_id[item_id] for item_id in component_ids]

    xs = [float(f.get("column_cx", f["cx"])) for f in involved]
    ys = [float(f.get("column_cy", f["cy"])) for f in involved]

    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    resultant = compute_resultant(involved)

    if group_type == "SC":
        prefix = "SC"
        element_type = "SC"
        cover = 0.40
        min_dim = 0.90
        h = 0.40
        area_factor = 1.00
        note = "semelle combinee finale"
    else:
        prefix = "RL"
        element_type = "RL"
        cover = 0.60
        min_dim = 1.20
        h = 0.45
        area_factor = 1.05
        note = "radier local final"

    if foundation_bbox is None:
        bx_min_bound = min_x - 1000.0
        bx_max_bound = max_x + 1000.0
        by_min_bound = min_y - 1000.0
        by_max_bound = max_y + 1000.0
    else:
        bx_min_bound = float(foundation_bbox["xmin"])
        bx_max_bound = float(foundation_bbox["xmax"])
        by_min_bound = float(foundation_bbox["ymin"])
        by_max_bound = float(foundation_bbox["ymax"])

    base_a = max((max_x - min_x) + 2.0 * cover, min_dim)
    base_b = max((max_y - min_y) + 2.0 * cover, min_dim)

    base_a = round_up(base_a)
    base_b = round_up(base_b)

    area_required = resultant["N_ELS_kN"] / q_allowable_kPa * area_factor

    candidates: list[dict[str, Any]] = []

    def try_candidate(a: float, b: float, label: str) -> None:
        a = round_up(a)
        b = round_up(b)

        xmin, xmax, ok_x = interval_for_rect_containing_points(
            min_point=min_x,
            max_point=max_x,
            length=a,
            bound_min=bx_min_bound,
            bound_max=bx_max_bound,
            preferred_center=float(resultant["xR"]),
        )

        ymin, ymax, ok_y = interval_for_rect_containing_points(
            min_point=min_y,
            max_point=max_y,
            length=b,
            bound_min=by_min_bound,
            bound_max=by_max_bound,
            preferred_center=float(resultant["yR"]),
        )

        bbox = {
            "xmin": xmin,
            "xmax": xmax,
            "ymin": ymin,
            "ymax": ymax,
        }

        area = round((xmax - xmin) * (ymax - ymin), 4)

        columns_inside = (
            min_x >= xmin - 1e-6
            and max_x <= xmax + 1e-6
            and min_y >= ymin - 1e-6
            and max_y <= ymax + 1e-6
        )

        inside = bbox_inside_boundary(bbox, foundation_bbox)
        area_ok = area >= area_required - 1e-6

        status = "OK_PRELIMINARY" if ok_x and ok_y and columns_inside and inside and area_ok else "ALTERNATIVE_REQUIRED"

        candidates.append({
            "label": label,
            "A_m": round(xmax - xmin, 3),
            "B_m": round(ymax - ymin, 3),
            "bbox": bbox,
            "area": area,
            "columns_inside": columns_inside,
            "inside": inside,
            "area_ok": area_ok,
            "status": status,
        })

    try_candidate(base_a, base_b, "base")

    if base_a * base_b < area_required:
        try_candidate(area_required / max(base_b, 1e-9), base_b, "increase_A")
        try_candidate(base_a, area_required / max(base_a, 1e-9), "increase_B")
        side = math.sqrt(area_required)
        try_candidate(max(base_a, side), max(base_b, side), "balanced")

    ok_candidates = [candidate for candidate in candidates if candidate["status"] == "OK_PRELIMINARY"]

    if ok_candidates:
        selected = sorted(ok_candidates, key=lambda item: item["area"])[0]
    else:
        selected = sorted(candidates, key=lambda item: item["area"])[0]

    bbox = selected["bbox"]
    area = selected["area"]

    return {
        "id": prefix + "_" + "_".join(component_ids),
        "type": element_type,
        "source": "GROUP_FINAL",
        "columns": [f["column_id"] for f in involved],
        "merged_footings": component_ids,
        "cx": round((bbox["xmin"] + bbox["xmax"]) / 2.0, 4),
        "cy": round((bbox["ymin"] + bbox["ymax"]) / 2.0, 4),
        "A_m": selected["A_m"],
        "B_m": selected["B_m"],
        "H_m": h,
        "area_required_m2": round(area_required, 4),
        "area_provided_m2": area,
        "q_allowable_kPa": q_allowable_kPa,
        "soil_pressure_ELS_kPa": round(resultant["N_ELS_kN"] / area, 3) if area > 0 else None,
        "N_ELS_kN": resultant["N_ELS_kN"],
        "bbox": bbox,
        "inside_emprise": selected["inside"],
        "columns_inside": selected["columns_inside"],
        "area_ok": selected["area_ok"],
        "status": selected["status"],
        "note": note,
    }




def decide_foundation_strategy(
    model: dict[str, Any],
    q_allowable_kPa: float = 200.0,
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
            "message": "Impossible de decider le systeme de fondation.",
            "isolated_report": isolated_report,
            "warnings": isolated_report.get("warnings", []),
            "errors": isolated_report.get("errors", []),
        }

    footings = isolated_report.get("footings", [])
    footings_by_id = {f["id"]: f for f in footings}

    foundation_bbox = get_foundation_bbox(model)
    foundation_area = bbox_area(foundation_bbox)

    isolated_candidates = {
        f["id"]: design_isolated_final(f, foundation_bbox)
        for f in footings
    }

    graph = build_graph_from_candidates(isolated_candidates)
    components = connected_components(graph)

    final_foundations: list[dict[str, Any]] = []
    previous_solution_ids: set[str] = set()

    isolated_final_ids: set[str] = set()
    combined_ids: set[str] = set()
    local_raft_ids: set[str] = set()
    pr_required_ids: set[str] = set()

    pair_groups: list[list[str]] = []
    local_raft_groups: list[list[str]] = []
    isolated_groups: list[list[str]] = []

    for component in components:
        if len(component) == 1:
            fid = component[0]
            element = isolated_candidates[fid]

            final_foundations.append(element)
            isolated_final_ids.add(fid)
            isolated_groups.append(component)

            if element["status"] != "OK_PRELIMINARY":
                pr_required_ids.add(fid)

        elif len(component) == 2:
            pair_groups.append(component)

            element = design_group_final(
                component_ids=component,
                footings_by_id=footings_by_id,
                q_allowable_kPa=q_allowable_kPa,
                foundation_bbox=foundation_bbox,
                group_type="SC",
            )

            final_foundations.append(element)
            previous_solution_ids.update(component)
            combined_ids.update(component)

            if element["status"] != "OK_PRELIMINARY":
                pr_required_ids.update(component)

        else:
            local_raft_groups.append(component)

            element = design_group_final(
                component_ids=component,
                footings_by_id=footings_by_id,
                q_allowable_kPa=q_allowable_kPa,
                foundation_bbox=foundation_bbox,
                group_type="RL",
            )

            final_foundations.append(element)
            previous_solution_ids.update(component)
            local_raft_ids.update(component)

            if element["status"] != "OK_PRELIMINARY":
                pr_required_ids.update(component)

    combined_footings = [f for f in final_foundations if f["type"] == "SC"]
    local_rafts = [f for f in final_foundations if f["type"] == "RL"]

    total_combined_area = sum(float(item["area_provided_m2"]) for item in combined_footings)
    total_raft_area = sum(float(item["area_provided_m2"]) for item in local_rafts)

    combined_area_ratio = total_combined_area / foundation_area if foundation_area > 0 else 0.0
    local_raft_area_ratio = total_raft_area / foundation_area if foundation_area > 0 else 0.0

    conflict_ids = set()
    for component in components:
        if len(component) >= 2:
            conflict_ids.update(component)

    conflict_column_ratio = len(conflict_ids) / len(footings) if footings else 0.0

    general_raft_note = (
        local_raft_area_ratio >= 0.50
        or conflict_column_ratio >= 0.70
    )

    if local_rafts:
        foundation_system = "LOCAL_RAFTS_AND_COMBINED_FOOTINGS"
    elif combined_footings:
        foundation_system = "ISOLATED_AND_COMBINED_FOOTINGS"
    else:
        foundation_system = "ISOLATED_FOOTINGS"

    warnings = list(isolated_report.get("warnings", []))

    if combined_footings:
        warnings.append({
            "code": "COMBINED_FOOTINGS_CREATED",
            "message": "Chaque intersection de deux semelles est traitee par une semelle combinee.",
            "count": len(combined_footings),
        })

    if local_rafts:
        warnings.append({
            "code": "LOCAL_RAFTS_CREATED",
            "message": "Les groupes de trois semelles ou plus sont traites par radier local.",
            "count": len(local_rafts),
        })

    if pr_required_ids:
        warnings.append({
            "code": "PR_OR_REDRESSING_REQUIRED",
            "message": "Certaines zones necessitent PR/redressement ou alternative.",
            "footings": sort_ids(list(pr_required_ids)),
        })

    if general_raft_note:
        warnings.append({
            "code": "GENERAL_RAFT_POSSIBILITY",
            "message": "Possibilite de radier general a laisser ouverte pour etude ulterieure.",
        })

    return {
        "status": "WARNING" if warnings else "OK",
        "method": "foundation_strategy_final_all_elements_v0_21_2_RESTORED_SAFE",
        "foundation_system": foundation_system,
        "hypotheses": {
            "q_allowable_kPa": q_allowable_kPa,
            "rule_1": "Le plan final contient toutes les fondations finales.",
            "rule_2": "Les semelles conservees restent visibles.",
            "rule_3": "Les semelles excentrees sont recalees dans l emprise.",
            "rule_4": "Deux semelles en conflit donnent une semelle combinee.",
            "rule_5": "Trois semelles ou plus en conflit donnent un radier local.",
        },
        "foundation_bbox": foundation_bbox,
        "foundation_area_m2": round(foundation_area, 4),
        "final_foundations": final_foundations,
        "isolated_groups": isolated_groups,
        "pair_groups": pair_groups,
        "local_raft_groups": local_raft_groups,
        "combined_footings": combined_footings,
        "local_rafts": local_rafts,
        "isolated_final_ids": sort_ids(list(isolated_final_ids)),
        "previous_solution_ids": sort_ids(list(previous_solution_ids)),
        "pr_required_ids": sort_ids(list(pr_required_ids)),
        "general_raft_note": general_raft_note,
        "ratios": {
            "combined_area_ratio": round(combined_area_ratio, 4),
            "local_raft_area_ratio": round(local_raft_area_ratio, 4),
            "conflict_column_ratio": round(conflict_column_ratio, 4),
        },
        "warnings": warnings,
        "errors": isolated_report.get("errors", []),
        "summary": {
            "footings_count": len(footings),
            "final_foundations_count": len(final_foundations),
            "isolated_final_count": len(isolated_final_ids),
            "combined_footings_count": len(combined_footings),
            "local_rafts_count": len(local_rafts),
            "general_raft_note": general_raft_note,
            "warnings_count": len(warnings),
            "errors_count": len(isolated_report.get("errors", [])),
        },
        "isolated_report": isolated_report,
    }
