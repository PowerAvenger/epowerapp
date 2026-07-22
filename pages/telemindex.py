import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

import pandas as pd
import datetime
from backend_telemindex import (
    filtrar_datos, añadir_fnee, #calcular_precios_atr,
    graficar_precios_medios_horarios, graficar_queso_componentes,
    tabla_precios, tabla_costes, tabla_pyc, tabla_margen, tabla_apuntamiento_spot,
    evol_mensual, evol_precios_diarios, graficar_diferencial_precios_mensuales, tabla_evol_mes_por_años,
    evol_diario,
    construir_df_curva_sheets, añadir_costes_curva,
    check_medias,
    analizar_dependencia_omie, graficar_elasticidad_lineal,
    
) 
from backend_comun import colores_precios, obtener_df_resumen, formatear_df_resumen, aplicar_estilo, aplicar_dh6p_zona, NOMBRE_ZONA_PERIODOS, calcular_precios_atr
from backend_curvadecarga import graficar_media_horaria, graficar_queso_periodos
from utilidades import generar_menu, init_app, init_app_index, persist_widget
from formato_es import (
    formato_cent_eur_kwh,
    formato_eur_kwh,
    formato_eur_mwh,
    formato_euros,
    formato_kwh,
    formato_numero_es,
    formato_pct,
)


if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')

  

if "df_ofertas_fijas" not in st.session_state:
    st.session_state.df_ofertas_fijas = pd.DataFrame()

if "df_oferta_fija_manual" not in st.session_state:
    st.session_state.df_oferta_fija_manual = pd.DataFrame()


if "margen_fijo" not in st.session_state:
    st.session_state.margen_fijo = 0.0

if 'opcion_comparativa' not in st.session_state:
    st.session_state.opcion_comparativa = 'Cobertura'

#para lo del análisis de elasticidad y tal
if 'peaje_analisis' not in st.session_state:
    st.session_state.peaje_analisis = '2.0'

if 'mes_select_evol' not in st.session_state:
    st.session_state.mes_select_evol = 'enero'

if 'precios_mensuales' not in st.session_state:
    st.session_state.precios_mensuales = None


#inicializamos variables de sesión
generar_menu()

if st.session_state.get('atr_dfnorm') in ['6.3', '6.4']:
    st.warning(f'No se disponen datos de indexado para {st.session_state.atr_dfnorm}TD')
    st.stop()  

init_app()

st.sidebar.header('⚡ Histórico de indexados ⚡')
zona_mensajes = st.sidebar.empty()
#if 'df_sheets' not in st.session_state:
if 'df_sheets_old' not in st.session_state:    
    zona_mensajes.warning('Cargando históricos de indexado. Espera a que estén disponibles...', icon = '⚠️')

init_app_index()

st.session_state.df_sheets = calcular_precios_atr(st.session_state.df_sheets)
print('df sheets con fnee y margen según fórmula')
print (st.session_state.df_sheets)

if "rango_curvadecarga" in st.session_state:
    if st.session_state.rango_temporal == "Selecciona un rango de fechas":
        st.session_state.dias_seleccionados = st.session_state.rango_curvadecarga




df_filtrado_sheets, lista_meses = filtrar_datos()

check_medias(df_filtrado_sheets, "3.0")

def check_componentes_ssaa_simple(df):
    
    componentes = [
        "balx", "bs3", "cfp", "ct2", "ct3",
        "dsv", "exd", "in7", "rad3", "rt3", "rt6"
    ]

    print("---- MEDIAS COMPONENTES ----\n")

    suma = 0

    for c in componentes:
        val = df[c].mean()
        suma += val
        print(f"{c.upper():5}: {val:.4f}")

    print("\nTOTAL SSAA (reconstruido):", round(suma, 4))
    print("SSAA en df:", round(df["ssaa"].mean(), 4))

check_componentes_ssaa_simple(df_filtrado_sheets)




#df_filtrado = calcular_precios_atr(df_filtrado_sheets)
df_filtrado = df_filtrado_sheets #por mantener nombre antiguo

try:
    fecha_ultima_filtrado = df_filtrado['fecha'].iloc[-1]
except:
    st.session_state.dia_seleccionado = datetime.date(2025,1,1)
    df_filtrado, lista_meses = filtrar_datos()

if "df_norm_h" in st.session_state and st.session_state.df_norm_h is not None and st.session_state.rango_temporal == "Selecciona un rango de fechas":

    df_curva_sheets = construir_df_curva_sheets(df_filtrado)
    df_curva_sheets = añadir_costes_curva(df_curva_sheets)
    
    print("df_curva_sheets generado correctamente")
    df_uso = df_curva_sheets.copy()
    df_uso = df_uso.drop_duplicates(subset=["fecha", "hora", "spot"])
    st.session_state.df_curva_sheets = df_uso
    print('st.session_state.df_curva_sheets = df_uso')
    print(df_uso)

    #consumo total curva
    consumo_total_curva = df_uso['consumo_neto_kWh'].sum()
    
    #calculamos el coste spot ponderado en €/MWh
    media_spot_curva = round(df_uso['coste_spot'].sum()/(consumo_total_curva/1000),2)
    media_ssaa_curva = round(df_uso['coste_ssaa'].sum()/(consumo_total_curva/1000),2)
        
    coste_total_curva = round(df_uso['coste_total'].sum(), 2)

    
    
else:
    st.session_state.df_curva_sheets = None
    print("df_norm_h no está disponible → no se genera df_curva_sheets")
    df_uso = df_filtrado.copy()
    #para usar en simulindex
    #st.session_state.df_uso = df_uso


#ejecutamos la función para obtener la tabla resumen y precios medios
media_20 = df_uso["precio_2.0"].mean()
media_30 = df_uso["precio_3.0"].mean()
media_61 = df_uso["precio_6.1"].mean()
media_spot = df_uso["spot"].mean()
media_ssaa = df_uso["ssaa"].mean()

