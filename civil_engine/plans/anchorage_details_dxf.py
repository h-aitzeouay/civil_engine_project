from __future__ import annotations

from pathlib import Path
from typing import Any

import ezdxf

from civil_engine.foundations.column_effective import get_effective_column_boxes


def ensure_layers(doc) -> None:
    layers = {
        "EMPRISE": 7,
        "POTEAUX": 7,
        "SI": 3,
        "SE": 30,
        "SC": 5,
        "RL": 140,
        "ATTENTES": 1,
        "CADRES": 2,
        "ANCRAGES": 5,
        "RECOUVREMENTS": 6,
        "FORMES": 4,
        "TEXTES": 7,
        "TABLEAU_ANCRAGE": 7,
        "NOTA": 1,
    }

    for name, color in layers.items():
        if name not in doc.layers:
            doc.layers.add(name=name, color=color)


def add_text(msp, text: str, x: float, y: float, height: float = 0.12, layer: str = "TEXTES") -> None:
    msp.add_text(
        text,
        dxfattribs={"height": height, "layer": layer},
    ).set_placement((x, y))


def add_line(msp, x1: float, y1: float, x2: float, y2: float, layer: str) -> None:
    msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": layer})


def add_rect(msp, xmin: float, ymin: float, xmax: float, ymax: float, layer: str) -> None:
    msp.add_lwpolyline(
        [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)],
        close=True,
        dxfattribs={"layer": layer},
    )


def add_circle(msp, x: float, y: float, r: float, layer: str) -> None:
    msp.add_circle((x, y), r, dxfattribs={"layer": layer})


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

    if foundation is None:
        return None

    points = []

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


def layer_for_type(ftype: str) -> str:
    if ftype == "SI":
        return "SI"
    if ftype == "SE":
        return "SE"
    if ftype == "SC":
        return "SC"
    if ftype == "RL":
        return "RL"
    return "SI"


def table_position(model: dict[str, Any]) -> tuple[float, float]:
    bbox = get_foundation_bbox(model)

    if bbox is None:
        return 18.0, 12.0

    return float(bbox["xmax"]) + 5.5, float(bbox["ymax"]) + 2.3


def draw_base(msp, model: dict[str, Any], strategy_report: dict[str, Any]) -> None:
    foundation = get_foundation_level(model)

    if foundation is None:
        return

    for footprint in foundation.get("footprints", []):
        add_polyline(msp, footprint.get("points", []), "EMPRISE", closed=True)

    for element in strategy_report.get("final_foundations", []):
        bbox = element.get("bbox")

        if not bbox:
            continue

        layer = layer_for_type(str(element.get("type", "")))

        add_rect(
            msp,
            float(bbox["xmin"]),
            float(bbox["ymin"]),
            float(bbox["xmax"]),
            float(bbox["ymax"]),
            layer,
        )

        add_text(
            msp,
            str(element.get("id", "")),
            float(bbox["xmax"]) + 0.12,
            float(bbox["ymax"]) + 0.12,
            0.10,
            layer,
        )

    for column_id, box in get_effective_column_boxes(model).items():
        add_rect(
            msp,
            float(box["xmin"]),
            float(box["ymin"]),
            float(box["xmax"]),
            float(box["ymax"]),
            "POTEAUX",
        )

        add_text(
            msp,
            column_id,
            float(box["xmax"]) + 0.10,
            float(box["ymax"]) + 0.10,
            0.10,
            "POTEAUX",
        )


def starter_points(box: dict[str, float], cover_m: float = 0.06) -> list[tuple[float, float]]:
    xmin = float(box["xmin"])
    xmax = float(box["xmax"])
    ymin = float(box["ymin"])
    ymax = float(box["ymax"])

    x1 = xmin + cover_m
    x2 = xmax - cover_m
    y1 = ymin + cover_m
    y2 = ymax - cover_m

    points = [
        (x1, y1),
        (x2, y1),
        (x2, y2),
        (x1, y2),
    ]

    if xmax - xmin >= 0.35:
        points.extend([((x1 + x2) / 2.0, y1), ((x1 + x2) / 2.0, y2)])

    if ymax - ymin >= 0.35:
        points.extend([(x1, (y1 + y2) / 2.0), (x2, (y1 + y2) / 2.0)])

    return points


