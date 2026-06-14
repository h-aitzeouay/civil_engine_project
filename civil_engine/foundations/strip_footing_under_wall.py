from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Iterable
import math

EPS = 1.0e-9


def round_up(value: float, step: float = 0.05) -> float:
    if step <= 0:
        return value
    return math.ceil((value - EPS) / step) * step


def round_down(value: float, step: float = 0.01) -> float:
    if step <= 0:
        return value
    return math.floor((value + EPS) / step) * step


def clamp(value: float, vmin: float, vmax: float) -> float:
    return max(vmin, min(vmax, value))


def area_phi_mm2(phi_mm: float) -> float:
    return math.pi * phi_mm * phi_mm / 4.0


def fctm_ec2_approx_mpa(fck_mpa: float) -> float:
    return 0.30 * (fck_mpa ** (2.0 / 3.0))


@dataclass
class Rect:
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    def normalized(self) -> "Rect":
        return Rect(min(self.xmin, self.xmax), min(self.ymin, self.ymax),
                    max(self.xmin, self.xmax), max(self.ymin, self.ymax))

    @property
    def width(self) -> float:
        return max(0.0, self.xmax - self.xmin)

    @property
    def height(self) -> float:
        return max(0.0, self.ymax - self.ymin)

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def cx(self) -> float:
        return 0.5 * (self.xmin + self.xmax)

    @property
    def cy(self) -> float:
        return 0.5 * (self.ymin + self.ymax)

    def contains_rect(self, other: "Rect", tol: float = 1.0e-6) -> bool:
        return (other.xmin >= self.xmin - tol and other.xmax <= self.xmax + tol
                and other.ymin >= self.ymin - tol and other.ymax <= self.ymax + tol)

    def intersects(self, other: "Rect", tol: float = 1.0e-6) -> bool:
        return not (self.xmax <= other.xmin + tol or self.xmin >= other.xmax - tol
                    or self.ymax <= other.ymin + tol or self.ymin >= other.ymax - tol)

    def intersection(self, other: "Rect") -> "Rect | None":
        if not self.intersects(other):
            return None
        return Rect(max(self.xmin, other.xmin), max(self.ymin, other.ymin),
                    min(self.xmax, other.xmax), min(self.ymax, other.ymax))

    def expanded(self, margin: float) -> "Rect":
        return Rect(self.xmin - margin, self.ymin - margin,
                    self.xmax + margin, self.ymax + margin)

    def clipped_inside(self, emprise: "Rect") -> "Rect":
        return Rect(clamp(self.xmin, emprise.xmin, emprise.xmax),
                    clamp(self.ymin, emprise.ymin, emprise.ymax),
                    clamp(self.xmax, emprise.xmin, emprise.xmax),
                    clamp(self.ymax, emprise.ymin, emprise.ymax)).normalized()

    def shifted(self, dx: float, dy: float) -> "Rect":
        return Rect(self.xmin + dx, self.ymin + dy, self.xmax + dx, self.ymax + dy)

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass
class WallInput:
    id: str
    x1: float
    y1: float
    x2: float
    y2: float
    thickness_m: float
    n_sls_kN_per_m: float
    n_uls_kN_per_m: float | None = None

    def axis(self) -> str:
        dx = abs(self.x2 - self.x1)
        dy = abs(self.y2 - self.y1)
        if dx < 1.0e-6 and dy < 1.0e-6:
            raise ValueError(f"Voile {self.id}: longueur nulle.")
        return "H" if dx >= dy else "V"

    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    def wall_bbox(self) -> Rect:
        axis = self.axis()
        t2 = 0.5 * self.thickness_m
        if axis == "H":
            y = 0.5 * (self.y1 + self.y2)
            return Rect(min(self.x1, self.x2), y - t2, max(self.x1, self.x2), y + t2)
        x = 0.5 * (self.x1 + self.x2)
        return Rect(x - t2, min(self.y1, self.y2), x + t2, max(self.y1, self.y2))

    def n_uls(self) -> float:
        if self.n_uls_kN_per_m is not None:
            return self.n_uls_kN_per_m
        return 1.35 * self.n_sls_kN_per_m


