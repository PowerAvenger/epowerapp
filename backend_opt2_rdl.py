# backend_opt2_rdl FINAL (corregido monotonicidad + lógica opt2)

import gc
import math
import numpy as np
import pandas as pd
from scipy.optimize import minimize

from backend_opt2 import calcular_costes, grafico_costes_con, graficar_costes_opt

GRUPOS_RDL = {
    'ene': {'afectado': ['P1','P2','P6'], 'no_afectado': ['P3','P4','P5']},
    'feb': {'afectado': ['P1','P2','P6'], 'no_afectado': ['P3','P4','P5']},
    'mar': {'afectado': ['P2','P3','P6'], 'no_afectado': ['P1','P4','P5']},
    'abr': {'afectado': ['P4','P5','P6'], 'no_afectado': ['P1','P2','P3']},
    'may': {'afectado': ['P4','P5','P6'], 'no_afectado': ['P1','P2','P3']},
    'jun': {'afectado': ['P3','P4','P6'], 'no_afectado': ['P1','P2','P5']},
    'jul': {'afectado': ['P1','P2','P6'], 'no_afectado': ['P3','P4','P5']},
    'ago': {'afectado': ['P3','P4','P6'], 'no_afectado': ['P1','P2','P5']},
    'sep': {'afectado': ['P3','P4','P6'], 'no_afectado': ['P1','P2','P5']},
    'oct': {'afectado': ['P4','P5','P6'], 'no_afectado': ['P1','P2','P3']},
    'nov': {'afectado': ['P2','P3','P6'], 'no_afectado': ['P1','P4','P5']},
    'dic': {'afectado': ['P1','P2','P6'], 'no_afectado': ['P3','P4','P5']},
}

MESES = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic']
PERIODOS = ['P1','P2','P3','P4','P5','P6']


# =========================
# MONOTONICIDAD GLOBAL (CLAVE)
# =========================
def enforce_monotonic(pot, afectados=None):
    pot = pot.copy()

    # subida hacia delante
    for i in range(1,6):
        p_prev = f"P{i}"
        p_curr = f"P{i+1}"
        if pot[p_curr] < pot[p_prev]:
            pot[p_curr] = pot[p_prev]

    # bajada hacia atrás (solo si no rompe afectados)
    for i in reversed(range(1,6)):
        p_prev = f"P{i}"
        p_curr = f"P{i+1}"
        if pot[p_prev] > pot[p_curr]:
            if afectados is None or p_prev not in afectados:
                pot[p_prev] = pot[p_curr]

    return pot


# =========================
# FASE 1 (OPT2 real)
# =========================
def optimizar_mes(df_mes, tarifa, pot_con, pyc_tp, tepp, afectados, fijar_P6):

    mes = df_mes["mes_nom"].iloc[0]

    def build(x):
        pot = pot_con.copy()
        for i,p in enumerate(afectados):
            pot[p] = x[i]
        return pot

    def obj(x):
        pot = build(x)
        _, _, c, _, _ = calcular_costes(df_mes, tarifa, pyc_tp, tepp, [mes], pot)
        return c

    def mono(x):
        pot = build(x)
        return min(pot[f"P{i+1}"] - pot[f"P{i}"] for i in range(1,6))

    cons = [{'type':'ineq','fun':mono}]

    if fijar_P6 and "P6" in afectados:
        idx = afectados.index("P6")
        cons.append({'type':'eq','fun':lambda x,idx=idx: x[idx]-pot_con["P6"]})

    bounds = []
    for p in afectados:
        if p=="P6":
            if fijar_P6:
                bounds.append((pot_con["P6"], pot_con["P6"]))
            else:
                bounds.append((0.1, pot_con["P6"]))
        else:
            bounds.append((0.1, None))

    x0 = [pot_con[p] for p in afectados]

    res = minimize(obj, x0, method="SLSQP", bounds=bounds, constraints=cons)

    pot = build(res.x if res.success else x0)

    # redondeo tipo opt2
    for p in afectados:
        pot[p] = math.ceil(pot[p])

    # 🔥 clave: corregir monotonicidad global
    pot = enforce_monotonic(pot)

    delta_max = max(max(0, pot_con[p]-pot[p]) for p in afectados)

    return pot, delta_max


# =========================
# FASE 2
# =========================
def aplicar_fase2(pot_f1, pot_con, grupos, delta):

    pot = pot_f1.copy()

    for p in grupos["no_afectado"]:
        pot[p] = max(0.1, pot_con[p] - delta)

    # 🔥 clave: monotonicidad global final
    pot = enforce_monotonic(pot, afectados=set(grupos["afectado"]))

    return pot


# =========================
# MAIN
# =========================
def calcular_optimizacion_rdl(df_in, fijar_P6, tarifa, pot_con, pyc_tp, tepp, mes_inicio):

    meses = MESES[MESES.index(mes_inicio):]

    rows = []
    costes = []

    for mes in meses:

        df_mes = df_in[df_in["mes_nom"]==mes].copy()
        if df_mes.empty:
            continue

        grupos = GRUPOS_RDL[mes]

        c_pot, c_exc, c_base, _, _ = calcular_costes(df_mes, tarifa, pyc_tp, tepp, [mes], pot_con)

        pot_f1, delta = optimizar_mes(df_mes, tarifa, pot_con, pyc_tp, tepp, grupos["afectado"], fijar_P6)

        pot_final = aplicar_fase2(pot_f1, pot_con, grupos, delta)

        c_pot_o, c_exc_o, c_opt, _, _ = calcular_costes(df_mes, tarifa, pyc_tp, tepp, [mes], pot_final)

        rows.append({
            "mes": mes,
            **pot_final,
            "delta_max": delta,
            "coste_actual": c_base,
            "coste_opt": c_opt,
            "ahorro": c_base - c_opt
        })

        costes.append({
            "mes": mes,
            "coste_actual": c_base,
            "coste_opt": c_opt,
            "ahorro": c_base - c_opt,
            "coste_pot_mes": c_pot,
            "coste_excesos_mes": c_exc,
            "coste_pot_mes_opt": c_pot_o,
            "coste_excesos_mes_opt": c_exc_o
        })

    df_det = pd.DataFrame(rows)
    df_coste = pd.DataFrame(costes).set_index("mes")

    graf = grafico_costes_con(df_coste)
    graf = graficar_costes_opt(graf, df_coste)

    total_actual = df_coste["coste_actual"].sum()
    total_opt = df_coste["coste_opt"].sum()
    ahorro = total_actual - total_opt
    ahorro_pct = (ahorro/total_actual*100) if total_actual else 0

    return (
        graf,
        graf,
        total_actual,
        total_opt,
        ahorro,
        ahorro_pct,
        df_det,
        graf,
        graf,
        graf,
        df_coste.reset_index()
    )
