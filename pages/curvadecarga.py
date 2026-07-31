import streamlit as st
import numpy as np
import pandas as pd
import io
import base64
import re
from html import escape
from pathlib import Path
from dateutil.relativedelta import relativedelta
from datetime import timedelta
import plotly.express as px
from jinja2 import Environment, FileSystemLoader
from backend_curvadecarga import (
    normalize_curve_simple, detectar_hojas_curva_excel, obtener_datos_contador,
    graficar_curva_horaria, graficar_diario_apilado, graficar_mensual_apilado, tabla_mensual_periodos, formatear_tabla_mensual_es, graficar_queso_periodos,
    graficar_media_horaria, graficar_media_horaria_combinada, graficar_boxplot_horario,
    graficar_dem_ver_mensual, graficar_con_gen_mensual,
    graficar_heatmap_dia_hora,
    calcular_patron_horario_boxplot, detectar_consumos_atipicos_horarios,
    resumir_atipicos_por_dia, calcular_kpis_atipicos, mostrar_kpis_atipicos, graficar_top_dias_revisables, graficar_heatmap_alertas, calcular_patron_horario_boxplot, obtener_top_horas_revisables,
    calcular_tabla_excesos_reactiva, calcular_tabla_factor_potencia, estilo_factor_potencia, calcular_tabla_precio_penalizacion_reactiva, calcular_tabla_coste_excesos_reactiva, estilo_coste_penalizacion,
    calcular_tabla_potencia_media_qh,calcular_tabla_coef_k, calcular_tabla_q_condensadores,
    calcular_comparacion, calcular_comparacion_costes
    )
from backend_comun import (
    aplicar_estilo,
    formatear_tabla_consumos,
    formatear_columnas_tabla,
)
from formato_es import formato_euros, formato_kwh, formato_numero_es



from utilidades import generar_menu

if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')

generar_menu()

if 'zona_periodos_cdc' not in st.session_state:
    st.session_state.zona_periodos = 'peninsula'

# ===============================
#  Interfaz SIDEBAR
# ===============================

hoja_curva_excel = None


def limpiar_curva_cargada():
    """Elimina la curva y los resultados calculados en esta sesión."""
    claves_curva = (
        "df_norm",
        "df_norm_h",
        "df_in",
        "csv_bytes_norm",
        "csv_bytes_h",
        "lista_ficheros",
        "consumo_total",
        "reactiva_total",
        "vertido_total",
        "consumo_neto",
        "vertido_neto",
        "rango_curvadecarga",
        "rango_fechas_comparativa",
        "precios_mensuales",
        "df_axon_raw",
        "frec_axon_raw",
        "reactiva_base_cache",
        "reactiva_compensacion",
        "curva_reactiva_version",
        "informe_reactiva_html",
    )
    for clave in claves_curva:
        st.session_state.pop(clave, None)
    st.session_state.curva_uploader_version = (
        st.session_state.get("curva_uploader_version", 0) + 1
    )


with st.sidebar:

    st.title("⚡:rainbow[PowerLoader]⚡")
    st.caption("Lee CSV/Excel, detecta columnas y normaliza horas al rango 0–23 del mismo día. Añade columnas adicionales.")

    if not st.session_state.get('usuario_autenticado', False):
        st.warning("🔒 Este módulo es solo para usuarios premium. Lo que estás viendo es un fichero de ejemplo")
        origen_curva = "Archivo CSV/Excel"
        uploaded = f"curvas/qh anual demo.csv" #es la --> qh 30 con aut anual Carles ES0031--01HS.csv
        atr_dfnorm = '3.0'

    else:
        origen_curva = st.selectbox(
            "Origen de la curva",
            ("Archivo CSV/Excel", "Axon"),
            index=0,
        )
        uploaded = None
        if origen_curva == "Archivo CSV/Excel":
            uploaded = st.file_uploader(
                "📂 Sube un archivo CSV o Excel",
                type=["csv", "xlsx"],
                accept_multiple_files=True,
                key=(
                    "curva_archivos_"
                    f"{st.session_state.get('curva_uploader_version', 0)}"
                ),
            )
            if uploaded:
                archivos_excel = [
                    archivo for archivo in uploaded
                    if archivo.name.lower().endswith(".xlsx")
                ]
                hojas_por_archivo = []
                for archivo_excel in archivos_excel:
                    try:
                        hojas_por_archivo.append(
                            set(detectar_hojas_curva_excel(archivo_excel))
                        )
                    except Exception:
                        hojas_por_archivo.append(set())

                if hojas_por_archivo:
                    hojas_comunes = set.intersection(*hojas_por_archivo)
                    opciones_hoja = [
                        h for h in ("Cuarto horarias", "Horarias")
                        if h in hojas_comunes
                    ]

                    if len(opciones_hoja) > 1:
                        hoja_curva_excel = st.radio(
                            "Curva de los Excel",
                            opciones_hoja,
                            format_func=lambda h: {
                                "Cuarto horarias": "Cuarto horaria",
                                "Horarias": "Horaria",
                            }[h],
                            horizontal=True,
                        )
                    elif len(opciones_hoja) == 1:
                        hoja_curva_excel = opciones_hoja[0]
        else:
            usuario_axon = st.text_input("Usuario Axon")
            password_axon = st.text_input("Contraseña Axon", type="password")
            cups_axon = st.text_input("CUPS")
            hoy_axon = pd.Timestamp.today().date()
            rango_axon = st.date_input(
                "Periodo de la curva",
                value=(
                    hoy_axon - timedelta(days=30),
                    hoy_axon - timedelta(days=1),
                ),
                max_value=hoy_axon,
                format="DD/MM/YYYY",
            )
            tipo_curva_axon = st.selectbox(
                "Tipo de curva",
                ("TM2", "TM1"),
                index=0,
                format_func=lambda valor: {
                    "TM1": "TM1 · Horaria (H)",
                    "TM2": "TM2 · Cuartohoraria (QH)",
                }[valor],
            )
        atr_dfnorm = st.sidebar.selectbox(
                    "Selecciona peaje de acceso:",
                    ("2.0", "3.0", "6.1", "6.2", "6.3", "6.4"),
                    index=0
                )
        #st.selectbox("Selecciona zona", options=["peninsula", "canarias", "baleares", "ceuta", "melilla"], index=0, key = 'zona_periodos', help="Se usa para asignar los periodos horarios según zona cuando la curva no trae columna de periodo.")
        opciones_zona_periodos = ["peninsula", "baleares", "canarias", "ceuta", "melilla"]
        st.selectbox(
            "Selecciona zona de periodos horarios",
            options=opciones_zona_periodos,
            index=0,
            key="zona_periodos_cdc",
            format_func=lambda x: {
                "peninsula": "Península",
                "baleares": "Baleares",
                "canarias": "Canarias",
                "ceuta": "Ceuta",
                "melilla": "Melilla",
            }[x]
        )

    normalizar = st.button(
        "Obtener y normalizar curva"
        if origen_curva == "Axon"
        else "Normalizar curva de carga",
        type='primary',
        use_container_width=True,
    )
    st.button(
        "🗑️ Eliminar curva y resultados",
        use_container_width=True,
        on_click=limpiar_curva_cargada,
        help=(
            "Elimina la curva cargada y sus cálculos de esta sesión. "
            "No borra preferencias, usuario ni cachés compartidas."
        ),
    )

    zona_mensajes = st.sidebar.empty()
    zona_mensajes2 = st.sidebar.empty()
    zona_mensajes3 = st.sidebar.empty()


# Inicializa el estado si no existe
if "df_norm" not in st.session_state:
    st.session_state.df_norm = None
if "df_norm_h" not in st.session_state:
    st.session_state.df_norm_h = None
if "df_in" not in st.session_state:
    st.session_state.df_in = None
if 'frec' not in st.session_state:
    st.session_state.frec = 'QH'
if 'fp_obj_min' not in st.session_state:
    st.session_state.fp_obj_min = 0.95
if 'fp_obj_max' not in st.session_state:
    st.session_state.fp_obj_max = 1.00
if 'fp_obj_sel' not in st.session_state:
    st.session_state.fp_obj_sel = 0.98
if 'margen_comp_min' not in st.session_state:
    st.session_state.margen_comp_min = 30 #en %
if "csv_bytes_norm" not in st.session_state:
    st.session_state.csv_bytes_norm = None
