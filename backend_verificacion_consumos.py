"""Conciliación independiente entre una factura y una curva de carga."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from calculo_excesos import prorratear_costes_excesos_mensuales

from backend_curvadecarga import (
    agrupar_curva_horaria,
    analizar_cobertura_periodo,
    completar_periodos_curva,
    dataframe_como_archivo_curva,
    normalize_curve_simple,
    recortar_curva_periodo,
    resumir_consumo_por_periodo,
)


FORMATOS_INICIO_INCLUIDO = {
    "naturgy_grandes_clientes",
    "nexus_nuevo",
    "vm_fijo",
    "vm_indexado",
}
COMERCIALIZADORAS_INICIO_INCLUIDO = ("nexus", "vm energía", "vm energia")


def resolver_ciclo_energia(
    fecha_inicio, fecha_fin, *, formato=None, comercializadora=None
):
    """Devuelve el ciclo real de consumo/reactiva según formato o comercializadora."""
    inicio = pd.to_datetime(fecha_inicio, dayfirst=True, errors="coerce")
    fin = pd.to_datetime(fecha_fin, dayfirst=True, errors="coerce")
    if pd.isna(inicio) or pd.isna(fin) or inicio.normalize() > fin.normalize():
        raise ValueError("El periodo de facturación no es válido.")
    formato_normalizado = str(formato or "").strip().casefold()
    comercializadora_normalizada = str(
        comercializadora or ""
    ).strip().casefold()
    inicio_incluido = (
        formato_normalizado in FORMATOS_INICIO_INCLUIDO
        or any(
            nombre in comercializadora_normalizada
            for nombre in COMERCIALIZADORAS_INICIO_INCLUIDO
        )
    )
    inicio_real = inicio.normalize()
    if not inicio_incluido and inicio.normalize() < fin.normalize():
        inicio_real += pd.Timedelta(days=1)
    return inicio_real.date(), fin.normalize().date()


@dataclass
class ResultadoCurvaFactura:
    curva_original: pd.DataFrame
    curva_normalizada: pd.DataFrame
    curva_periodo: pd.DataFrame
    frecuencia: str
    cobertura: dict
    consumos_periodos: dict[str, float]


def preparar_curva_factura(
    curva_original: pd.DataFrame,
    fecha_inicio,
    fecha_fin,
    atr="2.0",
    zona_periodos="peninsula",
    nombre_origen="curva.csv",
    inicio_exclusivo=True,
) -> ResultadoCurvaFactura:
    """Normaliza una curva, asigna periodos y extrae el ciclo de factura."""
    archivo = dataframe_como_archivo_curva(curva_original, nombre_origen)
    return preparar_archivo_factura(
        archivo,
        fecha_inicio,
        fecha_fin,
        atr=atr,
        zona_periodos=zona_periodos,
        nombre_origen=nombre_origen,
        curva_original=curva_original,
        inicio_exclusivo=inicio_exclusivo,
    )


def preparar_archivo_factura(
    archivo,
    fecha_inicio,
    fecha_fin,
    atr="2.0",
    zona_periodos="peninsula",
    nombre_origen=None,
    curva_original=None,
    inicio_exclusivo=True,
) -> ResultadoCurvaFactura:
    """Prepara un único CSV/Excel con el normalizador compartido."""
    return preparar_archivos_factura(
        [archivo],
        fecha_inicio,
        fecha_fin,
        atr=atr,
        zona_periodos=zona_periodos,
        nombres_origen=[nombre_origen] if nombre_origen else None,
        curva_original=curva_original,
        inicio_exclusivo=inicio_exclusivo,
    )


def preparar_archivos_factura(
    archivos,
    fecha_inicio,
    fecha_fin,
    atr="2.0",
    zona_periodos="peninsula",
    nombres_origen=None,
    curva_original=None,
    inicio_exclusivo=True,
) -> ResultadoCurvaFactura:
    """Normaliza y reúne varios CSV/Excel antes de recortar el ciclo."""
    archivos = list(archivos or [])
    if not archivos:
        raise ValueError("Selecciona al menos un archivo de curva.")
    nombres = list(nombres_origen or [])
    normalizadas = []
    originales = []
    frecuencias = []
    for indice, archivo in enumerate(archivos):
        nombre = (
            nombres[indice]
            if indice < len(nombres) and nombres[indice]
            else getattr(archivo, "name", f"curva_{indice + 1}")
        )
        df_in, normalizada, _, periodos_en_origen, calendario, frecuencia = (
            normalize_curve_simple(
                archivo,
                origin=nombre,
                zona_periodos=zona_periodos,
            )
        )
        if not periodos_en_origen:
            normalizada = completar_periodos_curva(normalizada, calendario, atr)
        originales.append(df_in)
        normalizadas.append(normalizada)
        frecuencias.append(frecuencia)
    frecuencias_distintas = set(frecuencias)
    if len(frecuencias_distintas) != 1:
        raise ValueError(
            "Todos los archivos deben tener la misma resolución temporal."
        )
    frecuencia = frecuencias[0]
    normalizada = (
        pd.concat(normalizadas, ignore_index=True)
        .sort_values("fecha_hora")
        .reset_index(drop=True)
    )
    cobertura = analizar_cobertura_periodo(
        normalizada,
        fecha_inicio,
        fecha_fin,
        frecuencia,
        inicio_exclusivo=inicio_exclusivo,
    )
    periodo = recortar_curva_periodo(
        normalizada,
        fecha_inicio,
        fecha_fin,
        inicio_exclusivo=inicio_exclusivo,
    )
    consumos = resumir_consumo_por_periodo(periodo)
    return ResultadoCurvaFactura(
        curva_original=(
            curva_original.copy()
            if curva_original is not None
            else pd.concat(originales, ignore_index=True)
        ),
        curva_normalizada=normalizada,
        curva_periodo=periodo,
        frecuencia=frecuencia,
        cobertura=cobertura,
        consumos_periodos=consumos,
    )


def tabla_conciliacion_consumos(
    consumos_factura: dict[str, float],
    consumos_medida: dict[str, float],
) -> pd.DataFrame:
    """Compara P1–P3 y total conservando diferencias con signo."""
    periodos = sorted(
        set(consumos_factura) | set(consumos_medida),
        key=lambda valor: int(str(valor).upper().removeprefix("P")),
    )
    filas = []
    for periodo in periodos:
        factura = float(consumos_factura.get(periodo, 0.0))
        medida = float(consumos_medida.get(periodo, 0.0))
        filas.append({
            "Periodo": periodo,
            "Factura (kWh)": factura,
            "Medida (kWh)": medida,
            "Diferencia (kWh)": medida - factura,
            "Diferencia (%)": (
                (medida - factura) / factura * 100 if factura else None
            ),
        })
    total_factura = sum(item["Factura (kWh)"] for item in filas)
    total_medida = sum(item["Medida (kWh)"] for item in filas)
    filas.append({
        "Periodo": "Total",
        "Factura (kWh)": total_factura,
        "Medida (kWh)": total_medida,
        "Diferencia (kWh)": total_medida - total_factura,
        "Diferencia (%)": (
            (total_medida - total_factura) / total_factura * 100
            if total_factura else None
        ),
    })
    return pd.DataFrame(filas)


def calcular_energia_fija(
    consumos_periodos: dict[str, float],
    precios_periodos: dict[str, float],
) -> tuple[pd.DataFrame, float]:
    """Valora la medida por periodo con precios fijos confirmados."""
    filas = []
    for periodo in sorted(
        consumos_periodos,
        key=lambda valor: int(str(valor).upper().removeprefix("P")),
    ):
        consumo = float(consumos_periodos[periodo])
        precio = float(precios_periodos.get(periodo, 0.0))
        filas.append({
            "Periodo": periodo,
            "Consumo medida (kWh)": consumo,
            "Precio confirmado (€/kWh)": precio,
            "Coste verificado (€)": consumo * precio,
        })
    detalle = pd.DataFrame(filas)
    return detalle, round(detalle["Coste verificado (€)"].sum(), 2)


def calcular_reactiva_desde_curva(curva_periodo):
    """Calcula la reactiva por periodo usando el ciclo completo ya recortado."""
    from regulacion_reactiva import (
        exceso_reactiva_inductiva,
        factor_potencia,
        precio_reactiva_inductiva,
    )

    requeridas = {"periodo", "consumo_neto_kWh", "reactiva_kVArh"}
    if curva_periodo is None or not requeridas.issubset(curva_periodo.columns):
        raise ValueError("La curva no contiene activa y reactiva por periodo.")
    curva = curva_periodo[list(requeridas)].copy()
    curva["periodo"] = curva["periodo"].astype(str).str.strip().str.upper()
    for columna in ("consumo_neto_kWh", "reactiva_kVArh"):
        curva[columna] = pd.to_numeric(curva[columna], errors="coerce")
    curva = curva.dropna(subset=["periodo", "consumo_neto_kWh", "reactiva_kVArh"])
    if curva.empty:
        raise ValueError("La curva no contiene datos de reactiva utilizables.")

    agrupada = curva.groupby("periodo", as_index=False)[
        ["consumo_neto_kWh", "reactiva_kVArh"]
    ].sum()
    filas = []
    for _, item in agrupada.iterrows():
        periodo = str(item["periodo"])
        activa = float(item["consumo_neto_kWh"])
        reactiva = float(item["reactiva_kVArh"])
        cos_phi = factor_potencia(activa, reactiva)
        exceso = exceso_reactiva_inductiva(activa, reactiva, periodo)
        precio = precio_reactiva_inductiva(cos_phi, periodo)
        filas.append({
            "Periodo": periodo,
            "Activa medida (kWh)": activa,
            "Reactiva medida (kVArh)": reactiva,
            "cos φ": cos_phi,
            "Exceso reactiva (kVArh)": exceso,
            "Precio (€/kVArh)": precio,
            "Coste verificado (€)": exceso * precio,
        })
    detalle = pd.DataFrame(filas).sort_values("Periodo").reset_index(drop=True)
    return detalle, round(float(detalle["Coste verificado (€)"].sum()), 2)


def calcular_energia_indexada(curva_periodo, precios_index, atr, frecuencia):
    """Agrupa la medida a horas y la valora con el precio horario Telemindex."""
    columna_precio = f"precio_{atr}"
    requeridas_curva = {"fecha_hora", "periodo", "consumo_neto_kWh"}
    if not requeridas_curva.issubset(curva_periodo.columns):
        raise ValueError("La curva no contiene fecha, periodo y consumo normalizados.")
    if columna_precio not in precios_index.columns:
        raise ValueError(f"Telemindex no contiene la columna {columna_precio}.")

    curva = curva_periodo[[
        "fecha_hora", "periodo", "consumo_neto_kWh"
    ]].copy()
    curva["fecha_hora"] = pd.to_datetime(curva["fecha_hora"], errors="coerce")
    curva = curva.dropna(subset=["fecha_hora"])
    curva["consumo_neto_kWh"] = pd.to_numeric(
        curva["consumo_neto_kWh"], errors="coerce"
    )
    if curva["consumo_neto_kWh"].isna().any():
        raise ValueError("La curva contiene consumos vacíos o no numéricos.")
    if (curva["consumo_neto_kWh"] < 0).any():
        raise ValueError("La curva contiene consumos negativos.")
    if curva["consumo_neto_kWh"].sum() <= 0:
        raise ValueError("La curva no contiene consumo positivo para ponderar.")
    curva["fecha_hora"] = curva["fecha_hora"].dt.floor("h")
    periodos_por_hora = curva.groupby("fecha_hora")["periodo"].nunique()
    if (periodos_por_hora > 1).any():
        raise ValueError(
            "La curva asigna más de un periodo tarifario a una misma hora."
        )
    curva = (
        curva.groupby("fecha_hora", as_index=False)
        .agg({"periodo": "first", "consumo_neto_kWh": "sum"})
    )
    curva["_fecha"] = curva["fecha_hora"].dt.date
    curva["_hora"] = curva["fecha_hora"].dt.hour
    curva["periodo"] = curva["periodo"].astype(str).str.strip().str.upper()
    periodos_invalidos = ~curva["periodo"].str.fullmatch(r"P[1-6]")
    if periodos_invalidos.any():
        raise ValueError("La curva contiene periodos tarifarios no válidos.")

    precios = precios_index.copy()
    precios["_fecha"] = pd.to_datetime(precios["fecha"], errors="coerce").dt.date
    precios["_hora"] = pd.to_numeric(precios["hora"], errors="coerce")
    precios = precios.dropna(subset=["_fecha", "_hora", columna_precio])
    # Algunas fuentes numeran las horas 1–24 y otras 0–23.
    if not precios.empty and precios["_hora"].min() >= 1 and precios["_hora"].max() == 24:
        precios["_hora"] = precios["_hora"] - 1
    precios = (
        precios.groupby(["_fecha", "_hora"], as_index=False)[columna_precio]
        .mean()
    )
    detalle_intervalos = curva.merge(
        precios, on=["_fecha", "_hora"], how="left", validate="many_to_one"
    )
    sin_precio = detalle_intervalos[columna_precio].isna()
    if sin_precio.any():
        faltantes = detalle_intervalos.loc[sin_precio, "fecha_hora"]
        raise ValueError(
            f"Faltan precios Telemindex para {sin_precio.sum()} intervalos "
            f"({faltantes.min():%d/%m/%Y %H:%M}–{faltantes.max():%d/%m/%Y %H:%M})."
        )
    detalle_intervalos["Precio verificación (€/kWh)"] = (
        pd.to_numeric(detalle_intervalos[columna_precio], errors="raise") / 1000
    )
    detalle_intervalos["Coste verificado (€)"] = (
        pd.to_numeric(detalle_intervalos["consumo_neto_kWh"], errors="raise")
        * detalle_intervalos["Precio verificación (€/kWh)"]
    )
    detalle = (
        detalle_intervalos.groupby("periodo", as_index=False)
        .agg({
            "consumo_neto_kWh": "sum",
            "Coste verificado (€)": "sum",
        })
        .rename(columns={"consumo_neto_kWh": "Consumo medida (kWh)"})
    )
    detalle["Precio verificación (€/kWh)"] = (
        detalle["Coste verificado (€)"] / detalle["Consumo medida (kWh)"]
    )
    detalle = detalle[[
        "periodo", "Consumo medida (kWh)",
        "Precio verificación (€/kWh)", "Coste verificado (€)",
    ]].rename(columns={"periodo": "Periodo"})
    return detalle, round(detalle["Coste verificado (€)"].sum(), 2)


def estado_verificacion_energia_real(
    importe_facturado,
    importe_verificado,
    *,
    cobertura_completa=True,
    precios_completos=True,
    tolerancia_pct=0.5,
    tolerancia_minima_eur=0.02,
):
    """Devuelve el semáforo real del coste de energía."""
    if not cobertura_completa or not precios_completos:
        return "🟡"
    facturado = float(importe_facturado)
    verificado = float(importe_verificado)
    margen = max(
        float(tolerancia_minima_eur),
        max(abs(facturado), abs(verificado)) * float(tolerancia_pct) / 100,
    )
    diferencia = facturado - verificado
    if abs(diferencia) <= margen:
        return "🟢"
    return "🟢 ⚠️" if diferencia < 0 else "🔴"


def calcular_potencia_confirmada(periodos):
    """Calcula potencia × días × precio diario para los valores confirmados."""
    filas = []
    for item in periodos:
        periodo = str(item["periodo"])
        potencia = float(item["potencia_kw"])
        dias = int(item["dias"])
        precio = float(item["precio_eur_kw_dia"])
        filas.append({
            "Periodo": periodo,
            "Potencia confirmada (kW)": potencia,
            "Días": dias,
            "Precio confirmado (€/kW día)": precio,
            "Coste verificado (€)": potencia * dias * precio,
        })
    detalle = pd.DataFrame(filas)
    return detalle, round(detalle["Coste verificado (€)"].sum(), 2)


def debe_prorratear_excesos_tramo(
    inicio, fin, numero_tramos=1, tipo_suministro=None, tarifa=None
):
    """Detecta cambios o una ruptura mensual en puntos de medida 1, 2 y 3."""
    tipo = str(tipo_suministro or "").upper().replace(" ", "")
    tarifa_normalizada = str(tarifa or "").upper().replace(" ", "")
    tipo_prorrateable = tipo in {"1", "2", "3", "TIPO1", "TIPO2", "TIPO3"}
    if not tipo_prorrateable and not tarifa_normalizada.startswith("6.1"):
        return False
    if int(numero_tramos) > 1:
        return True
    inicio = pd.to_datetime(inicio, dayfirst=True, errors="coerce")
    fin = pd.to_datetime(fin, dayfirst=True, errors="coerce")
    if pd.isna(inicio) or pd.isna(fin) or fin < inicio:
        return False
    if inicio.to_period("M") != fin.to_period("M"):
        return False
    dias_ciclo = (fin.normalize() - inicio.normalize()).days + 1
    return dias_ciclo < int(fin.days_in_month)


def calcular_excesos_desde_curva(
    curva_periodo,
    frecuencia,
    tarifa,
    anio,
    potencias,
    prorratear=False,
):
    """Reutiliza el cálculo de Término de potencia para verificar excesos."""
    from backend_opt2 import calcular_costes, meses, pyc_tp, tepp123

    tarifa = str(tarifa or "").replace("TD", "").strip()
    if anio not in pyc_tp or tarifa not in pyc_tp[anio]:
        raise ValueError(f"No hay precios de potencia para {tarifa} en {anio}.")
    if anio not in tepp123 or tarifa not in tepp123[anio]:
        raise ValueError(f"No hay TEPp para {tarifa} en {anio}.")

    curva = curva_periodo.copy()
    curva["fecha_hora"] = pd.to_datetime(curva["fecha_hora"], errors="coerce")
    curva["periodo"] = curva["periodo"].astype(str).str.strip().str.upper()
    curva["mes_nom"] = curva["fecha_hora"].dt.month.map(
        dict(enumerate(meses, start=1))
    )
    consumo = pd.to_numeric(curva["consumo_neto_kWh"], errors="coerce").fillna(0)
    multiplicador_potencia = 4 if str(frecuencia).upper() == "QH" else 1
    curva["potencia"] = consumo * multiplicador_potencia
    curva["periodo_mes"] = curva["fecha_hora"].dt.to_period("M").astype(str)
    maximetros = (
        curva.groupby(["periodo_mes", "periodo"])["potencia"]
        .max()
        .to_dict()
    )

    coeficiente_frecuencia = 2 if str(frecuencia).upper() == "H" else 1
    tepp = {
        periodo: float(valor) * coeficiente_frecuencia
        for periodo, valor in tepp123[anio][tarifa].items()
        if periodo in potencias and valor is not None
    }
    _, _, _, _, costes_brutos = calcular_costes(
        curva,
        tarifa,
        pyc_tp[anio][tarifa],
        tepp,
        meses,
        potencias,
    )
    if prorratear:
        costes, factores_prorrateo = prorratear_costes_excesos_mensuales(
            costes_brutos,
            curva,
        )
    else:
        costes = costes_brutos.copy()
        _, factores_prorrateo = prorratear_costes_excesos_mensuales(
            costes_brutos,
            curva,
        )
        factores_prorrateo.iloc[:, 2] = 1.0
    coste_excesos = float(costes.to_numpy().sum())
    filas = []
    for periodo_mes, fila in costes.iterrows():
        datos_prorrateo = factores_prorrateo.loc[periodo_mes]
        for periodo in potencias:
            importe = float(fila.get(periodo, 0.0))
            importe_bruto = float(
                costes_brutos.loc[periodo_mes].get(periodo, 0.0)
            )
            termino = float(tepp.get(periodo, 0.0))
            filas.append({
                "Mes": str(periodo_mes),
                "Periodo": periodo,
                "Potencia contratada (kW)": float(potencias[periodo]),
                "Maxímetro (kW)": float(
                    maximetros.get((str(periodo_mes), periodo), 0.0)
                ),
                "Raíz Σ excesos² (kW)": (
                    importe_bruto / termino if termino else 0.0
                ),
                "TEPp aplicado (€/kW)": termino,
                "Excesos sin prorrateo (€)": importe_bruto,
                "Días ciclo": int(datos_prorrateo["Días ciclo"]),
                "Días mes": int(datos_prorrateo["Días mes"]),
                "Factor prorrateo": float(
                    datos_prorrateo["Factor prorrateo"]
                ),
                "Excesos verificados (€)": importe,
            })
    return pd.DataFrame(filas), round(float(coste_excesos), 2)


def reconstruir_total_beta(
    *,
    total_factura,
    potencia_facturada,
    potencia_verificada,
    energia_facturada,
    energia_verificada,
    otros_facturados,
    otros_confirmados,
    iee_facturado,
    iva_facturado,
    base_iee_factura=None,
    tipo_iee_pct=None,
    base_iva_factura=None,
    tipo_iva_pct=None,
):
    """Reconstruye el total manteniendo el resto de conceptos por diferencias."""
    otros_facturados = {
        str(clave): float(valor) for clave, valor in otros_facturados.items()
    }
    otros_confirmados = {
        str(clave): float(valor) for clave, valor in otros_confirmados.items()
    }
    delta_potencia = float(potencia_verificada) - float(potencia_facturada)
    delta_energia = float(energia_verificada) - float(energia_facturada)
    delta_otros = sum(
        otros_confirmados.get(clave, valor) - valor
        for clave, valor in otros_facturados.items()
    )

    iee_verificado = float(iee_facturado)
    base_iee_verificada = base_iee_factura
    if base_iee_factura is not None and tipo_iee_pct is not None:
        base_iee_verificada = (
            float(base_iee_factura) + delta_potencia + delta_energia
        )
        iee_verificado = round(
            base_iee_verificada * float(tipo_iee_pct) / 100, 2
        )
    delta_iee = iee_verificado - float(iee_facturado)

    iva_verificado = float(iva_facturado)
    base_iva_verificada = base_iva_factura
    if base_iva_factura is not None and tipo_iva_pct is not None:
        base_iva_verificada = (
            float(base_iva_factura)
            + delta_potencia + delta_energia + delta_otros + delta_iee
        )
        iva_verificado = round(
            base_iva_verificada * float(tipo_iva_pct) / 100, 2
        )
    delta_iva = iva_verificado - float(iva_facturado)
    total_verificado = round(
        float(total_factura)
        + delta_potencia + delta_energia + delta_otros + delta_iee + delta_iva,
        2,
    )
    return {
        "total_verificado": total_verificado,
        "diferencia_total": round(float(total_factura) - total_verificado, 2),
        "potencia_verificada": round(float(potencia_verificada), 2),
        "energia_verificada": round(float(energia_verificada), 2),
        "otros_confirmados": otros_confirmados,
        "base_iee_verificada": base_iee_verificada,
        "iee_verificado": iee_verificado,
        "base_iva_verificada": base_iva_verificada,
        "iva_verificado": iva_verificado,
    }
