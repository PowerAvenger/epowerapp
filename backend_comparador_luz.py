"""Motor independiente del Comparador luz, sin dependencias de Streamlit."""

from __future__ import annotations

import numpy as np
import pandas as pd
import re

from backend_indexado import FormulaIndexada, calcular_precios_atr_formula
from backend_ofertas_fijas import (
    precios_energia_oferta,
    resolver_potencia_tarifa,
)


PERIODOS = [f"P{i}" for i in range(1, 7)]


def referenciar_comparativa_costes(
    resultados: pd.DataFrame,
    referencia: str,
    columna_coste: str = "Coste (€)",
) -> pd.DataFrame:
    """Calcula diferencias de todas las ofertas respecto a una referencia."""
    requeridas = {"Oferta", columna_coste}
    faltantes = requeridas.difference(resultados.columns)
    if faltantes:
        raise ValueError("Faltan columnas: " + ", ".join(sorted(faltantes)))

    salida = resultados.copy()
    salida["Oferta"] = salida["Oferta"].astype(str).str.strip()
    salida[columna_coste] = pd.to_numeric(
        salida[columna_coste], errors="coerce"
    )
    if salida[columna_coste].isna().any():
        raise ValueError("La comparativa contiene costes no válidos.")

    es_referencia = salida["Oferta"].eq(str(referencia).strip())
    if not es_referencia.any():
        raise ValueError("La referencia seleccionada no está en la comparativa.")
    coste_referencia = float(salida.loc[es_referencia, columna_coste].iloc[0])
    salida["Δ referencia (€)"] = salida[columna_coste] - coste_referencia
    salida["Δ referencia (%)"] = np.where(
        coste_referencia != 0,
        salida["Δ referencia (€)"] / coste_referencia * 100,
        np.nan,
    )
    salida["Es referencia"] = es_referencia
    return salida.sort_values(columna_coste, kind="stable").reset_index(drop=True)


def comparar_costes_mensuales(
    curva_indexado: pd.DataFrame,
    curva_seleccion: pd.DataFrame,
) -> pd.DataFrame:
    """Agrega dos curvas comparables en costes mensuales alineados."""
    requeridas = {"fecha", "coste_total"}
    for nombre, curva in (
        ("indexado", curva_indexado), ("selección", curva_seleccion)
    ):
        faltantes = requeridas.difference(curva.columns)
        if faltantes:
            raise ValueError(
                f"La curva de {nombre} no contiene: "
                + ", ".join(sorted(faltantes)) + "."
            )

    def agregar(curva, columna):
        datos = curva[["fecha", "coste_total"]].copy()
        datos["Mes"] = (
            pd.to_datetime(datos["fecha"], errors="coerce")
            .dt.to_period("M").dt.to_timestamp()
        )
        datos["coste_total"] = pd.to_numeric(
            datos["coste_total"], errors="coerce"
        )
        if datos.isna().any().any():
            raise ValueError("Hay fechas o costes no válidos en la comparativa.")
        return datos.groupby("Mes", as_index=False)["coste_total"].sum().rename(
            columns={"coste_total": columna}
        )

    return agregar(curva_indexado, "Coste indexado (€)").merge(
        agregar(curva_seleccion, "Coste selección (€)"),
        on="Mes",
        how="inner",
        validate="one_to_one",
    )


def comparar_costes_mensuales_referenciados(
    curva_referencia: pd.DataFrame,
    curva_seleccion: pd.DataFrame,
) -> pd.DataFrame:
    """Agrega dos escenarios mensuales sin imponer cuál es el indexado."""
    return comparar_costes_mensuales(
        curva_referencia, curva_seleccion
    ).rename(columns={
        "Coste indexado (€)": "Coste referencia (€)",
        "Coste selección (€)": "Coste selección (€)",
    })


def construir_curva_coste_oferta_fija(
    curva_base: pd.DataFrame,
    oferta,
) -> pd.DataFrame:
    """Proyecta una oferta fija sobre el consumo y periodos de una curva."""
    requeridas = {"periodo", "consumo_neto_kWh"}
    faltantes = requeridas.difference(curva_base.columns)
    if faltantes:
        raise ValueError(
            "La curva no contiene: " + ", ".join(sorted(faltantes)) + "."
        )
    salida = curva_base.copy()
    precios = precios_energia_oferta(oferta)
    salida["precio_fijo"] = salida["periodo"].map(precios)
    if salida["precio_fijo"].isna().any():
        raise ValueError("La oferta no tiene precio para todos los periodos usados.")
    salida["coste_total"] = (
        pd.to_numeric(salida["consumo_neto_kWh"], errors="coerce")
        * salida["precio_fijo"]
    )
    if salida["coste_total"].isna().any():
        raise ValueError("La curva contiene consumos no válidos.")
    return salida