def draw_plan_anchorage(msp, model: dict[str, Any], anchorage_report: dict[str, Any]) -> None:
    boxes = get_effective_column_boxes(model)

    row_map = {
        row["column_id"]: row
        for row in anchorage_report.get("rows", [])
    }

    for column_id, box in boxes.items():
        row = row_map.get(column_id)

        if row is None:
            continue

        diameter = float(row["starter_bars"]["diameter_mm"])
        r = max(diameter / 1000.0 / 2.0, 0.018)

        for x, y in starter_points(box):
            add_circle(msp, x, y, r, "ATTENTES")

        add_rect(
            msp,
            float(box["xmin"]) + 0.04,
            float(box["ymin"]) + 0.04,
            float(box["xmax"]) - 0.04,
            float(box["ymax"]) - 0.04,
            "CADRES",
        )


def draw_straight_bar_shape(msp, x: float, y: float, lbd_m: float) -> None:
    add_text(msp, "FORME A - ATTENTE DROITE", x, y + 1.00, 0.13, "FORMES")

    add_line(msp, x + 0.40, y, x + 0.40, y + 0.85, "ATTENTES")
    add_line(msp, x + 0.20, y, x + 0.60, y, "ANCRAGES")

    add_text(msp, f"Lbd = {lbd_m:.2f} m", x + 0.75, y + 0.35, 0.10, "TEXTES")
    add_text(msp, "A utiliser si epaisseur suffisante", x + 0.75, y + 0.15, 0.09, "NOTA")


def draw_bent_bar_shape(msp, x: float, y: float, lbd_m: float, hook_m: float) -> None:
    add_text(msp, "FORME B - ATTENTE COUDEE / CROSSE", x, y + 1.00, 0.13, "FORMES")

    add_line(msp, x + 0.40, y + 0.10, x + 0.40, y + 0.85, "ATTENTES")
    add_line(msp, x + 0.40, y + 0.10, x + 0.85, y + 0.10, "ATTENTES")

    add_text(msp, f"Lbd = {lbd_m:.2f} m", x + 1.00, y + 0.45, 0.10, "TEXTES")
    add_text(msp, f"Retour indic. = {hook_m:.2f} m", x + 1.00, y + 0.25, 0.10, "TEXTES")
    add_text(msp, "A verifier selon EC2/BAEL", x + 1.00, y + 0.05, 0.09, "NOTA")


def draw_lap_shape(msp, x: float, y: float, l0_m: float) -> None:
    add_text(msp, "FORME C - RECOUVREMENT", x, y + 1.00, 0.13, "FORMES")

    add_line(msp, x + 0.30, y, x + 0.30, y + 0.85, "ATTENTES")
    add_line(msp, x + 0.48, y + 0.20, x + 0.48, y + 1.05, "RECOUVREMENTS")

    add_text(msp, f"L0 = {l0_m:.2f} m", x + 0.75, y + 0.45, 0.10, "TEXTES")
    add_text(msp, "Recouvrement hors zones critiques", x + 0.75, y + 0.25, 0.09, "NOTA")


