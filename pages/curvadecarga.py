import streamlit as st
import numpy as np
import pandas as pd
from backend_curvadecarga import (
    normalize_curve_simple, 
    graficar_curva_horaria, graficar_diario_apilado, graficar_mensual_apilado, graficar_queso_periodos, 
    graficar_media_horaria, graficar_media_horaria_combinada, graficar_boxplot_horario,
    graficar_neteo_horario, graficar_neteo_mensual
    )
from utilidades import generar_menu

if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')

generar_menu()

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
                    ("2.0", "3.0", "6.1"),
                    index=0
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

  

if normalizar and uploaded:    
    try:
        #df_in, df_norm, msg_unidades, flag_periodos_en_origen, df_periodos, frec = normalize_curve_simple(uploaded, origin=uploaded.name if hasattr(uploaded, "name") else uploaded)

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
        

        if frec =='QH':
            # Agregar cada 4 muestras por hora
            # Agrupar a nivel horario (suma de los 4 cuartos horarios)
            df_norm_h = (
                df_norm.groupby(["fecha", "hora"], as_index=False)
                .agg({
                    "consumo_neto_kWh": "sum",
                    "vertido_neto_kWh": "sum",
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
            df_norm_h = df_norm[["fecha_hora", "fecha", "hora","consumo_neto_kWh", "vertido_neto_kWh", "periodo", "tipo_dia"]].copy()

        
        consumototalhorario= df_norm_h['consumo_neto_kWh'].sum()
        print(f'consumo total df_norm_h: {consumototalhorario}')
        
        st.session_state.df_norm = df_norm
        st.session_state.atr_dfnorm = atr_dfnorm
        st.session_state.df_norm_h = df_norm_h
        st.session_state.frec = frec
        st.session_state.df_in = df_in
        st.session_state.consumo_total=consumo_total
        st.session_state.vertido_total=vertido_total
        st.session_state.consumo_neto=consumo_neto
        st.session_state.vertido_neto=vertido_neto
        # Obtener fechas mínima y máxima del df_norm_h y guardar para telemindex
        fecha_ini = df_norm["fecha"].min()
        fecha_fin = df_norm["fecha"].max()
        st.session_state.rango_curvadecarga = (fecha_ini, fecha_fin)

        print('df norm horaria')
        print(df_norm_h)

    except Exception as e:
        zona_mensajes.error(f"❌ Error al normalizar: {e}")
        st.stop()

else:
    zona_mensajes.info("⬆️ Sube un archivo CSV o Excel para comenzar.")





if st.session_state.get("df_norm") is not None:
    st.sidebar.markdown(f'Peaje actualmente seleccionado: **:orange[{st.session_state.atr_dfnorm}]**')
    st.sidebar.markdown(f'Resolución temporal de la curva: **:orange[{st.session_state.frec}]**')
    
    tab1, tab2, tab3 = st.tabs(['Resumen', 'Perfiles Horarios', 'Autoconsumo'])

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
            st.dataframe(st.session_state.df_norm, height=altura_df)
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
            with c33:
                #st.subheader("Resumen datos")
                st.metric("Consumo neteo KWh", f"{st.session_state.consumo_neto:,.0f}".replace(",", "."))
                st.metric("Vertido neteo KWh", f"{st.session_state.vertido_neto:,.0f}".replace(",", "."))


        # --- Gráfico ---

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
            #st.subheader("Medias horarias")
            #graf_medias_horarias=graficar_media_horaria(st.session_state.df_norm)
            #st.plotly_chart(graf_medias_horarias, use_container_width=True)
        
        c1,c2,c3=st.columns([.4,.3,.3])
        with c1:
            graf_diario = graficar_diario_apilado(st.session_state.df_norm_h)
            st.plotly_chart(graf_diario, use_container_width=True)
        with c2:
            graf_mensual = graficar_mensual_apilado(st.session_state.df_norm_h)
            st.plotly_chart(graf_mensual, use_container_width=True)
        with c3:
            graf_medias_horarias_total=graficar_media_horaria('Todos', ymax = None)
            st.plotly_chart(graf_medias_horarias_total, use_container_width=True)    
            
            
    with tab2:
        
        graf_medias_horarias_combinadas, ymax = graficar_media_horaria_combinada()
        #graf = graficar_media_horaria_combinada_2()
        graf_medias_horarias_total=graficar_media_horaria('Todos', ymax)
        graf_medias_horarias_lab=graficar_media_horaria('L-V',ymax)
        graf_medias_horarias_ffss=graficar_media_horaria('FS', ymax)

        graf_medias_horarias_total_ranking = graficar_media_horaria('Todos', ymax, ordenar=True)
        graf_medias_horarias_lab_ranking = graficar_media_horaria('L-V', ymax, ordenar=True)
        graf_medias_horarias_ffss_ranking = graficar_media_horaria('FS', ymax, ordenar=True)

        graf_bigotes_total = graficar_boxplot_horario('Todos')
        graf_bigotes_lab = graficar_boxplot_horario('L-V')
        graf_bigotes_ffss = graficar_boxplot_horario('FS')

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.plotly_chart(graf_medias_horarias_total, use_container_width=True)
            st.plotly_chart(graf_medias_horarias_total_ranking, use_container_width=True)
            st.plotly_chart(graf_bigotes_total, use_container_width=True)
        with c2:
            st.plotly_chart(graf_medias_horarias_lab, use_container_width=True)
            st.plotly_chart(graf_medias_horarias_lab_ranking, use_container_width=True)
            st.plotly_chart(graf_bigotes_lab, use_container_width=True)
        with c3:
            st.plotly_chart(graf_medias_horarias_ffss, use_container_width=True)
            st.plotly_chart(graf_medias_horarias_ffss_ranking, use_container_width=True)
            st.plotly_chart(graf_bigotes_ffss, use_container_width=True)
        with c4:
            st.plotly_chart(graf_medias_horarias_combinadas, use_container_width=True)
            

    with tab3:
        graf_horario_neteo = graficar_neteo_horario(st.session_state.df_norm_h, st.session_state.frec)
        st.plotly_chart(graf_horario_neteo, use_container_width=True)

        c1,c2,c3 = st.columns(3)   
        with c1:
            graf_mensual_neteo = graficar_neteo_mensual(st.session_state.df_norm_h)
            st.plotly_chart(graf_mensual_neteo)

    # --- Descarga ---
    csv_bytes = st.session_state.df_norm.reset_index().to_csv(index=False, sep=";").encode("utf-8")
    if not st.session_state.get('usuario_autenticado', False):
        habilitar_descarga = False
        #st.sidebar.download_button("⬇️ Descargar CSV normalizado", csv_bytes, "curva_normalizada.csv", "text/csv", disabled=True)
    else:
        habilitar_descarga = True
        #st.sidebar.download_button("⬇️ Descargar CSV normalizado", csv_bytes, "curva_normalizada.csv", "text/csv", disabled=False)
    st.sidebar.download_button("⬇️ Descargar CSV normalizado", csv_bytes, "curva_normalizada.csv", "text/csv", disabled=not habilitar_descarga, use_container_width=True)