import streamlit as st
import plotly.express as px
import pandas as pd
import numpy as np
import io, re
from unidecode import unidecode
import plotly.graph_objects as go
from backend_comun import aplicar_estilo, aplicar_texto_pie_porcentaje


TZ = "Europe/Madrid"

colores_periodo = {
        "P1": "red",
        "P2": "#FF7518", #"orange",
        "P3": "#E6B800",   # amarillo oscuro
        "P4": "#FFF176",   # amarillo claro
        "P5": "#7CFC00",
        "P6": "green"
    }

# Esquema 2.0TD (3 periodos)
COLORES_3P = {
    "P1": "red",        # punta
    "P2": "#E6B800",    # llano (amarillo oscuro)
    "P3": "green"       # valle
}

# Esquema 3.0TD / 6.x (6 periodos)
COLORES_6P = {
    "P1": "red",
    "P2": "#FF7518",
    "P3": "#E6B800",
    "P4": "#FFF176",
    "P5": "#7CFC00",
    "P6": "green"
}

colores_neteo= {
    "consumo_neto_kWh": "#e74c3c",   # rojo
    "vertido_neto_kWh": "#27ae60",    # verde
    "generacion_kWh" : "#f1c40f"
}

# ===============================
#  Utilidades base
# ===============================

def _clean(s: str) -> str:
    s = unidecode(str(s)).lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s

   
def _read_any(uploaded_or_path):
    """
    Lee CSV o Excel forzando texto (sin autoconversión de fechas) y
    detecta automáticamente la fila de cabecera real (por ejemplo, si el archivo
    tiene encabezados en la fila 2 o 3 con 'FECHA', 'HORA', 'CONSUMO', etc.).
    """
    def detect_header_row(df):
        """Devuelve el número de fila que contiene cabecera real."""
        for i in range(min(10, len(df))):  # buscar solo en las primeras 10 filas
            #row_values = " ".join(df.iloc[i].astype(str).tolist()).lower()
            #if any(k in row_values for k in ["fecha", "hora", "consumo", "energ", "cups"]):
            #    return i
            row = df.iloc[i].astype(str).tolist()
            row_values = " ".join(row).lower()

            # Debe contener al menos una palabra clave
            if not any(k in row_values for k in ["fecha", "hora", "consumo", "energ", "cups"]):
                continue

            # Debe tener pocas celdas vacías y poca presencia de números
            non_empty = [x for x in row if x.strip() not in ["", "nan", "none"]]
            text_like = sum(1 for x in non_empty if not any(ch.isdigit() for ch in x))
            ratio_text = text_like / max(len(non_empty), 1)

            # Si más del 70% parecen texto (no números), se asume cabecera real
            if ratio_text > 0.7 and len(non_empty) >= 2:
                return i

        return None

    # --- Leer según tipo ---
    if isinstance(uploaded_or_path, str):
        print('Fichero seleccionado con ruta manual') #SOLO SE USARÁ EN CASO DE DEMO
        path = uploaded_or_path.lower()
        print(path)
        if path.endswith(".csv"):
            df = pd.read_csv(uploaded_or_path, dtype=str, header=None, skip_blank_lines=True)
        else:
            df = pd.read_excel(uploaded_or_path, dtype=str, header=None)
    else:
        print('Fichero seleccionado por upload files')
        name = uploaded_or_path.name.lower()
        print(name)
        if name.endswith(".csv"):
            content = uploaded_or_path.read()
            sample = content[:4096].decode("utf-8", errors="ignore")
            sep = ";" if sample.count(";") > sample.count(",") else ","
            df = pd.read_csv(io.BytesIO(content), sep=sep, dtype=str, header=None)
        else:
            
            xls = pd.ExcelFile(uploaded_or_path)

            mejor_df = None
            mejor_hoja = None
            mejor_score = 0

            MIN_FILAS = 20
            MIN_COLUMNAS = 2
            for sheet in xls.sheet_names:
                #df = pd.read_excel(uploaded_or_path, sheet_name=sheet, dtype=str, header=None)
                #if not df.empty:
                #    print(f"Usando hoja: {sheet}")
                #    break
                #print(df)
                df_tmp = pd.read_excel(
                    uploaded_or_path,
                    sheet_name=sheet,
                    dtype=str,
                    header=None
                )

                if df_tmp.empty:
                    continue

                df_tmp_limpio = df_tmp.dropna(how="all").dropna(axis=1, how="all")

                filas, columnas = df_tmp_limpio.shape
                score = filas * columnas

                print(f"Hoja revisada: {sheet} | filas={filas}, columnas={columnas}, score={score}")

                if filas < MIN_FILAS or columnas < MIN_COLUMNAS:
                    print(f"Descartando hoja pequeña: {sheet}")
                    continue

                if score > mejor_score:
                    mejor_score = score
                    mejor_df = df_tmp_limpio
                    mejor_hoja = sheet

            if mejor_df is None:
                raise ValueError(
                    f"No se ha encontrado ninguna hoja válida. Hojas disponibles: {xls.sheet_names}"
                )

            df = mejor_df
            print(f"Usando hoja: {mejor_hoja} | score={mejor_score}")

    # --- Detección automática de cabecera ---
    header_row = detect_header_row(df)
    if header_row is not None:
        df.columns = df.iloc[header_row]
        df = df.iloc[header_row + 1:].reset_index(drop=True)
    else:
        # fallback: usa la primera fila como cabecera
        df.columns = df.iloc[0]
        df = df.iloc[1:].reset_index(drop=True)
    
    df = df.dropna(axis=1, how="all")

    print('df original')
    print (df)

    return df, (header_row or 0)


def _guess_cols(df: pd.DataFrame):
    cols = list(df.columns)
    cleaned = {c: _clean(c) for c in cols}

    def find(patterns, prefer_qh_consumo=False):
        matches = []

        for c, cc in cleaned.items():
            for p in patterns:
                if re.search(p, cc, re.IGNORECASE):
                    matches.append(c)
                    break

        if not matches:
            return None
        
        col_consumo_total = None
        col_consumo_red = None

        for c in matches:
            cc = cleaned[c]

            if re.search(r"\bconsumo\s+total\b.*\(?kwh\)?", cc, re.IGNORECASE):
                col_consumo_total = c

            if re.search(r"\bconsumo\s+red\b.*\(?kwh\)?", cc, re.IGNORECASE):
                col_consumo_red = c

        if col_consumo_total is not None and col_consumo_red is not None:
            return col_consumo_red

        if col_consumo_red is not None:
            return col_consumo_red

        if prefer_qh_consumo:
            col_h = None
            col_qh = None

            for c in matches:
                cc = cleaned[c]

                if re.search(r"energia\s+activa\s+horaria\s*\(?kwh\)?", cc, re.IGNORECASE):
                    col_h = c

                if re.search(r"cuarto\s+horaria\s+activa", cc, re.IGNORECASE):
                    col_qh = c

            if col_h is not None and col_qh is not None:
                return col_qh

        return matches[0]
    
    c_dt = find([r"^fecha.?y.?hora$", r"fecha.?hora", r"^dia.?y.?hora$", r"datetime", r"timestamp", r"instante", r"^fecha.*", r"date"])
    c_date = find([r"fecha", r"^fecha$", r"dia", r"date", r"data"])
    c_time = find([r"hora", r"hour",r"hr", r"time", r"^h$"])
    #c_quarter = find([r"cuarto", r"q$", r"qh", r"15"])
    c_quarter = find([r"^cuarto$", r"q$", r"qh"])
    
    #c_kwh = find([r"consumo", r"energia", r"kwh", r"ae", r"active.?energy", r"importada", r"activa"])
    c_kwh = find(
        [r"consumo", r"AI", r"energia", r"kwh", r"ae", r"active.?energy", r"importada", r"activa", r"medida"],
        prefer_qh_consumo=True
    )
    c_per = find([r"periodo", r"^p$", r"^p[1-6]$"])
    c_ind = find(["reactiva", "kvarh", "inductiva"])
    c_cap = find(["capac"])
    #c_ver = find([r"gener", r"vertid", r"exportad", r"as", r"prod"])
    #c_ver = find([r"generaci[oó]n", r"vertid", r"exportad", r"as", r"prod"])
    c_ver = find([r"vertid", r"exporta"])
    c_gen = find(["generac"])

    print("\n--- Columnas originales ---")
    print(cols)
    print("\n--- Columnas limpias ---")
    for c, cc in cleaned.items():
        print(f"{c} → {cc}")

    return c_dt, c_date, c_time, c_quarter, c_kwh, c_per, c_ind, c_cap, c_ver, c_gen

