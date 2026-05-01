import gc
import math
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from scipy.optimize import minimize

from backend_opt2 import (
    calcular_costes,
    grafico_costes_con,
    graficar_costes_opt,
    ajustar_potencias,
)


GRUPOS_RDL = {
    'ene': {'afectado': ['P1', 'P2', 'P6'], 'no_afectado': ['P3', 'P4', 'P5']},
    'feb': {'afectado': ['P1', 'P2', 'P6'], 'no_afectado': ['P3', 'P4', 'P5']},
    'mar': {'afectado': ['P2', 'P3', 'P6'], 'no_afectado': ['P1', 'P4', 'P5']},
    'abr': {'afectado': ['P4', 'P5', 'P6'], 'no_afectado': ['P1', 'P2', 'P3']},
    'may': {'afectado': ['P4', 'P5', 'P6'], 'no_afectado': ['P1', 'P2', 'P3']},
    'jun': {'afectado': ['P3', 'P4', 'P6'], 'no_afectado': ['P1', 'P2', 'P5']},
    'jul': {'afectado': ['P1', 'P2', 'P6'], 'no_afectado': ['P3', 'P4', 'P5']},
    'ago': {'afectado': ['P3', 'P4', 'P6'], 'no_afectado': ['P1', 'P2', 'P5']},
    'sep': {'afectado': ['P3', 'P4', 'P6'], 'no_afectado': ['P1', 'P2', 'P5']},
    'oct': {'afectado': ['P4', 'P5', 'P6'], 'no_afectado': ['P1', 'P2', 'P3']},
    'nov': {'afectado': ['P2', 'P3', 'P6'], 'no_afectado': ['P1', 'P4', 'P5']},
    'dic': {'afectado': ['P1', 'P2', 'P6'], 'no_afectado': ['P3', 'P4', 'P5']},
}

MESES_ORDEN = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
PERIODOS = ['P1', 'P2', 'P3', 'P4', 'P5', 'P6']


def _coste_mes(df_mes: pd.DataFrame, tarifa: str, pyc_tp: dict, tepp: dict, mes: str, potencias: dict):
    return calcular_costes(df_mes, tarifa, pyc_tp, tepp, [mes], potencias)


def _formato_es(x):
    if pd.isna(x):
        return ""
    if isinstance(x, bool):
        return x
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _aplicar_monotonia_solo_no_afectados(
    pot: Dict[str, float],
    afectados: set,
    no_afectados: set,
) -> Dict[str, float]:
    pot = pot.copy()

    for _ in range(20):
        changed = False
        for i in range(len(PERIODOS) - 1):
            p_prev = PERIODOS[i]
            p_curr = PERIODOS[i + 1]

            if float(pot[p_prev]) <= float(pot[p_curr]):
                continue

            if p_prev in no_afectados and p_curr in afectados:
                pot[p_prev] = float(pot[p_curr])
                changed = True
            elif p_prev in afectados and p_curr in no_afectados:
                pot[p_curr] = float(pot[p_prev])
                changed = True
            elif p_prev in no_afectados and p_curr in no_afectados:
                pot[p_curr] = float(pot[p_prev])
                changed = True

        if not changed:
            break

    for p in no_afectados:
        pot[p] = max(0.1, float(pot[p]))

    return pot


def optimizar_mes_fase1_old(
    df_mes: pd.DataFrame,
    tarifa: str,
    pot_con: dict,
    pyc_tp: dict,
    tepp: dict,
    fijar_P6: bool,
    p6_limite=None
):
    mes = df_mes["mes_nom"].iloc[0]
    pot_inicial = list(pot_con.values())
    p6_max = pot_con["P6"]

    def funcion_objetivo_mes(pot_opt_vector):
        potencias = dict(zip(pot_con.keys(), pot_opt_vector))
        coste_potfra, coste_excesos, _, _, _ = calcular_costes(
            df_mes, tarifa, pyc_tp, tepp, [mes], potencias
        )
        return float(coste_potfra + coste_excesos)

    constraints = [
        {'type': 'ineq', 'fun': lambda x, i=i: x[i + 1] - x[i]}
        for i in range(len(pot_inicial) - 1)
    ]

    if fijar_P6:
        constraints.append({
            'type': 'eq',
            #'fun': lambda x: x[-1] - pot_con['P6']
            'fun': lambda x: x[-1] - p6_max
        })

    #bounds = [(0.0, None)] * len(pot_inicial)
    # Si P6 no puede superar su valor inicial y las potencias deben ser crecientes,
    # entonces ninguna potencia puede superar tampoco ese valor.
    bounds = [(0.0, p6_max)] * len(pot_inicial)

    #if not fijar_P6:
    #    bounds[-1] = (0.0, pot_con['P6'])

    resultado = minimize(
        funcion_objetivo_mes,
        pot_inicial,
        method='SLSQP',
        constraints=constraints,
        bounds=bounds
    )

    pot_opt_ini = dict(zip(pot_con.keys(), resultado.x if resultado.success else pot_inicial))

    pot_fase1 = ajustar_potencias(
        pot_opt_ini,
        fijar_P6=fijar_P6,
        pot_con=pot_con
    )
    
    # Blindaje final por si ajustar_potencias toca algo indebido
    if not fijar_P6:
        for p in pot_fase1:
            pot_fase1[p] = min(pot_fase1[p], p6_max)

    return pot_opt_ini, pot_fase1, resultado


