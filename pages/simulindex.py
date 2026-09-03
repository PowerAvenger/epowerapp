import streamlit as st
import io
from backend_simulindex import (obtener_historicos_meff, obtener_meff_anual, obtener_meff_trimestral, obtener_meff_mensual,
                                pyc_2026,
                                obtener_hist_mensual, obtener_spot_mensual, obtener_spot_diario,
                                obtener_graf_hist, obtener_grafico_omip, obtener_grafico_omip_omie,
                                obtener_trimestres_futuros, construir_escenarios,
                                graficar_2026,
                                construir_curva_omip_mensual_12m, graficar_curva_omip_mensual_12m,
                                construir_media_prevista_2026_diaria, graficar_media_prevista_2026,
                                construir_evolucion_media_omip, añadir_omie_real_12m_posterior, graficar_evolucion_media_omip, añadir_omie_real_12m_alineado_omip,
                                añadir_suavizado_omip_y_diferencial, graficar_omip_suavizado_vs_omie_real, graficar_omip_vs_omie_previsto_ajustado_1y)
from backend_comun import colores_precios, obtener_df_resumen, formatear_df_resumen, formatear_df_resultados, aplicar_estilo
import pandas as pd
import plotly.express as px
from utilidades import (
    generar_menu,
    init_app,
    init_app_index,
    mostrar_parametros_formula_indexado,
    persist_widget,
)
from backend_curvadecarga import graficar_media_horaria, graficar_queso_periodos
from formato_es import formato_cent_eur_kwh, formato_eur_mwh, formato_numero_es
from backend_previsiones import (
    guardar_prevision_omie_en_sesion,
    obtener_prevision_omie_anual,
)
from backend_indexado import FormulaIndexada, calcular_precios_atr_formula
from backend_telemindex import añadir_costes_curva, construir_df_curva_sheets
from backend_opt2 import (
    consumos_mensuales_desde_curva_normalizada,
    normalizar_tabla_consumos_sips,
)
from backend_sips import leer_sips_completo, perfil_anual_meses_naturales
from backend_ia_ofertas import extraer_oferta_imagen
from streamlit_paste_button import paste_image_button

if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')

generar_menu()
init_app()

st.sidebar.header('⚡ Simulación de indexados ⚡')
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
        df_curva_simulindex = df_curva_simulindex.drop_duplicates(
            subset=["fecha", "hora"], keep="first"
        )
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

fecha_ref_prevision_anual = pd.Timestamp.today().normalize()
df_año_movil = construir_curva_omip_mensual_12m(
    df_FTB_mensual,
    df_FTB_trimestral,
    fecha_ref_prevision_anual,
)
precio_medio_omip = round(df_año_movil["precio"].mean(),2)
graf_año_movil = graficar_curva_omip_mensual_12m(df_año_movil, precio_medio_omip)
st.session_state.precio_omip_previsto = precio_medio_omip

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
    fecha_ref=fecha_ref_prevision_anual,
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

# Valor comun para el ultimo punto del grafico suavizado y el SPOT previsto de
# Pricing. Se actualiza al renovar la prevision, salvo si el usuario ha
# sustituido manualmente el anterior valor automatico.
serie_forward_suav = pd.to_numeric(
    df_evol_media_forward_suav['media_forward_12m_suav'], errors='coerce'
).dropna()
spot_forward_suav_default = (
    float(serie_forward_suav.iloc[-1])
    if not serie_forward_suav.empty else float(precio_medio_omip)
)
spot_forward_suav_default = round(spot_forward_suav_default, 2)
spot_forward_auto_anterior = st.session_state.get(
    '_pricing_spot_forward_auto_anterior'
)
spot_forward_actual = st.session_state.get('pricing_spot_forward_12m')
if (
    spot_forward_actual is None
    or float(spot_forward_actual) == 0.0
    or (
        spot_forward_auto_anterior is not None
        and abs(
            float(spot_forward_actual) - float(spot_forward_auto_anterior)
        ) < 1e-9
    )
):
    st.session_state.pricing_spot_forward_12m = spot_forward_suav_default
st.session_state._pricing_spot_forward_auto_anterior = spot_forward_suav_default

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


for clave_pricing, clave_principal in {
    'pricing_ssaa_forward_12m': 'media_ssaa_prev',
    'pricing_fnee_prev': 'media_fnee_prev',
    'pricing_srad_prev': 'media_rad3_prev',
}.items():
    if clave_pricing not in st.session_state:
        st.session_state[clave_pricing] = st.session_state[clave_principal]
    clave_pendiente = f'_pendiente_{clave_pricing}'
    if clave_pendiente in st.session_state:
        st.session_state[clave_pricing] = st.session_state.pop(clave_pendiente)




tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    'Principal',
    'Futuros',
    'Previsión anual',
    'OMIP vs OMIE',
    'Comparador',
    'Cobertura trimestral',
    'Pricing',
])

