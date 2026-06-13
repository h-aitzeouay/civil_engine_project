from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import ezdxf


GLOBAL_LAYERS = {
    "LIMITE-PROPRIETE",
    "SS-RAMPE",
    "JOINT-DILATATION",
}

CLOSED_POLYLINE_TYPES = {
    "EMPRISE",
    "VOILES",
    "VIDE-COURS",
    "VIDE-ESCALIER",
    "VIDE-GAINE",
    "CHARGE-Q",
}


def normalize_level_name(raw_name: str) -> str:
    """
    Normalise les noms de niveaux :
    R+1      -> ETAGE1
    ETAGE 1  -> ETAGE1
    RDC      -> RDC
    """
    name = raw_name.strip().upper().replace(" ", "")

    if name.startswith("R+"):
        number = name.replace("R+", "")
        if number.isdigit():
            return f"ETAGE{number}"

    if name.startswith("ETAGE"):
        number = name.replace("ETAGE", "")
        if number.isdigit():
            return f"ETAGE{number}"

    return name


def parse_charge_value(text: str) -> float | None:
    """
    Extrait une valeur de surcharge depuis un texte de zone CHARGE-Q.
    Accepte par ex. "2.5", "2,5 kN/m2", "Q=3.0", "+ 1.5 kN/m²".
    Retourne la valeur en kN/m2, ou None si illisible.
    """
    if text is None:
        return None
    cleaned = text.replace(",", ".")
    matches = re.findall(r"[-+]?\d*\.?\d+", cleaned)
    if not matches:
        return None
    try:
        value = float(matches[0])
    except ValueError:
        return None
    if value < 0:
        return None
    return round(value, 3)


def split_layer(layer_name: str) -> tuple[str | None, str]:
    """
    Sépare un calque du type RDC-POTEAUX.

    Résultat :
    niveau = RDC
    type_calque = POTEAUX
    """
    layer = layer_name.strip().upper()

    if layer in GLOBAL_LAYERS:
        return None, layer

    if "-" not in layer:
        return None, layer

    level_name, layer_type = layer.split("-", 1)
    return normalize_level_name(level_name), layer_type


def polygon_area(points: list[list[float]]) -> float:
    """
    Calcule l'aire d'une polyligne fermée.
    """
    if len(points) < 3:
        return 0.0

    area = 0.0
    for index, point in enumerate(points):
        x1, y1 = point
        x2, y2 = points[(index + 1) % len(points)]
        area += x1 * y2 - x2 * y1

    return round(abs(area) / 2.0, 4)


def bbox_from_points(points: list[list[float]]) -> dict[str, float]:
    """
    Calcule le rectangle enveloppe d'une géométrie.
    """
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]

    xmin = min(xs)
    xmax = max(xs)
    ymin = min(ys)
    ymax = max(ys)

    return {
        "xmin": round(xmin, 4),
        "ymin": round(ymin, 4),
        "xmax": round(xmax, 4),
        "ymax": round(ymax, 4),
        "width": round(xmax - xmin, 4),
        "height": round(ymax - ymin, 4),
    }


def translate_point(point: list[float], origin: list[float]) -> list[float]:
    """
    Superposition ORIGINE :
    coordonnée globale = coordonnée brute - origine du niveau.
    """
    return [
        round(point[0] - origin[0], 4),
        round(point[1] - origin[1], 4),
    ]


def translate_points(points: list[list[float]], origin: list[float]) -> list[list[float]]:
    return [translate_point(point, origin) for point in points]


def parse_altitude(text: str) -> float | None:
    """
    Exemples acceptés :
    +3.06
    +3.06/TN
    -2.80
    """
    match = re.search(r"[-+]?\d+(?:[.,]\d+)?", text)

    if not match:
        return None

    return float(match.group(0).replace(",", "."))


def lwpolyline_points(entity: Any) -> list[list[float]]:
    """
    Extrait les points XY d'une LWPOLYLINE ezdxf.
    """
    return [
        [round(float(point[0]), 4), round(float(point[1]), 4)]
        for point in entity.get_points()
    ]


def init_level(level_name: str, origin: list[float]) -> dict[str, Any]:
    return {
        "name": level_name,
        "origin_raw": origin,
        "z_top_m": None,
        "footprints": [],
        "columns": [],
        "walls": [],
        "voids": [],
        "load_zones": [],
        "load_zone_labels": [],
        "slab_directions": [],
        "stairs": [],
        "layers": set(),
    }