def optimizar_mes_fase1_old(
    df_mes: pd.DataFrame,
    tarifa: str,
    pot_con: dict,
    pyc_tp: dict,
    tepp: dict,
    fijar_P6: bool,
    p6_limite=None
):
    mes = df_mes["mes_nom"].iloc[0]

    # P6 inicial contratada
    p6_inicial = float(pot_con["P6"])

    # Tope efectivo de P6
    # - Si se fija P6: P6 debe quedarse en su valor inicial.
    # - Si se limita P6: P6 no puede superar el límite indicado.
    # - Si no se fija ni se limita: P6 no puede superar su valor inicial.
    if fijar_P6:
        p6_max = p6_inicial
    elif p6_limite is not None:
        p6_max = min(float(p6_limite), p6_inicial)
    else:
        p6_max = p6_inicial

    # Vector inicial.
    # Si p6_limite es menor que alguna potencia inicial, recortamos el punto inicial
    # para que SLSQP no arranque fuera de los bounds.
    pot_inicial = [
        min(float(v), p6_max)
        for v in pot_con.values()
    ]

    def funcion_objetivo_mes(pot_opt_vector):
        potencias = dict(zip(pot_con.keys(), pot_opt_vector))

        coste_potfra, coste_excesos, _, _, _ = calcular_costes(
            df_mes,
            tarifa,
            pyc_tp,
            tepp,
            [mes],
            potencias
        )

        return float(coste_potfra + coste_excesos)

    # Potencias crecientes: P2 >= P1, P3 >= P2, ..., P6 >= P5
    constraints = [
        {
            "type": "ineq",
            "fun": lambda x, i=i: x[i + 1] - x[i]
        }
        for i in range(len(pot_inicial) - 1)
    ]

    # Si P6 se mantiene, la fijamos exactamente al valor inicial
    if fijar_P6:
        constraints.append({
            "type": "eq",
            "fun": lambda x: x[-1] - p6_inicial
        })

    # Como las potencias deben ser crecientes y P6 tiene un tope,
    # ninguna potencia puede superar ese mismo tope.
    bounds = [(0.0, p6_max)] * len(pot_inicial)

    resultado = minimize(
        funcion_objetivo_mes,
        pot_inicial,
        method="SLSQP",
        constraints=constraints,
        bounds=bounds
    )

    pot_opt_ini = dict(
        zip(
            pot_con.keys(),
            resultado.x if resultado.success else pot_inicial
        )
    )

    pot_fase1 = ajustar_potencias(
        pot_opt_ini,
        fijar_P6=fijar_P6,
        pot_con=pot_con
    )

    # Blindaje final:
    # - Si P6 está fijada, restauramos P6 inicial.
    # - Si P6 está limitada/no fijada, ninguna potencia puede superar p6_max.
    if fijar_P6:
        pot_fase1["P6"] = p6_inicial
    else:
        for p in pot_fase1:
            pot_fase1[p] = min(float(pot_fase1[p]), p6_max)

    # Segundo blindaje de potencias crecientes tras posibles recortes
    periodos = list(pot_fase1.keys())
    for i in range(len(periodos) - 2, -1, -1):
        p_actual = periodos[i]
        p_siguiente = periodos[i + 1]
        pot_fase1[p_actual] = min(
            float(pot_fase1[p_actual]),
            float(pot_fase1[p_siguiente])
        )

    return pot_opt_ini, pot_fase1, resultado


