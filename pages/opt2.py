import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from scipy.optimize import minimize
import numpy as np
import plotly.express as px
from utilidades import generar_menu, init_app, init_app_index
from backend_opt2 import leer_curva_normalizada, calcular_costes, funcion_objetivo, ajustar_potencias, grafico_costes_con, graficar_costes_opt, calcular_optimizacion, pyc_tp, tepp, meses
from backend_curvadecarga import colores_periodo

if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
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

if st.sidebar.button('Cargar potencias contratadas', use_container_width=True, type='primary'):
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

#if st.session_state.get('usuario_free', True):
#    st.warning("🔒 Este módulo es solo para usuarios premium")
    #st.info("Puedes acceder al resto de módulos sin problema.")
#    st.stop()
    
if 'atr_dfnorm' not in st.session_state:
    st.session_state.atr_dfnorm = 'Ninguno'

pot_con = st.session_state.df_pot["Potencia (kW)"].to_dict()
fijar_P6 = st.session_state["mantener_potencia"] == "Mantener"

if 'freq' not in st.session_state:
    st.session_state.freq = 'None'


#tab1, tab2 =st.tabs(['Optimizar', 'Verificar'])

if 'df_norm' not in st.session_state:
    st.session_state.df_norm = None
    st.sidebar.warning('Por favor introduce una curva de carga')
#    with tab1:
    submit_opt = st.sidebar.button("🔄 Calcular optimización", type='primary', use_container_width=True, disabled=True)
#    with tab2:
    submit_ver = st.sidebar.button("🔄 Realizar verificación", type='primary', use_container_width=True, disabled=True)
else:
    tarifa = st.session_state.atr_dfnorm
    if st.session_state.freq =='15T':
        df_in = leer_curva_normalizada(pot_con)
        st.sidebar.write(f'El peaje del suministro es {st.session_state.atr_dfnorm}')
        st.sidebar.info('Pincha en la opción activada')
        fecha_ini, fecha_fin = st.session_state.rango_curvadecarga
        dias_rango = (fecha_fin - fecha_ini).days + 1
        año_ver = fecha_ini.year

        if dias_rango <= 31:
            st.sidebar.info('Es posible verificar.')
            submit_opt = st.sidebar.button("🔄 Calcular optimización", type='primary', use_container_width=True, disabled=True)
            submit_ver = st.sidebar.button("🔄 Realizar verificación", type='primary', use_container_width=True, disabled=False)
            pyc_tp_ver = pyc_tp[año_ver][tarifa]
            tepp_ver = tepp[año_ver][tarifa]

        if dias_rango in (365,366):
            st.sidebar.info('Es posible optimizar.')
            submit_opt = st.sidebar.button("🔄 Calcular optimización", type='primary', use_container_width=True, disabled=False)
            submit_ver = st.sidebar.button("🔄 Realizar verificación", type='primary', use_container_width=True, disabled=True)

    else:
        st.sidebar.warning('Curva de carga horaria. No es posible ejecutar ninguna acción')
        submit_opt = st.sidebar.button("🔄 Calcular optimización", type='primary', use_container_width=True, disabled=True)
        submit_ver = st.sidebar.button("🔄 Realizar verificación", type='primary', use_container_width=True, disabled=True)

    
    año_opt = 2026
    pyc_tp_opt = pyc_tp[año_opt][tarifa]
    tepp_opt = tepp[año_opt][tarifa]
    

#with tab1:    
if submit_opt and st.session_state.df_norm is not None:
        
        

        if p6 < 50 or st.session_state.atr_dfnorm == '2.0':
            st.warning('Suministro no válido para optimización por excesos', icon='⚠️')
            st.stop()

        graf_costes_potcon, fig2, coste_tp_potcon, coste_tp_potopt, ahorro_opt, ahorro_opt_porc, df_potencias, fig_ahorro, fig1, fig = calcular_optimizacion(df_in, fijar_P6, tarifa, pot_con, pyc_tp_opt, tepp_opt)

        

        
        # INTERFAZ STREAMLIT++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        st.header('Resultados de la optimización del Término de Potencia para tipos 1, 2 y 3 (>50kW)', divider = 'rainbow')
        c1, c2, c3, c4 = st.columns([.5, .2, .1, .2])
        with c1:
            st.write(graf_costes_potcon)
        with c2:
            #st.write(graf_resumen_costes_tp)
            st.write(fig2)
        with c3:
            #st.plotly_chart(fig)
            st.metric('Coste ACTUAL (€)', f'{coste_tp_potcon:,.2f}'.replace(',','X').replace('.',',').replace('X','.'))
            st.metric('Coste OPTIMIZADO (€)', f'{coste_tp_potopt:,.2f}'.replace(',','X').replace('.',',').replace('X','.'))
            st.metric('AHORRO (€)', f'{ahorro_opt:,.2f}'.replace(',','X').replace('.',',').replace('X','.'), delta=f'{ahorro_opt_porc:,.1f}%')
        with c4:
            st.plotly_chart(fig)
        
        c11, c12, c13= st.columns([.25, .05, .7])
        with c11:
            st.subheader('Tabla de potencias')        
            st.dataframe(df_potencias, hide_index=True, use_container_width=True)
            st.write(fig_ahorro)
        with c13:
            st.write(fig1)

