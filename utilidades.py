import streamlit as st
import datetime
from pathlib import Path
import pandas as pd
from backend_comun import autenticar_google_sheets, carga_total_sheets, cargar_componentes_csv, cargar_precios_snp_csv, calcular_precios_atr
from backend_escalacv import leer_json
from backend_telemindex import COMPONENTES_SSAA_FORMULA, construir_df_rad3_manual, añadir_fnee


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
        st.page_link('pages/factura.py', label = 'Análisis de facturas', icon = "🧾")
        st.page_link('pages/opt2.py', label = 'Término de Potencia', icon = "🎯")
        st.page_link('pages/opt2_rdl.py', label = 'Optimización RDL 7/2026', icon = "🎯")
        st.page_link('pages/telemindex.py', label = 'Telemindex', icon = "📈")
        st.page_link('pages/simulindex.py', label = 'Simulindex', icon = "🔮")
        st.page_link('pages/indicadores_mensuales.py', label = 'Indicadores mensuales', icon = "📋")
        st.page_link('pages/indicadores_anuales.py', label = 'Indicadores anuales', icon = "📅")
        st.page_link('pages/fijovspvpc.py', label = 'FijovsPVPC', icon = "⚖️")
        st.page_link('pages/balkoning_solar.py', label = 'Balkoning Solar', icon = "🏊‍♂️")
        st.page_link('pages/escalacv.py', label = 'Escala CV', icon = "📊")
        st.page_link('pages/excedentes.py', label = 'Excedentes', icon = "💰")
        st.page_link('pages/demanda.py', label = 'Demanda', icon = "🏭")
        st.page_link('pages/redata_potgen.py', label = 'Tecnologías de generación', icon = "⚡️")
        st.page_link('pages/mibgas.py', label = 'Gas & Furious', icon = "🔥")
        st.page_link('pages/marginales.py', label = 'Marginales', icon = "🔀")
        if (Path(__file__).resolve().parent / '.local_data' / 'epower_beta.sqlite3').exists():
            st.page_link('pages/bbdd_beta.py', label='BBDD beta local', icon='🗃️')
        st.sidebar.header('', divider='rainbow')


def init_app():
    # General
    if 'client' not in st.session_state:
        st.session_state.client = autenticar_google_sheets()



from backend_comun import aplicar_periodos_zona, recalcular_componentes_regulados


def aplicar_precio_snp(df, df_snp, zona):
    """Usa SphdemDD como bloque spot+SSAA y limita el resultado al C2 SNP."""
    if zona == "peninsula":
        return df.copy()
    if df_snp is None or df_snp.empty:
        raise ValueError("No está configurado el histórico df_precios_snp.csv.")

    columna = f"snp_{zona}"
    if columna not in df_snp.columns:
        raise ValueError(f"No encuentro la columna {columna} en df_precios_snp.csv.")

    precios = df_snp[["datetime", columna]].copy()
    precios["datetime"] = pd.to_datetime(precios["datetime"], errors="coerce")
    precios["año"] = precios["datetime"].dt.year
    precios["mes"] = precios["datetime"].dt.month
    precios["dia"] = precios["datetime"].dt.day
    precios["hora"] = precios["datetime"].dt.hour
    precios = precios.drop(columns="datetime")

    claves = ["año", "mes", "dia", "hora"]
    precios["ocurrencia_snp"] = precios.groupby(claves).cumcount()
    base = df.copy()
    base["ocurrencia_snp"] = base.groupby(claves).cumcount()
    resultado = base.merge(
        precios, on=[*claves, "ocurrencia_snp"], how="inner", validate="one_to_one"
    ).drop(columns="ocurrencia_snp")
    resultado["spot"] = resultado[columna]
    resultado["ssaa"] = 0.0
    return resultado.drop(columns=columna)

