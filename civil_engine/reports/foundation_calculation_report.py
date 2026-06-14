from __future__ import annotations

from pathlib import Path
from typing import Any
from civil_engine.engine.load_takedown import compute_load_takedown


def fmt(value: Any, ndigits: int = 2) -> str:
    if value is None:
        return "-"

    if isinstance(value, float):
        return f"{value:.{ndigits}f}"

    return str(value)


def fmt_counts(counts: dict[str, Any]) -> str:
    """
    Formate un dictionnaire de comptage en libelle lisible.
    {'SE': 10, 'SI': 2} -> "SE : 10, SI : 2" ; vide -> "-".
    """
    if not counts:
        return "-"
    return ", ".join(f"{key} : {value}" for key, value in counts.items())


def summarize_strategy(strategy_report: dict[str, Any]) -> dict[str, Any]:
    final_foundations = strategy_report.get("final_foundations", [])

    by_type: dict[str, int] = {}

    for item in final_foundations:
        ftype = str(item.get("type", "-"))
        by_type[ftype] = by_type.get(ftype, 0) + 1

    return {
        "method": strategy_report.get("method", "-"),
        "foundation_count": len(final_foundations),
        "by_type": by_type,
        "warnings_count": len(strategy_report.get("warnings", [])),
    }


def summarize_reinforcement(reinforcement_final_report: dict[str, Any]) -> dict[str, Any]:
    checks = reinforcement_final_report.get("checks", [])

    by_status: dict[str, int] = {}

    for check in checks:
        status = str(check.get("status", "-"))
        by_status[status] = by_status.get(status, 0) + 1

    return {
        "status": reinforcement_final_report.get("status"),
        "foundations_checked": len(checks),
        "by_status": by_status,
        "warnings_count": len(reinforcement_final_report.get("warnings", [])),
        "errors_count": len(reinforcement_final_report.get("errors", [])),
    }


def summarize_punching(punching_final_report: dict[str, Any]) -> dict[str, Any]:
    checks = punching_final_report.get("checks", [])

    worst = 0.0
    worst_foundation = "-"

    by_status: dict[str, int] = {}

    for check in checks:
        status = str(check.get("status", "-"))
        by_status[status] = by_status.get(status, 0) + 1

        util = float(check.get("worst_utilization", 0.0))

        if util > worst:
            worst = util
            worst_foundation = str(check.get("foundation_id", "-"))

    return {
        "status": punching_final_report.get("status"),
        "foundations_checked": len(checks),
        "worst_utilization": round(worst, 3),
        "worst_foundation": worst_foundation,
        "by_status": by_status,
        "warnings_count": len(punching_final_report.get("warnings", [])),
        "errors_count": len(punching_final_report.get("errors", [])),
    }


