import streamlit as st
import pandas as pd
from backend_fijovspvpc import (obtener_datos_horarios, obtener_tabla_filtrada, grafico_horario_consumo, grafico_horario_coste, grafico_horario_precio, 
                                obtener_datos_por_periodo,graf_consumos_queso,graf_costes_queso,
                                optimizar_consumo_media_horaria, grafico_comparativo_perfiles, optimizar_consumo_suavizado, mapa_diferencias,
                                construir_historico_mensual_pvpc)
import datetime
import numpy as np
from dateutil.relativedelta import relativedelta
from datetime import timedelta
import plotly.express as px
from utilidades import generar_menu

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

#Inicializamos variables-------------------

# valor de la potencia contratada en kW
if 'pot_con' not in st.session_state:
    st.session_state.pot_con = 4.0   
# valor del tp fijo en €/kW año
if 'tp_fijo' not in st.session_state:
    st.session_state.tp_fijo = 40 

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


#obtenemos datos de backend
ultimo_registro_pvpc, dias_registrados, df_datos_horarios_combo = obtener_datos_horarios()

if 'fechas_periodo' not in st.session_state:
    fecha_delta_año = ultimo_registro_pvpc - relativedelta(years = 1) + timedelta(days = 1)
    st.session_state.fechas_periodo = (fecha_delta_año, ultimo_registro_pvpc)


fecha_inicio, fecha_fin = st.session_state.fechas_periodo 
fecha_inicio = pd.to_datetime(fecha_inicio)
fecha_fin = pd.to_datetime(fecha_fin) 
dias_periodo = (fecha_fin - fecha_inicio).days + 1
print('dias_periodo')
print(dias_periodo)

consumo_periodo = round(st.session_state.consumo_anual * dias_periodo / 365) #consumo del periodo seleccionado
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


df_datos_horarios_combo_filtrado_consumo, pt_horario_filtrado, media_precio_perfilado, coste_pvpc_perfilado = obtener_tabla_filtrada(df_datos_horarios_combo, fecha_inicio, fecha_fin, consumo_periodo)

#media pvpc sin perfilar
pvpc_medio=df_datos_horarios_combo_filtrado_consumo['pvpc'].mean()

te_pvpc = media_precio_perfilado
te_coste_pvpc = round(te_pvpc * consumo_periodo, 2)
coste_pvpc = round((tp_coste_pvpc + te_coste_pvpc) * (1 + iee) * (1 + iva), 2)

# Cálculo del FIJO a fecha último registro
tp_margen_fijo = +round(st.session_state.tp_fijo - tp_pvpc, 2)
tp_coste_fijo = (
    st.session_state.tp_fijo
    * st.session_state.pot_con
    * fraccion_anual_periodo
)
te_fijo = st.session_state.precio_ene / 100
te_coste_fijo = round(te_fijo * consumo_periodo, 2)
coste_fijo = float(f"{round((tp_coste_fijo + te_coste_fijo) * (1 + iee) * (1 + iva), 2):.2f}")

#precios medios del kWh del total de la factura en c€/kWh
media_pvpc_fra = coste_pvpc*100/consumo_periodo
media_fijo_fra = coste_fijo*100/consumo_periodo

print(f'precio energía fijo €/kWh: {te_fijo}')
print(f'coste energía fijo €: {te_coste_fijo}')
print(f'coste total fijo €: {coste_fijo}')

# Cálculo de la diferencia PVPC menos FIJO
sobrecoste_tp = round(tp_coste_fijo - tp_coste_pvpc, 2)
sobrecoste_tp_porc = round(100 * sobrecoste_tp / tp_pvpc, 2)
dif_pvpc_fijo = round(coste_fijo - coste_pvpc, 2)
dif_pvpc_fijo_porc = round(100 * dif_pvpc_fijo / coste_pvpc, 2)
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
    #st.session_state.porcentajes_consumo = pt_periodos_filtrado_porc['consumo'].tolist()
    consumo_periodos = pt_periodos_filtrado['consumo'].tolist()
    coste_periodos = pt_periodos_filtrado['coste'].tolist()
    #precios_fijo  = [c / con if con != 0 else 0 for c, con in zip(coste_periodos, consumo_periodos)]
    #print (precios_fijo)
    #st.session_state.precio_ene = np.sum(np.multiply(st.session_state.porcentajes_consumo, precios_fijo))
    error_periodos=False
