import streamlit as st
from utilidades import generar_menu


generar_menu()

if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')


col11,col12,col13,col14,col15=st.columns(5)
with col11:
    st.subheader('Curva de carga',divider='rainbow')
    st.page_link("pages/curvadecarga.py", label="Curva de carga: Analiza el suministro", icon="🕒", use_container_width=True)
    st.image('images/curvadecarga.jpg')
with col12:
    st.subheader('Término de potencia',divider='rainbow')
    st.page_link("pages/opt2.py", label="Optimiza y verifica el término de potencia", icon="🎯", use_container_width=True)
    st.image('images/optimizacion.jpg')

with col13:
    st.subheader('Telemindex',divider='rainbow')
    st.page_link("pages/telemindex.py", label="Telemindex: Analiza el mercado minorista de indexado", icon="📈", use_container_width=True)
    st.image('images/telemindex.jpg')

with col14:
    st.subheader('Simulindex',divider='rainbow')
    st.page_link("pages/simulindex.py", label="Simulindex: Simula los precios futuros de indexado", icon="🔮", use_container_width=True)
    st.image('images/simulindex.jpg')

with col15:
    st.subheader('Compara fijo vs PVPC',divider='rainbow')
    st.page_link("pages/fijovspvpc.py", label="Fijovspvpc: Compara a ver quién gana", icon="⚖️", use_container_width=True)
    st.image('images/fijovspvpc.jpg')
    

col21,col22,col23,col24,col25=st.columns(5)
with col21:
    st.subheader('Autoconsumo: Excedentes',divider='rainbow')
    st.page_link("pages/excedentes.py", label="Compara tus excedentes en fijo con el mercado regulado", icon="💰", use_container_width=True)
    st.image('images/excedentes.jpg')
with col22:
    st.subheader('Escala Cavero-Vidal',divider='rainbow')
    st.page_link("pages/escalacv.py", label="Escala Cavero-Vidal: OMIE a todo color", icon="📊")
    st.image('images/escalacv.jpg')
with col23:
    st.subheader('Demanda y Consumo',divider='rainbow')
    st.page_link("pages/demanda.py", label="Analiza la demanda sin y con autoconsumo", icon="🏭")
    st.image('images/demanda.jpg')

with col24:
    st.subheader('Infografías REData',divider='rainbow')
    st.page_link('pages/redata_potgen.py', label = 'Tecnologías de generación', icon = "🔀")
    st.image('images/redata.jpg')
with col25:
    st.subheader('Gas & Furious',divider='rainbow')
    st.page_link("pages/mibgas.py", label="Pasado, presente y futuro del gas", icon="🔥", use_container_width=True)
    st.image('images/gas.jpg')

col31,col32,col33,col34,col35=st.columns(5)
with col31:
    st.subheader('Tecnologías Marginales',divider='rainbow')
    st.page_link('pages/marginales.py', label = 'Tecnologías que casan precio marginal', icon = "⚡️")
    st.image('images/marginales.jpg')
with col32:
    url10 = "https://spo2425-josevidal.streamlit.app/"
    st.subheader('SPO: Super Power OMIE',divider='rainbow')
    st.write("Gana el [MVPStarPower](%s) del año y bate a OMIP!" % url10)
    st.image('images/spo.jpg')

