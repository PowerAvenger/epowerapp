import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import numpy as np

# LECTURA DE LOS JSON CON LOS DATOS DE ESTRUCTURA DE LA GENERACIÓN Y POTENCIA INSTALADA
@st.cache_data
def leer_json(file_id, widget):
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    response = requests.get(url)
    datos_json = response.json()
    
    column_mapping = {
        "estructura-generacion": {"valor": "gen_GWh_dia", "porcentaje": "porc_gen", "coef":1000},
        "potencia-instalada": {"valor": "pot_GW", "porcentaje": "porc_pot", "coef": 1000}
    }
    
    # Convertir a DataFrame
    df_in = pd.DataFrame(datos_json)
    df_in['fecha'] = pd.to_datetime(df_in['fecha'], utc=True).dt.tz_convert('Europe/Madrid').dt.tz_localize(None)
    df_in['mes_num'] = df_in['fecha'].dt.month
    df_in['año'] = df_in['fecha'].dt.year
    coef = column_mapping[widget]["coef"]
    df_in['valor'] = df_in['valor']/coef
    if widget in column_mapping:
        df_in.rename(columns={
            "valor": column_mapping[widget]["valor"],
            "porcentaje": column_mapping[widget]["porcentaje"]
        }, inplace=True)
    
    return df_in
    
     
# TABLA CON DATOS DIARIOS DE CADA TECNOLOGÍA
@st.cache_data
def tablas_diario(df_in_gen, df_in_pot, horas_eqmax):
    #montamos un dataframe de entrada con los datos de gen y pot. DIARIO
    df_out = pd.merge(df_in_gen, df_in_pot, on = ['mes_num', 'año','tecnologia'], how = 'left')
    df_out = df_out.drop(columns=['fecha_y']).rename(columns = {'fecha_x': 'fecha'})
    df_out['gen_GWh'] = df_out['gen_GWh_dia'] / 24
    df_out['FC'] = df_out['gen_GWh'] / df_out['pot_GW']
    df_out['horas_eq'] = round(df_out['gen_GWh_dia'] / df_out['pot_GW'], 1)
    coeficientes_heqmax = {
        'Nuclear': [0.0989, 0.0865, 0.0668, 0.0674, 0.0678, 0.0834, 0.0971, 0.0976, 0.0954, 0.0884, 0.0695, 0.0812],
        'Eólica': [0.0960, 0.1157, 0.1026, 0.0772, 0.0705, 0.0711, 0.0683, 0.0627, 0.0751, 0.0934, 0.0802, 0.0869],
        'Solar fotovoltaica': [0.0428, 0.0564, 0.0688, 0.0872, 0.1126, 0.1083, 0.1291, 0.1215, 0.0943, 0.0662, 0.0555, 0.0574],
        'Cogeneración': [0.1011, 0.0836, 0.0725, 0.0552, 0.0814, 0.0888, 0.0912, 0.0872, 0.0795, 0.0749, 0.0929, 0.0918],
        'Ciclo combinado': [0.0958, 0.0540, 0.0552, 0.0506, 0.0514, 0.0553, 0.0949, 0.1027, 0.0813, 0.0758, 0.1220, 0.1609],
        'Hidráulica': [0.1148, 0.0901, 0.1393, 0.1164, 0.0810, 0.0683, 0.0611, 0.0544, 0.0497, 0.0811, 0.0761, 0.0677]
    }
    def calcular_horas_eqmax(row):
        tec = row['tecnologia']
        if tec in horas_eqmax:
            heqmax = horas_eqmax[tec]
            mes = int(row['mes_num'])  # 1 a 12
            coef_mes = coeficientes_heqmax[tec][mes - 1]
            return heqmax * coef_mes / 30  # 30 días simplificados
        else:
            return None
    df_out['horas_eqmax'] = df_out.apply(calcular_horas_eqmax, axis=1)
    df_out['FU'] = round(df_out['horas_eq']/df_out['horas_eqmax'], 1)
    df_out.sort_values(by='fecha', inplace=True)
    df_out.rename(columns={'porc_gen':'%_mix_gen', 'porc_pot':'%_mix_pot'}, inplace=True)
    print('DF DIARIO TODOS LOS DIAS DESDE 2018')
    print (df_out)
    
    return df_out

