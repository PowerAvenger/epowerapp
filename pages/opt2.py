import hashlib
import math
import pathlib
import tempfile

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from utilidades import generar_menu
from backend_opt2 import (leer_curva_normalizada, calcular_costes, calcular_optimizacion, pyc_tp, tepp45, tepp123, meses, normalizar_tabla_maximetros)
from backend_curvadecarga import colores_periodo
from backend_comun import aplicar_estilo
from report_generator import preparar_informe, generar_formato_informe
from utils_docx import generar_docx_bytes, insertar_tabla
from formato_es import formato_euros, formato_numero_es


if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')

generar_menu()



if 'mantener_potencia' not in st.session_state:
    st.session_state.mantener_potencia = "Mantener" 
if 'forzar_maximetros' not in st.session_state:
    st.session_state.forzar_maximetros = False

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
#MIN_P6 = 50.01
MIN_P6 = 0.1
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
# modo1 = True  -> tipos 4/5: maxímetros
# modo1 = False -> tipos 1/2/3: curva de carga
modo1 = p6 <= 50

if st.session_state.forzar_maximetros:
    modo1 =p6

st.sidebar.radio(
    "Selecciona potencia P6",
    ["Mantener", "No mantener"],
    horizontal=True,
    key='mantener_potencia'
)

if 'atr_dfnorm' not in st.session_state:
    st.session_state.atr_dfnorm = 'Ninguno'

pot_con = st.session_state.df_pot["Potencia (kW)"].to_dict()
orden_periodos = [f'P{i}' for i in range(1, 7)]
fijar_P6 = st.session_state["mantener_potencia"] == "Mantener"

if 'frec' not in st.session_state:
    st.session_state.frec = 'None'



habilitar_opt = False
habilitar_ver = False
tarifa = st.session_state.atr_dfnorm



#if modo1 and tarifa == "Ninguno":
if modo1 and tarifa:
    tarifa = st.sidebar.selectbox(
        "Peaje de acceso",
        ["2.0", "3.0", "6.1", "6.2", "6.3", "6.4"],
        index=1,
        key="tarifa_maximetros"
    )

if p6>50:
        
    st.sidebar.checkbox(
        "Forzar optimización por maxímetro aunque P6 > 50 kW",
        value=False,
        help="Activa esta opción si quieres aplicar el método de maxímetro incluso en suministros con P6 superior a 50 kW.",
        key='forzar_maximetros'
    )    

if modo1:
    # P6 <= 50 → maxímetros

    st.sidebar.write(f'El peaje del suministro es **:orange[{tarifa}]**')
    st.sidebar.info('Modo P6 ≤ 50: optimización mediante maxímetros')
    if st.session_state.forzar_maximetros:
        st.sidebar.warning('¡¡Estás optimizando mediante maxímetros con P6 >50kW!!')

    archivo_max = st.sidebar.file_uploader(
        "Sube tabla de maxímetros",
        type=["xlsx"],
        key="upload_maximetros"
    )

    if archivo_max is not None:
        try:
            df_maximetros_raw = pd.read_excel(archivo_max)

            df_maximetros = normalizar_tabla_maximetros(
                df_maximetros_raw,
                meses
            )

            st.session_state.df_maximetros = df_maximetros
            st.sidebar.success("Tabla de maxímetros cargada correctamente")

        except Exception as e:
            st.sidebar.error(f"Error en tabla de maxímetros: {e}")
            habilitar_opt = False
            habilitar_ver = False

    if 'df_maximetros' not in st.session_state or st.session_state.df_maximetros is None:
        st.sidebar.warning('Por favor introduce una tabla de maxímetros')
        habilitar_opt = False
        habilitar_ver = False

    else:
        df_in = st.session_state.df_maximetros.copy()

        año_opt = 2026
        pyc_tp_opt = pyc_tp[año_opt][tarifa]

        tepp_opt = {
            k: v if v is not None else None
            for k, v in tepp45[año_opt][tarifa].items()
        }

        meses_maximetros = len(df_in)
        st.sidebar.caption('Costes regulados aplicados: 2026')
        if meses_maximetros < 12:
            st.sidebar.warning(
                f'Optimización basada en {meses_maximetros} mes(es) de '
                'maxímetros. El resultado puede no representar la '
                'estacionalidad anual.',
                icon='⚠️'
            )
        elif meses_maximetros == 12:
            st.sidebar.success('Periodo recomendado: 12 meses analizados.')
        else:
            st.sidebar.info(
                f'Optimización basada en {meses_maximetros} meses.'
            )

        habilitar_opt = True
        habilitar_ver = False

