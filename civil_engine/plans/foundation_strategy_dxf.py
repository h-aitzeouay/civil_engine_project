from __future__ import annotations

from pathlib import Path
from typing import Any

import ezdxf

from civil_engine.foundations.column_effective import get_effective_column_boxes, get_effective_column_centers


def ensure_layers(doc) -> None:
    layers = {
        "FONDATION_EMPRISE": 7,
        "POTEAUX": 7,
        "SEMELLES": 3,
        "SEMELLES_EXCENTREES": 30,
        "SEMELLES_COMBINEES": 5,
        "RADIER_LOCAL": 140,
        "RADIER_GENERAL_NOTE": 6,
        "PR": 30,
        "ANCIEN_PLAN": 8,
        "TEXTES": 7,
        "TABLEAU_FONDATIONS": 7,
        "ALERTES": 1,
        "CENTRE_CHARGE": 4,
        "AXES_CONSTRUCTION": 2,
        "COTATIONS_AXES": 4,
    }

    for name, color in layers.items():
        if name not in doc.layers:
            doc.layers.add(name=name, color=color)


def add_text(msp, text: str, x: float, y: float, height: float = 0.20, layer: str = "TEXTES") -> None:
    msp.add_text(text, dxfattribs={"height": height, "layer": layer}).set_placement((x, y))


def add_line(msp, x1: float, y1: float, x2: float, y2: float, layer: str) -> None:
    msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": layer})


def add_rect(msp, xmin: float, ymin: float, xmax: float, ymax: float, layer: str) -> None:
    msp.add_lwpolyline(
        [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)],
        close=True,
        dxfattribs={"layer": layer},
    )


def add_cross(msp, x: float, y: float, size: float, layer: str) -> None:
    add_line(msp, x - size, y, x + size, y, layer)
    add_line(msp, x, y - size, x, y + size, layer)


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


def add_polyline(msp, points: list[list[float]], layer: str, closed: bool = False, dx: float = 0.0, dy: float = 0.0) -> None:
    if len(points) < 2:
        return

    msp.add_lwpolyline(
        [(float(p[0]) + dx, float(p[1]) + dy) for p in points],
        close=closed,
        dxfattribs={"layer": layer},
    )


def fmt(value: Any) -> str:
    if value is None:
        return "-"

    if isinstance(value, float):
        return f"{value:.2f}"

    return str(value)


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
        "xmin": min(xs),
        "xmax": max(xs),
        "ymin": min(ys),
        "ymax": max(ys),
    }


def get_offsets(model: dict[str, Any]) -> dict[str, float]:
    bbox = get_foundation_bbox(model)

    if bbox is None:
        return {
            "old_dx": 22.0,
            "table_x": 46.0,
            "title_y": 13.0,
        }

    width = float(bbox["xmax"]) - float(bbox["xmin"])

    return {
        "old_dx": width + 5.0,
        "table_x": 2.0 * width + 10.0,
        "title_y": float(bbox["ymax"]) + 2.5,
    }


def draw_columns_and_emprise(
    msp,
    model: dict[str, Any],
    dx: float = 0.0,
    dy: float = 0.0,
    old: bool = False,
    *args,
    **kwargs,
) -> None:
    foundation = get_foundation_level(model)

    if foundation is None:
        return

    emprise_layer = "ANCIEN_PLAN" if old else "FONDATION_EMPRISE"
    poteaux_layer = "ANCIEN_PLAN" if old else "POTEAUX"

    for footprint in foundation.get("footprints", []):
        add_polyline(
            msp,
            footprint.get("points", []),
            emprise_layer,
            True,
            dx,
            dy,
        )

    boxes = get_effective_column_boxes(model)

    for column_id, box in boxes.items():
        add_rect(
            msp,
            float(box["xmin"]) + dx,
            float(box["ymin"]) + dy,
            float(box["xmax"]) + dx,
            float(box["ymax"]) + dy,
            poteaux_layer,
        )

        add_text(
            msp,
            column_id,
            float(box["xmax"]) + dx + 0.08,
            float(box["ymax"]) + dy + 0.08,
            0.10 if not old else 0.09,
            poteaux_layer,
        )


