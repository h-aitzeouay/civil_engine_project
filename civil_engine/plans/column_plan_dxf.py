from __future__ import annotations

"""
Plan de ferraillage des poteaux.

Vue en plan des poteaux (sections + aciers longitudinaux), tableau des poteaux
(section, N_ELU, ferraillage, cadres) et coupe type, avec axes et cartouche.
"""

import math
import re
from pathlib import Path
from typing import Any

import ezdxf

from civil_engine.plans.punching_dxf import (
    add_text, add_rect, draw_axes, draw_emprise_and_columns, get_foundation_bbox,
)
from civil_engine.foundations.column_effective import get_effective_column_boxes
from civil_engine.plans.dxf_finalize import finalize_and_save


def _ensure_layers(doc) -> None:
    layers = {
        "EMPRISE": 7, "POTEAUX": 7, "AXES": 2, "ARM_POTEAU": 1, "CADRES_POTEAUX": 6,
        "TEXTES": 7, "TABLEAU_POTEAUX": 7, "DETAILS_TITRES": 7, "DETAILS_SECTIONS": 3,
        "CARTOUCHE": 7,
    }
    for name, color in layers.items():
        if name not in doc.layers:
            doc.layers.add(name=name, color=color)


def _parse_bars(label: str) -> tuple[int, int]:
    m = re.match(r"\s*(\d+)\s*HA\s*(\d+)", str(label or ""))
    return (int(m.group(1)), int(m.group(2))) if m else (4, 12)


def _draw_bars_in_box(msp, box, count, cover=0.03):
    """Place `count` aciers le long du perimetre interieur de la section."""
    x0, y0 = float(box["xmin"]) + cover, float(box["ymin"]) + cover
    x1, y1 = float(box["xmax"]) - cover, float(box["ymax"]) - cover
    # repartition sur le perimetre du rectangle (au moins aux 4 angles)
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if count > 4:
        # ajouter des barres sur les cotes
        extra = count - 4
        per_side = [0, 0, 0, 0]
        for i in range(extra):
            per_side[i % 4] += 1
        sides = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
                 ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
        for s, (pa, pb) in enumerate(sides):
            for k in range(1, per_side[s] + 1):
                t = k / (per_side[s] + 1)
                pts.append((pa[0] + (pb[0] - pa[0]) * t, pa[1] + (pb[1] - pa[1]) * t))
    r = 0.018
    for (bx, by) in pts:
        msp.add_circle((bx, by), r, dxfattribs={"layer": "ARM_POTEAU"})


def _draw_column_table(msp, columns, x, y):
    add_text(msp, "TABLEAU DES POTEAUX", x, y, 0.22, "TABLEAU_POTEAUX")
    add_text(msp, "ID | a x b (m) | N_ELU (kN) | lambda | Long. | rho% | Cadres",
             x, y - 0.34, 0.11, "TABLEAU_POTEAUX")
    yy = y - 0.60
    for c in columns:
        row = (f"{c['id']} | {c['a_m']}x{c['b_m']} | {c['N_ELU_kN']} | "
               f"{c['slenderness_lambda']} | {c['bars_long']} | {c['rho_percent']} | "
               f"{c['stirrups']}")
        add_text(msp, row, x, yy, 0.092, "TABLEAU_POTEAUX")
        yy -= 0.205


def _draw_column_section_detail(msp, x, y, col):
    """Coupe type d'un poteau : section a x b, aciers, cadre, cotes."""
    scale = 4.0
    a, b = float(col["a_m"]), float(col["b_m"])
    W, H = a * scale, b * scale
    add_text(msp, f"COUPE TYPE POTEAU {col['id']} ({a:.2f}x{b:.2f})", x, y + H + 0.25, 0.13, "DETAILS_TITRES")
    add_rect(msp, x, y, x + W, y + H, "DETAILS_SECTIONS")
    c = 0.03 * scale
    add_rect(msp, x + c, y + c, x + W - c, y + H - c, "CADRES_POTEAUX")  # cadre
    n, phi = _parse_bars(col["bars_long"])
    box = {"xmin": x, "ymin": y, "xmax": x + W, "ymax": y + H}
    _draw_bars_in_box(msp, box, n, cover=c + 0.02)
    add_text(msp, f"Long. {col['bars_long']}", x, y - 0.20, 0.10, "DETAILS_SECTIONS")
    add_text(msp, f"Cadres {col['stirrups']}", x, y - 0.36, 0.085, "DETAILS_SECTIONS")
    add_text(msp, "Enrobage = 25 mm", x, y - 0.52, 0.085, "DETAILS_SECTIONS")


def generate_column_plan_dxf(
    model: dict[str, Any],
    design: dict[str, Any],
    output_path: str | Path,
    project_name: str = "",
    project_number: str = "",
    plan_date: str = "",
    scale_label: str = "1/50",
) -> str:
    output_path = Path(output_path)
    doc = ezdxf.new("R2010")
    doc.units = 6
    _ensure_layers(doc)
    msp = doc.modelspace()

    bbox = get_foundation_bbox(model)
    ty = (float(bbox["ymax"]) + 2.4) if bbox else 13.0
    xmax = float(bbox["xmax"]) if bbox else 15.0
    ymin = float(bbox["ymin"]) if bbox else 0.0

    add_text(msp, "PLAN DE FERRAILLAGE DES POTEAUX", 0.0, ty, 0.32, "TEXTES")
    add_text(msp, "INGENIERIE.COM - sections, aciers longitudinaux + cadres (RPS 2000)",
             0.0, ty - 0.42, 0.16, "TEXTES")

    draw_axes(msp, model)
    draw_emprise_and_columns(msp, model)

    boxes = get_effective_column_boxes(model)
    by_id = {c["id"]: c for c in design.get("columns", [])}
    for cid, box in boxes.items():
        c = by_id.get(cid)
        if not c:
            continue
        n, phi = _parse_bars(c["bars_long"])
        _draw_bars_in_box(msp, box, n)
        add_text(msp, c["bars_long"], float(box["xmax"]) + 0.06, float(box["ymin"]) - 0.06,
                 0.08, "ARM_POTEAU")

    # Tableau des poteaux a droite
    _draw_column_table(msp, design.get("columns", []), xmax + 2.0, ty - 0.5)

    # Coupe type (poteau le plus charge)
    if design.get("columns"):
        worst = max(design["columns"], key=lambda c: c.get("N_ELU_kN", 0.0))
        _draw_column_section_detail(msp, 0.0, ymin - 6.0, worst)

    # Planche A3 + cartouche
    try:
        from civil_engine.plans.cartouche import build_cartouche_values
        from civil_engine.plans.paperspace_layout import setup_a3_plan_sheet
        setup_a3_plan_sheet(
            doc=doc, foundation_bbox=bbox,
            values=build_cartouche_values(
                project_name=project_name, project_number=project_number,
                plan_title="Plan de ferraillage poteaux", date_str=plan_date,
                scale_label=scale_label),
            scale_denominator=50.0)
    except Exception:
        pass

    finalize_and_save(doc, output_path)
    return str(output_path)