# TABLAS RESUMEN DE TECNOLOGIAS PARA UN AÑO DETERMINADO+++++++++++++++++++++++++++++++++++++++++++++++++++++  
def tablas_salida(df, tec_filtro):
    #df es un df con los datos diarios del año seleccionado
    #tec_filtro son las tecnologías que se muestran
    
    #DATAFRAME PARA GRÁFICO FC DE DISPERSIÓN
    df_out_fc = df[df['tecnologia'].isin(tec_filtro)].copy()

    #tabla datos anual por tecnología. usada para grafico bolas, fu y mix    
    df_anual = df.groupby('tecnologia').agg({
        'gen_GWh_dia':'sum',
        'pot_GW':'mean',
        'FC':'mean',
        'horas_eq':'sum',
        'FU':'mean',
        'horas_eqmax':'sum',
        '%_mix_gen':'mean',
    }).reset_index()
    
    df_anual.rename(columns = {'gen_GWh_dia':'generacion_GWh'}, inplace = True)
    df_anual['horas_eq'] = df_anual['horas_eq'].astype(int)
    #eliminamos las filas de gen y pot total
    df_anual = df_anual[~df_anual['tecnologia'].isin(['Generación total', 'Potencia total'])]
    #calculamos totales de generacion y potencia
    gen_total = round(df_anual['generacion_GWh'].sum(), 1)
    pot_total = round(df_anual['pot_GW'].sum(), 1)
    
    #print ('df_anual')
    #print(df_anual)
    #print(df_anual['tecnologia'].unique())

    #creamos un df solo con las tecnologias seleccionadas
    df_anual_select = df_anual[df_anual['tecnologia'].isin(tec_filtro)].copy()
    df_anual_select['FNU'] = 1 - df_anual_select['FU']

    print ('df para visualización bolas, fc, fu y mix')
    print (df_anual_select)

    #DATAFRAMES PARA GRÁFICO DE BOLAS
    df_out_bolas = df_anual_select.sort_values(['FC'], ascending = False) 
    
    
    #añadimos columnas FC y %mix
    
    #df_out_ratio['FC'] = round(df_out_ratio['horas_eq'] / horas, 3)
    #df_out_ratio['%_mix'] = round(df_out_ratio['generacion_GWh'] / gen_total, 3)
    
    df_out_fu = df_anual_select.sort_values(['FU'], ascending=False)
    df_out_mix = df_anual_select.sort_values(['%_mix_gen'], ascending = False)

    #print (df_out_ratio_select_fc)
    #print (df_out_ratio_select_fu)

    #añadimos al mix 'resto' de tecnologías
    mix_tec_select = df_out_mix['%_mix_gen'].sum()
    mix_resto = round(1-mix_tec_select,3)
    gen_resto = round(gen_total-df_out_mix['generacion_GWh'].sum(), 1)
    pot_resto = pot_total-df_out_mix['pot_GW'].sum()
    nueva_fila = {
        'tecnologia': 'Resto',
        'generacion_GWh': gen_resto,
        'pot_GW': pot_resto,  # Opcional: si no aplica, puedo dejar como None
        'horas_eq': None,
        'FC': None,
        '%_mix_gen': mix_resto,
        'horas_eqmax': None,
        'FU': None
        }
    #print(pot_total,pot_resto)
    df_out_mix = pd.concat([df_out_mix, pd.DataFrame([nueva_fila])], ignore_index=True)

    #DATAFRAME PARA GRÁFICO MIX GENERACIÓN
    df_out_mix = df_out_mix.sort_values(['%_mix_gen'], ascending=False)
    #print ('df mix')
    #print (df_out_ratio_select_mix)

    
    
    
    
    print('df_out_new_fc')
    #print(df_out_fc)

    return df_out_bolas, df_out_fc, df_out_fu, df_out_mix #, df_out_ratio_select_mix, 