def draw_element_label(msp, element: dict[str, Any], layer: str) -> None:
    """
    Place le texte de la fondation hors de son rectangle
    pour éviter le chevauchement avec le texte du poteau.
    """
    bbox = element["bbox"]
    element_type = element.get("type", "")

    xmin = float(bbox["xmin"])
    xmax = float(bbox["xmax"])
    ymin = float(bbox["ymin"])
    ymax = float(bbox["ymax"])

    width = xmax - xmin
    height = ymax - ymin

    # Décalage de base
    dx = 0.10
    dy = 0.12

    # Par défaut : en haut à droite, hors rectangle
    x = xmax + dx
    y = ymax + dy

    # Cas des grands radiers : on écrit plutôt au-dessus à gauche
    if element_type == "RL":
        x = xmin + 0.10
        y = ymax + 0.18

    # Cas des semelles combinées : au-dessus à droite
    elif element_type == "SC":
        x = xmax + 0.10
        y = ymax + 0.10

    # Cas des semelles excentrées / isolées : légèrement décalées
    elif element_type in ("SI", "SE"):
        x = xmax + 0.08
        y = ymax + 0.08

    add_text(
        msp,
        element["id"],
        x,
        y,
        0.12,
        layer,
    )


def draw_final_base(msp, model: dict[str, Any], title_y: float) -> None:
    add_text(msp, "PLAN FINAL FONDATIONS", 0.0, title_y, 0.30, "TEXTES")
    add_text(msp, "INGENIERIE.COM - solution finale lisible, sans chevauchement", 0.0, title_y - 0.40, 0.17, "TEXTES")
    draw_columns_and_emprise(msp, model, 0.0, 0.0, False)


def draw_final_foundations(msp, strategy_report: dict[str, Any]) -> None:
    for element in strategy_report.get("final_foundations", []):
        element_type = element.get("type", "")
        bbox = element["bbox"]

        if element.get("status") != "OK_PRELIMINARY":
            x = float(element["cx"])
            y = float(element["cy"])
            add_cross(msp, x, y, 0.30, "ALERTES")
            add_text(msp, element["id"] + " ALT", x + 0.20, y + 0.20, 0.12, "ALERTES")
            continue

        if element_type == "SI":
            layer = "SEMELLES"
        elif element_type == "SE":
            layer = "SEMELLES_EXCENTREES"
        elif element_type == "SC":
            layer = "SEMELLES_COMBINEES"
        elif element_type == "RL":
            layer = "RADIER_LOCAL"
        else:
            layer = "ALERTES"

        add_rect(
            msp,
            float(bbox["xmin"]),
            float(bbox["ymin"]),
            float(bbox["xmax"]),
            float(bbox["ymax"]),
            layer,
        )

        add_cross(msp, float(element["cx"]), float(element["cy"]), 0.18, "CENTRE_CHARGE")
        draw_element_label(msp, element, layer)


def draw_old_plan(
    msp,
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    dx: float,
    dy: float,
    title_y: float,
) -> None:
    add_text(msp, "ANCIEN PLAN / SEMELLES INITIALES", dx, title_y, 0.23, "ANCIEN_PLAN")

    draw_columns_and_emprise(msp, model, dx, dy, True)

    footings = strategy_report.get("isolated_report", {}).get("footings", [])

    for footing in footings:
        bbox = footing["bbox"]

        add_dashed_rect(
            msp,
            float(bbox["xmin"]) + dx,
            float(bbox["ymin"]) + dy,
            float(bbox["xmax"]) + dx,
            float(bbox["ymax"]) + dy,
            "ANCIEN_PLAN",
        )

        cx = float(footing.get("footing_cx", footing["cx"])) + dx
        cy = float(footing.get("footing_cy", footing["cy"])) + dy

        add_text(
            msp,
            footing["id"],
            cx + 0.08,
            cy + 0.08,
            0.10,
            "ANCIEN_PLAN",
        )


def draw_table(msp, strategy_report: dict[str, Any], x: float, y: float) -> None:
    add_text(msp, "TABLEAU DES FONDATIONS", x, y, 0.25, "TABLEAU_FONDATIONS")
    y -= 0.45

    headers = [
        ("ID", 0.0),
        ("TYPE", 2.2),
        ("A", 3.8),
        ("B", 5.0),
        ("H", 6.2),
        ("qELS", 7.4),
        ("OBS", 9.0),
    ]

    for label, offset in headers:
        add_text(msp, label, x + offset, y, 0.13, "TABLEAU_FONDATIONS")

    y -= 0.28

    for element in strategy_report.get("final_foundations", []):
        obs = element.get("note", "")

        if element.get("status") != "OK_PRELIMINARY":
            obs = "alternative"

        values = [
            (element.get("id"), 0.0),
            (element.get("type"), 2.2),
            (fmt(element.get("A_m")), 3.8),
            (fmt(element.get("B_m")), 5.0),
            (fmt(element.get("H_m")), 6.2),
            (fmt(element.get("soil_pressure_ELS_kPa")), 7.4),
            (obs[:22], 9.0),
        ]

        for value, offset in values:
            add_text(msp, str(value), x + offset, y, 0.105, "TABLEAU_FONDATIONS")

        y -= 0.23

    y -= 0.35

    add_text(msp, "NOTA", x, y, 0.16, "ALERTES")
    y -= 0.25

    add_text(
        msp,
        "Radier general : possibilite a etudier selon tassements, poinconnement et ratio de couverture.",
        x,
        y,
        0.105,
        "RADIER_GENERAL_NOTE",
    )

    y -= 0.23

    add_text(
        msp,
        "Les dimensions A/B/H sont preliminaires et a verifier par note de calcul.",
        x,
        y,
        0.105,
        "ALERTES",
    )




