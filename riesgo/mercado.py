"""Datos de mercado: carga, cambios diarios de los factores de riesgo,
aplicación de escenarios y covarianza EWMA.

Convención de unidades (clave para leer todo el motor):
  - Nodos de la curva TES: nivel en % EA; cambio en puntos básicos (pb).
  - Spreads de crédito:    nivel en pb;     cambio en pb.
  - TRM e índice accionario: nivel en su unidad; cambio en retorno logarítmico.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

F = len(C.FACTORES)
IDX = {f: i for i, f in enumerate(C.FACTORES)}
IDX_NODOS = np.array([IDX[n] for n in C.NODOS_CURVA])
PLAZOS_NODOS = np.array(list(C.NODOS_CURVA.values()))
ES_LOG = np.array([f in C.FACTORES_LOG for f in C.FACTORES])
# Escala para pasar de "cambio" a "nivel" en factores lineales: 1 pb = 0,01 %
ESCALA_LIN = np.array([0.01 if f in C.NODOS_CURVA else 1.0 for f in C.FACTORES])
# Tamaño del "golpe" para sensibilidades por diferencias finitas
PASO_SENS = np.array([0.01 if f in C.FACTORES_LOG else 1.0 for f in C.FACTORES])


class ErrorMercado(Exception):
    pass


class Mercado:
    def __init__(self, ruta):
        if not ruta.exists():
            raise ErrorMercado(f"No existe el archivo de mercado {ruta}. "
                               "En la demo se crea con herramientas/generar_datos_demo.py")
        df = pd.read_csv(ruta, encoding="utf-8-sig")
        faltan = [c for c in ["fecha", *C.FACTORES, C.COLUMNA_IBR] if c not in df.columns]
        if faltan:
            raise ErrorMercado(f"Al archivo de mercado le faltan columnas: {faltan}")
        df["fecha"] = pd.to_datetime(df["fecha"])
        df = (df.drop_duplicates("fecha", keep="last").set_index("fecha")
                .sort_index()[[*C.FACTORES, C.COLUMNA_IBR]].astype(float))
        # Huecos cortos (festivos, fallas de publicación): se arrastra el último dato
        self.df = df.ffill(limit=3)
        if self.df[C.FACTORES].isna().any().any():
            raise ErrorMercado("El archivo de mercado tiene vacíos que no se pueden completar.")

    # ------------------------------------------------------------ consultas
    def indice(self, corte: pd.Timestamp) -> int:
        """Posición del último dato disponible a la fecha de corte."""
        pos = self.df.index.searchsorted(corte, side="right") - 1
        if pos < 0:
            raise ErrorMercado(f"No hay datos de mercado anteriores a {corte.date()}")
        rezago = (corte - self.df.index[pos]).days
        if rezago > 5:
            raise ErrorMercado(f"El último dato de mercado ({self.df.index[pos].date()}) está "
                               f"{rezago} días antes del corte {corte.date()}: actualice el archivo.")
        return int(pos)

    def matriz(self) -> np.ndarray:
        return self.df[C.FACTORES].to_numpy()

    def niveles(self, corte: pd.Timestamp) -> np.ndarray:
        return self.matriz()[self.indice(corte)]

    def ibr(self, fecha: pd.Timestamp) -> float:
        serie = self.df[C.COLUMNA_IBR]
        pos = serie.index.searchsorted(fecha, side="right") - 1
        return float(serie.iloc[max(pos, 0)])

    # ------------------------------------------------------- transformaciones
    @staticmethod
    def cambios(niveles: np.ndarray) -> np.ndarray:
        """Niveles (T x F) -> cambios diarios ((T-1) x F) en las unidades del motor."""
        d = np.empty((niveles.shape[0] - 1, F))
        lin = ~ES_LOG
        d[:, lin] = (niveles[1:, lin] - niveles[:-1, lin]) / ESCALA_LIN[lin]
        d[:, ES_LOG] = np.log(niveles[1:, ES_LOG] / niveles[:-1, ES_LOG])
        return d

    @staticmethod
    def aplicar(base: np.ndarray, cambios: np.ndarray) -> np.ndarray:
        """Aplica cambios (S x F) sobre niveles base (F) o (S x F)."""
        cambios = np.atleast_2d(cambios)
        base = np.broadcast_to(base, cambios.shape)
        out = np.empty_like(cambios, dtype=float)
        lin = ~ES_LOG
        out[:, lin] = base[:, lin] + cambios[:, lin] * ESCALA_LIN[lin]
        out[:, ES_LOG] = base[:, ES_LOG] * np.exp(cambios[:, ES_LOG])
        return out


def covarianzas_ewma(cambios: np.ndarray, lam: float = C.LAMBDA_EWMA,
                     n_inicio: int = C.OBS_INICIO_EWMA) -> np.ndarray:
    """Covarianza EWMA (RiskMetrics) después de cada observación.

    S_t = lam * S_{t-1} + (1 - lam) * x_t x_t'
    Devuelve un arreglo (T x F x F) donde el elemento t usa la información
    hasta la observación t inclusive. Es un IGARCH sin constante: la misma
    idea de persistencia total que vimos en el GARCH de la TRM.
    """
    T = cambios.shape[0]
    salida = np.full((T, F, F), np.nan)
    s = np.cov(cambios[:n_inicio].T)
    for t in range(n_inicio, T):
        x = cambios[t][:, None]
        s = lam * s + (1 - lam) * (x @ x.T)
        salida[t] = s
    return salida
