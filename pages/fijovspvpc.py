import streamlit as st
import pandas as pd
from backend_fijovspvpc import (obtener_datos_horarios, obtener_tabla_filtrada, grafico_horario_consumo, grafico_horario_coste, grafico_horario_precio, 
                                obtener_datos_por_periodo,graf_consumos_queso,graf_costes_queso,
                                optimizar_consumo_media_horaria, grafico_comparativo_perfiles, optimizar_consumo_suavizado, mapa_diferencias,
                                construir_historico_mensual_pvpc, obtener_tabla_curva_real,
                                calcular_energia_fija, costes_energia_fija_horarios)
import datetime
from calendar import monthrange
from dateutil.relativedelta import relativedelta
from datetime import timedelta
import plotly.express as px
import plotly.graph_objects as go
from utilidades import generar_menu, init_app, init_app_index
from componentes_curva import render_origen_curva, render_resumen_grafico_curva
from servicio_curva import obtener_curva_sesion
from componentes_comparativa_index_pvpc import (
    preparar_comparativa_index_pvpc,
    render_comparativa_index_pvpc,
)

if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')

generar_menu()


url_apps = 'https://powerappspy-josevidal.streamlit.app/'
url_linkedin = "https://www.linkedin.com/posts/josefvidalsierra_epowerapps-spo2425-telemindex-activity-7281942697399967744-IpFK?utm_source=share&utm_medium=member_deskto"
url_bluesky = "https://bsky.app/profile/poweravenger.bsky.social"





#DEFINIMOS CONSTANTES---------------------
#impuestos
iee = 0.051127
iva = 0.21
#costes regulados
#tp_boe_2024 = 26.36
#tp_boe_2025 = 27.63
#tp_boe_2026 = 28.43

#costes regulados €/kW año
tp_boe = {
    2024: 26.36,
    2025: 27.63,
    2026: 28.43,
}
tp_margen_pvpc = 3.12
MOSTRAR_COMPARATIVA_ANUAL_FIJO_PVPC = False

#Inicializamos variables-------------------

# valor de la potencia contratada en kW
if 'pot_con' not in st.session_state:
    st.session_state.pot_con = 4.0   
# valor del tp fijo en €/kW año
if 'tp_fijo' not in st.session_state:
    st.session_state.tp_fijo = 40.0

if 'consumo_anual' not in st.session_state:
    st.session_state.consumo_anual = 4000 #kWh

if 'precio_ene' not in st.session_state:
    st.session_state.precio_ene = 12.0   #c€/kWh
if "precio_fijo_p1" not in st.session_state:
    st.session_state.precio_fijo_p1 = 12.0
if "precio_fijo_p2" not in st.session_state:
    st.session_state.precio_fijo_p2 = 12.0
if "precio_fijo_p3" not in st.session_state:
    st.session_state.precio_fijo_p3 = 12.0
if 'precios_3p' not in st.session_state:
    st.session_state.precios_3p = False
if 'fijovspvpc_mismo_corte_anual' not in st.session_state:
    st.session_state.fijovspvpc_mismo_corte_anual = True


#obtenemos datos de backend
ultimo_registro_pvpc, dias_registrados, df_datos_horarios_combo = obtener_datos_horarios()

fecha_minima_pvpc = datetime.date(2024, 1, 1)
fecha_maxima_pvpc = pd.Timestamp(ultimo_registro_pvpc).date()
origen_consumo_actual = st.session_state.get(
    'origen_consumo_fijovspvpc', 'Perfilado'
)
curva_activa = obtener_curva_sesion(st.session_state)
rango_curva_comun = None
if origen_consumo_actual == 'Curva de carga' and curva_activa is not None:
    rango_curva = curva_activa.get('rango_fechas')
    if curva_activa.get('atr') == '2.0' and rango_curva and all(rango_curva):
        inicio_curva, fin_curva = (
            pd.Timestamp(fecha).date() for fecha in rango_curva
        )
        inicio_comun = max(fecha_minima_pvpc, inicio_curva)
        fin_comun = min(fecha_maxima_pvpc, fin_curva)
        if inicio_comun <= fin_comun:
            rango_curva_comun = (inicio_comun, fin_comun)

clave_periodo_analizado = 'fijovspvpc_periodo_analizado'
if clave_periodo_analizado not in st.session_state:
    fecha_delta_año = ultimo_registro_pvpc - relativedelta(years = 1) + timedelta(days = 1)
    st.session_state[clave_periodo_analizado] = st.session_state.get(
        'fechas_periodo', (fecha_delta_año, ultimo_registro_pvpc)
    )

if rango_curva_comun is not None:
    firma_curva = (curva_activa.get('version'), rango_curva_comun)
    if (
        st.session_state.get('_fijovspvpc_firma_curva_fechas') != firma_curva
        or st.session_state.get('_fijovspvpc_origen_anterior') != 'Curva de carga'
    ):
        st.session_state[clave_periodo_analizado] = rango_curva_comun
        st.session_state['_fijovspvpc_firma_curva_fechas'] = firma_curva
st.session_state['_fijovspvpc_origen_anterior'] = origen_consumo_actual

limites_periodo = rango_curva_comun or (fecha_minima_pvpc, fecha_maxima_pvpc)
periodo_guardado = st.session_state[clave_periodo_analizado]
if not isinstance(periodo_guardado, (tuple, list)) or len(periodo_guardado) != 2:
    st.session_state[clave_periodo_analizado] = limites_periodo
else:
    inicio_guardado, fin_guardado = (
        pd.Timestamp(fecha).date() for fecha in periodo_guardado
    )
    if (
        inicio_guardado < limites_periodo[0]
        or fin_guardado > limites_periodo[1]
        or inicio_guardado > fin_guardado
    ):
        st.session_state[clave_periodo_analizado] = limites_periodo
    else:
        st.session_state[clave_periodo_analizado] = (
            inicio_guardado, fin_guardado
        )

fecha_inicio, fecha_fin = st.session_state[clave_periodo_analizado]
fecha_inicio = pd.to_datetime(fecha_inicio)
fecha_fin = pd.to_datetime(fecha_fin) 
dias_periodo = (fecha_fin - fecha_inicio).days + 1
print('dias_periodo')
print(dias_periodo)

consumo_periodo = round(st.session_state.consumo_anual * dias_periodo / 365) #consumo perfilado del periodo
print('consumo_periodo')
print(consumo_periodo)


def dias_en_año(año):
    return 366 if pd.Timestamp(f"{año}-12-31").is_leap_year else 365

tp_coste_pvpc_kW = 0
fraccion_anual_periodo = 0

for año, tp_boe_año in tp_boe.items():

    inicio_año = max(fecha_inicio, pd.Timestamp(f"{año}-01-01"))
    fin_año = min(fecha_fin, pd.Timestamp(f"{año}-12-31"))

    if inicio_año <= fin_año:
        dias_año_periodo = (fin_año - inicio_año).days + 1
        dias_totales_año = dias_en_año(año)
        fraccion_anual_periodo += dias_año_periodo / dias_totales_año

        tp_pvpc_año = tp_boe_año + tp_margen_pvpc  # €/kW·año
        tp_coste_pvpc_kW += tp_pvpc_año * dias_año_periodo / dias_totales_año


tp_pvpc = (
    tp_coste_pvpc_kW / fraccion_anual_periodo
    if fraccion_anual_periodo
    else 0
)
tp_coste_pvpc = round(tp_coste_pvpc_kW * st.session_state.pot_con,2)  #€


usar_curva_real = False
error_curva_real = None
desvio_pvpc_perfilado = None
coste_pvpc_referencia = None
if origen_consumo_actual == 'Curva de carga' and rango_curva_comun is not None:
    try:
        (
            df_datos_horarios_combo_filtrado_consumo,
            pt_horario_filtrado,
            media_precio_perfilado,
            coste_pvpc_perfilado,
        ) = obtener_tabla_curva_real(
            df_datos_horarios_combo, curva_activa['df_norm_h'],
            fecha_inicio, fecha_fin,
        )
        consumo_periodo = float(
            df_datos_horarios_combo_filtrado_consumo['consumo'].sum()
        )
        usar_curva_real = True
    except (KeyError, ValueError) as exc:
        error_curva_real = str(exc)

if usar_curva_real:
    try:
        (_, _, _, coste_referencia) = obtener_tabla_filtrada(
            df_datos_horarios_combo, fecha_inicio, fecha_fin, consumo_periodo
        )
        if pd.notna(coste_referencia):
            coste_pvpc_referencia = float(coste_referencia)
            desvio_pvpc_perfilado = (
                coste_pvpc_perfilado - coste_pvpc_referencia
            )
    except (ValueError, ZeroDivisionError):
        pass

if not usar_curva_real:
    (
        df_datos_horarios_combo_filtrado_consumo,
        pt_horario_filtrado,
        media_precio_perfilado,
        coste_pvpc_perfilado,
    ) = obtener_tabla_filtrada(
        df_datos_horarios_combo, fecha_inicio, fecha_fin, consumo_periodo
    )

#media pvpc sin perfilar
pvpc_medio=df_datos_horarios_combo_filtrado_consumo['pvpc'].mean()

