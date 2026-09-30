"""Mensajes clave del informe, escritos por reglas (sin intervención manual).

Cada regla mira los resultados del corte y, si aplica, redacta una frase
lista para el comité. El color de cada mensaje sale del semáforo de los
límites relacionados: rojo si alguno está excedido, ámbar si alguno está en
alerta, informativo en otro caso.
"""
from __future__ import annotations

import numpy as np

from . import config as C
from .utilidades import fecha_corta, num, pct

# Límites que ya tienen un mensaje propio (no se repiten en el bloque genérico)
_PROPIOS = {
    "var": ["VAR_HS_10D_PCT_PT"],
    "backtesting": ["BT_EXCEPCIONES_HS"],
    "estres": ["ESTRES_PEOR_PCT_PT"],
    "liquidez": ["IRL_7D", "IRL_30D"],
    "datos": ["ERRORES_DATOS"],
}
_ORDEN = {"rojo": 0, "ambar": 1, "info": 2}


def _tono(estados: dict, codigos: list) -> str:
    valores = [estados.get(c) for c in codigos]
    if "ROJO" in valores:
        return "rojo"
    return "ambar" if "ÁMBAR" in valores else "info"


def mensajes_clave(r: dict, previo: dict | None) -> list[tuple[str, str]]:
    """Lista de (tono, texto), tono en {rojo, ambar, info}, ordenada por severidad."""
    lim, ind, conc = r["limites"], r["indicadores"], r["concentracion"]
    estados = dict(zip(lim["codigo"], lim["estado"]))
    propios = {c for lista in _PROPIOS.values() for c in lista}
    salida = []

    # 1) Límites sin mensaje propio, en rojo o ámbar
    for _, l in lim[lim["estado"].isin(["ROJO", "ÁMBAR"]) & ~lim["codigo"].isin(propios)].iterrows():
        indicador = l["indicador"][0].lower() + l["indicador"][1:]
        if l["codigo"] == "EMISOR_MAX_PCT":
            texto = (f"{'Límite excedido' if l['estado'] == 'ROJO' else 'En alerta'}: la exposición a "
                     f"{conc['emisor_max']} es {l['valor_txt']} del portafolio, frente a un límite de "
                     f"{l['limite_txt']} (alerta {l['alerta_txt']}).")
        elif l["estado"] == "ROJO":
            texto = f"Límite excedido: {indicador} en {l['valor_txt']} frente a un límite de {l['limite_txt']}"
        else:
            texto = (f"En alerta: {indicador} en {l['valor_txt']} "
                     f"(alerta {l['alerta_txt']}, límite {l['limite_txt']})")
        if l["codigo"] == "EMISOR_MAX_PCT":
            n = len(conc["emisor_max_nombres"])
            if n > 1:
                texto += (f" Esa exposición está escrita de {n} formas distintas en el archivo de posiciones; "
                          f"un control que agrupe por el nombre tal como está escrito la habría mostrado en "
                          f"{pct(conc['emisor_max_pct_manual'])}")
                texto += (" y no habría detectado el exceso."
                          if conc["emisor_max_pct_manual"] <= l["limite"] else ".")
        else:
            texto += f", {l['detalle']}." if l["detalle"] else "."
        salida.append(("rojo" if l["estado"] == "ROJO" else "ambar", texto))

    # 2) VaR y su evolución frente al corte anterior
    texto = (f"VaR histórico 99% a 1 día de COP {num(ind['VAR_HS_1D'], 0)} M "
             f"({pct(ind['VAR_HS_1D_PCT_PORT'], 2)} del portafolio); llevado a 10 días equivale al "
             f"{pct(ind['VAR_HS_10D_PCT_PT'], 2)} del patrimonio técnico")
    if previo is not None and previo.get("VAR_HS_1D"):
        cambio = ind["VAR_HS_1D"] / previo["VAR_HS_1D"] - 1
        if abs(cambio) >= 0.05:
            texto += (f", {'un aumento' if cambio > 0 else 'una disminución'} de {pct(abs(cambio), 0)} "
                      f"frente al corte anterior")
            d_dur = ind["DURACION_RF"] - previo.get("DURACION_RF", ind["DURACION_RF"])
            if abs(d_dur) >= 0.1:
                texto += (f"; la duración de la renta fija pasó de {num(previo['DURACION_RF'], 2)} a "
                          f"{num(ind['DURACION_RF'], 2)} años")
    salida.append((_tono(estados, _PROPIOS["var"]), texto + "."))

    # 3) Backtesting
    bt = r["backtesting"]
    hs, pa = bt["hs"], bt["param"]
    texto = (f"Backtesting de {bt['n']} días: {hs['excepciones']} excepciones del VaR histórico "
             f"(zona {hs['zona'].lower()} de Basilea) y {pa['excepciones']} del paramétrico "
             f"(zona {pa['zona'].lower()}), frente a {num(hs['esperadas'], 1)} esperadas.")
    if pa["kupiec_p"] < 0.05 <= hs["kupiec_p"]:
        texto += (" La prueba de Kupiec rechaza el modelo paramétrico normal, que subestima las colas, y "
                  "no rechaza el histórico, que se mantiene como medida principal.")
    elif pa["kupiec_p"] < 0.05 and hs["kupiec_p"] < 0.05:
        texto += " La prueba de Kupiec rechaza ambos modelos: se recomienda revisar la metodología."
    peores = sorted(zip(bt["fechas"], bt["pnl"]), key=lambda x: x[1])[:3]
    texto += " Mayores pérdidas: " + ", ".join(
        f"{f.day}-{fecha_corta(f)} (COP {num(-p / 1e6, 0)} M)" for f, p in peores) + "."
    salida.append((_tono(estados, _PROPIOS["backtesting"]), texto))

    # 4) Estrés
    e = r["estres"]
    peor = e.loc[e["pnl"].idxmin()]
    texto = (f"Escenario de estrés más severo: «{peor['escenario']}»"
             + (f" (ventana {peor['ventana']})" if peor["ventana"] else "")
             + f", con pérdida de COP {num(-peor['pnl'] / 1e6, 0)} M, "
               f"{pct(-peor['pnl'] / r['patrimonio_tecnico'])} del patrimonio técnico.")
    salida.append((_tono(estados, _PROPIOS["estres"]), texto))

    # 5) Liquidez
    liq = r["liquidez"]
    b = liq["bandas"]
    dias_banda = [hasta - desde + 1 for _, desde, hasta in C.BANDAS_LIQUIDEZ]
    banda_critica = b.loc[(b["rln"] / dias_banda).idxmax(), "banda"]
    texto = (f"IRL razón de {pct(liq['irl_7'], 0)} a 7 días y {pct(liq['irl_30'], 0)} a 30 días; la mayor "
             f"presión diaria de liquidez está en la banda de {banda_critica}")
    if previo is not None and previo.get("IRL_30D"):
        texto += f" (IRL a 30 días del corte anterior: {pct(previo['IRL_30D'], 0)})"
    salida.append((_tono(estados, _PROPIOS["liquidez"]), texto + "."))

    # 6) Calidad de datos
    h = r["hallazgos"]
    difs = sum(1 for x in h.registros if x["campo"] == "valor de mercado")
    texto = (f"Calidad de datos: {h.conteo('ERROR')} filas excluidas por error y "
             f"{h.conteo('ADVERTENCIA')} advertencias corregidas automáticamente")
    if difs:
        texto += (f", con {difs} {'diferencia' if difs == 1 else 'diferencias'} de valoración frente "
                  f"al valor reportado")
    salida.append((_tono(estados, _PROPIOS["datos"]), texto + " (detalle en la sección 9)."))

    return sorted(salida, key=lambda x: _ORDEN[x[0]])
