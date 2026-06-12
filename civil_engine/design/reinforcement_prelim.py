from __future__ import annotations

import math
from typing import Any


def get_foundation_level(model: dict[str, Any]) -> dict[str, Any] | None:
    for level in model.get("levels", []):
        if level.get("name") == "FONDATION":
            return level
    return None


def get_column_geometry(model: dict[str, Any]) -> dict[str, dict[str, float]]:
    foundation = get_foundation_level(model)

    if foundation is None:
        return {}

    columns = {}

    for column in foundation.get("columns", []):
        column_id = column["id"]

        cx = float(column.get("cx", 0.0))
        cy = float(column.get("cy", 0.0))

        points = column.get("points", [])

        if points:
            xs = [float(p[0]) for p in points]
            ys = [float(p[1]) for p in points]

            c1 = max(xs) - min(xs)
            c2 = max(ys) - min(ys)
        else:
            c1 = 0.25
            c2 = 0.25

        columns[column_id] = {
            "cx": cx,
            "cy": cy,
            "c1_m": max(c1, 0.20),
            "c2_m": max(c2, 0.20),
        }

    return columns


def build_column_load_map(strategy_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}

    footings = strategy_report.get("isolated_report", {}).get("footings", [])

    for footing in footings:
        column_id = footing.get("column_id")

        if not column_id:
            continue

        result[column_id] = {
            "N_ELS_kN": float(footing.get("N_ELS_kN", 0.0)),
            "N_ELU_kN": footing.get("N_ELU_kN"),
            "source_footing_id": footing.get("id"),
        }

    return result


def fctm_ec2_mpa(fck_mpa: float) -> float:
    if fck_mpa <= 50.0:
        return 0.30 * fck_mpa ** (2.0 / 3.0)

    return 2.12 * math.log(1.0 + (fck_mpa + 8.0) / 10.0)


def as_min_ec2_mm2_per_m(
    fck_mpa: float,
    fyk_mpa: float,
    d_m: float,
) -> float:
    d_mm = d_m * 1000.0
    fctm = fctm_ec2_mpa(fck_mpa)

    as_min_1 = 0.26 * fctm / fyk_mpa * 1000.0 * d_mm
    as_min_2 = 0.0013 * 1000.0 * d_mm

    return max(as_min_1, as_min_2)


def as_required_mm2_per_m(
    m_ed_kNm_per_m: float,
    d_m: float,
    fyk_mpa: float,
    gamma_s: float,
) -> float:
    if m_ed_kNm_per_m <= 0.0:
        return 0.0

    d_mm = d_m * 1000.0
    z_mm = 0.90 * d_mm
    fyd = fyk_mpa / gamma_s

    return m_ed_kNm_per_m * 1_000_000.0 / max(z_mm * fyd, 1e-9)


def bar_area_mm2(diameter_mm: float) -> float:
    return math.pi * diameter_mm * diameter_mm / 4.0


def provided_as_mm2_per_m(diameter_mm: float, spacing_m: float) -> float:
    return bar_area_mm2(diameter_mm) * 1000.0 / (spacing_m * 1000.0)


def choose_bars(as_required: float) -> dict[str, Any]:
    diameters = [10, 12, 14, 16, 20, 25]
    spacings_m = [0.20, 0.175, 0.15, 0.125, 0.10]

    best = None

    for diameter in diameters:
        for spacing in spacings_m:
            as_prov = provided_as_mm2_per_m(diameter, spacing)

            if as_prov >= as_required:
                candidate = {
                    "diameter_mm": diameter,
                    "spacing_m": spacing,
                    "spacing_cm": round(spacing * 100.0, 1),
                    "As_provided_mm2_m": round(as_prov, 1),
                    "label": f"HA{diameter}/e={round(spacing * 100.0, 1)}cm",
                }

                if best is None:
                    best = candidate
                elif candidate["As_provided_mm2_m"] < best["As_provided_mm2_m"]:
                    best = candidate

    if best is not None:
        return best

    diameter = 25
    spacing = 0.10

    return {
        "diameter_mm": diameter,
        "spacing_m": spacing,
        "spacing_cm": 10.0,
        "As_provided_mm2_m": round(provided_as_mm2_per_m(diameter, spacing), 1),
        "label": "HA25/e=10cm",
        "warning": "As demandee tres elevee. Augmenter H ou revoir la conception.",
    }


def get_element_loads(
    element: dict[str, Any],
    column_loads: dict[str, dict[str, Any]],
) -> dict[str, float]:
    n_els = 0.0
    n_elu = 0.0

    for column_id in element.get("columns", []):
        load = column_loads.get(column_id)

        if not load:
            continue

        n_els_col = float(load.get("N_ELS_kN", 0.0))

        if load.get("N_ELU_kN") is None:
            n_elu_col = 1.35 * n_els_col
        else:
            n_elu_col = float(load.get("N_ELU_kN"))

        n_els += n_els_col
        n_elu += n_elu_col

    return {
        "N_ELS_kN": round(n_els, 3),
        "N_ELU_kN": round(n_elu, 3),
    }


