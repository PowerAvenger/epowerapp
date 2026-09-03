"""Lectura común de exportaciones SIPS con ficha y medidas mensuales."""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from pathlib import Path

import pandas as pd


MESES = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
    7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic",
}


def obtener_atr_sips(metadatos):
    """Extrae y normaliza el ATR informado en la ficha del SIPS."""
    for clave in (
        "tarifa_atr", "tarifa_de_acceso", "tarifa", "peaje_acceso", "atr"
    ):
        valor = str((metadatos or {}).get(clave, "") or "").upper()
        coincidencia = re.search(r"(2[.,]0|3[.,]0|6[.,][1-4])", valor)
        if coincidencia:
            return coincidencia.group(1).replace(",", ".")
    return None


def _nombre_columna(valor):
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", texto.lower()).strip("_")


def _leer_bytes(origen):
    if isinstance(origen, (str, Path)):
        return Path(origen).read_bytes()
    if hasattr(origen, "getvalue"):
        return origen.getvalue()
    posicion = origen.tell() if hasattr(origen, "tell") else None
    contenido = origen.read()
    if posicion is not None and hasattr(origen, "seek"):
        origen.seek(posicion)
    return contenido.encode("utf-8") if isinstance(contenido, str) else contenido


def _decodificar(contenido):
    for codificacion in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return contenido.decode(codificacion)
        except UnicodeDecodeError:
            continue
    raise ValueError("No se ha podido determinar la codificación del SIPS.")


def _numero_es(serie):
    texto = serie.astype("string").str.strip().str.replace(" ", "", regex=False)
    texto = texto.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(texto, errors="coerce")


def _tabla_magnitud(lecturas, prefijo, agregacion):
    columnas_origen = [f"{prefijo}{i}" for i in range(1, 7)]
    tabla = lecturas[["periodo_mes", "dias_facturacion", *columnas_origen]].copy()
    tabla = (
        tabla.groupby("periodo_mes", as_index=False)
        .agg({
            "dias_facturacion": "sum",
            **{columna: agregacion for columna in columnas_origen},
        })
        .sort_values("periodo_mes")
        .reset_index(drop=True)
    )
    tabla = tabla.rename(
        columns={f"{prefijo}{i}": f"P{i}" for i in range(1, 7)}
    )
    tabla["año"] = tabla["periodo_mes"].dt.year
    tabla["mes"] = tabla["periodo_mes"].dt.month
    tabla["mes_nom"] = tabla["mes"].map(MESES)
    tabla["periodo_mes"] = tabla["periodo_mes"].astype(str)
    return tabla[
        ["periodo_mes", "año", "mes", "mes_nom", "dias_facturacion",
         *[f"P{i}" for i in range(1, 7)]]
    ]


def leer_sips_completo(origen):
    """Devuelve metadatos, activa, reactiva y maxímetros de un CSV SIPS."""
    texto = _decodificar(_leer_bytes(origen))
    filas = list(csv.reader(io.StringIO(texto), delimiter=";"))
    filas_no_vacias = [fila for fila in filas if any(celda.strip() for celda in fila)]
    if len(filas_no_vacias) < 4:
        raise ValueError("El CSV SIPS no contiene ficha y lecturas suficientes.")

    indice_lecturas = None
    for indice, fila in enumerate(filas):
        nombres = {_nombre_columna(celda) for celda in fila}
        if {"cups", "f_fin", "f_inicio", "ea1", "er1", "pt1"}.issubset(nombres):
            indice_lecturas = indice
            break
    if indice_lecturas is None:
        raise ValueError(
            "No encuentro la cabecera de medidas SIPS con EA, ER y PT."
        )

    filas_ficha = [
        fila for fila in filas[:indice_lecturas]
        if any(celda.strip() for celda in fila)
    ]
    metadatos = {}
    if len(filas_ficha) >= 2:
        cabecera_ficha = [_nombre_columna(valor) for valor in filas_ficha[0]]
        valores_ficha = filas_ficha[1]
        metadatos = {
            nombre: valores_ficha[posicion].strip()
            if posicion < len(valores_ficha) else ""
            for posicion, nombre in enumerate(cabecera_ficha)
            if nombre
        }

    cabecera = [_nombre_columna(valor) for valor in filas[indice_lecturas]]
    datos = [
        fila for fila in filas[indice_lecturas + 1:]
        if any(celda.strip() for celda in fila)
    ]
    lecturas = pd.DataFrame(datos, columns=cabecera)
    columnas_requeridas = {
        "cups", "f_fin", "f_inicio",
        *[f"ea{i}" for i in range(1, 7)],
        *[f"er{i}" for i in range(1, 7)],
        *[f"pt{i}" for i in range(1, 7)],
    }
    faltantes = columnas_requeridas.difference(lecturas.columns)
    if faltantes:
        raise ValueError(
            "Faltan columnas SIPS: " + ", ".join(sorted(faltantes)) + "."
        )

    lecturas["fecha_fin"] = pd.to_datetime(lecturas["f_fin"], errors="coerce")
    lecturas["fecha_inicio"] = pd.to_datetime(
        lecturas["f_inicio"], errors="coerce"
    )
    lecturas = lecturas.dropna(subset=["fecha_fin", "fecha_inicio"]).copy()
    if lecturas.empty:
        raise ValueError("El SIPS no contiene ciclos con fechas válidas.")
    lecturas["periodo_mes"] = lecturas["fecha_fin"].dt.to_period("M")
    lecturas["dias_facturacion"] = (
        lecturas["fecha_fin"].dt.normalize()
        - lecturas["fecha_inicio"].dt.normalize()
    ).dt.days.clip(lower=0)
    for prefijo in ("ea", "er", "pt"):
        for periodo in range(1, 7):
            columna = f"{prefijo}{periodo}"
            lecturas[columna] = _numero_es(lecturas[columna]).fillna(0.0)

    cups_lecturas = lecturas["cups"].dropna().astype(str).str.strip()
    if not metadatos.get("cups") and not cups_lecturas.empty:
        metadatos["cups"] = cups_lecturas.iloc[0]

    return {
        "metadatos": metadatos,
        "atr": obtener_atr_sips(metadatos),
        "consumos": _tabla_magnitud(lecturas, "ea", "sum"),
        "reactiva": _tabla_magnitud(lecturas, "er", "sum"),
        "maximetros": _tabla_magnitud(lecturas, "pt", "max"),
    }


def perfil_anual_meses_naturales(tabla):
    """Selecciona el dato más reciente disponible de cada mes natural."""
    datos = tabla.copy()
    datos["_periodo"] = pd.to_datetime(
        datos["periodo_mes"], format="%Y-%m", errors="coerce"
    )
    datos = datos.dropna(subset=["_periodo", "mes"]).sort_values("_periodo")
    datos = datos.drop_duplicates(subset=["mes"], keep="last").sort_values("mes")
    if sorted(datos["mes"].astype(int).tolist()) != list(range(1, 13)):
        meses = sorted(datos["mes"].astype(int).tolist())
        raise ValueError(
            "El SIPS no contiene al menos una lectura para cada mes natural. "
            f"Meses disponibles: {meses}."
        )
    return datos.drop(columns="_periodo").reset_index(drop=True)
