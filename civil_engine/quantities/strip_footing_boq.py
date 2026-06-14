"""
Metre (BOQ) des semelles filantes sous voiles : volume de beton,
beton de proprete, coffrage et acier estime.
"""
from __future__ import annotations

from typing import Any
import math


def unit_weight_steel_kg_m(diameter_mm: float) -> float:
    """Poids lineaire acier HA : kg/m = phi^2 / 162."""
    return (diameter_mm * diameter_mm) / 162.0


def _as_used_to_bars_per_m(as_mm2_per_m: float, phi_mm: float) -> float:
    """Nombre de barres par metre pour atteindre As (mm2/m)."""
    a_bar = math.pi * phi_mm * phi_mm / 4.0
    if a_bar <= 0:
        return 0.0
    return as_mm2_per_m / a_bar


def strip_footings_boq(
    strip_result: dict[str, Any],
    interference_result: dict[str, Any] | None = None,
    clean_concrete_thickness_m: float = 0.10,
    steel_overlap_factor: float = 1.10,
) -> dict[str, Any]:
    """
    Calcule le metre des semelles filantes.

    Pour chaque semelle filante (longueur A, largeur B, hauteur H) :
    - beton = A * B * H
    - beton de proprete = A * B * ep_proprete
    - coffrage lateral = 2 * A * H (les deux faces laterales)
    - acier transversal (principal) : barres sur la longueur A,
      de longueur ~ B chacune, espacees de s.
    - acier longitudinal (repartition) : barres sur la largeur B,
      de longueur ~ A chacune.
    """
    items = []
    total_concrete = 0.0
    total_clean = 0.0
    total_formwork = 0.0
    total_steel = 0.0

    for sf in strip_result.get("strip_footings", []):
        A = float(sf.get("A_m", 0.0))     # longueur
        B = float(sf.get("B_m", 0.0))     # largeur
        H = float(sf.get("H_m", 0.0))     # hauteur

        concrete = A * B * H
        clean = A * B * clean_concrete_thickness_m
        formwork = 2.0 * A * H

        # Acier
        reinf = sf.get("reinforcement", {})
        phi_main = float(reinf.get("main_phi_mm", 12.0))
        spacing = float(reinf.get("main_spacing_m", 0.20)) or 0.20

        # transversal : n = A/spacing barres, longueur ~ B
        n_trans = A / spacing
        len_trans = n_trans * B
        # longitudinal (repartition) : ~ B/spacing barres, longueur ~ A
        n_long = B / spacing
        len_long = n_long * A

        steel_len = (len_trans + len_long) * steel_overlap_factor
        steel_kg = steel_len * unit_weight_steel_kg_m(phi_main)

        items.append({
            "id": sf.get("id"),
            "wall_id": sf.get("wall_id"),
            "A_m": round(A, 2), "B_m": round(B, 2), "H_m": round(H, 2),
            "concrete_m3": round(concrete, 3),
            "clean_concrete_m3": round(clean, 3),
            "formwork_m2": round(formwork, 2),
            "steel_kg": round(steel_kg, 1),
        })
        total_concrete += concrete
        total_clean += clean
        total_formwork += formwork
        total_steel += steel_kg

    # Massifs (angle + locaux poteau-voile) : volume beton seul (estimatif)
    massif_items = []
    massif_concrete = 0.0

    def _massif_vol(m):
        bb = m["bbox"]
        w = bb["xmax"] - bb["xmin"]
        h = bb["ymax"] - bb["ymin"]
        H = float(m.get("H_m", 0.35))
        return w * h * H

    for m in strip_result.get("massifs", []):
        v = _massif_vol(m)
        massif_items.append({"id": m["id"], "type": m.get("type"), "concrete_m3": round(v, 3)})
        massif_concrete += v

    if interference_result:
        for m in interference_result.get("final_decisions", {}).get("local_massifs", []):
            v = _massif_vol(m)
            massif_items.append({"id": m["id"], "type": m.get("type"), "concrete_m3": round(v, 3)})
            massif_concrete += v

    return {
        "status": "OK",
        "method": "strip_footing_boq_v1",
        "strip_footings": items,
        "massifs": massif_items,
        "totals": {
            "strip_concrete_m3": round(total_concrete, 2),
            "clean_concrete_m3": round(total_clean, 2),
            "formwork_m2": round(total_formwork, 2),
            "steel_kg": round(total_steel, 1),
            "massifs_concrete_m3": round(massif_concrete, 2),
            "total_concrete_m3": round(total_concrete + massif_concrete, 2),
        },
        "notes": [
            "Metre preliminaire. Acier estime a partir du ferraillage type.",
            "Recouvrements pris en compte par un facteur forfaitaire.",
            "Validation par metre detaille obligatoire avant marche.",
        ],
    }
