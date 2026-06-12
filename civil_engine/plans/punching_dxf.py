from __future__ import annotations

from pathlib import Path
from typing import Any

import ezdxf

from civil_engine.foundations.column_effective import get_effective_column_boxes, get_effective_column_centers


# =========================================================
# OUTILS DE BASE
# =========================================================

def ensure_layers(doc) -> None:
    layers = {
        "EMPRISE": 7,
        "POTEAUX": 7,
        "AXES": 2,
        "COTATIONS_AXES": 4,
        "SI": 3,
        "SE": 30,
        "SC": 5,
        "RL": 140,
        "CENTRE_CHARGE": 4,
        "POINCON_OK": 8,
        "POINCON_WARNING": 30,
        "POINCON_NOT_OK": 1,
        "TEXTES": 7,
        "TABLEAU": 7,
        "NOTA": 1,
    }

    for name, color in layers.items():
        if name not in doc.layers:
            doc.layers.add(name=name, color=color)


def add_text(msp, text: str, x: float, y: float, height: float = 0.18, layer: str = "TEXTES") -> None:
    msp.add_text(
        text,
        dxfattribs={"height": height, "layer": layer},
    ).set_placement((x, y))


def add_text_rotated(
    msp,
    text: str,
    x: float,
    y: float,
    height: float,
    layer: str,
    rotation: float = 0.0,
) -> None:
    msp.add_text(
        text,
        dxfattribs={
            "height": height,
            "layer": layer,
            "rotation": rotation,
        },
    ).set_placement((x, y))


def add_line(msp, x1: float, y1: float, x2: float, y2: float, layer: str) -> None:
    msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": layer})


def add_rect(msp, xmin: float, ymin: float, xmax: float, ymax: float, layer: str) -> None:
    msp.add_lwpolyline(
        [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)],
        close=True,
        dxfattribs={"layer": layer},
    )


def add_circle(msp, x: float, y: float, radius: float, layer: str) -> None:
    msp.add_circle((x, y), radius, dxfattribs={"layer": layer})


def add_cross(msp, x: float, y: float, size: float, layer: str) -> None:
    add_line(msp, x - size, y, x + size, y, layer)
    add_line(msp, x, y - size, x, y + size, layer)


def add_polyline(msp, points: list[list[float]], layer: str, closed: bool = False) -> None:
    if len(points) < 2:
        return

    msp.add_lwpolyline(
        [(float(p[0]), float(p[1])) for p in points],
        close=closed,
        dxfattribs={"layer": layer},
    )


def add_dashed_line(msp, x1: float, y1: float, x2: float, y2: float, layer: str) -> None:
    dx = x2 - x1
    dy = y2 - y1
    length = (dx * dx + dy * dy) ** 0.5

    if length <= 1e-9:
        return

    ux = dx / length
    uy = dy / length

    dash = 0.25
    gap = 0.15
    pos = 0.0

    while pos < length:
        start = pos
        end = min(pos + dash, length)

        add_line(
            msp,
            x1 + ux * start,
            y1 + uy * start,
            x1 + ux * end,
            y1 + uy * end,
            layer,
        )

        pos += dash + gap




def add_dashed_rect(msp, xmin: float, ymin: float, xmax: float, ymax: float, layer: str) -> None:
    add_dashed_line(msp, xmin, ymin, xmax, ymin, layer)
    add_dashed_line(msp, xmax, ymin, xmax, ymax, layer)
    add_dashed_line(msp, xmax, ymax, xmin, ymax, layer)
    add_dashed_line(msp, xmin, ymax, xmin, ymin, layer)


def fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


# =========================================================
# LECTURE MODELE
# =========================================================

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


def unique_sorted(values: list[float], tolerance: float = 0.20) -> list[float]:
    if not values:
        return []

    values = sorted(values)
    groups: list[list[float]] = []

    for value in values:
        if not groups:
            groups.append([value])
            continue

        avg = sum(groups[-1]) / len(groups[-1])

        if abs(value - avg) <= tolerance:
            groups[-1].append(value)
        else:
            groups.append([value])

    return [round(sum(g) / len(g), 4) for g in groups]


def axis_label(index: int) -> str:
    letters = ""
    n = index

    while True:
        letters = chr(ord("A") + n % 26) + letters
        n = n // 26 - 1
        if n < 0:
            break

    return letters