te_pvpc = media_precio_perfilado
te_coste_pvpc = round(coste_pvpc_perfilado, 2)
coste_pvpc = round((tp_coste_pvpc + te_coste_pvpc) * (1 + iee) * (1 + iva), 2)

# Cálculo del FIJO a fecha último registro
tp_margen_fijo = +round(st.session_state.tp_fijo - tp_pvpc, 2)
tp_coste_fijo = (
    st.session_state.tp_fijo
    * st.session_state.pot_con
    * fraccion_anual_periodo
)
precios_fijos_periodo = (
    [st.session_state[f'precio_fijo_p{periodo}'] for periodo in (1, 2, 3)]
    if st.session_state.precios_3p else None
)
te_coste_fijo_sin_redondeo, precio_medio_fijo = calcular_energia_fija(
    df_datos_horarios_combo_filtrado_consumo,
    st.session_state.precio_ene,
    precios_fijos_periodo,
)
te_fijo = precio_medio_fijo / 100
te_coste_fijo = round(te_coste_fijo_sin_redondeo, 2)
coste_fijo = float(f"{round((tp_coste_fijo + te_coste_fijo) * (1 + iee) * (1 + iva), 2):.2f}")

#precios medios del kWh del total de la factura en c€/kWh
media_pvpc_fra = coste_pvpc*100/consumo_periodo
media_fijo_fra = coste_fijo*100/consumo_periodo


def medias_anuales_ponderadas_pvpc(datos_horarios):
    """Precio anual PVPC ponderado directamente con cada hora del perfil REE."""
    datos = datos_horarios[['fecha', 'pvpc', 'perfil_20']].copy()
    datos['fecha'] = pd.to_datetime(datos['fecha'], errors='coerce')
    datos['pvpc'] = pd.to_numeric(datos['pvpc'], errors='coerce')
    datos['perfil_20'] = pd.to_numeric(datos['perfil_20'], errors='coerce')
    datos = datos.dropna(subset=['fecha', 'pvpc', 'perfil_20'])
    datos = datos[datos['fecha'].dt.year.between(2024, 2026)].copy()
    datos['pvpc_perfil'] = datos['pvpc'] * datos['perfil_20']
    medias = (
        datos.assign(año=datos['fecha'].dt.year)
        .groupby('año', as_index=False)
        .agg(
            suma_pvpc_perfil=('pvpc_perfil', 'sum'),
            suma_perfil=('perfil_20', 'sum'),
            ultima_fecha=('fecha', 'max'),
        )
    )
    medias = medias[medias['suma_perfil'] > 0].copy()
    medias['media_ponderada_cent_kwh'] = (
        medias['suma_pvpc_perfil'] / medias['suma_perfil'] / 10
    )
    return medias


# Comparativa anual PVPC perfilado con el mismo corte opcional en los tres años.
fecha_corte_historico = pd.Timestamp(ultimo_registro_pvpc).date()
fechas_historicas = pd.to_datetime(
    df_datos_horarios_combo['fecha'], errors='coerce'
)
mascara_historica = (
    fechas_historicas.dt.year.between(2024, 2026)
    & fechas_historicas.dt.date.le(fecha_corte_historico)
)
if st.session_state.fijovspvpc_mismo_corte_anual:
    mes_dia = fechas_historicas.dt.month * 100 + fechas_historicas.dt.day
    mes_dia_corte = fecha_corte_historico.month * 100 + fecha_corte_historico.day
    mascara_historica &= mes_dia.le(mes_dia_corte)
historico_pvpc_anual = construir_historico_mensual_pvpc(
    df_datos_horarios_combo.loc[mascara_historica],
    consumo_anual=st.session_state.consumo_anual,
    potencia_contratada=st.session_state.pot_con,
    precios_potencia_boe=tp_boe,
    margen_comercializacion=tp_margen_pvpc,
    tipo_iee=iee,
    tipo_iva=iva,
    fecha_referencia=pd.Timestamp(2027, 1, 1),
)
componentes_anuales = [
    'Potencia BOE', 'Margen comercialización', 'Energía', 'IEE', 'IVA'
]
columnas_anuales = [
    'dias_calculados', 'consumo_kwh', *componentes_anuales, 'Total factura'
]
comparativa_pvpc_anual = (
    historico_pvpc_anual.groupby('año', as_index=False)[columnas_anuales].sum()
    if not historico_pvpc_anual.empty
    else pd.DataFrame(columns=['año', *columnas_anuales])
)
if not comparativa_pvpc_anual.empty:
    medias_comparativa_anual = medias_anuales_ponderadas_pvpc(
        df_datos_horarios_combo.loc[mascara_historica]
    )
    comparativa_pvpc_anual = comparativa_pvpc_anual.merge(
        medias_comparativa_anual[['año', 'media_ponderada_cent_kwh']],
        on='año', how='inner',
    ).rename(
        columns={'media_ponderada_cent_kwh': 'precio_ponderado_cent_kwh'}
    )
    # La energía anual sale de la media horaria directa; no se promedian meses.
    comparativa_pvpc_anual['Energía'] = (
        comparativa_pvpc_anual['precio_ponderado_cent_kwh']
        / 100 * comparativa_pvpc_anual['consumo_kwh']
    )
    base_anual = (
        comparativa_pvpc_anual['Potencia BOE']
        + comparativa_pvpc_anual['Margen comercialización']
        + comparativa_pvpc_anual['Energía']
    )
    comparativa_pvpc_anual['IEE'] = base_anual * iee
    comparativa_pvpc_anual['IVA'] = (base_anual + comparativa_pvpc_anual['IEE']) * iva
    comparativa_pvpc_anual['Total factura'] = (
        base_anual + comparativa_pvpc_anual['IEE']
        + comparativa_pvpc_anual['IVA']
    )


def render_comparativa_anual_fijo_pvpc_perfilada():
    """Comparativa FIJO/PVPC anual conservada para poder mostrarla más adelante."""
    facturas = []
    for anio in (2024, 2025, 2026):
        if anio > fecha_corte_historico.year:
            continue
        inicio = datetime.date(anio, 1, 1)
        if anio == fecha_corte_historico.year:
            fin = fecha_corte_historico
        elif st.session_state.fijovspvpc_mismo_corte_anual:
            fin = datetime.date(
                anio, fecha_corte_historico.month,
                min(
                    fecha_corte_historico.day,
                    monthrange(anio, fecha_corte_historico.month)[1],
                ),
            )
        else:
            fin = datetime.date(anio, 12, 31)
        try:
            dias = (fin - inicio).days + 1
            fraccion = dias / dias_en_año(anio)
            datos, _, _, energia_pvpc = obtener_tabla_filtrada(
                df_datos_horarios_combo,
                pd.Timestamp(inicio), pd.Timestamp(fin),
                st.session_state.consumo_anual * fraccion,
            )
            if datos['fecha'].nunique() != dias:
                raise ValueError('Faltan días de precios o consumo.')
            consumo = float(datos['consumo'].sum())
            if consumo <= 0:
                raise ValueError('El consumo no es positivo.')
            potencia_pvpc = round(
                (tp_boe[anio] + tp_margen_pvpc)
                * st.session_state.pot_con * fraccion, 2,
            )
            potencia_fijo = (
                st.session_state.tp_fijo * st.session_state.pot_con * fraccion
            )
            energia_fijo, _ = calcular_energia_fija(
                datos, st.session_state.precio_ene, precios_fijos_periodo,
            )
            pvpc = round(
                (potencia_pvpc + round(energia_pvpc, 2))
                * (1 + iee) * (1 + iva), 2,
            )
            fijo = round(
                (potencia_fijo + round(energia_fijo, 2))
                * (1 + iee) * (1 + iva), 2,
            )
            diferencia = round(fijo - pvpc, 2)
            facturas.append({
                'anio': anio, 'inicio': inicio, 'fin': fin,
                'consumo': consumo, 'pvpc': pvpc, 'fijo': fijo,
                'diferencia': diferencia,
                'porcentaje': 100 * diferencia / pvpc if pvpc else 0.0,
            })
        except (KeyError, ValueError, ZeroDivisionError):
            facturas.append({
                'anio': anio, 'inicio': inicio, 'fin': fin,
                'error': 'Datos insuficientes para este año.',
            })

    st.header('Comparativa anual FIJO vs PVPC', divider='gray')
    st.caption('Perfil REE 2.0TD y el mismo corte anual seleccionado arriba.')
    validas = [factura for factura in facturas if 'error' not in factura]
    if validas:
        figura = go.Figure()
        for oferta, color in (('PVPC', '#ef4444'), ('FIJO', '#00c853')):
            importes = [factura[oferta.lower()] for factura in validas]
            textos = [
                f'{importe:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
                for importe in importes
            ]
            figura.add_trace(go.Bar(
                x=[str(factura['anio']) for factura in validas],
                y=importes, name=oferta, marker_color=color,
                customdata=textos,
                hovertemplate=f'{oferta}: %{{customdata}} €<extra></extra>',
            ))
        figura.update_layout(
            height=330, barmode='group', bargap=0.3, bargroupgap=0.12,
            barcornerradius=4, yaxis_title='Factura (€)',
            margin=dict(l=8, r=8, t=55, b=20),
            legend=dict(orientation='h', yanchor='bottom', y=1.02,
                        xanchor='center', x=0.5, font=dict(size=15)),
            hoverlabel=dict(font=dict(size=15)), hovermode='x unified',
        )
        st.plotly_chart(
            figura, use_container_width=True,
            key='fijovspvpc_facturas_anuales_fijo_pvpc',
        )
    for factura in facturas:
        with st.container(border=True):
            st.markdown(
                f"**{factura['anio']}** · Del "
                f"{factura['inicio']:%d.%m} al {factura['fin']:%d.%m}"
            )
            if 'error' in factura:
                st.warning(factura['error'])
                continue
            diferencia = factura['diferencia']
            etiqueta = (
                'AHORRO DEL FIJO' if diferencia < 0 else
                'SOBRECOSTE DEL FIJO' if diferencia > 0 else 'MISMO COSTE'
            )
            color = '#00c853' if diferencia < 0 else (
                '#ef4444' if diferencia > 0 else '#9ca3af'
            )
            impacto = f'{abs(diferencia):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
            porcentaje = f"{abs(factura['porcentaje']):.2f}".replace('.', ',')
            st.markdown(
                f'<div style="font-weight:700;color:{color};">'
                f'{etiqueta}: {impacto} € · {porcentaje} %</div>',
                unsafe_allow_html=True,
            )
            metrica_pvpc, metrica_fijo = st.columns(2)
            metrica_pvpc.metric(
                'PVPC (€)',
                f"{factura['pvpc']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'),
            )
            metrica_fijo.metric(
                'FIJO (€)',
                f"{factura['fijo']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'),
            )
            consumo_texto = f"{factura['consumo']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            st.caption(f'Consumo: {consumo_texto} kWh · Incluye IEE e IVA.')

