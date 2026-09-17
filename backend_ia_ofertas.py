"""Extracción asistida de ofertas fijas desde imágenes.

La IA sólo transcribe la tabla. La validación y los cálculos permanecen en
Python y el usuario debe confirmar los valores antes de incorporarlos.
"""

from __future__ import annotations

import base64
import json
import math
import re
import unicodedata

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
        "unidad_potencia_original": {"type": ["string", "null"]},
        "tarifas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nombre": {"type": ["string", "null"]},
                    "atr": {"type": "string"},
                    "P1": {"type": ["number", "null"]},
                    "P2": {"type": ["number", "null"]},
                    "P3": {"type": ["number", "null"]},
                    "P4": {"type": ["number", "null"]},
                    "P5": {"type": ["number", "null"]},
                    "P6": {"type": ["number", "null"]},
                    **{
                        f"potencia_P{i}": {"type": ["number", "null"]}
                        for i in range(1, 7)
                    },
                },
                "required": [
                    "nombre", "atr", "P1", "P2", "P3", "P4", "P5", "P6",
                    "potencia_P1", "potencia_P2", "potencia_P3",
                    "potencia_P4", "potencia_P5", "potencia_P6",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "nombre", "unidad_original", "unidad_potencia_original", "tarifas"
    ],
    "additionalProperties": False,
}


def _normalizar_atr(valor):
    return str(valor).upper().replace(" ", "").removesuffix("TD")


def detectar_atr_en_texto(valor):
    """Recupera el ATR cuando la IA lo deja en el nombre de la fila."""
    texto = str(valor or "").upper().replace(",", ".")
    coincidencia = re.search(
        r"(?<!\d)(2\.0|3\.0|6\.1|6\.2)(?:\s*TD)?(?!\d)", texto
    )
    return coincidencia.group(1) if coincidencia else None