else:
    if 'df_norm' not in st.session_state or st.session_state.df_norm is None:
        #st.session_state.df_norm = None
        st.sidebar.warning('Por favor introduce una curva de carga')
        habilitar_opt = False
        habilitar_ver = False
    else:
        #tarifa = st.session_state.atr_dfnorm
        if tarifa != '2.0':
            df_in = leer_curva_normalizada(pot_con)
            st.sidebar.write(f'El peaje del suministro es **:orange[{st.session_state.atr_dfnorm}]**')
            st.sidebar.info('Pincha en la opción activada')
            fecha_ini, fecha_fin = st.session_state.rango_curvadecarga
            dias_rango = (fecha_fin - fecha_ini).days + 1
            año_ver = fecha_ini.year

            const_verif = 31

            if st.session_state.frec =='H':
                coef_excesos = 2
                st.sidebar.warning('Cálculo de excesos con curva HORARIA', icon='⚠️')
            else:
                coef_excesos = 1

            fechas_opt = pd.to_datetime(
                df_in['fecha_hora'], errors='coerce'
            ).dropna()
            periodos_analizados = fechas_opt.dt.to_period('M').nunique()
            cobertura_mensual = (
                pd.DataFrame({'fecha': fechas_opt})
                .assign(
                    periodo_mes=lambda x: x['fecha'].dt.to_period('M'),
                    dia=lambda x: x['fecha'].dt.date,
                    dias_mes=lambda x: x['fecha'].dt.days_in_month
                )
                .groupby('periodo_mes')
                .agg(dias_observados=('dia', 'nunique'), dias_mes=('dias_mes', 'first'))
            )
            meses_incompletos = cobertura_mensual[
                cobertura_mensual['dias_observados'] < cobertura_mensual['dias_mes']
            ]
            st.sidebar.caption('Costes regulados aplicados: 2026')
            if periodos_analizados < 12:
                st.sidebar.warning(
                    f'Optimización basada en {periodos_analizados} mes(es). '
                    'El resultado puede no representar la estacionalidad anual.',
                    icon='⚠️'
                )
            elif periodos_analizados == 12:
                st.sidebar.success('Periodo recomendado: 12 meses analizados.')
            else:
                st.sidebar.info(
                    f'Optimización basada en {periodos_analizados} meses.'
                )
            if not meses_incompletos.empty:
                etiquetas_incompletas = ', '.join(
                    str(periodo) for periodo in meses_incompletos.index
                )
                st.sidebar.warning(
                    'Meses parciales (coste de potencia prorrateado por días): '
                    f'{etiquetas_incompletas}.',
                    icon='⚠️'
                )

            año_opt = 2026
            pyc_tp_opt = pyc_tp[año_opt][tarifa]
            tepp_opt = {
                k: v * coef_excesos
                for k, v in tepp123[año_opt][tarifa].items()
            }
            habilitar_opt = True

            # Un mes natural también se puede verificar.
            if dias_rango <= const_verif:
                st.sidebar.info('Es posible verificar.')
                habilitar_ver = True
                pyc_tp_ver = pyc_tp[año_ver][tarifa]
                tepp_ver = {
                    k: v * coef_excesos
                    for k, v in tepp123[año_ver][tarifa].items()
                }
            else:
                st.sidebar.info('Es posible optimizar.')
                habilitar_ver = False
            
        else:
            st.sidebar.error('No es posible ejecutar ninguna acción. El peaje de acceso es 2.0TD', icon='⚠️')
            habilitar_opt = False
            habilitar_ver = False
        

submit_opt = st.sidebar.button("🔄 Calcular optimización", type='primary', use_container_width=True, disabled=not habilitar_opt)
submit_ver = st.sidebar.button("🔄 Realizar verificación", type='primary', use_container_width=True, disabled=not habilitar_ver)

tab_optimizacion, tab_verificacion, tab_comparacion, tab_informe = st.tabs(
    ['Optimización', 'Verificación', 'Comparar potencias', 'Informe']
)

resultados = None    

# OPTIMIZACIÓN DE POTENCIA. USADO EN MODO PREMIUM Y MODO DEMO.  
#if submit_opt and st.session_state.df_norm is not None:
#    if p6 < 50 or st.session_state.atr_dfnorm == '2.0':
#        st.warning('Suministro no válido para optimización por excesos', icon='⚠️')
#        st.stop()

#    resultados = calcular_optimizacion(df_in, fijar_P6, tarifa, pot_con, pyc_tp_opt, tepp_opt)
#    st.session_state.resultados_potencia = resultados
# si no recalcula → recupero

# OPTIMIZACIÓN DE POTENCIA. USADO EN MODO PREMIUM Y MODO DEMO.  
if submit_opt:

    # Seguridad: si por lo que sea no hay tarifa válida
    if tarifa == 'Ninguno':
        st.warning('Selecciona/carga el peaje del suministro antes de optimizar', icon='⚠️')
        st.stop()

    # MODO 1: P6 <= 50 → maxímetros
    if modo1:
        if 'df_maximetros' not in st.session_state or st.session_state.df_maximetros is None:
            st.warning('Falta la tabla de maxímetros para optimizar', icon='⚠️')
            st.stop()

    # MODO 2: P6 > 50 → curva de carga
    else:
        if 'df_norm' not in st.session_state or st.session_state.df_norm is None:
            st.warning('Falta la curva de carga para optimizar', icon='⚠️')
            st.stop()

    resultados = calcular_optimizacion(
        df_in,
        fijar_P6,
        tarifa,
        pot_con,
        pyc_tp_opt,
        tepp_opt
    )

    st.session_state.resultados_potencia = resultados


