import streamlit as st
import datetime
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go


from utilidades import (
    generar_menu,
    actualizar_datos_mercado,
    init_app_json_escalacv, init_app, init_app_index
)

from backend_escalacv import (
    diarios_totales, diarios, mensuales, horarios, medias_horarias, evolucion_mensual, meses_español,
    obtener_df_scatter_mensual, graficar_scatter_combo, obtener_puntos_anuales, graficar_simulacion_cuadratica, graficar_bandas_ssaa,
    mapa_calor_mes, mapa_calor_mes_gradual, graficar_media_acumulada_periodo,
    calcular_spreads_diarios, graficar_spreads_historicos,
    calcular_volatilidad_diaria, graficar_volatilidad_historica,
    graficar_distribucion_volatilidad,
    graficar_dispersion_volatilidad_diaria,
    get_limites_componentes, colores, marcador_nivel_cv,
    FONDO_CSS_APOCALIPSIS,
)
from backend_comun import aplicar_estilo, construir_media_acumulada_prevista
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
if '_año_visual_mensual' not in st.session_state:
    st.session_state._año_visual_mensual = st.session_state.año_seleccionado_esc
if '_año_visual_anual' not in st.session_state:
    st.session_state._año_visual_anual = st.session_state.año_seleccionado_esc


def _sincronizar_año_desde_mensual():
    año = st.session_state._año_visual_mensual
    st.session_state.año_seleccionado_esc = año
    st.session_state._año_visual_anual = año
    if st.session_state.get('año_seleccionado_comp') == año:
        st.session_state.año_seleccionado_comp = año - 1 if año > 2018 else 2019


def _sincronizar_año_desde_anual():
    año = st.session_state._año_visual_anual
    st.session_state.año_seleccionado_esc = año
    st.session_state._año_visual_mensual = año
    if st.session_state.get('año_seleccionado_comp') == año:
        st.session_state.año_seleccionado_comp = año - 1 if año > 2018 else 2019


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

# Ambas series ya llegan precargadas para toda ePowerApp.
datos_spot_general = st.session_state._escalacv_datos_spot_general
datos_ssaa_general = st.session_state._escalacv_datos_ssaa_general

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
graf_historico_spread = graficar_spreads_historicos(spreads_spot)
graf_historico_spread_ssaa = graficar_spreads_historicos(
    spreads_ssaa, componente='SSAA'
)
volatilidad_spot = calcular_volatilidad_diaria(datos_spot_general)
graf_volatilidad_historica = graficar_volatilidad_historica(volatilidad_spot)
graf_distribucion_volatilidad = graficar_distribucion_volatilidad(
    volatilidad_spot
)

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


#DATOS DIARIOS DESDE 2018
datos_totales, _ = diarios_totales(datos_total, fecha_ini, fecha_fin)
fecha_ini_spot_historico = datos_spot_general['fecha'].min()
fecha_fin_spot_historico = datos_spot_general['fecha'].max()
fecha_ini_ssaa_historico = datos_ssaa_general['fecha'].min()
fecha_fin_ssaa_historico = datos_ssaa_general['fecha'].max()
_, graf_historico_spot = diarios_totales(
    datos_spot_general,
    fecha_ini_spot_historico,
    fecha_fin_spot_historico,
    componente='SPOT',
)
_, graf_historico_ssaa = diarios_totales(
    datos_ssaa_general,
    fecha_ini_ssaa_historico,
    fecha_fin_ssaa_historico,
    componente='SSAA',
)

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





fecha_hoy_diario = pd.Timestamp(fecha_hoy).normalize()
fecha_diaria_predeterminada = (
    fecha_hoy_diario
    if fecha_min_select_dia <= fecha_hoy_diario <= fecha_max_select_dia
    else fecha_max_select_dia
)
if (
    'dia_seleccionado_esc' not in st.session_state
    or st.session_state.año_seleccionado_esc != st.session_state.año_anterior_esc
    or not st.session_state.get('_escalacv_diario_inicializado_hoy')
):
    st.session_state.dia_seleccionado_esc = fecha_diaria_predeterminada
    st.session_state.año_anterior_esc = st.session_state.año_seleccionado_esc
    st.session_state._escalacv_diario_inicializado_hoy = True

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


