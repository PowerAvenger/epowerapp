"""Cálculos normativos comunes para los excesos de potencia."""

from __future__ import annotations

import calendar

import pandas as pd


def prorratear_costes_excesos_mensuales(costes_brutos, curva):
    """Aplica días de ciclo/días del mes a costes TEPp de tipos 1, 2 y 3.

    La magnitud física del sobrepasamiento no se modifica. La función recibe
    una matriz de costes ya calculados y devuelve otra matriz económica junto
    con el detalle auditable de días y factores por mes.
    """
    costes = costes_brutos.copy()
    factores = pd.DataFrame(index=costes.index)
    factores["Días ciclo"] = 0
    factores["Días mes"] = 0
    factores["Factor prorrateo"] = 1.0
    factores["Prorrateo aplicable"] = False

    if curva is None or "fecha_hora" not in curva.columns:
        return costes, factores
    fechas = pd.to_datetime(curva["fecha_hora"], errors="coerce").dropna()
    if fechas.empty:
        return costes, factores

    inicio_ciclo = fechas.min().normalize()
    fin_ciclo = fechas.max().normalize()
    for etiqueta_mes in costes.index:
        periodo = pd.Period(str(etiqueta_mes), freq="M")
        inicio_mes = periodo.start_time.normalize()
        fin_mes = periodo.end_time.normalize()
        inicio = max(inicio_ciclo, inicio_mes)
        fin = min(fin_ciclo, fin_mes)
        dias_mes = calendar.monthrange(periodo.year, periodo.month)[1]
        dias_ciclo = max((fin - inicio).days + 1, 0) if inicio <= fin else 0
        factor = min(dias_ciclo / dias_mes, 1.0) if dias_mes else 1.0

        factores.loc[etiqueta_mes, "Días ciclo"] = dias_ciclo
        factores.loc[etiqueta_mes, "Días mes"] = dias_mes
        factores.loc[etiqueta_mes, "Factor prorrateo"] = factor
        factores.loc[etiqueta_mes, "Prorrateo aplicable"] = factor < 1.0
        costes.loc[etiqueta_mes] = costes.loc[etiqueta_mes] * factor

    return costes, factores