def _parse_date_ddmmyyyy(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    mask_yyyy = s.str.match(r"^\d{1,2}/\d{1,2}/\d{4}$")
    s2 = s.copy()
    s2.loc[mask_yyyy] = s.loc[mask_yyyy].str.replace(
        r"^(\d{1,2})/(\d{1,2})/(\d{4})$", r"\3-\2-\1", regex=True
    )
    mask_yy = s2.str.match(r"^\d{1,2}/\d{1,2}/\d{2}$")
    if mask_yy.any():
        dt_yy = pd.to_datetime(s2.loc[mask_yy], format="%d/%m/%y", errors="coerce")
        s2.loc[mask_yy] = dt_yy.dt.strftime("%Y-%m-%d")
    return pd.to_datetime(s2, errors="coerce")

def _parse_time_to_hour(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    def h(x):
        if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", x):
            return int(x.split(":")[0])
        if re.fullmatch(r"\d{3,4}", x):
            return int(x[-4:-2])
        if re.fullmatch(r"\d{1,2}", x):
            return int(x)
        return np.nan
    hh = s.map(h).astype("float").clip(0, 24)
    return hh.astype("Int64")

def _localize_madrid(dt: pd.Series) -> pd.Series:
    """
    Mantiene los valores horarios tal como vienen, sin aplicar DST ni tz_localize.
    Garantiza 8760 filas y una progresión continua de fechas.
    """
    dt = pd.to_datetime(dt, errors="coerce")
    # No tocar DST ni tz
    return dt

# ------------------------------------
# FUNCIÓN PARA NORMALIZAR CURVA
# ------------------------------------

def normalize_curve_simple(uploaded, origin="archivo") -> tuple[pd.DataFrame, pd.DataFrame, str]:

    import traceback

    #Lee y normaliza la curva, devolviendo (df_in, df_norm).
    #   Regla simple:
    #     - Si el primer registro válido está a las 01:00 → restar 1h a toda la serie.
    #     - Si está a las 00:00 → no tocar.
    #   Detección automática de formato de fecha (día primero o año primero)."""
    
    df, header_row = _read_any(uploaded)
    c_dt, c_date, c_time, c_quarter, c_kwh, c_per, c_ind, c_cap, c_ver, c_gen = _guess_cols(df)

    if not (c_dt or (c_date and c_time)):
        raise ValueError("No se encontró columna de fecha u hora reconocible.")
    
    if not c_kwh:
        raise ValueError("No se encontró columna de consumo (kWh).")

    # --- Consumo ---
    kwh_consumo = pd.to_numeric(df[c_kwh].str.replace(",", ".", regex=False), errors="coerce")
    #kwh_vertido = pd.to_numeric(df[c_ver].str.replace(",", ".", regex=False), errors="coerce") if c_ver else np.nan
    #kwh_generacion = pd.to_numeric(df[c_gen].str.replace(",", ".", regex=False), errors="coerce") if c_gen else np.nan
    kwh_vertido = pd.to_numeric(df[c_ver].astype(str).str.replace(",", ".", regex=False), errors="coerce") if c_ver else pd.Series(0, index=df.index)
    kwh_generacion = pd.to_numeric(df[c_gen].astype(str).str.replace(",", ".", regex=False), errors="coerce") if c_gen else pd.Series(0, index=df.index)


    msg_unidades = ""

    if (header_row > 1) or ("wh" in str(c_kwh).lower() and "kwh" not in str(c_kwh).lower()):
        kwh_consumo = kwh_consumo / 1000
        kwh_vertido = kwh_vertido / 1000
        msg_unidades = "Detectado consumo en Wh → Convertido automáticamente a kWh"
        # Caso especial:
        # la columna detectada como generación realmente es vertido
        kwh_vertido = kwh_generacion / 1000

        # generación real no informada
        kwh_generacion = pd.Series(0, index=df.index)


    # Flag usado sólo en formatos hora y cuarto que creo solo son de endesa cuarto horarios, donde la energía viene como potencia cuartohoria (consumox4)
    endesa_qh = False
    try:
        # Determinamos el formato de fecha hora
        if c_dt:
            # Disponemos de fecha y hora en la misma columna
            sample = str(df[c_dt].dropna().iloc[0]).strip()
            print('Intentamos entrar por datetime')
            # Detectar si TIENE hora → patrón HH:MM
            tiene_hora = re.search(r"\d{1,2}:\d{2}", sample) is not None
    
            # 🟡 NUEVO: detectar hora 00:00:00 artificial (Excel)
            horas = pd.to_datetime(df[c_dt], errors="coerce").dt.hour
            hora_artificial = (
                horas.notna().all()
                and (horas == 0).all()
                and c_time is not None
            )

            #if tiene_hora:
            if tiene_hora and not hora_artificial:
                # Ahora sí: procesar como datetime completo
                if re.match(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", sample):
                    # Formato AAAA/MM/DD
                    dt0 = pd.to_datetime(df[c_dt], errors="coerce", dayfirst=False)
                else:
                    # Formato DD/MM/AAAA
                    dt0 = pd.to_datetime(df[c_dt], errors="coerce", dayfirst=True)
                
                print("Detectamos datetime fecha-hora")

            else:
                # SOLO FECHA → tratar como fecha + hora separadas
                print(f'Columna "{c_dt}" contiene solo fecha o contiene 00:00:00 (excel con sólo fecha) → pasamos a parseo por separado')
                raise ValueError("NO_DATETIME")

        else:
            # No hay columna datetime → pasar a fecha + hora separadas
            raise ValueError("NO_DATETIME")


    except ValueError as e:
        if str(e) == "NO_DATETIME":
            print("Entramos por fecha y hora separadas")

            # --- Caso cuartohorario explícito: HORA + CUARTO EN COLUMNAS SEPARADAS. CASO TIPO ENDESA QH---
            if c_time and c_quarter:
                print("Detectado formato cuartohorario (HORA + CUARTO)")

                d = _parse_date_ddmmyyyy(df[c_date])

                h = pd.to_numeric(df[c_time], errors="coerce").fillna(0)
                q = pd.to_numeric(df[c_quarter], errors="coerce").fillna(1)

                # CUARTO: 1–4 → minutos 0,15,30,45
                minutos = (q - 1) * 15

                dt0 = (
                    d
                    + pd.to_timedelta(h, unit="h")
                    + pd.to_timedelta(minutos, unit="m")
                )

                print("DEBUG --- dt0 cuartohorario:")
                print(dt0.head(12))
                
                endesa_qh = True

            else:
                # --- Fecha y hora en columnas separadas. CASO HABITUAL ---
                d = _parse_date_ddmmyyyy(df[c_date])
                print('Datos de la columna fecha')
                print(d.head(24))

                hora_raw = df[c_time].astype(str).str.strip()
                print('hora_raw')
                print(hora_raw)

                # --- Corregir valores 24:00 ---
                mask_24 = hora_raw.isin(["24:00", "24:00:00"])
                if mask_24.any():
                    hora_raw.loc[mask_24] = "00:00"
                    d.loc[mask_24] = d.loc[mask_24] + pd.Timedelta(days=1)
                    print('Datos de la columna fecha con retoque 24:00 (tipo DATADIS)')
                    print(d.head(96))
                    print('Columna hora modificada (origen 24:00)')
                    print(hora_raw.head(96))

                # Detectar casos con formato HH:MM o HH:MM:SS
                if hora_raw.str.contains(":").any():
                    print("La columna hora contiene ':'")
                    #print(d.head(24))

                    minutos = hora_raw.str.extract(r":(\d{2})")[0].astype(float)

                    if minutos.max() == 0:
                        # Horario tipo “01:00”
                        print("Registros horarios")
                        #dt0 = d + pd.to_timedelta(hora_raw +":00", errors="coerce")
                        #dt0 = d + pd.to_timedelta(hora_raw, errors="coerce")
                        hora_norm = hora_raw.copy()

                        # HH:MM → añadir segundos
                        mask_horario = hora_norm.str.count(":") == 1
                        hora_norm.loc[mask_horario] = hora_norm.loc[mask_horario] + ":00"

                        dt0 = d + pd.to_timedelta(hora_norm, errors="coerce")
                        print(dt0)

                        # Ajuste por casos 01:00→00:00 del día siguiente
                        if dt0.dt.hour.min() == 1:
                            print('Hora mínima = 1')
                            dt0 = dt0 - pd.Timedelta(hours=1)
                    else:
                        # Cuartohoraria (00:15, 00:30…)
                        print("Registros cuarto horarios")
                        hora_norm = hora_raw.copy()

                        # HH:MM → añadir segundos
                        mask_horario = hora_norm.str.count(":") == 1
                        hora_norm.loc[mask_horario] = hora_norm.loc[mask_horario] + ":00"
                        #h = pd.to_timedelta(hora_raw, errors="coerce")
                        h = pd.to_timedelta(hora_norm, errors="coerce")
                        if h.isna().any():
                            print("🚨 HORAS PROBLEMÁTICAS:")
                            print(hora_norm[h.isna()].unique())
                        #print(repr(hora_raw.iloc[0]))
                        #print(type(hora_raw))
                        #print(hora_raw.dtype)
                        #print(type(hora_raw.iloc[0]))
                        #print(pd)
                        #print(pd.to_timedelta("0:15"))                # debería funcionar
                        #print(pd.to_timedelta(["0:15", "1:30"]))     # prueba lista
                        dt0 = d + h

                        print("DEBUG --- dt0 primeras filas:")
                        print(dt0.head(96))

                else:
                    # Horas numéricas (1–24)
                    h = _parse_time_to_hour(df[c_time]).fillna(0)
                    dt0 = d + pd.to_timedelta(h, unit="h")

                    #print("DEBUG --- dt0 primeras filas:")
                    #print(dt0.head(96))
                    #print("DEBUG --- diferencias en minutos:")
                    #print(dt0.diff().dt.total_seconds().head(10))
    
    except Exception as e:
        print("ERROR DETECTADO:")
        traceback.print_exc()
        raise

    #print(df[c_date].head())
    
    #print(_parse_date_ddmmyyyy(df[c_date]).head())
    #print (dt0)

    # --- df_in solo para vista previa ---
    df_in = df.copy()
    #print('df in')
    #print(df_in)


    # --- DETECTAR RESOLUCIÓN TEMPORAL ---
    # Diferencia media en minutos
    delta_min = (dt0.diff().dt.total_seconds().dropna().median() / 60)
    if abs(delta_min - 60) < 1:
        freq = "H"      # Horaria
        ajuste_tiempo = pd.Timedelta(hours=1)
    elif abs(delta_min - 15) < 1:
        freq = "QH"    # Cuartohoraria
        ajuste_tiempo = pd.Timedelta(minutes=15)
    elif abs(delta_min - 10) < 1:
        freq = "10MIN"  # Diezminutal
        ajuste_tiempo = pd.Timedelta(minutes=10)
    else:
        freq = "desconocida"
        ajuste_tiempo = pd.Timedelta(0)
        st.warning("Frecuencia no reconocida. No se aplica ajuste temporal.")

    print(f'Frecuencia detectada: {freq}')

    if dt0.dt.hour.min() == 1:
        # Formato 1–24 → ajustar 24:00
        if dt0.dt.hour.max() in [0, 24]:
            dt0 = dt0 - ajuste_tiempo

    # 2) Buscar primer datetime válido y su hora
    first_valid = dt0.dropna().iloc[0] if dt0.notna().any() else pd.NaT
    h0 = int(first_valid.hour) if pd.notna(first_valid) else 0

    if freq == "H":
        # si empieza en 01:00, corregir desplazando 1h atrás
        if h0 == 1:
            dt_adj = dt0 - pd.Timedelta(hours=1)
        else:
            dt_adj = dt0.copy()
    elif freq == "QH":
        # si empieza en 00:15, corregir desplazando 15min atrás
        if first_valid.minute == 15:
            dt_adj = dt0 - pd.Timedelta(minutes=15)
        else:
            dt_adj = dt0.copy()
    elif freq == "10MIN":
        # si empieza en 00:10, corregir desplazando 10min atrás
        if first_valid.minute == 10:
            dt_adj = dt0 - pd.Timedelta(minutes=10)
        else:
            dt_adj = dt0.copy()
    else:
        dt_adj = dt0.copy()

    # Redondeo y TZ
    # Redondeo
    PANDAS_FREQ = {
        "H": "H",
        "QH": "15T",
        "10MIN": "10T"
    }
    dt_adj = dt_adj.dt.floor(PANDAS_FREQ[freq])
    dt_tz = _localize_madrid(dt_adj)

    # obtención de periodos------------------------------------------------
    if c_per:
        periodo_raw = df[c_per].astype(str).str.strip().str.lower()

        # 🔁 Equivalencias para tarifas 2.0TD (domésticas)
        mapa_periodos_3P = {
            "punta": "1",
            "llano": "2",
            "valle": "3"
        }

        # Sustituir nombres por equivalencias numéricas si existen
        periodo_raw = periodo_raw.replace(mapa_periodos_3P)

        periodo = (
            periodo_raw
            .astype(str)
            .str.extract(r"(\d+)", expand=False)   # extrae solo los números
            .fillna("")                            # rellena vacíos
            .astype(str)                           # deja como texto limpio (no float)
            .replace("", np.nan)                   # vuelve a NaN los vacíos
        )
        # Añadir prefijo 'P' si hay número
        periodo = periodo.apply(lambda x: f"P{int(x)}" if pd.notna(x) and x.isdigit() else np.nan)
        df_periodos=pd.DataFrame()

        flag_periodos_en_origen = True
        
    else:
        # Si NO hay columna de periodo, cargar desde el Excel de periodos
        flag_periodos_en_origen = False
        try:
            # Puedes definir esta ruta al inicio del script
            periodos_path = "utils/periodos_horarios.xlsx"
            df_periodos = pd.read_excel(periodos_path, dtype={"año": int, "mes": int, "dia": int, "hora": int, "dh_3p": str, "dh_6p": str})

            
            #df_periodos["fecha_hora"] = pd.to_datetime(
            #    df_periodos["fecha"].astype(str) + " " + df_periodos["hora"].astype(str) + ":00",
            #    errors="coerce",
            #    dayfirst=True)

            # --- Compatibilidad con curvas horarias y cuartohorarias ---
            # Si el fichero tiene horas tipo 0–23, convertir a datetime horario
            if df_periodos["hora"].dtype in [int, float] or df_periodos["hora"].astype(str).str.match(r"^\d+$").all():
                df_periodos["fecha_hora"] = pd.to_datetime(
                    df_periodos["fecha"].astype(str) + " " + df_periodos["hora"].astype(str) + ":00:00",
                    errors="coerce",
                    dayfirst=True
                )
            else:
                # Si las horas incluyen formato "HH:MM", lo respetamos
                hora_aux = df_periodos["hora"].astype(str).str.strip()
                df_periodos["fecha_hora"] = pd.to_datetime(
                    df_periodos["fecha"].astype(str) + " " +
                    hora_aux.where(hora_aux.str.count(":") == 2, hora_aux + ":00"),
                    errors="coerce",
                    dayfirst=True
                )


            periodo = np.nan

            #print(df_periodos)
                        
            #periodo = df_merge["periodo"].astype(str).str.upper().str.strip()

            #msg_periodos = 'Cargados periodos desde fichero auxiliar. Seleccione modo 3P/6P'
        except Exception as e:
            st.warning(f"No se pudieron cargar los periodos: {e}")
            periodo = np.nan
    
    # --- NUEVO BLOQUE: Determinación del ATR según periodos detectados ---
    #try:
    if isinstance(periodo, pd.Series):
        # Extraemos el número del periodo (P1→1, etc.)
        numeros = periodo.dropna().str.extract(r"P(\d+)")[0].astype(float)
        if not numeros.empty and numeros.max() == 3:
            st.sidebar.warning("La curva parece compatible con 2.0TD (3 periodos). Verifique el ATR seleccionado.")
                #atr_dfnorm = "2.0"
            #else:
            #    atr_dfnorm = None
        #else:
            #atr_dfnorm = None
    #except Exception as e:
    #    atr_dfnorm = None
    #    print(f"Error determinando ATR: {e}")

    ind = pd.to_numeric(df[c_ind], errors="coerce") if c_ind else np.nan
    cap = pd.to_numeric(df[c_cap], errors="coerce") if c_cap else np.nan

    # --- df_norm con índice numérico (igual que df_in) ---
    df_norm = pd.DataFrame({
        "fecha_hora": dt_tz,
        "consumo_kWh": kwh_consumo,
        "excedentes_kWh": kwh_vertido,
        "generacion_kWh": kwh_generacion,
        "reactiva_kVArh": ind,
        "capacitiva_kVArh": cap,
        "periodo": periodo
    }).sort_values("fecha_hora").reset_index(drop=True)

    # Extraer la hora (0–23)
    df_norm["hora"] = df_norm["fecha_hora"].dt.hour
    # Extraer la fecha
    df_norm["fecha"] = df_norm["fecha_hora"].dt.date

    # --- Clasificación de tipo de día (laboral o fin de semana)
    df_norm["tipo_dia"] = np.where(
        df_norm["fecha_hora"].dt.dayofweek < 5, "L-V", "FS"  # 0=lunes, 6=domingo
    )
    
    # usado cuando la energía viene como potencia cuarto horaria
    if endesa_qh:
        df_norm["consumo_kWh"] /= 4
    
    # --- Cálculo del saldo horario (consumo - vertido) ---
    saldo_horario = df_norm["consumo_kWh"].fillna(0) - df_norm["excedentes_kWh"].fillna(0)

    # --- Columnas “shadow” ---
    df_norm["consumo_neto_kWh"] = np.where(saldo_horario > 0, saldo_horario, 0)
    df_norm["vertido_neto_kWh"] = np.where(saldo_horario < 0, -saldo_horario, 0)

    
    #print('atr dentro de la función')    
    #print(atr_dfnorm)

    print('df norm dentro de la funcion')
    print(df_norm)


    #return df_in, df_norm, msg_unidades, flag_periodos_en_origen, df_periodos, atr_dfnorm, freq
    return df_in, df_norm, msg_unidades, flag_periodos_en_origen, df_periodos, freq

# ================================================================================
# GRÁFICOS
#=================================================================================


def graficar_curva_horaria(df, frec):

    #df_plot = df.reset_index()
    df_plot = df.copy()

    #Seleccionar paleta de colores
    colores_periodo = COLORES_3P if st.session_state.atr_dfnorm == "2.0" else COLORES_6P
    orden_periodos = list(colores_periodo.keys())
    df_plot['periodo'] = pd.Categorical(
        df_plot['periodo'],
        categories=orden_periodos,
        ordered=True
    )


    #titulo = (
    #    "Curva cuarto horaria de consumo (kWh)"
    #    if frec == "QH"
    #    else "Curva horaria de consumo (kWh)"
    #)
    titulo = 'Curva HORARIA de consumo (kWh)'

    fig = px.bar(
        df_plot,
        x="fecha_hora",
        y="consumo_neto_kWh",
        color="periodo",
        color_discrete_map=colores_periodo,
        category_orders={"periodo": orden_periodos},
        labels={
            "fecha_hora": "Fecha y hora",
            "consumo_neto_kWh": "Consumo NETO (kWh)"
        },
        title=titulo
    )

    fig.update_layout(
        bargap=0.1,
        legend=dict(
            orientation="h",
            y=1.15,
            x=0.5,
            xanchor="center",
            title_text=""
        ),
    )

    fig = aplicar_estilo(fig)

    return fig

def graficar_queso_periodos(df_norm):

    
    # Agrupar por periodo
    df_periodos = (
        df_norm.groupby("periodo", as_index=False)["consumo_neto_kWh"]
        .sum()
        .sort_values("periodo")
    )

    # Ordenar los periodos de P1 a P6 según el orden lógico
    orden = [f"P{i}" for i in range(1, 7)]
    df_periodos["periodo"] = pd.Categorical(df_periodos["periodo"], categories=orden, ordered=True)
    df_periodos = df_periodos.sort_values("periodo")

    # Calcular porcentaje
    total = df_periodos["consumo_neto_kWh"].sum()
    df_periodos["porcentaje"] = (df_periodos["consumo_neto_kWh"] / total * 100).round(1)

    #Seleccionar paleta de colores
    colores_periodo = COLORES_3P if st.session_state.atr_dfnorm == "2.0" else COLORES_6P

    # Gráfico tipo “queso”
    fig = px.pie(
        df_periodos,
        names="periodo",
        values="consumo_neto_kWh",
        color="periodo",
        color_discrete_map=colores_periodo,
        title="Consumo por periodo tarifario",
        hole=0.5,
        category_orders={"periodo": orden}  # 👈 este es el truco
    )

    # Etiquetas con porcentaje y kWh
    fig.update_traces(
        textinfo="label+percent",
        hovertemplate="%{label}<br>%{value:,.0f} kWh<br>(%{percent})"
    )

    # 🔹 Añadir texto central con el total
    fig.add_annotation(
        #text=f"<b>{int(total):,} kWh</b>".replace(",", "."),
        text=f"<b>{int(total):,} kWh</b>",
        showarrow=False,
        font=dict(size=18)
    )

    fig = aplicar_estilo(fig)
    fig = aplicar_texto_pie_porcentaje(fig, size=16)

    return fig, df_periodos

def graficar_diario_apilado(df_norm):

    df_plot = (
        df_norm
        .reset_index()
        .assign(dia=lambda d: d["fecha_hora"].dt.date)
        .groupby(["dia", "periodo"], as_index=False)["consumo_neto_kWh"]
        .sum()
    )

    #Seleccionar paleta de colores
    colores_periodo = COLORES_3P if st.session_state.atr_dfnorm == "2.0" else COLORES_6P

    orden_periodos = list(colores_periodo.keys())
    df_plot["periodo"] = pd.Categorical(
        df_plot["periodo"],
        categories=orden_periodos,
        ordered=True
    )

    fig = px.bar(
        df_plot,
        x="dia",
        y="consumo_neto_kWh",
        color="periodo",
        color_discrete_map=colores_periodo,
        category_orders={"periodo": orden_periodos},
        labels={
            "dia": "Día",
            "consumo_kWh": "Consumo diario (kWh)"
        },
        title="Consumo diario por periodos (kWh)"
    )

    fig.update_layout(
        bargap=0.2,
        legend=dict(
            orientation="h",
            y=1.15,
            x=0.5,
            xanchor="center",
            title_text=""
        )
    )
    fig.update_yaxes(tickformat=",.0f")

    fig = aplicar_estilo(fig)

    return fig


def graficar_mensual_apilado(df_norm):

    df_plot = (
        df_norm
        .assign(
            mes=lambda d: d["fecha_hora"].dt.to_period("M").dt.to_timestamp()
        )
        .groupby(["mes", "periodo"], as_index=False)["consumo_neto_kWh"]
        .sum()
    )

    #Seleccionar paleta de colores
    colores_periodo = COLORES_3P if st.session_state.atr_dfnorm == "2.0" else COLORES_6P
    
    # Orden lógico de periodos
    orden_periodos = list(colores_periodo.keys())
    df_plot["periodo"] = pd.Categorical(
        df_plot["periodo"],
        categories=orden_periodos,
        ordered=True
    )

    # Etiqueta de mes bonita
    df_plot["Mes"] = df_plot["mes"].dt.strftime("%b %Y")

    fig = px.bar(
        df_plot,
        x="mes",
        y="consumo_neto_kWh",
        color="periodo",
        color_discrete_map=colores_periodo,
        category_orders={"periodo": orden_periodos},
        labels={
            "Mes": "Mes",
            "consumo_neto_kWh": "Consumo mensual (kWh)"
        },
        title="Consumo mensual por periodos (kWh)"
    )

    fig.update_layout(
        bargap=0.3,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            title_text=""
        )
    )

    

    fig = aplicar_estilo(fig)
    
    return fig


def tabla_mensual_periodos(df_norm, columna_valor="consumo_neto_kWh"):

    if columna_valor not in df_norm.columns:
        return None

    df_plot = (
        df_norm
        .assign(
            mes=lambda d: d["fecha_hora"].dt.to_period("M").dt.to_timestamp()
        )
        .groupby(["mes", "periodo"], as_index=False)[columna_valor]
        .sum()
    )

    colores_periodo = COLORES_3P if st.session_state.atr_dfnorm == "2.0" else COLORES_6P
    orden_periodos = list(colores_periodo.keys())

    df_plot["periodo"] = pd.Categorical(
        df_plot["periodo"],
        categories=orden_periodos,
        ordered=True
    )

    tabla = (
        df_plot
        .pivot_table(
            index="mes",
            columns="periodo",
            values=columna_valor,
            aggfunc="sum",
            fill_value=0,
            observed=False
        )
        .reset_index()
    )

    # Por seguridad, asegurar que existen todas las columnas P1...P6/P1...P3
    for p in orden_periodos:
        if p not in tabla.columns:
            tabla[p] = 0

    tabla["Total"] = tabla[orden_periodos].sum(axis=1)

    tabla["Mes"] = tabla["mes"].dt.strftime("%b %Y")

    tabla = tabla[["Mes"] + orden_periodos + ["Total"]]

    return tabla

def formatear_tabla_mensual_es(df_tabla, col_mes="Mes"):

    MESES_ES = {
        1: "ene", 2: "feb", 3: "mar", 4: "abr",
        5: "may", 6: "jun", 7: "jul", 8: "ago",
        9: "sep", 10: "oct", 11: "nov", 12: "dic"
    }

    df_fmt = df_tabla.copy()

    # Si la columna de mes es datetime, la pasamos a formato español.
    # Si ya es texto, la dejamos tal cual.
    if col_mes in df_fmt.columns:

        if pd.api.types.is_datetime64_any_dtype(df_fmt[col_mes]):
            df_fmt["Mes"] = (
                df_fmt[col_mes].dt.month.map(MESES_ES).str.capitalize()
                + " "
                + df_fmt[col_mes].dt.year.astype(str)
            )

            # Solo eliminar col_mes si NO es ya "Mes"
            if col_mes != "Mes":
                df_fmt = df_fmt.drop(columns=[col_mes])

        else:
            # Si ya viene como texto tipo "Apr 2025", no tocamos el mes
            if col_mes != "Mes":
                df_fmt = df_fmt.rename(columns={col_mes: "Mes"})

    # Formatear solo columnas numéricas / periodos
    cols_num = [c for c in df_fmt.columns if c != "Mes"]

    for col in cols_num:
        df_fmt[col] = (
            pd.to_numeric(df_fmt[col], errors="coerce")
            .fillna(0)
            .round(0)
            .astype(int)
            .map(lambda x: f"{x:,.0f}".replace(",", "."))
        )

    return df_fmt


# ====================================================================================================================
# SECCIÓN AUTOCONSUMO
# ====================================================================================================================
def graficar_dem_ver_mensual(df_norm, colores_energia):

    nombres_energia = {
        "demanda_neto_kWh": "Demanda",
        "vertido_neto_kWh": "Vertido"
    }

    df_plot = (
        df_norm
        .assign(
            mes=lambda d: d["fecha_hora"].dt.to_period("M").dt.to_timestamp()
        )
        .groupby(["mes"], as_index=False)[["demanda_neto_kWh", "vertido_neto_kWh"]]
        .sum()
    )

    # Etiqueta de mes bonita
    #df_plot["Mes"] = df_plot["mes"].map(formato_mes_es)
    df_plot["Mes"] = df_plot["mes"].dt.strftime("%b %Y")

    fig = px.bar(
        df_plot,
        x="Mes",
        y=["demanda_neto_kWh", "vertido_neto_kWh"],
        color_discrete_map=colores_energia,
        labels={
            "Mes": "Mes",
            "value": "Energía (kWh)",
            "variable": ""
        },
        title="Demanda/Vertido mensual (kWh)"
    )

    fig.for_each_trace(
        lambda trace: trace.update(
            name=nombres_energia.get(trace.name, trace.name),
            legendgroup=nombres_energia.get(trace.name, trace.name),
            hovertemplate=(
                "<b>Mes:</b> %{x}<br>"
                f"<b>{nombres_energia.get(trace.name, trace.name)}:</b> "
                "%{y:,.0f} kWh"
                "<extra></extra>"
            )
        )
    )

    fig.update_layout(
        barmode="stack",
        bargap=0.3,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            title_text=""
        )
    )

    fig.update_yaxes(tickformat=",.0f")

    fig = aplicar_estilo(fig)

    return fig

def graficar_con_gen_mensual(df_norm, colores_energia):

    nombres_energia = {
        "consumo_neto_kWh": "Consumo",
        "generacion_kWh": "Generación"
    }

    df_plot = (
        df_norm
        .assign(
            mes=lambda d: d["fecha_hora"].dt.to_period("M").dt.to_timestamp()
        )
        .groupby(["mes"], as_index=False)[["consumo_neto_kWh", "generacion_kWh"]]
        .sum()
    )

    # Etiqueta de mes bonita
    df_plot["Mes"] = df_plot["mes"].dt.strftime("%b %Y")

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=df_plot["Mes"],
            y=df_plot["consumo_neto_kWh"],
            mode="lines",
            name="Consumo",
            line=dict(
                color=colores_energia.get("consumo_neto_kWh", "#3498DB"),
                width=3
            ),
            fill="tozeroy",
            fillcolor="rgba(52, 152, 219, 0.35)",
            hovertemplate=(
                "<b>Mes:</b> %{x}<br>"
                "<b>Consumo:</b> %{y:,.0f} kWh"
                "<extra></extra>"
            )
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df_plot["Mes"],
            y=df_plot["generacion_kWh"],
            mode="lines",
            name="Generación",
            line=dict(
                color=colores_energia.get("generacion_kWh", "#F7DC6F"),
                width=3
            ),
            fill="tozeroy",
            fillcolor="rgba(247, 220, 111, 0.35)",
            hovertemplate=(
                "<b>Mes:</b> %{x}<br>"
                "<b>Generación:</b> %{y:,.0f} kWh"
                "<extra></extra>"
            )
        )
    )

    fig.update_layout(
        title="Consumo/Generación mensual (kWh)",
        xaxis_title="Mes",
        yaxis_title="Energía (kWh)",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            title_text=""
        )
    )

    fig.update_yaxes(tickformat=",.0f")

    fig = aplicar_estilo(fig)

    return fig




