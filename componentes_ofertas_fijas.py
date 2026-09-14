"""Motor común para entradas de ofertas fijas en los comparadores."""

from __future__ import annotations

from contextlib import nullcontext

import pandas as pd

from backend_ofertas_fijas import (
    normalizar_atr,
    periodos_aplicables_atr,
    periodos_con_consumo,
    periodos_no_aplicables_atr,
)

PERIODOS = [f"P{i}" for i in range(1, 7)]


def aplicar_seleccion_ofertas(
    ofertas: pd.DataFrame,
    seleccion_guardada: dict[str, bool] | None,
) -> pd.DataFrame:
    """Restaura los checks por nombre; las ofertas nuevas nacen seleccionadas."""
    salida = ofertas.copy()
    estado = seleccion_guardada or {}
    valores = salida["oferta"].astype(str).map(
        lambda nombre: bool(estado.get(nombre, True))
    )
    if "Comparar" in salida:
        salida["Comparar"] = valores
    else:
        salida.insert(0, "Comparar", valores)
    return salida


def actualizar_seleccion_ofertas(
    ofertas_editadas: pd.DataFrame,
    seleccion_guardada: dict[str, bool] | None = None,
) -> dict[str, bool]:
    """Actualiza el estado durable sin olvidar ofertas temporalmente ocultas."""
    estado = dict(seleccion_guardada or {})
    if "Comparar" not in ofertas_editadas:
        return estado
    estado.update({
        str(fila["oferta"]): bool(fila["Comparar"])
        for _, fila in ofertas_editadas.iterrows()
    })
    return estado


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


def preparar_tarifas_extraidas(tabla: pd.DataFrame) -> pd.DataFrame:
    """Normaliza el ATR visible y prepara la tabla común de revisión."""
    from backend_ia_ofertas import detectar_atr_en_texto

    datos = tabla.copy()
    for periodo in PERIODOS:
        if periodo not in datos:
            datos[periodo] = None
    if "ATR" not in datos:
        datos["ATR"] = ""
    datos["ATR"] = datos.apply(
        lambda fila: detectar_atr_en_texto(fila.get("oferta"))
        or normalizar_atr(fila.get("ATR")),
        axis=1,
    )
    datos.loc[datos["ATR"].eq("2.0"), PERIODOS[3:]] = None
    return datos[["ATR", *PERIODOS]].reset_index(drop=True)


def campos_pendientes_tarifas(tarifas: pd.DataFrame) -> list[str]:
    """Enumera únicamente las celdas obligatorias que necesitan revisión."""
    pendientes = []
    for _, fila in tarifas.iterrows():
        atr = normalizar_atr(fila.get("ATR"))
        for periodo in periodos_aplicables_atr(atr):
            valor = pd.to_numeric(fila.get(periodo), errors="coerce")
            if pd.isna(valor) or not 0 < float(valor) <= 2:
                pendientes.append(f"{atr}TD/{periodo}")
    return pendientes


def oferta_actual_desde_tarifas(
    tarifas: pd.DataFrame,
    nombre: str,
    atr: str,
    exigibles: list[str],
    vigencia_desde=None,
    vigencia_hasta=None,
) -> pd.DataFrame:
    """Obtiene del conjunto confirmado la fila utilizable por el comparador."""
    from backend_ofertas_fijas import normalizar_tarifas_oferta

    tarifas = normalizar_tarifas_oferta(tarifas)
    atr = normalizar_atr(atr)
    fila_atr = tarifas.loc[tarifas["ATR"].eq(atr)]
    if fila_atr.empty:
        raise ValueError(f"La oferta no contiene precios para {atr}TD.")
    precios = fila_atr.iloc[0].to_dict()
    aplicables = periodos_aplicables_atr(atr)
    # Conserva el juego de precios completo del peaje, aunque la curva actual
    # no tenga consumo en alguno de sus periodos.
    oferta = construir_oferta(nombre, precios, aplicables)
    oferta["Vigencia desde"] = (
        pd.Timestamp(vigencia_desde).date().isoformat()
        if vigencia_desde is not None else None
    )
    oferta["Vigencia hasta"] = (
        pd.Timestamp(vigencia_hasta).date().isoformat()
        if vigencia_hasta is not None else None
    )
    return oferta


