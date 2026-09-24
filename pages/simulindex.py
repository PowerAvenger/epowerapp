import streamlit as st
import hashlib
from io import BytesIO
from pathlib import Path
from backend_simulindex import (obtener_historicos_meff, obtener_meff_anual, obtener_meff_trimestral, obtener_meff_mensual,
                                pyc_2026,
                                obtener_hist_mensual, obtener_spot_mensual, obtener_spot_diario,
                                obtener_graf_hist, obtener_grafico_omip, obtener_grafico_omip_omie,
                                obtener_trimestres_futuros,
                                construir_escenarios_pricing_trimestral,
                                calcular_cobertura_trimestral_horaria,
                                graficar_2026,
                                graficar_curva_omip_mensual_12m,
                                construir_media_prevista_2026_diaria, graficar_media_prevista_2026,
                                construir_evolucion_media_omip, añadir_omie_real_12m_posterior, graficar_evolucion_media_omip, añadir_omie_real_12m_alineado_omip,
                                añadir_suavizado_omip_y_diferencial, graficar_omip_suavizado_vs_omie_real, graficar_omip_vs_omie_previsto_ajustado_1y)
from backend_comun import colores_precios, obtener_df_resumen, formatear_df_resumen, formatear_df_resultados, aplicar_estilo
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from backend_previsiones import (
    guardar_prevision_omip_12m_en_sesion,
    obtener_prevision_omip_12m,
)
from utilidades import (
    generar_menu,
    init_app,
    init_app_index,
    mostrar_parametros_formula_indexado,
    persist_widget,
)
from formato_es import formato_cent_eur_kwh, formato_eur_mwh, formato_numero_es
from backend_previsiones import (
    guardar_prevision_omie_en_sesion,
    obtener_prevision_omie_anual,
)
from backend_indexado import (
    FormulaIndexada,
    calcular_combo_index_fijo,
    calcular_precios_atr_formula,
    resumir_precio_ponderado,
)
from backend_telemindex import añadir_costes_curva, construir_df_curva_sheets
from backend_opt2 import (
    consumos_mensuales_desde_curva_normalizada,
    normalizar_tabla_consumos_sips,
)
from backend_sips import (
    combinar_consumos_sips, es_sips_excel, leer_sips_completo,
    perfil_anual_meses_naturales,
)
from backend_pricing_indexados import (
    calcular_escenarios_pricing_mensuales,
    obtener_pyc_historico_por_periodo,
    preparar_referencia_pricing,
)
from backend_ofertas_fijas import (
    cargar_catalogo_ofertas,
    precios_energia_oferta,
)
from backend_ofertas_pass_pool import obtener_oferta_pass_pool
from componentes_ofertas_fijas import (
    combinar_ofertas,
    normalizar_excel_ofertas,
    periodos_con_consumo,
    render_bloque_ofertas_fijas,
    render_oferta_ia,
)
from componentes_indexados import (
    render_escenarios_omie,
    render_formula_indexada,
    render_otros_escenarios,
    sincronizar_escenarios_aplicados,
)
from componentes_curva import render_origen_curva, render_resumen_grafico_curva
from informe_simulindex import mostrar_informe_comparador_trimestral

def _limpiar_consumos_comparador():
    """Descarta los consumos compartidos y los archivos seleccionados."""
    for clave in (
        'df_consumos_pricing', 'df_consumos_pricing_origen', 'sips_pricing',
        'upload_consumos_comparador_simulindex',
        'pricing_upload_consumos', 'firma_consumos_comparador_simulindex',
        '_pendiente_pricing_atr_seleccionado',
        '_limpiar_upload_pricing_por_comparador',
        '_reiniciar_atr_sips_comparador',
        'simulindex_comparador_atr_sips_manual',
        'pricing_atr_manual_confirmado_sips',
        'pricing_atr_seleccionado',
    ):
        st.session_state.pop(clave, None)


def _confirmar_atr_pricing_sips():
    st.session_state.pricing_atr_manual_confirmado_sips = True


def _cambiar_archivo_pricing():
    st.session_state.pop('df_consumos_pricing', None)
    st.session_state.pop('df_consumos_pricing_origen', None)
    st.session_state.pop('sips_pricing', None)
    st.session_state.pop('pricing_atr_manual_confirmado_sips', None)
    st.session_state.pop('pricing_atr_seleccionado', None)
    st.session_state.pop('simulindex_comparador_atr_sips_manual', None)


@st.cache_data(show_spinner=False, max_entries=12)
def _leer_sips_pricing(nombre, contenido):
    """Evita volver a leer los mismos SIPS en cada recarga de Pricing."""
    archivo = BytesIO(contenido)
    archivo.name = nombre
    return leer_sips_completo(archivo)


def _confirmar_atr_comparador_sips():
    atr = st.session_state.get('simulindex_comparador_atr_sips_manual')
    if atr is not None:
        st.session_state.pricing_atr_seleccionado = atr
        st.session_state.pricing_atr_manual_confirmado_sips = True

if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')

generar_menu()
init_app()
if st.session_state.pop('_limpiar_upload_pricing_por_comparador', False):
    st.session_state.pop('pricing_upload_consumos', None)
if st.session_state.pop('_reiniciar_atr_sips_comparador', False):
    st.session_state.pop('simulindex_comparador_atr_sips_manual', None)
    st.session_state.pop('pricing_atr_manual_confirmado_sips', None)
    st.session_state.pop('pricing_atr_seleccionado', None)

st.sidebar.header('⚡ Simulindex: Futuros de indexados ⚡')
zona_mensajes = st.sidebar.empty()
if 'df_sheets' not in st.session_state:
    zona_mensajes.warning('Cargando históricos de indexado. Espera a que estén disponibles...', icon = '⚠️')

# Simulindex conserva por ahora su metodología peninsular. La selección SNP
# pertenece a Telemindex y no debe recortar aquí el histórico provisional ESIOS.
zona_telemindex_previa = st.session_state.get("zona_periodos_index", "peninsula")
st.session_state.zona_periodos_index = "peninsula"
init_app_index()
st.session_state.zona_periodos_index = zona_telemindex_previa


df_historicos_FTB, ultimo_registro = obtener_historicos_meff()
df_FTB_trimestral, df_FTB_trimestral_futuros, fecha_ultimo_omip_trimestral, media_omip_trimestral, lista_trimestres_hist, trimestre_actual, df_ultimos_precios_trim = obtener_meff_trimestral(df_historicos_FTB)
df_FTB_mensual, df_FTB_mensual_simulindex, fecha_ultimo_omip_mensual, media_omip_mensual, lista_meses_hist, mes_actual = obtener_meff_mensual(df_historicos_FTB)
df_FTB_anual, df_FTB_anual_simulindex, fecha_ultimo_omip_anual, media_omip_anual, lista_años_hist, año_actual, df_ultimos_precios_años = obtener_meff_anual(df_historicos_FTB)

#print('df FTB mensual')
#print(df_FTB_mensual)
#print('df FTB trimestral')
#print(df_FTB_trimestral)

if 'omie_slider' not in st.session_state:
    st.session_state.omie_slider = round(media_omip_trimestral)
def reset_slider():
    st.session_state.omie_slider = round(media_omip_trimestral)

if 'trimestre_cobertura' not in st.session_state:
    st.session_state.trimestre_cobertura = trimestre_actual
if 'mes_cobertura' not in st.session_state:
    st.session_state.mes_cobertura = mes_actual 

#print("mes_cobertura:", repr(st.session_state.mes_cobertura))    

lista_trimestres_futuros, trimestre_inicial = obtener_trimestres_futuros(df_FTB_trimestral_futuros)   

if 'trimestre_futuro' not in st.session_state:
    st.session_state.trimestre_futuro = trimestre_inicial



def aplicar_pyc_2026_atr(df, pyc_2026):
    df = df.copy()

    map_atr_periodo = {
        "2.0": "dh_3p",
        "3.0": "dh_6p",
        "6.1": "dh_6p"
    }

    map_atr_col = {
        "2.0": "2.0TD",
        "3.0": "3.0TD",
        "6.1": "6.1TD"
    }

    for atr_short in ["2.0", "3.0", "6.1"]:
        col_periodo = map_atr_periodo[atr_short]
        atr_col = map_atr_col[atr_short]
        pyc_dict = pyc_2026[atr_col]

        df[f"pyc_{atr_short}_hist"] = df[f"pyc_{atr_short}"]
        df[f"pyc_{atr_short}"] = df[col_periodo].map(pyc_dict) * 1000

        df[f"precio_{atr_short}"] = (
            df[f"coste_{atr_short}"]
            + df[f"pyc_{atr_short}"]
            + df[f"margen_{atr_short}"]
            + df.get(f"otros_costes_{atr_short}", 0.0)
        )

    return df

st.session_state.pyc_2026 = pyc_2026

df_base = st.session_state.df_sheets.copy()
df_base = aplicar_pyc_2026_atr(df_base, st.session_state.pyc_2026)
df_sheets_origen = df_base.copy()

# Simulindex conserva su propia curva enriquecida. La clave df_curva_sheets de
# Telemindex es una salida de presentacion y puede pasar a None al cambiar su
# selector entre rango, mes o año; eso no debe invalidar la curva normalizada.
df_norm_simulindex = st.session_state.get("df_norm_h")
columnas_coste_simulindex = {"coste_base", "coste_margen", "coste_total"}
if isinstance(df_norm_simulindex, pd.DataFrame) and not df_norm_simulindex.empty:
    fechas_firma_curva = pd.to_datetime(
        df_norm_simulindex.get("fecha_hora", df_norm_simulindex.get("fecha")),
        errors="coerce",
    )
    fechas_firma_precios = pd.to_datetime(df_base["fecha"], errors="coerce")
    firma_curva_simulindex = (
        len(df_norm_simulindex),
        fechas_firma_curva.min(),
        fechas_firma_curva.max(),
        st.session_state.get("atr_dfnorm"),
        st.session_state.get("curva_reactiva_version", 0),
        len(df_base),
        fechas_firma_precios.max(),
    )
    df_curva_simulindex = st.session_state.get(
        "df_curva_simulindex_persistente"
    )
    necesita_reconstruir_curva = (
        not isinstance(df_curva_simulindex, pd.DataFrame)
        or df_curva_simulindex.empty
        or not columnas_coste_simulindex.issubset(
            df_curva_simulindex.columns
        )
        or st.session_state.get("_firma_curva_simulindex")
        != firma_curva_simulindex
    )
    if necesita_reconstruir_curva:
        df_curva_simulindex = construir_df_curva_sheets(df_base)
        df_curva_simulindex = añadir_costes_curva(df_curva_simulindex)
        st.session_state.df_curva_simulindex_persistente = (
            df_curva_simulindex
        )
        st.session_state._firma_curva_simulindex = firma_curva_simulindex

    # Compatibilidad con el resto del codigo historico de esta pagina.
    st.session_state.df_curva_sheets = df_curva_simulindex

# obtenemos históricos de medias mensuales de omie df_mes y un filtrado hist de los últimos 12 meses 
if 'df_curva_sheets' in st.session_state and st.session_state.df_curva_sheets is not None:
    def n_meses_df(df, col_fecha="fecha"):
        return (
            pd.to_datetime(df[col_fecha])
            .dt.to_period("M")
            .nunique()
        )
    MIN_MESES_OPT = 4
    if n_meses_df(st.session_state.df_curva_sheets) >= MIN_MESES_OPT:
        #CÓDIGO AÑADIDO PARA USAR PYCS2026 EN LA SIMULACION
        #st.session_state.pyc_2026 = pyc_2026
        df_simul = st.session_state.df_curva_sheets.copy()
        cons = df_simul["consumo_neto_kWh"] / 1000 #pasamos a MWh
        atr_map = {
            "2.0": "2.0TD",
            "3.0": "3.0TD",
            "6.1": "6.1TD"
        }
        atr_col = atr_map[st.session_state.atr_dfnorm]
        pyc_dict = st.session_state.pyc_2026[atr_col]
        df_simul["pyc_simul"] = df_simul["periodo"].map(pyc_dict)*1000 #pasamos a €/MWh
        df_simul["coste_pyc_simul"] = df_simul["pyc_simul"] * cons
        df_simul["coste_total_simul"] = df_simul["coste_base"] + df_simul["coste_pyc_simul"] + df_simul["coste_margen"]
        #df_simul["coste_total_simul"] += 3.0 * cons #+1 SSAA + 1,2 FNEE + 0,4 SRAD
        df_sheets_origen = df_simul

        margen_simul = round(df_simul[f"margen_{st.session_state.atr_dfnorm}"].iloc[0],3)





df_hist = obtener_hist_mensual(df_sheets_origen)

if 'media_ssaa_prev' not in st.session_state:
    st.session_state.media_ssaa_prev = 20.0
if 'media_fnee_prev' not in st.session_state:
    st.session_state.media_fnee_prev = 2.68
if 'media_rad3_prev' not in st.session_state:
    st.session_state.media_rad3_prev = 1.7

media_ssaa_hist = round(df_hist['ssaa'].mean(),2)
media_rad3_hist =round(df_hist['rad3'].mean(),2)
media_ssaa_hist = round(media_ssaa_hist - media_rad3_hist,2)
media_fnee_hist = round(df_hist['fnee'].mean(),2)

añadir_ssaa = round(st.session_state.media_ssaa_prev - media_ssaa_hist,2)
añadir_fnee = round(st.session_state.media_fnee_prev - media_fnee_hist,2)
añadir_rad3 = round(st.session_state.media_rad3_prev - media_rad3_hist,2)
añadir_hist = añadir_fnee+añadir_rad3+añadir_ssaa
añadir_hist = añadir_hist*(1+0.1)*(1.015)/10



grafico, simul20, simul30, simul61, simulcurva, resultados = obtener_graf_hist(df_hist, st.session_state.omie_slider, colores_precios, añadir_hist)

df_spot_mensual = obtener_spot_mensual()


# Inicializamos margen a cero
if 'margen_simulindex' not in st.session_state:
    st.session_state.margen_simulindex = 0

    

graf_omip_trimestral = obtener_grafico_omip(df_FTB_trimestral_futuros)
graf_omip_mensual = obtener_grafico_omip(df_FTB_mensual_simulindex)
graf_omip_anual = obtener_grafico_omip(df_FTB_anual_simulindex)

# Los futuros de Simulindex empiezan en M+1. El contrato del mes en curso se
# conserva aparte para visualizar su evolución sin alterar esa metodología.
df_FTB_mensual_mes_actual = df_FTB_mensual[
    df_FTB_mensual["Entrega"].eq(mes_actual)
].copy()
graf_omip_mensual_mes_actual = obtener_grafico_omip(
    df_FTB_mensual_mes_actual
)

df_trim_sel = df_FTB_trimestral[df_FTB_trimestral['Entrega'] == st.session_state.trimestre_futuro].copy()
graf_omip_trimestral_select = obtener_grafico_omip(df_trim_sel)


# dfs para trimestres históricos
df_FTB_trimestral_cobertura = df_FTB_trimestral[df_FTB_trimestral['Entrega'] == st.session_state.trimestre_cobertura]
df_FTB_mensual_cobertura = df_FTB_mensual[df_FTB_mensual['Entrega'] == st.session_state.mes_cobertura]
trimestre_sel, año_corto_sel = st.session_state.trimestre_cobertura.split('-')
primer_mes_trimestre = (int(trimestre_sel[1]) - 1) * 3 + 1
meses_trimestre = range(primer_mes_trimestre, primer_mes_trimestre + 3)
año_trimestre = 2000 + int(año_corto_sel)
spot_trimestre = df_spot_mensual.loc[
    (df_spot_mensual.index.year == año_trimestre)
    & (df_spot_mensual.index.month.isin(meses_trimestre)),
    'spot'
].dropna()
media_omie_trimestre = round(spot_trimestre.mean(), 2) if not spot_trimestre.empty else None
#print('df FTB trimestral cobertura')
#print(df_FTB_trimestral_cobertura)
graf_omip_omie_trimestral = obtener_grafico_omip_omie(df_FTB_trimestral_cobertura, df_spot_mensual, st.session_state.trimestre_cobertura)
graf_omip_omie_mensual = obtener_grafico_omip_omie(df_FTB_mensual_cobertura, df_spot_mensual, st.session_state.mes_cobertura)



if "df_ofertas_fijas_simul" not in st.session_state:
    st.session_state.df_ofertas_fijas_simul = pd.DataFrame()
if "df_ofertas_fijas_simul_trim" not in st.session_state:
    st.session_state.df_ofertas_fijas_trim = pd.DataFrame()    


#BARRA LATERAL+++++++++++++++++++++++++++++++++++++++++++++++++++++++

zona_mensajes.success('Cargados todos los históricos de **OMIP**. Ya puedes consultar los datos.', icon = '👍')
st.sidebar.info(f'Última fecha disponible: {ultimo_registro.strftime("%d.%m.%Y")}')
if st.sidebar.button('Actualizar datos', use_container_width=True):
    obtener_historicos_meff.clear()
    st.rerun()

with st.sidebar.expander('¡Personaliza la simulación!', icon = "ℹ️"):
    st.write('Usa el deslizador para modificar el valor de :green[OMIE] estimado. No te preocupes, siempre puedes resetear al valor por defecto.')
st.sidebar.slider(':green[OMIE] en €/MWh', min_value = 30, max_value = 150, step = 1, key = 'omie_slider')
reset_omip = st.sidebar.button('Resetear OMIE', on_click = reset_slider)
 
with st.sidebar.expander('¿Quieres añadir margen?', icon = "ℹ️"):
    st.write('Añade :violet[margen] al gusto y obtén un precio medio de indexado más ajustado con tus necesidades.')
    #añadir_margen = st.sidebar.toggle('Quieres añadir :violet[margen]?')
    #if añadir_margen:

if 'df_curva_sheets' in st.session_state and st.session_state.df_curva_sheets is not None and simulcurva is not None:
    st.sidebar.slider('Añade margen al precio base de indexado en €/MWh', min_value = 0, max_value = 50, step = 1, key = 'margen_simulindex', disabled=True)
else:
    st.sidebar.slider('Añade margen al precio base de indexado en €/MWh', min_value = 0, max_value = 50, step = 1, key = 'margen_simulindex', disabled=False)

zona_mensajes = st.sidebar.empty()


simul20_margen = simul20 + st.session_state.margen_simulindex / 10
simul30_margen = simul30 + st.session_state.margen_simulindex / 10
simul61_margen = simul61 + st.session_state.margen_simulindex / 10



if 'df_curva_sheets' in st.session_state and st.session_state.df_curva_sheets is not None and simulcurva is not None:
    # esto es para la tabla original de la página principal que se modifica con el margen del slider
    #simulcurva_margen = simulcurva + st.session_state.margen_simulindex / 10
    df_resumen_simul = obtener_df_resumen(st.session_state.df_curva_sheets, simulcurva, 0.0)
    df_resumen_simul_view = formatear_df_resumen(df_resumen_simul)
    df_uso_anual = st.session_state.df_curva_sheets.copy() 
    def filtrar_df_trimestre(df_norm, producto):
        
        mapa_trimestres = {
            'Q1': [1,2,3],
            'Q2': [4,5,6],
            'Q3': [7,8,9],
            'Q4': [10,11,12]
        }
        
        trim, _ = producto.split('-')
        meses_trim = mapa_trimestres[trim]
        
        df_trim = df_norm[
            df_norm['fecha_hora'].dt.month.isin(meses_trim)
        ].copy()
        
        return df_trim
    df_uso_trimestral = filtrar_df_trimestre(st.session_state.df_curva_sheets, st.session_state.trimestre_futuro)

    

prevision_omie_anual = obtener_prevision_omie_anual(df_spot_mensual)
guardar_prevision_omie_en_sesion(prevision_omie_anual)
df_2026 = prevision_omie_anual["curva_mensual"]
precio_medio_2026 = prevision_omie_anual["media_anual"]
graf_2026 = graficar_2026(df_2026, precio_medio_2026)

prevision_omip_12m = obtener_prevision_omip_12m()
guardar_prevision_omip_12m_en_sesion(prevision_omip_12m)
fecha_ref_prevision_12m = prevision_omip_12m["fecha_referencia"]
df_año_movil = prevision_omip_12m["curva_mensual"]
precio_medio_omip = prevision_omip_12m["media_12m"]
graf_año_movil = graficar_curva_omip_mensual_12m(df_año_movil, precio_medio_omip)

df_spot_diario = obtener_spot_diario()
df_media_2026 = construir_media_prevista_2026_diaria(
    df_spot_diario=df_spot_diario,
    df_ftb_m=df_FTB_mensual,
    df_ftb_q=df_FTB_trimestral,
    año=2026,
    col_fecha_spot="fecha",
    col_spot="spot"
)

fig_media_2026 = graficar_media_prevista_2026(df_media_2026)


df_evol_media_forward = construir_evolucion_media_omip(
    df_ftb_m=df_FTB_mensual,
    df_ftb_q=df_FTB_trimestral,
    fecha_ref=fecha_ref_prevision_12m,
    fecha_inicio="01.01.2024"
)

#antigua df_evol_media_forward (antes df_evol_media_forward) # OMIE real año móvil desde el día exacto
df_evol_media_forward_real = añadir_omie_real_12m_posterior(
    df_evol=df_evol_media_forward,
    df_spot_diario=df_spot_diario,   # aquí tu DF diario de OMIE real
    col_fecha_evol="Fecha",
    col_fecha_spot="fecha",
    col_spot="spot"
)

# OMIE real alineado con OMIP rolling 12m que añadimos al OMIP rolling 12m (mes en curso + 1)
df_evol_media_forward = añadir_omie_real_12m_alineado_omip(
    df_evol=df_evol_media_forward,
    df_spot_diario=df_spot_diario,   # aquí tu DF diario de OMIE real
    col_fecha_evol="Fecha",
    col_fecha_spot="fecha",
    col_spot="spot",
    meses =12,
    exigir_ventana_completa=True
)

