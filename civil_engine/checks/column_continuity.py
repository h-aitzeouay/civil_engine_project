from __future__ import annotations

import math
from typing import Any


def level_sort_key(level_name: str) -> tuple[int, int]:
    """
    Ordre logique des niveaux :
    FONDATION -> SS -> RDC -> ETAGE1 -> ETAGE2...
    """
    name = level_name.upper()

    if name == "FONDATION":
        return (0, 0)

    if name.startswith("SS"):
        if name == "SS":
            return (1, 0)
        number = name.replace("SS", "")
        if number.isdigit():
            return (1, -int(number))

    if name == "RDC":
        return (2, 0)

    if name.startswith("ETAGE"):
        number = name.replace("ETAGE", "")
        if number.isdigit():
            return (3, int(number))

    return (99, 0)


def distance_between_columns(col_a: dict[str, Any], col_b: dict[str, Any]) -> float:
    dx = float(col_a["cx"]) - float(col_b["cx"])
    dy = float(col_a["cy"]) - float(col_b["cy"])
    return math.sqrt(dx * dx + dy * dy)


def find_nearest_column(
    reference_column: dict[str, Any],
    candidate_columns: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, float | None]:
    """
    Cherche le poteau le plus proche d'un poteau de référence.
    """
    if not candidate_columns:
        return None, None

    nearest = None
    nearest_distance = None

    for candidate in candidate_columns:
        distance = distance_between_columns(reference_column, candidate)

        if nearest_distance is None or distance < nearest_distance:
            nearest = candidate
            nearest_distance = distance

    return nearest, nearest_distance


