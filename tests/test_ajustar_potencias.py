from backend_opt2 import ajustar_potencias


def test_ajustar_potencias_no_sube_un_kw_por_residuo_numerico():
    potencias = {
        "P1": 498.00000000001,
        "P2": 498.0,
        "P3": 981.0,
        "P4": 1140.0,
        "P5": 1140.0,
        "P6": 1300.00000000001,
    }

    resultado = ajustar_potencias(potencias)

    assert resultado["P1"] == 498
    assert resultado["P6"] == 1300


def test_ajustar_potencias_conserva_el_redondeo_hacia_arriba_real():
    potencias = {
        "P1": 498.0,
        "P2": 498.0,
        "P3": 981.0,
        "P4": 1140.0,
        "P5": 1140.0,
        "P6": 1300.2,
    }

    resultado = ajustar_potencias(potencias)

    assert resultado["P6"] == 1301
