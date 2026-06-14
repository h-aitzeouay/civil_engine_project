from __future__ import annotations

from pathlib import Path
from typing import Any

import ezdxf

from civil_engine.foundations.column_effective import get_effective_column_boxes
from civil_engine.plans.reinforcement_dxf import (
    ensure_layers as ensure_reinforcement_layers,
    add_text,
    add_line,
    add_rect,
    add_circle,
    get_foundation_bbox,
    draw_emprise_and_columns,
    draw_axes,
    build_initial_occupied_boxes,
    draw_final_foundations,
    draw_reinforcement,
    table_position,
    draw_bar_lines_x,
    draw_bar_lines_y,
    choose_label_box,
    add_label_lines,
    add_leader_to_label,
    pad_box,
)


# =========================================================
# LAYERS
# =========================================================

def ensure_execution_layers(doc) -> None:
    ensure_reinforcement_layers(doc)

    layers = {
        "ATTENTES_POTEAUX": 1,
        "CADRES_POTEAUX": 6,
        "TABLEAU_EXECUTION": 7,
        "REFERENCES": 4,
        "NOTES_EXECUTION": 1,
        "CARTOUCHE": 7,
        "RENVOIS_EXECUTION": 8,
        "DETAILS_ANCRAGE": 5,
        "DETAILS_ATTENTES": 2,
        "DETAILS_SECTIONS": 3,
        "DETAILS_TITRES": 7,
        "ARMATURES": 4,
        "COTES_DETAILS": 4,
        "HACHURES_DETAILS": 8,
        "SEMELLE_FILANTE": 3,
        "VOILE_FONDATION": 5,
        "MASSIF_FILANTE": 1,
    }

    for name, color in layers.items():
        if name not in doc.layers:
            doc.layers.add(name=name, color=color)


# =========================================================
# OUTILS
# =========================================================

def add_multiline_text(
    msp,
    lines: list[str],
    x: float,
    y: float,
    height: float = 0.10,
    spacing: float = 0.20,
    layer: str = "TEXTES",
) -> None:
    for i, line in enumerate(lines):
        add_text(msp, line, x, y - i * spacing, height, layer)


def draw_panel(
    msp,
    title: str,
    x: float,
    y: float,
    w: float,
    h: float,
    layer: str = "DETAILS_TITRES",
) -> None:
    add_rect(msp, x, y, x + w, y + h, layer)
    add_line(msp, x, y + h - 0.45, x + w, y + h - 0.45, layer)
    add_text(msp, title, x + 0.20, y + h - 0.30, 0.14, layer)

def starter_points_for_column(
    box: dict[str, float],
    cover_m: float = 0.06,
) -> list[tuple[float, float]]:
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
        points.append(((x1 + x2) / 2.0, y1))
        points.append(((x1 + x2) / 2.0, y2))

    if ymax - ymin >= 0.35:
        points.append((x1, (y1 + y2) / 2.0))
        points.append((x2, (y1 + y2) / 2.0))

    return points


# =========================================================
# PLAN PRINCIPAL
# =========================================================

def draw_starter_bars_on_plan(
    msp,
    model: dict[str, Any],
    starter_diameter_mm: float,
) -> None:
    boxes = get_effective_column_boxes(model)
    radius = max(starter_diameter_mm / 1000.0 / 2.0, 0.018)

    for _column_id, box in boxes.items():
        for x, y in starter_points_for_column(box):
            add_circle(msp, x, y, radius, "ATTENTES_POTEAUX")

        add_rect(
            msp,
            float(box["xmin"]) + 0.04,
            float(box["ymin"]) + 0.04,
            float(box["xmax"]) - 0.04,
            float(box["ymax"]) - 0.04,
            "CADRES_POTEAUX",
        )


