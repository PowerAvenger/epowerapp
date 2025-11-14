import streamlit as st
import numpy as np
import pandas as pd
from backend_curvadecarga import (normalize_curve_simple,graficar_curva,graficar_curva_neteo,graficar_media_horaria,graficar_queso_periodos)
from utilidades import generar_menu

if not st.session_state.get('usuario_autenticado', False):
    st.switch_page('epowerapp.py')

generar_menu()



# ===============================
#  Interfaz Streamlit
# ===============================


#st.set_page_config(page_title="Curvas de carga — Normalizador simple", layout="wide")

with st.sidebar:
    st.title("⚡ :orange[e]Powerapp :rainbow[PowerLoader] ⚡")
    st.caption("Lee CSV/Excel, detecta columnas y normaliza horas al rango 0–23 del mismo día. Añade columnas adicionales.")

    uploaded = st.file_uploader("📂 Sube un archivo CSV o Excel", type=["csv", "xlsx"])
    zona_mensajes = st.sidebar.empty()
    zona_mensajes2 = st.sidebar.empty()
    zona_mensajes3 = st.sidebar.empty()

    # Selector de modo
    #if uploaded:
    

# Inicializa el estado si no existe
if "df_norm" not in st.session_state:
    st.session_state.df_norm = None 
if "df_in" not in st.session_state:
    st.session_state.df_in = None      
if 'modo_agrupacion' not in st.session_state:
    st.session_state.modo_agrupacion = "Horario" 
if 'opcion_tipodia' not in st.session_state:
    st.session_state.opcion_tipodia = "TOTAL"

        

if uploaded:
    try:
        df_in, df_norm, msg_unidades, flag_periodos_en_origen, df_periodos = normalize_curve_simple(uploaded, origin=uploaded.name)
        #st.session_state.df_norm = df_norm

        #print('mensaje periodos')
        #print(msg_periodos)

        consumo_total=df_norm['consumo_kWh'].sum()
        vertido_total=df_norm['excedentes_kWh'].sum()
        consumo_neto=df_norm['consumo_neto_kWh'].sum()
        vertido_neto=df_norm['vertido_neto_kWh'].sum()


        zona_mensajes.success("✅ Curva normalizada correctamente")
        if msg_unidades != "":
            zona_mensajes2.info(msg_unidades, icon="ℹ️")

        if not flag_periodos_en_origen:
            msg_periodos = 'Cargados periodos desde fichero auxiliar. Seleccione modo 3P/6P'
            zona_mensajes3.warning(msg_periodos, icon="⚠️")
            tipo_periodo = st.sidebar.radio(
                    "Selecciona calendario tarifario:",
                    ("6P", "3P"),
                    index=0,
                    horizontal=True
                )
            col_periodo = "dh_6p" if "6" in tipo_periodo else "dh_3p"
            #si la columna periodo viene sin periodos (nan)
            if "periodo" not in df_norm.columns or df_norm["periodo"].isna().all():
                df_norm = df_norm.drop(columns=["periodo"])
                df_norm = pd.merge(
                    df_norm,
                    df_periodos[["fecha_hora", col_periodo]].rename(columns={col_periodo: "periodo"}),
                    on="fecha_hora",
                    how='left'
                )
            print('df_norm')
            print (df_norm)
            # Normalizar la columna 'periodo' a tipo texto limpio
            df_norm["periodo"] = df_norm["periodo"].astype(str).str.strip()

            # --- Rellenar periodos faltantes hacia abajo (para curvas QH) ---
            if df_norm["periodo"].isna().any() or (df_norm["periodo"] == "nan").any():
                df_norm["periodo"] = (
                    df_norm["periodo"]
                    .replace("nan", np.nan)
                    .ffill()        # rellena hacia abajo
                )

        else:
            msg_periodos = 'Cargados periodos desde fichero origen'
            zona_mensajes3.info(msg_periodos, icon="ℹ️")
        
        st.session_state.df_norm = df_norm
        st.session_state.df_in = df_in
        st.session_state.consumo_total=consumo_total
        st.session_state.vertido_total=vertido_total
        st.session_state.consumo_neto=consumo_neto
        st.session_state.vertido_neto=vertido_neto

    except Exception as e:
        zona_mensajes.error(f"❌ Error al normalizar: {e}")
        st.stop()

   
    
    


else:
    zona_mensajes.info("⬆️ Sube un archivo CSV o Excel para comenzar.")


if st.session_state.get('df_norm') is not None:

    st.sidebar.radio(
        "Selecciona el tipo de gráfico",
        ["Horario", "Diario", "Mensual"],
        horizontal=True,
        key='modo_agrupacion'
    )

    st.sidebar.radio(
        "Selecciona el tipo de día:",
        ["Todos", "L-V", "FS"],
        horizontal=True,
        key='opcion_tipodia'
    )

    altura_df = 300
    c1,c2,c3,c4,c5=st.columns([.35,.35,.1,.1,.1])
    with c1:
        # Visor del df in
        st.subheader("📄 Vista previa del archivo original (df_in)")
        st.dataframe(st.session_state.df_in, height=altura_df)
    with c2:
        # Visor del df out
        st.subheader("📊 DataFrame normalizado (df_norm)")
        st.dataframe(st.session_state.df_norm, height=altura_df)
    with c3:
        # --- Resumen registros---
        st.subheader("Resumen registros")
        st.metric("Número de registros", f"{len(st.session_state.df_norm):,.0f}".replace(",", "."))
        st.metric("Fecha inicio", st.session_state.df_norm["fecha_hora"].min().strftime("%d.%m.%Y"))
        st.metric("Fecha final", st.session_state.df_norm["fecha_hora"].max().strftime("%d.%m.%Y"))
    with c4:
        st.subheader("Resumen datos")
        st.metric("Consumo total KWh", f"{st.session_state.consumo_total:,.0f}".replace(",", "."))
        st.metric("Vertido total KWh", f"{st.session_state.vertido_total:,.0f}".replace(",", "."))
    with c5:
        st.subheader("Resumen datos")
        st.metric("Consumo neteo KWh", f"{st.session_state.consumo_neto:,.0f}".replace(",", "."))
        st.metric("Vertido neteo KWh", f"{st.session_state.vertido_neto:,.0f}".replace(",", "."))
    # --- Gráfico ---

    c1,c2=st.columns([.7,.3])
    with c1:
        st.subheader("Gráfico de consumo")
        # Mostrar gráfico
        graf_dfnorm = graficar_curva(st.session_state.df_norm)
        st.plotly_chart(graf_dfnorm, use_container_width=True)
        graf_dfneteo = graficar_curva_neteo(st.session_state.df_norm)
        st.plotly_chart(graf_dfneteo, use_container_width=True)
    with c2:
        st.subheader("Consumo por periodos")
        graf_periodos=graficar_queso_periodos(st.session_state.df_norm)
        st.plotly_chart(graf_periodos, use_container_width=True)
        st.subheader("Medias horarias")
        graf_medias_horarias=graficar_media_horaria(st.session_state.df_norm)
        st.plotly_chart(graf_medias_horarias, use_container_width=True)
        
        

    

    # --- Descarga ---
    csv_bytes = st.session_state.df_norm.reset_index().to_csv(index=False, sep=";").encode("utf-8")
    st.sidebar.download_button("⬇️ Descargar CSV normalizado", csv_bytes,
                       "curva_normalizada.csv", "text/csv")