def extract_axes(model: dict[str, Any]) -> tuple[list[float], list[float]]:
    foundation = get_foundation_level(model)
    if foundation is None:
        return [], []

    xs = [float(c["cx"]) for c in foundation.get("columns", [])]
    ys = [float(c["cy"]) for c in foundation.get("columns", [])]

    return unique_sorted(xs, 0.20), unique_sorted(ys, 0.20)


def get_column_centers(model: dict[str, Any]) -> dict[str, dict[str, float]]:
    return get_effective_column_centers(model)


def draw_emprise_and_columns(msp, model: dict[str, Any]) -> None:
    foundation = get_foundation_level(model)

    if foundation is None:
        return

    for footprint in foundation.get("footprints", []):
        add_polyline(msp, footprint.get("points", []), "EMPRISE", closed=True)

    boxes = get_effective_column_boxes(model)

    for column_id, box in boxes.items():
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
            float(box["xmax"]) + 0.08,
            float(box["ymax"]) + 0.08,
            0.10,
            "POTEAUX",
        )


def add_dimension_segment(
    msp,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    text: str,
    layer: str,
    vertical: bool = False,
) -> None:
    add_line(msp, x1, y1, x2, y2, layer)

    tick = 0.12

    if vertical:
        add_line(msp, x1 - tick, y1, x1 + tick, y1, layer)
        add_line(msp, x2 - tick, y2, x2 + tick, y2, layer)

        add_text_rotated(
            msp,
            text,
            x1 - 0.35,
            (y1 + y2) / 2.0,
            0.11,
            layer,
            rotation=90.0,
        )
    else:
        add_line(msp, x1, y1 - tick, x1, y1 + tick, layer)
        add_line(msp, x2, y2 - tick, x2, y2 + tick, layer)

        add_text(
            msp,
            text,
            (x1 + x2) / 2.0 - 0.12,
            y1 - 0.25,
            0.11,
            layer,
        )


def draw_axes(msp, model: dict[str, Any]) -> None:
    bbox = get_foundation_bbox(model)
    if bbox is None:
        return

    axes_x, axes_y = extract_axes(model)
    if not axes_x or not axes_y:
        return

    xmin = float(bbox["xmin"])
    xmax = float(bbox["xmax"])
    ymin = float(bbox["ymin"])
    ymax = float(bbox["ymax"])

    bubble_r = 0.18

    y_bottom = ymin - 0.55
    y_top = ymax + 0.55
    x_left = xmin - 0.55
    x_right = xmax + 0.55

    # Axes verticaux
    for i, x in enumerate(axes_x, start=1):
        add_dashed_line(msp, x, y_bottom + bubble_r, x, y_top - bubble_r, "AXES")

        add_circle(msp, x, y_bottom, bubble_r, "AXES")
        add_text(msp, str(i), x - 0.05, y_bottom - 0.06, 0.12, "AXES")

        add_circle(msp, x, y_top, bubble_r, "AXES")
        add_text(msp, str(i), x - 0.05, y_top - 0.06, 0.12, "AXES")

    # Axes horizontaux
    for i, y in enumerate(axes_y):
        label = axis_label(i)

        add_dashed_line(msp, x_left + bubble_r, y, x_right - bubble_r, y, "AXES")

        add_circle(msp, x_left, y, bubble_r, "AXES")
        add_text(msp, label, x_left - 0.05, y - 0.06, 0.12, "AXES")

        add_circle(msp, x_right, y, bubble_r, "AXES")
        add_text(msp, label, x_right - 0.05, y - 0.06, 0.12, "AXES")

    # Cotations X
    dim_y = ymin - 1.05
    for i in range(len(axes_x) - 1):
        dist = axes_x[i + 1] - axes_x[i]
        add_dimension_segment(
            msp,
            axes_x[i], dim_y,
            axes_x[i + 1], dim_y,
            f"{dist:.2f}",
            "COTATIONS_AXES",
            False,
        )

    add_dimension_segment(
        msp,
        axes_x[0], ymin - 1.45,
        axes_x[-1], ymin - 1.45,
        f"{axes_x[-1] - axes_x[0]:.2f}",
        "COTATIONS_AXES",
        False,
    )

    # Cotations Y
    dim_x = xmin - 1.05
    for i in range(len(axes_y) - 1):
        dist = axes_y[i + 1] - axes_y[i]
        add_dimension_segment(
            msp,
            dim_x, axes_y[i],
            dim_x, axes_y[i + 1],
            f"{dist:.2f}",
            "COTATIONS_AXES",
            True,
        )

    add_dimension_segment(
        msp,
        xmin - 1.45, axes_y[0],
        xmin - 1.45, axes_y[-1],
        f"{axes_y[-1] - axes_y[0]:.2f}",
        "COTATIONS_AXES",
        True,
    )