#fig_media_forward = graficar_evolucion_media_omip(df_evol_media_forward)
fig_media_forward = graficar_evolucion_media_omip(
    df_evol_media_forward,
    col_omie="omie_real_12m_alineado_omip",
    col_ventana_completa="ventana_completa_omie_alineado",
    nombre_omie="OMIE real 12M alineado",
    titulo="OMIP forward 12M vs OMIE real 12M alineado"
)

ventana_suavizado = 15
df_evol_media_forward_suav = añadir_suavizado_omip_y_diferencial(
    df_evol=df_evol_media_forward,
    ventana_dias=ventana_suavizado,
    col_fecha="Fecha",
    col_omip="media_forward_12m",
    #col_omie="omie_real_12m"
    col_omie="omie_real_12m_alineado_omip"
)

# Valor inicial del SPOT previsto de Pricing. El valor editado se guarda en
# una clave independiente del widget para conservarlo al salir de la página.
serie_forward_suav = pd.to_numeric(
    df_evol_media_forward_suav['media_forward_12m_suav'], errors='coerce'
).dropna()
spot_forward_suav_default = (
    float(serie_forward_suav.iloc[-1])
    if not serie_forward_suav.empty else float(precio_medio_omip)
)
spot_forward_suav_default = round(spot_forward_suav_default, 2)
spot_forward_auto_anterior = st.session_state.get('_pricing_spot_forward_auto_anterior')
clave_spot_guardado = 'simulindex_pricing_spot_forward_guardado'
if clave_spot_guardado not in st.session_state:
    valor_anterior = st.session_state.get('pricing_spot_forward_12m')
    st.session_state[clave_spot_guardado] = (
        float(valor_anterior) if valor_anterior is not None
        else spot_forward_suav_default
    )
spot_forward_actual = st.session_state[clave_spot_guardado]
if spot_forward_actual is None:
    st.session_state[clave_spot_guardado] = spot_forward_suav_default
elif (
    not st.session_state.get('_pricing_spot_forward_manual', False)
    and spot_forward_auto_anterior is not None
    and abs(float(spot_forward_actual) - float(spot_forward_auto_anterior)) < 1e-9
):
    st.session_state[clave_spot_guardado] = spot_forward_suav_default
elif (
    spot_forward_auto_anterior is not None
    and abs(float(spot_forward_actual) - float(spot_forward_auto_anterior)) >= 1e-9
):
    st.session_state['_pricing_spot_forward_manual'] = True
st.session_state._pricing_spot_forward_auto_anterior = spot_forward_suav_default


def guardar_spot_forward_pricing():
    st.session_state[clave_spot_guardado] = st.session_state[
        '_widget_pricing_spot_forward_12m'
    ]
    st.session_state['_pricing_spot_forward_manual'] = True

fig_omip_suav_vs_omie = graficar_omip_suavizado_vs_omie_real(
    df_evol=df_evol_media_forward_suav,
    ventana_dias=ventana_suavizado,
    col_omie="omie_real_12m_alineado_omip",
)


fecha_max_omie_real = df_spot_diario["fecha"].max()

fig_omie_omip_ajuste, df_previsto_1y = graficar_omip_vs_omie_previsto_ajustado_1y(
    df_evol=df_evol_media_forward_suav,
    ventana_dias=15,
    col_fecha="Fecha",
    col_omip="media_forward_12m",
    col_omip_suav="media_forward_12m_suav",
    #col_omie_real="omie_real_12m",
    col_omie_real="omie_real_12m_alineado_omip",
    fecha_max_omie_real=fecha_max_omie_real
)   

intercept_20, slope_20, r2_20 = resultados['precio_2.0']
elasticidad_20 = (slope_20 * df_hist['spot'].mean()) / df_hist['precio_2.0'].mean()


def sincronizar_input_prevision(origen, destino):
    """Mantiene enlazados los inputs equivalentes de Principal y Pricing."""
    valor = st.session_state[origen]
    if destino.startswith('pricing_'):
        st.session_state[f'_pendiente_{destino}'] = valor
    else:
        st.session_state[destino] = valor


def sincronizar_prevision_principal(clave_principal, clave_pricing):
    """Conserva el ajuste de Principal al cambiar de sección."""
    valor = st.session_state[f'_widget_{clave_principal}']
    st.session_state[clave_principal] = valor
    st.session_state[f'_pendiente_{clave_pricing}'] = valor


_previsiones_principal_pricing = {
    'pricing_ssaa_forward_12m': 'media_ssaa_prev',
    'pricing_fnee_prev': 'media_fnee_prev',
    'pricing_srad_prev': 'media_rad3_prev',
}
_sincronizacion_inicial = not st.session_state.get(
    '_previsiones_principal_pricing_sincronizadas', False
)
for clave_pricing, clave_principal in _previsiones_principal_pricing.items():
    if _sincronizacion_inicial or clave_pricing not in st.session_state:
        st.session_state[clave_pricing] = st.session_state[clave_principal]
    clave_pendiente = f'_pendiente_{clave_pricing}'
    if clave_pendiente in st.session_state:
        st.session_state[clave_pricing] = st.session_state.pop(clave_pendiente)
st.session_state['_previsiones_principal_pricing_sincronizadas'] = True

sincronizar_escenarios_aplicados(
    st.session_state,
    'escenarios_comparador_simulindex',
    {
        'ssaa': float(st.session_state.pricing_ssaa_forward_12m),
        'srad': float(st.session_state.pricing_srad_prev),
        'fnee': float(st.session_state.pricing_fnee_prev),
    },
)




seccion_simulindex = st.segmented_control('Sección', [
    'Principal',
    'Futuros',
    'Previsión anual',
    'OMIP vs OMIE',
    'Comparador',
    'Cobertura trimestral',
    'Pricing',
    'Combo index-fijo',
    'Informes',
], default='Principal', key='seccion_simulindex')

# =======================================================================================================================================================================
# PRICING
# Prepara las tablas que utiliza Comparador; solo se muestra su interfaz al
# seleccionar Pricing.
# =======================================================================================================================================================================
if seccion_simulindex != 'Pricing':
    st.markdown(
        '<style>.st-key-pricing_contenido_oculto {display: none;}</style>',
        unsafe_allow_html=True,
    )
