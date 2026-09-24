"""Persistencia local y versionada de ofertas fijas extraídas de imágenes."""

from __future__ import annotations

import json
import hashlib
import os
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd


RUTA_CATALOGO_OFERTAS = Path(__file__).resolve().parent / "data" / "ofertas_fijas.json"
PATRON_CATALOGOS_IMPORTADOS = "ofertas_fijas_importadas_*.json"
PERIODOS = [f"P{i}" for i in range(1, 7)]
ATRS_OFERTA = {"2.0", "3.0", "6.1", "6.2"}
UNIDAD_POTENCIA_DIARIA = "€/kW/día"


def normalizar_atr(atr: str) -> str:
    """Devuelve el ATR en el formato canónico usado por la aplicación."""
    return str(atr or "").upper().replace(" ", "").removesuffix("TD")


def periodos_aplicables_atr(atr: str) -> list[str]:
    """Una 2.0 TD solo tiene precios de energía P1, P2 y P3."""
    return PERIODOS[:3] if normalizar_atr(atr) == "2.0" else PERIODOS.copy()


def periodos_potencia_atr(atr: str) -> list[str]:
    """Devuelve los periodos del término de potencia del peaje."""
    return PERIODOS[:2] if normalizar_atr(atr) == "2.0" else PERIODOS.copy()


def periodos_no_aplicables_atr(atr: str) -> list[str]:
    """Periodos que deben mostrarse vacíos para el ATR indicado."""
    aplicables = set(periodos_aplicables_atr(atr))
    return [periodo for periodo in PERIODOS if periodo not in aplicables]


def periodos_con_consumo(consumos, atr: str) -> tuple[list[str], list[str]]:
    """Devuelve periodos exigibles y periodos aplicables sin consumo."""
    candidatos = periodos_aplicables_atr(atr)
    serie = pd.to_numeric(
        pd.Series(consumos).reindex(candidatos), errors="coerce"
    ).fillna(0)
    activos = [periodo for periodo in candidatos if serie[periodo] > 0]
    activos = activos or candidatos
    return activos, [periodo for periodo in candidatos if periodo not in activos]


def potencia_mensual_a_diaria(valor):
    """Convierte un precio de potencia mensual a su equivalente diario anual."""
    numero = pd.to_numeric(valor, errors="coerce")
    return None if pd.isna(numero) else float(numero) * 12 / 365


def resolver_potencia_tarifa(tarifa: dict, fecha_referencia=None) -> dict | None:
    """Obtiene la potencia diaria fija o resuelve la referencia regulada BOE."""
    potencia = tarifa.get("potencia")
    if not isinstance(potencia, dict):
        return None
    modalidad_original = str(
        potencia.get("modalidad", "CON MARGEN")
    ).upper()
    modalidad = "BOE" if modalidad_original == "BOE" else "CON MARGEN"
    if modalidad == "BOE":
        from backend_opt2 import precios_potencia_boe_diarios

        precios = precios_potencia_boe_diarios(
            tarifa.get("atr"), fecha_referencia
        )
    else:
        precios = {periodo: potencia.get(periodo) for periodo in PERIODOS}
    return {
        "modalidad": modalidad,
        "unidad": UNIDAD_POTENCIA_DIARIA,
        **precios,
    }


