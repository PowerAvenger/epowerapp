import pandas as pd
import plotly.express as px
import re
import streamlit as st

from backend_comun import aplicar_estilo
from backend_comparador_luz import (
    calcular_ahorro_seleccion_vs_indexados,
    calcular_costes_potencia,
    calcular_escenarios_indexados_mensuales,
    comparar_ofertas_fijas,
    filtrar_ofertas_elegibles,
    ofertas_catalogo_para_atr,
)
from backend_indexado import FormulaIndexada
from backend_ofertas_fijas import (
    cargar_catalogo_ofertas,
    eliminar_versiones_oferta,
    resolver_potencia_tarifa,
)
from backend_opt2 import consumos_mensuales_desde_curva_normalizada
from backend_simulindex import construir_curva_omip_mensual_12m, obtener_historicos_meff, obtener_meff_mensual, obtener_meff_trimestral
from backend_sips import (
    leer_sips_completo,
    perfil_anual_meses_naturales,
    potencias_contratadas_sips,
)
from componentes_curva import render_origen_curva
from componentes_indexados import (
    render_escenarios_omie,
    render_formula_indexada,
    render_otros_escenarios,
)
from servicio_curva import obtener_curva_sesion
from componentes_ofertas_fijas import (
    combinar_ofertas,
    normalizar_excel_ofertas,
    periodos_con_consumo,
    render_oferta_ia,
    render_oferta_manual,
    selector_origen_oferta,
)
from formato_es import formato_numero_es
from utilidades import (
    generar_menu,
    init_app,
    init_app_index,
)

COLOR_INDEXADO_ETIQUETA = '#7E57C2'

if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')
generar_menu(); init_app()
zona_previa = st.session_state.get('zona_periodos_index', 'peninsula')
st.session_state.zona_periodos_index = 'peninsula'; init_app_index()
st.session_state.zona_periodos_index = zona_previa
st.sidebar.header('⚖️ Comparador luz ⚖️'); st.title('Comparador luz')
tab_energia, tab_potencia_energia, tab_resultados = st.tabs([
    'Ofertas', 'Resultados', 'Comparativa'
])
with tab_energia:
    col1, col2, col3 = st.columns(3)
with tab_potencia_energia:
    col_resultados_principal, col_resultados_energia, col_resultados_potencia = st.columns(3)
    with col_resultados_principal:
        contenedor_resultado_comparativa = st.container()
        contenedor_grafico_resultado = st.container()
    with col_resultados_potencia:
        contenedor_precios_potencia = st.container()
        contenedor_controles_resultado = st.container()
with tab_resultados:
    col_resultados_1, col_resultados_2, col_resultados_3 = st.columns(3)

curva_sesion = st.session_state.get('df_curva_sheets')
potencias_contratadas = pd.Series(index=[f'P{i}' for i in range(1, 7)], dtype=float)
perfil_sips_guardado = st.session_state.get('comparador_luz_perfil_sips')
atr_sips_guardado = st.session_state.get('comparador_luz_atr_sips')
potencias_sips_guardadas = st.session_state.get('comparador_luz_potencias_sips')
metadatos_sips = st.session_state.get('comparador_luz_metadatos_sips', {})
hay_curva = isinstance(curva_sesion, pd.DataFrame) and not curva_sesion.empty
opciones = ['Curva + datos potencia', 'CSV SIPS']
with col1:
    st.subheader('Origen de datos', divider='rainbow')
    origen = st.radio(
        'Selecciona el origen', opciones, horizontal=True,
        label_visibility='collapsed',
    )
if origen == 'Curva + datos potencia':
    with col1:
        contenedor_curva_comparador = st.container()
        acciones_curva_comparador = st.container()
    render_origen_curva(
        contenedor_curva_comparador,
        acciones_curva_comparador,
        clave='comparador_luz_curva',
        titulo_compacto=True,
    )
    curva_actual_comparador = obtener_curva_sesion(st.session_state)
    if curva_actual_comparador is not None:
        curva_sesion = curva_actual_comparador.get('df_norm_h')
        hay_curva = isinstance(curva_sesion, pd.DataFrame) and not curva_sesion.empty
if origen == 'CSV SIPS':
    with col1:
        archivo = st.file_uploader('Sube el CSV SIPS', type=['csv'])
    if archivo is None and isinstance(perfil_sips_guardado, pd.DataFrame):
        perfil_mensual = perfil_sips_guardado.copy()
        atr = str(atr_sips_guardado or '')
        if isinstance(potencias_sips_guardadas, pd.Series):
            potencias_contratadas = potencias_sips_guardadas.copy()
        with col1:
            st.caption('SIPS recuperado de la sesión.')
    elif archivo is None:
        with col1:
            st.info('Sube un CSV SIPS para cargar consumos, ATR y periodos.')
        st.stop()
    else:
      try:
        sips = leer_sips_completo(archivo)
        atr = str(sips.get('atr') or '').upper().removesuffix('TD')
        perfil_mensual = perfil_anual_meses_naturales(sips['consumos'])
        metadatos_sips = sips.get('metadatos', {})
        potencias_contratadas = potencias_contratadas_sips(metadatos_sips)
        st.session_state.comparador_luz_perfil_sips = perfil_mensual.copy()
        st.session_state.comparador_luz_atr_sips = atr
        st.session_state.comparador_luz_potencias_sips = potencias_contratadas.copy()
        st.session_state.comparador_luz_metadatos_sips = dict(metadatos_sips)
      except Exception as error:
        st.error(f'No se pudo leer el SIPS: {error}'); st.stop()
else:
    atr = str(st.session_state.get('atr_dfnorm', '')).upper().removesuffix('TD')
    if not hay_curva:
        with col1:
            st.info('Carga y normaliza una curva; quedará disponible aquí.')
        st.stop()
    periodos_potencia_curva = ['P1', 'P2'] if atr == '2.0' else [f'P{i}' for i in range(1, 7)]
    with col1:
        st.markdown('#### Potencias contratadas (kW)')
        columnas_potencia_curva = st.columns(len(periodos_potencia_curva))
        for columna_potencia, periodo_potencia in zip(columnas_potencia_curva, periodos_potencia_curva):
            with columna_potencia:
                potencias_contratadas[periodo_potencia] = st.number_input(
                    periodo_potencia, min_value=0.0, step=0.1, format='%.3f',
                    key=f'comparador_luz_potencia_curva_{periodo_potencia}',
                )
    try:
        perfil_mensual = consumos_mensuales_desde_curva_normalizada(curva_sesion)
    except ValueError as error:
        st.error(str(error)); st.stop()
