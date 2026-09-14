"""Componentes Streamlit reutilizables para obtener la curva activa."""

from __future__ import annotations

import re
from datetime import timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from backend_comun import aplicar_estilo
from backend_curvadecarga import (
    colores_periodo,
    dataframe_como_archivo_curva,
    detectar_hojas_curva_excel,
    obtener_consumo_datadis_cacheado,
    obtener_datos_contador,
    obtener_suministros_datadis,
)
from servicio_curva import (
    aviso_resolucion_curva,
    inspeccionar_periodos_fuentes,
    limpiar_curva_sesion,
    normalizar_fuentes_curva,
    obtener_curva_sesion,
    publicar_curva_sesion,
)


ETIQUETAS_ZONA = {
    "peninsula": "Península",
    "baleares": "Baleares",
    "canarias": "Canarias",
    "ceuta": "Ceuta",
    "melilla": "Melilla",
}

OPCIONES_ATR_CURVA = ("2.0", "3.0", "6.1", "6.2", "6.3", "6.4")


def preparar_selector_atr_curva(clave_widget):
    """Sincroniza un selector local con la preferencia común de ATR."""
    preferido = st.session_state.get("atr_curva_preferido")
    if preferido not in OPCIONES_ATR_CURVA:
        curva = obtener_curva_sesion(st.session_state)
        preferido = curva.get("atr") if curva is not None else None
    if preferido not in OPCIONES_ATR_CURVA:
        preferido = st.session_state.get("atr_dfnorm")
    if preferido not in OPCIONES_ATR_CURVA:
        preferido = "2.0"

    clave_sincronizada = f"{clave_widget}__atr_compartido"
    if st.session_state.get(clave_sincronizada) != preferido:
        st.session_state[clave_widget] = preferido
        st.session_state[clave_sincronizada] = preferido
    return preferido


def guardar_selector_atr_curva(clave_widget):
    """Publica el cambio de un selector para los demás puntos de entrada."""
    valor = st.session_state.get(clave_widget)
    if valor not in OPCIONES_ATR_CURVA:
        return
    st.session_state.atr_curva_preferido = valor
    st.session_state[f"{clave_widget}__atr_compartido"] = valor


def ultimos_doce_meses_completos(fecha_referencia=None):
    referencia = pd.Timestamp(
        fecha_referencia if fecha_referencia is not None else pd.Timestamp.today()
    ).normalize()
    fin = referencia.replace(day=1) - pd.Timedelta(days=1)
    inicio = (fin.to_period("M") - 11).start_time
    return inicio.date(), fin.date()


def _guardar_credenciales_axon(clave_usuario, clave_password):
    st.session_state.axon_usuario_sesion = st.session_state.get(clave_usuario, "")
    st.session_state.axon_password_sesion = st.session_state.get(clave_password, "")


def render_campos_axon(clave, en_formulario=False):
    """Renderiza exactamente la misma configuración de Axon en cualquier página."""
    clave_usuario = f"{clave}_axon_usuario"
    clave_password = f"{clave}_axon_password"
    st.session_state.setdefault(
        clave_usuario, st.session_state.get("axon_usuario_sesion", "")
    )
    st.session_state.setdefault(
        clave_password, st.session_state.get("axon_password_sesion", "")
    )
    callback = {} if en_formulario else {
        "on_change": _guardar_credenciales_axon,
        "args": (clave_usuario, clave_password),
    }
    usuario = st.text_input("Usuario Axon", key=clave_usuario, **callback)
    password = st.text_input(
        "Contraseña Axon", type="password", key=clave_password, **callback
    )
    cups = st.text_input("CUPS", key=f"{clave}_axon_cups")
    cups_base = re.sub(r"[^A-Z0-9]", "", str(cups or "").upper())[:20]
    if cups:
        st.caption(f"CUPS base enviado a Axon: `{cups_base}`")

    hoy = pd.Timestamp.today().date()
    inicio_12m, fin_12m = ultimos_doce_meses_completos(hoy)
    clave_automatico = f"{clave}_axon_12m"
    automatico = st.checkbox(
        "Seleccionar automáticamente los últimos 12 meses completos",
        key=clave_automatico,
        help="Excluye el mes actual.",
    )
    clave_rango = f"{clave}_axon_rango"
    st.session_state.setdefault(
        clave_rango, (hoy - timedelta(days=30), hoy - timedelta(days=1))
    )
    if automatico:
        st.session_state[clave_rango] = (inicio_12m, fin_12m)
    rango = st.date_input(
        "Periodo de la curva",
        max_value=hoy,
        format="DD/MM/YYYY",
        key=clave_rango,
        disabled=automatico,
    )
    tipo = st.selectbox(
        "Tipo de curva",
        ("TM2", "TM1"),
        format_func=lambda valor: {
            "TM1": "TM1 · Horaria (H)",
            "TM2": "TM2 · Cuarto horaria (QH)",
        }[valor],
        key=f"{clave}_axon_tipo",
    )
    entrada_lista = bool(
        str(usuario or "").strip()
        and str(password or "")
        and len(cups_base) == 20
        and isinstance(rango, (tuple, list))
        and len(rango) == 2
        and rango[0] <= rango[1]
    )
    return {
        "usuario": usuario,
        "password": password,
        "cups": cups,
        "cups_base": cups_base,
        "rango": rango,
        "tipo": tipo,
        "entrada_lista": entrada_lista,
    }


