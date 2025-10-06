import streamlit as st
import base64
import time

st.set_page_config(
    page_title="ePowerAPP",
    page_icon="⚡",
    layout='wide',
    #layout='centered',
    #initial_sidebar_state='collapsed'
    initial_sidebar_state='expanded'
)

c1, c2, c3 = st.columns(3)

if 'acceso' not in st.session_state:
    st.session_state.acceso = ""


with c2:
    zona_predator = st.empty()
    zona_objetos = st.empty()
    
    with zona_objetos.container():
        st.title(':orange[e]PowerAPP© ⚡️:rainbow[TOTALPOWER]⚡️')
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
        
        url_linkedin = "https://www.linkedin.com/posts/josefvidalsierra_epowerapps-spo2425-telemindex-activity-7281942697399967744-IpFK?utm_source=share&utm_medium=member_deskto"
        #url_bluesky = "https://bsky.app/profile/poweravenger.bsky.social"
        st.markdown(f"Contacta por privado en mi perfil de [Linkedin]({url_linkedin}) para obtener un código de pago")
        st.text_input('Introduce el código de acceso', type='password', key='acceso')
        if st.session_state.acceso == st.secrets['KEY_ACCESS']:

            acceso = st.button('🚀 Acceder a la aplicación', type='primary', use_container_width=True, disabled=False)
            st.session_state.usuario_autenticado = True
        else:
            acceso = st.button('🚀 Acceder a la aplicación', type='primary', use_container_width=True, disabled=True)

        #acceso_simulindex = st.button('🔮 Acceder a **Simulindex**', type='primary', use_container_width=True)
    if acceso:
        zona_objetos.empty()
        zona_predator.image('images/predator.png')
        #zona_predator.video('images/predator1.mp4', autoplay=True)
        time.sleep(2)
        st.switch_page('pages/powerapps.py')
    


    


    