def _leer_catalogo(ruta: Path) -> list[dict]:
    ruta = Path(ruta)
    if not ruta.exists():
        return []
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"No se puede leer el catálogo local: {exc}") from exc
    if isinstance(datos, dict) and datos.get("formato") == "campaña_informa_v1":
        potencias = datos.get("potencias", {})
        consumo_anual = float(datos["consumo_anual_kwh"])
        registros = []
        for indice, oferta in enumerate(datos.get("ofertas", []), start=1):
            comision_eur = oferta.get("comision_estimada_eur")
            comision_mwh = oferta.get("comision_eur_mwh")
            tipo_comision = (
                "FIJA" if comision_eur is not None
                else "VARIABLE" if comision_mwh is not None
                else None
            )
            if comision_eur is None and comision_mwh is not None:
                comision_eur = float(comision_mwh) * consumo_anual / 1000
            comision_kwh = (
                float(comision_eur) / consumo_anual
                if comision_eur is not None and consumo_anual else None
            )
            precios_potencia = potencias[oferta["potencia"]]
            registros.append({
                "id": f"{datos['id_campaña']}-{indice:03d}",
                "nombre": oferta["nombre"],
                "vigencia_desde": datos["vigencia_desde"],
                "vigencia_hasta": datos["vigencia_hasta"],
                "guardado_en": datos["guardado_en"],
                "fuente": datos.get("fuente"),
                "plataforma": datos.get("plataforma", "INFORMA"),
                "zona": oferta.get("zona", "Península"),
                "comision": {
                    "tipo": tipo_comision,
                    "estimada_eur": comision_eur,
                    "eur_mwh": comision_mwh,
                    "eur_kwh": comision_kwh,
                    "consumo_anual_kwh": consumo_anual,
                },
                "potencia": {
                    "modalidad": (
                        "BOE" if oferta["potencia"] == "boe" else "CON MARGEN"
                    ),
                    "unidad": UNIDAD_POTENCIA_DIARIA,
                    **dict(zip(PERIODOS, precios_potencia)),
                },
                "tarifas": [{
                    "atr": "3.0",
                    **dict(zip(PERIODOS, oferta["energia"])),
                }],
            })
        return registros
    if not isinstance(datos, list):
        raise ValueError("El catálogo local de ofertas no tiene formato de lista.")
    return datos


def cargar_catalogo_ofertas(ruta=RUTA_CATALOGO_OFERTAS) -> list[dict]:
    ruta = Path(ruta)
    catalogo = _leer_catalogo(ruta)
    if ruta.resolve() == RUTA_CATALOGO_OFERTAS.resolve():
        for ruta_importada in sorted(ruta.parent.glob(PATRON_CATALOGOS_IMPORTADOS)):
            catalogo.extend(_leer_catalogo(ruta_importada))
    return catalogo


def ofertas_catalogo_para_atr(
    catalogo: list[dict],
    atr: str,
    producto_entrega: str | None = None,
) -> pd.DataFrame:
    """Proyecta versiones persistidas al contrato tabular de los comparadores."""
    atr_normalizado = str(atr or "").replace(" ", "").upper().removesuffix("TD")
    filas = []
    for version in catalogo:
        if producto_entrega is not None and str(
            version.get("producto_entrega", "")
        ).strip().upper() != str(producto_entrega).strip().upper():
            continue
        for tarifa in version.get("tarifas", []):
            atr_tarifa = (
                str(tarifa.get("atr", "")).replace(" ", "")
                .upper().removesuffix("TD")
            )
            if atr_tarifa != atr_normalizado:
                continue
            potencia = tarifa.get("potencia") or version.get("potencia") or {}
            comision = tarifa.get("comision") or version.get("comision") or {}
            # Si Informa facilita una comisión por energía, esta prevalece
            # sobre cualquier importe fijo mostrado como estimación.
            tipo_comision = (
                "VARIABLE" if comision.get("eur_mwh") is not None
                else comision.get("tipo")
            )
            filas.append({
                "oferta": version.get("nombre", "Oferta guardada"),
                "ID oferta": version.get("id"),
                "Vigencia desde": version.get("vigencia_desde"),
                "Vigencia hasta": version.get("vigencia_hasta"),
                "Producto entrega": version.get("producto_entrega"),
                "Fee (€/MWh)": 0.0,
                "Plataforma": version.get("plataforma"),
                "Segmento contrato": version.get("segmento_contrato"),
                "Comisión tipo": tipo_comision,
                "Comisión estimada (€)": comision.get("estimada_eur"),
                "Comisión (€/MWh)": comision.get("eur_mwh"),
                "Comisión participación (%)": 100.0,
                **{periodo: tarifa.get(periodo) for periodo in PERIODOS},
                "Potencia modalidad": (
                    "BOE" if str(potencia.get("modalidad", "BOE")).upper() == "BOE"
                    else "CON MARGEN"
                ),
                **{
                    f"Potencia {periodo}": potencia.get(periodo)
                    for periodo in PERIODOS
                },
            })
    return pd.DataFrame(filas)