#with tab2:
if submit_ver and st.session_state.df_norm is not None:
        coste_potfra_potcon, coste_excesos_potcon, coste_tp_potcon, df_coste_potfra_potcon, df_coste_excesos_potcon = calcular_costes(df_in, tarifa, pyc_tp_ver, tepp_ver, meses, pot_con)

        mes_verificado = df_in['mes_nom'].iloc[0]
        df_pot_mes = df_coste_potfra_potcon.loc[[mes_verificado]].copy()
        df_exc_mes = df_coste_excesos_potcon.loc[[mes_verificado]].copy()
        df_pot_mes['Total (€)'] = df_pot_mes.sum(axis=1)
        df_exc_mes['Total (€)'] = df_exc_mes.sum(axis=1)
        df_pot_mes.index = ['Potencia contratada']
        df_exc_mes.index = ['Excesos']


        df_coste = pd.concat([df_pot_mes, df_exc_mes])
        df_coste = df_coste.reset_index()
        df_coste = df_coste.rename(columns={'index': 'Tipo coste'})
        def formato_es(x):
            if pd.isna(x):
                return ''
            return f"{x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        
        cols_numericas = df_coste.select_dtypes(include='number').columns
        df_coste[cols_numericas] = df_coste[cols_numericas].applymap(formato_es)

        fecha_inicio = st.session_state.df_norm["fecha_hora"].min().strftime("%d.%m.%Y")
        fecha_final = st.session_state.df_norm["fecha_hora"].max().strftime("%d.%m.%Y")

        df_pie = pd.DataFrame({
            'Tipo coste': ['Potencia contratada', 'Excesos'],
            'Coste (€)': [
                df_coste_potfra_potcon.loc[mes_verificado].sum(),
                df_coste_excesos_potcon.loc[mes_verificado].sum()
            ]
        })
        fig_pie = px.pie(
            df_pie,
            names='Tipo coste',
            values='Coste (€)',
            title='Distribución del coste del término de potencia',
            hole=0.35  # donut elegante (opcional)
        )
        fig_pie.update_traces(
            textposition='inside',
            textinfo='percent+label',
            hovertemplate='%{label}<br>%{value:,.2f} €<extra></extra>'
        )



        orden_periodos = list(pot_con.keys())
        orden_periodos_presentes = [
            p for p in orden_periodos if p in df_in['periodo'].unique()
        ]

        fig_detalle_demanda = px.bar(
            df_in,
            x='fecha_hora',
            y='potencia',
            facet_col='periodo',
            facet_col_wrap=1,
            color='periodo',
            color_discrete_map=colores_periodo,
            category_orders={'periodo': orden_periodos_presentes},
            title='Demanda cuartohoraria vs Potencia contratada por periodo',
            height=250 * df_in['periodo'].nunique()
        )
        
        for i, periodo in enumerate(orden_periodos_presentes, start=1):
            df_p = df_in[df_in['periodo'] == periodo]

            fig_detalle_demanda.add_trace(
                go.Scatter(
                    x=df_p['fecha_hora'],
                    y=[pot_con[periodo]] * len(df_p),
                    mode='lines',
                    line=dict(
                        dash='dash',
                        width=2
                    ),
                    name=periodo,           # mismo nombre
                    legendgroup=periodo,     # mismo grupo → mismo color
                    showlegend=False
                ),
                row=i,
                col=1
            )
        
        fig_detalle_demanda2 = px.bar(
            df_in,
            x='fecha_hora',
            y='potencia',
            facet_col='periodo',
            facet_col_wrap=1,
            category_orders={'periodo': orden_periodos_presentes},
            title='Demanda cuartohoraria vs Potencia contratada por periodo',
            height=250 * len(orden_periodos_presentes)
        )
        for i, periodo in enumerate(orden_periodos_presentes, start=1):
            fig_detalle_demanda2.update_traces(
                marker_color=colores_periodo[periodo],
                row=i,
                col=1
            )
        import plotly.graph_objects as go

        for i, periodo in enumerate(orden_periodos_presentes, start=1):
            df_p = df_in[df_in['periodo'] == periodo]

            fig_detalle_demanda2.add_trace(
                go.Scatter(
                    x=df_p['fecha_hora'],
                    y=[pot_con[periodo]] * len(df_p),
                    mode='lines',
                    line=dict(
                        color=colores_periodo[periodo],
                        dash='dash',
                        width=2
                    ),
                    showlegend=False
                ),
                row=i,
                col=1
            )
        fig_detalle_demanda2.update_yaxes(title_text='kW')


        st.header('Resultados de la verificación', divider = 'rainbow')
        st.write(f'Datos del {fecha_inicio} al {fecha_final}')
        c1, c2 = st.columns([.3,.7])
        with c1:
            st.dataframe(df_coste, hide_index=True, use_container_width=True)
            st.plotly_chart(fig_pie, use_container_width=True)
        with c2:
            st.plotly_chart(fig_detalle_demanda2, use_container_width=True)


