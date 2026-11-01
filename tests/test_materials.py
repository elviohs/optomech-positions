import pytest

import materials


@pytest.fixture(scope="module")
def mats():
    return materials.load_materials()


def test_all_materials_verified(mats):
    assert mats, "materiales.json vacío"
    for m in mats.values():
        assert m.verified, f"{m.name} sin verificar"


def test_al6061_matches_nist_plot(mats):
    m = mats["Al 6061-T6 (NIST)"]
    assert m.strain(293) == pytest.approx(0, abs=1e-5)
    # valores leídos de la gráfica NIST (dL/L)
    for T, eps in [(50, -4.07e-3), (100, -3.65e-3), (150, -2.95e-3), (200, -2.03e-3), (300, 0.16e-3)]:
        assert m.strain(T) == pytest.approx(eps, abs=0.03e-3)
    assert m.strain(10) == pytest.approx(-415.45e-5)          # tramo constante T < 18 K
    assert m.alpha(10) == 0.0
    assert m.factor(130, 293) == pytest.approx(0.003270, abs=2e-6)


def test_stainless_curves_identical(mats):
    a, b, c = (mats[n] for n in ("AISI 304 inox (NIST)", "AISI 304L inox (NIST)", "AISI 316 inox (NIST)"))
    for T in (30, 77, 130, 200, 293):
        assert a.strain(T) == b.strain(T) == c.strain(T)
    assert a.factor(130, 293) == pytest.approx(0.002309, abs=2e-6)


def test_continuity_at_t_low(mats):
    for m in mats.values():
        if m.kind == "nist_poly" and m.t_low:
            assert m.strain(m.t_low - 1e-9) == pytest.approx(m.strain(m.t_low), abs=2e-7)
