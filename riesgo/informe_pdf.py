"""Informe mensual para el Comité de Riesgos (PDF).

Estructura:
  1 Resumen ejecutivo (indicadores clave y mensajes automáticos)
  2 Límites y evolución          6 Pruebas de estrés
  3 Portafolio                   7 Concentración
  4 Riesgo de mercado            8 Liquidez
  5 Backtesting                  9 Calidad de datos
                                10 Metodología y trazabilidad
"""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, Image, KeepTogether,
                                PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)

from . import config as C
from .limites import formatear
from .utilidades import fecha_larga, millones, num, pct, texto_pdf

TINTA = colors.HexColor("#0b0b0b")
TINTA_2 = colors.HexColor("#52514e")
TENUE = colors.HexColor("#898781")
NAVY = colors.HexColor("#1F3B5C")
FONDO = colors.HexColor("#f4f5f7")
LINEA = colors.HexColor("#d9dce1")
ESTADO_COLOR = {"ROJO": colors.HexColor("#d03b3b"), "ÁMBAR": colors.HexColor("#fab219"),
                "VERDE": colors.HexColor("#0ca30c"), "SIN DATO": colors.HexColor("#c3c2b7")}
ESTADO_TEXTO = {"ROJO": "#ffffff", "ÁMBAR": "#0b0b0b", "VERDE": "#0b0b0b", "SIN DATO": "#0b0b0b"}
ESTADO_ETIQUETA = {"ROJO": "Excedido", "ÁMBAR": "Alerta", "VERDE": "Cumple", "SIN DATO": "Sin dato"}
TONO_ESTADO = {"rojo": "ROJO", "ambar": "ÁMBAR", "info": None}

ANCHO_UTIL = letter[0] - 3.6 * cm


def _estilo(nombre, **kw):
    base = dict(fontName="Helvetica", fontSize=9, leading=12.5, textColor=TINTA, alignment=TA_LEFT)
    base.update(kw)
    return ParagraphStyle(nombre, **base)


S = {
    "entidad": _estilo("entidad", fontSize=9, textColor=TINTA_2, fontName="Helvetica-Bold"),
    "titulo": _estilo("titulo", fontSize=20, leading=24, fontName="Helvetica-Bold", textColor=NAVY),
    "sub": _estilo("sub", fontSize=10, textColor=TINTA_2, spaceAfter=10),
    "h1": _estilo("h1", fontSize=13, leading=16, fontName="Helvetica-Bold", textColor=NAVY,
                  spaceBefore=4, spaceAfter=6),
    "h2": _estilo("h2", fontSize=10, leading=13, fontName="Helvetica-Bold", textColor=TINTA,
                  spaceBefore=6, spaceAfter=3),
    "p": _estilo("p", spaceAfter=5),
    "peq": _estilo("peq", fontSize=7.5, leading=10, textColor=TINTA_2),
    "celda": _estilo("celda", fontSize=7.8, leading=9.8),
    "celda_b": _estilo("celda_b", fontSize=7.8, leading=9.8, fontName="Helvetica-Bold"),
    "celda_enc": _estilo("celda_enc", fontSize=7.8, leading=9.8, fontName="Helvetica-Bold",
                         textColor=colors.white),
    "kpi_rot": _estilo("kpi_rot", fontSize=7.8, leading=10, textColor=TINTA_2),
    "kpi_val": _estilo("kpi_val", fontSize=15, leading=19, fontName="Helvetica-Bold"),
    "kpi_sub": _estilo("kpi_sub", fontSize=7.5, leading=9.5, textColor=TINTA_2),
    "chip": _estilo("chip", fontSize=7, leading=9, fontName="Helvetica-Bold", alignment=1),
    "p1": _estilo("p1", fontSize=8.4, leading=10.9),
}


def P(texto, estilo="p"):
    return Paragraph(texto_pdf(str(texto)), S[estilo] if isinstance(estilo, str) else estilo)


def E(texto) -> str:
    """Escapa texto dinámico para el marcado de reportlab."""
    return escape(texto_pdf(str(texto)))


def imagen(ruta, ancho=ANCHO_UTIL):
    if ruta is None or not Path(ruta).exists():
        return Spacer(1, 1)
    w, h = ImageReader(str(ruta)).getSize()
    return Image(str(ruta), width=ancho, height=ancho * h / w)


