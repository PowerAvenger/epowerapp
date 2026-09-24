"""Acceso local y controlado al portal de agentes de Informa Energía."""

from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any


URL_ACCESO_INFORMA = "https://agentes.informaenergia.com/sign-in"
RUTA_PERFIL_INFORMA = (
    Path(__file__).resolve().parent / ".local_data" / "informa" / "chrome_profile"
)
RUTA_CAPTURA_ERROR = (
    Path(__file__).resolve().parent / ".local_data" / "informa" / "error_acceso.png"
)
RUTA_CAPTURA_DIAGNOSTICO = (
    Path(__file__).resolve().parent / ".local_data" / "informa" / "diagnostico.png"
)
RUTA_DATOS_DIAGNOSTICO = (
    Path(__file__).resolve().parent / ".local_data" / "informa" / "diagnostico.json"
)


def normalizar_filtros_informa(atr, contrato, segmento):
    """Aplica las combinaciones comerciales disponibles en Informa."""
    atr = str(atr or "2.0 TD").strip().upper()
    if not atr.endswith("TD"):
        atr = f"{atr} TD"
    contrato = str(contrato or "Fijo").strip()
    segmento = str(segmento or "Residencial").strip()
    if atr in {"3.0 TD", "6.1 TD"}:
        contrato = "Fijo"
        segmento = "PYME"
    return atr, contrato, segmento


def _primer_elemento(driver, selectores):
    from selenium.webdriver.common.by import By

    for selector in selectores:
        elementos = driver.find_elements(By.CSS_SELECTOR, selector)
        if elementos:
            return elementos[0]
    return None


def _pulsar_por_texto(driver, textos: tuple[str, ...]) -> bool:
    """Pulsa el primer enlace o botón visible cuyo texto coincida."""
    from selenium.webdriver.common.by import By

    for texto in textos:
        xpath = (
            "//*[self::a or self::button or @role='button']"
            f"[contains(normalize-space(.), {texto!r})]"
        )
        for elemento in driver.find_elements(By.XPATH, xpath):
            if elemento.is_displayed() and elemento.is_enabled():
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", elemento
                )
                elemento.click()
                return True
    # Los menús Angular de Informa pueden usar div/span con el evento de clic
    # en un ancestro, sin semántica HTML de enlace o botón.
    for texto in textos:
        xpath = f"//*[normalize-space(.)={texto!r}]"
        for elemento in driver.find_elements(By.XPATH, xpath):
            if not elemento.is_displayed():
                continue
            driver.execute_script(
                """
                const origen = arguments[0];
                const objetivo = origen.closest(
                    'a, button, [role="button"], li, [class*="menu"], [class*="item"]'
                ) || origen;
                objetivo.scrollIntoView({block: 'center'});
                objetivo.click();
                """,
                elemento,
            )
            return True
    return False


def _resumen_estructural(driver, navegacion=None, tarjetas=None) -> dict[str, Any]:
    """Devuelve metadatos de la interfaz sin conservar HTML ni credenciales."""
    from selenium.webdriver.common.by import By

    def textos(selector, limite=30):
        valores = []
        for elemento in driver.find_elements(By.CSS_SELECTOR, selector):
            texto = " ".join(elemento.text.split())
            if texto and texto not in valores:
                valores.append(texto)
            if len(valores) >= limite:
                break
        return valores

    selects = []
    for indice, elemento in enumerate(driver.find_elements(By.TAG_NAME, "select")):
        opciones = [
            " ".join(opcion.text.split())
            for opcion in elemento.find_elements(By.TAG_NAME, "option")
            if opcion.text.strip()
        ]
        selects.append({
            "indice": indice,
            "nombre": elemento.get_attribute("name") or "",
            "id": elemento.get_attribute("id") or "",
            "opciones": opciones,
        })
    return {
        "url": driver.current_url,
        "titulo": driver.title,
        "navegacion": navegacion or {},
        "encabezados": textos("h1, h2, h3, h4"),
        "botones": textos("button, a.btn, [role='button']"),
        "enlaces": [
            {
                "texto": " ".join(elemento.text.split()),
                "href": elemento.get_attribute("href") or "",
            }
            for elemento in driver.find_elements(By.CSS_SELECTOR, "a[href]")[:40]
            if elemento.text.strip()
        ],
        "selectores": selects,
        "tarjetas": _textos_tarjetas(driver) if tarjetas is None else tarjetas,
    }