def foundation_row_data(
    strategy_report: dict[str, Any],
    reinforcement_report: dict[str, Any],
) -> list[dict[str, Any]]:
    reinf_map = {
        item.get("foundation_id"): item
        for item in reinforcement_report.get("results", [])
    }

    rows = []

    for element in strategy_report.get("final_foundations", []):
        fid = element.get("id")
        reinf = reinf_map.get(fid, {})
        r = reinf.get("reinforcement", {})

        rows.append({
            "id": fid,
            "type": element.get("type"),
            "A_m": element.get("A_m"),
            "B_m": element.get("B_m"),
            "H_m": element.get("H_m"),
            "inf_x": r.get("bottom_bars_X", {}).get("proposal", {}).get("label", "-"),
            "inf_y": r.get("bottom_bars_Y", {}).get("proposal", {}).get("label", "-"),
            "sup_x": r.get("top_bars_X", {}).get("proposal", {}).get("label", "-"),
            "sup_y": r.get("top_bars_Y", {}).get("proposal", {}).get("label", "-"),
        })

    return rows


def draw_execution_table(
    msp,
    strategy_report: dict[str, Any],
    reinforcement_report: dict[str, Any],
    x: float,
    y: float,
) -> None:
    add_text(msp, "TABLEAU D'EXECUTION FONDATIONS", x, y, 0.22, "TABLEAU_EXECUTION")
    y -= 0.45

    headers = [
        ("FOND", 0.0),
        ("TYPE", 1.4),
        ("A", 2.4),
        ("B", 3.2),
        ("H", 4.0),
        ("INF X", 4.9),
        ("INF Y", 7.4),
        ("SUP X", 9.9),
        ("SUP Y", 12.4),
    ]

    for title, dx in headers:
        add_text(msp, title, x + dx, y, 0.10, "TABLEAU_EXECUTION")

    y -= 0.25

    for row in foundation_row_data(strategy_report, reinforcement_report):
        values = [
            (row["id"], 0.0),
            (row["type"], 1.4),
            (row["A_m"], 2.4),
            (row["B_m"], 3.2),
            (row["H_m"], 4.0),
            (row["inf_x"], 4.9),
            (row["inf_y"], 7.4),
            (row["sup_x"], 9.9),
            (row["sup_y"], 12.4),
        ]

        for value, dx in values:
            add_text(msp, str(value), x + dx, y, 0.078, "TABLEAU_EXECUTION")

        y -= 0.22


def draw_references(
    msp,
    x: float,
    y: float,
) -> None:
    add_text(msp, "REFERENCES DETAILS", x, y, 0.18, "REFERENCES")
    y -= 0.30

    refs = [
        "D1 : Coupes detaillees fondations",
        "D2 : Details ancrages et recouvrements",
        "D3 : Details attentes et cadres",
        "D4 : Verification poinconnement",
        "D5 : Note de calcul generale",
    ]

    for ref in refs:
        add_text(msp, ref, x, y, 0.10, "REFERENCES")
        y -= 0.20


def draw_general_notes(
    msp,
    x: float,
    y: float,
) -> None:
    add_text(msp, "NOTES GENERALES", x, y, 0.18, "NOTES_EXECUTION")
    y -= 0.30

    notes = [
        "1. Plan base sur la configuration finale retenue.",
        "2. Les dimensions et ferraillages sont issus du predimensionnement automatique.",
        "3. Verification finale par ingenieur structure obligatoire avant execution.",
        "4. Ancrages, recouvrements et dispositions sismiques a valider.",
        "5. Toute modification chantier doit etre validee avant execution.",
        "6. Les details integres ci-dessous sont schematiques et servent de renvoi d'execution.",
    ]

    for note in notes:
        add_text(msp, note, x, y, 0.085, "NOTES_EXECUTION")
        y -= 0.18


# =========================================================
# CARTOUCHE CORRIGE
# =========================================================