def graficar_dem_ver(df, colores_energia=None):

    df_plot = df.copy()

    if colores_energia is None:
        colores_energia = {
            "demanda_neto_kWh": "#E67E22",
            "vertido_neto_kWh": "#AF7AC5",
        }

    titulo = "Curva horaria de demanda / vertido (kWh)"

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=df_plot["fecha_hora"],
            y=df_plot["demanda_neto_kWh"],
            name="Demanda",
            marker_color=colores_energia.get("demanda_neto_kWh")
        )
    )

    fig.add_trace(
        go.Bar(
            x=df_plot["fecha_hora"],
            y=df_plot["vertido_neto_kWh"],
            name="Vertido",
            marker_color=colores_energia.get("vertido_neto_kWh")
        )
    )

    fig.update_layout(
        title=titulo,
        bargap=0.1,
        legend=dict(
            orientation="h",
            y=1.02,
            x=0.5,
            xanchor="center",
            title_text=""
        ),
        xaxis_title="Fecha y hora",
        yaxis_title="kWh",
        barmode="relative"
    )

    fig = aplicar_estilo(fig)

    return fig

def graficar_con_gen(df, colores_energia=None):

    

    df_plot = df.copy()

    if colores_energia is None:
        colores_energia = {
            "consumo_neto_kWh": "#3498DB",
            "generacion_kWh": "#F7DC6F",
        }

    titulo = "Curva horaria de consumo / generación (kWh)"

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=df_plot["fecha_hora"],
            y=df_plot["consumo_neto_kWh"],
            name="Consumo",
            marker_color=colores_energia.get("consumo_neto_kWh")
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df_plot["fecha_hora"],
            y=df_plot["generacion_kWh"],
            name="Generación",
            mode="lines",
            line=dict(
                color=colores_energia.get("generacion_kWh"),
                width=3
            )
        )
    )

    fig.update_layout(
        title=titulo,
        bargap=0.1,
        legend=dict(
            orientation="h",
            y=1.02,
            x=0.5,
            xanchor="center",
            title_text=""
        ),
        xaxis_title="Fecha y hora",
        yaxis_title="kWh"
    )

    fig = aplicar_estilo(fig)

    return fig




def graficar_media_horaria(tipo_dia, ymax=None, ordenar=False):
    
    df = st.session_state.df_norm_h.copy()
    # Filtrar según opción
    if tipo_dia == "L-V":
        df_sel = df[df["tipo_dia"] == "L-V"].copy()
        add_title='LUNES A VIERNES'
    elif tipo_dia == "FS":
        df_sel = df[df["tipo_dia"] == "FS"].copy()
        add_title='FIN DE SEMANA'
    else:
        df_sel = df.copy()
        add_title='TOTAL'

    # Calcular media por hora
    df_horas = (df_sel.resample("H", on="fecha_hora")["consumo_neto_kWh"].sum().reset_index())
    df_horas["hora"] = df_horas["fecha_hora"].dt.hour
    df_horas = (
        df_horas.groupby("hora", as_index=False)["consumo_neto_kWh"]
        .mean()
        .rename(columns={"consumo_neto_kWh": "media_kWh"})
    )

    # 🔑 ORDENACIÓN OPCIONAL
    if ordenar:
        df_horas = df_horas.sort_values("media_kWh", ascending=False)
        df_horas["hora_cat"] = df_horas["hora"].astype(str)
        x_col = "hora_cat"
        title = "Hora del día (ordenada por consumo)"
    else:
        x_col = "hora"
        title = f"Perfil medio horario: <span style='color:orange'>{add_title}</span>"
    # Gráfico
    
    fig = px.bar(
        df_horas,
        #x="hora",
        x=x_col,
        y="media_kWh",
        labels={"hora": "Hora del día", "media_kWh": "Consumo medio (kWh)"},
        color="media_kWh",
        color_continuous_scale="Blues",
        #title=f"Perfil medio horario: {add_title}"
    )

    if ymax is None:
        ymax = df_horas["media_kWh"].max() * 1.05

    fig.update_layout(
        title=dict(
            #text=f"Perfil medio horario: <span style='color:orange'>{add_title}</span>",
            text=title,
            x=0.5,
            xanchor="center"
        ),
        #xaxis=dict(dtick=1),
        yaxis_title="kWh medios",
        coloraxis_showscale=False,
        yaxis=dict(
            range=[0, ymax]
        ),
        separators=",."

    )
    # 🔒 Forzar orden solo si ordenar=True
    if ordenar:
        fig.update_xaxes(
            type='category',
            categoryorder="array",
            categoryarray=df_horas["hora_cat"].tolist()
        )
    else:
        fig.update_xaxes(dtick=1)
    
    fig.update_traces(
        hovertemplate=(
            "<b>Hora:</b> %{x}:00<br>"
            "<b>Consumo medio:</b> %{y:.2f} kWh"
            "<extra></extra>"
        )
    )

    fig = aplicar_estilo(fig)

    return fig

def graficar_media_horaria_combinada():
    
    df = st.session_state.df_norm_h.copy()

    def perfil_por_tipo(df, filtro=None):
        if filtro is not None:
            df = df[df["tipo_dia"] == filtro].copy()

        df_h = (
            df.resample("H", on="fecha_hora")["consumo_neto_kWh"]
            .sum()
            .reset_index()
        )
        df_h["hora"] = df_h["fecha_hora"].dt.hour

        return (
            df_h.groupby("hora", as_index=False)["consumo_neto_kWh"]
            .mean()
            .rename(columns={"consumo_neto_kWh": "media_kWh"})
        )

    # Perfiles
    df_lv = perfil_por_tipo(df, "L-V")
    df_lv["perfil"] = "L-V"

    df_fs = perfil_por_tipo(df, "FS")
    df_fs["perfil"] = "FS"

    df_total = perfil_por_tipo(df)
    df_total["perfil"] = "TOTAL"

    ymax = df_total["media_kWh"].max() * 1.05
    ymin = 0

    # Unimos
    df_plot = pd.concat([df_lv, df_fs, df_total], ignore_index=True)

    # Gráfico
    fig = px.line(
        df_plot,
        x="hora",
        y="media_kWh",
        color="perfil",
        labels={
            "hora": "Hora del día",
            "media_kWh": "Consumo medio (kWh)",
            "perfil": "Tipo de día"
        },
        title="Perfil medio horario: L-V vs Fin de Semana"
    )

    # Estilo de líneas
    fig.update_traces(line=dict(width=3))

    # Colores manuales
    fig.for_each_trace(lambda t: t.update(
        line=dict(
            color={
                "L-V": "#6a0dad",   # morado
                "FS": "#2e8b57",    # verde
                "TOTAL": "#999999" # gris apagado
            }[t.name]
        ),
        visible="legendonly" if t.name == "TOTAL" else True
    ))

    fig.update_layout(
        xaxis=dict(dtick=1),
        yaxis_title="kWh medios",
        yaxis=dict(
            range=[ymin, ymax]
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5
        )
    )

    return fig, ymax