def calcular_ahorro_seleccion_vs_indexados(
    resultados: pd.DataFrame,
    oferta_seleccionada: str,
) -> pd.DataFrame:
    """Compara el coste total de una oferta con Indexado A, B y C."""
    requeridas = {"Oferta", "Coste total (€)"}
    faltantes = requeridas.difference(resultados.columns)
    if faltantes:
        raise ValueError("Faltan columnas: " + ", ".join(sorted(faltantes)))

    seleccion = resultados.loc[
        resultados["Oferta"].astype(str).eq(str(oferta_seleccionada))
    ]
    if seleccion.empty:
        raise ValueError("La oferta seleccionada no está en los resultados.")
    coste_seleccion = float(seleccion.iloc[0]["Coste total (€)"])

    nombres_indexados = ["Indexado A", "Indexado B", "Indexado C"]
    indexados = (
        resultados.loc[
            resultados["Oferta"].isin(nombres_indexados),
            ["Oferta", "Coste total (€)"],
        ]
        .drop_duplicates(subset="Oferta", keep="first")
        .set_index("Oferta")
        .reindex(nombres_indexados)
        .dropna(subset=["Coste total (€)"])
        .reset_index()
    )
    indexados["Coste selección (€)"] = coste_seleccion
    indexados["Ahorro (€)"] = (
        indexados["Coste total (€)"] - coste_seleccion
    )
    indexados["Ahorro (%)"] = np.where(
        indexados["Coste total (€)"].ne(0),
        indexados["Ahorro (€)"] / indexados["Coste total (€)"] * 100,
        np.nan,
    )
    return indexados.rename(columns={"Coste total (€)": "Coste indexado (€)"})


def limite_maximo_consumo_oferta(nombre: str) -> float | None:
    """Extrae límites tipo «hasta 10.000 kWh» o «máx. 100.000 kWh»."""
    coincidencia = re.search(
        r"(?:HASTA|M[ÁA]X(?:IMO)?\.?)\s*([\d.]+)\s*KWH",
        str(nombre).upper(),
    )
    if not coincidencia:
        return None
    return float(coincidencia.group(1).replace(".", ""))


def filtrar_ofertas_por_consumo(
    ofertas: pd.DataFrame, consumo_anual_kwh: float
) -> tuple[pd.DataFrame, list[str]]:
    """Descarta ofertas cuyo límite máximo no admite el consumo cargado."""
    if ofertas.empty:
        return ofertas.copy(), []
    limites = ofertas["oferta"].map(limite_maximo_consumo_oferta)
    excluidas = ofertas.loc[
        limites.notna() & limites.lt(float(consumo_anual_kwh)), "oferta"
    ].astype(str).tolist()
    compatibles = ofertas.loc[
        limites.isna() | limites.ge(float(consumo_anual_kwh))
    ].copy()
    return compatibles.reset_index(drop=True), excluidas


