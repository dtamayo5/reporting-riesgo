"""Riesgo de mercado: VaR histórico y paramétrico, Expected Shortfall,
contribuciones, backtesting y pruebas de estrés.

Dos métodos, a propósito:
  - Simulación histórica (medida principal): aplica al portafolio de HOY los
    cambios diarios reales de los últimos 500 días y lo revalúa por completo.
    Captura colas pesadas, correlaciones de crisis y convexidad.
  - Paramétrico delta-normal con covarianza EWMA (RiskMetrics, lambda 0,94):
    rápido y descomponible, pero supone normalidad. El backtesting muestra
    cuándo esa suposición falla.
"""
from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import pandas as pd

from . import config as C
from .mercado import F, IDX, IDX_NODOS, PLAZOS_NODOS, Mercado, covarianzas_ewma
from .valoracion import Portafolio

_N = NormalDist()
Z_VAR = _N.inv_cdf(C.CONFIANZA_VAR)
Z_ES = _N.inv_cdf(C.CONFIANZA_ES)
FACTOR_ES_NORMAL = _N.pdf(Z_ES) / (1 - C.CONFIANZA_ES)


class ErrorRiesgo(Exception):
    pass


def var_es(pnl: np.ndarray):
    """VaR y ES históricos (positivos = pérdida)."""
    q_var = np.quantile(pnl, 1 - C.CONFIANZA_VAR)
    q_es = np.quantile(pnl, 1 - C.CONFIANZA_ES)
    return float(-q_var), float(-pnl[pnl <= q_es].mean())


def _mascara(factores) -> np.ndarray:
    return np.array([f in factores for f in C.FACTORES])


# ------------------------------------------------------------------- VaR ----
def calcular_var(port: Portafolio, mercado: Mercado, corte: pd.Timestamp) -> dict:
    L = mercado.matriz()
    c = mercado.indice(corte)
    minimo = C.VENTANA_HS + C.VENTANA_BACKTEST + 2
    if c < minimo:
        raise ErrorRiesgo(f"Se necesitan al menos {minimo} días de historia de mercado antes del corte.")
    D = Mercado.cambios(L[:c + 1])            # D[j] = cambio del día j al j+1
    L0 = L[c]
    V0 = port.valorar(L0)[0]

    # Simulación histórica con revaluación completa
    Dh = D[-C.VENTANA_HS:]
    pnl_pos = port.valorar(Mercado.aplicar(L0, Dh)) - V0          # (H x P)
    pnl = pnl_pos.sum(axis=1)
    var_hs, es_hs = var_es(pnl)
    cola = pnl <= np.quantile(pnl, 1 - C.CONFIANZA_ES)
    contrib_es = -pnl_pos[cola].mean(axis=0)                      # suma exactamente el ES

    # VaR histórico por grupo de factores (moviendo solo ese grupo)
    grupos_hs = {}
    for grupo, factores in C.GRUPOS_FACTORES.items():
        Dg = np.where(_mascara(factores), Dh, 0.0)
        grupos_hs[grupo] = var_es((port.valorar(Mercado.aplicar(L0, Dg)) - V0).sum(axis=1))[0]

    # Paramétrico delta-normal con covarianza EWMA
    sig_hist = covarianzas_ewma(D)
    S = sig_hist[-1]
    sens = port.sensibilidades(L0)                                # (P x F)
    s = sens.sum(axis=0)
    sigma = math.sqrt(max(float(s @ S @ s), 0.0))
    comp_param = (Z_VAR * (sens @ (S @ s)) / sigma if sigma > 0    # Euler: suma el VaR
                  else np.zeros(port.P))
    grupos_param = {}
    for grupo, factores in C.GRUPOS_FACTORES.items():
        m = _mascara(factores)
        sg = np.where(m, s, 0.0)
        grupos_param[grupo] = Z_VAR * math.sqrt(max(float(sg @ S @ sg), 0.0))

    fechas = mercado.df.index[c - C.VENTANA_HS + 1:c + 1]
    peores = np.argsort(pnl)[:5]
    return {
        "V0": V0, "valor_total": float(V0.sum()), "pnl_hs": pnl, "fechas_hs": fechas,
        "var_hs": var_hs, "es_hs": es_hs, "contrib_es": contrib_es,
        "grupos_hs": grupos_hs, "diversificacion_hs": sum(grupos_hs.values()) - var_hs,
        "var_param": Z_VAR * sigma, "es_param": sigma * FACTOR_ES_NORMAL, "sigma_param": sigma,
        "comp_param": comp_param, "grupos_param": grupos_param,
        "diversificacion_param": sum(grupos_param.values()) - Z_VAR * sigma,
        "sensibilidades": sens, "cambios": D, "sig_hist": sig_hist,
        "peores_dias": [(fechas[i], float(pnl[i])) for i in peores],
        "var_hs_10d": var_hs * math.sqrt(C.DIAS_HORIZONTE_REGULATORIO),
        "es_hs_10d": es_hs * math.sqrt(C.DIAS_HORIZONTE_REGULATORIO),
    }


