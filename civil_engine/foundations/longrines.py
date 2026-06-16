from __future__ import annotations

"""
Longrines / chainages de liaison — predimensionnement.

Relie les semelles peripheriques adjacentes par un reseau de longrines (anneau
de liaison le long des bords de l'emprise). Role : chainer les semelles entre
elles (RPS 2000), reprendre les tassements differentiels et un effort de
traction/compression de liaison sismique.

Hypotheses (preliminaire, a verifier) :
- une semelle est "peripherique" si son centre est a moins de `edge_margin_m`
  d'un bord de l'emprise ;
- les longrines suivent les bords : sur chaque bord on relie les semelles
  consecutives (triees le long du bord) -> segments orthogonaux ;
- effort de liaison indicatif Nt = tie_force_ratio * N_max (RPS, simplifie) ;
- section et ferraillage minimaux constructifs de chainage.
"""

import math
from typing import Any


PI = math.pi


def _bar_area_cm2(diameter_mm: float, count: int) -> float:
    return round(count * PI * (diameter_mm / 10.0) ** 2 / 4.0, 3)


def design_perimeter_ties(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    edge_margin_m: float = 1.50,
    b_m: float = 0.25,
    h_m: float = 0.40,
    fyk_mpa: float = 500.0,
    gamma_s: float = 1.15,
    tie_force_ratio: float = 0.10,
    phi_long_mm: float = 12.0,
    n_long_bars: int = 4,
) -> dict[str, Any]:
    """
    Genere les longrines de liaison entre semelles peripheriques adjacentes.
    """
    final_foundations = [f for f in strategy_report.get("final_foundations", [])
                         if f.get("cx") is not None and f.get("cy") is not None]

    # Emprise (niveau FONDATION)
    emp = None
    for level in model.get("levels", []):
        if level.get("name") == "FONDATION" and level.get("footprints"):
            emp = level["footprints"][0]["bbox"]
            break
    if emp is None:
        return {"status": "WARNING", "message": "Emprise FONDATION introuvable.",
                "ties": [], "totals": {"count": 0}}

    x0, y0, x1, y1 = emp["xmin"], emp["ymin"], emp["xmax"], emp["ymax"]

    def near(v, ref):
        return abs(v - ref) <= edge_margin_m

    # Classement des semelles par bord (un coin peut appartenir a 2 bords)
    edges = {"bottom": [], "top": [], "left": [], "right": []}
    for f in final_foundations:
        cx, cy = float(f["cx"]), float(f["cy"])
        if near(cy, y0):
            edges["bottom"].append(f)
        if near(cy, y1):
            edges["top"].append(f)
        if near(cx, x0):
            edges["left"].append(f)
        if near(cx, x1):
            edges["right"].append(f)

    fyd = fyk_mpa / gamma_s
    as_long = _bar_area_cm2(phi_long_mm, n_long_bars)
    bars_label = f"{n_long_bars}HA{int(phi_long_mm)}"

    ties: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    counter = 0

    def add_edge(footings: list[dict[str, Any]], sort_key) -> None:
        nonlocal counter
        ordered = sorted(footings, key=sort_key)
        for a, b in zip(ordered, ordered[1:]):
            ida, idb = a["id"], b["id"]
            key = tuple(sorted((ida, idb)))
            if key in seen:
                continue
            seen.add(key)
            ax, ay = float(a["cx"]), float(a["cy"])
            bx, by = float(b["cx"]), float(b["cy"])
            L = round(math.hypot(bx - ax, by - ay), 3)
            if L < 1e-3:
                continue
            n_max = max(float(a.get("N_ELS_kN") or 0.0), float(b.get("N_ELS_kN") or 0.0))
            nt = round(tie_force_ratio * n_max, 2)
            counter += 1
            ties.append({
                "id": f"LG{counter:02d}",
                "footing_a": ida, "footing_b": idb,
                "start": [round(ax, 4), round(ay, 4)],
                "end": [round(bx, 4), round(by, 4)],
                "length_m": L,
                "b_m": b_m, "h_m": h_m,
                "tie_force_kN": nt,
                "As_min_cm2": as_long,
                "bars_long": bars_label,
                "stirrups": "HA8 e=15 cm",
                "concrete_m3": round(b_m * h_m * L, 3),
                "steel_kg": round(n_long_bars * (phi_long_mm / 1000.0) ** 2 * PI / 4.0
                                  * L * 7850.0, 2),
                "status": "PRELIMINARY",
                "note": "Longrine de liaison peripherique (chainage). Section/ferraillage minimaux a verifier (RPS 2000).",
            })

    add_edge(edges["bottom"], lambda f: float(f["cx"]))
    add_edge(edges["top"], lambda f: float(f["cx"]))
    add_edge(edges["left"], lambda f: float(f["cy"]))
    add_edge(edges["right"], lambda f: float(f["cy"]))

    totals = {
        "count": len(ties),
        "concrete_m3": round(sum(t["concrete_m3"] for t in ties), 3),
        "steel_kg": round(sum(t["steel_kg"] for t in ties), 2),
        "total_length_m": round(sum(t["length_m"] for t in ties), 2),
    }

    return {
        "status": "OK" if ties else "WARNING",
        "method": "longrines_liaison_peripherique_v1",
        "hypotheses": {
            "edge_margin_m": edge_margin_m, "b_m": b_m, "h_m": h_m,
            "tie_force_ratio": tie_force_ratio,
            "bars_long": bars_label, "fyk_mpa": fyk_mpa,
            "note": "Reseau de liaison peripherique. Effort de liaison et section a confirmer selon RPS 2000 et la note d'hypotheses.",
        },
        "ties": ties,
        "totals": totals,
    }


