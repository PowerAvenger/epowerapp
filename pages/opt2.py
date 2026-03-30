import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from utilidades import generar_menu
from backend_opt2 import (leer_curva_normalizada, calcular_costes, calcular_optimizacion, pyc_tp, tepp, meses)
from backend_curvadecarga import colores_periodo
from report_generator import generar_informe
from utils_docx import generar_docx_bytes, insertar_tabla

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

MIN_P1 = 0.1
MIN_P6 = 50.01
def validar_potencias(df):
    errores = []

    # mínimos
    if df.loc["P1", "Potencia (kW)"] < MIN_P1:
        errores.append("P1 debe ser ≥ 0,1 kW")

    if df.loc["P6", "Potencia (kW)"] < MIN_P6:
        errores.append("P6 debe ser ≥ 50,01 kW")

    # orden P1 ≤ P2 ≤ ... ≤ P6
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

if 'frec' not in st.session_state:
    st.session_state.frec = 'None'



habilitar_opt = False
habilitar_ver = False

if 'df_norm' not in st.session_state or st.session_state.df_norm is None:
    #st.session_state.df_norm = None
    st.sidebar.warning('Por favor introduce una curva de carga')
    habilitar_opt = False
    habilitar_ver = False
else:
    tarifa = st.session_state.atr_dfnorm
    if tarifa != '2.0':
        df_in = leer_curva_normalizada(pot_con)
        st.sidebar.write(f'El peaje del suministro es **:orange[{st.session_state.atr_dfnorm}]**')
        st.sidebar.info('Pincha en la opción activada')
        fecha_ini, fecha_fin = st.session_state.rango_curvadecarga
        dias_rango = (fecha_fin - fecha_ini).days + 1
        año_ver = fecha_ini.year

        const_verif = 31
        const_optim_inf = 320
        const_optim_sup = 366

        if st.session_state.frec =='H':
            coef_excesos = 2
            st.sidebar.warning('Cálculo de excesos con curva HORARIA', icon='⚠️')
        else:
            coef_excesos = 1

        # mes natural: se puede verificar
        if dias_rango <= const_verif:
            st.sidebar.info('Es posible verificar.')
            habilitar_opt = False
            habilitar_ver = True
            pyc_tp_ver = pyc_tp[año_ver][tarifa]
            tepp_ver = {
                k: v * coef_excesos
                for k, v in tepp[año_ver][tarifa].items()
            }
            
        # no hay días suficientes para optimizar
        elif (const_verif < dias_rango < const_optim_inf): #or (dias_rango > const_optim_sup):
            st.sidebar.warning('No es posible ejecutar ninguna acción.', icon='⚠️')
            habilitar_opt = False
            habilitar_ver = False

        # sobran días: se recorta a los últimos 365    
        elif dias_rango > const_optim_sup:
            st.sidebar.warning('Curva demasiado larga → se recortan los últimos 365 días', icon='⚠️')

            # 🔹 fecha de corte (365 días naturales)
            fecha_ini = fecha_fin - pd.Timedelta(days=364)

            # 🔹 filtrar por fechas completas (date vs date)
            df_in = df_in[
                (df_in["fecha"] >= fecha_ini) &
                (df_in["fecha"] <= fecha_fin)
            ]
            print('curva recortada')
            print(df_in)
            # 🔹 recalcular rango real
            fecha_ini = df_in["fecha"].min()
            fecha_fin = df_in["fecha"].max()
            dias_rango = (fecha_fin - fecha_ini).days + 1

            st.sidebar.info(f'Nuevo rango: {fecha_ini} → {fecha_fin}')
            st.sidebar.write("Días finales:", dias_rango)

            habilitar_opt = True
            habilitar_ver = False

            año_opt = 2026
            pyc_tp_opt = pyc_tp[año_opt][tarifa]
        
            tepp_opt = {
                k: v * coef_excesos
                for k, v in tepp[año_opt][tarifa].items()
            }
        else:
            # 365 días: se puede optimizar    
            st.sidebar.info('Es posible optimizar.')
            habilitar_opt = True
            habilitar_ver = False
            
            año_opt = 2026
            pyc_tp_opt = pyc_tp[año_opt][tarifa]
        
            tepp_opt = {
                k: v * coef_excesos
                for k, v in tepp[año_opt][tarifa].items()
            }
        
    else:
        st.sidebar.error('No es posible ejecutar ninguna acción. El peaje de acceso es 2.0TD', icon='⚠️')
        habilitar_opt = False
        habilitar_ver = False
        

submit_opt = st.sidebar.button("🔄 Calcular optimización", type='primary', use_container_width=True, disabled=not habilitar_opt)
submit_ver = st.sidebar.button("🔄 Realizar verificación", type='primary', use_container_width=True, disabled=not habilitar_ver)
    
    
resultados = None    

# OPTIMIZACIÓN DE POTENCIA. USADO EN MODO PREMIUM Y MODO DEMO.  
if submit_opt and st.session_state.df_norm is not None:
        
        if p6 < 50 or st.session_state.atr_dfnorm == '2.0':
            st.warning('Suministro no válido para optimización por excesos', icon='⚠️')
            st.stop()

        #graf_costes_potcon, graf_resumen, coste_tp_potcon, coste_tp_potopt, ahorro_opt, ahorro_opt_porc, df_potencias, graf_ahorro, graf_costes_pot_periodos, graf_pie_peso = calcular_optimizacion(df_in, fijar_P6, tarifa, pot_con, pyc_tp_opt, tepp_opt)
        
        resultados = calcular_optimizacion(
            df_in, fijar_P6, tarifa, pot_con, pyc_tp_opt, tepp_opt
        )

        st.session_state.resultados_potencia = resultados
        

