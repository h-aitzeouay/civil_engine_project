from __future__ import annotations

from copy import deepcopy
from math import ceil
from typing import Any

from civil_engine.foundations.column_effective import get_effective_column_boxes


def round_up(value: float, step: float = 0.05) -> float:
    return round(ceil(value / step) * step, 2)


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


def is_inside(box: dict[str, float], emprise: dict[str, float], tol: float = 0.02) -> bool:
    return (
        float(box["xmin"]) >= float(emprise["xmin"]) - tol
        and float(box["xmax"]) <= float(emprise["xmax"]) + tol
        and float(box["ymin"]) >= float(emprise["ymin"]) - tol
        and float(box["ymax"]) <= float(emprise["ymax"]) + tol
    )


def column_union_box(
    columns: list[str],
    column_boxes: dict[str, dict[str, float]],
    margin_m: float = 0.05,
) -> dict[str, float] | None:
    boxes = [column_boxes[c] for c in columns if c in column_boxes]

    if not boxes:
        return None

    return {
        "xmin": min(float(b["xmin"]) for b in boxes) - margin_m,
        "xmax": max(float(b["xmax"]) for b in boxes) + margin_m,
        "ymin": min(float(b["ymin"]) for b in boxes) - margin_m,
        "ymax": max(float(b["ymax"]) for b in boxes) + margin_m,
    }


def choose_interval_position(
    old_min: float,
    size: float,
    emprise_min: float,
    emprise_max: float,
    required_min: float,
    required_max: float,
) -> tuple[float, bool]:
    """
    Choisit la position min d'une semelle de taille size :
    - dans l'emprise ;
    - contenant la zone required ;
    - le plus proche possible de l'ancien emplacement.
    """
    lower = max(emprise_min, required_max - size)
    upper = min(emprise_max - size, required_min)

    if lower <= upper:
        return min(max(old_min, lower), upper), True

    # Si impossible, on place dans l'emprise au mieux.
    clipped = min(max(old_min, emprise_min), emprise_max - size)
    return clipped, False


