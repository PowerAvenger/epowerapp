import streamlit as st
import plotly.express as px
import pandas as pd
import numpy as np
import io, re
from unidecode import unidecode
from zoneinfo import ZoneInfo
from datetime import timedelta, timezone

TZ = "Europe/Madrid"

colores_periodo = {
        "P1": "red",
        "P2": "#FF7518", #"orange",
        "P3": "#E6B800",   # amarillo oscuro
        "P4": "#FFF176",   # amarillo claro
        "P5": "#7CFC00",
        "P6": "green"
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
        path = uploaded_or_path.lower()
        if path.endswith(".csv"):
            df = pd.read_csv(uploaded_or_path, dtype=str, header=None, skip_blank_lines=True)
        else:
            df = pd.read_excel(uploaded_or_path, dtype=str, header=None)
    else:
        name = uploaded_or_path.name.lower()
        if name.endswith(".csv"):
            content = uploaded_or_path.read()
            sample = content[:4096].decode("utf-8", errors="ignore")
            sep = ";" if sample.count(";") > sample.count(",") else ","
            df = pd.read_csv(io.BytesIO(content), sep=sep, dtype=str, header=None)
        else:
            df = pd.read_excel(uploaded_or_path, dtype=str, header=None)

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

    def find(patterns):
        for c, cc in cleaned.items():
            for p in patterns:
                if re.search(p, cc, re.IGNORECASE):
                    return c
        return None

    c_dt = find([r"^fecha.?y.?hora$", r"fecha.?hora", r"^dia.?y.?hora$", r"datetime", r"timestamp", r"instante", r"^fecha.*"])
    #c_dt = find([r"^fecha.?y.?hora$", r"fecha.?hora", r"^dia.?y.?hora$", r"datetime", r"timestamp", r"instante"])
    c_date = find([r"fecha", r"^fecha$", r"dia", r"date", r"data"])
    c_time = find([r"hora", r"hr", r"time", r"^h$"])
    c_kwh = find([r"consumo", r"energia", r"kwh", r"ae", r"active.?energy", r"importada", r"activa"])
    c_per = find([r"periodo", r"^p$", r"^p[1-6]$"])
    c_ind = find(["reactiva", "kvarh", "inductiva"])
    c_cap = find(["capac"])
    c_ver = find([r"gener", r"vertid", r"exportad", r"as", r"prod"])

    print("\n--- Columnas originales ---")
    print(cols)
    print("\n--- Columnas limpias ---")
    for c, cc in cleaned.items():
        print(f"{c} → {cc}")

    return c_dt, c_date, c_time, c_kwh, c_per, c_ind, c_cap, c_ver

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

# ==============================================================================================================
#  Normalizador simple
# ==============================================================================================================

def normalize_curve_simple_old(uploaded, origin="archivo") -> tuple[pd.DataFrame, pd.DataFrame, str]:

    import traceback

    #Lee y normaliza la curva, devolviendo (df_in, df_norm).
    #   Regla simple:
    #     - Si el primer registro válido está a las 01:00 → restar 1h a toda la serie.
    #     - Si está a las 00:00 → no tocar.
    #   Detección automática de formato de fecha (día primero o año primero)."""
    
    df, header_row = _read_any(uploaded)
    c_dt, c_date, c_time, c_kwh, c_per, c_ind, c_cap, c_ver = _guess_cols(df)

    if not (c_dt or (c_date and c_time)):
        raise ValueError("No se encontró columna de fecha u hora reconocible.")
    
    if not c_kwh:
        raise ValueError("No se encontró columna de consumo (kWh).")

    # --- Consumo ---
    kwh_consumo = pd.to_numeric(df[c_kwh].str.replace(",", ".", regex=False), errors="coerce")
    kwh_vertido = pd.to_numeric(df[c_ver].str.replace(",", ".", regex=False), errors="coerce") if c_ver else np.nan

    msg_unidades = ""

    if (header_row > 0) or ("wh" in str(c_kwh).lower() and "kwh" not in str(c_kwh).lower()):
        kwh_consumo = kwh_consumo / 1000
        kwh_vertido = kwh_vertido / 1000
        msg_unidades = "Detectado consumo en Wh → Convertido automáticamente a kWh"


    try:
        # --- Datetime base (naïve) ---
        if c_dt:
            # Disponemos de fecha y hora en la misma columna
            sample = str(df[c_dt].dropna().iloc[0])
            if re.match(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", sample):
                # Formato AAAA/MM/DD
                dt0 = pd.to_datetime(df[c_dt], errors="coerce", dayfirst=False)
            else:
                # Formato DD/MM/AAAA
                dt0 = pd.to_datetime(df[c_dt], errors="coerce", dayfirst=True)
            
            print('Detectamos datetime fecha-hora')
          
        else:
            print('Entramos por fecha y hora seperados')    
            print(df[c_time].head())

                # Fecha y hora en columnas separadas
            d = _parse_date_ddmmyyyy(df[c_date])
            hora_raw = df[c_time].astype(str).str.strip()
            print('hora_raw')
            print(hora_raw)

            # Limpieza de valores nulos o texto "nan"
            #hora_raw = hora_raw.replace({"nan": np.nan})
            # --- Corregir valores "24:00" ---
            mask_24 = hora_raw.isin(["24:00", "24:00:00"])
            if mask_24.any():
                # Convertimos esas horas a 00:00 y sumamos un día en la fecha
                hora_raw.loc[mask_24] = "00:00"
                d.loc[mask_24] = d.loc[mask_24] + pd.Timedelta(days=1)

            # Detectar si hay ":" en el formato de hora
            if hora_raw.str.contains(":").any():
                print('contiene :')
                # Si todos los minutos son 00 → horario (01:00, 02:00, …)
                minutos = hora_raw.str.extract(r":(\d{2})")[0].astype(float)
                if minutos.max() == 0:
                    # Horario tipo "01:00"…"24:00": convertir directamente
                    #dt0 = pd.to_datetime(
                    #    df[c_date].astype(str).str.strip() + " " + hora_raw,
                    #    errors="coerce",
                    #    dayfirst=True
                    #)
                    # Si la hora máxima es 24 → restamos 1 hora a toda la serie
                    #if dt0.dt.hour.max() == 0 or (hora_raw.str.contains("24").any()):
                    #dt0 = dt0 - pd.Timedelta(hours=1)
                            # ⏰ Curva horaria tipo "01:00"…"24:00"
                    # 👉 Usamos 'd' directamente (ya en datetime), sin dayfirst ni conversión a string
                    dt0 = d + pd.to_timedelta(hora_raw + ":00")

                    # Si la serie empieza en 01:00 y termina en 00:00 del día siguiente → restar 1h
                    if dt0.dt.hour.min() == 1 and dt0.dt.hour.max() == 0:
                        dt0 = dt0 - pd.Timedelta(hours=1)
                    print ('horarios')
                    print(dt0.head(24))
                else:
                    # Cuartohoraria: 00:15, 00:30, etc.
                    print('cuarto horarios')
                    #h = pd.to_timedelta(hora_raw)
                    h = pd.to_timedelta(
                        hora_raw.where(hora_raw.str.count(":") == 2, hora_raw + ":00"),
                        errors="coerce"
                    )
                    dt0 = d + h
                    
            else:
                # Horas numéricas 1–24
                h = _parse_time_to_hour(df[c_time]).fillna(0)
                dt0 = d + pd.to_timedelta(h, unit="h")
                print("DEBUG --- dt0 primeras filas:")
                print(dt0.head(10))

                print("DEBUG --- diferencias en minutos:")
                print(dt0.diff().dt.total_seconds().head(10))
    
    except Exception as e:
        print("ERROR DETECTADO:")
        traceback.print_exc()
        raise

    print(df[c_date].head())
    
    print(_parse_date_ddmmyyyy(df[c_date]).head())
    #print (dt0)

    # --- df_in solo para vista previa ---
    df_in = df.copy()
    #print('df in')
    #print(df_in)


    # --- DETECTAR FRECUENCIA ---
    # Diferencia media en minutos
    delta_min = (dt0.diff().dt.total_seconds().dropna().median() / 60)
    if abs(delta_min - 60) < 1:
        freq = "H"      # Horaria
        ajuste_tiempo = pd.Timedelta(hours=1)
    elif abs(delta_min - 15) < 1:
        freq = "15T"    # Cuartohoraria
        ajuste_tiempo = pd.Timedelta(minutes=15)
    else:
        freq = "desconocida"
        ajuste_tiempo = pd.Timedelta(0)
        st.warning("Frecuencia no reconocida. No se aplica ajuste temporal.")



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
    elif freq == "15T":
        # si empieza en 00:15, corregir desplazando 15min atrás
        if first_valid.minute == 15:
            dt_adj = dt0 - pd.Timedelta(minutes=15)
        else:
            dt_adj = dt0.copy()
    else:
        dt_adj = dt0.copy()

    # Redondeo y TZ
    dt_adj = dt_adj.dt.floor(freq)
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
            periodos_path = "local_bbdd/periodos_horarios.xlsx"
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

            print(df_periodos)
                        
            #periodo = df_merge["periodo"].astype(str).str.upper().str.strip()

            #msg_periodos = 'Cargados periodos desde fichero auxiliar. Seleccione modo 3P/6P'
        except Exception as e:
            st.warning(f"No se pudieron cargar los periodos: {e}")
            periodo = np.nan
    
    # --- NUEVO BLOQUE: Determinación del ATR según periodos detectados ---
    try:
        if isinstance(periodo, pd.Series):
            # Extraemos el número del periodo (P1→1, etc.)
            numeros = periodo.dropna().str.extract(r"P(\d+)")[0].astype(float)
            if not numeros.empty and numeros.max() == 3:
                atr_dfnorm = "2.0"
            else:
                atr_dfnorm = None
        else:
            atr_dfnorm = None
    except Exception as e:
        atr_dfnorm = None
        print(f"Error determinando ATR: {e}")

    ind = pd.to_numeric(df[c_ind], errors="coerce") if c_ind else np.nan
    cap = pd.to_numeric(df[c_cap], errors="coerce") if c_cap else np.nan

    # --- df_norm con índice numérico (igual que df_in) ---
    df_norm = pd.DataFrame({
        "fecha_hora": dt_tz,
        "consumo_kWh": kwh_consumo,
        "excedentes_kWh": kwh_vertido,
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
    
    
    # --- Cálculo del saldo horario (consumo - vertido) ---
    saldo_horario = df_norm["consumo_kWh"].fillna(0) - df_norm["excedentes_kWh"].fillna(0)

    # --- Columnas “shadow” ---
    df_norm["consumo_neto_kWh"] = np.where(saldo_horario > 0, saldo_horario, 0)
    df_norm["vertido_neto_kWh"] = np.where(saldo_horario < 0, -saldo_horario, 0)

    print('df norm dentro de la funcion')
    print(df_norm)


    return df_in, df_norm, msg_unidades, flag_periodos_en_origen, df_periodos, atr_dfnorm, freq


def normalize_curve_simple(uploaded, origin="archivo") -> tuple[pd.DataFrame, pd.DataFrame, str]:

    import traceback

    #Lee y normaliza la curva, devolviendo (df_in, df_norm).
    #   Regla simple:
    #     - Si el primer registro válido está a las 01:00 → restar 1h a toda la serie.
    #     - Si está a las 00:00 → no tocar.
    #   Detección automática de formato de fecha (día primero o año primero)."""
    
    df, header_row = _read_any(uploaded)
    c_dt, c_date, c_time, c_kwh, c_per, c_ind, c_cap, c_ver = _guess_cols(df)

    if not (c_dt or (c_date and c_time)):
        raise ValueError("No se encontró columna de fecha u hora reconocible.")
    
    if not c_kwh:
        raise ValueError("No se encontró columna de consumo (kWh).")

    # --- Consumo ---
    kwh_consumo = pd.to_numeric(df[c_kwh].str.replace(",", ".", regex=False), errors="coerce")
    kwh_vertido = pd.to_numeric(df[c_ver].str.replace(",", ".", regex=False), errors="coerce") if c_ver else np.nan

    msg_unidades = ""

    if (header_row > 0) or ("wh" in str(c_kwh).lower() and "kwh" not in str(c_kwh).lower()):
        kwh_consumo = kwh_consumo / 1000
        kwh_vertido = kwh_vertido / 1000
        msg_unidades = "Detectado consumo en Wh → Convertido automáticamente a kWh"


    try:
        # --- Datetime base (naïve) ---
        # --- Datetime base (naïve) ---
        if c_dt:
            # Disponemos de fecha y hora en la misma columna
            sample = str(df[c_dt].dropna().iloc[0]).strip()

            # Detectar si TIENE hora → patrón HH:MM
            tiene_hora = re.search(r"\d{1,2}:\d{2}", sample) is not None

            if tiene_hora:
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
                print(f'Columna "{c_dt}" contiene solo fecha → pasamos a parseo por separado')
                raise ValueError("NO_DATETIME")

        else:
            # No hay columna datetime → pasar a fecha + hora separadas
            raise ValueError("NO_DATETIME")


    except ValueError as e:
        if str(e) == "NO_DATETIME":
            print("Entramos por fecha y hora separadas")
            print(df[c_time].head())

            # --- Fecha y hora en columnas separadas ---
            d = _parse_date_ddmmyyyy(df[c_date])
            hora_raw = df[c_time].astype(str).str.strip()

            print("hora_raw")
            print(hora_raw)

            # --- Corregir valores 24:00 ---
            mask_24 = hora_raw.isin(["24:00", "24:00:00"])
            if mask_24.any():
                hora_raw.loc[mask_24] = "00:00"
                d.loc[mask_24] = d.loc[mask_24] + pd.Timedelta(days=1)

            # Detectar casos con formato HH:MM o HH:MM:SS
            if hora_raw.str.contains(":").any():
                print("contiene :")

                minutos = hora_raw.str.extract(r":(\d{2})")[0].astype(float)

                if minutos.max() == 0:
                    # Horario tipo “01:00”
                    dt0 = d + pd.to_timedelta(hora_raw + ":00")

                    # Ajuste por casos 01:00→00:00 del día siguiente
                    if dt0.dt.hour.min() == 1 and dt0.dt.hour.max() == 0:
                        dt0 = dt0 - pd.Timedelta(hours=1)

                    print("horarios")
                    print(dt0.head(24))

                else:
                    # Cuartohoraria (00:15, 00:30…)
                    print("cuarto horarios")
                    h = pd.to_timedelta(
                        hora_raw.where(hora_raw.str.count(":") == 2,
                                    hora_raw + ":00"),
                        errors="coerce"
                    )
                    dt0 = d + h

            else:
                # Horas numéricas (1–24)
                h = _parse_time_to_hour(df[c_time]).fillna(0)
                dt0 = d + pd.to_timedelta(h, unit="h")

                print("DEBUG --- dt0 primeras filas:")
                print(dt0.head(10))

                print("DEBUG --- diferencias en minutos:")
                print(dt0.diff().dt.total_seconds().head(10))
    
    except Exception as e:
        print("ERROR DETECTADO:")
        traceback.print_exc()
        raise

    print(df[c_date].head())
    
    print(_parse_date_ddmmyyyy(df[c_date]).head())
    #print (dt0)

    # --- df_in solo para vista previa ---
    df_in = df.copy()
    #print('df in')
    #print(df_in)


    # --- DETECTAR FRECUENCIA ---
    # Diferencia media en minutos
    delta_min = (dt0.diff().dt.total_seconds().dropna().median() / 60)
    if abs(delta_min - 60) < 1:
        freq = "H"      # Horaria
        ajuste_tiempo = pd.Timedelta(hours=1)
    elif abs(delta_min - 15) < 1:
        freq = "15T"    # Cuartohoraria
        ajuste_tiempo = pd.Timedelta(minutes=15)
    else:
        freq = "desconocida"
        ajuste_tiempo = pd.Timedelta(0)
        st.warning("Frecuencia no reconocida. No se aplica ajuste temporal.")



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
    elif freq == "15T":
        # si empieza en 00:15, corregir desplazando 15min atrás
        if first_valid.minute == 15:
            dt_adj = dt0 - pd.Timedelta(minutes=15)
        else:
            dt_adj = dt0.copy()
    else:
        dt_adj = dt0.copy()

    # Redondeo y TZ
    dt_adj = dt_adj.dt.floor(freq)
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
            periodos_path = "local_bbdd/periodos_horarios.xlsx"
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

            print(df_periodos)
                        
            #periodo = df_merge["periodo"].astype(str).str.upper().str.strip()

            #msg_periodos = 'Cargados periodos desde fichero auxiliar. Seleccione modo 3P/6P'
        except Exception as e:
            st.warning(f"No se pudieron cargar los periodos: {e}")
            periodo = np.nan
    
    # --- NUEVO BLOQUE: Determinación del ATR según periodos detectados ---
    try:
        if isinstance(periodo, pd.Series):
            # Extraemos el número del periodo (P1→1, etc.)
            numeros = periodo.dropna().str.extract(r"P(\d+)")[0].astype(float)
            if not numeros.empty and numeros.max() == 3:
                atr_dfnorm = "2.0"
            else:
                atr_dfnorm = None
        else:
            atr_dfnorm = None
    except Exception as e:
        atr_dfnorm = None
        print(f"Error determinando ATR: {e}")

    ind = pd.to_numeric(df[c_ind], errors="coerce") if c_ind else np.nan
    cap = pd.to_numeric(df[c_cap], errors="coerce") if c_cap else np.nan

    # --- df_norm con índice numérico (igual que df_in) ---
    df_norm = pd.DataFrame({
        "fecha_hora": dt_tz,
        "consumo_kWh": kwh_consumo,
        "excedentes_kWh": kwh_vertido,
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
    
    
    # --- Cálculo del saldo horario (consumo - vertido) ---
    saldo_horario = df_norm["consumo_kWh"].fillna(0) - df_norm["excedentes_kWh"].fillna(0)

    # --- Columnas “shadow” ---
    df_norm["consumo_neto_kWh"] = np.where(saldo_horario > 0, saldo_horario, 0)
    df_norm["vertido_neto_kWh"] = np.where(saldo_horario < 0, -saldo_horario, 0)

    print('df norm dentro de la funcion')
    print(df_norm)


    return df_in, df_norm, msg_unidades, flag_periodos_en_origen, df_periodos, atr_dfnorm, freq


# ================================================================================
# GRÁFICOS
#=================================================================================


def graficar_curva(df_norm, frec):
    # Asegurar índice temporal
    df_norm = df_norm.set_index("fecha_hora")

    # --- Modo HORARIO ---
    if st.session_state.modo_agrupacion == "Horario":
        df_plot = df_norm.reset_index()
        # Asegurar orden lógico de periodos (P1→P6)
        orden_periodos = list(colores_periodo.keys())
        df_plot['periodo'] = pd.Categorical(df_plot['periodo'], categories=orden_periodos, ordered=True)

        if frec=='15T':
            titulo = 'Curva cuarto horaria de consumo (kWh)'
        else:
            titulo = 'Curva horaria de consumo (kWh)'
        
        fig = px.bar(
            df_plot,
            x="fecha_hora",
            y="consumo_kWh",
            labels={"fecha_hora": "Fecha y hora", "consumo_kWh": "Consumo (kWh)"},
            color='periodo',
            color_discrete_map=colores_periodo,
            category_orders={'periodo': orden_periodos},  # 👈 fuerza el orden
            #title="Curva horaria de consumo (kWh)"
            title=titulo
        )
        fig.update_layout(
            xaxis_title="Fecha",
            yaxis_title="Consumo (kWh)",
            #plot_bgcolor="white",
            bargap=0.1,
            legend=dict(
                orientation="h",        # horizontal
                yanchor="bottom",       # anclaje vertical inferior
                y=1.02,                 # un poco por encima del gráfico
                xanchor="center",       # anclaje horizontal centrado
                x=0.5,                  # centrado
                title_text=""           # sin título
            )
        )
        #fig.update_traces(mode="lines", line=dict(color="cyan"))

    # --- Modo DIARIO ---
    elif st.session_state.modo_agrupacion == "Diario":
        df_plot = df_norm.resample("D")["consumo_kWh"].sum().reset_index()
        fig = px.bar(
            df_plot,
            x="fecha_hora",
            y="consumo_kWh",
            labels={"fecha_hora": "Fecha", "consumo_kWh": "Consumo (kWh)"},
            color="consumo_kWh",
            color_continuous_scale="Blues",
            title="Consumo diario (kWh)"
        )
        fig.update_layout(
            xaxis_title="Fecha",
            yaxis_title="Consumo (kWh)",
            #plot_bgcolor="white",
            bargap=0.1,
            legend=dict(
                orientation="h",        # horizontal
                yanchor="bottom",       # anclaje vertical inferior
                y=1.02,                 # un poco por encima del gráfico
                xanchor="center",       # anclaje horizontal centrado
                x=0.5,                  # centrado
                title_text=""           # sin título
            )
        )

    # --- Modo MENSUAL ---
    elif st.session_state.modo_agrupacion == "Mensual":
        df_plot = df_norm.resample("M")["consumo_kWh"].sum().reset_index()
        df_plot["Mes"] = df_plot["fecha_hora"].dt.strftime("%b %Y")
        fig = px.bar(
            df_plot,
            x="Mes",
            y="consumo_kWh",
            labels={"Mes": "Mes", "consumo_kWh": "Consumo (kWh)"},
            color="consumo_kWh",
            color_continuous_scale="Blues",
            title="Consumo mensual (kWh)"
        )
        fig.update_layout(
            xaxis_title="Mes",
            yaxis_title="Consumo (kWh)",
            #plot_bgcolor="white",
            bargap=0.1,
            legend=dict(
                orientation="h",        # horizontal
                yanchor="bottom",       # anclaje vertical inferior
                y=1.02,                 # un poco por encima del gráfico
                xanchor="center",       # anclaje horizontal centrado
                x=0.5,                  # centrado
                title_text=""           # sin título
            )
        )
    
    return fig

def graficar_curva_neteo(df_norm):
    # Asegurar índice temporal
    df_norm = df_norm.set_index("fecha_hora")

    # --- Modo HORARIO ---
    if st.session_state.modo_agrupacion == "Horario":
        df_plot = df_norm.reset_index()

        
        fig = px.bar(
            df_plot,
            x="fecha_hora",
            y=["consumo_neto_kWh", "vertido_neto_kWh"],
            labels={"fecha_hora": "Fecha y hora", "consumo_neto_kWh": "Consumo (kWh)"},
            #color='periodo',
            #color_discrete_map=colores_periodo,
            color_discrete_map={"consumo_neto_kWh": "#e74c3c","vertido_neto_kWh": "#27ae60"},   

            title="Curva horaria de demanda/vertido (kWh)"
        )
        fig.update_layout(
            xaxis_title="Fecha",
            yaxis_title="kWh",
            #plot_bgcolor="white",
            bargap=0.1,
            legend=dict(
                orientation="h",        # horizontal
                yanchor="bottom",       # anclaje vertical inferior
                y=1.02,                 # un poco por encima del gráfico
                xanchor="center",       # anclaje horizontal centrado
                x=0.5,                  # centrado
                title_text=""           # sin título
            )
        )
        #fig.update_traces(mode="lines", line=dict(color="cyan"))

    # --- Modo DIARIO ---
    elif st.session_state.modo_agrupacion == "Diario":
        df_plot = df_norm.resample("D")["consumo_neto_kWh", "vertido_neto_kWh"].sum().reset_index()
        fig = px.bar(
            df_plot,
            x="fecha_hora",
            y=["consumo_neto_kWh", "vertido_neto_kWh"],
            labels={"fecha_hora": "Fecha", "consumo_kWh": "Consumo (kWh)"},
            #color="consumo_kWh",
            #color_continuous_scale="Blues",
            color_discrete_map={"consumo_neto_kWh": "#e74c3c","vertido_neto_kWh": "#27ae60"},  
            title="Demanda/Vertido diario (kWh)"
        )
        fig.update_layout(
            xaxis_title="Fecha",
            yaxis_title="kWh",
            #plot_bgcolor="white",
            bargap=0.1,
            legend=dict(
                orientation="h",        # horizontal
                yanchor="bottom",       # anclaje vertical inferior
                y=1.02,                 # un poco por encima del gráfico
                xanchor="center",       # anclaje horizontal centrado
                x=0.5,                  # centrado
                title_text=""           # sin título
            )
        )

    # --- Modo MENSUAL ---
    elif st.session_state.modo_agrupacion == "Mensual":
        df_plot = df_norm.resample("M")["consumo_neto_kWh", "vertido_neto_kWh"].sum().reset_index()
        df_plot["Mes"] = df_plot["fecha_hora"].dt.strftime("%b %Y")
        fig = px.bar(
            df_plot,
            x="Mes",
            y=["consumo_neto_kWh", "vertido_neto_kWh"],
            labels={"Mes": "Mes", "consumo_kWh": "Consumo (kWh)"},
            #color="consumo_kWh",
            #color_continuous_scale="Blues",
            color_discrete_map={"consumo_neto_kWh": "#e74c3c","vertido_neto_kWh": "#27ae60"},
            title="Demanda/Vertido mensual (kWh)"
        )
        fig.update_layout(
            xaxis_title="Mes",
            yaxis_title="kWh",
            #plot_bgcolor="white",
            bargap=0.1,
            legend=dict(
                orientation="h",        # horizontal
                yanchor="bottom",       # anclaje vertical inferior
                y=1.02,                 # un poco por encima del gráfico
                xanchor="center",       # anclaje horizontal centrado
                x=0.5,                  # centrado
                title_text=""           # sin título
            )
        )
    
    return fig

def graficar_media_horaria(df_norm):
    

    # Filtrar según opción
    if st.session_state.opcion_tipodia == "L-V":
        df_sel = df_norm[df_norm["tipo_dia"] == "L-V"]
        add_title='LUNES A VIERNES'
    elif st.session_state.opcion_tipodia == "FS":
        df_sel = df_norm[df_norm["tipo_dia"] == "FS"]
        add_title='FIN DE SEMANA'
    else:
        df_sel = df_norm.copy()
        add_title='TOTAL'

    # Calcular media por hora
    df_horas = (df_sel.resample("H", on="fecha_hora")["consumo_kWh"].sum().reset_index())
    #df_sel["hora"] = df_sel["fecha_hora"].dt.hour
    df_horas["hora"] = df_horas["fecha_hora"].dt.hour
    df_horas = (
        df_horas.groupby("hora", as_index=False)["consumo_kWh"]
        #df_sel.groupby("hora", as_index=False)["consumo_kWh"]
        .mean()
        .rename(columns={"consumo_kWh": "media_kWh"})
    )

    # Gráfico
    
    fig = px.bar(
        df_horas,
        x="hora",
        y="media_kWh",
        labels={"hora": "Hora del día", "media_kWh": "Consumo medio (kWh)"},
        color="media_kWh",
        color_continuous_scale="Blues",
        title=f"Perfil medio horario: {add_title}"
    )
    fig.update_layout(
        xaxis=dict(dtick=1),
        yaxis_title="kWh medios",
        #plot_bgcolor="white"
    )

    return fig



def graficar_queso_periodos(df_norm):

    
    # Agrupar por periodo
    df_periodos = (
        df_norm.groupby("periodo", as_index=False)["consumo_kWh"]
        .sum()
        .sort_values("periodo")
    )

    # Ordenar los periodos de P1 a P6 según el orden lógico
    orden = [f"P{i}" for i in range(1, 7)]
    df_periodos["periodo"] = pd.Categorical(df_periodos["periodo"], categories=orden, ordered=True)
    df_periodos = df_periodos.sort_values("periodo")

    # Calcular porcentaje
    total = df_periodos["consumo_kWh"].sum()
    df_periodos["porcentaje"] = (df_periodos["consumo_kWh"] / total * 100).round(1)

    # Gráfico tipo “queso”
    fig = px.pie(
        df_periodos,
        names="periodo",
        values="consumo_kWh",
        color="periodo",
        color_discrete_map=colores_periodo,
        title="Consumo por periodo tarifario",
        hole=0.4,
        category_orders={"periodo": orden}  # 👈 este es el truco
    )

    # Etiquetas con porcentaje y kWh
    fig.update_traces(
        textinfo="label+percent",
        hovertemplate="%{label}<br>%{value:.0f} kWh<br>(%{percent})"
    )

    # 🔹 Añadir texto central con el total
    fig.add_annotation(
        text=f"<b>{int(total):,} kWh</b>".replace(",", "."),
        showarrow=False,
        font=dict(size=18)
    )

    return fig