def draw_table(msp, anchorage_report: dict[str, Any], x: float, y: float) -> None:
    add_text(msp, "TABLEAU ANCRAGES ET RECOUVREMENTS", x, y, 0.22, "TABLEAU_ANCRAGE")
    y -= 0.45

    headers = [
        ("POT", 0.0),
        ("FOND", 1.2),
        ("ATTENTES", 2.6),
        ("CADRES", 4.2),
        ("DIM CADRE", 5.7),
        ("Lbd", 7.6),
        ("L0", 8.7),
        ("FORME", 9.8),
        ("OBS", 13.0),
    ]

    for title, dx in headers:
        add_text(msp, title, x + dx, y, 0.105, "TABLEAU_ANCRAGE")

    y -= 0.28

    for row in anchorage_report.get("rows", []):
        stirrup = row["stirrups"]
        anchorage = row["anchorage"]

        dim = f"{stirrup['frame_inside_x_m']:.2f}x{stirrup['frame_inside_y_m']:.2f}"

        shape = anchorage["recommended_shape"]

        if shape == "ATTENTE_DROITE":
            shape_short = "A"
        elif shape == "ATTENTE_COUDEE_OU_CROSSE_A_ETUDIER":
            shape_short = "B"
        else:
            shape_short = "A_VERIF"

        values = [
            (row["column_id"], 0.0),
            (row["foundation_id"], 1.2),
            (row["starter_bars"]["label"], 2.6),
            (stirrup["label"], 4.2),
            (dim, 5.7),
            (f"{anchorage['Lbd_m']:.2f}", 7.6),
            (f"{anchorage['lap_L0_m']:.2f}", 8.7),
            (shape_short, 9.8),
            ("A verifier", 13.0),
        ]

        for value, dx in values:
            add_text(msp, str(value), x + dx, y, 0.085, "TABLEAU_ANCRAGE")

        y -= 0.24

    y -= 0.30

    add_text(msp, "NOTA", x, y, 0.15, "NOTA")
    y -= 0.22

    add_text(
        msp,
        "A = attente droite ; B = attente coudee/crosse ; C = recouvrement.",
        x,
        y,
        0.09,
        "NOTA",
    )

    y -= 0.18

    add_text(
        msp,
        "Longueurs indicatives. Verification finale selon EC2/BAEL, effort poteau, adherence, zones sismiques.",
        x,
        y,
        0.09,
        "NOTA",
    )


def draw_shapes(msp, anchorage_report: dict[str, Any], x: float, y: float) -> None:
    rows = anchorage_report.get("rows", [])

    if not rows:
        return

    first = rows[0]["anchorage"]

    lbd = float(first["Lbd_m"])
    l0 = float(first["lap_L0_m"])
    hook = float(first["hook_leg_m"])

    add_text(msp, "DETAILS TYPES DES FORMES", x, y, 0.18, "FORMES")

    draw_straight_bar_shape(msp, x, y - 1.35, lbd)
    draw_bent_bar_shape(msp, x + 4.0, y - 1.35, lbd, hook)
    draw_lap_shape(msp, x + 8.4, y - 1.35, l0)


def generate_anchorage_details_dxf(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    anchorage_report: dict[str, Any],
    output_path: str | Path,
) -> str:
    output_path = Path(output_path)

    doc = ezdxf.new("R2010")
    doc.units = 6
    ensure_layers(doc)

    msp = doc.modelspace()

    bbox = get_foundation_bbox(model)

    title_y = 13.0
    if bbox is not None:
        title_y = float(bbox["ymax"]) + 2.4

    add_text(msp, "DETAILS D'ANCRAGE ET RECOUVREMENT - CONFIGURATION FINALE", 0.0, title_y, 0.30, "TEXTES")
    add_text(msp, "INGENIERIE.COM - ancrages indicatifs, formes A/B/C", 0.0, title_y - 0.40, 0.17, "TEXTES")

    draw_base(msp, model, strategy_report)
    draw_plan_anchorage(msp, model, anchorage_report)

    tx, ty = table_position(model)

    draw_table(msp, anchorage_report, tx, ty)
    draw_shapes(msp, anchorage_report, tx, ty - 6.2)

    # Planche A3 en presentation (paperspace) cadree sur les details d'ancrage.
    try:
        from civil_engine.plans.paperspace_layout import setup_a3_sheet_fit_modelspace
        from civil_engine.plans.cartouche import build_cartouche_values
        setup_a3_sheet_fit_modelspace(
            doc=doc,
            values=build_cartouche_values(
                plan_title="Ancrages et recouvrements",
                scale_label="VARIABLE",
            ),
        )
    except Exception:
        pass

    from civil_engine.plans.dxf_finalize import finalize_and_save
    finalize_and_save(doc, output_path)
    return str(output_path)
