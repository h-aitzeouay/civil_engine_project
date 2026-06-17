from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from civil_engine.readers.dxf_reader import read_dxf_model, read_dxf_summary
from civil_engine.checks.column_continuity import check_column_continuity
from civil_engine.checks.axis_detection import detect_axes_and_spans
from civil_engine.engine.tributary_areas import compute_tributary_areas
from civil_engine.engine.load_takedown import compute_load_takedown
from civil_engine.engine.wall_load_takedown import compute_wall_load_takedown
from civil_engine.foundations.footing_predim import predimension_isolated_footings
from civil_engine.foundations.strip_footing_under_wall import (
    design_strip_footings_under_walls,
    WallInput as StripWallInput,
    Rect as StripRect,
)
from civil_engine.foundations.strip_isolated_interference import (
    resolve_peripheral_strip_isolated_interferences,
    ColumnInput as IntfColumnInput,
    WallRef as IntfWallRef,
    IsolatedFootingInput as IntfIsolatedFooting,
    StripFootingInput as IntfStripFooting,
)
from civil_engine.plans.strip_footing_dxf import generate_strip_footings_dxf
from civil_engine.quantities.strip_footing_boq import strip_footings_boq
from civil_engine.plans.foundation_dxf import generate_foundation_predim_dxf
from civil_engine.foundations.combined_footings import generate_combined_footings
from civil_engine.plans.combined_foundation_dxf import generate_combined_foundation_dxf
from civil_engine.foundations.combined_eccentricity import check_combined_eccentricity
from civil_engine.foundations.combined_optimizer import optimize_combined_footings
from civil_engine.foundations.foundation_strategy_refined import decide_foundation_strategy
from civil_engine.foundations.support_geometry import fix_support_geometry_non_destructive
from civil_engine.checks.punching_prelim import check_punching_prelim
from civil_engine.checks.punching_final import check_punching_final
from civil_engine.design.reinforcement_prelim import design_reinforcement_prelim
from civil_engine.design.anchorage_details import build_anchorage_details
from civil_engine.checks.reinforcement_final_check import check_reinforcement_final
from civil_engine.plans.reinforcement_dxf import generate_reinforcement_dxf
from civil_engine.plans.starter_bars_dxf import generate_starter_bars_dxf
from civil_engine.plans.anchorage_details_dxf import generate_anchorage_details_dxf
from civil_engine.plans.foundation_sections_dxf import generate_foundation_sections_dxf
from civil_engine.plans.execution_foundation_dxf import generate_execution_foundation_dxf
from civil_engine.quantities.foundation_boq import build_foundation_boq, export_boq_csv
from civil_engine.reports.foundation_calculation_report import build_foundation_calculation_report, export_calculation_report_md
from civil_engine.reports.foundation_report_exports import export_calculation_report_docx, export_calculation_report_pdf
from civil_engine.deliverables.project_package import generate_project_package_zip
from civil_engine.quality.project_quality_check import build_project_quality_check
from civil_engine.dashboard.project_dashboard import build_project_dashboard
from civil_engine.reports.project_summary_report import export_project_summary_docx, export_project_summary_pdf
from civil_engine.quality.strategy_quality_remediation import fix_foundations_inside_emprise, fix_punching_by_increasing_thickness, secure_anchorage_execution_solution
from civil_engine.plans.punching_dxf import generate_punching_dxf
from civil_engine.plans.foundation_strategy_dxf import generate_foundation_strategy_dxf
from civil_engine.plans.optimized_combined_foundation_dxf import generate_optimized_combined_foundation_dxf


app = FastAPI(
    title="civil_engine API — INGENIERIE.COM",
    version="0.35.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "OK",
        "service": "civil_engine",
    }


def save_uploaded_file(upload_file: UploadFile, folder: Path) -> Path:
    file_path = folder / upload_file.filename

    with file_path.open("wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)

    return file_path


@app.post("/validate-dxf")
async def validate_dxf(
    dxf: UploadFile = File(...),
) -> JSONResponse:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            report = read_dxf_summary(dxf_path)
            return JSONResponse(report)

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant la lecture du DXF.",
                    "detail": str(error),
                },
            )


@app.post("/extract-model")
async def extract_model(
    dxf: UploadFile = File(...),
) -> JSONResponse:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            model = read_dxf_model(dxf_path)
            return JSONResponse(model)

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant l'extraction du model.json.",
                    "detail": str(error),
                },
            )


@app.post("/check-columns")
async def check_columns(
    dxf: UploadFile = File(...),
) -> JSONResponse:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            model = read_dxf_model(dxf_path)
            report = check_column_continuity(
                model=model,
                tolerance_m=0.50,
            )
            return JSONResponse(report)

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant le contrôle de continuité des poteaux.",
                    "detail": str(error),
                },
            )


@app.post("/detect-axes")
async def detect_axes(
    dxf: UploadFile = File(...),
) -> JSONResponse:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            model = read_dxf_model(dxf_path)
            report = detect_axes_and_spans(
                model=model,
                level_name="FONDATION",
                axis_tolerance_m=0.20,
                max_preferred_span_m=6.00,
            )
            return JSONResponse(report)

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant la détection des axes.",
                    "detail": str(error),
                },
            )


@app.post("/tributary-areas")
async def tributary_areas(
    dxf: UploadFile = File(...),
) -> JSONResponse:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            model = read_dxf_model(dxf_path)
            report = compute_tributary_areas(
                model=model,
                axis_tolerance_m=0.20,
            )
            return JSONResponse(report)

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant le calcul des surfaces tributaires.",
                    "detail": str(error),
                },
            )


@app.post("/load-takedown")
async def load_takedown(
    dxf: UploadFile = File(...),
) -> JSONResponse:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            model = read_dxf_model(dxf_path)
            report = compute_load_takedown(
                model=model,
                g_floor_kN_m2=5.00,
                q_floor_kN_m2=1.50,
                g_terrace_kN_m2=6.00,
                q_terrace_kN_m2=1.00,
                gamma_g=1.35,
                gamma_q=1.50,
            )
            return JSONResponse(report)

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant la descente de charges.",
                    "detail": str(error),
                },
            )


@app.post("/footing-predim")
async def footing_predim(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
) -> JSONResponse:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            model = read_dxf_model(dxf_path)
            report = predimension_isolated_footings(
                model=model,
                q_allowable_kPa=q_allowable_kPa,
                min_side_m=0.80,
                thickness_m=0.35,
                dimension_step_m=0.05,
                property_limit_margin_m=0.05,
            )
            return JSONResponse(report)

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant le prédimensionnement des semelles.",
                    "detail": str(error),
                },
            )


