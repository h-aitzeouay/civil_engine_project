from __future__ import annotations

from typing import Any


def get_foundation_level(model: dict[str, Any]) -> dict[str, Any] | None:
    for level in model.get("levels", []):
        if level.get("name") == "FONDATION":
            return level
    return None


def bbox_from_points(points: list[list[float]]) -> dict[str, float] | None:
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


def get_foundation_bbox(model: dict[str, Any]) -> dict[str, float] | None:
    foundation = get_foundation_level(model)

    if foundation is None:
        return None

    points = []

    for footprint in foundation.get("footprints", []):
        points.extend(footprint.get("points", []))

    return bbox_from_points(points)


def get_property_limit_bbox(model: dict[str, Any]) -> dict[str, float] | None:
    points = []
    global_layers = model.get("global_layers", {})

    for item in global_layers.get("limite_propriete", []):
        points.extend(item.get("points", []))

    bbox = bbox_from_points(points)

    if bbox is not None:
        return bbox

    return get_foundation_bbox(model)


def raw_column_boxes(model: dict[str, Any]) -> dict[str, dict[str, float]]:
    foundation = get_foundation_level(model)

    if foundation is None:
        return {}

    result = {}

    for column in foundation.get("columns", []):
        column_id = column["id"]
        cx = float(column.get("cx", 0.0))
        cy = float(column.get("cy", 0.0))
        points = column.get("points", [])

        if points:
            xs = [float(p[0]) for p in points]
            ys = [float(p[1]) for p in points]

            xmin = min(xs)
            xmax = max(xs)
            ymin = min(ys)
            ymax = max(ys)
        else:
            xmin = cx - 0.125
            xmax = cx + 0.125
            ymin = cy - 0.125
            ymax = cy + 0.125

        result[column_id] = {
            "id": column_id,
            "raw_cx": cx,
            "raw_cy": cy,
            "raw_xmin": xmin,
            "raw_xmax": xmax,
            "raw_ymin": ymin,
            "raw_ymax": ymax,
            "xmin": xmin,
            "xmax": xmax,
            "ymin": ymin,
            "ymax": ymax,
            "c1_m": xmax - xmin,
            "c2_m": ymax - ymin,
        }

    return result


def shift_box_inside_limit(
    box: dict[str, float],
    limit: dict[str, float] | None,
) -> dict[str, float]:
    item = dict(box)

    if limit is None:
        item["cx"] = (item["xmin"] + item["xmax"]) / 2.0
        item["cy"] = (item["ymin"] + item["ymax"]) / 2.0
        item["was_shifted"] = False
        return item

    xmin = float(item["xmin"])
    xmax = float(item["xmax"])
    ymin = float(item["ymin"])
    ymax = float(item["ymax"])

    width = xmax - xmin
    height = ymax - ymin

    lxmin = float(limit["xmin"])
    lxmax = float(limit["xmax"])
    lymin = float(limit["ymin"])
    lymax = float(limit["ymax"])

    shifted = False

    if width <= lxmax - lxmin:
        if xmin < lxmin:
            dx = lxmin - xmin
            xmin += dx
            xmax += dx
            shifted = True

        if xmax > lxmax:
            dx = xmax - lxmax
            xmin -= dx
            xmax -= dx
            shifted = True

    if height <= lymax - lymin:
        if ymin < lymin:
            dy = lymin - ymin
            ymin += dy
            ymax += dy
            shifted = True

        if ymax > lymax:
            dy = ymax - lymax
            ymin -= dy
            ymax -= dy
            shifted = True

    item["xmin"] = round(xmin, 4)
    item["xmax"] = round(xmax, 4)
    item["ymin"] = round(ymin, 4)
    item["ymax"] = round(ymax, 4)
    item["cx"] = round((xmin + xmax) / 2.0, 4)
    item["cy"] = round((ymin + ymax) / 2.0, 4)
    item["was_shifted"] = shifted

    return item


def get_effective_column_boxes(model: dict[str, Any]) -> dict[str, dict[str, float]]:
    """
    Poteaux effectifs pour plans de fondations.

    Si un poteau de rive est lu centré sur l'axe d'emprise,
    son rectangle est recalé à l'intérieur de la limite constructive.
    """
    limit = get_property_limit_bbox(model)
    raw_boxes = raw_column_boxes(model)

    return {
        column_id: shift_box_inside_limit(box, limit)
        for column_id, box in raw_boxes.items()
    }


def get_effective_column_centers(model: dict[str, Any]) -> dict[str, dict[str, float]]:
    boxes = get_effective_column_boxes(model)

    return {
        column_id: {
            "cx": float(box["cx"]),
            "cy": float(box["cy"]),
        }
        for column_id, box in boxes.items()
    }