def actualizar_df_index_por_zona(forzar=False):
    """
    Recalcula st.session_state.df_sheets desde la base limpia
    aplicando la zona de periodos seleccionada.

    Flujo:
    1. Parte siempre de df_sheets_base_index
    2. Sustituye dh_6p según zona
    3. Recalcula PPCC, pérdidas y PyC
    4. Recalcula precios finales
    """

    zona = st.session_state.get("zona_periodos_index", "peninsula")

    if "df_sheets_base_index" not in st.session_state:
        return

    zona_ya_aplicada = st.session_state.get("zona_periodos_index_aplicada")

    if (
        not forzar
        and zona_ya_aplicada == zona
        and "df_sheets" in st.session_state
    ):
        return

    print(f"Recalculando indexados para zona: {zona}")

    # 1. Partimos siempre de la base limpia
    df_index = st.session_state.df_sheets_base_index.copy()

    # 2. En SNP sustituimos spot+SSAA por SphdemDD y excluimos el provisional ESIOS.
    if zona != "peninsula" and "csv_precios_snp" not in st.session_state:
        st.session_state.csv_precios_snp = cargar_precios_snp_csv()
    df_index = aplicar_precio_snp(
        df_index, st.session_state.get("csv_precios_snp"), zona
    )

    # 3. Aplicamos los periodos 3P y 6P de la zona.
    df_index = aplicar_periodos_zona(df_index, zona)

    # 4. Recalculamos componentes regulados que dependen de los periodos
    df_index = recalcular_componentes_regulados(df_index)

    # 5. Eliminamos precios/costes antiguos por seguridad
    cols_drop = [
        c for c in df_index.columns
        if c.startswith("coste_") or c.startswith("precio_")
    ]

    df_index = df_index.drop(columns=cols_drop, errors="ignore")

    # 6. Recalculamos precios finales
    df_index = calcular_precios_atr(df_index)

    # 7. Guardamos resultado activo
    st.session_state.df_sheets = df_index
    st.session_state.zona_periodos_index_aplicada = zona
    st.session_state.precios_calculados = True

    print(f"Zona aplicada correctamente: {zona}")



def init_app_index():
    # Para TELEMINDEX Y SIMULINDEX

    # =====================================================
    # 0. ESTADOS GENERALES
    # =====================================================
    if "zona_periodos_index" not in st.session_state:
        st.session_state.zona_periodos_index = "peninsula"

    if "zona_periodos_index_aplicada" not in st.session_state:
        st.session_state.zona_periodos_index_aplicada = None

    if "rango_temporal" not in st.session_state:
        st.session_state.rango_temporal = "Selecciona un rango de fechas"

    if "año_seleccionado" not in st.session_state:
        st.session_state.año_seleccionado = 2026

    if "mes_seleccionado" not in st.session_state:
        st.session_state.mes_seleccionado = "enero"

    # =====================================================
    # 1. CARGA SHEETS OLD
    # =====================================================
    if "ultima_fecha_sheets" not in st.session_state or "df_sheets_old" not in st.session_state:
        carga_total_sheets()
        st.session_state.df_sheets_old["fecha"] = pd.to_datetime(
            st.session_state.df_sheets_old["fecha"]
        ).dt.date

    # =====================================================
    # 2. CARGA CSV COMPONENTES + COMBO CON SHEETS OLD
    # =====================================================
    if "df_sheets_base_index" not in st.session_state:

        if "csv_componentes" not in st.session_state:
            import time
            t0 = time.perf_counter()

            st.session_state.csv_componentes = cargar_componentes_csv()

            t1 = time.perf_counter()
            print(f"Tiempo carga csv_componentes: {t1 - t0:.3f} s")

        df_csv = st.session_state.csv_componentes.copy()

        # ¡¡¡ ATENCIÓN: EL COMPONENTE DSV VIENE COMO PROMEDIO QH, Y NO COMO SUMA!!!
        # df_csv["dsv"] = df_csv["dsv"] * 4

        df_csv["ssaa"] = df_csv[COMPONENTES_SSAA_FORMULA].sum(axis=1)

        fecha_corte = df_csv["fecha"].max()

        # Guardar para usar en la app
        st.session_state.ultima_fecha_csv = fecha_corte

        df_old = st.session_state.df_sheets_old.copy()
        df_old = df_old[df_old["fecha"] > fecha_corte]

        df_sheets_nuevo = pd.concat(
            [df_csv, df_old],
            ignore_index=True
        )

        # =====================================================
        # 3. RELLENO MANUAL RAD3 POST C2
        # =====================================================
        mask = df_sheets_nuevo["fecha"] > fecha_corte

        df_manual = construir_df_rad3_manual()

        df_sheets_nuevo = df_sheets_nuevo.merge(
            df_manual,
            on=["año", "hora"],
            how="left",
            suffixes=("", "_manual")
        )

        df_sheets_nuevo.loc[mask, "rad3"] = df_sheets_nuevo.loc[mask, "rad3_manual"]

        df_sheets_nuevo = df_sheets_nuevo.drop(columns=["rad3_manual"])

        # =====================================================
        # 4. LIMPIEZA COLUMNAS SOBRANTES
        # =====================================================
        cols_drop = [
            c for c in df_sheets_nuevo.columns
            if c.startswith("coste_") or c.startswith("precio_")
        ]

        cols_drop += ["otros"]

        df_sheets_nuevo = df_sheets_nuevo.drop(
            columns=cols_drop,
            errors="ignore"
        )

        # =====================================================
        # 5. BASE LIMPIA INDEXADOS
        # =====================================================
        # Esta base mantiene los dh_6p originales de península.
        # Nunca se debe machacar con Canarias/Baleares/Ceuta/Melilla.
        st.session_state.df_sheets_base_index = df_sheets_nuevo.copy()
        st.session_state.df_sheets_base_index = añadir_fnee(
            st.session_state.df_sheets_base_index
        )

        print("df_sheets_base_index creado")
        print(st.session_state.df_sheets_base_index.columns)

    # =====================================================
    # 6. INICIALIZACIÓN DE ESTADOS DE COMPONENTES/FÓRMULA
    # =====================================================
    for key, default in {
        "desvios_apant": 0.0,
        # "cfg_srad": True,
        "margen_telemindex": 0.0,
        "cfg_margen_pos": "tm",
        "cfg_fnee": True,
        "cfg_fnee_pos": "perdidas",
        "cf_pct": 0.0,
    }.items():
        if key not in st.session_state:
            st.session_state[key] = default

    # =====================================================
    # 7. APLICAR ZONA Y CALCULAR PRECIOS
    # =====================================================
    actualizar_df_index_por_zona()

    # =====================================================
    # 8. ESTADO DÍAS SELECCIONADOS
    # =====================================================
    if "dias_seleccionados" not in st.session_state:

        if "ultima_fecha_sheets" not in st.session_state:
            ultima_fecha = datetime.date(2026, 1, 1)
        else:
            ultima_fecha = st.session_state.ultima_fecha_sheets

        if isinstance(ultima_fecha, datetime.datetime):
            ultima_fecha = ultima_fecha.date()

        inicio_rango = ultima_fecha
        st.session_state.dias_seleccionados = (inicio_rango, ultima_fecha)

    # =====================================================
    # 9. TEXTO PRECIOS
    # =====================================================
    if "texto_precios" not in st.session_state:

        if "ultima_fecha_sheets" not in st.session_state:
            ultima_fecha = datetime.date(2026, 1, 1)
        else:
            ultima_fecha = st.session_state.ultima_fecha_sheets

        st.session_state.texto_precios = f"Día seleccionado: {ultima_fecha}"

