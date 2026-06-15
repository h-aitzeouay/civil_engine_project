from __future__ import annotations

"""
Rendu PDF des plans DXF.

Le pipeline genere des plans au format DXF (CAO). Pour le workflow
Ifc -> API -> plan + note de calcul, on rend ce DXF en PDF afin de fournir un
livrable directement consultable (le plan d'execution fondations).

Le rendu utilise le backend matplotlib de ezdxf (ezdxf.addons.drawing).
Les imports lourds sont volontairement internes pour ne pas ralentir le
demarrage de l'API.
"""

from pathlib import Path


def export_dxf_to_pdf(
    dxf_path: str | Path,
    output_path: str | Path,
    page_size_mm: tuple[float, float] | None = None,
) -> str:
    """
    Rend l'espace objet (modelspace) d'un DXF en PDF.

    Retourne le chemin du PDF genere.
    """
    import ezdxf
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    from ezdxf.addons.drawing.config import Configuration

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    dxf_path = Path(dxf_path)
    output_path = Path(output_path)

    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    fig = plt.figure()
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()

    try:
        context = RenderContext(doc)
        backend = MatplotlibBackend(ax)
        config = Configuration()
        frontend = Frontend(context, backend, config=config)
        frontend.draw_layout(msp, finalize=True)

        # Cadrage sur l'etendue reelle du dessin
        ax.set_aspect("equal")
        ax.autoscale(enable=True)

        if page_size_mm is not None:
            width_in = page_size_mm[0] / 25.4
            height_in = page_size_mm[1] / 25.4
            fig.set_size_inches(width_in, height_in)

        fig.savefig(output_path, dpi=200, format="pdf", bbox_inches="tight")
    finally:
        plt.close(fig)

    return str(output_path)
