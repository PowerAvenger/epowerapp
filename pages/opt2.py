import hashlib
import math
import pathlib
import re
import tempfile

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from utilidades import generar_menu
from backend_opt2 import (leer_curva_normalizada, calcular_costes, calcular_optimizacion, pyc_tp, tepp45, tepp123, meses, normalizar_tabla_maximetros, prorratear_excesos_ciclo_tipo_123)
from backend_sips import leer_sips_completo, potencias_contratadas_sips
from backend_curvadecarga import colores_periodo
from backend_comun import aplicar_estilo
from report_generator import preparar_informe, generar_formato_informe
from utils_docx import generar_docx_bytes, insertar_tabla
from formato_es import formato_euros, formato_numero_es
from componentes_curva import render_origen_curva


CLAVES_RESULTADOS_POTENCIA = (
    "resultados_potencia",
    "resultados_verificacion_potencia",
    "resultado_comparacion_potencias",
    "opt2_informe_preparado",
)


def invalidar_resultados_potencia():
    """Retira cálculos que ya no corresponden a los datos de entrada."""
    habia_resultados = any(
        clave in st.session_state for clave in CLAVES_RESULTADOS_POTENCIA
    )
    for clave in CLAVES_RESULTADOS_POTENCIA:
        st.session_state.pop(clave, None)
    st.session_state.pop("termino_potencia_contexto_resultados", None)
    return habia_resultados


if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')

generar_menu()

tab_entrada, tab_optimizacion, tab_verificacion, tab_comparacion, tab_informe = st.tabs(
    ['Datos de entrada', 'Optimización', 'Verificación', 'Comparar potencias', 'Informe']
)
with tab_entrada:
    col_origen_curva, col_datos_potencia, col_avisos_acciones = st.columns(
        [0.36, 0.34, 0.30], gap="large"
    )

col_avisos_acciones.subheader("Avisos y acciones", divider="rainbow")

col_origen_curva.subheader("Origen de datos", divider="rainbow")
origen_datos_potencia = col_origen_curva.radio(
    "Selecciona el origen de datos",
    ["Curva", "SIPS"],
    horizontal=True,
    label_visibility="collapsed",
    key="termino_potencia_origen_datos",
)
potencias_sips_entrada = None
periodos_potencia_sips_entrada = []
sips_nuevo_entrada = False
if origen_datos_potencia == "Curva":
    render_origen_curva(
        col_origen_curva,
        col_origen_curva,
        clave="termino_potencia_curva",
        titulo_compacto=True,
    )
else:
    col_origen_curva.markdown("#### Archivo SIPS")
    archivo_sips_entrada = col_origen_curva.file_uploader(
        "Sube el CSV o Excel SIPS",
        type=["csv", "xlsx", "xls"],
        key="termino_potencia_sips",
    )
    if archivo_sips_entrada is None:
        if st.session_state.get("sips_termino_potencia") is None:
            col_origen_curva.info(
                "Sube un CSV o Excel SIPS para cargar potencias y maxímetros."
            )
        else:
            col_origen_curva.caption("SIPS recuperado de la sesión.")
    else:
        try:
            contenido_sips = archivo_sips_entrada.getvalue()
            firma_sips = hashlib.sha256(contenido_sips).hexdigest()
            firma_archivo_anterior = st.session_state.get(
                "termino_potencia_firma_archivo_sips_seleccionado",
                st.session_state.get("termino_potencia_firma_sips"),
            )
            if (
                firma_archivo_anterior is not None
                and firma_archivo_anterior != firma_sips
            ):
                invalidar_resultados_potencia()
                st.session_state.pop("sips_termino_potencia", None)
                st.session_state.pop("termino_potencia_periodos_sips", None)
                st.session_state.pop(
                    "termino_potencia_firma_potencias_v2", None
                )
                if st.session_state.get(
                    "termino_potencia_origen_maximetros"
                ) == "SIPS":
                    st.session_state.pop("df_maximetros", None)
                    st.session_state.pop(
                        "termino_potencia_origen_maximetros", None
                    )
                    st.session_state.pop(
                        "termino_potencia_firma_maximetros", None
                    )
                st.session_state.pop("df_pot", None)
                st.session_state.termino_potencia_potencias_confirmadas = False
            st.session_state.termino_potencia_firma_archivo_sips_seleccionado = (
                firma_sips
            )
            sips_entrada = leer_sips_completo(archivo_sips_entrada)
            atr_sips_entrada = sips_entrada.get("atr")
            if atr_sips_entrada is not None and atr_sips_entrada not in {
                "2.0", "3.0", "6.1", "6.2", "6.3", "6.4"
            }:
                raise ValueError("El SIPS no contiene un ATR compatible.")
            potencias_sips_entrada = potencias_contratadas_sips(
                sips_entrada.get("metadatos")
            )
            periodos_potencia_sips_entrada = [
                periodo
                for periodo in [f"P{i}" for i in range(1, 7)]
                if (
                    pd.notna(potencias_sips_entrada.get(periodo))
                    and float(potencias_sips_entrada.get(periodo)) > 0
                )
            ]
            st.session_state.termino_potencia_periodos_sips = (
                periodos_potencia_sips_entrada
            )
            st.session_state.sips_termino_potencia = sips_entrada
            st.session_state.df_maximetros = sips_entrada["maximetros"][
                [
                    "periodo_mes", "mes_nom", "dias_facturacion",
                    "P1", "P2", "P3", "P4", "P5", "P6",
                ]
            ].copy()
            st.session_state.termino_potencia_origen_maximetros = "SIPS"
            st.session_state.termino_potencia_firma_maximetros = firma_sips
            if atr_sips_entrada is not None:
                st.session_state.atr_dfnorm = atr_sips_entrada
                st.session_state.tarifa_maximetros = atr_sips_entrada
            sips_nuevo_entrada = (
                st.session_state.get("termino_potencia_firma_potencias_v2")
                != firma_sips
            )
            st.session_state.termino_potencia_firma_sips = firma_sips
            st.session_state.termino_potencia_firma_potencias_v2 = firma_sips
            col_origen_curva.success(
                "SIPS cargado · "
                + (
                    f"ATR {atr_sips_entrada}TD · "
                    if atr_sips_entrada else "ATR no informado · "
                )
                + f"{len(st.session_state.df_maximetros)} ciclos."
            )
        except Exception as error_sips:
            col_origen_curva.error(f"No se pudo leer el SIPS: {error_sips}")



if 'mantener_potencia' not in st.session_state:
    st.session_state.mantener_potencia = "Mantener" 
if 'forzar_maximetros' not in st.session_state:
    st.session_state.forzar_maximetros = False

# Interfaz manual reservada para una posible reactivacion futura.
MOSTRAR_CARGA_MANUAL_MAXIMETROS = False
if not MOSTRAR_CARGA_MANUAL_MAXIMETROS:
    st.session_state.forzar_maximetros = False

pot_con_ini = {
    'P1' : 0.0,
    'P2' : 0.0,
    'P3' : 0.0,
    'P4' : 0.0,
    'P5' : 0.0,
    'P6' : 0.0,
}
df_pot_ini = pd.DataFrame(
    {
        "Periodo": pot_con_ini.keys(),
        "Potencia (kW)": pot_con_ini.values()
    }
).set_index("Periodo")

if "df_pot" not in st.session_state:
    st.session_state.df_pot = df_pot_ini
else:
    df_pot_ini = st.session_state.df_pot

if "termino_potencia_potencias_confirmadas" not in st.session_state:
    st.session_state.termino_potencia_potencias_confirmadas = False

if sips_nuevo_entrada and potencias_sips_entrada is not None:
    potencias_base = pd.Series(pot_con_ini, dtype=float)
    potencias_base.update(potencias_sips_entrada.dropna())
    st.session_state.df_pot = pd.DataFrame(
        {"Potencia (kW)": potencias_base}
    ).rename_axis("Periodo")
    df_pot_ini = st.session_state.df_pot
    st.session_state.termino_potencia_potencias_confirmadas = (
        len(periodos_potencia_sips_entrada) == 6
    )

col_datos_potencia.subheader("Datos de potencia", divider="rainbow")
col_datos_potencia.markdown("#### Potencias contratadas")

df_pot_editor = df_pot_ini.copy()
df_pot_editor["Potencia (kW)"] = df_pot_editor["Potencia (kW)"].map(
    lambda valor: formato_numero_es(valor, 3)
)
df_pot_edit = col_datos_potencia.data_editor(
    df_pot_editor,
    use_container_width=True,
    num_rows="fixed",
    column_config={
        "Potencia (kW)": st.column_config.TextColumn(
            "Potencia (kW)",
            help="Admite coma o punto decimal.",
        )
    },
)

def normalizar_potencias_editadas(df):
    resultado = df.copy()

    def convertir(valor):
        if isinstance(valor, (int, float)):
            return float(valor)
        texto = str(valor).strip().replace(" ", "")
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        return pd.to_numeric(texto, errors="coerce")

    resultado["Potencia (kW)"] = resultado["Potencia (kW)"].map(
        convertir
    )
    return resultado


MIN_P1 = 0.1
MIN_P6 = 0.1
def validar_potencias(df):
    errores = []

    # mínimos
    if df.loc["P1", "Potencia (kW)"] < MIN_P1:
        errores.append("P1 debe ser ≥ 0,1 kW")

    if df.loc["P6", "Potencia (kW)"] < MIN_P6:
        errores.append("P6 debe ser ≥ 0,1 kW")

    # orden P1 ≤ P2 ≤ ... ≤ P6
    potencias = df["Potencia (kW)"].values
    if not all(potencias[i] <= potencias[i+1] for i in range(len(potencias)-1)):
        errores.append("Debe cumplirse P1 ≤ P2 ≤ P3 ≤ P4 ≤ P5 ≤ P6")

    return errores


if col_datos_potencia.button(
    'Cargar potencias contratadas',
    use_container_width=True,
    type='primary',
    key='cargar_potencias_contratadas',
):
    df_pot_candidata = normalizar_potencias_editadas(df_pot_edit)
    if df_pot_candidata["Potencia (kW)"].isna().any():
        errores = [
            "Introduce valores numéricos válidos en todas las potencias."
        ]
    else:
        errores = validar_potencias(df_pot_candidata)

    if errores:
        for e in errores:
            col_avisos_acciones.error(e)
    else:
        st.session_state.df_pot = df_pot_candidata
        st.session_state.termino_potencia_potencias_confirmadas = True
        col_avisos_acciones.success("Potencias cargadas correctamente")


