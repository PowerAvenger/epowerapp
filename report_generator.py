"""
report_generator.py
-------------------
Módulo de generación de informes de optimización de potencias eléctricas.
Genera PDF, HTML y DOCX desde los mismos datos.

Dependencias (solo pip, sin instalaciones en Windows):
    pip install jinja2 xhtml2pdf python-docx matplotlib
"""

import base64
import io
from pathlib import Path
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from jinja2 import Environment, FileSystemLoader
# xhtml2pdf eliminado — incompatible con Streamlit Cloud
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def fig_to_png_base64(fig, width: int = 900, height: int = 400) -> str:
    """
    Convierte una figura matplotlib o plotly a PNG embebido como base64.
    Devuelve una etiqueta <img> lista para incrustar en HTML.
    Funciona en Streamlit Cloud con chromium + kaleido.
    """
    if hasattr(fig, "to_image"):
        # Plotly
        png_bytes = fig.to_image(format="png", width=width, height=height, scale=2)
    elif hasattr(fig, "savefig"):
        # matplotlib
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
        buf.seek(0)
        png_bytes = buf.read()
    else:
        raise TypeError(f"Tipo de figura no soportado: {type(fig)}")

    b64 = base64.b64encode(png_bytes).decode("utf-8")
    return f'<img src="data:image/png;base64,{b64}" style="width:100%;display:block;"/>'


def fig_to_base64(fig) -> str:
    """Alias mantenido por compatibilidad."""
    return fig_to_png_base64(fig)


def logo_to_base64(logo_path: str | None) -> str | None:
    """Carga el logo del usuario como base64. Devuelve None si no hay logo."""
    if not logo_path:
        return None
    path = Path(logo_path)
    if not path.exists():
        return None
    with open(path, "rb") as f:
        ext = path.suffix.lower().replace(".", "")
        if ext == "jpg":
            ext = "jpeg"
        data = base64.b64encode(f.read()).decode("utf-8")
        return f"data:image/{ext};base64,{data}"


def fmt_eur(value: float) -> str:
    """Formatea un número como moneda europea."""
    try:
        return f"{float(value):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return str(value)


# ---------------------------------------------------------------------------
# Preparación del contexto común
# ---------------------------------------------------------------------------

def build_context(
    graf_costes_potcon,
    graf_resumen,
    coste_tp_potcon: float,
    coste_tp_potopt: float,
    ahorro_opt: float,
    ahorro_opt_porc: float,
    df_potencias,
    graf_ahorro,
    graf_costes_pot_periodos,
    logo_path: str | None = None,
    titulo: str = "Informe de Optimización de Potencias",
    subtitulo: str = "",
    realizado_por: str = "",
    cliente: str = "",
    cups: str = "",
    peaje: str = "",
    periodo_datos: str = "",
    nif: str = "",
    direccion: str = "",
    fecha_realizacion: str = "",
    objeto: str = "",
) -> dict:
    """
    Construye el diccionario de contexto que alimenta tanto la plantilla HTML
    como el generador de DOCX.
    """
    return {
        "titulo": titulo,
        "subtitulo": subtitulo,
        "fecha": fecha_realizacion or datetime.now().strftime("%d/%m/%Y"),
        "fecha_realizacion": (
            fecha_realizacion or datetime.now().strftime("%d/%m/%Y")
        ),
        "realizado_por": realizado_por,
        "cliente": cliente,
        "nif": nif,
        "direccion": direccion,
        "objeto": objeto,
        "cups": cups,
        "peaje": peaje,
        "periodo_datos": periodo_datos,
        "logo": logo_to_base64(logo_path),
        # KPIs
        "coste_tp_potcon": fmt_eur(coste_tp_potcon),
        "coste_tp_potopt": fmt_eur(coste_tp_potopt),
        "ahorro_opt": fmt_eur(ahorro_opt),
        "ahorro_opt_porc": f"{float(ahorro_opt_porc):.1f} %",
        # Tabla (HTML desde pandas)
        "tabla_potencias": df_potencias.to_html(
            index=False,
            classes="tabla-datos",
            border=0,
            float_format=lambda x: f"{x:,.2f}",
        ),
        # Gráficos como base64
        "graf_resumen":            fig_to_png_base64(graf_resumen),
        "graf_costes_potcon":      fig_to_png_base64(graf_costes_potcon),
        "graf_ahorro":             fig_to_png_base64(graf_ahorro),
        "graf_costes_pot_periodos": fig_to_png_base64(graf_costes_pot_periodos, height=500),
    }


