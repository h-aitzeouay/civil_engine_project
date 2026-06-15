from __future__ import annotations

"""
Lecteur IFC -> model.json (meme structure que civil_engine.readers.dxf_reader).

Objectif : permettre le workflow Ifc -> API -> plan + note de calcul en
reutilisant integralement le pipeline fondations existant (qui consomme le
dictionnaire `model` produit par read_dxf_model).

Conventions de mapping (documentees) :
- Les IfcBuildingStorey sont tries par altitude croissante.
  Le niveau le plus bas devient "FONDATION", puis "RDC", "ETAGE1", "ETAGE2"...
- Chaque IfcColumn est rattache au niveau (storey) qui le contient.
  Les poteaux sont regroupes en "piles" verticales par proximite en plan
  (tolerance configurable) afin de partager un identifiant P01, P02, ...
  Le niveau FONDATION recoit un poteau "base" par pile (la ou est calculee la
  semelle), les niveaux superieurs portent les poteaux pour la descente de
  charges.
- La section des poteaux est lue depuis le profil (IfcRectangleProfileDef /
  IfcCircleProfileDef). A defaut, une section carree par defaut est supposee.
- Les IfcWall fournissent un axe (representation "Axis") transforme en segment
  de voile (calque NIVEAU-VOILE-AXE equivalent) sur le niveau FONDATION.
- L'emprise (footprint) est le rectangle englobant de tous les elements
  structuraux, elargi d'une marge. Elle est dupliquee sur chaque niveau pour la
  descente de charges.

Toutes les coordonnees retournees sont en metres.
"""

from pathlib import Path
from typing import Any

import numpy as np

import ifcopenshell
import ifcopenshell.util.unit as ifc_unit
import ifcopenshell.util.placement as ifc_placement
import ifcopenshell.util.element as ifc_element
import ifcopenshell.util.representation as ifc_representation


DEFAULT_COLUMN_SIDE_M = 0.30
DEFAULT_WALL_THICKNESS_M = 0.20


def _round_point(point: list[float] | tuple[float, float]) -> list[float]:
    return [round(float(point[0]), 4), round(float(point[1]), 4)]


