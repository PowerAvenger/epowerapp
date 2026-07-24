import hashlib

import base64
import re

from html import escape
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from jinja2 import Environment, FileSystemLoader

from backend_comun import aplicar_estilo
from backend_factura import (
    FacturaError,
    FormatoNoReconocido,
    analizar_factura,
    componentes_grafico,
    componentes_peso_grafico,
    es_servicio_adicional,
    estado_otro_segun_factura,
    extraer_texto_pdf,
    generar_resumen,
    importes_coinciden,
)
from formato_es import (
    formato_eur_kwh,
    formato_eur_mwh,
    formato_euros,
    formato_kwh,
    formato_pct,
    formatear_columnas_tabla,
)
from utilidades import (
    actualizar_df_index_por_zona,
    generar_menu,
    init_app,
    init_app_index,
    mostrar_parametros_formula_indexado,
    persist_widget,
)
from regulacion_reactiva import (
    FUENTE_REACTIVA,
    LIMITE_REACTIVA_SOBRE_ACTIVA,
    tramos_reactiva,
)
from regulacion_iee import obtener_referencia_iee


generar_menu()

if not st.session_state.get("usuario_autenticado", False) and not st.session_state.get("usuario_free", False):
    st.switch_page("epowerapp.py")

with st.sidebar:
    st.header("🧾 Análisis de factura eléctrica")
    st.caption(
        "Lectura local, sin IA y sin consultas externas. "
        "No se guardarán ni compartirán datos sensibles de factura. "
        "No es necesario anonimizar."
    )


VERSION_LECTOR = 115
MOSTRAR_TABLA_MAXIMETROS = False

with st.sidebar:
    st.caption(f"Motor de lectura · v{VERSION_LECTOR}")


@st.cache_data(show_spinner=False)
def procesar_pdf(contenido: bytes, version_lector: int):
    return extraer_texto_pdf(contenido)


def limpiar_factura_sesion():
    """Retira de memoria el PDF y el widget asociado."""
    for clave in (
        "factura_pdf_bytes",
        "factura_pdf_nombre",
        "factura_uploader",
        "factura_comparativa_indexado",
    ):
        st.session_state.pop(clave, None)


def _atr_indexado(atr_factura):
    """Traduce el ATR leído al nombre de columna usado por Telemindex."""

    atr = (atr_factura or "").replace(" ", "").upper()
    for candidato in ("2.0", "3.0", "6.1"):
        if atr.startswith(candidato):
            return candidato
    return None


def _fecha_factura(valor):
    fecha = pd.to_datetime(valor, dayfirst=True, errors="coerce")
    return None if pd.isna(fecha) else fecha.date()


def _buscar_dato_informe(texto, patrones):
    for patron in patrones:
        coincidencia = re.search(patron, texto, re.IGNORECASE | re.MULTILINE)
        if coincidencia:
            partes = [
                re.sub(r"\s+", " ", parte).strip(" ,-")
                for parte in coincidencia.groups()
                if parte and parte.strip()
            ]
            if partes:
                return ", ".join(partes)
    return ""


def _renderizar_plantilla_informe(contexto, ruta_plantilla):
    ruta = Path(ruta_plantilla)
    if not ruta.is_absolute():
        ruta = Path(__file__).resolve().parent.parent / ruta
    entorno = Environment(loader=FileSystemLoader(str(ruta.parent)))
    return entorno.get_template(ruta.name).render(**contexto)


def _datos_informe_desde_factura(factura, texto):
    """Prepara datos editables sin convertirlos en campos fiscales verificados."""
    cliente = _buscar_dato_informe(texto, [
        r"^Titular\s*:?\s*([^\n]+)$",
        r"^(?:Nombre|Raz[oó]n\s+social)\s*:?\s*([^\n]+)$",
        r"^Cliente\s*:?\s*([^\n]+)$",
    ])
    nif = _buscar_dato_informe(texto, [
        r"^(?:DNI/NIF/NIE|NIF|CIF)\s*:?\s*([A-Z0-9-]+)",
    ])
    direccion = _buscar_dato_informe(texto, [
        r"^Direcci.n\s*:?\s*([^\n]+)\n(\d{5}[^\n]*)$",
        r"^Direcci.n\s*:?\s*([^\n]+)$",
        r"^Direcci.n\s+de\s+suministro\s*:?\s*([^\n]+)$",
    ])
    ciclo = " – ".join(
        valor for valor in (factura.periodo_inicio, factura.periodo_fin) if valor
    )
    return {
        "factura_informe_cliente": cliente,
        "factura_informe_nif": nif,
        "factura_informe_direccion": direccion,
        "factura_informe_cups": factura.cups or "",
        "factura_informe_numero": factura.numero_factura or "",
        "factura_informe_fecha": factura.fecha_factura or "",
        "factura_informe_ciclo": ciclo,
        "factura_informe_comercializadora": factura.comercializadora or "",
        "factura_informe_atr": factura.atr or "",
        "factura_informe_realizado_por": "",
        "factura_informe_fecha_realizacion": (
            pd.Timestamp.today().strftime("%d/%m/%Y")
        ),
        "factura_informe_objeto": (
            "Mejorar las condiciones de contratación del suministro eléctrico "
            "conforme a la propuesta presentada."
        ),
    }


def _firma_formula_indexado():
    return (
        "ponderacion_periodos_v2",
        st.session_state.get("desvios_apant", 1.0),
        st.session_state.get("margen_telemindex", 5.0),
        st.session_state.get("cfg_margen_pos", "tm"),
        st.session_state.get("cfg_fnee", True),
        st.session_state.get("cfg_fnee_pos", "perdidas"),
        st.session_state.get("cf_pct", 0.0),
        st.session_state.get("zona_periodos_index", "peninsula"),
    )


def _firma_propuesta_energia(atr):
    modo = st.session_state.get("factura_tipo_energia", "Indexado")
    if modo == "Fijo":
        numero_periodos = 3 if atr == "2.0" else 6
        return (
            "energia_fija_v1",
            modo,
            *(
                st.session_state.get(f"factura_precio_fijo_p{i}", 0.0)
                for i in range(1, numero_periodos + 1)
            ),
        )
    return ("energia_indexada_v1", modo, *_firma_formula_indexado())


def _consumos_factura_por_periodo(factura):
    consumos = {}
    periodos_sin_identificar = []
    for item in factura.energia_periodos:
        if item.consumo_kwh <= 0:
            continue
        periodo = str(item.periodo or "").strip().upper()
        if not re.fullmatch(r"P[1-6]", periodo):
            periodos_sin_identificar.append(str(item.periodo or "Sin periodo"))
            continue
        consumos[periodo] = consumos.get(periodo, 0.0) + item.consumo_kwh

    if periodos_sin_identificar:
        raise ValueError(
            "La factura contiene consumo sin periodos P1…P6 identificables: "
            + ", ".join(periodos_sin_identificar)
            + ". No se aplicará una ponderación aproximada."
        )
    if not consumos:
        raise ValueError("No hay consumos por periodo utilizables para ponderar.")
    return consumos


def _crear_resultado_energia(factura, atr, inicio, fin, consumos, precios, tipo):
    filas = []
    for periodo, consumo in sorted(consumos.items()):
        precio = precios.get(periodo)
        if precio is None or pd.isna(precio) or precio <= 0:
            raise ValueError(f"No hay un precio válido disponible para {periodo}.")
        filas.append(
            {
                "Periodo": periodo,
                "Consumo (kWh)": consumo,
                "Precio propuesta (€/kWh)": precio,
                "Coste propuesta (€)": consumo * precio,
            }
        )

    detalle = pd.DataFrame(filas)
    consumo_total = detalle["Consumo (kWh)"].sum()
    detalle["Peso consumo (%)"] = (
        detalle["Consumo (kWh)"] / consumo_total * 100
    )
    detalle["Precio ponderado (€/kWh)"] = (
        detalle["Coste propuesta (€)"] / consumo_total
    )
    coste_propuesta = detalle["Coste propuesta (€)"].sum()
    coste_facturado = sum(item.coste_eur for item in factura.energia_periodos)

    return {
        "tipo": tipo,
        "atr": atr,
        "inicio": inicio,
        "fin": fin,
        "detalle": detalle,
        "consumo_total": consumo_total,
        "coste_facturado": coste_facturado,
        "coste_indexado": coste_propuesta,
        "precio_facturado": coste_facturado / consumo_total,
        "precio_indexado": coste_propuesta / consumo_total,
        "diferencia": coste_propuesta - coste_facturado,
    }


def _calcular_comparativa_indexado(factura):
    atr = _atr_indexado(factura.atr)
    if atr is None:
        raise ValueError(
            f"El peaje {factura.atr or 'no detectado'} no está disponible en Telemindex."
        )

    inicio = _fecha_factura(factura.periodo_inicio)
    fin = _fecha_factura(factura.periodo_fin)
    if inicio is None or fin is None or inicio > fin:
        raise ValueError("No se ha podido obtener un periodo de facturación válido.")

    consumos = _consumos_factura_por_periodo(factura)

    init_app()
    init_app_index()
    actualizar_df_index_por_zona(forzar=True)
    df_index = st.session_state.df_sheets
    fechas = pd.to_datetime(df_index["fecha"], errors="coerce").dt.date
    df_periodo = df_index.loc[(fechas >= inicio) & (fechas <= fin)].copy()

    if df_periodo.empty:
        raise ValueError("No hay datos de indexado para el periodo de la factura.")
    fecha_min = pd.to_datetime(df_periodo["fecha"]).dt.date.min()
    fecha_max = pd.to_datetime(df_periodo["fecha"]).dt.date.max()
    fechas_disponibles = set(pd.to_datetime(df_periodo["fecha"]).dt.date.unique())
    fechas_esperadas = set(pd.date_range(inicio, fin, freq="D").date)
    if (
        fecha_min != inicio
        or fecha_max != fin
        or fechas_esperadas.difference(fechas_disponibles)
    ):
        raise ValueError(
            "Telemindex no dispone todavía del periodo completo: "
            f"{inicio:%d/%m/%Y}–{fin:%d/%m/%Y}."
        )

    columna_periodo = "dh_3p" if atr == "2.0" else "dh_6p"
    columna_precio = f"precio_{atr}"
    precios = (
        df_periodo.assign(
            _periodo=df_periodo[columna_periodo].astype(str).str.extract(r"(\d+)")[0]
        )
        .assign(_periodo=lambda df: "P" + df["_periodo"])
        .groupby("_periodo", observed=False)[columna_precio]
        .mean()
        .div(1000)
    )

    return _crear_resultado_energia(
        factura, atr, inicio, fin, consumos, precios, "Indexado"
    )


def _calcular_comparativa_fijo(factura):
    atr = _atr_indexado(factura.atr)
    if atr is None:
        raise ValueError(
            f"El peaje {factura.atr or 'no detectado'} no admite esta comparativa."
        )
    consumos = _consumos_factura_por_periodo(factura)
    numero_periodos = 3 if atr == "2.0" else 6
    precios = {
        f"P{i}": st.session_state.get(f"factura_precio_fijo_p{i}", 0.0)
        for i in range(1, numero_periodos + 1)
    }
    if any(precio <= 0 for precio in precios.values()):
        raise ValueError(
            f"Introduce un precio fijo mayor que cero en los {numero_periodos} periodos."
        )
    return _crear_resultado_energia(
        factura,
        atr,
        _fecha_factura(factura.periodo_inicio),
        _fecha_factura(factura.periodo_fin),
        consumos,
        precios,
        "Fijo",
    )


