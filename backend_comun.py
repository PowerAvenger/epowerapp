import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials


NOMBRE_ZONA_PERIODOS = {
    "peninsula": "PENÍNSULA",
    "baleares": "BALEARES",
    "canarias": "CANARIAS",
    "ceuta": "CEUTA",
    "melilla": "MELILLA",
}

@st.cache_data
def cargar_componentes_regulados(path_componentes="utils/004 LUZ componentes regulados.xlsx"):
    """
    Carga las tablas reguladas necesarias para recalcular PPCC, pérdidas BOE y PyC energía.
    """

    tablas = pd.read_excel(
        path_componentes,
        sheet_name=None,
        engine="openpyxl"
    )

    df_ppcc = tablas["PPCC"].copy()
    df_perdidas_boe = tablas["PERDIDAS"].copy()
    df_pycs_energia = tablas["PYC_E"].copy()

    # Normalizamos fechas
    for df_tabla in [df_ppcc, df_pycs_energia]:
        df_tabla["fecha_inicio"] = pd.to_datetime(df_tabla["fecha_inicio"]).dt.date
        df_tabla["fecha_final"] = pd.to_datetime(df_tabla["fecha_final"]).dt.date

    return df_ppcc, df_perdidas_boe, df_pycs_energia

def recalcular_componentes_regulados(df):
    """
    Recalcula los componentes regulados que dependen del periodo horario.

    Está pensada para usarse después de aplicar la zona de periodos:
        1. aplicar_dh6p_zona()
        2. recalcular_componentes_regulados_index()
        3. calcular_precios_atr()

    Recalcula:
        - ppcc_2.0, ppcc_3.0, ppcc_6.1
        - perd_2.0_boe, perd_3.0_boe, perd_6.1_boe
        - perd_2.0, perd_3.0, perd_6.1
        - pyc_2.0, pyc_3.0, pyc_6.1

    Aunque dh_3p sea común a todas las zonas, recalculamos también 2.0
    para mantener coherencia con las tablas reguladas.
    """

    df = df.copy()

    df_ppcc, df_perdidas_boe, df_pycs_energia = cargar_componentes_regulados()

    # =====================================================
    # 0. NORMALIZACIÓN BÁSICA
    # =====================================================
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.date

    df["dh_3p"] = df["dh_3p"].astype(str)
    df["dh_6p"] = df["dh_6p"].astype(str)

    # Aseguramos coef_k
    if "coef_k" not in df.columns:
        raise ValueError("No encuentro la columna 'coef_k' en el DataFrame.")

    df["coef_k"] = pd.to_numeric(df["coef_k"], errors="coerce")

    # =====================================================
    # 1. RECALCULAR PPCC
    # =====================================================
    for col in ["ppcc_2.0", "ppcc_3.0", "ppcc_6.1"]:
        df[col] = None

    for _, row in df_ppcc.iterrows():

        mask_2p = (
            (df["fecha"] >= row["fecha_inicio"])
            & (df["fecha"] <= row["fecha_final"])
            & (df["dh_3p"] == str(row["periodo"]))
        )

        mask_6p = (
            (df["fecha"] >= row["fecha_inicio"])
            & (df["fecha"] <= row["fecha_final"])
            & (df["dh_6p"] == str(row["periodo"]))
        )

        df.loc[mask_2p, "ppcc_2.0"] = row["2.0TD"]
        df.loc[mask_6p, "ppcc_3.0"] = row["3.0TD"]
        df.loc[mask_6p, "ppcc_6.1"] = row["6.1TD"]

    df[["ppcc_2.0", "ppcc_3.0", "ppcc_6.1"]] = (
        df[["ppcc_2.0", "ppcc_3.0", "ppcc_6.1"]]
        .apply(pd.to_numeric, errors="coerce")
        * 1000
    ).round(2)

    # =====================================================
    # 2. RECALCULAR PÉRDIDAS BOE
    # =====================================================
    mapa_perd_20 = df_perdidas_boe.set_index("periodo")["2.0TD"]
    mapa_perd_30 = df_perdidas_boe.set_index("periodo")["3.0TD"]
    mapa_perd_61 = df_perdidas_boe.set_index("periodo")["6.1TD"]

    df["perd_2.0_boe"] = df["dh_3p"].map(mapa_perd_20)
    df["perd_3.0_boe"] = df["dh_6p"].map(mapa_perd_30)
    df["perd_6.1_boe"] = df["dh_6p"].map(mapa_perd_61)

    df["perd_2.0_boe"] = pd.to_numeric(df["perd_2.0_boe"], errors="coerce")
    df["perd_3.0_boe"] = pd.to_numeric(df["perd_3.0_boe"], errors="coerce")
    df["perd_6.1_boe"] = pd.to_numeric(df["perd_6.1_boe"], errors="coerce")

    # =====================================================
    # 3. RECALCULAR PÉRDIDAS CON COEF_K
    # =====================================================
    df["perd_2.0"] = df["perd_2.0_boe"] * df["coef_k"]
    df["perd_3.0"] = df["perd_3.0_boe"] * df["coef_k"]
    df["perd_6.1"] = df["perd_6.1_boe"] * df["coef_k"]

    # =====================================================
    # 4. RECALCULAR PYC ENERGÍA
    # =====================================================
    for col in ["pyc_2.0", "pyc_3.0", "pyc_6.1"]:
        df[col] = None

    for _, row in df_pycs_energia.iterrows():

        mask_2p = (
            (df["fecha"] >= row["fecha_inicio"])
            & (df["fecha"] <= row["fecha_final"])
            & (df["dh_3p"] == str(row["periodo"]))
        )

        mask_6p = (
            (df["fecha"] >= row["fecha_inicio"])
            & (df["fecha"] <= row["fecha_final"])
            & (df["dh_6p"] == str(row["periodo"]))
        )

        df.loc[mask_2p, "pyc_2.0"] = row["2.0TD"]
        df.loc[mask_6p, "pyc_3.0"] = row["3.0TD"]
        df.loc[mask_6p, "pyc_6.1"] = row["6.1TD"]

    df[["pyc_2.0", "pyc_3.0", "pyc_6.1"]] = (
        df[["pyc_2.0", "pyc_3.0", "pyc_6.1"]]
        .apply(pd.to_numeric, errors="coerce")
        * 1000
    )

    # =====================================================
    # 5. COMPROBACIÓN BÁSICA
    # =====================================================
    cols_check = [
        "ppcc_2.0", "ppcc_3.0", "ppcc_6.1",
        "perd_2.0_boe", "perd_3.0_boe", "perd_6.1_boe",
        "perd_2.0", "perd_3.0", "perd_6.1",
        "pyc_2.0", "pyc_3.0", "pyc_6.1",
    ]

    nulos = df[cols_check].isna().sum()
    nulos = nulos[nulos > 0]

    if len(nulos) > 0:
        print("Aviso: hay nulos tras recalcular componentes regulados:")
        print(nulos)

    return df