def draw_cartouche(
    msp,
    x: float,
    y: float,
) -> None:
    """
    Cartouche élargi et textes recadrés.
    """
    width = 13.5
    height = 1.80

    # colonnes
    c1 = 3.4
    c2 = 8.5

    add_rect(msp, x, y, x + width, y + height, "CARTOUCHE")
    add_line(msp, x, y + 0.55, x + width, y + 0.55, "CARTOUCHE")
    add_line(msp, x + c1, y, x + c1, y + height, "CARTOUCHE")
    add_line(msp, x + c2, y, x + c2, y + height, "CARTOUCHE")

    # Ligne haute
    add_text(msp, "INGENIERIE.COM", x + 0.20, y + 1.15, 0.16, "CARTOUCHE")
    add_text(msp, "PLAN FINAL D'EXECUTION FONDATIONS", x + c1 + 0.20, y + 1.15, 0.13, "CARTOUCHE")
    add_text(msp, "VERSION 0.27.2", x + c2 + 0.20, y + 1.15, 0.12, "CARTOUCHE")

    # Ligne basse
    add_text(msp, "Echelle : 1/50 indic.", x + 0.20, y + 0.18, 0.10, "CARTOUCHE")
    add_text(msp, "Statut : PRE-EXECUTION", x + c1 + 0.20, y + 0.18, 0.10, "CARTOUCHE")
    add_text(msp, "Controle ingenieur requis", x + c2 + 0.20, y + 0.18, 0.10, "CARTOUCHE")


# =========================================================
# DETAILS INTEGRES
# =========================================================


def add_detail_dimension_horizontal(
    msp,
    x1: float,
    x2: float,
    y: float,
    label: str,
) -> None:
    add_line(msp, x1, y, x2, y, "COTES_DETAILS")
    add_line(msp, x1, y - 0.05, x1, y + 0.05, "COTES_DETAILS")
    add_line(msp, x2, y - 0.05, x2, y + 0.05, "COTES_DETAILS")
    add_text(msp, label, (x1 + x2) / 2.0 - 0.15, y + 0.08, 0.075, "COTES_DETAILS")


def add_detail_dimension_vertical(
    msp,
    x: float,
    y1: float,
    y2: float,
    label: str,
) -> None:
    add_line(msp, x, y1, x, y2, "COTES_DETAILS")
    add_line(msp, x - 0.05, y1, x + 0.05, y1, "COTES_DETAILS")
    add_line(msp, x - 0.05, y2, x + 0.05, y2, "COTES_DETAILS")
    add_text(msp, label, x + 0.08, (y1 + y2) / 2.0, 0.075, "COTES_DETAILS")


def draw_small_hook_135(
    msp,
    x: float,
    y: float,
    direction: str,
    layer: str = "DETAILS_ANCRAGE",
) -> None:
    if direction == "right":
        add_line(msp, x, y, x + 0.35, y + 0.25, layer)
    elif direction == "left":
        add_line(msp, x, y, x - 0.35, y + 0.25, layer)
    elif direction == "down-right":
        add_line(msp, x, y, x + 0.35, y - 0.25, layer)
    else:
        add_line(msp, x, y, x - 0.35, y - 0.25, layer)


def draw_clean_column_section(
    msp,
    x: float,
    y: float,
    w: float,
    h: float,
    layer: str,
) -> None:
    add_rect(msp, x, y, x + w, y + h, layer)
    add_line(msp, x + 0.08, y + 0.25, x + w - 0.08, y + 0.25, "CADRES_POTEAUX")
    add_line(msp, x + 0.08, y + 0.55, x + w - 0.08, y + 0.55, "CADRES_POTEAUX")
    add_line(msp, x + 0.08, y + 0.85, x + w - 0.08, y + 0.85, "CADRES_POTEAUX")



