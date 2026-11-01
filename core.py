# =============================================================================
# core.py — Motor de cálculo genérico (sin dependencias de interfaz)
# =============================================================================
# Zemax (frío) -> CREO (frío / caliente / redondeado / back-calc)
# + estudio de estabilidad térmica a partir de ficheros de temperatura ANSYS.
#
# Convenciones (verificadas contra la herramienta de conversión Zemax-CREO del departamento):
#   - Zemax:  R = Rx(tx)·Ry(ty)·Rz(tz), columnas = ejes locales en global.
#   - CREO:   R = Rz(tz)·Ry(ty)·Rx(tx)  ->  ty = asin(-R20), tx = atan2(R21,R22),
#             tz = atan2(R10,R00).
#   - Gimbal lock (ty = ±90°): tz = 0 y tx = atan2(±R01, ±R02).
#   - Térmica: P_caliente = P_ref + (P_frío - P_ref)·(1 + f),  f = CTE·ΔT
#     (o factor total introducido directamente).
#   - Redondeo: mitad hacia fuera (igual que ROUND de Excel).
# =============================================================================

from __future__ import annotations

import heapq
import math
import re
from dataclasses import dataclass, field, asdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import materials

ZEMAX_SECTION_START = "GLOBAL VERTEX COORDINATES"
ZEMAX_SECTION_END = "GLOBAL SURFACE CENTER OF CURVATURE"

DEFAULT_IGNORE = {"tilt x", "tilt y", "tilt z", "field rotation"}

GIMBAL_TOL = 1e-6


# -----------------------------------------------------------------------------
# Estructuras de datos
# -----------------------------------------------------------------------------

@dataclass
class Surface:
    """Una superficie de la sección de coordenadas globales de Zemax."""
    surf_id: int
    comment: str
    R: list            # 3x3, R[fila][col]
    x: float
    y: float
    z: float
    tilt_x: float      # ángulos Zemax tal como los imprime el fichero
    tilt_y: float
    tilt_z: float


@dataclass
class ElementCfg:
    """Configuración de un elemento optomecánico (editable en la GUI)."""
    surf_id: int
    zemax_label: str
    acronym: str
    description: str = ""
    include: bool = True
    pos_offset: int = 0              # superficies a avanzar SOLO para X,Y,Z
    pos_step: str = ""               # intervalo de tolerancia de posición (mm); vacío = valor por defecto
    ang_step: str = ""               # intervalo de tolerancia angular (°); vacío = valor por defecto
    override: str = ""               # "tx;ty;tz" en convención CREO, vacío = automático
    fem_point: str = ""              # "x;y" punto de muestreo FEM (vacío = posición del elemento)


@dataclass
class Params:
    t_cold_k: float = 130.0
    t_warm_k: float = 293.0
    cte_mean_ppm: float = 20.67      # CTE medio entre T_frío y T_caliente (conversión frío<->caliente)
    use_manual_factor: bool = False
    manual_factor_pct: float = 0.337 # factor total en % (como 'factorAL' de la hoja original)
    ref_x: float = 0.0               # punto fijo del banco (no se mueve con la temperatura)
    ref_y: float = 0.0
    ref_z: float = 0.0
    round_pos_mm: float = 0.1
    round_ang_deg: float = 0.1
    ignore_labels: str = "tilt x; tilt y; tilt z; field rotation"   # etiquetas Zemax auxiliares
    backcalc_mode: str = "exacto"    # "exacto" | "excel"
    # Estabilidad
    cte_stab_ppm: float = 20.67      # CTE instantáneo a la T de operación
    fem_units: str = "auto"          # "auto" | "mm" | "m"
    fem_nodes: int = 5
    fem_model: str = "trayectoria"   # "local" | "trayectoria"
    fem_warn_mm: float = 50.0
    # Material (curva NIST / tabla en materiales.json)
    material: str = ""               # vacío = usar los CTE introducidos a mano
    mat_for_conversion: bool = False # usar la curva para el factor frío<->caliente
    mat_for_stability: bool = True   # usar la curva para el estudio de estabilidad

    def mat(self):
        return materials.get_material(self.material) if self.material else None

    @property
    def factor(self) -> float:
        if self.use_manual_factor:
            return self.manual_factor_pct / 100.0
        m = self.mat()
        if m and self.mat_for_conversion:
            return m.factor(self.t_cold_k, self.t_warm_k)
        return self.cte_mean_ppm * 1e-6 * (self.t_warm_k - self.t_cold_k)

    def factor_source(self) -> str:
        if self.use_manual_factor:
            return f"factor manual {self.manual_factor_pct} %"
        if self.material and self.mat_for_conversion:
            return f"curva '{self.material}' entre {self.t_cold_k} y {self.t_warm_k} K"
        return f"CTE medio {self.cte_mean_ppm} ppm/K x {self.t_warm_k - self.t_cold_k:.1f} K"

    def stability_source(self) -> str:
        if self.material and self.mat_for_stability:
            return f"curva '{self.material}' (Δε = ε(T1) - ε(T0) por nodo)"
        return f"CTE constante {self.cte_stab_ppm} ppm/K"


