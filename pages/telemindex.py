import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import io
from html import escape

import pandas as pd
import datetime
from backend_telemindex import (
    filtrar_datos, filtrar_datos_por_rango, añadir_fnee, #calcular_precios_atr,
    graficar_precios_medios_horarios, graficar_queso_componentes,
    graficar_perfil_atr_ponderado, graficar_queso_componentes_ponderados,
    tabla_precios, tabla_costes, tabla_pyc, tabla_margen,
    tabla_apuntamiento_spot, tabla_apuntamiento_ssaa,
    tabla_apuntamiento_precio_final,
    evol_mensual, evol_precios_diarios, graficar_diferencial_precios_mensuales, tabla_evol_mes_por_años,
    preparar_comparativa_mensual_indexados,
    calcular_impacto_anual_previsto,
    evol_diario,
    construir_df_curva_sheets, añadir_costes_curva,
    calcular_verificacion_ssaa,
    check_medias,
    analizar_dependencia_omie, graficar_elasticidad_lineal,
    
) 
from backend_comun import colores_precios, obtener_df_resumen, aplicar_estilo, NOMBRE_ZONA_PERIODOS, calcular_precios_atr, formatear_columnas_tabla
from backend_curvadecarga import (
    graficar_cascada_diferencias_mensuales,
    graficar_media_horaria,
    graficar_mensual_apilado,
    graficar_queso_periodos,
)
from backend_comparador_luz import (
    calcular_merma_margen_fijo,
    comparar_costes_mensuales_referenciados,
    comparar_ofertas_fijas,
    construir_curva_coste_oferta_fija,
    referenciar_comparativa_costes,
)
from backend_ofertas_fijas import (
    normalizar_atr,
    periodos_no_aplicables_atr,
)
from backend_previsiones import obtener_prevision_omie_anual
from componentes_ofertas_fijas import (
    render_bloque_ofertas_fijas,
    render_simulador_horquilla_ssaa,
)
from componentes_curva import render_origen_curva
from componentes_margen_facturado import (
    render_detalle_margen,
    render_impacto_margen,
    render_precios_facturados,
)
from componentes_indexados import render_formulario_formula_indexada
from backend_margen_facturado import estimar_margen_facturado
from backend_simulindex import (
    construir_prevision_indexados_2026,
    obtener_hist_mensual,
)
from backend_indexado import (
    FormulaIndexada,
    calcular_precios_atr_formula,
    construir_desglose_precio_indexado,
    construir_desglose_ssaa_c2,
    describir_formula_indexada,
)
from backend_telemindex import COMPONENTES_SSAA_FORMULA
from utilidades import (
    construir_base_index_por_zona,
    generar_menu,
    init_app,
    init_app_index,
    persist_widget,
)
from formato_es import (
    formato_cent_eur_kwh,
    formato_eur_kwh,
    formato_eur_mwh,
    formato_euros,
    formato_kwh,
    formato_mes_es,
    formato_numero_es,
    formato_pct,
    formatear_resumen_mixto,
)


CLAVES_FORMULA_HISTORICO = {
    "desvios_apant": "telemindex_historico_desvios_apant",
    "margen_telemindex": "telemindex_historico_margen",
    "cfg_margen_pos": "telemindex_historico_margen_pos",
    "otros_costes_indexado": "telemindex_historico_otros_costes",
    "cfg_otros_costes_pos": "telemindex_historico_otros_costes_pos",
    "cfg_fnee": "telemindex_historico_incluir_fnee",
    "cfg_fnee_pos": "telemindex_historico_fnee_pos",
    "cf_pct": "telemindex_historico_cf_pct",
}

CLAVES_FILTRO_HISTORICO = {
    "rango": "telemindex_historico_rango",
    "año": "telemindex_historico_año",
    "mes": "telemindex_historico_mes",
    "dias": "telemindex_historico_dias",
    "texto": "telemindex_historico_texto_periodo",
    "zona": "telemindex_historico_zona",
}

DEFAULTS_FORMULA_HISTORICO = {
    "desvios_apant": 0.0,
    "margen_telemindex": 0.0,
    "cfg_margen_pos": "neto",
    "otros_costes_indexado": 0.0,
    "cfg_otros_costes_pos": "neto",
    "cfg_fnee": True,
    "cfg_fnee_pos": "perdidas",
    "cf_pct": 0.0,
}

COLORES_TIPO_CONTRATO = {
    "Indexado": "#EF4444",
    "Cobertura": "#8B5CF6",
    "Fijo": "#F59E0B",
}


def inicializar_estado_historico():
    """Migra una vez los valores compartidos al ámbito histórico aislado."""

    for clave_legacy, clave_historica in CLAVES_FORMULA_HISTORICO.items():
        st.session_state.setdefault(
            clave_historica,
            st.session_state.get(
                clave_legacy,
                DEFAULTS_FORMULA_HISTORICO[clave_legacy],
            ),
        )

    migraciones_filtro = {
        CLAVES_FILTRO_HISTORICO["rango"]: st.session_state.get(
            "rango_temporal", "Selecciona un rango de fechas"
        ),
        CLAVES_FILTRO_HISTORICO["año"]: st.session_state.get(
            "año_seleccionado", 2026
        ),
        CLAVES_FILTRO_HISTORICO["mes"]: st.session_state.get(
            "mes_seleccionado", "enero"
        ),
        CLAVES_FILTRO_HISTORICO["dias"]: st.session_state.get(
            "dias_seleccionados"
        ),
        CLAVES_FILTRO_HISTORICO["zona"]: st.session_state.get(
            "zona_periodos_index", "peninsula"
        ),
    }
    for clave, valor in migraciones_filtro.items():
        if valor is not None:
            st.session_state.setdefault(clave, valor)


def aplicar_fee_desde_factura():
    """Precarga Históricos con periodo, ATR y precios enviados por Facturas."""
    datos = st.session_state.get("telemindex_fee_desde_factura")
    if not isinstance(datos, dict):
        return
    try:
        inicio = pd.to_datetime(datos["inicio"], dayfirst=True).date()
        fin = pd.to_datetime(datos["fin"], dayfirst=True).date()
    except (KeyError, TypeError, ValueError):
        st.session_state.pop("telemindex_fee_desde_factura", None)
        return
    st.session_state[CLAVES_FILTRO_HISTORICO["rango"]] = (
        "Selecciona un rango de fechas"
    )
    st.session_state[CLAVES_FILTRO_HISTORICO["dias"]] = (inicio, fin)
    atr = str(datos.get("atr", "")).strip()
    if atr in {"2.0", "3.0", "6.1"}:
        st.session_state["telemindex_historico_atr_margen_facturado"] = atr


def obtener_formula_historico():
    """Construye la fórmula exclusiva del tab Históricos."""

    estado = st.session_state
    return FormulaIndexada(
        desvios_apant=float(estado[CLAVES_FORMULA_HISTORICO["desvios_apant"]]),
        margen=float(estado[CLAVES_FORMULA_HISTORICO["margen_telemindex"]]),
        margen_pos=estado[CLAVES_FORMULA_HISTORICO["cfg_margen_pos"]],
        otros_costes=float(estado[CLAVES_FORMULA_HISTORICO["otros_costes_indexado"]]),
        otros_costes_pos=estado[CLAVES_FORMULA_HISTORICO["cfg_otros_costes_pos"]],
        incluir_fnee=bool(estado[CLAVES_FORMULA_HISTORICO["cfg_fnee"]]),
        fnee_pos=estado[CLAVES_FORMULA_HISTORICO["cfg_fnee_pos"]],
        cf_pct=float(estado[CLAVES_FORMULA_HISTORICO["cf_pct"]]),
    )


def obtener_formula_compartida():
    """Construye la fórmula vigente para Curva y el resto de indexados."""

    estado = st.session_state
    return FormulaIndexada(
        desvios_apant=float(estado.get("desvios_apant", 0.0)),
        margen=float(estado.get("margen_telemindex", 0.0)),
        margen_pos=estado.get("cfg_margen_pos", "neto"),
        otros_costes=float(estado.get("otros_costes_indexado", 0.0)),
        otros_costes_pos=estado.get("cfg_otros_costes_pos", "neto"),
        incluir_fnee=bool(estado.get("cfg_fnee", False)),
        fnee_pos=estado.get("cfg_fnee_pos", "perdidas"),
        cf_pct=float(estado.get("cf_pct", 0.0)),
    )


def mostrar_controles_telemindex(lista_meses, fecha_ultima_filtrado):
    """Dibuja los controles exclusivos del tab Históricos."""

    clave_rango = CLAVES_FILTRO_HISTORICO["rango"]
    clave_año = CLAVES_FILTRO_HISTORICO["año"]
    clave_mes = CLAVES_FILTRO_HISTORICO["mes"]
    clave_dias = CLAVES_FILTRO_HISTORICO["dias"]
    clave_zona = CLAVES_FILTRO_HISTORICO["zona"]

    st.subheader('Info sobre datos', divider='rainbow')
    st.info(
        f"Última fecha disponible: {st.session_state.ultima_fecha_sheets.strftime('%d.%m.%Y')}"
    )
    st.info(
        f"Última fecha C2 liquicomun: {st.session_state.ultima_fecha_csv.strftime('%d.%m.%Y')}"
    )

    with st.expander('Opciones', expanded=False):
        persist_widget(
            st.radio,
            "Seleccionar rango temporal",
            ['Por años', 'Por meses', 'Selecciona un rango de fechas'],
            key=clave_rango,
        )

        if st.session_state[clave_rango] == 'Por años':
            st.selectbox(
                'Seleccione el año',
                options=[2026, 2025, 2024],
                key=clave_año,
            )
        elif st.session_state[clave_rango] == 'Por meses':
            col_filtro1, col_filtro2 = st.columns(2)
            with col_filtro1:
                st.selectbox(
                    'Seleccione el año',
                    options=[2026, 2025, 2024],
                    key=clave_año,
                )
            with col_filtro2:
                st.selectbox(
                    'Seleccionar mes',
                    lista_meses,
                    key=clave_mes,
                )
        else:
            with st.form(key='form_fechas_telemindex_historico'):
                ultima_fecha_sheets = st.session_state.ultima_fecha_sheets
                if isinstance(
                    ultima_fecha_sheets, (pd.Timestamp, datetime.datetime)
                ):
                    ultima_fecha_sheets = ultima_fecha_sheets.date()
                st.date_input(
                    'Selecciona un rango de días',
                    min_value=datetime.date(2023, 1, 1),
                    max_value=ultima_fecha_sheets,
                    key=clave_dias,
                )
                st.form_submit_button('Actualizar cálculos')

        opciones_zona_periodos = [
            "peninsula", "baleares", "canarias", "ceuta", "melilla"
        ]
        persist_widget(
            st.selectbox,
            "Selecciona sistema eléctrico",
            options=opciones_zona_periodos,
            index=0,
            key=clave_zona,
            default="peninsula",
            disabled=not bool(st.secrets.get("CSV_SNP")),
            format_func=lambda x: {
                "peninsula": "Península",
                "baleares": "Baleares",
                "canarias": "Canarias",
                "ceuta": "Ceuta",
                "melilla": "Melilla",
            }[x],
        )
        if not st.secrets.get("CSV_SNP"):
            st.caption(
                "Configura `CSV_SNP` para habilitar Baleares, Canarias, Ceuta y Melilla."
            )

    with st.expander('Parámetros de fórmula', expanded=False):
        render_formulario_formula_indexada(
            clave="telemindex_historico",
            claves_estado=CLAVES_FORMULA_HISTORICO,
        )


if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')

  

if "df_ofertas_fijas" not in st.session_state:
    st.session_state.df_ofertas_fijas = pd.DataFrame()

if 'opcion_comparativa' not in st.session_state:
    st.session_state.opcion_comparativa = 'Cobertura'

#para lo del análisis de elasticidad y tal
if 'peaje_analisis' not in st.session_state:
    st.session_state.peaje_analisis = '2.0'

if 'mes_select_evol' not in st.session_state:
    st.session_state.mes_select_evol = 'enero'

if 'precios_mensuales' not in st.session_state:
    st.session_state.precios_mensuales = None


#inicializamos variables de sesión
generar_menu()

if st.session_state.get('atr_dfnorm') in ['6.3', '6.4']:
    st.warning(f'No se disponen datos de indexado para {st.session_state.atr_dfnorm}TD')
    st.stop()  

init_app()

init_app_index()
inicializar_estado_historico()
aplicar_fee_desde_factura()
formula_historico = obtener_formula_historico()

