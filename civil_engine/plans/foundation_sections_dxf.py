from __future__ import annotations

from pathlib import Path
from typing import Any

import ezdxf


def ensure_layers(doc) -> None:
    layers = {
        "COUPES": 7,
        "BETON": 3,
        "BETON_PROPRETE": 8,
        "SOL": 94,
        "POTEAUX": 7,
        "ARM_INF": 5,
        "ARM_SUP": 1,
        "ATTENTES": 1,
        "CADRES": 2,
        "COTATIONS": 4,
        "TEXTES": 7,
        "TABLEAU_COUPES": 7,
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


def add_text_rotated(
    msp,
    text: str,
    x: float,
    y: float,
    height: float = 0.11,
    layer: str = "TEXTES",
    rotation: float = 90.0,
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


def add_circle(msp, x: float, y: float, r: float, layer: str) -> None:
    msp.add_circle((x, y), r, dxfattribs={"layer": layer})


def fmt(value: Any) -> str:
    if value is None:
        return "-"

    if isinstance(value, float):
        return f"{value:.2f}"

    return str(value)


def get_reinf_item(
    reinforcement_report: dict[str, Any],
    foundation_id: str,
) -> dict[str, Any] | None:
    for item in reinforcement_report.get("results", []):
        if item.get("foundation_id") == foundation_id:
            return item

    return None


def get_reinf_label(
    reinf_item: dict[str, Any] | None,
    key: str,
) -> str:
    if reinf_item is None:
        return "-"

    return str(
        reinf_item.get("reinforcement", {})
        .get(key, {})
        .get("proposal", {})
        .get("label", "-")
    )


def get_anchorage_for_foundation(
    anchorage_report: dict[str, Any],
    foundation_id: str,
) -> dict[str, Any] | None:
    for row in anchorage_report.get("rows", []):
        if row.get("foundation_id") == foundation_id:
            return row

    return None


def type_title(ftype: str) -> str:
    titles = {
        "SI": "COUPE DETAILLEE - SEMELLE ISOLEE",
        "SE": "COUPE DETAILLEE - SEMELLE EXCENTREE",
        "SC": "COUPE DETAILLEE - SEMELLE COMBINEE",
        "RL": "COUPE DETAILLEE - RADIER LOCAL",
    }

    return titles.get(ftype, f"COUPE DETAILLEE - {ftype}")


def section_width_for_type(ftype: str, A_m: float | None, B_m: float | None) -> float:
    base = max(float(A_m or 2.0), float(B_m or 2.0))

    if ftype == "SC":
        return max(base, 4.20)

    if ftype == "RL":
        return max(base, 4.80)

    return max(base, 2.40)


def draw_dimension_vertical(
    msp,
    x: float,
    y1: float,
    y2: float,
    label: str,
) -> None:
    add_line(msp, x, y1, x, y2, "COTATIONS")
    add_line(msp, x - 0.08, y1, x + 0.08, y1, "COTATIONS")
    add_line(msp, x - 0.08, y2, x + 0.08, y2, "COTATIONS")
    add_text_rotated(msp, label, x - 0.20, (y1 + y2) / 2.0 - 0.10, 0.10, "COTATIONS", 90.0)


def draw_dimension_horizontal(
    msp,
    x1: float,
    x2: float,
    y: float,
    label: str,
) -> None:
    add_line(msp, x1, y, x2, y, "COTATIONS")
    add_line(msp, x1, y - 0.08, x1, y + 0.08, "COTATIONS")
    add_line(msp, x2, y - 0.08, x2, y + 0.08, "COTATIONS")
    add_text(msp, label, (x1 + x2) / 2.0 - 0.18, y - 0.22, 0.10, "COTATIONS")


def draw_soil_hatch(msp, x1: float, x2: float, y: float) -> None:
    add_line(msp, x1, y, x2, y, "SOL")

    step = 0.25
    x = x1

    while x < x2:
        add_line(msp, x, y, x + 0.12, y - 0.10, "SOL")
        x += step


def draw_bars_as_circles(
    msp,
    x1: float,
    x2: float,
    y: float,
    spacing: float,
    radius: float,
    layer: str,
) -> None:
    x = x1

    while x <= x2 + 1e-9:
        add_circle(msp, x, y, radius, layer)
        x += spacing


def draw_stirrups(
    msp,
    x1: float,
    x2: float,
    y1: float,
    y2: float,
    spacing: float,
) -> None:
    y = y1

    while y <= y2 + 1e-9:
        add_line(msp, x1, y, x2, y, "CADRES")
        y += spacing



def add_multiline_note(
    msp,
    lines: list[str],
    x: float,
    y: float,
    height: float = 0.10,
    line_spacing: float = 0.20,
    layer: str = "TEXTES",
) -> None:
    """
    Ecriture organisée : une ligne par information.
    Evite les superpositions dans les coupes.
    """
    for index, line in enumerate(lines):
        add_text(
            msp,
            line,
            x,
            y - index * line_spacing,
            height,
            layer,
        )


def draw_leader(
    msp,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    layer: str = "COTATIONS",
) -> None:
    add_line(msp, x1, y1, x2, y2, layer)


def draw_hooked_bar_135(
    msp,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    layer: str,
    hook_len: float = 0.22,
    hook_angle: str = "up",
) -> None:
    """
    Barre en plan avec petits retours/crochets schématiques à 135°.

    hook_angle:
    - up   : crochet vers le haut ;
    - down : crochet vers le bas.
    """
    add_line(msp, x1, y1, x2, y2, layer)

    sign = 1.0 if hook_angle == "up" else -1.0

    # Crochet gauche 135° schématique
    add_line(
        msp,
        x1,
        y1,
        x1 + hook_len * 0.70,
        y1 + sign * hook_len * 0.70,
        layer,
    )

    # Crochet droit 135° schématique
    add_line(
        msp,
        x2,
        y2,
        x2 - hook_len * 0.70,
        y2 + sign * hook_len * 0.70,
        layer,
    )


def draw_top_rebar_hook_view(
    msp,
    x: float,
    y: float,
    element: dict[str, Any],
    reinf_item: dict[str, Any] | None,
    view_scale: float = 0.65,
) -> None:
    """
    Vue en plan schématique des nappes avec crochets à 135°.

    - Nappe inférieure : ARM_INF
    - Nappe supérieure : ARM_SUP
    - Crochets 135° montrés aux extrémités des barres longitudinales
    """
    fid = str(element.get("id", "-"))
    ftype = str(element.get("type", "-"))

    A_m = float(element.get("A_m") or 2.40)
    B_m = float(element.get("B_m") or 2.40)

    # Dimensions graphiques limitées pour garder une lecture claire
    w = max(1.80, min(A_m * view_scale, 3.40))
    h = max(1.20, min(B_m * view_scale, 2.40))

    add_text(msp, f"VUE EN PLAN ANCRAGES 135° - {fid}", x, y + h + 0.45, 0.13, "COUPES")

    add_rect(msp, x, y, x + w, y + h, "BETON")

    inf_x = get_reinf_label(reinf_item, "bottom_bars_X")
    inf_y = get_reinf_label(reinf_item, "bottom_bars_Y")
    sup_x = get_reinf_label(reinf_item, "top_bars_X")
    sup_y = get_reinf_label(reinf_item, "top_bars_Y")

    # Nappe inférieure : barres horizontales avec crochets vers haut
    y_inf_1 = y + 0.28
    y_inf_2 = y + 0.48

    draw_hooked_bar_135(
        msp,
        x + 0.25,
        y_inf_1,
        x + w - 0.25,
        y_inf_1,
        "ARM_INF",
        hook_len=0.22,
        hook_angle="up",
    )

    draw_hooked_bar_135(
        msp,
        x + 0.25,
        y_inf_2,
        x + w - 0.25,
        y_inf_2,
        "ARM_INF",
        hook_len=0.22,
        hook_angle="up",
    )

    # Nappe supérieure : barres horizontales avec crochets vers bas
    y_sup_1 = y + h - 0.30
    y_sup_2 = y + h - 0.50

    draw_hooked_bar_135(
        msp,
        x + 0.25,
        y_sup_1,
        x + w - 0.25,
        y_sup_1,
        "ARM_SUP",
        hook_len=0.22,
        hook_angle="down",
    )

    draw_hooked_bar_135(
        msp,
        x + 0.25,
        y_sup_2,
        x + w - 0.25,
        y_sup_2,
        "ARM_SUP",
        hook_len=0.22,
        hook_angle="down",
    )

    # Barres transversales schématiques
    x_mid_1 = x + 0.45
    x_mid_2 = x + w - 0.45

    add_line(msp, x_mid_1, y + 0.20, x_mid_1, y + h - 0.20, "ARM_INF")
    add_line(msp, x_mid_2, y + 0.20, x_mid_2, y + h - 0.20, "ARM_SUP")

    # Légende propre hors vue
    legend_x = x + w + 0.35
    legend_y = y + h - 0.10

    add_multiline_note(
        msp,
        [
            f"Type : {ftype}",
            f"Inf X : {inf_x}",
            f"Inf Y : {inf_y}",
            f"Sup X : {sup_x}",
            f"Sup Y : {sup_y}",
            "Crochets 135° schematiques",
            "Ancrages a verifier selon EC2/BAEL",
        ],
        legend_x,
        legend_y,
        height=0.085,
        line_spacing=0.17,
        layer="TEXTES",
    )


def section_annotation_blocks(
    ftype: str,
    footing_x1: float,
    footing_x2: float,
    footing_y1: float,
    footing_y2: float,
    col_y1: float,
    col_y2: float,
) -> dict[str, tuple[float, float]]:
    """
    Positions fixes mais hors béton, hors semelle et hors poteau.
    Elles sont suffisamment espacées verticalement.
    """
    right_x = footing_x2 + 0.45
    left_x = footing_x1
    below_y = footing_y1 - 0.45
    above_y = col_y2 + 0.05

    return {
        "right_main": (right_x, col_y2 - 0.05),
        "right_secondary": (right_x, col_y1 + 0.40),
        "bottom_rebar": (left_x, below_y),
        "top_rebar": (left_x, footing_y2 + 0.55),
        "top_view": (footing_x2 + 4.20, footing_y1 - 0.10),
    }


def draw_section_for_element(
    msp,
    element: dict[str, Any],
    reinforcement_report: dict[str, Any],
    anchorage_report: dict[str, Any],
    x: float,
    y: float,
    cover_m: float,
    clean_concrete_m: float,
    starter_diameter_mm: float,
    stirrup_diameter_mm: float,
    stirrup_spacing_cm: float,
    stirrup_secondary_spacing_cm: float,
    critical_zone_m: float,
) -> dict[str, Any]:
    fid = str(element.get("id", "-"))
    ftype = str(element.get("type", "-"))

    A_m = element.get("A_m")
    B_m = element.get("B_m")
    H_m = float(element.get("H_m", 0.35))

    section_width = section_width_for_type(ftype, A_m, B_m)

    footing_x1 = x
    footing_x2 = x + section_width
    footing_y1 = y
    footing_y2 = y + H_m

    clean_y1 = y - clean_concrete_m
    clean_y2 = y

    column_w = 0.40
    column_h = 1.45
    cx = (footing_x1 + footing_x2) / 2.0

    col_x1 = cx - column_w / 2.0
    col_x2 = cx + column_w / 2.0
    col_y1 = footing_y2
    col_y2 = footing_y2 + column_h

    reinf_item = get_reinf_item(reinforcement_report, fid)
    anch_item = get_anchorage_for_foundation(anchorage_report, fid)

    inf_x = get_reinf_label(reinf_item, "bottom_bars_X")
    inf_y = get_reinf_label(reinf_item, "bottom_bars_Y")
    sup_x = get_reinf_label(reinf_item, "top_bars_X")
    sup_y = get_reinf_label(reinf_item, "top_bars_Y")

    lbd = "-"
    l0 = "-"
    shape = "-"

    if anch_item is not None:
        lbd = fmt(anch_item.get("anchorage", {}).get("Lbd_m"))
        l0 = fmt(anch_item.get("anchorage", {}).get("lap_L0_m"))
        shape = str(anch_item.get("anchorage", {}).get("recommended_shape", "-"))

    pos = section_annotation_blocks(
        ftype=ftype,
        footing_x1=footing_x1,
        footing_x2=footing_x2,
        footing_y1=footing_y1,
        footing_y2=footing_y2,
        col_y1=col_y1,
        col_y2=col_y2,
    )

    add_text(msp, f"{type_title(ftype)} : {fid}", x, col_y2 + 0.55, 0.18, "COUPES")

    # Sol + béton de propreté
    draw_soil_hatch(msp, footing_x1 - 0.40, footing_x2 + 0.40, clean_y1 - 0.05)

    add_rect(
        msp,
        footing_x1,
        clean_y1,
        footing_x2,
        clean_y2,
        "BETON_PROPRETE",
    )

    # Semelle / radier
    add_rect(msp, footing_x1, footing_y1, footing_x2, footing_y2, "BETON")

    # Poteau
    add_rect(msp, col_x1, col_y1, col_x2, col_y2, "POTEAUX")

    # Armatures inférieures
    y_inf = footing_y1 + cover_m

    draw_bars_as_circles(
        msp,
        footing_x1 + 0.20,
        footing_x2 - 0.20,
        y_inf,
        0.22,
        0.025,
        "ARM_INF",
    )

    add_line(msp, footing_x1 + 0.15, y_inf, footing_x2 - 0.15, y_inf, "ARM_INF")

    # Armatures supérieures
    y_sup = footing_y2 - cover_m

    if ftype in ["SC", "RL", "SE"]:
        draw_bars_as_circles(
            msp,
            footing_x1 + 0.45,
            footing_x2 - 0.45,
            y_sup,
            0.25,
            0.020,
            "ARM_SUP",
        )

        add_line(msp, footing_x1 + 0.35, y_sup, footing_x2 - 0.35, y_sup, "ARM_SUP")
    else:
        # Pour SI : nappe sup locale représentée discrètement près du poteau
        draw_bars_as_circles(
            msp,
            col_x1 - 0.20,
            col_x2 + 0.20,
            y_sup,
            0.20,
            0.018,
            "ARM_SUP",
        )

    # Attentes
    starter_r = max(starter_diameter_mm / 1000.0 / 2.0, 0.018)

    starter_xs = [
        col_x1 + 0.08,
        col_x2 - 0.08,
    ]

    for sx in starter_xs:
        add_line(msp, sx, footing_y1 + 0.08, sx, col_y2, "ATTENTES")
        add_circle(msp, sx, footing_y1 + 0.08, starter_r, "ATTENTES")

    # Cadres poteau
    stirrup_spacing_m = stirrup_spacing_cm / 100.0
    secondary_spacing_m = stirrup_secondary_spacing_cm / 100.0

    y_start = col_y1 + 0.08
    y_critical = min(col_y1 + critical_zone_m, col_y2 - 0.05)

    draw_stirrups(
        msp,
        col_x1 + 0.04,
        col_x2 - 0.04,
        y_start,
        y_critical,
        stirrup_spacing_m,
    )

    draw_stirrups(
        msp,
        col_x1 + 0.04,
        col_x2 - 0.04,
        y_critical + secondary_spacing_m,
        col_y2 - 0.05,
        secondary_spacing_m,
    )

    # =====================================================
    # ANNOTATIONS PROPRES HORS SEMELLE
    # =====================================================

    bx, by = pos["bottom_rebar"]
    add_multiline_note(
        msp,
        [
            f"Nappe inf. X : {inf_x}",
            f"Nappe inf. Y : {inf_y}",
        ],
        bx,
        by,
        height=0.10,
        line_spacing=0.20,
        layer="TEXTES",
    )

    draw_leader(msp, bx + 0.20, by + 0.08, footing_x1 + 0.35, y_inf, "COTATIONS")

    tx, ty = pos["top_rebar"]
    add_multiline_note(
        msp,
        [
            f"Nappe sup. X : {sup_x}",
            f"Nappe sup. Y : {sup_y}",
        ],
        tx,
        ty,
        height=0.10,
        line_spacing=0.20,
        layer="TEXTES",
    )

    draw_leader(msp, tx + 0.20, ty - 0.05, col_x1, y_sup, "COTATIONS")

    rx, ry = pos["right_main"]
    add_multiline_note(
        msp,
        [
            f"Attentes HA{int(starter_diameter_mm)}",
            f"Lbd = {lbd} m",
            f"L0 = {l0} m",
            f"Forme : {shape}",
        ],
        rx,
        ry,
        height=0.10,
        line_spacing=0.20,
        layer="TEXTES",
    )

    r2x, r2y = pos["right_secondary"]
    add_multiline_note(
        msp,
        [
            f"Cadres HA{int(stirrup_diameter_mm)}",
            f"e = {stirrup_spacing_cm:.0f} cm sur {critical_zone_m:.2f} m",
            f"puis e = {stirrup_secondary_spacing_cm:.0f} cm",
            f"Enrobage c = {cover_m:.2f} m",
            f"Béton propreté = {clean_concrete_m:.2f} m",
        ],
        r2x,
        r2y,
        height=0.095,
        line_spacing=0.18,
        layer="TEXTES",
    )

    draw_leader(msp, r2x - 0.10, r2y - 0.10, col_x2, col_y1 + 0.30, "COTATIONS")

    # Cotations
    draw_dimension_vertical(
        msp,
        footing_x1 - 0.35,
        footing_y1,
        footing_y2,
        f"H={H_m:.2f}",
    )

    draw_dimension_vertical(
        msp,
        footing_x1 - 0.70,
        clean_y1,
        clean_y2,
        f"{clean_concrete_m:.2f}",
    )

    draw_dimension_horizontal(
        msp,
        footing_x1,
        footing_x2,
        clean_y1 - 0.30,
        f"Largeur coupe {section_width:.2f} m",
    )

    # Vue en plan avec crochets 135° pour les nappes
    vx, vy = pos["top_view"]

    draw_top_rebar_hook_view(
        msp=msp,
        x=vx,
        y=vy,
        element=element,
        reinf_item=reinf_item,
        view_scale=0.65,
    )

    return {
        "foundation_id": fid,
        "type": ftype,
        "A_m": A_m,
        "B_m": B_m,
        "H_m": H_m,
        "inf_x": inf_x,
        "inf_y": inf_y,
        "sup_x": sup_x,
        "sup_y": sup_y,
        "lbd": lbd,
        "l0": l0,
    }

def representative_elements_by_type(strategy_report: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    seen = set()

    for element in strategy_report.get("final_foundations", []):
        ftype = element.get("type")

        if not ftype or ftype in seen:
            continue

        result.append(element)
        seen.add(ftype)

    return result


def draw_summary_table(
    msp,
    rows: list[dict[str, Any]],
    x: float,
    y: float,
) -> None:
    add_text(msp, "TABLEAU RECAPITULATIF DES COUPES", x, y, 0.20, "TABLEAU_COUPES")
    y -= 0.42

    headers = [
        ("FOND", 0.0),
        ("TYPE", 1.5),
        ("A", 2.6),
        ("B", 3.5),
        ("H", 4.4),
        ("INF X", 5.4),
        ("INF Y", 8.0),
        ("SUP X", 10.6),
        ("SUP Y", 13.2),
    ]

    for title, dx in headers:
        add_text(msp, title, x + dx, y, 0.10, "TABLEAU_COUPES")

    y -= 0.25

    for row in rows:
        values = [
            (row["foundation_id"], 0.0),
            (row["type"], 1.5),
            (fmt(row["A_m"]), 2.6),
            (fmt(row["B_m"]), 3.5),
            (fmt(row["H_m"]), 4.4),
            (row["inf_x"], 5.4),
            (row["inf_y"], 8.0),
            (row["sup_x"], 10.6),
            (row["sup_y"], 13.2),
        ]

        for value, dx in values:
            add_text(msp, str(value), x + dx, y, 0.08, "TABLEAU_COUPES")

        y -= 0.22

    y -= 0.30
    add_text(msp, "NOTA", x, y, 0.14, "NOTA")
    y -= 0.20
    add_text(
        msp,
        "Coupes types schematiques. Les longueurs, enrobages, ancrages et recouvrements doivent etre verifies selon la note finale.",
        x,
        y,
        0.09,
        "NOTA",
    )


def generate_foundation_sections_dxf(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    reinforcement_report: dict[str, Any],
    anchorage_report: dict[str, Any],
    output_path: str | Path,
    cover_m: float = 0.05,
    clean_concrete_m: float = 0.10,
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

    add_text(msp, "COUPES DETAILLEES DES FONDATIONS - CONFIGURATION FINALE", 0.0, 16.0, 0.30, "TEXTES")
    add_text(msp, "INGENIERIE.COM - SI / SE / SC / RL - version 0.26.1 anti-chevauchement + crochets 135°", 0.0, 15.55, 0.17, "TEXTES")

    elements = representative_elements_by_type(strategy_report)

    rows = []

    x0 = 0.0
    y0 = 11.0

    for index, element in enumerate(elements):
        row = draw_section_for_element(
            msp=msp,
            element=element,
            reinforcement_report=reinforcement_report,
            anchorage_report=anchorage_report,
            x=x0,
            y=y0 - index * 5.20,
            cover_m=cover_m,
            clean_concrete_m=clean_concrete_m,
            starter_diameter_mm=starter_diameter_mm,
            stirrup_diameter_mm=stirrup_diameter_mm,
            stirrup_spacing_cm=stirrup_spacing_cm,
            stirrup_secondary_spacing_cm=stirrup_secondary_spacing_cm,
            critical_zone_m=critical_zone_m,
        )

        rows.append(row)

    draw_summary_table(
        msp=msp,
        rows=rows,
        x=10.5,
        y=14.8,
    )

    from civil_engine.plans.dxf_finalize import finalize_and_save
    finalize_and_save(doc, output_path)
    return str(output_path)
