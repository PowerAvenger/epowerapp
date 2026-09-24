import streamlit as st
import numpy as np
import pandas as pd
import io
import base64
import re
import json
import sqlite3
from html import escape
from pathlib import Path
from dateutil.relativedelta import relativedelta
from datetime import timedelta
import plotly.express as px
from jinja2 import Environment, FileSystemLoader
from backend_curvadecarga import (
    obtener_datos_contador,
    obtener_suministros_datadis,
    obtener_detalle_contrato_datadis, extraer_potencias_contratadas_datadis,
    obtener_consumo_datadis_cacheado, dataframe_como_archivo_curva,
    dividir_energias_curva,
    graficar_curva_horaria, graficar_diario_apilado, graficar_mensual_apilado, tabla_mensual_periodos, formatear_tabla_mensual_es, graficar_queso_periodos,
    graficar_media_horaria, graficar_media_horaria_combinada, graficar_boxplot_horario,
    graficar_dem_ver_mensual, graficar_con_gen_mensual,
    graficar_heatmap_dia_hora,
    calcular_patron_horario_boxplot, detectar_consumos_atipicos_horarios,
    resumir_atipicos_por_dia, calcular_kpis_atipicos, mostrar_kpis_atipicos, graficar_top_dias_revisables, graficar_heatmap_alertas, calcular_patron_horario_boxplot, obtener_top_horas_revisables,
    calcular_tabla_excesos_reactiva, calcular_tabla_factor_potencia, estilo_factor_potencia, calcular_tabla_precio_penalizacion_reactiva, calcular_tabla_coste_excesos_reactiva, estilo_coste_penalizacion,
    calcular_tabla_potencia_media_qh,calcular_tabla_coef_k, calcular_tabla_q_condensadores,
    calcular_comparacion, calcular_comparacion_costes,
    calcular_comparativa_ahorro,
    filtrar_intervalos_comparacion,
    preparar_costes_mensuales_rango,
    )
from backend_comun import (
    aplicar_estilo,
    formatear_tabla_consumos,
    formatear_columnas_tabla,
)
from formato_es import formato_euros, formato_kwh, formato_numero_es
from informe_comparativa import mostrar_informe_comparativa