atrs_indexados = {'2.0', '3.0', '6.1', '6.2'}
atrs_comparador = {*atrs_indexados, '6.2'}
if atr not in atrs_comparador:
    st.error('El origen no contiene un ATR compatible.'); st.stop()
periodos = [f'P{i}' for i in range(1, 7)]
consumos = perfil_mensual[periodos].apply(pd.to_numeric, errors='coerce').sum()
cups_comparacion = next((
    str(valor).strip() for clave, valor in metadatos_sips.items()
    if 'cups' in str(clave).lower() and valor
), str(st.session_state.get('cups', '') or '').strip())
with col1:
    st.success(
        f'Consumos cargados · {formato_numero_es(consumos.sum(), 0)} kWh · '
        f'ATR {atr}TD'
        + (f' · CUPS {cups_comparacion}.' if cups_comparacion else '.')
    )
    st.markdown('#### Potencias P1–P6')
    st.dataframe(
        potencias_contratadas.to_frame().T.style.format(
            lambda valor: formato_numero_es(valor, 3)
            if pd.notna(valor) else '-'
        ),
        hide_index=True,
        use_container_width=True,
    )
    if not potencias_contratadas.notna().any():
        st.info('El origen no informa las potencias contratadas P1–P6.')
        if origen == 'CSV SIPS':
            campos_potencia_sips = [
                clave for clave in metadatos_sips
                if 'pot' in clave or re.fullmatch(r'p[1-6]|pc[1-6]|pt[1-6]', clave)
            ]
            with st.expander('Diagnóstico de campos de potencia del SIPS'):
                if campos_potencia_sips:
                    st.write(', '.join(campos_potencia_sips))
                else:
                    st.write(
                        'La ficha del CSV no contiene campos cuyo nombre '
                        'identifique potencias contratadas.'
                    )
    elif origen == 'CSV SIPS':
        st.caption('Potencias contratadas tomadas de PT1–PT6 de la ficha superior del SIPS.')
    st.markdown('#### Consumos anuales P1–P6')
    st.dataframe(
        consumos.to_frame().T.style.format(
            lambda valor: formato_numero_es(valor, 0)
        ),
        hide_index=True,
        use_container_width=True,
    )
    consumo_total_anual = pd.to_numeric(
        consumos, errors='coerce'
    ).fillna(0.0).sum()
    st.markdown(
        "Total consumo anual: "
        f"<span style='color:#ffc107; font-size:1.45rem; "
        f"font-weight:700;'>{formato_numero_es(consumo_total_anual, 0)} "
        "kWh</span>",
        unsafe_allow_html=True,
    )
    columnas_consumos_vista = [
        columna for columna in ['periodo_mes', 'año', 'mes', *periodos]
        if columna in perfil_mensual.columns
    ]
    consumos_mensuales_vista = perfil_mensual[
        columnas_consumos_vista
    ].copy()
    consumos_mensuales_vista['_orden_periodo'] = pd.to_datetime(
        consumos_mensuales_vista['periodo_mes'], errors='coerce'
    )
    consumos_mensuales_vista = (
        consumos_mensuales_vista
        .sort_values('_orden_periodo', ascending=False, na_position='last')
        .drop(columns='_orden_periodo')
        .reset_index(drop=True)
    )
    with st.expander('Ver consumos mensuales P1–P6'):
        st.dataframe(
            consumos_mensuales_vista.style.format({
                periodo: lambda valor: formato_numero_es(valor, 0)
                for periodo in periodos
            }),
            hide_index=True,
            use_container_width=True,
        )

forward_actual = float(st.session_state.get('precio_omip_previsto', 50.0))
with col2:
    omies = render_escenarios_omie(
        forward_actual, 'comparador_luz_escenarios'
    )
    otros_escenarios = render_otros_escenarios(
        'comparador_luz_escenarios'
    )
    ssaa = otros_escenarios['ssaa']
    srad = otros_escenarios['srad']
    fnee = otros_escenarios['fnee']
    render_formula_indexada('comparador_luz')

formula = FormulaIndexada(desvios_apant=st.session_state.get('desvios_apant', 0.0), margen=st.session_state.get('margen_telemindex', 0.0), margen_pos=st.session_state.get('cfg_margen_pos', 'tm'), incluir_fnee=st.session_state.get('cfg_fnee', True), fnee_pos=st.session_state.get('cfg_fnee_pos', 'perdidas'), cf_pct=st.session_state.get('cf_pct', 0.0))
referencia = st.session_state.get('df_sheets'); resultado_index = pd.DataFrame()
if (
    atr in atrs_indexados
    and isinstance(referencia, pd.DataFrame)
    and not referencia.empty
):
    resultado_index = calcular_escenarios_indexados_mensuales(referencia, perfil_mensual, atr, formula, omies, ssaa, fnee, srad)