def _textos_tarjetas(driver) -> list[str]:
    """Localiza las tarjetas por su contenido, sin depender de clases CSS."""
    textos = driver.execute_script(
        r"""
        const esVisible = el => {
            const estilo = window.getComputedStyle(el);
            const caja = el.getBoundingClientRect();
            return estilo.display !== 'none' && estilo.visibility !== 'hidden' &&
                caja.width > 0 && caja.height > 0;
        };
        const filtroContrato = [...document.querySelectorAll('select#tipoContrato')]
            .find(el => esVisible(el) && el.options && el.options.length > 0);
        let raiz = filtroContrato ? filtroContrato.parentElement : document.body;
        while (raiz && raiz !== document.body) {
            const contratosEnRaiz = [...raiz.querySelectorAll('*')].filter(el =>
                esVisible(el) &&
                (el.innerText || '').trim().toUpperCase() === 'CONTRATAR'
            ).length;
            if (contratosEnRaiz > 0) break;
            raiz = raiz.parentElement;
        }
        raiz = raiz || document.body;
        const visibles = [...raiz.querySelectorAll('*')].filter(el =>
            esVisible(el) &&
            /^Potencia\s*\(/i.test((el.innerText || '').trim()) &&
            (el.innerText || '').trim().split(/\r?\n/).length <= 2
        );
        const tarjetas = [];
        const registrarDesde = elemento => {
            let actual = elemento.parentElement;
            while (actual && actual !== document.body) {
                const texto = (actual.innerText || '').trim();
                const lineas = texto.split(/\r?\n/)
                    .map(linea => linea.trim()).filter(Boolean);
                const potencias = (texto.match(/Potencia\s*\(/gi) || []).length;
                if (
                    esVisible(actual) &&
                    potencias === 1 &&
                    /^\d+$/.test(lineas[0] || '') &&
                    /Energía\s*\(/i.test(texto)
                ) {
                    tarjetas.push(texto);
                    break;
                }
                actual = actual.parentElement;
            }
        };
        for (const encabezado of visibles) {
            registrarDesde(encabezado);
        }
        // Algunas tarjetas (en particular la primera) colocan el número de
        // orden fuera de la rama DOM del encabezado Potencia. Localizarlas
        // también desde su índice visible evita perder el 0 aunque el diseño
        // interno de esa tarjeta sea diferente.
        const indicesVisibles = [...raiz.querySelectorAll('*')].filter(el => {
            const texto = (el.innerText || '').trim();
            return esVisible(el) && /^\d+$/.test(texto) &&
                ![...el.children].some(hijo =>
                    (hijo.innerText || '').trim() === texto
                );
        });
        for (const indice of indicesVisibles) {
            registrarDesde(indice);
        }
        return [...new Set(tarjetas)];
        """
    )
    return ["\n".join(str(texto).splitlines()) for texto in (textos or [])]


def _cargar_todas_las_tarjetas(driver, max_iteraciones=40) -> list[str]:
    """Recorre la vista y acumula tarjetas aunque el DOM las virtualice."""
    driver.execute_script("window.scrollTo(0, 0);")
    acumuladas = {}
    # La primera fila puede tardar en volver al DOM después de una captura
    # anterior. No iniciamos el recorrido hasta recuperar expresamente el 0.
    for _ in range(24):
        iniciales = _textos_tarjetas(driver)
        for texto in iniciales:
            primera_linea = texto.lstrip().splitlines()[0]
            clave = int(primera_linea) if primera_linea.isdigit() else texto
            acumuladas[clave] = texto
        if 0 in acumuladas:
            break
        time.sleep(0.25)
    anterior = None
    estable = 0
    for _ in range(max_iteraciones):
        for texto in _textos_tarjetas(driver):
            primera_linea = texto.lstrip().splitlines()[0]
            clave = int(primera_linea) if primera_linea.isdigit() else texto
            acumuladas[clave] = texto
        estado = driver.execute_script(
            r"""
            const visibles = [...document.querySelectorAll('body *')].filter(el => {
                const estilo = window.getComputedStyle(el);
                const caja = el.getBoundingClientRect();
                return estilo.display !== 'none' && estilo.visibility !== 'hidden' &&
                    caja.width > 0 && caja.height > 0 &&
                    (el.innerText || '').trim().toUpperCase() === 'CONTRATAR';
            }).length;
            const siguiente = Math.min(
                window.scrollY + window.innerHeight * 0.8,
                document.documentElement.scrollHeight
            );
            window.scrollTo(0, siguiente);
            return {
                tarjetas: visibles,
                altura: document.documentElement.scrollHeight,
                posicion: window.scrollY + window.innerHeight
            };
            """
        )
        time.sleep(0.35)
        firma = (estado["tarjetas"], estado["altura"])
        esta_abajo = estado["posicion"] >= estado["altura"] - 5
        estable = estable + 1 if firma == anterior and esta_abajo else 0
        if estable >= 3:
            break
        anterior = firma
    for texto in _textos_tarjetas(driver):
        primera_linea = texto.lstrip().splitlines()[0]
        clave = int(primera_linea) if primera_linea.isdigit() else texto
        acumuladas[clave] = texto
    return [acumuladas[clave] for clave in sorted(
        acumuladas,
        key=lambda valor: (
            0, valor
        ) if isinstance(valor, int) else (1, str(valor)),
    )]


