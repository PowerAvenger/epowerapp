import base64
import re
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from jinja2 import Environment, FileSystemLoader

from backend_contractual import cargar_datos_suministro
from formato_es import formato_euros, formato_numero_es


def _figura_data_uri(figura):
    try:
        figura = go.Figure(figura)
        figura.update_layout(
            font=dict(size=17), title_font=dict(size=24),
            legend=dict(font=dict(size=15), title_font=dict(size=15)),
        )
        figura.update_yaxes(automargin=True)
        imagen = figura.to_image(format="png", width=1100, height=520, scale=1.5)
        return "data:image/png;base64," + base64.b64encode(imagen).decode("ascii")
    except Exception:
        return ""


def _tabla_html(tabla, decimales=2):
    salida = tabla.copy()
    salida.columns.name = None
    if salida.index.name or not isinstance(salida.index, pd.RangeIndex):
        salida = salida.reset_index()
    for columna in salida.columns:
        serie = pd.to_numeric(salida[columna], errors="coerce")
        if serie.notna().sum() == len(salida):
            salida[columna] = serie.map(
                lambda valor: formato_numero_es(valor, decimales)
            )
        salida[columna] = salida[columna].map(
            lambda valor: escape(str(valor)) if not pd.isna(valor) else "—"
        )
    return salida.to_html(index=False, border=0, escape=False)


