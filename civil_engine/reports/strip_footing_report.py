"""
Section "Semelles filantes sous voiles" pour la note de calcul.
Genere du Markdown (reutilisable en DOCX/PDF par la chaine existante).
"""
from __future__ import annotations

from typing import Any
from pathlib import Path


def fmt(value: Any, ndigits: int = 2) -> str:
    try:
        return f"{float(value):.{ndigits}f}"
    except (TypeError, ValueError):
        return str(value)


def _md_table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(out)


def build_strip_footing_section(
    strip_pipeline_result: dict[str, Any],
) -> str:
    """
    Construit la section Markdown des semelles filantes a partir de la
    reponse complete de l'endpoint /strip-footings (pipeline v2).
    """
    lines: list[str] = []
    hyp = strip_pipeline_result.get("hypotheses", {})
    wlt = strip_pipeline_result.get("wall_load_takedown", {})
    design = strip_pipeline_result.get("strip_footings_design", {})
    intf = strip_pipeline_result.get("interference_resolution", {})
    boq = strip_pipeline_result.get("boq", {})

    walls = wlt.get("walls", [])
    if not walls:
        return "## Semelles filantes sous voiles\n\n_Aucun voile (calque VOILE-AXE) dans ce projet._\n"

    lines.append("## Semelles filantes sous voiles")
    lines.append("")
    lines.append("### Hypothèses")
    lines.append(_md_table(
        ["Paramètre", "Valeur"],
        [["Contrainte admissible du sol", f"{fmt(hyp.get('q_allowable_kPa'))} kPa"],
         ["Épaisseur des voiles", f"{fmt(hyp.get('wall_thickness_m'))} m"],
         ["Hauteur d'étage", f"{fmt(hyp.get('storey_height_m'))} m"],
         ["G plancher / terrasse", f"{fmt(hyp.get('g_floor_kN_m2'))} / {fmt(hyp.get('g_terrace_kN_m2'))} kN/m²"],
         ["Q plancher / terrasse", f"{fmt(hyp.get('q_floor_kN_m2'))} / {fmt(hyp.get('q_terrace_kN_m2'))} kN/m²"],
         ["Béton / Acier", f"fck={fmt(hyp.get('fck_mpa'))} MPa / fyk={fmt(hyp.get('fyk_mpa'))} MPa"]]))
    lines.append("")

    # Descente de charges lineaire
    lines.append("### Descente de charges linéaire des voiles")
    rows = []
    for w in walls:
        rows.append([
            w["id"],
            f"{fmt(w['length_m'])} m",
            f"{fmt(w['tributary_band_width_m'])} m",
            ", ".join(w.get("levels_supported", [])),
            f"{fmt(w['n_sls_kN_per_m'])}",
            f"{fmt(w['n_uls_kN_per_m'])}",
        ])
    lines.append(_md_table(
        ["Voile", "Longueur", "Bande trib.", "Niveaux portés", "N ELS (kN/ml)", "N ELU (kN/ml)"],
        rows))
    lines.append("")

    # Dimensionnement des semelles filantes
    lines.append("### Dimensionnement des semelles filantes")
    rows = []
    for sf in design.get("strip_footings", []):
        reinf = sf.get("reinforcement", {})
        rows.append([
            sf["id"], sf.get("wall_id", ""),
            f"{fmt(sf['A_m'])}", f"{fmt(sf['B_m'])}", f"{fmt(sf['H_m'])}",
            f"{fmt(sf['q_sls_kPa'])}",
            reinf.get("main_bottom", ""),
            sf.get("status", ""),
        ])
    lines.append(_md_table(
        ["Semelle", "Voile", "L (m)", "B (m)", "H (m)", "q ELS (kPa)", "Ferraillage principal", "Statut"],
        rows))
    lines.append("")

    # Massifs et interferences
    massifs = design.get("massifs", [])
    n_local = len(intf.get("final_decisions", {}).get("local_massifs", [])) if intf else 0
    n_removed = len(intf.get("final_decisions", {}).get("isolated_footings_to_remove", [])) if intf else 0
    if massifs or n_local:
        lines.append("### Jonctions et massifs")
        lines.append(f"- Massifs d'angle (jonction filante↔filante) : **{len(massifs)}**")
        lines.append(f"- Massifs locaux combinés poteau-voile : **{n_local}**")
        lines.append(f"- Semelles isolées absorbées/fusionnées : **{n_removed}**")
        lines.append("")

    # BOQ
    if boq:
        tot = boq.get("totals", {})
        lines.append("### Métré estimatif des semelles filantes")
        lines.append(_md_table(
            ["Désignation", "Quantité"],
            [["Béton semelles filantes", f"{fmt(tot.get('strip_concrete_m3'))} m³"],
             ["Béton de propreté", f"{fmt(tot.get('clean_concrete_m3'))} m³"],
             ["Coffrage", f"{fmt(tot.get('formwork_m2'))} m²"],
             ["Acier", f"{fmt(tot.get('steel_kg'), 1)} kg"],
             ["Béton massifs (angle + locaux)", f"{fmt(tot.get('massifs_concrete_m3'))} m³"],
             ["**Béton total**", f"**{fmt(tot.get('total_concrete_m3'))} m³**"]]))
        lines.append("")

    lines.append("### Réserves")
    lines.append("- Prédimensionnement : charges linéaires par bande tributaire (demi-portée).")
    lines.append("- Semelles de rive mitoyennes excentrées : excentricité à reprendre par poutre de redressement ou disposition équivalente.")
    lines.append("- Métré préliminaire : validation par métré détaillé obligatoire avant marché.")
    lines.append("")

    return "\n".join(lines)


def export_strip_footing_section_md(
    strip_pipeline_result: dict[str, Any],
    output_path: str | Path,
) -> str:
    output_path = Path(output_path)
    content = build_strip_footing_section(strip_pipeline_result)
    output_path.write_text(content, encoding="utf-8")
    return str(output_path)