# GRAFICO 1. DE BOLAS --------------------------------------------------------------------------------------------
def graficar_bolas(df, colores_tecnologia):
    graf_bolas = px.scatter(df, x = 'pot_GW', y = 'generacion_GWh', size = 'horas_eq', 
        size_max = 100, color = df['tecnologia'], 
        hover_name = df['tecnologia'],
        color_discrete_map = colores_tecnologia,
        custom_data = df[['tecnologia', 'pot_GW', 'generacion_GWh', 'FC', 'horas_eq']],
        labels = {'generacion_GWh':'Generación (GWh)', 'pot_GW':'Potencia instalada (GW)'},
        )
    graf_bolas.update_traces(
        text = df['tecnologia'],  # Usa los índices (tecnologías) como texto
        textposition = 'middle center',
        hovertemplate = '<b>Tecnología: %{customdata[0]}</b><br><br>Potencia instalada (GW): %{customdata[1]:.1f}<br>Generación (GWh): %{customdata[2]:.0f}<br>FC: %{customdata[3]:.2f}<br>Horas equivalentes: %{customdata[4]:.0f}<extra></extra>',
        )
    graf_bolas.update_layout(
        legend=dict(
            title='',
            orientation='h',
            yanchor='top',
            y=1.1,
            xanchor='center',
            x=.5
        ),
        showlegend=True
        )
    graf_bolas.update_xaxes(
        showgrid=True
    )
    
    return graf_bolas


#NUEVO GRÁFICO 2. DISPERSIÓN FC--------------------------------------------------------------------------
def graficar_new_fc(df, color_tecnologia):

    medias_fc = df.groupby('tecnologia')['FC'].mean().reset_index()
    medias_fc = medias_fc.sort_values('FC', ascending = False)
    posiciones_base = {tec: i+1.0 for i, tec in enumerate(medias_fc['tecnologia'])}
    ancho_franja = 0.4
    def calcular_jitter(row):
        base = posiciones_base[row['tecnologia']]
        jitter = np.random.uniform(-ancho_franja / 2, ancho_franja / 2)
        return base + jitter
    df['x_jitter'] = df.apply(calcular_jitter, axis = 1)
    # Eje X con etiqueta personalizada
    nombres_cortos = {
        'Nuclear': 'Nuclear',
        'Hidráulica UGH': 'Hidráulica',
        'Ciclo combinado': 'Ciclo Comb.',
        'Gas Natural Cogeneración': 'Cogeneración',
        'Eólica terrestre': 'Eólica',
        'Solar fotovoltaica': 'Fotovoltaica'
    }

    graf = px.scatter(df, x = 'x_jitter', y = 'FC',
        color = 'tecnologia', color_discrete_map = color_tecnologia,
        custom_data = df[['tecnologia', 'pot_GW', 'gen_GWh_dia', 'FC', 'horas_eq', 'fecha']],
        labels = {'x_jitter':'Tecnología'},
        #animation_frame = 'datetime'
    )

    graf.update_traces(
        #text = df['tecnologia'],  # Usa los índices (tecnologías) como texto
        #textposition = 'middle center',
        hovertemplate = '<b>Tecnología: %{customdata[0]}</b><br><br>Potencia instalada (GW): %{customdata[1]:.1f}<br>Generación (GWh): %{customdata[2]:.0f}<br>FC: %{customdata[3]:.2f}<br>Horas equivalentes: %{customdata[4]:.0f}<br>Fecha: %{customdata[5]|%Y-%m-%d}<extra></extra>',
        )

    
    graf.update_layout(
        xaxis=dict(
            tickmode='array',
            # Extraer valores y textos ordenados por posición base
            tickvals = list(posiciones_base.values()),
            #ticktext = [nombres_cortos[tec] for tec in posiciones_base]
            ticktext = list(posiciones_base.keys())
        ),
        #width=1000,
        showlegend = False,
    )
    for _, row in medias_fc.iterrows():
        tecnologia = row['tecnologia']
        media_fc = row['FC']
        x_base = posiciones_base[tecnologia]
        color = color_tecnologia[tecnologia]
        color = 'yellow'
        # Limitar la línea horizontal a la franja de la tecnología
        graf.add_shape(
            type = 'line',
            x0 = x_base - ancho_franja / 2,
            x1 = x_base + ancho_franja / 2,
            y0 = media_fc,
            y1 = media_fc,
            line = dict(color=color, width=3),
            layer='above'
        )
        # Anotación con media FC en negro
        graf.add_annotation(
            x = x_base,
            y = media_fc,
            text = f"<b>{media_fc:.2f}",
            showarrow=False,
            yshift = 20,
            font=dict(color='yellow', size=20)
        )
    return graf




