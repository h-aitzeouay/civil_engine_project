from __future__ import annotations

from typing import Any


def cluster_coordinates(values: list[float], tolerance_m: float = 0.20) -> list[float]:
    """
    Regroupe des coordonnées proches pour créer les axes.
    Exemple : 4.499, 4.501 -> 4.50
    """
    if not values:
        return []

    sorted_values = sorted(values)
    clusters: list[list[float]] = []

    for value in sorted_values:
        if not clusters:
            clusters.append([value])
            continue

        current_cluster = clusters[-1]
        average = sum(current_cluster) / len(current_cluster)

        if abs(value - average) <= tolerance_m:
            current_cluster.append(value)
        else:
            clusters.append([value])

    axes = [
        round(sum(cluster) / len(cluster), 4)
        for cluster in clusters
    ]

    return axes


def spans_from_axes(axes: list[float]) -> list[dict[str, Any]]:
    """
    Calcule les portées entre axes successifs.
    """
    spans = []

    for index in range(len(axes) - 1):
        start = axes[index]
        end = axes[index + 1]
        span = round(end - start, 4)

        spans.append({
            "from_axis": index + 1,
            "to_axis": index + 2,
            "start_m": start,
            "end_m": end,
            "span_m": span,
        })

    return spans


def detect_axes_and_spans(
    model: dict[str, Any],
    level_name: str = "FONDATION",
    axis_tolerance_m: float = 0.20,
    max_preferred_span_m: float = 6.00,
) -> dict[str, Any]:
    """
    Détecte les axes X/Y à partir des poteaux d'un niveau.
    Par défaut, on utilise FONDATION, car c'est la base structurelle.
    """
    levels = model.get("levels", [])

    selected_level = None

    for level in levels:
        if level.get("name") == level_name:
            selected_level = level
            break

    if selected_level is None:
        return {
            "status": "ERROR",
            "message": f"Niveau {level_name} introuvable.",
            "axes_x": [],
            "axes_y": [],
            "spans_x": [],
            "spans_y": [],
            "warnings": [],
            "errors": [
                {
                    "code": "LEVEL_NOT_FOUND",
                    "message": f"Niveau {level_name} introuvable dans model.json.",
                }
            ],
        }

    columns = selected_level.get("columns", [])

    if not columns:
        return {
            "status": "ERROR",
            "message": f"Aucun poteau trouvé au niveau {level_name}.",
            "axes_x": [],
            "axes_y": [],
            "spans_x": [],
            "spans_y": [],
            "warnings": [],
            "errors": [
                {
                    "code": "NO_COLUMNS_FOR_AXES",
                    "message": f"Aucun poteau trouvé au niveau {level_name}.",
                }
            ],
        }

    x_values = [float(column["cx"]) for column in columns]
    y_values = [float(column["cy"]) for column in columns]

    axes_x = cluster_coordinates(x_values, tolerance_m=axis_tolerance_m)
    axes_y = cluster_coordinates(y_values, tolerance_m=axis_tolerance_m)

    spans_x = spans_from_axes(axes_x)
    spans_y = spans_from_axes(axes_y)

    warnings = []
    errors = []

    for span in spans_x:
        if span["span_m"] > max_preferred_span_m:
            warnings.append({
                "code": "LARGE_SPAN_X",
                "message": f"Portée X importante : {span['span_m']} m entre axes {span['from_axis']} et {span['to_axis']}.",
                "span": span,
            })

    for span in spans_y:
        if span["span_m"] > max_preferred_span_m:
            warnings.append({
                "code": "LARGE_SPAN_Y",
                "message": f"Portée Y importante : {span['span_m']} m entre axes {span['from_axis']} et {span['to_axis']}.",
                "span": span,
            })

    status = "OK" if not warnings and not errors else "WARNING"
    if errors:
        status = "ERROR"

    return {
        "status": status,
        "level_used": level_name,
        "axis_tolerance_m": axis_tolerance_m,
        "max_preferred_span_m": max_preferred_span_m,
        "axes_x": axes_x,
        "axes_y": axes_y,
        "spans_x": spans_x,
        "spans_y": spans_y,
        "columns_count": len(columns),
        "warnings": warnings,
        "errors": errors,
        "summary": {
            "axes_x_count": len(axes_x),
            "axes_y_count": len(axes_y),
            "spans_x_count": len(spans_x),
            "spans_y_count": len(spans_y),
            "warnings_count": len(warnings),
            "errors_count": len(errors),
        },
    }