if "csv_bytes_h" not in st.session_state:
    st.session_state.csv_bytes_h = None


if normalizar and origen_curva == "Axon":
    try:
        if not isinstance(rango_axon, (tuple, list)) or len(rango_axon) != 2:
            raise ValueError("Selecciona una fecha inicial y una fecha final.")
        with st.spinner("Conectando con Axon y descargando medidas…"):
            curva_axon, frecuencia_axon = obtener_datos_contador(
                usuario_axon,
                password_axon,
                cups_axon,
                rango_axon[0],
                rango_axon[1],
                tipo_curva_axon,
            )
        st.session_state.df_axon_raw = curva_axon
        st.session_state.frec_axon_raw = frecuencia_axon
        archivo_axon = io.BytesIO(
            curva_axon.to_csv(index=False, sep=";").encode("utf-8")
        )
        archivo_axon.name = f"axon_{tipo_curva_axon.lower()}.csv"
        uploaded = archivo_axon
        zona_mensajes.success(
            f"✅ Curva de Axon obtenida: "
            f"{formato_numero_es(len(curva_axon))} registros."
        )
        zona_mensajes2.info(f"Resolución recibida: {frecuencia_axon}.")
    except Exception as e:
        st.session_state.pop("df_axon_raw", None)
        st.session_state.pop("frec_axon_raw", None)
        zona_mensajes.error(f"❌ Error al obtener la curva de Axon: {e}")


if normalizar and uploaded:
    try:

        dfs_norm = []
        dfs_in = []

        if not isinstance(uploaded, list):
            uploaded = [uploaded]

        for file in uploaded:
            df_in_i, df_norm_i, msg_unidades, flag_periodos_en_origen, df_periodos, frec = normalize_curve_simple(
                file,
                origin=file.name if hasattr(file, "name") else file,
                excel_sheet=hoja_curva_excel,
            )
            dfs_norm.append(df_norm_i)
            dfs_in.append(df_in_i)

        df_norm = pd.concat(dfs_norm)
        if len(dfs_in) == 1:
            df_in = dfs_in[0]
            st.session_state.lista_ficheros = None
        else:
            df_in = None
            st.session_state.lista_ficheros = [file.name for file in uploaded]

        consumo_total=df_norm['consumo_kWh'].sum()
        vertido_total=df_norm['excedentes_kWh'].sum()
        consumo_neto=df_norm['consumo_neto_kWh'].sum()
        vertido_neto=df_norm['vertido_neto_kWh'].sum()
        reactiva_total=df_norm['reactiva_kVArh'].sum()


        zona_mensajes.success("✅ Curva normalizada correctamente")
        if msg_unidades != "":
            zona_mensajes2.info(msg_unidades, icon="ℹ️")

        # --- Obtención de periodos ------------------------------------------------
        if not flag_periodos_en_origen:
            msg_periodos = 'Cargados periodos desde fichero auxiliar.'
            zona_mensajes3.warning(msg_periodos, icon="⚠️")

            # --- Determinar ATR y tipo de calendario ---
            if atr_dfnorm == "2.0":
                tipo_periodo = "dh_3p"
            else:
                tipo_periodo = "dh_6p"   # ambos ATR 3.0 y 6.1 usan 6 periodos

            # --- Si la columna 'periodo' no existe o está vacía ---
            if "periodo" not in df_norm.columns or df_norm["periodo"].isna().all():
                if "periodo" in df_norm.columns:
                    df_norm = df_norm.drop(columns=["periodo"])

                df_norm = pd.merge(
                    df_norm,
                    df_periodos[["fecha_hora", tipo_periodo]].rename(columns={tipo_periodo: "periodo"}),
                    on="fecha_hora",
                    how='left'
                )

            # --- Normalizar la columna 'periodo' ---
            df_norm["periodo"] = df_norm["periodo"].astype(str).str.strip()

            # --- Rellenar periodos faltantes (curvas QH) ---
            if df_norm["periodo"].isna().any() or (df_norm["periodo"] == "nan").any():
                df_norm["periodo"] = (
                    df_norm["periodo"]
                    .replace("nan", np.nan)
                    .ffill()
                )

        else:
            msg_periodos = 'Cargados periodos desde fichero origen'
            zona_mensajes3.info(msg_periodos, icon="ℹ️")
            if not st.session_state.get('usuario_free', False):
                # --- Detectar ATR según los periodos en el origen ---
                if "periodo" in df_norm.columns:
                    numeros = (
                        df_norm["periodo"]
                        .astype(str)
                        .str.extract(r"P?(\d+)", expand=False)
                        .dropna()
                        .astype(int)
                    )

                    if not numeros.empty and numeros.max() == 3:
                        atr_dfnorm = "2.0"
                        st.sidebar.success("Tres periodos detectados.")
                    else:
                        st.sidebar.warning("Seis periodos detectados")

                else:
                    st.sidebar.warning("ATENCIÓN: NO HAY PERIODOS DETECTADOS")
            else:
                atr_dfnorm = "3.0"


        #if frec =='QH':
        if frec in ["QH", "10MIN"]:

            # Agregar cada 4 muestras por hora
            # Agrupar a nivel horario (suma de los 4 cuartos horarios)
            df_norm_h = (
                df_norm.groupby(["fecha", "hora"], as_index=False)
                .agg({
                    "consumo_neto_kWh": "sum",
                    "reactiva_kVArh":"sum",
                    "vertido_neto_kWh": "sum",
                    "generacion_kWh": "sum",
                    "periodo": "first",
                    "tipo_dia":"first"
                })
            )
            df_norm_h["fecha_hora"] = pd.to_datetime(
                df_norm_h["fecha"].astype(str)
                + " "
                + df_norm_h["hora"].astype(str)
                + ":00",
                dayfirst=True,
                errors="coerce"
            )
            # 🔑 reconstrucción correcta de fecha_hora
            df_norm_h["fecha_hora"] = (
                pd.to_datetime(df_norm_h["fecha"])
                + pd.to_timedelta(df_norm_h["hora"], unit="h")
            )
        else:
            # Ya está en frecuencia horaria → copiar
            df_norm_h = df_norm[["fecha_hora", "fecha", "hora","consumo_neto_kWh", "reactiva_kVArh","vertido_neto_kWh", "generacion_kWh", "periodo", "tipo_dia"]].copy()

        df_norm_h = (
            df_norm_h.groupby("fecha_hora", as_index=False)
            .agg({
                "fecha": "first",
                "hora": "first",
                "consumo_neto_kWh": "sum",
                "reactiva_kVArh":"sum",
                "vertido_neto_kWh": "sum",
                "generacion_kWh": "sum",
                "periodo": "first",
                "tipo_dia": "first"
            })
            .sort_values("fecha_hora")
            .reset_index(drop=True)
        )


        consumototalhorario= df_norm_h['consumo_neto_kWh'].sum()
        print(f'consumo total df_norm_h: {consumototalhorario}')
        csv_bytes_norm = df_norm.reset_index(drop=True).to_csv(index=False, sep=";", decimal=",", float_format="%.3f").encode("utf-8")
        csv_bytes_h = df_norm_h.reset_index(drop=True).to_csv(index=False, sep=";", decimal=",", float_format="%.3f").encode("utf-8")

        st.session_state.df_norm = df_norm
        st.session_state.curva_reactiva_version = (
            st.session_state.get("curva_reactiva_version", 0) + 1
        )
        st.session_state.pop("reactiva_base_cache", None)
        st.session_state.pop("reactiva_compensacion", None)
        st.session_state.pop("informe_reactiva_html", None)
        st.session_state.atr_dfnorm = atr_dfnorm
        st.session_state.df_norm_h = df_norm_h
        st.session_state.csv_bytes_norm = csv_bytes_norm
        st.session_state.csv_bytes_h = csv_bytes_h
        st.session_state.frec = frec
        st.session_state.df_in = df_in
        st.session_state.consumo_total=consumo_total
        st.session_state.reactiva_total = reactiva_total
        st.session_state.vertido_total=vertido_total
        st.session_state.consumo_neto=consumo_neto
        st.session_state.vertido_neto=vertido_neto
        # Obtener fechas mínima y máxima del df_norm_h y guardar para telemindex
        fecha_ini = df_norm["fecha"].min()
        fecha_fin = df_norm["fecha"].max()
        st.session_state.rango_curvadecarga = (fecha_ini, fecha_fin)

    except Exception as e:
        zona_mensajes.error(f"❌ Error al normalizar: {e}")
        st.stop()

