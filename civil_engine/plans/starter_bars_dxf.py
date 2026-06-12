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
        "CADRES_ATTENTES": 6,
        "CADRES_POTEAUX": 2,
        "FORMES_ARMATURES": 4,
        "COUPES": 7,
        "TEXTES": 7,
        "TABLEAU_ATTENTES": 7,
        "NOTA": 1,
        "RENVOIS": 8,
    }

    for name, color in layers.items():
        if name not in doc.layers:
            doc.layers.add(name=name, color=color)


def add_text(msp, text: str, x: float, y: float, height: float = 0.16, layer: str = "TEXTES") -> None:
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


def draw_base(
    msp,
    model: dict[str, Any],
    strategy_report: dict[str, Any],
) -> None:
    foundation = get_foundation_level(model)

    if foundation is None:
        return

    for footprint in foundation.get("footprints", []):
        add_polyline(msp, footprint.get("points", []), "EMPRISE", closed=True)

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

        add_text(
            msp,
            str(element.get("id", "")),
            float(bbox["xmax"]) + 0.15,
            float(bbox["ymax"]) + 0.15,
            0.11,
            layer,
        )


def draw_columns(msp, model: dict[str, Any]) -> None:
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


def starter_points_for_column(
    box: dict[str, float],
    edge_cover_m: float = 0.06,
) -> list[tuple[float, float]]:
    xmin = float(box["xmin"])
    xmax = float(box["xmax"])
    ymin = float(box["ymin"])
    ymax = float(box["ymax"])

    width = xmax - xmin
    height = ymax - ymin

    x1 = xmin + edge_cover_m
    x2 = xmax - edge_cover_m
    y1 = ymin + edge_cover_m
    y2 = ymax - edge_cover_m

    points = [
        (x1, y1),
        (x2, y1),
        (x2, y2),
        (x1, y2),
    ]

    if width >= 0.35:
        points.append(((x1 + x2) / 2.0, y1))
        points.append(((x1 + x2) / 2.0, y2))

    if height >= 0.35:
        points.append((x1, (y1 + y2) / 2.0))
        points.append((x2, (y1 + y2) / 2.0))

    return points


def foundation_id_for_column(
    strategy_report: dict[str, Any],
    column_id: str,
) -> str:
    for element in strategy_report.get("final_foundations", []):
        if column_id in element.get("columns", []):
            return str(element.get("id", "-"))

    return "-"


def draw_starter_bars(
    msp,
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    starter_diameter_mm: float,
) -> list[dict[str, Any]]:
    boxes = get_effective_column_boxes(model)
    rows = []

    r = max(starter_diameter_mm / 1000.0 / 2.0, 0.018)

    for column_id, box in boxes.items():
        points = starter_points_for_column(box)

        for x, y in points:
            add_circle(msp, x, y, r, "ATTENTES")

        xmin = float(box["xmin"])
        xmax = float(box["xmax"])
        ymin = float(box["ymin"])
        ymax = float(box["ymax"])

        # Cadre indicatif des attentes dans le poteau.
        add_rect(
            msp,
            xmin + 0.035,
            ymin + 0.035,
            xmax - 0.035,
            ymax - 0.035,
            "CADRES_ATTENTES",
        )

        label_x = xmax + 0.20
        label_y = ymax + 0.20

        label = f"{column_id} - {len(points)}HA{int(starter_diameter_mm)}"

        add_text(msp, label, label_x, label_y, 0.10, "TEXTES")
        add_line(
            msp,
            (xmin + xmax) / 2.0,
            (ymin + ymax) / 2.0,
            label_x,
            label_y,
            "RENVOIS",
        )

        foundation_id = foundation_id_for_column(strategy_report, column_id)

        rows.append({
            "column_id": column_id,
            "foundation_id": foundation_id,
            "bars_count": len(points),
            "diameter_mm": starter_diameter_mm,
            "label": label,
        })

    return rows


def anchorage_length_m(
    diameter_mm: float,
    factor_phi: float = 50.0,
    minimum_m: float = 0.60,
) -> float:
    return round(max(factor_phi * diameter_mm / 1000.0, minimum_m), 2)


def table_position(model: dict[str, Any]) -> tuple[float, float]:
    bbox = get_foundation_bbox(model)

    if bbox is None:
        return 18.0, 12.0

    return float(bbox["xmax"]) + 5.5, float(bbox["ymax"]) + 2.3