def graficar_ranking_horas_consumo(tipo_dia, ymax=None):
    
    df = st.session_state.df_norm_h.copy()

    # Filtro por tipo de día
    if tipo_dia == "L-V":
        df_sel = df[df["tipo_dia"] == "L-V"].copy()
        add_title = "LUNES A VIERNES"
    elif tipo_dia == "FS":
        df_sel = df[df["tipo_dia"] == "FS"].copy()
        add_title = "FIN DE SEMANA"
    else:
        df_sel = df.copy()
        add_title = "TOTAL"

    # Media por hora (misma lógica que perfil)
    df_horas = (
        df_sel
        .resample("H", on="fecha_hora")["consumo_kWh"]
        .sum()
        .reset_index()
    )
    df_horas["hora"] = df_horas["fecha_hora"].dt.hour

    df_horas = (
        df_horas
        .groupby("hora", as_index=False)["consumo_kWh"]
        .mean()
        .rename(columns={"consumo_kWh": "media_kWh"})
        .sort_values("media_kWh", ascending=True)
    )

    if ymax is None:
        ymax = df_horas["media_kWh"].max() * 1.05

    # Gráfico vertical ordenado
    fig = px.bar(
        df_horas,
        x="hora",
        y="media_kWh",
        labels={
            "hora": "Hora del día (ordenada por consumo)",
            "media_kWh": "Consumo medio (kWh)"
        },
        color="media_kWh",
        color_continuous_scale="Blues"
    )

    # 🔑 Forzar orden del eje X
    fig.update_layout(
        title=dict(
            text=f"Ranking de horas por consumo medio: <span style='color:orange'>{add_title}</span>",
            x=0.5
        ),
        xaxis=dict(
            categoryorder="array",
            categoryarray=df_horas["hora"].astype(str).tolist(),
            dtick=1
        ),
        yaxis=dict(
            range=[0, ymax],
            title="kWh medios"
        ),
        coloraxis_showscale=False
    )

    return fig


def graficar_boxplot_horario(tipo_dia):
    
    df = st.session_state.df_norm_h.copy()

    if tipo_dia == "L-V":
        df = df[df["tipo_dia"] == "L-V"]
        add_title = "LUNES A VIERNES"
    elif tipo_dia == "FS":
        df = df[df["tipo_dia"] == "FS"]
        add_title = "FIN DE SEMANA"
    else:
        add_title = "TOTAL"

    df["hora"] = df["fecha_hora"].dt.hour

    fig = px.box(
        df,
        x="hora",
        y="consumo_neto_kWh",
        points="outliers",   # o False si lo quieres más limpio
        labels={
            "hora": "Hora del día",
            "consumo_kWh": "Consumo (kWh)"
        }
    )

    fig.update_layout(
        title=dict(
            text=f"Distribución del consumo por hora: <span style='color:orange'>{add_title}</span>",
            x=0.5,
            xanchor='center'
        ),
        xaxis=dict(dtick=1)
    )

    return fig


def graficar_heatmap_dia_hora(tipo_dia='Todos', zmax=None):
    df = st.session_state.df_norm_h.copy()

    if tipo_dia != 'Todos':
        df = df[df['tipo_dia'] == tipo_dia]

    df["fecha"] = pd.to_datetime(df["fecha"])
    df["hora"] = df["hora"].astype(int)

    tabla = df.pivot_table(
        index="fecha",
        columns="hora",
        values="consumo_neto_kWh",
        aggfunc="mean"
    )
    tabla = tabla.sort_index()
    tabla = tabla.reindex(columns=range(24))

    df["fecha"] = pd.to_datetime(df["fecha"])
    df["fecha_hover"] = df["fecha"].dt.strftime("%d.%m.%Y")

    mapa_dias = {
        0: "Lunes",
        1: "Martes",
        2: "Miércoles",
        3: "Jueves",
        4: "Viernes",
        5: "Sábado",
        6: "Domingo"
    }

    df["dia_semana_hover"] = df["fecha"].dt.dayofweek.map(mapa_dias)
    df["hover_info"] = df["fecha_hover"] + " · " + df["dia_semana_hover"]

    tabla_fecha_hover = df.pivot_table(
        index="fecha",
        columns="hora",
        #values="fecha_hover",
        values="hover_info",
        aggfunc="first"
    )
    tabla_fecha_hover = tabla_fecha_hover.reindex(index=tabla.index, columns=tabla.columns)

    fig = px.imshow(
        tabla,
        aspect="auto",
        color_continuous_scale="YlOrRd",
        zmin=0,
        zmax=zmax,
        labels=dict(
            x="Hora",
            y="Fecha",
            color="kWh"
        ),
        
    )

    
    fig.update_traces(
        customdata=tabla_fecha_hover.values,
        hovertemplate=(
            "<b>%{customdata}</b><br>"
            "Hora: %{x}:00<br>"
            "Consumo: %{z:.2f} kWh"
            "<extra></extra>"
        )
    )



    titulo_map = {
        "Todos": "TOTAL",
        "L-V": "LUNES A VIERNES",
        "FS": "FIN DE SEMANA"
    }

    titulo = f"Distribución horaria del consumo: <span style='color:#ffc107'>{titulo_map.get(tipo_dia, tipo_dia)}</span>"

    fig.update_layout(
        title=dict(
            text=titulo,
            x=0.5,
            xanchor="center",
            font=dict(size=16, color="white")
        ),
        template="plotly_dark",
        height=800,
        margin=dict(l=10, r=10, t=80, b=20),
        coloraxis_colorbar=dict(
            title=dict(text="Consumo (kWh)", side="top"),
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.04,
            yanchor="bottom",
            len=0.65,
            thickness=12
        ),
        
    )

    fig.update_xaxes(
        title="Hora del día",
        tickmode="linear",
        dtick=2
    )


    df_ticks = (
        pd.DataFrame({"fecha": tabla.index})
        .assign(mes=lambda x: x["fecha"].dt.to_period("M"))
        .groupby("mes")["fecha"]
        .min()
        .reset_index()
    )

    fig.update_yaxes(
        title="Fecha",
        tickmode="array",
        tickvals=df_ticks["fecha"],
        ticktext=[f.strftime("%b %Y") for f in df_ticks["fecha"]]
    )

    return fig



def calcular_patron_horario_boxplot(df=None, variable="consumo_neto_kWh"):
    """
    Calcula el patrón horario de consumo por tipo de día y hora usando criterios de boxplot.

    Devuelve una tabla con:
    - q1
    - mediana
    - q3
    - iqr
    - limite_inf
    - limite_sup

    El límite superior se usará después para marcar consumos potencialmente revisables.
    """

    if df is None:
        df = st.session_state.df_norm_h.copy()
    else:
        df = df.copy()

    # Asegurar columnas necesarias
    df["fecha_hora"] = pd.to_datetime(df["fecha_hora"])

    if "hora" not in df.columns:
        df["hora"] = df["fecha_hora"].dt.hour

    if "tipo_dia" not in df.columns:
        df["tipo_dia"] = np.where(df["fecha_hora"].dt.dayofweek < 5, "L-V", "FS")

    # Asegurar numérico
    df[variable] = pd.to_numeric(df[variable], errors="coerce")

    df = df.dropna(subset=[variable, "tipo_dia", "hora"])

    patron = (
        df.groupby(["tipo_dia", "hora"])[variable]
        .agg(
            q1=lambda x: x.quantile(0.25),
            mediana="median",
            q3=lambda x: x.quantile(0.75),
            media="mean",
            std="std",
            n="count"
        )
        .reset_index()
    )

    patron["iqr"] = patron["q3"] - patron["q1"]

    patron["limite_inf"] = patron["q1"] - 1.5 * patron["iqr"]
    patron["limite_sup"] = patron["q3"] + 1.5 * patron["iqr"]

    # En consumo no tiene sentido un límite inferior negativo
    patron["limite_inf"] = patron["limite_inf"].clip(lower=0)

    return patron


def detectar_consumos_atipicos_horarios(
    df=None,
    patron=None,
    variable="consumo_neto_kWh",
    min_exceso_kwh=0,
    min_ratio=1.0
):
    """
    Cruza cada registro horario con el patrón horario tipo boxplot.

    Marca como potencialmente revisable una hora si:
    - consumo real > limite_sup del boxplot para su tipo_dia + hora
    - exceso_vs_mediana >= min_exceso_kwh
    - ratio_vs_mediana >= min_ratio

    Parámetros:
    - min_exceso_kwh permite evitar marcar diferencias pequeñas.
    - min_ratio permite exigir que el consumo sea X veces superior a lo esperado.
    """

    if df is None:
        df = st.session_state.df_norm_h.copy()
    else:
        df = df.copy()

    if patron is None:
        patron = calcular_patron_horario_boxplot(df, variable=variable)
    else:
        patron = patron.copy()

    # Asegurar tipos y columnas base
    df["fecha_hora"] = pd.to_datetime(df["fecha_hora"])

    if "fecha" not in df.columns:
        df["fecha"] = df["fecha_hora"].dt.date
    else:
        df["fecha"] = pd.to_datetime(df["fecha"]).dt.date

    if "hora" not in df.columns:
        df["hora"] = df["fecha_hora"].dt.hour

    if "tipo_dia" not in df.columns:
        df["tipo_dia"] = np.where(df["fecha_hora"].dt.dayofweek < 5, "L-V", "FS")

    df[variable] = pd.to_numeric(df[variable], errors="coerce")

    # Nos quedamos con las columnas del patrón que necesitamos
    cols_patron = [
        "tipo_dia",
        "hora",
        "q1",
        "mediana",
        "q3",
        "iqr",
        "limite_inf",
        "limite_sup"
    ]

    df_analisis = df.merge(
        patron[cols_patron],
        on=["tipo_dia", "hora"],
        how="left"
    )

    # Métricas frente al patrón
    df_analisis["consumo_real"] = df_analisis[variable]

    df_analisis["exceso_vs_mediana"] = (
        df_analisis["consumo_real"] - df_analisis["mediana"]
    )

    df_analisis["exceso_vs_limite_sup"] = (
        df_analisis["consumo_real"] - df_analisis["limite_sup"]
    )

    # Evitar divisiones raras si la mediana es 0
    df_analisis["ratio_vs_mediana"] = np.where(
        df_analisis["mediana"] > 0,
        df_analisis["consumo_real"] / df_analisis["mediana"],
        np.nan
    )

    # Regla principal: superar el bigote superior
    df_analisis["supera_limite_sup"] = (
        df_analisis["consumo_real"] > df_analisis["limite_sup"]
    )

    # Regla filtrada para no marcar casos poco relevantes
    df_analisis["es_revisable"] = (
        df_analisis["supera_limite_sup"]
        & (df_analisis["exceso_vs_mediana"] >= min_exceso_kwh)
        & (df_analisis["ratio_vs_mediana"] >= min_ratio)
    )

    return df_analisis


def resumir_atipicos_por_dia(df_analisis):
    df = df_analisis.copy()

    df["fecha"] = pd.to_datetime(df["fecha"])

    # columnas auxiliares solo para revisables
    df["exceso_mediana_revisable"] = np.where(
        df["es_revisable"],
        df["exceso_vs_mediana"].clip(lower=0),
        0
    )

    df["exceso_limite_revisable"] = np.where(
        df["es_revisable"],
        df["exceso_vs_limite_sup"].clip(lower=0),
        0
    )

    df["ratio_revisable"] = np.where(
        df["es_revisable"],
        df["ratio_vs_mediana"],
        np.nan
    )

    resumen = (
        df.groupby("fecha")
        .agg(
            horas_totales=("hora", "count"),
            horas_revisables=("es_revisable", "sum"),
            exceso_total_vs_mediana=("exceso_mediana_revisable", "sum"),
            exceso_total_vs_limite_sup=("exceso_limite_revisable", "sum"),
            ratio_max=("ratio_revisable", "max"),
            consumo_total=("consumo_real", "sum")
        )
        .reset_index()
    )

    resumen["pct_horas_revisables"] = np.where(
        resumen["horas_totales"] > 0,
        100 * resumen["horas_revisables"] / resumen["horas_totales"],
        0
    )

    resumen["tiene_alerta"] = resumen["horas_revisables"] > 0

    return resumen

def calcular_kpis_atipicos(df_analisis, resumen_dia=None):
    if resumen_dia is None:
        resumen_dia = resumir_atipicos_por_dia(df_analisis)

    total_horas = len(df_analisis)
    horas_revisables = int(df_analisis["es_revisable"].sum())
    pct_horas_revisables = 100 * horas_revisables / total_horas if total_horas > 0 else 0

    dias_con_alerta = int((resumen_dia["horas_revisables"] > 0).sum())
    total_dias = len(resumen_dia)

    exceso_total = resumen_dia["exceso_total_vs_mediana"].sum()

    return {
        "total_horas": total_horas,
        "horas_revisables": horas_revisables,
        "pct_horas_revisables": pct_horas_revisables,
        "dias_con_alerta": dias_con_alerta,
        "total_dias": total_dias,
        "exceso_total_vs_mediana": exceso_total
    }

def mostrar_kpis_atipicos(kpis):
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric("Horas revisables", f"{kpis['horas_revisables']:,}".replace(",", "."))

    with c2:
        st.metric("% horas revisables", f"{kpis['pct_horas_revisables']:.1f}%")

    with c3:
        st.metric("Días con alerta", f"{kpis['dias_con_alerta']:,}".replace(",", "."))

    with c4:
        st.metric("Exceso total vs mediana", f"{kpis['exceso_total_vs_mediana']:.1f} kWh")


def graficar_top_dias_revisables(
    resumen_dia,
    top_n=20,
    metrica="exceso_total_vs_mediana"
):
    df_plot = (
        resumen_dia[resumen_dia["horas_revisables"] > 0]
        .sort_values(metrica, ascending=False)
        .head(top_n)
        .copy()
    )

    if df_plot.empty:
        return None

    df_plot["fecha_str"] = df_plot["fecha"].dt.strftime("%d.%m.%Y")

    etiquetas = {
        "exceso_total_vs_mediana": "Exceso total vs mediana (kWh)",
        "exceso_total_vs_limite_sup": "Exceso total vs límite superior (kWh)",
        "horas_revisables": "Horas revisables"
    }

    fig = px.bar(
        df_plot,
        x="fecha_str",
        y=metrica,
        hover_data={
            "fecha_str": False,
            "horas_revisables": True,
            "pct_horas_revisables": ":.1f",
            "ratio_max": ":.2f",
            "consumo_total": ":.1f"
        },
        labels={
            "fecha_str": "Fecha",
            metrica: etiquetas.get(metrica, metrica)
        },
        text="horas_revisables",
        
    )

    fig.update_layout(
        title=dict(
            text=f"Top {top_n} días con mayor señal revisable",
            x=0.5,
            xanchor="center"
        ),
        xaxis_title="Fecha",
        yaxis_title=etiquetas.get(metrica, metrica)
    )

    fig.update_traces(
        texttemplate="%{text}",
        textposition="outside"
    )

    return fig

