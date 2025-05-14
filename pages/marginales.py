import streamlit as st
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta
import time
from backend_marginales import obtener_marginales, download_esios_id, graf_1, graf_2, color_map
import plotly.express as px



from utilidades import generar_menu

if not st.session_state.get('usuario_autenticado', False):
    st.switch_page('epowerapp.py')

    
generar_menu()

fecha_hoy = date.today()    #date. fecha de hoy, en formato aaaa-mm-dd
numdia_fechahoy = fecha_hoy.day   #integer. lo usamos para un write del último día registrado del mes en curso
meses = ["TODOS","enero", "febrero", "marzo", "abril", "mayo", "junio","julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]    #listado de meses a elegir
mes_fecha_hoy = meses[fecha_hoy.month] #str. devuelve el mes en curso p.e. 'agosto' a partir de fecha_hoy y un indice relacionado con la lista meses
meses_selectbox = meses[:fecha_hoy.month+1] #lista str. listado meses para el selectbox

tec_seleccionadas_iniciales = ['RE','TCC','HI','BG']   #multiselect por defecto

#obtenemos los parámetros para llamar a la función obtener_marginales
mes_num = meses.index(mes_fecha_hoy)
#print (mes_num)
fecha_ini = date(fecha_hoy.year, mes_num, 1).strftime('%Y-%m-%d')


print(fecha_ini)
fecha_fin = (date(fecha_hoy.year, mes_num, 1) + relativedelta(months=1) - relativedelta(days=1)).strftime('%Y-%m-%d')
print(fecha_fin)
#print(fecha_ini)
#print(fecha_fin)




##OBTENER MARGINALES DEL MES EN CURSO
#parametros pasadoS a la función obtener_marginales
mes_str = f"{mes_num:02d}"  
año_str = fecha_hoy.strftime('%Y')  #parametro pasado a la función obtener_marginales
dia_fin_str = fecha_fin[-2:]    #parametro pasado a la función obtener_marginales
print(mes_str,año_str,dia_fin_str)

#llamada a la funcion
mes_str='03'
año_str='2025'
dia_fin_str='31'
fecha_ini = f'{año_str}-{mes_str}-01'
fecha_fin = f'{año_str}-{mes_str}-{dia_fin_str}'


df_tecmarg_mesactual = obtener_marginales(mes_str, año_str, dia_fin_str)
df_tecmarg_mesactual['fecha'] = pd.to_datetime(df_tecmarg_mesactual['fecha']).dt.date
df_tecmarg_mesactual['hora'] = df_tecmarg_mesactual['hora'].astype(int)
#print (df_tecmarg_mesactual)
#st.write(df_tecmarg_mesactual)

##OBTENER SPOT 
#parámetros pasados a la API REE. Las fechas ini y fin ya están definidas

id='600'
agrupacion='hour'
#llamada a la funcion
df_spot_mesactual = download_esios_id(id, fecha_ini, fecha_fin, agrupacion)
df_spot_mesactual['fecha'] = pd.to_datetime(df_spot_mesactual['fecha']).dt.date
df_spot_mesactual['hora'] = df_spot_mesactual['hora'].astype(int)
df_spot_mesactual['value'] = pd.to_numeric(df_spot_mesactual['value'], errors='coerce')
#st.write(df_spot_mesactual)

##COMBINAMOS MARGINALES Y SPOT DEL MES EN CURSO  
df_spotmarg_write=pd.merge(df_tecmarg_mesactual,df_spot_mesactual,on=['fecha','hora'])
#df_spotmarg_write['fecha']=pd.to_datetime(df_spotmarg_write['fecha']).dt.date
df_spotmarg_write['fecha']=pd.to_datetime(df_spotmarg_write['fecha'])
#st.write(df_spotmarg_write)

##LEEMOS EL CSV CON LOS HISTÓRICOS
historicos=pd.read_csv('local_bbdd/powerapp_marginales.csv',sep=';')
#historicos['fecha'] = pd.to_datetime(historicos['fecha'], format='%d/%m/%Y').dt.strftime('%Y-%m-%d') 
#historicos['fecha'] = pd.to_datetime(historicos['fecha'], format='%d/%m/%Y')
historicos['fecha'] = pd.to_datetime(historicos['fecha'])
historicos['value'] = historicos['value'].astype(str)
historicos['value'] = historicos['value'].str.replace(',', '.', regex=False)
historicos['value'] = pd.to_numeric(historicos['value'], errors='coerce')
historicos['hora'] = historicos['hora'].astype(int)
historicos=historicos[['fecha','hora','tecnologia','value']]
#st.write(historicos)

##ACTUALIZAMOS LOS HISTÓRICOS CON LOS DATOS DEL MES EN CURSO, ELIMINANDO LOS DUPLICADOS Y GUARDANDO LOS DATOS
update_historicos=pd.concat([historicos,df_spotmarg_write],ignore_index=True)
update_historicos = update_historicos.drop_duplicates(subset=['fecha', 'hora','tecnologia'], keep='last')
update_historicos.to_csv('local_bbdd/powerapp_marginales.csv',sep=";", index=False)
#st.write(update_historicos)

##ABRIMOS EL CSV PARA TRATAR LOS DATOS Y PREPARAMOS UN DATAFRAME DE PARTIDA
df_spotmarg_read=pd.read_csv('local_bbdd/powerapp_marginales.csv',sep=";")
df_spotmarg=df_spotmarg_read.copy()
#df_spotmarg=df_spotmarg[df_spotmarg['tecnologia'] != 'II'] #esto es porque se cuelan registros de Portugal?
df_spotmarg['fecha']=pd.to_datetime(df_spotmarg['fecha'], errors='coerce') #, dayfirst=True)
#st.write(df_spotmarg)
df_spotmarg['hora'] = df_spotmarg['hora'].astype(str).astype(int)
df_spotmarg = df_spotmarg.dropna(subset=['fecha'])
df_spotmarg['mes']=df_spotmarg['fecha'].dt.month
df_spotmarg['año']=df_spotmarg['fecha'].dt.year
#st.write(df_spotmarg)



col1,col2=st.columns([0.30,0.70])
with col1:
    st.subheader('Visualización',divider='rainbow')
    if 'ultimo_registro' not in st.session_state:
        st.session_state['ultimo_registro'] = df_spotmarg['fecha'].iloc[-1]
    ultimo_registro=st.session_state['ultimo_registro'].strftime('%d.%m.%Y')
    mensaje = f"Se dispone de datos hasta el **{ultimo_registro}**"
    st.markdown(mensaje, unsafe_allow_html=True)

    col11,col12=st.columns(2)
    with col11:
        #CUIDADO QUE HEMOS FORZADO EL INDICE DE LA LISTA A 2, QUE ES 2024!!!!!!!
        año_seleccionado=st.selectbox('Selecciona el año a visualizar',options=['2022','2023','2024','2025'],index=3)
        año_seleccionado=int(año_seleccionado)
        if año_seleccionado < 2025:
            meses_selectbox=meses
        else:
            mes_seleccionado=meses_selectbox.index(mes_fecha_hoy)
            mes_seleccionado=2
            meses_selectbox = ['TODOS', 'enero', 'febrero', 'marzo']
    with col12:
        #mes_seleccionado=st.selectbox('Selecciona el mes a visualizar',options=meses_selectbox,index=meses.index(mes_fecha_hoy))
        #mes_seleccionado=st.selectbox('Selecciona el mes a visualizar',options=meses_selectbox,index=meses_selectbox.index(mes_fecha_hoy))
        mes_seleccionado=st.selectbox('Selecciona el mes a visualizar',options=meses_selectbox,index=2)
        
    if mes_seleccionado=="TODOS":
        df_spotmarg_filtro=df_spotmarg[df_spotmarg['año'] == año_seleccionado]
    
    else:
        df_spotmarg_filtro=df_spotmarg[(df_spotmarg['mes']==meses.index(mes_seleccionado)) & (df_spotmarg['año'] == año_seleccionado)]
    
    ##DATAFRAME DE TECNOLOGIAS Y SUS PRECIOS FILTRADO POR MES Y POR AÑO
    df_spotmarg_filtro=df_spotmarg_filtro.dropna()
    ##DATAFRAME CON PRECIOS MEDIOS DE LAS TECNOLOGIAS
    df_medias_tecmarg=df_spotmarg_filtro.groupby('tecnologia')['value'].mean().reset_index() #las visualizamos en st.metric
    #st.write(df_medias_tecmarg)

    ##DATAFRAME SOLO SPOT PARA VISUALIZAR EN GRAFICO Y METRIC
    df_spot_horario = df_spotmarg_filtro.drop_duplicates(subset=['fecha', 'hora'], keep='last')
    media_spot=df_spot_horario['value'].mean()
    df_spot_horario=df_spot_horario.groupby('hora')['value'].mean().reset_index() #medias horarias del spot a visualizar en grafico
    #st.write(df_spot_horario)
    df_spot_horario_tabla=df_spot_horario
    
    media_spot_texto=f'{media_spot:.2f}'    #visualizado en st.metric
        
    ##DATAFRAME CON PRECIOS MEDIOS DE CADA TECNOLOGIA, POR HORAS. DATOS PARA GRAFICO 1
    df_spotmarg_horario=df_spotmarg_filtro.groupby(['hora','tecnologia'])['value'].mean().reset_index()
    df_spotmarg_horario['media_movil'] = df_spotmarg_horario.groupby('tecnologia')['value'].transform(lambda x: x.rolling(window=2, min_periods=1).mean())
    df_spotmarg_horario_tabla=df_spotmarg_horario.set_index(['hora'])

    df_spotmarg_horario_correl=df_spotmarg_horario.copy()
    #st.write(df_spotmarg_horario)

    ##DATAFRAMES CON RESUMEN DE HORAS MARGINALES POR TECNOLOGIA
    #En el sumatorio, saldrán más horas de las que tiene el mes. No importa.
    df_conteo_tec=df_spotmarg_filtro['tecnologia'].value_counts()
    #st.write(df_conteo_tec)
    
    ##DATAFRAME PARA EL GRÁFICO 2. PORCENTAJES HORARIOS DE CADA TECNOLOGIA
    df_conteo_tec_horario = df_spotmarg_filtro.groupby(['hora', 'tecnologia']).size().reset_index(name='conteo')
    total_por_hora = df_conteo_tec_horario.groupby('hora')['conteo'].transform('sum')
    df_conteo_tec_horario['porcentaje_hora'] = (df_conteo_tec_horario['conteo'] / total_por_hora) * 100
    df_conteo_tec_horario_tabla=df_conteo_tec_horario.drop(columns=['conteo']).set_index(['hora'])
    #st.write(df_conteo_tec_horario)

    ##DATAFRAME CON LOS PORCENTAJES TOTALES DE LAS HORAS MARCADAS
    conteo_total_tec = df_conteo_tec_horario.groupby('tecnologia')['conteo'].sum().reset_index()
    total_conteos = conteo_total_tec['conteo'].sum()
    conteo_total_tec['porcentaje_total'] = (conteo_total_tec['conteo'] / total_conteos) * 100
    df_porc_tec=conteo_total_tec.set_index(['tecnologia'])
    df_porc_tec=df_porc_tec.drop(columns=['conteo'])
    #st.write(df_porc_tec)



    


    
    
    tecnologias=df_spotmarg_filtro['tecnologia'].unique()
    #print(tecnologias)
    tec_seleccionadas = st.multiselect('Selecciona las tecnologías a visualizar', options = tecnologias, default = tec_seleccionadas_iniciales)
    #print(tec_seleccionadas)
    df_spotmarg_horario=df_spotmarg_horario[df_spotmarg_horario['tecnologia'].isin(tec_seleccionadas)]
    
    
    altura_graf1=st.slider('Selecciona la altura del gráfico',min_value=400,max_value=1000,value=800, step=50)
    
    st.subheader('Datos resumen',divider='rainbow')
    st.caption('Se muestran las medias de precios en €/MWh, correlación con omie de cada tecnología y % de horas marcadas de las principales tecnologías')

    pt_coefrel=pd.pivot_table(df_spotmarg_horario_correl, index='hora', columns='tecnologia',values='value',aggfunc='mean')
    pt_coefrel=pt_coefrel.reset_index()
    df_spot_horario_values=df_spot_horario[['value']]
    #st.write(pt_coefrel)
    #st.write(df_spot_horario)
    pt_coefrel = pd.merge(pt_coefrel, df_spot_horario[['hora', 'value']], on='hora', how='left')
    #pt_coefrel=pd.concat([pt_coefrel,df_spot_horario],axis=1)
    #st.write(pt_coefrel)
    #st.write(df_spot_horario)

    tech_columns = ['RE', 'HI', 'BG', 'TCC', 'value']
    correlation_matrix = pt_coefrel[tech_columns].corr()
    correlations = correlation_matrix['value'][:-1]
    #st.write(correlations)
    
    
    
    
    col11,col12,col13=st.columns(3)
    with col11:
        st.write('Precio medio €/MWh')
        df_medias_tecmarg=df_medias_tecmarg[df_medias_tecmarg['tecnologia'].isin(tec_seleccionadas_iniciales)]
        df_medias_tecmarg['tecnologia'] = pd.Categorical(df_medias_tecmarg['tecnologia'], categories=tec_seleccionadas_iniciales, ordered=True)
        df_medias_tecmarg=df_medias_tecmarg.sort_values(by='tecnologia')
        #st.write(df_medias_tecmarg)
        
        for _, row in df_medias_tecmarg.iterrows():
            tecnologia = row['tecnologia']
            media_tecmarg = row['value']
            media_tecmarg_texto = f"{media_tecmarg:.2f}"  # Formatear el valor a 2 decimales
            st.metric(label=tecnologia, value=media_tecmarg_texto)
        
        st.metric('OMIE', value=media_spot_texto)
        #st.write(df_medias_tecmarg)
    with col12:
        st.write('Correlación')
        correlations=correlations[correlations.index.isin(tec_seleccionadas_iniciales)]
        correlations=correlations.sort_values(ascending=False)
        correlations=correlations.reindex(tec_seleccionadas_iniciales)
        for tec, corr in correlations.items():
            st.metric(label=f'{tec}',value=f'{corr:.2f}')
    with col13:
        st.write('% Horas marcadas')
        df_porc_tec=df_porc_tec[df_porc_tec.index.isin(tec_seleccionadas_iniciales)]
        
        df_porc_tec=df_porc_tec.sort_values(by=df_porc_tec.columns[0],ascending=False)
        
        df_porc_tec=df_porc_tec.reindex(tec_seleccionadas_iniciales)
        #st.write(df_porc_tec)
        for tec, porc in df_porc_tec[df_porc_tec.columns[0]].items():
            porc_value = float(porc)  # Asegúrate de que porc sea un número simple
            st.metric(label=f'{tec}',value=f'{porc:.1f}%')

    st.subheader('Tablas de datos',divider='rainbow')
    tab1, tab2, tab3 =st.tabs(['Datos de la gráfica 1','Datos de la gráfica 2','Datos de la gráfica 3'])
    with tab1:
        st.text('Precios marginales s/tecnología: medias horarias')
        st.dataframe(data=df_spotmarg_horario_tabla)
    with tab2:
        st.text('% de horas marginales: medias horarias')
        st.dataframe(data=df_conteo_tec_horario_tabla)
            
with col2:
    st.info((
            "En este primer gráfico tienes la media de OMIE por horas para el año y mes seleccionado. "
            "Las líneas de puntos son los precios medios de cada tecnología marginal relevante. Es una interesante forma de observar correlaciones entre OMIE y los precios marginales de cada tecnología. "
            "Puedes seleccionar al gusto las tecnologías marginales a representar. "
    ), icon="ℹ️")
    graf1=graf_1(df_spotmarg_horario,df_spot_horario,altura_graf1)
    st.plotly_chart(graf1)
    st.info((
            "La idea del gráfico inferior se la debo a **Rodrigo García Ruiz**. "
            "A diferencia del anterior, en este se representa OMIE (eje secundario) junto con el porcentaje de las horas marcadas según tecnología marginal. "
            "Es una ocurrente forma de determinar la frontera de las inframarginales."
    ), icon="ℹ️")
    graf2=graf_2(df_conteo_tec_horario,df_spot_horario,altura_graf1)
    st.plotly_chart(graf2)



#st.write(df_spotmarg_filtro)
df_spotmarg_no_duplicados=df_spotmarg_filtro.copy()
df_spotmarg_no_duplicados=df_spotmarg_no_duplicados.drop_duplicates(subset=['fecha','hora'], keep='first')
df_spotmarg_no_duplicados['fecha']=pd.to_datetime(df_spotmarg_no_duplicados['fecha'])
df_spotmarg_no_duplicados['hora'] = pd.to_numeric(df_spotmarg_no_duplicados['hora'], errors='coerce') - 1
#df_spotmarg_no_duplicados['hora']=df_spotmarg_no_duplicados['hora']-1
df_spotmarg_no_duplicados['fecha_hora'] = df_spotmarg_no_duplicados['fecha'] + pd.to_timedelta(df_spotmarg_no_duplicados['hora'], unit='h')
with tab3:
    st.dataframe(df_spotmarg_no_duplicados, hide_index=True)
#print(df_spotmarg_no_duplicados.dtypes)







graf_marginales=px.bar(df_spotmarg_no_duplicados, x='fecha_hora',y='value',
                    color='tecnologia',
                    color_discrete_map=color_map,
                    title='Precios y tecnologías marginales (€/MWh)',
                    labels={'value':'€/MWh'}
                    )
graf_marginales.update_layout(
        xaxis=dict(
            rangeslider=dict(
                visible=True,
                bgcolor='rgba(173, 216, 230, 0.5)',
                
            ),
            showgrid=True,
            dtick='86400000',
              
            rangeselector=dict(
                buttons=list([
                    dict(count=7, label="1w", step="day", stepmode="backward"),
                    dict(count=1, label="1m", step="month", stepmode="backward"),
                    dict(count=3, label="3m", step="month", stepmode="backward"),
                    dict(step="all")  # Visualizar todos los datos
                ]),
                #visible=True
            )
        ),
        bargap=.1,
        title=dict(
            x=.5,
            xanchor='center'
        )
        
    )

st.write(graf_marginales)