from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def unit_weight_steel_kg_m(diameter_mm: float) -> float:
    """
    Poids lineaire acier HA :
    kg/m = phi² / 162
    """
    return round((diameter_mm * diameter_mm) / 162.0, 4)


def get_reinf_item(
    reinforcement_report: dict[str, Any],
    foundation_id: str,
) -> dict[str, Any] | None:
    for item in reinforcement_report.get("results", []):
        if item.get("foundation_id") == foundation_id:
            return item
    return None


def layer_bar_quantity(
    A_m: float,
    B_m: float,
    layer_data: dict[str, Any],
    direction: str,
    anchorage_extra_m: float = 0.30,
) -> dict[str, Any]:
    proposal = layer_data.get("proposal", {})

    diameter = safe_float(proposal.get("diameter_mm"), 0.0)
    spacing = safe_float(proposal.get("spacing_m"), 0.20)
    label = proposal.get("label", "-")

    if diameter <= 0 or spacing <= 0:
        return {
            "label": label,
            "diameter_mm": diameter,
            "spacing_m": spacing,
            "bar_count": 0,
            "bar_length_m": 0.0,
            "total_length_m": 0.0,
            "weight_kg": 0.0,
        }

    if direction == "X":
        bar_count = int(B_m / spacing) + 1
        bar_length = A_m + 2.0 * anchorage_extra_m
    else:
        bar_count = int(A_m / spacing) + 1
        bar_length = B_m + 2.0 * anchorage_extra_m

    total_length = bar_count * bar_length
    weight = total_length * unit_weight_steel_kg_m(diameter)

    return {
        "label": label,
        "diameter_mm": diameter,
        "spacing_m": round(spacing, 3),
        "bar_count": bar_count,
        "bar_length_m": round(bar_length, 2),
        "total_length_m": round(total_length, 2),
        "weight_kg": round(weight, 2),
    }


def estimate_foundation_steel(
    element: dict[str, Any],
    reinf_item: dict[str, Any] | None,
) -> dict[str, Any]:
    A_m = safe_float(element.get("A_m"))
    B_m = safe_float(element.get("B_m"))

    if reinf_item is None:
        return {
            "bottom_X_kg": 0.0,
            "bottom_Y_kg": 0.0,
            "top_X_kg": 0.0,
            "top_Y_kg": 0.0,
            "total_kg": 0.0,
            "layers": {},
        }

    reinforcement = reinf_item.get("reinforcement", {})

    bottom_x = layer_bar_quantity(
        A_m=A_m,
        B_m=B_m,
        layer_data=reinforcement.get("bottom_bars_X", {}),
        direction="X",
    )

    bottom_y = layer_bar_quantity(
        A_m=A_m,
        B_m=B_m,
        layer_data=reinforcement.get("bottom_bars_Y", {}),
        direction="Y",
    )

    top_x = layer_bar_quantity(
        A_m=A_m,
        B_m=B_m,
        layer_data=reinforcement.get("top_bars_X", {}),
        direction="X",
    )

    top_y = layer_bar_quantity(
        A_m=A_m,
        B_m=B_m,
        layer_data=reinforcement.get("top_bars_Y", {}),
        direction="Y",
    )

    total = (
        bottom_x["weight_kg"]
        + bottom_y["weight_kg"]
        + top_x["weight_kg"]
        + top_y["weight_kg"]
    )

    return {
        "bottom_X_kg": bottom_x["weight_kg"],
        "bottom_Y_kg": bottom_y["weight_kg"],
        "top_X_kg": top_x["weight_kg"],
        "top_Y_kg": top_y["weight_kg"],
        "total_kg": round(total, 2),
        "layers": {
            "bottom_X": bottom_x,
            "bottom_Y": bottom_y,
            "top_X": top_x,
            "top_Y": top_y,
        },
    }


def estimate_concrete_and_formwork(
    element: dict[str, Any],
    clean_concrete_m: float,
) -> dict[str, Any]:
    A_m = safe_float(element.get("A_m"))
    B_m = safe_float(element.get("B_m"))
    H_m = safe_float(element.get("H_m"))

    area = A_m * B_m
    perimeter = 2.0 * (A_m + B_m)

    concrete = area * H_m
    clean_concrete = area * clean_concrete_m
    formwork = perimeter * H_m

    return {
        "area_m2": round(area, 3),
        "perimeter_m": round(perimeter, 3),
        "concrete_m3": round(concrete, 3),
        "clean_concrete_m3": round(clean_concrete, 3),
        "formwork_m2": round(formwork, 3),
    }