from utilidades import (
    actualizar_df_index_por_zona,
    generar_menu,
    init_app,
    init_app_index,
    mostrar_parametros_formula_indexado,
)
from backend_indexado import FormulaIndexada
from backend_telemindex import (
    añadir_costes_curva,
    construir_df_curva_sheets,
    evol_mensual,
)
from backend_contractual import (
    aplicar_condiciones_contractuales,
    aplicar_costes_extra_mensuales,
    cargar_condiciones_cups,
    cargar_costes_extra_cups,
    cargar_datos_suministro,
    condicion_como_referencia,
    condicion_manual_como_referencia,
    referencias_del_mismo_registro,
    ultimo_dia_cubierto_desde,
    guardar_costes_extra_cups,
    preparar_indexado_contractual,
    resumir_calculo_contractual,
)
from servicio_curva import (
    limpiar_curva_sesion,
    normalizar_fuentes_curva,
    publicar_curva_sesion,
    sincronizar_curva_sesion,
)
from componentes_curva import (
    OPCIONES_ATR_CURVA,
    anio_anterior_y_actual,
    excluir_periodo_automatico,
    guardar_selector_atr_curva,
    preparar_selector_atr_curva,
    render_campos_axon,
    render_campos_archivo_curva,
)
from data_beta.axon_access import listar_suministros_axon
from data_beta.contract_periods import (
    listar_periodos_cups,
    sugerir_cambios_contrato,
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
periodos_en_entrada = None


def ultimos_doce_meses_completos(fecha_referencia=None):
    """Devuelve desde el primer día de M-12 hasta el último día de M-1."""
    referencia = pd.Timestamp(
        fecha_referencia if fecha_referencia is not None else pd.Timestamp.today()
    ).normalize()
    fin = referencia.replace(day=1) - pd.Timedelta(days=1)
    inicio = (fin.to_period("M") - 11).start_time
    return inicio.date(), fin.date()


def cargar_widget_desde_sesion(clave_widget, clave_sesion, valor_defecto=""):
    """Restaura un widget que Streamlit pudo eliminar al ocultarlo o navegar."""
    if clave_widget not in st.session_state:
        st.session_state[clave_widget] = st.session_state.get(
            clave_sesion, valor_defecto
        )


def guardar_widget_en_sesion(clave_widget, clave_sesion):
    """Copia inmediatamente el valor temporal del widget a estado permanente."""
    st.session_state[clave_sesion] = st.session_state.get(clave_widget)


def usar_vigencia_en_ahorro(inicio, fin, condicion_referencia_id):
    """Aplica el periodo sugerido y conserva el precio de referencia elegido."""
    rango = (inicio, fin)
    st.session_state.rango_ahorro_widget = rango
    st.session_state.rango_ahorro_seleccionado = rango
    if st.session_state.get("origen_referencia_ahorro") == "Condición anterior del contrato":
        st.session_state.condicion_referencia_ahorro = condicion_referencia_id


def guardar_preferencias_datadis_sesion():
    """Persiste todos los campos de acceso antes de realizar una llamada remota."""
    for clave_widget, clave_sesion in (
        ("_curva_datadis_usuario", "datadis_usuario_sesion"),
        ("_curva_datadis_password", "datadis_password_sesion"),
        ("_curva_datadis_acceso", "datadis_acceso_sesion"),
        ("_curva_datadis_nif", "datadis_nif_sesion"),
    ):
        if clave_widget in st.session_state:
            guardar_widget_en_sesion(clave_widget, clave_sesion)


ETIQUETAS_ZONA_PERIODOS = {
    "peninsula": "Península",
    "baleares": "Baleares",
    "canarias": "Canarias",
    "ceuta": "Ceuta",
    "melilla": "Melilla",
}


def guardar_zona_confirmada_curva():
    """Conserva en el contrato común la zona confirmada por el usuario."""
    curva_actual = st.session_state.get("curva_actual")
    if curva_actual is not None:
        curva_actual["zona_confirmada"] = st.session_state.get(
            "zona_periodos_confirmada"
        )


def mostrar_zonas_compatibles(slot, zonas, cobertura):
    """Informa la inferencia y pide confirmación cuando no es unívoca."""
    with slot.container():
        if not zonas:
            st.info(
                "La curva incluye periodos, pero no se ha podido asociar de "
                "forma fiable a uno de los calendarios disponibles. Los "
                "periodos del archivo se respetarán."
            )
            return
        etiquetas = [ETIQUETAS_ZONA_PERIODOS[zona] for zona in zonas]
        if len(zonas) == 1:
            st.session_state.zona_periodos_confirmada = zonas[0]
            guardar_zona_confirmada_curva()
            st.info(
                f"Zona compatible con los periodos: **{etiquetas[0]}**. "
                "Se respetarán los periodos del archivo."
            )
            return

        st.info(
            "Los periodos son compatibles con varias zonas: "
            f"**{', '.join(etiquetas)}**. Confirma la zona del suministro."
        )
        zona_guardada = st.session_state.get("zona_periodos_confirmada")
        if zona_guardada not in zonas:
            st.session_state.zona_periodos_confirmada = (
                "peninsula" if "peninsula" in zonas else zonas[0]
            )
        st.selectbox(
            "Zona del suministro",
            zonas,
            key="zona_periodos_confirmada",
            format_func=ETIQUETAS_ZONA_PERIODOS.get,
            on_change=guardar_zona_confirmada_curva,
        )
        guardar_zona_confirmada_curva()


def limpiar_curva_cargada():
    """Elimina la curva y los resultados calculados en esta sesión."""
    limpiar_curva_sesion(st.session_state)


tab_curva, tab1, tab2, tab3, tab4, tab_ahorro, tab5, tab6 = st.tabs(
    [
        "Curva",
        "Resumen",
        "Perfiles Horarios",
        "Autoconsumo",
        "Efecto consumo/precio",
        "Comparativa de ahorro",
        "Reactiva",
        "Informes",
    ]
)

with tab_curva:
    col_curva_entrada, col_curva_vista, col_curva_info = st.columns(
        [0.27, 0.46, 0.27],
        gap="large",
    )

    with col_curva_entrada:
        st.subheader("Datos de entrada", divider="rainbow")
        st.caption("Selecciona el origen de la curva.")
        zona_periodos_slot = None
        zona_control_con_inferencia = False

        if not st.session_state.get('usuario_autenticado', False):
            st.warning(
                "🔒 Este módulo es solo para usuarios premium. "
                "Se utilizará un fichero de ejemplo."
            )
            origen_curva = "Archivo CSV/Excel"
            uploaded = "curvas/qh anual demo.csv"
            atr_dfnorm = "3.0"
        else:
            cargar_widget_desde_sesion(
                "_origen_curva_cdc", "origen_curva_cdc_sesion",
                "Archivo CSV/Excel",
            )
            origen_curva = st.radio(
                "Origen de la curva",
                ("Archivo CSV/Excel", "Axon", "Datadis"),
                index=0,
                horizontal=True,
                key="_origen_curva_cdc",
                on_change=guardar_widget_en_sesion,
                args=("_origen_curva_cdc", "origen_curva_cdc_sesion"),
            )
            uploaded = None
            if origen_curva == "Archivo CSV/Excel":
                campos_archivo = render_campos_archivo_curva("curva_carga")
                uploaded = campos_archivo["archivos"]
                hoja_curva_excel = campos_archivo["hoja_excel"]
                periodos_en_entrada = campos_archivo["trae_periodos"]
            elif origen_curva == "Axon":
                if st.session_state.get("es_admin", False):
                    try:
                        suministros_axon = listar_suministros_axon()
                    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
                        suministros_axon = []
                        st.warning(f"No se pudo consultar la lista de CUPS Axon: {exc}")

                    por_cups = {fila["cups"]: fila for fila in suministros_axon}
                    if suministros_axon:
                        cups_guardado_sesion = st.session_state.get(
                            "curva_carga_axon_cups_guardado_sesion", ""
                        )
                        if st.session_state.get(
                            "curva_carga_axon_cups_guardado", cups_guardado_sesion
                        ) not in ("", *por_cups):
                            st.session_state["curva_carga_axon_cups_guardado"] = ""
                        cargar_widget_desde_sesion(
                            "curva_carga_axon_cups_guardado",
                            "curva_carga_axon_cups_guardado_sesion",
                        )
                        cups_elegido = st.selectbox(
                            "CUPS Axon guardado",
                            ("", *por_cups),
                            format_func=lambda cups: (
                                "Selecciona un CUPS"
                                if not cups else (
                                    f"{cups} · {por_cups[cups]['denominacion']}"
                                    if por_cups[cups]["denominacion"] else cups
                                )
                            ),
                            key="curva_carga_axon_cups_guardado",
                            on_change=guardar_widget_en_sesion,
                            args=(
                                "curva_carga_axon_cups_guardado",
                                "curva_carga_axon_cups_guardado_sesion",
                            ),
                        )
                    else:
                        cups_elegido = ""
                        st.caption("No hay CUPS Axon disponibles en la base local.")

                    referencia = (
                        por_cups[cups_elegido]["credencial_ref"]
                        if cups_elegido else "axon_principal"
                    )
                    atr_bbdd = por_cups[cups_elegido]["atr"] if cups_elegido else ""
                    atr_normalizado = re.sub(r"\s+", "", atr_bbdd.upper())
                    if atr_normalizado.endswith("TD"):
                        atr_normalizado = atr_normalizado[:-2]
                    contexto_axon = (cups_elegido, referencia, atr_bbdd)
                    if st.session_state.get("_curva_axon_contexto") != contexto_axon:
                        if cups_elegido:
                            st.session_state["curva_carga_axon_cups"] = cups_elegido
                            st.session_state.axon_cups_sesion = cups_elegido
                            if atr_normalizado in OPCIONES_ATR_CURVA:
                                st.session_state.atr_curva_preferido = atr_normalizado
                        credencial = st.secrets.get("MEASURE_CREDENTIALS", {}).get(
                            referencia, {}
                        ) if referencia else {}
                        if str(credencial.get("proveedor", "")).upper() == "AXON":
                            st.session_state.axon_usuario_sesion = str(
                                credencial.get("usuario", "")
                            )
                            st.session_state.axon_password_sesion = str(
                                credencial.get("password", "")
                            )
                        elif cups_elegido:
                            st.session_state.axon_usuario_sesion = ""
                            st.session_state.axon_password_sesion = ""
                        st.session_state["_curva_axon_contexto"] = contexto_axon
                    if cups_elegido and atr_normalizado not in OPCIONES_ATR_CURVA:
                        st.caption(
                            "Este CUPS no tiene un peaje compatible en la base; "
                            "selecciónalo manualmente."
                        )
                campos_axon = render_campos_axon("curva_carga")
                usuario_axon = campos_axon["usuario"]
                password_axon = campos_axon["password"]
                cups_axon = campos_axon["cups"]
                cups_axon_base = campos_axon["cups_base"]
                rango_axon = campos_axon["rango"]
                tipo_curva_axon = campos_axon["tipo"]
            else:
                cargar_widget_desde_sesion(
                    "_curva_datadis_usuario", "datadis_usuario_sesion"
                )
                cargar_widget_desde_sesion(
                    "_curva_datadis_password", "datadis_password_sesion"
                )
                cargar_widget_desde_sesion(
                    "_curva_datadis_acceso", "datadis_acceso_sesion", "Titular"
                )
                usuario_datadis = st.text_input(
                    "Usuario Datadis",
                    key="_curva_datadis_usuario",
                    on_change=guardar_widget_en_sesion,
                    args=("_curva_datadis_usuario", "datadis_usuario_sesion"),
                )
                password_datadis = st.text_input(
                    "Contraseña Datadis",
                    type="password",
                    key="_curva_datadis_password",
                    on_change=guardar_widget_en_sesion,
                    args=("_curva_datadis_password", "datadis_password_sesion"),
                )
                acceso_datadis = st.radio(
                    "Acceso",
                    ("Titular", "Autorizado"),
                    horizontal=True,
                    key="_curva_datadis_acceso",
                    on_change=guardar_widget_en_sesion,
                    args=("_curva_datadis_acceso", "datadis_acceso_sesion"),
                )
                authorized_nif_datadis = ""
                if acceso_datadis == "Autorizado":
                    cargar_widget_desde_sesion(
                        "_curva_datadis_nif", "datadis_nif_sesion"
                    )
                    authorized_nif_datadis = st.text_input(
                        "NIF del titular",
                        key="_curva_datadis_nif",
                        on_change=guardar_widget_en_sesion,
                        args=("_curva_datadis_nif", "datadis_nif_sesion"),
                    )

                if st.button(
                    "Consultar suministros",
                    use_container_width=True,
                    key="consultar_suministros_datadis",
                    disabled=not bool(
                        str(usuario_datadis or "").strip()
                        and str(password_datadis or "")
                        and (
                            acceso_datadis != "Autorizado"
                            or str(authorized_nif_datadis or "").strip()
                        )
                    ),
                ):
                    # Se guarda antes de la petición: incluso si Datadis agota el
                    # timeout o el usuario navega, los campos podrán restaurarse.
                    guardar_preferencias_datadis_sesion()
                    try:
                        with st.spinner("Consultando suministros en Datadis…"):
                            suministros_consultados = obtener_suministros_datadis(
                                usuario_datadis,
                                password_datadis,
                                authorized_nif=authorized_nif_datadis,
                            )
                        # Usar un índice interno limpio evita que un índice devuelto
                        # por pandas termine siendo una opción ambigua del selectbox.
                        st.session_state.suministros_datadis = (
                            suministros_consultados.reset_index(drop=True)
                        )
                        st.session_state.datadis_suministros_mensaje = (
                            "success",
                            f"Se han encontrado {len(suministros_consultados)} "
                            "suministro(s).",
                        )
                    except Exception as e:
                        st.session_state.pop("suministros_datadis", None)
                        st.session_state.datadis_suministros_mensaje = (
                            "error",
                            f"No se pudieron consultar los suministros: {e}",
                        )

                mensaje_datadis = st.session_state.get(
                    "datadis_suministros_mensaje"
                )
                if mensaje_datadis:
                    tipo_mensaje, texto_mensaje = mensaje_datadis
                    getattr(st, tipo_mensaje)(texto_mensaje)

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
                        key="suministro_datadis_seleccionado",
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
                inicio_12m, fin_12m = ultimos_doce_meses_completos()
                mes_inicio_12m = pd.Timestamp(inicio_12m).strftime("%Y/%m")
                mes_fin_12m = pd.Timestamp(fin_12m).strftime("%Y/%m")
                inicio_dos_anios, _ = anio_anterior_y_actual()
                mes_inicio_dos_anios = pd.Timestamp(inicio_dos_anios).strftime("%Y/%m")
                for clave_mes_datadis in (
                    "mes_inicio_datadis",
                    "mes_fin_datadis",
                ):
                    if (
                        clave_mes_datadis not in st.session_state
                        or st.session_state[clave_mes_datadis] not in meses_datadis
                    ):
                        st.session_state[clave_mes_datadis] = mes_anterior_datadis
                seleccionar_12m_datadis = st.checkbox(
                    "Seleccionar automáticamente los últimos 12 meses completos",
                    key="seleccionar_12m_completos_datadis",
                    on_change=excluir_periodo_automatico,
                    args=(
                        "seleccionar_12m_completos_datadis",
                        "seleccionar_dos_anios_datadis",
                    ),
                    help=(
                        "Excluye el mes actual. Por ejemplo, en agosto selecciona "
                        "desde agosto del año anterior hasta julio."
                    ),
                )
                seleccionar_dos_anios_datadis = st.checkbox(
                    "Seleccionar el año anterior completo y el año actual",
                    key="seleccionar_dos_anios_datadis",
                    on_change=excluir_periodo_automatico,
                    args=(
                        "seleccionar_dos_anios_datadis",
                        "seleccionar_12m_completos_datadis",
                    ),
                    help="Desde enero del año anterior hasta el mes actual.",
                )
                if seleccionar_12m_datadis:
                    st.session_state.mes_inicio_datadis = mes_inicio_12m
                    st.session_state.mes_fin_datadis = mes_fin_12m
                elif seleccionar_dos_anios_datadis:
                    st.session_state.mes_inicio_datadis = mes_inicio_dos_anios
                    st.session_state.mes_fin_datadis = str(mes_actual_datadis).replace("-", "/")
                col_mes_inicio, col_mes_fin = st.columns(2)
                with col_mes_inicio:
                    mes_inicio_datadis = st.selectbox(
                        "Mes inicial",
                        meses_datadis,
                        key="mes_inicio_datadis",
                        disabled=seleccionar_12m_datadis or seleccionar_dos_anios_datadis,
                    )
                with col_mes_fin:
                    mes_fin_datadis = st.selectbox(
                        "Mes final",
                        meses_datadis,
                        key="mes_fin_datadis",
                        disabled=seleccionar_12m_datadis or seleccionar_dos_anios_datadis,
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
            clave_atr_entrada_cdc = "atr_dfnorm_entrada_cdc"
            preparar_selector_atr_curva(clave_atr_entrada_cdc)
            atr_dfnorm = st.selectbox(
                "Selecciona peaje de acceso",
                OPCIONES_ATR_CURVA,
                key=clave_atr_entrada_cdc,
                on_change=guardar_selector_atr_curva,
                args=(clave_atr_entrada_cdc,),
            )
            zona_periodos_slot = st.empty()
            zona_control_con_inferencia = False
            if origen_curva == "Archivo CSV/Excel" and uploaded:
                periodos_para_interfaz = periodos_en_entrada is True
            else:
                periodos_para_interfaz = st.session_state.get(
                    "curva_periodos_en_origen", False
                )
            if periodos_para_interfaz:
                curva_actual = st.session_state.get("curva_actual") or {}
                nombres_entrada = [
                    str(getattr(archivo, "name", archivo))
                    for archivo in (uploaded or [])
                ] if origen_curva == "Archivo CSV/Excel" else []
                misma_entrada = (
                    not nombres_entrada
                    or nombres_entrada == curva_actual.get("nombres_archivos")
                )
                zonas_compatibles = (
                    curva_actual.get("zonas_compatibles")
                    if misma_entrada else None
                )
                if zonas_compatibles is not None:
                    mostrar_zonas_compatibles(
                        zona_periodos_slot,
                        zonas_compatibles,
                        curva_actual.get("cobertura_zonas", 0.0),
                    )
                    zona_control_con_inferencia = True
                else:
                    zona_periodos_slot.info(
                        "La curva ya incluye periodos. Al normalizar se "
                        "comprobarán las zonas compatibles."
                    )
            else:
                opciones_zona_periodos = [
                    "peninsula", "baleares", "canarias", "ceuta", "melilla"
                ]
                with zona_periodos_slot.container():
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

        entrada_lista = True
        motivo_entrada_pendiente = ""
        if st.session_state.get('usuario_autenticado', False):
            if origen_curva == "Archivo CSV/Excel":
                entrada_lista = bool(uploaded)
                motivo_entrada_pendiente = "Sube al menos un archivo CSV o Excel."
            elif origen_curva == "Axon":
                rango_axon_valido = (
                    isinstance(rango_axon, (tuple, list))
                    and len(rango_axon) == 2
                    and rango_axon[0] <= rango_axon[1]
                )
                entrada_lista = bool(
                    str(usuario_axon or "").strip()
                    and str(password_axon or "")
                    and len(cups_axon_base) == 20
                    and rango_axon_valido
                )
                motivo_entrada_pendiente = (
                    "Completa usuario, contraseña, un CUPS válido y el periodo de Axon."
                )
            else:
                nif_requerido_valido = (
                    acceso_datadis != "Autorizado"
                    or bool(str(authorized_nif_datadis or "").strip())
                )
                rango_datadis_valido = mes_inicio_datadis <= mes_fin_datadis
                entrada_lista = bool(
                    str(usuario_datadis or "").strip()
                    and str(password_datadis or "")
                    and nif_requerido_valido
                    and suministro_datadis is not None
                    and rango_datadis_valido
                )
                if suministro_datadis is None:
                    motivo_entrada_pendiente = (
                        "Consulta los suministros y selecciona uno antes de continuar."
                    )
                elif not rango_datadis_valido:
                    motivo_entrada_pendiente = (
                        "El mes inicial no puede ser posterior al mes final."
                    )
                else:
                    motivo_entrada_pendiente = (
                        "Completa las credenciales y los datos de acceso de Datadis."
                    )

        normalizar = st.button(
            "Obtener y normalizar curva"
            if origen_curva in {"Axon", "Datadis"}
            else "Normalizar curva de carga",
            type="primary",
            use_container_width=True,
            disabled=not entrada_lista,
        )
        if not entrada_lista:
            st.caption(motivo_entrada_pendiente)
        st.button(
            "🗑️ Eliminar curva y resultados",
            use_container_width=True,
            on_click=limpiar_curva_cargada,
            help=(
                "Elimina la curva cargada, sus cálculos y las cachés de curva "
                "y Datadis de esta sesión. No borra archivos originales, "
                "preferencias, usuario ni cachés globales de otros módulos."
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
        st.session_state.cups_curva = re.sub(
            r"[^A-Z0-9]", "", str(cups_axon or "").upper()
        )
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
        st.session_state.cups_curva = str(
            suministro_datadis.get("cups", "") or ""
        ).strip().upper()
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
        resultado_curva = normalizar_fuentes_curva(
            uploaded,
            atr=atr_dfnorm,
            zona_periodos=st.session_state.get(
                "zona_periodos_cdc", "peninsula"
            ),
            excel_sheet=hoja_curva_excel,
        )
        publicar_curva_sesion(st.session_state, resultado_curva)

        df_norm = resultado_curva.df_norm
        df_norm_h = resultado_curva.df_norm_h
        df_in = resultado_curva.df_in
        frec = resultado_curva.frecuencia
        atr_dfnorm = resultado_curva.atr
        periodos_en_todos_los_origenes = (
            resultado_curva.periodos_en_origen
        )
        if (
            periodos_en_todos_los_origenes
            and zona_periodos_slot is not None
            and not zona_control_con_inferencia
        ):
            mostrar_zonas_compatibles(
                zona_periodos_slot,
                resultado_curva.zonas_compatibles,
                resultado_curva.cobertura_zonas,
            )
        zona_mensajes.success("✅ Curva normalizada correctamente")
        if resultado_curva.mensajes_unidades:
            zona_mensajes2.info(
                " · ".join(resultado_curva.mensajes_unidades), icon="ℹ️"
            )

        # --- Obtención de periodos ------------------------------------------------
        if not periodos_en_todos_los_origenes:
            msg_periodos = 'Cargados periodos desde fichero auxiliar.'
            zona_mensajes3.warning(msg_periodos, icon="⚠️")
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
                (
                    f"{etiqueta}: {formato_numero_es(diagnostico.get(campo, 0))}"
                    + (
                        " · posible repetición del cambio horario de octubre; "
                        "se conservan ambas lecturas"
                        if campo == "duplicados_fecha_hora"
                        and diagnostico.get(
                            "duplicados_cambio_hora_octubre", 0
                        ) > 0
                        else ""
                    )
                )
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
            # PyArrow necesita etiquetas de texto unicas. Las columnas sin
            # nombre pueden convertirse ambas en "nan" al mostrar el origen.
            etiquetas_originales = [str(columna) for columna in df_in_preview.columns]
            etiquetas_reservadas = set(etiquetas_originales)
            etiquetas_usadas = set()
            etiquetas_preview = []
            for etiqueta in etiquetas_originales:
                nombre = etiqueta
                sufijo = 2
                while nombre in etiquetas_usadas or (
                    nombre != etiqueta and nombre in etiquetas_reservadas
                ):
                    nombre = f"{etiqueta} ({sufijo})"
                    sufijo += 1
                etiquetas_preview.append(nombre)
                etiquetas_usadas.add(nombre)
            df_in_preview.columns = etiquetas_preview
            df_in_preview.index.name = None
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
        conversion_energia = st.selectbox(
            "Conversión manual de unidades",
            options=(
                "Multiplicar por 1.000 (MWh → kWh)",
                "Dividir por 1.000 (Wh → kWh)",
            ),
            key="conversion_energias_curva_1000",
            disabled=st.session_state.get(
                "curva_escala_manual_1000_aplicada", False
            ),
            help=(
                "Reescala consumo, excedentes, generación y energía "
                "reactiva/capacitiva. No modifica fechas, horas ni periodos."
            ),
        )
        if st.button(
            "Aplicar conversión",
            key="dividir_energias_curva_1000",
            disabled=st.session_state.get(
                "curva_escala_manual_1000_aplicada", False
            ),
            use_container_width=True,
        ):
            divisor_energia = (
                0.001
                if conversion_energia.startswith("Multiplicar")
                else 1000.0
            )
            st.session_state.df_norm = dividir_energias_curva(
                st.session_state.df_norm, divisor=divisor_energia
            )
            st.session_state.df_norm_h = dividir_energias_curva(
                st.session_state.df_norm_h, divisor=divisor_energia
            )
            df_norm_reescalada = st.session_state.df_norm
            st.session_state.consumo_total = df_norm_reescalada[
                "consumo_kWh"
            ].sum()
            st.session_state.vertido_total = df_norm_reescalada[
                "excedentes_kWh"
            ].sum()
            st.session_state.consumo_neto = df_norm_reescalada[
                "consumo_neto_kWh"
            ].sum()
            st.session_state.vertido_neto = df_norm_reescalada[
                "vertido_neto_kWh"
            ].sum()
            st.session_state.reactiva_total = df_norm_reescalada[
                "reactiva_kVArh"
            ].sum()
            st.session_state.csv_bytes_norm = (
                df_norm_reescalada.reset_index(drop=True)
                .to_csv(index=False, sep=";", decimal=",", float_format="%.3f")
                .encode("utf-8")
            )
            st.session_state.csv_bytes_h = (
                st.session_state.df_norm_h.reset_index(drop=True)
                .to_csv(index=False, sep=";", decimal=",", float_format="%.3f")
                .encode("utf-8")
            )
            st.session_state.curva_escala_manual_1000_aplicada = True
            st.session_state.curva_reactiva_version = (
                st.session_state.get("curva_reactiva_version", 0) + 1
            )
            for clave_derivada in (
                "df_curva_sheets",
                "precios_mensuales",
                "resumen_costes_contractuales",
                "origen_costes_comparativa",
                "cups_costes_comparativa",
                "version_curva_costes_comparativa",
                "reactiva_base_cache",
                "reactiva_compensacion",
                "informe_reactiva_html",
                "df_consumos_pricing",
                "df_consumos_pricing_origen",
                "df_curva_simulindex_persistente",
                "_firma_curva_simulindex",
            ):
                st.session_state.pop(clave_derivada, None)
            sincronizar_curva_sesion(st.session_state)
            st.rerun()
        total_filas_norm = len(st.session_state.df_norm)
        st.caption(
            f"Vista previa: primeras 1.000 filas de "
            f"{formato_numero_es(total_filas_norm)}"
        )
        df_norm_vista = st.session_state.df_norm.head(1000).copy()
        if "fecha_hora" in df_norm_vista.columns:
            df_norm_vista["fecha_hora"] = pd.to_datetime(
                df_norm_vista["fecha_hora"], errors="coerce"
            ).dt.strftime("%d/%m/%Y %H:%M")
        if "fecha" in df_norm_vista.columns:
            df_norm_vista["fecha"] = pd.to_datetime(
                df_norm_vista["fecha"], errors="coerce"
            ).dt.strftime("%d/%m/%Y")
        columnas_energia_vista = [
            columna
            for columna in (
                "consumo_kWh", "excedentes_kWh", "generacion_kWh",
                "reactiva_kVArh", "capacitiva_kVArh",
                "consumo_neto_kWh", "vertido_neto_kWh",
            )
            if columna in df_norm_vista.columns
        ]
        for columna in columnas_energia_vista:
            df_norm_vista[columna] = df_norm_vista[columna].map(
                lambda valor: formato_numero_es(valor, 3)
            )
        st.dataframe(
            df_norm_vista,
            height=altura_df,
            use_container_width=True,
            hide_index=True,
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
            fecha_inicio_resumen = st.session_state.df_norm["fecha_hora"].min()
            fecha_fin_resumen = st.session_state.df_norm["fecha_hora"].max()
            st.metric(
                "Fecha inicio",
                fecha_inicio_resumen.strftime("%d.%m.%Y")
                if pd.notna(fecha_inicio_resumen) else "Sin fecha válida",
            )
            st.metric(
                "Fecha final",
                fecha_fin_resumen.strftime("%d.%m.%Y")
                if pd.notna(fecha_fin_resumen) else "Sin fecha válida",
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
                cups_costes_actual = re.sub(
                    r"[^A-Z0-9]", "",
                    str(st.session_state.get("cups_curva", "") or "").upper(),
                )[:20]
                cups_costes_calculado = st.session_state.get(
                    "cups_costes_comparativa"
                )
                version_curva_actual = st.session_state.get(
                    "curva_reactiva_version", 0
                )
                version_curva_calculada = st.session_state.get(
                    "version_curva_costes_comparativa"
                )
                rango_costes_actual = st.session_state.get(
                    "rango_fechas_comparativa_guardado"
                )
                rango_costes_actual = (
                    tuple(rango_costes_actual)
                    if isinstance(rango_costes_actual, (tuple, list))
                    and len(rango_costes_actual) == 2 else None
                )
                if (
                    st.session_state.get("precios_mensuales") is not None
                    and (
                        cups_costes_calculado != cups_costes_actual
                        or version_curva_calculada != version_curva_actual
                        or st.session_state.get("rango_costes_calculado")
                        != rango_costes_actual
                    )
                ):
                    for clave_costes in (
                        "precios_mensuales", "df_curva_sheets",
                        "resumen_costes_contractuales",
                        "origen_costes_comparativa",
                        "cups_costes_comparativa",
                        "version_curva_costes_comparativa",
                        "rango_costes_calculado",
                    ):
                        st.session_state.pop(clave_costes, None)
                modo_coste_energia = st.radio(
                    "Origen de precios",
                    ("Indexado estándar", "Condiciones del contrato"),
                    horizontal=False,
                    key="modo_coste_energia_comparativa",
                )
                if (
                    st.session_state.get("precios_mensuales") is not None
                    and (
                        st.session_state.get("modo_coste_energia_calculado")
                        != modo_coste_energia
                        or st.session_state.get("df_curva_sheets") is None
                    )
                ):
                    st.session_state.pop("precios_mensuales", None)
                    st.session_state.pop("df_curva_sheets", None)
                precios_mensuales = st.session_state.get("precios_mensuales", None)
                if precios_mensuales is None:
                    st.warning(
                        'Todavía no se han calculado precios para la curva.'
                    )
                else:
                    origen_calculado = st.session_state.get(
                        "origen_costes_comparativa", "precios cargados"
                    )
                    st.success(f'Disponibles costes: {origen_calculado}')
                cargar_indexados = st.button(
                    (
                        "Aplicar condiciones del contrato"
                        if modo_coste_energia == "Condiciones del contrato"
                        else "Cargar precios indexados"
                    ),
                    use_container_width=True,
                    key="cargar_indexados_comparaciones",
                )
                if modo_coste_energia == "Condiciones del contrato":
                    st.caption(
                        "Cruza cada intervalo con la condición vigente del CUPS. "
                        "Los tramos fijos usan TE puro, todavía sin regularización "
                        "mensual de SSAA."
                    )
                else:
                    st.caption(
                        "Usa la fórmula vigente de Telemindex y la curva horaria "
                        "cargada, sin salir de este módulo."
                    )

                if modo_coste_energia == "Condiciones del contrato":
                    cups_extras = st.session_state.get("cups_curva", "")
                    try:
                        extras_guardados = cargar_costes_extra_cups(cups_extras)
                    except Exception as exc:
                        st.warning(f"No se han podido leer los costes extra: {exc}")
                        extras_guardados = pd.DataFrame()
                    columnas_extras = [
                        "Mes", "Concepto", "Cantidad_kWh",
                        "Precio_unitario_EUR_kWh", "Importe_EUR",
                        "Referencia", "Observaciones",
                    ]
                    if extras_guardados.empty:
                        extras_guardados = pd.DataFrame([{
                            "Mes": "", "Concepto": "REGULARIZACION SSAA",
                            "Cantidad_kWh": None,
                            "Precio_unitario_EUR_kWh": None,
                            "Importe_EUR": None, "Referencia": "",
                            "Observaciones": "",
                        }], columns=columnas_extras)
                    with st.expander("Añadir costes extra mensuales"):
                        st.caption(
                            "Introduzca varias mensualidades y guárdelas juntas. "
                            "Los meses sin datos deben dejarse sin fila: se mostrarán "
                            "como provisionales, no como coste cero."
                        )
                        with st.form(
                            f"form_costes_extra_contractuales_{cups_extras[:20]}"
                        ):
                            editor_extras = st.data_editor(
                                extras_guardados[columnas_extras],
                                num_rows="dynamic",
                                use_container_width=True,
                                hide_index=True,
                                column_config={
                                    "Mes": st.column_config.TextColumn(
                                        "Mes (AAAA-MM)", required=True
                                    ),
                                    "Concepto": st.column_config.TextColumn(
                                        "Concepto", default="REGULARIZACION SSAA"
                                    ),
                                    "Cantidad_kWh": st.column_config.NumberColumn(
                                        "Cantidad factura (kWh)", format="%.3f"
                                    ),
                                    "Precio_unitario_EUR_kWh": st.column_config.NumberColumn(
                                        "Precio unitario (€/kWh)", format="%.8f"
                                    ),
                                    "Importe_EUR": st.column_config.NumberColumn(
                                        "Importe (€)", required=True, format="%.2f"
                                    ),
                                },
                                key=(
                                    "editor_costes_extra_contractuales_"
                                    f"{cups_extras[:20]}"
                                ),
                            )
                            guardar_extras = st.form_submit_button(
                                "Guardar todas las mensualidades",
                                use_container_width=True,
                                type="primary",
                            )
                        if guardar_extras:
                            try:
                                filas_guardadas, avisos_extras = guardar_costes_extra_cups(
                                    cups_extras, editor_extras
                                )
                            except Exception as exc:
                                st.error(f"No se han guardado los costes extra: {exc}")
                            else:
                                st.session_state.pop("precios_mensuales", None)
                                st.session_state.pop(
                                    "resumen_costes_contractuales", None
                                )
                                st.success(
                                    f"Guardadas {filas_guardadas} mensualidades en "
                                    "un único guardado. Vuelva a aplicar el contrato."
                                )
                                for aviso_extra in avisos_extras:
                                    st.warning(aviso_extra)

                if cargar_indexados:
                    try:
                        with st.spinner("Cargando precios horarios indexados…"):
                            init_app()
                            st.session_state.zona_periodos_index = "peninsula"
                            init_app_index()
                            actualizar_df_index_por_zona(forzar=True)
                            condiciones = None
                            cups_contrato = ""
                            if modo_coste_energia == "Condiciones del contrato":
                                cups_contrato = st.session_state.get("cups_curva", "")
                                condiciones = cargar_condiciones_cups(cups_contrato)
                                st.session_state.df_sheets = (
                                    preparar_indexado_contractual(
                                        st.session_state.df_sheets,
                                        condiciones,
                                        st.session_state.atr_dfnorm,
                                    )
                                )
                            df_curva_indexada = construir_df_curva_sheets(
                                st.session_state.df_sheets.copy()
                            )
                            if modo_coste_energia == "Condiciones del contrato":
                                fechas_curva_completa = pd.to_datetime(
                                    df_curva_indexada["fecha_hora"]
                                ).dt.to_period("M").astype(str)
                                consumos_mensuales_completos = (
                                    df_curva_indexada.groupby(
                                        fechas_curva_completa
                                    )["consumo_neto_kWh"].sum().to_dict()
                                )
                            df_curva_indexada = filtrar_intervalos_comparacion(
                                df_curva_indexada, rango_costes_actual
                            )
                            if df_curva_indexada.empty:
                                raise ValueError(
                                    "No hay intervalos de curva en el periodo "
                                    "seleccionado y su réplica del año siguiente."
                                )
                            if modo_coste_energia == "Condiciones del contrato":
                                df_curva_indexada = aplicar_condiciones_contractuales(
                                    df_curva_indexada,
                                    condiciones,
                                    st.session_state.atr_dfnorm,
                                )
                                costes_extra = cargar_costes_extra_cups(cups_contrato)
                                df_curva_indexada = aplicar_costes_extra_mensuales(
                                    df_curva_indexada, costes_extra,
                                    consumos_mensuales_base=consumos_mensuales_completos,
                                )
                                st.session_state.resumen_costes_contractuales = (
                                    resumir_calculo_contractual(df_curva_indexada)
                                )
                                st.session_state.origen_costes_comparativa = (
                                    f"contrato del CUPS {cups_contrato[:20]}"
                                )
                            else:
                                columna_precio = (
                                    f"precio_{st.session_state.atr_dfnorm}"
                                )
                                precios_horarios = pd.to_numeric(
                                    df_curva_indexada[columna_precio],
                                    errors="coerce",
                                )
                                if precios_horarios.isna().any():
                                    raise ValueError(
                                        "Faltan precios indexados para "
                                        f"{int(precios_horarios.isna().sum())} "
                                        "intervalos de la curva. Revise la "
                                        "cobertura del histórico de Telemindex."
                                    )
                                df_curva_indexada = añadir_costes_curva(
                                    df_curva_indexada
                                )
                                st.session_state.pop(
                                    "resumen_costes_contractuales", None
                                )
                                st.session_state.origen_costes_comparativa = (
                                    "indexado estándar"
                                )
                            st.session_state.df_curva_sheets = df_curva_indexada
                            st.session_state.modo_coste_energia_calculado = (
                                modo_coste_energia
                            )
                            st.session_state.cups_costes_comparativa = (
                                cups_costes_actual
                            )
                            st.session_state.version_curva_costes_comparativa = (
                                version_curva_actual
                            )
                            st.session_state.rango_costes_calculado = (
                                rango_costes_actual
                            )
                            precios_mensuales, _ = evol_mensual(
                                df_curva_indexada, {}
                            )
                            st.session_state.precios_mensuales = precios_mensuales
                    except Exception as exc:
                        st.error(f"No se han podido calcular los costes: {exc}")
                    else:
                        st.success("Costes calculados correctamente.")
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
                st.session_state.comparativa_informe_datos = {
                    "consumo": res,
                    "costes": res_costes,
                    "resumen_contractual": st.session_state.get(
                        "resumen_costes_contractuales"
                    ),
                    "cups": str(st.session_state.get("cups_curva", "") or ""),
                    "atr": str(st.session_state.get("atr_dfnorm", "") or ""),
                }
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
                    resumen_contractual = st.session_state.get(
                        "resumen_costes_contractuales"
                    )
                    if resumen_contractual is not None:
                        with st.expander("Justificación contractual mensual"):
                            st.caption(
                                "En los tramos fijos, el precio mostrado es el TE "
                                "inicial sin regularización de SSAA."
                            )
                            st.dataframe(
                                resumen_contractual,
                                use_container_width=True,
                                hide_index=True,
                            )
                        with st.expander("Detalle horario del cálculo"):
                            columnas_detalle = [
                                "fecha_hora", "periodo", "consumo_neto_kWh",
                                "tipo_precio_contrato", "condicion_id",
                                "condicion_desde", "condicion_hasta",
                                "precio_fijo_te_eur_mwh",
                                "precio_contrato_eur_mwh",
                                "coste_total_inicial",
                                "coste_extra_mensual_asignado", "coste_total",
                                "estado_coste_contractual", "formula_contrato",
                            ]
                            detalle_contractual = st.session_state.get(
                                "df_curva_sheets", pd.DataFrame()
                            )
                            columnas_detalle = [
                                columna for columna in columnas_detalle
                                if columna in detalle_contractual.columns
                            ]
                            st.dataframe(
                                detalle_contractual[columnas_detalle],
                                use_container_width=True,
                                hide_index=True,
                                height=360,
                            )
                    st.subheader("Efecto PRECIO / CONSUMO")
                    st.markdown(
                        res_costes.get("impacto_html_costes", ""),
                        unsafe_allow_html=True,
                    )

                with coste_c2:
                    if res_costes["fig_precio_medio"] is not None:
                        st.plotly_chart(
                            res_costes["fig_precio_medio"],
                            use_container_width=True,
                        )
                    if res_costes["fig_efectos"] is not None:
                        st.plotly_chart(
                            res_costes["fig_efectos"],
                            use_container_width=True,
                        )

                with coste_c3:
                    if res_costes.get("fig_resumen_costes") is not None:
                        st.plotly_chart(
                            res_costes["fig_resumen_costes"],
                            use_container_width=True,
                        )

                with coste_c4:
                    if res_costes["fig_coste_total"] is not None:
                        st.plotly_chart(
                            res_costes["fig_coste_total"],
                            use_container_width=True,
                        )

    # ======================================================================================================================================================
    # COMPARATIVA DE AHORRO / SOBRECOSTE
    # ======================================================================================================================================================
    with tab_ahorro:
        col_resumen, col_resultado, col_graficos, col_acumulado = st.columns(4)
        col_resumen.info(
            "Compara el coste contractual real con otro precio sobre exactamente "
            "el mismo consumo y el mismo intervalo. El coste real incorpora los "
            "cambios de contrato y los extras mensuales guardados, incluidos SSAA."
        )
        df_rango_ahorro = st.session_state.df_norm_h.copy()
        fechas_rango_ahorro = pd.to_datetime(
            df_rango_ahorro["fecha_hora"], errors="coerce"
        ).dropna()
        fecha_min_ahorro = fechas_rango_ahorro.min().date()
        fecha_max_ahorro = fechas_rango_ahorro.max().date()
        cups_ahorro = str(st.session_state.get("cups_curva", "") or "")
        if cups_ahorro:
            col_resumen.markdown(f"**CUPS de la curva activa:** `{cups_ahorro}`")
        else:
            col_resumen.warning(
                "La curva activa no tiene un CUPS asociado. Carga la curva "
                "desde Axon o Datadis para consultar sus condiciones."
            )
        if origen_curva == "Axon" and cups_axon_base and cups_ahorro:
            if cups_axon_base != cups_ahorro[:20]:
                col_resumen.warning(
                    "El CUPS indicado en Curva es distinto del de la curva "
                    "activa. Descarga y normaliza la curva de ese CUPS."
                )
        condiciones_ahorro = None
        error_condiciones_ahorro = None
        sugerencias_ahorro = []
        periodos_ahorro = []
        try:
            condiciones_ahorro = cargar_condiciones_cups(cups_ahorro)
        except Exception as exc:
            error_condiciones_ahorro = str(exc)
        if condiciones_ahorro is not None:
            try:
                periodos_ahorro = listar_periodos_cups(cups_ahorro)
                sugerencias_ahorro = sugerir_cambios_contrato(
                    periodos_ahorro, condiciones_ahorro,
                    fecha_min_ahorro, fecha_max_ahorro,
                )
            except (ValueError, sqlite3.Error) as exc:
                col_resumen.warning(
                    f"No se pudieron consultar las vigencias contractuales: {exc}"
                )

        contexto_sugerencia = (
            cups_ahorro,
            tuple(
                (periodo["id"], periodo["fecha_inicio"],
                 periodo["fecha_vencimiento"])
                for periodo in periodos_ahorro
            ),
        )
        if st.session_state.get("_ahorro_contexto_vigencias") != contexto_sugerencia:
            if sugerencias_ahorro:
                sugerencia = sugerencias_ahorro[-1]
                st.session_state.rango_ahorro_widget = (
                    sugerencia["inicio"], sugerencia["fin"]
                )
                st.session_state.rango_ahorro_seleccionado = (
                    sugerencia["inicio"], sugerencia["fin"]
                )
                st.session_state.origen_referencia_ahorro = (
                    "Condición anterior del contrato"
                )
                st.session_state.condicion_referencia_ahorro = (
                    sugerencia["condicion_referencia_id"]
                )
            else:
                st.session_state.pop("rango_ahorro_widget", None)
                st.session_state.pop("condicion_referencia_ahorro", None)
            st.session_state["_ahorro_contexto_vigencias"] = contexto_sugerencia
        rango_defecto_ahorro = (fecha_min_ahorro, fecha_max_ahorro)
        rango_guardado_ahorro = st.session_state.get(
            "rango_ahorro_seleccionado", rango_defecto_ahorro
        )
        if (
            not isinstance(rango_guardado_ahorro, (tuple, list))
            or len(rango_guardado_ahorro) != 2
            or pd.Timestamp(rango_guardado_ahorro[0]).date() < fecha_min_ahorro
            or pd.Timestamp(rango_guardado_ahorro[1]).date() > fecha_max_ahorro
        ):
            rango_guardado_ahorro = rango_defecto_ahorro
        rango_ahorro = col_resumen.date_input(
            "Periodo de análisis",
            value=rango_guardado_ahorro,
            min_value=fecha_min_ahorro,
            max_value=fecha_max_ahorro,
            format="DD.MM.YYYY",
            key="rango_ahorro_widget",
        )
        origen_referencia = col_resumen.radio(
            "Precio de referencia",
            (
                "Condición anterior del contrato",
                "Referencia del mismo registro",
                "Oferta fija manual",
                "Oferta indexada manual",
            ),
            horizontal=False,
            key="origen_referencia_ahorro",
        )

        if periodos_ahorro:
            with col_resumen.expander(
                "Cambios de contrato registrados", expanded=True
            ):
                st.caption(
                    "Se muestran todos los contratos del CUPS. Los cambios "
                    "dentro del periodo cargado pueden aplicarse a la comparativa."
                )
                sugerencias_por_periodo = {
                    item["periodo_id"]: item for item in sugerencias_ahorro
                }
                for periodo in periodos_ahorro:
                    sugerencia = sugerencias_por_periodo.get(periodo["id"])
                    vencimiento_txt = (
                        f"{pd.Timestamp(periodo['fecha_vencimiento']):%d/%m/%Y}"
                        if periodo["fecha_vencimiento"] else "sin registrar"
                    )
                    st.write(
                        f"**{pd.Timestamp(periodo['fecha_inicio']):%d/%m/%Y}** · "
                        f"{periodo['comercializadora']} · "
                        f"vencimiento {vencimiento_txt}"
                    )
                    if sugerencia:
                        st.button(
                            f"Usar cambio del {sugerencia['inicio']:%d/%m/%Y}",
                            key=f"usar_periodo_ahorro_{sugerencia['periodo_id']}",
                            on_click=usar_vigencia_en_ahorro,
                            args=(
                                sugerencia["inicio"], sugerencia["fin"],
                                sugerencia["condicion_referencia_id"],
                            ),
                        )

        condicion_referencia_id = None
        precios_fijos_referencia = None
        formula_referencia = None
        if origen_referencia == "Condición anterior del contrato":
            if error_condiciones_ahorro:
                col_resumen.warning(error_condiciones_ahorro)
            else:
                opciones_condicion = condiciones_ahorro["condicion_id"].astype(int).tolist()
                etiquetas_condicion = {}
                for _, fila_condicion in condiciones_ahorro.iterrows():
                    fin_txt = (
                        pd.Timestamp(fila_condicion["fin_condicion"]).strftime("%d/%m/%Y")
                        if pd.notna(fila_condicion["fin_condicion"]) else "actualidad"
                    )
                    payload_condicion = json.loads(
                        fila_condicion.get("payload_json") or "{}"
                    )
                    detalle_condicion = ""
                    if not str(fila_condicion["tipo_precio"]).upper().startswith("FIJO"):
                        margen_condicion = str(
                            payload_condicion.get("INDEX CG", "0")
                        ).replace(",", ".")
                        posicion_condicion = {
                            "1": "pérdidas", "2": "TM", "3": "neto"
                        }.get(str(payload_condicion.get("CG F", "2")), "TM")
                        detalle_condicion = (
                            f" · margen {margen_condicion} €/MWh en {posicion_condicion}"
                        )
                    etiquetas_condicion[int(fila_condicion["condicion_id"])] = (
                        f"{str(fila_condicion['tipo_precio']).strip()} · "
                        f"{pd.Timestamp(fila_condicion['inicio_condicion']):%d/%m/%Y}–{fin_txt}"
                        f"{detalle_condicion}"
                    )
                inicio_ref_ahorro = pd.Timestamp(rango_ahorro[0])
                anteriores_ahorro = condiciones_ahorro.loc[
                    condiciones_ahorro["fin_condicion"].notna()
                    & (condiciones_ahorro["fin_condicion"] < inicio_ref_ahorro)
                ]
                condicion_default_ahorro = (
                    int(anteriores_ahorro.sort_values("fin_condicion").iloc[-1]["condicion_id"])
                    if not anteriores_ahorro.empty else opciones_condicion[-1]
                )
                condicion_referencia_id = col_resumen.selectbox(
                    "Condición que se aplicará como referencia a todo el periodo",
                    opciones_condicion,
                    index=opciones_condicion.index(condicion_default_ahorro),
                    format_func=lambda valor: etiquetas_condicion[valor],
                    key="condicion_referencia_ahorro",
                )
                col_resumen.caption(
                    "Se conserva su fórmula o sus precios, pero no su vigencia original. "
                    "No se trasladan extras históricos al escenario de referencia."
                )
        elif origen_referencia == "Referencia del mismo registro":
            col_resumen.caption(
                "Cada tramo fijo se compara con su fórmula indexada de referencia; "
                "cada tramo indexado, con sus precios TE REF."
            )
            if (
                condiciones_ahorro is not None
                and isinstance(rango_ahorro, (tuple, list))
                and len(rango_ahorro) == 2
            ):
                try:
                    referencias_vista = referencias_del_mismo_registro(
                        condiciones_ahorro, st.session_state.atr_dfnorm,
                        *rango_ahorro,
                    )
                except ValueError as exc:
                    col_resumen.warning(str(exc))
                else:
                    resumen_referencias = []
                    for _, fila in referencias_vista.iterrows():
                        payload = json.loads(fila["payload_json"] or "{}")
                        if str(fila["tipo_precio"]).startswith("INDEX"):
                            detalle = (
                                f"CG {payload.get('INDEX CG', '')} €/MWh · "
                                f"posición {payload.get('CG F', '')}"
                            )
                        else:
                            detalle = " · ".join(
                                f"P{i} {payload.get(f'TE P{i}', '')} €/kWh"
                                for i in range(
                                    1, 4 if str(st.session_state.atr_dfnorm).startswith("2.0") else 7
                                )
                            )
                        resumen_referencias.append({
                            "Condición": int(fila["condicion_id"]),
                            "Desde": pd.Timestamp(fila["inicio_condicion"]).date(),
                            "Hasta": (
                                pd.Timestamp(fila["fin_condicion"]).date()
                                if pd.notna(fila["fin_condicion"]) else None
                            ),
                            "Referencia": str(fila["tipo_precio"]),
                            "Detalle": detalle,
                        })
                    with col_resumen.expander("Referencias aplicadas por tramo"):
                        st.dataframe(
                            pd.DataFrame(resumen_referencias),
                            use_container_width=True, hide_index=True,
                        )
        elif origen_referencia == "Oferta fija manual":
            numero_periodos_ahorro = 3 if str(st.session_state.atr_dfnorm) == "2.0" else 6
            columnas_fijo_ahorro = col_resumen.columns(2)
            precios_fijos_referencia = {}
            for indice_ahorro in range(1, numero_periodos_ahorro + 1):
                with columnas_fijo_ahorro[(indice_ahorro - 1) % 2]:
                    precios_fijos_referencia[f"P{indice_ahorro}"] = st.number_input(
                        f"P{indice_ahorro} (€/kWh)", min_value=0.0, max_value=2.0,
                        step=0.001, format="%.6f",
                        key=f"ahorro_fijo_p{indice_ahorro}",
                    )
        else:
            with col_resumen:
                parametros_ref = mostrar_parametros_formula_indexado(
                    widget_suffix="ahorro_referencia", diferido=True
                )
            formula_referencia = FormulaIndexada(
                desvios_apant=float(parametros_ref.get("desvios_apant", 0.0)),
                margen=float(parametros_ref.get("margen_telemindex", 0.0)),
                margen_pos=parametros_ref.get("cfg_margen_pos", "neto"),
                otros_costes=float(parametros_ref.get("otros_costes_indexado", 0.0)),
                otros_costes_pos=parametros_ref.get("cfg_otros_costes_pos", "neto"),
                incluir_fnee=bool(parametros_ref.get("cfg_fnee", False)),
                fnee_pos=parametros_ref.get("cfg_fnee_pos", "perdidas"),
                cf_pct=float(parametros_ref.get("cf_pct", 0.0)),
            )

        if error_condiciones_ahorro and origen_referencia != "Condición anterior del contrato":
            col_resumen.warning(
                f"La oferta manual necesita el coste contractual actual como "
                f"escenario base. {error_condiciones_ahorro}"
            )

        calcular_ahorro = col_resumen.button(
            "Calcular ahorro / sobrecoste", type="primary",
            use_container_width=True, key="calcular_ahorro_contractual",
            disabled=bool(error_condiciones_ahorro),
        )
        if calcular_ahorro:
            st.session_state.pop("aviso_cobertura_ahorro", None)
            try:
                if error_condiciones_ahorro:
                    raise ValueError(error_condiciones_ahorro)
                if not isinstance(rango_ahorro, (tuple, list)) or len(rango_ahorro) != 2:
                    raise ValueError("Seleccione una fecha inicial y una fecha final.")
                inicio_ahorro, fin_ahorro = map(pd.Timestamp, rango_ahorro)
                if inicio_ahorro > fin_ahorro:
                    raise ValueError("La fecha inicial no puede ser posterior a la final.")
                fin_solicitado_ahorro = fin_ahorro
                fin_ahorro = ultimo_dia_cubierto_desde(
                    condiciones_ahorro, inicio_ahorro, fin_ahorro
                )
                aviso_cobertura_ahorro = (
                    "El periodo solicitado llega al "
                    f"{fin_solicitado_ahorro:%d/%m/%Y}, pero las condiciones "
                    f"solo permiten comparar hasta el {fin_ahorro:%d/%m/%Y}. "
                    "El cálculo excluye los días posteriores."
                    if fin_ahorro < fin_solicitado_ahorro else None
                )
                if origen_referencia == "Condición anterior del contrato":
                    fila_ref = condiciones_ahorro.loc[
                        condiciones_ahorro["condicion_id"].eq(condicion_referencia_id)
                    ].iloc[0]
                    condicion_ref = condicion_como_referencia(
                        fila_ref, inicio_ahorro, fin_ahorro
                    )
                elif origen_referencia == "Referencia del mismo registro":
                    condicion_ref = referencias_del_mismo_registro(
                        condiciones_ahorro, st.session_state.atr_dfnorm,
                        inicio_ahorro, fin_ahorro,
                    )
                elif origen_referencia == "Oferta fija manual":
                    condicion_ref = condicion_manual_como_referencia(
                        "FIJO", inicio_ahorro, fin_ahorro,
                        precios_fijos=precios_fijos_referencia,
                    )
                else:
                    condicion_ref = condicion_manual_como_referencia(
                        "INDEXADO", inicio_ahorro, fin_ahorro,
                        formula=formula_referencia,
                    )

                with st.spinner("Calculando ambos escenarios sobre la misma curva…"):
                    init_app()
                    st.session_state.zona_periodos_index = "peninsula"
                    init_app_index()
                    actualizar_df_index_por_zona(forzar=True)
                    precios_base = st.session_state.df_sheets.copy()

                    precios_actual = preparar_indexado_contractual(
                        precios_base, condiciones_ahorro, st.session_state.atr_dfnorm
                    )
                    curva_actual = construir_df_curva_sheets(precios_actual)
                    mascara_rango = (
                        pd.to_datetime(curva_actual["fecha_hora"]).dt.normalize()
                        .between(inicio_ahorro.normalize(), fin_ahorro.normalize())
                    )
                    curva_actual = curva_actual.loc[mascara_rango].copy()
                    curva_actual = aplicar_condiciones_contractuales(
                        curva_actual, condiciones_ahorro, st.session_state.atr_dfnorm
                    )
                    curva_completa_consumos = st.session_state.df_norm_h.copy()
                    curva_completa_consumos["_mes_extra"] = pd.to_datetime(
                        curva_completa_consumos["fecha_hora"]
                    ).dt.to_period("M").astype(str)
                    consumos_mes_completo = (
                        curva_completa_consumos.groupby("_mes_extra")[
                            "consumo_neto_kWh"
                        ].sum().to_dict()
                    )
                    curva_actual = aplicar_costes_extra_mensuales(
                        curva_actual, cargar_costes_extra_cups(cups_ahorro),
                        consumos_mensuales_base=consumos_mes_completo,
                    )

                    precios_ref = preparar_indexado_contractual(
                        precios_base, condicion_ref, st.session_state.atr_dfnorm
                    )
                    curva_ref = construir_df_curva_sheets(precios_ref)
                    mascara_ref = (
                        pd.to_datetime(curva_ref["fecha_hora"]).dt.normalize()
                        .between(inicio_ahorro.normalize(), fin_ahorro.normalize())
                    )
                    curva_ref = aplicar_condiciones_contractuales(
                        curva_ref.loc[mascara_ref].copy(), condicion_ref,
                        st.session_state.atr_dfnorm,
                    )
                    resultado_nuevo_ahorro = calcular_comparativa_ahorro(
                        curva_actual, curva_ref
                    )
                    if not resultado_nuevo_ahorro["ok"]:
                        raise ValueError(resultado_nuevo_ahorro["mensaje"])
                    st.session_state.resultado_comparativa_ahorro = resultado_nuevo_ahorro
                    st.session_state.rango_ahorro_seleccionado = (
                        inicio_ahorro.date(), fin_ahorro.date()
                    )
                    st.session_state.aviso_cobertura_ahorro = aviso_cobertura_ahorro
                    st.session_state.detalle_actual_ahorro = curva_actual
                    st.session_state.detalle_referencia_ahorro = curva_ref
            except Exception as exc:
                st.session_state.pop("resultado_comparativa_ahorro", None)
                col_resumen.error(f"No se ha podido calcular la comparativa: {exc}")

        resultado_ahorro = st.session_state.get("resultado_comparativa_ahorro")
        if resultado_ahorro is not None:
            aviso_cobertura_ahorro = st.session_state.get("aviso_cobertura_ahorro")
            if aviso_cobertura_ahorro:
                col_resumen.warning(aviso_cobertura_ahorro)
            if not resultado_ahorro["ok"]:
                st.warning(resultado_ahorro["mensaje"])
            else:
                rango_calculado = st.session_state.get("rango_ahorro_seleccionado")
                if rango_calculado:
                    col_resumen.caption(
                        "Periodo comparado: "
                        f"{rango_calculado[0]:%d/%m/%Y} – "
                        f"{rango_calculado[1]:%d/%m/%Y}."
                    )
                st.session_state.comparativa_ahorro_informe_datos = {
                    "resultado": resultado_ahorro,
                    "cups": str(st.session_state.get("cups_curva", "") or ""),
                    "atr": str(st.session_state.get("atr_dfnorm", "") or ""),
                    "origen": origen_referencia,
                    "rango": st.session_state.get("rango_ahorro_seleccionado"),
                }
                etiqueta_ref, etiqueta_actual = resultado_ahorro[
                    "etiquetas_periodos"
                ]
                diferencia_ahorro = resultado_ahorro["diferencia"]
                veredicto_ahorro = (
                    "Sobrecoste" if diferencia_ahorro > 0
                    else "Ahorro" if diferencia_ahorro < 0
                    else "Sin diferencia"
                )
                with col_resumen:
                    fig_perfil_precios = resultado_ahorro.get("fig_perfil_precios")
                    if fig_perfil_precios is not None:
                        st.plotly_chart(
                            fig_perfil_precios,
                            use_container_width=True,
                        )
                with col_resultado:
                    # Misma altura que la primera gráfica de las columnas 3 y 4:
                    # el gráfico horario comienza así en la segunda fila visual.
                    with st.container(height=500, border=False):
                        st.subheader("Resultado", divider="rainbow")
                        st.markdown(
                            resultado_ahorro.get("impacto_html", ""),
                            unsafe_allow_html=True,
                        )
                        subcol_real, subcol_referencia = st.columns(2)
                        with subcol_real:
                            st.metric(
                                "Coste real contractual",
                                formato_euros(resultado_ahorro["coste_real"]),
                            )
                        with subcol_referencia:
                            st.metric(
                                "Coste de referencia",
                                formato_euros(resultado_ahorro["coste_referencia"]),
                            )
                        with st.container(border=True):
                            st.metric(
                                veredicto_ahorro,
                                formato_euros(abs(diferencia_ahorro)),
                                delta=(
                                    f"{formato_numero_es(resultado_ahorro['diferencia_pct'], 2)} %"
                                ),
                                delta_color="inverse",
                            )
                        st.caption(
                            "Ambos importes usan exactamente la misma curva de consumo. "
                            "Positivo significa sobrecoste real; negativo, ahorro real."
                        )
                    fig_perfil_costes = resultado_ahorro.get("fig_perfil_costes")
                    if fig_perfil_costes is not None:
                        st.plotly_chart(
                            fig_perfil_costes,
                            use_container_width=True,
                        )
                with col_graficos:
                    fig_impacto_ahorro = resultado_ahorro.get("fig_impacto")
                    if fig_impacto_ahorro is not None:
                        st.plotly_chart(
                            fig_impacto_ahorro,
                            use_container_width=True,
                        )
                    else:
                        st.info(
                            "Recalcula la comparativa para generar el nuevo "
                            "gráfico de impacto total."
                        )
                    st.plotly_chart(
                        resultado_ahorro["fig_diferencia"],
                        use_container_width=True,
                    )
                with col_acumulado:
                    st.plotly_chart(
                        resultado_ahorro["fig_mensual"],
                        use_container_width=True,
                    )
                    fig_acumulado_ahorro = resultado_ahorro.get("fig_acumulado")
                    if fig_acumulado_ahorro is not None:
                        st.plotly_chart(
                            fig_acumulado_ahorro,
                            use_container_width=True,
                        )

                tabla_ahorro = resultado_ahorro["df_ahorro"]
                columnas_euros_ahorro = [
                    columna for columna in tabla_ahorro.columns
                    if "Coste" in columna or columna == "Ahorro / sobrecoste"
                ]
                columnas_precios_ahorro = [
                    columna for columna in tabla_ahorro.columns
                    if columna.startswith("Precio")
                ]
                columnas_consumo_ahorro = [
                    columna for columna in tabla_ahorro.columns
                    if columna.startswith("Consumo")
                ]
                tabla_ahorro_vista = formatear_columnas_tabla(
                    tabla_ahorro,
                    columnas_kwh=columnas_consumo_ahorro,
                    columnas_euros=columnas_euros_ahorro,
                    columnas_cent_eur_kwh=columnas_precios_ahorro,
                    columnas_pct=["Ahorro / sobrecoste %"],
                    incluir_unidades=False,
                )
                st.subheader("Detalle mensual", divider="rainbow")
                st.dataframe(
                    tabla_ahorro_vista,
                    use_container_width=True,
                    hide_index=True,
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
                            min_value=5,
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
        st.subheader("Informes", divider="rainbow")
        informe_base = st.session_state.get("reactiva_base_cache")
        informe_compensacion = st.session_state.get("reactiva_compensacion")
        informe_comparativa = st.session_state.get("comparativa_informe_datos")

        informes_disponibles = []
        if informe_comparativa:
            informes_disponibles.append("Comparativa")
        if informe_base and informe_compensacion:
            informes_disponibles.append("Reactiva")

        tipo_informe = None
        if informes_disponibles:
            tipo_informe = st.radio(
                "Informe disponible",
                informes_disponibles,
                horizontal=True,
                key="tipo_informe_curva",
            )

        if tipo_informe == "Comparativa":
            mostrar_informe_comparativa(informe_comparativa)
        elif not informes_disponibles:
            st.info(
                "Todavía no hay informes disponibles. Calcula una comparativa "
                "de costes o una compensación de reactiva."
            )
        elif not informe_base:
            st.info(
                "Carga una curva con datos de reactiva para preparar el informe."
            )
        elif not informe_compensacion:
            st.info(
                "Pulsa «Calcular compensación» en la pestaña Reactiva antes "
                "de preparar el informe."
            )
        else:
            cups_disponible = str(
                st.session_state.get("cups_curva", "") or ""
            ).strip().upper()
            datos_bbdd_informe = cargar_datos_suministro(cups_disponible)
            datos_bbdd_informe["cups"] = (
                datos_bbdd_informe.get("cups") or cups_disponible
            )
            anteriores_informe = st.session_state.get(
                "_reactiva_informe_autocompletado", {}
            )
            for campo_informe in (
                "cliente", "nif", "direccion", "cups", "atr"
            ):
                clave_informe = f"reactiva_informe_{campo_informe}"
                valor_actual = str(
                    st.session_state.get(clave_informe, "") or ""
                ).strip()
                valor_anterior = str(
                    anteriores_informe.get(campo_informe, "") or ""
                ).strip()
                valor_bbdd = str(
                    datos_bbdd_informe.get(campo_informe, "") or ""
                ).strip()
                if valor_bbdd and (
                    not valor_actual or valor_actual == valor_anterior
                ):
                    st.session_state[clave_informe] = valor_bbdd
            st.session_state._reactiva_informe_autocompletado = (
                datos_bbdd_informe
            )

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






