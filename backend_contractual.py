"""Aplicacion auditable de condiciones contractuales a una curva horaria."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from backend_indexado import FormulaIndexada, calcular_precios_atr_formula
from data_beta.db import DEFAULT_DB_PATH, connect, initialize_database


POSICIONES_LEGACY = {"1": "perdidas", "2": "tm", "3": "neto"}


def cargar_datos_suministro(cups, fecha=None, db_path: str | Path = DEFAULT_DB_PATH):
    """Devuelve suministro y titular vigente para autocompletar documentos."""
    initialize_database(db_path)
    cups20 = re.sub(r"[^A-Z0-9]", "", str(cups or "").upper())[:20]
    if len(cups20) != 20:
        return {}
    fecha_ref = pd.Timestamp(fecha or pd.Timestamp.today()).strftime("%Y-%m-%d")
    query = """
        SELECT s.cups20, s.atr, s.denominacion, s.direccion_1,
            s.direccion_2, s.codigo_postal, s.municipio, s.provincia,
            t.nombre_legal, t.nif,
            t.direccion_facturacion_1, t.direccion_facturacion_2
        FROM suministros s
        LEFT JOIN titularidades_suministro ts ON ts.id = (
            SELECT ts2.id
            FROM titularidades_suministro ts2
            WHERE ts2.suministro_id = s.id
              AND (ts2.vigente_desde IS NULL OR ts2.vigente_desde <= ?)
              AND (ts2.vigente_hasta IS NULL OR ts2.vigente_hasta >= ?)
            ORDER BY
                CASE WHEN ts2.vigente_desde IS NULL THEN 1 ELSE 0 END,
                ts2.vigente_desde DESC, ts2.id DESC
            LIMIT 1
        )
        LEFT JOIN titulares t ON t.id = ts.titular_id
        WHERE s.cups20 = ?
    """
    with connect(db_path) as connection:
        fila = connection.execute(query, (fecha_ref, fecha_ref, cups20)).fetchone()
    if fila is None:
        return {}

    def unir(*partes):
        return ", ".join(str(parte).strip() for parte in partes if str(parte or "").strip())

    return {
        "cliente": str(fila["nombre_legal"] or fila["denominacion"] or "").strip(),
        "nif": str(fila["nif"] or "").strip(),
        "direccion": unir(
            fila["direccion_1"], fila["direccion_2"], fila["codigo_postal"],
            fila["municipio"], fila["provincia"],
        ),
        "direccion_facturacion": unir(
            fila["direccion_facturacion_1"], fila["direccion_facturacion_2"]
        ),
        "cups": str(fila["cups20"] or "").strip(),
        "atr": str(fila["atr"] or "").strip(),
    }


def _numero_es(valor, default=0.0):
    if valor is None or str(valor).strip() == "":
        return default
    texto = str(valor).strip().replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    return float(texto)


def cargar_condiciones_cups(cups, db_path: str | Path = DEFAULT_DB_PATH):
    """Carga las versiones de condiciones enlazadas al CUPS indicado."""
    cups20 = re.sub(r"[^A-Z0-9]", "", str(cups or "").upper())[:20]
    if len(cups20) != 20:
        raise ValueError("El CUPS debe contener al menos 20 caracteres validos.")
    query = """
        SELECT c.id AS contrato_id, c.comercializadora,
            c.referencia_comercializadora, c.tarifa, c.vigente_desde,
            c.vigente_hasta, c.estado_fecha AS estado_fecha_contrato,
            f.id AS condicion_id, f.legacy_contract_id AS condicion_legacy,
            f.fecha_inicio_condiciones AS inicio_condicion,
            f.fecha_fin_condiciones AS fin_condicion, f.tipo_precio,
            l.payload_json
        FROM suministros s
        JOIN filas_contrato_origen f ON f.suministro_id = s.id
        LEFT JOIN contratos c ON c.id = f.contrato_id
        JOIN legacy_records l ON l.id = f.legacy_record_id
        WHERE s.cups20 = ?
        ORDER BY f.fecha_inicio_condiciones, f.id
    """
    with connect(db_path) as connection:
        condiciones = pd.read_sql_query(query, connection, params=(cups20,))
    if condiciones.empty:
        raise ValueError(f"No hay condiciones contractuales para el CUPS {cups20}.")
    condiciones["inicio_condicion"] = pd.to_datetime(
        condiciones["inicio_condicion"], errors="coerce"
    )
    condiciones["fin_condicion"] = pd.to_datetime(
        condiciones["fin_condicion"], errors="coerce"
    )
    if condiciones["inicio_condicion"].isna().any():
        raise ValueError("Hay condiciones sin fecha de inicio y no pueden aplicarse.")
    return condiciones


def cargar_costes_extra_cups(cups, db_path: str | Path = DEFAULT_DB_PATH):
    """Recupera los costes mensuales introducidos manualmente para un CUPS."""
    initialize_database(db_path)
    cups20 = re.sub(r"[^A-Z0-9]", "", str(cups or "").upper())[:20]
    query = """
        SELECT e.mes AS Mes, e.concepto AS Concepto,
            e.cantidad_factura_kwh AS Cantidad_kWh,
            e.precio_unitario_eur_kwh AS Precio_unitario_EUR_kWh,
            e.importe_eur AS Importe_EUR, e.referencia AS Referencia,
            e.observaciones AS Observaciones
        FROM costes_extra_contractuales e
        JOIN suministros s ON s.id = e.suministro_id
        WHERE s.cups20 = ?
        ORDER BY e.mes, e.concepto
    """
    with connect(db_path) as connection:
        return pd.read_sql_query(query, connection, params=(cups20,))


def condicion_como_referencia(condicion, inicio, fin, condicion_id=-1):
    """Extiende una condición existente al rango de una simulación.

    No modifica la base de datos ni la vigencia original: devuelve una única
    fila independiente para poder valorar el mismo consumo con esa referencia.
    """
    if isinstance(condicion, pd.Series):
        referencia = condicion.to_frame().T.copy()
    else:
        referencia = pd.DataFrame(condicion).copy()
    if len(referencia) != 1:
        raise ValueError("Debe seleccionarse una única condición de referencia.")
    referencia.loc[:, "inicio_condicion"] = pd.Timestamp(inicio).normalize()
    referencia.loc[:, "fin_condicion"] = pd.Timestamp(fin).normalize()
    referencia.loc[:, "condicion_id"] = int(condicion_id)
    return referencia


def condicion_manual_como_referencia(
    tipo_precio, inicio, fin, precios_fijos=None, formula=None,
):
    """Construye una condición temporal compatible con el motor contractual."""
    tipo = str(tipo_precio or "").strip().upper()
    payload = {}
    if tipo == "FIJO":
        precios_fijos = precios_fijos or {}
        for periodo in range(1, 7):
            # El payload contractual almacena el TE fijo en EUR/kWh.
            payload[f"TE P{periodo}"] = float(
                precios_fijos.get(f"P{periodo}", 0.0)
            )
    elif tipo == "INDEXADO":
        if formula is None:
            raise ValueError("Falta la fórmula indexada de referencia.")
        posiciones = {"perdidas": "1", "tm": "2", "neto": "3"}
        payload = {
            "INDEX DESVIOS": float(formula.desvios_apant),
            "INDEX CG": float(formula.margen),
            "CG F": posiciones[formula.margen_pos],
            "FNEE F": posiciones[formula.fnee_pos] if formula.incluir_fnee else "",
            "C FINAN %": float(formula.cf_pct),
        }
    else:
        raise ValueError("El tipo de referencia debe ser FIJO o INDEXADO.")
    return pd.DataFrame([{
        "condicion_id": -1,
        "inicio_condicion": pd.Timestamp(inicio).normalize(),
        "fin_condicion": pd.Timestamp(fin).normalize(),
        "tipo_precio": tipo,
        "payload_json": json.dumps(payload),
    }])


def guardar_costes_extra_cups(cups, filas, db_path: str | Path = DEFAULT_DB_PATH):
    """Valida y guarda todas las filas del formulario en una transaccion."""
    initialize_database(db_path)
    cups20 = re.sub(r"[^A-Z0-9]", "", str(cups or "").upper())[:20]
    datos = filas.copy()
    datos = datos.dropna(how="all")
    if datos.empty:
        raise ValueError("Introduzca al menos una regularizacion mensual.")
    datos["Mes"] = datos["Mes"].astype(str).str.strip()
    datos = datos[datos["Mes"].ne("") & datos["Mes"].ne("None")].copy()
    if not datos["Mes"].str.fullmatch(r"\d{4}-(0[1-9]|1[0-2])").all():
        raise ValueError("El mes debe escribirse como AAAA-MM, por ejemplo 2025-10.")
    datos["Concepto"] = (
        datos["Concepto"].fillna("REGULARIZACION SSAA").astype(str).str.strip()
    )
    datos.loc[datos["Concepto"].eq(""), "Concepto"] = "REGULARIZACION SSAA"
    for columna in ("Cantidad_kWh", "Precio_unitario_EUR_kWh", "Importe_EUR"):
        datos[columna] = pd.to_numeric(datos[columna], errors="coerce")
    if datos["Importe_EUR"].isna().any():
        raise ValueError("Todas las filas deben tener un importe en euros.")
    if datos.duplicated(["Mes", "Concepto"], keep=False).any():
        raise ValueError("No puede repetirse el mismo concepto dentro de un mes.")

    avisos = []
    comprobables = datos["Cantidad_kWh"].notna() & datos[
        "Precio_unitario_EUR_kWh"
    ].notna()
    diferencias = (
        datos.loc[comprobables, "Cantidad_kWh"]
        * datos.loc[comprobables, "Precio_unitario_EUR_kWh"]
        - datos.loc[comprobables, "Importe_EUR"]
    ).abs()
    for indice in diferencias[diferencias > 0.02].index:
        avisos.append(
            f"{datos.loc[indice, 'Mes']}: cantidad x precio difiere del importe "
            f"en {diferencias.loc[indice]:.2f} EUR."
        )

    with connect(db_path) as connection:
        suministro = connection.execute(
            "SELECT id FROM suministros WHERE cups20 = ?", (cups20,)
        ).fetchone()
        if suministro is None:
            raise ValueError(f"El CUPS {cups20} no existe en la base de datos.")
        for _, fila in datos.iterrows():
            connection.execute(
                """
                INSERT INTO costes_extra_contractuales(
                    suministro_id, mes, concepto, cantidad_factura_kwh,
                    precio_unitario_eur_kwh, importe_eur, referencia, observaciones
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(suministro_id, mes, concepto) DO UPDATE SET
                    cantidad_factura_kwh = excluded.cantidad_factura_kwh,
                    precio_unitario_eur_kwh = excluded.precio_unitario_eur_kwh,
                    importe_eur = excluded.importe_eur,
                    referencia = excluded.referencia,
                    observaciones = excluded.observaciones,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    int(suministro["id"]), fila["Mes"], fila["Concepto"],
                    fila["Cantidad_kWh"], fila["Precio_unitario_EUR_kWh"],
                    fila["Importe_EUR"], fila.get("Referencia"),
                    fila.get("Observaciones"),
                ),
            )
    return len(datos), avisos


