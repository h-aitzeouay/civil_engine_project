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


def nearest_centered_footing(footing: dict[str, Any], footings: list[dict[str, Any]]) -> dict[str, Any] | None:
    best = None
    best_distance = None

    x1 = float(footing.get("column_cx", footing["cx"]))
    y1 = float(footing.get("column_cy", footing["cy"]))

    for other in footings:
        if other["id"] == footing["id"]:
            continue

        if other.get("requires_pr_layer"):
            continue

        x2 = float(other.get("column_cx", other["cx"]))
        y2 = float(other.get("column_cy", other["cy"]))

        distance = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

        if best_distance is None or distance < best_distance:
            best = other
            best_distance = distance

    return best


def generate_foundation_predim_dxf(
    model: dict[str, Any],
    footing_report: dict[str, Any],
    output_path: str | Path,
) -> str:
    output_path = Path(output_path)

    doc = ezdxf.new("R2010")
    doc.units = 6
    ensure_layers(doc)

    msp = doc.modelspace()
    foundation_level = get_foundation_level(model)

    add_text(msp, "PLAN DE FONDATIONS - PREDIMENSIONNEMENT", 0, 13.0, 0.35, "TEXTES")
    add_text(msp, "INGENIERIE.COM - Version calcul preliminaire", 0, 12.55, 0.22, "TEXTES")
    add_text(msp, "NOTE : Semelles excentrees et PR a verifier par calcul complet.", 0, 12.20, 0.18, "ALERTES")

    if foundation_level:
        for footprint in foundation_level.get("footprints", []):
            add_polyline(msp, footprint.get("points", []), "FONDATION_EMPRISE", True)

        for column in foundation_level.get("columns", []):
            points = column.get("points")

            if points:
                add_polyline(msp, points, "POTEAUX", True)
            else:
                cx = float(column["cx"])
                cy = float(column["cy"])
                add_rect(msp, cx - 0.125, cy - 0.125, cx + 0.125, cy + 0.125, "POTEAUX")

            add_text(msp, column["id"], float(column["cx"]) + 0.10, float(column["cy"]) + 0.10, 0.16, "TEXTES")

    for item in model.get("global_layers", {}).get("limite_propriete", []):
        add_polyline(
            msp,
            points=item.get("points", []),
            layer="LIMITE_PROPRIETE",
            closed=bool(item.get("closed", False)),
        )

    footings = footing_report.get("footings", [])

    for footing in footings:
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

        column_cx = float(footing.get("column_cx", footing_cx))
        column_cy = float(footing.get("column_cy", footing_cy))

        add_text(
            msp,
            f"{footing['id']} {footing['B_m']}x{footing['L_m']}",
            footing_cx + 0.15,
            footing_cy - 0.25,
            0.16,
            "TEXTES",
        )

        if footing.get("requires_pr_layer"):
            # Centre semelle
            msp.add_circle(
                center=(footing_cx, footing_cy),
                radius=0.12,
                dxfattribs={"layer": "EXCENTRICITE"},
            )

            add_text(
                msp,
                "Centre semelle",
                footing_cx + 0.15,
                footing_cy,
                0.12,
                "EXCENTRICITE",
            )

            # Décalage poteau -> centre semelle
            msp.add_line(
                start=(column_cx, column_cy),
                end=(footing_cx, footing_cy),
                dxfattribs={"layer": "EXCENTRICITE"},
            )

            add_text(
                msp,
                "Semelle excentree",
                footing_cx + 0.20,
                footing_cy + 0.25,
                0.16,
                "ALERTES",
            )

            add_text(
                msp,
                "PR A CALCULER",
                column_cx + 0.35,
                column_cy + 0.35,
                0.16,
                "ALERTES",
            )

            other = nearest_centered_footing(footing, footings)

            if other:
                other_x = float(other.get("column_cx", other["cx"]))
                other_y = float(other.get("column_cy", other["cy"]))

                msp.add_line(
                    start=(column_cx, column_cy),
                    end=(other_x, other_y),
                    dxfattribs={"layer": "PR"},
                )

                add_text(
                    msp,
                    "PR conceptuel - a dimensionner",
                    (column_cx + other_x) / 2.0,
                    (column_cy + other_y) / 2.0 + 0.15,
                    0.14,
                    "PR",
                )

    table_x = 16.0
    table_y = 11.0

    add_text(msp, "TABLEAU DES SEMELLES", table_x, table_y, 0.24, "TABLEAU_SEMELLES")
    add_text(msp, "ID | Poteau | BxL | N_ELS | q_sol | Statut", table_x, table_y - 0.40, 0.16, "TABLEAU_SEMELLES")

    y = table_y - 0.75

    for footing in footings:
        line = (
            f"{footing['id']} | {footing['column_id']} | "
            f"{footing['B_m']}x{footing['L_m']} | "
            f"{footing['N_ELS_kN']} kN | "
            f"{footing['soil_pressure_ELS_kPa']} kPa | "
            f"{footing['constructability_status']}"
        )

        layer = "ALERTES" if footing.get("requires_pr_layer") else "TABLEAU_SEMELLES"
        add_text(msp, line, table_x, y, 0.14, layer)
        y -= 0.32

    summary = footing_report.get("summary", {})

    add_text(msp, f"Nombre semelles : {summary.get('footings_count', 0)}", table_x, y - 0.40, 0.16, "TABLEAU_SEMELLES")
    add_text(msp, f"Interferences : {summary.get('interferences_count', 0)}", table_x, y - 0.70, 0.16, "ALERTES" if summary.get("interferences_count", 0) else "TABLEAU_SEMELLES")
    add_text(msp, f"q_sol utilise : {footing_report.get('hypotheses', {}).get('q_allowable_kPa', 'NA')} kPa", table_x, y - 1.00, 0.16, "TABLEAU_SEMELLES")

    doc.saveas(output_path)
    return str(output_path)
