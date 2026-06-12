from __future__ import annotations

from typing import Any

from civil_engine.checks.axis_detection import detect_axes_and_spans


def level_sort_key(level_name: str) -> tuple[int, int]:
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


def nearest_axis_index(value: float, axes: list[float]) -> int:
    """
    Retourne l'indice de l'axe le plus proche.
    """
    distances = [abs(value - axis) for axis in axes]
    return distances.index(min(distances))


def tributary_width(axis_index: int, axes: list[float]) -> float:
    """
    Largeur tributaire d'un axe.

    Cas axe de rive :
    - demi-portée vers l'intérieur.

    Cas axe intérieur :
    - demi-portée à gauche + demi-portée à droite.
    """
    if len(axes) == 1:
        return 0.0

    if axis_index == 0:
        return (axes[1] - axes[0]) / 2.0

    if axis_index == len(axes) - 1:
        return (axes[-1] - axes[-2]) / 2.0

    left = (axes[axis_index] - axes[axis_index - 1]) / 2.0
    right = (axes[axis_index + 1] - axes[axis_index]) / 2.0

    return left + right


def get_level_area(level: dict[str, Any]) -> float:
    """
    Surface brute du niveau à partir des emprises.
    """
    return round(
        sum(footprint.get("area_m2", 0.0) for footprint in level.get("footprints", [])),
        4,
    )


def get_void_area(level: dict[str, Any]) -> float:
    """
    Surface totale des vides du niveau.
    """
    return round(
        sum(void.get("area_m2", 0.0) for void in level.get("voids", [])),
        4,
    )


def compute_tributary_areas(
    model: dict[str, Any],
    axis_tolerance_m: float = 0.20,
) -> dict[str, Any]:
    """
    Calcule les surfaces tributaires simplifiées des poteaux.

    Méthode :
    - axes X/Y détectés à partir des poteaux de fondation ;
    - chaque poteau est rattaché à l'axe X/Y le plus proche ;
    - surface brute = largeur tributaire X × largeur tributaire Y ;
    - surface nette = surface brute × coefficient de réduction des vides.

    Remarque :
    Cette méthode est volontairement simple et robuste.
    Elle sera remplacée plus tard par une méthode Voronoï bornée par l'emprise.
    """
    axes_report = detect_axes_and_spans(
        model=model,
        level_name="FONDATION",
        axis_tolerance_m=axis_tolerance_m,
        max_preferred_span_m=6.00,
    )

    if axes_report["status"] == "ERROR":
        return {
            "status": "ERROR",
            "message": "Impossible de calculer les surfaces tributaires sans axes.",
            "axes_report": axes_report,
            "levels": [],
            "warnings": [],
            "errors": axes_report.get("errors", []),
        }

    axes_x = axes_report["axes_x"]
    axes_y = axes_report["axes_y"]

    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    result_levels: list[dict[str, Any]] = []

    levels = sorted(
        model.get("levels", []),
        key=lambda level: level_sort_key(level["name"]),
    )

    structural_levels = [
        level for level in levels
        if level["name"] != "FONDATION"
    ]

    for level in structural_levels:
        level_name = level["name"]
        gross_floor_area = get_level_area(level)
        void_area = get_void_area(level)
        net_floor_area = round(max(gross_floor_area - void_area, 0.0), 4)

        if gross_floor_area > 0:
            void_reduction_factor = round(net_floor_area / gross_floor_area, 6)
        else:
            void_reduction_factor = 1.0
            warnings.append({
                "code": "ZERO_FLOOR_AREA",
                "level": level_name,
                "message": f"Surface brute nulle ou absente pour le niveau {level_name}.",
            })

        columns_results = []

        for column in level.get("columns", []):
            cx = float(column["cx"])
            cy = float(column["cy"])

            ix = nearest_axis_index(cx, axes_x)
            iy = nearest_axis_index(cy, axes_y)

            tributary_width_x = tributary_width(ix, axes_x)
            tributary_width_y = tributary_width(iy, axes_y)

            gross_area = round(tributary_width_x * tributary_width_y, 4)
            net_area = round(gross_area * void_reduction_factor, 4)

            column_type = "INTERIOR"

            if ix in {0, len(axes_x) - 1} and iy in {0, len(axes_y) - 1}:
                column_type = "CORNER"
            elif ix in {0, len(axes_x) - 1} or iy in {0, len(axes_y) - 1}:
                column_type = "EDGE"

            columns_results.append({
                "level": level_name,
                "column_id": column["id"],
                "cx": cx,
                "cy": cy,
                "axis_x_index": ix + 1,
                "axis_y_index": iy + 1,
                "column_type": column_type,
                "tributary_width_x_m": round(tributary_width_x, 4),
                "tributary_width_y_m": round(tributary_width_y, 4),
                "tributary_area_gross_m2": gross_area,
                "void_reduction_factor": void_reduction_factor,
                "tributary_area_net_m2": net_area,
            })

        sum_gross = round(
            sum(item["tributary_area_gross_m2"] for item in columns_results),
            4,
        )

        sum_net = round(
            sum(item["tributary_area_net_m2"] for item in columns_results),
            4,
        )

        result_levels.append({
            "level": level_name,
            "gross_floor_area_m2": gross_floor_area,
            "void_area_m2": void_area,
            "net_floor_area_m2": net_floor_area,
            "void_reduction_factor": void_reduction_factor,
            "columns_count": len(columns_results),
            "sum_tributary_gross_m2": sum_gross,
            "sum_tributary_net_m2": sum_net,
            "columns": columns_results,
        })

        if abs(sum_gross - gross_floor_area) > 0.01:
            warnings.append({
                "code": "TRIBUTARY_SUM_DIFFERS_FROM_FLOOR",
                "level": level_name,
                "message": (
                    f"La somme des surfaces tributaires brutes ({sum_gross} m²) "
                    f"diffère de la surface brute du niveau ({gross_floor_area} m²)."
                ),
            })

    status = "OK"

    if errors:
        status = "ERROR"
    elif warnings:
        status = "WARNING"

    return {
        "status": status,
        "method": "simplified_axis_midspan_method",
        "axes_x": axes_x,
        "axes_y": axes_y,
        "levels": result_levels,
        "warnings": warnings,
        "errors": errors,
        "summary": {
            "levels_count": len(result_levels),
            "warnings_count": len(warnings),
            "errors_count": len(errors),
        },
    }