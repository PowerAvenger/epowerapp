"""Comparador inicial de un PPA de carga base."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from backend_comun import aplicar_estilo
from backend_indexado import FormulaIndexada
from backend_ppa import calcular_ppa_fijo, calcular_ppa_indexado
from backend_telemindex import construir_df_curva_sheets, filtrar_datos_por_rango
from componentes_curva import render_origen_curva
from formato_es import (
    formatear_columnas_tabla,
    formato_euros,
    formato_euros_con_signo,
    formato_kwh,
    formato_kw,
    formato_mes_es,
    formato_mwh,
    formato_pct,
    formato_pct_con_signo,
)
from servicio_curva import obtener_curva_sesion
from utilidades import generar_menu, init_app, init_app_index, mostrar_parametros_formula_indexado


def _formula(parametros):
    return FormulaIndexada(
        desvios_apant=float(parametros.get("desvios_apant", 0.0)),
        margen=float(parametros.get("margen_telemindex", 0.0)),
        margen_pos=parametros.get("cfg_margen_pos", "neto"),
        incluir_fnee=bool(parametros.get("cfg_fnee", True)),
        fnee_pos=parametros.get("cfg_fnee_pos", "perdidas"),
        cf_pct=float(parametros.get("cf_pct", 0.0)),
        otros_costes=float(parametros.get("otros_costes_indexado", 0.0)),
        otros_costes_pos=parametros.get("cfg_otros_costes_pos", "neto"),
    )


def _tabla_mensual(detalle):
    fechas = pd.to_datetime(detalle["fecha_hora"], errors="coerce")
    mensual = detalle.assign(Mes=fechas.dt.to_period("M").astype(str)).groupby(
        "Mes", as_index=False
    ).agg(**{
        "Referencia (€)": ("coste_referencia_eur", "sum"),
        "Con PPA (€)": ("coste_escenario_ppa_eur", "sum"),
        "Cubierto PPA (kWh)": ("energia_ppa_cubierta_kWh", "sum"),
        "Energía no cubierta (kWh)": ("energia_residual_kWh", "sum"),
        "Excedente (kWh)": ("energia_excedente_kWh", "sum"),
    })
    mensual["Ahorro (€)"] = mensual["Referencia (€)"] - mensual["Con PPA (€)"]
    mensual["Mes"] = mensual["Mes"].map(formato_mes_es)
    return mensual


def _serie_temporal(detalle, frecuencia):
    """Agrega los bloques energéticos conservando su relación física."""
    temporal = detalle.copy()
    temporal["Fecha"] = pd.to_datetime(temporal["fecha_hora"], errors="coerce")
    temporal = temporal.dropna(subset=["Fecha"]).set_index("Fecha")
    regla = "D" if frecuencia == "Diaria" else "MS"
    return temporal.resample(regla).agg(
        consumo=("consumo_neto_kWh", "sum"),
        contratado=("energia_ppa_contratada_kWh", "sum"),
        cubierto=("energia_ppa_cubierta_kWh", "sum"),
        no_cubierto=("energia_residual_kWh", "sum"),
        excedente=("energia_excedente_kWh", "sum"),
    ).reset_index()


def _grafico_evolucion_energia(detalle, frecuencia):
    temporal = _serie_temporal(detalle, frecuencia)
    figura = go.Figure()
    figura.add_bar(
        x=temporal["Fecha"], y=temporal["cubierto"], name="Cubierta PPA",
        marker_color="#00A878",
        hovertemplate="%{x|%d/%m/%Y}<br>Cubierta: %{y:,.0f} kWh<extra></extra>",
    )
    figura.add_bar(
        x=temporal["Fecha"], y=temporal["no_cubierto"], name="No cubierta",
        marker_color="#F59E0B",
        hovertemplate="%{x|%d/%m/%Y}<br>No cubierta: %{y:,.0f} kWh<extra></extra>",
    )
    figura.add_scatter(
        x=temporal["Fecha"], y=temporal["consumo"], name="Consumo total",
        mode="lines", line=dict(color="#7E57C2", width=2),
        hovertemplate="%{x|%d/%m/%Y}<br>Consumo: %{y:,.0f} kWh<extra></extra>",
    )
    figura.add_scatter(
        x=temporal["Fecha"], y=temporal["contratado"], name="PPA contratado",
        mode="lines", line=dict(color="#60A5FA", width=2),
        hovertemplate="%{x|%d/%m/%Y}<br>Contratado: %{y:,.0f} kWh<extra></extra>",
    )
    figura.add_scatter(
        x=temporal["Fecha"], y=temporal["excedente"], name="Excedente",
        mode="lines", line=dict(color="#F87171", width=2, dash="dot"),
        hovertemplate="%{x|%d/%m/%Y}<br>Excedente: %{y:,.0f} kWh<extra></extra>",
    )
    figura.update_layout(
        barmode="stack", separators=",.", title=f"Evolución {frecuencia.lower()}",
        xaxis_title="Fecha", yaxis_title="Energía (kWh)", hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return aplicar_estilo(figura)


if not st.session_state.get("usuario_autenticado", False) and not st.session_state.get("usuario_free", False):
    st.switch_page("epowerapp.py")

generar_menu()
init_app()
st.session_state.zona_periodos_index = "peninsula"
init_app_index()

st.sidebar.header("⚡ PPA")
st.title("PPA · Carga base")
st.caption(
    "Compara el coste actual de la energía con un PPA de carga base. "
    "Primera versión: el excedente se muestra, pero no se valora."
)

col_config, col_resumen, col_resultados = st.columns([1, 1.12, 1.12], gap="large")

with col_config:
    st.subheader("Configuración", divider="rainbow")
    with st.expander("Curva de carga", expanded=False):
        origen = st.container()
        acciones = st.container()
        render_origen_curva(
            origen, acciones, clave="ppa_curva", titulo_compacto=True,
            mostrar_resumen=False, mostrar_aviso_resolucion=False,
        )

    curva_activa = obtener_curva_sesion(st.session_state)
    atr = str((curva_activa or {}).get("atr") or st.session_state.get("atr_dfnorm", ""))
    if curva_activa:
        rango = curva_activa.get("rango_fechas")
        consumo = pd.to_numeric(
            curva_activa["df_norm_h"]["consumo_neto_kWh"], errors="coerce"
        ).sum()
        st.success(f"Curva activa · ATR {atr}TD · {formato_kwh(consumo, unidad=True)}")
        if rango:
            st.caption(f"{rango[0]:%d/%m/%Y} → {rango[1]:%d/%m/%Y}")
    else:
        st.info("Carga una curva para activar el cálculo.")

    parametros_formula = None
    precios_fijos = {}
    with st.expander("Contrato a comparar", expanded=False):
        tipo_referencia = st.radio(
            "Tipo de precio", ("Fijo", "Indexado"), horizontal=True,
            key="ppa_tipo_referencia",
        )
        if tipo_referencia == "Fijo":
            numero_periodos = 3 if atr == "2.0" else 6
            columnas = st.columns(3)
            for indice in range(1, numero_periodos + 1):
                with columnas[(indice - 1) % 3]:
                    precios_fijos[f"P{indice}"] = st.number_input(
                        f"P{indice} (€/kWh)", min_value=0.0, max_value=2.0,
                        value=0.100, step=0.001, format="%.6f",
                        key=f"ppa_fijo_p{indice}",
                    )
        else:
            st.markdown("##### Fórmula indexada")
            parametros_formula = mostrar_parametros_formula_indexado(
                widget_suffix="ppa",
                claves_estado={clave: f"ppa_{clave}" for clave in (
                    "desvios_apant", "margen_telemindex", "cfg_margen_pos",
                    "cfg_fnee", "cfg_fnee_pos", "cf_pct",
                    "otros_costes_indexado", "cfg_otros_costes_pos",
                )},
            )

    with st.expander("Opciones del PPA", expanded=False):
        st.selectbox("Tipo de PPA", ("Carga base",), disabled=True)
        potencia_ppa = st.number_input(
            "Potencia base contratada (MW)", min_value=0.0, value=0.100,
            step=0.010, format="%.3f", key="ppa_potencia_mw",
        )
        precio_ppa = st.number_input(
            "Precio PPA en barras de central (€/MWh)", min_value=0.0,
            value=50.0, step=0.5, format="%.2f", key="ppa_precio_eur_mwh",
        )
        st.caption(
            f"{formato_kw(potencia_ppa * 1000, 0, unidad=True)} · "
            f"{formato_mwh(potencia_ppa * 8760, 0, unidad=True)}/año teóricos"
        )
    calcular = st.button(
        "Calcular PPA", type="primary", use_container_width=True,
        disabled=curva_activa is None or atr not in {"2.0", "3.0", "6.1", "6.2"},
    )

if calcular:
    try:
        curva = curva_activa["df_norm_h"].copy()
        if tipo_referencia == "Indexado":
            mercado = filtrar_datos_por_rango(
                st.session_state.df_sheets, curva_activa.get("rango_fechas")
            )
            if mercado.empty:
                raise ValueError("No hay precios de mercado para el periodo de la curva.")
            curva = construir_df_curva_sheets(mercado)
            detalle, resumen = calcular_ppa_indexado(
                curva, atr, _formula(parametros_formula or {}), potencia_ppa, precio_ppa
            )
        else:
            detalle, resumen = calcular_ppa_fijo(
                curva, atr, precios_fijos, potencia_ppa, precio_ppa
            )
        st.session_state.ppa_resultado = {
            "detalle": detalle, "resumen": resumen, "tipo": tipo_referencia, "atr": atr,
        }
    except Exception as exc:
        st.session_state.pop("ppa_resultado", None)
        st.error(str(exc))

resultado = st.session_state.get("ppa_resultado")

with col_resumen:
    st.subheader("Consumo y costes", divider="rainbow")
    if resultado is None:
        st.info("Configura el contrato y pulsa «Calcular PPA».")
    else:
        resumen = resultado["resumen"].copy()
        total = resumen.loc[resumen["Periodo"] == "Total"].iloc[0]
        energia_contratada = (
            total.get("Contratado PPA (kWh)", 0.0)
            or total["Cubierto PPA (kWh)"] + total["Excedente (kWh)"]
        )
        aprovechamiento_ppa = total.get("Aprovechamiento PPA (%)")
        if pd.isna(aprovechamiento_ppa):
            aprovechamiento_ppa = (
                total["Cubierto PPA (kWh)"] / energia_contratada * 100
                if energia_contratada else 0.0
            )
        metricas = st.columns(3)
        metricas[0].metric("Consumo", formato_kwh(total["Consumo (kWh)"], unidad=True))
        metricas[1].metric("Cobertura PPA", formato_pct(total["Cobertura (%)"], 1))
        metricas[2].metric(
            "Energía no cubierta", formato_kwh(total["Residual (kWh)"], unidad=True)
        )
        metricas = st.columns(3)
        metricas[0].metric(
            "Excedente no valorado", formato_kwh(total["Excedente (kWh)"], unidad=True)
        )
        metricas[1].metric(
            "Aprovechamiento PPA", formato_pct(aprovechamiento_ppa, 1)
        )

        st.markdown(f"#### Referencia {resultado['tipo'].lower()}")
        referencia = resumen[[
            "Periodo", "Consumo (kWh)", "Precio referencia (€/MWh)", "Coste referencia (€)",
        ]]
        st.dataframe(formatear_columnas_tabla(
            referencia,
            columnas_kwh=["Consumo (kWh)"],
            columnas_eur_mwh=["Precio referencia (€/MWh)"],
            columnas_euros=["Coste referencia (€)"],
        ), hide_index=True, use_container_width=True)

        st.markdown("#### Escenario PPA")
        escenario = resumen[[
            "Periodo", "Cubierto PPA (kWh)", "Residual (kWh)",
            "Cobertura (%)", "Precio con PPA (€/MWh)", "Coste con PPA (€)",
        ]].rename(columns={"Residual (kWh)": "Energía no cubierta (kWh)"})
        st.dataframe(formatear_columnas_tabla(
            escenario,
            columnas_kwh=["Cubierto PPA (kWh)", "Energía no cubierta (kWh)"],
            columnas_pct=["Cobertura (%)"],
            columnas_eur_mwh=["Precio con PPA (€/MWh)"],
            columnas_euros=["Coste con PPA (€)"],
            decimales_pct=1,
        ), hide_index=True, use_container_width=True)
        st.caption(
            "Comparativa del término de energía. No incluye potencia, impuestos ni "
            "una liquidación económica de los excedentes."
        )

with col_resultados:
    st.subheader("Resultados", divider="rainbow")
    if resultado is None:
        st.info("Aquí aparecerán el ahorro y los gráficos comparativos.")
    else:
        detalle = resultado["detalle"]
        total = resultado["resumen"].loc[
            resultado["resumen"]["Periodo"] == "Total"
        ].iloc[0]
        ahorro = total["Ahorro (€)"]
        porcentaje = ahorro / total["Coste referencia (€)"] * 100 if total["Coste referencia (€)"] else 0
        m1, m2, m3 = st.columns(3)
        m1.metric("Coste referencia", formato_euros(total["Coste referencia (€)"]))
        m2.metric("Coste con PPA", formato_euros(total["Coste con PPA (€)"]))
        m3.metric(
            "Ahorro", formato_euros_con_signo(ahorro),
            delta=formato_pct_con_signo(porcentaje),
        )

        with st.expander("Evolución temporal de la energía", expanded=False):
            frecuencia_temporal = st.radio(
                "Resolución", ("Diaria", "Mensual"), horizontal=True,
                key="ppa_frecuencia_grafico_energia",
            )
            st.plotly_chart(
                _grafico_evolucion_energia(detalle, frecuencia_temporal),
                use_container_width=True,
            )
            st.caption(
                "Las barras apiladas forman el consumo: energía cubierta por el "
                "PPA más energía no cubierta. El excedente se representa por "
                "separado y no forma parte del consumo."
            )

        mensual = _tabla_mensual(detalle)
        costes = mensual.melt(
            id_vars="Mes", value_vars=["Referencia (€)", "Con PPA (€)"],
            var_name="Escenario", value_name="Coste (€)",
        )
        fig_costes = px.bar(
            costes, x="Mes", y="Coste (€)", color="Escenario", barmode="group",
            title="Coste mensual de la energía",
            color_discrete_map={"Referencia (€)": "#7E57C2", "Con PPA (€)": "#00A878"},
        )
        fig_costes.update_layout(separators=",.")
        with st.expander("Coste mensual de la energía", expanded=False):
            st.plotly_chart(aplicar_estilo(fig_costes), use_container_width=True)

        energia = mensual.melt(
            id_vars="Mes", value_vars=[
                "Cubierto PPA (kWh)", "Energía no cubierta (kWh)", "Excedente (kWh)"
            ], var_name="Bloque", value_name="Energía (kWh)",
        )
        fig_energia = px.bar(
            energia, x="Mes", y="Energía (kWh)", color="Bloque", barmode="stack",
            title="Reparto mensual de energía",
        )
        fig_energia.update_layout(separators=",.")
        with st.expander("Reparto mensual de energía", expanded=False):
            st.plotly_chart(aplicar_estilo(fig_energia), use_container_width=True)

        with st.expander("Resumen mensual", expanded=False):
            st.dataframe(formatear_columnas_tabla(
                mensual,
                columnas_kwh=[
                    "Cubierto PPA (kWh)", "Energía no cubierta (kWh)",
                    "Excedente (kWh)",
                ],
                columnas_euros=["Referencia (€)", "Con PPA (€)", "Ahorro (€)"],
            ), hide_index=True, use_container_width=True)