def _formato_kw(valor):
    texto = f"{float(valor):,.3f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


potencias_confirmadas = st.session_state.get(
    "termino_potencia_potencias_confirmadas", False
)
periodos_potencia_sips = st.session_state.get(
    "termino_potencia_periodos_sips", []
)

if origen_datos_potencia == "SIPS" and st.session_state.get(
    "sips_termino_potencia"
) is not None:
    if not periodos_potencia_sips:
        mensaje_potencias_sips = (
            "El SIPS no informa las potencias contratadas. "
        )
        if potencias_confirmadas:
            mensaje_potencias_sips += (
                "Se usarán las potencias introducidas manualmente."
            )
        else:
            mensaje_potencias_sips += (
                "Introduce P1–P6 y pulsa **Cargar potencias contratadas**."
            )
        col_avisos_acciones.warning(mensaje_potencias_sips, icon="⚠️")
    elif len(periodos_potencia_sips) < 6 and not potencias_confirmadas:
        periodos_faltantes = [
            f"P{i}" for i in range(1, 7)
            if f"P{i}" not in periodos_potencia_sips
        ]
        col_avisos_acciones.warning(
            "El SIPS no informa todas las potencias contratadas. "
            f"Completa {', '.join(periodos_faltantes)} y confirma la carga.",
            icon="⚠️",
        )

if potencias_confirmadas:
    potencias_cargadas = st.session_state.df_pot["Potencia (kW)"]
    detalle_potencias = [
        f"**P{i}:** {_formato_kw(potencias_cargadas.loc[f'P{i}'])} kW"
        for i in range(1, 7)
    ]
    col_avisos_acciones.info(
        f"**Potencias cargadas · {origen_datos_potencia}**\n\n"
        + " · ".join(detalle_potencias[:3])
        + "  \n"
        + " · ".join(detalle_potencias[3:])
    )

print('df_pot')
print(st.session_state.df_pot)

p6 = float(st.session_state.df_pot.loc["P6", "Potencia (kW)"])
# modo1 = True  -> tipos 4/5: maxímetros
# modo1 = False -> tipos 1/2/3: curva de carga
modo1 = origen_datos_potencia == "SIPS" or p6 <= 50

if st.session_state.forzar_maximetros:
    modo1 = True

col_datos_potencia.radio(
    "Selecciona potencia P6",
    ["Mantener", "No mantener"],
    horizontal=True,
    key='mantener_potencia'
)

if (
    origen_datos_potencia == "SIPS"
    and st.session_state.get("df_maximetros") is not None
):
    tabla_maximetros_sips = st.session_state.df_maximetros[
        ["periodo_mes", "P1", "P2", "P3", "P4", "P5", "P6"]
    ].copy()
    tabla_maximetros_sips = tabla_maximetros_sips.sort_values(
        "periodo_mes", ascending=False
    )
    with col_datos_potencia.expander(
        "Ver maxímetros SIPS P1–P6 (kW)"
    ):
        st.dataframe(
            tabla_maximetros_sips,
            hide_index=True,
            use_container_width=True,
            column_config={
                "periodo_mes": st.column_config.TextColumn("Periodo"),
                **{
                    f"P{i}": st.column_config.NumberColumn(
                        f"P{i}", format="%.3f"
                    )
                    for i in range(1, 7)
                },
            },
        )

if 'atr_dfnorm' not in st.session_state:
    st.session_state.atr_dfnorm = 'Ninguno'

pot_con = st.session_state.df_pot["Potencia (kW)"].to_dict()
orden_periodos = [f'P{i}' for i in range(1, 7)]
fijar_P6 = st.session_state["mantener_potencia"] == "Mantener"

if 'frec' not in st.session_state:
    st.session_state.frec = 'None'



habilitar_opt = False
habilitar_ver = False
tarifa = st.session_state.atr_dfnorm

# La lectura manual queda preparada, pero por ahora los maximetros
# se obtienen unicamente desde el SIPS.
archivo_max_sesion = (
    st.session_state.get("upload_maximetros")
    if MOSTRAR_CARGA_MANUAL_MAXIMETROS else None
)
sips_potencia_detectado = (
    st.session_state.get("sips_termino_potencia")
    if origen_datos_potencia == "SIPS" else None
)
atr_sips_potencia = (
    sips_potencia_detectado.get("atr")
    if sips_potencia_detectado is not None else None
)
if (
    sips_potencia_detectado is None
    and
    modo1
    and archivo_max_sesion is not None
    and archivo_max_sesion.name.lower().endswith(".csv")
):
    try:
        sips_potencia_detectado = leer_sips_completo(archivo_max_sesion)
        atr_sips_potencia = sips_potencia_detectado.get("atr")
    except Exception:
        # La carga inferior presenta el error completo del fichero.
        pass
if atr_sips_potencia in {"2.0", "3.0", "6.1", "6.2", "6.3", "6.4"}:
    st.session_state.tarifa_maximetros = atr_sips_potencia
    tarifa = atr_sips_potencia



# Los Excel SIPS simplificados pueden incluir medidas y CUPS, pero no ATR.
# En ese caso el peaje se solicita sin reactivar la carga manual antigua.
if modo1 and (
    MOSTRAR_CARGA_MANUAL_MAXIMETROS
    or (origen_datos_potencia == "SIPS" and atr_sips_potencia is None)
):
    opciones_tarifa = ["2.0", "3.0", "6.1", "6.2", "6.3", "6.4"]
    if st.session_state.get("tarifa_maximetros") not in opciones_tarifa:
        st.session_state.tarifa_maximetros = "3.0"
    tarifa = col_datos_potencia.selectbox(
        "Peaje de acceso",
        opciones_tarifa,
        key="tarifa_maximetros",
        disabled=atr_sips_potencia is not None,
    )
    if sips_potencia_detectado is not None:
        if atr_sips_potencia is None:
            col_avisos_acciones.warning(
                "El SIPS no informa el ATR. Selecciónalo manualmente."
            )
            st.session_state.atr_dfnorm = tarifa
            sips_potencia_detectado["atr"] = tarifa
            st.session_state.sips_termino_potencia = sips_potencia_detectado
        else:
            col_avisos_acciones.info(
                f"ATR {atr_sips_potencia}TD leído del SIPS. "
                "El selector queda bloqueado."
            )

if (
    MOSTRAR_CARGA_MANUAL_MAXIMETROS
    and p6 > 50
    and origen_datos_potencia == "Curva"
):
        
    col_datos_potencia.checkbox(
        "Forzar optimización por maxímetro aunque P6 > 50 kW",
        value=False,
        help="Activa esta opción si quieres aplicar el método de maxímetro incluso en suministros con P6 superior a 50 kW.",
        key='forzar_maximetros'
    )    

if modo1:
    # P6 <= 50 → maxímetros

    col_avisos_acciones.write(f'El peaje del suministro es **:orange[{tarifa}]**')
    if origen_datos_potencia == "SIPS":
        col_avisos_acciones.info(
            'Modo SIPS: optimización mediante maxímetros.'
        )
        if p6 > 50:
            col_avisos_acciones.warning(
                "Se va a optimizar un suministro tipo 1, 2 o 3 "
                "mediante maxímetros. Es preferible hacerlo con una "
                "curva de carga.",
                icon="⚠️",
            )
    else:
        col_avisos_acciones.info(
            'Modo P6 ≤ 50: optimización mediante maxímetros'
        )
    if st.session_state.forzar_maximetros:
        col_avisos_acciones.warning('¡¡Estás optimizando mediante maxímetros con P6 >50kW!!')

    archivo_max = None
    if (
        MOSTRAR_CARGA_MANUAL_MAXIMETROS
        and origen_datos_potencia == "Curva"
    ):
        archivo_max = col_datos_potencia.file_uploader(
            "Sube tabla manual de maxímetros o CSV SIPS",
            type=["xlsx", "csv"],
            key="upload_maximetros"
        )
    elif origen_datos_potencia == "SIPS":
        col_datos_potencia.caption(
            "Maxímetros cargados desde el SIPS de la columna 1."
        )

    if archivo_max is not None:
        try:
            if archivo_max.name.lower().endswith(".csv"):
                sips_potencia = (
                    sips_potencia_detectado or leer_sips_completo(archivo_max)
                )
                df_maximetros = sips_potencia["maximetros"][
                    ["periodo_mes", "mes_nom", "dias_facturacion",
                     "P1", "P2", "P3", "P4", "P5", "P6"]
                ].copy()
                st.session_state.sips_termino_potencia = sips_potencia
                col_avisos_acciones.info(
                    "SIPS leído: consumos, reactiva y maxímetros disponibles."
                )
            else:
                st.session_state.pop("sips_termino_potencia", None)
                df_maximetros_raw = pd.read_excel(archivo_max)
                df_maximetros = normalizar_tabla_maximetros(
                    df_maximetros_raw,
                    meses
                )

            st.session_state.df_maximetros = df_maximetros
            st.session_state.termino_potencia_origen_maximetros = (
                "SIPS" if archivo_max.name.lower().endswith(".csv")
                else "Manual"
            )
            st.session_state.termino_potencia_firma_maximetros = (
                st.session_state.get("termino_potencia_firma_sips")
                if archivo_max.name.lower().endswith(".csv") else None
            )
            col_avisos_acciones.success("Tabla de maxímetros cargada correctamente")

        except Exception as e:
            col_avisos_acciones.error(f"Error en tabla de maxímetros: {e}")
            habilitar_opt = False
            habilitar_ver = False

    origen_maximetros = st.session_state.get(
        "termino_potencia_origen_maximetros"
    )
    firma_maximetros = st.session_state.get(
        "termino_potencia_firma_maximetros"
    )
    maximetros_de_fuente_actual = (
        origen_datos_potencia == "SIPS"
        and origen_maximetros == "SIPS"
        and firma_maximetros
        == st.session_state.get("termino_potencia_firma_sips")
    ) or (
        origen_datos_potencia == "Curva"
        and origen_maximetros == "Manual"
    )

    if (
        st.session_state.get("df_maximetros") is None
        or not maximetros_de_fuente_actual
    ):
        col_avisos_acciones.warning('Por favor introduce una tabla de maxímetros')
        habilitar_opt = False
        habilitar_ver = False

    else:
        df_maximetros_disponibles = st.session_state.df_maximetros.copy()
        df_in = df_maximetros_disponibles.tail(12).reset_index(drop=True)

        año_opt = 2026
        pyc_tp_opt = pyc_tp[año_opt][tarifa]

        tepp_opt = {
            k: v if v is not None else None
            for k, v in tepp45[año_opt][tarifa].items()
        }

        if origen_datos_potencia == "SIPS":
            periodos_sips = sorted(
                df_maximetros_disponibles["periodo_mes"]
                .dropna().astype(str).unique(),
                reverse=True,
            )
            clave_mes_sips = "mes_verificacion_sips_potencia"
            if st.session_state.get(clave_mes_sips) not in periodos_sips:
                st.session_state[clave_mes_sips] = periodos_sips[0]
            mes_verificacion_sips = col_datos_potencia.selectbox(
                "Mes de la verificación",
                periodos_sips,
                format_func=lambda periodo: (
                    f"{meses[int(periodo[5:7]) - 1]} {periodo[:4]}"
                ),
                key=clave_mes_sips,
            )
            df_verificacion_sips = df_maximetros_disponibles.loc[
                df_maximetros_disponibles["periodo_mes"]
                .astype(str).eq(mes_verificacion_sips)
            ].copy()
            año_ver = int(mes_verificacion_sips[:4])
            if año_ver in pyc_tp and año_ver in tepp45:
                pyc_tp_ver = {
                    periodo: valor if valor is not None else 0.0
                    for periodo, valor in pyc_tp[año_ver][tarifa].items()
                }
                tepp_ver = {
                    periodo: valor if valor is not None else 0.0
                    for periodo, valor in tepp45[año_ver][tarifa].items()
                }
                habilitar_ver = True
            else:
                col_avisos_acciones.warning(
                    f"No hay costes regulados disponibles para {año_ver}.",
                    icon="⚠️",
                )
                habilitar_ver = False

        meses_maximetros = len(df_in)
        col_avisos_acciones.caption('Costes regulados aplicados: 2026')
        if len(df_maximetros_disponibles) > 12:
            col_avisos_acciones.caption(
                f'Se usan los 12 meses más recientes de '
                f'{len(df_maximetros_disponibles)} disponibles.'
            )
        if meses_maximetros < 12:
            col_avisos_acciones.warning(
                f'Optimización basada en {meses_maximetros} mes(es) de '
                'maxímetros. El resultado puede no representar la '
                'estacionalidad anual.',
                icon='⚠️'
            )
        elif meses_maximetros == 12:
            col_avisos_acciones.success('Periodo recomendado: 12 meses analizados.')
        else:
            col_avisos_acciones.info(
                f'Optimización basada en {meses_maximetros} meses.'
            )

        habilitar_opt = True
        if origen_datos_potencia != "SIPS":
            habilitar_ver = False