def get_projection_data(
    element: dict[str, Any],
    columns_geometry: dict[str, dict[str, float]],
) -> dict[str, float]:
    bbox = element["bbox"]

    max_proj_x = 0.0
    max_proj_y = 0.0

    xs = []
    ys = []

    for column_id in element.get("columns", []):
        column = columns_geometry.get(column_id)

        if not column:
            continue

        cx = float(column["cx"])
        cy = float(column["cy"])
        c1 = float(column["c1_m"])
        c2 = float(column["c2_m"])

        xs.append(cx)
        ys.append(cy)

        left = cx - c1 / 2.0 - float(bbox["xmin"])
        right = float(bbox["xmax"]) - (cx + c1 / 2.0)
        bottom = cy - c2 / 2.0 - float(bbox["ymin"])
        top = float(bbox["ymax"]) - (cy + c2 / 2.0)

        max_proj_x = max(max_proj_x, left, right, 0.0)
        max_proj_y = max(max_proj_y, bottom, top, 0.0)

    max_span_x = 0.0
    max_span_y = 0.0

    if len(xs) >= 2:
        xs = sorted(xs)
        max_span_x = max(xs[i + 1] - xs[i] for i in range(len(xs) - 1))

    if len(ys) >= 2:
        ys = sorted(ys)
        max_span_y = max(ys[i + 1] - ys[i] for i in range(len(ys) - 1))

    return {
        "max_projection_x_m": round(max_proj_x, 4),
        "max_projection_y_m": round(max_proj_y, 4),
        "max_span_x_m": round(max_span_x, 4),
        "max_span_y_m": round(max_span_y, 4),
    }


def design_element_reinforcement(
    element: dict[str, Any],
    columns_geometry: dict[str, dict[str, float]],
    column_loads: dict[str, dict[str, Any]],
    fck_mpa: float,
    fyk_mpa: float,
    gamma_s: float,
    cover_m: float,
    phi_main_mm: float,
) -> dict[str, Any]:
    warnings = []

    h_m = float(element.get("H_m", 0.35))
    d_m = max(h_m - cover_m - phi_main_mm / 1000.0 / 2.0, 0.12)

    area_m2 = float(element.get("area_provided_m2", 0.0))

    loads = get_element_loads(element, column_loads)

    n_elu = loads["N_ELU_kN"]

    if area_m2 <= 0.0:
        q_elu = 0.0
        warnings.append({
            "code": "AREA_ZERO",
            "message": "Surface de fondation nulle ou non lue.",
        })
    else:
        q_elu = n_elu / area_m2

    projection = get_projection_data(element, columns_geometry)

    proj_x = projection["max_projection_x_m"]
    proj_y = projection["max_projection_y_m"]
    span_x = projection["max_span_x_m"]
    span_y = projection["max_span_y_m"]

    # Convention pratique :
    # barres X = barres paralleles a X, contrôlées par projection/spans suivant Y.
    # barres Y = barres paralleles a Y, contrôlées par projection/spans suivant X.
    m_bottom_x = q_elu * proj_y * proj_y / 2.0
    m_bottom_y = q_elu * proj_x * proj_x / 2.0

    # Pour SC/RL, on ajoute une nappe supérieure préliminaire aux zones de poteaux.
    if element.get("type") in ["SC", "RL"]:
        m_top_x = max(0.50 * m_bottom_x, q_elu * span_y * span_y / 12.0)
        m_top_y = max(0.50 * m_bottom_y, q_elu * span_x * span_x / 12.0)
    else:
        m_top_x = 0.25 * m_bottom_x
        m_top_y = 0.25 * m_bottom_y

    as_min = as_min_ec2_mm2_per_m(
        fck_mpa=fck_mpa,
        fyk_mpa=fyk_mpa,
        d_m=d_m,
    )

    as_bottom_x_req = max(
        as_required_mm2_per_m(m_bottom_x, d_m, fyk_mpa, gamma_s),
        as_min,
    )

    as_bottom_y_req = max(
        as_required_mm2_per_m(m_bottom_y, d_m, fyk_mpa, gamma_s),
        as_min,
    )

    as_top_x_req = max(
        as_required_mm2_per_m(m_top_x, d_m, fyk_mpa, gamma_s),
        as_min,
    )

    as_top_y_req = max(
        as_required_mm2_per_m(m_top_y, d_m, fyk_mpa, gamma_s),
        as_min,
    )

    bottom_x = choose_bars(as_bottom_x_req)
    bottom_y = choose_bars(as_bottom_y_req)
    top_x = choose_bars(as_top_x_req)
    top_y = choose_bars(as_top_y_req)

    if element.get("status") != "OK_PRELIMINARY":
        warnings.append({
            "code": "FOUNDATION_ALTERNATIVE_REQUIRED",
            "message": "La fondation n'est pas valide en geometrie preliminaire. Ferraillage indicatif seulement.",
        })

    if max(as_bottom_x_req, as_bottom_y_req, as_top_x_req, as_top_y_req) > 1800.0:
        warnings.append({
            "code": "HIGH_REINFORCEMENT_RATIO",
            "message": "Aciers importants. Augmenter H ou revoir les dimensions.",
        })

    return {
        "foundation_id": element.get("id"),
        "foundation_type": element.get("type"),
        "columns": element.get("columns", []),
        "A_m": element.get("A_m"),
        "B_m": element.get("B_m"),
        "H_m": round(h_m, 3),
        "d_m": round(d_m, 3),
        "N_ELS_kN": loads["N_ELS_kN"],
        "N_ELU_kN": loads["N_ELU_kN"],
        "q_ELU_kPa": round(q_elu, 3),
        "projection": projection,
        "moments_kNm_per_m": {
            "M_bottom_bars_X": round(m_bottom_x, 3),
            "M_bottom_bars_Y": round(m_bottom_y, 3),
            "M_top_bars_X": round(m_top_x, 3),
            "M_top_bars_Y": round(m_top_y, 3),
        },
        "As_min_mm2_m": round(as_min, 1),
        "reinforcement": {
            "bottom_bars_X": {
                "As_required_mm2_m": round(as_bottom_x_req, 1),
                "proposal": bottom_x,
            },
            "bottom_bars_Y": {
                "As_required_mm2_m": round(as_bottom_y_req, 1),
                "proposal": bottom_y,
            },
            "top_bars_X": {
                "As_required_mm2_m": round(as_top_x_req, 1),
                "proposal": top_x,
            },
            "top_bars_Y": {
                "As_required_mm2_m": round(as_top_y_req, 1),
                "proposal": top_y,
            },
        },
        "warnings": warnings,
        "note": "Predimensionnement. Les moments doivent etre verifies par modele de calcul et combinaisons finales.",
    }


