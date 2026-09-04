"""Persistencia local y versionada de ofertas fijas extraídas de imágenes."""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd


RUTA_CATALOGO_OFERTAS = Path(__file__).resolve().parent / "data" / "ofertas_fijas.json"
PATRON_CATALOGOS_IMPORTADOS = "ofertas_fijas_importadas_*.json"
PERIODOS = [f"P{i}" for i in range(1, 7)]
UNIDAD_POTENCIA_DIARIA = "€/kW/día"


def potencia_mensual_a_diaria(valor):
    """Convierte un precio de potencia mensual a su equivalente diario anual."""
    numero = pd.to_numeric(valor, errors="coerce")
    return None if pd.isna(numero) else float(numero) * 12 / 365


def resolver_potencia_tarifa(tarifa: dict, fecha_referencia=None) -> dict | None:
    """Obtiene la potencia diaria fija o resuelve la referencia regulada BOE."""
    potencia = tarifa.get("potencia")
    if not isinstance(potencia, dict):
        return None
    modalidad_original = str(
        potencia.get("modalidad", "CON MARGEN")
    ).upper()
    modalidad = "BOE" if modalidad_original == "BOE" else "CON MARGEN"
    if modalidad == "BOE":
        from backend_opt2 import precios_potencia_boe_diarios

        precios = precios_potencia_boe_diarios(
            tarifa.get("atr"), fecha_referencia
        )
    else:
        precios = {periodo: potencia.get(periodo) for periodo in PERIODOS}
    return {
        "modalidad": modalidad,
        "unidad": UNIDAD_POTENCIA_DIARIA,
        **precios,
    }


def _leer_catalogo(ruta: Path) -> list[dict]:
    ruta = Path(ruta)
    if not ruta.exists():
        return []
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"No se puede leer el catálogo local: {exc}") from exc
    if isinstance(datos, dict) and datos.get("formato") == "campaña_informa_v1":
        potencias = datos.get("potencias", {})
        consumo_anual = float(datos["consumo_anual_kwh"])
        registros = []
        for indice, oferta in enumerate(datos.get("ofertas", []), start=1):
            comision_eur = oferta.get("comision_estimada_eur")
            comision_mwh = oferta.get("comision_eur_mwh")
            tipo_comision = (
                "FIJA" if comision_eur is not None
                else "VARIABLE" if comision_mwh is not None
                else None
            )
            if comision_eur is None and comision_mwh is not None:
                comision_eur = float(comision_mwh) * consumo_anual / 1000
            comision_kwh = (
                float(comision_eur) / consumo_anual
                if comision_eur is not None and consumo_anual else None
            )
            precios_potencia = potencias[oferta["potencia"]]
            registros.append({
                "id": f"{datos['id_campaña']}-{indice:03d}",
                "nombre": oferta["nombre"],
                "vigencia_desde": datos["vigencia_desde"],
                "vigencia_hasta": datos["vigencia_hasta"],
                "guardado_en": datos["guardado_en"],
                "fuente": datos.get("fuente"),
                "plataforma": datos.get("plataforma", "INFORMA"),
                "zona": oferta.get("zona", "Península"),
                "comision": {
                    "tipo": tipo_comision,
                    "estimada_eur": comision_eur,
                    "eur_mwh": comision_mwh,
                    "eur_kwh": comision_kwh,
                    "consumo_anual_kwh": consumo_anual,
                },
                "potencia": {
                    "modalidad": (
                        "BOE" if oferta["potencia"] == "boe" else "CON MARGEN"
                    ),
                    "unidad": UNIDAD_POTENCIA_DIARIA,
                    **dict(zip(PERIODOS, precios_potencia)),
                },
                "tarifas": [{
                    "atr": "3.0",
                    **dict(zip(PERIODOS, oferta["energia"])),
                }],
            })
        return registros
    if not isinstance(datos, list):
        raise ValueError("El catálogo local de ofertas no tiene formato de lista.")
    return datos


def cargar_catalogo_ofertas(ruta=RUTA_CATALOGO_OFERTAS) -> list[dict]:
    ruta = Path(ruta)
    catalogo = _leer_catalogo(ruta)
    if ruta.resolve() == RUTA_CATALOGO_OFERTAS.resolve():
        for ruta_importada in sorted(ruta.parent.glob(PATRON_CATALOGOS_IMPORTADOS)):
            catalogo.extend(_leer_catalogo(ruta_importada))
    return catalogo


