"""Tests de regresión de los fallos encontrados en la revisión de la v1.5.1."""
import copy
import json
from pathlib import Path

import pytest

import core
import excel_out

EXAMPLE = Path(__file__).resolve().parents[1] / "ejemplos" / "sistema_3_espejos"


@pytest.fixture()
def setup():
    d = json.loads((EXAMPLE / "ejemplo_3_espejos.json").read_text(encoding="utf-8"))
    zf, prm, els, t0, cases, _, _, dref = core.profile_from_dict(d, base=EXAMPLE)
    surfs, info = core.read_zemax(zf)
    return zf, prm, els, t0, cases, dref, surfs, info


def _el(els, acr):
    return next(e for e in els if e.acronym == acr)


def test_example_profile_is_valid(setup):
    zf, prm, els, t0, cases, dref, *_ = setup
    assert core.validate_setup(els, prm, cases, t0, dref) == []


def test_duplicate_acronyms_rejected(setup):
    _, prm, els, *_ = setup
    _el(els, "M3").acronym = "M1"
    errs = core.validate_setup(els, prm)
    assert any("repetido" in e for e in errs)


def test_empty_acronym_rejected(setup):
    _, prm, els, *_ = setup
    _el(els, "M2").acronym = ""
    assert any("acrónimo" in e for e in core.validate_setup(els, prm))


@pytest.mark.parametrize("field, value", [("pos_step", "0,1 mm"), ("ang_step", "-0.1"),
                                          ("override", "0;90"), ("fem_point", "1;2;3;4")])
def test_bad_element_fields_rejected(setup, field, value):
    _, prm, els, *_ = setup
    setattr(_el(els, "M1"), field, value)
    assert core.validate_setup(els, prm)


def test_duplicate_and_colliding_case_labels(setup):
    _, prm, els, t0, cases, *_ = setup
    f = cases[0][1]
    assert core.validate_setup(els, prm, [("T+24h", f, "temp"), ("T+24h", f, "temp")], t0)
    long1, long2 = "Transitorio enfriamiento 1 hora", "Transitorio enfriamiento 1 hora B"
    assert core.validate_setup(els, prm, [(long1, f, "temp"), (long2, f, "temp")], t0)


def test_temperature_case_needs_t0(setup):
    _, prm, els, t0, cases, *_ = setup
    temp = [c for c in cases if c[2] == "temp"]
    assert any("T0" in e for e in core.validate_setup(els, prm, temp, ""))


def test_equal_temperatures(setup):
    _, prm, els, *_ = setup
    prm.t_warm_k = prm.t_cold_k
    assert any("iguales" in e for e in core.validate_setup(els, prm))
    core.check_material(prm, log=lambda m: None)          # sin ZeroDivisionError


def test_missing_material_reported(setup):
    _, prm, els, *_ = setup
    prm.material = "Material que no existe"
    assert any("materiales.json" in e for e in core.validate_setup(els, prm))


def test_fem_point_xyz_in_temperature_case(setup):
    _, prm, els, t0, cases, dref, surfs, _ = setup
    _el(els, "M2").fem_point = "-300;0;160"
    res = core.compute_positions(surfs, els, prm, log=lambda m: None)
    st = core.run_stability(res, prm, t0, [c for c in cases if c[2] == "temp"], [], log=lambda m: None)
    assert len(st[0][1]) == 3


def test_sheet_names_unique_and_short():
    for label in ("T+24h", "a/b:c*d?", "x" * 60):
        n = core.sheet_name_for_case(label)
        assert len(n) <= 31 and not set("[]*?/\\:") & set(n)


def test_case_file_names_in_sheet(setup, tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    zf, prm, els, t0, cases, dref, surfs, info = setup
    res = core.compute_positions(surfs, els, prm, log=lambda m: None)
    st = core.run_stability(res, prm, t0, cases, dref, log=lambda m: None)
    p = excel_out.write_workbook(tmp_path / "r.xlsx", zf, info, prm, res, st, [], t0, cases, dref)
    ws = openpyxl.load_workbook(p)["Estab T+1h"]
    assert "FEM_T1h.txt" in ws["A3"].value and "FEM_T0.txt" in ws["A3"].value


def test_default_acronyms_multiword_and_unique():
    S = [core.Surface(i, c, [[1, 0, 0], [0, 1, 0], [0, 0, 1]], 0, 0, i, 0, 0, 0) for i, c in
         enumerate(["Fold mirror 1", "Lens 1", "Fold mirror 2", "IPO FM25", "Object", "Object"], 1)]
    acr = [e.acronym for e in core.default_elements(S)]
    assert acr == ["FOLD_MIRROR_1", "LENS_1", "FOLD_MIRROR_2", "FM25", "OBJECT", "OBJECT_2"]


def test_csv_comma_separated(tmp_path):
    rows = ["Node Number,X Location (mm),Y Location (mm),Z Location (mm),Temperature (K)"]
    rows += [f"{i},{x}.5,{y}.25,0.0,130.1" for i, (x, y) in enumerate([(0, 0), (100, 0), (0, 100)], 1)]
    f = tmp_path / "t.csv"
    f.write_text("\n".join(rows), encoding="utf-8")
    fem = core.read_fem(f, log=lambda m: None)
    assert fem.x == pytest.approx([0.5, 100.5, 0.5]) and fem.t[0] == pytest.approx(130.1)


def test_small_model_in_mm_not_converted(tmp_path):
    f = tmp_path / "small.txt"
    f.write_text("Node Number\tX Location (mm)\tY Location (mm)\tZ Location (mm)\tTemperature (K)\n" +
                 "\n".join(f"{i}\t{x}\t{y}\t0\t130" for i, (x, y) in
                           enumerate([(0, 0), (15, 0), (0, 12), (15, 12)], 1)), encoding="utf-8")
    assert max(core.read_fem(f, log=lambda m: None).x) == pytest.approx(15.0)
