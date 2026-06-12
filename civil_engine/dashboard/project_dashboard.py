from __future__ import annotations

from typing import Any


def status_to_bool(status: str | None) -> bool:
    return str(status or "").upper() == "OK"


def summarize_foundations(strategy_report: dict[str, Any]) -> dict[str, Any]:
    by_type: dict[str, int] = {}

    h_values: dict[str, list[str]] = {}

    for item in strategy_report.get("final_foundations", []):
        ftype = str(item.get("type", "-"))
        by_type[ftype] = by_type.get(ftype, 0) + 1

        h = str(item.get("H_m", "-"))
        h_values.setdefault(h, []).append(str(item.get("id", "-")))

    return {
        "count": len(strategy_report.get("final_foundations", [])),
        "by_type": by_type,
        "thickness_groups": h_values,
        "warnings_count": len(strategy_report.get("warnings", [])),
        "errors_count": len(strategy_report.get("errors", [])),
    }


def summarize_reinforcement(reinforcement_final_report: dict[str, Any]) -> dict[str, Any]:
    checks = reinforcement_final_report.get("checks", [])

    by_status: dict[str, int] = {}

    for item in checks:
        status = str(item.get("status", "-"))
        by_status[status] = by_status.get(status, 0) + 1

    return {
        "status": reinforcement_final_report.get("status", "-"),
        "checks_count": len(checks),
        "by_status": by_status,
        "errors_count": len(reinforcement_final_report.get("errors", [])),
        "warnings_count": len(reinforcement_final_report.get("warnings", [])),
    }


def summarize_punching(punching_final_report: dict[str, Any]) -> dict[str, Any]:
    checks = punching_final_report.get("checks", [])

    worst_util = 0.0
    worst_foundation = "-"

    by_status: dict[str, int] = {}

    for item in checks:
        status = str(item.get("status", "-"))
        by_status[status] = by_status.get(status, 0) + 1

        util = float(item.get("worst_utilization") or 0.0)

        if util > worst_util:
            worst_util = util
            worst_foundation = str(item.get("foundation_id", "-"))

    return {
        "status": punching_final_report.get("status", "-"),
        "checks_count": len(checks),
        "by_status": by_status,
        "worst_foundation": worst_foundation,
        "worst_utilization": round(worst_util, 3),
        "errors_count": len(punching_final_report.get("errors", [])),
        "warnings_count": len(punching_final_report.get("warnings", [])),
    }


def summarize_anchorage(anchorage_report: dict[str, Any]) -> dict[str, Any]:
    rows = anchorage_report.get("rows", [])

    shapes: dict[str, int] = {}

    for row in rows:
        anchorage = row.get("anchorage", {})
        shape = str(anchorage.get("recommended_shape", "-"))
        shapes[shape] = shapes.get(shape, 0) + 1

    return {
        "status": anchorage_report.get("status", "-"),
        "rows_count": len(rows),
        "recommended_shapes": shapes,
        "execution_policy": anchorage_report.get("anchorage_execution_policy", {}),
    }


def summarize_boq(boq_report: dict[str, Any]) -> dict[str, Any]:
    totals = boq_report.get("totals", {})

    return {
        "concrete_m3": totals.get("concrete_m3", 0.0),
        "clean_concrete_m3": totals.get("clean_concrete_m3", 0.0),
        "formwork_m2": totals.get("formwork_m2", 0.0),
        "foundation_steel_kg": totals.get("foundation_steel_kg", 0.0),
        "starter_steel_kg": totals.get("starter_steel_kg", 0.0),
        "total_steel_kg": totals.get("total_steel_kg", 0.0),
    }


def build_project_dashboard(
    project_name: str,
    strategy_report: dict[str, Any],
    reinforcement_final_report: dict[str, Any],
    punching_final_report: dict[str, Any],
    anchorage_report: dict[str, Any],
    boq_report: dict[str, Any],
    quality_report: dict[str, Any],
) -> dict[str, Any]:
    quality_status = str(quality_report.get("status", "-"))
    reinforcement_status = str(reinforcement_final_report.get("status", "-"))
    punching_status = str(punching_final_report.get("status", "-"))
    anchorage_status = str(anchorage_report.get("status", "-"))

    blocking_reasons: list[str] = []

    if quality_status != "OK":
        blocking_reasons.append(f"Controle qualite = {quality_status}")

    if reinforcement_status != "OK":
        blocking_reasons.append(f"Ferraillage = {reinforcement_status}")

    if punching_status != "OK":
        blocking_reasons.append(f"Poinconnement = {punching_status}")

    # Les ancrages OK_WITH_EXECUTION_NOTES sont acceptables pour le tableau de bord,
    # car une disposition constructive 135° est imposée.
    anchorage_acceptable = anchorage_status in ["OK", "OK_WITH_EXECUTION_NOTES"]

    if not anchorage_acceptable:
        blocking_reasons.append(f"Ancrages = {anchorage_status}")

    ready_to_deliver = len(blocking_reasons) == 0

    return {
        "status": "OK" if ready_to_deliver else "NOT_READY",
        "method": "project_dashboard_v0_34",
        "project_name": project_name,
        "ready_to_deliver": ready_to_deliver,
        "blocking_reasons": blocking_reasons,
        "global_status": {
            "quality": quality_status,
            "reinforcement": reinforcement_status,
            "punching": punching_status,
            "anchorage": anchorage_status,
        },
        "summaries": {
            "foundations": summarize_foundations(strategy_report),
            "reinforcement": summarize_reinforcement(reinforcement_final_report),
            "punching": summarize_punching(punching_final_report),
            "anchorage": summarize_anchorage(anchorage_report),
            "boq": summarize_boq(boq_report),
            "quality": quality_report.get("summary", {}),
        },
        "deliverables": {
            "zip": "/project-package-zip",
            "plan_execution_dxf": "/execution-foundation-dxf",
            "sections_dxf": "/foundation-sections-dxf",
            "boq_json": "/boq-foundations",
            "boq_csv": "/boq-foundations-csv",
            "calculation_report_json": "/calculation-report",
            "calculation_report_md": "/calculation-report-md",
            "calculation_report_docx": "/calculation-report-docx",
            "calculation_report_pdf": "/calculation-report-pdf",
            "quality_check": "/project-quality-check",
            "quality_remediation": "/project-quality-remediation",
        },
        "engineering_notes": [
            "Le tableau de bord est basé sur la configuration corrigée.",
            "Les épaisseurs H corrigées doivent être reprises dans les plans et la note.",
            "Les attentes poteaux sont sécurisées par crosses/crochets 135 degrés.",
            "Validation finale par ingénieur structure obligatoire avant exécution.",
        ],
    }