def graficar_heatmap_alertas(
    df_analisis,
    tipo_dia="Todos",
    metrica="exceso_vs_mediana",
    zmax=None
):
    df = df_analisis.copy()

    if tipo_dia != "Todos":
        df = df[df["tipo_dia"] == tipo_dia].copy()

    df["fecha"] = pd.to_datetime(df["fecha"])
    df["hora"] = df["hora"].astype(int)

    # Valor a representar:
    # 0 si no es revisable
    # exceso si es revisable
    df["valor_plot"] = np.where(
        df["es_revisable"],
        df[metrica].clip(lower=0),
        0
    )

    tabla = (
        df.pivot_table(
            index="fecha",
            columns="hora",
            values="valor_plot",
            aggfunc="max"
        )
        .sort_index()
        .reindex(columns=range(24))
        .fillna(0)
    )

    # Hover auxiliar
    df["fecha_hover"] = df["fecha"].dt.strftime("%d.%m.%Y")

    mapa_dias = {
        0: "Lunes",
        1: "Martes",
        2: "Miércoles",
        3: "Jueves",
        4: "Viernes",
        5: "Sábado",
        6: "Domingo"
    }

    df["dia_semana_hover"] = df["fecha"].dt.dayofweek.map(mapa_dias)

    df["hover_estado"] = np.where(df["es_revisable"], "ALERTA", "Normal")

    tabla_hover_estado = (
        df.pivot_table(index="fecha", columns="hora", values="hover_estado", aggfunc="first")
        .reindex(index=tabla.index, columns=tabla.columns)
    )

    tabla_hover_fecha = (
        df.pivot_table(index="fecha", columns="hora", values="fecha_hover", aggfunc="first")
        .reindex(index=tabla.index, columns=tabla.columns)
    )

    tabla_hover_dia = (
        df.pivot_table(index="fecha", columns="hora", values="dia_semana_hover", aggfunc="first")
        .reindex(index=tabla.index, columns=tabla.columns)
    )

    tabla_hover_consumo = (
        df.pivot_table(index="fecha", columns="hora", values="consumo_real", aggfunc="mean")
        .reindex(index=tabla.index, columns=tabla.columns)
    )

    tabla_hover_mediana = (
        df.pivot_table(index="fecha", columns="hora", values="mediana", aggfunc="mean")
        .reindex(index=tabla.index, columns=tabla.columns)
    )

    tabla_hover_limite = (
        df.pivot_table(index="fecha", columns="hora", values="limite_sup", aggfunc="mean")
        .reindex(index=tabla.index, columns=tabla.columns)
    )

    # zmax automático si no se pasa
    if zmax is None:
        zmax_calc = np.nanmax(tabla.values)
        zmax = zmax_calc if zmax_calc > 0 else 1

    escala_alertas = [
        [0.00, "#000000"],
        [0.03, "#000000"],
        [0.0301, "#fff7bc"],
        [0.25, "#fee391"],
        [0.50, "#fdae6b"],
        [0.75, "#f16913"],
        [1.00, "#bd0026"]
    ]

    fig = px.imshow(
        tabla,
        aspect="auto",
        color_continuous_scale=escala_alertas,
        zmin=0,
        zmax=zmax,
        labels=dict(
            x="Hora",
            y="Fecha",
            color="Exceso (kWh)"
        )
    )

    customdata = np.dstack([
        tabla_hover_fecha.values,
        tabla_hover_dia.values,
        tabla_hover_estado.values,
        tabla_hover_consumo.values,
        tabla_hover_mediana.values,
        tabla_hover_limite.values
    ])

    fig.update_traces(
        customdata=customdata,
        xgap=1,
        ygap=1,
        hovertemplate=(
            "<b>%{customdata[0]}</b> · %{customdata[1]}<br>"
            "Hora: %{x}:00<br>"
            "Estado: %{customdata[2]}<br>"
            "Consumo real: %{customdata[3]:.2f} kWh<br>"
            "Mediana: %{customdata[4]:.2f} kWh<br>"
            "Límite superior: %{customdata[5]:.2f} kWh<br>"
            "Exceso mostrado: %{z:.2f} kWh"
            "<extra></extra>"
        )
    )

    titulo_map = {
        "Todos": "TOTAL",
        "L-V": "LUNES A VIERNES",
        "FS": "FIN DE SEMANA"
    }

    fig.update_layout(
        title=dict(
            text=f"Mapa de horas potencialmente revisables: <span style='color:#ffc107'>{titulo_map.get(tipo_dia, tipo_dia)}</span>",
            x=0.5,
            xanchor="center",
            font=dict(size=16, color="white")
        ),
        template="plotly_dark",
        height=800,
        margin=dict(l=10, r=10, t=80, b=20),
        coloraxis_colorbar=dict(
            title=dict(text="Exceso (kWh)", side="top"),
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.04,
            yanchor="bottom",
            len=0.65,
            thickness=12
        ),
    )

    fig.update_xaxes(
        title="Hora del día",
        tickmode="linear",
        dtick=2
    )

    df_ticks = (
        pd.DataFrame({"fecha": tabla.index})
        .assign(mes=lambda x: x["fecha"].dt.to_period("M"))
        .groupby("mes")["fecha"]
        .min()
        .reset_index()
    )

    fig.update_yaxes(
        title="Fecha",
        tickmode="array",
        tickvals=df_ticks["fecha"],
        ticktext=[f.strftime("%b %Y") for f in df_ticks["fecha"]]
    )

    return fig

def obtener_top_horas_revisables(df_analisis, top_n=50):
    cols = [
        "fecha_hora",
        "fecha",
        "tipo_dia",
        "hora",
        "consumo_real",
        "mediana",
        "limite_sup",
        "exceso_vs_mediana",
        "exceso_vs_limite_sup",
        "ratio_vs_mediana"
    ]

    df_top = (
        df_analisis[df_analisis["es_revisable"]]
        .copy()[cols]
        .sort_values(
            ["exceso_vs_mediana", "ratio_vs_mediana"],
            ascending=[False, False]
        )
        .head(top_n)
    )

    return df_top

def calcular_tabla_excesos_reactiva(tabla_consumos, tabla_reactiva, porcentaje_limite=0.33):

    if tabla_consumos is None or tabla_reactiva is None:
        return None

    colores_periodo = COLORES_3P if st.session_state.atr_dfnorm == "2.0" else COLORES_6P
    orden_periodos = list(colores_periodo.keys())

    tabla_excesos = tabla_consumos[["Mes"]].copy()

    for p in orden_periodos:

        # P6 no penaliza reactiva
        if p == "P6":
            tabla_excesos[p] = 0
            continue

        if p in tabla_consumos.columns and p in tabla_reactiva.columns:
            consumo = pd.to_numeric(tabla_consumos[p], errors="coerce").fillna(0)
            reactiva = pd.to_numeric(tabla_reactiva[p], errors="coerce").fillna(0)

            exceso = reactiva - consumo * porcentaje_limite
            tabla_excesos[p] = exceso.clip(lower=0)
        else:
            tabla_excesos[p] = 0

    tabla_excesos["Total"] = tabla_excesos[orden_periodos].sum(axis=1)

    return tabla_excesos

  

def calcular_tabla_factor_potencia(tabla_consumos, tabla_reactiva):

    if tabla_consumos is None or tabla_reactiva is None:
        return None

    colores_periodo = COLORES_3P if st.session_state.atr_dfnorm == "2.0" else COLORES_6P
    orden_periodos = list(colores_periodo.keys())

    # P6 no penaliza reactiva
    periodos_penalizables = [p for p in orden_periodos if p != "P6"]

    tabla_fp = tabla_consumos[["Mes"]].copy()

    for p in orden_periodos:

        # P6 vacío porque no aplica penalización de reactiva
        if p == "P6":
            tabla_fp[p] = np.nan
            continue

        if p in tabla_consumos.columns and p in tabla_reactiva.columns:
            ea = pd.to_numeric(tabla_consumos[p], errors="coerce")
            er = pd.to_numeric(tabla_reactiva[p], errors="coerce")

            tabla_fp[p] = np.where(
                (ea.notna()) & (er.notna()) & (ea != 0),
                ea / np.sqrt(ea**2 + er**2),
                np.nan
            )

            tabla_fp[p] = tabla_fp[p].round(2)
        else:
            tabla_fp[p] = np.nan

    # Total calculado solo sobre periodos penalizables, excluyendo P6
    ea_total = tabla_consumos[periodos_penalizables].apply(
        pd.to_numeric, errors="coerce"
    ).sum(axis=1)

    er_total = tabla_reactiva[periodos_penalizables].apply(
        pd.to_numeric, errors="coerce"
    ).sum(axis=1)

    tabla_fp["Total"] = np.where(
        (ea_total.notna()) & (er_total.notna()) & (ea_total != 0),
        ea_total / np.sqrt(ea_total**2 + er_total**2),
        np.nan
    )

    tabla_fp["Total"] = tabla_fp["Total"].round(2)

    return tabla_fp



def estilo_factor_potencia(val):
    if pd.isna(val):
        return ""

    try:
        val = float(val)
    except:
        return ""

    if val < 0.95:
        return "background-color: #EA9999; color: #000000;"  # rosa Excel
    else:
        return "background-color: #B6D7A8; color: #000000;"  # verde Excel
    
def calcular_tabla_precio_penalizacion_reactiva(tabla_fp):

    if tabla_fp is None:
        return None

    colores_periodo = COLORES_3P if st.session_state.atr_dfnorm == "2.0" else COLORES_6P
    orden_periodos = list(colores_periodo.keys())

    tabla_precio = tabla_fp[["Mes"]].copy()

    for p in orden_periodos:
        if p in tabla_fp.columns:
            fp = pd.to_numeric(tabla_fp[p], errors="coerce")

            tabla_precio[p] = np.select(
                [
                    fp >= 0.95,
                    (fp >= 0.80) & (fp < 0.95),
                    fp < 0.80
                ],
                [
                    0,
                    0.0411554,
                    0.062332
                ],
                default=np.nan
            )
        else:
            tabla_precio[p] = np.nan

    tabla_precio["Total"] = np.nan

    return tabla_precio
    
def calcular_tabla_coste_excesos_reactiva(tabla_excesos_reactiva, tabla_fp):

    if tabla_excesos_reactiva is None or tabla_fp is None:
        return None

    colores_periodo = COLORES_3P if st.session_state.atr_dfnorm == "2.0" else COLORES_6P
    orden_periodos = list(colores_periodo.keys())

    tabla_coste = tabla_excesos_reactiva[["Mes"]].copy()

    for p in orden_periodos:

        # P6 no aplica penalización de reactiva
        if p == "P6":
            tabla_coste[p] = np.nan
            continue

        if p in tabla_excesos_reactiva.columns and p in tabla_fp.columns:

            excesos = pd.to_numeric(tabla_excesos_reactiva[p], errors="coerce").fillna(0)
            fp = pd.to_numeric(tabla_fp[p], errors="coerce")

            precio_penalizacion = np.select(
                [
                    fp >= 0.95,
                    (fp >= 0.80) & (fp < 0.95),
                    fp < 0.80
                ],
                [
                    0,
                    0.0411554,
                    0.062332
                ],
                default=np.nan
            )

            coste = excesos * precio_penalizacion

            # Si el FP es NaN, ese periodo no aplica / no existe en ese mes
            coste = np.where(fp.isna(), np.nan, coste)

            tabla_coste[p] = coste

        else:
            tabla_coste[p] = np.nan

    periodos_afectados = [p for p in orden_periodos if p != "P6"]

    tabla_coste["Total"] = tabla_coste[periodos_afectados].sum(axis=1, skipna=True)

    return tabla_coste
    
def calcular_tabla_coste_excesos_reactiva_old(tabla_excesos_reactiva, tabla_fp):

    if tabla_excesos_reactiva is None or tabla_fp is None:
        return None

    colores_periodo = COLORES_3P if st.session_state.atr_dfnorm == "2.0" else COLORES_6P
    orden_periodos = list(colores_periodo.keys())

    tabla_coste = tabla_excesos_reactiva[["Mes"]].copy()

    for p in orden_periodos:

        # P6 no aplica penalización de reactiva
        if p == "P6":
            tabla_coste[p] = np.nan
            continue

        if p in tabla_excesos_reactiva.columns and p in tabla_fp.columns:

            excesos = pd.to_numeric(tabla_excesos_reactiva[p], errors="coerce").fillna(0)
            fp = pd.to_numeric(tabla_fp[p], errors="coerce")

            precio_penalizacion = np.select(
                [
                    fp >= 0.95,
                    (fp >= 0.80) & (fp < 0.95),
                    fp < 0.80
                ],
                [
                    0,
                    0.0411554,
                    0.062332
                ],
                default=0
            )

            tabla_coste[p] = excesos * precio_penalizacion

        else:
            tabla_coste[p] = np.nan

    # Total solo con periodos afectados, excluyendo P6
    periodos_afectados = [p for p in orden_periodos if p != "P6"]

    tabla_coste["Total"] = tabla_coste[periodos_afectados].sum(axis=1)

    return tabla_coste

def estilo_coste_penalizacion(val):
    if pd.isna(val):
        return ""

    try:
        val = float(val)
    except:
        return ""

    if val > 0:
        return "background-color: #EA9999; color: #000000;"  # rojo suave NO OK
    else:
        return "background-color: #B6D7A8; color: #000000;"  # verde OK
    


# ============================================================
# TABLA DE POTENCIA MEDIA QH POR MES Y PERIODO
# ============================================================

def calcular_tabla_potencia_media_qh(df_norm, columna_valor="consumo_neto_kWh"):

    if columna_valor not in df_norm.columns:
        return None
    
    if st.session_state.frec == 'QH':
        multiplicador = 4
    else:
        multiplicador = 1

    df_plot = (
        df_norm
        .assign(
            mes=lambda d: d["fecha_hora"].dt.to_period("M").dt.to_timestamp(),
            potencia_qh_kw=lambda d: d[columna_valor] * multiplicador
        )
        .groupby(["mes", "periodo"], as_index=False)["potencia_qh_kw"]
        .mean()
    )

    colores_periodo = COLORES_3P if st.session_state.atr_dfnorm == "2.0" else COLORES_6P
    orden_periodos = list(colores_periodo.keys())

    df_plot["periodo"] = pd.Categorical(
        df_plot["periodo"],
        categories=orden_periodos,
        ordered=True
    )

    tabla = (
        df_plot
        .pivot_table(
            index="mes",
            columns="periodo",
            values="potencia_qh_kw",
            aggfunc="mean",
            fill_value=0,
            observed=False
        )
        .reset_index()
    )

    # Asegurar columnas P1...P6/P1...P3
    for p in orden_periodos:
        if p not in tabla.columns:
            tabla[p] = 0

    # Total mensual: media real de todos los QH del mes, no suma de periodos
    total_mes = (
        df_norm
        .assign(
            mes=lambda d: d["fecha_hora"].dt.to_period("M").dt.to_timestamp(),
            potencia_qh_kw=lambda d: d[columna_valor] * 4
        )
        .groupby("mes", as_index=False)["potencia_qh_kw"]
        .mean()
        .rename(columns={"potencia_qh_kw": "Total"})
    )

    tabla = tabla.merge(total_mes, on="mes", how="left")

    tabla["Mes"] = tabla["mes"].dt.strftime("%b %Y")

    tabla = tabla[["Mes"] + orden_periodos + ["Total"]]

    return tabla


import numpy as np

def calcular_tabla_coef_k(tabla_mensual_fp, fp_objetivo):
    tabla = tabla_mensual_fp.copy()

    if tabla is None or tabla.empty:
        return None

    if "Mes" not in tabla.columns:
        return None

    # Detectar columnas de periodos
    columnas_periodo = [
        c for c in tabla.columns
        if str(c).startswith("P")
    ]

    # Mantener también Total si existe
    columnas_calculo = columnas_periodo.copy()
    if "Total" in tabla.columns:
        columnas_calculo.append("Total")

    # Función para calcular K celda a celda
    def calcular_k(fp_actual):
        try:
            fp_actual = float(fp_actual)
        except:
            return 0

        if pd.isna(fp_actual) or fp_actual <= 0:
            return 0

        # Limitar por seguridad entre 0 y 1
        fp_actual = min(max(fp_actual, 0), 1)
        fp_obj = min(max(float(fp_objetivo), 0), 1)

        # Si ya cumple objetivo, no compensamos
        if fp_actual >= fp_obj:
            return 0

        tg_actual = np.tan(np.arccos(fp_actual))
        tg_obj = np.tan(np.arccos(fp_obj))

        k = tg_actual - tg_obj

        return max(k, 0)

    # Aplicar cálculo a P1...P6 y Total
    for col in columnas_calculo:
        tabla[col] = tabla[col].apply(calcular_k)

    return tabla