else:
    if 'df_norm' not in st.session_state or st.session_state.df_norm is None:
        #st.session_state.df_norm = None
        col_avisos_acciones.warning('Por favor introduce una curva de carga')
        habilitar_opt = False
        habilitar_ver = False
    else:
        #tarifa = st.session_state.atr_dfnorm
        if tarifa != '2.0':
            df_in = leer_curva_normalizada(pot_con)
            col_avisos_acciones.write(f'El peaje del suministro es **:orange[{st.session_state.atr_dfnorm}]**')
            col_avisos_acciones.info('Selecciona la acción que quieras ejecutar.')
            fechas_verificacion_disponibles = pd.to_datetime(
                df_in['fecha_hora'], errors='coerce'
            ).dropna()
            fecha_min_verificacion = (
                fechas_verificacion_disponibles.min().date()
            )
            fecha_max_verificacion = (
                fechas_verificacion_disponibles.max().date()
            )
            rango_completo = True
            rango_dentro_curva = True
            tipo_periodo_verificacion = col_datos_potencia.radio(
                'Periodo de la verificación',
                ('Mes natural', 'Rango de fechas'),
                horizontal=True,
                key='tipo_periodo_verificacion_excesos',
            )
            if tipo_periodo_verificacion == 'Mes natural':
                periodos_verificacion = sorted(
                    fechas_verificacion_disponibles.dt.to_period('M')
                    .astype(str)
                    .unique(),
                    reverse=True,
                )
                clave_periodo_verificacion = 'periodo_verificacion_excesos'
                if (
                    st.session_state.get(clave_periodo_verificacion)
                    not in periodos_verificacion
                ):
                    st.session_state[clave_periodo_verificacion] = (
                        periodos_verificacion[0]
                    )
                periodo_verificacion = col_datos_potencia.selectbox(
                    'Mes de la verificación',
                    periodos_verificacion,
                    format_func=lambda periodo: (
                        f"{meses[int(periodo[5:7]) - 1]} {periodo[:4]}"
                    ),
                    key=clave_periodo_verificacion,
                )
                fechas_periodo_verificacion = fechas_verificacion_disponibles[
                    fechas_verificacion_disponibles.dt.to_period('M')
                    .astype(str)
                    .eq(periodo_verificacion)
                ]
                fecha_ini = fechas_periodo_verificacion.min().date()
                fecha_fin = fechas_periodo_verificacion.max().date()
            else:
                col_datos_potencia.caption(
                    'Fechas disponibles en la curva: '
                    f'{fecha_min_verificacion:%d/%m/%Y} - '
                    f'{fecha_max_verificacion:%d/%m/%Y}'
                )
                clave_curva_verificacion = (
                    f'{fecha_min_verificacion:%Y%m%d}_'
                    f'{fecha_max_verificacion:%Y%m%d}'
                )
                fecha_inicio_predeterminada = max(
                    fecha_min_verificacion,
                    (
                        pd.Timestamp(fecha_max_verificacion)
                        - pd.Timedelta(days=30)
                    ).date(),
                )
                col_fecha_ini, col_fecha_fin = col_datos_potencia.columns(2)
                fecha_ini = col_fecha_ini.date_input(
                    'Desde',
                    value=fecha_inicio_predeterminada,
                    min_value=fecha_min_verificacion,
                    max_value=fecha_max_verificacion,
                    format='DD/MM/YYYY',
                    key=f'fecha_ini_verificacion_{clave_curva_verificacion}',
                )
                fecha_fin = col_fecha_fin.date_input(
                    'Hasta',
                    value=fecha_max_verificacion,
                    min_value=fecha_min_verificacion,
                    max_value=fecha_max_verificacion,
                    format='DD/MM/YYYY',
                    key=f'fecha_fin_verificacion_{clave_curva_verificacion}',
                )
                rango_dentro_curva = (
                    fecha_min_verificacion <= fecha_ini
                    <= fecha_fin <= fecha_max_verificacion
                )
            dias_rango = (fecha_fin - fecha_ini).days + 1
            año_ver = fecha_ini.year

            const_verif = 31

            if st.session_state.frec =='H':
                coef_excesos = 2
                col_avisos_acciones.warning('Cálculo de excesos con curva HORARIA', icon='⚠️')
            else:
                coef_excesos = 1

            fechas_opt = pd.to_datetime(
                df_in['fecha_hora'], errors='coerce'
            ).dropna()
            periodos_analizados = fechas_opt.dt.to_period('M').nunique()
            cobertura_mensual = (
                pd.DataFrame({'fecha': fechas_opt})
                .assign(
                    periodo_mes=lambda x: x['fecha'].dt.to_period('M'),
                    dia=lambda x: x['fecha'].dt.date,
                    dias_mes=lambda x: x['fecha'].dt.days_in_month
                )
                .groupby('periodo_mes')
                .agg(dias_observados=('dia', 'nunique'), dias_mes=('dias_mes', 'first'))
            )
            meses_incompletos = cobertura_mensual[
                cobertura_mensual['dias_observados'] < cobertura_mensual['dias_mes']
            ]
            col_avisos_acciones.caption('Costes regulados aplicados: 2026')
            if periodos_analizados < 12:
                col_avisos_acciones.warning(
                    f'Optimización basada en {periodos_analizados} mes(es). '
                    'El resultado puede no representar la estacionalidad anual.',
                    icon='⚠️'
                )
            elif periodos_analizados == 12:
                col_avisos_acciones.success('Periodo recomendado: 12 meses analizados.')
            else:
                col_avisos_acciones.info(
                    f'Optimización basada en {periodos_analizados} meses.'
                )
            if not meses_incompletos.empty:
                etiquetas_incompletas = ', '.join(
                    str(periodo) for periodo in meses_incompletos.index
                )
                col_avisos_acciones.warning(
                    'Meses parciales (coste de potencia prorrateado por días): '
                    f'{etiquetas_incompletas}.',
                    icon='⚠️'
                )

            año_opt = 2026
            pyc_tp_opt = pyc_tp[año_opt][tarifa]
            tepp_opt = {
                k: v * coef_excesos
                for k, v in tepp123[año_opt][tarifa].items()
            }
            habilitar_opt = True

            # Un mes natural o un ciclo equivalente también se puede verificar.
            if not rango_completo:
                col_avisos_acciones.warning(
                    'Selecciona también la fecha final del rango.',
                    icon='⚠️',
                )
                habilitar_ver = False
            elif not rango_dentro_curva:
                col_avisos_acciones.warning(
                    'El rango de verificación debe estar incluido en las '
                    'fechas disponibles de la curva.',
                    icon='⚠️',
                )
                habilitar_ver = False
            elif dias_rango <= const_verif:
                col_avisos_acciones.info('Es posible verificar.')
                habilitar_ver = True
                pyc_tp_ver = pyc_tp[año_ver][tarifa]
                tepp_ver = {
                    k: v * coef_excesos
                    for k, v in tepp123[año_ver][tarifa].items()
                }
            else:
                col_avisos_acciones.info('Es posible optimizar.')
                habilitar_ver = False
            
        else:
            col_avisos_acciones.error('No es posible ejecutar ninguna acción. El peaje de acceso es 2.0TD', icon='⚠️')
            habilitar_opt = False
            habilitar_ver = False
        
if not potencias_confirmadas:
    habilitar_opt = False
    habilitar_ver = False

identificador_fuente = (
    st.session_state.get("termino_potencia_firma_sips")
    if origen_datos_potencia == "SIPS"
    else st.session_state.get("curva_reactiva_version", 0)
)
contexto_calculo_actual = (
    origen_datos_potencia,
    identificador_fuente,
    str(tarifa),
    bool(modo1),
    bool(fijar_P6),
    str(st.session_state.get("frec")),
    tuple(round(float(pot_con[f"P{i}"]), 6) for i in range(1, 7)),
)
if origen_datos_potencia == "SIPS" and "mes_verificacion_sips" in locals():
    contexto_verificacion_actual = (
        contexto_calculo_actual + ("mes", str(mes_verificacion_sips))
    )
