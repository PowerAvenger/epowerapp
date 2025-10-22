import streamlit as st
import datetime, pandas as pd
from backend_comun import autenticar_google_sheets, carga_rapida_sheets, carga_total_sheets, colores_precios

def generar_menu():
    with st.sidebar:
        st.title('**:rainbow[TOTALPOWER]** :orange[e]PowerAPP©')
        st.image('images/banner.png')
        st.caption("Copyright 2024 by Jose Vidal :ok_hand:")
        #url_apps = "https://powerappspy-josevidal.streamlit.app/"
        #st.write("Visita mi página de [ePowerAPPs](%s) con un montón de utilidades." % url_apps)
        #url_linkedin = "https://www.linkedin.com/posts/josefvidalsierra_epowerapps-spo2425-telemindex-activity-7281942697399967744-IpFK?utm_source=share&utm_medium=member_deskto"
        url_linkedin = 'https://www.linkedin.com/in/jfvidalsierra/'
        url_bluesky = "https://bsky.app/profile/poweravenger.bsky.social"
        #st.markdown(f"Deja tus comentarios y propuestas en mi perfil de [Linkedin]({url_linkedin}) - ¡Sígueme en [Bluesky]({url_bluesky})!")
        st.markdown(f"Deja tus comentarios y propuestas en mi perfil de [Linkedin]({url_linkedin})!")
        st.page_link('epowerapp.py', label = 'Bienvenida', icon = "🙌")
        st.page_link('pages/telemindex.py', label = 'Telemindex', icon = "📈")
        st.page_link('pages/simulindex.py', label = 'Simulindex', icon = "🔮")
        st.page_link('pages/fijovspvpc.py', label = 'FijovsPVPC', icon = "⚖️")
        st.page_link('pages/escalacv.py', label = 'Escala CV', icon = "📊")
        st.page_link('pages/excedentes.py', label = 'Excedentes', icon = "💰")
        st.page_link('pages/demanda.py', label = 'Demanda', icon = "🏭")
        st.page_link('pages/mibgas.py', label = 'Gas & Furious', icon = "🔥")
        st.page_link('pages/redata_potgen.py', label = 'Tecnologías de generación', icon = "⚡️")
        st.page_link('pages/marginales.py', label = 'Marginales', icon = "🔀")
        st.sidebar.header('', divider='rainbow')


def init_app():
    # General
    if 'client' not in st.session_state:
        st.session_state.client = autenticar_google_sheets()

def init_app_index():
    # Para TELEMINDEX Y SIMULINDEX
    if 'rango_temporal' not in st.session_state:
        st.session_state.rango_temporal = 'Selecciona un día'
    if 'año_seleccionado' not in st.session_state:
        st.session_state.año_seleccionado = 2025
    if 'mes_seleccionado' not in st.session_state: 
        st.session_state.mes_seleccionado = 'enero'
    if 'ultima_fecha_sheets' not in st.session_state or 'df_sheets' not in st.session_state:
        #sheet_id = st.secrets['SHEET_INDEX_ID']
        carga_rapida_sheets()
    if 'dia_seleccionado' not in st.session_state:
        st.session_state.dia_seleccionado = st.session_state.ultima_fecha_sheets
    else:
        if not isinstance(st.session_state.dia_seleccionado, (datetime.date, datetime.datetime)):
            try:
                st.session_state.dia_seleccionado = pd.to_datetime(st.session_state.dia_seleccionado).date()
            except Exception:
                st.session_state.dia_seleccionado = st.session_state.ultima_fecha_sheets
    if 'margen' not in st.session_state: 
        st.session_state.margen = 0
    if 'texto_precios' not in st.session_state:
        st.session_state.texto_precios = f'Día seleccionado: {st.session_state.ultima_fecha_sheets}'

    
    
    

    
    
    
