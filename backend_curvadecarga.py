import streamlit as st
import plotly.express as px
import pandas as pd
import numpy as np
import io, re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pathlib import Path
from unidecode import unidecode
import plotly.graph_objects as go
from backend_comun import aplicar_estilo, aplicar_texto_pie_porcentaje
from formato_es import formato_numero_es


TZ = "Europe/Madrid"
AXON_API_BASE = "https://api.twinmeter.es"
DATADIS_API_BASE = "https://datadis.es"
BASE_DIR = Path(__file__).resolve().parent


class DatadisLimiteConsultas(RuntimeError):
    """Datadis rechaza repetir una consulta antes de que venza su límite."""


AXON_RETRY_STATUS = (429, 500, 502, 503, 504)


def crear_sesion_axon() -> requests.Session:
    """Crea una sesión tolerante a fallos temporales de la API de Axon."""
    reintentos = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.75,
        status_forcelist=AXON_RETRY_STATUS,
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adaptador = HTTPAdapter(max_retries=reintentos)
    sesion = requests.Session()
    sesion.mount("https://", adaptador)
    return sesion

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

PATRONES_COLUMNAS_CALIDAD = (
    r"real.?estim",
    r"estimad",
    r"metodo.?obt",
    r"tipo.?lect",
    r"cualificador.*activa.*import",
    r"lectura.?real",
    r"fuente.?final",
    r"firmeza",
    r"estado",
    r"bandera",
)


def detectar_columnas_calidad_lectura(df_origen, max_valores=8):
    """Resume columnas que pueden informar si una lectura es real o estimada.

    No interpreta códigos opacos de distribuidora. Expone sus valores y solo
    clasifica textos inequívocos para evitar falsos diagnósticos.
    """
    if df_origen is None or df_origen.empty:
        return []

    resultado = []
    for columna in df_origen.columns:
        nombre_limpio = _clean(columna)
        if not any(re.search(patron, nombre_limpio) for patron in PATRONES_COLUMNAS_CALIDAD):
            continue

        serie = df_origen[columna].astype("string").str.strip()
        serie = serie[serie.notna() & ~serie.str.lower().isin(("", "nan", "none"))]
        conteos = serie.value_counts(dropna=False).head(max_valores)
        valores_normalizados = serie.map(_clean)
        estimadas_explicitas = int(
            valores_normalizados.str.contains(r"estim", regex=True, na=False).sum()
        )
        reales_explicitas = int(
            valores_normalizados.str.contains(r"\breal", regex=True, na=False).sum()
        )
        resultado.append({
            "columna": str(columna),
            "informadas": int(len(serie)),
            "sin_informar": int(len(df_origen) - len(serie)),
            "reales_explicitas": reales_explicitas,
            "estimadas_explicitas": estimadas_explicitas,
            "valores": {str(valor): int(cantidad) for valor, cantidad in conteos.items()},
        })
    return resultado


def analizar_calidad_curva(
    df_norm,
    df_origen=None,
    frecuencia=None,
    periodos_en_origen=False,
    origen="archivo",
):
    """Calcula incidencias sin modificar la curva normalizada."""
    diagnostico = {
        "origen": str(origen),
        "filas": int(len(df_norm)) if df_norm is not None else 0,
        "frecuencia": frecuencia,
        "fechas_invalidas": 0,
        "consumos_ausentes": 0,
        "consumos_negativos": 0,
        "duplicados_fecha_hora": 0,
        "saltos_temporales": 0,
        "intervalos_ausentes_estimados": 0,
        "periodos_ausentes": 0,
        "columnas_calidad": detectar_columnas_calidad_lectura(df_origen),
    }
    if df_norm is None or df_norm.empty:
        return diagnostico

    fechas = pd.to_datetime(df_norm.get("fecha_hora"), errors="coerce")
    consumos = pd.to_numeric(df_norm.get("consumo_kWh"), errors="coerce")
    diagnostico["fechas_invalidas"] = int(fechas.isna().sum())
    diagnostico["consumos_ausentes"] = int(consumos.isna().sum())
    diagnostico["consumos_negativos"] = int((consumos < 0).sum())

    fechas_validas = fechas.dropna()
    diagnostico["duplicados_fecha_hora"] = int(
        len(fechas_validas) - fechas_validas.nunique()
    )
    minutos_esperados = {"H": 60, "QH": 15, "10MIN": 10}.get(frecuencia)
    if minutos_esperados and not fechas_validas.empty:
        diferencias = (
            fechas_validas.drop_duplicates().sort_values().diff().dt.total_seconds()
            / 60
        ).dropna()
        saltos = diferencias[diferencias > minutos_esperados * 1.5]
        diagnostico["saltos_temporales"] = int(len(saltos))
        diagnostico["intervalos_ausentes_estimados"] = int(
            ((saltos / minutos_esperados).round() - 1).clip(lower=0).sum()
        )

    if periodos_en_origen and "periodo" in df_norm.columns:
        periodos = df_norm["periodo"].astype("string").str.strip()
        diagnostico["periodos_ausentes"] = int(
            (periodos.isna() | periodos.str.lower().isin(("", "nan", "none"))).sum()
        )
    return diagnostico


@st.cache_data(show_spinner=False)
def cargar_calendario_periodos(periodos_path, mtime_ns):
    """Carga y prepara una vez cada versión del calendario tarifario."""
    del mtime_ns  # Forma parte de la clave de caché.
    df_periodos = pd.read_excel(
        periodos_path,
        dtype={
            "año": int,
            "mes": int,
            "dia": int,
            "hora": int,
            "dh_3p": str,
            "dh_6p": str,
        },
    )
    if (
        pd.api.types.is_numeric_dtype(df_periodos["hora"])
        or df_periodos["hora"].astype(str).str.match(r"^\d+$").all()
    ):
        texto_hora = df_periodos["hora"].astype(str) + ":00:00"
    else:
        hora_aux = df_periodos["hora"].astype(str).str.strip()
        texto_hora = hora_aux.where(hora_aux.str.count(":") == 2, hora_aux + ":00")
    df_periodos["fecha_hora"] = pd.to_datetime(
        df_periodos["fecha"].astype(str) + " " + texto_hora,
        errors="coerce",
        dayfirst=True,
    )
    return df_periodos

def obtener_datos_contador(
    usuario,
    password,
    cups,
    fecha_inicio,
    fecha_fin,
    tipo_curva="TM2",
    timeout=30,
):
    """Descarga de Axon una curva horaria (TM1) o cuartohoraria (TM2).
    
    Según documentación Axon, la respuesta incluye:
    - energia: Energía activa entrante (consumida)
    - exportada: Energía activa saliente (vertida)
    - ie1q: Energía inductiva primer cuadrante (reactiva inductiva)
    - ce2q: Energía capacitiva segundo cuadrante
    - ie3q: Energía inductiva tercer cuadrante
    - ce4q: Energía capacitiva cuarto cuadrante
    - periodo: Si periodos=1
    """

    usuario = str(usuario or "").strip()
    password = str(password or "")
    # Axon identifica el suministro por el CUPS base de 20 caracteres. Las
    # extensiones de dos caracteres que pueden aparecer en facturas no deben
    # enviarse a su buscador.
    cups = re.sub(
        r"[^A-Z0-9]", "", str(cups or "").upper()
    )[:20]
    tipo_curva = str(tipo_curva or "").strip().upper()
    if not usuario or not password or not cups:
        raise ValueError("Usuario, contraseña y CUPS son obligatorios.")
    if len(cups) != 20:
        raise ValueError(
            "El CUPS base enviado a Axon debe contener 20 caracteres "
            "alfanuméricos."
        )
    if tipo_curva not in {"TM1", "TM2"}:
        raise ValueError("El tipo de curva debe ser TM1 o TM2.")

    inicio = pd.to_datetime(fecha_inicio, errors="coerce")
    fin = pd.to_datetime(fecha_fin, errors="coerce")
    if pd.isna(inicio) or pd.isna(fin):
        raise ValueError("El rango de fechas no es válido.")
    if inicio.date() > fin.date():
        raise ValueError("La fecha inicial no puede ser posterior a la final.")

    def respuesta_json(respuesta, contexto):
        try:
            respuesta.raise_for_status()
        except requests.RequestException as exc:
            if respuesta.status_code in AXON_RETRY_STATUS:
                raise RuntimeError(
                    f"Axon no ha podido completar {contexto}: el servicio "
                    f"sigue temporalmente no disponible después de varios "
                    f"intentos (HTTP {respuesta.status_code})."
                ) from exc
            raise RuntimeError(
                f"Axon no ha podido completar {contexto} "
                f"(HTTP {respuesta.status_code})."
            ) from exc
        try:
            return respuesta.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Axon ha devuelto una respuesta no válida durante {contexto}."
            ) from exc

    try:
        with crear_sesion_axon() as sesion:
            autenticacion = respuesta_json(
                sesion.get(
                    f"{AXON_API_BASE}/auth",
                    params={"usuario": usuario, "pass": password},
                    timeout=timeout,
                ),
                "la autenticación",
            )
            token = autenticacion.get("data", {}).get("token")
            if not token:
                raise RuntimeError(
                    "Axon no ha proporcionado un token de autenticación."
                )

            cabeceras = {"token": token}
            respuesta_cups = respuesta_json(
                sesion.get(
                    f"{AXON_API_BASE}/suministros/",
                    params={"cups": cups},
                    headers=cabeceras,
                    timeout=timeout,
                ),
                "la búsqueda del CUPS",
            )
            datos_cups = respuesta_cups.get("data")
            if isinstance(datos_cups, list):
                suministro = next(
                    (
                        item
                        for item in datos_cups
                        if re.sub(
                            r"[^A-Z0-9]",
                            "",
                            str(item.get("cups", "")).upper(),
                        )[:20] == cups
                    ),
                    datos_cups[0] if datos_cups else {},
                )
            elif isinstance(datos_cups, dict):
                suministro = datos_cups
            else:
                suministro = {}
            cups_id = suministro.get("cups_id")
            if not cups_id:
                raise ValueError(
                    "Axon no ha encontrado el CUPS indicado o no permite acceder a él."
                )

            # --- DESCARGA DE MEDIDAS (INCLUYE ACTIVA, REACTIVA, PERIODOS EN UNA SOLA LLAMADA) ---
            respuesta_medidas = respuesta_json(
                sesion.get(
                    f"{AXON_API_BASE}/medidas",
                    params={
                        "cups_id": cups_id,
                        "fecha_ini": inicio.date().isoformat(),
                        "fecha_fin": fin.date().isoformat(),
                        "tipo_curva": tipo_curva,
                        "periodos": 1,  # Solicitar periodos en la respuesta
                    },
                    headers=cabeceras,
                    timeout=timeout,
                ),
                "la descarga de medidas",
            )
    except requests.RequestException as exc:
        raise RuntimeError(
            "No se ha podido conectar con Axon. Comprueba la conexión e inténtalo "
            "de nuevo."
        ) from exc

    # --- PROCESAMIENTO DE MEDIDAS ---
    medidas = respuesta_medidas.get("data", [])
    if not isinstance(medidas, list) or not medidas:
        raise ValueError("Axon no ha devuelto medidas para el rango seleccionado.")

    curva = pd.DataFrame(medidas)
    columnas_obligatorias = {"fecha", "energia"}
    if not columnas_obligatorias.issubset(curva.columns):
        raise RuntimeError(
            "La respuesta de Axon no contiene las columnas fecha y energía."
        )

    # --- MAPEO DE COLUMNAS AXON ---
    # Función auxiliar para buscar columnas por patrones regex
    def find_col(patterns, df=None):
        """Busca la primera columna que coincida con algún patrón regex."""
        if df is None:
            df = curva
        for col in df.columns:
            col_clean = _clean(col)
            for pattern in patterns:
                if re.search(pattern, col_clean, re.IGNORECASE):
                    return col
        return None

    # Buscar campos según documentación Axon
    c_periodo = find_col([r"periodo"])
    c_ie1q = find_col([r"ie1q"])  # Inductiva primer cuadrante
    c_ce2q = find_col([r"ce2q"])  # Capacitiva segundo cuadrante
    c_ie3q = find_col([r"ie3q"])  # Inductiva tercer cuadrante
    c_ce4q = find_col([r"ce4q"])  # Capacitiva cuarto cuadrante
    c_exportada = find_col([r"exportada", r"exporta"])

    # --- EXTRACCIÓN DE DATOS RAW (SIN NORMALIZAR) ---
    # Nombres descriptivos para que _guess_cols los reconozca después
    curva["Fecha y hora"] = pd.to_datetime(
        curva["fecha"], dayfirst=True, errors="coerce"
    )
    
    # Consumo activo (kWh)
    curva["Consumo (kWh)"] = pd.to_numeric(
        curva["energia"].astype(str).str.replace(",", ".", regex=False),
        errors="coerce",
    )
    
    # Período (si existe, desde parámetro periodos=1)
    if c_periodo:
        curva["Periodo"] = curva[c_periodo]
    
    # Energía Reactiva (kVArh) - Axon devuelve en 4 campos según cuadrante
    # ie1q: Inductiva 1er cuadrante (reactiva inductiva entrada, típicamente penalizada en España)
    # ce2q: Capacitiva 2do cuadrante (reactiva capacitiva salida)
    # ie3q: Inductiva 3er cuadrante (reactiva inductiva salida)
    # ce4q: Capacitiva 4to cuadrante (reactiva capacitiva entrada)
    reactivas_disponibles = []
    if c_ie1q:
        reactivas_disponibles.append(c_ie1q)
    if c_ce2q:
        reactivas_disponibles.append(c_ce2q)
    if c_ie3q:
        reactivas_disponibles.append(c_ie3q)
    if c_ce4q:
        reactivas_disponibles.append(c_ce4q)
    
    # Usar ie1q si está disponible (es la penalizada), si no usar la primera encontrada
    c_reactiva_final = c_ie1q or (reactivas_disponibles[0] if reactivas_disponibles else None)
    if c_reactiva_final:
        curva["Reactiva (kVArh)"] = pd.to_numeric(
            curva[c_reactiva_final].astype(str).str.replace(",", ".", regex=False),
            errors="coerce",
        )
    
    # Exportación/Vertido (kWh)
    if c_exportada:
        curva["Vertido (kWh)"] = pd.to_numeric(
            curva[c_exportada].astype(str).str.replace(",", ".", regex=False),
            errors="coerce",
        )

    curva = curva.dropna(subset=["Fecha y hora", "Consumo (kWh)"])
    if curva.empty:
        raise ValueError("Axon no ha devuelto medidas utilizables.")

    # --- CONSTRUCCIÓN DEL DATAFRAME FINAL ---
    # ⚠️ IMPORTANTE: Sin transformaciones. Los datos se devuelven raw de Axon.
    # El ajuste de hora (desfase QH/H) se hace en normalize_curve_simple
    frecuencia = "QH" if tipo_curva == "TM2" else "H"
    
    # Columnas a retornar (en orden lógico, similar a normalize_curve_simple)
    columnas_salida = ["Fecha y hora", "Consumo (kWh)"]
    if "Vertido (kWh)" in curva.columns and curva["Vertido (kWh)"].notna().any():
        columnas_salida.append("Vertido (kWh)")
    if "Generación (kWh)" in curva.columns and curva["Generación (kWh)"].notna().any():
        columnas_salida.append("Generación (kWh)")
    if "Reactiva (kVArh)" in curva.columns and curva["Reactiva (kVArh)"].notna().any():
        columnas_salida.append("Reactiva (kVArh)")
    if "Capacitiva (kVArh)" in curva.columns and curva["Capacitiva (kVArh)"].notna().any():
        columnas_salida.append("Capacitiva (kVArh)")
    if "Periodo" in curva.columns and curva["Periodo"].notna().any():
        columnas_salida.append("Periodo")
    
    curva = (
        curva[columnas_salida]
        .drop_duplicates(subset="Fecha y hora", keep="first")
        .sort_values("Fecha y hora")
        .reset_index(drop=True)
    )
    return curva, frecuencia


