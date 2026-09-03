import streamlit as st
import datetime
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go


from utilidades import (
    generar_menu,
    init_app_json_escalacv, init_app, init_app_index
)

from backend_escalacv import (
    leer_json, diarios_totales, diarios, mensuales, horarios, medias_horarias, evolucion_mensual, meses_español,
    obtener_df_scatter_mensual, graficar_scatter_combo, obtener_puntos_anuales, graficar_simulacion_cuadratica, graficar_bandas_ssaa,
    mapa_calor_mes, mapa_calor_mes_gradual, graficar_media_acumulada_periodo,
    calcular_spreads_diarios
)
from backend_comun import aplicar_estilo, construir_media_acumulada_prevista
from backend_spot import media_spot
from formato_es import formato_numero_es
from backend_previsiones import (
    guardar_prevision_omie_en_sesion,
    obtener_prevision_omie_anual,
)

if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')

generar_menu()

fecha_hoy=datetime.today().date()
num_mes_actual = fecha_hoy.month
mes_actual = meses_español[num_mes_actual]

if 'año_seleccionado_esc' not in st.session_state:
    st.session_state.año_seleccionado_esc = 2026
    st.session_state.año_anterior_esc = 2026
if 'año_seleccionado_comp' not in st.session_state:
    st.session_state.año_seleccionado_comp = 2025
    st.session_state.año_anterior_comp = 2025

if 'mes_seleccionado_esc' not in st.session_state:
    st.session_state.mes_seleccionado_esc = mes_actual
    #st.session_state.año_anterior_esc = 2025    

if 'componente' not in st.session_state:
    st.session_state.componente = 'SPOT'

init_app_json_escalacv()


datos_total = st.session_state.datos_total_escalacv
fecha_ini = st.session_state.fecha_ini_escalacv
fecha_fin = st.session_state.fecha_fin_escalacv

# El selector diario del tab General siempre lo gobierna SPOT. Si el componente
# activo ya es SPOT, reutilizamos esos datos y evitamos una segunda carga.
if '_escalacv_datos_spot_general' not in st.session_state:
    if st.session_state.componente == 'SPOT':
        st.session_state._escalacv_datos_spot_general = datos_total
    else:
        datos_spot_general, _, _ = leer_json(
            st.secrets['FILE_ID_SPOT'],
            st.secrets['GOOGLE_SHEETS_CREDENTIALS'],
        )
        st.session_state._escalacv_datos_spot_general = datos_spot_general

# SSAA se carga bajo demanda al seleccionar SSAA o SPOT+SSAA. No debe retrasar
# el arranque normal del módulo cuando el componente activo es SPOT.
if (
    '_escalacv_datos_ssaa_general' not in st.session_state
    and st.session_state.componente != 'SPOT'
):
    try:
        datos_ssaa_general, _, _ = leer_json(
            st.secrets['FILE_ID_SSAA'],
            st.secrets['GOOGLE_SHEETS_CREDENTIALS'],
        )
        st.session_state._escalacv_error_ssaa_general = None
    except Exception as exc:
        datos_ssaa_general = pd.DataFrame()
        st.session_state._escalacv_error_ssaa_general = str(exc)
    st.session_state._escalacv_datos_ssaa_general = datos_ssaa_general

datos_spot_general = st.session_state._escalacv_datos_spot_general
datos_ssaa_general = st.session_state.get(
    '_escalacv_datos_ssaa_general', pd.DataFrame()
)

if '_escalacv_spreads_spot' not in st.session_state:
    st.session_state._escalacv_spreads_spot = calcular_spreads_diarios(
        datos_spot_general
    )
if (
    '_escalacv_spreads_ssaa' not in st.session_state
    or (
        st.session_state._escalacv_spreads_ssaa.empty
        and not datos_ssaa_general.empty
    )
):
    st.session_state._escalacv_spreads_ssaa = calcular_spreads_diarios(
        datos_ssaa_general
    )