@dataclass
class ReinforcementResult:
    main_bottom: str
    distribution_bottom: str
    top_constructive: str
    as_req_mm2_per_m: float
    as_min_mm2_per_m: float
    as_used_mm2_per_m: float
    main_phi_mm: float
    main_spacing_m: float


@dataclass
class StripFootingResult:
    id: str
    wall_id: str
    type: str
    axis: str
    status: str
    message: str
    A_m: float
    B_m: float
    H_m: float
    bbox: Rect
    wall_bbox: Rect
    q_sls_kPa: float
    q_allowable_kPa: float
    eccentricity_m: float
    side_mode: str
    reinforcement: ReinforcementResult
    issues: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["bbox"] = self.bbox.to_dict()
        data["wall_bbox"] = self.wall_bbox.to_dict()
        return data


def estimate_h_preliminary(B_m, wall_thickness_m, h_min_m=0.30, cover_m=0.05):
    cantilever = max(0.0, 0.5 * (B_m - wall_thickness_m))
    h = max(h_min_m, cover_m + 0.20 + cantilever / 3.0)
    return round_up(h, 0.05)


def compute_required_width_iterative(n_sls_kN_per_m, q_allowable_kPa, wall_thickness_m,
                                     gamma_concrete_kN_m3=25.0, B_min_m=0.60, h_min_m=0.30):
    if q_allowable_kPa <= 0:
        raise ValueError("q_allowable_kPa doit etre positif.")
    if n_sls_kN_per_m <= 0:
        raise ValueError("n_sls_kN_per_m doit etre positif.")

    B = max(B_min_m, n_sls_kN_per_m / max(q_allowable_kPa - 25.0 * h_min_m, 1.0))
    for _ in range(8):
        H = estimate_h_preliminary(B, wall_thickness_m, h_min_m=h_min_m)
        denom = q_allowable_kPa - gamma_concrete_kN_m3 * H
        if denom <= 0:
            # CORRECTION : repli coherent, on garde la deduction du poids propre
            denom_min = max(q_allowable_kPa - gamma_concrete_kN_m3 * h_min_m, 1.0)
            B = max(B_min_m, n_sls_kN_per_m / denom_min)
            H = estimate_h_preliminary(B, wall_thickness_m, h_min_m=h_min_m)
            q_sls = n_sls_kN_per_m / B + gamma_concrete_kN_m3 * H
            return round_up(B, 0.05), H, q_sls
        B_new = max(B_min_m, n_sls_kN_per_m / denom)
        B = round_up(B_new, 0.05)
    H = estimate_h_preliminary(B, wall_thickness_m, h_min_m=h_min_m)
    q_sls = n_sls_kN_per_m / B + gamma_concrete_kN_m3 * H
    return B, H, q_sls