def add_circle(msp, x: float, y: float, radius: float, layer: str) -> None:
    msp.add_circle(
        center=(x, y),
        radius=radius,
        dxfattribs={"layer": layer},
    )


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


def axis_label(index: int) -> str:
    """
    Convertit 0,1,2... en A,B,C...
    """
    letters = ""
    number = index

    while True:
        letters = chr(ord("A") + number % 26) + letters
        number = number // 26 - 1

        if number < 0:
            break

    return letters


def unique_sorted(values: list[float], tolerance: float = 0.20) -> list[float]:
    """
    Regroupe les coordonnées proches pour retrouver les axes.
    """
    if not values:
        return []

    values = sorted(values)
    groups: list[list[float]] = []

    for value in values:
        if not groups:
            groups.append([value])
            continue

        current_avg = sum(groups[-1]) / len(groups[-1])

        if abs(value - current_avg) <= tolerance:
            groups[-1].append(value)
        else:
            groups.append([value])

    return [
        round(sum(group) / len(group), 4)
        for group in groups
    ]


def extract_axes_from_columns(model: dict[str, Any]) -> tuple[list[float], list[float]]:
    foundation = get_foundation_level(model)

    if foundation is None:
        return [], []

    xs = []
    ys = []

    for column in foundation.get("columns", []):
        xs.append(float(column["cx"]))
        ys.append(float(column["cy"]))

    axes_x = unique_sorted(xs, tolerance=0.20)
    axes_y = unique_sorted(ys, tolerance=0.20)

    return axes_x, axes_y


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
    """
    Cotation simple entre deux axes.
    """
    add_line(msp, x1, y1, x2, y2, layer)

    tick = 0.12

    if vertical:
        add_line(msp, x1 - tick, y1, x1 + tick, y1, layer)
        add_line(msp, x2 - tick, y2, x2 + tick, y2, layer)

        add_text_rotated(
            msp,
            text,
            x1 - 0.38,
            (y1 + y2) / 2.0,
            0.12,
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
            y1 - 0.28,
            0.12,
            layer,
        )



