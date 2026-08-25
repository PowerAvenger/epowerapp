import hashlib

import base64
import re

from html import escape
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from jinja2 import Environment, FileSystemLoader

from backend_comun import aplicar_estilo
from backend_curvadecarga import (
    DatadisLimiteConsultas,
    colores_periodo,
    dataframe_como_archivo_curva,
    obtener_datos_contador,
    obtener_consumo_datadis_cacheado,
    obtener_suministros_datadis,
    rango_meses_datadis,
)
from backend_factura import (
    FacturaError,
    FormatoNoReconocido,
    analizar_factura,
    componentes_grafico,
    componentes_peso_grafico,
    es_servicio_adicional,
    estado_otro_calculo_factura,
    estado_otro_segun_factura,
    extraer_texto_pdf,
    generar_resumen,
    importes_coinciden,
)
from formato_es import (
    formato_eur_kwh,
    formato_eur_mwh,
    formato_euros,
    formato_kwh,
    formato_pct,
    formatear_columnas_tabla,
)
from backend_verificacion_consumos import (
    calcular_energia_indexada,
    calcular_energia_fija,
    calcular_excesos_desde_curva,
    calcular_potencia_confirmada,
    estado_verificacion_energia_real,
    preparar_archivos_factura,
    preparar_curva_factura,
    reconstruir_total_beta,
    tabla_conciliacion_consumos,
)
from utilidades import (
    actualizar_df_index_por_zona,
    generar_menu,
    init_app,
    init_app_index,
    mostrar_parametros_formula_indexado,
    persist_widget,
)
from regulacion_reactiva import (
    FUENTE_REACTIVA,
    LIMITE_REACTIVA_SOBRE_ACTIVA,
    tramos_reactiva,
)
from regulacion_iee import obtener_referencia_iee


generar_menu()

if not st.session_state.get("usuario_autenticado", False) and not st.session_state.get("usuario_free", False):
    st.switch_page("epowerapp.py")

with st.sidebar:
    st.header("🧾 Análisis de factura eléctrica")
    st.caption(
        "Lectura local y sin IA. La consulta externa a Datadis solo se realiza "
        "si la solicitas en la verificación de consumos; las credenciales se "
        "mantienen únicamente durante esta sesión."
    )


VERSION_LECTOR = 134
MOSTRAR_TABLA_MAXIMETROS = False

with st.sidebar:
    st.caption(f"Motor de lectura · v{VERSION_LECTOR}")


@st.cache_data(show_spinner=False)
def procesar_pdf(contenido: bytes, version_lector: int):
    return extraer_texto_pdf(contenido)


def limpiar_factura_sesion():
    """Retira de memoria el PDF y el widget asociado."""
    for clave in (
        "factura_pdf_bytes",
        "factura_pdf_nombre",
        "factura_uploader",
        "factura_comparativa_indexado",
        "factura_verificacion_consumos",
        "factura_suministros_datadis",
    ):
        st.session_state.pop(clave, None)


def _atr_indexado(atr_factura):
    """Traduce el ATR leído al nombre de columna usado por Telemindex."""

    atr = (atr_factura or "").replace(" ", "").upper()
    for candidato in ("2.0", "3.0", "6.1"):
        if atr.startswith(candidato):
            return candidato
    return None


def _fecha_factura(valor):
    fecha = pd.to_datetime(valor, dayfirst=True, errors="coerce")
    return None if pd.isna(fecha) else fecha.date()


def _semaforo_energia_real_sesion(factura, huella):
    """Obtiene el contraste real de energía guardado para esta factura."""
    verificacion = st.session_state.get("factura_verificacion_consumos")
    if not verificacion or verificacion.get("huella") != huella:
        return "🟡"
    resultado = verificacion.get("resultado")
    if resultado is None:
        return "🟡"
    atr = _atr_indexado(factura.atr)
    periodos = tuple(
        f"P{indice}" for indice in range(1, 4 if atr == "2.0" else 7)
    )
    modo = st.session_state.get(
        f"factura_verificacion_tipo_energia_{huella[:8]}", "Fijo"
    )
    if modo == "Indexado":
        try:
            _precios_indexado_periodo(factura)
            _, importe_verificado = calcular_energia_indexada(
                resultado.curva_periodo,
                st.session_state.df_sheets,
                atr,
                resultado.frecuencia,
            )
        except Exception:
            return "🟡"
        fnee_facturado = (
            sum(
                float(item.importe) for item in factura.otros
                if "fnee" in item.concepto.lower()
            )
            if st.session_state.get("cfg_fnee", True) else 0.0
        )
        return estado_verificacion_energia_real(
            float(factura.energia) + fnee_facturado,
            importe_verificado,
            cobertura_completa=bool(resultado.cobertura.get("completa")),
            precios_completos=True,
        )
    else:
        precios_factura = {
            item.periodo: item.precio_eur_kwh
            for item in factura.energia_periodos
            if item.periodo in periodos
        }
        precios = {
            periodo: st.session_state.get(
                f"factura_medida_precio_{periodo}_{huella[:8]}",
                precios_factura.get(periodo),
            )
            for periodo in periodos
        }
    periodos_necesarios = {
        periodo
        for periodo, consumo in resultado.consumos_periodos.items()
        if float(consumo) > 0
    }
    precios_completos = all(
        precios.get(periodo) is not None and float(precios[periodo]) > 0
        for periodo in periodos_necesarios
    )
    _, importe_verificado = calcular_energia_fija(
        resultado.consumos_periodos,
        {periodo: float(precio or 0.0) for periodo, precio in precios.items()},
    )
    return estado_verificacion_energia_real(
        factura.energia,
        importe_verificado,
        cobertura_completa=bool(resultado.cobertura.get("completa")),
        precios_completos=precios_completos,
    )


def _buscar_dato_informe(texto, patrones):
    for patron in patrones:
        coincidencia = re.search(patron, texto, re.IGNORECASE | re.MULTILINE)
        if coincidencia:
            partes = [
                re.sub(r"\s+", " ", parte).strip(" ,-")
                for parte in coincidencia.groups()
                if parte and parte.strip()
            ]
            if partes:
                return ", ".join(partes)
    return ""


def _renderizar_plantilla_informe(contexto, ruta_plantilla):
    ruta = Path(ruta_plantilla)
    if not ruta.is_absolute():
        ruta = Path(__file__).resolve().parent.parent / ruta
    entorno = Environment(loader=FileSystemLoader(str(ruta.parent)))
    return entorno.get_template(ruta.name).render(**contexto)


def _datos_informe_desde_factura(factura, texto):
    """Prepara datos editables sin convertirlos en campos fiscales verificados."""
    cliente = _buscar_dato_informe(texto, [
        r"^Titular\s*:?\s*([^\n]+)$",
        r"^(?:Nombre|Raz[oó]n\s+social)\s*:?\s*([^\n]+)$",
        r"^Cliente\s*:?\s*([^\n]+)$",
    ])
    nif = _buscar_dato_informe(texto, [
        r"^(?:DNI/NIF/NIE|NIF|CIF)\s*:?\s*([A-Z0-9-]+)",
    ])
    direccion = _buscar_dato_informe(texto, [
        r"^Direcci.n\s*:?\s*([^\n]+)\n(\d{5}[^\n]*)$",
        r"^Direcci.n\s*:?\s*([^\n]+)$",
        r"^Direcci.n\s+de\s+suministro\s*:?\s*([^\n]+)$",
    ])
    ciclo = " – ".join(
        valor for valor in (factura.periodo_inicio, factura.periodo_fin) if valor
    )
    return {
        "factura_informe_cliente": cliente,
        "factura_informe_nif": nif,
        "factura_informe_direccion": direccion,
        "factura_informe_cups": factura.cups or "",
        "factura_informe_numero": factura.numero_factura or "",
        "factura_informe_fecha": factura.fecha_factura or "",
        "factura_informe_ciclo": ciclo,
        "factura_informe_comercializadora": factura.comercializadora or "",
        "factura_informe_atr": factura.atr or "",
        "factura_informe_realizado_por": "",
        "factura_informe_fecha_realizacion": (
            pd.Timestamp.today().strftime("%d/%m/%Y")
        ),
        "factura_informe_objeto": (
            "Mejorar las condiciones de contratación del suministro eléctrico "
            "conforme a la propuesta presentada."
        ),
    }


def _firma_formula_indexado():
    return (
        "ponderacion_periodos_v2",
        st.session_state.get("desvios_apant", 1.0),
        st.session_state.get("margen_telemindex", 5.0),
        st.session_state.get("cfg_margen_pos", "tm"),
        st.session_state.get("cfg_fnee", True),
        st.session_state.get("cfg_fnee_pos", "perdidas"),
        st.session_state.get("cf_pct", 0.0),
        st.session_state.get("zona_periodos_index", "peninsula"),
    )


def _factura_parece_indexada(factura, texto):
    """Sugiere indexado sin convertir la heurística en una decisión cerrada."""
    tarifa = " ".join(filter(None, (
        getattr(factura, "tipo_suministro", None),
        getattr(factura, "formato", None),
    )))
    return bool(
        re.search(r"\b(?:indexad[oa]|spot|omie)\b", tarifa, re.IGNORECASE)
        or re.search(
            r"(?:tarifa|producto|modalidad|contrato)[^\n]{0,80}"
            r"\b(?:indexad[oa]|spot|omie)\b",
            texto,
            re.IGNORECASE,
        )
        or re.search(
            r"^ENERG[IÍ]A\s+ACTIVA\s+P[1-6].*?[\d.,]+\s*\*\s+",
            texto,
            re.IGNORECASE | re.MULTILINE,
        )
    )


def _firma_propuesta_energia(atr):
    modo = st.session_state.get("factura_tipo_energia", "Indexado")
    if modo == "Fijo":
        numero_periodos = 3 if atr == "2.0" else 6
        return (
            "energia_fija_v1",
            modo,
            *(
                st.session_state.get(f"factura_precio_fijo_p{i}", 0.0)
                for i in range(1, numero_periodos + 1)
            ),
        )
    medida_sesion = st.session_state.get("factura_verificacion_consumos")
    firma_curva = None
    if medida_sesion and medida_sesion.get("resultado") is not None:
        resultado_medida = medida_sesion["resultado"]
        curva = resultado_medida.curva_periodo
        firma_curva = (
            medida_sesion.get("huella"),
            resultado_medida.frecuencia,
            len(curva),
            round(float(pd.to_numeric(
                curva["consumo_neto_kWh"], errors="coerce"
            ).sum()), 6),
            str(pd.to_datetime(
                curva["fecha_hora"], errors="coerce"
            ).min()),
            str(pd.to_datetime(
                curva["fecha_hora"], errors="coerce"
            ).max()),
        )
    return (
        "energia_indexada_v2_curva",
        modo,
        firma_curva,
        *_firma_formula_indexado(),
    )


def _consumos_factura_por_periodo(factura, periodos_requeridos=None):
    consumos = {}
    periodos_identificados = set()
    periodos_sin_identificar = []
    for item in factura.energia_periodos:
        periodo = str(item.periodo or "").strip().upper()
        if not re.fullmatch(r"P[1-6]", periodo):
            if item.consumo_kwh > 0:
                periodos_sin_identificar.append(
                    str(item.periodo or "Sin periodo")
                )
            continue
        periodos_identificados.add(periodo)
        if item.consumo_kwh <= 0:
            continue
        consumos[periodo] = consumos.get(periodo, 0.0) + item.consumo_kwh

    if periodos_sin_identificar:
        raise ValueError(
            "La factura contiene consumo sin periodos P1…P6 identificables: "
            + ", ".join(periodos_sin_identificar)
            + ". No se aplicará una ponderación aproximada."
        )
    if not consumos:
        raise ValueError("No hay consumos por periodo utilizables para ponderar.")
    if periodos_requeridos:
        faltantes = [
            periodo for periodo in periodos_requeridos
            if periodo not in periodos_identificados
        ]
        if faltantes:
            raise ValueError(
                "La comparativa necesita el consumo real desglosado de "
                + ", ".join(periodos_requeridos)
                + ". Faltan: "
                + ", ".join(faltantes)
                + "."
            )
    return consumos


def _crear_resultado_energia(factura, atr, inicio, fin, consumos, precios, tipo):
    filas = []
    for periodo, consumo in sorted(consumos.items()):
        precio = precios.get(periodo)
        if precio is None or pd.isna(precio) or precio <= 0:
            raise ValueError(f"No hay un precio válido disponible para {periodo}.")
        filas.append(
            {
                "Periodo": periodo,
                "Consumo (kWh)": consumo,
                "Precio propuesta (€/kWh)": precio,
                "Coste propuesta (€)": consumo * precio,
            }
        )

    detalle = pd.DataFrame(filas)
    consumo_total = detalle["Consumo (kWh)"].sum()
    detalle["Peso consumo (%)"] = (
        detalle["Consumo (kWh)"] / consumo_total * 100
    )
    detalle["Precio ponderado (€/kWh)"] = (
        detalle["Coste propuesta (€)"] / consumo_total
    )
    coste_propuesta = detalle["Coste propuesta (€)"].sum()
    coste_facturado = sum(item.coste_eur for item in factura.energia_periodos)

    return {
        "tipo": tipo,
        "atr": atr,
        "inicio": inicio,
        "fin": fin,
        "detalle": detalle,
        "consumo_total": consumo_total,
        "coste_facturado": coste_facturado,
        "coste_indexado": coste_propuesta,
        "precio_facturado": coste_facturado / consumo_total,
        "precio_indexado": coste_propuesta / consumo_total,
        "diferencia": coste_propuesta - coste_facturado,
    }


def _precios_indexado_periodo(factura):
    atr = _atr_indexado(factura.atr)
    if atr is None:
        raise ValueError(
            f"El peaje {factura.atr or 'no detectado'} no está disponible en Telemindex."
        )

    inicio = _fecha_factura(factura.periodo_inicio)
    fin = _fecha_factura(factura.periodo_fin)
    if inicio is None or fin is None or inicio > fin:
        raise ValueError("No se ha podido obtener un periodo de facturación válido.")

    init_app()
    init_app_index()
    actualizar_df_index_por_zona(forzar=True)
    df_index = st.session_state.df_sheets
    fechas = pd.to_datetime(df_index["fecha"], errors="coerce").dt.date
    df_periodo = df_index.loc[(fechas >= inicio) & (fechas <= fin)].copy()

    if df_periodo.empty:
        raise ValueError("No hay datos de indexado para el periodo de la factura.")
    fecha_min = pd.to_datetime(df_periodo["fecha"]).dt.date.min()
    fecha_max = pd.to_datetime(df_periodo["fecha"]).dt.date.max()
    fechas_disponibles = set(pd.to_datetime(df_periodo["fecha"]).dt.date.unique())
    fechas_esperadas = set(pd.date_range(inicio, fin, freq="D").date)
    if (
        fecha_min != inicio
        or fecha_max != fin
        or fechas_esperadas.difference(fechas_disponibles)
    ):
        raise ValueError(
            "Telemindex no dispone todavía del periodo completo: "
            f"{inicio:%d/%m/%Y}–{fin:%d/%m/%Y}."
        )

    columna_periodo = "dh_3p" if atr == "2.0" else "dh_6p"
    columna_precio = f"precio_{atr}"
    precios = (
        df_periodo.assign(
            _periodo=df_periodo[columna_periodo].astype(str).str.extract(r"(\d+)")[0]
        )
        .assign(_periodo=lambda df: "P" + df["_periodo"])
        .groupby("_periodo", observed=False)[columna_precio]
        .mean()
        .div(1000)
    ).to_dict()
    return atr, inicio, fin, precios


def _calcular_comparativa_indexado(factura, resultado_medida=None):
    atr, inicio, fin, precios = _precios_indexado_periodo(factura)
    if resultado_medida is not None:
        detalle, coste_propuesta = calcular_energia_indexada(
            resultado_medida.curva_periodo,
            st.session_state.df_sheets,
            atr,
            resultado_medida.frecuencia,
        )
        detalle = detalle.rename(columns={
            "Consumo medida (kWh)": "Consumo (kWh)",
            "Precio verificación (€/kWh)": "Precio propuesta (€/kWh)",
            "Coste verificado (€)": "Coste propuesta (€)",
        })
        consumo_total = detalle["Consumo (kWh)"].sum()
        detalle["Peso consumo (%)"] = (
            detalle["Consumo (kWh)"] / consumo_total * 100
        )
        detalle["Precio ponderado (€/kWh)"] = (
            detalle["Coste propuesta (€)"] / consumo_total
        )
        coste_facturado = sum(
            item.coste_eur for item in factura.energia_periodos
        )
        return {
            "tipo": "Indexado · curva real",
            "atr": atr,
            "inicio": inicio,
            "fin": fin,
            "detalle": detalle,
            "consumo_total": consumo_total,
            "coste_facturado": coste_facturado,
            "coste_indexado": coste_propuesta,
            "precio_facturado": coste_facturado / consumo_total,
            "precio_indexado": coste_propuesta / consumo_total,
            "diferencia": coste_propuesta - coste_facturado,
            "metodo_calculo": "curva_horaria",
        }
    consumos = _consumos_factura_por_periodo(factura)
    resultado = _crear_resultado_energia(
        factura, atr, inicio, fin, consumos, precios, "Indexado"
    )
    resultado["metodo_calculo"] = "consumo_agregado_periodos"
    return resultado


def _calcular_comparativa_fijo(factura):
    atr = _atr_indexado(factura.atr)
    if atr is None:
        raise ValueError(
            f"El peaje {factura.atr or 'no detectado'} no admite esta comparativa."
        )
    numero_periodos = 3 if atr == "2.0" else 6
    precios = {
        f"P{i}": st.session_state.get(f"factura_precio_fijo_p{i}", 0.0)
        for i in range(1, numero_periodos + 1)
    }
    try:
        consumos = _consumos_factura_por_periodo(factura)
    except ValueError as exc:
        precio_unico = (
            all(precio > 0 for precio in precios.values())
            and
            len({round(precio, 9) for precio in precios.values()}) == 1
        )
        if not precio_unico:
            raise ValueError(
                f"{exc} Para comparar sin desglose por periodos, introduce "
                f"el mismo precio fijo en las {numero_periodos} casillas."
            ) from exc
        consumo_total = factura.consumo_total_kwh
        if consumo_total <= 0:
            raise ValueError(
                "La factura no contiene un consumo total utilizable."
            ) from exc
        consumos = {"Precio único": consumo_total}
        precios = {"Precio único": next(iter(precios.values()))}
    else:
        periodos_sin_precio = [
            periodo
            for periodo in consumos
            if precios.get(periodo, 0.0) <= 0
        ]
        if periodos_sin_precio:
            raise ValueError(
                "Introduce un precio fijo mayor que cero únicamente en los "
                "periodos con consumo: " + ", ".join(periodos_sin_precio) + "."
            )
    return _crear_resultado_energia(
        factura,
        atr,
        _fecha_factura(factura.periodo_inicio),
        _fecha_factura(factura.periodo_fin),
        consumos,
        precios,
        "Fijo",
    )


def _coste_potencia_propuesta(factura):
    modo = st.session_state.get(
        "factura_modo_precio_potencia", "Aplicar precios BOE"
    )
    if modo == "Mantener precios de factura":
        return factura.potencia
    if not factura.potencia_periodos or any(
        item.coste_boe_eur <= 0 for item in factura.potencia_periodos
    ):
        return None

    coste_boe = sum(item.coste_boe_eur for item in factura.potencia_periodos)
    if modo == "Aplicar precios BOE":
        return round(coste_boe, 2)

    margen_anual = st.session_state.get(
        "factura_margen_potencia_personalizado", 0.0
    )
    coste_margen = sum(
        item.potencia_kw * item.dias * margen_anual / 365
        for item in factura.potencia_periodos
    )
    return round(coste_boe + coste_margen, 2)


def _margen_potencia_propuesta(factura):
    if (
        st.session_state.get(
            "factura_modo_precio_potencia", "Aplicar precios BOE"
        )
        != "Personalizar con margen"
    ):
        return 0.0
    margen_anual = st.session_state.get(
        "factura_margen_potencia_personalizado", 0.0
    )
    return sum(
        item.potencia_kw * item.dias * margen_anual / 365
        for item in factura.potencia_periodos
    )


