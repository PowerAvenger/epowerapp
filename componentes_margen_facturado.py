"""Entrada aislada de precios facturados para el análisis de Telemindex."""

from html import escape

import pandas as pd
import streamlit as st

from backend_ofertas_fijas import periodos_aplicables_atr
from formato_es import formato_eur_mwh, formato_euros, formato_pct
from componentes_ofertas_fijas import (
    normalizar_excel_ofertas,
    preparar_tarifas_extraidas,
)


def _guardar_precios(clave, firma_curva, atr, consumos, precios, origen):
    aplicables = periodos_aplicables_atr(atr)
    valores = {}
    for periodo in aplicables:
        valor = pd.to_numeric(precios.get(periodo), errors="coerce")
        consumo = float(pd.to_numeric(consumos.get(periodo, 0), errors="coerce"))
        if pd.isna(consumo):
            raise ValueError(f"No hay un consumo válido para {periodo}.")
        if consumo > 0 and (pd.isna(valor) or not 0 < valor <= 2):
            raise ValueError(
                f"Introduce un precio de energía válido para {periodo} en €/kWh."
            )
        valores[periodo] = float(valor) if pd.notna(valor) else 0.0
    st.session_state[f"{clave}_precios"] = valores
    st.session_state[f"{clave}_firma"] = firma_curva
    st.session_state[f"{clave}_origen_guardado"] = origen


