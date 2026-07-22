import streamlit as st

from utilidades import generar_menu


generar_menu()

if (
    not st.session_state.get("usuario_autenticado", False)
    and not st.session_state.get("usuario_free", False)
):
    st.switch_page("epowerapp.py")


MODULOS = [
    ("Curva de carga", "pages/curvadecarga.py", "Curva de carga: Analiza el suministro", "🕒", "images/curvadecarga.jpg", None),
    ("Lector de facturas", "pages/factura.py", "Analiza y verifica tu factura eléctrica", "🧾", "images/lector_facturas.jpg", None),
    ("Término de potencia", "pages/opt2.py", "Optimiza y verifica el término de potencia", "🎯", "images/optimizacion.jpg", None),
    ("Telemindex", "pages/telemindex.py", "Analiza el mercado minorista de indexado", "📈", "images/telemindex.jpg", None),
    ("Simulindex", "pages/simulindex.py", "Simula los precios futuros de indexado", "🔮", "images/simulindex.jpg", None),
    ("Compara fijo vs PVPC", "pages/fijovspvpc.py", "Compara a ver quién gana", "⚖️", "images/fijovspvpc.jpg", None),
    ("Autoconsumo: Excedentes", "pages/excedentes.py", "Compara tus excedentes en fijo con el mercado regulado", "💰", "images/excedentes.jpg", None),
    ("Escala Cavero-Vidal", "pages/escalacv.py", "OMIE a todo color", "📊", "images/escalacv.jpg", None),
    ("Demanda y Consumo", "pages/demanda.py", "Analiza la demanda sin y con autoconsumo", "🏭", "images/demanda.jpg", None),
    ("Infografías REData", "pages/redata_potgen.py", "Tecnologías de generación", "🔀", "images/redata.jpg", None),
    ("Balkoning Solar FV", "pages/balkoning_solar.py", "¿El autoconsumo pisero es para todos?", "🏊‍♂️", "images/balkoning.jpg", None),
    ("Gas & Furious", "pages/mibgas.py", "Pasado, presente y futuro del gas", "🔥", "images/gas.jpg", None),
    ("Tecnologías Marginales", "pages/marginales.py", "Tecnologías que casan precio marginal", "⚡️", "images/marginales.jpg", None),
    ("Optimización RDL 7/2026", "pages/opt2_rdl.py", "Sácale todo el provecho a la flexibilización de potencias", "⚡️", "images/opt rdl 7 2026.jpg", None),
    ("SPO: Super Power OMIE", None, "Gana el MVPStarPower del año y bate a OMIP", None, "images/spo.jpg", "https://spo-epowerapp.streamlit.app/"),
    ("Interpolados qh REE", None, "Cuando la interpolación REE apenas tiene impacto", None, "images/interpolados.jpg", "https://interpolados-epowerapp.streamlit.app/"),
]


for inicio in range(0, len(MODULOS), 5):
    columnas = st.columns(5)
    for columna, modulo in zip(columnas, MODULOS[inicio:inicio + 5]):
        titulo, pagina, etiqueta, icono, imagen, url = modulo
        with columna:
            st.subheader(titulo, divider="rainbow")
            if pagina:
                st.page_link(
                    pagina,
                    label=etiqueta,
                    icon=icono,
                    use_container_width=True,
                )
            else:
                st.markdown(f"[{etiqueta}]({url})")
            st.image(imagen)
