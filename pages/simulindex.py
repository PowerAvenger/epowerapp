import streamlit as st
from backend_simulindex import (obtener_historicos_meff, obtener_meff_trimestral, obtener_meff_mensual,
                                obtener_hist_mensual, obtener_spot_mensual,
                                obtener_graf_hist, obtener_grafico_omip, obtener_grafico_omip_omie,
                                obtener_trimestres_futuros, construir_escenarios)
from backend_comun import colores_precios, obtener_df_resumen, formatear_df_resumen, formatear_df_resultados
import pandas as pd
import plotly.express as px
from utilidades import generar_menu, init_app, init_app_index
from backend_curvadecarga import graficar_media_horaria, graficar_queso_periodos

if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')

generar_menu()
init_app()

st.sidebar.header('⚡ Simulación de indexados ⚡')
zona_mensajes = st.sidebar.empty()
if 'df_sheets' not in st.session_state:
    zona_mensajes.warning('Cargando históricos de indexado. Espera a que estén disponibles...', icon = '⚠️')

init_app_index()


df_historicos_FTB, ultimo_registro = obtener_historicos_meff()
df_FTB_trimestral, df_FTB_trimestral_futuros, fecha_ultimo_omip, media_omip_trimestral, lista_trimestres_hist, trimestre_actual, df_ultimos_precios_trim = obtener_meff_trimestral(df_historicos_FTB)
df_FTB_mensual, df_FTB_mensual_simulindex, fecha_ultimo_omip_mensual, media_omip_mensual, lista_meses_hist, mes_actual = obtener_meff_mensual(df_historicos_FTB)

if 'omie_slider' not in st.session_state:
    st.session_state.omie_slider = round(media_omip_trimestral)
def reset_slider():
    st.session_state.omie_slider = round(media_omip_trimestral)

if 'trimestre_cobertura' not in st.session_state:
    st.session_state.trimestre_cobertura = trimestre_actual
if 'mes_cobertura' not in st.session_state:
    st.session_state.mes_cobertura = mes_actual 

lista_trimestres_futuros, trimestre_inicial = obtener_trimestres_futuros(df_FTB_trimestral_futuros)   

if 'trimestre_futuro' not in st.session_state:
    st.session_state.trimestre_futuro = trimestre_inicial

# obtenemos históricos de medias mensuales de omie df_mes y un filtrado hist de los últimos 12 meses 
if 'df_curva_sheets' in st.session_state and st.session_state.df_curva_sheets is not None:
    def n_meses_df(df, col_fecha="fecha"):
        return (
            pd.to_datetime(df[col_fecha])
            .dt.to_period("M")
            .nunique()
        )
    MIN_MESES_OPT = 10
    if n_meses_df(st.session_state.df_curva_sheets) >= MIN_MESES_OPT:
        #df_hist, df_mes = hist_mensual(st.session_state.df_curva_sheets)
        df_sheets_origen = st.session_state.df_curva_sheets
    else:
        #df_hist, df_mes = hist_mensual(st.session_state.df_sheets)
        df_sheets_origen = st.session_state.df_sheets
else:
    #df_hist, df_mes = hist_mensual(st.session_state.df_sheets)
    df_sheets_origen = st.session_state.df_sheets

df_hist = obtener_hist_mensual(df_sheets_origen)
#df_hist2, df_mes_cober = hist_mensual(st.session_state.df_sheets)
df_spot_mensual = obtener_spot_mensual()

#print('df_mes para cobertura')
#print(df_mes_cober)


grafico, simul20, simul30, simul61, simulcurva = obtener_graf_hist(df_hist, st.session_state.omie_slider, colores_precios)

# Inicializamos margen a cero
if 'margen_simulindex' not in st.session_state:
    st.session_state.margen_simulindex = 5
    
#if 'df_curva_sheets' in st.session_state and st.session_state.df_curva_sheets is not None and simulcurva is not None:
    #df_int, df_resumen_simul = resumen_periodos_simulado(df_curva = st.session_state.df_curva_sheets, simul_curva = simulcurva)  
#    df_resumen_simul = obtener_df_resumen(st.session_state.df_curva_sheets, simulcurva, 0.0)
#    df_resumen_simul_view = formatear_df_resumen(df_resumen_simul)