# La vista compartida permanece intacta para Curva, Simulindex y el resto.
st.session_state.df_sheets = calcular_precios_atr(st.session_state.df_sheets)
print (st.session_state.df_sheets)

# Históricos recalcula una vista propia sin sobrescribir el mercado compartido.
zona_historico = st.session_state[CLAVES_FILTRO_HISTORICO["zona"]]
base_mercado_historico = construir_base_index_por_zona(zona_historico)
df_mercado_historico = calcular_precios_atr_formula(
    base_mercado_historico,
    formula_historico,
)
df_filtrado_historico, lista_meses = filtrar_datos(
    df_mercado_historico,
    rango_temporal=st.session_state[CLAVES_FILTRO_HISTORICO["rango"]],
    año_seleccionado=st.session_state[CLAVES_FILTRO_HISTORICO["año"]],
    mes_seleccionado=st.session_state[CLAVES_FILTRO_HISTORICO["mes"]],
    dias_seleccionados=st.session_state[CLAVES_FILTRO_HISTORICO["dias"]],
)
df_filtrado_compartido, _ = filtrar_datos(
    st.session_state.df_sheets,
)

if df_filtrado_historico.empty or df_filtrado_historico["spot"].notna().sum() == 0:
    fechas_disponibles = pd.to_datetime(
        base_mercado_historico.loc[
            base_mercado_historico["spot"].notna(), "fecha"
        ],
        errors="coerce",
    ).dropna()
    if fechas_disponibles.empty:
        detalle_disponibilidad = "No hay precios disponibles para esta zona."
    else:
        detalle_disponibilidad = (
            "Hay precios para esta zona entre el "
            f"{fechas_disponibles.min():%d/%m/%Y} y el "
            f"{fechas_disponibles.max():%d/%m/%Y}."
        )
    st.warning(
        "No hay precios para la zona y el periodo seleccionados. "
        + detalle_disponibilidad
    )
    mostrar_controles_telemindex(lista_meses, st.session_state.ultima_fecha_sheets)
    st.stop()

check_medias(df_filtrado_historico, "3.0")

def check_componentes_ssaa_simple(df):
    
    componentes = [
        "balx", "bs3", "cfp", "ct2", "ct3",
        "dsv", "exd", "in7", "rad3", "rt3", "rt6"
    ]

    print("---- MEDIAS COMPONENTES ----\n")

    suma = 0

    for c in componentes:
        val = df[c].mean()
        suma += val
        print(f"{c.upper():5}: {val:.4f}")

    print("\nTOTAL SSAA (reconstruido):", round(suma, 4))
    print("SSAA en df:", round(df["ssaa"].mean(), 4))





if df_filtrado_historico.empty:
    fecha_ultima_filtrado = st.session_state.ultima_fecha_sheets
else:
    fecha_ultima_filtrado = df_filtrado_historico['fecha'].iloc[-1]

# El origen debe procesarse antes de calcular la curva y la comparativa.
# Streamlit ejecuta el script de arriba abajo en cada envío del formulario.
tab1, tab2, tab_curva, tab3, tab4 = st.tabs(
    [
        'Históricos', 'Evol', 'Curva', 'Comparativa', 'Verificación SSAA',
    ]
)
with tab_curva:
    curva_col1, curva_col2, curva_col3 = st.columns(
        [.17, .55, .28], gap="small"
    )
    with curva_col1:
        st.subheader("Personaliza", divider="rainbow")
        with st.expander("Opciones de curva", expanded=False):
            contenedor_origen_curva = st.container(border=True)
            contenedor_acciones_curva = st.container(border=True)
        with st.expander("Parámetros de fórmula", expanded=False):
            contenedor_formula_curva = st.container(border=False)

    estado_normalizacion_curva = render_origen_curva(
        contenedor_origen_curva,
        contenedor_acciones_curva,
        clave="telemindex_curva",
        titulo_compacto=True,
        mostrar_resumen=False,
        mostrar_aviso_resolucion=False,
    )
    if estado_normalizacion_curva["normalizacion_solicitada"]:
        st.session_state["_telemindex_curva_sin_normalizar"] = (
            not estado_normalizacion_curva["curva_publicada"]
        )
        st.session_state["_telemindex_curva_version_bloqueada"] = (
            st.session_state.get("curva_reactiva_version")
        )
    if (
        st.session_state.get("_telemindex_curva_sin_normalizar", False)
        and st.session_state.get("curva_reactiva_version")
        != st.session_state.get("_telemindex_curva_version_bloqueada")
    ):
        st.session_state.pop("_telemindex_curva_sin_normalizar", None)
    if st.session_state.get("df_norm_h") is None:
        st.session_state.pop("_telemindex_curva_sin_normalizar", None)
    with contenedor_formula_curva:
        render_formulario_formula_indexada(clave="telemindex_curva")

hay_curva = (
    st.session_state.get("df_norm_h") is not None
    and "rango_curvadecarga" in st.session_state
    and not st.session_state.get("_telemindex_curva_sin_normalizar", False)
)

if hay_curva:
    # La curva se cruza siempre con el mercado de sus propias fechas. El
    # selector histórico del sidebar conserva un rango completamente separado.
    df_mercado_curva = filtrar_datos_por_rango(
        st.session_state.df_sheets,
        st.session_state.rango_curvadecarga,
    )

    df_curva_sheets = construir_df_curva_sheets(df_mercado_curva)
    df_curva_sheets = añadir_costes_curva(df_curva_sheets)
    
    df_curva_uso = df_curva_sheets.copy()
    st.session_state.df_curva_sheets = df_curva_uso

    #consumo total curva
    consumo_total_curva = df_curva_uso['consumo_neto_kWh'].sum()
    
    #calculamos el coste spot ponderado en €/MWh
    media_spot_curva = round(df_curva_uso['coste_spot'].sum()/(consumo_total_curva/1000),2)
    media_ssaa_curva = round(df_curva_uso['coste_ssaa'].sum()/(consumo_total_curva/1000),2)
        
    coste_total_curva = round(df_curva_uso['coste_total'].sum(), 2)

    
    
else:
    df_mercado_curva = None
    st.session_state.df_curva_sheets = None

# Históricos obedece solo a sus selectores y su fórmula aislada.
df_historico = df_filtrado_historico.copy()


#ejecutamos la función para obtener la tabla resumen y precios medios
media_20 = df_historico["precio_2.0"].mean()
media_30 = df_historico["precio_3.0"].mean()
media_61 = df_historico["precio_6.1"].mean()
media_spot = df_historico["spot"].mean()
media_ssaa = df_historico["ssaa"].mean()

df_tabla_precios, _ = tabla_precios(df_historico, incluir_curva=False)
df_tabla_costes, _ = tabla_costes(df_historico, incluir_curva=False)
df_tabla_pyc, _ = tabla_pyc(df_historico, incluir_curva=False)
df_tabla_margen, _ = tabla_margen(df_historico, incluir_curva=False)
df_tabla_apuntamiento = tabla_apuntamiento_spot(
    df_historico,
    incluir_curva=False,
)
df_tabla_apuntamiento_ssaa = tabla_apuntamiento_ssaa(df_historico)
df_tabla_apuntamiento_precio = tabla_apuntamiento_precio_final(df_historico)

#media_20 = round(media_20 / 10, 1)
media_20 = media_20 / 10
#media_30 = round(media_30 / 10, 1)
media_30 = media_30 / 10
#media_61 = round(media_61 / 10, 1)
media_61 = media_61 / 10
media_spot = round(media_spot, 2)
media_ssaa = round(media_ssaa, 2)
media_combo = media_spot + media_ssaa
sobrecoste_ssaa = ((media_combo / media_spot) - 1) * 100




if hay_curva:

    media_atr_curva = (
        df_curva_uso["coste_total"].sum()
        / df_curva_uso["consumo_neto_kWh"].sum()
        * 1000
        / 10
    )
    media_spot_referencia_curva = df_mercado_curva["spot"].mean()
    media_ssaa_referencia_curva = df_mercado_curva["ssaa"].mean()
    apuntamiento_spot = round(media_spot_curva/media_spot_referencia_curva,3)
    apuntamiento_ssaa = round(media_ssaa_curva/media_ssaa_referencia_curva,3)

    col_precio_atr_curva = f"precio_{st.session_state.atr_dfnorm}"
    media_atr = df_mercado_curva[col_precio_atr_curva].mean() / 10
    apuntamiento_final = (
        round(media_atr_curva / media_atr, 3)
        if media_atr is not None and media_atr != 0
        else float("nan")
    )
    coste_sin_ponderar = round(consumo_total_curva * media_atr / 100,2)
    desvio_coste_total = coste_total_curva-coste_sin_ponderar
    desvio_coste_total_porc = (desvio_coste_total / coste_sin_ponderar) * 100



    df_filtrado_cober = df_mercado_curva.copy()
    
    
    if 'precio_cobertura' not in st.session_state:
        st.session_state.precio_cobertura = 50
    #precio_cober_omip = st.session_state.get('precio_cobertura', 50.0)

    df_filtrado_cober["spot"] = st.session_state.precio_cobertura * apuntamiento_spot
    df_filtrado_cober = calcular_precios_atr(df_filtrado_cober)

    df_curva_cober_omip = construir_df_curva_sheets(df_filtrado_cober)
    df_curva_cober_omip = añadir_costes_curva(df_curva_cober_omip)
           
    #df_heat = st.session_state.df_curva_sheets[["fecha","hora"]].copy()

    opcion_comparativa = str(st.session_state.get("opcion_comparativa", "Cobertura"))
    referencia_comparativa = str(
        st.session_state.get("telemindex_referencia_comparativa", "Indexado")
    )
    df_ofertas_sesion = st.session_state.get("df_ofertas_fijas")

    ofertas_disponibles = []
    if df_ofertas_sesion is not None and not df_ofertas_sesion.empty:
        df_ofertas_sesion = df_ofertas_sesion.copy()
        df_ofertas_sesion["oferta"] = df_ofertas_sesion["oferta"].astype(str).str.strip()
        ofertas_disponibles = df_ofertas_sesion["oferta"].tolist()

    curvas_comparativa = {
        "Indexado": df_curva_sheets.copy(),
        "Cobertura": df_curva_cober_omip.copy(),
    }
    tipos_comparativa = {"Indexado": "Indexado", "Cobertura": "Cobertura"}
    if df_ofertas_sesion is not None and not df_ofertas_sesion.empty:
        for _, fila_oferta in df_ofertas_sesion.iterrows():
            nombre_oferta = str(fila_oferta["oferta"]).strip()
            curvas_comparativa[nombre_oferta] = construir_curva_coste_oferta_fija(
                df_curva_sheets, fila_oferta
            )
            tipos_comparativa[nombre_oferta] = "Fijo"

    opciones_escenario = list(curvas_comparativa)
    if referencia_comparativa not in opciones_escenario:
        referencia_comparativa = "Indexado"
        st.session_state.telemindex_referencia_comparativa = referencia_comparativa

# Evol es una prolongación del histórico y no depende de la curva cargada.
df_evol_historico = st.session_state.df_sheets.copy()
if "fecha" in df_evol_historico.columns:
    fechas_evol = pd.to_datetime(df_evol_historico["fecha"], errors="coerce")
    df_evol_historico = df_evol_historico.loc[
        fechas_evol >= pd.Timestamp("2024-01-01")
    ].copy()
elif "año" in df_evol_historico.columns:
    anios_evol = pd.to_numeric(df_evol_historico["año"], errors="coerce")
    df_evol_historico = df_evol_historico.loc[anios_evol >= 2024].copy()

df_precios_mensuales, graf_mensual = evol_mensual(
    df_evol_historico, colores_precios
)
df_precios_mensuales_sin_curva = df_precios_mensuales
df_evol_precios_diarios, graf_evol_precios_diarios = evol_precios_diarios(
    df_evol_historico, colores_precios
)



