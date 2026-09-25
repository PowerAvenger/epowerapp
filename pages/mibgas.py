import streamlit as st
import pandas as pd
from html import escape
#import pygwalker as pyg
#from pygwalker.api.streamlit import StreamlitRenderer

import plotly.express as px
from datetime import datetime
from utilidades import generar_menu, init_app
from backend_comun import (
    carga_mibgas,
    carga_total_sheets,
    construir_media_acumulada_prevista,
)
from backend_mibgas import (
    filtrar_por_producto, graficar_qs, graficar_futuros_mibgas, graficar_da_corrido, graficar_da_2026_acumulado, graficar_da_comparado, graficar_medias_acumuladas_comparadas, graficar_ranking_medias_anuales_mibgas,
    construir_comparativa_diaria_mibgas_omie, graficar_comparativa_diaria_mibgas_omie,
    construir_resumen_mensual_omie_mibgas, estimar_omie_mensual_desde_gas,
    ajustar_modelo_lineal_omie_gas, graficar_diagnostico_ratio_gas,
    graficar_modelo_lineal_omie_gas,
    construir_relacion_horaria_omie_mibgas, graficar_mapa_calor_relacion_omie_mibgas,
    graficar_relacion_omie_mibgas_por_mes, graficar_relacion_omie_mibgas_por_hora,
    construir_ratios_maximos_horarios_por_mes,
    descargar_sendeco, obtener_sendeco, graficar_gas_co2,
    obtener_spot_mensual, construir_df_mensual, graf_simul_spot, obtener_spot_diario,
    obtener_mibgas_mensual, graficar_mibgas_mensual_historico, construir_curva_mibgas_2026, graficar_curva_mibgas_2026,
    construir_media_prevista_mibgas_2026_diaria, graficar_media_prevista_mibgas_2026,
    construir_curva_mibgas_mensual_12m, graficar_curva_mibgas_mensual_12m,
    construir_evolucion_media_mibgas_forward_12m, añadir_mibgas_real_12m_alineado_forward,
    graficar_evolucion_media_mibgas_forward
    )
from backend_previsiones import (
    guardar_prevision_omie_en_sesion,
    obtener_prevision_omie_anual,
)


COLOR_HITO_GAS = "#F1948A"
COLOR_28F_GAS = "#FF7575"


def _marcar_evento_gas(figura, inicio, etiqueta, color, fin=None, y=0.98, dentro=False):
    """Marca una fecha precisa o un periodo aproximado sin alterar las series."""
    inicio = pd.Timestamp(inicio)
    if fin is None:
        destacar_28f = inicio == pd.Timestamp("2026-02-28")
        color = COLOR_28F_GAS if destacar_28f else COLOR_HITO_GAS
        figura.add_shape(
            type="line", x0=inicio, x1=inicio, y0=0, y1=1,
            xref="x", yref="paper",
            line=dict(color=color, width=2.5 if destacar_28f else 1.5, dash="dash"),
        )
        x_etiqueta = inicio
    else:
        fin = pd.Timestamp(fin)
        figura.add_shape(
            type="rect", x0=inicio, x1=fin, y0=0, y1=1,
            xref="x", yref="paper",
            line=dict(width=0), fillcolor=color, opacity=0.12,
            layer="below",
        )
        x_etiqueta = inicio + (fin - inicio) / 2
    figura.add_annotation(
        x=x_etiqueta, y=0.68 if dentro else y, xref="x", yref="paper",
        text=f"<b>{etiqueta}</b>" if fin is None and destacar_28f else etiqueta,
        showarrow=False,
        xanchor="center" if fin is not None else "left",
        yanchor="middle" if dentro else "top",
        xshift=0 if fin is not None else 3,
        textangle=0,
        font=dict(
            color=color,
            size=15 if fin is None and inicio in (
                pd.Timestamp("2025-04-28"), pd.Timestamp("2026-02-28")
            ) else 12,
        ),
    )


def _marcar_contexto_historico_gas(figura, fecha_final):
    """Hitos selectivos desde 2021; las franjas indican periodos, no días."""
    _marcar_evento_gas(
        figura, "2022-06-15", "Tope gas", "#B7A7E8",
        fin="2023-03-01", dentro=True,
    )
    figura.add_shape(
        type="rect",
        x0=pd.Timestamp("2026-02-28"),
        x1=pd.Timestamp(fecha_final),
        y0=0, y1=1,
        xref="x", yref="paper",
        line=dict(width=0),
        fillcolor="#F1948A",
        opacity=0.10,
        layer="below",
    )
    eventos = (
        ("2020-03-14", "14 mar · Estado alarma COVID", "#F1948A", None),
        ("2021-01-09", "Filomena", "#79C7E3", None),
        ("2021-10-01", "Crisis gas<br>UE", "#E8B85B", "2022-01-01"),
        ("2022-02-24", "Ucrania", "#F1948A", None),
        ("2022-06-15", "Inicio tope gas", "#B7A7E8", None),
        ("2023-03-01", "Fin efectivo tope gas", "#B7A7E8", None),
        ("2025-04-28", "28A - Apagón", "#9CA3AF", None),
        ("2026-02-28", "28F", "#F1948A", None),
    )
    for inicio, etiqueta, color, fin in eventos:
        _marcar_evento_gas(figura, inicio, etiqueta, color, fin=fin)


