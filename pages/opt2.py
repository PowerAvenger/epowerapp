import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from scipy.optimize import minimize
import numpy as np
import plotly.express as px
from utilidades import generar_menu, init_app, init_app_index
from backend_opt2 import leer_curva_normalizada, calcular_costes, funcion_objetivo, ajustar_potencias, grafico_costes_con, graficar_costes_opt, pyc_tp, kp, tep, meses

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
if "df_pot" not in st.session_state:
    st.session_state.df_pot = pd.DataFrame.from_dict(
        pot_con_ini,
        orient="index",
        columns=["Potencia (kW)"]
    )
    st.session_state.df_pot.index.name = "Periodo"
    #st.session_state.df_pot = df_pot


with st.sidebar.form("form_optimizacion"):
    st.sidebar.markdown("### Potencias contratadas")

    df_pot_edit = st.sidebar.data_editor(
        st.session_state.df_pot,
        use_container_width=True,
        num_rows="fixed"
    )
    st.session_state.df_pot = df_pot_edit

    p6 = float(st.session_state.df_pot.loc["P6", "Potencia (kW)"])

    st.sidebar.radio(
        "Selecciona potencia P6",
        ["Mantener", "No mantener"],
        horizontal=True,
        key='mantener_potencia'
    )
    submit = st.form_submit_button("🔄 Calcular optimización")
    
    #st.form_submit_button("🔄 Calcular optimización")




if 'df_norm' not in st.session_state:
    st.session_state.df_norm = None
    st.sidebar.warning('Por favor introduce una curva de carga')
else:
    tarifa = st.session_state.atr_dfnorm
    st.sidebar.write(f'El peaje del suministro es {st.session_state.atr_dfnorm}')
    