@app.post("/strip-footings")
async def strip_footings(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
    wall_thickness_m: float = Form(0.20),
    storey_height_m: float = Form(3.00),
    g_floor_kN_m2: float = Form(5.00),
    q_floor_kN_m2: float = Form(1.50),
    g_terrace_kN_m2: float = Form(6.00),
    q_terrace_kN_m2: float = Form(1.00),
    fck_mpa: float = Form(25.0),
    fyk_mpa: float = Form(500.0),
    gamma_s: float = Form(1.15),
    cover_m: float = Form(0.05),
    phi_main_mm: float = Form(12.0),
    phi_distribution_mm: float = Form(10.0),
) -> JSONResponse:
    """
    Dimensionnement des semelles filantes sous voiles.

    Lit les voiles depuis le calque NIVEAU-VOILE-AXE (axe en polyligne ouverte),
    calcule la charge lineaire par bande tributaire (demi-portee de chaque cote),
    puis dimensionne chaque semelle filante (largeur, hauteur, ferraillage).
    L'epaisseur du voile et la hauteur d'etage sont saisies en parametres.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            model = read_dxf_model(dxf_path)

            # Brique 2 : descente de charges lineaire des voiles
            wlt = compute_wall_load_takedown(
                model=model,
                wall_thickness_m=wall_thickness_m,
                storey_height_m=storey_height_m,
                g_floor_kN_m2=g_floor_kN_m2,
                q_floor_kN_m2=q_floor_kN_m2,
                g_terrace_kN_m2=g_terrace_kN_m2,
                q_terrace_kN_m2=q_terrace_kN_m2,
                gamma_g=1.35,
                gamma_q=1.50,
            )

            walls_data = wlt.get("walls", [])
            if not walls_data:
                return JSONResponse({
                    "status": "OK",
                    "message": "Aucun voile (calque NIVEAU-VOILE-AXE) trouve dans le DXF.",
                    "wall_load_takedown": wlt,
                    "strip_footings": [],
                })

            # Construire les WallInput depuis la descente de charges
            walls = [
                StripWallInput(
                    id=w["id"], x1=w["x1"], y1=w["y1"], x2=w["x2"], y2=w["y2"],
                    thickness_m=w["thickness_m"],
                    n_sls_kN_per_m=w["n_sls_kN_per_m"],
                    n_uls_kN_per_m=w["n_uls_kN_per_m"],
                )
                for w in walls_data
            ]

            # Emprise (niveau FONDATION)
            fond = next((l for l in model["levels"] if l["name"] == "FONDATION"),
                        model["levels"][0] if model["levels"] else None)
            if fond is None or not fond.get("footprints"):
                return JSONResponse(
                    status_code=400,
                    content={"status": "ERROR",
                             "message": "Emprise FONDATION introuvable pour caler les semelles filantes."},
                )
            emp = fond["footprints"][0]["bbox"]
            emprise = StripRect(emp["xmin"], emp["ymin"], emp["xmax"], emp["ymax"])

            # Brique 3 : dimensionnement des semelles filantes
            design = design_strip_footings_under_walls(
                walls=walls,
                emprise=emprise,
                q_allowable_kPa=q_allowable_kPa,
                fck_mpa=fck_mpa,
                fyk_mpa=fyk_mpa,
                gamma_s=gamma_s,
                cover_m=cover_m,
                phi_main_mm=phi_main_mm,
                phi_distribution_mm=phi_distribution_mm,
            )

            # Brique 3bis : resolution des chevauchements filantes <-> isolees peripheriques
            interference = None
            try:
                # Semelles isolees des poteaux
                iso_report = predimension_isolated_footings(
                    model=model, q_allowable_kPa=q_allowable_kPa,
                    min_side_m=0.80, thickness_m=0.35,
                    dimension_step_m=0.05, property_limit_margin_m=0.05,
                )
                iso_footings_raw = iso_report.get("footings", [])

                # Marge de peripherie : un support est peripherique s'il est
                # a moins de peripheral_margin du bord de l'emprise.
                peripheral_margin = 1.0
                ex0, ey0, ex1, ey1 = emp["xmin"], emp["ymin"], emp["xmax"], emp["ymax"]

                def _is_peripheral(x, y):
                    return (
                        abs(x - ex0) <= peripheral_margin or abs(x - ex1) <= peripheral_margin
                        or abs(y - ey0) <= peripheral_margin or abs(y - ey1) <= peripheral_margin
                    )

                # Construire les entrees du module d'interference
                intf_walls = [
                    IntfWallRef(id=w["id"], x1=w["x1"], y1=w["y1"], x2=w["x2"], y2=w["y2"],
                                thickness_m=w["thickness_m"], n_sls_kN_per_m=w["n_sls_kN_per_m"],
                                is_peripheral=True)
                    for w in walls_data
                ]
                intf_strips = [
                    IntfStripFooting(
                        id=sf["id"], wall_id=sf["wall_id"],
                        bbox=StripRect(**sf["bbox"]), H_m=sf["H_m"], B_m=sf["B_m"],
                        q_sls_kPa=sf["q_sls_kPa"])
                    for sf in design.get("strip_footings", [])
                ]
                cols_by_id = {c["id"]: c for c in fond.get("columns", [])}
                intf_columns = []
                intf_isolated = []
                for f in iso_footings_raw:
                    cid = f["column_id"]
                    cx, cy = f.get("column_cx", f["cx"]), f.get("column_cy", f["cy"])
                    col = cols_by_id.get(cid, {})
                    intf_columns.append(IntfColumnInput(
                        id=cid, x=cx, y=cy,
                        bx_m=col.get("bx", 0.30), by_m=col.get("by", 0.30),
                        n_sls_kN=f.get("N_ELS_kN", 0.0), n_uls_kN=f.get("N_ELU_kN"),
                        is_peripheral=_is_peripheral(cx, cy)))
                    intf_isolated.append(IntfIsolatedFooting(
                        id=f["id"], column_id=cid,
                        bbox=StripRect(**f["bbox"]), H_m=f["thickness_m"],
                        q_sls_kPa=f.get("soil_pressure_ELS_kPa")))

                interference = resolve_peripheral_strip_isolated_interferences(
                    emprise=emprise, walls=intf_walls, columns=intf_columns,
                    strip_footings=intf_strips, isolated_footings=intf_isolated,
                    q_allowable_kPa=q_allowable_kPa)
            except Exception as intf_err:
                interference = {"status": "ERROR",
                                "message": "Resolution des chevauchements echouee.",
                                "detail": str(intf_err)}

            return JSONResponse({
                "status": design["status"],
                "method": "strip_footings_pipeline_v2",
                "hypotheses": {
                    "q_allowable_kPa": q_allowable_kPa,
                    "wall_thickness_m": wall_thickness_m,
                    "storey_height_m": storey_height_m,
                    "g_floor_kN_m2": g_floor_kN_m2,
                    "q_floor_kN_m2": q_floor_kN_m2,
                    "g_terrace_kN_m2": g_terrace_kN_m2,
                    "q_terrace_kN_m2": q_terrace_kN_m2,
                    "fck_mpa": fck_mpa,
                    "fyk_mpa": fyk_mpa,
                },
                "wall_load_takedown": wlt,
                "strip_footings_design": design,
                "interference_resolution": interference,
                "boq": strip_footings_boq(design, interference),
            })

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant le dimensionnement des semelles filantes.",
                    "detail": str(error),
                },
            )


@app.post("/strip-footings-dxf", response_model=None)
async def strip_footings_dxf(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
    wall_thickness_m: float = Form(0.20),
    storey_height_m: float = Form(3.00),
    g_floor_kN_m2: float = Form(5.00),
    q_floor_kN_m2: float = Form(1.50),
    g_terrace_kN_m2: float = Form(6.00),
    q_terrace_kN_m2: float = Form(1.00),
    fck_mpa: float = Form(25.0),
    fyk_mpa: float = Form(500.0),
    gamma_s: float = Form(1.15),
    cover_m: float = Form(0.05),
    phi_main_mm: float = Form(12.0),
    phi_distribution_mm: float = Form(10.0),
):
    """
    Genere le PLAN DXF des semelles filantes (emprise, voiles, semelles,
    massifs, annotations) a telecharger.
    """
    temp_path = Path(tempfile.mkdtemp())
    dxf_path = save_uploaded_file(dxf, temp_path)

    try:
        model = read_dxf_model(dxf_path)

        wlt = compute_wall_load_takedown(
            model=model, wall_thickness_m=wall_thickness_m, storey_height_m=storey_height_m,
            g_floor_kN_m2=g_floor_kN_m2, q_floor_kN_m2=q_floor_kN_m2,
            g_terrace_kN_m2=g_terrace_kN_m2, q_terrace_kN_m2=q_terrace_kN_m2,
            gamma_g=1.35, gamma_q=1.50)

        walls_data = wlt.get("walls", [])
        fond = next((l for l in model["levels"] if l["name"] == "FONDATION"),
                    model["levels"][0] if model["levels"] else None)
        if fond is None or not fond.get("footprints"):
            return JSONResponse(status_code=400, content={
                "status": "ERROR", "message": "Emprise FONDATION introuvable."})
        emp = fond["footprints"][0]["bbox"]
        emprise = StripRect(emp["xmin"], emp["ymin"], emp["xmax"], emp["ymax"])

        if not walls_data:
            # plan vide mais valide (emprise seule)
            design = {"status": "OK", "emprise": emp, "strip_footings": [], "massifs": []}
            interference = None
        else:
            walls = [StripWallInput(id=w["id"], x1=w["x1"], y1=w["y1"], x2=w["x2"], y2=w["y2"],
                                    thickness_m=w["thickness_m"], n_sls_kN_per_m=w["n_sls_kN_per_m"],
                                    n_uls_kN_per_m=w["n_uls_kN_per_m"]) for w in walls_data]
            design = design_strip_footings_under_walls(
                walls=walls, emprise=emprise, q_allowable_kPa=q_allowable_kPa,
                fck_mpa=fck_mpa, fyk_mpa=fyk_mpa, gamma_s=gamma_s, cover_m=cover_m,
                phi_main_mm=phi_main_mm, phi_distribution_mm=phi_distribution_mm)
            interference = None  # le dessin des massifs locaux est optionnel ici

        output_path = temp_path / "PLAN_SEMELLES_FILANTES_INGENIERIE.dxf"
        generate_strip_footings_dxf(
            strip_result=design, interference_result=interference,
            output_path=output_path)

        return FileResponse(
            path=output_path,
            filename="PLAN_SEMELLES_FILANTES_INGENIERIE.dxf",
            media_type="application/dxf",
        )

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={"status": "ERROR",
                     "message": "Erreur pendant la generation du plan des semelles filantes.",
                     "detail": str(error)},
        )


@app.post("/foundation-dxf", response_model=None)
async def foundation_dxf(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
):
    """
    Génère un DXF fondations préliminaire.

    Attention :
    - les PR dessinées sont conceptuelles ;
    - les semelles doivent être recalculées ;
    - le ferraillage n'est pas encore généré.
    """
    temp_path = Path(tempfile.mkdtemp())
    dxf_path = save_uploaded_file(dxf, temp_path)

    try:
        model = read_dxf_model(dxf_path)

        footing_report = predimension_isolated_footings(
            model=model,
            q_allowable_kPa=q_allowable_kPa,
            min_side_m=0.80,
            thickness_m=0.35,
            dimension_step_m=0.05,
            property_limit_margin_m=0.05,
        )

        output_path = temp_path / "FONDATIONS_PREDIM_INGENIERIE_COM.dxf"

        generate_foundation_predim_dxf(
            model=model,
            footing_report=footing_report,
            output_path=output_path,
        )

        return FileResponse(
            path=output_path,
            filename="FONDATIONS_PREDIM_INGENIERIE_COM.dxf",
            media_type="application/dxf",
        )

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "status": "ERROR",
                "message": "Erreur pendant la génération du DXF fondations.",
                "detail": str(error),
            },
        )


@app.post("/combined-footings")
async def combined_footings(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
) -> JSONResponse:
    """
    Détecte les interférences entre semelles isolées
    et génère des semelles combinées préliminaires.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            model = read_dxf_model(dxf_path)

            report = generate_combined_footings(
                model=model,
                q_allowable_kPa=q_allowable_kPa,
            )

            return JSONResponse(report)

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant la génération des semelles combinées.",
                    "detail": str(error),
                },
            )

@app.post("/combined-foundation-dxf", response_model=None)
async def combined_foundation_dxf(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
):
    """
    Génère un DXF avec semelles isolées, semelles excentrées,
    semelles combinées et massifs.
    """
    temp_path = Path(tempfile.mkdtemp())
    dxf_path = save_uploaded_file(dxf, temp_path)

    try:
        model = read_dxf_model(dxf_path)

        combined_report = generate_combined_footings(
            model=model,
            q_allowable_kPa=q_allowable_kPa,
        )

        output_path = temp_path / "FONDATIONS_COMBINEES_INGENIERIE_COM.dxf"

        generate_combined_foundation_dxf(
            model=model,
            combined_report=combined_report,
            output_path=output_path,
        )

        return FileResponse(
            path=output_path,
            filename="FONDATIONS_COMBINEES_INGENIERIE_COM.dxf",
            media_type="application/dxf",
        )

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "status": "ERROR",
                "message": "Erreur pendant la génération du DXF des semelles combinées.",
                "detail": str(error),
            },
        )

@app.post("/combined-eccentricity-check")
async def combined_eccentricity_check(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
) -> JSONResponse:
    """
    Vérifie l'excentricité de la résultante des charges
    dans les semelles combinées préliminaires.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            model = read_dxf_model(dxf_path)

            report = check_combined_eccentricity(
                model=model,
                q_allowable_kPa=q_allowable_kPa,
            )

            return JSONResponse(report)

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant le contrôle d'excentricité des semelles combinées.",
                    "detail": str(error),
                },
            )

@app.post("/optimize-combined-footings")
async def optimize_combined_footings_endpoint(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
) -> JSONResponse:
    """
    Recalage automatique des semelles combinées
    sur le centre de charge ELS.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            model = read_dxf_model(dxf_path)

            report = optimize_combined_footings(
                model=model,
                q_allowable_kPa=q_allowable_kPa,
            )

            return JSONResponse(report)

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant l'optimisation des semelles combinées.",
                    "detail": str(error),
                },
            )

@app.post("/optimized-combined-foundation-dxf", response_model=None)
async def optimized_combined_foundation_dxf(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
):
    """
    Génère un DXF avec semelles combinées optimisées/recentrées.
    """
    temp_path = Path(tempfile.mkdtemp())
    dxf_path = save_uploaded_file(dxf, temp_path)

    try:
        model = read_dxf_model(dxf_path)

        optimization_report = optimize_combined_footings(
            model=model,
            q_allowable_kPa=q_allowable_kPa,
        )

        output_path = temp_path / "FONDATIONS_COMBINEES_OPTIMISEES_INGENIERIE_COM.dxf"

        generate_optimized_combined_foundation_dxf(
            model=model,
            optimization_report=optimization_report,
            output_path=output_path,
        )

        return FileResponse(
            path=output_path,
            filename="FONDATIONS_COMBINEES_OPTIMISEES_INGENIERIE_COM.dxf",
            media_type="application/dxf",
        )

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "status": "ERROR",
                "message": "Erreur pendant la génération du DXF optimisé.",
                "detail": str(error),
            },
        )

@app.post("/foundation-strategy")
async def foundation_strategy(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
) -> JSONResponse:
    """
    Décide le système de fondation :
    semelles isolées, semelles excentrées, PR,
    semelles combinées, radier local ou radier général.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            model = read_dxf_model(dxf_path)

            report = decide_foundation_strategy(
                model=model,
                q_allowable_kPa=q_allowable_kPa,
            )

            return JSONResponse(report)

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant la décision du système de fondation.",
                    "detail": str(error),
                },
            )

@app.post("/foundation-strategy-dxf", response_model=None)
async def foundation_strategy_dxf(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
):
    """
    Génère le DXF de stratégie fondations :
    semelles isolées, semelles excentrées, PR,
    radiers locaux et radier général si recommandé.
    """
    temp_path = Path(tempfile.mkdtemp())
    dxf_path = save_uploaded_file(dxf, temp_path)

    try:
        model = read_dxf_model(dxf_path)

        strategy_report = decide_foundation_strategy(
            model=model,
            q_allowable_kPa=q_allowable_kPa,
        )

        strategy_report = fix_support_geometry_non_destructive(
            model=model,
            strategy_report=strategy_report,
            support_margin_m=0.05,
        )

        strategy_report = fix_support_geometry_non_destructive(
            model=model,
            strategy_report=strategy_report,
            support_margin_m=0.05,
        )

        output_path = temp_path / "FONDATIONS_STRATEGIE_INGENIERIE_COM.dxf"

        generate_foundation_strategy_dxf(
            model=model,
            strategy_report=strategy_report,
            output_path=output_path,
        )

        return FileResponse(
            path=output_path,
            filename="FONDATIONS_STRATEGIE_INGENIERIE_COM.dxf",
            media_type="application/dxf",
        )

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "status": "ERROR",
                "message": "Erreur pendant la génération du DXF de stratégie fondations.",
                "detail": str(error),
            },
        )


@app.post("/punching-prelim")
async def punching_prelim(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
    fck_mpa: float = Form(25.0),
    rho_l: float = Form(0.005),
    gamma_c: float = Form(1.50),
    cover_m: float = Form(0.05),
) -> JSONResponse:
    """
    Controle preliminaire du poinconnement pour les fondations finales :
    SI, SE, SC et RL.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            model = read_dxf_model(dxf_path)

            strategy_report = decide_foundation_strategy(
                model=model,
                q_allowable_kPa=q_allowable_kPa,
            )

            strategy_report = fix_support_geometry_non_destructive(
                model=model,
                strategy_report=strategy_report,
                support_margin_m=0.05,
            )

            strategy_report = fix_support_geometry_non_destructive(
                model=model,
                strategy_report=strategy_report,
                support_margin_m=0.05,
            )

            report = check_punching_prelim(
                model=model,
                strategy_report=strategy_report,
                fck_mpa=fck_mpa,
                rho_l=rho_l,
                gamma_c=gamma_c,
                cover_m=cover_m,
            )

            return JSONResponse(report)

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant le controle preliminaire du poinconnement.",
                    "detail": str(error),
                },
            )