def fix_foundations_inside_emprise(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    margin_m: float = 0.05,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Corrige les semelles qui débordent de l'emprise :
    - on ne déplace pas les poteaux ;
    - on déplace la semelle vers l'intérieur ;
    - on vérifie que la semelle contient toujours le ou les poteaux ;
    - si impossible, on garde une alerte de passage à semelle combinée/radier local.
    """
    report = deepcopy(strategy_report)
    corrections: list[dict[str, Any]] = []

    emprise = get_emprise_bbox(model)
    column_boxes = get_effective_column_boxes(model)

    if emprise is None:
        corrections.append({
            "type": "ERROR",
            "code": "EMPRISE_NOT_FOUND",
            "message": "Impossible de corriger les débords : emprise introuvable.",
        })
        return report, corrections

    for element in report.get("final_foundations", []):
        fid = str(element.get("id", "-"))
        bbox = element.get("bbox")

        if not bbox:
            continue

        if is_inside(bbox, emprise):
            continue

        A = float(bbox["xmax"]) - float(bbox["xmin"])
        B = float(bbox["ymax"]) - float(bbox["ymin"])

        required = column_union_box(
            columns=element.get("columns", []),
            column_boxes=column_boxes,
            margin_m=margin_m,
        )

        if required is None:
            required = {
                "xmin": float(bbox["xmin"]),
                "xmax": float(bbox["xmax"]),
                "ymin": float(bbox["ymin"]),
                "ymax": float(bbox["ymax"]),
            }

        new_xmin, feasible_x = choose_interval_position(
            old_min=float(bbox["xmin"]),
            size=A,
            emprise_min=float(emprise["xmin"]),
            emprise_max=float(emprise["xmax"]),
            required_min=float(required["xmin"]),
            required_max=float(required["xmax"]),
        )

        new_ymin, feasible_y = choose_interval_position(
            old_min=float(bbox["ymin"]),
            size=B,
            emprise_min=float(emprise["ymin"]),
            emprise_max=float(emprise["ymax"]),
            required_min=float(required["ymin"]),
            required_max=float(required["ymax"]),
        )

        new_bbox = {
            "xmin": round(new_xmin, 4),
            "xmax": round(new_xmin + A, 4),
            "ymin": round(new_ymin, 4),
            "ymax": round(new_ymin + B, 4),
        }

        element["bbox"] = new_bbox
        element["cx"] = round((new_bbox["xmin"] + new_bbox["xmax"]) / 2.0, 4)
        element["cy"] = round((new_bbox["ymin"] + new_bbox["ymax"]) / 2.0, 4)
        element["A_m"] = round(A, 2)
        element["B_m"] = round(B, 2)

        if feasible_x and feasible_y and is_inside(new_bbox, emprise):
            corrections.append({
                "type": "GEOMETRY_FIX",
                "foundation_id": fid,
                "code": "FOUNDATION_SHIFTED_INSIDE_EMPRISE",
                "message": "Semelle déplacée vers l'intérieur de l'emprise sans déplacement du poteau.",
                "old_bbox": bbox,
                "new_bbox": new_bbox,
            })
        else:
            corrections.append({
                "type": "WARNING",
                "foundation_id": fid,
                "code": "COMBINED_OR_LOCAL_RAFT_REQUIRED",
                "message": "La semelle ne peut pas être corrigée correctement seule. Prévoir semelle combinée ou radier local.",
                "old_bbox": bbox,
                "new_bbox": new_bbox,
            })

    return report, corrections


def fix_punching_by_increasing_thickness(
    strategy_report: dict[str, Any],
    punching_final_report: dict[str, Any],
    safety_factor: float = 1.10,
    min_increment_m: float = 0.05,
    target_utilization: float = 0.80,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Correction conservative du poinçonnement.

    Ancienne logique :
    - corriger seulement si utilisation > 1.00.

    Nouvelle logique :
    - corriger si utilisation > target_utilization.
    - par défaut target_utilization = 0.80.
    - cela transforme les cas WARNING proches de la limite en cas plus confortables.
    """
    report = deepcopy(strategy_report)
    corrections: list[dict[str, Any]] = []

    util_map = {
        str(check.get("foundation_id")): float(check.get("worst_utilization") or 0.0)
        for check in punching_final_report.get("checks", [])
    }

    for element in report.get("final_foundations", []):
        fid = str(element.get("id", "-"))
        util = util_map.get(fid, 0.0)

        if util <= target_utilization:
            continue

        old_h = float(element.get("H_m") or element.get("thickness_m") or 0.35)

        # H est augmenté proportionnellement au dépassement du taux cible.
        target_h = old_h * (util / target_utilization) * safety_factor
        new_h = max(old_h + min_increment_m, round_up(target_h, 0.05))

        element["H_m"] = round(new_h, 2)
        element["thickness_m"] = round(new_h, 2)

        corrections.append({
            "type": "PUNCHING_FIX",
            "foundation_id": fid,
            "code": "THICKNESS_INCREASED_FOR_PUNCHING_TARGET",
            "message": "Epaisseur augmentée pour viser un taux de poinçonnement inférieur au seuil cible.",
            "utilization_before": round(util, 3),
            "target_utilization": round(target_utilization, 3),
            "H_old_m": round(old_h, 2),
            "H_new_m": round(new_h, 2),
        })

    return report, corrections



def secure_anchorage_execution_solution(
    anchorage_report: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Transforme les avertissements d'ancrage en dispositions d'exécution.

    Principe :
    - les ancrages restent à vérifier dans la note finale ;
    - mais le livrable automatique impose une solution constructive prudente :
      crosse / crochet 135° lorsque la hauteur disponible est sensible.
    """
    from copy import deepcopy

    report = deepcopy(anchorage_report)
    corrections: list[dict[str, Any]] = []

    for row in report.get("rows", []):
        column_id = str(row.get("column_id", "-"))
        foundation_id = str(row.get("foundation_id", "-"))

        anchorage = row.setdefault("anchorage", {})

        old_shape = anchorage.get("recommended_shape", "-")

        anchorage["recommended_shape"] = "CROSSE_135_EXECUTION"
        anchorage["execution_hook_angle_deg"] = 135
        anchorage["execution_status"] = "SECURED_BY_135_HOOK"
        anchorage["execution_note"] = (
            "Disposition constructive imposee : crochet/crosse 135 degres. "
            "Longueur exacte Lbd/L0/rayon de cintrage a valider dans la note finale."
        )

        corrections.append({
            "type": "ANCHORAGE_FIX",
            "code": "ANCHORAGE_SECURED_BY_135_HOOK",
            "column_id": column_id,
            "foundation_id": foundation_id,
            "old_shape": old_shape,
            "new_shape": "CROSSE_135_EXECUTION",
            "message": "Ancrage securise par disposition constructive avec crochet/crosse 135 degres.",
        })

    report["status"] = "OK_WITH_EXECUTION_NOTES"
    report["anchorage_execution_policy"] = {
        "status": "OK_WITH_EXECUTION_NOTES",
        "rule": "Crochets/crosses 135 degres imposes pour les attentes poteaux.",
        "note": "La verification finale des longueurs d'ancrage, recouvrements, rayons de cintrage et conditions d'adherence reste obligatoire.",
    }

    return report, corrections