elif "resultados_potencia" in st.session_state:
    resultados = st.session_state.resultados_potencia


# 🔹 si hay resultados → muestro
if resultados is not None:
    df_coste_tp_mes, coste_tp_potcon, coste_tp_potopt, ahorro_opt, ahorro_opt_porc, df_potencias, graf_costes_pot_periodos, graf_pie_peso, coste_potfra_potcon, coste_excesos_potcon, coste_potfra_potopt, coste_excesos_potopt = resultados
    df_potencias = df_potencias.copy()
    def potencia_sin_decimales(valor):
        if isinstance(valor, str):
            valor = valor.replace(".", "").replace(",", ".")
        return formato_numero_es(float(valor), 0)

    for columna in ("P1", "P2", "P3", "P4", "P5", "P6"):
        if columna not in df_potencias:
            continue
        df_potencias[columna] = df_potencias[columna].apply(
            potencia_sin_decimales
        )

    from backend_opt2 import graficar_comparacion_mensual, graficar_gauge_ahorro, graficar_resumen
    graf_costes_potcon = graficar_comparacion_mensual(df_coste_tp_mes)
    graf_ahorro = graficar_gauge_ahorro(ahorro_opt, ahorro_opt_porc)
    graf_resumen = graficar_resumen (coste_potfra_potcon, coste_excesos_potcon, coste_potfra_potopt, coste_excesos_potopt)
    def formatear_tabla_costes_tp_mes(df_coste_tp_mes):
                df = df_coste_tp_mes.copy()

                # Transponer
                df = df.T

                # Renombrar filas
                nombres_filas = {
                    "coste_pot_mes": "Potencia a facturar",
                    "coste_excesos_mes": "Excesos a facturar",
                    "coste_pot_mes_opt": "Potencia optimizada",
                    "coste_excesos_mes_opt": "Excesos optimizados",
                }

                df = df.rename(index=nombres_filas)

                # Formato español: 3.038,49 €
                df_fmt = df.applymap(formato_euros)

                return df_fmt
    df_coste_tp_mes_fmt = formatear_tabla_costes_tp_mes(df_coste_tp_mes)
    if modo1:
        periodo_datos_informe = "Tabla de maxímetros"
        detalle_datos_optimizacion = (
            f"ATR/Peaje: **{tarifa}** · Datos utilizados: **tabla de maxímetros** "
            "· Costes regulados: **2026**"
        )
    else:
        columna_fecha = (
            "fecha_hora" if "fecha_hora" in df_in.columns else "fecha"
        )
        fechas_usadas = pd.to_datetime(
            df_in[columna_fecha], errors="coerce"
        ).dropna()
        if fechas_usadas.empty:
            rango_usado = "no disponible"
        else:
            rango_usado = (
                f"{fechas_usadas.min():%d/%m/%Y} – "
                f"{fechas_usadas.max():%d/%m/%Y}"
            )
        detalle_datos_optimizacion = (
            f"ATR/Peaje: **{tarifa}** · Curva utilizada: **{rango_usado}** "
            "· Costes regulados: **2026**"
        )
        periodo_datos_informe = rango_usado

    # ===============================================================================================================================    
    # INTERFAZ STREAMLIT
    # ===============================================================================================================================    

    with tab_optimizacion:
        
        
        c11, c12= st.columns([.55, .45])
        with c11:
            if modo1:
                st.header('Resultados de la optimización del Término de Potencia para tipos 4 y 5 (=<50kW)', divider = 'rainbow')
            else:
                st.header('Resultados de la optimización del Término de Potencia para tipos 1, 2 y 3 (>50kW)', divider = 'rainbow')
            st.markdown(detalle_datos_optimizacion)
            with st.container(border=True):
                c1, c2, c3 = st.columns([0.25, 0.20, 0.10])
                with c1:
                    st.write("")
                    st.write(graf_ahorro)
                    st.write("") 
                    st.write("")
                    st.subheader('Tabla de potencias y costes Tp')
                    st.dataframe(df_potencias, hide_index=True, use_container_width=True)
                with c2:
                    st.write(graf_resumen)
                with c3:
                    st.metric('Coste PREVISTO (€)', formato_euros(coste_tp_potcon))
                    st.metric('Coste OPTIMIZADO (€)', formato_euros(coste_tp_potopt))
                    st.metric(
                        'AHORRO (€)',
                        formato_euros(ahorro_opt),
                        delta=f'{formato_numero_es(ahorro_opt_porc, 1)} %',
                    )
            st.header('Detalle de optimización por periodos', divider = 'rainbow')  
            with st.container(border=True):
                st.plotly_chart(graf_costes_pot_periodos, use_container_width=True)
        with c12:
            st.header('Detalle de costes mensuales (€)', divider = 'rainbow')
            with st.container(border=True):
                st.write(graf_costes_potcon)
                st.subheader('Tabla mensual de detalle de costes')
                st.dataframe(df_coste_tp_mes_fmt, use_container_width=True)
        
        #c11, c12= st.columns([.55, .45])
        #with c11:
            
        #with c12:
            

    with tab_informe:
        st.subheader("📄 Generar informe")
        st.selectbox(
            'Tipo de informe disponible',
            ['Informe de optimización'],
            disabled=True,
            help=(
                'La verificación ya dispone de una pestaña y estado propios. '
                'Su plantilla documental se incorporará cuando se defina su contenido.'
            )
        )

        # Opciones que el usuario puede personalizar
        col_titulo, col_logo = st.columns([2, 2])
        with col_titulo:
            titulo    = st.text_input("Título del informe",    "Informe de Optimización de Potencias")
            subtitulo = st.text_input("Subtítulo (opcional)",  "Prueba de subtítulo")
            realizado_por = st.text_input("Realizado por", "")
            cliente       = st.text_input("Cliente", "")
            cups          = st.text_input("CUPS", "")
        #with col_logo:
            logo_file = st.file_uploader("Logo (PNG/JPG)", type=["png", "jpg", "jpeg"])

        logo_bytes = logo_file.getvalue() if logo_file is not None else b""
        firma = hashlib.sha256()
        firma.update(b"informe-potencia-v2")
        firma.update(
            repr((
                coste_tp_potcon,
                coste_tp_potopt,
                ahorro_opt,
                ahorro_opt_porc,
                titulo,
                subtitulo,
                realizado_por,
                cliente,
                cups,
                tarifa,
                periodo_datos_informe,
            )).encode("utf-8")
        )
        firma.update(
            pd.util.hash_pandas_object(
                df_potencias, index=True
            ).values.tobytes()
        )
        firma.update(logo_bytes)
        firma_informe = firma.hexdigest()

        if st.button("🚀 Preparar informe", type="primary"):
            with st.spinner("Preparando vista previa y gráficos..."):
                logo_path = None
                try:
                    if logo_file is not None:
                        suffix = pathlib.Path(logo_file.name).suffix
                        with tempfile.NamedTemporaryFile(
                            delete=False, suffix=suffix
                        ) as tmp:
                            tmp.write(logo_bytes)
                            logo_path = tmp.name
                    preparado = preparar_informe(
                        graf_costes_potcon=graf_costes_potcon,
                        graf_resumen=graf_resumen,
                        coste_tp_potcon=coste_tp_potcon,
                        coste_tp_potopt=coste_tp_potopt,
                        ahorro_opt=ahorro_opt,
                        ahorro_opt_porc=ahorro_opt_porc,
                        df_potencias=df_potencias,
                        graf_ahorro=graf_ahorro,
                        graf_costes_pot_periodos=graf_costes_pot_periodos,
                        logo_path=logo_path,
                        titulo=titulo,
                        subtitulo=subtitulo,
                        cliente=cliente,
                        cups=cups,
                        peaje=tarifa,
                        periodo_datos=periodo_datos_informe,
                        realizado_por=realizado_por,
                        template_path="templates/informe.html",
                    )
                    st.session_state["opt2_informe_preparado"] = {
                        "firma": firma_informe,
                        "preparado": preparado,
                        "formatos": {"html": preparado["html"]},
                    }
                except Exception as e:
                    st.error(f"Error al preparar el informe: {e}")
                finally:
                    if logo_path:
                        pathlib.Path(logo_path).unlink(missing_ok=True)

        informe_sesion = st.session_state.get("opt2_informe_preparado")
        informe_vigente = (
            informe_sesion
            if informe_sesion
            and informe_sesion.get("firma") == firma_informe
            else None
        )
        if informe_sesion and informe_vigente is None:
            st.info(
                "Los datos han cambiado. Prepara de nuevo el informe para "
                "actualizarlo."
            )

        if informe_vigente:
            st.success("✅ Informe preparado y conservado durante esta sesión")
            formatos = informe_vigente["formatos"]
            col1, col2, col3 = st.columns(3)
            with col1:
                if "pdf" not in formatos and st.button(
                    "Generar PDF", use_container_width=True
                ):
                    with st.spinner("Generando PDF..."):
                        formatos["pdf"] = generar_formato_informe(
                            informe_vigente["preparado"], "pdf"
                        )
                if "pdf" in formatos:
                    st.download_button(
                        "⬇️ Descargar PDF",
                        formatos["pdf"],
                        "informe_potencias.pdf",
                        "application/pdf",
                        use_container_width=True,
                    )
            with col2:
                if "docx" not in formatos and st.button(
                    "Generar Word", use_container_width=True
                ):
                    with st.spinner("Generando Word..."):
                        formatos["docx"] = generar_formato_informe(
                            informe_vigente["preparado"], "docx"
                        )
                if "docx" in formatos:
                    st.download_button(
                        "⬇️ Descargar Word",
                        formatos["docx"],
                        "informe_potencias.docx",
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document",
                        use_container_width=True,
                    )
            with col3:
                st.download_button(
                    "⬇️ Descargar HTML",
                    formatos["html"].encode("utf-8"),
                    "informe_potencias.html",
                    "text/html",
                    use_container_width=True,
                )

            with st.expander("👁️ Vista previa HTML"):
                st.components.v1.html(
                    formatos["html"], height=700, scrolling=True
                )