@app.post("/punching-dxf", response_model=None)
async def punching_dxf(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
    fck_mpa: float = Form(25.0),
    rho_l: float = Form(0.005),
    gamma_c: float = Form(1.50),
    cover_m: float = Form(0.05),
):
    """
    Genere un DXF de controle preliminaire du poinconnement.
    """
    temp_path = Path(tempfile.mkdtemp())
    dxf_path = save_uploaded_file(dxf, temp_path)

    try:
        model = read_dxf_model(dxf_path)

        strategy_report = decide_foundation_strategy(
            model=model,
            q_allowable_kPa=q_allowable_kPa,
        )

        strategy_report = fix_support_geometry_non_destructive(
            model=model,
            strategy_report=strategy_report,
            support_margin_m=0.05,
        )

        strategy_report = fix_support_geometry_non_destructive(
            model=model,
            strategy_report=strategy_report,
            support_margin_m=0.05,
        )

        punching_report = check_punching_prelim(
            model=model,
            strategy_report=strategy_report,
            fck_mpa=fck_mpa,
            rho_l=rho_l,
            gamma_c=gamma_c,
            cover_m=cover_m,
        )

        output_path = temp_path / "POINCONNEMENT_PRELIM_INGENIERIE_COM.dxf"

        generate_punching_dxf(
            model=model,
            strategy_report=strategy_report,
            punching_report=punching_report,
            output_path=output_path,
        )

        return FileResponse(
            path=output_path,
            filename="POINCONNEMENT_PRELIM_INGENIERIE_COM.dxf",
            media_type="application/dxf",
        )

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "status": "ERROR",
                "message": "Erreur pendant la generation du DXF de poinconnement.",
                "detail": str(error),
            },
        )


@app.post("/reinforcement-prelim")
async def reinforcement_prelim(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
    fck_mpa: float = Form(25.0),
    fyk_mpa: float = Form(500.0),
    gamma_s: float = Form(1.15),
    cover_m: float = Form(0.05),
    phi_main_mm: float = Form(12.0),
) -> JSONResponse:
    """
    Predimensionnement du ferraillage des fondations finales :
    SI, SE, SC et RL.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            model = read_dxf_model(dxf_path)

            strategy_report = decide_foundation_strategy(
                model=model,
                q_allowable_kPa=q_allowable_kPa,
            )

            strategy_report = fix_support_geometry_non_destructive(
                model=model,
                strategy_report=strategy_report,
                support_margin_m=0.05,
            )

            strategy_report = fix_support_geometry_non_destructive(
                model=model,
                strategy_report=strategy_report,
                support_margin_m=0.05,
            )

            report = design_reinforcement_prelim(
                model=model,
                strategy_report=strategy_report,
                fck_mpa=fck_mpa,
                fyk_mpa=fyk_mpa,
                gamma_s=gamma_s,
                cover_m=cover_m,
                phi_main_mm=phi_main_mm,
            )

            return JSONResponse(report)

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant le predimensionnement du ferraillage.",
                    "detail": str(error),
                },
            )


@app.post("/reinforcement-dxf", response_model=None)
async def reinforcement_dxf(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
    fck_mpa: float = Form(25.0),
    fyk_mpa: float = Form(500.0),
    gamma_s: float = Form(1.15),
    cover_m: float = Form(0.05),
    phi_main_mm: float = Form(12.0),
):
    """
    Genere un DXF de ferraillage preliminaire des fondations finales.
    """
    temp_path = Path(tempfile.mkdtemp())
    dxf_path = save_uploaded_file(dxf, temp_path)

    try:
        model = read_dxf_model(dxf_path)

        strategy_report = decide_foundation_strategy(
            model=model,
            q_allowable_kPa=q_allowable_kPa,
        )

        strategy_report = fix_support_geometry_non_destructive(
            model=model,
            strategy_report=strategy_report,
            support_margin_m=0.05,
        )

        strategy_report = fix_support_geometry_non_destructive(
            model=model,
            strategy_report=strategy_report,
            support_margin_m=0.05,
        )

        reinforcement_report = design_reinforcement_prelim(
            model=model,
            strategy_report=strategy_report,
            fck_mpa=fck_mpa,
            fyk_mpa=fyk_mpa,
            gamma_s=gamma_s,
            cover_m=cover_m,
            phi_main_mm=phi_main_mm,
        )

        output_path = temp_path / "FERRAILLAGE_PRELIM_INGENIERIE_COM.dxf"

        generate_reinforcement_dxf(
            model=model,
            strategy_report=strategy_report,
            reinforcement_report=reinforcement_report,
            output_path=output_path,
        )

        return FileResponse(
            path=output_path,
            filename="FERRAILLAGE_PRELIM_INGENIERIE_COM.dxf",
            media_type="application/dxf",
        )

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "status": "ERROR",
                "message": "Erreur pendant la generation du DXF de ferraillage.",
                "detail": str(error),
            },
        )


@app.post("/starter-bars-dxf", response_model=None)
async def starter_bars_dxf(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
    starter_diameter_mm: float = Form(14.0),
):
    """
    Genere un DXF des attentes poteaux et des coupes types SI/SE/SC/RL.
    """
    temp_path = Path(tempfile.mkdtemp())
    dxf_path = save_uploaded_file(dxf, temp_path)

    try:
        model = read_dxf_model(dxf_path)

        strategy_report = decide_foundation_strategy(
            model=model,
            q_allowable_kPa=q_allowable_kPa,
        )

        strategy_report = fix_support_geometry_non_destructive(
            model=model,
            strategy_report=strategy_report,
            support_margin_m=0.05,
        )

        output_path = temp_path / "ATTENTES_POTEAUX_INGENIERIE_COM.dxf"

        generate_starter_bars_dxf(
            model=model,
            strategy_report=strategy_report,
            output_path=output_path,
            starter_diameter_mm=starter_diameter_mm,
        )

        return FileResponse(
            path=output_path,
            filename="ATTENTES_POTEAUX_INGENIERIE_COM.dxf",
            media_type="application/dxf",
        )

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "status": "ERROR",
                "message": "Erreur pendant la generation du DXF des attentes poteaux.",
                "detail": str(error),
            },
        )


@app.post("/reinforcement-final-check")
async def reinforcement_final_check(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
    fck_mpa: float = Form(25.0),
    fyk_mpa: float = Form(500.0),
    gamma_s: float = Form(1.15),
    cover_m: float = Form(0.05),
    phi_main_mm: float = Form(12.0),
    max_spacing_m: float = Form(0.20),
    min_diameter_mm: float = Form(10.0),
) -> JSONResponse:
    """
    Verification finale de coherence du ferraillage propose :
    As fourni, As requis, espacement, diametre minimal et rho reel.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            model = read_dxf_model(dxf_path)

            strategy_report = decide_foundation_strategy(
                model=model,
                q_allowable_kPa=q_allowable_kPa,
            )

            strategy_report = fix_support_geometry_non_destructive(
                model=model,
                strategy_report=strategy_report,
                support_margin_m=0.05,
            )

            reinforcement_report = design_reinforcement_prelim(
                model=model,
                strategy_report=strategy_report,
                fck_mpa=fck_mpa,
                fyk_mpa=fyk_mpa,
                gamma_s=gamma_s,
                cover_m=cover_m,
                phi_main_mm=phi_main_mm,
            )

            report = check_reinforcement_final(
                reinforcement_report=reinforcement_report,
                max_spacing_m=max_spacing_m,
                min_diameter_mm=min_diameter_mm,
            )

            return JSONResponse(report)

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant la verification finale du ferraillage.",
                    "detail": str(error),
                },
            )


@app.post("/punching-final")
async def punching_final(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
    fck_mpa: float = Form(25.0),
    fyk_mpa: float = Form(500.0),
    gamma_s: float = Form(1.15),
    gamma_c: float = Form(1.50),
    cover_m: float = Form(0.05),
    phi_main_mm: float = Form(12.0),
    max_spacing_m: float = Form(0.20),
    min_diameter_mm: float = Form(10.0),
) -> JSONResponse:
    """
    Verification finale du poinconnement avec rho_l reel issu du ferraillage.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            model = read_dxf_model(dxf_path)

            strategy_report = decide_foundation_strategy(
                model=model,
                q_allowable_kPa=q_allowable_kPa,
            )

            strategy_report = fix_support_geometry_non_destructive(
                model=model,
                strategy_report=strategy_report,
                support_margin_m=0.05,
            )

            reinforcement_report = design_reinforcement_prelim(
                model=model,
                strategy_report=strategy_report,
                fck_mpa=fck_mpa,
                fyk_mpa=fyk_mpa,
                gamma_s=gamma_s,
                cover_m=cover_m,
                phi_main_mm=phi_main_mm,
            )

            reinforcement_final_report = check_reinforcement_final(
                reinforcement_report=reinforcement_report,
                max_spacing_m=max_spacing_m,
                min_diameter_mm=min_diameter_mm,
            )

            report = check_punching_final(
                model=model,
                strategy_report=strategy_report,
                reinforcement_final_report=reinforcement_final_report,
                fck_mpa=fck_mpa,
                gamma_c=gamma_c,
                cover_m=cover_m,
            )

            report["reinforcement_final_status"] = reinforcement_final_report.get("status")
            report["reinforcement_final_summary"] = reinforcement_final_report.get("summary")

            return JSONResponse(report)

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant la verification finale du poinconnement.",
                    "detail": str(error),
                },
            )


@app.post("/anchorage-details")
async def anchorage_details(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
    starter_diameter_mm: float = Form(14.0),
    stirrup_diameter_mm: float = Form(8.0),
    cover_m: float = Form(0.05),
    lbd_factor_phi: float = Form(50.0),
    lap_factor_phi: float = Form(60.0),
    hook_factor_phi: float = Form(15.0),
) -> JSONResponse:
    """
    Calcule les longueurs indicatives d'ancrage et de recouvrement des attentes poteaux.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            model = read_dxf_model(dxf_path)

            strategy_report = decide_foundation_strategy(
                model=model,
                q_allowable_kPa=q_allowable_kPa,
            )

            strategy_report = fix_support_geometry_non_destructive(
                model=model,
                strategy_report=strategy_report,
                support_margin_m=0.05,
            )

            report = build_anchorage_details(
                model=model,
                strategy_report=strategy_report,
                starter_diameter_mm=starter_diameter_mm,
                stirrup_diameter_mm=stirrup_diameter_mm,
                cover_m=cover_m,
                lbd_factor_phi=lbd_factor_phi,
                lap_factor_phi=lap_factor_phi,
                hook_factor_phi=hook_factor_phi,
            )

            return JSONResponse(report)

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant le calcul des ancrages.",
                    "detail": str(error),
                },
            )