def build_footing_bbox_inside_emprise(wall, B_m, emprise, end_extension_m):
    issues = []
    axis = wall.axis()
    wb = wall.wall_bbox()

    if not emprise.contains_rect(wb):
        issues.append({"severity": "ERROR", "code": "WALL_OUTSIDE_EMPRISE", "wall_id": wall.id,
                       "message": "Le voile lui-meme n'est pas entierement dans l'emprise."})

    if axis == "H":
        x0 = max(wb.xmin - end_extension_m, emprise.xmin)
        x1 = min(wb.xmax + end_extension_m, emprise.xmax)
        y_center = wb.cy
        rect = Rect(x0, y_center - B_m / 2.0, x1, y_center + B_m / 2.0)
        if rect.ymin < emprise.ymin:
            rect = rect.shifted(0.0, emprise.ymin - rect.ymin)
        if rect.ymax > emprise.ymax:
            rect = rect.shifted(0.0, emprise.ymax - rect.ymax)
        if rect.ymin < emprise.ymin - EPS or rect.ymax > emprise.ymax + EPS:
            issues.append({"severity": "ERROR", "code": "WIDTH_NOT_FITTING_EMPRISE", "wall_id": wall.id,
                           "message": "La largeur requise de semelle ne peut pas entrer dans l'emprise."})
            rect = rect.clipped_inside(emprise)
        eccentricity = abs(wb.cy - rect.cy)
        if eccentricity <= 0.02:
            side_mode = "CENTERED"
        elif rect.cy > wb.cy:
            side_mode = "SHIFTED_INSIDE_POSITIVE_Y"
        else:
            side_mode = "SHIFTED_INSIDE_NEGATIVE_Y"
    else:
        y0 = max(wb.ymin - end_extension_m, emprise.ymin)
        y1 = min(wb.ymax + end_extension_m, emprise.ymax)
        x_center = wb.cx
        rect = Rect(x_center - B_m / 2.0, y0, x_center + B_m / 2.0, y1)
        if rect.xmin < emprise.xmin:
            rect = rect.shifted(emprise.xmin - rect.xmin, 0.0)
        if rect.xmax > emprise.xmax:
            rect = rect.shifted(emprise.xmax - rect.xmax, 0.0)
        if rect.xmin < emprise.xmin - EPS or rect.xmax > emprise.xmax + EPS:
            issues.append({"severity": "ERROR", "code": "WIDTH_NOT_FITTING_EMPRISE", "wall_id": wall.id,
                           "message": "La largeur requise de semelle ne peut pas entrer dans l'emprise."})
            rect = rect.clipped_inside(emprise)
        eccentricity = abs(wb.cx - rect.cx)
        if eccentricity <= 0.02:
            side_mode = "CENTERED"
        elif rect.cx > wb.cx:
            side_mode = "SHIFTED_INSIDE_POSITIVE_X"
        else:
            side_mode = "SHIFTED_INSIDE_NEGATIVE_X"

    if not emprise.contains_rect(rect):
        issues.append({"severity": "ERROR", "code": "FOOTING_OUTSIDE_EMPRISE", "wall_id": wall.id,
                       "message": "La semelle deborde de l'emprise. Solution refusee.", "bbox": rect.to_dict()})
    if not rect.contains_rect(wb):
        issues.append({"severity": "ERROR", "code": "WALL_NOT_COVERED_BY_FOOTING", "wall_id": wall.id,
                       "message": "Le voile n'est pas entierement couvert par la semelle.",
                       "wall_bbox": wb.to_dict(), "footing_bbox": rect.to_dict()})
    return rect, side_mode, eccentricity, issues


def design_reinforcement_preliminary(wall, footing_bbox, B_m, H_m, q_sls_kPa,
                                     fck_mpa=25.0, fyk_mpa=500.0, gamma_s=1.15, cover_m=0.05,
                                     phi_main_mm=12.0, phi_distribution_mm=10.0, max_spacing_m=0.20):
    axis = wall.axis()
    wb = wall.wall_bbox()
    q_uls = wall.n_uls() / max(B_m, 1.0e-6) + 1.35 * 25.0 * H_m
    if axis == "H":
        a1 = max(0.0, wb.ymin - footing_bbox.ymin)
        a2 = max(0.0, footing_bbox.ymax - wb.ymax)
    else:
        a1 = max(0.0, wb.xmin - footing_bbox.xmin)
        a2 = max(0.0, footing_bbox.xmax - wb.xmax)
    a = max(a1, a2)
    M_uls = q_uls * a * a / 2.0
    d_mm = max(50.0, (H_m - cover_m - phi_main_mm / 2000.0) * 1000.0)
    z_mm = 0.90 * d_mm
    fyd = fyk_mpa / gamma_s
    as_req = (M_uls * 1.0e6) / (z_mm * fyd) if M_uls > 0 else 0.0
    fctm = fctm_ec2_approx_mpa(fck_mpa)
    as_min = max(0.26 * fctm / fyk_mpa * 1000.0 * d_mm, 0.0013 * 1000.0 * d_mm)
    as_needed = max(as_req, as_min)
    aphi = area_phi_mm2(phi_main_mm)
    spacing = min(max_spacing_m, aphi * 1000.0 / max(as_needed, 1.0) / 1000.0)
    spacing = max(0.08, round_down(spacing, 0.01))
    as_used = aphi / spacing
    return ReinforcementResult(
        main_bottom=f"Inf transversal HA{int(phi_main_mm)} / e={spacing:.2f} m",
        distribution_bottom=f"Inf longitudinal HA{int(phi_distribution_mm)} / e={max_spacing_m:.2f} m",
        top_constructive=f"Sup constructif HA{int(phi_distribution_mm)} / e={max_spacing_m:.2f} m",
        as_req_mm2_per_m=round(as_req, 1), as_min_mm2_per_m=round(as_min, 1),
        as_used_mm2_per_m=round(as_used, 1), main_phi_mm=phi_main_mm, main_spacing_m=spacing)


