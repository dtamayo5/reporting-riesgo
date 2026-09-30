"""Acciones sugeridas: convierte cada límite en rojo o ámbar en una acción
concreta con un monto de referencia.

Un semáforo dice QUÉ está mal; el comité necesita saber CUÁNTO hay que mover
para corregirlo. Ejemplo: si un emisor pesa 17,6% del portafolio y el límite
es 15%, hay que reducir su exposición en E - 15% x Total (manteniendo el
tamaño del portafolio, es decir, reinvirtiendo en otros emisores).

Las acciones son sugerencias para el comité: la decisión final es de la entidad.
"""
from __future__ import annotations

from . import config as C
from .utilidades import millones, num, pct

_PRIORIDAD = {"ROJO": 0, "ÁMBAR": 1, "INFO": 2}


def _objetivo(l) -> float:
    """Nivel al que hay que llevar el indicador: el límite si está en rojo,
    la alerta si está en ámbar (volver a la zona verde)."""
    return l["limite"] if l["estado"] == "ROJO" else l["alerta"]


def acciones_sugeridas(r: dict) -> list[dict]:
    t, lim, ind = r["tabla"], r["limites"], r["indicadores"]
    conc, liq, bt = r["concentracion"], r["liquidez"], r["backtesting"]
    total, pt = float(t["valor"].sum()), r["patrimonio_tecnico"]
    salida = []

    def agregar(estado, tema, accion, monto=None):
        salida.append({"prioridad": estado, "tema": tema, "accion": accion, "monto": monto})

    for _, l in lim[lim["estado"].isin(["ROJO", "ÁMBAR"])].iterrows():
        codigo, estado = l["codigo"], l["estado"]

        if codigo == "EMISOR_MAX_PCT":
            emisor = conc["emisor_max"]
            pos = t[t["emisor"] == emisor]
            expo = float(pos["valor"].sum())
            x_lim, x_ale = expo - l["limite"] * total, expo - l["alerta"] * total
            vista = float(pos.loc[pos["tipo"] == "LIQUIDEZ", "valor"].sum())
            rf = pos[pos["tipo"].isin(C.RENTA_FIJA)].sort_values("fecha_vencimiento")
            vias = []
            if vista > 0:
                vias.append(f"bajar el saldo de sus depósitos a la vista (hoy {millones(vista)})")
            if len(rf):
                p = rf.iloc[0]
                vias.append(f"no renovar el título que vence primero ({p['especie']}, "
                            f"{p['fecha_vencimiento']:%d/%m/%Y}, {millones(p['valor'])})")
            texto = (f"Reducir la exposición a {emisor} en al menos {millones(max(x_lim, 0))} para cumplir el "
                     f"límite de {pct(l['limite'], 0)}" if estado == "ROJO" else
                     f"Reducir la exposición a {emisor} en {millones(max(x_ale, 0))} para salir de la alerta")
            if estado == "ROJO" and x_ale > x_lim:
                texto += f" ({millones(x_ale)} para volver a la zona verde)"
            texto += ", reinvirtiendo en otros emisores. Vías: " + " o ".join(vias) + "." if vias else "."
            agregar(estado, "Concentración", texto, max(x_lim if estado == "ROJO" else x_ale, 0))

        elif codigo in ("IRL_7D", "IRL_30D"):
            fila = 0 if codigo == "IRL_7D" else 2
            b = liq["bandas"]
            rln, alac = float(b["rln_acumulado"].iloc[fila]), liq["alac"]
            d_lim, d_ale = l["limite"] * rln - alac, l["alerta"] * rln - alac
            dias = [hasta - desde + 1 for _, desde, hasta in C.BANDAS_LIQUIDEZ][:fila + 1]
            presion = b.iloc[:fila + 1].assign(por_dia=lambda x: x["rln"] / dias)
            critica = presion.loc[presion["por_dia"].idxmax()]
            objetivo = d_lim if estado == "ROJO" else d_ale
            nombre_irl = "IRL a 7 días" if codigo == "IRL_7D" else "IRL a 30 días"
            texto = (f"Aumentar los activos líquidos ajustados en {millones(max(objetivo, 0))} para llevar el "
                     f"{nombre_irl} a {pct(_objetivo(l), 0)}"
                     + (f" ({millones(d_ale)} para volver a la zona verde)" if estado == "ROJO" else "")
                     + ". Vías: trasladar recursos a disponible o TES de corto plazo (haircut de 0% a 2%) o "
                       f"escalonar los vencimientos de CDAT de la banda de {critica['banda']} "
                       f"({millones(critica['salidas_contractuales'])} de salidas contractuales).")
            agregar(estado, "Liquidez", texto, max(objetivo, 0))

        elif codigo == "BT_EXCEPCIONES_HS":
            fechas = bt["fechas"][bt["hs"]["mascara"]]
            texto = (f"Revisar el modelo de VaR con el área de riesgos: {bt['hs']['excepciones']} excepciones en "
                     f"{bt['n']} días (zona {bt['hs']['zona'].lower()} de Basilea), la más reciente el "
                     f"{fechas[-1]:%d/%m/%Y}. Mantener el ES como medida complementaria y evaluar un VaR "
                     "estresado con una ventana que incluya un periodo de crisis (p. ej., 2022).")
            agregar(estado, "Modelo de riesgo", texto)

        elif codigo == "ERRORES_DATOS":
            errores = [x for x in r["hallazgos"].registros if x["severidad"] == "ERROR"]
            partes = []
            for x in errores[:6]:
                corto = ("retirar el título vencido" if "vencido" in x["detalle"] else
                         "valorarlo aparte o activar el módulo" if "no soportado" in x["detalle"] else
                         x["detalle"].rstrip("."))
                partes.append(f"fila {x['fila_excel']} de {x['hoja']} ({corto})")
            texto = ("Corregir en el archivo de origen antes del próximo corte: " + "; ".join(partes) + "."
                     + (f" Y {len(errores) - 6} más en la sección 9." if len(errores) > 6 else ""))
            agregar(estado, "Calidad de datos", texto)

        elif codigo in ("DURACION_RF", "DV01_TOTAL"):
            dv01_total = float(t["dv01"].sum())
            if codigo == "DURACION_RF":
                reduccion = dv01_total * (1 - _objetivo(l) / ind["DURACION_RF"])
            else:
                reduccion = dv01_total - _objetivo(l) * 1e6
            tes = t[t["tipo"] == "TES_TF"].sort_values("duracion_mod", ascending=False)
            texto = f"Reducir la sensibilidad a tasas en COP {num(reduccion / 1e6, 2)} M por pb"
            if len(tes):
                p = tes.iloc[0]
                venta = reduccion / (p["dv01"] / p["valor"])
                texto += (f"; equivale a vender cerca de {millones(venta)} del {p['especie']} (el TES de mayor "
                          "duración) o a cubrir con un derivado de tasa")
            agregar(estado, "Riesgo de tasa", texto + ".")

        elif codigo == "VAR_HS_10D_PCT_PT":
            reduccion = 1 - _objetivo(l) / l["valor"]
            top = t.sort_values("contrib_es", ascending=False).iloc[0]
            texto = (f"Reducir el VaR en {pct(reduccion, 0)}. La posición que más aporta a la pérdida en la cola "
                     f"es {top['especie']} ({pct(top['contrib_es'] / r['var']['es_hs'], 0)} del ES).")
            agregar(estado, "Riesgo de mercado", texto)

        elif codigo == "ESTRES_PEOR_PCT_PT":
            e = r["estres"].loc[r["estres"]["pnl"].idxmin()]
            exceso = -e["pnl"] - _objetivo(l) * pt
            texto = (f"El escenario «{e['escenario']}» supera el apetito aprobado en {millones(max(exceso, 0))}. "
                     f"La posición más afectada es {e['posicion_mas_afectada']} "
                     f"({millones(-e['pnl_posicion_mas_afectada'])} de pérdida): evaluar reducirla o cubrirla.")
            agregar(estado, "Estrés", texto, max(exceso, 0))

        elif codigo in ("USD_PCT_PT", "RV_PCT", "TOP5_PCT", "CALIF_A_O_INF_PCT"):
            base = pt if codigo == "USD_PCT_PT" else total
            x = (l["valor"] - _objetivo(l)) * base
            que = {"USD_PCT_PT": "la posición en moneda extranjera",
                   "RV_PCT": "la renta variable",
                   "TOP5_PCT": "la exposición a los cinco mayores emisores privados",
                   "CALIF_A_O_INF_PCT": "la renta fija con calificación A+ o inferior"}[codigo]
            agregar(estado, "Límite de inversión", f"Reducir {que} en {millones(max(x, 0))}.", max(x, 0))

        elif codigo == "HHI_PRIVADOS":
            texto = (f"Diversificar los emisores privados: el HHI equivale a {num(conc['n_equivalente'], 1)} "
                     f"emisores del mismo tamaño y la mayor concentración está en {conc['emisor_max']}.")
            agregar(estado, "Concentración", texto)

    if not salida:
        agregar("INFO", "Seguimiento", "Todos los límites cumplen: mantener la estrategia y el monitoreo "
                                      "mensual de los indicadores que más se acercan a su alerta.")
    return sorted(salida, key=lambda a: _PRIORIDAD[a["prioridad"]])
