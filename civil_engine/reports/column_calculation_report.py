from __future__ import annotations

"""
Note de calcul des poteaux (predimensionnement).

Synthese du dimensionnement EC2 (interaction N-M biaxiale + excentricite minimale
+ flambement) et des dispositions parasismiques RPS 2000 pour les cadres.
Export Markdown ; ne remplace pas une note reglementaire signee.
"""

from pathlib import Path
from typing import Any


def _fmt(v: Any, n: int = 2) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.{n}f}"
    return str(v)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def build_column_report_md(design: dict[str, Any], hypotheses: dict[str, Any] | None = None) -> str:
    hyp = hypotheses or design.get("hypotheses", {})
    cols = design.get("columns", [])
    summ = design.get("summary", {})

    lines: list[str] = []
    lines.append("# NOTE DE CALCUL POTEAUX — PRÉDIMENSIONNEMENT")
    lines.append("")
    lines.append("## 1. Méthode")
    lines.append("")
    lines.append("- Dimensionnement de section EC2 : compatibilité des déformations, "
                 "interaction N-M biaxiale, excentricité minimale.")
    lines.append("- Vérification du flambement (élancement λ = l0/i).")
    lines.append("- Cadres selon **RPS 2000 (éd. 2011)** : zone critique "
                 "L.C = max(He/6, plus grande dimension, 45 cm).")
    lines.append("")
    lines.append("## 2. Hypothèses")
    lines.append("")
    lines.append(_table(["Paramètre", "Valeur"], [
        ["fck", f"{_fmt(hyp.get('fck_mpa'))} MPa"],
        ["fyk", f"{_fmt(hyp.get('fyk_mpa'))} MPa"],
        ["gamma_s", _fmt(hyp.get("gamma_s"))],
        ["gamma_c", _fmt(hyp.get("gamma_c"))],
        ["Enrobage", f"{_fmt(hyp.get('cover_m'))} m"],
        ["Hauteur d'étage", f"{_fmt(hyp.get('storey_height_m'))} m"],
        ["rho min / max", f"{_fmt(hyp.get('rho_min'))} / {_fmt(hyp.get('rho_max'))}"],
    ]))
    lines.append("")
    lines.append("## 3. Tableau des poteaux")
    lines.append("")
    rows = []
    for c in cols:
        rows.append([
            c.get("id"), f"{c.get('a_m')}x{c.get('b_m')}",
            f"{_fmt(c.get('niveau_depart_m'))} -> {_fmt(c.get('niveau_arrivee_m'))}",
            _fmt(c.get("N_ELU_kN"), 1), _fmt(c.get("slenderness_lambda"), 1),
            c.get("bars_long"), _fmt(c.get("rho_percent")), _fmt(c.get("utilization"), 3),
            c.get("stirrups"),
        ])
    lines.append(_table(
        ["ID", "a x b (m)", "Niveaux", "N_ELU (kN)", "λ", "Long.", "ρ%", "Util.", "Cadres"],
        rows))
    lines.append("")
    lines.append("## 4. Métré poteaux")
    lines.append("")
    qrows = [[c.get("id"), _fmt(c.get("height_m")), _fmt(c.get("concrete_m3"), 3),
              _fmt(c.get("long_steel_kg")), _fmt(c.get("stirrup_steel_kg")), _fmt(c.get("steel_kg"))]
             for c in cols]
    lines.append(_table(
        ["ID", "Hauteur (m)", "Béton (m³)", "Acier long. (kg)", "Cadres (kg)", "Acier total (kg)"],
        qrows))
    lines.append("")
    lines.append(f"**Totaux poteaux** — Béton : {_fmt(summ.get('total_concrete_m3'), 3)} m³ | "
                 f"Acier : {_fmt(summ.get('total_steel_kg'))} kg | "
                 f"Nombre : {summ.get('count', '-')}")
    lines.append("")
    lines.append("## 5. Réserves et validations obligatoires")
    lines.append("")
    for r in [
        "Note de prédimensionnement automatique.",
        "Les effets du 2e ordre (poteaux élancés) doivent être vérifiés selon la méthode réglementaire.",
        "Les dispositions sismiques détaillées (RPS 2000 / EC8) doivent être complétées selon le projet.",
        "La vérification réglementaire finale doit être effectuée par un ingénieur structure habilité.",
        "Les moments réels (portiques, séisme) doivent être intégrés à la note finale.",
    ]:
        lines.append(f"- {r}")
    lines.append("")
    lines.append("---")
    lines.append("Document généré automatiquement par INGENIERIE.COM STRUCTURAL AI.")
    return "\n".join(lines)


def export_column_report_md(design: dict[str, Any], output_path: str | Path,
                            hypotheses: dict[str, Any] | None = None) -> str:
    output_path = Path(output_path)
    output_path.write_text(build_column_report_md(design, hypotheses), encoding="utf-8")
    return str(output_path)
