import streamlit as st
from datetime import datetime, date
from backend_redata_potgen import (
    leer_json, tablas_diario, tablas_salida, 
    graficar_bolas,  graficar_new_fc, graficar_FU, graficar_mix, graficar_mix_queso,
    gen_evol, graficar_evol, calc_efi, graficar_efi_evol
)

from utilidades import generar_menu

generar_menu()

#constantes para la descarga de REData. son la de la #category = 'generacion' usadas en la API
widget_gen = 'estructura-generacion'
widget_pot = 'potencia-instalada'


file_id_gen = '1IvYqrGzSvf5KDwCcl7e7KTKGVcvw9LLb'
file_id_pot = '1UYWjjl7cnEOZSNitMdyWRQj5Vj27bSo4'

#horas equivalentes máximas anuales de cada tecnología. Visualización en la ePowerAPP
horas_eq_max = {
    'Ciclo combinado' : 6000,
    'Nuclear' : 8000,
    'Solar fotovoltaica' : 2000,
    'Eólica' : 2200,
    'Hidráulica' : 4000,
    'Cogeneración' : 7000,
    #'Turbinación bombeo' : 2000
}
code_heqmax = f'''Horas equivalentes máximas: {horas_eq_max}'''

# Usado para el select box de años
lista_años = [2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018]

# Usado para filtrar las tecnologías que vamos a visualizar
tec_filtro = ['Ciclo combinado', 'Hidráulica', 'Nuclear', 'Solar fotovoltaica', 'Eólica', 'Cogeneración']
colores = ["#555867", "#4be4ff", "#ff2b2b", "#ff8700", "#09ab3b", "#6d3fc0"]
colores_tec = {tec: colores[i % len(colores)] for i, tec in enumerate(tec_filtro)}
colores_tec['Resto'] = '#FFFFE0'

# usado para seleccionar el año en df_out (se obtiene df_out_filtrado)
if 'año_seleccionado' not in st.session_state:
    st.session_state.año_seleccionado = 2025
# usado en el multiselect FC y %mix EVOL    
if 'tec_seleccionadas' not in st.session_state:
    st.session_state.tec_seleccionadas = ['Solar fotovoltaica', 'Eólica', 'Hidráulica']
# usado para opciones de visualizacion en gráfico 5 
if 'opcion_evol' not in st.session_state:
    st.session_state.opcion_evol = 'FC'


with st.spinner('Cargando datos de generación...'):
    df_in_gen = leer_json(file_id_gen, widget_gen)
with st.spinner('Cargando datos de potencia instalada...'):
    df_in_pot = leer_json(file_id_pot, widget_pot)
with st.spinner('Tratando los datos...'):
    df_out = tablas_diario(df_in_gen, df_in_pot, horas_eq_max)



fecha_hoy = datetime.now().date()
año_hoy = fecha_hoy.year
dia_hoy = fecha_hoy.day
ultima_fecha_registro = df_out['fecha'].iloc[-1].date()
def es_bisiesto(año):
    return (año % 4 == 0 and año % 100 != 0) or (año % 400 == 0)
año_bisiesto = es_bisiesto(año_hoy)

if año_bisiesto:
    horas_año = 8784
else:
    horas_año = 8760

horas_2025_transcurridas = ((ultima_fecha_registro - date(2025, 1, 1)).days + 1) * 24
coef_horas = horas_año / horas_2025_transcurridas
print(f'coef horas =  {coef_horas}')

df_out_filtrado = df_out[df_out['año'] == st.session_state.año_seleccionado]
df_out_bolas, df_out_fc, df_out_fu, df_out_mix  = tablas_salida(df_out_filtrado, tec_filtro) 

graf_bolas = graficar_bolas(df_out_bolas, colores_tec)
graf_fc = graficar_new_fc(df_out_fc, colores_tec)
graf_fu = graficar_FU(df_out_fu, colores_tec)
graf_mix = graficar_mix(df_out_mix, colores_tec)
graf_mix_queso = graficar_mix_queso(df_out_mix, colores_tec)

df_fc_evol = gen_evol(df_out)
if not df_fc_evol.empty:
    graf_fc_evol = graficar_evol(df_fc_evol, colores_tec, 'FC')
    graf_mix_evol = graficar_evol(df_fc_evol, colores_tec, '%_mix_gen')

df_efi_evol = calc_efi(df_out, coef_horas)
graf_efi = graficar_efi_evol(df_efi_evol)