def combinar_ofertas(*tablas) -> pd.DataFrame:
    validas = [t for t in tablas if isinstance(t, pd.DataFrame) and not t.empty]
    if not validas:
        return pd.DataFrame(columns=["oferta", *PERIODOS])
    return pd.concat(validas, ignore_index=True).drop_duplicates("oferta", keep="last")


def render_oferta_ia(atr: str, periodos: list[str], clave: str) -> pd.DataFrame:
    """Revisa, guarda todos los ATR y devuelve el ATR activo al comparador."""
    import io
    import streamlit as st
    from streamlit_paste_button import paste_image_button
    from backend_ia_ofertas import extraer_oferta_imagen
    from backend_ofertas_fijas import guardar_version_oferta

    atr = normalizar_atr(atr)
    aplicables = periodos_aplicables_atr(atr)
    periodos = [periodo for periodo in periodos if periodo in aplicables]
    periodos = periodos or aplicables

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
                st.session_state[f"{clave}_nombre_editor"] = (
                    nombre or "Oferta desde imagen"
                )
            except Exception as error:
                st.error(f"No se pudo analizar la imagen: {error}")
        tabla = st.session_state.get(f"{clave}_tabla")
        if isinstance(tabla, pd.DataFrame) and not tabla.empty:
            tarifas = preparar_tarifas_extraidas(tabla)
            if tabla.attrs.get("unidad_inferida"):
                st.warning(
                    "La imagen no indica la unidad. Se ha inferido por la "
                    "magnitud de los precios; comprueba los valores en €/kWh."
                )

            clave_nombre_editor = f"{clave}_nombre_editor"
            if clave_nombre_editor not in st.session_state:
                st.session_state[clave_nombre_editor] = st.session_state.get(
                    f"{clave}_nombre", "Oferta desde imagen"
                )
            nombre = st.text_input(
                "Nombre de la oferta", key=clave_nombre_editor
            )
            hoy = pd.Timestamp.today().date()
            columnas_fechas = st.columns(2)
            with columnas_fechas[0]:
                vigencia_desde = st.date_input(
                    "Vigencia desde", value=hoy,
                    key=f"{clave}_vigencia_desde",
                )
            with columnas_fechas[1]:
                con_fecha_fin = st.checkbox(
                    "Indicar fecha fin", value=True,
                    key=f"{clave}_con_fecha_fin",
                )
                vigencia_hasta = None
                if con_fecha_fin:
                    vigencia_hasta = st.date_input(
                        "Vigencia hasta",
                        value=(
                            pd.Timestamp(vigencia_desde)
                            + pd.Timedelta(days=7)
                        ).date(),
                        key=f"{clave}_vigencia_hasta",
                    )

            st.caption(
                f"Se han detectado {len(tarifas)} peajes. Revisa todos los "
                "precios antes de cargarlos al sistema."
            )
            editada = st.data_editor(
                tarifas,
                hide_index=True,
                disabled=["ATR"],
                num_rows="fixed",
                key=f"{clave}_editor",
                column_config={
                    "ATR": st.column_config.TextColumn("Tarifa", width="small"),
                    **{
                        periodo: st.column_config.NumberColumn(
                            periodo,
                            min_value=0.0,
                            max_value=2.0,
                            format="%.6f",
                            width="small",
                        )
                        for periodo in PERIODOS
                    },
                },
            )
            pendientes = campos_pendientes_tarifas(editada)
            if pendientes:
                st.warning(
                    "La IA no ha podido leer con seguridad: "
                    + ", ".join(pendientes)
                    + ". Completa esas celdas antes de confirmar."
                )
            if st.button(
                "Confirmar y cargar oferta",
                key=f"{clave}_confirmar",
                type="primary",
                use_container_width=True,
            ):
                try:
                    oferta_actual = oferta_actual_desde_tarifas(
                        editada, nombre, atr, periodos,
                        vigencia_desde, vigencia_hasta,
                    )
                    registro_guardado = guardar_version_oferta(
                        nombre, vigencia_desde, vigencia_hasta, editada
                    )
                    oferta_actual.attrs["id_oferta"] = registro_guardado["id"]
                    st.success(
                        f"Oferta «{nombre.strip()}» guardada con {len(editada)} "
                        f"peajes. Se ha añadido {atr}TD a esta comparativa."
                    )
                    return oferta_actual
                except (OSError, ValueError) as error:
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