except:
    error_periodos=True

if 'porcentajes_consumo' not in st.session_state:
    st.session_state.porcentajes_consumo = pt_periodos_filtrado_porc['consumo'].tolist()

#precios_fijo = np.divide(st.session_state.precio_ene, st.session_state.porcentajes_consumo)


print(f'error_periodo = {error_periodos}')
#if 'porcentajes_consumo' in st.session_state:
#    porcentajes_consumo=st.session_state['porcentajes_consumo']


if 'precios_3p' not in st.session_state:
    st.session_state.precios_3p = False
    #st.session_state.porcentajes_consumo = [0.0, 0.0, 0.0]


df_opt, df_perfiles, resumen = optimizar_consumo_media_horaria(df_datos_horarios_combo_filtrado_consumo)
df_opt_2, df_perfiles_2, resumen_2 = optimizar_consumo_suavizado(df_datos_horarios_combo_filtrado_consumo, st.session_state.consumo_anual)


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
    fecha_referencia=pd.Timestamp.today(),
)

datos_media_anual = df_datos_horarios_combo[['fecha', 'pvpc', 'perfil_20']].copy()
datos_media_anual['fecha'] = pd.to_datetime(
    datos_media_anual['fecha'], errors='coerce'
)
datos_media_anual['pvpc'] = pd.to_numeric(
    datos_media_anual['pvpc'], errors='coerce'
)
datos_media_anual['perfil_20'] = pd.to_numeric(
    datos_media_anual['perfil_20'], errors='coerce'
)
datos_media_anual = datos_media_anual.dropna(
    subset=['fecha', 'pvpc', 'perfil_20']
)
datos_media_anual = datos_media_anual[
    datos_media_anual['fecha'].dt.year.between(2024, 2026)
].copy()
datos_media_anual['pvpc_perfil'] = (
    datos_media_anual['pvpc'] * datos_media_anual['perfil_20']
)
medias_anuales_pvpc = (
    datos_media_anual.assign(año=datos_media_anual['fecha'].dt.year)
    .groupby('año', as_index=False)
    .agg(
        suma_pvpc_perfil=('pvpc_perfil', 'sum'),
        suma_perfil=('perfil_20', 'sum'),
        ultima_fecha=('fecha', 'max'),
    )
)
medias_anuales_pvpc = medias_anuales_pvpc[
    medias_anuales_pvpc['suma_perfil'] > 0
].copy()
medias_anuales_pvpc['media_ponderada_cent_kwh'] = (
    medias_anuales_pvpc['suma_pvpc_perfil']
    / medias_anuales_pvpc['suma_perfil']
    / 10
)

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
graf_historico_precio_pvpc.update_xaxes(dtick="M1", tickformat="%b\n%Y")
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
    tab_factura,
    tab_comparativa,
    tab_pvpc_te,
    tab_optimizacion,
) = st.tabs(
    ['Principal', 'Factura', 'Comparativa', 'PVPC Te', 'Optimización']
)
col1, col2, col3 = tab_principal.columns([.3, .4, .4])
factura_col1, factura_col2, factura_col3 = tab_factura.columns(3)
comparativa_col1, comparativa_col2, comparativa_col3 = tab_comparativa.columns(3)
pvpc_te_col1, pvpc_te_col2, pvpc_te_col3 = tab_pvpc_te.columns(3)
optimizacion_col1, optimizacion_col2, optimizacion_col3 = (
    tab_optimizacion.columns(3)
)
with col1:
    st.header('Zona de interacción', divider = 'gray')
    #with st.form('form1'):
    with st.container(border=True):
        st.subheader('1. Introduce datos de potencia y consumo')
        st.slider('Potencias Contratadas P1, P3 (kW)', min_value = 1.0, max_value = 9.9, step = .1, key = 'pot_con')
        st.slider('Consumo :blue[ANUAL] estimado (kWh)',min_value = 500, max_value = 7000, step = 100, key = 'consumo_anual')
    with st.container(border=True):
        st.subheader('2.Introduce datos del contrato a precio fijo')
        st.slider('Precio ofertado: término de potencia (€/kW año)', min_value = tp_boe_ref, max_value = 80.0, step =.1, key = 'tp_fijo')


        st.toggle('Usar tres precios de energía (c€/kWh)', key = 'precios_3p')
        zona_precios = st.empty()
        
        if not st.session_state.precios_3p:
            zona_precios.slider('Precio ofertado: término de energía (c€/kWh)' ,min_value = 5.0, max_value = 30.0, step = .1, key = 'precio_ene')
            #st.session_state.precio_fijo_p1 = st.session_state.precio_ene       
        else:
            #st.session_state.precio_fijo_p1 = st.session_state.precio_ene 
            #st.session_state.precio_fijo_p2 = st.session_state.precio_ene
            #st.session_state.precio_fijo_p3 = st.session_state.precio_ene
            col21, col22, col23 = st.columns(3)
            with col21:           
                #precio_fijo_p1 = st.number_input('Precio P1', value = 0.160, step = 0.001, format = '%0.3f') 
                st.number_input('Precio P1', step = 0.001, format = '%0.3f', key = 'precio_fijo_p1')  #value = 0.160,
            with col22:
                st.number_input('Precio P2', step = 0.001, format = '%0.3f', key = 'precio_fijo_p2') # ,value = 0.130
            with col23:
                st.number_input('Precio P3', step = 0.001, format = '%0.3f', key = 'precio_fijo_p3') #, value = 0.110

            precios_fijo = [st.session_state.precio_fijo_p1, st.session_state.precio_fijo_p2, st.session_state.precio_fijo_p3]
            st.session_state.precio_ene = np.sum(np.multiply(st.session_state.porcentajes_consumo, precios_fijo))/100
            #print(precio_ene)
        
        #if precio_ene != st.session_state.precio_ene:        
        #    st.session_state.precio_ene = precio_ene
        st.write(f'El precio fijo medio es :red[{st.session_state.precio_ene:.2f}]c€/kWh')
        #st.rerun()  
        
    with st.form(border=True, key = 'form_fechas'):
        st.subheader('3.Introduce datos del periodo a analizar')
        st.caption(f'El último registro PVPC disponible es del  :blue[{ultimo_registro_pvpc.strftime("%d.%m.%Y")}]. Número de dias registrados: :blue[{dias_registrados}]')
        #st.caption(f'Número de dias registrados 2024: :blue[{dias_registrados}]')
        st.date_input('Selecciona el periodo a analizar', 
            #(datetime.date(2024, 1, 1), ultimo_registro_pvpc), 
            min_value = datetime.date(2024, 1, 1), max_value = ultimo_registro_pvpc, format = "DD.MM.YYYY",
            key = 'fechas_periodo',
            )
        st.form_submit_button('Actualizar cálculos')
    