with col2:
    st.subheader('Simulación indexados', divider='rainbow')
    if atr not in atrs_indexados:
        st.info(
            f'La comparación de ofertas fijas y potencia está disponible para '
            f'{atr}TD. La simulación indexada todavía no dispone de componentes '
            'regulados horarios para este ATR.'
        )
    elif resultado_index.empty:
        st.warning('No hay componentes de referencia para simular indexados.')
    else:
        st.dataframe(resultado_index.style.format({'Coste energía (€)': lambda x: formato_numero_es(x, 2), 'Precio medio energía (€/kWh)': lambda x: formato_numero_es(x, 6)}), hide_index=True, use_container_width=True)
        detalle_indexados = resultado_index.attrs.get('detalle', pd.DataFrame())
        with st.expander('Resultado indexados según escenario'):
            for nombre_indexado in resultado_index['Oferta']:
                detalle_oferta = detalle_indexados.loc[
                    detalle_indexados['Oferta'].eq(nombre_indexado)
                ].copy()
                resumen_periodos = detalle_oferta.groupby('Periodo').agg(
                    **{
                        'Coste (€)': ('Coste (€)', 'sum'),
                        'Consumo (kWh)': ('Consumo (kWh)', 'sum'),
                    }
                ).reindex(periodos, fill_value=0.0)
                resumen_periodos['Precio medio (€/kWh)'] = (
                    resumen_periodos['Coste (€)']
                    / resumen_periodos['Consumo (kWh)'].where(
                        resumen_periodos['Consumo (kWh)'].ne(0)
                    )
                ).fillna(0.0)
                tabla_escenario = resumen_periodos[
                    ['Coste (€)', 'Precio medio (€/kWh)']
                ].T
                omie_escenario = omies.get(nombre_indexado, 0.0)
                letra_escenario = nombre_indexado.removeprefix('Indexado ').strip()
                st.markdown(
                    f'**Indexado simulado {letra_escenario} '
                    f'({formato_numero_es(omie_escenario, 1)} €/MWh)**'
                )
                tabla_escenario_vista = tabla_escenario.copy().astype(object)
                for periodo in periodos:
                    tabla_escenario_vista.loc['Coste (€)', periodo] = (
                        f"{formato_numero_es(tabla_escenario.loc['Coste (€)', periodo], 2)} €"
                    )
                    tabla_escenario_vista.loc['Precio medio (€/kWh)', periodo] = (
                        formato_numero_es(
                            tabla_escenario.loc['Precio medio (€/kWh)', periodo], 6
                        )
                    )
                st.dataframe(
                    tabla_escenario_vista,
                    use_container_width=True,
                )
    # Renderiza carga y listado de ofertas en la tercera columna.
    col3.__enter__()
    st.subheader('Cargar oferta fija', divider='rainbow')
    periodos_oferta, periodos_sin_consumo = periodos_con_consumo(consumos, atr)
    if periodos_sin_consumo:
        st.caption(
            'Solo se solicitan precios para periodos con consumo. Sin consumo: '
            + ', '.join(periodos_sin_consumo) + '.'
        )
    origen_oferta = selector_origen_oferta('comparador_luz_oferta')
    oferta_nueva = pd.DataFrame()
    if origen_oferta == 'Oferta manual':
        oferta_nueva = render_oferta_manual(
            periodos_oferta, 'comparador_luz_oferta_manual'
        )
    elif origen_oferta == 'Excel':
        archivo_ofertas = st.file_uploader(
            'Sube el Excel con ofertas de precio fijo',
            type=['xlsx', 'xls'], key='comparador_luz_ofertas_excel',
        )
        if archivo_ofertas is not None:
            try:
                oferta_nueva = normalizar_excel_ofertas(
                    pd.read_excel(archivo_ofertas)
                )
            except ValueError as error_ofertas_excel:
                st.error(str(error_ofertas_excel))
    else:
        oferta_nueva = render_oferta_ia(
            atr, periodos_oferta, 'comparador_luz_oferta_ia'
        )
    if not oferta_nueva.empty:
        id_oferta_nueva = oferta_nueva.attrs.get('id_oferta')
        oferta_nueva = oferta_nueva.copy()
        if 'ID oferta' not in oferta_nueva:
            oferta_nueva['ID oferta'] = (
                id_oferta_nueva if id_oferta_nueva else pd.NA
            )
        oferta_nueva['Potencia modalidad'] = oferta_nueva.get(
            'Potencia modalidad', 'BOE'
        )
        for periodo_potencia in periodos:
            columna_potencia = f'Potencia {periodo_potencia}'
            if columna_potencia not in oferta_nueva:
                oferta_nueva[columna_potencia] = pd.NA
        for columna_usuario in (
            'Vigencia desde', 'Vigencia hasta', 'Plataforma', 'Comisión tipo',
            'Comisión estimada (€)', 'Comisión (€/MWh)',
            'Comisión participación (%)',
        ):
            if columna_usuario not in oferta_nueva:
                oferta_nueva[columna_usuario] = pd.NA
        if 'Fee (€/MWh)' not in oferta_nueva:
            oferta_nueva['Fee (€/MWh)'] = 0.0
        st.session_state.comparador_luz_ofertas_usuario = combinar_ofertas(
            st.session_state.get('comparador_luz_ofertas_usuario'), oferta_nueva
        )

    st.subheader('Ofertas disponibles', divider='rainbow')
    mensaje_borrado = st.session_state.pop(
        'comparador_luz_mensaje_borrado', None
    )
    if mensaje_borrado:
        tipo_mensaje, texto_mensaje = mensaje_borrado
        getattr(st, tipo_mensaje)(texto_mensaje)
    ofertas = combinar_ofertas(
        ofertas_catalogo_para_atr(cargar_catalogo_ofertas(), atr),
        st.session_state.get('comparador_luz_ofertas_usuario'),
    )
    if ofertas.empty: st.info(f'No hay ofertas disponibles para {atr}TD.')
    else:
        if 'ID oferta' not in ofertas:
            ofertas['ID oferta'] = pd.NA
        revision_editor_ofertas = st.session_state.get(
            'comparador_luz_revision_editor_ofertas', 0
        )
        clave_editor_ofertas = (
            f'comparador_luz_editor_ofertas_guardadas_{revision_editor_ofertas}'
        )
        st.session_state.comparador_luz_nombres_editor = (
            ofertas['oferta'].astype(str).tolist()
        )

        def guardar_cambios_fee_editor():
            estado_editor = st.session_state.get(clave_editor_ofertas, {})
            cambios = estado_editor.get('edited_rows', {})
            nombres_editor = st.session_state.get(
                'comparador_luz_nombres_editor', []
            )
            fees_sesion = dict(st.session_state.get(
                'comparador_luz_fees_por_oferta', {}
            ))
            for indice, cambio in cambios.items():
                indice = int(indice)
                if indice >= len(nombres_editor) or 'Fee (€/MWh)' not in cambio:
                    continue
                valor_fee = pd.to_numeric(
                    cambio['Fee (€/MWh)'], errors='coerce'
                )
                fees_sesion[nombres_editor[indice]] = (
                    0.0 if pd.isna(valor_fee) else float(valor_fee)
                )
            st.session_state.comparador_luz_fees_por_oferta = fees_sesion

        fees_guardados = st.session_state.get(
            'comparador_luz_fees_por_oferta', {}
        )
        ofertas['Fee (€/MWh)'] = ofertas.apply(
            lambda fila: float(fees_guardados.get(
                str(fila['oferta']), fila.get('Fee (€/MWh)', 0.0)
            )),
            axis=1,
        )
        columnas_potencia_oferta = ['Potencia modalidad', *[f'Potencia {p}' for p in periodos]]
        columnas_internas_oferta = [
            'ID oferta', *columnas_potencia_oferta, 'Plataforma', 'Comisión tipo',
            'Comisión estimada (€)', 'Comisión (€/MWh)',
            'Comisión participación (%)',
        ]
        ofertas_vista_editor = ofertas.drop(
            columns=columnas_internas_oferta, errors='ignore'
        ).copy()
        ofertas_vista_editor.insert(0, 'Eliminar', False)
        ofertas_editadas = st.data_editor(
            ofertas_vista_editor,
            hide_index=True, num_rows='fixed', use_container_width=True,
            disabled=['oferta', 'Vigencia desde', 'Vigencia hasta', *periodos],
            column_config={
                'Eliminar': st.column_config.CheckboxColumn(
                    'Eliminar', help='Marca las ofertas que quieres borrar.'
                ),
                'Fee (€/MWh)': st.column_config.NumberColumn(
                    min_value=0.0, step=0.1
                ),
            },
            key=clave_editor_ofertas,
            on_change=guardar_cambios_fee_editor,
        )
        ofertas_editadas = ofertas_editadas.reset_index(drop=True)
        st.session_state.comparador_luz_fees_por_oferta = {
            str(fila['oferta']): float(
                pd.to_numeric(fila['Fee (€/MWh)'], errors='coerce')
                if pd.notna(pd.to_numeric(fila['Fee (€/MWh)'], errors='coerce'))
                else 0.0
            )
            for _, fila in ofertas_editadas.iterrows()
        }
        fees_activos = {
            nombre: fee for nombre, fee in
            st.session_state.comparador_luz_fees_por_oferta.items()
            if abs(float(fee)) > 1e-12
        }
        if fees_activos:
            st.caption(
                'Fees aplicados: ' + ' · '.join(
                    f'{nombre}: {formato_numero_es(fee, 2)} €/MWh'
                    for nombre, fee in fees_activos.items()
                )
            )
        for columna_interna in columnas_internas_oferta:
            ofertas_editadas[columna_interna] = ofertas[
                columna_interna
            ].reset_index(drop=True)
        seleccionadas_borrar = ofertas_editadas.loc[
            ofertas_editadas['Eliminar'].fillna(False).astype(bool)
        ].copy()
        if not seleccionadas_borrar.empty:
            st.caption(
                'Al borrar una oferta guardada se elimina su versión completa, '
                'incluidos todos sus peajes.'
            )
        if st.button(
            'Eliminar ofertas seleccionadas',
            key='comparador_luz_eliminar_ofertas',
            disabled=seleccionadas_borrar.empty,
            use_container_width=True,
        ):
            ids_solicitados = {
                str(valor).strip()
                for valor in seleccionadas_borrar['ID oferta'].dropna()
                if str(valor).strip()
            }
            ids_eliminados = set(eliminar_versiones_oferta(ids_solicitados))
            nombres_borrar = set(
                seleccionadas_borrar['oferta'].astype(str).str.strip().str.casefold()
            )
            ofertas_usuario = st.session_state.get(
                'comparador_luz_ofertas_usuario', pd.DataFrame()
            )
            if isinstance(ofertas_usuario, pd.DataFrame) and not ofertas_usuario.empty:
                st.session_state.comparador_luz_ofertas_usuario = ofertas_usuario.loc[
                    ~ofertas_usuario['oferta'].astype(str).str.strip()
                    .str.casefold().isin(nombres_borrar)
                ].copy()
            fees_sesion = dict(st.session_state.get(
                'comparador_luz_fees_por_oferta', {}
            ))
            st.session_state.comparador_luz_fees_por_oferta = {
                nombre: fee for nombre, fee in fees_sesion.items()
                if str(nombre).strip().casefold() not in nombres_borrar
            }
            ids_no_eliminados = ids_solicitados.difference(ids_eliminados)
            cantidad_temporales = int(
                seleccionadas_borrar['ID oferta'].isna().sum()
            )
            cantidad_eliminadas = len(ids_eliminados) + cantidad_temporales
            if ids_no_eliminados:
                mensaje = (
                    f'Se eliminaron {cantidad_eliminadas} oferta(s). '
                    f'{len(ids_no_eliminados)} oferta(s) proceden de un catálogo '
                    'importado de solo lectura y no se modificaron.'
                )
                st.session_state.comparador_luz_mensaje_borrado = (
                    'warning', mensaje
                )
            else:
                st.session_state.comparador_luz_mensaje_borrado = (
                    'success', f'Se eliminaron {cantidad_eliminadas} oferta(s).'
                )
            st.session_state.comparador_luz_revision_editor_ofertas = (
                revision_editor_ofertas + 1
            )
            st.rerun()
        ofertas = ofertas_editadas.drop(columns='Eliminar')
        ofertas, ofertas_excluidas = filtrar_ofertas_elegibles(
            ofertas, float(consumos.sum()), potencias_contratadas,
            cups=cups_comparacion,
        )
        if not ofertas_excluidas.empty:
            st.caption(
                f'{len(ofertas_excluidas)} oferta(s) excluida(s) '
                'automáticamente por condiciones de contratación.'
            )
            with st.expander('Ver ofertas excluidas y motivo'):
                st.dataframe(
                    ofertas_excluidas[['oferta', 'Motivo exclusión']],
                    hide_index=True, use_container_width=True,
                )

    col3.__exit__(None, None, None)

