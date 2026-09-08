"""Servicio compartido para construir y publicar la curva activa de ePowerApp."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, MutableMapping, Sequence

import pandas as pd

from backend_curvadecarga import (
    agrupar_curva_horaria,
    analizar_calidad_curva,
    completar_periodos_curva,
    detectar_periodos_en_fuente,
    inferir_zonas_por_periodos,
    normalize_curve_simple,
)


CLAVES_CURVA_SESION = (
    "df_norm", "df_norm_h", "df_in", "csv_bytes_norm", "csv_bytes_h",
    "lista_ficheros", "consumo_total", "reactiva_total", "vertido_total",
    "consumo_neto", "vertido_neto", "rango_curvadecarga",
    "rango_fechas_comparativa", "rango_fechas_comparativa_guardado",
    "_rango_fechas_comparativa", "precios_mensuales", "df_curva_sheets",
    "resumen_costes_contractuales", "origen_costes_comparativa",
    "cups_costes_comparativa", "version_curva_costes_comparativa",
    "df_axon_raw", "frec_axon_raw", "df_datadis_raw", "frec_datadis_raw",
    "suministros_datadis", "datadis_curvas_cache", "datadis_detalles_cache",
    "detalle_datadis_actual", "detalle_datadis_clave", "cups_curva",
    "reactiva_base_cache", "reactiva_compensacion",
    "curva_escala_manual_1000_aplicada", "curva_reactiva_version",
    "df_curva_simulindex_persistente", "_firma_curva_simulindex",
    "informe_reactiva_html", "comparativa_informe_datos",
    "informe_comparativa_html", "diagnosticos_curva",
    "curva_periodos_en_origen", "curva_actual",
    "zona_periodos_confirmada",
)


@dataclass(frozen=True)
class ResultadoCurva:
    """Resultado completo y transportable de una normalización."""

    df_norm: pd.DataFrame
    df_norm_h: pd.DataFrame
    df_in: pd.DataFrame | None
    frecuencia: str
    atr: str
    zona_periodos: str
    periodos_en_origen: bool
    diagnosticos: list[dict[str, Any]]
    nombres_archivos: list[str]
    mensajes_unidades: list[str]
    zonas_compatibles: list[str]
    cobertura_zonas: float
    csv_bytes_norm: bytes
    csv_bytes_h: bytes

    @property
    def rango_fechas(self) -> tuple[Any, Any]:
        return self.df_norm["fecha"].min(), self.df_norm["fecha"].max()

    @property
    def totales(self) -> dict[str, float]:
        return {
            "consumo_total": float(self.df_norm["consumo_kWh"].sum()),
            "reactiva_total": float(self.df_norm["reactiva_kVArh"].sum()),
            "vertido_total": float(self.df_norm["excedentes_kWh"].sum()),
            "consumo_neto": float(self.df_norm["consumo_neto_kWh"].sum()),
            "vertido_neto": float(self.df_norm["vertido_neto_kWh"].sum()),
        }


def _nombre_fuente(fuente: Any) -> str:
    return str(getattr(fuente, "name", fuente))


def _detectar_atr_periodos(df_norm: pd.DataFrame, atr_indicado: str) -> str:
    if "periodo" not in df_norm.columns:
        return str(atr_indicado)
    numeros = (
        df_norm["periodo"].astype("string")
        .str.extract(r"P?(\d+)", expand=False).dropna().astype(int)
    )
    return "2.0" if not numeros.empty and numeros.max() == 3 else str(atr_indicado)


def inspeccionar_periodos_fuentes(
    fuentes: Any | Sequence[Any], excel_sheet: str | None = None
) -> bool:
    """Indica si todas las fuentes aportan una columna de periodos válida."""
    archivos = list(fuentes) if isinstance(fuentes, (list, tuple)) else [fuentes]
    return bool(archivos) and all(
        detectar_periodos_en_fuente(archivo, preferred_sheet=excel_sheet)
        for archivo in archivos
    )


def normalizar_fuentes_curva(
    fuentes: Any | Sequence[Any],
    atr: str,
    zona_periodos: str = "peninsula",
    excel_sheet: str | None = None,
) -> ResultadoCurva:
    """Normaliza uno o varios archivos y construye la curva compartida.

    Axon y Datadis entran también aquí después de convertir su DataFrame en un
    archivo en memoria mediante ``dataframe_como_archivo_curva``.
    """
    archivos = list(fuentes) if isinstance(fuentes, (list, tuple)) else [fuentes]
    if not archivos:
        raise ValueError("No se ha facilitado ninguna curva para normalizar.")

    normalizadas, originales, diagnosticos = [], [], []
    flags_periodos, frecuencias, mensajes_unidades, nombres = [], [], [], []

    for archivo in archivos:
        nombre = _nombre_fuente(archivo)
        (df_in, df_norm, mensaje_unidades, periodos_en_origen,
         df_periodos, frecuencia) = normalize_curve_simple(
            archivo,
            origin=nombre,
            excel_sheet=excel_sheet,
            zona_periodos=zona_periodos,
        )
        diagnosticos.append(analizar_calidad_curva(
            df_norm,
            df_origen=df_in,
            frecuencia=frecuencia,
            periodos_en_origen=periodos_en_origen,
            origen=nombre,
        ))
        if not periodos_en_origen:
            df_norm = completar_periodos_curva(df_norm, df_periodos, atr)
        normalizadas.append(df_norm)
        originales.append(df_in)
        flags_periodos.append(bool(periodos_en_origen))
        frecuencias.append(frecuencia)
        nombres.append(nombre)
        if mensaje_unidades and mensaje_unidades not in mensajes_unidades:
            mensajes_unidades.append(mensaje_unidades)

    if len(set(frecuencias)) != 1:
        detalle = ", ".join(
            f"{nombre}: {frecuencia}"
            for nombre, frecuencia in zip(nombres, frecuencias)
        )
        raise ValueError(
            "No se pueden combinar curvas con resoluciones temporales "
            f"distintas ({detalle})."
        )

    frecuencia = frecuencias[0]
    df_norm = pd.concat(normalizadas, ignore_index=True)
    df_norm = df_norm.sort_values("fecha_hora").reset_index(drop=True)
    periodos_en_todos = bool(flags_periodos) and all(flags_periodos)
    atr_resultado = (
        _detectar_atr_periodos(df_norm, atr) if periodos_en_todos else str(atr)
    )
    df_norm_h = agrupar_curva_horaria(df_norm, frecuencia)
    if periodos_en_todos:
        zonas_compatibles, cobertura_zonas = inferir_zonas_por_periodos(df_norm)
    else:
        zonas_compatibles, cobertura_zonas = [], 0.0
    csv_norm = df_norm.to_csv(
        index=False, sep=";", decimal=",", float_format="%.3f"
    ).encode("utf-8")
    csv_h = df_norm_h.to_csv(
        index=False, sep=";", decimal=",", float_format="%.3f"
    ).encode("utf-8")
    return ResultadoCurva(
        df_norm=df_norm,
        df_norm_h=df_norm_h,
        df_in=originales[0] if len(originales) == 1 else None,
        frecuencia=frecuencia,
        atr=atr_resultado,
        zona_periodos=str(zona_periodos),
        periodos_en_origen=periodos_en_todos,
        diagnosticos=diagnosticos,
        nombres_archivos=nombres,
        mensajes_unidades=mensajes_unidades,
        zonas_compatibles=zonas_compatibles,
        cobertura_zonas=cobertura_zonas,
        csv_bytes_norm=csv_norm,
        csv_bytes_h=csv_h,
    )


def publicar_curva_sesion(
    estado: MutableMapping[str, Any], resultado: ResultadoCurva
) -> None:
    """Publica una curva como única curva activa y conserva las claves antiguas."""
    version = int(estado.get("curva_reactiva_version", 0)) + 1
    curva_actual = {
        "df_norm": resultado.df_norm,
        "df_norm_h": resultado.df_norm_h,
        "df_in": resultado.df_in,
        "frecuencia": resultado.frecuencia,
        "atr": resultado.atr,
        "zona_periodos": resultado.zona_periodos,
        "periodos_en_origen": resultado.periodos_en_origen,
        "diagnosticos": resultado.diagnosticos,
        "nombres_archivos": resultado.nombres_archivos,
        "zonas_compatibles": resultado.zonas_compatibles,
        "cobertura_zonas": resultado.cobertura_zonas,
        "zona_confirmada": (
            resultado.zonas_compatibles[0]
            if len(resultado.zonas_compatibles) == 1 else None
        ),
        "rango_fechas": resultado.rango_fechas,
        "version": version,
    }
    estado.update({
        "curva_actual": curva_actual,
        "df_norm": resultado.df_norm,
        "df_norm_h": resultado.df_norm_h,
        "df_in": resultado.df_in,
        "csv_bytes_norm": resultado.csv_bytes_norm,
        "csv_bytes_h": resultado.csv_bytes_h,
        "lista_ficheros": (
            resultado.nombres_archivos if len(resultado.nombres_archivos) > 1
            else None
        ),
            "atr_dfnorm": resultado.atr,
            "atr_curva_preferido": resultado.atr,
        "frec": resultado.frecuencia,
        "rango_curvadecarga": resultado.rango_fechas,
        "diagnosticos_curva": resultado.diagnosticos,
        "curva_periodos_en_origen": resultado.periodos_en_origen,
        "curva_escala_manual_1000_aplicada": False,
        "curva_reactiva_version": version,
        **resultado.totales,
    })
    for clave in (
        "reactiva_base_cache", "reactiva_compensacion", "informe_reactiva_html"
    ):
        estado.pop(clave, None)


def obtener_curva_sesion(
    estado: MutableMapping[str, Any],
) -> dict[str, Any] | None:
    """Devuelve la curva activa, incluyendo sesiones previas a este servicio."""
    curva = estado.get("curva_actual")
    if curva is not None:
        return curva
    if estado.get("df_norm") is None or estado.get("df_norm_h") is None:
        return None
    return {
        "df_norm": estado["df_norm"],
        "df_norm_h": estado["df_norm_h"],
        "df_in": estado.get("df_in"),
        "frecuencia": estado.get("frec"),
        "atr": estado.get("atr_dfnorm"),
        "zona_periodos": estado.get("zona_periodos_cdc", "peninsula"),
        "periodos_en_origen": estado.get("curva_periodos_en_origen", False),
        "diagnosticos": estado.get("diagnosticos_curva", []),
        "nombres_archivos": estado.get("lista_ficheros") or [],
        "zonas_compatibles": [],
        "cobertura_zonas": 0.0,
        "zona_confirmada": estado.get("zona_periodos_confirmada"),
        "rango_fechas": estado.get("rango_curvadecarga"),
        "version": estado.get("curva_reactiva_version", 0),
    }


def sincronizar_curva_sesion(estado: MutableMapping[str, Any]) -> None:
    """Sincroniza el contrato común tras una modificación de la curva activa."""
    if estado.get("df_norm") is None or estado.get("df_norm_h") is None:
        estado.pop("curva_actual", None)
        return
    curva = dict(estado.get("curva_actual") or {})
    curva.update({
        "df_norm": estado["df_norm"],
        "df_norm_h": estado["df_norm_h"],
        "df_in": estado.get("df_in"),
        "frecuencia": estado.get("frec"),
        "atr": estado.get("atr_dfnorm"),
        "zona_periodos": estado.get("zona_periodos_cdc", "peninsula"),
        "periodos_en_origen": estado.get("curva_periodos_en_origen", False),
        "diagnosticos": estado.get("diagnosticos_curva", []),
        "nombres_archivos": estado.get("lista_ficheros") or [],
        "rango_fechas": estado.get("rango_curvadecarga"),
        "version": estado.get("curva_reactiva_version", 0),
    })
    estado["curva_actual"] = curva


def limpiar_curva_sesion(estado: MutableMapping[str, Any]) -> None:
    """Elimina la curva activa y sus resultados derivados de la sesión."""
    for clave in CLAVES_CURVA_SESION:
        estado.pop(clave, None)
    estado["curva_uploader_version"] = (
        int(estado.get("curva_uploader_version", 0)) + 1
    )
