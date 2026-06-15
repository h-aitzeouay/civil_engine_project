from __future__ import annotations

"""
Workflow Ifc -> API -> plan PDF + note de calcul.

Assemble les deux livrables principaux demandes a partir de la configuration
fondations calculee :
- le PLAN d'execution fondations rendu en PDF (a partir du DXF) ;
- la NOTE DE CALCUL en PDF (ainsi que MD/DOCX pour reutilisation).

Le DXF source et les JSON techniques sont egalement inclus dans le ZIP.
Les imports lourds sont internes pour ne pas ralentir le demarrage de l'API.
"""

import json
import zipfile
from pathlib import Path
from typing import Any


def _write_json(data: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def generate_ifc_workflow_package(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    reinforcement_report: dict[str, Any],
    anchorage_report: dict[str, Any],
    calculation_report: dict[str, Any],
    output_dir: str | Path,
    starter_diameter_mm: float = 14.0,
    project_name: str = "INGENIERIE.COM - Projet fondations",
    project_number: str = "",
    plan_date: str = "",
    scale_label: str = "1/50",
    strip_design: dict[str, Any] | None = None,
    strip_wall_thickness_m: float = 0.20,
) -> tuple[str, list[dict[str, str]]]:
    """
    Genere le ZIP du workflow IFC (plan PDF + note de calcul PDF).

    Retourne (chemin_zip, erreurs_livrables_secondaires).
    """
    from civil_engine.plans.execution_foundation_dxf import generate_execution_foundation_dxf
    from civil_engine.plans.plan_pdf import export_dxf_to_pdf
    from civil_engine.reports.foundation_calculation_report import export_calculation_report_md
    from civil_engine.reports.foundation_report_exports import (
        export_calculation_report_docx,
        export_calculation_report_pdf,
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    work_dir = output_dir / "WORKFLOW_IFC_FONDATIONS"
    work_dir.mkdir(parents=True, exist_ok=True)

    errors: list[dict[str, str]] = []

    # --- 1) Plan d'execution : DXF puis rendu PDF (livrables obligatoires) ---
    dxf_path = work_dir / "01_PLAN_EXECUTION_FONDATIONS.dxf"
    generate_execution_foundation_dxf(
        model=model,
        strategy_report=strategy_report,
        reinforcement_report=reinforcement_report,
        anchorage_report=anchorage_report,
        output_path=dxf_path,
        starter_diameter_mm=starter_diameter_mm,
        project_name=project_name,
        project_number=project_number,
        plan_date=plan_date,
        scale_label=scale_label,
        strip_design=strip_design,
        strip_wall_thickness_m=strip_wall_thickness_m,
    )

    plan_pdf_path = work_dir / "01_PLAN_EXECUTION_FONDATIONS.pdf"
    export_dxf_to_pdf(dxf_path, plan_pdf_path)

    # --- 2) Note de calcul : PDF (obligatoire) + MD/DOCX (secondaires) ---
    note_pdf_path = work_dir / "02_NOTE_CALCUL_FONDATIONS.pdf"
    export_calculation_report_pdf(report=calculation_report, output_path=note_pdf_path)

    try:
        export_calculation_report_md(
            report=calculation_report,
            output_path=work_dir / "02_NOTE_CALCUL_FONDATIONS.md",
        )
    except Exception as exc:
        errors.append({"livrable": "02_NOTE_CALCUL_FONDATIONS.md", "error": str(exc)})

    try:
        export_calculation_report_docx(
            report=calculation_report,
            output_path=work_dir / "02_NOTE_CALCUL_FONDATIONS.docx",
        )
    except Exception as exc:
        errors.append({"livrable": "02_NOTE_CALCUL_FONDATIONS.docx", "error": str(exc)})

    # --- 3) Donnees techniques ---
    _write_json(model, work_dir / "03_model_ifc.json")
    _write_json(calculation_report, work_dir / "03_calculation_report.json")
    _write_json(
        {"status": "OK_WITH_WARNINGS" if errors else "OK", "generation_errors": errors},
        work_dir / "00_workflow_log.json",
    )

    # --- 4) ZIP ---
    zip_path = output_dir / "WORKFLOW_IFC_PLAN_NOTE_INGENIERIE_COM.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file_path in sorted(work_dir.rglob("*")):
            if file_path.is_file():
                zipf.write(file_path, arcname=str(file_path.relative_to(work_dir.parent)))

    return str(zip_path), errors
