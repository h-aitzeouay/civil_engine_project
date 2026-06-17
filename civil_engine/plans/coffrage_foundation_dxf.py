from __future__ import annotations

"""
Plan de COFFRAGE des fondations.

Vue geometrique du beton (emprise, poteaux, semelles, longrines/PR/liaison,
voiles) avec axes et cotation, SANS ferraillage. Document distinct du plan
d'execution (ferraillage), conforme au decoupage usuel coffrage / ferraillage.
"""

import math
from pathlib import Path
from typing import Any

import ezdxf

from civil_engine.plans.punching_dxf import (
    add_text,
    add_rect,
    draw_axes,
    draw_emprise_and_columns,
    draw_final_foundations_only,
    get_foundation_bbox,
)
from civil_engine.plans.dxf_finalize import finalize_and_save


def _ensure_layers(doc) -> None:
    layers = {
        "EMPRISE": 7, "POTEAUX": 7, "AXES": 2, "COTATIONS_AXES": 4,
        "CENTRE_CHARGE": 4, "SI": 3, "SE": 30, "SC": 5, "RL": 140,
        "VOILE_FONDATION": 5, "LONGRINE": 4, "POUTRE_REDRESSEMENT": 30,
        "POUTRE_LIAISON": 3, "TEXTES": 7, "CARTOUCHE": 7,
        "TABLEAU_COFFRAGE": 7, "DETAILS_TITRES": 7,
    }
    for name, color in layers.items():
        if name not in doc.layers:
            doc.layers.add(name=name, color=color)


def _draw_beam_outlines(msp, design, layer, key) -> None:
    """Contour beton des poutres (sans ferraillage) + repere b x h."""
    for t in (design or {}).get(key, []):
        x1, y1 = t["start"]
        x2, y2 = t["end"]
        b = float(t["b_m"])
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy)
        if L < 1e-6:
            continue
        ux, uy = dx / L, dy / L
        nx, ny = -uy, ux
        hw = b / 2.0
        p = [(x1 + nx * hw, y1 + ny * hw), (x2 + nx * hw, y2 + ny * hw),
             (x2 - nx * hw, y2 - ny * hw), (x1 - nx * hw, y1 - ny * hw)]
        msp.add_lwpolyline(p, close=True, dxfattribs={"layer": layer})
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        add_text(msp, f"{t['id']} {b:.2f}x{t['h_m']:.2f}", mx - 0.30, my + 0.05, 0.085, "TEXTES")


def _draw_coffrage_table(msp, strategy_report, x, y) -> None:
    add_text(msp, "TABLEAU COFFRAGE - SEMELLES", x, y, 0.20, "TABLEAU_COFFRAGE")
    add_text(msp, "ID | Type | Poteau | A (m) | B (m) | H (m)", x, y - 0.32, 0.11, "TABLEAU_COFFRAGE")
    yy = y - 0.56
    for f in strategy_report.get("final_foundations", []):
        cols = ",".join(f.get("columns", []))
        row = (f"{f.get('id','-')} | {f.get('type','-')} | {cols} | "
               f"{f.get('A_m','-')} | {f.get('B_m','-')} | {f.get('H_m','-')}")
        add_text(msp, row, x, yy, 0.095, "TABLEAU_COFFRAGE")
        yy -= 0.20


def generate_coffrage_foundation_dxf(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
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

    add_text(msp, "PLAN DE COFFRAGE - FONDATIONS", 0.0, ty, 0.32, "TEXTES")
    add_text(msp, "INGENIERIE.COM - geometrie beton + cotation (sans ferraillage)",
             0.0, ty - 0.42, 0.16, "TEXTES")

    draw_axes(msp, model)
    draw_emprise_and_columns(msp, model)
    draw_final_foundations_only(msp, strategy_report)

    # Poutres (contours beton seulement)
    try:
        from civil_engine.foundations.longrines import design_perimeter_ties, design_central_ties
        from civil_engine.foundations.poutre_redressement import design_strap_beams
        _draw_beam_outlines(msp, design_perimeter_ties(model=model, strategy_report=strategy_report),
                            "LONGRINE", "ties")
        _draw_beam_outlines(msp, design_strap_beams(model=model, strategy_report=strategy_report),
                            "POUTRE_REDRESSEMENT", "strap_beams")
        _draw_beam_outlines(msp, design_central_ties(model=model, strategy_report=strategy_report),
                            "POUTRE_LIAISON", "ties")
    except Exception:
        pass

    # Tableau coffrage a droite du plan
    _draw_coffrage_table(msp, strategy_report, xmax + 2.0, ty - 0.5)

    # Planche A3 (paperspace) + cartouche
    try:
        from civil_engine.plans.cartouche import build_cartouche_values
        from civil_engine.plans.paperspace_layout import setup_a3_plan_sheet
        setup_a3_plan_sheet(
            doc=doc, foundation_bbox=bbox,
            values=build_cartouche_values(
                project_name=project_name, project_number=project_number,
                plan_title="Plan de coffrage fondations", date_str=plan_date,
                scale_label=scale_label),
            scale_denominator=50.0)
    except Exception:
        pass

    finalize_and_save(doc, output_path)
    return str(output_path)