df_tabla_precios, media_curva_precio = tabla_precios(df_uso)
media_atr_curva = media_curva_precio #por compatibilidad de media_atr_curva
df_tabla_costes, media_curva_coste = tabla_costes(df_uso)
df_tabla_pyc, media_curva_pyc = tabla_pyc(df_uso)
df_tabla_margen, media_curva_margen = tabla_margen(df_uso)
df_tabla_apuntamiento = tabla_apuntamiento_spot(df_uso)
print(f'Media precio curva en €/MWh: {media_curva_precio}')
print(f'Media precio 3.0 en €/MWh: {media_30}')

#media_20 = round(media_20 / 10, 1)
media_20 = media_20 / 10
#media_30 = round(media_30 / 10, 1)
media_30 = media_30 / 10
#media_61 = round(media_61 / 10, 1)
media_61 = media_61 / 10
media_spot = round(media_spot, 2)
media_ssaa = round(media_ssaa, 2)
media_combo = media_spot + media_ssaa
sobrecoste_ssaa = ((media_combo / media_spot) - 1) * 100




if "df_norm_h" in st.session_state and st.session_state.df_norm_h is not None and st.session_state.rango_temporal == "Selecciona un rango de fechas":

    media_atr_curva = media_curva_precio / 10
    apuntamiento_spot = round(media_spot_curva/media_spot,3)
    apuntamiento_ssaa = round(media_ssaa_curva/media_ssaa,3)

    atr_map = {
        "2.0": media_20,
        "3.0": media_30,
        "6.1": media_61
    }
    media_atr = atr_map.get(st.session_state.atr_dfnorm)
    coste_sin_ponderar = round(consumo_total_curva * media_atr / 100,2)
    desvio_coste_total = coste_total_curva-coste_sin_ponderar
    desvio_coste_total_porc = (desvio_coste_total / coste_sin_ponderar) * 100

    print(f'Coste sin ponderar: {coste_sin_ponderar}€')
    print(f'Coste ponderado: {coste_total_curva}€')


    df_filtrado_cober = df_filtrado_sheets.copy()
    
    
    if 'precio_cobertura' not in st.session_state:
        st.session_state.precio_cobertura = 50
    #precio_cober_omip = st.session_state.get('precio_cobertura', 50.0)

    df_filtrado_cober["spot"] = st.session_state.precio_cobertura * apuntamiento_spot
    df_filtrado_cober = calcular_precios_atr(df_filtrado_cober)

    df_curva_cober_omip = construir_df_curva_sheets(df_filtrado_cober)
    df_curva_cober_omip = añadir_costes_curva(df_curva_cober_omip)
    df_curva_cober_omip = df_curva_cober_omip.drop_duplicates(subset=["fecha", "hora", "spot"])
           
    #df_heat = st.session_state.df_curva_sheets[["fecha","hora"]].copy()

    opcion_comparativa = str(st.session_state.get("opcion_comparativa", "Cobertura"))
    df_ofertas_sesion = st.session_state.get("df_ofertas_fijas")

    ofertas_disponibles = []
    if df_ofertas_sesion is not None and not df_ofertas_sesion.empty:
        df_ofertas_sesion = df_ofertas_sesion.copy()
        df_ofertas_sesion["oferta"] = df_ofertas_sesion["oferta"].astype(str).str.strip()
        ofertas_disponibles = df_ofertas_sesion["oferta"].tolist()

    # La selección puede quedar obsoleta al sustituir el Excel o al normalizar
    # como texto nombres de oferta que originalmente eran numéricos.
    if opcion_comparativa != "Cobertura" and opcion_comparativa not in ofertas_disponibles:
        opcion_comparativa = "Cobertura"
        st.session_state.opcion_comparativa = "Cobertura"

    if opcion_comparativa == "Cobertura":

        df_curva_comp = df_curva_cober_omip.copy()
        #df_heat["coste_comp"] = df_curva_comp["coste_total"].values
        titulo_comp = "Comparativa INDEXADO vs COBERTURA" 
        nombre_color = "Cobertura"
        nombre_serie_comp = "Coste cobertura"
        color_serie_comp = "#8B5CF6"

    else:

        fila_oferta = df_ofertas_sesion[
            df_ofertas_sesion["oferta"] == opcion_comparativa
        ].iloc[0]
        periodos = [f"P{i}" for i in range(1, 7)]

        precios_fijo = {
            p: fila_oferta[p]
            for p in periodos
            if p in fila_oferta.index
        }

        df_curva_comp = df_curva_sheets.copy()

        df_curva_comp["precio_fijo"] = df_curva_comp["periodo"].map(precios_fijo)

        df_curva_comp["coste_total"] = (df_curva_comp["consumo_neto_kWh"] * df_curva_comp["precio_fijo"])

        titulo_comp = f"Comparativa INDEXADO vs FIJO {opcion_comparativa}"
        nombre_color = opcion_comparativa
        nombre_serie_comp = "Coste fijo"
        color_serie_comp = "#EF4444"

    
    # ==========================================
    # PREPARAR DF INDEX Y DF COMP
    # ==========================================
    df_index = (
        df_curva_sheets[["fecha", "hora", "coste_total"]]
        .copy()
        .groupby(["fecha", "hora"], as_index=False)["coste_total"]
        .sum()
        .rename(columns={"coste_total": "coste_index"})
    )

    df_comp = (
        df_curva_comp[["fecha", "hora", "coste_total"]]
        .copy()
        .groupby(["fecha", "hora"], as_index=False)["coste_total"]
        .sum()
        .rename(columns={"coste_total": "coste_comp"})
    )

    df_heat = df_index.merge(
        df_comp,
        on=["fecha", "hora"],
        how="inner"
    )

    df_heat["dif_coste"] = df_heat["coste_index"]- df_heat["coste_comp"]

    heatmap_data = df_heat.pivot_table(
        index="fecha",
        columns="hora",
        values="dif_coste"
    )
    heatmap_data = heatmap_data.reindex(sorted(heatmap_data.columns), axis=1)

    zmax = abs(heatmap_data.values).max()

    fig_heat = px.imshow(
        heatmap_data,
        color_continuous_scale="RdYlGn_r",
        zmin=-zmax,
        zmax=zmax,
        color_continuous_midpoint=0,
        aspect="auto",
        labels=dict(
            x="Hora",
            y="Día",
            color="Δ Coste (€)"
        )
    )

    fig_heat.update_layout(

        title=dict(
            #text="Cobertura OMIP vs Indexado – Diferencia de coste horario",
            text="",
            x=0.5,              # centra el título
            xanchor="center",
            font=dict(size=22)
        ),

        xaxis=dict(
            title=dict(text="Hora del día", font=dict(size=16)),
            tickmode="array",
            tickvals=list(range(0,24)),   # fuerza las 24 horas
            tickfont=dict(size=12)
        ),

        yaxis=dict(
            title=dict(text="Fecha", font=dict(size=16)),
            tickfont=dict(size=12),
            automargin=True
        ),

        coloraxis_colorbar=dict(
            title=dict(text="Δ Coste (€)", font=dict(size=14)),
            tickfont=dict(size=12)
        ),

        margin=dict(l=40, r=40, t=60, b=40),

        height=700
    )

    fig_heat.update_traces(
        zmin=-zmax,
        zmax=zmax
    )

    fig_heat.update_traces(
        hovertemplate=
        "<b>Día:</b> %{y}<br>"
        "<b>Hora:</b> %{x}<br>"
        "<b>Diferencia coste:</b> %{z:.2f} €<extra></extra>"
    )

    fig_heat.update_xaxes(showgrid=False)
    fig_heat.update_yaxes(showgrid=False)

    fig_heat.update_traces(
        xgap=1,
        ygap=1
    )

    #fig_heat = aplicar_estilo(fig_heat)