#GRÁFICO 3: SEGUNDO DE BARRAS. FU-----------------------------------------------------------------------------------------
def graficar_FU(df, colores_tecnologia):
    graf_FU=px.bar(df, x = 'FU', y = 'tecnologia',
        orientation = 'h',
        color = df['tecnologia'], 
        #hover_name=df_out_ratio_select_fu['tecnologia'],
        custom_data = df[['tecnologia', 'FC', 'horas_eq', 'FU', 'horas_eqmax']],
        color_discrete_map = colores_tecnologia,
        #width=1300,
        text_auto = True,
        text = 'FU'
    )

    graf_FU.update_traces(
        texttemplate='%{text:.1%}',
        textposition='inside',
        hovertemplate = '<b>Tecnología: %{customdata[0]}</b><br><br>FC: %{customdata[1]:.2f}<br>Horas equivalentes: %{customdata[2]:.0f}<br>FU: %{customdata[3]:.2f}<br>Horas equivalentes max: %{customdata[4]:.0f}<extra></extra>',
    )
    graf_FU.update_layout(
        xaxis_tickformat = '.0%',
        bargap = .4,
        showlegend = False,
        yaxis=dict(visible = True, title_text = None),
    )

    graf_FU.add_bar(
        x = df['FNU'],
        y = df['tecnologia'],
        orientation = 'h',
        marker_color = df['tecnologia'].map(colores_tecnologia),
        marker_opacity = 0.3,  # Mayor transparencia
        hoverinfo = 'skip',  # Opcional: no mostrar información de estas barras en hover
        showlegend = False
    )

    graf_FU.update_xaxes(
        showgrid = True
    )

    return graf_FU

# GRAFICO 4. MIX GENERACION EN BARRAS---------------------------------------------
def graficar_mix(df, colores_tecnologia):
    graf_mix = px.bar(df, x = '%_mix_gen', y = 'tecnologia',
        orientation = 'h',
        color = 'tecnologia', 
        #hover_name = 'tecnologia',
        custom_data = df[['tecnologia', 'pot_GW', 'generacion_GWh', '%_mix_gen']],
        color_discrete_map = colores_tecnologia,
        text_auto = True,
        text = '%_mix_gen'
        
        )
    graf_mix.update_traces(
        #formateamos el texto de las barras
        #texttemplate = '%{text:.1%}',
        #textposition = 'inside',  # Coloca el texto en el centro de las burbujas
        hovertemplate = '<b>Tecnología: %{customdata[0]}</b><br><br>Potencia media instalada (GW): %{customdata[1]:.1f}<br>Generación (GWh): %{customdata[2]:.0f}<br>% mix: %{customdata[3]:.2f%}<extra></extra>',
        
        #textfont=dict(size=12, color="black"),  # Tamaño y color del texto
        )
    graf_mix.update_layout(
        #title=dict(
        #    text='Aportación al mix de generación (%)',
        #    x=.5,
        #    xanchor='center',
        #),
        xaxis_tickformat = '.0%',
        bargap = .4,
        showlegend = False,
        yaxis = dict(visible = True, title_text = None),
    )

    graf_mix.update_xaxes(
        showgrid = True
    )
    return graf_mix

