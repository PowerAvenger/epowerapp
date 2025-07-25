import streamlit as st
import pandas as pd
from backend_fijovspvpc import (obtener_datos_horarios, obtener_tabla_filtrada, grafico_horario_consumo, grafico_horario_coste, grafico_horario_precio, 
                                obtener_datos_por_periodo,graf_consumos_queso,graf_costes_queso,
                                optimizar_consumo_media_horaria, grafico_comparativo_perfiles, optimizar_consumo_suavizado)
import datetime
import numpy as np
from dateutil.relativedelta import relativedelta
from datetime import timedelta
from utilidades import generar_menu

generar_menu()

#st.title('Fijo vs PVPC :orange[e]PowerAPP©')
#st.caption(f'Dedicado a **Fernando Sánchez Rey-Maeso** y a **Alfonso Zárate Conde** por sus contribuciones a la causa. Copyright by **Jose Vidal** :ok_hand:')
url_apps = 'https://powerappspy-josevidal.streamlit.app/'
url_linkedin = "https://www.linkedin.com/posts/josefvidalsierra_epowerapps-spo2425-telemindex-activity-7281942697399967744-IpFK?utm_source=share&utm_medium=member_deskto"
url_bluesky = "https://bsky.app/profile/poweravenger.bsky.social"

#st.write('Visita mi mini-web de [PowerAPPs](%s) con un montón de utilidades.' % url_apps)

#st.markdown(f"Deja tus comentarios y propuestas en mi perfil de [Linkedin]({url_linkedin}) - ¡Sígueme en [Bluesky]({url_bluesky})!")
#st.markdown(f'Visita mi mini-web de [PowerAPPs]({url_apps}) con un montón de utilidades. Deja tus comentarios y propuestas en mi perfil de [LinkedIn]({url_linkedin}) - ¡Sígueme en [Bluesky]({url_bluesky})! Copyright by **Jose Vidal** :ok_hand:')


if not st.session_state.get('usuario_autenticado', False):
    st.switch_page('epowerapp.py')


#DEFINIMOS CONSTANTES
#impuestos
iee = 0.051127
iva = 0.21
#costes regulados
tp_boe_2024 = 26.36
tp_boe_2025 = 27.63
tp_margen_pvpc = 3.12

#Inicializamos variables

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
# Calcular los días dentro de cada año
inicio_2024 = max(fecha_inicio, pd.Timestamp("2024-01-01"))
fin_2024 = min(fecha_fin, pd.Timestamp("2024-12-31"))
dias_2024 = (fin_2024 - inicio_2024).days + 1 if inicio_2024 <= fin_2024 else 0

inicio_2025 = max(fecha_inicio, pd.Timestamp("2025-01-01"))
fin_2025 = min(fecha_fin, pd.Timestamp("2025-12-31"))
dias_2025 = (fin_2025 - inicio_2025).days + 1 if inicio_2025 <= fin_2025 else 0
print('dias_2025')
print(dias_2025)

## CÁLCULOS
# Cálculo del coste del término de potencia PVPC

tp_pvpc_2024 = tp_boe_2024 + tp_margen_pvpc #€/kW año
tp_coste_pvpc_2024_kW = tp_pvpc_2024 * dias_2024 / 366 #€/kW

tp_pvpc_2025 = tp_boe_2025 + tp_margen_pvpc
tp_coste_pvpc_2025_kW = tp_pvpc_2025 * dias_2025 / 365 #€/kW

tp_coste_pvpc_kW = tp_coste_pvpc_2024_kW + tp_coste_pvpc_2025_kW #€/kW
tp_pvpc = tp_coste_pvpc_kW * 365 / dias_periodo
print('tp_pvpc')
print(tp_pvpc)
tp_coste_pvpc = tp_coste_pvpc_kW * st.session_state.pot_con  #€


df_datos_horarios_combo_filtrado_consumo, pt_horario_filtrado, media_precio_perfilado, coste_pvpc_perfilado = obtener_tabla_filtrada(df_datos_horarios_combo, fecha_inicio, fecha_fin, consumo_periodo)

te_pvpc = media_precio_perfilado
te_coste_pvpc = round(te_pvpc * consumo_periodo, 2)
coste_pvpc = round((tp_coste_pvpc + te_coste_pvpc) * (1 + iee) * (1 + iva), 2)

# Cálculo del FIJO a fecha último registro
tp_margen_fijo = +round(st.session_state.tp_fijo - tp_pvpc, 2)
tp_coste_fijo = st.session_state.tp_fijo * st.session_state.pot_con * dias_periodo / 365
te_fijo = st.session_state.precio_ene / 100
te_coste_fijo = round(te_fijo * consumo_periodo, 2)
coste_fijo = float(f"{round((tp_coste_fijo + te_coste_fijo) * (1 + iee) * (1 + iva), 2):.2f}")

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

