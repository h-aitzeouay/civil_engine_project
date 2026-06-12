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
        "SEMELLES_COMBINEES": 5,
        "MASSIF": 2,
        "PR": 30,
        "LIMITE_PROPRIETE": 1,
        "TEXTES": 7,
        "TABLEAU_SEMELLES": 7,
        "ALERTES": 1,
        "EXCENTRICITE": 6,
    }

    for name, color in layers.items():
        if name not in doc.layers:
            doc.layers.add(name=name, color=color)


def add_text(msp, text: str, x: float, y: float, height: float = 0.20, layer: str = "TEXTES") -> None:
    msp.add_text(
        text,
        dxfattribs={
            "height": height,
            "layer": layer,
        },
    ).set_placement((x, y))


def add_rect(msp, xmin: float, ymin: float, xmax: float, ymax: float, layer: str) -> None:
    msp.add_lwpolyline(
        [
            (xmin, ymin),
            (xmax, ymin),
            (xmax, ymax),
            (xmin, ymax),
        ],
        close=True,
        dxfattribs={"layer": layer},
    )


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


def draw_foundation_base(msp, model: dict[str, Any]) -> None:
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
                add_polyline(
                    msp,
                    points=points,
                    layer="POTEAUX",
                    closed=True,
                )
            else:
                cx = float(column["cx"])
                cy = float(column["cy"])
                add_rect(
                    msp,
                    xmin=cx - 0.125,
                    ymin=cy - 0.125,
                    xmax=cx + 0.125,
                    ymax=cy + 0.125,
                    layer="POTEAUX",
                )

            add_text(
                msp,
                text=column["id"],
                x=float(column["cx"]) + 0.10,
                y=float(column["cy"]) + 0.10,
                height=0.16,
                layer="TEXTES",
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

        if footing.get("requires_pr_layer"):
            layer = "SEMELLES_EXCENTREES"
        else:
            layer = "SEMELLES"

        add_rect(
            msp,
            xmin=float(bbox["xmin"]),
            ymin=float(bbox["ymin"]),
            xmax=float(bbox["xmax"]),
            ymax=float(bbox["ymax"]),
            layer=layer,
        )

        footing_cx = float(footing.get("footing_cx", footing["cx"]))
        footing_cy = float(footing.get("footing_cy", footing["cy"]))

        column_cx = float(footing.get("column_cx", footing_cx))
        column_cy = float(footing.get("column_cy", footing_cy))

        add_text(
            msp,
            text=f"{footing['id']} {footing['B_m']}x{footing['L_m']}",
            x=footing_cx + 0.15,
            y=footing_cy - 0.25,
            height=0.16,
            layer="TEXTES",
        )

        if footing.get("requires_pr_layer"):
            msp.add_line(
                start=(column_cx, column_cy),
                end=(footing_cx, footing_cy),
                dxfattribs={"layer": "EXCENTRICITE"},
            )

            add_text(
                msp,
                text="PR A CALCULER",
                x=column_cx + 0.35,
                y=column_cy + 0.35,
                height=0.16,
                layer="ALERTES",
            )


def draw_combined_footings(
    msp,
    combined_footings: list[dict[str, Any]],
    isolated_footings: list[dict[str, Any]],
) -> None:
    isolated_by_column = {
        footing["column_id"]: footing
        for footing in isolated_footings
    }

    for combined in combined_footings:
        bbox = combined["bbox"]

        add_rect(
            msp,
            xmin=float(bbox["xmin"]),
            ymin=float(bbox["ymin"]),
            xmax=float(bbox["xmax"]),
            ymax=float(bbox["ymax"]),
            layer="SEMELLES_COMBINEES",
        )

        cx = float(combined["cx"])
        cy = float(combined["cy"])

        add_text(
            msp,
            text=f"{combined['id']} {combined['Bx_m']}x{combined['Ly_m']}",
            x=cx + 0.20,
            y=cy + 0.20,
            height=0.18,
            layer="TEXTES",
        )

        add_text(
            msp,
            text="SEMELLE COMBINEE - A VERIFIER",
            x=cx + 0.20,
            y=cy - 0.15,
            height=0.16,
            layer="ALERTES",
        )

        # Massifs locaux autour des poteaux inclus dans la semelle combinée
        for column_id in combined.get("columns", []):
            footing = isolated_by_column.get(column_id)

            if not footing:
                continue

            column_x = float(footing.get("column_cx", footing["cx"]))
            column_y = float(footing.get("column_cy", footing["cy"]))

            massif_size = 0.70

            add_rect(
                msp,
                xmin=column_x - massif_size / 2.0,
                ymin=column_y - massif_size / 2.0,
                xmax=column_x + massif_size / 2.0,
                ymax=column_y + massif_size / 2.0,
                layer="MASSIF",
            )

            add_text(
                msp,
                text=f"MASSIF {column_id}",
                x=column_x + 0.10,
                y=column_y - 0.45,
                height=0.14,
                layer="MASSIF",
            )


def draw_tables(
    msp,
    combined_report: dict[str, Any],
) -> None:
    table_x = 16.0
    table_y = 11.0

    add_text(
        msp,
        "TABLEAU FONDATIONS",
        x=table_x,
        y=table_y,
        height=0.24,
        layer="TABLEAU_SEMELLES",
    )

    add_text(
        msp,
        "SEMELLES ISOLEES NON FUSIONNEES",
        x=table_x,
        y=table_y - 0.40,
        height=0.17,
        layer="TABLEAU_SEMELLES",
    )

    y = table_y - 0.75

    for footing in combined_report.get("isolated_footings", []):
        if footing.get("merged"):
            continue

        line = (
            f"{footing['id']} | {footing['column_id']} | "
            f"{footing['B_m']}x{footing['L_m']} | "
            f"NELS={footing['N_ELS_kN']} kN | "
            f"{footing['constructability_status']}"
        )

        layer = "ALERTES" if footing.get("requires_pr_layer") else "TABLEAU_SEMELLES"

        add_text(
            msp,
            line,
            x=table_x,
            y=y,
            height=0.13,
            layer=layer,
        )

        y -= 0.30

    y -= 0.25

    add_text(
        msp,
        "SEMELLES COMBINEES",
        x=table_x,
        y=y,
        height=0.17,
        layer="TABLEAU_SEMELLES",
    )

    y -= 0.35

    for combined in combined_report.get("combined_footings", []):
        line = (
            f"{combined['id']} | {combined['Bx_m']}x{combined['Ly_m']} | "
            f"NELS={combined['N_ELS_kN']} kN | "
            f"q={combined['soil_pressure_ELS_kPa']} kPa"
        )

        add_text(
            msp,
            line,
            x=table_x,
            y=y,
            height=0.13,
            layer="SEMELLES_COMBINEES",
        )

        y -= 0.30

    summary = combined_report.get("summary", {})

    y -= 0.30

    add_text(
        msp,
        f"Semelles combinees : {summary.get('combined_footings_count', 0)}",
        x=table_x,
        y=y,
        height=0.16,
        layer="TABLEAU_SEMELLES",
    )

    y -= 0.30

    add_text(
        msp,
        f"Semelles isolees fusionnees : {summary.get('merged_isolated_footings_count', 0)}",
        x=table_x,
        y=y,
        height=0.16,
        layer="TABLEAU_SEMELLES",
    )


def generate_combined_foundation_dxf(
    model: dict[str, Any],
    combined_report: dict[str, Any],
    output_path: str | Path,
) -> str:
    output_path = Path(output_path)

    doc = ezdxf.new("R2010")
    doc.units = 6
    ensure_layers(doc)

    msp = doc.modelspace()

    add_text(
        msp,
        "PLAN DE FONDATIONS - SEMELLES COMBINEES",
        x=0,
        y=13.0,
        height=0.35,
        layer="TEXTES",
    )

    add_text(
        msp,
        "INGENIERIE.COM - Predimensionnement automatique",
        x=0,
        y=12.55,
        height=0.22,
        layer="TEXTES",
    )

    add_text(
        msp,
        "NOTE : semelles combinees, massifs, poinconnement et ferraillage a verifier.",
        x=0,
        y=12.20,
        height=0.18,
        layer="ALERTES",
    )

    draw_foundation_base(msp, model)

    draw_isolated_footings(
        msp,
        isolated_footings=combined_report.get("isolated_footings", []),
    )

    draw_combined_footings(
        msp,
        combined_footings=combined_report.get("combined_footings", []),
        isolated_footings=combined_report.get("isolated_footings", []),
    )

    draw_tables(msp, combined_report)

    doc.saveas(output_path)

    return str(output_path)
