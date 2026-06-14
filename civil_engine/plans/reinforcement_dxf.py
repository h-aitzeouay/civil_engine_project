from __future__ import annotations

from pathlib import Path
from typing import Any

import ezdxf

from civil_engine.foundations.column_effective import get_effective_column_boxes


# =========================================================
# LAYERS
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
        "ARM_INF_X": 5,
        "ARM_INF_Y": 6,
        "ARM_SUP_X": 30,
        "ARM_SUP_Y": 1,
        "CENTRE_CHARGE": 4,
        "RENVOIS_FERRAILLAGE": 8,
        "TEXTES": 7,
        "TABLEAU_FERRAILLAGE": 7,
        "NOTA": 1,
    }

    for name, color in layers.items():
        if name not in doc.layers:
            doc.layers.add(name=name, color=color)


# =========================================================
# BASIC DXF TOOLS
# =========================================================

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


def fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


# =========================================================
# MODEL READING
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

    return [round(sum(group) / len(group), 4) for group in groups]


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


# =========================================================
# COLLISION / TEXT MANAGER
# =========================================================

def pad_box(box: dict[str, float], pad: float) -> dict[str, float]:
    return {
        "xmin": float(box["xmin"]) - pad,
        "xmax": float(box["xmax"]) + pad,
        "ymin": float(box["ymin"]) - pad,
        "ymax": float(box["ymax"]) + pad,
    }


def rects_overlap(a: dict[str, float], b: dict[str, float]) -> bool:
    return not (
        float(a["xmax"]) <= float(b["xmin"])
        or float(a["xmin"]) >= float(b["xmax"])
        or float(a["ymax"]) <= float(b["ymin"])
        or float(a["ymin"]) >= float(b["ymax"])
    )


def overlap_count(box: dict[str, float], occupied: list[dict[str, float]]) -> int:
    return sum(1 for other in occupied if rects_overlap(box, other))


def estimate_text_width(text: str, height: float) -> float:
    return max(0.45, len(text) * height * 0.62)


def make_text_box(
    x: float,
    y_top: float,
    lines: list[str],
    text_height: float,
    line_spacing: float,
) -> dict[str, float]:
    width = max(estimate_text_width(line, text_height) for line in lines)
    height = max(text_height, (len(lines) - 1) * line_spacing + text_height)

    return {
        "xmin": x,
        "xmax": x + width,
        "ymin": y_top - height,
        "ymax": y_top,
        "text_x": x,
        "text_y_top": y_top,
        "line_spacing": line_spacing,
        "text_height": text_height,
    }


def axis_exclusion_boxes(model: dict[str, Any]) -> list[dict[str, float]]:
    bbox = get_foundation_bbox(model)

    if bbox is None:
        return []

    axes_x, axes_y = extract_axes(model)

    if not axes_x or not axes_y:
        return []

    xmin = float(bbox["xmin"])
    xmax = float(bbox["xmax"])
    ymin = float(bbox["ymin"])
    ymax = float(bbox["ymax"])

    bubble_r = 0.18
    pad = 0.16

    y_bottom = ymin - 0.55
    y_top = ymax + 0.55
    x_left = xmin - 0.55
    x_right = xmax + 0.55

    boxes = []

    # bulles numerotees haut/bas
    for x in axes_x:
        boxes.append({
            "xmin": x - bubble_r - pad,
            "xmax": x + bubble_r + pad,
            "ymin": y_bottom - bubble_r - pad,
            "ymax": y_bottom + bubble_r + pad,
        })
        boxes.append({
            "xmin": x - bubble_r - pad,
            "xmax": x + bubble_r + pad,
            "ymin": y_top - bubble_r - pad,
            "ymax": y_top + bubble_r + pad,
        })

    # bulles alphabetiques gauche/droite
    for y in axes_y:
        boxes.append({
            "xmin": x_left - bubble_r - pad,
            "xmax": x_left + bubble_r + pad,
            "ymin": y - bubble_r - pad,
            "ymax": y + bubble_r + pad,
        })
        boxes.append({
            "xmin": x_right - bubble_r - pad,
            "xmax": x_right + bubble_r + pad,
            "ymin": y - bubble_r - pad,
            "ymax": y + bubble_r + pad,
        })

    # bandes de cotations horizontales et verticales
    boxes.append({
        "xmin": axes_x[0] - 0.40,
        "xmax": axes_x[-1] + 0.40,
        "ymin": ymin - 1.75,
        "ymax": ymin - 0.85,
    })

    boxes.append({
        "xmin": xmin - 1.75,
        "xmax": xmin - 0.85,
        "ymin": axes_y[0] - 0.40,
        "ymax": axes_y[-1] + 0.40,
    })

    return boxes


