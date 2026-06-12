from __future__ import annotations

from typing import Any

from civil_engine.foundations.combined_footings import generate_combined_footings


def compute_resultant_for_combined(
    combined: dict[str, Any],
    isolated_footings: list[dict[str, Any]],
) -> dict[str, Any]:
    columns = set(combined.get("columns", []))

    involved = [
        footing for footing in isolated_footings
        if footing.get("column_id") in columns
    ]

    total_n = sum(float(footing["N_ELS_kN"]) for footing in involved)

    if total_n <= 0:
        return {
            "status": "ERROR",
            "message": "Charge totale nulle ou négative.",
            "N_ELS_kN": total_n,
            "xR": None,
            "yR": None,
            "columns_used": [],
        }

    xR = sum(
        float(footing["N_ELS_kN"]) * float(footing.get("column_cx", footing["cx"]))
        for footing in involved
    ) / total_n

    yR = sum(
        float(footing["N_ELS_kN"]) * float(footing.get("column_cy", footing["cy"]))
        for footing in involved
    ) / total_n

    return {
        "status": "OK",
        "N_ELS_kN": round(total_n, 3),
        "xR": round(xR, 4),
        "yR": round(yR, 4),
        "columns_used": [
            {
                "column_id": footing["column_id"],
                "N_ELS_kN": footing["N_ELS_kN"],
                "x": footing.get("column_cx", footing["cx"]),
                "y": footing.get("column_cy", footing["cy"]),
            }
            for footing in involved
        ],
    }


def compute_soil_pressures_biaxial(
    N_ELS_kN: float,
    Bx_m: float,
    Ly_m: float,
    ex_m: float,
    ey_m: float,
) -> dict[str, Any]:
    area = Bx_m * Ly_m

    if area <= 0:
        return {
            "status": "ERROR",
            "message": "Surface de semelle nulle.",
            "q0_kPa": None,
            "qmin_kPa": None,
            "qmax_kPa": None,
            "corner_pressures_kPa": [],
        }

    q0 = N_ELS_kN / area

    corner_pressures = []

    for sx in [-1, 1]:
        for sy in [-1, 1]:
            q = q0 * (
                1.0
                + sx * 6.0 * ex_m / Bx_m
                + sy * 6.0 * ey_m / Ly_m
            )

            corner_pressures.append({
                "corner": f"x{sx}_y{sy}",
                "q_kPa": round(q, 3),
            })

    values = [item["q_kPa"] for item in corner_pressures]

    return {
        "status": "OK",
        "q0_kPa": round(q0, 3),
        "qmin_kPa": round(min(values), 3),
        "qmax_kPa": round(max(values), 3),
        "corner_pressures_kPa": corner_pressures,
    }


def check_combined_eccentricity_from_report(
    combined_report: dict[str, Any],
) -> dict[str, Any]:
    q_allowable = float(
        combined_report.get("hypotheses", {}).get("q_allowable_kPa", 200.0)
    )

    isolated_footings = combined_report.get("isolated_footings", [])
    combined_footings = combined_report.get("combined_footings", [])

    checks: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for combined in combined_footings:
        resultant = compute_resultant_for_combined(
            combined=combined,
            isolated_footings=isolated_footings,
        )

        if resultant["status"] == "ERROR":
            errors.append({
                "code": "RESULTANT_ERROR",
                "combined_id": combined["id"],
                "message": resultant["message"],
            })
            continue

        Bx = float(combined["Bx_m"])
        Ly = float(combined["Ly_m"])

        footing_cx = float(combined["cx"])
        footing_cy = float(combined["cy"])

        xR = float(resultant["xR"])
        yR = float(resultant["yR"])

        ex = round(xR - footing_cx, 4)
        ey = round(yR - footing_cy, 4)

        kern_limit_x = round(Bx / 6.0, 4)
        kern_limit_y = round(Ly / 6.0, 4)

        kern_check_x = abs(ex) <= kern_limit_x
        kern_check_y = abs(ey) <= kern_limit_y

        pressures = compute_soil_pressures_biaxial(
            N_ELS_kN=float(resultant["N_ELS_kN"]),
            Bx_m=Bx,
            Ly_m=Ly,
            ex_m=ex,
            ey_m=ey,
        )

        qmin = pressures["qmin_kPa"]
        qmax = pressures["qmax_kPa"]

        no_tension_check = qmin is not None and qmin >= 0.0
        bearing_check = qmax is not None and qmax <= q_allowable

        status = "OK"
        recommendations: list[str] = []

        if not kern_check_x or not kern_check_y:
            status = "WARNING"
            recommendations.append(
                "Résultante hors noyau central : recentrer ou agrandir la semelle combinée."
            )

        if not no_tension_check:
            status = "WARNING"
            recommendations.append(
                "qmin < 0 : traction sous semelle. Recentrage ou redimensionnement obligatoire."
            )

        if not bearing_check:
            status = "WARNING"
            recommendations.append(
                "qmax > qsol : augmenter la surface ou revoir le système de fondation."
            )

        if status == "WARNING":
            warnings.append({
                "code": "COMBINED_FOOTING_ECCENTRICITY_WARNING",
                "combined_id": combined["id"],
                "ex_m": ex,
                "ey_m": ey,
                "qmin_kPa": qmin,
                "qmax_kPa": qmax,
                "message": "Excentricité ou pression de sol à corriger.",
            })

        checks.append({
            "combined_id": combined["id"],
            "status": status,
            "columns": combined.get("columns", []),
            "N_ELS_kN": resultant["N_ELS_kN"],
            "footing_center": {
                "x": footing_cx,
                "y": footing_cy,
            },
            "load_resultant_center": {
                "xR": xR,
                "yR": yR,
            },
            "eccentricity": {
                "ex_m": ex,
                "ey_m": ey,
                "kern_limit_x_m": kern_limit_x,
                "kern_limit_y_m": kern_limit_y,
                "kern_check_x": kern_check_x,
                "kern_check_y": kern_check_y,
            },
            "soil_pressure": {
                "q_allowable_kPa": q_allowable,
                "q0_kPa": pressures["q0_kPa"],
                "qmin_kPa": qmin,
                "qmax_kPa": qmax,
                "no_tension_check": no_tension_check,
                "bearing_check": bearing_check,
                "corner_pressures_kPa": pressures["corner_pressures_kPa"],
            },
            "recommendations": recommendations,
            "resultant_details": resultant["columns_used"],
        })

    global_status = "OK"

    if errors:
        global_status = "ERROR"
    elif warnings:
        global_status = "WARNING"

    return {
        "status": global_status,
        "method": "combined_footing_resultant_eccentricity_check_v0_13",
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "summary": {
            "combined_footings_checked": len(checks),
            "warnings_count": len(warnings),
            "errors_count": len(errors),
        },
    }


def check_combined_eccentricity(
    model: dict[str, Any],
    q_allowable_kPa: float = 200.0,
) -> dict[str, Any]:
    combined_report = generate_combined_footings(
        model=model,
        q_allowable_kPa=q_allowable_kPa,
    )

    eccentricity_report = check_combined_eccentricity_from_report(
        combined_report=combined_report,
    )

    return {
        "status": eccentricity_report["status"],
        "method": "combined_footing_generation_and_eccentricity_check_v0_13",
        "combined_report_summary": combined_report.get("summary", {}),
        "eccentricity_report": eccentricity_report,
        "combined_report": combined_report,
    }
