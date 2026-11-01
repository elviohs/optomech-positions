# =============================================================================
# materials.py — Curvas de dilatación térmica de materiales (formato NIST)
# =============================================================================
# Definición usada (la de la base de datos criogénica de NIST):
#     ε(T) = (L(T) - L293) / L293
#
# Tipos admitidos en materiales.json:
#   "nist_poly": ε(T) = escala · Σ coef[i]·T^i        (válido entre t_min y t_max)
#                opcional t_low / f_low: ε = escala·f_low para T < t_low (como en NIST)
#   "tabla":     ε(T) interpolada linealmente en una tabla T / dL_L (·escala)
#
# A partir de ε(T):
#   α(T)          = (dε/dT) / (1 + ε(T))                    CTE instantáneo
#   factor(Tc,Tw) = (1 + ε(Tw)) / (1 + ε(Tc)) - 1          L(Tw) = L(Tc)·(1 + factor)
#   Δε(T0→T1)     = (ε(T1) - ε(T0)) / (1 + ε(T0))          deformación térmica entre dos estados
# =============================================================================

import json
from bisect import bisect_left
from pathlib import Path

MAT_FILE = Path(__file__).with_name("materiales.json")


class Material:
    def __init__(self, name, d):
        self.name = name
        self.kind = d["tipo"]
        self.scale = float(d.get("escala", 1.0))
        self.t_min = float(d.get("t_min", 0.0))
        self.t_max = float(d.get("t_max", 1e9))
        self.source = d.get("fuente", "")
        self.verified = bool(d.get("verificado", False))
        self.fit_error_pct = d.get("error_ajuste_pct")
        if self.kind == "nist_poly":
            self.coef = [float(c) for c in d["coef"]]
            # Tramo constante NIST: y = f para T < T_low
            self.t_low = float(d["t_low"]) if "t_low" in d else None
            self.f_low = float(d["f_low"]) if "f_low" in d else None
        elif self.kind == "tabla":
            pts = sorted(zip(map(float, d["T"]), map(float, d["dL_L"])))
            self.tt = [p[0] for p in pts]
            self.ee = [p[1] for p in pts]
            if len(self.tt) < 2:
                raise ValueError(f"{name}: la tabla necesita al menos 2 puntos")
            self.t_min, self.t_max = self.tt[0], self.tt[-1]
        else:
            raise ValueError(f"{name}: tipo de curva desconocido '{self.kind}'")

    # ---------------------------------------------------------------------
    def in_range(self, T):
        return self.t_min - 1e-9 <= T <= self.t_max + 1e-9

    def strain(self, T):
        """ε(T) adimensional."""
        if self.kind == "nist_poly":
            if self.t_low is not None and self.f_low is not None and T < self.t_low:
                return self.scale * self.f_low
            return self.scale * sum(c * T ** i for i, c in enumerate(self.coef))
        i = min(max(bisect_left(self.tt, T), 1), len(self.tt) - 1)
        t0, t1 = self.tt[i - 1], self.tt[i]
        e0, e1 = self.ee[i - 1], self.ee[i]
        return self.scale * (e0 + (e1 - e0) * (T - t0) / (t1 - t0))

    def dstrain(self, T):
        if self.kind == "nist_poly":
            if self.t_low is not None and self.f_low is not None and T < self.t_low:
                return 0.0
            return self.scale * sum(i * c * T ** (i - 1) for i, c in enumerate(self.coef) if i)
        h = 0.5
        return (self.strain(T + h) - self.strain(T - h)) / (2 * h)

    def alpha(self, T):
        """CTE instantáneo (1/K)."""
        return self.dstrain(T) / (1.0 + self.strain(T))

    def factor(self, t_cold, t_warm):
        return (1.0 + self.strain(t_warm)) / (1.0 + self.strain(t_cold)) - 1.0

    def mean_cte(self, t_cold, t_warm):
        return self.factor(t_cold, t_warm) / (t_warm - t_cold)

    def delta_strain(self, t0, t1):
        return (self.strain(t1) - self.strain(t0)) / (1.0 + self.strain(t0))


_cache = {"mtime": None, "mats": {}}


def load_materials(path=MAT_FILE):
    """Lee materiales.json (con caché; se recarga si el fichero cambia)."""
    path = Path(path)
    if not path.exists():
        return {}
    mtime = path.stat().st_mtime
    if _cache["mtime"] != mtime:
        raw = json.loads(path.read_text(encoding="utf-8"))
        _cache["mats"] = {n: Material(n, d) for n, d in raw.get("materiales", {}).items()
                          if not n.startswith("_")}
        _cache["mtime"] = mtime
    return _cache["mats"]


def get_material(name):
    if not name:
        return None
    mats = load_materials()
    if name not in mats:
        raise ValueError(f"Material '{name}' no encontrado en {MAT_FILE.name}")
    return mats[name]