def design_reinforcement_prelim(
    model: dict[str, Any],
    strategy_report: dict[str, Any],
    fck_mpa: float = 25.0,
    fyk_mpa: float = 500.0,
    gamma_s: float = 1.15,
    cover_m: float = 0.05,
    phi_main_mm: float = 12.0,
) -> dict[str, Any]:
    columns_geometry = get_column_geometry(model)
    column_loads = build_column_load_map(strategy_report)

    results = []
    warnings = []
    errors = []

    final_foundations = strategy_report.get("final_foundations", [])

    if not final_foundations:
        return {
            "status": "ERROR",
            "method": "reinforcement_preliminary_v0_20",
            "message": "Aucune fondation finale trouvee dans strategy_report.final_foundations.",
            "results": [],
            "warnings": [],
            "errors": [
                {
                    "code": "NO_FINAL_FOUNDATIONS",
                    "message": "Verifier que /foundation-strategy utilise la derniere version du moteur.",
                }
            ],
        }

    for element in final_foundations:
        try:
            result = design_element_reinforcement(
                element=element,
                columns_geometry=columns_geometry,
                column_loads=column_loads,
                fck_mpa=fck_mpa,
                fyk_mpa=fyk_mpa,
                gamma_s=gamma_s,
                cover_m=cover_m,
                phi_main_mm=phi_main_mm,
            )

            results.append(result)

            for warning in result.get("warnings", []):
                warnings.append({
                    "foundation_id": result["foundation_id"],
                    **warning,
                })

        except Exception as error:
            errors.append({
                "foundation_id": element.get("id"),
                "code": "REINFORCEMENT_DESIGN_ERROR",
                "detail": str(error),
            })

    status = "OK"

    if errors:
        status = "ERROR"
    elif warnings:
        status = "WARNING"

    return {
        "status": status,
        "method": "reinforcement_preliminary_v0_20",
        "hypotheses": {
            "fck_mpa": fck_mpa,
            "fyk_mpa": fyk_mpa,
            "gamma_s": gamma_s,
            "cover_m": cover_m,
            "phi_main_mm": phi_main_mm,
            "steel_grade": f"HA FeE{int(fyk_mpa)}",
            "note": "Predimensionnement. Les aciers definitifs doivent etre recalcules avec les efforts finaux, les combinaisons ELU/ELS, le poinconnement et les dispositions constructives.",
        },
        "results": results,
        "warnings": warnings,
        "errors": errors,
        "summary": {
            "foundations_designed": len(results),
            "warnings_count": len(warnings),
            "errors_count": len(errors),
        },
    }
