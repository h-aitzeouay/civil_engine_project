from __future__ import annotations

from typing import Any

from civil_engine.engine.tributary_areas import compute_tributary_areas


def level_sort_key(level_name: str) -> tuple[int, int]:
    """
    Classe les niveaux dans l'ordre vertical.
    """
    name = level_name.upper()

    if name == "FONDATION":
        return (0, 0)

    if name == "RDC":
        return (1, 0)

    if name.startswith("ETAGE"):
        number = name.replace("ETAGE", "")
        if number.isdigit():
            return (2, int(number))

    if name.startswith("SS"):
        if name == "SS":
            return (-1, 0)
        number = name.replace("SS", "")
        if number.isdigit():
            return (-1, -int(number))

    return (99, 0)


def is_top_structural_level(level_name: str, structural_level_names: list[str]) -> bool:
    """
    Détecte le dernier niveau structurel.
    Dans cette V0, on considère le dernier niveau comme terrasse.
    """
    sorted_names = sorted(structural_level_names, key=level_sort_key)
    return level_name == sorted_names[-1]


def compute_load_takedown(
    model: dict[str, Any],
    g_floor_kN_m2: float = 5.00,
    q_floor_kN_m2: float = 1.50,
    g_terrace_kN_m2: float = 6.00,
    q_terrace_kN_m2: float = 1.00,
    gamma_g: float = 1.35,
    gamma_q: float = 1.50,
) -> dict[str, Any]:
    """
    Descente de charges verticale V0.

    Hypothèses :
    - charges uniformes par niveau ;
    - surfaces tributaires issues de compute_tributary_areas ;
    - FONDATION exclue de la descente de charges ;
    - dernier niveau structurel considéré comme terrasse ;
    - les poteaux sont identifiés par P01, P02, etc.

    Sorties :
    - charges par poteau et par niveau ;
    - cumul en pied de poteau ;
    - ELU = gamma_g * G + gamma_q * Q.
    """
    trib_report = compute_tributary_areas(model=model, axis_tolerance_m=0.20)

    if trib_report["status"] == "ERROR":
        return {
            "status": "ERROR",
            "message": "Impossible de faire la descente de charges sans surfaces tributaires.",
            "tributary_report": trib_report,
            "warnings": [],
            "errors": trib_report.get("errors", []),
        }

    levels_tributary = trib_report.get("levels", [])
    structural_level_names = [level["level"] for level in levels_tributary]

    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    level_loads: list[dict[str, Any]] = []
    foundation_cumulative: dict[str, dict[str, Any]] = {}

    for level in levels_tributary:
        level_name = level["level"]

        if is_top_structural_level(level_name, structural_level_names):
            level_type = "TERRACE"
            g_used = g_terrace_kN_m2
            q_used = q_terrace_kN_m2
        else:
            level_type = "FLOOR"
            g_used = g_floor_kN_m2
            q_used = q_floor_kN_m2

        columns_loads = []

        for column in level.get("columns", []):
            column_id = column["column_id"]
            area_net = float(column["tributary_area_net_m2"])
            area_gross = float(column["tributary_area_gross_m2"])

            gk = round(area_net * g_used, 3)
            qk = round(area_net * q_used, 3)

            n_els = round(gk + qk, 3)
            n_elu = round(gamma_g * gk + gamma_q * qk, 3)

            item = {
                "level": level_name,
                "level_type": level_type,
                "column_id": column_id,
                "column_type": column.get("column_type"),
                "tributary_area_gross_m2": area_gross,
                "tributary_area_net_m2": area_net,
                "G_kN_m2": g_used,
                "Q_kN_m2": q_used,
                "Gk_kN": gk,
                "Qk_kN": qk,
                "N_ELS_kN": n_els,
                "N_ELU_kN": n_elu,
                "combination_elu": f"{gamma_g}G + {gamma_q}Q",
            }

            columns_loads.append(item)

            if column_id not in foundation_cumulative:
                foundation_cumulative[column_id] = {
                    "column_id": column_id,
                    "sum_Gk_kN": 0.0,
                    "sum_Qk_kN": 0.0,
                    "sum_N_ELS_kN": 0.0,
                    "sum_N_ELU_kN": 0.0,
                    "levels_supported": [],
                }

            foundation_cumulative[column_id]["sum_Gk_kN"] += gk
            foundation_cumulative[column_id]["sum_Qk_kN"] += qk
            foundation_cumulative[column_id]["sum_N_ELS_kN"] += n_els
            foundation_cumulative[column_id]["sum_N_ELU_kN"] += n_elu
            foundation_cumulative[column_id]["levels_supported"].append(level_name)

        level_loads.append({
            "level": level_name,
            "level_type": level_type,
            "G_kN_m2": g_used,
            "Q_kN_m2": q_used,
            "columns_count": len(columns_loads),
            "columns": columns_loads,
            "sum_Gk_kN": round(sum(col["Gk_kN"] for col in columns_loads), 3),
            "sum_Qk_kN": round(sum(col["Qk_kN"] for col in columns_loads), 3),
            "sum_N_ELS_kN": round(sum(col["N_ELS_kN"] for col in columns_loads), 3),
            "sum_N_ELU_kN": round(sum(col["N_ELU_kN"] for col in columns_loads), 3),
        })

    foundation_columns = []

    for column_id, data in sorted(foundation_cumulative.items()):
        foundation_columns.append({
            "column_id": column_id,
            "levels_supported": data["levels_supported"],
            "sum_Gk_kN": round(data["sum_Gk_kN"], 3),
            "sum_Qk_kN": round(data["sum_Qk_kN"], 3),
            "sum_N_ELS_kN": round(data["sum_N_ELS_kN"], 3),
            "sum_N_ELU_kN": round(data["sum_N_ELU_kN"], 3),
            "status": "PRELIMINARY",
        })

    total_G = round(sum(item["sum_Gk_kN"] for item in foundation_columns), 3)
    total_Q = round(sum(item["sum_Qk_kN"] for item in foundation_columns), 3)
    total_ELS = round(sum(item["sum_N_ELS_kN"] for item in foundation_columns), 3)
    total_ELU = round(sum(item["sum_N_ELU_kN"] for item in foundation_columns), 3)

    return {
        "status": "OK" if not errors else "ERROR",
        "method": "tributary_area_vertical_load_takedown_v0",
        "hypotheses": {
            "g_floor_kN_m2": g_floor_kN_m2,
            "q_floor_kN_m2": q_floor_kN_m2,
            "g_terrace_kN_m2": g_terrace_kN_m2,
            "q_terrace_kN_m2": q_terrace_kN_m2,
            "gamma_g": gamma_g,
            "gamma_q": gamma_q,
            "elu_combination": f"{gamma_g}G + {gamma_q}Q",
            "foundation_level_excluded": True,
            "last_structural_level_assumed_as_terrace": True,
            "note": "Descente de charges préliminaire. Les charges doivent être confirmées par le programme architectural et la note d'hypothèses.",
        },
        "levels": level_loads,
        "foundation_columns": foundation_columns,
        "totals": {
            "total_Gk_kN": total_G,
            "total_Qk_kN": total_Q,
            "total_N_ELS_kN": total_ELS,
            "total_N_ELU_kN": total_ELU,
        },
        "warnings": warnings,
        "errors": errors,
        "summary": {
            "levels_count": len(level_loads),
            "foundation_columns_count": len(foundation_columns),
            "warnings_count": len(warnings),
            "errors_count": len(errors),
        },
    }