def filtrar_ofertas_elegibles(
    ofertas: pd.DataFrame,
    consumo_anual_kwh: float,
    potencias_contratadas: pd.Series | None = None,
    cups: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aplica restricciones comerciales y devuelve el detalle excluido."""
    motivos = {indice: [] for indice in ofertas.index}
    valores_potencia = (
        pd.to_numeric(potencias_contratadas, errors="coerce").dropna()
        if potencias_contratadas is not None else pd.Series(dtype=float)
    )
    potencia_maxima = float(valores_potencia.max()) if not valores_potencia.empty else None
    cups_normalizado = re.sub(r"\s+", "", str(cups or "")).upper()
    for indice, fila in ofertas.iterrows():
        nombre = str(fila["oferta"])
        texto = nombre.upper()
        limite = limite_maximo_consumo_oferta(nombre)
        if limite is not None and consumo_anual_kwh > limite:
            motivos[indice].append(f"supera {limite:,.0f} kWh")
        minimo = re.search(r"M[ÁA]S\s+DE\s+([\d.]+)\s*KWH", texto)
        if minimo and consumo_anual_kwh <= float(minimo.group(1).replace(".", "")):
            motivos[indice].append("no alcanza el consumo mínimo")
        if "RENOVACIÓN" in texto or "RENOVACION" in texto:
            motivos[indice].append("renovación")
        if "MANTENIMIENTO" in texto:
            motivos[indice].append("incluye mantenimiento")
        tramo = re.search(r"(\d+)\s*-\s*(\d+)\s*KW", texto)
        if tramo and potencia_maxima is not None:
            minimo_kw, maximo_kw = map(float, tramo.groups())
            if not (minimo_kw < potencia_maxima <= maximo_kw):
                motivos[indice].append("potencia fuera de tramo")
        es_ide = "I-DE" in texto or "ES0021" in texto
        es_resto = "RESTO DISTRIBUIDORAS" in texto
        if cups_normalizado:
            cups_ide = cups_normalizado.startswith("ES0021")
            if cups_ide and es_resto:
                motivos[indice].append("CUPS I-DE")
            elif not cups_ide and es_ide:
                motivos[indice].append("CUPS no I-DE")
    mascara = pd.Series({i: not lista for i, lista in motivos.items()})
    excluidas = ofertas.loc[~mascara].copy()
    if not excluidas.empty:
        excluidas["Motivo exclusión"] = [
            "; ".join(motivos[i]) for i in excluidas.index
        ]
    return ofertas.loc[mascara].reset_index(drop=True), excluidas.reset_index(drop=True)


def periodo_atr(df: pd.DataFrame, atr: str) -> pd.Series:
    columna = "dh_3p" if atr == "2.0" else "dh_6p"
    if columna not in df:
        raise ValueError(f"No existe la columna {columna}.")
    return df[columna].astype(str).str.upper()


def consumos_por_periodo(df: pd.DataFrame, atr: str) -> pd.Series:
    if "consumo_neto_kWh" not in df:
        raise ValueError("La curva no contiene consumo_neto_kWh.")
    consumo = pd.to_numeric(df["consumo_neto_kWh"], errors="coerce")
    if consumo.isna().any():
        raise ValueError("La curva contiene consumos no numéricos.")
    return consumo.groupby(periodo_atr(df, atr)).sum().reindex(PERIODOS, fill_value=0.0)


def comparar_ofertas_fijas(
    consumos: pd.Series, ofertas: pd.DataFrame
) -> pd.DataFrame:
    filas = []
    energia_total = float(consumos.sum())
    for _, oferta in ofertas.iterrows():
        precios = precios_energia_oferta(oferta)
        coste = float((consumos * precios).sum())
        filas.append({
            "Oferta": oferta["oferta"], "Tipo": "Fijo",
            "Coste energía (€)": coste,
            "Precio medio energía (€/kWh)": coste / energia_total if energia_total else np.nan,
        })
    return pd.DataFrame(filas)


def calcular_costes_potencia(
    potencias_contratadas: pd.Series,
    ofertas: pd.DataFrame,
    dias_por_anio: dict[int, int],
    atr: str,
    fecha_referencia_boe=None,
) -> pd.DataFrame:
    """Calcula potencia fija o BOE para los días efectivos de cada año."""
    potencias = pd.to_numeric(
        potencias_contratadas.reindex(PERIODOS), errors="coerce"
    ).fillna(0.0)
    filas = []
    for _, oferta in ofertas.iterrows():
        modalidad_original = str(
            oferta.get("Potencia modalidad", "BOE")
        ).strip().upper()
        # Las ofertas manuales/IA antiguas pueden no tener modalidad. En
        # ausencia de precios de potencia propios se aplica la referencia BOE.
        modalidad = (
            "CON MARGEN" if modalidad_original == "CON MARGEN" else "BOE"
        )
        coste = 0.0
        for anio, dias in dias_por_anio.items():
            if modalidad == "BOE":
                tarifa = {
                    "atr": atr,
                    "potencia": {"modalidad": "BOE"},
                }
                precios = resolver_potencia_tarifa(
                    tarifa, fecha_referencia_boe or f"{anio}-01-01"
                )
            else:
                precios = {
                    periodo: pd.to_numeric(
                        oferta.get(f"Potencia {periodo}"), errors="coerce"
                    )
                    for periodo in PERIODOS
                }
            coste += sum(
                float(potencias[periodo])
                * (0.0 if pd.isna(precios.get(periodo)) else float(precios[periodo]))
                * int(dias)
                for periodo in PERIODOS
            )
        filas.append({"Oferta": oferta["oferta"], "Coste potencia (€)": coste})
    return pd.DataFrame(filas)


def calcular_escenarios_indexados(
    curva: pd.DataFrame,
    atr: str,
    formula: FormulaIndexada,
    escenarios: dict[str, float],
) -> pd.DataFrame:
    consumo = pd.to_numeric(curva["consumo_neto_kWh"], errors="coerce")
    filas = []
    for nombre, omie in escenarios.items():
        datos = curva.copy()
        datos["spot"] = float(omie)
        calculado = calcular_precios_atr_formula(datos, formula)
        coste = float((calculado[f"precio_{atr}"] * consumo / 1000).sum())
        total = float(consumo.sum())
        filas.append({
            "Oferta": nombre, "Tipo": "Indexado",
            "Coste energía (€)": coste,
            "Precio medio energía (€/kWh)": coste / total if total else np.nan,
        })
    return pd.DataFrame(filas)


def calcular_escenarios_indexados_mensuales(
    referencia: pd.DataFrame,
    consumos_mensuales: pd.DataFrame,
    atr: str,
    formula: FormulaIndexada,
    escenarios: dict[str, float],
    ssaa_previsto: float,
    fnee_previsto: float,
    srad_previsto: float,
) -> pd.DataFrame:
    """Converge curva/SIPS en mes-periodo y pondera con el mismo flujo."""
    datos = referencia.copy()
    datos["fecha"] = pd.to_datetime(datos["fecha"], errors="coerce")
    datos = datos.dropna(subset=["fecha", "spot"])
    datos["mes"] = datos["fecha"].dt.month
    datos["periodo"] = periodo_atr(datos, atr)
    datos["ssaa_sin_srad"] = (
        pd.to_numeric(datos["ssaa"], errors="coerce")
        - pd.to_numeric(datos.get("rad3", 0), errors="coerce")
    )
    grupo = datos.groupby(["mes", "periodo"], as_index=False).agg(
        spot=("spot", "mean"), ssaa=("ssaa_sin_srad", "mean"),
        osom=("osom", "mean"), perd=(f"perd_{atr}", "mean"),
        ppcc=(f"ppcc_{atr}", "mean"), pyc=(f"pyc_{atr}", "mean"),
    )
    media_spot_mes = datos.groupby("mes")["spot"].mean()
    media_ssaa_mes = datos.groupby("mes")["ssaa_sin_srad"].mean().replace(0, np.nan)
    grupo["ap_spot"] = grupo["spot"] / grupo["mes"].map(media_spot_mes)
    grupo["ap_ssaa"] = grupo["ssaa"] / grupo["mes"].map(media_ssaa_mes)
    grupo["ap_ssaa"] = grupo["ap_ssaa"].fillna(1.0)

    consumos = consumos_mensuales.copy()
    if "mes" not in consumos:
        raise ValueError("Los consumos mensuales no contienen la columna mes.")
    detalle_consumo = consumos.melt(
        id_vars=["mes"], value_vars=PERIODOS,
        var_name="periodo", value_name="consumo",
    )
    filas_resultado = []
    filas_detalle = []
    for nombre, omie in escenarios.items():
        componentes = grupo.copy()
        componentes["spot"] = componentes["ap_spot"] * float(omie)
        componentes["ssaa"] = (
            componentes["ap_ssaa"] * float(ssaa_previsto) + float(srad_previsto)
        )
        componentes["fnee"] = float(fnee_previsto)
        for tarifa in ("2.0", "3.0", "6.1", "6.2"):
            componentes[f"ppcc_{tarifa}"] = 0.0
            componentes[f"perd_{tarifa}"] = 0.0
            componentes[f"pyc_{tarifa}"] = 0.0
        componentes[f"ppcc_{atr}"] = componentes["ppcc"]
        componentes[f"perd_{atr}"] = componentes["perd"]
        componentes[f"pyc_{atr}"] = componentes["pyc"]
        calculado = calcular_precios_atr_formula(componentes, formula)
        ponderacion = detalle_consumo.merge(
            calculado[["mes", "periodo", f"precio_{atr}"]],
            on=["mes", "periodo"], how="inner",
        )
        ponderacion["coste"] = (
            ponderacion["consumo"] * ponderacion[f"precio_{atr}"] / 1000
        )
        detalle_escenario = ponderacion[
            ["mes", "periodo", "consumo", f"precio_{atr}", "coste"]
        ].copy()
        detalle_escenario["Oferta"] = nombre
        detalle_escenario = detalle_escenario.rename(columns={
            "mes": "Mes", "periodo": "Periodo", "consumo": "Consumo (kWh)",
            f"precio_{atr}": "Precio (€/MWh)", "coste": "Coste (€)",
        })
        filas_detalle.append(detalle_escenario)
        coste = ponderacion["coste"].sum()
        energia = ponderacion["consumo"].sum()
        filas_resultado.append({
            "Oferta": nombre, "Tipo": "Indexado",
            "Coste energía (€)": coste,
            "Precio medio energía (€/kWh)": coste / energia if energia else np.nan,
        })
    resultado = pd.DataFrame(filas_resultado)
    resultado.attrs["detalle"] = (
        pd.concat(filas_detalle, ignore_index=True)
        if filas_detalle else pd.DataFrame()
    )
    return resultado