contenedor_pricing = st.container(
    key=(
        'pricing_contenido_oculto'
        if seccion_simulindex != 'Pricing' else 'pricing_contenido_visible'
    )
)
with contenedor_pricing:
    col_pricing1, col_pricing2, col_pricing3 = st.columns(3)

    with col_pricing1:
        st.subheader('Parámetros de pricing', divider='rainbow')
        with st.expander('Parametriza el escenario'):
            col_spot_pricing, col_ssaa_pricing = st.columns(2)
            with col_spot_pricing:
                st.session_state['_widget_pricing_spot_forward_12m'] = (
                    st.session_state[clave_spot_guardado]
                )
                spot_forward_pricing = st.number_input(
                    'SPOT previsto (€/MWh)', min_value=0.0, step=0.1,
                    key='_widget_pricing_spot_forward_12m',
                    on_change=guardar_spot_forward_pricing,
                    help=(
                        'Parte del último valor de la media OMIP forward 12 meses '
                        'suavizada del tab Previsión anual.'
                    ),
                )
                st.session_state[clave_spot_guardado] = spot_forward_pricing
            with col_ssaa_pricing:
                ssaa_forward_pricing = st.number_input(
                    'SSAA previstos sin SRAD (€/MWh)', min_value=0.0,
                    max_value=40.0, step=0.1,
                    key='pricing_ssaa_forward_12m',
                    on_change=sincronizar_input_prevision,
                    args=('pricing_ssaa_forward_12m', 'media_ssaa_prev'),
                )
            col_fnee_pricing, col_srad_pricing = st.columns(2)
            with col_fnee_pricing:
                fnee_pricing = st.number_input(
                    'FNEE previsto (€/MWh)', min_value=0.0, max_value=4.0,
                    step=0.1, key='pricing_fnee_prev',
                    on_change=sincronizar_input_prevision,
                    args=('pricing_fnee_prev', 'media_fnee_prev'),
                )
            with col_srad_pricing:
                srad_pricing = st.number_input(
                    'SRAD previsto (€/MWh)', min_value=0.0, max_value=3.0,
                    step=0.1, key='pricing_srad_prev',
                    on_change=sincronizar_input_prevision,
                    args=('pricing_srad_prev', 'media_rad3_prev'),
                )
        with st.expander('Parametriza componentes'):
            mostrar_parametros_formula_indexado(
                widget_suffix='simulindex_pricing',
                dos_filas_tres_columnas=True,
            )

        with st.expander('Origen de los consumos'):
            # Simulindex trabaja habitualmente con la versión horaria compartida.
            # Algunas curvas recuperadas de sesión pueden conservar df_norm_h sin
            # conservar la tabla de intervalos original df_norm.
            df_curva_pricing_actual = st.session_state.get('df_norm_h')
            if df_curva_pricing_actual is None or df_curva_pricing_actual.empty:
                df_curva_pricing_actual = st.session_state.get('df_norm')
            atr_curva_pricing = str(
                st.session_state.get('atr_dfnorm', '')
            ).upper().removesuffix('TD')
            curva_pricing_disponible = (
                df_curva_pricing_actual is not None
                and not df_curva_pricing_actual.empty
                and atr_curva_pricing in {'2.0', '3.0', '6.1', '6.2'}
            )
            opciones_origen_consumos = ['Subir Excel / SIPS']
            if curva_pricing_disponible:
                opciones_origen_consumos.append('Usar curva normalizada')
            origen_consumos_pricing = st.radio(
                'Origen de los consumos',
                options=opciones_origen_consumos,
                horizontal=True,
                key='pricing_origen_consumos',
                label_visibility='collapsed',
            )
            usar_curva_pricing = origen_consumos_pricing == 'Usar curva normalizada'
            archivos_pricing_sesion = st.session_state.get('pricing_upload_consumos') or []
            if not isinstance(archivos_pricing_sesion, list):
                archivos_pricing_sesion = [archivos_pricing_sesion]
            sips_pricing_detectado = None
            atr_sips_pricing = None
            error_sips_pricing = None
            if not usar_curva_pricing and archivos_pricing_sesion:
                try:
                    if len(archivos_pricing_sesion) > 1:
                        sips_pricing_detectado = combinar_consumos_sips([
                            _leer_sips_pricing(archivo.name, archivo.getvalue())
                            for archivo in archivos_pricing_sesion
                        ])
                    else:
                        archivo = archivos_pricing_sesion[0]
                        if archivo.name.lower().endswith('.csv') or es_sips_excel(archivo):
                            sips_pricing_detectado = _leer_sips_pricing(
                                archivo.name, archivo.getvalue()
                            )
                    if sips_pricing_detectado is not None:
                        atr_sips_pricing = sips_pricing_detectado.get('atr')
                except Exception as error:
                    error_sips_pricing = str(error)
            if (
                not usar_curva_pricing
                and sips_pricing_detectado is None
                and st.session_state.get('df_consumos_pricing_origen') == 'sips'
            ):
                atr_sips_pricing = (
                    st.session_state.get('sips_pricing') or {}
                ).get('atr')
            atr_pricing_pendiente = st.session_state.pop(
                '_pendiente_pricing_atr_seleccionado', None
            )
            if atr_pricing_pendiente in {'2.0', '3.0', '6.1', '6.2'}:
                st.session_state.pricing_atr_seleccionado = atr_pricing_pendiente

            if usar_curva_pricing:
                st.session_state.pricing_atr_seleccionado = atr_curva_pricing
            elif atr_sips_pricing in {'2.0', '3.0', '6.1', '6.2'}:
                st.session_state.pricing_atr_seleccionado = atr_sips_pricing

            sips_sin_atr_pricing = (
                not usar_curva_pricing
                and (
                    sips_pricing_detectado is not None
                    or st.session_state.get('df_consumos_pricing_origen') == 'sips'
                )
                and atr_sips_pricing is None
                and (
                    sips_pricing_detectado is not None
                    or st.session_state.get('sips_pricing', {}).get('atr') is None
                )
            )
            tabla_sips_atr_pricing = (
                sips_pricing_detectado['consumos']
                if sips_pricing_detectado is not None
                else st.session_state.get('df_consumos_pricing')
            )
            sips_con_seis_periodos_pricing = (
                sips_sin_atr_pricing
                and isinstance(tabla_sips_atr_pricing, pd.DataFrame)
                and all(
                    periodo in tabla_sips_atr_pricing.columns
                    for periodo in ('P4', 'P5', 'P6')
                )
                and tabla_sips_atr_pricing[['P4', 'P5', 'P6']]
                .apply(pd.to_numeric, errors='coerce')
                .fillna(0).ne(0).any().any()
            )
            opciones_atr_pricing = (
                ['3.0', '6.1', '6.2']
                if sips_con_seis_periodos_pricing
                else ['2.0', '3.0', '6.1', '6.2']
            )
            if st.session_state.get('pricing_atr_seleccionado') not in [
                None, *opciones_atr_pricing
            ]:
                st.session_state.pop('pricing_atr_manual_confirmado_sips', None)
                st.session_state.pop('pricing_atr_seleccionado', None)
            if (
                sips_sin_atr_pricing
                and not st.session_state.get('pricing_atr_manual_confirmado_sips')
            ):
                st.session_state.pop('pricing_atr_seleccionado', None)

            atr_pricing_seleccionado = st.selectbox(
                'ATR para ponderación por consumo',
                options=opciones_atr_pricing,
                format_func=lambda atr: f'{atr}TD',
                key='pricing_atr_seleccionado',
                index=None if sips_sin_atr_pricing else 0,
                placeholder='Selecciona el ATR real del suministro',
                on_change=(
                    _confirmar_atr_pricing_sips if sips_sin_atr_pricing else None
                ),
                disabled=(
                    usar_curva_pricing
                    or atr_sips_pricing in {'2.0', '3.0', '6.1', '6.2'}
                ),
            )
            if (
                sips_pricing_detectado is not None
                or st.session_state.get('df_consumos_pricing_origen') == 'sips'
            ):
                if atr_sips_pricing is None:
                    st.warning(
                        'El SIPS no informa el ATR. Selecciónalo manualmente antes '
                        'de calcular el pricing.'
                    )
                elif atr_sips_pricing not in {'2.0', '3.0', '6.1', '6.2'}:
                    st.error(
                        f'El SIPS informa {atr_sips_pricing}TD, pero Pricing solo '
                        'admite actualmente 2.0TD, 3.0TD, 6.1TD y 6.2TD.'
                    )
                else:
                    st.info(
                        f'ATR {atr_sips_pricing}TD leído del SIPS. El selector '
                        'queda bloqueado.'
                    )

            if usar_curva_pricing:
                try:
                    st.session_state.df_consumos_pricing = (
                        consumos_mensuales_desde_curva_normalizada(
                            df_curva_pricing_actual,
                        )
                    )
                    st.session_state.df_consumos_pricing_origen = 'curva'
                    st.success(
                        'Curva agrupada por meses y periodos: '
                        f'{atr_pricing_seleccionado}TD.'
                    )
                except ValueError as error_consumos_pricing:
                    st.session_state.pop('df_consumos_pricing', None)
                    st.session_state.pop('df_consumos_pricing_origen', None)
                    st.warning(
                        'La curva cargada no es válida para un pricing anual: '
                        f'{error_consumos_pricing}'
                    )
            else:
                if st.session_state.get('df_consumos_pricing_origen') == 'curva':
                    st.session_state.pop('df_consumos_pricing', None)
                    st.session_state.pop('df_consumos_pricing_origen', None)
                archivo_consumos_pricing = st.file_uploader(
                    'Sube uno o varios SIPS (CSV/Excel) o un Excel de consumos',
                    type=['xlsx', 'xls', 'csv'],
                    key='pricing_upload_consumos',
                    on_change=_cambiar_archivo_pricing,
                    accept_multiple_files=True,
                    help=(
                        'Varios archivos deben ser SIPS de CUPS distintos, con el '
                        'mismo ATR y los mismos 12 meses. Se suman P1-P6 por mes.'
                    ),
                )
                if archivo_consumos_pricing:
                    try:
                        if error_sips_pricing:
                            raise ValueError(error_sips_pricing)
                        if sips_pricing_detectado is not None:
                            sips_pricing = sips_pricing_detectado
                            st.session_state.df_consumos_pricing = (
                                sips_pricing['consumos']
                                if len(archivo_consumos_pricing) > 1
                                else perfil_anual_meses_naturales(
                                    sips_pricing['consumos']
                                )
                            )
                            st.session_state.sips_pricing = sips_pricing
                            st.session_state.df_consumos_pricing_origen = 'sips'
                            if len(archivo_consumos_pricing) > 1:
                                st.success(
                                    f'{len(archivo_consumos_pricing)} SIPS agregados '
                                    'por mes y período. Pricing usa el consumo '
                                    'total para calcular el precio común.'
                                )
                            else:
                                st.success(
                                    'SIPS normalizado: activa, reactiva y maxímetros. '
                                    'Pricing usa la lectura más reciente de cada mes natural.'
                                )
                        else:
                            st.session_state.pop('sips_pricing', None)
                            consumos_raw_pricing = pd.read_excel(
                                archivo_consumos_pricing[0]
                            )
                            st.session_state.df_consumos_pricing = (
                                normalizar_tabla_consumos_sips(
                                    consumos_raw_pricing
                                )
                            )
                            st.session_state.df_consumos_pricing_origen = 'excel'
                            st.success(
                                'Consumos normalizados: últimos 12 meses disponibles.'
                            )
                    except Exception as error_consumos_pricing:
                        st.session_state.pop('df_consumos_pricing', None)
                        st.session_state.pop('df_consumos_pricing_origen', None)
                        st.session_state.pop('sips_pricing', None)
                        st.error(f'Error al leer consumos: {error_consumos_pricing}')

            if (
                st.session_state.get('df_consumos_pricing_origen') == 'sips'
                and st.session_state.get('df_consumos_pricing') is not None
            ):
                sips_resumen = st.session_state.get('sips_pricing', {})
                periodos_resumen = [f'P{i}' for i in range(1, 7)]
                filas_resumen = sips_resumen.get('resumen_sips')
                if not filas_resumen:
                    consumos_sips = st.session_state.df_consumos_pricing
                    filas_resumen = [{
                        'CUPS': sips_resumen.get('metadatos', {}).get('cups', 'SIPS'),
                        **{
                            periodo: float(consumos_sips[periodo].sum())
                            for periodo in periodos_resumen
                        },
                    }]
                tabla_resumen_sips = pd.DataFrame(filas_resumen)
                tabla_resumen_sips['Total (kWh)'] = tabla_resumen_sips[
                    periodos_resumen
                ].sum(axis=1)
                if len(tabla_resumen_sips) > 1:
                    totales_sips = tabla_resumen_sips[
                        [*periodos_resumen, 'Total (kWh)']
                    ].sum()
                    tabla_resumen_sips.loc[len(tabla_resumen_sips)] = {
                        'CUPS': 'TOTAL',
                        **totales_sips.to_dict(),
                    }
                st.markdown('#### Resumen de consumos')
                st.dataframe(
                    tabla_resumen_sips.style.format({
                        columna: lambda valor: formato_numero_es(valor, 0)
                        for columna in [*periodos_resumen, 'Total (kWh)']
                    }),
                    hide_index=True,
                    use_container_width=True,
                )

            if st.session_state.get('df_consumos_pricing') is not None:
                df_consumos_pricing_vista = st.session_state.df_consumos_pricing.copy()
                formato_consumos_pricing = {
                    'año': lambda valor: str(int(valor)),
                    'mes': lambda valor: str(int(valor)),
                    **{
                        f'P{i}': lambda valor: formato_numero_es(valor, 0)
                        for i in range(1, 7)
                    },
                }
                st.markdown('#### Desglose de consumos por meses')
                st.dataframe(
                    df_consumos_pricing_vista.style.format(
                        formato_consumos_pricing
                    ).hide(axis='index'),
                    use_container_width=True,
                    height=460,
                )

        with st.expander('Formación del precio'):
            df_spot_periodos = preparar_referencia_pricing(
                st.session_state.df_sheets
            )
            df_spot_periodos['mes_pricing'] = df_spot_periodos['fecha'].dt.to_period('M')

            # Compatibilidad con tablas horarias conservadas en sesión antes de
            # incorporar 6.2TD. Ambas pérdidas comparten el mismo coeficiente K,
            # por lo que la equivalencia por periodo se obtiene con la relación
            # exacta entre los coeficientes BOE de 6.2TD y 6.1TD.
            ratios_perdidas_62_61 = {
                'P1': 0.052 / 0.065,
                'P2': 0.054 / 0.068,
                'P3': 0.049 / 0.065,
                'P4': 0.050 / 0.065,
                'P5': 0.035 / 0.043,
                'P6': 0.054 / 0.077,
            }
            perdidas_61_compat = pd.to_numeric(
                df_spot_periodos['perd_6.1'], errors='coerce'
            )
            perdidas_62_compat = pd.to_numeric(
                df_spot_periodos.get(
                    'perd_6.2', pd.Series(index=df_spot_periodos.index, dtype=float)
                ),
                errors='coerce',
            )
            perdidas_62_calculadas = perdidas_61_compat * (
                df_spot_periodos['dh_6p'].map(ratios_perdidas_62_61)
            )
            df_spot_periodos['perd_6.2'] = perdidas_62_compat.fillna(
                perdidas_62_calculadas
            )

            periodos_3p_pricing = ['P1', 'P2', 'P3']
            tabla_spot_3p = df_spot_periodos.pivot_table(
                index='mes_pricing',
                columns='dh_3p',
                values='spot',
                aggfunc='mean',
            ).reindex(columns=periodos_3p_pricing)
            tabla_spot_3p['Media mes'] = df_spot_periodos.groupby(
                'mes_pricing'
            )['spot'].mean()
            tabla_spot_3p.index = tabla_spot_3p.index.strftime('%Y-%m')
            tabla_spot_3p.index.name = 'Mes'

            st.markdown('#### SPOT medio por periodo · 2.0TD (3P)')
            st.dataframe(
                tabla_spot_3p.style.format(
                    lambda valor: formato_numero_es(valor, 2) if pd.notna(valor) else '-'
                ),
                use_container_width=True,
                height=460,
            )

            media_spot_12m = df_spot_periodos['spot'].mean()
            st.markdown(
                f"**Media horaria del SPOT en los 12 meses: "
                f":orange[{formato_numero_es(media_spot_12m, 2)} €/MWh]**"
            )
            tabla_apuntamientos_spot_3p = tabla_spot_3p[periodos_3p_pricing].div(
                tabla_spot_3p['Media mes'], axis=0
            )
            tabla_apuntamientos_spot_3p['Media mes'] = 1.0
            st.markdown('#### Apuntamiento SPOT por periodo · 2.0TD (3P)')
            st.dataframe(
                tabla_apuntamientos_spot_3p.style.format(
                    lambda valor: formato_numero_es(valor, 4) if pd.notna(valor) else '-'
                ),
                use_container_width=True,
                height=460,
            )

            tabla_spot_forward_3p = (
                tabla_apuntamientos_spot_3p[periodos_3p_pricing]
                * spot_forward_pricing
            )
            tabla_spot_forward_3p['Media'] = spot_forward_pricing
            st.markdown('#### SPOT forward por periodo · 2.0TD (3P)')
            st.dataframe(
                tabla_spot_forward_3p.style.format(
                    lambda valor: formato_numero_es(valor, 2) if pd.notna(valor) else '-'
                ),
                use_container_width=True,
                height=460,
            )

            df_ssaa_3p = df_spot_periodos.copy()
            df_ssaa_3p['ssaa'] = (
                pd.to_numeric(df_ssaa_3p['ssaa'], errors='coerce')
                - pd.to_numeric(df_ssaa_3p['rad3'], errors='coerce')
            )
            tabla_ssaa_3p = df_ssaa_3p.pivot_table(
                index='mes_pricing',
                columns='dh_3p',
                values='ssaa',
                aggfunc='mean',
            ).reindex(columns=periodos_3p_pricing)
            tabla_ssaa_3p['Media mes'] = df_ssaa_3p.groupby('mes_pricing')['ssaa'].mean()
            tabla_ssaa_3p.index = tabla_ssaa_3p.index.strftime('%Y-%m')
            tabla_ssaa_3p.index.name = 'Mes'

            st.markdown('#### SSAA medios por periodo · 2.0TD (3P)')
            st.dataframe(
                tabla_ssaa_3p.style.format(
                    lambda valor: formato_numero_es(valor, 2) if pd.notna(valor) else '-'
                ),
                use_container_width=True,
                height=460,
            )

            media_ssaa_12m_pricing = df_ssaa_3p['ssaa'].mean()
            st.markdown(
                f"**Media horaria de SSAA en los 12 meses: "
                f":orange[{formato_numero_es(media_ssaa_12m_pricing, 2)} €/MWh]**"
            )
            media_ssaa_3p_no_cero = tabla_ssaa_3p['Media mes'].where(
                tabla_ssaa_3p['Media mes'].ne(0)
            )
            tabla_apuntamientos_ssaa_3p = tabla_ssaa_3p[
                periodos_3p_pricing
            ].div(media_ssaa_3p_no_cero, axis=0)
            tabla_apuntamientos_ssaa_3p['Media mes'] = 1.0
            st.markdown('#### Apuntamiento SSAA por periodo · 2.0TD (3P)')
            st.dataframe(
                tabla_apuntamientos_ssaa_3p.style.format(
                    lambda valor: formato_numero_es(valor, 4) if pd.notna(valor) else '-'
                ),
                use_container_width=True,
                height=460,
            )

            tabla_ssaa_forward_3p = (
                tabla_apuntamientos_ssaa_3p[periodos_3p_pricing]
                * ssaa_forward_pricing
            )
            tabla_ssaa_forward_3p['Media'] = ssaa_forward_pricing
            st.markdown('#### SSAA previstos por periodo · 2.0TD (3P)')
            st.dataframe(
                tabla_ssaa_forward_3p.style.format(
                    lambda valor: formato_numero_es(valor, 2) if pd.notna(valor) else '-'
                ),
                use_container_width=True,
                height=460,
            )

            st.markdown('---')
            st.markdown('#### SPOT medio por periodo · estructura 6P')
            columna_periodo = 'dh_6p'
            tabla_spot_periodos = df_spot_periodos.pivot_table(
                index='mes_pricing',
                columns=columna_periodo,
                values='spot',
                aggfunc='mean',
            )
            tabla_spot_periodos = tabla_spot_periodos.reindex(
                columns=sorted(
                    tabla_spot_periodos.columns,
                    key=lambda periodo: int(str(periodo).replace('P', '')),
                )
            )
            tabla_spot_periodos['Media mes'] = df_spot_periodos.groupby(
                'mes_pricing'
            )['spot'].mean()
            tabla_spot_periodos.index = tabla_spot_periodos.index.strftime('%Y-%m')
            tabla_spot_periodos.index.name = 'Mes'

            st.dataframe(
                tabla_spot_periodos.style.format(
                    lambda valor: formato_numero_es(valor, 2) if pd.notna(valor) else '-'
                ),
                use_container_width=True,
                height=460,
            )

            media_spot_12m = df_spot_periodos['spot'].mean()
            st.markdown(
                f"**Media horaria del SPOT en los 12 meses: "
                f":orange[{formato_numero_es(media_spot_12m, 2)} €/MWh]**"
            )

            st.markdown('#### Apuntamiento SPOT por periodo · 6P')
            columnas_periodo_pricing = [
                columna for columna in tabla_spot_periodos.columns
                if str(columna).startswith('P')
            ]
            tabla_apuntamientos = tabla_spot_periodos[columnas_periodo_pricing].div(
                tabla_spot_periodos['Media mes'], axis=0
            )
            tabla_apuntamientos['Media mes'] = 1.0
            tabla_apuntamientos.index.name = 'Mes'

            st.dataframe(
                tabla_apuntamientos.style.format(
                    lambda valor: formato_numero_es(valor, 4) if pd.notna(valor) else '-'
                ),
                use_container_width=True,
                height=460,
            )

            spot_forward_pricing = st.session_state[clave_spot_guardado]

            tabla_spot_forward = (
                tabla_apuntamientos[columnas_periodo_pricing]
                * spot_forward_pricing
            )
            tabla_spot_forward['Media'] = spot_forward_pricing
            tabla_spot_forward.index.name = 'Mes'

            st.markdown('#### SPOT forward por periodo · 6P')
            st.dataframe(
                tabla_spot_forward.style.format(
                    lambda valor: formato_numero_es(valor, 2) if pd.notna(valor) else '-'
                ),
                use_container_width=True,
                height=460,
                hide_index=False,
            )

            st.markdown('#### SSAA medios por periodo · estructura 6P')

            df_ssaa_periodos = df_spot_periodos.copy()
            df_ssaa_periodos['ssaa'] = (
                pd.to_numeric(df_ssaa_periodos['ssaa'], errors='coerce')
                - pd.to_numeric(df_ssaa_periodos['rad3'], errors='coerce')
            )
            df_ssaa_periodos = df_ssaa_periodos.dropna(subset=['ssaa'])

            tabla_ssaa_periodos = df_ssaa_periodos.pivot_table(
                index='mes_pricing',
                columns=columna_periodo,
                values='ssaa',
                aggfunc='mean',
            ).reindex(columns=columnas_periodo_pricing)
            tabla_ssaa_periodos['Media mes'] = df_ssaa_periodos.groupby(
                'mes_pricing'
            )['ssaa'].mean()
            tabla_ssaa_periodos.index = tabla_ssaa_periodos.index.strftime('%Y-%m')
            tabla_ssaa_periodos.index.name = 'Mes'

            st.dataframe(
                tabla_ssaa_periodos.style.format(
                    lambda valor: formato_numero_es(valor, 2) if pd.notna(valor) else '-'
                ),
                use_container_width=True,
                height=460,
            )

            media_ssaa_12m_pricing = df_ssaa_periodos['ssaa'].mean()
            st.markdown(
                f"**Media horaria de SSAA en los 12 meses: "
                f":orange[{formato_numero_es(media_ssaa_12m_pricing, 2)} €/MWh]**"
            )

            st.markdown('#### Apuntamiento SSAA por periodo · 6P')
            media_mensual_ssaa_no_cero = tabla_ssaa_periodos['Media mes'].where(
                tabla_ssaa_periodos['Media mes'].ne(0)
            )
            tabla_apuntamientos_ssaa = tabla_ssaa_periodos[
                columnas_periodo_pricing
            ].div(media_mensual_ssaa_no_cero, axis=0)
            tabla_apuntamientos_ssaa['Media mes'] = 1.0
            tabla_apuntamientos_ssaa.index.name = 'Mes'

            st.dataframe(
                tabla_apuntamientos_ssaa.style.format(
                    lambda valor: formato_numero_es(valor, 4) if pd.notna(valor) else '-'
                ),
                use_container_width=True,
                height=460,
            )

            ssaa_forward_pricing = st.session_state.pricing_ssaa_forward_12m

            tabla_ssaa_forward = (
                tabla_apuntamientos_ssaa[columnas_periodo_pricing]
                * ssaa_forward_pricing
            )
            tabla_ssaa_forward['Media'] = ssaa_forward_pricing
            tabla_ssaa_forward.index.name = 'Mes'

            st.markdown('#### SSAA previstos por periodo · 6P')
            st.dataframe(
                tabla_ssaa_forward.style.format(
                    lambda valor: formato_numero_es(valor, 2) if pd.notna(valor) else '-'
                ),
                use_container_width=True,
                height=460,
                hide_index=False,
            )

            st.markdown('#### PPC por periodo')
            df_ppc_pricing = st.session_state.df_sheets.copy()
            df_ppc_pricing['fecha'] = pd.to_datetime(
                df_ppc_pricing['fecha'], errors='coerce'
            )
            columnas_ppc_pricing = ['ppcc_2.0', 'ppcc_3.0', 'ppcc_6.1', 'ppcc_6.2']
            for columna_ppc_pricing in columnas_ppc_pricing:
                df_ppc_pricing[columna_ppc_pricing] = pd.to_numeric(
                    df_ppc_pricing[columna_ppc_pricing], errors='coerce'
                )
            df_ppc_pricing = df_ppc_pricing.dropna(subset=['fecha']).sort_values('fecha')
            ultimo_año_ppc = int(df_ppc_pricing['fecha'].dt.year.max())
            df_ppc_ultimo_año = df_ppc_pricing[
                df_ppc_pricing['fecha'].dt.year == ultimo_año_ppc
            ]
            configuracion_ppc_pricing = {
                '2.0TD': ('dh_3p', 'ppcc_2.0'),
                '3.0TD': ('dh_6p', 'ppcc_3.0'),
                '6.1TD': ('dh_6p', 'ppcc_6.1'),
                '6.2TD': ('dh_6p', 'ppcc_6.2'),
            }
            tabla_ppc_pricing = pd.DataFrame.from_dict(
                {
                    tarifa: (
                        df_ppc_ultimo_año.dropna(subset=[columna_periodo_ppc, columna_valor_ppc])
                        .groupby(columna_periodo_ppc)[columna_valor_ppc]
                        .last()
                        .reindex([f'P{i}' for i in range(1, 7)])
                        .to_dict()
                    )
                    for tarifa, (
                        columna_periodo_ppc,
                        columna_valor_ppc,
                    ) in configuracion_ppc_pricing.items()
                },
                orient='index',
            ).reindex(columns=[f'P{i}' for i in range(1, 7)])
            tabla_ppc_pricing.index.name = f'ATR · {ultimo_año_ppc}'
            st.dataframe(
                tabla_ppc_pricing.style.format(
                    lambda valor: formato_numero_es(valor, 2) if pd.notna(valor) else '-'
                ),
                use_container_width=True,
            )

            osom_12m_pricing = pd.to_numeric(
                df_spot_periodos['osom'], errors='coerce'
            ).mean()
            st.info(
                'OSOM medio horario de los 12 meses completos: '
                f'**{formato_numero_es(osom_12m_pricing, 2)} €/MWh**.',
                icon='ℹ️',
            )

            configuracion_perdidas_pricing = {
                '2.0': ('dh_3p', ['P1', 'P2', 'P3']),
                '3.0': ('dh_6p', [f'P{i}' for i in range(1, 7)]),
                '6.1': ('dh_6p', [f'P{i}' for i in range(1, 7)]),
                '6.2': ('dh_6p', [f'P{i}' for i in range(1, 7)]),
            }
            for atr_perdidas_pricing, (
                columna_periodo_perdidas,
                periodos_perdidas_pricing,
            ) in configuracion_perdidas_pricing.items():
                columna_perdidas_pricing = f'perd_{atr_perdidas_pricing}'
                df_perdidas_pricing = df_spot_periodos.copy()
                df_perdidas_pricing[columna_perdidas_pricing] = pd.to_numeric(
                    df_perdidas_pricing[columna_perdidas_pricing], errors='coerce'
                )
                tabla_perdidas_pricing = df_perdidas_pricing.pivot_table(
                    index='mes_pricing',
                    columns=columna_periodo_perdidas,
                    values=columna_perdidas_pricing,
                    aggfunc='mean',
                ).reindex(columns=periodos_perdidas_pricing).mul(100)
                tabla_perdidas_pricing.index = (
                    tabla_perdidas_pricing.index.strftime('%Y-%m')
                )
                tabla_perdidas_pricing.index.name = 'Mes'

                st.markdown(
                    f'#### Pérdidas reales mensuales {atr_perdidas_pricing}TD (%)'
                )
                st.dataframe(
                    tabla_perdidas_pricing.style.format(
                        lambda valor: formato_numero_es(valor, 2)
                        if pd.notna(valor) else '-'
                    ),
                    use_container_width=True,
                    height=460,
                )

            st.markdown('#### Peajes y cargos 2026 por periodo')
            periodos_pyc_pricing = [f'P{i}' for i in range(1, 7)]
            tabla_pyc_pricing = pd.DataFrame.from_dict(
                {
                    tarifa: {
                        periodo: (
                            valor * 1000 if valor is not None else float('nan')
                        )
                        for periodo, valor in pyc_2026[tarifa].items()
                    }
                    for tarifa in ['2.0TD', '3.0TD', '6.1TD', '6.2TD']
                },
                orient='index',
            ).reindex(columns=periodos_pyc_pricing)
            tabla_pyc_pricing.index.name = 'ATR'
            st.dataframe(
                tabla_pyc_pricing.style.format(
                    lambda valor: formato_numero_es(valor, 2) if pd.notna(valor) else '-'
                ),
                use_container_width=True,
            )

    with col_pricing2:
        st.subheader(
            'Precios medios SIN PONDERAR',
            help=(
                'Calculados con el mismo motor de fórmula indexada de '
                'Telemindex, perfilando SPOT y SSAA por mes y periodo.'
            ),
            divider='rainbow',
        )
        mes_actual_pricing = pd.Timestamp.today().to_period('M')
        inicio_horizonte_pricing = mes_actual_pricing + 1
        fin_horizonte_pricing = mes_actual_pricing + 12
        st.caption(
            'Unidades: €/kWh · Horizonte previsto: '
            f'M+1 ({inicio_horizonte_pricing.strftime("%m/%Y")}) → '
            f'M+12 ({fin_horizonte_pricing.strftime("%m/%Y")}).'
        )
        contenedor_metricas_pricing = st.container()

        formula_pricing = FormulaIndexada(
            desvios_apant=st.session_state.get('desvios_apant', 0.0),
            margen=st.session_state.get('margen_telemindex', 0.0),
            margen_pos=st.session_state.get('cfg_margen_pos', 'neto'),
            otros_costes=st.session_state.get('otros_costes_indexado', 0.0),
            otros_costes_pos=st.session_state.get('cfg_otros_costes_pos', 'neto'),
            incluir_fnee=st.session_state.get('cfg_fnee', True),
            fnee_pos=st.session_state.get('cfg_fnee_pos', 'perdidas'),
            cf_pct=st.session_state.get('cf_pct', 0.0),
        )
        configuracion_fijos_pricing = {
            '2.0': {
                'etiqueta': '2.0TD',
                'periodos': periodos_3p_pricing,
                'col_periodo': 'dh_3p',
                'spot': tabla_spot_forward_3p,
                'ssaa': tabla_ssaa_forward_3p,
            },
            '3.0': {
                'etiqueta': '3.0TD',
                'periodos': [f'P{i}' for i in range(1, 7)],
                'col_periodo': 'dh_6p',
                'spot': tabla_spot_forward,
                'ssaa': tabla_ssaa_forward,
            },
            '6.1': {
                'etiqueta': '6.1TD',
                'periodos': [f'P{i}' for i in range(1, 7)],
                'col_periodo': 'dh_6p',
                'spot': tabla_spot_forward,
                'ssaa': tabla_ssaa_forward,
            },
            '6.2': {
                'etiqueta': '6.2TD',
                'periodos': [f'P{i}' for i in range(1, 7)],
                'col_periodo': 'dh_6p',
                'spot': tabla_spot_forward,
                'ssaa': tabla_ssaa_forward,
            },
        }

        resumen_anual_pricing = []
        tablas_fijas_pricing = {}
        for atr_fijo, config_fijo in configuracion_fijos_pricing.items():
            perdidas_mensuales_fijo = (
                df_spot_periodos.groupby(
                    ['mes_pricing', config_fijo['col_periodo']]
                )[f'perd_{atr_fijo}'].mean()
            )
            horas_mensuales_fijo = df_spot_periodos.groupby(
                ['mes_pricing', config_fijo['col_periodo']]
            ).size()
            filas_fijo = []
            for mes_fijo in config_fijo['spot'].index:
                periodo_mes_fijo = pd.Period(mes_fijo, freq='M')
                for periodo_fijo in config_fijo['periodos']:
                    clave_perdidas_fijo = (periodo_mes_fijo, periodo_fijo)
                    spot_periodo_fijo = config_fijo['spot'].loc[
                        mes_fijo, periodo_fijo
                    ]
                    ssaa_periodo_fijo = config_fijo['ssaa'].loc[
                        mes_fijo, periodo_fijo
                    ]
                    if (
                        pd.isna(spot_periodo_fijo)
                        or pd.isna(ssaa_periodo_fijo)
                        or clave_perdidas_fijo not in perdidas_mensuales_fijo.index
                    ):
                        continue

                    fila_fijo = {
                        'Mes': mes_fijo,
                        'Periodo': periodo_fijo,
                        'Horas': horas_mensuales_fijo.loc[clave_perdidas_fijo],
                        'spot': spot_periodo_fijo,
                        'ssaa': ssaa_periodo_fijo + srad_pricing,
                        'osom': osom_12m_pricing,
                        'fnee': fnee_pricing,
                        'ppcc_2.0': 0.0,
                        'ppcc_3.0': 0.0,
                        'ppcc_6.1': 0.0,
                        'ppcc_6.2': 0.0,
                        'perd_2.0': 0.0,
                        'perd_3.0': 0.0,
                        'perd_6.1': 0.0,
                        'perd_6.2': 0.0,
                        'pyc_2.0': 0.0,
                        'pyc_3.0': 0.0,
                        'pyc_6.1': 0.0,
                        'pyc_6.2': 0.0,
                    }
                    fila_fijo[f'ppcc_{atr_fijo}'] = tabla_ppc_pricing.loc[
                        config_fijo['etiqueta'], periodo_fijo
                    ]
                    fila_fijo[f'perd_{atr_fijo}'] = perdidas_mensuales_fijo.loc[
                        clave_perdidas_fijo
                    ]
                    fila_fijo[f'pyc_{atr_fijo}'] = tabla_pyc_pricing.loc[
                        config_fijo['etiqueta'], periodo_fijo
                    ]
                    filas_fijo.append(fila_fijo)

            df_fijo_pricing = calcular_precios_atr_formula(
                pd.DataFrame(filas_fijo), formula_pricing
            )
            precio_anual_ponderado = (
                df_fijo_pricing[f'precio_{atr_fijo}']
                .mul(df_fijo_pricing['Horas'])
                .sum()
                / df_fijo_pricing['Horas'].sum()
            ) / 1000
            precios_anuales_por_periodo = (
                df_fijo_pricing.assign(
                    precio_x_hora=(
                        df_fijo_pricing[f'precio_{atr_fijo}']
                        * df_fijo_pricing['Horas']
                    )
                )
                .groupby('Periodo')
                .apply(
                    lambda grupo: grupo['precio_x_hora'].sum()
                    / grupo['Horas'].sum()
                )
                / 1000
            )
            fila_resumen_anual = {
                periodo: precios_anuales_por_periodo.get(periodo, float('nan'))
                for periodo in [f'P{i}' for i in range(1, 7)]
            }
            fila_resumen_anual['Precio medio anual'] = precio_anual_ponderado
            fila_resumen_anual['ATR'] = config_fijo['etiqueta']
            resumen_anual_pricing.append(fila_resumen_anual)
            precios_mensuales_ponderados = (
                df_fijo_pricing.assign(
                    precio_x_hora=(
                        df_fijo_pricing[f'precio_{atr_fijo}']
                        * df_fijo_pricing['Horas']
                    )
                )
                .groupby('Mes')
                .apply(
                    lambda grupo: grupo['precio_x_hora'].sum()
                    / grupo['Horas'].sum()
                )
                / 1000
            )
            tabla_fijo_pricing = df_fijo_pricing.pivot(
                index='Mes', columns='Periodo', values=f'precio_{atr_fijo}'
            ).reindex(columns=config_fijo['periodos']).div(1000)
            tabla_fijo_pricing['Precio medio mes'] = precios_mensuales_ponderados
            tabla_fijo_pricing.index.name = 'Mes'
            tablas_fijas_pricing[atr_fijo] = tabla_fijo_pricing.copy()

            tabla_resumen_atr_pricing = pd.DataFrame(
                [{
                    periodo: fila_resumen_anual[periodo]
                    for periodo in config_fijo['periodos']
                } | {'Precio medio anual': precio_anual_ponderado}],
                index=['Anual ponderado'],
            ).reindex(
                columns=[*config_fijo['periodos'], 'Precio medio anual']
            )
            with st.expander(
                f"Precio fijo {config_fijo['etiqueta']} (€/kWh)"
            ):
                st.markdown(
                    '**Precio anual ponderado: '
                    f':orange[{formato_numero_es(precio_anual_ponderado, 6)} €/kWh]**'
                )
                st.dataframe(
                    tabla_resumen_atr_pricing.style.format(
                        lambda valor: formato_numero_es(valor, 6)
                        if pd.notna(valor) else '-'
                    ),
                    use_container_width=True,
                )
                st.dataframe(
                    tabla_fijo_pricing.style.format(
                        lambda valor: formato_numero_es(valor, 6)
                        if pd.notna(valor) else '-'
                    ),
                    use_container_width=True,
                    height=460,
                )

        tabla_resumen_anual_pricing = pd.DataFrame(
            resumen_anual_pricing
        ).set_index('ATR')[['Precio medio anual']]
        with contenedor_metricas_pricing:
            columnas_metricas_pricing = st.columns(3)
            for columna_metrica_pricing, atr_metrica_pricing in zip(
                columnas_metricas_pricing, ['2.0TD', '3.0TD', '6.1TD']
            ):
                with columna_metrica_pricing:
                    valor_metrica_pricing = tabla_resumen_anual_pricing.loc[
                        atr_metrica_pricing, 'Precio medio anual'
                    ]
                    st.metric(
                        atr_metrica_pricing,
                        formato_numero_es(valor_metrica_pricing, 6),
                        help='Precio anual sin ponderación por curva de consumo.',
                    )
        st.markdown('#### Resumen de precios medios anuales (€/kWh)')
        st.dataframe(
            tabla_resumen_anual_pricing.style.format(
                lambda valor: formato_numero_es(valor, 6)
                if pd.notna(valor) else '-'
            ),
            use_container_width=True,
        )

    with col_pricing3:
        st.subheader(
            'Precios medios PONDERADOS AL CONSUMO',
            help=(
                'Calculados con el mismo motor de fórmula indexada de '
                'Telemindex, perfilando SPOT y SSAA por mes y periodo.'
            ),
            divider='rainbow',
        )
        st.caption(
            'Unidades: €/kWh · Horizonte previsto: '
            f'M+1 ({inicio_horizonte_pricing.strftime("%m/%Y")}) → '
            f'M+12 ({fin_horizonte_pricing.strftime("%m/%Y")}).'
        )
        df_consumos_pricing = st.session_state.get('df_consumos_pricing')
        if atr_pricing_seleccionado is None:
            st.info('El SIPS no informa el ATR. Selecciónalo para calcular el pricing.')
        elif df_consumos_pricing is None or df_consumos_pricing.empty:
            columnas_metricas_consumo = st.columns(2)
            precio_sin_ponderar_seleccionado = tabla_resumen_anual_pricing.loc[
                f'{atr_pricing_seleccionado}TD', 'Precio medio anual'
            ]
            with columnas_metricas_consumo[0]:
                st.metric(
                    f'{atr_pricing_seleccionado}TD sin ponderar',
                    formato_numero_es(precio_sin_ponderar_seleccionado, 6),
                )
            with columnas_metricas_consumo[1]:
                st.metric(
                    f'{atr_pricing_seleccionado}TD ponderado',
                    '—',
                )
            st.info(
                'Carga en la primera columna un Excel de consumos o un SIPS '
                'para obtener el pricing ponderado.',
                icon='ℹ️',
            )
        else:
            periodos_atr_seleccionado = (
                ['P1', 'P2', 'P3']
                if atr_pricing_seleccionado == '2.0'
                else [f'P{i}' for i in range(1, 7)]
            )
            resultado_pricing_ponderado = calcular_escenarios_pricing_mensuales(
                st.session_state.df_sheets,
                df_consumos_pricing,
                atr_pricing_seleccionado,
                formula_pricing,
                {'Pricing': spot_forward_pricing},
                ssaa_forward_pricing,
                fnee_pricing,
                srad_pricing,
            )
            precios_pricing = resultado_pricing_ponderado.attrs['precios']
            tabla_precio_seleccionado = precios_pricing.pivot(
                index='Mes', columns='Periodo', values='Precio (€/kWh)'
            ).reindex(columns=periodos_atr_seleccionado)
            nombres_mes_pricing = {
                pd.Period(mes, freq='M').month: mes
                for mes in tabla_precio_seleccionado.index
            }
            detalle_pricing = resultado_pricing_ponderado.attrs['detalle']
            df_ponderacion_pricing = detalle_pricing.rename(columns={
                'Periodo': 'Periodo',
                'Consumo (kWh)': 'Consumo',
                'Precio (€/MWh)': 'Precio',
                'Coste (€)': 'Coste',
            })[['Mes', 'Periodo', 'Precio', 'Consumo', 'Coste']].copy()
            df_ponderacion_pricing['Mes'] = (
                df_ponderacion_pricing['Mes'].map(nombres_mes_pricing)
            )
            df_ponderacion_pricing['Precio'] /= 1000
            df_ponderacion_pricing['Coste'] = (
                df_ponderacion_pricing['Precio']
                * df_ponderacion_pricing['Consumo']
            )
            resumen_periodos_consumo = df_ponderacion_pricing.groupby('Periodo').agg(
                Consumo=('Consumo', 'sum'),
                Coste=('Coste', 'sum'),
            )
            precios_periodo_consumo = (
                resumen_periodos_consumo['Coste']
                / resumen_periodos_consumo['Consumo'].where(
                    resumen_periodos_consumo['Consumo'].ne(0)
                )
            )
            precio_anual_consumo = (
                df_ponderacion_pricing['Coste'].sum()
                / df_ponderacion_pricing['Consumo'].sum()
            )
            columnas_metricas_consumo = st.columns(2)
            precio_sin_ponderar_seleccionado = tabla_resumen_anual_pricing.loc[
                f'{atr_pricing_seleccionado}TD', 'Precio medio anual'
            ]
            with columnas_metricas_consumo[0]:
                st.metric(
                    f'{atr_pricing_seleccionado}TD sin ponderar',
                    formato_numero_es(precio_sin_ponderar_seleccionado, 6),
                )
            with columnas_metricas_consumo[1]:
                st.metric(
                    f'{atr_pricing_seleccionado}TD ponderado',
                    formato_numero_es(precio_anual_consumo, 6),
                )
            consumo_anual_total = df_ponderacion_pricing['Consumo'].sum()
            coste_anual_total = df_ponderacion_pricing['Coste'].sum()
            tabla_anual_consumo = pd.DataFrame(
                {
                    periodo: {
                        'Consumo (kWh)': resumen_periodos_consumo['Consumo'].get(
                            periodo, 0.0
                        ),
                        'Coste (€)': resumen_periodos_consumo['Coste'].get(
                            periodo, 0.0
                        ),
                        'Precio medio (€/kWh)': precios_periodo_consumo.get(
                            periodo, float('nan')
                        ),
                    }
                    for periodo in periodos_atr_seleccionado
                }
            )
            tabla_anual_consumo['Total'] = [
                consumo_anual_total,
                coste_anual_total,
                precio_anual_consumo,
            ]
            tabla_anual_consumo_vista = tabla_anual_consumo.copy().astype(object)
            for periodo_resumen in tabla_anual_consumo_vista.columns:
                tabla_anual_consumo_vista.loc['Consumo (kWh)', periodo_resumen] = (
                    formato_numero_es(
                        tabla_anual_consumo.loc['Consumo (kWh)', periodo_resumen], 0
                    )
                )
                tabla_anual_consumo_vista.loc['Coste (€)', periodo_resumen] = (
                    formato_numero_es(
                        tabla_anual_consumo.loc['Coste (€)', periodo_resumen], 2
                    )
                )
                tabla_anual_consumo_vista.loc[
                    'Precio medio (€/kWh)', periodo_resumen
                ] = formato_numero_es(
                    tabla_anual_consumo.loc[
                        'Precio medio (€/kWh)', periodo_resumen
                    ],
                    6,
                )

            resumen_mensual_consumo = df_ponderacion_pricing.groupby('Mes').agg(
                Consumo=('Consumo', 'sum'),
                Coste=('Coste', 'sum'),
            )
            tabla_mensual_consumo = tabla_precio_seleccionado[
                periodos_atr_seleccionado
            ].copy()
            tabla_mensual_consumo['Precio ponderado mes'] = (
                resumen_mensual_consumo['Coste']
                / resumen_mensual_consumo['Consumo'].where(
                    resumen_mensual_consumo['Consumo'].ne(0)
                )
            )
            tabla_mensual_consumo['Consumo mes (kWh)'] = (
                resumen_mensual_consumo['Consumo']
            )

            st.markdown(
                f'#### Resumen anual {atr_pricing_seleccionado}TD'
            )
            st.dataframe(
                tabla_anual_consumo_vista,
                use_container_width=True,
            )
            with st.container(border=True):
                st.markdown('##### Parámetros utilizados')
                st.caption('Escenario')
                st.dataframe(
                    pd.DataFrame([
                        ('SPOT', f'{formato_numero_es(spot_forward_pricing, 2)} €/MWh'),
                        ('SSAA sin SRAD', f'{formato_numero_es(ssaa_forward_pricing, 2)} €/MWh'),
                        ('SRAD', f'{formato_numero_es(srad_pricing, 2)} €/MWh'),
                        ('FNEE previsto', f'{formato_numero_es(fnee_pricing, 2)} €/MWh'),
                    ], columns=['Parámetro', 'Valor']),
                    hide_index=True,
                    use_container_width=True,
                )
                st.caption('Componentes de fórmula')
                st.dataframe(
                    pd.DataFrame([
                        ('Desvíos apantallados', f'{formato_numero_es(formula_pricing.desvios_apant, 2)} €/MWh'),
                        ('Margen', f'{formato_numero_es(formula_pricing.margen, 2)} €/MWh'),
                        ('Ubicación margen', formula_pricing.margen_pos),
                        ('Otros costes', f'{formato_numero_es(formula_pricing.otros_costes, 2)} €/MWh'),
                        ('Ubicación otros costes', formula_pricing.otros_costes_pos),
                        ('Incluye FNEE', 'Sí' if formula_pricing.incluir_fnee else 'No'),
                        ('Ubicación FNEE', formula_pricing.fnee_pos if formula_pricing.incluir_fnee else '—'),
                        ('Coste financiero', f'{formato_numero_es(formula_pricing.cf_pct, 2)} %'),
                    ], columns=['Parámetro', 'Valor']),
                    hide_index=True,
                    use_container_width=True,
                )
            formatos_mensual_consumo = {
                periodo: (lambda valor: formato_numero_es(valor, 6))
                for periodo in periodos_atr_seleccionado
            }
            formatos_mensual_consumo['Precio ponderado mes'] = (
                lambda valor: formato_numero_es(valor, 6)
            )
            formatos_mensual_consumo['Consumo mes (kWh)'] = (
                lambda valor: formato_numero_es(valor, 0)
            )
            with st.expander(f'Detalle mensual {atr_pricing_seleccionado}TD'):
                st.dataframe(
                    tabla_mensual_consumo.style.format(formatos_mensual_consumo),
                    use_container_width=True,
                    height=460,
                )

            tabla_consumos_mensuales = df_ponderacion_pricing.pivot_table(
                index='Mes', columns='Periodo', values='Consumo', aggfunc='sum'
            ).reindex(columns=periodos_atr_seleccionado).fillna(0)
            tabla_consumos_mensuales['Total'] = tabla_consumos_mensuales.sum(axis=1)
            tabla_consumos_mensuales.index.name = 'Mes'

            tabla_costes_mensuales = df_ponderacion_pricing.pivot_table(
                index='Mes', columns='Periodo', values='Coste', aggfunc='sum'
            ).reindex(columns=periodos_atr_seleccionado).fillna(0)
            tabla_costes_mensuales['Total'] = tabla_costes_mensuales.sum(axis=1)
            tabla_costes_mensuales.index.name = 'Mes'

            with st.expander('Consumos mensuales por periodo (kWh)'):
                st.dataframe(
                    tabla_consumos_mensuales.style.format(
                        lambda valor: formato_numero_es(valor, 0)
                    ),
                    use_container_width=True,
                    height=460,
                )
            with st.expander('Costes mensuales por periodo (€)'):
                st.dataframe(
                    tabla_costes_mensuales.style.format(
                        lambda valor: formato_numero_es(valor, 2)
                    ),
                    use_container_width=True,
                    height=460,
                )