def render_selector_ofertas(
    ofertas: pd.DataFrame,
    clave: str,
    columnas_bloqueadas: list[str] | None = None,
    columnas_visibles: list[str] | None = None,
    titulo_expander: str | None = None,
) -> pd.DataFrame:
    """Muestra el selector común y devuelve la tabla con la columna Comparar."""
    import streamlit as st

    clave_seleccion = f"{clave}_seleccion"
    estado = st.session_state.get(clave_seleccion)
    seleccion = aplicar_seleccion_ofertas(ofertas, estado)
    contenedor = st.expander(titulo_expander) if titulo_expander else nullcontext()
    with contenedor:
        editadas = st.data_editor(
            seleccion,
            hide_index=True,
            num_rows="fixed",
            disabled=columnas_bloqueadas or ["oferta", *PERIODOS],
            column_order=columnas_visibles,
            use_container_width=True,
            key=clave,
            column_config={
                "Comparar": st.column_config.CheckboxColumn(
                    "Comparar", help="Incluye o excluye la oferta del cálculo."
                ),
                "Fee (€/MWh)": st.column_config.NumberColumn(
                    "Fee (€/MWh)", min_value=0.0, max_value=100.0,
                    step=0.1, format="%.2f",
                ),
            },
        )
    st.session_state[clave_seleccion] = actualizar_seleccion_ofertas(
        editadas, estado
    )
    return editadas