def estimate_starter_steel(
    anchorage_report: dict[str, Any],
    starter_extra_above_foundation_m: float = 1.00,
) -> dict[str, Any]:
    rows = []
    total_weight = 0.0
    total_length = 0.0

    for row in anchorage_report.get("rows", []):
        starter = row.get("starter_bars", {})
        anchorage = row.get("anchorage", {})

        count = int(starter.get("count", 0))
        diameter = safe_float(starter.get("diameter_mm"), 0.0)
        lbd = safe_float(anchorage.get("Lbd_m"), 0.0)

        single_length = lbd + starter_extra_above_foundation_m
        length = count * single_length
        weight = length * unit_weight_steel_kg_m(diameter)

        item = {
            "column_id": row.get("column_id"),
            "foundation_id": row.get("foundation_id"),
            "label": starter.get("label", "-"),
            "count": count,
            "diameter_mm": diameter,
            "single_length_m": round(single_length, 2),
            "total_length_m": round(length, 2),
            "weight_kg": round(weight, 2),
        }

        rows.append(item)
        total_weight += weight
        total_length += length

    return {
        "rows": rows,
        "total_length_m": round(total_length, 2),
        "total_weight_kg": round(total_weight, 2),
    }


def build_foundation_boq(
    strategy_report: dict[str, Any],
    reinforcement_report: dict[str, Any],
    anchorage_report: dict[str, Any],
    clean_concrete_m: float = 0.10,
) -> dict[str, Any]:
    foundation_rows = []

    totals = {
        "concrete_m3": 0.0,
        "clean_concrete_m3": 0.0,
        "formwork_m2": 0.0,
        "foundation_steel_kg": 0.0,
        "starter_steel_kg": 0.0,
        "total_steel_kg": 0.0,
    }

    for element in strategy_report.get("final_foundations", []):
        fid = str(element.get("id", "-"))
        reinf_item = get_reinf_item(reinforcement_report, fid)

        concrete = estimate_concrete_and_formwork(
            element=element,
            clean_concrete_m=clean_concrete_m,
        )

        steel = estimate_foundation_steel(
            element=element,
            reinf_item=reinf_item,
        )

        row = {
            "foundation_id": fid,
            "type": element.get("type"),
            "columns": element.get("columns", []),
            "A_m": element.get("A_m"),
            "B_m": element.get("B_m"),
            "H_m": element.get("H_m"),
            "concrete": concrete,
            "steel": steel,
        }

        foundation_rows.append(row)

        totals["concrete_m3"] += concrete["concrete_m3"]
        totals["clean_concrete_m3"] += concrete["clean_concrete_m3"]
        totals["formwork_m2"] += concrete["formwork_m2"]
        totals["foundation_steel_kg"] += steel["total_kg"]

    starters = estimate_starter_steel(anchorage_report)

    totals["starter_steel_kg"] = starters["total_weight_kg"]
    totals["total_steel_kg"] = totals["foundation_steel_kg"] + totals["starter_steel_kg"]

    for key in totals:
        totals[key] = round(totals[key], 2)

    return {
        "status": "OK",
        "method": "foundation_boq_v0_28",
        "hypotheses": {
            "clean_concrete_m": clean_concrete_m,
            "steel_weight_rule": "kg/m = phi^2 / 162",
            "formwork_rule": "coffrage lateral = perimetre x H",
            "starter_rule": "longueur attente = Lbd + 1.00 m hors fondation",
            "note": "Metre estimatif de predimensionnement. A verifier avec plans definitifs.",
        },
        "foundations": foundation_rows,
        "starter_bars": starters,
        "totals": totals,
        "summary": {
            "foundation_count": len(foundation_rows),
            "starter_rows": len(starters.get("rows", [])),
        },
    }


def export_boq_csv(
    boq_report: dict[str, Any],
    output_path: str | Path,
) -> str:
    output_path = Path(output_path)

    with output_path.open("w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.writer(csvfile, delimiter=";")

        writer.writerow([
            "ID",
            "TYPE",
            "POTEAUX",
            "A_m",
            "B_m",
            "H_m",
            "BETON_m3",
            "BETON_PROPRETE_m3",
            "COFFRAGE_m2",
            "ACIER_FONDATION_kg",
        ])

        for row in boq_report.get("foundations", []):
            concrete = row.get("concrete", {})
            steel = row.get("steel", {})

            writer.writerow([
                row.get("foundation_id"),
                row.get("type"),
                ",".join(row.get("columns", [])),
                row.get("A_m"),
                row.get("B_m"),
                row.get("H_m"),
                concrete.get("concrete_m3"),
                concrete.get("clean_concrete_m3"),
                concrete.get("formwork_m2"),
                steel.get("total_kg"),
            ])

        writer.writerow([])
        writer.writerow(["ATTENTES POTEAUX"])
        writer.writerow([
            "POTEAU",
            "FONDATION",
            "LIBELLE",
            "NB",
            "DIA_mm",
            "LONG_UNITAIRE_m",
            "LONG_TOTAL_m",
            "POIDS_kg",
        ])

        for row in boq_report.get("starter_bars", {}).get("rows", []):
            writer.writerow([
                row.get("column_id"),
                row.get("foundation_id"),
                row.get("label"),
                row.get("count"),
                row.get("diameter_mm"),
                row.get("single_length_m"),
                row.get("total_length_m"),
                row.get("weight_kg"),
            ])

        writer.writerow([])
        writer.writerow(["TOTAUX"])

        for key, value in boq_report.get("totals", {}).items():
            writer.writerow([key, value])

    return str(output_path)
