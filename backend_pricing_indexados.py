"""Simulación mensual de indexados compartida por los comparadores."""

from __future__ import annotations

import numpy as np
import pandas as pd

from backend_indexado import FormulaIndexada, calcular_precios_atr_formula
from backend_simulindex import pyc_2026


PERIODOS = [f"P{i}" for i in range(1, 7)]
ATRS = ("2.0", "3.0", "6.1", "6.2")
RATIOS_PERDIDAS_62_61 = {
    "P1": 0.052 / 0.065, "P2": 0.054 / 0.068,
    "P3": 0.049 / 0.065, "P4": 0.050 / 0.065,
    "P5": 0.035 / 0.043, "P6": 0.054 / 0.077,
}


def preparar_referencia_pricing(referencia: pd.DataFrame) -> pd.DataFrame:
    """Selecciona los 12 últimos meses horarios completos de referencia."""
    datos = referencia.copy()
    datos["fecha"] = pd.to_datetime(datos["fecha"], errors="coerce")
    datos["spot"] = pd.to_numeric(datos["spot"], errors="coerce")
    datos = datos.dropna(subset=["fecha", "spot"])
    meses = datos["fecha"].dt.to_period("M")
    completos = []
    for periodo, grupo in datos.groupby(meses):
        inicio = periodo.start_time.tz_localize("Europe/Madrid")
        fin = (periodo + 1).start_time.tz_localize("Europe/Madrid")
        horas = len(pd.date_range(inicio, fin, freq="h", inclusive="left"))
        fechas = grupo["fecha"]
        if (
            len(grupo) == horas
            and fechas.min().date() == periodo.start_time.date()
            and fechas.max().date() == periodo.end_time.date()
        ):
            completos.append(periodo)
    # Los datos de prueba pueden ser mensuales en vez de horarios.
    seleccion = sorted(completos or meses.dropna().unique())[-12:]
    return datos.loc[meses.isin(seleccion)].copy()


def _perdidas_62(datos: pd.DataFrame) -> pd.DataFrame:
    """Completa la pérdida 6.2 cuando la sesión conserva solo la 6.1."""
    if "perd_6.1" not in datos:
        return datos
    datos = datos.copy()
    actual = pd.to_numeric(
        datos.get("perd_6.2", pd.Series(index=datos.index, dtype=float)),
        errors="coerce",
    )
    estimada = (
        pd.to_numeric(datos["perd_6.1"], errors="coerce")
        * datos["dh_6p"].map(RATIOS_PERDIDAS_62_61)
    )
    datos["perd_6.2"] = actual.fillna(estimada)
    return datos


def _ppcc_vigente(referencia: pd.DataFrame, atr: str) -> pd.Series:
    """Reproduce el PPCC del último año usado en Pricing."""
    datos = referencia.copy()
    datos["fecha"] = pd.to_datetime(datos["fecha"], errors="coerce")
    datos = datos.dropna(subset=["fecha"]).sort_values("fecha")
    if datos.empty:
        raise ValueError("No hay referencia horaria para obtener PPCC.")
    datos = datos.loc[datos["fecha"].dt.year.eq(datos["fecha"].dt.year.max())]
    columna_periodo = "dh_3p" if atr == "2.0" else "dh_6p"
    columna_ppcc = f"ppcc_{atr}"
    datos[columna_ppcc] = pd.to_numeric(datos[columna_ppcc], errors="coerce")
    return (
        datos.dropna(subset=[columna_periodo, columna_ppcc])
        .groupby(columna_periodo)[columna_ppcc]
        .last()
    )