def draw_anchorage_detail_panel(
    msp,
    x: float,
    y: float,
) -> None:
    w = 14.0
    h = 5.0
    draw_panel(msp, "D1 - DETAILS ANCRAGES ET RECOUVREMENTS", x, y, w, h, "DETAILS_TITRES")

    # Sous-titres
    add_text(msp, "A - ATTENTE DROITE", x + 0.40, y + h - 0.80, 0.105, "DETAILS_ANCRAGE")
    add_text(msp, "B - ATTENTE COUDEE / CROSSE 135°", x + 4.60, y + h - 0.80, 0.105, "DETAILS_ANCRAGE")
    add_text(msp, "C - RECOUVREMENT", x + 9.80, y + h - 0.80, 0.105, "DETAILS_ANCRAGE")

    # Forme A
    ax = x + 1.20
    ay = y + 1.05
    add_line(msp, ax, ay, ax, ay + 2.20, "DETAILS_ANCRAGE")
    add_line(msp, ax - 0.35, ay, ax + 0.35, ay, "DETAILS_ANCRAGE")
    add_detail_dimension_vertical(msp, ax + 0.45, ay, ay + 2.20, "Lbd")
    add_text(msp, "Barre verticale ancree", ax - 0.75, ay - 0.35, 0.085, "DETAILS_ANCRAGE")

    # Forme B
    bx = x + 5.70
    by = y + 1.05
    add_line(msp, bx, by + 0.30, bx, by + 2.25, "DETAILS_ANCRAGE")
    add_line(msp, bx, by + 0.30, bx + 1.20, by + 0.30, "DETAILS_ANCRAGE")
    draw_small_hook_135(msp, bx + 1.20, by + 0.30, "right", "DETAILS_ANCRAGE")
    add_detail_dimension_vertical(msp, bx - 0.35, by + 0.30, by + 2.25, "Lbd")
    add_detail_dimension_horizontal(msp, bx, bx + 1.20, by - 0.05, "retour")
    add_text(msp, "Crosse a utiliser si H insuffisant", bx - 0.55, by - 0.45, 0.085, "DETAILS_ANCRAGE")

    # Forme C
    cx = x + 10.60
    cy = y + 0.95
    add_line(msp, cx, cy, cx, cy + 2.40, "DETAILS_ANCRAGE")
    add_line(msp, cx + 0.35, cy + 0.50, cx + 0.35, cy + 2.90, "RECOUVREMENTS")
    add_detail_dimension_vertical(msp, cx + 0.70, cy + 0.50, cy + 2.40, "L0")
    add_text(msp, "Recouvrement hors zone critique", cx - 0.45, cy - 0.35, 0.085, "DETAILS_ANCRAGE")

    # Notes séparées, sans chevauchement
    add_multiline_text(
        msp,
        [
            "Notes execution :",
            "- Lbd et L0 a recalculer selon EC2/BAEL.",
            "- Crochets, diametres et rayons de cintrage a verifier.",
            "- Eviter les recouvrements dans les zones critiques.",
        ],
        x + 0.40,
        y + 0.70,
        0.085,
        0.18,
        "NOTES_EXECUTION",
    )

def draw_attentes_detail_panel(
    msp,
    x: float,
    y: float,
) -> None:
    w = 14.0
    h = 5.0
    draw_panel(msp, "D2 - DETAILS ATTENTES POTEAUX ET CADRES", x, y, w, h, "DETAILS_TITRES")

    # Vue en plan
    px = x + 0.65
    py = y + 1.00
    pw = 2.50
    ph = 2.50

    add_text(msp, "Vue en plan du poteau", px, y + h - 0.80, 0.105, "DETAILS_ATTENTES")
    add_rect(msp, px, py, px + pw, py + ph, "DETAILS_ATTENTES")

    # Cadre interieur
    add_rect(msp, px + 0.50, py + 0.50, px + 2.00, py + 2.00, "CADRES_POTEAUX")

    # Attentes
    points = [
        (px + 0.25, py + 0.25),
        (px + 2.25, py + 0.25),
        (px + 2.25, py + 2.25),
        (px + 0.25, py + 2.25),
        (px + 1.25, py + 0.25),
        (px + 1.25, py + 2.25),
    ]

    for cx, cy in points:
        add_circle(msp, cx, cy, 0.055, "ATTENTES_POTEAUX")

    add_text(msp, "Attentes HA", px + 2.80, py + 2.20, 0.085, "DETAILS_ATTENTES")
    add_text(msp, "Cadre ferme", px + 2.80, py + 1.95, 0.085, "CADRES_POTEAUX")
    add_text(msp, "Enrobage c", px + 2.80, py + 1.70, 0.085, "DETAILS_ATTENTES")

    # Coupe type
    cx = x + 6.00
    cy = y + 0.80

    add_text(msp, "Coupe type poteau sur fondation", cx, y + h - 0.80, 0.105, "DETAILS_ATTENTES")

    # Fondation
    add_rect(msp, cx, cy, cx + 3.20, cy + 0.55, "DETAILS_ATTENTES")

    # Poteau
    col_x1 = cx + 1.15
    col_x2 = cx + 2.05
    col_y1 = cy + 0.55
    col_y2 = cy + 3.30

    add_rect(msp, col_x1, col_y1, col_x2, col_y2, "DETAILS_ATTENTES")

    # Attentes verticales
    add_line(msp, col_x1 + 0.20, cy + 0.12, col_x1 + 0.20, col_y2, "ATTENTES_POTEAUX")
    add_line(msp, col_x2 - 0.20, cy + 0.12, col_x2 - 0.20, col_y2, "ATTENTES_POTEAUX")

    # Cadres
    ycad = col_y1 + 0.25
    while ycad <= col_y2 - 0.20:
        add_line(msp, col_x1 + 0.08, ycad, col_x2 - 0.08, ycad, "CADRES_POTEAUX")
        ycad += 0.32

    add_detail_dimension_vertical(msp, cx + 3.45, col_y1, col_y1 + 0.95, "zone serree")
    add_detail_dimension_vertical(msp, cx + 3.75, col_y1, col_y2, "hauteur poteau")

    add_multiline_text(
        msp,
        [
            "Indications :",
            "- Cadres rapproches en pied de poteau.",
            "- Espacement courant au-dessus de la zone critique.",
            "- Attentes centrees dans le poteau effectif.",
            "- Enrobage et recouvrements a verifier.",
        ],
        x + 10.30,
        y + 3.55,
        0.085,
        0.18,
        "DETAILS_ATTENTES",
    )