datos_perfil_horario = df_datos_horarios_combo_filtrado_consumo[
    ['fecha', 'hora', 'consumo', 'coste']
].copy()
datos_perfil_horario['coste_energia_fijo'] = costes_energia_fija_horarios(
    df_datos_horarios_combo_filtrado_consumo,
    st.session_state.precio_ene,
    precios_fijos_periodo,
)
factor_impuestos = (1 + iee) * (1 + iva)
numero_registros_horarios = len(datos_perfil_horario)
datos_perfil_horario['coste_pvpc_total'] = (
    datos_perfil_horario['coste'] + tp_coste_pvpc / numero_registros_horarios
) * factor_impuestos
datos_perfil_horario['coste_fijo_total'] = (
    datos_perfil_horario['coste_energia_fijo']
    + tp_coste_fijo / numero_registros_horarios
) * factor_impuestos
perfil_medio_horario = datos_perfil_horario.groupby('hora', as_index=False).agg(
    consumo_medio=('consumo', 'mean'),
    coste_medio_pvpc=('coste_pvpc_total', 'mean'),
    coste_medio_fijo=('coste_fijo_total', 'mean'),
)
graf_perfil_consumo_costes = go.Figure()
graf_perfil_consumo_costes.add_trace(go.Bar(
    x=perfil_medio_horario['hora'],
    y=perfil_medio_horario['consumo_medio'],
    name='Consumo medio',
    marker_color='#3b82f6',
    opacity=0.5,
    hovertemplate='Consumo medio: %{y:.2f} kWh<extra></extra>',
))
for columna, nombre, color in (
    ('coste_medio_fijo', 'Coste medio FIJO', '#00c853'),
    ('coste_medio_pvpc', 'Coste medio PVPC', '#ef4444'),
):
    graf_perfil_consumo_costes.add_trace(go.Scatter(
        x=perfil_medio_horario['hora'],
        y=perfil_medio_horario[columna],
        mode='lines+markers',
        name=nombre,
        line=dict(color=color, width=3),
        yaxis='y2',
        hovertemplate=f'{nombre}: %{{y:.2f}} €<extra></extra>',
    ))
graf_perfil_consumo_costes.update_layout(
    height=430,
    margin=dict(l=12, r=12, t=90, b=20),
    xaxis=dict(title='Hora', dtick=2),
    yaxis=dict(title='Consumo medio (kWh)'),
    yaxis2=dict(title='Coste medio (€)', overlaying='y', side='right', showgrid=False),
    legend=dict(
        orientation='h', yanchor='bottom', y=1.02, xanchor='center', x=0.5,
        font=dict(size=16),
    ),
    hoverlabel=dict(font=dict(size=16)),
    hovermode='x unified',
    barmode='overlay',
)

fechas_coste = pd.date_range(fecha_inicio.normalize(), fecha_fin.normalize())
energia_diaria = (
    datos_perfil_horario.assign(
        fecha=pd.to_datetime(datos_perfil_horario['fecha']).dt.normalize()
    )
    .groupby('fecha')[['coste', 'coste_energia_fijo']]
    .sum()
    .reindex(fechas_coste, fill_value=0.0)
)
pesos_potencia_fijo = pd.Series(
    [1 / dias_en_año(fecha.year) for fecha in fechas_coste],
    index=fechas_coste,
)
pesos_potencia_pvpc = pd.Series(
    [
        (tp_boe[fecha.year] + tp_margen_pvpc) / dias_en_año(fecha.year)
        if fecha.year in tp_boe else 0.0
        for fecha in fechas_coste
    ],
    index=fechas_coste,
)
potencia_diaria_fijo = (
    tp_coste_fijo * pesos_potencia_fijo / pesos_potencia_fijo.sum()
)
potencia_diaria_pvpc = (
    tp_coste_pvpc * pesos_potencia_pvpc / pesos_potencia_pvpc.sum()
    if pesos_potencia_pvpc.sum() else pesos_potencia_pvpc
)
costes_diarios = pd.DataFrame(index=fechas_coste)
costes_diarios['PVPC'] = (
    energia_diaria['coste'] + potencia_diaria_pvpc
) * factor_impuestos
costes_diarios['FIJO'] = (
    energia_diaria['coste_energia_fijo'] + potencia_diaria_fijo
) * factor_impuestos
# La factura principal redondea sus términos; ajustamos solo el último día
# para que las barras mensuales y las líneas terminen en las mismas métricas.
for nombre, total in (('PVPC', coste_pvpc), ('FIJO', coste_fijo)):
    costes_diarios.loc[fechas_coste[-1], nombre] += total - costes_diarios[nombre].sum()
costes_mensuales = costes_diarios.resample('MS').sum()
costes_acumulados = costes_diarios.cumsum()