if resultados is None:
    with tab_optimizacion:
        st.info('Calcula una optimización para mostrar sus resultados.')
    with tab_informe:
        st.info(
            'El informe de optimización estará disponible después de realizar '
            'el cálculo.'
        )

# VERIFICACIÓN DE EXCESOS. NO SE USA EN MODO DEMO
if submit_ver and st.session_state.df_norm is not None:
        coste_potfra_potcon, coste_excesos_potcon, coste_tp_potcon, df_coste_potfra_potcon, df_coste_excesos_potcon = calcular_costes(df_in, tarifa, pyc_tp_ver, tepp_ver, meses, pot_con)

        mes_verificado = df_coste_potfra_potcon.index[0]
        df_pot_mes = df_coste_potfra_potcon.loc[[mes_verificado]].copy()
        df_exc_mes = df_coste_excesos_potcon.loc[[mes_verificado]].copy()
        df_pot_mes['Total (€)'] = df_pot_mes.sum(axis=1)
        df_exc_mes['Total (€)'] = df_exc_mes.sum(axis=1)
        df_pot_mes.index = ['Potencia contratada']
        df_exc_mes.index = ['Excesos']


        df_coste = pd.concat([df_pot_mes, df_exc_mes])
        df_coste = df_coste.reset_index()
        df_coste = df_coste.rename(columns={'index': 'Tipo coste'})
        cols_numericas = df_coste.select_dtypes(include='number').columns
        df_coste[cols_numericas] = df_coste[cols_numericas].applymap(
            lambda valor: formato_numero_es(valor, 2)
        )

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



        orden_periodos = [f'P{i}' for i in range(1, 7)]
        periodos_presentes = set(df_in['periodo'].dropna().unique())
        orden_visual = [p for p in orden_periodos if p in periodos_presentes]

        fig_detalle_demanda = make_subplots(
            rows=len(orden_visual),
            cols=1,
            shared_xaxes=True,
            subplot_titles=orden_visual,
            vertical_spacing=0.07
        )

        fecha_min = df_in['fecha_hora'].min()
        fecha_max = df_in['fecha_hora'].max()
        demanda_max_global = pd.to_numeric(
            df_in['potencia'], errors='coerce'
        ).max()
        potencia_contratada_max = max(
            float(pot_con[p]) for p in orden_visual
        )
        valor_max_global = max(
            float(demanda_max_global) if pd.notna(demanda_max_global) else 0,
            potencia_contratada_max
        )
        paso_eje = 500
        ultimo_tick = max(
            paso_eje,
            math.ceil(valor_max_global * 1.05 / paso_eje) * paso_eje
        )
        # El margen coloca el último tick dentro del área del gráfico para
        # que su línea de división sea visible y no coincida con el borde.
        limite_superior = ultimo_tick + paso_eje * 0.08
        
        for fila, periodo in enumerate(orden_visual, start=1):
            df_p = df_in[df_in['periodo'] == periodo]
            color_periodo = colores_periodo[periodo]

            fig_detalle_demanda.add_trace(
                go.Bar(
                    x=df_p['fecha_hora'],
                    y=df_p['potencia'],
                    marker_color=color_periodo,
                    name=periodo,
                    legendgroup=periodo,
                    hovertemplate=(
                        f'<b>{periodo}</b><br>'
                        'Fecha: %{x|%d/%m/%Y %H:%M}<br>'
                        'Demanda: %{y:,.2f} kW<extra></extra>'
                    )
                ),
                row=fila,
                col=1
            )

            fig_detalle_demanda.add_trace(
                go.Scatter(
                    x=[fecha_min, fecha_max],
                    y=[pot_con[periodo], pot_con[periodo]],
                    mode='lines',
                    line=dict(
                        color=color_periodo,
                        dash='dash',
                        width=2
                    ),
                    name=periodo,           # mismo nombre
                    legendgroup=periodo,     # mismo grupo → mismo color
                    showlegend=False
                ),
                row=fila,
                col=1
            )

        fig_detalle_demanda = aplicar_estilo(fig_detalle_demanda)
        fig_detalle_demanda.update_layout(
            title='Demanda cuartohoraria vs Potencia contratada por periodo',
            height=320 * len(orden_visual),
            legend_title_text='Periodo',
            bargap=0,
            margin=dict(t=100, b=70)
        )
        fig_detalle_demanda.update_yaxes(
            title_text='kW',
            range=[0, limite_superior],
            dtick=paso_eje,
            showgrid=True,
            gridwidth=1,
            gridcolor='rgba(128, 128, 128, 0.35)'
        )

        st.session_state.resultados_verificacion_potencia = {
            'fecha_inicio': fecha_inicio,
            'fecha_final': fecha_final,
            'df_coste': df_coste,
            'df_pot_mes': df_pot_mes,
            'fig_pie': fig_pie,
            'fig_detalle_demanda': fig_detalle_demanda,
            'coste_excesos': coste_excesos_potcon,
            'potencias': pot_con.copy(),
        }