with st.sidebar:
    st.title('Infografías REData :orange[e]PowerAPP©')
    st.caption("Copyright by Jose Vidal :ok_hand:")
    #st.write("Visita mi página de [PowerAPPs](%s) con un montón de utilidades" % url_apps)
    #st.markdown(f"Visita mi página de [ePowerAPPs]({url_apps}) con un montón de utilidades. Deja tus comentarios y propuestas en mi perfil de [Linkedin]({url_linkedin}) - ¡Sígueme en [Bluesky]({url_bluesky})!")
    st.info('Todos los datos son elaborados a partir de REData / Generación / Estructura generación y Potencia instalada (sistema eléctrico nacional todas las tecnologías). Rango temporal: Diario, siendo los datos agrupados por años.',icon="ℹ️")
    

st.sidebar.selectbox('Selecciona un año', options = lista_años, key = 'año_seleccionado')
st.sidebar.markdown(f'Último día del que se disponen datos: {ultima_fecha_registro}')
st.sidebar.text ('Datos para el Gráfico 3 - Factor de Uso')
st.sidebar.code(code_heqmax, language='python')

st.sidebar.radio('Selecciona el párametro a visualizar en el Gráfico 5:', ['FC', '%_mix'], key = 'opcion_evol')
st.sidebar.multiselect('Selecciona y compara tecnologías', options = tec_filtro, key = 'tec_seleccionadas')

# VISUALIZACION EN EL TABLERO++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
c1, c2, c3 = st.columns(3)

#st.header('Tecnologías de generación', divider='rainbow')
#zona_mensajes = st.empty()
#st.selectbox('Selecciona un año', options = lista_años, key = 'año_seleccionado')
#st.markdown(f'Último día del que se disponen datos: {ultima_fecha_registro}')

#zona_grafica = st.empty()

help_graf1 = (
    "En el eje X, tienes la potencia instalada de cada tecnología.\n\n"
    "En el eje Y tienes la generación de cada tecnología para el año seleccionado y hasta el último día disponible.\n\n "
    "Imagina la potencia instalada de cada tecnología generando al 100% todas las horas.\n\n"
    "La relación entre la generación real y la generación 'total' determina el **:orange[Factor de Capacidad (FC)]**.\n\n"
    "Las :orange[horas equivalentes] representan el tiempo que una tecnología habría estado generando a plena capacidad. En principio, cuanto más grande la burbuja, mejor."
)
help_graf2 = (
    "Para el año seleccionado, se representan los FC diarios y medio para cada tecnología de generación.\n\n"
    "Las tecnologías están ordenadas de mayor a menor FC medio.\n\n"
    "Cada punto representa el FC diario de cada tecnología de generación"
)
help_graf3 = (
    "Existe un límite teórico de generación en función del recurso disponible. No es lo mismo la disponibilidad de una central nuclear que la de un parque eólico.\n\n"
    "Aquí es cuando entra en juego el :orange[FU o Factor de Uso] (en %), siendo éste un dato bastante subjetivo (ver :orange[horas equivalentes máximas] en la barra lateral).\n\n"
    "El FU es interesante porque nos da una idea del aprovechamiento **relativo** de dicho recurso disponible para cada una de las tecnologías de generación.\n\n"
)
help_graf4 = (
    "Este gráfico está relacionado con el eje Y de las bolas. Generación pura y dura, con dos opciones de visualización.\n\n"
    "Fíjate que cuanto más arriba esté la bola, el sector o barra son más grandes.\n\n"
)
help_graf5 = (
    "Estos gráficos representan la evolución del FC y el % de generación medio anual para cada tecnología.\n\n"
    "Nótese que el año 2025 sólo dispone datos hasta el día de hoy.\n\n"
)
help_graf6 = (
    "Representa la relación entre la GENERACION y la POTENCIA INSTALADA. Es como un FC, pero de todo el sistema eléctrico nacional.\n\n"
    "A mayor relación, mayor eficiencia. El año 2025 es una proyección en base a la generación total a fecha de hoy.\n\n"
)
            

