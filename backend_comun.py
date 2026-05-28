import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import streamlit as st







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
            font_size=ESTILO_GRAF["hover_size"]
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


MESES_ES = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr",
    5: "may", 6: "jun", 7: "jul", 8: "ago",
    9: "sep", 10: "oct", 11: "nov", 12: "dic"
}


def formato_numero_es(valor, decimales=0):
    """
    Formatea un número en estilo español:
    22920.5 -> 22.921
    1234.56 -> 1.234,56
    """
    if pd.isna(valor):
        return ""

    try:
        valor = float(valor)
    except Exception:
        return valor

    texto = f"{valor:,.{decimales}f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")

    return texto


def formato_kwh(valor, decimales=0, unidad=False):
    texto = formato_numero_es(valor, decimales)

    if texto == "":
        return ""

    return f"{texto} kWh" if unidad else texto


def formato_mwh(valor, decimales=2, unidad=False):
    texto = formato_numero_es(valor, decimales)

    if texto == "":
        return ""

    return f"{texto} MWh" if unidad else texto


def formato_euros(valor, decimales=2, unidad=True):
    texto = formato_numero_es(valor, decimales)

    if texto == "":
        return ""

    return f"{texto} €" if unidad else texto


def formato_eur_mwh(valor, decimales=2, unidad=True):
    texto = formato_numero_es(valor, decimales)

    if texto == "":
        return ""

    return f"{texto} €/MWh" if unidad else texto


def formato_eur_kwh(valor, decimales=6, unidad=True):
    texto = formato_numero_es(valor, decimales)

    if texto == "":
        return ""

    return f"{texto} €/kWh" if unidad else texto

def formato_cent_eur_kwh(valor, decimales=4, unidad=True):
    texto = formato_numero_es(valor, decimales)

    if texto == "":
        return ""

    return f"{texto} €/kWh" if unidad else texto


def formato_pct(valor, decimales=2, unidad=True):
    texto = formato_numero_es(valor, decimales)

    if texto == "":
        return ""

    return f"{texto} %" if unidad else texto


def formato_mes_es(valor, capitalizar=True):
    """
    Convierte fechas o textos parseables tipo 'Apr 2025' en 'Abr 2025'.
    """
    fecha = pd.to_datetime(valor, errors="coerce")

    if pd.isna(fecha):
        return valor

    mes = MESES_ES.get(fecha.month, "")

    if capitalizar:
        mes = mes.capitalize()

    return f"{mes} {fecha.year}"

def formatear_columnas_tabla(
    df,
    columnas_kwh=None,
    columnas_mwh=None,
    columnas_euros=None,
    columnas_eur_mwh=None,
    columnas_eur_kwh=None,
    columnas_cent_eur_kwh=None,
    columnas_pct=None,
    columna_mes=None,
    incluir_unidades=False
):
    """
    Devuelve una copia del DataFrame formateada para visualización.
    No usar el resultado para cálculos.
    """

    df_fmt = df.copy()

    columnas_kwh = columnas_kwh or []
    columnas_mwh = columnas_mwh or []
    columnas_euros = columnas_euros or []
    columnas_eur_mwh = columnas_eur_mwh or []
    columnas_eur_kwh = columnas_eur_kwh or []
    columnas_cent_eur_kwh = columnas_cent_eur_kwh or []
    columnas_pct = columnas_pct or []

    if columna_mes is not None and columna_mes in df_fmt.columns:
        df_fmt[columna_mes] = df_fmt[columna_mes].map(formato_mes_es)

    for col in columnas_kwh:
        if col in df_fmt.columns:
            df_fmt[col] = df_fmt[col].map(
                lambda x: formato_kwh(x, decimales=0, unidad=incluir_unidades)
            )

    for col in columnas_mwh:
        if col in df_fmt.columns:
            df_fmt[col] = df_fmt[col].map(
                lambda x: formato_mwh(x, decimales=2, unidad=incluir_unidades)
            )

    for col in columnas_euros:
        if col in df_fmt.columns:
            df_fmt[col] = df_fmt[col].map(
                lambda x: formato_euros(x, decimales=2, unidad=incluir_unidades)
            )

    for col in columnas_eur_mwh:
        if col in df_fmt.columns:
            df_fmt[col] = df_fmt[col].map(
                lambda x: formato_eur_mwh(x, decimales=2, unidad=incluir_unidades)
            )

    for col in columnas_eur_kwh:
        if col in df_fmt.columns:
            df_fmt[col] = df_fmt[col].map(
                lambda x: formato_eur_kwh(x, decimales=6, unidad=incluir_unidades)
            )
    for col in columnas_cent_eur_kwh:
        if col in df_fmt.columns:
            df_fmt[col] = df_fmt[col].map(
                lambda x: formato_cent_eur_kwh(x, decimales=4, unidad=incluir_unidades)
            )

    for col in columnas_pct:
        if col in df_fmt.columns:
            df_fmt[col] = df_fmt[col].map(
                lambda x: formato_pct(x, decimales=2, unidad=incluir_unidades)
            )

    return df_fmt