# ========================================================================================================================================================================
#PANTALLA PRINCIPAL CON LAS RECTAS DE SIMULACIÓN Y DATOS PARA UN SOLO ESCENARIO OMIE
# ========================================================================================================================================================================
if seccion_simulindex == 'Combo index-fijo':
    st.subheader('Combo index-fijo · precio del volumen fijo', divider='rainbow')
    ruta_cuadrante_combo = (
        Path(__file__).resolve().parent.parent
        / 'assets'
        / 'cuadrante_combo_index_fijo.svg'
    )
    st.info(
        'Ejemplo del tipo de cuadrante horario que podrá introducirse. '
        'Por ahora se utiliza este calendario de muestra; todavía no está '
        'habilitada la carga de imagen ni su lectura con IA.',
        icon='ℹ️',
    )
    st.image(
        str(ruta_cuadrante_combo),
        caption='Cuadrante de muestra · horas Fijo e Indexado por mes',
        width=820,
    )
    st.caption(
        'Se valoran exclusivamente las horas marcadas como Fijo en el '
        'cuadrante. En ellas se sustituye OMIE por el valor indicado y se '
        'aplica la fórmula y los componentes horarios de Telemindex.'
    )
    omie_fijo_combo = st.number_input(
        'OMIE para las casillas Fijo (€/MWh)',
        min_value=0.0,
        value=40.0,
        step=0.5,
        key='combo_omie_fijo',
    )
    df_combo_origen = st.session_state.get('df_curva_sheets')
    atr_combo = str(st.session_state.get('atr_dfnorm', '')).upper().removesuffix('TD')
    if (
        not isinstance(df_combo_origen, pd.DataFrame)
        or df_combo_origen.empty
        or atr_combo not in {'2.0', '3.0', '6.1', '6.2'}
    ):
        st.info('Carga primero una curva de carga en Telemindex/Simulindex.')
    else:
        formula_combo = FormulaIndexada(
            desvios_apant=st.session_state.get('desvios_apant', 0.0),
            margen=st.session_state.get('margen_telemindex', 0.0),
            margen_pos=st.session_state.get('cfg_margen_pos', 'neto'),
            otros_costes=st.session_state.get('otros_costes_indexado', 0.0),
            otros_costes_pos=st.session_state.get('cfg_otros_costes_pos', 'neto'),
            incluir_fnee=st.session_state.get('cfg_fnee', True),
            fnee_pos=st.session_state.get('cfg_fnee_pos', 'perdidas'),
            cf_pct=st.session_state.get('cf_pct', 0.0),
        )
        try:
            detalle_combo, resumen_combo = calcular_combo_index_fijo(
                df_combo_origen,
                atr_combo,
                formula_combo,
                omie_fijo_combo,
            )
            fijo_combo = detalle_combo[detalle_combo['es_fijo']]
            resumen_solo_fijo = resumen_combo
            resumen_combo_completo = resumir_precio_ponderado(
                detalle_combo, atr_combo
            )
            resumen_solo_indexado = resumir_precio_ponderado(
                detalle_combo[~detalle_combo['es_fijo']].copy(), atr_combo
            )
            detalle_indexado = calcular_precios_atr_formula(
                df_combo_origen.copy(), formula_combo
            )
            resumen_todo_indexado = resumir_precio_ponderado(
                detalle_indexado, atr_combo
            )
            consumo_fijo_combo = pd.to_numeric(
                fijo_combo['consumo_neto_kWh'], errors='coerce'
            )
            spot_fijo_combo = pd.to_numeric(
                fijo_combo['spot_original'], errors='coerce'
            )
            mascara_omie_fijo_combo = (
                consumo_fijo_combo.notna()
                & spot_fijo_combo.notna()
                & consumo_fijo_combo.ge(0)
            )
            consumo_omie_fijo_combo = consumo_fijo_combo[
                mascara_omie_fijo_combo
            ].sum()
            omie_apuntado_horas_fijas = (
                spot_fijo_combo[mascara_omie_fijo_combo]
                .mul(consumo_fijo_combo[mascara_omie_fijo_combo])
                .sum()
                / consumo_omie_fijo_combo
                if consumo_omie_fijo_combo > 0 else float('nan')
            )
            fecha_min_combo = detalle_combo['fecha_hora'].min()
            fecha_max_combo = detalle_combo['fecha_hora'].max()
            st.info(
                f'Curva utilizada: {fecha_min_combo:%d/%m/%Y} → '
                f'{fecha_max_combo:%d/%m/%Y} · ATR {atr_combo}TD · '
                f'{formato_numero_es(fijo_combo["consumo_neto_kWh"].sum(), 0)} '
                'kWh incluidos en el bloque fijo.'
            )

            periodos_combo = [f'P{i}' for i in range(1, 7)]
            columnas_combo = st.columns(3)
            escenarios_combo = [
                ('1 · Solo fijo', resumen_solo_fijo),
                ('2 · Combo index + fijo', resumen_combo_completo),
                ('3 · Todo indexado', resumen_todo_indexado),
            ]
            for columna_combo, (
                titulo_combo, resumen_escenario_combo
            ) in zip(columnas_combo, escenarios_combo):
                with columna_combo:
                    st.markdown(f'### {titulo_combo}')
                    precio_total_combo = resumen_escenario_combo.loc[
                        'Total', 'Precio medio (EUR/MWh)'
                    ] / 1000
                    if titulo_combo == '3 · Todo indexado':
                        metricas_omie_combo = st.columns(3)
                        with metricas_omie_combo[0]:
                            st.metric(
                                'Precio ponderado (€/kWh)',
                                formato_numero_es(precio_total_combo, 6),
                            )
                        with metricas_omie_combo[1]:
                            st.metric(
                                'OMIE apuntado horas Fijo (€/MWh)',
                                formato_numero_es(omie_apuntado_horas_fijas, 2),
                            )
                        with metricas_omie_combo[2]:
                            st.metric(
                                'Diferencia vs fijo (€/MWh)',
                                formato_numero_es(
                                    omie_apuntado_horas_fijas - omie_fijo_combo,
                                    2,
                                ),
                            )
                    else:
                        st.metric(
                            'Precio medio ponderado (€/kWh)',
                            formato_numero_es(precio_total_combo, 6),
                        )
                    tabla_precio_combo = (
                        resumen_escenario_combo['Precio medio (EUR/MWh)']
                        .div(1000)
                        .reindex([*periodos_combo, 'Total'])
                        .rename(index={'Total': 'Total ponderado'})
                        .to_frame('Precio (€/kWh)')
                    )
                    st.dataframe(
                        tabla_precio_combo.style.format(
                            lambda valor: formato_numero_es(valor, 6)
                            if pd.notna(valor) else '-'
                        ),
                        use_container_width=True,
                    )
                    tabla_volumen_combo = resumen_escenario_combo[
                        ['Consumo (kWh)', 'Coste (EUR)']
                    ]
                    st.dataframe(
                        tabla_volumen_combo.style.format({
                            'Consumo (kWh)': (
                                lambda valor: formato_numero_es(valor, 0)
                            ),
                            'Coste (EUR)': (
                                lambda valor: formato_numero_es(valor, 2)
                            ),
                        }),
                        use_container_width=True,
                    )
                    if titulo_combo == '2 · Combo index + fijo':
                        for titulo_tramo_combo, resumen_tramo_combo in (
                            ('Volumen Fijo', resumen_solo_fijo),
                            ('Volumen Indexado', resumen_solo_indexado),
                        ):
                            st.markdown(f'#### {titulo_tramo_combo}')
                            tabla_tramo_combo = resumen_tramo_combo[
                                ['Consumo (kWh)', 'Coste (EUR)']
                            ]
                            st.dataframe(
                                tabla_tramo_combo.style.format({
                                    'Consumo (kWh)': (
                                        lambda valor: formato_numero_es(valor, 0)
                                    ),
                                    'Coste (EUR)': (
                                        lambda valor: formato_numero_es(valor, 2)
                                    ),
                                }),
                                use_container_width=True,
                            )
            st.markdown('### Mapa de calor · diferencia Fijo − OMIE real')
            st.caption(
                'Solo se muestran las casillas Fijo. Valores positivos: el '
                'precio OMIE fijo quedó por encima del OMIE real (sobrecoste); '
                'valores negativos: quedó por debajo (ahorro).'
            )
            mapa_combo = fijo_combo.copy()
            mapa_combo['Mes'] = mapa_combo['fecha_hora'].dt.month
            mapa_combo['Hora'] = mapa_combo['hora_entrega']
            mapa_combo['Diferencia'] = (
                omie_fijo_combo
                - pd.to_numeric(mapa_combo['spot_original'], errors='coerce')
            )
            matriz_mapa_combo = mapa_combo.pivot_table(
                index='Hora',
                columns='Mes',
                values='Diferencia',
                aggfunc='mean',
            ).reindex(
                index=range(1, 25),
                columns=range(1, 13),
            )
            meses_mapa_combo = [
                'ene', 'feb', 'mar', 'abr', 'may', 'jun',
                'jul', 'ago', 'sep', 'oct', 'nov', 'dic',
            ]
            limite_mapa_combo = matriz_mapa_combo.abs().max().max()
            if pd.isna(limite_mapa_combo) or limite_mapa_combo == 0:
                limite_mapa_combo = 1.0
            texto_mapa_combo = matriz_mapa_combo.applymap(
                lambda valor: formato_numero_es(valor, 1)
                if pd.notna(valor) else ''
            )
            grafico_mapa_combo = go.Figure(go.Heatmap(
                z=matriz_mapa_combo.values,
                x=meses_mapa_combo,
                y=list(range(1, 25)),
                text=texto_mapa_combo.values,
                texttemplate='%{text}',
                textfont={'size': 10},
                colorscale=[
                    [0.0, '#1a9850'],
                    [0.5, '#fff7bc'],
                    [1.0, '#d73027'],
                ],
                zmin=-limite_mapa_combo,
                zmax=limite_mapa_combo,
                colorbar={'title': 'Fijo − OMIE<br>(€/MWh)'},
                hovertemplate=(
                    'Mes: %{x}<br>Hora: %{y}<br>'
                    'Diferencia: %{z:.2f} €/MWh<extra></extra>'
                ),
                hoverongaps=False,
            ))
            grafico_mapa_combo.update_layout(
                height=650,
                margin={'l': 50, 'r': 80, 't': 25, 'b': 45},
                xaxis_title='Mes',
                yaxis_title='Hora de entrega',
                template='plotly_dark',
            )
            grafico_mapa_combo.update_yaxes(
                autorange='reversed',
                dtick=1,
            )
            st.plotly_chart(grafico_mapa_combo, use_container_width=True)
            st.caption(
                'Fórmula aplicada: [(OMIE fijo + SSAA + PPCC + OSOM + '
                'desvíos + FNEE/margen según configuración) × pérdidas, TM '
                'y coste financiero] + peajes y cargos.'
            )
        except ValueError as error_combo:
            st.error(f'No se ha podido calcular el bloque fijo: {error_combo}')