graf_omip_trimestral = obtener_grafico_omip(df_FTB_trimestral_futuros)
graf_omip_mensual = obtener_grafico_omip(df_FTB_mensual_simulindex)

df_trim_sel = df_FTB_trimestral[df_FTB_trimestral['Entrega'] == st.session_state.trimestre_futuro].copy()
graf_omip_trimestral_select = obtener_grafico_omip(df_trim_sel)


# dfs para trimestres históricos
df_FTB_trimestral_cobertura = df_FTB_trimestral[df_FTB_trimestral['Entrega'] == st.session_state.trimestre_cobertura]
df_FTB_mensual_cobertura = df_FTB_mensual[df_FTB_mensual['Entrega'] == st.session_state.mes_cobertura]
print('df FTB trimestral cobertura')
print(df_FTB_trimestral_cobertura)
graf_omip_omie_trimestral = obtener_grafico_omip_omie(df_FTB_trimestral_cobertura, df_spot_mensual, st.session_state.trimestre_cobertura)
graf_omip_omie_mensual = obtener_grafico_omip_omie(df_FTB_mensual_cobertura, df_spot_mensual, st.session_state.mes_cobertura)



if "df_ofertas_fijas_simul" not in st.session_state:
    st.session_state.df_ofertas_fijas_simul = pd.DataFrame()
if "df_ofertas_fijas_simul_trim" not in st.session_state:
    st.session_state.df_ofertas_fijas_trim = pd.DataFrame()    


#BARRA LATERAL+++++++++++++++++++++++++++++++++++++++++++++++++++++++

zona_mensajes.success('Cargados todos los históricos de indexado. Ya puedes consultar los datos.', icon = '👍')

with st.sidebar.expander('¡Personaliza la simulación!', icon = "ℹ️"):
    st.write('Usa el deslizador para modificar el valor de :green[OMIE] estimado. No te preocupes, siempre puedes resetear al valor por defecto.')
st.sidebar.slider(':green[OMIE] en €/MWh', min_value = 30, max_value = 150, step = 1, key = 'omie_slider')
reset_omip = st.sidebar.button('Resetear OMIE', on_click = reset_slider)
 
with st.sidebar.expander('¿Quieres añadir margen?', icon = "ℹ️"):
    st.write('Añade :violet[margen] al gusto y obtén un precio medio de indexado más ajustado con tus necesidades.')
    #añadir_margen = st.sidebar.toggle('Quieres añadir :violet[margen]?')
    #if añadir_margen:
st.sidebar.slider('Añade margen al precio base de indexado en €/MWh', min_value = 0, max_value = 50, step = 1, key = 'margen_simulindex')

zona_mensajes = st.sidebar.empty()


simul20_margen = simul20 + st.session_state.margen_simulindex / 10
simul30_margen = simul30 + st.session_state.margen_simulindex / 10
simul61_margen = simul61 + st.session_state.margen_simulindex / 10



if 'df_curva_sheets' in st.session_state and st.session_state.df_curva_sheets is not None and simulcurva is not None:
    # esto es para la tabla original de la página principal que se modifica con el margen del slider
    simulcurva_margen = simulcurva + st.session_state.margen_simulindex / 10
    df_resumen_simul = obtener_df_resumen(st.session_state.df_curva_sheets, simulcurva_margen, 0.0)
    df_resumen_simul_view = formatear_df_resumen(df_resumen_simul)
    df_uso_anual = st.session_state.df_curva_sheets.copy()
    def filtrar_df_trimestre(df_norm, producto):
        
        mapa_trimestres = {
            'Q1': [1,2,3],
            'Q2': [4,5,6],
            'Q3': [7,8,9],
            'Q4': [10,11,12]
        }
        
        trim, _ = producto.split('-')
        meses_trim = mapa_trimestres[trim]
        
        df_trim = df_norm[
            df_norm['fecha_hora'].dt.month.isin(meses_trim)
        ].copy()
        
        return df_trim
    df_uso_trimestral = filtrar_df_trimestre(st.session_state.df_curva_sheets, st.session_state.trimestre_futuro)

    


tab1, tab2, tab3, tab4, tab5 = st.tabs(['Principal', 'Futuros', 'OMIP vs OMIE', 'Comparador', 'Cobertura trimestral'])