def _coste_potencia_propuesta(factura):
    modo = st.session_state.get(
        "factura_modo_precio_potencia", "Aplicar precios BOE"
    )
    if modo == "Mantener precios de factura":
        return factura.potencia
    if not factura.potencia_periodos or any(
        item.coste_boe_eur <= 0 for item in factura.potencia_periodos
    ):
        return None

    coste_boe = sum(item.coste_boe_eur for item in factura.potencia_periodos)
    if modo == "Aplicar precios BOE":
        return round(coste_boe, 2)

    margen_anual = st.session_state.get(
        "factura_margen_potencia_personalizado", 0.0
    )
    coste_margen = sum(
        item.potencia_kw * item.dias * margen_anual / 365
        for item in factura.potencia_periodos
    )
    return round(coste_boe + coste_margen, 2)


def _margen_potencia_propuesta(factura):
    if (
        st.session_state.get(
            "factura_modo_precio_potencia", "Aplicar precios BOE"
        )
        != "Personalizar con margen"
    ):
        return 0.0
    margen_anual = st.session_state.get(
        "factura_margen_potencia_personalizado", 0.0
    )
    return sum(
        item.potencia_kw * item.dias * margen_anual / 365
        for item in factura.potencia_periodos
    )


def _parametros_iee_propuesta(factura):
    """Obtiene una base de IEE contrastada, aunque no venga desglosada."""
    if factura.verificacion_iee:
        verificacion = factura.verificacion_iee
        return (
            verificacion.base_eur,
            verificacion.tipo_pct,
            verificacion.minimo_eur_mwh,
        )

    fecha = _fecha_factura(factura.periodo_fin or factura.fecha_factura)
    referencia = (
        obtener_referencia_iee(fecha, factura.atr) if fecha else None
    )
    if not referencia or not factura.iee:
        return None

    bases_candidatas = []
    if factura.verificacion_iva:
        bases_candidatas.append(
            factura.verificacion_iva.base_eur - factura.iee
        )
    bases_candidatas.append(
        factura.suma_componentes - factura.iee - factura.iva
    )
    minimo_iee = (
        factura.consumo_total_kwh
        / 1000
        * referencia.minimo_eur_mwh
    )
    for base_iee in bases_candidatas:
        if base_iee <= 0:
            continue
        importe_reconstruido = round(max(
            base_iee * referencia.tipo_pct / 100,
            minimo_iee,
        ), 2)
        if importes_coinciden(
            factura.iee, importe_reconstruido, "componentes"
        ):
            return (
                base_iee,
                referencia.tipo_pct,
                referencia.minimo_eur_mwh,
            )
    return None


def _componentes_propuesta(factura, resultado_energia):
    potencia_propuesta = _coste_potencia_propuesta(factura)
    energia_propuesta = resultado_energia["coste_indexado"]
    if potencia_propuesta is None:
        diferencia_base = None
    else:
        diferencia_base = (
            potencia_propuesta
            - factura.potencia
            + energia_propuesta
            - factura.energia
        )

    iee_propuesta = None
    parametros_iee = _parametros_iee_propuesta(factura)
    if diferencia_base is not None and parametros_iee:
        base_factura_iee, tipo_iee, minimo_eur_mwh = parametros_iee
        base_iee = max(base_factura_iee + diferencia_base, 0.0)
        iee_propuesta = base_iee * tipo_iee / 100
        if minimo_eur_mwh is not None:
            minimo_iee = (
                factura.consumo_total_kwh
                / 1000
                * minimo_eur_mwh
            )
            iee_propuesta = max(iee_propuesta, minimo_iee)
        iee_propuesta = round(iee_propuesta, 2)

    iva_propuesta = None
    verificacion_iva = factura.verificacion_iva
    if diferencia_base is not None and verificacion_iva:
        variacion_iee = (
            iee_propuesta - factura.iee
            if iee_propuesta is not None
            else 0.0
        )
        base_iva = max(
            verificacion_iva.base_eur + diferencia_base + variacion_iee,
            0.0,
        )
        iva_propuesta = round(
            base_iva * verificacion_iva.tipo_pct / 100, 2
        )

    valores_propuesta = {
        "Potencia": (
            potencia_propuesta
            if potencia_propuesta is not None
            else factura.potencia
        ),
        "Energía": energia_propuesta,
        "Excesos": factura.excesos_potencia,
        "Reactiva": factura.reactiva,
        "Otros": factura.total_otros,
        "IEE": iee_propuesta if iee_propuesta is not None else factura.iee,
        "IVA": iva_propuesta if iva_propuesta is not None else factura.iva,
    }
    comparativa = pd.DataFrame(
        [
            {
                "Componente": item["Componente"],
                "Factura (€)": item["Importe (€)"],
                "Propuesta (€)": valores_propuesta.get(
                    item["Componente"], item["Importe (€)"]
                ),
            }
            for item in componentes_grafico(factura)
        ]
    )
    comparativa["Diferencia (€)"] = (
        comparativa["Propuesta (€)"] - comparativa["Factura (€)"]
    )
    comparativa["Diferencia (%)"] = comparativa.apply(
        lambda fila: (
            fila["Diferencia (€)"] / fila["Factura (€)"] * 100
            if fila["Factura (€)"]
            else None
        ),
        axis=1,
    )
    return comparativa


tab_analisis, tab_comparativa, tab_informe = st.tabs(
    ["Análisis", "Propuesta", "Informe"]
)

with tab_analisis:
    col_entrada, col_detalle, col_grafico = st.columns([0.26, 0.30, 0.44])

factura = None
huella = None
resultado = None
figura_componentes = None

with col_entrada:
    st.subheader("Suelta aquí tu factura", divider="rainbow")
    archivo = st.file_uploader(
        "Arrastra una factura PDF",
        type=["pdf"],
        accept_multiple_files=False,
        key="factura_uploader",
    )
    if archivo is not None:
        st.session_state.factura_pdf_bytes = archivo.getvalue()
        st.session_state.factura_pdf_nombre = archivo.name

    contenido = st.session_state.get("factura_pdf_bytes")
    if contenido is not None:
        nombre_factura = st.session_state.get("factura_pdf_nombre", "Factura PDF")
        st.caption(f"En memoria durante esta sesión: {nombre_factura}")
        st.button(
            "Quitar factura",
            on_click=limpiar_factura_sesion,
            use_container_width=True,
        )
        st.subheader("Resumen", divider="rainbow")