#GRAFICO 4. MIX GENERACION EN QUESO------------------------------------------
def graficar_mix_queso(df, colores_tecnologia):
    graf_mix_queso = px.pie(
        df, 
        names = 'tecnologia', 
        values = 'generacion_GWh',
        color = 'tecnologia',
        color_discrete_map = colores_tecnologia,
        #custom_data = df[['tecnologia', 'pot_GW', 'gen_GWh_dia', '%_mix']],
        hover_name = 'tecnologia',
        #hover_data = {'generacion_GWh': ':.0f'}, 
        hole = .4,
    )

    graf_mix_queso.update_traces(textinfo = 'percent+label',
        textposition = 'inside',
        insidetextorientation = 'horizontal',
        #hovertemplate = '<b>Tecnología: %{customdata[0]}</b><br><br>Potencia media instalada (GW): %{customdata[1]:.1f}<br>Generación (GWh): %{customdata[2]:.0f}<br>% mix: %{customdata[3]:.1f}<extra></extra>',
    )
    
    return graf_mix_queso




# NUEVO GRÁFICO DE EVOLUCION DE LOS FC Y % MIX GEN +++++++++++++++++++++++++++++++++++++++
def gen_evol(df_out_equiparado):
    #recibimos un df con valores diarios de todos los años. Depende del toogle, 
    df_in = df_out_equiparado.copy()
    #df_out_evol = df_out_evol[(df_out_evol['tecnologia'] == st.session_state.tec_select_1) | (df_out_evol['tecnologia'] == st.session_state.tec_select_2)]
    if not st.session_state.tec_seleccionadas:
        return pd.DataFrame(columns=['año', 'tecnologia', 'FC', '%_mix_gen'])
    
    df_out = df_in[df_in['tecnologia'].isin(st.session_state.tec_seleccionadas)]
    #df_out.rename(columns = {'porc_gen':'%_mix'}, inplace = True)
    
    print('df_out')
    #print(df_out)
    
    df_out2 = df_out.pivot_table(
        index = 'tecnologia',
        columns = 'año',
        values = ['FC', '%_mix_gen'],
        aggfunc = 'mean'
    )
    df_fc = df_out2['FC'].transpose().reset_index().rename(columns = {'index':'año'})
    df_fc = df_fc.melt(id_vars = 'año', var_name = 'tecnologia', value_name = 'FC')
    df_mix = df_out2['%_mix_gen'].transpose().reset_index().rename(columns = {'index':'año'})
    df_mix = df_mix.melt(id_vars = 'año', var_name = 'tecnologia', value_name = '%_mix_gen')
    df_out_evol = pd.merge(df_fc, df_mix, on = ['año', 'tecnologia'])
    df_out_evol['%_mix_gen'] = df_out_evol['%_mix_gen']*100
    
    print ('df_out_evol')
    print (df_out_evol)
    return df_out_evol

def graficar_evol(df, colores_tecnologia, param):
    graf_evol = px.line(df, x = 'año', y = param,
        color = 'tecnologia',
        color_discrete_map = colores_tecnologia,
        #barmode='group'
    )
    graf_evol.update_layout(
        legend=dict(
            title='',
            orientation='h',
            yanchor='top',
            y=1.1,
            xanchor='center',
            x=.5
        ),
        showlegend=True,
        xaxis = dict(tickmode = 'array'),
        #bargroupgap = 0.1
    )
    graf_evol.update_xaxes(
        showgrid = True
    )
    #graf_evol.update_yaxes(range = [0, 1])
    return graf_evol

