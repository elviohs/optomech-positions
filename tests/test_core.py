import json
import math
import random
from pathlib import Path

import pytest

import core

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "ejemplos" / "sistema_3_espejos"


def zemax_R(tx, ty, tz):
    """Matriz de Zemax: R = Rx·Ry·Rz (intrínseco)."""
    return core._mm(core._mm(core._rx(tx), core._ry(ty)), core._rz(tz))


def max_diff(A, B):
    return max(abs(A[i][j] - B[i][j]) for i in range(3) for j in range(3))


# ---------------------------------------------------------------- redondeo
@pytest.mark.parametrize("value, step, expected", [
    (-783.25, 0.1, -783.3),      # mitad hacia fuera (Python round() daría -783.2)
    (252.05, 0.1, 252.1),
    (41.457, 0.1, 41.5),
    (41.457, 0.05, 41.45),
    (-30.699, 0.05, -30.7),
    (-0.04, 0.1, 0.0),
])
def test_round_excel(value, step, expected):
    assert core.round_excel(value, step) == pytest.approx(expected)
    assert str(core.round_excel(-0.04, 0.1)) == "0.0"          # nunca -0.0


# ---------------------------------------------------------------- ángulos
def test_creo_angles_reproduce_orientation():
    random.seed(0)
    for _ in range(200):
        tx, ty, tz = (random.uniform(-170, 170) for _ in range(3))
        R = zemax_R(tx, ty, tz)
        cx, cy, cz = core.r_to_creo_angles(R)
        assert max_diff(core.creo_matrix(cx, cy, cz), R) < 1e-9


def test_gimbal_lock_convention():
    # Pliegue con ty_CREO = +90: convención tz = 0 y tx = atan2(R01, R02)
    R = zemax_R(-90, 59.3, 90)
    cx, cy, cz = core.r_to_creo_angles(R)
    assert (cx, cy, cz) == pytest.approx((-30.7, 90.0, 0.0), abs=1e-6)
    assert max_diff(core.creo_matrix(cx, cy, cz), R) < 1e-9


def test_rotation_angle_between():
    assert core.rotation_angle_between(core.creo_matrix(180, 90, 180), core.creo_matrix(0, 90, 0)) \
        == pytest.approx(0, abs=1e-6)
    assert core.rotation_angle_between(core.creo_matrix(0, 90, 0), core.creo_matrix(-16.5, 90, 0)) \
        == pytest.approx(16.5, abs=1e-6)


# ---------------------------------------------------------------- térmica
@pytest.mark.parametrize("mode", ["exacto"])
def test_cold_warm_roundtrip(mode):
    prm = core.Params(ref_x=10, ref_y=-20, ref_z=453.24, backcalc_mode=mode)
    p = core.Pose(-1050.5, 780.6, 252.647, 1, 2, 3)
    q = core.warm_to_cold(core.cold_to_warm(p, prm), prm)
    assert q.as_list() == pytest.approx(p.as_list(), abs=1e-9)


def test_fixed_point_does_not_move():
    prm = core.Params(ref_x=5, ref_y=6, ref_z=7)
    p = core.cold_to_warm(core.Pose(5, 6, 7, 0, 0, 0), prm)
    assert (p.x, p.y, p.z) == pytest.approx((5, 6, 7))


# ---------------------------------------------------------------- Zemax
def test_read_zemax_example():
    surfs, info = core.read_zemax(EXAMPLE / "zemax_ejemplo.txt")
    assert info["reference_surface"] == 1
    assert {"M1", "M2", "M3"} <= {s.comment for s in surfs}
    m3 = next(s for s in surfs if s.comment == "M3")
    assert (m3.x, m3.y, m3.z) == pytest.approx((-300, -400, 250))
    # R ortonormal y coherente con los ángulos Zemax impresos en el fichero
    RtR = core._mm(core._tr(m3.R), m3.R)
    assert max_diff(RtR, [[1, 0, 0], [0, 1, 0], [0, 0, 1]]) < 1e-8
    assert max_diff(zemax_R(m3.tilt_x, m3.tilt_y, m3.tilt_z), m3.R) < 1e-7


# ---------------------------------------------------------------- FEM
def _write_fem(path, unit, scale):
    rows = [f"Node Number\tX Location ({unit})\tY Location ({unit})\tZ Location ({unit})\tTemperature (K)"]
    for i, (x, y) in enumerate([(0, 0), (500, 0), (0, 400), (-600, -300)], 1):
        rows.append(f"{i}\t{x * scale:.4f}\t{y * scale:.4f}\t{0.15 * 1000 * scale:.4f}\t130,0".replace(".", ","))
    path.write_text("\n".join(rows), encoding="utf-8")


@pytest.mark.parametrize("unit, scale", [("mm", 1.0), ("m", 1e-3)])
def test_fem_units_from_header(tmp_path, unit, scale):
    f = tmp_path / "fem.txt"
    _write_fem(f, unit, scale)
    fem = core.read_fem(f, "auto", log=lambda m: None)
    assert max(fem.x) == pytest.approx(500)


def test_fem_units_wrong_header_detected(tmp_path):
    f = tmp_path / "fem.txt"
    _write_fem(f, "mm", 1e-3)          # cabecera dice mm pero los datos están en m
    msgs = []
    fem = core.read_fem(f, "auto", log=msgs.append)
    assert max(fem.x) == pytest.approx(500)
    assert any("metros" in m for m in msgs)


def test_knn_matches_brute_force():
    random.seed(3)
    xs = [random.uniform(-800, 800) for _ in range(3000)]
    ys = [random.uniform(-600, 600) for _ in range(3000)]
    g = core._Grid(xs, ys, [(0, 0)] * 3000)
    for _ in range(50):
        x, y = random.uniform(-900, 900), random.uniform(-700, 700)
        brute = sorted(math.hypot(a - x, b - y) for a, b in zip(xs, ys))[:5]
        assert [d for d, _ in g.knn(x, y, 5)] == pytest.approx(brute)


# ---------------------------------------------------------------- extremo a extremo
def test_example_profile_end_to_end(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    import excel_out
    d = json.loads((EXAMPLE / "ejemplo_3_espejos.json").read_text(encoding="utf-8"))
    zf, prm, els, t0, cases, _, _, dref = core.profile_from_dict(d, base=EXAMPLE)
    surfs, info = core.read_zemax(zf)
    res = core.compute_positions(surfs, els, prm, log=lambda m: None)
    assert [r.cfg.acronym for r in res] == ["M1", "M2", "M3"]
    stab = core.run_stability(res, prm, t0, cases, dref, log=lambda m: None)
    out = excel_out.write_workbook(tmp_path / "r.xlsx", zf, info, prm, res, stab, [], t0, cases, dref)
    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["Parametros", "Posiciones CREO", "Zemax global", "Estab T+1h",
                             "Estab T+1h desp", "Avisos"]
    for _, st in stab:
        for s in st:
            assert s.min_dist < 20