if seccion_simulindex == 'Principal':
    for clave_principal in (
        'media_ssaa_prev', 'media_fnee_prev', 'media_rad3_prev'
    ):
        st.session_state[f'_widget_{clave_principal}'] = (
            st.session_state[clave_principal]
        )
 
    col1, col2 = st.columns([0.2, 0.8])
    with col1:
        st.info('A partir de :green[OMIE] estimado y opcionalmente :violet[margen] añadido, obtendrás unos precios medios de indexado.', icon = "ℹ️")
        with st.container(border = True):
            st.subheader(':blue-background[Datos de entrada]', divider = 'rainbow')
            col11, col12 = st.columns(2)
            with col11:
                st.metric(':green[OMIE] (€/MWh)', value=formato_eur_mwh(st.session_state.omie_slider, 2, False), help = 'Este es el valor OMIE de referencia que has utilizado como entrada')
            with col12:
                if simulcurva is None:
                    st.metric(':violet[Margen] (€/MWh)', value=formato_eur_mwh(st.session_state.margen_simulindex, 2, False), help = 'Margen que añades para obtener un precio medio final más ajustado a tus necesidades')
                else:
                    st.metric(':violet[Margen] (€/MWh)', value=formato_eur_mwh(margen_simul, 2, False), help = 'Margen añadido en Telemidex para obtener un precio medio final más ajustado a tus necesidades')
        with st.container(border = True):
            st.subheader(':red-background[Ajustes SSAA y OTROS]', divider = 'rainbow')
            col11, col12 = st.columns(2)
            with col11:
                st.metric('SSAA media (€/MWh)', value=formato_eur_mwh(media_ssaa_hist, 2, False), help = 'Este es el valor medio de los SSAA')
 
                st.number_input(
                    'SSAA previsto (€/MWh)', min_value=0.0, max_value=40.0,
                    step=1.0, key='_widget_media_ssaa_prev',
                    on_change=sincronizar_prevision_principal,
                    args=('media_ssaa_prev', 'pricing_ssaa_forward_12m'),
                )
                
                st.metric('Añadir SSAA (€/MWh)', value=formato_eur_mwh(añadir_ssaa, 2, False))
                st.metric('FNEE media (€/MWh)', value=formato_eur_mwh(media_fnee_hist, 2, False), help = 'Este es el valor medio del FNEE')
                
                st.number_input(
                    'FNEE previsto (€/MWh)', min_value=0.0, max_value=4.0,
                    step=.1, key='_widget_media_fnee_prev',
                    on_change=sincronizar_prevision_principal,
                    args=('media_fnee_prev', 'pricing_fnee_prev'),
                )
                
                st.metric('Añadir FNEE (€/MWh)', value=formato_eur_mwh(añadir_fnee, 2, False))
            with col12:
                st.metric('SRAD media (€/MWh)', value=formato_eur_mwh(media_rad3_hist, 2, False), help = 'Este es el valor medio del SRAD')
                
                st.number_input(
                    'SRAD previsto (€/MWh)', min_value=0.0, max_value=3.0,
                    step=0.1, key='_widget_media_rad3_prev',
                    on_change=sincronizar_prevision_principal,
                    args=('media_rad3_prev', 'pricing_srad_prev'),
                )
                
                st.metric('Añadir SRAD (€/MWh)', value=formato_eur_mwh(añadir_rad3, 2, False))

        with st.container(border = True):
            st.subheader(':green-background[Datos de salida]', divider = 'rainbow')
            col13, col14 = st.columns(2)
            with col13:
                st.text('Precios base')
                st.metric(':orange[Precio 2.0] c€/kWh', value=formato_cent_eur_kwh(simul20, 2, False), help = 'Este el precio 2.0 medio simulado a un año vista')
                st.metric(':red[Precio 3.0] c€/kWh', value=formato_cent_eur_kwh(simul30, 2, False), help = 'Este el precio 3.0 medio simulado a un año vista')
                st.metric(':blue[Precio 6.1] c€/kWh', value=formato_cent_eur_kwh(simul61, 2, False), help='Este el precio 6.1 medio simulado a un año vista')
                if 'df_curva_sheets' in st.session_state and st.session_state.df_curva_sheets is not None and simulcurva is not None:
                    st.metric(f':green[Precio CURVA {st.session_state.atr_dfnorm}]  c€/kWh', value=formato_cent_eur_kwh(simulcurva, 2, False), help='Este el precio medio ponderado simulado a un año vista')
            with col14:
                st.text('Precios con margen')
                st.metric(':orange[Precio 2.0] c€/kWh', value=formato_cent_eur_kwh(simul20_margen, 2, False), help = 'Este el precio 2.0 con el margen añadido')
                st.metric(':red[Precio 3.0] c€/kWh', value=formato_cent_eur_kwh(simul30_margen, 2, False), help = 'Este el precio 3.0 con el margen añadido')
                st.metric(':blue[Precio 6.1] c€/kWh', value=formato_cent_eur_kwh(simul61_margen, 2, False), help = 'Este el precio 6.1 con el margen añadido')
                #if 'df_curva_sheets' in st.session_state and st.session_state.df_curva_sheets is not None and simulcurva is not None:
                #    st.metric(f':green[Precio CURVA {st.session_state.atr_dfnorm}]  c€/kWh', value = simulcurva_margen, help='Este el precio medio ponderado con el margen añadido')
    with col2:
        st.info('**¿Cómo funciona?** Los :orange[puntos] son valores de indexado de los 12 últimos meses. Las :orange[líneas] reflejan una tendencia. Los :orange[círculos] simulan los precios medios de indexado a un año vista en base al valor de OMIE estimado.',icon="ℹ️")
        st.plotly_chart(grafico)
        if 'df_curva_sheets' in st.session_state and st.session_state.df_curva_sheets is not None and simulcurva is not None:
            st.write(f'Tabla resumen de datos para el suministro :green[{st.session_state.atr_dfnorm}] con OMIE a :green[{st.session_state.omie_slider}]€/MWh y margen de :green[{st.session_state.margen_simulindex}]€/MWh')
            st.dataframe(df_resumen_simul_view)
                

          
#PANTALLA DE FUTUROS--------------------------------------------------
if seccion_simulindex == 'Futuros':
    
    col3, col4 = st.columns([0.18, 0.82])
    with col3:
        with st.container(border = True):
            st.info('Aquí tienes el valor medio de :blue[OMIP] en €/MWh a partir de los siguientes trimestres, así como la fecha del último registro.', icon = "ℹ️")
            st.subheader('Datos de OMIP', divider = 'rainbow')
            col31, col32 = st.columns(2)
            with col31:
                st.metric('Fecha', value = fecha_ultimo_omip_trimestral)
            with col32:
                st.metric(':blue[OMIP] medio', value = media_omip_trimestral)
    with col4:
        st.info('Aquí tienes la evolución de :blue[OMIP] por trimestres', icon = "ℹ️")
        st.write(graf_omip_trimestral)

    col1, col2 = st.columns([0.18, 0.82])
    with col1:
        st.info(
            f'Evolución de :blue[OMIP] para el mes en curso ({mes_actual})',
            icon="ℹ️",
        )
        if df_FTB_mensual_mes_actual.empty:
            st.warning('No hay cotizaciones OMIP para el mes en curso.')
        else:
            st.write(graf_omip_mensual_mes_actual)
    with col2:
        st.info(
            'Aquí tienes la evolución de :blue[OMIP] por meses desde M+1',
            icon="ℹ️",
        )
        st.write(graf_omip_mensual)
        st.write(graf_omip_anual)

# =======================================================================================================================================================================
# SECCIÓN PREVISIÓN ANUAL
# =======================================================================================================================================================================    
if seccion_simulindex == 'Previsión anual':
    c1, c2 = st.columns(2)
    with c1:
        st.info(f'Aquí tienes la previsión OMIE 2026 en base a los valores medios mensuales :green[OMIE] y los valores medios de :orange[OMIP] a fecha {fecha_ultimo_omip_mensual}.', icon = "ℹ️")
        st.write(graf_2026)
        st.info(f'Aquí tienes la evolución de **:violet[OMIE PREVISTO]** 2026 en base a históricos y futuros combinados, desde el 01.01.2026 hasta el {fecha_ultimo_omip_mensual}.', icon = "ℹ️")
        st.write(fig_media_2026)
    with c2:
        st.info(f'Aquí tienes la previsión :orange[OMIP] 12 MESES en base a los futuros mensuales y trimestrales a fecha {fecha_ultimo_omip_mensual}.', icon = "ℹ️")
        st.write(graf_año_movil)
        st.info(f'Evolución de :orange[OMIP] 12 MESES en base a los futuros mensuales y trimestrales. Comparativa con :green[OMIE]. Última fecha de datos disponible: {fecha_ultimo_omip_mensual}.', icon = "ℹ️")
        st.plotly_chart(fig_media_forward, use_container_width=True)
        st.plotly_chart(fig_omip_suav_vs_omie, use_container_width=True)
        st.plotly_chart(fig_omie_omip_ajuste, use_container_width=True)


# =======================================================================================================================================================================
# OMIP VS OMIE
# =======================================================================================================================================================================
if seccion_simulindex == 'OMIP vs OMIE':
    with st.container():
        col5, col6 = st.columns([0.2, 0.8])
        with col5:
            lista_trimestres_hist = lista_trimestres_hist[::-1]  # invierte la lista
            st.selectbox('Selecciona el trimestre', options=lista_trimestres_hist, key = 'trimestre_cobertura', index=0)
            st.metric('OMIE medio trimestre (€/MWh)', value=media_omie_trimestre if media_omie_trimestre is not None else '—')
        with col6:
            st.plotly_chart(graf_omip_omie_trimestral)
    with st.container():
        col5, col6 = st.columns([0.2, 0.8])
        with col5:
            lista_meses_hist = lista_meses_hist[::-1]  # invierte la lista
            st.selectbox('Selecciona el mes', options=lista_meses_hist, key = 'mes_cobertura', index=0)
        with col6:
            st.plotly_chart(graf_omip_omie_mensual)


