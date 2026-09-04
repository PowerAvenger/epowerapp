"""Extracción asistida de ofertas fijas desde imágenes.

La IA sólo transcribe la tabla. La validación y los cálculos permanecen en
Python y el usuario debe confirmar los valores antes de incorporarlos.
"""

from __future__ import annotations

import base64
import json

import pandas as pd


ATRS_OFERTA = {"2.0", "3.0", "6.1", "6.2"}
PERIODOS_ATR = {
    "2.0": ["P1", "P2", "P3"],
    "3.0": [f"P{i}" for i in range(1, 7)],
    "6.1": [f"P{i}" for i in range(1, 7)],
    "6.2": [f"P{i}" for i in range(1, 7)],
}


ESQUEMA_OFERTA_IMAGEN = {
    "type": "object",
    "properties": {
        "nombre": {"type": ["string", "null"]},
        "unidad_original": {"type": "string"},
        "tarifas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "atr": {"type": "string"},
                    "P1": {"type": ["number", "null"]},
                    "P2": {"type": ["number", "null"]},
                    "P3": {"type": ["number", "null"]},
                    "P4": {"type": ["number", "null"]},
                    "P5": {"type": ["number", "null"]},
                    "P6": {"type": ["number", "null"]},
                },
                "required": ["atr", "P1", "P2", "P3", "P4", "P5", "P6"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["nombre", "unidad_original", "tarifas"],
    "additionalProperties": False,
}


def _normalizar_atr(valor):
    return str(valor).upper().replace(" ", "").removesuffix("TD")


def _factor_a_eur_kwh(unidad, tarifas=None):
    unidad_limpia = str(unidad).lower().replace(" ", "")
    if "€/mwh" in unidad_limpia or "eur/mwh" in unidad_limpia:
        return 1 / 1000, False
    if "c€/kwh" in unidad_limpia or "cent" in unidad_limpia:
        return 1 / 100, False
    if "€/kwh" in unidad_limpia or "eur/kwh" in unidad_limpia:
        return 1.0, False

    # Muchas capturas comerciales omiten la unidad. En ese caso usamos la
    # magnitud de los precios visibles y obligamos al usuario a revisarlos en
    # el editor antes de incorporarlos a la comparativa.
    valores = []
    for tarifa in tarifas or []:
        for periodo in [f"P{i}" for i in range(1, 7)]:
            valor = tarifa.get(periodo)
            if valor is not None:
                try:
                    valor = float(valor)
                except (TypeError, ValueError):
                    continue
                if valor > 0:
                    valores.append(valor)
    if not valores:
        raise ValueError(f"No se reconoce la unidad de la oferta: {unidad}.")

    valor_referencia = sorted(valores)[len(valores) // 2]
    if valor_referencia < 2:
        return 1.0, True          # precios como 0,236937: EUR/kWh
    if valor_referencia < 100:
        return 1 / 100, True      # precios como 23,6937: cent EUR/kWh
    return 1 / 1000, True         # precios como 236,937: EUR/MWh


def validar_oferta_extraida(resultado):
    """Valida y convierte la extracción a una tabla canónica en €/kWh."""
    if not isinstance(resultado, dict) or not resultado.get("tarifas"):
        raise ValueError("No se ha detectado ninguna tarifa en la imagen.")
    factor, unidad_inferida = _factor_a_eur_kwh(
        resultado.get("unidad_original"), resultado.get("tarifas")
    )
    filas = []
    for tarifa in resultado["tarifas"]:
        atr = _normalizar_atr(tarifa.get("atr"))
        if atr not in ATRS_OFERTA:
            continue
        fila = {"ATR": atr}
        for periodo in [f"P{i}" for i in range(1, 7)]:
            valor = tarifa.get(periodo)
            fila[periodo] = None if valor is None else float(valor) * factor
        for periodo in PERIODOS_ATR[atr]:
            valor = fila[periodo]
            if valor is None or not 0 < valor < 2:
                raise ValueError(f"El precio {periodo} de {atr}TD no es válido.")
        filas.append(fila)
    if not filas:
        raise ValueError("No se ha detectado un ATR compatible.")
    tabla = pd.DataFrame(filas)
    tabla.attrs["unidad_inferida"] = unidad_inferida
    return tabla, resultado.get("nombre")


def extraer_oferta_imagen(
    contenido,
    mime_type,
    api_key,
    modelo="gpt-5.6-luna",
):
    """Envía una imagen al modelo y devuelve tarifas validadas en €/kWh."""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "Falta instalar el paquete openai incluido en requirements.txt."
        ) from exc

    imagen_b64 = base64.b64encode(contenido).decode("ascii")
    cliente = OpenAI(api_key=api_key)
    respuesta = cliente.responses.create(
        model=modelo,
        store=False,
        reasoning={"effort": "low"},
        instructions=(
            "Eres un extractor de tablas de ofertas eléctricas. Transcribe "
            "exclusivamente datos visibles. No inventes precios ni periodos. "
            "Conserva la unidad original y convierte comas decimales a números."
        ),
        input=[{
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "Extrae todas las filas ATR y sus precios P1-P6. "
                        "Usa null para periodos que no aparezcan."
                    ),
                },
                {
                    "type": "input_image",
                    "image_url": f"data:{mime_type};base64,{imagen_b64}",
                    "detail": "high",
                },
            ],
        }],
        text={
            "format": {
                "type": "json_schema",
                "name": "oferta_electrica",
                "strict": True,
                "schema": ESQUEMA_OFERTA_IMAGEN,
            }
        },
    )
    return validar_oferta_extraida(json.loads(respuesta.output_text))