def check_material(prm: "Params", log=print):
    """Avisos sobre el material: rango de validez y verificación de coeficientes."""
    m = prm.mat()
    if not m:
        return
    if not m.verified:
        log(f"[AVISO] Los coeficientes de '{m.name}' están marcados como NO verificados en "
            f"materiales.json. Compruébalos contra la fuente: {m.source}")
    for T in (prm.t_cold_k, prm.t_warm_k):
        if prm.mat_for_conversion and not m.in_range(T):
            log(f"[AVISO] {T} K está fuera del rango de validez de '{m.name}' "
                f"({m.t_min}-{m.t_max} K).")
    log(f"  Material {m.name}: α({prm.t_cold_k:g} K) = {m.alpha(prm.t_cold_k) * 1e6:.2f} ppm/K, "
        f"factor {prm.t_cold_k:g}->{prm.t_warm_k:g} K = {m.factor(prm.t_cold_k, prm.t_warm_k):.6f} "
        f"(CTE medio {m.mean_cte(prm.t_cold_k, prm.t_warm_k) * 1e6:.2f} ppm/K)")


@dataclass
class Pose:
    x: float
    y: float
    z: float
    tx: float
    ty: float
    tz: float

    def as_list(self):
        return [self.x, self.y, self.z, self.tx, self.ty, self.tz]


@dataclass
class ElementResult:
    cfg: ElementCfg
    surface: Surface          # superficie etiquetada (ángulos)
    pos_surface: Surface      # superficie usada para X,Y,Z (offset)
    cold: Pose
    warm: Pose
    warm_rnd: Pose
    cold_back: Pose
    override_used: bool = False
    override_dev_deg: float = 0.0
    pos_step: float = 0.0
    ang_step: float = 0.0


@dataclass
class StabilityResult:
    acronym: str
    sample_x: float
    sample_y: float
    mean_dT: float
    n_nodes: int
    min_dist: float
    dX: float
    dY: float
    dX_loc: float
    dY_loc: float
    dZ_loc: float


# -----------------------------------------------------------------------------
# Utilidades numéricas
# -----------------------------------------------------------------------------

def _f(s: str) -> float:
    s = s.strip().replace(",", ".")
    if s.endswith("."):
        s += "0"
    return float(s)


def round_excel(value: float, step: float) -> float:
    """Redondeo al múltiplo de 'step' con mitades hacia fuera (ROUND de Excel)."""
    if step <= 0:
        return value
    v = Decimal(f"{value:.9f}")          # quita ruido binario (Excel trabaja a 15 cifras)
    s = Decimal(str(step))
    return float((v / s).to_integral_value(rounding=ROUND_HALF_UP) * s) + 0.0  # evita -0.0


def _rx(a):
    a = math.radians(a); c, s = math.cos(a), math.sin(a)
    return [[1, 0, 0], [0, c, -s], [0, s, c]]


def _ry(a):
    a = math.radians(a); c, s = math.cos(a), math.sin(a)
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]