def draw_section_type_detail(
    msp,
    x: float,
    y: float,
    title: str,
    top_reinf: bool = True,
    eccentric: bool = False,
) -> None:
    w = 3.00
    h = 2.45

    add_rect(msp, x, y, x + w, y + h, "DETAILS_SECTIONS")
    add_text(msp, title, x + 0.12, y + h - 0.20, 0.10, "DETAILS_SECTIONS")

    # Semelle
    fx1 = x + 0.35
    fx2 = x + 2.65
    fy1 = y + 0.35
    fy2 = y + 0.80

    add_rect(msp, fx1, fy1, fx2, fy2, "DETAILS_SECTIONS")

    # Poteau
    if eccentric:
        px1 = fx1 + 0.20
        px2 = px1 + 0.55
    else:
        px1 = x + 1.22
        px2 = x + 1.78

    add_rect(msp, px1, fy2, px2, y + 2.05, "DETAILS_SECTIONS")

    # Nappe inf
    y_inf = fy1 + 0.12
    add_line(msp, fx1 + 0.15, y_inf, fx2 - 0.15, y_inf, "ARMATURES")
    for bx in [fx1 + 0.35, x + 1.50, fx2 - 0.35]:
        add_circle(msp, bx, y_inf, 0.035, "ARMATURES")

    # Nappe sup
    if top_reinf:
        y_sup = fy2 - 0.12
        add_line(msp, fx1 + 0.25, y_sup, fx2 - 0.25, y_sup, "ARMATURES")
        for bx in [fx1 + 0.55, x + 1.50, fx2 - 0.55]:
            add_circle(msp, bx, y_sup, 0.030, "ARMATURES")

    # Attentes
    add_line(msp, px1 + 0.15, fy1 + 0.05, px1 + 0.15, y + 2.05, "ATTENTES_POTEAUX")
    add_line(msp, px2 - 0.15, fy1 + 0.05, px2 - 0.15, y + 2.05, "ATTENTES_POTEAUX")

    # Labels courts hors dessin
    add_text(msp, "Inf", fx2 - 0.35, y_inf - 0.18, 0.075, "DETAILS_SECTIONS")
    if top_reinf:
        add_text(msp, "Sup", fx2 - 0.35, y_sup + 0.08, 0.075, "DETAILS_SECTIONS")

