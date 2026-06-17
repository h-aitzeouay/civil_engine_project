"""
poteaux_ba.py
Module de calcul / vérification de poteaux rectangulaires en béton armé.

Auteur : INGENIERIE.COM STRUCTURAL AI
Objet : pré-dimensionnement et vérification ELU d'une section de poteau BA
        sous N + flexion uniaxiale ou biaxiale.

Unités d'entrée recommandées :
- géométrie : m
- efforts : kN, kN.m via ColumnForces.from_kN_kNm(...)
- résistances : MPa

Méthode :
- compatibilité des déformations sur section rectangulaire discrétisée ;
- béton en compression uniquement, loi parabole-rectangle simplifiée ;
- acier élasto-plastique symétrique ;
- interaction biaxiale approchée :
    (MEd_y / MRd_y)^alpha + (MEd_z / MRd_z)^alpha <= 1
  avec MRd_y et MRd_z évalués au même NEd.

Limites importantes :
- ce module ne remplace pas une note de calcul réglementaire complète ;
- la stabilité de forme / effets du 2e ordre doivent être vérifiés séparément si le poteau est élancé ;
- les dispositions sismiques RPS/EC8 ne sont pas détaillées ici ;
- les résultats doivent être validés par un ingénieur structure habilité.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, pi, sqrt
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Constantes et petits utilitaires
# ---------------------------------------------------------------------------

MPA = 1e6
KN = 1e3
KNM = 1e3


def m2_to_cm2(a_m2: float) -> float:
    return a_m2 * 1e4


def cm2_to_m2(a_cm2: float) -> float:
    return a_cm2 / 1e4


def clamp(value: float, vmin: float, vmax: float) -> float:
    return max(vmin, min(vmax, value))


def phi_area_m2(phi_mm: float) -> float:
    """Aire d'une barre HA en m²."""
    phi_m = phi_mm / 1000.0
    return pi * phi_m * phi_m / 4.0


def round_up_to_step(value: float, step: float) -> float:
    return ceil(value / step) * step


# ---------------------------------------------------------------------------
# Données matériaux
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Concrete:
    """Béton selon une approche EC2 simplifiée."""
    fck_mpa: float = 25.0
    gamma_c: float = 1.50
    alpha_cc: float = 1.00
    eps_c2: float = 0.0020
    eps_cu2: float = 0.0035

    @property
    def fcd(self) -> float:
        """Résistance de calcul en compression du béton, en Pa."""
        return self.alpha_cc * self.fck_mpa * MPA / self.gamma_c

    def stress(self, eps: float) -> float:
        """
        Contrainte béton en Pa.
        Convention : eps > 0 = compression.
        Béton tendu négligé.
        """
        if eps <= 0.0:
            return 0.0
        if eps < self.eps_c2:
            x = eps / self.eps_c2
            return self.fcd * (1.0 - (1.0 - x) ** 2)
        return self.fcd


@dataclass(frozen=True)
class Steel:
    """Acier HA selon une loi élasto-plastique simplifiée."""
    fyk_mpa: float = 500.0
    gamma_s: float = 1.15
    Es_mpa: float = 200000.0

    @property
    def fyd(self) -> float:
        """Limite d'élasticité de calcul en Pa."""
        return self.fyk_mpa * MPA / self.gamma_s

    @property
    def Es(self) -> float:
        return self.Es_mpa * MPA

    @property
    def eps_yd(self) -> float:
        return self.fyd / self.Es

    def stress(self, eps: float) -> float:
        """Contrainte acier en Pa. eps > 0 compression, eps < 0 traction."""
        return clamp(self.Es * eps, -self.fyd, self.fyd)


# ---------------------------------------------------------------------------
# Armatures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Bar:
    y: float         # coordonnée horizontale par rapport au centre, m
    z: float         # coordonnée verticale par rapport au centre, m
    phi_mm: float

    @property
    def area(self) -> float:
        return phi_area_m2(self.phi_mm)