# BARRA LATERAL-----------------------------------------------------------------------------
st.sidebar.header('Herramientas adicionales')
with st.sidebar.form('form2'):
        st.subheader('Calcular Tp BOE anual')
        precio_tp_dia_P1 = st.number_input('potencia €/kW dia P1', min_value = 0.074, max_value = 0.164, step = .001, format  ="%f")
        precio_tp_dia_P3 = st.number_input('potencia €/kW dia P3',min_value=0.002, max_value = 0.164, step = .001, format  ="%f")
        precio_tp_año = round((precio_tp_dia_P1 + precio_tp_dia_P3) * 365, 2)
        if precio_tp_año < tp_boe_2025:
            precio_tp_año = tp_boe_2025

        st.form_submit_button('Calcular')
        st.write(f'Precio Tp anual en €/kW año = {precio_tp_año}')


# LAYAOUT DE DATOS++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
col1, col2, col3 = st.columns([.3, .4, .4])
with col1:
    st.header('Zona de interacción', divider = 'gray')
    #with st.form('form1'):
    with st.container(border=True):
        st.subheader('1. Introduce datos de potencia y consumo')
        st.slider('Potencias Contratadas P1, P3 (kW)', min_value = 1.0, max_value = 9.9, step = .1, key = 'pot_con')
        st.slider('Consumo :blue[ANUAL] estimado (kWh)',min_value = 500, max_value = 7000, step = 100, key = 'consumo_anual')
    with st.container(border=True):
        st.subheader('2.Introduce datos del contrato a precio fijo')
        st.slider('Precio ofertado: término de potencia (€/kW año)', min_value = tp_boe_2025, max_value = 70.0, step =.1, key = 'tp_fijo')


        st.toggle('Usar tres precios de energía', key = 'precios_3p')
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
        #else:
        
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
         
    with col102:
        st.metric('Precio medio del PVPC (c€/kWh)', f"{te_pvpc * 100:,.2f}".replace('.', ','), help = 'Precio medio del PVPC perfilado en el periodo seleccionado (c€/kWh)')
        st.metric('Coste del Te PVPC(€)', f'{te_coste_pvpc:0,.2f}'.replace('.', ','))

    with col103:
        st.dataframe(pt_periodos_filtrado, hide_index=True, use_container_width=True)
    
    # Resultados a mostrar
    st.subheader(':orange-background[Resultados comparativa total factura]') #, divider = 'rainbow')
    st.markdown(f':blue-background[Incluye todos los términos excepto alquiler de medida. Sección **Alfonso Zárate Conde**]')

    col4, col5, col6 = st.columns(3)
    with col4:
        st.metric('Coste factura PVPC (€)', f'{coste_pvpc:0,.2f}'.replace('.', ','))
    with col5: 
        st.metric('Coste factura FIJO (€)', f'{coste_fijo:0,.2f}'.replace('.', ','))
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

    

    st.subheader('Distribución de consumos y costes en %') #, divider = 'gray')
    
    if error_periodos == False:
        col301, col302 = st.columns(2)
        with col301:
            st.write(graf_consumos_queso)
            #if error_periodos == False:
            #    st.write(pt_periodos_filtrado)

        with col302:
            st.write(graf_costes_queso)
            #if error_periodos == False:
            #    st.write(totales_periodo)
    else:
        st.error('No se disponen de datos de periodos dh para el mes en curso.')   

        
with col3:
    st.header('Curvas horarias perfiladas del PVPC', divider = 'gray')
    #st.subheader('Gráfico de consumo perfilado REE 2.0TD', divider = 'gray')
    st.write(grafico_consumo)
    
    #st.subheader('Gráfico de coste del PVPC perfilado', divider = 'gray')
    st.write(grafico_coste)

    #st.subheader('Gráfico del PVPC medio horario perfilado', divider = 'gray')
    st.write(grafico_precio)

    st.header('Optimización burda del consumo', divider = 'gray')
    st.plotly_chart(grafico_comparativo_perfiles(df_perfiles))

    col31, col32, col33, col34 = st.columns(4)
    with col31:
        st.metric("Coste original", f"{resumen['coste_original']:.2f} €")
    with col32:
        st.metric("Coste optimizado", f"{resumen['coste_optimizado']:.2f} €")
    with col33:
        st.metric("Ahorro absoluto", f"{resumen['ahorro_abs']:.2f} €")
    with col34:
        st.metric("Ahorro relativo", f"{resumen['ahorro_pct']:.2f} %")

    
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

        

 
#with col32:
#    st.subheader('Provisional',divider='gray')
    #st.write(grafico_precio)
#    st.write(pt_periodos_filtrado)
#    st.write(pt_periodos_filtrado_porc)
#    st.write(totales_periodo)

#obtenemos tabla con los tres porcentajes de consumo. usado para obtener el precio fijo de 3P
#st.session_state['porcentajes_consumo']=pt_periodos_filtrado_porc['consumo']
#st.write(st.session_state['porcentajes_consumo'])

#st.text(f'El margen aplicado al término de potencia es {margenpot} €/kW año')
#st.text(f'El precio fijo ofertado es {precioene} c€/kWh')
#st.text(f'El coste del PVPC término de potencia es {tp_coste_pvpc}€')
#st.text(f'El coste del PVPC término de energía es {te_coste_pvpc}€')
#st.text(f'El coste total del PVPC es {coste_pvpc}€')
#st.text(f'El coste del FIJO término de potencia es {tp_coste_fijo}€')
#st.text(f'El coste del FIJO término de energía es {te_coste_fijo}€')
#st.text(f'El coste total del FIJO es {coste_fijo}€')