def obtener_pyc_historico_por_periodo(
    referencia: pd.DataFrame, atr: str, anio: int
) -> pd.Series:
    """Recupera los PyC de cada mes y periodo de un año, en €/MWh."""
    columna_periodo = 'dh_3p' if atr == '2.0' else 'dh_6p'
    columna_pyc = f'pyc_{atr}'
    datos = referencia[['fecha', columna_periodo, columna_pyc]].copy()
    datos['fecha'] = pd.to_datetime(datos['fecha'], errors='coerce')
    datos[columna_pyc] = pd.to_numeric(datos[columna_pyc], errors='coerce')
    datos = datos.loc[datos['fecha'].dt.year.eq(anio)].dropna()
    datos['mes'] = datos['fecha'].dt.month
    datos['periodo'] = datos[columna_periodo].astype(str).str.upper()
    valores = (
        datos.sort_values('fecha')
        .groupby(['mes', 'periodo'])[columna_pyc]
        .last()
    )
    if valores.empty:
        raise ValueError(f'No hay PyC de {anio} para {atr}TD.')
    meses_referencia = preparar_referencia_pricing(referencia)
    meses_referencia['mes'] = meses_referencia['fecha'].dt.month
    meses_referencia['periodo'] = (
        meses_referencia[columna_periodo].astype(str).str.upper()
    )
    necesarios = pd.MultiIndex.from_frame(
        meses_referencia[['mes', 'periodo']]
    ).unique()
    if not necesarios.isin(valores.index).all():
        raise ValueError(
            f'Faltan PyC de {anio} para algún mes y periodo usados '
            'en la comparación.'
        )
    return valores


