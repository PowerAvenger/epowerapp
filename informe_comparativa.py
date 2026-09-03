import base64
import re
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader

from formato_es import formato_euros, formato_numero_es
from backend_contractual import cargar_datos_suministro


def _figura_data_uri(figura, ancho=1100, alto=520):
    if figura is None:
        return ""
    try:
        figura_informe = go.Figure(figura)
        figura_informe.update_layout(
            font=dict(size=17),
            title_font=dict(size=24),
            legend=dict(font=dict(size=16), title_font=dict(size=16)),
        )
        figura_informe.update_xaxes(
            tickfont=dict(size=15), title_font=dict(size=18)
        )
        figura_informe.update_yaxes(
            tickfont=dict(size=15), title_font=dict(size=18)
        )
        figura_informe.for_each_annotation(
            lambda anotacion: anotacion.update(font=dict(size=16))
        )
        imagen = figura_informe.to_image(
            format="png", width=ancho, height=alto, scale=1.5
        )
        return "data:image/png;base64," + base64.b64encode(imagen).decode("ascii")
    except Exception:
        return ""


def _tabla_html(tabla, tipo=""):
    salida = tabla.copy()
    salida.columns.name = None
    for columna in salida.columns:
        nombre_columna = str(columna).lower()
        if nombre_columna == "mes":
            meses = pd.to_datetime(
                salida[columna].astype(str).str[:7],
                format="%Y-%m",
                errors="coerce",
            )
            if meses.notna().any():
                salida[columna] = meses.dt.strftime("%m/%Y").fillna("—")
            continue
        if any(texto in nombre_columna for texto in ("fecha", "desde", "hasta")):
            fechas = pd.to_datetime(salida[columna], errors="coerce")
            if fechas.notna().any():
                salida[columna] = fechas.dt.strftime("%d/%m/%Y").fillna("—")
            continue
        serie = pd.to_numeric(salida[columna], errors="coerce")
        if serie.notna().sum() == len(salida):
            salida[columna] = serie.map(
                lambda valor: formato_numero_es(valor, 2)
            )
    for columna in salida.columns:
        salida[columna] = salida[columna].map(
            lambda valor: escape(str(valor)) if not pd.isna(valor) else "—"
        )

    def unidad_columna(columna):
        nombre = str(columna).lower()
        if "%" in nombre or "porcentaje" in nombre:
            return "%"
        if "precio_unitario_eur_kwh" in nombre:
            return "€/kWh"
        if "eur_mwh" in nombre or "€/mwh" in nombre:
            return "€/MWh"
        if "precio" in nombre:
            return "c€/kWh" if tipo == "costes" else "€/kWh"
        if "consumo" in nombre or "cantidad" in nombre or "kwh" in nombre:
            return "kWh"
        if any(texto in nombre for texto in ("coste", "efecto", "importe", "variación")):
            return "€"
        if tipo == "consumos" and nombre not in ("mes", "periodo"):
            return "kWh"
        return ""

    salida.columns = [
        (
            f"{escape(str(columna))}<br>"
            f"<span class=\"unidad\">{unidad_columna(columna)}</span>"
            if unidad_columna(columna) else escape(str(columna))
        )
        for columna in salida.columns
    ]
    return salida.to_html(index=False, border=0, na_rep="—", escape=False)