def column_exclusion_boxes(
    model: dict[str, Any],
    strategy_report: dict[str, Any] | None = None,
) -> list[dict[str, float]]:
    """
    Zones interdites autour des poteaux et de leurs labels.

    Les labels poteaux sont considérés comme des objets graphiques
    à placer hors semelles.
    """
    boxes: list[dict[str, float]] = []

    occupied: list[dict[str, float]] = []

    if strategy_report is not None:
        occupied.extend(foundation_exclusion_boxes(strategy_report, pad_m=0.14))

    for column_id, box in get_effective_column_boxes(model).items():
        column_zone = pad_box(box, 0.10)

        boxes.append(column_zone)
        occupied.append(column_zone)

        label_box = choose_column_label_box(
            column_box=box,
            column_id=column_id,
            occupied=occupied,
            height=0.10,
        )

        label_zone = pad_box(label_box, 0.06)

        boxes.append(label_zone)
        occupied.append(label_zone)

    return boxes

def final_foundation_boxes(strategy_report: dict[str, Any]) -> list[dict[str, float]]:
    boxes = []

    for element in strategy_report.get("final_foundations", []):
        bbox = element.get("bbox")

        if not bbox:
            continue

        boxes.append(pad_box(bbox, 0.08))

    return boxes



def foundation_exclusion_boxes(
    strategy_report: dict[str, Any],
    pad_m: float = 0.22,
) -> list[dict[str, float]]:
    """
    Zones interdites pour les textes.

    Règle :
    aucune annotation de ferraillage ni désignation de poteau
    ne doit se placer sur ou trop près d'une semelle.
    """
    boxes: list[dict[str, float]] = []

    for element in strategy_report.get("final_foundations", []):
        bbox = element.get("bbox")

        if not bbox:
            continue

        boxes.append(pad_box(bbox, pad_m))

    return boxes


def candidate_text_box(
    x: float,
    y_top: float,
    text: str,
    height: float,
) -> dict[str, float]:
    return make_text_box(
        x=x,
        y_top=y_top,
        lines=[text],
        text_height=height,
        line_spacing=height * 1.25,
    )


def choose_column_label_box(
    column_box: dict[str, float],
    column_id: str,
    occupied: list[dict[str, float]],
    height: float = 0.10,
) -> dict[str, float]:
    """
    Place la désignation du poteau hors semelles.

    Priorité :
    - droite haut ;
    - gauche haut ;
    - haut ;
    - bas ;
    - droite / gauche ;
    - diagonales.
    """
    xmin = float(column_box["xmin"])
    xmax = float(column_box["xmax"])
    ymin = float(column_box["ymin"])
    ymax = float(column_box["ymax"])

    width = estimate_text_width(column_id, height)

    candidates: list[dict[str, float]] = []

    for off in [0.12, 0.22, 0.35, 0.55, 0.80, 1.10, 1.45]:
        positions = [
            (xmax + off, ymax + off),
            (xmin - off - width, ymax + off),
            ((xmin + xmax) / 2.0 - width / 2.0, ymax + off),
            ((xmin + xmax) / 2.0 - width / 2.0, ymin - off),
            (xmax + off, (ymin + ymax) / 2.0),
            (xmin - off - width, (ymin + ymax) / 2.0),
            (xmax + off, ymin - off),
            (xmin - off - width, ymin - off),
        ]

        for x, y in positions:
            candidates.append(candidate_text_box(x, y, column_id, height))

    free = [
        candidate
        for candidate in candidates
        if overlap_count(candidate, occupied) == 0
    ]

    if free:
        return free[0]

    return sorted(
        candidates,
        key=lambda c: overlap_count(c, occupied),
    )[0]


