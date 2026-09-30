"""Valoración con revaluación completa.

Cada título de renta fija se descompone en flujos de caja. Cada flujo se
descuenta con la curva TES interpolada a su plazo más el spread de crédito de
la calificación del emisor:

    VP = suma( flujo_i / (1 + y(t_i) + s)^t_i )

El mismo código valora el portafolio de hoy y miles de escenarios a la vez:
la función `valorar` recibe una matriz de niveles de mercado (escenarios x
factores) y devuelve (escenarios x posiciones). Así el VaR histórico, el
backtesting y las pruebas de estrés usan exactamente la misma valoración.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .mercado import F, IDX, IDX_NODOS, PASO_SENS, PLAZOS_NODOS, Mercado


def pesos_interpolacion(t: np.ndarray) -> np.ndarray:
    """Pesos de interpolación lineal de cada plazo sobre los nodos de la curva
    (extrapolación plana en los extremos). Resultado: (n_flujos x n_nodos)."""
    n = len(PLAZOS_NODOS)
    W = np.empty((len(t), n))
    for j in range(n):
        unitario = np.zeros(n)
        unitario[j] = 1.0
        W[:, j] = np.interp(t, PLAZOS_NODOS, unitario)
    return W


def fechas_cupon(vencimiento: pd.Timestamp, frecuencia: int, corte: pd.Timestamp):
    """Calendario hacia atrás desde el vencimiento. Devuelve las fechas de pago
    posteriores al corte y la última fecha de pago (o reprecio) anterior."""
    meses = 12 // frecuencia
    futuras, k = [], 0
    while True:
        f = vencimiento - pd.DateOffset(months=meses * k)
        if f <= corte:
            return sorted(futuras), f
        futuras.append(f)
        k += 1


def tir(t: np.ndarray, flujos: np.ndarray, precio: float) -> float:
    """Tasa interna de retorno (EA) por Newton-Raphson."""
    y = 0.10
    for _ in range(60):
        d = (1 + y) ** (-t)
        f = (flujos * d).sum() - precio
        fp = (-t * flujos * d / (1 + y)).sum()
        if fp == 0:
            break
        paso = f / fp
        y -= paso
        if abs(paso) < 1e-12:
            break
    return float(y)


class Portafolio:
    """Portafolio listo para valorar bajo cualquier conjunto de escenarios."""

    def __init__(self, pos: pd.DataFrame, mercado: Mercado, corte: pd.Timestamp):
        self.pos = pos.reset_index(drop=True).copy()
        self.corte = pd.Timestamp(corte)
        self.P = len(self.pos)
        self.niveles0 = mercado.niveles(self.corte)
        self.colcap0 = self.niveles0[IDX["COLCAP"]]

        self.lineal = np.zeros(self.P, dtype=int)   # 0 flujos | 1 RV | 2 divisa | 3 liquidez
        self.base = np.zeros(self.P)
        self.usd = np.zeros(self.P)
        self.beta = np.ones(self.P)
        self.plazo = np.full(self.P, np.nan)
        self.cupon_vigente = np.full(self.P, np.nan)

        cf_pos, cf_t, cf_fijo, cf_coef, cf_col, cf_off = [], [], [], [], [], []
        for p, r in self.pos.iterrows():
            tipo = r["tipo"]
            if tipo in C.RENTA_FIJA:
                col, off = self._spread(r)
                for t, fijo, coef in self._flujos(p, r, mercado):
                    cf_pos.append(p); cf_t.append(t); cf_fijo.append(fijo)
                    cf_coef.append(coef); cf_col.append(col); cf_off.append(off)
                self.plazo[p] = (r["fecha_vencimiento"] - self.corte).days / 365.0
            elif tipo == "RENTA_VARIABLE":
                self.lineal[p] = 1
                self.base[p] = r["valor_mercado"]
                self.beta[p] = r["beta"]
            elif tipo == "DIVISA":
                self.lineal[p] = 2
                self.usd[p] = r["valor_nominal"]
            elif tipo == "LIQUIDEZ":
                self.lineal[p] = 3
                self.base[p] = (r["valor_mercado"] if pd.notna(r["valor_mercado"])
                                else r["valor_nominal"])

        self.cf_pos = np.array(cf_pos, dtype=int)
        self.cf_t = np.array(cf_t, dtype=float)
        self.cf_fijo = np.array(cf_fijo, dtype=float)
        self.cf_coef = np.array(cf_coef, dtype=float)
        self.cf_off = np.array(cf_off, dtype=float)
        n = len(self.cf_t)
        self.W = pesos_interpolacion(self.cf_t) if n else np.zeros((0, len(PLAZOS_NODOS)))
        self.Sel = np.zeros((F, n))            # qué factor de spread usa cada flujo
        for i, col in enumerate(cf_col):
            if col >= 0:
                self.Sel[col, i] = 1.0
        self.Inc = np.zeros((n, self.P))       # a qué posición pertenece cada flujo
        if n:
            self.Inc[np.arange(n), self.cf_pos] = 1.0

    # ----------------------------------------------------------- flujos ----
    def _anios(self, fecha) -> float:
        return (pd.Timestamp(fecha) - self.corte).days / 365.0

    @staticmethod
    def _spread(r):
        if r["tipo"] == "TES_TF" or r["calificacion_lp"] == "NACION":
            return -1, 0.0
        factor, ajuste = C.SPREAD_POR_CALIFICACION.get(r["calificacion_lp"], C.SPREAD_INFERIOR)
        return IDX[factor], ajuste

    def _flujos(self, p: int, r, mercado: Mercado):
        """Lista de (plazo en años, monto fijo, coeficiente del spread)."""
        N, f = float(r["valor_nominal"]), int(r["frecuencia"])
        venc = r["fecha_vencimiento"]

        if r["tipo"] == "CDT_IBR":
            # Flotante: el próximo cupón ya está fijado con el IBR del último reprecio.
            # Después de esa fecha el título vale su nominal más el valor presente de
            # la diferencia entre el margen pactado (m) y el spread de mercado (s):
            #   VP = (N + c1) * FD(t1) + suma_k N * (m - s)/f * FD(tk)
            futuras, ultima = fechas_cupon(venc, f, self.corte)
            reprecio = ultima
            if pd.notna(r["fecha_emision"]) and r["fecha_emision"] > ultima:
                reprecio = r["fecha_emision"]
            ibr = mercado.ibr(reprecio) / 100.0
            j = f * ((1 + ibr) ** (1 / f) - 1)            # IBR nominal del periodo
            m = float(r["margen"])
            self.cupon_vigente[p] = j + m
            salida = [(self._anios(futuras[0]), N + N * (j + m) / f, 0.0)]
            salida += [(self._anios(fk), N * m / f, -N / f) for fk in futuras[1:]]
            return salida

        tasa = float(r["tasa_facial"])
        self.cupon_vigente[p] = tasa
        if f == 0:   # intereses y capital al vencimiento
            plazo_total = (venc - r["fecha_emision"]).days / 365.0
            interes = ((1 + tasa) ** plazo_total - 1 if r["base_tasa"] == "EA"
                       else tasa * plazo_total)
            return [(self._anios(venc), N * (1 + interes), 0.0)]
        tasa_periodo = (1 + tasa) ** (1 / f) - 1 if r["base_tasa"] == "EA" else tasa / f
        futuras, _ = fechas_cupon(venc, f, self.corte)
        salida = [(self._anios(fk), N * tasa_periodo, 0.0) for fk in futuras]
        t_final, cupon_final, _ = salida[-1]
        salida[-1] = (t_final, cupon_final + N, 0.0)
        return salida

    # --------------------------------------------------------- valoración ----
    def valorar(self, niveles: np.ndarray) -> np.ndarray:
        """Niveles de mercado (S x F) -> valor de cada posición (S x P), en COP."""
        niveles = np.atleast_2d(niveles)
        S = niveles.shape[0]
        V = np.zeros((S, self.P))
        if len(self.cf_t):
            for a in range(0, S, C.BLOQUE_ESCENARIOS):
                L = niveles[a:a + C.BLOQUE_ESCENARIOS]
                tasa_curva = L[:, IDX_NODOS] @ self.W.T          # % EA en cada flujo
                spread = L @ self.Sel + self.cf_off              # pb en cada flujo
                r = (tasa_curva + spread / 100.0) / 100.0
                factor_desc = np.exp(-self.cf_t * np.log1p(r))
                monto = self.cf_fijo + self.cf_coef * (spread / 1e4)
                V[a:a + C.BLOQUE_ESCENARIOS] = (monto * factor_desc) @ self.Inc
        m = self.lineal
        if (m == 1).any():
            ret = niveles[:, [IDX["COLCAP"]]] / self.colcap0 - 1
            V[:, m == 1] = self.base[m == 1] * (1 + self.beta[m == 1] * ret)
        if (m == 2).any():
            V[:, m == 2] = self.usd[m == 2] * niveles[:, [IDX["TRM"]]]
        if (m == 3).any():
            V[:, m == 3] = self.base[m == 3]
        return V

    def sensibilidades(self, niveles=None) -> np.ndarray:
        """Sensibilidad de cada posición a cada factor (P x F), por diferencias
        finitas centrales: COP por +1 pb (tasas y spreads) o por +1,00 de
        retorno logarítmico (TRM e índice accionario)."""
        base = self.niveles0 if niveles is None else niveles
        golpes = np.zeros((2 * F, F))
        for k in range(F):
            golpes[2 * k, k] = PASO_SENS[k]
            golpes[2 * k + 1, k] = -PASO_SENS[k]
        V = self.valorar(Mercado.aplicar(base, golpes))
        return ((V[0::2] - V[1::2]) / (2 * PASO_SENS[:, None])).T

    # ------------------------------------------------------------ resumen ----
    def tabla(self) -> pd.DataFrame:
        """Posiciones con valor, duración, DV01, TIR y sensibilidades."""
        V0 = self.valorar(self.niveles0)[0]
        sens = self.sensibilidades()
        nodos = IDX_NODOS
        dv01 = -sens[:, nodos].sum(axis=1)                   # pérdida por +1 pb en toda la curva
        dv01_spread = -sens[:, [IDX[s] for s in C.FACTORES_SPREAD]].sum(axis=1)
        t = self.pos.copy()
        t["valor"] = V0
        t["peso"] = V0 / V0.sum()
        t["dv01"] = dv01
        t["dv01_spread"] = dv01_spread
        with np.errstate(divide="ignore", invalid="ignore"):
            t["duracion_mod"] = np.where(V0 > 0, dv01 * 1e4 / V0, np.nan)
            t["duracion_spread"] = np.where(V0 > 0, dv01_spread * 1e4 / V0, np.nan)
        t.loc[~t["tipo"].isin(C.RENTA_FIJA), ["duracion_mod", "duracion_spread"]] = np.nan
        t["plazo_anios"] = self.plazo
        t["cupon_vigente"] = self.cupon_vigente
        t["delta_trm_1pct"] = sens[:, IDX["TRM"]] * 0.01
        t["delta_rv_1pct"] = sens[:, IDX["COLCAP"]] * 0.01
        tires = np.full(self.P, np.nan)
        for p in range(self.P):
            if self.pos.loc[p, "tipo"] in {"TES_TF", "CDT_TF", "BONO_TF"}:
                sel = self.cf_pos == p
                tires[p] = tir(self.cf_t[sel], self.cf_fijo[sel], V0[p])
        t["tir"] = tires
        for k, nodo in enumerate(C.NODOS_CURVA):
            t[f"krd_{nodo}"] = -sens[:, IDX_NODOS[k]]
        return t
