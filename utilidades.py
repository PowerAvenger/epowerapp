import streamlit as st
import datetime
import pandas as pd
from backend_comun import autenticar_google_sheets, carga_total_sheets, cargar_componentes_csv
from backend_escalacv import leer_json
from backend_telemindex import COMPONENTES_SSAA_FORMULA, construir_df_rad3_manual, calcular_precios_atr, añadir_fnee


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
        st.page_link('pages/opt2_rdl.py', label = 'Optimización RDL 7/2026', icon = "🎯")
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
        st.session_state.df_sheets_old['fecha'] = pd.to_datetime(st.session_state.df_sheets_old['fecha']).dt.date
    if 'csv_componentes' not in st.session_state:
        import time
        t0 = time.perf_counter()
        st.session_state.csv_componentes = cargar_componentes_csv()
        t1 = time.perf_counter()
        print(f"Tiempo carga csv_componentes: {t1 - t0:.3f} s")

        df_csv = st.session_state.csv_componentes.copy()
        # ¡¡¡ ATENCIÓN: EL COMPONENTE DSV VIENE COMO PROMEDIO QH, Y NO COMO SUMA!!!
        #df_csv["dsv"] = df_csv["dsv"] * 4
        df_csv["ssaa"] = df_csv[COMPONENTES_SSAA_FORMULA].sum(axis=1)
        fecha_corte = df_csv["fecha"].max()
        # guardar para usar en la app
        st.session_state.ultima_fecha_csv = fecha_corte
        df_old = st.session_state.df_sheets_old.copy()
        df_old = df_old[df_old["fecha"] > fecha_corte]
        df_sheets_nuevo = pd.concat([df_csv, df_old], ignore_index=True)

        # --- 6. RELLENO MANUAL RAD3 POST C2 ---
        # máscara: solo fechas posteriores al CSV
        mask = df_sheets_nuevo["fecha"] > fecha_corte
        # construir df manual desde diccionario
        df_manual = construir_df_rad3_manual()
        # merge
        df_sheets_nuevo = df_sheets_nuevo.merge(
            df_manual,
            on=["año", "hora"],
            how="left",
            suffixes=("", "_manual")
        )
        # rellenar RAD3 SOLO post C2
        df_sheets_nuevo.loc[mask, "rad3"] = df_sheets_nuevo.loc[mask, "rad3_manual"]
        df_sheets_nuevo = df_sheets_nuevo.drop(columns=["rad3_manual"])

        # eliminar columnas sobrantes
        cols_drop = [c for c in df_sheets_nuevo.columns 
             if c.startswith("coste_") or c.startswith("precio_")]
        cols_drop += ["otros"]
        df_sheets_nuevo = df_sheets_nuevo.drop(columns=cols_drop, errors="ignore")

        # guardar en sesión
        st.session_state.df_sheets = df_sheets_nuevo
        st.session_state.df_sheets = añadir_fnee(st.session_state.df_sheets)

        # Inicialización de estados st.session componentes fórmula
        for key, default in {
            "desvios_apant": 1.0,
            #"cfg_srad": True,
            "margen_telemindex": 1.0,
            "cfg_margen_pos": "tm",
            "cfg_fnee": True,
            "cfg_fnee_pos": "perdidas",
            "cf_pct": 0.8
        }.items():
            if key not in st.session_state:
                st.session_state[key] = default

        # esto lo hacemos para que el sheets inicial tenga las columnas coste_ y precio_ para evol mensual por defecto
        if 'precios_calculados' not in st.session_state:

            st.session_state.df_sheets = calcular_precios_atr(
                st.session_state.df_sheets
            )
            st.session_state.precios_calculados = True

        print('df sheets NUEVO COMBO CSV Y SHEETS OLD')
        print(df_sheets_nuevo.columns)

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

 

def persist_widget(widget_func, label, *args, key=None, default=None, **kwargs):
    """
    Hace persistente un widget entre páginas usando:
    - key permanente: key
    - key temporal de widget: _key
    """

    if key is None:
        raise ValueError("persist_widget requiere argumento 'key'")

    temp_key = f"_{key}"

    # 1️⃣ Inicializar valor permanente solo la primera vez
    if key not in st.session_state:
        st.session_state[key] = default

    # 2️⃣ Sincronizar widget con valor permanente
    st.session_state[temp_key] = st.session_state[key]

    # 3️⃣ Crear widget con key temporal
    widget_func(
        label,
        *args,
        key=temp_key,
        on_change=lambda: st.session_state.update(
            {key: st.session_state[temp_key]}
        ),
        **kwargs
    )


    
    