# =========================================================
# FONDATIONS FINALES UNIQUEMENT
# =========================================================

def layer_for_foundation_type(ftype: str) -> str:
    if ftype == "SI":
        return "SI"
    if ftype == "SE":
        return "SE"
    if ftype == "SC":
        return "SC"
    if ftype == "RL":
        return "RL"
    return "SI"


def draw_final_foundations_only(msp, strategy_report: dict[str, Any]) -> None:
    """
    Ne dessine que la configuration finale.
    Aucune ancienne semelle. Aucune solution antérieure.
    """
    for element in strategy_report.get("final_foundations", []):
        bbox = element.get("bbox")
        if not bbox:
            continue

        layer = layer_for_foundation_type(element.get("type", ""))

        add_rect(
            msp,
            float(bbox["xmin"]),
            float(bbox["ymin"]),
            float(bbox["xmax"]),
            float(bbox["ymax"]),
            layer,
        )

        add_cross(
            msp,
            float(element.get("cx", 0.0)),
            float(element.get("cy", 0.0)),
            0.15,
            "CENTRE_CHARGE",
        )

        add_text(
            msp,
            str(element.get("id", "")),
            float(bbox["xmax"]) + 0.18,
            float(bbox["ymax"]) + 0.18,
            0.11,
            layer,
        )


# =========================================================
# POINÇONNEMENT
# =========================================================

def status_layer(status: str) -> str:
    if status == "OK_PRELIMINARY":
        return "POINCON_OK"
    if status == "WARNING":
        return "POINCON_WARNING"
    return "POINCON_NOT_OK"



def draw_punching_zones(msp, model: dict[str, Any], strategy_report: dict[str, Any], punching_report: dict[str, Any]) -> None:
    """
    Dessine les périmètres de contrôle de poinçonnement.

    Important :
    - ce ne sont PAS des semelles ;
    - OK est dessiné en pointillé gris discret ;
    - WARNING orange ;
    - NOT_OK rouge.
    """
    centers = get_column_centers(model)
    final_ids = {item.get("id") for item in strategy_report.get("final_foundations", [])}

    for foundation_check in punching_report.get("checks", []):
        foundation_id = foundation_check.get("foundation_id")

        if foundation_id not in final_ids:
            continue

        for check in foundation_check.get("column_checks", []):
            column_id = check.get("column_id")
            center = centers.get(column_id)

            if center is None:
                continue

            x = float(center["cx"])
            y = float(center["cy"])
            c1 = float(check.get("c1_m", 0.25))
            c2 = float(check.get("c2_m", 0.25))
            d = float(check.get("d_m", 0.30))

            half_x = c1 / 2.0 + 2.0 * d
            half_y = c2 / 2.0 + 2.0 * d

            layer = status_layer(check.get("status", "NOT_OK"))

            add_dashed_rect(
                msp,
                x - half_x,
                y - half_y,
                x + half_x,
                y + half_y,
                layer,
            )

            # Petite croix discrète au poteau contrôlé
            add_cross(msp, x, y, 0.08, layer)

            # Label court pour ne pas confondre avec une semelle
            add_text(
                msp,
                "u1",
                x + half_x + 0.05,
                y + half_y + 0.05,
                0.08,
                layer,
            )