def add_leader_to_column_label(
    msp,
    column_box: dict[str, float],
    label_box: dict[str, float],
) -> None:
    cx = (float(column_box["xmin"]) + float(column_box["xmax"])) / 2.0
    cy = (float(column_box["ymin"]) + float(column_box["ymax"])) / 2.0

    lx = float(label_box["xmin"])
    ly = (float(label_box["ymin"]) + float(label_box["ymax"])) / 2.0

    add_line(
        msp,
        cx,
        cy,
        lx,
        ly,
        "RENVOIS_FERRAILLAGE",
    )

def table_position(model: dict[str, Any]) -> tuple[float, float]:
    bbox = get_foundation_bbox(model)

    if bbox is None:
        return 18.0, 12.0

    return float(bbox["xmax"]) + 5.5, float(bbox["ymax"]) + 2.3


def table_exclusion_box(model: dict[str, Any], reinforcement_report: dict[str, Any]) -> dict[str, float]:
    x, y = table_position(model)
    row_count = max(1, len(reinforcement_report.get("results", [])))

    return {
        "xmin": x - 0.20,
        "xmax": x + 16.80,
        "ymin": y - 1.60 - row_count * 0.25 - 2.50,
        "ymax": y + 0.40,
    }


def build_initial_occupied_boxes(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    reinforcement_report: dict[str, Any],
) -> list[dict[str, float]]:
    occupied: list[dict[str, float]] = []

    # Bulles, axes et cotations.
    occupied.extend(axis_exclusion_boxes(model))

    # Semelles = zones interdites pour les annotations Inf/Sup.
    # Le padding évite que le texte touche le contour.
    occupied.extend(foundation_exclusion_boxes(strategy_report, pad_m=0.25))

    # Poteaux + labels poteaux placés hors semelles.
    occupied.extend(column_exclusion_boxes(model, strategy_report))

    # Tableau à droite.
    occupied.append(table_exclusion_box(model, reinforcement_report))

    return occupied

def build_label_candidates(
    bbox: dict[str, float],
    lines: list[str],
    text_height: float,
    line_spacing: float,
) -> list[dict[str, float]]:
    xmin = float(bbox["xmin"])
    xmax = float(bbox["xmax"])
    ymin = float(bbox["ymin"])
    ymax = float(bbox["ymax"])

    width = xmax - xmin
    height = ymax - ymin

    candidates = []

    # plusieurs anneaux autour de la fondation
    for off in [0.25, 0.45, 0.70, 1.00, 1.35, 1.75]:
        raw_positions = [
            # droite
            (xmax + off, ymax - 0.05),
            (xmax + off, (ymin + ymax) / 2.0 + 0.10),
            (xmax + off, ymin + 0.35),

            # gauche
            (xmin - off - max(estimate_text_width(line, text_height) for line in lines), ymax - 0.05),
            (xmin - off - max(estimate_text_width(line, text_height) for line in lines), (ymin + ymax) / 2.0 + 0.10),

            # haut
            (xmin, ymax + off),
            (xmin + 0.35 * width, ymax + off),

            # bas
            (xmin, ymin - off),
            (xmin + 0.35 * width, ymin - off),

            # diagonales
            (xmax + off, ymax + off),
            (xmin - off - max(estimate_text_width(line, text_height) for line in lines), ymax + off),
            (xmax + off, ymin - off),
            (xmin - off - max(estimate_text_width(line, text_height) for line in lines), ymin - off),
        ]

        for x, y_top in raw_positions:
            candidates.append(make_text_box(
                x=x,
                y_top=y_top,
                lines=lines,
                text_height=text_height,
                line_spacing=line_spacing,
            ))

    return candidates