@dataclass
class ReinforcementLayout:
    bars: List[Bar]

    @property
    def As(self) -> float:
        return sum(b.area for b in self.bars)

    @property
    def n_bars(self) -> int:
        return len(self.bars)

    @property
    def phis_mm(self) -> List[float]:
        return [b.phi_mm for b in self.bars]

    @staticmethod
    def rectangular_perimeter(
        b: float,
        h: float,
        cover: float,
        link_phi_mm: float,
        main_phi_mm: float,
        n_total: int,
    ) -> "ReinforcementLayout":
        """
        Génère une disposition symétrique de barres sur le périmètre.

        b, h, cover en m ; diamètres en mm.
        n_total doit être pair et >= 4 pour une disposition symétrique propre.
        """
        if n_total < 4:
            raise ValueError("Un poteau rectangulaire exige au moins 4 barres longitudinales.")
        if n_total % 2 != 0:
            raise ValueError("n_total doit être pair pour une disposition symétrique.")

        phi = main_phi_mm / 1000.0
        link_phi = link_phi_mm / 1000.0
        offset = cover + link_phi + phi / 2.0

        y0 = b / 2.0 - offset
        z0 = h / 2.0 - offset
        if y0 <= 0 or z0 <= 0:
            raise ValueError("Enrobage + cadres + barres incompatible avec les dimensions du poteau.")

        # Total = 2*n_top + 2*(n_side - 2) = 2*(n_top+n_side)-4
        s = (n_total + 4) // 2
        ratio = b / (b + h)
        n_top = int(round(s * ratio))
        n_top = max(2, min(s - 2, n_top))
        n_side = s - n_top
        n_side = max(2, n_side)

        # Ajustement si nécessaire
        total = 2 * (n_top + n_side) - 4
        if total != n_total:
            n_side += (n_total - total) // 2

        bars: List[Bar] = []

        def linspace(a: float, c: float, n: int) -> List[float]:
            if n == 1:
                return [(a + c) / 2.0]
            return [a + i * (c - a) / (n - 1) for i in range(n)]

        ys = linspace(-y0, y0, n_top)
        for y in ys:
            bars.append(Bar(y, z0, main_phi_mm))
            bars.append(Bar(y, -z0, main_phi_mm))

        zs = linspace(-z0, z0, n_side)
        for z in zs[1:-1]:
            bars.append(Bar(-y0, z, main_phi_mm))
            bars.append(Bar(y0, z, main_phi_mm))

        # Tri pour lecture plus stable
        bars.sort(key=lambda bar: (-bar.z, bar.y))
        if len(bars) != n_total:
            raise RuntimeError(f"Disposition générée incorrecte : {len(bars)} barres au lieu de {n_total}.")
        return ReinforcementLayout(bars)

    def min_clear_spacing(self) -> Optional[float]:
        """
        Distance libre minimale approximative entre barres, en m.
        Calculée entre centres de barres moins demi-diamètres.
        """
        if len(self.bars) < 2:
            return None
        min_s = None
        for i, b1 in enumerate(self.bars):
            for b2 in self.bars[i + 1:]:
                dc = sqrt((b1.y - b2.y) ** 2 + (b1.z - b2.z) ** 2)
                clear = dc - (b1.phi_mm + b2.phi_mm) / 2000.0
                min_s = clear if min_s is None else min(min_s, clear)
        return min_s


# ---------------------------------------------------------------------------
# Efforts et résultats
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ColumnForces:
    """
    Efforts de calcul.
    Convention :
    - NEd > 0 : compression.
    - MEd_y : moment autour de y, lié à l'excentricité selon z.
    - MEd_z : moment autour de z, lié à l'excentricité selon y.
    """
    NEd: float       # N
    MEd_y: float     # N.m
    MEd_z: float     # N.m

    @staticmethod
    def from_kN_kNm(NEd_kN: float, MEd_y_kNm: float = 0.0, MEd_z_kNm: float = 0.0) -> "ColumnForces":
        return ColumnForces(NEd_kN * KN, MEd_y_kNm * KNM, MEd_z_kNm * KNM)

    @property
    def NEd_kN(self) -> float:
        return self.NEd / KN

    @property
    def MEd_y_kNm(self) -> float:
        return self.MEd_y / KNM

    @property
    def MEd_z_kNm(self) -> float:
        return self.MEd_z / KNM


@dataclass
class CheckResult:
    ok: bool
    utilization: float
    NEd_kN: float
    MEd_y_used_kNm: float
    MEd_z_used_kNm: float
    MRd_y_kNm: float
    MRd_z_kNm: float
    NRd_max_kN: float
    As_cm2: float
    rho_percent: float
    min_spacing_cm: Optional[float]
    messages: List[str]


# ---------------------------------------------------------------------------
# Section rectangulaire de poteau
# ---------------------------------------------------------------------------