def _marcar_contexto_2026_gas(figura):
    """Añade contexto de mercado a la curva diaria de 2026."""
    _marcar_evento_gas(
        figura, "2026-01-12", "Tensión<br>invernal<br>del gas", "#79C7E3",
        fin="2026-02-02", dentro=True,
    )
    _marcar_evento_gas(figura, "2026-02-28", "28F · conflicto Irán", "#F1948A")
    _marcar_evento_gas(
        figura, "2026-04-08", "Alto el<br>fuego<br>temporal", "#79C7E3",
        fin="2026-04-23", dentro=True,
    )
    _marcar_evento_gas(
        figura, "2026-06-17", "Acuerdo<br>provisional<br>de paz", "#79C7E3",
        fin="2026-07-08", dentro=True,
    )
    _marcar_evento_gas(
        figura, "2026-06-17", "Firma acuerdo", "#79C7E3",
    )
    _marcar_evento_gas(
        figura, "2026-07-08", "Ruptura tregua", "#F1948A",
    )
    _marcar_evento_gas(
        figura, "2026-07-27", "Expectativa<br>acuerdo<br>Ormuz", "#79C7E3",
        fin="2026-08-06", dentro=True,
    )
    _marcar_evento_gas(
        figura, "2026-08-06", "Nueva tensión Ormuz", "#F1948A",
    )


DESCRIPCIONES_EVENTOS_GAS = {
    "14 mar 2020 · Estado de alarma": (
        "El 14 de marzo se declaró el estado de alarma en España por la COVID-19. "
        "Las restricciones frenaron la actividad y la demanda energética. "
        "El gas ya cotizaba bajo y siguió débil durante la primavera. "
        "La recuperación de actividad en la segunda mitad de 2020 ayuda a "
        "entender el comienzo de la subida posterior."
    ),
    "9 ene 2021 · Filomena": (
        "Filomena dejó nieve y temperaturas muy bajas en España a principios "
        "de enero. El frío pudo elevar la demanda de calefacción y crear "
        "tensión puntual en el mercado. En la gráfica es un episodio breve: "
        "la tendencia ascendente del gas ya había comenzado durante 2020 "
        "y continuó después del temporal."
    ),
    "Oct–dic 2021 · Crisis gas UE": (
        "La banda destaca la fase más aguda de una subida iniciada en 2020. "
        "Europa afrontó el invierno con poco gas almacenado y compitió por "
        "cargamentos de GNL en un mercado mundial ajustado. También pesó la "
        "incertidumbre sobre el suministro ruso. MIBGAS D+1 alcanzó "
        "183 €/MWh el 21 de diciembre."
    ),
    "24 feb 2022 · Ucrania": (
        "Rusia inició la invasión de Ucrania el 24 de febrero. La dependencia "
        "europea del gas ruso convirtió el suministro en una preocupación "
        "central para el mercado. Los precios incorporaron ese riesgo, "
        "aunque cada oscilación diaria también dependió de la demanda, "
        "los almacenamientos y la disponibilidad de GNL."
    ),
    "15 jun 2022 · Inicio tope gas": (
        "Comenzó el mecanismo ibérico aplicado a la electricidad producida "
        "con gas. La línea marca su puesta en marcha y el inicio de la banda "
        "regulatoria. Conviene distinguirlo del precio de MIBGAS D+1 que "
        "muestra este gráfico: el mecanismo no fijaba un precio máximo "
        "para todo el gas negociado."
    ),
    "2022–23 · Banda tope gas": (
        "La franja va del 15 de junio de 2022 al 1 de marzo de 2023, "
        "fecha señalada aquí como fin efectivo. Sirve para comparar la "
        "evolución del gas con el periodo de aplicación práctica del "
        "mecanismo ibérico en el mercado eléctrico. No representa un "
        "límite directo al precio de MIBGAS D+1."
    ),
    "1 mar 2023 · Fin tope gas": (
        "Esta línea señala el fin efectivo del ajuste que hemos elegido "
        "para la gráfica. El último uso práctico relevante había sido en "
        "febrero de 2023. La fecha permite cerrar visualmente la banda, "
        "pero no debe confundirse con la fecha de finalización legal "
        "del mecanismo ibérico."
    ),
    "28 abr 2025 · Apagón": (
        "El 28A se produjo el gran apagón eléctrico en España. Lo marcamos "
        "como referencia del sistema energético y para facilitar la "
        "lectura temporal de la serie. El precio del gas responde a un "
        "mercado más amplio; que un movimiento coincida con esta fecha "
        "no demuestra que el apagón lo causara."
    ),
    "12 ene–2 feb 2026 · Tensión invernal": (
        "Entre mediados de enero y el 2 de febrero, el gas subió y después "
        "retrocedió. La banda identifica esa fase invernal anterior al 28F. "
        "El frío, la demanda y las expectativas de suministro son factores "
        "a considerar; no la presentamos como consecuencia de un único "
        "acontecimiento geopolítico."
    ),
    "28 feb 2026 · Conflicto Irán": (
        "El 28F marca el comienzo del conflicto con Irán y un cambio en "
        "el riesgo percibido para el gas y el GNL. El transporte por Ormuz "
        "y la oferta del Golfo pasan a ser claves para Europa. La línea "
        "sirve de referencia temporal: no atribuye automáticamente "
        "todos los movimientos posteriores del precio a la guerra."
    ),
    "28F–actualidad · Banda histórica": (
        "La banda tenue va del 28 de febrero hasta el último dato "
        "disponible del histórico. Permite reconocer de un vistazo el "
        "periodo posterior al inicio del conflicto y compararlo con los "
        "años anteriores. Es una ayuda visual de contexto, no una "
        "afirmación de causalidad para toda la franja."
    ),
    "8–22 abr 2026 · Alto el fuego": (
        "La banda recoge el alto el fuego temporal de abril. Un posible "
        "alivio de las tensiones de suministro puede influir en las "
        "expectativas del mercado. Aun así, el precio diario siguió "
        "sujeto a otros factores de oferta y demanda. Por eso se marca "
        "un periodo y no una caída causada por un solo día."
    ),
    "17 jun 2026 · Firma acuerdo": (
        "La línea señala la firma del acuerdo provisional de paz entre "
        "Estados Unidos e Irán. El anuncio abrió expectativas de una "
        "normalización gradual del tránsito por Ormuz. Es el punto "
        "inicial de la banda de acuerdo provisional; la recuperación "
        "efectiva de los flujos de GNL seguía siendo incierta."
    ),
    "17 jun–8 jul 2026 · Acuerdo de paz": (
        "La banda comienza con la firma del acuerdo provisional y llega "
        "hasta el 8 de julio. Representa una fase de expectativas de "
        "distensión y posible mejora del tránsito energético. La tregua "
        "no garantizaba una recuperación inmediata del suministro, y "
        "la gráfica muestra movimientos diarios en ambos sentidos."
    ),
    "8 jul 2026 · Ruptura tregua": (
        "La ruptura de la tregua volvió a elevar el riesgo de "
        "interrupciones en Ormuz y en los flujos energéticos de la "
        "región. La línea se sitúa junto al comienzo de una nueva "
        "escalada del precio del gas. Señala un contexto relevante, "
        "sin atribuirle por sí sola toda la subida posterior."
    ),
    "27 jul–5 ago 2026 · Expectativa Ormuz": (
        "A finales de julio volvió a hablarse de un posible acuerdo "
        "sobre el tránsito por Ormuz. La banda coincide con una breve "
        "desescalada de precios que llega a primeros de agosto. "
        "La expectativa no equivalía a un acuerdo cerrado ni "
        "aseguraba la normalización inmediata de los suministros."
    ),
    "6 ago 2026 · Nueva tensión Ormuz": (
        "El 6 de agosto se marca el retorno de la tensión en torno "
        "al estrecho de Ormuz. El riesgo para el tráfico de GNL y "
        "la necesidad europea de seguir comprando gas antes del "
        "invierno coincidieron con una subida persistente. La línea "
        "indica el inicio de esa fase, no una explicación única."
    ),
}