def build_foundation_calculation_report(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    reinforcement_report: dict[str, Any],
    reinforcement_final_report: dict[str, Any],
    punching_final_report: dict[str, Any],
    anchorage_report: dict[str, Any],
    boq_report: dict[str, Any],
    hypotheses: dict[str, Any],
) -> dict[str, Any]:
    """
    Note de calcul automatique synthétique.

    Elle ne remplace pas la note signée par l'ingénieur.
    Elle structure les résultats de prédimensionnement.
    """
    # Descente de charges (recalculée avec les hypothèses du dossier)
    try:
        load_report = compute_load_takedown(
            model=model,
            g_floor_kN_m2=float(hypotheses.get("g_floor_kN_m2", 5.0)),
            q_floor_kN_m2=float(hypotheses.get("q_floor_kN_m2", 1.5)),
            g_terrace_kN_m2=float(hypotheses.get("g_terrace_kN_m2", 6.0)),
            q_terrace_kN_m2=float(hypotheses.get("q_terrace_kN_m2", 1.0)),
            gamma_g=float(hypotheses.get("gamma_g", 1.35)),
            gamma_q=float(hypotheses.get("gamma_q", 1.5)),
        )
    except Exception:
        load_report = {"foundation_columns": [], "totals": {}, "hypotheses": {}}

    # Lien poteau -> semelle (depuis la strategie)
    column_to_foundation = {}
    for f in strategy_report.get("final_foundations", []):
        for col in f.get("columns", []):
            column_to_foundation[col] = f.get("id")

    load_takedown_by_footing = []
    for fc in load_report.get("foundation_columns", []):
        cid = fc.get("column_id")
        load_takedown_by_footing.append({
            "column_id": cid,
            "foundation_id": column_to_foundation.get(cid, "-"),
            "levels_supported": fc.get("levels_supported", []),
            "sum_Gk_kN": fc.get("sum_Gk_kN"),
            "sum_Qk_kN": fc.get("sum_Qk_kN"),
            "N_ELS_kN": fc.get("sum_N_ELS_kN"),
            "N_ELU_kN": fc.get("sum_N_ELU_kN"),
            "combination_elu": load_report.get("hypotheses", {}).get("elu_combination", "1.35G + 1.5Q"),
        })

    return {
        "status": "OK",
        "method": "foundation_calculation_report_v0_30",
        "title": "NOTE DE CALCUL FONDATIONS - PREDIMENSIONNEMENT",
        "project": {
            "name": hypotheses.get("project_name", "INGENIERIE.COM - Projet fondations"),
            "phase": "Predimensionnement / pre-execution",
            "unit_system": "SI",
        },
        "hypotheses": hypotheses,
        "load_takedown": {
            "by_footing": load_takedown_by_footing,
            "totals": load_report.get("totals", {}),
            "elu_combination": load_report.get("hypotheses", {}).get("elu_combination", "1.35G + 1.5Q"),
        },
        "strategy_summary": summarize_strategy(strategy_report),
        "reinforcement_summary": summarize_reinforcement(reinforcement_final_report),
        "punching_summary": summarize_punching(punching_final_report),
        "boq_summary": boq_report.get("totals", {}),
        "foundation_strategy": {
            "final_foundations": strategy_report.get("final_foundations", []),
            "warnings": strategy_report.get("warnings", []),
        },
        "reinforcement": {
            "preliminary": reinforcement_report,
            "final_check": reinforcement_final_report,
        },
        "punching": punching_final_report,
        "anchorage": anchorage_report,
        "boq": boq_report,
        "limitations": [
            "Cette note est une note automatique de prédimensionnement.",
            "Les efforts définitifs issus du modèle structurel doivent être vérifiés.",
            "Les excentricités, moments, efforts horizontaux et combinaisons sismiques doivent être intégrés dans la note finale.",
            "Le poinçonnement doit être validé avec le modèle réglementaire complet.",
            "Les longueurs d'ancrage et de recouvrement doivent être recalculées selon les conditions réelles d'adhérence.",
            "Les plans doivent être contrôlés par un ingénieur structure qualifié avant exécution.",
        ],
    }


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    out = []
    out.append("| " + " | ".join(headers) + " |")
    out.append("| " + " | ".join(["---"] * len(headers)) + " |")

    for row in rows:
        out.append("| " + " | ".join(str(x) for x in row) + " |")

    return "\n".join(out)


