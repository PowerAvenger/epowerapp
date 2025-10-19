import streamlit as st
from utilidades import generar_menu, init_app
from backend_comun import carga_mibgas
from backend_mibgas import filtrar_por_producto, graficar_qs, graficar_da_corrido, graficar_da_comparado
import pandas as pd


if not st.session_state.get('usuario_autenticado', False):
    st.switch_page('epowerapp.py')

#inicializamos variables de sesión

generar_menu()
init_app()


df_mibgas_base = carga_mibgas()
#df_mibgas_base=df_mibgas_base.rename(columns={'Product':'producto','First Day Delivery':'fecha','Last Price\n[EUR/MWh]':'precio_gas'})
#df_mibgas_base["precio_gas"] = pd.to_numeric(df_mibgas_base["precio_gas"], errors="coerce")

productos_q = ['GQES_Q+1', 'GQES_Q+2', 'GQES_Q+3', 'GQES_Q+4']
dfs_q = [filtrar_por_producto(df_mibgas_base, prod) for prod in productos_q]
df_mg_q = pd.concat(dfs_q, ignore_index=True)


graf_qs = graficar_qs(df_mg_q)

df_mg_da = filtrar_por_producto(df_mibgas_base, 'GDAES_D+1')
print('mibgas da')
print(df_mg_da)
graf_da_corrido = graficar_da_corrido(df_mg_da)
graf_da_comparado = graficar_da_comparado(df_mg_da)

st.write(graf_qs)
st.write(graf_da_corrido)
st.write(graf_da_comparado)