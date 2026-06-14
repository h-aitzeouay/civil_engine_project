"""
Resolution des chevauchements entre semelles filantes peripheriques (sous voiles)
et semelles isolees peripheriques (sous poteaux).

Reutilise Rect et WallInput du module strip_footing_under_wall.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Iterable, Literal
import math

from civil_engine.foundations.strip_footing_under_wall import Rect

EPS = 1.0e-9


def round_up(value: float, step: float = 0.05) -> float:
    if step <= 0:
        return value
    return math.ceil((value - EPS) / step) * step


def clamp(value: float, vmin: float, vmax: float) -> float:
    return max(vmin, min(vmax, value))


def rect_union(a: Rect, b: Rect) -> Rect:
    return Rect(min(a.xmin, b.xmin), min(a.ymin, b.ymin),
               max(a.xmax, b.xmax), max(a.ymax, b.ymax)).normalized()


def distance_point_to_segment(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    l2 = vx * vx + vy * vy
    if l2 <= EPS:
        return math.hypot(px - ax, py - ay), 0.0
    t = (wx * vx + wy * vy) / l2
    tc = clamp(t, 0.0, 1.0)
    return math.hypot(px - (ax + tc * vx), py - (ay + tc * vy)), tc


def _contains_point(r: Rect, x, y, tol=1e-6):
    return r.xmin - tol <= x <= r.xmax + tol and r.ymin - tol <= y <= r.ymax + tol


@dataclass
class ColumnInput:
    id: str
    x: float
    y: float
    bx_m: float
    by_m: float
    n_sls_kN: float
    n_uls_kN: float | None = None
    is_peripheral: bool = False

    def n_uls(self) -> float:
        return self.n_uls_kN if self.n_uls_kN is not None else 1.35 * self.n_sls_kN


@dataclass
class WallRef:
    id: str
    x1: float
    y1: float
    x2: float
    y2: float
    thickness_m: float
    n_sls_kN_per_m: float
    is_peripheral: bool = True

    def axis(self):
        dx, dy = abs(self.x2 - self.x1), abs(self.y2 - self.y1)
        if dx < 1e-6 and dy < 1e-6:
            raise ValueError(f"Voile {self.id}: longueur nulle.")
        if dx > 10.0 * max(dy, EPS):
            return "H"
        if dy > 10.0 * max(dx, EPS):
            return "V"
        return "DIAGONAL"


@dataclass
class IsolatedFootingInput:
    id: str
    column_id: str
    bbox: Rect
    H_m: float
    q_sls_kPa: float | None = None
    status: str = "ACTIVE"


@dataclass
class StripFootingInput:
    id: str
    wall_id: str
    bbox: Rect
    H_m: float
    B_m: float
    q_sls_kPa: float | None = None
    status: str = "ACTIVE"


def column_belongs_to_wall(column, wall, tolerance_m=0.15, influence_extension_m=0.30):
    dist, t = distance_point_to_segment(column.x, column.y, wall.x1, wall.y1, wall.x2, wall.y2)
    allowed = wall.thickness_m / 2.0 + tolerance_m
    inside = -influence_extension_m <= t <= 1.0 + influence_extension_m
    belongs = dist <= allowed and inside
    return {"belongs": belongs, "distance_to_wall_axis_m": round(dist, 3),
            "projection_parameter": round(t, 3), "allowed_distance_m": round(allowed, 3),
            "message": "Poteau integre au voile." if belongs else "Poteau independant du voile."}


def estimate_strip_q_with_column(strip, wall, column, tributary_length_m, gamma=25.0):
    B = max(strip.B_m, EPS)
    Ltrib = max(tributary_length_m, 0.50)
    return wall.n_sls_kN_per_m / B + column.n_sls_kN / (B * Ltrib) + gamma * strip.H_m


def estimate_isolated_q(footing, column, gamma=25.0):
    return column.n_sls_kN / max(footing.bbox.area, EPS) + gamma * footing.H_m


def estimate_massif_q(massif_bbox, H_m, wall, column, strip_direction, gamma=25.0):
    area = max(massif_bbox.area, EPS)
    if strip_direction == "H":
        wl = massif_bbox.width
    elif strip_direction == "V":
        wl = massif_bbox.height
    else:
        wl = min(massif_bbox.width, massif_bbox.height)
    n_total = wall.n_sls_kN_per_m * max(wl, 0.50) + column.n_sls_kN
    return n_total / area + gamma * H_m


def create_local_massif(massif_id, strip, isolated, column, wall, emprise,
                        min_margin_m=0.20, min_side_m=1.00):
    issues = []
    base = rect_union(strip.bbox, isolated.bbox).expanded(min_margin_m)
    if base.width < min_side_m:
        d = (min_side_m - base.width) / 2.0
        base = Rect(base.xmin - d, base.ymin, base.xmax + d, base.ymax)
    if base.height < min_side_m:
        d = (min_side_m - base.height) / 2.0
        base = Rect(base.xmin, base.ymin - d, base.xmax, base.ymax + d)
    clipped = base.clipped_inside(emprise)
    if not emprise.contains_rect(clipped):
        issues.append({"severity": "ERROR", "code": "MASSIF_OUTSIDE_EMPRISE",
                       "message": "Massif local deborde de l'emprise.", "bbox": clipped.to_dict()})
    if not _contains_point(clipped, column.x, column.y):
        issues.append({"severity": "ERROR", "code": "COLUMN_NOT_COVERED_BY_MASSIF",
                       "message": "Poteau non couvert par le massif.", "column_id": column.id})
    if not clipped.intersects(strip.bbox):
        issues.append({"severity": "ERROR", "code": "MASSIF_NOT_CONNECTED_TO_STRIP",
                       "message": "Massif non connecte a la filante."})
    if any(i["severity"] == "ERROR" for i in issues):
        return None, issues
    H = max(strip.H_m, isolated.H_m)
    massif = {"id": massif_id, "layer": "MASSIF", "type": "MASSIF_LOCAL_POTEAU_VOILE",
              "bbox": clipped.to_dict(), "H_m": round_up(H, 0.05),
              "related_column_id": column.id, "related_wall_id": wall.id,
              "related_footings": [strip.id, isolated.id],
              "message": "Massif local combine poteau-voile."}
    return massif, issues


def resolve_one(index, strip, isolated, wall, column, emprise, q_allowable_kPa,
                gamma=25.0, wall_col_tol=0.15, overlap_tol=0.01, trib_len=1.50):
    issues = []
    emprise = emprise.normalized()
    sb = strip.bbox.normalized()
    ib = isolated.bbox.normalized()

    base = {"id": f"INT_{index:03d}", "strip_id": strip.id, "isolated_id": isolated.id,
            "wall_id": wall.id, "column_id": column.id, "q_allowable_kPa": q_allowable_kPa}

    q_iso = estimate_isolated_q(isolated, column, gamma)

    if not sb.intersects(ib):
        return {**base, "status": "OK", "resolution_type": "KEEP_BOTH_NO_INTERFERENCE",
                "message": "Aucune interference. On garde les deux.",
                "keep_strip": True, "keep_isolated": True, "create_massif": False,
                "massif": None, "q_isolated_sls_kPa": round(q_iso, 2), "issues": []}

    inter = sb.intersection(ib)
    overlap = inter.area if inter else 0.0
    if overlap <= overlap_tol:
        return {**base, "status": "OK_WITH_NOTE", "resolution_type": "KEEP_BOTH_NO_INTERFERENCE",
                "message": "Contact mineur. Garder les deux avec detail d'arret.",
                "keep_strip": True, "keep_isolated": True, "create_massif": False,
                "massif": None, "q_isolated_sls_kPa": round(q_iso, 2), "issues": []}

    belongs = column_belongs_to_wall(column, wall, wall_col_tol)
    col_in_wall = bool(belongs["belongs"])
    issues.append({"severity": "INFO", "code": "COLUMN_WALL_RELATION", "message": belongs["message"], "data": belongs})

    if col_in_wall:
        q_strip = estimate_strip_q_with_column(strip, wall, column, trib_len, gamma)
        if q_strip <= q_allowable_kPa + EPS:
            return {**base, "status": "OK", "resolution_type": "KEEP_STRIP_ABSORB_COLUMN",
                    "message": "Poteau dans le voile, absorbe par la filante. Semelle isolee supprimee.",
                    "keep_strip": True, "keep_isolated": False, "create_massif": False,
                    "massif": None, "q_strip_sls_kPa": round(q_strip, 2),
                    "q_isolated_sls_kPa": round(q_iso, 2),
                    "column_considered_part_of_wall": True, "issues": issues}
        massif, mi = create_local_massif(f"MSF_INT_{index:03d}", strip, isolated, column, wall, emprise)
        issues.extend(mi)
        if massif is not None:
            q_m = estimate_massif_q(Rect(**massif["bbox"]), massif["H_m"], wall, column, wall.axis(), gamma)
            if q_m <= q_allowable_kPa + EPS:
                return {**base, "status": "OK", "resolution_type": "MERGE_LOCAL_COMBINED_FOOTING",
                        "message": "Massif local combine poteau-voile, dans l'emprise.",
                        "keep_strip": True, "keep_isolated": False, "create_massif": True,
                        "massif": massif, "q_massif_sls_kPa": round(q_m, 2),
                        "q_isolated_sls_kPa": round(q_iso, 2),
                        "column_considered_part_of_wall": True, "issues": issues}
        return {**base, "status": "NOT_OK", "resolution_type": "LOCAL_RAFT_REQUIRED",
                "message": "Ni filante ni massif suffisants. Prevoir radier local.",
                "keep_strip": False, "keep_isolated": False, "create_massif": False,
                "create_local_raft": True, "massif": None,
                "q_isolated_sls_kPa": round(q_iso, 2),
                "column_considered_part_of_wall": True, "issues": issues}

    # Poteau independant
    massif, mi = create_local_massif(f"MSF_INT_{index:03d}", strip, isolated, column, wall, emprise)
    issues.extend(mi)
    if massif is not None:
        q_m = estimate_massif_q(Rect(**massif["bbox"]), massif["H_m"], wall, column, wall.axis(), gamma)
        if q_m <= q_allowable_kPa + EPS:
            return {**base, "status": "OK_WITH_WARNINGS", "resolution_type": "MERGE_LOCAL_COMBINED_FOOTING",
                    "message": "Poteau independant : massif local combine propose.",
                    "keep_strip": True, "keep_isolated": False, "create_massif": True,
                    "massif": massif, "q_massif_sls_kPa": round(q_m, 2),
                    "q_isolated_sls_kPa": round(q_iso, 2),
                    "column_considered_part_of_wall": False, "issues": issues}
    return {**base, "status": "NOT_OK", "resolution_type": "LOCAL_RAFT_REQUIRED",
            "message": "Interference non resolue. Prevoir radier local.",
            "keep_strip": False, "keep_isolated": False, "create_massif": False,
            "create_local_raft": True, "massif": None,
            "q_isolated_sls_kPa": round(q_iso, 2),
            "column_considered_part_of_wall": False, "issues": issues}


def resolve_peripheral_strip_isolated_interferences(
    emprise, walls, columns, strip_footings, isolated_footings,
    q_allowable_kPa, gamma_concrete_kN_m3=25.0, wall_column_tolerance_m=0.15,
    tributary_length_for_column_m=1.50):
    walls_list = list(walls)
    columns_list = list(columns)
    strips = list(strip_footings)
    isolateds = list(isolated_footings)
    issues = []
    resolutions = []
    idx = 1

    wall_by_id = {w.id: w for w in walls_list}
    col_by_id = {c.id: c for c in columns_list}

    for strip in strips:
        wall = wall_by_id.get(strip.wall_id)
        if wall is None:
            issues.append({"severity": "ERROR", "code": "WALL_NOT_FOUND",
                           "strip_id": strip.id, "message": "Voile introuvable."})
            continue
        if not wall.is_peripheral:
            continue
        for isolated in isolateds:
            column = col_by_id.get(isolated.column_id)
            if column is None:
                continue
            if not column.is_peripheral:
                continue
            if not strip.bbox.intersects(isolated.bbox):
                continue
            res = resolve_one(idx, strip, isolated, wall, column, emprise,
                              q_allowable_kPa, gamma_concrete_kN_m3,
                              wall_column_tolerance_m, 0.01, tributary_length_for_column_m)
            resolutions.append(res)
            idx += 1

    for r in resolutions:
        issues.extend(r.get("issues", []))

    errors = sum(1 for i in issues if i.get("severity") == "ERROR")
    warnings = sum(1 for i in issues if i.get("severity") == "WARNING")
    status = "OK" if errors == 0 else "NOT_OK"

    isolated_to_remove = sorted({r["isolated_id"] for r in resolutions if not r.get("keep_isolated", True)})
    local_massifs = [r["massif"] for r in resolutions if r.get("massif")]
    local_rafts = [{"resolution_id": r["id"], "strip_id": r["strip_id"], "isolated_id": r["isolated_id"],
                    "message": r["message"]} for r in resolutions if r.get("create_local_raft")]

    return {
        "status": status, "method": "peripheral_strip_isolated_interference_v1",
        "summary": {"interferences_count": len(resolutions), "massifs_count": len(local_massifs),
                    "local_raft_required_count": len(local_rafts),
                    "isolated_removed_count": len(isolated_to_remove),
                    "errors_count": errors, "warnings_count": warnings},
        "final_decisions": {
            "isolated_footings_to_remove": isolated_to_remove,
            "local_massifs": local_massifs,
            "local_rafts_required": local_rafts,
        },
        "resolutions": resolutions,
        "issues": issues,
    }