def _formula_desde_payload(payload):
    posicion_margen = POSICIONES_LEGACY.get(str(payload.get("CG F", "2")), "tm")
    posicion_fnee = POSICIONES_LEGACY.get(str(payload.get("FNEE F", "")))
    return FormulaIndexada(
        desvios_apant=_numero_es(payload.get("INDEX DESVIOS")),
        margen=_numero_es(payload.get("INDEX CG")),
        margen_pos=posicion_margen,
        incluir_fnee=posicion_fnee is not None,
        fnee_pos=posicion_fnee or "perdidas",
        cf_pct=_numero_es(payload.get("C FINAN %")),
    )


def preparar_indexado_contractual(df_precios, condiciones, atr):
    """Aplica formulas contractuales sobre la serie de precios de Telemindex.

    Debe ejecutarse antes de cruzar precios y curva. Asi se conserva exactamente
    el tratamiento de calendario y cambio horario del flujo existente.
    """
    resultado = df_precios.copy()
    fechas = pd.to_datetime(resultado["fecha"], errors="coerce")
    resultado["precio_indexado_contrato_eur_mwh"] = np.nan
    resultado["formula_indexada_contrato"] = pd.NA
    for _, condicion in condiciones.iterrows():
        tipo = str(condicion["tipo_precio"] or "").strip().upper()
        if tipo.startswith("FIJO"):
            continue
        inicio = pd.Timestamp(condicion["inicio_condicion"]).normalize()
        fin = condicion["fin_condicion"]
        mascara = fechas >= inicio
        if pd.notna(fin):
            mascara &= fechas < pd.Timestamp(fin).normalize() + pd.Timedelta(days=1)
        if not mascara.any():
            continue
        formula = _formula_desde_payload(json.loads(condicion["payload_json"] or "{}"))
        calculado = calcular_precios_atr_formula(resultado.loc[mascara], formula)
        resultado.loc[mascara, "precio_indexado_contrato_eur_mwh"] = (
            calculado[f"precio_{atr}"].to_numpy()
        )
        resultado.loc[mascara, "formula_indexada_contrato"] = (
            f"Telemindex: CG={formula.margen:g} ({formula.margen_pos}), "
            f"desvios={formula.desvios_apant:g}, CF={formula.cf_pct:g}%"
        )
    return resultado


