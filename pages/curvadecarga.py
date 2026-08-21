import streamlit as st
import numpy as np
import pandas as pd
import io
import base64
import re
from html import escape
from pathlib import Path
from dateutil.relativedelta import relativedelta
from datetime import timedelta
import plotly.express as px
from jinja2 import Environment, FileSystemLoader
from backend_curvadecarga import (
    normalize_curve_simple, detectar_hojas_curva_excel, obtener_datos_contador,
    obtener_suministros_datadis,
    obtener_detalle_contrato_datadis, extraer_potencias_contratadas_datadis,
    obtener_consumo_datadis_cacheado, dataframe_como_archivo_curva,
    completar_periodos_curva, agrupar_curva_horaria,
    analizar_calidad_curva,
    graficar_curva_horaria, graficar_diario_apilado, graficar_mensual_apilado, tabla_mensual_periodos, formatear_tabla_mensual_es, graficar_queso_periodos,
    graficar_media_horaria, graficar_media_horaria_combinada, graficar_boxplot_horario,
    graficar_dem_ver_mensual, graficar_con_gen_mensual,
    graficar_heatmap_dia_hora,
    calcular_patron_horario_boxplot, detectar_consumos_atipicos_horarios,
    resumir_atipicos_por_dia, calcular_kpis_atipicos, mostrar_kpis_atipicos, graficar_top_dias_revisables, graficar_heatmap_alertas, calcular_patron_horario_boxplot, obtener_top_horas_revisables,
    calcular_tabla_excesos_reactiva, calcular_tabla_factor_potencia, estilo_factor_potencia, calcular_tabla_precio_penalizacion_reactiva, calcular_tabla_coste_excesos_reactiva, estilo_coste_penalizacion,
    calcular_tabla_potencia_media_qh,calcular_tabla_coef_k, calcular_tabla_q_condensadores,
    calcular_comparacion, calcular_comparacion_costes,
    preparar_costes_mensuales_rango,
    )
from backend_comun import (
    aplicar_estilo,
    formatear_tabla_consumos,
    formatear_columnas_tabla,
)
from formato_es import formato_euros, formato_kwh, formato_numero_es



from utilidades import (
    actualizar_df_index_por_zona,
    generar_menu,
    init_app,
    init_app_index,
)
from backend_telemindex import (
    añadir_costes_curva,
    construir_df_curva_sheets,
    evol_mensual,
)

if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')

generar_menu()

VERSION_CURVA_UI = 2

if 'zona_periodos_cdc' not in st.session_state:
    st.session_state.zona_periodos_cdc = 'peninsula'

# ===============================
#  Interfaz principal
# ===============================

hoja_curva_excel = None


def guardar_credenciales_axon_sesion():
    """Conserva las credenciales de Axon solo en la sesión de Streamlit."""
    st.session_state.axon_usuario_sesion = st.session_state.get(
        "_axon_usuario_input", ""
    )
    st.session_state.axon_password_sesion = st.session_state.get(
        "_axon_password_input", ""
    )


def limpiar_curva_cargada():
    """Elimina la curva y los resultados calculados en esta sesión."""
    claves_curva = (
        "df_norm",
        "df_norm_h",
        "df_in",
        "csv_bytes_norm",
        "csv_bytes_h",
        "lista_ficheros",
        "consumo_total",
        "reactiva_total",
        "vertido_total",
        "consumo_neto",
        "vertido_neto",
        "rango_curvadecarga",
        "rango_fechas_comparativa",
        "rango_fechas_comparativa_guardado",
        "_rango_fechas_comparativa",
        "precios_mensuales",
        "df_axon_raw",
        "frec_axon_raw",
        "df_datadis_raw",
        "frec_datadis_raw",
        "suministros_datadis",
        "reactiva_base_cache",
        "reactiva_compensacion",
        "curva_reactiva_version",
        "informe_reactiva_html",
        "diagnosticos_curva",
    )
    for clave in claves_curva:
        st.session_state.pop(clave, None)
    st.session_state.curva_uploader_version = (
        st.session_state.get("curva_uploader_version", 0) + 1
    )


tab_curva, tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    [
        "Curva",
        "Resumen",
        "Perfiles Horarios",
        "Autoconsumo",
        "Comparaciones",
        "Reactiva",
        "Informe",
    ]
)

with tab_curva:
    col_curva_entrada, col_curva_vista, col_curva_info = st.columns(
        [0.27, 0.46, 0.27],
        gap="large",
    )

    with col_curva_entrada:
        st.subheader("Datos de entrada", divider="rainbow")
        st.caption(
            "Lee CSV/Excel, detecta columnas y normaliza las horas al rango "
            "0–23 del mismo día."
        )

        if not st.session_state.get('usuario_autenticado', False):
            st.warning(
                "🔒 Este módulo es solo para usuarios premium. "
                "Se utilizará un fichero de ejemplo."
            )
            origen_curva = "Archivo CSV/Excel"
            uploaded = "curvas/qh anual demo.csv"
            atr_dfnorm = "3.0"
        else:
            origen_curva = st.selectbox(
                "Origen de la curva",
                ("Archivo CSV/Excel", "Axon", "Datadis"),
                index=0,
            )
            uploaded = None
            if origen_curva == "Archivo CSV/Excel":
                uploaded = st.file_uploader(
                    "📂 Sube uno o varios archivos CSV o Excel",
                    type=["csv", "xlsx"],
                    accept_multiple_files=True,
                    key=(
                        "curva_archivos_"
                        f"{st.session_state.get('curva_uploader_version', 0)}"
                    ),
                )
                if uploaded:
                    archivos_excel = [
                        archivo for archivo in uploaded
                        if archivo.name.lower().endswith(".xlsx")
                    ]
                    hojas_por_archivo = []
                    for archivo_excel in archivos_excel:
                        try:
                            hojas_por_archivo.append(
                                set(detectar_hojas_curva_excel(archivo_excel))
                            )
                        except Exception:
                            hojas_por_archivo.append(set())

                    if hojas_por_archivo:
                        hojas_comunes = set.intersection(*hojas_por_archivo)
                        opciones_hoja = [
                            hoja for hoja in ("Cuarto horarias", "Horarias")
                            if hoja in hojas_comunes
                        ]
                        if len(opciones_hoja) > 1:
                            hoja_curva_excel = st.radio(
                                "Curva de los Excel",
                                opciones_hoja,
                                format_func=lambda hoja: {
                                    "Cuarto horarias": "Cuarto horaria",
                                    "Horarias": "Horaria",
                                }[hoja],
                                horizontal=True,
                            )
                        elif len(opciones_hoja) == 1:
                            hoja_curva_excel = opciones_hoja[0]
            elif origen_curva == "Axon":
                # Las claves "sesión" no pertenecen a widgets, por lo que
                # sobreviven al cambiar de origen o de página. Session State
                # es individual por conexión y no se comparte entre usuarios.
                st.session_state.setdefault(
                    "_axon_usuario_input",
                    st.session_state.get("axon_usuario_sesion", ""),
                )
                st.session_state.setdefault(
                    "_axon_password_input",
                    st.session_state.get("axon_password_sesion", ""),
                )
                usuario_axon = st.text_input(
                    "Usuario Axon",
                    key="_axon_usuario_input",
                    on_change=guardar_credenciales_axon_sesion,
                )
                password_axon = st.text_input(
                    "Contraseña Axon",
                    type="password",
                    key="_axon_password_input",
                    on_change=guardar_credenciales_axon_sesion,
                )
                cups_axon = st.text_input("CUPS")
                hoy_axon = pd.Timestamp.today().date()
                rango_axon = st.date_input(
                    "Periodo de la curva",
                    value=(
                        hoy_axon - timedelta(days=30),
                        hoy_axon - timedelta(days=1),
                    ),
                    max_value=hoy_axon,
                    format="DD/MM/YYYY",
                )
                tipo_curva_axon = st.selectbox(
                    "Tipo de curva",
                    ("TM2", "TM1"),
                    index=0,
                    format_func=lambda valor: {
                        "TM1": "TM1 · Horaria (H)",
                        "TM2": "TM2 · Cuartohoraria (QH)",
                    }[valor],
                )
            else:
                usuario_datadis = st.text_input("Usuario Datadis")
                password_datadis = st.text_input("Contraseña Datadis", type="password")
                acceso_datadis = st.radio(
                    "Acceso", ("Titular", "Autorizado"), horizontal=True
                )
                authorized_nif_datadis = ""
                if acceso_datadis == "Autorizado":
                    authorized_nif_datadis = st.text_input("NIF del titular")

                if st.button(
                    "Consultar suministros",
                    use_container_width=True,
                    key="consultar_suministros_datadis",
                ):
                    try:
                        with st.spinner("Consultando suministros en Datadis…"):
                            st.session_state.suministros_datadis = obtener_suministros_datadis(
                                usuario_datadis,
                                password_datadis,
                                authorized_nif=authorized_nif_datadis,
                            )
                    except Exception as e:
                        st.session_state.pop("suministros_datadis", None)
                        st.error(f"No se pudieron consultar los suministros: {e}")

                suministros_datadis = st.session_state.get("suministros_datadis")
                suministro_datadis = None
                if suministros_datadis is not None and not suministros_datadis.empty:
                    indices_suministros = list(suministros_datadis.index)

                    def etiqueta_suministro(indice):
                        fila = suministros_datadis.loc[indice]
                        cups = str(fila.get("cups", ""))
                        direccion = str(
                            fila.get("address", fila.get("postalCode", "")) or ""
                        ).strip()
                        return f"{cups} · {direccion}" if direccion else cups

                    indice_datadis = st.selectbox(
                        "Suministro",
                        indices_suministros,
                        format_func=etiqueta_suministro,
                    )
                    suministro_datadis = suministros_datadis.loc[indice_datadis].to_dict()
                    st.caption(
                        f"Distribuidora: {suministro_datadis.get('distributorCode', '—')} · "
                        f"Tipo de punto: {suministro_datadis.get('pointType', '—')}"
                    )

                    clave_detalle_datadis = (
                        str(usuario_datadis or "").strip().upper(),
                        str(authorized_nif_datadis or "").strip().upper(),
                        str(suministro_datadis.get("cups", "")).strip().upper(),
                        str(suministro_datadis.get("distributorCode", "")).strip(),
                    )
                    cache_detalles = st.session_state.setdefault(
                        "datadis_detalles_cache", {}
                    )
                    if st.button(
                        "Consultar detalle del contrato",
                        use_container_width=True,
                        key="consultar_detalle_datadis",
                    ):
                        try:
                            detalle_cacheado = cache_detalles.get(clave_detalle_datadis)
                            if detalle_cacheado is None:
                                with st.spinner("Consultando el contrato en Datadis…"):
                                    detalle_cacheado = obtener_detalle_contrato_datadis(
                                        usuario_datadis,
                                        password_datadis,
                                        suministro_datadis,
                                        authorized_nif=authorized_nif_datadis,
                                    )
                                cache_detalles[clave_detalle_datadis] = detalle_cacheado
                            st.session_state.detalle_datadis_actual = detalle_cacheado
                            st.session_state.detalle_datadis_clave = clave_detalle_datadis
                        except Exception as e:
                            st.error(f"No se pudo consultar el detalle: {e}")

                    detalle_datadis = None
                    if st.session_state.get("detalle_datadis_clave") == clave_detalle_datadis:
                        detalle_datadis = st.session_state.get("detalle_datadis_actual")
                    elif clave_detalle_datadis in cache_detalles:
                        detalle_datadis = cache_detalles[clave_detalle_datadis]

                    if detalle_datadis:
                        potencias_datadis = extraer_potencias_contratadas_datadis(
                            detalle_datadis
                        )
                        with st.expander("Detalle del suministro", expanded=True):
                            campos_detalle = {
                                "Tarifa": detalle_datadis.get("codeFare"),
                                "Comercializadora": detalle_datadis.get("marketer"),
                                "Distribuidora": detalle_datadis.get("distributor"),
                                "Tensión": detalle_datadis.get("tension"),
                                "Control de potencia": detalle_datadis.get("modePowerControl"),
                                "Inicio del contrato": detalle_datadis.get("startDate"),
                                "Fin del contrato": detalle_datadis.get("endDate"),
                            }
                            st.dataframe(
                                pd.DataFrame(
                                    [
                                        {"Dato": campo, "Valor": valor}
                                        for campo, valor in campos_detalle.items()
                                        if valor not in (None, "")
                                    ]
                                ),
                                hide_index=True,
                                use_container_width=True,
                            )
                            if potencias_datadis:
                                st.dataframe(
                                    pd.DataFrame(
                                        {
                                            "Periodo": potencias_datadis.keys(),
                                            "Potencia (kW)": potencias_datadis.values(),
                                        }
                                    ),
                                    hide_index=True,
                                    use_container_width=True,
                                )
                                if len(potencias_datadis) == 6:
                                    if st.button(
                                        "Copiar P1–P6 a Optimización de potencia",
                                        use_container_width=True,
                                        key="copiar_potencias_datadis",
                                    ):
                                        st.session_state.df_pot = pd.DataFrame(
                                            {
                                                "Periodo": potencias_datadis.keys(),
                                                "Potencia (kW)": potencias_datadis.values(),
                                            }
                                        ).set_index("Periodo")
                                        st.success(
                                            "Potencias copiadas. Estarán disponibles en "
                                            "Optimización de potencia."
                                        )
                                else:
                                    st.info(
                                        "El contrato no contiene seis potencias; "
                                        "se muestran sin modificar la tabla de optimización."
                                    )

                mes_actual_datadis = pd.Timestamp.today().to_period("M")
                meses_datadis = [
                    str(periodo).replace("-", "/")
                    for periodo in pd.period_range(
                        start="2020-01",
                        end=mes_actual_datadis,
                        freq="M",
                    )
                ]
                mes_anterior_datadis = str(mes_actual_datadis - 1).replace("-", "/")
                indice_mes_defecto = meses_datadis.index(mes_anterior_datadis)
                col_mes_inicio, col_mes_fin = st.columns(2)
                with col_mes_inicio:
                    mes_inicio_datadis = st.selectbox(
                        "Mes inicial",
                        meses_datadis,
                        index=indice_mes_defecto,
                        key="mes_inicio_datadis",
                    )
                with col_mes_fin:
                    mes_fin_datadis = st.selectbox(
                        "Mes final",
                        meses_datadis,
                        index=indice_mes_defecto,
                        key="mes_fin_datadis",
                    )
                st.caption("Datadis recibirá las fechas en formato AAAA/MM.")
                preferir_qh_datadis = st.checkbox(
                    "Intentar curva cuartohoraria (opción avanzada)",
                    value=False,
                    key="preferir_qh_datadis_v2",
                    help=(
                        "Por defecto se solicita curva horaria. Datadis no ofrece "
                        "QH para todos los tipos de punto ni distribuidoras; los "
                        "tipos 4 y 5 se consultan siempre en horario. No se realiza "
                        "fallback automático para evitar consumir otra consulta."
                    ),
                )
            atr_dfnorm = st.selectbox(
                "Selecciona peaje de acceso",
                ("2.0", "3.0", "6.1", "6.2", "6.3", "6.4"),
                index=0,
            )
            opciones_zona_periodos = [
                "peninsula", "baleares", "canarias", "ceuta", "melilla"
            ]
            st.selectbox(
                "Selecciona zona de periodos horarios",
                options=opciones_zona_periodos,
                index=0,
                key="zona_periodos_cdc",
                format_func=lambda zona: {
                    "peninsula": "Península",
                    "baleares": "Baleares",
                    "canarias": "Canarias",
                    "ceuta": "Ceuta",
                    "melilla": "Melilla",
                }[zona],
            )

        normalizar = st.button(
            "Obtener y normalizar curva"
            if origen_curva in {"Axon", "Datadis"}
            else "Normalizar curva de carga",
            type="primary",
            use_container_width=True,
        )
        st.button(
            "🗑️ Eliminar curva y resultados",
            use_container_width=True,
            on_click=limpiar_curva_cargada,
            help=(
                "Elimina la curva cargada y sus cálculos de esta sesión. "
                "No borra preferencias, usuario ni cachés compartidas."
            ),
        )

    with col_curva_vista:
        st.subheader("Vista y normalización", divider="rainbow")

    with col_curva_info:
        st.subheader("Resumen y avisos", divider="rainbow")
        zona_mensajes = st.empty()
        zona_mensajes2 = st.empty()
        zona_mensajes3 = st.empty()


# Inicializa el estado si no existe
if "df_norm" not in st.session_state:
    st.session_state.df_norm = None
if "df_norm_h" not in st.session_state:
    st.session_state.df_norm_h = None
if "df_in" not in st.session_state:
    st.session_state.df_in = None
if 'frec' not in st.session_state:
    st.session_state.frec = 'QH'
if 'fp_obj_min' not in st.session_state:
    st.session_state.fp_obj_min = 0.95
if 'fp_obj_max' not in st.session_state:
    st.session_state.fp_obj_max = 1.00
if 'fp_obj_sel' not in st.session_state:
    st.session_state.fp_obj_sel = 0.98
if 'margen_comp_min' not in st.session_state:
    st.session_state.margen_comp_min = 30 #en %
if "csv_bytes_norm" not in st.session_state:
    st.session_state.csv_bytes_norm = None
if "csv_bytes_h" not in st.session_state:
    st.session_state.csv_bytes_h = None
if "datadis_curvas_cache" not in st.session_state:
    st.session_state.datadis_curvas_cache = {}


if normalizar and origen_curva == "Axon":
    try:
        if not isinstance(rango_axon, (tuple, list)) or len(rango_axon) != 2:
            raise ValueError("Selecciona una fecha inicial y una fecha final.")
        with st.spinner("Conectando con Axon y descargando medidas…"):
            curva_axon, frecuencia_axon = obtener_datos_contador(
                usuario_axon,
                password_axon,
                cups_axon,
                rango_axon[0],
                rango_axon[1],
                tipo_curva_axon,
            )
        st.session_state.df_axon_raw = curva_axon
        st.session_state.frec_axon_raw = frecuencia_axon
        archivo_axon = io.BytesIO(
            curva_axon.to_csv(index=False, sep=";").encode("utf-8")
        )
        archivo_axon.name = f"axon_{tipo_curva_axon.lower()}.csv"
        uploaded = archivo_axon
        zona_mensajes.success(
            f"✅ Curva de Axon obtenida: "
            f"{formato_numero_es(len(curva_axon))} registros."
        )
        zona_mensajes2.info(f"Resolución recibida: {frecuencia_axon}.")
    except Exception as e:
        st.session_state.pop("df_axon_raw", None)
        st.session_state.pop("frec_axon_raw", None)
        zona_mensajes.error(f"❌ Error al obtener la curva de Axon: {e}")


if normalizar and origen_curva == "Datadis":
    try:
        if suministro_datadis is None:
            raise ValueError("Consulta y selecciona primero un suministro.")
        fecha_inicio_datadis = pd.Timestamp(
            f"{mes_inicio_datadis.replace('/', '-')}-01"
        )
        fecha_fin_datadis = pd.Timestamp(
            f"{mes_fin_datadis.replace('/', '-')}-01"
        ) + pd.offsets.MonthEnd(0)
        with st.spinner("Conectando con Datadis y descargando consumos…"):
            (
                curva_datadis,
                frecuencia_datadis,
                aviso_fallback,
                clave_datadis,
                reutilizado_datadis,
            ) = obtener_consumo_datadis_cacheado(
                st.session_state.datadis_curvas_cache,
                usuario_datadis,
                password_datadis,
                suministro_datadis,
                fecha_inicio_datadis,
                fecha_fin_datadis,
                authorized_nif=authorized_nif_datadis,
                preferir_qh=preferir_qh_datadis,
            )
        if reutilizado_datadis:
            zona_mensajes2.info(
                "Se reutiliza la descarga Datadis de esta sesión para no repetir la llamada."
            )
        st.session_state.df_datadis_raw = curva_datadis
        st.session_state.frec_datadis_raw = frecuencia_datadis
        cache_detalles = st.session_state.setdefault("datadis_detalles_cache", {})
        detalle_datadis = cache_detalles.get(clave_detalle_datadis)
        if detalle_datadis is None:
            try:
                with st.spinner("Consultando el detalle del contrato…"):
                    detalle_datadis = obtener_detalle_contrato_datadis(
                        usuario_datadis,
                        password_datadis,
                        suministro_datadis,
                        authorized_nif=authorized_nif_datadis,
                    )
                cache_detalles[clave_detalle_datadis] = detalle_datadis
                st.session_state.detalle_datadis_actual = detalle_datadis
                st.session_state.detalle_datadis_clave = clave_detalle_datadis
            except Exception as error_detalle:
                zona_mensajes3.warning(
                    f"La curva se ha obtenido, pero no el detalle del contrato: "
                    f"{error_detalle}"
                )
        if detalle_datadis:
            st.session_state.detalle_datadis_actual = detalle_datadis
            st.session_state.detalle_datadis_clave = clave_detalle_datadis
        archivo_datadis = dataframe_como_archivo_curva(
            curva_datadis,
            f"datadis_{frecuencia_datadis.lower()}.csv",
        )
        uploaded = archivo_datadis
        zona_mensajes.success(
            f"✅ Curva de Datadis obtenida: "
            f"{formato_numero_es(len(curva_datadis))} registros."
        )
        if aviso_fallback:
            zona_mensajes2.warning(
                "La curva cuartohoraria no estaba disponible; "
                "se ha descargado la curva horaria."
            )
        elif not reutilizado_datadis:
            zona_mensajes2.info(f"Resolución recibida: {frecuencia_datadis}.")
    except Exception as e:
        st.session_state.pop("df_datadis_raw", None)
        st.session_state.pop("frec_datadis_raw", None)
        zona_mensajes.error(f"❌ Error al obtener la curva de Datadis: {e}")