#print('df curva sheets')
#print(df_curva_sheets) 
if st.session_state.df_curva_sheets is None:
    df_precios_mensuales, graf_mensual = evol_mensual(st.session_state.df_sheets, colores_precios)
    df_precios_mensuales_sin_curva = df_precios_mensuales
    df_evol_precios_diarios, graf_evol_precios_diarios = evol_precios_diarios(st.session_state.df_sheets, colores_precios)
else:
    df_precios_mensuales, graf_mensual = evol_mensual(st.session_state.df_curva_sheets, colores_precios)
    df_precios_mensuales_sin_curva, _ = evol_mensual(
        st.session_state.df_sheets, colores_precios
    )
    df_evol_precios_diarios, graf_evol_precios_diarios = evol_precios_diarios(st.session_state.df_curva_sheets, colores_precios)

print('precios mensuales')
print(df_precios_mensuales)

df_precios_diarios, graf_precios_diarios = evol_diario(st.session_state.df_sheets)

#ELEMENTOS DE LA BARRA LATERAL ---------------------------------------------------------------------------------------
zona_mensajes.info(
    f"Última fecha disponible: {st.session_state.ultima_fecha_sheets.strftime('%d.%m.%Y')}"
)
st.sidebar.info(
    f"Última fecha C2 liquicomun: {st.session_state.ultima_fecha_csv.strftime('%d.%m.%Y')}"
)

st.sidebar.subheader('Opciones')
with st.sidebar.container(border=True):
    #st.sidebar.radio("Seleccionar rango temporal", ['Por años', 'Por meses', 'Selecciona un rango de fechas'], key = "rango_temporal")
    persist_widget(st.sidebar.radio,"Seleccionar rango temporal", ['Por años', 'Por meses', 'Selecciona un rango de fechas'], key = "rango_temporal")
    #persist_widget(st.number_input, "Desvíos apantallados (€/MWh)", min_value=0.0, max_value=20.0, step=0.1, key="desvios_apant", default=1)

    if st.session_state.rango_temporal == 'Por años':
        st.sidebar.selectbox('Seleccione el año', options = [2026, 2025, 2024], key = 'año_seleccionado') 
        st.session_state.texto_precios = f'Año {st.session_state.año_seleccionado}, hasta el día {fecha_ultima_filtrado}'
    elif st.session_state.rango_temporal =='Por meses' : 
        col_sb1, col_sb2 = st.sidebar.container().columns(2)      
        with col_sb1:
            st.sidebar.selectbox('Seleccione el año', options = [2026, 2025, 2024], key = 'año_seleccionado') 
        with col_sb2:
            st.sidebar.selectbox('Seleccionar mes', lista_meses, key = 'mes_seleccionado')
            st.session_state.texto_precios = f'Seleccionado: {st.session_state.mes_seleccionado} de {st.session_state.año_seleccionado}'
    else:
        with st.sidebar.form(key='form_fechas_telemindex'):
            # Asegurar que ultima_fecha_sheets es un objeto datetime.date
            ultima_fecha_sheets = st.session_state.ultima_fecha_sheets
            if isinstance(ultima_fecha_sheets, (pd.Timestamp, datetime.datetime)):
                ultima_fecha_sheets = ultima_fecha_sheets.date()
            st.date_input('Selecciona un rango de días', min_value = datetime.date(2023, 1, 1), max_value = ultima_fecha_sheets, key = 'dias_seleccionados')   
            inicio, fin = st.session_state.dias_seleccionados
            st.session_state.texto_precios = (f"Rango seleccionado: {inicio.strftime('%d/%m/%Y')} → {fin.strftime('%d/%m/%Y')}")
            st.form_submit_button('Actualizar cálculos')

    #st.selectbox("Selecciona zona de periodos horarios", options=["Península", "Baleares", "Canarias", "Ceuta", "Melilla"], index=0, key="zona_periodos_index")
    opciones_zona_periodos = ["peninsula", "baleares", "canarias", "ceuta", "melilla"]

    st.selectbox(
        "Selecciona zona de periodos horarios",
        options=opciones_zona_periodos,
        index=0,
        key="zona_periodos_index",
        format_func=lambda x: {
            "peninsula": "Península",
            "baleares": "Baleares",
            "canarias": "Canarias",
            "ceuta": "Ceuta",
            "melilla": "Melilla",
        }[x]
    )