def calcular_precios_atr(df):
    
    tm_rate = 0.015
    cf = st.session_state.get("cf_pct", 0.0) / 100
    margen = st.session_state.get("margen_telemindex", 0.0)
    df = df.copy()

    for atr in ["2.0", "3.0", "6.1"]:

        base = (
            df["spot"]
            + df["ssaa"]
            + df[f"ppcc_{atr}"]
            + df["osom"]
        )

        # ajuste manual por diferencia de los SSAA id esios con los C2
        base += 0.0

        # componente fijo antes de pérdidas
        base += st.session_state.get("desvios_apant", 0.0)

        # FNEE en pérdidas
        if st.session_state.get("cfg_fnee", False) and st.session_state.get("cfg_fnee_pos") == "perdidas":
            base += df["fnee"]

        # duplicamos base: una para coste y otra para precio
        base_coste = base.copy()
        base_precio = base.copy()

        # margen en pérdidas: solo entra en precio
        if st.session_state.get("cfg_margen_pos") == "perdidas":
            df[f"margen_{atr}"] = margen * (1 + df[f"perd_{atr}"]) * (1 + tm_rate) * (1 + cf)
            base_precio += margen

        # pérdidas
        base_coste *= (1 + df[f"perd_{atr}"])
        base_precio *= (1 + df[f"perd_{atr}"])

        # margen en tm: solo entra en precio
        if st.session_state.get("cfg_margen_pos") == "tm":
            df[f"margen_{atr}"] = margen * (1 + tm_rate) * (1 + cf)
            base_precio += margen

        # FNEE en tm
        if st.session_state.get("cfg_fnee", False) and st.session_state.get("cfg_fnee_pos") == "tm":
            base_coste += df["fnee"]
            base_precio += df["fnee"]

        # tm
        base_coste *= (1 + tm_rate)
        base_precio *= (1 + tm_rate)

        # cf
        base_coste *= (1 + cf)
        base_precio *= (1 + cf)

        # FNEE en neto
        if st.session_state.get("cfg_fnee", False) and st.session_state.get("cfg_fnee_pos") == "neto":
            base_coste += df["fnee"]
            base_precio += df["fnee"]

        # margen en neto: solo entra en precio
        if st.session_state.get("cfg_margen_pos") == "neto":
            df[f"margen_{atr}"] = margen
            base_precio += margen

        # coste sin margen
        df[f"coste_{atr}"] = base_coste

        # precio final con margen y pyc
        df[f"precio_{atr}"] = base_precio + df[f"pyc_{atr}"]

    return df