def draw_sections_panel(
    msp,
    strategy_report: dict[str, Any],
    x: float,
    y: float,
) -> None:
    w = 14.0
    h = 5.2
    draw_panel(msp, "D3 - SECTIONS TYPES DE FERRAILLAGE", x, y, w, h, "DETAILS_TITRES")

    types_present = []
    for element in strategy_report.get("final_foundations", []):
        t = element.get("type")
        if t and t not in types_present:
            types_present.append(t)

    px = x + 0.45
    py = y + 1.45

    drawn = 0

    if "SI" in types_present:
        draw_section_type_detail(msp, px, py, "SI - semelle isolee", top_reinf=False, eccentric=False)
        px += 3.30
        drawn += 1

    if "SE" in types_present:
        draw_section_type_detail(msp, px, py, "SE - semelle excentree", top_reinf=True, eccentric=True)
        px += 3.30
        drawn += 1

    if "SC" in types_present:
        draw_section_type_detail(msp, px, py, "SC - semelle combinee", top_reinf=True, eccentric=False)
        px += 3.30
        drawn += 1

    if "RL" in types_present:
        draw_section_type_detail(msp, px, py, "RL - radier local", top_reinf=True, eccentric=False)
        drawn += 1

    if drawn == 0:
        add_text(msp, "Aucune section type detectee.", x + 0.50, y + 2.50, 0.10, "DETAILS_SECTIONS")

    add_multiline_text(
        msp,
        [
            "Notes :",
            "- Sections types de renvoi, non a l'echelle stricte.",
            "- Les coupes detaillees restent prioritaires.",
            "- Les ancrages, crochets et recouvrements sont a verifier par la note de calcul.",
        ],
        x + 0.45,
        y + 0.85,
        0.085,
        0.18,
        "DETAILS_SECTIONS",
    )

# =========================================================
# GENERATION FINALE
# =========================================================

from civil_engine.plans.cartouche import insert_cartouche, build_cartouche_values, cartouche_size


def draw_strip_footings_on_plan(msp, strip_design, interference=None, occupied=None):
    """
    Dessine les semelles filantes, voiles, massifs ET leur ferraillage sur le
    plan d'execution, avec annotation a leader harmonisee (meme style que les
    semelles isolees). occupied = liste des zones deja occupees par les
    annotations (anti-chevauchement).
    """
    if not strip_design:
        return
    if occupied is None:
        occupied = []

    def _rect(b, layer):
        msp.add_lwpolyline(
            [(b["xmin"], b["ymin"]), (b["xmax"], b["ymin"]),
             (b["xmax"], b["ymax"]), (b["xmin"], b["ymax"])],
            close=True, dxfattribs={"layer": layer})

    cover = 0.06

    for sf in strip_design.get("strip_footings", []):
        bb = sf["bbox"]
        _rect(bb, "SEMELLE_FILANTE")
        wb = sf.get("wall_bbox")
        if wb:
            _rect(wb, "VOILE_FONDATION")

        xmin, xmax = bb["xmin"], bb["xmax"]
        ymin, ymax = bb["ymin"], bb["ymax"]
        axis = sf.get("axis", "H")
        reinf = sf.get("reinforcement", {})
        spacing = float(reinf.get("main_spacing_m", 0.20)) or 0.20

        # Ferraillage : transversal (principal) + longitudinal (repartition).
        # Voile vertical (V) : semelle allongee selon Y.
        #   - transversal principal = lignes horizontales (sens X)
        #   - longitudinal repartition = lignes verticales (sens Y)
        # Voile horizontal (H) : l'inverse.
        if axis == "V":
            draw_bar_lines_x(msp, xmin, xmax, ymin, ymax, spacing, "ARM_INF_X", cover)
            draw_bar_lines_y(msp, xmin, xmax, ymin, ymax, 0.20, "ARM_INF_Y", cover)
        else:
            draw_bar_lines_y(msp, xmin, xmax, ymin, ymax, spacing, "ARM_INF_Y", cover)
            draw_bar_lines_x(msp, xmin, xmax, ymin, ymax, 0.20, "ARM_INF_X", cover)

        # Annotation a leader harmonisee
        main = reinf.get("main_bottom", "")
        dist = reinf.get("distribution_bottom", "")
        label_1 = f"{sf['id']}  {sf['B_m']:.2f}x{sf['H_m']:.2f}"
        label_2 = f"Princ. {main}"
        label_3 = f"Repart. {dist}"

        label_box = choose_label_box(
            bbox=bb, lines=[label_1, label_2, label_3], occupied=occupied,
            text_height=0.09, line_spacing=0.18)
        add_label_lines(msp, label_box, [label_1, label_2, label_3], "TEXTES")
        add_leader_to_label(msp, bb, label_box)
        occupied.append(pad_box(label_box, 0.08))

    # Massifs d'angle (filante <-> filante)
    for m in strip_design.get("massifs", []):
        _rect(m["bbox"], "MASSIF_FILANTE")

    # Massifs locaux combines poteau-voile
    if interference:
        for m in interference.get("final_decisions", {}).get("local_massifs", []):
            _rect(m["bbox"], "MASSIF_FILANTE")