st.sidebar.subheader('Parámetros de fórmula')
    
with st.sidebar.container(border=True):
    
    #st.number_input("Desvíos apantallados (€/MWh)", min_value=0.0, max_value=20.0, step=0.1, key="desvios_apant")
    persist_widget(st.number_input, "Desvíos apantallados (€/MWh)", min_value=0.0, max_value=20.0, step=0.1, key="desvios_apant", default=1)

    #persist_widget(st.checkbox, "Incluye SRAD", key="cfg_srad", default=True)
    #st.checkbox("Añadir SRAD", key="cfg_srad")

    persist_widget(st.number_input, "Margen (€/MWh)", min_value=0.0, max_value=50.0, step=0.1, key="margen_telemindex", default=5)
    #st.number_input("Margen (€/MWh)", min_value=0.0, max_value=50.0, step=0.1, key="margen_telemindex")
    

    persist_widget(st.selectbox, "Ubicación margen", ["perdidas", "tm", "neto"], key="cfg_margen_pos", default="tm")
    #st.selectbox("Ubicación margen", ["perdidas", "tm", "neto"], key="cfg_margen_pos")

    persist_widget(st.checkbox, "Incluye FNEE", key="cfg_fnee", default=True)
    if st.session_state.get("cfg_fnee", False):
        persist_widget(st.selectbox, "Ubicación FNEE", ["perdidas", "tm", "neto"], key="cfg_fnee_pos", default= "perdidas")
    #st.selectbox("Ubicación FNEE", ["perdidas", "tm", "neto"], key="cfg_fnee_pos")

    #st.number_input("Coste financiero (%)", min_value=0.0, max_value=10.0, step=0.01, key="cf_pct")
    persist_widget(st.number_input,"Coste financiero (%)", min_value=0.0, max_value=10.0, step=0.01, key="cf_pct", default=0.0)


# ZONA PRINCIPAL DE GRÁFICOS++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

tab1, tab2, tab3 = st.tabs(['Principal', 'Evol', 'Comparativa'])