def choose_label_box(
    bbox: dict[str, float],
    lines: list[str],
    occupied: list[dict[str, float]],
    text_height: float = 0.09,
    line_spacing: float = 0.20,
) -> dict[str, float]:
    candidates = build_label_candidates(
        bbox=bbox,
        lines=lines,
        text_height=text_height,
        line_spacing=line_spacing,
    )

    free = [candidate for candidate in candidates if overlap_count(candidate, occupied) == 0]

    if free:
        return free[0]

    # Si aucune position n'est totalement libre, on choisit la moins mauvaise,
    # au lieu de placer arbitrairement sur une bulle ou une cote.
    ranked = sorted(
        candidates,
        key=lambda candidate: (
            overlap_count(candidate, occupied),
            abs(candidate["xmin"] - float(bbox["xmax"])),
            -candidate["ymax"],
        ),
    )

    return ranked[0]


def add_label_lines(
    msp,
    label_box: dict[str, float],
    lines: list[str],
    layer: str = "TEXTES",
) -> None:
    x = float(label_box["text_x"])
    y = float(label_box["text_y_top"])
    h = float(label_box["text_height"])
    spacing = float(label_box["line_spacing"])

    for index, line in enumerate(lines):
        add_text(msp, line, x, y - index * spacing, h, layer)


def add_leader_to_label(
    msp,
    foundation_bbox: dict[str, float],
    label_box: dict[str, float],
) -> None:
    fx = (float(foundation_bbox["xmin"]) + float(foundation_bbox["xmax"])) / 2.0
    fy = (float(foundation_bbox["ymin"]) + float(foundation_bbox["ymax"])) / 2.0

    lx = float(label_box["xmin"])
    ly = (float(label_box["ymin"]) + float(label_box["ymax"])) / 2.0

    if float(label_box["xmin"]) > float(foundation_bbox["xmax"]):
        start_x = float(foundation_bbox["xmax"])
        start_y = fy
        end_x = float(label_box["xmin"])
        end_y = ly
    elif float(label_box["xmax"]) < float(foundation_bbox["xmin"]):
        start_x = float(foundation_bbox["xmin"])
        start_y = fy
        end_x = float(label_box["xmax"])
        end_y = ly
    elif float(label_box["ymin"]) > float(foundation_bbox["ymax"]):
        start_x = fx
        start_y = float(foundation_bbox["ymax"])
        end_x = fx
        end_y = float(label_box["ymin"])
    else:
        start_x = fx
        start_y = float(foundation_bbox["ymin"])
        end_x = lx
        end_y = float(label_box["ymax"])

    add_line(msp, start_x, start_y, end_x, end_y, "RENVOIS_FERRAILLAGE")


# =========================================================
# AXES / BASE DRAWING
# =========================================================