with tab_verificacion:
    verificacion = st.session_state.get('resultados_verificacion_potencia')
    if verificacion is None:
        st.info('Realiza una verificación para mostrar sus resultados.')
    else:
        st.header('Resultados de la verificación', divider='rainbow')
        st.write(
            f"Datos del {verificacion['fecha_inicio']} al "
            f"{verificacion['fecha_final']}"
        )
        df_potencias_verificacion = pd.DataFrame(
            [verificacion['potencias']],
            index=['Potencia contratada (kW)']
        )
        df_potencias_verificacion.index.name = 'Concepto'
        df_potencias_verificacion = df_potencias_verificacion.applymap(
            lambda valor: formato_numero_es(valor, 2)
        )

        c1, c2 = st.columns([.3,.7])
        with c1:
            st.subheader('Potencias utilizadas en la verificación')
            st.dataframe(
                df_potencias_verificacion,
                use_container_width=True
            )
            st.subheader('Resultado económico')
            st.dataframe(
                verificacion['df_coste'],
                hide_index=True,
                use_container_width=True
            )
            st.plotly_chart(verificacion['fig_pie'], use_container_width=True)
            c21,c22,c23 = st.columns(3)
            with c21:
                total_potfra = round(
                    verificacion['df_pot_mes']['Total (€)'].sum(), 2
                )
                st.metric('Potencia facturada €)', formato_euros(total_potfra))
            with c22:
                st.metric(
                    'Excesos facturados €)',
                    formato_euros(verificacion['coste_excesos'])
                )
            with c23:
                total_tp_fra = round(
                    total_potfra + verificacion['coste_excesos'], 2
                )
                st.metric('Total término de potencia €)', formato_euros(total_tp_fra))
        with c2:
            st.plotly_chart(
                verificacion['fig_detalle_demanda'],
                use_container_width=True
            )