with tab1:
    
        col1, col2 = st.columns([.7,.3])

        #COLUMNA PRINCIPAL
        with col1:
            zona_txt = NOMBRE_ZONA_PERIODOS.get(st.session_state.get("zona_periodos_index", "peninsula"), "PENÍNSULA")
            st.subheader(f'Resumen de precios finales de INDEXADO - Zona :blue[{zona_txt}]. **:orange[{st.session_state.texto_precios}]**', divider = 'rainbow') 
            
            with st.container():
                col5, col6, col7, col8, col9 = st.columns(5)
                with col5:
                    #st.metric(':orange[Precio medio 2.0 c€/kWh]',value = media_20)
                    st.metric(':orange[Precio medio 2.0 c€/kWh]', value=formato_cent_eur_kwh(media_20, 2, False))
                    if media_atr_curva is not None:
                        st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
                        st.metric(f'Precio medio curva {st.session_state.atr_dfnorm} c€/kWh', value=formato_cent_eur_kwh(media_atr_curva, 2, False))
                with col6:
                    st.metric(':red[Precio medio 3.0 c€/kWh]', value=formato_cent_eur_kwh(media_30, 2, False))
                    if media_atr_curva is not None:
                        st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
                        st.metric('Consumo curva kWh', value=formato_kwh(consumo_total_curva, 0, False))
                with col7:
                    st.metric(':blue[Precio medio 6.1 c€/kWh]', value=formato_cent_eur_kwh(media_61, 2, False))
                    if media_atr_curva is not None:
                        st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
                        st.metric('Coste total curva €', value=formato_euros(coste_total_curva, 0, False), delta=formato_pct(desvio_coste_total_porc), delta_color='inverse', help = 'El % indica el desvío con respecto al coste medio aritmético')
                with col8:
                    st.metric(':green[Precio medio Spot €/MWh]', value=formato_eur_mwh(media_spot, 2, False))
                    if media_atr_curva is not None:
                        st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
                        st.metric('Precio medio Spot curva €/MWh', value=formato_eur_mwh(media_spot_curva, 2, False), delta=formato_numero_es(apuntamiento_spot, 3), delta_color='inverse', help = 'Se indica apuntamiento.')
                with col9:
                    st.metric(':violet[Precio medio SSAA €/MWh]', value=formato_eur_mwh(media_ssaa, 2, False), delta=formato_pct(sobrecoste_ssaa, 1), delta_color='inverse', help= 'Se indica su valor medio y en qué % aumenta el precio medio Spot')
                    if media_atr_curva is not None:
                        st.metric('Precio medio SSAA curva €/MWh', value=formato_eur_mwh(media_ssaa_curva, 2, False), delta=formato_numero_es(apuntamiento_ssaa, 3), delta_color='inverse', help = 'Se indica apuntamiento.')

            st.empty()
            # gráfico principal de barras y lineas precios medios y omie+ssaa
            #st.plotly_chart(graf_principal(df_filtrado, colores_precios))
            st.plotly_chart(graficar_precios_medios_horarios(df_uso, colores_precios))
            st.empty()
            st.subheader("Peso de los componentes por peaje de acceso", divider='rainbow')
            #_, graf20, graf30, graf61 = pt1(df_filtrado)
            graf20, graf30, graf61 = graficar_queso_componentes(df_filtrado)
            with st.container():
                col10,col11,col12=st.columns(3)
                with col10:
                    st.write(graf20)    
                with col11:
                    st.write(graf30)
                with col12:
                    st.write(graf61)
                
            

            df_res, fig = analizar_dependencia_omie(st.session_state.df_sheets, st.session_state.peaje_analisis)

            st.subheader('Impacto del SPOT en el precio final', divider='rainbow')
            
            with st.container():
                col10,col11,col12=st.columns([.2,.4,.4])
                with col10:
                    st.selectbox("Selecciona peaje de acceso", ["2.0", "3.0", "6.1"], index=0, key ='peaje_analisis')
                    st.markdown('Tabla de datos')
                    st.dataframe(df_res, hide_index=True)
                with col11:
                    st.plotly_chart(fig, use_container_width=True)
                with col12:
                   fig = graficar_elasticidad_lineal(df_res, st.session_state.peaje_analisis)
                   st.plotly_chart(fig)


        with col2:
            if media_atr_curva is not None:
                apuntamiento_spot_fmt = formato_numero_es(apuntamiento_spot, 2)
                st.subheader(f"Perfil de consumo (kWh) vs coste (€) - Ap: :orange[{apuntamiento_spot_fmt}]", divider='rainbow')
                
                df_coste = st.session_state.df_curva_sheets.copy()
                df_coste_h = (
                    df_coste
                    .groupby("hora", as_index=False)["coste_total"]
                    .mean()
                )
                graf_medias_horarias=graficar_media_horaria('Total')
                graf_medias_horarias.add_trace(
                    go.Scatter(
                        x=df_coste_h["hora"],
                        y=df_coste_h["coste_total"],
                        mode="lines",
                        name="Coste medio indexado",
                        line=dict(
                            color="#E53935",
                            width=5
                        ),
                        yaxis="y2"
                    )
                )
                graf_medias_horarias.update_layout(
                    yaxis2=dict(
                        title="Coste medio (€)",
                        overlaying="y",
                        side="right",
                        showgrid=False
                    ),
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.0,
                        xanchor="center",
                        x=0.5
                    )
                )
                


                
                st.plotly_chart(graf_medias_horarias, use_container_width=True)

                st.subheader("Consumo por periodos")
                graf_periodos, df_periodos=graficar_queso_periodos(st.session_state.df_norm_h)
                st.plotly_chart(graf_periodos, use_container_width=True)
            st.subheader("Tabla resumen de precios por peaje de acceso", divider='rainbow')
            with st.expander("Nota sobre los precios de indexado:"):
                st.caption("Basados en la parametrización de la fórmula de indexado PT. Por supuesto peajes y cargos según tarifa de acceso.")
                
            with st.container():

                texto_precios=f'{st.session_state.texto_precios}. Precios en c€/kWh'
                st.caption(st.session_state.texto_precios)

                from backend_comun import formatear_columnas_tabla
                cols_precios = ["P1", "P2", "P3", "P4", "P5", "P6", "Media"]

                st.text ('Precios medios de indexado', help='PRECIO MEDIO FINAL DE LA ENERGÍA. Suma de costes (energía y ATR) y margen')
                df_tabla_precios_fmt = formatear_columnas_tabla(df_tabla_precios, columnas_cent_eur_kwh=cols_precios, incluir_unidades=False)
                st.dataframe(df_tabla_precios_fmt, use_container_width=True)
                
                st.text ('Costes medios de indexado', help = 'COSTE MEDIO DE LA ENERGÍA, sin incluir ATR ni MARGEN.')
                df_tabla_costes_fmt = formatear_columnas_tabla(df_tabla_costes, columnas_cent_eur_kwh=cols_precios, incluir_unidades=False)    
                st.dataframe(df_tabla_costes_fmt, use_container_width=True)

                st.text ('Costes de ATR')
                df_tabla_pycs_fmt = formatear_columnas_tabla(df_tabla_pyc, columnas_cent_eur_kwh=cols_precios, incluir_unidades=False)
                st.dataframe(df_tabla_pycs_fmt, use_container_width=True )
                
                st.text ('Margen')
                df_tabla_margen_fmt = formatear_columnas_tabla(df_tabla_margen, columnas_cent_eur_kwh=cols_precios, incluir_unidades=False)
                st.dataframe(df_tabla_margen_fmt, use_container_width=True )

                st.subheader("Apuntamiento SPOT / OMIE", divider="rainbow")
                st.caption(
                    "Las filas por peaje muestran el apuntamiento horario sin ponderar. "
                    "La fila de curva, cuando existe, está ponderada por el consumo neto."
                )
                st.dataframe(
                    df_tabla_apuntamiento.style.format("{:.3f}", na_rep="-"),
                    use_container_width=True,
                )