colores_precios = {'precio_2.0': 'goldenrod', 'precio_3.0': 'darkred', 'precio_6.1': '#1C83E1', 'precio_curva': 'limegreen'}

def rango_componentes():
    componente = st.session_state.get('componente', 'SPOT')

    if componente in ['SPOT', 'SPOT+SSAA']:
        return {
            'rango': [-50, 0, 20.01, 40.01, 60.01, 80.01, 100.01, 120.01, 140.01, 160.01, 100000000],
            'valor_asignado': ['≤0', 'muy bajo', 'bajo', 'medio', 'alto', 'muy alto', 'chungo', 'xtrem', 'defcon3', 'defcon2']
        }
    else:
        return {
            'rango': [-5000000, 0, 4.01, 8.01, 12.01, 16.01, 20.01, 24.01, 28.01, 32.01, 100000000],
            'valor_asignado': ['≤0', 'muy bajo', 'bajo', 'medio', 'alto', 'muy alto', 'chungo', 'xtrem', 'defcon3', 'defcon2']
        }
    
ESTILO_GRAF = dict(
    title_size = 22,
    axis_title_size = 16,
    tick_size = 12,
    hover_size = 16,
    legend_size = 13,
    height = 500,
    separators=",."
)

ESTILO_GRAF_COMPACTO = dict(
    title_size = 20,
    axis_title_size = 14,
    tick_size = 11,
    hover_size = 15,
    legend_size = 12,
    height = 420
)

def aplicar_estilo(fig):

    fig.update_layout(

        title=dict(
            x=0.5,
            xanchor="center",
            font=dict(size=ESTILO_GRAF["title_size"])
        ),

        xaxis=dict(
            title_font=dict(size=ESTILO_GRAF["axis_title_size"]),
            tickfont=dict(size=ESTILO_GRAF["tick_size"])
        ),

        yaxis=dict(
            title_font=dict(size=ESTILO_GRAF["axis_title_size"]),
            tickfont=dict(size=ESTILO_GRAF["tick_size"])
        ),

        hoverlabel=dict(
            font_size=ESTILO_GRAF["hover_size"],
            
        ),

        legend=dict(
            font=dict(size=ESTILO_GRAF["legend_size"])
        ),

        height=ESTILO_GRAF["height"],
        separators=ESTILO_GRAF["separators"],

    )

    return fig


def aplicar_texto_pie_porcentaje(fig, size=18, position="auto", color=None):
    """
    Aumenta y pone en negrita los porcentajes en gráficos tipo pie/donut.
    """

    textfont = dict(size=size)
    if color is not None:
        textfont["color"] = color

    fig.update_traces(
        textinfo="percent",
        texttemplate="<b>%{percent}</b>",
        textfont=dict(
            size=size,
            color=color
        ),
        textposition=position
    )

    return fig