spreads_spot = st.session_state._escalacv_spreads_spot
spreads_ssaa = st.session_state._escalacv_spreads_ssaa

# 1️⃣ Conteo total por mes
control_mes = (
    datos_total
    .groupby(['año','mes'])
    .agg(
        horas=('value','count'),
        media=('value','mean')
    )
    .reset_index()
)


ultimo_registro = datos_total['fecha'].max()
valor_minimo_horario_total = datos_total['value'].min()
valor_maximo_horario_total = datos_total['value'].max()
fecha_min_horario_total = datos_total.loc[datos_total['value'].idxmin(), 'fecha'] 
fecha_max_horario_total = datos_total.loc[datos_total['value'].idxmax(), 'fecha'] 

# Ultimos doce meses completos respecto a la fecha mas reciente disponible.
fecha_fin_año_movil = pd.Timestamp(datos_total['fecha'].max()).normalize()
fecha_corte_año_movil = fecha_fin_año_movil - pd.DateOffset(years=1)
fechas_total_normalizadas = pd.to_datetime(datos_total['fecha']).dt.normalize()
datos_ultimo_año_movil = datos_total.loc[
    (fechas_total_normalizadas > fecha_corte_año_movil)
    & (fechas_total_normalizadas <= fecha_fin_año_movil)
]
precio_medio_ultimo_año_movil = media_spot(datos_ultimo_año_movil)

#DATOS DIARIOS DESDE 2018
datos_totales, graf_ecv_total = diarios_totales(datos_total, fecha_ini, fecha_fin)
valor_minimo_diario_total = datos_totales['value'].min()
valor_maximo_diario_total = datos_totales['value'].max()
fecha_min_diario_total = datos_totales.loc[datos_totales['value'].idxmin(), 'fecha'] 
fecha_max_diario_total = datos_totales.loc[datos_totales['value'].idxmax(), 'fecha']

#FILTRAMOS POR EL AÑO SELECCIONADO
datos_año_filtrado = datos_total[datos_total['año'] == st.session_state.año_seleccionado_esc]
fecha_ini_año = datos_año_filtrado['fecha'].min()
fecha_fin_año = datetime(st.session_state.año_seleccionado_esc, 12, 31) 
#FILTRAMOS POR EL AÑO COMPARADO
datos_año_comparado = datos_totales[datos_totales['año'] == st.session_state.año_seleccionado_comp]

#datos diarios
datos_dia, graf_ecv_diario = diarios(datos_año_filtrado, fecha_ini_año, fecha_fin_año, datos_año_comparado)
prevision_omie_anual = st.session_state.get("prevision_omie_anual")
if (
    st.session_state.get("componente") == "SPOT"
    and isinstance(prevision_omie_anual, dict)
    and prevision_omie_anual.get("año") == st.session_state.año_seleccionado_esc
    and isinstance(prevision_omie_anual.get("curva_mensual"), pd.DataFrame)
):
    df_media_acumulada_prevista = construir_media_acumulada_prevista(
        datos_diarios_reales=datos_dia,
        curva_mensual_prevista=prevision_omie_anual["curva_mensual"],
        año=prevision_omie_anual["año"],
    )
    if not df_media_acumulada_prevista.empty:
        graf_ecv_diario.add_trace(
            go.Scatter(
                x=df_media_acumulada_prevista["fecha"],
                y=df_media_acumulada_prevista["media_acumulada_prevista"],
                mode="lines",
                name=f"Media acumulada prevista {prevision_omie_anual['año']}",
                line=dict(color="yellow", width=2, dash="dot"),
                hovertemplate=(
                    "<b>Media acumulada prevista</b><br>"
                    "%{x|%d-%m-%Y}<br>"
                    "%{y:.2f} €/MWh"
                    "<extra></extra>"
                ),
            )
        )
        ultimo_punto_previsto = df_media_acumulada_prevista.iloc[-1]
        graf_ecv_diario.add_annotation(
            x=ultimo_punto_previsto["fecha"],
            y=ultimo_punto_previsto["media_acumulada_prevista"],
            text=(
                f"Previsión {prevision_omie_anual['año']}: "
                f"{ultimo_punto_previsto['media_acumulada_prevista']:.2f} €/MWh"
            ),
            showarrow=False,
            xanchor="right",
            yshift=18,
            font=dict(color="yellow", size=15),
        )
