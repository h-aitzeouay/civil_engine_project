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

    readme = work_dir / "README_LIVRABLES.txt"
    readme.write_text(
        "\n".join([
            "DOSSIER FONDATIONS - INGENIERIE.COM",
            "",
            "Contenu :",
            "01_DXF : plans et details graphiques",
            "02_RAPPORTS : note de calcul MD / DOCX / PDF",
            "03_METRE : metrage CSV",
            "04_JSON : rapports de controle et donnees techniques",
            "",
            "Important :",
            "Ce dossier est issu d'un predimensionnement automatique.",
            "Validation par ingenieur structure obligatoire avant execution.",
            "",
            "En cas de livrable secondaire manquant, consulter :",
            "04_JSON/00_package_generation_log.json",
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