def precios_energia_oferta(oferta) -> pd.Series:
    """Devuelve P1–P6 en €/kWh con el fee comercial aplicado una sola vez."""
    fee = pd.to_numeric(oferta.get("Fee (€/MWh)", 0), errors="coerce")
    fee = 0.0 if pd.isna(fee) else float(fee)
    precios = pd.Series({
        periodo: pd.to_numeric(oferta.get(periodo), errors="coerce")
        for periodo in PERIODOS
    })
    return precios.fillna(0.0) + fee / 1000


def perdidas_medias_ponderadas(
    curva: pd.DataFrame,
    columna_perdidas: str,
) -> float:
    """Devuelve la pérdida media de la curva ponderada por consumo, en %."""
    requeridas = {"consumo_neto_kWh", columna_perdidas}
    faltantes = requeridas.difference(curva.columns)
    if faltantes:
        raise ValueError(
            "Faltan datos para calcular las pérdidas: "
            + ", ".join(sorted(faltantes)) + "."
        )
    consumo = pd.to_numeric(curva["consumo_neto_kWh"], errors="coerce")
    perdidas = pd.to_numeric(curva[columna_perdidas], errors="coerce")
    if consumo.isna().any() or perdidas.isna().any():
        raise ValueError("La curva contiene consumos o pérdidas no válidos.")
    consumo_total = float(consumo.sum())
    if consumo_total == 0:
        return 0.0
    return float((perdidas * consumo).sum() / consumo_total * 100)