def render_simulador_horquilla_ssaa(
    ofertas: pd.DataFrame,
    clave_bloque: str,
    curva: pd.DataFrame,
    columna_perdidas: str | None = None,
    apuntamiento_spot: float | None = None,
) -> None:
    """Crea copias temporales para estimar el riesgo de una horquilla SSAA."""
    import streamlit as st
    from backend_ofertas_fijas import (
        copiar_oferta_con_horquilla_ssaa,
        perdidas_medias_ponderadas,
    )
    from formato_es import formato_numero_es

    clave_detalles = f"{clave_bloque}_horquillas_ssaa"
    detalles_sesion = dict(st.session_state.get(clave_detalles, {}))
    nombres_obsoletos = {
        nombre for nombre, detalle in detalles_sesion.items()
        if not isinstance(detalle, dict)
        or detalle.get("version_calculo") != 2
        or not isinstance(detalle.get("detalle_mensual"), pd.DataFrame)
    }
    if nombres_obsoletos:
        clave_usuario = f"{clave_bloque}_ofertas_usuario"
        ofertas_usuario = st.session_state.get(clave_usuario)
        if isinstance(ofertas_usuario, pd.DataFrame) and not ofertas_usuario.empty:
            st.session_state[clave_usuario] = ofertas_usuario.loc[
                ~ofertas_usuario["oferta"].astype(str).isin(nombres_obsoletos)
            ].copy()
        st.session_state[clave_detalles] = {
            nombre: detalle for nombre, detalle in detalles_sesion.items()
            if nombre not in nombres_obsoletos
        }
        st.rerun()

    perdidas_pct = (
        perdidas_medias_ponderadas(curva, columna_perdidas)
        if columna_perdidas else 0.0
    )
    with st.expander("🧮 Calcular ajuste de SSAA"):
        if ofertas.empty:
            st.info("Selecciona al menos una oferta fija para crear la simulación.")
        else:
            nombres = ofertas["oferta"].astype(str).tolist()
            with st.form(f"{clave_bloque}_form_horquilla_ssaa"):
                nombre_origen = st.selectbox("Oferta base", nombres)
                nombre_copia = st.text_input(
                    "Nombre de la copia para esta sesión",
                    value="Oferta con horquilla SSAA",
                )
                c_limite, c_perdidas, c_apuntamiento = st.columns(3)
                with c_limite:
                    limite = st.number_input(
                        "Horquilla superior SSAA (€/MWh)",
                        min_value=0.0,
                        value=16.77,
                        step=0.01,
                        format="%.2f",
                    )
                with c_perdidas:
                    st.number_input(
                        "Pérdidas (%)",
                        value=float(perdidas_pct),
                        format="%.2f",
                        disabled=True,
                    )
                with c_apuntamiento:
                    st.number_input(
                        "Apuntamiento spot",
                        value=float(apuntamiento_spot or 0.0),
                        format="%.3f",
                        disabled=True,
                    )
                st.caption(
                    "Cálculo mensual: exceso sobre la horquilla × apuntamiento "
                    "SSAA × (1 + pérdidas ponderadas) × TM 1,015. El resultado "
                    "se multiplica por el consumo mensual; los importes de todos "
                    "los meses se suman para obtener el ajuste del periodo. El "
                    "apuntamiento spot se muestra como referencia informativa."
                )
                crear = st.form_submit_button(
                    "Crear copia temporal", type="primary",
                    use_container_width=True,
                )
            if crear:
                try:
                    oferta = ofertas.loc[
                        ofertas["oferta"].astype(str).eq(nombre_origen)
                    ].iloc[0]
                    copia, detalle = copiar_oferta_con_horquilla_ssaa(
                        oferta,
                        nombre_copia,
                        limite,
                        curva,
                        columna_perdidas=columna_perdidas,
                        factor_tm=1.015,
                    )
                    clave_usuario = f"{clave_bloque}_ofertas_usuario"
                    st.session_state[clave_usuario] = combinar_ofertas(
                        st.session_state.get(clave_usuario), copia
                    )
                    detalles = dict(st.session_state.get(clave_detalles, {}))
                    detalles[detalle["nombre"]] = detalle
                    st.session_state[clave_detalles] = detalles
                    st.rerun()
                except (IndexError, ValueError) as error:
                    st.error(str(error))

    activas = set(ofertas.get("oferta", pd.Series(dtype=str)).astype(str))
    for nombre, detalle in st.session_state.get(clave_detalles, {}).items():
        if nombre not in activas:
            continue
        st.warning(
            f"Riesgo SSAA · {nombre}: techo "
            f"{formato_numero_es(detalle['limite_superior_eur_mwh'], 2)} €/MWh; "
            f"ajuste medio equivalente {formato_numero_es(detalle['ajuste_eur_mwh'], 2)} "
            f"€/MWh y sobrecoste mensual acumulado estimado "
            f"{formato_numero_es(detalle['sobrecoste_eur'], 2)} €. "
            "Es una estimación del riesgo, no una liquidación contractual."
        )
        with st.expander(f"Detalle mensual · {nombre}"):
            st.dataframe(
                detalle["detalle_mensual"],
                hide_index=True,
                use_container_width=True,
            )