valor_medio_diario = round(datos_dia['value'].mean(),2)
valor_minimo_diario = datos_dia['value'].min()
valor_maximo_diario = datos_dia['value'].max()
fecha_min_diario = datos_dia.loc[datos_dia['value'].idxmin(), 'fecha'] 
fecha_max_diario = datos_dia.loc[datos_dia['value'].idxmax(), 'fecha'] 
#fechas para slider valores horarios de un día concreto
datos_spot_año_general = datos_spot_general[
    datos_spot_general['año'] == st.session_state.año_seleccionado_esc
]
fecha_min_select_dia = pd.Timestamp(datos_spot_año_general['fecha'].min()).normalize()
fecha_max_select_dia = pd.Timestamp(datos_spot_año_general['fecha'].max()).normalize()
print (f'fecha min dia select: {fecha_min_select_dia}')
print (f'fecha max dia select: {fecha_max_select_dia}')



graf_ecv_mensual = mensuales(datos_dia)
graf_ecv_evol_mes_años = evolucion_mensual(datos_totales)





if (
    'dia_seleccionado_esc' not in st.session_state
    or st.session_state.año_seleccionado_esc != st.session_state.año_anterior_esc
):
    st.session_state.dia_seleccionado_esc = fecha_max_select_dia
    st.session_state.año_anterior_esc = st.session_state.año_seleccionado_esc

st.session_state.dia_seleccionado_esc = pd.Timestamp(
    st.session_state.dia_seleccionado_esc
).normalize()

if st.session_state.dia_seleccionado_esc > fecha_max_select_dia:
    st.session_state.dia_seleccionado_esc = fecha_max_select_dia
elif st.session_state.dia_seleccionado_esc < fecha_min_select_dia:
    st.session_state.dia_seleccionado_esc = fecha_min_select_dia


datos_horarios = datos_año_filtrado
valor_medio_horario = round(datos_horarios['value'].mean(),2)
valor_minimo_horario = round(datos_horarios['value'].min(),2)
valor_maximo_horario = round(datos_horarios['value'].max(),2)
fecha_min_horario = datos_horarios.loc[datos_horarios['value'].idxmin(), 'fecha']
fecha_max_horario = datos_horarios.loc[datos_horarios['value'].idxmax(), 'fecha']

meses_lista = ['todos', 'ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic']
mes_sel = st.session_state.get("mes_seleccionado_esc", "todos")
if mes_sel == "todos":
    datos_mes_filtrado = datos_año_filtrado.copy()
else:
    mes_num_sel = meses_lista.index(mes_sel)  # ene = 1, feb = 2, ..., dic = 12
    datos_mes_filtrado = datos_año_filtrado[
        datos_año_filtrado["mes"] == mes_num_sel
    ].copy()

# El tab anual siempre usa todo el año; el mensual respeta el mes elegido.
medias_horarias_anual, graf_medias_horarias_anual = medias_horarias(
    datos_año_filtrado, mes_etiqueta='todos'
)
medias_horarias_filtrado, graf_medias_horarias = medias_horarias(
    datos_mes_filtrado
)
mes_num_acumulada = None if mes_sel == "todos" else meses_lista.index(mes_sel)
df_media_acumulada_periodo, graf_media_acumulada_periodo = graficar_media_acumulada_periodo(
    datos_año_filtrado,
    mes_num=mes_num_acumulada,
)

#st.write(ultimo_registro) 
#   fecha_descarga=pasar_fecha()
    #st.write(ultima_descarga)

años_lista = list(range(2018, 2027)) #se pone un año más del actual
años_comp = [
    a for a in años_lista
    if a != st.session_state.año_seleccionado_esc
]