def tabla(datos, anchos, numericas=(), negrita_ultima=False, estados=None, col_estado=None, tam=7.8):
    """Tabla con encabezado azul, filas alternas y columnas numéricas a la derecha."""
    numericas = set(numericas)

    def estilo_celda(j, enc=False, negrita=False):
        return _estilo(f"c{int(enc)}{int(negrita)}{int(j in numericas)}{tam}", fontSize=tam,
                       leading=tam * 1.28, alignment=2 if j in numericas else 0,
                       fontName="Helvetica-Bold" if (enc or negrita) else "Helvetica",
                       textColor=colors.white if enc else TINTA)

    filas = [[P(E(c), estilo_celda(j, enc=True)) for j, c in enumerate(datos[0])]]
    ultima = len(datos) - 1
    for i, fila in enumerate(datos[1:], start=1):
        negrita = negrita_ultima and i == ultima
        filas.append([P(c, estilo_celda(j, negrita=negrita)) if isinstance(c, str) else c
                      for j, c in enumerate(fila)])
    t = Table(filas, colWidths=anchos, repeatRows=1, hAlign="LEFT")
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINEA),
    ]
    for i in range(2, len(filas), 2):
        estilo.append(("BACKGROUND", (0, i), (-1, i), FONDO))
    if negrita_ultima:
        estilo.append(("LINEABOVE", (0, -1), (-1, -1), 0.8, TINTA_2))
    if estados is not None and col_estado is not None:
        for i, est in enumerate(estados, start=1):
            estilo.append(("BACKGROUND", (col_estado, i), (col_estado, i), ESTADO_COLOR[est]))
    t.setStyle(TableStyle(estilo))
    return t


def chip(estado):
    return Paragraph(f'<font color="{ESTADO_TEXTO[estado]}">{ESTADO_ETIQUETA[estado]}</font>', S["chip"])


def _num_der(texto):
    return P(texto, _estilo("nd", fontSize=7.8, leading=9.8, alignment=2))