def guardar_version_oferta(
    nombre: str,
    vigencia_desde: date,
    vigencia_hasta: date | None,
    tarifas: pd.DataFrame,
    ruta=RUTA_CATALOGO_OFERTAS,
    potencia_tarifas: pd.DataFrame | None = None,
) -> dict:
    """Añade una versión sin sobrescribir las versiones semanales anteriores."""
    nombre = str(nombre).strip()
    if not nombre:
        raise ValueError("Indica un nombre para la oferta.")
    desde = pd.Timestamp(vigencia_desde).date()
    hasta = (
        pd.Timestamp(vigencia_hasta).date()
        if vigencia_hasta is not None else None
    )
    if hasta is not None and hasta < desde:
        raise ValueError("La fecha fin no puede ser anterior a la fecha inicio.")
    requeridas = {"ATR", *PERIODOS}
    faltantes = requeridas.difference(tarifas.columns)
    if faltantes:
        raise ValueError("Faltan columnas: " + ", ".join(sorted(faltantes)))

    potencias_por_atr = {}
    if potencia_tarifas is not None and not potencia_tarifas.empty:
        if "ATR" not in potencia_tarifas.columns:
            raise ValueError("Falta la columna ATR en los precios de potencia.")
        for _, fila_potencia in potencia_tarifas.iterrows():
            atr_potencia = (
                str(fila_potencia["ATR"]).strip().upper()
                .replace(" ", "").removesuffix("TD")
            )
            modalidad = str(
                fila_potencia.get("Modalidad", "CON MARGEN")
            ).strip() or "CON MARGEN"
            potencias_por_atr[atr_potencia] = {
                "modalidad": modalidad,
                "unidad": UNIDAD_POTENCIA_DIARIA,
                **{
                    periodo: (
                        None if pd.isna(pd.to_numeric(
                            fila_potencia.get(periodo), errors="coerce"
                        )) else float(pd.to_numeric(
                            fila_potencia.get(periodo), errors="coerce"
                        ))
                    )
                    for periodo in PERIODOS
                },
            }

    filas = []
    for _, fila in tarifas.iterrows():
        atr = str(fila["ATR"]).strip().upper().replace(" ", "").removesuffix("TD")
        precios = {}
        for periodo in PERIODOS:
            valor = pd.to_numeric(fila[periodo], errors="coerce")
            precios[periodo] = None if pd.isna(valor) else float(valor)
        tarifa = {"atr": atr, **precios}
        if atr in potencias_por_atr:
            tarifa["potencia"] = potencias_por_atr[atr]
        filas.append(tarifa)
    if not filas:
        raise ValueError("No hay tarifas que guardar.")

    registro = {
        "id": uuid4().hex,
        "nombre": nombre,
        "vigencia_desde": desde.isoformat(),
        "vigencia_hasta": hasta.isoformat() if hasta is not None else None,
        "guardado_en": datetime.now().astimezone().isoformat(timespec="seconds"),
        "tarifas": filas,
    }
    ruta = Path(ruta)
    # Solo se escribe el catálogo manual. Los catálogos importados se agregan
    # en lectura y no deben copiarse ni duplicarse aquí.
    catalogo = _leer_catalogo(ruta)
    catalogo.append(registro)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(f".{ruta.name}.{uuid4().hex}.tmp")
    temporal.write_text(
        json.dumps(catalogo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporal, ruta)
    return registro


def catalogo_a_dataframe(catalogo: list[dict]) -> pd.DataFrame:
    filas = []
    for registro in catalogo:
        for tarifa in registro.get("tarifas", []):
            filas.append({
                "Nombre": registro.get("nombre"),
                "Desde": registro.get("vigencia_desde"),
                "Hasta": registro.get("vigencia_hasta"),
                "ATR": tarifa.get("atr"),
                **{periodo: tarifa.get(periodo) for periodo in PERIODOS},
                "ID": registro.get("id"),
            })
    return pd.DataFrame(filas)