df_prevision_indexados_2026 = pd.DataFrame()
error_prevision_indexados = None
try:
    df_hist_simulindex = obtener_hist_mensual(st.session_state.df_sheets)
    media_ssaa_prev = st.session_state.get("media_ssaa_prev", 20.0)
    media_fnee_prev = st.session_state.get("media_fnee_prev", 2.68)
    media_rad3_prev = st.session_state.get("media_rad3_prev", 1.7)
    media_rad3_hist = df_hist_simulindex["rad3"].mean()
    media_ssaa_hist = df_hist_simulindex["ssaa"].mean() - media_rad3_hist
    media_fnee_hist = df_hist_simulindex["fnee"].mean()
    ajuste_hist_simulindex = (
        (media_ssaa_prev - media_ssaa_hist)
        + (media_fnee_prev - media_fnee_hist)
        + (media_rad3_prev - media_rad3_hist)
    ) * 1.1 * 1.015 / 10
    df_spot_prevision = st.session_state.df_sheets.copy()
    df_spot_prevision["fecha"] = pd.to_datetime(df_spot_prevision["fecha"])
    df_spot_prevision = df_spot_prevision.set_index("fecha")[["spot"]]
    prevision_omie_2026 = obtener_prevision_omie_anual(df_spot_prevision)
    df_prevision_indexados_2026 = construir_prevision_indexados_2026(
        df_hist_simulindex,
        prevision_omie_2026["curva_telemindex"],
        ajuste_hist=ajuste_hist_simulindex,
    )
except Exception as exc:
    error_prevision_indexados = str(exc)

df_precios_diarios, graf_precios_diarios = evol_diario(
    df_evol_historico,
    df_prevision_2026=df_prevision_indexados_2026,
)

def actualizar_texto_periodo_telemindex(fecha_ultima_filtrado):
    """Sincroniza el texto del resumen antes de dibujar sus controles."""

    clave_rango = CLAVES_FILTRO_HISTORICO["rango"]
    clave_año = CLAVES_FILTRO_HISTORICO["año"]
    clave_mes = CLAVES_FILTRO_HISTORICO["mes"]
    clave_dias = CLAVES_FILTRO_HISTORICO["dias"]
    clave_texto = CLAVES_FILTRO_HISTORICO["texto"]

    if st.session_state[clave_rango] == 'Por años':
        st.session_state[clave_texto] = (
            f'Año {st.session_state[clave_año]}, '
            f'hasta el día {fecha_ultima_filtrado}'
        )
    elif st.session_state[clave_rango] == 'Por meses':
        st.session_state[clave_texto] = (
            f'Seleccionado: {st.session_state[clave_mes]} '
            f'de {st.session_state[clave_año]}'
        )
    else:
        inicio, fin = st.session_state[clave_dias]
        st.session_state[clave_texto] = (
            f"Rango seleccionado: {inicio.strftime('%d/%m/%Y')} → "
            f"{fin.strftime('%d/%m/%Y')}"
        )


def construir_grafico_perfil_consumo_coste(df_curva):
    """Recupera el perfil medio de consumo y añade el coste horario."""

    df_coste_h = (
        df_curva.groupby("hora", as_index=False)["coste_total"].mean()
    )
    figura = graficar_media_horaria('Total')
    figura.add_trace(
        go.Scatter(
            x=df_coste_h["hora"],
            y=df_coste_h["coste_total"],
            mode="lines",
            name="Coste medio indexado",
            line=dict(color="#E53935", width=5),
            yaxis="y2",
        )
    )
    figura.update_layout(
        yaxis2=dict(
            title="Coste medio (€)",
            overlaying="y",
            side="right",
            showgrid=False,
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.0,
            xanchor="center",
            x=0.5,
        ),
    )
    return figura


def mostrar_graficos_curva(apuntamiento_spot, apuntamiento_final):
    """Gráficos de curva reservados para el futuro tab específico."""

    apuntamiento_spot_fmt = formato_numero_es(apuntamiento_spot, 3)
    apuntamiento_final_fmt = formato_numero_es(apuntamiento_final, 3)
    st.subheader(
        "Perfil de consumo vs coste - "
        f"APo: :orange[{apuntamiento_spot_fmt}] · "
        f"APf: :orange[{apuntamiento_final_fmt}]",
        divider='rainbow',
        help=(
            "APo es el apuntamiento de OMIE/SPOT: precio SPOT "
            "ponderado por la curva dividido por su media aritmética. "
            "APf es el apuntamiento del precio final del ATR: precio "
            "final ponderado por la curva dividido por su media "
            "aritmética. Un valor inferior a 1 reduce el precio; "
            "un valor superior a 1 lo incrementa."
        ),
    )

    graf_medias_horarias = construir_grafico_perfil_consumo_coste(
        st.session_state.df_curva_sheets
    )
    st.plotly_chart(graf_medias_horarias, use_container_width=True)

    st.subheader("Consumo por periodos")
    graf_periodos, _ = graficar_queso_periodos(st.session_state.df_norm_h)
    st.plotly_chart(graf_periodos, use_container_width=True)


def mostrar_metricas_curva(
    media_atr_curva,
    apuntamiento_final,
    consumo_total_curva,
    coste_total_curva,
    desvio_coste_total_porc,
    media_spot_curva,
    apuntamiento_spot,
    media_ssaa_curva,
    apuntamiento_ssaa,
):
    """Métricas reservadas para el futuro tab específico de curva."""

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric(
            f'Precio ponderado {st.session_state.atr_dfnorm} c€/kWh',
            value=formato_cent_eur_kwh(media_atr_curva, 2, False),
            delta=f'APf = {formato_numero_es(apuntamiento_final, 3)}',
            delta_color='inverse',
            help='APf: apuntamiento del precio final.',
        )
    with col2:
        st.metric(
            'Consumo neto kWh',
            value=formato_kwh(consumo_total_curva, 0, False),
        )
    with col3:
        st.metric(
            'Coste total €',
            value=formato_euros(coste_total_curva, 0, False),
            delta=formato_pct(desvio_coste_total_porc),
            delta_color='inverse',
            help='El % indica el desvío con respecto al coste medio aritmético',
        )
    with col4:
        st.metric(
            'SPOT ponderado €/MWh',
            value=formato_eur_mwh(media_spot_curva, 2, False),
            delta=f'APo = {formato_numero_es(apuntamiento_spot, 3)}',
            delta_color='inverse',
            help='APo: apuntamiento de OMIE/SPOT.',
        )
    with col5:
        st.metric(
            'SSAA ponderados €/MWh',
            value=formato_eur_mwh(media_ssaa_curva, 2, False),
            delta=f'APs = {formato_numero_es(apuntamiento_ssaa, 3)}',
            delta_color='inverse',
            help='APs: apuntamiento de los servicios de ajuste.',
        )


def ocultar_filas_curva(tabla):
    """Devuelve una vista sin curva conservando intacta la tabla completa."""

    indices = tabla.index.astype(str)
    return tabla.loc[~indices.str.endswith("_curva")].copy()


def estilizar_etiquetas_atr(tabla, columna):
    """Colorea una columna de etiquetas con el color común de cada ATR."""
    colores_atr = {
        atr: colores_precios[f"precio_{atr}"] for atr in ("2.0", "3.0", "6.1")
    }

    def estilo(valor):
        texto = str(valor)
        atr = next((atr for atr in colores_atr if atr in texto), None)
        return (
            f"color: {colores_atr[atr]}; font-weight: 700"
            if atr else ""
        )

    return tabla.style.applymap(estilo, subset=[columna])


def mostrar_impacto_spot():
    """Muestra la evolución y elasticidad del SPOT dentro del tab Evol."""

    df_res, fig_dependencia = analizar_dependencia_omie(
        st.session_state.df_sheets,
        st.session_state.peaje_analisis,
    )
    st.subheader('Impacto del SPOT en el precio final', divider='rainbow')
    col_selector, col_dependencia, col_elasticidad = st.columns([.2, .4, .4])
    with col_selector:
        st.selectbox(
            "Selecciona peaje de acceso",
            ["2.0", "3.0", "6.1"],
            index=0,
            key='peaje_analisis',
        )
        st.markdown('Tabla de datos')
        st.dataframe(df_res, hide_index=True)
    with col_dependencia:
        st.plotly_chart(fig_dependencia, use_container_width=True)
    with col_elasticidad:
        fig_elasticidad = graficar_elasticidad_lineal(
            df_res,
            st.session_state.peaje_analisis,
        )
        st.plotly_chart(fig_elasticidad, use_container_width=True)


def mostrar_desgloses_precios_historicos(df, formula):
    """Muestra una justificación aritmética independiente para cada ATR."""

    colores_atr_markdown = {"2.0": "orange", "3.0": "red", "6.1": "blue"}
    for atr in ("2.0", "3.0", "6.1"):
        color = colores_atr_markdown[atr]
        with st.expander(
            f"Desglose justificativo :{color}[{atr} TD]"
        ):
            try:
                tabla = construir_desglose_precio_indexado(
                    df,
                    atr,
                    formula,
                    columna_consumo=None,
                )
                tabla_mostrar = tabla.copy()
                for columna in tabla_mostrar.columns[1:]:
                    tabla_mostrar[columna] = tabla_mostrar[columna].map(
                        lambda valor: formato_eur_kwh(valor / 1000, 6, False)
                    )
                st.caption("Valores en €/kWh · media aritmética")
                st.dataframe(
                    tabla_mostrar,
                    use_container_width=True,
                    hide_index=True,
                    height=38 + 35 * len(tabla_mostrar),
                )
            except ValueError as exc:
                st.warning(f"No se puede construir el desglose: {exc}")


def mostrar_tabla_apuntamiento(tabla):
    """Muestra apuntamientos con anchos idénticos en las tres tablas."""

    tabla_mostrar = tabla.rename_axis("Peaje").reset_index()
    columnas_valores = [f"P{i}" for i in range(1, 7)] + ["Media"]
    tabla_mostrar["Peaje"] = (
        tabla_mostrar["Peaje"].astype(str)
        .str.replace(r"^Ap_", "", regex=True)
        + " TD"
    )
    tabla_mostrar = formatear_columnas_tabla(
        tabla_mostrar,
        columnas_numero=columnas_valores,
        decimales_numero=3,
    )
    configuracion = {
        "Peaje": st.column_config.TextColumn("Peaje", width="small"),
        **{
            columna: st.column_config.TextColumn(
                columna,
                width="small",
            )
            for columna in columnas_valores
        },
    }
    st.dataframe(
        estilizar_etiquetas_atr(tabla_mostrar, "Peaje"),
        column_config=configuracion,
        use_container_width=True,
        hide_index=True,
    )


actualizar_texto_periodo_telemindex(fecha_ultima_filtrado)


