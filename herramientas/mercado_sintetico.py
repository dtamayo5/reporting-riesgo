"""
Mercado sintético para la demostración.

Genera una historia diaria (días hábiles, 2022-2026) de los factores de riesgo
que usa el motor: curva cero cupón TES, spreads de crédito AAA y AA, TRM,
un índice accionario local e IBR.

No son datos oficiales. La serie sigue de forma aproximada los grandes
episodios del mercado colombiano -la venta masiva de TES de octubre de 2022,
el ciclo de recortes de 2024-2025, las alzas de la tasa de política de 2026 y
el repunte de los TES tras las elecciones de junio de 2026- para que la demo se
comporte como un mercado real: colas pesadas, volatilidad en racimos y saltos
en días de decisiones de política monetaria.

En producción este archivo se reemplaza por las curvas del proveedor de
precios de la entidad (o la curva cero cupón TES del Banco de la República),
con el mismo formato de columnas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Nodos de la curva (años) en el mismo orden que riesgo/config.py
NODOS = {"TES_3M": 0.25, "TES_1A": 1.0, "TES_2A": 2.0, "TES_3A": 3.0,
         "TES_5A": 5.0, "TES_7A": 7.0, "TES_10A": 10.0, "TES_15A": 15.0}
LAMBDA_NS = 0.7   # parámetro de forma Nelson-Siegel

# Anclas aproximadas: fecha, TES 3M, TES 10A, curvatura NS, spread AAA (pb),
# spread AA (pb), TRM, índice accionario. Fechas consecutivas = saltos de un día.
ANCLAS = [
    ("2022-01-03", 3.5, 8.6, 2.2, 80, 160, 4000, 1410),
    ("2022-03-31", 5.6, 9.8, 2.0, 85, 170, 3750, 1550),
    ("2022-06-30", 8.4, 11.8, 1.5, 95, 185, 4150, 1300),
    ("2022-09-30", 11.0, 12.9, 1.2, 110, 210, 4530, 1190),
    ("2022-10-17", 11.2, 13.4, 1.2, 115, 220, 4650, 1180),
    ("2022-10-18", 11.4, 14.0, 1.2, 125, 240, 4720, 1165),   # venta masiva de TES
    ("2022-10-19", 11.6, 14.6, 1.1, 135, 260, 4790, 1150),
    ("2022-10-20", 11.7, 14.9, 1.1, 145, 280, 4850, 1140),
    ("2022-10-21", 11.9, 15.4, 1.0, 155, 300, 4920, 1130),
    ("2022-10-24", 12.0, 15.8, 1.0, 165, 320, 4950, 1150),
    ("2022-11-03", 12.1, 15.0, 1.0, 170, 330, 5061, 1140),
    ("2022-12-30", 12.6, 13.2, 1.0, 150, 290, 4810, 1286),
    ("2023-06-30", 13.0, 11.0, 0.3, 120, 230, 4190, 1100),
    ("2023-12-29", 12.4, 10.1, -0.3, 110, 210, 3820, 1195),
    ("2024-06-28", 10.9, 10.7, 0.2, 100, 195, 4150, 1350),
    ("2024-12-31", 9.3, 11.4, 0.8, 95, 185, 4410, 1380),
    ("2025-06-30", 9.0, 12.0, 1.2, 95, 180, 4070, 1650),
    ("2025-09-16", 9.1, 12.1, 1.2, 95, 180, 3897, 1800),
    ("2025-12-31", 9.6, 12.4, 1.3, 100, 190, 3757, 1950),
    ("2026-01-29", 10.1, 12.6, 1.3, 102, 195, 3720, 1960),
    ("2026-01-30", 10.5, 12.85, 1.3, 106, 202, 3740, 1945),  # alza de 100 pb de la TPM
    ("2026-03-30", 10.9, 13.8, 1.2, 112, 215, 3650, 1900),
    ("2026-03-31", 11.4, 14.2, 1.2, 122, 230, 3690, 1870),   # alza de 100 pb de la TPM
    ("2026-04-14", 11.6, 14.8, 1.1, 128, 245, 3700, 1880),   # pico de la venta de TES
    ("2026-05-29", 11.8, 13.6, 1.0, 118, 232, 3560, 1990),
    ("2026-06-01", 11.7, 13.1, 1.0, 110, 220, 3490, 2070),   # repunte post-elecciones
    ("2026-06-12", 11.8, 12.8, 1.0, 110, 220, 3470, 2060),
    ("2026-06-29", 11.9, 12.7, 1.0, 110, 220, 3420, 2040),
    ("2026-06-30", 12.2, 12.85, 1.0, 112, 224, 3440, 2030),  # alza de 75 pb de la TPM
    ("2026-07-31", 12.3, 12.6, 1.0, 110, 220, 3300, 2050),
    ("2026-08-31", 12.2, 12.5, 1.0, 108, 215, 3214, 2080),
    ("2026-09-16", 12.2, 12.45, 1.0, 109, 216, 3100, 2090),
    ("2026-09-30", 12.25, 12.5, 1.0, 110, 218, 3120, 2100),
]

# Tasa de política monetaria (aprox.) para construir el IBR
TPM = [("2022-01-03", 3.0), ("2022-01-31", 4.0), ("2022-03-31", 5.0), ("2022-04-29", 6.0),
       ("2022-06-30", 7.5), ("2022-07-29", 9.0), ("2022-09-30", 10.0), ("2022-10-31", 11.0),
       ("2022-12-16", 12.0), ("2023-01-31", 12.75), ("2023-03-31", 13.0), ("2023-04-28", 13.25),
       ("2023-12-19", 13.0), ("2024-01-31", 12.75), ("2024-03-22", 12.25), ("2024-04-30", 11.75),
       ("2024-06-28", 11.25), ("2024-07-31", 10.75), ("2024-09-30", 10.25), ("2024-10-31", 9.75),
       ("2024-12-19", 9.5), ("2025-04-30", 9.25), ("2026-01-30", 10.25), ("2026-03-31", 11.25),
       ("2026-06-30", 12.0)]

# Regímenes de volatilidad (multiplicador sobre la volatilidad base)
REGIMENES = [("2022-09-15", "2022-12-15", 2.2), ("2026-03-01", "2026-04-30", 1.8),
             ("2026-05-15", "2026-06-15", 1.5)]

# Volatilidad diaria base: corto (pb), largo (pb), curvatura (pb), spread AAA (pb),
# spread AA (pb), log TRM, log índice accionario
SIGMA = np.array([4.0, 6.0, 6.0, 1.2, 2.0, 0.0060, 0.0080])
PHI = np.array([0.97, 0.97, 0.97, 0.98, 0.98, 0.97, 0.97])   # reversión a las anclas
CORR = np.array([
    # corto  largo  curv  AAA    AA     TRM    RV
    [1.00, 0.60, 0.10, 0.20, 0.15, 0.30, -0.20],
    [0.60, 1.00, 0.10, 0.30, 0.25, 0.45, -0.35],
    [0.10, 0.10, 1.00, 0.05, 0.05, 0.05, -0.05],
    [0.20, 0.30, 0.05, 1.00, 0.70, 0.25, -0.25],
    [0.15, 0.25, 0.05, 0.70, 1.00, 0.30, -0.30],
    [0.30, 0.45, 0.05, 0.25, 0.30, 1.00, -0.45],
    [-0.20, -0.35, -0.05, -0.25, -0.30, -0.45, 1.00],
])


def _ns_cargas(tau):
    x = LAMBDA_NS * np.asarray(tau, dtype=float)
    g1 = (1 - np.exp(-x)) / x
    return g1, g1 - np.exp(-x)


def _curva(corto, largo, curv):
    """Curva Nelson-Siegel que pasa por el TES 3M y el TES 10A dados."""
    g1s, g2s = _ns_cargas(0.25)
    g1l, g2l = _ns_cargas(10.0)
    b1 = ((corto - curv * g2s) - (largo - curv * g2l)) / (g1s - g1l)
    b0 = largo - curv * g2l - b1 * g1l
    g1, g2 = _ns_cargas(np.array(list(NODOS.values())))
    return b0[:, None] + b1[:, None] * g1 + curv[:, None] * g2


def generar(semilla: int = 2026, inicio="2022-01-03", fin="2026-09-30") -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    fechas = pd.bdate_range(inicio, fin)
    T = len(fechas)

    # Anclas interpoladas día a día (lineal; logarítmica para TRM e índice)
    a = pd.DataFrame(ANCLAS, columns=["fecha", "corto", "largo", "curv", "aaa", "aa", "trm", "rv"])
    a["fecha"] = pd.to_datetime(a["fecha"])
    a = a.set_index("fecha")
    a["trm"], a["rv"] = np.log(a["trm"]), np.log(a["rv"])
    ancla = a.reindex(a.index.union(fechas)).interpolate(method="time").reindex(fechas)
    ancla = ancla.to_numpy()

    # Volatilidad: régimen x agrupamiento tipo GARCH(1,1)
    regimen = np.ones(T)
    for d, h, mult in REGIMENES:
        regimen[(fechas >= d) & (fechas <= h)] = mult

    chol = np.linalg.cholesky(CORR)
    nu = 5.0
    z = rng.standard_t(nu, size=(T, 7)) * np.sqrt((nu - 2) / nu)
    z = z @ chol.T
    desv = np.zeros((T, 7))
    g2 = 1.0
    for t in range(1, T):
        g2 = 0.05 + 0.10 * z[t - 1, 1] ** 2 + 0.85 * g2
        vol = SIGMA * regimen[t] * np.sqrt(g2)
        desv[t] = PHI * desv[t - 1] + vol * z[t]

    corto = ancla[:, 0] + desv[:, 0] / 100
    largo = ancla[:, 1] + desv[:, 1] / 100
    curv = ancla[:, 2] + desv[:, 2] / 100
    curva = _curva(corto, largo, curv)
    # Ruido propio de cada nodo (para que el riesgo por nodo no sea degenerado)
    ruido = np.zeros((T, len(NODOS)))
    for t in range(1, T):
        ruido[t] = 0.9 * ruido[t - 1] + rng.normal(0, 1.0, len(NODOS))
    curva = curva + ruido / 100

    df = pd.DataFrame(curva, index=fechas, columns=list(NODOS))
    df["SPR_AAA"] = np.maximum(ancla[:, 3] + desv[:, 3], 20)
    df["SPR_AA"] = np.maximum(ancla[:, 4] + desv[:, 4], df["SPR_AAA"] + 25)
    df["TRM"] = np.exp(ancla[:, 5] + desv[:, 5])
    df["COLCAP"] = np.exp(ancla[:, 6] + desv[:, 6])

    tpm = pd.Series({pd.Timestamp(d): v for d, v in TPM}).reindex(
        pd.DatetimeIndex(sorted(set(fechas) | {pd.Timestamp(d) for d, _ in TPM}))
    ).ffill().reindex(fechas)
    ruido_ibr = np.zeros(T)
    for t in range(1, T):
        ruido_ibr[t] = 0.9 * ruido_ibr[t - 1] + rng.normal(0, 1.5)
    df["IBR"] = tpm.to_numpy() + 0.15 + ruido_ibr / 100

    df = df.round({**{n: 4 for n in NODOS}, "SPR_AAA": 2, "SPR_AA": 2,
                   "TRM": 2, "COLCAP": 2, "IBR": 4})
    df.index.name = "fecha"
    return df
