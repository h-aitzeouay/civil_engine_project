from __future__ import annotations

"""
Import de details types complementaires (poteau, semelle, coupes de poutres,
chainage, ferraillage escalier...) depuis un gabarit DXF, pour les integrer
au plan d'execution final.

Le gabarit `templates/details_standards.dxf` est insere comme bloc, mis a
l'echelle pour tenir dans une largeur cible et place dans une zone dediee.
"""

from pathlib import Path
from typing import Any

import ezdxf
from ezdxf import bbox
from ezdxf.addons import Importer


TEMPLATE = Path(__file__).resolve().parent / "templates" / "details_standards.dxf"
BLOCK_NAME = "DETAILS_IMPORTES"


def place_standard_details(
    doc: Any,
    x_left: float,
    y_top: float,
    target_width: float = 26.0,
    title: str = "D4 - DETAILS TYPES COMPLEMENTAIRES",
    title_layer: str = "DETAILS_TITRES",
) -> bool:
    """
    Importe le gabarit de details et l'insere dans le modelspace de `doc`,
    coin haut-gauche du contenu place a (x_left, y_top), largeur = target_width.
    Retourne True si insere.
    """
    if not TEMPLATE.exists():
        return False
    try:
        src = ezdxf.readfile(str(TEMPLATE))
        bb = bbox.extents(src.modelspace(), fast=True)
        if not bb.has_data:
            return False

        src_w = bb.extmax.x - bb.extmin.x
        src_h = bb.extmax.y - bb.extmin.y
        if src_w <= 0:
            return False
        scale = target_width / src_w
        sh = src_h * scale

        # Creer le bloc (une seule fois) a partir du modelspace du gabarit.
        if BLOCK_NAME not in doc.blocks:
            blk = doc.blocks.new(BLOCK_NAME)
            imp = Importer(src, doc)
            imp.import_modelspace(target_layout=blk)
            imp.finalize()

        # Placement : contenu (xmin, ymax) du gabarit -> (x_left, y_top).
        insert = (x_left - scale * bb.extmin.x, y_top - scale * bb.extmax.y)
        doc.modelspace().add_blockref(
            BLOCK_NAME, insert=insert,
            dxfattribs={"xscale": scale, "yscale": scale, "rotation": 0},
        )

        # Cadre + titre du panneau.
        msp = doc.modelspace()
        if title_layer not in doc.layers:
            doc.layers.add(title_layer, color=7)
        x0, y0, x1, y1 = x_left, y_top - sh, x_left + target_width, y_top
        msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1 + 0.8), (x0, y1 + 0.8)],
                           close=True, dxfattribs={"layer": title_layer})
        msp.add_text(title, dxfattribs={"layer": title_layer, "height": 0.35,
                                        "insert": (x0 + 0.3, y1 + 0.2)})
        return True
    except Exception:
        return False