def mostrar_informe_comparador_trimestral(datos):
    resultados = datos["resultados"].copy()
    detalle_precios = datos["detalle_precios"].copy()
    trimestre = datos["trimestre"]
    atr = datos["atr"]
    cups_base = str(datos.get("cups", "") or "").strip().upper()
    datos_bbdd = cargar_datos_suministro(cups_base)
    datos_bbdd["cups"] = datos_bbdd.get("cups") or cups_base
    anteriores = st.session_state.get("_simulindex_informe_autocompletado", {})
    for campo in ("cliente", "nif", "direccion", "cups", "atr"):
        clave = f"simulindex_informe_{campo}"
        actual = str(st.session_state.get(clave, "") or "").strip()
        anterior = str(anteriores.get(campo, "") or "").strip()
        valor = str(datos_bbdd.get(campo, "") or "").strip()
        if campo == "atr" and not valor:
            valor = atr
        if valor and (not actual or actual == anterior):
            st.session_state[clave] = valor
    st.session_state._simulindex_informe_autocompletado = datos_bbdd

    col_datos, col_previa = st.columns([0.38, 0.62])
    with col_datos:
        st.selectbox(
            "Tipo de informe disponible",
            ["Informe de comparador trimestral"],
            disabled=True,
        )
        st.caption(
            "El informe utiliza los resultados vigentes de Cobertura trimestral."
        )
        with st.container(border=True):
            st.markdown("#### Datos del cliente y del suministro")
            c1, c2 = st.columns([0.68, 0.32])
            c1.text_input("Cliente / Razón social", key="simulindex_informe_cliente")
            c2.text_input("NIF / CIF", key="simulindex_informe_nif")
            st.text_input("Dirección", key="simulindex_informe_direccion")
            c1, c2 = st.columns([0.68, 0.32])
            c1.text_input("CUPS", key="simulindex_informe_cups")
            c2.text_input("ATR", value=atr, key="simulindex_informe_atr")
        with st.container(border=True):
            st.markdown("#### Datos del informe")
            c1, c2 = st.columns([0.60, 0.40])
            c1.text_input("Realizado por", key="simulindex_informe_realizado_por")
            c2.text_input(
                "Fecha de realización",
                value=pd.Timestamp.today().strftime("%d/%m/%Y"),
                key="simulindex_informe_fecha",
            )
            st.text_input(
                "Objeto del estudio",
                value=(
                    "Comparar ofertas de suministro fijo y coberturas "
                    f"indexadas para {trimestre}."
                ),
                key="simulindex_informe_objeto",
            )
        with st.container(border=True):
            st.markdown("#### Personalización")
            logo = st.file_uploader(
                "Logo para el informe", type=["png", "jpg", "jpeg"],
                key="simulindex_informe_logo",
            )
            if logo is not None:
                st.image(logo, width=180)
            st.text_area(
                "Comentario personalizado",
                key="simulindex_informe_comentario",
                height=110,
            )
        preparar = st.button(
            "Preparar informe", type="primary", use_container_width=True,
            key="preparar_informe_simulindex_trimestral",
        )

    with col_previa:
        if preparar:
            mascara_a = (
                resultados["Tipo"].eq("Indexado")
                & resultados["Oferta"].astype(str).str.contains(
                    "simulado A", case=False, regex=False
                )
            )
            if not mascara_a.any():
                st.error("No se encuentra el escenario indexado A.")
            else:
                escenario_a = resultados.loc[mascara_a].iloc[0]
                ofertas_fijas = resultados.loc[resultados["Tipo"].eq("Fijo")]
                mejor = (
                    ofertas_fijas.sort_values("Coste trimestre (€)").iloc[0]
                    if not ofertas_fijas.empty else escenario_a
                )
                coste_mejor = float(mejor["Coste trimestre (€)"])
                coste_a = float(escenario_a["Coste trimestre (€)"])
                ahorro = coste_a - coste_mejor
                ahorro_pct = 100 * ahorro / coste_a if coste_a else 0.0
                logo_data = ""
                if logo is not None:
                    subtipo = "jpeg" if logo.type == "image/jpeg" else "png"
                    logo_data = f"data:image/{subtipo};base64," + base64.b64encode(
                        logo.getvalue()
                    ).decode("ascii")
                contexto = {
                    "logo": logo_data,
                    "cliente": escape(st.session_state.get("simulindex_informe_cliente", "")),
                    "nif": escape(st.session_state.get("simulindex_informe_nif", "")),
                    "direccion": escape(st.session_state.get("simulindex_informe_direccion", "")),
                    "cups": escape(st.session_state.get("simulindex_informe_cups", "")),
                    "atr": escape(st.session_state.get("simulindex_informe_atr", atr)),
                    "realizado_por": escape(st.session_state.get("simulindex_informe_realizado_por", "")),
                    "fecha_realizacion": escape(st.session_state.get("simulindex_informe_fecha", "")),
                    "objeto": escape(st.session_state.get("simulindex_informe_objeto", "")),
                    "comentario": escape(st.session_state.get("simulindex_informe_comentario", "")),
                    "trimestre": escape(str(trimestre)),
                    "etiqueta_mejor": (
                        "Mejor oferta fija"
                        if not ofertas_fijas.empty else "Referencia disponible"
                    ),
                    "mejor_opcion": escape(str(mejor["Oferta"])),
                    "tipo_mejor": escape(str(mejor["Tipo"])),
                    "coste_mejor": formato_euros(coste_mejor),
                    "precio_mejor": f"{formato_numero_es(float(mejor['Precio medio (€/kWh)']) * 100, 3)} c€/kWh",
                    "coste_escenario_a": formato_euros(coste_a),
                    "precio_escenario_a": f"{formato_numero_es(float(escenario_a['Precio medio (€/kWh)']) * 100, 3)} c€/kWh",
                    "ahorro": formato_euros(ahorro),
                    "ahorro_pct": f"{formato_numero_es(ahorro_pct, 2)} %",
                    "conclusion": (
                        f"La opción de menor coste es {mejor['Oferta']}. "
                        f"Frente al indexado escenario A representa un ahorro "
                        f"de {formato_euros(ahorro)} ({formato_numero_es(ahorro_pct, 2)} %)."
                    ),
                    "tabla_resultados": _tabla_html(resultados),
                    "grafico_resultados": _figura_data_uri(datos.get("grafico")),
                    "tabla_precios": _tabla_html(detalle_precios, 6),
                }
                ruta = Path(__file__).resolve().parent / "templates" / "informe_simulindex_trimestral.html"
                entorno = Environment(loader=FileSystemLoader(str(ruta.parent)))
                st.session_state.informe_simulindex_trimestral_html = (
                    entorno.get_template(ruta.name).render(**contexto)
                )

        html = st.session_state.get("informe_simulindex_trimestral_html")
        if html:
            st.markdown("#### Vista previa")
            st.components.v1.html(html, height=980, scrolling=True)
            cups_archivo = re.sub(
                r"[^A-Za-z0-9]+", "",
                st.session_state.get("simulindex_informe_cups", ""),
            ).upper() or "SIN_CUPS"
            nombre = f"Informe_comparador_{trimestre}_{cups_archivo}"
            st.download_button(
                "Descargar informe HTML", html.encode("utf-8"),
                f"{nombre}.html", "text/html; charset=utf-8",
                use_container_width=True,
            )
        else:
            st.info("La vista previa aparecerá aquí al preparar el informe.")
