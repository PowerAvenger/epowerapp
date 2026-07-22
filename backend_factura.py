"""Lectura local y resumen de facturas eléctricas conocidas.

Este módulo no verifica precios ni consulta servicios externos. Su contrato de
salida es común para todos los formatos, de modo que la interfaz no dependa de
los regex concretos de cada comercializadora.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
import calendar
from pathlib import Path
import re
from typing import Callable

import pandas as pd
import pdfplumber

from formato_es import formato_euros, formato_pct


class FacturaError(ValueError):
    """Error controlado durante la lectura de una factura."""


class FormatoNoReconocido(FacturaError):
    """El PDF tiene texto, pero no coincide con un formato conocido."""


# Márgenes admitidos al comparar un importe leído del PDF con uno calculado.
# El mínimo absoluto absorbe el redondeo normal a céntimos. En excesos se
# admite algo más porque los maxímetros publicados suelen venir redondeados.
TOLERANCIAS_COMPARACION = {
    "total_factura": {"porcentaje": 0.5, "minimo_eur": 0.05},
    "componentes": {"porcentaje": 0.5, "minimo_eur": 0.02},
    "impuestos": {"porcentaje": 0.5, "minimo_eur": 0.02},
    "fbs": {"porcentaje": 0.5, "minimo_eur": 0.02},
    "excesos_maximetros": {"porcentaje": 1.5, "minimo_eur": 0.02},
}


def importes_coinciden(
    importe_pdf: float,
    importe_calculado: float,
    tipo: str = "componentes",
) -> bool:
    """Compara importes con un margen relativo y un suelo absoluto."""
    tolerancia = TOLERANCIAS_COMPARACION[tipo]
    referencia = max(abs(importe_pdf), abs(importe_calculado))
    margen = max(
        tolerancia["minimo_eur"],
        referencia * tolerancia["porcentaje"] / 100,
    )
    return abs(importe_pdf - importe_calculado) <= margen


def semaforo_desviacion_coste(
    importe_facturado: float,
    importe_referencia: float,
    tipo: str = "componentes",
) -> str:
    """Verde si coincide, verde con aviso si el desvío favorece al cliente."""
    if importes_coinciden(importe_facturado, importe_referencia, tipo):
        return "🟢"
    return "🟢 ⚠️" if importe_facturado < importe_referencia else "🔴"


@dataclass
class OtroConcepto:
    concepto: str
    importe: float


@dataclass
class VerificacionFBS:
    dias: int
    precio_facturado_eur_dia: float
    precio_regulado_eur_dia: float | None
    importe_facturado_eur: float
    importe_regulado_eur: float | None
    estado: str
    mensaje: str


@dataclass
class VerificacionFNEE:
    modalidad: str
    consumo_mwh: float | None
    precio_facturado_eur_mwh: float | None
    precio_referencia_eur_mwh: float | None
    importe_facturado_eur: float
    importe_referencia_eur: float | None
    estado: str
    mensaje: str


@dataclass
class VerificacionImpuesto:
    base_eur: float
    tipo_pct: float
    importe_facturado_eur: float
    importe_calculado_eur: float
    estado: str
    mensaje: str
    tipo_regulado_pct: float | None = None
    minimo_eur_mwh: float | None = None
    importe_regulado_eur: float | None = None
    fuente_regulatoria: str | None = None


@dataclass
class EnergiaPeriodo:
    periodo: str
    consumo_kwh: float
    precio_eur_kwh: float
    coste_eur: float
    coste_calculado_eur: float | None = None


@dataclass
class MaximetroPeriodo:
    periodo: str
    potencia_kw: float


@dataclass
class PotenciaContratadaPeriodo:
    periodo: str
    potencia_kw: float


@dataclass
class SobrepasamientoPeriodo:
    periodo: str
    exceso_kw: float


@dataclass
class PotenciaFacturadaPeriodo:
    periodo: str
    potencia_kw: float
    dias: int
    precio_facturado_eur_kw_dia: float
    coste_facturado_eur: float
    precio_boe_eur_kw_dia: float = 0.0
    coste_boe_eur: float = 0.0
    sobrecoste_eur: float = 0.0
    resultado: str = "No verificado"
    coste_calculado_eur: float | None = None
    meses: float | None = None
    precio_facturado_eur_kw_mes: float | None = None


@dataclass
class ExcesoVerificadoPeriodo:
    periodo: str
    potencia_contratada_kw: float
    maximetro_kw: float
    exceso_kw: float
    tepp_eur_kw_dia: float
    dias: int
    coste_calculado_eur: float


@dataclass
class ReactivaPeriodo:
    periodo: str
    energia_activa_kwh: float
    energia_reactiva_kvarh: float
    exceso_facturado_kvarh: float
    exceso_calculado_kvarh: float
    cos_phi: float | None
    precio_eur_kvarh: float
    coste_facturado_eur: float
    coste_calculado_eur: float
    estado: str
    detalle_coste_facturado: bool = True


@dataclass
class FacturaLeida:
    formato: str
    comercializadora: str
    numero_factura: str | None = None
    cups: str | None = None
    atr: str | None = None
    tipo_suministro: str | None = None
    fecha_factura: str | None = None
    fecha_vencimiento_contrato: str | None = None
    periodo_inicio: str | None = None
    periodo_fin: str | None = None
    potencia: float = 0.0
    energia: float = 0.0
    excesos_potencia: float = 0.0
    reactiva: float = 0.0
    iee: float = 0.0
    iva: float = 0.0
    total: float = 0.0
    energia_periodos: list[EnergiaPeriodo] = field(default_factory=list)
    potencias_contratadas: list[PotenciaContratadaPeriodo] = field(default_factory=list)
    potencia_periodos: list[PotenciaFacturadaPeriodo] = field(default_factory=list)
    maximetros: list[MaximetroPeriodo] = field(default_factory=list)
    sobrepasamientos: list[SobrepasamientoPeriodo] = field(default_factory=list)
    excesos_verificados: list[ExcesoVerificadoPeriodo] = field(default_factory=list)
    reactiva_periodos: list[ReactivaPeriodo] = field(default_factory=list)
    verificacion_excesos: str | None = None
    verificacion_fbs: VerificacionFBS | None = None
    verificacion_fnee: VerificacionFNEE | None = None
    verificacion_iee: VerificacionImpuesto | None = None
    verificacion_iva: VerificacionImpuesto | None = None
    otros: list[OtroConcepto] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)

    @property
    def total_otros(self) -> float:
        return round(sum(item.importe for item in self.otros), 2)

    @property
    def consumo_total_kwh(self) -> float:
        return round(sum(item.consumo_kwh for item in self.energia_periodos), 3)

    @property
    def precio_medio_energia(self) -> float:
        if not self.consumo_total_kwh:
            return 0.0
        return self.energia / self.consumo_total_kwh

    @property
    def coste_excesos_calculado(self) -> float:
        return round(
            sum(item.coste_calculado_eur for item in self.excesos_verificados),
            2,
        )

    @property
    def diferencia_excesos(self) -> float:
        return round(self.excesos_potencia - self.coste_excesos_calculado, 2)

    @property
    def sobrecoste_potencia(self) -> float:
        return round(sum(
            item.sobrecoste_eur
            for item in self.potencia_periodos
            if item.resultado == "Superior a BOE"
        ), 2)

    @property
    def porcentaje_sobrecoste_potencia(self) -> float:
        coste_facturado = sum(
            item.coste_facturado_eur for item in self.potencia_periodos
            if item.resultado != "No verificado"
        )
        if not coste_facturado:
            return 0.0
        return max(0.0, self.sobrecoste_potencia / coste_facturado * 100)

    @property
    def sobrecoste_anual_potencia(self) -> float:
        """Proyección anual del margen sobre BOE manteniendo precios y potencias."""
        fecha_referencia = self.periodo_inicio or self.fecha_factura or self.periodo_fin
        try:
            ejercicio = datetime.strptime(fecha_referencia or "", "%d/%m/%Y").year
        except ValueError:
            ejercicio = datetime.now().year
        dias_ejercicio = 366 if calendar.isleap(ejercicio) else 365
        return round(sum(
            max(
                0.0,
                item.precio_facturado_eur_kw_dia
                - item.precio_boe_eur_kw_dia,
            )
            * item.potencia_kw
            * dias_ejercicio
            for item in self.potencia_periodos
            if item.resultado != "No verificado"
        ), 2)

    @property
    def suma_componentes(self) -> float:
        return round(
            self.potencia
            + self.energia
            + self.excesos_potencia
            + self.reactiva
            + self.iee
            + self.iva
            + self.total_otros,
            2,
        )

    @property
    def total_calculado_segun_factura(self) -> float:
        """Concilia el total facturado aplicando solo referencias disponibles.

        La base es siempre la suma de importes facturados. Cada verificación se
        incorpora como un ajuste (referencia menos facturado), evitando que un
        detalle ausente, parcial o un descuento se conviertan accidentalmente
        en cero o se contabilicen dos veces.
        """
        total = self.suma_componentes

        if self.potencia_periodos:
            potencia_calculada = round(sum(
                item.coste_calculado_eur
                if item.coste_calculado_eur is not None
                else round(
                    item.potencia_kw
                    * item.dias
                    * item.precio_facturado_eur_kw_dia,
                    2,
                )
                for item in self.potencia_periodos
            ), 2)
            total += potencia_calculada - self.potencia

        if self.energia_periodos:
            energia_calculada = round(sum(
                item.coste_calculado_eur
                if item.coste_calculado_eur is not None
                else item.coste_eur
                for item in self.energia_periodos
            ), 2)
            total += energia_calculada - self.energia

        if self.excesos_potencia and self.excesos_verificados:
            total += self.coste_excesos_calculado - self.excesos_potencia

        if self.reactiva_periodos:
            reactiva_calculada = round(sum(
                item.coste_calculado_eur for item in self.reactiva_periodos
            ), 2)
            total += reactiva_calculada - self.reactiva

        if self.verificacion_iee:
            iee_referencia = (
                self.verificacion_iee.importe_regulado_eur
                if self.verificacion_iee.importe_regulado_eur is not None
                else self.verificacion_iee.importe_calculado_eur
            )
            total += iee_referencia - self.iee

        if self.verificacion_iva:
            iva_referencia = (
                self.verificacion_iva.importe_regulado_eur
                if self.verificacion_iva.importe_regulado_eur is not None
                else self.verificacion_iva.importe_calculado_eur
            )
            total += iva_referencia - self.iva

        if self.verificacion_fbs:
            fbs_extraido = sum(
                item.importe for item in self.otros
                if "bono social" in item.concepto.lower()
            )
            if self.verificacion_fbs.importe_regulado_eur is not None:
                total += (
                    self.verificacion_fbs.importe_regulado_eur - fbs_extraido
                )
        if (
            self.verificacion_fnee
            and self.verificacion_fnee.importe_referencia_eur is not None
        ):
            total += (
                self.verificacion_fnee.importe_referencia_eur
                - self.verificacion_fnee.importe_facturado_eur
            )
        return round(total, 2)

    @property
    def reconstruccion_total_completa(self) -> bool:
        """Indica si cada componente principal dispone de detalle recalculable."""
        incluye_fbs = any(
            "bono social" in item.concepto.lower() for item in self.otros
        )
        incluye_fnee = any(
            "fnee" in item.concepto.lower() for item in self.otros
        )
        return all((
            # La cohesión contable no usa tolerancia porcentual: antes de
            # verificar referencias, los conceptos extraídos deben reconstruir
            # el total PDF a céntimos (salvo redondeos acumulados mínimos).
            abs(self.total - self.suma_componentes) <= 0.05,
            not self.potencia or (
                bool(self.potencia_periodos)
                and abs(
                    self.potencia
                    - sum(
                        item.coste_facturado_eur
                        for item in self.potencia_periodos
                    )
                ) <= 0.05
                and all(
                    item.resultado != "No verificado"
                    for item in self.potencia_periodos
                )
            ),
            not self.energia or (
                bool(self.energia_periodos)
                and abs(
                    self.energia
                    - sum(item.coste_eur for item in self.energia_periodos)
                ) <= 0.05
            ),
            not self.excesos_potencia or bool(self.excesos_verificados),
            not self.reactiva or bool(self.reactiva_periodos),
            not self.iee or (
                self.verificacion_iee is not None
                and self.verificacion_iee.importe_regulado_eur is not None
            ),
            not self.iva or (
                self.verificacion_iva is not None
                and self.verificacion_iva.importe_regulado_eur is not None
            ),
            not incluye_fbs or (
                self.verificacion_fbs is not None
                and self.verificacion_fbs.importe_regulado_eur is not None
            ),
            not incluye_fnee or (
                self.verificacion_fnee is not None
                and self.verificacion_fnee.importe_referencia_eur is not None
            ),
        ))

    @property
    def diferencia_total_calculado(self) -> float:
        return round(self.total - self.total_calculado_segun_factura, 2)

    @property
    def diferencia(self) -> float:
        return round(self.total - self.suma_componentes, 2)

    def como_dict(self) -> dict:
        datos = asdict(self)
        datos["total_otros"] = self.total_otros
        datos["suma_componentes"] = self.suma_componentes
        datos["diferencia"] = self.diferencia
        datos["total_calculado_segun_factura"] = self.total_calculado_segun_factura
        datos["diferencia_total_calculado"] = self.diferencia_total_calculado
        datos["consumo_total_kwh"] = self.consumo_total_kwh
        datos["precio_medio_energia"] = self.precio_medio_energia
        datos["coste_excesos_calculado"] = self.coste_excesos_calculado
        datos["diferencia_excesos"] = self.diferencia_excesos
        datos["sobrecoste_potencia"] = self.sobrecoste_potencia
        datos["porcentaje_sobrecoste_potencia"] = self.porcentaje_sobrecoste_potencia
        return datos


def extraer_texto_pdf(contenido: bytes) -> tuple[str, int]:
    try:
        with pdfplumber.open(BytesIO(contenido)) as pdf:
            paginas = [
                pagina.extract_text(x_tolerance=2, y_tolerance=3) or ""
                for pagina in pdf.pages
            ]
    except Exception as exc:
        raise FacturaError("No se ha podido abrir el PDF.") from exc

    texto = "\n".join(paginas).strip()
    if not texto:
        raise FacturaError(
            "El PDF no contiene texto extraíble. Puede ser un documento escaneado."
        )
    return texto, len(paginas)


def numero_es(valor: str | None) -> float:
    if valor is None:
        return 0.0
    limpio = valor.strip().replace("€", "").replace(" ", "")
    if not limpio:
        return 0.0
    if "," in limpio:
        limpio = limpio.replace(".", "").replace(",", ".")
    return float(limpio)


def consumo_es(valor: str) -> float:
    limpio = valor.strip().replace(" ", "")
    if "," in limpio:
        return numero_es(limpio)
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", limpio):
        return float(limpio.replace(".", ""))
    return float(limpio)


def buscar_numero(texto: str, patrones: list[str], grupo: int = 1) -> float:
    for patron in patrones:
        match = re.search(patron, texto, re.IGNORECASE | re.MULTILINE)
        if match:
            return numero_es(match.group(grupo))
    return 0.0


def buscar_texto(texto: str, patrones: list[str], grupo: int = 1) -> str | None:
    for patron in patrones:
        match = re.search(patron, texto, re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(grupo).strip()
    return None


def buscar_periodo(texto: str, patrones: list[str]) -> tuple[str | None, str | None]:
    for patron in patrones:
        match = re.search(patron, texto, re.IGNORECASE)
        if match:
            return match.group(1), match.group(2)
    return None, None


def extraer_atr(texto: str) -> str | None:
    atr = buscar_texto(texto, [
        r"Peaje\s+de\s+Transporte\s+y\s+Distribuci\S{0,12}?([236])n?[.:]0:?TD",
        r"Peaje\s+de\s+Transporte\s+y\s+Distribuci[oó]\S*\s*([236])\s*[.:]\s*0\s*:?[Tt][Dd]",
        r"Tarifa\s+de\s+acceso\s*:\s*(\d(?:\.\d)?\s*TD)",
        r"(?:Peaje|Tarifa)\s+de\s+acceso\s*:\s*(\d(?:\.\d)?\s*TD)",
        r"(?:Peaje|ATR)\s*:\s*(\d(?:\.\d)?\s*TD)",
        r"\b(2\.0\s*TD|3\.0\s*TD|6\.[1-4]\s*TD)\b",
    ])
    if not atr:
        return None
    if atr in {"2", "3", "6"}:
        return f"{atr}.0TD"
    return re.sub(r"\s+", " ", atr.upper()).strip()


def sumar_coincidencias(texto: str, patron: str, grupo: int = 1) -> float:
    return round(
        sum(
            numero_es(match.group(grupo))
            for match in re.finditer(
                patron, texto, re.IGNORECASE | re.MULTILINE
            )
        ),
        2,
    )


def extraer_periodos_energia(
    texto: str,
    patrones: list[str],
    primer_bloque_secuencial: bool = False,
) -> list[EnergiaPeriodo]:
    """Extrae tuplas periodo, consumo, precio y coste del primer patrón válido."""
    for patron in patrones:
        coincidencias = re.findall(patron, texto, re.IGNORECASE | re.MULTILINE)
        if coincidencias:
            if primer_bloque_secuencial:
                bloque = []
                ultimo_numero = 0
                for coincidencia in coincidencias:
                    periodo = coincidencia[0].upper()
                    numero_periodo = int(periodo[1:])
                    if bloque and numero_periodo <= ultimo_numero:
                        break
                    bloque.append(coincidencia)
                    ultimo_numero = numero_periodo
                coincidencias = bloque
            return [
                EnergiaPeriodo(
                    periodo=periodo.upper(),
                    consumo_kwh=consumo_es(consumo),
                    precio_eur_kwh=numero_es(precio),
                    coste_eur=numero_es(coste),
                )
                for periodo, consumo, precio, coste in coincidencias
            ]
    return []


def extraer_maximetros_visalia_empresas(texto: str) -> list[MaximetroPeriodo]:
    patrones = [
        r"Potencia\s+M[aá]xima.*?((?:\d+[,.]\d+\s*){1,6})",
        r"Potencia\s+Max(?:[ií]ma|[ií]metros).*?((?:\d+[.,]?\d*\s*){1,6})",
    ]
    valores: list[float] = []
    for patron in patrones:
        match = re.search(patron, texto, re.IGNORECASE)
        if match:
            valores = [
                numero_es(valor)
                for valor in re.findall(r"\d+[.,]?\d*", match.group(1))
            ][:6]
            break
    return [
        MaximetroPeriodo(periodo=f"P{indice}", potencia_kw=valor)
        for indice, valor in enumerate(valores, start=1)
    ]


def extraer_potencias_contratadas(texto: str) -> list[PotenciaContratadaPeriodo]:
    coincidencias = re.findall(
        r"\b(P[1-6])\s*:?\s*([\d.,]+)\s*kW\b",
        texto,
        re.IGNORECASE,
    )
    por_periodo: dict[str, float] = {}
    for periodo, potencia in coincidencias:
        por_periodo.setdefault(periodo.upper(), numero_es(potencia))
    return [
        PotenciaContratadaPeriodo(periodo=periodo, potencia_kw=por_periodo[periodo])
        for periodo in sorted(por_periodo, key=lambda valor: int(valor[1:]))
    ]


def extraer_periodos_potencia(texto: str) -> list[PotenciaFacturadaPeriodo]:
    patrones = [
        # potencia x días x precio (ADI, VM y formatos equivalentes)
        (
            r"^(?:Potencia\s+facturada\s+)?(P[1-6])\s*:?\s*([\d.,]+)\s*kW\s+x\s+(\d+)\s+d.as\s+x\s+"
            r"([\d.,]+)[^\d\n]+([-\d.,]+)\s*[^\d\n]*$",
            "dias_precio",
        ),
        # potencia, precio diario y días (Visalia domésticos / Imagina)
        (
            r"^(?:T[eé]rmino\s+fijo\s+)?(P[1-6])\s*:?\s*([\d.,]+)\s*kW\s+"
            r"(?:x\s*)?([\d.,]+)[^\d\n]*?/kW[^\d\n]*?(?:x\s*)?(\d+)\s+d.as\s+"
            r"([-\d.,]+)\s*[^\d\n]*$",
            "precio_dias",
        ),
        # precio anual prorrateado por fracción (Visalia Empresas)
        (
            r"^(P[1-6]):\s*([\d.,]+)\s*kW\s*x\s*([\d.,]+)\s*€/kW\s*y\s*año\s*x\s*"
            r"\((\d+)/(\d+)\)\s*año\s*=\s*([-\d.,]+)\s*€[^\n]*$",
            "anual",
        ),
        # potencia x precio mensual x fracción de mes (CYE y equivalentes)
        (
            r"^(P[1-6])\s+([\d.,]+)\s*kW\s+x\s+([\d.,]+)\s*€/kWmes\s+x\s+"
            r"([\d.,]+)\s+meses\s+([-\d.,]+)\s*€\s*$",
            "mensual",
        ),
    ]
    for patron, modo in patrones:
        matches = re.findall(patron, texto, re.IGNORECASE | re.MULTILINE)
        if not matches:
            continue
        resultado = []
        for match in matches:
            if modo == "dias_precio":
                periodo, potencia, dias, precio, coste = match
                precio_diario = numero_es(precio)
            elif modo == "precio_dias":
                periodo, potencia, precio, dias, coste = match
                precio_diario = numero_es(precio)
            elif modo == "anual":
                periodo, potencia, precio_anual, dias, divisor, coste = match
                precio_diario = numero_es(precio_anual) / int(divisor)
            else:
                periodo, potencia, precio_mensual, fraccion_mes, coste = match
                dias = round(numero_es(fraccion_mes) * 365 / 12)
                precio_diario = numero_es(precio_mensual) * 12 / 365
            resultado.append(PotenciaFacturadaPeriodo(
                periodo=periodo.upper(),
                potencia_kw=numero_es(potencia),
                dias=int(dias),
                precio_facturado_eur_kw_dia=precio_diario,
                coste_facturado_eur=numero_es(coste),
            ))
        return resultado
    return []


def clasificar_tipo_suministro(
    potencias: list[PotenciaContratadaPeriodo],
) -> str | None:
    if not potencias:
        return None
    potencia_referencia = max(item.potencia_kw for item in potencias)
    if potencia_referencia >= 10_000:
        return "Tipo 1"
    if potencia_referencia >= 450:
        return "Tipo 2"
    if potencia_referencia > 50:
        return "Tipo 3"
    if potencia_referencia > 15:
        return "Tipo 4"
    return "Tipo 5"


def _dias_facturados(factura: FacturaLeida) -> int | None:
    """Obtiene una duración común para todos los componentes del ciclo."""
    dias_potencia = {
        item.dias for item in factura.potencia_periodos if item.dias > 0
    }
    if len(dias_potencia) == 1:
        return dias_potencia.pop()

    if not factura.periodo_inicio or not factura.periodo_fin:
        return None
    try:
        fecha_inicio = datetime.strptime(factura.periodo_inicio, "%d/%m/%Y")
        fecha_fin = datetime.strptime(factura.periodo_fin, "%d/%m/%Y")
    except ValueError:
        return None
    return (fecha_fin - fecha_inicio).days + 1


def verificar_excesos_maximetros(factura: FacturaLeida) -> None:
    if (
        not factura.excesos_potencia
        and not factura.maximetros
        and not factura.sobrepasamientos
    ):
        return
    if factura.tipo_suministro in {"Tipo 1", "Tipo 2", "Tipo 3"}:
        verificar_excesos_sobrepasamientos(factura)
        return
    if factura.tipo_suministro not in {"Tipo 4", "Tipo 5"}:
        return
    if not factura.maximetros:
        factura.verificacion_excesos = "No hay maxímetros extraídos para verificar."
        return
    if not factura.potencias_contratadas:
        factura.verificacion_excesos = (
            "No se han extraído las potencias contratadas necesarias."
        )
        return
    dias = _dias_facturados(factura)
    if dias is None:
        factura.verificacion_excesos = "No se ha podido determinar la duración del ciclo."
        return

    try:
        fecha_fin = datetime.strptime(factura.periodo_fin, "%d/%m/%Y")
        fecha_referencia = (
            datetime.strptime(factura.fecha_factura, "%d/%m/%Y")
            if factura.fecha_factura
            else fecha_fin
        )
    except ValueError:
        factura.verificacion_excesos = "Las fechas extraídas no tienen un formato válido."
        return

    tarifa = (factura.atr or "").upper().replace("TD", "").strip()
    try:
        from backend_opt2 import tepp45

        coeficientes = tepp45[fecha_referencia.year][tarifa]
    except (ImportError, KeyError):
        factura.verificacion_excesos = (
            f"No hay coeficientes TEPp45 para {fecha_referencia.year} y {tarifa or 'ATR desconocido'}."
        )
        return

    potencias = {
        item.periodo: item.potencia_kw for item in factura.potencias_contratadas
    }
    for maximetro in factura.maximetros:
        potencia = potencias.get(maximetro.periodo)
        tepp = coeficientes.get(maximetro.periodo)
        if potencia is None or tepp is None:
            continue
        exceso_kw = max(maximetro.potencia_kw - potencia, 0.0)
        coste = exceso_kw * float(tepp) * dias
        factura.excesos_verificados.append(ExcesoVerificadoPeriodo(
            periodo=maximetro.periodo,
            potencia_contratada_kw=potencia,
            maximetro_kw=maximetro.potencia_kw,
            exceso_kw=exceso_kw,
            tepp_eur_kw_dia=float(tepp),
            dias=dias,
            coste_calculado_eur=round(coste, 2),
        ))

    if not factura.excesos_verificados:
        factura.verificacion_excesos = "No hay periodos comunes para verificar."
    elif importes_coinciden(
        factura.excesos_potencia,
        factura.coste_excesos_calculado,
        "excesos_maximetros",
    ):
        factura.verificacion_excesos = "El coste facturado de excesos es correcto."
    else:
        factura.verificacion_excesos = (
            "El coste facturado de excesos no coincide con el calculado."
        )


def verificar_excesos_sobrepasamientos(factura: FacturaLeida) -> None:
    """Verifica tipos 1-3 usando el sobrepasamiento agregado declarado."""
    if not factura.sobrepasamientos:
        factura.verificacion_excesos = (
            "No verificable sin curva de carga ni detalle de sobrepasamientos "
            "para suministros tipos 1, 2 y 3."
        )
        return

    consumos = {
        item.periodo: item.consumo_kwh for item in factura.energia_periodos
    }
    maximetros_extraidos = {
        item.periodo: item.potencia_kw for item in factura.maximetros
    }
    periodos_incoherentes = [
        periodo
        for periodo, consumo in consumos.items()
        if consumo > 0 and maximetros_extraidos.get(periodo, 0.0) <= 0
    ]
    sobrepasamientos_nulos = all(
        item.exceso_kw <= 0 for item in factura.sobrepasamientos
    )
    if periodos_incoherentes and sobrepasamientos_nulos:
        factura.verificacion_excesos = (
            "No se pueden validar los excesos: hay consumo en "
            f"{', '.join(periodos_incoherentes)} pero sus maxímetros figuran a cero. "
            "El detalle de medidas de la factura parece incompleto."
        )
        return

    fecha_referencia = factura.periodo_inicio or factura.fecha_factura
    try:
        ejercicio = datetime.strptime(fecha_referencia or "", "%d/%m/%Y").year
    except ValueError:
        factura.verificacion_excesos = "No se ha podido determinar el año regulatorio."
        return
    tarifa = (factura.atr or "").upper().replace("TD", "").strip()
    try:
        from backend_opt2 import tepp123

        coeficientes = tepp123[ejercicio][tarifa]
    except (ImportError, KeyError):
        factura.verificacion_excesos = (
            f"No hay coeficientes TEP para {ejercicio} y {tarifa or 'ATR desconocido'}."
        )
        return

    potencias = {
        item.periodo: item.potencia_kw for item in factura.potencias_contratadas
    }
    maximetros = {item.periodo: item.potencia_kw for item in factura.maximetros}
    for item in factura.sobrepasamientos:
        tepp = coeficientes.get(item.periodo)
        if tepp is None:
            continue
        factura.excesos_verificados.append(ExcesoVerificadoPeriodo(
            periodo=item.periodo,
            potencia_contratada_kw=potencias.get(item.periodo, 0.0),
            maximetro_kw=maximetros.get(item.periodo, 0.0),
            exceso_kw=item.exceso_kw,
            tepp_eur_kw_dia=float(tepp),
            dias=0,
            coste_calculado_eur=round(item.exceso_kw * float(tepp), 2),
        ))

    if importes_coinciden(
        factura.excesos_potencia,
        factura.coste_excesos_calculado,
        "excesos_maximetros",
    ):
        factura.verificacion_excesos = (
            "El coste de excesos es correcto según los sobrepasamientos "
            "agregados declarados en la factura. No se reconstruye la curva de carga."
        )
    else:
        factura.verificacion_excesos = (
            "El coste de excesos no coincide con los sobrepasamientos agregados "
            "declarados en la factura."
        )


def _otros_comunes(texto: str) -> list[OtroConcepto]:
    texto_importes = re.sub(r"(\d)\.\s*,(\d{2})", r"\1,\2", texto)
    patrones = [
        ("Alquiler equipo de medida", [
            r"Alquiler(?:\s+(?:de|del))?\s+equipo(?:s)?(?:\s+de\s+medida)?[^\n]*?(?:=\s*)?([\d.,]+)\s*€\s*$",
            r"Alquiler\s+(?:de|del)\s+contador\s*:\s*([\d.,]+)\s*€\s*$",
            r"Alquiler\s*del\s*contador[^\n]*?([\d.,]+)\s*€\s*$",
            r"Coste\s+del\s+alquiler\s+del\s+equipo\s+de\s+medida\s+y\s+control\s+([\d.,]+)\s*€",
            r"Alquiler\s+([\d.,]+)\s*€",
        ]),
        ("Financiación bono social", [
            r"(?:Financiaci[oó]n|Facturaci[oó]n)\s+bono\s+social[^\n]*?([\d.,]+)\s*€\s*$",
            r"Financiaci[oó]n\s+Bono\s*Social[^\n]*?([\d.,]+)\s*€\s*$",
        ]),
        ("Servicios de ajuste (SSAA/REE)", [
            r"(?:Ajuste\s+Sistema\s+El[eé]ctrico\s*\(REE\)|"
            r"Servicios?\s+de\s+Ajuste(?:\s*\(SSAA\))?)[^\n]*?"
            r"([-\d.,]+)\s*€\s*$",
        ]),
        ("Actualización FNEE", [
            r"(?:Actualizaci[oó]n|Diferencia(?:l)?)\s+(?:del\s+)?(?:FNEE|Fondo\s+"
            r"Nacional\s+de\s+Eficiencia\s+Energ[eé]tica)[^\n]*?"
            r"([\d.,]+)\s*€?\s*$",
        ]),
        ("Aportación FNEE", [
            r"Aportaci[oó]n\s+al\s+Fondo\s+Nacional\s+de\s+Eficiencia\s+"
            r"Energ[eé]tica[^\n]*?(?:\n[^\n]*?)?([\d.,]+)\s*€\s*$",
        ]),
        ("Coste mínimo de gestión", [
            r"Coste\s+m[ií]nimo\s+de\s+gesti[oó]n[^\n]*?"
            r"([-\d.,]+)\s*€?\s*$",
        ]),
        ("Mecanismo de ajuste OM RDL 10/2022", [
            r"Mecanismo\s+de\s+ajuste\s+OM\s+RDL[^\n]*?"
            r"([-\d.,]+)\s*€?\s*$",
        ]),
        ("Mecanismo de ajuste OS RDL 10/2022", [
            r"Mecanismo\s+de\s+ajuste\s+OS\s+RDL[^\n]*?"
            r"([-\d.,]+)\s*€?\s*$",
        ]),
    ]
    resultado = []
    for nombre, opciones in patrones:
        importe = buscar_numero(texto_importes, opciones)
        if importe:
            resultado.append(OtroConcepto(nombre, importe))
    resultado.extend(_extraer_derechos(texto))
    return resultado


def _cargar_tabla_fbs() -> pd.DataFrame:
    ruta = Path(__file__).resolve().parent / "utils" / "004 LUZ componentes regulados.xlsx"
    tabla = pd.read_excel(ruta, sheet_name="FBS", engine="openpyxl")
    columnas = {"fecha_ini", "fecha_fin", "importe_fbs"}
    if not columnas.issubset(tabla.columns):
        raise FacturaError("La hoja FBS no contiene las columnas regulatorias esperadas.")
    tabla = tabla[list(columnas)].copy()
    tabla["fecha_ini"] = pd.to_datetime(tabla["fecha_ini"], errors="raise").dt.date
    tabla["fecha_fin"] = pd.to_datetime(tabla["fecha_fin"], errors="raise").dt.date
    tabla["importe_fbs"] = pd.to_numeric(tabla["importe_fbs"], errors="raise")
    return tabla.sort_values("fecha_ini").reset_index(drop=True)


def _verificar_fbs(factura: FacturaLeida, texto: str) -> None:
    tramos_fbs = re.findall(
        r"^Del\s+\d{2}/\d{2}/\d{4}\s+al\s+\d{2}/\d{2}/\d{4}\s+"
        r"(\d+)\s*d[ií]as\s+x\s*[\d.,]+\s*€/d[ií]a\s+([\d.,]+)\s*€\s*$",
        _seccion(texto, r"Financiaci[oó]n\s+de\s+Bono\s+Social", r"Subtotal"),
        re.IGNORECASE | re.MULTILINE,
    )
    if len(tramos_fbs) > 1:
        dias_total = sum(int(dias) for dias, _ in tramos_fbs)
        importe_total = round(sum(numero_es(importe) for _, importe in tramos_fbs), 2)
        precio_medio = importe_total / dias_total
        texto += (
            f"\nFinanciación bono social {dias_total} días x "
            f"{precio_medio:.9f} €/día {importe_total:.2f} €"
        )
    precio_explicito = True
    patron = (
        r"(?:(?:Financiaci[oó]n|Facturaci[oó]n|Importe)"
        r"(?:\s+(?:de|del))?\s+)?bono\s*social"
        r"(?:\s+fijo)?[^\n]*?(\d+)(?:,00)?\s*d[ií]as?\s*[x*]?\s*"
        r"([\d.,]+)\s*(?:€|Eur)/(?:d(?:[ií]a)?)[^\n]*?"
        r"([-\d.,]+)\s*€(?:\s+.*)?$"
    )
    coincidencia = re.search(patron, texto, re.IGNORECASE | re.MULTILINE)
    if not coincidencia:
        # Tabla CONTIGO/Gesternova: días, precio diario e importe, sin unidad
        # monetaria explícita entre las dos últimas columnas.
        coincidencia = re.search(
            r"financiaci[oó]n\s+del\s+bono\s+social[^\n]*?"
            r"(\d+)\s*d[ií]as?\s+([\d.,]+)\s+([\d.,]+)\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        )
    if coincidencia:
        dias = int(coincidencia.group(1))
        precio_facturado = numero_es(coincidencia.group(2))
        importe_facturado = numero_es(coincidencia.group(3))
    else:
        patron_importe_primero = (
            r"(?:Financiaci[oó]n|Facturaci[oó]n)(?:\s+(?:de|del))?\s+"
            r"bono\s*social\s+([\d.,]+)\s*€\s+(\d+)\s*d[ií]as?\s*"
            r"[x*]\s*([\d.,]+)\s*(?:€|Eur)/d[ií]a"
        )
        coincidencia = re.search(
            patron_importe_primero, texto, re.IGNORECASE | re.MULTILINE
        )
        if not coincidencia:
            coincidencia_importe = re.search(
                r"(?:(?:Financiaci[oó]n|Facturaci[oó]n)(?:\s+(?:de|del))?\s+"
                r"bono\s*social|B\.\s*Social|Bono\s+Social)[^\n]*?"
                r"([\d.,]+)\s*(?:€|Eur)\s*$",
                texto,
                re.IGNORECASE | re.MULTILINE,
            )
            dias_facturados = _dias_facturados(factura)
            if not coincidencia_importe or not dias_facturados:
                return
            importe_facturado = numero_es(coincidencia_importe.group(1))
            dias = dias_facturados
            precio_facturado = importe_facturado / dias
            precio_explicito = False
        else:
            importe_facturado = numero_es(coincidencia.group(1))
            dias = int(coincidencia.group(2))
            precio_facturado = numero_es(coincidencia.group(3))
    conceptos_fbs = [
        item for item in factura.otros
        if "bono social" in item.concepto.lower()
    ]
    if len(conceptos_fbs) > 1:
        dias_por_tramo = [
            int(valor) for valor in re.findall(
                r"bono\s+social[^\n]*?(\d+)\s*d[ií]as?",
                texto,
                re.IGNORECASE,
            )
        ]
        if len(dias_por_tramo) >= len(conceptos_fbs):
            dias = sum(dias_por_tramo[:len(conceptos_fbs)])
        importe_facturado = round(sum(item.importe for item in conceptos_fbs), 2)
        precio_facturado = importe_facturado / dias
        precio_explicito = False
    calculo_linea = round(dias * precio_facturado, 2)

    try:
        tabla = _cargar_tabla_fbs()
    except (OSError, ValueError, KeyError, FacturaError) as exc:
        factura.verificacion_fbs = VerificacionFBS(
            dias, precio_facturado, None, importe_facturado, None, "🟡",
            f"FBS extraído, pero no se pudo consultar la referencia local: {exc}",
        )
        return

    fecha_inicio = _parsear_fecha_factura(factura.periodo_inicio)
    fecha_fin = _parsear_fecha_factura(
        factura.periodo_fin or factura.fecha_factura
    )
    if not fecha_fin:
        factura.verificacion_fbs = VerificacionFBS(
            dias, precio_facturado, None, importe_facturado, None, "🟡",
            "FBS extraído, pero falta una fecha con la que seleccionar el coste regulado.",
        )
        return

    referencias = tabla[
        (tabla["fecha_ini"] <= fecha_fin) & (tabla["fecha_fin"] >= fecha_fin)
    ]
    precio_regulado = (
        float(referencias.iloc[0]["importe_fbs"])
        if len(referencias) == 1 else None
    )
    importe_regulado = round(dias * precio_regulado, 2) if precio_regulado else None

    # Si el ciclo cruza un cambio regulatorio, se calcula por solapamientos.
    # Se hace coincidir la ventana con los días explícitos de la factura: hay
    # comercializadoras que incluyen ambos extremos y otras que no computan
    # el inicial.
    if fecha_inicio and fecha_inicio < fecha_fin:
        dias_inclusivos = (fecha_fin - fecha_inicio).days + 1
        primer_dia = (
            fecha_inicio
            if dias_inclusivos == dias
            else fecha_inicio + timedelta(days=1)
        )
        tramos = tabla[
            (tabla["fecha_ini"] <= fecha_fin) & (tabla["fecha_fin"] >= primer_dia)
        ]
        if len(tramos) > 1:
            total = 0.0
            dias_cubiertos = 0
            for _, tramo in tramos.iterrows():
                inicio = max(primer_dia, tramo["fecha_ini"])
                fin = min(fecha_fin, tramo["fecha_fin"])
                if inicio <= fin:
                    dias_tramo = (fin - inicio).days + 1
                    dias_cubiertos += dias_tramo
                    total += dias_tramo * float(tramo["importe_fbs"])
            if dias_cubiertos == dias:
                importe_regulado = round(total, 2)
                precio_regulado = None

    formula_correcta = (
        not precio_explicito
        or importes_coinciden(importe_facturado, calculo_linea, "fbs")
    )
    if importe_regulado is None:
        estado = "🟡"
        mensaje = "FBS extraído, pero no existe una referencia regulatoria aplicable."
    elif formula_correcta:
        estado = semaforo_desviacion_coste(
            importe_facturado, importe_regulado, "fbs"
        )
        mensaje = (
            "El FBS facturado coincide con el coste regulado aplicable."
            if estado == "🟢"
            else "El FBS difiere del coste regulado, pero favorece al cliente."
            if estado == "🟢 ⚠️"
            else "El FBS facturado supera el coste regulado aplicable."
        )
    else:
        estado = "🔴"
        mensaje = "El FBS facturado no coincide con su cálculo o referencia regulatoria."

    if len(conceptos_fbs) > 1 and estado != "🟢":
        estado = "🟡"
        mensaje = (
            "El FBS total facturado no coincide con nuestra referencia y contiene "
            "una línea adicional de regularización: concepto no entendible/no "
            "aplicable con los datos disponibles."
        )

    factura.verificacion_fbs = VerificacionFBS(
        dias=dias,
        precio_facturado_eur_dia=precio_facturado,
        precio_regulado_eur_dia=precio_regulado,
        importe_facturado_eur=importe_facturado,
        importe_regulado_eur=importe_regulado,
        estado=estado,
        mensaje=mensaje,
    )


def _verificar_fnee(factura: FacturaLeida, texto: str) -> None:
    concepto = next(
        (item for item in factura.otros if "fnee" in item.concepto.lower()),
        None,
    )
    if not concepto:
        return
    diferencial = "actualización" in concepto.concepto.lower()
    modalidad = "Diferencial" if diferencial else "Aportación completa"
    etiqueta = (
        r"(?:Actualizaci[oó]n|Regularizaci[oó]n|Diferencia(?:l)?)\s+"
        r"(?:del\s+)?(?:FNEE|Fondo\s+"
        r"Nacional\s+de\s+Eficiencia\s+Energ[eé]tica)"
        if diferencial
        else r"Aportaci[oó]n\s+(?:al\s+Fondo\s+Nacional\s+de\s+Eficiencia\s+Energ[eé]tica|Fondo\s+de\s+Eficiencia)"
    )
    linea = buscar_texto(texto, [etiqueta + r"([^\n]*)"], grupo=1) or ""
    consumo_match = re.search(r"([\d.,]+)\s*(kWh|MWh)\b", linea, re.IGNORECASE)
    precio_match = re.search(
        r"([\d.,]+)\s*€/(kWh|MWh)\b", linea, re.IGNORECASE
    )
    consumo_mwh = None
    if consumo_match:
        consumo_mwh = numero_es(consumo_match.group(1))
        if consumo_match.group(2).lower() == "kwh":
            consumo_mwh /= 1000
    precio_facturado = None
    if precio_match:
        precio_facturado = numero_es(precio_match.group(1))
        if precio_match.group(2).lower() == "kwh":
            precio_facturado *= 1000
    elif consumo_mwh:
        precio_facturado = concepto.importe / consumo_mwh

    if consumo_mwh is None:
        formula_fondo = re.search(
            r"Coste\s+fondo\s+eficiencia\s*=\s*([\s\S]{0,600}?)"
            r"(?:\nCon\s+fecha|\nLa\s+sociedad)",
            texto,
            re.IGNORECASE,
        )
        if formula_fondo:
            bloque_formula = formula_fondo.group(1)
            consumos_kwh = [
                consumo_es(valor)
                for valor in re.findall(
                    r"([\d.,]+)\s*kWh\s*x", bloque_formula, re.IGNORECASE
                )
            ]
            precio_kwh = buscar_texto(bloque_formula, [
                r"([\d.,]+)\s*Eur/kWh",
            ])
            if consumos_kwh:
                consumo_mwh = sum(consumos_kwh) / 1000
            if precio_kwh:
                precio_facturado = numero_es(precio_kwh) * 1000

    fecha = _parsear_fecha_factura(factura.periodo_fin or factura.fecha_factura)
    from regulacion_fnee import referencia_fnee

    precio_referencia = referencia_fnee(fecha, diferencial) if fecha else None
    importe_referencia = (
        round(consumo_mwh * precio_referencia, 2)
        if consumo_mwh is not None and precio_referencia is not None
        else None
    )
    if consumo_mwh is None or precio_referencia is None:
        estado = "🟡"
        mensaje = (
            "FNEE contabilizado, pero faltan consumo o fecha para contrastarlo "
            "con la referencia propia."
        )
    else:
        estado = semaforo_desviacion_coste(
            concepto.importe, importe_referencia, "componentes"
        )
        if estado == "🟢":
            mensaje = "El FNEE facturado coincide con la referencia propia aplicable."
        elif estado == "🟢 ⚠️":
            mensaje = (
                "El FNEE no coincide con la referencia propia, pero la diferencia "
                "es favorable para el cliente."
            )
        else:
            mensaje = (
                "El FNEE facturado supera la referencia propia aplicable."
            )
    factura.verificacion_fnee = VerificacionFNEE(
        modalidad=modalidad,
        consumo_mwh=consumo_mwh,
        precio_facturado_eur_mwh=precio_facturado,
        precio_referencia_eur_mwh=precio_referencia,
        importe_facturado_eur=concepto.importe,
        importe_referencia_eur=importe_referencia,
        estado=estado,
        mensaje=mensaje,
    )


def semaforo_otro_segun_factura(
    texto: str,
    concepto: OtroConcepto,
) -> str:
    """Comprueba la operación publicada para conceptos diarios conocidos."""
    nombre = concepto.concepto.lower()
    if es_servicio_adicional(concepto):
        return "🟡"
    if "excedent" in nombre:
        coincidencia = re.search(
            r"Compensaci\S*n\s+(?:de\s+excedentes|energ\S*a\s+excedentaria)"
            r"[^\n]*?([-\d.,]+)\s*kWh\s*x\s*([\d.,]+)\s*€/kWh"
            r"[^\n]*?([-\d.,]+)\s*€\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        )
        if not coincidencia:
            return "🟡"
        energia_kwh, precio, importe = coincidencia.groups()
        importe_impreso = numero_es(importe)
        importe_calculado = -abs(round(
            numero_es(energia_kwh) * numero_es(precio), 2
        ))
        return "🟢" if (
            importes_coinciden(
                importe_impreso, importe_calculado, "componentes"
            )
            and importes_coinciden(
                concepto.importe, importe_impreso, "componentes"
            )
        ) else "🔴"
    if "alquiler" in nombre:
        # Criterio provisional: se acepta el cargo publicado por la
        # comercializadora hasta disponer de datos contractuales del cliente.
        return "🟢 ⚠️"
    if "bono social" in nombre:
        return "🟡"
    if "fnee" in nombre:
        etiqueta = (
            r"(?:Actualizaci[oó]n|Diferencia(?:l)?)\s+(?:del\s+)?(?:FNEE|Fondo\s+"
            r"Nacional\s+de\s+Eficiencia\s+Energ[eé]tica)"
            if "actualización" in nombre
            else r"Aportaci[oó]n\s+(?:al\s+Fondo\s+Nacional\s+de\s+Eficiencia\s+Energ[eé]tica|Fondo\s+de\s+Eficiencia)"
        )
        coincidencia_fnee = re.search(
            etiqueta
            + r"[^\n]*?([\d.,]+)\s*(kWh|MWh)\b[^\n]*?"
            + r"([\d.,]+)\s*€/(kWh|MWh)[^\n]*?([\d.,]+)\s*€\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        )
        if not coincidencia_fnee:
            return "🟡"
        consumo, unidad_consumo, precio, unidad_precio, importe = (
            coincidencia_fnee.groups()
        )
        consumo_mwh = numero_es(consumo) / (1000 if unidad_consumo.lower() == "kwh" else 1)
        precio_mwh = numero_es(precio) * (1000 if unidad_precio.lower() == "kwh" else 1)
        calculado = round(consumo_mwh * precio_mwh, 2)
        formula_correcta = (
            importes_coinciden(numero_es(importe), calculado, "componentes")
            and importes_coinciden(concepto.importe, numero_es(importe), "componentes")
        )
        if not formula_correcta:
            return "🔴"
        fecha_referencia = buscar_texto(texto, [
            r"Periodo\s+consumo\s*:\s*De[^\n]*?hasta\s+"
            r"(\d{1,2}\s+de\s+[^\s]+\s+de\s+\d{4})",
            r"(?:Periodo\s+de\s+consumo|Periodo\s+de\s+facturaci[oó]n)"
            r"[^\n]*?(\d{2}/\d{2}/\d{4})\s*$",
            r"Fecha\s+de\s+emisi.n\s*:\s*"
            r"(\d{1,2}\s+de\s+[^\s]+\s+de\s+\d{4})",
        ])
        fecha = _parsear_fecha_factura(_fecha_es_a_ddmmyyyy(fecha_referencia))
        if not fecha:
            return "🟡"
        from regulacion_fnee import referencia_fnee

        precio_regulado = referencia_fnee(
            fecha,
            diferencial="actualización" in nombre,
        )
        if precio_regulado is None:
            return "🟡"
        return "🟢" if abs(precio_mwh - precio_regulado) <= 0.001 else "🔴"
    if "alquiler" not in nombre:
        return "🟡"

    coincidencia = re.search(
        r"Alquiler(?:\s+de\s+contador|\s+(?:del\s+)?equipo(?:\s+de\s+medida)?)"
        r"[^\n]*?(\d+)\s*d[ií]as?\s*[x*]\s*([\d.,]+)\s*€/d[ií]a"
        r"[^\n]*?([\d.,]+)\s*€\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if not coincidencia:
        bloque_alquiler = _seccion(
            texto,
            r"Alquiler\s+de\s+contador",
            r"Total\s+electricidad",
        )
        tramos = re.findall(
            r"Del\s+\d{2}/\d{2}/\d{4}\s+al\s+\d{2}/\d{2}/\d{4}\s+"
            r"(\d+)\s+d[ií]as?\s*x\s*([\d.,]+)\s*€/d[ií]a\s+"
            r"([\d.,]+)\s*€",
            bloque_alquiler,
            re.IGNORECASE,
        )
        if not tramos:
            return "🟡"
        formulas_correctas = all(
            importes_coinciden(
                numero_es(importe),
                round(int(dias) * numero_es(precio), 2),
                "componentes",
            )
            for dias, precio, importe in tramos
        )
        total_lineas = round(sum(numero_es(importe) for _, _, importe in tramos), 2)
        return (
            "🟢"
            if formulas_correctas
            and importes_coinciden(concepto.importe, total_lineas, "componentes")
            else "🔴"
        )
    dias, precio, importe = coincidencia.groups()
    importe_linea = numero_es(importe)
    calculado = round(int(dias) * numero_es(precio), 2)
    coincide_formula = importes_coinciden(
        importe_linea, calculado, "componentes"
    )
    coincide_extraido = importes_coinciden(
        concepto.importe, importe_linea, "componentes"
    )
    return "🟢" if coincide_formula and coincide_extraido else "🔴"


def estado_otro_segun_factura(
    factura: FacturaLeida,
    texto: str,
    concepto: OtroConcepto,
) -> str:
    """Devuelve el estado efectivo de un concepto del bloque Otros."""
    nombre = concepto.concepto.lower()
    if "bono social" in nombre and factura.verificacion_fbs:
        return factura.verificacion_fbs.estado
    if "fnee" in nombre and factura.verificacion_fnee:
        return factura.verificacion_fnee.estado
    return semaforo_otro_segun_factura(texto, concepto)


def _peor_semaforo(estados: list[str]) -> str:
    """Agrega estados conservando siempre el resultado más desfavorable."""
    if any(estado == "🔴" for estado in estados):
        return "🔴"
    if any(estado == "🟡" for estado in estados):
        return "🟡"
    if any(estado == "🟢 ⚠️" for estado in estados):
        return "🟢 ⚠️"
    return "🟢" if estados else "🟡"


def _parsear_fecha_factura(valor: str | None):
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%d/%m/%Y").date()
    except ValueError:
        return None


def _crear_verificacion_impuesto(
    base: str,
    tipo: str,
    importe: str,
    importe_extraido: float,
    nombre: str,
) -> VerificacionImpuesto:
    base_eur = numero_es(base)
    tipo_pct = numero_es(tipo)
    importe_facturado = numero_es(importe)
    importe_calculado = round(base_eur * tipo_pct / 100, 2)
    correcto = (
        importes_coinciden(importe_facturado, importe_calculado, "impuestos")
        and (
            not importe_extraido
            or importes_coinciden(importe_extraido, importe_facturado, "impuestos")
        )
    )
    return VerificacionImpuesto(
        base_eur=base_eur,
        tipo_pct=tipo_pct,
        importe_facturado_eur=importe_facturado,
        importe_calculado_eur=importe_calculado,
        estado="🟢" if correcto else "🔴",
        mensaje=(
            f"El {nombre} coincide con la base y el tipo indicados en la factura."
            if correcto
            else f"El {nombre} no coincide con su base, tipo o importe extraído."
        ),
    )


def _crear_verificacion_iva(
    factura: FacturaLeida,
    base: str,
    tipo: str,
    importe: str,
) -> VerificacionImpuesto:
    verificacion = _crear_verificacion_impuesto(
        base, tipo, importe, factura.iva, "IVA"
    )
    from regulacion_iva import obtener_referencia_iva

    fecha = _parsear_fecha_factura(factura.fecha_factura or factura.periodo_fin)
    referencia = obtener_referencia_iva(
        fecha,
        [item.potencia_kw for item in factura.potencias_contratadas],
    ) if fecha else None
    if referencia is None:
        verificacion.estado = "🟡"
        verificacion.mensaje = (
            "La operación del IVA es correcta, pero faltan fecha o potencias "
            "contratadas para validar el tipo aplicable."
        )
        return verificacion

    tipo_correcto = abs(verificacion.tipo_pct - referencia.tipo_pct) <= 0.000001
    importe_regulado = round(verificacion.base_eur * referencia.tipo_pct / 100, 2)
    importe_correcto = importes_coinciden(
        verificacion.importe_facturado_eur, importe_regulado, "impuestos"
    )
    verificacion.tipo_regulado_pct = referencia.tipo_pct
    verificacion.importe_regulado_eur = importe_regulado
    verificacion.fuente_regulatoria = referencia.fuente
    if tipo_correcto and importe_correcto:
        verificacion.estado = "🟢"
        verificacion.mensaje = (
            "El IVA coincide con la operación y con el tipo legal aplicable."
        )
    elif verificacion.estado == "🟢":
        verificacion.estado = semaforo_desviacion_coste(
            verificacion.importe_facturado_eur, importe_regulado, "impuestos"
        )
        verificacion.mensaje = (
            "El IVA no coincide con la referencia legal, pero la diferencia es "
            "favorable para el cliente."
            if verificacion.estado == "🟢 ⚠️"
            else f"El IVA facturado al {verificacion.tipo_pct:g} % supera la "
            f"referencia legal del {referencia.tipo_pct:g} %."
        )
    return verificacion


def _verificar_iva_multiple(
    factura: FacturaLeida,
    texto: str,
) -> VerificacionImpuesto | None:
    """Valida facturas que separan el IVA del suministro y los servicios."""
    lineas = re.findall(
        r"^IVA\s*\(([\d.,]+)\s*%\)\s+de\s+([\d.,]+)\s+"
        r"([\d.,]+)\s*€\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if len(lineas) < 2:
        return None

    from regulacion_iva import obtener_referencia_iva

    fecha = _parsear_fecha_factura(factura.fecha_factura or factura.periodo_fin)
    referencia = obtener_referencia_iva(
        fecha,
        [item.potencia_kw for item in factura.potencias_contratadas],
    ) if fecha else None
    bases = [numero_es(base) for _, base, _ in lineas]
    tipos = [numero_es(tipo) for tipo, _, _ in lineas]
    importes = [numero_es(importe) for _, _, importe in lineas]
    calculados = [
        float((
            Decimal(str(base)) * Decimal(str(tipo)) / Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        for base, tipo in zip(bases, tipos)
    ]
    tipos_admitidos = {21.0}
    if referencia:
        tipos_admitidos.add(referencia.tipo_pct)
    correcto = (
        referencia is not None
        and all(tipo in tipos_admitidos for tipo in tipos)
        and all(
            importes_coinciden(impreso, calculado, "impuestos")
            for impreso, calculado in zip(importes, calculados)
        )
        and importes_coinciden(
            factura.iva, sum(importes), "impuestos"
        )
    )
    total_facturado = round(sum(importes), 2)
    total_calculado = round(sum(calculados), 2)
    return VerificacionImpuesto(
        base_eur=round(sum(bases), 2),
        tipo_pct=0.0,
        importe_facturado_eur=total_facturado,
        importe_calculado_eur=total_calculado,
        estado="🟢" if correcto else "🔴" if referencia else "🟡",
        mensaje=(
            "Las cuotas de IVA por tipos diferenciados coinciden con sus "
            "bases y referencias legales."
            if correcto else
            "No se han podido validar todas las cuotas diferenciadas de IVA."
        ),
        importe_regulado_eur=total_calculado if referencia else None,
        fuente_regulatoria=(
            referencia.fuente + "; Ley 37/1992, artículo 90"
            if referencia else None
        ),
    )


def _verificar_impuestos(factura: FacturaLeida, texto: str) -> None:
    coincidencia_iva_iberdrola_reducido = re.search(
        r"IVA\s+Reducido(?:\s*\([^\n]*?\))?\s+([\d.,]+)\s*%\s+"
        r"s/\s*([\d.,]+)\s*€\s+([\d.,]+)\s*€",
        texto,
        re.IGNORECASE,
    )
    if coincidencia_iva_iberdrola_reducido:
        tipo, base, importe = coincidencia_iva_iberdrola_reducido.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )

    coincidencia_iee_naturgy_gc = re.search(
        r"IMPUESTO\s+EL[ÉE]CTRICO\s+\d{2}\.\d{2}\.\d{4}\s*-\s*"
        r"\d{2}\.\d{2}\.\d{4}\s+([\d.,]+)\s+Eur\s+"
        r"([\d.,]+)\s+([\d.,]+)\s+Eur",
        texto,
        re.IGNORECASE,
    )
    if coincidencia_iee_naturgy_gc:
        base, factor, importe = coincidencia_iee_naturgy_gc.groups()
        tipo = str(numero_es(factor) * 100)
        factura.verificacion_iee = _aplicar_referencia_iee(
            factura,
            _crear_verificacion_impuesto(base, tipo, importe, factura.iee, "IEE"),
        )

    coincidencia_iee_tabla_simple = re.search(
        r"^Impuesto\s+El[eé]ctrico\s+([\d.,]+)\s*€\s+"
        r"([\d.,]+)\s*%\s+([\d.,]+)\s*€\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iee_tabla_simple:
        base, tipo, importe = coincidencia_iee_tabla_simple.groups()
        factura.verificacion_iee = _aplicar_referencia_iee(
            factura,
            _crear_verificacion_impuesto(
                base, tipo, importe, factura.iee, "IEE"
            ),
        )

    coincidencia_iee_dos_lineas = re.search(
        r"^Impuesto\s+Electricidad\s*\n\s*([\d.,]+)\s*%\s+sobre\s+"
        r"([\d.,]+)\s*€\s+x\s*1\s+([\d.,]+)\s*€\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iee_dos_lineas:
        tipo, base, importe = coincidencia_iee_dos_lineas.groups()
        factura.verificacion_iee = _aplicar_referencia_iee(
            factura,
            _crear_verificacion_impuesto(
                base, tipo, importe, factura.iee, "IEE"
            ),
        )

    coincidencia_iee_importe = re.search(
        r"^Importe\s+IEE\s+([\d.,]+)\s*%\s+s/\s*\(\s*"
        r"([\d.,]+)\s*\)\s*=\s*([\d.,]+)\s*€\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iee_importe:
        tipo, base, importe = coincidencia_iee_importe.groups()
        factura.verificacion_iee = _aplicar_referencia_iee(
            factura,
            _crear_verificacion_impuesto(
                base, tipo, importe, factura.iee, "IEE"
            ),
        )

    coincidencia_iva_naturgy_gc = re.search(
        r"Base\s+imponible\s+([\d.,]+)\s+Eur\s*\n\s*"
        r"IVA\s+([\d.,]+)\s*%\s+([\d.,]+)\s+Eur",
        texto,
        re.IGNORECASE,
    )
    if coincidencia_iva_naturgy_gc:
        base, tipo, importe = coincidencia_iva_naturgy_gc.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    coincidencia_iee_nagini = re.search(
        r"Impuesto\s+sobre\s+la\s+electricidad\s+[\d.,]+\s*€\s*\n\s*"
        r"([\d.,]+)\s*%\s+sobre\s+([\d.,]+)\s*€\s+x\s+1\s+"
        r"([\d.,]+)\s*€",
        texto,
        re.IGNORECASE,
    )
    if coincidencia_iee_nagini:
        tipo, base, importe = coincidencia_iee_nagini.groups()
        factura.verificacion_iee = _aplicar_referencia_iee(
            factura,
            _crear_verificacion_impuesto(base, tipo, importe, factura.iee, "IEE"),
        )

    coincidencia_iee_unielectrica = re.search(
        r"\bI\.?\s*E\.?\s+([\d.,]+)\s*%\s+sobre\s+"
        r"[\d.,]+\s*€\s*\(\s*[\d.,]+\s*€\s*x\s*MWh\s*\)\s*"
        r"[\d.,]+\s*€",
        texto,
        re.IGNORECASE,
    )
    if coincidencia_iee_unielectrica:
        factura.verificacion_iee = _verificar_iee_por_minimo_sin_base(
            factura, coincidencia_iee_unielectrica.group(1)
        )

    coincidencia_iee_axpo = re.search(
        r"Impuesto\s+el[eé]ctrico\s+([\d.,]+)\s*€\s+"
        r"([\d.,]+)\s*%\s+([\d.,]+)\s*€",
        texto,
        re.IGNORECASE,
    )
    if coincidencia_iee_axpo:
        base, tipo, importe = coincidencia_iee_axpo.groups()
        verificacion_iee = _crear_verificacion_impuesto(
            base, tipo, importe, factura.iee, "IEE"
        )
        factura.verificacion_iee = _aplicar_referencia_iee(
            factura, verificacion_iee
        )

    coincidencia_iee_ecovergy = re.search(
        r"Impuesto\s+el[eé]ctrico\s+([\d.,]+)\s*%\s*s/\s*\(\s*"
        r"([\d.,]+)\s*€\s*\)\s*([\d.,]+)\s*€",
        texto,
        re.IGNORECASE,
    )
    if coincidencia_iee_ecovergy:
        tipo, base, importe = coincidencia_iee_ecovergy.groups()
        verificacion_iee = _crear_verificacion_impuesto(
            base, tipo, importe, factura.iee, "IEE"
        )
        factura.verificacion_iee = _aplicar_referencia_iee(
            factura, verificacion_iee
        )

    coincidencia_iee_eni = re.search(
        r"Impuestos?\s+el[eé]ctricos?\s*\n\s*([\d.,]+)\s*€\s*x\s*"
        r"([\d.,]+)\s+([\d.,]+)\s*€",
        texto,
        re.IGNORECASE,
    )
    if coincidencia_iee_eni:
        base, factor, importe = coincidencia_iee_eni.groups()
        verificacion_iee = _crear_verificacion_impuesto(
            base, str(numero_es(factor) * 100), importe, factura.iee, "IEE"
        )
        factura.verificacion_iee = _aplicar_referencia_iee(
            factura, verificacion_iee
        )

    coincidencia_iee_vm = re.search(
        r"Impuestos?\s+el[eé]ctricos?\s+([\d.,]+)\s*€\s*x\s*"
        r"([\d.,]+)\s*%\s*([\d.,]+)\s*€?\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iee_vm:
        base, tipo, importe = coincidencia_iee_vm.groups()
        verificacion_iee = _crear_verificacion_impuesto(
            base, tipo, importe, factura.iee, "IEE"
        )
        factura.verificacion_iee = _aplicar_referencia_iee(
            factura, verificacion_iee
        )

    coincidencia_iee_endesa = re.search(
        r"Impuesto\s+electricidad\s*\(\s*([\d.,]+)\s*Eur\s*X\s*"
        r"([\d.,]+)\s*%\s*\)[^\n]*?([\d.,]+)\s*€",
        texto,
        re.IGNORECASE,
    )
    if coincidencia_iee_endesa:
        base, tipo, importe = coincidencia_iee_endesa.groups()
        verificacion_iee = _crear_verificacion_impuesto(
            base, tipo, importe, factura.iee, "IEE"
        )
        factura.verificacion_iee = _aplicar_referencia_iee(factura, verificacion_iee)

    if factura.verificacion_iee is None:
        coincidencia_iee_endesa_simple = re.search(
            r"Impuesto\s+Electricidad\s+([\d.,]+)\s*Eur\s*x\s*"
            r"([\d.,]+)\s*%\s+([\d.,]+)\s*€",
            texto,
            re.IGNORECASE,
        )
        if coincidencia_iee_endesa_simple:
            base, tipo, importe = coincidencia_iee_endesa_simple.groups()
            verificacion_iee = _crear_verificacion_impuesto(
                base, tipo, importe, factura.iee, "IEE"
            )
            factura.verificacion_iee = _aplicar_referencia_iee(
                factura, verificacion_iee
            )

    coincidencia_iee_on510 = re.search(
        r"Impuesto\s+de\s+Electricidad\s*\(\s*([\d.,]+)\s*%\s+s/"
        r"\s*([\d.,]+)\s*€\s*\)\s*:\s*([\d.,]+)\s*€",
        texto,
        re.IGNORECASE,
    )
    if coincidencia_iee_on510:
        tipo, base, importe = coincidencia_iee_on510.groups()
        verificacion_iee = _crear_verificacion_impuesto(
            base, tipo, importe, factura.iee, "IEE"
        )
        factura.verificacion_iee = _aplicar_referencia_iee(factura, verificacion_iee)

    coincidencia_iee_canaluz = re.search(
        r"^([\d.,]+)\s*%\s*\*\s*([\d.,]+)\s*€\s+([\d.,]+)\s*€\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iee_canaluz:
        tipo, base, importe = coincidencia_iee_canaluz.groups()
        verificacion_iee = _crear_verificacion_impuesto(
            base, tipo, importe, factura.iee, "IEE"
        )
        factura.verificacion_iee = _aplicar_referencia_iee(factura, verificacion_iee)

    coincidencia_iee_amperios = re.search(
        r"^Impuesto\s+Electricidad\s+([\d.,]+)\s*%\s+"
        r"([\d.,]+)\s*€\s+([\d.,]+)\s*€\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iee_amperios and factura.verificacion_iee is None:
        tipo, base, importe = coincidencia_iee_amperios.groups()
        verificacion_iee = _crear_verificacion_impuesto(
            base, tipo, importe, factura.iee, "IEE"
        )
        factura.verificacion_iee = _aplicar_referencia_iee(
            factura, verificacion_iee
        )

    patron_iee = (
        r"Impuesto\s+(?:sobre\s+(?:la\s+)?)?El[eé]ctric(?:o|idad)[^\n]*?"
        r"([\d.,]+)\s*%\s*(?:s/|sobre)\s*([\d.,]+)\s*€"
        r"(?:\s*x\s*1)?\s*\)?\s*([\d.,]+)\s*€\s*$"
    )
    coincidencia_iee = re.search(
        patron_iee, texto, re.IGNORECASE | re.MULTILINE
    )
    if coincidencia_iee and factura.verificacion_iee is None:
        tipo, base, importe = coincidencia_iee.groups()
        verificacion_iee = _crear_verificacion_impuesto(
            base, tipo, importe, factura.iee, "IEE"
        )
        factura.verificacion_iee = _aplicar_referencia_iee(
            factura, verificacion_iee
        )
    else:
        patron_iee_base_primero = (
            r"Impuesto\s+(?:sobre\s+(?:la\s+)?)?El[eé]ctric(?:o|idad)[^\n]*?"
            r"([\d.,]+)\s*€\s*[x*]\s*([\d.,]+)\s*%\s*([\d.,]+)\s*€?\s*$"
        )
        coincidencia_iee_base = re.search(
            patron_iee_base_primero, texto, re.IGNORECASE | re.MULTILINE
        )
        if coincidencia_iee_base:
            base, tipo, importe = coincidencia_iee_base.groups()
            verificacion_iee = _crear_verificacion_impuesto(
                base, tipo, importe, factura.iee, "IEE"
            )
            factura.verificacion_iee = _aplicar_referencia_iee(
                factura, verificacion_iee
            )

        patron_iee_importe_primero = (
            r"Impuesto\s+El[eé]ctrico\s+([\d.,]+)\s*€\s+"
            r"([\d.,]+)\s*[x*]\s*([\d.,]+)\s*%"
        )
        coincidencia_iee_importe = re.search(
            patron_iee_importe_primero, texto, re.IGNORECASE | re.MULTILINE
        )
        if coincidencia_iee_importe:
            importe, base, tipo = coincidencia_iee_importe.groups()
            verificacion_iee = _crear_verificacion_impuesto(
                base, tipo, importe, factura.iee, "IEE"
            )
            factura.verificacion_iee = _aplicar_referencia_iee(
                factura, verificacion_iee
            )

        patron_iee_minimo = (
            r"Impuestos?\s+el[eé]ctricos?[^\n]*?([\d.,]+)\s*€/MWh\s*"
            r"(?:x|\*)\s*([\d.,]+)\s*MWh[^\n]*?([\d.,]+)\s*€?\s*$"
        )
        coincidencia_minimo = re.search(
            patron_iee_minimo, texto, re.IGNORECASE | re.MULTILINE
        )
        if coincidencia_minimo:
            tarifa_mwh, consumo_mwh, importe = coincidencia_minimo.groups()
            factura.verificacion_iee = _verificar_iee_minimo(
                factura, tarifa_mwh, consumo_mwh, importe
            )

        if factura.verificacion_iee is None:
            coincidencia_minimo_kwh = re.search(
                r"^M[ií]nimoIE\s+([\d.,]+)\s*kWh\s+x\s+"
                r"([\d.,]+)\s*€/kWh\s+([\d.,]+)\s*€\s*$",
                texto,
                re.IGNORECASE | re.MULTILINE,
            )
            if coincidencia_minimo_kwh:
                consumo_kwh, tarifa_kwh, importe = coincidencia_minimo_kwh.groups()
                factura.verificacion_iee = _verificar_iee_minimo(
                    factura,
                    str(numero_es(tarifa_kwh) * 1000),
                    str(numero_es(consumo_kwh) / 1000),
                    importe,
                )

        if factura.verificacion_iee is None:
            coincidencia_minimo_tabla = re.search(
                r"^([\d.,]+)\s*MWh\s+([\d.,]+)\s*€/MWh\s+"
                r"I\.?E\.?E?\.?\s+([\d.,]+)\s*€\s*$",
                texto,
                re.IGNORECASE | re.MULTILINE,
            )
            if coincidencia_minimo_tabla:
                consumo_mwh, tarifa_mwh, importe = (
                    coincidencia_minimo_tabla.groups()
                )
                factura.verificacion_iee = _verificar_iee_minimo(
                    factura, tarifa_mwh, consumo_mwh, importe
                )

    if factura.verificacion_iee is None and factura.iee:
        tipo_iee_sin_base = buscar_texto(texto, [
            r"Impuesto\s+el[eé]ctrico\s*\(([\d.,]+)\s*%\)",
        ])
        if tipo_iee_sin_base and factura.consumo_total_kwh:
            factura.verificacion_iee = _verificar_iee_por_minimo_sin_base(
                factura, tipo_iee_sin_base
            )

    if (
        factura.verificacion_iee is None
        and factura.iee
        and factura.consumo_total_kwh
    ):
        from regulacion_iee import obtener_referencia_iee

        fecha_iee = _parsear_fecha_factura(
            factura.fecha_factura or factura.periodo_fin
        )
        referencia_iee = (
            obtener_referencia_iee(fecha_iee, factura.atr)
            if fecha_iee else None
        )
        cuota_minima = (
            round(
                factura.consumo_total_kwh / 1000
                * referencia_iee.minimo_eur_mwh,
                2,
            )
            if referencia_iee else None
        )
        if (
            cuota_minima is not None
            and importes_coinciden(
                factura.iee, cuota_minima, "impuestos"
            )
        ):
            factura.verificacion_iee = _verificar_iee_por_minimo_sin_base(
                factura, str(referencia_iee.tipo_pct)
            )

    if factura.verificacion_iee is None:
        # Tabla fiscal con columnas: base, tipo, impuesto e importe.
        coincidencia_iee_tabla = re.search(
            r"^([\d.,]+)\s*€\s+([\d.,]+)\s*%\s+I\.?E\.?E\.?\s+"
            r"([\d.,]+)\s*€\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        )
        if coincidencia_iee_tabla:
            base, tipo, importe = coincidencia_iee_tabla.groups()
            verificacion_iee = _crear_verificacion_impuesto(
                base, tipo, importe, factura.iee, "IEE"
            )
            factura.verificacion_iee = _aplicar_referencia_iee(
                factura, verificacion_iee
            )

    if factura.verificacion_iee is None:
        coincidencia_iee_visalia = re.search(
            r"Impuesto\s+sobre\s+electricidad\s*:\s*\n"
            r"([\d.,]+)\s*%\s+sobre\s+([\d.,]+)\s*=\s*([\d.,]+)\s*€",
            texto,
            re.IGNORECASE | re.MULTILINE,
        )
        if coincidencia_iee_visalia:
            tipo, base, importe = coincidencia_iee_visalia.groups()
            verificacion_iee = _crear_verificacion_impuesto(
                base, tipo, importe, factura.iee, "IEE"
            )
            factura.verificacion_iee = _aplicar_referencia_iee(
                factura, verificacion_iee
            )

    if factura.verificacion_iee is None:
        # Algunas tablas expresan el tipo como factor decimal, sin símbolo %.
        coincidencia_iee_factor = re.search(
            r"^Impuesto\s+El[eé]ctrico\s+([\d.,]+)\s+"
            r"(0[.,]\d+)\s+([\d.,]+)\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        )
        if coincidencia_iee_factor:
            base, factor, importe = coincidencia_iee_factor.groups()
            verificacion_iee = _crear_verificacion_impuesto(
                base,
                str(numero_es(factor) * 100),
                importe,
                factura.iee,
                "IEE",
            )
            factura.verificacion_iee = _aplicar_referencia_iee(
                factura, verificacion_iee
            )

    if factura.verificacion_iee is None:
        coincidencia_iee_factor_primero = re.search(
            r"^Impuesto\s+(?:de\s+)?electricidad\s+(0[.,]\d+)\s+s/\s*"
            r"([\d.,]+)\s*€\s+([\d.,]+)\s*€?\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        )
        if coincidencia_iee_factor_primero:
            factor, base, importe = coincidencia_iee_factor_primero.groups()
            verificacion_iee = _crear_verificacion_impuesto(
                base, str(numero_es(factor) * 100), importe, factura.iee, "IEE"
            )
            factura.verificacion_iee = _aplicar_referencia_iee(
                factura, verificacion_iee
            )

    if factura.verificacion_iee is None:
        # Resumen ACCIONA: base, importe y tipo se publican en líneas distintas.
        base_iee_resumen = re.search(
            r"^Total\s+Base\s+Imponible\s+([\d.,]+)\s*$",
            texto, re.IGNORECASE | re.MULTILINE,
        )
        bases_iee_detalladas = re.search(
            r"^Total\s+Base\s+Imponible\s+Impuesto\s+El[eé]ctrico\s+€\s+"
            r"([^\n]+)$",
            texto, re.IGNORECASE | re.MULTILINE,
        )
        importe_iee_resumen = re.search(
            r"^Impuesto\s+El[eé]ctrico\s+([\d.,]+)\s*$",
            texto, re.IGNORECASE | re.MULTILINE,
        )
        tipo_iee_resumen = re.search(
            r"Tipo\s+impositivo\s+I\.?Electricidad\s+de\s+([\d.,]+)\s*%",
            texto, re.IGNORECASE,
        )
        if base_iee_resumen and importe_iee_resumen and tipo_iee_resumen:
            importes_base_iee = (
                re.findall(r"[\d.]+,\d+", bases_iee_detalladas.group(1))
                if bases_iee_detalladas else []
            )
            base = (
                importes_base_iee[-1]
                if importes_base_iee else base_iee_resumen.group(1)
            )
            importe = importe_iee_resumen.group(1)
            tipo = tipo_iee_resumen.group(1)
            verificacion_iee = _crear_verificacion_impuesto(
                base, tipo, importe, factura.iee, "IEE"
            )
            factura.verificacion_iee = _aplicar_referencia_iee(
                factura, verificacion_iee
            )

    if factura.verificacion_iee is None and factura.iee:
        # Si la factura omite la fórmula, solo se infiere la base cuando los
        # componentes eléctricos y el tipo regulado reconstruyen la cuota al
        # céntimo. En cualquier otro caso permanece no verificable.
        from regulacion_iee import obtener_referencia_iee

        fecha_iee = _parsear_fecha_factura(
            factura.fecha_factura or factura.periodo_fin
        )
        referencia_iee = (
            obtener_referencia_iee(fecha_iee, factura.atr)
            if fecha_iee else None
        )
        base_iee_inferida = round(
            factura.potencia
            + factura.energia
            + factura.excesos_potencia
            + factura.reactiva,
            2,
        )
        cuota_iee_inferida = (
            round(base_iee_inferida * referencia_iee.tipo_pct / 100, 2)
            if referencia_iee else None
        )
        if (
            cuota_iee_inferida is not None
            and importes_coinciden(
                factura.iee, cuota_iee_inferida, "impuestos"
            )
        ):
            verificacion_iee = _crear_verificacion_impuesto(
                str(base_iee_inferida),
                str(referencia_iee.tipo_pct),
                str(factura.iee),
                factura.iee,
                "IEE",
            )
            factura.verificacion_iee = _aplicar_referencia_iee(
                factura, verificacion_iee
            )

    coincidencia_iva_nagini = re.search(
        r"I\.?V\.?A\.?\s+([\d.,]+)\s*%\s+([\d.,]+)\s*€\s+"
        r"([\d.,]+)\s*€",
        texto,
        re.IGNORECASE,
    )
    if coincidencia_iva_nagini:
        tipo, base, importe = coincidencia_iva_nagini.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    coincidencia_iva_general_tabla = re.search(
        r"^IVA\s*\(GENERAL\)\s+([\d.,]+)\s*€\s+"
        r"([\d.,]+)\s*%\s+([\d.,]+)\s*€\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iva_general_tabla:
        base, tipo, importe = coincidencia_iva_general_tabla.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    coincidencia_iva_base_sobre = re.search(
        r"^Base\s+Imponible\s+([\d.,]+)\s*€\s+([\d.,]+)\s*%\s+"
        r"sobre\s+[\d.,]+\s*€\s+([\d.,]+)\s*€\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iva_base_sobre:
        base, tipo, importe = coincidencia_iva_base_sobre.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    coincidencia_iva_importe = re.search(
        r"^Importe\s+IVA\s+([\d.,]+)\s*%\s+s/\s*\(\s*"
        r"([\d.,]+)\s*\)\s*=\s*([\d.,]+)\s*€\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iva_importe:
        tipo, base, importe = coincidencia_iva_importe.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    coincidencia_iva_importe_separado = re.search(
        r"^Importe\s+total\s+([\d.,]+)\s*€\s*\n"
        r"(?:Impuesto(?:\s+de\s+aplicaci[oó]n)?\s*:?)\s*([\d.,]+)\s*€\s*\n"
        r"IVA\s*:\s*\(\s*([\d.,]+)\s*%",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iva_importe_separado:
        base, importe, tipo = coincidencia_iva_importe_separado.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    coincidencia_iva_base_tipo = re.search(
        r"^IVA\s+([\d.,]+)\s*€\s+([\d.,]+)\s*%\s+"
        r"([\d.,]+)\s*€\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iva_base_tipo:
        base, tipo, importe = coincidencia_iva_base_tipo.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    coincidencia_iva_tipo_repetido = re.search(
        r"^IVA\s+([\d.,]+)\s*%\s+[\d.,]+\s*%\s+s/\s*"
        r"([\d.,]+)\s*€\s+([\d.,]+)\s*€?\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iva_tipo_repetido:
        tipo, base, importe = coincidencia_iva_tipo_repetido.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    coincidencia_iva_unielectrica = re.search(
        r"Base\s+Imponible\s+%\s+I\.?V\.?A\.?\s+Impuestos\s+"
        r"TOTAL\s+FACTURA\s*\n\s*"
        r"([\d.,]+)\s*€\s+([\d.,]+)\s*%\s+"
        r"([\d.,]+)\s*€\s+[\d.,]+\s*€",
        texto,
        re.IGNORECASE,
    )
    if coincidencia_iva_unielectrica:
        base, tipo, importe = coincidencia_iva_unielectrica.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    patron_iva = (
        r"\bI\.?V\.?A\.?\s+([\d.,]+)\s*%\s*(?:s/|sobre)\s*"
        r"([\d.,]+)\s*€\s*([\d.,]+)\s*€\s*$"
    )
    coincidencia_iva = re.search(
        patron_iva, texto, re.IGNORECASE | re.MULTILINE
    )
    if coincidencia_iva:
        tipo, base, importe = coincidencia_iva.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    patron_iva_de_base = (
        r"\bI\.?V\.?A\.?\s*\(\s*([\d.,]+)\s*%\s*\)\s+de\s+"
        r"([\d.,]+)\s+([\d.,]+)\s*€\s*$"
    )
    coincidencia_iva = re.search(
        patron_iva_de_base, texto, re.IGNORECASE | re.MULTILINE
    )
    if coincidencia_iva:
        tipo, base, importe = coincidencia_iva.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    patron_iva_base_primero = (
        r"\bI\.?V\.?A\.?\s*\(\s*([\d.,]+)\s*%\s*\)\s*"
        r"([\d.,]+)\s*€\s*[x*]\s*[\d.,]+\s*%\s*([\d.,]+)\s*€?\s*$"
    )
    coincidencia_iva = re.search(
        patron_iva_base_primero, texto, re.IGNORECASE | re.MULTILINE
    )
    if coincidencia_iva:
        tipo, base, importe = coincidencia_iva.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    patron_base_iva = (
        r"Base\s+Imponible\s+([\d.,]+)\s*€\s+([\d.,]+)\s*%\s+"
        r"sobre\s+[\d.,]+\s*€\s+([\d.,]+)\s*€\s*$"
    )
    coincidencia_iva = re.search(
        patron_base_iva, texto, re.IGNORECASE | re.MULTILINE
    )
    if coincidencia_iva:
        base, tipo, importe = coincidencia_iva.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    # Tabla fiscal con columnas: base, tipo, impuesto e importe.
    coincidencia_iva_tabla = re.search(
        r"^([\d.,]+)\s*€\s+([\d.,]+)\s*%\s+I\.?V\.?A\.?\s+"
        r"([\d.,]+)\s*€\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iva_tabla:
        base, tipo, importe = coincidencia_iva_tabla.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    coincidencia_iva_eleia = re.search(
        r"^Base\s+Imponible\s+([\d.,]+)\s*€\s*\n"
        r"Impuesto\s+IVA\s+([\d.,]+)\s*%[^\n]*?\(([\d.,]+)\s*€\)\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iva_eleia:
        base, tipo, importe = coincidencia_iva_eleia.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    coincidencia_iva_base_anterior = re.search(
        r"^Base\s+imponible\s+([\d.,]+)\s*€\s*\n"
        r"IVA\s+([\d.,]+)\s*%\s+([\d.,]+)\s*€\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iva_base_anterior:
        base, tipo, importe = coincidencia_iva_base_anterior.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    coincidencia_iva_visalia = re.search(
        r"^I\.?V\.?A\.?\s+([\d.,]+)\s*%\s*\(Base\s+Imponible\s+"
        r"([\d.,]+)\s*€\)\s*=\s*([\d.,]+)\s*€\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iva_visalia:
        tipo, base, importe = coincidencia_iva_visalia.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    coincidencia_iva_amperios = re.search(
        r"Base\s+imponible\s+([\d.,]+)\s*€[\s\S]{0,120}?"
        r"I\.?\s*V\.?\s*A\.?\s+([\d.,]+)\s*%\s+([\d.,]+)\s*€",
        texto,
        re.IGNORECASE,
    )
    if coincidencia_iva_amperios:
        base, tipo, importe = coincidencia_iva_amperios.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    coincidencia_iva_endesa = re.search(
        r"IVA\s*normal\s+([\d.,]+)\s*%\s+s/\s*(\d+,\d{2})"
        r"\.*?([\d.]+,\d{2})\s*€",
        texto,
        re.IGNORECASE,
    )
    if coincidencia_iva_endesa:
        tipo, base, importe = coincidencia_iva_endesa.groups()
        importe = importe.replace(".", "")
        factura.verificacion_iva = _crear_verificacion_iva(factura, base, tipo, importe)
        return

    coincidencia_iva_endesa_columnas = re.search(
        r"^IVA\s*normal\s+([\d.,]+)\s*%\s+s/\s*([\d.,]+)[^\n]*?"
        r"([\d.,]+)\s*€",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iva_endesa_columnas:
        tipo, base, importe = coincidencia_iva_endesa_columnas.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    coincidencia_iva_endesa_parentesis = re.search(
        r"IVA\s*normal\s*\(\s*([\d.,]+)\s*%\s*\)\s*[\d.,]+\s*%\s*"
        r"s/\s*([\d.,]+)\s+([\d.,]+)\s*€",
        texto,
        re.IGNORECASE,
    )
    if coincidencia_iva_endesa_parentesis:
        tipo, base, importe = coincidencia_iva_endesa_parentesis.groups()
        factura.verificacion_iva = _crear_verificacion_iva(factura, base, tipo, importe)
        return

    coincidencia_iva_vm = re.search(
        r"^Base\s+imponible\s+([\d.,]+)\s*€?\s*\n"
        r"IVA\s+([\d.,]+)\s*%\s+([\d.,]+)\s*€?\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iva_vm:
        base, tipo, importe = coincidencia_iva_vm.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    coincidencia_iva_eni = re.search(
        r"IVA\s+General\s*\([^)]*\)\s*([\d.,]+)\s*%\s*s/\s*"
        r"([\d.,]+)\s*€\s+([\d.,]+)\s*€",
        texto,
        re.IGNORECASE,
    )
    if coincidencia_iva_eni:
        tipo, base, importe = coincidencia_iva_eni.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    coincidencia_iva_axpo = re.search(
        r"^Base\s+imponible\s+([\d.,]+)\s*€\s*\n"
        r"IVA\s+([\d.,]+)\s*%\s+([\d.,]+)\s*€",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iva_axpo:
        base, tipo, importe = coincidencia_iva_axpo.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    coincidencia_iva_on510 = re.search(
        r"IVA\s*:\s*\(\s*([\d.,]+)\s*%\s+s/\s*([\d.,]+)\s*€\s*\)\s*"
        r"([\d.,]+)\s*€",
        texto,
        re.IGNORECASE,
    )
    if coincidencia_iva_on510:
        tipo, base, importe = coincidencia_iva_on510.groups()
        factura.verificacion_iva = _crear_verificacion_iva(factura, base, tipo, importe)
        return

    coincidencia_iva_canaluz = re.search(
        r"^([\d.,]+)\s*%\s+IVA\s*\*\s*([\d.,]+)\s*€\s+([\d.,]+)\s*€\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iva_canaluz:
        tipo, base, importe = coincidencia_iva_canaluz.groups()
        factura.verificacion_iva = _crear_verificacion_iva(factura, base, tipo, importe)
        return

    coincidencia_iva_aeq = re.search(
        r"^Base\s+Imponible\s+([\d.,]+)\s*€\s*\n"
        r"Impuesto\s+IVA\s*\(\s*([\d.,]+)\s*%\s*\)\s+"
        r"([\d.,]+)\s*€\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iva_aeq:
        base, tipo, importe = coincidencia_iva_aeq.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    coincidencia_iva_totalenergies = re.search(
        r"^Impuesto\s+IVA\s+([\d.,]+)\s*%\s+sobre\s+"
        r"([\d.,]+)\s*€\s+([\d.,]+)\s*€\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iva_totalenergies:
        tipo, base, importe = coincidencia_iva_totalenergies.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    coincidencia_iva_resumen = re.search(
        r"Total\s+Base\s+Imponible\s+([\d.,]+)[\s\S]{0,120}?"
        r"IVA\s*\(\s*([\d.,]+)\s*%\s*\)\s+([\d.,]+)",
        texto,
        re.IGNORECASE,
    )
    if coincidencia_iva_resumen:
        base, tipo, importe = coincidencia_iva_resumen.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )
        return

    coincidencia_iva_fila_base = re.search(
        r"^Base\s+Imponible\s+\d+\s+([\d.,]+)\s+([\d.,]+)\s+"
        r"([\d.,]+)\s+[\d.,]+\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if coincidencia_iva_fila_base:
        base, tipo, importe = coincidencia_iva_fila_base.groups()
        factura.verificacion_iva = _crear_verificacion_iva(
            factura, base, tipo, importe
        )


def _aplicar_referencia_iee(
    factura: FacturaLeida,
    verificacion: VerificacionImpuesto,
) -> VerificacionImpuesto:
    from regulacion_iee import obtener_referencia_iee

    fecha = _parsear_fecha_factura(
        factura.fecha_factura or factura.periodo_fin
    )
    if not fecha:
        verificacion.estado = "🟡"
        verificacion.mensaje = (
            "La operación del IEE es correcta, pero falta la fecha para validar el tipo."
        )
        return verificacion

    referencia = obtener_referencia_iee(fecha, factura.atr)
    if not referencia:
        verificacion.estado = "🟡"
        verificacion.mensaje = (
            "La operación del IEE es correcta, pero no hay referencia regulatoria "
            f"cargada para {fecha.strftime('%d/%m/%Y')}."
        )
        return verificacion

    cuota_porcentual = round(
        verificacion.base_eur * referencia.tipo_pct / 100, 2
    )
    cuota_minima = round(
        factura.consumo_total_kwh / 1000 * referencia.minimo_eur_mwh, 2
    ) if factura.consumo_total_kwh else 0.0
    importe_regulado = max(cuota_porcentual, cuota_minima)
    # Las facturas suelen imprimir el tipo legal 5,11269632 % redondeado a
    # cuatro decimales (5,1127 %).
    tipo_correcto = abs(verificacion.tipo_pct - referencia.tipo_pct) <= 0.00005
    importe_correcto = (
        importes_coinciden(
            verificacion.importe_facturado_eur, importe_regulado, "impuestos"
        )
    )

    verificacion.tipo_regulado_pct = referencia.tipo_pct
    verificacion.minimo_eur_mwh = referencia.minimo_eur_mwh
    verificacion.importe_regulado_eur = importe_regulado
    verificacion.fuente_regulatoria = referencia.fuente
    if verificacion.estado == "🟢" and tipo_correcto and importe_correcto:
        verificacion.mensaje = (
            "El IEE coincide con la operación y con el tipo regulado aplicable."
        )
    elif verificacion.estado == "🟢":
        verificacion.estado = semaforo_desviacion_coste(
            verificacion.importe_facturado_eur, importe_regulado, "impuestos"
        )
        verificacion.mensaje = (
            "El IEE no coincide con la referencia regulatoria, pero la diferencia "
            "es favorable para el cliente."
            if verificacion.estado == "🟢 ⚠️"
            else "El IEE facturado supera la referencia regulatoria aplicable."
        )
    return verificacion


def _verificar_iee_minimo(
    factura: FacturaLeida,
    tarifa_mwh: str,
    consumo_mwh: str,
    importe: str,
) -> VerificacionImpuesto:
    from regulacion_iee import obtener_referencia_iee

    tarifa = numero_es(tarifa_mwh)
    consumo = numero_es(consumo_mwh)
    importe_facturado = numero_es(importe)
    importe_calculado = round(tarifa * consumo, 2)
    fecha = _parsear_fecha_factura(
        factura.fecha_factura or factura.periodo_fin
    )
    referencia = obtener_referencia_iee(fecha, factura.atr) if fecha else None
    correcto = (
        importes_coinciden(importe_facturado, importe_calculado, "impuestos")
        and importes_coinciden(factura.iee, importe_facturado, "impuestos")
        and referencia is not None
        and abs(tarifa - referencia.minimo_eur_mwh) <= 0.000001
    )
    return VerificacionImpuesto(
        base_eur=0.0,
        tipo_pct=0.0,
        importe_facturado_eur=importe_facturado,
        importe_calculado_eur=importe_calculado,
        estado="🟢" if correcto else "🔴" if referencia else "🟡",
        mensaje=(
            "El IEE coincide con la cuota mínima regulatoria aplicable."
            if correcto
            else "No se ha podido validar la cuota mínima regulatoria del IEE."
        ),
        tipo_regulado_pct=referencia.tipo_pct if referencia else None,
        minimo_eur_mwh=referencia.minimo_eur_mwh if referencia else None,
        importe_regulado_eur=(
            round(consumo * referencia.minimo_eur_mwh, 2)
            if referencia else None
        ),
        fuente_regulatoria=referencia.fuente if referencia else None,
    )


def _verificar_iee_por_minimo_sin_base(
    factura: FacturaLeida,
    tipo_impreso: str,
) -> VerificacionImpuesto:
    """Valida una cuota minima cuando el PDF muestra el tipo, pero no su base."""
    from regulacion_iee import obtener_referencia_iee

    fecha = _parsear_fecha_factura(factura.fecha_factura or factura.periodo_fin)
    referencia = obtener_referencia_iee(fecha, factura.atr) if fecha else None
    tipo_pct = numero_es(tipo_impreso)
    base_estimada = round(
        factura.potencia
        + factura.energia
        + factura.excesos_potencia
        + factura.reactiva
        + factura.total_otros,
        2,
    )
    cuota_porcentual = round(base_estimada * tipo_pct / 100, 2)
    cuota_minima = (
        round(factura.consumo_total_kwh / 1000 * referencia.minimo_eur_mwh, 2)
        if referencia else 0.0
    )
    importe_regulado = max(cuota_porcentual, cuota_minima) if referencia else None
    correcto = (
        referencia is not None
        and abs(tipo_pct - referencia.tipo_pct) <= 0.00005
        and importes_coinciden(factura.iee, importe_regulado, "impuestos")
    )
    return VerificacionImpuesto(
        base_eur=base_estimada,
        tipo_pct=tipo_pct,
        importe_facturado_eur=factura.iee,
        importe_calculado_eur=importe_regulado or cuota_porcentual,
        estado="🟢" if correcto else "🔴" if referencia else "🟡",
        mensaje=(
            "El IEE coincide con la cuota mínima regulatoria aplicable."
            if correcto
            else "No se ha podido validar el IEE con la referencia regulatoria aplicable."
        ),
        tipo_regulado_pct=referencia.tipo_pct if referencia else None,
        minimo_eur_mwh=referencia.minimo_eur_mwh if referencia else None,
        importe_regulado_eur=importe_regulado,
        fuente_regulatoria=referencia.fuente if referencia else None,
    )


def _extraer_derechos(texto: str) -> list[OtroConcepto]:
    """Extrae derechos regulados facturados, que llevan IVA pero no IEE."""
    nombres = {
        "enganche": "Derechos de enganche",
        "acceso": "Derechos de acceso",
        "extensión": "Derechos de extensión",
        "extension": "Derechos de extensión",
        "actuación": "Actuación en equipo de medida",
        "actuacion": "Actuación en equipo de medida",
        "verificación": "Derechos de verificación",
        "verificacion": "Derechos de verificación",
    }
    resultado: list[OtroConcepto] = []
    lineas_vistas: set[str] = set()

    patron_derecho = re.compile(
        r"derechos?\s+(?:de\s+|por\s+)?"
        r"(enganche|acceso|extensi[oó]n|actuaci[oó]n|verificaci[oó]n)\b",
        re.IGNORECASE,
    )
    patron_equipo = re.compile(
        r"actuaci[oó]n(?:es)?\s+(?:en|sobre)\s+(?:los?\s+)?equipos?\s+de\s+medida",
        re.IGNORECASE,
    )

    for linea in texto.splitlines():
        match = patron_derecho.search(linea)
        es_actuacion_equipo = patron_equipo.search(linea)
        if not match and not es_actuacion_equipo:
            continue

        importes = re.findall(r"([-\d.,]+)\s*€", linea)
        if not importes:
            continue
        clave_linea = re.sub(r"\s+", " ", linea.strip().lower())
        if clave_linea in lineas_vistas:
            continue
        lineas_vistas.add(clave_linea)

        if match:
            clave = match.group(1).lower()
            concepto = nombres.get(clave, f"Derechos de {clave}")
        else:
            concepto = "Actuación en equipo de medida"
        resultado.append(OtroConcepto(concepto, numero_es(importes[-1])))

    return resultado


def _extraer_abonos(texto: str) -> list[OtroConcepto]:
    resultado = []
    for linea in texto.splitlines():
        if not re.search(
            r"\b(?:ABONO|COMPENSACI[OÓ]N\s+ENERG[IÍ]A\s+EXCEDENTARIA)\b",
            linea,
            re.IGNORECASE,
        ):
            continue
        importes = re.findall(r"(-[\d.,]+)\s*€", linea)
        if importes:
            concepto = re.sub(r"\s+-?[\d.,]+\s*€\s*$", "", linea).strip()
            resultado.append(OtroConcepto(concepto.title(), numero_es(importes[-1])))
    return resultado


def _extraer_compensaciones_excedentes(texto: str) -> list[OtroConcepto]:
    """Extrae como abono las compensaciones por energía vertida a la red."""
    resultado = []
    for linea in texto.splitlines():
        if not re.search(
            r"Compensaci\S*n\s+(?:de\s+excedentes|energ\S*a\s+excedentaria)",
            linea,
            re.IGNORECASE,
        ):
            continue
        importes = re.findall(r"(-[\d.,]+)\s*€", linea)
        if importes:
            resultado.append(OtroConcepto(
                "Compensación de excedentes",
                numero_es(importes[-1]),
            ))
    return resultado


def es_servicio_adicional(concepto: str | OtroConcepto) -> bool:
    """Identifica servicios comerciales ajenos al suministro eléctrico."""
    nombre = (
        concepto.concepto if isinstance(concepto, OtroConcepto) else concepto
    ).lower()
    return bool(re.search(
        r"protecci.n|mantenimiento|asistencia|asistente|24\s*h|"
        r"reparaci.n|urgencias?|"
        r"servicio\s+(?:hogar|el.ctrico|t.cnico)|seguro\s+hogar",
        nombre,
        re.IGNORECASE,
    ))


def _extraer_servicios_adicionales(texto: str) -> list[OtroConcepto]:
    """Extrae servicios con importe propio, excluyendo textos informativos."""
    resultado = []
    for linea in texto.splitlines():
        linea_limpia = re.sub(r"\s+", " ", linea).strip()
        if not es_servicio_adicional(linea_limpia):
            continue
        if re.search(
            r"^(?:TOTAL\s+)?SERVICIOS\s+Y\s+OTROS\s+CONCEPTOS\b",
            linea_limpia,
            re.IGNORECASE,
        ):
            continue
        importe = re.search(r"([-\d.,]+)\s*€\s*$", linea_limpia)
        if not importe:
            continue
        concepto = re.sub(
            r"\s+[-\d.,]+\s*€\s*$", "", linea_limpia
        ).strip()
        concepto = re.split(
            r"\s+(?=[-\d.,]+\s+(?:mes(?:es)?|d[ií]as?|años?|"
            r"kWh|MWh|kW|\u20ac/))",
            concepto,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        resultado.append(OtroConcepto(
            concepto.strip().title(),
            numero_es(importe.group(1)),
        ))
    return resultado


def _fecha_es_a_ddmmyyyy(valor: str | None) -> str | None:
    if not valor:
        return None
    fecha_numerica = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})", valor)
    if fecha_numerica:
        dia, mes, anio = fecha_numerica.groups()
        if len(anio) == 2:
            anio = f"20{anio}"
        return f"{int(dia):02d}/{int(mes):02d}/{anio}"
    meses = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
        "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
        "septiembre": 9, "setiembre": 9, "octubre": 10,
        "noviembre": 11, "diciembre": 12,
    }
    match = re.match(r"(\d{1,2})\s+de\s+([a-záéíóúüñ]+)\s+de\s+(\d{4})", valor, re.IGNORECASE)
    if not match or match.group(2).lower() not in meses:
        return valor
    fecha = datetime(int(match.group(3)), meses[match.group(2).lower()], int(match.group(1)))
    return fecha.strftime("%d/%m/%Y")


def _normalizar_fecha_ocr_visalia(linea: str | None) -> str | None:
    """Reconstruye las fechas cuyos dígitos aparecen duplicados en Visalia."""
    if not linea:
        return None
    # Variante observada: 2255//0033//22002255 -> 25/03/2025.
    duplicada = re.search(r"(\d{4})//(\d{4})//(\d{8})", linea)
    if duplicada:
        dia = duplicada.group(1)[::2]
        mes = duplicada.group(2)[::2]
        anio = duplicada.group(3)[::2]
        candidata = f"{dia}/{mes}/{anio}"
        try:
            datetime.strptime(candidata, "%d/%m/%Y")
            return candidata
        except ValueError:
            pass

    # Variante ya contemplada en SVA:
    # 1149//0055/2/2002266 -> 19/05/2026.
    rota_sva = re.search(r"(\d{4})//(\d{4})/(\d)/(\d{7})", linea)
    if rota_sva:
        dia = rota_sva.group(1)[1] + rota_sva.group(1)[3]
        mes = rota_sva.group(2)[1] + rota_sva.group(2)[3]
        anio_completo = rota_sva.group(3) + rota_sva.group(4)
        anio = anio_completo[0] + anio_completo[2] + anio_completo[4] + anio_completo[6]
        candidata = f"{dia}/{mes}/{anio}"
        try:
            datetime.strptime(candidata, "%d/%m/%Y")
            return candidata
        except ValueError:
            return None
    return None


def _extraer_fecha_factura_visalia(texto: str) -> str | None:
    """Lee la fecha limpia o reconstruye las variantes OCR de Visalia."""
    fecha_limpia = buscar_texto(texto, [
        r"Fecha\s+Factura:\s*(\d{2}/\d{2}/\d{4})",
    ])
    if fecha_limpia:
        return fecha_limpia

    linea = buscar_texto(texto, [r"Fecha\s+Factura:\s*([^\n\r]{0,40})"])
    return _normalizar_fecha_ocr_visalia(linea)


def _extraer_fecha_vencimiento_contrato(texto: str) -> str | None:
    """Extrae la fecha de vencimiento del contrato, no el plazo de pago."""
    fecha = buscar_texto(texto, [
        r"Vto\.?\s+del\s+contrato\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"Fecha\s+(?:de\s+)?vencimiento\s+del\s+contrato\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"Vencimiento\s+(?:del\s+)?contrato\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"Fin\s+(?:de\s+)?contrato\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"Fecha\s+final\s+(?:(?:del|de)\s+)?contrato\s*[:.]?\s*"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"Fecha\s+de\s+finalizaci[oó]n\s+del\s+contrato\s*[:.]?\s*"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"Fecha\s+fin\s+(?:de\s+)?contrato\s*[:.]?\s*"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"Fecha\s+fin\s+(?:de\s+)?contrato[^\n]*\n(?:[^\n]*\n)?"
        r"\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    ])
    if not fecha:
        vencimiento_visalia = buscar_texto(texto, [
            r"Fecha\s+Vencimiento\s*:\s*([^\n\r]{0,40})",
        ])
        fecha_visalia = _normalizar_fecha_ocr_visalia(vencimiento_visalia)
        if fecha_visalia:
            return fecha_visalia

        fecha_textual = re.search(
            r"(?:Fecha\s+final\s+(?:(?:del|de)\s+)?contrato|"
            r"Fecha\s+de\s+finalizaci[oó]n\s+del\s+contrato|"
            r"Fin\s+(?:del|de)\s+contrato)\s*[:.]?\s*"
            r"(\d{1,2})\s+de\s+"
            r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
            r"septiembre|setiembre|octubre|noviembre|diciembre)\s+de\s+"
            r"(\d{4})",
            texto,
            re.IGNORECASE,
        )
        if not fecha_textual:
            return None
        dia, mes_texto, anio = fecha_textual.groups()
        meses = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
            "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
            "septiembre": 9, "setiembre": 9, "octubre": 10,
            "noviembre": 11, "diciembre": 12,
        }
        candidata = f"{int(dia):02d}/{meses[mes_texto.lower()]:02d}/{anio}"
        try:
            datetime.strptime(candidata, "%d/%m/%Y")
            return candidata
        except ValueError:
            return None
    fecha = fecha.replace("-", "/")
    partes = fecha.split("/")
    if len(partes) == 3 and len(partes[2]) == 2:
        partes[2] = f"20{partes[2]}"
    return "/".join(parte.zfill(2) for parte in partes)


def _maximetros_desde_excesos(
    texto: str,
    potencias: list[PotenciaContratadaPeriodo],
) -> list[MaximetroPeriodo]:
    contratadas = {item.periodo: item.potencia_kw for item in potencias}
    resultado = []
    patron = (
        r"^(P[1-6])\s+([\d.,]+)\s+x\s+\d+\s+d[ií]as\s+x\s+"
        r"[\d.,]+\s*€\s+[-\d.,]+\s*€\s*$"
    )
    for periodo, exceso in re.findall(patron, texto, re.IGNORECASE | re.MULTILINE):
        periodo = periodo.upper()
        if periodo in contratadas:
            resultado.append(MaximetroPeriodo(
                periodo=periodo,
                potencia_kw=round(contratadas[periodo] + numero_es(exceso), 3),
            ))
    return resultado


def _completar_advertencias(factura: FacturaLeida) -> FacturaLeida:
    if not factura.tipo_suministro:
        factura.tipo_suministro = clasificar_tipo_suministro(
            factura.potencias_contratadas
        )
    verificar_precios_potencia(factura)
    verificar_excesos_maximetros(factura)
    if not importes_coinciden(
        factura.total, factura.suma_componentes, "total_factura"
    ):
        factura.advertencias.append(
            "La suma de los conceptos extraídos no coincide con el total "
            f"(diferencia: {formato_euros(factura.diferencia)})."
        )
    return factura


def verificar_precios_potencia(factura: FacturaLeida) -> None:
    """Compara el precio diario facturado con peajes y cargos regulados."""
    if not factura.potencia_periodos or not factura.atr:
        return

    # En ciclos que cruzan de año, los precios aplicables se identifican mejor
    # con la fecha de factura o el cierre del periodo que con su fecha inicial.
    fecha_referencia = factura.fecha_factura or factura.periodo_fin or factura.periodo_inicio
    try:
        ejercicio = datetime.strptime(fecha_referencia or "", "%d/%m/%Y").year
    except ValueError:
        return

    tarifa = factura.atr.upper().replace("TD", "").strip()
    try:
        from backend_opt2 import pyc_tp

        referencias = pyc_tp[ejercicio][tarifa]
    except (ImportError, KeyError):
        return

    for item in factura.potencia_periodos:
        precio_anual = referencias.get(item.periodo)
        if precio_anual is None:
            continue
        dias_ejercicio = 366 if calendar.isleap(ejercicio) else 365
        item.precio_boe_eur_kw_dia = precio_anual / dias_ejercicio
        item.coste_boe_eur = round(
            item.potencia_kw * item.dias * item.precio_boe_eur_kw_dia, 2
        )
        item.sobrecoste_eur = round(
            item.coste_facturado_eur - item.coste_boe_eur, 2
        )
        estado = semaforo_desviacion_coste(
            item.coste_facturado_eur, item.coste_boe_eur, "componentes"
        )
        item.resultado = (
            "BOE" if estado == "🟢"
            else "Inferior a BOE" if estado == "🟢 ⚠️"
            else "Superior a BOE"
        )


def _visalia_domesticos(texto: str) -> FacturaLeida:
    inicio, fin = buscar_periodo(texto, [
        r"Periodo\s+consumo\s*:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})",
        r"Del\s+(\d{1,2}\s+de\s+[^\s]+\s+de\s+\d{4})\s+al\s+"
        r"(\d{1,2}\s+de\s+[^\s]+\s+de\s+\d{4})",
        r"Periodo\s+de\s+facturaci[oó]n:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})"
    ])
    potencia = buscar_numero(texto, [r"Por\s+t[eé]rmino\s+fijo:\s*([\d.,]+)\s*€"])
    if not potencia:
        potencia = sumar_coincidencias(
            texto,
            r"T[eé]rmino\s+fijo\s+P\d[^\n]*?([\d.,]+)\s*€\s*$",
        )
    energia = buscar_numero(texto, [r"Por\s+energ[ií]a\s+utilizada:\s*([\d.,]+)\s*€"])
    if not energia:
        energia = sumar_coincidencias(
            texto,
            r"T[eé]rmino\s+de\s+energ[iía]+\s+P\d[^\n]*?([\d.,]+)\s*€\s*$",
        )
    energia_periodos = extraer_periodos_energia(texto, [
        r"T[eé]rmino\s+de\s+energ[iía]+\s+(P\d)\s+([\d.,]+)\s*kWh\s+([\d.,]+)\s*€/kWh\s+([\d.,]+)\s*€"
    ])
    return _completar_advertencias(FacturaLeida(
        formato="visalia_domesticos",
        comercializadora="Visalia",
        numero_factura=buscar_texto(texto, [r"N[uú]mero\s+de\s+factura:\s*(DM\d+)"]),
        cups=buscar_texto(texto, [r"CUPS:\s*(ES[A-Z0-9]+)"]),
        atr=extraer_atr(texto),
        fecha_factura=buscar_texto(texto, [r"Fecha\s+de\s+factura:\s*(\d{2}/\d{2}/\d{4})"]),
        periodo_inicio=inicio,
        periodo_fin=fin,
        potencia=potencia,
        energia=energia,
        iee=buscar_numero(texto, [r"Impuesto\s+el[eé]ctrico\s+[\d.,]+\s*€\s+[\d.,]+\s*%\s+([\d.,]+)\s*€"]),
        iva=buscar_numero(texto, [r"IVA\s+\d+\s*%\s+[\d.,]+\s*€\s+\d+\s*%\s+([\d.,]+)\s*€"]),
        total=buscar_numero(texto, [r"^Total:\s*([\d.,]+)\s*€"]),
        energia_periodos=energia_periodos,
        potencias_contratadas=extraer_potencias_contratadas(texto),
        potencia_periodos=extraer_periodos_potencia(texto),
        otros=_otros_comunes(texto),
    ))


def extraer_reactiva_visalia_empresas(texto: str) -> list[ReactivaPeriodo]:
    """Cruza el detalle facturado con las lecturas P1-P6 de Visalia Empresas."""
    from regulacion_reactiva import (
        exceso_reactiva_inductiva,
        factor_potencia,
        precio_reactiva_inductiva,
    )

    activas = _fila_numerica(
        texto, r"Energ[iía]+\s+Activa\s+Consumo\s*\(kWh\)"
    )
    reactivas = _fila_numerica(
        texto, r"Energ[iía]+\s+Reactiva\s+Consumo\s*\(kVArh\)"
    )
    if len(activas) < 6 or len(reactivas) < 6:
        return []

    detalle = {
        int(periodo): (
            numero_es(exceso), numero_es(precio), numero_es(coste)
        )
        for periodo, exceso, precio, coste in re.findall(
            r"^P([1-6]):\s*([\d.,]+)\s*kVarh\s*x\s*([\d.,]+)\s*"
            r"€/kVarh\s*=\s*([\d.,]+)\s*€\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        )
    }
    if not detalle:
        return []

    resultado = []
    for periodo_num in sorted(detalle):
        indice = periodo_num - 1
        periodo = f"P{periodo_num}"
        exceso_facturado, _precio_facturado, coste_facturado = detalle[periodo_num]
        activa = activas[indice]
        reactiva = reactivas[indice]
        cos_phi = factor_potencia(activa, reactiva)
        exceso_calculado = exceso_reactiva_inductiva(activa, reactiva, periodo)
        precio_regulado = precio_reactiva_inductiva(cos_phi, periodo)
        coste_calculado = round(exceso_calculado * precio_regulado, 2)
        resultado.append(ReactivaPeriodo(
            periodo=periodo,
            energia_activa_kwh=activa,
            energia_reactiva_kvarh=reactiva,
            exceso_facturado_kvarh=exceso_facturado,
            exceso_calculado_kvarh=round(exceso_calculado, 3),
            cos_phi=round(cos_phi, 4) if cos_phi is not None else None,
            precio_eur_kvarh=precio_regulado,
            coste_facturado_eur=coste_facturado,
            coste_calculado_eur=coste_calculado,
            estado=semaforo_desviacion_coste(
                coste_facturado, coste_calculado, "componentes"
            ),
        ))
    return resultado


def _visalia_empresas(texto: str) -> FacturaLeida:
    inicio, fin = buscar_periodo(texto, [
        r"FACTURACI[ÓO]N\s+Periodo:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})"
    ])
    potencia = sumar_coincidencias(
        texto,
        r"P\d:\s*[\d.,]+\s*kW\s*x\s*[\d.,]+\s*€/kW\s*y\s*año[^\n]*?=\s*([\d.,]+)\s*€",
    )
    if not potencia:
        potencia = buscar_numero(texto, [r"T[eé]rmino\s+Fijo:.*?\n\s*([\d.,]+)\s*€"])
    energia_periodos = extraer_periodos_energia(texto, [
        r"(P\d):\s*([\d.,]+)\s*kWh\s*x\s*([\d.,]+)\s*€/kWh\s*=\s*([\d.,]+)\s*€"
    ], primer_bloque_secuencial=True)
    energia = round(sum(item.coste_eur for item in energia_periodos), 2)
    if not energia:
        energia = buscar_numero(texto, [r"Energ[ií]a\s+Activa.*?\n\s*([\d.,]+)\s*€"])
    reactiva_periodos = extraer_reactiva_visalia_empresas(texto)
    reactiva = round(sum(
        item.coste_facturado_eur for item in reactiva_periodos
    ), 2)
    if not reactiva:
        reactiva = sumar_coincidencias(
            texto,
            r"P\d:\s*[\d.,]+\s*kVarh[^\n]*?=\s*([\d.,]+)\s*€",
        )
    sobrepasamientos = _sobrepasamientos_visalia_empresas(texto)
    return _completar_advertencias(FacturaLeida(
        formato="visalia_empresas",
        comercializadora="Visalia Empresas",
        numero_factura=buscar_texto(texto, [r"(VIS-SCV-\d{4}/\d{6})"]),
        cups=buscar_texto(texto, [r"([A-Z]{2}\d{16}[A-Z]{2})"]),
        atr=extraer_atr(texto),
        fecha_factura=_extraer_fecha_factura_visalia(texto),
        periodo_inicio=inicio,
        periodo_fin=fin,
        potencia=potencia,
        energia=energia,
        excesos_potencia=_excesos_visalia_empresas(texto),
        reactiva=reactiva,
        iee=buscar_numero(texto, [
            r"Impuesto\s+sobre\s+electricidad\s*:\s*[\d.,]+\s*%\s*sobre\s*[\d.,]+\s*=\s*([\d.,]+)\s*€",
            r"Aplicaci[oó]n\s+impuesto\s+electricidad\s+m[ií]nimo[^\n]*?=\s*([\d.,]+)\s*€",
        ]),
        iva=buscar_numero(texto, [r"I\.?V\.?A\s+\d+\s*%\s*\(Base\s+Imponible\s+[-\d.,]+\s*€\)\s*=\s*([-\d.,]+)\s*€"]),
        total=buscar_numero(texto, [r"TOTAL\s+A\s+FACTURAR\s*:\s*([-\d.,]+)\s*€"]),
        energia_periodos=energia_periodos,
        potencias_contratadas=extraer_potencias_contratadas(texto),
        potencia_periodos=extraer_periodos_potencia(texto),
        maximetros=extraer_maximetros_visalia_empresas(texto),
        sobrepasamientos=sobrepasamientos,
        reactiva_periodos=reactiva_periodos,
        otros=_otros_comunes(texto),
    ))


def _sobrepasamientos_visalia_empresas(
    texto: str,
) -> list[SobrepasamientoPeriodo]:
    """Lee el detalle cuarto-horario P1-P6 publicado por Visalia Empresas."""
    bloque = _seccion(
        texto,
        r"Exceso\s+Potencia\s*\(m[eé]todo\s+cuarto\s+horario\)",
        r"(?:Financiaci[oó]n\s+bono\s+social|Impuesto\s+sobre\s+electricidad)",
    )
    return [
        SobrepasamientoPeriodo(f"P{periodo}", numero_es(exceso))
        for periodo, exceso in re.findall(
            r"^P([1-6]):\s*([\d.,]+)\s*kW\s*x\s*[\d.,]+\s*"
            r"€/kW\s*=\s*[\d.,]+\s*€\s*$",
            bloque,
            re.IGNORECASE | re.MULTILINE,
        )
    ]


def _excesos_visalia_empresas(texto: str) -> float:
    total_explicito = buscar_numero(texto, [
        r"Total\s+Excesos?\s+(?:de\s+)?Potencia\s*:?\s*([\d.,]+)\s*€",
        r"Excesos?\s+(?:de\s+)?Potencia\s+TOTAL\s*:?\s*([\d.,]+)\s*€",
    ])
    if total_explicito:
        return total_explicito

    en_bloque = False
    total = 0.0
    for linea in texto.splitlines():
        if re.search(r"\bExcesos?\s+(?:de\s+)?Potencia\b", linea, re.IGNORECASE):
            en_bloque = True
            continue

        if not en_bloque:
            continue

        linea_limpia = linea.strip()
        if not linea_limpia:
            continue
        if not re.match(r"P[1-6]\b", linea_limpia, re.IGNORECASE):
            break

        importe = re.search(r"=\s*([\d.,]+)\s*€", linea_limpia)
        if importe:
            total += numero_es(importe.group(1))

    return round(total, 2)


def extraer_reactiva_vm(
    texto: str,
    importe_facturado: float,
) -> list[ReactivaPeriodo]:
    """Reconstruye la reactiva P1-P6 publicada en la tabla de consumos VM."""
    from regulacion_reactiva import (
        exceso_reactiva_inductiva,
        factor_potencia,
        precio_reactiva_inductiva,
    )

    activa = re.search(
        r"^Consumo\s+kWh\s+((?:[\d.,]+\s+){5}[\d.,]+)\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    reactiva = re.search(
        r"^Consumo\s+kVArh\s+((?:[\d.,]+\s+){5}[\d.,]+)\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if not activa or not reactiva:
        return []
    activas = [numero_es(x) for x in re.findall(r"[\d.,]+", activa.group(1))]
    reactivas = [numero_es(x) for x in re.findall(r"[\d.,]+", reactiva.group(1))]
    if len(activas) != 6 or len(reactivas) != 6:
        return []

    calculos = []
    for indice, (kwh, kvarh) in enumerate(zip(activas, reactivas)):
        periodo = f"P{indice + 1}"
        cos_phi = factor_potencia(kwh, kvarh)
        exceso = exceso_reactiva_inductiva(kwh, kvarh, periodo)
        precio = precio_reactiva_inductiva(cos_phi, periodo)
        calculos.append((periodo, kwh, kvarh, exceso, cos_phi, precio, round(exceso * precio, 2)))

    total_calculado = round(sum(item[6] for item in calculos), 2)
    estado_total = semaforo_desviacion_coste(
        importe_facturado, total_calculado, "componentes"
    )
    facturados = [0.0] * 6
    indices_con_coste = [i for i, item in enumerate(calculos) if item[6] > 0]
    if importe_facturado and total_calculado and indices_con_coste:
        acumulado = 0.0
        for indice in indices_con_coste[:-1]:
            coste = round(importe_facturado * calculos[indice][6] / total_calculado, 2)
            facturados[indice] = coste
            acumulado += coste
        facturados[indices_con_coste[-1]] = round(importe_facturado - acumulado, 2)

    return [
        ReactivaPeriodo(
            periodo=periodo,
            energia_activa_kwh=kwh,
            energia_reactiva_kvarh=kvarh,
            exceso_facturado_kvarh=None,
            exceso_calculado_kvarh=round(exceso, 3),
            cos_phi=round(cos_phi, 4) if cos_phi is not None else None,
            precio_eur_kvarh=precio,
            coste_facturado_eur=facturados[indice],
            coste_calculado_eur=coste_calculado,
            estado=estado_total,
            detalle_coste_facturado=False,
        )
        for indice, (
            periodo, kwh, kvarh, exceso, cos_phi, precio, coste_calculado
        ) in enumerate(calculos)
    ]


def extraer_potencia_vm(texto: str) -> list[PotenciaFacturadaPeriodo]:
    """Lee las seis líneas VM, incluida P1 precedida por 'Término de potencia'."""
    coincidencias = re.findall(
        r"^(?:T[eé]rmino\s+de\s+potencia\s+)?(P[1-6])\s*:\s*"
        r"([\d.,]+)\s*kW\s*x\s*(\d+)\s*d[ií]as?\s*x\s*"
        r"([\d.,]+)\s*€/kW/d[ií]a\.?\s*([\d.,]+)\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    return [
        PotenciaFacturadaPeriodo(
            periodo=periodo.upper(),
            potencia_kw=numero_es(potencia),
            dias=int(dias),
            precio_facturado_eur_kw_dia=numero_es(precio),
            coste_facturado_eur=numero_es(coste),
            coste_calculado_eur=round(
                numero_es(potencia) * int(dias) * numero_es(precio), 2
            ),
        )
        for periodo, potencia, dias, precio, coste in coincidencias
    ]


def _concepto_energia_vm_indexado(
    texto: str,
    nombre: str,
    patrones: list[str],
) -> EnergiaPeriodo | None:
    importe = buscar_numero(texto, patrones)
    if not importe:
        return None
    return EnergiaPeriodo(
        periodo=nombre,
        consumo_kwh=0.0,
        precio_eur_kwh=0.0,
        coste_eur=importe,
        coste_calculado_eur=importe,
    )


def _vm(texto: str) -> FacturaLeida:
    inicio, fin = buscar_periodo(texto, [
        r"Periodo\s+de\s+facturaci[oó]n\s*:\s*(\d{2}/\d{2}/\d{4})\s+a\s+(\d{2}/\d{2}/\d{4})"
    ])
    meses = "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre"
    energia_periodos = extraer_periodos_energia(texto, [
        r"(P\d)\s*:\s*([\d.,]+)\s*kWh,\s*Precio:\s*([\d.,]+)\s*€/kWh\.?\s*([\d.,]+)"
    ])
    es_indexado = bool(re.search(
        r"(?:Total\s+)?Costes?\s+de\s+Mercado|Coste\s+Financiero|"
        r"Remuneraci[oó]n\s+(?:En[eé]rgya-)?VM",
        texto,
        re.IGNORECASE,
    ))
    if es_indexado:
        componentes_indexados = [
            _concepto_energia_vm_indexado(texto, "Costes de mercado", [
                r"Total\s+Costes\s+de\s+Mercado(?:\s+Total\s+Costes\s+de\s+Mercado)?\s+([\d.,]+)"
            ]),
            _concepto_energia_vm_indexado(texto, "Coste de mercado fijo industrial", [
                r"Coste\s+de\s+Mercado\s+Fijo\s+Industrial[^\n]*?"
                r"\s([-\d.,]+)\s*€?\s*$"
            ]),
            _concepto_energia_vm_indexado(texto, "Otros costes de comercialización", [
                r"Otros\s+costes(?:\s+Otros\s+costes\s+de\s+comercializaci[oó]n|\s+de\s+comercializaci[oó]n)\s+([\d.,]+)"
            ]),
            _concepto_energia_vm_indexado(texto, "Remuneración Enérgya-VM", [
                r"Remuneraci[oó]n\s+(?:En[eé]rgya-VM\s+)?Remuneraci[oó]n\s+En[eé]rgya-VM\s+([\d.,]+)",
                r"Remuneraci[oó]n\s+En[eé]rgya-VM\s+([\d.,]+)",
            ]),
        ]
        energia_periodos.extend(
            item for item in componentes_indexados if item is not None
        )
    energia_total = round(sum(item.coste_eur for item in energia_periodos), 2)
    importe_reactiva = buscar_numero(texto, [
        r"Complemento\s+por\s+reactiva\s+Energ[ií]a\s+Reactiva\s+([-\d.,]+)"
    ])
    otros = _otros_comunes(texto)
    if not any("alquiler" in item.concepto.lower() for item in otros):
        alquiler_vm = buscar_numero(texto, [
            r"Alquiler\s+equipo\s+de\s+medida[^\n]*?([\d.,]+)\s*€?\s*$"
        ])
        if alquiler_vm:
            otros.append(OtroConcepto("Alquiler equipo de medida", alquiler_vm))
    if es_indexado:
        coste_financiero = buscar_numero(texto, [
            r"Coste\s+Financiero(?:\s+Coste\s+Financiero)?[^\n]*?"
            r"([\d.,]+)\s*€?\s*$"
        ])
        if coste_financiero:
            otros.append(OtroConcepto("Coste financiero", coste_financiero))
    return _completar_advertencias(FacturaLeida(
        formato="vm_indexado" if es_indexado else "vm_fijo",
        comercializadora="VM Energía",
        numero_factura=buscar_texto(texto, [r"N[ºo]?\s*factura:\s*([A-Z]\d{7,})"]),
        cups=buscar_texto(texto, [r"CUPS\s*:\s*([A-Z0-9]+)"]),
        atr=extraer_atr(texto),
        fecha_factura=_fecha_es_a_ddmmyyyy(buscar_texto(texto, [
            rf"Fecha\s+emisi[oó]n:\s*(\d{{1,2}}\s+de\s+(?:{meses})\s+de\s+\d{{4}})"
        ])),
        periodo_inicio=inicio,
        periodo_fin=fin,
        potencia=sumar_coincidencias(texto, r"P\d\s*:\s*[\d.,]+\s*kW\s*x\s*\d+\s*d[ií]as[^\n]*?([\d.,]+)\s*$"),
        energia=energia_total,
        excesos_potencia=buscar_numero(texto, [r"Excesos\s+de\s+Potencia(?:\s+Excesos\s+de\s+Potencia)?\s*:?\s*([\d.,]+)"]),
        reactiva=importe_reactiva,
        iee=buscar_numero(texto, [
            r"Impuestos?\s+el[eé]ctricos?\s+[\d.,]+\s*€\s*x\s*[\d.,]+\s*%\s*([\d.,]+)",
            r"Impuestos?\s+el[eé]ctricos?\s+[\d.,]+\s*€/MWh\s*\*\s*[\d.,]+\s*(?:MWh|kWh)\s+consumidos\s+([\d.,]+)",
        ]),
        iva=buscar_numero(texto, [r"IVA\s+\d+%\s+([\d.,]+)"]),
        total=buscar_numero(texto, [r"TOTAL(?:\s+FACTURA)?\s*:?[ \t]*([\d.,]+)\s*€"]),
        energia_periodos=energia_periodos,
        potencias_contratadas=extraer_potencias_contratadas(texto),
        potencia_periodos=extraer_potencia_vm(texto),
        reactiva_periodos=extraer_reactiva_vm(texto, importe_reactiva),
        otros=otros,
    ))


def _imagina(texto: str) -> FacturaLeida:
    fechas = re.findall(r"\d{2}/\d{2}/\d{4}", texto)
    inicio = fechas[1] if len(fechas) >= 3 else None
    fin = fechas[2] if len(fechas) >= 3 else None
    energia_periodos = extraer_periodos_energia(texto, [
        r"(P\d)\s+([\d.,]+)\s+kWh\s+x\s+([\d.,]+)\s*€/kWh\s+([\d.,]+)\s*€",
        r"(P\d)\s+([\d.,]+)\s*kWh\s*\*\s*([\d.,]+)\s*€/kWh.*?\s+([\d.,]+)\s*€",
    ])
    return _completar_advertencias(FacturaLeida(
        formato="imagina",
        comercializadora="Imagina Energía",
        numero_factura=buscar_texto(texto, [r"^(FE\d{14}|FEN\d{13})$"]),
        cups=buscar_texto(texto, [r"([A-Z]{2}\d{16}[A-Z]{2})"]),
        atr=extraer_atr(texto),
        periodo_inicio=inicio,
        periodo_fin=fin,
        potencia=buscar_numero(texto, [r"Facturaci[oó]n\s+por\s+potencia\s+contratada\s+([\d.,]+)\s*€", r"Potencia:\s*([\d.,]+)\s*€"]),
        energia=buscar_numero(texto, [r"Facturaci[oó]n\s+por\s+energ[ií]a\s+consumida\s+([\d.,]+)\s*€", r"TOTAL\s+ENERG[IÍ]A\s+CONSUMIDA\s+([\d.,]+)\s*€"]),
        excesos_potencia=buscar_numero(texto, [r"T[eé]rmino\s+Excesos\s+Distribuidora\s+([\d.,]+)\s*€", r"Excesos\s+de\s+potencia\s+([\d.,]+)\s*€"]),
        reactiva=buscar_numero(texto, [r"T[eé]rmino\s+Reactiva\s+Distribuidora\s+([\d.,]+)\s*€", r"TOTAL\s+REACTIVA\s+([\d.,]+)\s*€"]),
        iee=buscar_numero(texto, [r"Imp\.\s+electricidad\s*\([^)]*\)\s*([\d.,]+)\s*€", r"Impuesto\s+El[eé]ctrico\s*\([^)]*\)\s*([\d.,]+)\s*€"]),
        iva=buscar_numero(texto, [r"IVA\s+\d+%\s+([\d.,]+)\s*€", r"IVA:\s*\(\d+%\s+s/[\d.,]+\s*€\)\s*([\d.,]+)\s*€"]),
        total=buscar_numero(texto, [r"Importe\s+total\s+a\s+abonar\s+([\d.,]+)\s*€", r"^TOTAL\s+([\d.,]+)\s*€"]),
        energia_periodos=energia_periodos,
        potencias_contratadas=extraer_potencias_contratadas(texto),
        potencia_periodos=extraer_periodos_potencia(texto),
        otros=_otros_comunes(texto),
    ))


def _fila_numerica(texto: str, etiqueta: str) -> list[float]:
    """Obtiene los números situados tras una etiqueta en una fila horizontal."""
    coincidencia = re.search(
        rf"^[^\n]*?{etiqueta}\s+([^\n]+)$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if not coincidencia:
        return []
    return [
        numero_es(valor)
        for valor in re.findall(r"-?\d+(?:[.,]\d+)?", coincidencia.group(1))
    ]


def _fila_numerica_tras_periodo(
    texto: str,
    etiqueta: str,
    miles_sin_decimales: bool = False,
) -> list[float]:
    """Lee una fila cuya fecha de vigencia aparece antes de los valores P1-P6."""
    coincidencia = re.search(
        rf"^[^\n]*?{etiqueta}[^\n]*?\d{{2}}/\d{{2}}/\d{{2,4}}\s*-\s*"
        rf"\d{{2}}/\d{{2}}/\d{{2,4}}\s+([^\n]+)$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    if not coincidencia:
        return []
    valores = re.findall(r"-?\d[\d.]*(?:,\d+)?", coincidencia.group(1))
    conversor = consumo_es if miles_sin_decimales else numero_es
    return [conversor(valor) for valor in valores]


def _seccion(texto: str, inicio: str, fin: str) -> str:
    coincidencia = re.search(
        rf"{inicio}(.*?)(?={fin})",
        texto,
        re.IGNORECASE | re.DOTALL,
    )
    return coincidencia.group(1) if coincidencia else ""


def extraer_energia_matricial(texto: str) -> list[EnergiaPeriodo]:
    """Lee tablas horizontales con filas de consumo, precio e importe P1-P6."""
    bloque = _seccion(
        texto,
        r"Facturaci[oó]n\s+energ[ií]a\s+consumida",
        r"Facturaci[oó]n\s+potencia",
    )
    consumos = _fila_numerica(bloque, r"Consumo\s+kWh")
    precios = _fila_numerica(bloque, r"Precio\s+€/kWh")
    importes = _fila_numerica(bloque, r"Importe\s+por\s+energ[ií]a\s+consumida")
    if min(len(consumos), len(precios), len(importes)) < 6:
        return []
    return [
        EnergiaPeriodo(
            periodo=f"P{indice + 1}",
            consumo_kwh=consumos[indice],
            precio_eur_kwh=precios[indice],
            coste_eur=importes[indice],
        )
        for indice in range(6)
    ]


def extraer_energia_horizontal_con_periodo(texto: str) -> list[EnergiaPeriodo]:
    """Combina coste de producto y ATR en tablas horizontales con huecos."""
    consumos = _fila_numerica_tras_periodo(
        texto,
        r"Energ.a\s+Activa\s+consumida\s+kWh",
        miles_sin_decimales=True,
    )
    costes_producto = _fila_numerica_tras_periodo(
        texto, r"Total\s+Coste\s+de\s+Energ.a\s+producto"
    )
    precios_atr = _fila_numerica_tras_periodo(
        texto, r"Precio\s+t.rmino\s+de\s+Energ.a\s+ATR"
    )
    costes_atr = _fila_numerica_tras_periodo(
        texto, r"Total\s+T.rmino\s+de\s+Energ.a\s+ATR"
    )
    if (
        len(consumos) < 2 or len(costes_producto) < 2
        or len(precios_atr) < 6 or len(costes_atr) < 2
    ):
        return []

    consumos = consumos[:-1]
    costes_producto = costes_producto[:-1]
    costes_atr = costes_atr[:-1]
    if not (len(consumos) == len(costes_producto) == len(costes_atr)):
        return []

    disponibles = set(range(6))
    resultado = []
    for consumo, coste_producto, coste_atr in zip(
        consumos, costes_producto, costes_atr
    ):
        indice = min(
            disponibles,
            key=lambda candidato: abs(
                consumo * precios_atr[candidato] - coste_atr
            ),
        )
        disponibles.remove(indice)
        coste_total = round(coste_producto + coste_atr, 2)
        resultado.append(EnergiaPeriodo(
            periodo=f"P{indice + 1}",
            consumo_kwh=consumo,
            precio_eur_kwh=coste_total / consumo if consumo else 0.0,
            coste_eur=coste_total,
        ))
    return sorted(resultado, key=lambda item: int(item.periodo[1:]))


def extraer_energia_activa_vertical(texto: str) -> list[EnergiaPeriodo]:
    patron = (
        r"^P([1-6])\.\s+Energ[ií]a\s+activa\s+([\d.,]+)\s+kWh\s+"
        r"([\d.,]+)\s+([\d.,]+)\s*$"
    )
    coincidencias = re.findall(patron, texto, re.IGNORECASE | re.MULTILINE)
    if not coincidencias:
        return []
    periodos = [
        EnergiaPeriodo(
            periodo=f"P{periodo}",
            consumo_kwh=consumo_es(consumo),
            precio_eur_kwh=numero_es(precio),
            coste_eur=numero_es(coste),
        )
        for periodo, consumo, precio, coste in coincidencias
    ]
    costes_regulados = sumar_coincidencias(
        texto,
        r"^Importe\s+(?:peaje[^\n]*|cargos[^\n]*)\s+([\d.,]+)\s*$",
    )
    consumo_total = sum(item.consumo_kwh for item in periodos)
    if costes_regulados and consumo_total:
        for item in periodos:
            parte = costes_regulados * item.consumo_kwh / consumo_total
            item.coste_eur = round(item.coste_eur + parte, 2)
            item.precio_eur_kwh = item.coste_eur / item.consumo_kwh
        ajuste = round(
            sum(numero_es(coste) for *_, coste in coincidencias)
            + costes_regulados
            - sum(item.coste_eur for item in periodos),
            2,
        )
        periodos[-1].coste_eur = round(periodos[-1].coste_eur + ajuste, 2)
        periodos[-1].precio_eur_kwh = (
            periodos[-1].coste_eur / periodos[-1].consumo_kwh
        )
    return periodos


def extraer_energia_desglosada_por_bloques(texto: str) -> list[EnergiaPeriodo]:
    """Agrupa ATR y energía variable cuando repiten consumo y periodo."""
    patron = (
        r"(?:^|·\s*)P([1-6])\s+([\d.,]+)\s+kWh\s+x\s+"
        r"([\d.,]+)\s*€/kWh\s+([\d.,]+)\s*€"
    )
    coincidencias = re.findall(patron, texto, re.IGNORECASE | re.MULTILINE)
    if not coincidencias:
        return []
    agrupado: dict[str, dict[str, float]] = {}
    for periodo, consumo, _precio, coste in coincidencias:
        clave = f"P{periodo}"
        dato = agrupado.setdefault(
            clave, {"consumo": consumo_es(consumo), "coste": 0.0}
        )
        dato["coste"] += numero_es(coste)
    return [
        EnergiaPeriodo(
            periodo=periodo,
            consumo_kwh=dato["consumo"],
            precio_eur_kwh=dato["coste"] / dato["consumo"] if dato["consumo"] else 0,
            coste_eur=round(dato["coste"], 2),
        )
        for periodo, dato in sorted(
            agrupado.items(), key=lambda item: int(item[0][1:])
        )
    ]


def extraer_energia_centimos_con_periodo(texto: str) -> list[EnergiaPeriodo]:
    """Lee lineas ``EnergiaP1`` con el precio expresado en centimos/kWh."""
    patron = (
        r"^Energ[ií]a\s*P([1-6])\s+"
        r"\d{2}/\d{2}/\d{4}\s*-\s*\d{2}/\d{2}/\d{4}\s+"
        r"([\d.,]+)\s*kWh\s+([\d.,]+)\s*cent\s*€/kWh\b"
        r"[^\n]*?([\d.,]+)\s*€\s*$"
    )
    return [
        EnergiaPeriodo(
            periodo=f"P{periodo}",
            consumo_kwh=consumo_es(consumo),
            precio_eur_kwh=numero_es(precio_centimos) / 100,
            coste_eur=numero_es(coste),
        )
        for periodo, consumo, precio_centimos, coste in re.findall(
            patron, texto, re.IGNORECASE | re.MULTILINE
        )
    ]


def extraer_energia_por_componentes(texto: str) -> list[EnergiaPeriodo]:
    """Agrupa varias lineas de energia para un mismo periodo y consumo."""
    patron = (
        r"^(?:T[eé]rmino\s+Energ[ií]a[^\n]*?\s+)?P([1-6])\s+"
        r"([\d.,]+)\s*kWh\s*x\s*([\d.,]+)\s*€/kWh\s+"
        r"([\d.,]+)\s*€\s*$"
    )
    coincidencias = re.findall(patron, texto, re.IGNORECASE | re.MULTILINE)
    if not coincidencias:
        return []
    agrupado: dict[str, dict[str, float]] = {}
    for periodo, consumo, _precio, coste in coincidencias:
        clave = f"P{periodo}"
        consumo_kwh = consumo_es(consumo)
        dato = agrupado.setdefault(
            clave,
            {"consumo": consumo_kwh, "precio": 0.0, "coste": 0.0, "calculado": 0.0},
        )
        if abs(dato["consumo"] - consumo_kwh) > 0.001:
            return []
        precio = numero_es(_precio)
        dato["precio"] += precio
        dato["coste"] += numero_es(coste)
        dato["calculado"] += round(consumo_kwh * precio, 2)
    return [
        EnergiaPeriodo(
            periodo=periodo,
            consumo_kwh=dato["consumo"],
            precio_eur_kwh=dato["precio"],
            coste_eur=round(dato["coste"], 2),
            coste_calculado_eur=round(dato["calculado"], 2),
        )
        for periodo, dato in sorted(agrupado.items(), key=lambda item: int(item[0][1:]))
    ]


def extraer_potencia_matricial(
    texto: str,
    periodo_inicio: str | None,
    periodo_fin: str | None,
) -> list[PotenciaFacturadaPeriodo]:
    bloque = _seccion(
        texto,
        r"Facturaci[oó]n\s+potencia\s+contratada",
        r"Facturaci[oó]n\s+energ[ií]a\s+reactiva",
    )
    potencias = _fila_numerica(bloque, r"Potencia\s+facturada\s+kW")
    precios = _fila_numerica(bloque, r"Precio\s+€/kW\s+y\s+d[ií]a")
    importes = _fila_numerica(bloque, r"Importe\s+por\s+potencia")
    if min(len(potencias), len(precios), len(importes)) < 6:
        return []
    try:
        inicio = datetime.strptime(periodo_inicio or "", "%d/%m/%Y")
        fin = datetime.strptime(periodo_fin or "", "%d/%m/%Y")
        dias = (fin - inicio).days + 1
    except ValueError:
        dias = 0
    return [
        PotenciaFacturadaPeriodo(
            periodo=f"P{indice + 1}",
            potencia_kw=potencias[indice],
            dias=dias,
            precio_facturado_eur_kw_dia=precios[indice],
            coste_facturado_eur=importes[indice],
        )
        for indice in range(6)
    ]


def extraer_potencia_horizontal_con_periodo(
    texto: str,
    periodo_inicio: str | None,
    periodo_fin: str | None,
) -> list[PotenciaFacturadaPeriodo]:
    potencias = _fila_numerica_tras_periodo(texto, r"Potencia\s+facturada\s+kW")
    precios_anuales = _fila_numerica_tras_periodo(
        texto, r"Precio\s+t.rmino\s+Potencia"
    )
    importes = _fila_numerica_tras_periodo(
        texto, r"Total\s+t.rmino\s+de\s+potencia"
    )
    if min(len(potencias), len(precios_anuales), len(importes)) < 6:
        return []
    try:
        ejercicio = datetime.strptime(periodo_inicio or "", "%d/%m/%Y").year
        inicio = datetime.strptime(periodo_inicio or "", "%d/%m/%Y")
        fin = datetime.strptime(periodo_fin or "", "%d/%m/%Y")
        dias = (fin - inicio).days + 1
    except ValueError:
        return []
    divisor = 366 if calendar.isleap(ejercicio) else 365
    return [
        PotenciaFacturadaPeriodo(
            periodo=f"P{indice + 1}",
            potencia_kw=potencias[indice],
            dias=dias,
            precio_facturado_eur_kw_dia=precios_anuales[indice] / divisor,
            coste_facturado_eur=importes[indice],
        )
        for indice in range(6)
    ]


def extraer_potencia_anual_dos_lineas(
    texto: str,
) -> list[PotenciaFacturadaPeriodo]:
    patron = (
        r"^P([1-6])\.\s+Precio:\s*([\d.,]+)\s+X\s*\((\d+)\s*/\s*(\d+)\)"
        r"[^\n]*\nP\1\.\s+Potencia\s+facturada\s+([\d.,]+)\s+kW\s+"
        r"[\d.,]+\s+([\d.,]+)\s*$"
    )
    coincidencias = re.findall(patron, texto, re.IGNORECASE | re.MULTILINE)
    return [
        PotenciaFacturadaPeriodo(
            periodo=f"P{periodo}",
            potencia_kw=numero_es(potencia),
            dias=int(dias),
            precio_facturado_eur_kw_dia=numero_es(precio_anual) / int(divisor),
            coste_facturado_eur=numero_es(coste),
        )
        for periodo, precio_anual, dias, divisor, potencia, coste in coincidencias
    ]


def extraer_potencia_vertical_con_viñetas(
    texto: str,
) -> list[PotenciaFacturadaPeriodo]:
    patron = (
        r"(?:^|·\s*)P([1-6])\s+([\d.,]+)\s+kW\s+x\s+(\d+)\s+D[ií]as\s+x\s+"
        r"([\d.,]+)\s*€/kW\s+d[ií]a\s+([\d.,]+)\s*€"
    )
    return [
        PotenciaFacturadaPeriodo(
            periodo=f"P{periodo}",
            potencia_kw=numero_es(potencia),
            dias=int(dias),
            precio_facturado_eur_kw_dia=numero_es(precio),
            coste_facturado_eur=numero_es(coste),
        )
        for periodo, potencia, dias, precio, coste in re.findall(
            patron, texto, re.IGNORECASE | re.MULTILINE
        )
    ]


def extraer_potencia_centimos_con_periodo(
    texto: str,
) -> list[PotenciaFacturadaPeriodo]:
    """Lee lineas ``PotenciaP1`` con precios en centimos por kW y dia."""
    patron = (
        r"^Potencia\s*P([1-6])\s+"
        r"\d{2}/\d{2}/\d{4}\s*-\s*\d{2}/\d{2}/\d{4}\s+"
        r"([\d.,]+)\s*kW\s+([\d.,]+)\s*cent\s*€/kW/d[ií]a\s+"
        r"(\d+)\b[^\n]*?([\d.,]+)\s*€\s*$"
    )
    return [
        PotenciaFacturadaPeriodo(
            periodo=f"P{periodo}",
            potencia_kw=numero_es(potencia),
            dias=int(dias),
            precio_facturado_eur_kw_dia=numero_es(precio_centimos) / 100,
            coste_facturado_eur=numero_es(coste),
        )
        for periodo, potencia, precio_centimos, dias, coste in re.findall(
            patron, texto, re.IGNORECASE | re.MULTILINE
        )
    ]


def extraer_potencia_con_prefijo(texto: str) -> list[PotenciaFacturadaPeriodo]:
    """Lee potencia cuando la primera linea incluye el nombre del concepto."""
    patron = (
        r"^(?:(?:T[eé]rmino\s+Potencia[^\n]*?|Potencia\s+facturada)\s+)?"
        r"P([1-6])\s+"
        r"([\d.,]+)\s*kW\s*x\s*(\d+)\s*D[ií]as\s*x\s*"
        r"([\d.,]+)\s*€/kW\s*d[ií]a\s+([\d.,]+)\s*€\s*$"
    )
    return [
        PotenciaFacturadaPeriodo(
            periodo=f"P{periodo}",
            potencia_kw=numero_es(potencia),
            dias=int(dias),
            precio_facturado_eur_kw_dia=numero_es(precio),
            coste_facturado_eur=numero_es(coste),
        )
        for periodo, potencia, dias, precio, coste in re.findall(
            patron, texto, re.IGNORECASE | re.MULTILINE
        )
    ]


def extraer_potencia_gana(texto: str) -> list[PotenciaFacturadaPeriodo]:
    patron = (
        r"^T[eé]rmino\s+potencia\s+\d{2}-\d{2}-\d{4}\s*/\s*"
        r"\d{2}-\d{2}-\d{4}\s+(\d+)\s+d[ií]as\s*-\s*P([12])\s*:\s*"
        r"([\d.,]+)\s*kW\s*-\s*Precio\s*:\s*([\d.,]+)\s+"
        r"([\d.,]+)\s*€\s*$"
    )
    return [
        PotenciaFacturadaPeriodo(
            periodo=f"P{periodo}",
            potencia_kw=numero_es(potencia),
            dias=int(dias),
            precio_facturado_eur_kw_dia=numero_es(precio),
            coste_facturado_eur=numero_es(coste),
        )
        for dias, periodo, potencia, precio, coste in re.findall(
            patron, texto, re.IGNORECASE | re.MULTILINE
        )
    ]


def extraer_potencia_asteriscos(texto: str) -> list[PotenciaFacturadaPeriodo]:
    patron = (
        r"\bP([1-6])\s*:\s*([\d.,]+)\s*kW\s*\*\s*([\d.,]+)\s*"
        r"€/kW\s*\*\s*(\d+)\s*d[ií]a\(s\)\s+([\d.,]+)\s*€\s*$"
    )
    return [
        PotenciaFacturadaPeriodo(
            periodo=f"P{periodo}", potencia_kw=numero_es(potencia),
            dias=int(dias), precio_facturado_eur_kw_dia=numero_es(precio),
            coste_facturado_eur=numero_es(coste),
        )
        for periodo, potencia, precio, dias, coste in re.findall(
            patron, texto, re.IGNORECASE | re.MULTILINE
        )
    ]


def extraer_energia_asteriscos(texto: str) -> list[EnergiaPeriodo]:
    patron = (
        r"\bP([1-6])\s*:\s*([\d.,]+)\s*kWh\s*\*\s*([\d.,]+)\s*"
        r"€/kWh\s+([\d.,]+)\s*€\s*$"
    )
    return [
        EnergiaPeriodo(f"P{periodo}", consumo_es(consumo), numero_es(precio), numero_es(coste))
        for periodo, consumo, precio, coste in re.findall(
            patron, texto, re.IGNORECASE | re.MULTILINE
        )
    ]


def extraer_potencia_on510(texto: str) -> list[PotenciaFacturadaPeriodo]:
    patron = (
        r"\bP([1-6])\s+([\d.,]+)\s*kW\s*\*\s*([\d.,]+)\s*€/kW\s*\*\s*"
        r"\(\s*(\d+)\s*/\s*365\s*\)\s*d[ií]as[^\n]*?([\d.,]+)\s*€"
    )
    por_periodo = {}
    for periodo, potencia, precio, dias, coste in re.findall(
        patron, texto, re.IGNORECASE
    ):
        por_periodo.setdefault(periodo, PotenciaFacturadaPeriodo(
            periodo=f"P{periodo}", potencia_kw=numero_es(potencia),
            dias=int(dias), precio_facturado_eur_kw_dia=numero_es(precio),
            coste_facturado_eur=numero_es(coste),
        ))
    return [por_periodo[p] for p in sorted(por_periodo, key=int)]


def extraer_energia_on510(texto: str) -> list[EnergiaPeriodo]:
    patron = (
        r"\bP([1-6])\s+([\d.,]+)\s*kWh\s*\*\s*([\d.,]+)\s*€/kWh"
        r"[^\n]*?([\d.,]+)\s*€"
    )
    por_periodo = {}
    for periodo, consumo, precio, coste in re.findall(
        patron, texto, re.IGNORECASE
    ):
        por_periodo.setdefault(periodo, EnergiaPeriodo(
            f"P{periodo}", consumo_es(consumo), numero_es(precio), numero_es(coste)
        ))
    return [por_periodo[p] for p in sorted(por_periodo, key=int)]


def extraer_maximetros_canaluz(texto: str) -> list[MaximetroPeriodo]:
    bloque = _seccion(texto, r"LECTURA\s+LECTURA\s+POTENCIA", r"HORARIOS\s*/\s*PERIODOS")
    resultado = []
    for periodo, resto in re.findall(
        r"\bP([1-6])\s+([^\n]+)$", bloque, re.IGNORECASE | re.MULTILINE
    ):
        valores = re.findall(r"[\d.]+,\d+", resto)
        if len(valores) >= 4:
            resultado.append(MaximetroPeriodo(f"P{periodo}", numero_es(valores[3])))
    return resultado


def extraer_reactiva_canaluz(
    texto: str, energia_periodos: list[EnergiaPeriodo]
) -> list[ReactivaPeriodo]:
    from regulacion_reactiva import (
        exceso_reactiva_inductiva, factor_potencia, precio_reactiva_inductiva,
    )
    activas = {item.periodo: item.consumo_kwh for item in energia_periodos}
    lecturas = {
        f"P{periodo}": numero_es(reactiva)
        for periodo, reactiva in re.findall(
            r"^P([1-6])\s+[\d.,]+\s+[\d.,]+\s+[\d.,]+\s+[\d.,]+\s+([\d.,]+)\s*$",
            _seccion(texto, r"LECTURA\s+LECTURA\s+POTENCIA", r"HORARIOS\s*/\s*PERIODOS"),
            re.IGNORECASE | re.MULTILINE,
        )
    }
    patron = (
        r"^P([1-6])\s*:\s*([\d.,]+)\s*kVArh\s*\*\s*([\d.,]+)\s*"
        r"€/kVArh\s+([\d.,]+)\s*€\s*$"
    )
    resultado = []
    for periodo_num, exceso_txt, precio_txt, coste_txt in re.findall(
        patron, texto, re.IGNORECASE | re.MULTILINE
    ):
        periodo = f"P{periodo_num}"
        activa = activas.get(periodo, 0.0)
        reactiva = lecturas.get(periodo, 0.0)
        exceso = exceso_reactiva_inductiva(activa, reactiva, periodo)
        cos_phi = factor_potencia(activa, reactiva)
        precio_regulado = precio_reactiva_inductiva(cos_phi, periodo)
        coste_calculado = round(exceso * precio_regulado, 2)
        coste_facturado = numero_es(coste_txt)
        resultado.append(ReactivaPeriodo(
            periodo=periodo, energia_activa_kwh=activa,
            energia_reactiva_kvarh=reactiva,
            exceso_facturado_kvarh=numero_es(exceso_txt),
            exceso_calculado_kvarh=round(exceso, 3),
            cos_phi=round(cos_phi, 4) if cos_phi is not None else None,
            precio_eur_kvarh=numero_es(precio_txt),
            coste_facturado_eur=coste_facturado,
            coste_calculado_eur=coste_calculado,
            estado=semaforo_desviacion_coste(coste_facturado, coste_calculado),
        ))
    return resultado


def _filas_totalenergies(bloque: str) -> dict[str, tuple[float, float, float]]:
    """Agrupa por periodo las líneas kW/kWh de un bloque TotalEnergies."""
    filas: dict[str, tuple[float, float, float]] = {}
    patron = (
        r"^P([1-6])\s+([\d.,]+)\s*(?:kW|kWh)\s+x\s+"
        r"(?:\d+\s+D[ií]as\s+x\s+)?([\d.,]+)\s*€/[^\s]+(?:\s+d[ií]a)?\s+"
        r"([\d.,]+)\s*€\s*$"
    )
    for periodo, cantidad, precio, coste in re.findall(
        patron, bloque, re.IGNORECASE | re.MULTILINE
    ):
        clave = f"P{periodo}"
        cantidad_num = numero_es(cantidad)
        precio_num = numero_es(precio)
        coste_num = numero_es(coste)
        cantidad_anterior, precio_anterior, coste_anterior = filas.get(
            clave, (cantidad_num, 0.0, 0.0)
        )
        filas[clave] = (
            cantidad_anterior,
            precio_anterior + precio_num,
            coste_anterior + coste_num,
        )
    return filas


def extraer_potencia_totalenergies(texto: str) -> list[PotenciaFacturadaPeriodo]:
    bloque = _seccion(
        texto,
        r"T[eé]rmino\s+Potencia\s+Tarifa\s+Acceso",
        r"T[eé]rmino\s+Cargos\s+Potencia\s+Acceso",
    )
    filas = _filas_totalenergies(bloque)
    dias = buscar_numero(bloque, [r"\bkW\s+x\s+(\d+)\s+D[ií]as"])
    return [
        PotenciaFacturadaPeriodo(
            periodo=periodo,
            potencia_kw=cantidad,
            dias=int(dias),
            precio_facturado_eur_kw_dia=round(precio, 6),
            coste_facturado_eur=round(coste, 2),
            coste_calculado_eur=round(coste, 2),
        )
        for periodo, (cantidad, precio, coste) in sorted(filas.items())
    ] if dias else []


def extraer_energia_totalenergies(texto: str) -> list[EnergiaPeriodo]:
    tarifa = _seccion(
        texto,
        r"T[eé]rmino\s+Energ[ií]a\s+Tarifa\s+Acceso",
        r"T[eé]rmino\s+Cargos\s+Energ[ií]a\s+Acceso",
    )
    variable = _seccion(
        texto,
        r"T[eé]rmino\s+Energ[ií]a\s+Variable",
        r"Impuesto\s+Electricidad",
    )
    filas = _filas_totalenergies(tarifa + "\n" + variable)
    return [
        EnergiaPeriodo(
            periodo=periodo,
            consumo_kwh=cantidad,
            precio_eur_kwh=round(precio, 6),
            coste_eur=round(coste, 2),
            coste_calculado_eur=round(coste, 2),
        )
        for periodo, (cantidad, precio, coste) in sorted(filas.items())
    ]


def extraer_energia_gana(texto: str) -> list[EnergiaPeriodo]:
    patron = (
        r"^T[eé]rmino\s+energ[ií]a\s+\d{2}-\d{2}-\d{4}\s*/\s*"
        r"\d{2}-\d{2}-\d{4}\s+\d+\s+d[ií]as\s*-\s*P([1-3])\s*:\s*"
        r"([\d.,]+)\s*kWh\s*-\s*Precio\s*:\s*([\d.,]+)\s+"
        r"([\d.,]+)\s*€\s*$"
    )
    return [
        EnergiaPeriodo(
            periodo=f"P{periodo}",
            consumo_kwh=consumo_es(consumo),
            precio_eur_kwh=numero_es(precio),
            coste_eur=numero_es(coste),
        )
        for periodo, consumo, precio, coste in re.findall(
            patron, texto, re.IGNORECASE | re.MULTILINE
        )
    ]


def extraer_maximetros_etiquetados(texto: str) -> list[MaximetroPeriodo]:
    linea = buscar_texto(texto, [r"Potencia\s+m[aá]xima\s+demandada\s*\n([^\n]+)"])
    if not linea:
        return []
    return [
        MaximetroPeriodo(f"P{periodo}", numero_es(valor))
        for periodo, valor in re.findall(r"P([1-6])\s*:\s*([\d.,]+)", linea, re.IGNORECASE)
    ]


def extraer_medidas_verticales(
    texto: str,
    concepto: str,
) -> list[MaximetroPeriodo]:
    patron = (
        rf"{concepto}\s+Periodo\s+([1-6])\s*\(W\)[^\n]*?"
        rf"\d{{2}}/\d{{2}}/\d{{4}}\s+([\d.,]+)\s*$"
    )
    return [
        MaximetroPeriodo(
            periodo=f"P{periodo}",
            potencia_kw=consumo_es(valor) / 1000,
        )
        for periodo, valor in re.findall(
            patron, texto, re.IGNORECASE | re.MULTILINE
        )
    ]


def extraer_maximetros_matriciales(texto: str) -> list[MaximetroPeriodo]:
    valores_directos = _fila_numerica(texto, r"Max[ií]metros?\s*\(kW\)")
    if valores_directos:
        valores = (
            valores_directos[1:7]
            if len(valores_directos) >= 7
            else valores_directos[:6]
        )
    else:
        valores = _fila_numerica_tras_periodo(
            texto, r"Potencia\s+m[aá]xima\s+demandada\s+kW"
        )[:6]
    return [
        MaximetroPeriodo(periodo=f"P{indice + 1}", potencia_kw=valor)
        for indice, valor in enumerate(valores[:6])
    ] if len(valores) >= 6 else []


def extraer_maximetros_demanda_parcial(
    texto: str,
    energia_periodos: list[EnergiaPeriodo],
) -> list[MaximetroPeriodo]:
    """Asocia una fila parcial de máximas a los periodos con consumo facturado."""
    linea = buscar_texto(texto, [
        r"Potencia\s+m[aá]x\.?\s+demandada\s*\(kW\)\s+([^\n]+)",
        r"Potencia\s+m[aá]xima\s+demandada\s*\(kW\)\s+([^\n]+)",
    ])
    if not linea:
        return []
    valores = [numero_es(valor) for valor in re.findall(r"[\d.,]+", linea)]
    periodos = [item.periodo for item in energia_periodos if item.consumo_kwh]
    if not valores or len(valores) != len(periodos):
        return []
    return [
        MaximetroPeriodo(periodo, valor)
        for periodo, valor in zip(periodos, valores)
    ]


def extraer_sobrepasamientos_matriciales(
    texto: str,
) -> list[SobrepasamientoPeriodo]:
    valores = _fila_numerica_tras_periodo(texto, r"Excesos\s+Potencia\s+kW")
    if not valores:
        valores_directos = _fila_numerica(
            texto, r"Max[ií]metro\s+Excesos\s*\(kW\)"
        )
        valores = (
            valores_directos[1:7]
            if len(valores_directos) >= 7
            else valores_directos[:6]
        )
    return [
        SobrepasamientoPeriodo(periodo=f"P{indice + 1}", exceso_kw=valor)
        for indice, valor in enumerate(valores[:6])
    ] if len(valores) >= 6 else []


def extraer_total_excesos_horizontal(texto: str) -> float:
    valores = _fila_numerica_tras_periodo(
        texto, r"Total\s+excesos\s+de\s+potencia"
    )
    return valores[-1] if len(valores) >= 7 else 0.0


def extraer_excesos_detallados_maximetro(
    texto: str,
    potencias: list[PotenciaContratadaPeriodo],
) -> tuple[list[SobrepasamientoPeriodo], list[MaximetroPeriodo], float]:
    """Lee filas periodo, sobrepasamiento, TEP e importe bajo Maxímetros."""
    bloque = _seccion(
        texto,
        r"Excesos\s+de\s+potencia\s*\(Max[ií]metros?\)",
        r"(?:COMPENSACI[OÓ]N|Financiaci[oó]n\s+Bono|I\.?E\.?)",
    )
    coincidencias = re.findall(
        r"^P([1-6])\s+([\d.,]+)\s+x\s+([\d.,]+)\s*€\s+"
        r"([\d.,]+)\s*€\s*$",
        bloque,
        re.IGNORECASE | re.MULTILINE,
    )
    if not coincidencias:
        return [], [], 0.0
    contratadas = {
        item.periodo: item.potencia_kw for item in potencias
    }
    sobrepasamientos = []
    maximetros = []
    total = 0.0
    for periodo_num, exceso_txt, _tepp_txt, coste_txt in coincidencias:
        periodo = f"P{periodo_num}"
        exceso = numero_es(exceso_txt)
        coste = numero_es(coste_txt)
        sobrepasamientos.append(SobrepasamientoPeriodo(periodo, exceso))
        if periodo in contratadas:
            maximetros.append(MaximetroPeriodo(
                periodo,
                round(contratadas[periodo] + exceso, 3),
            ))
        total += coste
    return sobrepasamientos, maximetros, round(total, 2)


def extraer_reactiva_matricial(texto: str) -> list[ReactivaPeriodo]:
    """Reconstruye reactiva cuando el PDF publica lecturas y coste P1-P6."""
    from regulacion_reactiva import (
        exceso_reactiva_inductiva,
        factor_potencia,
        precio_reactiva_inductiva,
    )

    activas = _fila_numerica(texto, r"Consumo\s+activa\s*\(kWh\)")
    reactivas = _fila_numerica(texto, r"Consumo\s+reactiva\s*\(kVArh\)")
    bloque = _seccion(
        texto,
        r"Facturaci[oó]n\s+energ[ií]a\s+reactiva",
        r"Excesos\s+de\s+Potencia",
    )
    excesos_facturados = _fila_numerica(bloque, r"Consumo\s+kVArh")
    precios = _fila_numerica(bloque, r"Precio\s+€/kVArh")
    costes = _fila_numerica(bloque, r"Importe\s+por\s+energ[ií]a\s+reactiva")
    if min(
        len(activas), len(reactivas), len(excesos_facturados),
        len(precios), len(costes),
    ) < 6:
        return []

    resultado = []
    for indice in range(6):
        periodo = f"P{indice + 1}"
        cos_phi = factor_potencia(activas[indice], reactivas[indice])
        exceso_calculado = exceso_reactiva_inductiva(
            activas[indice], reactivas[indice], periodo
        )
        precio_regulado = precio_reactiva_inductiva(cos_phi, periodo)
        coste_calculado = round(exceso_calculado * precio_regulado, 2)
        coste_facturado = costes[indice]
        resultado.append(ReactivaPeriodo(
            periodo=periodo,
            energia_activa_kwh=activas[indice],
            energia_reactiva_kvarh=reactivas[indice],
            exceso_facturado_kvarh=excesos_facturados[indice],
            exceso_calculado_kvarh=round(exceso_calculado, 3),
            cos_phi=round(cos_phi, 4) if cos_phi is not None else None,
            precio_eur_kvarh=precios[indice],
            coste_facturado_eur=coste_facturado,
            coste_calculado_eur=coste_calculado,
            estado=semaforo_desviacion_coste(
                coste_facturado, coste_calculado, "componentes"
            ),
        ))
    return resultado


def extraer_energia_eni_plenitude(texto: str) -> list[EnergiaPeriodo]:
    """Agrupa peajes y cargos P1-P6 y añade los componentes indexados."""
    por_periodo: dict[str, EnergiaPeriodo] = {}
    for periodo, consumo, precio, coste in re.findall(
        r"^(P[1-6]):\s*([\d.,]+)\s*kWh\s*x\s*([\d.,]+)\s*€/kWh\s+"
        r"([-\d.,]+)\s*€\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    ):
        periodo = periodo.upper()
        consumo_kwh = consumo_es(consumo)
        precio_kwh = numero_es(precio)
        coste_eur = numero_es(coste)
        if periodo not in por_periodo:
            por_periodo[periodo] = EnergiaPeriodo(
                periodo, consumo_kwh, precio_kwh, coste_eur
            )
        else:
            item = por_periodo[periodo]
            item.precio_eur_kwh += precio_kwh
            item.coste_eur += coste_eur
        por_periodo[periodo].coste_calculado_eur = round(
            por_periodo[periodo].consumo_kwh
            * por_periodo[periodo].precio_eur_kwh,
            2,
        )

    resultado = [por_periodo[p] for p in sorted(por_periodo)]
    for nombre, patrones in (
        ("Costes de mercado", [
            r"Total\s+Costes\s+de\s+Mercado\s+([\d.,]+)\s*€"
        ]),
        ("Ajuste adenda cierres", [
            r"Ajuste\s+adenda\s+cierres\s+([-\d.,]+)\s*€"
        ]),
        ("Remuneración", [r"^Remuneraci[oó]n\s+([\d.,]+)\s*€\s*$"]),
    ):
        importe = buscar_numero(texto, patrones)
        if importe:
            resultado.append(EnergiaPeriodo(
                nombre, 0.0, 0.0, importe, coste_calculado_eur=importe
            ))
    return resultado


def extraer_maximetros_eni_plenitude(texto: str) -> list[MaximetroPeriodo]:
    return [
        MaximetroPeriodo(periodo.upper(), numero_es(potencia))
        for periodo, potencia in re.findall(
            r"^MAXIMETRO\s+(P[1-6])\s+\d{2}/\d{2}/\d{4}\s+"
            r"\d{2}/\d{2}/\d{4}\s+([\d.,]+)\s*kW\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        )
    ]


def _axpo(texto: str) -> FacturaLeida:
    def fecha_corta(valor: str | None) -> str | None:
        if not valor:
            return None
        for formato in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(valor, formato).strftime("%d/%m/%Y")
            except ValueError:
                continue
        return valor

    inicio_txt, fin_txt = buscar_periodo(texto, [
        r"Periodo\s+factura\s*:\s*(\d{2}/\d{2}/\d{2,4})\s*-\s*"
        r"(\d{2}/\d{2}/\d{2,4})"
    ])
    inicio, fin = fecha_corta(inicio_txt), fecha_corta(fin_txt)
    dias = 0
    if inicio and fin:
        dias = (
            datetime.strptime(fin, "%d/%m/%Y")
            - datetime.strptime(inicio, "%d/%m/%Y")
        ).days + 1

    energia_por_periodo: dict[str, EnergiaPeriodo] = {}
    patron_energia = (
        r"^(?:Energ[ií]a|T[eé]rmino\s+(?:ATR|Cargos)\s+Energ[ií]a)\s+"
        r"(P[1-6])\s+\d{2}/\d{2}/\d{4}-\d{2}/\d{2}/\d{4}\s+"
        r"([\d.,]+)\s*kWh\s+([\d.,]+)\s*€/kWh\s+([\d.,]+)\s*€\s*$"
    )
    for periodo, consumo, precio, coste in re.findall(
        patron_energia, texto, re.IGNORECASE | re.MULTILINE
    ):
        periodo = periodo.upper()
        if periodo not in energia_por_periodo:
            energia_por_periodo[periodo] = EnergiaPeriodo(
                periodo, consumo_es(consumo), numero_es(precio), numero_es(coste)
            )
        else:
            item = energia_por_periodo[periodo]
            item.precio_eur_kwh += numero_es(precio)
            item.coste_eur += numero_es(coste)
        item = energia_por_periodo[periodo]
        item.coste_calculado_eur = round(
            item.consumo_kwh * item.precio_eur_kwh, 2
        )
    energia_periodos = [
        energia_por_periodo[p] for p in sorted(energia_por_periodo)
    ]

    potencia_agregada: dict[str, dict[str, float]] = {}
    patron_potencia = (
        r"^(?:Potencia\s+a\s+Facturar|T[eé]rmino\s+Cargos\s+Potencia)\s+"
        r"(P[1-6])\s+\d{2}/\d{2}/\d{4}-\d{2}/\d{2}/\d{4}\s+"
        r"([\d.,]+)\s*kW\s+([\d.,]+)\s*€/kW\s+([\d.,]+)\s*€\s*$"
    )
    for periodo, potencia, precio_ciclo, coste in re.findall(
        patron_potencia, texto, re.IGNORECASE | re.MULTILINE
    ):
        datos = potencia_agregada.setdefault(
            periodo.upper(),
            {"potencia": numero_es(potencia), "precio": 0.0, "coste": 0.0},
        )
        datos["precio"] += numero_es(precio_ciclo)
        datos["coste"] += numero_es(coste)
    potencia_periodos = [
        PotenciaFacturadaPeriodo(
            periodo=periodo,
            potencia_kw=datos["potencia"],
            dias=dias,
            precio_facturado_eur_kw_dia=(datos["precio"] / dias if dias else 0.0),
            coste_facturado_eur=round(datos["coste"], 2),
            coste_calculado_eur=round(datos["potencia"] * datos["precio"], 2),
        )
        for periodo, datos in sorted(potencia_agregada.items())
    ]

    otros = []
    for concepto, patrones in (
        ("Alquiler equipo de medida", [
            r"Alquiler\s+de\s+Equipo\s+de\s+Medida[^\n]*?([\d.,]+)\s*€"
        ]),
        ("Financiación bono social", [
            r"Importe\s+Bono\s+Social[^\n]*?([\d.,]+)\s*€\s*$"
        ]),
        ("Aportación FNEE", [
            r"Aportaci[oó]n\s+Fondo\s+de\s+Eficiencia[^\n]*?"
            r"([\d.,]+)\s*€\s*$"
        ]),
    ):
        importe = buscar_numero(texto, patrones)
        if importe:
            otros.append(OtroConcepto(concepto, importe))

    maximetros = [
        MaximetroPeriodo(periodo.upper(), numero_es(potencia_w) / 1000)
        for periodo, potencia_w in re.findall(
            r"Potencia\s+Maxima\s+(P[1-6])[^\n]*?([\d.,]+)\s*W\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        )
    ]
    sobrepasamientos = [
        SobrepasamientoPeriodo(periodo.upper(), numero_es(exceso_w) / 1000)
        for periodo, exceso_w in re.findall(
            r"Exceso\s+de\s+Potencia\s+(P[1-6])[^\n]*?([\d.,]+)\s*W\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        )
    ]

    return _completar_advertencias(FacturaLeida(
        formato="axpo",
        comercializadora="AXPO Iberia",
        numero_factura=buscar_texto(texto, [r"N[ºo]\s*Factura\s*:\s*([^\s]+)"]),
        cups=buscar_texto(texto, [r"CUPS\s*\n\s*(ES[A-Z0-9]+)"]),
        atr=extraer_atr(texto),
        fecha_factura=buscar_texto(texto, [
            r"Fecha\s+de\s+emisi[oó]n\s*:\s*(\d{2}/\d{2}/\d{4})"
        ]),
        periodo_inicio=inicio,
        periodo_fin=fin,
        potencia=round(sum(x.coste_facturado_eur for x in potencia_periodos), 2),
        energia=round(sum(x.coste_eur for x in energia_periodos), 2),
        excesos_potencia=buscar_numero(texto, [
            r"Excesos\s+de\s+Potencia[^\n]*?([\d.,]+)\s*€"
        ]),
        iee=buscar_numero(texto, [
            r"Impuesto\s+el[eé]ctrico\s+[\d.,]+\s*€\s+[\d.,]+\s*%\s+([\d.,]+)\s*€"
        ]),
        iva=buscar_numero(texto, [r"^IVA\s+\d+%\s+([\d.,]+)\s*€"]),
        total=buscar_numero(texto, [r"^TOTAL\s+([\d.,]+)\s*€"]),
        energia_periodos=energia_periodos,
        potencias_contratadas=extraer_potencias_contratadas(texto),
        potencia_periodos=potencia_periodos,
        maximetros=maximetros,
        sobrepasamientos=sobrepasamientos,
        otros=otros,
    ))


def _generico(texto: str) -> FacturaLeida:
    if "datos de la factura de gas" in texto.lower():
        raise FormatoNoReconocido(
            "Las facturas de gas están fuera del alcance actual del motor eléctrico."
        )
    cups = buscar_texto(texto, [
        r"CUPS\s*\.*\s*:\s*(ES[A-Z0-9]+)",
        r"C\.?\s*U\.?\s*P\.?\s*S\.?\s*:\s*(ES[A-Z0-9]+)",
        r"C\.?\s*U\.?\s*P\.?\s*S\.?\s*:[\s\S]{0,180}?(ES\d{16}[A-Z0-9]{2,4})",
        r"CUPS\).*?(ES(?:\s*[A-Z0-9]){18})",
    ])
    cups = re.sub(r"\s+", "", cups).upper() if cups else None
    total = buscar_numero(texto, [
        r"^IMPORTE\s+FACTURA\s*:\s*([\d.,]+)\s*€\s*$",
        r"^TOTAL\s+FACTURA\s*:?[ \t]+([\d.,]+)\s*€\s*$",
        r"^TOTAL\s+([\d.,]+)\s*€(?:\s+Periodo\b[^\n]*)?$",
        r"^TOTAL\s+([\d.,]+)\s*€\s*$",
        r"TOTAL\s+FACTURA\s*\.*\s*:\s*([\d.,]+)\s*€",
        r"TOTAL\s+FACTURA\s+([\d.,]+)\s*€",
        r"TOTAL\s+IMPORTE\s+FACTURA\s*:?\s*([\d.,]+)\s*€",
        r"Importe\s+Total\s+([\d.,]+)\s*€?",
        r"TOTAL\s+(?:A\s+PAGAR|A\s+ABONAR)\s*:?\s*([\d.,]+)\s*€",
    ])
    es_canaluz = "@canaluz.es" in texto.lower()
    es_on510 = "acenhol energia" in texto.lower()
    es_endesa = "horas open" in texto.lower() or "endesa energ" in texto.lower()
    es_eni_plenitude = "eni plenitude iberia" in texto.lower()
    es_nagini = "naginienergia.com" in texto.lower()
    es_niba = "niba negocios" in texto.lower()
    es_factorenergia = "factor energia,s.a." in texto.lower()
    es_ignis_loop = "clientes.ignisluz.es" in texto.lower()
    es_clara = "clara@claraenergia.com" in texto.lower()
    es_octopus = "hola@octopusenergy.es" in texto.lower()
    es_endesa_open_20 = es_endesa and bool(re.search(
        r"Potencias?\s+contratadas?\s*:\s*punta-llano", texto, re.IGNORECASE
    ))
    es_endesa_open_30 = es_endesa and bool(re.search(
        r"Pot\.\s*P6\s+[\d.,]+\s*kW", texto, re.IGNORECASE
    ))
    if (
        not cups
        and not es_canaluz
        and not es_on510
        and not es_eni_plenitude
        and not es_endesa
    ) or not total:
        raise FormatoNoReconocido(
            "Formato no reconocido y datos insuficientes para una extracción genérica."
        )

    atr = extraer_atr(texto)

    inicio, fin = buscar_periodo(texto, [
        r"Periodo\s*:\s*(\d{2}-\d{2}-\d{4})\s+a\s+"
        r"(\d{2}-\d{2}-\d{4})",
        r"Periodo\s+de\s+Consumo\s*:\s*Del\s+"
        r"(\d{2}/\d{2}/\d{4})\s+al\s+(\d{2}/\d{2}/\d{4})",
        r"Periodo\s+de\s+Consumo\s*:\s*De\s+"
        r"(\d{2}/\d{2}/\d{4})\s+al\s+(\d{2}/\d{2}/\d{4})",
        r"Periodo\s+consumo\s*:\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})",
        r"Del\s+(\d{1,2}\s+de\s+[^\s]+\s+de\s+\d{4})\s+al\s+"
        r"(\d{1,2}\s+de\s+[^\s]+\s+de\s+\d{4})",
        r"PERIODO\s*\.*\s*:\s*Del\s+(\d{2}/\d{2}/\d{4})\s+al\s+(\d{2}/\d{2}/\d{4})",
        r"Periodo\s+de\s+facturaci[oó]n\s*:?\s*(\d{2}/\d{2}/\d{4})\s*(?:-|a|al)\s*(\d{2}/\d{2}/\d{4})",
        r"Periodo\s+de\s+facturaci[oó]n\s*:?\s*del\s+(\d{2}/\d{2}/\d{4})\s+(?:a|al)\s+(\d{2}/\d{2}/\d{4})",
        r"Periodo\s+facturaci.n\s*:?\s*(\d{2}/\d{2}/\d{4})\s*(?:-|a|al)\s*(\d{2}/\d{2}/\d{4})",
        r"Per.odo\s+de\s+facturaci.n\s*:?\s*(\d{2}/\d{2}/\d{4})\s*(?:-|a|al)\s*(\d{2}/\d{2}/\d{4})",
        r"Periodo\s+factura\s*:\s*De\s+(\d{2}/\d{2}/\d{4})\s+al\s+(\d{2}/\d{2}/\d{4})",
        r"Periodo\s+de\s+consumo\s*:?\s*(\d{2}/\d{2}/\d{4})\s*(?:-|a|al)\s*(\d{2}/\d{2}/\d{4})",
        r"Periodo\s+de\s+facturaci[oó]n\s*:?\s*(\d{2}-\d{2}-\d{4})\s+(?:-|a|al)\s+(\d{2}-\d{2}-\d{4})",
        r"PERIODO\s+DE\s+FACTURACI.N[^\n]*\n(?:[^\n]*\n)?\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})",
        r"Periodo\s+de\s+Facturaci[oó]n\s*:\s*\n[^\n]*?Del\s+(\d{2}/\d{2}/\d{4})\s+al\s+(\d{2}/\d{2}/\d{4})",
        r"Periodo\s+consumo\s*:\s*De\s+"
        r"(\d{1,2}\s+de\s+[a-záéíóúüñ]+\s+de\s+\d{4})\s+hasta\s+"
        r"(\d{1,2}\s+de\s+[a-záéíóúüñ]+\s+de\s+\d{4})",
        r"PERIODO\s+DE\s+CONSUMO\s*:\s*Del\s+"
        r"(\d{1,2}\s+de\s+[a-záéíóúüñ]+\s+de\s+\d{4})\s+al\s+"
        r"(\d{1,2}\s+de\s+[a-záéíóúüñ]+\s+de\s+\d{4})",
    ])
    inicio = _fecha_es_a_ddmmyyyy(inicio.replace("-", "/")) if inicio else None
    fin = _fecha_es_a_ddmmyyyy(fin.replace("-", "/")) if fin else None
    potencias = extraer_potencias_contratadas(texto)
    if not potencias and es_endesa:
        coincidencia_potencias_endesa = re.search(
            r"Potencias?\s+contratadas?\s*:\s*punta-llano\s+([\d.,]+)\s*kW\s*;\s*"
            r"valle\s+([\d.,]+)\s*kW",
            texto,
            re.IGNORECASE,
        )
        if coincidencia_potencias_endesa:
            p1, p2 = coincidencia_potencias_endesa.groups()
            potencias = [
                PotenciaContratadaPeriodo("P1", numero_es(p1)),
                PotenciaContratadaPeriodo("P2", numero_es(p2)),
            ]
    energia_periodos = extraer_energia_gana(texto)
    if not energia_periodos and es_on510:
        energia_periodos = extraer_energia_on510(texto)
    if not energia_periodos:
        energia_periodos = extraer_energia_asteriscos(texto)
    if not energia_periodos and es_niba:
        coincidencia_energia_niba = re.search(
            r"^Energ[ií]a\s+Activa\s+([\d.,]+)\s*kWh\s+"
            r"([\d.,]+)\s*€/kWh\s+([\d.,]+)\s*€\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        )
        if coincidencia_energia_niba:
            consumo, precio, coste = coincidencia_energia_niba.groups()
            energia_periodos = [EnergiaPeriodo(
                "Total", consumo_es(consumo), numero_es(precio), numero_es(coste)
            )]
    if not energia_periodos and es_factorenergia:
        for periodo, consumo, precio in re.findall(
            r"^(P[1-6])\s+([\d.,]+)\s*x\s*([\d.,]+)\s*€/kWh\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        ):
            consumo_kwh = consumo_es(consumo)
            precio_kwh = numero_es(precio)
            coste = round(consumo_kwh * precio_kwh, 2)
            energia_periodos.append(EnergiaPeriodo(
                periodo.upper(), consumo_kwh, precio_kwh, coste, coste
            ))
    if es_ignis_loop:
        energia_ignis: dict[str, dict[str, float]] = {}
        for periodo, consumo, precio, coste in re.findall(
            r"(?:T[eé]rmino\s+Energ[ií]a[^\n]*?)?·\s*(P[1-6])\s+"
            r"([\d.,]+)\s*kWh\s*x\s*([\d.,]+)\s*€/kWh\s+"
            r"([\d.,]+)\s*€",
            texto,
            re.IGNORECASE,
        ):
            datos = energia_ignis.setdefault(
                periodo.upper(),
                {"consumo": consumo_es(consumo), "precio": 0.0, "coste": 0.0},
            )
            datos["precio"] += numero_es(precio)
            datos["coste"] += numero_es(coste)
        if energia_ignis:
            energia_periodos = []
            for periodo, datos in sorted(energia_ignis.items()):
                coste = round(datos["coste"], 2)
                energia_periodos.append(EnergiaPeriodo(
                    periodo,
                    datos["consumo"],
                    round(datos["precio"], 9),
                    coste,
                    coste,
                ))
    if es_octopus:
        energia_octopus: dict[str, dict[str, float]] = {}
        for nombre, consumo, precio, coste in re.findall(
            r"^(Punta|Llano|Valle)\s+([\d.,]+)\s*kWh\s+"
            r"([\d.,]+)\s*€/kWh\s+([\d.,]+)\s*€\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        ):
            periodo = {"punta": "P1", "llano": "P2", "valle": "P3"}[
                nombre.lower()
            ]
            datos = energia_octopus.setdefault(
                periodo, {"consumo": 0.0, "coste": 0.0}
            )
            datos["consumo"] += consumo_es(consumo)
            datos["coste"] += numero_es(coste)
        if energia_octopus:
            energia_periodos = []
            for periodo, datos in sorted(energia_octopus.items()):
                consumo = round(datos["consumo"], 3)
                coste = round(datos["coste"], 2)
                energia_periodos.append(EnergiaPeriodo(
                    periodo,
                    consumo,
                    coste / consumo if consumo else 0.0,
                    coste,
                    coste,
                ))
    if not energia_periodos:
        energia_periodos = extraer_energia_por_componentes(texto)
    if not energia_periodos:
        energia_periodos = extraer_periodos_energia(texto, [
        r"^(P[1-6])\s+([\d.,]+)\s*kWh\s+x\s+([\d.,]+)[^\d\n]+([-\d.,]+)\s*[^\d\n]*$",
        ])
    if not energia_periodos:
        energia_periodos = extraer_energia_matricial(texto)
    if not energia_periodos:
        energia_periodos = extraer_energia_horizontal_con_periodo(texto)
    if not energia_periodos:
        energia_periodos = extraer_energia_activa_vertical(texto)
    if not energia_periodos:
        energia_periodos = extraer_energia_desglosada_por_bloques(texto)
    if not energia_periodos:
        energia_periodos = extraer_energia_centimos_con_periodo(texto)
    if not energia_periodos:
        patron_energia_bloques = (
            r"^(?:Energ[ií]a\s+consumida\s+)?(Horas\s+(?:no\s+)?promocionadas)\s+"
            r"([\d.,]+)\s*kWh\s+x\s+([\d.,]+)\s*€/kWh\s+([\d.,]+)\s*€\s*$"
        )
        energia_periodos = [
            EnergiaPeriodo(nombre.title(), numero_es(consumo), numero_es(precio), numero_es(coste))
            for nombre, consumo, precio, coste in re.findall(
                patron_energia_bloques, texto, re.IGNORECASE | re.MULTILINE
            )
        ]
    if not energia_periodos and es_endesa:
        coincidencia_consumo_endesa = re.search(
            r"Facturaci[oó]n\s+del\s*Consumo\s+([\d.,]+)\s*kWh\s*x\s*"
            r"([\d.,]+)\s*Eur/kWh[^\n]*?([\d.,]+)\s*€",
            texto,
            re.IGNORECASE,
        )
        if coincidencia_consumo_endesa:
            consumo, precio, coste = coincidencia_consumo_endesa.groups()
            energia_periodos = [EnergiaPeriodo(
                "Total", consumo_es(consumo), numero_es(precio), numero_es(coste)
            )]
    if es_eni_plenitude:
        energia_periodos = extraer_energia_eni_plenitude(texto)
    potencia_periodos = extraer_potencia_gana(texto)
    if not potencia_periodos and es_on510:
        potencia_periodos = extraer_potencia_on510(texto)
    if not potencia_periodos:
        potencia_periodos = extraer_potencia_asteriscos(texto)
    if not potencia_periodos:
        potencia_periodos = extraer_potencia_con_prefijo(texto)
    if not potencia_periodos:
        potencia_periodos = extraer_periodos_potencia(texto)
    if not potencia_periodos:
        potencia_periodos = extraer_potencia_matricial(texto, inicio, fin)
    if not potencia_periodos:
        potencia_periodos = extraer_potencia_horizontal_con_periodo(
            texto, inicio, fin
        )
    if not potencia_periodos:
        potencia_periodos = extraer_potencia_anual_dos_lineas(texto)
    if not potencia_periodos:
        potencia_periodos = extraer_potencia_vertical_con_viñetas(texto)
    if not potencia_periodos:
        potencia_periodos = extraer_potencia_centimos_con_periodo(texto)
    if not potencia_periodos:
        for periodo, potencia_kw, precio, dias, coste in re.findall(
            r"^(P[1-6]):\s*([\d.,]+)\s*kW\s*\*\s*([\d.,]+)\s*"
            r"€/kW\s*\*\s*(\d+)\s*d[ií]as\s+([\d.,]+)\s*€\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        ):
            potencia_periodos.append(PotenciaFacturadaPeriodo(
                periodo=periodo.upper(),
                potencia_kw=numero_es(potencia_kw),
                dias=int(dias),
                precio_facturado_eur_kw_dia=numero_es(precio),
                coste_facturado_eur=numero_es(coste),
                coste_calculado_eur=round(
                    numero_es(potencia_kw) * int(dias) * numero_es(precio), 2
                ),
            ))
    if not potencia_periodos and es_niba:
        for nombre, potencia_kw, dias, precio, coste in re.findall(
            r"^Importe\s+potencia\s+(Punta|Valle)\s+([\d.,]+)\s*kW\s+-\s*"
            r"(\d+)\s*d[ií]as\s+([\d.,]+)\s*€/kW\s*d[ií]a\s+"
            r"([\d.,]+)\s*€\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        ):
            potencia_periodos.append(PotenciaFacturadaPeriodo(
                periodo="P1" if nombre.lower() == "punta" else "P2",
                potencia_kw=numero_es(potencia_kw),
                dias=int(dias),
                precio_facturado_eur_kw_dia=numero_es(precio),
                coste_facturado_eur=numero_es(coste),
                coste_calculado_eur=round(
                    numero_es(potencia_kw) * int(dias) * numero_es(precio), 2
                ),
            ))
    if not potencia_periodos and es_factorenergia:
        dias_periodo = _dias_facturados(FacturaLeida(
            formato="temporal",
            comercializadora="Factor Energía",
            periodo_inicio=inicio,
            periodo_fin=fin,
        ))
        for periodo, potencia_kw, precio_mes, meses in re.findall(
            r"^(P[1-6])\s+([\d.,]+)\s*x\s*([\d.,]+)\s*€/kW\s+mes\s+"
            r"x\s*([\d.,]+)\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        ):
            kw = numero_es(potencia_kw)
            precio = numero_es(precio_mes)
            meses_num = numero_es(meses)
            coste = round(kw * precio * meses_num, 2)
            potencia_periodos.append(PotenciaFacturadaPeriodo(
                periodo=periodo.upper(),
                potencia_kw=kw,
                dias=dias_periodo,
                precio_facturado_eur_kw_dia=(
                    coste / kw / dias_periodo if kw and dias_periodo else 0.0
                ),
                coste_facturado_eur=coste,
                coste_calculado_eur=coste,
                meses=meses_num,
                precio_facturado_eur_kw_mes=precio,
            ))
    if es_ignis_loop:
        potencia_ignis = []
        for periodo, potencia_kw, dias, precio, coste in re.findall(
            r"(?:T[eé]rmino\s+Potencia\s+)?·\s*(P[1-6])\s+"
            r"([\d.,]+)\s*kW\s*x\s*(\d+)\s*D[ií]as\s*x\s*"
            r"([\d.,]+)\s*€/kW\s*d[ií]a\s+([\d.,]+)\s*€",
            texto,
            re.IGNORECASE,
        ):
            kw = numero_es(potencia_kw)
            dias_num = int(dias)
            precio_dia = numero_es(precio)
            coste_num = numero_es(coste)
            potencia_ignis.append(PotenciaFacturadaPeriodo(
                periodo=periodo.upper(),
                potencia_kw=kw,
                dias=dias_num,
                precio_facturado_eur_kw_dia=precio_dia,
                coste_facturado_eur=coste_num,
                coste_calculado_eur=round(kw * dias_num * precio_dia, 2),
            ))
        if potencia_ignis:
            potencia_periodos = potencia_ignis
    if es_octopus:
        potencia_octopus = []
        for nombre, potencia_kw, dias, precio, coste in re.findall(
            r"^(Punta|Valle)\s+([\d.,]+)\s*kW\s*\*\s*(\d+)\s*d[ií]as\s+"
            r"([\d.,]+)\s*€/kW/d[ií]a\s+([\d.,]+)\s*€\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        ):
            potencia_octopus.append(PotenciaFacturadaPeriodo(
                periodo="P1" if nombre.lower() == "punta" else "P2",
                potencia_kw=numero_es(potencia_kw),
                dias=int(dias),
                precio_facturado_eur_kw_dia=numero_es(precio),
                coste_facturado_eur=numero_es(coste),
                coste_calculado_eur=numero_es(coste),
            ))
        if potencia_octopus:
            potencia_periodos = potencia_octopus
    if not potencia_periodos and es_endesa:
        # Tempo Open 20 y Tempo Open 30 comparten marca, pero publican el
        # término de potencia con distinto orden de días y precio.
        patrones_endesa = (
            r"Pot\.\s*(P[1-6])\s*([\d.,]+)\s*kW\s*x\s*([\d.,]+)\s*"
            r"Eur/kW\s*x\s*(\d+)\s*d[ií]as[^\n]*?([\d.,]+)\s*€",
            r"Pot\.\s*(P[1-6])\s*([\d.,]+)\s*kW\s*x\s*(\d+)\s*d[ií]as\s*x\s*"
            r"([\d.,]+)\s*Eur/kW\s*y\s*d[ií]a[^\n]*?([\d.,]+)\s*€",
        )
        for indice, patron in enumerate(patrones_endesa):
            for periodo, potencia_kw, valor_3, valor_4, coste in re.findall(
                patron, texto, re.IGNORECASE
            ):
                precio, dias = (
                    (numero_es(valor_3), int(valor_4))
                    if indice == 0
                    else (numero_es(valor_4), int(valor_3))
                )
                potencia_periodos.append(PotenciaFacturadaPeriodo(
                    periodo=periodo.upper(),
                    potencia_kw=numero_es(potencia_kw),
                    dias=dias,
                    precio_facturado_eur_kw_dia=precio,
                    coste_facturado_eur=numero_es(coste),
                    coste_calculado_eur=round(
                        numero_es(potencia_kw) * dias * precio, 2
                    ),
                ))
        if not potencia_periodos:
            for nombre, potencia_kw, precio, dias, coste in re.findall(
                r"^Pot\.\s+(Punta-Llano|Valle)\s+([\d.,]+)\s*kW\s+x\s*"
                r"([\d.,]+)\s*Eur/kW\s+x\s*(\d+)\s*d[ií]as[^\n]*?"
                r"([\d.,]+)\s*€",
                texto,
                re.IGNORECASE | re.MULTILINE,
            ):
                kw = numero_es(potencia_kw)
                precio_dia = numero_es(precio)
                dias_num = int(dias)
                potencia_periodos.append(PotenciaFacturadaPeriodo(
                    periodo="P1" if nombre.lower() == "punta-llano" else "P2",
                    potencia_kw=kw,
                    dias=dias_num,
                    precio_facturado_eur_kw_dia=precio_dia,
                    coste_facturado_eur=numero_es(coste),
                    coste_calculado_eur=round(kw * dias_num * precio_dia, 2),
                ))
    # Algunas facturas 2.0TD denominan P3 al segundo periodo de potencia.
    if atr and atr.startswith("2.0"):
        periodos_potencia = {item.periodo for item in potencia_periodos}
        if "P3" in periodos_potencia and "P2" not in periodos_potencia:
            for item in potencia_periodos:
                if item.periodo == "P3":
                    item.periodo = "P2"
        periodos_contratados = {item.periodo for item in potencias}
        if "P3" in periodos_contratados and "P2" not in periodos_contratados:
            for item in potencias:
                if item.periodo == "P3":
                    item.periodo = "P2"
    if not potencias and potencia_periodos:
        potencias = [
            PotenciaContratadaPeriodo(item.periodo, item.potencia_kw)
            for item in potencia_periodos
        ]
    potencia = round(sum(item.coste_facturado_eur for item in potencia_periodos), 2) or sumar_coincidencias(
        texto,
        r"^P[1-6]\s+[\d.,]+\s*KW\s+x\s+\d+\s+d.as\s+x\s+[\d.,]+[^\d\n]+([-\d.,]+)\s*[^\d\n]*$",
    )
    if es_canaluz:
        potencia = buscar_numero(texto, [
            r"Facturaci[oó]n\s+por\s+potencia[^\n]*?:\s*([\d.,]+)\s*€",
        ]) or potencia
    if es_on510 and not potencia:
        potencia = buscar_numero(texto, [
            r"T[eé]rmino\s+de\s+Potencia\s+Contratada\s+([\d.,]+)\s*€",
        ])
    if es_endesa and not potencia:
        potencia = buscar_numero(texto, [r"^Potencia\s+([\d.,]+)\s*€"])
    energia = round(sum(item.coste_eur for item in energia_periodos), 2)
    descuento_energia = buscar_numero(texto, [
        # La leyenda del RDL 6/2022 cuantifica un ahorro regulatorio, pero no
        # es una partida facturada ni debe restarse de la energía.
        r"Descuentos?(?!\s+asociado\s+al\s+ahorro\s+de\s+cargos)[^\n]*?"
        r"(-[\d.,]+)\s*€\s*$",
    ])
    energia = round(energia + descuento_energia, 2)
    if es_canaluz:
        energia = buscar_numero(texto, [
            r"Facturaci[oó]n\s+por\s+energ[ií]a\s+consumida[^\n]*?:\s*([\d.,]+)\s*€",
        ]) or energia
    if es_on510 and not energia:
        energia = buscar_numero(texto, [
            r"T[eé]rmino\s+de\s+Energ[ií]a\s+Activa\s+([\d.,]+)\s*€",
        ])
    if es_endesa:
        energia_bruta = buscar_numero(texto, [
            r"^Energ[ií]a\s+consumida\s+de\s+la\s+red\s+([\d.,]+)\s*€",
            r"^Energ[ií]a\s+([\d.,]+)\s*€",
        ]) or round(sum(item.coste_eur for item in energia_periodos), 2)
        energia = round(energia_bruta + descuento_energia, 2)
    if es_eni_plenitude:
        energia = round(sum(item.coste_eur for item in energia_periodos), 2)
    if descuento_energia:
        energia_periodos.append(EnergiaPeriodo(
            "Descuento sobre consumo",
            0.0,
            0.0,
            descuento_energia,
            coste_calculado_eur=descuento_energia,
        ))
    excesos = sumar_coincidencias(
        texto,
        r"^P[1-6]\s+[\d.,]+\s+x\s+\d+\s+d.as\s+x\s+[\d.,]+[^\d\n]+([-\d.,]+)\s*[^\d\n]*$",
    )
    if not excesos:
        excesos = buscar_numero(texto, [
            r"Excesos\s+(?:de\s+)?Potencia\s+([-\d.,]+)\s*€?\s*$",
            r"T[eé]rmino\s+Excesos\s+Distribuidora[^\n]*?([-\d.,]+)\s*€\s*$",
        ])
    if not excesos:
        excesos = extraer_total_excesos_horizontal(texto)
    excesos_detallados, maximetros_excesos, total_excesos_detallados = (
        extraer_excesos_detallados_maximetro(texto, potencias)
    )
    if not excesos:
        excesos = total_excesos_detallados
    otros = _otros_comunes(texto) + _extraer_abonos(texto)
    if es_endesa and not otros:
        for concepto, patron in (
            ("Regularización FNEE", r"^Regularizaci[oó]n\s+Fondo\s+Nacional\s+Eficiencia\s+Energ[ií]a[^\n]*?([\d.,]+)\s*€"),
            ("Financiación bono social", r"^Financiaci[oó]n\s+Bono\s+Social[^\n]*?([\d.,]+)\s*€"),
            ("Alquiler equipo de medida", r"^Alquiler\s+del\s+contador[^\n]*?([\d.,]+)\s*€"),
        ):
            importe = buscar_numero(texto, [patron])
            if importe:
                otros.append(OtroConcepto(concepto, importe))
    if es_clara:
        for periodo, importe in re.findall(
            r"^(P[1-6])\s+[\d.,]+\s*kWh\s+x\s*[\d.,]+\s*€/kWh\s+"
            r"(-[\d.,]+)\s*€\s*$",
            _seccion(texto, r"Autoconsumo\s+Variable", r"Impuesto\s+Electricidad"),
            re.IGNORECASE | re.MULTILINE,
        ):
            otros.append(OtroConcepto(
                f"Compensación autoconsumo {periodo.upper()}",
                -abs(numero_es(importe)),
            ))
    if es_niba and not any("alquiler" in item.concepto.lower() for item in otros):
        alquiler_niba = buscar_numero(texto, [
            r"^Alquiler\s+Aparato\s+Medida[^\n]*?([\d.,]+)\s*€\s*$",
        ])
        if alquiler_niba:
            otros.append(OtroConcepto("Alquiler equipo de medida", alquiler_niba))
    if es_nagini:
        otros = []
        for concepto, patron in (
            (
                "Devolución depósito de garantía",
                r"^Devoluci[oó]n\s+dep[oó]sito\s+de\s+garant[ií]a\s+"
                r"(-[\d.,]+)\s*€\s*$",
            ),
            (
                "Servicios de ajuste (SSAA/REE)",
                r"^Ajuste\s+Sistema\s+El[eé]ctrico\s*\(REE\)[^\n]*?"
                r"([\d.,]+)\s*€\s*$",
            ),
            (
                "Financiación bono social 2026",
                r"^Financiaci[oó]n\s+Bono\s+Social\s+2026\s+"
                r"([\d.,]+)\s*€\s*$",
            ),
            (
                "Regularización bono social 2026",
                r"^Bono\s+social\s+2026\s+Orden\s+TED/634/2026\s+"
                r"([\d.,]+)\s*€\s*$",
            ),
        ):
            importe = buscar_numero(texto, [patron])
            if importe:
                otros.append(OtroConcepto(concepto, importe))
    if es_eni_plenitude:
        coste_financiero = buscar_numero(texto, [
            r"Coste\s+Financiero[^\n]*?([\d.,]+)\s*€\s*$"
        ])
        if coste_financiero:
            otros.append(OtroConcepto("Coste financiero", coste_financiero))
    for concepto, patron in (
        ("Bono social", r"Bono\s+Social[^\n]*?([-\d.,]+)\s*€?\s*$"),
        ("Alquiler equipo de medida", r"alquiler\s+equipo\s+de\s+medida[^\n]*?([-\d.,]+)\s*€?\s*$"),
        ("Conceptos extra", r"^Conceptos\s+extra\s+([-\d.,]+)\s*€\s*$"),
        ("Regularización RRTT Sistema", r"^Reg\.\s*RRTT\s+Sistema[^\n]*?([-\d.,]+)\s*€\s*$"),
        ("Financiación bono social", r"^B\.\s*Social[^\n]*?([-\d.,]+)\s*€\s*$"),
    ):
        importe = buscar_numero(texto, [patron])
        concepto_clave = concepto.lower()
        ya_extraido = any(
            concepto_clave in item.concepto.lower()
            or item.concepto.lower() in concepto_clave
            for item in otros
        )
        if importe and not ya_extraido:
            otros.append(OtroConcepto(concepto, importe))
    fecha_factura_txt = buscar_texto(texto, [
        r"Fecha\s+Factura\s*:?[ \t]+(\d{2}/\d{2}/\d{4})",
        r"Emitida\s*:\s*(\d{2}/\d{2}/\d{4})",
        r"ATENCO\s+ENERGIA[^\n]*?FAT-\d{4}-\d+\s+"
        r"(\d{1,2}\s+de\s+[^\s]+\s+de\s+\d{4})",
        r"FECHA\s+DE\s+EMISI[ÓO]N\s+DE\s+FACTURA\s*:\s*"
        r"(\d{1,2}\s+de\s+[^\s]+\s+de\s+\d{4})",
        r"Fecha\s+de\s+emisi.n\s*:\s*"
        r"(\d{1,2}\s+de\s+[^\s]+\s+de\s+\d{4})",
        r"Fecha\s+de\s+emisi[oó]n\s*:\s*(\d{2}-\d{2}-\d{2,4})",
        r"FECHA\s+FACTURA\s*\.*\s*:\s*(\d{1,2}\s+de\s+[a-záéíóúüñ]+\s+de\s+\d{4})",
        r"FECHA\s+FACTURA\s*\.*\s*:\s*(\d{2}/\d{2}/\d{4})",
        r"Fecha\s+de\s+Factura\s*:\s*(\d{2}/\d{2}/\d{4})",
        r"Fecha\s+factura\s*:?\s*(\d{2}-\d{2}-\d{4})",
        r"Fecha\s+emisi[oó]n\s*:?\s*(\d{2}/\d{2}/\d{4})",
        r"Fecha\s+emisi[oó]n\s+factura\s*:?\s*(\d{2}/\d{2}/\d{4})",
        r"Fecha\s+emisi[oó]n\s+factura\s*:?\s*"
        r"(\d{1,2}\s+de\s+[^\s]+\s+de\s+\d{4})",
        r"FECHA\s+DE\s+EMISI.N[^\n]*\n[^\n]*?(\d{1,2}\s+de\s+[a-záéíóúüñ]+\s+de\s+\d{4})",
        r"Fecha\s+de\s+emisi[oó]n\s*:\s*"
        r"(\d{1,2}\s+de\s+[a-záéíóúüñ]+\s+de\s+\d{4})",
    ])
    iva = buscar_numero(texto, [
        r"^IVA\s+normal\s+[\d.,]+\s*%\s+s/\s*[\d.,]+[^\n]*?"
        r"([\d.,]+)\s*€",
        r"^IVA\s*\(GENERAL\)\s+[\d.,]+\s*€\s+[\d.,]+\s*%\s+"
        r"([\d.,]+)\s*€\s*$",
        r"IVA\s*normal\s*\([^\n]*?\)[^\n]*?s/\s*[\d.,]+[^\n]*?([\d.,]+)\s*€\s*$",
        r"Base\s+Imponible\s+%\s+I\.?V\.?A\.?\s+Impuestos\s+TOTAL\s+FACTURA\s+"
        r"[\d.,]+\s*€\s+[\d.,]+\s*%\s+([\d.,]+)\s*€",
        r"\bI\.?V\.?A\.?\s+\d+(?:[.,]\d+)?\s*%[^\n]*?([\d.,]+)\s*€\s*$",
        r"\bIVA\s*\(\d+(?:[.,]\d+)?%\)\s+([\d.,]+)\s*€?\s*$",
        r"^Base\s+Imponible\s+\d+\s+[\d.,]+\s+\d+(?:[.,]\d+)?\s+([\d.,]+)\s+[\d.,]+\s*$",
        r"^Base\s+Imponible\s+[\d.,]+\s*€\s+\d+(?:[.,]\d+)?%[^\n]*?([\d.,]+)\s*€\s*$",
        r"^[\d.,]+\s*€\s+\d+(?:[.,]\d+)?\s*%\s+I\.?V\.?A\.?\s+([\d.,]+)\s*€\s*$",
        r"^Impuesto\s+IVA\s+[\d.,]+\s*%[^\n]*?\(([\d.,]+)\s*€\)\s*$",
        r"^Impuesto\s+IVA\s*\(\s*[\d.,]+\s*%\s*\)\s+"
        r"([\d.,]+)\s*€\s*$",
        r"IVA\s*:\s*\(\s*[\d.,]+\s*%\s+s/\s*[\d.,]+\s*€\s*\)\s*"
        r"([\d.,]+)\s*€",
        r"IVA\s*normal\s+[\d.,]+\s*%\s+s/[\d.,]+[^\n]*?([\d.,]+)\s*€",
        r"^Impuesto\s+de\s+aplicaci[oó]n\s*:\s*([\d.,]+)\s*€\s*$",
    ])
    iee = buscar_numero(texto, [
        r"^Impuesto\s+El[eé]ctrico\s+[\d.,]+\s*€\s+[\d.,]+\s*%\s+"
        r"([\d.,]+)\s*€\s*$",
        r"^Impuesto\s+Electricidad\s*\n\s*[\d.,]+\s*%\s+sobre\s+"
        r"[\d.,]+\s*€\s+x\s*1\s+([\d.,]+)\s*€\s*$",
        r"^Importe\s+IEE\s+(?:[\d.,]+\s*%[^\n]*?=\s*)?"
        r"([\d.,]+)\s*€\s*$",
        r"^Impuesto\s+el[eé]ctrico\s*:\s*([\d.,]+)\s*€",
        r"Impuestos?\s+el[eé]ctricos?\s*\n\s*[\d.,]+\s*€\s*x\s*"
        r"[\d.,]+\s+([\d.,]+)\s*€",
        r"Impuesto\s+Electricidad[^\n]*?%[^\n]*?([\d.,]+)\s*€\s*$",
        r"Impuesto\s+electricidad\s*\([^\n]*?%\)[^\n]*?([\d.,]+)\s*€\s*$",
        r"I\.?E\.?\s+[\d.,]+\s*%\s+sobre\s+[\d.,]+[^\n]*\s([\d.,]+)\s*€\s*$",
        r"Impuesto\s+(?:sobre\s+)?(?:la\s+)?electricidad[^\n]*?([\d.,]+)\s*€\s*$",
        r"Impuesto\s+de\s+electricidad[^\n]*?([\d.,]+)\s*€\s*$",
        r"Impuesto\s+Electricidad[^\n]*?([\d.,]+)\s*€\s*$",
        r"Impuesto\s+El.ctrico[^\n]*?([\d.,]+)\s*€?\s*$",
        r"Impuesto\s+Electricidad[^\n]*?([\d.,]+)\s*€?\s*$",
        r"^Impuesto\s+de\s+electricidad\s*:\s*([\d.,]+)\s*€\s*$",
    ])
    comercializadora = buscar_texto(texto, [
        r"^(IBERDROLA\s+CLIENTES)",
        r"\b([A-ZÁÉÍÓÚ][A-ZÁÉÍÓÚ ]+ENERG[IÍ]A)\s+-",
        r"^(Acciona\s+Green\s+Energy\s+Developments)",
        r"^(UniEl[eé]ctrica\s+Energ[ií]a)",
        r"clientes@(ignis)luz\.es",
    ])
    if not comercializadora:
        dominio = buscar_texto(texto, [
            r"@([a-z0-9-]+?)-?energia\.com",
        ])
        comercializadora = f"{dominio.replace('-', ' ').title()} Energía" if dominio else None
    if comercializadora and comercializadora.lower() == "ignis":
        comercializadora = "Ignis Luz"
    comercializadora = comercializadora or "Comercializadora no identificada"
    if es_canaluz:
        comercializadora = "Canaluz"
    elif es_on510:
        comercializadora = "ON510 / Acenhol Energía"
    elif es_endesa:
        comercializadora = "Endesa"
    elif es_eni_plenitude:
        comercializadora = "Eni Plenitude"
    maximetros = (
        extraer_maximetros_etiquetados(texto)
        or extraer_medidas_verticales(texto, r"Potencia\s+M[aá]xima")
        or extraer_maximetros_canaluz(texto)
        or extraer_maximetros_demanda_parcial(texto, energia_periodos)
        or extraer_maximetros_matriciales(texto)
        or maximetros_excesos
        or _maximetros_desde_excesos(texto, potencias)
    )
    if es_nagini:
        maximetros = [
            MaximetroPeriodo(periodo.upper(), numero_es(valor))
            for periodo, valor in re.findall(
                r"^(P[1-6])\s+(?:[\d.,]+\s+){8}([\d.,]+)\s*$",
                _seccion(texto, r"DATOS\s+DE\s+CONSUMO", r"DATOS\s+DEL\s+PAGO"),
                re.IGNORECASE | re.MULTILINE,
            )
        ]
    if es_on510:
        # Esta plantilla publica lecturas por periodo, no maxímetros.
        maximetros = []
    if es_eni_plenitude:
        maximetros = extraer_maximetros_eni_plenitude(texto)
    if atr and atr.startswith("2.0"):
        max_por_periodo = {item.periodo: item for item in maximetros}
        if "P3" in max_por_periodo and "P2" in max_por_periodo:
            maximetros = [
                MaximetroPeriodo("P1", max_por_periodo["P1"].potencia_kw),
                MaximetroPeriodo("P2", max_por_periodo["P3"].potencia_kw),
            ]
    sobrepasamientos = extraer_sobrepasamientos_matriciales(texto)
    if not sobrepasamientos:
        sobrepasamientos = excesos_detallados
    if not sobrepasamientos:
        medidas_exceso = extraer_medidas_verticales(
            texto, r"Excesos\s+de\s+Potencia"
        )
        sobrepasamientos = [
            SobrepasamientoPeriodo(item.periodo, item.potencia_kw)
            for item in medidas_exceso
        ]

    reactiva_periodos = extraer_reactiva_matricial(texto)
    if not reactiva_periodos:
        reactiva_periodos = extraer_reactiva_canaluz(texto, energia_periodos)
    factura = FacturaLeida(
        formato="generico",
        comercializadora=comercializadora.title(),
        numero_factura=buscar_texto(texto, [
            r"N[uú]mero\s+de\s+factura\s*:\s*([^\s]+)",
            r"N[º°o]?\s*de\s*factura\s*:\s*([A-Z]\d+[A-Z]+\d+)",
            r"N[º°o]?\s*factura\s*:\s*([A-Z]\d+[A-Z]+\d+)",
            r"N[º°o]?\s*Factura\s*:\s*([A-Z]+/\d{2}/\d+)",
            r"ATENCO\s+ENERGIA[^\n]*?\s(FAT-\d{4}-\d+)",
            r"N[º°o]?\s*FACTURA\s*:\s*([A-Z]+-\d{4}-\d+)",
            r"N[º°o]?\s*Factura\s*:\s*([^\n]+)",
            r"N[º°o]?\s*de\s*Factura\s*:\s*([^\n]+)",
            r"N[º°o]?\s*Factura\s*:\s*(IGNIS\s+\d+)",
            r"PERIODO\s+DE\s+FACTURACI.N:\s+N[º°o]?\s+FACTURA:\s*\n"
            r"(?:[^\n]*\n)?\s*\d{2}/\d{2}/\d{4}\s*-\s*\d{2}/\d{2}/\d{4}\s+(\d+)",
            r"N[º°o]?\s*FACTURA\s*\.*\s*:\s*([^\s]+)",
            r"N[º°o]?\s*factura\s+([^\s]+)",
        ]),
        cups=cups,
        atr=atr,
        fecha_factura=_fecha_es_a_ddmmyyyy(
            fecha_factura_txt.replace("-", "/") if fecha_factura_txt else None
        ),
        periodo_inicio=inicio,
        periodo_fin=fin,
        potencia=potencia,
        energia=energia,
        excesos_potencia=excesos,
        reactiva=(
            round(sum(item.coste_facturado_eur for item in reactiva_periodos), 2)
            or buscar_numero(texto, [
                r"(?:TOTAL\s+)?REACTIVA[^\n]*?([-\d.,]+)\s*€\s*$",
                r"Facturaci[oó]n\s+por\s+energ[ií]a\s+reactiva\s*:\s*([\d.,]+)\s*€",
            ])
        ),
        iee=iee,
        iva=iva,
        total=total,
        energia_periodos=energia_periodos,
        potencias_contratadas=potencias,
        potencia_periodos=potencia_periodos,
        maximetros=maximetros,
        sobrepasamientos=sobrepasamientos,
        reactiva_periodos=reactiva_periodos,
        otros=otros,
    )
    return _completar_advertencias(factura)


def _totalenergies(texto: str) -> FacturaLeida:
    """Extrae el formato detallado de TotalEnergies España."""
    inicio, fin = buscar_periodo(texto, [
        r"Periodo\s+de\s+consumo\s+De\s+(\d{2}/\d{2}/\d{4})\s+al\s+"
        r"(\d{2}/\d{2}/\d{4})",
    ])
    potencia_periodos = extraer_potencia_totalenergies(texto)
    energia_periodos = extraer_energia_totalenergies(texto)
    potencias = extraer_potencias_contratadas(texto)
    alquiler = buscar_numero(texto, [
        r"^Alquiler\s+Equipo\s+Distribuidora\s+([\d.,]+)\s*€\s*$",
    ])
    cargos = buscar_numero(texto, [r"^Cargos\s+([\d.,]+)\s*€\s*$"])
    otros = []
    if cargos:
        otros.append(OtroConcepto("Cargos regulados", cargos))
    if alquiler:
        otros.append(OtroConcepto("Alquiler equipo de medida", alquiler))

    maximetros = [
        MaximetroPeriodo(f"P{periodo}", numero_es(valor))
        for periodo, valor in re.findall(
            r"\bP([1-6])\s*:\s*([\d.,]+)",
            _seccion(
                texto,
                r"Potencias\s+m[aá]ximas\s+demandadas",
                r"Informaci[oó]n\s+de\s+consumo\s+el[eé]ctrico",
            ),
            re.IGNORECASE,
        )
    ]
    fecha_txt = buscar_texto(texto, [
        r"Fecha\s+emisi[oó]n\s+factura\s*:\s*"
        r"(\d{1,2}\s+de\s+[a-záéíóúüñ]+\s+de\s+\d{4})",
    ])
    cups = buscar_texto(texto, [
        r"punto\s+de\s+suministro\s*\(CUPS\)\s*:\s*(ES[A-Z0-9]+)",
    ])
    numero_factura = buscar_texto(texto, [r"N[º°o]\s*Factura\s+([^\n]+)"])
    if numero_factura and numero_factura.strip().upper() == "NUMERO FACTURA":
        numero_factura = None
    factura = FacturaLeida(
        formato="totalenergies",
        comercializadora="TotalEnergies",
        numero_factura=numero_factura,
        cups=cups,
        atr=extraer_atr(texto),
        fecha_factura=_fecha_es_a_ddmmyyyy(fecha_txt),
        periodo_inicio=inicio,
        periodo_fin=fin,
        potencia=round(sum(item.coste_facturado_eur for item in potencia_periodos), 2),
        energia=round(sum(item.coste_eur for item in energia_periodos), 2),
        iee=buscar_numero(texto, [
            r"^M[ií]nimoIE\s+[\d.,]+\s*kWh\s+x\s+[\d.,]+\s*€/kWh\s+"
            r"([\d.,]+)\s*€\s*$",
        ]),
        iva=buscar_numero(texto, [
            r"^Impuesto\s+IVA\s+[\d.,]+\s*%\s+sobre\s+[\d.,]+\s*€\s+"
            r"([\d.,]+)\s*€\s*$",
        ]),
        total=buscar_numero(texto, [
            r"^TOTAL\s+IMPORTE\s+FACTURA\s+([\d.,]+)\s*€\s*$",
            r"^Total\s+importe\s+factura\s*:\s*([\d.,]+)\s*€\s*$",
        ]),
        energia_periodos=energia_periodos,
        potencias_contratadas=potencias,
        potencia_periodos=potencia_periodos,
        maximetros=maximetros,
        otros=otros,
    )
    return _completar_advertencias(factura)


def _iberdrola_tramos(texto: str) -> FacturaLeida:
    """Extrae Iberdrola cuando potencia y energía se dividen en tramos."""
    cups = buscar_texto(texto, [
        r"Identificaci[oó]n\s+punto\s+de\s+suministro\s*\(CUPS\)\s*:\s*"
        r"((?:[A-Z0-9]\s*){20})",
    ])
    cups = re.sub(r"\s+", "", cups).upper() if cups else None
    total = buscar_numero(texto, [
        r"^TOTAL\s+IMPORTE\s+FACTURA\s+([\d.,]+)\s*€\s*$",
    ])
    if not cups or not total:
        raise FormatoNoReconocido(
            "Factura Iberdrola por tramos reconocida, pero faltan CUPS o total."
        )

    inicio, fin = buscar_periodo(texto, [
        r"PERIODO\s+DE\s+FACTURACI[ÓO]N:\s+N[º°]?\s+FACTURA:\s*\n"
        r"[^\n]*\n\s*(\d{2}/\d{2}/\d{4})\s*-\s*"
        r"(\d{2}/\d{2}/\d{4})",
    ])
    if not inicio:
        inicio, fin = buscar_periodo(texto, [
            r"(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})\s+\d+",
        ])

    potencia_periodos = []
    patron_potencia = (
        r"^(?:Potencia\s+facturada(?:\s*\([^\n]*?\))?\s+)?(Punta|Valle)\s+"
        r"([\d.,]+)\s*kW\s*x\s*(\d+)\s*d[ií]as?\s*x\s*"
        r"([\d.,]+)\s*€/kW\s*d[ií]a\s+([\d.,]+)\s*€\s*$"
    )
    for nombre_periodo, potencia_kw, dias_tramo, precio, coste in re.findall(
        patron_potencia, texto, re.IGNORECASE | re.MULTILINE
    ):
        potencia_periodos.append(PotenciaFacturadaPeriodo(
            "P1" if nombre_periodo.lower() == "punta" else "P2",
            numero_es(potencia_kw), int(dias_tramo), numero_es(precio),
            numero_es(coste),
        ))

    potencia_punta = buscar_numero(texto, [
        r"Potencia\s+punta\s*:\s*([\d.,]+)\s*kW",
    ])
    potencia_valle = buscar_numero(texto, [
        r"Potencia\s+valle\s*:\s*([\d.,]+)\s*kW",
    ])
    potencias = [
        PotenciaContratadaPeriodo("P1", potencia_punta),
        PotenciaContratadaPeriodo("P2", potencia_valle),
    ]

    energia_periodos = [
        EnergiaPeriodo(
            f"Tramo {indice}", consumo_es(consumo), numero_es(precio),
            numero_es(coste),
        )
        for indice, (consumo, precio, coste) in enumerate(re.findall(
            r"^Energ[ií]a\s+consumida(?:\s*\([^\n]*?\))?\s+"
            r"([\d.,]+)\s*k\w{1,2}h\s+x\s*"
            r"([\d.,]+)\s*€/kWh\s+([\d.,]+)\s*€\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        ), start=1)
    ]
    descuento = buscar_numero(texto, [
        r"^Descuento\s+sobre\s+consumo[^\n]*?\s(-[\d.,]+)\s*€\s*$",
    ])
    if descuento:
        energia_periodos.append(EnergiaPeriodo(
            "Descuento sobre consumo", 0.0, 0.0, descuento,
            coste_calculado_eur=descuento,
        ))

    regularizacion_fnee = buscar_numero(texto, [
        r"^Regularizaci[oó]n\s+FNEE[^\n]*?([\d.,]+)\s*€\s*$",
    ])

    otros = [
        OtroConcepto(
            f"Financiación bono social · tramo {indice}", numero_es(importe)
        )
        for indice, importe in enumerate(re.findall(
            r"^Financiaci[oó]n\s+bono\s+social\s+fijo[^\n]*?"
            r"([\d.,]+)\s*€\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        ), start=1)
    ]
    alquiler = buscar_numero(texto, [
        r"^Alquiler\s+equipos?\s+medida[^\n]*?([\d.,]+)\s*€\s*$",
    ])
    if alquiler:
        otros.append(OtroConcepto("Alquiler equipo de medida", alquiler))
    if regularizacion_fnee:
        otros.append(OtroConcepto("Actualización FNEE", regularizacion_fnee))

    maximetros = []
    maximos = re.search(
        r"lecturas\s+de\s+su\s+max[ií]metro\s+son:\s*punta:\s*"
        r"([\d.,]+);\s*valle:\s*([\d.,]+)",
        texto,
        re.IGNORECASE,
    )
    if maximos:
        maximetros = [
            MaximetroPeriodo("P1", numero_es(maximos.group(1))),
            MaximetroPeriodo("P2", numero_es(maximos.group(2))),
        ]

    fecha_txt = buscar_texto(texto, [
        r"FECHA\s+DE\s+EMISI[ÓO]N:[^\n]*\n\s*"
        r"(\d{1,2}\s+de\s+[a-záéíóúüñ]+\s+de\s+\d{4})",
        r"DIAS\s+FACTURADOS:\s+FECHA\s+DE\s+EMISI[ÓO]N:[^\n]*\n\s*"
        r"\d+\s+(\d{1,2}\s+de\s+[a-záéíóúüñ]+\s+de\s+\d{4})",
    ])
    factura = FacturaLeida(
        formato="iberdrola_tramos",
        comercializadora="Iberdrola Clientes",
        numero_factura=buscar_texto(texto, [
            r"\d{2}/\d{2}/\d{4}\s*-\s*\d{2}/\d{2}/\d{4}\s+([A-Z0-9]+)",
        ]),
        cups=cups,
        atr=extraer_atr(texto),
        fecha_factura=_fecha_es_a_ddmmyyyy(fecha_txt),
        periodo_inicio=inicio,
        periodo_fin=fin,
        potencia=round(sum(
            item.coste_facturado_eur for item in potencia_periodos
        ), 2),
        energia=round(sum(item.coste_eur for item in energia_periodos), 2),
        iee=buscar_numero(texto, [
            r"^Impuesto\s+sobre\s+electricidad[^\n]*?([\d.,]+)\s*€\s*$",
        ]),
        iva=buscar_numero(texto, [
            r"^IVA(?:\s+Reducido)?(?:\s*\([^\n]*?\))?\s+[\d.,]+\s*%\s+"
            r"s/[\d.,]+\s*€\s+([\d.,]+)\s*€\s*$",
        ]),
        total=total,
        energia_periodos=energia_periodos,
        potencias_contratadas=potencias,
        potencia_periodos=potencia_periodos,
        maximetros=maximetros,
        otros=otros,
    )
    return _completar_advertencias(factura)


def _naturgy_grandes_clientes(texto: str) -> FacturaLeida:
    """Extrae Naturgy Clientes Empresas / Grandes Clientes."""
    cups = buscar_texto(texto, [
        r"FECHA\s+VENCIMIENTO\s+CUPS[^\n]*\n[^\n]*?\s(ES[A-Z0-9]+)\s+Tarifa",
        r"C[oó]digo\s+CUPS\s+CONTRATO\s+ATR\s*\n\s*(ES[A-Z0-9]+)",
    ])
    total = buscar_numero(texto, [
        r"^Total\s+factura\s+([\d.,]+)\s+Eur\s*$",
    ])
    if not cups or not total:
        raise FormatoNoReconocido(
            "Factura Naturgy Grandes Clientes reconocida, pero faltan el CUPS "
            "o el total."
        )

    inicio, fin = buscar_periodo(texto, [
        r"PERIODO\s*\n\s*(\d{2}\.\d{2}\.\d{2})\s*/\s*"
        r"(\d{2}\.\d{2}\.\d{2})",
    ])

    def normalizar_fecha(valor: str | None) -> str | None:
        if not valor:
            return None
        partes = valor.replace(".", "/").split("/")
        if len(partes) == 3 and len(partes[2]) == 2:
            partes[2] = f"20{partes[2]}"
        return "/".join(partes)

    inicio = normalizar_fecha(inicio)
    fin = normalizar_fecha(fin)
    dias = 0
    if inicio and fin:
        dias = (datetime.strptime(fin, "%d/%m/%Y") - datetime.strptime(
            inicio, "%d/%m/%Y"
        )).days + 1

    potencias = [
        PotenciaContratadaPeriodo(f"P{periodo}", consumo_es(valor))
        for periodo, valor in re.findall(
            r"^P([1-6]):\s*([\d.,]+)\s*kW\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        )
    ]
    potencias_kw = {item.periodo: item.potencia_kw for item in potencias}

    potencia_agregada: dict[str, dict[str, float]] = {}
    for _, periodo, meses, precio, coste in re.findall(
        r"^POTENCIA\s+(ACCESO|CARGOS)\s+P([1-6])\s+[\d.,]+\s*kW\s+"
        r"([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+Eur\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    ):
        clave = f"P{periodo}"
        datos = potencia_agregada.setdefault(
            clave,
            {"meses": numero_es(meses), "precio_mes": 0.0, "coste": 0.0},
        )
        datos["precio_mes"] += numero_es(precio)
        datos["coste"] += numero_es(coste)

    potencia_periodos = []
    for periodo, datos in sorted(potencia_agregada.items()):
        potencia_kw = potencias_kw.get(periodo, 0.0)
        coste = round(datos["coste"], 2)
        precio_dia = coste / potencia_kw / dias if potencia_kw and dias else 0.0
        potencia_periodos.append(PotenciaFacturadaPeriodo(
            periodo=periodo,
            potencia_kw=potencia_kw,
            dias=dias,
            precio_facturado_eur_kw_dia=precio_dia,
            coste_facturado_eur=coste,
            coste_calculado_eur=round(
                potencia_kw * datos["meses"] * datos["precio_mes"], 2
            ),
            meses=datos["meses"],
            precio_facturado_eur_kw_mes=round(datos["precio_mes"], 9),
        ))

    energia_agregada: dict[str, dict[str, float]] = {}
    for _, periodo, consumo, precio, coste in re.findall(
        r"^ENERG[IÍ]A\s+ACTIVA(?:\s+(CARGOS|ACCESO))?\s+P([1-6])\s+"
        r"([\d.,]+)\s*kWh\s+([\d.,]+)\s+([\d.,]+)\s+Eur\s*$",
        texto,
        re.IGNORECASE | re.MULTILINE,
    ):
        clave = f"P{periodo}"
        datos = energia_agregada.setdefault(
            clave, {"consumo": consumo_es(consumo), "precio": 0.0, "coste": 0.0}
        )
        datos["precio"] += numero_es(precio)
        datos["coste"] += numero_es(coste)

    energia_periodos = [
        EnergiaPeriodo(
            periodo=periodo,
            consumo_kwh=datos["consumo"],
            precio_eur_kwh=round(datos["precio"], 9),
            coste_eur=round(datos["coste"], 2),
        )
        for periodo, datos in sorted(energia_agregada.items())
    ]

    otros = []
    for concepto, patron in (
        (
            "Regularización pagos de capacidad",
            r"^REGULARIZACI[ÓO]N\s+PAGOS\s+CAPACIDAD\s+([-\d.,]+)\s+Eur$",
        ),
        (
            "Regularización financiación OM+OS",
            r"^REGULARIZACI[ÓO]N\s+FINANCIACI[ÓO]N\s+OM\+OS\s+"
            r"([-\d.,]+)\s+Eur$",
        ),
        (
            "Aportación FNEE",
            r"^FONDO\s+DE\s+EFICIENCIA\s+ENERG[ÉE]TICA\s+"
            r"([\d.,]+)\s+Eur$",
        ),
        (
            "Financiación bono social",
            r"^FINANCIACI[ÓO]N\s+BONO\s+SOCIAL\s+CLIENTE[^\n]*?"
            r"([\d.,]+)\s+Eur$",
        ),
    ):
        importe = buscar_numero(texto, [patron])
        if importe:
            otros.append(OtroConcepto(concepto, importe))

    sobrepasamientos = [
        SobrepasamientoPeriodo(f"P{periodo}", consumo_es(valor))
        for periodo, valor in re.findall(
            r"^Ae([1-6])\s+([\d.,]+)\s*kW\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        )
    ]

    factura = FacturaLeida(
        formato="naturgy_grandes_clientes",
        comercializadora="Naturgy Grandes Clientes",
        numero_factura=buscar_texto(texto, [
            r"FACTURA\s+N[º°]?\s+CUENTA\s+CONTRATO[^\n]*\n\s*([^\s]+)",
        ]),
        cups=cups.upper(),
        atr=extraer_atr(texto),
        fecha_factura=normalizar_fecha(buscar_texto(texto, [
            r"FECHA\s+EMISI[ÓO]N\s+CONTRATO\s*\n\s*(\d{2}\.\d{2}\.\d{4})",
        ])),
        periodo_inicio=inicio,
        periodo_fin=fin,
        potencia=round(sum(
            datos["coste"] for datos in potencia_agregada.values()
        ), 2),
        energia=round(sum(item.coste_eur for item in energia_periodos), 2),
        excesos_potencia=buscar_numero(texto, [
            r"^EXCESOS\s+DE\s+POTENCIA\s+ACCESO\s+([\d.,]+)\s+Eur$",
        ]),
        iee=buscar_numero(texto, [
            r"^IMPUESTO\s+EL[ÉE]CTRICO[^\n]*?([\d.,]+)\s+Eur$",
        ]),
        iva=buscar_numero(texto, [
            r"^IVA\s+[\d.,]+\s*%\s+([\d.,]+)\s+Eur$",
        ]),
        total=total,
        energia_periodos=energia_periodos,
        potencias_contratadas=potencias,
        potencia_periodos=potencia_periodos,
        sobrepasamientos=sobrepasamientos,
        otros=otros,
    )
    return _completar_advertencias(factura)


def _naturgy(texto: str) -> FacturaLeida:
    """Extrae las facturas eléctricas detalladas de Naturgy Clientes."""
    cups = buscar_texto(texto, [
        r"C[oó]digo\s+CUPS\s*:\s*(ES[A-Z0-9]+)",
        r"CUPS\s*:\s*(ES[A-Z0-9]+)",
    ])
    total = buscar_numero(texto, [
        r"^Total\s+a\s+pagar\s+([\d.,]+)\s*€?\s*$",
    ])
    cups_anonimizado = bool(re.search(r"C[oó]digo\s+CUPS\s*:\s*CUPS\b", texto, re.IGNORECASE))
    if (not cups and not cups_anonimizado) or not total:
        raise FormatoNoReconocido(
            "Factura Naturgy reconocida, pero faltan el CUPS o el total."
        )

    inicio, fin = buscar_periodo(texto, [
        r"Per[ií]odo\s+electricidad\s*:\s*\n?\s*del\s+"
        r"(\d{2}/\d{2}/\d{4})\s+al\s+(\d{2}/\d{2}/\d{4})",
        r"Per[ií]odo\s+electricidad\s+del\s+"
        r"(\d{2}/\d{2}/\d{4})\s+al\s+(\d{2}/\d{2}/\d{4})",
    ])

    energia_periodos = [
        EnergiaPeriodo(
            periodo=f"P{periodo}",
            consumo_kwh=consumo_es(consumo),
            precio_eur_kwh=numero_es(precio),
            coste_eur=numero_es(coste),
        )
        for periodo, consumo, precio, coste in re.findall(
            r"^[^\n]*?Consumo\s+electricidad\s+P([1-6])\s+([\d.,]+)\s+kWh\s+x\s+"
            r"([\d.,]+)\s*€/kWh\s+([\d.,]+)\s*€?\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        )
    ]
    if not energia_periodos:
        bloque_energia_naturgy = _seccion(
            texto, r"Consumo\s+electricidad", r"T[eé]rmino\s+potencia\s+P1"
        )
        energia_periodos = [
            EnergiaPeriodo(
                periodo=f"Tramo {indice}",
                consumo_kwh=consumo_es(consumo),
                precio_eur_kwh=numero_es(precio),
                coste_eur=numero_es(coste),
                coste_calculado_eur=round(
                    consumo_es(consumo) * numero_es(precio), 2
                ),
            )
            for indice, (consumo, precio, coste) in enumerate(re.findall(
                r"^[^\n]*?\bDel\s+\d{2}/\d{2}/\d{4}\s+al\s+\d{2}/\d{2}/\d{4}\s+"
                r"([\d.,]+)\s*kWh\s+x\s*([\d.,]+)\s*€/kWh\s+"
                r"([\d.,]+)\s*€\s*$",
                bloque_energia_naturgy,
                re.IGNORECASE | re.MULTILINE,
            ), start=1)
        ]

    potencia_periodos = [
        PotenciaFacturadaPeriodo(
            periodo=f"P{periodo}",
            potencia_kw=numero_es(potencia_kw),
            dias=int(dias),
            precio_facturado_eur_kw_dia=numero_es(precio),
            coste_facturado_eur=numero_es(coste),
        )
        for periodo, potencia_kw, dias, precio, coste in re.findall(
            r"^T[eé]rmino\s+potencia\s+P([1-6])\s+([\d.,]+)\s+kW\s+x\s+"
            r"(\d+)\s+d[ií]as\s+x\s+([\d.,]+)\s*€/kW\s+d[ií]a\s+"
            r"([\d.,]+)\s*€?\s*$",
            texto,
            re.IGNORECASE | re.MULTILINE,
        )
    ]
    if not potencia_periodos:
        for periodo in (1, 2):
            bloque_potencia_naturgy = _seccion(
                texto,
                rf"T[eé]rmino\s+potencia\s+P{periodo}",
                rf"T[eé]rmino\s+potencia\s+P{periodo + 1}"
                if periodo == 1 else r"Financiaci[oó]n\s+de\s+Bono\s+Social",
            )
            for potencia_kw, dias, precio, coste in re.findall(
                r"^Del\s+\d{2}/\d{2}/\d{4}\s+al\s+\d{2}/\d{2}/\d{4}\s+"
                r"([\d.,]+)\s*kW\s+x\s*(\d+)\s*d[ií]as\s+x\s*"
                r"([\d.,]+)\s*€/kW\s*d[ií]a\s+([\d.,]+)\s*€\s*$",
                bloque_potencia_naturgy,
                re.IGNORECASE | re.MULTILINE,
            ):
                kw = numero_es(potencia_kw)
                dias_num = int(dias)
                precio_dia = numero_es(precio)
                potencia_periodos.append(PotenciaFacturadaPeriodo(
                    periodo=f"P{periodo}",
                    potencia_kw=kw,
                    dias=dias_num,
                    precio_facturado_eur_kw_dia=precio_dia,
                    coste_facturado_eur=numero_es(coste),
                    coste_calculado_eur=round(kw * dias_num * precio_dia, 2),
                ))

    potencias = extraer_potencias_contratadas(texto)
    if not potencias and potencia_periodos:
        potencias = [
            PotenciaContratadaPeriodo(item.periodo, item.potencia_kw)
            for item in potencia_periodos
        ]

    excesos = sumar_coincidencias(
        texto,
        r"^Exceso\s+de\s+potencia\s+P[1-6]\s+([\d.,]+)\s*€?\s*$",
    )
    maximetros = [
        MaximetroPeriodo(f"P{periodo}", numero_es(valor))
        for periodo, valor in re.findall(
            r"Max[ií]metro\s+P([1-6])\s+-\s+([\d.,]+)\s+kW",
            texto,
            re.IGNORECASE,
        )
    ]

    otros = _otros_comunes(texto)
    for concepto, patron in (
        (
            "Financiación del bono social",
            r"Financiaci[oó]n\s+de\s+Bono\s+Social[^\n]*?([\d.,]+)\s*€?\s*$",
        ),
        (
            "Alquiler equipo de medida",
            r"Alquiler\s+de\s+contador[^\n]*?([\d.,]+)\s*€?\s*$",
        ),
    ):
        importe = buscar_numero(texto, [patron])
        if importe and not any(
            concepto.lower() in item.concepto.lower()
            or item.concepto.lower() in concepto.lower()
            for item in otros
        ):
            otros.append(OtroConcepto(concepto, importe))

    if not any("alquiler" in item.concepto.lower() for item in otros):
        bloque_alquiler = _seccion(
            texto,
            r"Alquiler\s+de\s+contador",
            r"Total\s+electricidad",
        )
        importes_alquiler = re.findall(
            r"Del\s+\d{2}/\d{2}/\d{4}\s+al\s+\d{2}/\d{2}/\d{4}[^\n]*?"
            r"([\d.,]+)\s*€\s*$",
            bloque_alquiler,
            re.IGNORECASE | re.MULTILINE,
        )
        if importes_alquiler:
            otros.append(OtroConcepto(
                "Alquiler equipo de medida",
                round(sum(numero_es(importe) for importe in importes_alquiler), 2),
            ))
    if not any("bono social" in item.concepto.lower() for item in otros):
        bloque_bono = _seccion(
            texto,
            r"Financiaci[oó]n\s+de\s+Bono\s+Social",
            r"Subtotal",
        )
        importes_bono = re.findall(
            r"^Del\s+\d{2}/\d{2}/\d{4}\s+al\s+\d{2}/\d{2}/\d{4}[^\n]*?"
            r"([\d.,]+)\s*€\s*$",
            bloque_bono,
            re.IGNORECASE | re.MULTILINE,
        )
        if importes_bono:
            otros.append(OtroConcepto(
                "Financiación del bono social",
                round(sum(numero_es(importe) for importe in importes_bono), 2),
            ))

    factura = FacturaLeida(
        formato="naturgy",
        comercializadora="Naturgy",
        numero_factura=buscar_texto(texto, [
            r"N\.?[º°o]\s+de\s+factura\s*:\s*([^\s]+)",
        ]),
        cups=cups.upper() if cups else None,
        atr=extraer_atr(texto),
        fecha_factura=buscar_texto(texto, [
            r"Fecha\s+de\s+emisi[oó]n\s*:\s*(\d{2}/\d{2}/\d{4})",
        ]),
        periodo_inicio=inicio,
        periodo_fin=fin,
        potencia=round(
            sum(item.coste_facturado_eur for item in potencia_periodos), 2
        ),
        energia=round(sum(item.coste_eur for item in energia_periodos), 2),
        excesos_potencia=excesos,
        reactiva=buscar_numero(texto, [
            r"^(?:Energ[ií]a\s+)?reactiva[^\n]*?([\d.,]+)\s*€\s*$",
        ]),
        iee=buscar_numero(texto, [
            r"^Impuesto\s+electricidad[^\n]*?([\d.,]+)\s*€?\s*$",
        ]),
        iva=buscar_numero(texto, [
            r"^IVA\s*\([^\n]*?\)[^\n]*?([\d.,]+)\s*€?\s*$",
        ]),
        total=total,
        energia_periodos=energia_periodos,
        potencias_contratadas=potencias,
        potencia_periodos=potencia_periodos,
        maximetros=maximetros,
        otros=otros,
    )
    return _completar_advertencias(factura)


def _repsol(texto: str) -> FacturaLeida:
    """Extrae la plantilla residencial actual de Repsol Luz y Gas."""
    cups = buscar_texto(texto, [r"^CUPS\s+(ES[A-Z0-9]+)\s*$"])
    total = buscar_numero(texto, [r"^Total\s+factura\s+([\d.,]+)\s*€\s*$"])
    if not cups or not total:
        raise FormatoNoReconocido(
            "Factura Repsol reconocida, pero faltan el CUPS o el total."
        )

    inicio, fin = buscar_periodo(texto, [
        r"Periodo\s+de\s+facturaci[oó]n\s+"
        r"(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})",
    ])
    potencia_periodos = [
        PotenciaFacturadaPeriodo(
            periodo=f"P{periodo}",
            potencia_kw=numero_es(potencia_kw),
            dias=int(dias),
            precio_facturado_eur_kw_dia=numero_es(precio),
            coste_facturado_eur=numero_es(coste),
        )
        for periodo, coste, potencia_kw, dias, precio in re.findall(
            r"^Periodo\s+([12])\s+([\d.,]+)\s*€\s+([\d.,]+)\s*kW\s*x\s*"
            r"(\d+)\s*d[ií]as\s*x\s*([\d.,]+)\s*€/kW\s*d[ií]a",
            texto,
            re.IGNORECASE | re.MULTILINE,
        )
    ]
    potencias = [
        PotenciaContratadaPeriodo(item.periodo, item.potencia_kw)
        for item in potencia_periodos
    ]

    calculos_energia = re.findall(
        r"^[^\n]*?([\d.,]+)\s*€\s+([\d.,]+)\s*kWh\s*x\s*"
        r"([\d.,]+)\s*€/kWh",
        texto,
        re.IGNORECASE | re.MULTILINE,
    )
    energia_periodos = [
        EnergiaPeriodo(
            periodo=f"Tramo {indice}",
            consumo_kwh=numero_es(consumo),
            precio_eur_kwh=numero_es(precio),
            coste_eur=numero_es(coste),
        )
        for indice, (coste, consumo, precio) in enumerate(
            calculos_energia, start=1
        )
    ]

    otros = []
    for concepto, patron in (
        (
            "Servicio Batería Virtual",
            r"^Servicio\s+Bater[ií]a\s+Virtual\s+([\d.,]+)\s*€\s*$",
        ),
        (
            "Servicio Integral Hogar Confort",
            r"^Servicio\s+Integral\s+Hogar\s+Confort\s+([\d.,]+)\s*€\s*$",
        ),
        (
            "Financiación bono social",
            r"^Financiaci[oó]n\s+Bono\s+Social\s+([\d.,]+)\s*€",
        ),
        (
            "Alquiler equipo de medida",
            r"^Alquiler\s+de\s+contador\s+([\d.,]+)\s*€",
        ),
    ):
        importe = buscar_numero(texto, [patron])
        if importe:
            otros.append(OtroConcepto(concepto, importe))

    factura = FacturaLeida(
        formato="repsol",
        comercializadora="Repsol",
        numero_factura=buscar_texto(texto, [
            r"^N[º°o]\s+de\s+factura\s+(\d+)\s*$",
        ]),
        cups=cups.upper(),
        atr=extraer_atr(texto),
        fecha_factura=buscar_texto(texto, [
            r"Fecha\s+de\s+emisi[oó]n\s+(\d{2}/\d{2}/\d{4})",
        ]),
        periodo_inicio=inicio,
        periodo_fin=fin,
        potencia=buscar_numero(texto, [r"^T[eé]rmino\s+fijo\s+([\d.,]+)\s*€"]),
        energia=buscar_numero(texto, [r"^Energ[ií]a\s+([\d.,]+)\s*€"]),
        iee=buscar_numero(texto, [
            r"^Impuesto\s+El[eé]ctrico\s+([\d.,]+)\s*€",
        ]),
        iva=buscar_numero(texto, [
            r"^IVA\s*\([^\n]*?\)\s+de\s+[\d.,]+\s+([\d.,]+)\s*€",
        ]) if len(re.findall(
            r"^IVA\s*\([^\n]*?\)\s+de\s+[\d.,]+\s+([\d.,]+)\s*€",
            texto, re.IGNORECASE | re.MULTILINE,
        )) < 2 else sumar_coincidencias(
            texto,
            r"^IVA\s*\([^\n]*?\)\s+de\s+[\d.,]+\s+([\d.,]+)\s*€",
        ),
        total=total,
        energia_periodos=energia_periodos,
        potencias_contratadas=potencias,
        potencia_periodos=potencia_periodos,
        otros=otros,
    )
    return _completar_advertencias(factura)


EXTRACTORES: list[tuple[str, Callable[[str], FacturaLeida], Callable[[str], bool]]] = [
    ("axpo", _axpo, lambda t: "clientes@axpoiberia.es" in t.lower()),
    (
        "iberdrola_tramos",
        _iberdrola_tramos,
        lambda t: (
            "iberdrola clientes" in t.lower()
            and (
                "potencia facturada (" in t.lower()
                or "potencia facturada punta" in t.lower()
            )
        ),
    ),
    (
        "naturgy_grandes_clientes",
        _naturgy_grandes_clientes,
        lambda t: "atenciongrandesclientes@naturgy.com" in t.lower(),
    ),
    (
        "totalenergies",
        _totalenergies,
        lambda t: "totalenergies electricidad y gas españa" in t.lower(),
    ),
    (
        "repsol",
        _repsol,
        lambda t: "repsol comercializadora de electricidad y gas" in t.lower(),
    ),
    (
        "naturgy",
        _naturgy,
        lambda t: "naturgy clientes" in t.lower(),
    ),
    ("visalia_empresas", _visalia_empresas, lambda t: "clientes.empresa@grupovisalia.com" in t.lower()),
    ("visalia_domesticos", _visalia_domesticos, lambda t: "clientes@grupovisalia.com" in t.lower()),
    ("vm", _vm, lambda t: "atcliente@energyavm.es" in t.lower()),
    ("imagina", _imagina, lambda t: "hola@imaginaenergia.com" in t.lower()),
]


def analizar_factura(texto: str) -> FacturaLeida:
    for _, extractor, detecta in EXTRACTORES:
        if detecta(texto):
            factura = extractor(texto)
            break
    else:
        factura = _generico(texto)
    for abono in _extraer_compensaciones_excedentes(texto):
        if not any(
            (
                item.concepto.lower() == abono.concepto.lower()
                or "excedent" in item.concepto.lower()
            )
            and importes_coinciden(
                item.importe, abono.importe, "componentes"
            )
            for item in factura.otros
        ):
            factura.otros.append(abono)
    for servicio in _extraer_servicios_adicionales(texto):
        if not any(
            item.concepto.lower() == servicio.concepto.lower()
            and importes_coinciden(
                item.importe, servicio.importe, "componentes"
            )
            for item in factura.otros
        ):
            factura.otros.append(servicio)
    factura.fecha_vencimiento_contrato = _extraer_fecha_vencimiento_contrato(texto)
    _verificar_fbs(factura, texto)
    _verificar_fnee(factura, texto)
    _verificar_impuestos(factura, texto)
    verificacion_iva_multiple = _verificar_iva_multiple(factura, texto)
    if verificacion_iva_multiple:
        factura.verificacion_iva = verificacion_iva_multiple
    if not factura.iee and factura.verificacion_iee:
        factura.iee = factura.verificacion_iee.importe_facturado_eur
    if not factura.iva and factura.verificacion_iva:
        factura.iva = factura.verificacion_iva.importe_facturado_eur
    # Algunos formatos recuperan los impuestos durante la verificación. La
    # advertencia inicial, calculada antes de ese paso, ya no sería válida.
    factura.advertencias = [
        aviso for aviso in factura.advertencias
        if not aviso.startswith("La suma de los conceptos extraídos")
    ]
    if not importes_coinciden(
        factura.total, factura.suma_componentes, "total_factura"
    ):
        factura.advertencias.append(
            "La suma de los conceptos extraídos no coincide con el total "
            f"(diferencia: {formato_euros(factura.diferencia)})."
        )
    return factura


def componentes_grafico(factura: FacturaLeida, texto: str = "") -> list[dict]:
    valores = {
        "Potencia": factura.potencia,
        "Energía": factura.energia,
        "Excesos": factura.excesos_potencia,
        "Reactiva": factura.reactiva,
        "Otros": factura.total_otros,
        "IEE": factura.iee,
        "IVA": factura.iva,
    }
    verificaciones_factura = {
        "Potencia": _semaforo_componente_potencia(factura),
        "Energía": _semaforo_componente_energia(factura),
        "Excesos": _semaforo_componente_excesos(factura),
        "Reactiva": _semaforo_reactiva_segun_factura(factura),
        "Otros": _semaforo_otros_segun_factura(factura, texto),
        "IEE": _semaforo_impuesto_segun_factura(factura.verificacion_iee),
        "IVA": _semaforo_impuesto_segun_factura(factura.verificacion_iva),
    }
    verificaciones_reales = {
        "Potencia": _semaforo_real_potencia(factura),
        "Energía": "🟡",
        # Los datos agregados de factura permiten comprobar su operación, pero
        # la verificación real de excesos exige siempre la curva de carga.
        "Excesos": "🟡",
        "Reactiva": _semaforo_real_reactiva(factura),
        "Otros": _semaforo_componente_otros(factura, texto),
        "IEE": factura.verificacion_iee.estado if factura.verificacion_iee else "🟡",
        "IVA": factura.verificacion_iva.estado if factura.verificacion_iva else "🟡",
    }
    filas = [
        {
            "Componente": nombre,
            "Importe (€)": importe,
            "Verificación s/factura": verificaciones_factura[nombre],
            "Verificación real": verificaciones_reales[nombre],
        }
        for nombre, importe in valores.items()
        if abs(importe) > 0.0001
        or (nombre == "Reactiva" and bool(factura.reactiva_periodos))
    ]
    if abs(factura.diferencia) > 0.05:
        filas.append({
            "Componente": "Sin asignar",
            "Importe (€)": factura.diferencia,
            "Verificación s/factura": "🔴",
            "Verificación real": "🔴",
        })
    return filas


def componentes_peso_grafico(factura: FacturaLeida) -> list[dict]:
    """Prepara importes no negativos para visualizar el peso neto de la factura.

    Los abonos no se dibujan como sectores negativos: reducen primero Energía,
    después Potencia y finalmente los demás componentes positivos. Esta
    transformación es únicamente visual y no altera el desglose contable.
    """
    otros_positivos = round(
        sum(max(item.importe, 0.0) for item in factura.otros), 2
    )
    abonos = round(
        sum(abs(item.importe) for item in factura.otros if item.importe < 0), 2
    )
    valores = {
        "Potencia": max(factura.potencia, 0.0),
        "Energía": max(factura.energia, 0.0),
        "Excesos": max(factura.excesos_potencia, 0.0),
        "Reactiva": max(factura.reactiva, 0.0),
        "Otros": otros_positivos,
        "IEE": max(factura.iee, 0.0),
        "IVA": max(factura.iva, 0.0),
    }
    for componente in (
        "Energía", "Potencia", "Otros", "Excesos", "Reactiva", "IEE", "IVA"
    ):
        reduccion = min(valores[componente], abonos)
        valores[componente] = round(valores[componente] - reduccion, 2)
        abonos = round(abonos - reduccion, 2)
        if abonos <= 0:
            break
    return [
        {"Componente": nombre, "Importe (€)": importe}
        for nombre, importe in valores.items()
        if importe > 0
    ]


def _semaforo_componente_potencia(factura: FacturaLeida) -> str:
    if not factura.potencia_periodos:
        return "🟡"
    if any(
        item.resultado == "No verificado"
        for item in factura.potencia_periodos
    ):
        return "🟡"
    detalle = sum(item.coste_facturado_eur for item in factura.potencia_periodos)
    return "🟢" if importes_coinciden(
        factura.potencia, detalle, "componentes"
    ) else "🔴"


def _semaforo_reactiva_segun_factura(factura: FacturaLeida) -> str:
    if not factura.reactiva_periodos:
        return "🟡"
    detalle = sum(item.coste_facturado_eur for item in factura.reactiva_periodos)
    return "🟢" if importes_coinciden(
        factura.reactiva, detalle, "componentes"
    ) else "🔴"


def _semaforo_real_reactiva(factura: FacturaLeida) -> str:
    if not factura.reactiva_periodos:
        return "🟡"
    estados = {item.estado for item in factura.reactiva_periodos}
    if "🔴" in estados:
        return "🔴"
    return "🟢 ⚠️" if "🟢 ⚠️" in estados else "🟢"


def _semaforo_real_potencia(factura: FacturaLeida) -> str:
    if not factura.potencia_periodos:
        return "🟡"
    if any(
        item.resultado == "No verificado"
        for item in factura.potencia_periodos
    ):
        return "🟡"
    calculos_correctos = all(
        importes_coinciden(
            item.coste_facturado_eur,
            round(
                item.potencia_kw
                * item.dias
                * item.precio_facturado_eur_kw_dia,
                2,
            ),
            "componentes",
        )
        for item in factura.potencia_periodos
    )
    return "🟢" if calculos_correctos else "🔴"


def _semaforo_impuesto_segun_factura(
    verificacion: VerificacionImpuesto | None,
) -> str:
    if not verificacion:
        return "🟡"
    return (
        "🟢"
        if importes_coinciden(
            verificacion.importe_facturado_eur,
            verificacion.importe_calculado_eur,
            "impuestos",
        )
        else "🔴"
    )


def _semaforo_componente_energia(factura: FacturaLeida) -> str:
    if not factura.energia_periodos:
        return "🟡"
    detalle = sum(
        item.coste_calculado_eur
        if item.coste_calculado_eur is not None
        else item.coste_eur
        for item in factura.energia_periodos
    )
    return "🟢" if importes_coinciden(
        factura.energia, detalle, "componentes"
    ) else "🟡"


def _semaforo_componente_excesos(factura: FacturaLeida) -> str:
    if not factura.excesos_verificados:
        return "🟡"
    return semaforo_desviacion_coste(
        factura.excesos_potencia,
        factura.coste_excesos_calculado,
        "excesos_maximetros",
    )


def _semaforo_componente_otros(factura: FacturaLeida, texto: str) -> str:
    return _peor_semaforo([
        estado_otro_segun_factura(factura, texto, item)
        for item in factura.otros
    ])


def _semaforo_otros_segun_factura(factura: FacturaLeida, texto: str) -> str:
    return _peor_semaforo([
        estado_otro_segun_factura(factura, texto, item)
        for item in factura.otros
    ])


def generar_resumen(factura: FacturaLeida) -> str:
    componentes = {
        "la potencia": factura.potencia,
        "la energía": factura.energia,
        "los excesos de potencia": factura.excesos_potencia,
        "la energía reactiva": factura.reactiva,
        "otros conceptos": factura.total_otros,
        "el impuesto eléctrico": factura.iee,
        "el IVA": factura.iva,
    }
    principales = sorted(
        ((nombre, importe) for nombre, importe in componentes.items() if importe > 0),
        key=lambda item: item[1],
        reverse=True,
    )[:2]

    texto = f"La factura asciende a {formato_euros(factura.total)}."
    if principales and factura.total:
        pesos = [
            f"{nombre} representa el "
            f"{formato_pct(importe / factura.total * 100, 1)}"
            for nombre, importe in principales
        ]
        texto += " " + " y ".join(pesos).capitalize() + "."
    if factura.excesos_potencia:
        texto += (
            f" Incluye {formato_euros(factura.excesos_potencia)} "
            "de excesos de potencia."
        )
    if factura.reactiva:
        texto += f" Incluye {formato_euros(factura.reactiva)} de energía reactiva."
    if importes_coinciden(
        factura.total, factura.suma_componentes, "total_factura"
    ):
        texto += " Los componentes extraídos cuadran con el total."
    else:
        texto += " La extracción requiere revisión porque los componentes no cuadran."
    return texto
