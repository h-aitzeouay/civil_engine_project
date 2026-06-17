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
        "DETAILS_ANCRAGE": 7,
        "RECOUVREMENTS": 7,
        "DETAILS_ATTENTES": 2,
        "DETAILS_SECTIONS": 3,
        "DETAILS_TITRES": 7,
        "ARMATURES": 4,
        "COTES_DETAILS": 4,
        "HACHURES_DETAILS": 8,
        "SEMELLE_FILANTE": 3,
        "VOILE_FONDATION": 5,
        "MASSIF_FILANTE": 1,
        "ARM_FILANTE_PRINC": 2,
        "ARM_FILANTE_REP": 30,
        "POUTRE_REDRESSEMENT": 30,
        "ARM_PR": 2,
        "LONGRINE": 4,
        "ARM_LONGRINE": 2,
        "POUTRE_LIAISON": 3,
        "ARM_LIAISON": 2,
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
    strip_design: dict[str, Any] | None = None,
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

    # Section semelles filantes sous voiles
    if strip_design and strip_design.get("strip_footings"):
        y -= 0.30
        add_text(msp, "SEMELLES FILANTES SOUS VOILES", x, y, 0.13, "SEMELLE_FILANTE")
        y -= 0.30
        sf_headers = [
            ("SEM", 0.0), ("VOILE", 1.4), ("L", 2.4), ("B", 3.2), ("H", 4.0),
            ("PRINCIPAL", 4.9), ("REPARTITION", 9.9),
        ]
        for title, dx in sf_headers:
            add_text(msp, title, x + dx, y, 0.10, "SEMELLE_FILANTE")
        y -= 0.25

        for sf in strip_design["strip_footings"]:
            reinf = sf.get("reinforcement", {})
            principal = reinf.get("main_bottom", "").replace("Inf transversal ", "")
            repart = reinf.get("distribution_bottom", "").replace("Inf longitudinal ", "")
            values = [
                (sf.get("id", ""), 0.0),
                (sf.get("wall_id", ""), 1.4),
                (f"{sf.get('A_m', 0):.2f}", 2.4),
                (f"{sf.get('B_m', 0):.2f}", 3.2),
                (f"{sf.get('H_m', 0):.2f}", 4.0),
                (principal, 4.9),
                (repart, 9.9),
            ]
            for value, dx in values:
                add_text(msp, str(value), x + dx, y, 0.078, "SEMELLE_FILANTE")
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
    add_detail_dimension_vertical(msp, ax + 0.45, ay, ay + 2.20, "Lbd = 40 phi")
    add_text(msp, "Barre verticale ancree", ax - 0.75, ay - 0.35, 0.085, "DETAILS_ANCRAGE")

    # Forme B
    bx = x + 5.70
    by = y + 1.05
    add_line(msp, bx, by + 0.30, bx, by + 2.25, "DETAILS_ANCRAGE")
    add_line(msp, bx, by + 0.30, bx + 1.20, by + 0.30, "DETAILS_ANCRAGE")
    draw_small_hook_135(msp, bx + 1.20, by + 0.30, "right", "DETAILS_ANCRAGE")
    add_detail_dimension_vertical(msp, bx - 0.35, by + 0.30, by + 2.25, "Lbd = 40 phi")
    add_detail_dimension_horizontal(msp, bx, bx + 1.20, by - 0.05, "retour")
    add_text(msp, "Crosse a utiliser si H insuffisant", bx - 0.55, by - 0.45, 0.085, "DETAILS_ANCRAGE")

    # Forme C
    cx = x + 10.60
    cy = y + 0.95
    add_line(msp, cx, cy, cx, cy + 2.40, "DETAILS_ANCRAGE")
    add_line(msp, cx + 0.35, cy + 0.50, cx + 0.35, cy + 2.90, "RECOUVREMENTS")
    add_detail_dimension_vertical(msp, cx + 0.70, cy + 0.50, cy + 2.40, "L0 = 60 phi")
    add_text(msp, "Recouvrement hors zone critique", cx - 0.45, cy - 0.35, 0.085, "DETAILS_ANCRAGE")

    # Notes separees, sans chevauchement (valeurs normatives EC2/BAEL)
    add_multiline_text(
        msp,
        [
            "Notes execution (valeurs normatives EC2/BAEL) :",
            "- Lbd = 40 phi (ancrage droit, conditions d'adherence courantes).",
            "- L0 = 60 phi (recouvrement = 1.5 x Lbd, barres tendues).",
            "- Crochets, diametres et rayons de cintrage selon EC2/BAEL.",
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

def draw_strip_section_detail(
    msp,
    x: float,
    y: float,
    sf: dict[str, Any] | None = None,
    wall_thickness_m: float = 0.20,
) -> None:
    """
    Coupe transversale type d'une semelle filante sous voile (voile au centre,
    attentes verticales). Inclut : semelle, beton de proprete hachure, voile
    montant, nappes d'aciers, attentes du voile avec crosses, cotation, notes.
    """
    B = float(sf.get("B_m", 0.60)) if sf else 0.60
    H = float(sf.get("H_m", 0.35)) if sf else 0.35
    sid = sf.get("id", "SFV") if sf else "SFV"
    ep = wall_thickness_m

    # Cadre du detail
    w_box = 4.40
    h_box = 3.30
    add_rect(msp, x, y, x + w_box, y + h_box, "DETAILS_SECTIONS")
    add_text(msp, f"COUPE SEMELLE FILANTE {sid}", x + 0.12, y + h_box - 0.22, 0.10, "DETAILS_TITRES")

    # Geometrie dessinee (dimensions fixes maitrisees pour tenir dans le cadre)
    draw_w = 2.40                       # largeur dessinee de la semelle
    sc = draw_w / max(B, 0.1)           # echelle horizontale
    draw_h = min(H * sc, 0.55)          # hauteur semelle bornee
    prop_h = 0.12                       # beton de proprete (fixe a l'ecran)
    wall_h = 0.85                       # hauteur voile dessinee (bornee)
    wall_draw_w = max(ep * sc, 0.20)

    # Origine de la semelle (coin bas-gauche), centree dans le cadre
    sx = x + (w_box - draw_w) / 2.0
    sy = y + 0.95

    # --- Beton de proprete hachure sous la semelle ---
    deb = 0.12
    px1, px2 = sx - deb, sx + draw_w + deb
    py1, py2 = sy - prop_h, sy
    add_rect(msp, px1, py1, px2, py2, "HACHURES_DETAILS")
    import random
    random.seed(7)
    for _ in range(45):
        gx = px1 + random.random() * (px2 - px1)
        gy = py1 + random.random() * (py2 - py1)
        add_circle(msp, gx, gy, 0.010, "HACHURES_DETAILS")

    # --- Semelle ---
    add_rect(msp, sx, sy, sx + draw_w, sy + draw_h, "DETAILS_SECTIONS")

    # --- Voile montant EN RIVE (cote mitoyen = bord exterieur) ---
    # Convention : la face mitoyenne est le bord gauche de la semelle dessinee ;
    # le voile demarre sur ce bord et la semelle se developpe vers l'interieur (droite).
    wx1 = sx                          # voile colle au bord exterieur (mitoyen)
    wx2 = sx + wall_draw_w
    wcx = 0.5 * (wx1 + wx2)
    wall_top = sy + draw_h + wall_h
    add_rect(msp, wx1, sy + draw_h, wx2, wall_top, "DETAILS_SECTIONS")

    # --- Nappe inferieure (aciers principaux transversaux) ---
    cov = 0.06
    y_inf = sy + cov
    add_line(msp, sx + cov, y_inf, sx + draw_w - cov, y_inf, "ARM_FILANTE_PRINC")
    n_long = 5
    for i in range(n_long):
        bx = sx + cov + i * (draw_w - 2 * cov) / (n_long - 1)
        add_circle(msp, bx, y_inf, 0.022, "ARM_FILANTE_PRINC")

    # --- Nappe superieure ---
    y_sup = sy + draw_h - cov
    add_line(msp, sx + cov, y_sup, sx + draw_w - cov, y_sup, "ARM_FILANTE_REP")
    for i in range(n_long):
        bx = sx + cov + i * (draw_w - 2 * cov) / (n_long - 1)
        add_circle(msp, bx, y_sup, 0.018, "ARM_FILANTE_REP")

    # --- Attentes du voile (2 barres verticales avec crosses en bas) ---
    att_x1 = wx1 + 0.04
    att_x2 = wx2 - 0.04
    att_bot = sy + cov
    add_line(msp, att_x1, att_bot, att_x1, wall_top - 0.08, "ATTENTES_POTEAUX")
    add_line(msp, att_x2, att_bot, att_x2, wall_top - 0.08, "ATTENTES_POTEAUX")
    # crosses en bas (retour horizontal)
    add_line(msp, att_x1, att_bot, att_x1 + 0.08, att_bot, "ATTENTES_POTEAUX")
    add_line(msp, att_x2, att_bot, att_x2 - 0.08, att_bot, "ATTENTES_POTEAUX")
    # crochets en haut
    add_line(msp, att_x1, wall_top - 0.08, att_x1 + 0.06, wall_top - 0.02, "ATTENTES_POTEAUX")
    add_line(msp, att_x2, wall_top - 0.08, att_x2 - 0.06, wall_top - 0.02, "ATTENTES_POTEAUX")

    # --- Cotation largeur B (sous la propreté) ---
    cot_y = py1 - 0.14
    add_line(msp, sx, cot_y, sx + draw_w, cot_y, "COTES_DETAILS")
    add_line(msp, sx, cot_y - 0.04, sx, cot_y + 0.04, "COTES_DETAILS")
    add_line(msp, sx + draw_w, cot_y - 0.04, sx + draw_w, cot_y + 0.04, "COTES_DETAILS")
    add_text(msp, f"B = {B:.2f} m", sx + draw_w / 2.0 - 0.28, cot_y - 0.15, 0.085, "COTES_DETAILS")
    # cotation H (a droite)
    cot_x = sx + draw_w + deb + 0.10
    add_line(msp, cot_x, sy, cot_x, sy + draw_h, "COTES_DETAILS")
    add_line(msp, cot_x - 0.04, sy, cot_x + 0.04, sy, "COTES_DETAILS")
    add_line(msp, cot_x - 0.04, sy + draw_h, cot_x + 0.04, sy + draw_h, "COTES_DETAILS")
    add_text(msp, f"H={H:.2f}", cot_x + 0.06, sy + draw_h / 2.0 - 0.04, 0.075, "COTES_DETAILS")

    # --- Annotations ---
    add_text(msp, f"Voile ep.{ep:.2f}", wx1 - 0.05, wall_top + 0.05, 0.075, "DETAILS_SECTIONS")
    # repere cote mitoyen (limite de propriete) sur le bord exterieur
    add_line(msp, sx, sy - prop_h - 0.05, sx, wall_top + 0.20, "COTES_DETAILS")
    add_text(msp, "Limite propriete (mitoyen)", sx - 0.05, wall_top + 0.22, 0.060, "COTES_DETAILS")
    reinf = sf.get("reinforcement", {}) if sf else {}
    princ = reinf.get("main_bottom", "HA12 e=0.20").replace("Inf transversal ", "")
    rep = reinf.get("distribution_bottom", "HA10 e=0.20").replace("Inf longitudinal ", "")
    add_text(msp, f"Princ.: {princ}", x + 0.15, sy + 0.02, 0.068, "ARM_FILANTE_PRINC")
    add_text(msp, f"Repart.: {rep}", x + 0.15, sy - 0.12, 0.068, "ARM_FILANTE_REP")
    add_text(msp, "Attentes voile + crosses securite", wx2 + 0.12, sy + draw_h + wall_h * 0.5, 0.065, "ATTENTES_POTEAUX")
    add_text(msp, "Semelle developpee vers l'interieur", sx + 0.30, sy + draw_h * 0.4, 0.060, "DETAILS_SECTIONS")
    add_text(msp, "Beton proprete ep.0.10", px1, py1 - 0.02, 0.06, "DETAILS_SECTIONS")
    add_text(msp, "Ecarteurs 1/1.50 m - sur-prof. gros beton eventuelle", x + 0.15, y + 0.12, 0.058, "DETAILS_SECTIONS")


def draw_sections_panel(
    msp,
    strategy_report: dict[str, Any],
    x: float,
    y: float,
    strip_design: dict[str, Any] | None = None,
    wall_thickness_m: float = 0.20,
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

    # Coupe transversale de la semelle filante (si voiles presents)
    if strip_design and strip_design.get("strip_footings"):
        first_sf = strip_design["strip_footings"][0]
        draw_strip_section_detail(msp, px, py - 0.10, sf=first_sf, wall_thickness_m=wall_thickness_m)
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


def _parse_bars_label(label: str) -> tuple[int, int]:
    """'2HA14' -> (2, 14). Defaut (2, 12)."""
    import re
    m = re.match(r"\s*(\d+)\s*HA\s*(\d+)", str(label or ""))
    if m:
        return int(m.group(1)), int(m.group(2))
    return 2, 12


def draw_beam_section_detail(msp, x, y, title, b, h, top_label, bot_label,
                             stirrup_label, scale=2.0):
    """Coupe transversale type d'une poutre : contour b x h, cadre, aciers
    superieurs/inferieurs, cotes et libelles."""
    W, H = b * scale, h * scale
    c = 0.04 * scale
    add_rect(msp, x, y, x + W, y + H, "DETAILS_SECTIONS")
    add_rect(msp, x + c, y + c, x + W - c, y + H - c, "ARM_PR")  # cadre

    def _bars(n, yy, phi):
        r = max(phi / 1000.0 * scale * 0.5, 0.028)
        if n <= 1:
            xs = [x + W / 2.0]
        else:
            span = (W - 2 * c - 2 * r)
            xs = [x + c + r + span * i / (n - 1) for i in range(n)]
        for bx in xs:
            msp.add_circle((bx, yy), r, dxfattribs={"layer": "ARM_PR"})

    nt, pt = _parse_bars_label(top_label)
    nb, pb = _parse_bars_label(bot_label)
    _bars(nt, y + H - c - 0.06, pt)
    _bars(nb, y + c + 0.06, pb)

    add_text(msp, title, x, y + H + 0.12, 0.10, "DETAILS_TITRES")
    add_text(msp, f"{b:.2f} x {h:.2f} m", x, y - 0.18, 0.09, "DETAILS_SECTIONS")
    add_text(msp, f"Sup {top_label} / Inf {bot_label}", x, y - 0.34, 0.08, "DETAILS_SECTIONS")
    add_text(msp, f"Cadres {stirrup_label}", x, y - 0.50, 0.08, "DETAILS_SECTIONS")


def draw_beam_sections_panel(msp, x, y, beams):
    """Panneau de coupes types des poutres (chainage / PR / liaison)."""
    if not beams:
        return
    w, h = 14.0, 3.6
    draw_panel(msp, "D4 - COUPES TYPES POUTRES (CHAINAGE / REDRESSEMENT / LIAISON)",
               x, y, w, h, "DETAILS_TITRES")
    px = x + 1.10
    py = y + 1.30
    for bd in beams:
        draw_beam_section_detail(msp, px, py, bd["title"], bd["b"], bd["h"],
                                 bd["top"], bd["bot"], bd["stirrup"])
        px += 4.30

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

        # Affichage allege : on espace les barres a l'ecran (x2) pour ne pas
        # confondre avec les semelles isolees adjacentes. L'annotation garde
        # l'espacement reel du calcul. Calques dedies couleur distincte.
        display_spacing = max(spacing * 2.0, 0.30)
        rep_display_spacing = 0.40

        if axis == "V":
            draw_bar_lines_x(msp, xmin, xmax, ymin, ymax, display_spacing, "ARM_FILANTE_PRINC", cover)
            draw_bar_lines_y(msp, xmin, xmax, ymin, ymax, rep_display_spacing, "ARM_FILANTE_REP", cover)
        else:
            draw_bar_lines_y(msp, xmin, xmax, ymin, ymax, display_spacing, "ARM_FILANTE_PRINC", cover)
            draw_bar_lines_x(msp, xmin, xmax, ymin, ymax, rep_display_spacing, "ARM_FILANTE_REP", cover)

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


def draw_strap_beams_on_plan(msp, strap_design, occupied=None):
    """
    Dessine les poutres de redressement (PR) sur le plan : contour de la poutre
    (rectangle oriente start->end, largeur b), axe, aciers principaux schematiques
    et annotation a leader. occupied = anti-chevauchement des annotations.
    """
    import math as _m
    if not strap_design:
        return
    if occupied is None:
        occupied = []

    for pr in strap_design.get("strap_beams", []):
        x1, y1 = pr["start"]
        x2, y2 = pr["end"]
        b = float(pr["b_m"])
        dx, dy = x2 - x1, y2 - y1
        L = _m.hypot(dx, dy)
        if L < 1e-6:
            continue
        ux, uy = dx / L, dy / L
        nx, ny = -uy, ux           # normale unitaire
        hw = b / 2.0

        # Contour de la poutre
        p = [(x1 + nx * hw, y1 + ny * hw), (x2 + nx * hw, y2 + ny * hw),
             (x2 - nx * hw, y2 - ny * hw), (x1 - nx * hw, y1 - ny * hw)]
        msp.add_lwpolyline(p, close=True, dxfattribs={"layer": "POUTRE_REDRESSEMENT"})

        # Axe de la poutre (pointille via meme calque)
        msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": "POUTRE_REDRESSEMENT"})

        # Aciers principaux schematiques (2 files proches des faces)
        off = hw - 0.04
        for s in (off, -off):
            msp.add_line((x1 + nx * s, y1 + ny * s), (x2 + nx * s, y2 + ny * s),
                         dxfattribs={"layer": "ARM_PR"})

        # Annotation a leader
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        lines = [f"{pr['id']}  {b:.2f}x{pr['h_m']:.2f}",
                 f"Sup {pr['bars_top']} / Inf {pr['bars_bottom']}"]
        bb = {"xmin": min(x1, x2), "xmax": max(x1, x2),
              "ymin": min(y1, y2), "ymax": max(y1, y2)}
        try:
            label_box = choose_label_box(bbox=bb, lines=lines, occupied=occupied,
                                         text_height=0.09, line_spacing=0.16)
            add_label_lines(msp, label_box, lines, "TEXTES")
            add_leader_to_label(msp, bb, label_box)
            occupied.append(pad_box(label_box, 0.08))
        except Exception:
            add_text(msp, lines[0], mx, my + 0.10, 0.09, "TEXTES")


def draw_perimeter_ties_on_plan(msp, tie_design, occupied=None,
                                layer="LONGRINE", arm_layer="ARM_LONGRINE"):
    """Dessine des poutres de liaison (contour + axe + aciers). Sert aux longrines
    peripheriques et a la poutre de liaison centrale (calques parametrables)."""
    import math as _m
    if not tie_design:
        return
    if occupied is None:
        occupied = []
    for t in tie_design.get("ties", []):
        x1, y1 = t["start"]
        x2, y2 = t["end"]
        b = float(t["b_m"])
        dx, dy = x2 - x1, y2 - y1
        L = _m.hypot(dx, dy)
        if L < 1e-6:
            continue
        ux, uy = dx / L, dy / L
        nx, ny = -uy, ux
        hw = b / 2.0
        p = [(x1 + nx * hw, y1 + ny * hw), (x2 + nx * hw, y2 + ny * hw),
             (x2 - nx * hw, y2 - ny * hw), (x1 - nx * hw, y1 - ny * hw)]
        msp.add_lwpolyline(p, close=True, dxfattribs={"layer": layer})
        off = hw - 0.03
        for s in (off, -off):
            msp.add_line((x1 + nx * s, y1 + ny * s), (x2 + nx * s, y2 + ny * s),
                         dxfattribs={"layer": arm_layer})
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        add_text(msp, f"{t['id']} {b:.2f}x{t['h_m']:.2f}", mx - 0.30, my + 0.04, 0.08, "TEXTES")


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
    strip_wall_thickness_m: float = 0.20,
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

    # Longrines de liaison peripheriques (chainage) entre semelles adjacentes.
    tie_design = None
    try:
        from civil_engine.foundations.longrines import design_perimeter_ties
        tie_design = design_perimeter_ties(model=model, strategy_report=strategy_report)
        draw_perimeter_ties_on_plan(msp, tie_design, occupied)
    except Exception:
        tie_design = None  # le plan reste valide sans longrines

    # Poutres de liaison entre semelles interieures (les deux centrales).
    central_tie_design = None
    try:
        from civil_engine.foundations.longrines import design_central_ties
        central_tie_design = design_central_ties(model=model, strategy_report=strategy_report)
        draw_perimeter_ties_on_plan(msp, central_tie_design, occupied,
                                    layer="POUTRE_LIAISON", arm_layer="ARM_LIAISON")
    except Exception:
        central_tie_design = None  # le plan reste valide sans poutre de liaison centrale

    # Poutres de redressement (PR) pour les semelles excentrees.
    strap_design = None
    try:
        from civil_engine.foundations.poutre_redressement import design_strap_beams
        strap_design = design_strap_beams(model=model, strategy_report=strategy_report)
        draw_strap_beams_on_plan(msp, strap_design, occupied)
    except Exception:
        strap_design = None  # le plan reste valide sans PR

    # Zone tableau à droite
    tx, ty = table_position(model)

    draw_execution_table(
        msp=msp,
        strategy_report=strategy_report,
        reinforcement_report=reinforcement_report,
        x=tx,
        y=ty,
        strip_design=strip_design,
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
        strip_design=strip_design,
        wall_thickness_m=strip_wall_thickness_m,
    )

    # Coupes types des poutres (chainage / PR / liaison) : un panneau dedie.
    beams_sections = []
    try:
        if tie_design and tie_design.get("ties"):
            t = tie_design["ties"][0]
            beams_sections.append({"title": "Chainage (longrine)", "b": t["b_m"], "h": t["h_m"],
                                   "top": "2HA12", "bot": "2HA12", "stirrup": "HA8 e=15"})
        if strap_design and strap_design.get("strap_beams"):
            s = strap_design["strap_beams"][0]
            beams_sections.append({"title": f"Redressement {s['id']}", "b": s["b_m"], "h": s["h_m"],
                                   "top": s["bars_top"], "bot": s["bars_bottom"], "stirrup": "HA8 e=15"})
        if central_tie_design and central_tie_design.get("ties"):
            c = central_tie_design["ties"][0]
            beams_sections.append({"title": f"Liaison centrale {c['id']}", "b": c["b_m"], "h": c["h_m"],
                                   "top": "2HA14", "bot": "2HA14", "stirrup": "HA8 e=15"})
        draw_beam_sections_panel(msp, details_x, details_y - 16.40, beams_sections)
    except Exception:
        pass

    # Details types complementaires importes (poteau, semelle, coupes poutres,
    # chainage, ferraillage escalier...) depuis le gabarit details_standards.dxf.
    try:
        from civil_engine.plans.details_import import place_standard_details
        place_standard_details(doc, x_left=details_x, y_top=details_y - 21.00,
                               target_width=26.0)
    except Exception:
        pass

    cart_values = build_cartouche_values(
        project_name=project_name,
        project_number=project_number,
        plan_title="Plan d'execution fondations",
        date_str=plan_date,
        scale_label=scale_label,
    )

    # Planche A3 en presentation (paperspace) : cadre + cartouche au gabarit
    # reel insere en 1:1 + fenetre cadree sur le plan a l'echelle 1/50.
    # Le cartouche n'est plus duplique en modelspace (presentation propre).
    a3_ok = False
    try:
        from civil_engine.plans.paperspace_layout import setup_a3_plan_sheet
        a3_ok = setup_a3_plan_sheet(
            doc=doc,
            foundation_bbox=bbox,
            values=cart_values,
            scale_denominator=50.0,
        )
    except Exception:
        a3_ok = False

    if not a3_ok:
        # Repli : cartouche insere en modelspace si la planche A3 a echoue.
        cart_w, cart_h = cartouche_size("m", drawing_scale=50.0)
        cartouche_y = details_y - 17.40 - cart_h
        cartouche_x = xmin
        try:
            insert_cartouche(
                target_doc=doc,
                insert_xy=(cartouche_x, cartouche_y),
                values=cart_values,
                target_units="m",
                drawing_scale=50.0,
            )
        except Exception:
            draw_cartouche(msp, cartouche_x, cartouche_y)

    from civil_engine.plans.dxf_finalize import finalize_and_save
    finalize_and_save(doc, output_path)
    return str(output_path)
