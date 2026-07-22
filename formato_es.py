"""Formato español reutilizable para la capa de presentación.

Las funciones de este módulo no alteran los datos de cálculo. Los DataFrames
que devuelven texto deben utilizarse únicamente como copias de visualización.
"""

from __future__ import annotations

import re
from typing import Iterable

import pandas as pd


MESES_ES = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr",
    5: "may", 6: "jun", 7: "jul", 8: "ago",
    9: "sep", 10: "oct", 11: "nov", 12: "dic",
}


def formato_numero_es(valor, decimales: int = 0) -> str:
    """Devuelve un número con punto de millares y coma decimal."""
    if valor is None or pd.isna(valor):
        return ""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    texto = f"{numero:,.{decimales}f}"
    return texto.translate(str.maketrans({",": ".", ".": ","}))


def _con_unidad(valor, decimales: int, unidad: str, incluir: bool) -> str:
    texto = formato_numero_es(valor, decimales)
    if not texto:
        return ""
    return f"{texto} {unidad}" if incluir else texto


def formato_kwh(valor, decimales: int = 0, unidad: bool = False) -> str:
    return _con_unidad(valor, decimales, "kWh", unidad)


def formato_mwh(valor, decimales: int = 2, unidad: bool = False) -> str:
    return _con_unidad(valor, decimales, "MWh", unidad)


def formato_kw(valor, decimales: int = 2, unidad: bool = False) -> str:
    return _con_unidad(valor, decimales, "kW", unidad)


def formato_euros(valor, decimales: int = 2, unidad: bool = True) -> str:
    return _con_unidad(valor, decimales, "€", unidad)


def formato_eur_mwh(valor, decimales: int = 2, unidad: bool = True) -> str:
    return _con_unidad(valor, decimales, "€/MWh", unidad)


def formato_eur_kwh(valor, decimales: int = 6, unidad: bool = True) -> str:
    return _con_unidad(valor, decimales, "€/kWh", unidad)


def formato_cent_eur_kwh(valor, decimales: int = 4, unidad: bool = True) -> str:
    return _con_unidad(valor, decimales, "c€/kWh", unidad)


def formato_eur_kw_dia(valor, decimales: int = 6, unidad: bool = True) -> str:
    return _con_unidad(valor, decimales, "€/kW día", unidad)


def formato_eur_kw_mes(valor, decimales: int = 6, unidad: bool = True) -> str:
    return _con_unidad(valor, decimales, "€/kW mes", unidad)


def formato_pct(valor, decimales: int = 2, unidad: bool = True) -> str:
    return _con_unidad(valor, decimales, "%", unidad)


def formato_fecha_es(valor, separador: str = ".") -> str:
    if isinstance(valor, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor.strip()):
        fecha = pd.to_datetime(valor, format="%Y-%m-%d", errors="coerce")
    else:
        fecha = pd.to_datetime(valor, errors="coerce", dayfirst=True)
    if pd.isna(fecha):
        return "" if valor is None else str(valor)
    return fecha.strftime(f"%d{separador}%m{separador}%Y")


def formato_mes_es(valor, capitalizar: bool = True, compacto: bool = False) -> str:
    """Convierte una fecha en ``Jun 2026`` o, con compacto, ``Jun26``."""
    fecha = pd.to_datetime(valor, errors="coerce")
    if pd.isna(fecha):
        return "" if valor is None else str(valor)
    mes = MESES_ES[fecha.month]
    if capitalizar:
        mes = mes.capitalize()
    return f"{mes}{str(fecha.year)[-2:]}" if compacto else f"{mes} {fecha.year}"


