from __future__ import annotations

from typing import Any

from civil_engine.checks.punching_prelim import (
    build_load_maps,
    check_column_punching,
    get_column_geometry,
)


def clamp_rho_l(value: float) -> float:
    """
    Limites pratiques EC2 :
    - rho minimal évite une valeur nulle irréaliste ;
    - rho maximal pris à 2%.
    """
    return min(max(value, 0.001), 0.020)


def build_rho_real_map(
    reinforcement_final_report: dict[str, Any],
) -> dict[str, float]:
    """
    Récupère rho_l réel calculé à l'étape 23.
    """
    result = {}

    for check in reinforcement_final_report.get("checks", []):
        foundation_id = check.get("foundation_id")

        if not foundation_id:
            continue

        rho_l = float(check.get("rho_l_real_for_punching", 0.005))
        result[foundation_id] = clamp_rho_l(rho_l)

    return result


def check_foundation_punching_final(
    element: dict[str, Any],
    columns_geometry: dict[str, dict[str, float]],
    column_loads: dict[str, dict[str, Any]],
    rho_l_real: float,
    fck_mpa: float,
    gamma_c: float,
    cover_m: float,
) -> dict[str, Any]:
    foundation_id = element.get("id")
    foundation_type = element.get("type")

    column_checks = []
    warnings = []
    errors = []

    for column_id in element.get("columns", []):
        column = columns_geometry.get(column_id)
        load = column_loads.get(column_id)

        if column is None:
            errors.append({
                "code": "COLUMN_GEOMETRY_NOT_FOUND",
                "column_id": column_id,
                "message": "Géométrie du poteau introuvable.",
            })
            continue

        if load is None:
            errors.append({
                "code": "COLUMN_LOAD_NOT_FOUND",
                "column_id": column_id,
                "message": "Charge du poteau introuvable.",
            })
            continue

        check = check_column_punching(
            column_id=column_id,
            column=column,
            column_load=load,
            foundation_element=element,
            fck_mpa=fck_mpa,
            rho_l=rho_l_real,
            gamma_c=gamma_c,
            cover_m=cover_m,
        )

        column_checks.append(check)

        if check["status"] != "OK_PRELIMINARY":
            warnings.append({
                "code": "PUNCHING_FINAL_TO_REVIEW",
                "column_id": column_id,
                "utilization": check["utilization"],
                "status": check["status"],
                "recommendation": check["recommendation"],
            })

    worst_utilization = 0.0

    if column_checks:
        worst_utilization = max(float(item["utilization"]) for item in column_checks)

    if errors:
        status = "NOT_OK"
    elif worst_utilization <= 0.80:
        status = "OK"
    elif worst_utilization <= 1.00:
        status = "WARNING"
    else:
        status = "NOT_OK"

    return {
        "foundation_id": foundation_id,
        "foundation_type": foundation_type,
        "columns": element.get("columns", []),
        "A_m": element.get("A_m"),
        "B_m": element.get("B_m"),
        "H_m": element.get("H_m"),
        "rho_l_real_used": round(rho_l_real, 5),
        "worst_utilization": round(worst_utilization, 3),
        "status": status,
        "column_checks": column_checks,
        "warnings": warnings,
        "errors": errors,
    }


def check_punching_final(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    reinforcement_final_report: dict[str, Any],
    fck_mpa: float = 25.0,
    gamma_c: float = 1.50,
    cover_m: float = 0.05,
) -> dict[str, Any]:
    """
    Vérification finale du poinçonnement avec rho_l réel.

    Le rho_l réel provient de l'étape 23 :
    check_reinforcement_final -> rho_l_real_for_punching.
    """
    columns_geometry = get_column_geometry(model)
    column_loads = build_load_maps(strategy_report)
    rho_real_map = build_rho_real_map(reinforcement_final_report)

    checks = []
    warnings = []
    errors = []

    if reinforcement_final_report.get("status") == "NOT_OK":
        warnings.append({
            "code": "REINFORCEMENT_NOT_OK",
            "message": "Le ferraillage n'est pas validé. Le poinçonnement final est indicatif seulement.",
        })

    for element in strategy_report.get("final_foundations", []):
        foundation_id = element.get("id")

        rho_l_real = rho_real_map.get(foundation_id, 0.005)
        rho_l_real = clamp_rho_l(rho_l_real)

        check = check_foundation_punching_final(
            element=element,
            columns_geometry=columns_geometry,
            column_loads=column_loads,
            rho_l_real=rho_l_real,
            fck_mpa=fck_mpa,
            gamma_c=gamma_c,
            cover_m=cover_m,
        )

        checks.append(check)

        for warning in check.get("warnings", []):
            warnings.append({
                "foundation_id": foundation_id,
                **warning,
            })

        for error in check.get("errors", []):
            errors.append({
                "foundation_id": foundation_id,
                **error,
            })

    if errors:
        status = "NOT_OK"
    elif any(item.get("status") == "NOT_OK" for item in checks):
        status = "NOT_OK"
    elif any(item.get("status") == "WARNING" for item in checks):
        status = "WARNING"
    elif warnings:
        status = "WARNING"
    else:
        status = "OK"

    return {
        "status": status,
        "method": "punching_final_with_real_rho_v0_24",
        "hypotheses": {
            "fck_mpa": fck_mpa,
            "gamma_c": gamma_c,
            "cover_m": cover_m,
            "rho_source": "rho_l_real_for_punching from reinforcement_final_check",
            "note": "Vérification finale simplifiée du poinçonnement. A valider avec efforts finaux, excentricités, réactions du sol, dispositions d'armatures et modèle réglementaire complet.",
        },
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "summary": {
            "foundations_checked": len(checks),
            "warnings_count": len(warnings),
            "errors_count": len(errors),
        },
    }
