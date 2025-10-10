import streamlit as st
from datetime import datetime, date
from backend_redata_potgen import (
    leer_json, tablas_diario, tablas_salida, 
    graficar_bolas,  graficar_new_fc, graficar_FU, graficar_mix, graficar_mix_queso,
    gen_evol, graficar_evol, calc_efi, graficar_efi_evol, graficar_gen_diaria
)

from utilidades import generar_menu

if not st.session_state.get('usuario_autenticado', False):
    st.switch_page('epowerapp.py')

generar_menu()

#constantes para la descarga de REData. son la de la #category = 'generacion' usadas en la API
widget_gen = 'estructura-generacion'
widget_pot = 'potencia-instalada'

# identificadores de los sheets con los históricos de generación y potencia instalada
file_id_gen = st.secrets['FILE_ID_GEN']
file_id_pot = st.secrets['FILE_ID_POT']

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
    #st.session_state.tec_seleccionadas = ['Solar fotovoltaica', 'Eólica', 'Hidráulica']
    st.session_state.tec_seleccionadas = ['Solar fotovoltaica', 'Eólica']

# usado para opciones de visualizacion en gráfico 5 
#if 'opcion_evol' not in st.session_state:
#    st.session_state.opcion_evol = 'FC'

# descargamos datos históricos y montamos una tabla con TODOS los datos diarios tratados (%mix, FC, heq, FU, heqmax)
with st.spinner('Cargando datos de generación...'):
    df_in_gen = leer_json(file_id_gen, widget_gen)
with st.spinner('Cargando datos de potencia instalada...'):
    df_in_pot = leer_json(file_id_pot, widget_pot)
with st.spinner('Tratando los datos...'):
    #df con TODOS los datos diarios
    df_diario_all = tablas_diario(df_in_gen, df_in_pot, horas_eq_max)



fecha_hoy = datetime.now().date()
año_hoy = fecha_hoy.year
dia_hoy = fecha_hoy.day
ultima_fecha_registro = df_diario_all['fecha'].iloc[-1].date()
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



df_año_filtrado = df_diario_all[df_diario_all['año'] == st.session_state.año_seleccionado]

#'''CODIGO AÑADIDO PARA INTENTAR FILTRAR LOS AÑOS HASTA FECHA SIMILAR A LA DEL ÚLTIMO REGISTRO DEL AÑO EN CURSO'''
# Obtener día y mes del último registro
dia_ult = ultima_fecha_registro.day
mes_ult = ultima_fecha_registro.month

# Año actual (por ejemplo, 2025)
año_actual = ultima_fecha_registro.year

# Filtro adicional si el toggle está activado y el año seleccionado es anterior al actual
if st.session_state.get('dias_equiparados', True) and st.session_state.año_seleccionado < año_actual:
    df_año_filtrado = df_año_filtrado[
        (df_año_filtrado['mes_num'] < mes_ult) |
        ((df_año_filtrado['mes_num'] == mes_ult) & (df_año_filtrado['fecha'].dt.day <= dia_ult))
    ]

# usado para los gráficos 5,6,9, donde comparamos todos los años
df_out_equiparado = df_diario_all.copy()

if st.session_state.get('dias_equiparados', True):
    df_out_equiparado = df_out_equiparado[
        (df_out_equiparado['mes_num'] < mes_ult) |
        ((df_out_equiparado['mes_num'] == mes_ult) & (df_out_equiparado['fecha'].dt.day <= dia_ult))
    ]


# CÓDIGO AÑADIDO PARA PODER FILTRAR POR MES
nombres_meses = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}
meses_disponibles = sorted(df_año_filtrado['mes_num'].unique())
meses_nombres = ["TODOS"] + [nombres_meses[m] for m in meses_disponibles]

# Aplicar filtro solo si no es 'TODOS'
if st.session_state.get('mes_seleccionado_redata', 'TODOS') != "TODOS":
    num_mes_seleccionado = {v: k for k, v in nombres_meses.items()}[st.session_state.mes_seleccionado_redata]
    df_año_filtrado = df_año_filtrado[df_año_filtrado['mes_num'] == num_mes_seleccionado]
    df_out_equiparado = df_out_equiparado[df_out_equiparado['mes_num'] == num_mes_seleccionado]

print('df out equiparado')
print(df_out_equiparado)

#dfs con el año seleccionado
df_out_bolas, df_out_fc, df_out_fu, df_out_mix  = tablas_salida(df_año_filtrado, tec_filtro) 