def _fusionar_captura_anterior(tarjetas, atr, contrato, segmento):
    """Completa huecos con la captura previa de la misma configuración."""
    combinadas = {}

    def incorporar(coleccion):
        for texto in coleccion or []:
            primera_linea = str(texto).lstrip().splitlines()[0]
            if primera_linea.isdigit():
                combinadas[int(primera_linea)] = str(texto)

    if RUTA_DATOS_DIAGNOSTICO.exists():
        try:
            anterior = json.loads(
                RUTA_DATOS_DIAGNOSTICO.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            anterior = {}
        navegacion = anterior.get("navegacion", {})
        misma_configuracion = (
            navegacion.get("familia_atr") == atr
            and navegacion.get("contrato") == contrato
            and navegacion.get("segmento") == segmento
        )
        if misma_configuracion:
            incorporar(anterior.get("tarjetas"))
    incorporar(tarjetas)
    return [combinadas[indice] for indice in sorted(combinadas)]


def _texto_normalizado(valor: str) -> str:
    return "".join(
        caracter for caracter in unicodedata.normalize("NFKD", str(valor))
        if not unicodedata.combining(caracter)
    ).casefold()


def _numero_despues_de_linea(lineas, prefijo):
    prefijo = _texto_normalizado(prefijo)
    for indice, linea in enumerate(lineas[:-1]):
        if _texto_normalizado(linea).startswith(prefijo):
            try:
                return float(lineas[indice + 1].replace(",", "."))
            except ValueError:
                return None
    return None


def parsear_tarjeta_informa(texto: str, atr: str) -> dict[str, Any]:
    """Convierte el texto visible de una tarjeta en una oferta normalizada."""
    lineas = [linea.strip() for linea in str(texto).splitlines() if linea.strip()]
    if len(lineas) < 4 or not lineas[0].isdigit():
        raise ValueError("La tarjeta de Informa no tiene una cabecera reconocible.")
    nombre = lineas[1]
    segmento_contrato = lineas[2]

    def bloque(desde, hasta):
        inicio = next(
            indice for indice, linea in enumerate(lineas)
            if _texto_normalizado(linea).startswith(_texto_normalizado(desde))
        )
        fin = next(
            (
                indice for indice in range(inicio + 1, len(lineas))
                if _texto_normalizado(lineas[indice]).startswith(
                    _texto_normalizado(hasta)
                )
            ),
            len(lineas),
        )
        precios = {}
        for linea in lineas[inicio + 1:fin]:
            coincidencia = re.fullmatch(r"P([1-6]):\s*([0-9]+(?:[.,][0-9]+)?)", linea)
            if coincidencia:
                precios[f"P{coincidencia.group(1)}"] = float(
                    coincidencia.group(2).replace(",", ".")
                )
        return precios

    potencia = bloque("Potencia", "Energía")
    energia = bloque("Energía", "Comisión")
    vigencia = re.search(r"válida\s+hasta\s+el\s+(\d{4}-\d{2}-\d{2})", texto, re.I)
    atr_normalizado = str(atr).upper().replace(" ", "").removesuffix("TD")
    exigibles_energia = 3 if atr_normalizado == "2.0" else 6
    exigibles_potencia = 2 if atr_normalizado == "2.0" else 6
    if len(energia) != exigibles_energia or len(potencia) != exigibles_potencia:
        raise ValueError(
            f"Periodos incompletos en {nombre}: potencia {len(potencia)} y "
            f"energía {len(energia)} para {atr_normalizado}TD."
        )
    return {
        "indice_web": int(lineas[0]),
        "nombre": nombre,
        "segmento_contrato": segmento_contrato,
        "atr": atr_normalizado,
        "vigencia_hasta": vigencia.group(1) if vigencia else None,
        "potencia": potencia,
        "energia": energia,
        "costes_fijos_eur": _numero_despues_de_linea(lineas, "Costes Fijos"),
        "comision_fija_eur": _numero_despues_de_linea(lineas, "Comisión fija"),
        "comision_energia_eur_mwh": _numero_despues_de_linea(
            lineas, "Comisión energía"
        ),
        "comision_potencia_eur": _numero_despues_de_linea(
            lineas, "Comisión potencia"
        ),
    }


def parsear_tarjetas_informa(tarjetas, atr: str) -> list[dict[str, Any]]:
    """Parsea todas las tarjetas y conserva cualquier error para revisión."""
    ofertas = []
    for texto in tarjetas or []:
        try:
            ofertas.append(parsear_tarjeta_informa(texto, atr))
        except ValueError as error:
            ofertas.append({"error": str(error), "texto": str(texto)})
    return ofertas


def validar_captura_informa(tarjetas, atr: str) -> list[dict[str, Any]]:
    """Exige una secuencia completa y tarjetas compatibles antes de publicar."""
    tarjetas = list(tarjetas or [])
    indices = []
    for texto in tarjetas:
        primera_linea = str(texto).lstrip().splitlines()[0]
        if not primera_linea.isdigit():
            raise ValueError("Hay una tarjeta sin índice web reconocible.")
        indices.append(int(primera_linea))
    if not indices:
        raise ValueError("Informa no ha devuelto ninguna tarjeta.")
    duplicados = sorted({indice for indice in indices if indices.count(indice) > 1})
    if duplicados:
        raise ValueError(
            "Hay índices de oferta duplicados: "
            + ", ".join(map(str, duplicados)) + "."
        )
    faltantes = sorted(set(range(max(indices) + 1)).difference(indices))
    if min(indices) != 0 or faltantes:
        raise ValueError(
            "La captura de Informa no está completa. Faltan los índices: "
            + ", ".join(map(str, faltantes or [0])) + "."
        )
    ofertas = parsear_tarjetas_informa(tarjetas, atr)
    errores = [oferta["error"] for oferta in ofertas if "error" in oferta]
    if errores:
        raise ValueError(
            f"{len(errores)} tarjeta(s) no superan la validación: {errores[0]}"
        )
    return ofertas


def cargar_ultimo_diagnostico_informa() -> dict[str, Any] | None:
    """Recupera la última vista previa local después de reiniciar Streamlit."""
    if not RUTA_DATOS_DIAGNOSTICO.exists():
        return None
    try:
        datos = json.loads(RUTA_DATOS_DIAGNOSTICO.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return datos if isinstance(datos, dict) else None


def _seleccionar_filtro(driver, opciones_distintivas, valor: str) -> bool:
    """Selecciona por texto el desplegable reconocido por sus opciones."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import Select

    distintivas = {texto.casefold() for texto in opciones_distintivas}
    for elemento in driver.find_elements(By.TAG_NAME, "select"):
        opciones = {
            " ".join(opcion.text.split()).casefold()
            for opcion in elemento.find_elements(By.TAG_NAME, "option")
        }
        # Algunas familias solo ofrecen un subconjunto (por ejemplo, 3.0 y
        # 6.1 ya llegan restringidas a Pyme). Basta con que el desplegable
        # contenga el valor objetivo y alguna opción propia de este filtro.
        if valor.casefold() not in opciones or not distintivas.intersection(opciones):
            continue
        objetivo = next(
            (
                opcion.text
                for opcion in elemento.find_elements(By.TAG_NAME, "option")
                if " ".join(opcion.text.split()).casefold() == valor.casefold()
            ),
            None,
        )
        if objetivo is None:
            return False
        Select(elemento).select_by_visible_text(objetivo)
        return True
    return False


def diagnosticar_acceso_informa(
    email: str,
    password: str,
    *,
    atr: str = "2.0 TD",
    contrato: str = "Fijo",
    segmento: str = "Residencial",
    timeout: int = 30,
) -> dict[str, Any]:
    """Inicia sesión y describe la pantalla de ofertas sin modificar datos."""
    email = str(email or "").strip()
    password = str(password or "")
    if not email or not password:
        raise ValueError(
            "Faltan email o contraseña en INFORMA_CREDENTIALS."
        )
    atr, contrato, segmento = normalizar_filtros_informa(
        atr, contrato, segmento
    )

    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    RUTA_PERFIL_INFORMA.mkdir(parents=True, exist_ok=True)
    opciones = webdriver.ChromeOptions()
    opciones.add_argument(f"--user-data-dir={RUTA_PERFIL_INFORMA}")
    opciones.add_argument("--start-maximized")
    opciones.add_argument("--disable-notifications")
    opciones.add_argument("--disable-search-engine-choice-screen")

    driver = None
    etapa = "iniciar Chrome"
    try:
        driver = webdriver.Chrome(options=opciones)
        etapa = "abrir la página de acceso"
        driver.get(URL_ACCESO_INFORMA)
        espera = WebDriverWait(driver, timeout)

        etapa = "localizar el formulario de acceso"
        campo_password = _primer_elemento(driver, [
            "input[type='password']",
            "input[name*='password' i]",
            "input[name*='pass' i]",
        ])
        if campo_password is not None:
            campo_email = _primer_elemento(driver, [
                "input[type='email']",
                "input[name*='email' i]",
                "input[name*='user' i]",
                "input[type='text']",
            ])
            if campo_email is None:
                raise RuntimeError("No se encontró el campo de email de Informa.")
            campo_email.clear()
            campo_email.send_keys(email)
            campo_password.clear()
            campo_password.send_keys(password)
            boton = _primer_elemento(driver, [
                "button[type='submit']",
                "input[type='submit']",
                "input[value*='entrar' i]",
                "[class*='btn-login' i]",
                "[class*='login-btn' i]",
            ])
            etapa = "enviar las credenciales"
            if boton is not None:
                boton.click()
            elif not _pulsar_por_texto(driver, ("ENTRAR", "Entrar")):
                # Algunos formularios Angular no exponen el control como un
                # submit HTML, pero sí procesan Enter desde la contraseña.
                from selenium.webdriver.common.keys import Keys

                campo_password.send_keys(Keys.ENTER)

        etapa = "esperar la validación del acceso"
        espera.until(lambda navegador: "sign-in" not in navegador.current_url)
        etapa = "esperar el panel principal"
        espera.until(lambda navegador: "Ofertas" in navegador.page_source)
        etapa = "abrir el menú Ofertas"
        menu_ofertas = _pulsar_por_texto(driver, ("Ofertas",))
        etapa = "abrir Todas las ofertas"
        if menu_ofertas:
            espera.until(
                lambda navegador: "Todas las Ofertas" in navegador.page_source
                or "Todas las ofertas" in navegador.page_source
            )
        todas_ofertas = _pulsar_por_texto(
            driver, ("Todas las Ofertas", "Todas las ofertas")
        )
        if not todas_ofertas:
            raise RuntimeError("No se encontró la opción Todas las ofertas.")
        etapa = f"esperar el selector de familias y abrir {atr}"
        alias_atr = (atr, atr.replace(" ", ""), atr.replace(" TD", ""))

        def familia_visible(navegador):
            texto_visible = navegador.find_element(By.TAG_NAME, "body").text.upper()
            return any(alias.upper() in texto_visible for alias in alias_atr)

        espera_familias = WebDriverWait(driver, max(timeout * 3, 90))
        try:
            espera_familias.until(familia_visible)
        except TimeoutException:
            # El dashboard de Informa puede quedarse en el spinner tras el
            # primer clic. Reabrir la vista relanza la petición de Angular.
            _pulsar_por_texto(driver, ("Ofertas",))
            _pulsar_por_texto(
                driver, ("Todas las Ofertas", "Todas las ofertas")
            )
            espera_familias.until(familia_visible)
        familia_atr = _pulsar_por_texto(driver, alias_atr)
        if not familia_atr:
            raise RuntimeError(f"No se encontró la familia {atr}.")
        etapa = f"esperar los filtros de ofertas {atr}"
        espera.until(
            lambda navegador: (
                "Tipo contrato" in navegador.page_source
                and "Tipo oferta" in navegador.page_source
            )
        )
        etapa = f"seleccionar contrato {contrato}"
        filtro_contrato = _seleccionar_filtro(
            driver, ("Fijo", "Indexado"), contrato
        )
        if not filtro_contrato:
            raise RuntimeError(
                f"No se pudo seleccionar el tipo de contrato {contrato}."
            )
        etapa = f"seleccionar tipo de oferta {segmento}"
        filtro_segmento = _seleccionar_filtro(
            driver, ("Residencial y Pyme", "Residencial", "PYME"), segmento
        )
        if not filtro_segmento and segmento.upper() == "PYME":
            try:
                WebDriverWait(driver, max(timeout, 30)).until(
                    lambda navegador: bool(_textos_tarjetas(navegador))
                )
            except TimeoutException:
                pass
            filtro_segmento = _seleccionar_filtro(
                driver,
                ("Residencial y Pyme", "Residencial", "PYME"),
                segmento,
            )
            tarjetas_visibles = _textos_tarjetas(driver)
            filtro_segmento = filtro_segmento or (
                bool(tarjetas_visibles) and all(
                    re.search(r"\bPyme\s*-\s*Fijo\b", tarjeta, re.IGNORECASE)
                    for tarjeta in tarjetas_visibles
                )
            )
        if not filtro_segmento:
            raise RuntimeError(
                f"No se pudo seleccionar el tipo de oferta {segmento}."
            )
        etapa = f"esperar las tarjetas {atr} {contrato} {segmento}"
        espera.until(
            lambda navegador: (
                "CONTRATAR" in navegador.find_element(
                    By.TAG_NAME, "body"
                ).text.upper()
                or "OFERTA PDF" in navegador.find_element(
                    By.TAG_NAME, "body"
                ).text.upper()
            )
        )
        etapa = f"completar la carga diferida de tarjetas {atr}"
        tarjetas = _cargar_todas_las_tarjetas(driver)
        tarjetas = _fusionar_captura_anterior(
            tarjetas, atr, contrato, segmento
        )
        etapa = f"validar la captura completa de tarjetas {atr}"
        validar_captura_informa(tarjetas, atr)
        etapa = "analizar la interfaz de ofertas"
        RUTA_CAPTURA_DIAGNOSTICO.parent.mkdir(parents=True, exist_ok=True)
        driver.save_screenshot(str(RUTA_CAPTURA_DIAGNOSTICO))
        diagnostico = _resumen_estructural(driver, {
            "menu_ofertas_pulsado": menu_ofertas,
            "todas_ofertas_pulsado": todas_ofertas,
            "familia_atr": atr,
            "familia_atr_pulsada": familia_atr,
            "contrato": contrato,
            "filtro_contrato_seleccionado": filtro_contrato,
            "segmento": segmento,
            "filtro_segmento_seleccionado": filtro_segmento,
            "tarjetas_cargadas": len(tarjetas),
            "captura": str(RUTA_CAPTURA_DIAGNOSTICO),
        }, tarjetas=tarjetas)
        RUTA_DATOS_DIAGNOSTICO.write_text(
            json.dumps(diagnostico, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return diagnostico
    except ValueError:
        raise
    except Exception as error:
        url_actual = ""
        if driver is not None:
            try:
                url_actual = driver.current_url
                RUTA_CAPTURA_ERROR.parent.mkdir(parents=True, exist_ok=True)
                driver.save_screenshot(str(RUTA_CAPTURA_ERROR))
            except Exception:
                pass
        detalle = str(error).splitlines()[0].strip().rstrip(".")
        detalle = detalle.replace(email, "[email]").replace(password, "[password]")
        if len(detalle) > 240:
            detalle = detalle[:237] + "..."
        contexto = f" URL: {url_actual}." if url_actual else ""
        raise RuntimeError(
            f"Fallo al {etapa}.{contexto} "
            f"{type(error).__name__}: {detalle or 'sin detalle adicional'}. "
            f"Captura local: {RUTA_CAPTURA_ERROR}."
        ) from error
    finally:
        if driver is not None:
            driver.quit()