def _datadis_json(response, contexto):
    """Valida una respuesta Datadis sin exponer credenciales ni el token."""
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        detalle = str(getattr(response, "text", "") or "").strip()[:300]
        mensaje = f"Datadis no ha podido completar {contexto} (HTTP {response.status_code})."
        if detalle:
            mensaje += f" {detalle}"
        if response.status_code == 429:
            raise DatadisLimiteConsultas(mensaje) from exc
        raise RuntimeError(mensaje) from exc
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Datadis ha devuelto una respuesta no válida durante {contexto}."
        ) from exc


def autenticar_datadis(usuario, password, timeout=30, session=None):
    usuario = str(usuario or "").strip()
    password = str(password or "")
    if not usuario or not password:
        raise ValueError("Usuario y contraseña de Datadis son obligatorios.")

    cliente = session or requests
    try:
        respuesta = cliente.post(
            f"{DATADIS_API_BASE}/nikola-auth/tokens/login",
            data={"username": usuario, "password": password},
            timeout=timeout,
        )
        respuesta.raise_for_status()
    except requests.RequestException as exc:
        codigo = getattr(getattr(exc, "response", None), "status_code", None)
        sufijo = f" (HTTP {codigo})" if codigo else ""
        raise RuntimeError(f"No se ha podido iniciar sesión en Datadis{sufijo}.") from exc

    token = str(respuesta.text or "").strip().strip('"')
    if not token:
        raise RuntimeError("Datadis no ha proporcionado un token de autenticación.")
    return token


