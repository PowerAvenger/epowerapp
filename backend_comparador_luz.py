"""Motor independiente del Comparador luz, sin dependencias de Streamlit."""

from __future__ import annotations

import numpy as np
import pandas as pd
import re

from backend_indexado import FormulaIndexada, calcular_precios_atr_formula
from backend_ofertas_fijas import resolver_potencia_tarifa


PERIODOS = [f"P{i}" for i in range(1, 7)]


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
        fee = float(pd.to_numeric(oferta.get("Fee (€/MWh)", 0), errors="coerce") or 0)
        precios = pd.Series({
            p: pd.to_numeric(oferta.get(p), errors="coerce") for p in PERIODOS
        })
        precios = precios.fillna(0.0) + fee / 1000
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
        ).upper()
        modalidad = "BOE" if modalidad_original == "BOE" else "CON MARGEN"
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
    for nombre, omie in escenarios.items():
        componentes = grupo.copy()
        componentes["spot"] = componentes["ap_spot"] * float(omie)
        componentes["ssaa"] = (
            componentes["ap_ssaa"] * float(ssaa_previsto) + float(srad_previsto)
        )
        componentes["fnee"] = float(fnee_previsto)
        for tarifa in ("2.0", "3.0", "6.1"):
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
        coste = ponderacion["coste"].sum()
        energia = ponderacion["consumo"].sum()
        filas_resultado.append({
            "Oferta": nombre, "Tipo": "Indexado",
            "Coste energía (€)": coste,
            "Precio medio energía (€/kWh)": coste / energia if energia else np.nan,
        })
    return pd.DataFrame(filas_resultado)


def ofertas_catalogo_para_atr(catalogo: list[dict], atr: str) -> pd.DataFrame:
    filas = []
    for version in catalogo:
        for tarifa in version.get("tarifas", []):
            if tarifa.get("atr") == atr:
                potencia = tarifa.get("potencia") or version.get("potencia") or {}
                comision = tarifa.get("comision") or version.get("comision") or {}
                modalidad_potencia = (
                    "BOE"
                    if str(potencia.get("modalidad", "BOE")).upper() == "BOE"
                    else "CON MARGEN"
                )
                filas.append({
                    "oferta": version["nombre"],
                    "Vigencia desde": version.get("vigencia_desde"),
                    "Vigencia hasta": version.get("vigencia_hasta"),
                    "Fee (€/MWh)": 0.0,
                    "Plataforma": version.get("plataforma"),
                    "Comisión tipo": comision.get("tipo"),
                    "Comisión estimada (€)": comision.get("estimada_eur"),
                    "Comisión (€/MWh)": comision.get("eur_mwh"),
                    "Comisión participación (%)": 100.0,
                    **{p: tarifa.get(p) for p in PERIODOS},
                    "Potencia modalidad": modalidad_potencia,
                    **{
                        f"Potencia {p}": potencia.get(p)
                        for p in PERIODOS
                    },
                })
    return pd.DataFrame(filas)
