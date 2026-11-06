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


# ---------------------------------------------------------------- espejos fuera de eje
def _surf(sid, comment, p, R=None, **kw):
    R = R or [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    return core.Surface(sid, comment, R, p[0], p[1], p[2], 0.0, 0.0, 0.0, **kw)


def _oap(radius_known=True, surf_type="STANDARD"):
    """Paraboloide fuera de eje: rayo paralelo al eje en x = h que refleja hacia el foco."""
    f, h = 500.0, 120.0
    hit = (h, 0.0, h * h / (4 * f))                     # z = r² / (4f)  (R = 2f, k = -1)
    surfs = [_surf(1, "Inicio", (h, 0.0, 1000.0)),
             _surf(2, "OAP", (0.0, 0.0, 0.0), surf_type=surf_type,
                   radius=2 * f if radius_known else None, conic=-1.0, glass="MIRROR"),
             _surf(3, "", (h, 0.0, 0.0)),                 # coordinate break en el plano del vértice
             _surf(4, "Foco", (0.0, 0.0, f))]
    els = [core.ElementCfg(surf_id=2, zemax_label="OAP", acronym="OAP", pos_offset=1)]
    return surfs, els, hit


def test_off_axis_paraboloid_checked_at_hit_point():
    surfs, els, hit = _oap()
    nodes, warns = geometry.build_path(surfs, els)
    n = next(x for x in nodes if x.name == "OAP")
    assert n.status == "ok" and n.normal_src.startswith("impacto")
    assert n.err_deg < 1e-9
    assert n.p == pytest.approx(hit)
    assert n.hit_offset_mm == pytest.approx(hit[2])     # sagita
    assert not warns


def test_off_axis_without_surface_data_not_checkable():
    surfs, els, _ = _oap(radius_known=False, surf_type="")
    nodes, warns = geometry.build_path(surfs, els)
    assert next(x for x in nodes if x.name == "OAP").status == "fuera de eje"
    assert any("SURFACE DATA SUMMARY" in w for w in warns)


def test_off_axis_unsupported_type():
    surfs, els, _ = _oap(surf_type="TOROIDAL")
    nodes, warns = geometry.build_path(surfs, els)
    assert next(x for x in nodes if x.name == "OAP").status == "fuera de eje"


def test_summary_table_parsed(tmp_path):
    txt = "\r\n".join([
        "SURFACE DATA SUMMARY:", "",
        "Surf\tType\tRadius\tThickness\tGlass\tClear Diam\tChip Zone\tMech Diam\tConic\tComment",
        " OBJ\t STANDARD\t Infinity\t 100\t \t 10\t 0\t 10\t 0\t Obj",
        "   1\t STANDARD\t 1599,175\t 0\t MIRROR\t 261\t 0\t 130\t -1\t M",
        "", "GLOBAL VERTEX COORDINATES, ORIENTATIONS, AND ROTATION/OFFSET MATRICES:", "",
        "  0\t 1,0\t 0,0\t 0,0\t 0,0\t 0,0\tObj", "   \t 0,0\t 1,0\t 0,0\t 0,0\t 0,0", "   \t 0,0\t 0,0\t 1,0\t 0,0\t 0,0", "",
        "  1\t 1,0\t 0,0\t 0,0\t 0,0\t 0,0\tM", "   \t 0,0\t 1,0\t 0,0\t 0,0\t 0,0", "   \t 0,0\t 0,0\t 1,0\t 100,0\t 0,0", "",
        "GLOBAL SURFACE CENTER OF CURVATURE POINTS:"])
    f = tmp_path / "z.txt"
    f.write_bytes(txt.encode("utf-16"))          # sin traducción de finales de línea (Windows)
    surfs, info = core.read_zemax(f)
    assert info["summary"]
    m = next(s for s in surfs if s.comment == "M")
    assert (m.surf_type, m.radius, m.conic, m.glass) == ("STANDARD", pytest.approx(1599.175), -1.0, "MIRROR")
    assert surfs[0].radius == float("inf")


def test_double_cr_line_endings(tmp_path):
    """Ficheros con '\\r\\r\\n' (copias entre sistemas) se leen igual."""
    src = (EXAMPLE / "zemax_ejemplo.txt").read_bytes().decode("utf-16")
    f = tmp_path / "z.txt"
    f.write_bytes(src.replace("\r\n", "\r\r\n").encode("utf-16"))
    a, _ = core.read_zemax(EXAMPLE / "zemax_ejemplo.txt")
    b, _ = core.read_zemax(f)
    assert [(s.surf_id, s.comment, s.x, s.y, s.z) for s in a] == [(s.surf_id, s.comment, s.x, s.y, s.z) for s in b]