def aplicar_condiciones_contractuales(df_horario, condiciones, atr):
    """Calcula el coste horario fijo/indexado segun la condicion vigente.

    En fijo se conserva el precio TE puro. La regularizacion mensual de SSAA se
    incorporara despues como una capa adicional, sin reemplazar este valor.
    """
    if df_horario is None or df_horario.empty:
        raise ValueError("La curva horaria esta vacia.")
    atr = str(atr)
    if atr not in {"2.0", "3.0", "6.1"}:
        raise ValueError(f"ATR no soportado para el calculo contractual: {atr}.")
    resultado = df_horario.copy()
    fechas = pd.to_datetime(resultado["fecha_hora"], errors="coerce")
    if fechas.isna().any():
        raise ValueError("Hay intervalos sin fecha valida en la curva.")
    resultado["fecha_hora"] = fechas
    resultado["tipo_precio_contrato"] = pd.NA
    resultado["condicion_id"] = pd.NA
    resultado["condicion_desde"] = pd.NaT
    resultado["condicion_hasta"] = pd.NaT
    resultado["precio_fijo_te_eur_mwh"] = np.nan
    resultado["precio_contrato_eur_mwh"] = np.nan
    resultado["formula_contrato"] = pd.NA
    asignaciones = pd.Series(0, index=resultado.index, dtype="int64")
    consumo = pd.to_numeric(resultado["consumo_neto_kWh"], errors="coerce")
    if consumo.isna().any():
        raise ValueError("Hay intervalos con consumo vacio o no numerico.")

    for _, condicion in condiciones.iterrows():
        inicio = pd.Timestamp(condicion["inicio_condicion"]).normalize()
        fin = condicion["fin_condicion"]
        mascara = fechas >= inicio
        if pd.notna(fin):
            mascara &= fechas < pd.Timestamp(fin).normalize() + pd.Timedelta(days=1)
        if not mascara.any():
            continue
        asignaciones.loc[mascara] += 1
        tipo = str(condicion["tipo_precio"] or "").strip().upper()
        payload = json.loads(condicion["payload_json"] or "{}")
        resultado.loc[mascara, "tipo_precio_contrato"] = (
            "FIJO" if tipo.startswith("FIJO") else "INDEXADO"
        )
        resultado.loc[mascara, "condicion_id"] = int(condicion["condicion_id"])
        resultado.loc[mascara, "condicion_desde"] = inicio
        resultado.loc[mascara, "condicion_hasta"] = (
            pd.Timestamp(fin) if pd.notna(fin) else pd.NaT
        )

        if tipo.startswith("FIJO"):
            periodos = resultado.loc[mascara, "periodo"].astype(str).str.upper()
            precios = periodos.map({
                f"P{i}": _numero_es(payload.get(f"TE P{i}"), np.nan) * 1000
                for i in range(1, 7)
            })
            resultado.loc[mascara, "precio_fijo_te_eur_mwh"] = precios.to_numpy()
            resultado.loc[mascara, "precio_contrato_eur_mwh"] = precios.to_numpy()
            resultado.loc[mascara, "formula_contrato"] = (
                "TE fijo por periodo (sin regularizacion SSAA)"
            )
        else:
            if "precio_indexado_contrato_eur_mwh" not in resultado:
                raise ValueError(
                    "Los precios indexados contractuales deben prepararse antes "
                    "de cruzar la curva, mediante el flujo de Telemindex."
                )
            resultado.loc[mascara, "precio_contrato_eur_mwh"] = resultado.loc[
                mascara, "precio_indexado_contrato_eur_mwh"
            ]
            formula_preparada = resultado.get("formula_indexada_contrato")
            if formula_preparada is not None:
                resultado.loc[mascara, "formula_contrato"] = formula_preparada.loc[
                    mascara
                ]
            else:
                resultado.loc[mascara, "formula_contrato"] = (
                    "Formula contractual calculada por Telemindex"
                )

    if (asignaciones > 1).any():
        raise ValueError(
            f"Hay {int((asignaciones > 1).sum())} intervalos con condiciones "
            "solapadas; corrija la vigencia en la base de datos."
        )
    resultado["estado_cobertura_contrato"] = np.where(
        asignaciones.eq(0), "SIN CONDICION", "CUBIERTO"
    )
    resultado["coste_total"] = (
        resultado["precio_contrato_eur_mwh"] * consumo / 1000
    )
    resultado.loc[consumo.eq(0), "coste_total"] = 0.0
    sin_cobertura = asignaciones.eq(0)
    if sin_cobertura.any():
        ejemplos = fechas.loc[sin_cobertura].dt.strftime("%d/%m/%Y %H:%M").head(3)
        raise ValueError(
            f"No hay condicion contractual para {int(sin_cobertura.sum())} "
            f"intervalos; primeros: {', '.join(ejemplos)}."
        )
    resultado["estado_precio_horario"] = np.where(
        resultado["precio_contrato_eur_mwh"].isna(),
        "SIN INTERVALO DE MERCADO",
        "CALCULADO",
    )
    return resultado