# Reexportación compatible de la API canónica de presentación.
from formato_es import (
    MESES_ES,
    formato_cent_eur_kwh,
    formato_eur_kwh,
    formato_eur_mwh,
    formato_euros,
    formato_fecha_es,
    formato_kwh,
    formato_kw,
    formato_mes_es,
    formato_mwh,
    formato_numero_es,
    formato_pct,
    formatear_columnas_tabla,
    formatear_resumen_mixto,
    formatear_tabla_consumos,
    formatear_tabla_euros,
)
@st.cache_resource
def autenticar_google_sheets():
    # Rutas y configuraciones
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    CREDENTIALS_INFO = st.secrets['GOOGLE_SHEETS_CREDENTIALS'] 
    #CREDENTIALS_INFO = dict(st.secrets['GOOGLE_SHEETS_CREDENTIALS'])
    #CREDENTIALS_INFO["private_key"] = CREDENTIALS_INFO["private_key"].replace("\\n", "\n")
    
    # Autenticación
    #credentials = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    credentials = Credentials.from_service_account_info(CREDENTIALS_INFO, scopes=SCOPES)
    st.session_state.client = gspread.authorize(credentials)
    return st.session_state.client

#@st.cache_data
def carga_rapida_sheets():
    """Obtiene la última fecha registrada en Google Sheets en formato 'YYYY-MM-DD' de la forma más rápida posible."""
    # CONSTANTES
    SPREADSHEET_ID = st.secrets['SHEET_INDEX_ID']
    sheet = st.session_state.client.open_by_key(SPREADSHEET_ID)
    worksheet = sheet.sheet1
    # 🔹 Leer solo la columna de fechas (columna A)
    fechas_col = worksheet.col_values(1)  

    ultima_fecha_str = fechas_col[-1]
    # 🔹 Encontrar la fila donde empieza la última fecha
    celdas_fecha = worksheet.findall(ultima_fecha_str, in_column = 1)
    fila_inicio = celdas_fecha[0].row
    fila_fin = celdas_fecha[-1].row
    # 🔹 Obtener todas las filas del último día dinámicamente
    data_rows = worksheet.get(f"A{fila_inicio}:AE{fila_fin}")  # Ajustar rango según el número real de filas
    # Obtener los encabezados
    header = worksheet.row_values(1)
    # Convertir a DataFrame y obtener la última fecha
    st.session_state.df_sheets = pd.DataFrame(data_rows, columns=header)
    st.session_state.df_sheets['fecha'] = pd.to_datetime(st.session_state.df_sheets['fecha']).dt.date

    columnas_numericas = st.session_state.df_sheets.columns.difference(['fecha', 'mes_nombre', 'dh_3p', 'dh_6p'])  # Excluir columnas de texto si las hay
    # 🔹 Convertir todas las columnas a numérico (int o float según corresponda)
    st.session_state.df_sheets[columnas_numericas] = st.session_state.df_sheets[columnas_numericas].apply(pd.to_numeric, errors='coerce')

    st.session_state.ultima_fecha_sheets = pd.to_datetime(ultima_fecha_str, errors='coerce').date()
    st.session_state.worksheet = worksheet
    return


#ESTE CÓDIGO ES PARA ACCEDER AL SHEETS COMPLETO DE INDEXADOS
#@st.cache_data
def carga_total_sheets(): #sheet_name=None
    SPREADSHEET_ID = st.secrets['SHEET_INDEX_ID']
    sheet = st.session_state.client.open_by_key(SPREADSHEET_ID)
    # Primera hoja por defecto  
    worksheet = sheet.sheet1  
    # Obtener los datos como DataFrame
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    
    df['fecha'] = pd.to_datetime(df['fecha']).dt.date

    # 🔹 Leer solo la columna de fechas (columna A)
    fechas_col = worksheet.col_values(1)
    ultima_fecha_str = fechas_col[-1]
    st.session_state.ultima_fecha_sheets = pd.to_datetime(ultima_fecha_str, errors='coerce').date()
    
    st.session_state.df_sheets_old = df
    columnas_numericas = st.session_state.df_sheets_old.columns.difference(['fecha', 'mes_nombre', 'dh_3p', 'dh_6p'])  # Excluir columnas de texto si las hay
    # 🔹 Convertir todas las columnas a numérico (int o float según corresponda)
    st.session_state.df_sheets_old[columnas_numericas] = st.session_state.df_sheets_old[columnas_numericas].apply(pd.to_numeric, errors='coerce')
    
    st.session_state.worksheet = worksheet
    return 
    #return st.session_state.df_sheets