def render_campos_archivo_curva(clave):
    """Renderiza el cargador CSV/Excel común y realiza su prelectura."""
    archivos = st.file_uploader(
        "📂 Sube uno o varios archivos CSV o Excel",
        type=("csv", "xlsx"),
        accept_multiple_files=True,
        key=(
            f"{clave}_archivos_"
            f"{st.session_state.get('curva_uploader_version', 0)}"
        ),
    )
    hoja_excel = None
    if archivos:
        excels = [a for a in archivos if a.name.lower().endswith(".xlsx")]
        hojas = []
        for excel in excels:
            try:
                hojas.append(set(detectar_hojas_curva_excel(excel)))
            except Exception:
                hojas.append(set())
        if hojas:
            comunes = set.intersection(*hojas)
            opciones = [
                hoja for hoja in ("Cuarto horarias", "Horarias")
                if hoja in comunes
            ]
            if len(opciones) > 1:
                hoja_excel = st.radio(
                    "Curva de los Excel",
                    opciones,
                    format_func=lambda hoja: {
                        "Cuarto horarias": "Cuarto horaria",
                        "Horarias": "Horaria",
                    }[hoja],
                    horizontal=True,
                    key=f"{clave}_hoja",
                )
            elif opciones:
                hoja_excel = opciones[0]
        try:
            trae_periodos = inspeccionar_periodos_fuentes(
                archivos, excel_sheet=hoja_excel
            )
        except Exception:
            trae_periodos = False
    else:
        trae_periodos = False
    return {
        "archivos": archivos,
        "hoja_excel": hoja_excel,
        "trae_periodos": trae_periodos,
        "entrada_lista": bool(archivos),
    }


def _mostrar_zonas(resultado, contenedor):
    zonas = resultado.zonas_compatibles
    if not zonas:
        contenedor.info(
            "Se respetan los periodos del archivo, pero no ha sido posible "
            "asociarlos de forma fiable a una zona."
        )
    elif len(zonas) == 1:
        st.session_state.zona_periodos_confirmada = zonas[0]
        st.session_state.curva_actual["zona_confirmada"] = zonas[0]
        contenedor.info(
            f"Zona compatible: **{ETIQUETAS_ZONA[zonas[0]]}**."
        )
    else:
        contenedor.info(
            "Periodos compatibles con: "
            + ", ".join(ETIQUETAS_ZONA[zona] for zona in zonas)
            + ". Confirma la zona en los datos de origen."
        )


def _publicar(resultado, contenedor):
    publicar_curva_sesion(st.session_state, resultado)
    contenedor.success(
        f"Curva activa actualizada: {len(resultado.df_norm):,} registros."
        .replace(",", ".")
    )
    render_aviso_resolucion_curva(resultado.frecuencia, contenedor)
    _mostrar_zonas(resultado, contenedor)


def render_aviso_resolucion_curva(frecuencia, contenedor=st):
    """Muestra de forma homogénea la resolución de cualquier curva cargada."""
    nivel, mensaje = aviso_resolucion_curva(frecuencia)
    getattr(contenedor, nivel)(mensaje)