# usada para formatear consumos con columna de mes en formato Abr 2026
def formatear_tabla_consumos(df, columna_mes=None, incluir_unidades=False):
    columnas_kwh = [
        c for c in df.columns
        if c.startswith("P") or c in ["Total", "consumo_neto_kWh", "demanda_neto_kWh", "vertido_neto_kWh"]
    ]

    return formatear_columnas_tabla(
        df,
        columnas_kwh=columnas_kwh,
        columna_mes=columna_mes,
        incluir_unidades=incluir_unidades
    )

# usada para formatear tablas económicas con columna de mes en formato Abr 2026
def formatear_tabla_euros(df, columna_mes=None, incluir_unidades=False):
    columnas_euros = [
        c for c in df.columns
        if c.startswith("P") or c in ["Total", "coste", "importe"]
    ]

    return formatear_columnas_tabla(
        df,
        columnas_euros=columnas_euros,
        columna_mes=columna_mes,
        incluir_unidades=incluir_unidades
    )

# usada para formatear consumos, costes y precios medios (telemindex y simulindex p.e.)
def formatear_resumen_mixto(df_resumen):
    """
    Formatea una tabla resumen con magnitudes por filas:
    - Consumo (kWh)
    - Coste (€)
    - Precio medio (€/kWh)

    Solo presentación.
    """

    df_t = df_resumen.T.copy()

    df_t_fmt = formatear_columnas_tabla(
        df_t,
        columnas_kwh=["Consumo (kWh)"],
        columnas_euros=["Coste (€)"],
        columnas_eur_kwh=["Precio medio (€/kWh)"],
        incluir_unidades=False,
        decimales_kwh=0,
        decimales_euros=2,
        decimales_eur_kwh=6
    )

    return df_t_fmt.T

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
            formatter=lambda x: (
                f"{x:,.0f}".replace(",", ".")
                if pd.notnull(x) else ""
            )
        )

    # ======================
    # Precio medio (€/kWh)
    # ======================
    if "Precio medio (€/kWh)" in df_resumen.index:
        styler = styler.format(
            subset=pd.IndexSlice["Precio medio (€/kWh)", :],
            formatter=lambda x: (
                f"{x:,.6f}".replace(".", ",")
                if pd.notnull(x) else ""
            )
        )

    # ======================
    # Coste (€)
    # ======================
    if "Coste (€)" in df_resumen.index:
        styler = styler.format(
            subset=pd.IndexSlice["Coste (€)", :],
            formatter=lambda x: (
                f"{x:,.2f} €".replace(",", ".")
                if pd.notnull(x) else ""
            )
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
        "Coste anual (€)": lambda x: f"{x:,.2f} €"
            .replace(",", "X").replace(".", ",").replace("X", "."),
        "Precio medio (€/kWh)": lambda x: f"{x:.6f}".replace(".", ","),
        "% sobre la más barata": lambda x: f"{x:.2f} %".replace(".", ","),
        "Δ vs más barata (€)": lambda x: f"{x:,.2f} €"
            .replace(",", "X").replace(".", ",").replace("X", "."),
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