def calcular_tabla_q_condensadores(df_potmed_qh, df_coef_k):
    """
    Calcula la potencia reactiva capacitiva necesaria por mes y periodo:

        Qc = Pdem * K

    df_potmed_qh: tabla de potencia media demandada en kW
    df_coef_k: tabla de coeficientes K

    Devuelve kVAr por mes y periodo.
    """

    if df_potmed_qh is None or df_coef_k is None:
        return None

    if df_potmed_qh.empty or df_coef_k.empty:
        return None

    periodos = [
        c for c in df_potmed_qh.columns
        if c.startswith("P") and c in df_coef_k.columns
    ]

    tabla = df_potmed_qh[["Mes"]].copy()

    for p in periodos:
        pot = pd.to_numeric(df_potmed_qh[p], errors="coerce").fillna(0)
        k = pd.to_numeric(df_coef_k[p], errors="coerce").fillna(0)

        tabla[p] = pot * k

    # Para dimensionar batería, no sumaría periodos.
    # Me quedaría con el máximo requerimiento mensual.
    tabla["Total"] = tabla[periodos].max(axis=1)

    return tabla



def graficar_compensacion(tabla_mensual_consumos, df_reactiva, q_min=None, q_max=None):
    # --------------------------------------------------------
    # Datos anuales medios para el gráfico conceptual
    # --------------------------------------------------------
    consumo_total_anual = tabla_mensual_consumos["Total"].sum()
    reactiva_total_anual = df_reactiva["Total"].sum()

    fp_actual_anual = consumo_total_anual / np.sqrt(
        consumo_total_anual**2 + reactiva_total_anual**2
    )

    # Potencia media anual demandada (kW)
    p_med_anual = (st.session_state.df_norm["consumo_neto_kWh"] * 4).mean()

    fp_actual_anual = np.clip(fp_actual_anual, 0.01, 0.99)

    fp_obj_min = min(st.session_state.fp_obj_min, st.session_state.fp_obj_max)
    fp_obj_max = max(st.session_state.fp_obj_min, st.session_state.fp_obj_max)

    # --------------------------------------------------------
    # Curva de compensación anual media
    # --------------------------------------------------------
    x_ini = min(fp_actual_anual, fp_obj_min) - 0.01
    x_fin = max(fp_obj_max, 0.999)

    x_ini = max(0.80, x_ini)
    x_fin = min(0.999, x_fin)

    fp_curve = np.linspace(fp_actual_anual, x_fin, 200)

    q_curve = p_med_anual * (
        np.tan(np.arccos(fp_actual_anual)) -
        np.tan(np.arccos(fp_curve))
    )

    q_curve = np.maximum(q_curve, 0)

    # --------------------------------------------------------
    # Valores anuales medios, por si no se pasan q_min/q_max
    # --------------------------------------------------------
    q_obj_min_anual = p_med_anual * (
        np.tan(np.arccos(fp_actual_anual)) -
        np.tan(np.arccos(fp_obj_min))
    )

    q_obj_max_anual = p_med_anual * (
        np.tan(np.arccos(fp_actual_anual)) -
        np.tan(np.arccos(fp_obj_max))
    )

    q_obj_min_anual = max(q_obj_min_anual, 0)
    q_obj_max_anual = max(q_obj_max_anual, 0)

    # Si no se pasan q_min/q_max, usamos los anuales medios
    if q_min is None:
        q_min = q_obj_min_anual

    if q_max is None:
        q_max = q_obj_max_anual

    q_min = max(float(q_min), 0)
    q_max = max(float(q_max), 0)

    # --------------------------------------------------------
    # Rango de ejes con margen visual
    # --------------------------------------------------------
    margen_x = 0.01

    x_axis_min = max(0.80, min(fp_actual_anual, fp_obj_min, fp_obj_max) - margen_x)
    x_axis_max = min(1.01, max(fp_actual_anual, fp_obj_min, fp_obj_max) + margen_x)

    y_max = max(
        q_max,
        q_min,
        q_curve.max() if len(q_curve) > 0 else 0
    )

    if y_max <= 0:
        y_max = 1

    y_axis_max = y_max * 1.20

    # --------------------------------------------------------
    # Gráfico
    # --------------------------------------------------------
    fig = go.Figure()

    # Curva anual media
    fig.add_trace(go.Scatter(
        x=fp_curve,
        y=q_curve,
        mode="lines",
        name="Referencia anual media",
        hovertemplate=(
            "cos φ objetivo: %{x:.3f}<br>"
            "Qc anual media: %{y:.1f} kVAr"
            "<extra></extra>"
        )
    ))

    # Estado actual
    fig.add_trace(go.Scatter(
        x=[fp_actual_anual],
        y=[0],
        mode="markers+text",
        name="Estado actual",
        text=[f"Actual<br>{fp_actual_anual:.3f}"],
        textposition="top center",
        hovertemplate=(
            "Estado actual<br>"
            "cos φ: %{x:.3f}<br>"
            "Qc: %{y:.1f} kVAr"
            "<extra></extra>"
        )
    ))

    # Objetivo mínimo
    fig.add_trace(go.Scatter(
        x=[fp_obj_min],
        y=[q_min],
        mode="markers+text",
        name="Objetivo mínimo",
        text=[f"Q min<br>{q_min:.1f} kVAr"],
        textposition="top right",
        hovertemplate=(
            "Objetivo mínimo<br>"
            "cos φ objetivo: %{x:.3f}<br>"
            "Qc: %{y:.1f} kVAr"
            "<extra></extra>"
        )
    ))

    # Objetivo máximo
    fig.add_trace(go.Scatter(
        x=[fp_obj_max],
        y=[q_max],
        mode="markers+text",
        name="Objetivo máximo",
        text=[f"Q max<br>{q_max:.1f} kVAr"],
        textposition="top right",
        hovertemplate=(
            "Objetivo máximo<br>"
            "cos φ objetivo: %{x:.3f}<br>"
            "Qc: %{y:.1f} kVAr"
            "<extra></extra>"
        )
    ))

    # --------------------------------------------------------
    # Líneas auxiliares objetivo mínimo
    # --------------------------------------------------------
    fig.add_shape(
        type="line",
        x0=fp_obj_min,
        y0=0,
        x1=fp_obj_min,
        y1=q_min,
        line=dict(dash="dot", width=1)
    )

    fig.add_shape(
        type="line",
        x0=x_axis_min,
        y0=q_min,
        x1=fp_obj_min,
        y1=q_min,
        line=dict(dash="dot", width=1)
    )

    # --------------------------------------------------------
    # Líneas auxiliares objetivo máximo
    # --------------------------------------------------------
    fig.add_shape(
        type="line",
        x0=fp_obj_max,
        y0=0,
        x1=fp_obj_max,
        y1=q_max,
        line=dict(dash="dot", width=1)
    )

    fig.add_shape(
        type="line",
        x0=x_axis_min,
        y0=q_max,
        x1=fp_obj_max,
        y1=q_max,
        line=dict(dash="dot", width=1)
    )

    # --------------------------------------------------------
    # Layout
    # --------------------------------------------------------
    fig.update_layout(
        title="Compensación de reactiva: estado actual y objetivos",
        xaxis_title="cos φ objetivo",
        yaxis_title="Qc necesaria (kVAr)",
        title_x=0.5,
        hovermode="closest",
        margin=dict(l=70, r=120, t=80, b=70),
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02
        )
    )

    fig.update_xaxes(
        range=[x_axis_min, x_axis_max],
        tickformat=".2f",
        showspikes=True,
        spikemode="across",
        spikesnap="cursor"
    )

    fig.update_yaxes(
        range=[0, y_axis_max],
        showspikes=True,
        spikemode="across",
        spikesnap="cursor"
    )

    return fig

def calcular_curva_q_dimensionamiento(
    df_fp,
    df_potmed_qh,
    fp_ini=0.900,
    fp_fin=1.000,
    paso=0.001
):
    """
    Itera distintos cosphi objetivo y calcula el Q máximo necesario
    usando el mismo método que calcular_tabla_q_condensadores.

    Devuelve un DataFrame con:
    - fp_obj
    - q_max
    """
    #fp_ini = max(0.900, fp_actual_aprox)
    fps = np.arange(fp_ini, fp_fin + paso, paso)

    resultados = []

    for fp_obj in fps:
        fp_obj = min(fp_obj, 0.999999)  # evitar problemas exactos con arccos(1)

        df_coef_k_iter = calcular_tabla_coef_k(df_fp, fp_obj)

        df_q_iter = calcular_tabla_q_condensadores(
            df_potmed_qh,
            df_coef_k_iter
        )

        cols_periodos = [
            c for c in df_q_iter.columns
            if c.startswith("P")
        ]

        q_max_iter = df_q_iter[cols_periodos].max().max()

        resultados.append({
            "fp_obj": fp_obj,
            "q_max": q_max_iter
        })

    df_curva_q = pd.DataFrame(resultados)

    return df_curva_q

def graficar_compensacion_dimensionamiento(df_curva_q, q_min, fp_min_rec, q_min_rec, q_sel, fp_ini):

    fp_obj_min = min(st.session_state.fp_obj_min, st.session_state.fp_obj_sel)
    fp_obj_sel = max(st.session_state.fp_obj_min, st.session_state.fp_obj_sel)

    # Estado actual aproximado: primer punto con Q = 0 o mínimo de curva
    df_no_cero = df_curva_q[df_curva_q["q_max"] > 0]

    if not df_no_cero.empty:
        fp_actual_aprox = df_no_cero["fp_obj"].min()
    else:
        fp_actual_aprox = df_curva_q["fp_obj"].min()

    fp_actual_aprox = fp_ini
    margen_x = 0.01
    x_min = max(0.89, df_curva_q["fp_obj"].min() - margen_x)
    x_max = min(1.01, df_curva_q["fp_obj"].max() + margen_x)

    y_max = max(df_curva_q["q_max"].max(), q_min, q_sel)

    if y_max <= 0:
        y_max = 1

    fig = go.Figure()

    def add_area_entre_q(fig, df_curva_q, q_low, q_high, color, name):
        """
        Sombrea el área entre dos niveles de Q siguiendo la curva.
        """

        if q_low is None or q_high is None:
            return fig

        q_low = float(q_low)
        q_high = float(q_high)

        if q_high <= q_low:
            return fig

        df_aux = df_curva_q.copy().sort_values("q_max")

        q_min_curva = df_aux["q_max"].min()
        q_max_curva = df_aux["q_max"].max()

        q_low_clip = np.clip(q_low, q_min_curva, q_max_curva)
        q_high_clip = np.clip(q_high, q_min_curva, q_max_curva)

        fp_low = np.interp(q_low_clip, df_aux["q_max"], df_aux["fp_obj"])
        fp_high = np.interp(q_high_clip, df_aux["q_max"], df_aux["fp_obj"])

        df_seg = df_curva_q[
            (df_curva_q["fp_obj"] >= fp_low) &
            (df_curva_q["fp_obj"] <= fp_high)
        ].copy()

        # Añadimos extremos interpolados para que el área cierre bien
        df_extremos = pd.DataFrame({
            "fp_obj": [fp_low, fp_high],
            "q_max": [q_low_clip, q_high_clip]
        })

        df_seg = (
            pd.concat([df_extremos, df_seg], ignore_index=True)
            .drop_duplicates(subset=["fp_obj"])
            .sort_values("fp_obj")
        )

        x_area = (
            [fp_low]
            + df_seg["fp_obj"].tolist()
            + [fp_high, fp_high, fp_low]
        )

        y_area = (
            [q_low_clip]
            + df_seg["q_max"].tolist()
            + [q_low_clip, 0, 0]
        )

        fig.add_trace(go.Scatter(
            x=x_area,
            y=y_area,
            fill="toself",
            mode="none",
            name=name,
            fillcolor=color,
            opacity=0.25,
            hoverinfo="skip",
            showlegend=True
        ))

        return fig

    # curva de dimensionamiento FP/Q
    fig.add_trace(go.Scatter(
        x=df_curva_q["fp_obj"],
        y=df_curva_q["q_max"],
        mode="lines",
        name="Curva de dimensionamiento",
        hovertemplate=(
            "cos φ objetivo: %{x:.3f}<br>"
            "Q compensación: %{y:.1f} kVAr"
            "<extra></extra>"
        )
    ))

    # marcador inicial
    fig.add_trace(go.Scatter(
        x=[fp_actual_aprox],
        y=[0],
        mode="markers+text",
        name="Situación actual",
        text=[f"Q Actual<br>{fp_actual_aprox:.3f}"],
        textposition="top left",
        textfont=dict(
            size=16,
            color="red"
        ),
        marker=dict(
            size=14,
            #line=dict(width=2),
            color = 'red'
        ),
        hovertemplate=(
            "Estado actual aproximado<br>"
            "cos φ: %{x:.3f}<br>"
            "Q: %{y:.1f} kVAr"
            "<extra></extra>"
        )
    ))

    # marcador fp minimo = 0,95
    fig.add_trace(go.Scatter(
        x=[fp_obj_min],
        y=[q_min],
        mode="markers+text",
        name="Objetivo mínimo",
        text=[f"Q min<br>{q_min:.1f} kVAr"],
        textposition="top left",
        textfont=dict(
            size=16,
            color="yellow"
        ),
        marker=dict(
            size=14,
            #line=dict(width=2),
            color = 'yellow'
        ),
        hovertemplate=(
            "Objetivo mínimo<br>"
            "cos φ objetivo: %{x:.3f}<br>"
            "Q compensación: %{y:.1f} kVAr"
            "<extra></extra>"
        )
    ))

    # marcador fp minimo = 0,95 + MARGEN
    fig.add_trace(go.Scatter(
        x=[fp_min_rec],
        y=[q_min_rec],
        mode="markers+text",
        name="Objetivo mínimo recomendado",
        text=[f"Q min rec<br>{q_min_rec:.1f} kVAr"],
        textposition="top left",
        textfont=dict(
            size=16,
            color="orange"
        ),
        marker=dict(
            size=14,
            #line=dict(width=2),
            color = 'orange'
        ),
        hovertemplate=(
            "Objetivo mínimo recomendado<br>"
            "cos φ objetivo: %{x:.3f}<br>"
            "Q compensación: %{y:.1f} kVAr"
            "<extra></extra>"
        )
    ))

    # marcador fp seleccionable
    fig.add_trace(go.Scatter(
        x=[fp_obj_sel],
        y=[q_sel],
        mode="markers+text",
        name="Objetivo seleccionado",
        text=[f"Q sel<br>{q_sel:.1f} kVAr"],
        textposition="top left",
        textfont=dict(
            size=16,
            color="lightgreen"
        ),
        marker=dict(
            size=14,
            color="lightgreen",
            #line=dict(width=2)
        ),
        hovertemplate=(
            "Objetivo seleccionado<br>"
            "cos φ objetivo: %{x:.3f}<br>"
            "Q compensación: %{y:.1f} kVAr"
            "<extra></extra>"
        )
    ))

    # Líneas auxiliares mínimo
    fig.add_shape(
        type="line",
        x0=fp_obj_min,
        y0=0,
        x1=fp_obj_min,
        y1=q_min,
        line=dict(dash="dot", width=1, color ='grey')
    )

    fig.add_shape(
        type="line",
        x0=x_min,
        y0=q_min,
        x1=fp_obj_min,
        y1=q_min,
        line=dict(dash="dot", width=1, color = 'grey')
    )

    # Líneas auxiliares mínimo recomendado
    fig.add_shape(
        type="line",
        x0=fp_min_rec,
        y0=0,
        x1=fp_min_rec,
        y1=q_min_rec,
        line=dict(dash="dot", width=1, color ='grey')
    )

    fig.add_shape(
        type="line",
        x0=x_min,
        y0=q_min_rec,
        x1=fp_min_rec,
        y1=q_min_rec,
        line=dict(dash="dot", width=1, color = 'grey')
    )

    # Líneas auxiliares selección
    fig.add_shape(
        type="line",
        x0=fp_obj_sel,
        y0=0,
        x1=fp_obj_sel,
        y1=q_sel,
        line=dict(dash="dot", width=1, color = 'grey')
    )

    fig.add_shape(
        type="line",
        x0=x_min,
        y0=q_sel,
        x1=fp_obj_sel,
        y1=q_sel,
        line=dict(dash="dot", width=1, color = 'grey')
    )

    fig.update_layout(
        title="Compensación kVAr necesaria",
        xaxis_title="cos φ objetivo",
        yaxis_title="Q compensación (kVAr)",
        title_x=0.5,
        hovermode="closest",
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02
        ),
        autosize=False,
        height=1000
    )

    fig = add_area_entre_q(
        fig,
        df_curva_q,
        q_low=q_min,
        q_high=q_min_rec,
        color="orange",
        name="Margen recomendado"
    )

    fig = add_area_entre_q(
        fig,
        df_curva_q,
        q_low=q_min_rec,
        q_high=q_sel,
        color="lightgreen",
        name="Margen hasta objetivo seleccionado"
    )
        
    fig = aplicar_estilo(fig)
    fig.update_layout(
        height=600,
        autosize=False
    )

    return fig