def draw_emprise_and_columns(
    msp,
    model: dict[str, Any],
    strategy_report: dict[str, Any] | None = None,
) -> None:
    foundation = get_foundation_level(model)

    if foundation is None:
        return

    for footprint in foundation.get("footprints", []):
        add_polyline(msp, footprint.get("points", []), "EMPRISE", closed=True)

    occupied: list[dict[str, float]] = []

    if strategy_report is not None:
        occupied.extend(foundation_exclusion_boxes(strategy_report, pad_m=0.14))

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

        column_zone = pad_box(box, 0.10)
        occupied.append(column_zone)

        label_box = choose_column_label_box(
            column_box=box,
            column_id=column_id,
            occupied=occupied,
            height=0.10,
        )

        add_label_lines(
            msp,
            label_box,
            [column_id],
            "POTEAUX",
        )

        add_leader_to_column_label(
            msp,
            column_box=box,
            label_box=label_box,
        )

        occupied.append(pad_box(label_box, 0.06))

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
        add_text_rotated(msp, text, x1 - 0.35, (y1 + y2) / 2.0, 0.11, layer, 90.0)
    else:
        add_line(msp, x1, y1 - tick, x1, y1 + tick, layer)
        add_line(msp, x2, y2 - tick, x2, y2 + tick, layer)
        add_text(msp, text, (x1 + x2) / 2.0 - 0.12, y1 - 0.25, 0.11, layer)


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

    for i, x in enumerate(axes_x, start=1):
        add_dashed_line(msp, x, y_bottom + bubble_r, x, y_top - bubble_r, "AXES")

        add_circle(msp, x, y_bottom, bubble_r, "AXES")
        add_text(msp, str(i), x - 0.05, y_bottom - 0.06, 0.12, "AXES")

        add_circle(msp, x, y_top, bubble_r, "AXES")
        add_text(msp, str(i), x - 0.05, y_top - 0.06, 0.12, "AXES")

    for i, y in enumerate(axes_y):
        label = axis_label(i)

        add_dashed_line(msp, x_left + bubble_r, y, x_right - bubble_r, y, "AXES")

        add_circle(msp, x_left, y, bubble_r, "AXES")
        add_text(msp, label, x_left - 0.05, y - 0.06, 0.12, "AXES")

        add_circle(msp, x_right, y, bubble_r, "AXES")
        add_text(msp, label, x_right - 0.05, y - 0.06, 0.12, "AXES")

    dim_y = ymin - 1.05

    for i in range(len(axes_x) - 1):
        dist = axes_x[i + 1] - axes_x[i]
        add_dimension_segment(
            msp,
            axes_x[i],
            dim_y,
            axes_x[i + 1],
            dim_y,
            f"{dist:.2f}",
            "COTATIONS_AXES",
            False,
        )

    add_dimension_segment(
        msp,
        axes_x[0],
        ymin - 1.45,
        axes_x[-1],
        ymin - 1.45,
        f"{axes_x[-1] - axes_x[0]:.2f}",
        "COTATIONS_AXES",
        False,
    )

    dim_x = xmin - 1.05

    for i in range(len(axes_y) - 1):
        dist = axes_y[i + 1] - axes_y[i]
        add_dimension_segment(
            msp,
            dim_x,
            axes_y[i],
            dim_x,
            axes_y[i + 1],
            f"{dist:.2f}",
            "COTATIONS_AXES",
            True,
        )

    add_dimension_segment(
        msp,
        xmin - 1.45,
        axes_y[0],
        xmin - 1.45,
        axes_y[-1],
        f"{axes_y[-1] - axes_y[0]:.2f}",
        "COTATIONS_AXES",
        True,
    )


# =========================================================
# FOUNDATIONS
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


def draw_final_foundations(
    msp,
    strategy_report: dict[str, Any],
    occupied: list[dict[str, float]],
) -> None:
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

        fid = str(element.get("id", ""))

        label_box = choose_label_box(
            bbox=bbox,
            lines=[fid],
            occupied=occupied,
            text_height=0.11,
            line_spacing=0.12,
        )

        add_label_lines(msp, label_box, [fid], layer)
        occupied.append(pad_box(label_box, 0.05))


# =========================================================
# REINFORCEMENT DRAWING
# =========================================================

def find_reinf_result(reinforcement_report: dict[str, Any], foundation_id: str) -> dict[str, Any] | None:
    for item in reinforcement_report.get("results", []):
        if item.get("foundation_id") == foundation_id:
            return item
    return None


def get_spacing_m(reinf: dict[str, Any], key: str) -> float:
    return float(
        reinf.get("reinforcement", {})
        .get(key, {})
        .get("proposal", {})
        .get("spacing_m", 0.20)
    )


def get_label(reinf: dict[str, Any], key: str) -> str:
    return str(
        reinf.get("reinforcement", {})
        .get(key, {})
        .get("proposal", {})
        .get("label", "-")
    )


def draw_bar_lines_x(
    msp,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    spacing_m: float,
    layer: str,
    cover_m: float = 0.08,
) -> None:
    y = ymin + cover_m

    while y <= ymax - cover_m + 1e-9:
        add_line(msp, xmin + cover_m, y, xmax - cover_m, y, layer)
        y += spacing_m


