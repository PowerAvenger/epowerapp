"""Componentes compartidos para parametrizar ofertas indexadas."""

from __future__ import annotations


def sincronizar_valor_inicial(estado, clave_widget: str, valor_actual: float) -> None:
    """Actualiza un valor heredado solo mientras el usuario no lo haya editado."""
    clave_anterior = f"_origen_{clave_widget}"
    anterior = estado.get(clave_anterior)
    if anterior is None or clave_widget not in estado or estado[clave_widget] == anterior:
        estado[clave_widget] = float(valor_actual)
    estado[clave_anterior] = float(valor_actual)


def sincronizar_escenarios_aplicados(estado, clave: str, valores: dict[str, float]) -> None:
    """Propaga nuevos valores de referencia a los escenarios no personalizados."""
    clave_anterior = f"_origen_{clave}"
    anteriores = estado.get(clave_anterior)
    escenarios = estado.get(clave)
    if escenarios is not None and anteriores != valores:
        omie, otros = escenarios
        otros = dict(otros)
        for nombre, valor in valores.items():
            if anteriores is None or otros.get(nombre) == anteriores.get(nombre):
                otros[nombre] = float(valor)
        estado[clave] = (omie, otros)
    estado[clave_anterior] = dict(valores)


def _publicar_formula_diferida(clave, claves_estado, nombres):
    """Copia los widgets temporales antes del rerun natural del formulario."""
    import streamlit as st

    for nombre in nombres:
        destino = claves_estado.get(nombre, nombre)
        temporal = f"_{destino}_{clave}"
        if temporal in st.session_state:
            st.session_state[destino] = st.session_state[temporal]


def render_escenarios_omie(precio_central: float, clave: str) -> dict[str, float]:
    """Muestra el selector A/B/C común y devuelve los escenarios OMIE."""
    import streamlit as st

    st.subheader('Parametriza escenarios OMIE', divider='rainbow')
    columnas = st.columns(3)
    valores = {}
    for columna, letra, desplazamiento in zip(
        columnas, ('A', 'B', 'C'), (-5.0, 0.0, 5.0)
    ):
        with columna:
            valores[f'Indexado {letra}'] = st.number_input(
                f'OMIE simulado {letra} (€/MWh)',
                value=float(precio_central) + desplazamiento,
                key=f'{clave}_omie_{letra.lower()}',
            )
    return valores


def render_otros_escenarios(
    clave: str, en_formulario: bool = False,
    aplicados: dict[str, float] | None = None,
) -> dict[str, float]:
    """Muestra SSAA, SRAD y FNEE en una fila común de tres columnas."""
    import streamlit as st

    st.markdown('#### Parametriza otros escenarios')
    componentes = (
        ('ssaa', 'SSAA sin SRAD (€/MWh)', 'pricing_ssaa_forward_12m', 20.0),
        ('srad', 'SRAD (€/MWh)', 'pricing_srad_prev', 1.7),
        ('fnee', 'FNEE (€/MWh)', 'pricing_fnee_prev', 2.68),
    )
    valores = {}
    for columna, (nombre, etiqueta, clave_estado, defecto) in zip(
        st.columns(3), componentes
    ):
        clave_widget = f'_{clave_estado}_{clave}'
        if clave_widget not in st.session_state and aplicados is not None:
            st.session_state[clave_widget] = float(
                aplicados.get(nombre, st.session_state.get(clave_estado, defecto))
            )
            st.session_state[f'_origen_{clave_widget}'] = float(
                st.session_state.get(clave_estado, defecto)
            )
        sincronizar_valor_inicial(
            st.session_state,
            clave_widget,
            st.session_state.get(clave_estado, defecto),
        )

        def guardar_pendiente(
            widget=clave_widget, destino=clave_estado
        ):
            st.session_state[f'_pendiente_{destino}'] = (
                st.session_state[widget]
            )

        with columna:
            opciones = {} if en_formulario else {'on_change': guardar_pendiente}
            valores[nombre] = st.number_input(
                etiqueta,
                min_value=0.0,
                step=0.1,
                key=clave_widget,
                **opciones,
            )
    return valores


def render_formula_indexada(clave: str) -> None:
    """Renderiza la fórmula con la misma estructura en todos los módulos."""
    import streamlit as st
    from utilidades import mostrar_parametros_formula_indexado

    st.subheader('Fórmula indexada', divider='rainbow')
    mostrar_parametros_formula_indexado(
        widget_suffix=clave,
        dos_filas_tres_columnas=True,
    )


def render_formulario_formula_indexada(
    clave: str,
    claves_estado: dict[str, str] | None = None,
    dos_filas_tres_columnas: bool = False,
    etiqueta_boton: str = "Aplicar fórmula",
) -> None:
    """Edita una fórmula en diferido y la publica únicamente al confirmar."""
    import streamlit as st
    from utilidades import mostrar_parametros_formula_indexado

    claves_estado = claves_estado or {}
    with st.form(f"{clave}_form_formula", clear_on_submit=False):
        valores = mostrar_parametros_formula_indexado(
            widget_suffix=clave,
            diferido=True,
            dos_filas_tres_columnas=dos_filas_tres_columnas,
            claves_estado=claves_estado,
        )
        st.form_submit_button(
            etiqueta_boton,
            type="primary",
            use_container_width=True,
            on_click=_publicar_formula_diferida,
            args=(clave, claves_estado, tuple(valores)),
        )