if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')

generar_menu()
init_app()

# Gas solo necesita las columnas históricas de fecha y SPOT. Evitamos
# init_app_index(), que además carga componentes y recalcula indexados.
if "df_sheets" not in st.session_state:
    if "df_sheets_old" not in st.session_state:
        carga_total_sheets()
    st.session_state.df_sheets = st.session_state.df_sheets_old.copy()

st.sidebar.header('⚡ Gas & Furious ⚡')
zona_mensajes = st.sidebar.empty()

df_mibgas_completo = carga_mibgas()
# Gas & Furious mantiene el horizonte operativo original (2024 en adelante),
# aunque el Sheets compartido conserve el histórico completo desde 2018.
df_mibgas_base = df_mibgas_completo.loc[
    df_mibgas_completo["Trading day"] >= pd.Timestamp("2024-01-01")
].copy()
ultima_fecha_mibgas = df_mibgas_base['Trading day'].max()
st.sidebar.info(f'Última fecha disponible: {ultima_fecha_mibgas.strftime("%d.%m.%Y")}')
if st.sidebar.button('Actualizar datos', use_container_width=True):
    carga_mibgas.clear()
    st.session_state.pop("gas_analisis_omie_mibgas", None)
    st.session_state.pop("gas_grafico_co2", None)
    st.rerun()

# FUTUROS M MESES
productos_m = ['GMAES', 'GMES_M+2', 'GMES_M+3', 'GMES_M+4', 'GMES_M+5', 'GMES_M+6']
dfs_m = [filtrar_por_producto(df_mibgas_base, prod) for prod in productos_m]
df_mg_m = pd.concat(dfs_m, ignore_index=True)
graf_ms = graficar_futuros_mibgas(df_mg_m, tipo="M")

# FUTUROS Q TRIMESTRES
productos_q = ['GQES_Q+1', 'GQES_Q+2', 'GQES_Q+3', 'GQES_Q+4']
dfs_q = [filtrar_por_producto(df_mibgas_base, prod) for prod in productos_q]
df_mg_q = pd.concat(dfs_q, ignore_index=True)
#graf_qs = graficar_qs(df_mg_q)
graf_qs = graficar_futuros_mibgas(df_mg_q, tipo="Q")

# FUTUROS Y AÑOS
productos_y = ['GYES_Y+1', 'GYES_Y+2', 'GYES_Y+3', 'GQES_Y+4']
dfs_y = [filtrar_por_producto(df_mibgas_base, prod) for prod in productos_y]
df_mg_y = pd.concat(dfs_y, ignore_index=True)
#graf_ys = graficar_qs(df_mg_y)
graf_ys = graficar_futuros_mibgas(df_mg_y, tipo="Y")


df_mg_da = filtrar_por_producto(df_mibgas_base, 'GDAES_D+1')
df_mg_da_historico = filtrar_por_producto(
    df_mibgas_completo,
    'GDAES_D+1',
)
#print('mibgas da')
#print(df_mg_da)

df_mibgas_mensual = obtener_mibgas_mensual(df_mg_da)
graf_mibgas_mensual_historico = graficar_mibgas_mensual_historico(df_mibgas_mensual)
df_curva_mibgas_2026 = construir_curva_mibgas_2026(df_mibgas_mensual, df_mg_m, df_mg_q)
df_media_acumulada_prevista_2026 = construir_media_acumulada_prevista(
    datos_diarios_reales=df_mg_da,
    curva_mensual_prevista=df_curva_mibgas_2026,
    año=2026,
    col_fecha_real="fecha_entrega",
    col_valor_real="precio_gas",
)
precio_medio_mibgas_2026 = round(df_curva_mibgas_2026["precio"].mean(), 2)

