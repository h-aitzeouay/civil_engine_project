from __future__ import annotations

from pathlib import Path
from typing import Any

import ezdxf


def ensure_layers(doc) -> None:
    layers = {
        "FONDATION_EMPRISE": 7,
        "POTEAUX": 7,
        "SEMELLES": 3,
        "SEMELLES_EXCENTREES": 30,
        "SEMELLES_COMBINEES_OPT": 5,
        "MASSIF": 2,
        "PR": 30,
        "LIMITE_PROPRIETE": 1,
        "TEXTES": 7,
        "TABLEAU_SEMELLES": 7,
        "ALERTES": 1,
        "EXCENTRICITE": 6,
        "CENTRE_CHARGE": 4,
        "SOLUTIONS_PRECEDENTES": 8,
        "CENTRE_ANCIEN": 1,
        "EMPRISE_CORRECTION": 2,
    }

    for name, color in layers.items():
        if name not in doc.layers:
            doc.layers.add(name=name, color=color)


def add_text(msp, text: str, x: float, y: float, height: float = 0.20, layer: str = "TEXTES") -> None:
    msp.add_text(
        text,
        dxfattribs={"height": height, "layer": layer},
    ).set_placement((x, y))


def add_rect(msp, xmin: float, ymin: float, xmax: float, ymax: float, layer: str) -> None:
    msp.add_lwpolyline(
        [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)],
        close=True,
        dxfattribs={"layer": layer},
    )


def add_cross(msp, x: float, y: float, size: float, layer: str) -> None:
    msp.add_line((x - size, y), (x + size, y), dxfattribs={"layer": layer})
    msp.add_line((x, y - size), (x, y + size), dxfattribs={"layer": layer})


def add_polyline(msp, points: list[list[float]], layer: str, closed: bool = False) -> None:
    if len(points) < 2:
        return

    msp.add_lwpolyline(
        [(float(p[0]), float(p[1])) for p in points],
        close=closed,
        dxfattribs={"layer": layer},
    )


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
        "xmin": min(xs),
        "xmax": max(xs),
        "ymin": min(ys),
        "ymax": max(ys),
    }


def bbox_from_center(cx: float, cy: float, bx: float, ly: float) -> dict[str, float]:
    return {
        "xmin": round(cx - bx / 2.0, 4),
        "xmax": round(cx + bx / 2.0, 4),
        "ymin": round(cy - ly / 2.0, 4),
        "ymax": round(cy + ly / 2.0, 4),
    }


def clamp_combined_bbox_to_emprise(
    combined: dict[str, Any],
    foundation_bbox: dict[str, float] | None,
) -> dict[str, Any]:
    """
    Sécurité graphique et constructibilité :
    empêche le rectangle de semelle combinée de sortir de l'emprise.

    Si la semelle est plus grande que l'emprise disponible,
    on garde la taille mais on signale NON_CONSTRUCTIBLE.
    """
    bx = float(combined["Bx_m"])
    ly = float(combined["Ly_m"])

    cx = float(combined["cx"])
    cy = float(combined["cy"])

    original_bbox = bbox_from_center(cx, cy, bx, ly)

    if foundation_bbox is None:
        return {
            "cx": cx,
            "cy": cy,
            "bbox": original_bbox,
            "status": "NO_EMPRISE_FOUND",
            "move_x_m": 0.0,
            "move_y_m": 0.0,
        }

    half_bx = bx / 2.0
    half_ly = ly / 2.0

    min_cx = float(foundation_bbox["xmin"]) + half_bx
    max_cx = float(foundation_bbox["xmax"]) - half_bx
    min_cy = float(foundation_bbox["ymin"]) + half_ly
    max_cy = float(foundation_bbox["ymax"]) - half_ly

    if min_cx > max_cx or min_cy > max_cy:
        return {
            "cx": cx,
            "cy": cy,
            "bbox": original_bbox,
            "status": "NON_CONSTRUCTIBLE_FOOTING_LARGER_THAN_EMPRISE",
            "move_x_m": 0.0,
            "move_y_m": 0.0,
        }

    corrected_cx = min(max(cx, min_cx), max_cx)
    corrected_cy = min(max(cy, min_cy), max_cy)

    corrected_bbox = bbox_from_center(corrected_cx, corrected_cy, bx, ly)

    moved = abs(corrected_cx - cx) > 1e-6 or abs(corrected_cy - cy) > 1e-6

    return {
        "cx": round(corrected_cx, 4),
        "cy": round(corrected_cy, 4),
        "bbox": corrected_bbox,
        "status": "MOVED_INSIDE_EMPRISE" if moved else "OK_INSIDE_EMPRISE",
        "move_x_m": round(corrected_cx - cx, 4),
        "move_y_m": round(corrected_cy - cy, 4),
    }