def render_bloque_ofertas_fijas(
    consumos,
    atr: str,
    clave: str,
    titulo: str = "Ofertas a precio fijo",
    periodos_afectados=None,
    titulo_selector_expander: str | None = None,
) -> pd.DataFrame:
    """Renderiza el bloque completo de ofertas y devuelve las activas con fee."""
    import streamlit as st
    from backend_ofertas_fijas import (
        cargar_catalogo_ofertas,
        ofertas_catalogo_para_atr,
    )

    clave_usuario = f"{clave}_ofertas_usuario"
    clave_eliminadas = f"{clave}_ofertas_eliminadas"
    clave_editor = f"{clave}_editor_ofertas"
    st.subheader(titulo)

    aplicables = periodos_aplicables_atr(atr)
    if periodos_afectados is None:
        exigibles, sin_consumo = periodos_con_consumo(consumos, atr)
    else:
        afectados = {
            str(periodo).strip().upper() for periodo in periodos_afectados
        }
        exigibles = [periodo for periodo in aplicables if periodo in afectados]
        sin_consumo = []
    if sin_consumo:
        st.caption(
            "No se exige precio en periodos sin consumo: "
            + ", ".join(sin_consumo) + "."
        )

    origen = selector_origen_oferta(clave)
    nueva = pd.DataFrame()
    if origen == "Oferta manual":
        nueva = render_oferta_manual(exigibles, f"{clave}_manual")
    elif origen == "Excel":
        archivo = st.file_uploader(
            "Sube el Excel con ofertas de precio fijo",
            type=["xlsx", "xls"],
            key=f"{clave}_excel",
        )
        st.caption("Las columnas P1…P6 deben estar expresadas en €/kWh.")
        if archivo is not None:
            try:
                nueva = normalizar_excel_ofertas(pd.read_excel(archivo))
            except (ValueError, OSError) as error:
                st.error(str(error))
    else:
        nueva = render_oferta_ia(atr, exigibles, f"{clave}_ia")

    if not nueva.empty:
        if "Fee (€/MWh)" not in nueva:
            nueva["Fee (€/MWh)"] = 0.0
        st.session_state[clave_usuario] = combinar_ofertas(
            st.session_state.get(clave_usuario), nueva
        )

    try:
        catalogo = cargar_catalogo_ofertas()
    except ValueError as error:
        catalogo = []
        st.warning(str(error))
    ofertas_catalogo = ofertas_catalogo_para_atr(catalogo, atr)
    ofertas = combinar_ofertas(
        ofertas_catalogo, st.session_state.get(clave_usuario)
    )

    eliminadas = set(st.session_state.get(clave_eliminadas, []))
    if eliminadas and not ofertas.empty:
        ofertas = ofertas.loc[
            ~ofertas["oferta"].astype(str).str.strip().str.casefold().isin(eliminadas)
        ].copy()
    if ofertas.empty:
        st.info(f"Aún no hay ofertas disponibles para {atr}.")
        return pd.DataFrame(columns=["oferta", *PERIODOS, "Fee (€/MWh)"])

    ofertas = ofertas.copy()
    ofertas[PERIODOS] = ofertas[PERIODOS].apply(
        pd.to_numeric, errors="coerce"
    ).fillna(0.0)
    if "Fee (€/MWh)" not in ofertas:
        ofertas["Fee (€/MWh)"] = 0.0
    ofertas["Fee (€/MWh)"] = pd.to_numeric(
        ofertas["Fee (€/MWh)"], errors="coerce"
    ).fillna(0.0)
    periodos_vacios = set(periodos_no_aplicables_atr(atr))
    if periodos_afectados is not None:
        periodos_vacios.update(set(aplicables).difference(afectados))
    ofertas[list(periodos_vacios)] = pd.NA
    editadas = render_selector_ofertas(
        ofertas,
        clave_editor,
        ["oferta", *PERIODOS],
        ["Comparar", "oferta", *PERIODOS, "Fee (€/MWh)"],
        titulo_expander=titulo_selector_expander,
    )

    a_eliminar = st.multiselect(
        "Eliminar ofertas cargadas",
        options=ofertas["oferta"].astype(str).tolist(),
        key=f"{clave}_seleccion_eliminar",
    )
    if st.button(
        "Eliminar de la comparativa",
        key=f"{clave}_eliminar",
        disabled=not a_eliminar,
        use_container_width=True,
    ):
        eliminadas.update(str(n).strip().casefold() for n in a_eliminar)
        st.session_state[clave_eliminadas] = sorted(eliminadas)
        st.rerun()
    if eliminadas and st.button(
        "Restablecer ofertas eliminadas",
        key=f"{clave}_restablecer",
        use_container_width=True,
    ):
        st.session_state[clave_eliminadas] = []
        st.rerun()

    activas = editadas.loc[
        editadas["Comparar"].fillna(False)
    ].drop(columns="Comparar").copy()
    return activas.reset_index(drop=True)