def _parametros_iee_propuesta(factura):
    """Obtiene una base de IEE contrastada, aunque no venga desglosada."""
    if factura.verificacion_iee:
        verificacion = factura.verificacion_iee
        return (
            verificacion.base_eur,
            verificacion.tipo_pct,
            verificacion.minimo_eur_mwh,
        )

    fecha = _fecha_factura(factura.fecha_factura or factura.periodo_fin)
    referencia = (
        obtener_referencia_iee(fecha, factura.atr) if fecha else None
    )
    if not referencia or not factura.iee:
        return None

    bases_candidatas = []
    if factura.verificacion_iva:
        bases_candidatas.append(
            factura.verificacion_iva.base_eur - factura.iee
        )
    bases_candidatas.append(
        factura.suma_componentes - factura.iee - factura.iva
    )
    minimo_iee = (
        factura.consumo_total_kwh
        / 1000
        * referencia.minimo_eur_mwh
    )
    for base_iee in bases_candidatas:
        if base_iee <= 0:
            continue
        importe_reconstruido = round(max(
            base_iee * referencia.tipo_pct / 100,
            minimo_iee,
        ), 2)
        if importes_coinciden(
            factura.iee, importe_reconstruido, "componentes"
        ):
            return (
                base_iee,
                referencia.tipo_pct,
                referencia.minimo_eur_mwh,
            )
    return None


def _componentes_propuesta(factura, resultado_energia):
    potencia_propuesta = _coste_potencia_propuesta(factura)
    energia_propuesta = resultado_energia["coste_indexado"]
    fnee_integrado = (
        sum(
            float(item.importe)
            for item in factura.otros
            if "fnee" in item.concepto.lower()
        )
        if (
            str(resultado_energia.get("tipo", "")).lower().startswith("indexado")
            and st.session_state.get("cfg_fnee", False)
        )
        else 0.0
    )
    otros_propuesta = factura.total_otros - fnee_integrado
    if potencia_propuesta is None:
        diferencia_base = None
    else:
        diferencia_base = (
            potencia_propuesta
            - factura.potencia
            + energia_propuesta
            - factura.energia
            + otros_propuesta
            - factura.total_otros
        )

    iee_propuesta = None
    parametros_iee = _parametros_iee_propuesta(factura)
    if diferencia_base is not None and parametros_iee:
        base_factura_iee, tipo_iee, minimo_eur_mwh = parametros_iee
        base_iee = max(base_factura_iee + diferencia_base, 0.0)
        iee_propuesta = base_iee * tipo_iee / 100
        if minimo_eur_mwh is not None:
            minimo_iee = (
                factura.consumo_total_kwh
                / 1000
                * minimo_eur_mwh
            )
            iee_propuesta = max(iee_propuesta, minimo_iee)
        iee_propuesta = round(iee_propuesta, 2)

    iva_propuesta = None
    verificacion_iva = factura.verificacion_iva
    if diferencia_base is not None and verificacion_iva:
        variacion_iee = (
            iee_propuesta - factura.iee
            if iee_propuesta is not None
            else 0.0
        )
        base_iva = max(
            verificacion_iva.base_eur + diferencia_base + variacion_iee,
            0.0,
        )
        iva_propuesta = round(
            base_iva * verificacion_iva.tipo_pct / 100, 2
        )

    valores_propuesta = {
        "Potencia": (
            potencia_propuesta
            if potencia_propuesta is not None
            else factura.potencia
        ),
        "Energía": energia_propuesta,
        "Excesos": factura.excesos_potencia,
        "Reactiva": factura.reactiva,
        "Otros": otros_propuesta,
        "IEE": iee_propuesta if iee_propuesta is not None else factura.iee,
        "IVA": iva_propuesta if iva_propuesta is not None else factura.iva,
    }
    comparativa = pd.DataFrame(
        [
            {
                "Componente": item["Componente"],
                "Factura (€)": item["Importe (€)"],
                "Propuesta (€)": valores_propuesta.get(
                    item["Componente"], item["Importe (€)"]
                ),
            }
            for item in componentes_grafico(factura)
        ]
    )
    comparativa["Diferencia (€)"] = (
        comparativa["Propuesta (€)"] - comparativa["Factura (€)"]
    )
    comparativa["Diferencia (%)"] = comparativa.apply(
        lambda fila: (
            fila["Diferencia (€)"] / fila["Factura (€)"] * 100
            if fila["Factura (€)"]
            else None
        ),
        axis=1,
    )
    return comparativa


def _estilar_diferencias_comparativa(tabla_numerica):
    """Formatea la tabla y colorea las diferencias según su signo."""
    tabla_formateada = formatear_columnas_tabla(
        tabla_numerica,
        columnas_euros=[
            "Factura (€)", "Propuesta (€)", "Diferencia (€)",
        ],
        columnas_pct=["Diferencia (%)"],
        incluir_unidades=True,
    )
    estilos = pd.DataFrame(
        "", index=tabla_formateada.index, columns=tabla_formateada.columns
    )
    for columna in ("Diferencia (€)", "Diferencia (%)"):
        for indice, valor in tabla_numerica[columna].items():
            if pd.isna(valor) or abs(valor) < 0.005:
                continue
            color = "#00c853" if valor < 0 else "#ef4444"
            estilos.loc[indice, columna] = (
                f"color: {color}; font-weight: 700;"
            )
    return tabla_formateada.style.apply(lambda _: estilos, axis=None)


tab_analisis, tab_verificacion, tab_comparativa, tab_informe = st.tabs(
    ["Análisis", "Verificación", "Propuesta", "Informe"]
)

with tab_analisis:
    col_entrada, col_detalle, col_grafico = st.columns([0.26, 0.30, 0.44])

factura = None
huella = None
resultado = None
figura_componentes = None

with col_entrada:
    st.subheader("Suelta aquí tu factura", divider="rainbow")
    archivo = st.file_uploader(
        "Arrastra una factura PDF",
        type=["pdf"],
        accept_multiple_files=False,
        key="factura_uploader",
    )
    if archivo is not None:
        st.session_state.factura_pdf_bytes = archivo.getvalue()
        st.session_state.factura_pdf_nombre = archivo.name

    contenido = st.session_state.get("factura_pdf_bytes")
    if contenido is not None:
        nombre_factura = st.session_state.get("factura_pdf_nombre", "Factura PDF")
        st.caption(f"En memoria durante esta sesión: {nombre_factura}")
        st.button(
            "Quitar factura",
            on_click=limpiar_factura_sesion,
            use_container_width=True,
        )
        st.subheader("Resumen", divider="rainbow")