def internal_cadre_dimensions(
    column_box: dict[str, float],
    cover_m: float = 0.05,
) -> tuple[float, float]:
    """
    Dimensions intérieures indicatives du cadre poteau.
    """
    c1 = float(column_box["xmax"]) - float(column_box["xmin"])
    c2 = float(column_box["ymax"]) - float(column_box["ymin"])

    a_int = max(c1 - 2.0 * cover_m, 0.10)
    b_int = max(c2 - 2.0 * cover_m, 0.10)

    return round(a_int, 2), round(b_int, 2)


def spacing_label(
    stirrup_spacing_cm: float,
    stirrup_secondary_spacing_cm: float,
    critical_zone_m: float,
) -> str:
    return (
        f"e={stirrup_spacing_cm:.0f}cm sur {critical_zone_m:.2f}m, "
        f"puis e={stirrup_secondary_spacing_cm:.0f}cm"
    )


def draw_vertical_bar_symbol(
    msp,
    x: float,
    y: float,
    height: float = 0.22,
    layer: str = "FORMES_ARMATURES",
) -> None:
    """
    Petit symbole de barre droite dans le tableau.
    """
    add_line(msp, x, y, x, y + height, layer)
    add_line(msp, x, y + height, x + 0.06, y + height - 0.04, layer)


def draw_rect_stirrup_symbol(
    msp,
    x: float,
    y: float,
    width: float = 0.30,
    height: float = 0.18,
    layer: str = "FORMES_ARMATURES",
) -> None:
    """
    Petit symbole de cadre rectangulaire fermé.
    """
    add_rect(msp, x, y, x + width, y + height, layer)

    # crochets schématiques
    add_line(msp, x + width, y + height, x + width - 0.06, y + height - 0.04, layer)
    add_line(msp, x, y, x + 0.06, y + 0.04, layer)


def draw_stirrups_in_section(
    msp,
    x_left: float,
    x_right: float,
    y_bottom: float,
    y_top: float,
    stirrup_spacing_m: float,
    secondary_spacing_m: float,
    critical_zone_m: float,
) -> None:
    """
    Dessine les cadres dans la coupe du poteau.
    Zone basse serrée, puis zone courante.
    """
    y = y_bottom + 0.08
    y_limit_critical = min(y_bottom + critical_zone_m, y_top - 0.05)

    while y <= y_limit_critical + 1e-9:
        add_line(msp, x_left, y, x_right, y, "CADRES_POTEAUX")
        y += stirrup_spacing_m

    y = max(y, y_limit_critical + secondary_spacing_m)

    while y <= y_top - 0.05 + 1e-9:
        add_line(msp, x_left, y, x_right, y, "CADRES_POTEAUX")
        y += secondary_spacing_m