def detect_strip_footing_interferences(footings):
    issues = []
    for i in range(len(footings)):
        for j in range(i + 1, len(footings)):
            inter = footings[i].bbox.intersection(footings[j].bbox)
            if inter is not None and inter.area > 1.0e-4:
                issues.append({"severity": "WARNING", "code": "STRIP_FOOTING_INTERFERENCE",
                               "items": [footings[i].id, footings[j].id],
                               "message": "Intersection entre deux semelles filantes. Prevoir massif commun ou radier local.",
                               "intersection_bbox": inter.to_dict()})
    return issues


def _shared_endpoint(f1, f2, tol_m=0.30):
    """
    Detecte si deux semelles filantes partagent une extremite d'axe (angle L/U).
    Compare les extremites des axes de voile. Retourne le point commun ou None.
    """
    ends1 = [(f1.wall_bbox.cx, f1.wall_bbox.cy)]  # fallback centre
    # On utilise plutot les extremites stockees via l'axe du voile :
    e1 = getattr(f1, "_axis_ends", None)
    e2 = getattr(f2, "_axis_ends", None)
    if not e1 or not e2:
        return None
    for p1 in e1:
        for p2 in e2:
            d = ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5
            if d <= tol_m:
                return (0.5 * (p1[0] + p2[0]), 0.5 * (p1[1] + p2[1]))
    return None


def build_intersection_massifs(footings, emprise, margin_m=0.20, shared_tol_m=0.30):
    """
    Cree un massif a chaque jonction de deux filantes :
    - cas 1 : chevauchement geometrique des bbox ;
    - cas 2 : extremites d'axe communes (angle L/U) meme sans recouvrement large.
    Hauteur du massif = max des deux filantes. Le massif englobe la zone
    de jonction + une marge, et reste dans l'emprise.
    """
    massifs = []
    idx = 1
    for i in range(len(footings)):
        for j in range(i + 1, len(footings)):
            f1, f2 = footings[i], footings[j]
            inter = f1.bbox.intersection(f2.bbox)
            has_overlap = inter is not None and inter.area > 1.0e-4
            shared = _shared_endpoint(f1, f2, tol_m=shared_tol_m)

            if not has_overlap and shared is None:
                continue

            # Zone de base du massif
            if has_overlap:
                base = inter
            else:
                # angle sans recouvrement : carre autour du point commun,
                # de cote = max des deux largeurs B
                side = max(f1.B_m, f2.B_m)
                base = Rect(shared[0] - side / 2.0, shared[1] - side / 2.0,
                            shared[0] + side / 2.0, shared[1] + side / 2.0)

            H_massif = max(f1.H_m, f2.H_m)
            massif_rect = base.expanded(margin_m).clipped_inside(emprise)

            massifs.append({
                "id": f"MSF_ANGLE_{idx:02d}",
                "type": "MASSIF_ANGLE_SEMELLES_FILANTES",
                "layer": "MASSIF",
                "related_footings": [f1.id, f2.id],
                "bbox": massif_rect.to_dict(),
                "H_m": round_up(H_massif, 0.05),
                "junction_type": "OVERLAP" if has_overlap else "SHARED_CORNER",
                "message": "Massif d'angle fusionnant deux semelles filantes (hauteur = max des deux).",
            })
            idx += 1
    return massifs