if contenido is not None:
    huella = hashlib.sha256(contenido).hexdigest()

    try:
        texto, numero_paginas = procesar_pdf(contenido, VERSION_LECTOR)
        factura = analizar_factura(texto)
    except FormatoNoReconocido as exc:
        with col_entrada:
            st.warning(str(exc))
            st.info(
                "El PDF se ha podido leer, pero no hay un extractor para este formato. "
                "El texto sirve para preparar un nuevo patrón sin usar IA."
            )
        with col_detalle:
            with st.expander("Ver texto extraído para diagnóstico"):
                st.text(texto)
    except FacturaError as exc:
        with col_entrada:
            st.error(str(exc))
    except Exception as exc:
        with col_entrada:
            st.error(f"No se ha podido completar la lectura: {exc}")
    else:
        es_20td = (factura.atr or "").replace(" ", "").upper() == "2.0TD"
        reconstruccion_total_completa = factura.reconstruccion_total_completa
        verificacion_total_ok = reconstruccion_total_completa and importes_coinciden(
            factura.total,
            factura.total_calculado_segun_factura,
            "total_factura",
        )
        cups_mostrado = (
            f"{factura.cups[:6]}…{factura.cups[-4:]}"
            if factura.cups and len(factura.cups) > 12
            else factura.cups or "No detectado"
        )

        with col_entrada:
            st.success(
                f"Formato: {factura.comercializadora} · {numero_paginas} página(s)"
            )
            st.info(generar_resumen(factura))
            st.caption(
                "🛠️ Uso interno · Control de extracción: "
                f"componentes {formato_euros(factura.suma_componentes)} · "
                f"diferencia con total PDF {formato_euros(factura.diferencia)}."
            )
            potencia_verificada = any(
                item.resultado != "No verificado"
                for item in factura.potencia_periodos
            )
            if factura.sobrecoste_potencia > 0:
                st.warning(
                    "⚠️ Sobrecoste neto en el término de potencia: "
                    f"{formato_euros(factura.sobrecoste_potencia)} "
                    f"({formato_pct(factura.porcentaje_sobrecoste_potencia, 1)} "
                    "del término facturado)."
                )
            elif factura.sobrecoste_potencia < 0:
                st.success(
                    "✅ El término de potencia presenta un ahorro neto frente a BOE de "
                    f"{formato_euros(abs(factura.sobrecoste_potencia))} "
                    f"({formato_pct(abs(factura.porcentaje_sobrecoste_potencia), 1)} "
                    "del término facturado)."
                )
            elif potencia_verificada:
                st.success("✅ Término de potencia sin sobrecoste sobre BOE.")
            else:
                st.info("ℹ️ Término de potencia no verificable con los datos extraídos.")

            if factura.excesos_potencia:
                st.warning(
                    "⚠️ La factura incluye excesos de potencia: "
                    f"{formato_euros(factura.excesos_potencia)}."
                )
            else:
                st.info(
                    "ℹ️ La factura no incluye excesos de potencia."
                    + (
                        " Para este suministro 2.0TD se asume control por ICP, "
                        "salvo que las condiciones contractuales indiquen modo excesos."
                        if es_20td else ""
                    )
                )

            if not es_20td:
                if factura.reactiva:
                    st.error(
                        "🔴 La factura incluye penalización por energía reactiva: "
                        f"{formato_euros(factura.reactiva)}."
                    )
                else:
                    st.success(
                        "✅ La factura no incluye penalización por energía reactiva."
                    )

            servicios_adicionales = [
                item for item in factura.otros
                if es_servicio_adicional(item)
            ]
            if servicios_adicionales:
                total_servicios = round(sum(
                    item.importe for item in servicios_adicionales
                ), 2)
                st.error(
                    "🔴 Servicios adicionales contratados: "
                    + ", ".join(item.concepto for item in servicios_adicionales)
                    + ". Importe antes de impuestos: "
                    + formato_euros(total_servicios)
                    + ". Conviene revisar si siguen siendo necesarios."
                )

            factura_alquiler_medida = any(
                "alquiler" in item.concepto.lower()
                for item in factura.otros
            )
            if not factura_alquiler_medida:
                st.info(
                    "ℹ️ No se ha detectado alquiler de equipos de medida en la factura. "
                    "La telemedida puede facturarse por otra vía."
                )

            if factura.fecha_vencimiento_contrato:
                vencimiento_fecha = pd.to_datetime(
                    factura.fecha_vencimiento_contrato,
                    format="%d/%m/%Y",
                    errors="coerce",
                )
                if not pd.isna(vencimiento_fecha):
                    hoy = pd.Timestamp.today().normalize()
                    limite_aviso = hoy + pd.DateOffset(months=2)
                    if vencimiento_fecha < hoy:
                        dias_caducado = (hoy - vencimiento_fecha).days
                        st.markdown(
                            "<div style='background:#6f1d2c;color:#fff;"
                            "border-left:5px solid #3f0d18;border-radius:8px;"
                            "padding:12px 14px;margin:8px 0;'>"
                            "⛔ <b>Contrato vencido:</b> finalizó el "
                            f"{escape(factura.fecha_vencimiento_contrato)} "
                            f"(hace {dias_caducado} días)."
                            "</div>",
                            unsafe_allow_html=True,
                        )
                    elif vencimiento_fecha <= limite_aviso:
                        dias_restantes = (vencimiento_fecha - hoy).days
                        st.warning(
                            "⚠️ Vencimiento contractual próximo: "
                            f"{factura.fecha_vencimiento_contrato} "
                            f"({dias_restantes} días restantes)."
                        )

            if factura.permanencia is False:
                st.success(
                    "✅ La factura indica que el contrato no tiene permanencia."
                )
            elif factura.permanencia is True:
                st.warning(
                    "⚠️ La factura indica que el contrato tiene permanencia."
                )

            col_total_factura, col_resultado_factura = st.columns(2)
            col_total_factura.metric("Total factura", formato_euros(factura.total))
            if reconstruccion_total_completa:
                col_resultado_factura.metric(
                    "Resultado verificación",
                    "✅" if verificacion_total_ok else "❌",
                )
            else:
                col_resultado_factura.metric("Resultado verificación", "?")

            factura_numero = escape(str(factura.numero_factura or "No detectada"))
            fecha_factura = escape(str(factura.fecha_factura or "No detectada"))
            vencimiento = escape(
                str(factura.fecha_vencimiento_contrato or "No detectado")
            )
            permanencia = (
                "No" if factura.permanencia is False
                else "Sí" if factura.permanencia is True
                else "No detectada"
            )
            periodo_inicio = escape(str(factura.periodo_inicio or "?"))
            periodo_fin = escape(str(factura.periodo_fin or "?"))
            cups_html = escape(str(cups_mostrado))
            atr_html = escape(str(factura.atr or "No detectado"))
            suministro_html = escape(
                str(factura.tipo_suministro or "No detectado")
            )
            col_total_factura.markdown(
                f"""
                <div style="background:rgba(236,72,153,.10); border-left:4px solid #ec4899;
                            border-radius:8px; padding:12px 14px; margin:8px 0;
                            height:215px; box-sizing:border-box;">
                    <div style="color:#db2777; font-size:1.45rem; font-weight:700;
                                margin-bottom:7px;">Datos del contrato</div>
                    <div style="font-size:1.02rem; line-height:1.65;">
                        <b>Factura:</b> {factura_numero}<br>
                        <b>Fecha de factura:</b> {fecha_factura}<br>
                        <b>Vencimiento:</b> {vencimiento}<br>
                        <b>Permanencia:</b> {permanencia}<br>
                        <b>Periodo:</b> {periodo_inicio} - {periodo_fin}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            col_resultado_factura.markdown(
                f"""
                <div style="background:rgba(249,115,22,.11); border-left:4px solid #f97316;
                            border-radius:8px; padding:12px 14px; margin:8px 0;
                            height:215px; box-sizing:border-box;">
                    <div style="color:#ea580c; font-size:1.45rem; font-weight:700;
                                margin-bottom:7px;">Datos del suministro</div>
                    <div style="font-size:1.02rem; line-height:1.65;">
                        <b>CUPS:</b> {cups_html}<br>
                        <b>ATR/Peaje:</b> {atr_html}<br>
                        <b>Tipo de suministro:</b> {suministro_html}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if not reconstruccion_total_completa:
                col_resultado_factura.markdown(
                    "<style>"
                    ":is([data-testid='column'],[data-testid='stColumn']):has("
                    ".metric-no-verificable-marker) "
                    "[data-testid='stMetricValue'],"
                    ":is([data-testid='column'],[data-testid='stColumn']):has("
                    ".metric-no-verificable-marker) "
                    "[data-testid='stMetricValue'] * "
                    "{color:#f59e0b !important;}"
                    "</style>"
                    "<span class='metric-no-verificable-marker' "
                    "style='display:none'></span>",
                    unsafe_allow_html=True,
                )
        componentes = componentes_grafico(factura, texto)
        semaforo_energia_real = _semaforo_energia_real_sesion(factura, huella)
        for componente in componentes:
            if componente["Componente"] == "Energía":
                componente["Verificación real"] = semaforo_energia_real
                break
        df_componentes = pd.DataFrame(componentes)
        semaforos_reales = {
            item["Componente"]: item["Verificación real"]
            for item in componentes
        }
        semaforos_factura = {
            item["Componente"]: item["Verif s/cálculo"]
            for item in componentes
        }

        def etiqueta_expander(componente, texto_etiqueta):
            return f"{semaforos_factura.get(componente, '🔵')} {texto_etiqueta}"

        with col_detalle:
            if not df_componentes.empty:
                st.subheader(
                    "Comprobación cálculo coste factura",
                    divider="rainbow",
                    help=(
                        "El análisis se realiza sobre los datos contenidos en la "
                        "factura, incluyendo la comprobación de los componentes "
                        "regulados y normativos aplicables."
                    ),
                )
                if reconstruccion_total_completa:
                    resultado_texto = (
                        "CORRECTO" if verificacion_total_ok else "INCORRECTO"
                    )
                    resultado_icono = "✓" if verificacion_total_ok else "✕"
                    resultado_color = (
                        "#00c853" if verificacion_total_ok else "#ef4444"
                    )
                    resultado_fondo = (
                        "rgba(0,200,83,.12)"
                        if verificacion_total_ok else "rgba(239,68,68,.12)"
                    )
                    resultado_borde = (
                        "rgba(0,200,83,.55)"
                        if verificacion_total_ok else "rgba(239,68,68,.55)"
                    )
                else:
                    resultado_texto = "NO VERIFICABLE"
                    resultado_icono = "?"
                    resultado_color = "#f59e0b"
                    resultado_fondo = "rgba(100,116,139,.12)"
                    resultado_borde = "rgba(100,116,139,.5)"
                st.markdown(
                    "<div style='display:flex;align-items:center;justify-content:"
                    "space-between;gap:1rem;flex-wrap:wrap;margin:1rem 0 .8rem 0;"
                    f"padding:.8rem 1rem;border:1px solid {resultado_borde};"
                    f"border-radius:1rem;background:{resultado_fondo};"
                    "box-shadow:0 4px 14px rgba(0,0,0,.10);'>"
                    "<div style='display:flex;align-items:baseline;flex-wrap:wrap;"
                    "font-size:1.55rem;font-weight:700;line-height:1.2;'>"
                    "<span style='font-size:1.35rem;'>El resultado de la "
                    "verificación es:</span>"
                    f"<span style='color:{resultado_color};font-size:1.9rem;"
                    "margin-left:.8rem;'>"
                    f"{resultado_texto}</span></div>"
                    "<div style='display:flex;align-items:center;justify-content:center;"
                    "width:3.7rem;height:3.7rem;flex:0 0 3.7rem;"
                    "background:transparent;font-size:2.8rem;"
                    f"line-height:1;color:{resultado_color};font-weight:800;'>"
                    f"{resultado_icono}</div></div>",
                    unsafe_allow_html=True,
                )
                if not reconstruccion_total_completa:
                    if abs(factura.total - factura.suma_componentes) <= 0.05:
                        st.success(
                            "🧮 La suma aritmética de los componentes extraídos "
                            "coincide con el total de la factura: "
                            f"{formato_euros(factura.total)}."
                        )
                    motivos_no_verificable = []
                    if not importes_coinciden(
                        factura.total, factura.suma_componentes, "total_factura"
                    ):
                        motivos_no_verificable.append(
                            "los componentes extraídos no reconstruyen el total"
                        )
                    if factura.potencia and (
                        not factura.potencia_periodos
                        or any(
                            item.resultado == "No verificado"
                            for item in factura.potencia_periodos
                        )
                    ):
                        motivos_no_verificable.append(
                            "el término de potencia no tiene detalle verificable"
                        )
                    if factura.energia and not factura.energia_periodos:
                        motivos_no_verificable.append(
                            "el término de energía no tiene detalle verificable"
                        )
                    if factura.excesos_potencia and not factura.excesos_verificados:
                        motivos_no_verificable.append(
                            factura.verificacion_excesos
                            or "los excesos no tienen detalle verificable"
                        )
                    if factura.reactiva and not factura.reactiva_periodos:
                        motivos_no_verificable.append(
                            "la reactiva no tiene detalle por periodos"
                        )
                    if factura.iee and (
                        not factura.verificacion_iee
                        or factura.verificacion_iee.importe_regulado_eur is None
                    ):
                        motivos_no_verificable.append(
                            "el IEE no dispone de referencia regulatoria"
                        )
                    if factura.iva and (
                        not factura.verificacion_iva
                        or factura.verificacion_iva.importe_regulado_eur is None
                    ):
                        motivos_no_verificable.append(
                            "el IVA no dispone de referencia regulatoria"
                        )
                    detalle_no_verificable = "; ".join(motivos_no_verificable)
                    st.info(
                        "ℹ️ No se puede completar la verificación: "
                        + (detalle_no_verificable or
                           "faltan datos suficientes en la factura")
                        + "."
                    )
                estados_otros = [
                    (item, estado_otro_segun_factura(factura, texto, item))
                    for item in factura.otros
                ]
                otros_pendientes = [
                    item.concepto for item, estado in estados_otros
                    if estado == "🟡"
                ]
                otros_incorrectos = [
                    item.concepto for item, estado in estados_otros
                    if estado == "🔴"
                ]
                col_total_pdf, col_total_calculado, col_diferencia = st.columns(3)
                col_total_pdf.metric(
                    "Total extraído factura", formato_euros(factura.total)
                )
                col_total_calculado.metric(
                    "Total verificado (referencias)",
                    formato_euros(factura.total_calculado_segun_factura)
                    if reconstruccion_total_completa else "No verificable",
                )
                col_diferencia.metric(
                    "Diferencia",
                    formato_euros(factura.diferencia_total_calculado)
                    if reconstruccion_total_completa else "No disponible",
                )
                if (
                    reconstruccion_total_completa
                    and abs(factura.diferencia_total_calculado) >= 0.005
                ):
                    origenes_diferencia = []
                    if not importes_coinciden(
                        factura.total,
                        factura.suma_componentes,
                        "total_factura",
                    ):
                        if factura.diferencia > 0:
                            origenes_diferencia.append(
                                f"{formato_euros(factura.diferencia)} del total "
                                "todavía no están asignados a ningún componente extraído"
                            )
                        else:
                            origenes_diferencia.append(
                                "los componentes extraídos superan el total en "
                                f"{formato_euros(abs(factura.diferencia))}"
                            )
                    if factura.verificacion_fnee and (
                        factura.verificacion_fnee.importe_referencia_eur is not None
                    ):
                        delta = round(
                            factura.verificacion_fnee.importe_facturado_eur
                            - factura.verificacion_fnee.importe_referencia_eur,
                            2,
                        )
                        if abs(delta) > 0.02:
                            origenes_diferencia.append(
                                f"FNEE: {formato_euros(delta)} frente a referencia"
                            )
                    if factura.verificacion_fbs and (
                        factura.verificacion_fbs.importe_regulado_eur is not None
                    ):
                        delta = round(
                            factura.verificacion_fbs.importe_facturado_eur
                            - factura.verificacion_fbs.importe_regulado_eur,
                            2,
                        )
                        if abs(delta) > 0.02:
                            origenes_diferencia.append(
                                f"FBS: {formato_euros(delta)} frente a referencia"
                            )
                    for nombre, verificacion in (
                        ("IEE", factura.verificacion_iee),
                        ("IVA", factura.verificacion_iva),
                    ):
                        if verificacion and verificacion.importe_regulado_eur is not None:
                            delta = round(
                                verificacion.importe_facturado_eur
                                - verificacion.importe_regulado_eur,
                                2,
                            )
                            if abs(delta) > 0.02:
                                origenes_diferencia.append(
                                    f"{nombre}: {formato_euros(delta)} frente a referencia"
                                )
                    delta_reactiva = round(
                        factura.reactiva
                        - sum(
                            item.coste_calculado_eur
                            for item in factura.reactiva_periodos
                        ),
                        2,
                    ) if factura.reactiva_periodos else 0.0
                    if abs(delta_reactiva) > 0.02:
                        origenes_diferencia.append(
                            "Reactiva: "
                            f"{formato_euros(delta_reactiva)} frente al cálculo"
                        )
                    detalle_origen = "; ".join(origenes_diferencia) or (
                        "la diferencia procede de redondeos o ajustes de los "
                        "componentes reconstruidos"
                    )
                    dentro_margen = importes_coinciden(
                        factura.total,
                        factura.total_calculado_segun_factura,
                        "total_factura",
                    )
                    prefijo = (
                        "Diferencia dentro del margen admitido. "
                        if dentro_margen else ""
                    )
                    st.warning(
                        "💶 " + prefijo + "Origen de la diferencia: "
                        + detalle_origen + "."
                    )
                if verificacion_total_ok and otros_pendientes:
                    st.warning(
                        "🔎 El cálculo de la factura es correcto, pero falta "
                        "comprobar con la documentación del usuario: "
                        + ", ".join(otros_pendientes) + "."
                    )
                if verificacion_total_ok and otros_incorrectos:
                    st.error(
                        "Aunque el total queda reconstruido, presentan discrepancias: "
                        + ", ".join(otros_incorrectos) + "."
                    )
                st.subheader("Componentes", divider="rainbow")
                st.dataframe(
                    formatear_columnas_tabla(
                        df_componentes,
                        columnas_euros=["Importe (€)"],
                        incluir_unidades=True,
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
                st.caption(
                    "Verif s/factura: cuadre de los importes extraídos con el total · "
                    "Verif s/cálculo: reproducción del importe con su detalle o fórmula · "
                    "Verificación real: contraste regulatorio, contractual o externo. "
                    "🟢 Verificado · 🔴 No coincide · "
                    "🟢 ⚠️ Desvío favorable · 🟡 Sin datos suficientes · "
                    "🔵 No facturado"
                )
                st.subheader("Peso de los componentes", divider="rainbow")
                df_peso_componentes = pd.DataFrame(
                    componentes_peso_grafico(factura)
                )
                if not df_peso_componentes.empty:
                    figura = px.pie(
                        df_peso_componentes,
                        names="Componente",
                        values="Importe (€)",
                        hole=0.42,
                    )
                    figura.update_traces(textinfo="percent+label")
                    st.plotly_chart(figura, use_container_width=True)
                    if any(item.importe < 0 for item in factura.otros):
                        st.caption(
                            "Los abonos se imputan visualmente primero a Energía y "
                            "después a Potencia; la tabla conserva los importes reales."
                        )
                else:
                    st.info(
                        "No hay importe neto positivo que representar en el gráfico."
                    )

            if MOSTRAR_TABLA_MAXIMETROS and factura.maximetros:
                st.subheader("Maxímetros", divider="rainbow")
                df_maximetros = pd.DataFrame(
                        [
                            {
                                "Periodo": item.periodo,
                                "Potencia máxima (kW)": item.potencia_kw,
                            }
                            for item in factura.maximetros
                        ]
                    )
                st.dataframe(
                    formatear_columnas_tabla(
                        df_maximetros,
                        columnas_kw=["Potencia máxima (kW)"],
                        decimales_kw=2,
                    ),
                    hide_index=True,
                    use_container_width=True,
                )

        with col_grafico:
            st.subheader("Detalle de componentes", divider="rainbow")
            alerta_potencia = (
                factura.sobrecoste_potencia > 0
                or semaforos_reales.get("Potencia") == "🔴"
            )
            etiqueta_potencia = etiqueta_expander(
                "Potencia",
                f"{'⚠️ ' if alerta_potencia else ''}Potencia facturada",
            )
            with st.expander(etiqueta_potencia):
                if factura.potencia_periodos:
                    potencia_facturada_por_meses = all(
                        item.meses is not None
                        and item.precio_facturado_eur_kw_mes is not None
                        for item in factura.potencia_periodos
                    )
                    tramos_detectados = sorted({
                        (item.periodo_inicio, item.periodo_fin)
                        for item in factura.potencia_periodos
                        if item.periodo_inicio and item.periodo_fin
                    })
                    if tramos_detectados:
                        filas_potencias_tramos = []
                        for numero_tramo, (inicio_tramo, fin_tramo) in enumerate(
                            tramos_detectados, start=1
                        ):
                            fila_tramo = {
                                "Tramo": f"Tramo {numero_tramo}",
                                "Periodo facturado": (
                                    f"{inicio_tramo} – {fin_tramo}"
                                ),
                            }
                            for item in factura.potencia_periodos:
                                if (
                                    item.periodo_inicio == inicio_tramo
                                    and item.periodo_fin == fin_tramo
                                ):
                                    fila_tramo[item.periodo] = item.potencia_kw
                            filas_potencias_tramos.append(fila_tramo)
                        df_potencias_tramos = pd.DataFrame(
                            filas_potencias_tramos,
                            columns=[
                                "Tramo", "Periodo facturado",
                                "P1", "P2", "P3", "P4", "P5", "P6",
                            ],
                        )
                        st.markdown("#### Potencias contratadas por tramo")
                        st.dataframe(
                            formatear_columnas_tabla(
                                df_potencias_tramos,
                                columnas_kw=[
                                    "P1", "P2", "P3", "P4", "P5", "P6"
                                ],
                                decimales_kw=3,
                                incluir_unidades=False,
                            ),
                            hide_index=True,
                            use_container_width=True,
                        )
                    df_potencia = pd.DataFrame(
                        [
                            ({
                                "Periodo": item.periodo,
                                "Potencia (kW)": item.potencia_kw,
                                "Meses": item.meses,
                                "Precio factura (€/kW mes)": (
                                    item.precio_facturado_eur_kw_mes
                                ),
                                "Precio BOE (€/kW día)": item.precio_boe_eur_kw_dia or None,
                                "Coste factura (€)": item.coste_facturado_eur,
                                "Coste BOE (€)": item.coste_boe_eur or None,
                                "Sobrecoste (€)": item.sobrecoste_eur,
                                "Resultado": (
                                    "🟢 BOE" if item.resultado == "BOE"
                                    else "🟢 ⚠️ Inferior a BOE"
                                    if item.resultado == "Inferior a BOE"
                                    else "⚠️ Superior a BOE"
                                    if item.resultado == "Superior a BOE"
                                    else "No verificado"
                                ),
                            } if potencia_facturada_por_meses else {
                                "Periodo": item.periodo,
                                "Potencia (kW)": item.potencia_kw,
                                "Días": item.dias,
                                "Precio factura (€/kW día)": item.precio_facturado_eur_kw_dia,
                                "Precio BOE (€/kW día)": item.precio_boe_eur_kw_dia or None,
                                "Coste factura (€)": item.coste_facturado_eur,
                                "Coste BOE (€)": item.coste_boe_eur or None,
                                "Sobrecoste (€)": item.sobrecoste_eur,
                                "Resultado": (
                                    "🟢 BOE" if item.resultado == "BOE"
                                    else "🟢 ⚠️ Inferior a BOE"
                                    if item.resultado == "Inferior a BOE"
                                    else "⚠️ Superior a BOE"
                                    if item.resultado == "Superior a BOE"
                                    else "No verificado"
                                ),
                            })
                            for item in factura.potencia_periodos
                        ]
                    )
                    st.dataframe(
                        formatear_columnas_tabla(
                            df_potencia,
                            columnas_kw=["Potencia (kW)"],
                            columnas_eur_kw_dia=[
                                "Precio factura (€/kW día)",
                                "Precio BOE (€/kW día)",
                            ],
                            columnas_eur_kw_mes=[
                                "Precio factura (€/kW mes)",
                            ],
                            columnas_euros=[
                                "Coste factura (€)", "Coste BOE (€)", "Sobrecoste (€)"
                            ],
                            decimales_kw=3,
                            incluir_unidades=False,
                        ),
                        hide_index=True,
                        use_container_width=True,
                    )
                    potencia_desglosada = round(sum(
                        item.coste_facturado_eur
                        for item in factura.potencia_periodos
                    ), 2)
                    if abs(potencia_desglosada - factura.potencia) <= 0.02:
                        st.success(
                            "El desglose de potencia por periodos coincide con el "
                            "importe de potencia de la factura."
                        )
                    else:
                        st.warning(
                            "El desglose de potencia por periodos no coincide con el "
                            "importe de potencia extraído."
                        )
                    calculos_potencia_correctos = all(
                        abs(
                            item.coste_facturado_eur
                            - round(
                                item.potencia_kw * item.meses
                                * item.precio_facturado_eur_kw_mes
                                if potencia_facturada_por_meses
                                else item.potencia_kw * item.dias
                                * item.precio_facturado_eur_kw_dia,
                                2,
                            )
                        ) <= 0.02
                        for item in factura.potencia_periodos
                    )
                    if calculos_potencia_correctos:
                        st.success(
                            "El cálculo potencia × meses × precio mensual coincide "
                            "en todos los periodos facturados."
                            if potencia_facturada_por_meses
                            else "El cálculo potencia × días × precio coincide en "
                            "todos los periodos facturados."
                        )
                    else:
                        st.warning(
                            "Algún periodo no coincide con el cálculo potencia × días "
                            "× precio facturado."
                        )
                    verificadas = [
                        item for item in factura.potencia_periodos
                        if item.resultado != "No verificado"
                    ]
                    if any(item.resultado == "Superior a BOE" for item in verificadas):
                        if factura.sobrecoste_potencia > 0:
                            st.warning(
                                "El término de potencia incluye precios superiores a los "
                                "regulados. Diferencia neta en el periodo facturado, "
                                "incluidos los periodos inferiores a BOE: "
                                f"{formato_euros(factura.sobrecoste_potencia)} "
                                f"({formato_pct(factura.porcentaje_sobrecoste_potencia, 1)} "
                                "del término facturado). De mantenerse las mismas potencias "
                                "y precios durante un año completo, el sobrecoste neto anual "
                                "estimado sería de "
                                f"{formato_euros(factura.sobrecoste_anual_potencia)}."
                            )
                        else:
                            st.info(
                                "Aunque algún periodo tiene un precio superior a BOE, los "
                                "periodos inferiores lo compensan. Ahorro neto en el periodo "
                                f"facturado: {formato_euros(abs(factura.sobrecoste_potencia))}. "
                                "De mantenerse las mismas potencias y precios durante un año "
                                "completo, el ahorro neto anual estimado sería de "
                                f"{formato_euros(abs(factura.sobrecoste_anual_potencia))}."
                            )
                    elif verificadas:
                        st.success("El término de potencia está facturado a precios BOE.")
                    else:
                        st.info(
                            "No hay referencia regulada disponible para verificar estos precios."
                        )
                else:
                    st.info("No se ha podido extraer el detalle de potencia por periodos.")

            desplegable_consumo = st.expander(
                etiqueta_expander("Energía", "Consumo facturado")
            )
            if factura.energia_periodos:
                df_energia = pd.DataFrame(
                    [
                        {
                            "Periodo": item.periodo,
                            "Consumo (kWh)": item.consumo_kwh,
                            "Precio (€/kWh)": item.precio_eur_kwh,
                            "Coste (€)": item.coste_eur,
                        }
                        for item in factura.energia_periodos
                    ]
                )
                desplegable_consumo.dataframe(
                    formatear_columnas_tabla(
                        df_energia,
                        columnas_kwh=["Consumo (kWh)"],
                        columnas_eur_kwh=["Precio (€/kWh)"],
                        columnas_euros=["Coste (€)"],
                        decimales_kwh=2,
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                desplegable_consumo.warning(
                    "No se ha podido extraer el detalle de energía por periodos."
                )

            if factura.energia_periodos:
                with desplegable_consumo.container(border=True):
                    col_consumo_grafico, col_consumo_metricas = st.columns([0.68, 0.32])
                    with col_consumo_grafico:
                        st.subheader("Peso del consumo", divider="rainbow")
                        df_consumo_periodos = pd.DataFrame([
                            {"Periodo": item.periodo, "Consumo (kWh)": item.consumo_kwh}
                            for item in factura.energia_periodos
                            if item.consumo_kwh > 0
                        ])
                        if not df_consumo_periodos.empty:
                            es_20td = (
                                (factura.atr or "").replace(" ", "").upper() == "2.0TD"
                            )
                            if es_20td:
                                colores_consumo = {
                                    "P1": "red", "P2": "orange", "P3": "green",
                                }
                                orden_periodos = ["P1", "P2", "P3"]
                            else:
                                colores_consumo = {
                                    "P1": "#D73027", "P2": "#FC8D59",
                                    "P3": "#FEE08B", "P4": "#D9EF8B",
                                    "P5": "#91CF60", "P6": "#1A9850",
                                }
                                orden_periodos = ["P1", "P2", "P3", "P4", "P5", "P6"]

                            figura_consumo = px.pie(
                                df_consumo_periodos,
                                names="Periodo",
                                values="Consumo (kWh)",
                                color="Periodo",
                                color_discrete_map=colores_consumo,
                                category_orders={"Periodo": orden_periodos},
                                hole=0.3,
                            )
                            figura_consumo.update_traces(
                                textposition="inside", textinfo="label+percent",
                            )
                            figura_consumo.update_layout(
                                legend_title_text="Periodo", showlegend=True,
                            )
                            st.plotly_chart(figura_consumo, use_container_width=True)

                    with col_consumo_metricas:
                        st.metric(
                            "Consumo",
                            formato_kwh(factura.consumo_total_kwh, 2, True),
                        )
                        st.metric(
                            "Precio medio",
                            formato_eur_kwh(factura.precio_medio_energia)
                            if factura.consumo_total_kwh
                            else "No disponible",
                        )
                        st.metric(
                            "Coste de la energía",
                            formato_euros(factura.energia),
                        )

            desplegable_excesos = st.expander(
                etiqueta_expander("Excesos", "Verificación de excesos")
            )
            if not factura.excesos_potencia:
                desplegable_excesos.info(
                    "🔵 La factura no incluye excesos de potencia."
                    + (
                        " En 2.0TD se presupone control de potencia mediante ICP, "
                        "salvo que el contrato establezca expresamente modo excesos."
                        if es_20td else ""
                    )
                )
            elif factura.excesos_verificados or factura.verificacion_excesos:
                with desplegable_excesos:
                    if factura.excesos_verificados:
                        es_tipo_123 = factura.tipo_suministro in {
                            "Tipo 1", "Tipo 2", "Tipo 3"
                        }
                        df_excesos = pd.DataFrame(
                            [
                                ({
                                    "Periodo": item.periodo,
                                    "Contratada (kW)": item.potencia_contratada_kw,
                                    "Maxímetro (kW)": item.maximetro_kw,
                                    "Sobrepasamiento equivalente (kW)": item.exceso_kw,
                                    "TEP (€/kW)": item.tepp_eur_kw_dia,
                                    "Factor prorrateo": (
                                        f"{item.factor_prorrateo:.4f}"
                                        .replace(".", ",")
                                    ),
                                    "Coste (€)": item.coste_calculado_eur,
                                } if es_tipo_123 else {
                                    "Periodo": item.periodo,
                                    "Contratada (kW)": item.potencia_contratada_kw,
                                    "Maxímetro (kW)": item.maximetro_kw,
                                    "Exceso (kW)": item.exceso_kw,
                                    "TEPp (€/kW día)": item.tepp_eur_kw_dia,
                                    "Días": item.dias,
                                    "Coste (€)": item.coste_calculado_eur,
                                })
                                for item in sorted(
                                    factura.excesos_verificados,
                                    key=lambda detalle: int(
                                        detalle.periodo.upper().removeprefix("P")
                                    ),
                                )
                            ]
                        )
                        st.dataframe(
                            formatear_columnas_tabla(
                                df_excesos,
                                columnas_kw=[
                                    "Contratada (kW)", "Maxímetro (kW)", "Exceso (kW)",
                                    "Sobrepasamiento equivalente (kW)",
                                ],
                                columnas_eur_kw_dia=["TEPp (€/kW día)", "TEP (€/kW)"],
                                columnas_euros=["Coste (€)"],
                            ),
                            hide_index=True,
                            use_container_width=True,
                        )
                        col_exc_calc, col_exc_fra = st.columns(2)
                        col_exc_calc.metric(
                            "Excesos calculados",
                            formato_euros(factura.coste_excesos_calculado),
                        )
                        col_exc_fra.metric(
                            "Excesos facturados",
                            formato_euros(factura.excesos_potencia),
                            delta=formato_euros(factura.diferencia_excesos),
                            delta_color="inverse",
                        )

                    if factura.verificacion_excesos:
                        if (
                            factura.excesos_verificados
                            and importes_coinciden(
                                factura.excesos_potencia,
                                factura.coste_excesos_calculado,
                                "excesos_maximetros",
                            )
                        ):
                            st.success(factura.verificacion_excesos)
                        else:
                            st.info(factura.verificacion_excesos)

            zona_detalle_reactiva = st.empty()
            with zona_detalle_reactiva.expander(
                etiqueta_expander("Reactiva", "Energía reactiva")
            ):
                if factura.reactiva:
                    st.error(
                        "La factura incluye una penalización por reactiva de "
                        f"{formato_euros(factura.reactiva)}."
                    )
                else:
                    st.success("No se ha detectado coste por energía reactiva.")
                if factura.reactiva_periodos:
                    coste_reactiva_detallado = all(
                        item.detalle_coste_facturado
                        for item in factura.reactiva_periodos
                    )
                    etiqueta_coste_factura = (
                        "Coste factura (€)" if coste_reactiva_detallado
                        else "Coste factura prorrateado (€)"
                    )
                    df_reactiva = pd.DataFrame([
                        {
                            "Periodo": item.periodo,
                            "Activa (kWh)": item.energia_activa_kwh,
                            "Reactiva (kVArh)": item.energia_reactiva_kvarh,
                            "Exceso factura (kVArh)": item.exceso_facturado_kvarh,
                            "Exceso calculado (kVArh)": item.exceso_calculado_kvarh,
                            "cos φ": item.cos_phi,
                            "Precio (€/kVArh)": item.precio_eur_kvarh,
                            etiqueta_coste_factura: item.coste_facturado_eur,
                            "Coste calculado (€)": item.coste_calculado_eur,
                            "Verificación": item.estado,
                        }
                        for item in factura.reactiva_periodos
                    ])
                    st.dataframe(
                        formatear_columnas_tabla(
                            df_reactiva,
                            columnas_kwh=[
                                "Activa (kWh)", "Reactiva (kVArh)",
                                "Exceso factura (kVArh)",
                                "Exceso calculado (kVArh)",
                            ],
                            columnas_eur_kwh=["Precio (€/kVArh)"],
                            columnas_euros=[
                                etiqueta_coste_factura, "Coste calculado (€)",
                            ],
                            incluir_unidades=False,
                        ),
                        hide_index=True,
                        use_container_width=True,
                    )
                    if any(
                        item.estado == "🔴"
                        for item in factura.reactiva_periodos
                    ):
                        st.error(
                            "El coste total de reactiva supera el cálculo regulado."
                        )
                    elif any(
                        item.estado == "🟢 ⚠️"
                        for item in factura.reactiva_periodos
                    ):
                        st.warning(
                            "El coste total de reactiva difiere del cálculo, pero "
                            "la diferencia favorece al cliente."
                        )
                    elif all(
                        item.estado == "🟢"
                        for item in factura.reactiva_periodos
                    ):
                        st.success(
                            "El coste de reactiva coincide con las lecturas, "
                            "los excesos y los precios regulados por periodo."
                        )
                    if not coste_reactiva_detallado:
                        st.caption(
                            "La factura solo publica el coste total de reactiva. "
                            "El reparto por periodo es un prorrateo técnico para "
                            "visualización; la verificación compara los totales."
                        )
                st.dataframe(
                    formatear_columnas_tabla(
                        pd.DataFrame(tramos_reactiva()),
                        columnas_eur_kwh=["Precio (€/kVArh)"],
                        incluir_unidades=False,
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
                st.caption(
                    "La reactiva inductiva penalizable es la que excede el "
                    f"{LIMITE_REACTIVA_SOBRE_ACTIVA:.0%} de la energía activa "
                    f"en P1-P5. Fuente: {FUENTE_REACTIVA}."
                )
                if not factura.reactiva_periodos:
                    st.info(
                        "Para verificar el importe hacen falta energía activa y "
                        "reactiva desglosadas por periodo. Si el PDF solo publica el "
                        "coste, se detecta la penalización, pero no se reconstruye."
                    )
            if es_20td:
                zona_detalle_reactiva.empty()

            if factura.iee or factura.iva:
                estados_impuestos = [
                    semaforos_factura.get(nombre, "🟡")
                    for nombre in ("IEE", "IVA")
                    if nombre in semaforos_factura
                ]
                estado_impuestos = (
                    "🔴" if "🔴" in estados_impuestos
                    else "🟢" if estados_impuestos and all(
                        estado == "🟢" for estado in estados_impuestos
                    )
                    else "🟡"
                )
                with st.expander(f"{estado_impuestos} IEE e IVA"):
                    filas_impuestos = []
                    for nombre, importe_componente, verificacion in (
                        ("IEE", factura.iee, factura.verificacion_iee),
                        ("IVA", factura.iva, factura.verificacion_iva),
                    ):
                        if not importe_componente:
                            continue
                        filas_impuestos.append({
                            "Impuesto": nombre,
                            "Base (€)": verificacion.base_eur if verificacion else None,
                            "Tipo aplicado (%)": (
                                verificacion.tipo_pct if verificacion else None
                            ),
                            "Tipo regulado (%)": (
                                verificacion.tipo_regulado_pct
                                if verificacion else None
                            ),
                            "Importe factura (€)": importe_componente,
                            "Importe calculado (€)": (
                                verificacion.importe_calculado_eur
                                if verificacion else None
                            ),
                            "Verificación s/factura": (
                                "🟢" if verificacion and abs(
                                    verificacion.importe_facturado_eur
                                    - verificacion.importe_calculado_eur
                                ) <= 0.02 else "🟡"
                            ),
                            "Verificación real": (
                                verificacion.estado if verificacion else "🟡"
                            ),
                        })
                    df_impuestos = pd.DataFrame(filas_impuestos)
                    st.dataframe(
                        formatear_columnas_tabla(
                            df_impuestos,
                            columnas_euros=[
                                "Base (€)", "Importe factura (€)",
                                "Importe calculado (€)",
                            ],
                            columnas_pct=["Tipo aplicado (%)", "Tipo regulado (%)"],
                            incluir_unidades=False,
                            decimales_pct=6,
                        ),
                        hide_index=True,
                        use_container_width=True,
                    )
                    for verificacion in (
                        factura.verificacion_iee,
                        factura.verificacion_iva,
                    ):
                        if not verificacion:
                            continue
                        if verificacion.estado == "🟢":
                            st.success(verificacion.mensaje)
                        elif verificacion.estado == "🔴":
                            st.error(verificacion.mensaje)
                        else:
                            st.info(verificacion.mensaje)

            if factura.otros:
                with st.expander(
                    etiqueta_expander("Otros", "Otros conceptos detectados")
                ):
                    df_otros = pd.DataFrame(
                        [
                            {
                                "Concepto": item.concepto,
                                "Importe factura (€)": item.importe,
                                "Importe calculado s/factura (€)": (
                                    round(
                                        factura.verificacion_fbs.dias
                                        * factura.verificacion_fbs.precio_facturado_eur_dia,
                                        2,
                                    )
                                    if factura.verificacion_fbs
                                    and "bono social" in item.concepto.lower()
                                    else None
                                ),
                                "Referencia regulada (€)": (
                                    factura.verificacion_fbs.importe_regulado_eur
                                    if factura.verificacion_fbs
                                    and "bono social" in item.concepto.lower()
                                    else factura.verificacion_fnee.importe_referencia_eur
                                    if factura.verificacion_fnee
                                    and "fnee" in item.concepto.lower()
                                    else None
                                ),
                                "Verif s/cálculo": (
                                    "🟡"
                                    if "ssaa/ree" in item.concepto.lower()
                                    else estado_otro_calculo_factura(
                                        factura, texto, item
                                    )
                                ),
                                "Verificación real": estado_otro_segun_factura(
                                    factura, texto, item
                                ),
                                "Observación": (
                                    "No verificable: la factura no identifica el "
                                    "ciclo de liquidación al que corresponde."
                                    if "ssaa/ree" in item.concepto.lower()
                                    else
                                    "Servicio adicional contratado; compruebe si "
                                    "sigue siendo necesario y si puede cancelarse."
                                    if es_servicio_adicional(item)
                                    else
                                    "Aceptado por defecto según factura; "
                                    "sujeto a validación con datos del cliente."
                                    if "alquiler" in item.concepto.lower()
                                    else factura.verificacion_fbs.mensaje
                                    if factura.verificacion_fbs
                                    and not factura.verificacion_fbs.estado.startswith("🟢")
                                    and "bono social" in item.concepto.lower()
                                    else factura.verificacion_fnee.mensaje
                                    if factura.verificacion_fnee
                                    and not factura.verificacion_fnee.estado.startswith("🟢")
                                    and "fnee" in item.concepto.lower()
                                    else ""
                                ),
                            }
                            for item in factura.otros
                        ]
                    )
                    st.dataframe(
                        formatear_columnas_tabla(
                            df_otros,
                            columnas_euros=[
                                "Importe factura (€)",
                                "Importe calculado s/factura (€)",
                                "Referencia regulada (€)",
                            ],
                            incluir_unidades=True,
                        ),
                        hide_index=True,
                        use_container_width=True,
                    )
                    if factura.verificacion_fbs or factura.verificacion_fnee:
                        fbs = factura.verificacion_fbs
                        fnee = factura.verificacion_fnee
                        col_unitario_fbs, col_unitario_fnee, col_referencia_fnee = (
                            st.columns(3)
                        )
                        precio_regulado_fbs = (
                            fbs.precio_regulado_eur_dia
                            if fbs and fbs.precio_regulado_eur_dia is not None
                            else (
                                fbs.importe_regulado_eur / fbs.dias
                                if fbs
                                and fbs.importe_regulado_eur is not None
                                and fbs.dias
                                else None
                            )
                        )
                        col_unitario_fbs.metric(
                            "FBS regulado",
                            formato_euros(precio_regulado_fbs) + "/día"
                            if precio_regulado_fbs is not None
                            else "No disponible",
                            delta=(
                                formato_euros(
                                    fbs.precio_facturado_eur_dia
                                    - precio_regulado_fbs
                                )
                                if fbs
                                and fbs.precio_facturado_eur_dia is not None
                                and precio_regulado_fbs is not None
                                else None
                            ),
                            delta_color="inverse",
                        )
                        col_unitario_fnee.metric(
                            "FNEE facturado/implícito",
                            formato_eur_mwh(fnee.precio_facturado_eur_mwh, 3)
                            if fnee
                            and fnee.precio_facturado_eur_mwh is not None
                            else "No disponible",
                        )
                        col_referencia_fnee.metric(
                            "FNEE de referencia",
                            formato_eur_mwh(fnee.precio_referencia_eur_mwh, 3)
                            if fnee
                            and fnee.precio_referencia_eur_mwh is not None
                            else "No disponible",
                        )
                        if fbs:
                            st.caption(f"FBS calculado sobre {fbs.dias} días.")
                    if any(
                        "ssaa/ree" in item.concepto.lower()
                        for item in factura.otros
                    ):
                        st.warning(
                            "La reliquidación de servicios de ajuste REE se ha "
                            "detectado, pero no puede verificarse porque la factura "
                            "no indica el ciclo de liquidación correspondiente."
                        )
                    if factura.verificacion_fnee:
                        fnee = factura.verificacion_fnee
                        st.caption(f"Modalidad: {fnee.modalidad}")

            with st.expander("Detalles técnicos"):
                st.write(f"Identificador local del PDF: `{huella[:16]}`")
                st.json(factura.como_dict())
                st.text_area("Texto extraído", texto, height=240)


with tab_verificacion:
    if factura is None:
        st.info("Carga una factura válida para preparar la verificación con medida.")
    elif _atr_indexado(factura.atr) is None:
        st.info("El peaje de la factura no está soportado en esta verificación.")
    elif not factura.periodo_inicio or not factura.periodo_fin:
        st.warning("La factura no contiene un periodo de consumo completo.")
    else:
        atr_medida = _atr_indexado(factura.atr)
        periodos_medida = tuple(
            f"P{indice}" for indice in range(1, 4 if atr_medida == "2.0" else 7)
        )
        tab_medida, tab_condiciones, tab_resultado_medida = st.columns(
            [0.30, 0.30, 0.40], gap="large"
        )
        fecha_inicio_medida = _fecha_factura(factura.periodo_inicio)
        fecha_fin_medida = _fecha_factura(factura.periodo_fin)
        resultado_medida_sesion = st.session_state.get(
            "factura_verificacion_consumos"
        )
        resultado_medida = None
        if (
            resultado_medida_sesion
            and resultado_medida_sesion.get("huella") == huella
        ):
            resultado_medida = resultado_medida_sesion.get("resultado")

        with tab_medida:
            st.subheader("1 · Datos de medida", divider="rainbow")
            origen_medida_factura = st.selectbox(
                "Origen de datos",
                ("Datadis", "Axon", "Archivo CSV/Excel"),
                key="factura_origen_medida",
            )
            if origen_medida_factura == "Axon":
                with st.expander("Acceso y descarga Axon", expanded=True):
                    usuario_axon_factura = st.text_input(
                        "Usuario Axon",
                        value=st.session_state.get("axon_usuario_sesion", ""),
                        key="factura_axon_usuario",
                    )
                    password_axon_factura = st.text_input(
                        "Contraseña Axon",
                        value=st.session_state.get("axon_password_sesion", ""),
                        type="password",
                        key="factura_axon_password",
                    )
                    cups_axon_factura = st.text_input(
                        "CUPS",
                        value=(factura.cups or "")[:20],
                        max_chars=20,
                        key=f"factura_axon_cups_{huella[:8]}",
                        help="Axon utiliza el CUPS base de 20 caracteres, sin los dos caracteres finales.",
                    )
                    tipo_axon_factura = st.selectbox(
                        "Resolución solicitada",
                        ("TM1 · Horaria", "TM2 · Cuartohoraria"),
                        key="factura_axon_tipo",
                        help=(
                            "TM2 solo está disponible para determinados equipos "
                            "y suministros."
                        ),
                    )
                    descargar_axon_factura = st.button(
                        "Obtener y verificar consumos",
                        type="primary",
                        use_container_width=True,
                        key="factura_obtener_consumos_axon",
                    )
                    if descargar_axon_factura:
                        try:
                            cups_axon_factura = "".join(
                                str(cups_axon_factura or "").split()
                            ).upper()[:20]
                            with st.spinner("Descargando y preparando la curva Axon…"):
                                curva_axon, frecuencia_axon = obtener_datos_contador(
                                    usuario_axon_factura,
                                    password_axon_factura,
                                    cups_axon_factura,
                                    fecha_inicio_medida,
                                    fecha_fin_medida,
                                    "TM1" if tipo_axon_factura.startswith("TM1") else "TM2",
                                )
                                preparado = preparar_curva_factura(
                                    curva_axon,
                                    fecha_inicio_medida,
                                    fecha_fin_medida,
                                    atr=atr_medida,
                                    zona_periodos="peninsula",
                                    nombre_origen=f"axon_{frecuencia_axon.lower()}.csv",
                                )
                            st.session_state.axon_usuario_sesion = usuario_axon_factura
                            st.session_state.axon_password_sesion = password_axon_factura
                            st.session_state.factura_verificacion_consumos = {
                                "huella": huella,
                                "origen": "axon",
                                "resultado": preparado,
                            }
                            st.rerun()
                        except Exception as exc:
                            st.error(f"No se ha podido verificar la curva Axon: {exc}")
            if origen_medida_factura == "Archivo CSV/Excel":
                with st.expander(
                    "Usar un CSV/Excel ya descargado",
                    expanded=origen_medida_factura == "Archivo CSV/Excel",
                ):
                    archivo_medida_factura = st.file_uploader(
                        "Curvas de carga",
                        type=["csv", "xlsx"],
                        accept_multiple_files=True,
                        key="factura_archivo_medida",
                        help=(
                            "Se procesa con el mismo normalizador que utiliza "
                            "Curva de carga."
                        ),
                    )
                    usar_archivo_medida = st.button(
                        "Verificar con estos archivos",
                        disabled=not archivo_medida_factura,
                        key="factura_usar_archivo_medida",
                    )
                    if usar_archivo_medida:
                        try:
                            with st.spinner("Normalizando y recortando la curva…"):
                                preparado = preparar_archivos_factura(
                                    archivo_medida_factura,
                                    fecha_inicio_medida,
                                    fecha_fin_medida,
                                    atr=atr_medida,
                                    zona_periodos="peninsula",
                                )
                            st.session_state.factura_verificacion_consumos = {
                                "huella": huella,
                                "origen": "archivo",
                                "resultado": preparado,
                            }
                            st.rerun()
                        except Exception as exc:
                            st.error(f"No se ha podido preparar el archivo: {exc}")

            if origen_medida_factura == "Datadis":
                col_acceso, col_suministro, col_estado = st.columns([0.30, 0.34, 0.36])
                with col_acceso:
                    st.markdown("#### Acceso Datadis")
                    usuario_datadis_factura = st.text_input(
                        "Usuario Datadis", key="factura_datadis_usuario"
                    )
                    password_datadis_factura = st.text_input(
                        "Contraseña Datadis",
                        type="password",
                        key="factura_datadis_password",
                    )
                    acceso_datadis_factura = st.radio(
                        "Acceso",
                        ("Titular", "Autorizado"),
                        horizontal=True,
                        key="factura_datadis_acceso",
                    )
                    authorized_nif_factura = ""
                    if acceso_datadis_factura == "Autorizado":
                        authorized_nif_factura = st.text_input(
                            "NIF del titular", key="factura_datadis_nif"
                        )
                    consultar_suministros_factura = st.button(
                        "Consultar suministros",
                        use_container_width=True,
                        key="factura_consultar_suministros_datadis",
                    )
                    if consultar_suministros_factura:
                        try:
                            with st.spinner("Consultando suministros en Datadis…"):
                                st.session_state.factura_suministros_datadis = (
                                    obtener_suministros_datadis(
                                        usuario_datadis_factura,
                                        password_datadis_factura,
                                        authorized_nif=authorized_nif_factura,
                                    )
                                )
                        except Exception as exc:
                            st.session_state.pop("factura_suministros_datadis", None)
                            st.error(f"No se pudieron consultar los suministros: {exc}")

                suministro_factura = None
                with col_suministro:
                    st.markdown("#### Suministro y periodo")
                    suministros_factura = st.session_state.get(
                        "factura_suministros_datadis"
                    )
                    if suministros_factura is not None and not suministros_factura.empty:
                        indices = list(suministros_factura.index)
                        cups_factura = (factura.cups or "").strip().upper()
                        indice_defecto = next(
                            (
                                posicion for posicion, indice in enumerate(indices)
                                if str(suministros_factura.loc[indice].get("cups", ""))
                                .strip().upper() == cups_factura
                            ),
                            0,
                        )

                        def etiqueta_suministro_factura(indice):
                            fila = suministros_factura.loc[indice]
                            cups = str(fila.get("cups", ""))
                            direccion = str(fila.get("address", "") or "").strip()
                            return f"{cups} · {direccion}" if direccion else cups

                        indice_suministro = st.selectbox(
                            "Suministro",
                            indices,
                            index=indice_defecto,
                            format_func=etiqueta_suministro_factura,
                            key="factura_suministro_datadis",
                        )
                        suministro_factura = suministros_factura.loc[
                            indice_suministro
                        ].to_dict()
                        if (
                            cups_factura
                            and str(suministro_factura.get("cups", "")).strip().upper()
                            != cups_factura
                        ):
                            st.warning("El CUPS seleccionado no coincide con el de la factura.")
                    else:
                        st.info("Consulta los suministros para seleccionar el CUPS.")

                    inicio_mes, fin_mes = rango_meses_datadis(
                        factura.periodo_inicio, factura.periodo_fin
                    )
                    st.write(
                        f"Factura: **{factura.periodo_inicio} – {factura.periodo_fin}**"
                    )
                    st.write(
                        f"Consulta Datadis: **{inicio_mes:%m/%Y} – {fin_mes:%m/%Y}**"
                    )
                    preferir_qh_factura = st.checkbox(
                        "Intentar curva cuartohoraria (opción avanzada)",
                        value=False,
                        key="factura_datadis_preferir_qh_v2",
                        help=(
                            "Por defecto se solicita curva horaria. Datadis no ofrece "
                            "QH para todos los tipos de punto ni distribuidoras; los "
                            "tipos 4 y 5 se consultan siempre en horario. No se realiza "
                            "fallback automático para evitar consumir otra consulta."
                        ),
                    )
                    obtener_medida = st.button(
                        "Obtener y verificar consumos",
                        type="primary",
                        use_container_width=True,
                        disabled=suministro_factura is None,
                        key="factura_obtener_consumos_datadis",
                    )
                    if obtener_medida:
                        try:
                            cache_curvas = st.session_state.setdefault(
                                "datadis_curvas_cache", {}
                            )
                            with st.spinner("Descargando y preparando la curva…"):
                                (
                                    curva_original,
                                    frecuencia_datadis,
                                    aviso_fallback,
                                    clave_datadis,
                                    reutilizado,
                                ) = obtener_consumo_datadis_cacheado(
                                    cache_curvas,
                                    usuario_datadis_factura,
                                    password_datadis_factura,
                                    suministro_factura,
                                    fecha_inicio_medida,
                                    fecha_fin_medida,
                                    authorized_nif=authorized_nif_factura,
                                    preferir_qh=preferir_qh_factura,
                                )
                                preparado = preparar_curva_factura(
                                    curva_original,
                                    fecha_inicio_medida,
                                    fecha_fin_medida,
                                    atr=atr_medida,
                                    zona_periodos="peninsula",
                                    nombre_origen=(
                                        f"datadis_{frecuencia_datadis.lower()}.csv"
                                    ),
                                )
                            st.session_state.factura_verificacion_consumos = {
                                "huella": huella,
                                "clave_datadis": clave_datadis,
                                "reutilizado": reutilizado,
                                "aviso_fallback": aviso_fallback,
                                "resultado": preparado,
                            }
                            st.rerun()
                        except DatadisLimiteConsultas as exc:
                            st.warning(
                                f"{exc} Datadis aplica el límite al CUPS/consulta, "
                                "aunque el rango solicitado sea diferente. Usa arriba "
                                "el CSV ya descargado o espera a que venza el plazo."
                            )
                        except Exception as exc:
                            st.session_state.pop("factura_verificacion_consumos", None)
                            st.error(f"No se ha podido verificar la curva: {exc}")

                with col_estado:
                    st.markdown("#### Estado de la medida")
                    if resultado_medida is None:
                        st.info("Todavía no se ha obtenido una curva para esta factura.")
                    else:
                        cobertura = resultado_medida.cobertura
                        if cobertura["completa"]:
                            st.success("Cobertura completa del periodo facturado.")
                        else:
                            st.warning(
                                "La curva tiene incidencias de cobertura: "
                                f"{cobertura['intervalos_ausentes']} intervalos ausentes y "
                                f"{cobertura['registros_duplicados']} registros duplicados."
                            )
                        st.metric("Resolución", resultado_medida.frecuencia)
                        st.metric(
                            "Registros del ciclo",
                            cobertura["intervalos_unicos"],
                            delta=(
                                cobertura["intervalos_unicos"]
                                - cobertura["intervalos_esperados"]
                            ),
                        )
                        original_csv = dataframe_como_archivo_curva(
                            resultado_medida.curva_original, "datadis_original.csv"
                        ).getvalue()
                        recorte_csv = dataframe_como_archivo_curva(
                            resultado_medida.curva_periodo,
                            "datadis_periodo_factura.csv",
                        ).getvalue()
                        st.download_button(
                            "Descargar curva original",
                            original_csv,
                            "datadis_original.csv",
                            "text/csv",
                            use_container_width=True,
                        )
                        st.download_button(
                            "Descargar periodo facturado",
                            recorte_csv,
                            "datadis_periodo_factura.csv",
                            "text/csv",
                            use_container_width=True,
                        )

            if resultado_medida is not None:
                curva_graficos = resultado_medida.curva_periodo.copy()
                curva_graficos["fecha_hora"] = pd.to_datetime(
                    curva_graficos["fecha_hora"], errors="coerce"
                )
                curva_graficos["consumo_neto_kWh"] = pd.to_numeric(
                    curva_graficos["consumo_neto_kWh"], errors="coerce"
                ).fillna(0.0)
                curva_graficos = curva_graficos.dropna(subset=["fecha_hora"])
                col_graficos_izq, col_graficos_der = st.columns(
                    2, gap="small"
                )

                def estilo_grafico_medida(figura):
                    figura = aplicar_estilo(figura)
                    figura.update_layout(height=300)
                    return figura

                consumo_diario = (
                    curva_graficos.assign(
                        Fecha=curva_graficos["fecha_hora"].dt.date
                    )
                    .groupby("Fecha", as_index=False)["consumo_neto_kWh"]
                    .sum()
                    .rename(columns={"consumo_neto_kWh": "Consumo diario (kWh)"})
                )
                media_diaria_grafico = consumo_diario[
                    "Consumo diario (kWh)"
                ].mean()
                figura_diaria = px.bar(
                    consumo_diario,
                    x="Fecha",
                    y="Consumo diario (kWh)",
                    title="Consumo diario y medio",
                )
                figura_diaria.add_scatter(
                    x=consumo_diario["Fecha"],
                    y=[media_diaria_grafico] * len(consumo_diario),
                    name="Media diaria",
                    mode="lines",
                    line=dict(color="#f59e0b", width=2.5),
                )
                figura_diaria.update_layout(
                    height=170,
                    margin=dict(l=5, r=5, t=38, b=5),
                    yaxis_title="Consumo diario (kWh)",
                    legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
                )
                col_graficos_izq.plotly_chart(
                    estilo_grafico_medida(figura_diaria),
                    use_container_width=True,
                    key=f"factura_consumo_diario_{huella[:8]}",
                )

                consumo_horario_dia = (
                    curva_graficos.assign(
                        Fecha=curva_graficos["fecha_hora"].dt.date,
                        Hora=curva_graficos["fecha_hora"].dt.hour,
                    )
                    .groupby(["Fecha", "Hora"], as_index=False)[
                        "consumo_neto_kWh"
                    ]
                    .sum()
                )
                perfil_medio = (
                    consumo_horario_dia.groupby("Hora", as_index=False)[
                        "consumo_neto_kWh"
                    ]
                    .mean()
                    .rename(
                        columns={"consumo_neto_kWh": "Consumo medio (kWh)"}
                    )
                )
                figura_perfil = px.line(
                    perfil_medio,
                    x="Hora",
                    y="Consumo medio (kWh)",
                    markers=False,
                    title="Perfil medio horario",
                )
                figura_perfil.update_layout(
                    height=170,
                    margin=dict(l=5, r=5, t=38, b=5),
                )
                figura_perfil.update_xaxes(dtick=2, range=[0, 23])
                figura_perfil.update_yaxes(rangemode="tozero")
                col_graficos_der.plotly_chart(
                    estilo_grafico_medida(figura_perfil),
                    use_container_width=True,
                    key=f"factura_perfil_horario_{huella[:8]}",
                )

                consumo_periodos_grafico = (
                    curva_graficos.groupby("periodo", as_index=False)[
                        "consumo_neto_kWh"
                    ]
                    .sum()
                    .rename(columns={"consumo_neto_kWh": "Consumo (kWh)"})
                )
                figura_periodos = px.pie(
                    consumo_periodos_grafico,
                    names="periodo",
                    values="Consumo (kWh)",
                    hole=0.42,
                    title="Consumo por periodos",
                    color="periodo",
                    color_discrete_map=colores_periodo,
                )
                figura_periodos.update_traces(
                    textinfo="none",
                    texttemplate="<b>%{label}</b><br><b>%{percent}</b>",
                    textfont=dict(size=14, family="Arial Black"),
                    textposition="inside",
                    hovertemplate=(
                        "%{label}<br>%{value:,.2f} kWh<br>"
                        "%{percent}<extra></extra>"
                    ),
                )
                figura_periodos.update_layout(
                    height=170,
                    margin=dict(l=5, r=5, t=38, b=5),
                    showlegend=False,
                )
                col_graficos_izq.plotly_chart(
                    estilo_grafico_medida(figura_periodos),
                    use_container_width=True,
                    key=f"factura_consumo_periodos_{huella[:8]}",
                )

                tabla_calor = curva_graficos.assign(
                    Fecha=curva_graficos["fecha_hora"].dt.strftime("%d/%m"),
                    Hora=curva_graficos["fecha_hora"].dt.hour,
                ).pivot_table(
                    index="Fecha",
                    columns="Hora",
                    values="consumo_neto_kWh",
                    aggfunc="sum",
                    fill_value=0,
                    sort=False,
                )
                figura_calor = go.Figure(go.Heatmap(
                    z=tabla_calor.to_numpy(),
                    x=tabla_calor.columns,
                    y=tabla_calor.index,
                    colorscale="YlOrRd",
                    colorbar=dict(title="kWh", thickness=10),
                    hovertemplate=(
                        "Fecha: %{y}<br>Hora: %{x}:00<br>"
                        "Consumo: %{z:.2f} kWh<extra></extra>"
                    ),
                ))
                figura_calor.update_layout(
                    title="Mapa de calor del consumo",
                    height=170,
                    margin=dict(l=5, r=5, t=38, b=20),
                    xaxis_title="Hora",
                    yaxis=dict(title="", autorange="reversed"),
                )
                col_graficos_der.plotly_chart(
                    estilo_grafico_medida(figura_calor),
                    use_container_width=True,
                    key=f"factura_mapa_calor_{huella[:8]}",
                )

                consumo_medio_diario = consumo_diario[
                    "Consumo diario (kWh)"
                ].mean()
                consumo_medio_horario = consumo_horario_dia[
                    "consumo_neto_kWh"
                ].mean()
                fila_max_diario = consumo_diario.loc[
                    consumo_diario["Consumo diario (kWh)"].idxmax()
                ]
                fila_max_horario = consumo_horario_dia.loc[
                    consumo_horario_dia["consumo_neto_kWh"].idxmax()
                ]
                fecha_hora_maxima = (
                    pd.Timestamp(fila_max_horario["Fecha"]).normalize()
                    + pd.Timedelta(hours=int(fila_max_horario["Hora"]))
                )

                metric_medio_dia, metric_medio_hora, metric_max_dia, metric_max_hora = (
                    st.columns(4, gap="small")
                )
                metric_medio_dia.metric(
                    "Consumo medio diario",
                    formato_kwh(consumo_medio_diario),
                )
                metric_medio_hora.metric(
                    "Consumo medio horario",
                    formato_kwh(consumo_medio_horario),
                )
                metric_max_dia.metric(
                    "Máximo diario",
                    formato_kwh(fila_max_diario["Consumo diario (kWh)"]),
                    delta=pd.Timestamp(fila_max_diario["Fecha"]).strftime("%d/%m/%Y"),
                    delta_color="off",
                )
                metric_max_hora.metric(
                    "Máximo horario",
                    formato_kwh(fila_max_horario["consumo_neto_kWh"]),
                    delta=fecha_hora_maxima.strftime("%d/%m/%Y %H:%M"),
                    delta_color="off",
                )

        precios_confirmados = {}
        potencia_confirmada = []
        detalle_excesos_beta = pd.DataFrame()
        coste_excesos_beta = None
        componentes_confirmados = {}
        componentes_facturados_beta = {}
        fnee_incluido_indexado = 0.0
        clave_tipo_energia_verificacion = (
            f"factura_verificacion_tipo_energia_{huella[:8]}"
        )
        with tab_condiciones:
            st.subheader("2 · Datos de contrato", divider="rainbow")
            if resultado_medida is None:
                st.info("Obtén primero la curva de medida en la pestaña anterior.")
            else:
                if clave_tipo_energia_verificacion not in st.session_state:
                    st.session_state[clave_tipo_energia_verificacion] = (
                        "Indexado"
                        if _factura_parece_indexada(factura, texto)
                        else "Fijo"
                    )
                tipo_energia_verificacion = st.radio(
                    "Tipo de precio de energía",
                    ["Fijo", "Indexado"],
                    key=clave_tipo_energia_verificacion,
                    horizontal=True,
                )
                if tipo_energia_verificacion == "Fijo":
                    st.markdown("#### Confirma los precios fijos de energía")
                    st.caption(
                        "Se proponen los precios extraídos de la factura. "
                        "Modifícalos si las condiciones contractuales son distintas."
                    )
                    precios_factura = {
                        item.periodo: item.precio_eur_kwh
                        for item in factura.energia_periodos
                        if item.periodo in periodos_medida
                    }
                    columnas_precio = st.columns(3)
                    for indice, periodo in enumerate(periodos_medida):
                        with columnas_precio[indice % 3]:
                            precios_confirmados[periodo] = st.number_input(
                                f"{periodo} (€/kWh)",
                                min_value=0.0,
                                max_value=2.0,
                                value=float(precios_factura.get(periodo, 0.0)),
                                step=0.001,
                                format="%.6f",
                                key=(
                                    f"factura_medida_precio_{periodo}_{huella[:8]}"
                                ),
                            )
                else:
                    st.markdown("#### Confirma la fórmula indexada de energía")
                    st.caption(
                        "Configuración común con Telemindex. Se aplicará a los "
                        "consumos reales de la curva para el periodo de la factura."
                    )
                    mostrar_parametros_formula_indexado(
                        widget_suffix="factura_verificacion"
                    )
                    if st.session_state.get("cfg_fnee", True):
                        fnee_incluido_indexado = sum(
                            float(item.importe)
                            for item in factura.otros
                            if "fnee" in item.concepto.lower()
                        )

                st.markdown("#### Confirma potencia y precio de potencia")
                items_potencia = [
                    item for item in factura.potencia_periodos
                    if item.periodo in periodos_medida
                ]
                st.caption(
                    "Los precios están normalizados en €/kW día. Los cambios "
                    "de potencia dentro del ciclo se muestran por tramos."
                )
                tramos_potencia = {}
                for item in items_potencia:
                    clave_tramo = (
                        item.periodo_inicio or factura.periodo_inicio,
                        item.periodo_fin or factura.periodo_fin,
                    )
                    tramos_potencia.setdefault(clave_tramo, []).append(item)

                for numero_tramo, (fechas_tramo, items_tramo) in enumerate(
                    sorted(tramos_potencia.items()), start=1
                ):
                    inicio_tramo, fin_tramo = fechas_tramo
                    dias_tramo = sorted({int(item.dias) for item in items_tramo})
                    st.markdown(
                        f"**Tramo {numero_tramo}: {inicio_tramo}–{fin_tramo} "
                        f"· {', '.join(map(str, dias_tramo))} días**"
                    )
                    sufijo_tramo = re.sub(
                        r"\D", "", f"{inicio_tramo}_{fin_tramo}"
                    )
                    st.caption("Potencias contratadas (kW)")
                    columnas_potencia_kw = st.columns(3)
                    potencias_tramo = {}
                    for indice, item in enumerate(items_tramo):
                        with columnas_potencia_kw[indice % 3]:
                            potencias_tramo[item.periodo] = st.number_input(
                                f"{item.periodo} (kW)",
                                min_value=0.0,
                                value=float(item.potencia_kw),
                                step=0.1,
                                format="%.3f",
                                key=(
                                    f"factura_medida_potencia_kw_{item.periodo}_"
                                    f"{sufijo_tramo}_{huella[:8]}"
                                ),
                            )
                    st.caption("Precios de potencia (€/kW día)")
                    columnas_precio_potencia = st.columns(3)
                    precios_tramo = {}
                    for indice, item in enumerate(items_tramo):
                        with columnas_precio_potencia[indice % 3]:
                            precios_tramo[item.periodo] = st.number_input(
                                f"{item.periodo} (€/kW día)",
                                min_value=0.0,
                                value=float(item.precio_facturado_eur_kw_dia),
                                step=0.0001,
                                format="%.8f",
                                key=(
                                    f"factura_medida_precio_potencia_{item.periodo}_"
                                    f"{sufijo_tramo}_{huella[:8]}"
                                ),
                            )
                    potencia_confirmada.extend({
                        "periodo": item.periodo,
                        "potencia_kw": potencias_tramo[item.periodo],
                        "dias": item.dias,
                        "precio_eur_kw_dia": precios_tramo[item.periodo],
                        "periodo_inicio": inicio_tramo,
                        "periodo_fin": fin_tramo,
                    } for item in items_tramo)

                if (
                    factura.excesos_potencia is not None
                    and potencia_confirmada
                ):
                    try:
                        detalles_tramos_excesos = []
                        coste_excesos_beta = 0.0
                        grupos_confirmados = {}
                        for item in potencia_confirmada:
                            clave_tramo = (
                                item.get("periodo_inicio") or factura.periodo_inicio,
                                item.get("periodo_fin") or factura.periodo_fin,
                            )
                            grupos_confirmados.setdefault(clave_tramo, []).append(item)
                        for (inicio_tramo, fin_tramo), items_tramo in sorted(
                            grupos_confirmados.items()
                        ):
                            inicio_dt = pd.to_datetime(
                                inicio_tramo, dayfirst=True
                            ).normalize()
                            fin_dt = pd.to_datetime(
                                fin_tramo, dayfirst=True
                            ).normalize() + pd.Timedelta(days=1)
                            fechas_curva = pd.to_datetime(
                                resultado_medida.curva_periodo["fecha_hora"],
                                errors="coerce",
                            )
                            curva_tramo = resultado_medida.curva_periodo.loc[
                                (fechas_curva >= inicio_dt) & (fechas_curva < fin_dt)
                            ].copy()
                            potencias_tramo = {
                                item["periodo"]: item["potencia_kw"]
                                for item in items_tramo
                            }
                            detalle_tramo, coste_tramo = calcular_excesos_desde_curva(
                                curva_tramo,
                                resultado_medida.frecuencia,
                                atr_medida,
                                inicio_dt.year,
                                potencias_tramo,
                                prorratear=len(grupos_confirmados) > 1,
                            )
                            detalle_tramo.insert(
                                0, "Tramo", f"{inicio_tramo}–{fin_tramo}"
                            )
                            detalles_tramos_excesos.append(detalle_tramo)
                            coste_excesos_beta += coste_tramo
                        detalle_excesos_beta = pd.concat(
                            detalles_tramos_excesos, ignore_index=True
                        )
                        coste_excesos_beta = round(coste_excesos_beta, 2)
                        componentes_facturados_beta["excesos_potencia"] = float(
                            factura.excesos_potencia
                        )
                        componentes_confirmados["excesos_potencia"] = (
                            coste_excesos_beta
                        )
                    except Exception as exc:
                        componentes_facturados_beta["excesos_potencia"] = float(
                            factura.excesos_potencia
                        )
                        componentes_confirmados["excesos_potencia"] = float(
                            factura.excesos_potencia
                        )
                        st.warning(
                            "No se han podido verificar los excesos de potencia: "
                            f"{exc}"
                        )

                st.markdown("#### Confirma el resto de componentes")
                filas_componentes_beta = []
                for indice, item in enumerate(factura.otros):
                    clave_otro = f"otro_{indice}"
                    if (
                        fnee_incluido_indexado
                        and "fnee" in item.concepto.lower()
                    ):
                        # Ya forma parte del precio horario Telemindex.
                        continue
                    if (
                        "bono social" in item.concepto.lower()
                        and factura.verificacion_fbs
                        and factura.verificacion_fbs.importe_regulado_eur
                        is not None
                    ):
                        componentes_facturados_beta[clave_otro] = float(
                            item.importe
                        )
                        componentes_confirmados[clave_otro] = float(
                            factura.verificacion_fbs.importe_regulado_eur
                        )
                        continue
                    if (
                        "fnee" in item.concepto.lower()
                        and factura.verificacion_fnee
                        and factura.verificacion_fnee.importe_referencia_eur
                        is not None
                    ):
                        componentes_facturados_beta[clave_otro] = float(
                            item.importe
                        )
                        componentes_confirmados[clave_otro] = float(
                            factura.verificacion_fnee.importe_referencia_eur
                        )
                        continue
                    filas_componentes_beta.append({
                        "Clave": clave_otro,
                        "Componente": item.concepto,
                        "Importe factura (€)": item.importe,
                        "Confirmado": True,
                        "Importe verificación (€)": item.importe,
                    })
                if (
                    factura.verificacion_fbs
                    and factura.verificacion_fbs.importe_regulado_eur
                    is not None
                ):
                    st.caption(
                        "FBS verificado automáticamente con el precio regulado: "
                        f"{formato_euros(factura.verificacion_fbs.importe_regulado_eur)}."
                    )
                if (
                    factura.verificacion_fnee
                    and factura.verificacion_fnee.importe_referencia_eur
                    is not None
                ):
                    st.caption(
                        "FNEE verificado automáticamente con la referencia "
                        f"regulatoria: {formato_euros(factura.verificacion_fnee.importe_referencia_eur)}."
                    )
                df_componentes_beta = pd.DataFrame(filas_componentes_beta)
                if df_componentes_beta.empty:
                    st.info("No se han extraído otros componentes de la factura.")
                else:
                    editor_componentes = st.data_editor(
                        df_componentes_beta,
                        hide_index=True,
                        use_container_width=True,
                        disabled=["Clave", "Componente", "Importe factura (€)"],
                        column_config={
                            "Clave": None,
                            "Confirmado": st.column_config.CheckboxColumn(
                                "OK", help="Mantiene el importe de la factura."
                            ),
                            "Importe verificación (€)": st.column_config.NumberColumn(
                                "Importe si no está OK (€)",
                                min_value=0.0,
                                format="%.2f €",
                            ),
                        },
                        key=f"factura_componentes_beta_{huella[:8]}",
                    )
                    for _, fila in editor_componentes.iterrows():
                        clave = str(fila["Clave"])
                        importe_facturado = float(fila["Importe factura (€)"])
                        componentes_facturados_beta[clave] = importe_facturado
                        componentes_confirmados[clave] = (
                            importe_facturado
                            if bool(fila["Confirmado"])
                            else float(fila["Importe verificación (€)"])
                        )
                st.caption(
                    "IEE e IVA se recalculan automáticamente con sus tipos "
                    "regulatorios sobre las bases ajustadas."
                )

            reparto_energia_potencia = pd.DataFrame({
                "Componente": ["Energía", "Potencia"],
                "Importe (€)": [
                    max(float(factura.energia), 0.0),
                    max(float(factura.potencia), 0.0),
                ],
            })
            reparto_energia_potencia = reparto_energia_potencia[
                reparto_energia_potencia["Importe (€)"] > 0
            ]

        with tab_resultado_medida:
            if resultado_medida is not None:
                st.subheader("3 · Resultado", divider="rainbow")
                subcol_resultado, subcol_metricas = st.columns(
                    [0.70, 0.30], gap="medium"
                )
                estado_resumen_real = subcol_resultado.empty()
                gauge_resumen_real = subcol_resultado.empty()
                metric_factura_resumen = subcol_metricas.empty()
                metric_verificado_resumen = subcol_metricas.empty()
                metric_diferencia_resumen = subcol_metricas.empty()
            st.subheader("4 · Detalles de la verificación", divider="rainbow")
            cups_periodo = (factura.cups or "").strip().upper()
            cups_enmascarado = (
                f"{cups_periodo[:6]}***{cups_periodo[-6:]}"
                if len(cups_periodo) > 12
                else cups_periodo
            )
            st.caption(
                f"Periodo analizado: {factura.periodo_inicio} – "
                f"{factura.periodo_fin} · CUPS: {cups_enmascarado} · "
                f"Factura: {factura.numero_factura or 'No disponible'}"
            )
            if resultado_medida is None:
                st.info("Obtén primero la curva de medida.")
            else:
                col_tabla_reconstruccion, col_metricas_resultado = st.columns(
                    [0.70, 0.30], gap="medium"
                )
                titulo_resumen_componentes = col_tabla_reconstruccion.empty()
                tabla_resumen_componentes = col_tabla_reconstruccion.empty()
                detalle_costes = col_tabla_reconstruccion.container()
                grafico_componentes = col_metricas_resultado.container()
                col_medida_resultado, _ = st.columns(
                    [0.70, 0.30], gap="medium"
                )
                col_costes_resultado = st.container()
                consumos_factura = {
                    item.periodo: item.consumo_kwh
                    for item in factura.energia_periodos
                    if item.periodo in periodos_medida
                }
                tabla_consumos = tabla_conciliacion_consumos(
                    consumos_factura,
                    resultado_medida.consumos_periodos,
                )
                col_medida_resultado.markdown("#### Comparativa de consumos")
                col_medida_resultado.dataframe(
                    formatear_columnas_tabla(
                        tabla_consumos,
                        columnas_kwh=[
                            "Factura (kWh)", "Medida (kWh)", "Diferencia (kWh)"
                        ],
                        columnas_pct=["Diferencia (%)"],
                        incluir_unidades=False,
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
                tipo_energia_verificacion = st.session_state.get(
                    clave_tipo_energia_verificacion, "Fijo"
                )
                if tipo_energia_verificacion == "Indexado":
                    try:
                        _precios_indexado_periodo(
                            factura
                        )
                        detalle_coste, coste_energia_medida = (
                            calcular_energia_indexada(
                                resultado_medida.curva_periodo,
                                st.session_state.df_sheets,
                                _atr_indexado(factura.atr),
                                resultado_medida.frecuencia,
                            )
                        )
                    except Exception as exc:
                        precios_resultado = {}
                        detalle_costes.error(
                            "No se ha podido calcular la fórmula indexada con "
                            f"Telemindex: {exc}"
                        )
                        detalle_coste, coste_energia_medida = calcular_energia_fija(
                            resultado_medida.consumos_periodos, {}
                        )
                else:
                    precios_resultado = {
                        periodo: st.session_state.get(
                            f"factura_medida_precio_{periodo}_{huella[:8]}",
                            next(
                                (
                                    item.precio_eur_kwh
                                    for item in factura.energia_periodos
                                    if item.periodo == periodo
                                ),
                                0.0,
                            ),
                        )
                        for periodo in periodos_medida
                    }
                    detalle_coste, coste_energia_medida = calcular_energia_fija(
                        resultado_medida.consumos_periodos,
                        precios_resultado,
                    )
                    detalle_coste = detalle_coste.rename(columns={
                        "Precio confirmado (€/kWh)":
                        "Precio verificación (€/kWh)"
                    })
                consumo_total_medida = detalle_coste[
                    "Consumo medida (kWh)"
                ].sum()
                precio_medio_ponderado = (
                    coste_energia_medida / consumo_total_medida
                    if consumo_total_medida > 0 else 0.0
                )
                energia_facturada_comparable = round(
                    float(factura.energia) + fnee_incluido_indexado, 2
                )
                detalle_coste_mostrar = pd.concat(
                    [
                        detalle_coste,
                        pd.DataFrame([{
                            "Periodo": "TOTAL",
                            "Consumo medida (kWh)": consumo_total_medida,
                            "Precio verificación (€/kWh)": precio_medio_ponderado,
                            "Coste verificado (€)": coste_energia_medida,
                        }]),
                    ],
                    ignore_index=True,
                )
                detalle_costes.markdown(
                    "#### Coste previsto del consumo"
                )
                detalle_costes.dataframe(
                    formatear_columnas_tabla(
                        detalle_coste_mostrar,
                        columnas_kwh=["Consumo medida (kWh)"],
                        columnas_eur_kwh=["Precio verificación (€/kWh)"],
                        columnas_euros=["Coste verificado (€)"],
                        incluir_unidades=False,
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
                detalle_potencia_beta, coste_potencia_beta = (
                    calcular_potencia_confirmada(potencia_confirmada)
                )
                detalle_potencia_mostrar = pd.concat(
                    [
                        detalle_potencia_beta,
                        pd.DataFrame([{
                            "Periodo": "TOTAL",
                            "Potencia confirmada (kW)": None,
                            "Días": None,
                            "Precio confirmado (€/kW día)": None,
                            "Coste verificado (€)": coste_potencia_beta,
                        }]),
                    ],
                    ignore_index=True,
                )
                detalle_costes.markdown(
                    "#### Coste previsto de la potencia facturada"
                )
                tabla_potencia_mostrar = formatear_columnas_tabla(
                        detalle_potencia_mostrar,
                        columnas_kw=["Potencia confirmada (kW)"],
                        columnas_eur_kw_dia=[
                            "Precio confirmado (€/kW día)"
                        ],
                        columnas_euros=["Coste verificado (€)"],
                        incluir_unidades=False,
                    ).fillna("")
                detalle_costes.table(tabla_potencia_mostrar)

                if coste_excesos_beta is not None:
                    col_excesos_tabla, col_excesos_metricas = st.columns(
                        [0.70, 0.30], gap="medium"
                    )
                    col_excesos_tabla.markdown(
                        "#### Excesos de potencia según medida"
                    )
                    tabla_excesos_mostrar = formatear_columnas_tabla(
                        detalle_excesos_beta,
                        columnas_kw=[
                            "Potencia contratada (kW)",
                            "Maxímetro (kW)",
                            "Raíz Σ excesos² (kW)",
                        ],
                        columnas_euros=[
                            "Excesos sin prorrateo (€)",
                            "Excesos verificados (€)",
                        ],
                        incluir_unidades=False,
                    )
                    col_excesos_tabla.table(tabla_excesos_mostrar)
                    coste_excesos_bruto_beta = float(
                        detalle_excesos_beta[
                            "Excesos sin prorrateo (€)"
                        ].sum()
                    )
                    col_excesos_tabla.caption(
                        "Coste de excesos sin prorrateo: "
                        f"{formato_euros(coste_excesos_bruto_beta)}. "
                        "El prorrateo se aplica al coste de cada tramo; no "
                        "modifica sus sobrepasamientos."
                    )
                    col_excesos_metricas.markdown("#### Excesos")
                    col_excesos_metricas.metric(
                        "Excesos facturados",
                        formato_euros(factura.excesos_potencia),
                    )
                    col_excesos_metricas.metric(
                        "Excesos según Axon",
                        formato_euros(coste_excesos_beta),
                        delta=formato_euros(
                            coste_excesos_beta - factura.excesos_potencia
                        ),
                        delta_color="inverse",
                    )

                verificacion_iee_beta = factura.verificacion_iee
                verificacion_iva_beta = factura.verificacion_iva
                reconstruccion_beta = reconstruir_total_beta(
                    total_factura=factura.total,
                    potencia_facturada=factura.potencia,
                    potencia_verificada=coste_potencia_beta,
                    energia_facturada=energia_facturada_comparable,
                    energia_verificada=coste_energia_medida,
                    otros_facturados=componentes_facturados_beta,
                    otros_confirmados=componentes_confirmados,
                    iee_facturado=factura.iee,
                    iva_facturado=factura.iva,
                    base_iee_factura=(
                        verificacion_iee_beta.base_eur
                        if verificacion_iee_beta else None
                    ),
                    tipo_iee_pct=(
                        verificacion_iee_beta.tipo_regulado_pct
                        or verificacion_iee_beta.tipo_pct
                        if verificacion_iee_beta else None
                    ),
                    base_iva_factura=(
                        verificacion_iva_beta.base_eur
                        if verificacion_iva_beta else None
                    ),
                    tipo_iva_pct=(
                        verificacion_iva_beta.tipo_regulado_pct
                        or verificacion_iva_beta.tipo_pct
                        if verificacion_iva_beta else None
                    ),
                )
                filas_total_beta = [
                    {
                        "Componente": "Potencia",
                        "Factura (€)": factura.potencia,
                        "Verificado (€)": coste_potencia_beta,
                    },
                    {
                        "Componente": "Energía",
                        "Factura (€)": energia_facturada_comparable,
                        "Verificado (€)": coste_energia_medida,
                    },
                ]
                nombres_componentes_beta = {
                    "excesos_potencia": "Excesos de potencia",
                    **{
                        f"otro_{indice}": item.concepto
                        for indice, item in enumerate(factura.otros)
                    },
                }
                filas_otros_beta = [
                    {
                        "Componente": nombres_componentes_beta.get(clave, clave),
                        "Factura (€)": importe,
                        "Verificado (€)": componentes_confirmados.get(
                            clave, importe
                        ),
                    }
                    for clave, importe in componentes_facturados_beta.items()
                ]
                filas_alquiler_beta = [
                    fila for fila in filas_otros_beta
                    if "alquiler" in fila["Componente"].lower()
                    and any(
                        termino in fila["Componente"].lower()
                        for termino in ("medida", "contador", "equipo")
                    )
                ]
                filas_total_beta.extend(
                    fila for fila in filas_otros_beta
                    if fila not in filas_alquiler_beta
                )
                filas_total_beta.append(
                    {
                        "Componente": "IEE",
                        "Factura (€)": factura.iee,
                        "Verificado (€)": reconstruccion_beta["iee_verificado"],
                    }
                )
                filas_total_beta.extend(filas_alquiler_beta)
                filas_total_beta.extend([
                    {
                        "Componente": "IVA",
                        "Factura (€)": factura.iva,
                        "Verificado (€)": reconstruccion_beta["iva_verificado"],
                    },
                    {
                        "Componente": "TOTAL",
                        "Factura (€)": factura.total,
                        "Verificado (€)": reconstruccion_beta["total_verificado"],
                    },
                ])
                tabla_total_beta = pd.DataFrame(filas_total_beta)
                tabla_total_beta["Diferencia (€)"] = (
                    tabla_total_beta["Factura (€)"]
                    - tabla_total_beta["Verificado (€)"]
                )
                tabla_total_beta["Desvío (%)"] = tabla_total_beta.apply(
                    lambda fila: (
                        fila["Diferencia (€)"] / fila["Verificado (€)"] * 100
                        if abs(fila["Verificado (€)"]) > 0.000001
                        else (0.0 if abs(fila["Diferencia (€)"]) <= 0.02 else None)
                    ),
                    axis=1,
                )
                def impacto_fila(fila):
                    tipo_tolerancia = (
                        "total_factura"
                        if fila["Componente"] == "TOTAL" else "componentes"
                    )
                    if importes_coinciden(
                        fila["Factura (€)"],
                        fila["Verificado (€)"],
                        tipo_tolerancia,
                    ):
                        return "correcto"
                    # Factura − verificado < 0: se ha cobrado menos que la
                    # referencia; hay desviación, pero favorece al cliente.
                    return "favorable" if fila["Diferencia (€)"] < 0 else "contra"

                impactos_tabla_beta = tabla_total_beta.apply(
                    impacto_fila, axis=1
                )
                tabla_total_beta["Estado"] = impactos_tabla_beta.map(
                    {"correcto": "✔", "favorable": "✖", "contra": "✖"}
                )
                verificacion_beta_ok = importes_coinciden(
                    factura.total,
                    reconstruccion_beta["total_verificado"],
                    "total_factura",
                )
                verificacion_beta_favorable = (
                    not verificacion_beta_ok
                    and reconstruccion_beta["diferencia_total"] < 0
                )
                if verificacion_beta_ok:
                    beta_texto, beta_icono, beta_color = (
                        "CORRECTO", "✓", "#00c853"
                    )
                elif verificacion_beta_favorable:
                    beta_texto, beta_icono, beta_color = (
                        "INCORRECTO", "✕", "#00c853"
                    )
                else:
                    beta_texto, beta_icono, beta_color = (
                        "INCORRECTO", "✕", "#ef4444"
                    )
                beta_fondo = (
                    "rgba(0,200,83,.12)"
                    if verificacion_beta_ok or verificacion_beta_favorable
                    else "rgba(239,68,68,.12)"
                )
                beta_borde = (
                    "rgba(0,200,83,.55)"
                    if verificacion_beta_ok or verificacion_beta_favorable
                    else "rgba(239,68,68,.55)"
                )
                estado_resumen_real.markdown(
                        "<div style='display:flex;align-items:center;"
                        "justify-content:space-between;gap:.8rem;margin:0 0 .8rem 0;"
                        f"padding:.75rem .9rem;border:1px solid {beta_borde};"
                        f"border-radius:1rem;background:{beta_fondo};'>"
                        "<div style='font-size:1.4rem;font-weight:700;"
                        "line-height:1.15;white-space:nowrap;'>"
                        "Resultado de la verificación real: "
                        f"<span style='display:inline;color:{beta_color};"
                        f"font-size:2.4rem;font-weight:800;margin-left:.35rem;'"
                        f">{beta_texto}</span>"
                        "</div>"
                        f"<div style='color:{beta_color};font-size:2.8rem;"
                        f"font-weight:800;'>{beta_icono}</div></div>",
                        unsafe_allow_html=True,
                )
                metric_factura_resumen.metric(
                    "Total factura", formato_euros(factura.total)
                )
                metric_verificado_resumen.metric(
                    "Total verificado",
                    formato_euros(reconstruccion_beta["total_verificado"]),
                )
                metric_diferencia_resumen.metric(
                    "Factura − verificado",
                    formato_euros(reconstruccion_beta["diferencia_total"]),
                    delta=(
                        formato_pct(
                            reconstruccion_beta["diferencia_total"]
                            / reconstruccion_beta["total_verificado"]
                            * 100
                        )
                        if abs(reconstruccion_beta["total_verificado"]) > 0.000001
                        else None
                    ),
                    delta_color="inverse",
                )
                titulo_resumen_componentes.markdown(
                    "#### Resumen verificación componentes"
                )
                tabla_total_beta_mostrar = formatear_columnas_tabla(
                    tabla_total_beta,
                    columnas_euros=[
                        "Factura (€)",
                        "Verificado (€)",
                        "Diferencia (€)",
                    ],
                    columnas_pct=["Desvío (%)"],
                    incluir_unidades=False,
                )

                def colorear_estados(dataframe):
                    estilos = pd.DataFrame(
                        "", index=dataframe.index, columns=dataframe.columns
                    )
                    for indice in dataframe.index:
                        impacto = impactos_tabla_beta.loc[indice]
                        color = "#00c853" if impacto != "contra" else "#ef4444"
                        estilos.loc[indice, "Estado"] = (
                            f"color:{color};font-size:1.5rem;font-weight:900;"
                            f"-webkit-text-stroke:0.65px {color};"
                            "background-color:transparent;"
                            "text-align:center !important"
                        )
                        if impacto != "correcto":
                            estilo_diferencia = (
                                f"color:{color};font-weight:800;"
                                "background-color:transparent;"
                            )
                            estilos.loc[indice, "Diferencia (€)"] = (
                                estilo_diferencia
                            )
                            estilos.loc[indice, "Desvío (%)"] = (
                                estilo_diferencia
                            )
                    return estilos

                tabla_resumen_componentes.dataframe(
                        tabla_total_beta_mostrar.style.apply(
                            colorear_estados, axis=None
                        ).set_properties(
                            subset=["Estado"],
                            **{"text-align": "center"},
                        ).set_table_styles([{
                            "selector": "th.col_heading.level0.col5",
                            "props": [("text-align", "center")],
                        }]),
                        hide_index=True,
                        use_container_width=True,
                )
                if not reparto_energia_potencia.empty:
                    grafico_componentes.markdown("#### Potencia y Energía")
                    figura_reparto_contrato = px.pie(
                        reparto_energia_potencia,
                        names="Componente",
                        values="Importe (€)",
                        hole=0.48,
                        color="Componente",
                        color_discrete_map={
                            "Energía": "#e74c3c",
                            "Potencia": "#3498db",
                        },
                    )
                    figura_reparto_contrato.update_traces(
                        textinfo="label+percent",
                        textposition="inside",
                        textfont=dict(size=17, color="white"),
                        hovertemplate=(
                            "%{label}<br>%{value:.2f} €<br>"
                            "%{percent}<extra></extra>"
                        ),
                    )
                    figura_reparto_contrato.update_layout(
                        height=165,
                        margin=dict(l=5, r=5, t=0, b=0),
                        showlegend=False,
                    )
                    figura_reparto_contrato = aplicar_estilo(
                        figura_reparto_contrato
                    )
                    figura_reparto_contrato.update_layout(
                        title=None,
                        title_text=None,
                        height=400,
                        margin=dict(l=0, r=0, t=0, b=0),
                        showlegend=False,
                    )
                    grafico_componentes.plotly_chart(
                        figura_reparto_contrato,
                        use_container_width=True,
                        key=f"factura_reparto_contrato_{huella[:8]}",
                        config={"displayModeBar": False},
                    )

                def categoria_componente(nombre):
                    texto_componente = str(nombre).lower()
                    if nombre in {"Potencia", "Energía", "IEE", "IVA"}:
                        return nombre
                    if "exceso" in texto_componente:
                        return "Excesos"
                    if "reactiva" in texto_componente:
                        return "Reactiva"
                    if (
                        "alquiler" in texto_componente
                        and any(
                            termino in texto_componente
                            for termino in ("medida", "contador", "equipo")
                        )
                    ):
                        return "AM"
                    return "Otros"

                reparto_todos_componentes = tabla_total_beta.loc[
                    tabla_total_beta["Componente"] != "TOTAL",
                    ["Componente", "Verificado (€)"],
                ].copy()
                reparto_todos_componentes["Categoría"] = (
                    reparto_todos_componentes["Componente"].map(
                        categoria_componente
                    )
                )
                reparto_todos_componentes = (
                    reparto_todos_componentes.groupby(
                        "Categoría", as_index=False
                    )["Verificado (€)"].sum()
                )
                reparto_todos_componentes = reparto_todos_componentes[
                    reparto_todos_componentes["Verificado (€)"] > 0
                ]
                if not reparto_todos_componentes.empty:
                    figura_todos_componentes = px.pie(
                        reparto_todos_componentes,
                        names="Categoría",
                        values="Verificado (€)",
                        hole=0.48,
                        title="Todos los componentes",
                    )
                    figura_todos_componentes.update_traces(
                        textinfo="label+percent",
                        textposition="inside",
                        textfont=dict(size=16, family="Arial"),
                        hovertemplate=(
                            "%{label}<br>%{value:.2f} €<br>"
                            "%{percent}<extra></extra>"
                        ),
                    )
                    figura_todos_componentes.update_layout(
                        height=400,
                        margin=dict(l=0, r=0, t=55, b=0),
                        showlegend=False,
                    )
                    figura_todos_componentes = aplicar_estilo(
                        figura_todos_componentes
                    )
                    figura_todos_componentes.update_layout(
                        height=400, showlegend=False
                    )
                    grafico_componentes.plotly_chart(
                        figura_todos_componentes,
                        use_container_width=True,
                        key=f"factura_todos_componentes_{huella[:8]}",
                        config={"displayModeBar": False},
                    )
                grafico_componentes.metric(
                    "Energía facturada",
                    formato_euros(energia_facturada_comparable),
                )
                grafico_componentes.metric(
                    "Energía según medida",
                    formato_euros(coste_energia_medida),
                )
                grafico_componentes.metric(
                    "Diferencia energía",
                    formato_euros(
                        energia_facturada_comparable - coste_energia_medida
                    ),
                    delta_color="inverse",
                )
                desvio_total_pct = (
                    reconstruccion_beta["diferencia_total"]
                    / reconstruccion_beta["total_verificado"]
                    * 100
                    if abs(reconstruccion_beta["total_verificado"]) > 0.000001
                    else 0.0
                )
                maximo_gauge_pct = 1.0
                valor_gauge = max(
                    -maximo_gauge_pct,
                    min(maximo_gauge_pct, desvio_total_pct),
                )
                color_gauge = (
                    "#00a651" if desvio_total_pct <= 0.5 else "#ef4444"
                )
                ancho_arco = abs(valor_gauge) / maximo_gauge_pct * 90
                centro_arco = (
                    90 - ancho_arco / 2
                    if valor_gauge >= 0 else 90 + ancho_arco / 2
                )
                figura_desvio = go.Figure()
                figura_desvio.add_trace(go.Barpolar(
                    r=[0.28, 0.28],
                    theta=[135, 45],
                    width=[90, 90],
                    base=[0.72, 0.72],
                    marker_color=["rgba(0,166,81,.16)", "rgba(239,68,68,.16)"],
                    marker_line_width=0,
                    hoverinfo="skip",
                    showlegend=False,
                ))
                if ancho_arco > 0:
                    figura_desvio.add_trace(go.Barpolar(
                        r=[0.28],
                        theta=[centro_arco],
                        width=[ancho_arco],
                        base=[0.72],
                        marker_color=color_gauge,
                        marker_line_width=0,
                        hovertemplate=(
                            f"Desvío: {desvio_total_pct:.2f} %<extra></extra>"
                        ),
                        showlegend=False,
                    ))
                figura_desvio.add_trace(go.Scatterpolar(
                    r=[0.68, 1.05],
                    theta=[45, 45],
                    mode="lines",
                    line=dict(color="#ef4444", width=3),
                    hoverinfo="skip",
                    showlegend=False,
                ))
                figura_desvio.add_annotation(
                    x=0.5,
                    y=1.18,
                    text="<b>Desvío total</b>",
                    showarrow=False,
                    font=dict(size=17),
                )
                figura_desvio.add_annotation(
                    x=0.5,
                    y=0.02,
                    xref="paper",
                    yref="paper",
                    text=f"<b>{desvio_total_pct:.2f} %</b>",
                    showarrow=False,
                    font=dict(size=42, color=color_gauge),
                )
                for posicion_x, posicion_y, etiqueta in (
                    (0.13, 0.02, "−1 %"),
                    (0.5, 1.07, "0 %"),
                    (0.87, 0.02, "+1 %"),
                ):
                    figura_desvio.add_annotation(
                        x=posicion_x,
                        y=posicion_y,
                        text=etiqueta,
                        showarrow=False,
                        font=dict(size=15),
                    )
                figura_desvio.update_layout(
                    height=235,
                    margin=dict(l=12, r=12, t=45, b=5),
                    paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Arial"),
                    polar=dict(
                        sector=[0, 180],
                        radialaxis=dict(visible=False, range=[0, 1.08]),
                        angularaxis=dict(visible=False),
                        bgcolor="rgba(0,0,0,0)",
                    ),
                    barmode="overlay",
                    showlegend=False,
                )
                gauge_resumen_real.plotly_chart(
                    figura_desvio,
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key=f"factura_gauge_desvio_{huella[:8]}",
                )
                if not verificacion_iee_beta or not verificacion_iva_beta:
                    col_costes_resultado.warning(
                        "No se ha podido recalcular completamente IEE o IVA; se "
                        "mantiene el importe facturado del impuesto sin referencia."
                    )


with tab_comparativa:
    col_formula, col_resultado, col_visual = st.columns([0.30, 0.34, 0.36])

    if factura is None:
        with col_formula:
            st.subheader("Comparativa de energía", divider="rainbow")
            st.info("Carga una factura válida en la pestaña Análisis.")
    else:
        st.session_state.zona_periodos_index = "peninsula"
        atr_indexado = _atr_indexado(factura.atr)
        inicio_indexado = _fecha_factura(factura.periodo_inicio)
        fin_indexado = _fecha_factura(factura.periodo_fin)

        with col_formula:
            st.subheader("Propuesta", divider="rainbow")

            st.markdown("#### Término de potencia")
            with st.container(border=True):
                persist_widget(
                    st.radio,
                    "Tratamiento del precio de potencia",
                    [
                        "Mantener precios de factura",
                        "Aplicar precios BOE",
                        "Personalizar con margen",
                    ],
                    key="factura_modo_precio_potencia",
                    default="Aplicar precios BOE",
                )
                if (
                    st.session_state.get("factura_modo_precio_potencia")
                    == "Personalizar con margen"
                ):
                    persist_widget(
                        st.number_input,
                        "Margen a añadir (€/kW año)",
                        min_value=0.0,
                        max_value=100.0,
                        step=0.1,
                        key="factura_margen_potencia_personalizado",
                        default=0.0,
                    )
                    st.caption(
                        "Margen único añadido al precio de todos los periodos."
                    )

            st.markdown("#### Término de energía")
            with st.container(border=True):
                persist_widget(
                    st.radio,
                    "Tipo de propuesta de energía",
                    ["Indexado", "Fijo"],
                    key="factura_tipo_energia",
                    default="Indexado",
                    horizontal=True,
                )
                if st.session_state.get("factura_tipo_energia") == "Fijo":
                    numero_periodos = 3 if atr_indexado == "2.0" else 6
                    columnas_precios = st.columns(3)
                    for indice in range(1, numero_periodos + 1):
                        with columnas_precios[(indice - 1) % 3]:
                            persist_widget(
                                st.number_input,
                                f"P{indice} (€/kWh)",
                                min_value=0.0,
                                max_value=2.0,
                                step=0.001,
                                format="%.6f",
                                key=f"factura_precio_fijo_p{indice}",
                                default=0.0,
                            )
                    st.caption(
                        "Introduce precios en los periodos con consumo real; los "
                        "periodos sin consumo pueden quedar a cero. Si la factura "
                        "no ofrece desglose y la propuesta tiene precio único, "
                        f"introduce el mismo valor en las {numero_periodos} casillas."
                    )
                else:
                    st.caption(
                        "Configuración compartida con Telemindex durante esta sesión."
                    )
                    mostrar_parametros_formula_indexado(
                        widget_suffix="factura_propuesta"
                    )

            if st.session_state.get("factura_tipo_energia") == "Indexado":
                if inicio_indexado and fin_indexado:
                    st.info(
                        f"Periodo trasladado: {inicio_indexado:%d/%m/%Y} → "
                        f"{fin_indexado:%d/%m/%Y} · ATR "
                        f"{factura.atr or 'no detectado'}"
                    )
                else:
                    st.warning("La factura no contiene un periodo válido.")

            calcular = st.button(
                "Calcular comparativa",
                type="primary",
                use_container_width=True,
                disabled=atr_indexado is None,
            )

            if calcular:
                try:
                    if st.session_state.get("factura_tipo_energia") == "Fijo":
                        resultado_nuevo = _calcular_comparativa_fijo(factura)
                    else:
                        with st.spinner("Cargando precios y calculando el periodo…"):
                            medida_sesion = st.session_state.get(
                                "factura_verificacion_consumos"
                            )
                            medida_propuesta = (
                                medida_sesion.get("resultado")
                                if medida_sesion
                                and medida_sesion.get("huella") == huella
                                else None
                            )
                            resultado_nuevo = _calcular_comparativa_indexado(
                                factura, medida_propuesta
                            )
                except Exception as exc:
                    st.session_state.pop("factura_comparativa_indexado", None)
                    st.error(str(exc))
                else:
                    st.session_state.factura_comparativa_indexado = {
                        "huella": huella,
                        "firma": _firma_propuesta_energia(atr_indexado),
                        "resultado": resultado_nuevo,
                    }

        comparativa_sesion = st.session_state.get("factura_comparativa_indexado")
        resultado = None
        if (
            comparativa_sesion
            and comparativa_sesion.get("huella") == huella
            and comparativa_sesion.get("firma")
            == _firma_propuesta_energia(atr_indexado)
        ):
            resultado = comparativa_sesion["resultado"]

        with col_resultado:
            st.subheader("Resultado", divider="rainbow")
            if resultado is None:
                st.info(
                    "Pulsa «Calcular comparativa» para valorar el término de energía "
                    "con la propuesta indicada."
                )
            else:
                tipo_propuesta = resultado.get("tipo", "Indexado")
                tipo_propuesta_minusculas = tipo_propuesta.lower()
                if resultado.get("metodo_calculo") == "curva_horaria":
                    st.caption(
                        "Método: precio horario Telemindex ponderado con la curva "
                        "real de consumo."
                    )
                elif resultado.get("metodo_calculo") == "consumo_agregado_periodos":
                    st.caption(
                        "Método aproximado: precio medio por periodo tarifario "
                        "ponderado con los consumos de la factura (sin curva)."
                    )
                diferencia_energia_pct = (
                    resultado["diferencia"] / resultado["coste_facturado"] * 100
                    if resultado["coste_facturado"]
                    else None
                )
                df_comparativa_componentes = _componentes_propuesta(
                    factura, resultado
                )
                total_factura = df_comparativa_componentes["Factura (€)"].sum()
                total_propuesta = df_comparativa_componentes["Propuesta (€)"].sum()
                diferencia_total = total_propuesta - total_factura
                diferencia_total_pct = (
                    diferencia_total / total_factura * 100
                    if total_factura
                    else None
                )
                propuesta_mejor = diferencia_total <= 0
                aviso_icono = "🚀" if propuesta_mejor else "🛑"
                aviso_color = "#00c853" if propuesta_mejor else "#ef4444"
                aviso_fondo = (
                    "rgba(0,200,83,.12)"
                    if propuesta_mejor
                    else "rgba(239,68,68,.12)"
                )
                aviso_borde = (
                    "rgba(0,200,83,.55)"
                    if propuesta_mejor
                    else "rgba(239,68,68,.55)"
                )
                aviso_texto = (
                    "La propuesta mejora la factura en"
                    if propuesta_mejor
                    else "La propuesta resulta más cara que la factura en"
                )
                diferencia_aviso = formato_euros(abs(diferencia_total))
                porcentaje_aviso = (
                    f" ({formato_pct(abs(diferencia_total_pct), 2)})"
                    if diferencia_total_pct is not None
                    else ""
                )
                st.markdown(
                    "<div style='display:flex;align-items:center;justify-content:"
                    "space-between;gap:1rem;flex-wrap:wrap;margin:1rem 0 .8rem 0;"
                    f"padding:.8rem 1rem;border:1px solid {aviso_borde};"
                    f"border-radius:1rem;background:{aviso_fondo};"
                    "box-shadow:0 4px 14px rgba(0,0,0,.10);'>"
                    "<div style='font-size:1.35rem;font-weight:700;line-height:1.3;'>"
                    f"{aviso_texto} "
                    f"<span style='display:inline-block;color:{aviso_color};"
                    "font-size:2.1rem;margin-left:.55rem;line-height:1.15;'>"
                    f"{diferencia_aviso}{porcentaje_aviso}</span></div>"
                    "<div style='display:flex;align-items:center;justify-content:center;"
                    "width:3.7rem;height:3.7rem;flex:0 0 3.7rem;"
                    "background:transparent;font-size:2.8rem;line-height:1;'>"
                    f"{aviso_icono}</div></div>",
                    unsafe_allow_html=True,
                )
                st.dataframe(
                    _estilar_diferencias_comparativa(
                        df_comparativa_componentes
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
                metrica_total_factura, metrica_total_propuesta, metrica_diferencia = (
                    st.columns(3)
                )
                with metrica_total_factura:
                    st.markdown(
                        "<div style='height:.75rem'></div>",
                        unsafe_allow_html=True,
                    )
                    st.metric("Total factura", formato_euros(total_factura))
                with metrica_total_propuesta:
                    st.markdown(
                        "<div style='height:.75rem'></div>",
                        unsafe_allow_html=True,
                    )
                    st.metric("Total propuesta", formato_euros(total_propuesta))
                with metrica_diferencia.container(border=True):
                    st.metric(
                        "Diferencia",
                        formato_euros(diferencia_total),
                        delta=(
                            formato_pct(diferencia_total_pct, 2)
                            if diferencia_total_pct is not None
                            else None
                        ),
                        delta_color="inverse",
                    )
                st.markdown("#### Detalle del término de energía propuesto")
                detalle_resultado = resultado["detalle"].copy()
                if (
                    "Coste propuesta (€)" not in detalle_resultado.columns
                    and "Coste indexado (€)" in detalle_resultado.columns
                ):
                    detalle_resultado = detalle_resultado.rename(
                        columns={"Coste indexado (€)": "Coste propuesta (€)"}
                    )
                if (
                    "Precio propuesta (€/kWh)" not in detalle_resultado.columns
                    and "Precio indexado (€/kWh)" in detalle_resultado.columns
                ):
                    detalle_resultado = detalle_resultado.rename(
                        columns={
                            "Precio indexado (€/kWh)": "Precio propuesta (€/kWh)"
                        }
                    )
                if "Peso consumo (%)" not in detalle_resultado.columns:
                    detalle_resultado["Peso consumo (%)"] = (
                        detalle_resultado["Consumo (kWh)"]
                        / resultado["consumo_total"]
                        * 100
                    )
                detalle_mostrado = detalle_resultado[
                    [
                        "Periodo",
                        "Consumo (kWh)",
                        "Peso consumo (%)",
                        "Precio propuesta (€/kWh)",
                        "Coste propuesta (€)",
                    ]
                ]
                detalle_mostrado = pd.concat(
                    [
                        detalle_mostrado,
                        pd.DataFrame([{
                            "Periodo": "Total",
                            "Consumo (kWh)": resultado["consumo_total"],
                            "Peso consumo (%)": 100.0,
                            "Precio propuesta (€/kWh)": resultado["precio_indexado"],
                            "Coste propuesta (€)": resultado["coste_indexado"],
                        }]),
                    ],
                    ignore_index=True,
                )
                st.dataframe(
                    formatear_columnas_tabla(
                        detalle_mostrado,
                        columnas_kwh=["Consumo (kWh)"],
                        columnas_pct=["Peso consumo (%)"],
                        columnas_eur_kwh=["Precio propuesta (€/kWh)"],
                        columnas_euros=["Coste propuesta (€)"],
                        decimales_kwh=2,
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
                st.markdown(
                    "<div style='font-size:1.05rem; line-height:1.45; margin-top:0.6rem;'>"
                    "La fila total muestra el precio medio ponderado de la propuesta "
                    "según el peso de consumo de cada periodo."
                    "</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    "<div style='height:1.25rem;'></div>",
                    unsafe_allow_html=True,
                )
                metrica_precio_factura, metrica_precio_propuesta = st.columns(2)
                metrica_precio_factura.metric(
                    "Precio medio facturado",
                    formato_eur_kwh(resultado["precio_facturado"], 5),
                )
                metrica_precio_propuesta.metric(
                    f"Precio medio {tipo_propuesta_minusculas}",
                    formato_eur_kwh(resultado["precio_indexado"], 5),
                    delta=(
                        formato_pct(diferencia_energia_pct, 2)
                        if diferencia_energia_pct is not None
                        else None
                    ),
                    delta_color="inverse",
                )

        with col_visual:
            st.subheader("Gráfico comparativo", divider="rainbow")
            if resultado is not None:
                colores_componentes = {
                    "Potencia": "#2563EB",
                    "Energía": "#F97316",
                    "Excesos": "#DC2626",
                    "Reactiva": "#9333EA",
                    "Otros": "#EAB308",
                    "IEE": "#14B8A6",
                    "IVA": "#EC4899",
                    "Sin asignar": "#64748B",
                }
                df_grafico_componentes = df_comparativa_componentes.melt(
                    id_vars="Componente",
                    value_vars=["Factura (€)", "Propuesta (€)"],
                    var_name="Escenario",
                    value_name="Importe (€)",
                )
                df_grafico_componentes["Escenario"] = (
                    df_grafico_componentes["Escenario"]
                    .str.replace(" (€)", "", regex=False)
                )
                figura_componentes = px.bar(
                    df_grafico_componentes,
                    x="Escenario",
                    y="Importe (€)",
                    color="Componente",
                    barmode="stack",
                    color_discrete_map=colores_componentes,
                    category_orders={
                        "Componente": list(colores_componentes),
                        "Escenario": ["Factura", "Propuesta"],
                    },
                )
                figura_componentes.update_traces(
                    width=0.38,
                    marker_cornerradius=8,
                    hovertemplate=(
                        "<b>%{fullData.name}</b><br>"
                        "%{x}: %{y:,.2f} €<extra></extra>"
                    ),
                )
                for escenario, total in (
                    ("Factura", total_factura),
                    ("Propuesta", total_propuesta),
                ):
                    figura_componentes.add_annotation(
                        x=escenario,
                        y=total,
                        text=f"<b>{formato_euros(total)}</b>",
                        showarrow=False,
                        yshift=22,
                        font=dict(size=24),
                    )
                figura_componentes.update_layout(
                    title_text="",
                    xaxis_title="",
                    yaxis_title="",
                    legend_title_text="",
                    margin=dict(l=10, r=10, t=65, b=10),
                )
                figura_componentes = aplicar_estilo(figura_componentes)
                figura_componentes.update_xaxes(
                    title_text="",
                    tickfont=dict(size=20),
                )
                figura_componentes.update_yaxes(
                    title_text="Coste (€)",
                    title_font=dict(size=20),
                    tickfont=dict(size=16),
                )
                st.plotly_chart(figura_componentes, use_container_width=True)

                margen_potencia_propuesta = _margen_potencia_propuesta(factura)
                margen_energia_propuesta = (
                    resultado["consumo_total"]
                    * (
                        st.session_state.get("margen_telemindex", 0.0)
                        if resultado.get("tipo") == "Indexado"
                        else 0.0
                    )
                    / 1000
                )
                margen_total_propuesta = (
                    margen_potencia_propuesta + margen_energia_propuesta
                )
                st.subheader("Tu beneficio", divider="rainbow")
                with st.container(border=True):
                    col_margen_tp, col_margen_te, col_margen_total = st.columns(3)
                    col_margen_tp.metric(
                        "Término de potencia",
                        formato_euros(margen_potencia_propuesta),
                    )
                    col_margen_te.metric(
                        "Término de energía",
                        formato_euros(margen_energia_propuesta),
                    )
                    col_margen_total.metric(
                        "Margen total",
                        formato_euros(margen_total_propuesta),
                    )
                    st.caption(
                        "Margen comercial nominal correspondiente al periodo "
                        "analizado, antes de IEE e IVA."
                    )

                mostrar_grafico_energia_anterior = False
                if mostrar_grafico_energia_anterior:
                    etiqueta_propuesta = (
                        f"Propuesta {resultado.get('tipo', 'Indexado').lower()}"
                    )
                    df_comparacion = pd.DataFrame(
                        {
                            "Alternativa": ["Factura", etiqueta_propuesta],
                            "Coste de energía (€)": [
                                resultado["coste_facturado"],
                                resultado["coste_indexado"],
                            ],
                        }
                    )
                    figura_comparacion = px.bar(
                        df_comparacion,
                        x="Alternativa",
                        y="Coste de energía (€)",
                        color="Alternativa",
                        color_discrete_map={
                            "Factura": "#ec4899",
                            etiqueta_propuesta: "#1C83E1",
                        },
                    )
                    figura_comparacion.update_traces(
                        width=0.38,
                        marker_cornerradius=12,
                        texttemplate="<b>%{y:,.2f} €</b>",
                        textposition="outside",
                        textfont=dict(size=28),
                        cliponaxis=False,
                    )
                    figura_comparacion.update_layout(
                        title_text="",
                        showlegend=False,
                        margin=dict(l=10, r=10, t=55, b=10),
                    )
                    figura_comparacion = aplicar_estilo(figura_comparacion)
                    st.plotly_chart(figura_comparacion, use_container_width=True)


with tab_informe:
    st.subheader("Informe", divider="rainbow")
    col_informe, col_salida_informe = st.columns([0.40, 0.60])
    contenedor_salida_informe = col_salida_informe.container()
    with col_informe:
        if factura is None:
            st.info(
                "Carga y analiza una factura para preparar los datos del informe."
            )
            contenedor_salida_informe.info(
                "La vista previa aparecerá aquí cuando exista una propuesta."
            )
        else:
            datos_informe = _datos_informe_desde_factura(factura, texto)
            if st.session_state.get("_factura_informe_huella") != huella:
                for clave, valor in datos_informe.items():
                    st.session_state[clave] = valor
                st.session_state["_factura_informe_huella"] = huella
                st.session_state.pop("factura_informe_logo", None)
            else:
                for clave, valor in datos_informe.items():
                    st.session_state.setdefault(clave, valor)

            st.caption(
                "Los datos detectados en la factura son editables. Revisa la "
                "información antes de generar o entregar el informe."
            )
            with st.container(border=True):
                st.markdown("#### Datos del cliente y del suministro")
                col_cliente, col_nif = st.columns([0.68, 0.32])
                persist_widget(
                    col_cliente.text_input,
                    "Cliente / Razón social",
                    key="factura_informe_cliente",
                    default=datos_informe["factura_informe_cliente"],
                )
                persist_widget(
                    col_nif.text_input,
                    "NIF / CIF",
                    key="factura_informe_nif",
                    default=datos_informe["factura_informe_nif"],
                )
                persist_widget(
                    st.text_input,
                    "Dirección",
                    key="factura_informe_direccion",
                    default=datos_informe["factura_informe_direccion"],
                )
                col_cups, col_atr = st.columns([0.68, 0.32])
                persist_widget(
                    col_cups.text_input,
                    "CUPS",
                    key="factura_informe_cups",
                    default=datos_informe["factura_informe_cups"],
                )
                persist_widget(
                    col_atr.text_input,
                    "ATR",
                    key="factura_informe_atr",
                    default=datos_informe["factura_informe_atr"],
                )

            with st.container(border=True):
                st.markdown("#### Datos de la factura")
                col_comercializadora, col_numero = st.columns([0.58, 0.42])
                persist_widget(
                    col_comercializadora.text_input,
                    "Comercializadora",
                    key="factura_informe_comercializadora",
                    default=datos_informe[
                        "factura_informe_comercializadora"
                    ],
                )
                persist_widget(
                    col_numero.text_input,
                    "Número de factura",
                    key="factura_informe_numero",
                    default=datos_informe["factura_informe_numero"],
                )
                col_fecha, col_ciclo = st.columns([0.32, 0.68])
                persist_widget(
                    col_fecha.text_input,
                    "Fecha de factura",
                    key="factura_informe_fecha",
                    default=datos_informe["factura_informe_fecha"],
                )
                persist_widget(
                    col_ciclo.text_input,
                    "Ciclo de facturación",
                    key="factura_informe_ciclo",
                    default=datos_informe["factura_informe_ciclo"],
                )

            with st.container(border=True):
                st.markdown("#### Datos del informe")
                col_autor, col_fecha_informe = st.columns([0.60, 0.40])
                persist_widget(
                    col_autor.text_input,
                    "Realizado por",
                    key="factura_informe_realizado_por",
                    default=datos_informe["factura_informe_realizado_por"],
                )
                persist_widget(
                    col_fecha_informe.text_input,
                    "Fecha de realización",
                    key="factura_informe_fecha_realizacion",
                    default=datos_informe[
                        "factura_informe_fecha_realizacion"
                    ],
                )
                persist_widget(
                    st.text_input,
                    "Objeto de la propuesta",
                    key="factura_informe_objeto",
                    default=datos_informe["factura_informe_objeto"],
                )

            with st.container(border=True):
                st.markdown("#### Personalización")
                logo_informe = st.file_uploader(
                    "Logo para el informe",
                    type=["png", "jpg", "jpeg"],
                    accept_multiple_files=False,
                    key="factura_informe_logo",
                )
                if logo_informe is not None:
                    st.image(logo_informe, width=180)

            contenedor_salida_informe.markdown("#### Resumen comercial")
            if resultado is None:
                contenedor_salida_informe.info(
                    "Calcula primero la propuesta para preparar el resumen comercial."
                )
            else:
                componentes_informe = _componentes_propuesta(factura, resultado)
                total_factura_informe = componentes_informe["Factura (€)"].sum()
                total_propuesta_informe = componentes_informe["Propuesta (€)"].sum()
                diferencia_informe = (
                    total_propuesta_informe - total_factura_informe
                )
                diferencia_pct_informe = (
                    diferencia_informe / total_factura_informe * 100
                    if total_factura_informe else 0.0
                )
                favorable_informe = diferencia_informe <= 0
                maximo_total = max(
                    total_factura_informe, total_propuesta_informe, 0.01
                )
                logo_bytes = (
                    logo_informe.getvalue() if logo_informe is not None else b""
                )
                firma_resumen = hashlib.sha256()
                firma_resumen.update(b"informe-comercial-factura-v6")
                firma_resumen.update((huella or "").encode("utf-8"))
                firma_resumen.update(
                    repr((
                        total_factura_informe,
                        total_propuesta_informe,
                        resultado.get("tipo", "Indexado"),
                        st.session_state.get(
                            "factura_modo_precio_potencia", ""
                        ),
                        *(
                            st.session_state.get(clave, "")
                            for clave in datos_informe
                        ),
                    )).encode("utf-8")
                )
                firma_resumen.update(logo_bytes)
                firma_resumen = firma_resumen.hexdigest()

                if contenedor_salida_informe.button(
                    "Preparar informe comercial",
                    type="primary",
                    use_container_width=True,
                ):
                    logo_data = ""
                    if logo_informe is not None:
                        subtipo_logo = (
                            "jpeg"
                            if logo_informe.type == "image/jpeg"
                            else "png"
                        )
                        logo_data = (
                            f"data:image/{subtipo_logo};base64,"
                            + base64.b64encode(logo_bytes).decode("ascii")
                        )
                    grafico_componentes_data = ""
                    if figura_componentes is not None:
                        try:
                            grafico_png = figura_componentes.to_image(
                                format="png",
                                width=1100,
                                height=520,
                                scale=1.5,
                            )
                            grafico_componentes_data = (
                                "data:image/png;base64,"
                                + base64.b64encode(grafico_png).decode("ascii")
                            )
                        except Exception:
                            contenedor_salida_informe.warning(
                                "No se ha podido incorporar el gráfico a la "
                                "vista previa."
                            )
                    filas_componentes_informe = []
                    for _, fila in componentes_informe.iterrows():
                        diferencia_fila = float(fila["Diferencia (€)"])
                        porcentaje_fila = fila["Diferencia (%)"]
                        clase_fila = (
                            "favorable"
                            if diferencia_fila < -0.005
                            else "unfavorable"
                            if diferencia_fila > 0.005
                            else "neutral"
                        )
                        filas_componentes_informe.append({
                            "componente": escape(str(fila["Componente"])),
                            "factura": formato_euros(fila["Factura (€)"]),
                            "propuesta": formato_euros(fila["Propuesta (€)"]),
                            "diferencia": formato_euros(diferencia_fila),
                            "diferencia_pct": (
                                formato_pct(porcentaje_fila, 2)
                                if porcentaje_fila is not None
                                and not pd.isna(porcentaje_fila)
                                else "—"
                            ),
                            "clase": clase_fila,
                        })

                    diferencias_relevantes = componentes_informe.loc[
                        componentes_informe["Diferencia (€)"].abs() > 0.005
                    ]
                    if diferencias_relevantes.empty:
                        insight_principal = (
                            "La propuesta no modifica el coste total de los "
                            "componentes analizados."
                        )
                    else:
                        indice_principal = (
                            diferencias_relevantes["Diferencia (€)"].idxmin()
                            if favorable_informe
                            else diferencias_relevantes["Diferencia (€)"].idxmax()
                        )
                        fila_principal = componentes_informe.loc[indice_principal]
                        impacto_principal = float(
                            fila_principal["Diferencia (€)"]
                        )
                        insight_principal = (
                            f"El componente {fila_principal['Componente']} "
                            + (
                                "reduce el coste en "
                                if impacto_principal < 0
                                else "incrementa el coste en "
                            )
                            + formato_euros(abs(impacto_principal))
                            + "."
                        )

                    filas_energia = componentes_informe.loc[
                        componentes_informe["Componente"] == "Energía"
                    ]
                    if filas_energia.empty:
                        insight_energia = (
                            "No hay un término de energía comparable disponible."
                        )
                    else:
                        fila_energia = filas_energia.iloc[0]
                        insight_energia = (
                            f"Pasa de "
                            f"{formato_euros(fila_energia['Factura (€)'])} "
                            f"a "
                            f"{formato_euros(fila_energia['Propuesta (€)'])}, "
                            f"con un precio medio de propuesta de "
                            f"{formato_eur_kwh(resultado['precio_indexado'], 5)}."
                        )
                    filas_potencia = componentes_informe.loc[
                        componentes_informe["Componente"] == "Potencia"
                    ]
                    modo_potencia = st.session_state.get(
                        "factura_modo_precio_potencia",
                        "Aplicar precios BOE",
                    )
                    if filas_potencia.empty:
                        insight_potencia = (
                            f"{modo_potencia}. No hay un término de potencia "
                            "comparable disponible."
                        )
                    else:
                        fila_potencia = filas_potencia.iloc[0]
                        insight_potencia = (
                            f"{modo_potencia}. El coste pasa de "
                            f"{formato_euros(fila_potencia['Factura (€)'])} a "
                            f"{formato_euros(fila_potencia['Propuesta (€)'])}."
                        )

                    detalle_energia = resultado["detalle"].copy()
                    if "Peso consumo (%)" not in detalle_energia:
                        detalle_energia["Peso consumo (%)"] = (
                            detalle_energia["Consumo (kWh)"]
                            / resultado["consumo_total"]
                            * 100
                        )
                    filas_energia_tecnica = [
                        {
                            "periodo": escape(str(fila["Periodo"])),
                            "consumo": formato_kwh(fila["Consumo (kWh)"]),
                            "peso": formato_pct(
                                fila["Peso consumo (%)"], 2
                            ),
                            "precio": formato_eur_kwh(
                                fila["Precio propuesta (€/kWh)"], 6
                            ),
                            "coste": formato_euros(
                                fila["Coste propuesta (€)"]
                            ),
                        }
                        for _, fila in detalle_energia.iterrows()
                    ]

                    modo_potencia_informe = st.session_state.get(
                        "factura_modo_precio_potencia",
                        "Aplicar precios BOE",
                    )
                    margen_potencia = st.session_state.get(
                        "factura_margen_potencia_personalizado", 0.0
                    )
                    filas_potencia_tecnica = []
                    for item in factura.potencia_periodos:
                        if modo_potencia_informe == "Mantener precios de factura":
                            coste_potencia_periodo = item.coste_facturado_eur
                        elif modo_potencia_informe == "Aplicar precios BOE":
                            coste_potencia_periodo = item.coste_boe_eur
                        else:
                            coste_potencia_periodo = (
                                item.coste_boe_eur
                                + item.potencia_kw
                                * item.dias
                                * margen_potencia
                                / 365
                            )
                        potencia_es = (
                            f"{item.potencia_kw:,.2f}"
                            .replace(",", "X")
                            .replace(".", ",")
                            .replace("X", ".")
                        )
                        filas_potencia_tecnica.append({
                            "periodo": escape(str(item.periodo)),
                            "potencia": f"{potencia_es} kW",
                            "dias": str(item.dias),
                            "factura": formato_euros(
                                item.coste_facturado_eur
                            ),
                            "propuesta": formato_euros(
                                coste_potencia_periodo
                            ),
                        })

                    filas_impuestos_tecnica = []
                    parametros_iee_informe = _parametros_iee_propuesta(factura)
                    for impuesto in ("IEE", "IVA"):
                        filas_impuesto = componentes_informe.loc[
                            componentes_informe["Componente"] == impuesto
                        ]
                        if filas_impuesto.empty:
                            continue
                        fila_impuesto = filas_impuesto.iloc[0]
                        if impuesto == "IEE" and parametros_iee_informe:
                            tipo_impuesto = formato_pct(
                                parametros_iee_informe[1], 6
                            )
                        elif impuesto == "IVA" and factura.verificacion_iva:
                            tipo_impuesto = formato_pct(
                                factura.verificacion_iva.tipo_pct, 2
                            )
                        else:
                            tipo_impuesto = "No disponible"
                        filas_impuestos_tecnica.append({
                            "impuesto": impuesto,
                            "tipo": tipo_impuesto,
                            "factura": formato_euros(
                                fila_impuesto["Factura (€)"]
                            ),
                            "propuesta": formato_euros(
                                fila_impuesto["Propuesta (€)"]
                            ),
                        })

                    parametros_formula = []
                    if resultado.get("tipo") == "Indexado":
                        parametros_formula = [
                            {
                                "nombre": "Desvíos apantallados",
                                "valor": formato_eur_mwh(
                                    st.session_state.get(
                                        "desvios_apant", 0.0
                                    ), 2
                                ),
                            },
                            {
                                "nombre": "Margen",
                                "valor": formato_eur_mwh(
                                    st.session_state.get(
                                        "margen_telemindex", 0.0
                                    ), 2
                                ),
                            },
                            {
                                "nombre": "Posición del margen",
                                "valor": escape(str(st.session_state.get(
                                    "cfg_margen_pos", "tm"
                                ))),
                            },
                            {
                                "nombre": "FNEE",
                                "valor": (
                                    "Incluido"
                                    if st.session_state.get("cfg_fnee", True)
                                    else "No incluido"
                                ),
                            },
                            {
                                "nombre": "Posición del FNEE",
                                "valor": (
                                    escape(str(st.session_state.get(
                                        "cfg_fnee_pos", "perdidas"
                                    )))
                                    if st.session_state.get("cfg_fnee", True)
                                    else "No aplica"
                                ),
                            },
                            {
                                "nombre": "Coste financiero",
                                "valor": formato_pct(
                                    st.session_state.get("cf_pct", 0.0), 2
                                ),
                            },
                        ]
                    else:
                        parametros_formula = [{
                            "nombre": "Modalidad",
                            "valor": "Precios fijos por periodo",
                        }]

                    hipotesis_tecnicas = [
                        "Se mantiene el consumo registrado en la factura.",
                        "La propuesta modifica únicamente los términos "
                        "parametrizados por el usuario.",
                        "Los conceptos sin propuesta específica conservan el "
                        "importe facturado.",
                        "IEE e IVA se recalculan sobre las bases resultantes "
                        "cuando existen datos suficientes para contrastarlos.",
                        "No se utiliza curva de carga para ponderar el término "
                        "de energía; se emplea el consumo facturado por periodo.",
                    ]
                    contexto_resumen = {
                        "logo": logo_data,
                        "cliente": escape(
                            st.session_state.get(
                                "factura_informe_cliente", ""
                            )
                        ),
                        "cups": escape(
                            st.session_state.get("factura_informe_cups", "")
                        ),
                        "numero_factura": escape(
                            st.session_state.get(
                                "factura_informe_numero", ""
                            )
                        ),
                        "ciclo": escape(
                            st.session_state.get(
                                "factura_informe_ciclo", ""
                            )
                        ),
                        "realizado_por": escape(
                            st.session_state.get(
                                "factura_informe_realizado_por", ""
                            )
                        ),
                        "fecha_realizacion": escape(
                            st.session_state.get(
                                "factura_informe_fecha_realizacion", ""
                            )
                        ),
                        "objeto_propuesta": escape(
                            st.session_state.get(
                                "factura_informe_objeto", ""
                            )
                        ),
                        "hero_label": (
                            "Ahorro estimado con la propuesta"
                            if favorable_informe
                            else "Sobrecoste estimado de la propuesta"
                        ),
                        "diferencia": formato_euros(abs(diferencia_informe)),
                        "diferencia_pct": formato_pct(
                            abs(diferencia_pct_informe), 2
                        ),
                        "total_factura": formato_euros(
                            total_factura_informe
                        ),
                        "total_propuesta": formato_euros(
                            total_propuesta_informe
                        ),
                        "factura_width": round(
                            total_factura_informe / maximo_total * 100, 2
                        ),
                        "propuesta_width": round(
                            total_propuesta_informe / maximo_total * 100, 2
                        ),
                        "hero_color": (
                            "#15803d" if favorable_informe else "#dc2626"
                        ),
                        "hero_border": (
                            "#86efac" if favorable_informe else "#fca5a5"
                        ),
                        "hero_background": (
                            "#f0fdf4" if favorable_informe else "#fef2f2"
                        ),
                        "highlight_energia": (
                            "Propuesta de energía "
                            f"{resultado.get('tipo', 'Indexado').lower()}."
                        ),
                        "highlight_potencia": (
                            "Término de potencia: "
                            + st.session_state.get(
                                "factura_modo_precio_potencia",
                                "Aplicar precios BOE",
                            ).lower()
                            + "."
                        ),
                        "highlight_periodo": (
                            "Comparación realizada sobre el periodo y consumo "
                            "de la factura analizada."
                        ),
                        "insight_principal": escape(insight_principal),
                        "insight_energia": escape(insight_energia),
                        "insight_potencia": escape(insight_potencia),
                        "filas_componentes": filas_componentes_informe,
                        "grafico_componentes": grafico_componentes_data,
                        "atr": escape(str(factura.atr or "")),
                        "consumo_total": formato_kwh(
                            resultado["consumo_total"]
                        ),
                        "tipo_propuesta": escape(str(
                            resultado.get("tipo", "Indexado")
                        )),
                        "modo_potencia": escape(modo_potencia_informe),
                        "filas_energia_tecnica": filas_energia_tecnica,
                        "filas_potencia_tecnica": filas_potencia_tecnica,
                        "filas_impuestos_tecnica": filas_impuestos_tecnica,
                        "parametros_formula": parametros_formula,
                        "hipotesis_tecnicas": hipotesis_tecnicas,
                    }
                    html_resumen = _renderizar_plantilla_informe(
                        contexto_resumen,
                        "templates/informe_factura_resumen.html",
                    )
                    st.session_state["factura_resumen_comercial"] = {
                        "firma": firma_resumen,
                        "html": html_resumen,
                    }

                resumen_sesion = st.session_state.get(
                    "factura_resumen_comercial"
                )
                if (
                    resumen_sesion
                    and resumen_sesion.get("firma") == firma_resumen
                ):
                    with contenedor_salida_informe.expander(
                        "Vista previa del resumen comercial",
                        expanded=True,
                    ):
                        st.components.v1.html(
                            resumen_sesion["html"],
                            height=900,
                            scrolling=True,
                        )
                        numero_informe = re.sub(
                            r"[^A-Za-z0-9._-]+",
                            "_",
                            str(
                                st.session_state.get(
                                    "factura_informe_numero", ""
                                )
                            ),
                        ).strip("._") or "factura"
                        st.download_button(
                            "Descargar informe HTML",
                            data=resumen_sesion["html"].encode("utf-8"),
                            file_name=f"informe_factura_{numero_informe}.html",
                            mime="text/html; charset=utf-8",
                            use_container_width=True,
                        )
                elif resumen_sesion:
                    contenedor_salida_informe.info(
                        "Los datos han cambiado. Prepara de nuevo el resumen "
                        "para actualizar la vista previa."
                    )