def draw_bar_lines_y(
    msp,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    spacing_m: float,
    layer: str,
    cover_m: float = 0.08,
) -> None:
    x = xmin + cover_m

    while x <= xmax - cover_m + 1e-9:
        add_line(msp, x, ymin + cover_m, x, ymax - cover_m, layer)
        x += spacing_m


def draw_reinforcement_for_element(
    msp,
    element: dict[str, Any],
    reinf: dict[str, Any],
    occupied: list[dict[str, float]],
) -> None:
    bbox = element["bbox"]

    xmin = float(bbox["xmin"])
    xmax = float(bbox["xmax"])
    ymin = float(bbox["ymin"])
    ymax = float(bbox["ymax"])

    cover = 0.08

    spacing_inf_x = get_spacing_m(reinf, "bottom_bars_X")
    spacing_inf_y = get_spacing_m(reinf, "bottom_bars_Y")
    spacing_sup_x = get_spacing_m(reinf, "top_bars_X")
    spacing_sup_y = get_spacing_m(reinf, "top_bars_Y")

    # Nappe inferieure
    draw_bar_lines_x(msp, xmin, xmax, ymin, ymax, spacing_inf_x, "ARM_INF_X", cover)
    draw_bar_lines_y(msp, xmin, xmax, ymin, ymax, spacing_inf_y, "ARM_INF_Y", cover)

    # Nappe superieure sur zone centrale
    width = xmax - xmin
    height = ymax - ymin

    sxmin = xmin + 0.20 * width
    sxmax = xmax - 0.20 * width
    symin = ymin + 0.20 * height
    symax = ymax - 0.20 * height

    if sxmax > sxmin and symax > symin:
        draw_bar_lines_x(msp, sxmin, sxmax, symin, symax, spacing_sup_x, "ARM_SUP_X", cover / 2.0)
        draw_bar_lines_y(msp, sxmin, sxmax, symin, symax, spacing_sup_y, "ARM_SUP_Y", cover / 2.0)

    label_1 = f"Inf  X:{get_label(reinf, 'bottom_bars_X')}    Y:{get_label(reinf, 'bottom_bars_Y')}"
    label_2 = f"Sup  X:{get_label(reinf, 'top_bars_X')}    Y:{get_label(reinf, 'top_bars_Y')}"

    label_box = choose_label_box(
        bbox=bbox,
        lines=[label_1, label_2],
        occupied=occupied,
        text_height=0.09,
        line_spacing=0.20,
    )

    add_label_lines(msp, label_box, [label_1, label_2], "TEXTES")
    add_leader_to_label(msp, bbox, label_box)

    occupied.append(pad_box(label_box, 0.08))


def draw_reinforcement(
    msp,
    strategy_report: dict[str, Any],
    reinforcement_report: dict[str, Any],
    occupied: list[dict[str, float]],
) -> None:
    for element in strategy_report.get("final_foundations", []):
        fid = element.get("id")
        reinf = find_reinf_result(reinforcement_report, fid)

        if reinf is None:
            continue

        draw_reinforcement_for_element(
            msp=msp,
            element=element,
            reinf=reinf,
            occupied=occupied,
        )


# =========================================================
# TABLES
# =========================================================