def render_resumen_grafico_curva(df_curva, clave="curva_comun", contenedor=st):
    """Renderiza el resumen visual común de una curva normalizada."""
    if not isinstance(df_curva, pd.DataFrame) or df_curva.empty:
        return
    curva = df_curva.copy()
    curva["fecha_hora"] = pd.to_datetime(curva["fecha_hora"], errors="coerce")
    curva["consumo_neto_kWh"] = pd.to_numeric(
        curva["consumo_neto_kWh"], errors="coerce"
    ).fillna(0.0)
    curva = curva.dropna(subset=["fecha_hora"])
    if curva.empty:
        return

    def estilizar(figura):
        figura = aplicar_estilo(figura)
        figura.update_layout(height=300, margin=dict(l=5, r=5, t=38, b=20))
        return figura

    diario = (
        curva.assign(Fecha=curva["fecha_hora"].dt.date)
        .groupby("Fecha", as_index=False)["consumo_neto_kWh"].sum()
        .rename(columns={"consumo_neto_kWh": "Consumo diario (kWh)"})
    )
    por_hora_dia = (
        curva.assign(
            Fecha=curva["fecha_hora"].dt.date,
            Hora=curva["fecha_hora"].dt.hour,
        )
        .groupby(["Fecha", "Hora"], as_index=False)["consumo_neto_kWh"].sum()
    )
    perfil = (
        por_hora_dia.groupby("Hora", as_index=False)["consumo_neto_kWh"].mean()
        .rename(columns={"consumo_neto_kWh": "Consumo medio (kWh)"})
    )

    fig_diario = px.bar(
        diario, x="Fecha", y="Consumo diario (kWh)", title="Consumo diario y medio"
    )
    fig_diario.add_scatter(
        x=diario["Fecha"],
        y=[diario["Consumo diario (kWh)"].mean()] * len(diario),
        name="Media diaria", mode="lines", line=dict(color="#f59e0b", width=2.5),
    )
    fig_diario.update_layout(
        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center")
    )

    fig_perfil = px.line(
        perfil, x="Hora", y="Consumo medio (kWh)", title="Perfil medio horario"
    )
    fig_perfil.update_xaxes(dtick=2, range=[0, 23])
    fig_perfil.update_yaxes(rangemode="tozero")

    figuras_inferiores = []
    if "periodo" in curva.columns and curva["periodo"].notna().any():
        periodos = (
            curva.groupby("periodo", as_index=False)["consumo_neto_kWh"].sum()
            .rename(columns={"consumo_neto_kWh": "Consumo (kWh)"})
        )
        fig_periodos = px.pie(
            periodos, names="periodo", values="Consumo (kWh)", hole=0.42,
            title="Consumo por periodos", color="periodo",
            color_discrete_map=colores_periodo,
        )
        fig_periodos.update_traces(
            textinfo="label+percent", textposition="inside", textfont=dict(size=14)
        )
        fig_periodos.update_layout(showlegend=False)
        figuras_inferiores.append((fig_periodos, "periodos"))

    calor = curva.assign(
        Fecha=curva["fecha_hora"].dt.strftime("%d/%m"),
        Hora=curva["fecha_hora"].dt.hour,
    ).pivot_table(
        index="Fecha", columns="Hora", values="consumo_neto_kWh",
        aggfunc="sum", fill_value=0, sort=False,
    )
    fig_calor = go.Figure(go.Heatmap(
        z=calor.to_numpy(), x=calor.columns, y=calor.index,
        colorscale="YlOrRd", colorbar=dict(title="kWh", thickness=10),
        hovertemplate=(
            "Fecha: %{y}<br>Hora: %{x}:00<br>Consumo: %{z:.2f} kWh<extra></extra>"
        ),
    ))
    fig_calor.update_layout(
        title="Mapa de calor del consumo",
        xaxis_title="Hora", yaxis=dict(title="", autorange="reversed"),
    )
    figuras_inferiores.append((fig_calor, "calor"))

    with contenedor:
        izquierda, derecha = st.columns(2, gap="small")
        izquierda.plotly_chart(
            estilizar(fig_diario), use_container_width=True,
            key=f"{clave}_resumen_diario",
        )
        derecha.plotly_chart(
            estilizar(fig_perfil), use_container_width=True,
            key=f"{clave}_resumen_perfil",
        )
        columnas = (izquierda, derecha) if len(figuras_inferiores) == 2 else (izquierda,)
        for columna, (figura, sufijo) in zip(columnas, figuras_inferiores):
            columna.plotly_chart(
                estilizar(figura), use_container_width=True,
                key=f"{clave}_resumen_{sufijo}",
            )