with c1:
    #GRAFICO 1
    st.subheader(f'Gráfico 1: Factor de Capacidad medio en **:orange[{st.session_state.año_seleccionado}]**', divider = 'rainbow', help=help_graf1)
    #with st.expander(f'Explicación ℹ️'):
    #    st.info('En el eje Y tienes la generación de cada tecnología para el año seleccionado y hasta el último día disponible. En el eje X tienes la potencia instalada de cada tecnología.\n'
    #            'La relación entre ambas magnitudes determina el **:orange[Factor de Capacidad (FC)]**. \n'   
    #            'Las horas equivalentes es el tiempo que hubiera estado generando una tecnología a tope de su capacidad instalada. En principio, cuanto más gorda la bola, mejor.'
    #            , icon="ℹ️"
    #    )
    #st.caption(f'Factor de Capacidad y horas equivalentes: Generación vs Potencia Instalada. Año {st.session_state.año_seleccionado}')
    st.write(graf_bolas)

    #GRAFICO 2
    st.subheader(f'Gráfico 2: Factores de Capacidad diarios en **:orange[{st.session_state.año_seleccionado}]**', divider = 'rainbow', help=help_graf2)
    #with st.expander(f'Explicación ℹ️'):
    #    st.info('Para el año seleccionado, se representan los FC diarios y medio para cada tecnología de generación.\n'
    #            'Las tecnologías están ordenadas de mayor a menor FC medio. \n'
    #            'Cada punto representa el FC diario de cada tecnología de generación'
    #            , icon="ℹ️"
    #    )
    #st.caption(f'Factores de Capacidad diarios y medio anual. Año {st.session_state.año_seleccionado}')
    st.write(graf_fc)

with c2:
    #GRAFICO 3
    st.subheader(f'Gráfico 3: Factor de Uso en **:orange[{st.session_state.año_seleccionado}]**', divider = 'rainbow', help=help_graf3)
    #with st.expander(f'Explicación ℹ️'):
    #    st.info('Existe un límite teórico de generación en función del recurso disponible. No es lo mismo la disponibilidad de una central nuclear que la de un parque eólico.\n'
    #        'Aquí es cuando entra en juego el :orange[FU o Factor de Uso] (en %), siendo éste un dato bastante subjetivo.\n'
    #        'El FU es interesante porque nos da una idea del aprovechamiento **relativo** de dicho recurso disponible para cada una de las tecnologías de generación. \n'
    #        , icon="ℹ️"
    #    )
    #st.code(code_heqmax, language='python')
    #st.caption(f'Factor de Uso: Según horas equivalentes máximas. Año {st.session_state.año_seleccionado}')
    st.write(graf_fu)

    #GRAFICO 4
    st.subheader(f'Gráfico 4: Mix de generación en **:orange[{st.session_state.año_seleccionado}]**', divider = 'rainbow', help=help_graf4)
    #with st.expander(f'Explicación ℹ️'):
    #    st.info('Este gráfico está relacionado con el eje Y de las bolas. Generación pura y dura, con dos opciones de visualización.\n'
    #        'Fíjate que cuanto más arriba esté la bola, el sector o barra son más grandes.\n'
    #        , icon="ℹ️"
    #    )
    tipo_mix = st.toggle('Cambiar de tipo de gráfico')
    espacio_mix = st.empty()
    if tipo_mix:
        espacio_mix.write(graf_mix)
    else:
        espacio_mix.write(graf_mix_queso)

with c3:
    st.subheader('Gráfico 5: FC y Mix de generación Evolution', divider = 'rainbow', help=help_graf5)
    #with st.expander(f'Explicación ℹ️'):
    #    st.info('Estos gráficos representan la evolución del FC y el % de generación medio anual para cada tecnología.\n'
    #        'Nótese que el año 2025 sólo dispone datos hasta el día de hoy.\n'
    #        , icon="ℹ️"
    #    )
    #st.multiselect('Selecciona y compara tecnologías', options = tec_filtro, key = 'tec_seleccionadas')
    if not df_fc_evol.empty:
        if st.session_state.opcion_evol == 'FC':
            st.write(graf_fc_evol)
        else:
            st.write(graf_mix_evol)
    else:
        st.warning('Selecciona al menos una tecnología', icon = '⚠️') 

    st.subheader('Gráfico 6: Eficiencia del sistema', divider = 'rainbow', help=help_graf6)
    #st.info('Representa la relación entre la GENERACION y la POTENCIA INSTALADA. Es como un FC, pero de todo el sistema eléctrico nacional.\n'
    #    'A mayor relación, mayor eficiencia. El año 2025 es una proyección en base a la generación total a fecha de hoy.\n'
    #    , icon="ℹ️"
    #)
    st.write(graf_efi)
