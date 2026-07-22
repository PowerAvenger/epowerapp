import hashlib

from html import escape

import pandas as pd
import plotly.express as px
import streamlit as st

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
from utilidades import generar_menu
from regulacion_reactiva import (
    FUENTE_REACTIVA,
    LIMITE_REACTIVA_SOBRE_ACTIVA,
    tramos_reactiva,
)


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
    for clave in ("factura_pdf_bytes", "factura_pdf_nombre", "factura_uploader"):
        st.session_state.pop(clave, None)


col_entrada, col_detalle, col_grafico = st.columns([0.26, 0.30, 0.44])

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
            item["Componente"]: item["Verificación s/factura"]
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

            if factura.excesos_verificados or factura.verificacion_excesos:
                with st.expander(
                    etiqueta_expander("Excesos", "Verificación de excesos")
                ):
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
                                "Importe (€)": item.importe,
                                "Verificación": (
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
                                    "Servicio adicional contratado; compruebe si "
                                    "sigue siendo necesario y si puede cancelarse."
                                    if es_servicio_adicional(item)
                                    else
                                    "Aceptado por defecto según factura; "
                                    "sujeto a validación con datos del cliente."
                                    if "alquiler" in item.concepto.lower()
                                    else factura.verificacion_fbs.mensaje
                                    if factura.verificacion_fbs
                                    and factura.verificacion_fbs.estado == "🟡"
                                    and "bono social" in item.concepto.lower()
                                    else ""
                                ),
                            }
                            for item in factura.otros
                        ]
                    )
                    st.dataframe(
                        formatear_columnas_tabla(
                            df_otros,
                            columnas_euros=["Importe (€)"],
                            incluir_unidades=True,
                        ),
                        hide_index=True,
                        use_container_width=True,
                    )
                    if factura.verificacion_fbs:
                        fbs = factura.verificacion_fbs
                        col_fbs_dias, col_fbs_facturado, col_fbs_regulado = st.columns(3)
                        col_fbs_dias.metric("Días FBS", fbs.dias)
                        col_fbs_facturado.metric(
                            "FBS facturado", formato_euros(fbs.importe_facturado_eur)
                        )
                        col_fbs_regulado.metric(
                            "FBS regulado",
                            formato_euros(fbs.importe_regulado_eur)
                            if fbs.importe_regulado_eur is not None
                            else "No disponible",
                        )
                        if fbs.estado == "🟢":
                            st.success(fbs.mensaje)
                        elif fbs.estado == "🟢 ⚠️":
                            st.warning(fbs.mensaje)
                        elif fbs.estado == "🔴":
                            st.error(fbs.mensaje)
                        else:
                            st.warning(fbs.mensaje)
                    if factura.verificacion_fnee:
                        fnee = factura.verificacion_fnee
                        st.markdown("**Verificación FNEE**")
                        col_fnee_facturado, col_fnee_referencia, col_fnee_importe = (
                            st.columns(3)
                        )
                        col_fnee_facturado.metric(
                            "Precio facturado/implícito",
                            formato_eur_mwh(fnee.precio_facturado_eur_mwh, 3)
                            if fnee.precio_facturado_eur_mwh is not None
                            else "No disponible",
                        )
                        col_fnee_referencia.metric(
                            "Referencia propia",
                            formato_eur_mwh(fnee.precio_referencia_eur_mwh, 3)
                            if fnee.precio_referencia_eur_mwh is not None
                            else "No disponible",
                        )
                        col_fnee_importe.metric(
                            "Importe según referencia",
                            formato_euros(fnee.importe_referencia_eur)
                            if fnee.importe_referencia_eur is not None
                            else "No disponible",
                            delta=(
                                formato_euros(
                                    fnee.importe_facturado_eur
                                    - fnee.importe_referencia_eur
                                )
                                if fnee.importe_referencia_eur is not None
                                else None
                            ),
                            delta_color="inverse",
                        )
                        st.caption(f"Modalidad: {fnee.modalidad}")
                        if fnee.estado == "🟢":
                            st.success(fnee.mensaje)
                        elif fnee.estado == "🟢 ⚠️":
                            st.warning(fnee.mensaje)
                        elif fnee.estado == "🔴":
                            st.error(fnee.mensaje)
                        else:
                            st.info(fnee.mensaje)

            with st.expander("Detalles técnicos"):
                st.write(f"Identificador local del PDF: `{huella[:16]}`")
                st.json(factura.como_dict())
                st.text_area("Texto extraído", texto, height=240)