# ELEMENTOS DE LA BARRA LATERAL DE OPCIONES-----------------------------------------------------------------------------------------------
st.sidebar.header('⚡ Escala Cavero-Vidal ⚡')
st.sidebar.markdown(f':blue-background[Sección dedicada a **Roberto Cavero García**]')
ultima_fecha_spot = pd.Timestamp(datos_spot_general['fecha'].max())
st.sidebar.info(f'Última fecha SPOT disponible: {ultima_fecha_spot.strftime("%d.%m.%Y")}')
if st.sidebar.button('Actualizar datos', use_container_width=True):
    leer_json.clear()
    for clave_datos_escalacv in (
        'datos_total_escalacv',
        'fecha_ini_escalacv',
        'fecha_fin_escalacv',
        '_escalacv_componente_cargado',
        '_escalacv_datos_spot_general',
        '_escalacv_datos_ssaa_general',
        '_escalacv_error_ssaa_general',
        '_escalacv_spreads_spot',
        '_escalacv_spreads_ssaa',
    ):
        st.session_state.pop(clave_datos_escalacv, None)
    st.rerun()

st.sidebar.selectbox('Selecciona el año a visualizar', options = años_lista, key = 'año_seleccionado_esc')
st.sidebar.selectbox('Selecciona el año a comparar la media anual', options = años_comp, key = 'año_seleccionado_comp')
st.sidebar.selectbox('Selecciona el mes', options = meses_lista, key = 'mes_seleccionado_esc')
st.sidebar.date_input('Selecciona el día', min_value= fecha_min_select_dia, max_value=fecha_max_select_dia, key = 'dia_seleccionado_esc')
st.sidebar.radio('Selecciona el componente de mercado', options=['SPOT', 'SSAA', 'SPOT+SSAA'], key = 'componente')

if st.session_state.componente == 'SPOT+SSAA':
    st.sidebar.toggle('Predator Mode', key = 'dos_colores')
if 'dos_colores' in st.session_state and st.session_state.dos_colores:
    st.sidebar.toggle('Peso componentes', key = 'peso_comp')

# VISUALIZACIÓN ÁREA PRINCIPAL---------------------------------------------------------------------------------------------------------

tab_general, tab_anual, tab_mensual, tab_mapa, tab_simulador = st.tabs(
    ['General', 'Anual', 'Mensual', 'Mapa de Calor', 'Simulador']
)