graf_costes_mensuales = go.Figure()
graf_costes_acumulados = go.Figure()
etiquetas_meses = costes_mensuales.index.strftime('%m/%Y')
for nombre, color in (('PVPC', '#ef4444'), ('FIJO', '#00c853')):
    importes_mes = costes_mensuales[nombre].map(
        lambda valor: f'{valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    )
    importes_acumulados = costes_acumulados[nombre].map(
        lambda valor: f'{valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    )
    graf_costes_mensuales.add_trace(go.Bar(
        x=etiquetas_meses,
        y=costes_mensuales[nombre],
        name=nombre,
        marker_color=color,
        customdata=importes_mes,
        hovertemplate=f'{nombre}: %{{customdata}} €<extra></extra>',
    ))
    graf_costes_acumulados.add_trace(go.Scatter(
        x=costes_acumulados.index,
        y=costes_acumulados[nombre],
        mode='lines',
        name=nombre,
        line=dict(color=color, width=3),
        customdata=importes_acumulados,
        hovertemplate=f'{nombre}: %{{customdata}} €<extra></extra>',
    ))
for figura in (graf_costes_mensuales, graf_costes_acumulados):
    figura.update_layout(
        height=360,
        margin=dict(l=12, r=12, t=60, b=55),
        yaxis_title='Coste (€)',
        legend=dict(
            orientation='h', yanchor='bottom', y=1.02,
            xanchor='center', x=0.5, font=dict(size=16),
        ),
        hoverlabel=dict(font=dict(size=16)),
        hovermode='x unified',
    )
graf_costes_mensuales.update_layout(
    barmode='group', bargap=0.3, bargroupgap=0.12,
    barcornerradius=4, xaxis_title='Mes',
)
graf_costes_mensuales.update_xaxes(tickangle=-45)
graf_costes_acumulados.update_layout(xaxis_title='Fecha')

print(f'precio energía fijo €/kWh: {te_fijo}')
print(f'coste energía fijo €: {te_coste_fijo}')
print(f'coste total fijo €: {coste_fijo}')

# Cálculo de la diferencia PVPC menos FIJO
sobrecoste_tp = round(tp_coste_fijo - tp_coste_pvpc, 2)
sobrecoste_tp_porc = round(100 * sobrecoste_tp / tp_pvpc, 2)
dif_pvpc_fijo = round(coste_fijo - coste_pvpc, 2)
dif_pvpc_fijo_porc = round(100 * dif_pvpc_fijo / coste_pvpc, 2)

if dif_pvpc_fijo < 0:
    etiqueta_impacto = 'AHORRO DEL FIJO FRENTE AL PVPC'
    color_impacto = '#00c853'
    fondo_impacto = 'rgba(0,200,83,.10)'
elif dif_pvpc_fijo > 0:
    etiqueta_impacto = 'SOBRECOSTE DEL FIJO FRENTE AL PVPC'
    color_impacto = '#ef4444'
    fondo_impacto = 'rgba(239,68,68,.10)'
else:
    etiqueta_impacto = 'FIJO Y PVPC TIENEN EL MISMO COSTE'
    color_impacto = '#9ca3af'
    fondo_impacto = 'rgba(156,163,175,.10)'

importe_impacto = f'{abs(dif_pvpc_fijo):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
porcentaje_impacto = f'{abs(dif_pvpc_fijo_porc):.2f}'.replace('.', ',')
valor_gauge = max(-50.0, min(50.0, dif_pvpc_fijo_porc))
ancho_arco = abs(valor_gauge) / 50.0 * 90
centro_arco = 90 - ancho_arco / 2 if valor_gauge >= 0 else 90 + ancho_arco / 2
gauge_impacto = go.Figure()
gauge_impacto.add_trace(go.Barpolar(
    r=[0.28, 0.28], theta=[135, 45], width=[90, 90],
    base=[0.72, 0.72],
    marker_color=['rgba(0,166,81,.16)', 'rgba(239,68,68,.16)'],
    marker_line_width=0, hoverinfo='skip', showlegend=False,
))
if ancho_arco > 0:
    gauge_impacto.add_trace(go.Barpolar(
        r=[0.28], theta=[centro_arco], width=[ancho_arco],
        base=[0.72], marker_color=color_impacto,
        marker_line_width=0, showlegend=False,
        hovertemplate=(
            f'Coste fijo − PVPC: {dif_pvpc_fijo_porc:+.2f} %<extra></extra>'
        ),
    ))
gauge_impacto.add_trace(go.Scatterpolar(
    r=[0.68, 1.05], theta=[90, 90], mode='lines',
    line=dict(color='#9ca3af', width=2),
    hoverinfo='skip', showlegend=False,
))
gauge_impacto.add_annotation(
    x=0.5, y=0.02, xref='paper', yref='paper',
    text=f'<b>{dif_pvpc_fijo_porc:+.2f} %</b>'.replace('.', ','),
    showarrow=False, font=dict(size=38, color=color_impacto),
)
for posicion_x, posicion_y, etiqueta in (
    (0.13, 0.02, '−50 %'), (0.5, 1.07, '0 %'), (0.87, 0.02, '+50 %'),
):
    gauge_impacto.add_annotation(
        x=posicion_x, y=posicion_y, text=etiqueta,
        showarrow=False, font=dict(size=12),
    )
gauge_impacto.update_layout(
    height=245, margin=dict(l=8, r=8, t=28, b=5),
    paper_bgcolor='rgba(0,0,0,0)',
    polar=dict(
        sector=[0, 180],
        radialaxis=dict(visible=False, range=[0, 1.08]),
        angularaxis=dict(visible=False),
        bgcolor='rgba(0,0,0,0)',
    ),
    barmode='overlay', showlegend=False,
)
# Cálculo del FIJO ANUAL
tp_coste_fijo_anual = st.session_state.tp_fijo * st.session_state.pot_con
tp_coste_pvpc_anual = tp_pvpc * st.session_state.pot_con
sobrecoste_tp_anual = round(tp_coste_fijo_anual - tp_coste_pvpc_anual, 2)

##GRÁFICOS 1
grafico_consumo=grafico_horario_consumo(pt_horario_filtrado)
grafico_coste=grafico_horario_coste(pt_horario_filtrado)
grafico_precio=grafico_horario_precio(pt_horario_filtrado)
grafico_precio.update_layout(
    legend=dict(
        orientation='h',
        yanchor='bottom',
        y=1.02,
        xanchor='center',
        x=0.5,
    )
)

try:
    pt_periodos_filtrado, pt_periodos_filtrado_porc, totales_periodo = obtener_datos_por_periodo(df_datos_horarios_combo_filtrado_consumo)
    graf_consumos_queso=graf_consumos_queso(pt_periodos_filtrado_porc)
    graf_costes_queso=graf_costes_queso(pt_periodos_filtrado_porc)
    consumo_periodos = pt_periodos_filtrado['consumo'].tolist()
    coste_periodos = pt_periodos_filtrado['coste'].tolist()
    error_periodos=False
except:
    error_periodos=True

print(f'error_periodo = {error_periodos}')


df_opt, df_perfiles, resumen = optimizar_consumo_media_horaria(df_datos_horarios_combo_filtrado_consumo)
df_opt_2, df_perfiles_2, resumen_2 = optimizar_consumo_suavizado(df_datos_horarios_combo_filtrado_consumo, consumo_periodo)


consumo_anual_mapa = (
    consumo_periodo * 365 / dias_periodo
    if usar_curva_real else st.session_state.consumo_anual
)
try:
    graf_mapa = mapa_diferencias(
        te_pvpc, tp_pvpc,
        consumo_anual=consumo_anual_mapa,
        precio_fijo_energia=precio_medio_fijo,
        tipo_iee=iee,
        tipo_iva=iva,
    )
except TypeError as exc:
    if 'unexpected keyword argument' not in str(exc):
        raise
    # Una sesión Streamlit abierta puede conservar una versión anterior del
    # módulo importado hasta el siguiente reinicio del servidor.
    graf_mapa = mapa_diferencias(te_pvpc, tp_pvpc)

# PESO DE LOS COMPONENTES DE LA FACTURA REGULADA
base_iee_pvpc = round(tp_coste_pvpc + te_coste_pvpc,2)
iee_coste_pvpc = round(iee * base_iee_pvpc,2)
base_iva_pvpc = round(base_iee_pvpc + iee_coste_pvpc,2)
iva_coste_pvpc = round(iva * base_iva_pvpc,2)
df_pie_pvpc = pd.DataFrame({
    "Concepto": ["Potencia", "Energía", "IEE", "IVA"],
    "Importe (€)": [tp_coste_pvpc, te_coste_pvpc, iee_coste_pvpc, iva_coste_pvpc]
})
title_pvpc = 'Peso de los componentes de la factura regulada (PVPC)'

# PESO DE LOS COMPONENTES DE LA FACTURA FIJA
base_iee_fijo = round(tp_coste_fijo + te_coste_fijo, 2)
iee_coste_fijo = round(iee * base_iee_fijo, 2)

base_iva_fijo = round(base_iee_fijo + iee_coste_fijo, 2)
iva_coste_fijo = round(iva * base_iva_fijo, 2)

df_pie_fijo = pd.DataFrame({
    "Concepto": ["Potencia", "Energía", "IEE", "IVA"],
    "Importe (€)": [tp_coste_fijo, te_coste_fijo, iee_coste_fijo, iva_coste_fijo]
})
title_fijo = 'Peso de los componentes de la factura libre (FIJO)'

def dibujar_queso_peso(df, titulo):
    fig = px.pie(
        df,
        values="Importe (€)",
        names="Concepto",
        title=titulo,
        hole=0.4,
        category_orders={"Concepto": ["Potencia", "Energía", "IEE", "IVA"]}
        
    )
    fig.update_traces(textinfo="percent+label")

    return fig

graf_queso_comp_pvpc = dibujar_queso_peso(df_pie_pvpc,title_pvpc )
graf_queso_comp_fijo = dibujar_queso_peso(df_pie_fijo, title_fijo)

historico_mensual_pvpc = construir_historico_mensual_pvpc(
    df_datos_horarios_combo,
    consumo_anual=st.session_state.consumo_anual,
    potencia_contratada=st.session_state.pot_con,
    precios_potencia_boe=tp_boe,
    margen_comercializacion=tp_margen_pvpc,
    tipo_iee=iee,
    tipo_iva=iva,
    fecha_referencia=pd.Timestamp(2027, 1, 1),
)

medias_anuales_pvpc = medias_anuales_ponderadas_pvpc(df_datos_horarios_combo)

graf_historico_precio_pvpc = px.line(
    historico_mensual_pvpc,
    x="fecha_mes",
    y="precio_ponderado_cent_kwh",
    markers=True,
    title="Evolución mensual del precio medio ponderado PVPC",
    labels={
        "fecha_mes": "Mes",
        "precio_ponderado_cent_kwh": "Precio ponderado (c€/kWh)",
    },
)
graf_historico_precio_pvpc.update_traces(
    line=dict(width=3),
    hovertemplate=(
        "%{x|%b %Y}<br>Precio ponderado: %{y:.2f} c€/kWh"
        "<extra></extra>"
    ),
)
graf_historico_precio_pvpc.update_layout(
    hoverlabel=dict(font_size=18),
    margin=dict(b=105),
)
graf_historico_precio_pvpc.update_xaxes(
    dtick="M1", tickformat="%b", title_text=None,
)
if not historico_mensual_pvpc.empty:
    graf_historico_precio_pvpc.update_xaxes(
        range=[
            historico_mensual_pvpc['fecha_mes'].min(),
            historico_mensual_pvpc['fecha_mes'].max() + pd.offsets.MonthBegin(1),
        ],
    )
    for anio, datos_anio in historico_mensual_pvpc.groupby(
        historico_mensual_pvpc['fecha_mes'].dt.year
    ):
        inicio_anio_visible = datos_anio['fecha_mes'].min()
        fin_anio_visible = datos_anio['fecha_mes'].max() + pd.offsets.MonthBegin(1)
        centro_anio = inicio_anio_visible + (
            fin_anio_visible - inicio_anio_visible
        ) / 2
        graf_historico_precio_pvpc.add_annotation(
            x=centro_anio, y=-0.24, xref='x', yref='paper',
            text=str(anio), showarrow=False,
            font=dict(size=14),
        )
for anio in sorted(historico_mensual_pvpc["fecha_mes"].dt.year.unique())[1:]:
    graf_historico_precio_pvpc.add_vline(
        x=pd.Timestamp(int(anio), 1, 1).timestamp() * 1000,
        line_width=1,
        line_dash="dash",
        line_color="rgba(180, 180, 180, 0.65)",
    )
for media_anual in medias_anuales_pvpc.itertuples():
    inicio_anio = pd.Timestamp(int(media_anual.año), 1, 1)
    fin_anio = min(
        pd.Timestamp(int(media_anual.año), 12, 31),
        pd.Timestamp(media_anual.ultima_fecha),
    )
    graf_historico_precio_pvpc.add_shape(
        type='line',
        x0=inicio_anio.timestamp() * 1000,
        x1=fin_anio.timestamp() * 1000,
        y0=media_anual.media_ponderada_cent_kwh,
        y1=media_anual.media_ponderada_cent_kwh,
        line=dict(color='#FFD54F', width=3, dash='dot'),
        layer='above',
    )

componentes_historicos = [
    "Potencia BOE", "Margen comercialización", "Energía", "IEE", "IVA"
]
historico_componentes_largo = historico_mensual_pvpc.melt(
    id_vars=["fecha_mes", "dias_calculados"],
    value_vars=componentes_historicos,
    var_name="Componente",
    value_name="Importe (€)",
)
graf_historico_componentes = px.bar(
    historico_componentes_largo,
    x="fecha_mes",
    y="Importe (€)",
    color="Componente",
    title="Evolución mensual de los componentes de la factura PVPC",
    labels={"fecha_mes": "Mes"},
    category_orders={"Componente": componentes_historicos},
    custom_data=["dias_calculados"],
)
graf_historico_componentes.update_traces(
    hovertemplate=(
        "%{x|%b %Y}<br>%{fullData.name}: %{y:.2f} €<br>"
        "Días calculados: %{customdata[0]}<extra></extra>"
    )
)
graf_historico_componentes.update_layout(barmode="stack")
graf_historico_componentes.update_xaxes(dtick="M1", tickformat="%b\n%Y")

def construir_factura_media_diaria_pvpc(datos_horarios):
    """Factura media mensual equivalente, acumulada día a día por año."""
    datos = datos_horarios[['fecha', 'pvpc', 'perfil_20']].copy()
    datos['fecha'] = pd.to_datetime(datos['fecha'], errors='coerce').dt.normalize()
    datos['pvpc'] = pd.to_numeric(datos['pvpc'], errors='coerce')
    datos['perfil_20'] = pd.to_numeric(datos['perfil_20'], errors='coerce')
    datos = datos.dropna(subset=['fecha', 'pvpc', 'perfil_20'])
    datos = datos[
        datos['fecha'].dt.year.between(2024, 2026)
        & datos['fecha'].le(pd.Timestamp(ultimo_registro_pvpc).normalize())
    ].copy()
    datos['año'] = datos['fecha'].dt.year

    facturas_diarias = []
    for año, horas in datos.groupby('año', sort=True):
        suma_perfil = horas['perfil_20'].sum()
        if suma_perfil <= 0 or año not in tp_boe:
            continue
        dias_año = dias_en_año(año)
        dias_registrados_año = horas['fecha'].nunique()
        consumo_periodo_año = (
            st.session_state.consumo_anual * dias_registrados_año / dias_año
        )
        horas = horas.copy()
        horas['coste_energia'] = (
            horas['pvpc'] / 1000 * horas['perfil_20']
            / suma_perfil * consumo_periodo_año
        )
        diario = (
            horas.groupby('fecha', as_index=False)['coste_energia'].sum()
            .sort_values('fecha')
        )
        coste_potencia_dia = (
            (tp_boe[año] + tp_margen_pvpc)
            * st.session_state.pot_con / dias_año
        )
        diario['coste_factura'] = (
            diario['coste_energia'] + coste_potencia_dia
        ) * (1 + iee) * (1 + iva)
        diario['factura_media_acumulada'] = (
            diario['coste_factura'].cumsum()
            / (pd.Series(range(1, len(diario) + 1)) * 12 / dias_año)
        )
        diario['año'] = año
        facturas_diarias.append(diario)

    if not facturas_diarias:
        return pd.DataFrame(columns=[
            'fecha', 'fecha_tipo', 'Año', 'fecha_formateada',
            'factura_media_acumulada', 'factura_media_formateada',
        ])
    resultado = pd.concat(facturas_diarias, ignore_index=True)
    resultado['fecha_tipo'] = pd.to_datetime(
        '2024-' + resultado['fecha'].dt.strftime('%m-%d')
    )
    resultado['Año'] = resultado['año'].astype(str)
    resultado['fecha_formateada'] = resultado['fecha'].dt.strftime('%d.%m.%Y')
    resultado['factura_media_formateada'] = (
        resultado['factura_media_acumulada'].map(
            lambda importe: f'{importe:,.2f}'.replace(',', 'X')
            .replace('.', ',').replace('X', '.')
        )
    )
    return resultado


facturas_diarias_pvpc = construir_factura_media_diaria_pvpc(
    df_datos_horarios_combo
)
graf_factura_media_acumulada = px.line(
    facturas_diarias_pvpc,
    x='fecha_tipo', y='factura_media_acumulada', color='Año',
    custom_data=['fecha_formateada', 'factura_media_formateada'],
    title='Evolución de la factura media mensual acumulada',
    labels={'fecha_tipo': 'Día del año',
            'factura_media_acumulada': 'Factura media (€/mes)'},
    color_discrete_map={
        '2024': '#8ecbff', '2025': '#ffd166', '2026': '#73e6a0',
    },
)
graf_factura_media_acumulada.update_traces(
    line=dict(width=3),
    hovertemplate=(
        '%{customdata[0]}<br>'
        'Factura media acumulada: %{customdata[1]} €/mes'
        '<extra>%{fullData.name}</extra>'
    ),
)
graf_factura_media_acumulada.update_layout(
    hoverlabel=dict(font_size=17),
    legend=dict(orientation='h', yanchor='bottom', y=1.02),
)
graf_factura_media_acumulada.update_xaxes(
    tickmode='array',
    tickvals=pd.date_range('2024-01-01', '2024-12-01', freq='MS'),
    ticktext=['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
              'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'],
    range=[pd.Timestamp('2024-01-01'), pd.Timestamp('2024-12-31')],
)


# BARRA LATERAL-----------------------------------------------------------------------------
st.sidebar.header('Herramientas adicionales')
with st.sidebar.form('form2'):
        st.subheader('Calcular Tp BOE anual')
        precio_tp_dia_P1 = st.number_input('potencia €/kW dia P1', min_value = 0.076, max_value = 0.192, step = .001, format  ="%f")
        precio_tp_dia_P3 = st.number_input('potencia €/kW dia P3',min_value=0.002, max_value = 0.192, step = .001, format  ="%f")
        año_boe = max(tp_boe.keys())
        precio_tp_año = round(
            (precio_tp_dia_P1 + precio_tp_dia_P3) * dias_en_año(año_boe),
            2,
        )
        tp_boe_ref = tp_boe[año_boe]
        if precio_tp_año < tp_boe_ref:
            precio_tp_año = tp_boe_ref

        st.form_submit_button('Calcular')
        st.write(f'Precio Tp anual en €/kW año = {precio_tp_año}')


# LAYAOUT DE DATOS++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
(
    tab_principal,
    tab_comparativa,
    tab_index_pvpc,
    tab_optimizacion,
) = st.tabs(
    [
        'Principal', 'PVPC perfilado', 'Index 2.0 vs PVPC',
        'Optimización',
    ]
)
col1, col2, col3 = tab_principal.columns([.3, .4, .4])
comparativa_col1, comparativa_col2, comparativa_col3 = tab_comparativa.columns(3)
optimizacion_col1, optimizacion_col2, optimizacion_col3 = (
    tab_optimizacion.columns(3)
)

with tab_index_pvpc:
    st.caption(
        "Reutiliza el histórico PVPC ya cargado en este módulo y los datos "
        "indexados disponibles en la sesión."
    )
    clave_resultado = 'comparativa_index_pvpc_resultado'
    if st.session_state.get('_comparativa_index_pvpc_version') != 2:
        st.session_state.pop(clave_resultado, None)
        st.session_state['_comparativa_index_pvpc_version'] = 2
    df_index_sesion = st.session_state.get("df_sheets")
    if df_index_sesion is None or df_index_sesion.empty:
        st.session_state.pop(clave_resultado, None)
        espacio_boton_carga = st.empty()
        if espacio_boton_carga.button(
            'Cargar indexados', key='cargar_indexados_fijovspvpc',
            type='primary',
        ):
            try:
                with st.spinner('Cargando históricos de indexados...'):
                    init_app()
                    init_app_index()
                df_index_sesion = st.session_state.get('df_sheets')
                if df_index_sesion is None or df_index_sesion.empty:
                    raise ValueError('La carga no ha devuelto datos indexados.')
                espacio_boton_carga.empty()
            except Exception as exc:
                st.error(f'No se pueden cargar los indexados: {exc}')
        if df_index_sesion is None or df_index_sesion.empty:
            st.info('Pulsa «Cargar indexados» para obtener los históricos.')

    if df_index_sesion is not None and not df_index_sesion.empty:
        if clave_resultado not in st.session_state:
            with st.spinner('Preparando la comparativa...'):
                try:
                    st.session_state[clave_resultado] = (
                        preparar_comparativa_index_pvpc(
                            df_index_sesion, df_datos_horarios_combo,
                        )
                    )
                except Exception as exc:
                    st.error(f'No se puede preparar la comparativa: {exc}')
        if clave_resultado in st.session_state:
            render_comparativa_index_pvpc(st.session_state[clave_resultado])
with col1:
    st.header('Zona de interacción', divider = 'gray')
    origen_consumo = st.radio(
        'Origen del consumo', ('Curva de carga', 'Perfilado'),
        index=1, horizontal=True, key='origen_consumo_fijovspvpc',
    )
    if origen_consumo == 'Curva de carga':
        if error_curva_real:
            st.error(f'No se puede calcular con la curva: {error_curva_real}')
        elif not usar_curva_real:
            st.warning('Carga una curva 2.0 para calcular la comparativa real.')
        with st.expander('Cargar curva de carga'):
            curva_previa = obtener_curva_sesion(st.session_state)
            version_previa = curva_previa.get('version') if curva_previa else None
            bloque_curva = st.container()
            render_origen_curva(
                bloque_curva, bloque_curva,
                clave='fijovspvpc_curva', titulo_compacto=True,
                mostrar_resumen=False, atr_fijo='2.0', permitir_qh=False,
            )
            curva_cargada = obtener_curva_sesion(st.session_state)
            if curva_cargada and curva_cargada.get('version') != version_previa:
                st.rerun()
            if (
                curva_cargada
                and any(
                    str(nombre).lower().startswith('datadis_')
                    for nombre in curva_cargada.get('nombres_archivos', [])
                )
                and isinstance(curva_cargada.get('df_in'), pd.DataFrame)
            ):
                inicio_curva, fin_curva = curva_cargada['rango_fechas']
                st.download_button(
                    'Guardar curva Datadis en CSV',
                    data=curva_cargada['df_in'].to_csv(
                        index=False, sep=';'
                    ).encode('utf-8-sig'),
                    file_name=(
                        f'curva_datadis_{inicio_curva:%Y%m%d}_'
                        f'{fin_curva:%Y%m%d}.csv'
                    ),
                    mime='text/csv',
                    key='fijovspvpc_guardar_curva_datadis',
                )
            st.caption(
                'La comparativa usa la curva real cuando hay consumo y PVPC '
                'para todas las horas del periodo seleccionado.'
            )
        with st.expander('Gráficos de la curva'):
            contenedor_graficos = st.container()
            curva_graficos = obtener_curva_sesion(st.session_state)
            datos_graficos = (
                curva_graficos.get('df_norm') if curva_graficos else None
            )
            if (
                curva_graficos and curva_graficos.get('atr') == '2.0'
                and isinstance(datos_graficos, pd.DataFrame)
                and not datos_graficos.empty
            ):
                render_resumen_grafico_curva(
                    datos_graficos,
                    clave='fijovspvpc_curva',
                    contenedor=contenedor_graficos,
                )
            else:
                st.info('Carga una curva 2.0 para ver los gráficos.')
    st.toggle('Usar tres precios de energía (c€/kWh)', key='precios_3p')
    with st.form('form_datos_comparativa', border=True):
        datos_suministro, datos_fijo = st.columns(2)
        with datos_suministro:
            st.subheader('1. Potencia y consumo')
            potencia_entrada = st.number_input(
                'Potencias contratadas P1, P3 (kW)',
                min_value=1.0, max_value=9.9, step=0.1,
                value=float(st.session_state.pot_con),
                format='%0.1f', key='fijovspvpc_pot_con_input',
            )
            consumo_entrada = st.number_input(
                'Consumo :blue[ANUAL] estimado (kWh)',
                min_value=500, max_value=7000, step=100,
                value=int(st.session_state.consumo_anual),
                key='fijovspvpc_consumo_anual_input',
                disabled=origen_consumo == 'Curva de carga',
            )
        with datos_fijo:
            st.subheader('2. Contrato a precio fijo')
            potencia_fija_entrada = st.number_input(
                'Término de potencia (€/kW año)',
                min_value=float(tp_boe_ref), max_value=80.0, step=0.1,
                value=float(st.session_state.tp_fijo),
                format='%0.1f', key='fijovspvpc_tp_fijo_input',
            )
            precios_periodo_entrada = {}
            if st.session_state.precios_3p:
                for periodo in ('p1', 'p2', 'p3'):
                    precios_periodo_entrada[periodo] = st.number_input(
                        f'Precio {periodo.upper()} (c€/kWh)',
                        min_value=0.0, step=0.001,
                        value=float(st.session_state[f'precio_fijo_{periodo}']),
                        format='%0.3f',
                        key=f'fijovspvpc_precio_fijo_{periodo}_input',
                    )
            else:
                precio_energia_entrada = st.number_input(
                    'Término de energía (c€/kWh)',
                    min_value=5.0, max_value=30.0, step=0.1,
                    value=float(st.session_state.precio_ene),
                    format='%0.1f', key='fijovspvpc_precio_ene_input',
                )
        aplicar_datos = st.form_submit_button('Actualizar cálculos')
    if aplicar_datos:
        st.session_state.pot_con = potencia_entrada
        st.session_state.tp_fijo = potencia_fija_entrada
        if origen_consumo == 'Perfilado':
            st.session_state.consumo_anual = consumo_entrada
        if st.session_state.precios_3p:
            for periodo, precio in precios_periodo_entrada.items():
                st.session_state[f'precio_fijo_{periodo}'] = precio
        else:
            st.session_state.precio_ene = precio_energia_entrada
        st.rerun()
    st.write(f'El precio fijo medio es :red[{precio_medio_fijo:.2f}] c€/kWh')

    with st.form(border=True, key = 'form_fechas'):
        st.subheader('3.Introduce datos del periodo a analizar')
        st.caption(f'El último registro PVPC disponible es del  :blue[{ultimo_registro_pvpc.strftime("%d.%m.%Y")}]. Número de dias registrados: :blue[{dias_registrados}]')
        if rango_curva_comun is not None:
            st.caption(
                'Rango disponible en la curva y el PVPC: '
                f'{rango_curva_comun[0]:%d.%m.%Y}–'
                f'{rango_curva_comun[1]:%d.%m.%Y}.'
            )
        elif origen_consumo == 'Curva de carga' and curva_activa is not None:
            st.warning(
                'La curva activa no es 2.0 o no coincide en fechas con el PVPC.'
            )
        periodo_entrada = st.date_input('Selecciona el periodo a analizar',
            value=st.session_state[clave_periodo_analizado],
            min_value=limites_periodo[0],
            max_value=limites_periodo[1],
            format = "DD.MM.YYYY",
            )
        aplicar_periodo = st.form_submit_button('Actualizar cálculos')
    if aplicar_periodo:
        if isinstance(periodo_entrada, (tuple, list)) and len(periodo_entrada) == 2:
            st.session_state[clave_periodo_analizado] = tuple(periodo_entrada)
            st.rerun()
        else:
            st.warning('Selecciona una fecha inicial y otra final.')

with comparativa_col1:
    st.header('Comparativa factura anual PVPC', divider='gray')
    st.toggle(
        'Comparar los tres años hasta el último día disponible',
        key='fijovspvpc_mismo_corte_anual',
        help=(
            'Aplica el mismo día y mes de corte a 2024, 2025 y 2026. '
            'Si se desactiva, muestra completos los años anteriores.'
        ),
    )
    meses_es = (
        'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
        'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
    )
    fecha_corte_texto = (
        f'{fecha_corte_historico.day} de '
        f'{meses_es[fecha_corte_historico.month - 1]}'
    )
    if st.session_state.fijovspvpc_mismo_corte_anual:
        texto_periodo_anual = (
            f'Del 1 de enero al {fecha_corte_texto} en los tres años.'
        )
    else:
        texto_periodo_anual = (
            f'2024 y 2025 completos; 2026 hasta el '
            f'{fecha_corte_texto}.'
        )
    potencia_anual_texto = f'{st.session_state.pot_con:,.1f}'.replace('.', ',')
    consumo_anual_texto = f'{st.session_state.consumo_anual:,.0f}'.replace(',', '.')
    st.info(
        f'{texto_periodo_anual} La factura PVPC de cada año se calcula con '
        'su perfil REE 2.0TD y las mismas condiciones de suministro.\n\n'
        f'**Potencia:** {potencia_anual_texto} kW · '
        f'**Consumo anual estimado:** {consumo_anual_texto} kWh'
    )
    if comparativa_pvpc_anual.empty:
        st.info('No hay datos anuales de PVPC disponibles.')
    else:
        comparativa_pvpc_anual = comparativa_pvpc_anual.sort_values('año')
        columnas_metricas_anuales = st.columns(len(comparativa_pvpc_anual))
        precio_anterior_anual = None
        for columna, fila in zip(
            columnas_metricas_anuales, comparativa_pvpc_anual.itertuples()
        ):
            precio = fila.precio_ponderado_cent_kwh
            delta = None
            if precio_anterior_anual not in (None, 0):
                delta = f'{(precio / precio_anterior_anual - 1) * 100:+.2f} %'
            columna.metric(
                f'{int(fila.año)} · PVPC ponderado',
                f'{precio:.2f} c€/kWh'.replace('.', ','),
                delta,
                delta_color='inverse',
            )
            precio_anterior_anual = precio

        componentes_anuales_largo = comparativa_pvpc_anual.melt(
            id_vars=['año'],
            value_vars=componentes_anuales,
            var_name='Componente',
            value_name='Importe (€)',
        )
        graf_comparativa_anual = px.bar(
            componentes_anuales_largo,
            x='año',
            y='Importe (€)',
            color='Componente',
            category_orders={'Componente': componentes_anuales},
            title='Factura estimada · comparativa anual',
            labels={'año': 'Año'},
        )
        graf_comparativa_anual.update_layout(
            barmode='stack', bargap=0.55, barcornerradius=8,
        )
        graf_comparativa_anual.update_xaxes(dtick=1)
        graf_comparativa_anual.update_traces(
            hovertemplate=(
                'Año %{x}<br>%{fullData.name}: %{y:.2f} €<extra></extra>'
            )
        )
        textos_totales_anuales = []
        total_anterior_anual = None
        for total in comparativa_pvpc_anual['Total factura']:
            total_formateado = (
                f'{total:,.2f} €'.replace(',', 'X').replace('.', ',').replace('X', '.')
            )
            if total_anterior_anual not in (None, 0):
                variacion = (total / total_anterior_anual - 1) * 100
                total_formateado += f'<br>{variacion:+.2f} %'.replace('.', ',')
            textos_totales_anuales.append(total_formateado)
            total_anterior_anual = total
        graf_comparativa_anual.add_scatter(
            x=comparativa_pvpc_anual['año'],
            y=comparativa_pvpc_anual['Total factura'],
            mode='text',
            text=textos_totales_anuales,
            textposition='top center',
            textfont=dict(size=14),
            cliponaxis=False,
            hoverinfo='skip',
            showlegend=False,
        )
        st.plotly_chart(
            graf_comparativa_anual,
            use_container_width=True,
            key='fijovspvpc_comparativa_pvpc_anual',
        )
    if MOSTRAR_COMPARATIVA_ANUAL_FIJO_PVPC:
        render_comparativa_anual_fijo_pvpc_perfilada()

with comparativa_col3:
    st.header('Gráficos adicionales', divider='gray')
    with st.expander('Evolución mensual del precio medio PVPC'):
        st.caption(
            'Precio de energía ponderado con el perfil 2.0TD. Los meses cerrados '
            'se muestran completos; el mes actual llega hasta el último registro PVPC.'
        )
        columnas_medias_anuales = st.columns(3)
        medias_por_anio = medias_anuales_pvpc.set_index('año')
        for columna_media, anio_media in zip(columnas_medias_anuales, [2024, 2025, 2026]):
            if anio_media in medias_por_anio.index:
                valor_media = medias_por_anio.loc[
                    anio_media, 'media_ponderada_cent_kwh'
                ]
                etiqueta_media = f'Media {anio_media}'
                if anio_media == 2026:
                    etiqueta_media += ' (acum.)'
                columna_media.metric(
                    etiqueta_media,
                    f'{valor_media:.2f} c€/kWh'.replace('.', ','),
                )
        st.plotly_chart(graf_historico_precio_pvpc, use_container_width=True)
    with st.expander('Evolución de la factura mensual PVPC'):
        st.plotly_chart(graf_historico_componentes, use_container_width=True)
    with st.expander('Evolución de la factura media acumulada'):
        st.caption(
            'Evolución diaria de la factura media mensual equivalente desde '
            'enero de cada año, con energía, potencia, IEE e IVA.'
        )
        st.plotly_chart(graf_factura_media_acumulada, use_container_width=True)


    

with col2:

    # Algunos datos de salida a mostrar
    st.header('Resultado de la comparativa FIJO vs PVPC', divider = 'gray')
    potencia_resumen = f'{st.session_state.pot_con:.1f}'.replace('.', ',')
    consumo_resumen = (
        f'{consumo_periodo:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    )
    st.markdown(
        f'**Potencia del suministro:** {potencia_resumen} kW · '
        f'**Consumo del periodo:** {consumo_resumen} kWh'
    )
    st.caption(
        'Comparativa con consumo real de la curva.' if usar_curva_real
        else 'Comparativa con consumo estimado según el perfil REE 2.0TD.'
    )
    st.markdown(
        f'<div style="padding:1rem;border:1px solid {color_impacto};'
        f'border-left:6px solid {color_impacto};border-radius:.75rem;'
        f'background:{fondo_impacto};text-align:center;">'
        f'<div style="font-size:.82rem;font-weight:800;letter-spacing:.07em;'
        f'color:{color_impacto};">{etiqueta_impacto}</div>'
        f'<div style="font-size:2rem;font-weight:800;line-height:1.2;'
        f'color:{color_impacto};margin-top:.25rem;">'
        f'{importe_impacto} € · {porcentaje_impacto} %</div>'
        f'<div style="font-size:.85rem;margin-top:.35rem;opacity:.8;">'
        f'Del {fecha_inicio:%d.%m.%Y} al {fecha_fin:%d.%m.%Y}</div></div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        gauge_impacto, use_container_width=True,
        key='fijovspvpc_gauge_impacto',
        config={'displayModeBar': False},
    )
    st.caption('Gauge: negativo = ahorro del fijo; positivo = sobrecoste. Escala ±50 %.')
    metrica_pvpc, metrica_fijo, metrica_diferencial = st.columns(3)
    metrica_pvpc.metric(
        'Coste factura PVPC (€)',
        f'{coste_pvpc:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'),
    )
    metrica_pvpc.metric(
        'Precio factura PVPC (c€/kWh)',
        f'{media_pvpc_fra:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'),
        help='Incluye todos los componentes de la factura PVPC.',
    )
    metrica_pvpc.metric(
        'Media ponderada del PVPC (c€/kWh)',
        f'{te_pvpc * 100:,.2f}'.replace('.', ','),
        help='Precio de la energía PVPC ponderado por el consumo del periodo.',
    )
    metrica_fijo.metric(
        'Coste factura FIJO (€)',
        f'{coste_fijo:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'),
    )
    metrica_fijo.metric(
        'Precio factura FIJO (c€/kWh)',
        f'{media_fijo_fra:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'),
        help='Incluye todos los componentes de la factura fija.',
    )
    metrica_fijo.metric(
        'Media ponderada del FIJO (c€/kWh)',
        f'{precio_medio_fijo:,.2f}'.replace('.', ','),
        help='Precio de la energía fija ponderado por el consumo de cada periodo tarifario.',
    )
    metrica_diferencial.metric(
        'Diferencial FIJO − PVPC (€)',
        f'{dif_pvpc_fijo:+,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'),
        delta=f'{dif_pvpc_fijo_porc:+.2f} %'.replace('.', ','),
        delta_color='inverse',
        help='Coste fijo menos coste PVPC. Un valor negativo indica ahorro.',
    )
    with st.expander('Datos adicionales sobre PVPC'):
        st.metric(
            'Precio medio aritmético del PVPC (c€/kWh)',
            f'{pvpc_medio / 10:,.2f}'.replace('.', ','),
            help='Precio medio del PVPC sin ponderar por el consumo (c€/kWh)',
        )
        st.metric(
            'Coste del Te PVPC (€)',
            f'{te_coste_pvpc:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'),
        )

    with st.expander('Desglose del PVPC por periodo'):
        desglose_pvpc = pt_periodos_filtrado.copy()
        for columna, decimales in [('consumo', 2), ('coste', 2), ('precio', 6)]:
            desglose_pvpc[columna] = desglose_pvpc[columna].map(
                lambda valor: f'{valor:,.{decimales}f}'
                .replace(',', 'X').replace('.', ',').replace('X', '.')
            )
        st.dataframe(desglose_pvpc, hide_index=True, use_container_width=True)
    
    with st.expander('Datos adicionales oferta FIJO'):
        st.markdown(
            ':blue-background[Obtén información del sobrecoste del término '
            'de potencia. Sección **Fernando Sánchez Rey-Maeso**]',
            help='Sobrecoste con respecto al margen regulado del PVPC (2)',
        )
        col111, col112, col113 = st.columns(3)
        with col111:
            st.metric('Margen Tp (€/kW año)', f'{tp_margen_fijo:,.2f}'.replace('.', ','))
        with col112:
            st.metric('Sobrecoste Tp (€)', f'{sobrecoste_tp:,.2f}'.replace('.', ','))
        with col113:
            with st.container(border=True):
                st.metric(
                    'Sobrecoste Tp ANUAL (€)',
                    f'{sobrecoste_tp_anual:,.2f}'.replace('.', ','),
                    f'{sobrecoste_tp_porc:,.2f}%'.replace('.', ','),
                    'inverse',
                )

    

    col3.header('Info adicional', divider='gray')
    with col3.expander('Peso de los componentes de la factura'):
        st.plotly_chart(
            graf_queso_comp_pvpc,
            use_container_width=True,
            key='fijovspvpc_componentes_pvpc_info',
        )
        st.plotly_chart(
            graf_queso_comp_fijo,
            use_container_width=True,
            key='fijovspvpc_componentes_fijo_info',
        )
    with col3.expander('Distribución de consumos y costes PVPC por periodo'):
        if not error_periodos:
            col301, col302 = st.columns(2)
            with col301:
                st.plotly_chart(graf_consumos_queso, use_container_width=True)
            with col302:
                st.plotly_chart(graf_costes_queso, use_container_width=True)
        else:
            st.error('No se disponen de datos de periodos dh para el mes en curso.')

    with col3.expander('Perfil medio horario de consumo y costes'):
        st.caption(
            'Consumo medio por hora y costes medios horarios FIJO y PVPC '
            'del periodo seleccionado, con potencia, IEE e IVA.'
        )
        st.plotly_chart(
            graf_perfil_consumo_costes,
            use_container_width=True,
            key='fijovspvpc_perfil_consumo_costes',
        )

    with col3.expander('Costes mensuales y acumulados'):
        st.caption(
            'Costes del periodo seleccionado con energía, potencia, IEE e IVA; '
            'sin alquiler de medida.'
        )
        st.subheader('Coste total por mes')
        st.plotly_chart(
            graf_costes_mensuales,
            use_container_width=True,
            key='fijovspvpc_costes_mensuales',
        )
        st.subheader('Coste acumulado')
        st.plotly_chart(
            graf_costes_acumulados,
            use_container_width=True,
            key='fijovspvpc_costes_acumulados',
        )

    with col3.expander('Mapa comparativo FIJO vs PVPC'):
        st.caption('Importes anuales con IEE e IVA.')
        if usar_curva_real:
            st.caption(
                'Escala el consumo real del periodo a 365 días para representar '
                'una oferta anual.'
            )
        st.plotly_chart(graf_mapa, use_container_width=True)

    comparativa_col2.header('Comparativa factura mensual PVPC', divider='gray')
    if usar_curva_real:
        comparativa_col2.caption(
            'Histórico estimado con el perfil REE 2.0TD; no usa la curva real.'
        )
    nombres_meses = {
        1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
        5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
        9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre',
    }
    fechas_historico = pd.to_datetime(
        df_datos_horarios_combo['fecha'], errors='coerce'
    )
    anio_comparacion = min(pd.Timestamp.today().year, fechas_historico.dt.year.max())
    meses_disponibles = sorted(
        fechas_historico.loc[fechas_historico.dt.year == anio_comparacion]
        .dt.month.dropna().astype(int).unique(),
        reverse=True,
    )

    if meses_disponibles:
        mes_comparacion = comparativa_col2.selectbox(
            f'Mes de {anio_comparacion}',
            options=meses_disponibles,
            format_func=lambda mes: nombres_meses[mes],
            key='mes_comparacion_pvpc',
        )
        mascara_mes = (
            fechas_historico.dt.month.eq(mes_comparacion)
            & fechas_historico.dt.year.between(anio_comparacion - 2, anio_comparacion)
        )
        datos_mes_comparacion = df_datos_horarios_combo.loc[mascara_mes].copy()
        ultima_fecha_mes = fechas_historico.loc[
            fechas_historico.dt.year.eq(anio_comparacion)
            & fechas_historico.dt.month.eq(mes_comparacion)
        ].max()
        comparativa_mes = construir_historico_mensual_pvpc(
            datos_mes_comparacion,
            consumo_anual=st.session_state.consumo_anual,
            potencia_contratada=st.session_state.pot_con,
            precios_potencia_boe=tp_boe,
            margen_comercializacion=tp_margen_pvpc,
            tipo_iee=iee,
            tipo_iva=iva,
            fecha_referencia=ultima_fecha_mes,
        ).sort_values('año')

        if not comparativa_mes.empty:
            dia_corte = int(comparativa_mes['dias_calculados'].min())
            comparativa_col2.info(
                'Selecciona un mes. Se compara ese mes del año en curso con '
                'el mismo mes de los otros años. Si es el mes actual, se '
                'tienen en cuenta los datos hasta el último día disponible.\n\n'
                f'**{nombres_meses[mes_comparacion]}:** del día 1 al '
                f'{dia_corte} en los tres años.\n\n'
                f'**Potencia:** {potencia_anual_texto} kW · '
                f'**Consumo anual estimado:** {consumo_anual_texto} kWh'
            )
            columnas_metricas = comparativa_col2.columns(len(comparativa_mes))
            precio_anterior = None
            for columna, fila in zip(columnas_metricas, comparativa_mes.itertuples()):
                precio = fila.precio_ponderado_cent_kwh
                delta = None
                if precio_anterior not in (None, 0):
                    delta = f'{(precio / precio_anterior - 1) * 100:+.2f} %'
                columna.metric(
                    f'{int(fila.año)} · PVPC ponderado',
                    f'{precio:.2f} c€/kWh'.replace('.', ','),
                    delta,
                    delta_color='inverse',
                )
                precio_anterior = precio

            componentes_comparacion = [
                'Potencia BOE', 'Margen comercialización', 'Energía', 'IEE', 'IVA'
            ]
            comparativa_componentes = comparativa_mes.melt(
                id_vars=['año'],
                value_vars=componentes_comparacion,
                var_name='Componente',
                value_name='Importe (€)',
            )
            graf_comparativa_mes = px.bar(
                comparativa_componentes,
                x='año',
                y='Importe (€)',
                color='Componente',
                category_orders={'Componente': componentes_comparacion},
                title=f'Factura estimada · {nombres_meses[mes_comparacion]}',
                labels={'año': 'Año'},
            )
            graf_comparativa_mes.update_layout(
                barmode='stack',
                bargap=0.55,
                barcornerradius=8,
            )
            graf_comparativa_mes.update_xaxes(dtick=1)
            graf_comparativa_mes.update_traces(
                hovertemplate=(
                    'Año %{x}<br>%{fullData.name}: %{y:.2f} €<extra></extra>'
                )
            )
            textos_totales = []
            total_anterior = None
            for total in comparativa_mes['Total factura']:
                total_formateado = (
                    f'{total:,.2f} €'.replace(',', 'X').replace('.', ',').replace('X', '.')
                )
                if total_anterior not in (None, 0):
                    variacion = (total / total_anterior - 1) * 100
                    total_formateado += f'<br>{variacion:+.2f} %'.replace('.', ',')
                textos_totales.append(total_formateado)
                total_anterior = total
            graf_comparativa_mes.add_scatter(
                x=comparativa_mes['año'],
                y=comparativa_mes['Total factura'],
                mode='text',
                text=textos_totales,
                textposition='top center',
                textfont=dict(size=14),
                cliponaxis=False,
                hoverinfo='skip',
                showlegend=False,
            )
            comparativa_col2.plotly_chart(
                graf_comparativa_mes, use_container_width=True
            )
    else:
        comparativa_col2.info(
            f'No hay datos mensuales disponibles para {anio_comparacion}.'
        )