def _numero_extraido(valor):
    """Convierte una celda leída por IA sin inventar valores dudosos."""
    if valor is None:
        return None
    if isinstance(valor, str):
        texto = valor.strip().lower()
        if not texto or texto in {"-", "--", "---", "null", "none", "n/a"}:
            return None
        texto = texto.replace(" ", "").replace(",", ".")
        valor = texto
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


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
            valor = _numero_extraido(tarifa.get(periodo))
            if valor is not None and valor > 0:
                valores.append(valor)
    if not valores:
        raise ValueError(f"No se reconoce la unidad de la oferta: {unidad}.")

    valor_referencia = sorted(valores)[len(valores) // 2]
    if valor_referencia < 2:
        return 1.0, True          # precios como 0,236937: EUR/kWh
    if valor_referencia < 100:
        return 1 / 100, True      # precios como 23,6937: cent EUR/kWh
    return 1 / 1000, True         # precios como 236,937: EUR/MWh


def _texto_normalizado(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(c for c in texto if not unicodedata.combining(c)).casefold()


def _fusionar_filas_potencia_energia(tarifas):
    """Une tablas horizontales que expresan potencia y energía como filas."""
    tarifas = [dict(fila) for fila in tarifas or []]
    indices_potencia = [
        indice for indice, fila in enumerate(tarifas)
        if "potencia" in _texto_normalizado(fila.get("nombre"))
    ]
    indices_energia = [
        indice for indice, fila in enumerate(tarifas)
        if "energia" in _texto_normalizado(fila.get("nombre"))
    ]
    if len(indices_potencia) != 1 or len(indices_energia) != 1:
        return tarifas, False
    indice_potencia, indice_energia = indices_potencia[0], indices_energia[0]
    potencia, energia = tarifas[indice_potencia], tarifas[indice_energia]
    for periodo in [f"P{i}" for i in range(1, 7)]:
        if _numero_extraido(energia.get(f"potencia_{periodo}")) is None:
            energia[f"potencia_{periodo}"] = potencia.get(periodo)
    return [
        fila for indice, fila in enumerate(tarifas)
        if indice not in {indice_potencia, indice_energia}
    ] + [energia], True


def _factor_potencia_a_diaria(unidad, valores=None):
    """Convierte una unidad explícita de potencia a €/kW/día."""
    texto = (
        str(unidad or "").lower().replace(" ", "")
        .replace("eur", "€").replace("año", "ano")
    )
    if "€/kw/d" in texto or "€/kwdia" in texto or "€/kw/dia" in texto:
        return 1.0, False
    if "€/kw/ano" in texto or "€/kwano" in texto:
        return 1 / 365, False
    if "€/kw/mes" in texto or "€/kwmes" in texto:
        return 12 / 365, False
    validos = sorted(
        float(valor) for valor in (valores or [])
        if valor is not None and math.isfinite(float(valor)) and float(valor) > 0
    )
    if validos:
        mediana = validos[len(validos) // 2]
        return (1.0 if mediana < 0.5 else 1 / 365), True
    raise ValueError(
        "Se han detectado precios de potencia, pero no se reconoce su unidad."
    )


def validar_oferta_extraida(resultado, atr_contexto=None):
    """Valida y convierte la extracción a una tabla canónica en €/kWh."""
    if not isinstance(resultado, dict) or not resultado.get("tarifas"):
        raise ValueError("No se ha detectado ninguna tarifa en la imagen.")
    tarifas, filas_fusionadas = _fusionar_filas_potencia_energia(
        resultado.get("tarifas")
    )
    factor, unidad_inferida = _factor_a_eur_kwh(
        resultado.get("unidad_original"), tarifas
    )
    filas = []
    filas_potencia = []
    campos_revisar = []
    nombres_usados = {}
    numero_tarifas = len(tarifas)
    nombre_global = str(resultado.get("nombre") or "Oferta desde imagen").strip()
    potencia_unidad_inferida = False
    for indice, tarifa in enumerate(tarifas, start=1):
        # La etiqueta visible de la fila (p. ej. "2.0 TD") es más fiable que
        # un ATR repetido erróneamente por el modelo en todas las filas.
        atr_nombre = detectar_atr_en_texto(tarifa.get("nombre"))
        atr = atr_nombre or _normalizar_atr(tarifa.get("atr"))
        if atr not in ATRS_OFERTA and atr_contexto is not None:
            atr = _normalizar_atr(atr_contexto)
        if atr not in ATRS_OFERTA:
            continue
        nombre_fila = str(tarifa.get("nombre") or "").strip()
        if not nombre_fila:
            nombre_fila = (
                nombre_global if numero_tarifas == 1
                else f"{nombre_global} {indice}"
            )
        clave_nombre = nombre_fila.casefold()
        repeticion = nombres_usados.get(clave_nombre, 0) + 1
        nombres_usados[clave_nombre] = repeticion
        if repeticion > 1:
            nombre_fila = f"{nombre_fila} ({repeticion})"
        fila = {"oferta": nombre_fila, "ATR": atr}
        for periodo in [f"P{i}" for i in range(1, 7)]:
            valor_original = tarifa.get(periodo)
            valor = _numero_extraido(valor_original)
            fila[periodo] = None if valor is None else valor * factor
        for periodo in PERIODOS_ATR[atr]:
            valor = fila[periodo]
            if valor is None or not 0 < valor < 2:
                fila[periodo] = None
                campos_revisar.append({
                    "atr": atr,
                    "periodo": periodo,
                    "valor_extraido": tarifa.get(periodo),
                })
        filas.append(fila)
        valores_potencia = {
            periodo: _numero_extraido(tarifa.get(f"potencia_{periodo}"))
            for periodo in [f"P{i}" for i in range(1, 7)]
        }
        if any(valor is not None for valor in valores_potencia.values()):
            factor_potencia, potencia_inferida_fila = _factor_potencia_a_diaria(
                resultado.get("unidad_potencia_original"),
                valores_potencia.values(),
            )
            potencia_unidad_inferida = (
                potencia_unidad_inferida or potencia_inferida_fila
            )
            periodos_potencia = (
                ["P1", "P2"] if atr == "2.0"
                else [f"P{i}" for i in range(1, 7)]
            )
            fila_potencia = {"ATR": atr, "Modalidad": "BOE"}
            for periodo in [f"P{i}" for i in range(1, 7)]:
                valor = valores_potencia[periodo]
                fila_potencia[periodo] = (
                    None if valor is None else valor * factor_potencia
                )
            faltantes_potencia = [
                periodo for periodo in periodos_potencia
                if fila_potencia[periodo] is None
                or fila_potencia[periodo] <= 0
            ]
            if faltantes_potencia:
                raise ValueError(
                    f"Faltan precios de potencia para {atr}TD: "
                    + ", ".join(faltantes_potencia) + "."
                )
            filas_potencia.append(fila_potencia)
    if not filas:
        raise ValueError("No se ha detectado un ATR compatible.")
    tabla = pd.DataFrame(filas)
    tabla.attrs["unidad_inferida"] = unidad_inferida
    tabla.attrs["campos_revisar"] = campos_revisar
    tabla.attrs["potencia_tarifas"] = pd.DataFrame(filas_potencia)
    tabla.attrs["unidad_potencia_inferida"] = potencia_unidad_inferida
    tabla.attrs["filas_potencia_energia_fusionadas"] = filas_fusionadas
    tabla.attrs["unidad_potencia_original"] = resultado.get(
        "unidad_potencia_original"
    )
    return tabla, resultado.get("nombre")


def extraer_oferta_imagen(
    contenido,
    mime_type,
    api_key,
    modelo="gpt-5.6-luna",
    atr_contexto=None,
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
            "Conserva la unidad original y convierte comas decimales a números. "
            "Mantén exactamente la escala decimal: 0,130714 debe ser 0.130714, "
            "nunca 130714. Los guiones son null, pero solo en la celda donde "
            "aparecen. Las tarifas 3.0TD, 6.1TD y 6.2TD suelen tener P1-P6: "
            "revisa por segunda vez esas seis columnas antes de responder. "
            "Si la primera columna contiene 2.0TD, 3.0TD, 6.1TD o 6.2TD, "
            "copia ese valor en el campo atr de su misma fila. "
            "Cada fila de precios es una oferta independiente: conserva en el "
            "campo nombre su etiqueta comercial completa. Si dos filas tienen "
            "la misma etiqueta, incorpora otro dato visible de la fila, como "
            "el valor OMIE, para que sus nombres sean inequívocos. "
            "Los campos P1-P6 representan siempre ENERGÍA. Si también hay una "
            "tabla de potencia, transcríbela en potencia_P1-potencia_P6 y copia "
            "su unidad exacta en unidad_potencia_original. Si solo hay una "
            "tabla P1-P6 sin indicación de potencia, trátala como energía y "
            "deja todos los campos potencia_P en null. Cuando la captura "
            "contenga dos tablas, la tabla de potencia aparece primero y la "
            "tabla de energía después; confirma igualmente sus encabezados y "
            "unidades visibles antes de asignar los valores. Una tabla única "
            "también puede contener dos filas llamadas POTENCIA y ENERGÍA: "
            "asigna POTENCIA a potencia_P1-potencia_P6 y ENERGÍA a P1-P6 "
            "dentro de una sola tarifa."
        ),
        input=[{
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "Extrae todas las filas de ofertas y sus precios de "
                        "energía P1-P6, y también la potencia si aparece, "
                        "incluido el nombre de cada fila. Si la tabla no muestra "
                        "ATR, deja atr vacío: se aplicará el ATR del contexto. "
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
    return validar_oferta_extraida(
        json.loads(respuesta.output_text), atr_contexto=atr_contexto
    )