with tab_curva:
    with curva_col2:
        if hay_curva:
            atr_curva = st.session_state.atr_dfnorm
            st.subheader(
                f"Perfil horario ponderado · ATR {atr_curva}",
                divider="rainbow",
            )
            mostrar_metricas_curva(
                media_atr_curva,
                apuntamiento_final,
                consumo_total_curva,
                coste_total_curva,
                desvio_coste_total_porc,
                media_spot_curva,
                apuntamiento_spot,
                media_ssaa_curva,
                apuntamiento_ssaa,
            )
            color_atr_curva = colores_precios.get(
                f"precio_{atr_curva}", "#FF8C00"
            )
            st.plotly_chart(
                graficar_perfil_atr_ponderado(
                    df_mercado_curva,
                    df_curva_uso,
                    atr_curva,
                    color=color_atr_curva,
                ),
                use_container_width=True,
                key="telemindex_curva_perfil_ponderado",
            )

            graf_componentes = graficar_queso_componentes_ponderados(
                df_curva_uso,
                atr_curva,
            )
            graf_periodos, _ = graficar_queso_periodos(
                st.session_state.df_norm_h
            )
            for graf_queso in (graf_componentes, graf_periodos):
                graf_queso.update_traces(hole=0.42)
                graf_queso.update_layout(
                    height=390,
                    margin=dict(l=10, r=10, t=55, b=15),
                )

            componentes_col, periodos_col = st.columns(2, gap="small")
            with componentes_col:
                st.subheader(
                    "Peso de los componentes",
                    divider="rainbow",
                )
                st.plotly_chart(
                    graf_componentes,
                    use_container_width=True,
                    key="telemindex_curva_queso_ponderado",
                )
            with periodos_col:
                st.subheader(
                    "Reparto de consumos",
                    divider="rainbow",
                )
                st.plotly_chart(
                    graf_periodos,
                    use_container_width=True,
                    key="telemindex_curva_consumo_periodos",
                )
        else:
            st.subheader("Curva histórica ponderada", divider="rainbow")
            if st.session_state.get("_telemindex_curva_sin_normalizar", False):
                st.error(
                    "La nueva curva no se ha normalizado. Se han ocultado "
                    "los resultados de la curva anterior."
                )
            else:
                st.info(
                    "Carga una curva para visualizar sus precios y apuntamientos "
                    "ponderados por consumo."
                )

    with curva_col3:
        st.subheader("Resultados ponderados", divider="rainbow")
        if hay_curva:
            resumen_curva = obtener_df_resumen(df_curva_uso, None, 0.0)
            periodos_afectados_curva = (
                df_curva_uso["periodo"].dropna().astype(str)
                .str.strip().str.upper().unique().tolist()
            )
            resumen_curva_mostrar = formatear_resumen_mixto(
                resumen_curva,
                columnas_en_blanco=periodos_no_aplicables_atr(atr_curva),
                periodos_afectados=periodos_afectados_curva,
            )
            st.caption(
                f"Consumos, costes y precios medios · ATR {atr_curva}"
            )
            st.dataframe(
                resumen_curva_mostrar,
                use_container_width=True,
            )
            with st.expander("Desglose justificativo"):
                try:
                    desglose_curva = construir_desglose_precio_indexado(
                        df_curva_uso,
                        atr_curva,
                        obtener_formula_compartida(),
                        columna_consumo="consumo_neto_kWh",
                    )
                    desglose_curva_mostrar = desglose_curva.copy()
                    for columna in desglose_curva_mostrar.columns[1:]:
                        desglose_curva_mostrar[columna] = (
                            desglose_curva_mostrar[columna].map(
                                lambda valor: formato_eur_kwh(
                                    valor / 1000,
                                    6,
                                    False,
                                )
                            )
                        )
                    st.caption("Valores ponderados por consumo en €/kWh")
                    st.dataframe(
                        desglose_curva_mostrar,
                        use_container_width=True,
                        hide_index=True,
                        height=38 + 35 * len(desglose_curva_mostrar),
                    )
                except ValueError as exc:
                    st.warning(f"No se puede construir el desglose: {exc}")

                fechas_curva = pd.to_datetime(
                    df_curva_uso["fecha"], errors="coerce"
                ).dt.date
                fechas_validas_curva = fechas_curva.dropna()
                fecha_limite_c2 = pd.to_datetime(
                    st.session_state.ultima_fecha_csv
                ).date()
                rango_curva_dentro_c2 = (
                    not fechas_validas_curva.empty
                    and fechas_curva.notna().all()
                    and fechas_validas_curva.max() <= fecha_limite_c2
                )
                curva_actual = st.session_state.get("curva_actual") or {}
                zona_curva = (
                    curva_actual.get("zona_confirmada")
                    or curva_actual.get("zona_periodos")
                    or st.session_state.get("zona_periodos_cdc", "peninsula")
                )
                componentes_ssaa_disponibles = all(
                    columna in df_curva_uso.columns
                    and df_curva_uso[columna].notna().all()
                    for columna in COMPONENTES_SSAA_FORMULA
                )

                st.markdown("#### Desglose de los SSAA del C2 Compodem")
                if zona_curva != "peninsula":
                    st.info(
                        "El desglose C2 de SSAA está disponible únicamente "
                        "para Península."
                    )
                elif not rango_curva_dentro_c2:
                    st.info(
                        "El rango supera la última fecha con detalle C2 "
                        f"({fecha_limite_c2.strftime('%d/%m/%Y')})."
                    )
                elif not componentes_ssaa_disponibles:
                    st.warning(
                        "La curva no contiene todas las columnas de detalle "
                        "SSAA del C2."
                    )
                else:
                    desglose_ssaa_curva = construir_desglose_ssaa_c2(
                        df_curva_uso,
                        COMPONENTES_SSAA_FORMULA,
                        atr_curva,
                        columna_consumo="consumo_neto_kWh",
                    )
                    desglose_ssaa_curva_mostrar = desglose_ssaa_curva.copy()
                    for columna in desglose_ssaa_curva_mostrar.columns[1:]:
                        desglose_ssaa_curva_mostrar[columna] = (
                            desglose_ssaa_curva_mostrar[columna].map(
                                lambda valor: formato_eur_kwh(
                                    valor / 1000,
                                    6,
                                    False,
                                )
                            )
                        )
                    st.dataframe(
                        desglose_ssaa_curva_mostrar,
                        use_container_width=True,
                        hide_index=True,
                        height=38 + 35 * len(desglose_ssaa_curva_mostrar),
                    )

            with st.expander("Consumo mensual", expanded=False):
                st.plotly_chart(
                    graficar_mensual_apilado(df_curva_uso),
                    use_container_width=True,
                    key="telemindex_curva_consumo_mensual",
                )

            with st.expander("Perfil de consumo vs coste", expanded=False):
                st.plotly_chart(
                    construir_grafico_perfil_consumo_coste(df_curva_uso),
                    use_container_width=True,
                    key="telemindex_curva_perfil_consumo_coste",
                )
            st.subheader("¿Qué margen han cargado?", divider="rainbow")
            firma_facturada = (
                atr_curva,
                str(st.session_state.get("rango_curvadecarga")),
                st.session_state.get("curva_reactiva_version"),
                len(df_curva_uso),
                round(float(resumen_curva.loc["Consumo (kWh)", "TOTAL"]), 3),
            )
            precios_facturados = render_precios_facturados(
                resumen_curva.loc["Consumo (kWh)"],
                atr_curva,
                firma_facturada,
                "telemindex_curva_facturada",
            )
            if precios_facturados:
                try:
                    margen_facturado = estimar_margen_facturado(
                        df_curva_uso,
                        atr_curva,
                        obtener_formula_compartida(),
                        precios_facturados,
                    )
                except (ValueError, KeyError) as exc:
                    st.warning(f"No se puede estimar el margen: {exc}")
                else:
                    render_impacto_margen(margen_facturado)
                    with st.expander("Detalle del margen por periodo", expanded=False):
                        detalle_calculo = margen_facturado["detalle"]
                        detalle = detalle_calculo[
                            [
                                "Periodo",
                                "Consumo (kWh)",
                                "Precio facturado (€/kWh)",
                                "Precio calculado (€/kWh)",
                                "Margen adicional (€/MWh)",
                                "Diferencia vs fórmula (€)",
                            ]
                        ].copy()
                        consumo_total = margen_facturado["consumo_kwh"]
                        detalle = pd.concat(
                            [
                                detalle,
                                pd.DataFrame([{
                                    "Periodo": "<strong>TOTAL</strong>",
                                    "Consumo (kWh)": consumo_total,
                                    "Precio facturado (€/kWh)": (
                                        margen_facturado[
                                            "precio_facturado_medio_eur_kwh"
                                        ]
                                    ),
                                    "Precio calculado (€/kWh)": (
                                        detalle_calculo["Coste fórmula (€)"].sum()
                                        / consumo_total
                                    ),
                                    "Margen adicional (€/MWh)": (
                                        margen_facturado["margen_adicional_eur_mwh"]
                                    ),
                                    "Diferencia vs fórmula (€)": (
                                        margen_facturado[
                                            "diferencia_coste_vs_formula_eur"
                                        ]
                                    ),
                                }]),
                            ],
                            ignore_index=True,
                        )
                        for columna in detalle.columns[1:]:
                            decimales = 6 if "€/kWh" in columna else 2
                            detalle[columna] = detalle[columna].map(
                                lambda valor, n=decimales: formato_numero_es(valor, n)
                            )
                        detalle.columns = [
                            "Periodo",
                            "Consumo<br>(kWh)",
                            "Precio facturado<br>(€/kWh)",
                            "Precio calculado<br>(€/kWh)",
                            "Margen adicional<br>(€/MWh)",
                            "Diferencia vs fórmula<br>(€)",
                        ]
                        st.markdown(
                            '<div style="overflow-x:auto">'
                            + detalle.to_html(index=False, escape=False, border=0)
                            + "</div>",
                            unsafe_allow_html=True,
                        )
        else:
            if st.session_state.get("_telemindex_curva_sin_normalizar", False):
                st.info("Corrige la carga y pulsa «Normalizar curva de carga».")
            else:
                st.info(
                    "Carga una curva para calcular sus consumos, costes y precios."
                )

# Código del antiguo tab Desglose conservado temporalmente, pero sin renderizar.
if False:
    st.subheader("Desglose justificativo del precio indexado", divider="rainbow")
    df_desglose = (
        st.session_state.df_curva_sheets
        if st.session_state.get("df_curva_sheets") is not None
        else df_filtrado_compartido
    )
    columna_consumo = (
        "consumo_neto_kWh"
        if "consumo_neto_kWh" in df_desglose.columns
        and pd.to_numeric(df_desglose["consumo_neto_kWh"], errors="coerce").sum() > 0
        else None
    )
    metodo_media = "ponderada por el consumo" if columna_consumo else "aritmética"
    fecha_limite_c2 = pd.to_datetime(st.session_state.ultima_fecha_csv).date()
    fechas_desglose = pd.to_datetime(df_desglose["fecha"], errors="coerce").dt.date
    fechas_validas_desglose = fechas_desglose.dropna()
    if fechas_validas_desglose.empty:
        texto_rango_desglose = "Sin fechas"
    else:
        fecha_inicio_desglose = fechas_validas_desglose.min()
        fecha_fin_desglose = fechas_validas_desglose.max()
        texto_rango_desglose = (
            fecha_inicio_desglose.strftime("%d/%m/%Y")
            if fecha_inicio_desglose == fecha_fin_desglose
            else (
                f"{fecha_inicio_desglose.strftime('%d/%m/%Y')} → "
                f"{fecha_fin_desglose.strftime('%d/%m/%Y')}"
            )
        )
    opciones_atr_desglose = ["2.0", "3.0", "6.1"]
    atr_curva = st.session_state.get("atr_dfnorm") if columna_consumo else None
    if atr_curva in opciones_atr_desglose:
        st.session_state.atr_desglose = atr_curva
    elif st.session_state.get("atr_desglose") not in opciones_atr_desglose:
        st.session_state.atr_desglose = "2.0"

    col_atr, col_media, col_c2 = st.columns([0.8, 1.1, 1.1])
    with col_atr:
        st.metric("Rango de fechas seleccionado", texto_rango_desglose)
        atr_desglose = st.selectbox(
            "Peaje de acceso",
            opciones_atr_desglose,
            key="atr_desglose",
            disabled=atr_curva in opciones_atr_desglose,
            help=(
                "El ATR se toma automáticamente de la curva cargada."
                if atr_curva in opciones_atr_desglose
                else "Selecciona el ATR que se aplicará a las dos tablas."
            ),
        )
    with col_media:
        st.metric("Tipo de media", metodo_media.capitalize())
    with col_c2:
        st.metric("Detalle C2 disponible hasta", fecha_limite_c2.strftime("%d/%m/%Y"))

    st.caption(
        f"Valores en €/kWh. Media {metodo_media}, por periodos y total del peaje "
        f"{atr_desglose}TD. La fila Precio final concilia con la fórmula activa."
    )

    formula_desglose = FormulaIndexada(
        desvios_apant=st.session_state.get("desvios_apant", 0.0),
        margen=st.session_state.get("margen_telemindex", 0.0),
        margen_pos=st.session_state.get("cfg_margen_pos", "neto"),
        otros_costes=st.session_state.get("otros_costes_indexado", 0.0),
        otros_costes_pos=st.session_state.get("cfg_otros_costes_pos", "neto"),
        incluir_fnee=st.session_state.get("cfg_fnee", False),
        fnee_pos=st.session_state.get("cfg_fnee_pos", "perdidas"),
        cf_pct=st.session_state.get("cf_pct", 0.0),
    )
    try:
        tabla_desglose = construir_desglose_precio_indexado(
            df_desglose,
            atr_desglose,
            formula_desglose,
            columna_consumo=columna_consumo,
        )
        tabla_desglose_mostrar = tabla_desglose.copy()
        for columna in tabla_desglose_mostrar.columns[1:]:
            tabla_desglose_mostrar[columna] = tabla_desglose_mostrar[columna].map(
                lambda valor: formato_eur_kwh(valor / 1000, 6, False)
            )
        st.markdown("#### Formación del precio final")
        col1_tabla_precio, col2_tabla_precio = st.columns([0.82, 0.18])
        with col1_tabla_precio:
            st.dataframe(
                tabla_desglose_mostrar,
                use_container_width=True,
                hide_index=True,
                height=38 + 35 * len(tabla_desglose),
            )
    except ValueError as exc:
        st.warning(f"No se puede construir el desglose del precio: {exc}")

    rango_dentro_c2 = (
        not fechas_validas_desglose.empty
        and fechas_desglose.notna().all()
        and fechas_validas_desglose.max() <= fecha_limite_c2
    )
    zona_peninsular = st.session_state.get("zona_periodos_index", "peninsula") == "peninsula"
    componentes_disponibles = all(
        columna in df_desglose.columns and df_desglose[columna].notna().all()
        for columna in COMPONENTES_SSAA_FORMULA
    )

    st.markdown("#### Desglose de los SSAA del C2 Compodem")
    if not zona_peninsular:
        st.info("El desglose C2 de SSAA está disponible únicamente para Península.")
    elif not rango_dentro_c2:
        st.info(
            "El rango supera la última fecha con detalle C2 "
            f"({fecha_limite_c2.strftime('%d/%m/%Y')}). Se mantiene la tabla global, "
            "pero no se muestra un desglose parcial de SSAA."
        )
    elif not componentes_disponibles:
        st.warning("El rango no contiene todas las columnas de detalle SSAA del C2.")
    else:
        tabla_ssaa = construir_desglose_ssaa_c2(
            df_desglose,
            COMPONENTES_SSAA_FORMULA,
            atr_desglose,
            columna_consumo=columna_consumo,
        )
        tabla_ssaa_mostrar = tabla_ssaa.copy()
        for columna in tabla_ssaa_mostrar.columns[1:]:
            tabla_ssaa_mostrar[columna] = tabla_ssaa_mostrar[columna].map(
                lambda valor: formato_eur_kwh(valor / 1000, 6, False)
            )
        st.dataframe(
            tabla_ssaa_mostrar,
            use_container_width=True,
            hide_index=True,
            height=38 + 35 * len(tabla_ssaa),
        )