elif (
    origen_datos_potencia == "Curva"
    and "fecha_ini" in locals()
    and "fecha_fin" in locals()
):
    contexto_verificacion_actual = (
        contexto_calculo_actual
        + ("rango", str(fecha_ini), str(fecha_fin))
    )
else:
    contexto_verificacion_actual = None
contexto_resultados = st.session_state.get(
    "termino_potencia_contexto_resultados"
)
hay_resultados_guardados = any(
    clave in st.session_state for clave in CLAVES_RESULTADOS_POTENCIA
)
if hay_resultados_guardados and contexto_resultados != contexto_calculo_actual:
    if invalidar_resultados_potencia():
        col_avisos_acciones.info(
            "Los datos de entrada han cambiado. Se han retirado los "
            "resultados anteriores; ejecuta de nuevo el cálculo."
        )

datos_calculo_disponibles = (
    "df_in" in locals()
    and df_in is not None
    and not df_in.empty
)
if not datos_calculo_disponibles:
    habilitar_opt = False
    habilitar_ver = False

submit_opt = col_avisos_acciones.button(
    "🔄 Calcular optimización", type='primary', use_container_width=True,
    disabled=not habilitar_opt,
)
submit_ver = col_avisos_acciones.button(
    "🔄 Realizar verificación", type='primary', use_container_width=True,
    disabled=not habilitar_ver,
)

resultados = None    

# OPTIMIZACIÓN DE POTENCIA. USADO EN MODO PREMIUM Y MODO DEMO.  
#if submit_opt and st.session_state.df_norm is not None:
#    if p6 < 50 or st.session_state.atr_dfnorm == '2.0':
#        st.warning('Suministro no válido para optimización por excesos', icon='⚠️')
#        st.stop()

#    resultados = calcular_optimizacion(df_in, fijar_P6, tarifa, pot_con, pyc_tp_opt, tepp_opt)
#    st.session_state.resultados_potencia = resultados
# si no recalcula → recupero

# OPTIMIZACIÓN DE POTENCIA. USADO EN MODO PREMIUM Y MODO DEMO.  
if submit_opt:

    # Seguridad: si por lo que sea no hay tarifa válida
    if tarifa == 'Ninguno':
        st.warning('Selecciona/carga el peaje del suministro antes de optimizar', icon='⚠️')
        st.stop()

    # MODO 1: P6 <= 50 → maxímetros
    if modo1:
        if 'df_maximetros' not in st.session_state or st.session_state.df_maximetros is None:
            st.warning('Falta la tabla de maxímetros para optimizar', icon='⚠️')
            st.stop()

    # MODO 2: P6 > 50 → curva de carga
    else:
        if 'df_norm' not in st.session_state or st.session_state.df_norm is None:
            st.warning('Falta la curva de carga para optimizar', icon='⚠️')
            st.stop()

    resultados = calcular_optimizacion(
        df_in,
        fijar_P6,
        tarifa,
        pot_con,
        pyc_tp_opt,
        tepp_opt
    )

    st.session_state.resultados_potencia = resultados
    st.session_state.termino_potencia_contexto_resultados = (
        contexto_calculo_actual
    )


elif (
    datos_calculo_disponibles
    and st.session_state.get("termino_potencia_contexto_resultados")
    == contexto_calculo_actual
    and "resultados_potencia" in st.session_state
):
    resultados = st.session_state.resultados_potencia


# 🔹 si hay resultados → muestro
if resultados is not None:
    df_coste_tp_mes, coste_tp_potcon, coste_tp_potopt, ahorro_opt, ahorro_opt_porc, df_potencias, graf_costes_pot_periodos, graf_pie_peso, coste_potfra_potcon, coste_excesos_potcon, coste_potfra_potopt, coste_excesos_potopt = resultados
    df_potencias = df_potencias.copy()
    def potencia_sin_decimales(valor):
        if isinstance(valor, str):
            valor = valor.replace(".", "").replace(",", ".")
        return formato_numero_es(float(valor), 0)

    for columna in ("P1", "P2", "P3", "P4", "P5", "P6"):
        if columna not in df_potencias:
            continue
        df_potencias[columna] = df_potencias[columna].apply(
            potencia_sin_decimales
        )

    from backend_opt2 import graficar_comparacion_mensual, graficar_gauge_ahorro, graficar_resumen
    graf_costes_potcon = graficar_comparacion_mensual(df_coste_tp_mes)
    graf_ahorro = graficar_gauge_ahorro(ahorro_opt, ahorro_opt_porc)
    graf_resumen = graficar_resumen (coste_potfra_potcon, coste_excesos_potcon, coste_potfra_potopt, coste_excesos_potopt)
    def formatear_tabla_costes_tp_mes(df_coste_tp_mes):
                df = df_coste_tp_mes.copy()

                # Transponer
                df = df.T

                # Renombrar filas
                nombres_filas = {
                    "coste_pot_mes": "Potencia a facturar",
                    "coste_excesos_mes": "Excesos a facturar",
                    "coste_pot_mes_opt": "Potencia optimizada",
                    "coste_excesos_mes_opt": "Excesos optimizados",
                }

                df = df.rename(index=nombres_filas)

                # Formato español: 3.038,49 €
                df_fmt = df.applymap(formato_euros)

                return df_fmt
    df_coste_tp_mes_fmt = formatear_tabla_costes_tp_mes(df_coste_tp_mes)
    if modo1:
        periodo_datos_informe = "Tabla de maxímetros"
        detalle_datos_optimizacion = (
            f"ATR/Peaje: **{tarifa}** · Datos utilizados: **tabla de maxímetros** "
            "· Costes regulados: **2026**"
        )
    else:
        columna_fecha = (
            "fecha_hora" if "fecha_hora" in df_in.columns else "fecha"
        )
        fechas_usadas = pd.to_datetime(
            df_in[columna_fecha], errors="coerce"
        ).dropna()
        if fechas_usadas.empty:
            rango_usado = "no disponible"
        else:
            rango_usado = (
                f"{fechas_usadas.min():%d/%m/%Y} – "
                f"{fechas_usadas.max():%d/%m/%Y}"
            )
        detalle_datos_optimizacion = (
            f"ATR/Peaje: **{tarifa}** · Curva utilizada: **{rango_usado}** "
            "· Costes regulados: **2026**"
        )
        periodo_datos_informe = rango_usado

    # ===============================================================================================================================    
    # INTERFAZ STREAMLIT
    # ===============================================================================================================================    

    with tab_optimizacion:
        
        
        c11, c12= st.columns([.55, .45])
        with c11:
            if modo1:
                st.header('Resultados de la optimización del Término de Potencia para tipos 4 y 5 (=<50kW)', divider = 'rainbow')
            else:
                st.header('Resultados de la optimización del Término de Potencia para tipos 1, 2 y 3 (>50kW)', divider = 'rainbow')
            st.markdown(detalle_datos_optimizacion)
            with st.container(border=True):
                c1, c2, c3 = st.columns([0.25, 0.20, 0.10])
                with c1:
                    st.write("")
                    st.write(graf_ahorro)
                    st.write("") 
                    st.write("")
                    st.subheader('Tabla de potencias y costes Tp')
                    st.dataframe(df_potencias, hide_index=True, use_container_width=True)
                with c2:
                    st.write(graf_resumen)
                with c3:
                    st.metric('Coste PREVISTO (€)', formato_euros(coste_tp_potcon))
                    st.metric('Coste OPTIMIZADO (€)', formato_euros(coste_tp_potopt))
                    st.metric(
                        'AHORRO (€)',
                        formato_euros(ahorro_opt),
                        delta=f'{formato_numero_es(ahorro_opt_porc, 1)} %',
                    )
            st.header('Detalle de optimización por periodos', divider = 'rainbow')  
            with st.container(border=True):
                st.plotly_chart(graf_costes_pot_periodos, use_container_width=True)
        with c12:
            st.header('Detalle de costes mensuales (€)', divider = 'rainbow')
            with st.container(border=True):
                st.write(graf_costes_potcon)
                st.subheader('Tabla mensual de detalle de costes')
                st.dataframe(df_coste_tp_mes_fmt, use_container_width=True)
        
        #c11, c12= st.columns([.55, .45])
        #with c11:
            
        #with c12:
            

    with tab_informe:
        st.subheader("Informes", divider="rainbow")
        col_titulo, col_generar_informe = st.columns([0.34, 0.66])
        clave_cups_informe = "opt2_informe_cups"
        st.session_state.setdefault(clave_cups_informe, "")
        if origen_datos_potencia == "SIPS":
            sips_informe = st.session_state.get("sips_termino_potencia") or {}
            cups_sips_informe = str(
                (sips_informe.get("metadatos") or {}).get("cups", "") or ""
            ).strip()
            if (
                cups_sips_informe
                and st.session_state.get("opt2_cups_sips_autocargado")
                != cups_sips_informe
            ):
                st.session_state[clave_cups_informe] = cups_sips_informe
                st.session_state.opt2_cups_sips_autocargado = cups_sips_informe
        with col_titulo:
            st.selectbox(
                'Tipo de informe disponible',
                ['Informe de optimización'],
                disabled=True,
                help=(
                    'La verificación ya dispone de una pestaña y estado propios. '
                    'Su plantilla documental se incorporará cuando se defina su contenido.'
                )
            )
            st.caption(
                "Completa los datos del cliente y del realizador. "
                "La cabecera sigue el esquema común de epowerapp."
            )
            with st.container(border=True):
                st.markdown("#### Datos del cliente y del suministro")
                col_cliente, col_nif = st.columns([0.68, 0.32])
                cliente = col_cliente.text_input(
                    "Cliente / Razón social", key="opt2_informe_cliente"
                )
                nif = col_nif.text_input(
                    "NIF / CIF", key="opt2_informe_nif"
                )
                direccion = st.text_input(
                    "Dirección", key="opt2_informe_direccion"
                )
                col_cups, col_atr = st.columns([0.68, 0.32])
                cups = col_cups.text_input(
                    "CUPS", key=clave_cups_informe
                )
                col_atr.text_input(
                    "ATR", value=str(tarifa), disabled=True,
                    key="opt2_informe_atr",
                )

            with st.container(border=True):
                st.markdown("#### Datos del informe")
                titulo = st.text_input(
                    "Título del informe",
                    "Informe de optimización de potencias",
                )
                subtitulo = st.text_input("Subtítulo (opcional)", "")
                col_autor, col_fecha = st.columns([0.60, 0.40])
                realizado_por = col_autor.text_input(
                    "Realizado por", key="opt2_informe_realizado_por"
                )
                fecha_realizacion = col_fecha.text_input(
                    "Fecha de realización",
                    value=pd.Timestamp.today().strftime("%d/%m/%Y"),
                    key="opt2_informe_fecha_realizacion",
                )
                objeto_informe = st.text_input(
                    "Objeto del informe",
                    value=(
                        "Analizar y optimizar las potencias contratadas del "
                        "suministro."
                    ),
                    key="opt2_informe_objeto",
                )

            with st.container(border=True):
                st.markdown("#### Personalización")
                logo_file = st.file_uploader(
                    "Logo para el informe",
                    type=["png", "jpg", "jpeg"],
                    accept_multiple_files=False,
                    key="opt2_informe_logo",
                )
                if logo_file is not None:
                    st.image(logo_file, width=180)

        col_generar_informe.markdown("#### Generar informe")
        col_generar_informe.caption(
            "Prepara la vista previa y descarga después el formato necesario."
        )

        logo_bytes = logo_file.getvalue() if logo_file is not None else b""
        firma = hashlib.sha256()
        firma.update(b"informe-potencia-v2")
        firma.update(
            repr((
                coste_tp_potcon,
                coste_tp_potopt,
                ahorro_opt,
                ahorro_opt_porc,
                titulo,
                subtitulo,
                realizado_por,
                cliente,
                nif,
                direccion,
                cups,
                fecha_realizacion,
                objeto_informe,
                tarifa,
                periodo_datos_informe,
            )).encode("utf-8")
        )
        firma.update(
            pd.util.hash_pandas_object(
                df_potencias, index=True
            ).values.tobytes()
        )
        firma.update(logo_bytes)
        firma_informe = firma.hexdigest()

        if col_generar_informe.button(
            "Preparar informe", type="primary", use_container_width=True
        ):
            with st.spinner(
                "Preparando vista previa y gráficos..."
            ):
                logo_path = None
                try:
                    if logo_file is not None:
                        suffix = pathlib.Path(logo_file.name).suffix
                        with tempfile.NamedTemporaryFile(
                            delete=False, suffix=suffix
                        ) as tmp:
                            tmp.write(logo_bytes)
                            logo_path = tmp.name
                    preparado = preparar_informe(
                        graf_costes_potcon=graf_costes_potcon,
                        graf_resumen=graf_resumen,
                        coste_tp_potcon=coste_tp_potcon,
                        coste_tp_potopt=coste_tp_potopt,
                        ahorro_opt=ahorro_opt,
                        ahorro_opt_porc=ahorro_opt_porc,
                        df_potencias=df_potencias,
                        graf_ahorro=graf_ahorro,
                        graf_costes_pot_periodos=graf_costes_pot_periodos,
                        logo_path=logo_path,
                        titulo=titulo,
                        subtitulo=subtitulo,
                        cliente=cliente,
                        nif=nif,
                        direccion=direccion,
                        cups=cups,
                        peaje=tarifa,
                        periodo_datos=periodo_datos_informe,
                        realizado_por=realizado_por,
                        fecha_realizacion=fecha_realizacion,
                        objeto=objeto_informe,
                        template_path="templates/informe.html",
                    )
                    st.session_state["opt2_informe_preparado"] = {
                        "firma": firma_informe,
                        "preparado": preparado,
                        "formatos": {"html": preparado["html"]},
                    }
                except Exception as e:
                    col_generar_informe.error(
                        f"Error al preparar el informe: {e}"
                    )
                finally:
                    if logo_path:
                        pathlib.Path(logo_path).unlink(missing_ok=True)

        informe_sesion = st.session_state.get("opt2_informe_preparado")
        informe_vigente = (
            informe_sesion
            if informe_sesion
            and informe_sesion.get("firma") == firma_informe
            else None
        )
        if informe_sesion and informe_vigente is None:
            col_generar_informe.info(
                "Los datos han cambiado. Prepara de nuevo el informe para "
                "actualizarlo."
            )

        if informe_vigente:
            col_generar_informe.success(
                "✅ Informe preparado y conservado durante esta sesión"
            )
            formatos = informe_vigente["formatos"]
            partes_nombre_informe = [
                "Informe de optimización de potencias",
                str(cliente or "").strip(),
                str(cups or "").strip(),
                pd.Timestamp.today().strftime("%d-%m-%Y"),
            ]
            nombre_base_informe = "_".join(
                parte for parte in partes_nombre_informe if parte
            )
            nombre_base_informe = re.sub(
                r'[<>:"/\\|?*\x00-\x1f]+',
                "_",
                nombre_base_informe,
            )
            nombre_base_informe = re.sub(
                r"\s+", "_", nombre_base_informe
            )
            nombre_base_informe = re.sub(
                r"_+", "_", nombre_base_informe
            ).strip("._")
            col1, col2, col3 = col_generar_informe.columns(3)
            with col1:
                if "pdf" not in formatos and st.button(
                    "Generar PDF", use_container_width=True
                ):
                    with st.spinner("Generando PDF..."):
                        formatos["pdf"] = generar_formato_informe(
                            informe_vigente["preparado"], "pdf"
                        )
                if "pdf" in formatos:
                    st.download_button(
                        "⬇️ Descargar PDF",
                        formatos["pdf"],
                        f"{nombre_base_informe}.pdf",
                        "application/pdf",
                        use_container_width=True,
                    )
            with col2:
                if "docx" not in formatos and st.button(
                    "Generar Word", use_container_width=True
                ):
                    with st.spinner("Generando Word..."):
                        formatos["docx"] = generar_formato_informe(
                            informe_vigente["preparado"], "docx"
                        )
                if "docx" in formatos:
                    st.download_button(
                        "⬇️ Descargar Word",
                        formatos["docx"],
                        f"{nombre_base_informe}.docx",
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document",
                        use_container_width=True,
                    )
            with col3:
                st.download_button(
                    "⬇️ Descargar HTML",
                    formatos["html"].encode("utf-8"),
                    f"{nombre_base_informe}.html",
                    "text/html",
                    use_container_width=True,
                )

            with col_generar_informe.expander("👁️ Vista previa HTML"):
                st.components.v1.html(
                    formatos["html"], height=700, scrolling=True
                )