# =======================================================================================================================================================================
# SECCIÓN COMPARADOR
# =======================================================================================================================================================================
if seccion_simulindex == 'Comparador':

    curva_comparador_disponible = (
        isinstance(df_curva_pricing_actual, pd.DataFrame)
        and not df_curva_pricing_actual.empty
        and atr_curva_pricing in {'2.0', '3.0', '6.1', '6.2'}
    )
    consumos_pricing_comparador = st.session_state.get('df_consumos_pricing')
    atr_consumos_pricing = atr_pricing_seleccionado
    if st.session_state.get('df_consumos_pricing_origen') == 'sips':
        atr_sips_en_sesion = st.session_state.get('sips_pricing', {}).get('atr')
        if atr_sips_en_sesion in {'2.0', '3.0', '6.1', '6.2'}:
            atr_consumos_pricing = atr_sips_en_sesion
        else:
            if (
                st.session_state.get('simulindex_comparador_atr_sips_manual') is None
                and st.session_state.get('pricing_atr_manual_confirmado_sips')
            ):
                st.session_state.simulindex_comparador_atr_sips_manual = (
                    atr_pricing_seleccionado
                )
            atr_consumos_pricing = st.session_state.get(
                'simulindex_comparador_atr_sips_manual'
            )
    pricing_comparador_disponible = (
        isinstance(consumos_pricing_comparador, pd.DataFrame)
        and not consumos_pricing_comparador.empty
        and 'tablas_fijas_pricing' in locals()
        and atr_consumos_pricing in tablas_fijas_pricing
    )

    opciones_origen_comparador = [
        'Curva de carga',
        'Consumos mensuales / SIPS',
    ]
    origen_comparador_pendiente = st.session_state.pop(
        '_pendiente_origen_consumos_comparador', None
    )
    if origen_comparador_pendiente in opciones_origen_comparador:
        st.session_state.origen_consumos_comparador_simulindex = (
            origen_comparador_pendiente
        )
    origen_guardado_comparador = st.session_state.get(
        'origen_consumos_comparador_simulindex'
    )
    if origen_guardado_comparador not in opciones_origen_comparador:
        st.session_state.origen_consumos_comparador_simulindex = (
            'Consumos mensuales / SIPS'
            if isinstance(consumos_pricing_comparador, pd.DataFrame)
            and not consumos_pricing_comparador.empty
            and not curva_comparador_disponible
            else 'Curva de carga'
        )
    c1, c2, c3 = st.columns(3)

    with c1:
        with st.expander(
            '📈 Curva de carga y origen de consumos',
            expanded=not curva_comparador_disponible,
        ):
            origen_comparador_seleccionado = st.radio(
                'Origen de consumos para la comparación',
                opciones_origen_comparador,
                horizontal=True,
                key='origen_consumos_comparador_simulindex',
            )
            if origen_comparador_seleccionado == 'Curva de carga':
                contenedor_origen_curva_comparador = st.container(
                    border=True
                )
                contenedor_acciones_curva_comparador = st.container(
                    border=True
                )

            if (
                origen_comparador_seleccionado
                == 'Consumos mensuales / SIPS'
            ):
                contenedor_atr_sips_comparador = st.empty()
                archivo_consumos_comparador = st.file_uploader(
                    'Sube un Excel de consumos mensuales o un SIPS (CSV/Excel)',
                    type=['xlsx', 'xls', 'csv'],
                    key='upload_consumos_comparador_simulindex',
                )
                if isinstance(consumos_pricing_comparador, pd.DataFrame):
                    st.caption('Hay consumos cargados. Puedes sustituir el archivo o eliminarlos.')
                    st.button(
                        'Eliminar consumos cargados',
                        key='eliminar_consumos_comparador_simulindex',
                        on_click=_limpiar_consumos_comparador,
                    )

    if origen_comparador_seleccionado == 'Curva de carga':
        estado_normalizacion_comparador = render_origen_curva(
            contenedor_origen_curva_comparador,
            contenedor_acciones_curva_comparador,
            clave='simulindex_comparador_curva',
            titulo_compacto=True,
            mostrar_resumen=False,
        )
        if estado_normalizacion_comparador['normalizacion_solicitada']:
            st.session_state['_comparador_curva_sin_normalizar'] = (
                not estado_normalizacion_comparador['curva_publicada']
            )
            st.session_state['_comparador_curva_version_bloqueada'] = (
                st.session_state.get('curva_reactiva_version')
            )
        if (
            st.session_state.get('_comparador_curva_sin_normalizar', False)
            and st.session_state.get('curva_reactiva_version')
            != st.session_state.get('_comparador_curva_version_bloqueada')
        ):
            st.session_state.pop('_comparador_curva_sin_normalizar', None)
        if st.session_state.get('df_norm_h') is None:
            st.session_state.pop('_comparador_curva_sin_normalizar', None)
        if st.session_state.get('_comparador_curva_sin_normalizar', False):
            c2.error(
                'La nueva curva no se ha normalizado. Se han ocultado los '
                'resultados de la curva anterior.'
            )
            c3.info('Corrige la carga y pulsa «Normalizar curva de carga».')
            st.stop()
        # La curva pudo cambiar dentro del formulario en esta misma ejecución.
        # Volvemos a leerla antes de cualquier cálculo del comparador.
        curva_publicada_comparador = st.session_state.get('df_norm_h')
        if (
            not isinstance(curva_publicada_comparador, pd.DataFrame)
            or curva_publicada_comparador.empty
        ):
            curva_publicada_comparador = st.session_state.get('df_norm')
        df_curva_pricing_actual = curva_publicada_comparador
        atr_publicado_comparador = str(
            st.session_state.get('atr_dfnorm', '')
        ).upper().removesuffix('TD')
        atr_curva_pricing = atr_publicado_comparador
        curva_comparador_disponible = (
            isinstance(curva_publicada_comparador, pd.DataFrame)
            and not curva_publicada_comparador.empty
            and atr_publicado_comparador in {'2.0', '3.0', '6.1', '6.2'}
        )

        curva_graficos_comparador = st.session_state.get('df_norm')
        if (
            not isinstance(curva_graficos_comparador, pd.DataFrame)
            or curva_graficos_comparador.empty
        ):
            curva_graficos_comparador = curva_publicada_comparador
        if (
            isinstance(curva_graficos_comparador, pd.DataFrame)
            and not curva_graficos_comparador.empty
        ):
            with c1:
                with st.expander('Gráficos de consumo', expanded=True):
                    render_resumen_grafico_curva(
                        curva_graficos_comparador,
                        clave='simulindex_comparador_curva',
                    )

    if (
        origen_comparador_seleccionado == 'Curva de carga'
        and not curva_comparador_disponible
    ):
        c2.info(
            'Sube y normaliza una curva para habilitar los escenarios del '
            'comparador.'
        )
        c3.info(
            'La comparación anterior se ha descartado al cambiar el origen '
            'de consumos.'
        )
        st.stop()

    if origen_comparador_seleccionado == 'Consumos mensuales / SIPS':
        firma_archivo_comparador = (
            hashlib.sha256(archivo_consumos_comparador.getvalue()).hexdigest()
            if archivo_consumos_comparador is not None else None
        )
        if (
            firma_archivo_comparador is not None
            and firma_archivo_comparador != st.session_state.get(
                'firma_consumos_comparador_simulindex'
            )
        ):
            try:
                if (
                    archivo_consumos_comparador.name.lower().endswith('.csv')
                    or es_sips_excel(archivo_consumos_comparador)
                ):
                    sips_comparador = leer_sips_completo(
                        archivo_consumos_comparador
                    )
                    atr_sips_comparador = sips_comparador.get('atr')
                    if (
                        atr_sips_comparador is not None
                        and atr_sips_comparador not in {'2.0', '3.0', '6.1', '6.2'}
                    ):
                        raise ValueError(
                            'El SIPS no contiene un ATR compatible '
                            '(2.0TD, 3.0TD, 6.1TD o 6.2TD).'
                        )
                    st.session_state.df_consumos_pricing = (
                        perfil_anual_meses_naturales(
                            sips_comparador['consumos']
                        )
                    )
                    if atr_sips_comparador is not None:
                        st.session_state._pendiente_pricing_atr_seleccionado = (
                            atr_sips_comparador
                        )
                    st.session_state.sips_pricing = sips_comparador
                    st.session_state.df_consumos_pricing_origen = 'sips'
                    st.session_state.pop(
                        'simulindex_comparador_atr_sips_manual', None
                    )
                else:
                    consumos_excel_comparador = pd.read_excel(
                        archivo_consumos_comparador
                    )
                    st.session_state.df_consumos_pricing = (
                        normalizar_tabla_consumos_sips(
                            consumos_excel_comparador
                        )
                    )
                    st.session_state.df_consumos_pricing_origen = 'excel'
                    st.session_state.pop('sips_pricing', None)
                st.session_state.firma_consumos_comparador_simulindex = (
                    firma_archivo_comparador
                )
                st.session_state._limpiar_upload_pricing_por_comparador = True
                st.success(
                    'Consumos cargados. También quedan disponibles en Pricing.'
                )
                st.session_state._pendiente_origen_consumos_comparador = (
                    'Consumos mensuales / SIPS'
                )
                consumos_pricing_comparador = st.session_state.df_consumos_pricing
                if st.session_state.get('df_consumos_pricing_origen') == 'sips':
                    atr_consumos_pricing = st.session_state.sips_pricing.get('atr')
                pricing_comparador_disponible = (
                    isinstance(consumos_pricing_comparador, pd.DataFrame)
                    and not consumos_pricing_comparador.empty
                    and atr_consumos_pricing in tablas_fijas_pricing
                )
            except Exception as error_carga_comparador:
                st.error(f'No se pudieron leer los consumos: {error_carga_comparador}')

        if (
            st.session_state.get('df_consumos_pricing_origen') == 'sips'
            and st.session_state.get('sips_pricing', {}).get('atr') is None
            and isinstance(consumos_pricing_comparador, pd.DataFrame)
        ):
            hay_p4_p6 = bool(
                consumos_pricing_comparador[['P4', 'P5', 'P6']]
                .apply(pd.to_numeric, errors='coerce')
                .fillna(0).ne(0).any().any()
            )
            opciones_atr_sips = (
                ['3.0', '6.1', '6.2'] if hay_p4_p6
                else ['2.0', '3.0', '6.1', '6.2']
            )
            if st.session_state.get(
                'simulindex_comparador_atr_sips_manual'
            ) not in [None, *opciones_atr_sips]:
                st.session_state.pop(
                    'simulindex_comparador_atr_sips_manual', None
                )
            with contenedor_atr_sips_comparador.container():
                atr_consumos_pricing = st.selectbox(
                    'ATR del SIPS (no figura en el archivo)',
                    opciones_atr_sips,
                    index=None,
                    placeholder='Selecciona el peaje real del suministro',
                    format_func=lambda valor: f'{valor}TD',
                    key='simulindex_comparador_atr_sips_manual',
                    on_change=_confirmar_atr_comparador_sips,
                )
            pricing_comparador_disponible = (
                isinstance(consumos_pricing_comparador, pd.DataFrame)
                and not consumos_pricing_comparador.empty
                and atr_consumos_pricing in tablas_fijas_pricing
            )

    if (
        origen_comparador_seleccionado == 'Consumos mensuales / SIPS'
        and not pricing_comparador_disponible
    ):
        sips_sin_atr_comparador = (
            st.session_state.get('df_consumos_pricing_origen') == 'sips'
            and st.session_state.get('sips_pricing', {}).get('atr') is None
            and isinstance(consumos_pricing_comparador, pd.DataFrame)
        )
        if sips_sin_atr_comparador:
            with c2:
                st.subheader('Consumo anual por periodo del SIPS')
                periodos_sips = [f'P{i}' for i in range(1, 7)]
                totales_sips = (
                    consumos_pricing_comparador[periodos_sips]
                    .apply(pd.to_numeric, errors='coerce').sum()
                )
                st.dataframe(
                    formatear_df_resumen(pd.DataFrame(
                        [totales_sips], index=['Consumo (kWh)']
                    )),
                    use_container_width=True,
                )
            with c1:
                st.info('El SIPS no informa el ATR. Selecciona el peaje real para calcular la comparación.')
        else:
            with c1:
                st.info(
                    'Carga los consumos para habilitar los tres escenarios y la '
                    'comparación con ofertas fijas.'
                )
        st.stop()

    usar_pricing_en_comparador = (
        origen_comparador_seleccionado == 'Consumos mensuales / SIPS'
    )
    with c1:
        
        # ----------------------------
        # 5. FORMATO ESPAÑOL (SOLO VISTA)
        # ----------------------------

        if not usar_pricing_en_comparador:
            meses_curva_comparador = pd.to_datetime(
                df_curva_pricing_actual['fecha_hora'], errors='coerce'
            ).dt.to_period('M').nunique()
            try:
                consumos_fuente_comparador = (
                    consumos_mensuales_desde_curva_normalizada(
                        df_curva_pricing_actual,
                    )
                )
            except ValueError as error_curva_comparador:
                st.warning(
                    f'La curva cargada no es válida para una comparación '
                    f'anual: {error_curva_comparador}'
                )
                c2.warning(
                    'Sin resultados: la curva seleccionada no contiene '
                    '12 meses válidos.'
                )
                c3.info(
                    'La comparación anterior se ha descartado al cambiar '
                    'el origen de consumos.'
                )
                st.stop()
            atr_calculo_comparador = atr_curva_pricing
            primer_mes_comparador = consumos_fuente_comparador[
                'periodo_mes'
            ].iloc[0]
            ultimo_mes_comparador = consumos_fuente_comparador[
                'periodo_mes'
            ].iloc[-1]
            st.info(
                f'Curva válida: contiene {meses_curva_comparador} meses. '
                f'Para la comparación anual se utilizan los 12 últimos, '
                f'de {primer_mes_comparador} a {ultimo_mes_comparador}.'
            )
        else:
            consumos_fuente_comparador = consumos_pricing_comparador
            atr_calculo_comparador = atr_consumos_pricing
        anios_consumo_comparador = (
            pd.to_numeric(
                consumos_fuente_comparador.get('año', pd.Series(dtype=float)),
                errors='coerce',
            ).dropna().astype(int).unique().tolist()
        )
        if 'perfil_mercado_comparador_simulindex' not in st.session_state:
            st.session_state.perfil_mercado_comparador_simulindex = (
                '2025 histórico' if anios_consumo_comparador == [2025]
                else 'Últimos 12 meses'
            )
        perfil_mercado_comparador = st.selectbox(
            'Perfil de mercado para la comparación',
            ['Últimos 12 meses', '2025 histórico'],
            key='perfil_mercado_comparador_simulindex',
            help=(
                '2025 histórico usa OMIE, SSAA, pérdidas, PPCC, OSOM y '
                'peajes y cargos de 2025. Conserva los escenarios OMIE, '
                'SSAA y FNEE introducidos.'
            ),
        )
        usar_perfil_2025_comparador = (
            perfil_mercado_comparador == '2025 histórico'
        )
        if usar_perfil_2025_comparador:
            st.caption(
                'Referencia 2025 agregada por mes y periodo. Su resultado '
                'puede diferir del cálculo horario de Telemindex.'
            )
        referencia_comparador = st.session_state.df_sheets
        if usar_perfil_2025_comparador:
            fechas_referencia_comparador = pd.to_datetime(
                referencia_comparador['fecha'], errors='coerce'
            )
            referencia_comparador = referencia_comparador.loc[
                fechas_referencia_comparador.dt.year.eq(2025)
            ].copy()
            meses_referencia_comparador = preparar_referencia_pricing(
                referencia_comparador
            )['fecha'].dt.to_period('M').nunique()
            if meses_referencia_comparador != 12:
                st.error('No hay 12 meses completos de mercado en 2025.')
                st.stop()
        periodos_comparador_pricing = (
            ['P1', 'P2', 'P3']
            if atr_calculo_comparador == '2.0'
            else [f'P{i}' for i in range(1, 7)]
        )
        consumos_comparador = (
            consumos_fuente_comparador[periodos_comparador_pricing]
            .apply(pd.to_numeric, errors='coerce')
            .sum()
            .reindex([f'P{i}' for i in range(1, 7)], fill_value=0.0)
        )
        df_resumen = pd.DataFrame(
            [consumos_comparador], index=['Consumo (kWh)']
        )
        df_consumos = df_resumen.loc[["Consumo (kWh)"]]
        df_consumos_view = formatear_df_resumen(df_consumos)
        # ----------------------------
        # 6. MOSTRAR TABLA
        # ----------------------------
        with st.expander('Escenarios OMIE y otros escenarios'):
            with st.form('form_escenarios_comparador_simulindex'):
                omie_editados = render_escenarios_omie(
                    st.session_state.precio_omip_previsto,
                    'simulindex_escenarios',
                )
                escenarios_aplicados = st.session_state.get(
                    'escenarios_comparador_simulindex'
                )
                otros_editados = render_otros_escenarios(
                    'simulindex_comparador', en_formulario=True,
                    aplicados=(
                        escenarios_aplicados[1]
                        if escenarios_aplicados is not None else None
                    ),
                )
                aplicar_escenarios = st.form_submit_button(
                    'Aplicar escenarios', type='primary',
                    use_container_width=True,
                )
            if (
                aplicar_escenarios
                or 'escenarios_comparador_simulindex' not in st.session_state
            ):
                st.session_state.escenarios_comparador_simulindex = (
                    omie_editados.copy(), otros_editados.copy()
                )
            escenarios_omie_comparador, otros_escenarios_comparador = (
                st.session_state.escenarios_comparador_simulindex
            )
            lista_simul = list(escenarios_omie_comparador.values())
            ssaa_forward_pricing = otros_escenarios_comparador['ssaa']
            srad_pricing = otros_escenarios_comparador['srad']
            fnee_pricing = otros_escenarios_comparador['fnee']

        with st.expander('Fórmula indexada'):
            render_formula_indexada('simulindex_comparador')

        # Entradas de ofertas fijas propias de Simulindex.
        expander_ofertas_fijas = st.expander('Ofertas a precio fijo')
        expander_ofertas_fijas.__enter__()
        if "df_ofertas_fijas_excel_simulindex" not in st.session_state:
            st.session_state.df_ofertas_fijas_excel_simulindex = pd.DataFrame()
        if "df_oferta_fija_manual_simulindex" not in st.session_state:
            st.session_state.df_oferta_fija_manual_simulindex = pd.DataFrame()
        if "df_ofertas_fijas_ia_simulindex" not in st.session_state:
            st.session_state.df_ofertas_fijas_ia_simulindex = pd.DataFrame()

        uploaded_file = st.file_uploader(
            "Sube el Excel con ofertas de precio fijo",
            type=["xlsx", "xls"],
            key="uploaded_ofertas_fijas_simulindex",
        )
        if uploaded_file is not None:
            df_new = normalizar_excel_ofertas(pd.read_excel(uploaded_file))
            df_new.columns = df_new.columns.str.strip()
            col_oferta = df_new.columns[0]
            df_new = df_new.rename(columns={col_oferta: "oferta"})
            periodos = [f"P{i}" for i in range(1, 7)]
            faltan = set(periodos) - set(df_new.columns)
            if faltan:
                st.error(f"Faltan columnas de periodos: {faltan}")
                st.stop()
            for p in periodos:
                df_new[p] = pd.to_numeric(df_new[p], errors="coerce")
            if df_new[periodos].isna().any().any():
                st.error("Hay valores no numéricos en los precios")
                st.stop()
            st.session_state.df_ofertas_fijas_excel_simulindex = df_new.copy()

        atr_comparador = (
            str(
                atr_calculo_comparador
                if usar_pricing_en_comparador
                else atr_curva_pricing
            )
            .replace(" ", "")
            .upper()
        )
        periodos_manuales, periodos_sin_consumo = periodos_con_consumo(
            consumos_comparador, atr_comparador
        )
        if periodos_sin_consumo:
            st.caption(
                "No se exige precio en periodos sin consumo: "
                + ", ".join(periodos_sin_consumo) + "."
            )

        def reactivar_oferta_comparador(nombre_oferta):
            excluidas = set(st.session_state.get(
                '_ofertas_excluidas_comparador_simulindex', []
            ))
            excluidas.discard(str(nombre_oferta).strip().casefold())
            st.session_state[
                '_ofertas_excluidas_comparador_simulindex'
            ] = sorted(excluidas)
            eliminadas = set(st.session_state.get(
                '_ofertas_eliminadas_comparador_simulindex', []
            ))
            eliminadas.discard(str(nombre_oferta).strip().casefold())
            st.session_state[
                '_ofertas_eliminadas_comparador_simulindex'
            ] = sorted(eliminadas)

        try:
            catalogo_ofertas_local = cargar_catalogo_ofertas()
        except ValueError as error_catalogo_ofertas:
            catalogo_ofertas_local = []
            st.warning(str(error_catalogo_ofertas))

        with st.container(border=True):
            st.markdown(
                f"**Ofertas guardadas en local ({len(catalogo_ofertas_local)})**"
            )
            if not catalogo_ofertas_local:
                st.info('Todavía no hay ofertas guardadas.')
            else:
                etiquetas_catalogo = {
                    registro['id']: (
                        f"{registro['nombre']} · "
                        f"{registro['vigencia_desde']} → "
                        f"{registro.get('vigencia_hasta') or 'sin fecha fin'}"
                    )
                    for registro in catalogo_ofertas_local
                }
                id_oferta_local = st.selectbox(
                    'Selecciona una versión',
                    options=list(etiquetas_catalogo),
                    format_func=etiquetas_catalogo.get,
                    key='version_oferta_local_simulindex',
                )
                oferta_local_seleccionada = next(
                    registro for registro in catalogo_ofertas_local
                    if registro['id'] == id_oferta_local
                )
                tarifas_oferta_local = pd.DataFrame(
                    oferta_local_seleccionada.get('tarifas', [])
                ).rename(columns={'atr': 'ATR'})
                st.dataframe(
                    tarifas_oferta_local,
                    hide_index=True,
                    use_container_width=True,
                )
                atr_local_buscado = atr_comparador.removesuffix('TD')
                fila_oferta_local = tarifas_oferta_local[
                    tarifas_oferta_local['ATR'] == atr_local_buscado
                ]
                if fila_oferta_local.empty:
                    st.warning(
                        f'Esta versión no contiene la tarifa {atr_comparador}.'
                    )
                else:
                    fee_oferta_local = st.number_input(
                        'Fee para esta oferta (€/MWh)',
                        min_value=0.0,
                        max_value=100.0,
                        value=0.0,
                        step=0.1,
                        key=f'fee_oferta_local_{id_oferta_local}',
                        help='Se suma a todos los periodos al incorporarla.',
                    )
                if not fila_oferta_local.empty and st.button(
                    f'Usar {atr_comparador} en el comparador',
                    key='usar_oferta_local_simulindex',
                    type='primary',
                    use_container_width=True,
                ):
                    fila_local = fila_oferta_local.iloc[0]
                    nombre_local = oferta_local_seleccionada['nombre']
                    fila_comparador_local = {
                        'oferta': nombre_local,
                        'Fee (€/MWh)': fee_oferta_local,
                        **{
                            periodo: (
                                float(fila_local[periodo])
                                if pd.notna(fila_local.get(periodo)) else 0.0
                            )
                            for periodo in [f'P{i}' for i in range(1, 7)]
                        },
                    }
                    ofertas_locales_comparador = st.session_state.get(
                        'df_ofertas_fijas_ia_simulindex', pd.DataFrame()
                    ).copy()
                    if not ofertas_locales_comparador.empty:
                        mascara_otras_ofertas = (
                            ofertas_locales_comparador['oferta']
                            .astype(str).str.strip().str.casefold()
                            != nombre_local.strip().casefold()
                        )
                        ofertas_locales_comparador = (
                            ofertas_locales_comparador[mascara_otras_ofertas]
                        )
                    st.session_state.df_ofertas_fijas_ia_simulindex = pd.concat(
                        [
                            ofertas_locales_comparador,
                            pd.DataFrame([fila_comparador_local]),
                        ],
                        ignore_index=True,
                    )
                    st.session_state.revision_ofertas_ia_simulindex = (
                        st.session_state.get(
                            'revision_ofertas_ia_simulindex', 0
                        ) + 1
                    )
                    reactivar_oferta_comparador(nombre_local)
                    st.success(f'«{nombre_local}» añadida al comparador.')

        oferta_ia_nueva = render_oferta_ia(
            atr_comparador, periodos_manuales,
            "oferta_ia_simulindex",
            en_expander=False,
        )
        if not oferta_ia_nueva.empty:
            oferta_ia_nueva = oferta_ia_nueva.copy()
            oferta_ia_nueva["Fee (€/MWh)"] = 0.0
            st.session_state.df_ofertas_fijas_ia_simulindex = combinar_ofertas(
                st.session_state.get(
                    "df_ofertas_fijas_ia_simulindex", pd.DataFrame()
                ),
                oferta_ia_nueva,
            )
            st.session_state.revision_ofertas_ia_simulindex = (
                st.session_state.get(
                    "revision_ofertas_ia_simulindex", 0
                ) + 1
            )
            for nombre_oferta_ia in oferta_ia_nueva["oferta"]:
                reactivar_oferta_comparador(nombre_oferta_ia)

        ofertas_ia_actuales = st.session_state.get(
            "df_ofertas_fijas_ia_simulindex", pd.DataFrame()
        )
        if not ofertas_ia_actuales.empty:
            if "Fee (€/MWh)" not in ofertas_ia_actuales.columns:
                ofertas_ia_actuales = ofertas_ia_actuales.copy()
                ofertas_ia_actuales["Fee (€/MWh)"] = 0.0
                st.session_state.df_ofertas_fijas_ia_simulindex = (
                    ofertas_ia_actuales
                )
            st.markdown("**Ofertas incorporadas con IA**")
            revision_ofertas_ia = st.session_state.get(
                "revision_ofertas_ia_simulindex", 0
            )
            ofertas_ia_editadas = st.data_editor(
                ofertas_ia_actuales,
                hide_index=True,
                num_rows="fixed",
                disabled=[f"P{i}" for i in range(1, 7)],
                key=f"nombres_ofertas_ia_simulindex_{revision_ofertas_ia}",
                column_config={
                    "oferta": st.column_config.TextColumn(
                        "Nombre de la oferta", required=True
                    ),
                    "Fee (€/MWh)": st.column_config.NumberColumn(
                        "Fee (€/MWh)",
                        min_value=0.0,
                        max_value=100.0,
                        step=0.1,
                        format="%.2f",
                        help=(
                            "Se suma a todos los periodos de esta oferta."
                        ),
                    ),
                },
            )
            nombres_ia_limpios = (
                ofertas_ia_editadas["oferta"].astype(str).str.strip()
            )
            if (
                nombres_ia_limpios.ne("").all()
                and not nombres_ia_limpios.str.casefold().duplicated().any()
            ):
                ofertas_ia_editadas = ofertas_ia_editadas.copy()
                ofertas_ia_editadas["oferta"] = nombres_ia_limpios
                st.session_state.df_ofertas_fijas_ia_simulindex = (
                    ofertas_ia_editadas
                )
            else:
                st.warning(
                    "Cada oferta debe tener un nombre distinto y no vacío."
                )
        st.markdown("**Introducción manual de precios fijos (€/kWh)**")
        with st.form("form_oferta_fija_manual_simulindex", clear_on_submit=False):
            nombre_oferta_manual_simul = st.text_input(
                "Nombre de la oferta manual",
                value="Oferta manual",
                key="nombre_oferta_fija_manual_simulindex",
            )
            columnas_manual_simul = st.columns(len(periodos_manuales))
            precios_manual_simul = {}
            for columna_manual, periodo_manual in zip(
                columnas_manual_simul, periodos_manuales
            ):
                with columna_manual:
                    precios_manual_simul[periodo_manual] = st.number_input(
                        periodo_manual,
                        min_value=0.0,
                        max_value=2.0,
                        value=0.0,
                        step=0.001,
                        format="%.6f",
                        key=f"precio_fijo_manual_simulindex_{periodo_manual}",
                        help="Precio fijo en €/kWh.",
                    )
            guardar_manual_simul = st.form_submit_button(
                "Añadir o actualizar oferta manual",
                type="primary",
                use_container_width=True,
            )

        if guardar_manual_simul:
            nombre_manual_limpio = nombre_oferta_manual_simul.strip()
            if not nombre_manual_limpio:
                st.error("Indica un nombre para la oferta manual.")
            elif any(
                precios_manual_simul[p] <= 0 for p in periodos_manuales
            ):
                st.error(
                    "Introduce un precio mayor que cero en todos los periodos con consumo."
                )
            else:
                fila_manual_simul = {"oferta": nombre_manual_limpio}
                fila_manual_simul.update(
                    {f"P{i}": 0.0 for i in range(1, 7)}
                )
                fila_manual_simul.update(precios_manual_simul)
                st.session_state.df_oferta_fija_manual_simulindex = pd.DataFrame(
                    [fila_manual_simul]
                )
                reactivar_oferta_comparador(nombre_manual_limpio)
                st.success(
                    f"Oferta manual «{nombre_manual_limpio}» actualizada."
                )

        expander_ofertas_fijas.__exit__(None, None, None)

    with c2:
        origen_comparador = (
            'consumos mensuales del pricing'
            if usar_pricing_en_comparador else 'curva de carga introducida'
        )
        atr_resultado_comparador = (
            atr_calculo_comparador
        )
        st.subheader('Consumo anual por periodo')
        st.dataframe(
            df_consumos_view,
            use_container_width=True,
        )
        total_consumo_comparador = pd.to_numeric(
            consumos_comparador, errors="coerce"
        ).fillna(0.0).sum()
        st.markdown(
            "Total consumo: "
            f"<span style='color:#ffc107; font-size:1.45rem; "
            f"font-weight:700;'>{formato_numero_es(total_consumo_comparador, 0)} "
            "kWh</span> - Peaje de acceso: "
            f"<span style='color:#ffc107; font-size:1.45rem; "
            f"font-weight:700;'>{atr_resultado_comparador}TD</span>",
            unsafe_allow_html=True,
        )

        # El cotejo histórico conserva el cálculo mensual por periodo del
        # comparador; así se puede medir su error frente a Telemindex.
        pyc_2025_comparador = None
        if usar_perfil_2025_comparador:
            pyc_2025_comparador = obtener_pyc_historico_por_periodo(
                st.session_state.df_sheets, atr_calculo_comparador, 2025
            )
        opciones_perfil_comparador = {
            'perfil_anual': usar_perfil_2025_comparador,
            'ssaa_incluye_srad': (
                usar_perfil_2025_comparador and abs(srad_pricing) < 1e-9
            ),
        }
        resultado_indexados = calcular_escenarios_pricing_mensuales(
            referencia_comparador,
            consumos_fuente_comparador,
            atr_calculo_comparador,
            formula_pricing,
            escenarios_omie_comparador,
            ssaa_forward_pricing,
            fnee_pricing,
            srad_pricing,
            pyc_por_periodo=pyc_2025_comparador,
            **opciones_perfil_comparador,
        )
        try:
            if pyc_2025_comparador is None:
                pyc_2025_comparador = obtener_pyc_historico_por_periodo(
                    st.session_state.df_sheets, atr_calculo_comparador, 2025
                )
        except ValueError as error_pyc_2025:
            st.info(str(error_pyc_2025))
        else:
            resultado_otro_pyc = calcular_escenarios_pricing_mensuales(
                referencia_comparador,
                consumos_fuente_comparador,
                atr_calculo_comparador,
                formula_pricing,
                escenarios_omie_comparador,
                ssaa_forward_pricing,
                fnee_pricing,
                srad_pricing,
                pyc_por_periodo=(
                    None if usar_perfil_2025_comparador
                    else pyc_2025_comparador
                ),
                **opciones_perfil_comparador,
            )
            resultado_pyc_2025 = (
                resultado_indexados if usar_perfil_2025_comparador
                else resultado_otro_pyc
            )
            resultado_pyc_2026 = (
                resultado_otro_pyc if usar_perfil_2025_comparador
                else resultado_indexados
            )
            columnas_comparativa_pyc = [
                'Oferta', 'Coste energía (€)', 'Precio medio energía (€/kWh)'
            ]
            resumen_pyc_2026 = resultado_pyc_2026[
                columnas_comparativa_pyc
            ].copy()
            resumen_pyc_2025 = resultado_pyc_2025[
                columnas_comparativa_pyc
            ].copy()
            # Los resultados completos guardan DataFrames en attrs; Pandas
            # intenta compararlos al concatenar las columnas del merge.
            resumen_pyc_2026.attrs = {}
            resumen_pyc_2025.attrs = {}
            comparativa_pyc = resumen_pyc_2026.merge(
                resumen_pyc_2025,
                on='Oferta', suffixes=(' 2026', ' 2025'),
                validate='one_to_one',
            )
            comparativa_pyc['Diferencia 2025 − 2026 (€)'] = (
                comparativa_pyc['Coste energía (€) 2025']
                - comparativa_pyc['Coste energía (€) 2026']
            )
            st.markdown('#### Efecto de los peajes y cargos 2025')
            st.caption(
                'Mismo consumo, OMIE, SSAA, FNEE y fórmula; solo cambia '
                'el PyC de energía por periodo.'
            )
            st.dataframe(
                comparativa_pyc.style.format({
                    'Coste energía (€) 2026': '{:,.2f}',
                    'Coste energía (€) 2025': '{:,.2f}',
                    'Precio medio energía (€/kWh) 2026': '{:.6f}',
                    'Precio medio energía (€/kWh) 2025': '{:.6f}',
                    'Diferencia 2025 − 2026 (€)': '{:+,.2f}',
                }),
                hide_index=True,
                use_container_width=True,
            )
            st.markdown('#### Medias realmente aplicadas al consumo')
            st.caption(
                'Permite cotejar el perfilado del simulador con el OMIE y '
                'los SSAA ponderados de Telemindex. El cambio de PyC no '
                'altera estas dos medias.'
            )
            st.dataframe(
                resultado_pyc_2025.attrs['componentes_ponderados'].style.format({
                    'OMIE aplicado ponderado (€/MWh)': '{:.2f}',
                    'SSAA aplicados ponderados (€/MWh)': '{:.2f}',
                }),
                hide_index=True,
                use_container_width=True,
            )
        detalle_indexados = resultado_indexados.attrs['detalle']
        escenarios = []
        for nombre_escenario, omie_escenario in escenarios_omie_comparador.items():
            detalle_periodo = (
                detalle_indexados.loc[
                    detalle_indexados['Oferta'].eq(nombre_escenario)
                ]
                .groupby('Periodo')
                .agg(
                    consumo=('Consumo (kWh)', 'sum'),
                    coste=('Coste (€)', 'sum'),
                )
                .reindex([f'P{i}' for i in range(1, 7)], fill_value=0.0)
            )
            detalle_periodo['precio'] = (
                detalle_periodo['coste']
                / detalle_periodo['consumo'].where(
                    detalle_periodo['consumo'].ne(0)
                )
            )
            resumen_escenario = pd.DataFrame(
                [
                    detalle_periodo['consumo'],
                    detalle_periodo['coste'],
                    detalle_periodo['precio'],
                ],
                index=[
                    'Consumo (kWh)', 'Coste (€)',
                    'Precio medio (€/kWh)',
                ],
            )
            consumo_escenario = detalle_periodo['consumo'].sum()
            coste_escenario = detalle_periodo['coste'].sum()
            escenarios.append({
                'label': (
                    f'Indexado simulado {nombre_escenario.removeprefix("Indexado ")} '
                    f'({omie_escenario:.1f} €/MWh)'
                ),
                'simul_curva': (
                    coste_escenario / consumo_escenario * 100
                    if consumo_escenario else 0.0
                ),
                'df_resumen': resumen_escenario,
            })
        # Oferta PP Pass Pool: OMIE mensual rolling por apuntamiento mensual
        # y periodo, más el término B de la oferta (en €/kWh).
        oferta_pass_pool = obtener_oferta_pass_pool('pp-pass-pool-001')
        terminos_b_pass_pool = oferta_pass_pool['terminos_b']
        apuntamientos_pass_pool = (
            tabla_apuntamientos_spot_3p
            if atr_calculo_comparador == '2.0'
            else tabla_apuntamientos
        )[periodos_comparador_pricing].copy()
        fechas_apuntamientos_pp = pd.to_datetime(
            apuntamientos_pass_pool.index.astype(str),
            format='%Y-%m',
            errors='coerce',
        )
        apuntamientos_pass_pool['numero_mes'] = fechas_apuntamientos_pp.month
        apuntamientos_pass_pool = (
            apuntamientos_pass_pool.dropna(subset=['numero_mes'])
            .drop_duplicates('numero_mes', keep='last')
            .set_index('numero_mes')
        )

        curva_omie_pass_pool = prevision_omip_12m['curva_mensual'][
            ['fecha', 'precio']
        ].copy()
        curva_omie_pass_pool['fecha'] = pd.to_datetime(
            curva_omie_pass_pool['fecha'], errors='coerce'
        )
        curva_omie_pass_pool['precio'] = pd.to_numeric(
            curva_omie_pass_pool['precio'], errors='coerce'
        )
        curva_omie_pass_pool = curva_omie_pass_pool.dropna(
            subset=['fecha', 'precio']
        )
        consumos_mensuales_pass_pool = consumos_fuente_comparador.set_index(
            'mes'
        )
        filas_pass_pool = []
        for fila_omie_pp in curva_omie_pass_pool.itertuples(index=False):
            numero_mes_pp = fila_omie_pp.fecha.month
            if (
                numero_mes_pp not in apuntamientos_pass_pool.index
                or numero_mes_pp not in consumos_mensuales_pass_pool.index
            ):
                continue
            consumo_mes_pp = consumos_mensuales_pass_pool.loc[numero_mes_pp]
            for periodo_pp in periodos_comparador_pricing:
                apuntamiento_pp = float(
                    apuntamientos_pass_pool.loc[numero_mes_pp, periodo_pp]
                )
                consumo_pp = float(consumo_mes_pp[periodo_pp])
                precio_pp = (
                    float(fila_omie_pp.precio) * apuntamiento_pp / 1000
                    + terminos_b_pass_pool[periodo_pp]
                )
                filas_pass_pool.append({
                    'Mes': fila_omie_pp.fecha,
                    'Periodo': periodo_pp,
                    'Consumo': consumo_pp,
                    'OMIE (€/MWh)': float(fila_omie_pp.precio),
                    'Apuntamiento': apuntamiento_pp,
                    'B (€/kWh)': terminos_b_pass_pool[periodo_pp],
                    'Precio (€/kWh)': precio_pp,
                    'Coste (€)': consumo_pp * precio_pp,
                })

        detalle_pass_pool = pd.DataFrame(filas_pass_pool)
        coste_pass_pool = detalle_pass_pool['Coste (€)'].sum()
        consumo_pass_pool = detalle_pass_pool['Consumo'].sum()
        precio_medio_pass_pool = (
            coste_pass_pool / consumo_pass_pool
            if consumo_pass_pool else 0.0
        )

        st.subheader('Resultado indexados según escenario')
        for esc in escenarios:
            st.markdown(esc["label"])

            df_vista = esc["df_resumen"].loc[
                ["Coste (€)", "Precio medio (€/kWh)"]
            ]

            st.dataframe(
                formatear_df_resumen(df_vista),
                use_container_width=True
            )    

        st.markdown(
            f"**{oferta_pass_pool['nombre']} · OMIE rolling 12 meses**"
        )
        st.dataframe(
            pd.DataFrame([{
                'Coste anual (€)': coste_pass_pool,
                'Precio medio (€/kWh)': precio_medio_pass_pool,
            }]).style.format({
                'Coste anual (€)': lambda valor: formato_numero_es(valor, 2),
                'Precio medio (€/kWh)': (
                    lambda valor: formato_numero_es(valor, 6)
                ),
            }),
            hide_index=True,
            use_container_width=True,
        )


        ofertas_base_simulindex = []
        ofertas_eliminadas_comparador = set(st.session_state.get(
            '_ofertas_eliminadas_comparador_simulindex', []
        ))
        for clave_ofertas_simulindex in (
            "df_ofertas_fijas_excel_simulindex",
            "df_oferta_fija_manual_simulindex",
            "df_ofertas_fijas_ia_simulindex",
        ):
            ofertas_fuente = st.session_state.get(clave_ofertas_simulindex)
            if isinstance(ofertas_fuente, pd.DataFrame) and not ofertas_fuente.empty:
                if ofertas_eliminadas_comparador:
                    nombres_fuente = (
                        ofertas_fuente['oferta'].astype(str)
                        .str.strip().str.casefold()
                    )
                    ofertas_fuente = ofertas_fuente.loc[
                        ~nombres_fuente.isin(ofertas_eliminadas_comparador)
                    ].copy()
                ofertas_base_simulindex.append(ofertas_fuente)

        if ofertas_base_simulindex:
            df_ofertas_base_simul = pd.concat(
                ofertas_base_simulindex, ignore_index=True
            )
        else:
            df_ofertas_base_simul = pd.DataFrame(
                columns=["oferta", *[f"P{i}" for i in range(1, 7)]]
            )

        ofertas_excluidas_comparador = {
            str(nombre).strip().casefold()
            for nombre in st.session_state.get(
                '_ofertas_excluidas_comparador_simulindex', []
            )
        }
        df_ofertas_calc = df_ofertas_base_simul.copy()
        if not df_ofertas_base_simul.empty:
            st.subheader("Resultado ofertas fijo")
            selector_ofertas_comparador = (
                df_ofertas_base_simul[['oferta']]
                .drop_duplicates(subset=['oferta'])
                .reset_index(drop=True)
            )
            nombres_selector_normalizados = (
                selector_ofertas_comparador['oferta'].astype(str)
                .str.strip().str.casefold()
            )
            selector_ofertas_comparador.insert(
                0,
                'Mostrar',
                ~nombres_selector_normalizados.isin(
                    ofertas_excluidas_comparador
                ),
            )
            firma_selector_ofertas = abs(hash(tuple(
                nombres_selector_normalizados.tolist()
            )))
            selector_ofertas_editado = st.data_editor(
                selector_ofertas_comparador,
                hide_index=True,
                num_rows='fixed',
                disabled=['oferta'],
                use_container_width=True,
                key=f'selector_ofertas_comparador_{firma_selector_ofertas}',
                column_config={
                    'Mostrar': st.column_config.CheckboxColumn(
                        'Mostrar',
                        help='Incluye o excluye la oferta de la comparativa.',
                    ),
                    'oferta': st.column_config.TextColumn('Oferta'),
                },
            )
            nombres_ocultos_comparador = set(
                selector_ofertas_editado.loc[
                    ~selector_ofertas_editado['Mostrar'], 'oferta'
                ].astype(str).str.strip().str.casefold()
            )
            st.session_state[
                '_ofertas_excluidas_comparador_simulindex'
            ] = sorted(nombres_ocultos_comparador)
            df_ofertas_base_simul = df_ofertas_base_simul[
                ~df_ofertas_base_simul['oferta'].astype(str)
                .str.strip().str.casefold().isin(
                    nombres_ocultos_comparador
                )
            ].copy()

            ofertas_a_eliminar = st.multiselect(
                'Eliminar ofertas cargadas',
                options=selector_ofertas_comparador['oferta'].astype(str).tolist(),
                key='eliminar_ofertas_comparador_simulindex_v2',
                placeholder='Selecciona una o varias ofertas',
            )
            if st.button(
                'Eliminar de la comparativa',
                key='confirmar_eliminar_ofertas_comparador_simulindex_v2',
                disabled=not ofertas_a_eliminar,
                use_container_width=True,
            ):
                nombres_eliminados = {
                    str(nombre).strip().casefold()
                    for nombre in ofertas_a_eliminar
                }
                ofertas_eliminadas_comparador.update(nombres_eliminados)
                st.session_state[
                    '_ofertas_eliminadas_comparador_simulindex'
                ] = sorted(ofertas_eliminadas_comparador)
                for clave_fuente_ofertas in (
                    'df_ofertas_fijas_excel_simulindex',
                    'df_oferta_fija_manual_simulindex',
                    'df_ofertas_fijas_ia_simulindex',
                    'df_ofertas_fijas_simul',
                ):
                    fuente_ofertas = st.session_state.get(clave_fuente_ofertas)
                    if (
                        isinstance(fuente_ofertas, pd.DataFrame)
                        and not fuente_ofertas.empty
                        and 'oferta' in fuente_ofertas.columns
                    ):
                        nombres_fuente = (
                            fuente_ofertas['oferta'].astype(str)
                            .str.strip().str.casefold()
                        )
                        st.session_state[clave_fuente_ofertas] = (
                            fuente_ofertas.loc[
                                ~nombres_fuente.isin(nombres_eliminados)
                            ].copy()
                        )
                st.rerun()

            columna_fee_simul = "Fee (€/MWh)"
            if columna_fee_simul not in df_ofertas_base_simul.columns:
                df_ofertas_base_simul[columna_fee_simul] = 0.0
            df_ofertas_base_simul[columna_fee_simul] = pd.to_numeric(
                df_ofertas_base_simul[columna_fee_simul], errors="coerce"
            ).fillna(0.0)
            df_ofertas_calc = df_ofertas_base_simul.copy()
            for periodo_fee_simul in periodos_manuales:
                if periodo_fee_simul in df_ofertas_calc.columns:
                    df_ofertas_calc[periodo_fee_simul] = (
                        df_ofertas_calc[periodo_fee_simul]
                        + df_ofertas_calc[columna_fee_simul] / 1000
                    )

            st.session_state.df_ofertas_fijas_simul = df_ofertas_calc

            df_ofertas_view = formatear_df_resumen(st.session_state.df_ofertas_fijas_simul)
            st.dataframe(
                df_ofertas_view,
                use_container_width=True,
                hide_index=True
            )
        else:
            st.session_state.df_ofertas_fijas_simul = df_ofertas_base_simul.copy()
            st.info("Aún no hay ofertas cargadas en Simulindex.")
                



        with c2:

            periodos = [f"P{i}" for i in range(1, 7)]

            # Consumos por periodo
            consumos = df_resumen.loc["Consumo (kWh)", periodos]

            resultados = []

            # Ofertas fijas
            for _, row in st.session_state.df_ofertas_fijas_simul.iterrows():
                coste_total = (consumos * row[periodos]).sum()
                energia_total = consumos.sum()
                precio_medio = coste_total / energia_total

                resultados.append({
                    "Oferta": row["oferta"],
                    "Tipo": "Fijo",
                    "Coste anual (€)": coste_total,
                    "Precio medio (€/kWh)": precio_medio
                })

            # Indexado
            for esc in escenarios:
                df_res = esc["df_resumen"]

                precios_index = df_res.loc["Precio medio (€/kWh)", periodos]
                coste_index = (consumos * precios_index).sum()
                precio_medio_index = coste_index / consumos.sum()

                resultados.append({
                    "Oferta": esc["label"],
                    "Tipo": "Indexado PT",
                    "Coste anual (€)": coste_index,
                    "Precio medio (€/kWh)": precio_medio_index
                })

            resultados.append({
                "Oferta": oferta_pass_pool["nombre"],
                "Tipo": "Pass Pool",
                "Coste anual (€)": coste_pass_pool,
                "Precio medio (€/kWh)": precio_medio_pass_pool,
            })

            df_resultados = pd.DataFrame(resultados)
            # Ordenar por coste anual (de más barato a más caro)
            df_resultados = df_resultados.sort_values("Coste anual (€)").reset_index(drop=True)

            coste_min = df_resultados["Coste anual (€)"].iloc[0]

            df_resultados["% sobre la más barata"] = (
                (df_resultados["Coste anual (€)"] - coste_min) / coste_min * 100
            )

            df_resultados["Δ vs más barata (€)"] = (
                df_resultados["Coste anual (€)"] - coste_min
            )

            
            
            df_resultados_view = formatear_df_resultados(df_resultados)



        with c3:
            st.subheader("📊 Comparativa TOTALPOWER")
            st.dataframe(df_resultados_view, use_container_width=True, hide_index=True)

            orden_ofertas = df_resultados["Oferta"].tolist()

            fig = px.bar(
                df_resultados,
                x="Oferta",
                y="Coste anual (€)",
                color="Tipo",
                #title="Coste anual por oferta",
                text_auto=".0f",
                category_orders={"Oferta": orden_ofertas}
            )

            fig.update_layout(
                yaxis_title="Coste anual (€)",
                xaxis_title="",
                legend_title="",
                bargap=.4,
                title=dict(
                    text=(
                        f"Coste anual por oferta (€) para peaje "
                        f"{atr_resultado_comparador}"
                    ),
                    x=0.5,
                    xanchor="center"
                )
            )
            fig.update_traces(
                textposition="inside",
                textfont_size=16,
                marker_cornerradius=12,
            )
            fig = aplicar_estilo(fig)
            st.plotly_chart(fig, use_container_width=True)

