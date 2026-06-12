from __future__ import annotations

from typing import Any


def rho_from_as(
    as_mm2_m: float,
    d_m: float,
) -> float:
    """
    rho = As / (b*d), avec b = 1000 mm.
    As est en mm2/m.
    """
    d_mm = d_m * 1000.0

    if d_mm <= 0:
        return 0.0

    return as_mm2_m / (1000.0 * d_mm)


def check_layer(
    layer_name: str,
    layer_data: dict[str, Any],
    d_m: float,
    max_spacing_m: float,
    min_diameter_mm: float,
) -> dict[str, Any]:
    proposal = layer_data.get("proposal", {})

    as_required = float(layer_data.get("As_required_mm2_m", 0.0))
    as_provided = float(proposal.get("As_provided_mm2_m", 0.0))
    diameter = float(proposal.get("diameter_mm", 0.0))
    spacing = float(proposal.get("spacing_m", 999.0))
    label = proposal.get("label", "-")

    warnings = []
    errors = []

    ratio = as_provided / as_required if as_required > 0 else 999.0

    if as_provided + 1e-6 < as_required:
        errors.append({
            "code": "AS_PROVIDED_INSUFFICIENT",
            "message": "Section d'acier fournie inferieure a la section requise.",
        })

    if spacing > max_spacing_m + 1e-9:
        warnings.append({
            "code": "SPACING_TOO_LARGE",
            "message": f"Espacement {spacing:.2f} m superieur au maximum admis {max_spacing_m:.2f} m.",
        })

    if diameter < min_diameter_mm - 1e-9:
        warnings.append({
            "code": "DIAMETER_TOO_SMALL",
            "message": f"Diametre HA{diameter:.0f} inferieur au minimum recommande HA{min_diameter_mm:.0f}.",
        })

    rho = rho_from_as(
        as_mm2_m=as_provided,
        d_m=d_m,
    )

    if errors:
        status = "NOT_OK"
    elif warnings:
        status = "WARNING"
    else:
        status = "OK"

    return {
        "layer": layer_name,
        "label": label,
        "As_required_mm2_m": round(as_required, 1),
        "As_provided_mm2_m": round(as_provided, 1),
        "ratio_provided_required": round(ratio, 3),
        "diameter_mm": diameter,
        "spacing_m": round(spacing, 3),
        "rho_real": round(rho, 5),
        "status": status,
        "warnings": warnings,
        "errors": errors,
    }


def check_foundation_reinforcement(
    item: dict[str, Any],
    max_spacing_m: float,
    min_diameter_mm: float,
) -> dict[str, Any]:
    reinforcement = item.get("reinforcement", {})
    d_m = float(item.get("d_m", 0.0))

    layers_to_check = [
        "bottom_bars_X",
        "bottom_bars_Y",
        "top_bars_X",
        "top_bars_Y",
    ]

    layer_checks = []

    for layer_name in layers_to_check:
        layer_data = reinforcement.get(layer_name, {})

        layer_checks.append(
            check_layer(
                layer_name=layer_name,
                layer_data=layer_data,
                d_m=d_m,
                max_spacing_m=max_spacing_m,
                min_diameter_mm=min_diameter_mm,
            )
        )

    errors = []
    warnings = []

    for check in layer_checks:
        errors.extend(check.get("errors", []))

        for warning in check.get("warnings", []):
            warnings.append({
                "layer": check["layer"],
                **warning,
            })

    bottom_x = next(c for c in layer_checks if c["layer"] == "bottom_bars_X")
    bottom_y = next(c for c in layer_checks if c["layer"] == "bottom_bars_Y")

    rho_x = float(bottom_x["rho_real"])
    rho_y = float(bottom_y["rho_real"])

    # rho_l réel pour poinçonnement EC2 : moyenne géométrique des deux directions,
    # avec limite haute généralement prise à 2%.
    rho_l_real = min((rho_x * rho_y) ** 0.5, 0.02)

    if errors:
        status = "NOT_OK"
    elif warnings:
        status = "WARNING"
    else:
        status = "OK"

    return {
        "foundation_id": item.get("foundation_id"),
        "foundation_type": item.get("foundation_type"),
        "columns": item.get("columns", []),
        "A_m": item.get("A_m"),
        "B_m": item.get("B_m"),
        "H_m": item.get("H_m"),
        "d_m": item.get("d_m"),
        "N_ELU_kN": item.get("N_ELU_kN"),
        "q_ELU_kPa": item.get("q_ELU_kPa"),
        "rho_l_real_for_punching": round(rho_l_real, 5),
        "layer_checks": layer_checks,
        "status": status,
        "warnings": warnings,
        "errors": errors,
    }


def check_reinforcement_final(
    reinforcement_report: dict[str, Any],
    max_spacing_m: float = 0.20,
    min_diameter_mm: float = 10.0,
) -> dict[str, Any]:
    checks = []
    warnings = []
    errors = []

    for item in reinforcement_report.get("results", []):
        check = check_foundation_reinforcement(
            item=item,
            max_spacing_m=max_spacing_m,
            min_diameter_mm=min_diameter_mm,
        )

        checks.append(check)

        for warning in check.get("warnings", []):
            warnings.append({
                "foundation_id": check["foundation_id"],
                **warning,
            })

        for error in check.get("errors", []):
            errors.append({
                "foundation_id": check["foundation_id"],
                **error,
            })

    if errors:
        status = "NOT_OK"
    elif warnings:
        status = "WARNING"
    else:
        status = "OK"

    return {
        "status": status,
        "method": "reinforcement_final_check_v0_23",
        "hypotheses": {
            "max_spacing_m": max_spacing_m,
            "min_diameter_mm": min_diameter_mm,
            "note": "Verification finale de coherence des aciers proposes. Les efforts definitifs, ancrages, recouvrements et dispositions sismiques restent a valider.",
        },
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "summary": {
            "foundations_checked": len(checks),
            "warnings_count": len(warnings),
            "errors_count": len(errors),
        },
    }