with comparativa_col3:
    with st.expander(
        'Curvas horarias reales del PVPC' if usar_curva_real
        else 'Curvas horarias perfiladas del PVPC'
    ):
        st.write(grafico_consumo)
        st.write(grafico_coste)
        st.write(grafico_precio)


with optimizacion_col1:
    #st.header('Optimización burda del consumo', divider = 'gray')
    #st.plotly_chart(grafico_comparativo_perfiles(df_perfiles))

    #col31, col32, col33, col34 = st.columns(4)
    #with col31:
    #    st.metric("Coste original", f"{resumen['coste_original']:.2f} €")
    #with col32:
    #    st.metric("Coste optimizado", f"{resumen['coste_optimizado']:.2f} €")
    #with col33:
    #    st.metric("Ahorro absoluto", f"{resumen['ahorro_abs']:.2f} €")
    #with col34:
    #    st.metric("Ahorro relativo", f"{resumen['ahorro_pct']:.2f} %")

    
    st.header('Optimización del consumo (en pruebas)', divider = 'gray')
    st.plotly_chart(grafico_comparativo_perfiles(df_perfiles_2))

    col31, col32, col33, col34 = st.columns(4)
    with col31:
        st.metric("Coste original", f"{resumen_2['coste_original']:.2f} €")
    with col32:
        st.metric("Coste optimizado", f"{resumen_2['coste_optimizado']:.2f} €")
    with col33:
        st.metric("Ahorro absoluto", f"{resumen_2['ahorro_abs']:.2f} €")
    with col34:
        st.metric("Ahorro relativo", f"{resumen_2['ahorro_pct']:.2f} %")

        



