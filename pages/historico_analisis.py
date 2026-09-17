from __future__ import annotations

import json
import sqlite3

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data_beta.db import DEFAULT_DB_PATH, initialize_database
from formato_es import formato_euros, formato_euros_con_signo, formato_kwh
from utilidades import generar_menu


generar_menu()
if not st.session_state.get("usuario_autenticado", False):
    st.switch_page("epowerapp.py")

st.title("📚 Histórico de verificaciones y comparativas")
st.caption(
    "Consulta expedientes guardados, reproduce sus resultados y analiza su "
    "evolución sin recalcular los datos originales."
)
if not DEFAULT_DB_PATH.exists():
    st.info("La base local todavía no se ha creado en este equipo.")
    st.stop()
initialize_database(DEFAULT_DB_PATH)


def consultar(sql: str, parametros: tuple = ()) -> pd.DataFrame:
    with sqlite3.connect(DEFAULT_DB_PATH) as connection:
        return pd.read_sql_query(sql, connection, params=parametros)


def cargar_snapshot(analisis_id: int) -> dict:
    with sqlite3.connect(DEFAULT_DB_PATH) as connection:
        fila = connection.execute(
            "SELECT snapshot_json FROM analisis_factura WHERE id = ?",
            (int(analisis_id),),
        ).fetchone()
    if fila is None:
        raise ValueError("El expediente ya no existe.")
    return json.loads(fila[0])


expedientes = consultar(
    """
    SELECT a.id, a.tipo, s.cups20 AS cups, a.numero_factura,
           a.fecha_factura, a.ciclo_inicio, a.ciclo_fin, a.estado,
           a.total_facturado_eur, a.total_referencia_eur,
           a.diferencia_eur, a.diferencia_pct, a.version_calculo, a.creado_en
    FROM analisis_factura a
    JOIN suministros s ON s.id = a.suministro_id
    ORDER BY a.ciclo_fin, a.id
    """
)
if expedientes.empty:
    st.info(
        "Todavía no hay resultados guardados. Guarda una verificación o una "
        "comparativa desde Análisis de facturas."
    )
    st.stop()
for columna in ("fecha_factura", "ciclo_inicio", "ciclo_fin", "creado_en"):
    expedientes[columna] = pd.to_datetime(expedientes[columna], errors="coerce")

st.subheader("Filtros", divider="rainbow")
col_cups, col_tipo, col_desde, col_hasta = st.columns([1.25, 1, 0.8, 0.8])
cups_seleccionados = col_cups.multiselect(
    "CUPS", sorted(expedientes["cups"].dropna().unique()),
    placeholder="Todos los suministros",
)
etiquetas_tipo = {
    "VERIFICACION": "Verificación",
    "COMPARATIVA_AHORRO": "Comparativa de ahorro",
}
tipos_seleccionados = col_tipo.multiselect(
    "Tipo de análisis", list(etiquetas_tipo),
    format_func=lambda valor: etiquetas_tipo[valor],
    placeholder="Todos los tipos",
)
fecha_minima = expedientes["ciclo_inicio"].min().date()
fecha_maxima = expedientes["ciclo_fin"].max().date()
desde = col_desde.date_input("Desde", value=fecha_minima)
hasta = col_hasta.date_input("Hasta", value=fecha_maxima)
filtrados = expedientes.loc[
    expedientes["ciclo_fin"].dt.date.ge(desde)
    & expedientes["ciclo_inicio"].dt.date.le(hasta)
].copy()
if cups_seleccionados:
    filtrados = filtrados[filtrados["cups"].isin(cups_seleccionados)]
if tipos_seleccionados:
    filtrados = filtrados[filtrados["tipo"].isin(tipos_seleccionados)]

tab_expedientes, tab_detalle, tab_evolucion, tab_consumos = st.tabs(
    ("Expedientes", "Detalle reconstruido", "Evolución", "Consumos facturados")
)