partes = ([resultado_index] if not resultado_index.empty else [])
if not ofertas.empty: partes.append(comparar_ofertas_fijas(consumos, ofertas))
with col_resultados_energia:
    st.subheader('Resultado comparativa SÓLO ENERGÍA', divider='rainbow')
    resultado = pd.concat(partes, ignore_index=True).sort_values('Coste energía (€)') if partes else pd.DataFrame()
    if resultado.empty: st.info('No hay escenarios u ofertas compatibles que comparar.')
    else:
        st.dataframe(resultado.style.format({'Coste energía (€)': lambda x: formato_numero_es(x, 2), 'Precio medio energía (€/kWh)': lambda x: formato_numero_es(x, 6)}), hide_index=True, use_container_width=True)
        resultado_grafico = resultado.sort_values(
            'Coste energía (€)', ascending=False
        )
        grafico = px.bar(
            resultado_grafico,
            x='Coste energía (€)', y='Oferta', color='Tipo',
            orientation='h', text='Coste energía (€)',
            title='Coste anual de energía por oferta',
            color_discrete_map={
                'Indexado': COLOR_INDEXADO_ETIQUETA,
                'Fijo': '#0B74C9',
            },
        )
        grafico.update_traces(
            texttemplate='%{text:,.0f} €', textposition='outside',
            cliponaxis=False,
        )
        grafico = aplicar_estilo(grafico)
        grafico.update_layout(
            height=max(420, 34*len(resultado)+150),
            yaxis_title=None,
            legend_title=None,
            bargap=0.45,
            barcornerradius=8,
            title=dict(x=0.5, xanchor='center'),
            legend=dict(
                orientation='h',
                x=0.5,
                xanchor='center',
                y=1.02,
                yanchor='bottom',
            ),
            margin=dict(l=10, r=80, t=105, b=45),
        )
        coste_maximo_grafico = pd.to_numeric(
            resultado['Coste energía (€)'], errors='coerce'
        ).max()
        if pd.notna(coste_maximo_grafico) and coste_maximo_grafico > 0:
            grafico.update_xaxes(range=[0, float(coste_maximo_grafico) * 1.18])
        grafico.update_yaxes(
            categoryorder='array',
            categoryarray=resultado_grafico['Oferta'].tolist(),
        )
        st.plotly_chart(grafico, use_container_width=True)