def copiar_oferta_con_horquilla_ssaa(
    oferta,
    nombre: str,
    limite_superior_eur_mwh: float,
    curva: pd.DataFrame,
    columna_perdidas: str | None = None,
    factor_tm: float = 1.015,
) -> tuple[pd.DataFrame, dict]:
    """Crea una variante temporal liquidando mensualmente la horquilla SSAA."""
    nombre = str(nombre or "").strip()
    if not nombre:
        raise ValueError("Indica un nombre para la copia con horquilla SSAA.")
    limite = pd.to_numeric(limite_superior_eur_mwh, errors="coerce")
    if pd.isna(limite) or float(limite) < 0:
        raise ValueError("El límite superior de SSAA no puede ser negativo.")
    requeridas = {"fecha", "ssaa", "consumo_neto_kWh", "coste_ssaa"}
    if columna_perdidas:
        requeridas.add(columna_perdidas)
    faltantes = requeridas.difference(curva.columns)
    if faltantes:
        raise ValueError(
            "Faltan datos para calcular la horquilla SSAA: "
            + ", ".join(sorted(faltantes)) + "."
        )

    datos = curva[list(requeridas)].copy()
    datos["fecha"] = pd.to_datetime(datos["fecha"], errors="coerce")
    for columna in ["ssaa", "consumo_neto_kWh", "coste_ssaa"]:
        datos[columna] = pd.to_numeric(datos[columna], errors="coerce")
    if columna_perdidas:
        datos[columna_perdidas] = pd.to_numeric(
            datos[columna_perdidas], errors="coerce"
        )
    if datos.isna().any().any():
        raise ValueError("La curva contiene datos incompletos para calcular SSAA.")
    datos["Mes"] = datos["fecha"].dt.to_period("M").astype(str)
    datos["Pérdidas ponderadas"] = (
        datos[columna_perdidas] * datos["consumo_neto_kWh"]
        if columna_perdidas else 0.0
    )
    detalle_mensual = datos.groupby("Mes", as_index=False).agg(
        **{
            "SSAA medio (€/MWh)": ("ssaa", "mean"),
            "Consumo (kWh)": ("consumo_neto_kWh", "sum"),
            "Coste SSAA (€)": ("coste_ssaa", "sum"),
            "Pérdidas ponderadas": ("Pérdidas ponderadas", "sum"),
        }
    )
    consumo_mwh = detalle_mensual["Consumo (kWh)"] / 1000
    ssaa_apuntado = detalle_mensual["Coste SSAA (€)"] / consumo_mwh
    detalle_mensual["Apuntamiento SSAA"] = (
        ssaa_apuntado / detalle_mensual["SSAA medio (€/MWh)"]
    ).where(consumo_mwh.gt(0), 0.0).fillna(0.0)
    detalle_mensual["Pérdidas (%)"] = (
        detalle_mensual["Pérdidas ponderadas"]
        / detalle_mensual["Consumo (kWh)"] * 100
    ).where(detalle_mensual["Consumo (kWh)"].ne(0), 0.0).fillna(0.0)
    detalle_mensual = detalle_mensual.drop(columns="Pérdidas ponderadas")
    detalle_mensual["Diferencial (€/MWh)"] = (
        detalle_mensual["SSAA medio (€/MWh)"] - float(limite)
    ).clip(lower=0.0)
    detalle_mensual["Ajuste apuntado (€/MWh)"] = (
        detalle_mensual["Diferencial (€/MWh)"]
        * detalle_mensual["Apuntamiento SSAA"]
    )
    detalle_mensual["Ajuste con pérdidas y TM (€/MWh)"] = (
        detalle_mensual["Ajuste apuntado (€/MWh)"]
        * (1 + detalle_mensual["Pérdidas (%)"] / 100)
        * float(factor_tm)
    )
    detalle_mensual["Sobrecoste (€)"] = (
        detalle_mensual["Ajuste con pérdidas y TM (€/MWh)"] * consumo_mwh
    )
    consumo_kwh = float(detalle_mensual["Consumo (kWh)"].sum())
    sobrecoste = float(detalle_mensual["Sobrecoste (€)"].sum())
    ajuste_eur_mwh = sobrecoste / (consumo_kwh / 1000) if consumo_kwh else 0.0

    copia = pd.DataFrame([dict(oferta)])
    copia.loc[0, "oferta"] = nombre
    for periodo in PERIODOS:
        precio = pd.to_numeric(copia.loc[0, periodo], errors="coerce")
        copia.loc[0, periodo] = (
            pd.NA if pd.isna(precio) else float(precio) + ajuste_eur_mwh / 1000
        )
    copia.loc[0, "Horquilla SSAA superior (€/MWh)"] = float(
        limite
    )
    copia.loc[0, "Ajuste horquilla SSAA (€/MWh)"] = ajuste_eur_mwh
    copia.loc[0, "Oferta origen"] = str(oferta.get("oferta", ""))
    copia.loc[0, "ID oferta"] = pd.NA

    detalle = {
        "version_calculo": 2,
        "nombre": nombre,
        "oferta_origen": str(oferta.get("oferta", "")),
        "limite_superior_eur_mwh": float(limite),
        "ajuste_eur_mwh": ajuste_eur_mwh,
        "consumo_kwh": consumo_kwh,
        "sobrecoste_eur": sobrecoste,
        "perdidas_pct": perdidas_medias_ponderadas(
            curva, columna_perdidas
        ) if columna_perdidas else 0.0,
        "factor_tm": float(factor_tm),
        "detalle_mensual": detalle_mensual,
    }
    return copia, detalle


