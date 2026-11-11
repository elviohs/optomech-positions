"""Regresión de los fallos detectados en la revisión externa (v1.5.3)."""
import copy
import json
import math
import random
import time
from pathlib import Path

import pytest

import core
import geometry

EXAMPLE = Path(__file__).resolve().parents[1] / "ejemplos" / "sistema_3_espejos"
I3 = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def _load():
    d = json.loads((EXAMPLE / "ejemplo_3_espejos.json").read_text(encoding="utf-8"))
    zf, prm, els, *_ = core.profile_from_dict(d, base=EXAMPLE)
    surfs, _ = core.read_zemax(zf)
    return surfs, els, prm


# 1. Fila defectuosa en un fichero FEM
def test_fem_bad_row_skipped_without_shifting(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("Node Number\tX Location (mm)\tY Location (mm)\tZ Location (mm)\tTemperature (K)\n"
                 "1\t0\t0\t0\t130\n2\t100\t0\t****\t131\n3\t0\t100\t0\t132\n4\t100\t100\t0\t133\n",
                 encoding="utf-8")
    msgs = []
    d = core.read_fem(f, log=msgs.append)
    assert d.ids == [1, 3, 4]
    assert d.t == [130.0, 132.0, 133.0]
    assert len(d.ids) == len(d.x) == len(d.y) == len(d.z) == len(d.t)
    assert any("no numéricos" in m for m in msgs)


# 3. Etiquetas repetidas al releer un Zemax renumerado
def _surf(i, c):
    return core.Surface(i, c, I3, 0.0, 0.0, float(i), 0.0, 0.0, 0.0)


def test_duplicate_labels_keep_their_own_config_after_renumbering():
    before = [_surf(0, "Object"), _surf(3, "Object"), _surf(5, "M1")]
    old = core.default_elements(before)
    old[0].description, old[1].description = "primero", "segundo"
    # se inserta una superficie: la segunda 'Object' pasa de la 3 a la 4
    after = [_surf(0, "Object"), _surf(4, "Object"), _surf(6, "M1")]
    merged, msgs, _ = core.merge_elements(old, core.default_elements(after))
    objs = [e for e in merged if e.zemax_label == "Object"]
    assert [(e.surf_id, e.description) for e in objs] == [(0, "primero"), (4, "segundo")]


def test_legacy_profiles_get_occurrence_by_surface_order():
    els = [core.ElementCfg(surf_id=3, zemax_label="Object", acronym="B"),
           core.ElementCfg(surf_id=0, zemax_label="Object", acronym="A")]
    core.fix_occurrences(els)
    assert {e.acronym: e.occurrence for e in els} == {"A": 0, "B": 1}


# 4. Offset de posición fuera de rango
def test_offset_out_of_range_validated_and_view_safe():
    surfs, els, prm = _load()
    next(e for e in els if e.acronym == "M3").pos_offset = 5
    errs = core.validate_setup(els, prm, surfaces=surfs)
    assert any("fuera de rango" in e for e in errs)
    nodes, warns = geometry.build_path(surfs, els)          # sin IndexError
    assert any("fuera de rango" in w for w in warns)


# 5. Cerca de ty = ±90°: sin forzar tz = 0
@pytest.mark.parametrize("ty", [89.92, 89.95, 89.99, 89.999, -89.95])
@pytest.mark.parametrize("tz", [25.0, 90.0])
def test_near_gimbal_orientation_exact(ty, tz):
    R = core.creo_matrix(10.0, ty, tz)
    assert core.rotation_angle_between(core.creo_matrix(*core.r_to_creo_angles(R)), R) < 1e-6


def test_exact_gimbal_keeps_convention():
    R = core._mm(core._mm(core._rx(-90), core._ry(59.3)), core._rz(90))
    assert core.r_to_creo_angles(R) == pytest.approx((-30.7, 90.0, 0.0), abs=1e-6)


# 6. Búsqueda de nodos lejos de la malla
def test_knn_far_from_mesh_fast_and_correct():
    random.seed(1)
    xs = [random.uniform(-600, 600) for _ in range(20000)]
    ys = [random.uniform(-500, 500) for _ in range(20000)]
    g = core._Grid(xs, ys, [(0, 0)] * 20000)
    for x, y in [(10000, 0), (-8000, 9000), (0, -15000)]:
        t = time.time()
        got = [d for d, _ in g.knn(x, y, 5)]
        assert time.time() - t < 1.0
        brute = sorted(math.hypot(a - x, b - y) for a, b in zip(xs, ys))[:5]
        assert got == pytest.approx(brute)
