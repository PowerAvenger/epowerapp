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

st.sidebar.radio(
    "Selecciona potencia P6",
    ["Mantener", "No mantener"],
    horizontal=True,
    key='mantener_potencia'
)

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

        const_optim_inf = 320
        const_optim_sup = 366

        if st.session_state.frec == 'H':
            coef_excesos = 2
            st.sidebar.warning('Cálculo de excesos con curva HORARIA', icon='⚠️')
        else:
            coef_excesos = 1

        if const_optim_inf <= dias_rango <= const_optim_sup:
            st.sidebar.info('Es posible optimizar en modo RDL.')
            habilitar_opt = True
            año_opt = 2026
            pyc_tp_opt = pyc_tp[año_opt][tarifa]
            tepp_opt = {k: v * coef_excesos for k, v in tepp[año_opt][tarifa].items()}

        elif dias_rango > const_optim_sup:
            st.sidebar.warning('Curva demasiado larga → se recortan los últimos 365 días', icon='⚠️')

            fecha_ini = fecha_fin - pd.Timedelta(days=364)
            df_in = df_in[
                (df_in["fecha_hora"].dt.date >= fecha_ini) &
                (df_in["fecha_hora"].dt.date <= fecha_fin)
            ].copy()

            fecha_ini_real = df_in["fecha_hora"].min().date()
            fecha_fin_real = df_in["fecha_hora"].max().date()
            dias_rango_real = (fecha_fin_real - fecha_ini_real).days + 1

            st.sidebar.info(f'Nuevo rango: {fecha_ini_real} → {fecha_fin_real}')
            st.sidebar.write("Días finales:", dias_rango_real)

            habilitar_opt = True
            año_opt = 2026
            pyc_tp_opt = pyc_tp[año_opt][tarifa]
            tepp_opt = {k: v * coef_excesos for k, v in tepp[año_opt][tarifa].items()}
        else:
            st.sidebar.warning('No es posible optimizar: se necesita aprox. un año de curva.', icon='⚠️')
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
        mes_inicio=st.session_state.mes_inicio_rdl
    )

    st.session_state.resultados_potencia_rdl = resultados

elif "resultados_potencia_rdl" in st.session_state:
    resultados = st.session_state.resultados_potencia_rdl

if resultados is not None:
    (
        graf_costes_potcon,
        graf_resumen,
        coste_tp_potcon,
        coste_tp_potopt,
        ahorro_opt,
        ahorro_opt_porc,
        df_detalle_mostrar,
        graf_ahorro,
        graf_potencias,
        graf_ahorro_mensual,
        df_coste_tp_mes
    ) = resultados

    st.header('Resultados de la optimización RDL del Término de Potencia', divider='rainbow')

    c1, c2, c3 = st.columns([.5, .25, .25])
    with c1:
        st.plotly_chart(graf_costes_potcon, use_container_width=True)
    with c2:
        st.plotly_chart(graf_resumen, use_container_width=True)
    with c3:
        st.metric('Coste ACTUAL (€)', f'{coste_tp_potcon:,.2f}'.replace(',','X').replace('.',',').replace('X','.'))
        st.metric('Coste OPTIMIZADO (€)', f'{coste_tp_potopt:,.2f}'.replace(',','X').replace('.',',').replace('X','.'))
        st.metric('AHORRO (€)', f'{ahorro_opt:,.2f}'.replace(',','X').replace('.',',').replace('X','.'), delta=f'{ahorro_opt_porc:,.1f}%')

    c11, c12 = st.columns([.45, .55])
    with c11:
        st.subheader('Tabla comparativa mensual')
        st.dataframe(df_detalle_mostrar, hide_index=True, use_container_width=True)
        st.plotly_chart(graf_ahorro, use_container_width=True)
    with c12:
        st.plotly_chart(graf_potencias, use_container_width=True)
        st.plotly_chart(graf_ahorro_mensual, use_container_width=True)