def draw_table(msp, reinforcement_report: dict[str, Any], x: float, y: float) -> None:
    add_text(msp, "TABLEAU FERRAILLAGE PRELIMINAIRE", x, y, 0.22, "TABLEAU_FERRAILLAGE")
    y -= 0.45

    headers = [
        ("FOND", 0.0),
        ("TYPE", 2.0),
        ("A", 3.0),
        ("B", 4.0),
        ("H", 5.0),
        ("INF X", 6.0),
        ("INF Y", 8.4),
        ("SUP X", 10.8),
        ("SUP Y", 13.2),
    ]

    for label, dx in headers:
        add_text(msp, label, x + dx, y, 0.105, "TABLEAU_FERRAILLAGE")

    y -= 0.26

    for item in reinforcement_report.get("results", []):
        r = item.get("reinforcement", {})

        values = [
            (item.get("foundation_id"), 0.0),
            (item.get("foundation_type"), 2.0),
            (fmt(item.get("A_m")), 3.0),
            (fmt(item.get("B_m")), 4.0),
            (fmt(item.get("H_m")), 5.0),
            (r.get("bottom_bars_X", {}).get("proposal", {}).get("label", "-"), 6.0),
            (r.get("bottom_bars_Y", {}).get("proposal", {}).get("label", "-"), 8.4),
            (r.get("top_bars_X", {}).get("proposal", {}).get("label", "-"), 10.8),
            (r.get("top_bars_Y", {}).get("proposal", {}).get("label", "-"), 13.2),
        ]

        for value, dx in values:
            add_text(msp, str(value), x + dx, y, 0.085, "TABLEAU_FERRAILLAGE")

        y -= 0.22

    y -= 0.35

    add_text(msp, "NOTA", x, y, 0.15, "NOTA")
    y -= 0.22
    add_text(msp, "Ferraillage preliminaire base sur final_foundations.", x, y, 0.10, "NOTA")
    y -= 0.18
    add_text(msp, "Placement automatique anti-chevauchement des annotations.", x, y, 0.10, "NOTA")
    y -= 0.18
    add_text(msp, "A verifier avec efforts definitifs, poinconnement final et ancrages.", x, y, 0.10, "NOTA")


def draw_legend(msp, x: float, y: float) -> None:
    add_text(msp, "LEGENDE ARMATURES", x, y, 0.16, "TABLEAU_FERRAILLAGE")
    y -= 0.30

    add_line(msp, x, y, x + 0.40, y, "ARM_INF_X")
    add_text(msp, "Nappe inferieure X", x + 0.55, y - 0.04, 0.10, "TABLEAU_FERRAILLAGE")
    y -= 0.24

    add_line(msp, x, y, x + 0.40, y, "ARM_INF_Y")
    add_text(msp, "Nappe inferieure Y", x + 0.55, y - 0.04, 0.10, "TABLEAU_FERRAILLAGE")
    y -= 0.24

    add_line(msp, x, y, x + 0.40, y, "ARM_SUP_X")
    add_text(msp, "Nappe superieure X", x + 0.55, y - 0.04, 0.10, "TABLEAU_FERRAILLAGE")
    y -= 0.24

    add_line(msp, x, y, x + 0.40, y, "ARM_SUP_Y")
    add_text(msp, "Nappe superieure Y", x + 0.55, y - 0.04, 0.10, "TABLEAU_FERRAILLAGE")


# =========================================================
# GENERATION
# =========================================================

def generate_reinforcement_dxf(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    reinforcement_report: dict[str, Any],
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

    add_text(msp, "PLAN DE FERRAILLAGE PRELIMINAIRE - CONFIGURATION FINALE", 0.0, title_y, 0.30, "TEXTES")
    add_text(msp, "INGENIERIE.COM - version 0.21.7B annotations et labels hors semelles", 0.0, title_y - 0.40, 0.17, "TEXTES")

    occupied = build_initial_occupied_boxes(
        model=model,
        strategy_report=strategy_report,
        reinforcement_report=reinforcement_report,
    )

    draw_emprise_and_columns(msp, model, strategy_report)
    draw_axes(msp, model)

    # Les IDs de fondations sont aussi placés avec le gestionnaire anti-chevauchement
    draw_final_foundations(msp, strategy_report, occupied)

    # Les annotations Inf/Sup utilisent les zones deja occupees
    draw_reinforcement(msp, strategy_report, reinforcement_report, occupied)

    tx, ty = table_position(model)
    draw_table(msp, reinforcement_report, tx, ty)
    draw_legend(msp, tx, ty - 5.3)

    from civil_engine.plans.dxf_finalize import finalize_and_save
    finalize_and_save(doc, output_path)
    return str(output_path)
