"""Motor común para entradas de ofertas fijas en los comparadores."""

from __future__ import annotations

import pandas as pd

PERIODOS = [f"P{i}" for i in range(1, 7)]


def periodos_con_consumo(consumos, atr: str) -> tuple[list[str], list[str]]:
    """Devuelve periodos exigibles y periodos sin consumo."""
    candidatos = PERIODOS[:3] if str(atr).upper().startswith("2.0") else PERIODOS
    serie = pd.to_numeric(pd.Series(consumos).reindex(candidatos), errors="coerce").fillna(0)
    activos = [p for p in candidatos if serie[p] > 0]
    activos = activos or candidatos
    return activos, [p for p in candidatos if p not in activos]


def normalizar_excel_ofertas(tabla: pd.DataFrame) -> pd.DataFrame:
    """Normaliza y valida el contrato común oferta/P1…P6 en €/kWh."""
    datos = tabla.copy()
    datos.columns = datos.columns.astype(str).str.strip()
    if datos.empty or datos.shape[1] == 0:
        raise ValueError("El Excel no contiene ofertas.")
    datos = datos.rename(columns={datos.columns[0]: "oferta"})
    faltantes = set(PERIODOS).difference(datos.columns)
    if faltantes:
        raise ValueError("Faltan columnas de periodos: " + ", ".join(sorted(faltantes)))
    datos["oferta"] = datos["oferta"].astype("string").str.strip()
    if datos["oferta"].isna().any() or datos["oferta"].eq("").any():
        raise ValueError("Hay ofertas sin nombre en el Excel.")
    datos[PERIODOS] = datos[PERIODOS].apply(pd.to_numeric, errors="coerce")
    if datos[PERIODOS].isna().any().any():
        raise ValueError("Hay valores no numéricos en los precios.")
    if (datos[PERIODOS] < 0).any().any():
        raise ValueError("Los precios P1–P6 no pueden contener valores negativos.")
    return datos


def construir_oferta(nombre: str, precios: dict, exigibles: list[str]) -> pd.DataFrame:
    nombre = str(nombre).strip()
    if not nombre:
        raise ValueError("Indica un nombre para la oferta.")
    invalidos = [p for p in exigibles if pd.isna(precios.get(p)) or float(precios[p]) <= 0]
    if invalidos:
        raise ValueError("Introduce un precio mayor que cero en: " + ", ".join(invalidos) + ".")
    fila = {"oferta": nombre, **{p: 0.0 for p in PERIODOS}}
    fila.update({p: float(precios[p]) for p in exigibles})
    return pd.DataFrame([fila])


def construir_ofertas(filas: pd.DataFrame, exigibles: list[str]) -> pd.DataFrame:
    """Valida y conserva todas las filas editadas como ofertas independientes."""
    ofertas = [
        construir_oferta(fila.get("oferta"), fila.to_dict(), exigibles)
        for _, fila in filas.iterrows()
    ]
    if not ofertas:
        return pd.DataFrame(columns=["oferta", *PERIODOS])
    return pd.concat(ofertas, ignore_index=True)


def combinar_ofertas(*tablas) -> pd.DataFrame:
    validas = [t for t in tablas if isinstance(t, pd.DataFrame) and not t.empty]
    if not validas:
        return pd.DataFrame(columns=["oferta", *PERIODOS])
    return pd.concat(validas, ignore_index=True).drop_duplicates("oferta", keep="last")


