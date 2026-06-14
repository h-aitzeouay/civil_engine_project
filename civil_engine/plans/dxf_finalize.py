from __future__ import annotations

"""
Finalisation commune des DXF generes.

Objectif : garantir que chaque plan s'ouvre deja cadre (zoom etendu) dans
AutoCAD / DraftSight / viewers, en initialisant les extents du dessin et la
fenetre active du modelspace.

A appeler a la place de doc.saveas(...) dans chaque generateur de plan.
"""

from pathlib import Path
from typing import Any

from ezdxf import bbox, zoom


def finalize_and_save(doc: Any, output_path: str | Path, margin_ratio: float = 0.05) -> None:
    """
    Cadre la fenetre active du modelspace sur l'etendue du dessin (de sorte
    que le plan s'ouvre deja zoome dans AutoCAD / DraftSight / viewers), met a
    jour les variables d'entete d'etendue a titre indicatif, puis sauvegarde.

    Remarque : $EXTMIN/$EXTMAX sont recalcules par AutoCAD au premier REGEN ;
    c'est la fenetre active (VPORT du modelspace) qui controle reellement le
    cadrage a l'ouverture, configuree ici via ezdxf.zoom.extents().

    margin_ratio : marge ajoutee autour du dessin (5 % par defaut) pour ne pas
    coller le contenu au bord de l'ecran a l'ouverture.
    """
    msp = doc.modelspace()

    try:
        extents = bbox.extents(msp, fast=True)
    except Exception:
        extents = None

    if extents is not None and extents.has_data:
        xmin, ymin = extents.extmin.x, extents.extmin.y
        xmax, ymax = extents.extmax.x, extents.extmax.y

        width = max(xmax - xmin, 1e-6)
        height = max(ymax - ymin, 1e-6)
        mx = width * margin_ratio
        my = height * margin_ratio

        # Variables d'entete (indicatives) : aident certains viewers legers.
        doc.header["$EXTMIN"] = (xmin - mx, ymin - my, 0.0)
        doc.header["$EXTMAX"] = (xmax + mx, ymax + my, 0.0)
        doc.header["$LIMMIN"] = (xmin - mx, ymin - my)
        doc.header["$LIMMAX"] = (xmax + mx, ymax + my)

        # Cadrage reel a l'ouverture : configure la fenetre active du modele.
        try:
            zoom.extents(msp, factor=1.0 + 2.0 * margin_ratio)
        except Exception:
            pass

    doc.saveas(output_path)