@dataclass
class RectangularColumn:
    b: float
    h: float
    concrete: Concrete
    steel: Steel
    reinforcement: ReinforcementLayout
    cover: float = 0.03
    mesh_ny: int = 36
    mesh_nz: int = 36

    @property
    def Ac(self) -> float:
        return self.b * self.h

    @property
    def As(self) -> float:
        return self.reinforcement.As

    @property
    def rho(self) -> float:
        return self.As / self.Ac

    @property
    def Iy(self) -> float:
        return self.b * self.h ** 3 / 12.0

    @property
    def Iz(self) -> float:
        return self.h * self.b ** 3 / 12.0

    @property
    def iy(self) -> float:
        return sqrt(self.Iy / self.Ac)

    @property
    def iz(self) -> float:
        return sqrt(self.Iz / self.Ac)

    def min_longitudinal_As(self, NEd: float) -> float:
        """
        Minimum pratique EC2 usuel pour poteaux :
        As,min = max(0.10 NEd/fyd ; 0.002 Ac).
        """
        return max(0.10 * max(NEd, 0.0) / self.steel.fyd, 0.002 * self.Ac)

    def max_longitudinal_As(self) -> float:
        """Limite usuelle : 4 % Ac hors zones de recouvrement."""
        return 0.04 * self.Ac

    def axial_resistance_max(self) -> float:
        """
        Résistance axiale compression centrée approchée.
        Le coefficient 0.85 est conservateur pour intégrer les effets de longue durée
        et les imperfections non modélisées.
        """
        return 0.85 * self.concrete.fcd * self.Ac + self.steel.fyd * self.As

    def _fiber_centers(self) -> Iterable[Tuple[float, float, float]]:
        dy = self.b / self.mesh_ny
        dz = self.h / self.mesh_nz
        area = dy * dz
        y_start = -self.b / 2.0 + dy / 2.0
        z_start = -self.h / 2.0 + dz / 2.0
        for i in range(self.mesh_ny):
            y = y_start + i * dy
            for j in range(self.mesh_nz):
                z = z_start + j * dz
                yield y, z, area

    def response(self, eps0: float, k_y: float, k_z: float) -> Tuple[float, float, float]:
        """
        Résultantes N, My, Mz pour le champ :
            eps(y,z) = eps0 + k_y*z + k_z*y

        Retour :
            N en N ; My, Mz en N.m
        """
        N = 0.0
        My = 0.0
        Mz = 0.0

        for y, z, area in self._fiber_centers():
            eps = eps0 + k_y * z + k_z * y
            sig_c = self.concrete.stress(eps)
            dN = sig_c * area
            N += dN
            My += dN * z
            Mz += dN * y

        # Acier : on ajoute seulement le supplément acier - béton remplacé
        for bar in self.reinforcement.bars:
            eps = eps0 + k_y * bar.z + k_z * bar.y
            sig_s = self.steel.stress(eps)
            sig_c_at_bar = self.concrete.stress(eps)
            dN = (sig_s - sig_c_at_bar) * bar.area
            N += dN
            My += dN * bar.z
            Mz += dN * bar.y

        return N, My, Mz

    def _strain_plane_from_neutral_axis(
        self,
        axis: str,
        edge_sign: int,
        c: float,
    ) -> Tuple[float, float, float]:
        """
        Plan de déformation avec eps_cu sur l'arête comprimée.

        axis = 'y' : courbure selon z, moment My.
        axis = 'z' : courbure selon y, moment Mz.
        edge_sign = +1 ou -1.
        c : distance de l'arête comprimée à l'axe neutre, m.
        """
        eps_cu = self.concrete.eps_cu2
        if c <= 0:
            raise ValueError("c doit être positif.")

        if axis == "y":
            z_edge = edge_sign * self.h / 2.0
            z_na = z_edge - edge_sign * c
            k_y = eps_cu / (z_edge - z_na)
            eps0 = -k_y * z_na
            return eps0, k_y, 0.0

        if axis == "z":
            y_edge = edge_sign * self.b / 2.0
            y_na = y_edge - edge_sign * c
            k_z = eps_cu / (y_edge - y_na)
            eps0 = -k_z * y_na
            return eps0, 0.0, k_z

        raise ValueError("axis doit valoir 'y' ou 'z'.")

    def interaction_curve_uniaxial(
        self,
        axis: str,
        n_points: int = 220,
        c_min_ratio: float = 0.02,
        c_max_ratio: float = 40.0,
    ) -> List[Tuple[float, float]]:
        """
        Courbe N-M uniaxiale enveloppe.
        axis='y' retourne [(N, |My|)], axis='z' retourne [(N, |Mz|)].
        """
        if axis not in ("y", "z"):
            raise ValueError("axis doit valoir 'y' ou 'z'.")

        dim = self.h if axis == "y" else self.b
        c_min = max(c_min_ratio * dim, 0.002)
        c_max = c_max_ratio * dim

        # Échelle logarithmique pour couvrir flexion forte et compression quasi-centrée
        ratios = []
        for i in range(n_points):
            t = i / (n_points - 1)
            c = c_min * (c_max / c_min) ** t
            ratios.append(c)

        pts: List[Tuple[float, float]] = []

        # Deux signes de flexion
        for edge_sign in (+1, -1):
            for c in ratios:
                eps0, ky, kz = self._strain_plane_from_neutral_axis(axis, edge_sign, c)
                N, My, Mz = self.response(eps0, ky, kz)
                M = abs(My if axis == "y" else Mz)
                pts.append((N, M))

        # Point compression centrée
        N0, My0, Mz0 = self.response(self.concrete.eps_cu2, 0.0, 0.0)
        pts.append((N0, abs(My0 if axis == "y" else Mz0)))

        # Point traction pure acier à la limite élastique de calcul
        Nt, Myt, Mzt = self.response(-self.steel.eps_yd, 0.0, 0.0)
        pts.append((Nt, abs(Myt if axis == "y" else Mzt)))

        return pts

    def moment_capacity_at_N(self, NEd: float, axis: str) -> float:
        """
        Capacité MRd uniaxiale au niveau NEd par interpolation de l'enveloppe.
        Retourne 0 si NEd est hors domaine.
        """
        pts = self.interaction_curve_uniaxial(axis=axis)
        n_min = min(p[0] for p in pts)
        n_max = max(p[0] for p in pts)

        if NEd < n_min or NEd > n_max:
            return 0.0

        m_candidates: List[float] = []

        # Interpolation sur tous les segments qui croisent NEd
        for (n1, m1), (n2, m2) in zip(pts[:-1], pts[1:]):
            if (n1 - NEd) == 0.0:
                m_candidates.append(m1)
            if (n1 - NEd) * (n2 - NEd) <= 0.0 and n1 != n2:
                t = (NEd - n1) / (n2 - n1)
                if 0.0 <= t <= 1.0:
                    m_candidates.append(m1 + t * (m2 - m1))

        # Recherche par voisinage si interpolation pauvre
        if not m_candidates:
            pts_sorted = sorted(pts, key=lambda x: abs(x[0] - NEd))[:8]
            m_candidates = [m for _, m in pts_sorted]

        return max(m_candidates) if m_candidates else 0.0

    def design_moments_with_min_eccentricity(self, forces: ColumnForces) -> Tuple[float, float]:
        """
        Application d'une excentricité minimale pratique :
        e_min = max(dim/30 ; 20 mm).
        """
        N = max(forces.NEd, 0.0)
        e_min_z = max(self.h / 30.0, 0.020)  # pour My
        e_min_y = max(self.b / 30.0, 0.020)  # pour Mz

        My = max(abs(forces.MEd_y), N * e_min_z)
        Mz = max(abs(forces.MEd_z), N * e_min_y)
        return My, Mz

    def slenderness(self, l0_y: Optional[float] = None, l0_z: Optional[float] = None) -> Dict[str, Optional[float]]:
        """
        Élancement géométrique lambda = l0/i.
        l0_y : longueur efficace pour flambement donnant moment autour y.
        l0_z : longueur efficace pour flambement donnant moment autour z.
        """
        return {
            "lambda_y": None if l0_y is None else l0_y / self.iy,
            "lambda_z": None if l0_z is None else l0_z / self.iz,
        }

    def check(
        self,
        forces: ColumnForces,
        alpha_biaxial: float = 1.50,
        apply_min_eccentricity: bool = True,
        l0_y: Optional[float] = None,
        l0_z: Optional[float] = None,
    ) -> CheckResult:
        messages: List[str] = []

        As_min = self.min_longitudinal_As(forces.NEd)
        As_max = self.max_longitudinal_As()
        if self.As < As_min:
            messages.append(
                f"As < As_min : {m2_to_cm2(self.As):.2f} cm² < {m2_to_cm2(As_min):.2f} cm²."
            )
        if self.As > As_max:
            messages.append(
                f"As > As_max usuel : {m2_to_cm2(self.As):.2f} cm² > {m2_to_cm2(As_max):.2f} cm²."
            )

        My_used, Mz_used = (
            self.design_moments_with_min_eccentricity(forces)
            if apply_min_eccentricity
            else (abs(forces.MEd_y), abs(forces.MEd_z))
        )

        MRdy = self.moment_capacity_at_N(forces.NEd, axis="y")
        MRdz = self.moment_capacity_at_N(forces.NEd, axis="z")
        NRd = self.axial_resistance_max()

        if forces.NEd > NRd:
            messages.append(f"NEd > NRd,max : {forces.NEd / KN:.1f} kN > {NRd / KN:.1f} kN.")

        if MRdy <= 0.0 and My_used > 0.0:
            messages.append("MRd_y nul ou hors domaine d'interaction pour ce NEd.")
        if MRdz <= 0.0 and Mz_used > 0.0:
            messages.append("MRd_z nul ou hors domaine d'interaction pour ce NEd.")

        uy = 0.0 if My_used == 0.0 else My_used / MRdy if MRdy > 0 else float("inf")
        uz = 0.0 if Mz_used == 0.0 else Mz_used / MRdz if MRdz > 0 else float("inf")
        utilization = uy ** alpha_biaxial + uz ** alpha_biaxial

        slender = self.slenderness(l0_y=l0_y, l0_z=l0_z)
        for key, value in slender.items():
            if value is not None and value > 70.0:
                messages.append(
                    f"{key} = {value:.1f} : poteau très élancé, calcul du 2e ordre indispensable."
                )
            elif value is not None and value > 35.0:
                messages.append(
                    f"{key} = {value:.1f} : vérifier les effets du 2e ordre selon la méthode réglementaire."
                )

        clear = self.reinforcement.min_clear_spacing()
        if clear is not None and clear < 0.02:
            messages.append(f"Espacement libre minimal faible : {clear*100:.1f} cm.")

        ok = utilization <= 1.0 and not any(msg.startswith(("As <", "As >", "NEd >")) for msg in messages)
        if utilization > 1.0:
            messages.append(f"Interaction biaxiale non vérifiée : taux = {utilization:.3f} > 1.000.")
        else:
            messages.append(f"Interaction biaxiale vérifiée : taux = {utilization:.3f} <= 1.000.")

        return CheckResult(
            ok=ok,
            utilization=utilization,
            NEd_kN=forces.NEd_kN,
            MEd_y_used_kNm=My_used / KNM,
            MEd_z_used_kNm=Mz_used / KNM,
            MRd_y_kNm=MRdy / KNM,
            MRd_z_kNm=MRdz / KNM,
            NRd_max_kN=NRd / KN,
            As_cm2=m2_to_cm2(self.As),
            rho_percent=100.0 * self.rho,
            min_spacing_cm=None if clear is None else clear * 100.0,
            messages=messages,
        )