def draw_table(msp, strategy_report: dict[str, Any], punching_report: dict[str, Any], x: float, y: float) -> None:
    add_text(msp, "TABLEAU POINCONNEMENT - CONFIGURATION FINALE", x, y, 0.22, "TABLEAU")

    y -= 0.45

    headers = [
        ("FOND", 0.0),
        ("TYPE", 2.2),
        ("POT", 3.2),
        ("H", 4.2),
        ("d", 5.0),
        ("vEd", 5.9),
        ("vRdc", 7.0),
        ("U", 8.1),
        ("STATUT", 8.9),
    ]

    for label, dx in headers:
        add_text(msp, label, x + dx, y, 0.11, "TABLEAU")

    y -= 0.28

    type_map = {
        item.get("id"): item.get("type")
        for item in strategy_report.get("final_foundations", [])
    }

    final_ids = set(type_map.keys())

    for foundation_check in punching_report.get("checks", []):
        fid = foundation_check.get("foundation_id")

        if fid not in final_ids:
            continue

        ftype = type_map.get(fid, "-")

        for check in foundation_check.get("column_checks", []):
            stat = check.get("status", "-")
            stat_layer = status_layer(stat)

            row = [
                (fid, 0.0),
                (ftype, 2.2),
                (check.get("column_id", "-"), 3.2),
                (fmt(check.get("H_m")), 4.2),
                (fmt(check.get("d_m")), 5.0),
                (fmt(check.get("vEd_MPa")), 5.9),
                (fmt(check.get("vRdc_MPa")), 7.0),
                (fmt(check.get("utilization")), 8.1),
                (stat, 8.9),
            ]

            for value, dx in row:
                add_text(
                    msp,
                    str(value),
                    x + dx,
                    y,
                    0.095,
                    stat_layer if dx == 8.9 else "TABLEAU",
                )

            y -= 0.22

    y -= 0.30

    add_text(msp, "NOTA", x, y, 0.15, "NOTA")
    y -= 0.22

    add_text(
        msp,
        "Plan base uniquement sur la configuration finale.",
        x,
        y,
        0.10,
        "NOTA",
    )
    y -= 0.18

    add_text(
        msp,
        "Aucune ancienne semelle ni solution anterieure n'est affichee.",
        x,
        y,
        0.10,
        "NOTA",
    )
    y -= 0.18

    add_text(
        msp,
        "Controle preliminaire a verifier dans la note finale EC2 / BAEL.",
        x,
        y,
        0.10,
        "NOTA",
    )


def draw_legend(msp, x: float, y: float) -> None:
    add_text(msp, "LEGENDE POINCONNEMENT", x, y, 0.16, "TABLEAU")
    y -= 0.30

    add_rect(msp, x, y - 0.08, x + 0.30, y + 0.08, "POINCON_OK")
    add_text(msp, "OK_PRELIMINARY", x + 0.45, y - 0.06, 0.11, "TABLEAU")
    y -= 0.25

    add_rect(msp, x, y - 0.08, x + 0.30, y + 0.08, "POINCON_WARNING")
    add_text(msp, "WARNING", x + 0.45, y - 0.06, 0.11, "TABLEAU")
    y -= 0.25

    add_rect(msp, x, y - 0.08, x + 0.30, y + 0.08, "POINCON_NOT_OK")
    add_text(msp, "NOT_OK", x + 0.45, y - 0.06, 0.11, "TABLEAU")


def table_position(model: dict[str, Any]) -> tuple[float, float]:
    bbox = get_foundation_bbox(model)
    if bbox is None:
        return 18.0, 12.0

    return float(bbox["xmax"]) + 5.5, float(bbox["ymax"]) + 2.3


# =========================================================
# GENERATION DXF
# =========================================================

def generate_punching_dxf(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    punching_report: dict[str, Any],
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

    add_text(
        msp,
        "PLAN DE POINCONNEMENT - CONFIGURATION FINALE",
        0.0,
        title_y,
        0.30,
        "TEXTES",
    )

    add_text(
        msp,
        "INGENIERIE.COM - fondations finales uniquement",
        0.0,
        title_y - 0.40,
        0.17,
        "TEXTES",
    )

    draw_emprise_and_columns(msp, model)
    draw_axes(msp, model)
    draw_final_foundations_only(msp, strategy_report)
    draw_punching_zones(msp, model, strategy_report, punching_report)

    tx, ty = table_position(model)
    draw_table(msp, strategy_report, punching_report, tx, ty)
    draw_legend(msp, tx, ty - 5.1)

    doc.saveas(output_path)
    return str(output_path)