if resultados is None:
    with tab_optimizacion:
        st.info('Calcula una optimización para mostrar sus resultados.')
    with tab_informe:
        st.info(
            'El informe de optimización estará disponible después de realizar '
            'el cálculo.'
        )

# VERIFICACIÓN DE EXCESOS. NO SE USA EN MODO DEMO
if submit_ver and origen_datos_potencia == "SIPS":
    (
        coste_potfra_potcon,
        coste_excesos_potcon,
        coste_tp_potcon,
        df_coste_potfra_potcon,
        df_coste_excesos_potcon,
    ) = calcular_costes(
        df_verificacion_sips, tarifa, pyc_tp_ver, tepp_ver, meses, pot_con
    )

    df_pot_mes = pd.DataFrame(
        [df_coste_potfra_potcon.sum(axis=0)],
        index=["Potencia contratada"],
    )
    df_exc_mes = pd.DataFrame(
        [df_coste_excesos_potcon.sum(axis=0)],
        index=["Excesos"],
    )
    df_pot_mes["Total (€)"] = df_pot_mes.sum(axis=1)
    df_exc_mes["Total (€)"] = df_exc_mes.sum(axis=1)
    df_coste = pd.concat([df_pot_mes, df_exc_mes]).reset_index()
    df_coste = df_coste.rename(columns={"index": "Tipo coste"})
    columnas_numericas = df_coste.select_dtypes(include="number").columns
    df_coste[columnas_numericas] = df_coste[columnas_numericas].applymap(
        lambda valor: formato_numero_es(valor, 2)
    )

    filas_detalle_verificacion = []
    for _, fila_maximetros in df_verificacion_sips.iterrows():
        periodo_mes = str(fila_maximetros["periodo_mes"])
        dias_aplicados = int(
            pd.to_numeric(
                fila_maximetros.get("dias_facturacion"), errors="coerce"
            )
            if pd.notna(
                pd.to_numeric(
                    fila_maximetros.get("dias_facturacion"), errors="coerce"
                )
            )
            else pd.Period(periodo_mes, freq="M").days_in_month
        )
        for periodo in pot_con:
            maximetro = float(fila_maximetros.get(periodo, 0.0) or 0.0)
            potencia = float(pot_con[periodo])
            exceso_kw = max(maximetro - potencia, 0.0)
            tepp_periodo = float(tepp_ver.get(periodo) or 0.0)
            filas_detalle_verificacion.append({
                "Mes": periodo_mes,
                "Periodo": periodo,
                "Potencia contratada (kW)": potencia,
                "Maxímetro (kW)": maximetro,
                "Exceso (kW)": exceso_kw,
                "TEPp (€/kW día)": tepp_periodo,
                "Días aplicados": dias_aplicados,
                "Potencia (€)": float(
                    df_coste_potfra_potcon.at[periodo_mes, periodo]
                ),
                "Excesos (€)": float(
                    df_coste_excesos_potcon.at[periodo_mes, periodo]
                ),
            })
    df_detalle_verificacion = pd.DataFrame(filas_detalle_verificacion)

    df_pie = pd.DataFrame({
        "Tipo coste": ["Potencia contratada", "Excesos"],
        "Coste (€)": [coste_potfra_potcon, coste_excesos_potcon],
    })
    fig_pie = px.pie(
        df_pie, names="Tipo coste", values="Coste (€)",
        title="Distribución del coste del término de potencia", hole=0.35,
    )
    fig_pie.update_traces(
        textposition="inside", textinfo="percent+label",
        hovertemplate="%{label}<br>%{value:,.2f} €<extra></extra>",
    )

    periodos_grafico = list(pot_con)
    fila_grafico = df_verificacion_sips.iloc[0]
    fig_detalle_demanda = go.Figure()
    fig_detalle_demanda.add_bar(
        x=periodos_grafico,
        y=[float(fila_grafico.get(p, 0.0) or 0.0) for p in periodos_grafico],
        name="Maxímetro",
        marker_color="#f59e0b",
    )
    fig_detalle_demanda.add_bar(
        x=periodos_grafico,
        y=[float(pot_con[p]) for p in periodos_grafico],
        name="Potencia contratada",
        marker_color="#2563eb",
    )
    fig_detalle_demanda = aplicar_estilo(fig_detalle_demanda)
    fig_detalle_demanda.update_layout(
        title="Maxímetros y potencias contratadas",
        barmode="group",
        xaxis_title="Periodo",
        yaxis_title="kW",
    )

    etiqueta_mes_sips = (
        f"{meses[int(mes_verificacion_sips[5:7]) - 1]} "
        f"{mes_verificacion_sips[:4]}"
    )
    st.session_state.resultados_verificacion_potencia = {
        "contexto": contexto_verificacion_actual,
        "modo": "maximetros_sips",
        "periodo_texto": etiqueta_mes_sips,
        "df_coste": df_coste,
        "df_pot_mes": df_pot_mes,
        "df_detalle": df_detalle_verificacion,
        "fig_pie": fig_pie,
        "fig_detalle_demanda": fig_detalle_demanda,
        "coste_excesos": coste_excesos_potcon,
        "factores_prorrateo_excesos": None,
        "potencias": pot_con.copy(),
    }
    st.session_state.termino_potencia_contexto_resultados = (
        contexto_calculo_actual
    )