with col_resultados_principal:
    if resultado.empty:
        st.info('No hay escenarios u ofertas compatibles que comparar.')
    elif not potencias_contratadas.notna().any():
        st.info('Carga las potencias contratadas para comparar potencia y energía.')
    else:
        meses_comparados = perfil_mensual[['año', 'mes']].drop_duplicates().copy()
        meses_comparados['días'] = pd.to_datetime(dict(
            year=meses_comparados['año'].astype(int),
            month=meses_comparados['mes'].astype(int), day=1,
        )).dt.days_in_month
        dias_por_anio = meses_comparados.groupby('año')['días'].sum().astype(int).to_dict()
        ofertas_potencia = ofertas.copy() if not ofertas.empty else pd.DataFrame()
        if not resultado_index.empty:
            index_potencia = pd.DataFrame({
                'oferta': resultado_index['Oferta'],
                'Potencia modalidad': 'BOE',
            })
            ofertas_potencia = pd.concat([ofertas_potencia, index_potencia], ignore_index=True)
        fecha_referencia_boe = pd.Timestamp.today().normalize()
        costes_potencia = calcular_costes_potencia(
            potencias_contratadas, ofertas_potencia, dias_por_anio, atr,
            fecha_referencia_boe=fecha_referencia_boe,
        )
        ofertas_potencia_boe = ofertas_potencia.copy()
        ofertas_potencia_boe['Potencia modalidad'] = 'BOE'
        costes_potencia_boe = calcular_costes_potencia(
            potencias_contratadas, ofertas_potencia_boe, dias_por_anio, atr,
            fecha_referencia_boe=fecha_referencia_boe,
        ).rename(columns={'Coste potencia (€)': 'Coste potencia BOE (€)'})
        costes_potencia = costes_potencia.merge(
            costes_potencia_boe, on='Oferta', how='left'
        )
        resultado_total = resultado.merge(costes_potencia, on='Oferta', how='left')
        resultado_total['Sobrecoste potencia (€)'] = (
            resultado_total['Coste potencia (€)']
            - resultado_total['Coste potencia BOE (€)']
        ).clip(lower=0.0)
        resultado_total['Potencia base (€)'] = (
            resultado_total['Coste potencia (€)']
            - resultado_total['Sobrecoste potencia (€)']
        )
        resultado_total['Coste total (€)'] = (
            resultado_total['Coste potencia (€)'] + resultado_total['Coste energía (€)']
        )
        resultado_total = resultado_total.sort_values(
            'Coste total (€)', ascending=True
        ).reset_index(drop=True)
        with contenedor_controles_resultado:
            solo_ofertas_un_anio = st.checkbox(
                'Comparar solo ofertas de 1 año',
                value=False,
                key='comparador_luz_solo_ofertas_un_anio',
                help=(
                    'Excluye ofertas identificadas como 2, 3, 5, 7 o 10 años. '
                    'Se mantienen los indexados y las ofertas sin duración indicada.'
                ),
            )
        if solo_ofertas_un_anio:
            duracion_superior = resultado_total['Oferta'].astype(str).str.contains(
                r'\b(?:2|3|5|7|10)\s*AÑOS?\b', case=False, regex=True
            )
            resultado_total = resultado_total.loc[
                resultado_total['Tipo'].eq('Indexado') | ~duracion_superior
            ].reset_index(drop=True)
            ofertas_potencia = ofertas_potencia.loc[
                ofertas_potencia['oferta'].isin(resultado_total['Oferta'])
            ].reset_index(drop=True)
        with contenedor_controles_resultado:
            opciones_referencia = resultado_total['Oferta'].tolist()
            if st.session_state.get(
                'comparador_luz_oferta_referencia_total'
            ) not in opciones_referencia:
                st.session_state.comparador_luz_oferta_referencia_total = (
                    opciones_referencia[0]
                )
            oferta_referencia = st.selectbox(
                'Oferta de referencia',
                options=opciones_referencia,
                index=0,
                key='comparador_luz_oferta_referencia_total',
                help='Las diferencias se calculan respecto a esta oferta.',
            )
            criterio_orden_comision = st.radio(
                'Orden del gráfico de comisiones',
                ['Como comparativa', 'Mayor comisión'],
                index=0,
                horizontal=True,
                key='comparador_luz_orden_comisiones',
            )
            tolerancia_cliente_pct = st.slider(
                'Sobrecoste máximo frente a la oferta más barata (%)',
                min_value=0.0,
                max_value=10.0,
                value=1.0,
                step=0.25,
                key='comparador_luz_tolerancia_win_win',
                help=(
                    'El algoritmo solo considera ofertas cuyo coste anual no '
                    'supere este porcentaje respecto a la más barata.'
                ),
            )
        coste_referencia = float(
            resultado_total.loc[
                resultado_total['Oferta'].eq(oferta_referencia),
                'Coste total (€)',
            ].iloc[0]
        )
        resultado_total['Diferencia vs referencia (€)'] = (
            resultado_total['Coste total (€)'] - coste_referencia
        )
        resultado_total['Delta vs referencia (%)'] = (
            resultado_total['Diferencia vs referencia (€)']
            / coste_referencia * 100
            if coste_referencia else 0.0
        )
        anio_referencia = int(fecha_referencia_boe.year)
        filas_precios_potencia = []
        for _, oferta_potencia in ofertas_potencia.iterrows():
            modalidad = str(
                oferta_potencia.get('Potencia modalidad', 'BOE')
            ).strip().upper()
            modalidad = 'CON MARGEN' if modalidad == 'CON MARGEN' else 'BOE'
            if modalidad == 'BOE':
                precios_potencia = resolver_potencia_tarifa(
                    {'atr': atr, 'potencia': {'modalidad': 'BOE'}},
                    f'{anio_referencia}-01-01',
                )
            else:
                precios_potencia = {
                    periodo: oferta_potencia.get(f'Potencia {periodo}')
                    for periodo in periodos
                }
            filas_precios_potencia.append({
                'Oferta': oferta_potencia['oferta'],
                'Modalidad': modalidad,
                **{periodo: precios_potencia.get(periodo) for periodo in periodos},
            })
        with contenedor_precios_potencia:
            st.markdown('#### Precios de potencia (€/kW día)')
            st.dataframe(
                pd.DataFrame(filas_precios_potencia).style.format({
                    periodo: lambda x: '-' if pd.isna(x) else formato_numero_es(x, 6)
                    for periodo in periodos
                }),
                hide_index=True, use_container_width=True,
            )
        comisiones_previstas = []
        for _, oferta_comision in ofertas_potencia.iterrows():
            tipo_comision = str(oferta_comision.get('Comisión tipo') or '').upper()
            if tipo_comision == 'FIJA':
                comision_total = pd.to_numeric(
                    oferta_comision.get('Comisión estimada (€)'), errors='coerce'
                )
            elif tipo_comision == 'VARIABLE':
                comision_mwh = pd.to_numeric(
                    oferta_comision.get('Comisión (€/MWh)'), errors='coerce'
                )
                comision_total = comision_mwh * float(consumos.sum()) / 1000
            else:
                # En ofertas manuales sin ficha de comisión, el fee introducido
                # se considera comisión variable por energía.
                comision_mwh = pd.to_numeric(
                    oferta_comision.get('Fee (€/MWh)'), errors='coerce'
                )
                comision_total = (
                    float(comision_mwh) * float(consumos.sum()) / 1000
                    if pd.notna(comision_mwh) and float(comision_mwh) != 0
                    else float('nan')
                )
            participacion = pd.to_numeric(
                oferta_comision.get('Comisión participación (%)', 100.0),
                errors='coerce',
            )
            if pd.notna(comision_total):
                comisiones_previstas.append({
                    'Oferta': oferta_comision['oferta'],
                    'Comisión prevista (€)': float(comision_total)
                    * (100.0 if pd.isna(participacion) else float(participacion)) / 100,
                })
        df_comisiones = pd.DataFrame(comisiones_previstas).sort_values(
            'Comisión prevista (€)', ascending=False
        ) if comisiones_previstas else pd.DataFrame()
        if not df_comisiones.empty:
            df_comisiones = resultado_total[['Oferta']].merge(
                df_comisiones, on='Oferta', how='left'
            )
            df_comisiones['Comisión gráfica (€)'] = (
                df_comisiones['Comisión prevista (€)'].fillna(0.0)
            )
        altura_graficos = max(
            420, 34 * max(len(resultado_total), len(df_comisiones)) + 80
        )
        nombres_indexados = set(
            resultado_total.loc[
                resultado_total['Tipo'].eq('Indexado'), 'Oferta'
            ].astype(str)
        )
        nombres_fijos_propios = (
            set(
                ofertas_potencia.loc[
                    ofertas_potencia['Plataforma'].isna(), 'oferta'
                ].astype(str)
            )
            if 'Plataforma' in ofertas_potencia.columns
            else set()
        )
        with col_resultados_2:
            if df_comisiones.empty:
                st.info('No hay comisiones informadas para las ofertas filtradas.')
            else:
                if criterio_orden_comision == 'Como comparativa':
                    ofertas_con_comision = set(df_comisiones['Oferta'])
                    orden_visual_comisiones = [
                        oferta for oferta in resultado_total['Oferta']
                        if oferta in ofertas_con_comision
                    ]
                else:
                    orden_visual_comisiones = df_comisiones.sort_values(
                        'Comisión prevista (€)', ascending=False, na_position='last'
                    )['Oferta'].tolist()
                # Plotly coloca abajo el primer elemento de categoryarray.
                orden_comisiones = orden_visual_comisiones[::-1]
                grafico_comisiones = px.bar(
                    df_comisiones,
                    x='Comisión gráfica (€)', y='Oferta', orientation='h',
                    category_orders={'Oferta': orden_comisiones},
                    color_discrete_sequence=['#27AE60'],
                )
                grafico_comisiones.update_traces(
                    text=[
                        f'{formato_numero_es(valor, 2)} €' if pd.notna(valor) else ''
                        for valor in df_comisiones['Comisión prevista (€)']
                    ],
                    texttemplate='%{text}', textposition='outside',
                    cliponaxis=False,
                )
                grafico_comisiones = aplicar_estilo(grafico_comisiones)
                etiquetas_comisiones = []
                for nombre_oferta in orden_comisiones:
                    if nombre_oferta in nombres_indexados or nombre_oferta in nombres_fijos_propios:
                        etiquetas_comisiones.append('')
                        color_fondo = (
                            COLOR_INDEXADO_ETIQUETA if nombre_oferta in nombres_indexados
                            else '#1565C0'
                        )
                        grafico_comisiones.add_annotation(
                            x=0, xref='paper', xshift=-7,
                            y=nombre_oferta, yref='y',
                            text=nombre_oferta,
                            showarrow=False,
                            xanchor='right', yanchor='middle',
                            bgcolor=color_fondo,
                            borderpad=3,
                            font=dict(color='white', size=10),
                        )
                    else:
                        etiquetas_comisiones.append(nombre_oferta)
                grafico_comisiones.update_layout(
                    height=altura_graficos,
                    showlegend=False, yaxis_title=None,
                    bargap=0.45, barcornerradius=8,
                    title=dict(text=' '),
                    margin=dict(l=10, r=65, t=15, b=45),
                )
                grafico_comisiones.update_yaxes(
                    categoryorder='array', categoryarray=orden_comisiones,
                    tickmode='array', tickvals=orden_comisiones,
                    ticktext=etiquetas_comisiones,
                    range=[-0.5, len(orden_comisiones) - 0.5],
                    fixedrange=True,
                    automargin=True,
                )
                grafico_comisiones.update_xaxes(
                    range=[0, float(df_comisiones['Comisión gráfica (€)'].max()) * 1.20]
                )
                st.markdown(
                    '''
                    <div style="text-align:center; margin:0 0 .35rem 0; height:3.2rem;">
                      <div style="font-size:1.05rem; font-weight:700; margin-bottom:.3rem;">
                        Comisión prevista por oferta
                      </div>
                      <div style="display:flex; justify-content:center; gap:.55rem;
                                  align-items:center; font-size:.70rem; height:1.2rem;
                                  white-space:nowrap;">
                        <span><b style="color:#27AE60;">■</b>&nbsp; Comisión prevista</span>
                      </div>
                    </div>
                    ''',
                    unsafe_allow_html=True,
                )
                st.plotly_chart(grafico_comisiones, use_container_width=True)
        datos_grafico_total = resultado_total.melt(
            id_vars=['Oferta', 'Coste total (€)'],
            value_vars=['Potencia base (€)', 'Sobrecoste potencia (€)', 'Coste energía (€)'],
            var_name='Componente', value_name='Coste (€)',
        )
        datos_grafico_total['Componente'] = datos_grafico_total['Componente'].replace({
            'Potencia base (€)': 'Potencia',
            'Sobrecoste potencia (€)': 'Sobrecoste s/BOE',
            'Coste energía (€)': 'Energía',
        })
        # En un eje Y categórico Plotly dibuja el primer elemento abajo;
        # invertimos el orden para mostrar arriba la oferta más barata.
        orden_ofertas = resultado_total['Oferta'].tolist()[::-1]
        grafico_total = px.bar(
            datos_grafico_total, x='Coste (€)', y='Oferta', color='Componente',
            orientation='h', barmode='stack',
            title=' ',
            category_orders={
                'Componente': ['Potencia', 'Sobrecoste s/BOE', 'Energía'],
                'Oferta': orden_ofertas,
            },
            color_discrete_map={
                'Potencia': '#F2994A',
                'Sobrecoste s/BOE': '#E53935',
                'Energía': '#F2C94C',
            },
        )
        separacion_importes = float(
            resultado_total['Coste total (€)'].max()
        ) * 0.012
        grafico_total.add_scatter(
            x=resultado_total['Coste total (€)'] + separacion_importes,
            y=resultado_total['Oferta'],
            mode='text',
            text=[f'{formato_numero_es(valor, 0)} €' for valor in resultado_total['Coste total (€)']],
            textposition='middle right', showlegend=False, hoverinfo='skip',
            cliponaxis=False,
            textfont=dict(size=14),
        )
        grafico_total = aplicar_estilo(grafico_total)
        etiquetas_eje = []
        for nombre_oferta in orden_ofertas:
            es_indexado = nombre_oferta in nombres_indexados
            es_manual = nombre_oferta in nombres_fijos_propios
            if es_indexado or es_manual:
                etiquetas_eje.append('')
                grafico_total.add_annotation(
                    x=0, xref='paper', xshift=-10,
                    y=nombre_oferta, yref='y',
                    text=nombre_oferta,
                    showarrow=False,
                    xanchor='right', yanchor='middle',
                    bgcolor=COLOR_INDEXADO_ETIQUETA if es_indexado else '#1565C0',
                    borderpad=4,
                    font=dict(color='white', size=14),
                )
            else:
                etiquetas_eje.append(nombre_oferta)
        grafico_total.update_layout(
            height=altura_graficos, yaxis_title=None,
            showlegend=False, bargap=0.45, barcornerradius=8,
            title=dict(text=' '),
            margin=dict(l=145, r=85, t=15, b=60),
            font=dict(size=14),
        )
        grafico_total.update_yaxes(
            categoryorder='array', categoryarray=orden_ofertas,
            tickmode='array', tickvals=orden_ofertas, ticktext=etiquetas_eje,
            range=[-0.5, len(orden_ofertas) - 0.5],
            fixedrange=True,
            automargin=True,
            tickfont=dict(size=14),
        )
        grafico_total.update_xaxes(
            range=[0, float(resultado_total['Coste total (€)'].max()) * 1.22],
            title_text='Coste (€)',
            showticklabels=True,
            automargin=True,
            tickfont=dict(size=13),
            title_font=dict(size=15),
        )
        with col_resultados_1:
            st.markdown(
                '''
                <div style="text-align:center; margin:0 0 .35rem 0; height:3.2rem;">
                  <div style="font-size:1.05rem; font-weight:700; margin-bottom:.3rem;">
                    Coste anual de potencia y energía por oferta
                  </div>
                  <div style="display:flex; justify-content:center; gap:.55rem;
                              align-items:center; font-size:.88rem; height:1.2rem;
                              white-space:nowrap;">
                    <span><b style="color:#F2994A;">■</b>&nbsp; Potencia</span>
                    <span><b style="color:#E53935;">■</b>&nbsp; Sobrecoste s/BOE</span>
                    <span><b style="color:#F2C94C;">■</b>&nbsp; Energía</span>
                  </div>
                </div>
                ''',
                unsafe_allow_html=True,
            )
            st.plotly_chart(grafico_total, use_container_width=True)
        with contenedor_resultado_comparativa:
            st.markdown('#### RESULTADO COMPARATIVA')
            tabla_costes_anuales = resultado_total[[
                'Oferta', 'Coste potencia (€)', 'Coste energía (€)',
                'Coste total (€)', 'Diferencia vs referencia (€)',
                'Delta vs referencia (%)',
            ]].rename(columns={
                'Coste potencia (€)': 'Potencia (€)',
                'Coste energía (€)': 'Energía (€)',
                'Coste total (€)': 'Total (€)',
                'Diferencia vs referencia (€)': 'Diferencia vs ref. (€)',
                'Delta vs referencia (%)': 'Delta vs ref. (%)',
            }).copy()
            for columna_euros in [
                'Potencia (€)', 'Energía (€)', 'Total (€)',
                'Diferencia vs ref. (€)',
            ]:
                tabla_costes_anuales[columna_euros] = (
                    tabla_costes_anuales[columna_euros]
                    .map(lambda x: f'{formato_numero_es(x, 2)} €')
                )
            tabla_costes_anuales['Delta vs ref. (%)'] = (
                tabla_costes_anuales['Delta vs ref. (%)']
                .map(lambda x: f'{formato_numero_es(x, 2)} %')
            )
            estilo_costes_anuales = tabla_costes_anuales.style.apply(
                lambda columna: [
                    (
                        f'background-color: {COLOR_INDEXADO_ETIQUETA}; '
                        'color: white; font-weight: 600;'
                    )
                    if str(valor) in nombres_indexados else ''
                    for valor in columna
                ],
                subset=['Oferta'],
            )
            st.dataframe(
                estilo_costes_anuales,
                hide_index=True, use_container_width=True,
            )
        with contenedor_grafico_resultado:
            st.markdown(
                '''
                <div style="text-align:center; margin:0 0 .35rem 0; height:3.2rem;">
                  <div style="font-size:1.05rem; font-weight:700; margin-bottom:.3rem;">
                    Coste anual de potencia y energía por oferta
                  </div>
                  <div style="display:flex; justify-content:center; gap:.55rem;
                              align-items:center; font-size:.88rem; height:1.2rem;
                              white-space:nowrap;">
                    <span><b style="color:#F2994A;">■</b>&nbsp; Potencia</span>
                    <span><b style="color:#E53935;">■</b>&nbsp; Sobrecoste s/BOE</span>
                    <span><b style="color:#F2C94C;">■</b>&nbsp; Energía</span>
                  </div>
                </div>
                ''',
                unsafe_allow_html=True,
            )
            st.plotly_chart(
                grafico_total,
                use_container_width=True,
                key='grafico_total_tab_resultados',
            )
        with col_resultados_3:
            st.markdown('#### Resultado win-win')
            comisiones_algoritmo = (
                df_comisiones[['Oferta', 'Comisión prevista (€)']]
                if not df_comisiones.empty
                else pd.DataFrame(columns=['Oferta', 'Comisión prevista (€)'])
            )
            evaluacion_win_win = resultado_total.merge(
                comisiones_algoritmo, on='Oferta', how='left'
            )
            evaluacion_win_win['Comisión prevista (€)'] = (
                evaluacion_win_win['Comisión prevista (€)'].fillna(0.0)
            )
            coste_mas_barato = float(
                evaluacion_win_win['Coste total (€)'].min()
            )
            limite_win_win = coste_mas_barato * (
                1 + tolerancia_cliente_pct / 100
            )
            evaluacion_win_win['Sobrecoste vs barata (€)'] = (
                evaluacion_win_win['Coste total (€)'] - coste_mas_barato
            )
            evaluacion_win_win['Sobrecoste vs barata (%)'] = (
                evaluacion_win_win['Sobrecoste vs barata (€)']
                / coste_mas_barato * 100
                if coste_mas_barato else 0.0
            )
            evaluacion_win_win['Ahorro vs referencia (€)'] = (
                coste_referencia - evaluacion_win_win['Coste total (€)']
            )
            candidatas_win_win = evaluacion_win_win.loc[
                evaluacion_win_win['Coste total (€)'].le(limite_win_win + 1e-9)
            ].sort_values(
                ['Comisión prevista (€)', 'Coste total (€)'],
                ascending=[False, True],
            )
            recomendada = candidatas_win_win.iloc[0]
            st.success(f"**{recomendada['Oferta']}**")
            metrica_cliente, metrica_usuario = st.columns(2)
            with metrica_cliente:
                st.metric(
                    'Sobrecoste vs barata',
                    f"{formato_numero_es(recomendada['Sobrecoste vs barata (€)'], 2)} €",
                    f"{formato_numero_es(recomendada['Sobrecoste vs barata (%)'], 2)} %",
                    delta_color='inverse',
                )
            with metrica_usuario:
                st.metric(
                    'Comisión prevista',
                    f"{formato_numero_es(recomendada['Comisión prevista (€)'], 2)} €",
                )
            ahorro_recomendacion = float(
                recomendada['Ahorro vs referencia (€)']
            )
            st.metric(
                f'Ahorro vs {oferta_referencia}',
                f'{formato_numero_es(ahorro_recomendacion, 2)} €',
            )
            st.caption(
                f'{len(candidatas_win_win)} oferta(s) dentro del límite del '
                f'{formato_numero_es(tolerancia_cliente_pct, 2)} %. Entre '
                'ellas se recomienda la de mayor comisión; en caso de empate, '
                'la de menor coste para el cliente.'
            )
            tabla_win_win = candidatas_win_win.head(5)[[
                'Oferta', 'Coste total (€)', 'Sobrecoste vs barata (%)',
                'Comisión prevista (€)',
            ]].rename(columns={
                'Coste total (€)': 'Total',
                'Sobrecoste vs barata (%)': 'Sobrecoste',
                'Comisión prevista (€)': 'Comisión',
            }).copy()
            tabla_win_win['Total'] = tabla_win_win['Total'].map(
                lambda x: f'{formato_numero_es(x, 2)} €'
            )
            tabla_win_win['Sobrecoste'] = tabla_win_win['Sobrecoste'].map(
                lambda x: f'{formato_numero_es(x, 2)} %'
            )
            tabla_win_win['Comisión'] = tabla_win_win['Comisión'].map(
                lambda x: f'{formato_numero_es(x, 2)} €'
            )
            st.dataframe(
                tabla_win_win, hide_index=True, use_container_width=True
            )
            ahorro_vs_indexados = calcular_ahorro_seleccion_vs_indexados(
                resultado_total,
                oferta_referencia,
            )
            st.markdown('#### Ahorro frente a los indexados')
            if ahorro_vs_indexados.empty:
                st.info('No están disponibles los tres escenarios indexados.')
            else:
                tabla_ahorro_indexados = ahorro_vs_indexados[[
                    'Oferta', 'Ahorro (€)', 'Ahorro (%)'
                ]].rename(columns={'Oferta': 'Referencia'}).copy()
                tabla_ahorro_indexados['Ahorro (€)'] = (
                    tabla_ahorro_indexados['Ahorro (€)'].map(
                        lambda valor: f'{formato_numero_es(valor, 2)} €'
                    )
                )
                tabla_ahorro_indexados['Ahorro (%)'] = (
                    tabla_ahorro_indexados['Ahorro (%)'].map(
                        lambda valor: f'{formato_numero_es(valor, 2)} %'
                    )
                )
                st.dataframe(
                    tabla_ahorro_indexados,
                    hide_index=True,
                    use_container_width=True,
                )
                ahorro_minimo = float(
                    ahorro_vs_indexados['Ahorro (€)'].min()
                )
                ahorro_maximo = float(
                    ahorro_vs_indexados['Ahorro (€)'].max()
                )
                ahorro_pct_minimo = float(
                    ahorro_vs_indexados['Ahorro (%)'].min()
                )
                ahorro_pct_maximo = float(
                    ahorro_vs_indexados['Ahorro (%)'].max()
                )
                st.markdown(
                    f'''
                    <div style="padding:1rem .8rem;border:1px solid #e0b400;
                        border-left:6px solid #e0b400;border-radius:.75rem;
                        background:#fff3bf;color:#5f4b00;text-align:center;
                        box-shadow:0 2px 8px rgba(224,180,0,.16);">
                        <div style="font-size:28px;line-height:1.15;">
                            La <b>horquilla de ahorro</b> de la selección frente
                            a indexado es de:
                        </div>
                        <div style="font-size:36px;font-weight:bold;
                            line-height:1.15;margin-top:.35rem;">
                            {formato_numero_es(ahorro_minimo, 2)} € –
                            {formato_numero_es(ahorro_maximo, 2)} €
                            <div style="font-size:24px;margin-top:.25rem;">
                                ({formato_numero_es(ahorro_pct_minimo, 2)} % –
                                {formato_numero_es(ahorro_pct_maximo, 2)} %)
                            </div>
                        </div>
                    </div>
                    ''',
                    unsafe_allow_html=True,
                )
                st.caption(
                    'Un valor positivo indica ahorro de la oferta seleccionada; '
                    'un valor negativo indica sobrecoste.'
                )