graf_bolas = graficar_bolas(df_out_bolas, colores_tec)
graf_fc = graficar_new_fc(df_out_fc, colores_tec)
graf_fu = graficar_FU(df_out_fu, colores_tec)
graf_mix = graficar_mix(df_out_mix, colores_tec)
graf_mix_queso = graficar_mix_queso(df_out_mix, colores_tec)

df_fc_mix_evol = gen_evol(df_out_equiparado)
#df_fc_evol = gen_evol(df_out)
#if not df_fc_evol.empty:
graf_fc_evol = graficar_evol(df_fc_mix_evol, colores_tec, 'FC')
graf_mix_evol = graficar_evol(df_fc_mix_evol, colores_tec, '%_mix_gen')
graf_gen_evol = graficar_evol(df_fc_mix_evol, colores_tec, 'gen_GWh')

#df_efi_evol = calc_efi(df_out, coef_horas)
df_efi_evol = calc_efi(df_out_equiparado, coef_horas)
graf_efi = graficar_efi_evol(df_efi_evol)

graf_gen_diaria = graficar_gen_diaria(df_año_filtrado, colores_tec)



with st.sidebar:
    st.header('Infografías REData', help=' ℹ️ Todos los datos son elaborados a partir de REData / Generación / Estructura generación y Potencia instalada (sistema eléctrico nacional todas las tecnologías).')
    #st.caption("Copyright by Jose Vidal :ok_hand:")
    #st.write("Visita mi página de [PowerAPPs](%s) con un montón de utilidades" % url_apps)
    #st.markdown(f"Visita mi página de [ePowerAPPs]({url_apps}) con un montón de utilidades. Deja tus comentarios y propuestas en mi perfil de [Linkedin]({url_linkedin}) - ¡Sígueme en [Bluesky]({url_bluesky})!")
    #st.info('Todos los datos son elaborados a partir de REData / Generación / Estructura generación y Potencia instalada (sistema eléctrico nacional todas las tecnologías).',icon="ℹ️")
    
    st.write(f'Datos disponibles hasta el {ultima_fecha_registro.strftime("%d.%m.%Y")}')
    st.toggle('Equiparar años anteriores al actual', key = 'dias_equiparados', value = True)
    st.selectbox('Selecciona un año (gráficos 1 a 4)', options = lista_años, key = 'año_seleccionado')
    
    st.selectbox('Selecciona un mes (todos los gráficos)', options = meses_nombres, key = 'mes_seleccionado_redata')
        
    st.text ('Datos para el Gráfico 3 - Factor de Uso')
    st.code(code_heqmax, language='python')

    #st.radio('Selecciona el párametro a visualizar en el Gráfico 5:', ['FC', '%_mix'], key = 'opcion_evol')
    st.multiselect('Selecciona y compara tecnologías', options = tec_filtro, key = 'tec_seleccionadas')
    tipo_mix = st.toggle('Cambiar de tipo de gráfico 4')

# VISUALIZACION EN EL TABLERO++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
c1, c2, c3 = st.columns(3)

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
    "Este gráfico representa la evolución del FC Factor de Capacidad medio anual para cada tecnología.\n\n"
    "Este valor variará según si el año seleccionado es completo o hasta el último día con registros del año en curso.\n\n"
)
help_graf6 = (
    "Este gráfico representa la evolución del peso en el mix de generación medio para cada tecnología.\n\n"
    "Este valor variará según si el año seleccionado es completo o hasta el último día con registros del año en curso.\n\n"
)
help_graf7 = (
    "Representa la relación entre la GENERACION y la POTENCIA INSTALADA. Es como un FC, pero de todo el sistema eléctrico nacional.\n\n"
    "A mayor relación, mayor eficiencia. El año 2025 es una proyección en base a la generación total a fecha de hoy.\n\n"
)