def draw_construction_axes(msp, model: dict[str, Any]) -> None:
    """
    Axes de construction du plan final.

    Convention retenue :
    - axes verticaux suivant X : bulles numerotees 1, 2, 3...
    - axes horizontaux suivant Y : bulles alphabetiques A, B, C...
    """
    bbox = get_foundation_bbox(model)

    if bbox is None:
        return

    axes_x, axes_y = extract_axes_from_columns(model)

    if not axes_x or not axes_y:
        return

    xmin = float(bbox["xmin"])
    xmax = float(bbox["xmax"])
    ymin = float(bbox["ymin"])
    ymax = float(bbox["ymax"])

    extension = 0.65
    bubble_radius = 0.18

    y_bottom_bubble = ymin - 0.55
    y_top_bubble = ymax + 0.55

    x_left_bubble = xmin - 0.55
    x_right_bubble = xmax + 0.55

    # Axes verticaux numerotes
    for index, x in enumerate(axes_x, start=1):
        # segment principal sans traverser les bulles
        add_dashed_line(
            msp,
            x,
            y_bottom_bubble + bubble_radius,
            x,
            y_top_bubble - bubble_radius,
            "AXES_CONSTRUCTION",
        )

        label = str(index)

        # bulle basse
        add_circle(msp, x, y_bottom_bubble, bubble_radius, "AXES_CONSTRUCTION")
        add_text(
            msp,
            label,
            x - 0.05,
            y_bottom_bubble - 0.06,
            0.12,
            "AXES_CONSTRUCTION",
        )

        # petit trait de liaison entre bulle et axe
        add_line(
            msp,
            x,
            y_bottom_bubble + bubble_radius,
            x,
            y_bottom_bubble + bubble_radius + 0.10,
            "AXES_CONSTRUCTION",
        )

        # bulle haute
        add_circle(msp, x, y_top_bubble, bubble_radius, "AXES_CONSTRUCTION")
        add_text(
            msp,
            label,
            x - 0.05,
            y_top_bubble - 0.06,
            0.12,
            "AXES_CONSTRUCTION",
        )

        # petit trait de liaison entre axe et bulle
        add_line(
            msp,
            x,
            y_top_bubble - bubble_radius - 0.10,
            x,
            y_top_bubble - bubble_radius,
            "AXES_CONSTRUCTION",
        )

    # Axes horizontaux alphabetiques
    for index, y in enumerate(axes_y):
        label = axis_label(index)

        # segment principal sans traverser les bulles
        add_dashed_line(
            msp,
            x_left_bubble + bubble_radius,
            y,
            x_right_bubble - bubble_radius,
            y,
            "AXES_CONSTRUCTION",
        )

        # bulle gauche
        add_circle(msp, x_left_bubble, y, bubble_radius, "AXES_CONSTRUCTION")
        add_text(
            msp,
            label,
            x_left_bubble - 0.05,
            y - 0.06,
            0.12,
            "AXES_CONSTRUCTION",
        )

        add_line(
            msp,
            x_left_bubble + bubble_radius,
            y,
            x_left_bubble + bubble_radius + 0.10,
            y,
            "AXES_CONSTRUCTION",
        )

        # bulle droite
        add_circle(msp, x_right_bubble, y, bubble_radius, "AXES_CONSTRUCTION")
        add_text(
            msp,
            label,
            x_right_bubble - 0.05,
            y - 0.06,
            0.12,
            "AXES_CONSTRUCTION",
        )

        add_line(
            msp,
            x_right_bubble - bubble_radius - 0.10,
            y,
            x_right_bubble - bubble_radius,
            y,
            "AXES_CONSTRUCTION",
        )

    # Cotations horizontales entre axes X
    dim_y = ymin - 1.05

    for i in range(len(axes_x) - 1):
        distance = axes_x[i + 1] - axes_x[i]

        add_dimension_segment(
            msp,
            axes_x[i],
            dim_y,
            axes_x[i + 1],
            dim_y,
            f"{distance:.2f}",
            "COTATIONS_AXES",
            vertical=False,
        )

    # Cote totale horizontale
    total_dim_y = ymin - 1.45
    add_dimension_segment(
        msp,
        axes_x[0],
        total_dim_y,
        axes_x[-1],
        total_dim_y,
        f"{axes_x[-1] - axes_x[0]:.2f}",
        "COTATIONS_AXES",
        vertical=False,
    )

    # Cotations verticales entre axes Y
    dim_x = xmin - 1.05

    for i in range(len(axes_y) - 1):
        distance = axes_y[i + 1] - axes_y[i]

        add_dimension_segment(
            msp,
            dim_x,
            axes_y[i],
            dim_x,
            axes_y[i + 1],
            f"{distance:.2f}",
            "COTATIONS_AXES",
            vertical=True,
        )

    # Cote totale verticale
    total_dim_x = xmin - 1.45
    add_dimension_segment(
        msp,
        total_dim_x,
        axes_y[0],
        total_dim_x,
        axes_y[-1],
        f"{axes_y[-1] - axes_y[0]:.2f}",
        "COTATIONS_AXES",
        vertical=True,
    )


def generate_foundation_strategy_dxf(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    output_path: str | Path,
) -> str:
    output_path = Path(output_path)

    doc = ezdxf.new("R2010")
    doc.units = 6
    ensure_layers(doc)

    msp = doc.modelspace()

    offsets = get_offsets(model)
    old_dx = offsets["old_dx"]
    table_x = offsets["table_x"]
    title_y = offsets["title_y"]

    draw_final_base(msp, model, title_y)
    draw_construction_axes(msp, model)
    draw_final_foundations(msp, strategy_report)

    draw_old_plan(
        msp=msp,
        model=model,
        strategy_report=strategy_report,
        dx=old_dx,
        dy=0.0,
        title_y=title_y,
    )

    draw_table(
        msp=msp,
        strategy_report=strategy_report,
        x=table_x,
        y=title_y,
    )

    from civil_engine.plans.dxf_finalize import finalize_and_save
    finalize_and_save(doc, output_path)
    return str(output_path)