from dateutil.relativedelta import relativedelta
from datetime import timedelta
def calcular_comparacion():
    """
    Calcula la comparativa anual de consumo entre un periodo base seleccionado
    y el mismo periodo desplazado +1 año.

    Devuelve un diccionario con:
    - ok: bool
    - mensaje: str
    - df_pivot: DataFrame
    - resumen_html: str
    - fig_total: Figure o None
    - fig_mensual: Figure o None
    - fechas: dict con fechas útiles para el frontend
    """

    fig_mensual = None
    fig_total = None
    resumen_html = ""
    df_pivot = pd.DataFrame()

    # =====================================================
    # 1. FECHAS GLOBALES
    # =====================================================
    fecha_ini_global, fecha_fin_global = st.session_state.rango_curvadecarga
    fecha_ini_global = pd.to_datetime(fecha_ini_global).date()
    fecha_fin_global = pd.to_datetime(fecha_fin_global).date()

    # Fecha máxima seleccionable para el periodo base:
    # la curva debe tener datos disponibles un año después
    fecha_max_comparable = fecha_fin_global - relativedelta(years=1)

    resultado = {
        "ok": False,
        "mensaje": "",
        "df_pivot": df_pivot,
        "resumen_html": resumen_html,
        "fig_total": fig_total,
        "fig_mensual": fig_mensual,
        "fechas": {
            "fecha_ini_global": fecha_ini_global,
            "fecha_fin_global": fecha_fin_global,
            "fecha_max_comparable": fecha_max_comparable,
            "rango_valido": None,
            "fecha_delta": None,
        },
        "debug": {}
    }

    print("fecha_ini_global:", fecha_ini_global)
    print("fecha_fin_global:", fecha_fin_global)
    print("fecha_max_comparable:", fecha_max_comparable)

    # =====================================================
    # 2. VALIDACIÓN DE DATOS SUFICIENTES
    # =====================================================
    if fecha_max_comparable < fecha_ini_global:
        resultado["mensaje"] = "No hay datos suficientes para realizar una comparativa anual (+1 año)."
        return resultado

    # =====================================================
    # 3. RANGO COMPARABLE DISPONIBLE
    # =====================================================
    fecha_delta = (
        pd.to_datetime(fecha_max_comparable)
        - relativedelta(years=1)
        + timedelta(days=1)
    ).date()

    if fecha_delta < fecha_ini_global:
        fecha_delta = fecha_ini_global

    rango_valido = (fecha_delta, fecha_max_comparable)

    resultado["fechas"]["rango_valido"] = rango_valido
    resultado["fechas"]["fecha_delta"] = fecha_delta

    print(f"rango_valido: {rango_valido}")

    # =====================================================
    # 4. INICIALIZACIÓN / SANEADO DEL RANGO EN SESSION_STATE
    # =====================================================
    if "rango_fechas_comparativa" not in st.session_state:
        st.session_state.rango_fechas_comparativa = rango_valido

    else:
        rango_actual = st.session_state.rango_fechas_comparativa

        if not isinstance(rango_actual, (list, tuple)) or len(rango_actual) != 2:
            st.session_state.rango_fechas_comparativa = rango_valido

        else:
            f_ini, f_fin = rango_actual
            f_ini = pd.to_datetime(f_ini).date()
            f_fin = pd.to_datetime(f_fin).date()

            # Recortar a límites válidos
            f_ini = max(f_ini, fecha_ini_global)
            f_fin = min(f_fin, fecha_max_comparable)

            # Si tras recortar queda inválido, reset
            if f_ini > f_fin:
                st.session_state.rango_fechas_comparativa = rango_valido
            else:
                st.session_state.rango_fechas_comparativa = (f_ini, f_fin)

    print(f"Rango fechas comparativa: {st.session_state.rango_fechas_comparativa}")

    # =====================================================
    # 5. RECUPERAR FECHAS SELECCIONADAS
    # =====================================================
    rango = st.session_state.get("rango_fechas_comparativa")

    if rango is None or len(rango) != 2:
        resultado["mensaje"] = "No se ha seleccionado un rango válido."
        return resultado

    fecha_inicio, fecha_fin = rango

    inicio = pd.to_datetime(fecha_inicio)
    fin = pd.to_datetime(fecha_fin)

    # =====================================================
    # 6. GENERAR PERIODO +1 AÑO
    # =====================================================
    inicio_1y = inicio + relativedelta(years=1)
    fin_1y = fin + relativedelta(years=1)

    resultado["debug"] = {
        "inicio": inicio,
        "fin": fin,
        "inicio_1y": inicio_1y,
        "fin_1y": fin_1y,
    }

    # =====================================================
    # 7. CHECK DATOS DISPONIBLES
    # =====================================================
    fecha_max_df = st.session_state.df_norm_h["fecha_hora"].max()

    if fin_1y > fecha_max_df:
        resultado["mensaje"] = "No hay datos completos para el periodo comparativo (+1 año)."
        return resultado

    # =====================================================
    # 8. FILTRADO
    # =====================================================
    df_base = st.session_state.df_norm_h[
        (st.session_state.df_norm_h["fecha_hora"] >= inicio) &
        (st.session_state.df_norm_h["fecha_hora"] < fin + pd.Timedelta(days=1))
    ].copy()

    df_comp = st.session_state.df_norm_h[
        (st.session_state.df_norm_h["fecha_hora"] >= inicio_1y) &
        (st.session_state.df_norm_h["fecha_hora"] < fin_1y + pd.Timedelta(days=1))
    ].copy()

    if df_base.empty:
        resultado["mensaje"] = "El periodo base seleccionado no tiene datos."
        return resultado

    if df_comp.empty:
        resultado["mensaje"] = "El periodo comparativo (+1 año) no tiene datos."
        return resultado

    # =====================================================
    # 9. ETIQUETADO
    # =====================================================
    df_base["periodo_comp"] = "Base"
    df_comp["periodo_comp"] = "+1 año"

    df_total = pd.concat([df_base, df_comp], ignore_index=True)

    # =====================================================
    # 10. COLUMNAS TEMPORALES
    # =====================================================
    df_total["mes_nom"] = df_total["fecha_hora"].dt.strftime("%b")
    df_total["mes_num"] = df_total["fecha_hora"].dt.month
    df_total["mes_label"] = df_total["fecha_hora"].dt.strftime("%b %Y")
    df_total["año"] = df_total["fecha_hora"].dt.year

    mes_inicio = inicio.month
    df_total["mes_orden"] = (df_total["mes_num"] - mes_inicio) % 12

    # =====================================================
    # 11. AGREGACIÓN MENSUAL
    # =====================================================
    df_mensual = (
        df_total
        .groupby(
            ["periodo_comp", "mes_num", "mes_nom", "mes_orden"],
            as_index=False
        )["consumo_neto_kWh"]
        .sum()
    )

    # =====================================================
    # 12. PIVOT
    # =====================================================
    df_pivot = df_mensual.pivot(
        index=["mes_num", "mes_nom", "mes_orden"],
        columns="periodo_comp",
        values="consumo_neto_kWh"
    ).reset_index()

    # Asegurar columnas por si falta alguna
    for col in ["Base", "+1 año"]:
        if col not in df_pivot.columns:
            df_pivot[col] = 0

    # =====================================================
    # 13. DIFERENCIALES
    # =====================================================
    df_pivot["Δ"] = df_pivot["+1 año"] - df_pivot["Base"]

    df_pivot["Δ %"] = np.where(
        df_pivot["Base"] != 0,
        df_pivot["Δ"] / df_pivot["Base"] * 100,
        0
    )

    fila_total = {
        "Mes": "TOTAL",
        "Base": df_pivot["Base"].sum(),
        "+1 año": df_pivot["+1 año"].sum()
    }

    fila_total["Δ"] = fila_total["+1 año"] - fila_total["Base"]

    fila_total["Δ %"] = (
        fila_total["Δ"] / fila_total["Base"] * 100
        if fila_total["Base"] != 0
        else 0
    )

    # =====================================================
    # 14. ORDEN Y FORMATO DE TABLA
    # =====================================================
    df_pivot = df_pivot.sort_values("mes_orden")

    df_pivot["Mes"] = df_pivot["mes_nom"] + f" ({inicio.year}/{inicio_1y.year})"

    df_pivot = df_pivot.drop(columns=["mes_num", "mes_orden"])
    df_pivot = df_pivot[["Mes", "Base", "+1 año", "Δ", "Δ %"]]

    df_pivot = pd.concat(
        [df_pivot, pd.DataFrame([fila_total])],
        ignore_index=True
    )

    # =====================================================
    # 15. RESUMEN HTML
    # =====================================================
    delta = fila_total["Δ"]
    delta_pct = fila_total["Δ %"]

    if delta > 0:
        texto_tipo = "incremento"
    elif delta < 0:
        texto_tipo = "decremento"
    else:
        texto_tipo = "variación nula"

    def formato_es(valor, decimales=0):
        return f"{valor:,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")

    delta_str = formato_es(delta, 0)
    delta_pct_str = formato_es(delta_pct, 2)

    resumen_html = f"""
    <div style="font-size:28px; text-align:center; color:white;">
        El <b>{texto_tipo}</b> del consumo en el periodo seleccionado ha sido de:
        <br>
        <span style="font-size:36px; font-weight:bold;">
            <span style="color:yellow;">{delta_str}</span> kWh
        </span> 
        (<span style="font-size:36px; font-weight:bold;">
            <span style="color:yellow;">{delta_pct_str}</span> %
        </span>)
    </div>
    """

    # =====================================================
    # 16. GRÁFICOS
    # =====================================================
    color_base = "#1f77b4"
    color_comp = "#ff7f0e"

    df_plot = df_pivot[df_pivot["Mes"] != "TOTAL"]

    fig_mensual = px.bar(
        df_plot,
        x="Mes",
        y=["Base", "+1 año"],
        barmode="group",
    )

    fig_mensual.for_each_trace(
        lambda t: t.update(marker_color=color_base)
        if t.name == "Base"
        else t.update(marker_color=color_comp)
    )

    fig_mensual.update_layout(
        title=dict(
            text="Comparativa MENSUAL del periodo (kWh)",
            x=0.5,
            xanchor="center"
        ),
        legend_title_text="Periodo",
        xaxis_title="Mes",
        yaxis_title="kWh",
        bargap=0.25,
        bargroupgap=0.1
    )

    df_total_plot = df_pivot[df_pivot["Mes"] == "TOTAL"]

    fig_total = px.bar(
        df_total_plot,
        x=["TOTAL"],
        y=["Base", "+1 año"],
        barmode="group",
    )

    fig_total.for_each_trace(
        lambda t: t.update(marker_color=color_base)
        if t.name == "Base"
        else t.update(marker_color=color_comp)
    )

    fig_total.update_traces(
        texttemplate="%{y:,.0f}",
        textposition="inside",
        textfont_size=20
    )

    fig_total.update_layout(
        title=dict(
            text="Comparativa TOTAL del periodo (kWh)",
            x=0.5,
            xanchor="center"
        ),
        showlegend=True,
        xaxis_title="",
        yaxis_title="kWh",
        bargap=0.4,
        bargroupgap=0.1
    )

    # =====================================================
    # 17. RETURN FINAL
    # =====================================================
    resultado["ok"] = True
    resultado["mensaje"] = ""
    resultado["df_pivot"] = df_pivot
    resultado["resumen_html"] = resumen_html
    resultado["fig_total"] = fig_total
    resultado["fig_mensual"] = fig_mensual

    return resultado

