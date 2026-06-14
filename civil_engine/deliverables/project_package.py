from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any


def write_json(data: dict[str, Any], path: Path) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def safe_generate(
    label: str,
    func,
    errors: list[dict[str, str]],
    **kwargs,
) -> None:
    try:
        func(**kwargs)
    except Exception as exc:
        errors.append({
            "livrable": label,
            "error": str(exc),
        })


def generate_project_package_zip(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    reinforcement_report: dict[str, Any],
    reinforcement_final_report: dict[str, Any],
    punching_final_report: dict[str, Any],
    anchorage_report: dict[str, Any],
    boq_report: dict[str, Any],
    calculation_report: dict[str, Any],
    output_dir: str | Path,
    starter_diameter_mm: float = 14.0,
    stirrup_diameter_mm: float = 8.0,
    stirrup_spacing_cm: float = 15.0,
    stirrup_secondary_spacing_cm: float = 20.0,
    critical_zone_m: float = 0.60,
    cover_m: float = 0.05,
    clean_concrete_m: float = 0.10,
    q_allowable_kPa: float = 200.0,
    wall_thickness_m: float = 0.20,
    storey_height_m: float = 3.00,
    g_floor_kN_m2: float = 5.00,
    q_floor_kN_m2: float = 1.50,
    g_terrace_kN_m2: float = 6.00,
    q_terrace_kN_m2: float = 1.00,
    fck_mpa: float = 25.0,
    fyk_mpa: float = 500.0,
    gamma_s: float = 1.15,
) -> str:
    """
    Génère un ZIP complet du dossier fondations.
    Les imports sont volontairement internes pour éviter de bloquer le démarrage API.
    """

    from civil_engine.plans.execution_foundation_dxf import generate_execution_foundation_dxf
    from civil_engine.plans.foundation_sections_dxf import generate_foundation_sections_dxf
    from civil_engine.plans.anchorage_details_dxf import generate_anchorage_details_dxf
    from civil_engine.plans.starter_bars_dxf import generate_starter_bars_dxf
    from civil_engine.plans.reinforcement_dxf import generate_reinforcement_dxf
    from civil_engine.quantities.foundation_boq import export_boq_csv
    from civil_engine.reports.foundation_calculation_report import export_calculation_report_md
    from civil_engine.reports.foundation_report_exports import (
        export_calculation_report_docx,
        export_calculation_report_pdf,
    )

    # --- Calcul des semelles filantes sous voiles (si voiles presents) ---
    strip_design_pkg = None
    try:
        from civil_engine.engine.wall_load_takedown import compute_wall_load_takedown
        from civil_engine.foundations.strip_footing_under_wall import (
            design_strip_footings_under_walls,
            WallInput as _PkgWallInput,
            Rect as _PkgRect,
        )
        _wlt = compute_wall_load_takedown(
            model=model, wall_thickness_m=wall_thickness_m, storey_height_m=storey_height_m,
            g_floor_kN_m2=g_floor_kN_m2, q_floor_kN_m2=q_floor_kN_m2,
            g_terrace_kN_m2=g_terrace_kN_m2, q_terrace_kN_m2=q_terrace_kN_m2,
            gamma_g=1.35, gamma_q=1.50)
        _walls_data = _wlt.get("walls", [])
        if _walls_data:
            _fond = next((l for l in model["levels"] if l["name"] == "FONDATION"),
                         model["levels"][0] if model.get("levels") else None)
            if _fond and _fond.get("footprints"):
                _emp = _fond["footprints"][0]["bbox"]
                _emprise = _PkgRect(_emp["xmin"], _emp["ymin"], _emp["xmax"], _emp["ymax"])
                _walls = [_PkgWallInput(
                    id=w["id"], x1=w["x1"], y1=w["y1"], x2=w["x2"], y2=w["y2"],
                    thickness_m=w["thickness_m"], n_sls_kN_per_m=w["n_sls_kN_per_m"],
                    n_uls_kN_per_m=w["n_uls_kN_per_m"]) for w in _walls_data]
                strip_design_pkg = design_strip_footings_under_walls(
                    walls=_walls, emprise=_emprise, q_allowable_kPa=q_allowable_kPa,
                    fck_mpa=fck_mpa, fyk_mpa=fyk_mpa, gamma_s=gamma_s, cover_m=cover_m,
                    phi_main_mm=12.0, phi_distribution_mm=10.0)
    except Exception:
        strip_design_pkg = None  # le dossier reste valide sans filantes

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    work_dir = output_dir / "DOSSIER_FONDATIONS_INGENIERIE_COM"
    dxf_dir = work_dir / "01_DXF"
    reports_dir = work_dir / "02_RAPPORTS"
    boq_dir = work_dir / "03_METRE"
    json_dir = work_dir / "04_JSON"

    for folder in [dxf_dir, reports_dir, boq_dir, json_dir]:
        folder.mkdir(parents=True, exist_ok=True)

    errors: list[dict[str, str]] = []

    # =====================================================
    # DXF
    # =====================================================

    safe_generate(
        "01_PLAN_EXECUTION_FONDATIONS.dxf",
        generate_execution_foundation_dxf,
        errors,
        model=model,
        strategy_report=strategy_report,
        reinforcement_report=reinforcement_report,
        anchorage_report=anchorage_report,
        output_path=dxf_dir / "01_PLAN_EXECUTION_FONDATIONS.dxf",
        starter_diameter_mm=starter_diameter_mm,
        strip_design=strip_design_pkg,
        strip_wall_thickness_m=wall_thickness_m,
    )

    safe_generate(
        "02_COUPES_DETAILLEES_FONDATIONS.dxf",
        generate_foundation_sections_dxf,
        errors,
        model=model,
        strategy_report=strategy_report,
        reinforcement_report=reinforcement_report,
        anchorage_report=anchorage_report,
        output_path=dxf_dir / "02_COUPES_DETAILLEES_FONDATIONS.dxf",
        cover_m=cover_m,
        clean_concrete_m=clean_concrete_m,
        starter_diameter_mm=starter_diameter_mm,
        stirrup_diameter_mm=stirrup_diameter_mm,
        stirrup_spacing_cm=stirrup_spacing_cm,
        stirrup_secondary_spacing_cm=stirrup_secondary_spacing_cm,
        critical_zone_m=critical_zone_m,
    )

    safe_generate(
        "03_ANCRAGES_RECOUVREMENTS.dxf",
        generate_anchorage_details_dxf,
        errors,
        model=model,
        strategy_report=strategy_report,
        anchorage_report=anchorage_report,
        output_path=dxf_dir / "03_ANCRAGES_RECOUVREMENTS.dxf",
    )

    safe_generate(
        "04_ATTENTES_POTEAUX.dxf",
        generate_starter_bars_dxf,
        errors,
        model=model,
        strategy_report=strategy_report,
        output_path=dxf_dir / "04_ATTENTES_POTEAUX.dxf",
        starter_diameter_mm=starter_diameter_mm,
        stirrup_diameter_mm=stirrup_diameter_mm,
        stirrup_spacing_cm=stirrup_spacing_cm,
        stirrup_secondary_spacing_cm=stirrup_secondary_spacing_cm,
        critical_zone_m=critical_zone_m,
    )

    safe_generate(
        "05_FERRAILLAGE_PRELIMINAIRE.dxf",
        generate_reinforcement_dxf,
        errors,
        model=model,
        strategy_report=strategy_report,
        reinforcement_report=reinforcement_report,
        output_path=dxf_dir / "05_FERRAILLAGE_PRELIMINAIRE.dxf",
    )

    # Poinçonnement DXF optionnel
    try:
        from civil_engine.plans.punching_dxf import generate_punching_dxf

        safe_generate(
            "06_POINCONNEMENT_FINAL.dxf",
            generate_punching_dxf,
            errors,
            model=model,
            strategy_report=strategy_report,
            punching_report=punching_final_report,
            output_path=dxf_dir / "06_POINCONNEMENT_FINAL.dxf",
        )
    except Exception as exc:
        errors.append({
            "livrable": "06_POINCONNEMENT_FINAL.dxf",
            "error": f"Livrable optionnel non genere : {exc}",
        })

    # =====================================================
    # RAPPORTS
    # =====================================================

    safe_generate(
        "NOTE_CALCUL_FONDATIONS.md",
        export_calculation_report_md,
        errors,
        report=calculation_report,
        output_path=reports_dir / "NOTE_CALCUL_FONDATIONS.md",
    )

    # DOCX et PDF sont des livrables obligatoires.
    # Si l'un échoue, on bloque le ZIP pour éviter un dossier incomplet.
    export_calculation_report_docx(
        report=calculation_report,
        output_path=reports_dir / "NOTE_CALCUL_FONDATIONS.docx",
    )

    export_calculation_report_pdf(
        report=calculation_report,
        output_path=reports_dir / "NOTE_CALCUL_FONDATIONS.pdf",
    )

    # =====================================================
    # METRE
    # =====================================================

    safe_generate(
        "METRE_FONDATIONS.csv",
        export_boq_csv,
        errors,
        boq_report=boq_report,
        output_path=boq_dir / "METRE_FONDATIONS.csv",
    )

    # =====================================================
    # JSON
    # =====================================================

    write_json(strategy_report, json_dir / "01_strategy_report.json")
    write_json(reinforcement_report, json_dir / "02_reinforcement_prelim.json")
    write_json(reinforcement_final_report, json_dir / "03_reinforcement_final_check.json")
    write_json(punching_final_report, json_dir / "04_punching_final.json")
    write_json(anchorage_report, json_dir / "05_anchorage_report.json")
    write_json(boq_report, json_dir / "06_boq_report.json")
    write_json(calculation_report, json_dir / "07_calculation_report.json")

    write_json(
        {
            "status": "OK_WITH_WARNINGS" if errors else "OK",
            "generation_errors": errors,
        },
        json_dir / "00_package_generation_log.json",
    )

    # --- Synthese des statuts (deduite des rapports) ---
    from datetime import datetime

    project_name = (
        calculation_report.get("project", {}).get("name")
        or "INGENIERIE.COM - Projet fondations"
    )
    strat_sum = calculation_report.get("strategy_summary", {})
    reinf_sum = calculation_report.get("reinforcement_summary", {})
    punch_sum = calculation_report.get("punching_summary", {})
    boq_tot = boq_report.get("totals", {})

    def _counts(counts: dict) -> str:
        if not counts:
            return "-"
        return ", ".join(f"{k} : {v}" for k, v in counts.items())

    readme = work_dir / "README_LIVRABLES.txt"
    readme.write_text(
        "\n".join([
            "====================================================",
            "  DOSSIER FONDATIONS — INGENIERIE.COM",
            "====================================================",
            "",
            f"Projet      : {project_name}",
            f"Généré le   : {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"Statut      : {'OK AVEC AVERTISSEMENTS' if errors else 'OK'}",
            "",
            "----------------------------------------------------",
            "SYNTHÈSE TECHNIQUE",
            "----------------------------------------------------",
            f"Fondations finales      : {strat_sum.get('foundation_count', '-')}",
            f"Répartition par type    : {_counts(strat_sum.get('by_type', {}))}",
            f"Ferraillage (statut)    : {reinf_sum.get('status', '-')}",
            f"  répartition           : {_counts(reinf_sum.get('by_status', {}))}",
            f"Poinçonnement (statut)  : {punch_sum.get('status', '-')}",
            f"  utilisation max       : {punch_sum.get('worst_utilization', '-')}"
            f" (critique : {punch_sum.get('worst_foundation', '-')})",
            f"Béton fondations        : {boq_tot.get('concrete_m3', '-')} m3",
            f"Acier total             : {boq_tot.get('total_steel_kg', '-')} kg",
            "",
            "----------------------------------------------------",
            "CONTENU DU DOSSIER",
            "----------------------------------------------------",
            "01_DXF      : plans et détails graphiques (cadrés à l'ouverture)",
            "              01_PLAN_EXECUTION_FONDATIONS.dxf",
            "              02_COUPES_DETAILLEES_FONDATIONS.dxf",
            "              03_ANCRAGES_RECOUVREMENTS.dxf",
            "              04_ATTENTES_POTEAUX.dxf",
            "              05_FERRAILLAGE_PRELIMINAIRE.dxf",
            "              06_POINCONNEMENT_FINAL.dxf",
            "02_RAPPORTS : note de calcul (MD / DOCX / PDF)",
            "03_METRE    : métré estimatif (CSV)",
            "04_JSON     : rapports de contrôle et données techniques",
            "",
            "----------------------------------------------------",
            "RÉSERVES",
            "----------------------------------------------------",
            "Ce dossier est issu d'un prédimensionnement automatique.",
            "Validation par ingénieur structure obligatoire avant exécution.",
            "En cas de livrable secondaire manquant, consulter :",
            "  04_JSON/00_package_generation_log.json",
        ]),
        encoding="utf-8",
    )

    zip_path = output_dir / "DOSSIER_COMPLET_FONDATIONS_INGENIERIE_COM.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file_path in work_dir.rglob("*"):
            if file_path.is_file():
                arcname = str(file_path.relative_to(work_dir.parent))
                zipf.write(file_path, arcname=arcname)

    return str(zip_path)