@app.post("/anchorage-details-dxf", response_model=None)
async def anchorage_details_dxf(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
    starter_diameter_mm: float = Form(14.0),
    stirrup_diameter_mm: float = Form(8.0),
    cover_m: float = Form(0.05),
    lbd_factor_phi: float = Form(50.0),
    lap_factor_phi: float = Form(60.0),
    hook_factor_phi: float = Form(15.0),
):
    """
    Genere un DXF des ancrages, recouvrements et formes d'attentes.
    """
    temp_path = Path(tempfile.mkdtemp())
    dxf_path = save_uploaded_file(dxf, temp_path)

    try:
        model = read_dxf_model(dxf_path)

        strategy_report = decide_foundation_strategy(
            model=model,
            q_allowable_kPa=q_allowable_kPa,
        )

        strategy_report = fix_support_geometry_non_destructive(
            model=model,
            strategy_report=strategy_report,
            support_margin_m=0.05,
        )

        anchorage_report = build_anchorage_details(
            model=model,
            strategy_report=strategy_report,
            starter_diameter_mm=starter_diameter_mm,
            stirrup_diameter_mm=stirrup_diameter_mm,
            cover_m=cover_m,
            lbd_factor_phi=lbd_factor_phi,
            lap_factor_phi=lap_factor_phi,
            hook_factor_phi=hook_factor_phi,
        )

        output_path = temp_path / "ANCRAGES_RECOUVREMENTS_INGENIERIE_COM.dxf"

        generate_anchorage_details_dxf(
            model=model,
            strategy_report=strategy_report,
            anchorage_report=anchorage_report,
            output_path=output_path,
        )

        return FileResponse(
            path=output_path,
            filename="ANCRAGES_RECOUVREMENTS_INGENIERIE_COM.dxf",
            media_type="application/dxf",
        )

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "status": "ERROR",
                "message": "Erreur pendant la generation du DXF des ancrages.",
                "detail": str(error),
            },
        )


@app.post("/foundation-sections-dxf", response_model=None)
async def foundation_sections_dxf(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
    fck_mpa: float = Form(25.0),
    fyk_mpa: float = Form(500.0),
    gamma_s: float = Form(1.15),
    cover_m: float = Form(0.05),
    clean_concrete_m: float = Form(0.10),
    phi_main_mm: float = Form(12.0),
    starter_diameter_mm: float = Form(14.0),
    stirrup_diameter_mm: float = Form(8.0),
    stirrup_spacing_cm: float = Form(15.0),
    stirrup_secondary_spacing_cm: float = Form(20.0),
    critical_zone_m: float = Form(0.60),
):
    """
    Genere un DXF de coupes detaillees SI / SE / SC / RL.
    """
    temp_path = Path(tempfile.mkdtemp())
    dxf_path = save_uploaded_file(dxf, temp_path)

    try:
        model = read_dxf_model(dxf_path)

        strategy_report = decide_foundation_strategy(
            model=model,
            q_allowable_kPa=q_allowable_kPa,
        )

        strategy_report = fix_support_geometry_non_destructive(
            model=model,
            strategy_report=strategy_report,
            support_margin_m=0.05,
        )

        reinforcement_report = design_reinforcement_prelim(
            model=model,
            strategy_report=strategy_report,
            fck_mpa=fck_mpa,
            fyk_mpa=fyk_mpa,
            gamma_s=gamma_s,
            cover_m=cover_m,
            phi_main_mm=phi_main_mm,
        )

        anchorage_report = build_anchorage_details(
            model=model,
            strategy_report=strategy_report,
            starter_diameter_mm=starter_diameter_mm,
            stirrup_diameter_mm=stirrup_diameter_mm,
            cover_m=cover_m,
        )

        output_path = temp_path / "COUPES_DETAILLEES_FONDATIONS_INGENIERIE_COM.dxf"

        generate_foundation_sections_dxf(
            model=model,
            strategy_report=strategy_report,
            reinforcement_report=reinforcement_report,
            anchorage_report=anchorage_report,
            output_path=output_path,
            cover_m=cover_m,
            clean_concrete_m=clean_concrete_m,
            starter_diameter_mm=starter_diameter_mm,
            stirrup_diameter_mm=stirrup_diameter_mm,
            stirrup_spacing_cm=stirrup_spacing_cm,
            stirrup_secondary_spacing_cm=stirrup_secondary_spacing_cm,
            critical_zone_m=critical_zone_m,
        )

        return FileResponse(
            path=output_path,
            filename="COUPES_DETAILLEES_FONDATIONS_INGENIERIE_COM.dxf",
            media_type="application/dxf",
        )

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "status": "ERROR",
                "message": "Erreur pendant la generation du DXF des coupes detaillees.",
                "detail": str(error),
            },
        )


@app.post("/execution-foundation-dxf", response_model=None)
async def execution_foundation_dxf(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
    fck_mpa: float = Form(25.0),
    fyk_mpa: float = Form(500.0),
    gamma_s: float = Form(1.15),
    cover_m: float = Form(0.05),
    phi_main_mm: float = Form(12.0),
    starter_diameter_mm: float = Form(14.0),
    stirrup_diameter_mm: float = Form(8.0),
    wall_thickness_m: float = Form(0.20),
    storey_height_m: float = Form(3.00),
    g_floor_kN_m2: float = Form(5.00),
    q_floor_kN_m2: float = Form(1.50),
    g_terrace_kN_m2: float = Form(6.00),
    q_terrace_kN_m2: float = Form(1.00),
    project_name: str = Form("INGENIERIE.COM - Projet fondations"),
    project_number: str = Form(""),
    plan_date: str = Form(""),
    scale_label: str = Form("1/50"),
):
    """
    Genere le plan final d'execution fondations :
    fondations finales, axes, ferraillage principal, attentes, tableaux, notes et cartouche.
    """
    temp_path = Path(tempfile.mkdtemp())
    dxf_path = save_uploaded_file(dxf, temp_path)

    try:
        model = read_dxf_model(dxf_path)

        strategy_report = decide_foundation_strategy(
            model=model,
            q_allowable_kPa=q_allowable_kPa,
        )

        strategy_report = fix_support_geometry_non_destructive(
            model=model,
            strategy_report=strategy_report,
            support_margin_m=0.05,
        )

        reinforcement_report = design_reinforcement_prelim(
            model=model,
            strategy_report=strategy_report,
            fck_mpa=fck_mpa,
            fyk_mpa=fyk_mpa,
            gamma_s=gamma_s,
            cover_m=cover_m,
            phi_main_mm=phi_main_mm,
        )

        anchorage_report = build_anchorage_details(
            model=model,
            strategy_report=strategy_report,
            starter_diameter_mm=starter_diameter_mm,
            stirrup_diameter_mm=stirrup_diameter_mm,
            cover_m=cover_m,
        )

        output_path = temp_path / "PLAN_EXECUTION_FONDATIONS_INGENIERIE_COM.dxf"

        # Calcul des semelles filantes sous voiles (si voiles presents)
        strip_design = None
        strip_interference = None
        try:
            wlt = compute_wall_load_takedown(
                model=model, wall_thickness_m=wall_thickness_m, storey_height_m=storey_height_m,
                g_floor_kN_m2=g_floor_kN_m2, q_floor_kN_m2=q_floor_kN_m2,
                g_terrace_kN_m2=g_terrace_kN_m2, q_terrace_kN_m2=q_terrace_kN_m2,
                gamma_g=1.35, gamma_q=1.50)
            walls_data = wlt.get("walls", [])
            if walls_data:
                fond = next((l for l in model["levels"] if l["name"] == "FONDATION"),
                            model["levels"][0] if model["levels"] else None)
                if fond and fond.get("footprints"):
                    emp = fond["footprints"][0]["bbox"]
                    emprise = StripRect(emp["xmin"], emp["ymin"], emp["xmax"], emp["ymax"])
                    walls = [StripWallInput(
                        id=w["id"], x1=w["x1"], y1=w["y1"], x2=w["x2"], y2=w["y2"],
                        thickness_m=w["thickness_m"], n_sls_kN_per_m=w["n_sls_kN_per_m"],
                        n_uls_kN_per_m=w["n_uls_kN_per_m"]) for w in walls_data]
                    strip_design = design_strip_footings_under_walls(
                        walls=walls, emprise=emprise, q_allowable_kPa=q_allowable_kPa,
                        fck_mpa=fck_mpa, fyk_mpa=fyk_mpa, gamma_s=gamma_s, cover_m=cover_m,
                        phi_main_mm=phi_main_mm, phi_distribution_mm=10.0)
        except Exception:
            strip_design = None  # le plan reste valide sans filantes

        generate_execution_foundation_dxf(
            model=model,
            strategy_report=strategy_report,
            reinforcement_report=reinforcement_report,
            anchorage_report=anchorage_report,
            output_path=output_path,
            starter_diameter_mm=starter_diameter_mm,
            project_name=project_name,
            project_number=project_number,
            plan_date=plan_date,
            scale_label=scale_label,
            strip_design=strip_design,
            strip_interference=strip_interference,
            strip_wall_thickness_m=wall_thickness_m,
        )

        return FileResponse(
            path=output_path,
            filename="PLAN_EXECUTION_FONDATIONS_INGENIERIE_COM.dxf",
            media_type="application/dxf",
        )

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "status": "ERROR",
                "message": "Erreur pendant la generation du plan final d'execution.",
                "detail": str(error),
            },
        )