# ----------------------------------------------------------- backtesting ----
def kupiec(x: int, n: int, p: float):
    """Prueba de cobertura incondicional (proporción de fallas)."""
    if x == 0:
        lr = -2 * n * math.log(1 - p)
    elif x == n:
        lr = -2 * n * math.log(p)
    else:
        f = x / n
        lr = -2 * ((n - x) * math.log(1 - p) + x * math.log(p)
                   - (n - x) * math.log(1 - f) - x * math.log(f))
    lr = max(lr, 0.0)
    return lr, math.erfc(math.sqrt(lr / 2))


def christoffersen(excepciones: np.ndarray):
    """Prueba de independencia: ¿las excepciones llegan en racimos?"""
    e = excepciones.astype(int)
    a, b = e[:-1], e[1:]
    n00, n01 = int(((a == 0) & (b == 0)).sum()), int(((a == 0) & (b == 1)).sum())
    n10, n11 = int(((a == 1) & (b == 0)).sum()), int(((a == 1) & (b == 1)).sum())

    def xlog(x, y):
        return x * math.log(y) if x > 0 else 0.0

    pi0 = n01 / (n00 + n01) if n00 + n01 else 0.0
    pi1 = n11 / (n10 + n11) if n10 + n11 else 0.0
    pi = (n01 + n11) / max(n00 + n01 + n10 + n11, 1)
    l_ind = xlog(n00, 1 - pi0) + xlog(n01, pi0) + xlog(n10, 1 - pi1) + xlog(n11, pi1)
    l_0 = xlog(n00 + n10, 1 - pi) + xlog(n01 + n11, pi)
    lr = max(-2 * (l_0 - l_ind), 0.0)
    return lr, math.erfc(math.sqrt(lr / 2))


def zona_basilea(x: int, n: int, p: float = 1 - C.CONFIANZA_VAR) -> str:
    """Semáforo de Basilea: verde si P(X <= x) < 95%, amarilla si < 99,99%."""
    acumulada = sum(math.comb(n, k) * p ** k * (1 - p) ** (n - k) for k in range(x + 1))
    return "Verde" if acumulada < 0.95 else "Amarilla" if acumulada < 0.9999 else "Roja"


def backtesting(port: Portafolio, mercado: Mercado, corte: pd.Timestamp, res_var: dict) -> dict:
    """Backtesting hipotético: el portafolio de hoy, mantenido fijo, contra los
    últimos 250 días. Cada VaR se calcula SOLO con información del día anterior."""
    L = mercado.matriz()
    c = mercado.indice(corte)
    B, H = C.VENTANA_BACKTEST, C.VENTANA_HS
    D, sig_hist = res_var["cambios"], res_var["sig_hist"]

    V = port.valorar(L[c - B:c + 1]).sum(axis=1)
    pnl = np.diff(V)
    var_hs, var_param = np.empty(B), np.empty(B)
    for k, i in enumerate(range(c - B + 1, c + 1)):
        base = L[i - 1]
        vb = port.valorar(base)[0].sum()
        vs = port.valorar(Mercado.aplicar(base, D[i - 1 - H:i - 1])).sum(axis=1)
        var_hs[k] = -np.quantile(vs - vb, 1 - C.CONFIANZA_VAR)
        s = port.sensibilidades(base).sum(axis=0)
        var_param[k] = Z_VAR * math.sqrt(max(float(s @ sig_hist[i - 2] @ s), 0.0))

    salida = {"fechas": mercado.df.index[c - B + 1:c + 1], "pnl": pnl,
              "var_hs": var_hs, "var_param": var_param, "n": B}
    p = 1 - C.CONFIANZA_VAR
    for nombre, v in (("hs", var_hs), ("param", var_param)):
        exc = pnl < -v
        x = int(exc.sum())
        lr_k, p_k = kupiec(x, B, p)
        lr_c, p_c = christoffersen(exc)
        salida[nombre] = {"excepciones": x, "mascara": exc, "kupiec_lr": lr_k, "kupiec_p": p_k,
                          "christoffersen_lr": lr_c, "christoffersen_p": p_c,
                          "zona": zona_basilea(x, B, p), "esperadas": B * p}
    return salida