def init_app_index_old():
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
            "desvios_apant": 0.0,
            #"cfg_srad": True,
            "margen_telemindex": 0.0,
            "cfg_margen_pos": "tm",
            "cfg_fnee": True,
            "cfg_fnee_pos": "perdidas",
            "cf_pct": 0.0
        }.items():
            if key not in st.session_state:
                st.session_state[key] = default

        # esto lo hacemos para que el sheets inicial tenga las columnas coste_ y precio_ para evol mensual por defecto
        if 'precios_calculados' not in st.session_state:
            st.session_state.df_sheets = calcular_precios_atr(st.session_state.df_sheets)
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
    
    if "zona_periodos_index" not in st.session_state:
        st.session_state.zona_periodos_index = "peninsula"


def init_app_json_escalacv():
    """
    Inicializa los datos OMIE (SPOT, SSAA o ambos combinados)
    y los guarda en st.session_state para uso compartido entre páginas.
    """
    
    componente_actual = st.session_state.get('componente', 'SPOT')
    if (
        st.session_state.get('_escalacv_componente_cargado')
        == componente_actual
        and st.session_state.get('datos_total_escalacv') is not None
        and st.session_state.get('fecha_ini_escalacv') is not None
        and st.session_state.get('fecha_fin_escalacv') is not None
    ):
        return

    #CODIGO ORIGINAL DE escalacv.py-----------------------------------------------------------------------------
    CREDENTIALS = st.secrets['GOOGLE_SHEETS_CREDENTIALS']
    #componente = st.session_state.get('componente', 'SPOT')

    if st.session_state.get('componente', 'SPOT') == 'SPOT':
        FILE_ID = st.secrets['FILE_ID_SPOT']
        datos_total, fecha_ini, fecha_fin = leer_json(FILE_ID, CREDENTIALS)
        st.session_state._escalacv_datos_spot_general = datos_total

    elif st.session_state.get('componente', 'SPOT') == 'SSAA':
        FILE_ID = st.secrets['FILE_ID_SSAA']
        datos_total, fecha_ini, fecha_fin = leer_json(FILE_ID, CREDENTIALS)
        st.session_state._escalacv_datos_ssaa_general = datos_total

    else:
        # 🔹 Caso combinado (SPOT + SSAA)
        FILE_ID_SPOT = st.secrets['FILE_ID_SPOT']
        FILE_ID_SSAA = st.secrets['FILE_ID_SSAA']
        datos_spot, fecha_ini_spot, fecha_fin_spot = leer_json(FILE_ID_SPOT, CREDENTIALS)
        datos_ssaa, fecha_ini_ssaa, fecha_fin_ssaa = leer_json(FILE_ID_SSAA, CREDENTIALS)

        # Conservamos las dos series ya obtenidas para el panel General. Así
        # no se vuelven a materializar desde cache justo después de combinarlas.
        st.session_state._escalacv_datos_spot_general = datos_spot
        st.session_state._escalacv_datos_ssaa_general = datos_ssaa

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
    st.session_state._escalacv_componente_cargado = componente_actual

 