def generate_execution_foundation_dxf(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    reinforcement_report: dict[str, Any],
    anchorage_report: dict[str, Any],
    output_path: str | Path,
    starter_diameter_mm: float = 14.0,
    project_name: str = "",
    project_number: str = "",
    plan_date: str = "",
    scale_label: str = "1/50",
    strip_design: dict[str, Any] | None = None,
    strip_interference: dict[str, Any] | None = None,
) -> str:
    output_path = Path(output_path)

    doc = ezdxf.new("R2010")
    doc.units = 6
    ensure_execution_layers(doc)

    msp = doc.modelspace()

    bbox = get_foundation_bbox(model)

    title_y = 13.0
    xmin = 0.0
    ymin = -3.0
    xmax = 15.0

    if bbox is not None:
        title_y = float(bbox["ymax"]) + 2.6
        xmin = float(bbox["xmin"])
        ymin = float(bbox["ymin"])
        xmax = float(bbox["xmax"])

    add_text(msp, "PLAN FINAL D'EXECUTION FONDATIONS", 0.0, title_y, 0.32, "TEXTES")
    add_text(msp, "INGENIERIE.COM - configuration finale + ferraillage + attentes + details lisibles integres", 0.0, title_y - 0.42, 0.17, "TEXTES")

    occupied = build_initial_occupied_boxes(
        model=model,
        strategy_report=strategy_report,
        reinforcement_report=reinforcement_report,
    )

    # Plan principal
    draw_emprise_and_columns(msp, model, strategy_report)
    draw_axes(msp, model)
    draw_final_foundations(msp, strategy_report, occupied)
    draw_reinforcement(msp, strategy_report, reinforcement_report, occupied)
    draw_strip_footings_on_plan(msp, strip_design, strip_interference, occupied)
    draw_starter_bars_on_plan(msp, model, starter_diameter_mm)

    # Zone tableau à droite
    tx, ty = table_position(model)

    draw_execution_table(
        msp=msp,
        strategy_report=strategy_report,
        reinforcement_report=reinforcement_report,
        x=tx,
        y=ty,
    )

    draw_references(msp, tx, ty - 5.10)
    draw_general_notes(msp, tx, ty - 6.70)

    # Détails intégrés sous le plan principal
    details_y = ymin - 8.80
    details_x = xmin

    draw_anchorage_detail_panel(
        msp,
        details_x,
        details_y,
    )

    draw_attentes_detail_panel(
        msp,
        details_x,
        details_y - 5.60,
    )

    draw_sections_panel(
        msp,
        strategy_report,
        details_x,
        details_y - 11.20,
    )

    # Cartouche A3 réel (gabarit INGENIERIE.COM), agrandi pour lisibilité
    cart_w, cart_h = cartouche_size("m", drawing_scale=50.0)
    cartouche_y = details_y - 17.40 - cart_h
    cartouche_x = xmin

    cart_values = build_cartouche_values(
        project_name=project_name,
        project_number=project_number,
        plan_title="Plan d'execution fondations",
        date_str=plan_date,
        scale_label=scale_label,
    )
    try:
        insert_cartouche(
            target_doc=doc,
            insert_xy=(cartouche_x, cartouche_y),
            values=cart_values,
            target_units="m",
            drawing_scale=50.0,
        )
    except Exception:
        # repli sur l'ancien cartouche simplifié si le gabarit est indisponible
        draw_cartouche(msp, cartouche_x, cartouche_y)

    doc.saveas(output_path)
    return str(output_path)