# ---------------------------------------------------------------- estrés ----
def _choque_hipotetico(e) -> np.ndarray:
    d = np.zeros(F)
    peso_largo = np.clip((PLAZOS_NODOS - 0.25) / (10.0 - 0.25), 0.0, 1.0)
    d[IDX_NODOS] = e["paralelo_bp"] + e["corto_bp"] + (e["largo_bp"] - e["corto_bp"]) * peso_largo
    d[IDX["SPR_AAA"]] = e["spr_aaa_bp"]
    d[IDX["SPR_AA"]] = e["spr_aa_bp"]
    d[IDX["TRM"]] = math.log(1 + e["trm_pct"])
    d[IDX["COLCAP"]] = math.log(1 + e["rv_pct"])
    return d


def _describir(d: np.ndarray) -> str:
    return (f"TES 2A {d[IDX['TES_2A']]:+.0f} pb, TES 10A {d[IDX['TES_10A']]:+.0f} pb, "
            f"AAA {d[IDX['SPR_AAA']]:+.0f} pb, AA {d[IDX['SPR_AA']]:+.0f} pb, "
            f"TRM {100 * (math.exp(d[IDX['TRM']]) - 1):+.1f}%, "
            f"RV {100 * (math.exp(d[IDX['COLCAP']]) - 1):+.1f}%").replace(".", ",")


def pruebas_estres(port: Portafolio, mercado: Mercado, corte: pd.Timestamp,
                   escenarios: pd.DataFrame, V0: np.ndarray) -> pd.DataFrame:
    L = mercado.matriz()
    c = mercado.indice(corte)
    L0, W = L[c], C.DIAS_VENTANA_ESTRES_HIST
    fechas = mercado.df.index
    filas = []
    for _, e in escenarios.iterrows():
        ventana = ""
        if e["historico"]:
            ini = int(fechas.searchsorted(e["desde"]))
            fin = min(int(fechas.searchsorted(e["hasta"], side="right")) - 1, c)
            inicios = np.arange(ini, fin - W + 1)
            if len(inicios) == 0:
                continue
            choques = np.vstack([Mercado.cambios(np.vstack([L[s], L[s + W]]))[0] for s in inicios])
            pnl_ventanas = (port.valorar(Mercado.aplicar(L0, choques)) - V0).sum(axis=1)
            peor = int(np.argmin(pnl_ventanas))
            d = choques[peor]
            s0 = inicios[peor]
            ventana = f"{fechas[s0]:%d/%m/%Y} a {fechas[s0 + W]:%d/%m/%Y}"
        else:
            d = _choque_hipotetico(e)
        pnl_pos = port.valorar(Mercado.aplicar(L0, d[None, :]))[0] - V0
        filas.append({"codigo": e["codigo"], "escenario": e["nombre"],
                      "tipo": "Histórico" if e["historico"] else "Hipotético",
                      "pnl": float(pnl_pos.sum()), "choque": _describir(d), "ventana": ventana,
                      "posicion_mas_afectada": int(np.argmin(pnl_pos)),
                      "pnl_posicion_mas_afectada": float(pnl_pos.min())})
    return pd.DataFrame(filas)