def calcular_comparacion_costes(precios_mensuales, rango_base=None):

    df = precios_mensuales.copy()

    # =====================================================
    # 0. VALIDACIONES BÁSICAS
    # =====================================================
    cols_necesarias = [
        "año",
        "mes_nombre",
        "mes_num",
        "fecha",
        "consumo_neto_kWh",
        "coste_total"
    ]

    faltan = [c for c in cols_necesarias if c not in df.columns]

    if faltan:
        return {
            "ok": False,
            "mensaje": f"Faltan columnas para comparar costes: {faltan}",
            "df_costes": pd.DataFrame(),
            "df_efectos": pd.DataFrame(),
            "resumen_html_costes": "",
            "fig_coste_total": None,
            "fig_efectos": None,
            "fig_precio_medio": None,
        }

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["año"] = pd.to_numeric(df["año"], errors="coerce").astype("Int64")
    df["mes_num"] = pd.to_numeric(df["mes_num"], errors="coerce").astype("Int64")

    df["consumo_neto_kWh"] = pd.to_numeric(
        df["consumo_neto_kWh"],
        errors="coerce"
    )

    df["coste_total"] = pd.to_numeric(
        df["coste_total"],
        errors="coerce"
    )

    df = df.dropna(
        subset=[
            "fecha",
            "año",
            "mes_num",
            "consumo_neto_kWh",
            "coste_total"
        ]
    )

    if df.empty:
        return {
            "ok": False,
            "mensaje": "No hay datos mensuales válidos para comparar costes.",
            "df_costes": pd.DataFrame(),
            "df_efectos": pd.DataFrame(),
            "resumen_html_costes": "",
            "fig_coste_total": None,
            "fig_efectos": None,
            "fig_precio_medio": None,
        }

    # =====================================================
    # 1. FILTRAR PERIODO BASE
    # =====================================================
    if rango_base is not None:

        if isinstance(rango_base, tuple) or isinstance(rango_base, list):
            fecha_ini_base = pd.to_datetime(rango_base[0])
            fecha_fin_base = pd.to_datetime(rango_base[1])
        else:
            fecha_ini_base = pd.to_datetime(rango_base)
            fecha_fin_base = pd.to_datetime(rango_base)

        # Llevamos el rango a meses completos
        fecha_ini_mes = fecha_ini_base.replace(day=1)
        fecha_fin_mes = fecha_fin_base.replace(day=1)

        df_base = df[
            (df["fecha"] >= fecha_ini_mes)
            & (df["fecha"] <= fecha_fin_mes)
        ].copy()

    else:
        df_base = df.copy()

    if df_base.empty:
        return {
            "ok": False,
            "mensaje": "No hay meses base dentro del rango seleccionado.",
            "df_costes": pd.DataFrame(),
            "df_efectos": pd.DataFrame(),
            "resumen_html_costes": "",
            "fig_coste_total": None,
            "fig_efectos": None,
            "fig_precio_medio": None,
        }

    # =====================================================
    # 2. CREAR CLAVE DE COMPARACIÓN +1 AÑO
    # =====================================================
    df_base = df_base.copy()
    df_base["año_comp"] = df_base["año"] + 1

    df_comp = df.copy()

    df_comp = df_comp.rename(
        columns={
            "año": "año_comp",
            "consumo_neto_kWh": "consumo_comp",
            "coste_total": "coste_comp",
            "fecha": "fecha_comp",
            "mes_nombre": "mes_nombre_comp"
        }
    )

    df_base = df_base.rename(
        columns={
            "año": "año_base",
            "consumo_neto_kWh": "consumo_base",
            "coste_total": "coste_base",
            "fecha": "fecha_base"
        }
    )

    df_cmp = df_base.merge(
        df_comp[
            [
                "año_comp",
                "mes_num",
                "mes_nombre_comp",
                "fecha_comp",
                "consumo_comp",
                "coste_comp"
            ]
        ],
        on=["año_comp", "mes_num"],
        how="inner"
    )

    if df_cmp.empty:
        return {
            "ok": False,
            "mensaje": "No hay meses comparables con +1 año para el rango seleccionado.",
            "df_costes": pd.DataFrame(),
            "df_efectos": pd.DataFrame(),
            "resumen_html_costes": "",
            "fig_coste_total": None,
            "fig_efectos": None,
            "fig_precio_medio": None,
        }

    # =====================================================
    # 3. CÁLCULOS DE PRECIO MEDIO E IMPACTOS
    # =====================================================
    df_cmp["precio_base_eur_kwh"] = np.where(
        df_cmp["consumo_base"] > 0,
        df_cmp["coste_base"] / df_cmp["consumo_base"],
        np.nan
    )

    df_cmp["precio_comp_eur_kwh"] = np.where(
        df_cmp["consumo_comp"] > 0,
        df_cmp["coste_comp"] / df_cmp["consumo_comp"],
        np.nan
    )

    df_cmp["precio_base_cent_kwh"] = df_cmp["precio_base_eur_kwh"] * 100
    df_cmp["precio_comp_cent_kwh"] = df_cmp["precio_comp_eur_kwh"] * 100

    # Escenario: consumo base con precio del año siguiente
    df_cmp["coste_simulado_precio_comp"] = (
        df_cmp["consumo_base"] * df_cmp["precio_comp_eur_kwh"]
    )

    df_cmp["variacion_coste"] = (
        df_cmp["coste_comp"] - df_cmp["coste_base"]
    )

    df_cmp["variacion_coste_pct"] = np.where(
        df_cmp["coste_base"] != 0,
        df_cmp["variacion_coste"] / df_cmp["coste_base"] * 100,
        np.nan
    )

    df_cmp["efecto_precio"] = (
        df_cmp["coste_simulado_precio_comp"] - df_cmp["coste_base"]
    )

    df_cmp["efecto_consumo"] = (
        df_cmp["coste_comp"] - df_cmp["coste_simulado_precio_comp"]
    )

    df_cmp["check"] = (
        df_cmp["efecto_precio"]
        + df_cmp["efecto_consumo"]
        - df_cmp["variacion_coste"]
    )

    df_cmp["mes_label"] = (
        df_cmp["mes_nombre"].astype(str).str[:3].str.capitalize()
        + " "
        + df_cmp["año_base"].astype(str)
        + " → "
        + df_cmp["año_comp"].astype(str)
    )

    # =====================================================
    # 4. TABLAS DE SALIDA
    # =====================================================
    df_costes = df_cmp[
        [
            "mes_label",
            "consumo_base",
            "consumo_comp",
            "coste_base",
            "coste_comp",
            "variacion_coste",
            "variacion_coste_pct",
            "precio_base_cent_kwh",
            "precio_comp_cent_kwh"
        ]
    ].copy()

    df_costes = df_costes.rename(
        columns={
            "mes_label": "Mes",
            "consumo_base": "Consumo base",
            "consumo_comp": "+1 año",
            "coste_base": "Coste base",
            "coste_comp": "Coste +1 año",
            "variacion_coste": "Δ coste",
            "variacion_coste_pct": "Δ coste %",
            "precio_base_cent_kwh": "Precio base",
            "precio_comp_cent_kwh": "Precio +1 año"
        }
    )

    df_efectos = df_cmp[
        [
            "mes_label",
            "variacion_coste",
            "efecto_precio",
            "efecto_consumo",
            "coste_simulado_precio_comp"
        ]
    ].copy()

    df_efectos = df_efectos.rename(
        columns={
            "mes_label": "Mes",
            "variacion_coste": "Δ coste real",
            "efecto_precio": "Efecto precio",
            "efecto_consumo": "Efecto consumo",
            "coste_simulado_precio_comp": "Coste con consumo base y precio +1 año"
        }
    )

    # =====================================================
    # 5. RESUMEN TOTAL
    # =====================================================
    consumo_base_total = df_cmp["consumo_base"].sum()
    consumo_comp_total = df_cmp["consumo_comp"].sum()

    coste_base_total = df_cmp["coste_base"].sum()
    coste_comp_total = df_cmp["coste_comp"].sum()

    precio_base_total = (
        coste_base_total / consumo_base_total * 100
        if consumo_base_total > 0 else np.nan
    )

    precio_comp_total = (
        coste_comp_total / consumo_comp_total * 100
        if consumo_comp_total > 0 else np.nan
    )

    coste_simulado_total = (
        consumo_base_total * coste_comp_total / consumo_comp_total
        if consumo_comp_total > 0 else np.nan
    )

    variacion_total = coste_comp_total - coste_base_total
    efecto_precio_total = coste_simulado_total - coste_base_total
    efecto_consumo_total = coste_comp_total - coste_simulado_total

    def formato_numero_es(valor, decimales=2):
        if pd.isna(valor):
            return "-"
        return f"{valor:,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def generar_resumen_html_costes(
        coste_base_total,
        coste_comp_total,
        consumo_base_total,
        consumo_comp_total,
        precio_base_total,
        precio_comp_total,
        coste_simulado_total,
        efecto_precio_total,
        efecto_consumo_total
    ):

        variacion_total = coste_comp_total - coste_base_total
        variacion_consumo = consumo_comp_total - consumo_base_total
        variacion_precio = precio_comp_total - precio_base_total

        def signo(x):
            return "+" if x > 0 else ""

        html = (
            '<div style="'
            'padding:1rem 1.1rem;'
            'border-radius:0.75rem;'
            'background-color:rgba(240,242,246,0.08);'
            'border-left:5px solid #1C83E1;'
            'font-size:0.95rem;'
            'line-height:1.55;'
            '">'

            '<div style="font-weight:700;font-size:1.05rem;margin-bottom:0.75rem;">'
            'Comparativa de coste de energía'
            '</div>'

            '<p>'
            'El coste de energía pasó de '
            f'<b>{formato_numero_es(coste_base_total, 2)} €</b> a '
            f'<b>{formato_numero_es(coste_comp_total, 2)} €</b>, '
            'con una variación de '
            f'<b>{signo(variacion_total)}{formato_numero_es(variacion_total, 2)} €</b>.'
            '</p>'

            '<p>'
            'El consumo pasó de '
            f'<b>{formato_numero_es(consumo_base_total, 0)} kWh</b> a '
            f'<b>{formato_numero_es(consumo_comp_total, 0)} kWh</b>, '
            'con una variación de '
            f'<b>{signo(variacion_consumo)}{formato_numero_es(variacion_consumo, 0)} kWh</b>.'
            '</p>'

            '<p>'
            'El precio medio pasó de '
            f'<b>{formato_numero_es(precio_base_total, 2)} c€/kWh</b> a '
            f'<b>{formato_numero_es(precio_comp_total, 2)} c€/kWh</b>, '
            'con una variación de '
            f'<b>{signo(variacion_precio)}{formato_numero_es(variacion_precio, 2)} c€/kWh</b>.'
            '</p>'

            '<p>'
            'A igualdad de consumo base, aplicando el precio medio del año siguiente, '
            'el coste habría sido de '
            f'<b>{formato_numero_es(coste_simulado_total, 2)} €</b>.'
            '</p>'

            '<div style="'
            'margin-top:0.8rem;'
            'padding-top:0.8rem;'
            'border-top:1px solid rgba(255,255,255,0.18);'
            '">'

            '<b>Efecto precio:</b> '
            f'<span style="font-weight:700;">{signo(efecto_precio_total)}{formato_numero_es(efecto_precio_total, 2)} €</span>'
            '<br>'

            '<b>Efecto consumo:</b> '
            f'<span style="font-weight:700;">{signo(efecto_consumo_total)}{formato_numero_es(efecto_consumo_total, 2)} €</span>'

            '</div>'
            '</div>'
        )

        return html
    
    resumen_html_costes = generar_resumen_html_costes(
        coste_base_total=coste_base_total,
        coste_comp_total=coste_comp_total,
        consumo_base_total=consumo_base_total,
        consumo_comp_total=consumo_comp_total,
        precio_base_total=precio_base_total,
        precio_comp_total=precio_comp_total,
        coste_simulado_total=coste_simulado_total,
        efecto_precio_total=efecto_precio_total,
        efecto_consumo_total=efecto_consumo_total
    )

    # =====================================================
    # 6. GRÁFICO COSTE BASE VS +1 AÑO
    # =====================================================

    color_base = "#1f77b4"
    color_comp = "#ff7f0e"

    fig_coste_total = go.Figure()

    fig_coste_total.add_trace(
        go.Bar(
            x=df_cmp["mes_label"],
            y=df_cmp["coste_base"],
            name="Coste base",
            marker_color = color_base,
            hovertemplate="Coste base: %{y:.2f} €<extra></extra>"
        )
    )

    fig_coste_total.add_trace(
        go.Bar(
            x=df_cmp["mes_label"],
            y=df_cmp["coste_comp"],
            name="Coste +1 año",
            marker_color = color_comp,
            hovertemplate="Coste +1 año: %{y:.2f} €<extra></extra>"
        )
    )

    fig_coste_total.update_layout(
        title="Comparativa mensual de COSTES (€)",
        barmode="group",
        hovermode="x unified",
        legend_title_text=""
    )

    fig_coste_total.update_yaxes(
        title_text="Coste energía (€)",
        rangemode="tozero",
        showgrid=True
    )

    fig_coste_total.update_xaxes(
        title_text="Mes",
        showgrid=True
    )

    fig_coste_total = aplicar_estilo(fig_coste_total)

    # =====================================================
    # 7. GRÁFICO EFECTO PRECIO / CONSUMO
    # =====================================================

    color_efecto_precio = "#2ca02c"   # verde
    color_efecto_consumo = "#9467bd"  # morado
    color_delta_real = "#ff9896"      # rosa/salmón para línea
    color_efecto_precio = "#800020"
    color_delta_real = "yellow"  

    fig_efectos = go.Figure()

    fig_efectos.add_trace(
        go.Bar(
            x=df_cmp["mes_label"],
            y=df_cmp["efecto_precio"],
            marker_color = color_efecto_precio,
            name="Efecto precio",
            hovertemplate="Efecto precio: %{y:.2f} €<extra></extra>"
        )
    )

    fig_efectos.add_trace(
        go.Bar(
            x=df_cmp["mes_label"],
            y=df_cmp["efecto_consumo"],
            marker_color = color_efecto_consumo,
            name="Efecto consumo",
            hovertemplate="Efecto consumo: %{y:.2f} €<extra></extra>"
        )
    )

    fig_efectos.add_trace(
        go.Scatter(
            x=df_cmp["mes_label"],
            y=df_cmp["variacion_coste"],
            mode="lines+markers",
            name="Δ coste real",
            marker_color = color_delta_real,
            line=dict(width=4),
            marker=dict(size=8),
            hovertemplate="Δ coste real: %{y:.2f} €<extra></extra>"
        )
    )

    fig_efectos.add_hline(
        y=0,
        line_dash="dot",
        line_color="gray"
    )

    fig_efectos.update_layout(
        title="Efecto PRECIO/CONSUMO",
        barmode="relative",
        hovermode="x unified",
        legend_title_text=""
    )

    fig_efectos.update_yaxes(
        title_text="Impacto económico (€)",
        showgrid=True
    )

    fig_efectos.update_xaxes(
        title_text="Mes",
        showgrid=True
    )

    fig_efectos = aplicar_estilo(fig_efectos)

    # =====================================================
    # 8. GRÁFICO PRECIO MEDIO
    # =====================================================
    fig_precio_medio = go.Figure()

    fig_precio_medio.add_trace(
        go.Scatter(
            x=df_cmp["mes_label"],
            y=df_cmp["precio_base_cent_kwh"],
            mode="lines+markers",
            name="Precio base",
            marker_color = color_base,
            line=dict(width=3),
            marker=dict(size=7),
            hovertemplate="Precio base: %{y:.2f} c€/kWh<extra></extra>"
        )
    )

    fig_precio_medio.add_trace(
        go.Scatter(
            x=df_cmp["mes_label"],
            y=df_cmp["precio_comp_cent_kwh"],
            mode="lines+markers",
            name="Precio +1 año",
            marker_color = color_comp,
            line=dict(width=3),
            marker=dict(size=7),
            hovertemplate="Precio +1 año: %{y:.2f} c€/kWh<extra></extra>"
        )
    )

    fig_precio_medio.update_layout(
        title="Comparativa mensual de PRECIOS (c€/kWh)",
        hovermode="x unified",
        legend_title_text=""
    )

    fig_precio_medio.update_yaxes(
        title_text="Precio medio c€/kWh",
        rangemode="tozero",
        showgrid=True
    )

    fig_precio_medio.update_xaxes(
        title_text="Mes",
        showgrid=True
    )

    fig_precio_medio = aplicar_estilo(fig_precio_medio)

    return {
        "ok": True,
        "mensaje": "",
        "df_costes": df_costes,
        "df_efectos": df_efectos,
        "resumen_html_costes": resumen_html_costes,
        "fig_coste_total": fig_coste_total,
        "fig_efectos": fig_efectos,
        "fig_precio_medio": fig_precio_medio,
    }