# para el csv componentes
def enriquecer_datetime(df):

    df = df.copy()

    df["datetime"] = pd.to_datetime(df["datetime"])

    df["fecha"] = df["datetime"].dt.date
    df["año"] = df["datetime"].dt.year
    df["mes"] = df["datetime"].dt.month
    df["dia"] = df["datetime"].dt.day
    df["hora"] = df["datetime"].dt.hour

    map_mes = {
        1: "enero", 2: "febrero", 3: "marzo",
        4: "abril", 5: "mayo", 6: "junio",
        7: "julio", 8: "agosto", 9: "septiembre",
        10: "octubre", 11: "noviembre", 12: "diciembre"
    }

    df["mes_nombre"] = df["mes"].map(map_mes)

    return df


def construir_media_acumulada_prevista(
    datos_diarios_reales,
    curva_mensual_prevista,
    año,
    col_fecha_real="fecha",
    col_valor_real="value",
    col_fecha_prevision="fecha",
    col_valor_prevision="precio",
):
    """Prolonga la media acumulada real con una previsión mensual.

    Devuelve exclusivamente el tramo previsto, incluyendo como anclaje el
    último punto real. No accede a ``st.session_state`` y no modifica los
    dataframes recibidos.
    """
    columnas_salida = ["fecha", "media_acumulada_prevista", "precio_base", "tipo"]

    columnas_reales = {col_fecha_real, col_valor_real}
    columnas_prevision = {col_fecha_prevision, col_valor_prevision}
    if not columnas_reales.issubset(datos_diarios_reales.columns):
        return pd.DataFrame(columns=columnas_salida)
    if not columnas_prevision.issubset(curva_mensual_prevista.columns):
        return pd.DataFrame(columns=columnas_salida)

    reales = datos_diarios_reales[[col_fecha_real, col_valor_real]].copy()
    reales[col_fecha_real] = pd.to_datetime(reales[col_fecha_real], errors="coerce")
    reales[col_valor_real] = pd.to_numeric(reales[col_valor_real], errors="coerce")
    reales = reales.dropna().copy()
    reales = reales[reales[col_fecha_real].dt.year == int(año)]
    reales[col_fecha_real] = reales[col_fecha_real].dt.normalize()
    reales = (
        reales.groupby(col_fecha_real, as_index=False)[col_valor_real]
        .mean()
        .sort_values(col_fecha_real)
    )

    if reales.empty:
        return pd.DataFrame(columns=columnas_salida)

    ultima_fecha_real = reales[col_fecha_real].max()
    fecha_fin = pd.Timestamp(int(año), 12, 31)
    if ultima_fecha_real >= fecha_fin:
        return pd.DataFrame(columns=columnas_salida)

    curva = curva_mensual_prevista[[col_fecha_prevision, col_valor_prevision]].copy()
    curva[col_fecha_prevision] = pd.to_datetime(curva[col_fecha_prevision], errors="coerce")
    curva[col_valor_prevision] = pd.to_numeric(curva[col_valor_prevision], errors="coerce")
    curva = curva.dropna().copy()
    curva = curva[curva[col_fecha_prevision].dt.year == int(año)]
    curva["periodo"] = curva[col_fecha_prevision].dt.to_period("M")
    precios_mensuales = curva.drop_duplicates("periodo", keep="last").set_index("periodo")[col_valor_prevision]

    fechas_futuras = pd.date_range(ultima_fecha_real + pd.Timedelta(days=1), fecha_fin, freq="D")
    futuro = pd.DataFrame({"fecha": fechas_futuras})
    futuro["periodo"] = futuro["fecha"].dt.to_period("M")
    futuro["precio_base"] = futuro["periodo"].map(precios_mensuales)

    # Una previsión incompleta no debe generar una curva engañosa.
    if futuro["precio_base"].isna().any():
        return pd.DataFrame(columns=columnas_salida)

    reales_base = reales.rename(
        columns={col_fecha_real: "fecha", col_valor_real: "precio_base"}
    )[["fecha", "precio_base"]]
    futuro_base = futuro[["fecha", "precio_base"]]
    combinado = pd.concat([reales_base, futuro_base], ignore_index=True)
    combinado["media_acumulada_prevista"] = combinado["precio_base"].expanding().mean()
    combinado["tipo"] = "previsto"

    tramo_previsto = combinado[combinado["fecha"] >= ultima_fecha_real].copy()
    tramo_previsto.loc[tramo_previsto["fecha"] == ultima_fecha_real, "tipo"] = "anclaje_real"

    return tramo_previsto[columnas_salida].reset_index(drop=True)