def mostrar_informe_comparativa(informe):
    consumo = informe["consumo"]
    costes = informe["costes"]
    cups = str(informe.get("cups", "") or "").strip().upper()
    datos_bbdd = cargar_datos_suministro(cups)
    datos_bbdd["cups"] = datos_bbdd.get("cups") or cups
    anteriores = st.session_state.get("_comparativa_informe_autocompletado", {})
    for campo in ("cliente", "nif", "direccion", "cups", "atr"):
        clave = f"comparativa_informe_{campo}"
        actual = str(st.session_state.get(clave, "") or "").strip()
        anterior = str(anteriores.get(campo, "") or "").strip()
        valor = str(datos_bbdd.get(campo, "") or "").strip()
        if valor and (not actual or actual == anterior):
            st.session_state[clave] = valor
    st.session_state._comparativa_informe_autocompletado = datos_bbdd

    col_datos, col_previa = st.columns([0.38, 0.62])
    with col_datos:
        st.caption(
            "Completa los datos una sola vez. El informe utiliza exactamente "
            "los resultados ya calculados en Comparaciones."
        )
        with st.container(border=True):
            st.markdown("#### Datos del cliente y del suministro")
            c1, c2 = st.columns([0.68, 0.32])
            c1.text_input("Cliente / Razón social", key="comparativa_informe_cliente")
            c2.text_input("NIF / CIF", key="comparativa_informe_nif")
            st.text_input("Dirección", key="comparativa_informe_direccion")
            c1, c2 = st.columns([0.68, 0.32])
            c1.text_input("CUPS", key="comparativa_informe_cups")
            c2.text_input("ATR", key="comparativa_informe_atr")
        with st.container(border=True):
            st.markdown("#### Datos del informe")
            c1, c2 = st.columns([0.60, 0.40])
            c1.text_input("Realizado por", key="comparativa_informe_realizado_por")
            c2.text_input(
                "Fecha de realización",
                value=pd.Timestamp.today().strftime("%d/%m/%Y"),
                key="comparativa_informe_fecha",
            )
            st.text_input(
                "Objeto del estudio",
                value=(
                    "Comparar la evolución del consumo, del coste de energía "
                    "y del precio medio entre ambos periodos."
                ),
                key="comparativa_informe_objeto",
            )
        with st.container(border=True):
            st.markdown("#### Personalización")
            logo = st.file_uploader(
                "Logo para el informe",
                type=["png", "jpg", "jpeg"],
                key="comparativa_informe_logo",
            )
            if logo is not None:
                st.image(logo, width=180)
            st.text_area(
                "Comentario personalizado",
                key="comparativa_informe_comentario",
                placeholder=(
                    "Añade una observación, recomendación o contexto para "
                    "el destinatario del informe."
                ),
                height=120,
            )
        preparar = st.button(
            "Preparar informe",
            type="primary",
            use_container_width=True,
            key="preparar_informe_comparativa",
        )

    with col_previa:
        if preparar:
            df_consumos = consumo["df_pivot"].copy()
            df_costes = costes["df_costes"].copy()
            df_efectos = costes["df_efectos"].copy()
            etiqueta_base, etiqueta_comp = costes.get(
                "etiquetas_periodos", ("Base", "+1 año")
            )
            cb = float(df_costes[f"Consumo {etiqueta_base}"].sum())
            cc = float(df_costes[f"Consumo {etiqueta_comp}"].sum())
            kb = float(df_costes[f"Coste {etiqueta_base}"].sum())
            kc = float(df_costes[f"Coste {etiqueta_comp}"].sum())
            dc, dk = cc - cb, kc - kb
            pc = 100 * dc / cb if cb else np.nan
            pk = 100 * dk / kb if kb else np.nan
            pb = 100 * kb / cb if cb else np.nan
            pn = 100 * kc / cc if cc else np.nan
            ep = float(df_efectos["Efecto precio"].sum())
            ec = float(df_efectos["Efecto consumo"].sum())
            rango = consumo.get("fechas", {}).get("rango_valido")
            periodo = (
                f"{rango[0]:%d/%m/%Y} – {rango[1]:%d/%m/%Y} / +1 año"
                if rango is not None else f"{etiqueta_base} / {etiqueta_comp}"
            )
            direccion = "aumenta" if dk >= 0 else "disminuye"
            causa = "precio" if abs(ep) >= abs(ec) else "consumo"
            logo_data = ""
            if logo is not None:
                subtipo = "jpeg" if logo.type == "image/jpeg" else "png"
                logo_data = f"data:image/{subtipo};base64," + base64.b64encode(
                    logo.getvalue()
                ).decode("ascii")
            resumen_contractual = informe.get("resumen_contractual")
            fig_efectos_informe = costes.get("fig_efectos")
            if fig_efectos_informe is not None:
                fig_efectos_informe = go.Figure(fig_efectos_informe)
                for traza in fig_efectos_informe.data:
                    if getattr(traza, "name", "") == "Δ coste real":
                        traza.update(
                            line=dict(color="#111111", width=4),
                            marker=dict(color="#111111", size=8),
                        )
            contexto = {
                "logo": logo_data,
                "cliente": escape(st.session_state.get("comparativa_informe_cliente", "")),
                "nif": escape(st.session_state.get("comparativa_informe_nif", "")),
                "direccion": escape(st.session_state.get("comparativa_informe_direccion", "")),
                "cups": escape(st.session_state.get("comparativa_informe_cups", "")),
                "atr": escape(st.session_state.get("comparativa_informe_atr", "")),
                "realizado_por": escape(st.session_state.get("comparativa_informe_realizado_por", "")),
                "fecha_realizacion": escape(st.session_state.get("comparativa_informe_fecha", "")),
                "objeto": escape(st.session_state.get("comparativa_informe_objeto", "")),
                "comentario": escape(
                    st.session_state.get("comparativa_informe_comentario", "")
                ),
                "periodo": periodo,
                "etiqueta_base": etiqueta_base,
                "etiqueta_comp": etiqueta_comp,
                "delta_consumo": f"{formato_numero_es(dc, 0)} kWh",
                "pct_consumo": f"{formato_numero_es(pc, 2)} %",
                "delta_coste": formato_euros(dk),
                "pct_coste": f"{formato_numero_es(pk, 2)} %",
                "precio_base": f"{formato_numero_es(pb, 2)} c€/kWh",
                "precio_comp": f"{formato_numero_es(pn, 2)} c€/kWh",
                "delta_precio": f"{formato_numero_es(pn - pb, 2)} c€/kWh",
                "efecto_precio": formato_euros(ep),
                "efecto_consumo": formato_euros(ec),
                "conclusion": (
                    f"El coste {direccion} {formato_euros(abs(dk))}. "
                    f"El componente con mayor impacto es el efecto {causa}."
                ),
                "grafico_consumo_total": _figura_data_uri(consumo.get("fig_total")),
                "grafico_consumo_mensual": _figura_data_uri(consumo.get("fig_mensual")),
                "grafico_coste_total": _figura_data_uri(costes.get("fig_resumen_costes")),
                "grafico_coste_mensual": _figura_data_uri(costes.get("fig_coste_total")),
                "grafico_precios": _figura_data_uri(costes.get("fig_precio_medio")),
                "grafico_efectos": _figura_data_uri(fig_efectos_informe),
                "tabla_consumos": _tabla_html(df_consumos, "consumos"),
                "tabla_costes": _tabla_html(df_costes, "costes"),
                "tabla_efectos": _tabla_html(df_efectos, "efectos"),
                "tabla_contractual": (
                    _tabla_html(resumen_contractual)
                    if isinstance(resumen_contractual, pd.DataFrame)
                    and not resumen_contractual.empty else ""
                ),
            }
            ruta = Path(__file__).resolve().parent / "templates" / "informe_comparativa.html"
            entorno = Environment(loader=FileSystemLoader(str(ruta.parent)))
            st.session_state.informe_comparativa_html = entorno.get_template(
                ruta.name
            ).render(**contexto)

        html = st.session_state.get("informe_comparativa_html")
        if html:
            st.markdown("#### Vista previa")
            st.components.v1.html(html, height=980, scrolling=True)
            cups_archivo = re.sub(
                r"[^A-Za-z0-9]+", "",
                st.session_state.get("comparativa_informe_cups", ""),
            ).upper() or "SIN_CUPS"
            fechas_calculadas = consumo.get("debug", {})
            fecha_inicio_calculada = fechas_calculadas.get("inicio")
            fecha_fin_comparada = fechas_calculadas.get("fin_1y")
            if (
                fecha_inicio_calculada is not None
                and fecha_fin_comparada is not None
            ):
                fecha_inicio_archivo = pd.Timestamp(fecha_inicio_calculada)
                fecha_fin_archivo = pd.Timestamp(fecha_fin_comparada)
                fechas_nombre_archivo = (
                    f"{fecha_inicio_archivo:%Y%m%d}_"
                    f"{fecha_fin_archivo:%Y%m%d}"
                )
            else:
                fechas_nombre_archivo = "SIN_FECHAS"
            st.download_button(
                "Descargar informe HTML",
                data=html.encode("utf-8"),
                file_name=(
                    f"Informe_consumo_precio_{cups_archivo}_"
                    f"{fechas_nombre_archivo}.html"
                ),
                mime="text/html; charset=utf-8",
                use_container_width=True,
            )
        else:
            st.info("La vista previa aparecerá aquí al preparar el informe.")