with factura_col1:
    st.header('Peso de los componentes de la factura', divider='gray')
    st.plotly_chart(graf_queso_comp_pvpc, use_container_width=True)
    st.plotly_chart(graf_queso_comp_fijo, use_container_width=True)

with pvpc_te_col1:
    st.header('Evolución mensual del PVPC', divider='gray')
    st.caption(
        "Precio de energía ponderado con el perfil 2.0TD. Para el mes en curso "
        "se aplica el mismo corte diario a ese mes de los años anteriores."
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

with comparativa_col1:
    st.plotly_chart(graf_historico_componentes, use_container_width=True)


    

with col2:

    # Algunos datos de salida a mostrar
    st.header('Resumen del periodo analizado', divider = 'gray')
    st.markdown(f':blue-background[Periodo seleccionado del {fecha_inicio.strftime("%d.%m.%Y")} al {fecha_fin.strftime("%d.%m.%Y")}]')
    
    col101, col102, col103 = st.columns(3)

    with col101:
        if consumo_periodo < 1000:
            consumo_periodo_formateado = f'{consumo_periodo:.0f}'
        else:
            consumo_periodo_formateado = f'{consumo_periodo/1000:0,.3f}'.replace(',', '.')
        st.metric('Consumo periodo (kWh)', consumo_periodo_formateado)
        st.metric('Precio medio del PVPC (c€/kWh)', f"{pvpc_medio / 10:,.2f}".replace('.', ','), help = 'Precio medio del PVPC sin perfilar (c€/kWh)')
         
    with col102:
        st.metric('Media ponderada del PVPC (c€/kWh)', f"{te_pvpc * 100:,.2f}".replace('.', ','), help = 'Precio medio del PVPC perfilado en el periodo seleccionado (c€/kWh)')
        st.metric('Coste del Te PVPC(€)', f'{te_coste_pvpc:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'))

    with col103:
        st.dataframe(pt_periodos_filtrado, hide_index=True, use_container_width=True)
    
    # Resultados a mostrar
    st.subheader(':orange-background[Resultados comparativa total factura]') #, divider = 'rainbow')
    st.markdown(f':blue-background[Incluye todos los términos excepto alquiler de medida. Sección **Alfonso Zárate Conde**]')

    col4, col5, col6 = st.columns(3)
    with col4:
        st.metric('Coste factura PVPC (€)', f'{coste_pvpc:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'))
        st.metric('Precio factura PVPC (c€/kWh)', f'{media_pvpc_fra:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'), help='Precio medio en c€/kWh teniendo en cuenta todos los componentes de la factura PVPC')
    with col5: 
        st.metric('Coste factura FIJO (€)', f'{coste_fijo:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'))
        st.metric('Precio factura FIJO (c€/kWh)', f'{media_fijo_fra:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'), help='Precio medio en c€/kWh teniendo en cuenta todos los componentes de la factura FIJO')
    with col6:
        with st.container(border = True):
            st.metric('Sobrecoste FIJO (€)', dif_pvpc_fijo, f'{dif_pvpc_fijo_porc} %', 'inverse')

    


    st.subheader('Datos adicionales oferta FIJO') #, divider ='gray')
    st.markdown(f':blue-background[Obtén información del sobrecoste del término de potencia. Sección **Fernando Sánchez Rey-Maeso**]', help = 'Sobrecoste con respecto al margen regulado del PVPC (2)')

    col111, col112, col113 = st.columns(3)
    with col111:
        st.metric('Margen Tp (€/kW año)', f'{tp_margen_fijo:,.2f}'.replace('.', ','))
    with col112:
        st.metric('Sobrecoste Tp (€)', f'{sobrecoste_tp:,.2f}'.replace('.', ',')) 
    with col113:
        with st.container(border = True):
            st.metric('Sobrecoste Tp ANUAL (€)', f'{sobrecoste_tp_anual:,.2f}'.replace('.', ','), f'{sobrecoste_tp_porc:,.2f}%'.replace('.', ','),'inverse')

    

    col3.subheader('Distribución de consumos y costes en %') #, divider = 'gray')
    
    if error_periodos == False:
        col301, col302 = col3.columns(2)
        with col301:
            st.write(graf_consumos_queso)
            #if error_periodos == False:
            #    st.write(pt_periodos_filtrado)

        with col302:
            st.write(graf_costes_queso)
            #if error_periodos == False:
            #    st.write(totales_periodo)
    else:
        col3.error('No se disponen de datos de periodos dh para el mes en curso.')

    col3.header('Mapa comparativo FIJO vs PVPC', divider='gray')
    col3.write(graf_mapa)

    comparativa_col2.header('Comparativa mensual PVPC', divider='gray')
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
            comparativa_col2.caption(
                f'{nombres_meses[mes_comparacion]} comparado del día 1 al '
                f'{dia_corte}, con el mismo consumo anual y potencia seleccionados.'
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

with pvpc_te_col3:
    st.header('Curvas horarias perfiladas del PVPC', divider = 'gray')
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

        



