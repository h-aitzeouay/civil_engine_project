from __future__ import annotations

import math
from typing import Any


def get_foundation_level(model: dict[str, Any]) -> dict[str, Any] | None:
    for level in model.get("levels", []):
        if level.get("name") == "FONDATION":
            return level
    return None


def get_column_geometry(model: dict[str, Any]) -> dict[str, dict[str, float]]:
    """
    Récupère les dimensions des poteaux à partir du DXF.
    Si les dimensions ne sont pas lisibles, on adopte 25x25 cm par défaut.
    """
    foundation = get_foundation_level(model)

    if foundation is None:
        return {}

    columns = {}

    for column in foundation.get("columns", []):
        column_id = column["id"]

        cx = float(column.get("cx", 0.0))
        cy = float(column.get("cy", 0.0))

        points = column.get("points", [])

        if points:
            xs = [float(p[0]) for p in points]
            ys = [float(p[1]) for p in points]

            c1 = max(xs) - min(xs)
            c2 = max(ys) - min(ys)
        else:
            c1 = 0.25
            c2 = 0.25

        columns[column_id] = {
            "cx": cx,
            "cy": cy,
            "c1_m": max(c1, 0.20),
            "c2_m": max(c2, 0.20),
        }

    return columns


def edge_factor_for_column(
    column: dict[str, float],
    foundation_element: dict[str, Any],
    d_m: float,
) -> tuple[float, str]:
    """
    Facteur simplifié pour poteau intérieur / rive / angle.

    Si le poteau est proche d'un bord de la fondation, le périmètre utile
    de poinçonnement est réduit.
    """
    bbox = foundation_element["bbox"]

    x = float(column["cx"])
    y = float(column["cy"])

    distances = [
        abs(x - float(bbox["xmin"])),
        abs(float(bbox["xmax"]) - x),
        abs(y - float(bbox["ymin"])),
        abs(float(bbox["ymax"]) - y),
    ]

    near_edges = sum(1 for distance in distances if distance < 2.0 * d_m)

    if near_edges >= 2:
        return 0.50, "ANGLE_OU_BORD_TRES_PROCHe"

    if near_edges == 1:
        return 0.65, "BORD"

    return 1.00, "INTERIEUR"


def punching_resistance_ec2_prelim(
    d_m: float,
    fck_mpa: float,
    rho_l: float,
    gamma_c: float,
) -> float:
    """
    Résistance approximative vRd,c en MPa.

    Forme préliminaire inspirée EC2 :
    vRd,c = CRdc * k * (100*rho*fck)^(1/3)

    Ce module est volontairement conservatif et doit être validé
    dans la note de calcul finale.
    """
    d_mm = d_m * 1000.0

    k = min(2.0, 1.0 + math.sqrt(200.0 / max(d_mm, 1.0)))
    c_rdc = 0.18 / gamma_c

    rho = min(max(rho_l, 0.001), 0.02)

    return round(c_rdc * k * (100.0 * rho * fck_mpa) ** (1.0 / 3.0), 4)


def check_column_punching(
    column_id: str,
    column: dict[str, float],
    column_load: dict[str, Any],
    foundation_element: dict[str, Any],
    fck_mpa: float,
    rho_l: float,
    gamma_c: float,
    cover_m: float,
) -> dict[str, Any]:
    h_m = float(foundation_element.get("H_m", 0.35))
    d_m = max(h_m - cover_m - 0.006, 0.12)

    c1 = float(column["c1_m"])
    c2 = float(column["c2_m"])

    # Périmètre simplifié conservatif autour du poteau.
    u1_m = 2.0 * (c1 + c2) + 8.0 * d_m

    edge_factor, position_type = edge_factor_for_column(
        column=column,
        foundation_element=foundation_element,
        d_m=d_m,
    )

    u1_eff_m = u1_m * edge_factor

    n_elu = column_load.get("N_ELU_kN")

    if n_elu is None:
        n_els = float(column_load.get("N_ELS_kN", 0.0))
        n_elu = 1.35 * n_els

    n_elu = float(n_elu)

    ved_mpa = (n_elu * 1000.0) / max(u1_eff_m * d_m, 1e-9) / 1_000_000.0

    vrdc_mpa = punching_resistance_ec2_prelim(
        d_m=d_m,
        fck_mpa=fck_mpa,
        rho_l=rho_l,
        gamma_c=gamma_c,
    )

    utilization = ved_mpa / max(vrdc_mpa, 1e-9)

    if utilization <= 0.80:
        status = "OK_PRELIMINARY"
        recommendation = "Poinconnement preliminaire acceptable."
    elif utilization <= 1.00:
        status = "WARNING"
        recommendation = "Zone proche de la limite. Verifier avec ferraillage reel et effet de sol."
    else:
        status = "NOT_OK"
        recommendation = "Renfort de poinconnement, augmentation H, chapiteau/massif ou radier local a etudier."

    return {
        "column_id": column_id,
        "position_type": position_type,
        "c1_m": round(c1, 3),
        "c2_m": round(c2, 3),
        "H_m": round(h_m, 3),
        "d_m": round(d_m, 3),
        "u1_m": round(u1_m, 3),
        "u1_eff_m": round(u1_eff_m, 3),
        "edge_factor": edge_factor,
        "N_ELU_kN": round(n_elu, 3),
        "vEd_MPa": round(ved_mpa, 4),
        "vRdc_MPa": round(vrdc_mpa, 4),
        "utilization": round(utilization, 3),
        "status": status,
        "recommendation": recommendation,
    }