def design_strip_footings_under_walls(walls, emprise, q_allowable_kPa,
                                      fck_mpa=25.0, fyk_mpa=500.0, gamma_s=1.15, cover_m=0.05,
                                      gamma_concrete_kN_m3=25.0, B_min_m=0.60, h_min_m=0.30,
                                      end_extension_min_m=0.30, phi_main_mm=12.0,
                                      phi_distribution_mm=10.0, max_spacing_m=0.20):
    emprise = emprise.normalized()
    walls = list(walls)
    footing_results = []
    global_issues = []

    for idx, wall in enumerate(walls, start=1):
        wall_issues = []
        try:
            axis = wall.axis()
            wb = wall.wall_bbox()
            B, H, q_sls = compute_required_width_iterative(
                wall.n_sls_kN_per_m, q_allowable_kPa, wall.thickness_m,
                gamma_concrete_kN_m3, B_min_m, h_min_m)
            end_extension = max(end_extension_min_m, min(0.50, 0.25 * B))
            bbox, side_mode, eccentricity, geom_issues = build_footing_bbox_inside_emprise(
                wall, B, emprise, end_extension)
            wall_issues.extend(geom_issues)
            if q_sls > q_allowable_kPa + 1.0e-6:
                wall_issues.append({"severity": "ERROR", "code": "SOIL_PRESSURE_EXCEEDED", "wall_id": wall.id,
                                    "message": "Contrainte sol ELS superieure a q admissible.",
                                    "q_sls_kPa": round(q_sls, 2), "q_allowable_kPa": q_allowable_kPa})
            reinforcement = design_reinforcement_preliminary(
                wall, bbox, B, H, q_sls, fck_mpa, fyk_mpa, gamma_s, cover_m,
                phi_main_mm, phi_distribution_mm, max_spacing_m)
            has_error = any(i["severity"] == "ERROR" for i in wall_issues)
            if has_error:
                status = "NOT_OK"
                message = "Semelle filante non acceptable seule. Prevoir redressement, semelle combinee ou radier local."
            elif side_mode == "CENTERED":
                status = "OK"
                message = "Semelle filante centree et dans l'emprise."
            else:
                status = "OK_WITH_ECCENTRICITY"
                message = "Semelle filante recalee dans l'emprise. Excentricite a verifier."
            A = bbox.width if axis == "H" else bbox.height
            result_obj = StripFootingResult(
                id=f"SFV_{idx:02d}", wall_id=wall.id, type="SEMELLE_FILANTE_SOUS_VOILE",
                axis=axis, status=status, message=message, A_m=round(A, 3), B_m=round(B, 3),
                H_m=round(H, 3), bbox=bbox, wall_bbox=wb, q_sls_kPa=round(q_sls, 2),
                q_allowable_kPa=q_allowable_kPa, eccentricity_m=round(eccentricity, 3),
                side_mode=side_mode, reinforcement=reinforcement, issues=wall_issues)
            # extremites de l'axe du voile, pour la detection des angles
            result_obj._axis_ends = [(wall.x1, wall.y1), (wall.x2, wall.y2)]
            footing_results.append(result_obj)
        except Exception as exc:
            global_issues.append({"severity": "ERROR", "code": "STRIP_FOOTING_DESIGN_FAILED",
                                  "wall_id": wall.id, "message": str(exc)})

    interference_issues = detect_strip_footing_interferences(footing_results)
    massifs = build_intersection_massifs(footing_results, emprise)
    global_issues.extend(interference_issues)
    all_issues = global_issues[:]
    for f in footing_results:
        all_issues.extend(f.issues)
    errors_count = sum(1 for i in all_issues if i.get("severity") == "ERROR")
    warnings_count = sum(1 for i in all_issues if i.get("severity") == "WARNING")
    status = "OK" if errors_count == 0 else "NOT_OK"

    return {
        "status": status, "method": "strip_footing_under_wall_v1",
        "summary": {"walls_count": len(walls), "strip_footings_count": len(footing_results),
                    "massifs_count": len(massifs), "errors_count": errors_count,
                    "warnings_count": warnings_count},
        "emprise": emprise.to_dict(),
        "strip_footings": [f.to_dict() for f in footing_results],
        "massifs": massifs, "issues": all_issues,
    }