if origen_curva == "Datadis":
    detalle_visible_datadis = st.session_state.get("detalle_datadis_actual")
    clave_visible_datadis = st.session_state.get("detalle_datadis_clave")
    if (
        detalle_visible_datadis
        and suministro_datadis is not None
        and clave_visible_datadis == clave_detalle_datadis
    ):
        potencias_visibles_datadis = extraer_potencias_contratadas_datadis(
            detalle_visible_datadis
        )
        with col_curva_info:
            st.markdown("#### Contrato Datadis")
            campos_visibles = {
                "Tarifa": detalle_visible_datadis.get("codeFare"),
                "Comercializadora": detalle_visible_datadis.get("marketer"),
                "Distribuidora": detalle_visible_datadis.get("distributor"),
                "Tensión": detalle_visible_datadis.get("tension"),
                "Control": detalle_visible_datadis.get("modePowerControl"),
                "Inicio": detalle_visible_datadis.get("startDate"),
                "Fin": detalle_visible_datadis.get("endDate"),
            }
            st.dataframe(
                pd.DataFrame(
                    [
                        {"Dato": campo, "Valor": valor}
                        for campo, valor in campos_visibles.items()
                        if valor not in (None, "")
                    ]
                ),
                hide_index=True,
                use_container_width=True,
            )
            if potencias_visibles_datadis:
                st.markdown("##### Potencias contratadas")
                st.dataframe(
                    pd.DataFrame(
                        {
                            "Periodo": potencias_visibles_datadis.keys(),
                            "Potencia (kW)": potencias_visibles_datadis.values(),
                        }
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
                if len(potencias_visibles_datadis) == 6:
                    if st.button(
                        "Copiar a Optimización de potencia",
                        use_container_width=True,
                        key="copiar_potencias_datadis_resumen",
                    ):
                        st.session_state.df_pot = pd.DataFrame(
                            {
                                "Periodo": potencias_visibles_datadis.keys(),
                                "Potencia (kW)": potencias_visibles_datadis.values(),
                            }
                        ).set_index("Periodo")
                        st.success("Potencias P1–P6 copiadas correctamente.")


if normalizar and uploaded:
    try:

        dfs_norm = []
        dfs_in = []
        diagnosticos_curva = []

        if not isinstance(uploaded, list):
            uploaded = [uploaded]

        for file in uploaded:
            df_in_i, df_norm_i, msg_unidades, flag_periodos_en_origen, df_periodos, frec = normalize_curve_simple(
                file,
                origin=file.name if hasattr(file, "name") else file,
                excel_sheet=hoja_curva_excel,
                zona_periodos=st.session_state.get(
                    "zona_periodos_cdc", "peninsula"
                ),
            )
            dfs_norm.append(df_norm_i)
            dfs_in.append(df_in_i)
            diagnosticos_curva.append(
                analizar_calidad_curva(
                    df_norm_i,
                    df_origen=df_in_i,
                    frecuencia=frec,
                    periodos_en_origen=flag_periodos_en_origen,
                    origen=file.name if hasattr(file, "name") else str(file),
                )
            )

        df_norm = pd.concat(dfs_norm)
        if len(dfs_in) == 1:
            df_in = dfs_in[0]
            st.session_state.lista_ficheros = None
        else:
            df_in = None
            st.session_state.lista_ficheros = [file.name for file in uploaded]

        consumo_total=df_norm['consumo_kWh'].sum()
        vertido_total=df_norm['excedentes_kWh'].sum()
        consumo_neto=df_norm['consumo_neto_kWh'].sum()
        vertido_neto=df_norm['vertido_neto_kWh'].sum()
        reactiva_total=df_norm['reactiva_kVArh'].sum()


        zona_mensajes.success("✅ Curva normalizada correctamente")
        if msg_unidades != "":
            zona_mensajes2.info(msg_unidades, icon="ℹ️")

        # --- Obtención de periodos ------------------------------------------------
        if not flag_periodos_en_origen:
            msg_periodos = 'Cargados periodos desde fichero auxiliar.'
            zona_mensajes3.warning(msg_periodos, icon="⚠️")

            df_norm = completar_periodos_curva(
                df_norm, df_periodos, atr_dfnorm
            )

        else:
            msg_periodos = 'Cargados periodos desde fichero origen'
            zona_mensajes3.info(msg_periodos, icon="ℹ️")
            if not st.session_state.get('usuario_free', False):
                # --- Detectar ATR según los periodos en el origen ---
                if "periodo" in df_norm.columns:
                    numeros = (
                        df_norm["periodo"]
                        .astype(str)
                        .str.extract(r"P?(\d+)", expand=False)
                        .dropna()
                        .astype(int)
                    )

                    if not numeros.empty and numeros.max() == 3:
                        atr_dfnorm = "2.0"
                        col_curva_info.success("Tres periodos detectados.")
                    else:
                        col_curva_info.warning("Seis periodos detectados.")

                else:
                    col_curva_info.warning("ATENCIÓN: NO HAY PERIODOS DETECTADOS")
            else:
                atr_dfnorm = "3.0"


        df_norm_h = agrupar_curva_horaria(df_norm, frec)


        csv_bytes_norm = df_norm.reset_index(drop=True).to_csv(index=False, sep=";", decimal=",", float_format="%.3f").encode("utf-8")
        csv_bytes_h = df_norm_h.reset_index(drop=True).to_csv(index=False, sep=";", decimal=",", float_format="%.3f").encode("utf-8")

        st.session_state.df_norm = df_norm
        st.session_state.curva_reactiva_version = (
            st.session_state.get("curva_reactiva_version", 0) + 1
        )
        st.session_state.pop("reactiva_base_cache", None)
        st.session_state.pop("reactiva_compensacion", None)
        st.session_state.pop("informe_reactiva_html", None)
        st.session_state.atr_dfnorm = atr_dfnorm
        st.session_state.df_norm_h = df_norm_h
        st.session_state.csv_bytes_norm = csv_bytes_norm
        st.session_state.csv_bytes_h = csv_bytes_h
        st.session_state.frec = frec
        st.session_state.df_in = df_in
        st.session_state.consumo_total=consumo_total
        st.session_state.reactiva_total = reactiva_total
        st.session_state.vertido_total=vertido_total
        st.session_state.consumo_neto=consumo_neto
        st.session_state.vertido_neto=vertido_neto
        st.session_state.diagnosticos_curva = diagnosticos_curva
        # Obtener fechas mínima y máxima del df_norm_h y guardar para telemindex
        fecha_ini = df_norm["fecha"].min()
        fecha_fin = df_norm["fecha"].max()
        st.session_state.rango_curvadecarga = (fecha_ini, fecha_fin)

    except Exception as e:
        zona_mensajes.error(f"❌ Error al normalizar: {e}")
        st.stop()

elif (
    origen_curva == "Archivo CSV/Excel"
    and st.session_state.get("df_norm") is None
):
    if uploaded:
        zona_mensajes.info("Pulsa **Normalizar curva de carga** para procesar los archivos.")
    else:
        zona_mensajes.info("⬆️ Sube un archivo CSV o Excel para comenzar.")





if st.session_state.get("df_norm") is None:
    col_curva_vista.info(
        "La vista del archivo original y la tabla normalizada aparecerán aquí."
    )


if st.session_state.get("df_norm") is not None:
    col_curva_info.markdown(
        f'Peaje actualmente seleccionado: '
        f'**:orange[{st.session_state.atr_dfnorm}]**'
    )
    col_curva_info.markdown(
        f'Resolución temporal de la curva: '
        f'**:orange[{st.session_state.frec}]**'
    )
    # --- Descarga ---
    csv_bytes = st.session_state.get("csv_bytes_norm")
    if not st.session_state.get('usuario_autenticado', False):
        habilitar_descarga = False
    else:
        habilitar_descarga = True
    col_curva_entrada.download_button("⬇️ Descargar CSV normalizado", csv_bytes or b"", "curva_normalizada.csv", "text/csv", disabled=not habilitar_descarga or csv_bytes is None, use_container_width=True)

    csv_bytes_h = st.session_state.get("csv_bytes_h")
    if not st.session_state.get('usuario_autenticado', False):
        habilitar_descarga = False
    else:
        habilitar_descarga = True
    col_curva_entrada.download_button("⬇️ Descargar CSV agrupado horario", csv_bytes_h or b"", "curva_agrupado.csv", "text/csv", disabled=not habilitar_descarga or csv_bytes_h is None, use_container_width=True)

    diagnosticos_curva = st.session_state.get("diagnosticos_curva", [])
    campos_incidencia = {
        "fechas_invalidas": "Fechas no interpretadas",
        "consumos_ausentes": "Consumos ausentes/no numéricos",
        "consumos_negativos": "Consumos negativos",
        "duplicados_fecha_hora": "Marcas temporales duplicadas",
        "saltos_temporales": "Saltos en la secuencia temporal",
        "intervalos_ausentes_estimados": "Intervalos ausentes estimados",
        "periodos_ausentes": "Periodos ausentes en el origen",
    }
    hay_incidencias = any(
        diagnostico.get(campo, 0) > 0
        for diagnostico in diagnosticos_curva
        for campo in campos_incidencia
    )
    titulo_calidad = (
        "⚠️ Calidad de datos"
        if hay_incidencias
        else "✅ Calidad de datos"
    )
    with col_curva_info.expander(titulo_calidad, expanded=hay_incidencias):
        st.caption(
            "Los saltos o duplicados pueden proceder del cambio oficial de hora, "
            "de periodos parciales o de huecos del origen. Se muestran para revisión "
            "y no modifican automáticamente la curva."
        )
        if not diagnosticos_curva:
            st.caption("No hay diagnóstico disponible para esta curva.")
        for diagnostico in diagnosticos_curva:
            st.markdown(f"**{diagnostico['origen']}**")
            incidencias_archivo = [
                f"{etiqueta}: {formato_numero_es(diagnostico.get(campo, 0))}"
                for campo, etiqueta in campos_incidencia.items()
                if diagnostico.get(campo, 0) > 0
            ]
            if incidencias_archivo:
                for incidencia in incidencias_archivo:
                    st.warning(incidencia)
            else:
                st.success("Sin incidencias estructurales detectadas.")

            columnas_calidad = diagnostico.get("columnas_calidad", [])
            if columnas_calidad:
                st.caption("Información de lectura real/estimada detectada:")
                for columna in columnas_calidad:
                    valores = ", ".join(
                        f"{valor}: {formato_numero_es(cantidad)}"
                        for valor, cantidad in columna["valores"].items()
                    )
                    st.markdown(f"- **{columna['columna']}** — {valores}")
            else:
                st.caption("El origen no incluye una columna reconocible de calidad de lectura.")

    with col_curva_vista:
        altura_df = 250
        st.markdown("**Archivo original**")
        if st.session_state.get("df_in") is not None:
            # Altura aproximada de seis filas visibles; el resto queda accesible
            # mediante scroll sin recortar el DataFrame de origen.
            df_in_preview = (
                st.session_state.df_in
                .reset_index(drop=True)
                .fillna("")
            )
            st.caption(
                f"Lecturas de origen: {formato_numero_es(len(df_in_preview))}"
            )
            st.dataframe(
                df_in_preview,
                height=altura_df,
                use_container_width=True,
                hide_index=True,
            )
        elif st.session_state.get("lista_ficheros"):
            with st.container(height=altura_df):
                st.info("Se han cargado múltiples suministros.")
                for fichero in st.session_state.lista_ficheros:
                    st.write(f"• {fichero}")

        st.markdown("**Tabla normalizada**")
        total_filas_norm = len(st.session_state.df_norm)
        st.caption(
            f"Vista previa: primeras 1.000 filas de "
            f"{formato_numero_es(total_filas_norm)}"
        )
        st.dataframe(
            st.session_state.df_norm.head(1000),
            height=altura_df,
            use_container_width=True,
        )

    with col_curva_info:
        st.markdown("**Resumen de datos**")
        resumen_1, resumen_2 = st.columns(2, gap="medium")
        with resumen_1:
            st.metric("Registros", formato_numero_es(len(st.session_state.df_norm)))
            st.metric("Consumo total", formato_kwh(st.session_state.consumo_total))
            st.metric(
                "Reactiva total",
                formato_numero_es(st.session_state.reactiva_total),
            )
            st.metric("Consumo neto", formato_kwh(st.session_state.consumo_neto))
        with resumen_2:
            st.metric(
                "Fecha inicio",
                st.session_state.df_norm["fecha_hora"].min().strftime("%d.%m.%Y"),
            )
            st.metric(
                "Fecha final",
                st.session_state.df_norm["fecha_hora"].max().strftime("%d.%m.%Y"),
            )
            st.metric("Vertido total", formato_kwh(st.session_state.vertido_total))
            st.metric("Vertido neto", formato_kwh(st.session_state.vertido_neto))

    # ===============================================================
    # RESUMEN GENERAL
    # ===============================================================
    with tab1:
        c1,c2=st.columns([.7,.3])
        with c1:
            st.subheader("Gráfico de consumo")
            # Mostrar gráfico
            graf_horario = graficar_curva_horaria(st.session_state.df_norm_h, st.session_state.frec)
            st.plotly_chart(graf_horario, use_container_width=True)
        with c2:
            st.subheader("Consumo por periodos")
            graf_periodos, df_periodos = graficar_queso_periodos(st.session_state.df_norm_h)
            st.plotly_chart(graf_periodos, use_container_width=True)

        c1,c2,c3=st.columns([.4,.3,.3])
        with c1:
            graf_diario = graficar_diario_apilado(st.session_state.df_norm_h)
            st.plotly_chart(graf_diario, use_container_width=True)
        with c2:
            graf_mensual = graficar_mensual_apilado(st.session_state.df_norm_h)
            st.plotly_chart(graf_mensual, use_container_width=True)
            tabla_mensual_consumos = tabla_mensual_periodos(st.session_state.df_norm_h)

            # La fila de total es solo para presentacion. Conservamos la tabla
            # mensual original para los calculos de reactiva que se hacen despues.
            fila_total_consumos = tabla_mensual_consumos.drop(columns="Mes").sum().to_dict()
            fila_total_consumos["Mes"] = "Total"
            tabla_mensual_consumos_mostrar = pd.concat(
                [tabla_mensual_consumos, pd.DataFrame([fila_total_consumos])],
                ignore_index=True,
            )

            from backend_comun import formatear_tabla_consumos
            tabla_mensual_consumos_fmt = formatear_tabla_consumos(
                tabla_mensual_consumos_mostrar,
                columna_mes="Mes",
                incluir_unidades=False,
            )
            st.dataframe(tabla_mensual_consumos_fmt, use_container_width=True, hide_index=True)
        with c3:
            graf_medias_horarias_total=graficar_media_horaria('Todos', ymax = None)
            st.plotly_chart(graf_medias_horarias_total, use_container_width=True)

    # ========================================================================================================
    # ANÁLISIS
    # ========================================================================================================
    with tab2:

        graf_medias_horarias_combinadas, ymax = graficar_media_horaria_combinada()
        #zmax_heatmap = st.session_state.df_norm_h["consumo_neto_kWh"].max()
        zmax_heatmap = st.session_state.df_norm_h["consumo_neto_kWh"].quantile(0.98)
        print (zmax_heatmap)

        graf_medias_horarias_total=graficar_media_horaria('Todos', ymax)
        graf_medias_horarias_lab=graficar_media_horaria('L-V',ymax)
        graf_medias_horarias_ffss=graficar_media_horaria('FS', ymax)

        graf_medias_horarias_total_ranking = graficar_media_horaria('Todos', ymax, ordenar=True)
        graf_medias_horarias_lab_ranking = graficar_media_horaria('L-V', ymax, ordenar=True)
        graf_medias_horarias_ffss_ranking = graficar_media_horaria('FS', ymax, ordenar=True)

        graf_bigotes_total = graficar_boxplot_horario('Todos')
        graf_bigotes_lab = graficar_boxplot_horario('L-V')
        graf_bigotes_ffss = graficar_boxplot_horario('FS')

        graf_heatmap_total = graficar_heatmap_dia_hora('Todos', zmax_heatmap)
        graf_heatmap_lab = graficar_heatmap_dia_hora('L-V', zmax_heatmap)
        graf_heatmap_ffss = graficar_heatmap_dia_hora('FS', zmax_heatmap)

        patron_horario = calcular_patron_horario_boxplot()
        df_analisis_horario = detectar_consumos_atipicos_horarios(
            patron=patron_horario,
            min_exceso_kwh=0,
            min_ratio=1.0
        )

        df_revisables = df_analisis_horario[df_analisis_horario["es_revisable"]].copy()

        resumen_dia = resumir_atipicos_por_dia(df_analisis_horario)
        kpis = calcular_kpis_atipicos(df_analisis_horario, resumen_dia)

        mostrar_kpis_atipicos(kpis)

        fig_top = graficar_top_dias_revisables(resumen_dia, top_n=20, metrica="exceso_total_vs_mediana")

        serie_alertas = df_analisis_horario.loc[df_analisis_horario["es_revisable"], "exceso_vs_mediana"]
        zmax_alertas = serie_alertas.quantile(0.95) if not serie_alertas.empty else 1
        fig_lv = graficar_heatmap_alertas(df_analisis_horario, tipo_dia="L-V", metrica="exceso_vs_mediana", zmax=zmax_alertas)
        fig_fs = graficar_heatmap_alertas(df_analisis_horario, tipo_dia="FS", metrica="exceso_vs_mediana", zmax=zmax_alertas)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.plotly_chart(graf_medias_horarias_total, use_container_width=True)
            st.plotly_chart(graf_medias_horarias_total_ranking, use_container_width=True)
            st.plotly_chart(graf_bigotes_total, use_container_width=True)
            st.plotly_chart(graf_heatmap_total, use_container_width=True)
        with c2:
            st.plotly_chart(graf_medias_horarias_lab, use_container_width=True)
            st.plotly_chart(graf_medias_horarias_lab_ranking, use_container_width=True)
            st.plotly_chart(graf_bigotes_lab, use_container_width=True)
            st.plotly_chart(graf_heatmap_lab, use_container_width=True)
            st.plotly_chart(fig_lv, use_container_width=True)


        with c3:
            st.plotly_chart(graf_medias_horarias_ffss, use_container_width=True)
            st.plotly_chart(graf_medias_horarias_ffss_ranking, use_container_width=True)
            st.plotly_chart(graf_bigotes_ffss, use_container_width=True)
            st.plotly_chart(graf_heatmap_ffss, use_container_width=True)
            st.plotly_chart(fig_fs, use_container_width=True)
        with c4:
            st.plotly_chart(graf_medias_horarias_combinadas, use_container_width=True)


        st.write("Patrón horario boxplot")
        st.dataframe(patron_horario)



        st.write("Análisis horario frente al patrón")
        st.dataframe(df_analisis_horario)



        st.write("Horas potencialmente revisables")
        st.dataframe(
            df_revisables[
                [
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
            ].sort_values("exceso_vs_mediana", ascending=False)
        )




        if fig_top is not None:
            st.plotly_chart(fig_top, use_container_width=True)






        st.write("Top horas revisables")
        st.dataframe(obtener_top_horas_revisables(df_analisis_horario, top_n=50))

    # ================================================================================================
    # AUTOCONSUMO
    # ================================================================================================
    from backend_curvadecarga import graficar_dem_ver, graficar_con_gen
    with tab3:
        df_norm_h_modif = st.session_state.df_norm_h.copy()
        df_norm_h_modif['demanda_neto_kWh'] = df_norm_h_modif['consumo_neto_kWh']
        if df_norm_h_modif["generacion_kWh"].sum() > 0:
            df_norm_h_modif['consumo_neto_kWh'] = df_norm_h_modif['demanda_neto_kWh'] + df_norm_h_modif['generacion_kWh'] - df_norm_h_modif['vertido_neto_kWh']
            df_norm_h_modif["autoconsumo_kWh"] = (df_norm_h_modif["generacion_kWh"] - df_norm_h_modif["vertido_neto_kWh"])
            df_norm_h_modif["autoconsumo_kWh"] = df_norm_h_modif["autoconsumo_kWh"].apply(lambda x: x if x > 0 else 0)
        else:
            df_norm_h_modif["autoconsumo_kWh"] = 0

        df_be = df_norm_h_modif.agg({
            "consumo_neto_kWh": "sum",
            "generacion_kWh": "sum",
            "demanda_neto_kWh": "sum",
            "vertido_neto_kWh": "sum",
            "autoconsumo_kWh": "sum",
        }).to_frame().T

        #calculamos el % de cobertura del consumo, autoconsumo por un lado y demanda por otro
        df_be['%_autoconsumo']=round(df_be['autoconsumo_kWh']*100/df_be['consumo_neto_kWh'],2)
        df_be['%_demanda']=100-df_be['%_autoconsumo']
        #calculamos el % de aprovechamiento de la generación
        df_be['%_vertido_neto_kWh']=round(df_be['vertido_neto_kWh']*100/df_be['generacion_kWh'],2)
        df_be['%_generacion']=100-df_be['%_vertido_neto_kWh']


        colores_energia = {
            'consumo_neto_kWh': '#3498DB',        # azul
            'demanda_neto_kWh': '#E74C3C',         # naranja
            'generacion_kWh': '#F7DC6F',  # amarillo suave
            'vertido_neto_kWh': '#AF7AC5',        # lila / violeta claro
            'autoconsumo_kWh': '#2ECC71'     # verde
        }

        from backend_balkoning_solar import graficar_quesos_balance
        #graf_con_gen = graficar_con_gen(df_be)
        #graf_cobertura = graficar_barras_balance(df_be, 'cobertura', colores_energia)
        #graf_aprovechamiento = graficar_barras_balance(df_be, 'aprovechamiento', colores_energia)

        total_consumo = df_be['consumo_neto_kWh'].sum()
        total_genfv = df_be['generacion_kWh'].sum()
        total_demanda = df_be['demanda_neto_kWh'].sum()
        total_vertido = df_be['vertido_neto_kWh'].sum()
        #total_aprovechamiento = total_genfv-total_vertido
        total_autoconsumo = df_be['autoconsumo_kWh'].sum()
        #print(total_autoconsumo)

        cobertura_media_porc=round(total_autoconsumo*100/total_consumo,2)
        #aprovechamiento_medio_porc=round(100-total_vertido*100/total_genfv,2)
        aprovechamiento_medio_porc = (
            round(100 - total_vertido * 100 / total_genfv, 2)
            if pd.notna(total_genfv) and total_genfv != 0
            else 0
        )


        # DATAFRANES PARA QUESOS RESUMEN BALANCE ENERGÉTICO
        df_aprovechamiento = pd.DataFrame({
            'concepto': ['autoconsumo_kWh', 'vertido_neto_kWh'],
            'energia_kwh': [total_autoconsumo, total_vertido]
        })
        df_cobertura = pd.DataFrame({
            'concepto': ['autoconsumo_kWh', 'demanda_neto_kWh'],
            'energia_kwh': [total_autoconsumo, total_demanda]
        })
        graf_aprovechamiento_total = graficar_quesos_balance(df_aprovechamiento, aprovechamiento_medio_porc, colores_energia, 'aprovechamiento')
        graf_cobertura_total = graficar_quesos_balance(df_cobertura, cobertura_media_porc, colores_energia, 'cobertura')

        graf_dem_ver = graficar_dem_ver(df_norm_h_modif, colores_energia)
        graf_con_gen = graficar_con_gen(df_norm_h_modif, colores_energia)


        with st.container():
            st.subheader('Balance energético')
            c1, c2, c3= st.columns([.3,.4,.4])
            with c1:

                c21, c22 = st.columns(2)
                with c21:
                    st.metric("Consumo total (kWh)", formato_kwh(total_consumo))
                    st.metric("Demanda total (kWh)", formato_kwh(total_demanda))
                    st.metric("Generación FV (kWh)", formato_kwh(total_genfv))
                with c22:
                    #st.metric("", "")
                    st.metric("Autoconsumo (kWh)", formato_kwh(total_autoconsumo))
                    st.metric("Vertido (kWh)", formato_kwh(total_vertido))
            with c2:
                st.plotly_chart(graf_aprovechamiento_total)
            with c3:
                st.plotly_chart(graf_cobertura_total)
        #with c2:
        with st.container():
            c1,c2 = st.columns([.3,.7])
            with c1:
                graf_dem_ver_mensual = graficar_dem_ver_mensual(df_norm_h_modif, colores_energia)
                st.plotly_chart(graf_dem_ver_mensual)

            with c2:
               st.plotly_chart(graf_dem_ver, use_container_width=True)
        with st.container():
            c1,c2 = st.columns([.3,.7])
            with c1:
                graf_con_gen_mensual = graficar_con_gen_mensual(df_norm_h_modif, colores_energia)
                st.plotly_chart(graf_con_gen_mensual, use_container_width=True)

            with c2:
                st.plotly_chart(graf_con_gen, use_container_width=True)



    # ===================================================================================================================================================================================================
    # COMPARATIVAS
    # ===================================================================================================================================================================================================


    res = calcular_comparacion()

    fechas = res["fechas"]

    fecha_ini_global = fechas["fecha_ini_global"]
    fecha_fin_global = fechas["fecha_fin_global"]
    fecha_max_comparable = fechas["fecha_max_comparable"]
    rango_valido = fechas["rango_valido"]

    df_pivot = res['df_pivot']
    resumen_html = res["resumen_html"]
    fig_total = res["fig_total"]
    fig_mensual = res["fig_mensual"]
    etiqueta_base_consumo, etiqueta_comp_consumo = res.get(
        "etiquetas_periodos", ("Base", "+1 año")
    )

    with tab4:
        with st.container():
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.subheader('Introduce rango de fechas a comparar')
                st.info(
                    f"Rango disponible de la curva: "
                    f"{fecha_ini_global.strftime('%d.%m.%Y')} → {fecha_fin_global.strftime('%d.%m.%Y')}"
                )
                if rango_valido is not None:
                    st.success(
                        f"Rango comparable seleccionable: "
                        f"{rango_valido[0].strftime('%d.%m.%Y')} → {rango_valido[1].strftime('%d.%m.%Y')}"
                    )
                else:
                    st.warning(res["mensaje"])
                    #st.stop()


            if rango_valido is not None:

                    with c1:
                        with st.form('Seleccionar'):
                            if "_rango_fechas_comparativa" not in st.session_state:
                                st.session_state._rango_fechas_comparativa = (
                                    st.session_state.rango_fechas_comparativa_guardado
                                )
                            st.date_input(
                                "Selecciona periodo base",
                                min_value=fecha_ini_global,
                                max_value=fecha_max_comparable,
                                key="_rango_fechas_comparativa",
                                format="DD.MM.YYYY",
                            )
                            actualizar_comparacion = st.form_submit_button(
                                'Actualizar periodo de comparación'
                            )
                        if actualizar_comparacion:
                            st.session_state.rango_fechas_comparativa_guardado = (
                                st.session_state._rango_fechas_comparativa
                            )
                            st.rerun()
                    with c2:
                        st.markdown(resumen_html, unsafe_allow_html=True)
                        st.subheader('Tabla de resultados')
                        #df_pivot_fmt = formatear_resumen_mixto(df_pivot)
                        df_pivot_fmt = formatear_columnas_tabla(
                            df_pivot,
                            columnas_kwh=[
                                etiqueta_base_consumo,
                                etiqueta_comp_consumo,
                                "Δ",
                            ],
                            columnas_pct=["Δ %"],
                            incluir_unidades=False
                        )
                        st.dataframe(
                            df_pivot_fmt,
                            use_container_width=True,
                            hide_index=True,
                            height=178,
                        )

                    with c3:
                        if fig_total is not None:
                            st.plotly_chart(fig_total, use_container_width=True)
                    with c4:
                        if fig_mensual is not None:
                            st.plotly_chart(fig_mensual, use_container_width=True)

        coste_c1, coste_c2, coste_c3, coste_c4 = st.columns(4)
        with coste_c1:
                st.subheader("Comparación de costes de energía")
                precios_mensuales = st.session_state.get("precios_mensuales", None)
                if precios_mensuales is None:
                    st.warning(
                        'Todavía no se han cargado precios indexados para la curva.'
                    )
                else:
                    st.success('Disponibles datos de indexado para la curva introducida')
                cargar_indexados = st.button(
                    "Cargar precios indexados",
                    use_container_width=True,
                    key="cargar_indexados_comparaciones",
                )
                st.caption(
                    "Usa la fórmula vigente de Telemindex y la curva horaria "
                    "cargada, sin salir de este módulo."
                )

                if cargar_indexados:
                    try:
                        with st.spinner("Cargando precios horarios indexados…"):
                            init_app()
                            st.session_state.zona_periodos_index = "peninsula"
                            init_app_index()
                            actualizar_df_index_por_zona(forzar=True)
                            df_curva_indexada = construir_df_curva_sheets(
                                st.session_state.df_sheets.copy()
                            )
                            df_curva_indexada = añadir_costes_curva(
                                df_curva_indexada
                            ).drop_duplicates(
                                subset=["fecha", "hora"], keep="first"
                            )
                            st.session_state.df_curva_sheets = df_curva_indexada
                            precios_mensuales, _ = evol_mensual(
                                df_curva_indexada, {}
                            )
                            st.session_state.precios_mensuales = precios_mensuales
                    except Exception as exc:
                        st.error(f"No se han podido cargar los indexados: {exc}")
                    else:
                        st.success("Precios indexados cargados correctamente.")
                        st.rerun()

        if precios_mensuales is not None and rango_valido is not None:

            rango_costes = st.session_state.get(
                "rango_fechas_comparativa_guardado", None
            )
            precios_costes = preparar_costes_mensuales_rango(
                st.session_state.get("df_curva_sheets"), rango_costes
            )
            if precios_costes.empty:
                precios_costes = precios_mensuales

            res_costes = calcular_comparacion_costes(
                precios_mensuales=precios_costes,
                rango_base=rango_costes,
            )

            if not res_costes["ok"]:
                st.warning(res_costes["mensaje"])

            else:
                df_costes = res_costes["df_costes"]
                df_efectos = res_costes["df_efectos"]
                etiqueta_base_coste, etiqueta_comp_coste = res_costes.get(
                    "etiquetas_periodos", ("Base", "+1 año")
                )
                df_costes_fmt = formatear_columnas_tabla(
                    df_costes,
                    columnas_kwh=[
                        f"Consumo {etiqueta_base_coste}",
                        f"Consumo {etiqueta_comp_coste}",
                    ],
                    columnas_euros=[
                        f"Coste {etiqueta_base_coste}",
                        f"Coste {etiqueta_comp_coste}",
                        "Δ coste",
                    ],
                    columnas_pct=["Δ coste %"],
                    incluir_unidades=False,
                )
                df_efectos_fmt = formatear_columnas_tabla(
                    df_efectos,
                    columnas_euros=[
                        "Δ coste real",
                        "Efecto precio",
                        "Efecto consumo",
                        "Coste con consumo base y precio +1 año",
                    ],
                    incluir_unidades=False,
                )

                with coste_c1:
                    st.markdown(
                        res_costes.get("impacto_total_html_costes", ""),
                        unsafe_allow_html=True,
                    )
                    with st.expander("Resumen económico"):
                        st.markdown(
                            res_costes["resumen_html_costes"],
                            unsafe_allow_html=True,
                        )
                    with st.expander("Tabla de costes"):
                        st.dataframe(
                            df_costes_fmt,
                            use_container_width=True,
                            hide_index=True,
                        )
                    with st.expander("Descomposición de la variación"):
                        st.dataframe(
                            df_efectos_fmt,
                            use_container_width=True,
                            hide_index=True,
                        )
                    st.subheader("Efecto PRECIO / CONSUMO")
                    st.markdown(
                        res_costes.get("impacto_html_costes", ""),
                        unsafe_allow_html=True,
                    )

                with coste_c2:
                    if res_costes.get("fig_resumen_costes") is not None:
                        st.plotly_chart(
                            res_costes["fig_resumen_costes"],
                            use_container_width=True,
                        )
                    if res_costes["fig_efectos"] is not None:
                        st.plotly_chart(
                            res_costes["fig_efectos"],
                            use_container_width=True,
                        )

                with coste_c3:
                    if res_costes["fig_precio_medio"] is not None:
                        st.plotly_chart(
                            res_costes["fig_precio_medio"],
                            use_container_width=True,
                        )

                with coste_c4:
                    if res_costes["fig_coste_total"] is not None:
                        st.plotly_chart(
                            res_costes["fig_coste_total"],
                            use_container_width=True,
                        )



    # ======================================================================================================================================================
    # REACTIVA
    # ======================================================================================================================================================
    with tab5:
        df_norm_h_reactiva = st.session_state.df_norm_h.copy()
        df_norm_reactiva = st.session_state.df_norm.copy()
        hay_datos_reactiva = (
            "reactiva_kVArh" in df_norm_reactiva.columns
            and pd.to_numeric(
                df_norm_reactiva["reactiva_kVArh"],
                errors="coerce",
            ).notna().any()
        )
        if not hay_datos_reactiva:
            st.subheader("RESUMEN COMPENSACIÓN")
            st.warning(
                "La curva de carga no contiene datos de energía reactiva. "
                "No es posible realizar un estudio de compensación de "
                "reactiva.",
                icon="⚠️",
            )
        else:
            fecha_fin_reactiva = df_norm_h_reactiva["fecha_hora"].max().normalize()
            fecha_inicio_reactiva = df_norm_h_reactiva["fecha_hora"].min().normalize()
            if (fecha_fin_reactiva - fecha_inicio_reactiva).days + 1 > 365:
                fecha_inicio_reactiva = fecha_fin_reactiva - pd.Timedelta(days=364)
                fecha_limite_reactiva = fecha_fin_reactiva + pd.Timedelta(days=1)
                df_norm_h_reactiva = df_norm_h_reactiva[
                    (df_norm_h_reactiva["fecha_hora"] >= fecha_inicio_reactiva)
                    & (df_norm_h_reactiva["fecha_hora"] < fecha_limite_reactiva)
                ].copy()
                df_norm_reactiva = df_norm_reactiva[
                    (df_norm_reactiva["fecha_hora"] >= fecha_inicio_reactiva)
                    & (df_norm_reactiva["fecha_hora"] < fecha_limite_reactiva)
                ].copy()

            version_curva = st.session_state.get("curva_reactiva_version", 0)
            cache_base = st.session_state.get("reactiva_base_cache")
            if not cache_base or cache_base.get("version") != version_curva:
                tabla_mensual_consumos_reactiva = tabla_mensual_periodos(
                    df_norm_h_reactiva,
                    columna_valor="consumo_neto_kWh",
                )
                df_reactiva = tabla_mensual_periodos(
                    df_norm_h_reactiva,
                    columna_valor="reactiva_kVArh",
                )
                df_excesos_reactiva = calcular_tabla_excesos_reactiva(
                    tabla_mensual_consumos_reactiva,
                    df_reactiva,
                )
                df_fp = calcular_tabla_factor_potencia(
                    tabla_mensual_consumos_reactiva,
                    df_reactiva,
                )
                df_coste_excesos_reactiva = calcular_tabla_coste_excesos_reactiva(
                    df_excesos_reactiva,
                    df_fp,
                )
                df_potmed_qh = calcular_tabla_potencia_media_qh(
                    df_norm_reactiva,
                    columna_valor="consumo_neto_kWh",
                )
                cache_base = {
                    "version": version_curva,
                    "consumos": tabla_mensual_consumos_reactiva,
                    "reactiva": df_reactiva,
                    "excesos": df_excesos_reactiva,
                    "fp": df_fp,
                    "costes": df_coste_excesos_reactiva,
                    "potencia_media": df_potmed_qh,
                }
                st.session_state.reactiva_base_cache = cache_base
            else:
                tabla_mensual_consumos_reactiva = cache_base["consumos"]
                df_reactiva = cache_base["reactiva"]
                df_excesos_reactiva = cache_base["excesos"]
                df_fp = cache_base["fp"]
                df_coste_excesos_reactiva = cache_base["costes"]
                df_potmed_qh = cache_base["potencia_media"]

            total_penalizacion_reactiva = df_coste_excesos_reactiva["Total"].sum()

            tabla_mensual_consumos_reactiva_fmt = formatear_tabla_consumos(
                tabla_mensual_consumos_reactiva,
                columna_mes="Mes",
                incluir_unidades=False,
            )
            df_potmed_qh_fmt = formatear_tabla_consumos(df_potmed_qh, columna_mes="Mes", incluir_unidades=False)
            df_reactiva_fmt = formatear_tabla_consumos(df_reactiva, columna_mes="Mes", incluir_unidades=False)
            df_excesos_react_fmt = formatear_tabla_consumos(df_excesos_reactiva, columna_mes="Mes", incluir_unidades=False)

            #aplicamos colores a la tabla mensual de FPs
            df_fp_fmt = df_fp.copy()
            df_fp_fmt.columns.name = None
            cols_fp = [c for c in df_fp_fmt.columns if c != "Mes"]
            styler_fp = (
                df_fp_fmt
                .style
                .applymap(estilo_factor_potencia, subset=cols_fp)
                .format({
                    col: lambda x: "" if x == "" or pd.isna(x) else f"{float(x):.2f}"
                    for col in cols_fp
                })
            )

            #calculamos penalizaciones y formateamos
            df_coste_excesos_reactiva_fmt = df_coste_excesos_reactiva.copy()
            df_coste_excesos_reactiva_fmt.columns.name = None
            cols_coste = [c for c in df_coste_excesos_reactiva_fmt.columns if c != "Mes"]
            for col in cols_coste:
                df_coste_excesos_reactiva_fmt[col] = (
                    df_coste_excesos_reactiva_fmt[col]
                    #.replace("None", np.nan)
                    .replace(["None", "nan", "NaN", ""], np.nan)
                    #.replace(None, np.nan)
                )
                df_coste_excesos_reactiva_fmt[col] = pd.to_numeric(df_coste_excesos_reactiva_fmt[col], errors="coerce")
            # 2) Convertimos NaN a "" SOLO para visualización
            df_coste_excesos_reactiva_fmt[cols_coste] = df_coste_excesos_reactiva_fmt[cols_coste].astype(object)
            df_coste_excesos_reactiva_fmt[cols_coste] = df_coste_excesos_reactiva_fmt[cols_coste].where(
                pd.notna(df_coste_excesos_reactiva_fmt[cols_coste]),
                ""
            )
            # 3) Formato visual
            def formato_coste_celda(x):
                if x == "" or pd.isna(x):
                    return ""
                try:
                    x = float(x)
                except:
                    return ""
                return formato_numero_es(x, 2)

            styler_coste_exc = (
                df_coste_excesos_reactiva_fmt
                .style
                .applymap(estilo_coste_penalizacion, subset=cols_coste)
                .format({
                    #col: lambda x: "" if pd.isna(x) else f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    col: formato_coste_celda
                    for col in cols_coste
                },
                na_rep=""
                )
            )

            cols_periodos = [c for c in df_fp.columns if c.startswith("P")]
            fp_min = df_fp[cols_periodos].min().min()
            fp_med = round(df_fp["Total"].mean(), 2)
            fp_max = df_fp[cols_periodos].max().max()

            def gestionar_form_compensacion():
                with st.form("form_compensacion_reactiva"):
                    st.subheader("Cálculo de compensación")
                    c_form1, c_form2, c_form3 = st.columns(3)
                    with c_form1:
                        fp_obj_min_form = st.number_input(
                            "Cos φ objetivo mínimo",
                            min_value=0.95,
                            max_value=1.00,
                            value=float(st.session_state.fp_obj_min),
                            disabled=True,
                        )
                    with c_form2:
                        margen_comp_form = st.number_input(
                            "Margen de seguridad (%)",
                            min_value=30,
                            max_value=50,
                            value=int(st.session_state.margen_comp_min),
                        )
                    with c_form3:
                        fp_obj_sel_form = st.number_input(
                            "Cos φ deseado",
                            min_value=0.95,
                            max_value=1.00,
                            value=0.98,
                            step=0.01,
                            format="%.2f",
                        )
                    calcular_compensacion = st.form_submit_button(
                        "Calcular compensación",
                        type="primary",
                        use_container_width=True,
                    )

                if calcular_compensacion:
                    from backend_curvadecarga import (
                        calcular_curva_q_dimensionamiento,
                        graficar_compensacion_dimensionamiento,
                    )
                    df_coef_k_min = calcular_tabla_coef_k(df_fp, fp_obj_min_form)
                    df_q_condensadores_min = calcular_tabla_q_condensadores(
                        df_potmed_qh,
                        df_coef_k_min,
                    )
                    cols_q = [
                        c for c in df_q_condensadores_min.columns
                        if c.startswith("P")
                    ]
                    q_min = df_q_condensadores_min[cols_q].max().max()
                    q_min_margen = q_min * (1 + margen_comp_form / 100)
                    df_curva_q = calcular_curva_q_dimensionamiento(
                        df_fp=df_fp,
                        df_potmed_qh=df_potmed_qh,
                        fp_ini=fp_min,
                        fp_fin=1.000,
                        paso=0.001,
                    )
                    df_curva_aux = (
                        df_curva_q[["fp_obj", "q_max"]]
                        .dropna()
                        .sort_values("q_max")
                    )
                    q_min_margen_clip = np.clip(
                        q_min_margen,
                        df_curva_aux["q_max"].min(),
                        df_curva_aux["q_max"].max(),
                    )
                    fp_min_margen = float(np.interp(
                        q_min_margen_clip,
                        df_curva_aux["q_max"],
                        df_curva_aux["fp_obj"],
                    ))
                    fp_obj_sel_aplicado = max(
                        float(fp_obj_sel_form),
                        fp_min_margen,
                    )
                    df_coef_k_sel = calcular_tabla_coef_k(
                        df_fp,
                        fp_obj_sel_aplicado,
                    )
                    df_q_condensadores_sel = calcular_tabla_q_condensadores(
                        df_potmed_qh,
                        df_coef_k_sel,
                    )
                    q_sel = df_q_condensadores_sel[cols_q].max().max()
                    fig_compensacion = graficar_compensacion_dimensionamiento(
                        df_curva_q=df_curva_q,
                        q_min=q_min,
                        fp_min_rec=fp_min_margen,
                        q_min_rec=q_min_margen,
                        q_sel=q_sel,
                        fp_ini=fp_min,
                    )
                    st.session_state.margen_comp_min = margen_comp_form
                    st.session_state.fp_obj_sel = fp_obj_sel_aplicado
                    st.session_state.reactiva_compensacion = {
                        "version": version_curva,
                        "q_min": q_min,
                        "q_min_margen": q_min_margen,
                        "fp_min_margen": fp_min_margen,
                        "fp_solicitado": float(fp_obj_sel_form),
                        "fp_aplicado": fp_obj_sel_aplicado,
                        "q_sel": q_sel,
                        "coef_min": df_coef_k_min,
                        "coef_sel": df_coef_k_sel,
                        "q_min_df": df_q_condensadores_min,
                        "q_sel_df": df_q_condensadores_sel,
                        "figura": fig_compensacion,
                    }
                    st.session_state.pop("informe_reactiva_html", None)
                    st.rerun()

                resultado_compensacion = st.session_state.get(
                    "reactiva_compensacion"
                )
                if (
                    resultado_compensacion
                    and resultado_compensacion.get("version") != version_curva
                ):
                    resultado_compensacion = None
                    st.session_state.pop("reactiva_compensacion", None)
                return resultado_compensacion


            with st.container():
                c1, c2 = st.columns([.4,.6])
                with c1:
                    st.subheader('RESUMEN COMPENSACIÓN')
                    c_aviso, c_penalizacion = st.columns([2, 1])
                    if (
                        pd.notna(total_penalizacion_reactiva)
                        and total_penalizacion_reactiva > 0
                    ):
                        c_aviso.warning(
                            "Se ha detectado una penalización por energía reactiva "
                            f"de {formato_euros(total_penalizacion_reactiva)} en el "
                            f"periodo {fecha_inicio_reactiva:%d/%m/%Y} – "
                            f"{fecha_fin_reactiva:%d/%m/%Y}.",
                            icon="⚠️",
                        )
                    color_valor_penalizacion = (
                        "#b91c1c"
                        if total_penalizacion_reactiva > 0
                        else "#15803d"
                    )
                    with c_penalizacion:
                        st.markdown(
                            "<style>"
                            ":is([data-testid='column'],[data-testid='stColumn']):has("
                            ".valor-penalizacion-reactiva):not(:has("
                            ":is([data-testid='column'],[data-testid='stColumn']) "
                            ".valor-penalizacion-reactiva)) "
                            "[data-testid='stMetricValue'],"
                            ":is([data-testid='column'],[data-testid='stColumn']):has("
                            ".valor-penalizacion-reactiva):not(:has("
                            ":is([data-testid='column'],[data-testid='stColumn']) "
                            ".valor-penalizacion-reactiva)) "
                            "[data-testid='stMetricValue'] *"
                            f"{{color:{color_valor_penalizacion} !important;}}"
                            "</style>"
                            "<span class='valor-penalizacion-reactiva' "
                            "style='display:none'></span>",
                            unsafe_allow_html=True,
                        )
                        st.metric(
                            'Penalización reactiva (€)',
                            formato_euros(total_penalizacion_reactiva),
                        )

                    c31,c32,c33=st.columns(3)
                    with c31:
                        st.metric('Factor de potencia mínimo', fp_min)
                    with c32:
                        st.metric('Factor de potencia medio', fp_med)
                    with c33:
                        st.metric('Factor de potencia máximo', fp_max)
                    resultado_compensacion = gestionar_form_compensacion()
                    if resultado_compensacion:
                        c31, c32, c33 = st.columns(3)
                        with c31:
                            st.metric(
                                ":yellow[Potencia mínima de compensación (kVAr)]",
                                formato_numero_es(
                                    resultado_compensacion["q_min"], 2
                                ),
                            )
                        with c32:
                            st.metric(
                                ":orange[Potencia mínima recomendada (kVAr)]",
                                formato_numero_es(
                                    resultado_compensacion["q_min_margen"], 2
                                ),
                                delta=(
                                    "cos φ "
                                    + formato_numero_es(
                                        resultado_compensacion[
                                            "fp_min_margen"
                                        ],
                                        3,
                                    )
                                ),
                            )
                        with c33:
                            st.metric(
                                ":green[Potencia de condensadores (kVAr)]",
                                formato_numero_es(
                                    resultado_compensacion["q_sel"], 2
                                ),
                                delta=(
                                    "cos φ "
                                    + formato_numero_es(
                                        resultado_compensacion["fp_aplicado"],
                                        3,
                                    )
                                ),
                            )
                        if (
                            resultado_compensacion["fp_aplicado"]
                            > resultado_compensacion["fp_solicitado"]
                        ):
                            st.info(
                                "El cos φ deseado se ha ajustado a "
                                f"{resultado_compensacion['fp_aplicado']:.3f} "
                                "porque no puede ser inferior al alcanzado con "
                                "la potencia mínima recomendada."
                            )
                with c2:
                    if resultado_compensacion:
                        st.plotly_chart(
                            resultado_compensacion["figura"],
                            use_container_width=True,
                        )

            alto_df_fmt = 460
            st.markdown(
                """
                <style>
                .tabla-reactiva-html {
                    overflow-x: auto;
                    margin-bottom: 1rem;
                }
                .tabla-reactiva-html table {
                    width: 100%;
                    border-collapse: collapse;
                    font-size: 0.9rem;
                }
                .tabla-reactiva-html th,
                .tabla-reactiva-html td {
                    padding: 0.35rem 0.5rem;
                    border-bottom: 1px solid rgba(128, 128, 128, 0.25);
                    text-align: right;
                }
                .tabla-reactiva-html th:first-child,
                .tabla-reactiva-html td:first-child {
                    text-align: left;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )
            def mostrar_tabla_reactiva_html(df, decimales=None):
                tabla_html = df.copy()
                tabla_html.columns = tabla_html.columns.map(str)
                tabla_html.columns.name = None
                tabla_html.index.name = None
                if decimales is not None:
                    columnas_numericas = tabla_html.select_dtypes(
                        include=[np.number]
                    ).columns
                    tabla_html[columnas_numericas] = tabla_html[
                        columnas_numericas
                    ].round(decimales)
                st.markdown(
                    "<div class='tabla-reactiva-html'>"
                    f"{tabla_html.to_html(index=False, border=0)}"
                    "</div>",
                    unsafe_allow_html=True,
                )

            penalizacion_grafico = df_coste_excesos_reactiva[
                ["Mes", "Total"]
            ].copy()
            penalizacion_grafico["Total"] = pd.to_numeric(
                penalizacion_grafico["Total"],
                errors="coerce",
            ).fillna(0)
            graf_penalizacion_reactiva = px.bar(
                penalizacion_grafico,
                x="Mes",
                y="Total",
                labels={"Mes": "", "Total": "Penalización (€)"},
                color_discrete_sequence=["#C94C4C"],
            )
            graf_penalizacion_reactiva.update_traces(
                hovertemplate=(
                    "<b>%{x}</b><br>Penalización: %{y:.2f} €"
                    "<extra></extra>"
                )
            )
            graf_penalizacion_reactiva = aplicar_estilo(
                graf_penalizacion_reactiva
            )
            graf_penalizacion_reactiva.update_layout(
                height=430,
                xaxis_title="",
                showlegend=False,
                barcornerradius=8,
                title="",
            )

            with st.container():
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.subheader('FP Factor de Potencia')
                    st.markdown(
                        "<div class='tabla-reactiva-html'>"
                        f"{styler_fp.hide(axis='index').to_html()}"
                        "</div>",
                        unsafe_allow_html=True,
                    )
                with c2:
                    st.subheader('Penalización (€) por excesos de REACTIVA')
                    st.markdown(
                        "<div class='tabla-reactiva-html'>"
                        f"{styler_coste_exc.hide(axis='index').to_html()}"
                        "</div>",
                        unsafe_allow_html=True,
                    )
                with c3:
                    st.subheader("Evolución mensual de la penalización (€)")
                    st.plotly_chart(
                        graf_penalizacion_reactiva,
                        use_container_width=True,
                    )

            with st.container():
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.subheader('Consumos mensuales (kWh)')
                    mostrar_tabla_reactiva_html(
                        tabla_mensual_consumos_reactiva_fmt
                    )
                with c2:
                    st.subheader('Reactiva mensual (kVArh)')
                    mostrar_tabla_reactiva_html(df_reactiva_fmt)
                with c3:
                    st.subheader('Excesos de REACTIVA (kVArh)')
                    mostrar_tabla_reactiva_html(df_excesos_react_fmt)

            if resultado_compensacion:
                df_q_condensadores_min_fmt = formatear_tabla_consumos(
                    resultado_compensacion["q_min_df"],
                    columna_mes="Mes",
                    incluir_unidades=False,
                )
                df_q_condensadores_sel_fmt = formatear_tabla_consumos(
                    resultado_compensacion["q_sel_df"],
                    columna_mes="Mes",
                    incluir_unidades=False,
                )
                coef_min_mostrar = (
                    resultado_compensacion["coef_min"]
                    .copy()
                    .round(3)
                )
                coef_sel_mostrar = (
                    resultado_compensacion["coef_sel"]
                    .copy()
                    .round(3)
                )
                with st.container():
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.subheader("Coeficientes K MÍNIMO")
                        mostrar_tabla_reactiva_html(
                            coef_min_mostrar,
                            decimales=3,
                        )
                    with c2:
                        st.subheader("Coeficientes K SELECCIONADO")
                        mostrar_tabla_reactiva_html(
                            coef_sel_mostrar,
                            decimales=3,
                        )
                    with c3:
                        st.subheader("Potencia media demandada (kW)")
                        mostrar_tabla_reactiva_html(
                            df_potmed_qh_fmt
                        )

                with st.container():
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.subheader("Q (kVAr) COMPENSACIÓN MÍNIMA")
                        mostrar_tabla_reactiva_html(
                            df_q_condensadores_min_fmt,
                        )
                    with c2:
                        st.subheader("Q (kVAr) COMPENSACIÓN SELECCIONADA")
                        mostrar_tabla_reactiva_html(
                            df_q_condensadores_sel_fmt,
                        )

    with tab6:
        st.subheader("Informe de compensación", divider="rainbow")
        informe_base = st.session_state.get("reactiva_base_cache")
        informe_compensacion = st.session_state.get("reactiva_compensacion")

        if not informe_base:
            st.info(
                "Carga una curva con datos de reactiva para preparar el informe."
            )
        elif not informe_compensacion:
            st.info(
                "Pulsa «Calcular compensación» en la pestaña Reactiva antes "
                "de preparar el informe."
            )
        else:
            col_datos_informe, col_previa_informe = st.columns([0.38, 0.62])
            with col_datos_informe:
                st.caption(
                    "Completa los datos del cliente y del realizador. Estos "
                    "campos siguen el mismo esquema utilizado en Factura."
                )
                with st.container(border=True):
                    st.markdown("#### Datos del cliente y del suministro")
                    col_cliente, col_nif = st.columns([0.68, 0.32])
                    col_cliente.text_input(
                        "Cliente / Razón social",
                        key="reactiva_informe_cliente",
                    )
                    col_nif.text_input(
                        "NIF / CIF",
                        key="reactiva_informe_nif",
                    )
                    st.text_input(
                        "Dirección",
                        key="reactiva_informe_direccion",
                    )
                    col_cups, col_atr = st.columns([0.68, 0.32])
                    col_cups.text_input(
                        "CUPS",
                        key="reactiva_informe_cups",
                    )
                    col_atr.text_input(
                        "ATR",
                        value=str(st.session_state.get("atr_dfnorm", "")),
                        key="reactiva_informe_atr",
                    )

                with st.container(border=True):
                    st.markdown("#### Datos del informe")
                    col_autor, col_fecha = st.columns([0.60, 0.40])
                    col_autor.text_input(
                        "Realizado por",
                        key="reactiva_informe_realizado_por",
                    )
                    col_fecha.text_input(
                        "Fecha de realización",
                        value=pd.Timestamp.today().strftime("%d/%m/%Y"),
                        key="reactiva_informe_fecha",
                    )
                    st.text_input(
                        "Objeto del estudio",
                        value=(
                            "Analizar la penalización por energía reactiva y "
                            "dimensionar su compensación."
                        ),
                        key="reactiva_informe_objeto",
                    )

                with st.container(border=True):
                    st.markdown("#### Personalización")
                    logo_reactiva = st.file_uploader(
                        "Logo para el informe",
                        type=["png", "jpg", "jpeg"],
                        accept_multiple_files=False,
                        key="reactiva_informe_logo",
                    )
                    if logo_reactiva is not None:
                        st.image(logo_reactiva, width=180)

                preparar_informe_reactiva = st.button(
                    "Preparar informe",
                    type="primary",
                    use_container_width=True,
                    key="preparar_informe_reactiva",
                )

            with col_previa_informe:
                if preparar_informe_reactiva:
                    def figura_data_uri(figura, ancho=1100, alto=520):
                        try:
                            imagen = figura.to_image(
                                format="png",
                                width=ancho,
                                height=alto,
                                scale=1.5,
                            )
                            return (
                                "data:image/png;base64,"
                                + base64.b64encode(imagen).decode("ascii")
                            )
                        except Exception:
                            return ""

                    logo_data = ""
                    if logo_reactiva is not None:
                        subtipo = (
                            "jpeg"
                            if logo_reactiva.type == "image/jpeg"
                            else "png"
                        )
                        logo_data = (
                            f"data:image/{subtipo};base64,"
                            + base64.b64encode(
                                logo_reactiva.getvalue()
                            ).decode("ascii")
                        )

                    df_fp_informe = informe_base["fp"].copy()
                    df_fp_informe.columns.name = None
                    df_excesos_informe = informe_base["excesos"].copy()
                    df_excesos_informe.columns.name = None
                    for tabla in (df_fp_informe, df_excesos_informe):
                        for columna in tabla.columns:
                            if columna != "Mes":
                                tabla[columna] = pd.to_numeric(
                                    tabla[columna],
                                    errors="coerce",
                                ).round(2)

                    penalizacion_informe = float(
                        informe_base["costes"]["Total"].sum()
                    )
                    fp_informe = informe_base["fp"]
                    fp_medio_informe = float(fp_informe["Total"].mean())
                    periodo_informe = (
                        f"{st.session_state.df_norm['fecha_hora'].min():%d/%m/%Y}"
                        " – "
                        f"{st.session_state.df_norm['fecha_hora'].max():%d/%m/%Y}"
                    )
                    contexto_informe = {
                        "logo": logo_data,
                        "cliente": escape(st.session_state.get(
                            "reactiva_informe_cliente", ""
                        )),
                        "nif": escape(st.session_state.get(
                            "reactiva_informe_nif", ""
                        )),
                        "direccion": escape(st.session_state.get(
                            "reactiva_informe_direccion", ""
                        )),
                        "cups": escape(st.session_state.get(
                            "reactiva_informe_cups", ""
                        )),
                        "atr": escape(st.session_state.get(
                            "reactiva_informe_atr", ""
                        )),
                        "realizado_por": escape(st.session_state.get(
                            "reactiva_informe_realizado_por", ""
                        )),
                        "fecha_realizacion": escape(st.session_state.get(
                            "reactiva_informe_fecha", ""
                        )),
                        "objeto": escape(st.session_state.get(
                            "reactiva_informe_objeto", ""
                        )),
                        "periodo": periodo_informe,
                        "penalizacion": formato_euros(
                            penalizacion_informe
                        ),
                        "mensaje_penalizacion": (
                            "Existe coste evitable asociado al exceso de "
                            "energía reactiva."
                            if penalizacion_informe > 0
                            else "No se estima penalización en el periodo."
                        ),
                        "q_minima": (
                            f"{formato_numero_es(informe_compensacion['q_min'], 2)} "
                            "kVAr"
                        ),
                        "q_recomendada": (
                            f"{formato_numero_es(informe_compensacion['q_min_margen'], 2)} "
                            "kVAr"
                        ),
                        "q_propuesta": (
                            f"{formato_numero_es(informe_compensacion['q_sel'], 2)} "
                            "kVAr"
                        ),
                        "fp_medio": formato_numero_es(fp_medio_informe, 3),
                        "fp_margen": formato_numero_es(
                            informe_compensacion["fp_min_margen"], 3
                        ),
                        "fp_propuesto": formato_numero_es(
                            informe_compensacion["fp_aplicado"], 3
                        ),
                        "grafico_compensacion": figura_data_uri(
                            informe_compensacion["figura"]
                        ),
                        "grafico_penalizacion": figura_data_uri(
                            graf_penalizacion_reactiva
                        ),
                        "tabla_fp": df_fp_informe.to_html(
                            index=False,
                            border=0,
                            na_rep="—",
                        ),
                        "tabla_excesos": df_excesos_informe.to_html(
                            index=False,
                            border=0,
                            na_rep="—",
                        ),
                    }
                    ruta_plantilla = (
                        Path(__file__).resolve().parent.parent
                        / "templates"
                        / "informe_reactiva.html"
                    )
                    entorno = Environment(
                        loader=FileSystemLoader(str(ruta_plantilla.parent))
                    )
                    html_informe_reactiva = entorno.get_template(
                        ruta_plantilla.name
                    ).render(**contexto_informe)
                    st.session_state.informe_reactiva_html = (
                        html_informe_reactiva
                    )

                html_informe_reactiva = st.session_state.get(
                    "informe_reactiva_html"
                )
                if html_informe_reactiva:
                    st.markdown("#### Vista previa")
                    st.components.v1.html(
                        html_informe_reactiva,
                        height=980,
                        scrolling=True,
                    )
                    nombre_cliente = re.sub(
                        r"[^A-Za-z0-9._-]+",
                        "_",
                        st.session_state.get(
                            "reactiva_informe_cliente", ""
                        ),
                    ).strip("._") or "cliente"
                    st.download_button(
                        "Descargar informe HTML",
                        data=html_informe_reactiva.encode("utf-8"),
                        file_name=(
                            f"informe_compensacion_reactiva_{nombre_cliente}.html"
                        ),
                        mime="text/html; charset=utf-8",
                        use_container_width=True,
                    )
                else:
                    st.info(
                        "La vista previa aparecerá aquí al preparar el informe."
                    )