def render_origen_curva(
    contenedor, acciones, clave="curva_comun", titulo_compacto=False,
    resumen=None, mostrar_resumen=True,
):
    """Renderiza los tres orígenes y publica una sola curva para toda la app."""
    with contenedor:
        if titulo_compacto:
            st.markdown("#### Origen de curva")
        else:
            st.subheader("Origen de curva", divider="rainbow")
        actual = obtener_curva_sesion(st.session_state)
        if actual is not None:
            rango = actual.get("rango_fechas")
            texto_rango = (
                f" · {rango[0]:%d/%m/%Y}–{rango[1]:%d/%m/%Y}"
                if rango and rango[0] is not None and rango[1] is not None else ""
            )
            st.success(
                f"Curva activa: {actual.get('frecuencia', '—')} · "
                f"ATR {actual.get('atr', '—')}{texto_rango}"
            )
            render_aviso_resolucion_curva(actual.get("frecuencia"), st)
            zonas_actuales = actual.get("zonas_compatibles") or []
            if len(zonas_actuales) == 1:
                st.info(
                    "Zona compatible: "
                    f"**{ETIQUETAS_ZONA[zonas_actuales[0]]}**."
                )
            elif len(zonas_actuales) > 1:
                zona_confirmada = actual.get("zona_confirmada")
                if zona_confirmada not in zonas_actuales:
                    zona_confirmada = (
                        "peninsula"
                        if "peninsula" in zonas_actuales else zonas_actuales[0]
                    )
                indice_zona = zonas_actuales.index(zona_confirmada)
                clave_zona_confirmada = f"{clave}_zona_confirmada"
                if (
                    clave_zona_confirmada in st.session_state
                    and st.session_state[clave_zona_confirmada]
                    not in zonas_actuales
                ):
                    st.session_state[clave_zona_confirmada] = zona_confirmada
                zona_confirmada = st.selectbox(
                    "Confirma la zona del suministro",
                    zonas_actuales,
                    index=indice_zona,
                    format_func=ETIQUETAS_ZONA.get,
                    key=clave_zona_confirmada,
                )
                st.session_state.zona_periodos_confirmada = zona_confirmada
                actual["zona_confirmada"] = zona_confirmada

        origen = st.radio(
            "Origen de la curva",
            ("Archivo CSV/Excel", "Axon", "Datadis"),
            horizontal=True,
            key=f"{clave}_origen",
        )
        zona = "peninsula"
        archivo_normalizar = None
        hoja_excel = None
        entrada_lista = False
        trae_periodos = False
        consultar_datadis = False
        with st.form(f"{clave}_form_{origen}"):
            if origen == "Archivo CSV/Excel":
                campos_archivo = render_campos_archivo_curva(clave)
                archivos = campos_archivo["archivos"]
                archivo_normalizar = archivos
                hoja_excel = campos_archivo["hoja_excel"]
                entrada_lista = campos_archivo["entrada_lista"]
                trae_periodos = campos_archivo["trae_periodos"]
                if trae_periodos:
                    st.info(
                        "La curva incluye periodos. Se respetarán y se "
                        "comprobarán las zonas compatibles."
                    )

            elif origen == "Axon":
                campos_axon = render_campos_axon(clave, en_formulario=True)
                usuario = campos_axon["usuario"]
                password = campos_axon["password"]
                cups = campos_axon["cups"]
                rango = campos_axon["rango"]
                tipo = campos_axon["tipo"]
                entrada_lista = campos_axon["entrada_lista"]
                trae_periodos = True

            else:
                usuario = st.text_input(
                    "Usuario Datadis", key=f"{clave}_datadis_usuario"
                )
                password = st.text_input(
                    "Contraseña Datadis", type="password",
                    key=f"{clave}_datadis_password",
                )
                acceso = st.radio(
                    "Acceso", ("Titular", "Autorizado"), horizontal=True,
                    key=f"{clave}_datadis_acceso",
                )
                nif = st.text_input(
                    "NIF del titular", key=f"{clave}_datadis_nif"
                ) if acceso == "Autorizado" else ""
                suministros = st.session_state.get(f"{clave}_datadis_suministros")
                suministro = None
                if suministros is not None and not suministros.empty:
                    indice = st.selectbox(
                        "Suministro", list(suministros.index),
                        format_func=lambda i: str(suministros.loc[i].get("cups", "")),
                        key=f"{clave}_datadis_suministro",
                    )
                    suministro = suministros.loc[indice].to_dict()
                hoy = pd.Timestamp.today().date()
                rango = st.date_input(
                    "Periodo de la curva",
                    value=(hoy - timedelta(days=365), hoy - timedelta(days=1)),
                    max_value=hoy,
                    format="DD/MM/YYYY",
                    key=f"{clave}_datadis_rango",
                )
                preferir_qh = st.checkbox(
                    "Intentar curva cuarto horaria",
                    key=f"{clave}_datadis_qh",
                )
                entrada_lista = bool(
                    usuario and password and suministro is not None
                    and isinstance(rango, (tuple, list)) and len(rango) == 2
                    and (acceso != "Autorizado" or nif)
                )
                trae_periodos = True

            # Todos los orígenes mantienen el mismo orden: primero sus datos,
            # después ATR y, solo si hace falta, la zona para calcular periodos.
            clave_atr = f"{clave}_atr"
            preparar_selector_atr_curva(clave_atr)
            atr = st.selectbox(
                "Peaje de acceso", OPCIONES_ATR_CURVA, key=clave_atr
            )
            if not trae_periodos:
                zona = st.selectbox(
                    "Zona de periodos horarios",
                    tuple(ETIQUETAS_ZONA),
                    format_func=ETIQUETAS_ZONA.get,
                    key=f"{clave}_zona",
                )

            if origen == "Datadis":
                consultar_datadis = st.form_submit_button(
                    "Consultar suministros",
                    use_container_width=True,
                )
            etiqueta = (
                "Obtener y normalizar curva"
                if origen in {"Axon", "Datadis"}
                else "Normalizar curva de carga"
            )
            obtener = st.form_submit_button(
                etiqueta,
                type="primary",
                use_container_width=True,
            )

    with acciones:
        st.markdown("#### Acciones de curva")
        credenciales_datadis_listas = bool(
            origen == "Datadis"
            and usuario and password
            and (acceso != "Autorizado" or nif)
        )
        if consultar_datadis and not credenciales_datadis_listas:
            st.warning("Completa las credenciales de Datadis antes de consultar.")
            consultar_datadis = False
        if obtener and not entrada_lista:
            st.warning(
                "Completa los datos requeridos antes de obtener y normalizar la curva."
            )
            obtener = False
        if consultar_datadis or obtener:
            guardar_selector_atr_curva(clave_atr)
        if origen == "Axon" and obtener:
            _guardar_credenciales_axon(
                f"{clave}_axon_usuario", f"{clave}_axon_password"
            )

        if origen == "Datadis" and consultar_datadis:
            try:
                with st.spinner("Consultando suministros…"):
                    datos = obtener_suministros_datadis(
                        usuario, password, authorized_nif=nif
                    )
                st.session_state[f"{clave}_datadis_suministros"] = datos.reset_index(drop=True)
                st.success(f"{len(datos)} suministro(s) encontrados.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudieron consultar los suministros: {exc}")

        if obtener:
            try:
                if origen == "Axon":
                    with st.spinner("Descargando curva de Axon…"):
                        curva, frecuencia = obtener_datos_contador(
                            usuario, password, cups, rango[0], rango[1], tipo
                        )
                    st.session_state.cups_curva = re.sub(
                        r"[^A-Z0-9]", "", cups.upper()
                    )
                    archivo_normalizar = dataframe_como_archivo_curva(
                        curva, f"axon_{frecuencia.lower()}.csv"
                    )
                elif origen == "Datadis":
                    cache = st.session_state.setdefault("datadis_curvas_cache", {})
                    with st.spinner("Descargando curva de Datadis…"):
                        curva, frecuencia, aviso, _, reutilizado = (
                            obtener_consumo_datadis_cacheado(
                                cache, usuario, password, suministro,
                                rango[0], rango[1], authorized_nif=nif,
                                preferir_qh=preferir_qh,
                            )
                        )
                    st.session_state.cups_curva = str(suministro.get("cups", ""))
                    archivo_normalizar = dataframe_como_archivo_curva(
                        curva, f"datadis_{frecuencia.lower()}.csv"
                    )
                    if aviso:
                        st.warning("Datadis no ha proporcionado resolución QH; se usa H.")
                    elif reutilizado:
                        st.info("Se reutiliza la descarga Datadis de esta sesión.")
                resultado = normalizar_fuentes_curva(
                    archivo_normalizar, atr=atr, zona_periodos=zona,
                    excel_sheet=hoja_excel,
                )
                _publicar(resultado, st)
            except Exception as exc:
                st.error(f"No se pudo obtener y normalizar la curva: {exc}")

        if st.button(
            "Eliminar curva activa", use_container_width=True,
            key=f"{clave}_eliminar",
            disabled=st.session_state.get("df_norm") is None,
        ):
            limpiar_curva_sesion(st.session_state)
            st.rerun()

    curva_resumen = obtener_curva_sesion(st.session_state)
    if mostrar_resumen and curva_resumen is not None:
        render_resumen_grafico_curva(
            curva_resumen.get("df_norm"),
            clave=clave,
            contenedor=resumen or contenedor,
        )