def eliminar_versiones_oferta(
    ids,
    ruta=RUTA_CATALOGO_OFERTAS,
) -> list[str]:
    """Elimina versiones del catálogo manual y devuelve los ID eliminados."""
    ids_objetivo = {str(valor).strip() for valor in ids if str(valor).strip()}
    if not ids_objetivo:
        return []
    ruta = Path(ruta)
    catalogo = _leer_catalogo(ruta)
    eliminados = [
        str(registro.get("id"))
        for registro in catalogo
        if str(registro.get("id")) in ids_objetivo
    ]
    if not eliminados:
        return []
    catalogo = [
        registro for registro in catalogo
        if str(registro.get("id")) not in ids_objetivo
    ]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(f".{ruta.name}.{uuid4().hex}.tmp")
    temporal.write_text(
        json.dumps(catalogo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporal, ruta)
    return eliminados


def normalizar_tarifas_oferta(tarifas: pd.DataFrame) -> pd.DataFrame:
    """Valida todos los peajes de una oferta antes de guardarlos.

    P4, P5 y P6 no son aplicables a 2.0 TD y se conservan como nulos. En los
    demás peajes sí se exige un precio positivo para P1–P6.
    """
    if not isinstance(tarifas, pd.DataFrame) or tarifas.empty:
        raise ValueError("No hay tarifas que guardar.")
    requeridas = {"ATR", *PERIODOS}
    faltantes = requeridas.difference(tarifas.columns)
    if faltantes:
        raise ValueError("Faltan columnas: " + ", ".join(sorted(faltantes)))

    salida = tarifas.copy()
    salida["ATR"] = (
        salida["ATR"].astype(str).str.strip().str.upper()
        .str.replace(" ", "", regex=False).str.removesuffix("TD")
    )
    atrs_invalidos = sorted(set(salida["ATR"]).difference(ATRS_OFERTA))
    if atrs_invalidos:
        raise ValueError("ATR no compatible: " + ", ".join(atrs_invalidos) + ".")
    duplicados = salida.loc[salida["ATR"].duplicated(), "ATR"].unique().tolist()
    if duplicados:
        raise ValueError(
            "Hay más de una fila para el mismo ATR: "
            + ", ".join(f"{atr}TD" for atr in duplicados) + "."
        )

    for indice, fila in salida.iterrows():
        atr = fila["ATR"]
        aplicables = PERIODOS[:3] if atr == "2.0" else PERIODOS
        invalidos = []
        for periodo in PERIODOS:
            valor = pd.to_numeric(fila.get(periodo), errors="coerce")
            if periodo not in aplicables:
                salida.at[indice, periodo] = None
            elif pd.isna(valor) or not 0 < float(valor) <= 2:
                salida.at[indice, periodo] = None
                invalidos.append(periodo)
            else:
                salida.at[indice, periodo] = float(valor)
        if invalidos:
            raise ValueError(
                f"Introduce un precio mayor que cero en {atr}TD: "
                + ", ".join(invalidos) + "."
            )
    return salida[["ATR", *PERIODOS]].reset_index(drop=True)


def guardar_version_oferta(
    nombre: str,
    vigencia_desde: date,
    vigencia_hasta: date | None,
    tarifas: pd.DataFrame,
    ruta=RUTA_CATALOGO_OFERTAS,
    potencia_tarifas: pd.DataFrame | None = None,
    producto_entrega: str | None = None,
) -> dict:
    """Añade una versión sin sobrescribir las versiones semanales anteriores."""
    nombre = str(nombre).strip()
    if not nombre:
        raise ValueError("Indica un nombre para la oferta.")
    desde = pd.Timestamp(vigencia_desde).date()
    hasta = (
        pd.Timestamp(vigencia_hasta).date()
        if vigencia_hasta is not None else None
    )
    if hasta is not None and hasta < desde:
        raise ValueError("La fecha fin no puede ser anterior a la fecha inicio.")
    tarifas = normalizar_tarifas_oferta(tarifas)

    potencias_por_atr = {}
    if potencia_tarifas is not None and not potencia_tarifas.empty:
        if "ATR" not in potencia_tarifas.columns:
            raise ValueError("Falta la columna ATR en los precios de potencia.")
        for _, fila_potencia in potencia_tarifas.iterrows():
            atr_potencia = (
                str(fila_potencia["ATR"]).strip().upper()
                .replace(" ", "").removesuffix("TD")
            )
            modalidad = str(
                fila_potencia.get("Modalidad", "CON MARGEN")
            ).strip() or "CON MARGEN"
            potencias_por_atr[atr_potencia] = {
                "modalidad": modalidad,
                "unidad": UNIDAD_POTENCIA_DIARIA,
                **{
                    periodo: (
                        None if pd.isna(pd.to_numeric(
                            fila_potencia.get(periodo), errors="coerce"
                        )) else float(pd.to_numeric(
                            fila_potencia.get(periodo), errors="coerce"
                        ))
                    )
                    for periodo in PERIODOS
                },
            }

    filas = []
    for _, fila in tarifas.iterrows():
        atr = str(fila["ATR"]).strip().upper().replace(" ", "").removesuffix("TD")
        precios = {}
        for periodo in PERIODOS:
            valor = pd.to_numeric(fila[periodo], errors="coerce")
            precios[periodo] = None if pd.isna(valor) else float(valor)
        tarifa = {"atr": atr, **precios}
        if atr in potencias_por_atr:
            tarifa["potencia"] = potencias_por_atr[atr]
        filas.append(tarifa)
    if not filas:
        raise ValueError("No hay tarifas que guardar.")

    registro = {
        "id": uuid4().hex,
        "nombre": nombre,
        "vigencia_desde": desde.isoformat(),
        "vigencia_hasta": hasta.isoformat() if hasta is not None else None,
        "guardado_en": datetime.now().astimezone().isoformat(timespec="seconds"),
        "tarifas": filas,
    }
    if producto_entrega:
        registro["producto_entrega"] = str(producto_entrega).strip().upper()
    ruta = Path(ruta)
    # Solo se escribe el catálogo manual. Los catálogos importados se agregan
    # en lectura y no deben copiarse ni duplicarse aquí.
    catalogo = _leer_catalogo(ruta)
    catalogo.append(registro)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(f".{ruta.name}.{uuid4().hex}.tmp")
    temporal.write_text(
        json.dumps(catalogo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporal, ruta)
    return registro


def incorporar_ofertas_informa(
    ofertas: list[dict],
    vigencia_desde: date,
    ruta=RUTA_CATALOGO_OFERTAS,
) -> dict:
    """Incorpora atómicamente una captura validada de Informa sin duplicarla."""
    desde = pd.Timestamp(vigencia_desde).date().isoformat()
    ruta = Path(ruta)
    catalogo = _leer_catalogo(ruta)
    ids_existentes = {registro.get("id") for registro in catalogo}
    nuevos = []
    omitidos = 0
    ahora = datetime.now().astimezone().isoformat(timespec="seconds")

    for oferta in ofertas:
        huella_datos = {
            "indice_web": oferta["indice_web"],
            "nombre": oferta["nombre"],
            "segmento_contrato": oferta["segmento_contrato"],
            "atr": normalizar_atr(oferta["atr"]),
            "vigencia_hasta": oferta.get("vigencia_hasta"),
            "potencia": oferta["potencia"],
            "energia": oferta["energia"],
            "costes_fijos_eur": oferta.get("costes_fijos_eur"),
            "comision_fija_eur": oferta.get("comision_fija_eur"),
            "comision_energia_eur_mwh": oferta.get(
                "comision_energia_eur_mwh"
            ),
            "comision_potencia_eur": oferta.get("comision_potencia_eur"),
        }
        huella = hashlib.sha256(json.dumps(
            huella_datos, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")).hexdigest()[:20]
        identificador = f"informa-{huella}"
        if identificador in ids_existentes:
            omitidos += 1
            continue

        comision_fija = oferta.get("comision_fija_eur")
        comision_mwh = oferta.get("comision_energia_eur_mwh")
        comision = {
            "tipo": (
                "VARIABLE" if comision_mwh is not None
                else "FIJA" if comision_fija is not None else None
            ),
            "estimada_eur": comision_fija,
            "eur_mwh": comision_mwh,
            "eur_kwh": (
                float(comision_mwh) / 1000
                if comision_mwh is not None else None
            ),
            "potencia_eur": oferta.get("comision_potencia_eur"),
        }
        energia = oferta["energia"]
        potencia = oferta["potencia"]
        registro = {
            "id": identificador,
            "nombre": oferta["nombre"],
            "vigencia_desde": desde,
            "vigencia_hasta": oferta.get("vigencia_hasta"),
            "guardado_en": ahora,
            "fuente": "Captura web Informa Energía",
            "plataforma": "INFORMA",
            "indice_web": oferta["indice_web"],
            "segmento_contrato": oferta["segmento_contrato"],
            "costes_fijos_eur": oferta.get("costes_fijos_eur"),
            "comision": comision,
            "tarifas": [{
                "atr": normalizar_atr(oferta["atr"]),
                **{periodo: energia.get(periodo) for periodo in PERIODOS},
                "potencia": {
                    "modalidad": "CON MARGEN",
                    "unidad": UNIDAD_POTENCIA_DIARIA,
                    **{
                        periodo: potencia.get(periodo)
                        for periodo in PERIODOS
                    },
                },
            }],
        }
        nuevos.append(registro)
        ids_existentes.add(identificador)

    if nuevos:
        catalogo.extend(nuevos)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = ruta.with_name(f".{ruta.name}.{uuid4().hex}.tmp")
        temporal.write_text(
            json.dumps(catalogo, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporal, ruta)
    return {"incorporadas": len(nuevos), "omitidas": omitidos}


def actualizar_vigencia_oferta(
    id_oferta: str,
    vigencia_desde: date,
    vigencia_hasta: date | None,
    ruta=RUTA_CATALOGO_OFERTAS,
) -> dict:
    """Actualiza la vigencia de una versión local mediante escritura atómica."""
    desde = pd.Timestamp(vigencia_desde).date()
    hasta = (
        pd.Timestamp(vigencia_hasta).date()
        if vigencia_hasta is not None else None
    )
    if hasta is not None and hasta < desde:
        raise ValueError("La fecha fin no puede ser anterior a la fecha inicio.")

    ruta = Path(ruta)
    catalogo = _leer_catalogo(ruta)
    coincidencias = [
        registro for registro in catalogo if registro.get("id") == id_oferta
    ]
    if not coincidencias:
        raise ValueError("La oferta no pertenece al catálogo local editable.")
    if len(coincidencias) > 1:
        raise ValueError("El identificador de la oferta está duplicado.")

    registro = coincidencias[0]
    registro["vigencia_desde"] = desde.isoformat()
    registro["vigencia_hasta"] = hasta.isoformat() if hasta else None
    registro["modificado_en"] = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )
    temporal = ruta.with_name(f".{ruta.name}.{uuid4().hex}.tmp")
    temporal.write_text(
        json.dumps(catalogo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporal, ruta)
    return registro


def catalogo_a_dataframe(catalogo: list[dict]) -> pd.DataFrame:
    filas = []
    for registro in catalogo:
        for tarifa in registro.get("tarifas", []):
            filas.append({
                "Nombre": registro.get("nombre"),
                "Desde": registro.get("vigencia_desde"),
                "Hasta": registro.get("vigencia_hasta"),
                "ATR": tarifa.get("atr"),
                **{periodo: tarifa.get(periodo) for periodo in PERIODOS},
                "ID": registro.get("id"),
            })
    return pd.DataFrame(filas)