def draw_table(
    msp,
    model: dict[str, Any],
    rows: list[dict[str, Any]],
    x: float,
    y: float,
    anchorage_m: float,
    stirrup_diameter_mm: float,
    stirrup_spacing_cm: float,
    stirrup_secondary_spacing_cm: float,
    critical_zone_m: float,
) -> None:
    """
    Tableau lisible et organisé :
    - attentes ;
    - forme des attentes ;
    - cadres ;
    - dimensions intérieures ;
    - espacement des cadres.
    """
    column_boxes = get_effective_column_boxes(model)

    add_text(msp, "TABLEAU DES ATTENTES ET CADRES POTEAUX", x, y, 0.22, "TABLEAU_ATTENTES")
    y -= 0.45

    headers = [
        ("POTEAU", 0.0),
        ("FOND", 1.4),
        ("ATTENTES", 2.8),
        ("FORME", 4.6),
        ("Lbd", 5.5),
        ("CADRES", 6.6),
        ("DIM. CADRE", 8.2),
        ("ESPACEMENT CADRES", 10.0),
        ("OBS", 14.0),
    ]

    for title, dx in headers:
        add_text(msp, title, x + dx, y, 0.105, "TABLEAU_ATTENTES")

    y -= 0.30

    for row in rows:
        column_id = row["column_id"]
        box = column_boxes.get(column_id)

        if box is not None:
            a_int, b_int = internal_cadre_dimensions(box)
            dim_cadre = f"{a_int:.2f} x {b_int:.2f} m"
        else:
            dim_cadre = "A verifier"

        att_label = f"{row['bars_count']}HA{int(row['diameter_mm'])}"
        cadre_label = f"HA{int(stirrup_diameter_mm)}"
        espacement = spacing_label(
            stirrup_spacing_cm=stirrup_spacing_cm,
            stirrup_secondary_spacing_cm=stirrup_secondary_spacing_cm,
            critical_zone_m=critical_zone_m,
        )

        values = [
            (column_id, 0.0),
            (row["foundation_id"], 1.4),
            (att_label, 2.8),
            ("Droites", 4.6),
            (f"{anchorage_m:.2f}m", 5.5),
            (cadre_label, 6.6),
            (dim_cadre, 8.2),
            (espacement, 10.0),
            ("Prelim.", 14.0),
        ]

        for value, dx in values:
            add_text(msp, str(value), x + dx, y, 0.085, "TABLEAU_ATTENTES")

        # Symboles de forme dans le tableau
        draw_vertical_bar_symbol(
            msp,
            x + 4.35,
            y - 0.04,
            height=0.18,
            layer="FORMES_ARMATURES",
        )

        draw_rect_stirrup_symbol(
            msp,
            x + 7.55,
            y - 0.04,
            width=0.28,
            height=0.16,
            layer="FORMES_ARMATURES",
        )

        y -= 0.30

    y -= 0.35

    add_text(msp, "LEGENDE DES FORMES", x, y, 0.15, "TABLEAU_ATTENTES")
    y -= 0.25

    draw_vertical_bar_symbol(msp, x, y - 0.03, 0.20, "FORMES_ARMATURES")
    add_text(msp, "Attente droite verticale, ancree dans la fondation", x + 0.35, y, 0.09, "TABLEAU_ATTENTES")
    y -= 0.25

    draw_rect_stirrup_symbol(msp, x, y - 0.03, 0.30, 0.16, "FORMES_ARMATURES")
    add_text(msp, "Cadre ferme rectangulaire avec crochets a verifier selon norme", x + 0.45, y, 0.09, "TABLEAU_ATTENTES")
    y -= 0.35

    add_text(msp, "NOTA", x, y, 0.15, "NOTA")
    y -= 0.22

    add_text(
        msp,
        "Attentes et cadres indicatifs. Dimensions finales selon sections poteaux, efforts, EC2/BAEL, recouvrements et dispositions sismiques.",
        x,
        y,
        0.09,
        "NOTA",
    )

def draw_section_type(
    msp,
    x: float,
    y: float,
    foundation_type: str,
    title: str,
    starter_diameter_mm: float,
    anchorage_m: float,
    stirrup_diameter_mm: float,
    stirrup_spacing_cm: float,
    stirrup_secondary_spacing_cm: float,
    critical_zone_m: float,
) -> None:
    """
    Coupe type schématique avec attentes + cadres + espacements.
    """
    footing_width = 2.80
    footing_h = 0.45
    column_w = 0.45
    column_h = 1.35

    add_text(msp, title, x, y + 1.85, 0.16, "COUPES")

    # Semelle / radier
    add_rect(
        msp,
        x,
        y,
        x + footing_width,
        y + footing_h,
        layer_for_foundation_type(foundation_type),
    )

    # Poteau
    cx = x + footing_width / 2.0
    col_x1 = cx - column_w / 2.0
    col_x2 = cx + column_w / 2.0
    col_y1 = y + footing_h
    col_y2 = y + footing_h + column_h

    add_rect(
        msp,
        col_x1,
        col_y1,
        col_x2,
        col_y2,
        "POTEAUX",
    )

    # Attentes verticales
    bar_x1 = cx - column_w / 4.0
    bar_x2 = cx + column_w / 4.0

    add_line(msp, bar_x1, y + 0.08, bar_x1, col_y2, "ATTENTES")
    add_line(msp, bar_x2, y + 0.08, bar_x2, col_y2, "ATTENTES")

    # Cadres poteaux dans la coupe
    stirrup_spacing_m = stirrup_spacing_cm / 100.0
    secondary_spacing_m = stirrup_secondary_spacing_cm / 100.0

    draw_stirrups_in_section(
        msp=msp,
        x_left=col_x1 + 0.04,
        x_right=col_x2 - 0.04,
        y_bottom=col_y1,
        y_top=col_y2,
        stirrup_spacing_m=stirrup_spacing_m,
        secondary_spacing_m=secondary_spacing_m,
        critical_zone_m=critical_zone_m,
    )

    # Nappe inférieure schématique
    add_line(msp, x + 0.15, y + 0.10, x + footing_width - 0.15, y + 0.10, "CADRES_ATTENTES")

    # Annotations coupe
    tx = x + footing_width + 0.25

    add_text(msp, f"Attentes : HA{int(starter_diameter_mm)}", tx, col_y1 + 0.95, 0.10, "TEXTES")
    add_text(msp, f"Ancrage indicatif Lbd = {anchorage_m:.2f} m", tx, col_y1 + 0.75, 0.10, "TEXTES")

    add_text(
        msp,
        f"Cadres : HA{int(stirrup_diameter_mm)} / e={stirrup_spacing_cm:.0f}cm",
        tx,
        col_y1 + 0.50,
        0.10,
        "TEXTES",
    )

    add_text(
        msp,
        f"Zone serree : {critical_zone_m:.2f} m depuis dessus semelle",
        tx,
        col_y1 + 0.32,
        0.09,
        "TEXTES",
    )

    add_text(
        msp,
        f"Zone courante : e={stirrup_secondary_spacing_cm:.0f}cm",
        tx,
        col_y1 + 0.15,
        0.09,
        "TEXTES",
    )

    add_text(
        msp,
        "Crochets / ancrages a verifier selon norme",
        tx,
        y + 0.05,
        0.085,
        "NOTA",
    )