# ------------------------------------------------------------------ páginas
class _Doc(BaseDocTemplate):
    def __init__(self, ruta, r):
        super().__init__(str(ruta), pagesize=letter, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                         topMargin=2.0 * cm, bottomMargin=1.7 * cm,
                         title=f"Informe de riesgos de tesorería - {r['corte']:%Y-%m-%d}",
                         author="Motor de reporting de riesgos")
        self.r = r
        marco = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="m")
        self.addPageTemplates([PageTemplate(id="todas", frames=[marco], onPage=self._decorar)])

    def _decorar(self, canvas, doc):
        r = self.r
        canvas.saveState()
        ancho, alto = letter
        if doc.page > 1:
            canvas.setFont("Helvetica-Bold", 7.5)
            canvas.setFillColor(NAVY)
            canvas.drawString(1.8 * cm, alto - 1.2 * cm, texto_pdf(r["politica"]["nombre"]))
            canvas.setFont("Helvetica", 7.5)
            canvas.setFillColor(TINTA_2)
            canvas.drawRightString(ancho - 1.8 * cm, alto - 1.2 * cm,
                                   f"Informe de riesgos de tesorería | Corte {fecha_larga(r['corte'])}")
            canvas.setStrokeColor(LINEA)
            canvas.setLineWidth(0.6)
            canvas.line(1.8 * cm, alto - 1.35 * cm, ancho - 1.8 * cm, alto - 1.35 * cm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(TENUE)
        nota = r["politica"].get("nota_pie", "")
        marca = f" | {C.MARCA}" if C.MARCA else ""
        canvas.drawString(1.8 * cm, 1.1 * cm, texto_pdf(
            f"Motor de reporting de riesgos v{C.VERSION}{marca} | generado {r['traza']['ejecutado'][:16]}"))
        if nota:
            canvas.drawString(1.8 * cm, 0.75 * cm, texto_pdf(nota))
        canvas.drawRightString(ancho - 1.8 * cm, 1.1 * cm, f"Página {doc.page}")
        canvas.restoreState()


def _kpi(rotulo, valor, sub):
    return [P(E(rotulo), "kpi_rot"), P(E(valor), "kpi_val"), P(sub, "kpi_sub")]


def _delta(actual, previo, fmt="pct"):
    if previo is None or previo == 0 or pd.isna(previo):
        return "Primer corte procesado"
    if fmt == "pp":
        d = 100 * (actual - previo)
        return f"{'+' if d >= 0 else ''}{num(d, 1)} pp frente al corte anterior"
    cambio = actual / previo - 1
    signo = "+" if cambio >= 0 else ""
    return f"{signo}{num(100 * cambio, 1)}% frente al corte anterior"


def _resumen(r) -> list:
    ind, prev, lim = r["indicadores"], r["previo"] or {}, r["limites"]
    n = lim["estado"].value_counts()
    historia = [
        Spacer(1, 0.2 * cm),
        P(E(r["politica"]["nombre"]).upper(), "entidad"),
        P("Informe mensual de riesgos de tesorería", "titulo"),
        P(f"Corte al {fecha_larga(r['corte'])} &nbsp;|&nbsp; Para el Comité de Riesgos &nbsp;|&nbsp; "
          f"Cifras en millones de pesos (COP M)", "sub"),
    ]
    tiles = [
        _kpi("Valor del portafolio", f"COP {num(ind['VALOR_PORTAFOLIO'], 0)} M",
             _delta(ind["VALOR_PORTAFOLIO"], prev.get("VALOR_PORTAFOLIO"))),
        _kpi("VaR histórico 1 día (99%)", f"COP {num(ind['VAR_HS_1D'], 0)} M",
             _delta(ind["VAR_HS_1D"], prev.get("VAR_HS_1D"))),
        _kpi("IRL razón a 30 días", pct(ind["IRL_30D"], 0),
             _delta(ind["IRL_30D"], prev.get("IRL_30D"), "pp")),
        _kpi("Semáforo de límites", f"{n.get('ROJO', 0)} · {n.get('ÁMBAR', 0)} · {n.get('VERDE', 0)}",
             "excedidos · en alerta · cumplen"),
    ]
    t = Table([[celda for celda in [tiles[0], tiles[1], tiles[2], tiles[3]]]],
              colWidths=[ANCHO_UTIL / 4] * 4)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), FONDO), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBEFORE", (1, 0), (-1, 0), 2, colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    historia += [t, Spacer(1, 0.45 * cm), P("1. Mensajes clave del corte", "h1")]
    filas = []
    for tono, texto in r["mensajes"]:
        est = TONO_ESTADO[tono]
        filas.append([chip(est) if est else P('<font color="#52514e">Info</font>', "chip"), P(E(texto), "p1")])
    tm = Table(filas, colWidths=[1.7 * cm, ANCHO_UTIL - 1.7 * cm])
    estilo = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3.5),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINEA)]
    for i, (tono, _) in enumerate(r["mensajes"]):
        est = TONO_ESTADO[tono]
        estilo.append(("BACKGROUND", (0, i), (0, i), ESTADO_COLOR[est] if est else FONDO))
    tm.setStyle(TableStyle(estilo))
    historia += [tm, Spacer(1, 0.3 * cm), P("Acciones sugeridas para el comité", "h1"),
                 P("Generadas por reglas a partir del corte. El monto lleva el indicador al límite (rojo) o a la "
                   "zona verde (ámbar); la decisión es del comité. Guía de lectura y glosario: sección 11.", "peq"),
                 Spacer(1, 0.12 * cm)]
    filas, estilo = [], [("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                         ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINEA)]
    for i, a in enumerate(r["acciones"]):
        est = a["prioridad"] if a["prioridad"] in ESTADO_COLOR else None
        celda = chip(est) if est else P('<font color="#52514e">Info</font>', "chip")
        monto = "" if a["monto"] is None else f"<br/><b>{E(millones(a['monto']))}</b>"
        filas.append([celda, P(f"<b>{E(a['tema'])}.</b> {E(a['accion'])}", "p1"),
                      P(monto.replace("<br/>", "") or "-", _estilo("mt", fontSize=8.5, leading=11, alignment=2))])
        estilo.append(("BACKGROUND", (0, i), (0, i), ESTADO_COLOR[est] if est else FONDO))
    ta = Table(filas, colWidths=[1.7 * cm, ANCHO_UTIL - 4.5 * cm, 2.8 * cm])
    ta.setStyle(TableStyle(estilo))
    historia += [ta, PageBreak()]
    return historia


def _limites(r, graficas) -> list:
    lim = r["limites"]
    datos = [["Estado", "Indicador", "Categoría", "Valor", "Límite", "Alerta", "Uso"]]
    for _, l in lim.iterrows():
        indicador = E(l["indicador"]) + (f"<br/><font color='#52514e' size='6.8'>{E(l['detalle'])}</font>"
                                          if l["detalle"] else "")
        uso = "-" if pd.isna(l["uso"]) else pct(l["uso"], 0)
        datos.append([chip(l["estado"]), indicador, E(l["categoria"]), _num_der(E(l["valor_txt"])),
                      _num_der(E(l["limite_txt"])), _num_der(E(l["alerta_txt"])), _num_der(uso)])
    historia = [P("2. Límites y evolución", "h1"),
                P(f"Límites definidos en la política vigente ({E(r['politica']['organo'])}). "
                  "Uso = valor / límite para los máximos y límite / valor para los mínimos.", "peq"),
                Spacer(1, 0.15 * cm),
                tabla(datos, [1.7 * cm, 6.6 * cm, 2.4 * cm, 1.9 * cm, 1.8 * cm, 1.8 * cm, 1.2 * cm],
                      estados=list(lim["estado"]), col_estado=0)]
    if graficas.get("evolucion"):
        historia += [Spacer(1, 0.35 * cm), P("Evolución de indicadores clave", "h2"),
                     imagen(graficas["evolucion"])]
    else:
        historia.append(P("La evolución mensual aparecerá a partir del segundo corte procesado.", "peq"))
    historia.append(PageBreak())
    return historia


def _portafolio(r, graficas) -> list:
    t = r["tabla"]
    total = t["valor"].sum()
    datos = [["Tipo de instrumento", "N.º", "Valor (COP M)", "% portafolio", "Duración mod.",
              "TIR promedio", "DV01 (COP M/pb)"]]
    for tipo, g in t.groupby("tipo", sort=False):
        v = g["valor"].sum()
        rf = g["es_renta_fija"].all()
        dur = (g["duracion_mod"] * g["valor"]).sum() / v if rf else np.nan
        tires = g.dropna(subset=["tir"])
        tir = (tires["tir"] * tires["valor"]).sum() / tires["valor"].sum() if len(tires) else np.nan
        datos.append([E(C.NOMBRE_TIPO[tipo]), num(len(g)), num(v / 1e6, 0), pct(v / total),
                      "-" if np.isnan(dur) else num(dur, 2), "-" if np.isnan(tir) else pct(tir, 2),
                      num(g["dv01"].sum() / 1e6, 2)])
    rf = t[t["es_renta_fija"]]
    datos.append(["Total", num(len(t)), num(total / 1e6, 0), "100,0%",
                  num((rf["duracion_mod"] * rf["valor"]).sum() / rf["valor"].sum(), 2) + " (RF)", "",
                  num(t["dv01"].sum() / 1e6, 2)])
    n = r["mercado_niveles"]
    mercado = (f"Niveles de mercado al {r['fecha_mercado']:%d/%m/%Y}: TES 1 año {num(n['TES_1A'], 2)}%, "
               f"TES 10 años {num(n['TES_10A'], 2)}%, spread AAA {num(n['SPR_AAA'], 0)} pb, "
               f"spread AA {num(n['SPR_AA'], 0)} pb, TRM {num(n['TRM'], 2)}.")
    plazo = r["concentracion"]["por_plazo"]
    datos_p = [["Plazo al vencimiento", "Valor (COP M)", "% portafolio"]]
    for _, g in plazo.iterrows():
        datos_p.append([E(g["grupo"]), num(g["valor"] / 1e6, 0), pct(g["pct"])])
    return [P("3. Portafolio", "h1"),
            P(f"Portafolio valorado con la curva cero cupón TES más el spread de crédito de la calificación "
              f"de cada emisor. {E(mercado)}", "p"),
            tabla(datos, [4.6 * cm, 1.1 * cm, 2.4 * cm, 2.1 * cm, 2.2 * cm, 2.2 * cm, 2.4 * cm],
                  numericas=range(1, 7), negrita_ultima=True),
            Spacer(1, 0.4 * cm), imagen(graficas["composicion"]), Spacer(1, 0.3 * cm),
            KeepTogether([P("Perfil de vencimientos", "h2"),
                          tabla(datos_p, [5.0 * cm, 3.0 * cm, 3.0 * cm], numericas=(1, 2))]),
            PageBreak()]


def _mercado(r, graficas) -> list:
    v, pt = r["var"], r["patrimonio_tecnico"]
    total = v["valor_total"]
    datos = [["Medida (1 día)", "COP M", "% portafolio", "% patrimonio técnico", "A 10 días (COP M)"]]
    for nombre, valor in (("VaR 99% histórico (medida principal)", v["var_hs"]),
                          ("ES 97,5% histórico", v["es_hs"]),
                          ("VaR 99% paramétrico EWMA", v["var_param"]),
                          ("ES 97,5% paramétrico normal", v["es_param"])):
        datos.append([E(nombre), num(valor / 1e6, 0), pct(valor / total, 2), pct(valor / pt, 2),
                      num(valor / 1e6 * np.sqrt(C.DIAS_HORIZONTE_REGULATORIO), 0)])
    ratio = v["es_hs"] / v["es_param"] - 1 if v["es_param"] > 0 else 0.0
    texto_colas = (f"El ES histórico supera en {pct(ratio, 0)} al que implicaría una distribución normal: "
                   "evidencia de colas pesadas en los factores de riesgo." if ratio > 0.05 else
                   "El ES histórico es cercano al normal: en la ventana actual las colas no son extremas.")
    grupos = [["Factor de riesgo", "VaR histórico (COP M)", "VaR paramétrico (COP M)"]]
    for g in C.GRUPOS_FACTORES:
        grupos.append([E(g), num(v["grupos_hs"][g] / 1e6, 0), num(v["grupos_param"][g] / 1e6, 0)])
    grupos.append(["Beneficio de diversificación", num(-v["diversificacion_hs"] / 1e6, 0),
                   num(-v["diversificacion_param"] / 1e6, 0)])
    grupos.append(["VaR total", num(v["var_hs"] / 1e6, 0), num(v["var_param"] / 1e6, 0)])
    return [P("4. Riesgo de mercado", "h1"),
            P("Medida principal: VaR histórico con revaluación completa (los cambios diarios reales de los "
              f"últimos {C.VENTANA_HS} días aplicados al portafolio de hoy). Se contrasta con el VaR "
              "paramétrico delta-normal con covarianza EWMA (RiskMetrics).", "p"),
            tabla(datos, [6.2 * cm, 2.2 * cm, 2.4 * cm, 3.2 * cm, 3.0 * cm], numericas=range(1, 5)),
            Spacer(1, 0.15 * cm), P(E(texto_colas), "peq"), Spacer(1, 0.3 * cm),
            imagen(graficas["distribucion"]), Spacer(1, 0.2 * cm),
            KeepTogether([P("Riesgo por factor y diversificación", "h2"),
                          tabla(grupos, [6.2 * cm, 4.0 * cm, 4.0 * cm], numericas=(1, 2), negrita_ultima=True)]),
            PageBreak(),
            P("Contribuciones y sensibilidades", "h2"),
            P("Contribución de cada posición a la pérdida promedio en el peor 2,5% de los escenarios "
              "(las contribuciones suman el ES). Identifica qué títulos concentran el riesgo de cola.", "peq"),
            imagen(graficas["contribucion"]), Spacer(1, 0.3 * cm),
            P(f"DV01 total: COP {num(r['tabla']['dv01'].sum() / 1e6, 2)} M por cada punto básico de alza "
              f"paralela de la curva TES. La gráfica muestra en qué plazos se concentra esa sensibilidad.", "peq"),
            imagen(graficas["dv01"]), PageBreak()]


def _backtesting(r, graficas) -> list:
    bt = r["backtesting"]
    datos = [["Modelo", "Excepciones", "Esperadas", "Zona Basilea", "Kupiec (p-valor)",
              "Christoffersen (p-valor)"]]
    for nombre, k in (("VaR histórico", "hs"), ("VaR paramétrico EWMA", "param")):
        x = bt[k]
        datos.append([nombre, num(x["excepciones"]), num(x["esperadas"], 1), x["zona"],
                      num(x["kupiec_p"], 3), num(x["christoffersen_p"], 3)])
    return [P("5. Backtesting", "h1"),
            P(f"Se mantiene fijo el portafolio de hoy y se compara su pérdida y ganancia diaria hipotética de "
              f"los últimos {bt['n']} días con el VaR que el modelo habría calculado el día anterior, usando "
              "solo la información disponible en ese momento. Una excepción ocurre cuando la pérdida supera "
              "el VaR.", "p"),
            imagen(graficas["backtesting"]), Spacer(1, 0.3 * cm),
            tabla(datos, [4.0 * cm, 2.2 * cm, 2.0 * cm, 2.5 * cm, 2.8 * cm, 3.5 * cm], numericas=range(1, 6)),
            Spacer(1, 0.2 * cm),
            P("Lectura: Kupiec prueba si la frecuencia de excepciones es coherente con el 1% esperado; "
              "Christoffersen prueba si las excepciones llegan en racimos. Un p-valor menor que 0,05 rechaza "
              "el modelo. Zonas de Basilea para 250 observaciones: verde hasta 4 excepciones, amarilla de 5 a "
              "9 y roja desde 10.", "peq"),
            PageBreak()]


def _estres(r, graficas) -> list:
    e = r["estres"].sort_values("pnl")
    datos = [["Escenario", "Tipo", "P&G (COP M)", "% patrimonio técnico", "Choque aplicado"]]
    for _, f in e.iterrows():
        choque = E(f["choque"]) + (f"<br/><font color='#52514e'>Ventana: {E(f['ventana'])}</font>"
                                   if f["ventana"] else "")
        datos.append([E(f["escenario"]), E(f["tipo"]), num(f["pnl"] / 1e6, 0), pct(f["pct_pt"], 2), choque])
    return [P("6. Pruebas de estrés", "h1"),
            P("Escenarios aprobados en la política. Los hipotéticos son choques instantáneos; los históricos "
              f"toman la peor ventana de {C.DIAS_VENTANA_ESTRES_HIST} días hábiles del periodo indicado y "
              "aplican esos movimientos reales al portafolio de hoy.", "p"),
            imagen(graficas["estres"]), Spacer(1, 0.3 * cm),
            tabla(datos, [4.4 * cm, 1.8 * cm, 2.0 * cm, 2.4 * cm, 6.8 * cm], numericas=(2, 3), tam=7.4),
            PageBreak()]


def _concentracion(r, graficas) -> list:
    c = r["concentracion"]
    lim = r["limites"].set_index("codigo")
    limite = float(lim.loc["EMISOR_MAX_PCT", "limite"]) if "EMISOR_MAX_PCT" in lim.index else None
    alerta = float(lim.loc["EMISOR_MAX_PCT", "alerta"]) if "EMISOR_MAX_PCT" in lim.index else None
    datos = [["Estado", "Emisor unificado", "Cómo aparece en el archivo", "Títulos", "COP M",
              "% portafolio", "% patrimonio"]]
    estados = []
    for _, f in c["emisores"].iterrows():
        if f["exento"] or limite is None:
            est = "SIN DATO" if f["exento"] else "VERDE"
        else:
            est = "ROJO" if f["pct_portafolio"] > limite else "ÁMBAR" if f["pct_portafolio"] > alerta else "VERDE"
        estados.append(est)
        nombres = "<br/>".join(E(n) for n in f["nombres"])
        celda_estado = chip(est) if not f["exento"] else P("Exento", "chip")
        datos.append([celda_estado, E(f["emisor"]), nombres, num(f["titulos"]), num(f["valor"] / 1e6, 0),
                      pct(f["pct_portafolio"]), pct(f["pct_pt"])])
    t = tabla(datos, [1.6 * cm, 4.4 * cm, 4.6 * cm, 1.3 * cm, 1.9 * cm, 2.0 * cm, 2.0 * cm],
              numericas=range(3, 7), estados=estados, col_estado=0, tam=7.4)
    resumen = [["Indicador", "Valor", "Lectura"],
               ["HHI emisores privados", num(c["hhi_privados"], 0),
                f"Equivale a {num(c['n_equivalente'], 1)} emisores del mismo tamaño"],
               ["Cinco mayores emisores privados", pct(c["top5_pct"]), "% del portafolio"],
               ["Renta fija A+ o inferior", pct(c["calif_a_o_inferior_pct"]), "% del portafolio"]]
    historia = [P("7. Concentración", "h1"),
                P("La exposición por emisor suma títulos y depósitos a la vista con la misma contraparte. "
                  "Antes de sumar, el motor unifica los nombres del archivo contra el maestro de emisores "
                  "(mayúsculas, tildes, puntuación, 'S.A.', abreviaturas y alias).", "p")]
    if len(c["emisor_max_nombres"]) > 1:
        historia.append(P(
            f"<b>Hallazgo:</b> {E(c['emisor_max'])} aparece escrito de {len(c['emisor_max_nombres'])} formas "
            f"({E('; '.join(c['emisor_max_nombres']))}). Agrupando por el nombre tal como está escrito, su "
            f"mayor participación visible sería {pct(c['emisor_max_pct_manual'])}; la exposición real "
            f"unificada es {pct(c['emisor_max_pct'])}.", "p"))
    historia += [imagen(graficas["concentracion"]), Spacer(1, 0.3 * cm), t, Spacer(1, 0.3 * cm),
                 KeepTogether([tabla(resumen, [5.0 * cm, 2.4 * cm, 7.0 * cm], numericas=(1,))]),
                 PageBreak()]
    return historia


def _liquidez(r, graficas) -> list:
    liq = r["liquidez"]
    b = liq["bandas"]
    datos = [["Banda", "Salidas contractuales", "Retiros estimados", "Entradas computables", "RLN",
              "RLN acumulado", "IRL razón"]]
    for _, f in b.iterrows():
        datos.append([f["banda"], num(f["salidas_contractuales"] / 1e6, 0), num(f["retiros_estimados"] / 1e6, 0),
                      num(f["entradas_computables"] / 1e6, 0), num(f["rln"] / 1e6, 0),
                      num(f["rln_acumulado"] / 1e6, 0), pct(f["irl_razon"], 0)])
    act = liq["resumen_activos"].sort_values("alac", ascending=False)
    datos_a = [["Categoría de activo", "Valor (COP M)", "Haircut", "Computable (COP M)"]]
    for _, f in act.iterrows():
        datos_a.append([E(f["descripcion"]), num(f["valor"] / 1e6, 0), pct(f["haircut"], 0),
                        num(f["alac"] / 1e6, 0)])
    datos_a.append(["Total activos líquidos ajustados (ALAC)", num(act["valor"].sum() / 1e6, 0), "",
                    num(liq["alac"] / 1e6, 0)])
    return [P("8. Liquidez", "h1"),
            P("Indicador de riesgo de liquidez simplificado: activos líquidos ajustados por haircuts (ALAC) "
              "frente al requerimiento de liquidez neto (RLN) acumulado por bandas. El RLN suma las salidas "
              "contractuales y los retiros estimados de depósitos a la vista, y resta las entradas "
              "contractuales hasta un tope del 75% de las salidas.", "p"),
            imagen(graficas["liquidez"]), Spacer(1, 0.3 * cm),
            tabla(datos, [2.3 * cm, 2.9 * cm, 2.5 * cm, 2.9 * cm, 2.0 * cm, 2.5 * cm, 1.9 * cm],
                  numericas=range(1, 7)),
            Spacer(1, 0.35 * cm),
            KeepTogether([P("Composición de los activos líquidos", "h2"),
                          tabla(datos_a, [7.4 * cm, 3.0 * cm, 2.0 * cm, 3.4 * cm], numericas=(1, 2, 3),
                                negrita_ultima=True)]),
            Spacer(1, 0.2 * cm),
            P(f"Saldo de depósitos a la vista: COP {num(liq['saldo_vista'] / 1e6, 0)} M. Metodología "
              "ilustrativa: antes de su uso oficial se ajusta al estándar del supervisor de la entidad.", "peq"),
            PageBreak()]


def _calidad(r) -> list:
    h = r["hallazgos"].tabla()
    conteo = [["Severidad", "Cantidad", "Qué significa"],
              ["ERROR", num((h["severidad"] == "ERROR").sum()), "Fila excluida del cálculo: corregir en el origen"],
              ["ADVERTENCIA", num((h["severidad"] == "ADVERTENCIA").sum()),
               "Corregido automáticamente: verificar"],
              ["INFO", num((h["severidad"] == "INFO").sum()), "Conversión de formato sin impacto"]]
    datos = [["Severidad", "Hoja", "Fila", "Campo", "Valor original", "Detalle y acción"]]
    for _, f in h.iterrows():
        datos.append([f["severidad"], E(f["hoja"]), "" if pd.isna(f["fila_excel"]) else num(f["fila_excel"]),
                      E(f["campo"]), E(f["valor_original"]),
                      E(f["detalle"]) + (f" <i>{E(f['accion'])}</i>" if f["accion"] else "")])
    return [P("9. Calidad de datos", "h1"),
            P("Cada hallazgo indica la hoja y la fila exactas del archivo de la entidad para corregir el "
              "origen. Las filas con ERROR no entran en ningún cálculo de este informe.", "p"),
            tabla(conteo, [3.0 * cm, 2.0 * cm, 9.0 * cm], numericas=(1,)), Spacer(1, 0.35 * cm),
            tabla(datos, [2.2 * cm, 2.3 * cm, 1.0 * cm, 2.4 * cm, 3.2 * cm, 6.3 * cm], numericas=(2,), tam=7.2),
            PageBreak()]


def _metodologia(r) -> list:
    tr = r["traza"]
    param = [["Parámetro", "Valor"]] + [[E(k), E(v)] for k, v in tr["parametros"].items()]
    archivos = [["Archivo de entrada", "Huella SHA-256"]] + [[E(n), f"<font size='6.5'>{h}</font>"]
                                                              for n, h in tr["archivos"]]
    textos = [
        ("Valoración", "Revaluación completa por flujos de caja. Tasa de descuento de cada flujo: curva cero "
         "cupón TES interpolada linealmente a su plazo más el spread de crédito de la calificación del emisor "
         "(las calificaciones de corto plazo se llevan a su equivalente de largo plazo). Los CDT IBR se valoran "
         "como flotantes: próximo cupón fijado con el IBR del último reprecio y, después, nominal más el valor "
         "presente de la diferencia entre el margen pactado y el spread de mercado."),
        ("VaR y ES", f"Simulación histórica de {C.VENTANA_HS} días con revaluación completa (medida principal) y "
         f"paramétrico delta-normal con covarianza EWMA (lambda {str(C.LAMBDA_EWMA).replace('.', ',')}). VaR al "
         f"{pct(C.CONFIANZA_VAR, 0)} y ES al {pct(C.CONFIANZA_ES, 1)} a 1 día; el horizonte de 10 días se obtiene "
         "con la regla de la raíz del tiempo (aproximación). Contribuciones: descomposición del ES histórico "
         "por posición y VaR por grupo de factores moviendo un grupo a la vez."),
        ("Backtesting", f"Hipotético sobre {C.VENTANA_BACKTEST} días con el portafolio actual fijo; pruebas de "
         "Kupiec (cobertura) y Christoffersen (independencia) y zonas de Basilea."),
        ("Límites", "Parámetros de negocio leídos de la política de riesgos de la entidad. Máximo: rojo si el "
         "valor supera el límite y ámbar si supera la alerta. Mínimo: rojo si el valor es inferior al límite y "
         "ámbar si es inferior a la alerta."),
        ("Alcance y limitaciones",
         ("Demostración con entidad y emisores ficticios y datos de mercado sintéticos calibrados a niveles "
          "aproximados del mercado colombiano. " if r["politica"].get("demo") else "")
         + "La curva TES y los spreads de crédito provienen del archivo de mercado configurado (en producción, "
         "el proveedor de precios de la entidad). El IRL es una versión simplificada y no reemplaza el reporte "
         "regulatorio. Los instrumentos no soportados en esta versión (p. ej. UVR, titularizaciones) se reportan "
         "como error de datos y se excluyen."),
    ]
    historia = [P("10. Metodología y trazabilidad", "h1")]
    for titulo, texto in textos:
        historia += [P(titulo, "h2"), P(E(texto), "p")]
    historia += [Spacer(1, 0.2 * cm), P("Parámetros de la ejecución", "h2"),
                 tabla(param, [6.0 * cm, 6.0 * cm]), Spacer(1, 0.3 * cm),
                 P("Trazabilidad de insumos", "h2"),
                 P("La huella SHA-256 identifica de forma única cada archivo usado: si alguien modifica el "
                   "archivo, la huella cambia. Permite a auditoría verificar qué datos produjeron este informe.",
                   "peq"),
                 tabla(archivos, [5.2 * cm, 11.8 * cm]),
                 Spacer(1, 0.25 * cm),
                 P(f"Motor v{tr['version']} · ejecutado el {tr['ejecutado']} · tiempo de cálculo "
                   f"{num(tr['segundos_calculo'], 1)} segundos.", "peq")]
    return historia


GUIA = [
    ("1. Resumen ejecutivo", "¿Qué requiere atención este mes?",
     "Mensajes en rojo y ámbar, y el monto de cada acción sugerida.",
     "Aprobar, ajustar o rechazar el plan de acción y dejarlo en el acta."),
    ("2. Límites y evolución", "¿Cumplimos la política? ¿Hacia dónde vamos?",
     "Estado y uso de cada límite; tendencia de los últimos meses.",
     "Anticiparse a los indicadores en verde que se acercan a su alerta."),
    ("3. Portafolio", "¿Qué tenemos y a qué plazo?",
     "Composición por tipo, calificación y vencimientos; duración y TIR.",
     "Verificar la coherencia con la estrategia de inversión aprobada."),
    ("4. Riesgo de mercado", "¿Cuánto podemos perder en un día normal y en uno muy malo?",
     "VaR (pérdida que solo se supera 1 de cada 100 días), ES (promedio de ese 1% de peores días), "
     "factor dominante y posiciones que más aportan.",
     "Decidir si el riesgo es coherente con el apetito y qué factor o título reducir."),
    ("5. Backtesting", "¿Podemos confiar en el VaR?",
     "Excepciones observadas frente a las esperadas y zona de Basilea.",
     "Mantener, ajustar o reemplazar el modelo de medición."),
    ("6. Pruebas de estrés", "¿Qué pasaría en una crisis?",
     "Peor escenario frente al límite; posición más afectada.",
     "Dimensionar el colchón de capital y evaluar coberturas."),
    ("7. Concentración", "¿Dependemos demasiado de una contraparte?",
     "Exposición por emisor unificado (títulos + depósitos) y HHI.",
     "Reducir o diversificar exposiciones; actualizar cupos por contraparte."),
    ("8. Liquidez", "¿Podemos atender retiros y vencimientos?",
     "IRL a 7 y 30 días y la banda con mayor presión diaria.",
     "Mover recursos a activos líquidos o escalonar vencimientos de captaciones."),
    ("9. Calidad de datos", "¿Los datos del informe son confiables?",
     "Filas excluidas (ERROR) y correcciones automáticas (ADVERTENCIA).",
     "Exigir la corrección en el origen y asignar responsables."),
    ("10. Metodología", "¿Cómo se calculó cada cifra?",
     "Parámetros y huellas SHA-256 de los archivos de entrada.",
     "Soporte ante auditoría, revisoría fiscal y el supervisor."),
]

GLOSARIO = [
    ("VaR 99% a 1 día", "Pérdida que, según la historia reciente, solo se supera 1 de cada 100 días."),
    ("Expected Shortfall (ES)", "Pérdida promedio en los peores días (el 2,5% más adverso): mide qué tan "
     "profunda es la cola que el VaR no ve."),
    ("Simulación histórica", "Aplica al portafolio de hoy los movimientos reales del mercado de los últimos "
     "500 días hábiles."),
    ("Backtesting / excepción", "Comparación del VaR con la pérdida real; una excepción es un día en que la "
     "pérdida superó el VaR."),
    ("Kupiec y zona de Basilea", "Pruebas que indican si el número de excepciones es coherente con el 1% "
     "esperado (verde hasta 4 en 250 días)."),
    ("Duración modificada", "Cambio porcentual aproximado del valor ante un movimiento de 1 punto en las tasas."),
    ("DV01", "Pérdida en pesos si las tasas suben un punto básico (0,01%)."),
    ("Spread de crédito", "Rendimiento adicional sobre los TES que se exige a un emisor por su riesgo."),
    ("HHI", "Índice de concentración: suma de los cuadrados de las participaciones (10.000 = un solo emisor)."),
    ("IRL razón", "Activos líquidos ajustados divididos por el requerimiento neto de liquidez de la banda."),
    ("ALAC y haircut", "Activos líquidos después de descontar (haircut) la pérdida posible al venderlos rápido."),
    ("Estrés histórico", "La peor ventana de 20 días de un periodo de crisis, aplicada al portafolio actual."),
]


def _guia(r) -> list:
    datos = [["Sección", "Pregunta que responde", "Qué mirar primero", "Qué decide el comité"]]
    for fila in GUIA:
        datos.append([E(c) for c in fila])
    semaforo = [["Color", "Significado", "Respuesta esperada"],
                [chip("ROJO"), "Límite excedido", "Acción correctiva con plazo y responsable"],
                [chip("ÁMBAR"), "Cerca del límite (zona de alerta)", "Acción preventiva o seguimiento reforzado"],
                [chip("VERDE"), "Dentro de la política", "Monitoreo normal"]]
    glosario = [["Término", "En palabras simples"]] + [[E(a), E(b)] for a, b in GLOSARIO]
    return [PageBreak(), P("11. Cómo leer este informe", "h1"),
            P("Cada mes el informe responde cuatro preguntas: cuánto podemos perder, si estamos dentro de los "
              "límites aprobados, si tenemos liquidez suficiente y si los datos son confiables. Se recomienda "
              "leer la página 1 completa y luego solo las secciones señaladas en rojo o ámbar.", "p"),
            tabla(datos, [3.0 * cm, 3.9 * cm, 5.3 * cm, 5.0 * cm], tam=7.4),
            Spacer(1, 0.35 * cm),
            KeepTogether([P("El semáforo", "h2"),
                          tabla(semaforo, [1.9 * cm, 5.6 * cm, 9.7 * cm], estados=["ROJO", "ÁMBAR", "VERDE"],
                                col_estado=0)]),
            Spacer(1, 0.35 * cm),
            KeepTogether([P("Glosario", "h2"), tabla(glosario, [4.2 * cm, 13.0 * cm], tam=7.4)])]


def generar_pdf(r: dict, graficas: dict, ruta: Path) -> Path:
    doc = _Doc(ruta, r)
    historia = (_resumen(r) + _limites(r, graficas) + _portafolio(r, graficas) + _mercado(r, graficas)
                + _backtesting(r, graficas) + _estres(r, graficas) + _concentracion(r, graficas)
                + _liquidez(r, graficas) + _calidad(r) + _metodologia(r) + _guia(r))
    doc.build(historia)
    return ruta
