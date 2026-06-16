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


# Epaisseurs de trait par role graphique (valeurs ezdxf en 1/100 mm).
# 50 = 0.50 mm | 35 = 0.35 mm | 30 = 0.30 mm | 18 = 0.18 mm | 13 = 0.13 mm
LW_EMPRISE = 50      # contour d'emprise : trait fort
LW_BETON = 35        # contours beton (semelles, voiles, poteaux, massifs)
LW_ARM_PRINC = 30    # aciers principaux et attentes
LW_FIN = 18          # axes, cotations, textes, tableaux, cartouche, renvois
LW_HACHURE = 13      # hachures de detail


def lineweight_for_layer(name: str) -> int | None:
    """
    Retourne l'epaisseur de trait (1/100 mm) selon le role du calque,
    ou None si le calque doit garder l'epaisseur par defaut.
    L'ordre des tests est important (les annotations priment sur les
    jetons beton courts comme SE/SI).
    """
    n = name.upper()

    # Aciers
    if n.startswith("ARM") or "ATTENTES" in n or n == "ARMATURES" or "RECOUVREMENT" in n:
        if ("PRINC" in n or "INF" in n or "SUP" in n or n == "ARMATURES"
                or "ATTENTES" in n or n.endswith("_PR")
                or "LONGRINE" in n or "LIAISON" in n):
            return LW_ARM_PRINC
        return LW_FIN
    if "CADRES" in n:
        return LW_FIN

    # Hachures et sol (avant les details pour ne pas etre capte par "DETAIL")
    if "HACHURE" in n or n == "SOL":
        return LW_HACHURE

    # Beton de proprete : beton maigre, trait fin (avant le contour beton).
    if "PROPRETE" in n:
        return LW_FIN

    # Annotations, details, tableaux, cartouche
    if any(k in n for k in (
        "DETAIL", "COTAT", "COTE", "TEXTE", "TABLEAU", "CARTOUCHE",
        "NOTE", "NOTA", "REFERENCE", "RENVOI", "CENTRE_CHARGE",
        "TITRE", "G-ANNO", "A-DETL",
    )):
        return LW_FIN
    if "AXE" in n:
        return LW_FIN

    # Contours
    if "EMPRISE" in n:
        return LW_EMPRISE
    if any(k in n for k in ("SEMELLE", "MASSIF", "VOILE", "POTEAU",
                            "BETON", "COUPE", "RADIER",
                            "POUTRE", "REDRESS", "LONGRINE", "CHAINAGE")):
        return LW_BETON
    if n in ("SI", "SE", "SC", "RL"):
        return LW_BETON

    return None


def apply_layer_lineweights(doc: Any) -> None:
    """Affecte une epaisseur de trait par calque selon son role et active
    l'affichage des epaisseurs dans le dessin."""
    for layer in doc.layers:
        lw = lineweight_for_layer(layer.dxf.name)
        if lw is not None:
            layer.dxf.lineweight = lw
    try:
        doc.header["$LWDISPLAY"] = 1  # afficher les epaisseurs de trait
    except Exception:
        pass


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

    apply_layer_lineweights(doc)

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