def design_central_ties(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    edge_margin_m: float = 1.50,
    b_m: float = 0.30,
    h_m: float = 0.45,
    fyk_mpa: float = 500.0,
    gamma_s: float = 1.15,
    phi_long_mm: float = 14.0,
    n_long_bars: int = 4,
) -> dict[str, Any]:
    """
    Poutres de liaison entre les semelles INTERIEURES (non peripheriques), qui
    ne sont pas reprises par l'anneau de longrines. Relie les semelles
    interieures entre elles (chaine par plus proche voisin). Pour deux semelles
    centrales -> une seule poutre de liaison.
    """
    final_foundations = [f for f in strategy_report.get("final_foundations", [])
                         if f.get("cx") is not None and f.get("cy") is not None]

    emp = None
    for level in model.get("levels", []):
        if level.get("name") == "FONDATION" and level.get("footprints"):
            emp = level["footprints"][0]["bbox"]
            break
    if emp is None:
        return {"status": "WARNING", "message": "Emprise FONDATION introuvable.",
                "ties": [], "totals": {"count": 0}}

    x0, y0, x1, y1 = emp["xmin"], emp["ymin"], emp["xmax"], emp["ymax"]

    def is_interior(f):
        cx, cy = float(f["cx"]), float(f["cy"])
        near_edge = (abs(cx - x0) <= edge_margin_m or abs(cx - x1) <= edge_margin_m
                     or abs(cy - y0) <= edge_margin_m or abs(cy - y1) <= edge_margin_m)
        return not near_edge

    interior = [f for f in final_foundations if is_interior(f)]

    as_long = _bar_area_cm2(phi_long_mm, n_long_bars)
    bars_label = f"{n_long_bars}HA{int(phi_long_mm)}"

    ties: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    counter = 0

    # Chaine par plus proche voisin entre semelles interieures.
    for a in interior:
        best = None
        best_d = None
        for b in interior:
            if b is a:
                continue
            d = math.hypot(float(b["cx"]) - float(a["cx"]), float(b["cy"]) - float(a["cy"]))
            if best_d is None or d < best_d:
                best_d, best = d, b
        if best is None:
            continue
        key = tuple(sorted((a["id"], best["id"])))
        if key in seen:
            continue
        seen.add(key)
        ax, ay = float(a["cx"]), float(a["cy"])
        bx, by = float(best["cx"]), float(best["cy"])
        L = round(math.hypot(bx - ax, by - ay), 3)
        if L < 1e-3:
            continue
        counter += 1
        ties.append({
            "id": f"PL{counter:02d}",
            "footing_a": a["id"], "footing_b": best["id"],
            "start": [round(ax, 4), round(ay, 4)],
            "end": [round(bx, 4), round(by, 4)],
            "length_m": L,
            "b_m": b_m, "h_m": h_m,
            "As_min_cm2": as_long,
            "bars_long": bars_label,
            "stirrups": "HA8 e=15 cm",
            "concrete_m3": round(b_m * h_m * L, 3),
            "steel_kg": round(n_long_bars * (phi_long_mm / 1000.0) ** 2 * PI / 4.0
                              * L * 7850.0, 2),
            "status": "PRELIMINARY",
            "note": "Poutre de liaison entre semelles interieures (non reprises par l'anneau peripherique).",
        })

    totals = {
        "count": len(ties),
        "concrete_m3": round(sum(t["concrete_m3"] for t in ties), 3),
        "steel_kg": round(sum(t["steel_kg"] for t in ties), 2),
        "total_length_m": round(sum(t["length_m"] for t in ties), 2),
    }
    return {
        "status": "OK" if ties else "WARNING",
        "method": "poutres_liaison_centrales_v1",
        "hypotheses": {"edge_margin_m": edge_margin_m, "b_m": b_m, "h_m": h_m,
                       "bars_long": bars_label,
                       "note": "Liaison des semelles interieures. Section/ferraillage a confirmer."},
        "ties": ties,
        "totals": totals,
    }
