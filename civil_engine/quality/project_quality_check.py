from __future__ import annotations

from typing import Any

from civil_engine.foundations.column_effective import get_effective_column_boxes


def bbox_inside(
    inner: dict[str, float],
    outer: dict[str, float],
    tol: float = 1e-6,
) -> bool:
    return (
        float(inner["xmin"]) >= float(outer["xmin"]) - tol
        and float(inner["xmax"]) <= float(outer["xmax"]) + tol
        and float(inner["ymin"]) >= float(outer["ymin"]) - tol
        and float(inner["ymax"]) <= float(outer["ymax"]) + tol
    )


def get_foundation_level(model: dict[str, Any]) -> dict[str, Any] | None:
    for level in model.get("levels", []):
        if level.get("name") == "FONDATION":
            return level
    return None


def get_emprise_bbox(model: dict[str, Any]) -> dict[str, float] | None:
    foundation = get_foundation_level(model)

    if foundation is None:
        return None

    points = []

    for footprint in foundation.get("footprints", []):
        points.extend(footprint.get("points", []))

    if not points:
        return None

    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]

    return {
        "xmin": min(xs),
        "xmax": max(xs),
        "ymin": min(ys),
        "ymax": max(ys),
    }


def add_issue(
    issues: list[dict[str, Any]],
    severity: str,
    code: str,
    message: str,
    item_id: str | None = None,
) -> None:
    issues.append({
        "severity": severity,
        "code": code,
        "item_id": item_id,
        "message": message,
    })