def render_precios_facturados(consumos, atr, firma_curva, clave):
    """Admite entrada manual, Excel o imagen sin alterar el catálogo de ofertas."""
    clave_precios = f"{clave}_precios"
    if st.session_state.get(f"{clave}_firma") != firma_curva:
        st.session_state.pop(clave_precios, None)
        st.session_state.pop(f"{clave}_ia_tarifas", None)
        st.session_state[f"{clave}_firma"] = firma_curva

    aplicables = periodos_aplicables_atr(atr)
    etiqueta = (
        "Editar precios medios facturados"
        if clave_precios in st.session_state
        else "Introducir precios medios facturados"
    )
    with st.expander(etiqueta, expanded=False):
        st.caption(
            "Precios del término de energía en €/kWh, sin impuestos ni potencia, "
            "para el mismo periodo de la curva."
        )
        origen = st.radio(
            "Origen de los precios",
            ("Manual", "Excel", "IA"),
            horizontal=True,
            key=f"{clave}_origen",
        )

        if origen == "Manual":
            with st.form(f"{clave}_manual_form"):
                columnas = st.columns(2)
                precios = {}
                for i, periodo in enumerate(aplicables):
                    with columnas[i % 2]:
                        precios[periodo] = st.number_input(
                            f"{periodo} (€/kWh)",
                            min_value=0.0, max_value=2.0,
                            step=0.001, format="%.6f",
                            key=f"{clave}_manual_{periodo}",
                        )
                guardar = st.form_submit_button(
                    "Aplicar precios facturados", use_container_width=True
                )
            if guardar:
                try:
                    _guardar_precios(
                        clave, firma_curva, atr, consumos, precios, "Manual"
                    )
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))

        elif origen == "Excel":
            archivo = st.file_uploader(
                "Excel con precios P1–P6",
                type=["xlsx", "xls"],
                key=f"{clave}_excel",
            )
            st.caption(
                "Primera columna: referencia. Después, P1–P6 en €/kWh, "
                "como en la tabla de ofertas fijas."
            )
            if archivo is not None:
                try:
                    tabla = normalizar_excel_ofertas(pd.read_excel(archivo))
                    nombres = tabla["oferta"].astype(str).tolist()
                    indice = st.selectbox(
                        "Fila a comparar", range(len(tabla)),
                        format_func=lambda i: nombres[i],
                        key=f"{clave}_excel_fila",
                    )
                    if st.button(
                        "Aplicar fila del Excel",
                        key=f"{clave}_excel_aplicar",
                        use_container_width=True,
                    ):
                        _guardar_precios(
                            clave, firma_curva, atr, consumos,
                            tabla.iloc[indice].to_dict(), f"Excel · {nombres[indice]}",
                        )
                        st.rerun()
                except (ValueError, OSError, ImportError) as error:
                    st.error(str(error))

        else:
            archivo = st.file_uploader(
                "Imagen con precios facturados",
                type=["png", "jpg", "jpeg", "webp"],
                key=f"{clave}_imagen",
            )
            api_key = st.secrets.get("OPENAI_API_KEY")
            if st.button(
                "Extraer precios con IA",
                disabled=archivo is None or not api_key,
                key=f"{clave}_ia_extraer",
                use_container_width=True,
            ):
                try:
                    from backend_ia_ofertas import extraer_oferta_imagen

                    tabla, _ = extraer_oferta_imagen(
                        archivo.getvalue(), archivo.type, api_key,
                        atr_contexto=atr,
                    )
                    tarifas = preparar_tarifas_extraidas(tabla)
                    tarifas = tarifas.loc[tarifas["ATR"].eq(atr)].reset_index(drop=True)
                    if tarifas.empty:
                        raise ValueError(f"La imagen no contiene precios para {atr}TD.")
                    st.session_state[f"{clave}_ia_tarifas"] = tarifas
                    st.session_state[f"{clave}_ia_revision"] = (
                        st.session_state.get(f"{clave}_ia_revision", 0) + 1
                    )
                except Exception as error:
                    st.error(f"No se pudieron extraer los precios: {error}")

            tarifas = st.session_state.get(f"{clave}_ia_tarifas")
            if isinstance(tarifas, pd.DataFrame) and not tarifas.empty:
                st.caption("Revisa y corrige cada precio antes de aplicarlo.")
                indice = st.selectbox(
                    "Fila extraída", range(len(tarifas)),
                    format_func=lambda i: f"Fila {i + 1}",
                    key=f"{clave}_ia_fila",
                )
                editada = st.data_editor(
                    tarifas.loc[[indice], aplicables].reset_index(drop=True),
                    hide_index=True, num_rows="fixed",
                    key=f"{clave}_ia_editor_"
                    f"{st.session_state.get(f'{clave}_ia_revision', 0)}_{indice}",
                    column_config={
                        periodo: st.column_config.NumberColumn(
                            periodo, min_value=0.0, max_value=2.0,
                            format="%.6f",
                        )
                        for periodo in aplicables
                    },
                )
                if st.button(
                    "Aplicar precios revisados",
                    key=f"{clave}_ia_aplicar",
                    use_container_width=True,
                ):
                    try:
                        _guardar_precios(
                            clave, firma_curva, atr, consumos,
                            editada.iloc[0].to_dict(), "IA revisada",
                        )
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
            elif not api_key:
                st.info("Configura OPENAI_API_KEY para activar la lectura de imágenes.")

        if clave_precios in st.session_state:
            st.caption(
                "Origen aplicado: "
                + st.session_state.get(f"{clave}_origen_guardado", "")
            )
            if st.button(
                "Quitar precios facturados", key=f"{clave}_quitar",
                use_container_width=True,
            ):
                st.session_state.pop(clave_precios, None)
                st.rerun()

    return st.session_state.get(clave_precios)


