import streamlit as st
import numpy as np
import pandas as pd
from backend_curvadecarga import (normalize_curve_simple, procesar_curva_completa,
    graficar_curva_horaria, graficar_diario_apilado, graficar_mensual_apilado, graficar_queso_periodos, 
    graficar_media_horaria, graficar_media_horaria_combinada,
    graficar_neteo_horario,
    )
from utilidades import generar_menu

if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')


generar_menu()

#if "curva_procesada" not in st.session_state:
#    st.session_state.curva_procesada = False
if "curva_normalizada" not in st.session_state:
    st.session_state.curva_normalizada = False
if "atr_dfnorm_ui" not in st.session_state:
    st.session_state.atr_dfnorm_ui = '2.0'

# ===============================
#  Interfaz Streamlit
# ===============================

with st.sidebar:
    st.title("⚡:rainbow[PowerLoader]⚡")
    st.caption("Lee CSV/Excel, detecta columnas y normaliza horas al rango 0–23 del mismo día. Añade columnas adicionales.")
    if not st.session_state.get('usuario_autenticado', False):
        st.warning("🔒 Este módulo es solo para usuarios premium. Lo que estás viendo es un fichero de ejemplo")
        uploaded = f"curvas/qh anual demo.csv" #es la --> qh 30 con aut anual Carles ES0031--01HS.csv
    else:
        uploaded = st.file_uploader("📂 Sube un archivo CSV o Excel", type=["csv", "xlsx"])
    
    st.selectbox(
        "Peaje de acceso",
        ("2.0", "3.0", "6.1"),
        #index=0,
        key="atr_dfnorm_ui"
    )

    ejecutar = st.button(
        "🔄 Normalizar curva",
        type="primary",
        use_container_width=True
    )
        
    zona_mensajes = st.sidebar.empty()
    zona_mensajes2 = st.sidebar.empty()
    zona_mensajes3 = st.sidebar.empty()
    

# Inicializa el estado si no existe
if "df_norm" not in st.session_state:
    st.session_state.df_norm = None
if "df_norm_h" not in st.session_state:
    st.session_state.df_norm = None  
if "df_in" not in st.session_state:
    st.session_state.df_in = None
if 'frec' not in st.session_state:
    st.session_state.frec = 'QH'      


if uploaded and ejecutar:

    try:
        resultado = procesar_curva_completa(uploaded, st.session_state.atr_dfnorm_ui)

        print('resultado obtenido')

        for k, v in resultado.items():
            st.session_state[k] = v

        st.session_state.curva_normalizada = True

        zona_mensajes.success("✅ Curva normalizada correctamente")

        if resultado.get("msg_unidades"):
            zona_mensajes2.info(resultado["msg_unidades"], icon="ℹ️")

    except Exception as e:
        zona_mensajes.error(f"❌ Error al normalizar: {e}")
        st.stop()


if not st.session_state.curva_normalizada:
    zona_mensajes.info("⬆️ Sube un archivo, selecciona el peaje y pulsa *Normalizar curva*")
        

        
st.session_state



#if st.session_state.get('df_norm') is not None:
if (
    st.session_state.get("curva_normalizada", False)
    and st.session_state.get("df_norm") is not None
    and st.session_state.get("atr_dfnorm") in ("2.0", "3.0", "6.1")
):

    st.sidebar.markdown(f'Peaje de acceso de la curva: **:orange[{st.session_state.atr_dfnorm}]**')
    st.sidebar.markdown(f'Resolución temporal de la curva: **:orange[{st.session_state.freq}]**')
    
    tab1, tab2, tab3 = st.tabs(['Resumen', 'Perfiles Horarios', 'Autoconsumo'])

    with tab1:
        altura_df = 300
        c1,c2,c3,c4,c5=st.columns([.35,.35,.1,.1,.1])
        with c1:
            # Visor del df in
            st.subheader("📄 Vista previa del archivo original")
            st.dataframe(st.session_state.df_in, height=altura_df)
        with c2:
            # Visor del df out
            st.subheader("📊 Tabla normalizada de datos")
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
            graf_horario = graficar_curva_horaria(st.session_state.df_norm, st.session_state.freq)
            st.plotly_chart(graf_horario, use_container_width=True)
            


        with c2:
            st.subheader("Consumo por periodos")
            graf_periodos=graficar_queso_periodos(st.session_state.df_norm)
            st.plotly_chart(graf_periodos, use_container_width=True)
            #st.subheader("Medias horarias")
            #graf_medias_horarias=graficar_media_horaria(st.session_state.df_norm)
            #st.plotly_chart(graf_medias_horarias, use_container_width=True)
        
        c1,c2,c3=st.columns([.4,.3,.3])
        with c1:
            graf_diario = graficar_diario_apilado(st.session_state.df_norm)
            st.plotly_chart(graf_diario, use_container_width=True)
        with c2:
            graf_mensual = graficar_mensual_apilado(st.session_state.df_norm)
            st.plotly_chart(graf_mensual, use_container_width=True)
        with c3:
            graf_medias_horarias_total=graficar_media_horaria('Todos', ymax = None)
            st.plotly_chart(graf_medias_horarias_total, use_container_width=True)    
            
            
    with tab2:
        
        graf_medias_horarias_combinadas, ymax = graficar_media_horaria_combinada()
        #graf = graficar_media_horaria_combinada_2()
        graf_medias_horarias_total=graficar_media_horaria('Todos', ymax = None)
        graf_medias_horarias_lab=graficar_media_horaria('L-V',ymax)
        graf_medias_horarias_ffss=graficar_media_horaria('FS', ymax)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.plotly_chart(graf_medias_horarias_total, use_container_width=True)
        with c2:
            st.plotly_chart(graf_medias_horarias_lab, use_container_width=True)
        with c3:
            st.plotly_chart(graf_medias_horarias_ffss, use_container_width=True)
        with c4:
            st.plotly_chart(graf_medias_horarias_combinadas, use_container_width=True)
            

    with tab3:
        graf_horario_neteo = graficar_neteo_horario(st.session_state.df_norm, st.session_state.frec)
        st.plotly_chart(graf_horario_neteo, use_container_width=True)

    # --- Descarga ---
    csv_bytes = st.session_state.df_norm.reset_index().to_csv(index=False, sep=";").encode("utf-8")
    if not st.session_state.get('usuario_autenticado', False):
        st.sidebar.download_button("⬇️ Descargar CSV normalizado", csv_bytes, "curva_normalizada.csv", "text/csv", disabled=True)
    else:
        st.sidebar.download_button("⬇️ Descargar CSV normalizado", csv_bytes, "curva_normalizada.csv", "text/csv", disabled=False)