def formatear_columnas_tabla(
    df: pd.DataFrame,
    *,
    columnas_kwh: Iterable[str] | None = None,
    columnas_mwh: Iterable[str] | None = None,
    columnas_kw: Iterable[str] | None = None,
    columnas_euros: Iterable[str] | None = None,
    columnas_eur_mwh: Iterable[str] | None = None,
    columnas_eur_kwh: Iterable[str] | None = None,
    columnas_cent_eur_kwh: Iterable[str] | None = None,
    columnas_eur_kw_dia: Iterable[str] | None = None,
    columnas_eur_kw_mes: Iterable[str] | None = None,
    columnas_pct: Iterable[str] | None = None,
    columna_mes: str | None = None,
    mes_compacto: bool = False,
    incluir_unidades: bool = False,
    decimales_kwh: int = 0,
    decimales_mwh: int = 2,
    decimales_kw: int = 2,
    decimales_euros: int = 2,
    decimales_eur_mwh: int = 2,
    decimales_eur_kwh: int = 6,
    decimales_cent_eur_kwh: int = 4,
    decimales_eur_kw_dia: int = 6,
    decimales_eur_kw_mes: int = 6,
    decimales_pct: int = 2,
) -> pd.DataFrame:
    """Crea una copia textual para mostrar; nunca debe usarse para cálculos."""
    resultado = df.copy()
    if columna_mes and columna_mes in resultado.columns:
        resultado[columna_mes] = resultado[columna_mes].map(
            lambda valor: formato_mes_es(valor, compacto=mes_compacto)
        )

    grupos = (
        (columnas_kwh, formato_kwh, decimales_kwh),
        (columnas_mwh, formato_mwh, decimales_mwh),
        (columnas_kw, formato_kw, decimales_kw),
        (columnas_euros, formato_euros, decimales_euros),
        (columnas_eur_mwh, formato_eur_mwh, decimales_eur_mwh),
        (columnas_eur_kwh, formato_eur_kwh, decimales_eur_kwh),
        (columnas_cent_eur_kwh, formato_cent_eur_kwh, decimales_cent_eur_kwh),
        (columnas_eur_kw_dia, formato_eur_kw_dia, decimales_eur_kw_dia),
        (columnas_eur_kw_mes, formato_eur_kw_mes, decimales_eur_kw_mes),
        (columnas_pct, formato_pct, decimales_pct),
    )
    for columnas, formateador, decimales in grupos:
        for columna in columnas or ():
            if columna in resultado.columns:
                resultado[columna] = resultado[columna].map(
                    lambda valor, f=formateador, d=decimales: f(
                        valor, decimales=d, unidad=incluir_unidades
                    )
                )
    return resultado


def formatear_tabla_consumos(
    df: pd.DataFrame,
    columna_mes: str | None = None,
    incluir_unidades: bool = False,
    mes_compacto: bool = False,
) -> pd.DataFrame:
    columnas = [
        columna for columna in df.columns
        if columna.startswith("P") or columna in {
            "Total", "consumo_neto_kWh", "demanda_neto_kWh",
            "vertido_neto_kWh", "generacion_kWh", "autoconsumo_kWh",
        }
    ]
    return formatear_columnas_tabla(
        df,
        columnas_kwh=columnas,
        columna_mes=columna_mes,
        mes_compacto=mes_compacto,
        incluir_unidades=incluir_unidades,
    )


def formatear_tabla_euros(
    df: pd.DataFrame,
    columna_mes: str | None = None,
    incluir_unidades: bool = False,
    mes_compacto: bool = False,
) -> pd.DataFrame:
    columnas = [
        columna for columna in df.columns
        if columna.startswith("P") or columna in {"Total", "coste", "importe"}
    ]
    return formatear_columnas_tabla(
        df,
        columnas_euros=columnas,
        columna_mes=columna_mes,
        mes_compacto=mes_compacto,
        incluir_unidades=incluir_unidades,
    )


def formatear_resumen_mixto(df_resumen: pd.DataFrame) -> pd.DataFrame:
    transpuesto = df_resumen.T
    return formatear_columnas_tabla(
        transpuesto,
        columnas_kwh=["Consumo (kWh)"],
        columnas_euros=["Coste (€)"],
        columnas_eur_kwh=["Precio medio (€/kWh)"],
    ).T