def _leyenda_escala_cv(titulo, componente):
    """Muestra los niveles de la Escala CV en una columna estrecha."""
    df_limites, etiquetas, _ = get_limites_componentes(componente)
    limites = df_limites['rango'].tolist()
    filas = []
    for indice, etiqueta in enumerate(etiquetas):
        if indice == 0:
            rango = '≤ 0'
        elif indice == len(etiquetas) - 1:
            rango = f'&gt; {round(limites[indice])}'
        else:
            rango = (
                f'{round(limites[indice])}–'
                f'{round(limites[indice + 1])}'
            )
        fondo = colores[etiqueta]
        if etiqueta == 'apocalipsis zombie':
            fondo = FONDO_CSS_APOCALIPSIS
        filas.append(
            '<div class="escala-cv-fila">'
            f'<span class="escala-cv-color" style="background:{fondo}"></span>'
            f'<span>{rango}</span>'
            f'<span class="escala-cv-nivel">{etiqueta}</span>'
            '</div>'
        )
    st.markdown(
        f'<div class="escala-cv-bloque">'
        f'<div class="escala-cv-titulo">{titulo} <small>€/MWh</small></div>'
        f'{"".join(filas)}'
        '</div>',
        unsafe_allow_html=True,
    )


def _marcar_apagon_28a(figura):
    """Señala el apagón peninsular del 28 de abril de 2025."""
    fecha_apagon = pd.Timestamp('2025-04-28')
    figura.add_shape(
        type='line',
        x0=fecha_apagon,
        x1=fecha_apagon,
        y0=0,
        y1=1,
        xref='x',
        yref='paper',
        line=dict(color='yellow', width=2, dash='dash'),
        layer='above',
    )
    figura.add_annotation(
        x=fecha_apagon,
        y=1,
        xref='x',
        yref='paper',
        text='<b>28A</b>',
        showarrow=False,
        xshift=5,
        yshift=12,
        xanchor='left',
        font=dict(color='yellow', size=15, family='Arial'),
    )


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
graf_media_acumulada_periodo.update_yaxes(
    dtick=4 if st.session_state.componente == 'SSAA' else 20
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
st.sidebar.header('⚡ Escala CV: Mercados OMIE ⚡')
st.sidebar.markdown(f':blue-background[Sección dedicada a **Roberto Cavero García**]')
ultima_fecha_spot = pd.Timestamp(datos_spot_general['fecha'].max())
st.sidebar.info(f'Última fecha SPOT disponible: {ultima_fecha_spot.strftime("%d.%m.%Y")}')
if st.sidebar.button('Actualizar datos', use_container_width=True):
    with st.spinner('Actualizando SPOT y SSAA desde Drive...'):
        actualizar_datos_mercado()
    st.rerun()

# VISUALIZACIÓN ÁREA PRINCIPAL---------------------------------------------------------------------------------------------------------

tab_diario, tab_mensual, tab_anual, tab_historica, tab_spread, tab_volatilidad, tab_mapa, tab_simulador = st.tabs(
    ['Diario', 'Mensual', 'Anual', 'Serie histórica', 'Spread', 'Volatilidad', 'Mapa de Calor', 'Simulador']
)

with tab_diario:
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

    def _grafico_diario(datos, perfil_medio_anual, titulo, componente, año):
        df_limites, etiquetas, _ = get_limites_componentes(componente)
        escala_horaria = pd.cut(
            datos['value'],
            bins=df_limites['rango'],
            labels=etiquetas,
            right=False,
        )
        niveles_horarios = [
            str(nivel) if pd.notna(nivel) else 'fuera de escala'
            for nivel in escala_horaria
        ]
        figura = go.Figure()
        datos_grafico = datos.copy()
        datos_grafico['_nivel_cv'] = niveles_horarios
        for nivel in dict.fromkeys(niveles_horarios):
            datos_nivel = datos_grafico.loc[
                datos_grafico['_nivel_cv'].eq(nivel)
            ]
            figura.add_trace(
                go.Bar(
                    x=datos_nivel['hora'],
                    y=datos_nivel['value'],
                    width=0.9,
                    name=nivel,
                    showlegend=False,
                    marker=marcador_nivel_cv(nivel),
                    marker_cornerradius=8,
                    customdata=datos_nivel['_nivel_cv'],
                    hovertemplate=(
                        '<b>Hora %{x}:00</b><br>Día: %{y:.2f} €/MWh<br>'
                        'Escala CV: %{customdata}'
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
                    line=dict(color='#FFD700', width=3),
                    marker=dict(color='#FFD700', size=6),
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
            barmode='overlay',
            bargap=0.08,
            margin=dict(l=20, r=20, t=105, b=20),
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.01,
                xanchor='center',
                x=0.5,
            ),
        )
        figura.update_xaxes(
            tickmode='array',
            tickvals=list(range(24)),
            range=[-0.5, 23.5],
        )
        return aplicar_estilo(figura)

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
    (
        col_fecha,
        col_spot_graf,
        col_spot_met,
        col_ssaa_graf,
        col_ssaa_met,
    ) = st.columns(
        [.12, .34, .10, .34, .10]
    )
    with col_fecha:
        st.subheader('Fecha', divider='rainbow')
        st.date_input(
            'Selecciona el día',
            min_value=fecha_min_select_dia,
            max_value=fecha_max_select_dia,
            format='DD.MM.YYYY',
            key='dia_seleccionado_esc',
        )
        _leyenda_escala_cv('SPOT', 'SPOT')
        _leyenda_escala_cv('SSAA', 'SSAA')
    with col_spot_graf:
        if spot_dia_general.empty:
            st.info('No hay datos SPOT para la fecha seleccionada.')
        else:
            st.plotly_chart(
                _grafico_diario(
                    spot_dia_general,
                    spot_perfil_medio_anual,
                    f'SPOT · {fecha_general.strftime("%d.%m.%Y")}',
                    'SPOT',
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
                    'SSAA',
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
        st.selectbox(
            'Año a visualizar',
            options=años_lista,
            key='_año_visual_anual',
            on_change=_sincronizar_año_desde_anual,
        )
        st.selectbox(
            'Año a comparar',
            options=años_comp,
            key='año_seleccionado_comp',
        )
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
    col_filtros, col_contenido_mensual = st.columns([.12, .88])
    with col_filtros:
        st.subheader('Opciones', divider='rainbow')
        st.selectbox(
            'Año a visualizar',
            options=años_lista,
            key='_año_visual_mensual',
            on_change=_sincronizar_año_desde_mensual,
        )
        st.selectbox(
            'Mes',
            options=meses_lista,
            key='mes_seleccionado_esc',
        )
        st.radio(
            'Componente de mercado',
            options=['SPOT', 'SSAA', 'SPOT+SSAA'],
            key='componente',
        )
        if st.session_state.componente == 'SPOT+SSAA':
            st.toggle('Predator Mode', key='dos_colores')
        if st.session_state.get('dos_colores', False):
            st.toggle('Peso componentes', key='peso_comp')
        st.markdown(
            """
            <style>
            .escala-cv-bloque {
                margin-top: .65rem;
                padding: .45rem .4rem;
                border: 1px solid rgba(128, 128, 128, .28);
                border-radius: .45rem;
            }
            .escala-cv-titulo {
                margin-bottom: .28rem;
                font-size: 1.12rem;
                font-weight: 700;
            }
            .escala-cv-titulo small { font-size: .88rem; font-weight: 400; }
            .escala-cv-fila {
                display: grid;
                grid-template-columns: .75rem 3.25rem minmax(0, 1fr);
                align-items: center;
                gap: .25rem;
                min-height: 1.5rem;
                font-size: .92rem;
                line-height: 1.1;
                white-space: nowrap;
            }
            .escala-cv-color {
                width: .7rem;
                height: .7rem;
                border: 1px solid rgba(80, 80, 80, .55);
                border-radius: 2px;
            }
            .escala-cv-nivel {
                overflow: hidden;
                text-overflow: ellipsis;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        _leyenda_escala_cv('SPOT', 'SPOT')
        _leyenda_escala_cv('SSAA', 'SSAA')

    col_evol, col_evol_met, col_perfil, col_perfil_met = (
        col_contenido_mensual.columns([.36, .14, .36, .14])
    )

    if mes_sel == 'todos':
        with col_evol:
            st.info('Selecciona un mes para ver el análisis mensual.')
    else:
        perfil_horario_mes = (
            datos_mes_filtrado.groupby('hora', as_index=False)['value'].mean()
        )
        spreads_mes_grafico = calcular_spreads_diarios(datos_mes_filtrado)
        graf_spreads_mes = None
        if not spreads_mes_grafico.empty:
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
            fin_mes_spread = inicio_mes_spread + pd.offsets.MonthEnd(0)
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

        with col_evol:
            if df_media_acumulada_periodo.empty:
                st.info(
                    'No hay precios diarios con los que calcular la media '
                    'acumulada de este mes.'
                )
            else:
                st.plotly_chart(
                    graf_media_acumulada_periodo, use_container_width=True
                )
        with col_evol_met:
            st.subheader('Datos en €/MWh', divider='rainbow')
            if not df_media_acumulada_periodo.empty:
                fecha_min_periodo = df_media_acumulada_periodo.loc[
                    df_media_acumulada_periodo['value'].idxmin(), 'fecha'
                ]
                fecha_max_periodo = df_media_acumulada_periodo.loc[
                    df_media_acumulada_periodo['value'].idxmax(), 'fecha'
                ]
                st.metric(
                    'Precio medio del periodo',
                    formato_numero_es(
                        df_media_acumulada_periodo[
                            'media_acumulada'
                        ].iloc[-1],
                        2,
                    ),
                )
                st.metric(
                    f'Precio mínimo ({pd.Timestamp(fecha_min_periodo).strftime("%d.%m.%Y")})',
                    formato_numero_es(
                        df_media_acumulada_periodo['value'].min(), 2
                    ),
                )
                st.metric(
                    f'Precio máximo ({pd.Timestamp(fecha_max_periodo).strftime("%d.%m.%Y")})',
                    formato_numero_es(
                        df_media_acumulada_periodo['value'].max(), 2
                    ),
                )
        with col_perfil:
            if medias_horarias_filtrado.empty:
                st.info(
                    'No hay datos horarios para el mes, año y componente '
                    'seleccionados.'
                )
            else:
                st.plotly_chart(graf_medias_horarias, use_container_width=True)
        with col_perfil_met:
            st.subheader('Perfil horario medio', divider='rainbow')
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
        (
            col_comparativa,
            col_comparativa_met,
            col_spread,
            col_spread_met,
        ) = col_contenido_mensual.columns([.36, .14, .36, .14])
        with col_comparativa:
            st.plotly_chart(
                graf_ecv_evol_mes_años, use_container_width=True
            )
        with col_comparativa_met:
            st.empty()
        with col_spread:
            if graf_spreads_mes is None:
                st.info('No hay datos para calcular los spreads diarios.')
            else:
                st.plotly_chart(graf_spreads_mes, use_container_width=True)
        with col_spread_met:
            st.subheader('Spread diario', divider='rainbow')
            if not spreads_mes_grafico.empty:
                fila_spread_min = spreads_mes_grafico.loc[
                    spreads_mes_grafico['spread_diario'].idxmin()
                ]
                fila_spread_max = spreads_mes_grafico.loc[
                    spreads_mes_grafico['spread_diario'].idxmax()
                ]
                st.metric(
                    'Spread medio',
                    formato_numero_es(
                        spreads_mes_grafico['spread_diario'].mean(), 2
                    ),
                )
                st.metric(
                    f'Mínimo ({pd.Timestamp(fila_spread_min["fecha"]).strftime("%d.%m.%Y")})',
                    formato_numero_es(fila_spread_min['spread_diario'], 2),
                )
                st.metric(
                    f'Máximo ({pd.Timestamp(fila_spread_max["fecha"]).strftime("%d.%m.%Y")})',
                    formato_numero_es(fila_spread_max['spread_diario'], 2),
                )


    
        

with tab_historica:
    graf_historico_spot.update_layout(height=620)
    graf_historico_ssaa.update_layout(height=620)
    if not any(
        traza.name == 'apocalipsis zombie'
        for traza in graf_historico_ssaa.data
    ):
        graf_historico_ssaa.add_trace(
            go.Bar(
                x=[None],
                y=[None],
                name='apocalipsis zombie',
                visible='legendonly',
                hoverinfo='skip',
                marker=marcador_nivel_cv('apocalipsis zombie'),
            )
        )
    _marcar_apagon_28a(graf_historico_spot)
    _marcar_apagon_28a(graf_historico_ssaa)
    st.plotly_chart(graf_historico_spot, use_container_width=True)
    st.plotly_chart(graf_historico_ssaa, use_container_width=True)


with tab_spread:
    st.info(
        '**¿Cuánta diferencia hay entre la hora más cara y la más barata?** '
        'El spread diario es el precio horario máximo menos el mínimo de '
        'cada día. Las líneas amarillas muestran la media de los spreads '
        'diarios de cada año.'
    )
    if graf_historico_spread is None:
        st.info('No hay datos de SPOT para calcular el spread desde 2018.')
    else:
        graf_historico_spread.update_layout(height=620)
        st.plotly_chart(graf_historico_spread, use_container_width=True)
    if graf_historico_spread_ssaa is None:
        st.info('No hay datos de SSAA para calcular el spread desde 2018.')
    else:
        graf_historico_spread_ssaa.update_layout(height=620)
        st.plotly_chart(graf_historico_spread_ssaa, use_container_width=True)


with tab_volatilidad:
    st.info(
        '**¿Cuánto se mueve el precio dentro de cada día?** La volatilidad '
        'se calcula como la desviación estándar de todos sus precios '
        'horarios. A diferencia del spread, tiene en cuenta las 24 horas y '
        'no solo el máximo y el mínimo.'
    )
    if graf_volatilidad_historica is None:
        st.info('No hay datos para calcular la volatilidad desde 2018.')
    else:
        graf_volatilidad_historica.update_layout(height=620)
        st.plotly_chart(graf_volatilidad_historica, use_container_width=True)
        volatilidad_boxplot = volatilidad_spot.copy()
        volatilidad_boxplot['fecha'] = pd.to_datetime(
            volatilidad_boxplot['fecha'], errors='coerce'
        )
        volatilidad_boxplot = volatilidad_boxplot[
            volatilidad_boxplot['fecha'] >= pd.Timestamp('2018-01-01')
        ].dropna(subset=['fecha', 'volatilidad_diaria'])
        medianas_anuales = volatilidad_boxplot.groupby(
            volatilidad_boxplot['fecha'].dt.year
        )['volatilidad_diaria'].median()
        año_mayor_mediana = int(medianas_anuales.idxmax())
        mayor_mediana = medianas_anuales.loc[año_mayor_mediana]
        ultima_fecha = volatilidad_boxplot['fecha'].max()
        aviso_año_incompleto = ''
        if ultima_fecha < pd.Timestamp(ultima_fecha.year, 12, 31):
            aviso_año_incompleto = (
                f' **{ultima_fecha.year} está incompleto**, por lo que su '
                'distribución todavía no es directamente comparable con '
                'la de los años cerrados.'
            )
        col1_graf2, col2_graf2 = st.columns([.25, .75])
        with col1_graf2:
            st.info(
                '**Cómo leer la distribución:** la línea dentro de cada '
                'caja es la mediana; la caja contiene el 50 % central de los '
                'días; los bigotes muestran el rango habitual y los puntos '
                'son jornadas excepcionalmente volátiles. En los datos '
                f'disponibles, **{año_mayor_mediana} presenta la mediana '
                f'diaria más alta** '
                f'({formato_numero_es(mayor_mediana, 2)} €/MWh).'
                f'{aviso_año_incompleto}'
            )
        with col2_graf2:
            if graf_distribucion_volatilidad is not None:
                graf_distribucion_volatilidad.update_layout(height=620)
                st.plotly_chart(
                    graf_distribucion_volatilidad, use_container_width=True
                )

        años_disponibles = sorted(
            volatilidad_boxplot['fecha'].dt.year.dropna().astype(int).unique(),
            reverse=True,
        )
        col1_graf3, col2_graf3 = st.columns([.12, .88])
        with col1_graf3:
            st.markdown('**Años**')
            años_seleccionados = [
                año
                for año in años_disponibles
                if st.checkbox(
                    str(año),
                    value=(año == 2026),
                    key=f'volatilidad_comparador_{año}',
                )
            ]
        with col2_graf3:
            if años_seleccionados:
                graf_dispersion_diaria = graficar_dispersion_volatilidad_diaria(
                    volatilidad_boxplot,
                    años=años_seleccionados,
                )
                graf_dispersion_diaria.update_layout(height=620)
                st.plotly_chart(
                    graf_dispersion_diaria, use_container_width=True
                )
            else:
                st.info('Selecciona al menos un año para mostrar la dispersión.')


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
        

        