def export_calculation_report_md(
    report: dict[str, Any],
    output_path: str | Path,
) -> str:
    output_path = Path(output_path)

    lines: list[str] = []

    lines.append("# NOTE DE CALCUL FONDATIONS — PRÉDIMENSIONNEMENT")
    lines.append("")
    lines.append("## 1. Identification")
    lines.append("")
    lines.append(f"- Projet : {report.get('project', {}).get('name', '-')}")
    lines.append(f"- Phase : {report.get('project', {}).get('phase', '-')}")
    lines.append(f"- Méthode : {report.get('method', '-')}")
    lines.append("")

    h = report.get("hypotheses", {})

    lines.append("## 2. Hypothèses")
    lines.append("")
    lines.append(markdown_table(
        ["Paramètre", "Valeur"],
        [
            ["Contrainte admissible sol", f"{fmt(h.get('q_allowable_kPa'))} kPa"],
            ["fck", f"{fmt(h.get('fck_mpa'))} MPa"],
            ["fyk", f"{fmt(h.get('fyk_mpa'))} MPa"],
            ["gamma_s", fmt(h.get("gamma_s"))],
            ["gamma_c", fmt(h.get("gamma_c"))],
            ["Enrobage", f"{fmt(h.get('cover_m'))} m"],
            ["Béton de propreté", f"{fmt(h.get('clean_concrete_m'))} m"],
            ["Diamètre principal", f"HA{fmt(h.get('phi_main_mm'), 0)}"],
            ["Attentes poteaux", f"HA{fmt(h.get('starter_diameter_mm'), 0)}"],
        ],
    ))
    lines.append("")

    ss = report.get("strategy_summary", {})

    lines.append("## 3. Stratégie de fondations")
    lines.append("")
    lines.append(f"- Nombre de fondations finales : {ss.get('foundation_count', 0)}")
    lines.append(f"- Répartition par type : {fmt_counts(ss.get('by_type', {}))}")
    lines.append(f"- Avertissements : {ss.get('warnings_count', 0)}")
    lines.append("")

    final_foundations = report.get("foundation_strategy", {}).get("final_foundations", [])

    foundation_rows = []

    for f in final_foundations:
        foundation_rows.append([
            f.get("id"),
            f.get("type"),
            ",".join(f.get("columns", [])),
            fmt(f.get("A_m")),
            fmt(f.get("B_m")),
            fmt(f.get("H_m")),
            fmt(f.get("soil_pressure_ELS_kPa")),
            f.get("status", "-"),
        ])

    lines.append(markdown_table(
        ["ID", "Type", "Poteaux", "A", "B", "H", "qELS", "Statut"],
        foundation_rows,
    ))
    lines.append("")

    # --- Section descente de charges par semelle ---
    lt = report.get("load_takedown", {})
    lt_rows = []
    for r in lt.get("by_footing", []):
        lt_rows.append([
            r.get("foundation_id", "-"),
            r.get("column_id", "-"),
            ",".join(r.get("levels_supported", [])) or "-",
            fmt(r.get("sum_Gk_kN")),
            fmt(r.get("sum_Qk_kN")),
            fmt(r.get("N_ELS_kN")),
            fmt(r.get("N_ELU_kN")),
            r.get("combination_elu", "-"),
        ])

    lines.append("## 4. Descente de charges par semelle")
    lines.append("")
    lines.append(f"- Combinaison ELU appliquée : **{lt.get('elu_combination', '1.35G + 1.5Q')}**")
    lines.append("- Combinaison ELS : G + Q")
    lines.append("- N_ELS = Gk + Qk (cumul de tous les niveaux portés)")
    lines.append("- Les surcharges locales (calque CHARGE-Q) sont incluses dans Qk le cas échéant.")
    lines.append("")
    if lt_rows:
        lines.append(markdown_table(
            ["Semelle", "Poteau", "Niveaux portés", "ΣGk (kN)", "ΣQk (kN)", "N_ELS (kN)", "N_ELU (kN)", "Comb. ELU"],
            lt_rows,
        ))
    else:
        lines.append("_Descente de charges non disponible pour ce dossier._")
    lines.append("")
    tot = lt.get("totals", {})
    if tot:
        lines.append(f"**Totaux projet** — ΣGk : {fmt(tot.get('total_Gk_kN'))} kN | "
                     f"ΣQk : {fmt(tot.get('total_Qk_kN'))} kN | "
                     f"N_ELS : {fmt(tot.get('total_N_ELS_kN'))} kN | "
                     f"N_ELU : {fmt(tot.get('total_N_ELU_kN'))} kN")
        lines.append("")

    rs = report.get("reinforcement_summary", {})

    lines.append("## 5. Vérification du ferraillage")
    lines.append("")
    lines.append(f"- Statut global : **{rs.get('status', '-')}**")
    lines.append(f"- Fondations vérifiées : {rs.get('foundations_checked', 0)}")
    lines.append(f"- Répartition : {fmt_counts(rs.get('by_status', {}))}")
    lines.append(f"- Avertissements : {rs.get('warnings_count', 0)}")
    lines.append(f"- Erreurs : {rs.get('errors_count', 0)}")
    lines.append("")

    checks = report.get("reinforcement", {}).get("final_check", {}).get("checks", [])
    reinf_rows = []

    for c in checks:
        reinf_rows.append([
            c.get("foundation_id"),
            c.get("foundation_type"),
            fmt(c.get("rho_l_real_for_punching"), 5),
            c.get("status"),
        ])

    lines.append(markdown_table(
        ["Fondation", "Type", "rho_l réel", "Statut"],
        reinf_rows,
    ))
    lines.append("")

    ps = report.get("punching_summary", {})

    lines.append("## 6. Poinçonnement final")
    lines.append("")
    lines.append(f"- Statut global : **{ps.get('status', '-')}**")
    lines.append(f"- Utilisation maximale : {fmt(ps.get('worst_utilization'), 3)}")
    lines.append(f"- Fondation critique : {ps.get('worst_foundation', '-')}")
    lines.append(f"- Répartition : {fmt_counts(ps.get('by_status', {}))}")
    lines.append("")

    punching_rows = []

    for c in report.get("punching", {}).get("checks", []):
        punching_rows.append([
            c.get("foundation_id"),
            c.get("foundation_type"),
            fmt(c.get("rho_l_real_used"), 5),
            fmt(c.get("worst_utilization"), 3),
            c.get("status"),
        ])

    lines.append(markdown_table(
        ["Fondation", "Type", "rho utilisé", "Taux utilisation", "Statut"],
        punching_rows,
    ))
    lines.append("")

    lines.append("## 7. Ancrages et recouvrements")
    lines.append("")

    anchorage_rows = []

    for row in report.get("anchorage", {}).get("rows", []):
        a = row.get("anchorage", {})
        s = row.get("starter_bars", {})
        anchorage_rows.append([
            row.get("column_id"),
            row.get("foundation_id"),
            s.get("label"),
            fmt(a.get("Lbd_m")),
            fmt(a.get("lap_L0_m")),
            fmt(a.get("hook_leg_m")),
            a.get("recommended_shape"),
        ])

    lines.append(markdown_table(
        ["Poteau", "Fondation", "Attentes", "Lbd", "L0", "Retour", "Forme"],
        anchorage_rows,
    ))
    lines.append("")

    lines.append("## 8. Métré estimatif")
    lines.append("")

    totals = report.get("boq_summary", {})

    lines.append(markdown_table(
        ["Poste", "Quantité"],
        [
            ["Béton fondations", f"{fmt(totals.get('concrete_m3'))} m³"],
            ["Béton de propreté", f"{fmt(totals.get('clean_concrete_m3'))} m³"],
            ["Coffrage latéral", f"{fmt(totals.get('formwork_m2'))} m²"],
            ["Acier fondations", f"{fmt(totals.get('foundation_steel_kg'))} kg"],
            ["Acier attentes", f"{fmt(totals.get('starter_steel_kg'))} kg"],
            ["Acier total", f"{fmt(totals.get('total_steel_kg'))} kg"],
        ],
    ))
    lines.append("")

    lines.append("## 9. Réserves et validations obligatoires")
    lines.append("")

    for item in report.get("limitations", []):
        lines.append(f"- {item}")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("Document généré automatiquement par INGENIERIE.COM STRUCTURAL AI.")
    lines.append("Contrôle et validation par ingénieur structure obligatoire avant exécution.")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return str(output_path)
