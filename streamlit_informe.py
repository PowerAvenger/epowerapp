"""
streamlit_informe.py
--------------------
Fragmento listo para pegar en tu app de Streamlit.

Coloca este bloque donde quieras mostrar el botón de descarga de informes.
Asume que en ese punto ya tienes disponibles todas las variables listadas.
"""

import streamlit as st
from report_generator import generar_informe

# ── Aquí ya tienes tus variables (las que genera tu app) ──────────────────
#
#   graf_costes_potcon      → Figure matplotlib/plotly
#   graf_resumen            → Figure matplotlib/plotly
#   coste_tp_potcon         → float  (€)
#   coste_tp_potopt         → float  (€)
#   ahorro_opt              → float  (€)
#   ahorro_opt_porc         → float  (%)
#   df_potencias            → pd.DataFrame
#   graf_ahorro             → Figure matplotlib/plotly
#   graf_costes_pot_periodos → Figure matplotlib/plotly
#
# ─────────────────────────────────────────────────────────────────────────

st.divider()
st.subheader("📄 Generar informe")

# Opciones que el usuario puede personalizar
col_titulo, col_logo = st.columns([3, 1])
with col_titulo:
    titulo    = st.text_input("Título del informe",    "Informe de Optimización de Potencias")
    subtitulo = st.text_input("Subtítulo (opcional)",  "")
with col_logo:
    logo_file = st.file_uploader("Logo (PNG/JPG)", type=["png", "jpg", "jpeg"])

# Guarda el logo en un fichero temporal si el usuario lo sube
logo_path = None
if logo_file is not None:
    import tempfile, pathlib
    suffix = pathlib.Path(logo_file.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(logo_file.read())
        logo_path = tmp.name

# Botón de generación
if st.button("🚀 Generar informe", type="primary"):
    with st.spinner("Generando informe..."):
        try:
            resultado = generar_informe(
                graf_costes_potcon       = graf_costes_potcon,
                graf_resumen             = graf_resumen,
                coste_tp_potcon          = coste_tp_potcon,
                coste_tp_potopt          = coste_tp_potopt,
                ahorro_opt               = ahorro_opt,
                ahorro_opt_porc          = ahorro_opt_porc,
                df_potencias             = df_potencias,
                graf_ahorro              = graf_ahorro,
                graf_costes_pot_periodos = graf_costes_pot_periodos,
                logo_path                = logo_path,
                titulo                   = titulo,
                subtitulo                = subtitulo,
                template_path            = "templates/informe.html",  # ajusta si es necesario
            )

            st.success("✅ Informe generado correctamente")

            # ── Botones de descarga ───────────────────────────────────
            col1, col2, col3 = st.columns(3)

            with col1:
                st.download_button(
                    label        = "⬇️ Descargar PDF",
                    data         = resultado["pdf"],
                    file_name    = "informe_potencias.pdf",
                    mime         = "application/pdf",
                    use_container_width=True,
                )
            with col2:
                st.download_button(
                    label        = "⬇️ Descargar Word",
                    data         = resultado["docx"],
                    file_name    = "informe_potencias.docx",
                    mime         = "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )
            with col3:
                st.download_button(
                    label        = "⬇️ Descargar HTML",
                    data         = resultado["html"].encode("utf-8"),
                    file_name    = "informe_potencias.html",
                    mime         = "text/html",
                    use_container_width=True,
                )

            # Vista previa en Streamlit (opcional)
            with st.expander("👁️ Vista previa HTML"):
                st.components.v1.html(resultado["html"], height=700, scrolling=True)

        except Exception as e:
            st.error(f"Error al generar el informe: {e}")
            raise  # elimina esta línea en producción
