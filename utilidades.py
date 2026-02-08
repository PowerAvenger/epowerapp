import streamlit as st
import datetime
from backend_comun import autenticar_google_sheets, carga_total_sheets
from backend_escalacv import leer_json

def generar_menu():
    with st.sidebar:
        st.title('**:rainbow[TOTALPOWER]** :orange[e]PowerAPP©')
        st.image('images/banner.png')
        st.caption("Copyright 2024 by Jose Vidal :ok_hand:")
        url_bluesky = "https://bsky.app/profile/poweravenger.bsky.social"
        #st.markdown(f"Deja tus comentarios y propuestas en mi perfil de [Linkedin]({url_linkedin}) - ¡Sígueme en [Bluesky]({url_bluesky})!")
        url_linkedin = 'https://www.linkedin.com/posts/josefvidalsierra_epowerapp-totalpower-activity-7382675731379830784-ObeG/?utm_source=share&utm_medium=member_desktop&rcm=ACoAAFYBwa4BRZN7ghU77azb6YGy123gZvYnqoE'
        st.markdown(f"Deja tus impresiones y valoraciones en [Linkedin]({url_linkedin}).")

        st.page_link('epowerapp.py', label = 'Bienvenida', icon = "🙌")
        st.page_link('pages/curvadecarga.py', label = 'Curvas de carga', icon = "🕒")
        st.page_link('pages/opt2.py', label = 'Término de Potencia', icon = "🎯")
        st.page_link('pages/telemindex.py', label = 'Telemindex', icon = "📈")
        st.page_link('pages/simulindex.py', label = 'Simulindex', icon = "🔮")
        st.page_link('pages/fijovspvpc.py', label = 'FijovsPVPC', icon = "⚖️")
        st.page_link('pages/balkoning_solar.py', label = 'Balkoning Solar', icon = "🏊‍♂️")
        st.page_link('pages/escalacv.py', label = 'Escala CV', icon = "📊")
        st.page_link('pages/excedentes.py', label = 'Excedentes', icon = "💰")
        st.page_link('pages/demanda.py', label = 'Demanda', icon = "🏭")
        st.page_link('pages/redata_potgen.py', label = 'Tecnologías de generación', icon = "⚡️")
        st.page_link('pages/mibgas.py', label = 'Gas & Furious', icon = "🔥")
        st.page_link('pages/marginales.py', label = 'Marginales', icon = "🔀")
        st.sidebar.header('', divider='rainbow')


def init_app():
    # General
    if 'client' not in st.session_state:
        st.session_state.client = autenticar_google_sheets()

def init_app_index():
    # Para TELEMINDEX Y SIMULINDEX
    if 'rango_temporal' not in st.session_state:
        st.session_state.rango_temporal = 'Selecciona un rango de fechas'   
    if 'año_seleccionado' not in st.session_state:
        st.session_state.año_seleccionado = 2026
    if 'mes_seleccionado' not in st.session_state: 
        st.session_state.mes_seleccionado = 'enero'
    if 'ultima_fecha_sheets' not in st.session_state or 'df_sheets' not in st.session_state:
        #sheet_id = st.secrets['SHEET_INDEX_ID']
        #carga_rapida_sheets()
        carga_total_sheets()

    if 'dias_seleccionados' not in st.session_state:
        #st.session_state.dia_seleccionado = st.session_state.ultima_fecha_sheets
        if 'ultima_fecha_sheets' not in st.session_state:
            ultima_fecha = datetime.date(2026,1,1)
        else:
            ultima_fecha = st.session_state.ultima_fecha_sheets
        if isinstance(ultima_fecha, datetime.datetime):
            ultima_fecha = ultima_fecha.date()
        inicio_rango = ultima_fecha
        st.session_state.dias_seleccionados = (inicio_rango, ultima_fecha)
    #else:
    #    if not isinstance(st.session_state.dias_seleccionados, tuple) or len(st.session_state.dias_seleccionados) != 2:
    #        ultima_fecha = st.session_state.ultima_fecha_sheets
    #        inicio_rango = ultima_fecha - datetime.timedelta(days=5)
    #        st.session_state.dias_seleccionados = (inicio_rango, ultima_fecha)

    

    if 'margen' not in st.session_state: 
        st.session_state.margen = 0
    if 'texto_precios' not in st.session_state:
        if 'ultima_fecha_sheets' not in st.session_state:
            ultima_fecha = datetime.date(2026,1,1)
        else:
            ultima_fecha = st.session_state.ultima_fecha_sheets
        st.session_state.texto_precios = f'Día seleccionado: {ultima_fecha}'


def init_app_json_escalacv():
    """
    Inicializa los datos OMIE (SPOT, SSAA o ambos combinados)
    y los guarda en st.session_state para uso compartido entre páginas.
    """
    
    #CODIGO ORIGINAL DE escalacv.py-----------------------------------------------------------------------------
    CREDENTIALS = st.secrets['GOOGLE_SHEETS_CREDENTIALS']
    #componente = st.session_state.get('componente', 'SPOT')

    if st.session_state.get('componente', 'SPOT') == 'SPOT':
        FILE_ID = st.secrets['FILE_ID_SPOT']
        datos_total, fecha_ini, fecha_fin = leer_json(FILE_ID, CREDENTIALS)

    elif st.session_state.get('componente', 'SPOT') == 'SSAA':
        FILE_ID = st.secrets['FILE_ID_SSAA']
        datos_total, fecha_ini, fecha_fin = leer_json(FILE_ID, CREDENTIALS)

    else:
        # 🔹 Caso combinado (SPOT + SSAA)
        FILE_ID_SPOT = st.secrets['FILE_ID_SPOT']
        FILE_ID_SSAA = st.secrets['FILE_ID_SSAA']
        datos_spot, fecha_ini_spot, fecha_fin_spot = leer_json(FILE_ID_SPOT, CREDENTIALS)
        datos_ssaa, fecha_ini_ssaa, fecha_fin_ssaa = leer_json(FILE_ID_SSAA, CREDENTIALS)

        datos_spot = datos_spot.reset_index()
        datos_ssaa = datos_ssaa.reset_index()

        datos_total = (
            datos_spot[['datetime', 'value']].rename(columns={'value': 'value_spot'})
            .merge(
                datos_ssaa[['datetime', 'value']].rename(columns={'value': 'value_ssaa'}),
                on='datetime',
                how='inner'
            )
        )
        datos_total['value'] = datos_total['value_spot'] + datos_total['value_ssaa']
        datos_total['fecha'] = datos_total['datetime'].dt.date
        datos_total['hora'] = datos_total['datetime'].dt.hour
        datos_total['dia'] = datos_total['datetime'].dt.day
        datos_total['mes'] = datos_total['datetime'].dt.month
        datos_total['año'] = datos_total['datetime'].dt.year
        datos_total.set_index('datetime', inplace=True)

        fecha_ini = datos_total['fecha'].min()
        fecha_fin = datos_total['fecha'].max()



    # 💾 Guardar todo en sesión para reuso
    st.session_state.datos_total_escalacv = datos_total
    st.session_state.fecha_ini_escalacv = fecha_ini
    st.session_state.fecha_fin_escalacv = fecha_fin

 

    
    
    