# NUEVO GRÁFICO DE EVOLUCION DE LA EFICIENCIA DEL SISTEMA+++++++++++++++++++++++++++++++++++++++
def calc_efi(df, coef):

    df_in = df.copy()
    df_in = df_in[df_in['tecnologia'] != 'Generación total']
    #print(df_in)
        
    df_gen = df_in.groupby('año').agg({
        'gen_GWh_dia':'sum',
        #'pot_GW':'max'
    }).reset_index()
    df_gen.rename(columns={'gen_GWh_dia':'gen_GWh'}, inplace=True)
    df_pot_media = df_in.groupby(['año', 'tecnologia'])['pot_GW'].mean().reset_index()
    df_pot = df_pot_media.groupby('año')['pot_GW'].sum().reset_index(name='pot_GW')

    df_out = pd.merge(df_pot, df_gen, on='año')
    
    if not st.session_state.get('dias_equiparados', True):
        df_out.loc[df_out['año'] == 2025, 'gen_GWh'] *= coef

        horas_anuales = {
            2018: 365 * 24,  # 8760
            2019: 365 * 24,  # 8760
            2020: 366 * 24,  # 8784 (bisiesto)
            2021: 365 * 24,  # 8760
            2022: 365 * 24,  # 8760
            2023: 365 * 24,  # 8760
            2024: 366 * 24,  # 8784 (bisiesto)
            2025: 365 * 24   # 8760
        }
    
        df_out['gen_max'] = df_out['pot_GW'] * df_out['año'].map(horas_anuales)
    
    else:
        # Estás en modo truncado (dias_filtrados = True)
        dias_por_año = df_in.groupby('año')['fecha'].nunique().reset_index(name='dias')
        df_out = pd.merge(df_out, dias_por_año, on='año')
        df_out['gen_max'] = df_out['pot_GW'] * df_out['dias'] * 24
    
    df_out['eficiencia'] = df_out['gen_GWh'] / df_out['gen_max']
    
    print ('df_out_efi_evol')
    print (df_out)
    return df_out

def graficar_efi_evol(df):
    graf = px.area(df, x = 'año', y = 'eficiencia',
        #color = 'tecnologia',
        #color_discrete_map = colores_tecnologia,
        #barmode='group'
    )
    graf.update_layout(
        legend=dict(
            title='',
            orientation='h',
            yanchor='top',
            y=1.1,
            xanchor='center',
            x=.5
        ),
        showlegend=True,
        xaxis = dict(tickmode = 'array'),
        #bargroupgap = 0.1
    )
    graf.update_xaxes(
        showgrid = True
    )
    graf.update_traces(
        line = dict(color='gold', width=3),
        fillcolor='rgba(255, 215, 0, 0.3)',  # fondo amarillo translúcido
        marker = dict(color='gold')
    )
    #graf_evol.update_yaxes(range = [0, 1])
    return graf






#NO USADO+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
def graficar_FC(df_out_ratio_select_fc, colores_tecnologia):
    graf_FC = px.bar(df_out_ratio_select_fc, x = 'FC', y = 'tecnologia',
                        orientation='h',
                        color=df_out_ratio_select_fc['tecnologia'], 
                        hover_name=df_out_ratio_select_fc['tecnologia'],
                        color_discrete_map=colores_tecnologia,
                        text_auto=True,
                        hover_data={
                            'tecnologia':False,
                            'horas_eq':True
                        },
                        text='FC',
                        
                        )
    graf_FC.update_traces(
        texttemplate='%{text:.1%}',
        textposition='inside', 
        
        )
    graf_FC.update_layout(
        #title=dict(
        #    text='Factor de carga (%)',
        #    x=.5,
        #    xanchor='center',
        #),
        xaxis_tickformat='.0%',
        bargap=.4,
        showlegend=False,
        yaxis=dict(visible=True, title_text=None),
    )

    graf_FC.update_xaxes(
        showgrid=True,
        range=[0,1.01],
        dtick=0.2,
        tickmode='linear'
    )

    return graf_FC