with tab_general:
    # Gráfijo fijo de medias diarias y anuales
    with st.container():
        col1,col2=st.columns([0.84,0.16])
        with col1:
            st.plotly_chart(graf_ecv_total)
            #st.plotly_chart(graf_ecv_diario)
        with col2:
            st.subheader('Datos en €/MWh',divider='rainbow')
            st.metric(f'Precio mínimo diario ( {fecha_min_diario_total})', value=formato_numero_es(valor_minimo_diario_total, 2))
            st.metric(f'Precio máximo diario ({fecha_max_diario_total})', value=formato_numero_es(valor_maximo_diario_total, 2))
            if precio_medio_ultimo_año_movil is not None:
                st.metric(
                    'Precio medio del último año móvil',
                    value=formato_numero_es(
                        precio_medio_ultimo_año_movil, 2
                    ),
                )

    # SPOT y SSAA comparten exactamente la fecha marcada en el date_input.
    fecha_general = pd.Timestamp(st.session_state.dia_seleccionado_esc).date()

    def _datos_del_dia(datos):
        if not isinstance(datos, pd.DataFrame) or datos.empty:
            return pd.DataFrame()
        return datos.loc[datos['fecha'] == fecha_general].sort_values('hora').copy()

    def _perfil_horario_medio_año(datos, año):
        if not isinstance(datos, pd.DataFrame) or datos.empty:
            return pd.DataFrame(columns=['hora', 'value'])
        fechas = pd.to_datetime(datos['fecha'], errors='coerce')
        return (
            datos.loc[fechas.dt.year == año]
            .groupby('hora', as_index=False)['value']
            .mean()
            .sort_values('hora')
        )

    def _grafico_diario(
        datos, perfil_medio_anual, titulo, color_barras, color_media, año
    ):
        figura = go.Figure()
        figura.add_trace(
            go.Bar(
                x=datos['hora'],
                y=datos['value'],
                name='Día seleccionado',
                marker_color=color_barras,
                marker_cornerradius=8,
                hovertemplate=(
                    '<b>Hora %{x}:00</b><br>Día: %{y:.2f} €/MWh'
                    '<extra></extra>'
                ),
            )
        )
        if not perfil_medio_anual.empty:
            figura.add_trace(
                go.Scatter(
                    x=perfil_medio_anual['hora'],
                    y=perfil_medio_anual['value'],
                    name=f'Media horaria {año}',
                    mode='lines+markers',
                    line=dict(color=color_media, width=3),
                    marker=dict(color=color_media, size=6),
                    hovertemplate=(
                        f'<b>Media {año} · hora %{{x}}:00</b><br>'
                        '%{y:.2f} €/MWh<extra></extra>'
                    ),
                )
            )
        figura.update_layout(
            title=dict(
                text=titulo,
                x=0.5,
                xanchor='center',
                y=0.98,
                yanchor='top',
                font=dict(size=24),
            ),
            xaxis_title='Hora',
            yaxis_title='€/MWh',
            separators=',.',
            margin=dict(l=20, r=20, t=105, b=20),
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.01,
                xanchor='center',
                x=0.5,
            ),
        )
        figura.update_xaxes(dtick=2)
        return figura

    def _metricas_diarias(datos, spreads):
        hora_min = int(datos.loc[datos['value'].idxmin(), 'hora'])
        hora_max = int(datos.loc[datos['value'].idxmax(), 'hora'])
        st.metric('Precio medio diario', formato_numero_es(datos['value'].mean(), 2))
        st.metric(f'Precio mínimo horario ({hora_min}:00)', formato_numero_es(datos['value'].min(), 2))
        st.metric(f'Precio máximo horario ({hora_max}:00)', formato_numero_es(datos['value'].max(), 2))
        spread_dia = spreads.loc[spreads['fecha'] == fecha_general]
        if not spread_dia.empty:
            st.metric(
                'Spread diario',
                formato_numero_es(spread_dia['spread_diario'].iloc[0], 2),
            )

    spot_dia_general = _datos_del_dia(datos_spot_general)
    ssaa_dia_general = _datos_del_dia(datos_ssaa_general)
    año_fecha_general = fecha_general.year
    spot_perfil_medio_anual = _perfil_horario_medio_año(
        datos_spot_general, año_fecha_general
    )
    ssaa_perfil_medio_anual = _perfil_horario_medio_año(
        datos_ssaa_general, año_fecha_general
    )
    col_spot_graf, col_spot_met, col_ssaa_graf, col_ssaa_met = st.columns(
        [.34, .16, .34, .16]
    )
    with col_spot_graf:
        if spot_dia_general.empty:
            st.info('No hay datos SPOT para la fecha seleccionada.')
        else:
            st.plotly_chart(
                _grafico_diario(
                    spot_dia_general,
                    spot_perfil_medio_anual,
                    f'SPOT · {fecha_general.strftime("%d.%m.%Y")}',
                    'green',
                    '#7CFC00',
                    año_fecha_general,
                ),
                use_container_width=True,
            )
    with col_spot_met:
        st.subheader('SPOT', divider='rainbow')
        if not spot_dia_general.empty:
            _metricas_diarias(spot_dia_general, spreads_spot)
    with col_ssaa_graf:
        if ssaa_dia_general.empty:
            st.info('No hay datos de SSAA para la fecha SPOT seleccionada.')
        else:
            st.plotly_chart(
                _grafico_diario(
                    ssaa_dia_general,
                    ssaa_perfil_medio_anual,
                    f'SSAA · {fecha_general.strftime("%d.%m.%Y")}',
                    '#F28E2B',
                    '#FFD166',
                    año_fecha_general,
                ),
                use_container_width=True,
            )
    with col_ssaa_met:
        st.subheader('SSAA', divider='rainbow')
        if not ssaa_dia_general.empty:
            _metricas_diarias(ssaa_dia_general, spreads_ssaa)