if (
    submit_ver
    and origen_datos_potencia == "Curva"
    and st.session_state.df_norm is not None
):
        fechas_df_verificacion = pd.to_datetime(
            df_in['fecha_hora'], errors='coerce'
        )
        df_verificacion = df_in.loc[
            (fechas_df_verificacion.dt.date >= fecha_ini)
            & (fechas_df_verificacion.dt.date <= fecha_fin)
        ].copy()
        if df_verificacion.empty:
            st.error('No hay datos en el rango seleccionado para verificar.')
            st.stop()
        coste_potfra_potcon, coste_excesos_potcon, coste_tp_potcon, df_coste_potfra_potcon, df_coste_excesos_potcon = calcular_costes(df_verificacion, tarifa, pyc_tp_ver, tepp_ver, meses, pot_con)
        df_excesos_brutos_verificacion = df_coste_excesos_potcon.copy()
        df_coste_excesos_potcon, factores_prorrateo_excesos = (
            prorratear_excesos_ciclo_tipo_123(
                df_coste_excesos_potcon,
                df_verificacion,
                pot_con.get("P6", 0.0),
            )
        )
        coste_excesos_potcon = float(df_coste_excesos_potcon.to_numpy().sum())
        coste_tp_potcon = round(coste_potfra_potcon + coste_excesos_potcon, 2)

        filas_detalle_verificacion = []
        for periodo_mes in df_coste_potfra_potcon.index:
            for periodo in pot_con:
                coste_potencia = float(
                    df_coste_potfra_potcon.at[periodo_mes, periodo]
                )
                coste_exceso_bruto = float(
                    df_excesos_brutos_verificacion.at[periodo_mes, periodo]
                )
                coste_exceso = float(
                    df_coste_excesos_potcon.at[periodo_mes, periodo]
                )
                potencia = float(pot_con[periodo])
                precio_potencia = float(pyc_tp_ver[periodo])
                precio_exceso = float(tepp_ver[periodo])
                denominador_potencia = potencia * precio_potencia
                prorrata = (
                    coste_potencia * 12 / denominador_potencia
                    if denominador_potencia else 0.0
                )
                datos_prorrateo = factores_prorrateo_excesos.loc[periodo_mes]
                mascara_detalle = (
                    pd.to_datetime(df_verificacion['fecha_hora'], errors='coerce')
                    .dt.to_period('M').astype(str).eq(str(periodo_mes))
                    & df_verificacion['periodo'].eq(periodo)
                )
                potencias_intervalo = pd.to_numeric(
                    df_verificacion.loc[mascara_detalle, 'potencia'],
                    errors='coerce',
                ).dropna()
                maximetro = (
                    float(potencias_intervalo.max())
                    if not potencias_intervalo.empty else 0.0
                )
                excesos_intervalo = (
                    potencias_intervalo - potencia
                ).clip(lower=0)
                suma_excesos_cuadrado = float((excesos_intervalo ** 2).sum())
                raiz_excesos = math.sqrt(suma_excesos_cuadrado)
                filas_detalle_verificacion.append({
                    'Mes': str(periodo_mes),
                    'Periodo': periodo,
                    'Potencia contratada (kW)': potencia,
                    'Maxímetro (kW)': maximetro,
                    'Precio potencia (€/kW año)': precio_potencia,
                    'Prorrata mensual': prorrata,
                    'Potencia (€)': coste_potencia,
                    'N.º sobrepasamientos': int(excesos_intervalo.gt(0).sum()),
                    'Σ excesos² (kW²)': suma_excesos_cuadrado,
                    'Raíz Σ excesos² (kW)': raiz_excesos,
                    'TEPp (€/kW)': precio_exceso,
                    'Excesos brutos (€)': coste_exceso_bruto,
                    'Días ciclo': int(datos_prorrateo['Días ciclo']),
                    'Días mes': int(datos_prorrateo['Días mes']),
                    'Factor prorrateo': float(datos_prorrateo['Factor prorrateo']),
                    'Excesos (€)': coste_exceso,
                    'Total (€)': coste_potencia + coste_exceso,
                })
        df_detalle_verificacion = pd.DataFrame(filas_detalle_verificacion)

        df_pot_mes = pd.DataFrame(
            [df_coste_potfra_potcon.sum(axis=0)],
            index=['Potencia contratada'],
        )
        df_exc_mes = pd.DataFrame(
            [df_coste_excesos_potcon.sum(axis=0)],
            index=['Excesos'],
        )
        df_pot_mes['Total (€)'] = df_pot_mes.sum(axis=1)
        df_exc_mes['Total (€)'] = df_exc_mes.sum(axis=1)


        df_coste = pd.concat([df_pot_mes, df_exc_mes])
        df_coste = df_coste.reset_index()
        df_coste = df_coste.rename(columns={'index': 'Tipo coste'})
        cols_numericas = df_coste.select_dtypes(include='number').columns
        df_coste[cols_numericas] = df_coste[cols_numericas].applymap(
            lambda valor: formato_numero_es(valor, 2)
        )

        fecha_inicio = df_verificacion["fecha_hora"].min().strftime("%d.%m.%Y")
        fecha_final = df_verificacion["fecha_hora"].max().strftime("%d.%m.%Y")

        df_pie = pd.DataFrame({
            'Tipo coste': ['Potencia contratada', 'Excesos'],
            'Coste (€)': [
                df_coste_potfra_potcon.to_numpy().sum(),
                df_coste_excesos_potcon.to_numpy().sum()
            ]
        })
        fig_pie = px.pie(
            df_pie,
            names='Tipo coste',
            values='Coste (€)',
            title='Distribución del coste del término de potencia',
            hole=0.35  # donut elegante (opcional)
        )
        fig_pie.update_traces(
            textposition='inside',
            textinfo='percent+label',
            hovertemplate='%{label}<br>%{value:,.2f} €<extra></extra>'
        )



        orden_periodos = [f'P{i}' for i in range(1, 7)]
        periodos_presentes = set(df_verificacion['periodo'].dropna().unique())
        orden_visual = [p for p in orden_periodos if p in periodos_presentes]

        fig_detalle_demanda = make_subplots(
            rows=len(orden_visual),
            cols=1,
            shared_xaxes=True,
            subplot_titles=orden_visual,
            vertical_spacing=0.07
        )

        fecha_min = df_verificacion['fecha_hora'].min()
        fecha_max = df_verificacion['fecha_hora'].max()

        def escala_y_periodo(valor_maximo):
            objetivo = max(float(valor_maximo) * 1.08, 1.0)
            paso_bruto = objetivo / 5
            magnitud = 10 ** math.floor(math.log10(paso_bruto))
            proporcion = paso_bruto / magnitud
            factor = next(
                candidato
                for candidato in (1, 2, 5, 10)
                if proporcion <= candidato
            )
            paso = factor * magnitud
            limite = math.ceil(objetivo / paso) * paso
            return limite, paso
        
        for fila, periodo in enumerate(orden_visual, start=1):
            df_p = df_verificacion[df_verificacion['periodo'] == periodo]
            color_periodo = colores_periodo[periodo]
            demanda_max_periodo = pd.to_numeric(
                df_p['potencia'], errors='coerce'
            ).max()
            valor_max_periodo = max(
                float(demanda_max_periodo)
                if pd.notna(demanda_max_periodo) else 0.0,
                float(pot_con[periodo]),
            )
            limite_superior, paso_eje = escala_y_periodo(
                valor_max_periodo
            )

            fig_detalle_demanda.add_trace(
                go.Bar(
                    x=df_p['fecha_hora'],
                    y=df_p['potencia'],
                    marker_color=color_periodo,
                    name=periodo,
                    legendgroup=periodo,
                    hovertemplate=(
                        f'<b>{periodo}</b><br>'
                        'Fecha: %{x|%d/%m/%Y %H:%M}<br>'
                        'Demanda: %{y:,.2f} kW<extra></extra>'
                    )
                ),
                row=fila,
                col=1
            )

            fig_detalle_demanda.update_yaxes(
                title_text='kW',
                range=[0, limite_superior],
                dtick=paso_eje,
                showgrid=True,
                gridwidth=1,
                gridcolor='rgba(128, 128, 128, 0.35)',
                row=fila,
                col=1,
            )

            fig_detalle_demanda.add_trace(
                go.Scatter(
                    x=[fecha_min, fecha_max],
                    y=[pot_con[periodo], pot_con[periodo]],
                    mode='lines',
                    line=dict(
                        color=color_periodo,
                        dash='dash',
                        width=2
                    ),
                    name=periodo,           # mismo nombre
                    legendgroup=periodo,     # mismo grupo → mismo color
                    showlegend=False
                ),
                row=fila,
                col=1
            )

        fig_detalle_demanda = aplicar_estilo(fig_detalle_demanda)
        fig_detalle_demanda.update_layout(
            title='Demanda cuartohoraria vs Potencia contratada por periodo',
            height=320 * len(orden_visual),
            legend_title_text='Periodo',
            bargap=0,
            margin=dict(t=100, b=70)
        )
        st.session_state.resultados_verificacion_potencia = {
            'contexto': contexto_verificacion_actual,
            'fecha_inicio': fecha_inicio,
            'fecha_final': fecha_final,
            'df_coste': df_coste,
            'df_pot_mes': df_pot_mes,
            'df_detalle': df_detalle_verificacion,
            'fig_pie': fig_pie,
            'fig_detalle_demanda': fig_detalle_demanda,
            'coste_excesos': coste_excesos_potcon,
            'factores_prorrateo_excesos': factores_prorrateo_excesos,
            'potencias': pot_con.copy(),
        }
        st.session_state.termino_potencia_contexto_resultados = (
            contexto_calculo_actual
        )