if submit and st.session_state.df_norm is not None:

    if p6 < 50 or st.session_state.atr_dfnorm == '2.0':
        st.warning('Suministro no válido para optimización por excesos', icon='⚠️')
        st.stop()

    #pot_con = df_pot_edit["Potencia (kW)"].to_dict()
    pot_con = st.session_state.df_pot["Potencia (kW)"].to_dict()
    fijar_P6 = st.session_state["mantener_potencia"] == "Mantener"
    #fijar_P6 = st.session_state["mantener_potencia"]
    print(f'fijar_P6 = {fijar_P6}')


    df_in = leer_curva_normalizada(pot_con)

    potencias_contratadas = list(pot_con.values())
    coste_potfra_potcon, coste_excesos_potcon, coste_tp_potcon, df_coste_potfra_potcon, df_coste_excesos_potcon = calcular_costes(potencias_contratadas, df_in, tarifa, pyc_tp, kp, tep, meses, pot_con)
    df_coste_potfra_potcon['coste_pot_mes'] = df_coste_potfra_potcon.sum(axis=1)
    totales_potfra_potcon = df_coste_potfra_potcon.sum()
    totales_potfra_potcon.name = 'total año'
    #df_coste_potfra_potcon = pd.concat([df_coste_potfra_potcon, totales_potfra_potcon.to_frame().T])
    
    df_coste_excesos_potcon['coste_excesos_mes'] = df_coste_excesos_potcon.sum(axis=1)
    totales_excesos_potcon = df_coste_excesos_potcon.sum()
    totales_excesos_potcon.name = 'total año'
    #df_coste_excesos_potcon = pd.concat([df_coste_excesos_potcon, totales_excesos_potcon.to_frame().T])
    
    df_coste_tp_mes = pd.concat([df_coste_potfra_potcon['coste_pot_mes'], df_coste_excesos_potcon['coste_excesos_mes']], axis=1)

    graf_costes_potcon= grafico_costes_con(df_coste_tp_mes)



    pot_inicial = list(pot_con.values())  # Valores iniciales de las potencias contratadas
    constraints = [{'type': 'ineq', 'fun': lambda x, i=i: x[i + 1] - x[i]} for i in range(len(pot_inicial) - 1)]
    # Si fijar_p6 es True, agregamos la restricción para que P6 sea igual a pot_con['P6']
    if fijar_P6:
        constraints.append({
            'type': 'eq',  # 'eq' para que la restricción sea igual (P6 debe ser igual a pot_con['P6'])
            'fun': lambda x: x[-1] - pot_con['P6']  # Asegura que la última potencia (P6) sea igual a la contratada
        })


    
    # Optimización
    resultado = minimize(
        funcion_objetivo,
        pot_inicial,  # Valores iniciales
        args=(df_in, tarifa, pyc_tp, kp, tep, meses, pot_con),  # Argumentos adicionales
        method='SLSQP',
        constraints=constraints,
        bounds=[(0, None)] * len(pot_inicial)  # Las potencias deben ser >= 0
    )

    pot_opt_ini = dict(zip(pot_con.keys(), resultado.x))
    coste_minimizado = resultado.fun

    print("Potencias óptimas:", pot_opt_ini)
    print("Coste minimizado:", coste_minimizado)
    print("¿Optimización exitosa?", resultado.success)
    print("Mensaje de optimización:", resultado.message)

    pot_opt = ajustar_potencias(pot_opt_ini, fijar_P6=fijar_P6, pot_con=pot_con)

    coste_potfra_potopt, coste_excesos_potopt, coste_tp_potopt, df_coste_potfra_potopt, df_coste_excesos_potopt = calcular_costes(list(pot_opt.values()), df_in, tarifa, pyc_tp, kp, tep, meses, pot_con)

    
    df_coste_potfra_potopt['coste_pot_mes_opt'] = df_coste_potfra_potopt.sum(axis=1)
    df_coste_excesos_potopt['coste_excesos_mes_opt'] = df_coste_excesos_potopt.sum(axis=1)
    totales_potfra_potopt = df_coste_potfra_potopt.sum()
    print(f'total coste potencia a facturar OPTIMIZADA: {totales_potfra_potopt}')
    totales_potfra_potopt.name = 'total año'
    #df_coste_potfra_potopt = pd.concat([df_coste_potfra_potopt, totales_potfra_potopt.to_frame().T])
    
    totales_excesos_potopt = df_coste_excesos_potopt.sum()
    totales_excesos_potopt.name = 'total año'
    #df_coste_excesos_potopt = pd.concat([df_coste_excesos_potopt, totales_excesos_potopt.to_frame().T])
    

    
    df_coste_tp_mes_opt = pd.concat([df_coste_potfra_potopt['coste_pot_mes_opt'], df_coste_excesos_potopt['coste_excesos_mes_opt']], axis=1)

    
    df_coste_tp_mes = pd.concat([df_coste_tp_mes, df_coste_tp_mes_opt,], axis=1)
    

    ahorro_opt = int(coste_tp_potcon - coste_tp_potopt)
    ahorro_opt_porc = ahorro_opt * 100 / coste_tp_potcon

    graf_costes_potcon = graficar_costes_opt(graf_costes_potcon, df_coste_tp_mes)

    

    df_potencias = pd.DataFrame({
        'Potencias (kW)': ['Contratadas', 'Optimizadas'],
        'P1': [pot_con['P1'], pot_opt['P1']],
        'P2': [pot_con['P2'], pot_opt['P2']],
        'P3': [pot_con['P3'], pot_opt['P3']],
        'P4': [pot_con['P4'], pot_opt['P4']],
        'P5': [pot_con['P5'], pot_opt['P5']],
        'P6': [pot_con['P6'], pot_opt['P6']],
        'Coste Total (€)': [int(coste_tp_potcon), int(coste_tp_potopt)]
    })

    pot_rangos = {}
    for periodo in pot_con.keys():
        min_pot = min(pot_con[periodo], pot_opt[periodo])
        max_pot = max(pot_con[periodo], pot_opt[periodo])
        intervalo = max(1, (max_pot - min_pot) // 10)
        #pot_rangos[periodo] = np.arange(min_pot, max_pot + intervalo, intervalo)
        # Crear el rango de potencias y añadir las potencias optimizadas y contratadas
        rango_potencias = np.arange(min_pot, max_pot, intervalo)
        
        # Asegurarnos de incluir las potencias optimizadas y contratadas en el rango
        pot_rangos[periodo] = np.unique(np.concatenate([rango_potencias, [pot_con[periodo], pot_opt[periodo]]]))
        # Verificar si la potencia máxima (contratada o optimizada) está en el rango y agregarla si no
        if pot_rangos[periodo][-1] != max_pot:
            pot_rangos[periodo] = np.append(pot_rangos[periodo], max_pot)
    
    data = []

    # Iteramos sobre cada periodo
    for periodo in pot_con.keys():
        rango_potencias = pot_rangos[periodo]  # Rango de potencias para este periodo
        
        for potencia in rango_potencias:
            # Calculamos los costes para esta potencia, solo optimizando este periodo
            potencias_actuales = pot_con.copy()
            potencias_actuales[periodo] = potencia  # Cambiamos solo la potencia de este periodo
            
            # Calculamos costes por mes, referenciados al periodo
            _, _, _, df_coste_pot_temp, df_aei_temp = calcular_costes(
                list(potencias_actuales.values()), df_in, tarifa, pyc_tp, kp, tep, meses, pot_con
            )
            
            # Sumamos los costes de todos los meses para este periodo específico
            coste_potencia_periodo = df_coste_pot_temp[periodo].sum()
            coste_excesos_periodo = df_aei_temp[periodo].sum()
            
            # Añadimos los datos al DataFrame para graficar
            data.append({
                "Periodo": periodo,
                "Potencia": potencia,
                "Coste Potencia": coste_potencia_periodo,
                "Coste Excesos": coste_excesos_periodo,
            })
    
    # Creamos un DataFrame con los datos referenciados al periodo
    df_plot = pd.DataFrame(data)

    # Gráfico de área apilado
    fig1 = px.area(
        df_plot,
        x="Potencia",
        y=["Coste Potencia", "Coste Excesos"],
        color="variable",  # Diferenciamos costes de potencia y excesos
        facet_col="Periodo",  # Facetas para cada periodo
        labels={
            "Potencia": "Potencia (kW)",
            "value": "Coste (€)",
            "variable": "Tipo de Coste"
        },
        title="Costes de Potencia y Excesos por Periodo"
    )

    fig1.update_layout(
        legend_title_text="Tipo de Coste",
        yaxis_title="Coste (€)",
        xaxis_title="Potencia (kW)",
        margin=dict(l=40, r=20, t=40, b=40),
        #width = 1600
        height = 600
    )

    data_graf_resumen_opt = {
        'coste del tp': ['contratado', 'optimizado'],
        'coste en €' : [coste_tp_potcon, coste_tp_potopt]
    }
    df_resumen_costes_tp = pd.DataFrame(data_graf_resumen_opt)
    df_resumen_costes_tp['coste en €'] = df_resumen_costes_tp['coste en €'].round(0)
    

    
    colores = {
        'contratado': 'blue',
        'optimizado': 'green'
    }

    
    graf_resumen_costes_tp = px.bar(
        df_resumen_costes_tp,
        x = 'coste del tp',
        y = 'coste en €',
        color = 'coste del tp',
        color_discrete_map = colores,
        text = 'coste en €',
        #width=500
        )
    
    fig2 = go.Figure()

    # 🔵 CONTRATADO – Potencia
    fig2.add_trace(
        go.Bar(
            x=["Contratado"],
            y=[coste_potfra_potcon],
            name="Potencia (Contratado)",
            marker_color="lightblue"
        )
    )

    # 🔵 CONTRATADO – Excesos
    fig2.add_trace(
        go.Bar(
            x=["Contratado"],
            y=[coste_excesos_potcon],
            name="Excesos (Contratado)",
            marker_color="blue"
        )
    )

    # 🟢 OPTIMIZADO – Potencia
    fig2.add_trace(
        go.Bar(
            x=["Optimizado"],
            y=[coste_potfra_potopt],
            name="Potencia (Optimizado)",
            marker_color="lightgreen"
        )
    )

    # 🟢 OPTIMIZADO – Excesos
    fig2.add_trace(
        go.Bar(
            x=["Optimizado"],
            y=[coste_excesos_potopt],
            name="Excesos (Optimizado)",
            marker_color="green"
        )
    )

    fig2.update_layout(
        barmode="stack",
        title="Resumen de costes: Contratado vs Optimizado",
        yaxis_title="Coste (€)",
        xaxis_title="Situación",
        legend_title_text="Tipo de coste",
        #height=600,
        margin=dict(t=60, b=40, l=40, r=40)
    )
    #coste_potfra_potcon, coste_excesos_potcon, coste_potfra_potopt, coste_excesos_potopt

    
    ahorro_opt = coste_tp_potcon - coste_tp_potopt
    ahorro_opt_porc = ahorro_opt * 100 / coste_tp_potcon
    

    
    colors = [
        "rgba(255, 0, 0, 0.6)",  # Red for low
        "rgba(255, 165, 0, 0.6)",  # Orange for medium
        "rgba(255, 255, 0, 0.6)",  # Yellow for average
        "rgba(144, 238, 144, 0.6)",  # Light green for good
        "rgba(154, 205, 50, 0.6)"  # Green for excellent
    ]

    colors = [
        "rgba(204, 255, 204, 0.6)",  # Very light green
        "rgba(144, 238, 144, 0.6)",  # Light green
        "rgba(34, 139, 34, 0.6)",    # Medium green
        "rgba(0, 128, 0, 0.6)",      # Dark green
        "rgba(0, 100, 0, 0.6)"       # Very dark green
    ]

    
    fig_ahorro = go.Figure(go.Indicator(
        mode = "gauge+number",  # Agregar número y delta
        value = ahorro_opt_porc,  # El valor del indicador
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "Ahorro Obtenido (%)", 'font': {'size': 30}},
        gauge = {
            'axis': {'range': [None, 50]},  # Rango de 0 a 100
            'bar': {'color': "green"},  # Color de la barra
            'bgcolor': "white",  # Fondo blanco
            'steps': [
                {'range': [0, 10], 'color': colors[0]},
                {'range': [10, 20], 'color': colors[1]},
                {'range': [20, 30], 'color': colors[2]},
                {'range': [30, 40], 'color': colors[3]},
                {'range': [40, 50], 'color': colors[4]},
            ],
            #'threshold': {
            #    'line': {'color': "red", 'width': 4},  # Línea roja para indicar el valor
            #    'thickness': 0.75,
            #    'value': value  # El valor que se indica en el gráfico
            #}
        }
    ))

    fig_ahorro.update_traces(number_suffix='%', selector=dict(type='indicator'))

    fig = go.Figure()
    # 🔵 Anillo interior: situación actual
    fig.add_trace(
        go.Pie(
            labels=["Potencia", "Excesos"],
            values=[
                coste_potfra_potcon, 
                coste_excesos_potcon,
                
            ],
            hole=0.6,
            name="Actual",
            marker_colors=["deepskyblue", "blue"],
            domain={"x": [0, 1], "y": [0, 1]},
            textinfo="label+percent",
            textposition="inside"
        )
    )

    # 🟢 Anillo exterior: optimizado
    fig.add_trace(
        go.Pie(
            labels=["Potencia", "Excesos"],
            values=[
                coste_potfra_potopt, 
                coste_excesos_potopt,
            ],
            hole=0.8,
            name="Optimizado",
            marker_colors=["lightgreen", "green"],
            domain={"x": [0, 1], "y": [0, 1]},
            textinfo="label+percent",
            textposition="outside"
        )
    )
    fig.update_layout(
        title="Distribución de costes: Actual vs Optimizado",
        annotations=[
            dict(
                text="Costes<br>Anuales",
                x=0.5,
                y=0.5,
                font_size=14,
                showarrow=False
            )
        ],
        legend_title_text="Tipo de coste",
        margin=dict(t=60, b=40, l=40, r=40)
    )

    
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

