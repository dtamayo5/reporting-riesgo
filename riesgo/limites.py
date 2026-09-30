"""Indicadores y semáforo de límites.

  Máximo: ROJO si valor > límite; ÁMBAR si valor > alerta; VERDE en otro caso.
  Mínimo: ROJO si valor < límite; ÁMBAR si valor < alerta; VERDE en otro caso.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .utilidades import num, pct

ESTADOS = ("ROJO", "ÁMBAR", "VERDE", "SIN DATO")


def calcular_indicadores(r: dict) -> dict:
    """Todos los indicadores del corte, en las unidades de la política:
    % como fracción, COP M en millones, el resto en su unidad natural."""
    pt = r["patrimonio_tecnico"]
    var, bt, conc, liq = r["var"], r["backtesting"], r["concentracion"], r["liquidez"]
    tabla = r["tabla"]
    rf = tabla[tabla["es_renta_fija"]]
    duracion = float((rf["duracion_mod"] * rf["valor"]).sum() / rf["valor"].sum()) if len(rf) else 0.0
    peor = r["estres"].loc[r["estres"]["pnl"].idxmin()]
    return {
        "VALOR_PORTAFOLIO": var["valor_total"] / 1e6,
        "PATRIMONIO_TECNICO": pt / 1e6,
        "VAR_HS_1D": var["var_hs"] / 1e6,
        "ES_HS_1D": var["es_hs"] / 1e6,
        "VAR_PARAM_1D": var["var_param"] / 1e6,
        "VAR_HS_10D": var["var_hs_10d"] / 1e6,
        "VAR_HS_10D_PCT_PT": var["var_hs_10d"] / pt,
        "VAR_HS_1D_PCT_PORT": var["var_hs"] / var["valor_total"],
        "DURACION_RF": duracion,
        "DV01_TOTAL": float(tabla["dv01"].sum()) / 1e6,
        "ESTRES_PEOR_PCT_PT": max(-float(peor["pnl"]), 0.0) / pt,
        "ESTRES_PEOR_ESCENARIO": peor["escenario"],
        "BT_EXCEPCIONES_HS": bt["hs"]["excepciones"],
        "BT_EXCEPCIONES_PARAM": bt["param"]["excepciones"],
        "USD_PCT_PT": conc["usd_pct_pt"],
        "RV_PCT": conc["rv_pct"],
        "EMISOR_MAX_PCT": conc["emisor_max_pct"],
        "EMISOR_MAX_NOMBRE": conc["emisor_max"],
        "HHI_PRIVADOS": conc["hhi_privados"],
        "TOP5_PCT": conc["top5_pct"],
        "CALIF_A_O_INF_PCT": conc["calif_a_o_inferior_pct"],
        "IRL_7D": liq["irl_7"],
        "IRL_30D": liq["irl_30"],
        "IRL_90D": liq["irl_90"],
        "ALAC": liq["alac"] / 1e6,
        "ERRORES_DATOS": r["hallazgos"].conteo("ERROR"),
        "ADVERTENCIAS_DATOS": r["hallazgos"].conteo("ADVERTENCIA"),
    }


def formatear(valor, unidad: str) -> str:
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return "-"
    if unidad == "%":
        return pct(valor, 1)
    if unidad == "COP M":
        return f"{num(valor, 1)} M"
    if unidad == "años":
        return f"{num(valor, 2)} años"
    if unidad in ("número", "puntos"):
        return num(valor, 0)
    return num(valor, 2)


def evaluar_limites(limites: pd.DataFrame, ind: dict) -> pd.DataFrame:
    detalles = {
        "EMISOR_MAX_PCT": lambda: ind["EMISOR_MAX_NOMBRE"],
        "ESTRES_PEOR_PCT_PT": lambda: ind["ESTRES_PEOR_ESCENARIO"],
    }
    filas = []
    for _, l in limites.iterrows():
        v = ind.get(l["codigo"])
        if v is None or (isinstance(v, float) and np.isnan(v)):
            estado, uso = "SIN DATO", np.nan
        elif l["tipo"] == "MAX":
            estado = "ROJO" if v > l["limite"] else "ÁMBAR" if v > l["alerta"] else "VERDE"
            uso = v / l["limite"] if l["limite"] else np.nan
        else:
            estado = "ROJO" if v < l["limite"] else "ÁMBAR" if v < l["alerta"] else "VERDE"
            uso = l["limite"] / v if v else np.nan
        filas.append({
            "codigo": l["codigo"], "indicador": l["indicador"], "categoria": l["categoria"],
            "tipo": "Máximo" if l["tipo"] == "MAX" else "Mínimo", "unidad": l["unidad"],
            "valor": v, "limite": l["limite"], "alerta": l["alerta"], "uso": uso, "estado": estado,
            "valor_txt": formatear(v, l["unidad"]), "limite_txt": formatear(l["limite"], l["unidad"]),
            "alerta_txt": formatear(l["alerta"], l["unidad"]),
            "detalle": detalles.get(l["codigo"], lambda: "")(),
        })
    df = pd.DataFrame(filas)
    df["_o"] = df["estado"].map({e: i for i, e in enumerate(ESTADOS)})
    return df.sort_values(["_o"], kind="stable").drop(columns="_o").reset_index(drop=True)
