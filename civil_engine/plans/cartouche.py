from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf.addons import Importer


# Chemin du gabarit cartouche A3 (livré avec le package)
CARTOUCHE_TEMPLATE = Path(__file__).resolve().parent / "templates" / "Cartouche_A3.dxf"

# Dimensions du cartouche source (mm)
CARTOUCHE_WIDTH_MM = 420.0
CARTOUCHE_HEIGHT_MM = 297.0


def _norm(text: str) -> str:
    """Nettoie un MTEXT de ses codes de formatage pour comparaison."""
    if text is None:
        return ""
    t = text.replace("\\P", " ").replace("\n", " ")
    t = re.sub(r"\{?\\[A-Za-z]\d*;?", "", t)   # codes \C256; \c0; etc.
    t = t.replace("{", "").replace("}", "")
    return t.strip()


def _wrap_like(original: str, new_value: str) -> str:
    """Réapplique le préfixe de couleur du MTEXT original à la nouvelle valeur."""
    m = re.match(r"^(\{(?:\\[A-Za-z]\d*;)+)", original)
    if m:
        return m.group(1) + new_value + " }"
    return new_value


def build_cartouche_values(
    project_name: str = "",
    project_number: str = "",
    plan_title: str = "",
    date_str: str = "",
    revision_index: str = "",
    scale_label: str = "1/50",
    drawn_by: str = "H.AIT ZEOUAY",
    checked_by: str = "S.BELQLIB",
) -> dict[str, str]:
    """
    Construit le dictionnaire de valeurs du cartouche.
    Les champs vides ne remplacent pas le texte du gabarit.
    """
    return {
        "project_name": project_name,
        "project_number": project_number,
        "plan_title": plan_title,
        "date": date_str,
        "revision_index": revision_index,
        "scale": scale_label,
        "drawn_by": drawn_by,
        "checked_by": checked_by,
    }


# Correspondances : texte repère (normalisé, dans le gabarit) -> clé de valeur.
# On repère par CONTENU plutôt que par handle, pour survivre à une réédition du gabarit.
_MATCHERS = [
    ("COMMUNE DE CHEFCHAOUEN", "project_name"),
    ("Etude et suivi des travaux", "plan_subtitle_skip"),  # sous-titre projet : on le laisse
    ("Plan de masse", "plan_title"),
    ("S.1-PCFC-25", "plan_number_skip"),   # numéro de plan : composé séparément
    ("PCFC-25", "project_number"),
    ("S.BELQLIB", "checked_by"),
    ("H.AIT ZEOUAY", "drawn_by"),
    ("As indicated", "scale"),
    ("25/11/2025", "date"),
]


def _prepare_filled_template(values: dict[str, str], tmp_path: Path) -> Path:
    """
    Charge le gabarit cartouche, remplace les textes variables selon `values`,
    sauvegarde une copie temporaire et retourne son chemin.
    """
    doc = ezdxf.readfile(str(CARTOUCHE_TEMPLATE))
    msp = doc.modelspace()

    project_number = values.get("project_number", "")
    plan_number = ""
    if project_number:
        plan_number = f"S.1-{project_number}"

    for e in msp:
        if e.dxftype() != "MTEXT":
            continue
        clean = _norm(e.text)
        for needle, key in _MATCHERS:
            if needle in clean:
                if key.endswith("_skip"):
                    # numéro de plan : recomposé à partir du n° projet
                    if needle.startswith("S.1-") and plan_number:
                        e.text = plan_number
                    break
                new_val = values.get(key, "")
                if new_val:
                    e.text = _wrap_like(e.text, new_val)
                break

    out = tmp_path / "cartouche_filled.dxf"
    doc.saveas(str(out))
    return out


def insert_cartouche(
    target_doc,
    insert_xy: tuple[float, float],
    values: dict[str, str],
    target_units: str = "m",
    drawing_scale: float = 50.0,
    block_name: str = "CARTOUCHE_A3",
) -> None:
    """
    Insère le cartouche A3 (textes remplis) dans target_doc à insert_xy.

    target_units : 'm' (plans à l'échelle réelle) ou 'mm'.
    drawing_scale : facteur d'agrandissement pour rendre le cartouche lisible
                    face à un plan tracé en vraies dimensions. Pour un plan en
                    mètres à l'échelle 1/50, drawing_scale=50 donne un cartouche
                    de 21.0 x 14.85 m (cohérent avec la planche A3 à 1/50).
    """
    import tempfile

    base = 0.001 if target_units == "m" else 1.0
    scale = base * drawing_scale

    with tempfile.TemporaryDirectory() as td:
        filled = _prepare_filled_template(values, Path(td))
        src = ezdxf.readfile(str(filled))

        # Créer (une seule fois) un block contenant le cartouche
        if block_name not in target_doc.blocks:
            blk = target_doc.blocks.new(block_name)
            importer = Importer(src, target_doc)
            importer.import_modelspace(target_layout=blk)
            importer.finalize()

    target_doc.modelspace().add_blockref(
        block_name,
        insert=insert_xy,
        dxfattribs={"xscale": scale, "yscale": scale, "rotation": 0},
    )


def cartouche_size(target_units: str = "m", drawing_scale: float = 50.0) -> tuple[float, float]:
    """Dimensions du cartouche dans les unités cibles (largeur, hauteur)."""
    base = 0.001 if target_units == "m" else 1.0
    scale = base * drawing_scale
    return (CARTOUCHE_WIDTH_MM * scale, CARTOUCHE_HEIGHT_MM * scale)
