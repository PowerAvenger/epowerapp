import streamlit as st
import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from datetime import timedelta
import plotly.express as px
from backend_curvadecarga import (
    normalize_curve_simple, 
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
from backend_comun import formatear_tabla_consumos, formatear_columnas_tabla


        
from utilidades import generar_menu

if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')

generar_menu()

if 'zona_periodos_cdc' not in st.session_state:
    st.session_state.zona_periodos = 'peninsula'

# ===============================
#  Interfaz SIDEBAR
# ===============================

with st.sidebar:

    st.title("⚡:rainbow[PowerLoader]⚡")
    st.caption("Lee CSV/Excel, detecta columnas y normaliza horas al rango 0–23 del mismo día. Añade columnas adicionales.")

    if not st.session_state.get('usuario_autenticado', False):
        st.warning("🔒 Este módulo es solo para usuarios premium. Lo que estás viendo es un fichero de ejemplo")
        uploaded = f"curvas/qh anual demo.csv" #es la --> qh 30 con aut anual Carles ES0031--01HS.csv
        atr_dfnorm = '3.0'
        
    else:
        uploaded = st.file_uploader("📂 Sube un archivo CSV o Excel", type=["csv", "xlsx"], accept_multiple_files=True)
        #uploaded = st.file_uploader("📂 Sube un archivo CSV o Excel", type=["csv", "xlsx"])
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
        
    normalizar = st.button('Normalizar curva de carga', type='primary', use_container_width=True)
        
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
  

if normalizar and uploaded:    
    try:
        
        dfs_norm = []
        dfs_in = []

        if not isinstance(uploaded, list):
            uploaded = [uploaded]
        
        for file in uploaded:
            df_in_i, df_norm_i, msg_unidades, flag_periodos_en_origen, df_periodos, frec = normalize_curve_simple(file, origin=file.name if hasattr(file, "name") else file)
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

else:
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


    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(['Resumen', 'Perfiles Horarios', 'Autoconsumo', 'Comparaciones', 'Reactiva'])

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
            st.caption(f"Vista previa: primeras 1.000 filas de {total_filas_norm:,.0f}".replace(",", "."))
            st.dataframe(st.session_state.df_norm.head(1000), height=altura_df)
        with c3:
            # --- Resumen registros---
            st.subheader("Resumen de datos")
            c31,c32,c33 = st.columns(3)
            with c31:
                st.metric("Número de registros", f"{len(st.session_state.df_norm):,.0f}".replace(",", "."))
                st.metric("Fecha inicio", st.session_state.df_norm["fecha_hora"].min().strftime("%d.%m.%Y"))
                st.metric("Fecha final", st.session_state.df_norm["fecha_hora"].max().strftime("%d.%m.%Y"))
            with c32:
                #st.subheader("Resumen datos")
                st.metric("Consumo total KWh", f"{st.session_state.consumo_total:,.0f}".replace(",", "."))
                st.metric("Vertido total KWh", f"{st.session_state.vertido_total:,.0f}".replace(",", "."))
                st.metric("Reactiva total kVArh", f"{st.session_state.reactiva_total:,.0f}".replace(",", "."))
            with c33:
                #st.subheader("Resumen datos")
                st.metric("Consumo neteo KWh", f"{st.session_state.consumo_neto:,.0f}".replace(",", "."))
                st.metric("Vertido neteo KWh", f"{st.session_state.vertido_neto:,.0f}".replace(",", "."))

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
                    st.metric("Consumo total (kWh)", f"{total_consumo:,.0f}".replace(",", "."))
                    st.metric("Demanda total (kWh)", f"{total_demanda:,.0f}".replace(",", "."))
                    st.metric("Generación FV (kWh)", f"{total_genfv:,.0f}".replace(",", "."))
                with c22:
                    #st.metric("", "")
                    st.metric("Autoconsumo (kWh)", f"{total_autoconsumo:,.0f}".replace(",", "."))
                    st.metric("Vertido (kWh)", f"{total_vertido:,.0f}".replace(",", "."))
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
        df_reactiva = tabla_mensual_periodos(st.session_state.df_norm_h, columna_valor='reactiva_kVArh')
        df_excesos_reactiva = calcular_tabla_excesos_reactiva(tabla_mensual_consumos, df_reactiva, porcentaje_limite=0.33)
        df_fp = calcular_tabla_factor_potencia(tabla_mensual_consumos, df_reactiva)
        df_coste_excesos_reactiva = calcular_tabla_coste_excesos_reactiva(df_excesos_reactiva, df_fp)
        df_potmed_qh = calcular_tabla_potencia_media_qh(st.session_state.df_norm, columna_valor="consumo_neto_kWh")
        df_coef_k_min = calcular_tabla_coef_k(df_fp, st.session_state.fp_obj_min)
        df_coef_k_sel = calcular_tabla_coef_k(df_fp, st.session_state.fp_obj_sel)
        df_q_condensadores_min = calcular_tabla_q_condensadores(df_potmed_qh, df_coef_k_min)
        df_q_condensadores_sel = calcular_tabla_q_condensadores(df_potmed_qh, df_coef_k_sel)

        total_penalizacion_reactiva = df_coste_excesos_reactiva["Total"].sum()

        df_potmed_qh_fmt = formatear_tabla_consumos(df_potmed_qh, columna_mes="Mes", incluir_unidades=False)
        df_reactiva_fmt = formatear_tabla_consumos(df_reactiva, columna_mes="Mes", incluir_unidades=False)    
        df_excesos_react_fmt = formatear_tabla_consumos(df_excesos_reactiva, columna_mes="Mes", incluir_unidades=False)
        df_q_condensadores_min_fmt = formatear_tabla_consumos(df_q_condensadores_min, columna_mes="Mes", incluir_unidades=False)
        df_q_condensadores_sel_fmt = formatear_tabla_consumos(df_q_condensadores_sel, columna_mes="Mes", incluir_unidades=False)

        cols_periodos = [c for c in df_q_condensadores_min.columns if c.startswith("P")]
        q_min = (df_q_condensadores_min[cols_periodos].max().max())
        q_sel = (df_q_condensadores_sel[cols_periodos].max().max())
        
        #aplicamos colores a la tabla mensual de FPs
        df_fp_fmt = df_fp.copy()
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
        for col in df_fp_fmt.columns:
            if col != "Mes":
                df_fp_fmt[col] = df_fp_fmt[col].apply(
                    lambda x: "" if pd.isna(x) else f"{x:.2f}"
                )
        
        #calculamos penalizaciones y formateamos
        df_coste_excesos_reactiva_fmt = df_coste_excesos_reactiva.copy()
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
            return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
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

        from backend_curvadecarga import calcular_curva_q_dimensionamiento, graficar_compensacion_dimensionamiento
        cols_periodos = [c for c in df_fp.columns if c.startswith("P")]
        fp_min = df_fp[cols_periodos].min().min()
        cols_total = [c for c in df_fp.columns if c.startswith("T")]
        fp_med = round(df_fp[cols_total].mean() ,2)

        q_min_margen = q_min * (1 + st.session_state.margen_comp_min/100)
        

        df_curva_q = calcular_curva_q_dimensionamiento(df_fp=df_fp, df_potmed_qh=df_potmed_qh, fp_ini=fp_min, fp_fin=1.000, paso=0.001)
        # Calcular el cos φ alcanzable con esa potencia recomendada
        #df_posible = df_curva_q[df_curva_q["q_max"] <= q_min_margen]

        #if not df_posible.empty:
        #    fp_alcanzable_margen = df_posible["fp_obj"].max()
        #else:
        #    fp_alcanzable_margen = df_curva_q["fp_obj"].min()

        # Calcular fp alcanzable con la potencia recomendada con margen
        df_curva_aux = (
            df_curva_q[["fp_obj", "q_max"]]
            .dropna()
            .sort_values("q_max")
        )

        q_min_curva = df_curva_aux["q_max"].min()
        q_max_curva = df_curva_aux["q_max"].max()

        q_min_margen_clip = np.clip(q_min_margen, q_min_curva, q_max_curva)

        fp_min_margen = np.interp(
            q_min_margen_clip,
            df_curva_aux["q_max"],
            df_curva_aux["fp_obj"]
        )    
        
        fig_compensacion = graficar_compensacion_dimensionamiento(df_curva_q=df_curva_q, q_min=q_min, fp_min_rec=fp_min_margen, q_min_rec=q_min_margen, q_sel=q_sel, fp_ini = fp_min)


        with st.container():
            c1, c2 = st.columns([.4,.6])
            with c1:
                st.subheader('RESUMEN COMPENSACIÓN')
                c31,c32,c33=st.columns(3)
                with c31:
                    st.metric(f':red[Penalización reactiva (€)]', f"{total_penalizacion_reactiva:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                with c32:
                    st.metric('Factor de potencia mínimo', fp_min)
                with c33:
                    st.metric('Factor de potencia medio', fp_med)
                c31,c32,c33=st.columns(3)
                with c31:
                    st.number_input(f'Introduce el cos φ objetivo MÍNIMO', min_value=0.95, max_value=1.00, key = 'fp_obj_min', disabled=True)
                    st.metric(f':yellow[Potencia mínima de compensación (kVAr)]', f"{q_min:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), help='Potencia MÍNIMA en condensadores para compensar. Recomendable añadir un margen')
                with c32:
                    st.number_input('Introduce un margen en %', min_value=30, max_value=50, key = 'margen_comp_min')
                    
                    st.metric(f':orange[Potencia mínima recomendada (kVAr)]', f"{q_min_margen:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), delta=round(fp_min_margen,3), help='Potencia MÍNIMA RECOMENDADA en condensadores para compensar.')                              

                with c33:
                    fp_min_value = max(st.session_state.fp_obj_min+0.01,fp_min)
                    st.number_input('Introduce el cosdephi objetivo DESEADO', min_value=fp_min_value, max_value=1.00, key = 'fp_obj_sel')
                    with st.container(border=True):
                        st.metric(f':green[Potencia de condensadores (kVAr)]', f"{q_sel:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), )
            with c2:
                st.plotly_chart(fig_compensacion, use_container_width=True)
        
        alto_df_fmt = 460
        with st.container():
            c1, c2, c3 = st.columns(3)
            with c1:
                st.subheader('Tabla de FP Factor de Potencia')
                st.dataframe(styler_fp, use_container_width=True, hide_index=True, height=alto_df_fmt)
            with c2:
                st.subheader('Tabla de penalización (€) por excesos de REACTIVA')
                st.dataframe(styler_coste_exc, use_container_width=True, hide_index=True, height=alto_df_fmt) 

        with st.container():
            c1, c2, c3 = st.columns(3)
            with c1:
                st.subheader('Tabla de consumos mensuales (kWh)')
                st.dataframe(tabla_mensual_consumos_fmt, use_container_width=True, hide_index=True, height=alto_df_fmt)
            with c2:
                st.subheader('Tabla de reactiva mensual (kVArh)')
                st.dataframe(df_reactiva_fmt, use_container_width=True, hide_index=True, height=alto_df_fmt)
            with c3:
                st.subheader('Tabla de excesos de REACTIVA (kVArh)')
                st.dataframe(df_excesos_react_fmt, use_container_width=True, hide_index=True, height=alto_df_fmt)
                
        with st.container():    
            c1, c2, c3 = st.columns(3)
            with c1:
                st.subheader('Tabla de Coeficientes K MÍNIMO')
                st.dataframe(df_coef_k_min, use_container_width=True, hide_index=True, height=alto_df_fmt)

            with c2:
                st.subheader('Tabla de Potencia medida demandada (kW)')
                st.dataframe(df_potmed_qh_fmt, use_container_width=True, hide_index=True, height=alto_df_fmt)

            with c3:
                st.subheader('Tabla de Q (kVAr) COMPENSACIÓN A REALIZAR')
                st.dataframe(df_q_condensadores_min_fmt, use_container_width=True, hide_index=True, height=alto_df_fmt)

        with st.container():
            c1, c2, c3 = st.columns(3)
            with c1:
                st.subheader('Tabla de Coeficientes K SELECCIONADO')
                st.dataframe(df_coef_k_sel, use_container_width=True, hide_index=True, height=alto_df_fmt)

            with c2:
                st.subheader('Tabla de Potencia medida demandada (kW)')
                st.dataframe(df_potmed_qh_fmt, use_container_width=True, hide_index=True, height=alto_df_fmt)

            with c3:
                st.subheader('Tabla de Q (kVAr) COMPENSACIÓN A REALIZAR')
                st.dataframe(df_q_condensadores_sel_fmt, use_container_width=True, hide_index=True, height=alto_df_fmt)

       





