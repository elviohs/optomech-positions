import json
import math
import random
from pathlib import Path

import pytest

import core

EXAMPLE = Path(__file__).resolve().parents[1] / "ejemplos" / "sistema_3_espejos"


def test_rigid_fit_recovers_motion():
    random.seed(7)
    t_true, th_true = (0.01, -0.02, 0.005), (3e-6, -2e-6, 5e-6)
    pts = [(random.uniform(-50, 50), random.uniform(-50, 50), random.uniform(-10, 10)) for _ in range(30)]
    c = tuple(sum(p[i] for p in pts) / len(pts) for i in range(3))
    disps = []
    for p in pts:
        r = tuple(p[i] - c[i] for i in range(3))
        w = core._cross(th_true, r)
        disps.append(tuple(t_true[i] + w[i] for i in range(3)))
    t, th, c2, rms = core.rigid_fit(pts, disps)
    assert t == pytest.approx(t_true, abs=1e-12)
    assert th == pytest.approx(th_true, abs=1e-12)
    assert rms < 1e-12


def test_rigid_fit_collinear_is_degenerate():
    pts = [(float(i), 0.0, 0.0) for i in range(10)]
    t, th, c, rms = core.rigid_fit(pts, [(0.001, 0.0, 0.0)] * 10)
    assert th is None


def _write(path, header_u, rows):
    hdr = "Node Number\tX Location (mm)\tY Location (mm)\tZ Location (mm)\t" + header_u
    path.write_text("\n".join([hdr] + rows), encoding="utf-8")


def test_three_files_and_units(tmp_path):
    rows = lambda comp: [f"{i}\t{x}\t{y}\t0\t{comp(x, y)}" for i, (x, y) in
                         enumerate([(0, 0), (100, 0), (0, 100), (100, 100)], 1)]
    _write(tmp_path / "U_X.txt", "Directional Deformation (m)", rows(lambda x, y: 1e-6 * x))
    _write(tmp_path / "U_Y.txt", "Directional Deformation (um)", rows(lambda x, y: 2.0))
    _write(tmp_path / "U_Z.txt", "Directional Deformation (mm)", rows(lambda x, y: 0.003))
    d = core.read_disp([tmp_path / "U_Z.txt", tmp_path / "U_X.txt", tmp_path / "U_Y.txt"], log=lambda m: None)
    i = d.ids.index(2)                                  # nodo (100, 0)
    assert d.ux[i] == pytest.approx(0.1)                # 1e-4 m -> 0.1 mm
    assert d.uy[i] == pytest.approx(0.002)              # 2 µm -> 0.002 mm
    assert d.uz[i] == pytest.approx(0.003)


def test_three_files_without_axis_name_fails(tmp_path):
    for n in ("a", "b", "c"):
        _write(tmp_path / f"{n}.txt", "Deformation (mm)", ["1\t0\t0\t0\t0", "2\t1\t0\t0\t0"])
    with pytest.raises(ValueError, match="dirección"):
        core.read_disp([tmp_path / f"{n}.txt" for n in "abc"], log=lambda m: None)


def test_example_displacement_case():
    d = json.loads((EXAMPLE / "ejemplo_3_espejos.json").read_text(encoding="utf-8"))
    zf, prm, els, t0, cases, _, _, dref = core.profile_from_dict(d, base=EXAMPLE)
    surfs, _ = core.read_zemax(zf)
    res = core.compute_positions(surfs, els, prm, log=lambda m: None)
    disp_cases = [c for c in cases if c[2] == "desp"]
    (label, st), = core.run_stability(res, prm, "", disp_cases, dref, log=lambda m: None)
    s = {x.acronym: x for x in st}
    # Campo sintético: dilatación 1.2e-6 desde (0,0,150) + flexión con pendiente 2 µrad en x = -300
    m2 = s["M2"]
    assert m2.rot[1] == pytest.approx(2.0e-6, rel=0.02)                 # giro θy
    assert m2.dX == pytest.approx(1.2e-6 * -300 + 2.0e-6 * 100, abs=5e-6)  # incluye brazo de palanca (100 mm)
    assert m2.dZ == pytest.approx(0.5 * 6.67e-9 * 300 ** 2, abs=5e-6)
    assert s["M3"].dY == pytest.approx(1.2e-6 * -400, abs=5e-6)
    # sin referencia, el desplazamiento absoluto incluye el enfriamiento (orden mm)
    (_, st_abs), = core.run_stability(res, prm, "", disp_cases, [], log=lambda m: None)
    assert abs(st_abs[1].dX) > 0.5