df_medias = df_mg_da.groupby("año_entrega", as_index=False)["precio_gas"].mean()
df_medias["precio_gas"] = df_medias["precio_gas"].round(2)
df_medias["precio_str"] = df_medias["precio_gas"].astype(str).str.replace('.', ',')
gas_media_2026 = df_medias.loc[
    df_medias["año_entrega"] == 2026,
    "precio_gas"
]
gas_media_2026 = float(gas_media_2026.iloc[0]) if not gas_media_2026.empty else None
print("GAS media 2026:", gas_media_2026)

graf_da_comparado = graficar_da_comparado(df_mg_da)



df_spot_mensual = obtener_spot_mensual(st.session_state.df_sheets)
print (df_spot_mensual)

# El SPOT mensual se etiqueta con el fin de mes. En el mes en curso esa
# fecha todavia no existe en la serie diaria de MIBGAS, por lo que un cruce
# por fecha exacta descartaba visualmente el punto mensual (p. ej. Sep-26).
# Cruzamos las dos series ya agregadas por periodo mensual. Asi se conserva
# exactamente un punto por cada mes comun, incluido el mes en curso.
df_mibgas_simulador = df_mibgas_mensual.copy()
df_spot_simulador = df_spot_mensual.copy()
df_mibgas_simulador['_periodo_mes'] = pd.to_datetime(
    df_mibgas_simulador['fecha_entrega']
).dt.to_period('M')
df_spot_simulador['_periodo_mes'] = pd.to_datetime(
    df_spot_simulador['fecha_entrega']
).dt.to_period('M')
df_total_data = df_mibgas_simulador.merge(
    df_spot_simulador[['_periodo_mes', 'spot']],
    on='_periodo_mes',
    how='left',
).drop(columns='_periodo_mes')

df_mensual = construir_df_mensual(df_total_data)


#valor_mibgas_previsto = 40
df_spot_diario = obtener_spot_diario(st.session_state.df_sheets)
print (df_spot_diario)
omie_media_2026 = round(df_spot_diario.loc[df_spot_diario["fecha"].dt.year == 2026, "spot"].mean(),2)
print(omie_media_2026)
df_comparativa_diaria_historica = construir_comparativa_diaria_mibgas_omie(
    df_mg_da,
    df_spot_diario,
    año=None,
)
df_resumen_mensual_omie_mibgas = construir_resumen_mensual_omie_mibgas(
    df_comparativa_diaria_historica
)
df_validacion = pd.DataFrame({
    'año': [2024, 2025, 2021, 2019, 2018],
    'precio_gas': [35.95,34.72, 47.3, 15.27, 28.95],   # MIBGAS real
    'omie': [63.03,65.28, 111.93, 47.68, 57.29]          # SPOT real
})
df_validacion = pd.DataFrame({
    'año': [2024, 2025, 2021, 2018],
    'precio_gas': [35.95, 34.72, 47.3, 28.95],   # MIBGAS real
    'omie': [63.03, 65.28, 111.93, 57.29]        # SPOT real
})

colores_precios = {'precio_gas': 'goldenrod', '': 'darkred', 'precio_6.1': '#1C83E1'}






#LAYOUT++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

zona_mensajes.empty()

seccion_gas = st.segmented_control(
    "Sección",
    [
        'Históricos', 'Futuros', 'Previsión anual', 'OMIE vs MIBGAS',
        'Comparador', 'CO2', 'Simulador',
    ],
    default='Históricos',
    key='seccion_gas',
)

if seccion_gas == 'Históricos':
    with st.container():
        col1, col2 = st.columns([.82, .18])
        with col2:
            st.plotly_chart(
                graficar_ranking_medias_anuales_mibgas(
                    df_mg_da_historico, compacto=True
                ),
                use_container_width=True,
            )
            mostrar_degradado = st.checkbox(
                "Degradado por precio", value=True,
                key="gas_historicos_degradado",
            )
            escala_gas = "umbrales"
            if mostrar_degradado:
                escala_elegida = st.selectbox(
                    "Escala de colores",
                    ("Umbrales 20–100", "Escala anterior"),
                    key="gas_historicos_escala",
                )
                escala_gas = (
                    "umbrales" if escala_elegida == "Umbrales 20–100"
                    else "anterior"
                )
            mostrar_eventos = st.checkbox(
                "Mostrar eventos", key="gas_historicos_eventos"
            )
            if mostrar_eventos:
                st.caption("Hitos de contexto: la coincidencia temporal no implica causalidad.")
        with col1:
            graf_da_corrido = graficar_da_corrido(
                df_mg_da_historico, degradado=mostrar_degradado,
                escala=escala_gas,
            )
            if mostrar_eventos:
                _marcar_contexto_historico_gas(
                    graf_da_corrido, df_mg_da_historico["fecha_entrega"].max()
                )
            st.write(graf_da_corrido)

        col1_graf2, col2_metricas = st.columns([.82, .18])
        with col1_graf2:
            precio_maximo_historico = pd.to_numeric(
                df_mg_da_historico.loc[
                    df_mg_da_historico["fecha_entrega"].dt.year >= 2018,
                    "precio_gas",
                ],
                errors="coerce",
            ).max()
            graf_da_2026_acumulado = graficar_da_2026_acumulado(
                df_mg_da,
                degradado=mostrar_degradado,
                precio_maximo_escala=precio_maximo_historico,
                escala=escala_gas,
            )
            if mostrar_eventos:
                _marcar_contexto_2026_gas(graf_da_2026_acumulado)
            st.write(graf_da_2026_acumulado)
        with col2_metricas:
            datos_2026 = df_mg_da.loc[
                df_mg_da["fecha_entrega"].dt.year == 2026,
                ["fecha_entrega", "precio_gas"],
            ].dropna(subset=["precio_gas"]).sort_values("fecha_entrega")
            if not datos_2026.empty:
                ultimo_dato = datos_2026.iloc[-1]
                col_media, col_ultimo = st.columns(2)
                with col_media:
                    st.metric(
                        f"Media anual {ultimo_dato['fecha_entrega'].year}",
                        f"{datos_2026['precio_gas'].mean():.2f}".replace(".", ","),
                    )
                with col_ultimo:
                    st.metric(
                        "Precio último día",
                        f"{ultimo_dato['precio_gas']:.2f}".replace(".", ","),
                    )
                st.caption(
                    f"Último dato: {ultimo_dato['fecha_entrega']:%d/%m/%Y} - Unidades en €/MWh"
                )
            if mostrar_eventos:
                evento_seleccionado = st.selectbox(
                    "Eventos y bandas",
                    tuple(DESCRIPCIONES_EVENTOS_GAS),
                    key="gas_evento_descripcion",
                )
                st.markdown(
                    '<div style="background:rgba(70,140,200,0.14);'
                    'border:1px solid rgba(130,180,230,0.28);'
                    'border-radius:10px;padding:12px 14px;line-height:1.5">'
                    f'{escape(DESCRIPCIONES_EVENTOS_GAS[evento_seleccionado])}'
                    '</div>',
                    unsafe_allow_html=True,
                )


