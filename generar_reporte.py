"""
MOTOR DE REPORTING DE RIESGOS DE TESORERÍA
==========================================

Convierte el Excel mensual de posiciones de la entidad en:
  - salidas/AAAA-MM-DD/informe_riesgos_AAAA-MM-DD.pdf   (informe para el comité)
  - salidas/AAAA-MM-DD/anexo_riesgos_AAAA-MM-DD.xlsx    (detalle para auditoría)
  - salidas/AAAA-MM-DD/graficas/*.png
  - salidas/historial_indicadores.csv                    (evolución mensual)

Uso (con el entorno virtual activo, parado en la carpeta del proyecto):
    python generar_reporte.py                     procesa el corte más reciente
    python generar_reporte.py --corte 2026-09-30  procesa un corte específico
    python generar_reporte.py --todos             procesa todos los cortes en orden
    python generar_reporte.py --debug             muestra el detalle técnico de un error
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import traceback

import pandas as pd

from riesgo import config as C
from riesgo.anexo_excel import generar_anexo
from riesgo.graficas import generar_todas
from riesgo.informe_pdf import generar_pdf
from riesgo.lectura import ErrorEntrada, leer_politica
from riesgo.mercado import ErrorMercado, Mercado
from riesgo.proceso import (actualizar_historial, cargar_historial, indicadores_previos,
                            procesar_corte)
from riesgo.riesgo_mercado import ErrorRiesgo
from riesgo.utilidades import num, pct

PASOS = 6


def listar_cortes() -> list[tuple[pd.Timestamp, object]]:
    cortes = []
    for ruta in C.DIR_ENTRADA.glob("posiciones_*.xlsx"):
        m = re.match(C.PATRON_POSICIONES, ruta.name)
        if m:
            cortes.append((pd.Timestamp(m.group(1)), ruta))
    return sorted(cortes)


def avance(paso: int, texto: str) -> None:
    print(f"   [{paso}/{PASOS}] {texto}")


def procesar(corte, ruta, politica, mercado) -> float:
    t0 = time.perf_counter()
    print(f"\n>> Corte {corte:%Y-%m-%d}  ({ruta.name})")
    hist = cargar_historial()
    r = procesar_corte(ruta, corte, politica, mercado, indicadores_previos(hist, corte), avance)
    hist = actualizar_historial(hist, corte, r["indicadores"])

    avance(6, "Gráficas, informe PDF y anexo Excel")
    carpeta = C.DIR_SALIDAS / f"{corte:%Y-%m-%d}"
    carpeta.mkdir(parents=True, exist_ok=True)
    graficas = generar_todas(r, hist[hist.index <= corte], carpeta / "graficas")
    pdf = carpeta / f"informe_riesgos_{corte:%Y-%m-%d}.pdf"
    xlsx = carpeta / f"anexo_riesgos_{corte:%Y-%m-%d}.xlsx"
    for destino, funcion in ((pdf, lambda: generar_pdf(r, graficas, pdf)),
                             (xlsx, lambda: generar_anexo(r, xlsx))):
        try:
            funcion()
        except PermissionError as e:
            raise ErrorEntrada(f"No se pudo escribir {destino.name}: ciérrelo (Excel o el lector de PDF) "
                               "y vuelva a ejecutar.") from e

    ind, lim = r["indicadores"], r["limites"]
    n = lim["estado"].value_counts()
    h = r["hallazgos"]
    segundos = time.perf_counter() - t0
    print(f"   Portafolio: COP {num(ind['VALOR_PORTAFOLIO'], 0)} M | VaR 1d 99%: COP {num(ind['VAR_HS_1D'], 0)} M"
          f" | IRL 30d: {pct(ind['IRL_30D'], 0)}")
    print(f"   Límites: {n.get('ROJO', 0)} excedidos, {n.get('ÁMBAR', 0)} en alerta, {n.get('VERDE', 0)} cumplen"
          f" | Datos: {h.conteo('ERROR')} errores, {h.conteo('ADVERTENCIA')} advertencias")
    for _, l in lim[lim["estado"] == "ROJO"].iterrows():
        print(f"   ! EXCEDIDO: {l['indicador']} = {l['valor_txt']} (límite {l['limite_txt']})"
              + (f" - {l['detalle']}" if l["detalle"] else ""))
    print(f"   Informe: {pdf.relative_to(C.RAIZ)}")
    print(f"   Anexo:   {xlsx.relative_to(C.RAIZ)}")
    print(f"   Tiempo:  {num(segundos, 1)} segundos")
    return segundos


def main() -> int:
    ap = argparse.ArgumentParser(description="Motor de reporting de riesgos de tesorería")
    ap.add_argument("--corte", help="fecha de corte AAAA-MM-DD (por defecto, la más reciente)")
    ap.add_argument("--todos", action="store_true", help="procesa todos los cortes disponibles, en orden")
    ap.add_argument("--debug", action="store_true", help="muestra el detalle técnico de los errores")
    args = ap.parse_args()
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(errors="replace")   # consolas de Windows con codificación limitada
        except (AttributeError, ValueError):
            pass

    print("=" * 66)
    print(f" MOTOR DE REPORTING DE RIESGOS DE TESORERÍA  v{C.VERSION}")
    print("=" * 66)
    try:
        cortes = listar_cortes()
        if not cortes:
            raise ErrorEntrada(f"No hay archivos posiciones_AAAA-MM-DD.xlsx en {C.DIR_ENTRADA}. "
                               "Para la demo, ejecute primero: python herramientas/generar_datos_demo.py")
        if args.corte:
            buscado = pd.Timestamp(args.corte)
            cortes = [c for c in cortes if c[0] == buscado]
            if not cortes:
                raise ErrorEntrada(f"No existe entrada/posiciones_{args.corte}.xlsx")
        elif not args.todos:
            cortes = cortes[-1:]

        politica = leer_politica(C.ARCHIVO_POLITICA)
        mercado = Mercado(C.ARCHIVO_MERCADO)
        print(f" Entidad: {politica['nombre']}")
        print(f" Mercado: {len(mercado.df):,} días ({mercado.df.index[0]:%Y-%m-%d} a "
              f"{mercado.df.index[-1]:%Y-%m-%d})".replace(",", "."))
        total = sum(procesar(corte, ruta, politica, mercado) for corte, ruta in cortes)
        if len(cortes) > 1:
            print(f"\n{len(cortes)} cortes procesados en {num(total, 1)} segundos.")
        print("\nListo.")
        return 0
    except (ErrorEntrada, ErrorMercado, ErrorRiesgo) as e:
        print(f"\nNO SE PUDO GENERAR EL INFORME:\n   {e}")
        if args.debug:
            traceback.print_exc()
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"\nERROR INESPERADO: {type(e).__name__}: {e}")
        print("   Ejecute con --debug para ver el detalle técnico y compártalo con soporte.")
        if args.debug:
            traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