#PANTALLA PRINCIPAL CON LAS RECTAS DE SIMULACIÓN Y DATOS PARA UN SOLO ESCENARIO OMIE------------------------------------------------------------------------------------------------------------------
with tab1:
 
    col1, col2 = st.columns([0.2, 0.8])
    with col1:
        st.info('A partir de :green[OMIE] estimado y opcionalmente :violet[margen] añadido, obtendrás unos precios medios de indexado.', icon = "ℹ️")
        with st.container(border = True):
            st.subheader(':blue-background[Datos de entrada]', divider = 'rainbow')
            col11, col12 = st.columns(2)
            with col11:
                st.metric(':green[OMIE] (€/MWh)', value = st.session_state.omie_slider, help = 'Este es el valor OMIE de referencia que has utilizado como entrada')
            with col12:
                st.metric(':violet[Margen] (€/MWh)', value = st.session_state.margen_simulindex, help = 'Margen que añades para obtener un precio medio final más ajustado a tus necesidades')
        with st.container(border = True):
            st.subheader(':green-background[Datos de salida]', divider = 'rainbow')
            col13, col14 = st.columns(2)
            with col13:
                st.text('Precios base')
                st.metric(':orange[Precio 2.0] c€/kWh', value = simul20, help = 'Este el precio 2.0 medio simulado a un año vista')
                st.metric(':red[Precio 3.0] c€/kWh', value = simul30, help = 'Este el precio 3.0 medio simulado a un año vista')
                st.metric(':blue[Precio 6.1] c€/kWh', value = simul61, help='Este el precio 6.1 medio simulado a un año vista')
                if 'df_curva_sheets' in st.session_state and st.session_state.df_curva_sheets is not None and simulcurva is not None:
                    st.metric(f':green[Precio CURVA {st.session_state.atr_dfnorm}]  c€/kWh', value = simulcurva, help='Este el precio medio ponderado simulado a un año vista')
            with col14:
                st.text('Precios con margen')
                st.metric(':orange[Precio 2.0] c€/kWh', value = round(simul20_margen, 2), help = 'Este el precio 2.0 con el margen añadido')
                st.metric(':red[Precio 3.0] c€/kWh', value = round(simul30_margen, 2), help = 'Este el precio 3.0 con el margen añadido')
                st.metric(':blue[Precio 6.1] c€/kWh', value = round(simul61_margen, 2), help = 'Este el precio 6.1 con el margen añadido')
                if 'df_curva_sheets' in st.session_state and st.session_state.df_curva_sheets is not None and simulcurva is not None:
                    st.metric(f':green[Precio CURVA {st.session_state.atr_dfnorm}]  c€/kWh', value = simulcurva_margen, help='Este el precio medio ponderado con el margen añadido')
    with col2:
        st.info('**¿Cómo funciona?** Los :orange[puntos] son valores de indexado de los 12 últimos meses. Las :orange[líneas] reflejan una tendencia. Los :orange[círculos] simulan los precios medios de indexado a un año vista en base al valor de OMIE estimado.',icon="ℹ️")
        st.plotly_chart(grafico)
        if 'df_curva_sheets' in st.session_state and st.session_state.df_curva_sheets is not None and simulcurva is not None:
            st.write(f'Tabla resumen de datos para el suministro :green[{st.session_state.atr_dfnorm}] con OMIE a :green[{st.session_state.omie_slider}]€/MWh y margen de :green[{st.session_state.margen_simulindex}]€/MWh')
            st.dataframe(df_resumen_simul_view)
                

          
#PANTALLA DE FUTUROS--------------------------------------------------
with tab2:
    
    col3, col4 = st.columns([0.2, 0.8])
    with col3:
        with st.container(border = True):
            st.info('Aquí tienes el valor medio de :blue[OMIP] en €/MWh a partir de los siguientes trimestres, así como la fecha del último registro.', icon = "ℹ️")
            st.subheader('Datos de OMIP', divider = 'rainbow')
            col31, col32 = st.columns(2)
            with col31:
                st.metric('Fecha', value = fecha_ultimo_omip)
            with col32:
                st.metric(':blue[OMIP] medio', value = media_omip_trimestral)
    with col4:
        st.info('Aquí tienes la evolución de :blue[OMIP] por trimestres', icon = "ℹ️")
        st.write(graf_omip_trimestral)
        st.info('Aquí tienes la evolución de :blue[OMIP] por meses', icon = "ℹ️")
        st.write(graf_omip_mensual)
    

# PANTALLA DE COMPARACIONES OMIP EVOL VS OMIE
with tab3:
    with st.container():
        col5, col6 = st.columns([0.2, 0.8])
        with col5:
            lista_trimestres_hist = lista_trimestres_hist[::-1]  # invierte la lista
            st.selectbox('Selecciona el trimestre', options=lista_trimestres_hist, key = 'trimestre_cobertura', index=0)
        with col6:
            st.plotly_chart(graf_omip_omie_trimestral)
    with st.container():
        col5, col6 = st.columns([0.2, 0.8])
        with col5:
            lista_meses_hist = lista_meses_hist[::-1]  # invierte la lista
            st.selectbox('Selecciona el mes', options=lista_meses_hist, key = 'mes_cobertura', index=0)
        with col6:
            st.plotly_chart(graf_omip_omie_mensual)



with tab4:

    if 'df_curva_sheets' not in st.session_state or st.session_state.df_curva_sheets is None or simulcurva is None:
        st.warning('Introduce una curva de carga anual')
        st.stop()
    c1, c2, c3 = st.columns(3)
    with c1:
        
        
        # ----------------------------
        # 5. FORMATO ESPAÑOL (SOLO VISTA)
        # ----------------------------

        print('df_uso para usar en resumen')
        print(df_uso_anual)
        #df_resumen_view = df_resumen.copy()
        
        df_resumen = obtener_df_resumen(df_uso_anual, simulcurva, 0.0)
        df_consumos = df_resumen.loc[["Consumo (kWh)"]]
        df_consumos_view = formatear_df_resumen(df_consumos)
        # ----------------------------
        # 6. MOSTRAR TABLA
        # ----------------------------
        st.subheader(f'Consumos según curva de carga introducida para peaje :orange[{st.session_state.atr_dfnorm}]')
        st.dataframe(
            df_consumos_view,
            use_container_width=True
        )

    with c2:
        st.subheader(f'Parametriza')
            
        c11, c12, c13, c14 = st.columns(4)
        with c11:
            margen_simul = st.number_input("Margen (€/MWh)", min_value=0.0, max_value=50.0, value=10.0, step=1.1) / 10   # → c€/kWh        
        with c12:
            simul_a = st.number_input("OMIE simulado A (€/MWh)", value=55.0)
        with c13:
            simul_b = st.number_input("OMIE simulado B (€/MWh)", value=60.0)
        with c14:
            simul_c = st.number_input("OMIE simulado C (€/MWh)", value=65.0)

        lista_simul = [simul_a, simul_b, simul_c]

        escenarios = []
        
        print(f'margen_simul: {margen_simul}')

        for etiqueta, omie_value in zip(["A", "B", "C"], lista_simul):
            _, _, _, _, simul_curva = obtener_graf_hist(df_hist, omie_value, colores_precios)
            print(f'simul_curva antes de añadir margen: {simul_curva}')
            simul_curva = simul_curva + margen_simul
            print(f'simul_curva después de añadir margen: {simul_curva}')
            df_resumen_simul = obtener_df_resumen(df_uso_anual, simul_curva, 0.0)

            escenarios.append({
                "label": f"Indexado simulado {etiqueta} ({omie_value:.1f} €/MWh)",
                "simul_curva": simul_curva,
                "df_resumen": df_resumen_simul
            })

        st.subheader('Resultado indexados según escenario')
        for esc in escenarios:
            st.markdown(esc["label"])

            df_vista = esc["df_resumen"].loc[
                ["Coste (€)", "Precio medio (€/kWh)"]
            ]

            st.dataframe(
                formatear_df_resumen(df_vista),
                use_container_width=True
            )    


        # CARGAR EXCEL CON PRECIOS FIJOS+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        st.subheader("Carga excel con ofertas a precio FIJO")
        uploaded_file = st.file_uploader(
            "Sube el Excel con ofertas de precio fijo",
            type=["xlsx", "xls"]
        )

        if uploaded_file is not None:

            # 🔥 CLAVE: empezar siempre de cero
            st.session_state.df_ofertas_fijas = None

            df_new = pd.read_excel(uploaded_file)
            df_new.columns = df_new.columns.str.strip()

            # Primera columna = oferta
            col_oferta = df_new.columns[0]
            df_new = df_new.rename(columns={col_oferta: "oferta"})

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

            

            # 🔁 Reemplazar directamente
            st.session_state.df_ofertas_fijas_simul = df_new.copy()
            df_ofertas_view = formatear_df_resumen(st.session_state.df_ofertas_fijas_simul)

            st.markdown("Ofertas fijas cargadas")

            if st.session_state.df_ofertas_fijas_simul.empty:
                st.info("Aún no hay ofertas cargadas")
            else:
                st.dataframe(
                    #st.session_state.df_ofertas_fijas_simul,
                    df_ofertas_view,
                    use_container_width=True,
                    hide_index=True
                )


        with c2:

            
            

            periodos = [f"P{i}" for i in range(1, 7)]

            # Consumos por periodo
            consumos = df_resumen.loc["Consumo (kWh)", periodos]

            resultados = []

            # Ofertas fijas
            for _, row in st.session_state.df_ofertas_fijas_simul.iterrows():
                coste_total = (consumos * row[periodos]).sum()
                energia_total = consumos.sum()
                precio_medio = coste_total / energia_total

                resultados.append({
                    "Oferta": row["oferta"],
                    "Tipo": "Fijo",
                    "Coste anual (€)": coste_total,
                    "Precio medio (€/kWh)": precio_medio
                })

            # Indexado
            for esc in escenarios:
                df_res = esc["df_resumen"]

                precios_index = df_res.loc["Precio medio (€/kWh)", periodos]
                coste_index = (consumos * precios_index).sum()
                precio_medio_index = coste_index / consumos.sum()

                resultados.append({
                    "Oferta": esc["label"],
                    "Tipo": "Indexado",
                    "Coste anual (€)": coste_index,
                    "Precio medio (€/kWh)": precio_medio_index
                })

            df_resultados = pd.DataFrame(resultados)
            # Ordenar por coste anual (de más barato a más caro)
            df_resultados = df_resultados.sort_values("Coste anual (€)").reset_index(drop=True)

            coste_min = df_resultados["Coste anual (€)"].iloc[0]

            df_resultados["% sobre la más barata"] = (
                (df_resultados["Coste anual (€)"] - coste_min) / coste_min * 100
            )

            df_resultados["Δ vs más barata (€)"] = (
                df_resultados["Coste anual (€)"] - coste_min
            )

            
            print('df resultados')
            print(df_resultados)
            
            df_resultados_view = formatear_df_resultados(df_resultados)

            print('df resultados view')
            print(df_resultados_view)


        with c3:
            st.subheader("📊 Comparativa TOTALPOWER")
            st.dataframe(df_resultados_view, use_container_width=True, hide_index=True)

            orden_ofertas = df_resultados["Oferta"].tolist()

            fig = px.bar(
                df_resultados,
                x="Oferta",
                y="Coste anual (€)",
                color="Tipo",
                title="Coste anual por oferta",
                text_auto=".2f",
                category_orders={"Oferta": orden_ofertas}
            )

            fig.update_layout(
                yaxis_title="Coste anual (€)",
                xaxis_title="",
                legend_title="",
                bargap=.4
            )

            st.plotly_chart(fig, use_container_width=True)


        with c1:
            st.subheader("Perfil horario")    
            graf_medias_horarias = graficar_media_horaria('Total')
            st.plotly_chart(graf_medias_horarias, use_container_width=True)
            st.subheader("Consumo por periodos")
            graf_periodos, df_periodos=graficar_queso_periodos(st.session_state.df_norm_h)
            st.plotly_chart(graf_periodos, use_container_width=True)


with tab5:
    
    if 'df_curva_sheets' not in st.session_state or st.session_state.df_curva_sheets is None or simulcurva is None:
        st.warning('Introduce una curva de carga anual')
        st.stop()

       
    
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader(f'Selecciona el trimestre de la cobertura')
        st.selectbox('Selecciona trimestre futuro', options=lista_trimestres_futuros, key='trimestre_futuro')

        precio_trim_sel = df_ultimos_precios_trim.loc[df_ultimos_precios_trim['Entrega'] == st.session_state.trimestre_futuro, 'Precio'].iloc[0]

        st.write(graf_omip_trimestral_select)

        st.subheader(f'Parametriza margen y escenarios alternativos')
        c11, c12, c13, c14 = st.columns(4)
        with c11:
            st.number_input("Margen (€/MWh)", min_value=0.0, max_value=50.0, value=10.0, step=1.1, key = 'margen_simul_trim')         
        with c12:
            #st.number_input("OMIE simulado A (€/MWh)", value=55.0, key = 'simul_a_trim')
            st.caption('OMIE simulado A (€/MWh)')
            #st.text(precio_trim_sel)
            st.markdown(
                f"""
                <div style="
                    background-color:#FF8C00;
                    padding:6px 12px;
                    border-radius:6px;
                    color:white;
                    font-weight:bold;
                    display:inline-block;
                ">
                    {precio_trim_sel:.2f} €/MWh
                </div>
                """,
                unsafe_allow_html=True
            )
            st.session_state.simul_a_trim = precio_trim_sel
        with c13:
            st.number_input("OMIE simulado B (€/MWh)", value=precio_trim_sel-5, key = 'simul_b_trim')
        with c14:
            st.number_input("OMIE simulado C (€/MWh)", value=precio_trim_sel+5,key = 'simul_c_trim')


        

    with c2:
        # ----------------------------
        # 5. FORMATO ESPAÑOL (SOLO VISTA)
        # ----------------------------

        print('df_uso para usar en resumen')
        print(df_uso_trimestral)
        #df_resumen_view = df_resumen.copy()
        
        df_resumen = obtener_df_resumen(df_uso_trimestral, simulcurva, 0.0)
        df_consumos = df_resumen.loc[["Consumo (kWh)"]]
        df_consumos_view = formatear_df_resumen(df_consumos)
        
        # ----------------------------
        # 6. MOSTRAR TABLA DE CONSUMOS
        # ----------------------------
        st.subheader(f'Consumos según curva de carga introducida para peaje :orange[{st.session_state.atr_dfnorm}]')
        st.dataframe(
            df_consumos_view,
            use_container_width=True
        )
            
        lista_simul_trim = [st.session_state.simul_a_trim, st.session_state.simul_b_trim, st.session_state.simul_c_trim]

        #escenarios = []
        
        #print(f'margen_simul: {st.session_state.margen_simul_trim}')

        #for etiqueta, omie_value2 in zip(["A", "B", "C"], lista_simul):
        #    _, _, _, _, simul_curva = obtener_graf_hist(df_hist, omie_value2, colores_precios)
        #    print(f'simul_curva antes de añadir margen: {simul_curva}')
        #    simul_curva = simul_curva + st.session_state.margen_simul_trim
        #    print(f'simul_curva después de añadir margen: {simul_curva}')
        #    df_resumen_simul_trim = obtener_df_resumen(df_uso_trimestral, simul_curva, 0.0)

        #    escenarios.append({
        #        "label": f"Indexado simulado {etiqueta} ({omie_value2:.1f} €/MWh)",
        #        "simul_curva": simul_curva,
        #        "df_resumen": df_resumen_simul_trim
        #    })

        margen_simul_trim = st.session_state.margen_simul_trim / 10
        escenarios = construir_escenarios(df_uso_trimestral, lista_simul_trim, margen_simul_trim, df_hist, colores_precios)

        st.subheader('Resultado coberturas de indexados según escenario')
        for esc in escenarios:
            st.markdown(esc["label"])

            df_vista_trim = esc["df_resumen"].loc[
                ["Coste (€)", "Precio medio (€/kWh)"]
            ]

            st.dataframe(
                formatear_df_resumen(df_vista_trim),
                use_container_width=True
            )    


        # CARGAR EXCEL CON PRECIOS FIJOS+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        st.subheader("Carga excel con ofertas a precio FIJO")
        st.file_uploader("Sube el Excel con ofertas de precio fijo", type=["xlsx", "xls"], key= 'uploaded_file_trim')

        if st.session_state.uploaded_file_trim is not None:

            # 🔥 CLAVE: empezar siempre de cero
            st.session_state.df_ofertas_fijas = None

            df_new = pd.read_excel(st.session_state.uploaded_file_trim)
            df_new.columns = df_new.columns.str.strip()

            # Primera columna = oferta
            col_oferta = df_new.columns[0]
            df_new = df_new.rename(columns={col_oferta: "oferta"})

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

            

            # 🔁 Reemplazar directamente
            st.session_state.df_ofertas_fijas_simul = df_new.copy()
            df_ofertas_view = formatear_df_resumen(st.session_state.df_ofertas_fijas_simul)

            st.markdown("Ofertas fijas cargadas")

            if st.session_state.df_ofertas_fijas_simul.empty:
                st.info("Aún no hay ofertas cargadas")
            else:
                st.dataframe(
                    #st.session_state.df_ofertas_fijas_simul,
                    df_ofertas_view,
                    use_container_width=True,
                    hide_index=True
                )


        with c2:

            
            

            periodos = [f"P{i}" for i in range(1, 7)]

            # Consumos por periodo
            consumos = df_resumen.loc["Consumo (kWh)", periodos]

            resultados = []

            # Ofertas fijas
            for _, row in st.session_state.df_ofertas_fijas_simul.iterrows():
                coste_total = (consumos * row[periodos]).sum()
                energia_total = consumos.sum()
                precio_medio = coste_total / energia_total

                resultados.append({
                    "Oferta": row["oferta"],
                    "Tipo": "Fijo",
                    "Coste anual (€)": coste_total,
                    "Precio medio (€/kWh)": precio_medio
                })

            # Indexado
            for esc in escenarios:
                df_res = esc["df_resumen"]

                precios_index = df_res.loc["Precio medio (€/kWh)", periodos]
                coste_index = (consumos * precios_index).sum()
                precio_medio_index = coste_index / consumos.sum()

                resultados.append({
                    "Oferta": esc["label"],
                    "Tipo": "Indexado",
                    "Coste anual (€)": coste_index,
                    "Precio medio (€/kWh)": precio_medio_index
                })

            df_resultados = pd.DataFrame(resultados)
            # Ordenar por coste anual (de más barato a más caro)
            df_resultados = df_resultados.sort_values("Coste anual (€)").reset_index(drop=True)

            coste_min = df_resultados["Coste anual (€)"].iloc[0]

            df_resultados["% sobre la más barata"] = (
                (df_resultados["Coste anual (€)"] - coste_min) / coste_min * 100
            )

            df_resultados["Δ vs más barata (€)"] = (
                df_resultados["Coste anual (€)"] - coste_min
            )

            
            print('df resultados')
            print(df_resultados)
            
            df_resultados_view = formatear_df_resultados(df_resultados)

            print('df resultados view')
            print(df_resultados_view)


        with c3:
            st.subheader("📊 Comparativa TOTALPOWER")
            st.dataframe(df_resultados_view, use_container_width=True, hide_index=True)

            orden_ofertas = df_resultados["Oferta"].tolist()

            fig = px.bar(
                df_resultados,
                x="Oferta",
                y="Coste anual (€)",
                color="Tipo",
                #title="Coste anual por oferta (€)",
                text_auto=".0f",
                category_orders={"Oferta": orden_ofertas}
            )

            # qué barra quieres resaltar
            target = "simulado A"
            highlight = "#FF8C00"  # amarillo-anaranjado

            for trace in fig.data:
                # trace.x son las ofertas que caen en este trace (Tipo)
                trace.marker.color = [
                    (highlight if (isinstance(x, str) and target in x) else c)
                    for x, c in zip(
                        trace.x,
                        [trace.marker.color] * len(trace.x)  # color base del trace
                    )
                ]

            fig.update_layout(
                yaxis_title="Coste anual (€)",
                xaxis_title="",
                legend_title="",
                bargap=.4,
                title=dict(
                    text="Coste anual por oferta (€)",
                    x=0.5,
                    xanchor="center"
                )
            )
            fig.update_traces(
                textposition="inside",
                textfont_size=16  # ← ajusta aquí
            )



            st.plotly_chart(fig, use_container_width=True)


        #with c1:
        #    st.subheader("Perfil horario")    
        #    graf_medias_horarias = graficar_media_horaria('Total')
        #    st.plotly_chart(graf_medias_horarias, use_container_width=True)
        #    st.subheader("Consumo por periodos")
        #    graf_periodos, df_periodos=graficar_queso_periodos(st.session_state.df_norm_h)
        #    st.plotly_chart(graf_periodos, use_container_width=True)

    




