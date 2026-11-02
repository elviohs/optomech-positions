# =============================================================================
# geometry.py — Trazado del rayo central y comprobación de la ley de reflexión
# =============================================================================
# El rayo central se reconstruye como la poligonal que une, en orden de superficie:
#   punto inicial (última superficie etiquetada antes del primer elemento)
#   -> posición de cada elemento incluido (con su offset de posición)
#   -> punto final (última superficie con coordenadas finitas tras el último elemento)
#
# En cada elemento se compara la dirección de salida real con la que predice la
# ley de reflexión usando su normal (eje Z local de Zemax = columna 2 de R):
#     d_refl = d_in - 2·(d_in·n)·n
# Estados:
#   "ok"          reflexión coherente (error < tolerancia)
#   "transmisión" el rayo no cambia de dirección (lente, ventana, filtro…)
#   "error"       ni reflexión ni transmisión: revisar ángulos, posición u orden
#   "fuera de eje" el elemento usa offset de posición (vértice ≠ punto de impacto):
#                 la normal del vértice no sirve para comprobar la reflexión
#   "extremo"     primer/último punto del trazado
# =============================================================================
from __future__ import annotations

import math
from dataclasses import dataclass, field

FINITE_LIMIT = 1e6     # superficies más lejanas (objeto en el infinito) se ignoran


@dataclass
class PathNode:
    name: str
    p: tuple                      # posición global (mm)
    normal: tuple | None = None   # normal unitaria (orientada hacia el rayo incidente)
    is_element: bool = False
    status: str = "extremo"
    aoi_deg: float | None = None  # ángulo de incidencia
    err_deg: float | None = None  # error respecto a la ley de reflexión
    defl_deg: float | None = None # desviación total del rayo
    z_label: str = ""


def _sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _norm(v):
    m = math.sqrt(_dot(v, v))
    return tuple(c / m for c in v) if m > 1e-12 else None


def _ang(a, b):
    return math.degrees(math.acos(max(-1.0, min(1.0, _dot(a, b)))))


def _finite(s):
    return all(abs(c) < FINITE_LIMIT for c in (s.x, s.y, s.z))


def build_path(surfaces, elements, tol_deg: float = 0.05, ignore=None):
    """Devuelve (lista de PathNode, lista de avisos)."""
    warnings = []
    idx = {s.surf_id: i for i, s in enumerate(surfaces)}
    els = sorted([e for e in elements if e.include and e.surf_id in idx], key=lambda e: idx[e.surf_id])
    if not els:
        return [], ["No hay elementos incluidos."]

    ignore = {t.lower() for t in (ignore or ())}
    nodes = []
    first_i, last_i = idx[els[0].surf_id], idx[els[-1].surf_id] + els[-1].pos_offset
    fe, le = els[0], els[-1]
    p_first = surfaces[first_i + fe.pos_offset]
    p_last = surfaces[last_i]

    def distinct(s, ref):
        return math.dist((s.x, s.y, s.z), (ref.x, ref.y, ref.z)) > 1e-6

    def usable(s, ref):
        return _finite(s) and distinct(s, ref) and s.comment.lower() not in ignore

    # Punto inicial: última superficie etiquetada (no auxiliar) antes del primer elemento
    start = next((s for s in reversed(surfaces[:first_i]) if s.comment and usable(s, p_first)), None)
    if start is None:
        start = next((s for s in reversed(surfaces[:first_i]) if usable(s, p_first)), None)
    if start is not None:
        nodes.append(PathNode(start.comment or f"Sup {start.surf_id}", (start.x, start.y, start.z)))

    for e in els:
        i = idx[e.surf_id]
        s = surfaces[i]
        ps = surfaces[min(i + e.pos_offset, len(surfaces) - 1)]
        n = (s.R[0][2], s.R[1][2], s.R[2][2])
        node = PathNode(e.acronym, (ps.x, ps.y, ps.z), _norm(n), True, "")
        if e.pos_offset:
            node.status = "fuera de eje"
        nodes.append(node)

    # Punto final: última superficie finita después del último elemento
    end = next((s for s in reversed(surfaces[last_i + 1:]) if usable(s, p_last)), None)
    if end is not None:
        nodes.append(PathNode(end.comment or f"Sup {end.surf_id}", (end.x, end.y, end.z)))

    # Comprobaciones en los elementos interiores
    for k, nd in enumerate(nodes):
        nd.z_label = f"Z={nd.p[2]:.1f}"
        if not nd.is_element:
            continue
        if k == 0 or k == len(nodes) - 1:
            nd.status = nd.status or "extremo"
            continue
        d_in = _norm(_sub(nd.p, nodes[k - 1].p))
        d_out = _norm(_sub(nodes[k + 1].p, nd.p))
        if d_in is None or d_out is None:
            nd.status = nd.status or "extremo"
            warnings.append(f"{nd.name}: coincide con el punto anterior o el siguiente; "
                            f"no se puede comprobar la dirección del rayo.")
            continue
        nd.defl_deg = _ang(d_in, d_out)
        n = nd.normal
        if n is not None:
            if _dot(n, d_in) > 0:          # orientar la normal hacia el rayo incidente
                n = tuple(-c for c in n)
                nd.normal = n
            nd.aoi_deg = _ang(tuple(-c for c in d_in), n)
            refl = tuple(d_in[i] - 2 * _dot(d_in, n) * n[i] for i in range(3))
            nd.err_deg = _ang(refl, d_out)
        if nd.status == "fuera de eje":
            continue
        if nd.defl_deg < tol_deg:
            nd.status = "transmisión"
        elif nd.err_deg is not None and nd.err_deg < tol_deg:
            nd.status = "ok"
        else:
            nd.status = "error"
            warnings.append(f"{nd.name}: la dirección de salida no cumple la ley de reflexión "
                            f"(error {nd.err_deg:.3f}°). Revisa orientación, posición u orden "
                            f"de los elementos.")
    return nodes, warnings


PLANES = {"XY (planta, desde +Z)": (0, 1, 2), "XZ (alzado, desde −Y)": (0, 2, 1),
          "YZ (perfil, desde +X)": (1, 2, 0)}