def render_impacto_margen(resultado):
    """Presenta la diferencia facturada como una comparación visual compacta."""
    detalle = resultado["detalle"]
    coste_calculado = float(detalle["Coste fórmula (€)"].sum())
    diferencia = float(resultado["diferencia_coste_vs_formula_eur"])
    coste_facturado = coste_calculado + diferencia
    margen = float(resultado["margen_adicional_eur_mwh"])
    margen_total = float(resultado["margen_implicito_eur_mwh"])
    margen_formula = float(resultado["margen_formula_eur_mwh"])

    color = "#ff7779" if diferencia > 0 else "#55d6a0" if diferencia < 0 else "#aab8c8"
    fondo = "rgba(255,119,121,.13)" if diferencia > 0 else "rgba(85,214,160,.13)" if diferencia < 0 else "rgba(170,184,200,.13)"
    etiqueta = "Sobrecoste" if diferencia > 0 else "Ahorro" if diferencia < 0 else "Sin diferencia"
    flecha = "↑" if diferencia > 0 else "↓" if diferencia < 0 else "="
    porcentaje = (
        formato_pct(abs(100 * diferencia / coste_calculado), 2)
        if coste_calculado else "Sin base de comparación"
    )
    escala = max(abs(coste_calculado), abs(coste_facturado), 1.0)
    ancho_calculado = 100 * max(coste_calculado, 0) / escala
    ancho_facturado = 100 * max(coste_facturado, 0) / escala

    st.markdown(
        f"""
<style>
.tm-impacto {{background:linear-gradient(145deg,#192333,#111820 75%);border:1px solid #34465c;border-radius:15px;padding:17px 18px;color:#f4f7fb;box-shadow:0 8px 24px rgba(0,0,0,.12)}}
.tm-impacto * {{box-sizing:border-box}}
.tm-impacto .tm-titulo {{font-size:19px;font-weight:700;letter-spacing:.01em;margin-bottom:17px}}
.tm-impacto .tm-kpis {{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px}}
.tm-impacto .tm-kpi {{min-width:0;padding:11px 12px;border-radius:11px;background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.08)}}
.tm-impacto .tm-etiqueta {{font-size:14px;line-height:1.35;color:#bbcadb;margin-bottom:8px}}
.tm-impacto .tm-valor {{font-size:clamp(23px,2vw,32px);line-height:1.15;font-weight:700;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}}
.tm-impacto .tm-pill {{display:inline-block;margin-top:9px;padding:4px 10px;border-radius:99px;font-size:14px;font-weight:700;color:{color};background:{fondo}}}
.tm-impacto .tm-fila {{display:flex;justify-content:space-between;gap:8px;font-size:14px;color:#c5d1df;margin:10px 0 5px}}
.tm-impacto .tm-fila strong {{color:#f4f7fb;font-weight:600;white-space:nowrap}}
.tm-impacto .tm-pista {{height:7px;background:rgba(255,255,255,.08);border-radius:99px;overflow:hidden}}
.tm-impacto .tm-barra {{height:100%;border-radius:99px}}
.tm-impacto .tm-pie {{margin-top:17px;padding-top:12px;border-top:1px solid rgba(255,255,255,.1);font-size:14px;line-height:1.5;color:#afc0d1}}
</style>
<div class="tm-impacto">
  <div class="tm-titulo">Impacto estimado</div>
  <div class="tm-kpis">
    <div class="tm-kpi"><div class="tm-etiqueta">Margen adicional estimado</div><div class="tm-valor">{escape(formato_eur_mwh(margen, 2))}</div></div>
    <div class="tm-kpi"><div class="tm-etiqueta">Facturado − calculado</div><div class="tm-valor" style="color:{color}">{escape(formato_euros(diferencia))}</div><span class="tm-pill">{flecha} {escape(porcentaje)} · {etiqueta}</span></div>
  </div>
  <div class="tm-fila"><span>Coste calculado</span><strong>{escape(formato_euros(coste_calculado))}</strong></div>
  <div class="tm-pista"><div class="tm-barra" style="width:{ancho_calculado:.2f}%;background:#5daaf7"></div></div>
  <div class="tm-fila"><span>Coste facturado</span><strong>{escape(formato_euros(coste_facturado))}</strong></div>
  <div class="tm-pista"><div class="tm-barra" style="width:{ancho_facturado:.2f}%;background:{color}"></div></div>
  <div class="tm-pie">Margen implícito total: {escape(formato_eur_mwh(margen_total, 2))} · Incluido en la fórmula: {escape(formato_eur_mwh(margen_formula, 2))}<br>Estimación ponderada por consumo; la diferencia puede incluir conceptos ajenos a la fórmula.</div>
</div>
""",
        unsafe_allow_html=True,
    )