def aplicar_costes_extra_mensuales(
    df_horario, costes_extra, consumos_mensuales_base=None,
):
    """Suma importes mensuales repartiendolos por consumo para conservar totales."""
    resultado = df_horario.copy()
    resultado["coste_total_inicial"] = resultado["coste_total"]
    resultado["coste_extra_mensual_asignado"] = 0.0
    resultado["estado_coste_contractual"] = np.where(
        resultado["tipo_precio_contrato"].eq("FIJO"),
        "PROVISIONAL SIN EXTRAS",
        "DEFINITIVO",
    )
    if costes_extra is None or costes_extra.empty:
        return resultado
    resultado["_mes_extra"] = (
        pd.to_datetime(resultado["fecha_hora"]).dt.to_period("M").astype(str)
    )
    extras_mes = costes_extra.groupby("Mes", as_index=False)["Importe_EUR"].sum()
    consumo = pd.to_numeric(resultado["consumo_neto_kWh"], errors="coerce").fillna(0)
    consumos_base = consumos_mensuales_base or {}
    for _, extra in extras_mes.iterrows():
        mascara = resultado["_mes_extra"].eq(str(extra["Mes"]))
        consumo_mes = float(
            consumos_base.get(str(extra["Mes"]), consumo.loc[mascara].sum())
        )
        if not mascara.any() or consumo_mes == 0:
            continue
        resultado.loc[mascara, "coste_extra_mensual_asignado"] = (
            consumo.loc[mascara] / consumo_mes * float(extra["Importe_EUR"])
        )
        resultado.loc[mascara, "estado_coste_contractual"] = "DEFINITIVO CON EXTRAS"
    resultado["coste_total"] = (
        resultado["coste_total_inicial"]
        + resultado["coste_extra_mensual_asignado"]
    )
    return resultado.drop(columns="_mes_extra")