# CARGAMOS CSV COMPONENTES
def cargar_componentes_csv():
    
    file_id = st.secrets['CSV_COMPONENTES']
    url = f"https://drive.google.com/uc?export=download&id={file_id}"

    import requests
    r = requests.get(url)
    print(r.text[:500])
    df = pd.read_csv(
        url,
        sep=",",                # 👈 confirmado por tu CSV
        engine="python",        # 👈 clave
        quoting=3,              # 👈 IGNORA comillas problemáticas
        on_bad_lines="skip",    # 👈 salta líneas corruptas
        encoding="utf-8"
    )

    # 🔹 limpieza básica nombres columnas
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
    )
    print('carga csv componentes')
    print(df)
    df = enriquecer_datetime(df)
    print('carga csv componentes enriquecido')
    print(df)

    return df

#CARGAMOS MIBGAS DESDE SHEET DE DRIVE
@st.cache_data
def carga_mibgas(): #sheet_name=None
    SPREADSHEET_ID = st.secrets['SHEET_MIBGAS_ID']
    sheet = st.session_state.client.open_by_key(SPREADSHEET_ID)
    # Primera hoja por defecto  
    worksheet = sheet.sheet1  
    # Obtener los datos como DataFrame
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    df=df.rename(columns={'Product':'producto','First Day Delivery':'fecha_entrega','Last Price\n[EUR/MWh]':'precio_gas'})
    df["precio_gas"] = pd.to_numeric(df["precio_gas"], errors="coerce")
    df['fecha_entrega'] = pd.to_datetime(df['fecha_entrega'], dayfirst=False, errors='coerce')
    df['año_entrega'] = df['fecha_entrega'].dt.year
    df['Trading day'] = pd.to_datetime(df['Trading day'])

    # Crear nueva columna con formato "6-ene"
    #df['fecha_corta'] = df['fecha_entrega'].dt.strftime('%-d-%b')  # en Linux/Mac
    # Si estás en Windows y da error con %-d, usa:
    df['fecha_corta'] = df['fecha_entrega'].dt.strftime('%#d-%b')
    # Convertir abreviaturas de mes a minúsculas y eliminar puntos
    df['fecha_corta'] = df['fecha_corta'].str.lower().str.replace('.', '', regex=False)
    df = df.sort_values('fecha_entrega', ascending=True).reset_index(drop=True)

    print('mibgas base')
    print(df)
    
    return df



def obtener_df_resumen(df_curva, simul_curva=None, margen_eur_kWh=0.0):
    """
    Construye el df_resumen canónico para Telemindex y Simulindex con consumos, costes y precios medios

    - simul_curva = None  → Telemindex (datos reales)
    - simul_curva != None → Simulindex (datos simulados)
    """

    orden = [f"P{i}" for i in range(1, 7)]

    # ======================
    # CONSUMOS
    # ======================
    consumo = (
        df_curva.groupby("periodo")["consumo_neto_kWh"]
        .sum()
        .reindex(orden)
        .fillna(0)
    )
    consumo["TOTAL"] = consumo.sum()


    # ======================
    # COSTE BASE (real)
    # ======================
    coste_base = (
        df_curva.groupby("periodo")["coste_total"]
        .sum()
        .reindex(orden)
        .fillna(0)
    )
    coste_base["TOTAL"] = coste_base.sum()

    # ======================
    # PRECIO REAL MEDIO
    # ======================
    precio_real = coste_base / consumo
    precio_real_total = precio_real["TOTAL"]

    # ======================
    # SI HAY SIMULACIÓN
    # ======================
    if simul_curva is not None:
        # ratios históricos
        ratios = precio_real / precio_real_total

        # precio total simulado (€/kWh)
        precio_sim_total = simul_curva / 100 + margen_eur_kWh

        # precios simulados por periodo
        precio = ratios * precio_sim_total
        precio["TOTAL"] = precio_sim_total

        # costes simulados
        coste = consumo * precio

    else:
        # modo real (Telemindex)
        precio = precio_real
        coste = coste_base

    # ======================
    # DF RESUMEN CANÓNICO
    # ======================
    df_resumen = pd.DataFrame({
        "Consumo (kWh)": consumo,
        "Coste (€)": coste,
        "Precio medio (€/kWh)": coste / consumo
    }).T

    print('df_resumen')
    print(df_resumen)

    return df_resumen