@app.post("/boq-foundations")
async def boq_foundations(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
    fck_mpa: float = Form(25.0),
    fyk_mpa: float = Form(500.0),
    gamma_s: float = Form(1.15),
    cover_m: float = Form(0.05),
    phi_main_mm: float = Form(12.0),
    starter_diameter_mm: float = Form(14.0),
    stirrup_diameter_mm: float = Form(8.0),
    clean_concrete_m: float = Form(0.10),
) -> JSONResponse:
    """
    Metre estimatif beton / acier / coffrage des fondations.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            model = read_dxf_model(dxf_path)

            strategy_report = decide_foundation_strategy(
                model=model,
                q_allowable_kPa=q_allowable_kPa,
            )

            strategy_report = fix_support_geometry_non_destructive(
                model=model,
                strategy_report=strategy_report,
                support_margin_m=0.05,
            )

            reinforcement_report = design_reinforcement_prelim(
                model=model,
                strategy_report=strategy_report,
                fck_mpa=fck_mpa,
                fyk_mpa=fyk_mpa,
                gamma_s=gamma_s,
                cover_m=cover_m,
                phi_main_mm=phi_main_mm,
            )

            anchorage_report = build_anchorage_details(
                model=model,
                strategy_report=strategy_report,
                starter_diameter_mm=starter_diameter_mm,
                stirrup_diameter_mm=stirrup_diameter_mm,
                cover_m=cover_m,
            )

            report = build_foundation_boq(
                strategy_report=strategy_report,
                reinforcement_report=reinforcement_report,
                anchorage_report=anchorage_report,
                clean_concrete_m=clean_concrete_m,
                model=model,
            )

            return JSONResponse(report)

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant le calcul du metre fondations.",
                    "detail": str(error),
                },
            )


@app.post("/boq-foundations-csv", response_model=None)
async def boq_foundations_csv(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
    fck_mpa: float = Form(25.0),
    fyk_mpa: float = Form(500.0),
    gamma_s: float = Form(1.15),
    cover_m: float = Form(0.05),
    phi_main_mm: float = Form(12.0),
    starter_diameter_mm: float = Form(14.0),
    stirrup_diameter_mm: float = Form(8.0),
    clean_concrete_m: float = Form(0.10),
):
    """
    Export CSV du metre estimatif beton / acier / coffrage.
    """
    temp_path = Path(tempfile.mkdtemp())
    dxf_path = save_uploaded_file(dxf, temp_path)

    try:
        model = read_dxf_model(dxf_path)

        strategy_report = decide_foundation_strategy(
            model=model,
            q_allowable_kPa=q_allowable_kPa,
        )

        strategy_report = fix_support_geometry_non_destructive(
            model=model,
            strategy_report=strategy_report,
            support_margin_m=0.05,
        )

        reinforcement_report = design_reinforcement_prelim(
            model=model,
            strategy_report=strategy_report,
            fck_mpa=fck_mpa,
            fyk_mpa=fyk_mpa,
            gamma_s=gamma_s,
            cover_m=cover_m,
            phi_main_mm=phi_main_mm,
        )

        anchorage_report = build_anchorage_details(
            model=model,
            strategy_report=strategy_report,
            starter_diameter_mm=starter_diameter_mm,
            stirrup_diameter_mm=stirrup_diameter_mm,
            cover_m=cover_m,
        )

        report = build_foundation_boq(
            strategy_report=strategy_report,
            reinforcement_report=reinforcement_report,
            anchorage_report=anchorage_report,
            clean_concrete_m=clean_concrete_m,
            model=model,
        )

        output_path = temp_path / "METRE_FONDATIONS_INGENIERIE_COM.csv"

        export_boq_csv(
            boq_report=report,
            output_path=output_path,
        )

        return FileResponse(
            path=output_path,
            filename="METRE_FONDATIONS_INGENIERIE_COM.csv",
            media_type="text/csv",
        )

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "status": "ERROR",
                "message": "Erreur pendant l'export CSV du metre fondations.",
                "detail": str(error),
            },
        )


@app.post("/calculation-report")
async def calculation_report(
    dxf: UploadFile = File(...),
    project_name: str = Form("INGENIERIE.COM - Projet fondations"),
    q_allowable_kPa: float = Form(200.0),
    fck_mpa: float = Form(25.0),
    fyk_mpa: float = Form(500.0),
    gamma_s: float = Form(1.15),
    gamma_c: float = Form(1.50),
    cover_m: float = Form(0.05),
    clean_concrete_m: float = Form(0.10),
    phi_main_mm: float = Form(12.0),
    starter_diameter_mm: float = Form(14.0),
    stirrup_diameter_mm: float = Form(8.0),
    max_spacing_m: float = Form(0.20),
    min_diameter_mm: float = Form(10.0),
) -> JSONResponse:
    """
    Genere la note de calcul automatique en JSON.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            model = read_dxf_model(dxf_path)

            strategy_report = decide_foundation_strategy(
                model=model,
                q_allowable_kPa=q_allowable_kPa,
            )

            strategy_report = fix_support_geometry_non_destructive(
                model=model,
                strategy_report=strategy_report,
                support_margin_m=0.05,
            )

            reinforcement_report = design_reinforcement_prelim(
                model=model,
                strategy_report=strategy_report,
                fck_mpa=fck_mpa,
                fyk_mpa=fyk_mpa,
                gamma_s=gamma_s,
                cover_m=cover_m,
                phi_main_mm=phi_main_mm,
            )

            reinforcement_final_report = check_reinforcement_final(
                reinforcement_report=reinforcement_report,
                max_spacing_m=max_spacing_m,
                min_diameter_mm=min_diameter_mm,
            )

            punching_final_report = check_punching_final(
                model=model,
                strategy_report=strategy_report,
                reinforcement_final_report=reinforcement_final_report,
                fck_mpa=fck_mpa,
                gamma_c=gamma_c,
                cover_m=cover_m,
            )

            anchorage_report = build_anchorage_details(
                model=model,
                strategy_report=strategy_report,
                starter_diameter_mm=starter_diameter_mm,
                stirrup_diameter_mm=stirrup_diameter_mm,
                cover_m=cover_m,
            )

            anchorage_report, anchorage_corrections = secure_anchorage_execution_solution(
                anchorage_report=anchorage_report,
            )

            boq_report = build_foundation_boq(
                strategy_report=strategy_report,
                reinforcement_report=reinforcement_report,
                anchorage_report=anchorage_report,
                clean_concrete_m=clean_concrete_m,
                model=model,
            )

            hypotheses = {
                "project_name": project_name,
                "q_allowable_kPa": q_allowable_kPa,
                "fck_mpa": fck_mpa,
                "fyk_mpa": fyk_mpa,
                "gamma_s": gamma_s,
                "gamma_c": gamma_c,
                "cover_m": cover_m,
                "clean_concrete_m": clean_concrete_m,
                "phi_main_mm": phi_main_mm,
                "starter_diameter_mm": starter_diameter_mm,
                "stirrup_diameter_mm": stirrup_diameter_mm,
                "max_spacing_m": max_spacing_m,
                "min_diameter_mm": min_diameter_mm,
            }

            report = build_foundation_calculation_report(
                model=model,
                strategy_report=strategy_report,
                reinforcement_report=reinforcement_report,
                reinforcement_final_report=reinforcement_final_report,
                punching_final_report=punching_final_report,
                anchorage_report=anchorage_report,
                boq_report=boq_report,
                hypotheses=hypotheses,
            )

            return JSONResponse(report)

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant la generation de la note de calcul.",
                    "detail": str(error),
                },
            )


@app.post("/calculation-report-md", response_model=None)
async def calculation_report_md(
    dxf: UploadFile = File(...),
    project_name: str = Form("INGENIERIE.COM - Projet fondations"),
    q_allowable_kPa: float = Form(200.0),
    fck_mpa: float = Form(25.0),
    fyk_mpa: float = Form(500.0),
    gamma_s: float = Form(1.15),
    gamma_c: float = Form(1.50),
    cover_m: float = Form(0.05),
    clean_concrete_m: float = Form(0.10),
    phi_main_mm: float = Form(12.0),
    starter_diameter_mm: float = Form(14.0),
    stirrup_diameter_mm: float = Form(8.0),
    max_spacing_m: float = Form(0.20),
    min_diameter_mm: float = Form(10.0),
):
    """
    Exporte la note de calcul automatique en Markdown.
    """
    temp_path = Path(tempfile.mkdtemp())
    dxf_path = save_uploaded_file(dxf, temp_path)

    try:
        model = read_dxf_model(dxf_path)

        strategy_report = decide_foundation_strategy(
            model=model,
            q_allowable_kPa=q_allowable_kPa,
        )

        strategy_report = fix_support_geometry_non_destructive(
            model=model,
            strategy_report=strategy_report,
            support_margin_m=0.05,
        )

        reinforcement_report = design_reinforcement_prelim(
            model=model,
            strategy_report=strategy_report,
            fck_mpa=fck_mpa,
            fyk_mpa=fyk_mpa,
            gamma_s=gamma_s,
            cover_m=cover_m,
            phi_main_mm=phi_main_mm,
        )

        reinforcement_final_report = check_reinforcement_final(
            reinforcement_report=reinforcement_report,
            max_spacing_m=max_spacing_m,
            min_diameter_mm=min_diameter_mm,
        )

        punching_final_report = check_punching_final(
            model=model,
            strategy_report=strategy_report,
            reinforcement_final_report=reinforcement_final_report,
            fck_mpa=fck_mpa,
            gamma_c=gamma_c,
            cover_m=cover_m,
        )

        anchorage_report = build_anchorage_details(
            model=model,
            strategy_report=strategy_report,
            starter_diameter_mm=starter_diameter_mm,
            stirrup_diameter_mm=stirrup_diameter_mm,
            cover_m=cover_m,
        )

        boq_report = build_foundation_boq(
            strategy_report=strategy_report,
            reinforcement_report=reinforcement_report,
            anchorage_report=anchorage_report,
            clean_concrete_m=clean_concrete_m,
            model=model,
        )

        hypotheses = {
            "project_name": project_name,
            "q_allowable_kPa": q_allowable_kPa,
            "fck_mpa": fck_mpa,
            "fyk_mpa": fyk_mpa,
            "gamma_s": gamma_s,
            "gamma_c": gamma_c,
            "cover_m": cover_m,
            "clean_concrete_m": clean_concrete_m,
            "phi_main_mm": phi_main_mm,
            "starter_diameter_mm": starter_diameter_mm,
            "stirrup_diameter_mm": stirrup_diameter_mm,
            "max_spacing_m": max_spacing_m,
            "min_diameter_mm": min_diameter_mm,
        }

        report = build_foundation_calculation_report(
            model=model,
            strategy_report=strategy_report,
            reinforcement_report=reinforcement_report,
            reinforcement_final_report=reinforcement_final_report,
            punching_final_report=punching_final_report,
            anchorage_report=anchorage_report,
            boq_report=boq_report,
            hypotheses=hypotheses,
        )

        output_path = temp_path / "NOTE_CALCUL_FONDATIONS_INGENIERIE_COM.md"

        export_calculation_report_md(
            report=report,
            output_path=output_path,
        )

        return FileResponse(
            path=output_path,
            filename="NOTE_CALCUL_FONDATIONS_INGENIERIE_COM.md",
            media_type="text/markdown",
        )

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "status": "ERROR",
                "message": "Erreur pendant l'export Markdown de la note de calcul.",
                "detail": str(error),
            },
        )


@app.post("/calculation-report-docx", response_model=None)
async def calculation_report_docx(
    dxf: UploadFile = File(...),
    project_name: str = Form("INGENIERIE.COM - Projet fondations"),
    q_allowable_kPa: float = Form(200.0),
    fck_mpa: float = Form(25.0),
    fyk_mpa: float = Form(500.0),
    gamma_s: float = Form(1.15),
    gamma_c: float = Form(1.50),
    cover_m: float = Form(0.05),
    clean_concrete_m: float = Form(0.10),
    phi_main_mm: float = Form(12.0),
    starter_diameter_mm: float = Form(14.0),
    stirrup_diameter_mm: float = Form(8.0),
    max_spacing_m: float = Form(0.20),
    min_diameter_mm: float = Form(10.0),
):
    """
    Exporte la note de calcul automatique en DOCX.
    """
    temp_path = Path(tempfile.mkdtemp())
    dxf_path = save_uploaded_file(dxf, temp_path)

    try:
        model = read_dxf_model(dxf_path)

        strategy_report = decide_foundation_strategy(
            model=model,
            q_allowable_kPa=q_allowable_kPa,
        )

        strategy_report = fix_support_geometry_non_destructive(
            model=model,
            strategy_report=strategy_report,
            support_margin_m=0.05,
        )

        reinforcement_report = design_reinforcement_prelim(
            model=model,
            strategy_report=strategy_report,
            fck_mpa=fck_mpa,
            fyk_mpa=fyk_mpa,
            gamma_s=gamma_s,
            cover_m=cover_m,
            phi_main_mm=phi_main_mm,
        )

        reinforcement_final_report = check_reinforcement_final(
            reinforcement_report=reinforcement_report,
            max_spacing_m=max_spacing_m,
            min_diameter_mm=min_diameter_mm,
        )

        punching_final_report = check_punching_final(
            model=model,
            strategy_report=strategy_report,
            reinforcement_final_report=reinforcement_final_report,
            fck_mpa=fck_mpa,
            gamma_c=gamma_c,
            cover_m=cover_m,
        )

        anchorage_report = build_anchorage_details(
            model=model,
            strategy_report=strategy_report,
            starter_diameter_mm=starter_diameter_mm,
            stirrup_diameter_mm=stirrup_diameter_mm,
            cover_m=cover_m,
        )

        boq_report = build_foundation_boq(
            strategy_report=strategy_report,
            reinforcement_report=reinforcement_report,
            anchorage_report=anchorage_report,
            clean_concrete_m=clean_concrete_m,
            model=model,
        )

        hypotheses = {
            "project_name": project_name,
            "q_allowable_kPa": q_allowable_kPa,
            "fck_mpa": fck_mpa,
            "fyk_mpa": fyk_mpa,
            "gamma_s": gamma_s,
            "gamma_c": gamma_c,
            "cover_m": cover_m,
            "clean_concrete_m": clean_concrete_m,
            "phi_main_mm": phi_main_mm,
            "starter_diameter_mm": starter_diameter_mm,
            "stirrup_diameter_mm": stirrup_diameter_mm,
            "max_spacing_m": max_spacing_m,
            "min_diameter_mm": min_diameter_mm,
        }

        report = build_foundation_calculation_report(
            model=model,
            strategy_report=strategy_report,
            reinforcement_report=reinforcement_report,
            reinforcement_final_report=reinforcement_final_report,
            punching_final_report=punching_final_report,
            anchorage_report=anchorage_report,
            boq_report=boq_report,
            hypotheses=hypotheses,
        )

        output_path = temp_path / "NOTE_CALCUL_FONDATIONS_INGENIERIE_COM.docx"

        export_calculation_report_docx(
            report=report,
            output_path=output_path,
        )

        return FileResponse(
            path=output_path,
            filename="NOTE_CALCUL_FONDATIONS_INGENIERIE_COM.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "status": "ERROR",
                "message": "Erreur pendant l'export DOCX de la note de calcul.",
                "detail": str(error),
            },
        )