# =======================================================================================================================================================================
# PRICING
# Se renderiza antes que los tabs que requieren una curva y pueden detener la
# ejecución completa de Streamlit.
# =======================================================================================================================================================================
with tab7:
    col_pricing1, col_pricing2, col_pricing3 = st.columns(3)

    with col_pricing1:
        st.subheader('Parámetros de pricing', divider='rainbow')
        spot_forward_pricing = st.number_input(
            'SPOT previsto (€/MWh)', min_value=0.0, step=0.1,
            key='pricing_spot_forward_12m',
            help=(
                'Parte del último valor de la media OMIP forward 12 meses '
                'suavizada del tab Previsión anual.'
            ),
        )
        ssaa_forward_pricing = st.number_input(
            'SSAA previstos sin SRAD (€/MWh)', min_value=0.0, max_value=40.0,
            step=0.1, key='pricing_ssaa_forward_12m',
            on_change=sincronizar_input_prevision,
            args=('pricing_ssaa_forward_12m', 'media_ssaa_prev'),
        )
        fnee_pricing = st.number_input(
            'FNEE previsto (€/MWh)', min_value=0.0, max_value=4.0,
            step=0.1, key='pricing_fnee_prev',
            on_change=sincronizar_input_prevision,
            args=('pricing_fnee_prev', 'media_fnee_prev'),
        )
        srad_pricing = st.number_input(
            'SRAD previsto (€/MWh)', min_value=0.0, max_value=3.0,
            step=0.1, key='pricing_srad_prev',
            on_change=sincronizar_input_prevision,
            args=('pricing_srad_prev', 'media_rad3_prev'),
        )

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
            and atr_curva_pricing in {'2.0', '3.0', '6.1'}
        )
        opciones_origen_consumos = ['Subir Excel / SIPS']
        if curva_pricing_disponible:
            opciones_origen_consumos.append('Usar curva normalizada')
        origen_consumos_pricing = st.radio(
            'Origen de los consumos',
            options=opciones_origen_consumos,
            horizontal=True,
            key='pricing_origen_consumos',
        )
        usar_curva_pricing = origen_consumos_pricing == 'Usar curva normalizada'
        archivo_pricing_sesion = st.session_state.get('pricing_upload_consumos')
        sips_pricing_detectado = None
        atr_sips_pricing = None
        if (
            not usar_curva_pricing
            and archivo_pricing_sesion is not None
            and archivo_pricing_sesion.name.lower().endswith('.csv')
        ):
            try:
                sips_pricing_detectado = leer_sips_completo(
                    archivo_pricing_sesion
                )
                atr_sips_pricing = sips_pricing_detectado.get('atr')
            except Exception:
                # El bloque de carga inferior muestra el diagnóstico completo.
                pass
        atr_pricing_pendiente = st.session_state.pop(
            '_pendiente_pricing_atr_seleccionado', None
        )
        if atr_pricing_pendiente in {'2.0', '3.0', '6.1'}:
            st.session_state.pricing_atr_seleccionado = atr_pricing_pendiente

        if usar_curva_pricing:
            st.session_state.pricing_atr_seleccionado = atr_curva_pricing
        elif atr_sips_pricing in {'2.0', '3.0', '6.1'}:
            st.session_state.pricing_atr_seleccionado = atr_sips_pricing

        atr_pricing_seleccionado = st.selectbox(
            'ATR para ponderación por consumo',
            options=['2.0', '3.0', '6.1'],
            format_func=lambda atr: f'{atr}TD',
            key='pricing_atr_seleccionado',
            disabled=(
                usar_curva_pricing
                or atr_sips_pricing in {'2.0', '3.0', '6.1'}
            ),
        )
        if sips_pricing_detectado is not None:
            if atr_sips_pricing is None:
                st.warning(
                    'El SIPS no informa el ATR. Selecciónalo manualmente antes '
                    'de calcular el pricing.'
                )
            elif atr_sips_pricing not in {'2.0', '3.0', '6.1'}:
                st.error(
                    f'El SIPS informa {atr_sips_pricing}TD, pero Pricing solo '
                    'admite actualmente 2.0TD, 3.0TD y 6.1TD.'
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
                'Sube Excel de consumos o CSV SIPS',
                type=['xlsx', 'xls', 'csv'],
                key='pricing_upload_consumos',
            )
            if archivo_consumos_pricing is not None:
                try:
                    if archivo_consumos_pricing.name.lower().endswith('.csv'):
                        sips_pricing = (
                            sips_pricing_detectado
                            or leer_sips_completo(archivo_consumos_pricing)
                        )
                        st.session_state.df_consumos_pricing = (
                            perfil_anual_meses_naturales(
                                sips_pricing['consumos']
                            )
                        )
                        st.session_state.sips_pricing = sips_pricing
                        st.session_state.df_consumos_pricing_origen = 'sips'
                        st.success(
                            'SIPS normalizado: activa, reactiva y maxímetros. '
                            'Pricing usa la lectura más reciente de cada mes natural.'
                        )
                    else:
                        st.session_state.pop('sips_pricing', None)
                        consumos_raw_pricing = pd.read_excel(
                            archivo_consumos_pricing
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
                    if sips_pricing_detectado is None:
                        st.session_state.pop('sips_pricing', None)
                    else:
                        st.session_state.sips_pricing = sips_pricing_detectado
                    st.error(f'Error al leer consumos: {error_consumos_pricing}')

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
            st.dataframe(
                df_consumos_pricing_vista.style.format(
                    formato_consumos_pricing
                ).hide(axis='index'),
                use_container_width=True,
                height=460,
            )

        df_spot_periodos = st.session_state.df_sheets.copy()
        df_spot_periodos['fecha'] = pd.to_datetime(
            df_spot_periodos['fecha'], errors='coerce'
        )
        df_spot_periodos['spot'] = pd.to_numeric(
            df_spot_periodos['spot'], errors='coerce'
        )
        df_spot_periodos = df_spot_periodos.dropna(subset=['fecha', 'spot'])
        df_spot_periodos['mes_pricing'] = df_spot_periodos['fecha'].dt.to_period('M')

        def mes_horario_completo(periodo, grupo):
            inicio = periodo.start_time.tz_localize('Europe/Madrid')
            fin = (periodo + 1).start_time.tz_localize('Europe/Madrid')
            horas_esperadas = len(
                pd.date_range(inicio, fin, freq='h', inclusive='left')
            )
            fechas = grupo['fecha']
            return (
                len(grupo) == horas_esperadas
                and fechas.min().date() == periodo.start_time.date()
                and fechas.max().date() == periodo.end_time.date()
            )

        meses_completos = [
            periodo
            for periodo, grupo in df_spot_periodos.groupby('mes_pricing')
            if mes_horario_completo(periodo, grupo)
        ]
        meses_disponibles = sorted(meses_completos)[-12:]
        df_spot_periodos = df_spot_periodos[
            df_spot_periodos['mes_pricing'].isin(meses_disponibles)
        ].copy()

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

        spot_forward_pricing = st.session_state.pricing_spot_forward_12m

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

    with col_pricing1:
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
        columnas_ppc_pricing = ['ppcc_2.0', 'ppcc_3.0', 'ppcc_6.1']
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
                for tarifa in ['2.0TD', '3.0TD', '6.1TD']
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
            margen_pos=st.session_state.get('cfg_margen_pos', 'tm'),
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
                        'perd_2.0': 0.0,
                        'perd_3.0': 0.0,
                        'perd_6.1': 0.0,
                        'pyc_2.0': 0.0,
                        'pyc_3.0': 0.0,
                        'pyc_6.1': 0.0,
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

            st.markdown(f"#### Precio fijo {config_fijo['etiqueta']} (€/kWh)")
            st.markdown(
                '**Precio anual ponderado: '
                f':orange[{formato_numero_es(precio_anual_ponderado, 6)} €/kWh]**'
            )
            tabla_resumen_atr_pricing = pd.DataFrame(
                [{
                    periodo: fila_resumen_anual[periodo]
                    for periodo in config_fijo['periodos']
                } | {'Precio medio anual': precio_anual_ponderado}],
                index=['Anual ponderado'],
            ).reindex(
                columns=[*config_fijo['periodos'], 'Precio medio anual']
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
        if df_consumos_pricing is None or df_consumos_pricing.empty:
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
            tabla_precio_seleccionado = tablas_fijas_pricing[
                atr_pricing_seleccionado
            ]
            periodos_atr_seleccionado = (
                ['P1', 'P2', 'P3']
                if atr_pricing_seleccionado == '2.0'
                else [f'P{i}' for i in range(1, 7)]
            )
            consumos_por_mes_natural = df_consumos_pricing.set_index('mes')
            filas_ponderacion_pricing = []
            for mes_precio_pricing in tabla_precio_seleccionado.index:
                numero_mes_pricing = pd.Period(mes_precio_pricing, freq='M').month
                consumo_mes_pricing = consumos_por_mes_natural.loc[numero_mes_pricing]
                for periodo_pricing in periodos_atr_seleccionado:
                    precio_periodo_pricing = tabla_precio_seleccionado.loc[
                        mes_precio_pricing, periodo_pricing
                    ]
                    consumo_periodo_pricing = pd.to_numeric(
                        consumo_mes_pricing[periodo_pricing], errors='coerce'
                    )
                    if pd.isna(precio_periodo_pricing) or pd.isna(consumo_periodo_pricing):
                        continue
                    filas_ponderacion_pricing.append({
                        'Mes': mes_precio_pricing,
                        'Periodo': periodo_pricing,
                        'Precio': precio_periodo_pricing,
                        'Consumo': float(consumo_periodo_pricing),
                    })

            df_ponderacion_pricing = pd.DataFrame(filas_ponderacion_pricing)
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
            st.markdown(
                f'#### Detalle mensual {atr_pricing_seleccionado}TD'
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

            st.markdown('#### Consumos mensuales por periodo (kWh)')
            st.dataframe(
                tabla_consumos_mensuales.style.format(
                    lambda valor: formato_numero_es(valor, 0)
                ),
                use_container_width=True,
                height=460,
            )
            st.markdown('#### Costes mensuales por periodo (€)')
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
with tab1:
 
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
                    step=1.0, key='media_ssaa_prev',
                    on_change=sincronizar_input_prevision,
                    args=('media_ssaa_prev', 'pricing_ssaa_forward_12m'),
                )
                
                st.metric('Añadir SSAA (€/MWh)', value=formato_eur_mwh(añadir_ssaa, 2, False))
                st.metric('FNEE media (€/MWh)', value=formato_eur_mwh(media_fnee_hist, 2, False), help = 'Este es el valor medio del FNEE')
                
                st.number_input(
                    'FNEE previsto (€/MWh)', min_value=0.0, max_value=4.0,
                    step=.1, key='media_fnee_prev',
                    on_change=sincronizar_input_prevision,
                    args=('media_fnee_prev', 'pricing_fnee_prev'),
                )
                
                st.metric('Añadir FNEE (€/MWh)', value=formato_eur_mwh(añadir_fnee, 2, False))
            with col12:
                st.metric('SRAD media (€/MWh)', value=formato_eur_mwh(media_rad3_hist, 2, False), help = 'Este es el valor medio del SRAD')
                
                st.number_input(
                    'SRAD previsto (€/MWh)', min_value=0.0, max_value=3.0,
                    step=0.1, key='media_rad3_prev',
                    on_change=sincronizar_input_prevision,
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
with tab2:
    
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
        st.info('Aquí tienes la evolución de :blue[OMIP] por meses', icon = "ℹ️")
        st.write(graf_omip_mensual)
        st.write(graf_omip_anual)

# =======================================================================================================================================================================
# SECCIÓN PREVISIÓN ANUAL
# =======================================================================================================================================================================    
with tab3:
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
with tab4:
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
with tab5:

    curva_comparador_disponible = (
        isinstance(df_curva_pricing_actual, pd.DataFrame)
        and not df_curva_pricing_actual.empty
        and atr_curva_pricing in {'2.0', '3.0', '6.1'}
    )
    consumos_pricing_comparador = st.session_state.get('df_consumos_pricing')
    atr_consumos_pricing = atr_pricing_seleccionado
    if st.session_state.get('df_consumos_pricing_origen') == 'sips':
        atr_sips_en_sesion = st.session_state.get('sips_pricing', {}).get('atr')
        if atr_sips_en_sesion in {'2.0', '3.0', '6.1'}:
            atr_consumos_pricing = atr_sips_en_sesion
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
            if pricing_comparador_disponible and not curva_comparador_disponible
            else 'Curva de carga'
        )
    origen_comparador_seleccionado = st.radio(
        'Origen de consumos para la comparación',
        opciones_origen_comparador,
        horizontal=True,
        key='origen_consumos_comparador_simulindex',
    )
    c1, c2, c3 = st.columns(3)

    if (
        origen_comparador_seleccionado == 'Curva de carga'
        and not curva_comparador_disponible
    ):
        with c1:
            st.info(
                'La curva se importa y normaliza con el mismo flujo del '
                'módulo Curva de carga. Al terminar, vuelve a Simulindex: '
                'la curva quedará disponible en este selector.'
            )
            st.page_link(
                'pages/curvadecarga.py',
                label='Ir a cargar y normalizar la curva',
                icon='📈',
            )
        c2.warning('No hay una curva de carga disponible.')
        c3.info(
            'La comparación anterior se ha descartado al cambiar el origen '
            'de consumos.'
        )
        st.stop()

    if (
        origen_comparador_seleccionado == 'Consumos mensuales / SIPS'
        and not pricing_comparador_disponible
    ):
        with c1:
            archivo_consumos_comparador = st.file_uploader(
                'Sube un Excel de consumos mensuales o un CSV SIPS',
                type=['xlsx', 'xls', 'csv'],
                key='upload_consumos_comparador_simulindex',
            )
        if archivo_consumos_comparador is not None:
            try:
                if archivo_consumos_comparador.name.lower().endswith('.csv'):
                    sips_comparador = leer_sips_completo(
                        archivo_consumos_comparador
                    )
                    atr_sips_comparador = sips_comparador.get('atr')
                    if atr_sips_comparador not in {'2.0', '3.0', '6.1'}:
                        raise ValueError(
                            'El SIPS no contiene un ATR compatible '
                            '(2.0TD, 3.0TD o 6.1TD).'
                        )
                    st.session_state.df_consumos_pricing = (
                        perfil_anual_meses_naturales(
                            sips_comparador['consumos']
                        )
                    )
                    st.session_state._pendiente_pricing_atr_seleccionado = (
                        atr_sips_comparador
                    )
                    st.session_state.sips_pricing = sips_comparador
                    st.session_state.df_consumos_pricing_origen = 'sips'
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
                st.success(
                    'Consumos cargados. También quedan disponibles en Pricing.'
                )
                st.session_state._pendiente_origen_consumos_comparador = (
                    'Consumos mensuales / SIPS'
                )
                st.rerun()
            except Exception as error_carga_comparador:
                st.error(f'No se pudieron leer los consumos: {error_carga_comparador}')

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
        st.subheader('Parametriza escenarios OMIE')
        c12, c13, c14 = st.columns(3)
        with c12:
            simul_a = st.number_input(
                "OMIE simulado A (€/MWh)",
                value=st.session_state.precio_omip_previsto - 5,
            )
        with c13:
            simul_b = st.number_input(
                "OMIE simulado B (€/MWh)",
                value=st.session_state.precio_omip_previsto,
            )
        with c14:
            simul_c = st.number_input(
                "OMIE simulado C (€/MWh)",
                value=st.session_state.precio_omip_previsto + 5,
            )

        lista_simul = [simul_a, simul_b, simul_c]

        st.subheader('Componentes absolutos', divider='rainbow')
        componentes_comparador = [
            ('SSAA sin SRAD (€/MWh)', 'pricing_ssaa_forward_12m'),
            ('SRAD (€/MWh)', 'pricing_srad_prev'),
            ('FNEE (€/MWh)', 'pricing_fnee_prev'),
        ]
        columnas_componentes_comparador = st.columns(3)
        for columna_componente, (etiqueta_componente, clave_pricing) in zip(
            columnas_componentes_comparador, componentes_comparador
        ):
            clave_widget_comparador = f'_{clave_pricing}_comparador'
            st.session_state[clave_widget_comparador] = st.session_state.get(
                clave_pricing, 0.0
            )

            def actualizar_componente_comparador(
                clave_widget=clave_widget_comparador,
                clave_destino=clave_pricing,
            ):
                st.session_state[f'_pendiente_{clave_destino}'] = (
                    st.session_state[clave_widget]
                )

            with columna_componente:
                st.number_input(
                    etiqueta_componente,
                    min_value=0.0,
                    step=0.1,
                    key=clave_widget_comparador,
                    on_change=actualizar_componente_comparador,
                )

        st.subheader('Fórmula indexada', divider='rainbow')
        mostrar_parametros_formula_indexado(
            widget_suffix='simulindex_comparador',
            dos_filas_tres_columnas=True,
        )

        # Entradas de ofertas fijas propias de Simulindex.
        if "df_ofertas_fijas_excel_simulindex" not in st.session_state:
            st.session_state.df_ofertas_fijas_excel_simulindex = pd.DataFrame()
        if "df_oferta_fija_manual_simulindex" not in st.session_state:
            st.session_state.df_oferta_fija_manual_simulindex = pd.DataFrame()
        if "df_ofertas_fijas_ia_simulindex" not in st.session_state:
            st.session_state.df_ofertas_fijas_ia_simulindex = pd.DataFrame()

        st.subheader("Ofertas a precio fijo")
        uploaded_file = st.file_uploader(
            "Sube el Excel con ofertas de precio fijo",
            type=["xlsx", "xls"],
            key="uploaded_ofertas_fijas_simulindex",
        )
        if uploaded_file is not None:
            df_new = pd.read_excel(uploaded_file)
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
        periodos_manuales = (
            ["P1", "P2", "P3"]
            if atr_comparador.startswith("2.0")
            else [f"P{i}" for i in range(1, 7)]
        )

        with st.expander("Importar oferta desde imagen con IA"):
            st.caption(
                "La IA transcribe la tabla. Revisa siempre los precios antes "
                "de incorporarlos a la comparación."
            )
            resultado_portapapeles_ia = paste_image_button(
                "📋 Pegar captura del portapapeles",
                key="pegar_oferta_ia_simulindex",
                errors="raise",
            )

            contenido_imagen_ia = None
            mime_imagen_ia = None
            vista_imagen_ia = None
            if resultado_portapapeles_ia.image_data is not None:
                buffer_imagen_ia = io.BytesIO()
                resultado_portapapeles_ia.image_data.save(
                    buffer_imagen_ia, format="PNG"
                )
                contenido_imagen_ia = buffer_imagen_ia.getvalue()
                mime_imagen_ia = "image/png"
                vista_imagen_ia = resultado_portapapeles_ia.image_data

            if vista_imagen_ia is not None:
                st.image(vista_imagen_ia, caption="Imagen a analizar")
            clave_openai = st.secrets.get("OPENAI_API_KEY")
            analizar_oferta_ia = st.button(
                "Analizar imagen",
                key="analizar_oferta_ia_simulindex",
                disabled=contenido_imagen_ia is None or not bool(clave_openai),
                use_container_width=True,
            )
            if not clave_openai:
                st.info(
                    "Para activar el análisis, configura OPENAI_API_KEY en "
                    ".streamlit/secrets.toml."
                )
            if analizar_oferta_ia:
                try:
                    with st.spinner("Leyendo tarifas y precios..."):
                        tabla_ia, nombre_ia = extraer_oferta_imagen(
                            contenido_imagen_ia,
                            mime_imagen_ia,
                            clave_openai,
                        )
                    st.session_state.tabla_oferta_ia_simulindex = tabla_ia
                    st.session_state.nombre_oferta_ia_simulindex = (
                        nombre_ia or "Oferta desde imagen"
                    )
                except Exception as error_oferta_ia:
                    st.error(f"No se pudo analizar la imagen: {error_oferta_ia}")

            tabla_oferta_ia = st.session_state.get(
                "tabla_oferta_ia_simulindex"
            )
            if isinstance(tabla_oferta_ia, pd.DataFrame) and not tabla_oferta_ia.empty:
                fila_atr_ia = tabla_oferta_ia[
                    tabla_oferta_ia["ATR"] == atr_comparador.removesuffix("TD")
                ].copy()
                if fila_atr_ia.empty:
                    st.warning(
                        f"La imagen no contiene precios para {atr_comparador}."
                    )
                else:
                    if tabla_oferta_ia.attrs.get("unidad_inferida"):
                        st.warning(
                            "La imagen no indica la unidad. Se ha inferido por "
                            "la magnitud de los precios; comprueba los valores "
                            "en €/kWh antes de añadir la oferta."
                        )
                    st.success(
                        f"Detectada la fila {atr_comparador}. Revisa los valores."
                    )
                    nombre_confirmacion_ia = st.text_input(
                        "Nombre de la oferta",
                        key="nombre_oferta_ia_simulindex",
                    )
                    fila_atr_ia = fila_atr_ia[["ATR", *periodos_manuales]]
                    fila_editada_ia = st.data_editor(
                        fila_atr_ia,
                        hide_index=True,
                        disabled=["ATR"],
                        num_rows="fixed",
                        key="editor_oferta_ia_simulindex",
                        column_config={
                            periodo: st.column_config.NumberColumn(
                                periodo, min_value=0.0, max_value=2.0,
                                format="%.6f",
                            )
                            for periodo in periodos_manuales
                        },
                    )
                    if st.button(
                        "Confirmar y añadir oferta",
                        key="confirmar_oferta_ia_simulindex",
                        type="primary",
                        use_container_width=True,
                    ):
                        valores_ia = fila_editada_ia.iloc[0]
                        if not nombre_confirmacion_ia.strip():
                            st.error("Indica un nombre para la oferta.")
                        elif any(
                            pd.isna(valores_ia[p]) or not 0 < float(valores_ia[p]) < 2
                            for p in periodos_manuales
                        ):
                            st.error("Revisa los precios detectados.")
                        else:
                            fila_guardada_ia = {
                                "oferta": nombre_confirmacion_ia.strip(),
                                "Fee (€/MWh)": 0.0,
                                **{f"P{i}": 0.0 for i in range(1, 7)},
                            }
                            fila_guardada_ia.update({
                                p: float(valores_ia[p]) for p in periodos_manuales
                            })
                            ofertas_ia_guardadas = st.session_state.get(
                                "df_ofertas_fijas_ia_simulindex",
                                pd.DataFrame(),
                            ).copy()
                            nombre_nuevo_normalizado = (
                                fila_guardada_ia["oferta"].strip().casefold()
                            )
                            if not ofertas_ia_guardadas.empty:
                                nombres_normalizados = (
                                    ofertas_ia_guardadas["oferta"]
                                    .astype(str)
                                    .str.strip()
                                    .str.casefold()
                                )
                                ofertas_ia_guardadas = ofertas_ia_guardadas.loc[
                                    nombres_normalizados != nombre_nuevo_normalizado
                                ]
                            st.session_state.df_ofertas_fijas_ia_simulindex = (
                                pd.concat(
                                    [
                                        ofertas_ia_guardadas,
                                        pd.DataFrame([fila_guardada_ia]),
                                    ],
                                    ignore_index=True,
                                )
                            )
                            st.session_state.revision_ofertas_ia_simulindex = (
                                st.session_state.get(
                                    "revision_ofertas_ia_simulindex", 0
                                ) + 1
                            )
                            st.success(
                                "Oferta incorporada a la comparación sin "
                                "eliminar las anteriores."
                            )

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
                st.error("Introduce un precio mayor que cero en todos los periodos.")
            else:
                fila_manual_simul = {"oferta": nombre_manual_limpio}
                fila_manual_simul.update(
                    {f"P{i}": 0.0 for i in range(1, 7)}
                )
                fila_manual_simul.update(precios_manual_simul)
                st.session_state.df_oferta_fija_manual_simulindex = pd.DataFrame(
                    [fila_manual_simul]
                )
                st.success(
                    f"Oferta manual «{nombre_manual_limpio}» actualizada."
                )

    with c2:
        origen_comparador = (
            'consumos mensuales del pricing'
            if usar_pricing_en_comparador else 'curva de carga introducida'
        )
        atr_resultado_comparador = (
            atr_calculo_comparador
        )
        st.subheader(
            f'Consumos según {origen_comparador} para peaje '
            f':orange[{atr_resultado_comparador}]'
        )
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
            "kWh</span>",
            unsafe_allow_html=True,
        )

        escenarios = []
        
        #print(f'margen_simul: {margen_simul}')

        # El comparador usa el motor de Pricing para ambos orígenes. La
        # metodología histórica/regresión se conserva íntegra en Principal.
        for etiqueta, omie_value in zip(["A", "B", "C"], lista_simul):
            if True:
                apuntamientos_escenario = (
                    tabla_apuntamientos_spot_3p
                    if atr_calculo_comparador == '2.0'
                    else tabla_apuntamientos
                )
                config_escenario = configuracion_fijos_pricing[
                    atr_calculo_comparador
                ]
                spot_escenario = (
                    apuntamientos_escenario[periodos_comparador_pricing]
                    * omie_value
                )
                perdidas_escenario = df_spot_periodos.groupby(
                    ['mes_pricing', config_escenario['col_periodo']]
                )[f'perd_{atr_calculo_comparador}'].mean()
                horas_escenario = df_spot_periodos.groupby(
                    ['mes_pricing', config_escenario['col_periodo']]
                ).size()
                filas_formula_escenario = []
                for mes_escenario in spot_escenario.index:
                    periodo_mes_escenario = pd.Period(mes_escenario, freq='M')
                    for periodo_escenario in periodos_comparador_pricing:
                        clave_escenario = (
                            periodo_mes_escenario, periodo_escenario
                        )
                        if clave_escenario not in perdidas_escenario.index:
                            continue
                        fila_formula_escenario = {
                            'Mes': mes_escenario,
                            'Periodo': periodo_escenario,
                            'Horas': horas_escenario.loc[clave_escenario],
                            'spot': spot_escenario.loc[
                                mes_escenario, periodo_escenario
                            ],
                            'ssaa': config_escenario['ssaa'].loc[
                                mes_escenario, periodo_escenario
                            ] + srad_pricing,
                            'osom': osom_12m_pricing,
                            'fnee': fnee_pricing,
                            **{f'ppcc_{atr}': 0.0 for atr in ['2.0', '3.0', '6.1']},
                            **{f'perd_{atr}': 0.0 for atr in ['2.0', '3.0', '6.1']},
                            **{f'pyc_{atr}': 0.0 for atr in ['2.0', '3.0', '6.1']},
                        }
                        fila_formula_escenario[
                            f'ppcc_{atr_calculo_comparador}'
                        ] = tabla_ppc_pricing.loc[
                            config_escenario['etiqueta'], periodo_escenario
                        ]
                        fila_formula_escenario[
                            f'perd_{atr_calculo_comparador}'
                        ] = perdidas_escenario.loc[clave_escenario]
                        fila_formula_escenario[
                            f'pyc_{atr_calculo_comparador}'
                        ] = tabla_pyc_pricing.loc[
                            config_escenario['etiqueta'], periodo_escenario
                        ]
                        filas_formula_escenario.append(fila_formula_escenario)
                df_formula_escenario = calcular_precios_atr_formula(
                    pd.DataFrame(filas_formula_escenario), formula_pricing
                )
                tabla_escenario_pricing = df_formula_escenario.pivot(
                    index='Mes',
                    columns='Periodo',
                    values=f'precio_{atr_calculo_comparador}',
                ).div(1000)
                filas_escenario = []
                consumos_por_mes = consumos_fuente_comparador.set_index('mes')
                for mes_escenario in tabla_escenario_pricing.index:
                    numero_mes = pd.Period(mes_escenario, freq='M').month
                    consumo_mes = consumos_por_mes.loc[numero_mes]
                    for periodo_escenario in periodos_comparador_pricing:
                        filas_escenario.append({
                            'Periodo': periodo_escenario,
                            'Consumo': float(consumo_mes[periodo_escenario]),
                            'Precio': float(tabla_escenario_pricing.loc[
                                mes_escenario, periodo_escenario
                            ]),
                        })
                detalle_escenario = pd.DataFrame(filas_escenario)
                resumen_escenario = detalle_escenario.assign(
                    Coste=lambda x: x['Consumo'] * x['Precio']
                ).groupby('Periodo').agg(
                    **{'Consumo (kWh)': ('Consumo', 'sum'), 'Coste (€)': ('Coste', 'sum')}
                )
                resumen_escenario['Precio medio (€/kWh)'] = (
                    resumen_escenario['Coste (€)']
                    / resumen_escenario['Consumo (kWh)'].where(
                        resumen_escenario['Consumo (kWh)'].ne(0)
                    )
                )
                df_resumen_simul = resumen_escenario.T.reindex(
                    columns=[f'P{i}' for i in range(1, 7)], fill_value=0.0
                )
                simul_curva = (
                    detalle_escenario['Consumo'].mul(detalle_escenario['Precio']).sum()
                    / detalle_escenario['Consumo'].sum()
                    * 100
                )

            escenarios.append({
                "label": f"Indexado simulado {etiqueta} ({omie_value:.1f} €/MWh)",
                "simul_curva": simul_curva,
                "df_resumen": df_resumen_simul
            })

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


        ofertas_base_simulindex = []
        for clave_ofertas_simulindex in (
            "df_ofertas_fijas_excel_simulindex",
            "df_oferta_fija_manual_simulindex",
            "df_ofertas_fijas_ia_simulindex",
        ):
            ofertas_fuente = st.session_state.get(clave_ofertas_simulindex)
            if isinstance(ofertas_fuente, pd.DataFrame) and not ofertas_fuente.empty:
                ofertas_base_simulindex.append(ofertas_fuente)

        if ofertas_base_simulindex:
            df_ofertas_base_simul = pd.concat(
                ofertas_base_simulindex, ignore_index=True
            )
        else:
            df_ofertas_base_simul = pd.DataFrame(
                columns=["oferta", *[f"P{i}" for i in range(1, 7)]]
            )

        df_ofertas_calc = df_ofertas_base_simul.copy()
        if not df_ofertas_base_simul.empty:
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
            st.subheader("Resultado ofertas fijo")
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
                    "Tipo": "Indexado",
                    "Coste anual (€)": coste_index,
                    "Precio medio (€/kWh)": precio_medio_index
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


        with c1:
            if usar_pricing_en_comparador:
                st.info(
                    'Comparación calculada con consumos mensuales. No se '
                    'muestra perfil horario porque no existe curva de carga.'
                )
            else:
                st.subheader("Perfil horario")
                graf_medias_horarias = graficar_media_horaria('Total')
                st.plotly_chart(graf_medias_horarias, use_container_width=True)
                st.subheader("Consumo por periodos")
                graf_periodos, df_periodos=graficar_queso_periodos(
                    st.session_state.df_norm_h
                )
                st.plotly_chart(graf_periodos, use_container_width=True)



# =======================================================================================================================================================================
# SECCIÓN COBERTURA TRIMESTRAL
# =======================================================================================================================================================================
with tab6:
    
    if 'df_curva_sheets' not in st.session_state or st.session_state.df_curva_sheets is None or simulcurva is None:
        st.warning('Introduce una curva de carga anual')
        st.stop()

    c1, c2, c3 = st.columns(3)

    with c1:
        st.subheader(f'Selecciona el trimestre de la cobertura')
        st.selectbox('Selecciona trimestre futuro', options=lista_trimestres_futuros, key='trimestre_futuro')

        precio_trim_sel = df_ultimos_precios_trim.loc[df_ultimos_precios_trim['Entrega'] == st.session_state.trimestre_futuro, 'Precio'].iloc[0]

        st.write(graf_omip_trimestral_select)

        st.subheader(f'Parametriza escenarios alternativos')
        c11, c12, c13, c14 = st.columns(4)
        #with c11:
            #st.number_input("Margen (€/MWh)", min_value=0.0, max_value=50.0, value=10.0, step=1.1, key = 'margen_simul_trim')         
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
                OMIE simulado A (€/MWh)
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
            st.number_input("OMIE simulado B (€/MWh)", value=precio_trim_sel-5, key = 'simul_b_trim')
        with c14:
            st.number_input("OMIE simulado C (€/MWh)", value=precio_trim_sel+5,key = 'simul_c_trim')


        

    with c2:
        # ----------------------------
        # 5. FORMATO ESPAÑOL (SOLO VISTA)
        # ----------------------------

        #df_resumen_view = df_resumen.copy()
        
        df_resumen_trim = obtener_df_resumen(df_uso_trimestral, simulcurva, 0.0)
        df_consumos_trim = df_resumen_trim.loc[["Consumo (kWh)"]]
        df_consumos_trim_view = formatear_df_resumen(df_consumos_trim)
        
        # ----------------------------
        # 6. MOSTRAR TABLA DE CONSUMOS
        # ----------------------------
        st.subheader(f'Consumos según curva de carga introducida para peaje :orange[{st.session_state.atr_dfnorm}]')
        st.dataframe(
            df_consumos_trim_view,
            use_container_width=True
        )
            
        lista_simul_trim = [st.session_state.simul_a_trim, st.session_state.simul_b_trim, st.session_state.simul_c_trim]

        escenarios_trim = construir_escenarios(df_uso_trimestral, lista_simul_trim, df_hist, colores_precios, añadir_hist)

        st.subheader('Resultado coberturas de indexados según escenario')
        for esc in escenarios_trim:
            st.markdown(esc["label"])

            df_vista_trim = esc["df_resumen"].loc[
                ["Coste (€)", "Precio medio (€/kWh)"]
            ]

            st.dataframe(
                formatear_df_resumen(df_vista_trim),
                use_container_width=True
            )    


        # CARGAR EXCEL CON PRECIOS FIJOS+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

        # 🔥 CLAVE: empezar siempre de cero
        if 'df_ofertas_fijas_trim' not in st.session_state:
            st.session_state.df_ofertas_fijas_trim = None

        st.subheader("Carga excel con ofertas a precio FIJO")
        st.file_uploader("Sube el Excel con ofertas de precio fijo", type=["xlsx", "xls"], key= 'uploaded_file_trim')

        if st.session_state.uploaded_file_trim is not None:

            df_new_trim = pd.read_excel(st.session_state.uploaded_file_trim)
            df_new_trim.columns = df_new_trim.columns.str.strip()

            # Primera columna = oferta
            col_oferta = df_new_trim.columns[0]
            df_new_trim = df_new_trim.rename(columns={col_oferta: "oferta"})

            periodos = [f"P{i}" for i in range(1, 7)]

            faltan = set(periodos) - set(df_new_trim.columns)
            if faltan:
                st.error(f"Faltan columnas de periodos: {faltan}")
                st.stop()

            for p in periodos:
                df_new_trim[p] = pd.to_numeric(df_new_trim[p], errors="coerce")

            if df_new_trim[periodos].isna().any().any():
                st.error("Hay valores no numéricos en los precios")
                st.stop()

            
            # 🔁 Reemplazar directamente
            st.session_state.df_ofertas_fijas_simul_trim = df_new_trim.copy()

        #if st.session_state.df_ofertas_fijas_simul_trim is not None: 
        if st.session_state.get("df_ofertas_fijas_simul_trim") is not None:
            df_ofertas_trim_view = formatear_df_resumen(st.session_state.df_ofertas_fijas_simul_trim)

            st.markdown("Ofertas fijas cargadas")

            if st.session_state.df_ofertas_fijas_simul_trim.empty:
                st.info("Aún no hay ofertas cargadas")
            else:
                st.dataframe(
                    #st.session_state.df_ofertas_fijas_simul,
                    df_ofertas_trim_view,
                    use_container_width=True,
                    hide_index=True
                )


        with c2:

            periodos = [f"P{i}" for i in range(1, 7)]

            # Consumos por periodo
            consumos_trim = df_resumen_trim.loc["Consumo (kWh)", periodos]

            resultados_trim = []

            # Ofertas fijas
            if st.session_state.get("df_ofertas_fijas_simul_trim") is not None:
                for _, row in st.session_state.df_ofertas_fijas_simul_trim.iterrows():
                    coste_total = (consumos_trim * row[periodos]).sum()
                    energia_total = consumos_trim.sum()
                    precio_medio = coste_total / energia_total

                    resultados_trim.append({
                        "Oferta": row["oferta"],
                        "Tipo": "Fijo",
                        "Coste anual (€)": coste_total,
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
                    "Coste anual (€)": coste_index,
                    "Precio medio (€/kWh)": precio_medio_index
                })

            df_resultados_trim = pd.DataFrame(resultados_trim)
            # Ordenar por coste anual (de más barato a más caro)
            df_resultados_trim = df_resultados_trim.sort_values("Coste anual (€)").reset_index(drop=True)

            coste_min = df_resultados_trim["Coste anual (€)"].iloc[0]

            df_resultados_trim["% sobre la más barata"] = (
                (df_resultados_trim["Coste anual (€)"] - coste_min) / coste_min * 100
            )

            df_resultados_trim["Δ vs más barata (€)"] = (
                df_resultados_trim["Coste anual (€)"] - coste_min
            )

            
            
            df_resultados_trim_view = formatear_df_resultados(df_resultados_trim)

            

        with c3:
            st.subheader("📊 Comparativa TOTALPOWER")
            st.dataframe(df_resultados_trim_view, use_container_width=True, hide_index=True)

            orden_ofertas_trim = df_resultados_trim["Oferta"].tolist()

            fig = px.bar(
                df_resultados_trim,
                x="Oferta",
                y="Coste anual (€)",
                color="Tipo",
                #title="Coste anual por oferta (€)",
                text_auto=".0f",
                category_orders={"Oferta": orden_ofertas_trim}
            )

            # qué barra quieres resaltar
            target = "simulado A"
            highlight = "#FF8C00"  # amarillo-anaranjado

            for trace in fig.data:
                # trace.x son las ofertas que caen en este trace (Tipo)
                trace.marker.color = [
                    (highlight if (isinstance(x, str) and target in x) else c)
                    for x, c in zip(
                        trace.x,
                        [trace.marker.color] * len(trace.x)  # color base del trace
                    )
                ]

            fig.update_layout(
                yaxis_title="Coste anual (€)",
                xaxis_title="",
                legend_title="",
                bargap=.4,
                title=dict(
                    text="Coste TRIMESTRAL por oferta (€)",
                    x=0.5,
                    xanchor="center"
                )
            )
            fig.update_traces(
                textposition="inside",
                textfont_size=16  # ← ajusta aquí
            )



            st.plotly_chart(fig, use_container_width=True)