with tab2:
    # gráfico de evolución de los precios medios mensuales
    st.subheader("Comparativa anual de los precios medios de indexado, por peaje de acceso (media acumulada)", divider='rainbow')
    st.plotly_chart(graf_precios_diarios, use_container_width=True)
    st.subheader("Evolución de los precios medios de indexado, por meses", divider='rainbow')
    st.plotly_chart(graf_mensual)
    st.subheader("Evolución de los precios medios de indexado, por días", divider='rainbow')
    st.plotly_chart(graf_evol_precios_diarios, use_container_width=True)
    
    

    df_delta, fig_delta = graficar_diferencial_precios_mensuales(
        df_mensual=df_precios_mensuales_sin_curva,
        anio_base=2025,
        anio_comp=2026,
        convertir_a_cent_kwh=True
    )
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(fig_delta, use_container_width=True)
        
    with c2:
        MESES_ORDEN = [
            "enero", "febrero", "marzo", "abril",
            "mayo", "junio", "julio", "agosto",
            "septiembre", "octubre", "noviembre", "diciembre"
        ]
        df_mes_años = tabla_evol_mes_por_años(
            df_precios_mensuales_sin_curva, MESES_ORDEN
        )
        #st.subheader("Comparativa mensual (precios en c€/kWh)", divider='rainbow')
        st.subheader(f"Comparativa mensual de precios (c€/kWh) - {st.session_state.mes_select_evol}", divider='rainbow')
        st.selectbox("Selecciona mes", MESES_ORDEN, key = 'mes_select_evol')
        st.dataframe(
        df_mes_años.style.format({
            "SPOT": "{:.2f}",
            "Precio 2.0": "{:.2f}",
            "Precio 3.0": "{:.2f}",
            "Precio 6.1": "{:.2f}",
            "Ratio 2.0 / SPOT": "{:.2f}",
            "Ratio 3.0 / SPOT": "{:.2f}",
            "Ratio 6.1 / SPOT": "{:.2f}",
        }),
        use_container_width=True,
        hide_index=True
    )
        