def render_oferta_ia(atr: str, periodos: list[str], clave: str) -> pd.DataFrame:
    """Carga IA reutilizable; devuelve una oferta confirmada o una tabla vacía."""
    import io
    import streamlit as st
    from streamlit_paste_button import paste_image_button
    from backend_ia_ofertas import extraer_oferta_imagen

    with st.expander("Importar nueva oferta desde imagen con IA"):
        st.caption(
            "La IA transcribe la tabla. Revisa siempre los precios antes de "
            "incorporarlos a la comparación."
        )
        resultado_pegado = paste_image_button(
            "📋 Pegar captura del portapapeles",
            key=f"{clave}_portapapeles",
            errors="raise",
        )
        contenido_imagen = None
        mime_imagen = None
        if resultado_pegado.image_data is not None:
            buffer_imagen = io.BytesIO()
            resultado_pegado.image_data.save(buffer_imagen, format="PNG")
            contenido_imagen = buffer_imagen.getvalue()
            mime_imagen = "image/png"
            st.image(resultado_pegado.image_data, caption="Imagen a analizar")
        api_key = st.secrets.get("OPENAI_API_KEY")
        if st.button(
            "Analizar imagen", key=f"{clave}_analizar",
            disabled=contenido_imagen is None or not api_key,
            use_container_width=True,
        ):
            try:
                tabla, nombre = extraer_oferta_imagen(
                    contenido_imagen, mime_imagen, api_key,
                    atr_contexto=atr,
                )
                st.session_state[f"{clave}_tabla"] = tabla
                st.session_state[f"{clave}_nombre"] = nombre or "Oferta desde imagen"
            except Exception as error:
                st.error(f"No se pudo analizar la imagen: {error}")
        tabla = st.session_state.get(f"{clave}_tabla")
        if isinstance(tabla, pd.DataFrame) and not tabla.empty:
            atr = str(atr).upper().replace(" ", "").removesuffix("TD")
            filas = tabla.loc[tabla["ATR"].astype(str).eq(atr)].copy()
            if filas.empty:
                st.warning(f"La imagen no contiene precios para {atr}TD.")
            else:
                if "oferta" not in filas:
                    nombre_base = st.session_state.get(
                        f"{clave}_nombre", "Oferta desde imagen"
                    )
                    filas["oferta"] = [
                        nombre_base if len(filas) == 1 else f"{nombre_base} {i}"
                        for i in range(1, len(filas) + 1)
                    ]
                st.caption(
                    f"Se han detectado {len(filas)} ofertas. Revisa sus nombres "
                    "y precios antes de incorporarlas."
                )
                editada = st.data_editor(
                    filas[["oferta", "ATR", *periodos]],
                    hide_index=True,
                    disabled=["ATR"],
                    num_rows="fixed",
                    key=f"{clave}_editor",
                )
                if st.button("Confirmar y añadir ofertas", key=f"{clave}_confirmar", type="primary"):
                    try:
                        return construir_ofertas(editada, periodos)
                    except ValueError as error:
                        st.error(str(error))
        if not api_key:
            st.info("Configura OPENAI_API_KEY para activar el análisis.")
    return pd.DataFrame()


def selector_origen_oferta(clave: str) -> str:
    """Selector compacto y homogéneo para todos los comparadores."""
    import streamlit as st
    return st.radio(
        "Origen de la oferta fija",
        ["Oferta manual", "Excel", "IA"],
        horizontal=True,
        key=f"{clave}_origen",
    )


def render_oferta_manual(periodos: list[str], clave: str) -> pd.DataFrame:
    """Formulario manual limitado a los periodos realmente necesarios."""
    import streamlit as st
    with st.form(f"{clave}_form"):
        nombre = st.text_input("Nombre de la oferta", value="Oferta manual")
        columnas = st.columns(len(periodos))
        precios = {}
        for columna, periodo in zip(columnas, periodos):
            with columna:
                precios[periodo] = st.number_input(
                    periodo, min_value=0.0, max_value=2.0, step=0.001,
                    format="%.6f", help="Precio fijo en €/kWh."
                )
        guardar = st.form_submit_button(
            "Añadir o actualizar oferta", type="primary",
            use_container_width=True,
        )
    if guardar:
        try:
            return construir_oferta(nombre, precios, periodos)
        except ValueError as error:
            st.error(str(error))
    return pd.DataFrame()