# ---------------------------------------------------------------------------
# Generador HTML
# ---------------------------------------------------------------------------

def generate_html(context: dict, template_path: str = "templates/informe.html") -> str:
    """
    Renderiza la plantilla Jinja2 con el contexto y devuelve el HTML como string.
    template_path puede ser relativo al directorio de trabajo o absoluto.
    """
    template_dir = str(Path(template_path).parent.resolve())
    template_file = Path(template_path).name
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template(template_file)
    return template.render(**context)


# ---------------------------------------------------------------------------
# Generador PDF
# ---------------------------------------------------------------------------

def generate_pdf_old(html_string: str) -> bytes:
    """
    PDF desactivado temporalmente — xhtml2pdf incompatible con Streamlit Cloud.
    Devuelve bytes vacíos para no romper la app.
    """
    return b""

def generate_pdf(html_string: str) -> bytes:
    """
    Genera un PDF a partir del HTML renderizado con Jinja2.
    Usa WeasyPrint — compatible con Streamlit Community Cloud.
    """
    from weasyprint import HTML
    return HTML(string=html_string).write_pdf()

# ---------------------------------------------------------------------------
# Generador DOCX
# ---------------------------------------------------------------------------

def generate_docx(context: dict, df_potencias, figs: dict | None = None) -> bytes:
    """
    Genera un archivo Word (.docx) directamente desde los datos (no desde HTML).
    Devuelve los bytes del archivo.
    """
    doc = Document()
    azul = "17365D"
    azul_rgb = RGBColor(0x17, 0x36, 0x5D)
    verde_rgb = RGBColor(0x15, 0x80, 0x3D)

    section = doc.sections[0]
    section.top_margin = Inches(0.65)
    section.bottom_margin = Inches(0.65)
    section.left_margin = Inches(0.72)
    section.right_margin = Inches(0.72)

    style = doc.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(10)
    for style_name in ("Title", "Heading 1", "Heading 2"):
        heading_style = doc.styles[style_name]
        heading_style.font.name = "Arial"
        heading_style.font.color.rgb = azul_rgb

    def set_cell_fill(cell, color):
        tc_pr = cell._tc.get_or_add_tcPr()
        shading = tc_pr.find(qn("w:shd"))
        if shading is None:
            shading = OxmlElement("w:shd")
            tc_pr.append(shading)
        shading.set(qn("w:fill"), color)

    def set_cell_margins(cell, top=90, start=100, bottom=90, end=100):
        tc_pr = cell._tc.get_or_add_tcPr()
        tc_mar = tc_pr.first_child_found_in("w:tcMar")
        if tc_mar is None:
            tc_mar = OxmlElement("w:tcMar")
            tc_pr.append(tc_mar)
        for margin, value in (
            ("top", top), ("start", start),
            ("bottom", bottom), ("end", end),
        ):
            node = tc_mar.find(qn(f"w:{margin}"))
            if node is None:
                node = OxmlElement(f"w:{margin}")
                tc_mar.append(node)
            node.set(qn("w:w"), str(value))
            node.set(qn("w:type"), "dxa")

    def add_level_heading(text):
        table = doc.add_table(rows=1, cols=1)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        cell = table.cell(0, 0)
        set_cell_fill(cell, "FFEDD5")
        set_cell_margins(cell, top=120, start=160, bottom=120, end=160)
        run = cell.paragraphs[0].add_run(text)
        run.bold = True
        run.font.name = "Arial"
        run.font.size = Pt(16)
        run.font.color.rgb = RGBColor(0x9A, 0x34, 0x12)
        return table

    # ---- Cabecera común de informes epowerapp ----
    cabecera = doc.add_table(rows=1, cols=2)
    cabecera.alignment = WD_TABLE_ALIGNMENT.CENTER
    celda_titulo = cabecera.cell(0, 0)
    titulo_p = celda_titulo.paragraphs[0]
    titulo_run = titulo_p.add_run(context.get("titulo") or "Informe")
    titulo_run.bold = True
    titulo_run.font.name = "Arial"
    titulo_run.font.size = Pt(22)
    titulo_run.font.color.rgb = azul_rgb
    if context.get("subtitulo"):
        sub_p = celda_titulo.add_paragraph(context["subtitulo"])
        sub_p.runs[0].font.color.rgb = RGBColor(0x53, 0x65, 0x79)
    firma_p = celda_titulo.add_paragraph()
    firma_run = firma_p.add_run(
        f"Realizado por {context.get('realizado_por') or '—'} · "
        f"Fecha de realización: "
        f"{context.get('fecha_realizacion') or context.get('fecha') or '—'}"
    )
    firma_run.bold = True
    firma_run.font.size = Pt(9)
    firma_run.font.color.rgb = RGBColor(0x53, 0x65, 0x79)
    if context.get("logo"):
        try:
            logo_data = base64.b64decode(context["logo"].split(",", 1)[1])
            logo_p = cabecera.cell(0, 1).paragraphs[0]
            logo_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            logo_p.add_run().add_picture(
                io.BytesIO(logo_data), width=Inches(1.55)
            )
        except Exception:
            pass

    borde = doc.add_paragraph()
    borde.paragraph_format.space_after = Pt(10)
    p_bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "24")
    bottom.set(qn("w:color"), azul)
    p_bdr.append(bottom)
    borde._p.get_or_add_pPr().append(p_bdr)

    objeto_p = doc.add_paragraph()
    objeto_p.paragraph_format.space_after = Pt(10)
    objeto_p.add_run("Objeto del informe: ").bold = True
    objeto_p.add_run(
        context.get("objeto")
        or "Analizar y optimizar las potencias contratadas del suministro."
    )

    ficha = doc.add_table(rows=3, cols=4)
    ficha.style = "Table Grid"
    ficha.alignment = WD_TABLE_ALIGNMENT.CENTER
    datos_ficha = [
        ("Cliente", context.get("cliente"), "NIF / CIF", context.get("nif")),
        ("Dirección", context.get("direccion"), "CUPS", context.get("cups")),
        ("ATR", context.get("peaje"), "Periodo analizado", context.get("periodo_datos")),
    ]
    for fila, datos in enumerate(datos_ficha):
        for columna, valor in enumerate(datos):
            celda = ficha.cell(fila, columna)
            celda.text = str(valor or "—")
            set_cell_margins(celda)
            if columna in (0, 2):
                set_cell_fill(celda, "EEF4F8")
                run = celda.paragraphs[0].runs[0]
                run.bold = True
                run.font.color.rgb = azul_rgb
    doc.add_paragraph()

    add_level_heading("Nivel 1 · Resultado y propuesta")
    doc.add_paragraph()
    kpi_table = doc.add_table(rows=2, cols=4)
    kpi_table.style = "Table Grid"
    kpi_table.alignment = WD_TABLE_ALIGNMENT.CENTER

    headers = ["Coste actual", "Coste optimizado", "Ahorro estimado", "Ahorro"]
    values  = [
        context["coste_tp_potcon"],
        context["coste_tp_potopt"],
        context["ahorro_opt"],
        context["ahorro_opt_porc"],
    ]
    for i, (h, v) in enumerate(zip(headers, values)):
        hcell = kpi_table.cell(0, i)
        hcell.text = h
        set_cell_fill(hcell, "EEF4F8")
        header_run = hcell.paragraphs[0].runs[0]
        header_run.bold = True
        header_run.font.color.rgb = azul_rgb
        value_cell = kpi_table.cell(1, i)
        value_cell.text = v
        value_run = value_cell.paragraphs[0].runs[0]
        value_run.bold = True
        value_run.font.size = Pt(13)
        if i >= 2:
            value_run.font.color.rgb = verde_rgb
        set_cell_margins(hcell)
        set_cell_margins(value_cell, top=120, bottom=120)

    doc.add_paragraph()

    doc.add_heading("Potencias contratadas y propuesta optimizada", level=2)
    cols = list(df_potencias.columns)
    data_table = doc.add_table(rows=1 + len(df_potencias), cols=len(cols))
    data_table.style = "Table Grid"
    data_table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for i, col in enumerate(cols):
        cell = data_table.cell(0, i)
        cell.text = str(col)
        set_cell_fill(cell, azul)
        run = cell.paragraphs[0].runs[0]
        run.bold = True
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    for row_number, (_, row) in enumerate(df_potencias.iterrows(), start=1):
        for col_idx, val in enumerate(row):
            cell = data_table.cell(row_number, col_idx)
            cell.text = str(val)
            if row_number % 2 == 0:
                set_cell_fill(cell, "F7F9FB")

    doc.add_paragraph()

    add_level_heading("Nivel 2 · Análisis económico")
    doc.add_paragraph()
    graficos_nombres = [
        ("Resumen de costes", "graf_resumen"),
        ("Ahorro estimado", "graf_ahorro"),
        ("__NIVEL_3__", ""),
        ("Costes mensuales", "graf_costes_potcon"),
        ("Costes por periodos", "graf_costes_pot_periodos"),
    ]
    for nombre, key in graficos_nombres:
        if nombre == "__NIVEL_3__":
            add_level_heading("Nivel 3 · Detalle y trazabilidad")
            doc.add_paragraph()
            continue
        doc.add_paragraph(nombre).runs[0].bold = True
        fig = (figs or {}).get(key)
        imagen_contexto = context.get(key, "")
        if "base64," in imagen_contexto:
            try:
                datos_b64 = imagen_contexto.split("base64,", 1)[1].split('"', 1)[0]
                doc.add_picture(
                    io.BytesIO(base64.b64decode(datos_b64)),
                    width=Inches(5.5),
                )
            except Exception:
                doc.add_paragraph(
                    f"[Gráfico '{nombre}' no disponible en este entorno]"
                )
        elif fig is not None:
            try:
                if hasattr(fig, "to_image"):
                    png_bytes = fig.to_image(format="png", width=900, height=450, scale=1.5)
                elif hasattr(fig, "savefig"):
                    buf = io.BytesIO()
                    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120)
                    buf.seek(0)
                    png_bytes = buf.read()
                else:
                    png_bytes = None
                if png_bytes:
                    doc.add_picture(io.BytesIO(png_bytes), width=Inches(5.5))
            except Exception:
                doc.add_paragraph(f"[Gráfico '{nombre}' no disponible en este entorno]")
        else:
            doc.add_paragraph(f"[Gráfico '{nombre}' no disponible]")
        doc.add_paragraph()

    footer_p = doc.add_paragraph(
        "Informe elaborado con los datos y costes regulados disponibles en "
        "epowerapp. Revisa los datos del suministro antes de entregar el documento."
    )
    footer_p.paragraph_format.space_before = Pt(12)
    for run in footer_p.runs:
        run.font.size = Pt(8)
        run.font.color.rgb = RGBColor(0x65, 0x75, 0x8B)

    out_buf = io.BytesIO()
    doc.save(out_buf)
    out_buf.seek(0)
    return out_buf.read()


