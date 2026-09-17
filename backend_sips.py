"""Lectura común de exportaciones SIPS con ficha y medidas mensuales."""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd


MESES = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
    7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic",
}


def obtener_atr_sips(metadatos):
    """Extrae y normaliza el ATR informado en la ficha del SIPS."""
    for clave in (
        "tarifa_atr", "descripcion_tarifa", "tarifa_de_acceso", "tarifa",
        "peaje_acceso", "atr"
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
    if isinstance(origen, (bytes, bytearray, memoryview)):
        return bytes(origen)
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


def _numero_es(serie, decimal_punto=False):
    texto = serie.astype("string").str.strip().str.replace(" ", "", regex=False)
    if decimal_punto:
        texto = texto.str.replace(",", ".", regex=False)
    else:
        texto = texto.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(texto, errors="coerce")


def _es_excel_sips(origen, contenido):
    nombre = str(getattr(origen, "name", origen) or "").lower()
    return (
        nombre.endswith((".xlsx", ".xls"))
        or contenido.startswith(b"PK\x03\x04")
        or contenido.startswith(bytes.fromhex("D0CF11E0A1B11AE1"))
    )


def es_sips_excel_html(origen):
    """Reconoce las exportaciones HTML que Excel guarda con extensión .xls."""
    contenido = _leer_bytes(origen)
    inicio = contenido.lstrip()[:32].lower()
    return inicio.startswith((b"<html", b"<!doctype html"))


class _LectorTablaHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.filas = []
        self.fila = None
        self.celda = None

    def handle_starttag(self, etiqueta, atributos):
        if etiqueta == "tr":
            self.fila = []
        elif etiqueta in {"td", "th"} and self.fila is not None:
            self.celda = []

    def handle_data(self, dato):
        if self.celda is not None:
            self.celda.append(dato)

    def handle_endtag(self, etiqueta):
        if etiqueta in {"td", "th"} and self.celda is not None:
            self.fila.append("".join(self.celda).strip())
            self.celda = None
        elif etiqueta == "tr" and self.fila is not None:
            self.filas.append(self.fila)
            self.fila = None


def _filas_excel_sips(contenido):
    """Localiza la hoja de medidas de un SIPS Excel y la convierte en filas."""
    if es_sips_excel_html(contenido):
        lector = _LectorTablaHTML()
        lector.feed(_decodificar(contenido))
        grupos_filas = [lector.filas]
    else:
        try:
            hojas = pd.read_excel(
                io.BytesIO(contenido), sheet_name=None, header=None, dtype=object
            )
        except (ImportError, OSError, ValueError) as exc:
            raise ValueError(f"No se ha podido leer el Excel SIPS: {exc}") from exc
        grupos_filas = [
            [
                ["" if pd.isna(valor) else str(valor).strip() for valor in fila]
                for fila in tabla.itertuples(index=False, name=None)
            ]
            for tabla in hojas.values()
        ]
    for filas in grupos_filas:
        for fila in filas:
            nombres = {_nombre_columna(celda) for celda in fila}
            if {
                "cups", "fecha_lectura_inicial", "fecha_lectura_final",
                "p1_activa", "p1_reactiva", "p1_maximetro",
            }.issubset(nombres):
                return filas
    raise ValueError("No encuentro una hoja de medidas SIPS reconocida.")


def es_sips_excel(origen):
    """Distingue una tabla SIPS de un Excel de consumos genérico."""
    if es_sips_excel_html(origen):
        return True
    if not str(getattr(origen, "name", origen) or "").lower().endswith((".xls", ".xlsx")):
        return False
    try:
        _filas_excel_sips(_leer_bytes(origen))
    except ValueError:
        return False
    return True


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


def _extraer_metadatos(filas, limite):
    """Localiza la ficha superior aunque el CSV incluya títulos y separadores."""
    for indice, fila in enumerate(filas[:limite]):
        cabecera = [_nombre_columna(valor) for valor in fila]
        if "cups" not in cabecera:
            continue
        for valores in filas[indice + 1:limite]:
            if not any(celda.strip() for celda in valores):
                continue
            return {
                nombre: valores[posicion].strip()
                if posicion < len(valores) else ""
                for posicion, nombre in enumerate(cabecera)
                if nombre
            }
    return {}


def leer_sips_completo(origen):
    """Devuelve metadatos, activa, reactiva y maxímetros de un SIPS CSV/Excel."""
    contenido = _leer_bytes(origen)
    es_excel = _es_excel_sips(origen, contenido)
    if es_excel:
        filas = _filas_excel_sips(contenido)
    else:
        texto = _decodificar(contenido)
        filas = list(csv.reader(io.StringIO(texto), delimiter=";"))
    filas_no_vacias = [fila for fila in filas if any(celda.strip() for celda in fila)]
    if len(filas_no_vacias) < 4:
        raise ValueError("El SIPS no contiene ficha y lecturas suficientes.")

    indice_lecturas = None
    formato_lecturas = None
    for indice, fila in enumerate(filas):
        nombres = {_nombre_columna(celda) for celda in fila}
        if {"cups", "f_fin", "f_inicio", "ea1", "er1", "pt1"}.issubset(nombres):
            indice_lecturas = indice
            formato_lecturas = "ea"
            break
        if {
            "fecha", "energia_activa_kwhp1", "energia_reactiva_kvarhp1",
            "potencia_demandada_kwp1",
        }.issubset(nombres):
            indice_lecturas = indice
            formato_lecturas = "mensual"
            break
        if {
            "cups", "fecha_lectura_inicial", "fecha_lectura_final",
            "p1_activa", "p1_reactiva", "p1_maximetro",
        }.issubset(nombres):
            indice_lecturas = indice
            formato_lecturas = "excel"
            break
    if indice_lecturas is None:
        raise ValueError(
            "No encuentro una cabecera de medidas SIPS reconocida."
        )

    metadatos = _extraer_metadatos(filas, indice_lecturas)

    cabecera = [_nombre_columna(valor) for valor in filas[indice_lecturas]]
    datos = [
        fila for fila in filas[indice_lecturas + 1:]
        if any(celda.strip() for celda in fila)
    ]
    # Ignora posibles secciones posteriores con una anchura distinta.
    datos = [fila for fila in datos if len(fila) == len(cabecera)]
    lecturas = pd.DataFrame(datos, columns=cabecera)

    if formato_lecturas == "mensual":
        renombrado = {"fecha": "f_fin"}
        for periodo in range(1, 7):
            renombrado.update({
                f"energia_activa_kwhp{periodo}": f"ea{periodo}",
                f"energia_reactiva_kvarhp{periodo}": f"er{periodo}",
                f"potencia_demandada_kwp{periodo}": f"pt{periodo}",
            })
        lecturas = lecturas.rename(columns=renombrado)
        lecturas["cups"] = metadatos.get("cups", "")
        lecturas["fecha_fin"] = pd.to_datetime(
            lecturas["f_fin"], errors="coerce", dayfirst=True
        )
        lecturas["fecha_inicio"] = (
            lecturas["fecha_fin"].dt.to_period("M").dt.start_time
        )
    elif formato_lecturas == "excel":
        renombrado = {
            "fecha_lectura_inicial": "f_inicio",
            "fecha_lectura_final": "f_fin",
        }
        for periodo in range(1, 7):
            renombrado.update({
                f"p{periodo}_activa": f"ea{periodo}",
                f"p{periodo}_reactiva": f"er{periodo}",
                f"p{periodo}_maximetro": f"pt{periodo}",
            })
        lecturas = lecturas.rename(columns=renombrado)
        lecturas["fecha_fin"] = pd.to_datetime(
            lecturas["f_fin"], errors="coerce"
        )
        lecturas["fecha_inicio"] = pd.to_datetime(
            lecturas["f_inicio"], errors="coerce"
        )
    else:
        lecturas["fecha_fin"] = pd.to_datetime(lecturas["f_fin"], errors="coerce")
        lecturas["fecha_inicio"] = pd.to_datetime(
            lecturas["f_inicio"], errors="coerce"
        )

    columnas_requeridas = {
        "cups", "f_fin",
        *[f"ea{i}" for i in range(1, 7)],
        *[f"er{i}" for i in range(1, 7)],
        *[f"pt{i}" for i in range(1, 7)],
    }
    faltantes = columnas_requeridas.difference(lecturas.columns)
    if faltantes:
        raise ValueError(
            "Faltan columnas SIPS: " + ", ".join(sorted(faltantes)) + "."
        )

    cups_lecturas = lecturas["cups"].dropna().astype(str).str.strip()
    cups_lecturas = cups_lecturas.loc[cups_lecturas.ne("")]
    if not metadatos.get("cups") and not cups_lecturas.empty:
        metadatos["cups"] = cups_lecturas.iloc[0]

    lecturas = lecturas.dropna(subset=["fecha_fin", "fecha_inicio"]).copy()
    if lecturas.empty:
        raise ValueError("El SIPS no contiene ciclos con fechas válidas.")
    lecturas["periodo_mes"] = lecturas["fecha_fin"].dt.to_period("M")
    if formato_lecturas == "mensual":
        lecturas["dias_facturacion"] = lecturas["fecha_fin"].dt.days_in_month
    else:
        lecturas["dias_facturacion"] = (
            lecturas["fecha_fin"].dt.normalize()
            - lecturas["fecha_inicio"].dt.normalize()
        ).dt.days.clip(lower=0)
    for prefijo in ("ea", "er", "pt"):
        for periodo in range(1, 7):
            columna = f"{prefijo}{periodo}"
            lecturas[columna] = _numero_es(
                lecturas[columna], decimal_punto=es_excel
            ).fillna(0.0)

    return {
        "metadatos": metadatos,
        "atr": obtener_atr_sips(metadatos),
        "consumos": _tabla_magnitud(lecturas, "ea", "sum"),
        "reactiva": _tabla_magnitud(lecturas, "er", "sum"),
        "maximetros": _tabla_magnitud(lecturas, "pt", "max"),
    }


def potencias_contratadas_sips(metadatos):
    """Extrae P1-P6 de una ficha SIPS normalizada, en kW."""
    potencias = pd.Series(
        index=[f"P{i}" for i in range(1, 7)], dtype=float
    )
    metadatos = metadatos or {}
    for numero_periodo in range(1, 7):
        periodo = f"P{numero_periodo}"
        claves = (
            f"potencia_contratada_p{numero_periodo}",
            f"potencia_contratada_{numero_periodo}",
            f"pot_contratada_p{numero_periodo}",
            f"pot_contratada_{numero_periodo}",
            f"pot_cont_p{numero_periodo}",
            f"pot_cont_{numero_periodo}",
            f"potencia_p{numero_periodo}",
            f"potencia_{numero_periodo}",
            f"p{numero_periodo}",
            f"pc{numero_periodo}",
            f"pt{numero_periodo}",
            *(["ptl"] if numero_periodo == 1 else []),
        )
        for clave in claves:
            if metadatos.get(clave) in (None, ""):
                continue
            texto = str(metadatos[clave]).strip()
            if "," in texto:
                texto = texto.replace(".", "").replace(",", ".")
            potencias[periodo] = pd.to_numeric(texto, errors="coerce")
            break
        if pd.notna(potencias[periodo]):
            continue
        patron = re.compile(
            rf"(?:pot|potencia|pc).*?(?:p|periodo)?_?{numero_periodo}(?:_|$)"
        )
        for clave, valor in metadatos.items():
            if not patron.search(clave):
                continue
            coincidencia = re.search(r"\d+(?:[.,]\d+)?", str(valor))
            if coincidencia:
                potencia = float(coincidencia.group().replace(",", "."))
                if clave.endswith("_w"):
                    potencia /= 1000
                potencias[periodo] = potencia
                break
    if not potencias.notna().any():
        for clave, valor in metadatos.items():
            if "pot" not in clave or not valor:
                continue
            numeros = re.findall(r"\d+(?:[.,]\d+)?", str(valor))
            if len(numeros) >= 6:
                potencias[:] = [
                    float(numero.replace(",", "."))
                    for numero in numeros[:6]
                ]
                break
    return potencias


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