def _rz(a):
    a = math.radians(a); c, s = math.cos(a), math.sin(a)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def _mm(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _tr(A):
    return [[A[j][i] for j in range(3)] for i in range(3)]


def creo_matrix(tx, ty, tz):
    return _mm(_mm(_rz(tz), _ry(ty)), _rx(tx))


def rotation_angle_between(A, B) -> float:
    """Ángulo (grados) de la rotación que lleva A a B."""
    M = _mm(_tr(A), B)
    c = (M[0][0] + M[1][1] + M[2][2] - 1.0) / 2.0
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def r_to_creo_angles(R):
    """Ángulos CREO (tx, ty, tz) en grados a partir de la matriz R de Zemax."""
    s = max(-1.0, min(1.0, -R[2][0]))
    ty = math.degrees(math.asin(s))
    if abs(abs(s) - 1.0) < GIMBAL_TOL:
        sign = 1.0 if s > 0 else -1.0
        tx = math.degrees(math.atan2(sign * R[0][1], sign * R[0][2]))
        tz = 0.0
    else:
        tx = math.degrees(math.atan2(R[2][1], R[2][2]))
        tz = math.degrees(math.atan2(R[1][0], R[0][0]))
    return tx, ty, tz


def parse_triplet(text: str, n: int):
    parts = [p for p in re.split(r"[;\s]+", text.strip().replace(",", ".")) if p]
    if len(parts) != n:
        raise ValueError(f"Se esperaban {n} valores separados por ';' y se recibió '{text}'")
    return [float(p) for p in parts]


# -----------------------------------------------------------------------------
# Lectura de Zemax
# -----------------------------------------------------------------------------

_NUM = r"([+-]?\d[\d,\.]*(?:[Ee][+-]?\d+)?)"
_RE_SURF = re.compile(r"^\s*(\d+)\s+" + r"\s+".join([_NUM] * 5) + r"[ \t]*(.*)$")
_RE_CONT = re.compile(r"^\s+" + r"\s+".join([_NUM] * 5) + r"\s*$")


def _read_text_any(path: Path) -> str:
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def read_zemax(path) -> tuple[list[Surface], dict]:
    """Lee todas las superficies de la sección GLOBAL VERTEX del prescription data."""
    path = Path(path)
    lines = _read_text_any(path).splitlines()
    info = {"reference_surface": None, "file": path.name}

    start = end = None
    for i, ln in enumerate(lines):
        if start is None and ZEMAX_SECTION_START in ln.upper():
            start = i
        elif start is not None and ZEMAX_SECTION_END in ln.upper():
            end = i
            break
    if start is None:
        raise ValueError("No se encuentra la sección 'GLOBAL VERTEX COORDINATES'. "
                         "Exporta el Prescription Data con las coordenadas globales activadas.")
    section = lines[start:end]

    for ln in section[:15]:
        m = re.search(r"Reference Surface\s*:\s*(\d+)", ln, re.I)
        if m:
            info["reference_surface"] = int(m.group(1))

    surfaces = []
    i = 0
    while i < len(section) - 2:
        m1 = _RE_SURF.match(section[i])
        m2 = _RE_CONT.match(section[i + 1]) if m1 else None
        m3 = _RE_CONT.match(section[i + 2]) if m2 else None
        if not (m1 and m2 and m3):
            i += 1
            continue
        g1, g2, g3 = m1.groups(), m2.groups(), m3.groups()
        R = [[_f(g1[1]), _f(g1[2]), _f(g1[3])],
             [_f(g2[0]), _f(g2[1]), _f(g2[2])],
             [_f(g3[0]), _f(g3[1]), _f(g3[2])]]
        surfaces.append(Surface(
            surf_id=int(g1[0]), comment=g1[6].strip(), R=R,
            x=_f(g1[4]), y=_f(g2[3]), z=_f(g3[3]),
            tilt_x=_f(g1[5]), tilt_y=_f(g2[4]), tilt_z=_f(g3[4]),
        ))
        i += 3
    if not surfaces:
        raise ValueError("La sección de coordenadas globales está vacía o tiene un formato no reconocido.")
    return surfaces, info


def parse_ignore(text: str) -> set:
    return {t.strip().lower() for t in re.split(r"[;\n]", text or "") if t.strip()}


def default_elements(surfaces: list[Surface], show_all: bool = False,
                     ignore: str = "") -> list[ElementCfg]:
    ign = parse_ignore(ignore) if ignore else DEFAULT_IGNORE
    out = []
    for s in surfaces:
        c = s.comment
        if not show_all and (not c or c.lower() in ign):
            continue
        acr = re.sub(r"[^A-Za-z0-9_]", "", c.split()[-1]).upper() if c else f"S{s.surf_id}"
        out.append(ElementCfg(surf_id=s.surf_id, zemax_label=c, acronym=acr, include=bool(c)))
    return out


# -----------------------------------------------------------------------------
# Conversión térmica frío <-> caliente
# -----------------------------------------------------------------------------

def cold_to_warm(p: Pose, prm: Params) -> Pose:
    k = 1.0 + prm.factor
    return Pose(prm.ref_x + (p.x - prm.ref_x) * k,
                prm.ref_y + (p.y - prm.ref_y) * k,
                prm.ref_z + (p.z - prm.ref_z) * k,
                p.tx, p.ty, p.tz)


def warm_to_cold(p: Pose, prm: Params) -> Pose:
    f = prm.factor
    if prm.backcalc_mode == "excel":
        # Réplica de la hoja original: cold = warm·(1-f) en los 3 ejes desde el origen.
        return Pose(p.x * (1 - f), p.y * (1 - f), p.z * (1 - f), p.tx, p.ty, p.tz)
    k = 1.0 + f
    return Pose(prm.ref_x + (p.x - prm.ref_x) / k,
                prm.ref_y + (p.y - prm.ref_y) / k,
                prm.ref_z + (p.z - prm.ref_z) / k,
                p.tx, p.ty, p.tz)


def element_steps(cfg: "ElementCfg", prm: Params):
    """Intervalos de tolerancia (posición mm, ángulo °) aplicables a un elemento."""
    ps = float(cfg.pos_step.replace(",", ".")) if cfg.pos_step.strip() else prm.round_pos_mm
    an = float(cfg.ang_step.replace(",", ".")) if cfg.ang_step.strip() else prm.round_ang_deg
    return ps, an


def round_pose(p: Pose, pos_step: float, ang_step: float) -> Pose:
    a, s = ang_step, pos_step
    return Pose(round_excel(p.x, s), round_excel(p.y, s), round_excel(p.z, s),
                round_excel(p.tx, a), round_excel(p.ty, a), round_excel(p.tz, a))


def compute_positions(surfaces, elements, prm: Params, log=print) -> list[ElementResult]:
    by_index = {s.surf_id: i for i, s in enumerate(surfaces)}
    results = []
    for cfg in elements:
        if not cfg.include:
            continue
        if cfg.surf_id not in by_index:
            log(f"[ERROR] {cfg.acronym}: la superficie {cfg.surf_id} no existe en el fichero Zemax.")
            continue
        idx = by_index[cfg.surf_id]
        surf = surfaces[idx]
        if surf.comment != cfg.zemax_label:
            log(f"[AVISO] {cfg.acronym}: la superficie {cfg.surf_id} ahora se llama "
                f"'{surf.comment}' (perfil: '{cfg.zemax_label}'). ¿Ha cambiado la numeración en Zemax?")
        pidx = idx + cfg.pos_offset
        if not 0 <= pidx < len(surfaces):
            log(f"[ERROR] {cfg.acronym}: offset de posición fuera de rango.")
            continue
        psurf = surfaces[pidx]

        tx, ty, tz = r_to_creo_angles(surf.R)
        used = False
        dev = 0.0
        if cfg.override.strip():
            otx, oty, otz = parse_triplet(cfg.override, 3)
            dev = rotation_angle_between(creo_matrix(otx, oty, otz), surf.R)
            tx, ty, tz = otx, oty, otz
            used = True
            if dev > 0.01:
                log(f"[AVISO] {cfg.acronym}: el override ({otx}, {oty}, {otz}) cambia la "
                    f"orientación física respecto a Zemax en {dev:.2f}°. Compruébalo en CREO.")
        elif abs(abs(ty) - 90.0) < 1e-4:
            log(f"[INFO] {cfg.acronym}: ty = ±90° (gimbal lock). Convención automática tz = 0.")

        cold = Pose(psurf.x, psurf.y, psurf.z, tx, ty, tz)
        warm = cold_to_warm(cold, prm)
        ps, an = element_steps(cfg, prm)
        warm_r = round_pose(warm, ps, an)
        back = warm_to_cold(warm_r, prm)
        results.append(ElementResult(cfg, surf, psurf, cold, warm, warm_r, back, used, dev, ps, an))
    return results


# -----------------------------------------------------------------------------
# Estabilidad: ficheros ANSYS
# -----------------------------------------------------------------------------

@dataclass
class FEMData:
    ids: list
    x: list
    y: list
    z: list
    t: list
    units_detected: str
    path: str


def _split_row(line: str):
    if "\t" in line:
        return line.split("\t")
    if ";" in line:
        return line.split(";")
    return line.split()


def read_fem(path, units: str = "auto", log=print) -> FEMData:
    path = Path(path)
    text = _read_text_any(path).splitlines()
    if not text:
        raise ValueError(f"Fichero vacío: {path.name}")
    header = text[0]
    hdr_unit = None
    m = re.search(r"X Location\s*\(([^)]+)\)", header, re.I)
    if m:
        hdr_unit = m.group(1).strip().lower()

    ids, xs, ys, zs, ts = [], [], [], [], []
    for ln in text[1:]:
        p = _split_row(ln.strip())
        if len(p) < 5:
            continue
        try:
            ids.append(int(float(_f(p[0]))))
            xs.append(_f(p[1])); ys.append(_f(p[2])); zs.append(_f(p[3])); ts.append(_f(p[4]))
        except ValueError:
            continue
    if not ids:
        raise ValueError(f"No se han podido leer nodos en {path.name}")

    extent = max(max(xs) - min(xs), max(ys) - min(ys))
    if units == "auto":
        if hdr_unit in ("m", "meter", "metre"):
            scale, det = 1000.0, "m (cabecera)"
        elif hdr_unit == "mm":
            scale, det = 1.0, "mm (cabecera)"
            if extent < 20:
                log(f"[AVISO] {path.name}: la cabecera dice mm pero la extensión de la malla es "
                    f"{extent:.3f}. Parece que está en metros; se convierte a mm.")
                scale, det = 1000.0, "m (deducido por extensión)"
        else:
            scale, det = (1000.0, "m (deducido)") if extent < 20 else (1.0, "mm (deducido)")
    else:
        scale, det = (1000.0, "m (forzado)") if units == "m" else (1.0, "mm (forzado)")

    if scale != 1.0:
        xs = [v * scale for v in xs]; ys = [v * scale for v in ys]; zs = [v * scale for v in zs]
    log(f"  {path.name}: {len(ids)} nodos, unidades {det}, "
        f"X [{min(xs):.0f}, {max(xs):.0f}] mm, Y [{min(ys):.0f}, {max(ys):.0f}] mm")
    return FEMData(ids, xs, ys, zs, ts, det, str(path))


class _Grid:
    """Índice espacial 2D sencillo para buscar los k nodos más cercanos en X-Y."""

    def __init__(self, xs, ys, vals, cell=25.0):
        self.cell = cell
        self.cells = {}
        self.xs, self.ys, self.vals = xs, ys, vals
        self.minx, self.maxx = min(xs), max(xs)
        self.miny, self.maxy = min(ys), max(ys)
        for i, (x, y) in enumerate(zip(xs, ys)):
            self.cells.setdefault((int(math.floor(x / cell)), int(math.floor(y / cell))), []).append(i)

    def knn(self, x, y, k):
        cx, cy = int(math.floor(x / self.cell)), int(math.floor(y / self.cell))
        max_r = int(max(abs(x - self.minx), abs(x - self.maxx), abs(y - self.miny),
                        abs(y - self.maxy)) / self.cell) + 2
        found = []
        r = 0
        while r <= max_r:
            for ix in range(cx - r, cx + r + 1):
                for iy in range(cy - r, cy + r + 1):
                    if max(abs(ix - cx), abs(iy - cy)) != r:
                        continue
                    for i in self.cells.get((ix, iy), ()):
                        d = math.hypot(self.xs[i] - x, self.ys[i] - y)
                        found.append((d, i))
            if len(found) >= k:
                best = heapq.nsmallest(k, found)
                if best[-1][0] <= r * self.cell:   # nada más cercano puede aparecer fuera
                    return best
            r += 1
        return heapq.nsmallest(k, found)


def build_dT_grid(fem0: FEMData, fem1: FEMData, prm: "Params", log=print) -> _Grid:
    """Índice con (ΔT, Δε) por nodo. Δε sale de la curva del material o de α·ΔT."""
    t1 = dict(zip(fem1.ids, fem1.t))
    m = prm.mat() if prm.mat_for_stability else None
    alpha = prm.cte_stab_ppm * 1e-6
    xs, ys, dts = [], [], []
    missing = out_range = 0
    for nid, x, y, t0 in zip(fem0.ids, fem0.x, fem0.y, fem0.t):
        if nid in t1:
            ta = t1[nid]
            if m:
                if not (m.in_range(t0) and m.in_range(ta)):
                    out_range += 1
                de = m.delta_strain(t0, ta)
            else:
                de = alpha * (ta - t0)
            xs.append(x); ys.append(y); dts.append((ta - t0, de))
        else:
            missing += 1
    if out_range:
        log(f"[AVISO] {out_range} nodos con temperaturas fuera del rango de validez de '{m.name}'.")
    if missing:
        log(f"[AVISO] {missing} nodos de T0 no están en {Path(fem1.path).name}; se ignoran.")
    if not xs:
        raise ValueError("No hay nodos comunes entre los dos ficheros FEM.")
    return _Grid(xs, ys, dts)


def compute_stability(results: list[ElementResult], grid: _Grid, prm: Params,
                      log=print) -> list[StabilityResult]:
    k = max(1, int(prm.fem_nodes))
    out = []
    for r in results:
        cfg = r.cfg
        ex, ey = r.cold.x, r.cold.y
        sx, sy = ex, ey
        if cfg.fem_point.strip():
            sx, sy = parse_triplet(cfg.fem_point, 2)

        best = grid.knn(sx, sy, k)
        dmin = best[0][0]
        local_dT = sum(grid.vals[i][0] for _, i in best) / len(best)
        local_de = sum(grid.vals[i][1] for _, i in best) / len(best)
        if dmin > prm.fem_warn_mm:
            log(f"[AVISO] {cfg.acronym}: nodo FEM más cercano a {dmin:.1f} mm del punto de "
                f"muestreo ({sx:.1f}, {sy:.1f}). Revisa unidades o el punto FEM.")

        vx, vy = ex - prm.ref_x, ey - prm.ref_y
        if prm.fem_model == "trayectoria":
            # Media de ΔT a lo largo del segmento punto fijo -> elemento (aprox. de α∫ΔT ds)
            n = 20
            acc_t = acc_e = 0.0
            for j in range(n):
                t = (j + 0.5) / n
                b = grid.knn(prm.ref_x + vx * t, prm.ref_y + vy * t, k)
                acc_t += sum(grid.vals[i][0] for _, i in b) / len(b)
                acc_e += sum(grid.vals[i][1] for _, i in b) / len(b)
            eff_dT, eff_de = acc_t / n, acc_e / n
        else:
            eff_dT, eff_de = local_dT, local_de

        dX = eff_de * vx
        dY = eff_de * vy
        # Mismo desplazamiento expresado en el sistema local de la superficie: d_loc = Rᵀ·d
        R = r.surface.R
        d = (dX, dY, 0.0)
        dl = [sum(R[i][j] * d[i] for i in range(3)) for j in range(3)]
        out.append(StabilityResult(cfg.acronym, sx, sy, eff_dT, len(best), dmin,
                                   dX, dY, dl[0], dl[1], dl[2]))
    return out


# -----------------------------------------------------------------------------
# Perfiles (JSON)
# -----------------------------------------------------------------------------

def _rel(p, base):
    """Ruta relativa a la carpeta del perfil si cuelga de ella (perfiles portables)."""
    if not p:
        return ""
    if base is None:
        return str(p)
    try:
        return str(Path(p).resolve().relative_to(Path(base).resolve()))
    except ValueError:
        return str(Path(p).resolve())


def _abs(p, base):
    if not p:
        return ""
    q = Path(p)
    if q.is_absolute() or base is None:
        return str(q)
    return str((Path(base) / q).resolve())


def profile_to_dict(zemax_path, prm, elements, fem_t0, fem_cases, out_dir, out_name, base=None):
    return {
        "version": 2,
        "zemax_file": _rel(zemax_path, base),
        "params": asdict(prm),
        "elements": [asdict(e) for e in elements],
        "fem_t0": _rel(fem_t0, base),
        "fem_cases": [{"label": l, "file": _rel(f, base)} for l, f in fem_cases],
        "out_dir": _rel(out_dir, base),
        "out_name": out_name or "",
    }


def profile_from_dict(d, base=None):
    prm = Params(**{k: v for k, v in d.get("params", {}).items() if k in Params.__dataclass_fields__})
    fine_old = d.get("params", {}).get("round_ang_fine_deg", 0.05)
    els = []
    for e in d.get("elements", []):
        cfg = ElementCfg(**{k: v for k, v in e.items() if k in ElementCfg.__dataclass_fields__})
        if e.get("fine_rounding") and not cfg.ang_step:      # perfiles de la versión anterior
            cfg.ang_step = str(fine_old)
        els.append(cfg)
    cases = [(c["label"], _abs(c["file"], base)) for c in d.get("fem_cases", [])]
    return _abs(d.get("zemax_file", ""), base), prm, els, _abs(d.get("fem_t0", ""), base), cases, \
        _abs(d.get("out_dir", ""), base), d.get("out_name", "")