# ---------------------------------------------------------------------------
# Preparación común y generación bajo demanda
# ---------------------------------------------------------------------------

def preparar_informe(
    graf_costes_potcon,
    graf_resumen,
    coste_tp_potcon: float,
    coste_tp_potopt: float,
    ahorro_opt: float,
    ahorro_opt_porc: float,
    df_potencias,
    graf_ahorro,
    graf_costes_pot_periodos,
    logo_path: str | None = None,
    titulo: str = "Informe de Optimización de Potencias",
    subtitulo: str = "",
    realizado_por: str = "",
    cliente: str = "",
    cups: str = "",
    peaje: str = "",
    periodo_datos: str = "",
    nif: str = "",
    direccion: str = "",
    fecha_realizacion: str = "",
    objeto: str = "",
    template_path: str = "templates/informe.html",
) -> dict:
    """Prepara una sola vez el contexto, los gráficos y la vista HTML."""
    context = build_context(
        graf_costes_potcon=graf_costes_potcon,
        graf_resumen=graf_resumen,
        coste_tp_potcon=coste_tp_potcon,
        coste_tp_potopt=coste_tp_potopt,
        ahorro_opt=ahorro_opt,
        ahorro_opt_porc=ahorro_opt_porc,
        df_potencias=df_potencias,
        graf_ahorro=graf_ahorro,
        graf_costes_pot_periodos=graf_costes_pot_periodos,
        logo_path=logo_path,
        titulo=titulo,
        subtitulo=subtitulo,
        realizado_por=realizado_por,
        cliente=cliente,
        cups=cups,
        peaje=peaje,
        periodo_datos=periodo_datos,
        nif=nif,
        direccion=direccion,
        fecha_realizacion=fecha_realizacion,
        objeto=objeto,
    )
    return {
        "context": context,
        "html": generate_html(context, template_path),
        "df_potencias": df_potencias.copy(),
    }


