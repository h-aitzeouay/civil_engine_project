from __future__ import annotations

from typing import Any

from civil_engine.foundations.column_effective import get_effective_column_boxes


def anchorage_length_m(
    diameter_mm: float,
    factor_phi: float = 50.0,
    minimum_m: float = 0.60,
) -> float:
    """
    Longueur d'ancrage indicative.
    Par défaut : Lbd = max(50 phi, 0.60 m)
    """
    return round(max(factor_phi * diameter_mm / 1000.0, minimum_m), 2)


def lap_length_m(
    diameter_mm: float,
    factor_phi: float = 60.0,
    minimum_m: float = 0.70,
) -> float:
    """
    Longueur de recouvrement indicative.
    Par défaut : L0 = max(60 phi, 0.70 m)
    """
    return round(max(factor_phi * diameter_mm / 1000.0, minimum_m), 2)


def hook_leg_m(
    diameter_mm: float,
    factor_phi: float = 15.0,
    minimum_m: float = 0.20,
) -> float:
    """
    Longueur indicative de retour/crosse.
    """
    return round(max(factor_phi * diameter_mm / 1000.0, minimum_m), 2)


def internal_frame_dimensions(
    column_box: dict[str, float],
    cover_m: float = 0.05,
) -> dict[str, float]:
    c1 = float(column_box["xmax"]) - float(column_box["xmin"])
    c2 = float(column_box["ymax"]) - float(column_box["ymin"])

    return {
        "column_dim_x_m": round(c1, 2),
        "column_dim_y_m": round(c2, 2),
        "frame_inside_x_m": round(max(c1 - 2.0 * cover_m, 0.10), 2),
        "frame_inside_y_m": round(max(c2 - 2.0 * cover_m, 0.10), 2),
    }


def starter_bars_count(column_box: dict[str, float]) -> int:
    """
    Nombre indicatif d'attentes selon taille du poteau.
    """
    c1 = float(column_box["xmax"]) - float(column_box["xmin"])
    c2 = float(column_box["ymax"]) - float(column_box["ymin"])

    count = 4

    if c1 >= 0.35:
        count += 2

    if c2 >= 0.35:
        count += 2

    return count


def foundation_for_column(
    strategy_report: dict[str, Any],
    column_id: str,
) -> dict[str, Any] | None:
    for element in strategy_report.get("final_foundations", []):
        if column_id in element.get("columns", []):
            return element

    return None


def recommended_anchor_shape(
    foundation: dict[str, Any] | None,
    lbd_m: float,
) -> str:
    if foundation is None:
        return "A_VERIFIER"

    h_m = float(foundation.get("H_m", 0.0))

    # Si l'épaisseur ne permet pas un ancrage vertical confortable,
    # on recommande une attente coudée/crossée à vérifier.
    if h_m < 0.75 * lbd_m:
        return "ATTENTE_COUDEE_OU_CROSSE_A_ETUDIER"

    return "ATTENTE_DROITE"


def build_anchorage_details(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    starter_diameter_mm: float = 14.0,
    stirrup_diameter_mm: float = 8.0,
    cover_m: float = 0.05,
    lbd_factor_phi: float = 50.0,
    lap_factor_phi: float = 60.0,
    hook_factor_phi: float = 15.0,
) -> dict[str, Any]:
    columns = get_effective_column_boxes(model)

    lbd = anchorage_length_m(
        diameter_mm=starter_diameter_mm,
        factor_phi=lbd_factor_phi,
    )

    l0 = lap_length_m(
        diameter_mm=starter_diameter_mm,
        factor_phi=lap_factor_phi,
    )

    hook = hook_leg_m(
        diameter_mm=starter_diameter_mm,
        factor_phi=hook_factor_phi,
    )

    rows = []
    warnings = []

    for column_id, column_box in columns.items():
        foundation = foundation_for_column(strategy_report, column_id)
        foundation_id = "-"
        foundation_type = "-"
        h_m = None

        if foundation is not None:
            foundation_id = str(foundation.get("id", "-"))
            foundation_type = str(foundation.get("type", "-"))
            h_m = foundation.get("H_m")

        frame = internal_frame_dimensions(
            column_box=column_box,
            cover_m=cover_m,
        )

        nb_bars = starter_bars_count(column_box)

        shape = recommended_anchor_shape(
            foundation=foundation,
            lbd_m=lbd,
        )

        if shape != "ATTENTE_DROITE":
            warnings.append({
                "code": "ANCHORAGE_SHAPE_TO_REVIEW",
                "column_id": column_id,
                "foundation_id": foundation_id,
                "message": "Epaisseur de fondation probablement insuffisante pour ancrage droit complet. Prevoir attente coudee/crosse ou verifier Lbd reel.",
            })

        rows.append({
            "column_id": column_id,
            "foundation_id": foundation_id,
            "foundation_type": foundation_type,
            "H_m": h_m,
            "starter_bars": {
                "count": nb_bars,
                "diameter_mm": starter_diameter_mm,
                "label": f"{nb_bars}HA{int(starter_diameter_mm)}",
            },
            "stirrups": {
                "diameter_mm": stirrup_diameter_mm,
                "label": f"Cadres HA{int(stirrup_diameter_mm)}",
                "frame_inside_x_m": frame["frame_inside_x_m"],
                "frame_inside_y_m": frame["frame_inside_y_m"],
            },
            "anchorage": {
                "Lbd_m": lbd,
                "lap_L0_m": l0,
                "hook_leg_m": hook,
                "recommended_shape": shape,
            },
            "column_dimensions": {
                "x_m": frame["column_dim_x_m"],
                "y_m": frame["column_dim_y_m"],
            },
        })

    status = "WARNING" if warnings else "OK"

    return {
        "status": status,
        "method": "anchorage_and_lap_details_v0_25",
        "hypotheses": {
            "starter_diameter_mm": starter_diameter_mm,
            "stirrup_diameter_mm": stirrup_diameter_mm,
            "cover_m": cover_m,
            "Lbd_rule": f"max({lbd_factor_phi:.0f}phi, 0.60m)",
            "lap_rule": f"max({lap_factor_phi:.0f}phi, 0.70m)",
            "hook_rule": f"max({hook_factor_phi:.0f}phi, 0.20m)",
            "note": "Valeurs indicatives de prédimensionnement. A recalculer selon EC2/BAEL, classe beton, adherence, position des barres, efforts et dispositions sismiques.",
        },
        "rows": rows,
        "warnings": warnings,
        "errors": [],
        "summary": {
            "columns_checked": len(rows),
            "warnings_count": len(warnings),
            "errors_count": 0,
        },
    }