with tab_anual:
    # 2. Precios diarios del año seleccionado.
    col1,col2=st.columns([0.8,0.2])
    with col1:
        st.plotly_chart(graf_ecv_diario)
    with col2:
        st.subheader('Datos en €/MWh',divider='rainbow')
        st.metric(f'Precio medio diario {st.session_state.año_seleccionado_esc}', value=formato_numero_es(valor_medio_diario, 2))
        st.metric(
            f'Precio mínimo diario ({pd.Timestamp(fecha_min_diario).strftime("%d.%m.%Y")})',
            value=formato_numero_es(valor_minimo_diario, 2),
        )
        st.metric(
            f'Precio máximo diario ({pd.Timestamp(fecha_max_diario).strftime("%d.%m.%Y")})',
            value=formato_numero_es(valor_maximo_diario, 2),
        )
        if (
            st.session_state.componente == "SPOT"
            and st.session_state.año_seleccionado_esc == 2026
            and not isinstance(prevision_omie_anual, dict)
        ):
            if st.button('Calcular previsión OMIE 2026', use_container_width=True):
                with st.spinner('Calculando la curva híbrida OMIE-OMIP...'):
                    prevision = obtener_prevision_omie_anual(datos_total)
                    guardar_prevision_omie_en_sesion(prevision)
                st.rerun()

    # 3 y 4. Medias mensuales y perfil horario medio de todo el año.
    col5,col6,col7=st.columns([.45,.35,.2])
    with col5:
        st.plotly_chart(graf_ecv_mensual)
    with col6:
        st.plotly_chart(graf_medias_horarias_anual)
    with col7:
        st.subheader('Datos en €/MWh',divider='rainbow')
        spreads_año = calcular_spreads_diarios(datos_año_filtrado)
        sub1, sub2 = st.columns([.7,.3])
        with sub1:
            st.metric(f'Precio mínimo horario ({fecha_min_horario})', value=formato_numero_es(valor_minimo_horario, 2))
            st.metric(f'Precio máximo horario ({fecha_max_horario})', value=formato_numero_es(valor_maximo_horario, 2))
        with sub2:
            def mod_min():
                st.session_state.dia_seleccionado_esc = fecha_min_horario
            def mod_max():
                st.session_state.dia_seleccionado_esc = fecha_max_horario

            st.button('Seleccionar día', on_click=mod_min, key='mod_min')
            st.button('Seleccionar día', on_click=mod_max)
        if not spreads_año.empty:
            st.metric(
                'Spread medio anual',
                formato_numero_es(spreads_año['spread_diario'].mean(), 2),
            )