def draw_base(msp, model: dict[str, Any]) -> None:
    foundation_level = get_foundation_level(model)

    if foundation_level:
        for footprint in foundation_level.get("footprints", []):
            add_polyline(
                msp,
                points=footprint.get("points", []),
                layer="FONDATION_EMPRISE",
                closed=True,
            )

        for column in foundation_level.get("columns", []):
            points = column.get("points")

            if points:
                add_polyline(msp, points, "POTEAUX", True)
            else:
                cx = float(column["cx"])
                cy = float(column["cy"])
                add_rect(msp, cx - 0.125, cy - 0.125, cx + 0.125, cy + 0.125, "POTEAUX")

            add_text(
                msp,
                column["id"],
                float(column["cx"]) + 0.10,
                float(column["cy"]) + 0.10,
                0.16,
                "TEXTES",
            )

    for item in model.get("global_layers", {}).get("limite_propriete", []):
        add_polyline(
            msp,
            points=item.get("points", []),
            layer="LIMITE_PROPRIETE",
            closed=bool(item.get("closed", False)),
        )


def draw_isolated_footings(msp, isolated_footings: list[dict[str, Any]]) -> None:
    for footing in isolated_footings:
        if footing.get("merged"):
            continue

        bbox = footing["bbox"]
        layer = "SEMELLES_EXCENTREES" if footing.get("requires_pr_layer") else "SEMELLES"

        add_rect(
            msp,
            float(bbox["xmin"]),
            float(bbox["ymin"]),
            float(bbox["xmax"]),
            float(bbox["ymax"]),
            layer,
        )

        footing_cx = float(footing.get("footing_cx", footing["cx"]))
        footing_cy = float(footing.get("footing_cy", footing["cy"]))

        add_text(
            msp,
            f"{footing['id']} {footing['B_m']}x{footing['L_m']}",
            footing_cx + 0.15,
            footing_cy - 0.25,
            0.16,
            "TEXTES",
        )


def draw_optimized_combined_footings(
    msp,
    optimized_combined_footings: list[dict[str, Any]],
    isolated_footings: list[dict[str, Any]],
    foundation_bbox: dict[str, float] | None,
) -> None:
    isolated_by_column = {
        footing["column_id"]: footing
        for footing in isolated_footings
    }

    for combined in optimized_combined_footings:
        if combined.get("status") == "ALTERNATIVE_REQUIRED":
            # Ne jamais dessiner une semelle combinée rejetée comme solution valide.
            cols = combined.get("columns", [])
            xs = []
            ys = []

            for column_id in cols:
                footing = isolated_by_column.get(column_id)
                if footing:
                    xs.append(float(footing.get("column_cx", footing["cx"])))
                    ys.append(float(footing.get("column_cy", footing["cy"])))

            if xs and ys:
                alert_x = sum(xs) / len(xs)
                alert_y = sum(ys) / len(ys)

                add_cross(
                    msp,
                    x=alert_x,
                    y=alert_y,
                    size=0.45,
                    layer="ALERTES",
                )

                add_text(
                    msp,
                    text="ALTERNATIVE REQUIRED : PR / radier local / semelle filante",
                    x=alert_x + 0.30,
                    y=alert_y + 0.30,
                    height=0.15,
                    layer="ALERTES",
                )

            continue

        correction = clamp_combined_bbox_to_emprise(
            combined=combined,
            foundation_bbox=foundation_bbox,
        )

        bbox = correction["bbox"]

        add_rect(
            msp,
            float(bbox["xmin"]),
            float(bbox["ymin"]),
            float(bbox["xmax"]),
            float(bbox["ymax"]),
            "SEMELLES_COMBINEES_OPT",
        )

        cx = float(correction["cx"])
        cy = float(correction["cy"])

        add_text(
            msp,
            f"{combined['id']} OPT {combined['Bx_m']}x{combined['Ly_m']}",
            cx + 0.20,
            cy + 0.25,
            0.18,
            "TEXTES",
        )

        if correction["status"] == "MOVED_INSIDE_EMPRISE":
            add_text(
                msp,
                f"CORRIGEE EMPRISE dx={correction['move_x_m']} dy={correction['move_y_m']}",
                cx + 0.20,
                cy - 0.15,
                0.15,
                "EMPRISE_CORRECTION",
            )

        if correction["status"] == "NON_CONSTRUCTIBLE_FOOTING_LARGER_THAN_EMPRISE":
            add_text(
                msp,
                "NON CONSTRUCTIBLE : semelle plus grande que l'emprise",
                cx + 0.20,
                cy - 0.15,
                0.15,
                "ALERTES",
            )

        optimization = combined.get("optimization", {})
        old_center = optimization.get("old_center", {})
        desired = optimization.get("desired_center_on_load_resultant", optimization.get("new_center", {}))

        old_x = old_center.get("x")
        old_y = old_center.get("y")
        desired_x = desired.get("x")
        desired_y = desired.get("y")

        if old_x is not None and old_y is not None:
            add_cross(msp, float(old_x), float(old_y), 0.25, "CENTRE_ANCIEN")
            add_text(msp, "Ancien centre", float(old_x) + 0.20, float(old_y) + 0.20, 0.13, "CENTRE_ANCIEN")

        if desired_x is not None and desired_y is not None:
            add_cross(msp, float(desired_x), float(desired_y), 0.30, "CENTRE_CHARGE")
            add_text(
                msp,
                "Centre charge demande",
                float(desired_x) + 0.20,
                float(desired_y) + 0.20,
                0.13,
                "CENTRE_CHARGE",
            )

        add_cross(msp, cx, cy, 0.35, "EMPRISE_CORRECTION")
        add_text(msp, "Centre final dans emprise", cx + 0.20, cy + 0.45, 0.13, "EMPRISE_CORRECTION")

        # Massifs autour des poteaux
        for column_id in combined.get("columns", []):
            footing = isolated_by_column.get(column_id)

            if not footing:
                continue

            column_x = float(footing.get("column_cx", footing["cx"]))
            column_y = float(footing.get("column_cy", footing["cy"]))

            massif_size = 0.70

            add_rect(
                msp,
                column_x - massif_size / 2.0,
                column_y - massif_size / 2.0,
                column_x + massif_size / 2.0,
                column_y + massif_size / 2.0,
                "MASSIF",
            )

            add_text(
                msp,
                f"MASSIF {column_id}",
                column_x + 0.10,
                column_y - 0.45,
                0.14,
                "MASSIF",
            )