#definir texto secundario de los gráficos
#Si el toogle 'dias_equiparados' es True y mes = TODOS, indicar 'Hasta el día {ultimo_dia_registro} con formato dd.mm
#Si el toogle 'dias_equiparados' es True y mes = cualquiera menos el mes actual (mes_ult), indicar 'Mes de {mes_nombre}
#Si el toogle 'dias_equiparados' es True y mes =  mes actual (mes_ult), indicar 'Mes de {mes_nombre} hasta el {ultimo_dia_registro} con formato dd.mm'
#Si el toogle 'dias_equiparados' es False y mes = TODOS, indicar 'Hasta el día 31.12'
#Si el toogle 'dias_equiparados' es False y mes = cualquiera menos el mes actual (mes_ult), indicar 'Mes de {mes_nombre}  
#Si el toogle 'dias_equiparados' es False y mes =  mes actual (mes_ult), indicar 'Mes de {mes_nombre} hasta el {ultimo_dia_registro} con formato dd.mm'
#if st.session_state.get('dias_equiparados', True):
if st.session_state.año_seleccionado == año_actual:
    if st.session_state.mes_seleccionado_redata == 'TODOS':
        subtexto = f'Hasta el día {ultima_fecha_registro.strftime("%d")} de {nombres_meses[mes_ult]}'
    elif st.session_state.mes_seleccionado_redata == nombres_meses[mes_ult]:
        subtexto = f'Mes de {st.session_state.mes_seleccionado_redata} hasta el día {ultima_fecha_registro.strftime("%d")}'
    else:
        subtexto = f'Mes de {st.session_state.mes_seleccionado_redata}'
else:
    if st.session_state.dias_equiparados == True:
        if st.session_state.mes_seleccionado_redata == 'TODOS':
            subtexto = f'Hasta el día {ultima_fecha_registro.strftime("%d")} de {nombres_meses[mes_ult]}'
        elif st.session_state.mes_seleccionado_redata == nombres_meses[mes_ult]:
            subtexto = f'Mes de {st.session_state.mes_seleccionado_redata} hasta el día {ultima_fecha_registro.strftime("%d")}'
        else:
            subtexto = f'Mes de {st.session_state.mes_seleccionado_redata}'
    else:
        if st.session_state.mes_seleccionado_redata == 'TODOS':
            subtexto = f'Hasta el día 31 de diciembre'
        else:
            subtexto = f'Mes de {st.session_state.mes_seleccionado_redata}'



with c1:
    #GRAFICO 1
    st.subheader(f'Gráfico 1: Factor de Capacidad medio en **:orange[{st.session_state.año_seleccionado}]**', divider = 'rainbow', help=help_graf1)
    st.write(subtexto)
    st.write(graf_bolas)

    #GRAFICO 2
    st.subheader(f'Gráfico 2: Factores de Capacidad diarios en **:orange[{st.session_state.año_seleccionado}]**', divider = 'rainbow', help=help_graf2)
    st.write(subtexto)
    st.write(graf_fc)

    #GRAFICO 7
    st.subheader('Gráfico 7: Eficiencia del sistema', divider = 'rainbow', help=help_graf7)
    st.write(subtexto)
    st.write(graf_efi)

with c2:
    #GRAFICO 3
    st.subheader(f'Gráfico 3: Factor de Uso en **:orange[{st.session_state.año_seleccionado}]**', divider = 'rainbow', help=help_graf3)
    st.write(subtexto)
    st.write(graf_fu)

    #GRAFICO 4
    st.subheader(f'Gráfico 4: Mix de generación en **:orange[{st.session_state.año_seleccionado}]**', divider = 'rainbow', help=help_graf4)
    st.write(subtexto)
    #tipo_mix = st.toggle('Cambiar de tipo de gráfico')
    espacio_mix = st.empty()
    if tipo_mix:
        espacio_mix.write(graf_mix)
    else:
        espacio_mix.write(graf_mix_queso)
    
    #GRAFICO 8
    st.subheader(f'Gráfico 8: Generación diaria **:orange[{st.session_state.año_seleccionado}]**', divider = 'rainbow', help=help_graf3)
    st.write(subtexto)
    st.write(graf_gen_diaria)

with c3:
    st.subheader('Gráfico 5: Evolución del FC Factor de Capacidad', divider = 'rainbow', help=help_graf5)
    st.write(subtexto)
    if not df_fc_mix_evol.empty:
        st.write(graf_fc_evol)
    else:
        st.warning('Selecciona al menos una tecnología', icon = '⚠️') 

    st.subheader('Gráfico 6: Evolución del MIX de Generación', divider = 'rainbow', help=help_graf6)
    st.write(subtexto)
    if not df_fc_mix_evol.empty:
        st.write(graf_mix_evol)
    else:
        st.warning('Selecciona al menos una tecnología', icon = '⚠️') 
    
    st.subheader('Gráfico 9: Evolución de la Generación', divider = 'rainbow', help=help_graf6)
    st.write(subtexto)
    if not df_fc_mix_evol.empty:
        st.write(graf_gen_evol)
    else:
        st.warning('Selecciona al menos una tecnología', icon = '⚠️') 
    
