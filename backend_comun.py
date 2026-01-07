import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import streamlit as st
from datetime import datetime,date
import locale





colores_precios = {'precio_2.0': 'goldenrod', 'precio_3.0': 'darkred', 'precio_6.1': '#1C83E1', 'precio_curva': 'limegreen'}

def rango_componentes():
    componente = st.session_state.get('componente', 'SPOT')
    if componente in ['SPOT', 'SPOT+SSAA']:
        return {
                'rango': [-50, 20.01, 40.01, 60.01, 80.01, 100.01, 120.01, 140.01, 10000], #9 elementos
                'valor_asignado': ['muy bajo', 'bajo', 'medio', 'alto', 'muy alto', 'chungo', 'xtrem', 'defcon3', 'defcon2'],
        }
    else:
        return {
                'rango': [-50, 4.01, 8.01, 12.01, 16.01, 20.01, 24.01, 28.01, 10000], #9 elementos
                'valor_asignado': ['muy bajo', 'bajo', 'medio', 'alto', 'muy alto', 'chungo', 'xtrem', 'defcon3', 'defcon2'],
        }
    

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
    
    st.session_state.df_sheets = df
    columnas_numericas = st.session_state.df_sheets.columns.difference(['fecha', 'mes_nombre', 'dh_3p', 'dh_6p'])  # Excluir columnas de texto si las hay
    # 🔹 Convertir todas las columnas a numérico (int o float según corresponda)
    st.session_state.df_sheets[columnas_numericas] = st.session_state.df_sheets[columnas_numericas].apply(pd.to_numeric, errors='coerce')
    
    st.session_state.worksheet = worksheet
    return 
    #return st.session_state.df_sheets

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