with tab_verificacion:
    verificacion = st.session_state.get('resultados_verificacion_potencia')
    verificacion_descartada = False
    if (
        verificacion is not None
        and verificacion.get("contexto") != contexto_verificacion_actual
    ):
        st.session_state.pop("resultados_verificacion_potencia", None)
        verificacion = None
        verificacion_descartada = True
    if verificacion is None:
        if verificacion_descartada:
            st.info(
                "El periodo o los datos han cambiado. Realiza de nuevo la "
                "verificación para actualizar sus resultados."
            )
        else:
            st.info('Realiza una verificación para mostrar sus resultados.')
    else:
        if verificacion.get("periodo_texto"):
            st.write(
                f"Mes SIPS verificado: **{verificacion['periodo_texto']}**"
            )
        else:
            st.write(
                f"Datos del {verificacion['fecha_inicio']} al "
                f"{verificacion['fecha_final']}"
            )
        df_potencias_verificacion = pd.DataFrame(
            [verificacion['potencias']],
            index=['Potencia contratada (kW)']
        )
        df_potencias_verificacion.index.name = 'Concepto'
        df_potencias_verificacion = df_potencias_verificacion.applymap(
            lambda valor: formato_numero_es(valor, 2)
        )

        c1, c2 = st.columns([.3,.7])
        with c1:
            st.subheader('Potencias utilizadas en la verificación')
            st.dataframe(
                df_potencias_verificacion,
                use_container_width=True
            )
            st.subheader('Resultado económico')
            tabla_resultado_economico = verificacion['df_coste']

            def resaltar_total_excesos(tabla):
                estilos = pd.DataFrame(
                    '', index=tabla.index, columns=tabla.columns
                )
                columnas_total = [
                    columna for columna in tabla.columns
                    if str(columna).startswith('Total')
                ]
                if 'Tipo coste' in tabla.columns and columnas_total:
                    filas_excesos = tabla['Tipo coste'].eq('Excesos')
                    estilos.loc[filas_excesos, columnas_total[0]] = (
                        'background-color: #f59e0b; color: #111827; '
                        'font-weight: 700;'
                    )
                return estilos

            st.dataframe(
                tabla_resultado_economico.style.apply(
                    resaltar_total_excesos, axis=None
                ),
                hide_index=True,
                use_container_width=True
            )
            st.subheader('Justificación de excesos')
            df_detalle_verificacion = verificacion.get('df_detalle')
            if verificacion.get("modo") == "maximetros_sips":
                columnas_excesos = [
                    'Mes', 'Periodo', 'Potencia contratada (kW)',
                    'Maxímetro (kW)', 'Exceso (kW)',
                    'TEPp (€/kW día)', 'Días aplicados',
                    'Potencia (€)', 'Excesos (€)',
                ]
            else:
                columnas_excesos = [
                    'Mes',
                    'Periodo',
                    'Maxímetro (kW)',
                    'N.º sobrepasamientos',
                    'Σ excesos² (kW²)',
                    'Raíz Σ excesos² (kW)',
                    'TEPp (€/kW)',
                    'Excesos brutos (€)',
                    'Días ciclo',
                    'Días mes',
                    'Factor prorrateo',
                    'Excesos (€)',
                ]
            if (
                df_detalle_verificacion is None
                or not set(columnas_excesos).issubset(
                    df_detalle_verificacion.columns
                )
            ):
                st.info(
                    'Pulsa de nuevo «Realizar verificación» para generar el '
                    'detalle justificativo de excesos.'
                )
            else:
                st.dataframe(
                    df_detalle_verificacion[columnas_excesos],
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        'Maxímetro (kW)': st.column_config.NumberColumn(
                            format='%.2f kW'
                        ),
                        'Potencia contratada (kW)': st.column_config.NumberColumn(
                            format='%.2f kW'
                        ),
                        'Exceso (kW)': st.column_config.NumberColumn(
                            format='%.2f kW'
                        ),
                        'TEPp (€/kW día)': st.column_config.NumberColumn(
                            format='%.6f'
                        ),
                        'Días aplicados': st.column_config.NumberColumn(
                            format='%d'
                        ),
                        'Σ excesos² (kW²)': st.column_config.NumberColumn(
                            format='%.6f'
                        ),
                        'Raíz Σ excesos² (kW)': st.column_config.NumberColumn(
                            format='%.6f'
                        ),
                        'TEPp (€/kW)': st.column_config.NumberColumn(format='%.6f'),
                        'Excesos brutos (€)': st.column_config.NumberColumn(
                            format='%.2f €'
                        ),
                        'Días ciclo': st.column_config.NumberColumn(format='%d'),
                        'Días mes': st.column_config.NumberColumn(format='%d'),
                        'Factor prorrateo': st.column_config.NumberColumn(
                            format='%.6f'
                        ),
                        'Excesos (€)': st.column_config.NumberColumn(format='%.2f €'),
                    },
                )
                es_verificacion_sips = (
                    verificacion.get("modo") == "maximetros_sips"
                )
                columna_coste_detalle = (
                    'Excesos (€)' if es_verificacion_sips
                    else 'Excesos brutos (€)'
                )
                coste_excesos_sin_prorrateo = float(
                    df_detalle_verificacion[columna_coste_detalle].sum()
                )
                if es_verificacion_sips:
                    st.caption(
                        'Excesos (€) = exceso de maxímetro (kW) × TEPp '
                        '(€/kW día) × días informados por el SIPS.'
                    )
                else:
                    st.caption(
                        '**Coste de los excesos sin prorrateo:** '
                        f'{formato_euros(coste_excesos_sin_prorrateo)}. '
                        'El cálculo de los sobrepasamientos no se modifica; '
                        'el prorrateo se aplica únicamente sobre su coste.'
                    )
                factores_prorrateo = verificacion.get(
                    'factores_prorrateo_excesos'
                )
                if (
                    factores_prorrateo is not None
                    and factores_prorrateo['Prorrateo aplicable'].any()
                ):
                    st.info(
                        'Suministro tipo 1–3 (P6 > 50 kW) con ciclo parcial: '
                        'se aplica al coste bruto de los excesos el factor '
                        'días del ciclo / días naturales del mes.'
                    )
                elif not es_verificacion_sips:
                    st.caption(
                        'Excesos (€) = TEPp × √Σ(demanda − potencia '
                        'contratada)², considerando únicamente los intervalos '
                        'con sobrepasamiento.'
                    )
            st.plotly_chart(verificacion['fig_pie'], use_container_width=True)
            c21,c22,c23 = st.columns(3)
            with c21:
                total_potfra = round(
                    verificacion['df_pot_mes']['Total (€)'].sum(), 2
                )
                st.metric('Potencia facturada €)', formato_euros(total_potfra))
            with c22:
                st.metric(
                    'Excesos facturados €)',
                    formato_euros(verificacion['coste_excesos'])
                )
            with c23:
                total_tp_fra = round(
                    total_potfra + verificacion['coste_excesos'], 2
                )
                st.metric('Total término de potencia €)', formato_euros(total_tp_fra))
        with c2:
            st.plotly_chart(
                verificacion['fig_detalle_demanda'],
                use_container_width=True
            )


