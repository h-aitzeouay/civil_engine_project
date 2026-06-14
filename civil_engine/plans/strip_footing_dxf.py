"""
Plan DXF des semelles filantes sous voiles : trace l'emprise, les voiles,
les semelles filantes, les massifs (d'angle et combines poteau-voile),
avec annotations (id, B, H) et cotation simple.

Calques : EMPRISE, VOILE, SEMELLE_FILANTE, MASSIF, TEXTES, COTATION.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import ezdxf


LAYER_COLORS = {
    "EMPRISE": 8,            # gris
    "VOILE": 5,             # bleu
    "SEMELLE_FILANTE": 3,   # vert
    "MASSIF": 1,            # rouge
    "TEXTES": 7,            # noir/blanc
    "COTATION": 4,         # cyan
}


def _ensure_layers(doc) -> None:
    for name, color in LAYER_COLORS.items():
        if name not in doc.layers:
            doc.layers.add(name, color=color)


def _add_text(msp, text, x, y, height=0.18, layer="TEXTES"):
    msp.add_text(text, dxfattribs={"height": height, "layer": layer}).set_placement((x, y))


def _add_rect(msp, b, layer, closed=True):
    msp.add_lwpolyline(
        [(b["xmin"], b["ymin"]), (b["xmax"], b["ymin"]),
         (b["xmax"], b["ymax"]), (b["xmin"], b["ymax"])],
        close=closed, dxfattribs={"layer": layer})


def generate_strip_footings_dxf(
    strip_result: dict[str, Any],
    interference_result: dict[str, Any] | None,
    output_path: str | Path,
    title: str = "PLAN DES SEMELLES FILANTES",
) -> str:
    """
    Genere un DXF des semelles filantes a partir des resultats du pipeline.
    strip_result = body["strip_footings_design"]
    interference_result = body["interference_resolution"] (optionnel)
    """
    doc = ezdxf.new("R2010")
    doc.units = 6  # metres
    _ensure_layers(doc)
    msp = doc.modelspace()

    emprise = strip_result.get("emprise")
    if emprise:
        _add_rect(msp, emprise, "EMPRISE")

    # Titre
    if emprise:
        _add_text(msp, title, emprise["xmin"], emprise["ymax"] + 0.6, 0.35, "TEXTES")
        _add_text(msp, "INGENIERIE.COM - Predimensionnement",
                  emprise["xmin"], emprise["ymax"] + 0.2, 0.20, "TEXTES")

    # Semelles filantes + voiles
    for sf in strip_result.get("strip_footings", []):
        _add_rect(msp, sf["bbox"], "SEMELLE_FILANTE")
        # voile (face mitoyenne -> interieur)
        wb = sf.get("wall_bbox")
        if wb:
            _add_rect(msp, wb, "VOILE")
        # annotation au centre de la semelle
        bb = sf["bbox"]
        cx = 0.5 * (bb["xmin"] + bb["xmax"])
        cy = 0.5 * (bb["ymin"] + bb["ymax"])
        label = f"{sf['id']} B={sf['B_m']:.2f} H={sf['H_m']:.2f}"
        _add_text(msp, label, cx + 0.1, cy, 0.16, "TEXTES")

    # Massifs d'angle (depuis strip_result)
    for m in strip_result.get("massifs", []):
        _add_rect(msp, m["bbox"], "MASSIF")
        bb = m["bbox"]
        _add_text(msp, m["id"], bb["xmin"] + 0.05, bb["ymax"] - 0.25, 0.14, "TEXTES")

    # Massifs locaux poteau-voile (depuis interference_result)
    if interference_result:
        for m in interference_result.get("final_decisions", {}).get("local_massifs", []):
            _add_rect(msp, m["bbox"], "MASSIF")

    # Legende
    if emprise:
        y0 = emprise["ymin"] - 1.2
        _add_text(msp, "Legende : vert=semelle filante, bleu=voile, rouge=massif",
                  emprise["xmin"], y0, 0.16, "TEXTES")

    output_path = str(output_path)
    doc.saveas(output_path)
    return output_path