def obtener_suministros_datadis(
    usuario,
    password,
    authorized_nif=None,
    timeout=30,
    session=None,
):
    """Autentica y devuelve los suministros propios o autorizados."""
    cliente = session or requests.Session()
    cerrar = session is None
    try:
        token = autenticar_datadis(usuario, password, timeout=timeout, session=cliente)
        params = {}
        authorized_nif = str(authorized_nif or "").strip().upper()
        if authorized_nif:
            params["authorizedNif"] = authorized_nif
        respuesta = cliente.get(
            f"{DATADIS_API_BASE}/api-private/api/get-supplies",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        datos = _datadis_json(respuesta, "la consulta de suministros")
    finally:
        if cerrar:
            cliente.close()

    if not isinstance(datos, list):
        raise RuntimeError("Datadis ha devuelto un listado de suministros no válido.")
    suministros = pd.DataFrame(datos)
    obligatorias = {"cups", "distributorCode", "pointType"}
    if suministros.empty:
        raise ValueError("Datadis no ha devuelto suministros para este usuario.")
    if not obligatorias.issubset(suministros.columns):
        raise RuntimeError(
            "La respuesta de Datadis no contiene CUPS, distribuidora y tipo de punto."
        )
    return suministros


def obtener_detalle_contrato_datadis(
    usuario,
    password,
    suministro,
    authorized_nif=None,
    timeout=30,
    session=None,
):
    """Devuelve el detalle del contrato de un CUPS, incluidas sus potencias."""
    faltantes = [
        campo for campo in ("cups", "distributorCode")
        if not str(suministro.get(campo, "") or "").strip()
    ]
    if faltantes:
        raise ValueError(f"Faltan datos del suministro Datadis: {', '.join(faltantes)}.")

    cliente = session or requests.Session()
    cerrar = session is None
    try:
        token = autenticar_datadis(usuario, password, timeout=timeout, session=cliente)
        params = {
            "cups": str(suministro["cups"]).strip().upper(),
            "distributorCode": str(suministro["distributorCode"]).strip(),
        }
        authorized_nif = str(authorized_nif or "").strip().upper()
        if authorized_nif:
            params["authorizedNif"] = authorized_nif
        respuesta = cliente.get(
            f"{DATADIS_API_BASE}/api-private/api/get-contract-detail",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        datos = _datadis_json(respuesta, "la consulta del detalle de contrato")
    finally:
        if cerrar:
            cliente.close()

    if isinstance(datos, list):
        detalle = datos[0] if datos else None
    elif isinstance(datos, dict):
        detalle = datos
    else:
        detalle = None
    if not isinstance(detalle, dict) or not detalle:
        raise ValueError("Datadis no ha devuelto el detalle del contrato.")
    return detalle


def extraer_potencias_contratadas_datadis(detalle):
    """Convierte contractedPowerkW en un diccionario P1, P2, ... validado."""
    valores = detalle.get("contractedPowerkW") if isinstance(detalle, dict) else None
    if not isinstance(valores, (list, tuple)) or not valores:
        return {}
    potencias = {}
    for indice, valor in enumerate(valores[:6], start=1):
        numero = pd.to_numeric(str(valor).replace(",", "."), errors="coerce")
        if pd.notna(numero):
            potencias[f"P{indice}"] = float(numero)
    return potencias


def _descargar_consumo_datadis(
    cliente,
    token,
    suministro,
    fecha_inicio,
    fecha_fin,
    measurement_type,
    authorized_nif=None,
    timeout=60,
):
    params = {
        "cups": str(suministro["cups"]).strip().upper(),
        "distributorCode": str(suministro["distributorCode"]).strip(),
        "startDate": pd.Timestamp(fecha_inicio).strftime("%Y/%m"),
        "endDate": pd.Timestamp(fecha_fin).strftime("%Y/%m"),
        "measurementType": str(measurement_type),
        "pointType": str(suministro["pointType"]).strip(),
    }
    authorized_nif = str(authorized_nif or "").strip().upper()
    if authorized_nif:
        params["authorizedNif"] = authorized_nif

    respuesta = cliente.get(
        f"{DATADIS_API_BASE}/api-private/api/get-consumption-data",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    datos = _datadis_json(respuesta, "la descarga de consumos")
    if not isinstance(datos, list):
        raise RuntimeError("Datadis ha devuelto datos de consumo no válidos.")
    return pd.DataFrame(datos)


def _descargar_consumo_datadis_con_reintentos(
    cliente,
    token,
    suministro,
    fecha_inicio,
    fecha_fin,
    measurement_type,
    authorized_nif=None,
    timeout=60,
    max_intentos=3,
):
    """Reintenta Datadis; ante 429 amplía el inicio un mes en cada intento."""
    max_intentos = max(1, int(max_intentos))
    ultimo_limite = None
    inicio_intento = pd.Timestamp(fecha_inicio)
    for intento in range(max_intentos):
        try:
            curva = _descargar_consumo_datadis(
                cliente,
                token,
                suministro,
                inicio_intento,
                fecha_fin,
                measurement_type,
                authorized_nif=authorized_nif,
                timeout=timeout,
            )
        except DatadisLimiteConsultas as exc:
            ultimo_limite = exc
            if intento + 1 == max_intentos:
                raise
            inicio_intento = (
                pd.Timestamp(fecha_inicio) - pd.DateOffset(months=intento + 1)
            ).to_period("M").start_time
            continue
        if not curva.empty:
            return curva
    if ultimo_limite is not None:
        raise ultimo_limite
    return curva


def obtener_consumo_datadis(
    usuario,
    password,
    suministro,
    fecha_inicio,
    fecha_fin,
    authorized_nif=None,
    preferir_qh=False,
    timeout=60,
    session=None,
    max_intentos=3,
):
    """Descarga activa H o QH, reintentando hasta tres respuestas vacías."""
    inicio = pd.to_datetime(fecha_inicio, errors="coerce", dayfirst=True)
    fin = pd.to_datetime(fecha_fin, errors="coerce", dayfirst=True)
    if pd.isna(inicio) or pd.isna(fin) or inicio.date() > fin.date():
        raise ValueError("El rango de fechas de Datadis no es válido.")

    faltantes = [
        campo for campo in ("cups", "distributorCode", "pointType")
        if not str(suministro.get(campo, "") or "").strip()
    ]
    if faltantes:
        raise ValueError(f"Faltan datos del suministro Datadis: {', '.join(faltantes)}.")

    cliente = session or requests.Session()
    cerrar = session is None
    try:
        token = autenticar_datadis(usuario, password, timeout=timeout, session=cliente)
        point_type = str(suministro["pointType"]).strip().split(".")[0]
        intentar_qh = bool(preferir_qh and point_type not in {"4", "5"})
        aviso_fallback = None
        if intentar_qh:
            curva = _descargar_consumo_datadis_con_reintentos(
                cliente, token, suministro, inicio, fin, "1",
                authorized_nif=authorized_nif, timeout=timeout,
                max_intentos=max_intentos,
            )
            frecuencia = "QH"
        else:
            curva = _descargar_consumo_datadis_con_reintentos(
                cliente, token, suministro, inicio, fin, "0",
                authorized_nif=authorized_nif, timeout=timeout,
                max_intentos=max_intentos,
            )
            frecuencia = "H"
    finally:
        if cerrar:
            cliente.close()

    obligatorias = {"date", "time", "consumptionKWh"}
    if curva.empty:
        raise ValueError("Datadis no ha devuelto consumos para el rango seleccionado.")
    if not obligatorias.issubset(curva.columns):
        raise RuntimeError("La respuesta Datadis no contiene fecha, hora y consumo activo.")

    fechas = pd.to_datetime(curva["date"], errors="coerce")
    mascara = fechas.dt.date.between(inicio.date(), fin.date())
    salida = curva.loc[mascara, ["date", "time", "consumptionKWh"]].rename(
        columns={
            "date": "Fecha",
            "time": "Hora",
            "consumptionKWh": "Consumo (kWh)",
        }
    )
    salida["Consumo (kWh)"] = pd.to_numeric(
        salida["Consumo (kWh)"].astype(str).str.replace(",", ".", regex=False),
        errors="coerce",
    )
    salida = salida.dropna(subset=["Fecha", "Hora", "Consumo (kWh)"])
    if salida.empty:
        raise ValueError("Datadis no ha devuelto consumos utilizables en las fechas elegidas.")
    return salida.reset_index(drop=True), frecuencia, aviso_fallback


def rango_meses_datadis(fecha_inicio, fecha_fin):
    """Amplía un ciclo de consumo a los meses completos exigidos por Datadis."""
    inicio = pd.to_datetime(fecha_inicio, errors="coerce", dayfirst=True)
    fin = pd.to_datetime(fecha_fin, errors="coerce", dayfirst=True)
    if pd.isna(inicio) or pd.isna(fin) or inicio.normalize() > fin.normalize():
        raise ValueError("El periodo de facturación no es válido.")
    inicio_mes = inicio.to_period("M").start_time
    fin_mes = fin.to_period("M").end_time.normalize()
    return inicio_mes, fin_mes


def _descargar_componente_v2_datadis(
    cliente,
    token,
    endpoint,
    suministro,
    fecha_inicio,
    fecha_fin,
    authorized_nif=None,
    timeout=120,
):
    """Descarga un componente V2 conservando los errores de distribuidora."""
    params = {
        "cups": str(suministro["cups"]).strip().upper(),
        "distributorCode": str(suministro["distributorCode"]).strip(),
        "startDate": pd.Timestamp(fecha_inicio).strftime("%Y/%m"),
        "endDate": pd.Timestamp(fecha_fin).strftime("%Y/%m"),
    }
    authorized_nif = str(authorized_nif or "").strip().upper()
    if authorized_nif:
        params["authorizedNif"] = authorized_nif
    respuesta = cliente.get(
        f"{DATADIS_API_BASE}/api-private/api/{endpoint}",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    datos = _datadis_json(respuesta, f"la descarga de {endpoint}")
    if not isinstance(datos, dict):
        raise RuntimeError(f"Datadis ha devuelto una respuesta {endpoint} no válida.")
    return datos


def _normalizar_maximetros_datadis(datos, fecha_inicio, fecha_fin):
    """Normaliza los máximos mensuales V2 por periodo tarifario."""
    registros = datos.get("maxPower") or []
    if not isinstance(registros, list):
        raise RuntimeError("La respuesta Datadis no contiene maxPower válido.")
    columnas = ["period", "maxPower", "date", "time"]
    if not registros:
        return pd.DataFrame(columns=columnas), False
    df = pd.DataFrame(registros)
    obligatorias = {"maxPower", "period"}
    if not obligatorias.issubset(df.columns):
        raise RuntimeError("La respuesta de maxímetros no contiene sus campos básicos.")
    for columna in ("date", "time"):
        if columna not in df:
            df[columna] = None
    df["maxPower"] = pd.to_numeric(df["maxPower"], errors="coerce")
    df["period"] = (
        df["period"].astype(str).str.extract(r"(\d+)", expand=False).map(
            lambda valor: f"P{valor}" if pd.notna(valor) else None
        )
    )
    inicio = pd.to_datetime(fecha_inicio, dayfirst=True).normalize()
    fin = pd.to_datetime(fecha_fin, dayfirst=True).normalize()
    primer_dia = inicio + pd.Timedelta(days=1) if inicio < fin else inicio
    ciclo_mes_completo = (
        primer_dia.is_month_start
        and fin.is_month_end
        and primer_dia.to_period("M") == fin.to_period("M")
    )
    return (
        df[columnas].sort_values("period").reset_index(drop=True),
        bool(ciclo_mes_completo),
    )


def _normalizar_reactiva_datadis(datos, fecha_inicio, fecha_fin):
    """Normaliza la reactiva mensual V2 e indica si cubre exactamente el ciclo."""
    bloque = datos.get("reactiveEnergy") or {}
    registros = bloque.get("energy") or [] if isinstance(bloque, dict) else []
    if not isinstance(registros, list):
        raise RuntimeError("La respuesta Datadis no contiene energía reactiva válida.")
    df = pd.DataFrame(registros)
    if df.empty:
        return df, False
    renombrar = {}
    for columna in df.columns:
        coincidencia = re.fullmatch(r"energy[_-]?[pP](\d)", str(columna))
        if coincidencia:
            renombrar[columna] = f"P{coincidencia.group(1)}"
    df = df.rename(columns=renombrar)
    columna_fecha = next(
        (col for col in ("date", "month", "period") if col in df.columns), None
    )
    if columna_fecha is None:
        raise RuntimeError("La reactiva Datadis no contiene el mes de medida.")
    meses = pd.to_datetime(
        df[columna_fecha].astype(str).str.replace("-", "/", regex=False),
        format="%Y/%m",
        errors="coerce",
    ).dt.to_period("M")
    inicio = pd.to_datetime(fecha_inicio, dayfirst=True).normalize()
    fin = pd.to_datetime(fecha_fin, dayfirst=True).normalize()
    primer_dia = inicio + pd.Timedelta(days=1) if inicio < fin else inicio
    meses_completos = pd.period_range(
        primer_dia.to_period("M"), fin.to_period("M"), freq="M"
    )
    ciclo_meses_completos = (
        primer_dia.is_month_start
        and fin.is_month_end
        and all(
            periodo.start_time.normalize() >= primer_dia
            and periodo.end_time.normalize() <= fin
            for periodo in meses_completos
        )
    )
    df = df.loc[meses.isin(meses_completos)].copy()
    for periodo in [f"P{i}" for i in range(1, 7)]:
        if periodo in df:
            df[periodo] = pd.to_numeric(df[periodo], errors="coerce")
    return df.reset_index(drop=True), bool(ciclo_meses_completos)


def obtener_complementos_verificacion_datadis(
    usuario,
    password,
    suministro,
    fecha_inicio,
    fecha_fin,
    authorized_nif=None,
    timeout=120,
    session=None,
):
    """Obtiene reactiva y maxímetros V2 sin bloquear un componente por el otro."""
    cliente = session or requests.Session()
    cerrar = session is None
    resultado = {
        "reactiva": pd.DataFrame(),
        "reactiva_ciclo_exacto": False,
        "maximetros": pd.DataFrame(),
        "maximetros_ciclo_exacto": False,
        "errores": {},
        "avisos_distribuidora": {},
    }
    try:
        token = autenticar_datadis(usuario, password, timeout=timeout, session=cliente)
        inicio_mes, fin_mes = rango_meses_datadis(fecha_inicio, fecha_fin)
        for nombre, endpoint in (
            ("reactiva", "get-reactive-data-v2"),
            ("maximetros", "get-max-power-v2"),
        ):
            try:
                datos = _descargar_componente_v2_datadis(
                    cliente,
                    token,
                    endpoint,
                    suministro,
                    inicio_mes,
                    fin_mes,
                    authorized_nif=authorized_nif,
                    timeout=timeout,
                )
                avisos = datos.get("distributorError") or []
                if avisos:
                    resultado["avisos_distribuidora"][nombre] = avisos
                if nombre == "reactiva":
                    reactiva, exacto = _normalizar_reactiva_datadis(
                        datos, fecha_inicio, fecha_fin
                    )
                    resultado["reactiva"] = reactiva
                    resultado["reactiva_ciclo_exacto"] = exacto
                else:
                    maximetros, exacto = _normalizar_maximetros_datadis(
                        datos, fecha_inicio, fecha_fin
                    )
                    resultado["maximetros"] = maximetros
                    resultado["maximetros_ciclo_exacto"] = exacto
            except Exception as exc:
                resultado["errores"][nombre] = str(exc)
    finally:
        if cerrar:
            cliente.close()
    return resultado


def clave_cache_consumo_datadis(
    usuario,
    authorized_nif,
    suministro,
    fecha_inicio,
    fecha_fin,
    preferir_qh=False,
):
    """Crea una clave estable sin incluir la contraseña de Datadis."""
    inicio_mes, fin_mes = rango_meses_datadis(fecha_inicio, fecha_fin)
    return (
        str(usuario or "").strip().upper(),
        str(authorized_nif or "").strip().upper(),
        str(suministro.get("cups", "")).strip().upper(),
        str(suministro.get("distributorCode", "")).strip(),
        inicio_mes.strftime("%Y/%m"),
        fin_mes.strftime("%Y/%m"),
        bool(preferir_qh),
    )


def obtener_consumo_datadis_cacheado(
    cache,
    usuario,
    password,
    suministro,
    fecha_inicio,
    fecha_fin,
    authorized_nif=None,
    preferir_qh=False,
    **kwargs,
):
    """Descarga meses completos una sola vez y reutiliza copias desde ``cache``."""
    inicio_mes, fin_mes = rango_meses_datadis(fecha_inicio, fecha_fin)
    clave = clave_cache_consumo_datadis(
        usuario,
        authorized_nif,
        suministro,
        inicio_mes,
        fin_mes,
        preferir_qh,
    )
    resultado = cache.get(clave)
    reutilizado = resultado is not None
    if resultado is None:
        resultado = obtener_consumo_datadis(
            usuario,
            password,
            suministro,
            inicio_mes,
            fin_mes,
            authorized_nif=authorized_nif,
            preferir_qh=preferir_qh,
            **kwargs,
        )
        curva, frecuencia, aviso_fallback = resultado
        cache[clave] = (curva.copy(), frecuencia, aviso_fallback)
    curva, frecuencia, aviso_fallback = cache[clave]
    return curva.copy(), frecuencia, aviso_fallback, clave, reutilizado


def dataframe_como_archivo_curva(df, nombre="curva.csv"):
    """Convierte una curva en un archivo CSV en memoria aceptado por el normalizador."""
    archivo = io.BytesIO(df.to_csv(index=False, sep=";").encode("utf-8"))
    archivo.name = nombre
    return archivo


def completar_periodos_curva(df_norm, df_periodos, atr):
    """Asigna o normaliza periodos tarifarios sin depender de la interfaz."""
    salida = df_norm.copy()
    if "periodo" not in salida.columns or salida["periodo"].isna().all():
        tipo_periodo = "dh_3p" if str(atr).startswith("2.0") else "dh_6p"
        salida = salida.drop(columns=["periodo"], errors="ignore")
        salida = pd.merge(
            salida,
            df_periodos[["fecha_hora", tipo_periodo]].rename(
                columns={tipo_periodo: "periodo"}
            ),
            on="fecha_hora",
            how="left",
        )
    salida["periodo"] = (
        salida["periodo"]
        .astype("string")
        .str.strip()
        .replace("nan", pd.NA)
        .ffill()
    )
    return salida


def agrupar_curva_horaria(df_norm, frecuencia):
    """Devuelve una copia horaria común para curvas H, QH o diezminutales."""
    columnas_agregadas = {
        "fecha": "first",
        "hora": "first",
        "consumo_neto_kWh": "sum",
        "reactiva_kVArh": "sum",
        "vertido_neto_kWh": "sum",
        "generacion_kWh": "sum",
        "periodo": "first",
        "tipo_dia": "first",
    }
    if frecuencia in {"QH", "10MIN"}:
        salida = (
            df_norm.groupby(["fecha", "hora"], as_index=False)
            .agg({clave: valor for clave, valor in columnas_agregadas.items()
                  if clave not in {"fecha", "hora"}})
        )
        salida["fecha_hora"] = (
            pd.to_datetime(salida["fecha"])
            + pd.to_timedelta(salida["hora"], unit="h")
        )
    else:
        salida = df_norm[["fecha_hora", *columnas_agregadas]].copy()
    return (
        salida.groupby("fecha_hora", as_index=False)
        .agg(columnas_agregadas)
        .sort_values("fecha_hora")
        .reset_index(drop=True)
    )


def recortar_curva_periodo(
    df_norm, fecha_inicio, fecha_fin, inicio_exclusivo=False
):
    """Recorta una curva normalizada incluyendo todos los intervalos del último día."""
    inicio = pd.to_datetime(fecha_inicio, errors="coerce", dayfirst=True)
    fin = pd.to_datetime(fecha_fin, errors="coerce", dayfirst=True)
    if pd.isna(inicio) or pd.isna(fin) or inicio.normalize() > fin.normalize():
        raise ValueError("El periodo de facturación no es válido.")
    fechas = pd.to_datetime(df_norm.get("fecha_hora"), errors="coerce")
    limite_inicio = inicio.normalize()
    if inicio_exclusivo and inicio.normalize() < fin.normalize():
        limite_inicio += pd.Timedelta(days=1)
    limite_fin = fin.normalize() + pd.Timedelta(days=1)
    salida = df_norm.loc[
        (fechas >= limite_inicio) & (fechas < limite_fin)
    ].copy()
    if salida.empty:
        raise ValueError("La curva no contiene datos del periodo de facturación.")
    return salida.reset_index(drop=True)


def analizar_cobertura_periodo(
    df_norm, fecha_inicio, fecha_fin, frecuencia, inicio_exclusivo=False
):
    """Comprueba cobertura, huecos y duplicados dentro de un ciclo facturado."""
    recortada = recortar_curva_periodo(
        df_norm, fecha_inicio, fecha_fin, inicio_exclusivo=inicio_exclusivo
    )
    paso = {"H": "1h", "QH": "15min", "10MIN": "10min"}.get(frecuencia)
    if paso is None:
        raise ValueError("No se puede validar una frecuencia desconocida.")
    inicio = pd.to_datetime(fecha_inicio, dayfirst=True).normalize()
    fin = pd.to_datetime(fecha_fin, dayfirst=True).normalize()
    if inicio_exclusivo and inicio < fin:
        inicio += pd.Timedelta(days=1)
    limite_fin = (
        fin + pd.Timedelta(days=1)
    )
    esperadas = pd.date_range(inicio, limite_fin, freq=paso, inclusive="left")
    fechas = pd.to_datetime(recortada["fecha_hora"], errors="coerce").dropna()
    unicas = pd.DatetimeIndex(fechas.drop_duplicates().sort_values())
    ausentes = esperadas.difference(unicas)
    fuera_secuencia = unicas.difference(esperadas)
    duplicados = int(fechas.duplicated(keep=False).sum())
    return {
        "completa": not len(ausentes) and not len(fuera_secuencia) and not duplicados,
        "intervalos_esperados": int(len(esperadas)),
        "intervalos_unicos": int(len(unicas)),
        "intervalos_ausentes": int(len(ausentes)),
        "intervalos_fuera_secuencia": int(len(fuera_secuencia)),
        "registros_duplicados": duplicados,
        "primer_intervalo": unicas.min() if len(unicas) else None,
        "ultimo_intervalo": unicas.max() if len(unicas) else None,
    }


def dividir_energias_curva(df_curva, divisor=1000.0):
    """Reescala solo las magnitudes energéticas de una curva normalizada."""
    if divisor is None or float(divisor) <= 0:
        raise ValueError("El divisor de la curva debe ser mayor que cero.")
    salida = df_curva.copy()
    columnas_energia = (
        "consumo_kWh",
        "excedentes_kWh",
        "generacion_kWh",
        "reactiva_kVArh",
        "capacitiva_kVArh",
        "consumo_neto_kWh",
        "vertido_neto_kWh",
    )
    for columna in columnas_energia:
        if columna in salida.columns:
            salida[columna] = pd.to_numeric(
                salida[columna], errors="coerce"
            ) / float(divisor)
    return salida


def resumir_consumo_por_periodo(df_norm):
    """Suma el consumo neto de una curva ya periodificada."""
    if "periodo" not in df_norm or "consumo_neto_kWh" not in df_norm:
        raise ValueError("La curva no contiene periodos o consumo neto.")
    resumen = (
        df_norm.groupby("periodo", observed=True)["consumo_neto_kWh"]
        .sum()
        .sort_index()
    )
    return {str(periodo): float(consumo) for periodo, consumo in resumen.items()}

def _clean(s: str) -> str:
    s = unidecode(str(s)).lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s

   
def detectar_hojas_curva_excel(uploaded_or_path):
    """
    Devuelve únicamente las hojas de curva admitidas que contienen datos.

    Por ahora se limita deliberadamente a las designaciones exactas
    ``Horarias`` y ``Cuarto horarias``.
    """
    posicion = None
    if hasattr(uploaded_or_path, "tell"):
        try:
            posicion = uploaded_or_path.tell()
        except Exception:
            posicion = None

    try:
        xls = pd.ExcelFile(uploaded_or_path)
        hojas = []
        for nombre in ("Horarias", "Cuarto horarias"):
            if nombre not in xls.sheet_names:
                continue
            muestra = pd.read_excel(
                uploaded_or_path,
                sheet_name=nombre,
                dtype=str,
                header=None,
                nrows=25,
            )
            muestra = muestra.dropna(how="all").dropna(axis=1, how="all")
            # Exigimos cabecera y al menos una fila de valores.
            if len(muestra) >= 4 and muestra.shape[1] >= 2:
                hojas.append(nombre)
        return hojas
    finally:
        if posicion is not None and hasattr(uploaded_or_path, "seek"):
            uploaded_or_path.seek(posicion)


def _read_any(uploaded_or_path, preferred_sheet=None):
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

            header_keywords = [
                "fecha", "hora", "consumo", "energ", "cups",
                "periodo", "react", "generacion",
            ]
            keyword_hits = sum(k in row_values for k in header_keywords)

            # Debe contener al menos una palabra clave
            if keyword_hits == 0:
                continue

            # Debe tener pocas celdas vacías y poca presencia de números
            non_empty = [x for x in row if x.strip() not in ["", "nan", "none"]]
            text_like = sum(1 for x in non_empty if not any(ch.isdigit() for ch in x))
            ratio_text = text_like / max(len(non_empty), 1)

            # Si más del 70% parecen texto (no números), se asume cabecera real
            # Algunas distribuidoras incluyen Q1-Q4 y RESERVA 1-2 en los
            # encabezados. Esos dígitos reducen ratio_text aunque la fila sea
            # inequívocamente una cabecera.
            if len(non_empty) >= 2 and (ratio_text > 0.7 or keyword_hits >= 2):
                return i

        return None

    def read_csv_bytes(content):
        """Lee CSV habituales sin asumir que todos están codificados en UTF-8."""
        texto = None
        errores = []
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                texto = content.decode(encoding)
                break
            except UnicodeDecodeError as exc:
                errores.append(f"{encoding}: {exc}")
        if texto is None:
            raise UnicodeError(
                "No se pudo identificar la codificación del CSV. "
                + " | ".join(errores)
            )
        muestra = texto[:4096]
        separador = ";" if muestra.count(";") > muestra.count(",") else ","
        return pd.read_csv(
            io.StringIO(texto),
            sep=separador,
            dtype=str,
            header=None,
            skip_blank_lines=True,
        )

    # --- Leer según tipo ---
    if isinstance(uploaded_or_path, str):
        path = uploaded_or_path.lower()
        if path.endswith(".csv"):
            content = Path(uploaded_or_path).read_bytes()
            df = read_csv_bytes(content)
        else:
            df = pd.read_excel(
                uploaded_or_path,
                sheet_name=preferred_sheet if preferred_sheet is not None else 0,
                dtype=str,
                header=None,
            )
    else:
        name = uploaded_or_path.name.lower()
        if name.endswith(".csv"):
            content = uploaded_or_path.read()
            df = read_csv_bytes(content)
        else:
            
            xls = pd.ExcelFile(uploaded_or_path)

            mejor_df = None
            mejor_hoja = None
            mejor_score = 0
            hoja_horarias = None
            hoja_cuarto_horarias = None
            hoja_preferida = None

            MIN_FILAS = 20
            MIN_COLUMNAS = 2
            hojas_a_revisar = (
                [preferred_sheet]
                if preferred_sheet in xls.sheet_names
                else xls.sheet_names
            )
            for sheet in hojas_a_revisar:
                #df = pd.read_excel(uploaded_or_path, sheet_name=sheet, dtype=str, header=None)
                #if not df.empty:
                #    print(f"Usando hoja: {sheet}")
                #    break
                #print(df)
                df_tmp = pd.read_excel(
                    xls,
                    sheet_name=sheet,
                    dtype=str,
                    header=None
                )

                if df_tmp.empty:
                    continue

                df_tmp_limpio = df_tmp.dropna(how="all").dropna(axis=1, how="all")

                filas, columnas = df_tmp_limpio.shape
                score = filas * columnas

                if filas < MIN_FILAS or columnas < MIN_COLUMNAS:
                    continue

                if _clean(sheet) == "horarias":
                    hoja_horarias = (df_tmp_limpio, sheet, score)
                elif _clean(sheet) == "cuarto horarias":
                    hoja_cuarto_horarias = (df_tmp_limpio, sheet, score)
                if preferred_sheet is not None and sheet == preferred_sheet:
                    hoja_preferida = (df_tmp_limpio, sheet, score)

                if score > mejor_score:
                    mejor_score = score
                    mejor_df = df_tmp_limpio
                    mejor_hoja = sheet

            # Prioridad explícita para estos libros:
            # "Cuarto horarias" con datos > "Horarias" con datos > hoja mayor.
            if hoja_preferida is not None:
                mejor_df, mejor_hoja, mejor_score = hoja_preferida
            elif hoja_cuarto_horarias is not None:
                mejor_df, mejor_hoja, mejor_score = hoja_cuarto_horarias
            elif hoja_horarias is not None:
                mejor_df, mejor_hoja, mejor_score = hoja_horarias

            if mejor_df is None:
                raise ValueError(
                    f"No se ha encontrado ninguna hoja válida. Hojas disponibles: {xls.sheet_names}"
                )

            df = mejor_df

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
            # Priorizar columnas inequívocas de energía activa/consumo frente
            # a metadatos genéricos como "TIPO MEDIDA".
            for c in matches:
                cc = cleaned[c]
                es_consumo = re.search(
                    r"\bconsumo\b|\bactive.?energy\b|\benergia\s+activa\b|\bkwh\b",
                    cc,
                    re.IGNORECASE,
                )
                es_auxiliar = re.search(
                    r"\bcal\.?\b|\bgeneraci[oó]n\b|\breact",
                    cc,
                    re.IGNORECASE,
                )
                if es_consumo and not es_auxiliar:
                    return c

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
    # Priorizar nombres inequívocos. El buscador genérico recorre columnas y
    # podría escoger "dia_semana" antes que una columna posterior "fecha".
    c_date = next(
        (
            columna for columna, nombre_limpio in cleaned.items()
            if nombre_limpio in {"fecha", "date", "data", "dia", "día"}
        ),
        None,
    )
    if c_date is None:
        c_date = find([
            r"^fecha\b", r"\bfecha$", r"^date\b", r"^data\b",
            r"^dia$", r"^día$",
        ])
    c_time = find([r"hora", r"hour",r"hr", r"time", r"^h$"])
    #c_quarter = find([r"cuarto", r"q$", r"qh", r"15"])
    c_quarter = find([r"^cuarto$", r"q$", r"qh"])
    
    #c_kwh = find([r"consumo", r"energia", r"kwh", r"ae", r"active.?energy", r"importada", r"activa"])
    c_kwh = find(
        [r"consumo", r"AI", r"energia", r"kwh", r"ae", r"active.?energy", r"importada", r"activa", r"medida"],
        prefer_qh_consumo=True
    )
    c_per = find([r"periodo", r"^p$", r"^p[1-6]$"])
    c_ind = find([
        r"^r1$",
        r"reactiva",
        r"reactive",
        r"\breact\b",
        r"react.?q1\b",
        r"kvarh",
        r"inductiva",
    ])
    c_cap = find(["capac"])
    #c_ver = find([r"gener", r"vertid", r"exportad", r"as", r"prod"])
    #c_ver = find([r"generaci[oó]n", r"vertid", r"exportad", r"as", r"prod"])
    c_ver = find([r"vertid", r"exporta"])
    c_gen = find(["generac"])

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

def normalize_curve_simple(
    uploaded,
    origin="archivo",
    excel_sheet=None,
    zona_periodos="peninsula",
) -> tuple[pd.DataFrame, pd.DataFrame, str]:

    #Lee y normaliza la curva, devolviendo (df_in, df_norm).
    #   Regla simple:
    #     - Si el primer registro válido está a las 01:00 → restar 1h a toda la serie.
    #     - Si está a las 00:00 → no tocar.
    #   Detección automática de formato de fecha (día primero o año primero)."""
    
    df, header_row = _read_any(uploaded, preferred_sheet=excel_sheet)
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

    nombre_consumo = _clean(c_kwh)
    unidad_kwh_explicita = "kwh" in nombre_consumo
    unidad_wh_explicita = bool(re.search(r"\bwh\b", nombre_consumo)) and not unidad_kwh_explicita

    # La posición de la cabecera puede sugerir ciertos formatos históricos,
    # pero una unidad "kWh" escrita en la propia columna siempre prevalece.
    if unidad_wh_explicita or (header_row > 1 and not unidad_kwh_explicita):
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
                
            else:
                # SOLO FECHA → tratar como fecha + hora separadas
                raise ValueError("NO_DATETIME")

        else:
            # No hay columna datetime → pasar a fecha + hora separadas
            raise ValueError("NO_DATETIME")


    except ValueError as e:
        if str(e) == "NO_DATETIME":
            # --- Caso cuartohorario explícito: HORA + CUARTO EN COLUMNAS SEPARADAS. CASO TIPO ENDESA QH---
            if c_time and c_quarter:
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

                endesa_qh = True

            else:
                # --- Fecha y hora en columnas separadas. CASO HABITUAL ---
                d = _parse_date_ddmmyyyy(df[c_date])
                hora_raw = df[c_time].astype(str).str.strip()

                # --- Corregir valores 24:00 ---
                mask_24 = hora_raw.isin(["24:00", "24:00:00"])
                if mask_24.any():
                    hora_raw.loc[mask_24] = "00:00"
                    d.loc[mask_24] = d.loc[mask_24] + pd.Timedelta(days=1)

                # Detectar casos con formato HH:MM o HH:MM:SS
                if hora_raw.str.contains(":").any():
                    #print(d.head(24))

                    minutos = hora_raw.str.extract(r":(\d{2})")[0].astype(float)

                    if minutos.max() == 0:
                        # Horario tipo “01:00”
                        #dt0 = d + pd.to_timedelta(hora_raw +":00", errors="coerce")
                        #dt0 = d + pd.to_timedelta(hora_raw, errors="coerce")
                        hora_norm = hora_raw.copy()

                        # HH:MM → añadir segundos
                        mask_horario = hora_norm.str.count(":") == 1
                        hora_norm.loc[mask_horario] = hora_norm.loc[mask_horario] + ":00"

                        dt0 = d + pd.to_timedelta(hora_norm, errors="coerce")
                        # Ajuste por casos 01:00→00:00 del día siguiente
                        if dt0.dt.hour.min() == 1:
                            dt0 = dt0 - pd.Timedelta(hours=1)
                    else:
                        # Cuartohoraria (00:15, 00:30…)
                        hora_norm = hora_raw.copy()

                        # HH:MM → añadir segundos
                        mask_horario = hora_norm.str.count(":") == 1
                        hora_norm.loc[mask_horario] = hora_norm.loc[mask_horario] + ":00"
                        #h = pd.to_timedelta(hora_raw, errors="coerce")
                        h = pd.to_timedelta(hora_norm, errors="coerce")
                        #print(repr(hora_raw.iloc[0]))
                        #print(type(hora_raw))
                        #print(hora_raw.dtype)
                        #print(type(hora_raw.iloc[0]))
                        #print(pd)
                        #print(pd.to_timedelta("0:15"))                # debería funcionar
                        #print(pd.to_timedelta(["0:15", "1:30"]))     # prueba lista
                        dt0 = d + h


                else:
                    # Horas numéricas (1–24)
                    h = _parse_time_to_hour(df[c_time]).fillna(0)
                    dt0 = d + pd.to_timedelta(h, unit="h")

                    #print("DEBUG --- dt0 primeras filas:")
                    #print(dt0.head(96))
                    #print("DEBUG --- diferencias en minutos:")
                    #print(dt0.diff().dt.total_seconds().head(10))
    
    except Exception as e:
        raise

    if not dt0.notna().any():
        columna_fecha = c_dt or c_date
        muestras_fecha = (
            df[columna_fecha].dropna().astype(str).head(5).tolist()
            if columna_fecha is not None else []
        )
        muestras_hora = (
            df[c_time].dropna().astype(str).head(5).tolist()
            if c_time is not None else []
        )
        raise ValueError(
            "Se detectaron las columnas de fecha/hora, pero ninguna fila pudo "
            "convertirse a una fecha válida. "
            f"Columna fecha: {columna_fecha!r}; muestras: {muestras_fecha}. "
            f"Columna hora: {c_time!r}; muestras: {muestras_hora}."
        )

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
    if freq in PANDAS_FREQ:
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
            #periodos_path = "utils/periodos_horarios.xlsx"
            mapa_periodos_path = {
                "peninsula": BASE_DIR / "utils" / "periodos_horarios.xlsx",
                "canarias": BASE_DIR / "utils" / "periodos_horarios_canarias.xlsx",
                "baleares": BASE_DIR / "utils" / "periodos_horarios_baleares.xlsx",
                "ceuta": BASE_DIR / "utils" / "periodos_horarios_ceuta.xlsx",
                "melilla": BASE_DIR / "utils" / "periodos_horarios_melilla.xlsx",
            }
            periodos_path = mapa_periodos_path.get(
                str(zona_periodos or "peninsula").lower(),
                BASE_DIR / "utils" / "periodos_horarios.xlsx"
            )
            periodos_path = Path(periodos_path)
            df_periodos = cargar_calendario_periodos(
                str(periodos_path),
                periodos_path.stat().st_mtime_ns,
            )


            periodo = np.nan

            #print(df_periodos)
                        
            #periodo = df_merge["periodo"].astype(str).str.upper().str.strip()

            #msg_periodos = 'Cargados periodos desde fichero auxiliar. Seleccione modo 3P/6P'
        except Exception:
            periodo = np.nan
    
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
    """Compatibilidad histórica con el formato mensual de Curva de carga."""
    from formato_es import formatear_tabla_consumos

    df_vista = (
        df_tabla.rename(columns={col_mes: "Mes"})
        if col_mes != "Mes"
        else df_tabla
    )
    return formatear_tabla_consumos(df_vista, columna_mes="Mes")

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

    df["fecha_hora"] = pd.to_datetime(df["fecha_hora"])

    # Filtrar según opción
    if tipo_dia == "L-V":
        df_sel = df[df["tipo_dia"] == "L-V"].copy()
        add_title = "LUNES A VIERNES"

    elif tipo_dia == "FS":
        df_sel = df[df["tipo_dia"] == "FS"].copy()
        add_title = "FIN DE SEMANA"

    else:
        df_sel = df.copy()
        add_title = "TOTAL"

    # =====================================================
    # Si df_norm_h ya es horario, NO resampleamos
    # =====================================================
    df_sel["hora"] = df_sel["fecha_hora"].dt.hour

    df_horas = (
        df_sel.groupby("hora", as_index=False)["consumo_neto_kWh"]
        .mean()
        .rename(columns={"consumo_neto_kWh": "media_kWh"})
    )

    # Nos aseguramos de que estén las 24 horas
    df_horas = (
        df_horas.set_index("hora")
        .reindex(range(24))
        .reset_index()
    )

    # =====================================================
    # ORDENACIÓN OPCIONAL
    # =====================================================
    if ordenar:
        df_horas = df_horas.sort_values("media_kWh", ascending=False)
        df_horas["hora_cat"] = df_horas["hora"].astype(str)
        x_col = "hora_cat"
        title = "Hora del día (ordenada por consumo)"
    else:
        x_col = "hora"
        title = f"Perfil medio horario: <span style='color:orange'>{add_title}</span>"

    # =====================================================
    # Gráfico
    # =====================================================
    fig = px.bar(
        df_horas,
        x=x_col,
        y="media_kWh",
        labels={
            "hora": "Hora del día",
            "hora_cat": "Hora del día",
            "media_kWh": "Consumo medio (kWh)"
        },
        color="media_kWh",
        color_continuous_scale="Blues"
    )

    if ymax is None:
        ymax = df_horas["media_kWh"].max() * 1.05

    fig.update_layout(
        title=dict(
            text=title,
            x=0.5,
            xanchor="center"
        ),
        yaxis_title="kWh medios",
        coloraxis_showscale=False,
        yaxis=dict(
            range=[0, ymax]
        ),
        separators=",."
    )

    if ordenar:
        fig.update_xaxes(
            type="category",
            categoryorder="array",
            categoryarray=df_horas["hora_cat"].tolist()
        )
    else:
        fig.update_xaxes(
            dtick=1,
            tickmode="linear",
            tick0=0
        )

    fig.update_traces(
        hovertemplate=(
            "<b>Hora:</b> %{x}:00<br>"
            "<b>Consumo medio:</b> %{y:.2f} kWh"
            "<extra></extra>"
        )
    )

    fig = aplicar_estilo(fig)

    return fig

def graficar_media_horaria_old(tipo_dia, ymax=None, ordenar=False):
    
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

    # Aseguramos fecha_hora como datetime
    df["fecha_hora"] = pd.to_datetime(df["fecha_hora"])

    # Si df_norm_h ya está corregido a horario, solo sacamos la hora
    df["hora"] = df["fecha_hora"].dt.hour

    # =====================================================
    # Perfil medio L-V / FS
    # =====================================================
    df_tipo = (
        df.groupby(["tipo_dia", "hora"], as_index=False)["consumo_neto_kWh"]
        .mean()
        .rename(columns={"consumo_neto_kWh": "media_kWh"})
    )

    df_tipo = df_tipo.rename(columns={"tipo_dia": "perfil"})

    # =====================================================
    # Perfil TOTAL
    # =====================================================
    df_total = (
        df.groupby("hora", as_index=False)["consumo_neto_kWh"]
        .mean()
        .rename(columns={"consumo_neto_kWh": "media_kWh"})
    )

    df_total["perfil"] = "TOTAL"

    # =====================================================
    # Unimos
    # =====================================================
    df_plot = pd.concat([df_tipo, df_total], ignore_index=True)

    # Orden de perfiles
    orden_perfiles = ["L-V", "FS", "TOTAL"]

    df_plot["perfil"] = pd.Categorical(
        df_plot["perfil"],
        categories=orden_perfiles,
        ordered=True
    )

    df_plot = df_plot.sort_values(["perfil", "hora"])

    ymax = df_plot["media_kWh"].max() * 1.05
    ymin = 0

    # =====================================================
    # Gráfico
    # =====================================================
    fig = px.line(
        df_plot,
        x="hora",
        y="media_kWh",
        color="perfil",
        category_orders={"perfil": orden_perfiles},
        labels={
            "hora": "Hora del día",
            "media_kWh": "Consumo medio (kWh)",
            "perfil": "Tipo de día"
        },
        title="Perfil medio horario: L-V vs Fin de Semana",
        color_discrete_map={
            "L-V": "#6a0dad",
            "FS": "#2e8b57",
            "TOTAL": "#999999"
        }
    )

    fig.update_traces(line=dict(width=3))

    # Si quieres que TOTAL salga oculto por defecto:
    fig.for_each_trace(
        lambda t: t.update(
            visible="legendonly" if t.name == "TOTAL" else True
        )
    )

    fig.update_layout(
        xaxis=dict(
            dtick=1,
            title="Hora del día"
        ),
        yaxis=dict(
            title="kWh medios",
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

def graficar_media_horaria_combinada_old():
    
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

def calcular_tabla_excesos_reactiva(tabla_consumos, tabla_reactiva, porcentaje_limite=None):

    from regulacion_reactiva import LIMITE_REACTIVA_SOBRE_ACTIVA

    if porcentaje_limite is None:
        porcentaje_limite = LIMITE_REACTIVA_SOBRE_ACTIVA

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
    from regulacion_reactiva import COS_PHI_SIN_PENALIZACION

    if pd.isna(val):
        return ""

    try:
        val = float(val)
    except:
        return ""

    if val < COS_PHI_SIN_PENALIZACION:
        return "background-color: #EA9999; color: #000000;"  # rosa Excel
    else:
        return "background-color: #B6D7A8; color: #000000;"  # verde Excel
    
def calcular_tabla_precio_penalizacion_reactiva(tabla_fp):

    from regulacion_reactiva import (
        COS_PHI_PENALIZACION_ALTA,
        COS_PHI_SIN_PENALIZACION,
        PRECIO_REACTIVA_ALTA_EUR_KVARH,
        PRECIO_REACTIVA_MEDIA_EUR_KVARH,
    )

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
                    fp >= COS_PHI_SIN_PENALIZACION,
                    (fp >= COS_PHI_PENALIZACION_ALTA) & (fp < COS_PHI_SIN_PENALIZACION),
                    fp < COS_PHI_PENALIZACION_ALTA
                ],
                [
                    0,
                    PRECIO_REACTIVA_MEDIA_EUR_KVARH,
                    PRECIO_REACTIVA_ALTA_EUR_KVARH
                ],
                default=np.nan
            )
        else:
            tabla_precio[p] = np.nan

    tabla_precio["Total"] = np.nan

    return tabla_precio
    
def calcular_tabla_coste_excesos_reactiva(tabla_excesos_reactiva, tabla_fp):

    from regulacion_reactiva import (
        COS_PHI_PENALIZACION_ALTA,
        COS_PHI_SIN_PENALIZACION,
        PRECIO_REACTIVA_ALTA_EUR_KVARH,
        PRECIO_REACTIVA_MEDIA_EUR_KVARH,
    )

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
                    fp >= COS_PHI_SIN_PENALIZACION,
                    (fp >= COS_PHI_PENALIZACION_ALTA) & (fp < COS_PHI_SIN_PENALIZACION),
                    fp < COS_PHI_PENALIZACION_ALTA
                ],
                [
                    0,
                    PRECIO_REACTIVA_MEDIA_EUR_KVARH,
                    PRECIO_REACTIVA_ALTA_EUR_KVARH
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
    return calcular_tabla_coste_excesos_reactiva(
        tabla_excesos_reactiva, tabla_fp
    )

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
    
    multiplicador = {
        "QH": 4,
        "10MIN": 6,
    }.get(st.session_state.frec, 1)

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
            potencia_qh_kw=lambda d: d[columna_valor] * multiplicador
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

    # Situación actual: factor de potencia mínimo recibido desde la interfaz y
    # su Q interpolada sobre la propia curva de dimensionamiento.
    fp_actual_aprox = fp_ini
    curva_ordenada = (
        df_curva_q[["fp_obj", "q_max"]]
        .dropna()
        .sort_values("fp_obj")
    )
    q_actual_aprox = np.interp(
        fp_actual_aprox,
        curva_ordenada["fp_obj"],
        curva_ordenada["q_max"],
    )
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
        y=[q_actual_aprox],
        mode="markers+text",
        name="FP actual mínimo",
        text=[f"FP actual mínimo<br>{fp_actual_aprox:.3f}"],
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
            "FP actual mínimo<br>"
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
        q_low=q_actual_aprox,
        q_high=q_min,
        color="red",
        name="Compensación hasta objetivo mínimo"
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


def _añadir_diferencial_hover_unico(
    fig, x, y, diferencial, diferencial_pct, etiqueta, unidad, decimales=2
):
    """Añade una sola entrada de diferencial a un hover unificado."""
    valores = [formato_numero_es(valor, decimales) for valor in diferencial]
    porcentajes = [formato_numero_es(valor, 2) for valor in diferencial_pct]
    fig.add_trace(go.Scatter(
        x=list(x),
        y=list(y),
        mode="markers",
        name="Diferencial",
        showlegend=False,
        marker=dict(size=12, opacity=0),
        customdata=np.column_stack([valores, porcentajes]),
        hovertemplate=(
            f"Diferencial {etiqueta}: %{{customdata[0]}} {unidad} "
            "(%{customdata[1]} %)<extra></extra>"
        ),
    ))
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


    # =====================================================
    # 4. INICIALIZACIÓN / SANEADO DEL RANGO EN SESSION_STATE
    # =====================================================
    clave_rango = "rango_fechas_comparativa_guardado"
    if clave_rango not in st.session_state:
        # Migra el valor anterior si todavía existe en la sesión.
        st.session_state[clave_rango] = st.session_state.get(
            "rango_fechas_comparativa", rango_valido
        )

    else:
        rango_actual = st.session_state[clave_rango]

        if not isinstance(rango_actual, (list, tuple)) or len(rango_actual) != 2:
            st.session_state[clave_rango] = rango_valido

        else:
            f_ini, f_fin = rango_actual
            f_ini = pd.to_datetime(f_ini).date()
            f_fin = pd.to_datetime(f_fin).date()

            # Recortar a límites válidos
            f_ini = max(f_ini, fecha_ini_global)
            f_fin = min(f_fin, fecha_max_comparable)

            # Si tras recortar queda inválido, reset
            if f_ini > f_fin:
                st.session_state[clave_rango] = rango_valido
            else:
                st.session_state[clave_rango] = (f_ini, f_fin)


    # =====================================================
    # 5. RECUPERAR FECHAS SELECCIONADAS
    # =====================================================
    rango = st.session_state.get(clave_rango)

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
    etiqueta_base = (
        str(inicio.year) if inicio.year == fin.year
        else f"{inicio.year}–{fin.year}"
    )
    etiqueta_comp = (
        str(inicio_1y.year) if inicio_1y.year == fin_1y.year
        else f"{inicio_1y.year}–{fin_1y.year}"
    )

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

    delta_str = formato_numero_es(delta, 0)
    delta_pct_str = formato_numero_es(delta_pct, 2)

    resumen_html = f"""
    <div style="
        padding:1rem .8rem;
        border:1px solid #e0b400;
        border-left:6px solid #e0b400;
        border-radius:.75rem;
        background:#fff3bf;
        color:#5f4b00;
        text-align:center;
        box-shadow:0 2px 8px rgba(224,180,0,.16);
    ">
        <div style="font-size:28px;line-height:1.15;">
            El <b>{texto_tipo}</b> del consumo en el periodo seleccionado ha sido de:
        </div>
        <div style="font-size:36px;font-weight:bold;line-height:1.15;margin-top:.35rem;">
            {delta_str} kWh&nbsp; (&nbsp;{delta_pct_str} %&nbsp;)
        </div>
    </div>
    """

    # =====================================================
    # 16. GRÁFICOS
    # =====================================================
    color_base = "#1f77b4"
    color_comp = "#ff7f0e"

    df_plot = df_pivot[df_pivot["Mes"] != "TOTAL"].rename(columns={
        "Base": etiqueta_base, "+1 año": etiqueta_comp,
    })

    fig_mensual = px.bar(
        df_plot,
        x="Mes",
        y=[etiqueta_base, etiqueta_comp],
        barmode="group",
    )

    fig_mensual.for_each_trace(
        lambda t: t.update(marker_color=color_base)
        if t.name == etiqueta_base
        else t.update(marker_color=color_comp)
    )
    def actualizar_hover_consumo_mensual(traza):
        valores = [formato_numero_es(valor, 0) for valor in traza.y]
        traza.update(
            customdata=valores,
            hovertemplate=f"{traza.name}: %{{customdata}} kWh<extra></extra>",
        )

    fig_mensual.for_each_trace(actualizar_hover_consumo_mensual)
    _añadir_diferencial_hover_unico(
        fig_mensual,
        x=df_plot["Mes"],
        y=df_plot[[etiqueta_base, etiqueta_comp]].max(axis=1),
        diferencial=df_plot["Δ"],
        diferencial_pct=df_plot["Δ %"],
        etiqueta=f"{etiqueta_comp}−{etiqueta_base}",
        unidad="kWh",
        decimales=0,
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
        hovermode="x unified",
        hoverlabel=dict(font_size=16, font_family="Arial"),
        barcornerradius="28%",
        bargap=0.25,
        bargroupgap=0.1
    )

    df_total_plot = df_pivot[df_pivot["Mes"] == "TOTAL"].rename(columns={
        "Base": etiqueta_base, "+1 año": etiqueta_comp,
    })

    fig_total = px.bar(
        df_total_plot,
        x=["TOTAL"],
        y=[etiqueta_base, etiqueta_comp],
        barmode="group",
    )

    fig_total.for_each_trace(
        lambda t: t.update(marker_color=color_base)
        if t.name == etiqueta_base
        else t.update(marker_color=color_comp)
    )
    fig_total.for_each_trace(lambda traza: traza.update(
        customdata=[formato_numero_es(valor, 0) for valor in traza.y],
        hovertemplate=f"{traza.name}: %{{customdata}} kWh<extra></extra>"
    ))
    _añadir_diferencial_hover_unico(
        fig_total,
        x=["TOTAL"],
        y=[max(fila_total["Base"], fila_total["+1 año"])],
        diferencial=[fila_total["Δ"]],
        diferencial_pct=[fila_total["Δ %"]],
        etiqueta=f"{etiqueta_comp}−{etiqueta_base}",
        unidad="kWh",
        decimales=0,
    )

    fig_total.for_each_trace(
        lambda traza: traza.update(
            text=[formato_numero_es(valor, 0) for valor in traza.y],
            texttemplate="<b>%{text}</b>",
            textposition="outside",
            textfont_size=20,
            cliponaxis=False,
        ),
        selector=dict(type="bar"),
    )

    fig_total.update_layout(
        title=dict(
            text="Comparativa TOTAL del periodo (kWh)",
            x=0.5,
            xanchor="center"
        ),
        showlegend=True,
        hovermode="x unified",
        hoverlabel=dict(font_size=16, font_family="Arial"),
        xaxis_title="",
        yaxis_title="kWh",
        barcornerradius="10%",
        bargap=0.42,
        bargroupgap=0.38,
        uniformtext_minsize=18,
        uniformtext_mode="show",
    )

    # =====================================================
    # 17. RETURN FINAL
    # =====================================================
    resultado["ok"] = True
    resultado["mensaje"] = ""
    resultado["df_pivot"] = df_pivot.rename(columns={
        "Base": etiqueta_base, "+1 año": etiqueta_comp,
    })
    resultado["etiquetas_periodos"] = (etiqueta_base, etiqueta_comp)
    resultado["resumen_html"] = resumen_html
    resultado["fig_total"] = fig_total
    resultado["fig_mensual"] = fig_mensual

    return resultado

def preparar_costes_mensuales_rango(df_horario, rango_base):
    """Agrega costes horarios solo para el rango base y su réplica +1 año."""
    if df_horario is None or df_horario.empty or rango_base is None:
        return pd.DataFrame()
    if not isinstance(rango_base, (tuple, list)) or len(rango_base) != 2:
        return pd.DataFrame()

    inicio = pd.to_datetime(rango_base[0]).normalize()
    fin = pd.to_datetime(rango_base[1]).normalize()
    inicio_1y = inicio + relativedelta(years=1)
    fin_1y = fin + relativedelta(years=1)
    etiqueta_base = (
        str(inicio.year) if inicio.year == fin.year
        else f"{inicio.year}–{fin.year}"
    )
    etiqueta_comp = (
        str(inicio_1y.year) if inicio_1y.year == fin_1y.year
        else f"{inicio_1y.year}–{fin_1y.year}"
    )
    df = df_horario.copy()
    fechas = pd.to_datetime(df["fecha_hora"], errors="coerce")
    mascara = (
        ((fechas >= inicio) & (fechas < fin + pd.Timedelta(days=1)))
        | ((fechas >= inicio_1y) & (fechas < fin_1y + pd.Timedelta(days=1)))
    )
    df = df.loc[mascara].copy()
    df["fecha_hora"] = fechas.loc[mascara]
    if df.empty:
        return pd.DataFrame()
    df["año"] = df["fecha_hora"].dt.year
    df["mes_num"] = df["fecha_hora"].dt.month
    nombres_meses = {
        1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
        5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
        9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
    }
    df["mes_nombre"] = df["mes_num"].map(nombres_meses)
    mensual = (
        df.groupby(["año", "mes_num", "mes_nombre"], as_index=False)
        .agg(
            consumo_neto_kWh=("consumo_neto_kWh", "sum"),
            coste_total=("coste_total", "sum"),
        )
    )
    mensual["fecha"] = pd.to_datetime(dict(
        year=mensual["año"], month=mensual["mes_num"], day=1
    ))
    return mensual


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

        # Los datos recibidos pueden estar ya recortados hora a hora al rango
        # exacto. La fecha mensual solo sirve aquí para seleccionar sus meses.
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

    if isinstance(rango_base, (tuple, list)) and len(rango_base) == 2:
        rango_ini = pd.to_datetime(rango_base[0])
        rango_fin = pd.to_datetime(rango_base[1])
        rango_ini_1y = rango_ini + relativedelta(years=1)
        rango_fin_1y = rango_fin + relativedelta(years=1)
        etiqueta_base = (
            str(rango_ini.year) if rango_ini.year == rango_fin.year
            else f"{rango_ini.year}–{rango_fin.year}"
        )
        etiqueta_comp = (
            str(rango_ini_1y.year)
            if rango_ini_1y.year == rango_fin_1y.year
            else f"{rango_ini_1y.year}–{rango_fin_1y.year}"
        )
    else:
        etiqueta_base = str(int(df_cmp["año_base"].min()))
        etiqueta_comp = str(int(df_cmp["año_comp"].min()))

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
            "consumo_base": f"Consumo {etiqueta_base}",
            "consumo_comp": f"Consumo {etiqueta_comp}",
            "coste_base": f"Coste {etiqueta_base}",
            "coste_comp": f"Coste {etiqueta_comp}",
            "variacion_coste": "Δ coste",
            "variacion_coste_pct": "Δ coste %",
            "precio_base_cent_kwh": f"Precio {etiqueta_base}",
            "precio_comp_cent_kwh": f"Precio {etiqueta_comp}"
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
    variacion_coste_pct_total = (
        variacion_total / coste_base_total * 100 if coste_base_total else 0.0
    )
    tipo_variacion_coste = (
        "incremento" if variacion_total > 0
        else "decremento" if variacion_total < 0
        else "variación nula"
    )
    impacto_total_html_costes = f"""
    <div style="padding:1rem .8rem;border:1px solid #e0b400;
        border-left:6px solid #e0b400;border-radius:.75rem;
        background:#fff3bf;color:#5f4b00;text-align:center;
        box-shadow:0 2px 8px rgba(224,180,0,.16);">
        <div style="font-size:28px;line-height:1.15;">
            El <b>{tipo_variacion_coste}</b> del coste en el periodo seleccionado ha sido de:
        </div>
        <div style="font-size:36px;font-weight:bold;line-height:1.15;margin-top:.35rem;">
            {formato_numero_es(variacion_total, 2)} €&nbsp;
            (&nbsp;{formato_numero_es(variacion_coste_pct_total, 2)} %&nbsp;)
        </div>
    </div>
    """

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
    signo_precio = "+" if efecto_precio_total > 0 else ""
    signo_consumo = "+" if efecto_consumo_total > 0 else ""
    impacto_html_costes = f"""
    <div style="padding:1.15rem 1.25rem;border:1px solid #e0b400;
        border-left:6px solid #e0b400;border-radius:.75rem;
        background:#fff3bf;color:#5f4b00;margin:.2rem 0 .8rem 0;
        box-shadow:0 2px 8px rgba(224,180,0,.16);font-size:1.35rem;line-height:1.8;">
        <div><b>Efecto precio:</b>
            <span style="font-size:1.85rem;font-weight:800;margin-left:.45rem;">
                {signo_precio}{formato_numero_es(efecto_precio_total, 2)} €
            </span>
        </div>
        <div><b>Efecto consumo:</b>
            <span style="font-size:1.85rem;font-weight:800;margin-left:.45rem;">
                {signo_consumo}{formato_numero_es(efecto_consumo_total, 2)} €
            </span>
        </div>
    </div>
    """

    fig_resumen_costes = go.Figure()
    for nombre, valor, color in (
        (etiqueta_base, coste_base_total, "#1f77b4"),
        (etiqueta_comp, coste_comp_total, "#ff7f0e"),
    ):
        fig_resumen_costes.add_trace(go.Bar(
            x=["TOTAL"],
            y=[valor],
            name=nombre,
            marker_color=color,
            text=[formato_numero_es(valor, 2) + " €"],
            texttemplate="<b>%{text}</b>",
            textposition="outside",
            textfont=dict(size=20),
            cliponaxis=False,
            hovertemplate=(
                f"{nombre}: {formato_numero_es(valor, 2)} €<extra></extra>"
            ),
        ))
    _añadir_diferencial_hover_unico(
        fig_resumen_costes,
        x=["TOTAL"],
        y=[max(coste_base_total, coste_comp_total)],
        diferencial=[variacion_total],
        diferencial_pct=[variacion_coste_pct_total],
        etiqueta=f"{etiqueta_comp}−{etiqueta_base}",
        unidad="€",
        decimales=2,
    )
    fig_resumen_costes.update_layout(
        title="Comparativa TOTAL de costes (€)",
        barmode="group",
        hovermode="x unified",
        barcornerradius="10%",
        bargap=.42,
        bargroupgap=.38,
        xaxis_title="",
        yaxis_title="€",
        uniformtext_minsize=18,
        uniformtext_mode="show",
        hoverlabel=dict(font_size=16, font_family="Arial"),
    )
    fig_resumen_costes = aplicar_estilo(fig_resumen_costes)

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
            name=f"Coste {etiqueta_base}",
            marker_color = color_base,
            hovertemplate=f"Coste {etiqueta_base}: %{{y:.2f}} €<extra></extra>"
        )
    )

    fig_coste_total.add_trace(
        go.Bar(
            x=df_cmp["mes_label"],
            y=df_cmp["coste_comp"],
            name=f"Coste {etiqueta_comp}",
            marker_color = color_comp,
            hovertemplate=f"Coste {etiqueta_comp}: %{{y:.2f}} €<extra></extra>"
        )
    )

    fig_coste_total.update_layout(
        title="Comparativa mensual de COSTES (€)",
        barmode="group",
        hovermode="x unified",
        legend_title_text="",
        barcornerradius="28%",
        bargap=0.25,
        bargroupgap=0.1,
        hoverlabel=dict(font_size=16, font_family="Arial"),
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
        barcornerradius=8,
        hovermode="x unified",
        legend_title_text=""
        ,hoverlabel=dict(font_size=16, font_family="Arial")
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
    diferencial_precio = (
        df_cmp["precio_comp_cent_kwh"] - df_cmp["precio_base_cent_kwh"]
    )
    diferencial_precio_pct = np.where(
        df_cmp["precio_base_cent_kwh"] != 0,
        diferencial_precio / df_cmp["precio_base_cent_kwh"] * 100,
        np.nan,
    )
    fig_precio_medio = go.Figure()

    fig_precio_medio.add_trace(
        go.Scatter(
            x=df_cmp["mes_label"],
            y=df_cmp["precio_base_cent_kwh"],
            mode="lines+markers",
            name=f"Precio {etiqueta_base}",
            marker_color = color_base,
            line=dict(width=3),
            marker=dict(size=7),
            hovertemplate=(
                f"Precio {etiqueta_base}: %{{y:.2f}} c€/kWh<extra></extra>"
            )
        )
    )

    fig_precio_medio.add_trace(
        go.Scatter(
            x=df_cmp["mes_label"],
            y=df_cmp["precio_comp_cent_kwh"],
            mode="lines+markers",
            name=f"Precio {etiqueta_comp}",
            marker_color = color_comp,
            line=dict(width=3),
            marker=dict(size=7),
            hovertemplate=(
                f"Precio {etiqueta_comp}: %{{y:.2f}} c€/kWh<extra></extra>"
            )
        )
    )

    _añadir_diferencial_hover_unico(
        fig_coste_total,
        x=df_cmp["mes_label"],
        y=df_cmp[["coste_base", "coste_comp"]].max(axis=1),
        diferencial=df_cmp["variacion_coste"],
        diferencial_pct=df_cmp["variacion_coste_pct"],
        etiqueta=f"{etiqueta_comp}−{etiqueta_base}",
        unidad="€",
        decimales=2,
    )

    _añadir_diferencial_hover_unico(
        fig_precio_medio,
        x=df_cmp["mes_label"],
        y=df_cmp[["precio_base_cent_kwh", "precio_comp_cent_kwh"]].max(axis=1),
        diferencial=diferencial_precio,
        diferencial_pct=diferencial_precio_pct,
        etiqueta=f"{etiqueta_comp}−{etiqueta_base}",
        unidad="c€/kWh",
        decimales=2,
    )

    fig_precio_medio.add_hline(
        y=precio_base_total,
        line_color=color_base,
        line_width=2,
        line_dash="dot",
    )
    fig_precio_medio.add_hline(
        y=precio_comp_total,
        line_color=color_comp,
        line_width=2,
        line_dash="dot",
    )

    fig_precio_medio.update_layout(
        title="Comparativa mensual de PRECIOS (c€/kWh)",
        hovermode="x unified",
        legend_title_text=""
        ,hoverlabel=dict(font_size=16, font_family="Arial")
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
        "impacto_total_html_costes": impacto_total_html_costes,
        "impacto_html_costes": impacto_html_costes,
        "fig_coste_total": fig_coste_total,
        "fig_resumen_costes": fig_resumen_costes,
        "fig_efectos": fig_efectos,
        "fig_precio_medio": fig_precio_medio,
        "etiquetas_periodos": (etiqueta_base, etiqueta_comp),
    }


def calcular_comparativa_ahorro(df_actual, df_referencia):
    """Compara dos precios sobre el mismo consumo y el mismo rango temporal."""
    requeridas = {"fecha_hora", "consumo_neto_kWh", "coste_total"}
    for nombre, datos in (("actual", df_actual), ("referencia", df_referencia)):
        if datos is None or datos.empty or not requeridas.issubset(datos.columns):
            return {
                "ok": False,
                "mensaje": f"Faltan datos horarios del escenario {nombre}.",
                "df_ahorro": pd.DataFrame(), "fig_mensual": None,
                "fig_diferencia": None,
            }

    def mensual(datos, prefijo):
        df = datos.copy()
        df["Mes"] = pd.to_datetime(df["fecha_hora"]).dt.to_period("M").astype(str)
        df["consumo_neto_kWh"] = pd.to_numeric(
            df["consumo_neto_kWh"], errors="coerce"
        )
        df["coste_total"] = pd.to_numeric(df["coste_total"], errors="coerce")
        return df.groupby("Mes", as_index=False).agg(**{
            f"Consumo {prefijo}": ("consumo_neto_kWh", "sum"),
            f"Coste {prefijo}": ("coste_total", "sum"),
        })

    actual = mensual(df_actual, "real")
    referencia = mensual(df_referencia, "referencia")
    salida = referencia.merge(actual, on="Mes", how="outer", validate="one_to_one")
    salida = salida.sort_values("Mes").reset_index(drop=True)
    if not np.allclose(
        salida["Consumo referencia"], salida["Consumo real"],
        rtol=0, atol=1e-6, equal_nan=False,
    ):
        return {
            "ok": False,
            "mensaje": "Los escenarios no contienen exactamente el mismo consumo mensual.",
            "df_ahorro": pd.DataFrame(), "fig_mensual": None,
            "fig_diferencia": None,
        }
    consumo = salida["Consumo real"]
    salida["Precio referencia"] = np.where(
        consumo != 0, salida["Coste referencia"] / consumo * 100, np.nan
    )
    salida["Precio real"] = np.where(
        consumo != 0, salida["Coste real"] / consumo * 100, np.nan
    )
    salida["Ahorro / sobrecoste"] = salida["Coste real"] - salida["Coste referencia"]
    salida["Ahorro / sobrecoste %"] = np.where(
        salida["Coste referencia"] != 0,
        salida["Ahorro / sobrecoste"]
        / salida["Coste referencia"] * 100,
        np.nan,
    )

    coste_referencia = salida["Coste referencia"].sum()
    coste_actual = salida["Coste real"].sum()
    diferencia = coste_actual - coste_referencia
    diferencia_pct = diferencia / coste_referencia * 100 if coste_referencia else np.nan
    consumo_total = consumo.sum()
    tipo_impacto = (
        "sobrecoste" if diferencia > 0
        else "ahorro" if diferencia < 0
        else "resultado neutro"
    )
    impacto_html = f"""
    <div style="padding:1rem .8rem;border:1px solid #e0b400;
        border-left:6px solid #e0b400;border-radius:.75rem;
        background:#fff3bf;color:#5f4b00;text-align:center;
        box-shadow:0 2px 8px rgba(224,180,0,.16);">
        <div style="font-size:28px;line-height:1.15;">
            El <b>{tipo_impacto}</b> frente al coste de referencia ha sido de:
        </div>
        <div style="font-size:36px;font-weight:bold;line-height:1.15;margin-top:.35rem;">
            {formato_numero_es(abs(diferencia), 2)} €&nbsp;
            (&nbsp;{formato_numero_es(abs(diferencia_pct), 2)} %&nbsp;)
        </div>
    </div>
    """

    datos_graf = salida.melt(
        id_vars="Mes",
        value_vars=[
            "Coste referencia", "Coste real",
        ],
        var_name="Escenario",
        value_name="Coste",
    )
    fig_mensual = px.bar(
        datos_graf, x="Mes", y="Coste", color="Escenario", barmode="group",
        title="Coste mensual real frente a referencia",
        labels={"Coste": "Coste (€)"},
    )
    fig_mensual.update_traces(marker_cornerradius=10)
    fig_mensual = aplicar_estilo(fig_mensual)
    fig_mensual.update_layout(
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="center", x=0.5,
        )
    )

    fig_diferencia = go.Figure(go.Bar(
        x=salida["Mes"], y=salida["Ahorro / sobrecoste"],
        marker_color=np.where(
            salida["Ahorro / sobrecoste"] > 0, "#d62728", "#2ca02c"
        ),
        marker_cornerradius=10,
        hovertemplate="<b>%{x}</b><br>Ahorro / sobrecoste: %{y:.2f} €<extra></extra>",
    ))
    fig_diferencia.update_layout(
        title="Ahorro (-) / sobrecoste (+) mensual", yaxis_title="€",
        xaxis_title="",
    )
    fig_diferencia.add_hline(y=0, line_color="white", line_width=1)
    fig_diferencia = aplicar_estilo(fig_diferencia)
    fig_diferencia.update_layout(
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="center", x=0.5,
        )
    )

    fig_impacto = go.Figure()
    for nombre, valor, color in (
        ("Referencia", coste_referencia, "#1f77b4"),
        ("Real contractual", coste_actual, "#ff7f0e"),
    ):
        fig_impacto.add_trace(go.Bar(
            x=["TOTAL"], y=[valor], name=nombre, marker_color=color,
            text=[formato_numero_es(valor, 2) + " €"],
            texttemplate="<b>%{text}</b>", textposition="outside",
            textfont=dict(size=20), cliponaxis=False,
            hovertemplate=(
                f"{nombre}: {formato_numero_es(valor, 2)} €<extra></extra>"
            ),
        ))
    _añadir_diferencial_hover_unico(
        fig_impacto,
        x=["TOTAL"], y=[max(coste_referencia, coste_actual)],
        diferencial=[diferencia], diferencial_pct=[diferencia_pct],
        etiqueta="Real−referencia", unidad="€", decimales=2,
    )
    fig_impacto.update_layout(
        title="Impacto económico total (€)", barmode="group",
        hovermode="x unified", barcornerradius="10%", bargap=.42,
        bargroupgap=.38, xaxis_title="", yaxis_title="€",
        uniformtext_minsize=18, uniformtext_mode="show",
        hoverlabel=dict(font_size=16, font_family="Arial"),
    )
    fig_impacto = aplicar_estilo(fig_impacto)
    fig_impacto.update_layout(
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="center", x=0.5,
        )
    )

    return {
        "ok": True,
        "mensaje": "",
        "df_ahorro": salida,
        "etiquetas_periodos": ("referencia", "real"),
        "coste_referencia": coste_referencia,
        "coste_real": coste_actual,
        "diferencia": diferencia,
        "diferencia_pct": diferencia_pct,
        "precio_referencia": coste_referencia / consumo_total * 100 if consumo_total else np.nan,
        "precio_real": coste_actual / consumo_total * 100 if consumo_total else np.nan,
        "fig_mensual": fig_mensual,
        "fig_diferencia": fig_diferencia,
        "fig_impacto": fig_impacto,
        "impacto_html": impacto_html,
    }


