"""Gráficas del informe (PNG para el PDF).

Reglas de diseño: una serie usa un solo color; el texto va siempre en tinta
(nunca del color de la serie); los colores de estado (rojo/ámbar) solo se
usan cuando significan estado y siempre con etiqueta; rejilla tenue y sólida;
líneas punteadas solo para umbrales (límites y alertas).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from . import config as C  # noqa: E402
from .utilidades import fecha_corta, num  # noqa: E402

AZUL, NARANJA = "#2a78d6", "#eb6834"
AZUL_OSCURO = "#104281"
CRITICO, ALERTA = "#d03b3b", "#fab219"
TINTA, TINTA_2, TENUE = "#0b0b0b", "#52514e", "#898781"
REJILLA, BASE = "#e1e0d9", "#c3c2b7"
ANCHO = 6.6   # pulgadas (ancho útil de la página)

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8, "axes.titlesize": 9,
    "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.titlecolor": TINTA,
    "axes.edgecolor": BASE, "axes.labelcolor": TINTA_2, "axes.linewidth": 0.8,
    "xtick.color": TINTA_2, "ytick.color": TINTA_2, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
    "axes.grid": True, "grid.color": REJILLA, "grid.linewidth": 0.6, "grid.linestyle": "-",
    "legend.frameon": False, "legend.fontsize": 7.5, "figure.dpi": 100, "savefig.dpi": 200,
    "axes.spines.top": False, "axes.spines.right": False,
})

FMT_MILES = FuncFormatter(lambda x, _: num(x, 0))
FMT_PCT0 = FuncFormatter(lambda x, _: num(100 * x, 0) + "%")


def _guardar(fig, ruta: Path) -> Path:
    fig.savefig(ruta, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return ruta


def _barras_h(ax, etiquetas, valores, textos, colores=None, alto=0.58):
    y = np.arange(len(etiquetas))[::-1]
    ax.barh(y, valores, height=alto, color=colores or AZUL, zorder=3)
    ax.set_yticks(y, etiquetas)
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", length=0)
    maximo = max(abs(v) for v in valores) if len(valores) else 1
    for yi, v, t in zip(y, valores, textos):
        ax.text(v + (0.012 * maximo if v >= 0 else -0.012 * maximo), yi, t, va="center",
                ha="left" if v >= 0 else "right", fontsize=7.5, color=TINTA)
    return y


def composicion(conc: dict, ruta: Path) -> Path:
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(ANCHO, 2.6), gridspec_kw={"wspace": 0.55})
    t = conc["por_tipo"]
    _barras_h(a1, t["grupo"], t["pct"], [num(100 * p, 1) + "%" for p in t["pct"]])
    a1.set_title("Por tipo de instrumento")
    c = conc["por_calificacion"]
    _barras_h(a2, c["grupo"], c["pct"], [num(100 * p, 1) + "%" for p in c["pct"]])
    a2.set_title("Por calificación")
    for a in (a1, a2):
        a.xaxis.set_major_formatter(FMT_PCT0)
        a.set_xlim(0, max(a.get_xlim()[1], 0.1) * 1.18)
    return _guardar(fig, ruta)


def distribucion_pnl(var: dict, ruta: Path) -> Path:
    pnl = var["pnl_hs"] / 1e6
    fig, ax = plt.subplots(figsize=(ANCHO, 2.7))
    ax.hist(pnl, bins=60, color=AZUL, alpha=0.9, zorder=3, rwidth=0.85)
    lineas = [(-var["var_hs"] / 1e6, TINTA, "-", "VaR 99% histórico"),
              (-var["es_hs"] / 1e6, TINTA, (0, (4, 2)), "ES 97,5% histórico"),
              (-var["var_param"] / 1e6, NARANJA, "-", "VaR 99% paramétrico")]
    for x, color, estilo, etiqueta in lineas:
        ax.axvline(x, color=color, linestyle=estilo, linewidth=1.5, zorder=4,
                   label=f"{etiqueta}: {num(-x, 0)}")
    ax.set_xlabel("Pérdidas y ganancias simuladas a 1 día (COP millones)")
    ax.set_ylabel("Escenarios")
    ax.xaxis.set_major_formatter(FMT_MILES)
    ax.legend(loc="upper right")
    ax.set_title(f"Distribución de P&G: {C.VENTANA_HS} escenarios históricos aplicados al portafolio actual")
    return _guardar(fig, ruta)


def var_por_factor(var: dict, ruta: Path) -> Path:
    grupos = var["grupos_hs"]
    etiquetas = list(grupos) + ["Beneficio de diversificación", "VaR total"]
    valores = [v / 1e6 for v in grupos.values()] + [-var["diversificacion_hs"] / 1e6, var["var_hs"] / 1e6]
    colores = [AZUL] * len(grupos) + [TENUE, AZUL_OSCURO]
    fig, ax = plt.subplots(figsize=(ANCHO, 2.3))
    _barras_h(ax, etiquetas, valores, [num(v, 0) for v in valores], colores)
    ax.axvline(0, color=BASE, linewidth=0.8)
    ax.xaxis.set_major_formatter(FMT_MILES)
    ax.set_xlabel("COP millones")
    lo, hi = ax.get_xlim()
    ax.set_xlim(lo * 1.25, hi * 1.12)
    ax.set_title("VaR histórico 99% a 1 día por factor de riesgo (cada factor por separado)")
    return _guardar(fig, ruta)


def contribucion_posiciones(tabla: pd.DataFrame, ruta: Path, n: int = 10) -> Path:
    t = tabla.sort_values("contrib_es", ascending=False).head(n)
    etiquetas = [e if len(e) <= 38 else e[:36] + "…" for e in t["especie"]]
    valores = list(t["contrib_es"] / 1e6)
    fig, ax = plt.subplots(figsize=(ANCHO, 2.9))
    _barras_h(ax, etiquetas, valores, [num(v, 0) for v in valores])
    ax.xaxis.set_major_formatter(FMT_MILES)
    ax.set_xlabel("Contribución al ES 97,5% histórico (COP millones)")
    ax.set_xlim(min(0, min(valores) * 1.3), max(max(valores), 1e-9) * 1.15)
    ax.set_title(f"Las {n} posiciones que más aportan a la pérdida en la cola")
    return _guardar(fig, ruta)


def dv01_nodos(tabla: pd.DataFrame, ruta: Path) -> Path:
    nodos = list(C.NODOS_CURVA)
    valores = [tabla[f"krd_{n}"].sum() / 1e6 for n in nodos]
    fig, ax = plt.subplots(figsize=(ANCHO, 2.3))
    x = np.arange(len(nodos))
    ax.bar(x, valores, width=0.55, color=AZUL, zorder=3)
    for xi, v in zip(x, valores):
        ax.text(xi, v, f"{num(v, 2)}", ha="center", va="bottom", fontsize=7.5, color=TINTA)
    ax.set_xticks(x, [C.ETIQUETA_NODO[n] for n in nodos])
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("COP M por +1 pb")
    ax.set_ylim(0, max(valores) * 1.2 if max(valores) > 0 else 1)
    ax.set_title("Sensibilidad por nodo de la curva TES (pérdida ante +1 pb en cada plazo)")
    return _guardar(fig, ruta)


def backtesting(bt: dict, ruta: Path) -> Path:
    f = bt["fechas"]
    fig, ax = plt.subplots(figsize=(ANCHO, 2.8))
    ax.bar(f, bt["pnl"] / 1e6, width=1.2, color=AZUL, alpha=0.75, zorder=3, label="P&G diario hipotético")
    ax.plot(f, -bt["var_hs"] / 1e6, color=TINTA, linewidth=1.5, zorder=4, label="-VaR histórico")
    ax.plot(f, -bt["var_param"] / 1e6, color=NARANJA, linewidth=1.5, zorder=4, label="-VaR paramétrico")
    exc = bt["hs"]["mascara"] | bt["param"]["mascara"]
    ax.scatter(f[exc], bt["pnl"][exc] / 1e6, s=26, color=CRITICO, edgecolor="white", linewidth=1.2,
               zorder=5, label="Excepción (pérdida mayor que algún VaR)")
    ax.axhline(0, color=BASE, linewidth=0.8)
    ax.yaxis.set_major_formatter(FMT_MILES)
    ax.set_ylabel("COP millones")
    meses = pd.date_range(f[0], f[-1], freq="MS")[::2]
    ax.set_xticks(meses, [fecha_corta(m) for m in meses])
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=4, fontsize=7)
    ax.set_title(f"Backtesting: P&G del portafolio actual frente al VaR del día anterior ({bt['n']} días)")
    return _guardar(fig, ruta)


def estres(est: pd.DataFrame, pt: float, limite: float | None, alerta: float | None, ruta: Path) -> Path:
    t = est.sort_values("pnl")
    valores = list(t["pnl"] / pt)
    fig, ax = plt.subplots(figsize=(ANCHO, 2.8))
    _barras_h(ax, t["escenario"], valores, [num(100 * v, 1) + "%" for v in valores])
    ax.axvline(0, color=BASE, linewidth=0.8)
    for umbral, color, texto, lado in ((limite, CRITICO, "Límite", "right"), (alerta, ALERTA, "Alerta", "left")):
        if umbral:
            ax.axvline(-umbral, color=color, linestyle=(0, (4, 2)), linewidth=1.2, zorder=4)
            ax.text(-umbral, ax.get_ylim()[1], f" {texto} -{num(100 * umbral, 1)}% ", ha=lado,
                    va="bottom", fontsize=7, color=TINTA)
    ax.xaxis.set_major_formatter(FMT_PCT0)
    lo, hi = ax.get_xlim()
    ax.set_xlim(min(lo, -(limite or 0) * 1.1) * 1.18, max(hi, 0.01) * 1.35)
    ax.set_xlabel("Pérdida (-) o ganancia (+) como % del patrimonio técnico")
    ax.set_title("Pruebas de estrés sobre el portafolio actual", pad=14)
    return _guardar(fig, ruta)


def concentracion(conc: dict, limite: float | None, alerta: float | None, ruta: Path, n: int = 10) -> Path:
    e = conc["emisores"]
    e = e[~e["exento"]].head(n)
    if e.empty:                      # portafolio sin emisores privados: no hay nada que graficar
        return None
    valores = list(e["pct_portafolio"])
    colores = [CRITICO if (limite and v > limite) else AZUL for v in valores]
    textos = [num(100 * v, 1) + "%" + ("  excede" if (limite and v > limite) else "") for v in valores]
    fig, ax = plt.subplots(figsize=(ANCHO, 2.9))
    _barras_h(ax, e["emisor"], valores, textos, colores)
    for umbral, color, texto, lado in ((limite, CRITICO, "Límite", "left"), (alerta, ALERTA, "Alerta", "right")):
        if umbral:
            ax.axvline(umbral, color=color, linestyle=(0, (4, 2)), linewidth=1.2, zorder=4)
            ax.text(umbral, ax.get_ylim()[1], f" {texto} {num(100 * umbral, 0)}% ", ha=lado,
                    va="bottom", fontsize=7, color=TINTA)
    ax.xaxis.set_major_formatter(FMT_PCT0)
    ax.set_xlim(0, max(max(valores), limite or 0) * 1.3)
    ax.set_title("Exposición por emisor privado (títulos + depósitos), % del portafolio", pad=14)
    return _guardar(fig, ruta)


def liquidez(liq: dict, ruta: Path) -> Path:
    b = liq["bandas"]
    fig, ax = plt.subplots(figsize=(ANCHO, 2.6))
    x = np.arange(len(b))
    ax.bar(x, b["rln_acumulado"] / 1e6, width=0.5, color=AZUL, zorder=3,
           label="Requerimiento neto acumulado (RLN)")
    ax.axhline(liq["alac"] / 1e6, color=TINTA, linewidth=1.5, zorder=4,
               label=f"Activos líquidos ajustados (ALAC): {num(liq['alac'] / 1e6, 0)}")
    etiquetas = [f"Hasta {e.split('-')[1]}\nIRL {num(100 * v, 0)}%" for e, v in zip(b["banda"], b["irl_razon"])]
    ax.set_xticks(x, etiquetas)
    ax.grid(axis="x", visible=False)
    ax.yaxis.set_major_formatter(FMT_MILES)
    ax.set_ylabel("COP millones")
    ax.set_ylim(0, max(liq["alac"], b["rln_acumulado"].max()) / 1e6 * 1.12)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=2, fontsize=7)
    ax.set_title("Liquidez: activos líquidos frente al requerimiento neto acumulado por banda")
    return _guardar(fig, ruta)


def evolucion(hist: pd.DataFrame, limites: pd.DataFrame, ruta: Path) -> Path:
    paneles = [("VAR_HS_1D", "VaR histórico 1 día (COP M)", "num"),
               ("EMISOR_MAX_PCT", "Mayor emisor privado (% portafolio)", "pct"),
               ("IRL_30D", "IRL a 30 días", "pct"),
               ("DURACION_RF", "Duración de la renta fija (años)", "dec")]
    lim = limites.set_index("codigo") if len(limites) else pd.DataFrame()
    fig, ejes = plt.subplots(2, 2, figsize=(ANCHO, 3.9), gridspec_kw={"hspace": 0.55, "wspace": 0.28})
    x = np.arange(len(hist))
    mismo_anio = hist.index.year.nunique() == 1
    etiquetas = [fecha_corta(f)[:3] if mismo_anio else fecha_corta(f) for f in hist.index]
    for ax, (codigo, titulo, fmt) in zip(ejes.flat, paneles):
        y = hist[codigo].to_numpy(dtype=float)
        ax.plot(x, y, color=AZUL, linewidth=2, zorder=4, solid_capstyle="round")
        ax.scatter(x[-1:], y[-1:], s=40, color=AZUL, edgecolor="white", linewidth=1.5, zorder=5)
        f = (lambda v: num(100 * v, 1) + "%") if fmt == "pct" else \
            (lambda v: num(v, 0)) if fmt == "num" else (lambda v: num(v, 2))
        ax.annotate(f(y[-1]), (x[-1], y[-1]), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=7.5, color=TINTA)
        valores_ref = list(y)
        if codigo in lim.index:
            for col, color in (("limite", CRITICO), ("alerta", ALERTA)):
                v = float(lim.loc[codigo, col])
                ax.axhline(v, color=color, linestyle=(0, (4, 2)), linewidth=1.1, zorder=3)
                valores_ref.append(v)
        lo, hi = min(valores_ref), max(valores_ref)
        margen = (hi - lo) * 0.25 or abs(hi) * 0.1 or 1
        ax.set_ylim(lo - margen, hi + margen)
        ax.set_xticks(x, etiquetas)
        ax.set_xlim(-0.3, len(x) - 0.4)
        ax.yaxis.set_major_formatter(FMT_PCT0 if fmt == "pct" else FMT_MILES if fmt == "num"
                                     else FuncFormatter(lambda v, _: num(v, 1)))
        ax.set_title(titulo, fontsize=8)
    nota = "Líneas punteadas: roja = límite, amarilla = alerta."
    if mismo_anio:
        nota = f"Cortes mensuales de {hist.index[0].year}. " + nota
    fig.text(0.01, -0.02, nota, fontsize=7, color=TINTA_2)
    return _guardar(fig, ruta)


def generar_todas(r: dict, hist: pd.DataFrame, carpeta: Path) -> dict:
    carpeta.mkdir(parents=True, exist_ok=True)
    lim = r["limites"].set_index("codigo")

    def umbrales(codigo):
        if codigo in lim.index:
            return float(lim.loc[codigo, "limite"]), float(lim.loc[codigo, "alerta"])
        return None, None

    l_est, a_est = umbrales("ESTRES_PEOR_PCT_PT")
    l_emi, a_emi = umbrales("EMISOR_MAX_PCT")
    return {
        "composicion": composicion(r["concentracion"], carpeta / "01_composicion.png"),
        "distribucion": distribucion_pnl(r["var"], carpeta / "02_distribucion_pyg.png"),
        "factores": var_por_factor(r["var"], carpeta / "03_var_por_factor.png"),
        "contribucion": contribucion_posiciones(r["tabla"], carpeta / "04_contribucion.png"),
        "dv01": dv01_nodos(r["tabla"], carpeta / "05_sensibilidad_nodos.png"),
        "backtesting": backtesting(r["backtesting"], carpeta / "06_backtesting.png"),
        "estres": estres(r["estres"], r["patrimonio_tecnico"], l_est, a_est, carpeta / "07_estres.png"),
        "concentracion": concentracion(r["concentracion"], l_emi, a_emi, carpeta / "08_concentracion.png"),
        "liquidez": liquidez(r["liquidez"], carpeta / "09_liquidez.png"),
        "evolucion": evolucion(hist, r["limites"], carpeta / "10_evolucion.png") if len(hist) >= 2 else None,
    }