@app.post("/calculation-report-pdf", response_model=None)
async def calculation_report_pdf(
    dxf: UploadFile = File(...),
    project_name: str = Form("INGENIERIE.COM - Projet fondations"),
    q_allowable_kPa: float = Form(200.0),
    fck_mpa: float = Form(25.0),
    fyk_mpa: float = Form(500.0),
    gamma_s: float = Form(1.15),
    gamma_c: float = Form(1.50),
    cover_m: float = Form(0.05),
    clean_concrete_m: float = Form(0.10),
    phi_main_mm: float = Form(12.0),
    starter_diameter_mm: float = Form(14.0),
    stirrup_diameter_mm: float = Form(8.0),
    max_spacing_m: float = Form(0.20),
    min_diameter_mm: float = Form(10.0),
):
    """
    Exporte la note de calcul automatique en PDF.
    """
    temp_path = Path(tempfile.mkdtemp())
    dxf_path = save_uploaded_file(dxf, temp_path)

    try:
        model = read_dxf_model(dxf_path)

        strategy_report = decide_foundation_strategy(
            model=model,
            q_allowable_kPa=q_allowable_kPa,
        )

        strategy_report = fix_support_geometry_non_destructive(
            model=model,
            strategy_report=strategy_report,
            support_margin_m=0.05,
        )

        reinforcement_report = design_reinforcement_prelim(
            model=model,
            strategy_report=strategy_report,
            fck_mpa=fck_mpa,
            fyk_mpa=fyk_mpa,
            gamma_s=gamma_s,
            cover_m=cover_m,
            phi_main_mm=phi_main_mm,
        )

        reinforcement_final_report = check_reinforcement_final(
            reinforcement_report=reinforcement_report,
            max_spacing_m=max_spacing_m,
            min_diameter_mm=min_diameter_mm,
        )

        punching_final_report = check_punching_final(
            model=model,
            strategy_report=strategy_report,
            reinforcement_final_report=reinforcement_final_report,
            fck_mpa=fck_mpa,
            gamma_c=gamma_c,
            cover_m=cover_m,
        )

        anchorage_report = build_anchorage_details(
            model=model,
            strategy_report=strategy_report,
            starter_diameter_mm=starter_diameter_mm,
            stirrup_diameter_mm=stirrup_diameter_mm,
            cover_m=cover_m,
        )

        boq_report = build_foundation_boq(
            strategy_report=strategy_report,
            reinforcement_report=reinforcement_report,
            anchorage_report=anchorage_report,
            clean_concrete_m=clean_concrete_m,
            model=model,
        )

        hypotheses = {
            "project_name": project_name,
            "q_allowable_kPa": q_allowable_kPa,
            "fck_mpa": fck_mpa,
            "fyk_mpa": fyk_mpa,
            "gamma_s": gamma_s,
            "gamma_c": gamma_c,
            "cover_m": cover_m,
            "clean_concrete_m": clean_concrete_m,
            "phi_main_mm": phi_main_mm,
            "starter_diameter_mm": starter_diameter_mm,
            "stirrup_diameter_mm": stirrup_diameter_mm,
            "max_spacing_m": max_spacing_m,
            "min_diameter_mm": min_diameter_mm,
        }

        report = build_foundation_calculation_report(
            model=model,
            strategy_report=strategy_report,
            reinforcement_report=reinforcement_report,
            reinforcement_final_report=reinforcement_final_report,
            punching_final_report=punching_final_report,
            anchorage_report=anchorage_report,
            boq_report=boq_report,
            hypotheses=hypotheses,
        )

        output_path = temp_path / "NOTE_CALCUL_FONDATIONS_INGENIERIE_COM.pdf"

        export_calculation_report_pdf(
            report=report,
            output_path=output_path,
        )

        return FileResponse(
            path=output_path,
            filename="NOTE_CALCUL_FONDATIONS_INGENIERIE_COM.pdf",
            media_type="application/pdf",
        )

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "status": "ERROR",
                "message": "Erreur pendant l'export PDF de la note de calcul.",
                "detail": str(error),
            },
        )


@app.post("/project-package-zip", response_model=None)
async def project_package_zip(
    dxf: UploadFile = File(...),
    project_name: str = Form("INGENIERIE.COM - Projet fondations"),
    q_allowable_kPa: float = Form(200.0),
    fck_mpa: float = Form(25.0),
    fyk_mpa: float = Form(500.0),
    gamma_s: float = Form(1.15),
    gamma_c: float = Form(1.50),
    cover_m: float = Form(0.05),
    clean_concrete_m: float = Form(0.10),
    phi_main_mm: float = Form(12.0),
    starter_diameter_mm: float = Form(14.0),
    stirrup_diameter_mm: float = Form(8.0),
    stirrup_spacing_cm: float = Form(15.0),
    stirrup_secondary_spacing_cm: float = Form(20.0),
    critical_zone_m: float = Form(0.60),
    max_spacing_m: float = Form(0.20),
    min_diameter_mm: float = Form(10.0),
    backfill_kN_m2: float = Form(0.0),
    g_floor_kN_m2: float = Form(5.0),
    q_floor_kN_m2: float = Form(1.5),
    g_terrace_kN_m2: float = Form(6.0),
    q_terrace_kN_m2: float = Form(1.0),
    wall_thickness_m: float = Form(0.20),
    storey_height_m: float = Form(3.00),
):
    """
    Genere un dossier ZIP complet base sur la configuration corrigee :
    DXF + rapports + metrage + JSON.
    """
    temp_path = Path(tempfile.mkdtemp())
    dxf_path = save_uploaded_file(dxf, temp_path)

    try:
        model = read_dxf_model(dxf_path)

        strategy_report = decide_foundation_strategy(
            model=model,
            q_allowable_kPa=q_allowable_kPa,
            backfill_kN_m2=backfill_kN_m2,
            g_floor_kN_m2=g_floor_kN_m2,
            q_floor_kN_m2=q_floor_kN_m2,
            g_terrace_kN_m2=g_terrace_kN_m2,
            q_terrace_kN_m2=q_terrace_kN_m2,
        )

        strategy_report = fix_support_geometry_non_destructive(
            model=model,
            strategy_report=strategy_report,
            support_margin_m=0.05,
        )

        strategy_report, geometry_corrections = fix_foundations_inside_emprise(
            model=model,
            strategy_report=strategy_report,
            margin_m=0.05,
        )

        reinforcement_report = design_reinforcement_prelim(
            model=model,
            strategy_report=strategy_report,
            fck_mpa=fck_mpa,
            fyk_mpa=fyk_mpa,
            gamma_s=gamma_s,
            cover_m=cover_m,
            phi_main_mm=phi_main_mm,
        )

        reinforcement_final_report = check_reinforcement_final(
            reinforcement_report=reinforcement_report,
            max_spacing_m=max_spacing_m,
            min_diameter_mm=min_diameter_mm,
        )

        punching_final_report = check_punching_final(
            model=model,
            strategy_report=strategy_report,
            reinforcement_final_report=reinforcement_final_report,
            fck_mpa=fck_mpa,
            gamma_c=gamma_c,
            cover_m=cover_m,
        )

        strategy_report, punching_corrections = fix_punching_by_increasing_thickness(
            strategy_report=strategy_report,
            punching_final_report=punching_final_report,
            safety_factor=1.10,
            min_increment_m=0.05,
            target_utilization=0.80,
        )

        reinforcement_report = design_reinforcement_prelim(
            model=model,
            strategy_report=strategy_report,
            fck_mpa=fck_mpa,
            fyk_mpa=fyk_mpa,
            gamma_s=gamma_s,
            cover_m=cover_m,
            phi_main_mm=phi_main_mm,
        )

        reinforcement_final_report = check_reinforcement_final(
            reinforcement_report=reinforcement_report,
            max_spacing_m=max_spacing_m,
            min_diameter_mm=min_diameter_mm,
        )

        punching_final_report = check_punching_final(
            model=model,
            strategy_report=strategy_report,
            reinforcement_final_report=reinforcement_final_report,
            fck_mpa=fck_mpa,
            gamma_c=gamma_c,
            cover_m=cover_m,
        )

        anchorage_report = build_anchorage_details(
            model=model,
            strategy_report=strategy_report,
            starter_diameter_mm=starter_diameter_mm,
            stirrup_diameter_mm=stirrup_diameter_mm,
            cover_m=cover_m,
        )

        anchorage_report, anchorage_corrections = secure_anchorage_execution_solution(
            anchorage_report=anchorage_report,
        )

        boq_report = build_foundation_boq(
            strategy_report=strategy_report,
            reinforcement_report=reinforcement_report,
            anchorage_report=anchorage_report,
            clean_concrete_m=clean_concrete_m,
            model=model,
        )

        hypotheses = {
            "project_name": project_name,
            "q_allowable_kPa": q_allowable_kPa,
            "fck_mpa": fck_mpa,
            "fyk_mpa": fyk_mpa,
            "gamma_s": gamma_s,
            "gamma_c": gamma_c,
            "cover_m": cover_m,
            "clean_concrete_m": clean_concrete_m,
            "phi_main_mm": phi_main_mm,
            "starter_diameter_mm": starter_diameter_mm,
            "stirrup_diameter_mm": stirrup_diameter_mm,
            "stirrup_spacing_cm": stirrup_spacing_cm,
            "stirrup_secondary_spacing_cm": stirrup_secondary_spacing_cm,
            "critical_zone_m": critical_zone_m,
            "max_spacing_m": max_spacing_m,
            "min_diameter_mm": min_diameter_mm,
        }

        calculation_report = build_foundation_calculation_report(
            model=model,
            strategy_report=strategy_report,
            reinforcement_report=reinforcement_report,
            reinforcement_final_report=reinforcement_final_report,
            punching_final_report=punching_final_report,
            anchorage_report=anchorage_report,
            boq_report=boq_report,
            hypotheses=hypotheses,
        )

        zip_path = generate_project_package_zip(
            model=model,
            strategy_report=strategy_report,
            reinforcement_report=reinforcement_report,
            reinforcement_final_report=reinforcement_final_report,
            punching_final_report=punching_final_report,
            anchorage_report=anchorage_report,
            boq_report=boq_report,
            calculation_report=calculation_report,
            output_dir=temp_path,
            starter_diameter_mm=starter_diameter_mm,
            stirrup_diameter_mm=stirrup_diameter_mm,
            stirrup_spacing_cm=stirrup_spacing_cm,
            stirrup_secondary_spacing_cm=stirrup_secondary_spacing_cm,
            critical_zone_m=critical_zone_m,
            cover_m=cover_m,
            clean_concrete_m=clean_concrete_m,
            q_allowable_kPa=q_allowable_kPa,
            wall_thickness_m=wall_thickness_m,
            storey_height_m=storey_height_m,
            g_floor_kN_m2=g_floor_kN_m2,
            q_floor_kN_m2=q_floor_kN_m2,
            g_terrace_kN_m2=g_terrace_kN_m2,
            q_terrace_kN_m2=q_terrace_kN_m2,
            fck_mpa=fck_mpa,
            fyk_mpa=fyk_mpa,
            gamma_s=gamma_s,
        )

        return FileResponse(
            path=zip_path,
            filename="DOSSIER_COMPLET_FONDATIONS_INGENIERIE_COM.zip",
            media_type="application/zip",
        )

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "status": "ERROR",
                "message": "Erreur pendant la generation du dossier complet ZIP.",
                "detail": str(error),
            },
        )


