from regulacion_reactiva import (
    PRECIO_REACTIVA_ALTA_EUR_KVARH,
    PRECIO_REACTIVA_MEDIA_EUR_KVARH,
    precio_reactiva_inductiva,
)


def test_cos_phi_redondeado_a_095_no_penaliza():
    assert precio_reactiva_inductiva(0.949, "P1") == 0.0


def test_cos_phi_redondeado_inferior_a_095_penaliza():
    assert (
        precio_reactiva_inductiva(0.944, "P1")
        == PRECIO_REACTIVA_MEDIA_EUR_KVARH
    )


def test_p6_no_penaliza_aunque_el_factor_sea_bajo():
    assert precio_reactiva_inductiva(0.70, "P6") == 0.0


def test_tramo_inferior_a_080_aplica_precio_alto():
    assert (
        precio_reactiva_inductiva(0.794, "P1")
        == PRECIO_REACTIVA_ALTA_EUR_KVARH
    )