def resumir_calculo_contractual(df):
    """Resume por mes y condicion los importes que alimentan los graficos."""
    detalle = df.copy()
    if "coste_total_inicial" not in detalle:
        detalle["coste_total_inicial"] = detalle["coste_total"]
    if "coste_extra_mensual_asignado" not in detalle:
        detalle["coste_extra_mensual_asignado"] = 0.0
    detalle["Mes"] = pd.to_datetime(detalle["fecha_hora"]).dt.to_period("M").astype(str)
    resumen = (
        detalle.groupby(
            [
                "Mes", "tipo_precio_contrato", "condicion_id",
                "condicion_desde", "condicion_hasta",
            ],
            dropna=False,
            as_index=False,
        )
        .agg(
            Consumo_kWh=("consumo_neto_kWh", "sum"),
            Coste_inicial_eur=("coste_total_inicial", "sum"),
            Costes_extra_eur=("coste_extra_mensual_asignado", "sum"),
            Coste_energia_eur=("coste_total", "sum"),
            Intervalos=("fecha_hora", "size"),
        )
    )
    resumen["Precio_medio_cents_kWh"] = np.where(
        resumen["Consumo_kWh"] != 0,
        resumen["Coste_energia_eur"] / resumen["Consumo_kWh"] * 100,
        np.nan,
    )
    resumen["Precio_medio_inicial_cents_kWh"] = np.where(
        resumen["Consumo_kWh"] != 0,
        resumen["Coste_inicial_eur"] / resumen["Consumo_kWh"] * 100,
        np.nan,
    )
    return resumen.sort_values(
        ["Mes", "condicion_desde", "condicion_hasta", "condicion_id"],
        na_position="last",
    ).reset_index(drop=True)