def draw_table(msp, report: dict[str, Any]) -> None:
    table_x = 16.0
    table_y = 11.0

    add_text(msp, "TABLEAU FONDATIONS OPTIMISEES", table_x, table_y, 0.24, "TABLEAU_SEMELLES")

    y = table_y - 0.45

    add_text(msp, "SEMELLES COMBINEES RECENTREES", table_x, y, 0.17, "TABLEAU_SEMELLES")

    y -= 0.35

    for combined in report.get("optimized_combined_footings", []):
        opt = combined.get("optimization", {})
        after = combined.get("eccentricity_check_after", {})

        line = (
            f"{combined['id']} | {combined['Bx_m']}x{combined['Ly_m']} | "
            f"dx={opt.get('move_x_m', 0)} dy={opt.get('move_y_m', 0)} | "
            f"qmax={after.get('qmax_kPa', 'NA')} kPa"
        )

        add_text(msp, line, table_x, y, 0.13, "SEMELLES_COMBINEES_OPT")
        y -= 0.30

    y -= 0.20

    add_text(msp, "SEMELLES ISOLEES RESTANTES", table_x, y, 0.17, "TABLEAU_SEMELLES")

    y -= 0.35

    for footing in report.get("isolated_footings", []):
        if footing.get("merged"):
            continue

        line = (
            f"{footing['id']} | {footing['column_id']} | "
            f"{footing['B_m']}x{footing['L_m']} | "
            f"{footing['constructability_status']}"
        )

        layer = "ALERTES" if footing.get("requires_pr_layer") else "TABLEAU_SEMELLES"
        add_text(msp, line, table_x, y, 0.13, layer)
        y -= 0.30

    summary = report.get("summary", {})

    y -= 0.30

    add_text(
        msp,
        f"Semelles combinees optimisees : {summary.get('combined_footings_optimized', 0)}",
        table_x,
        y,
        0.16,
        "TABLEAU_SEMELLES",
    )

    y -= 0.30

    add_text(
        msp,
        f"Warnings : {summary.get('warnings_count', 0)}",
        table_x,
        y,
        0.16,
        "ALERTES" if summary.get("warnings_count", 0) else "TABLEAU_SEMELLES",
    )


def generate_optimized_combined_foundation_dxf(
    model: dict[str, Any],
    optimization_report: dict[str, Any],
    output_path: str | Path,
) -> str:
    output_path = Path(output_path)

    doc = ezdxf.new("R2010")
    doc.units = 6
    ensure_layers(doc)

    msp = doc.modelspace()

    foundation_bbox = get_foundation_bbox(model)

    add_text(
        msp,
        "PLAN DE FONDATIONS - SEMELLES COMBINEES OPTIMISEES",
        0,
        13.0,
        0.35,
        "TEXTES",
    )

    add_text(
        msp,
        "INGENIERIE.COM - Recentrage contraint par emprise",
        0,
        12.55,
        0.22,
        "TEXTES",
    )

    add_text(
        msp,
        "NOTE : aucune semelle combinee ne doit sortir de l'emprise. Verifications BA a faire.",
        0,
        12.20,
        0.18,
        "ALERTES",
    )

    draw_base(msp, model)
    draw_previous_solutions(msp, strategy_report)

    draw_isolated_footings(
        msp,
        isolated_footings=optimization_report.get("isolated_footings", []),
    )

    draw_optimized_combined_footings(
        msp,
        optimized_combined_footings=optimization_report.get("optimized_combined_footings", []),
        isolated_footings=optimization_report.get("isolated_footings", []),
        foundation_bbox=foundation_bbox,
    )

    draw_table(msp, optimization_report)

    from civil_engine.plans.dxf_finalize import finalize_and_save
    finalize_and_save(doc, output_path)
    return str(output_path)