def optimizar_mes_fase1(
    df_mes: pd.DataFrame,
    tarifa: str,
    pot_con: dict,
    pyc_tp: dict,
    tepp: dict,
    fijar_P6: bool,
    p6_limite=None
):
    mes = df_mes["mes_nom"].iloc[0]

    # P6 inicial contratada
    p6_inicial = float(pot_con["P6"])

    # p6_limite se interpreta como MÍNIMO permitido de P6.
    # Es decir:
    # - Mantener P6  -> P6 = P6 inicial
    # - No mantener  -> 0 <= P6 <= P6 inicial
    # - Limitar P6   -> p6_limite <= P6 <= P6 inicial
    if p6_limite is not None:
        p6_min = min(float(p6_limite), p6_inicial)
    else:
        p6_min = 0.0

    # Vector inicial real.
    # No recortamos P1-P5 por p6_limite, porque p6_limite solo afecta al mínimo de P6.
    pot_inicial = [
        float(v)
        for v in pot_con.values()
    ]

    def funcion_objetivo_mes(pot_opt_vector):
        potencias = dict(zip(pot_con.keys(), pot_opt_vector))

        coste_potfra, coste_excesos, _, _, _ = calcular_costes(
            df_mes,
            tarifa,
            pyc_tp,
            tepp,
            [mes],
            potencias
        )

        return float(coste_potfra + coste_excesos)

    # Potencias crecientes:
    # P2 >= P1, P3 >= P2, ..., P6 >= P5
    constraints = [
        {
            "type": "ineq",
            "fun": lambda x, i=i: x[i + 1] - x[i]
        }
        for i in range(len(pot_inicial) - 1)
    ]

    # Si P6 se mantiene, la fijamos exactamente al valor inicial
    if fijar_P6:
        constraints.append({
            "type": "eq",
            "fun": lambda x: x[-1] - p6_inicial
        })

    # Bounds por periodo
    bounds = []

    for p in pot_con.keys():
        if p == "P6":
            if fijar_P6:
                bounds.append((p6_inicial, p6_inicial))
            else:
                bounds.append((p6_min, p6_inicial))
        else:
            # P1-P5 pueden moverse entre 0 y P6 inicial.
            # Como hay restricción creciente, nunca podrán quedar por encima de P6.
            bounds.append((0.0, p6_inicial))

    resultado = minimize(
        funcion_objetivo_mes,
        pot_inicial,
        method="SLSQP",
        constraints=constraints,
        bounds=bounds
    )

    pot_opt_ini = dict(
        zip(
            pot_con.keys(),
            resultado.x if resultado.success else pot_inicial
        )
    )

    pot_fase1 = ajustar_potencias(
        pot_opt_ini,
        fijar_P6=fijar_P6,
        pot_con=pot_con
    )

    # Blindaje final P6
    if fijar_P6:
        pot_fase1["P6"] = p6_inicial
    else:
        pot_fase1["P6"] = max(float(pot_fase1["P6"]), p6_min)
        pot_fase1["P6"] = min(float(pot_fase1["P6"]), p6_inicial)

    # Reasegurar potencias crecientes hacia atrás:
    # P5 <= P6, P4 <= P5, ..., P1 <= P2
    periodos = list(pot_fase1.keys())

    for i in range(len(periodos) - 2, -1, -1):
        p_actual = periodos[i]
        p_siguiente = periodos[i + 1]

        pot_fase1[p_actual] = min(
            float(pot_fase1[p_actual]),
            float(pot_fase1[p_siguiente])
        )

    return pot_opt_ini, pot_fase1, resultado


def aplicar_fase2_rdl(
    pot_fase1: Dict[str, float],
    pot_con: Dict[str, float],
    grupos: Dict[str, List[str]],
):
    afectados = set(grupos["afectado"])
    no_afectados = set(grupos["no_afectado"])

    delta_max = max(
        max(0.0, float(pot_con[p]) - float(pot_fase1[p]))
        for p in afectados
    )

    pot_final = pot_fase1.copy()

    for p in no_afectados:
        pot_final[p] = float(pot_con[p])

    if delta_max > 0:
        for p in no_afectados:
            pot_final[p] = max(0.1, float(pot_con[p]) - float(delta_max))

    pot_final = _aplicar_monotonia_solo_no_afectados(
        pot_final,
        afectados=afectados,
        no_afectados=no_afectados
    )

    bajada_aplicada = 0.0
    for p in no_afectados:
        bajada_aplicada = max(
            bajada_aplicada,
            max(0.0, float(pot_con[p]) - float(pot_final[p]))
        )

    return pot_final, float(delta_max), float(bajada_aplicada)