def persist_widget(
    widget_func, label, *args, key=None, default=None, widget_suffix=None, **kwargs
):
    """
    Hace persistente un widget entre páginas usando:
    - key permanente: key
    - key temporal de widget: _key
    """

    if key is None:
        raise ValueError("persist_widget requiere argumento 'key'")

    temp_key = f"_{key}_{widget_suffix}" if widget_suffix else f"_{key}"

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


def mostrar_parametros_formula_indexado(
    widget_suffix=None,
    diferido=False,
    dos_filas_tres_columnas=False,
):
    """Dibuja la configuración de fórmula compartida por los indexados."""

    valores = {}

    def widget(widget_func, label, *args, key, default, **kwargs):
        if diferido:
            if key not in st.session_state:
                st.session_state[key] = default
            temp_key = f"_{key}_{widget_suffix or 'diferido'}"
            if temp_key not in st.session_state:
                st.session_state[temp_key] = st.session_state[key]
            valor = widget_func(label, *args, key=temp_key, **kwargs)
            valores[key] = valor
            return valor
        return persist_widget(
            widget_func,
            label,
            *args,
            key=key,
            default=default,
            widget_suffix=widget_suffix,
            **kwargs,
        )

    if dos_filas_tres_columnas:
        fila1_col1, fila1_col2, fila1_col3 = st.columns(3)
        with fila1_col1:
            widget(
                st.number_input,
                "Desvíos apantallados (€/MWh)",
                min_value=0.0, max_value=20.0, step=0.1,
                key="desvios_apant", default=0.0,
            )
        with fila1_col2:
            widget(
                st.number_input,
                "Margen (€/MWh)",
                min_value=0.0, max_value=50.0, step=0.1,
                key="margen_telemindex", default=0.0,
            )
        with fila1_col3:
            widget(
                st.selectbox,
                "Ubicación margen",
                ["perdidas", "tm", "neto"],
                key="cfg_margen_pos", default="tm",
            )

        fila2_col1, fila2_col2, fila2_col3 = st.columns(3)
        with fila2_col1:
            widget(
                st.checkbox,
                "Incluye FNEE",
                key="cfg_fnee", default=True,
            )
        with fila2_col2:
            if valores.get("cfg_fnee", st.session_state.get("cfg_fnee", False)):
                widget(
                    st.selectbox,
                    "Ubicación FNEE",
                    ["perdidas", "tm", "neto"],
                    key="cfg_fnee_pos", default="perdidas",
                )
        with fila2_col3:
            widget(
                st.number_input,
                "Coste financiero (%)",
                min_value=0.0, max_value=10.0, step=0.01,
                key="cf_pct", default=0.0,
            )
        return valores

    widget(
        st.number_input,
        "Desvíos apantallados (€/MWh)",
        min_value=0.0,
        max_value=20.0,
        step=0.1,
        key="desvios_apant",
        default=0.0,
    )
    widget(
        st.number_input,
        "Margen (€/MWh)",
        min_value=0.0,
        max_value=50.0,
        step=0.1,
        key="margen_telemindex",
        default=0.0,
    )
    widget(
        st.selectbox,
        "Ubicación margen",
        ["perdidas", "tm", "neto"],
        key="cfg_margen_pos",
        default="tm",
    )
    widget(
        st.checkbox,
        "Incluye FNEE",
        key="cfg_fnee",
        default=True,
    )
    if valores.get("cfg_fnee", st.session_state.get("cfg_fnee", False)):
        widget(
            st.selectbox,
            "Ubicación FNEE",
            ["perdidas", "tm", "neto"],
            key="cfg_fnee_pos",
            default="perdidas",
        )
    widget(
        st.number_input,
        "Coste financiero (%)",
        min_value=0.0,
        max_value=10.0,
        step=0.01,
        key="cf_pct",
        default=0.0,
    )
    return valores
