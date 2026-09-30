"""Orquestación de un corte: lectura -> validación -> valoración -> riesgo ->
límites -> mensajes. Devuelve un diccionario con todos los resultados, que
luego consumen el informe PDF, el anexo Excel y el historial."""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from .acciones import acciones_sugeridas
from .concentracion import calcular_concentracion
from .lectura import leer_posiciones
from .limites import calcular_indicadores, evaluar_limites
from .liquidez import calcular_liquidez
from .mercado import Mercado
from .narrativa import mensajes_clave
from .riesgo_mercado import backtesting, calcular_var, pruebas_estres
from .utilidades import Hallazgos, millones, pct, sha256
from .valoracion import Portafolio


def _revisar_valoracion(tabla: pd.DataFrame, h: Hallazgos) -> None:
    """Compara el valor reportado por la entidad con el valor teórico del motor."""
    revisables = tabla["tipo"].isin(C.RENTA_FIJA | {"DIVISA"}) & tabla["valor_mercado"].notna()
    for _, f in tabla[revisables].iterrows():
        dif = f["valor"] / f["valor_mercado"] - 1
        if abs(dif) > C.TOLERANCIA_VALORACION:
            h.agregar("ADVERTENCIA", "Inversiones", f["fila_excel"], "valor de mercado",
                      millones(f["valor_mercado"], 1),
                      f"El valor reportado difiere {pct(-dif / (1 + dif), 1)} del valor teórico "
                      f"({millones(f['valor'], 1)}).",
                      "Verificar con el proveedor de precios; el motor usa el valor teórico.")


def procesar_corte(ruta: Path, corte: pd.Timestamp, politica: dict, mercado: Mercado,
                   previo: dict | None, avance=None) -> dict:
    avance = avance or (lambda paso, texto: None)
    t0 = time.perf_counter()
    h = Hallazgos()

    avance(1, "Leyendo y validando posiciones")
    datos = leer_posiciones(ruta, corte, politica, h)
    pt = datos["patrimonio_tecnico"]

    avance(2, "Valorando el portafolio")
    port = Portafolio(datos["inversiones"], mercado, corte)
    tabla = port.tabla()
    tabla["es_renta_fija"] = tabla["tipo"].isin(C.RENTA_FIJA)
    _revisar_valoracion(tabla, h)

    avance(3, "Riesgo de mercado (VaR, ES, backtesting, estrés)")
    res_var = calcular_var(port, mercado, corte)
    tabla["contrib_es"] = res_var["contrib_es"]
    tabla["comp_var_param"] = res_var["comp_param"]
    tabla["pct_pt"] = tabla["valor"] / pt
    bt = backtesting(port, mercado, corte, res_var)
    est = pruebas_estres(port, mercado, corte, politica["escenarios"], res_var["V0"])
    est["posicion_mas_afectada"] = [tabla.loc[i, "especie"] for i in est["posicion_mas_afectada"]]
    est["pct_pt"] = est["pnl"] / pt
    est["pct_portafolio"] = est["pnl"] / res_var["valor_total"]

    avance(4, "Concentración y liquidez")
    conc = calcular_concentracion(tabla, pt)
    liq = calcular_liquidez(tabla, datos["flujos"], datos["depositos"], politica)
    for col in ("categoria", "haircut", "alac"):
        tabla[col] = liq["activos"][col].to_numpy()

    avance(5, "Límites y mensajes clave")
    r = {"corte": corte, "politica": politica, "patrimonio_tecnico": pt, "tabla": tabla,
         "var": res_var, "backtesting": bt, "estres": est, "concentracion": conc,
         "liquidez": liq, "flujos": datos["flujos"], "depositos": datos["depositos"],
         "hallazgos": h, "mercado_niveles": dict(zip(C.FACTORES, port.niveles0)),
         "fecha_mercado": mercado.df.index[mercado.indice(corte)]}
    r["indicadores"] = calcular_indicadores(r)
    r["limites"] = evaluar_limites(politica["limites"], r["indicadores"])
    r["mensajes"] = mensajes_clave(r, previo)
    r["acciones"] = acciones_sugeridas(r)
    r["previo"] = previo
    r["traza"] = {
        "version": C.VERSION, "ejecutado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "segundos_calculo": time.perf_counter() - t0,
        "archivos": [(p.name, sha256(p)) for p in (ruta, C.ARCHIVO_POLITICA, C.ARCHIVO_MERCADO)],
        "parametros": {
            "Confianza VaR": pct(C.CONFIANZA_VAR, 0), "Confianza ES": pct(C.CONFIANZA_ES, 1),
            "Ventana simulación histórica": f"{C.VENTANA_HS} días hábiles",
            "Ventana backtesting": f"{C.VENTANA_BACKTEST} días hábiles",
            "Lambda EWMA": str(C.LAMBDA_EWMA).replace(".", ","),
            "Horizonte regulatorio": f"{C.DIAS_HORIZONTE_REGULATORIO} días (raíz del tiempo)",
            "Ventana estrés histórico": f"{C.DIAS_VENTANA_ESTRES_HIST} días hábiles",
            "Tolerancia de valoración": pct(C.TOLERANCIA_VALORACION, 0),
        },
    }
    return r


# ------------------------------------------------------------- historial ----
COLUMNAS_HIST = ["VALOR_PORTAFOLIO", "PATRIMONIO_TECNICO", "VAR_HS_1D", "ES_HS_1D", "VAR_PARAM_1D",
                 "VAR_HS_10D_PCT_PT", "DURACION_RF", "DV01_TOTAL", "ESTRES_PEOR_PCT_PT",
                 "BT_EXCEPCIONES_HS", "BT_EXCEPCIONES_PARAM", "USD_PCT_PT", "RV_PCT", "EMISOR_MAX_PCT",
                 "HHI_PRIVADOS", "TOP5_PCT", "CALIF_A_O_INF_PCT", "IRL_7D", "IRL_30D", "ALAC",
                 "ERRORES_DATOS", "ADVERTENCIAS_DATOS"]


def cargar_historial() -> pd.DataFrame:
    if not C.ARCHIVO_HISTORIAL.exists():
        return pd.DataFrame(columns=COLUMNAS_HIST, index=pd.DatetimeIndex([], name="fecha_corte"))
    h = pd.read_csv(C.ARCHIVO_HISTORIAL, encoding="utf-8-sig", parse_dates=["fecha_corte"])
    return h.set_index("fecha_corte").sort_index()


def indicadores_previos(hist: pd.DataFrame, corte: pd.Timestamp) -> dict | None:
    anteriores = hist[hist.index < corte]
    return None if anteriores.empty else anteriores.iloc[-1].to_dict()


def actualizar_historial(hist: pd.DataFrame, corte: pd.Timestamp, ind: dict) -> pd.DataFrame:
    fila = pd.DataFrame([{c: ind.get(c, np.nan) for c in COLUMNAS_HIST}],
                        index=pd.DatetimeIndex([corte], name="fecha_corte"))
    resto = hist[hist.index != corte]
    hist = fila if resto.empty else pd.concat([resto, fila]).sort_index()
    C.ARCHIVO_HISTORIAL.parent.mkdir(parents=True, exist_ok=True)
    hist.to_csv(C.ARCHIVO_HISTORIAL, encoding="utf-8-sig")
    return hist