def _crear_fig_resumen(coste_pot_actual, coste_exc_actual, coste_pot_opt, coste_exc_opt):
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=["Actual"],
        y=[coste_pot_actual],
        name="Potencia actual",
        marker_color="deepskyblue"
    ))
    fig.add_trace(go.Bar(
        x=["Actual"],
        y=[coste_exc_actual],
        name="Excesos actual",
        marker_color="blue"
    ))
    fig.add_trace(go.Bar(
        x=["Optimizado"],
        y=[coste_pot_opt],
        name="Potencia optimizada",
        marker_color="lightgreen"
    ))
    fig.add_trace(go.Bar(
        x=["Optimizado"],
        y=[coste_exc_opt],
        name="Excesos optimizados",
        marker_color="green"
    ))

    fig.update_layout(
        barmode="stack",
        title="Resumen costes periodo seleccionado",
        yaxis_title="Coste (€)",
        xaxis_title="Situación",
        legend_title_text="Tipo de coste",
        margin=dict(t=60, b=40, l=40, r=40)
    )
    return fig


def _crear_fig_ahorro(ahorro_pct):
    colors = [
        "rgba(204, 255, 204, 0.6)",
        "rgba(144, 238, 144, 0.6)",
        "rgba(34, 139, 34, 0.6)",
        "rgba(0, 128, 0, 0.6)",
        "rgba(0, 100, 0, 0.6)"
    ]

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=ahorro_pct,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': "Ahorro Obtenido (%)", 'font': {'size': 26}},
        gauge={
            'axis': {'range': [None, 50]},
            'bar': {'color': "green"},
            'bgcolor': "white",
            'steps': [
                {'range': [0, 10], 'color': colors[0]},
                {'range': [10, 20], 'color': colors[1]},
                {'range': [20, 30], 'color': colors[2]},
                {'range': [30, 40], 'color': colors[3]},
                {'range': [40, 50], 'color': colors[4]},
            ],
        }
    ))
    fig.update_traces(number_suffix='%', selector=dict(type='indicator'))
    return fig


def _crear_fig_potencias(df_detalle):
    cols = [c for c in PERIODOS if c in df_detalle.columns]
    fig = px.line(
        df_detalle,
        x="mes",
        y=cols,
        markers=True,
        title="Potencias finales por mes (fase 2)"
    )
    fig.update_layout(margin=dict(t=50, b=40, l=40, r=20))
    return fig


def _crear_fig_ahorro_mensual(df_detalle):
    fig = px.bar(
        df_detalle,
        x="mes",
        y="ahorro",
        title="Ahorro mensual"
    )
    fig.update_layout(margin=dict(t=50, b=40, l=40, r=20))
    return fig