with tab_expedientes:
    col_n, col_facturado, col_referencia, col_diferencia = st.columns(4)
    col_n.metric("Expedientes", len(filtrados))
    col_facturado.metric(
        "Total facturado", formato_euros(filtrados["total_facturado_eur"].sum())
    )
    col_referencia.metric(
        "Total contrastado", formato_euros(filtrados["total_referencia_eur"].sum())
    )
    col_diferencia.metric(
        "Factura − referencia",
        formato_euros_con_signo(filtrados["diferencia_eur"].sum()),
    )
    tabla_expedientes = filtrados.copy()
    tabla_expedientes["tipo"] = tabla_expedientes["tipo"].map(etiquetas_tipo)
    st.dataframe(
        tabla_expedientes.rename(columns={
            "id": "ID", "tipo": "Tipo", "cups": "CUPS",
            "numero_factura": "Factura", "ciclo_inicio": "Inicio",
            "ciclo_fin": "Fin", "estado": "Resultado",
            "total_facturado_eur": "Facturado (€)",
            "total_referencia_eur": "Referencia (€)",
            "diferencia_eur": "Diferencia (€)",
            "diferencia_pct": "Diferencia (%)",
        }), hide_index=True, use_container_width=True,
    )
    st.download_button(
        "Descargar expedientes filtrados CSV",
        data=tabla_expedientes.to_csv(index=False).encode("utf-8-sig"),
        file_name="historico_analisis_facturas.csv", mime="text/csv",
    )

with tab_detalle:
    if filtrados.empty:
        st.info("No hay expedientes para los filtros seleccionados.")
    else:
        opciones = {
            (
                f"ID {int(fila.id)} · {etiquetas_tipo[fila.tipo]} · "
                f"{fila.cups} · {fila.ciclo_inicio:%d/%m/%Y}–"
                f"{fila.ciclo_fin:%d/%m/%Y}"
            ): int(fila.id)
            for fila in filtrados.itertuples()
        }
        etiqueta = st.selectbox("Expediente", tuple(reversed(opciones)))
        expediente_id = opciones[etiqueta]
        cabecera = filtrados.loc[filtrados["id"] == expediente_id].iloc[0]
        snapshot = cargar_snapshot(expediente_id)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Resultado", cabecera["estado"])
        c2.metric("Facturado", formato_euros(cabecera["total_facturado_eur"]))
        c3.metric("Referencia", formato_euros(cabecera["total_referencia_eur"]))
        c4.metric(
            "Factura − referencia",
            formato_euros_con_signo(cabecera["diferencia_eur"]),
        )
        resultado_snapshot = snapshot.get("resultado", {})
        st.markdown("#### Resumen por componentes")
        st.dataframe(
            pd.DataFrame(resultado_snapshot.get("componentes", [])),
            hide_index=True, use_container_width=True,
        )
        nombres_detalle = {
            "termino_potencia": "Término de potencia",
            "detalle_potencia": "Detalle de potencia",
            "comparacion_potencia": "Comparación de potencia",
            "detalle_excesos": "Detalle de excesos",
            "comparacion_excesos": "Comparación de excesos",
            "detalle_energia": "Detalle de energía",
        }
        st.markdown("#### Detalles justificativos")
        for clave, titulo in nombres_detalle.items():
            datos = resultado_snapshot.get(clave)
            if isinstance(datos, list) and datos:
                with st.expander(titulo, expanded=False):
                    st.dataframe(
                        pd.DataFrame(datos), hide_index=True,
                        use_container_width=True,
                    )

