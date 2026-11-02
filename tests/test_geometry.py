import json
from pathlib import Path

import pytest

import core
import geometry

EXAMPLE = Path(__file__).resolve().parents[1] / "ejemplos" / "sistema_3_espejos"


def _load():
    d = json.loads((EXAMPLE / "ejemplo_3_espejos.json").read_text(encoding="utf-8"))
    zf, prm, els, *_ = core.profile_from_dict(d, base=EXAMPLE)
    surfs, _ = core.read_zemax(zf)
    return surfs, els, prm


def test_example_path_is_consistent():
    surfs, els, prm = _load()
    nodes, warns = geometry.build_path(surfs, els, ignore=core.parse_ignore(prm.ignore_labels))
    assert [n.name for n in nodes] == ["Objeto", "M1", "M2", "M3", "Detector"]
    for n in nodes[1:-1]:
        assert n.status == "ok"
        assert n.err_deg < 1e-6
    assert nodes[1].aoi_deg == pytest.approx(45.0)
    assert not warns


def test_wrong_orientation_detected():
    surfs, els, prm = _load()
    m2 = next(s for s in surfs if s.comment == "M2")
    m2.R = core._mm(m2.R, core._rx(3.0))          # se desajusta M2 3°
    nodes, warns = geometry.build_path(surfs, els, ignore=core.parse_ignore(prm.ignore_labels))
    st = {n.name: n.status for n in nodes}
    assert st["M2"] == "error"
    assert any("M2" in w for w in warns)


def test_offset_element_marked_off_axis():
    surfs, els, prm = _load()
    m1 = next(e for e in els if e.acronym == "M1")
    m1.pos_offset = 1
    nodes, _ = geometry.build_path(surfs, els, ignore=core.parse_ignore(prm.ignore_labels))
    assert next(n for n in nodes if n.name == "M1").status == "fuera de eje"


def test_transmissive_element():
    surfs, els, prm = _load()
    # la superficie "Pupila" está sobre el rayo M1->M2: incluida, se ve como transmisión
    els.append(core.ElementCfg(surf_id=5, zemax_label="Pupila", acronym="PUP", include=True))
    nodes, _ = geometry.build_path(surfs, els, ignore=core.parse_ignore(prm.ignore_labels))
    assert next(n for n in nodes if n.name == "PUP").status == "transmisión"
