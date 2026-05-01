import streamlit as st
import pandas as pd

from utilidades import generar_menu
from backend_opt2 import leer_curva_normalizada, pyc_tp, tepp, meses
from backend_opt2_rdl import calcular_optimizacion_rdl


if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')

generar_menu()

if 'mantener_potencia' not in st.session_state:
    st.session_state.mantener_potencia = "Mantener"

if 'mes_inicio_rdl' not in st.session_state:
    st.session_state.mes_inicio_rdl = 'may'

if 'p6_limite' not in st.session_state:
    st.session_state.p6_limite = 50

pot_con_ini = {
    'P1': 50,
    'P2': 50,
    'P3': 50,
    'P4': 50,
    'P5': 50,
    'P6': 110
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

MIN_P1 = 0.1
MIN_P6 = 50.01

def validar_potencias(df):
    errores = []
    if df.loc["P1", "Potencia (kW)"] < MIN_P1:
        errores.append("P1 debe ser ≥ 0,1 kW")
    if df.loc["P6", "Potencia (kW)"] < MIN_P6:
        errores.append("P6 debe ser ≥ 50,01 kW")

    potencias = df["Potencia (kW)"].values
    if not all(potencias[i] <= potencias[i+1] for i in range(len(potencias)-1)):
        errores.append("Debe cumplirse P1 ≤ P2 ≤ P3 ≤ P4 ≤ P5 ≤ P6")
    return errores

if st.sidebar.button('Cargar potencias contratadas', use_container_width=True, type='primary'):
    errores = validar_potencias(df_pot_edit)
    if errores:
        for e in errores:
            st.sidebar.error(e)
    else:
        st.session_state.df_pot = df_pot_edit
        st.sidebar.success("Potencias cargadas correctamente")

pot_con = st.session_state.df_pot["Potencia (kW)"].to_dict()
p6 = float(st.session_state.df_pot.loc["P6", "Potencia (kW)"])
p6_limite = None

st.sidebar.radio(
    "Selecciona potencia P6",
    ["Mantener", "No mantener", "Limitar"],
    horizontal=True,
    key='mantener_potencia'
)

if st.session_state.mantener_potencia == "Limitar":
    st.sidebar.number_input("Límite mínimo P6 (kW)", min_value=50, max_value=pot_con["P6"], step=1, key="p6_limite")

mes_default_idx = meses.index('may') if 'may' in meses else 0
if st.session_state.mes_inicio_rdl not in meses:
    st.session_state.mes_inicio_rdl = meses[mes_default_idx]

st.sidebar.selectbox(
    "Mes desde el que calcular el ahorro",
    meses,
    key="mes_inicio_rdl",
    index=mes_default_idx
)

if 'atr_dfnorm' not in st.session_state:
    st.session_state.atr_dfnorm = 'Ninguno'

if 'frec' not in st.session_state:
    st.session_state.frec = 'None'

fijar_P6 = st.session_state["mantener_potencia"] == "Mantener"

habilitar_opt = False

if 'df_norm' not in st.session_state or st.session_state.df_norm is None:
    st.sidebar.warning('Por favor introduce una curva de carga')
else:
    tarifa = st.session_state.atr_dfnorm
    if tarifa != '2.0':
        df_in = leer_curva_normalizada(pot_con)
        st.sidebar.write(f'El peaje del suministro es **:orange[{st.session_state.atr_dfnorm}]**')

        fecha_ini, fecha_fin = st.session_state.rango_curvadecarga
        dias_rango = (fecha_fin - fecha_ini).days + 1

        if st.session_state.frec == 'H':
            coef_excesos = 2
            st.sidebar.warning('Cálculo de excesos con curva HORARIA', icon='⚠️')
        else:
            coef_excesos = 1

        if dias_rango >= 1:
            habilitar_opt = True
            año_opt = 2026
            pyc_tp_opt = pyc_tp[año_opt][tarifa]
            tepp_opt = {k: v * coef_excesos for k, v in tepp[año_opt][tarifa].items()}
        else:
            st.sidebar.warning('No es posible optimizar con el rango actual.', icon='⚠️')
    else:
        st.sidebar.error('No es posible ejecutar ninguna acción. El peaje de acceso es 2.0TD', icon='⚠️')

submit_opt = st.sidebar.button(
    "🔄 Calcular optimización RDL",
    type='primary',
    use_container_width=True,
    disabled=not habilitar_opt
)

resultados = None

if submit_opt and st.session_state.df_norm is not None:
    if p6 < 50 or st.session_state.atr_dfnorm == '2.0':
        st.warning('Suministro no válido para optimización por excesos', icon='⚠️')
        st.stop()

    resultados = calcular_optimizacion_rdl(
        df_in=df_in,
        fijar_P6=fijar_P6,
        tarifa=tarifa,
        pot_con=pot_con,
        pyc_tp=pyc_tp_opt,
        tepp=tepp_opt,
        mes_inicio=st.session_state.mes_inicio_rdl,
        p6_limite=st.session_state.p6_limite if st.session_state.mantener_potencia == "Limitar" else None
    )

    st.session_state.resultados_potencia_rdl = resultados

elif "resultados_potencia_rdl" in st.session_state:
    resultados = st.session_state.resultados_potencia_rdl



if resultados is not None:

    orden_meses = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic']
    orden_meses_tabla = ["inicial"] + orden_meses

    df_final = resultados["df_final"].copy()
    #df_final["mes"] = pd.Categorical(df_final["mes"], categories=orden_meses, ordered=True)
    df_final["mes"] = pd.Categorical(df_final["mes"], categories=orden_meses_tabla, ordered=True)
    df_final = df_final.sort_values("mes").reset_index(drop=True)

    
    st.header('Resultados de la optimización RDL del Término de Potencia', divider='rainbow')

    c1, c2, c3 = st.columns([.5, .25, .25])
    with c1:
        st.plotly_chart(resultados["graf_costes_potcon"], use_container_width=True)
    with c2:
        st.plotly_chart(resultados["graf_resumen"], use_container_width=True)
    with c3:
        st.metric('Coste ACTUAL (€)', f'{resultados["coste_tp_potcon"]:,.2f}'.replace(',','X').replace('.',',').replace('X','.'))
        st.metric('Coste OPTIMIZADO (€)', f'{resultados["coste_tp_potopt"]:,.2f}'.replace(',','X').replace('.',',').replace('X','.'))
        st.metric('AHORRO (€)', f'{resultados["ahorro_opt"]:,.2f}'.replace(',','X').replace('.',',').replace('X','.'), delta=f'{resultados["ahorro_opt_porc"]:,.1f}%')

    #with st.expander("Fase 1 · Optimización total mes a mes", expanded=False):
    #    st.dataframe(resultados["df_fase1"], hide_index=True, use_container_width=True)

    c11, c12 = st.columns([.45, .55])
    with c11:
        st.subheader('Tabla comparativa mensual final (fase 2)')
        #st.dataframe(resultados["df_final"], hide_index=True, use_container_width=True)
        st.dataframe(df_final, hide_index=True, use_container_width=True)
        st.plotly_chart(resultados["graf_ahorro"], use_container_width=True)
    with c12:
        st.plotly_chart(resultados["graf_potencias"], use_container_width=True)
        st.plotly_chart(resultados["graf_ahorro_mensual"], use_container_width=True)
