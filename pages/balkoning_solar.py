import streamlit as st
import pandas as pd
import numpy_financial as npf
import numpy as np
import folium
from streamlit_folium import st_folium
from backend_balkoning_solar import (
    obtener_pvgis_horario, arreglar_pvgis, leer_curva_normalizada,
    combo_gen_dem, generar_be,
    graficar_con_gen, graficar_quesos_balance, graficar_barras_balance, graficar_amortizacion, graficar_ahorro
    )


from utilidades import generar_menu

if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')

generar_menu()

if 'potencia_paneles' not in st.session_state:
    st.session_state.potencia_paneles = 400
if 'inclinacion' not in st.session_state:
    st.session_state.inclinacion = 90
if 'orientacion' not in st.session_state:
    st.session_state.orientacion = 220
if 'latitud' not in st.session_state:
    st.session_state.latitud = 39.501
if 'longitud' not in st.session_state:
    st.session_state.longitud = -0.443
if 'precio_energia' not in st.session_state:
    st.session_state.precio_energia = 11    
if 'coste_inversion' not in st.session_state:
    st.session_state.coste_inversion = 350    


potencia_paneles = st.session_state.potencia_paneles / 1000 # potencia en kWp
inclinacion = st.session_state.inclinacion #90 es vertical
orientacion = st.session_state.orientacion #azimuth: ATENCIÓN la convención de pvgis es sur=0, pero pvlib sur=180. para SO 40 grados sería 180+40 = 220
latitud = st.session_state.latitud
longitud = st.session_state.longitud
año_pvgis = 2023

# definimos obstáculo finca delante de la nuestra
distancia = 15 #metros
altura = 6 # metros



df_pvgis_ini, meta, inputs = obtener_pvgis_horario(latitud, longitud, año_pvgis, inclinacion, orientacion, potencia_paneles)

df_pvgis = arreglar_pvgis(df_pvgis_ini)

curva = 'curvas/curva_normalizada_casa_2025.csv'

df_in = leer_curva_normalizada(curva)

df_gen_dem = combo_gen_dem(df_in, df_pvgis)

df_be = generar_be(df_gen_dem)

colores_energia = {
    'consumo': '#3498DB',        # azul
    'demanda': '#F39C12',         # naranja  
    'demanda': '#D35400',           #rojizo   
    'Generación FV': '#F7DC6F',  # amarillo suave
    'vertido': '#AF7AC5',        # lila / violeta claro
    'autoconsumo': '#2ECC71'     # verde
}


graf_con_gen = graficar_con_gen(df_be)
graf_cobertura = graficar_barras_balance(df_be, 'cobertura', colores_energia)
graf_aprovechamiento = graficar_barras_balance(df_be, 'aprovechamiento', colores_energia)

total_consumo = df_be['consumo'].sum()
total_genfv = df_be['gen_fv'].sum()
total_demanda = df_be['demanda'].sum()
total_vertido = df_be['vertido'].sum()
#total_aprovechamiento = total_genfv-total_vertido
total_autoconsumo = df_be['autoconsumo'].sum()
#print(total_autoconsumo)

cobertura_media_porc=round(total_autoconsumo*100/total_consumo,2)
aprovechamiento_medio_porc=round(100-total_vertido*100/total_genfv,2)


# DATAFRANES PARA QUESOS RESUMEN BALANCE ENERGÉTICO
df_aprovechamiento = pd.DataFrame({
    'concepto': ['autoconsumo', 'vertido'],
    'energia_kwh': [total_autoconsumo, total_vertido]
})
df_cobertura = pd.DataFrame({
    'concepto': ['autoconsumo', 'demanda'],
    'energia_kwh': [total_autoconsumo, total_demanda]
})
graf_aprovechamiento_total = graficar_quesos_balance(df_aprovechamiento, aprovechamiento_medio_porc, colores_energia, 'aprovechamiento')
graf_cobertura_total = graficar_quesos_balance(df_cobertura, cobertura_media_porc, colores_energia, 'cobertura')


df_totales = pd.DataFrame({
    'Concepto': [
        'Consumo total',
        'Generación FV',
        'Demanda total',
        'Vertido'
    ],
    'Energía (kWh)': [
        total_consumo,
        total_genfv,
        total_demanda,
        total_vertido
    ]
})


# CÓDIGO PARA EL MAPA DE UBICACIÓN+++++++++++++++++++++++
# Mapa centrado inicialmente
m = folium.Map(
    location=[latitud, longitud],
    zoom_start=7,
    tiles="OpenStreetMap"
)
# Permitir click
m.add_child(folium.LatLngPopup())


# CÓDIGO PARA LA COMPARATIVA DE LAS PELAS++++++++++++++++++++
iee = .051127
iva = .21
impuestos = (1 + iee) * (1 + iva)
coste_sin_aut = round(total_consumo * st.session_state.precio_energia / 100, 2) # el precio viene inicialmente en c€/kWh
coste_sin_aut = coste_sin_aut * impuestos
coste_con_aut = round(total_demanda * st.session_state.precio_energia / 100, 2)
coste_con_aut = coste_con_aut * impuestos
ahorro = round(coste_sin_aut - coste_con_aut, 2)
ahorro_porc = round(ahorro * 100 / coste_sin_aut, 1)

graf_ahorro = graficar_ahorro(ahorro_porc)

# CÁLCULO DE LA AMORTIZACIÓN++++++++++++++++++++++++++++++++++++++++++++
incremento_precio = 0.05
tasa_descuento = 0.03
horizonte = 20
coste_inversion = st.session_state.coste_inversion
flujos = [-coste_inversion]