def calcular_optimizacion_rdl(
    df_in: pd.DataFrame,
    fijar_P6: bool,
    tarifa: str,
    pot_con: dict,
    pyc_tp: dict,
    tepp: dict,
    mes_inicio: str,
    p6_limite=None
):
    idx_ini = MESES_ORDEN.index(mes_inicio)
    meses_eval = MESES_ORDEN[idx_ini:]

    detalle_fase1 = []
    detalle_final = []
    filas_coste = []

    #añadido nuevo para usar las potencias de referencia del mes anterior
    pot_ref = pot_con.copy()

    detalle_final.append({
        "mes": "inicial",
        **{p: float(pot_con[p]) for p in PERIODOS},
        "delta_max": None,
        "bajada_aplicada": None,
        "coste_actual": None,
        "coste_opt": None,
        "ahorro": None,
        "optim_success": None,
        "optim_message": "Potencias iniciales de partida",
    })

    for mes in meses_eval:
        df_mes = df_in[df_in["mes_nom"] == mes].copy()
        if df_mes.empty:
            continue

        grupos = GRUPOS_RDL[mes]

        coste_pot_base, coste_exc_base, coste_base, _, _ = _coste_mes(
            df_mes, tarifa, pyc_tp, tepp, mes, pot_con
        )

        pot_opt_ini, pot_fase1, resultado = optimizar_mes_fase1(
            df_mes=df_mes,
            tarifa=tarifa,
            pot_con=pot_con,
            pyc_tp=pyc_tp,
            tepp=tepp,
            fijar_P6=fijar_P6,
            p6_limite=p6_limite
        )

        pot_final, delta_max, bajada_aplicada = aplicar_fase2_rdl(
            pot_fase1=pot_fase1,
            #pot_con=pot_con,
            pot_con=pot_ref,
            grupos=grupos
        )

        coste_pot_opt, coste_exc_opt, coste_opt, _, _ = _coste_mes(
            df_mes, tarifa, pyc_tp, tepp, mes, pot_final
        )

        # 🔥 ACTUALIZACIÓN DINÁMICA
        pot_ref = pot_final.copy()

        detalle_fase1.append({
            "mes": mes,
            **{p: float(pot_fase1[p]) for p in PERIODOS},
            "optim_success": bool(resultado.success),
            "optim_message": str(resultado.message),
        })

        detalle_final.append({
            "mes": mes,
            **{p: float(pot_final[p]) for p in PERIODOS},
            "delta_max": float(delta_max),
            "bajada_aplicada": float(bajada_aplicada),
            "coste_actual": float(coste_base),
            "coste_opt": float(coste_opt),
            "ahorro": float(coste_base - coste_opt),
            "optim_success": bool(resultado.success),
            "optim_message": str(resultado.message),
        })

        filas_coste.append({
            "mes": mes,
            "coste_pot_mes": float(coste_pot_base),
            "coste_excesos_mes": float(coste_exc_base),
            "coste_pot_mes_opt": float(coste_pot_opt),
            "coste_excesos_mes_opt": float(coste_exc_opt),
            "coste_actual": float(coste_base),
            "coste_opt": float(coste_opt),
            "ahorro": float(coste_base - coste_opt),
        })

    df_fase1 = pd.DataFrame(detalle_fase1)
    df_final = pd.DataFrame(detalle_final)
    df_coste_tp_mes = pd.DataFrame(filas_coste).set_index("mes")

    coste_tp_potcon = float(df_coste_tp_mes["coste_actual"].sum()) if not df_coste_tp_mes.empty else 0.0
    coste_tp_potopt = float(df_coste_tp_mes["coste_opt"].sum()) if not df_coste_tp_mes.empty else 0.0
    ahorro_opt = float(coste_tp_potcon - coste_tp_potopt)
    ahorro_opt_porc = (ahorro_opt * 100 / coste_tp_potcon) if coste_tp_potcon else 0.0

    graf_costes_potcon = grafico_costes_con(df_coste_tp_mes)
    graf_costes_potcon = graficar_costes_opt(graf_costes_potcon, df_coste_tp_mes)

    graf_resumen = _crear_fig_resumen(
        df_coste_tp_mes["coste_pot_mes"].sum(),
        df_coste_tp_mes["coste_excesos_mes"].sum(),
        df_coste_tp_mes["coste_pot_mes_opt"].sum(),
        df_coste_tp_mes["coste_excesos_mes_opt"].sum()
    )

    graf_ahorro = _crear_fig_ahorro(ahorro_opt_porc)
    graf_potencias = _crear_fig_potencias(df_final)
    graf_ahorro_mensual = _crear_fig_ahorro_mensual(df_final)

    df_fase1_mostrar = df_fase1.copy()
    df_final_mostrar = df_final.copy()

    for df_show in [df_fase1_mostrar, df_final_mostrar]:
        for col in ["delta_max", "bajada_aplicada", "coste_actual", "coste_opt", "ahorro"]:
            if col in df_show.columns:
                df_show[col] = df_show[col].apply(_formato_es)

    gc.collect()

    return {
        "graf_costes_potcon": graf_costes_potcon,
        "graf_resumen": graf_resumen,
        "coste_tp_potcon": coste_tp_potcon,
        "coste_tp_potopt": coste_tp_potopt,
        "ahorro_opt": ahorro_opt,
        "ahorro_opt_porc": ahorro_opt_porc,
        "df_fase1": df_fase1_mostrar,
        "df_final": df_final_mostrar,
        "graf_ahorro": graf_ahorro,
        "graf_potencias": graf_potencias,
        "graf_ahorro_mensual": graf_ahorro_mensual,
        "df_coste_tp_mes": df_coste_tp_mes.reset_index(),
    }