def calcular_escenarios_pricing_mensuales(
    referencia: pd.DataFrame,
    consumos_mensuales: pd.DataFrame,
    atr: str,
    formula: FormulaIndexada,
    escenarios: dict[str, float],
    ssaa_previsto: float,
    fnee_previsto: float,
    srad_previsto: float,
    pyc_por_periodo: pd.Series | None = None,
    perfil_anual: bool = False,
    ssaa_incluye_srad: bool = False,
) -> pd.DataFrame:
    """Aplica el perfilado y los componentes vigentes de Pricing a A/B/C."""
    if atr not in ATRS:
        raise ValueError(f"ATR no compatible con Pricing: {atr}.")
    datos = _perdidas_62(preparar_referencia_pricing(referencia))
    if datos.empty:
        raise ValueError("No hay meses de referencia para simular indexados.")
    columna_periodo = "dh_3p" if atr == "2.0" else "dh_6p"
    periodos = PERIODOS[:3] if atr == "2.0" else PERIODOS
    datos["periodo"] = datos[columna_periodo].astype(str).str.upper()
    datos["mes_referencia"] = datos["fecha"].dt.to_period("M")
    datos["ssaa_perfil"] = pd.to_numeric(datos["ssaa"], errors="coerce")
    if not ssaa_incluye_srad:
        datos["ssaa_perfil"] -= pd.to_numeric(
            datos["rad3"], errors="coerce"
        )
    for columna in ("spot", "ssaa_perfil", f"perd_{atr}"):
        datos[columna] = pd.to_numeric(datos[columna], errors="coerce")
    grupo = datos.groupby(["mes_referencia", "periodo"], as_index=False).agg(
        spot=("spot", "mean"),
        ssaa=("ssaa_perfil", "mean"),
        perd=(f"perd_{atr}", "mean"),
    )
    if perfil_anual:
        media_spot = datos["spot"].mean()
        media_ssaa = datos["ssaa_perfil"].mean()
        if not np.isfinite(media_spot) or media_spot == 0:
            raise ValueError("La referencia anual no tiene una media OMIE válida.")
        grupo["ap_spot"] = grupo["spot"] / media_spot
        grupo["ap_ssaa"] = (
            grupo["ssaa"] / media_ssaa
            if np.isfinite(media_ssaa) and media_ssaa != 0 else 1.0
        )
    else:
        media_mes = datos.groupby("mes_referencia").agg(
            spot=("spot", "mean"), ssaa=("ssaa_perfil", "mean")
        )
        grupo["ap_spot"] = (
            grupo["spot"] / grupo["mes_referencia"].map(media_mes["spot"])
        )
        grupo["ap_ssaa"] = (
            grupo["ssaa"]
            / grupo["mes_referencia"].map(
                media_mes["ssaa"].replace(0, np.nan)
            )
        ).fillna(1.0)
    grupo = grupo.loc[grupo["periodo"].isin(periodos)].copy()
    grupo["mes"] = grupo["mes_referencia"].dt.month

    ppcc = _ppcc_vigente(referencia, atr)
    grupo["ppcc"] = grupo["periodo"].map(ppcc)
    if pyc_por_periodo is None:
        grupo['pyc'] = grupo['periodo'].map(pyc_2026[f'{atr}TD']) * 1000
    else:
        indice_pyc = pd.MultiIndex.from_frame(grupo[['mes', 'periodo']])
        grupo['pyc'] = indice_pyc.map(pyc_por_periodo).to_numpy()
        if grupo['pyc'].isna().any():
            raise ValueError('Faltan PyC históricos para algún mes y periodo.')
    osom = pd.to_numeric(datos["osom"], errors="coerce").mean()

    consumos = consumos_mensuales.copy()
    if "mes" not in consumos:
        raise ValueError("Los consumos mensuales no contienen la columna mes.")
    detalle_consumo = consumos.melt(
        id_vars=["mes"], value_vars=periodos,
        var_name="periodo", value_name="consumo",
    )
    detalle_consumo["consumo"] = pd.to_numeric(
        detalle_consumo["consumo"], errors="coerce"
    )
    if detalle_consumo["consumo"].isna().any():
        raise ValueError("Hay consumos no numéricos en el perfil mensual.")
    detalle_consumo = detalle_consumo.loc[
        detalle_consumo["consumo"].ne(0)
    ].copy()

    resultados = []
    detalles = []
    precios = []
    componentes_ponderados = []
    for nombre, omie in escenarios.items():
        componentes = grupo.copy()
        componentes["spot"] = componentes["ap_spot"] * float(omie)
        componentes["ssaa"] = (
            componentes["ap_ssaa"] * float(ssaa_previsto) + float(srad_previsto)
        )
        componentes["osom"] = osom
        componentes["fnee"] = float(fnee_previsto)
        for tarifa in ATRS:
            componentes[f"ppcc_{tarifa}"] = 0.0
            componentes[f"perd_{tarifa}"] = 0.0
            componentes[f"pyc_{tarifa}"] = 0.0
        componentes[f"ppcc_{atr}"] = componentes["ppcc"]
        componentes[f"perd_{atr}"] = componentes["perd"]
        componentes[f"pyc_{atr}"] = componentes["pyc"]
        calculado = calcular_precios_atr_formula(componentes, formula)
        tabla_precios = calculado[[
            "mes_referencia", "periodo", f"precio_{atr}"
        ]].rename(columns={
            "mes_referencia": "Mes", "periodo": "Periodo",
            f"precio_{atr}": "Precio (€/kWh)",
        })
        tabla_precios["Mes"] = tabla_precios["Mes"].astype(str)
        tabla_precios["Precio (€/kWh)"] /= 1000
        tabla_precios["Oferta"] = nombre
        precios.append(tabla_precios)
        ponderacion = detalle_consumo.merge(
            calculado[["mes", "periodo", "spot", "ssaa", f"precio_{atr}"]],
            on=["mes", "periodo"], how="inner", validate="many_to_one",
        )
        if len(ponderacion) != len(detalle_consumo):
            raise ValueError("La referencia no cubre todos los meses y periodos del consumo.")
        ponderacion["coste"] = (
            ponderacion["consumo"] * ponderacion[f"precio_{atr}"] / 1000
        )
        coste = float(ponderacion["coste"].sum())
        energia = float(ponderacion["consumo"].sum())
        componentes_ponderados.append({
            "Oferta": nombre,
            "OMIE aplicado ponderado (€/MWh)": (
                float((ponderacion["spot"] * ponderacion["consumo"]).sum())
                / energia if energia else np.nan
            ),
            "SSAA aplicados ponderados (€/MWh)": (
                float((ponderacion["ssaa"] * ponderacion["consumo"]).sum())
                / energia if energia else np.nan
            ),
        })
        resultados.append({
            "Oferta": nombre,
            "Tipo": "Indexado",
            "Coste energía (€)": coste,
            "Precio medio energía (€/kWh)": coste / energia if energia else np.nan,
        })
        detalle = ponderacion[[
            "mes", "periodo", "consumo", f"precio_{atr}", "coste"
        ]].rename(columns={
            "mes": "Mes", "periodo": "Periodo",
            "consumo": "Consumo (kWh)",
            f"precio_{atr}": "Precio (€/MWh)",
            "coste": "Coste (€)",
        })
        detalle["Oferta"] = nombre
        detalles.append(detalle)
    resultado = pd.DataFrame(resultados)
    resultado.attrs["detalle"] = (
        pd.concat(detalles, ignore_index=True) if detalles else pd.DataFrame()
    )
    resultado.attrs["precios"] = (
        pd.concat(precios, ignore_index=True) if precios else pd.DataFrame()
    )
    resultado.attrs["componentes_ponderados"] = pd.DataFrame(
        componentes_ponderados
    )
    return resultado
