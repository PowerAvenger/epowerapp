import pandas as pd
import plotly.express as px
import streamlit as st
from backend_comun import colores_precios



def filtrar_datos():
   
    if st.session_state.rango_temporal == 'Por años': 
        df_filtrado = st.session_state.df_sheets[st.session_state.df_sheets['año'] == st.session_state.año_seleccionado]
        lista_meses = df_filtrado['mes_nombre'].unique().tolist()
        print('1')
    elif st.session_state.rango_temporal == 'Por meses': 
        df_filtrado_año = st.session_state.df_sheets[st.session_state.df_sheets['año'] == st.session_state.año_seleccionado]
        df_filtrado = st.session_state.df_sheets[(st.session_state.df_sheets['año'] == st.session_state.año_seleccionado) & (st.session_state.df_sheets['mes_nombre'] == st.session_state.mes_seleccionado)]
        print('df_filtrado AÑO')
        print(df_filtrado)
        lista_meses = df_filtrado_año['mes_nombre'].unique().tolist()
        print('2')
    else:
        df_filtrado = st.session_state.df_sheets[(st.session_state.df_sheets['fecha'] == st.session_state.dia_seleccionado)]
        lista_meses = None
        print('3')

    print('dia seleccionado')
    print(st.session_state.dia_seleccionado)
    print('st session df sheets')
    print(st.session_state.df_sheets)

    print ('df_filtrado')
    print (df_filtrado)
             
    return df_filtrado, lista_meses
        


def aplicar_margen(df_filtrado):
    for col in ['precio_2.0','precio_3.0', 'precio_6.1']:
        df_filtrado[col] += st.session_state.margen
    

    return df_filtrado


def pt1(df_filtrado):
    dffm = aplicar_margen(df_filtrado)
    
    pt1 = dffm.pivot_table(
        values = ['spot', 'ssaa', 'precio_2.0', 'precio_3.0', 'precio_6.1'],
        index = 'hora',
        aggfunc = 'mean'
    ).reset_index()
    #print(pt1)
    pt20 = dffm.pivot_table(
        values=['spot', 'ssaa', 'osom', 'otros', 'ppcc_2.0', 'perd_2.0', 'pyc_2.0'],
        index='año',
        aggfunc='mean'
    )
    pt20['comp_perd'] = pt20['spot'] + pt20['ssaa'] + pt20['osom'] + pt20['otros'] + pt20['ppcc_2.0']
    pt20['perdidas_2.0'] = pt20['comp_perd'] * (pt20['perd_2.0'])
    pt20 = pt20.drop(columns = ['perd_2.0','comp_perd'])
    print('pt20')
    print(pt20)
    pt20_trans = pt20.transpose().reset_index()
    pt20_trans = pt20_trans.rename(columns  ={'index':'componente', pt20_trans.columns[1] :'valor'})
    pt20_trans['componente'] = pt20_trans['componente'].replace({'otros': 'otros'})
    print('pt20_trans')
    print(pt20_trans)
    pt20_trans = pt20_trans.sort_values(by='valor', ascending=False)
    print('pt20_trans')
    print(pt20_trans)
    #pt20_trans['valor'] = round(pt20_trans['valor'],2)
    #pt20_trans['valor'] = pt20_trans['valor'].round(2)
    print('pt20_trans')
    print(pt20_trans)

    graf20 = px.pie(pt20_trans,names='componente',values='valor', hole=.3, color_discrete_sequence=px.colors.sequential.Oranges_r)
    graf20.update_layout(
          title={'text':'Peaje de acceso 2.0','x':.5,'xanchor':'center'}
    )

    pt30=dffm.pivot_table(
        values=['spot', 'ssaa', 'osom', 'otros', 'ppcc_3.0', 'perd_3.0', 'pyc_3.0'],
        index='año',
        aggfunc='mean'
    )
    pt30['comp_perd']=pt30['spot']+pt30['ssaa']+pt30['osom']+pt30['otros']+pt30['ppcc_3.0']
    pt30['perdidas_3.0']=pt30['comp_perd']*(pt30['perd_3.0'])
    pt30=pt30.drop(columns=['perd_3.0','comp_perd'])
    pt30_trans=pt30.transpose().reset_index()
    pt30_trans=pt30_trans.rename(columns={'index':'componente', pt30_trans.columns[1]:'valor'})
    pt30_trans['componente'] = pt30_trans['componente'].replace({'otros': 'otros'})
    pt30_trans=pt30_trans.sort_values(by='valor',ascending=False)
    #pt30_trans['valor']=round(pt30_trans['valor'],2)

    graf30=px.pie(pt30_trans,names='componente',values='valor', hole=.3, color_discrete_sequence=px.colors.sequential.Reds_r)
    graf30.update_layout(
          title={'text':'Peaje de acceso 3.0','x':.5,'xanchor':'center'}
    )

    pt61=dffm.pivot_table(
        values=['spot', 'ssaa', 'osom', 'otros', 'ppcc_6.1', 'perd_6.1', 'pyc_6.1'],
        index='año',
        aggfunc='mean'
    )
    pt61['comp_perd']=pt61['spot']+pt61['ssaa']+pt61['osom']+pt61['otros']+pt61['ppcc_6.1']
    pt61['perdidas_6.1']=pt61['comp_perd']*(pt61['perd_6.1'])
    pt61=pt61.drop(columns=['perd_6.1','comp_perd'])
    pt61_trans=pt61.transpose().reset_index()
    pt61_trans=pt61_trans.rename(columns={'index':'componente', pt61_trans.columns[1]:'valor'})
    pt61_trans['componente'] = pt61_trans['componente'].replace({'otros': 'otros'})
    pt61_trans=pt61_trans.sort_values(by='valor',ascending=False)
    #pt61_trans['valor']=round(pt61_trans['valor'],2)

    graf61=px.pie(pt61_trans,names='componente',values='valor', hole=.3, color_discrete_sequence=px.colors.sequential.Blues_r)
    graf61.update_layout(
          title={'text':'Peaje de acceso 6.1','x':.5,'xanchor':'center'}
    )
    
    return pt1, graf20, graf30, graf61