with tab3:
    #if 'df_curva_sheets' not in st.session_state or st.session_state.df_curva_sheets is None:
    if 'df_curva_sheets' not in st.session_state:
        st.warning('Introduce una curva de carga')
        st.stop()
    elif st.session_state.df_curva_sheets is None:
        st.warning('Asegúrate de tener seleccionado un rango de fechas')
        st.stop()
    
    c1, c2, c3 = st.columns(3)
    with c1:
        
        # TABLA RESUMEN DE CONSUMOS, COSTES Y PRECIOS MEDIOS DE INDEXADO PONDERADOS A LA CURVA DE CARGA

        print('df_uso para usar en resumen')
        print(df_uso)
        df_resumen = obtener_df_resumen(df_uso, None, 0.0)
        from backend_comun import formatear_resumen_mixto
        #df_resumen_view = formatear_df_resumen(df_resumen)
        df_resumen_fmt = df_resumen.copy()

        # Transponemos porque las unidades están en el índice, no en columnas
        df_resumen_fmt = df_resumen_fmt.T

        df_resumen_fmt = formatear_columnas_tabla(
            df_resumen_fmt,
            columnas_kwh=["Consumo (kWh)"],
            columnas_euros=["Coste (€)"],
            columnas_eur_kwh=["Precio medio (€/kWh)"],
            incluir_unidades=False,
        )

        # Volvemos al formato original
        df_resumen_fmt = df_resumen_fmt.T

        
        
        st.subheader(f':orange[{st.session_state.texto_precios}]')
        st.subheader(f'Resumen de :blue[INDEXADO]')
        #st.dataframe(df_resumen_view, use_container_width=True)
        st.dataframe(df_resumen_fmt, use_container_width=True)
        from io import BytesIO

        output = BytesIO()
        df_resumen.to_excel(output, index=True, engine="openpyxl")
        output.seek(0)
        fecha_inicio, fecha_fin = st.session_state.rango_curvadecarga
        nombre_excel = f"resumen_indexado_{fecha_inicio:%Y%m%d}_{fecha_fin:%Y%m%d}.xlsx"


        st.download_button(
            "Descargar Excel",
            data=output,
            file_name=nombre_excel,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        df_resumen_cober = obtener_df_resumen(df_curva_cober_omip, None, 0.0)
        df_resumen_cober_view = formatear_df_resumen(df_resumen_cober)
        #st.subheader(f'Resumen de :violet[COBERTURA] para el suministro con peaje de acceso :orange[{st.session_state.atr_dfnorm}]')
        st.subheader(f'Resumen de :violet[COBERTURA]')
        ca,cb = st.columns(2)
        with ca:
            st.number_input('Introduce el valor de la cobertura realizada', min_value=20.0, max_value=120.0, step=.1, key = 'precio_cobertura', help = 'Se aplicará un apuntamiento medio real a la cobertura realizada')
        with cb:
            st.metric('Apuntamiento medio ponderado', value=apuntamiento_spot)
        st.dataframe(df_resumen_cober_view, use_container_width=True)


        # CARGAR EXCEL CON PRECIOS FIJOS
        st.subheader(f'Tabla de precios :red[FIJOS] para comparar')
        uploaded_file = st.file_uploader(
            "Sube el Excel con ofertas de precio fijo",
            type=["xlsx", "xls"]
        )
        st.caption("Los precios de las columnas P1…P6 deben indicarse en €/kWh.")

        st.markdown("**Introducción manual de precios fijos (€/kWh)**")
        nombre_oferta_manual = st.text_input(
            "Nombre de la oferta manual",
            value="Oferta manual",
            key="nombre_oferta_fija_manual",
        )
        es_20td_manual = (
            str(st.session_state.get("atr_dfnorm", ""))
            .replace(" ", "")
            .upper()
            .startswith("2.0")
        )
        periodos_manuales = (
            ["P1", "P2", "P3"]
            if es_20td_manual else [f"P{i}" for i in range(1, 7)]
        )
        columnas_precios_manuales = st.columns(len(periodos_manuales))
        precios_manuales = {}
        for columna, periodo in zip(
            columnas_precios_manuales, periodos_manuales
        ):
            with columna:
                precios_manuales[periodo] = st.number_input(
                    periodo,
                    min_value=0.0,
                    max_value=2.0,
                    value=0.0,
                    step=0.001,
                    format="%.6f",
                    key=f"precio_fijo_manual_{periodo}",
                    help="Precio fijo en €/kWh.",
                )
        if st.button(
            "Añadir o actualizar oferta manual",
            key="guardar_oferta_fija_manual",
            type="primary",
        ):
            nombre_limpio = nombre_oferta_manual.strip()
            if not nombre_limpio:
                st.error("Indica un nombre para la oferta manual.")
            elif any(precios_manuales[p] <= 0 for p in periodos_manuales):
                st.error("Introduce un precio mayor que cero en todos los periodos.")
            else:
                fila_manual = {"oferta": nombre_limpio}
                fila_manual.update({f"P{i}": 0.0 for i in range(1, 7)})
                fila_manual.update(precios_manuales)
                st.session_state.df_oferta_fija_manual = pd.DataFrame(
                    [fila_manual]
                )
                st.success(f"Oferta manual «{nombre_limpio}» actualizada.")

        if uploaded_file is not None:
            df_new = pd.read_excel(uploaded_file)
            df_new.columns = df_new.columns.str.strip()

            # Primera columna = oferta
            col_oferta = df_new.columns[0]
            df_new = df_new.rename(columns={col_oferta: "oferta"})

            if df_new["oferta"].isna().any():
                st.error("Hay ofertas sin nombre en el Excel.")
                st.stop()

            # Mantener todas las categorías del eje Y como texto, incluso si
            # los nombres de oferta introducidos en el Excel son números.
            df_new["oferta"] = df_new["oferta"].astype(str).str.strip()

            if df_new["oferta"].eq("").any():
                st.error("Hay ofertas sin nombre en el Excel.")
                st.stop()

            periodos = [f"P{i}" for i in range(1, 7)]

            faltan = set(periodos) - set(df_new.columns)
            if faltan:
                st.error(f"Faltan columnas de periodos: {faltan}")
                st.stop()

            for p in periodos:
                df_new[p] = pd.to_numeric(df_new[p], errors="coerce")

            if df_new[periodos].isna().any().any():
                st.error("Hay valores no numéricos en los precios")
                st.stop()

            if (df_new[periodos] < 0).any().any():
                st.error("Los precios P1…P6 no pueden contener valores negativos.")
                st.stop()

            precio_maximo = df_new[periodos].max().max()
            if precio_maximo > 2:
                st.warning(
                    "Se han detectado precios superiores a 2 €/kWh. Es posible "
                    "que el Excel esté expresado en c€/kWh o €/MWh. Convierte "
                    "los valores a €/kWh antes de comparar o confirma que la "
                    "unidad introducida es correcta."
                )
                confirmar_unidades = st.checkbox(
                    "Confirmo que los precios del Excel están expresados en €/kWh",
                    key="confirmar_unidades_ofertas_fijas",
                )
                if not confirmar_unidades:
                    st.stop()

            # 🔁 Añadimos margen si procede
            df_ofertas_calc = df_new.copy()
            if st.session_state.get("aplicar_margen_fijo", False):
                
                periodos = [f"P{i}" for i in range(1, 7)]
                
                for p in periodos:
                    if p in df_ofertas_calc.columns:
                        #df_ofertas_calc[p] = df_ofertas_calc[p] + margen_simul/100   
                        df_ofertas_calc[p] = df_ofertas_calc[p] + st.session_state.margen_fijo/1000   
                
            oferta_manual = st.session_state.get("df_oferta_fija_manual")
            ofertas_combinadas = [df_ofertas_calc]
            if oferta_manual is not None and not oferta_manual.empty:
                ofertas_combinadas.append(oferta_manual)
            st.session_state.df_ofertas_fijas = (
                pd.concat(ofertas_combinadas, ignore_index=True)
                .drop_duplicates(subset=["oferta"], keep="last")
            )
                
            df_ofertas_view = formatear_df_resumen(st.session_state.df_ofertas_fijas)

            st.markdown("Ofertas fijas cargadas")

            if st.session_state.df_ofertas_fijas.empty:
                st.info("Aún no hay ofertas cargadas")
            else:
                st.checkbox("Aplicar margen comercial también a ofertas fijas", value=False, key='aplicar_margen_fijo')
                if st.session_state.get("aplicar_margen_fijo", False):
                    st.number_input('Introduce el margen para las ofertas FIJO.', min_value=0.0, max_value=30.0, step=.1, key = 'margen_fijo') #€/MWh
                st.dataframe(
                    #st.session_state.df_ofertas_fijas_simul,
                    df_ofertas_view,
                    use_container_width=True,
                    hide_index=True
                )
        elif not st.session_state.df_oferta_fija_manual.empty:
            st.session_state.df_ofertas_fijas = (
                st.session_state.df_oferta_fija_manual.copy()
            )
            st.markdown("Oferta fija manual cargada")
            st.dataframe(
                formatear_df_resumen(st.session_state.df_ofertas_fijas),
                use_container_width=True,
                hide_index=True,
            )


        with c2:

            import pandas as pd
            

            periodos = [f"P{i}" for i in range(1, 7)]

            # Consumos por periodo
            consumos = df_resumen.loc["Consumo (kWh)", periodos]

            resultados = []

            # Ofertas fijas
            df_ofertas_comparativa = st.session_state.get("df_ofertas_fijas")
            if df_ofertas_comparativa is not None and not df_ofertas_comparativa.empty:
                for _, row in df_ofertas_comparativa.iterrows():
                    coste_total = (consumos * row[periodos]).sum()
                    energia_total = consumos.sum()
                    precio_medio = coste_total / energia_total

                    resultados.append({
                        "Oferta": row["oferta"],
                        "Tipo": "Fijo",
                        "Coste (€)": coste_total,
                        "Precio medio (€/kWh)": precio_medio
                    })

            # Indexado
            precios_index = df_resumen.loc["Precio medio (€/kWh)", periodos]
            coste_index = (consumos * precios_index).sum()
            precio_medio_index = coste_index / consumos.sum()

            resultados.append({
                "Oferta": "Indexado",
                "Tipo": "Indexado",
                "Coste (€)": coste_index,
                "Precio medio (€/kWh)": precio_medio_index
            })

            # Cobertura OMIP
            precios_cober = df_resumen_cober.loc["Precio medio (€/kWh)", periodos]
            coste_cober = (consumos * precios_cober).sum()
            precio_medio_cober = coste_cober / consumos.sum()

            resultados.append({
                "Oferta": "Cobertura",
                "Tipo": "Cobertura",
                "Coste (€)": coste_cober,
                "Precio medio (€/kWh)": precio_medio_cober
            })



            df_resultados = pd.DataFrame(resultados)
            # Plotly puede interpretar como números etiquetas de texto como
            # "1" o "2". Normalizamos de nuevo junto al punto de visualización.
            df_resultados["Oferta"] = df_resultados["Oferta"].astype(str).str.strip()

            # Ordenar por coste anual (de más barato a más caro)
            df_resultados = df_resultados.sort_values("Coste (€)").reset_index(drop=True)

            coste_min = df_resultados["Coste (€)"].iloc[0]

            df_resultados["% sobre la más barata"] = (
                (df_resultados["Coste (€)"] - coste_min) / coste_min * 100
            )

            df_resultados["Δ vs más barata (€)"] = (
                df_resultados["Coste (€)"] - coste_min
            )

            #df_resultados = df_resultados.sort_values("Coste (€)")

            df_view = df_resultados.copy()

            df_view["Coste (€)"] = df_view["Coste (€)"].apply(
                lambda x: formato_euros(x, unidad=False)
            )

            df_view["Precio medio (€/kWh)"] = df_view["Precio medio (€/kWh)"].apply(
                lambda x: formato_eur_kwh(x, unidad=False)
            )

            df_view["Δ vs más barata (€)"] = df_view["Δ vs más barata (€)"].apply(
                lambda x: formato_euros(x, unidad=False)
            )
            df_view["% sobre la más barata"] = df_view["% sobre la más barata"].apply(
                lambda x: formato_pct(x, 1)
            )

            st.subheader(f'Peaje de acceso :orange[{st.session_state.atr_dfnorm}]')
            st.subheader("📊 Comparativa TOTALPOWER")
            st.dataframe(df_view, use_container_width=True, hide_index=True)

            orden_ofertas = df_resultados["Oferta"].tolist()

            colores_tipo = {
                "Fijo": "#EF4444",
                "Indexado": "#F59E0B",
                "Cobertura": "#8B5CF6"
            }
            fig = px.bar(
                df_resultados,
                y="Oferta",
                x="Coste (€)",
                color="Tipo",
                color_discrete_map=colores_tipo,
                title=f"Coste por oferta/tipo de contrato",
                text_auto=".2f",
                category_orders={"Oferta": orden_ofertas},
                orientation ='h'
            )
            fig.update_layout(
                xaxis_title="Coste (€)",
                yaxis_title="",
                legend_title="",
                title_font=dict(size=24),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="center",
                    x=0.5
                )
            )
            fig.update_yaxes(
                type="category",
                categoryorder="array",
                categoryarray=orden_ofertas,
            )
            fig.update_traces(
                textfont_size=24,
                width=0.6,
            )

            fig = aplicar_estilo(fig)
            altura_grafico_barras = max(300, 150 + len(df_resultados) * 55)
            fig.update_layout(
                height=altura_grafico_barras,
                bargap=0.4,
                barcornerradius=4,
            )
            fig.update_yaxes(tickfont=dict(size=16))

            st.plotly_chart(fig, use_container_width=True)

        with c3:

            opciones_comparativa = ["Cobertura"]

            if (
                "df_ofertas_fijas" in st.session_state
                and st.session_state.df_ofertas_fijas is not None
                and not st.session_state.df_ofertas_fijas.empty
            ):
                opciones_comparativa += (
                    st.session_state.df_ofertas_fijas["oferta"]
                    .astype(str)
                    .str.strip()
                    .tolist()
                )

            st.selectbox("Selecciona la opción a comparar contra el indexado", opciones_comparativa, index=0, key = 'opcion_comparativa')
            
            #st.subheader(f'Comparativa INDEXADO vs {st.session_state.opcion_comparativa}')
            st.subheader(titulo_comp)
            st.plotly_chart(fig_heat, use_container_width=True)

            graf_medias_horarias=graficar_media_horaria('Total')
            graf_medias_horarias.add_trace(
                go.Scatter(
                    x=df_coste_h["hora"],
                    y=df_coste_h["coste_total"],
                    mode="lines",
                    name="Coste medio indexado",
                    line=dict(
                        color="#F59E0B",
                        width=5
                    ),
                    yaxis="y2"
                )
            )
            graf_medias_horarias.update_layout(
                yaxis2=dict(
                    title="Coste medio (€)",
                    overlaying="y",
                    side="right",
                    showgrid=False
                ),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.0,
                    xanchor="center",
                    x=0.5
                )
            )
            df_coste_comp = df_curva_comp.copy()
            df_coste_comp_h = (
                df_coste_comp
                .groupby("hora", as_index=False)["coste_total"]
                .mean()
            )
            graf_medias_horarias.add_trace(
                go.Scatter(
                    x=df_coste_comp_h["hora"],
                    y=df_coste_comp_h["coste_total"],
                    mode="lines",
                    name=nombre_serie_comp,
                    line=dict(color=color_serie_comp, width=5),
                    yaxis="y2"
                )
            )

            st.plotly_chart(graf_medias_horarias)
            



       
