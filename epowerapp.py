import streamlit as st
import base64

st.set_page_config(
    page_title="ePowerAPP",
    page_icon="⚡",
    layout='wide',
    #layout='centered',
    #initial_sidebar_state='collapsed'
    initial_sidebar_state='expanded'
)

c1, c2, c3 = st.columns(3)

with c2:
    st.title(':orange[e]PowerAPP© TOTALPOWER')
    st.header('Todo lo que necesitas para energizarte.')
    st.caption("Copyright by Jose Vidal 2024-2025 :ok_hand:")
    

    with open("images/banner.png", "rb") as f:
        data = f.read()
        encoded = base64.b64encode(data).decode()

    # Mostrar la imagen con estilo
    st.markdown(f"""
        <style>
            .img-redonda {{
                border-radius: 10px;
                width: 100%;
                height: auto;
                box-shadow: 0px 4px 10px rgba(0,0,0,0.2);
            }}
        </style>
        <img src="data:image/png;base64,{encoded}" class="img-redonda"/>
    """, unsafe_allow_html=True)


    st.text('')
    st.text('')
    st.info('¡¡Bienvenido a mi :orange[e]PowerAPP!! \n\n'
            'En ningún sitio vas a encontrar herramientas personalizables para obtener información de los mercados mayoristas y minoristas de electricidad y gas.\n'
            'No dudes en contactar para comentar errores detectados o proponer mejoras en la :orange[e]PowerAPP'
            , icon="ℹ️")
    
    
    
    acceso = st.button('🚀 Acceder a la aplicación', type='primary', use_container_width=True)
    #acceso_simulindex = st.button('🔮 Acceder a **Simulindex**', type='primary', use_container_width=True)
    if acceso:
        st.switch_page('pages/powerapps.py')
    #if acceso_simulindex:
    #   st.switch_page('pages/simulindex.py')
    # bla
    


    