def pt1_trans(df_filtrado):
    pt2=pt1(df_filtrado)[0]
    pt1_trans=pt2.transpose()
    pt1_trans=pt1_trans.drop(['hora'])
    pt1_trans.columns.name='peajes'
    pt1_trans=pt1_trans.round(2)
    
    return pt1_trans

# GRAFICO PRINCIPAL CON LAS BARRAS DE OMIE Y SSAA Y LAS LINEAS DE PRECIO FINAL. HORARIAS
def graf_principal(df_filtrado, colores_precios):
    pt2 = pt1(df_filtrado)[0]
    print('pt2')
    print(pt2)
    #colores_precios = {'precio_2.0': 'goldenrod', 'precio_3.0': 'darkred', 'precio_6.1': '#1C83E1'}
    graf_pt1=px.line(pt2,x='hora',y=['precio_2.0','precio_3.0','precio_6.1'],
        height=600,
        #title=f'Telemindex {st.session_state.año_seleccionado}: Precios medios horarios de indexado según tarifas de acceso',
        labels={'value':'€/MWh','variable':'Precios según ATR'},
        color_discrete_map=colores_precios,
    )
    graf_pt1.update_traces(line=dict(width=4))
   
    graf_pt1.update_layout(
        margin=dict(t=100),
        #title_font_size=16,
        #title={'x':.5,'xanchor':'center'},
        xaxis=dict(
              tickmode='array',
              tickvals=pt2['hora']
        ),
        #barmode = 'stack'
        barmode = 'relative'
    )
    graf_pt1 = graf_pt1.add_bar(y = pt2['spot'], name = 'spot', marker_color = 'green', width = 0.5)
    graf_pt1 = graf_pt1.add_bar(y = pt2['ssaa'], name = 'ssaa', marker_color = 'lightgreen', width = 0.5)
    return graf_pt1



def pt5_trans(df_filtrado_final):
        dffm=aplicar_margen(df_filtrado_final)
        pt3=dffm.pivot_table(
                values=['precio_2.0'],
                aggfunc='mean',
                index='dh_3p'
                )
        pt4=dffm.pivot_table(
                values=['precio_3.0','precio_6.1'],
                aggfunc='mean',
                index='dh_6p',
                )
        pt5=pd.concat([pt3,pt4],axis=1)
        
        
        media_20=dffm['precio_2.0'].mean()
        media_30=dffm['precio_3.0'].mean()
        media_61=dffm['precio_6.1'].mean()
        media_spot=dffm['spot'].mean()
        media_ssaa = dffm['ssaa'].mean()
        precios_medios = [media_20, media_30, media_61]
        pt5_trans = pt5.transpose()
        pt5_trans['Media'] = precios_medios
        pt5_trans = pt5_trans.div(10)
        pt5_trans = pt5_trans.round(1)
        pt5_trans = pt5_trans.apply(pd.to_numeric, errors = 'coerce')
        

        return pt5_trans, media_20, media_30, media_61, media_spot, media_ssaa

def costes_indexado(df_filtrado_final):
        dffm = aplicar_margen(df_filtrado_final)
        pt3 = dffm.pivot_table(
                values=['coste_2.0'],
                aggfunc='mean',
                index='dh_3p'
                )
        pt4=dffm.pivot_table(
                values=['coste_3.0','coste_6.1'],
                aggfunc='mean',
                index='dh_6p',
                )
        pt5=pd.concat([pt3,pt4],axis=1)
        
        
        media_20=dffm['coste_2.0'].mean()
        media_30=dffm['coste_3.0'].mean()
        media_61=dffm['coste_6.1'].mean()
        #media_spot=dffm['spot'].mean()
        precios_medios = [media_20, media_30, media_61]
        pt5_trans = pt5.transpose()
        pt5_trans['Media'] = precios_medios
        pt5_trans=pt5_trans.div(10)
        pt5_trans=pt5_trans.round(1)
        
        pt5_trans = pt5_trans.apply(pd.to_numeric, errors='coerce')
        #pt5_trans = pt5_trans.astype(object).where(pt5_trans.notna(), '')

        return pt5_trans

# TABLA RESUMEN DE PEAJES Y CARGOS
def pt7_trans(df_filtrado_final):
        dffm=aplicar_margen(df_filtrado_final)
        pt3=dffm.pivot_table(
                values=['pyc_2.0'],
                aggfunc='mean',
                index='dh_3p'
                )
        pt4=dffm.pivot_table(
                values=['pyc_3.0','pyc_6.1'],
                aggfunc='mean',
                index='dh_6p',
                )
        pt5=pd.concat([pt3,pt4],axis=1)
        
        
        media_20 = dffm['pyc_2.0'].mean()
        media_30 = dffm['pyc_3.0'].mean()
        media_61 = dffm['pyc_6.1'].mean()
        #media_spot=dffm['spot'].mean()
        precios_medios = [media_20, media_30, media_61]
        pt5_trans = pt5.transpose()
        pt5_trans['Media']=precios_medios
        pt5_trans = pt5_trans.div(10)
        pt5_trans = pt5_trans.round(1)
        pt5_trans = pt5_trans.apply(pd.to_numeric, errors='coerce')
        #pt5_trans=pt5_trans.fillna('')

        return pt5_trans #, media_20,media_30,media_61,media_spot

        



