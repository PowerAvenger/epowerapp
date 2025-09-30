import pandas as pd
import plotly.express as px




# función para crear un df según el producto
def filtrar_por_producto(df, producto):
    df_f = df[df['producto'] == producto].copy()
    #df_f['fecha'] = pd.to_datetime(df_f['fecha'], dayfirst=True, errors='coerce')
    df_f['fecha'] = pd.to_datetime(df_f['fecha'], dayfirst=False, errors='coerce').dt.date
    #df_f = df_f.drop(columns=['producto']).dropna().reset_index(drop=True)
    return df_f


def graficar_qs(df_mg_q):
    df_mg_q['Trading day'] = pd.to_datetime(df_mg_q['Trading day'])
    df_mg_q['fecha'] = pd.to_datetime(df_mg_q['fecha'])

    # Crear columna 'trimestre'
    df_mg_q["trimestre"] = ("Q" + df_mg_q["fecha"].dt.quarter.astype(str) + "-" + df_mg_q["fecha"].dt.year.astype(str))

    def _key(lbl):
        q, y = lbl.split("-")
        return (int(y), int(q[1]))  # (año, nº de Q)

    uniq = sorted(df_mg_q["trimestre"].unique(), key=_key)
    labels = uniq[-4:]  # últimos 4 trimestres que haya en el df

    df_win = df_mg_q[df_mg_q["trimestre"].isin(labels)].copy()
    cat = pd.api.types.CategoricalDtype(categories=labels, ordered=True)
    df_win["trimestre"] = df_win["trimestre"].astype(cat)
    df_win = df_win.sort_values(["Trading day", "trimestre"])

    # Pivotar para tener cada trimestre en una columna
    df_pivot = df_win.pivot(index="Trading day", columns="trimestre", values="precio_gas").reset_index()


    #escala de azules (oscuro → claro)
    palette = px.colors.sequential.Blues[3:7]  # 4 tonos (ajusta si necesitas más/menos)

    # tus trimestres ya están en orden en 'labels'
    color_map = {labels[i]: palette[i] for i in range(len(labels))}
    # Gráfico con varias columnas como "wide form"
    fig = px.line(
        df_pivot,
        x="Trading day",
        y=df_pivot.columns[1:], 
        #color="trimestre",
        labels={'value':'€/MWh', 'variable':'Trimestre'},
        color_discrete_map=color_map, # todas las columnas de trimestres
        title='Evolución de MIBGAS para los próximos trimestres',
        height=800
    )

    # Ajustar el tooltip para que muestre todas las series
    # 1) Un solo tooltip por x (Trading day)
    fig.update_layout(hovermode="x unified")

    # 2) Formato de la fecha en el encabezado del tooltip
    fig.update_xaxes(
        hoverformat="%Y-%m-%d",
        dtick="M1",   # intervalo de 1 mes
        tickformat="%b\n%Y",  # etiquetas: abreviatura del mes y año
        showgrid=True,
        gridcolor="lightgrey",
        #gridwidth=.1
    )

    # 3) Contenido de cada fila del tooltip (nombre del Q y su valor)
    fig.update_traces(hovertemplate="%{fullData.name}: %{y:.2f} €/MWh<extra></extra>")

  
    
    return fig