@app.post("/project-quality-check")
async def project_quality_check(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
    fck_mpa: float = Form(25.0),
    fyk_mpa: float = Form(500.0),
    gamma_s: float = Form(1.15),
    gamma_c: float = Form(1.50),
    cover_m: float = Form(0.05),
    clean_concrete_m: float = Form(0.10),
    phi_main_mm: float = Form(12.0),
    starter_diameter_mm: float = Form(14.0),
    stirrup_diameter_mm: float = Form(8.0),
    max_spacing_m: float = Form(0.20),
    min_diameter_mm: float = Form(10.0),
) -> JSONResponse:
    """
    Controle qualite global du dossier fondations.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            model = read_dxf_model(dxf_path)

            strategy_report = decide_foundation_strategy(
                model=model,
                q_allowable_kPa=q_allowable_kPa,
            )

            strategy_report = fix_support_geometry_non_destructive(
                model=model,
                strategy_report=strategy_report,
                support_margin_m=0.05,
            )

            reinforcement_report = design_reinforcement_prelim(
                model=model,
                strategy_report=strategy_report,
                fck_mpa=fck_mpa,
                fyk_mpa=fyk_mpa,
                gamma_s=gamma_s,
                cover_m=cover_m,
                phi_main_mm=phi_main_mm,
            )

            reinforcement_final_report = check_reinforcement_final(
                reinforcement_report=reinforcement_report,
                max_spacing_m=max_spacing_m,
                min_diameter_mm=min_diameter_mm,
            )

            punching_final_report = check_punching_final(
                model=model,
                strategy_report=strategy_report,
                reinforcement_final_report=reinforcement_final_report,
                fck_mpa=fck_mpa,
                gamma_c=gamma_c,
                cover_m=cover_m,
            )

            anchorage_report = build_anchorage_details(
                model=model,
                strategy_report=strategy_report,
                starter_diameter_mm=starter_diameter_mm,
                stirrup_diameter_mm=stirrup_diameter_mm,
                cover_m=cover_m,
            )

            boq_report = build_foundation_boq(
                strategy_report=strategy_report,
                reinforcement_report=reinforcement_report,
                anchorage_report=anchorage_report,
                clean_concrete_m=clean_concrete_m,
                model=model,
            )

            report = build_project_quality_check(
                model=model,
                strategy_report=strategy_report,
                reinforcement_report=reinforcement_report,
                reinforcement_final_report=reinforcement_final_report,
                punching_final_report=punching_final_report,
                anchorage_report=anchorage_report,
                boq_report=boq_report,
                q_allowable_kPa=q_allowable_kPa,
            )

            return JSONResponse(report)

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant le controle qualite global.",
                    "detail": str(error),
                },
            )


@app.post("/project-quality-remediation")
async def project_quality_remediation(
    dxf: UploadFile = File(...),
    q_allowable_kPa: float = Form(200.0),
    fck_mpa: float = Form(25.0),
    fyk_mpa: float = Form(500.0),
    gamma_s: float = Form(1.15),
    gamma_c: float = Form(1.50),
    cover_m: float = Form(0.05),
    clean_concrete_m: float = Form(0.10),
    phi_main_mm: float = Form(12.0),
    starter_diameter_mm: float = Form(14.0),
    stirrup_diameter_mm: float = Form(8.0),
    max_spacing_m: float = Form(0.20),
    min_diameter_mm: float = Form(10.0),
) -> JSONResponse:
    """
    Correction automatique des erreurs qualité :
    - semelles hors emprise ;
    - poinçonnement > 1.00 par augmentation de H ;
    puis recalcul complet et nouveau contrôle qualité.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            anchorage_corrections = []
            model = read_dxf_model(dxf_path)

            strategy_report = decide_foundation_strategy(
                model=model,
                q_allowable_kPa=q_allowable_kPa,
            )

            strategy_report = fix_support_geometry_non_destructive(
                model=model,
                strategy_report=strategy_report,
                support_margin_m=0.05,
            )

            # 1) Correction géométrique hors emprise
            strategy_report, geometry_corrections = fix_foundations_inside_emprise(
                model=model,
                strategy_report=strategy_report,
                margin_m=0.05,
            )

            # 2) Premier calcul après correction géométrique
            reinforcement_report = design_reinforcement_prelim(
                model=model,
                strategy_report=strategy_report,
                fck_mpa=fck_mpa,
                fyk_mpa=fyk_mpa,
                gamma_s=gamma_s,
                cover_m=cover_m,
                phi_main_mm=phi_main_mm,
            )

            reinforcement_final_report = check_reinforcement_final(
                reinforcement_report=reinforcement_report,
                max_spacing_m=max_spacing_m,
                min_diameter_mm=min_diameter_mm,
            )

            punching_final_report = check_punching_final(
                model=model,
                strategy_report=strategy_report,
                reinforcement_final_report=reinforcement_final_report,
                fck_mpa=fck_mpa,
                gamma_c=gamma_c,
                cover_m=cover_m,
            )

            # 3) Correction du poinçonnement par augmentation de H
            strategy_report, punching_corrections = fix_punching_by_increasing_thickness(
                strategy_report=strategy_report,
                punching_final_report=punching_final_report,
                safety_factor=1.10,
                min_increment_m=0.05,
                target_utilization=0.80,
            )

            # 4) Recalcul complet après augmentation H
            reinforcement_report = design_reinforcement_prelim(
                model=model,
                strategy_report=strategy_report,
                fck_mpa=fck_mpa,
                fyk_mpa=fyk_mpa,
                gamma_s=gamma_s,
                cover_m=cover_m,
                phi_main_mm=phi_main_mm,
            )

            reinforcement_final_report = check_reinforcement_final(
                reinforcement_report=reinforcement_report,
                max_spacing_m=max_spacing_m,
                min_diameter_mm=min_diameter_mm,
            )

            punching_final_report = check_punching_final(
                model=model,
                strategy_report=strategy_report,
                reinforcement_final_report=reinforcement_final_report,
                fck_mpa=fck_mpa,
                gamma_c=gamma_c,
                cover_m=cover_m,
            )

            anchorage_report = build_anchorage_details(
                model=model,
                strategy_report=strategy_report,
                starter_diameter_mm=starter_diameter_mm,
                stirrup_diameter_mm=stirrup_diameter_mm,
                cover_m=cover_m,
            )

            anchorage_report, anchorage_corrections = secure_anchorage_execution_solution(
                anchorage_report=anchorage_report,
            )

            boq_report = build_foundation_boq(
                strategy_report=strategy_report,
                reinforcement_report=reinforcement_report,
                anchorage_report=anchorage_report,
                clean_concrete_m=clean_concrete_m,
                model=model,
            )

            quality_report = build_project_quality_check(
                model=model,
                strategy_report=strategy_report,
                reinforcement_report=reinforcement_report,
                reinforcement_final_report=reinforcement_final_report,
                punching_final_report=punching_final_report,
                anchorage_report=anchorage_report,
                boq_report=boq_report,
                q_allowable_kPa=q_allowable_kPa,
            )

            return JSONResponse({
                "status": quality_report.get("status"),
                "method": "project_quality_remediation_v0_32_4",
                "geometry_corrections": geometry_corrections,
                "punching_corrections": punching_corrections,
                "anchorage_corrections": anchorage_corrections,
                "quality_after_remediation": quality_report,
                "strategy_report_corrected": strategy_report,
                "reinforcement_final_report": reinforcement_final_report,
                "punching_final_report": punching_final_report,
                "boq_totals": boq_report.get("totals", {}),
            })

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant la correction automatique qualité.",
                    "detail": str(error),
                },
            )