if seccion_gas == 'OMIE vs MIBGAS':
    clave_analisis = "gas_analisis_omie_mibgas"
    if clave_analisis not in st.session_state:
        with st.spinner("Preparando análisis OMIE vs MIBGAS..."):
            try:
                comparativa_diaria = construir_comparativa_diaria_mibgas_omie(
                    df_mg_da, df_spot_diario
                )
                relacion_horaria = construir_relacion_horaria_omie_mibgas(
                    df_mg_da, st.session_state.df_sheets
                )
                graf_relacion_mes, relacion_mes = (
                    graficar_relacion_omie_mibgas_por_mes(relacion_horaria)
                )
                graf_relacion_hora, relacion_hora = (
                    graficar_relacion_omie_mibgas_por_hora(relacion_horaria)
                )
                st.session_state[clave_analisis] = {
                    "comparativa_diaria": comparativa_diaria,
                    "graf_comparativa": graficar_comparativa_diaria_mibgas_omie(
                        comparativa_diaria
                    ),
                    "relacion_horaria": relacion_horaria,
                    "graf_mapa": graficar_mapa_calor_relacion_omie_mibgas(
                        relacion_horaria
                    ),
                    "graf_mes": graf_relacion_mes,
                    "relacion_mes": relacion_mes,
                    "graf_hora": graf_relacion_hora,
                    "relacion_hora": relacion_hora,
                    "ratios_maximos": construir_ratios_maximos_horarios_por_mes(
                        relacion_horaria
                    ),
                }
            except Exception as exc:
                st.session_state.pop(clave_analisis, None)
                st.error(f"No se pudo preparar el análisis: {exc}")

    analisis = st.session_state.get(clave_analisis)
    if analisis is not None:
        st.plotly_chart(analisis["graf_comparativa"], use_container_width=True)
        with st.expander("Ver tabla diaria MIBGAS D+1 vs OMIE"):
            st.dataframe(
                analisis["comparativa_diaria"],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
                    "mibgas_d1": st.column_config.NumberColumn(
                        "MIBGAS D+1 (€/MWh)", format="%.2f"
                    ),
                    "omie": st.column_config.NumberColumn("OMIE (€/MWh)", format="%.2f"),
                    "rel_omie_gas": st.column_config.NumberColumn(
                        "Rel. OMIE/Gas", format="%.4f"
                    ),
                },
            )

        col_mapa, col_metricas = st.columns([.85, .15])
        with col_mapa:
            st.plotly_chart(analisis["graf_mapa"], use_container_width=True)
        with col_metricas:
            relacion_horaria = analisis["relacion_horaria"]
            if not relacion_horaria.empty:
                fila_max = relacion_horaria.loc[
                    relacion_horaria["rel_omie_gas"].idxmax()
                ]
                st.metric("Máx. OMIE/Gas", f"{fila_max['rel_omie_gas']:.2f}")
                st.metric("Fecha del máximo", fila_max["fecha"].strftime("%d/%m/%Y"))
                st.metric("Hora", f"{int(fila_max['hora']):02d}:00")
                st.metric("OMIE", f"{fila_max['omie']:.2f} €/MWh")
                st.metric("MIBGAS D+1", f"{fila_max['mibgas_d1']:.2f} €/MWh")
            else:
                st.info("No hay datos horarios coincidentes para 2026.")

        col_rel_mes, col_rel_hora = st.columns(2)
        col_rel_mes.plotly_chart(analisis["graf_mes"], use_container_width=True)
        col_rel_hora.plotly_chart(analisis["graf_hora"], use_container_width=True)

        st.subheader("Ratios máximos horarios OMIE/MIBGAS por mes")
        st.caption("Máximo ratio observado en cada hora dentro de cada mes · año 2026")
        ratios = analisis["ratios_maximos"]
        if ratios.empty:
            st.info("No hay datos horarios coincidentes para calcular los máximos.")
        else:
            columnas_horarias = [col for col in ratios.columns if col != "Mes"]

            def resaltar_maximos_horarios(fila):
                estilos = pd.Series("", index=fila.index)
                valores = pd.to_numeric(fila[columnas_horarias], errors="coerce")
                if valores.notna().any():
                    maximo = valores.max()
                    estilos.loc[columnas_horarias] = valores.eq(maximo).map(
                        lambda es_maximo: (
                            "background-color: #FFD700; color: #111111; font-weight: 700"
                            if es_maximo else ""
                        )
                    )
                return estilos

            st.dataframe(
                ratios.style.apply(resaltar_maximos_horarios, axis=1).format(
                    {col: "{:.2f}" for col in columnas_horarias}, na_rep=""
                ),
                hide_index=True,
                use_container_width=True,
            )