def check_column_continuity(
    model: dict[str, Any],
    tolerance_m: float = 0.50,
) -> dict[str, Any]:
    """
    Vérifie la continuité verticale des poteaux.

    Référence :
    - on prend les poteaux de FONDATION comme base ;
    - chaque poteau de fondation doit avoir un poteau correspondant
      au RDC, ETAGE1, etc. dans la tolérance donnée.

    Sortie :
    - groupes verticaux VG_P01, VG_P02...
    - missing_columns : poteaux manquants par niveau
    - shifted_columns : poteaux présents mais déplacés au-delà tolérance
    - extra_columns : poteaux présents en étage mais non rattachés à fondation
    """
    levels = model.get("levels", [])

    levels_sorted = sorted(
        levels,
        key=lambda level: level_sort_key(level["name"]),
    )

    foundation_level = None

    for level in levels_sorted:
        if level["name"] == "FONDATION":
            foundation_level = level
            break

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    vertical_groups: list[dict[str, Any]] = []
    extra_columns: list[dict[str, Any]] = []

    if foundation_level is None:
        return {
            "status": "ERROR",
            "tolerance_m": tolerance_m,
            "errors": [
                {
                    "code": "MISSING_FOUNDATION_LEVEL",
                    "message": "Le niveau FONDATION est absent. Impossible de contrôler la continuité verticale.",
                }
            ],
            "warnings": [],
            "vertical_groups": [],
            "extra_columns": [],
        }

    foundation_columns = foundation_level.get("columns", [])

    if not foundation_columns:
        return {
            "status": "ERROR",
            "tolerance_m": tolerance_m,
            "errors": [
                {
                    "code": "NO_FOUNDATION_COLUMNS",
                    "message": "Aucun poteau trouvé dans FONDATION-POTEAUX.",
                }
            ],
            "warnings": [],
            "vertical_groups": [],
            "extra_columns": [],
        }

    structural_levels = [
        level for level in levels_sorted
        if level["name"] != "FONDATION"
    ]

    used_columns_by_level: dict[str, set[str]] = {
        level["name"]: set()
        for level in structural_levels
    }

    for index, foundation_column in enumerate(foundation_columns, start=1):
        group_id = f"VG_P{index:02d}"

        group = {
            "vertical_group_id": group_id,
            "reference_level": "FONDATION",
            "reference_column_id": foundation_column["id"],
            "cx": foundation_column["cx"],
            "cy": foundation_column["cy"],
            "matches": [
                {
                    "level": "FONDATION",
                    "column_id": foundation_column["id"],
                    "cx": foundation_column["cx"],
                    "cy": foundation_column["cy"],
                    "distance_m": 0.0,
                    "status": "REFERENCE",
                }
            ],
        }

        for level in structural_levels:
            level_name = level["name"]
            candidate_columns = level.get("columns", [])

            nearest, distance = find_nearest_column(
                foundation_column,
                candidate_columns,
            )

            if nearest is None or distance is None:
                errors.append({
                    "code": "MISSING_LEVEL_COLUMNS",
                    "level": level_name,
                    "reference_column": foundation_column["id"],
                    "message": f"Aucun poteau trouvé au niveau {level_name}.",
                })

                group["matches"].append({
                    "level": level_name,
                    "column_id": None,
                    "distance_m": None,
                    "status": "MISSING",
                })

            elif distance <= tolerance_m:
                used_columns_by_level[level_name].add(nearest["id"])

                group["matches"].append({
                    "level": level_name,
                    "column_id": nearest["id"],
                    "cx": nearest["cx"],
                    "cy": nearest["cy"],
                    "distance_m": round(distance, 4),
                    "status": "OK",
                })

            else:
                errors.append({
                    "code": "COLUMN_SHIFTED_OR_MISSING",
                    "level": level_name,
                    "reference_column": foundation_column["id"],
                    "nearest_column": nearest["id"],
                    "distance_m": round(distance, 4),
                    "message": (
                        f"Le poteau {foundation_column['id']} de fondation "
                        f"n'a pas de correspondant dans la tolérance {tolerance_m} m "
                        f"au niveau {level_name}."
                    ),
                })

                group["matches"].append({
                    "level": level_name,
                    "column_id": nearest["id"],
                    "cx": nearest["cx"],
                    "cy": nearest["cy"],
                    "distance_m": round(distance, 4),
                    "status": "SHIFTED_OR_MISSING",
                })

        vertical_groups.append(group)

    # Détection des poteaux en étage qui ne correspondent à aucun poteau de fondation
    for level in structural_levels:
        level_name = level["name"]

        for column in level.get("columns", []):
            if column["id"] not in used_columns_by_level[level_name]:
                nearest_foundation, distance = find_nearest_column(
                    column,
                    foundation_columns,
                )

                if distance is not None and distance > tolerance_m:
                    extra_columns.append({
                        "level": level_name,
                        "column_id": column["id"],
                        "cx": column["cx"],
                        "cy": column["cy"],
                        "nearest_foundation_column": nearest_foundation["id"] if nearest_foundation else None,
                        "distance_m": round(distance, 4),
                        "status": "EXTRA_OR_UNSUPPORTED",
                        "message": (
                            f"Poteau {column['id']} au niveau {level_name} "
                            f"sans poteau correspondant en fondation."
                        ),
                    })

    if extra_columns:
        warnings.append({
            "code": "EXTRA_COLUMNS_DETECTED",
            "message": "Des poteaux existent en étage sans correspondance claire en fondation.",
            "count": len(extra_columns),
        })

    status = "OK"

    if errors:
        status = "ERROR"
    elif warnings:
        status = "WARNING"

    return {
        "status": status,
        "tolerance_m": tolerance_m,
        "reference_level": "FONDATION",
        "levels_checked": [level["name"] for level in structural_levels],
        "foundation_columns_count": len(foundation_columns),
        "vertical_groups_count": len(vertical_groups),
        "vertical_groups": vertical_groups,
        "extra_columns": extra_columns,
        "warnings": warnings,
        "errors": errors,
        "summary": {
            "errors_count": len(errors),
            "warnings_count": len(warnings),
            "extra_columns_count": len(extra_columns),
        },
    }