datos = []
ahorro_acumulado = 0
for año in range(1, horizonte + 1):
    ahorro_nominal = ahorro * ((1 + incremento_precio) ** (año - 1))
    ahorro_actualizado = ahorro_nominal / ((1 + tasa_descuento) ** año)
    ahorro_acumulado += ahorro_actualizado
    flujos.append(ahorro)

    datos.append({
        'Año': año,
        'Ahorro acumulado (€)': ahorro_acumulado
    })
df_amortizacion = pd.DataFrame(datos)
df_cross = df_amortizacion.copy()

cruce = df_cross[df_cross['Ahorro acumulado (€)'] >= coste_inversion]

if not cruce.empty:
    fila_actual = cruce.iloc[0]
    fila_anterior = df_cross.iloc[fila_actual.name - 1]

    ahorro_prev = fila_anterior['Ahorro acumulado (€)']
    ahorro_curr = fila_actual['Ahorro acumulado (€)']

    fraccion = (
        (coste_inversion - ahorro_prev) /
        (ahorro_curr - ahorro_prev)
    )

    año_amortizacion = fila_anterior['Año'] + fraccion

tir = npf.irr(flujos)
tir = tir * 100

graf_amortizacion = graficar_amortizacion(df_amortizacion, coste_inversion)



# ========================================================================================================
# VISUALICIÓN
# ========================================================================================================

st.header('Balkoning Solar: ¿Es para todos? No te tires a la piscina sin comprobar si hay agua...', divider='rainbow')

with st.container():
    c1, c2, c3 = st.columns([.2,.3,.5])
    with c1:
        st.subheader('Parámetros de entrada')
        st.info('Introduce los valores para calcular la generación FV prevista según PVGIS-ERA5', icon = 'ℹ️')
        st.number_input('Introduce la potencia de paneles (en Wp)', min_value=100, max_value=1000, step=100, key='potencia_paneles')
        st.number_input('Introduce la inclinacion de los paneles (en grados)', min_value=0, max_value=90, step=10, key='inclinacion', help='90° es vertical')
        st.number_input('Introduce la orientación (en grados)', min_value=0, max_value=355, step=5, key='orientacion', help='El NORTE son 0° y el SUR son 180°')

        # Mostrar mapa
        st.caption('Introduce las coordenadas de la ubicación')
        mapa = st_folium(m, height=400, width=700)

        # Leer coordenadas clicadas
        if mapa["last_clicked"]:
            st.session_state.latitud = mapa["last_clicked"]["lat"]
            st.session_state.longitud = mapa["last_clicked"]["lng"]

        st.write(f"📍 Latitud: {st.session_state.latitud:.5f}")
        st.write(f"📍 Longitud: {st.session_state.longitud:.5f}")

        st.number_input('Introduce el precio medio de la energía (en c€/kWh)', min_value=8, max_value=25, step=1, key='precio_energia')
        st.number_input('Introduce el coste de la inversión IVA INCLUIDO (en €)', min_value=100, max_value=10000, step=100, key='coste_inversion')

    with c2:
        st.subheader('Balance energético')
        c21, c22, c23 = st.columns(3)
        with c21:
            st.metric("Consumo total (kWh)", f"{total_consumo:,.0f}".replace(",", "."))
            st.metric("Generación FV (kWh)", f"{total_genfv:,.0f}".replace(",", "."))
        with c22:
            st.metric("Demanda total (kWh)", f"{total_demanda:,.0f}".replace(",", "."))
            st.metric("Vertido (kWh)", f"{total_vertido:,.0f}".replace(",", "."))
        with c23:
            st.metric("Autoconsumo (kWh)", f"{total_autoconsumo:,.0f}".replace(",", "."))

        st.plotly_chart(graf_aprovechamiento_total)
        st.plotly_chart(graf_cobertura_total)
    with c3:
        st.subheader('Resumen de las pelas. Datos anuales. SÓLO TÉRMINO DE ENERGÍA')
        st.info((
            f'Se incluye IEE e IVA. No se tiene en cuenta el término de potencia. '
            f'Para los cálculos financieros se ha usado un incremento anual del precio de la energía del {100*incremento_precio}% y una tasa de descuento del {100*tasa_descuento}%. '
            f'El ahorro acumulado tiene en cuenta {horizonte} años'), icon = 'ℹ️')

        c31, c32, c33 = st.columns([.3,.3, .4])
        with c31:
            st.metric("Coste SIN autoconsumo (€)", f"{coste_sin_aut:,.2f}".replace(".", ","))
            st.metric("Coste CON autoconsumo (€)", f"{coste_con_aut:,.2f}".replace(".", ","))
            st.metric("Ahorro (€)", f"{ahorro:,.2f}".replace(".", ","), delta=f"{ahorro_porc:,.1f}%".replace(".", ","),)
        with c32:
            st.metric("Ahorro acumulado (€)", f"{ahorro_acumulado:,.2f}".replace(".", "X").replace(",", ".").replace("X", ","))
            st.metric("Año de amortización (€)", f"{año_amortizacion:,.2f}".replace(".", ","))
            st.metric("TIR (%)", f"{tir:,.1f}".replace(".", ","), help='La TIR representa la rentabilidad anual equivalente de la inversión en autoconsumo.')
        with c33:
            st.plotly_chart(graf_ahorro, use_container_width=True)
        if tir > tasa_descuento:
            st.success(f'Parece una buena inversión, ya que el TIR supera a la Tasa de Descuento ({100*tasa_descuento}%)')
        st.plotly_chart(graf_amortizacion, use_container_width=True)

c1, c2, c3 = st.columns(3)
with c1:
    st.plotly_chart(graf_con_gen)
with c2:
    st.plotly_chart(graf_cobertura)
with c3:
    st.plotly_chart(graf_aprovechamiento)