with tab_comparacion:
    st.caption(
        'Todos los escenarios se valoran sobre el mismo periodo y con los '
        'costes regulados de 2026.'
    )

    if 'df_in' not in locals() or df_in is None or df_in.empty:
        st.info('Carga una curva o una tabla de maxímetros para comparar.')
    else:
        df_comparacion_base = df_in.copy()
        rango_comparacion = None
        col_entrada, col_metricas, col_resultado = st.columns(
            [0.25, 0.30, 0.45],
            gap='large'
        )

        with col_entrada:
            st.subheader('Datos de entrada', divider='rainbow')
            with st.form('form_comparacion_potencias'):
                if 'fecha_hora' in df_comparacion_base.columns:
                    fechas_disponibles = pd.to_datetime(
                        df_comparacion_base['fecha_hora'], errors='coerce'
                    ).dropna()
                    fecha_min_comparacion = fechas_disponibles.min().date()
                    fecha_max_comparacion = fechas_disponibles.max().date()
                    rango_comparacion = st.date_input(
                        'Rango de fechas de la comparación',
                        value=(fecha_min_comparacion, fecha_max_comparacion),
                        min_value=fecha_min_comparacion,
                        max_value=fecha_max_comparacion,
                        format='DD/MM/YYYY'
                    )

                st.subheader('Potencias alternativas')
                df_potencias_comparacion_ini = pd.DataFrame(
                    {'Potencia (kW)': pot_con}
                )
                df_potencias_comparacion = st.data_editor(
                    df_potencias_comparacion_ini,
                    use_container_width=True,
                    num_rows='fixed'
                )
                submit_comparacion = st.form_submit_button(
                    'Calcular comparación',
                    type='primary',
                    use_container_width=True
                )

        with col_resultado:
            st.subheader('Gráfico comparativo', divider='rainbow')

        with col_metricas:
            st.subheader('Resumen', divider='rainbow')

        if submit_comparacion:
            errores_comparacion = validar_potencias(df_potencias_comparacion)
            if errores_comparacion:
                for error in errores_comparacion:
                    st.error(error)
            else:
                df_periodo_comparacion = df_comparacion_base.copy()
                if rango_comparacion is not None:
                    if not isinstance(rango_comparacion, (tuple, list)) or len(rango_comparacion) != 2:
                        st.error('Selecciona una fecha inicial y una fecha final.')
                        st.stop()
                    inicio_comparacion, fin_comparacion = rango_comparacion
                    fechas_comparacion = pd.to_datetime(
                        df_periodo_comparacion['fecha_hora'], errors='coerce'
                    )
                    df_periodo_comparacion = df_periodo_comparacion.loc[
                        (fechas_comparacion.dt.date >= inicio_comparacion)
                        & (fechas_comparacion.dt.date <= fin_comparacion)
                    ].copy()

                if df_periodo_comparacion.empty:
                    st.error('No hay datos en el rango seleccionado.')
                    st.stop()

                potencias_alternativas = (
                    df_potencias_comparacion['Potencia (kW)']
                    .astype(float)
                    .to_dict()
                )
                escenarios = {
                    'Contratadas': pot_con.copy(),
                }

                resultados_opt_sesion = st.session_state.get(
                    'resultados_potencia'
                )
                if resultados_opt_sesion is not None:
                    tabla_opt = resultados_opt_sesion[5]
                    fila_opt = tabla_opt.loc[
                        tabla_opt['Potencias (kW)'] == 'Optimizadas'
                    ]
                    if not fila_opt.empty:
                        def a_float_es(valor):
                            if isinstance(valor, str):
                                valor = valor.replace('.', '').replace(',', '.')
                            return float(valor)

                        escenarios['Optimizadas'] = {
                            p: a_float_es(fila_opt.iloc[0][p])
                            for p in orden_periodos
                        }

                escenarios['Alternativas'] = potencias_alternativas

                filas_comparacion = []
                for nombre_escenario, potencias_escenario in escenarios.items():
                    coste_potencia, coste_excesos, coste_total, _, _ = calcular_costes(
                        df_periodo_comparacion,
                        tarifa,
                        pyc_tp_opt,
                        tepp_opt,
                        meses,
                        potencias_escenario
                    )
                    filas_comparacion.append({
                        'Escenario': nombre_escenario,
                        **potencias_escenario,
                        'Coste potencia (€)': coste_potencia,
                        'Coste excesos (€)': coste_excesos,
                        'Coste total (€)': coste_total,
                    })

                df_resultado_comparacion = pd.DataFrame(filas_comparacion)
                coste_base = df_resultado_comparacion.loc[
                    df_resultado_comparacion['Escenario'] == 'Contratadas',
                    'Coste total (€)'
                ].iloc[0]
                df_resultado_comparacion['Ahorro vs contratadas (€)'] = (
                    coste_base - df_resultado_comparacion['Coste total (€)']
                )

                df_grafico_comparacion = df_resultado_comparacion.melt(
                    id_vars='Escenario',
                    value_vars=['Coste potencia (€)', 'Coste excesos (€)'],
                    var_name='Concepto',
                    value_name='Coste (€)'
                )
                fig_comparacion = px.bar(
                    df_grafico_comparacion,
                    x='Escenario',
                    y='Coste (€)',
                    color='Concepto',
                    text='Coste (€)',
                    barmode='stack',
                    title='Comparación de costes en el periodo seleccionado',
                    color_discrete_map={
                        'Coste potencia (€)': 'deepskyblue',
                        'Coste excesos (€)': 'blue',
                    }
                )
                fig_comparacion = aplicar_estilo(fig_comparacion)
                fig_comparacion.update_traces(
                    texttemplate='<b>%{y:,.0f} €</b>',
                    textposition='auto',
                    textfont_size=24,
                    cliponaxis=False,
                    hovertemplate=(
                        '<b>%{x}</b><br>'
                        'Coste: %{y:,.2f} €<extra></extra>'
                    )
                )
                fig_comparacion.update_layout(
                    barcornerradius=8,
                    legend_title_text='',
                    height=520,
                    xaxis=dict(
                        tickfont=dict(size=20),
                        title_font=dict(size=20)
                    )
                )

                fila_alternativa_grafico = df_resultado_comparacion.loc[
                    df_resultado_comparacion['Escenario'] == 'Alternativas'
                ].iloc[0]
                coste_alternativo_grafico = fila_alternativa_grafico[
                    'Coste total (€)'
                ]
                ahorro_grafico = coste_base - coste_alternativo_grafico
                porcentaje_grafico = (
                    abs(ahorro_grafico) / coste_base * 100
                    if coste_base else 0
                )
                ahorro_favorable_grafico = ahorro_grafico >= 0
                texto_impacto_grafico = (
                    'Ahorro' if ahorro_favorable_grafico else 'Sobrecoste'
                )
                fondo_impacto_grafico = (
                    '#bbf7d0' if ahorro_favorable_grafico else '#fecaca'
                )
                borde_impacto_grafico = (
                    '#15803d' if ahorro_favorable_grafico else '#dc2626'
                )
                fig_comparacion.add_annotation(
                    x='Alternativas',
                    y=1.02,
                    yref='paper',
                    yanchor='bottom',
                    visible=False,
                    text=(
                        f'<b>{texto_impacto_grafico}</b><br>'
                        f'<b>{formato_euros(abs(ahorro_grafico))} '
                        f'({formato_numero_es(porcentaje_grafico, 1)} %)</b>'
                    ),
                    showarrow=False,
                    bgcolor=fondo_impacto_grafico,
                    bordercolor=borde_impacto_grafico,
                    borderwidth=2,
                    borderpad=8,
                    font=dict(color=borde_impacto_grafico, size=20),
                    align='center'
                )

                st.session_state.resultado_comparacion_potencias = {
                    'tabla': df_resultado_comparacion,
                    'grafico': fig_comparacion,
                    'rango': rango_comparacion,
                }

        comparacion_guardada = st.session_state.get(
            'resultado_comparacion_potencias'
        )
        if comparacion_guardada is not None:
            tabla_comparacion_fmt = comparacion_guardada['tabla'].copy()
            for columna in orden_periodos:
                tabla_comparacion_fmt[columna] = tabla_comparacion_fmt[columna].apply(
                    lambda valor: formato_numero_es(valor, 2)
                )
            for columna in (
                'Coste potencia (€)',
                'Coste excesos (€)',
                'Coste total (€)',
                'Ahorro vs contratadas (€)',
            ):
                tabla_comparacion_fmt[columna] = tabla_comparacion_fmt[columna].apply(
                    formato_euros
                )

            # La tabla horizontal se conserva como fuente; se presenta
            # transpuesta para comparar cada concepto entre escenarios.
            tabla_comparacion_vertical = (
                tabla_comparacion_fmt
                .set_index('Escenario')
                .T
            )

            with col_resultado:
                st.plotly_chart(
                    comparacion_guardada['grafico'],
                    use_container_width=True
                )
                st.subheader('Detalle por escenario')
                st.dataframe(
                    tabla_comparacion_vertical,
                    use_container_width=True
                )

            tabla_metricas = comparacion_guardada['tabla']
            fila_contratada = tabla_metricas.loc[
                tabla_metricas['Escenario'] == 'Contratadas'
            ].iloc[0]
            fila_alternativa = tabla_metricas.loc[
                tabla_metricas['Escenario'] == 'Alternativas'
            ].iloc[0]
            ahorro_alternativa = (
                fila_contratada['Coste total (€)']
                - fila_alternativa['Coste total (€)']
            )
            porcentaje_impacto = (
                abs(ahorro_alternativa)
                / fila_contratada['Coste total (€)']
                * 100
                if fila_contratada['Coste total (€)'] else 0
            )

            with col_metricas:
                hay_ahorro = ahorro_alternativa >= 0
                texto_impacto = (
                    'El ahorro en el TP es de'
                    if hay_ahorro
                    else 'El sobrecoste es de'
                )
                color_impacto = '#15803d' if hay_ahorro else '#dc2626'
                borde_impacto = '#86efac' if hay_ahorro else '#fca5a5'
                fondo_impacto = '#bbf7d0' if hay_ahorro else '#fecaca'
                st.markdown(
                    f'''
                    <div style="
                        width: 100%;
                        box-sizing: border-box;
                        padding: 1rem;
                        margin-bottom: 1rem;
                        border: 1px solid {borde_impacto};
                        border-radius: 0.5rem;
                        background-color: {fondo_impacto};
                        color: {color_impacto};
                        text-align: center;
                    ">
                        <div style="font-size: 1.3rem; font-weight: 600;">
                            {texto_impacto}
                        </div>
                        <div style="font-size: 2.5rem; font-weight: 700;">
                            {formato_euros(abs(ahorro_alternativa))}
                            ({formato_numero_es(porcentaje_impacto, 1)} %)
                        </div>
                    </div>
                    ''',
                    unsafe_allow_html=True
                )

                col_resumen, col_alternativa = st.columns(2, gap='medium')
                with col_resumen:
                    st.markdown(
                        '<div style="font-size: 1.35rem; font-weight: 700;">'
                        'Contratadas</div>',
                        unsafe_allow_html=True
                    )
                    st.metric(
                        'Coste Potencia',
                        formato_euros(fila_contratada['Coste potencia (€)'])
                    )
                    st.metric(
                        'Coste Excesos',
                        formato_euros(fila_contratada['Coste excesos (€)'])
                    )
                    st.metric(
                        'Total TP',
                        formato_euros(fila_contratada['Coste total (€)'])
                    )

                with col_alternativa:
                    st.markdown(
                        '<div style="font-size: 1.35rem; font-weight: 700;">'
                        'Alternativas</div>',
                        unsafe_allow_html=True
                    )
                    st.metric(
                        'Coste Potencia',
                        formato_euros(fila_alternativa['Coste potencia (€)'])
                    )
                    st.metric(
                        'Coste Excesos',
                        formato_euros(fila_alternativa['Coste excesos (€)'])
                    )
                    st.metric(
                        'Total TP',
                        formato_euros(fila_alternativa['Coste total (€)']),
                        delta=(
                            f'{formato_euros(ahorro_alternativa)} '
                            f'({formato_numero_es(porcentaje_impacto, 1)} %)'
                        )
                    )

            with col_entrada:
                rango_guardado = comparacion_guardada.get('rango')
                if (
                    isinstance(rango_guardado, (tuple, list))
                    and len(rango_guardado) == 2
                ):
                    texto_rango = (
                        f'{rango_guardado[0]:%d/%m/%Y} – '
                        f'{rango_guardado[1]:%d/%m/%Y}'
                    )
                else:
                    texto_rango = 'Meses disponibles en la tabla'
                st.info(
                    f'**Periodo valorado:** {texto_rango}\n\n'
                    f'**Escenarios:** {len(tabla_metricas)}\n\n'
                    '**Costes regulados:** 2026'
                )