elif origen_curva == "Archivo CSV/Excel":
    zona_mensajes.info("⬆️ Sube un archivo CSV o Excel para comenzar.")





if st.session_state.get("df_norm") is not None:
    st.sidebar.markdown(f'Peaje actualmente seleccionado: **:orange[{st.session_state.atr_dfnorm}]**')
    st.sidebar.markdown(f'Resolución temporal de la curva: **:orange[{st.session_state.frec}]**')
    # --- Descarga ---
    csv_bytes = st.session_state.get("csv_bytes_norm")
    if not st.session_state.get('usuario_autenticado', False):
        habilitar_descarga = False
        #st.sidebar.download_button("⬇️ Descargar CSV normalizado", csv_bytes, "curva_normalizada.csv", "text/csv", disabled=True)
    else:
        habilitar_descarga = True
        #st.sidebar.download_button("⬇️ Descargar CSV normalizado", csv_bytes, "curva_normalizada.csv", "text/csv", disabled=False)
    st.sidebar.download_button("⬇️ Descargar CSV normalizado", csv_bytes or b"", "curva_normalizada.csv", "text/csv", disabled=not habilitar_descarga or csv_bytes is None, use_container_width=True)

    csv_bytes_h = st.session_state.get("csv_bytes_h")
    if not st.session_state.get('usuario_autenticado', False):
        habilitar_descarga = False
        #st.sidebar.download_button("⬇️ Descargar CSV normalizado", csv_bytes, "curva_normalizada.csv", "text/csv", disabled=True)
    else:
        habilitar_descarga = True
        #st.sidebar.download_button("⬇️ Descargar CSV normalizado", csv_bytes, "curva_normalizada.csv", "text/csv", disabled=False)
    st.sidebar.download_button("⬇️ Descargar CSV agrupado horario", csv_bytes_h or b"", "curva_agrupado.csv", "text/csv", disabled=not habilitar_descarga or csv_bytes_h is None, use_container_width=True)



    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        [
            'Resumen',
            'Perfiles Horarios',
            'Autoconsumo',
            'Comparaciones',
            'Reactiva',
            'Informe',
        ]
    )

    # ===============================================================
    # RESUMEN GENERAL
    # ===============================================================
    with tab1:
        altura_df = 250
        c1,c2,c3=st.columns([.35,.35,.3])
        with c1:
            # Visor del df in
            st.subheader("📄 Vista previa del archivo original")
            if st.session_state.get("df_in") is not None:
                st.dataframe(st.session_state.df_in, height=altura_df)
            elif st.session_state.get("lista_ficheros"):
            #elif st.session_state.get("lista_ficheros") is not None:
                with st.container(height=250):
                    st.info("Se han cargado múltiples suministros.")

                    st.write("Archivos cargados:")
                    for f in st.session_state.lista_ficheros:
                        st.write(f"• {f}")
        with c2:
            # Visor del df out
            st.subheader("📊 Tabla normalizada de datos")
            total_filas_norm = len(st.session_state.df_norm)
            st.caption(f"Vista previa: primeras 1.000 filas de {formato_numero_es(total_filas_norm)}")
            st.dataframe(st.session_state.df_norm.head(1000), height=altura_df)
        with c3:
            # --- Resumen registros---
            st.subheader("Resumen de datos")
            c31,c32,c33 = st.columns(3)
            with c31:
                st.metric("Número de registros", formato_numero_es(len(st.session_state.df_norm)))
                st.metric("Fecha inicio", st.session_state.df_norm["fecha_hora"].min().strftime("%d.%m.%Y"))
                st.metric("Fecha final", st.session_state.df_norm["fecha_hora"].max().strftime("%d.%m.%Y"))
            with c32:
                #st.subheader("Resumen datos")
                st.metric("Consumo total kWh", formato_kwh(st.session_state.consumo_total))
                st.metric("Vertido total kWh", formato_kwh(st.session_state.vertido_total))
                st.metric("Reactiva total kVArh", formato_numero_es(st.session_state.reactiva_total))
            with c33:
                #st.subheader("Resumen datos")
                st.metric("Consumo neteo kWh", formato_kwh(st.session_state.consumo_neto))
                st.metric("Vertido neteo kWh", formato_kwh(st.session_state.vertido_neto))

        c1,c2=st.columns([.7,.3])
        with c1:
            st.subheader("Gráfico de consumo")
            # Mostrar gráfico
            graf_horario = graficar_curva_horaria(st.session_state.df_norm_h, st.session_state.frec)
            st.plotly_chart(graf_horario, use_container_width=True)
        with c2:
            st.subheader("Consumo por periodos")
            graf_periodos, df_periodos = graficar_queso_periodos(st.session_state.df_norm_h)
            st.plotly_chart(graf_periodos, use_container_width=True)

        c1,c2,c3=st.columns([.4,.3,.3])
        with c1:
            graf_diario = graficar_diario_apilado(st.session_state.df_norm_h)
            st.plotly_chart(graf_diario, use_container_width=True)
        with c2:
            graf_mensual = graficar_mensual_apilado(st.session_state.df_norm_h)
            st.plotly_chart(graf_mensual, use_container_width=True)
            tabla_mensual_consumos = tabla_mensual_periodos(st.session_state.df_norm_h)

            # La fila de total es solo para presentacion. Conservamos la tabla
            # mensual original para los calculos de reactiva que se hacen despues.
            fila_total_consumos = tabla_mensual_consumos.drop(columns="Mes").sum().to_dict()
            fila_total_consumos["Mes"] = "Total"
            tabla_mensual_consumos_mostrar = pd.concat(
                [tabla_mensual_consumos, pd.DataFrame([fila_total_consumos])],
                ignore_index=True,
            )

            from backend_comun import formatear_tabla_consumos
            tabla_mensual_consumos_fmt = formatear_tabla_consumos(
                tabla_mensual_consumos_mostrar,
                columna_mes="Mes",
                incluir_unidades=False,
            )
            st.dataframe(tabla_mensual_consumos_fmt, use_container_width=True, hide_index=True)
        with c3:
            graf_medias_horarias_total=graficar_media_horaria('Todos', ymax = None)
            st.plotly_chart(graf_medias_horarias_total, use_container_width=True)

    # ========================================================================================================
    # ANÁLISIS
    # ========================================================================================================
    with tab2:

        graf_medias_horarias_combinadas, ymax = graficar_media_horaria_combinada()
        #zmax_heatmap = st.session_state.df_norm_h["consumo_neto_kWh"].max()
        zmax_heatmap = st.session_state.df_norm_h["consumo_neto_kWh"].quantile(0.98)
        print (zmax_heatmap)

        graf_medias_horarias_total=graficar_media_horaria('Todos', ymax)
        graf_medias_horarias_lab=graficar_media_horaria('L-V',ymax)
        graf_medias_horarias_ffss=graficar_media_horaria('FS', ymax)

        graf_medias_horarias_total_ranking = graficar_media_horaria('Todos', ymax, ordenar=True)
        graf_medias_horarias_lab_ranking = graficar_media_horaria('L-V', ymax, ordenar=True)
        graf_medias_horarias_ffss_ranking = graficar_media_horaria('FS', ymax, ordenar=True)

        graf_bigotes_total = graficar_boxplot_horario('Todos')
        graf_bigotes_lab = graficar_boxplot_horario('L-V')
        graf_bigotes_ffss = graficar_boxplot_horario('FS')

        graf_heatmap_total = graficar_heatmap_dia_hora('Todos', zmax_heatmap)
        graf_heatmap_lab = graficar_heatmap_dia_hora('L-V', zmax_heatmap)
        graf_heatmap_ffss = graficar_heatmap_dia_hora('FS', zmax_heatmap)

        patron_horario = calcular_patron_horario_boxplot()
        df_analisis_horario = detectar_consumos_atipicos_horarios(
            patron=patron_horario,
            min_exceso_kwh=0,
            min_ratio=1.0
        )

        df_revisables = df_analisis_horario[df_analisis_horario["es_revisable"]].copy()

        resumen_dia = resumir_atipicos_por_dia(df_analisis_horario)
        kpis = calcular_kpis_atipicos(df_analisis_horario, resumen_dia)

        mostrar_kpis_atipicos(kpis)

        fig_top = graficar_top_dias_revisables(resumen_dia, top_n=20, metrica="exceso_total_vs_mediana")

        serie_alertas = df_analisis_horario.loc[df_analisis_horario["es_revisable"], "exceso_vs_mediana"]
        zmax_alertas = serie_alertas.quantile(0.95) if not serie_alertas.empty else 1
        fig_lv = graficar_heatmap_alertas(df_analisis_horario, tipo_dia="L-V", metrica="exceso_vs_mediana", zmax=zmax_alertas)
        fig_fs = graficar_heatmap_alertas(df_analisis_horario, tipo_dia="FS", metrica="exceso_vs_mediana", zmax=zmax_alertas)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.plotly_chart(graf_medias_horarias_total, use_container_width=True)
            st.plotly_chart(graf_medias_horarias_total_ranking, use_container_width=True)
            st.plotly_chart(graf_bigotes_total, use_container_width=True)
            st.plotly_chart(graf_heatmap_total, use_container_width=True)
        with c2:
            st.plotly_chart(graf_medias_horarias_lab, use_container_width=True)
            st.plotly_chart(graf_medias_horarias_lab_ranking, use_container_width=True)
            st.plotly_chart(graf_bigotes_lab, use_container_width=True)
            st.plotly_chart(graf_heatmap_lab, use_container_width=True)
            st.plotly_chart(fig_lv, use_container_width=True)


        with c3:
            st.plotly_chart(graf_medias_horarias_ffss, use_container_width=True)
            st.plotly_chart(graf_medias_horarias_ffss_ranking, use_container_width=True)
            st.plotly_chart(graf_bigotes_ffss, use_container_width=True)
            st.plotly_chart(graf_heatmap_ffss, use_container_width=True)
            st.plotly_chart(fig_fs, use_container_width=True)
        with c4:
            st.plotly_chart(graf_medias_horarias_combinadas, use_container_width=True)


        st.write("Patrón horario boxplot")
        st.dataframe(patron_horario)



        st.write("Análisis horario frente al patrón")
        st.dataframe(df_analisis_horario)



        st.write("Horas potencialmente revisables")
        st.dataframe(
            df_revisables[
                [
                    "fecha_hora",
                    "fecha",
                    "tipo_dia",
                    "hora",
                    "consumo_real",
                    "mediana",
                    "limite_sup",
                    "exceso_vs_mediana",
                    "exceso_vs_limite_sup",
                    "ratio_vs_mediana"
                ]
            ].sort_values("exceso_vs_mediana", ascending=False)
        )




        if fig_top is not None:
            st.plotly_chart(fig_top, use_container_width=True)






        st.write("Top horas revisables")
        st.dataframe(obtener_top_horas_revisables(df_analisis_horario, top_n=50))

    # ================================================================================================
    # AUTOCONSUMO
    # ================================================================================================
    from backend_curvadecarga import graficar_dem_ver, graficar_con_gen
    with tab3:
        df_norm_h_modif = st.session_state.df_norm_h.copy()
        df_norm_h_modif['demanda_neto_kWh'] = df_norm_h_modif['consumo_neto_kWh']
        if df_norm_h_modif["generacion_kWh"].sum() > 0:
            df_norm_h_modif['consumo_neto_kWh'] = df_norm_h_modif['demanda_neto_kWh'] + df_norm_h_modif['generacion_kWh'] - df_norm_h_modif['vertido_neto_kWh']
            df_norm_h_modif["autoconsumo_kWh"] = (df_norm_h_modif["generacion_kWh"] - df_norm_h_modif["vertido_neto_kWh"])
            df_norm_h_modif["autoconsumo_kWh"] = df_norm_h_modif["autoconsumo_kWh"].apply(lambda x: x if x > 0 else 0)
        else:
            df_norm_h_modif["autoconsumo_kWh"] = 0

        df_be = df_norm_h_modif.agg({
            "consumo_neto_kWh": "sum",
            "generacion_kWh": "sum",
            "demanda_neto_kWh": "sum",
            "vertido_neto_kWh": "sum",
            "autoconsumo_kWh": "sum",
        }).to_frame().T

        #calculamos el % de cobertura del consumo, autoconsumo por un lado y demanda por otro
        df_be['%_autoconsumo']=round(df_be['autoconsumo_kWh']*100/df_be['consumo_neto_kWh'],2)
        df_be['%_demanda']=100-df_be['%_autoconsumo']
        #calculamos el % de aprovechamiento de la generación
        df_be['%_vertido_neto_kWh']=round(df_be['vertido_neto_kWh']*100/df_be['generacion_kWh'],2)
        df_be['%_generacion']=100-df_be['%_vertido_neto_kWh']


        colores_energia = {
            'consumo_neto_kWh': '#3498DB',        # azul
            'demanda_neto_kWh': '#E74C3C',         # naranja
            'generacion_kWh': '#F7DC6F',  # amarillo suave
            'vertido_neto_kWh': '#AF7AC5',        # lila / violeta claro
            'autoconsumo_kWh': '#2ECC71'     # verde
        }

        from backend_balkoning_solar import graficar_quesos_balance
        #graf_con_gen = graficar_con_gen(df_be)
        #graf_cobertura = graficar_barras_balance(df_be, 'cobertura', colores_energia)
        #graf_aprovechamiento = graficar_barras_balance(df_be, 'aprovechamiento', colores_energia)

        total_consumo = df_be['consumo_neto_kWh'].sum()
        total_genfv = df_be['generacion_kWh'].sum()
        total_demanda = df_be['demanda_neto_kWh'].sum()
        total_vertido = df_be['vertido_neto_kWh'].sum()
        #total_aprovechamiento = total_genfv-total_vertido
        total_autoconsumo = df_be['autoconsumo_kWh'].sum()
        #print(total_autoconsumo)

        cobertura_media_porc=round(total_autoconsumo*100/total_consumo,2)
        #aprovechamiento_medio_porc=round(100-total_vertido*100/total_genfv,2)
        aprovechamiento_medio_porc = (
            round(100 - total_vertido * 100 / total_genfv, 2)
            if pd.notna(total_genfv) and total_genfv != 0
            else 0
        )


        # DATAFRANES PARA QUESOS RESUMEN BALANCE ENERGÉTICO
        df_aprovechamiento = pd.DataFrame({
            'concepto': ['autoconsumo_kWh', 'vertido_neto_kWh'],
            'energia_kwh': [total_autoconsumo, total_vertido]
        })
        df_cobertura = pd.DataFrame({
            'concepto': ['autoconsumo_kWh', 'demanda_neto_kWh'],
            'energia_kwh': [total_autoconsumo, total_demanda]
        })
        graf_aprovechamiento_total = graficar_quesos_balance(df_aprovechamiento, aprovechamiento_medio_porc, colores_energia, 'aprovechamiento')
        graf_cobertura_total = graficar_quesos_balance(df_cobertura, cobertura_media_porc, colores_energia, 'cobertura')

        graf_dem_ver = graficar_dem_ver(df_norm_h_modif, colores_energia)
        graf_con_gen = graficar_con_gen(df_norm_h_modif, colores_energia)


        with st.container():
            st.subheader('Balance energético')
            c1, c2, c3= st.columns([.3,.4,.4])
            with c1:

                c21, c22 = st.columns(2)
                with c21:
                    st.metric("Consumo total (kWh)", formato_kwh(total_consumo))
                    st.metric("Demanda total (kWh)", formato_kwh(total_demanda))
                    st.metric("Generación FV (kWh)", formato_kwh(total_genfv))
                with c22:
                    #st.metric("", "")
                    st.metric("Autoconsumo (kWh)", formato_kwh(total_autoconsumo))
                    st.metric("Vertido (kWh)", formato_kwh(total_vertido))
            with c2:
                st.plotly_chart(graf_aprovechamiento_total)
            with c3:
                st.plotly_chart(graf_cobertura_total)
        #with c2:
        with st.container():
            c1,c2 = st.columns([.3,.7])
            with c1:
                graf_dem_ver_mensual = graficar_dem_ver_mensual(df_norm_h_modif, colores_energia)
                st.plotly_chart(graf_dem_ver_mensual)

            with c2:
               st.plotly_chart(graf_dem_ver, use_container_width=True)
        with st.container():
            c1,c2 = st.columns([.3,.7])
            with c1:
                graf_con_gen_mensual = graficar_con_gen_mensual(df_norm_h_modif, colores_energia)
                st.plotly_chart(graf_con_gen_mensual, use_container_width=True)

            with c2:
                st.plotly_chart(graf_con_gen, use_container_width=True)



    # ===================================================================================================================================================================================================
    # COMPARATIVAS
    # ===================================================================================================================================================================================================


    res = calcular_comparacion()

    fechas = res["fechas"]

    fecha_ini_global = fechas["fecha_ini_global"]
    fecha_fin_global = fechas["fecha_fin_global"]
    fecha_max_comparable = fechas["fecha_max_comparable"]
    rango_valido = fechas["rango_valido"]

    df_pivot = res['df_pivot']
    resumen_html = res["resumen_html"]
    fig_total = res["fig_total"]
    fig_mensual = res["fig_mensual"]

    with tab4:
        with st.container():
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.subheader('Introduce rango de fechas a comparar')
                st.info(
                    f"Rango disponible de la curva: "
                    f"{fecha_ini_global.strftime('%d.%m.%Y')} → {fecha_fin_global.strftime('%d.%m.%Y')}"
                )
                if rango_valido is not None:
                    st.success(
                        f"Rango comparable seleccionable: "
                        f"{rango_valido[0].strftime('%d.%m.%Y')} → {rango_valido[1].strftime('%d.%m.%Y')}"
                    )
                else:
                    st.warning(res["mensaje"])
                    #st.stop()


            if rango_valido is not None:

                    with c1:
                        with st.form('Seleccionar'):
                            st.date_input("Selecciona periodo base", min_value=fecha_ini_global, max_value=fecha_max_comparable, key="rango_fechas_comparativa", format="DD.MM.YYYY")
                            st.form_submit_button('Actualizar periodo de comparación')
                    with c2:
                        st.subheader('Tabla de resultados')
                        #df_pivot_fmt = formatear_resumen_mixto(df_pivot)
                        df_pivot_fmt = formatear_columnas_tabla(
                            df_pivot,
                            columnas_kwh=["Base", "+1 año", "Δ"],
                            columnas_pct=["Δ %"],
                            incluir_unidades=False
                        )
                        st.dataframe(df_pivot_fmt, use_container_width=True, hide_index=True)
                        st.markdown(resumen_html, unsafe_allow_html=True)

                    with c3:
                        if fig_total is not None:
                            st.plotly_chart(fig_total, use_container_width=True)
                    with c4:
                        if fig_mensual is not None:
                            st.plotly_chart(fig_mensual, use_container_width=True)

        with st.container():
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                precios_mensuales = st.session_state.get("precios_mensuales", None)
                if precios_mensuales is None:
                    st.warning('Accede a Telemindex para obtender datos de indexado de la curva introducida')
                else:
                    st.success('Disponibles datos de indexado para la curva introducida')

        if precios_mensuales is not None and rango_valido is not None:

            res_costes = calcular_comparacion_costes(
                precios_mensuales=precios_mensuales,
                rango_base=st.session_state.get("rango_fechas_comparativa", None)
            )

            if not res_costes["ok"]:
                st.warning(res_costes["mensaje"])

            else:
                df_costes = res_costes["df_costes"]
                df_efectos = res_costes["df_efectos"]

                with st.container():

                    #st.markdown("---")
                    st.header("Comparativa de costes de energía", divider='rainbow')

                    c1, c2, c3, c4 = st.columns(4)

                    with c1:
                        #st.markdown("##### Resumen económico")
                        st.subheader('Resumen económico')
                        st.markdown(
                            res_costes["resumen_html_costes"],
                            unsafe_allow_html=True
                        )
                        st.markdown("##### Tabla de costes")

                        df_costes_fmt = formatear_columnas_tabla(
                            df_costes,
                            columnas_kwh=["Consumo base", "+1 año"],
                            columnas_euros=["Coste base", "Coste +1 año", "Δ coste"],
                            columnas_pct=["Δ coste %"],
                            incluir_unidades=False
                        )

                        st.dataframe(
                            df_costes_fmt,
                            use_container_width=True,
                            hide_index=True
                        )

                    with c2:
                        if res_costes["fig_coste_total"] is not None:
                            st.plotly_chart(
                                res_costes["fig_coste_total"],
                                use_container_width=True
                            )

                    with c3:
                        if res_costes["fig_efectos"] is not None:
                            st.plotly_chart(
                                res_costes["fig_efectos"],
                                use_container_width=True
                            )

                    with c4:
                        if res_costes["fig_precio_medio"] is not None:
                            st.plotly_chart(
                                res_costes["fig_precio_medio"],
                                use_container_width=True
                            )

                with st.container():

                    c1, c2, c3, c4 = st.columns(4)

                    with c1:
                        st.markdown("##### Descomposición de la variación")

                        df_efectos_fmt = formatear_columnas_tabla(
                            df_efectos,
                            columnas_euros=[
                                "Δ coste real",
                                "Efecto precio",
                                "Efecto consumo",
                                "Coste con consumo base y precio +1 año"
                            ],
                            incluir_unidades=False
                        )

                        st.dataframe(
                            df_efectos_fmt,
                            use_container_width=True,
                            hide_index=True
                        )

                    #with c2:


    # ======================================================================================================================================================
    # REACTIVA
    # ======================================================================================================================================================
    with tab5:
        df_norm_h_reactiva = st.session_state.df_norm_h.copy()
        df_norm_reactiva = st.session_state.df_norm.copy()
        hay_datos_reactiva = (
            "reactiva_kVArh" in df_norm_reactiva.columns
            and pd.to_numeric(
                df_norm_reactiva["reactiva_kVArh"],
                errors="coerce",
            ).notna().any()
        )
        if not hay_datos_reactiva:
            st.subheader("RESUMEN COMPENSACIÓN")
            st.warning(
                "La curva de carga no contiene datos de energía reactiva. "
                "No es posible realizar un estudio de compensación de "
                "reactiva.",
                icon="⚠️",
            )
        else:
            fecha_fin_reactiva = df_norm_h_reactiva["fecha_hora"].max().normalize()
            fecha_inicio_reactiva = df_norm_h_reactiva["fecha_hora"].min().normalize()
            if (fecha_fin_reactiva - fecha_inicio_reactiva).days + 1 > 365:
                fecha_inicio_reactiva = fecha_fin_reactiva - pd.Timedelta(days=364)
                fecha_limite_reactiva = fecha_fin_reactiva + pd.Timedelta(days=1)
                df_norm_h_reactiva = df_norm_h_reactiva[
                    (df_norm_h_reactiva["fecha_hora"] >= fecha_inicio_reactiva)
                    & (df_norm_h_reactiva["fecha_hora"] < fecha_limite_reactiva)
                ].copy()
                df_norm_reactiva = df_norm_reactiva[
                    (df_norm_reactiva["fecha_hora"] >= fecha_inicio_reactiva)
                    & (df_norm_reactiva["fecha_hora"] < fecha_limite_reactiva)
                ].copy()

            version_curva = st.session_state.get("curva_reactiva_version", 0)
            cache_base = st.session_state.get("reactiva_base_cache")
            if not cache_base or cache_base.get("version") != version_curva:
                tabla_mensual_consumos_reactiva = tabla_mensual_periodos(
                    df_norm_h_reactiva,
                    columna_valor="consumo_neto_kWh",
                )
                df_reactiva = tabla_mensual_periodos(
                    df_norm_h_reactiva,
                    columna_valor="reactiva_kVArh",
                )
                df_excesos_reactiva = calcular_tabla_excesos_reactiva(
                    tabla_mensual_consumos_reactiva,
                    df_reactiva,
                )
                df_fp = calcular_tabla_factor_potencia(
                    tabla_mensual_consumos_reactiva,
                    df_reactiva,
                )
                df_coste_excesos_reactiva = calcular_tabla_coste_excesos_reactiva(
                    df_excesos_reactiva,
                    df_fp,
                )
                df_potmed_qh = calcular_tabla_potencia_media_qh(
                    df_norm_reactiva,
                    columna_valor="consumo_neto_kWh",
                )
                cache_base = {
                    "version": version_curva,
                    "consumos": tabla_mensual_consumos_reactiva,
                    "reactiva": df_reactiva,
                    "excesos": df_excesos_reactiva,
                    "fp": df_fp,
                    "costes": df_coste_excesos_reactiva,
                    "potencia_media": df_potmed_qh,
                }
                st.session_state.reactiva_base_cache = cache_base
            else:
                tabla_mensual_consumos_reactiva = cache_base["consumos"]
                df_reactiva = cache_base["reactiva"]
                df_excesos_reactiva = cache_base["excesos"]
                df_fp = cache_base["fp"]
                df_coste_excesos_reactiva = cache_base["costes"]
                df_potmed_qh = cache_base["potencia_media"]

            total_penalizacion_reactiva = df_coste_excesos_reactiva["Total"].sum()

            tabla_mensual_consumos_reactiva_fmt = formatear_tabla_consumos(
                tabla_mensual_consumos_reactiva,
                columna_mes="Mes",
                incluir_unidades=False,
            )
            df_potmed_qh_fmt = formatear_tabla_consumos(df_potmed_qh, columna_mes="Mes", incluir_unidades=False)
            df_reactiva_fmt = formatear_tabla_consumos(df_reactiva, columna_mes="Mes", incluir_unidades=False)
            df_excesos_react_fmt = formatear_tabla_consumos(df_excesos_reactiva, columna_mes="Mes", incluir_unidades=False)

            #aplicamos colores a la tabla mensual de FPs
            df_fp_fmt = df_fp.copy()
            df_fp_fmt.columns.name = None
            cols_fp = [c for c in df_fp_fmt.columns if c != "Mes"]
            styler_fp = (
                df_fp_fmt
                .style
                .applymap(estilo_factor_potencia, subset=cols_fp)
                .format({
                    col: lambda x: "" if x == "" or pd.isna(x) else f"{float(x):.2f}"
                    for col in cols_fp
                })
            )

            #calculamos penalizaciones y formateamos
            df_coste_excesos_reactiva_fmt = df_coste_excesos_reactiva.copy()
            df_coste_excesos_reactiva_fmt.columns.name = None
            cols_coste = [c for c in df_coste_excesos_reactiva_fmt.columns if c != "Mes"]
            for col in cols_coste:
                df_coste_excesos_reactiva_fmt[col] = (
                    df_coste_excesos_reactiva_fmt[col]
                    #.replace("None", np.nan)
                    .replace(["None", "nan", "NaN", ""], np.nan)
                    #.replace(None, np.nan)
                )
                df_coste_excesos_reactiva_fmt[col] = pd.to_numeric(df_coste_excesos_reactiva_fmt[col], errors="coerce")
            # 2) Convertimos NaN a "" SOLO para visualización
            df_coste_excesos_reactiva_fmt[cols_coste] = df_coste_excesos_reactiva_fmt[cols_coste].astype(object)
            df_coste_excesos_reactiva_fmt[cols_coste] = df_coste_excesos_reactiva_fmt[cols_coste].where(
                pd.notna(df_coste_excesos_reactiva_fmt[cols_coste]),
                ""
            )
            # 3) Formato visual
            def formato_coste_celda(x):
                if x == "" or pd.isna(x):
                    return ""
                try:
                    x = float(x)
                except:
                    return ""
                return formato_numero_es(x, 2)

            styler_coste_exc = (
                df_coste_excesos_reactiva_fmt
                .style
                .applymap(estilo_coste_penalizacion, subset=cols_coste)
                .format({
                    #col: lambda x: "" if pd.isna(x) else f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    col: formato_coste_celda
                    for col in cols_coste
                },
                na_rep=""
                )
            )

            cols_periodos = [c for c in df_fp.columns if c.startswith("P")]
            fp_min = df_fp[cols_periodos].min().min()
            fp_med = round(df_fp["Total"].mean(), 2)
            fp_max = df_fp[cols_periodos].max().max()

            def gestionar_form_compensacion():
                with st.form("form_compensacion_reactiva"):
                    st.subheader("Cálculo de compensación")
                    c_form1, c_form2, c_form3 = st.columns(3)
                    with c_form1:
                        fp_obj_min_form = st.number_input(
                            "Cos φ objetivo mínimo",
                            min_value=0.95,
                            max_value=1.00,
                            value=float(st.session_state.fp_obj_min),
                            disabled=True,
                        )
                    with c_form2:
                        margen_comp_form = st.number_input(
                            "Margen de seguridad (%)",
                            min_value=30,
                            max_value=50,
                            value=int(st.session_state.margen_comp_min),
                        )
                    with c_form3:
                        fp_obj_sel_form = st.number_input(
                            "Cos φ deseado",
                            min_value=0.95,
                            max_value=1.00,
                            value=0.98,
                            step=0.01,
                            format="%.2f",
                        )
                    calcular_compensacion = st.form_submit_button(
                        "Calcular compensación",
                        type="primary",
                        use_container_width=True,
                    )

                if calcular_compensacion:
                    from backend_curvadecarga import (
                        calcular_curva_q_dimensionamiento,
                        graficar_compensacion_dimensionamiento,
                    )
                    df_coef_k_min = calcular_tabla_coef_k(df_fp, fp_obj_min_form)
                    df_q_condensadores_min = calcular_tabla_q_condensadores(
                        df_potmed_qh,
                        df_coef_k_min,
                    )
                    cols_q = [
                        c for c in df_q_condensadores_min.columns
                        if c.startswith("P")
                    ]
                    q_min = df_q_condensadores_min[cols_q].max().max()
                    q_min_margen = q_min * (1 + margen_comp_form / 100)
                    df_curva_q = calcular_curva_q_dimensionamiento(
                        df_fp=df_fp,
                        df_potmed_qh=df_potmed_qh,
                        fp_ini=fp_min,
                        fp_fin=1.000,
                        paso=0.001,
                    )
                    df_curva_aux = (
                        df_curva_q[["fp_obj", "q_max"]]
                        .dropna()
                        .sort_values("q_max")
                    )
                    q_min_margen_clip = np.clip(
                        q_min_margen,
                        df_curva_aux["q_max"].min(),
                        df_curva_aux["q_max"].max(),
                    )
                    fp_min_margen = float(np.interp(
                        q_min_margen_clip,
                        df_curva_aux["q_max"],
                        df_curva_aux["fp_obj"],
                    ))
                    fp_obj_sel_aplicado = max(
                        float(fp_obj_sel_form),
                        fp_min_margen,
                    )
                    df_coef_k_sel = calcular_tabla_coef_k(
                        df_fp,
                        fp_obj_sel_aplicado,
                    )
                    df_q_condensadores_sel = calcular_tabla_q_condensadores(
                        df_potmed_qh,
                        df_coef_k_sel,
                    )
                    q_sel = df_q_condensadores_sel[cols_q].max().max()
                    fig_compensacion = graficar_compensacion_dimensionamiento(
                        df_curva_q=df_curva_q,
                        q_min=q_min,
                        fp_min_rec=fp_min_margen,
                        q_min_rec=q_min_margen,
                        q_sel=q_sel,
                        fp_ini=fp_min,
                    )
                    st.session_state.margen_comp_min = margen_comp_form
                    st.session_state.fp_obj_sel = fp_obj_sel_aplicado
                    st.session_state.reactiva_compensacion = {
                        "version": version_curva,
                        "q_min": q_min,
                        "q_min_margen": q_min_margen,
                        "fp_min_margen": fp_min_margen,
                        "fp_solicitado": float(fp_obj_sel_form),
                        "fp_aplicado": fp_obj_sel_aplicado,
                        "q_sel": q_sel,
                        "coef_min": df_coef_k_min,
                        "coef_sel": df_coef_k_sel,
                        "q_min_df": df_q_condensadores_min,
                        "q_sel_df": df_q_condensadores_sel,
                        "figura": fig_compensacion,
                    }
                    st.session_state.pop("informe_reactiva_html", None)
                    st.rerun()

                resultado_compensacion = st.session_state.get(
                    "reactiva_compensacion"
                )
                if (
                    resultado_compensacion
                    and resultado_compensacion.get("version") != version_curva
                ):
                    resultado_compensacion = None
                    st.session_state.pop("reactiva_compensacion", None)
                return resultado_compensacion


            with st.container():
                c1, c2 = st.columns([.4,.6])
                with c1:
                    st.subheader('RESUMEN COMPENSACIÓN')
                    c_aviso, c_penalizacion = st.columns([2, 1])
                    if (
                        pd.notna(total_penalizacion_reactiva)
                        and total_penalizacion_reactiva > 0
                    ):
                        c_aviso.warning(
                            "Se ha detectado una penalización por energía reactiva "
                            f"de {formato_euros(total_penalizacion_reactiva)} en el "
                            f"periodo {fecha_inicio_reactiva:%d/%m/%Y} – "
                            f"{fecha_fin_reactiva:%d/%m/%Y}.",
                            icon="⚠️",
                        )
                    color_valor_penalizacion = (
                        "#b91c1c"
                        if total_penalizacion_reactiva > 0
                        else "#15803d"
                    )
                    with c_penalizacion:
                        st.markdown(
                            "<style>"
                            ":is([data-testid='column'],[data-testid='stColumn']):has("
                            ".valor-penalizacion-reactiva):not(:has("
                            ":is([data-testid='column'],[data-testid='stColumn']) "
                            ".valor-penalizacion-reactiva)) "
                            "[data-testid='stMetricValue'],"
                            ":is([data-testid='column'],[data-testid='stColumn']):has("
                            ".valor-penalizacion-reactiva):not(:has("
                            ":is([data-testid='column'],[data-testid='stColumn']) "
                            ".valor-penalizacion-reactiva)) "
                            "[data-testid='stMetricValue'] *"
                            f"{{color:{color_valor_penalizacion} !important;}}"
                            "</style>"
                            "<span class='valor-penalizacion-reactiva' "
                            "style='display:none'></span>",
                            unsafe_allow_html=True,
                        )
                        st.metric(
                            'Penalización reactiva (€)',
                            formato_euros(total_penalizacion_reactiva),
                        )

                    c31,c32,c33=st.columns(3)
                    with c31:
                        st.metric('Factor de potencia mínimo', fp_min)
                    with c32:
                        st.metric('Factor de potencia medio', fp_med)
                    with c33:
                        st.metric('Factor de potencia máximo', fp_max)
                    resultado_compensacion = gestionar_form_compensacion()
                    if resultado_compensacion:
                        c31, c32, c33 = st.columns(3)
                        with c31:
                            st.metric(
                                ":yellow[Potencia mínima de compensación (kVAr)]",
                                formato_numero_es(
                                    resultado_compensacion["q_min"], 2
                                ),
                            )
                        with c32:
                            st.metric(
                                ":orange[Potencia mínima recomendada (kVAr)]",
                                formato_numero_es(
                                    resultado_compensacion["q_min_margen"], 2
                                ),
                                delta=(
                                    "cos φ "
                                    + formato_numero_es(
                                        resultado_compensacion[
                                            "fp_min_margen"
                                        ],
                                        3,
                                    )
                                ),
                            )
                        with c33:
                            st.metric(
                                ":green[Potencia de condensadores (kVAr)]",
                                formato_numero_es(
                                    resultado_compensacion["q_sel"], 2
                                ),
                                delta=(
                                    "cos φ "
                                    + formato_numero_es(
                                        resultado_compensacion["fp_aplicado"],
                                        3,
                                    )
                                ),
                            )
                        if (
                            resultado_compensacion["fp_aplicado"]
                            > resultado_compensacion["fp_solicitado"]
                        ):
                            st.info(
                                "El cos φ deseado se ha ajustado a "
                                f"{resultado_compensacion['fp_aplicado']:.3f} "
                                "porque no puede ser inferior al alcanzado con "
                                "la potencia mínima recomendada."
                            )
                with c2:
                    if resultado_compensacion:
                        st.plotly_chart(
                            resultado_compensacion["figura"],
                            use_container_width=True,
                        )

            alto_df_fmt = 460
            st.markdown(
                """
                <style>
                .tabla-reactiva-html {
                    overflow-x: auto;
                    margin-bottom: 1rem;
                }
                .tabla-reactiva-html table {
                    width: 100%;
                    border-collapse: collapse;
                    font-size: 0.9rem;
                }
                .tabla-reactiva-html th,
                .tabla-reactiva-html td {
                    padding: 0.35rem 0.5rem;
                    border-bottom: 1px solid rgba(128, 128, 128, 0.25);
                    text-align: right;
                }
                .tabla-reactiva-html th:first-child,
                .tabla-reactiva-html td:first-child {
                    text-align: left;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )
            def mostrar_tabla_reactiva_html(df, decimales=None):
                tabla_html = df.copy()
                tabla_html.columns = tabla_html.columns.map(str)
                tabla_html.columns.name = None
                tabla_html.index.name = None
                if decimales is not None:
                    columnas_numericas = tabla_html.select_dtypes(
                        include=[np.number]
                    ).columns
                    tabla_html[columnas_numericas] = tabla_html[
                        columnas_numericas
                    ].round(decimales)
                st.markdown(
                    "<div class='tabla-reactiva-html'>"
                    f"{tabla_html.to_html(index=False, border=0)}"
                    "</div>",
                    unsafe_allow_html=True,
                )

            penalizacion_grafico = df_coste_excesos_reactiva[
                ["Mes", "Total"]
            ].copy()
            penalizacion_grafico["Total"] = pd.to_numeric(
                penalizacion_grafico["Total"],
                errors="coerce",
            ).fillna(0)
            graf_penalizacion_reactiva = px.bar(
                penalizacion_grafico,
                x="Mes",
                y="Total",
                labels={"Mes": "", "Total": "Penalización (€)"},
                color_discrete_sequence=["#C94C4C"],
            )
            graf_penalizacion_reactiva.update_traces(
                hovertemplate=(
                    "<b>%{x}</b><br>Penalización: %{y:.2f} €"
                    "<extra></extra>"
                )
            )
            graf_penalizacion_reactiva = aplicar_estilo(
                graf_penalizacion_reactiva
            )
            graf_penalizacion_reactiva.update_layout(
                height=430,
                xaxis_title="",
                showlegend=False,
                barcornerradius=8,
                title="",
            )

            with st.container():
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.subheader('FP Factor de Potencia')
                    st.markdown(
                        "<div class='tabla-reactiva-html'>"
                        f"{styler_fp.hide(axis='index').to_html()}"
                        "</div>",
                        unsafe_allow_html=True,
                    )
                with c2:
                    st.subheader('Penalización (€) por excesos de REACTIVA')
                    st.markdown(
                        "<div class='tabla-reactiva-html'>"
                        f"{styler_coste_exc.hide(axis='index').to_html()}"
                        "</div>",
                        unsafe_allow_html=True,
                    )
                with c3:
                    st.subheader("Evolución mensual de la penalización (€)")
                    st.plotly_chart(
                        graf_penalizacion_reactiva,
                        use_container_width=True,
                    )

            with st.container():
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.subheader('Consumos mensuales (kWh)')
                    mostrar_tabla_reactiva_html(
                        tabla_mensual_consumos_reactiva_fmt
                    )
                with c2:
                    st.subheader('Reactiva mensual (kVArh)')
                    mostrar_tabla_reactiva_html(df_reactiva_fmt)
                with c3:
                    st.subheader('Excesos de REACTIVA (kVArh)')
                    mostrar_tabla_reactiva_html(df_excesos_react_fmt)

            if resultado_compensacion:
                df_q_condensadores_min_fmt = formatear_tabla_consumos(
                    resultado_compensacion["q_min_df"],
                    columna_mes="Mes",
                    incluir_unidades=False,
                )
                df_q_condensadores_sel_fmt = formatear_tabla_consumos(
                    resultado_compensacion["q_sel_df"],
                    columna_mes="Mes",
                    incluir_unidades=False,
                )
                coef_min_mostrar = (
                    resultado_compensacion["coef_min"]
                    .copy()
                    .round(3)
                )
                coef_sel_mostrar = (
                    resultado_compensacion["coef_sel"]
                    .copy()
                    .round(3)
                )
                with st.container():
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.subheader("Coeficientes K MÍNIMO")
                        mostrar_tabla_reactiva_html(
                            coef_min_mostrar,
                            decimales=3,
                        )
                    with c2:
                        st.subheader("Coeficientes K SELECCIONADO")
                        mostrar_tabla_reactiva_html(
                            coef_sel_mostrar,
                            decimales=3,
                        )
                    with c3:
                        st.subheader("Potencia media demandada (kW)")
                        mostrar_tabla_reactiva_html(
                            df_potmed_qh_fmt
                        )

                with st.container():
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.subheader("Q (kVAr) COMPENSACIÓN MÍNIMA")
                        mostrar_tabla_reactiva_html(
                            df_q_condensadores_min_fmt,
                        )
                    with c2:
                        st.subheader("Q (kVAr) COMPENSACIÓN SELECCIONADA")
                        mostrar_tabla_reactiva_html(
                            df_q_condensadores_sel_fmt,
                        )

    with tab6:
        st.subheader("Informe de compensación", divider="rainbow")
        informe_base = st.session_state.get("reactiva_base_cache")
        informe_compensacion = st.session_state.get("reactiva_compensacion")

        if not informe_base:
            st.info(
                "Carga una curva con datos de reactiva para preparar el informe."
            )
        elif not informe_compensacion:
            st.info(
                "Pulsa «Calcular compensación» en la pestaña Reactiva antes "
                "de preparar el informe."
            )
        else:
            col_datos_informe, col_previa_informe = st.columns([0.38, 0.62])
            with col_datos_informe:
                st.caption(
                    "Completa los datos del cliente y del realizador. Estos "
                    "campos siguen el mismo esquema utilizado en Factura."
                )
                with st.container(border=True):
                    st.markdown("#### Datos del cliente y del suministro")
                    col_cliente, col_nif = st.columns([0.68, 0.32])
                    col_cliente.text_input(
                        "Cliente / Razón social",
                        key="reactiva_informe_cliente",
                    )
                    col_nif.text_input(
                        "NIF / CIF",
                        key="reactiva_informe_nif",
                    )
                    st.text_input(
                        "Dirección",
                        key="reactiva_informe_direccion",
                    )
                    col_cups, col_atr = st.columns([0.68, 0.32])
                    col_cups.text_input(
                        "CUPS",
                        key="reactiva_informe_cups",
                    )
                    col_atr.text_input(
                        "ATR",
                        value=str(st.session_state.get("atr_dfnorm", "")),
                        key="reactiva_informe_atr",
                    )

                with st.container(border=True):
                    st.markdown("#### Datos del informe")
                    col_autor, col_fecha = st.columns([0.60, 0.40])
                    col_autor.text_input(
                        "Realizado por",
                        key="reactiva_informe_realizado_por",
                    )
                    col_fecha.text_input(
                        "Fecha de realización",
                        value=pd.Timestamp.today().strftime("%d/%m/%Y"),
                        key="reactiva_informe_fecha",
                    )
                    st.text_input(
                        "Objeto del estudio",
                        value=(
                            "Analizar la penalización por energía reactiva y "
                            "dimensionar su compensación."
                        ),
                        key="reactiva_informe_objeto",
                    )

                with st.container(border=True):
                    st.markdown("#### Personalización")
                    logo_reactiva = st.file_uploader(
                        "Logo para el informe",
                        type=["png", "jpg", "jpeg"],
                        accept_multiple_files=False,
                        key="reactiva_informe_logo",
                    )
                    if logo_reactiva is not None:
                        st.image(logo_reactiva, width=180)

                preparar_informe_reactiva = st.button(
                    "Preparar informe",
                    type="primary",
                    use_container_width=True,
                    key="preparar_informe_reactiva",
                )

            with col_previa_informe:
                if preparar_informe_reactiva:
                    def figura_data_uri(figura, ancho=1100, alto=520):
                        try:
                            imagen = figura.to_image(
                                format="png",
                                width=ancho,
                                height=alto,
                                scale=1.5,
                            )
                            return (
                                "data:image/png;base64,"
                                + base64.b64encode(imagen).decode("ascii")
                            )
                        except Exception:
                            return ""

                    logo_data = ""
                    if logo_reactiva is not None:
                        subtipo = (
                            "jpeg"
                            if logo_reactiva.type == "image/jpeg"
                            else "png"
                        )
                        logo_data = (
                            f"data:image/{subtipo};base64,"
                            + base64.b64encode(
                                logo_reactiva.getvalue()
                            ).decode("ascii")
                        )

                    df_fp_informe = informe_base["fp"].copy()
                    df_fp_informe.columns.name = None
                    df_excesos_informe = informe_base["excesos"].copy()
                    df_excesos_informe.columns.name = None
                    for tabla in (df_fp_informe, df_excesos_informe):
                        for columna in tabla.columns:
                            if columna != "Mes":
                                tabla[columna] = pd.to_numeric(
                                    tabla[columna],
                                    errors="coerce",
                                ).round(2)

                    penalizacion_informe = float(
                        informe_base["costes"]["Total"].sum()
                    )
                    fp_informe = informe_base["fp"]
                    fp_medio_informe = float(fp_informe["Total"].mean())
                    periodo_informe = (
                        f"{st.session_state.df_norm['fecha_hora'].min():%d/%m/%Y}"
                        " – "
                        f"{st.session_state.df_norm['fecha_hora'].max():%d/%m/%Y}"
                    )
                    contexto_informe = {
                        "logo": logo_data,
                        "cliente": escape(st.session_state.get(
                            "reactiva_informe_cliente", ""
                        )),
                        "nif": escape(st.session_state.get(
                            "reactiva_informe_nif", ""
                        )),
                        "direccion": escape(st.session_state.get(
                            "reactiva_informe_direccion", ""
                        )),
                        "cups": escape(st.session_state.get(
                            "reactiva_informe_cups", ""
                        )),
                        "atr": escape(st.session_state.get(
                            "reactiva_informe_atr", ""
                        )),
                        "realizado_por": escape(st.session_state.get(
                            "reactiva_informe_realizado_por", ""
                        )),
                        "fecha_realizacion": escape(st.session_state.get(
                            "reactiva_informe_fecha", ""
                        )),
                        "objeto": escape(st.session_state.get(
                            "reactiva_informe_objeto", ""
                        )),
                        "periodo": periodo_informe,
                        "penalizacion": formato_euros(
                            penalizacion_informe
                        ),
                        "mensaje_penalizacion": (
                            "Existe coste evitable asociado al exceso de "
                            "energía reactiva."
                            if penalizacion_informe > 0
                            else "No se estima penalización en el periodo."
                        ),
                        "q_minima": (
                            f"{formato_numero_es(informe_compensacion['q_min'], 2)} "
                            "kVAr"
                        ),
                        "q_recomendada": (
                            f"{formato_numero_es(informe_compensacion['q_min_margen'], 2)} "
                            "kVAr"
                        ),
                        "q_propuesta": (
                            f"{formato_numero_es(informe_compensacion['q_sel'], 2)} "
                            "kVAr"
                        ),
                        "fp_medio": formato_numero_es(fp_medio_informe, 3),
                        "fp_margen": formato_numero_es(
                            informe_compensacion["fp_min_margen"], 3
                        ),
                        "fp_propuesto": formato_numero_es(
                            informe_compensacion["fp_aplicado"], 3
                        ),
                        "grafico_compensacion": figura_data_uri(
                            informe_compensacion["figura"]
                        ),
                        "grafico_penalizacion": figura_data_uri(
                            graf_penalizacion_reactiva
                        ),
                        "tabla_fp": df_fp_informe.to_html(
                            index=False,
                            border=0,
                            na_rep="—",
                        ),
                        "tabla_excesos": df_excesos_informe.to_html(
                            index=False,
                            border=0,
                            na_rep="—",
                        ),
                    }
                    ruta_plantilla = (
                        Path(__file__).resolve().parent.parent
                        / "templates"
                        / "informe_reactiva.html"
                    )
                    entorno = Environment(
                        loader=FileSystemLoader(str(ruta_plantilla.parent))
                    )
                    html_informe_reactiva = entorno.get_template(
                        ruta_plantilla.name
                    ).render(**contexto_informe)
                    st.session_state.informe_reactiva_html = (
                        html_informe_reactiva
                    )

                html_informe_reactiva = st.session_state.get(
                    "informe_reactiva_html"
                )
                if html_informe_reactiva:
                    st.markdown("#### Vista previa")
                    st.components.v1.html(
                        html_informe_reactiva,
                        height=980,
                        scrolling=True,
                    )
                    nombre_cliente = re.sub(
                        r"[^A-Za-z0-9._-]+",
                        "_",
                        st.session_state.get(
                            "reactiva_informe_cliente", ""
                        ),
                    ).strip("._") or "cliente"
                    st.download_button(
                        "Descargar informe HTML",
                        data=html_informe_reactiva.encode("utf-8"),
                        file_name=(
                            f"informe_compensacion_reactiva_{nombre_cliente}.html"
                        ),
                        mime="text/html; charset=utf-8",
                        use_container_width=True,
                    )
                else:
                    st.info(
                        "La vista previa aparecerá aquí al preparar el informe."
                    )






