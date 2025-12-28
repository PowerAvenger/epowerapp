import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from scipy.optimize import minimize
import numpy as np
import plotly.express as px
from utilidades import generar_menu, init_app, init_app_index
from backend_opt2 import leer_curva_normalizada, calcular_costes, funcion_objetivo, ajustar_potencias, grafico_costes_con, graficar_costes_opt, calcular_optimizacion, pyc_tp, kp, tep, meses

if not st.session_state.get('usuario_autenticado', False):
    st.switch_page('epowerapp.py')

generar_menu()

if 'mantener_potencia' not in st.session_state:
    st.session_state.mantener_potencia = "Mantener" 

pot_con_ini = {
    'P1' : 50,
    'P2' : 50,
    'P3' : 50,
    'P4' : 50,
    'P5' : 50,
    'P6' : 110
}
df_pot_ini = pd.DataFrame(
    {
        "Periodo": pot_con_ini.keys(),
        "Potencia (kW)": pot_con_ini.values()
    }
).set_index("Periodo")

if "df_pot" not in st.session_state:
    st.session_state.df_pot = df_pot_ini
else:
    df_pot_ini = st.session_state.df_pot

st.sidebar.markdown("### Potencias contratadas")

df_pot_edit = st.sidebar.data_editor(
    df_pot_ini,
    use_container_width=True,
    num_rows="fixed",
)

st.session_state.df_pot = df_pot_edit


print('df_pot')
print(st.session_state.df_pot)

p6 = float(st.session_state.df_pot.loc["P6", "Potencia (kW)"])


st.sidebar.radio(
    "Selecciona potencia P6",
    ["Mantener", "No mantener"],
    horizontal=True,
    key='mantener_potencia'
)

    
if 'atr_dfnorm' not in st.session_state:
    st.session_state.atr_dfnorm = 'Ninguno'




if 'df_norm' not in st.session_state:
    st.session_state.df_norm = None
    st.sidebar.warning('Por favor introduce una curva de carga')
    submit = st.sidebar.button("🔄 Calcular optimización", type='primary', use_container_width=True, disabled=True)
else:
    #tarifa = st.session_state.atr_dfnorm
    st.sidebar.write(f'El peaje del suministro es {st.session_state.atr_dfnorm}')
    submit = st.sidebar.button("🔄 Calcular optimización", type='primary', use_container_width=True, disabled=False)
    
if submit and st.session_state.df_norm is not None:
    
    

    if p6 < 50 or st.session_state.atr_dfnorm == '2.0':
        st.warning('Suministro no válido para optimización por excesos', icon='⚠️')
        st.stop()

    graf_costes_potcon, fig2, coste_tp_potcon, coste_tp_potopt, ahorro_opt, ahorro_opt_porc, df_potencias, fig_ahorro, fig1, fig = calcular_optimizacion(p6)

    

    
    # INTERFAZ STREAMLIT++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    st.header('Resultados de la optimización', divider = 'rainbow')
    c1, c2, c3, c4 = st.columns([.5, .2, .1, .2])
    with c1:
        st.write(graf_costes_potcon)
    with c2:
        #st.write(graf_resumen_costes_tp)
        st.write(fig2)
    with c3:
        #st.plotly_chart(fig)
        st.metric('Coste ACTUAL (€)', f'{coste_tp_potcon:,.0f}'.replace(',','.'))
        st.metric('Coste OPTIMIZADO (€)', f'{coste_tp_potopt:,.0f}'.replace(',','.'))
        st.metric('AHORRO (€)', f'{ahorro_opt:,.0f}'.replace(',','.'), delta=f'{ahorro_opt_porc:,.1f}%')
    with c4:
        st.plotly_chart(fig)
    
    c11, c12, c13= st.columns([.25, .05, .7])
    with c11:
        st.subheader('Tabla de potencias')        
        st.dataframe(df_potencias, hide_index=True, use_container_width=True)
        st.write(fig_ahorro)
    with c13:
        st.write(fig1)