def read_dxf_model(dxf_path: str | Path) -> dict[str, Any]:
    """
    Génère un model.json simplifié.

    Important :
    les coordonnées retournées sont déjà superposées par ORIGINE.
    """
    dxf_path = Path(dxf_path)

    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    layers_detected: set[str] = set()
    detected_levels: set[str] = set()
    origins: dict[str, list[float]] = {}

    warnings: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []

    # Premier passage : détecter niveaux, calques et ORIGINE
    for entity in msp:
        layer = entity.dxf.layer.upper()
        layers_detected.add(layer)

        level_name, layer_type = split_layer(layer)

        if level_name is None:
            continue

        detected_levels.add(level_name)

        if layer_type == "ORIGINE":
            if entity.dxftype() == "POINT":
                point = entity.dxf.location
                origins[level_name] = [
                    round(float(point.x), 4),
                    round(float(point.y), 4),
                ]
            else:
                warnings.append({
                    "code": "ORIGINE_NOT_POINT",
                    "message": f"Le calque {layer} doit contenir un POINT.",
                })

    # Initialiser les niveaux
    levels: dict[str, dict[str, Any]] = {}

    for level_name in sorted(detected_levels):
        if level_name not in origins:
            warnings.append({
                "code": "MISSING_ORIGIN",
                "message": f"Le niveau {level_name} n'a pas de point {level_name}-ORIGINE. Origine [0,0] utilisée.",
            })

        levels[level_name] = init_level(
            level_name=level_name,
            origin=origins.get(level_name, [0.0, 0.0]),
        )

    global_layers = {
        "limite_propriete": [],
        "ss_rampe": [],
        "joint_dilatation": [],
    }

    column_counter: dict[str, int] = {}

    # Deuxième passage : extraire les géométries
    for entity in msp:
        layer = entity.dxf.layer.upper()
        level_name, layer_type = split_layer(layer)
        entity_type = entity.dxftype()

        if level_name is None:
            # Calques globaux
            if layer in GLOBAL_LAYERS and entity_type == "LWPOLYLINE":
                points = lwpolyline_points(entity)

                item = {
                    "layer": layer,
                    "points": points,
                    "closed": bool(entity.closed),
                    "area_m2": polygon_area(points) if entity.closed else 0.0,
                    "bbox": bbox_from_points(points),
                }

                if layer == "LIMITE-PROPRIETE":
                    global_layers["limite_propriete"].append(item)
                elif layer == "SS-RAMPE":
                    global_layers["ss_rampe"].append(item)
                elif layer == "JOINT-DILATATION":
                    global_layers["joint_dilatation"].append(item)

            continue

        if level_name not in levels:
            continue

        level = levels[level_name]
        origin = level["origin_raw"]
        level["layers"].add(layer)

        if entity_type == "LWPOLYLINE":
            points_raw = lwpolyline_points(entity)
            points_global = translate_points(points_raw, origin)

            if layer_type in CLOSED_POLYLINE_TYPES and not entity.closed:
                errors.append({
                    "code": "POLYLINE_NOT_CLOSED",
                    "message": f"Le calque {layer} doit contenir une LWPOLYLINE fermée.",
                })

            item = {
                "layer": layer,
                "points": points_global,
                "points_raw": points_raw,
                "closed": bool(entity.closed),
                "area_m2": polygon_area(points_global) if entity.closed else 0.0,
                "bbox": bbox_from_points(points_global),
            }

            if layer_type == "EMPRISE":
                level["footprints"].append(item)

            elif layer_type == "POTEAUX":
                column_counter[level_name] = column_counter.get(level_name, 0) + 1
                bbox = item["bbox"]

                level["columns"].append({
                    "id": f"P{column_counter[level_name]:02d}",
                    "shape": "RECTANGLE_OR_POLYLINE",
                    "cx": round((bbox["xmin"] + bbox["xmax"]) / 2.0, 4),
                    "cy": round((bbox["ymin"] + bbox["ymax"]) / 2.0, 4),
                    "bx": bbox["width"],
                    "by": bbox["height"],
                    "area_m2": item["area_m2"],
                    "points": points_global,
                    "source_layer": layer,
                })

            elif layer_type == "VOILES":
                level["walls"].append(item)

            elif layer_type.startswith("VIDE"):
                level["voids"].append(item)

            elif layer_type == "CHARGE-Q":
                level["load_zones"].append(item)

            elif layer_type == "ESCALIER-FOULEE":
                level["stairs"].append(item)

            elif layer_type == "SENS-PLANCHER":
                level["slab_directions"].append(item)

        elif entity_type == "CIRCLE" and layer_type == "POTEAUX":
            center_raw = [
                round(float(entity.dxf.center.x), 4),
                round(float(entity.dxf.center.y), 4),
            ]
            center_global = translate_point(center_raw, origin)
            radius = round(float(entity.dxf.radius), 4)

            column_counter[level_name] = column_counter.get(level_name, 0) + 1

            level["columns"].append({
                "id": f"P{column_counter[level_name]:02d}",
                "shape": "CIRCLE",
                "cx": center_global[0],
                "cy": center_global[1],
                "diameter": round(2 * radius, 4),
                "area_m2": round(3.1416 * radius * radius, 4),
                "source_layer": layer,
            })

        elif entity_type == "POINT" and layer_type == "POTEAUX":
            point = entity.dxf.location

            point_raw = [
                round(float(point.x), 4),
                round(float(point.y), 4),
            ]
            point_global = translate_point(point_raw, origin)

            column_counter[level_name] = column_counter.get(level_name, 0) + 1

            level["columns"].append({
                "id": f"P{column_counter[level_name]:02d}",
                "shape": "POINT_DEFAULT_25X25",
                "cx": point_global[0],
                "cy": point_global[1],
                "bx": 0.25,
                "by": 0.25,
                "area_m2": 0.0625,
                "source_layer": layer,
                "warning": "Poteau représenté par un POINT. Section supposée 25x25 cm.",
            })

            warnings.append({
                "code": "POINT_COLUMN_DEFAULT_SECTION",
                "message": f"Un poteau POINT sur {layer} a été assimilé à 25x25 cm.",
            })

        elif entity_type in {"TEXT", "MTEXT"} and layer_type == "NIVEAU":
            if entity_type == "TEXT":
                text = entity.dxf.text
            else:
                text = entity.plain_text()

            altitude = parse_altitude(text)

            if altitude is not None:
                level["z_top_m"] = altitude

        elif entity_type in {"TEXT", "MTEXT"} and layer_type == "CHARGE-Q":
            if entity_type == "TEXT":
                raw_text = entity.dxf.text
                ins = entity.dxf.insert
            else:
                raw_text = entity.plain_text()
                ins = entity.dxf.insert

            q_value = parse_charge_value(raw_text)
            pos_raw = [round(float(ins.x), 4), round(float(ins.y), 4)]
            pos_global = translate_point(pos_raw, origin)

            if q_value is not None:
                level["load_zone_labels"].append({
                    "q_add_kN_m2": q_value,
                    "position": pos_global,
                    "raw_text": raw_text,
                })

    # Contrôles finaux
    for level_name, level in levels.items():
        if len(level["footprints"]) == 0:
            warnings.append({
                "code": "MISSING_EMPRISE",
                "message": f"Le niveau {level_name} n'a pas d'emprise {level_name}-EMPRISE.",
            })

        if level["z_top_m"] is None:
            warnings.append({
                "code": "MISSING_NIVEAU_TEXT",
                "message": f"Le niveau {level_name} n'a pas de texte d'altitude {level_name}-NIVEAU.",
            })

    clean_levels = []

    for level in levels.values():
        clean_level = dict(level)
        clean_level["layers"] = sorted(list(clean_level["layers"]))
        clean_levels.append(clean_level)

    model = {
        "schema_version": "0.3",
        "source_file": str(dxf_path),
        "units": "m",
        "superposition_rule": "global_coordinates = raw_coordinates - level_origin",
        "layers_detected": sorted(list(layers_detected)),
        "levels_detected": sorted(list(levels.keys())),
        "levels": clean_levels,
        "global_layers": global_layers,
        "validation": {
            "status": "OK" if not errors else "ERROR",
            "warnings": warnings,
            "errors": errors,
            "summary": {
                "levels_count": len(levels),
                "layers_count": len(layers_detected),
                "warnings_count": len(warnings),
                "errors_count": len(errors),
            },
        },
    }

    return model


def read_dxf_summary(dxf_path: str | Path) -> dict[str, Any]:
    """
    Résumé simple pour /validate-dxf.
    """
    model = read_dxf_model(dxf_path)

    levels_summary = []

    for level in model["levels"]:
        levels_summary.append({
            "level": level["name"],
            "has_origin": level["origin_raw"] != [0.0, 0.0] or level["name"] == "FONDATION",
            "origin": level["origin_raw"],
            "emprises_count": len(level["footprints"]),
            "poteaux_count": len(level["columns"]),
            "voiles_count": len(level["walls"]),
            "vides_count": len(level["voids"]),
            "niveau_text_found": level["z_top_m"] is not None,
            "layers": level["layers"],
        })

    return {
        "status": model["validation"]["status"],
        "file": model["source_file"],
        "layers_detected": model["layers_detected"],
        "levels_detected": model["levels_detected"],
        "levels": levels_summary,
        "warnings": model["validation"]["warnings"],
        "errors": model["validation"]["errors"],
        "summary": model["validation"]["summary"],
    }