with tab_mensual:
    if mes_sel == 'todos':
        st.info('Selecciona un mes en la barra lateral para ver el análisis mensual.')
    else:
        col5,col6,col7=st.columns([.4,.4,.2])
        with col5:
            st.plotly_chart(graf_ecv_evol_mes_años, use_container_width=True)
        with col6:
            if medias_horarias_filtrado.empty:
                st.info(
                    'No hay datos horarios para el mes, año y componente '
                    'seleccionados.'
                )
            else:
                st.plotly_chart(graf_medias_horarias, use_container_width=True)
        with col7:
            st.subheader('Perfil horario medio', divider='rainbow')
            perfil_horario_mes = (
                datos_mes_filtrado.groupby('hora', as_index=False)['value'].mean()
            )
            if perfil_horario_mes.empty:
                st.info('No hay datos para calcular las métricas del perfil.')
            else:
                hora_min_perfil = int(
                    perfil_horario_mes.loc[
                        perfil_horario_mes['value'].idxmin(), 'hora'
                    ]
                )
                hora_max_perfil = int(
                    perfil_horario_mes.loc[
                        perfil_horario_mes['value'].idxmax(), 'hora'
                    ]
                )
                st.metric(
                    'Media',
                    formato_numero_es(perfil_horario_mes['value'].mean(), 2),
                )
                st.metric(
                    f'Mínimo ({hora_min_perfil}:00)',
                    formato_numero_es(perfil_horario_mes['value'].min(), 2),
                )
                st.metric(
                    f'Máximo ({hora_max_perfil}:00)',
                    formato_numero_es(perfil_horario_mes['value'].max(), 2),
                )
                spreads_mes = calcular_spreads_diarios(datos_mes_filtrado)
                if not spreads_mes.empty:
                    st.metric(
                        'Spread medio mensual',
                        formato_numero_es(
                            spreads_mes['spread_diario'].mean(), 2
                        ),
                    )

        if df_media_acumulada_periodo.empty:
            st.info(
                'No hay precios diarios con los que calcular la media '
                'acumulada de este mes.'
            )
        else:
            col5,col6,col7=st.columns([.4,.4,.2])
            with col5:
                spreads_mes_grafico = calcular_spreads_diarios(
                    datos_mes_filtrado
                )
                if spreads_mes_grafico.empty:
                    st.info('No hay datos para calcular los spreads diarios.')
                else:
                    graf_spreads_mes = go.Figure(
                        go.Bar(
                            x=spreads_mes_grafico['fecha'],
                            y=spreads_mes_grafico['spread_diario'],
                            marker_color='#4C78A8',
                            marker_cornerradius=8,
                            hovertemplate=(
                                '<b>%{x|%d.%m.%Y}</b><br>'
                                'Spread: %{y:.2f} €/MWh<extra></extra>'
                            ),
                        )
                    )
                    graf_spreads_mes.update_layout(
                        title=(
                            f'{st.session_state.componente}: spread diario '
                            f'· {mes_sel} '
                            f'{st.session_state.año_seleccionado_esc}'
                        ),
                        xaxis_title='Día',
                        yaxis_title='€/MWh',
                        separators=',.',
                    )
                    inicio_mes_spread = pd.Timestamp(
                        st.session_state.año_seleccionado_esc,
                        mes_num_sel,
                        1,
                    )
                    fin_mes_spread = (
                        inicio_mes_spread
                        + pd.offsets.MonthEnd(0)
                    )
                    graf_spreads_mes.update_xaxes(
                        range=[
                            inicio_mes_spread - pd.Timedelta(hours=12),
                            fin_mes_spread + pd.Timedelta(hours=12),
                        ],
                        tickformat='%d',
                        dtick=24 * 60 * 60 * 1000,
                        showgrid=True,
                    )
                    graf_spreads_mes = aplicar_estilo(graf_spreads_mes)
                    st.plotly_chart(
                        graf_spreads_mes, use_container_width=True
                    )
            with col6:
                st.plotly_chart(
                    graf_media_acumulada_periodo, use_container_width=True
                )
            with col7:
                fecha_min_periodo = df_media_acumulada_periodo.loc[
                    df_media_acumulada_periodo['value'].idxmin(), 'fecha'
                ]
                fecha_max_periodo = df_media_acumulada_periodo.loc[
                    df_media_acumulada_periodo['value'].idxmax(), 'fecha'
                ]
                st.subheader('Datos en €/MWh', divider='rainbow')
                st.metric(
                    'Precio medio del periodo',
                    formato_numero_es(
                        df_media_acumulada_periodo['media_acumulada'].iloc[-1], 2
                    ),
                )
                st.metric(
                    f'Precio mínimo ({pd.Timestamp(fecha_min_periodo).strftime("%d.%m.%Y")})',
                    formato_numero_es(df_media_acumulada_periodo['value'].min(), 2),
                )
                st.metric(
                    f'Precio máximo ({pd.Timestamp(fecha_max_periodo).strftime("%d.%m.%Y")})',
                    formato_numero_es(df_media_acumulada_periodo['value'].max(), 2),
                )


    
        