if seccion_gas == 'Comparador':
    col_graf_comparador, col_selector_comparador, col_ranking = st.columns(
        [.65, .06, .29]
    )
    with col_selector_comparador:
        st.markdown("**Años**")
        años_disponibles = sorted(
            df_mg_da_historico["fecha_entrega"]
            .dropna()
            .dt.year
            .astype(int)
            .unique()
            .tolist(),
            reverse=True,
        )
        años_seleccionados = [
            año
            for año in años_disponibles
            if st.checkbox(
                str(año),
                value=(año == 2026),
                key=f"comparador_mibgas_{año}",
            )
        ]
    with col_graf_comparador:
        if años_seleccionados:
            años_titulo = ", ".join(map(str, años_seleccionados))
            graf_comparador = graficar_da_comparado(
                df_mg_da_historico,
                años=años_seleccionados,
                titulo=f"Comparación anual del precio del gas: {años_titulo}",
            )
            st.plotly_chart(graf_comparador, use_container_width=True)
            graf_medias_acumuladas = graficar_medias_acumuladas_comparadas(
                df_mg_da_historico,
                años=años_seleccionados,
                df_prevision_actual=df_media_acumulada_prevista_2026,
            )
            st.plotly_chart(
                graf_medias_acumuladas,
                use_container_width=True,
            )
        else:
            st.info("Selecciona al menos un año para mostrar la comparación.")
    with col_ranking:
        graf_ranking_mibgas = graficar_ranking_medias_anuales_mibgas(
            df_mg_da_historico
        )
        st.plotly_chart(graf_ranking_mibgas, use_container_width=True)
    st.plotly_chart(graf_mibgas_mensual_historico, use_container_width=True)


if seccion_gas == 'Futuros':
    with st.container():
        col1,col2 = st.columns([.9,.1]) 
        with col1:
            st.write(graf_ms)
            st.write(graf_qs)
            st.write(graf_ys) 
        
        



if seccion_gas == 'CO2':
    clave_co2 = "gas_grafico_co2"
    if clave_co2 not in st.session_state:
        with st.spinner("Cargando datos SENDECO..."):
            try:
                año_actual = datetime.now().year
                descargar_sendeco(año_actual)
                df_sendeco = obtener_sendeco()
                df_total_data_gas_co2 = df_mg_da.merge(
                    df_sendeco, on="fecha_entrega", how="left"
                )
                df_total_data_gas_co2["co2_€ton"] = (
                    df_total_data_gas_co2["co2_€ton"].ffill().bfill()
                )
                df_total_data_gas_co2["co2"] = (
                    df_total_data_gas_co2["co2_€ton"] * .35
                ).round(2)
                df_total_data_gas_co2["año"] = (
                    df_total_data_gas_co2["fecha_entrega"].dt.year
                )
                df_total_data_gas_co2["día_del_año"] = (
                    df_total_data_gas_co2["fecha_entrega"].dt.dayofyear
                )
                st.session_state[clave_co2] = graficar_gas_co2(
                    df_total_data_gas_co2
                )
            except Exception as exc:
                st.session_state.pop(clave_co2, None)
                st.error(f"No se pudieron cargar los datos de CO2: {exc}")
    if clave_co2 in st.session_state:
        st.write(st.session_state[clave_co2])



