from __future__ import annotations

"""
Planche A3 en presentation (paperspace).

Construit une vraie planche imprimable A3 (420 x 297 mm) dans le Layout1 :
- cadre A3 + cadre interieur ;
- cartouche au gabarit reel INGENIERIE.COM insere en 1:1 (le gabarit fait
  deja 420 x 297 mm) dans la bande basse ;
- fenetre (VIEWPORT) cadree sur le plan du modelspace, a une echelle definie.

Le modelspace n'est pas modifie : la planche reference son contenu via la
fenetre. Approche additive, sans regression sur le dessin en espace objet.
"""

import json
import tempfile
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf.addons import Importer

from civil_engine.plans import cartouche as C


FRAME_LAYER = "A3_CADRE"
VIEWPORT_LAYER = "A3_FENETRE"


def _ensure_sheet_layers(doc: Any) -> None:
    if FRAME_LAYER not in doc.layers:
        doc.layers.add(FRAME_LAYER, color=7)
    if VIEWPORT_LAYER not in doc.layers:
        # calque de la fenetre : non trace
        vp = doc.layers.add(VIEWPORT_LAYER, color=8)
        try:
            vp.plot = False
        except Exception:
            pass


def _insert_logo_paperspace(psp: Any, doc: Any) -> None:
    """Trace le logo vectoriel dans la zone logo du cartouche, en paperspace (mm)."""
    if not C.LOGO_VECTORS.exists():
        return
    data = json.loads(C.LOGO_VECTORS.read_text())
    paths = data.get("paths", [])
    box = data.get("bbox")
    if not paths or not box:
        return

    ox, oy, x1, y1 = box
    lw_x = max(x1 - ox, 1e-6)
    lw_y = max(y1 - oy, 1e-6)
    ratio = lw_x / lw_y

    lx0, lx1 = C.LOGO_AREA_X_MM
    ly0, ly1 = C.LOGO_AREA_Y_MM
    box_w, box_h = (lx1 - lx0), (ly1 - ly0)

    margin = 0.90
    if box_w / box_h > ratio:
        h = box_h * margin
        w = h * ratio
    else:
        w = box_w * margin
        h = w / ratio
    sx, sy = w / lw_x, h / lw_y

    cx = (lx0 + lx1) / 2.0
    cy = (ly0 + ly1) / 2.0
    base_x = cx - w / 2.0
    base_y = cy - h / 2.0

    def _aci(rgb):
        r, g, b = rgb
        return 1 if (r > 120 and g < 100 and b < 100) else 7

    for pa in paths:
        pts = [(base_x + (px - ox) * sx, base_y + (py - oy) * sy) for (px, py) in pa["pts"]]
        if len(pts) >= 2:
            psp.add_lwpolyline(pts, dxfattribs={"color": _aci(pa.get("rgb", [0, 0, 0])),
                                                "layer": "CARTOUCHE_LOGO"})


def setup_a3_plan_sheet(
    doc: Any,
    foundation_bbox: dict[str, float] | None,
    values: dict[str, str],
    scale_denominator: float = 50.0,
    layout_name: str = "Layout1",
) -> bool:
    """
    Configure la planche A3 (paperspace) avec cadre, cartouche et fenetre.

    foundation_bbox : bbox du plan en metres (xmin/ymin/xmax/ymax) pour cadrer
                      la fenetre. Si None, la fenetre cadre tout le modelspace.
    scale_denominator : echelle de trace (1/50 par defaut). Le plan en metres
                      apparait a 1000/scale mm par metre dans la fenetre.
    Retourne True si la planche a ete construite, False sinon.
    """
    try:
        _ensure_sheet_layers(doc)

        psp = doc.layouts.get(layout_name)
        # Format A3 paysage, 1 unite papier = 1 mm, trace 1:1.
        psp.page_setup(size=(420, 297), margins=(0, 0, 0, 0), units="mm")

        # Cadre A3 + cadre interieur
        psp.add_lwpolyline(
            [(0, 0), (420, 0), (420, 297), (0, 297)],
            close=True, dxfattribs={"layer": FRAME_LAYER},
        )
        psp.add_lwpolyline(
            [(5, 5), (415, 5), (415, 292), (5, 292)],
            close=True, dxfattribs={"layer": FRAME_LAYER},
        )

        # --- Cartouche au gabarit reel, insere en 1:1 (le gabarit fait A3) ---
        block_name = "CARTOUCHE_A3_PSP"
        with tempfile.TemporaryDirectory() as td:
            filled = C._prepare_filled_template(values, Path(td))
            src = ezdxf.readfile(str(filled))
            if block_name not in doc.blocks:
                blk = doc.blocks.new(block_name)
                importer = Importer(src, doc)
                importer.import_modelspace(target_layout=blk)
                importer.finalize()
        psp.add_blockref(block_name, insert=(0, 0),
                         dxfattribs={"xscale": 1.0, "yscale": 1.0, "rotation": 0})
        try:
            _insert_logo_paperspace(psp, doc)
        except Exception:
            pass

        # --- Fenetre (viewport) sur la zone de dessin du cartouche ---
        dx0, dx1 = C.DRAW_AREA_X_MM
        dy0, dy1 = C.DRAW_AREA_Y_MM
        vp_center = ((dx0 + dx1) / 2.0, (dy0 + dy1) / 2.0)
        vp_w, vp_h = (dx1 - dx0), (dy1 - dy0)

        # Centre de vue (modelspace) et hauteur de vue selon l'echelle.
        if foundation_bbox is not None:
            mcx = (float(foundation_bbox["xmin"]) + float(foundation_bbox["xmax"])) / 2.0
            mcy = (float(foundation_bbox["ymin"]) + float(foundation_bbox["ymax"])) / 2.0
        else:
            mcx, mcy = 0.0, 0.0

        # 1 mm papier = scale_denominator/1000 m modele.
        m_per_mm = scale_denominator / 1000.0
        view_height_model = vp_h * m_per_mm  # hauteur cadree en metres

        # Si le plan deborde a cette echelle, on elargit la vue pour tout cadrer.
        if foundation_bbox is not None:
            bw = float(foundation_bbox["xmax"]) - float(foundation_bbox["xmin"])
            bh = float(foundation_bbox["ymax"]) - float(foundation_bbox["ymin"])
            needed_h = max(bh, bw * (vp_h / vp_w)) * 1.10
            view_height_model = max(view_height_model, needed_h)

        psp.add_viewport(
            center=vp_center,
            size=(vp_w, vp_h),
            view_center_point=(mcx, mcy),
            view_height=view_height_model,
            dxfattribs={"layer": VIEWPORT_LAYER},
        )
        return True
    except Exception:
        return False
