"""Componentes compartidos para parametrizar ofertas indexadas."""

from __future__ import annotations


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


def render_otros_escenarios(clave: str) -> dict[str, float]:
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
        if clave_widget not in st.session_state:
            st.session_state[clave_widget] = float(
                st.session_state.get(clave_estado, defecto)
            )

        def guardar_pendiente(
            widget=clave_widget, destino=clave_estado
        ):
            st.session_state[f'_pendiente_{destino}'] = (
                st.session_state[widget]
            )

        with columna:
            valores[nombre] = st.number_input(
                etiqueta,
                min_value=0.0,
                step=0.1,
                key=clave_widget,
                on_change=guardar_pendiente,
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