@app.post("/project-dashboard")
async def project_dashboard(
    dxf: UploadFile = File(...),
    project_name: str = Form("INGENIERIE.COM - Projet fondations"),
    q_allowable_kPa: float = Form(200.0),
    fck_mpa: float = Form(25.0),
    fyk_mpa: float = Form(500.0),
    gamma_s: float = Form(1.15),
    gamma_c: float = Form(1.50),
    cover_m: float = Form(0.05),
    clean_concrete_m: float = Form(0.10),
    phi_main_mm: float = Form(12.0),
    starter_diameter_mm: float = Form(14.0),
    stirrup_diameter_mm: float = Form(8.0),
    max_spacing_m: float = Form(0.20),
    min_diameter_mm: float = Form(10.0),
    backfill_kN_m2: float = Form(0.0),
    g_floor_kN_m2: float = Form(5.0),
    q_floor_kN_m2: float = Form(1.5),
    g_terrace_kN_m2: float = Form(6.0),
    q_terrace_kN_m2: float = Form(1.0),
) -> JSONResponse:
    """
    Tableau de bord global du projet fondations.
    Utilise la configuration corrigée.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        dxf_path = save_uploaded_file(dxf, temp_path)

        try:
            model = read_dxf_model(dxf_path)

            strategy_report = decide_foundation_strategy(
                model=model,
                q_allowable_kPa=q_allowable_kPa,
                backfill_kN_m2=backfill_kN_m2,
                g_floor_kN_m2=g_floor_kN_m2,
                q_floor_kN_m2=q_floor_kN_m2,
                g_terrace_kN_m2=g_terrace_kN_m2,
                q_terrace_kN_m2=q_terrace_kN_m2,
            )

            strategy_report = fix_support_geometry_non_destructive(
                model=model,
                strategy_report=strategy_report,
                support_margin_m=0.05,
            )

            strategy_report, geometry_corrections = fix_foundations_inside_emprise(
                model=model,
                strategy_report=strategy_report,
                margin_m=0.05,
            )

            reinforcement_report = design_reinforcement_prelim(
                model=model,
                strategy_report=strategy_report,
                fck_mpa=fck_mpa,
                fyk_mpa=fyk_mpa,
                gamma_s=gamma_s,
                cover_m=cover_m,
                phi_main_mm=phi_main_mm,
            )

            reinforcement_final_report = check_reinforcement_final(
                reinforcement_report=reinforcement_report,
                max_spacing_m=max_spacing_m,
                min_diameter_mm=min_diameter_mm,
            )

            punching_final_report = check_punching_final(
                model=model,
                strategy_report=strategy_report,
                reinforcement_final_report=reinforcement_final_report,
                fck_mpa=fck_mpa,
                gamma_c=gamma_c,
                cover_m=cover_m,
            )

            strategy_report, punching_corrections = fix_punching_by_increasing_thickness(
                strategy_report=strategy_report,
                punching_final_report=punching_final_report,
                safety_factor=1.10,
                min_increment_m=0.05,
                target_utilization=0.80,
            )

            reinforcement_report = design_reinforcement_prelim(
                model=model,
                strategy_report=strategy_report,
                fck_mpa=fck_mpa,
                fyk_mpa=fyk_mpa,
                gamma_s=gamma_s,
                cover_m=cover_m,
                phi_main_mm=phi_main_mm,
            )

            reinforcement_final_report = check_reinforcement_final(
                reinforcement_report=reinforcement_report,
                max_spacing_m=max_spacing_m,
                min_diameter_mm=min_diameter_mm,
            )

            punching_final_report = check_punching_final(
                model=model,
                strategy_report=strategy_report,
                reinforcement_final_report=reinforcement_final_report,
                fck_mpa=fck_mpa,
                gamma_c=gamma_c,
                cover_m=cover_m,
            )

            anchorage_report = build_anchorage_details(
                model=model,
                strategy_report=strategy_report,
                starter_diameter_mm=starter_diameter_mm,
                stirrup_diameter_mm=stirrup_diameter_mm,
                cover_m=cover_m,
            )

            anchorage_report, anchorage_corrections = secure_anchorage_execution_solution(
                anchorage_report=anchorage_report,
            )

            boq_report = build_foundation_boq(
                strategy_report=strategy_report,
                reinforcement_report=reinforcement_report,
                anchorage_report=anchorage_report,
                clean_concrete_m=clean_concrete_m,
                model=model,
            )

            quality_report = build_project_quality_check(
                model=model,
                strategy_report=strategy_report,
                reinforcement_report=reinforcement_report,
                reinforcement_final_report=reinforcement_final_report,
                punching_final_report=punching_final_report,
                anchorage_report=anchorage_report,
                boq_report=boq_report,
                q_allowable_kPa=q_allowable_kPa,
            )

            dashboard = build_project_dashboard(
                project_name=project_name,
                strategy_report=strategy_report,
                reinforcement_final_report=reinforcement_final_report,
                punching_final_report=punching_final_report,
                anchorage_report=anchorage_report,
                boq_report=boq_report,
                quality_report=quality_report,
            )

            dashboard["remediation_summary"] = {
                "geometry_corrections_count": len(geometry_corrections),
                "punching_corrections_count": len(punching_corrections),
                "anchorage_corrections_count": len(anchorage_corrections),
                "geometry_corrections": geometry_corrections,
                "punching_corrections": punching_corrections,
                "anchorage_corrections": anchorage_corrections,
            }

            return JSONResponse(dashboard)

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "ERROR",
                    "message": "Erreur pendant la generation du tableau de bord projet.",
                    "detail": str(error),
                },
            )


@app.post("/project-summary-report-docx", response_model=None)
async def project_summary_report_docx(
    dxf: UploadFile = File(...),
    project_name: str = Form("INGENIERIE.COM - Projet fondations"),
    q_allowable_kPa: float = Form(200.0),
    fck_mpa: float = Form(25.0),
    fyk_mpa: float = Form(500.0),
    gamma_s: float = Form(1.15),
    gamma_c: float = Form(1.50),
    cover_m: float = Form(0.05),
    clean_concrete_m: float = Form(0.10),
    phi_main_mm: float = Form(12.0),
    starter_diameter_mm: float = Form(14.0),
    stirrup_diameter_mm: float = Form(8.0),
    max_spacing_m: float = Form(0.20),
    min_diameter_mm: float = Form(10.0),
):
    """
    Exporte le rapport de synthese projet en DOCX.
    """
    temp_path = Path(tempfile.mkdtemp())
    dxf_path = save_uploaded_file(dxf, temp_path)

    try:
        model = read_dxf_model(dxf_path)

        strategy_report = decide_foundation_strategy(
            model=model,
            q_allowable_kPa=q_allowable_kPa,
        )

        strategy_report = fix_support_geometry_non_destructive(
            model=model,
            strategy_report=strategy_report,
            support_margin_m=0.05,
        )

        strategy_report, geometry_corrections = fix_foundations_inside_emprise(
            model=model,
            strategy_report=strategy_report,
            margin_m=0.05,
        )

        reinforcement_report = design_reinforcement_prelim(
            model=model,
            strategy_report=strategy_report,
            fck_mpa=fck_mpa,
            fyk_mpa=fyk_mpa,
            gamma_s=gamma_s,
            cover_m=cover_m,
            phi_main_mm=phi_main_mm,
        )

        reinforcement_final_report = check_reinforcement_final(
            reinforcement_report=reinforcement_report,
            max_spacing_m=max_spacing_m,
            min_diameter_mm=min_diameter_mm,
        )

        punching_final_report = check_punching_final(
            model=model,
            strategy_report=strategy_report,
            reinforcement_final_report=reinforcement_final_report,
            fck_mpa=fck_mpa,
            gamma_c=gamma_c,
            cover_m=cover_m,
        )

        strategy_report, punching_corrections = fix_punching_by_increasing_thickness(
            strategy_report=strategy_report,
            punching_final_report=punching_final_report,
            safety_factor=1.10,
            min_increment_m=0.05,
            target_utilization=0.80,
        )

        reinforcement_report = design_reinforcement_prelim(
            model=model,
            strategy_report=strategy_report,
            fck_mpa=fck_mpa,
            fyk_mpa=fyk_mpa,
            gamma_s=gamma_s,
            cover_m=cover_m,
            phi_main_mm=phi_main_mm,
        )

        reinforcement_final_report = check_reinforcement_final(
            reinforcement_report=reinforcement_report,
            max_spacing_m=max_spacing_m,
            min_diameter_mm=min_diameter_mm,
        )

        punching_final_report = check_punching_final(
            model=model,
            strategy_report=strategy_report,
            reinforcement_final_report=reinforcement_final_report,
            fck_mpa=fck_mpa,
            gamma_c=gamma_c,
            cover_m=cover_m,
        )

        anchorage_report = build_anchorage_details(
            model=model,
            strategy_report=strategy_report,
            starter_diameter_mm=starter_diameter_mm,
            stirrup_diameter_mm=stirrup_diameter_mm,
            cover_m=cover_m,
        )

        anchorage_report, anchorage_corrections = secure_anchorage_execution_solution(
            anchorage_report=anchorage_report,
        )

        boq_report = build_foundation_boq(
            strategy_report=strategy_report,
            reinforcement_report=reinforcement_report,
            anchorage_report=anchorage_report,
            clean_concrete_m=clean_concrete_m,
            model=model,
        )

        quality_report = build_project_quality_check(
            model=model,
            strategy_report=strategy_report,
            reinforcement_report=reinforcement_report,
            reinforcement_final_report=reinforcement_final_report,
            punching_final_report=punching_final_report,
            anchorage_report=anchorage_report,
            boq_report=boq_report,
            q_allowable_kPa=q_allowable_kPa,
        )

        dashboard = build_project_dashboard(
            project_name=project_name,
            strategy_report=strategy_report,
            reinforcement_final_report=reinforcement_final_report,
            punching_final_report=punching_final_report,
            anchorage_report=anchorage_report,
            boq_report=boq_report,
            quality_report=quality_report,
        )

        dashboard["remediation_summary"] = {
            "geometry_corrections_count": len(geometry_corrections),
            "punching_corrections_count": len(punching_corrections),
            "anchorage_corrections_count": len(anchorage_corrections),
            "geometry_corrections": geometry_corrections,
            "punching_corrections": punching_corrections,
            "anchorage_corrections": anchorage_corrections,
        }

        output_path = temp_path / "RAPPORT_SYNTHESE_PROJET_FONDATIONS.docx"

        export_project_summary_docx(
            dashboard=dashboard,
            output_path=output_path,
        )

        return FileResponse(
            path=output_path,
            filename="RAPPORT_SYNTHESE_PROJET_FONDATIONS.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "status": "ERROR",
                "message": "Erreur pendant l'export DOCX du rapport de synthese projet.",
                "detail": str(error),
            },
        )


@app.post("/project-summary-report-pdf", response_model=None)
async def project_summary_report_pdf(
    dxf: UploadFile = File(...),
    project_name: str = Form("INGENIERIE.COM - Projet fondations"),
    q_allowable_kPa: float = Form(200.0),
    fck_mpa: float = Form(25.0),
    fyk_mpa: float = Form(500.0),
    gamma_s: float = Form(1.15),
    gamma_c: float = Form(1.50),
    cover_m: float = Form(0.05),
    clean_concrete_m: float = Form(0.10),
    phi_main_mm: float = Form(12.0),
    starter_diameter_mm: float = Form(14.0),
    stirrup_diameter_mm: float = Form(8.0),
    max_spacing_m: float = Form(0.20),
    min_diameter_mm: float = Form(10.0),
):
    """
    Exporte le rapport de synthese projet en PDF.
    """
    temp_path = Path(tempfile.mkdtemp())
    dxf_path = save_uploaded_file(dxf, temp_path)

    try:
        model = read_dxf_model(dxf_path)

        strategy_report = decide_foundation_strategy(
            model=model,
            q_allowable_kPa=q_allowable_kPa,
        )

        strategy_report = fix_support_geometry_non_destructive(
            model=model,
            strategy_report=strategy_report,
            support_margin_m=0.05,
        )

        strategy_report, geometry_corrections = fix_foundations_inside_emprise(
            model=model,
            strategy_report=strategy_report,
            margin_m=0.05,
        )

        reinforcement_report = design_reinforcement_prelim(
            model=model,
            strategy_report=strategy_report,
            fck_mpa=fck_mpa,
            fyk_mpa=fyk_mpa,
            gamma_s=gamma_s,
            cover_m=cover_m,
            phi_main_mm=phi_main_mm,
        )

        reinforcement_final_report = check_reinforcement_final(
            reinforcement_report=reinforcement_report,
            max_spacing_m=max_spacing_m,
            min_diameter_mm=min_diameter_mm,
        )

        punching_final_report = check_punching_final(
            model=model,
            strategy_report=strategy_report,
            reinforcement_final_report=reinforcement_final_report,
            fck_mpa=fck_mpa,
            gamma_c=gamma_c,
            cover_m=cover_m,
        )

        strategy_report, punching_corrections = fix_punching_by_increasing_thickness(
            strategy_report=strategy_report,
            punching_final_report=punching_final_report,
            safety_factor=1.10,
            min_increment_m=0.05,
            target_utilization=0.80,
        )

        reinforcement_report = design_reinforcement_prelim(
            model=model,
            strategy_report=strategy_report,
            fck_mpa=fck_mpa,
            fyk_mpa=fyk_mpa,
            gamma_s=gamma_s,
            cover_m=cover_m,
            phi_main_mm=phi_main_mm,
        )

        reinforcement_final_report = check_reinforcement_final(
            reinforcement_report=reinforcement_report,
            max_spacing_m=max_spacing_m,
            min_diameter_mm=min_diameter_mm,
        )

        punching_final_report = check_punching_final(
            model=model,
            strategy_report=strategy_report,
            reinforcement_final_report=reinforcement_final_report,
            fck_mpa=fck_mpa,
            gamma_c=gamma_c,
            cover_m=cover_m,
        )

        anchorage_report = build_anchorage_details(
            model=model,
            strategy_report=strategy_report,
            starter_diameter_mm=starter_diameter_mm,
            stirrup_diameter_mm=stirrup_diameter_mm,
            cover_m=cover_m,
        )

        anchorage_report, anchorage_corrections = secure_anchorage_execution_solution(
            anchorage_report=anchorage_report,
        )

        boq_report = build_foundation_boq(
            strategy_report=strategy_report,
            reinforcement_report=reinforcement_report,
            anchorage_report=anchorage_report,
            clean_concrete_m=clean_concrete_m,
            model=model,
        )

        quality_report = build_project_quality_check(
            model=model,
            strategy_report=strategy_report,
            reinforcement_report=reinforcement_report,
            reinforcement_final_report=reinforcement_final_report,
            punching_final_report=punching_final_report,
            anchorage_report=anchorage_report,
            boq_report=boq_report,
            q_allowable_kPa=q_allowable_kPa,
        )

        dashboard = build_project_dashboard(
            project_name=project_name,
            strategy_report=strategy_report,
            reinforcement_final_report=reinforcement_final_report,
            punching_final_report=punching_final_report,
            anchorage_report=anchorage_report,
            boq_report=boq_report,
            quality_report=quality_report,
        )

        dashboard["remediation_summary"] = {
            "geometry_corrections_count": len(geometry_corrections),
            "punching_corrections_count": len(punching_corrections),
            "anchorage_corrections_count": len(anchorage_corrections),
            "geometry_corrections": geometry_corrections,
            "punching_corrections": punching_corrections,
            "anchorage_corrections": anchorage_corrections,
        }

        output_path = temp_path / "RAPPORT_SYNTHESE_PROJET_FONDATIONS.pdf"

        export_project_summary_pdf(
            dashboard=dashboard,
            output_path=output_path,
        )

        return FileResponse(
            path=output_path,
            filename="RAPPORT_SYNTHESE_PROJET_FONDATIONS.pdf",
            media_type="application/pdf",
        )

    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "status": "ERROR",
                "message": "Erreur pendant l'export PDF du rapport de synthese projet.",
                "detail": str(error),
            },
        )