def draw_sections(
    msp,
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    starter_diameter_mm: float,
    anchorage_m: float,
    stirrup_diameter_mm: float,
    stirrup_spacing_cm: float,
    stirrup_secondary_spacing_cm: float,
    critical_zone_m: float,
) -> None:
    tx, ty = table_position(model)

    x = tx
    y = ty - 8.8

    types_present = []
    for element in strategy_report.get("final_foundations", []):
        ftype = element.get("type")
        if ftype and ftype not in types_present:
            types_present.append(ftype)

    titles = {
        "SI": "COUPE TYPE SI - attentes et cadres",
        "SE": "COUPE TYPE SE - attentes et cadres",
        "SC": "COUPE TYPE SC - attentes et cadres",
        "RL": "COUPE TYPE RL - attentes et cadres",
    }

    for index, ftype in enumerate(types_present):
        draw_section_type(
            msp,
            x=x,
            y=y - index * 2.65,
            foundation_type=ftype,
            title=titles.get(ftype, f"COUPE TYPE {ftype}"),
            starter_diameter_mm=starter_diameter_mm,
            anchorage_m=anchorage_m,
            stirrup_diameter_mm=stirrup_diameter_mm,
            stirrup_spacing_cm=stirrup_spacing_cm,
            stirrup_secondary_spacing_cm=stirrup_secondary_spacing_cm,
            critical_zone_m=critical_zone_m,
        )

def generate_starter_bars_dxf(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    output_path: str | Path,
    starter_diameter_mm: float = 14.0,
    stirrup_diameter_mm: float = 8.0,
    stirrup_spacing_cm: float = 15.0,
    stirrup_secondary_spacing_cm: float = 20.0,
    critical_zone_m: float = 0.60,
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

    add_text(msp, "PLAN DES ATTENTES POTEAUX - CONFIGURATION FINALE", 0.0, title_y, 0.30, "TEXTES")
    add_text(msp, "INGENIERIE.COM - attentes, cadres et coupes types preliminaires", 0.0, title_y - 0.40, 0.17, "TEXTES")

    draw_base(msp, model, strategy_report)
    draw_columns(msp, model)

    rows = draw_starter_bars(
        msp=msp,
        model=model,
        strategy_report=strategy_report,
        starter_diameter_mm=starter_diameter_mm,
    )

    anchorage_m = anchorage_length_m(starter_diameter_mm)

    tx, ty = table_position(model)

    draw_table(
        msp=msp,
        model=model,
        rows=rows,
        x=tx,
        y=ty,
        anchorage_m=anchorage_m,
        stirrup_diameter_mm=stirrup_diameter_mm,
        stirrup_spacing_cm=stirrup_spacing_cm,
        stirrup_secondary_spacing_cm=stirrup_secondary_spacing_cm,
        critical_zone_m=critical_zone_m,
    )

    draw_sections(
        msp=msp,
        model=model,
        strategy_report=strategy_report,
        starter_diameter_mm=starter_diameter_mm,
        anchorage_m=anchorage_m,
        stirrup_diameter_mm=stirrup_diameter_mm,
        stirrup_spacing_cm=stirrup_spacing_cm,
        stirrup_secondary_spacing_cm=stirrup_secondary_spacing_cm,
        critical_zone_m=critical_zone_m,
    )

    doc.saveas(output_path)
    return str(output_path)