with tab_mapa:
    with st.container():
        col5,col6,col7=st.columns([.4,.4,.2])
        with col5:
            st.info(
                '**¿El precio es bajo o alto?** Este mapa usa siempre los '
                'mismos rangos para cada color. Sirve para comparar días, '
                'meses o años, porque el significado de los colores no '
                'cambia. El precio exacto aparece al pasar el cursor.'
            )
            matriz_heat, graf_heat = mapa_calor_mes(datos_año_filtrado)
            if graf_heat is not None:
                st.plotly_chart(graf_heat, use_container_width=True)
        with col6:
            st.info(
                '**¿Qué horas son más baratas o más caras?** Este mapa '
                'ajusta los colores al mínimo y máximo del periodo. Sirve '
                'para encontrar contrastes dentro del mes o año, pero no '
                'para comparar colores con otro periodo. El precio exacto '
                'aparece al pasar el cursor.'
            )
            matriz_heat_difuso, graf_heat_difuso= mapa_calor_mes_gradual(datos_año_filtrado)
            if graf_heat_difuso is not None:
                st.plotly_chart(graf_heat_difuso, use_container_width=True)
            

with tab_simulador:
    col1, col2 = st.columns(2) 

    with col1:

        with st.container():
            col5,col6,col7=st.columns([.4,.4,.2])
            #with col5:
            mostrar_combo = st.button('Mostrar simulación SSAA a partir de SPOT', use_container_width=True)
            st.number_input("OMIE medio anual esperado (€/MWh)", min_value=40.0, max_value=150.0, step=1.0, key='omie_input')
            if mostrar_combo:
                #if "df_sheets" not in st.session_state:
                if "csv_componentes" not in st.session_state:    
                    init_app()
                    init_app_index()

                # 2. Construimos DF mensual SOLO una vez
                if "df_scatter_mensual" not in st.session_state:
                    obtener_df_scatter_mensual()

            
                if 'df_scatter_mensual' in st.session_state:
                    #grafico base con los scatter omie ssaa mensuales
                    graf_scatter_combo = graficar_scatter_combo()
                        
                    if 'omie_input' not in st.session_state:
                        st.session_state.omie_input = 58
                    #añadimos 
                    p_real = obtener_puntos_anuales()
                    graf_scatter_combo, ssaa_simulada, _ = graficar_simulacion_cuadratica(
                        graf_scatter_combo,
                        st.session_state.df_scatter_mensual,
                        {
                            2025: p_real[2025],
                            2026: p_real[2026],
                        },
                        st.session_state.omie_input,
                        nombre="Curva central",
                        color="orange"
                    )
                    
                
                
     
       
    
                st.subheader('Micropower 2026 combo SPOT+SSAA', divider='rainbow')
                # 3. Input OMIE anual
                #st.number_input("OMIE medio anual esperado (€/MWh)", min_value=0.0, max_value=200.0, step=1.0, key='omie_input')
                c55, c56, c57, c58, c59 =st.columns(5)
                with c55:
                    st.metric('SPOT MEDIO', f'{st.session_state.omie_input:,.2f}') 
                    #st.number_input("OMIE medio anual esperado (€/MWh)", min_value=40.0, max_value=150.0, step=1.0, key='omie_input')
                with c57:
                    st.metric('SSAA MEDIO', f'{ssaa_simulada:,.2f}') 
                    
                with c58:
                    combo_estimado = st.session_state.omie_input+ssaa_simulada
                    st.metric('COMBO SPOT+SSAA',f'{combo_estimado:,.2f}')

                        
                st.plotly_chart(graf_scatter_combo, use_container_width=True)

            
    with col2:
        if "csv_componentes" not in st.session_state:    
            init_app()
            init_app_index()
             
        graf_bandas_combo = graficar_bandas_ssaa()
        st.write(graf_bandas_combo)         
        

        
