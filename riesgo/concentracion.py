"""Riesgo de concentración: por emisor (unificado), sector, calificación,
plazo y tipo de instrumento, con el índice Herfindahl-Hirschman (HHI).

La exposición por emisor suma TODO lo que la entidad tiene con esa
contraparte: títulos y depósitos a la vista. La Nación y los emisores
marcados como exentos en el maestro no cuentan para el límite individual.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

TRAMOS_PLAZO = [("Hasta 1 año", 0, 1), ("1 a 3 años", 1, 3), ("3 a 5 años", 3, 5),
                ("5 a 10 años", 5, 10), ("Más de 10 años", 10, 1e9)]


def _tramo(fila) -> str:
    if fila["tipo"] == "LIQUIDEZ":
        return "A la vista"
    if fila["tipo"] not in C.RENTA_FIJA:
        return "Sin vencimiento"
    for etiqueta, a, b in TRAMOS_PLAZO:
        if a <= fila["plazo_anios"] < b:
            return etiqueta
    return TRAMOS_PLAZO[-1][0]


def _participacion(tabla, columna, total, orden=None) -> pd.DataFrame:
    s = tabla.groupby(columna, sort=False)["valor"].sum()
    if orden:
        s = s.reindex([o for o in orden if o in s.index] + [i for i in s.index if i not in orden])
    else:
        s = s.sort_values(ascending=False)
    return pd.DataFrame({"valor": s, "pct": s / total}).reset_index().rename(columns={columna: "grupo"})


def calcular_concentracion(tabla: pd.DataFrame, patrimonio_tecnico: float) -> dict:
    total = float(tabla["valor"].sum())
    emisores = (tabla.groupby("emisor", sort=False)
                .agg(valor=("valor", "sum"), titulos=("valor", "size"),
                     sector=("sector", "first"), calificacion=("calificacion_lp", "first"),
                     exento=("exento", "first"),
                     nombres=("emisor_original", lambda s: sorted({x.strip() for x in s})))
                .sort_values("valor", ascending=False))
    emisores["pct_portafolio"] = emisores["valor"] / total
    emisores["pct_pt"] = emisores["valor"] / patrimonio_tecnico
    emisores["n_nombres"] = emisores["nombres"].map(len)

    privados = emisores[~emisores["exento"]]
    if privados.empty:            # p. ej., un portafolio solo en TES
        hhi, emisor_max, max_manual_mismo_emisor, nombres = 0.0, "Ninguno", 0.0, []
    else:
        cuotas = privados["valor"] / privados["valor"].sum()
        hhi = float((cuotas ** 2).sum() * 1e4)
        # Lo que habría mostrado un control manual que agrupa por el nombre tal como
        # está escrito (Excel no distingue mayúsculas, pero sí 'S.A.' o 'Bco.')
        nombre_excel = tabla["emisor_original"].str.strip().str.casefold()
        manual = tabla.groupby(nombre_excel)["valor"].sum() / total
        emisor_max = privados.index[0]
        nombres = emisores.loc[emisor_max, "nombres"]
        nombres_max = {n.casefold() for n in nombres}
        max_manual_mismo_emisor = float(manual[manual.index.isin(nombres_max)].max())

    t = tabla.copy()
    t["calificacion_grupo"] = t["calificacion_lp"].fillna("Sin calificación").replace({"NACION": "Nación"})
    t["tramo"] = t.apply(_tramo, axis=1)
    t["tipo_nombre"] = t["tipo"].map(C.NOMBRE_TIPO)
    orden_cal = ["Nación"] + C.ESCALA[1:] + ["Sin calificación"]
    rf = t["tipo"].isin(C.RENTA_FIJA)
    idx_a_mas = C.ESCALA.index("A+")
    bajo_a = rf & t["calificacion_lp"].map(lambda c: c in C.ESCALA and C.ESCALA.index(c) >= idx_a_mas)

    return {
        "total": total, "emisores": emisores.reset_index(),
        "hhi_privados": hhi, "n_equivalente": 1e4 / hhi if hhi > 0 else np.nan,
        "top5_pct": float(privados["valor"].head(5).sum() / total),
        "emisor_max": emisor_max,
        "emisor_max_pct": float(privados["pct_portafolio"].iloc[0]) if len(privados) else 0.0,
        "emisor_max_pct_manual": max_manual_mismo_emisor,
        "emisor_max_nombres": nombres,
        "por_sector": _participacion(t, "sector", total),
        "por_calificacion": _participacion(t, "calificacion_grupo", total, orden_cal),
        "por_plazo": _participacion(t, "tramo", total, ["A la vista"] + [x[0] for x in TRAMOS_PLAZO]
                                    + ["Sin vencimiento"]),
        "por_tipo": _participacion(t, "tipo_nombre", total),
        "calif_a_o_inferior_pct": float(t.loc[bajo_a, "valor"].sum() / total),
        "rv_pct": float(t.loc[t["tipo"] == "RENTA_VARIABLE", "valor"].sum() / total),
        "usd_pct_pt": float(t.loc[t["tipo"] == "DIVISA", "valor"].sum() / patrimonio_tecnico),
    }