# =======================================================================================================================================================================
# SECCIÓN COBERTURA TRIMESTRAL
# =======================================================================================================================================================================
if seccion_simulindex == 'Cobertura trimestral':

    c1, c2, c3 = st.columns(3)

    curva_trim_disponible = isinstance(
        st.session_state.get('df_norm_h'), pd.DataFrame
    ) and not st.session_state.df_norm_h.empty
    opciones_origen_trim = ['Curva de carga', 'Consumos mensuales / SIPS']
    st.session_state.setdefault(
        'origen_consumos_cobertura_trim',
        'Curva de carga' if curva_trim_disponible else 'Consumos mensuales / SIPS',
    )
    with c1:
        with st.expander(
            '📈 Curva de carga y origen de consumos',
            expanded=not curva_trim_disponible,
        ):
            origen_consumos_trim = st.radio(
                'Origen de consumos para la cobertura',
                opciones_origen_trim,
                horizontal=True,
                key='origen_consumos_cobertura_trim',
            )
            if origen_consumos_trim == 'Curva de carga':
                contenedor_origen_curva_trim = st.container(border=True)
                contenedor_acciones_curva_trim = st.container(border=True)
            else:
                archivo_consumos_trim = st.file_uploader(
                    'Sube un Excel de consumos mensuales o un SIPS (CSV/Excel)',
                    type=['xlsx', 'xls', 'csv'],
                    key='upload_consumos_cobertura_trim',
                )
                if archivo_consumos_trim is not None:
                    firma_consumos_trim = hashlib.sha256(
                        archivo_consumos_trim.getvalue()
                    ).hexdigest()
                    if firma_consumos_trim != st.session_state.get(
                        'firma_consumos_cobertura_trim'
                    ):
                        try:
                            if (
                                archivo_consumos_trim.name.lower().endswith('.csv')
                                or es_sips_excel(archivo_consumos_trim)
                            ):
                                sips_trim = _leer_sips_pricing(
                                    archivo_consumos_trim.name,
                                    archivo_consumos_trim.getvalue(),
                                )
                                consumos_trim_cargados = perfil_anual_meses_naturales(
                                    sips_trim['consumos']
                                )
                                st.session_state.sips_cobertura_trim = sips_trim
                                st.session_state.atr_cobertura_trim = sips_trim.get('atr')
                            else:
                                consumos_trim_cargados = normalizar_tabla_consumos_sips(
                                    pd.read_excel(archivo_consumos_trim)
                                )
                                st.session_state.pop('sips_cobertura_trim', None)
                                st.session_state.pop('atr_cobertura_trim', None)
                            st.session_state.df_consumos_cobertura_trim = (
                                consumos_trim_cargados
                            )
                            st.session_state.firma_consumos_cobertura_trim = (
                                firma_consumos_trim
                            )
                            st.success('Consumos mensuales cargados correctamente.')
                        except Exception as error_consumos_trim:
                            st.error(
                                f'No se pudieron leer los consumos: '
                                f'{error_consumos_trim}'
                            )
                if isinstance(
                    st.session_state.get('df_consumos_cobertura_trim'),
                    pd.DataFrame,
                ):
                    st.caption(
                        'Hay consumos mensuales cargados. Puedes sustituir el '
                        'archivo o eliminarlos.'
                    )
                    if st.button(
                        'Eliminar consumos cargados',
                        key='eliminar_consumos_cobertura_trim',
                        use_container_width=True,
                    ):
                        for clave_trim in (
                            'df_consumos_cobertura_trim',
                            'sips_cobertura_trim',
                            'atr_cobertura_trim',
                            'firma_consumos_cobertura_trim',
                            'upload_consumos_cobertura_trim',
                        ):
                            st.session_state.pop(clave_trim, None)
                        st.rerun()

    if origen_consumos_trim == 'Curva de carga':
        estado_curva_trim = render_origen_curva(
            contenedor_origen_curva_trim,
            contenedor_acciones_curva_trim,
            clave='simulindex_cobertura_trimestral_curva',
            titulo_compacto=True,
            mostrar_resumen=False,
        )
        if estado_curva_trim['curva_publicada']:
            st.rerun()

    trimestre_num_trim = int(
        st.session_state.trimestre_futuro.split('-')[0].removeprefix('Q')
    )
    meses_trim = range(
        (trimestre_num_trim - 1) * 3 + 1,
        trimestre_num_trim * 3 + 1,
    )
    if origen_consumos_trim == 'Curva de carga':
        df_curva_trim = st.session_state.get('df_curva_sheets')
        if not isinstance(df_curva_trim, pd.DataFrame) or df_curva_trim.empty:
            c2.warning('Introduce y normaliza una curva de carga anual.')
            st.stop()
        fechas_curva_trim = pd.to_datetime(
            df_curva_trim['fecha_hora'], errors='coerce'
        )
        periodos_mes_curva = fechas_curva_trim.dt.to_period('M')
        ultimos_doce_meses_curva = sorted(
            periodos_mes_curva.dropna().unique()
        )[-12:]
        mascara_trim = (
            periodos_mes_curva.isin(ultimos_doce_meses_curva)
            & fechas_curva_trim.dt.month.isin(meses_trim)
        )
        df_uso_trimestral = df_curva_trim.loc[mascara_trim].copy()
        atr_fuente_trim = str(st.session_state.get('atr_dfnorm', ''))
    else:
        consumos_mensuales_trim = st.session_state.get(
            'df_consumos_cobertura_trim'
        )
        if not isinstance(consumos_mensuales_trim, pd.DataFrame) or consumos_mensuales_trim.empty:
            c2.warning('Carga consumos mensuales o un SIPS para continuar.')
            st.stop()
        atr_detectado_trim = st.session_state.get('atr_cobertura_trim')
        opciones_atr_trim = ['2.0', '3.0', '6.1', '6.2']
        if atr_detectado_trim in opciones_atr_trim:
            st.session_state.atr_manual_cobertura_trim = atr_detectado_trim
        with c1:
            atr_fuente_trim = st.selectbox(
                'ATR para ponderación por consumo',
                opciones_atr_trim,
                key='atr_manual_cobertura_trim',
                disabled=atr_detectado_trim in opciones_atr_trim,
                format_func=lambda valor: f'{valor}TD',
            )
        filas_consumo_trim = []
        for _, fila_consumo_trim in consumos_mensuales_trim.iterrows():
            mes_consumo_trim = int(fila_consumo_trim['mes'])
            if mes_consumo_trim not in meses_trim:
                continue
            for periodo_consumo_trim in [f'P{i}' for i in range(1, 7)]:
                consumo_periodo_trim = pd.to_numeric(
                    fila_consumo_trim.get(periodo_consumo_trim), errors='coerce'
                )
                filas_consumo_trim.append({
                    'fecha_hora': pd.Timestamp(2025, mes_consumo_trim, 1),
                    'periodo': periodo_consumo_trim,
                    'consumo_neto_kWh': (
                        0.0 if pd.isna(consumo_periodo_trim)
                        else float(consumo_periodo_trim)
                    ),
                })
        df_uso_trimestral = pd.DataFrame(filas_consumo_trim)

    if set(pd.to_datetime(
        df_uso_trimestral['fecha_hora'], errors='coerce'
    ).dt.month.dropna().unique()) != set(meses_trim):
        st.error(
            'El origen seleccionado no contiene los tres meses naturales '
            'necesarios para el trimestre.'
        )
        st.stop()

    with c1:
        st.subheader(f'Selecciona el trimestre de la cobertura')
        st.selectbox('Selecciona trimestre futuro', options=lista_trimestres_futuros, key='trimestre_futuro')

        precio_trim_sel = df_ultimos_precios_trim.loc[df_ultimos_precios_trim['Entrega'] == st.session_state.trimestre_futuro, 'Precio'].iloc[0]
        precio_trim_sel = float(precio_trim_sel)
        if 'simul_b_trim' in st.session_state:
            st.session_state.simul_b_trim = min(
                max(float(st.session_state.simul_b_trim), 0.0),
                precio_trim_sel,
            )
        if 'simul_c_trim' in st.session_state:
            st.session_state.simul_c_trim = max(
                float(st.session_state.simul_c_trim), precio_trim_sel
            )

        st.write(graf_omip_trimestral_select)

        st.subheader(f'Parametriza escenarios alternativos')
        c11, c12, c13, c14 = st.columns(4)
        with c11:
            st.number_input(
                "Cobertura (%)",
                min_value=0,
                max_value=100,
                value=100,
                step=5,
                key="porcentaje_cobertura_trim",
                disabled=True,
                help="Primera versión: cobertura simplificada del 100 %.",
            )
        with c12:
            #st.number_input("OMIE simulado A (€/MWh)", value=55.0, key = 'simul_a_trim')
            #st.markdown('OMIE simulado A (€/MWh)')

            st.markdown(
                """
                <div style="
                    color:white;
                    font-size:0.9rem;
                    font-weight:600;
                    margin-bottom:5px;
                ">
                Cobertura (€/MWh)
                </div>
                """,
                unsafe_allow_html=True
            )
            #st.text(precio_trim_sel)
            st.markdown(
                f"""
                <div style="
                    background-color:#FF8C00;
                    padding:6px;
                    border-radius:6px;
                    color:white;
                    font-weight:bold;
                    display:inline-block;
                    width:100%
                ">
                    {formato_numero_es(precio_trim_sel, 2)}
                </div>
                """,
                unsafe_allow_html=True
            )
            st.session_state.simul_a_trim = precio_trim_sel
        with c13:
            st.number_input(
                "OMIE previsto inf. (€/MWh)",
                min_value=0.0,
                max_value=precio_trim_sel,
                value=max(0.0, precio_trim_sel - 5.0),
                key='simul_b_trim',
            )
        with c14:
            st.number_input(
                "OMIE previsto sup. (€/MWh)",
                min_value=precio_trim_sel,
                value=precio_trim_sel + 5.0,
                key='simul_c_trim',
            )


        

    with c2:
        # ----------------------------
        # 5. FORMATO ESPAÑOL (SOLO VISTA)
        # ----------------------------

        #df_resumen_view = df_resumen.copy()
        
        periodos_trim = [f"P{i}" for i in range(1, 7)]
        consumo_por_periodo_trim = (
            df_uso_trimestral.groupby("periodo")["consumo_neto_kWh"]
            .sum().reindex(periodos_trim).fillna(0.0)
        )
        consumo_por_periodo_trim["TOTAL"] = consumo_por_periodo_trim.sum()
        df_consumos_trim = pd.DataFrame(
            [consumo_por_periodo_trim], index=["Consumo (kWh)"]
        )
        df_consumos_trim_view = formatear_df_resumen(df_consumos_trim)
        
        # ----------------------------
        # 6. MOSTRAR TABLA DE CONSUMOS
        # ----------------------------
        st.subheader(
            f'Consumos utilizados para peaje :orange[{atr_fuente_trim}]'
        )
        st.dataframe(
            df_consumos_trim_view,
            use_container_width=True
        )
            
        atr_trim = str(atr_fuente_trim).replace(
            " ", ""
        ).upper().removesuffix("TD")
        config_trim = configuracion_fijos_pricing[atr_trim]
        apuntamientos_spot_trim = (
            tabla_apuntamientos_spot_3p
            if atr_trim == "2.0" else tabla_apuntamientos
        )
        try:
            escenario_cobertura_a_trim = construir_escenarios_pricing_trimestral(
                df_uso_trimestral,
                st.session_state.trimestre_futuro,
                [st.session_state.simul_a_trim],
                atr_trim,
                apuntamientos_spot_trim,
                config_trim["ssaa"],
                df_spot_periodos,
                config_trim["col_periodo"],
                tabla_ppc_pricing,
                tabla_pyc_pricing,
                osom_12m_pricing,
                srad_pricing,
                fnee_pricing,
                formula_pricing,
                aplicar_apuntamiento=False,
                etiquetas=["A"],
            )[0]
            escenario_cobertura_a_trim["label"] = (
                "Cobertura "
                f"({st.session_state.simul_a_trim:.1f} €/MWh)"
            )
            resumen_cobertura_a_trim = escenario_cobertura_a_trim["df_resumen"]
            escenarios_trim = construir_escenarios_pricing_trimestral(
                df_uso_trimestral,
                st.session_state.trimestre_futuro,
                [st.session_state.simul_b_trim, st.session_state.simul_c_trim],
                atr_trim,
                apuntamientos_spot_trim,
                config_trim["ssaa"],
                df_spot_periodos,
                config_trim["col_periodo"],
                tabla_ppc_pricing,
                tabla_pyc_pricing,
                osom_12m_pricing,
                srad_pricing,
                fnee_pricing,
                formula_pricing,
                aplicar_apuntamiento=True,
                etiquetas=["B", "C"],
            )
            escenarios_trim[0]["label"] = (
                "OMIE previsto inf. "
                f"({st.session_state.simul_b_trim:.1f} €/MWh)"
            )
            escenarios_trim[1]["label"] = (
                "OMIE previsto sup. "
                f"({st.session_state.simul_c_trim:.1f} €/MWh)"
            )
        except (KeyError, ValueError) as error_pricing_trim:
            st.error(
                "No se pudo calcular la cobertura trimestral con Pricing: "
                f"{error_pricing_trim}"
            )
            st.stop()

        st.subheader('Cobertura frente a exposición al mercado')
        st.caption(
            "Cobertura simplificada del 100 %: se aplica el precio OMIP "
            "plano, sin apuntamiento. Los escenarios OMIE inferior y "
            "superior permanecen expuestos al mercado y sí utilizan "
            "apuntamientos. Todos comparten consumos, SSAA, SRAD, FNEE, "
            "pérdidas y fórmula de Pricing."
        )
        comparacion_a_trim = pd.DataFrame({
            "Cobertura": resumen_cobertura_a_trim.loc[
                "Precio medio (€/kWh)"
            ],
            "OMIE previsto inf.": escenarios_trim[0]["df_resumen"].loc[
                "Precio medio (€/kWh)"
            ],
            "OMIE previsto sup.": escenarios_trim[1]["df_resumen"].loc[
                "Precio medio (€/kWh)"
            ],
        }).T
        comparacion_a_trim["Coste total (€)"] = [
            resumen_cobertura_a_trim.loc["Coste (€)", "TOTAL"],
            escenarios_trim[0]["df_resumen"].loc["Coste (€)", "TOTAL"],
            escenarios_trim[1]["df_resumen"].loc["Coste (€)", "TOTAL"],
        ]
        st.dataframe(
            comparacion_a_trim.style.format({
                **{
                    columna: lambda valor: formato_numero_es(valor, 6)
                    for columna in [f"P{i}" for i in range(1, 7)] + ["TOTAL"]
                },
                "Coste total (€)": lambda valor: formato_numero_es(valor, 2),
            }),
            use_container_width=True,
        )

        with st.expander('Detalles de simulación', expanded=False):
            st.markdown(
                "**Cobertura · "
                f"{formato_numero_es(st.session_state.simul_a_trim, 2)} €/MWh**"
            )
            st.caption(
                "Cobertura simplificada del 100 % del consumo. El componente "
                "de mercado utiliza el precio OMIP plano en todos los periodos, "
                "sin apuntamiento."
            )
            df_vista_cobertura_trim = resumen_cobertura_a_trim.loc[
                ["Coste (€)", "Precio medio (€/kWh)"]
            ]
            st.dataframe(
                formatear_df_resumen(df_vista_cobertura_trim),
                use_container_width=True,
            )

            for esc in escenarios_trim:
                st.markdown(f"**{esc['label']}**")
                df_vista_trim = esc["df_resumen"].loc[
                    ["Coste (€)", "Precio medio (€/kWh)"]
                ]
                st.dataframe(
                    formatear_df_resumen(df_vista_trim),
                    use_container_width=True,
                )

        consumos_trim = df_consumos_trim.loc[
            "Consumo (kWh)", [f"P{i}" for i in range(1, 7)]
        ]
        st.subheader("Ofertas a precio fijo")
        with st.expander("Configurar y seleccionar ofertas", expanded=False):
            st.session_state.df_ofertas_fijas_simul_trim = (
                render_bloque_ofertas_fijas(
                    consumos_trim,
                    atr_trim,
                    "simulindex_trim_fijos",
                    titulo="",
                    producto_entrega=(
                        f"{st.session_state.trimestre_futuro.split('-')[0]}-"
                        f"{2000 + int(st.session_state.trimestre_futuro.split('-')[1])}"
                    ),
                )
            )


        with c2:

            periodos = [f"P{i}" for i in range(1, 7)]

            # Consumos por periodo
            consumos_trim = df_consumos_trim.loc["Consumo (kWh)", periodos]

            resultados_trim = []

            resultados_trim.append({
                "Oferta": (
                    "Cobertura "
                    f"({st.session_state.simul_a_trim:.1f} €/MWh)"
                ),
                "Tipo": "Cobertura",
                "Coste trimestre (€)": resumen_cobertura_a_trim.loc[
                    "Coste (€)", "TOTAL"
                ],
                "Precio medio (€/kWh)": resumen_cobertura_a_trim.loc[
                    "Precio medio (€/kWh)", "TOTAL"
                ],
            })

            # Ofertas fijas
            if not st.session_state.df_ofertas_fijas_simul_trim.empty:
                for _, row in st.session_state.df_ofertas_fijas_simul_trim.iterrows():
                    precios_oferta = precios_energia_oferta(row)
                    coste_total = (consumos_trim * precios_oferta).sum()
                    energia_total = consumos_trim.sum()
                    precio_medio = coste_total / energia_total

                    resultados_trim.append({
                        "Oferta": row["oferta"],
                        "Tipo": "Fijo",
                        "Coste trimestre (€)": coste_total,
                        "Precio medio (€/kWh)": precio_medio
                    })

            # Indexado
            for esc in escenarios_trim:
                df_res = esc["df_resumen" \
                ""]

                precios_index = df_res.loc["Precio medio (€/kWh)", periodos]
                coste_index = (consumos_trim * precios_index).sum()
                precio_medio_index = coste_index / consumos_trim.sum()

                resultados_trim.append({
                    "Oferta": esc["label"],
                    "Tipo": "Indexado",
                    "Coste trimestre (€)": coste_index,
                    "Precio medio (€/kWh)": precio_medio_index
                })

            df_resultados_trim = pd.DataFrame(resultados_trim)
            # Ordenar por coste trimestral (de más barato a más caro)
            df_resultados_trim = df_resultados_trim.sort_values("Coste trimestre (€)").reset_index(drop=True)

            coste_min = df_resultados_trim["Coste trimestre (€)"].iloc[0]

            df_resultados_trim["% sobre la más barata"] = (
                (df_resultados_trim["Coste trimestre (€)"] - coste_min) / coste_min * 100
            )

            df_resultados_trim["Δ vs más barata (€)"] = (
                df_resultados_trim["Coste trimestre (€)"] - coste_min
            )

        with c3:
            st.subheader("📊 Comparativa TOTALPOWER")
            oferta_referencia_trim = st.selectbox(
                "Oferta de referencia",
                options=df_resultados_trim["Oferta"].tolist(),
                key="oferta_referencia_comparativa_trim",
            )
            coste_referencia_trim = df_resultados_trim.loc[
                df_resultados_trim["Oferta"].eq(oferta_referencia_trim),
                "Coste trimestre (€)",
            ].iloc[0]
            df_tabla_resultados_trim = df_resultados_trim.drop(
                columns=["% sobre la más barata", "Δ vs más barata (€)"]
            ).copy()
            df_tabla_resultados_trim["% vs referencia"] = (
                (
                    df_tabla_resultados_trim["Coste trimestre (€)"]
                    - coste_referencia_trim
                )
                / coste_referencia_trim
                * 100
            )
            df_tabla_resultados_trim["Δ vs referencia (€)"] = (
                df_tabla_resultados_trim["Coste trimestre (€)"]
                - coste_referencia_trim
            )
            df_tabla_resultados_trim["_es_referencia"] = (
                df_tabla_resultados_trim["Oferta"].eq(oferta_referencia_trim)
            )
            df_tabla_resultados_trim = (
                df_tabla_resultados_trim.sort_values(
                    ["_es_referencia", "Coste trimestre (€)"],
                    ascending=[False, True],
                )
                .drop(columns="_es_referencia")
                .reset_index(drop=True)
            )
            st.dataframe(
                formatear_df_resultados(df_tabla_resultados_trim),
                use_container_width=True,
                hide_index=True,
            )

            df_grafico_trim = df_resultados_trim.copy()
            df_grafico_trim["Oferta gráfico"] = df_grafico_trim["Oferta"].map(
                lambda nombre: (
                    f"Index Esc. {letra}"
                    if str(nombre).startswith("Indexado simulado ")
                    and (letra := str(nombre).removeprefix(
                        "Indexado simulado "
                    )[:1]) in {"A", "B", "C"}
                    else str(nombre)
                )
            )
            df_grafico_trim["Coste mostrado"] = df_grafico_trim[
                "Coste trimestre (€)"
            ].map(lambda valor: f"{formato_numero_es(valor, 0)} €")
            df_grafico_trim = df_grafico_trim.sort_values(
                "Coste trimestre (€)", ascending=True
            )
            orden_ofertas_trim = df_grafico_trim["Oferta gráfico"].tolist()
            margen_izquierdo_trim = min(
                380,
                max(120, max(map(len, orden_ofertas_trim), default=0) * 7),
            )

            fig = px.bar(
                df_grafico_trim,
                x="Coste trimestre (€)",
                y="Oferta gráfico",
                color="Tipo",
                orientation="h",
                text="Coste mostrado",
                category_orders={"Oferta gráfico": orden_ofertas_trim},
                color_discrete_map={
                    "Indexado": "#00A878",
                    "Fijo": "#1C83E1",
                    "Cobertura": "#E4579A",
                },
            )

            for trace in fig.data:
                color_base = {
                    "Indexado": "#00A878",
                    "Fijo": "#1C83E1",
                    "Cobertura": "#E4579A",
                }.get(trace.name, "#64748B")
                trace.marker.color = [
                    "#FF8C00" if etiqueta == "Index Esc. A" else color_base
                    for etiqueta in trace.y
                ]

            fig.update_layout(
                xaxis_title="Coste trimestre (€)",
                yaxis_title="",
                legend_title="",
                bargap=.4,
                barcornerradius=12,
                separators=",.",
                height=max(430, 38 * len(df_grafico_trim) + 170),
                margin=dict(l=margen_izquierdo_trim, r=95, t=115, b=45),
                legend=dict(
                    orientation="h",
                    x=0.5,
                    xanchor="center",
                    y=1.02,
                    yanchor="bottom",
                ),
                title=dict(
                    text="Coste TRIMESTRAL por oferta (€)",
                    x=0.5,
                    xanchor="center",
                )
            )
            fig.update_traces(
                texttemplate="<b>%{text}</b>",
                textposition="outside",
                textfont_size=16,
                cliponaxis=False,
                marker_cornerradius=12,
            )
            coste_maximo_trim = df_grafico_trim["Coste trimestre (€)"].max()
            if pd.notna(coste_maximo_trim) and coste_maximo_trim > 0:
                fig.update_xaxes(range=[0, float(coste_maximo_trim) * 1.2])
            fig.update_yaxes(automargin=True)
            fig = aplicar_estilo(fig)
            st.plotly_chart(fig, use_container_width=True)

        filas_detalle_informe_trim = []
        for escenario_informe_trim in escenarios_trim:
            precios_informe_trim = escenario_informe_trim["df_resumen"].loc[
                "Precio medio (€/kWh)"
            ]
            filas_detalle_informe_trim.append({
                "Oferta": escenario_informe_trim["label"],
                "Tipo": "Indexado",
                **{
                    periodo_informe_trim: precios_informe_trim.get(
                        periodo_informe_trim, 0.0
                    )
                    for periodo_informe_trim in periodos
                },
                "Precio medio (€/kWh)": precios_informe_trim.get("TOTAL", 0.0),
            })
        precios_cobertura_informe_trim = resumen_cobertura_a_trim.loc[
            "Precio medio (€/kWh)"
        ]
        filas_detalle_informe_trim.append({
            "Oferta": (
                "Cobertura "
                f"({st.session_state.simul_a_trim:.1f} €/MWh)"
            ),
            "Tipo": "Cobertura",
            **{
                periodo_informe_trim: precios_cobertura_informe_trim.get(
                    periodo_informe_trim, 0.0
                )
                for periodo_informe_trim in periodos
            },
            "Precio medio (€/kWh)": precios_cobertura_informe_trim.get(
                "TOTAL", 0.0
            ),
        })
        for _, oferta_informe_trim in (
            st.session_state.df_ofertas_fijas_simul_trim.iterrows()
        ):
            precios_oferta_informe = precios_energia_oferta(
                oferta_informe_trim
            )
            coste_oferta_informe = sum(
                float(consumos_trim[periodo_informe_trim])
                * float(precios_oferta_informe[periodo_informe_trim])
                for periodo_informe_trim in periodos
            )
            filas_detalle_informe_trim.append({
                "Oferta": oferta_informe_trim["oferta"],
                "Tipo": "Fijo",
                **{
                    periodo_informe_trim: precios_oferta_informe[
                        periodo_informe_trim
                    ]
                    for periodo_informe_trim in periodos
                },
                "Precio medio (€/kWh)": (
                    coste_oferta_informe / consumos_trim.sum()
                    if consumos_trim.sum() else 0.0
                ),
            })
        firma_datos_informe_trim = (
            st.session_state.trimestre_futuro,
            st.session_state.get("atr_dfnorm", ""),
            int(pd.util.hash_pandas_object(
                df_resultados_trim, index=True
            ).sum()),
        )
        if (
            st.session_state.get("simulindex_informe_trimestral_firma")
            != firma_datos_informe_trim
        ):
            st.session_state.pop("informe_simulindex_trimestral_html", None)
        st.session_state.simulindex_informe_trimestral_firma = (
            firma_datos_informe_trim
        )
        st.session_state.simulindex_informe_trimestral_datos = {
            "resultados": df_resultados_trim.copy(),
            "detalle_precios": pd.DataFrame(filas_detalle_informe_trim),
            "grafico": fig,
            "trimestre": st.session_state.trimestre_futuro,
            "atr": st.session_state.get("atr_dfnorm", ""),
            "cups": st.session_state.get(
                "cups_curva", st.session_state.get("cups_dfnorm", "")
            ),
        }


if seccion_simulindex == 'Informes':
    st.subheader("Informes", divider="rainbow")
    datos_informe_trimestral = st.session_state.get(
        "simulindex_informe_trimestral_datos"
    )
    if datos_informe_trimestral:
        mostrar_informe_comparador_trimestral(datos_informe_trimestral)
    else:
        st.info(
            "Calcula primero una cobertura trimestral para preparar el informe."
        )