with tab_evolucion:
    if filtrados.empty:
        st.info("No hay expedientes para construir la evolución.")
    else:
        tipos_disponibles = [
            tipo for tipo in etiquetas_tipo if tipo in filtrados["tipo"].unique()
        ]
        tipo_evolucion = st.radio(
            "Serie a analizar", tipos_disponibles,
            format_func=lambda valor: etiquetas_tipo[valor], horizontal=True,
        )
        granularidad = st.radio(
            "Agrupación", ("Mensual", "Trimestral", "Anual"), horizontal=True
        )
        serie = filtrados[filtrados["tipo"] == tipo_evolucion].copy()
        frecuencias = {"Mensual": "M", "Trimestral": "Q", "Anual": "Y"}
        serie["Periodo"] = serie["ciclo_fin"].dt.to_period(
            frecuencias[granularidad]
        ).astype(str)
        agrupada = serie.groupby("Periodo", as_index=False).agg(
            Facturado=("total_facturado_eur", "sum"),
            Referencia=("total_referencia_eur", "sum"),
            Diferencia=("diferencia_eur", "sum"), Expedientes=("id", "count"),
        )
        grafico_totales = agrupada.melt(
            id_vars="Periodo", value_vars=["Facturado", "Referencia"],
            var_name="Serie", value_name="Importe (€)",
        )
        st.plotly_chart(
            px.line(
                grafico_totales, x="Periodo", y="Importe (€)", color="Serie",
                markers=True, title="Facturado frente a referencia",
            ), use_container_width=True,
        )
        agrupada["Ahorro / sobrecoste (€)"] = -agrupada["Diferencia"]
        agrupada["Acumulado (€)"] = agrupada["Ahorro / sobrecoste (€)"].cumsum()
        figura_impacto = go.Figure()
        figura_impacto.add_bar(
            x=agrupada["Periodo"], y=agrupada["Ahorro / sobrecoste (€)"],
            name="Ahorro (+) / sobrecoste (−)",
            marker_color=[
                "#16a34a" if valor >= 0 else "#dc2626"
                for valor in agrupada["Ahorro / sobrecoste (€)"]
            ],
        )
        figura_impacto.add_scatter(
            x=agrupada["Periodo"], y=agrupada["Acumulado (€)"],
            name="Acumulado", mode="lines+markers", yaxis="y2",
        )
        figura_impacto.update_layout(
            title="Evolución del ahorro y sobrecoste",
            yaxis_title="Impacto del periodo (€)",
            yaxis2=dict(title="Acumulado (€)", overlaying="y", side="right"),
            hovermode="x unified",
        )
        st.plotly_chart(figura_impacto, use_container_width=True)
        st.dataframe(agrupada, hide_index=True, use_container_width=True)

with tab_consumos:
    filas_consumo = []
    base_consumos = filtrados.sort_values("id").drop_duplicates(
        ["cups", "numero_factura", "ciclo_inicio", "ciclo_fin"]
    )
    for fila in base_consumos.itertuples():
        factura_snapshot = cargar_snapshot(int(fila.id)).get("factura", {})
        filas_consumo.append({
            "CUPS": fila.cups, "Factura": fila.numero_factura,
            "Inicio": fila.ciclo_inicio, "Fin": fila.ciclo_fin,
            "Consumo facturado (kWh)": factura_snapshot.get(
                "consumo_total_kwh", 0.0
            ),
            "Energía facturada (€)": factura_snapshot.get("energia", 0.0),
        })
    consumos = pd.DataFrame(filas_consumo)
    if consumos.empty:
        st.info("No hay consumos para los filtros seleccionados.")
    else:
        c1, c2 = st.columns(2)
        c1.metric(
            "Consumo facturado",
            formato_kwh(consumos["Consumo facturado (kWh)"].sum()),
        )
        c2.metric(
            "Coste de energía", formato_euros(consumos["Energía facturada (€)"].sum())
        )
        st.dataframe(consumos, hide_index=True, use_container_width=True)
        st.plotly_chart(
            px.bar(
                consumos, x="Fin", y="Consumo facturado (kWh)", color="CUPS",
                title="Consumo facturado por ciclo",
            ), use_container_width=True,
        )
        st.download_button(
            "Descargar consumos filtrados CSV",
            data=consumos.to_csv(index=False).encode("utf-8-sig"),
            file_name="consumos_facturados_historico.csv", mime="text/csv",
        )