def formatear_df_resumen(df_resumen):
    """
    Aplica formato español a un df_resumen ya etiquetado.
    Solo presentación.
    """

    styler = df_resumen.style

    # ======================
    # Consumo (kWh)
    # ======================
    if "Consumo (kWh)" in df_resumen.index:
        styler = styler.format(
            subset=pd.IndexSlice["Consumo (kWh)", :],
            formatter=lambda x: formato_kwh(x, decimales=0, unidad=False)
        )

    # ======================
    # Precio medio (€/kWh)
    # ======================
    if "Precio medio (€/kWh)" in df_resumen.index:
        styler = styler.format(
            subset=pd.IndexSlice["Precio medio (€/kWh)", :],
            formatter=lambda x: formato_eur_kwh(x, decimales=6, unidad=False)
        )

    # ======================
    # Coste (€)
    # ======================
    if "Coste (€)" in df_resumen.index:
        styler = styler.format(
            subset=pd.IndexSlice["Coste (€)", :],
            formatter=lambda x: formato_euros(x, decimales=2, unidad=True)
        )

    # ======================
    # Estilo general
    # ======================
    styler = styler.set_properties(**{"text-align": "right"})

    styler = styler.set_table_styles([
        {
            "selector": "th.col_heading",
            "props": "background-color: #F0F4F8; font-weight: bold; text-align: center;"
        },
        {
            "selector": "th.row_heading",
            "props": "background-color: #F7F7F7; font-weight: bold;"
        },
        {
            "selector": "td",
            "props": "padding: 6px;"
        },
    ])

    return styler

def formatear_df_resultados(df):
    """
    Formato SOLO de presentación para tabla de comparación de ofertas
    (columnas, no índice)
    """

    styler = df.style

    styler = styler.format({
        "Coste anual (€)": formato_euros,
        "Precio medio (€/kWh)": lambda x: formato_eur_kwh(x, unidad=False),
        "% sobre la más barata": formato_pct,
        "Δ vs más barata (€)": formato_euros,
    })

    # Alineación
    styler = styler.set_properties(**{"text-align": "right"})

    # Estilos visuales (coherentes con el resto)
    styler = styler.set_table_styles([
        {
            "selector": "th.col_heading",
            "props": "background-color: #F0F4F8; font-weight: bold; text-align: center;"
        },
        {
            "selector": "td",
            "props": "padding: 6px;"
        },
    ])

    return styler

@st.cache_data
def cargar_periodos_zona(zona):
    """
    Carga el fichero de periodos horarios correspondiente a la zona.
    La hora debe estar en formato 0-23.
    """

    mapa_periodos_path = {
        "peninsula": "utils/periodos_horarios.xlsx",
        "baleares": "utils/periodos_horarios_baleares.xlsx",
        "canarias": "utils/periodos_horarios_canarias.xlsx",
        "ceuta": "utils/periodos_horarios_ceuta.xlsx",
        "melilla": "utils/periodos_horarios_melilla.xlsx",
    }

    if zona not in mapa_periodos_path:
        raise ValueError(f"Zona de periodos no reconocida: {zona}")

    periodos_path = mapa_periodos_path[zona]

    df_periodos = pd.read_excel(
        periodos_path,
        dtype={
            "año": int,
            "mes": int,
            "dia": int,
            "hora": int,
            "dh_6p": str,
        }
    )

    return df_periodos[["año", "mes", "dia", "hora", "dh_6p"]]

def aplicar_dh6p_zona(df, zona):
    """
    Sustituye la columna dh_6p de un DataFrame por la correspondiente
    a la zona seleccionada.

    Para península no modifica nada.
    """

    df = df.copy()

    if zona == "peninsula":
        return df

    df_periodos = cargar_periodos_zona(zona).rename(
        columns={"dh_6p": "dh_6p_zona"}
    )

    claves = ["año", "mes", "dia", "hora"]

    # Aseguramos tipos para que el merge no falle por int/str/float
    for col in claves:
        df[col] = df[col].astype(int)
        df_periodos[col] = df_periodos[col].astype(int)

    df = df.merge(
        df_periodos,
        on=claves,
        how="left"
    )

    # Sustituimos solo cuando haya valor encontrado
    df["dh_6p"] = df["dh_6p_zona"].fillna(df["dh_6p"])

    df = df.drop(columns=["dh_6p_zona"])

    return df