if contenido is not None:
    huella = hashlib.sha256(contenido).hexdigest()

    try:
        texto, numero_paginas = procesar_pdf(contenido, VERSION_LECTOR)
        factura = analizar_factura(texto)
    except FormatoNoReconocido as exc:
        with col_entrada:
            st.warning(str(exc))
            st.info(
                "El PDF se ha podido leer, pero no hay un extractor para este formato. "
                "El texto sirve para preparar un nuevo patrón sin usar IA."
            )
        with col_detalle:
            with st.expander("Ver texto extraído para diagnóstico"):
                st.text(texto)
    except FacturaError as exc:
        with col_entrada:
            st.error(str(exc))
    except Exception as exc:
        with col_entrada:
            st.error(f"No se ha podido completar la lectura: {exc}")
    else:
        reconstruccion_total_completa = factura.reconstruccion_total_completa
        verificacion_total_ok = reconstruccion_total_completa and importes_coinciden(
            factura.total,
            factura.total_calculado_segun_factura,
            "total_factura",
        )
        cups_mostrado = (
            f"{factura.cups[:6]}…{factura.cups[-4:]}"
            if factura.cups and len(factura.cups) > 12
            else factura.cups or "No detectado"
        )

        with col_entrada:
            st.success(
                f"Formato: {factura.comercializadora} · {numero_paginas} página(s)"
            )
            st.info(generar_resumen(factura))
            st.caption(
                "🛠️ Uso interno · Control de extracción: "
                f"componentes {formato_euros(factura.suma_componentes)} · "
                f"diferencia con total PDF {formato_euros(factura.diferencia)}."
            )
            potencia_verificada = any(
                item.resultado != "No verificado"
                for item in factura.potencia_periodos
            )
            if factura.sobrecoste_potencia > 0:
                st.warning(
                    "⚠️ Sobrecoste en el término de potencia: "
                    f"{formato_euros(factura.sobrecoste_potencia)} "
                    f"({formato_pct(factura.porcentaje_sobrecoste_potencia, 1)} "
                    "del término facturado)."
                )
            elif potencia_verificada:
                st.success("✅ Término de potencia sin sobrecoste sobre BOE.")
            else:
                st.info("ℹ️ Término de potencia no verificable con los datos extraídos.")

            if factura.excesos_potencia:
                st.warning(
                    "⚠️ La factura incluye excesos de potencia: "
                    f"{formato_euros(factura.excesos_potencia)}."
                )
            else:
                st.info("ℹ️ La factura no incluye excesos de potencia.")

            if factura.reactiva:
                st.error(
                    "🔴 La factura incluye penalización por energía reactiva: "
                    f"{formato_euros(factura.reactiva)}."
                )
            else:
                st.success(
                    "✅ La factura no incluye penalización por energía reactiva."
                )

            servicios_adicionales = [
                item for item in factura.otros
                if es_servicio_adicional(item)
            ]
            if servicios_adicionales:
                total_servicios = round(sum(
                    item.importe for item in servicios_adicionales
                ), 2)
                st.error(
                    "🔴 Servicios adicionales contratados: "
                    + ", ".join(item.concepto for item in servicios_adicionales)
                    + ". Importe antes de impuestos: "
                    + formato_euros(total_servicios)
                    + ". Conviene revisar si siguen siendo necesarios."
                )

            factura_alquiler_medida = any(
                "alquiler" in item.concepto.lower()
                for item in factura.otros
            )
            if not factura_alquiler_medida:
                st.info(
                    "ℹ️ No se ha detectado alquiler de equipos de medida en la factura. "
                    "La telemedida puede facturarse por otra vía."
                )

            if factura.fecha_vencimiento_contrato:
                vencimiento_fecha = pd.to_datetime(
                    factura.fecha_vencimiento_contrato,
                    format="%d/%m/%Y",
                    errors="coerce",
                )
                if not pd.isna(vencimiento_fecha):
                    hoy = pd.Timestamp.today().normalize()
                    limite_aviso = hoy + pd.DateOffset(months=2)
                    if vencimiento_fecha < hoy:
                        dias_caducado = (hoy - vencimiento_fecha).days
                        st.markdown(
                            "<div style='background:#6f1d2c;color:#fff;"
                            "border-left:5px solid #3f0d18;border-radius:8px;"
                            "padding:12px 14px;margin:8px 0;'>"
                            "⛔ <b>Contrato vencido:</b> finalizó el "
                            f"{escape(factura.fecha_vencimiento_contrato)} "
                            f"(hace {dias_caducado} días)."
                            "</div>",
                            unsafe_allow_html=True,
                        )
                    elif vencimiento_fecha <= limite_aviso:
                        dias_restantes = (vencimiento_fecha - hoy).days
                        st.warning(
                            "⚠️ Vencimiento contractual próximo: "
                            f"{factura.fecha_vencimiento_contrato} "
                            f"({dias_restantes} días restantes)."
                        )

            col_total_factura, col_resultado_factura = st.columns(2)
            col_total_factura.metric("Total factura", formato_euros(factura.total))
            if reconstruccion_total_completa:
                col_resultado_factura.metric(
                    "Resultado verificación",
                    "✅" if verificacion_total_ok else "❌",
                )
            else:
                col_resultado_factura.metric("Resultado verificación", "?")

            factura_numero = escape(str(factura.numero_factura or "No detectada"))
            fecha_factura = escape(str(factura.fecha_factura or "No detectada"))
            vencimiento = escape(
                str(factura.fecha_vencimiento_contrato or "No detectado")
            )
            periodo_inicio = escape(str(factura.periodo_inicio or "?"))
            periodo_fin = escape(str(factura.periodo_fin or "?"))
            cups_html = escape(str(cups_mostrado))
            atr_html = escape(str(factura.atr or "No detectado"))
            suministro_html = escape(
                str(factura.tipo_suministro or "No detectado")
            )
            col_total_factura.markdown(
                f"""
                <div style="background:rgba(236,72,153,.10); border-left:4px solid #ec4899;
                            border-radius:8px; padding:12px 14px; margin:8px 0;
                            height:190px; box-sizing:border-box;">
                    <div style="color:#db2777; font-size:1.45rem; font-weight:700;
                                margin-bottom:7px;">Datos del contrato</div>
                    <div style="font-size:1.02rem; line-height:1.65;">
                        <b>Factura:</b> {factura_numero}<br>
                        <b>Fecha de factura:</b> {fecha_factura}<br>
                        <b>Vencimiento:</b> {vencimiento}<br>
                        <b>Periodo:</b> {periodo_inicio} - {periodo_fin}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            col_resultado_factura.markdown(
                f"""
                <div style="background:rgba(249,115,22,.11); border-left:4px solid #f97316;
                            border-radius:8px; padding:12px 14px; margin:8px 0;
                            height:190px; box-sizing:border-box;">
                    <div style="color:#ea580c; font-size:1.45rem; font-weight:700;
                                margin-bottom:7px;">Datos del suministro</div>
                    <div style="font-size:1.02rem; line-height:1.65;">
                        <b>CUPS:</b> {cups_html}<br>
                        <b>ATR/Peaje:</b> {atr_html}<br>
                        <b>Tipo de suministro:</b> {suministro_html}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if not reconstruccion_total_completa:
                col_resultado_factura.markdown(
                    "<style>"
                    ":is([data-testid='column'],[data-testid='stColumn']):has("
                    ".metric-no-verificable-marker) "
                    "[data-testid='stMetricValue'],"
                    ":is([data-testid='column'],[data-testid='stColumn']):has("
                    ".metric-no-verificable-marker) "
                    "[data-testid='stMetricValue'] * "
                    "{color:#f59e0b !important;}"
                    "</style>"
                    "<span class='metric-no-verificable-marker' "
                    "style='display:none'></span>",
                    unsafe_allow_html=True,
                )
        componentes = componentes_grafico(factura, texto)
        df_componentes = pd.DataFrame(componentes)
        semaforos_reales = {
            item["Componente"]: item["Verificación real"]
            for item in componentes
        }
        semaforos_factura = {
            item["Componente"]: item["Verif s/cálculo"]
            for item in componentes
        }

        def etiqueta_expander(componente, texto_etiqueta):
            return f"{semaforos_factura.get(componente, '🔵')} {texto_etiqueta}"

        with col_detalle:
            if not df_componentes.empty:
                st.subheader(
                    "Comprobación cálculo coste factura",
                    divider="rainbow",
                    help=(
                        "El análisis se realiza sobre los datos contenidos en la "
                        "factura, incluyendo la comprobación de los componentes "
                        "regulados y normativos aplicables."
                    ),
                )
                if reconstruccion_total_completa:
                    resultado_texto = (
                        "CORRECTO" if verificacion_total_ok else "INCORRECTO"
                    )
                    resultado_icono = "✓" if verificacion_total_ok else "✕"
                    resultado_color = (
                        "#00c853" if verificacion_total_ok else "#ef4444"
                    )
                    resultado_fondo = (
                        "rgba(0,200,83,.12)"
                        if verificacion_total_ok else "rgba(239,68,68,.12)"
                    )
                    resultado_borde = (
                        "rgba(0,200,83,.55)"
                        if verificacion_total_ok else "rgba(239,68,68,.55)"
                    )
                else:
                    resultado_texto = "NO VERIFICABLE"
                    resultado_icono = "?"
                    resultado_color = "#f59e0b"
                    resultado_fondo = "rgba(100,116,139,.12)"
                    resultado_borde = "rgba(100,116,139,.5)"
                st.markdown(
                    "<div style='display:flex;align-items:center;justify-content:"
                    "space-between;gap:1rem;flex-wrap:wrap;margin:1rem 0 .8rem 0;"
                    f"padding:.8rem 1rem;border:1px solid {resultado_borde};"
                    f"border-radius:1rem;background:{resultado_fondo};"
                    "box-shadow:0 4px 14px rgba(0,0,0,.10);'>"
                    "<div style='display:flex;align-items:baseline;flex-wrap:wrap;"
                    "font-size:1.55rem;font-weight:700;line-height:1.2;'>"
                    "<span style='font-size:1.35rem;'>El resultado de la "
                    "verificación es:</span>"
                    f"<span style='color:{resultado_color};font-size:1.9rem;"
                    "margin-left:.8rem;'>"
                    f"{resultado_texto}</span></div>"
                    "<div style='display:flex;align-items:center;justify-content:center;"
                    "width:3.7rem;height:3.7rem;flex:0 0 3.7rem;"
                    "background:transparent;font-size:2.8rem;"
                    f"line-height:1;color:{resultado_color};font-weight:800;'>"
                    f"{resultado_icono}</div></div>",
                    unsafe_allow_html=True,
                )
                if not reconstruccion_total_completa:
                    if abs(factura.total - factura.suma_componentes) <= 0.05:
                        st.success(
                            "🧮 La suma aritmética de los componentes extraídos "
                            "coincide con el total de la factura: "
                            f"{formato_euros(factura.total)}."
                        )
                    motivos_no_verificable = []
                    if not importes_coinciden(
                        factura.total, factura.suma_componentes, "total_factura"
                    ):
                        motivos_no_verificable.append(
                            "los componentes extraídos no reconstruyen el total"
                        )
                    if factura.potencia and (
                        not factura.potencia_periodos
                        or any(
                            item.resultado == "No verificado"
                            for item in factura.potencia_periodos
                        )
                    ):
                        motivos_no_verificable.append(
                            "el término de potencia no tiene detalle verificable"
                        )
                    if factura.energia and not factura.energia_periodos:
                        motivos_no_verificable.append(
                            "el término de energía no tiene detalle verificable"
                        )
                    if factura.excesos_potencia and not factura.excesos_verificados:
                        motivos_no_verificable.append(
                            factura.verificacion_excesos
                            or "los excesos no tienen detalle verificable"
                        )
                    if factura.reactiva and not factura.reactiva_periodos:
                        motivos_no_verificable.append(
                            "la reactiva no tiene detalle por periodos"
                        )
                    if factura.iee and (
                        not factura.verificacion_iee
                        or factura.verificacion_iee.importe_regulado_eur is None
                    ):
                        motivos_no_verificable.append(
                            "el IEE no dispone de referencia regulatoria"
                        )
                    if factura.iva and (
                        not factura.verificacion_iva
                        or factura.verificacion_iva.importe_regulado_eur is None
                    ):
                        motivos_no_verificable.append(
                            "el IVA no dispone de referencia regulatoria"
                        )
                    detalle_no_verificable = "; ".join(motivos_no_verificable)
                    st.info(
                        "ℹ️ No se puede completar la verificación: "
                        + (detalle_no_verificable or
                           "faltan datos suficientes en la factura")
                        + "."
                    )
                estados_otros = [
                    (item, estado_otro_segun_factura(factura, texto, item))
                    for item in factura.otros
                ]
                otros_pendientes = [
                    item.concepto for item, estado in estados_otros
                    if estado == "🟡"
                ]
                otros_incorrectos = [
                    item.concepto for item, estado in estados_otros
                    if estado == "🔴"
                ]
                col_total_pdf, col_total_calculado, col_diferencia = st.columns(3)
                col_total_pdf.metric(
                    "Total extraído factura", formato_euros(factura.total)
                )
                col_total_calculado.metric(
                    "Total verificado (referencias)",
                    formato_euros(factura.total_calculado_segun_factura)
                    if reconstruccion_total_completa else "No verificable",
                )
                col_diferencia.metric(
                    "Diferencia",
                    formato_euros(factura.diferencia_total_calculado)
                    if reconstruccion_total_completa else "No disponible",
                )
                if (
                    reconstruccion_total_completa
                    and abs(factura.diferencia_total_calculado) >= 0.005
                ):
                    origenes_diferencia = []
                    if not importes_coinciden(
                        factura.total,
                        factura.suma_componentes,
                        "total_factura",
                    ):
                        if factura.diferencia > 0:
                            origenes_diferencia.append(
                                f"{formato_euros(factura.diferencia)} del total "
                                "todavía no están asignados a ningún componente extraído"
                            )
                        else:
                            origenes_diferencia.append(
                                "los componentes extraídos superan el total en "
                                f"{formato_euros(abs(factura.diferencia))}"
                            )
                    if factura.verificacion_fnee and (
                        factura.verificacion_fnee.importe_referencia_eur is not None
                    ):
                        delta = round(
                            factura.verificacion_fnee.importe_facturado_eur
                            - factura.verificacion_fnee.importe_referencia_eur,
                            2,
                        )
                        if abs(delta) > 0.02:
                            origenes_diferencia.append(
                                f"FNEE: {formato_euros(delta)} frente a referencia"
                            )
                    if factura.verificacion_fbs and (
                        factura.verificacion_fbs.importe_regulado_eur is not None
                    ):
                        delta = round(
                            factura.verificacion_fbs.importe_facturado_eur
                            - factura.verificacion_fbs.importe_regulado_eur,
                            2,
                        )
                        if abs(delta) > 0.02:
                            origenes_diferencia.append(
                                f"FBS: {formato_euros(delta)} frente a referencia"
                            )
                    for nombre, verificacion in (
                        ("IEE", factura.verificacion_iee),
                        ("IVA", factura.verificacion_iva),
                    ):
                        if verificacion and verificacion.importe_regulado_eur is not None:
                            delta = round(
                                verificacion.importe_facturado_eur
                                - verificacion.importe_regulado_eur,
                                2,
                            )
                            if abs(delta) > 0.02:
                                origenes_diferencia.append(
                                    f"{nombre}: {formato_euros(delta)} frente a referencia"
                                )
                    delta_reactiva = round(
                        factura.reactiva
                        - sum(
                            item.coste_calculado_eur
                            for item in factura.reactiva_periodos
                        ),
                        2,
                    ) if factura.reactiva_periodos else 0.0
                    if abs(delta_reactiva) > 0.02:
                        origenes_diferencia.append(
                            "Reactiva: "
                            f"{formato_euros(delta_reactiva)} frente al cálculo"
                        )
                    detalle_origen = "; ".join(origenes_diferencia) or (
                        "la diferencia procede de redondeos o ajustes de los "
                        "componentes reconstruidos"
                    )
                    dentro_margen = importes_coinciden(
                        factura.total,
                        factura.total_calculado_segun_factura,
                        "total_factura",
                    )
                    prefijo = (
                        "Diferencia dentro del margen admitido. "
                        if dentro_margen else ""
                    )
                    st.warning(
                        "💶 " + prefijo + "Origen de la diferencia: "
                        + detalle_origen + "."
                    )
                if verificacion_total_ok and otros_pendientes:
                    st.warning(
                        "🔎 El cálculo de la factura es correcto, pero falta "
                        "comprobar con la documentación del usuario: "
                        + ", ".join(otros_pendientes) + "."
                    )
                if verificacion_total_ok and otros_incorrectos:
                    st.error(
                        "Aunque el total queda reconstruido, presentan discrepancias: "
                        + ", ".join(otros_incorrectos) + "."
                    )
                st.subheader("Componentes", divider="rainbow")
                st.dataframe(
                    formatear_columnas_tabla(
                        df_componentes,
                        columnas_euros=["Importe (€)"],
                        incluir_unidades=True,
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
                st.caption(
                    "Verif s/factura: cuadre de los importes extraídos con el total · "
                    "Verif s/cálculo: reproducción del importe con su detalle o fórmula · "
                    "Verificación real: contraste regulatorio, contractual o externo. "
                    "🟢 Verificado · 🔴 No coincide · "
                    "🟢 ⚠️ Desvío favorable · 🟡 Sin datos suficientes · "
                    "🔵 No facturado"
                )
                st.subheader("Peso de los componentes", divider="rainbow")
                df_peso_componentes = pd.DataFrame(
                    componentes_peso_grafico(factura)
                )
                if not df_peso_componentes.empty:
                    figura = px.pie(
                        df_peso_componentes,
                        names="Componente",
                        values="Importe (€)",
                        hole=0.42,
                    )
                    figura.update_traces(textinfo="percent+label")
                    st.plotly_chart(figura, use_container_width=True)
                    if any(item.importe < 0 for item in factura.otros):
                        st.caption(
                            "Los abonos se imputan visualmente primero a Energía y "
                            "después a Potencia; la tabla conserva los importes reales."
                        )
                else:
                    st.info(
                        "No hay importe neto positivo que representar en el gráfico."
                    )

            if MOSTRAR_TABLA_MAXIMETROS and factura.maximetros:
                st.subheader("Maxímetros", divider="rainbow")
                df_maximetros = pd.DataFrame(
                        [
                            {
                                "Periodo": item.periodo,
                                "Potencia máxima (kW)": item.potencia_kw,
                            }
                            for item in factura.maximetros
                        ]
                    )
                st.dataframe(
                    formatear_columnas_tabla(
                        df_maximetros,
                        columnas_kw=["Potencia máxima (kW)"],
                        decimales_kw=2,
                    ),
                    hide_index=True,
                    use_container_width=True,
                )

        with col_grafico:
            st.subheader("Detalle de componentes", divider="rainbow")
            alerta_potencia = (
                factura.sobrecoste_potencia > 0
                or semaforos_reales.get("Potencia") == "🔴"
            )
            etiqueta_potencia = etiqueta_expander(
                "Potencia",
                f"{'⚠️ ' if alerta_potencia else ''}Potencia facturada",
            )
            with st.expander(etiqueta_potencia):
                if factura.potencia_periodos:
                    potencia_facturada_por_meses = all(
                        item.meses is not None
                        and item.precio_facturado_eur_kw_mes is not None
                        for item in factura.potencia_periodos
                    )
                    df_potencia = pd.DataFrame(
                        [
                            ({
                                "Periodo": item.periodo,
                                "Potencia (kW)": item.potencia_kw,
                                "Meses": item.meses,
                                "Precio factura (€/kW mes)": (
                                    item.precio_facturado_eur_kw_mes
                                ),
                                "Precio BOE (€/kW día)": item.precio_boe_eur_kw_dia or None,
                                "Coste factura (€)": item.coste_facturado_eur,
                                "Coste BOE (€)": item.coste_boe_eur or None,
                                "Sobrecoste (€)": item.sobrecoste_eur,
                                "Resultado": (
                                    "🟢 BOE" if item.resultado == "BOE"
                                    else "🟢 ⚠️ Inferior a BOE"
                                    if item.resultado == "Inferior a BOE"
                                    else "⚠️ Superior a BOE"
                                    if item.resultado == "Superior a BOE"
                                    else "No verificado"
                                ),
                            } if potencia_facturada_por_meses else {
                                "Periodo": item.periodo,
                                "Potencia (kW)": item.potencia_kw,
                                "Días": item.dias,
                                "Precio factura (€/kW día)": item.precio_facturado_eur_kw_dia,
                                "Precio BOE (€/kW día)": item.precio_boe_eur_kw_dia or None,
                                "Coste factura (€)": item.coste_facturado_eur,
                                "Coste BOE (€)": item.coste_boe_eur or None,
                                "Sobrecoste (€)": item.sobrecoste_eur,
                                "Resultado": (
                                    "🟢 BOE" if item.resultado == "BOE"
                                    else "🟢 ⚠️ Inferior a BOE"
                                    if item.resultado == "Inferior a BOE"
                                    else "⚠️ Superior a BOE"
                                    if item.resultado == "Superior a BOE"
                                    else "No verificado"
                                ),
                            })
                            for item in factura.potencia_periodos
                        ]
                    )
                    st.dataframe(
                        formatear_columnas_tabla(
                            df_potencia,
                            columnas_kw=["Potencia (kW)"],
                            columnas_eur_kw_dia=[
                                "Precio factura (€/kW día)",
                                "Precio BOE (€/kW día)",
                            ],
                            columnas_eur_kw_mes=[
                                "Precio factura (€/kW mes)",
                            ],
                            columnas_euros=[
                                "Coste factura (€)", "Coste BOE (€)", "Sobrecoste (€)"
                            ],
                            decimales_kw=3,
                            incluir_unidades=False,
                        ),
                        hide_index=True,
                        use_container_width=True,
                    )
                    potencia_desglosada = round(sum(
                        item.coste_facturado_eur
                        for item in factura.potencia_periodos
                    ), 2)
                    if abs(potencia_desglosada - factura.potencia) <= 0.02:
                        st.success(
                            "El desglose de potencia por periodos coincide con el "
                            "importe de potencia de la factura."
                        )
                    else:
                        st.warning(
                            "El desglose de potencia por periodos no coincide con el "
                            "importe de potencia extraído."
                        )
                    calculos_potencia_correctos = all(
                        abs(
                            item.coste_facturado_eur
                            - round(
                                item.potencia_kw * item.meses
                                * item.precio_facturado_eur_kw_mes
                                if potencia_facturada_por_meses
                                else item.potencia_kw * item.dias
                                * item.precio_facturado_eur_kw_dia,
                                2,
                            )
                        ) <= 0.02
                        for item in factura.potencia_periodos
                    )
                    if calculos_potencia_correctos:
                        st.success(
                            "El cálculo potencia × meses × precio mensual coincide "
                            "en todos los periodos facturados."
                            if potencia_facturada_por_meses
                            else "El cálculo potencia × días × precio coincide en "
                            "todos los periodos facturados."
                        )
                    else:
                        st.warning(
                            "Algún periodo no coincide con el cálculo potencia × días "
                            "× precio facturado."
                        )
                    verificadas = [
                        item for item in factura.potencia_periodos
                        if item.resultado != "No verificado"
                    ]
                    if any(item.resultado == "Superior a BOE" for item in verificadas):
                        st.warning(
                            "El término de potencia incluye precios superiores a los "
                            f"regulados. Sobrecoste en el periodo facturado: "
                            f"{formato_euros(factura.sobrecoste_potencia)} "
                            f"({formato_pct(factura.porcentaje_sobrecoste_potencia, 1)} "
                            "del término facturado). De mantenerse las mismas potencias y "
                            "precios durante un año completo, el sobrecoste anual estimado "
                            f"sería de {formato_euros(factura.sobrecoste_anual_potencia)}."
                        )
                    elif verificadas:
                        st.success("El término de potencia está facturado a precios BOE.")
                    else:
                        st.info(
                            "No hay referencia regulada disponible para verificar estos precios."
                        )
                else:
                    st.info("No se ha podido extraer el detalle de potencia por periodos.")

            desplegable_consumo = st.expander(
                etiqueta_expander("Energía", "Consumo facturado")
            )
            if factura.energia_periodos:
                df_energia = pd.DataFrame(
                    [
                        {
                            "Periodo": item.periodo,
                            "Consumo (kWh)": item.consumo_kwh,
                            "Precio (€/kWh)": item.precio_eur_kwh,
                            "Coste (€)": item.coste_eur,
                        }
                        for item in factura.energia_periodos
                    ]
                )
                desplegable_consumo.dataframe(
                    formatear_columnas_tabla(
                        df_energia,
                        columnas_kwh=["Consumo (kWh)"],
                        columnas_eur_kwh=["Precio (€/kWh)"],
                        columnas_euros=["Coste (€)"],
                        decimales_kwh=2,
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                desplegable_consumo.warning(
                    "No se ha podido extraer el detalle de energía por periodos."
                )

            if factura.energia_periodos:
                with desplegable_consumo.container(border=True):
                    col_consumo_grafico, col_consumo_metricas = st.columns([0.68, 0.32])
                    with col_consumo_grafico:
                        st.subheader("Peso del consumo", divider="rainbow")
                        df_consumo_periodos = pd.DataFrame([
                            {"Periodo": item.periodo, "Consumo (kWh)": item.consumo_kwh}
                            for item in factura.energia_periodos
                            if item.consumo_kwh > 0
                        ])
                        if not df_consumo_periodos.empty:
                            es_20td = (
                                (factura.atr or "").replace(" ", "").upper() == "2.0TD"
                            )
                            if es_20td:
                                colores_consumo = {
                                    "P1": "red", "P2": "orange", "P3": "green",
                                }
                                orden_periodos = ["P1", "P2", "P3"]
                            else:
                                colores_consumo = {
                                    "P1": "#D73027", "P2": "#FC8D59",
                                    "P3": "#FEE08B", "P4": "#D9EF8B",
                                    "P5": "#91CF60", "P6": "#1A9850",
                                }
                                orden_periodos = ["P1", "P2", "P3", "P4", "P5", "P6"]

                            figura_consumo = px.pie(
                                df_consumo_periodos,
                                names="Periodo",
                                values="Consumo (kWh)",
                                color="Periodo",
                                color_discrete_map=colores_consumo,
                                category_orders={"Periodo": orden_periodos},
                                hole=0.3,
                            )
                            figura_consumo.update_traces(
                                textposition="inside", textinfo="label+percent",
                            )
                            figura_consumo.update_layout(
                                legend_title_text="Periodo", showlegend=True,
                            )
                            st.plotly_chart(figura_consumo, use_container_width=True)

                    with col_consumo_metricas:
                        st.metric(
                            "Consumo",
                            formato_kwh(factura.consumo_total_kwh, 2, True),
                        )
                        st.metric(
                            "Precio medio",
                            formato_eur_kwh(factura.precio_medio_energia)
                            if factura.consumo_total_kwh
                            else "No disponible",
                        )
                        st.metric(
                            "Coste de la energía",
                            formato_euros(factura.energia),
                        )

            desplegable_excesos = st.expander(
                etiqueta_expander("Excesos", "Verificación de excesos")
            )
            if not factura.excesos_potencia:
                desplegable_excesos.info(
                    "🔵 La factura no incluye excesos de potencia."
                )
            elif factura.excesos_verificados or factura.verificacion_excesos:
                with desplegable_excesos:
                    if factura.excesos_verificados:
                        es_tipo_123 = factura.tipo_suministro in {
                            "Tipo 1", "Tipo 2", "Tipo 3"
                        }
                        df_excesos = pd.DataFrame(
                            [
                                ({
                                    "Periodo": item.periodo,
                                    "Contratada (kW)": item.potencia_contratada_kw,
                                    "Maxímetro (kW)": item.maximetro_kw,
                                    "Sobrepasamiento equivalente (kW)": item.exceso_kw,
                                    "TEP (€/kW)": item.tepp_eur_kw_dia,
                                    "Coste (€)": item.coste_calculado_eur,
                                } if es_tipo_123 else {
                                    "Periodo": item.periodo,
                                    "Contratada (kW)": item.potencia_contratada_kw,
                                    "Maxímetro (kW)": item.maximetro_kw,
                                    "Exceso (kW)": item.exceso_kw,
                                    "TEPp (€/kW día)": item.tepp_eur_kw_dia,
                                    "Días": item.dias,
                                    "Coste (€)": item.coste_calculado_eur,
                                })
                                for item in factura.excesos_verificados
                            ]
                        )
                        st.dataframe(
                            formatear_columnas_tabla(
                                df_excesos,
                                columnas_kw=[
                                    "Contratada (kW)", "Maxímetro (kW)", "Exceso (kW)",
                                    "Sobrepasamiento equivalente (kW)",
                                ],
                                columnas_eur_kw_dia=["TEPp (€/kW día)", "TEP (€/kW)"],
                                columnas_euros=["Coste (€)"],
                            ),
                            hide_index=True,
                            use_container_width=True,
                        )
                        col_exc_calc, col_exc_fra = st.columns(2)
                        col_exc_calc.metric(
                            "Excesos calculados",
                            formato_euros(factura.coste_excesos_calculado),
                        )
                        col_exc_fra.metric(
                            "Excesos facturados",
                            formato_euros(factura.excesos_potencia),
                            delta=formato_euros(factura.diferencia_excesos),
                            delta_color="inverse",
                        )

                    if factura.verificacion_excesos:
                        if (
                            factura.excesos_verificados
                            and importes_coinciden(
                                factura.excesos_potencia,
                                factura.coste_excesos_calculado,
                                "excesos_maximetros",
                            )
                        ):
                            st.success(factura.verificacion_excesos)
                        else:
                            st.info(factura.verificacion_excesos)

            with st.expander(
                etiqueta_expander("Reactiva", "Energía reactiva")
            ):
                if factura.reactiva:
                    st.error(
                        "La factura incluye una penalización por reactiva de "
                        f"{formato_euros(factura.reactiva)}."
                    )
                else:
                    st.success("No se ha detectado coste por energía reactiva.")
                if factura.reactiva_periodos:
                    coste_reactiva_detallado = all(
                        item.detalle_coste_facturado
                        for item in factura.reactiva_periodos
                    )
                    etiqueta_coste_factura = (
                        "Coste factura (€)" if coste_reactiva_detallado
                        else "Coste factura prorrateado (€)"
                    )
                    df_reactiva = pd.DataFrame([
                        {
                            "Periodo": item.periodo,
                            "Activa (kWh)": item.energia_activa_kwh,
                            "Reactiva (kVArh)": item.energia_reactiva_kvarh,
                            "Exceso factura (kVArh)": item.exceso_facturado_kvarh,
                            "Exceso calculado (kVArh)": item.exceso_calculado_kvarh,
                            "cos φ": item.cos_phi,
                            "Precio (€/kVArh)": item.precio_eur_kvarh,
                            etiqueta_coste_factura: item.coste_facturado_eur,
                            "Coste calculado (€)": item.coste_calculado_eur,
                            "Verificación": item.estado,
                        }
                        for item in factura.reactiva_periodos
                    ])
                    st.dataframe(
                        formatear_columnas_tabla(
                            df_reactiva,
                            columnas_kwh=[
                                "Activa (kWh)", "Reactiva (kVArh)",
                                "Exceso factura (kVArh)",
                                "Exceso calculado (kVArh)",
                            ],
                            columnas_eur_kwh=["Precio (€/kVArh)"],
                            columnas_euros=[
                                etiqueta_coste_factura, "Coste calculado (€)",
                            ],
                            incluir_unidades=False,
                        ),
                        hide_index=True,
                        use_container_width=True,
                    )
                    if any(
                        item.estado == "🔴"
                        for item in factura.reactiva_periodos
                    ):
                        st.error(
                            "El coste total de reactiva supera el cálculo regulado."
                        )
                    elif any(
                        item.estado == "🟢 ⚠️"
                        for item in factura.reactiva_periodos
                    ):
                        st.warning(
                            "El coste total de reactiva difiere del cálculo, pero "
                            "la diferencia favorece al cliente."
                        )
                    elif all(
                        item.estado == "🟢"
                        for item in factura.reactiva_periodos
                    ):
                        st.success(
                            "El coste de reactiva coincide con las lecturas, "
                            "los excesos y los precios regulados por periodo."
                        )
                    if not coste_reactiva_detallado:
                        st.caption(
                            "La factura solo publica el coste total de reactiva. "
                            "El reparto por periodo es un prorrateo técnico para "
                            "visualización; la verificación compara los totales."
                        )
                st.dataframe(
                    formatear_columnas_tabla(
                        pd.DataFrame(tramos_reactiva()),
                        columnas_eur_kwh=["Precio (€/kVArh)"],
                        incluir_unidades=False,
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
                st.caption(
                    "La reactiva inductiva penalizable es la que excede el "
                    f"{LIMITE_REACTIVA_SOBRE_ACTIVA:.0%} de la energía activa "
                    f"en P1-P5. Fuente: {FUENTE_REACTIVA}."
                )
                if not factura.reactiva_periodos:
                    st.info(
                        "Para verificar el importe hacen falta energía activa y "
                        "reactiva desglosadas por periodo. Si el PDF solo publica el "
                        "coste, se detecta la penalización, pero no se reconstruye."
                    )

            if factura.iee or factura.iva:
                estados_impuestos = [
                    semaforos_factura.get(nombre, "🟡")
                    for nombre in ("IEE", "IVA")
                    if nombre in semaforos_factura
                ]
                estado_impuestos = (
                    "🔴" if "🔴" in estados_impuestos
                    else "🟢" if estados_impuestos and all(
                        estado == "🟢" for estado in estados_impuestos
                    )
                    else "🟡"
                )
                with st.expander(f"{estado_impuestos} IEE e IVA"):
                    filas_impuestos = []
                    for nombre, importe_componente, verificacion in (
                        ("IEE", factura.iee, factura.verificacion_iee),
                        ("IVA", factura.iva, factura.verificacion_iva),
                    ):
                        if not importe_componente:
                            continue
                        filas_impuestos.append({
                            "Impuesto": nombre,
                            "Base (€)": verificacion.base_eur if verificacion else None,
                            "Tipo aplicado (%)": (
                                verificacion.tipo_pct if verificacion else None
                            ),
                            "Tipo regulado (%)": (
                                verificacion.tipo_regulado_pct
                                if verificacion else None
                            ),
                            "Importe factura (€)": importe_componente,
                            "Importe calculado (€)": (
                                verificacion.importe_calculado_eur
                                if verificacion else None
                            ),
                            "Verificación s/factura": (
                                "🟢" if verificacion and abs(
                                    verificacion.importe_facturado_eur
                                    - verificacion.importe_calculado_eur
                                ) <= 0.02 else "🟡"
                            ),
                            "Verificación real": (
                                verificacion.estado if verificacion else "🟡"
                            ),
                        })
                    df_impuestos = pd.DataFrame(filas_impuestos)
                    st.dataframe(
                        formatear_columnas_tabla(
                            df_impuestos,
                            columnas_euros=[
                                "Base (€)", "Importe factura (€)",
                                "Importe calculado (€)",
                            ],
                            columnas_pct=["Tipo aplicado (%)", "Tipo regulado (%)"],
                            incluir_unidades=False,
                            decimales_pct=6,
                        ),
                        hide_index=True,
                        use_container_width=True,
                    )
                    for verificacion in (
                        factura.verificacion_iee,
                        factura.verificacion_iva,
                    ):
                        if not verificacion:
                            continue
                        if verificacion.estado == "🟢":
                            st.success(verificacion.mensaje)
                        elif verificacion.estado == "🔴":
                            st.error(verificacion.mensaje)
                        else:
                            st.info(verificacion.mensaje)

            if factura.otros:
                with st.expander(
                    etiqueta_expander("Otros", "Otros conceptos detectados")
                ):
                    df_otros = pd.DataFrame(
                        [
                            {
                                "Concepto": item.concepto,
                                "Importe factura (€)": item.importe,
                                "Importe calculado (€)": (
                                    factura.verificacion_fbs.importe_regulado_eur
                                    if factura.verificacion_fbs
                                    and "bono social" in item.concepto.lower()
                                    else factura.verificacion_fnee.importe_referencia_eur
                                    if factura.verificacion_fnee
                                    and "fnee" in item.concepto.lower()
                                    else None
                                ),
                                "Verificación": (
                                    "🟡"
                                    if "ssaa/ree" in item.concepto.lower()
                                    else
                                    factura.verificacion_fbs.estado
                                    if factura.verificacion_fbs
                                    and "bono social" in item.concepto.lower()
                                    else factura.verificacion_fnee.estado
                                    if factura.verificacion_fnee
                                    and "fnee" in item.concepto.lower()
                                    else estado_otro_segun_factura(
                                        factura, texto, item
                                    )
                                ),
                                "Observación": (
                                    "No verificable: la factura no identifica el "
                                    "ciclo de liquidación al que corresponde."
                                    if "ssaa/ree" in item.concepto.lower()
                                    else
                                    "Servicio adicional contratado; compruebe si "
                                    "sigue siendo necesario y si puede cancelarse."
                                    if es_servicio_adicional(item)
                                    else
                                    "Aceptado por defecto según factura; "
                                    "sujeto a validación con datos del cliente."
                                    if "alquiler" in item.concepto.lower()
                                    else factura.verificacion_fbs.mensaje
                                    if factura.verificacion_fbs
                                    and not factura.verificacion_fbs.estado.startswith("🟢")
                                    and "bono social" in item.concepto.lower()
                                    else factura.verificacion_fnee.mensaje
                                    if factura.verificacion_fnee
                                    and not factura.verificacion_fnee.estado.startswith("🟢")
                                    and "fnee" in item.concepto.lower()
                                    else ""
                                ),
                            }
                            for item in factura.otros
                        ]
                    )
                    st.dataframe(
                        formatear_columnas_tabla(
                            df_otros,
                            columnas_euros=[
                                "Importe factura (€)",
                                "Importe calculado (€)",
                            ],
                            incluir_unidades=True,
                        ),
                        hide_index=True,
                        use_container_width=True,
                    )
                    if factura.verificacion_fbs or factura.verificacion_fnee:
                        fbs = factura.verificacion_fbs
                        fnee = factura.verificacion_fnee
                        col_unitario_fbs, col_unitario_fnee, col_referencia_fnee = (
                            st.columns(3)
                        )
                        col_unitario_fbs.metric(
                            "FBS regulado",
                            formato_euros(fbs.precio_regulado_eur_dia) + "/día"
                            if fbs and fbs.precio_regulado_eur_dia is not None
                            else "No disponible",
                            delta=(
                                formato_euros(
                                    fbs.precio_facturado_eur_dia
                                    - fbs.precio_regulado_eur_dia
                                )
                                if fbs
                                and fbs.precio_facturado_eur_dia is not None
                                and fbs.precio_regulado_eur_dia is not None
                                else None
                            ),
                            delta_color="inverse",
                        )
                        col_unitario_fnee.metric(
                            "FNEE facturado/implícito",
                            formato_eur_mwh(fnee.precio_facturado_eur_mwh, 3)
                            if fnee
                            and fnee.precio_facturado_eur_mwh is not None
                            else "No disponible",
                        )
                        col_referencia_fnee.metric(
                            "FNEE de referencia",
                            formato_eur_mwh(fnee.precio_referencia_eur_mwh, 3)
                            if fnee
                            and fnee.precio_referencia_eur_mwh is not None
                            else "No disponible",
                        )
                        if fbs:
                            st.caption(f"FBS calculado sobre {fbs.dias} días.")
                    if any(
                        "ssaa/ree" in item.concepto.lower()
                        for item in factura.otros
                    ):
                        st.warning(
                            "La reliquidación de servicios de ajuste REE se ha "
                            "detectado, pero no puede verificarse porque la factura "
                            "no indica el ciclo de liquidación correspondiente."
                        )
                    if factura.verificacion_fnee:
                        fnee = factura.verificacion_fnee
                        st.caption(f"Modalidad: {fnee.modalidad}")

            with st.expander("Detalles técnicos"):
                st.write(f"Identificador local del PDF: `{huella[:16]}`")
                st.json(factura.como_dict())
                st.text_area("Texto extraído", texto, height=240)


with tab_comparativa:
    col_formula, col_resultado, col_visual = st.columns([0.30, 0.34, 0.36])

    if factura is None:
        with col_formula:
            st.subheader("Comparativa de energía", divider="rainbow")
            st.info("Carga una factura válida en la pestaña Análisis.")
    else:
        st.session_state.zona_periodos_index = "peninsula"
        atr_indexado = _atr_indexado(factura.atr)
        inicio_indexado = _fecha_factura(factura.periodo_inicio)
        fin_indexado = _fecha_factura(factura.periodo_fin)

        with col_formula:
            st.subheader("Propuesta", divider="rainbow")

            st.markdown("#### Término de potencia")
            with st.container(border=True):
                persist_widget(
                    st.radio,
                    "Tratamiento del precio de potencia",
                    [
                        "Mantener precios de factura",
                        "Aplicar precios BOE",
                        "Personalizar con margen",
                    ],
                    key="factura_modo_precio_potencia",
                    default="Aplicar precios BOE",
                )
                if (
                    st.session_state.get("factura_modo_precio_potencia")
                    == "Personalizar con margen"
                ):
                    persist_widget(
                        st.number_input,
                        "Margen a añadir (€/kW año)",
                        min_value=0.0,
                        max_value=100.0,
                        step=0.1,
                        key="factura_margen_potencia_personalizado",
                        default=0.0,
                    )
                    st.caption(
                        "Margen único añadido al precio de todos los periodos."
                    )

            st.markdown("#### Término de energía")
            with st.container(border=True):
                persist_widget(
                    st.radio,
                    "Tipo de propuesta de energía",
                    ["Indexado", "Fijo"],
                    key="factura_tipo_energia",
                    default="Indexado",
                    horizontal=True,
                )
                if st.session_state.get("factura_tipo_energia") == "Fijo":
                    numero_periodos = 3 if atr_indexado == "2.0" else 6
                    columnas_precios = st.columns(3)
                    for indice in range(1, numero_periodos + 1):
                        with columnas_precios[(indice - 1) % 3]:
                            persist_widget(
                                st.number_input,
                                f"P{indice} (€/kWh)",
                                min_value=0.0,
                                max_value=2.0,
                                step=0.001,
                                format="%.6f",
                                key=f"factura_precio_fijo_p{indice}",
                                default=0.0,
                            )
                else:
                    st.caption(
                        "Configuración compartida con Telemindex durante esta sesión."
                    )
                    mostrar_parametros_formula_indexado()

            if st.session_state.get("factura_tipo_energia") == "Indexado":
                if inicio_indexado and fin_indexado:
                    st.info(
                        f"Periodo trasladado: {inicio_indexado:%d/%m/%Y} → "
                        f"{fin_indexado:%d/%m/%Y} · ATR "
                        f"{factura.atr or 'no detectado'}"
                    )
                else:
                    st.warning("La factura no contiene un periodo válido.")

            calcular = st.button(
                "Calcular comparativa",
                type="primary",
                use_container_width=True,
                disabled=atr_indexado is None,
            )

            if calcular:
                try:
                    if st.session_state.get("factura_tipo_energia") == "Fijo":
                        resultado_nuevo = _calcular_comparativa_fijo(factura)
                    else:
                        with st.spinner("Cargando precios y calculando el periodo…"):
                            resultado_nuevo = _calcular_comparativa_indexado(factura)
                except Exception as exc:
                    st.session_state.pop("factura_comparativa_indexado", None)
                    st.error(str(exc))
                else:
                    st.session_state.factura_comparativa_indexado = {
                        "huella": huella,
                        "firma": _firma_propuesta_energia(atr_indexado),
                        "resultado": resultado_nuevo,
                    }

        comparativa_sesion = st.session_state.get("factura_comparativa_indexado")
        resultado = None
        if (
            comparativa_sesion
            and comparativa_sesion.get("huella") == huella
            and comparativa_sesion.get("firma")
            == _firma_propuesta_energia(atr_indexado)
        ):
            resultado = comparativa_sesion["resultado"]

        with col_resultado:
            st.subheader("Resultado", divider="rainbow")
            if resultado is None:
                st.info(
                    "Pulsa «Calcular comparativa» para valorar el término de energía "
                    "con la propuesta indicada."
                )
            else:
                tipo_propuesta = resultado.get("tipo", "Indexado")
                tipo_propuesta_minusculas = tipo_propuesta.lower()
                diferencia_energia_pct = (
                    resultado["diferencia"] / resultado["coste_facturado"] * 100
                    if resultado["coste_facturado"]
                    else None
                )
                df_comparativa_componentes = _componentes_propuesta(
                    factura, resultado
                )
                total_factura = df_comparativa_componentes["Factura (€)"].sum()
                total_propuesta = df_comparativa_componentes["Propuesta (€)"].sum()
                diferencia_total = total_propuesta - total_factura
                diferencia_total_pct = (
                    diferencia_total / total_factura * 100
                    if total_factura
                    else None
                )
                propuesta_mejor = diferencia_total <= 0
                aviso_icono = "🚀" if propuesta_mejor else "🛑"
                aviso_color = "#00c853" if propuesta_mejor else "#ef4444"
                aviso_fondo = (
                    "rgba(0,200,83,.12)"
                    if propuesta_mejor
                    else "rgba(239,68,68,.12)"
                )
                aviso_borde = (
                    "rgba(0,200,83,.55)"
                    if propuesta_mejor
                    else "rgba(239,68,68,.55)"
                )
                aviso_texto = (
                    "La propuesta mejora la factura en"
                    if propuesta_mejor
                    else "La propuesta resulta más cara que la factura en"
                )
                diferencia_aviso = formato_euros(abs(diferencia_total))
                porcentaje_aviso = (
                    f" ({formato_pct(abs(diferencia_total_pct), 2)})"
                    if diferencia_total_pct is not None
                    else ""
                )
                st.markdown(
                    "<div style='display:flex;align-items:center;justify-content:"
                    "space-between;gap:1rem;flex-wrap:wrap;margin:1rem 0 .8rem 0;"
                    f"padding:.8rem 1rem;border:1px solid {aviso_borde};"
                    f"border-radius:1rem;background:{aviso_fondo};"
                    "box-shadow:0 4px 14px rgba(0,0,0,.10);'>"
                    "<div style='font-size:1.35rem;font-weight:700;line-height:1.3;'>"
                    f"{aviso_texto} "
                    f"<span style='display:inline-block;color:{aviso_color};"
                    "font-size:2.1rem;margin-left:.55rem;line-height:1.15;'>"
                    f"{diferencia_aviso}{porcentaje_aviso}</span></div>"
                    "<div style='display:flex;align-items:center;justify-content:center;"
                    "width:3.7rem;height:3.7rem;flex:0 0 3.7rem;"
                    "background:transparent;font-size:2.8rem;line-height:1;'>"
                    f"{aviso_icono}</div></div>",
                    unsafe_allow_html=True,
                )
                st.dataframe(
                    formatear_columnas_tabla(
                        df_comparativa_componentes,
                        columnas_euros=[
                            "Factura (€)", "Propuesta (€)", "Diferencia (€)",
                        ],
                        columnas_pct=["Diferencia (%)"],
                        incluir_unidades=True,
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
                metrica_total_factura, metrica_total_propuesta, metrica_diferencia = (
                    st.columns(3)
                )
                with metrica_total_factura:
                    st.markdown(
                        "<div style='height:.75rem'></div>",
                        unsafe_allow_html=True,
                    )
                    st.metric("Total factura", formato_euros(total_factura))
                with metrica_total_propuesta:
                    st.markdown(
                        "<div style='height:.75rem'></div>",
                        unsafe_allow_html=True,
                    )
                    st.metric("Total propuesta", formato_euros(total_propuesta))
                with metrica_diferencia.container(border=True):
                    st.metric(
                        "Diferencia",
                        formato_euros(diferencia_total),
                        delta=(
                            formato_pct(diferencia_total_pct, 2)
                            if diferencia_total_pct is not None
                            else None
                        ),
                        delta_color="inverse",
                    )
                st.markdown("#### Detalle del término de energía propuesto")
                detalle_resultado = resultado["detalle"].copy()
                if (
                    "Coste propuesta (€)" not in detalle_resultado.columns
                    and "Coste indexado (€)" in detalle_resultado.columns
                ):
                    detalle_resultado = detalle_resultado.rename(
                        columns={"Coste indexado (€)": "Coste propuesta (€)"}
                    )
                if (
                    "Precio propuesta (€/kWh)" not in detalle_resultado.columns
                    and "Precio indexado (€/kWh)" in detalle_resultado.columns
                ):
                    detalle_resultado = detalle_resultado.rename(
                        columns={
                            "Precio indexado (€/kWh)": "Precio propuesta (€/kWh)"
                        }
                    )
                if "Peso consumo (%)" not in detalle_resultado.columns:
                    detalle_resultado["Peso consumo (%)"] = (
                        detalle_resultado["Consumo (kWh)"]
                        / resultado["consumo_total"]
                        * 100
                    )
                detalle_mostrado = detalle_resultado[
                    [
                        "Periodo",
                        "Consumo (kWh)",
                        "Peso consumo (%)",
                        "Precio propuesta (€/kWh)",
                        "Coste propuesta (€)",
                    ]
                ]
                detalle_mostrado = pd.concat(
                    [
                        detalle_mostrado,
                        pd.DataFrame([{
                            "Periodo": "Total",
                            "Consumo (kWh)": resultado["consumo_total"],
                            "Peso consumo (%)": 100.0,
                            "Precio propuesta (€/kWh)": resultado["precio_indexado"],
                            "Coste propuesta (€)": resultado["coste_indexado"],
                        }]),
                    ],
                    ignore_index=True,
                )
                st.dataframe(
                    formatear_columnas_tabla(
                        detalle_mostrado,
                        columnas_kwh=["Consumo (kWh)"],
                        columnas_pct=["Peso consumo (%)"],
                        columnas_eur_kwh=["Precio propuesta (€/kWh)"],
                        columnas_euros=["Coste propuesta (€)"],
                        decimales_kwh=2,
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
                st.markdown(
                    "<div style='font-size:1.05rem; line-height:1.45; margin-top:0.6rem;'>"
                    "La fila total muestra el precio medio ponderado de la propuesta "
                    "según el peso de consumo de cada periodo."
                    "</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    "<div style='height:1.25rem;'></div>",
                    unsafe_allow_html=True,
                )
                metrica_precio_factura, metrica_precio_propuesta = st.columns(2)
                metrica_precio_factura.metric(
                    "Precio medio facturado",
                    formato_eur_kwh(resultado["precio_facturado"], 5),
                )
                metrica_precio_propuesta.metric(
                    f"Precio medio {tipo_propuesta_minusculas}",
                    formato_eur_kwh(resultado["precio_indexado"], 5),
                    delta=(
                        formato_pct(diferencia_energia_pct, 2)
                        if diferencia_energia_pct is not None
                        else None
                    ),
                    delta_color="inverse",
                )

        with col_visual:
            st.subheader("Gráfico comparativo", divider="rainbow")
            if resultado is not None:
                colores_componentes = {
                    "Potencia": "#2563EB",
                    "Energía": "#F97316",
                    "Excesos": "#DC2626",
                    "Reactiva": "#9333EA",
                    "Otros": "#EAB308",
                    "IEE": "#14B8A6",
                    "IVA": "#EC4899",
                    "Sin asignar": "#64748B",
                }
                df_grafico_componentes = df_comparativa_componentes.melt(
                    id_vars="Componente",
                    value_vars=["Factura (€)", "Propuesta (€)"],
                    var_name="Escenario",
                    value_name="Importe (€)",
                )
                df_grafico_componentes["Escenario"] = (
                    df_grafico_componentes["Escenario"]
                    .str.replace(" (€)", "", regex=False)
                )
                figura_componentes = px.bar(
                    df_grafico_componentes,
                    x="Escenario",
                    y="Importe (€)",
                    color="Componente",
                    barmode="stack",
                    color_discrete_map=colores_componentes,
                    category_orders={
                        "Componente": list(colores_componentes),
                        "Escenario": ["Factura", "Propuesta"],
                    },
                )
                figura_componentes.update_traces(
                    width=0.38,
                    marker_cornerradius=8,
                    hovertemplate=(
                        "<b>%{fullData.name}</b><br>"
                        "%{x}: %{y:,.2f} €<extra></extra>"
                    ),
                )
                for escenario, total in (
                    ("Factura", total_factura),
                    ("Propuesta", total_propuesta),
                ):
                    figura_componentes.add_annotation(
                        x=escenario,
                        y=total,
                        text=f"<b>{formato_euros(total)}</b>",
                        showarrow=False,
                        yshift=22,
                        font=dict(size=24),
                    )
                figura_componentes.update_layout(
                    title_text="",
                    xaxis_title="",
                    yaxis_title="",
                    legend_title_text="",
                    margin=dict(l=10, r=10, t=65, b=10),
                )
                figura_componentes = aplicar_estilo(figura_componentes)
                figura_componentes.update_xaxes(
                    title_text="",
                    tickfont=dict(size=20),
                )
                figura_componentes.update_yaxes(
                    title_text="Coste (€)",
                    title_font=dict(size=20),
                    tickfont=dict(size=16),
                )
                st.plotly_chart(figura_componentes, use_container_width=True)

                margen_potencia_propuesta = _margen_potencia_propuesta(factura)
                margen_energia_propuesta = (
                    resultado["consumo_total"]
                    * (
                        st.session_state.get("margen_telemindex", 0.0)
                        if resultado.get("tipo") == "Indexado"
                        else 0.0
                    )
                    / 1000
                )
                margen_total_propuesta = (
                    margen_potencia_propuesta + margen_energia_propuesta
                )
                st.subheader("Tu beneficio", divider="rainbow")
                with st.container(border=True):
                    col_margen_tp, col_margen_te, col_margen_total = st.columns(3)
                    col_margen_tp.metric(
                        "Término de potencia",
                        formato_euros(margen_potencia_propuesta),
                    )
                    col_margen_te.metric(
                        "Término de energía",
                        formato_euros(margen_energia_propuesta),
                    )
                    col_margen_total.metric(
                        "Margen total",
                        formato_euros(margen_total_propuesta),
                    )
                    st.caption(
                        "Margen comercial nominal correspondiente al periodo "
                        "analizado, antes de IEE e IVA."
                    )

                mostrar_grafico_energia_anterior = False
                if mostrar_grafico_energia_anterior:
                    etiqueta_propuesta = (
                        f"Propuesta {resultado.get('tipo', 'Indexado').lower()}"
                    )
                    df_comparacion = pd.DataFrame(
                        {
                            "Alternativa": ["Factura", etiqueta_propuesta],
                            "Coste de energía (€)": [
                                resultado["coste_facturado"],
                                resultado["coste_indexado"],
                            ],
                        }
                    )
                    figura_comparacion = px.bar(
                        df_comparacion,
                        x="Alternativa",
                        y="Coste de energía (€)",
                        color="Alternativa",
                        color_discrete_map={
                            "Factura": "#ec4899",
                            etiqueta_propuesta: "#1C83E1",
                        },
                    )
                    figura_comparacion.update_traces(
                        width=0.38,
                        marker_cornerradius=12,
                        texttemplate="<b>%{y:,.2f} €</b>",
                        textposition="outside",
                        textfont=dict(size=28),
                        cliponaxis=False,
                    )
                    figura_comparacion.update_layout(
                        title_text="",
                        showlegend=False,
                        margin=dict(l=10, r=10, t=55, b=10),
                    )
                    figura_comparacion = aplicar_estilo(figura_comparacion)
                    st.plotly_chart(figura_comparacion, use_container_width=True)


with tab_informe:
    st.subheader("Informe", divider="rainbow")
    col_informe, col_salida_informe = st.columns([0.40, 0.60])
    contenedor_salida_informe = col_salida_informe.container()
    with col_informe:
        if factura is None:
            st.info(
                "Carga y analiza una factura para preparar los datos del informe."
            )
            contenedor_salida_informe.info(
                "La vista previa aparecerá aquí cuando exista una propuesta."
            )
        else:
            datos_informe = _datos_informe_desde_factura(factura, texto)
            if st.session_state.get("_factura_informe_huella") != huella:
                for clave, valor in datos_informe.items():
                    st.session_state[clave] = valor
                st.session_state["_factura_informe_huella"] = huella
                st.session_state.pop("factura_informe_logo", None)
            else:
                for clave, valor in datos_informe.items():
                    st.session_state.setdefault(clave, valor)

            st.caption(
                "Los datos detectados en la factura son editables. Revisa la "
                "información antes de generar o entregar el informe."
            )
            with st.container(border=True):
                st.markdown("#### Datos del cliente y del suministro")
                col_cliente, col_nif = st.columns([0.68, 0.32])
                persist_widget(
                    col_cliente.text_input,
                    "Cliente / Razón social",
                    key="factura_informe_cliente",
                    default=datos_informe["factura_informe_cliente"],
                )
                persist_widget(
                    col_nif.text_input,
                    "NIF / CIF",
                    key="factura_informe_nif",
                    default=datos_informe["factura_informe_nif"],
                )
                persist_widget(
                    st.text_input,
                    "Dirección",
                    key="factura_informe_direccion",
                    default=datos_informe["factura_informe_direccion"],
                )
                col_cups, col_atr = st.columns([0.68, 0.32])
                persist_widget(
                    col_cups.text_input,
                    "CUPS",
                    key="factura_informe_cups",
                    default=datos_informe["factura_informe_cups"],
                )
                persist_widget(
                    col_atr.text_input,
                    "ATR",
                    key="factura_informe_atr",
                    default=datos_informe["factura_informe_atr"],
                )

            with st.container(border=True):
                st.markdown("#### Datos de la factura")
                col_comercializadora, col_numero = st.columns([0.58, 0.42])
                persist_widget(
                    col_comercializadora.text_input,
                    "Comercializadora",
                    key="factura_informe_comercializadora",
                    default=datos_informe[
                        "factura_informe_comercializadora"
                    ],
                )
                persist_widget(
                    col_numero.text_input,
                    "Número de factura",
                    key="factura_informe_numero",
                    default=datos_informe["factura_informe_numero"],
                )
                col_fecha, col_ciclo = st.columns([0.32, 0.68])
                persist_widget(
                    col_fecha.text_input,
                    "Fecha de factura",
                    key="factura_informe_fecha",
                    default=datos_informe["factura_informe_fecha"],
                )
                persist_widget(
                    col_ciclo.text_input,
                    "Ciclo de facturación",
                    key="factura_informe_ciclo",
                    default=datos_informe["factura_informe_ciclo"],
                )

            with st.container(border=True):
                st.markdown("#### Datos del informe")
                col_autor, col_fecha_informe = st.columns([0.60, 0.40])
                persist_widget(
                    col_autor.text_input,
                    "Realizado por",
                    key="factura_informe_realizado_por",
                    default=datos_informe["factura_informe_realizado_por"],
                )
                persist_widget(
                    col_fecha_informe.text_input,
                    "Fecha de realización",
                    key="factura_informe_fecha_realizacion",
                    default=datos_informe[
                        "factura_informe_fecha_realizacion"
                    ],
                )
                persist_widget(
                    st.text_input,
                    "Objeto de la propuesta",
                    key="factura_informe_objeto",
                    default=datos_informe["factura_informe_objeto"],
                )

            with st.container(border=True):
                st.markdown("#### Personalización")
                logo_informe = st.file_uploader(
                    "Logo para el informe",
                    type=["png", "jpg", "jpeg"],
                    accept_multiple_files=False,
                    key="factura_informe_logo",
                )
                if logo_informe is not None:
                    st.image(logo_informe, width=180)

            contenedor_salida_informe.markdown("#### Resumen comercial")
            if resultado is None:
                contenedor_salida_informe.info(
                    "Calcula primero la propuesta para preparar el resumen comercial."
                )
            else:
                componentes_informe = _componentes_propuesta(factura, resultado)
                total_factura_informe = componentes_informe["Factura (€)"].sum()
                total_propuesta_informe = componentes_informe["Propuesta (€)"].sum()
                diferencia_informe = (
                    total_propuesta_informe - total_factura_informe
                )
                diferencia_pct_informe = (
                    diferencia_informe / total_factura_informe * 100
                    if total_factura_informe else 0.0
                )
                favorable_informe = diferencia_informe <= 0
                maximo_total = max(
                    total_factura_informe, total_propuesta_informe, 0.01
                )
                logo_bytes = (
                    logo_informe.getvalue() if logo_informe is not None else b""
                )
                firma_resumen = hashlib.sha256()
                firma_resumen.update(b"informe-comercial-factura-v6")
                firma_resumen.update((huella or "").encode("utf-8"))
                firma_resumen.update(
                    repr((
                        total_factura_informe,
                        total_propuesta_informe,
                        resultado.get("tipo", "Indexado"),
                        st.session_state.get(
                            "factura_modo_precio_potencia", ""
                        ),
                        *(
                            st.session_state.get(clave, "")
                            for clave in datos_informe
                        ),
                    )).encode("utf-8")
                )
                firma_resumen.update(logo_bytes)
                firma_resumen = firma_resumen.hexdigest()

                if contenedor_salida_informe.button(
                    "Preparar informe comercial",
                    type="primary",
                    use_container_width=True,
                ):
                    logo_data = ""
                    if logo_informe is not None:
                        subtipo_logo = (
                            "jpeg"
                            if logo_informe.type == "image/jpeg"
                            else "png"
                        )
                        logo_data = (
                            f"data:image/{subtipo_logo};base64,"
                            + base64.b64encode(logo_bytes).decode("ascii")
                        )
                    grafico_componentes_data = ""
                    if figura_componentes is not None:
                        try:
                            grafico_png = figura_componentes.to_image(
                                format="png",
                                width=1100,
                                height=520,
                                scale=1.5,
                            )
                            grafico_componentes_data = (
                                "data:image/png;base64,"
                                + base64.b64encode(grafico_png).decode("ascii")
                            )
                        except Exception:
                            contenedor_salida_informe.warning(
                                "No se ha podido incorporar el gráfico a la "
                                "vista previa."
                            )
                    filas_componentes_informe = []
                    for _, fila in componentes_informe.iterrows():
                        diferencia_fila = float(fila["Diferencia (€)"])
                        porcentaje_fila = fila["Diferencia (%)"]
                        clase_fila = (
                            "favorable"
                            if diferencia_fila < -0.005
                            else "unfavorable"
                            if diferencia_fila > 0.005
                            else "neutral"
                        )
                        filas_componentes_informe.append({
                            "componente": escape(str(fila["Componente"])),
                            "factura": formato_euros(fila["Factura (€)"]),
                            "propuesta": formato_euros(fila["Propuesta (€)"]),
                            "diferencia": formato_euros(diferencia_fila),
                            "diferencia_pct": (
                                formato_pct(porcentaje_fila, 2)
                                if porcentaje_fila is not None
                                and not pd.isna(porcentaje_fila)
                                else "—"
                            ),
                            "clase": clase_fila,
                        })

                    diferencias_relevantes = componentes_informe.loc[
                        componentes_informe["Diferencia (€)"].abs() > 0.005
                    ]
                    if diferencias_relevantes.empty:
                        insight_principal = (
                            "La propuesta no modifica el coste total de los "
                            "componentes analizados."
                        )
                    else:
                        indice_principal = (
                            diferencias_relevantes["Diferencia (€)"].idxmin()
                            if favorable_informe
                            else diferencias_relevantes["Diferencia (€)"].idxmax()
                        )
                        fila_principal = componentes_informe.loc[indice_principal]
                        impacto_principal = float(
                            fila_principal["Diferencia (€)"]
                        )
                        insight_principal = (
                            f"El componente {fila_principal['Componente']} "
                            + (
                                "reduce el coste en "
                                if impacto_principal < 0
                                else "incrementa el coste en "
                            )
                            + formato_euros(abs(impacto_principal))
                            + "."
                        )

                    filas_energia = componentes_informe.loc[
                        componentes_informe["Componente"] == "Energía"
                    ]
                    if filas_energia.empty:
                        insight_energia = (
                            "No hay un término de energía comparable disponible."
                        )
                    else:
                        fila_energia = filas_energia.iloc[0]
                        insight_energia = (
                            f"Pasa de "
                            f"{formato_euros(fila_energia['Factura (€)'])} "
                            f"a "
                            f"{formato_euros(fila_energia['Propuesta (€)'])}, "
                            f"con un precio medio de propuesta de "
                            f"{formato_eur_kwh(resultado['precio_indexado'], 5)}."
                        )
                    filas_potencia = componentes_informe.loc[
                        componentes_informe["Componente"] == "Potencia"
                    ]
                    modo_potencia = st.session_state.get(
                        "factura_modo_precio_potencia",
                        "Aplicar precios BOE",
                    )
                    if filas_potencia.empty:
                        insight_potencia = (
                            f"{modo_potencia}. No hay un término de potencia "
                            "comparable disponible."
                        )
                    else:
                        fila_potencia = filas_potencia.iloc[0]
                        insight_potencia = (
                            f"{modo_potencia}. El coste pasa de "
                            f"{formato_euros(fila_potencia['Factura (€)'])} a "
                            f"{formato_euros(fila_potencia['Propuesta (€)'])}."
                        )

                    detalle_energia = resultado["detalle"].copy()
                    if "Peso consumo (%)" not in detalle_energia:
                        detalle_energia["Peso consumo (%)"] = (
                            detalle_energia["Consumo (kWh)"]
                            / resultado["consumo_total"]
                            * 100
                        )
                    filas_energia_tecnica = [
                        {
                            "periodo": escape(str(fila["Periodo"])),
                            "consumo": formato_kwh(fila["Consumo (kWh)"]),
                            "peso": formato_pct(
                                fila["Peso consumo (%)"], 2
                            ),
                            "precio": formato_eur_kwh(
                                fila["Precio propuesta (€/kWh)"], 6
                            ),
                            "coste": formato_euros(
                                fila["Coste propuesta (€)"]
                            ),
                        }
                        for _, fila in detalle_energia.iterrows()
                    ]

                    modo_potencia_informe = st.session_state.get(
                        "factura_modo_precio_potencia",
                        "Aplicar precios BOE",
                    )
                    margen_potencia = st.session_state.get(
                        "factura_margen_potencia_personalizado", 0.0
                    )
                    filas_potencia_tecnica = []
                    for item in factura.potencia_periodos:
                        if modo_potencia_informe == "Mantener precios de factura":
                            coste_potencia_periodo = item.coste_facturado_eur
                        elif modo_potencia_informe == "Aplicar precios BOE":
                            coste_potencia_periodo = item.coste_boe_eur
                        else:
                            coste_potencia_periodo = (
                                item.coste_boe_eur
                                + item.potencia_kw
                                * item.dias
                                * margen_potencia
                                / 365
                            )
                        potencia_es = (
                            f"{item.potencia_kw:,.2f}"
                            .replace(",", "X")
                            .replace(".", ",")
                            .replace("X", ".")
                        )
                        filas_potencia_tecnica.append({
                            "periodo": escape(str(item.periodo)),
                            "potencia": f"{potencia_es} kW",
                            "dias": str(item.dias),
                            "factura": formato_euros(
                                item.coste_facturado_eur
                            ),
                            "propuesta": formato_euros(
                                coste_potencia_periodo
                            ),
                        })

                    filas_impuestos_tecnica = []
                    parametros_iee_informe = _parametros_iee_propuesta(factura)
                    for impuesto in ("IEE", "IVA"):
                        filas_impuesto = componentes_informe.loc[
                            componentes_informe["Componente"] == impuesto
                        ]
                        if filas_impuesto.empty:
                            continue
                        fila_impuesto = filas_impuesto.iloc[0]
                        if impuesto == "IEE" and parametros_iee_informe:
                            tipo_impuesto = formato_pct(
                                parametros_iee_informe[1], 6
                            )
                        elif impuesto == "IVA" and factura.verificacion_iva:
                            tipo_impuesto = formato_pct(
                                factura.verificacion_iva.tipo_pct, 2
                            )
                        else:
                            tipo_impuesto = "No disponible"
                        filas_impuestos_tecnica.append({
                            "impuesto": impuesto,
                            "tipo": tipo_impuesto,
                            "factura": formato_euros(
                                fila_impuesto["Factura (€)"]
                            ),
                            "propuesta": formato_euros(
                                fila_impuesto["Propuesta (€)"]
                            ),
                        })

                    parametros_formula = []
                    if resultado.get("tipo") == "Indexado":
                        parametros_formula = [
                            {
                                "nombre": "Desvíos apantallados",
                                "valor": formato_eur_mwh(
                                    st.session_state.get(
                                        "desvios_apant", 0.0
                                    ), 2
                                ),
                            },
                            {
                                "nombre": "Margen",
                                "valor": formato_eur_mwh(
                                    st.session_state.get(
                                        "margen_telemindex", 0.0
                                    ), 2
                                ),
                            },
                            {
                                "nombre": "Posición del margen",
                                "valor": escape(str(st.session_state.get(
                                    "cfg_margen_pos", "tm"
                                ))),
                            },
                            {
                                "nombre": "FNEE",
                                "valor": (
                                    "Incluido"
                                    if st.session_state.get("cfg_fnee", True)
                                    else "No incluido"
                                ),
                            },
                            {
                                "nombre": "Posición del FNEE",
                                "valor": (
                                    escape(str(st.session_state.get(
                                        "cfg_fnee_pos", "perdidas"
                                    )))
                                    if st.session_state.get("cfg_fnee", True)
                                    else "No aplica"
                                ),
                            },
                            {
                                "nombre": "Coste financiero",
                                "valor": formato_pct(
                                    st.session_state.get("cf_pct", 0.0), 2
                                ),
                            },
                        ]
                    else:
                        parametros_formula = [{
                            "nombre": "Modalidad",
                            "valor": "Precios fijos por periodo",
                        }]

                    hipotesis_tecnicas = [
                        "Se mantiene el consumo registrado en la factura.",
                        "La propuesta modifica únicamente los términos "
                        "parametrizados por el usuario.",
                        "Los conceptos sin propuesta específica conservan el "
                        "importe facturado.",
                        "IEE e IVA se recalculan sobre las bases resultantes "
                        "cuando existen datos suficientes para contrastarlos.",
                        "No se utiliza curva de carga para ponderar el término "
                        "de energía; se emplea el consumo facturado por periodo.",
                    ]
                    contexto_resumen = {
                        "logo": logo_data,
                        "cliente": escape(
                            st.session_state.get(
                                "factura_informe_cliente", ""
                            )
                        ),
                        "cups": escape(
                            st.session_state.get("factura_informe_cups", "")
                        ),
                        "numero_factura": escape(
                            st.session_state.get(
                                "factura_informe_numero", ""
                            )
                        ),
                        "ciclo": escape(
                            st.session_state.get(
                                "factura_informe_ciclo", ""
                            )
                        ),
                        "realizado_por": escape(
                            st.session_state.get(
                                "factura_informe_realizado_por", ""
                            )
                        ),
                        "fecha_realizacion": escape(
                            st.session_state.get(
                                "factura_informe_fecha_realizacion", ""
                            )
                        ),
                        "objeto_propuesta": escape(
                            st.session_state.get(
                                "factura_informe_objeto", ""
                            )
                        ),
                        "hero_label": (
                            "Ahorro estimado con la propuesta"
                            if favorable_informe
                            else "Sobrecoste estimado de la propuesta"
                        ),
                        "diferencia": formato_euros(abs(diferencia_informe)),
                        "diferencia_pct": formato_pct(
                            abs(diferencia_pct_informe), 2
                        ),
                        "total_factura": formato_euros(
                            total_factura_informe
                        ),
                        "total_propuesta": formato_euros(
                            total_propuesta_informe
                        ),
                        "factura_width": round(
                            total_factura_informe / maximo_total * 100, 2
                        ),
                        "propuesta_width": round(
                            total_propuesta_informe / maximo_total * 100, 2
                        ),
                        "hero_color": (
                            "#15803d" if favorable_informe else "#dc2626"
                        ),
                        "hero_border": (
                            "#86efac" if favorable_informe else "#fca5a5"
                        ),
                        "hero_background": (
                            "#f0fdf4" if favorable_informe else "#fef2f2"
                        ),
                        "highlight_energia": (
                            "Propuesta de energía "
                            f"{resultado.get('tipo', 'Indexado').lower()}."
                        ),
                        "highlight_potencia": (
                            "Término de potencia: "
                            + st.session_state.get(
                                "factura_modo_precio_potencia",
                                "Aplicar precios BOE",
                            ).lower()
                            + "."
                        ),
                        "highlight_periodo": (
                            "Comparación realizada sobre el periodo y consumo "
                            "de la factura analizada."
                        ),
                        "insight_principal": escape(insight_principal),
                        "insight_energia": escape(insight_energia),
                        "insight_potencia": escape(insight_potencia),
                        "filas_componentes": filas_componentes_informe,
                        "grafico_componentes": grafico_componentes_data,
                        "atr": escape(str(factura.atr or "")),
                        "consumo_total": formato_kwh(
                            resultado["consumo_total"]
                        ),
                        "tipo_propuesta": escape(str(
                            resultado.get("tipo", "Indexado")
                        )),
                        "modo_potencia": escape(modo_potencia_informe),
                        "filas_energia_tecnica": filas_energia_tecnica,
                        "filas_potencia_tecnica": filas_potencia_tecnica,
                        "filas_impuestos_tecnica": filas_impuestos_tecnica,
                        "parametros_formula": parametros_formula,
                        "hipotesis_tecnicas": hipotesis_tecnicas,
                    }
                    html_resumen = _renderizar_plantilla_informe(
                        contexto_resumen,
                        "templates/informe_factura_resumen.html",
                    )
                    st.session_state["factura_resumen_comercial"] = {
                        "firma": firma_resumen,
                        "html": html_resumen,
                    }

                resumen_sesion = st.session_state.get(
                    "factura_resumen_comercial"
                )
                if (
                    resumen_sesion
                    and resumen_sesion.get("firma") == firma_resumen
                ):
                    with contenedor_salida_informe.expander(
                        "Vista previa del resumen comercial",
                        expanded=True,
                    ):
                        st.components.v1.html(
                            resumen_sesion["html"],
                            height=900,
                            scrolling=True,
                        )
                elif resumen_sesion:
                    contenedor_salida_informe.info(
                        "Los datos han cambiado. Prepara de nuevo el resumen "
                        "para actualizar la vista previa."
                    )
