import pandas as pd
import pytest

from backend_indexado import FormulaIndexada
from backend_ppa import calcular_ppa_fijo, calcular_ppa_indexado, repartir_carga_base


def _curva():
    return pd.DataFrame({
        "fecha_hora": pd.date_range("2026-01-01", periods=2, freq="h"),
        "consumo_neto_kWh": [1500.0, 500.0],
        "periodo": ["P1", "P2"],
        "spot": [50.0, 100.0],
        "ssaa": [0.0, 0.0],
        "osom": [0.0, 0.0],
        "fnee": [0.0, 0.0],
        **{
            columna: [0.0, 0.0]
            for atr in ("2.0", "3.0", "6.1")
            for columna in (f"ppcc_{atr}", f"perd_{atr}", f"pyc_{atr}")
        },
    })


def test_reparto_carga_base_separa_residual_y_excedente():
    resultado = repartir_carga_base(_curva(), 1.0)
    assert resultado["energia_ppa_cubierta_kWh"].tolist() == [1000.0, 500.0]
    assert resultado["energia_residual_kWh"].tolist() == [500.0, 0.0]
    assert resultado["energia_excedente_kWh"].tolist() == [0.0, 500.0]


def test_ppa_fijo_solo_aplica_precio_ppa_al_volumen_cubierto():
    _, resumen = calcular_ppa_fijo(
        _curva(), "2.0", {"P1": 0.10, "P2": 0.20}, 1.0, 60.0
    )
    total = resumen.set_index("Periodo").loc["Total"]
    assert total["Coste referencia (€)"] == pytest.approx(250.0)
    assert total["Coste con PPA (€)"] == pytest.approx(140.0)
    assert total["Excedente (kWh)"] == pytest.approx(500.0)
    assert total["Aprovechamiento PPA (%)"] == pytest.approx(75.0)


def test_ppa_indexado_reutiliza_formula_en_ambos_bloques():
    _, resumen = calcular_ppa_indexado(
        _curva(), "2.0", FormulaIndexada(), 1.0, 40.0
    )
    total = resumen.set_index("Periodo").loc["Total"]
    # La fórmula incluye la tasa municipal del 1,5 % incluso sin otros costes.
    assert total["Coste referencia (€)"] == pytest.approx(126.875)
    assert total["Coste con PPA (€)"] == pytest.approx(86.275)