if seccion_gas == 'Simulador':

    col1, col2 = st.columns([.25,.75])
    with col1:
        st.success('Bienvenido a la simulación baratera del precio medio OMIE anual a partir de MIBGAS')

        st.info('🟡 Punto de simulación sobre curva azul')

        # Fila 1: simulación directa MIBGAS -> OMIE.
        col11, col12 = st.columns(2)
        with col11:
            mibgas_simul_input = st.number_input(
                'Introduce el valor previsto MIBGAS 2026',
                min_value=26,
                max_value=70,
                value=40,
                key='mibgas_simul',
            )

        # Se genera despues del widget para que el punto de simulacion use
        # siempre el mismo valor MIBGAS que se muestra en el input.
        graf_hist, simul_spot, simul_gas = graf_simul_spot(
            df_mensual,
            df_validacion,
            float(mibgas_simul_input),
            omie_media_2026=omie_media_2026,
            gas_media_2026=gas_media_2026,
            omie_previsto=st.session_state.get("precio_omie_previsto"),
            gas_previsto=precio_medio_mibgas_2026,
        )
        with col12:
            st.metric('Valor de OMIE 2026 esperado', simul_spot)

        # Fila 2: simulación inversa OMIE -> MIBGAS a partir de la curva
        # híbrida calculada en Simulindex.
        precio_omie_previsto = st.session_state.get("precio_omie_previsto")
        if precio_omie_previsto is not None:
            col21, col22 = st.columns(2)
            with col21:
                st.metric('Valor OMIE previsto s/OMIP', precio_omie_previsto)
            with col22:
                if simul_gas is not None:
                    st.metric('Valor de gas 2026 esperado', simul_gas)
        else:
            st.caption('La previsión OMIE de Simulindex no está disponible en esta sesión.')
            if st.button('Calcular previsión OMIE 2026', use_container_width=True):
                with st.spinner('Calculando la curva híbrida OMIE-OMIP...'):
                    prevision_omie = obtener_prevision_omie_anual(df_spot_diario)
                    guardar_prevision_omie_en_sesion(prevision_omie)
                st.rerun()

        st.info(':green[◆] Punto según valores actuales OMIE/MIBGAS')

        # Fila 3: valores medios observados en el año en curso.
        col31, col32 = st.columns(2)
        with col31:
            st.metric('Valor medio OMIE 2026 €/MWh', omie_media_2026)
        with col32:
            st.metric("Precio medio gas 2026 (€/MWh)", df_medias.loc[df_medias["año_entrega"] == 2026, "precio_str"].values[0])

        st.info('🟧 Punto según valores futuros')

        # Fila 4: previsiones anuales procedentes de Simulindex y MIBGAS.
        col41, col42 = st.columns(2)
        with col41:
            st.metric(
                'Valor OMIE previsto s/OMIP',
                precio_omie_previsto if precio_omie_previsto is not None else 'No disponible'
            )
        with col42:
            st.metric('Valor MIBGAS previsto (€/MWh)', precio_medio_mibgas_2026)
            
    with col2:        
        st.write(graf_hist)

        #renderer = StreamlitRenderer(df_mensual)
        #renderer.explorer()

    st.divider()
    st.subheader("Estimación mensual OMIE a partir de MIBGAS")
    st.caption(
        "La relación mensual es la media de los ratios diarios "
        "OMIE/MIBGAS. La estimación usa únicamente el mismo mes de años "
        "anteriores."
    )
    meses_estimacion = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
        5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
        9: "Septiembre", 10: "Octubre", 11: "Noviembre",
        12: "Diciembre",
    }
    col_simul_mensual, col_hist_mensual = st.columns([.32, .68])
    with col_simul_mensual:
        mes_objetivo = st.selectbox(
            "Mes objetivo",
            options=list(meses_estimacion),
            index=7,
            format_func=lambda mes: meses_estimacion[mes],
            key="gas_mes_objetivo_ratio",
        )
        año_objetivo = st.number_input(
            "Año objetivo",
            min_value=2025,
            max_value=2035,
            value=2026,
            step=1,
            key="gas_año_objetivo_ratio",
        )
        gas_mensual_simulado = st.number_input(
            "MIBGAS mensual previsto (€/MWh)",
            min_value=0.01,
            max_value=200.0,
            value=40.0,
            step=0.5,
            format="%.2f",
            key="gas_mensual_simulado_ratio",
        )
        modelo_lineal_mensual = ajustar_modelo_lineal_omie_gas(
            df_resumen_mensual_omie_mibgas,
            gas_mensual_simulado,
        )
        modelo_lineal_12m = ajustar_modelo_lineal_omie_gas(
            df_resumen_mensual_omie_mibgas,
            gas_mensual_simulado,
            ultimos_meses=12,
        )
        estimacion_mensual = estimar_omie_mensual_desde_gas(
            df_resumen_mensual_omie_mibgas,
            gas_mensual_simulado,
            mes_objetivo,
            año_objetivo,
        )
        if estimacion_mensual:
            st.metric(
                "OMIE mensual estimado",
                f"{estimacion_mensual['omie_estimado']:.2f} €/MWh",
            )
            st.metric(
                "Ratio histórico medio",
                f"{estimacion_mensual['ratio_medio']:.3f}",
            )
            st.metric(
                "Rango histórico resultante",
                (
                    f"{estimacion_mensual['omie_minimo']:.2f} – "
                    f"{estimacion_mensual['omie_maximo']:.2f} €/MWh"
                ),
            )
            st.caption(
                "Años utilizados: "
                + ", ".join(
                    str(año)
                    for año in estimacion_mensual["años_utilizados"]
                )
            )
        else:
            años_disponibles_mes = (
                df_resumen_mensual_omie_mibgas.loc[
                    df_resumen_mensual_omie_mibgas["mes"] == mes_objetivo,
                    "año",
                ]
                .astype(int)
                .tolist()
            )
            st.warning(
                "No hay ratios históricos anteriores disponibles para ese mes. "
                "Años encontrados: "
                + (
                    ", ".join(str(año) for año in años_disponibles_mes)
                    if años_disponibles_mes
                    else "ninguno"
                )
            )
        if modelo_lineal_mensual:
            st.markdown("#### Corrección por nivel del gas")
            st.metric(
                "OMIE estimado · modelo lineal",
                f"{modelo_lineal_mensual['omie_estimado']:.2f} €/MWh",
            )
            st.metric(
                "Banda residual orientativa",
                (
                    f"{modelo_lineal_mensual['omie_inferior_orientativo']:.2f}"
                    " – "
                    f"{modelo_lineal_mensual['omie_superior_orientativo']:.2f}"
                    " €/MWh"
                ),
            )
            st.caption(
                f"R²: {modelo_lineal_mensual['r2']:.3f} · "
                f"{modelo_lineal_mensual['num_observaciones']} meses · "
                "Correlación gas-ratio: "
                f"{modelo_lineal_mensual['correlacion_ratio_gas']:.3f}"
            )
        if modelo_lineal_12m:
            st.markdown("#### Modelo últimos 12 meses")
            st.metric(
                "OMIE estimado · 12 meses",
                f"{modelo_lineal_12m['omie_estimado']:.2f} €/MWh",
            )
            st.metric(
                "Banda residual · 12 meses",
                (
                    f"{modelo_lineal_12m['omie_inferior_orientativo']:.2f}"
                    " – "
                    f"{modelo_lineal_12m['omie_superior_orientativo']:.2f}"
                    " €/MWh"
                ),
            )
            st.caption(
                f"R²: {modelo_lineal_12m['r2']:.3f} · "
                f"{modelo_lineal_12m['num_observaciones']} meses · "
                "Correlación gas-ratio: "
                f"{modelo_lineal_12m['correlacion_ratio_gas']:.3f}"
            )

    with col_hist_mensual:
        if estimacion_mensual:
            detalle_ratio_mes = estimacion_mensual["detalle"].copy()
            detalle_ratio_mes["año"] = detalle_ratio_mes["año"].astype(str)
            graf_ratio_mes = px.bar(
                detalle_ratio_mes,
                x="año",
                y="ratio_medio_diario",
                text_auto=".3f",
                labels={
                    "año": "Año",
                    "ratio_medio_diario": "Media ratios diarios OMIE/Gas",
                },
                title=(
                    f"Ratio histórico de {meses_estimacion[mes_objetivo]}"
                ),
                color_discrete_sequence=["#4C78A8"],
            )
            graf_ratio_mes.add_hline(
                y=estimacion_mensual["ratio_medio"],
                line_dash="dot",
                line_color="#E74C3C",
                annotation_text="Media histórica",
            )
            graf_ratio_mes.update_layout(
                title={"x": 0.5, "xanchor": "center"},
                showlegend=False,
                height=430,
            )
            st.plotly_chart(graf_ratio_mes, use_container_width=True)

    if modelo_lineal_mensual:
        col_diag_ratio, col_modelo_lineal = st.columns(2)
        with col_diag_ratio:
            st.plotly_chart(
                graficar_diagnostico_ratio_gas(
                    df_resumen_mensual_omie_mibgas
                ),
                use_container_width=True,
            )
        with col_modelo_lineal:
            st.plotly_chart(
                graficar_modelo_lineal_omie_gas(
                    modelo_lineal_mensual,
                    gas_mensual_simulado,
                    etiqueta_objetivo=(
                        f"{meses_estimacion[mes_objetivo]} "
                        f"{int(año_objetivo)}"
                    ),
                    destacar_objetivo=True,
                    mes_objetivo=mes_objetivo,
                ),
                use_container_width=True,
            )
            if modelo_lineal_12m:
                st.plotly_chart(
                    graficar_modelo_lineal_omie_gas(
                        modelo_lineal_12m,
                        gas_mensual_simulado,
                        titulo=(
                            "Modelo lineal OMIE vs MIBGAS · "
                            "últimos 12 meses"
                        ),
                        etiqueta_objetivo=(
                            f"{meses_estimacion[mes_objetivo]} "
                            f"{int(año_objetivo)}"
                        ),
                    ),
                    use_container_width=True,
                )

    with st.expander("Ver tabla mensual OMIE, MIBGAS y ratios diarios"):
        st.dataframe(
            df_resumen_mensual_omie_mibgas,
            hide_index=True,
            use_container_width=True,
            column_config={
                "año": st.column_config.NumberColumn("Año", format="%d"),
                "mes": st.column_config.NumberColumn("Mes", format="%d"),
                "fecha_mes": st.column_config.DateColumn(
                    "Periodo", format="MMM YYYY"
                ),
                "mibgas_medio": st.column_config.NumberColumn(
                    "MIBGAS medio (€/MWh)", format="%.2f"
                ),
                "omie_medio": st.column_config.NumberColumn(
                    "OMIE medio (€/MWh)", format="%.2f"
                ),
                "ratio_medio_diario": st.column_config.NumberColumn(
                    "Media ratios diarios", format="%.4f"
                ),
                "dias_con_datos": st.column_config.NumberColumn(
                    "Días", format="%d"
                ),
            },
        )


