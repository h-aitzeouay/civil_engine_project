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

# Zone de dessin utile (cadre vide au-dessus de la bande cartouche), en mm
# relatif au coin bas-gauche du cartouche.
DRAW_AREA_X_MM = (5.0, 415.0)
DRAW_AREA_Y_MM = (48.0, 291.0)

# Zone logo (bas-gauche, avant les cases texte), en mm.
LOGO_AREA_X_MM = (6.0, 128.0)
LOGO_AREA_Y_MM = (5.0, 43.0)

# Logo image (livre avec le package)
LOGO_IMAGE = Path(__file__).resolve().parent / "templates" / "logo_ingenierie.png"
LOGO_VECTORS = Path(__file__).resolve().parent / "templates" / "logo_vectors.json"
LOGO_PX_RATIO = 2.81  # largeur / hauteur du PNG recadre

# Largeur approximative d'un caractere MTEXT selon la hauteur de police.
# Calibre sur le gabarit reel (police large) pour eviter tout debordement.
CHAR_WIDTH_FACTOR = 0.78

# Cases (largeur disponible en mm) par texte repere, mesurees sur le gabarit.
CASE_WIDTH_MM = {
    "project_name": 85.0,
    "plan_title": 110.0,
    "project_number": 55.0,
    "plan_number": 55.0,
    "scale": 55.0,
    "date": 55.0,
    "checked_by": 55.0,
    "drawn_by": 55.0,
}


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
                resolved_key = key
                if key.endswith("_skip"):
                    # numero de plan : recompose a partir du n projet
                    if needle.startswith("S.1-") and plan_number:
                        e.text = plan_number
                        resolved_key = "plan_number"
                    else:
                        break
                else:
                    new_val = values.get(key, "")
                    if new_val:
                        e.text = _wrap_like(e.text, new_val)

                # Ajustement de la hauteur de police a la largeur de la case
                _fit_text_to_case(e, resolved_key)
                break

    # (Le logo est insere apres l'import, directement dans le doc cible,
    #  via _insert_logo_in_target dans insert_cartouche.)

    out = tmp_path / "cartouche_filled.dxf"
    doc.saveas(str(out))
    return out


def _fit_text_to_case(mtext, key: str) -> None:
    """
    Reduit la hauteur de police d'un MTEXT si le texte estime depasse
    la largeur de sa case. Empeche le debordement (ex. 'COMMUNE DE TEMARA').
    """
    case_w = CASE_WIDTH_MM.get(key)
    if not case_w:
        return
    raw = _norm(mtext.text)
    n_chars = max(1, len(raw))
    h = float(getattr(mtext.dxf, "char_height", 0) or 0)
    if h <= 0:
        return
    # largeur estimee du texte a la hauteur actuelle
    est_w = n_chars * h * CHAR_WIDTH_FACTOR
    margin = 0.92  # garde une marge dans la case
    if est_w > case_w * margin:
        new_h = (case_w * margin) / (n_chars * CHAR_WIDTH_FACTOR)
        new_h = max(1.2, round(new_h, 2))  # plancher de lisibilite
        mtext.dxf.char_height = new_h
        # limiter la largeur de reference du MTEXT a la case
        try:
            mtext.dxf.width = case_w * margin
        except Exception:
            pass


def _insert_logo_in_target(target_doc, insert_xy: tuple[float, float], scale: float) -> None:
    """
    Dessine le logo en TRACE VECTORIEL natif (polylignes) dans la zone logo
    du cartouche, directement dans le modelspace cible. Autonome : aucune
    image externe, le logo fait partie du DXF.
    """
    import json

    if not LOGO_VECTORS.exists():
        return

    data = json.loads(LOGO_VECTORS.read_text())
    paths = data.get("paths", [])
    bbox = data.get("bbox")
    if not paths or not bbox:
        return

    ox, oy, x1, y1 = bbox
    lw_x = max(x1 - ox, 1e-6)
    lw_y = max(y1 - oy, 1e-6)
    ratio = lw_x / lw_y

    # Zone logo cible (coordonnees finales)
    lx0, lx1 = LOGO_AREA_X_MM
    ly0, ly1 = LOGO_AREA_Y_MM
    box_w = (lx1 - lx0) * scale
    box_h = (ly1 - ly0) * scale

    # Respecter le ratio dans la zone (avec petite marge)
    margin = 0.90
    if box_w / box_h > ratio:
        h = box_h * margin
        w = h * ratio
    else:
        w = box_w * margin
        h = w / ratio

    sx = w / lw_x
    sy = h / lw_y

    ix, iy = insert_xy
    # centrer le logo dans la zone
    cx = ix + (lx0 + lx1) / 2.0 * scale
    cy = iy + (ly0 + ly1) / 2.0 * scale
    base_x = cx - w / 2.0
    base_y = cy - h / 2.0

    msp = target_doc.modelspace()

    def _aci(rgb):
        r, g, b = rgb
        if r > 120 and g < 100 and b < 100:
            return 1   # rouge
        return 7       # noir

    for pa in paths:
        pts = [
            (base_x + (px - ox) * sx, base_y + (py - oy) * sy)
            for (px, py) in pa["pts"]
        ]
        if len(pts) >= 2:
            msp.add_lwpolyline(
                pts,
                dxfattribs={"color": _aci(pa.get("rgb", [0, 0, 0])), "layer": "CARTOUCHE_LOGO"},
            )


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

    # Logo : insere directement dans le modelspace cible (l'Importer ne
    # transfere pas fiablement les entites IMAGE dans un block).
    try:
        _insert_logo_in_target(target_doc, insert_xy, scale)
    except Exception:
        pass  # cartouche utilisable sans logo


def cartouche_size(target_units: str = "m", drawing_scale: float = 50.0) -> tuple[float, float]:
    """Dimensions du cartouche dans les unités cibles (largeur, hauteur)."""
    base = 0.001 if target_units == "m" else 1.0
    scale = base * drawing_scale
    return (CARTOUCHE_WIDTH_MM * scale, CARTOUCHE_HEIGHT_MM * scale)


def draw_area(
    insert_xy: tuple[float, float],
    target_units: str = "m",
    drawing_scale: float = 50.0,
) -> dict[str, float]:
    """
    Rectangle de la zone de dessin (cadre vide) en coordonnees cibles,
    une fois le cartouche insere a insert_xy. Le plan doit etre mis a
    l'echelle pour tenir dans ce rectangle.
    """
    base = 0.001 if target_units == "m" else 1.0
    scale = base * drawing_scale
    ix, iy = insert_xy
    return {
        "xmin": ix + DRAW_AREA_X_MM[0] * scale,
        "xmax": ix + DRAW_AREA_X_MM[1] * scale,
        "ymin": iy + DRAW_AREA_Y_MM[0] * scale,
        "ymax": iy + DRAW_AREA_Y_MM[1] * scale,
        "width": (DRAW_AREA_X_MM[1] - DRAW_AREA_X_MM[0]) * scale,
        "height": (DRAW_AREA_Y_MM[1] - DRAW_AREA_Y_MM[0]) * scale,
    }