with tab_comparacion:
    st.caption(
        'Todos los escenarios se valoran sobre el mismo periodo y con los '
        'costes regulados de 2026.'
    )

    if 'df_in' not in locals() or df_in is None or df_in.empty:
        st.info('Carga una curva o una tabla de maxímetros para comparar.')
    else:
        df_comparacion_base = df_in.copy()
        rango_comparacion = None
        col_entrada, col_metricas, col_resultado = st.columns(
            [0.25, 0.30, 0.45],
            gap='large'
        )

        with col_entrada:
            st.subheader('Datos de entrada', divider='rainbow')
            with st.form('form_comparacion_potencias'):
                if 'fecha_hora' in df_comparacion_base.columns:
                    fechas_disponibles = pd.to_datetime(
                        df_comparacion_base['fecha_hora'], errors='coerce'
                    ).dropna()
                    fecha_min_comparacion = fechas_disponibles.min().date()
                    fecha_max_comparacion = fechas_disponibles.max().date()
                    rango_comparacion = st.date_input(
                        'Rango de fechas de la comparación',
                        value=(fecha_min_comparacion, fecha_max_comparacion),
                        min_value=fecha_min_comparacion,
                        max_value=fecha_max_comparacion,
                        format='DD/MM/YYYY'
                    )

                st.subheader('Potencias alternativas')
                df_potencias_comparacion_ini = pd.DataFrame(
                    {'Potencia (kW)': pot_con}
                )
                df_potencias_comparacion = st.data_editor(
                    df_potencias_comparacion_ini,
                    use_container_width=True,
                    num_rows='fixed'
                )
                submit_comparacion = st.form_submit_button(
                    'Calcular comparación',
                    type='primary',
                    use_container_width=True
                )

        with col_resultado:
            st.subheader('Gráfico comparativo', divider='rainbow')

        with col_metricas:
            st.subheader('Resumen', divider='rainbow')

        if submit_comparacion:
            errores_comparacion = validar_potencias(df_potencias_comparacion)
            if errores_comparacion:
                for error in errores_comparacion:
                    st.error(error)
            else:
                df_periodo_comparacion = df_comparacion_base.copy()
                if rango_comparacion is not None:
                    if not isinstance(rango_comparacion, (tuple, list)) or len(rango_comparacion) != 2:
                        st.error('Selecciona una fecha inicial y una fecha final.')
                        st.stop()
                    inicio_comparacion, fin_comparacion = rango_comparacion
                    fechas_comparacion = pd.to_datetime(
                        df_periodo_comparacion['fecha_hora'], errors='coerce'
                    )
                    df_periodo_comparacion = df_periodo_comparacion.loc[
                        (fechas_comparacion.dt.date >= inicio_comparacion)
                        & (fechas_comparacion.dt.date <= fin_comparacion)
                    ].copy()

                if df_periodo_comparacion.empty:
                    st.error('No hay datos en el rango seleccionado.')
                    st.stop()

                potencias_alternativas = (
                    df_potencias_comparacion['Potencia (kW)']
                    .astype(float)
                    .to_dict()
                )
                escenarios = {
                    'Contratadas': pot_con.copy(),
                }

                resultados_opt_sesion = st.session_state.get(
                    'resultados_potencia'
                )
                if resultados_opt_sesion is not None:
                    tabla_opt = resultados_opt_sesion[5]
                    fila_opt = tabla_opt.loc[
                        tabla_opt['Potencias (kW)'] == 'Optimizadas'
                    ]
                    if not fila_opt.empty:
                        def a_float_es(valor):
                            if isinstance(valor, str):
                                valor = valor.replace('.', '').replace(',', '.')
                            return float(valor)

                        escenarios['Optimizadas'] = {
                            p: a_float_es(fila_opt.iloc[0][p])
                            for p in orden_periodos
                        }

                escenarios['Alternativas'] = potencias_alternativas

                filas_comparacion = []
                for nombre_escenario, potencias_escenario in escenarios.items():
                    coste_potencia, _, _, _, costes_excesos_brutos = calcular_costes(
                        df_periodo_comparacion,
                        tarifa,
                        pyc_tp_opt,
                        tepp_opt,
                        meses,
                        potencias_escenario
                    )
                    costes_excesos_prorrateados, _ = (
                        prorratear_excesos_ciclo_tipo_123(
                            costes_excesos_brutos,
                            df_periodo_comparacion,
                            pot_con.get('P6', 0.0),
                        )
                    )
                    coste_excesos = float(
                        costes_excesos_prorrateados.to_numpy().sum()
                    )
                    coste_total = round(coste_potencia + coste_excesos, 2)
                    filas_comparacion.append({
                        'Escenario': nombre_escenario,
                        **potencias_escenario,
                        'Coste potencia (€)': coste_potencia,
                        'Coste excesos (€)': coste_excesos,
                        'Coste total (€)': coste_total,
                    })

                df_resultado_comparacion = pd.DataFrame(filas_comparacion)
                coste_base = df_resultado_comparacion.loc[
                    df_resultado_comparacion['Escenario'] == 'Contratadas',
                    'Coste total (€)'
                ].iloc[0]
                df_resultado_comparacion['Ahorro vs contratadas (€)'] = (
                    coste_base - df_resultado_comparacion['Coste total (€)']
                )

                df_grafico_comparacion = df_resultado_comparacion.melt(
                    id_vars='Escenario',
                    value_vars=['Coste potencia (€)', 'Coste excesos (€)'],
                    var_name='Concepto',
                    value_name='Coste (€)'
                )
                fig_comparacion = px.bar(
                    df_grafico_comparacion,
                    x='Escenario',
                    y='Coste (€)',
                    color='Concepto',
                    text='Coste (€)',
                    barmode='stack',
                    title='Comparación de costes en el periodo seleccionado',
                    color_discrete_map={
                        'Coste potencia (€)': 'deepskyblue',
                        'Coste excesos (€)': 'blue',
                    }
                )
                fig_comparacion = aplicar_estilo(fig_comparacion)
                fig_comparacion.update_traces(
                    texttemplate='<b>%{y:,.0f} €</b>',
                    textposition='auto',
                    textfont_size=24,
                    cliponaxis=False,
                    hovertemplate=(
                        '<b>%{x}</b><br>'
                        'Coste: %{y:,.2f} €<extra></extra>'
                    )
                )
                fig_comparacion.update_layout(
                    barcornerradius=8,
                    legend_title_text='',
                    height=520,
                    xaxis=dict(
                        tickfont=dict(size=20),
                        title_font=dict(size=20)
                    )
                )

                fila_alternativa_grafico = df_resultado_comparacion.loc[
                    df_resultado_comparacion['Escenario'] == 'Alternativas'
                ].iloc[0]
                coste_alternativo_grafico = fila_alternativa_grafico[
                    'Coste total (€)'
                ]
                ahorro_grafico = coste_base - coste_alternativo_grafico
                porcentaje_grafico = (
                    abs(ahorro_grafico) / coste_base * 100
                    if coste_base else 0
                )
                ahorro_favorable_grafico = ahorro_grafico >= 0
                texto_impacto_grafico = (
                    'Ahorro' if ahorro_favorable_grafico else 'Sobrecoste'
                )
                fondo_impacto_grafico = (
                    '#bbf7d0' if ahorro_favorable_grafico else '#fecaca'
                )
                borde_impacto_grafico = (
                    '#15803d' if ahorro_favorable_grafico else '#dc2626'
                )
                fig_comparacion.add_annotation(
                    x='Alternativas',
                    y=1.02,
                    yref='paper',
                    yanchor='bottom',
                    visible=False,
                    text=(
                        f'<b>{texto_impacto_grafico}</b><br>'
                        f'<b>{formato_euros(abs(ahorro_grafico))} '
                        f'({formato_numero_es(porcentaje_grafico, 1)} %)</b>'
                    ),
                    showarrow=False,
                    bgcolor=fondo_impacto_grafico,
                    bordercolor=borde_impacto_grafico,
                    borderwidth=2,
                    borderpad=8,
                    font=dict(color=borde_impacto_grafico, size=20),
                    align='center'
                )

                st.session_state.resultado_comparacion_potencias = {
                    'tabla': df_resultado_comparacion,
                    'grafico': fig_comparacion,
                    'rango': rango_comparacion,
                }

        comparacion_guardada = st.session_state.get(
            'resultado_comparacion_potencias'
        )
        if comparacion_guardada is not None:
            tabla_comparacion_fmt = comparacion_guardada['tabla'].copy()
            for columna in orden_periodos:
                tabla_comparacion_fmt[columna] = tabla_comparacion_fmt[columna].apply(
                    lambda valor: formato_numero_es(valor, 2)
                )
            for columna in (
                'Coste potencia (€)',
                'Coste excesos (€)',
                'Coste total (€)',
                'Ahorro vs contratadas (€)',
            ):
                tabla_comparacion_fmt[columna] = tabla_comparacion_fmt[columna].apply(
                    formato_euros
                )

            # La tabla horizontal se conserva como fuente; se presenta
            # transpuesta para comparar cada concepto entre escenarios.
            tabla_comparacion_vertical = (
                tabla_comparacion_fmt
                .set_index('Escenario')
                .T
            )

            with col_resultado:
                st.plotly_chart(
                    comparacion_guardada['grafico'],
                    use_container_width=True
                )
                st.subheader('Detalle por escenario')
                st.dataframe(
                    tabla_comparacion_vertical,
                    use_container_width=True
                )

            tabla_metricas = comparacion_guardada['tabla']
            fila_contratada = tabla_metricas.loc[
                tabla_metricas['Escenario'] == 'Contratadas'
            ].iloc[0]
            fila_alternativa = tabla_metricas.loc[
                tabla_metricas['Escenario'] == 'Alternativas'
            ].iloc[0]
            ahorro_alternativa = (
                fila_contratada['Coste total (€)']
                - fila_alternativa['Coste total (€)']
            )
            porcentaje_impacto = (
                abs(ahorro_alternativa)
                / fila_contratada['Coste total (€)']
                * 100
                if fila_contratada['Coste total (€)'] else 0
            )

            with col_metricas:
                hay_ahorro = ahorro_alternativa >= 0
                texto_impacto = (
                    'El ahorro en el TP es de'
                    if hay_ahorro
                    else 'El sobrecoste es de'
                )
                color_impacto = '#15803d' if hay_ahorro else '#dc2626'
                borde_impacto = '#86efac' if hay_ahorro else '#fca5a5'
                fondo_impacto = '#bbf7d0' if hay_ahorro else '#fecaca'
                st.markdown(
                    f'''
                    <div style="
                        width: 100%;
                        box-sizing: border-box;
                        padding: 1rem;
                        margin-bottom: 1rem;
                        border: 1px solid {borde_impacto};
                        border-radius: 0.5rem;
                        background-color: {fondo_impacto};
                        color: {color_impacto};
                        text-align: center;
                    ">
                        <div style="font-size: 1.3rem; font-weight: 600;">
                            {texto_impacto}
                        </div>
                        <div style="font-size: 2.5rem; font-weight: 700;">
                            {formato_euros(abs(ahorro_alternativa))}
                            ({formato_numero_es(porcentaje_impacto, 1)} %)
                        </div>
                    </div>
                    ''',
                    unsafe_allow_html=True
                )

                col_resumen, col_alternativa = st.columns(2, gap='medium')
                with col_resumen:
                    st.markdown(
                        '<div style="font-size: 1.35rem; font-weight: 700;">'
                        'Contratadas</div>',
                        unsafe_allow_html=True
                    )
                    st.metric(
                        'Coste Potencia',
                        formato_euros(fila_contratada['Coste potencia (€)'])
                    )
                    st.metric(
                        'Coste Excesos',
                        formato_euros(fila_contratada['Coste excesos (€)'])
                    )
                    st.metric(
                        'Total TP',
                        formato_euros(fila_contratada['Coste total (€)'])
                    )

                with col_alternativa:
                    st.markdown(
                        '<div style="font-size: 1.35rem; font-weight: 700;">'
                        'Alternativas</div>',
                        unsafe_allow_html=True
                    )
                    st.metric(
                        'Coste Potencia',
                        formato_euros(fila_alternativa['Coste potencia (€)'])
                    )
                    st.metric(
                        'Coste Excesos',
                        formato_euros(fila_alternativa['Coste excesos (€)'])
                    )
                    st.metric(
                        'Total TP',
                        formato_euros(fila_alternativa['Coste total (€)']),
                        delta=(
                            f'{formato_euros(ahorro_alternativa)} '
                            f'({formato_numero_es(porcentaje_impacto, 1)} %)'
                        )
                    )

            with col_entrada:
                rango_guardado = comparacion_guardada.get('rango')
                if (
                    isinstance(rango_guardado, (tuple, list))
                    and len(rango_guardado) == 2
                ):
                    texto_rango = (
                        f'{rango_guardado[0]:%d/%m/%Y} – '
                        f'{rango_guardado[1]:%d/%m/%Y}'
                    )
                else:
                    texto_rango = 'Meses disponibles en la tabla'
                st.info(
                    f'**Periodo valorado:** {texto_rango}\n\n'
                    f'**Escenarios:** {len(tabla_metricas)}\n\n'
                    '**Costes regulados:** 2026'
                )