def generar_formato_informe(preparado: dict, formato: str):
    """Genera solo el formato solicitado reutilizando el trabajo preparado."""
    formato = formato.lower()
    if formato == "html":
        return preparado["html"]
    if formato == "pdf":
        return generate_pdf(preparado["html"])
    if formato == "docx":
        return generate_docx(
            preparado["context"],
            preparado["df_potencias"],
            figs=None,
        )
    raise ValueError(f"Formato de informe no soportado: {formato}")


# ---------------------------------------------------------------------------
# Función compatible: genera los tres formatos de una vez
# ---------------------------------------------------------------------------

def generar_informe(
    graf_costes_potcon,
    graf_resumen,
    coste_tp_potcon: float,
    coste_tp_potopt: float,
    ahorro_opt: float,
    ahorro_opt_porc: float,
    df_potencias,
    graf_ahorro,
    graf_costes_pot_periodos,
    logo_path: str | None = None,
    titulo: str = "Informe de Optimización de Potencias",
    subtitulo: str = "",
    realizado_por: str = "",
    cliente: str = "",
    cups: str = "",
    peaje: str = "",
    periodo_datos: str = "",
    nif: str = "",
    direccion: str = "",
    fecha_realizacion: str = "",
    objeto: str = "",
    template_path: str = "templates/informe.html",
) -> dict:
    """
    Genera los tres formatos del informe y devuelve un dict con las claves:
        - "html"  → str  (HTML completo)
        - "pdf"   → bytes
        - "docx"  → bytes

    Uso en Streamlit:
        resultado = generar_informe(...)
        st.download_button("Descargar PDF",  resultado["pdf"],  "informe.pdf",  "application/pdf")
        st.download_button("Descargar Word", resultado["docx"], "informe.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        st.download_button("Descargar HTML", resultado["html"].encode(), "informe.html", "text/html")
    """
    preparado = preparar_informe(
        graf_costes_potcon=graf_costes_potcon,
        graf_resumen=graf_resumen,
        coste_tp_potcon=coste_tp_potcon,
        coste_tp_potopt=coste_tp_potopt,
        ahorro_opt=ahorro_opt,
        ahorro_opt_porc=ahorro_opt_porc,
        df_potencias=df_potencias,
        graf_ahorro=graf_ahorro,
        graf_costes_pot_periodos=graf_costes_pot_periodos,
        logo_path=logo_path,
        titulo=titulo,
        subtitulo=subtitulo,
        realizado_por=realizado_por,
        cliente=cliente,
        cups=cups,
        peaje=peaje,
        periodo_datos=periodo_datos,
        nif=nif,
        direccion=direccion,
        fecha_realizacion=fecha_realizacion,
        objeto=objeto,
        template_path=template_path,
    )
    return {
        formato: generar_formato_informe(preparado, formato)
        for formato in ("html", "pdf", "docx")
    }