if seccion_gas == 'Previsión anual':
    graf_mibgas_2026 = graficar_curva_mibgas_2026(
        df_curva_mibgas_2026, precio_medio_mibgas_2026
    )
    df_media_mibgas_2026 = construir_media_prevista_mibgas_2026_diaria(
        df_mg_da, df_mg_m, df_mg_q
    )
    graf_media_mibgas_2026 = graficar_media_prevista_mibgas_2026(
        df_media_mibgas_2026
    )
    df_mibgas_año_movil = construir_curva_mibgas_mensual_12m(
        df_mg_m, df_mg_q
    )
    num_meses_mibgas_año_movil = df_mibgas_año_movil["precio"].notna().sum()
    precio_medio_mibgas_año_movil = round(
        df_mibgas_año_movil["precio"].mean(), 2
    )
    graf_mibgas_año_movil = graficar_curva_mibgas_mensual_12m(
        df_mibgas_año_movil, precio_medio_mibgas_año_movil
    )
    df_evol_media_mibgas_forward = construir_evolucion_media_mibgas_forward_12m(
        df_mg_m=df_mg_m,
        df_mg_q=df_mg_q,
        fecha_inicio="01.01.2024",
    )
    df_evol_media_mibgas_forward = añadir_mibgas_real_12m_alineado_forward(
        df_evol=df_evol_media_mibgas_forward,
        df_mg_da=df_mg_da,
        col_fecha_evol="Fecha",
        col_fecha_real="fecha_entrega",
        col_real="precio_gas",
        meses=12,
        exigir_ventana_completa=True,
    )
    graf_evol_media_mibgas_forward = graficar_evolucion_media_mibgas_forward(
        df_evol_media_mibgas_forward
    )
    col1, col2 = st.columns(2)
    with col1:
        st.info('Previsión MIBGAS 2026 combinando medias mensuales D+1 y futuros mensuales/trimestrales.', icon="ℹ️")
        st.write(graf_mibgas_2026)
        st.info('Evolucion diaria de la media MIBGAS prevista 2026 en base a D+1 real y futuros combinados.')
        st.write(graf_media_mibgas_2026)

    with col2:
        st.info('Curva MIBGAS 12 meses desde M+1 con futuros mensuales y fallback trimestral.', icon="ℹ️")
        if num_meses_mibgas_año_movil < 12:
            st.warning(
                f'La curva año móvil tiene {num_meses_mibgas_año_movil}/12 meses con precio disponible. '
                'Se muestra la media de los meses disponibles.',
                icon="⚠️"
            )
        st.write(graf_mibgas_año_movil)
        st.info('Evolución de MIBGAS forward 12M desde M+1. Comparativa con MIBGAS D+1 real alineado.', icon="ℹ️")
        st.plotly_chart(graf_evol_media_mibgas_forward, use_container_width=True)