# 🔹 si no recalcula → recupero
elif "resultados_potencia" in st.session_state:

    resultados = st.session_state.resultados_potencia


# 🔹 si hay resultados → muestro
if resultados is not None:
    graf_costes_potcon, graf_resumen, coste_tp_potcon, coste_tp_potopt, ahorro_opt, ahorro_opt_porc, df_potencias, graf_ahorro, graf_costes_pot_periodos, graf_pie_peso = resultados
        
    # INTERFAZ STREAMLIT++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

    tab1, tab2 = st.tabs(['Resultados', 'Informe'])
    with tab1:
        st.header('Resultados de la optimización del Término de Potencia para tipos 1, 2 y 3 (>50kW)', divider = 'rainbow')
        c1, c2, c3, c4 = st.columns([.5, .2, .1, .2])
        with c1:
            st.write(graf_costes_potcon)
        with c2:
            st.write(graf_resumen)
        with c3:
            st.metric('Coste ACTUAL (€)', f'{coste_tp_potcon:,.2f}'.replace(',','X').replace('.',',').replace('X','.'))
            st.metric('Coste OPTIMIZADO (€)', f'{coste_tp_potopt:,.2f}'.replace(',','X').replace('.',',').replace('X','.'))
            st.metric('AHORRO (€)', f'{ahorro_opt:,.2f}'.replace(',','X').replace('.',',').replace('X','.'), delta=f'{ahorro_opt_porc:,.1f}%')
        with c4:
            st.plotly_chart(graf_pie_peso)
        
        c11, c12, c13= st.columns([.25, .05, .7])
        with c11:
            st.subheader('Tabla de potencias')
            st.dataframe(df_potencias, hide_index=True, use_container_width=True)
            st.write(graf_ahorro)
        with c13:
            st.write(graf_costes_pot_periodos)

    with tab2:    
        st.subheader("📄 Generar informe")

        # Opciones que el usuario puede personalizar
        col_titulo, col_logo = st.columns([3, 1])
        with col_titulo:
            titulo    = st.text_input("Título del informe",    "Informe de Optimización de Potencias")
            subtitulo = st.text_input("Subtítulo (opcional)",  "Prueba de subtítulo")
            realizado_por = st.text_input("Realizado por", "")
            cliente       = st.text_input("Cliente", "")
            cups          = st.text_input("CUPS", "")
        with col_logo:
            logo_file = st.file_uploader("Logo (PNG/JPG)", type=["png", "jpg", "jpeg"])

        # Guarda el logo en un fichero temporal si el usuario lo sube
        logo_path = None
        if logo_file is not None:
            import tempfile, pathlib
            suffix = pathlib.Path(logo_file.name).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(logo_file.read())
                logo_path = tmp.name

        # Botón de generación
        if st.button("🚀 Generar informe", type="primary"):
            with st.spinner("Generando informe..."):
                try:
                    resultado = generar_informe(
                        graf_costes_potcon       = graf_costes_potcon,
                        graf_resumen             = graf_resumen,
                        coste_tp_potcon          = coste_tp_potcon,
                        coste_tp_potopt          = coste_tp_potopt,
                        ahorro_opt               = ahorro_opt,
                        ahorro_opt_porc          = ahorro_opt_porc,
                        df_potencias             = df_potencias,
                        graf_ahorro              = graf_ahorro,
                        graf_costes_pot_periodos = graf_costes_pot_periodos,
                        logo_path                = logo_path,
                        titulo                   = titulo,
                        subtitulo                = subtitulo,
                        cliente                = cliente,   
                        cups = cups,
                        realizado_por = realizado_por,
                        template_path            = "templates/informe.html",  # ajusta si es necesario
                    )

                    st.success("✅ Informe generado correctamente")

                    # ── Botones de descarga ───────────────────────────────────
                    col1, col2, col3 = st.columns(3)

                    #with col1:
                    #    st.download_button(
                    #        label        = "⬇️ Descargar PDF",
                    #        data         = resultado["pdf"],
                    #        file_name    = "informe_potencias.pdf",
                    #        mime         = "application/pdf",
                    #        use_container_width=True,
                    #    )
                    with col2:
                        st.download_button(
                            label        = "⬇️ Descargar Word",
                            data         = resultado["docx"],
                            file_name    = "informe_potencias.docx",
                            mime         = "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=True,
                        )
                    with col3:
                        st.download_button(
                            label        = "⬇️ Descargar HTML",
                            data         = resultado["html"].encode("utf-8"),
                            file_name    = "informe_potencias.html",
                            mime         = "text/html",
                            use_container_width=True,
                        )

                    # Vista previa en Streamlit (opcional)
                    with st.expander("👁️ Vista previa HTML"):
                        st.components.v1.html(resultado["html"], height=700, scrolling=True)

                except Exception as e:
                    st.error(f"Error al generar el informe: {e}")
                    raise  # elimina esta línea en producción

    

# VERIFICACIÓN DE EXCESOS. NO SE USA EN MODO DEMO
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
            c21,c22,c23 = st.columns(3)
            with c21:
                total_potfra = round(df_pot_mes['Total (€)'].sum(),2)
                st.metric('Potencia facturada €)', f"{total_potfra:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            with c22:
                st.metric('Excesos facturados €)', f"{coste_excesos_potcon:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            with c23:
                total_tp_fra = round(total_potfra+coste_excesos_potcon,2)
                st.metric('Total término de potencia €)', f"{total_tp_fra:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        with c2:
            st.plotly_chart(fig_detalle_demanda2, use_container_width=True)


