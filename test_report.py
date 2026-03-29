"""
test_report.py
--------------
Prueba rápida para verificar que la generación funciona
antes de integrar en tu app real.

Ejecutar desde la carpeta informe_potencias/:
    python test_report.py

Genera:  test_informe.pdf  /  test_informe.docx  /  test_informe.html
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from report_generator import generar_informe


# ── Datos de ejemplo ──────────────────────────────────────────────────

df_potencias = pd.DataFrame({
    "Periodo":          ["P1", "P2", "P3", "P4", "P5", "P6"],
    "Pot. contratada (kW)": [50, 50, 40, 40, 30, 30],
    "Pot. óptima (kW)":     [42, 45, 35, 38, 28, 26],
    "Ahorro (kW)":          [8,   5,  5,  2,  2,  4],
})

coste_tp_potcon  = 18_450.00
coste_tp_potopt  = 14_920.00
ahorro_opt       = 3_530.00
ahorro_opt_porc  = 19.1


def make_fig_resumen():
    fig, ax = plt.subplots(figsize=(5, 3))
    periodos = ["P1","P2","P3","P4","P5","P6"]
    contratada = [50, 50, 40, 40, 30, 30]
    optima     = [42, 45, 35, 38, 28, 26]
    x = np.arange(len(periodos))
    ax.bar(x - 0.2, contratada, 0.4, label="Contratada", color="#1a56db")
    ax.bar(x + 0.2, optima,     0.4, label="Óptima",     color="#15803d")
    ax.set_xticks(x); ax.set_xticklabels(periodos)
    ax.set_ylabel("kW"); ax.set_title("Potencias por periodo")
    ax.legend(); fig.tight_layout()
    return fig

def make_fig_costes_potcon():
    fig, ax = plt.subplots(figsize=(5, 3))
    meses = ["Ene","Feb","Mar","Abr","May","Jun"]
    costes = [1600, 1520, 1480, 1550, 1600, 1700]
    ax.plot(meses, costes, marker="o", color="#1a56db", linewidth=2)
    ax.fill_between(meses, costes, alpha=0.15, color="#1a56db")
    ax.set_ylabel("€"); ax.set_title("Costes potencia contratada")
    fig.tight_layout()
    return fig

def make_fig_ahorro():
    fig, ax = plt.subplots(figsize=(5, 3))
    periodos = ["P1","P2","P3","P4","P5","P6"]
    ahorro   = [380, 230, 220,  90, 85, 160]
    colors   = ["#15803d" if a > 0 else "#dc2626" for a in ahorro]
    ax.bar(periodos, ahorro, color=colors)
    ax.set_ylabel("€"); ax.set_title("Ahorro por periodo")
    fig.tight_layout()
    return fig

def make_fig_costes_pot_periodos():
    fig, ax = plt.subplots(figsize=(5, 3))
    periodos = ["P1","P2","P3","P4","P5","P6"]
    cont = [3200, 3000, 2400, 2200, 1400, 1250]
    opt  = [2700, 2700, 2100, 2100, 1200, 1120]
    x = np.arange(len(periodos))
    ax.bar(x - 0.2, cont, 0.4, label="Contratada", color="#1a56db", alpha=0.85)
    ax.bar(x + 0.2, opt,  0.4, label="Óptima",     color="#15803d", alpha=0.85)
    ax.set_xticks(x); ax.set_xticklabels(periodos)
    ax.set_ylabel("€"); ax.set_title("Costes por periodo")
    ax.legend(); fig.tight_layout()
    return fig


# ── Generar informe ───────────────────────────────────────────────────

if __name__ == "__main__":
    print("Generando informe de prueba...")

    resultado = generar_informe(
        graf_costes_potcon       = make_fig_costes_potcon(),
        graf_resumen             = make_fig_resumen(),
        coste_tp_potcon          = coste_tp_potcon,
        coste_tp_potopt          = coste_tp_potopt,
        ahorro_opt               = ahorro_opt,
        ahorro_opt_porc          = ahorro_opt_porc,
        df_potencias             = df_potencias,
        graf_ahorro              = make_fig_ahorro(),
        graf_costes_pot_periodos = make_fig_costes_pot_periodos(),
        titulo                   = "Informe de Optimización de Potencias",
        subtitulo                = "Análisis tarifario — Ejemplo de prueba",
        template_path            = "templates/informe.html",
    )

    with open("test_informe.pdf",  "wb") as f: f.write(resultado["pdf"])
    with open("test_informe.docx", "wb") as f: f.write(resultado["docx"])
    with open("test_informe.html", "w",  encoding="utf-8") as f: f.write(resultado["html"])

    print("✅ Archivos generados:")
    print("   → test_informe.pdf")
    print("   → test_informe.docx")
    print("   → test_informe.html")
