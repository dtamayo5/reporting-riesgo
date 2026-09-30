"""Riesgo de liquidez: IRL simplificado por bandas de tiempo.

Inspirado en la lógica del estándar regulatorio colombiano (activos líquidos
ajustados por haircuts frente al requerimiento de liquidez neto por bandas),
pero SIMPLIFICADO: antes de usarlo como reporte oficial se debe ajustar a la
metodología exacta del supervisor de cada entidad.

  ALAC  = suma( valor x (1 - haircut) ) de los activos no restringidos
  RLN   = salidas contractuales + retiros estimados de depósitos a la vista
          - entradas contractuales (con tope del 75% de las salidas)
  IRL razón (acumulado a la banda k) = ALAC / RLN acumulado hasta k
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .utilidades import normalizar

DESCRIPCION_CATEGORIA = {
    "LIQUIDEZ": "Disponible y FIC a la vista",
    "TES_HASTA_1A": "TES hasta 1 año", "TES_1A_5A": "TES de 1 a 5 años",
    "TES_MAS_5A": "TES a más de 5 años", "PRIVADO_AAA": "Renta fija privada AAA",
    "PRIVADO_AA": "Renta fija privada AA+ a AA-", "PRIVADO_INFERIOR": "Renta fija privada A+ o inferior",
    "RENTA_VARIABLE": "Renta variable", "DIVISA": "Moneda extranjera",
    "RESTRINGIDO": "Restringido / en garantía (no computa)",
}


def categoria_haircut(fila) -> str:
    if fila["restringido"]:
        return "RESTRINGIDO"
    tipo = fila["tipo"]
    if tipo == "LIQUIDEZ":
        return "LIQUIDEZ"
    if tipo == "TES_TF":
        p = fila["plazo_anios"]
        return "TES_HASTA_1A" if p <= 1 else "TES_1A_5A" if p <= 5 else "TES_MAS_5A"
    if tipo in C.RENTA_FIJA:
        cal = fila["calificacion_lp"]
        if cal in ("NACION", "AAA"):
            return "PRIVADO_AAA"
        return "PRIVADO_AA" if cal in ("AA+", "AA", "AA-") else "PRIVADO_INFERIOR"
    return "RENTA_VARIABLE" if tipo == "RENTA_VARIABLE" else "DIVISA"


def activos_liquidos(tabla: pd.DataFrame, haircuts: dict) -> pd.DataFrame:
    t = tabla[["id", "especie", "tipo", "emisor", "valor", "restringido",
               "plazo_anios", "calificacion_lp"]].copy()
    t["categoria"] = t.apply(categoria_haircut, axis=1)
    t["haircut"] = [1.0 if c == "RESTRINGIDO" else haircuts.get(c, 1.0) for c in t["categoria"]]
    t["alac"] = t["valor"] * (1 - t["haircut"])
    return t


def calcular_liquidez(tabla: pd.DataFrame, flujos: pd.DataFrame, depositos: pd.DataFrame,
                      politica: dict) -> dict:
    activos = activos_liquidos(tabla, politica["haircuts"])
    alac = float(activos["alac"].sum())
    param = politica["liquidez"]
    tope = param.get("tope de entradas", 0.75)
    saldo_vista = float(depositos["saldo"].sum()) if len(depositos) else 0.0

    filas, acumulado = [], 0.0
    for etiqueta, d0, d1 in C.BANDAS_LIQUIDEZ:
        f = flujos[(flujos["dias"] >= d0) & (flujos["dias"] <= d1)]
        sc = float(f.loc[f["sentido"] == "SALIDA", "monto"].sum())
        ec = float(f.loc[f["sentido"] == "ENTRADA", "monto"].sum())
        snc = saldo_vista * param.get(normalizar(etiqueta), 0.0)
        ec_comp = min(ec, tope * (sc + snc))
        rln = sc + snc - ec_comp
        acumulado += rln
        filas.append({
            "banda": etiqueta, "salidas_contractuales": sc, "retiros_estimados": snc,
            "entradas": ec, "entradas_computables": ec_comp, "rln": rln,
            "rln_acumulado": acumulado, "alac": alac, "irl_monto": alac - acumulado,
            "irl_razon": alac / acumulado if acumulado > 0 else np.inf,
        })
    bandas = pd.DataFrame(filas)
    resumen_cat = (activos.groupby("categoria", sort=False)
                   .agg(valor=("valor", "sum"), alac=("alac", "sum"), haircut=("haircut", "first"))
                   .reset_index())
    resumen_cat["descripcion"] = resumen_cat["categoria"].map(DESCRIPCION_CATEGORIA)
    return {
        "alac": alac, "activos": activos, "resumen_activos": resumen_cat, "bandas": bandas,
        "saldo_vista": saldo_vista,
        "irl_7": float(bandas["irl_razon"].iloc[0]),
        "irl_30": float(bandas["irl_razon"].iloc[2]),
        "irl_90": float(bandas["irl_razon"].iloc[3]),
        "flujos_fuera_horizonte": int((flujos["dias"] > C.BANDAS_LIQUIDEZ[-1][2]).sum()),
    }