def build_load_maps(strategy_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """
    Associe chaque poteau à sa charge issue du prédimensionnement.
    """
    isolated_report = strategy_report.get("isolated_report", {})
    footings = isolated_report.get("footings", [])

    by_column = {}

    for footing in footings:
        column_id = footing.get("column_id")

        if not column_id:
            continue

        by_column[column_id] = {
            "footing_id": footing.get("id"),
            "N_ELS_kN": footing.get("N_ELS_kN", 0.0),
            "N_ELU_kN": footing.get("N_ELU_kN"),
        }

    return by_column


def check_punching_prelim(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    fck_mpa: float = 25.0,
    rho_l: float = 0.005,
    gamma_c: float = 1.50,
    cover_m: float = 0.05,
) -> dict[str, Any]:
    columns_geometry = get_column_geometry(model)
    column_loads = build_load_maps(strategy_report)

    final_foundations = strategy_report.get("final_foundations", [])

    checks = []
    warnings = []
    errors = []

    for element in final_foundations:
        element_checks = []

        for column_id in element.get("columns", []):
            column = columns_geometry.get(column_id)
            load = column_loads.get(column_id)

            if column is None:
                errors.append({
                    "code": "COLUMN_GEOMETRY_NOT_FOUND",
                    "column_id": column_id,
                    "foundation_id": element.get("id"),
                })
                continue

            if load is None:
                errors.append({
                    "code": "COLUMN_LOAD_NOT_FOUND",
                    "column_id": column_id,
                    "foundation_id": element.get("id"),
                })
                continue

            check = check_column_punching(
                column_id=column_id,
                column=column,
                column_load=load,
                foundation_element=element,
                fck_mpa=fck_mpa,
                rho_l=rho_l,
                gamma_c=gamma_c,
                cover_m=cover_m,
            )

            element_checks.append(check)

            if check["status"] != "OK_PRELIMINARY":
                warnings.append({
                    "code": "PUNCHING_TO_REVIEW",
                    "foundation_id": element.get("id"),
                    "column_id": column_id,
                    "status": check["status"],
                    "utilization": check["utilization"],
                    "recommendation": check["recommendation"],
                })

        worst_utilization = 0.0

        if element_checks:
            worst_utilization = max(float(item["utilization"]) for item in element_checks)

        if worst_utilization <= 0.80:
            element_status = "OK_PRELIMINARY"
        elif worst_utilization <= 1.00:
            element_status = "WARNING"
        else:
            element_status = "NOT_OK"

        checks.append({
            "foundation_id": element.get("id"),
            "foundation_type": element.get("type"),
            "A_m": element.get("A_m"),
            "B_m": element.get("B_m"),
            "H_m": element.get("H_m"),
            "columns": element.get("columns", []),
            "worst_utilization": round(worst_utilization, 3),
            "status": element_status,
            "column_checks": element_checks,
        })

    status = "OK"

    if errors:
        status = "ERROR"
    elif warnings:
        status = "WARNING"

    return {
        "status": status,
        "method": "punching_preliminary_ec2_simplified_v0_18",
        "hypotheses": {
            "fck_mpa": fck_mpa,
            "rho_l": rho_l,
            "gamma_c": gamma_c,
            "cover_m": cover_m,
            "note": "Controle preliminaire. La verification finale doit integrer efforts reels, reactions du sol, ferraillage, dispositions constructives et modele de calcul.",
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