def check_final_foundations(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    q_allowable_kPa: float,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    final_foundations = strategy_report.get("final_foundations", [])

    if not final_foundations:
        add_issue(
            issues,
            "ERROR",
            "NO_FINAL_FOUNDATIONS",
            "Aucune fondation finale n'a été générée.",
        )
        return issues

    emprise = get_emprise_bbox(model)

    if emprise is None:
        add_issue(
            issues,
            "WARNING",
            "EMPRISE_NOT_FOUND",
            "Emprise de fondation introuvable. Le contrôle de débord n'est pas possible.",
        )

    for element in final_foundations:
        fid = str(element.get("id", "-"))
        bbox = element.get("bbox")

        A_m = float(element.get("A_m") or 0.0)
        B_m = float(element.get("B_m") or 0.0)
        H_m = float(element.get("H_m") or 0.0)

        if A_m <= 0 or B_m <= 0 or H_m <= 0:
            add_issue(
                issues,
                "ERROR",
                "INVALID_FOUNDATION_DIMENSIONS",
                f"Dimensions invalides A={A_m}, B={B_m}, H={H_m}.",
                fid,
            )

        if bbox and emprise and not bbox_inside(bbox, emprise, tol=0.02):
            add_issue(
                issues,
                "ERROR",
                "FOUNDATION_OUTSIDE_EMPRISE",
                "La fondation déborde de l'emprise admissible.",
                fid,
            )

        q_els = element.get("soil_pressure_ELS_kPa")

        if q_els is not None and float(q_els) > q_allowable_kPa * 1.05:
            add_issue(
                issues,
                "ERROR",
                "SOIL_PRESSURE_EXCEEDED",
                f"Contrainte sol ELS {float(q_els):.2f} kPa > q_adm {q_allowable_kPa:.2f} kPa.",
                fid,
            )

        if not element.get("columns"):
            add_issue(
                issues,
                "WARNING",
                "FOUNDATION_WITHOUT_COLUMNS",
                "Fondation finale sans poteau associé.",
                fid,
            )

    return issues


def check_column_coverage(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    columns = set(get_effective_column_boxes(model).keys())

    covered: set[str] = set()

    for element in strategy_report.get("final_foundations", []):
        for column_id in element.get("columns", []):
            covered.add(column_id)

    missing = sorted(columns - covered)
    extra = sorted(covered - columns)

    for column_id in missing:
        add_issue(
            issues,
            "ERROR",
            "COLUMN_NOT_COVERED_BY_FOUNDATION",
            "Poteau non couvert par une fondation finale.",
            column_id,
        )

    for column_id in extra:
        add_issue(
            issues,
            "WARNING",
            "UNKNOWN_COLUMN_REFERENCED",
            "Une fondation référence un poteau non trouvé dans le modèle.",
            column_id,
        )

    return issues


def check_reinforcement_consistency(
    strategy_report: dict[str, Any],
    reinforcement_report: dict[str, Any],
    reinforcement_final_report: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    foundation_ids = {
        str(element.get("id"))
        for element in strategy_report.get("final_foundations", [])
    }

    reinf_ids = {
        str(item.get("foundation_id"))
        for item in reinforcement_report.get("results", [])
    }

    missing = sorted(foundation_ids - reinf_ids)

    for fid in missing:
        add_issue(
            issues,
            "ERROR",
            "MISSING_REINFORCEMENT_RESULT",
            "Fondation finale sans résultat de ferraillage.",
            fid,
        )

    final_status = reinforcement_final_report.get("status")

    if final_status == "NOT_OK":
        add_issue(
            issues,
            "ERROR",
            "REINFORCEMENT_FINAL_NOT_OK",
            "Le contrôle final du ferraillage contient des erreurs.",
        )
    elif final_status == "WARNING":
        add_issue(
            issues,
            "WARNING",
            "REINFORCEMENT_FINAL_WARNING",
            "Le contrôle final du ferraillage contient des avertissements.",
        )

    return issues


def check_punching_consistency(
    punching_final_report: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    status = punching_final_report.get("status")

    if status == "NOT_OK":
        add_issue(
            issues,
            "ERROR",
            "PUNCHING_FINAL_NOT_OK",
            "Le poinçonnement final contient des erreurs.",
        )
    elif status == "WARNING":
        add_issue(
            issues,
            "WARNING",
            "PUNCHING_FINAL_WARNING",
            "Le poinçonnement final contient des avertissements.",
        )

    for check in punching_final_report.get("checks", []):
        util = float(check.get("worst_utilization") or 0.0)

        if util > 1.0:
            add_issue(
                issues,
                "ERROR",
                "PUNCHING_UTILIZATION_EXCEEDED",
                f"Taux de poinçonnement {util:.3f} > 1.00.",
                str(check.get("foundation_id", "-")),
            )
        elif util > 0.80:
            add_issue(
                issues,
                "WARNING",
                "PUNCHING_UTILIZATION_HIGH",
                f"Taux de poinçonnement élevé {util:.3f}.",
                str(check.get("foundation_id", "-")),
            )

    return issues


def check_anchorage_consistency(
    model: dict[str, Any],
    anchorage_report: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    columns = set(get_effective_column_boxes(model).keys())

    anchorage_columns = {
        str(row.get("column_id"))
        for row in anchorage_report.get("rows", [])
    }

    missing = sorted(columns - anchorage_columns)

    for column_id in missing:
        add_issue(
            issues,
            "WARNING",
            "MISSING_ANCHORAGE_ROW",
            "Poteau sans ligne d'ancrage / attente.",
            column_id,
        )

    if anchorage_report.get("status") == "WARNING":
        add_issue(
            issues,
            "WARNING",
            "ANCHORAGE_WARNING",
            "Certains ancrages nécessitent une vérification complémentaire.",
        )

    return issues


def check_boq_consistency(
    boq_report: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    totals = boq_report.get("totals", {})

    concrete = float(totals.get("concrete_m3") or 0.0)
    steel = float(totals.get("total_steel_kg") or 0.0)

    if concrete <= 0:
        add_issue(
            issues,
            "ERROR",
            "BOQ_CONCRETE_ZERO",
            "Le volume béton total est nul ou invalide.",
        )

    if steel <= 0:
        add_issue(
            issues,
            "WARNING",
            "BOQ_STEEL_ZERO",
            "Le poids acier total est nul ou invalide.",
        )

    return issues


def build_project_quality_check(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    reinforcement_report: dict[str, Any],
    reinforcement_final_report: dict[str, Any],
    punching_final_report: dict[str, Any],
    anchorage_report: dict[str, Any],
    boq_report: dict[str, Any],
    q_allowable_kPa: float,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []

    issues.extend(check_final_foundations(model, strategy_report, q_allowable_kPa))
    issues.extend(check_column_coverage(model, strategy_report))
    issues.extend(check_reinforcement_consistency(strategy_report, reinforcement_report, reinforcement_final_report))
    issues.extend(check_punching_consistency(punching_final_report))
    issues.extend(check_anchorage_consistency(model, anchorage_report))
    issues.extend(check_boq_consistency(boq_report))

    error_count = sum(1 for item in issues if item["severity"] == "ERROR")
    warning_count = sum(1 for item in issues if item["severity"] == "WARNING")

    if error_count > 0:
        status = "NOT_OK"
    elif warning_count > 0:
        status = "WARNING"
    else:
        status = "OK"

    return {
        "status": status,
        "method": "project_quality_check_v0_32",
        "summary": {
            "errors_count": error_count,
            "warnings_count": warning_count,
            "issues_count": len(issues),
            "final_foundations_count": len(strategy_report.get("final_foundations", [])),
            "columns_count": len(get_effective_column_boxes(model)),
        },
        "issues": issues,
        "rules_checked": [
            "Présence des fondations finales",
            "Dimensions A/B/H valides",
            "Fondations dans l'emprise",
            "Contrainte sol ELS <= q admissible",
            "Tous les poteaux couverts",
            "Ferraillage présent pour chaque fondation",
            "Contrôle final du ferraillage",
            "Contrôle final du poinçonnement",
            "Ancrages / attentes par poteau",
            "Métré béton / acier cohérent",
        ],
    }