# ---------------------------------------------------------------------------
# Pré-dimensionnement automatique
# ---------------------------------------------------------------------------

@dataclass
class ReinforcementProposal:
    column: RectangularColumn
    result: CheckResult
    n_bars: int
    phi_mm: float


def suggest_reinforcement(
    b: float,
    h: float,
    forces: ColumnForces,
    concrete: Concrete = Concrete(),
    steel: Steel = Steel(),
    cover: float = 0.03,
    link_phi_mm: float = 8.0,
    phi_list_mm: Sequence[float] = (12, 14, 16, 20, 25, 32),
    n_bars_list: Sequence[int] = (4, 6, 8, 10, 12, 14, 16, 20, 24),
    alpha_biaxial: float = 1.50,
    l0_y: Optional[float] = None,
    l0_z: Optional[float] = None,
    mesh: int = 36,
) -> Optional[ReinforcementProposal]:
    """
    Cherche une combinaison simple n x HAphi vérifiant la section.
    La solution retournée est la moins armée parmi les candidats vérifiés.
    """
    # Candidats (n, phi) tries par acier croissant : on verifie dans cet ordre
    # et on retourne le PREMIER qui passe (= solution la moins armee), ce qui
    # evite de tester toutes les combinaisons (performance).
    candidates = [
        (n, phi)
        for n in n_bars_list if n >= 4 and n % 2 == 0
        for phi in phi_list_mm
    ]
    candidates.sort(key=lambda c: (c[0] * phi_area_m2(c[1]), c[1], c[0]))

    for n, phi in candidates:
        try:
            layout = ReinforcementLayout.rectangular_perimeter(
                b=b, h=h, cover=cover, link_phi_mm=link_phi_mm,
                main_phi_mm=phi, n_total=n,
            )
            col = RectangularColumn(
                b=b, h=h, concrete=concrete, steel=steel,
                reinforcement=layout, cover=cover, mesh_ny=mesh, mesh_nz=mesh,
            )
            res = col.check(
                forces=forces, alpha_biaxial=alpha_biaxial,
                apply_min_eccentricity=True, l0_y=l0_y, l0_z=l0_z,
            )
            if res.ok:
                return ReinforcementProposal(col, res, n, phi)
        except Exception:
            continue

    return None