with tab1:
    
        col1, col2, col3 = st.columns([.14, .58, .28], gap="small")

        #COLUMNA PRINCIPAL
        with col2:
            zona_txt = NOMBRE_ZONA_PERIODOS.get(zona_historico, "PENÍNSULA")
            texto_periodo_historico = st.session_state[
                CLAVES_FILTRO_HISTORICO["texto"]
            ]
            st.subheader(
                'Resumen de precios finales de INDEXADO - '
                f'Zona :blue[{zona_txt}]. '
                f'**:orange[{texto_periodo_historico}]**',
                divider='rainbow',
            )
            
            with st.container():
                col5, col6, col7, col8, col9 = st.columns(5)
                with col5:
                    #st.metric(':orange[Precio medio 2.0 c€/kWh]',value = media_20)
                    st.metric(':orange[Precio 2.0 c€/kWh]', value=formato_cent_eur_kwh(media_20, 2, False))
                with col6:
                    st.metric(':red[Precio 3.0 c€/kWh]', value=formato_cent_eur_kwh(media_30, 2, False))
                with col7:
                    st.metric(':blue[Precio 6.1 c€/kWh]', value=formato_cent_eur_kwh(media_61, 2, False))
                with col8:
                    st.metric(':green[SPOT €/MWh]', value=formato_eur_mwh(media_spot, 2, False))
                with col9:
                    st.metric(':violet[SSAA €/MWh]', value=formato_eur_mwh(media_ssaa, 2, False), delta=formato_pct(sobrecoste_ssaa, 1), delta_color='inverse', help= 'Se indica su valor medio y en qué % aumenta el precio medio Spot')

            st.empty()
            # gráfico principal de barras y lineas precios medios y omie+ssaa
            #st.plotly_chart(graf_principal(df_filtrado, colores_precios))
            st.plotly_chart(
                graficar_precios_medios_horarios(
                    df_historico,
                    colores_precios,
                    incluir_curva=False,
                    leyenda_horizontal=True,
                ),
                use_container_width=True,
            )
            st.empty()
            st.subheader("Peso de los componentes por peaje de acceso", divider='rainbow')
            #_, graf20, graf30, graf61 = pt1(df_filtrado)
            graf20, graf30, graf61 = graficar_queso_componentes(df_historico)
            for graf_queso in (graf20, graf30, graf61):
                graf_queso.update_layout(
                    height=390,
                    margin=dict(l=10, r=10, t=55, b=15),
                )
            with st.container():
                col10,col11,col12=st.columns(3)
                with col10:
                    st.write(graf20)    
                with col11:
                    st.write(graf30)
                with col12:
                    st.write(graf61)
                
            

        with col3:
            st.subheader("Tabla resumen de precios por peaje de acceso", divider='rainbow')
            with st.container():

                cols_precios = ["P1", "P2", "P3", "P4", "P5", "P6", "Media"]

                st.text(
                    'Precios finales (€/kWh)',
                    help=(
                        'Precios finales de indexado, basados en parámetros de fórmula. '
                        'Incluyen peajes y cargos.'
                    ),
                )
                df_tabla_precios_eur_kwh = ocultar_filas_curva(
                    df_tabla_precios
                )
                df_tabla_precios_eur_kwh[cols_precios] = (
                    df_tabla_precios_eur_kwh[cols_precios] / 100
                )
                df_tabla_precios_fmt = formatear_columnas_tabla(
                    df_tabla_precios_eur_kwh,
                    columnas_eur_kwh=cols_precios,
                    incluir_unidades=False,
                )
                df_tabla_precios_fmt = (
                    df_tabla_precios_fmt.rename_axis("Precio").reset_index()
                )
                df_tabla_precios_fmt["Precio"] = (
                    df_tabla_precios_fmt["Precio"].astype(str)
                    .str.replace(r"^precio_", "Precio final ", regex=True)
                    + " TD"
                )
                st.dataframe(
                    estilizar_etiquetas_atr(
                        df_tabla_precios_fmt, "Precio"
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

                # Las tablas resumidas de costes, ATR y margen se mantienen en
                # df_tabla_costes, df_tabla_pyc y df_tabla_margen para poder
                # recuperarlas, pero dejan de mostrarse en el tab Históricos.
                mostrar_desgloses_precios_historicos(
                    df_historico,
                    formula_historico,
                )

                st.subheader("Tablas de apuntamientos", divider="rainbow")
                with st.expander("Apuntamiento SPOT / OMIE"):
                    st.caption(
                        "Las filas por peaje muestran el apuntamiento horario sin ponderar."
                    )
                    mostrar_tabla_apuntamiento(
                        ocultar_filas_curva(df_tabla_apuntamiento)
                    )

                with st.expander("Apuntamiento SSAA"):
                    mostrar_tabla_apuntamiento(df_tabla_apuntamiento_ssaa)

                with st.expander("Apuntamiento precio final"):
                    mostrar_tabla_apuntamiento(df_tabla_apuntamiento_precio)

                st.subheader("¿Qué margen han cargado?", divider="rainbow")
                atr_margen_historico = st.selectbox(
                    "ATR de referencia",
                    ("2.0", "3.0", "6.1"),
                    format_func=lambda atr: f"{atr} TD",
                    key="telemindex_historico_atr_margen_facturado",
                    help=(
                        "La comparación usa los precios medios aritméticos "
                        "del ATR seleccionado en la tabla superior."
                    ),
                )
                columna_periodo_historico = (
                    "dh_3p" if atr_margen_historico == "2.0" else "dh_6p"
                )
                curva_aritmetica = df_historico.copy()
                curva_aritmetica["periodo"] = (
                    curva_aritmetica[columna_periodo_historico]
                    .astype(str).str.strip().str.upper()
                )
                periodos_validos_historico = periodos_no_aplicables_atr(
                    atr_margen_historico
                )
                periodos_validos_historico = [
                    f"P{i}" for i in range(1, 7)
                    if f"P{i}" not in periodos_validos_historico
                ]
                curva_aritmetica = curva_aritmetica.loc[
                    curva_aritmetica["periodo"].isin(periodos_validos_historico)
                ].copy()
                if not curva_aritmetica.empty:
                    fee_desde_factura = st.session_state.get(
                        "telemindex_fee_desde_factura"
                    )
                    contexto_consumos_factura = (
                        atr_margen_historico,
                        texto_periodo_historico,
                        zona_historico,
                    )
                    consumos_factura = (
                        fee_desde_factura.get("consumos")
                        if isinstance(fee_desde_factura, dict)
                        and str(fee_desde_factura.get("atr", ""))
                        == atr_margen_historico
                        else st.session_state.get(
                            "telemindex_historico_facturada_consumos"
                        )
                        if st.session_state.get(
                            "telemindex_historico_facturada_consumos_contexto"
                        ) == contexto_consumos_factura
                        else {}
                    )
                    consumos_factura = (
                        consumos_factura
                        if isinstance(consumos_factura, dict) else {}
                    )
                    def consumo_facturado_periodo(periodo):
                        valor = pd.to_numeric(
                            consumos_factura.get(periodo, 0), errors="coerce"
                        )
                        return max(float(valor), 0.0) if pd.notna(valor) else 0.0

                    consumos_validos = {
                        periodo: consumo_facturado_periodo(periodo)
                        for periodo in periodos_validos_historico
                    }
                    total_consumo_factura = sum(consumos_validos.values())
                    usa_reparto_factura = total_consumo_factura > 0
                    if usa_reparto_factura:
                        horas_por_periodo = (
                            curva_aritmetica["periodo"].value_counts()
                        )
                        curva_aritmetica["consumo_neto_kWh"] = (
                            curva_aritmetica["periodo"].map(consumos_validos)
                            .div(curva_aritmetica["periodo"].map(horas_por_periodo))
                            .fillna(0.0)
                        )
                    else:
                        curva_aritmetica["consumo_neto_kWh"] = (
                            1_000.0 / len(curva_aritmetica)
                        )
                    consumos_aritmeticos = (
                        curva_aritmetica.groupby("periodo")["consumo_neto_kWh"]
                        .sum().reindex([f"P{i}" for i in range(1, 7)], fill_value=0.0)
                    )
                    firma_historica_facturada = (
                        atr_margen_historico,
                        texto_periodo_historico,
                        zona_historico,
                        len(curva_aritmetica),
                    )
                    if (
                        isinstance(fee_desde_factura, dict)
                        and str(fee_desde_factura.get("atr", ""))
                        == atr_margen_historico
                    ):
                        precios_precargados = fee_desde_factura.get("precios")
                        if isinstance(precios_precargados, dict):
                            st.session_state[
                                "telemindex_historico_facturada_consumos"
                            ] = consumos_factura
                            st.session_state[
                                "telemindex_historico_facturada_consumos_contexto"
                            ] = contexto_consumos_factura
                            st.session_state[
                                "telemindex_historico_facturada_origen"
                            ] = "Manual"
                            for periodo, precio in precios_precargados.items():
                                st.session_state[
                                    f"telemindex_historico_facturada_manual_{periodo}"
                                ] = float(precio)
                            st.session_state[
                                "telemindex_historico_facturada_precios"
                            ] = precios_precargados
                            st.session_state[
                                "telemindex_historico_facturada_firma"
                            ] = firma_historica_facturada
                            st.session_state[
                                "telemindex_historico_facturada_origen_guardado"
                            ] = (
                                "Factura "
                                + str(fee_desde_factura.get("factura") or "")
                            ).strip()
                            st.session_state.pop(
                                "telemindex_fee_desde_factura", None
                            )
                    precios_historicos_facturados = render_precios_facturados(
                        consumos_aritmeticos,
                        atr_margen_historico,
                        firma_historica_facturada,
                        "telemindex_historico_facturada",
                        descripcion_periodo=(
                            "Precios medios facturados del término de energía "
                            "en €/kWh, sin impuestos ni potencia. Se comparan "
                            "con las medias aritméticas del periodo seleccionado."
                        ),
                    )
                    if precios_historicos_facturados:
                        try:
                            margen_historico = estimar_margen_facturado(
                                curva_aritmetica,
                                atr_margen_historico,
                                formula_historico,
                                precios_historicos_facturados,
                            )
                        except (ValueError, KeyError) as exc:
                            st.warning(f"No se puede estimar el margen: {exc}")
                        else:
                            render_impacto_margen(
                                margen_historico,
                                texto_metodo=(
                                    "Estimación sobre medias aritméticas, con una "
                                    "base real de "
                                    f"{formato_kwh(total_consumo_factura, 2, True)} "
                                    "distribuida según los consumos P1–P6 de la factura."
                                    if usa_reparto_factura else
                                    "Estimación sobre medias aritméticas, con una "
                                    "base normalizada de 1.000 kWh repartida "
                                    "uniformemente entre las horas del periodo."
                                ),
                            )
                            render_detalle_margen(margen_historico)

        with col1:
            mostrar_controles_telemindex(lista_meses, fecha_ultima_filtrado)


with tab2:
    # gráfico de evolución de los precios medios mensuales
    st.subheader("Comparativa anual de los precios medios de indexado, por peaje de acceso (media acumulada)", divider='rainbow')
    if (
        not error_prevision_indexados
        and not df_prevision_indexados_2026.empty
    ):
        impacto_anual = calcular_impacto_anual_previsto(
            st.session_state.df_sheets,
            df_prevision_indexados_2026,
            anio_base=2025,
            anio_previsto=2026,
        )
        if not impacto_anual.empty:
            columnas_impacto = st.columns(3)
            etiquetas_consumo = {
                "2.0 TD": "1.000 kWh",
                "3.0 TD": "100.000 kWh",
                "6.1 TD": "1 GWh",
            }
            for columna_ui, (_, fila) in zip(
                columnas_impacto, impacto_anual.iterrows()
            ):
                atr_impacto = str(fila["ATR"])
                impacto_euros = float(fila["Impacto (€)"])
                impacto_pct = float(fila["Impacto (%)"])
                es_sobrecoste = impacto_euros > 0
                es_ahorro = impacto_euros < 0
                concepto = (
                    "sobrecoste" if es_sobrecoste else
                    "ahorro" if es_ahorro else "mismo coste"
                )
                color_impacto = (
                    "#f44747" if es_sobrecoste else
                    "#22c55e" if es_ahorro else "#9ca3af"
                )
                fondo_impacto = (
                    "rgba(244,71,71,.10)" if es_sobrecoste else
                    "rgba(34,197,94,.10)" if es_ahorro else
                    "rgba(156,163,175,.10)"
                )
                signo_pct = "+" if impacto_pct > 0 else ""
                icono_sobrecoste = (
                    "<span style='display:inline-block;"
                    "transform:translateX(-.2rem) scaleY(.62);"
                    "margin-right:.55rem;'>▲</span>"
                    if es_sobrecoste else ""
                )
                columna_ui.markdown(
                    f"""
                    <div style="min-height:170px;padding:18px 18px;
                        border:1px solid {color_impacto}88;
                        border-left:6px solid {color_impacto};
                        border-radius:14px;background:{fondo_impacto};
                        display:flex;flex-direction:column;
                        justify-content:center;text-align:center;
                        box-shadow:0 5px 14px rgba(0,0,0,.12);">
                      <div style="font-size:1.25rem;font-weight:800;
                          letter-spacing:.08em;color:#9ca3af;margin-bottom:.55rem;">
                        IMPACTO PREVISTO 2026 · ATR {atr_impacto}
                      </div>
                      <div style="font-size:.94rem;line-height:1.45;">
                        Para un suministro de
                        <strong style="font-size:1.18rem;color:#d6b85a;">
                          {etiquetas_consumo[atr_impacto]} anuales
                        </strong>
                        en indexado, en 2026 el término de energía supondrá,
                        respecto a 2025, un {concepto} de
                      </div>
                      <div style="font-size:2.15rem;font-weight:900;
                          color:{color_impacto};margin-top:.4rem;line-height:1.1;">
                        {icono_sobrecoste}{formato_euros(abs(impacto_euros), 2)}
                        <span style="font-size:1.35rem;">
                          ({signo_pct}{formato_pct(impacto_pct, 1)})
                        </span>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
    st.plotly_chart(graf_precios_diarios, use_container_width=True)
    if error_prevision_indexados:
        st.caption(
            "La previsión de Simulindex no está disponible temporalmente: "
            f"{error_prevision_indexados}"
        )
    st.subheader("Evolución de los precios medios de indexado, por meses", divider='rainbow')
    st.plotly_chart(graf_mensual)
    st.subheader("Evolución de los precios medios de indexado, por días", divider='rainbow')
    st.plotly_chart(graf_evol_precios_diarios, use_container_width=True)
    
    

    resumen_comparativa, fechas_corte_comparativa = preparar_comparativa_mensual_indexados(
        st.session_state.df_sheets,
        anio_base=2025,
        anio_comp=2026,
    )
    df_delta, fig_delta = graficar_diferencial_precios_mensuales(
        df_mensual=resumen_comparativa,
        anio_base=2025,
        anio_comp=2026,
        convertir_a_cent_kwh=False
    )
    c1, c2 = st.columns(2)
    with c1:
        fecha_corte_mes_actual = (
            max(fechas_corte_comparativa.values())
            if fechas_corte_comparativa
            else None
        )
        st.caption(
            "Precios finales según ATR · diferencias en c€/kWh · "
            "2026 frente a 2025"
            + (
                f" · ambos hasta el {fecha_corte_mes_actual.strftime('%d.%m')}"
                if fecha_corte_mes_actual is not None
                else ""
            )
        )
        st.plotly_chart(fig_delta, use_container_width=True)
        
    with c2:
        MESES_ORDEN = [
            "enero", "febrero", "marzo", "abril",
            "mayo", "junio", "julio", "agosto",
            "septiembre", "octubre", "noviembre", "diciembre"
        ]
        df_mes_años = tabla_evol_mes_por_años(
            df_precios_mensuales_sin_curva, MESES_ORDEN
        )
        #st.subheader("Comparativa mensual (precios en c€/kWh)", divider='rainbow')
        st.subheader(f"Comparativa mensual de precios (c€/kWh) - {st.session_state.mes_select_evol}", divider='rainbow')
        st.selectbox("Selecciona mes", MESES_ORDEN, key = 'mes_select_evol')
        st.dataframe(
        df_mes_años.style.format({
            "SPOT": "{:.2f}",
            "Precio 2.0": "{:.2f}",
            "Precio 3.0": "{:.2f}",
            "Precio 6.1": "{:.2f}",
            "Ratio 2.0 / SPOT": "{:.2f}",
            "Ratio 3.0 / SPOT": "{:.2f}",
            "Ratio 6.1 / SPOT": "{:.2f}",
        }),
        use_container_width=True,
        hide_index=True
    )
    mostrar_impacto_spot()


with tab3:
    df_curva_comparativa = st.session_state.get("df_curva_sheets")
    if df_curva_comparativa is None or df_curva_comparativa.empty:
        st.warning("Sube una curva de carga")
        st.stop()
    
    c1, c2, c3 = st.columns(3)
    with c1:
        
        # TABLA RESUMEN DE CONSUMOS, COSTES Y PRECIOS MEDIOS DE INDEXADO PONDERADOS A LA CURVA DE CARGA

        df_resumen = obtener_df_resumen(
            st.session_state.df_curva_sheets, None, 0.0
        )
        periodos_en_blanco = periodos_no_aplicables_atr(
            st.session_state.get("atr_dfnorm", "")
        )
        periodos_afectados = (
            df_curva_sheets["periodo"].dropna().astype(str)
            .str.strip().str.upper().unique().tolist()
        )
        df_resumen_fmt = formatear_resumen_mixto(
            df_resumen,
            columnas_en_blanco=periodos_en_blanco,
            periodos_afectados=periodos_afectados,
        )

        
        
        fecha_inicio_curva, fecha_fin_curva = (
            pd.to_datetime(fecha).date()
            for fecha in st.session_state.rango_curvadecarga
        )
        texto_periodo_curva = (
            fecha_inicio_curva.strftime("%d/%m/%Y")
            if fecha_inicio_curva == fecha_fin_curva
            else (
                f"{fecha_inicio_curva.strftime('%d/%m/%Y')} → "
                f"{fecha_fin_curva.strftime('%d/%m/%Y')}"
            )
        )
        st.subheader(
            f'Resumen de :red[INDEXADO] · :green[{texto_periodo_curva}]'
        )
        st.caption(
            describir_formula_indexada(
                obtener_formula_compartida(),
                st.session_state.get("atr_dfnorm", ""),
                color_atr="green",
            )
        )
        #st.dataframe(df_resumen_view, use_container_width=True)
        st.dataframe(df_resumen_fmt, use_container_width=True)
        from io import BytesIO

        output = BytesIO()
        df_resumen.to_excel(output, index=True, engine="openpyxl")
        output.seek(0)
        fecha_inicio, fecha_fin = st.session_state.rango_curvadecarga
        nombre_excel = f"resumen_indexado_{fecha_inicio:%Y%m%d}_{fecha_fin:%Y%m%d}.xlsx"


        st.download_button(
            "Descargar Excel",
            data=output,
            file_name=nombre_excel,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        df_resumen_cober = obtener_df_resumen(df_curva_cober_omip, None, 0.0)
        df_resumen_cober_view = formatear_resumen_mixto(
            df_resumen_cober,
            columnas_en_blanco=periodos_en_blanco,
            periodos_afectados=periodos_afectados,
        )
        #st.subheader(f'Resumen de :violet[COBERTURA] para el suministro con peaje de acceso :orange[{st.session_state.atr_dfnorm}]')
        st.subheader(f'Resumen de :violet[COBERTURA]')
        ca,cb = st.columns(2)
        with ca:
            st.number_input('Introduce el valor de la cobertura realizada', min_value=20.0, max_value=120.0, step=.1, key = 'precio_cobertura', help = 'Se aplicará un apuntamiento medio real a la cobertura realizada')
        with cb:
            st.metric('Apuntamiento medio ponderado', value=apuntamiento_spot)
        st.dataframe(df_resumen_cober_view, use_container_width=True)


        st.session_state.df_ofertas_fijas = render_bloque_ofertas_fijas(
            df_resumen.loc["Consumo (kWh)"],
            st.session_state.get("atr_dfnorm", ""),
            "telemindex_fijos",
            titulo="Tabla de precios :orange[FIJOS] para comparar",
            periodos_afectados=periodos_afectados,
            titulo_selector_expander="📋 Ofertas cargadas",
        )
        render_simulador_horquilla_ssaa(
            st.session_state.df_ofertas_fijas,
            "telemindex_fijos",
            df_curva_uso,
            columna_perdidas=f"perd_{st.session_state.atr_dfnorm}",
            apuntamiento_spot=apuntamiento_spot,
        )

        with c2:

            import pandas as pd
            

            periodos = [f"P{i}" for i in range(1, 7)]

            # Consumos por periodo
            consumos = df_resumen.loc["Consumo (kWh)", periodos]

            # Ofertas fijas: cálculo compartido con el Comparador.
            df_ofertas_comparativa = st.session_state.get("df_ofertas_fijas")
            resultados_fijos = comparar_ofertas_fijas(
                consumos,
                df_ofertas_comparativa
                if isinstance(df_ofertas_comparativa, pd.DataFrame)
                else pd.DataFrame(),
            ).rename(columns={
                "Coste energía (€)": "Coste (€)",
                "Precio medio energía (€/kWh)": "Precio medio (€/kWh)",
            })
            resultados = resultados_fijos.to_dict("records")

            # Indexado
            precios_index = df_resumen.loc["Precio medio (€/kWh)", periodos]
            coste_index = (consumos * precios_index).sum()
            precio_medio_index = coste_index / consumos.sum()

            resultados.append({
                "Oferta": "Indexado",
                "Tipo": "Indexado",
                "Coste (€)": coste_index,
                "Precio medio (€/kWh)": precio_medio_index
            })

            # Cobertura OMIP
            precios_cober = df_resumen_cober.loc["Precio medio (€/kWh)", periodos]
            coste_cober = (consumos * precios_cober).sum()
            precio_medio_cober = coste_cober / consumos.sum()

            resultados.append({
                "Oferta": "Cobertura",
                "Tipo": "Cobertura",
                "Coste (€)": coste_cober,
                "Precio medio (€/kWh)": precio_medio_cober
            })



            df_resultados = pd.DataFrame(resultados)
            # Plotly puede interpretar como números etiquetas de texto como
            # "1" o "2". Normalizamos de nuevo junto al punto de visualización.
            df_resultados["Oferta"] = df_resultados["Oferta"].astype(str).str.strip()

            opciones_referencia = df_resultados["Oferta"].tolist()
            clave_referencia = "telemindex_referencia_comparativa"
            referencia_inicial = (
                "Indexado" if "Indexado" in opciones_referencia
                else opciones_referencia[0]
            )
            if st.session_state.get(clave_referencia) not in opciones_referencia:
                st.session_state[clave_referencia] = referencia_inicial

            st.subheader(
                "📊 Comparativa TOTALPOWER · "
                f"ATR :green[{normalizar_atr(st.session_state.atr_dfnorm)} TD]"
            )
            referencia_comparativa = st.selectbox(
                "Referencia para calcular las diferencias",
                opciones_referencia,
                key=clave_referencia,
                help=(
                    "Los importes negativos son más baratos que la referencia; "
                    "los positivos, más caros."
                ),
            )
            df_resultados = referenciar_comparativa_costes(
                df_resultados, referencia_comparativa
            )

            df_view = df_resultados.copy()

            df_view["Coste (€)"] = df_view["Coste (€)"].apply(
                lambda x: formato_euros(x, unidad=False)
            )

            df_view["Precio medio (€/kWh)"] = df_view["Precio medio (€/kWh)"].apply(
                lambda x: formato_eur_kwh(x, unidad=False)
            )

            columna_delta_euros = f"Δ vs {referencia_comparativa} (€)"
            columna_delta_pct = f"Δ vs {referencia_comparativa} (%)"
            df_view = df_view.rename(columns={
                "Δ referencia (€)": columna_delta_euros,
                "Δ referencia (%)": columna_delta_pct,
            })
            df_view[columna_delta_euros] = df_view[columna_delta_euros].apply(
                lambda x: formato_euros(x, unidad=False)
            )
            df_view[columna_delta_pct] = df_view[columna_delta_pct].apply(
                lambda x: formato_pct(x, 1)
            )
            filas_referencia = df_view.pop("Es referencia")
            estilo_tabla = df_view.style.apply(
                lambda _: [
                    (
                        "background-color: rgba(34, 197, 94, 0.18); "
                        "font-weight: 700"
                    ) if es_referencia else ""
                    for es_referencia in filas_referencia
                ],
                axis=0,
            )
            st.dataframe(
                estilo_tabla, use_container_width=True, hide_index=True
            )

            orden_ofertas = df_resultados["Oferta"].tolist()

            fig = px.bar(
                df_resultados,
                y="Oferta",
                x="Coste (€)",
                color="Tipo",
                color_discrete_map=COLORES_TIPO_CONTRATO,
                title=f"Coste por oferta/tipo de contrato",
                text_auto=".2f",
                category_orders={"Oferta": orden_ofertas},
                orientation ='h'
            )
            fig.update_layout(
                xaxis_title="Coste (€)",
                yaxis_title="",
                legend_title="",
                title_font=dict(size=24),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="center",
                    x=0.5
                )
            )
            fig.update_yaxes(
                type="category",
                categoryorder="array",
                categoryarray=orden_ofertas,
                autorange="reversed",
                tickmode="array",
                tickvals=orden_ofertas,
                ticktext=[
                    "" if oferta == referencia_comparativa else escape(oferta)
                    for oferta in orden_ofertas
                ],
            )
            fig.update_traces(
                textfont_size=24,
                width=0.6,
            )

            fig = aplicar_estilo(fig)
            altura_grafico_barras = max(300, 150 + len(df_resultados) * 55)
            margen_etiquetas = max(
                120,
                max(len(str(oferta)) for oferta in orden_ofertas) * 9 + 28,
            )
            fig.update_layout(
                height=altura_grafico_barras,
                bargap=0.4,
                barcornerradius=4,
                margin_l=margen_etiquetas,
            )
            fig.update_yaxes(tickfont=dict(size=16))
            fig.add_annotation(
                x=-0.01,
                y=referencia_comparativa,
                xref="paper",
                yref="y",
                text=f"<b>{escape(referencia_comparativa)}</b>",
                showarrow=False,
                xanchor="right",
                yanchor="middle",
                bgcolor="rgba(34, 197, 94, 0.18)",
                bordercolor="rgba(34, 197, 94, 0.55)",
                borderwidth=1,
                borderpad=4,
                font=dict(size=16),
            )

            st.plotly_chart(fig, use_container_width=True)

        with c3:
            referencia_comparativa = st.session_state.get(
                "telemindex_referencia_comparativa", "Indexado"
            )
            opciones_comparativa = [
                opcion for opcion in curvas_comparativa
                if opcion != referencia_comparativa
            ]
            if st.session_state.get("opcion_comparativa") not in opciones_comparativa:
                st.session_state.opcion_comparativa = opciones_comparativa[0]
            opcion_comparativa = st.session_state.opcion_comparativa
            titulo_comp = (
                f"Comparativa {referencia_comparativa} vs {opcion_comparativa}"
            )
            st.subheader(titulo_comp)
            opcion_elegida = st.selectbox(
                f"Selecciona una opción para comparar con {referencia_comparativa}",
                opciones_comparativa,
                key='opcion_comparativa',
            )
            opcion_comparativa = opcion_elegida

            # Las curvas se resuelven después de leer ambos selectores para
            # que todos los gráficos representen exactamente el estado visible.
            df_curva_referencia = curvas_comparativa[referencia_comparativa]
            df_curva_comp = curvas_comparativa[opcion_elegida]
            tipo_referencia = tipos_comparativa[referencia_comparativa]
            tipo_seleccion = tipos_comparativa[opcion_elegida]
            color_referencia = COLORES_TIPO_CONTRATO[tipo_referencia]
            color_serie_comp = COLORES_TIPO_CONTRATO[tipo_seleccion]

            df_referencia_h = (
                df_curva_referencia[["fecha", "hora", "coste_total"]]
                .groupby(["fecha", "hora"], as_index=False)["coste_total"]
                .sum()
                .rename(columns={"coste_total": "coste_referencia"})
            )
            df_seleccion_h = (
                df_curva_comp[["fecha", "hora", "coste_total"]]
                .groupby(["fecha", "hora"], as_index=False)["coste_total"]
                .sum()
                .rename(columns={"coste_total": "coste_seleccion"})
            )
            df_heat = df_referencia_h.merge(
                df_seleccion_h, on=["fecha", "hora"], how="inner"
            )
            df_heat["dif_coste"] = (
                df_heat["coste_referencia"] - df_heat["coste_seleccion"]
            )
            heatmap_data = df_heat.pivot_table(
                index="fecha", columns="hora", values="dif_coste"
            ).reindex(sorted(df_heat["hora"].unique()), axis=1)
            zmax = float(abs(heatmap_data.to_numpy()).max())
            fig_heat = px.imshow(
                heatmap_data,
                color_continuous_scale="RdYlGn_r",
                zmin=-zmax,
                zmax=zmax,
                color_continuous_midpoint=0,
                aspect="auto",
                labels={"x": "Hora", "y": "Día", "color": "Δ Coste (€)"},
            )
            fig_heat.update_layout(
                title="",
                xaxis=dict(
                    title="Hora del día", tickmode="array",
                    tickvals=list(range(24)), tickfont=dict(size=12),
                ),
                yaxis=dict(title="Fecha", tickfont=dict(size=12), automargin=True),
                coloraxis_colorbar=dict(title="Δ Coste (€)", tickfont=dict(size=12)),
                margin=dict(l=40, r=40, t=60, b=40),
                height=700,
            )
            fig_heat.update_traces(
                xgap=1,
                ygap=1,
                hovertemplate=(
                    "<b>Día:</b> %{y}<br><b>Hora:</b> %{x}<br>"
                    f"<b>Diferencia {referencia_comparativa} - "
                    f"{opcion_elegida}:</b> %{{z:.2f}} €<extra></extra>"
                ),
            )

            with st.expander("🔥 Mapa de calor de diferencias horarias"):
                st.plotly_chart(fig_heat, use_container_width=True)

            df_coste_referencia_h = (
                df_curva_referencia
                .groupby("hora", as_index=False)["coste_total"]
                .mean()
            )
            graf_medias_horarias=graficar_media_horaria('Total')
            graf_medias_horarias.add_trace(
                go.Scatter(
                    x=df_coste_referencia_h["hora"],
                    y=df_coste_referencia_h["coste_total"],
                    mode="lines",
                    name=f"Coste medio {referencia_comparativa}",
                    line=dict(
                        color=color_referencia,
                        width=5
                    ),
                    yaxis="y2"
                )
            )
            graf_medias_horarias.update_layout(
                yaxis2=dict(
                    title="Coste medio (€)",
                    overlaying="y",
                    side="right",
                    showgrid=False
                ),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.0,
                    xanchor="center",
                    x=0.5
                )
            )
            df_coste_comp = df_curva_comp.copy()
            df_coste_comp_h = (
                df_coste_comp
                .groupby("hora", as_index=False)["coste_total"]
                .mean()
            )
            graf_medias_horarias.add_trace(
                go.Scatter(
                    x=df_coste_comp_h["hora"],
                    y=df_coste_comp_h["coste_total"],
                    mode="lines",
                    name=f"Coste medio {opcion_comparativa}",
                    line=dict(color=color_serie_comp, width=5),
                    yaxis="y2"
                )
            )

            with st.expander("🕒 Perfil medio horario de costes"):
                st.plotly_chart(
                    graf_medias_horarias,
                    use_container_width=True,
                )

            costes_mensuales = comparar_costes_mensuales_referenciados(
                df_curva_referencia,
                df_curva_comp,
            )
            nombre_referencia = referencia_comparativa
            nombre_seleccion = opcion_comparativa
            grafico_mensual = costes_mensuales.rename(columns={
                "Coste referencia (€)": nombre_referencia,
                "Coste selección (€)": nombre_seleccion,
            }).melt(
                id_vars="Mes",
                var_name="Alternativa",
                value_name="Coste mensual (€)",
            )
            grafico_mensual["Mes"] = grafico_mensual["Mes"].map(
                formato_mes_es
            )
            grafico_mensual["Coste mostrado"] = grafico_mensual[
                "Coste mensual (€)"
            ].map(lambda valor: formato_numero_es(valor, 0))
            color_seleccion = color_serie_comp
            fig_mensual = px.bar(
                grafico_mensual,
                x="Mes",
                y="Coste mensual (€)",
                color="Alternativa",
                barmode="group",
                title="Comparativa mensual de costes",
                color_discrete_map={
                    nombre_referencia: color_referencia,
                    nombre_seleccion: color_seleccion,
                },
                text="Coste mostrado",
            )
            hover_costes_mensuales = {}
            for _, fila_mes in costes_mensuales.iterrows():
                etiqueta_mes = formato_mes_es(fila_mes["Mes"])
                coste_referencia_mes = fila_mes["Coste referencia (€)"]
                coste_seleccion_mes = fila_mes["Coste selección (€)"]
                diferencia_mes = coste_referencia_mes - coste_seleccion_mes
                hover_costes_mensuales[etiqueta_mes] = (
                    f"<b>{etiqueta_mes}</b><br>"
                    f"Coste {nombre_referencia}: "
                    f"{formato_numero_es(coste_referencia_mes, 2)} €<br>"
                    f"Coste {nombre_seleccion}: "
                    f"{formato_numero_es(coste_seleccion_mes, 2)} €<br>"
                    f"Diferencia {nombre_referencia} - {nombre_seleccion}: "
                    f"{formato_numero_es(diferencia_mes, 2)} €"
                )
            for traza in fig_mensual.data:
                traza.customdata = [
                    hover_costes_mensuales[str(mes)] for mes in traza.x
                ]
                traza.hovertemplate = "%{customdata}<extra></extra>"
            fig_mensual = aplicar_estilo(fig_mensual)
            fig_mensual.update_traces(
                textposition="outside",
                textfont_size=16,
                cliponaxis=False,
            )
            fig_mensual.update_layout(
                xaxis_title="",
                yaxis_title="Coste mensual (€)",
                legend_title="",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                hovermode="closest",
                bargap=0.4,
                bargroupgap=0.32,
                barcornerradius=5,
            )
            with st.expander("📊 Comparativa mensual de costes"):
                st.plotly_chart(fig_mensual, use_container_width=True)

            costes_acumulados = costes_mensuales.copy()
            columnas_coste = [
                "Coste referencia (€)", "Coste selección (€)"
            ]
            costes_acumulados[columnas_coste] = (
                costes_acumulados[columnas_coste].cumsum()
            )
            grafico_acumulado = costes_acumulados.rename(columns={
                "Coste referencia (€)": nombre_referencia,
                "Coste selección (€)": nombre_seleccion,
            }).melt(
                id_vars="Mes",
                var_name="Alternativa",
                value_name="Coste acumulado (€)",
            )
            grafico_acumulado["Mes"] = grafico_acumulado["Mes"].map(
                formato_mes_es
            )
            fig_acumulado = px.line(
                grafico_acumulado,
                x="Mes",
                y="Coste acumulado (€)",
                color="Alternativa",
                markers=True,
                title="Evolución del coste acumulado",
                color_discrete_map={
                    nombre_referencia: color_referencia,
                    nombre_seleccion: color_seleccion,
                },
            )
            hover_costes_acumulados = {}
            for _, fila_mes in costes_acumulados.iterrows():
                etiqueta_mes = formato_mes_es(fila_mes["Mes"])
                acumulado_referencia = fila_mes["Coste referencia (€)"]
                acumulado_seleccion = fila_mes["Coste selección (€)"]
                diferencia_acumulada = acumulado_referencia - acumulado_seleccion
                hover_costes_acumulados[etiqueta_mes] = (
                    f"<b>{etiqueta_mes}</b><br>"
                    f"Acumulado {nombre_referencia}: "
                    f"{formato_numero_es(acumulado_referencia, 2)} €<br>"
                    f"Acumulado {nombre_seleccion}: "
                    f"{formato_numero_es(acumulado_seleccion, 2)} €<br>"
                    f"Diferencia acumulada {nombre_referencia} - "
                    f"{nombre_seleccion}: "
                    f"{formato_numero_es(diferencia_acumulada, 2)} €"
                )
            for traza in fig_acumulado.data:
                traza.customdata = [
                    hover_costes_acumulados[str(mes)] for mes in traza.x
                ]
                traza.hovertemplate = "%{customdata}<extra></extra>"
            fig_acumulado = aplicar_estilo(fig_acumulado)
            fig_acumulado.update_traces(line=dict(width=4), marker=dict(size=9))
            fig_acumulado.update_layout(
                xaxis_title="",
                yaxis_title="Coste acumulado (€)",
                legend_title="",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            with st.expander("📈 Evolución del coste acumulado"):
                st.plotly_chart(fig_acumulado, use_container_width=True)

            diferencias_mensuales = (
                costes_mensuales["Coste referencia (€)"]
                - costes_mensuales["Coste selección (€)"]
            )
            diferencial_total = diferencias_mensuales.sum()
            fig_cascada = graficar_cascada_diferencias_mensuales(
                costes_mensuales["Mes"].map(formato_mes_es),
                diferencias_mensuales,
                titulo=(
                    "Diferencial mensual acumulado: "
                    f"{formato_numero_es(diferencial_total, 2)} €"
                ),
                color_positivo="#d62728",
                color_negativo="#2ca02c",
            )
            with st.expander("🧮 Diferencial mensual acumulado"):
                st.caption(
                    f"Cada barra muestra el coste de {nombre_referencia} menos "
                    f"el coste de {nombre_seleccion}. Los valores positivos "
                    f"indican que {nombre_referencia} es más caro; los negativos, "
                    f"que {nombre_referencia} es más barato. La última barra recoge el "
                    "diferencial total del periodo."
                )
                st.plotly_chart(fig_cascada, use_container_width=True)
            
            ofertas_fijas_merma = [
                oferta for oferta in curvas_comparativa
                if tipos_comparativa.get(oferta) == "Fijo"
            ]
            if ofertas_fijas_merma:
                with st.expander(
                    "🩸 Merma de margen del contrato fijo", expanded=False
                ):
                    fijo_merma = st.selectbox(
                        "Contrato fijo analizado",
                        ofertas_fijas_merma,
                        key="telemindex_fijo_merma",
                    )
                    ingreso_fijo = float(
                        curvas_comparativa[fijo_merma]["coste_total"].sum()
                    )
                    tabla_merma = calcular_merma_margen_fijo(
                        ingreso_fijo,
                        {
                            "Cobertura": curvas_comparativa["Cobertura"],
                            "Indexado 100 %": curvas_comparativa["Indexado"],
                        },
                    )
                    merma_cobertura = float(
                        tabla_merma.loc[
                            tabla_merma["Escenario"].eq("Cobertura"), "Merma (€)"
                        ].iloc[0]
                    )
                    merma_indexado = float(
                        tabla_merma.loc[
                            tabla_merma["Escenario"].eq("Indexado 100 %"), "Merma (€)"
                        ].iloc[0]
                    )
                    st.metric(
                        "Coste adicional de no haber cubierto",
                        formato_euros(
                            merma_indexado - merma_cobertura, 2, False
                        ),
                        help=(
                            "Diferencia entre comprar finalmente a indexado y "
                            "haber ejecutado la cobertura."
                        ),
                    )
                    st.caption(
                        "La merma es la diferencia directa entre el coste de cada "
                        "escenario y el ingreso contratado en fijo. En «Solo margen» "
                        "se mide cuánto margen queda después de absorberla; en "
                        "«Margen + otros costes» se amplía el colchón con ambos "
                        "componentes. Los desvíos apantallados no se añaden como "
                        "colchón adicional."
                    )
                    for lectura in ("Solo margen", "Margen + otros costes"):
                        st.markdown(f"**{lectura}**")
                        datos_lectura = tabla_merma.loc[
                            tabla_merma["Lectura"].eq(lectura)
                        ]
                        columnas_metricas = st.columns(2)
                        for columna, (_, fila) in zip(
                            columnas_metricas, datos_lectura.iterrows()
                        ):
                            resultado = float(fila["Resultado (€)"])
                            consumido = float(fila["Colchón consumido (%)"])
                            estado = (
                                "margen restante" if resultado >= 0
                                else "déficit tras agotar el colchón"
                            )
                            columna.metric(
                                str(fila["Escenario"]),
                                formato_euros(resultado, 2, False),
                                delta=(
                                    f"{formato_pct(consumido, 1)} consumido"
                                    if pd.notna(consumido) else "Sin colchón"
                                ),
                                delta_color="inverse",
                                help=(
                                    f"Resultado: {estado}. Colchón inicial: "
                                    f"{formato_euros(fila['Colchón inicial (€)'], 2)}. "
                                    f"Merma frente al fijo: "
                                    f"{formato_euros(fila['Merma (€)'], 2)}."
                                ),
                            )

                    tabla_merma_view = tabla_merma[[
                        "Escenario", "Lectura", "Colchón inicial (€)",
                        "Coste sin colchón (€)", "Resultado (€)",
                        "Merma (€)", "Colchón consumido (%)",
                    ]].copy()
                    st.dataframe(
                        tabla_merma_view.style.format({
                            "Colchón inicial (€)": lambda x: formato_euros(x, 2, False),
                            "Coste sin colchón (€)": lambda x: formato_euros(x, 2, False),
                            "Resultado (€)": lambda x: formato_euros(x, 2, False),
                            "Merma (€)": lambda x: formato_euros(x, 2, False),
                            "Colchón consumido (%)": lambda x: formato_pct(x, 1),
                        }),
                        use_container_width=True,
                        hide_index=True,
                    )


with tab4:
    st.subheader("Verificación de la regularización de SSAA", divider="rainbow")
    st.caption(
        "Los meses completos se muestran como regularizaciones cerradas y los "
        "meses parciales como estimaciones sobre los días y el consumo cargados, "
        "sin extrapolar al final del mes. La tabla compara "
        "el criterio contractual por media aritmética mensual con la aplicación "
        "de la misma horquilla a cada hora. En el cálculo horario no se aplica "
        "apuntamiento, porque el perfil ya está recogido en el consumo real horario."
    )

    df_curva_ssaa = st.session_state.get("df_curva_sheets")
    if df_curva_ssaa is None or df_curva_ssaa.empty:
        st.warning("Introduce una curva de carga que contenga meses naturales completos.")
    else:
        atr_ssaa = st.session_state.atr_dfnorm
        perdidas_contractuales_defecto = 17.0 if atr_ssaa == "2.0" else 7.0
        metodo_ssaa = st.radio(
            "Método principal de verificación",
            ["Media aritmética mensual", "Hora a hora"],
            horizontal=True,
            help="Los dos resultados se calculan siempre para poder comparar su diferencia.",
        )

        with st.expander("Parámetros contractuales", expanded=True):
            p1, p2, p3, p4, p5 = st.columns(5)
            ref_inferior = p1.number_input(
                "Referencia inferior (€/MWh)", value=13.0, step=0.1, key="ssaa_ref_inferior"
            )
            ref_superior = p2.number_input(
                "Referencia superior (€/MWh)", value=16.0, step=0.1, key="ssaa_ref_superior"
            )
            perdidas_ssaa = p3.number_input(
                "Pérdidas media mensual (%)", min_value=0.0,
                value=perdidas_contractuales_defecto, step=0.5,
                key=f"ssaa_perdidas_{atr_ssaa}",
                help="La verificación hora a hora toma las pérdidas horarias del CSV.",
            )
            ap_ssaa = p4.number_input(
                "Apuntamiento media mensual", min_value=0.0, value=1.02, step=0.01,
                format="%.3f", key="ssaa_ap",
                help="No se aplica en la verificación hora a hora.",
            )
            hl_ssaa = p5.number_input(
                "Hacienda Local", min_value=0.0, value=1.015, step=0.001, format="%.3f", key="ssaa_hl"
            )

        if ref_inferior >= ref_superior:
            st.error("La referencia inferior debe ser menor que la referencia superior.")
        else:
            columna_perdidas_ssaa = f"perd_{atr_ssaa}"
            st.caption(
                f"En el método hora a hora se aplica `{columna_perdidas_ssaa}` "
                "del CSV a cada registro."
            )
            df_verificacion, meses_excluidos = calcular_verificacion_ssaa(
                df_curva_ssaa,
                referencia_inferior=ref_inferior,
                referencia_superior=ref_superior,
                perdidas_pct=perdidas_ssaa,
                apuntamiento=ap_ssaa,
                hacienda_local=hl_ssaa,
                columna_perdidas_horarias=columna_perdidas_ssaa,
            )

            if meses_excluidos:
                st.warning(
                    "Periodos excluidos por contener datos nulos: "
                    + ", ".join(meses_excluidos)
                )

            if df_verificacion.empty:
                st.warning("El periodo seleccionado no contiene datos suficientes para el cálculo.")
            else:
                col_metodo = (
                    "Regularización media mensual (€)"
                    if metodo_ssaa == "Media aritmética mensual"
                    else "Regularización hora a hora (€)"
                )
                total_media = df_verificacion["Regularización media mensual (€)"].sum()
                total_horas = df_verificacion["Regularización hora a hora (€)"].sum()
                total_principal = df_verificacion[col_metodo].sum()
                periodos_parciales = df_verificacion.loc[
                    df_verificacion["Estado"] != "Completo", "Periodo"
                ].tolist()
                diferencia_total = total_horas - total_media
                diferencia_pct = (
                    diferencia_total / abs(total_media) * 100
                    if total_media != 0
                    else None
                )

                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Método seleccionado", metodo_ssaa)
                m2.metric("Regularización seleccionada", formato_euros(total_principal, 2))
                m3.metric("Media mensual", formato_euros(total_media, 2))
                m4.metric("Hora a hora", formato_euros(total_horas, 2))
                m5.metric(
                    "Diferencia",
                    formato_euros(diferencia_total, 2),
                    delta=formato_pct(diferencia_pct, 2) if diferencia_pct is not None else "Sin base",
                    delta_color="inverse",
                    help="Hora a hora menos media mensual. El porcentaje se calcula sobre el valor absoluto de la media mensual.",
                )

                if periodos_parciales:
                    st.info(
                        "Estimaciones parciales incluidas: "
                        + ", ".join(periodos_parciales)
                        + ". Sus importes solo abarcan el consumo cargado."
                    )

                st.markdown("#### Detalle mensual")
                columnas_euros = [
                    "Regularización media mensual (€)",
                    "Regularización hora a hora (€)",
                    "Diferencia entre métodos (€)",
                ]
                formato_tabla = {
                    "SSAA medio (€/MWh)": "{:.2f}",
                    "Diferencia mensual (€/MWh)": "{:+.2f}",
                    "Consumo (MWh)": "{:,.2f}",
                    **{col: "{:+,.2f}" for col in columnas_euros},
                }
                st.dataframe(
                    df_verificacion.drop(columns=["Año"]).style.format(formato_tabla),
                    use_container_width=True,
                    hide_index=True,
                )

                df_trimestral = (
                    df_verificacion.groupby("Trimestre", as_index=False)
                    .agg(
                        Meses=("Periodo", "count"),
                        Meses_parciales=(
                            "Estado", lambda estados: (estados != "Completo").sum()
                        ),
                        **{
                            "Consumo (MWh)": ("Consumo (MWh)", "sum"),
                            "Media mensual (€)": ("Regularización media mensual (€)", "sum"),
                            "Hora a hora (€)": ("Regularización hora a hora (€)", "sum"),
                            "Diferencia (€)": ("Diferencia entre métodos (€)", "sum"),
                        },
                    )
                )
                df_trimestral["Estado"] = df_trimestral.apply(
                    lambda fila: (
                        "Trimestre completo"
                        if fila["Meses"] == 3 and fila["Meses_parciales"] == 0
                        else "Trimestre parcial/estimado"
                    ),
                    axis=1,
                )
                st.markdown("#### Resumen trimestral")
                st.dataframe(
                    df_trimestral.style.format({
                        "Consumo (MWh)": "{:,.2f}",
                        "Media mensual (€)": "{:+,.2f}",
                        "Hora a hora (€)": "{:+,.2f}",
                        "Diferencia (€)": "{:+,.2f}",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )
