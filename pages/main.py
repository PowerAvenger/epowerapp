import streamlit as st
from utilidades import generar_menu, init_app

from backend_comun import autenticar_google_sheets, carga_rapida_sheets, carga_total_sheets, colores_precios
from backend_telemindex import filtrar_datos, aplicar_margen, graf_principal, pt5_trans, pt1, pt7_trans, costes_indexado
from backend_simulindex import obtener_historicos_meff, obtener_meff_trimestral, obtener_grafico_meff, hist_mensual, graf_hist






init_app()
generar_menu()


zona_mensajes = st.sidebar.empty() 




df_filtrado, lista_meses = filtrar_datos()
try:
    fecha_ultima_filtrado = df_filtrado['fecha'].iloc[-1]
except:
    st.session_state.dia_seleccionado = '2025-01-01'
    df_filtrado, lista_meses = filtrar_datos()


# DASHBOARD
zona_grafica = st.empty()
with zona_grafica.container():

    c1, c2, c3 = st.columns(3)
    with c1:
        # grafico main telemindex
        st.subheader(f'Precios minoristas de indexado {st.session_state.dia_seleccionado}')
        st.plotly_chart(graf_principal(df_filtrado, colores_precios))



if 'df_sheets_full' not in st.session_state:
    zona_mensajes.warning('Cargados datos iniciales. Espera a que estén disponibles todos los datos', icon = '⚠️')
    st.session_state.df_sheets_full = carga_total_sheets()
    st.session_state.df_sheets = st.session_state.df_sheets_full
    zona_mensajes.success('Cargados todos los datos. Ya puedes consultar los históricos', icon = '👍')