def polygon_area(points: list[list[float]]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    for index, point in enumerate(points):
        x1, y1 = point
        x2, y2 = points[(index + 1) % len(points)]
        area += x1 * y2 - x2 * y1
    return round(abs(area) / 2.0, 4)


def bbox_from_points(points: list[list[float]]) -> dict[str, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    return {
        "xmin": round(xmin, 4),
        "ymin": round(ymin, 4),
        "xmax": round(xmax, 4),
        "ymax": round(ymax, 4),
        "width": round(xmax - xmin, 4),
        "height": round(ymax - ymin, 4),
    }


def normalize_level_name(index: int) -> str:
    """index 0 -> FONDATION, 1 -> RDC, 2 -> ETAGE1, 3 -> ETAGE2 ..."""
    if index <= 0:
        return "FONDATION"
    if index == 1:
        return "RDC"
    return f"ETAGE{index - 1}"


def _transform_local_point(
    matrix: np.ndarray,
    x_local: float,
    y_local: float,
    unit_scale: float,
) -> list[float]:
    """Transforme un point local (unites fichier) en coordonnees monde (m)."""
    world = matrix @ np.array([x_local, y_local, 0.0, 1.0])
    return _round_point([world[0] * unit_scale, world[1] * unit_scale])


def _placement_matrix(product: Any) -> np.ndarray | None:
    placement = getattr(product, "ObjectPlacement", None)
    if placement is None:
        return None
    try:
        return ifc_placement.get_local_placement(placement)
    except Exception:
        return None


def _iter_swept_profiles(representation: Any) -> list[Any]:
    """Retourne les profils (SweptArea) des solides extrudes d'une representation."""
    profiles: list[Any] = []

    def walk(items: Any) -> None:
        for item in items or []:
            cls = item.is_a()
            if cls in {"IfcExtrudedAreaSolid", "IfcExtrudedAreaSolidTapered"}:
                profiles.append(item.SweptArea)
            elif cls == "IfcMappedItem":
                source = item.MappingSource
                if source is not None:
                    walk(source.MappedRepresentation.Items)
            elif cls == "IfcBooleanResult" or cls == "IfcBooleanClippingResult":
                walk([item.FirstOperand])

    if representation is not None:
        walk(representation.Items)
    return profiles


def _column_plan_polygon(
    column: Any,
    matrix: np.ndarray,
    unit_scale: float,
    warnings: list[dict[str, str]],
) -> tuple[list[list[float]], str]:
    """
    Retourne le polygone en plan (4 coins, m) de la section du poteau et la forme.
    Utilise le profil si disponible, sinon une section carree par defaut.
    """
    representation = ifc_representation.get_representation(column, "Model", "Body")
    if representation is None and column.Representation is not None:
        reps = column.Representation.Representations
        representation = reps[0] if reps else None

    profiles = _iter_swept_profiles(representation)

    for profile in profiles:
        cls = profile.is_a()
        if cls == "IfcRectangleProfileDef" and profile.XDim and profile.YDim:
            hx = float(profile.XDim) / 2.0
            hy = float(profile.YDim) / 2.0
            corners_local = [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]
            points = [
                _transform_local_point(matrix, cx, cy, unit_scale)
                for cx, cy in corners_local
            ]
            return points, "RECTANGLE"
        if cls == "IfcCircleProfileDef" and profile.Radius:
            r = float(profile.Radius)
            corners_local = [(-r, -r), (r, -r), (r, r), (-r, r)]
            points = [
                _transform_local_point(matrix, cx, cy, unit_scale)
                for cx, cy in corners_local
            ]
            return points, "CIRCLE"

    # Section par defaut centree sur le placement
    warnings.append({
        "code": "COLUMN_DEFAULT_SECTION",
        "message": (
            f"Poteau {column.Name or column.GlobalId} sans profil exploitable. "
            f"Section supposee {DEFAULT_COLUMN_SIDE_M*100:.0f}x{DEFAULT_COLUMN_SIDE_M*100:.0f} cm."
        ),
    })
    h = DEFAULT_COLUMN_SIDE_M / 2.0
    corners_local = [(-h, -h), (h, -h), (h, h), (-h, h)]
    points = [
        _transform_local_point(matrix, cx, cy, unit_scale)
        for cx, cy in corners_local
    ]
    return points, "RECTANGLE_DEFAULT"


def _wall_axis_segments(
    wall: Any,
    matrix: np.ndarray,
    unit_scale: float,
) -> list[list[list[float]]]:
    """Retourne la liste des segments [p1, p2] (m) de l'axe du voile."""
    representation = ifc_representation.get_representation(wall, "Model", "Axis")
    segments: list[list[list[float]]] = []

    if representation is not None:
        for item in representation.Items:
            if item.is_a("IfcPolyline"):
                pts = [
                    _transform_local_point(matrix, pt.Coordinates[0], pt.Coordinates[1], unit_scale)
                    for pt in item.Points
                ]
                for i in range(len(pts) - 1):
                    segments.append([pts[i], pts[i + 1]])
            elif item.is_a("IfcTrimmedCurve") and item.BasisCurve.is_a("IfcLine"):
                # Approche simple : ignore (peu courant pour un axe de voile)
                continue

    return segments


def _make_level(name: str, z_top_m: float | None) -> dict[str, Any]:
    return {
        "name": name,
        "origin_raw": [0.0, 0.0],
        "z_top_m": z_top_m,
        "footprints": [],
        "columns": [],
        "walls": [],
        "wall_axes": [],
        "voids": [],
        "load_zones": [],
        "load_zone_labels": [],
        "slab_directions": [],
        "stairs": [],
        "layers": [],
    }


def _cluster_id(cx: float, cy: float, clusters: list[tuple[float, float]], tol: float) -> int:
    """Retourne l'index de pile (cluster) pour un poteau, en creant un cluster au besoin."""
    for index, (ccx, ccy) in enumerate(clusters):
        if abs(cx - ccx) <= tol and abs(cy - ccy) <= tol:
            return index
    clusters.append((cx, cy))
    return len(clusters) - 1


def read_ifc_model(
    ifc_path: str | Path,
    emprise_margin_m: float = 0.50,
    column_cluster_tol_m: float = 0.50,
) -> dict[str, Any]:
    """
    Lit un fichier IFC et produit un `model` compatible avec read_dxf_model.
    """
    ifc_path = Path(ifc_path)
    ifc_file = ifcopenshell.open(str(ifc_path))

    unit_scale = float(ifc_unit.calculate_unit_scale(ifc_file))

    warnings: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []

    # --- 1) Niveaux (storeys) tries par altitude ---
    storeys = list(ifc_file.by_type("IfcBuildingStorey"))

    def _storey_elevation(storey: Any) -> float:
        if storey.Elevation is not None:
            return float(storey.Elevation) * unit_scale
        matrix = _placement_matrix(storey)
        if matrix is not None:
            return float(matrix[2, 3]) * unit_scale
        return 0.0

    storeys.sort(key=_storey_elevation)

    if not storeys:
        # Pas de storey : un niveau FONDATION unique
        warnings.append({
            "code": "NO_STOREY",
            "message": "Aucun IfcBuildingStorey trouve. Niveau FONDATION unique cree.",
        })
        storeys = []

    levels: dict[str, dict[str, Any]] = {}
    storey_to_level: dict[int, str] = {}

    if storeys:
        for index, storey in enumerate(storeys):
            level_name = normalize_level_name(index)
            z_top = round(_storey_elevation(storey), 4)
            levels[level_name] = _make_level(level_name, z_top)
            storey_to_level[storey.id()] = level_name
    else:
        levels["FONDATION"] = _make_level("FONDATION", 0.0)

    fondation_name = "FONDATION"

    # --- 2) Poteaux ---
    columns = list(ifc_file.by_type("IfcColumn"))
    clusters: list[tuple[float, float]] = []
    # cluster -> {"section_points", "shape"} (premiere occurrence retenue pour la base)
    cluster_section: dict[int, dict[str, Any]] = {}
    # (level_name, cluster_index) deja place
    placed: set[tuple[str, int]] = set()

    for column in columns:
        matrix = _placement_matrix(column)
        if matrix is None:
            errors.append({
                "code": "COLUMN_NO_PLACEMENT",
                "message": f"Poteau {column.Name or column.GlobalId} sans placement, ignore.",
            })
            continue

        points, shape = _column_plan_polygon(column, matrix, unit_scale, warnings)
        bbox = bbox_from_points(points)
        cx = round((bbox["xmin"] + bbox["xmax"]) / 2.0, 4)
        cy = round((bbox["ymin"] + bbox["ymax"]) / 2.0, 4)

        cluster_index = _cluster_id(cx, cy, clusters, column_cluster_tol_m)
        if cluster_index not in cluster_section:
            cluster_section[cluster_index] = {"points": points, "bbox": bbox, "shape": shape}

        container = ifc_element.get_container(column)
        level_name = storey_to_level.get(container.id()) if container is not None else None
        if level_name is None:
            level_name = fondation_name

        key = (level_name, cluster_index)
        if key in placed:
            continue
        placed.add(key)

        levels.setdefault(level_name, _make_level(level_name, None))
        levels[level_name]["columns"].append({
            "id": f"P{cluster_index + 1:02d}",
            "shape": shape,
            "cx": cx,
            "cy": cy,
            "bx": bbox["width"],
            "by": bbox["height"],
            "area_m2": round(bbox["width"] * bbox["height"], 4),
            "points": points,
            "source_layer": "IFC-IFCCOLUMN",
        })

    # --- 2bis) Base des piles sur le niveau FONDATION ---
    levels.setdefault(fondation_name, _make_level(fondation_name, 0.0))
    fond_columns_by_id = {c["id"] for c in levels[fondation_name]["columns"]}

    for cluster_index, (ccx, ccy) in enumerate(clusters):
        col_id = f"P{cluster_index + 1:02d}"
        if col_id in fond_columns_by_id:
            continue
        section = cluster_section.get(cluster_index, {})
        points = section.get("points")
        bbox = section.get("bbox")
        if points is None or bbox is None:
            h = DEFAULT_COLUMN_SIDE_M / 2.0
            points = [
                [round(ccx - h, 4), round(ccy - h, 4)],
                [round(ccx + h, 4), round(ccy - h, 4)],
                [round(ccx + h, 4), round(ccy + h, 4)],
                [round(ccx - h, 4), round(ccy + h, 4)],
            ]
            bbox = bbox_from_points(points)
        levels[fondation_name]["columns"].append({
            "id": col_id,
            "shape": section.get("shape", "RECTANGLE_DEFAULT"),
            "cx": ccx,
            "cy": ccy,
            "bx": bbox["width"],
            "by": bbox["height"],
            "area_m2": round(bbox["width"] * bbox["height"], 4),
            "points": points,
            "source_layer": "IFC-IFCCOLUMN-BASE",
        })

    # --- 3) Voiles (IfcWall / IfcWallStandardCase) -> axes sur FONDATION ---
    walls = list(ifc_file.by_type("IfcWall"))
    wall_counter = 0
    for wall in walls:
        matrix = _placement_matrix(wall)
        if matrix is None:
            continue
        segments = _wall_axis_segments(wall, matrix, unit_scale)
        for p_start, p_end in segments:
            seg_len = ((p_end[0] - p_start[0]) ** 2 + (p_end[1] - p_start[1]) ** 2) ** 0.5
            if seg_len < 1e-6:
                continue
            wall_counter += 1
            levels[fondation_name]["wall_axes"].append({
                "id": f"V{wall_counter:02d}",
                "x1": round(p_start[0], 4),
                "y1": round(p_start[1], 4),
                "x2": round(p_end[0], 4),
                "y2": round(p_end[1], 4),
                "length_m": round(seg_len, 4),
                "points": [p_start, p_end],
                "source_layer": "IFC-IFCWALL-AXE",
            })

    # --- 4) Emprise : rectangle englobant + marge, duplique sur chaque niveau ---
    all_points: list[list[float]] = []
    for level in levels.values():
        for col in level["columns"]:
            all_points.extend(col.get("points", [[col["cx"], col["cy"]]]))
        for axis in level["wall_axes"]:
            all_points.extend(axis["points"])

    if all_points:
        bbox = bbox_from_points(all_points)
        x0 = round(bbox["xmin"] - emprise_margin_m, 4)
        y0 = round(bbox["ymin"] - emprise_margin_m, 4)
        x1 = round(bbox["xmax"] + emprise_margin_m, 4)
        y1 = round(bbox["ymax"] + emprise_margin_m, 4)
        emprise_points = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
        emprise_bbox = bbox_from_points(emprise_points)
        emprise_area = polygon_area(emprise_points)
        for level in levels.values():
            level["footprints"].append({
                "layer": f"{level['name']}-EMPRISE",
                "points": [p[:] for p in emprise_points],
                "closed": True,
                "area_m2": emprise_area,
                "bbox": dict(emprise_bbox),
            })
    else:
        errors.append({
            "code": "NO_GEOMETRY",
            "message": "Aucun poteau ni voile exploitable dans l'IFC : emprise indeterminee.",
        })

    # --- 5) Controles finaux ---
    if not columns:
        warnings.append({
            "code": "NO_COLUMN",
            "message": "Aucun IfcColumn trouve dans le fichier IFC.",
        })

    clean_levels = [levels[name] for name in sorted(levels.keys())]

    model = {
        "schema_version": "0.3",
        "source_file": str(ifc_path),
        "source_format": "IFC",
        "units": "m",
        "ifc_unit_scale_to_m": unit_scale,
        "superposition_rule": "world_coordinates (IFC placements, converties en metres)",
        "layers_detected": ["IFC-IFCCOLUMN", "IFC-IFCWALL"],
        "levels_detected": sorted(list(levels.keys())),
        "levels": clean_levels,
        "global_layers": {
            "limite_propriete": [],
            "ss_rampe": [],
            "joint_dilatation": [],
        },
        "validation": {
            "status": "OK" if not errors else "ERROR",
            "warnings": warnings,
            "errors": errors,
            "summary": {
                "levels_count": len(levels),
                "columns_count": len(columns),
                "walls_count": len(walls),
                "warnings_count": len(warnings),
                "errors_count": len(errors),
            },
        },
    }

    return model


def read_ifc_summary(ifc_path: str | Path) -> dict[str, Any]:
    """Resume simple pour /validate-ifc."""
    model = read_ifc_model(ifc_path)

    levels_summary = []
    for level in model["levels"]:
        levels_summary.append({
            "level": level["name"],
            "z_top_m": level["z_top_m"],
            "emprises_count": len(level["footprints"]),
            "poteaux_count": len(level["columns"]),
            "voiles_count": len(level["wall_axes"]),
        })

    return {
        "status": model["validation"]["status"],
        "file": model["source_file"],
        "source_format": "IFC",
        "ifc_unit_scale_to_m": model["ifc_unit_scale_to_m"],
        "levels_detected": model["levels_detected"],
        "levels": levels_summary,
        "warnings": model["validation"]["warnings"],
        "errors": model["validation"]["errors"],
        "summary": model["validation"]["summary"],
    }
