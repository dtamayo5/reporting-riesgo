"""
Parámetros TÉCNICOS del motor.

Separación deliberada de responsabilidades:
  - Aquí viven las decisiones metodológicas (niveles de confianza, ventanas,
    factores de riesgo, convenciones) que mantiene el consultor.
  - Los parámetros de NEGOCIO (límites, maestro de emisores, haircuts de
    liquidez, factores de retiro, escenarios de estrés) viven en
    entrada/politica_riesgo.xlsx, porque los aprueba la entidad y su
    comité, no el programador.
"""
from pathlib import Path

VERSION = "1.1.0"

# Marca que aparece en el pie del informe (dejar "" para no mostrarla)
MARCA = "David - Consultoría Cuantitativa de Riesgo"

# --------------------------------------------------------------------------
# Rutas (relativas a la carpeta del proyecto, funcionan desde cualquier lugar)
# --------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parent.parent
DIR_ENTRADA = RAIZ / "entrada"
DIR_MERCADO = RAIZ / "mercado"
DIR_SALIDAS = RAIZ / "salidas"
ARCHIVO_POLITICA = DIR_ENTRADA / "politica_riesgo.xlsx"
ARCHIVO_MERCADO = DIR_MERCADO / "factores_mercado.csv"
ARCHIVO_HISTORIAL = DIR_SALIDAS / "historial_indicadores.csv"
PATRON_POSICIONES = r"^posiciones_(\d{4}-\d{2}-\d{2})\.xlsx$"

# --------------------------------------------------------------------------
# Factores de riesgo
#   - Nodos de la curva cero cupón TES (tasas en % efectivo anual)
#   - Spreads de crédito sobre TES (puntos básicos)
#   - Factores en logaritmo (TRM y un índice accionario local)
# --------------------------------------------------------------------------
NODOS_CURVA = {
    "TES_3M": 0.25, "TES_1A": 1.0, "TES_2A": 2.0, "TES_3A": 3.0,
    "TES_5A": 5.0, "TES_7A": 7.0, "TES_10A": 10.0, "TES_15A": 15.0,
}
FACTORES_SPREAD = ["SPR_AAA", "SPR_AA"]
FACTORES_LOG = ["TRM", "COLCAP"]
FACTORES = list(NODOS_CURVA) + FACTORES_SPREAD + FACTORES_LOG
COLUMNA_IBR = "IBR"  # no es factor de VaR: solo fija el cupón vigente de los flotantes

GRUPOS_FACTORES = {
    "Tasas TES": list(NODOS_CURVA),
    "Spreads de crédito": FACTORES_SPREAD,
    "Tasa de cambio": ["TRM"],
    "Renta variable": ["COLCAP"],
}
ETIQUETA_NODO = {"TES_3M": "3M", "TES_1A": "1A", "TES_2A": "2A", "TES_3A": "3A",
                 "TES_5A": "5A", "TES_7A": "7A", "TES_10A": "10A", "TES_15A": "15A"}

# --------------------------------------------------------------------------
# Metodología de riesgo de mercado
# --------------------------------------------------------------------------
CONFIANZA_VAR = 0.99          # VaR al 99% (estándar Basilea)
CONFIANZA_ES = 0.975          # Expected Shortfall al 97,5% (estándar FRTB)
VENTANA_HS = 500              # días hábiles de la simulación histórica (~2 años)
VENTANA_BACKTEST = 250        # días hábiles evaluados en el backtesting (~1 año)
LAMBDA_EWMA = 0.94            # decaimiento RiskMetrics (un IGARCH sin constante)
OBS_INICIO_EWMA = 60          # observaciones para inicializar la covarianza EWMA
DIAS_HORIZONTE_REGULATORIO = 10   # VaR a 10 días por regla de la raíz del tiempo
DIAS_VENTANA_ESTRES_HIST = 20     # ventana de los escenarios históricos de estrés
BLOQUE_ESCENARIOS = 4000          # escenarios por lote en la revaluación (memoria)

# --------------------------------------------------------------------------
# Calidad de datos
# --------------------------------------------------------------------------
TOLERANCIA_VALORACION = 0.02      # diferencia admitida valor reportado vs. teórico
TASA_MAXIMA_RAZONABLE = 0.40      # tasas facial > 40% se consideran error de digitación
UMBRAL_PORCENTAJE_TASA = 1.0      # una tasa > 1 se interpreta escrita en porcentaje
UMBRAL_PORCENTAJE_MARGEN = 0.15   # un margen > 0,15 se interpreta escrito en porcentaje

# --------------------------------------------------------------------------
# Liquidez
# --------------------------------------------------------------------------
BANDAS_LIQUIDEZ = [("1-7 días", 1, 7), ("8-15 días", 8, 15),
                   ("16-30 días", 16, 30), ("31-90 días", 31, 90)]

# --------------------------------------------------------------------------
# Calificaciones (escala nacional de largo plazo, de mejor a peor)
# --------------------------------------------------------------------------
ESCALA = ["NACION", "AAA", "AA+", "AA", "AA-", "A+", "A", "A-",
          "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B", "B-", "CCC", "D"]
EQUIVALENCIA_CORTO_PLAZO = {
    "F1+": "AAA", "BRC1+": "AAA", "VRR1+": "AAA",
    "F1": "AA+", "BRC1": "AA+", "VRR1": "AA+",
    "F2": "A", "BRC2": "A", "VRR2": "A",
    "F3": "BBB", "BRC3": "BBB", "VRR3": "BBB",
}
SINONIMOS_NACION = {"NACION", "GOBIERNO", "SOBERANO", "MHCP", "GOBIERNONACIONAL", "NAC"}
# Calificación -> (factor de spread, ajuste en pb sobre ese factor)
SPREAD_POR_CALIFICACION = {
    "AAA": ("SPR_AAA", 0.0), "AA+": ("SPR_AA", -45.0), "AA": ("SPR_AA", 0.0),
    "AA-": ("SPR_AA", 40.0), "A+": ("SPR_AA", 130.0), "A": ("SPR_AA", 180.0),
    "A-": ("SPR_AA", 240.0), "BBB+": ("SPR_AA", 330.0), "BBB": ("SPR_AA", 400.0),
    "BBB-": ("SPR_AA", 480.0),
}
SPREAD_INFERIOR = ("SPR_AA", 650.0)       # por debajo de BBB-
CALIFICACION_DEFECTO = "A+"               # conservadora, si no hay dato en ninguna parte

# --------------------------------------------------------------------------
# Instrumentos soportados y sus alias en los Excel de los clientes
# --------------------------------------------------------------------------
TIPOS = {
    "TES_TF": ["tes", "tes tf", "tes tasa fija", "tfit", "tes_tf", "tes pesos",
               "tes pesos tasa fija", "titulos de tesoreria"],
    "CDT_TF": ["cdt", "cdt tf", "cdt tasa fija", "cdt_tf", "cdt fijo"],
    "CDT_IBR": ["cdt ibr", "cdt_ibr", "cdt indexado ibr", "cdt variable ibr", "cdt tasa variable"],
    "BONO_TF": ["bono", "bono tf", "bono tasa fija", "bono_tf", "bono ordinario",
                "bonos ordinarios", "bono corporativo"],
    "RENTA_VARIABLE": ["accion", "acciones", "etf", "renta variable", "renta_variable",
                       "fondo bursatil"],
    "DIVISA": ["usd", "divisa", "divisas", "dolares", "deposito usd",
               "cuenta de compensacion", "cuenta compensacion usd", "deposito en usd"],
    "LIQUIDEZ": ["cuenta ahorros", "cuenta de ahorros", "ahorros", "cuenta corriente",
                 "fic", "fic vista", "fondo de inversion colectiva", "liquidez",
                 "disponible", "caja", "fondo vista"],
}
NOMBRE_TIPO = {
    "TES_TF": "TES tasa fija", "CDT_TF": "CDT tasa fija", "CDT_IBR": "CDT IBR",
    "BONO_TF": "Bonos tasa fija", "RENTA_VARIABLE": "Renta variable",
    "DIVISA": "Divisas (USD)", "LIQUIDEZ": "Disponible y FIC",
}
RENTA_FIJA = {"TES_TF", "CDT_TF", "CDT_IBR", "BONO_TF"}
FRECUENCIAS = {
    "AV": 1, "ANUAL": 1, "SV": 2, "SEMESTRAL": 2, "TV": 4, "TRIMESTRAL": 4,
    "BV": 6, "BIMESTRAL": 6, "MV": 12, "MENSUAL": 12,
    "PV": 0, "ALVENCIMIENTO": 0, "VENCIMIENTO": 0, "PERIODOVENCIDO": 0,
}
FRECUENCIA_DEFECTO = {"TES_TF": 1, "CDT_TF": 4, "CDT_IBR": 4, "BONO_TF": 4}

# Columnas de la hoja de inversiones -> alias aceptados (se comparan normalizados)
COLUMNAS_INVERSIONES = {
    "id": ["id", "no", "no.", "numero", "consecutivo", "id titulo", "codigo", "isin"],
    "especie": ["especie", "nemotecnico", "especie nemotecnico", "especie / nemotecnico",
                "descripcion", "titulo"],
    "tipo": ["tipo", "tipo de instrumento", "tipo instrumento", "instrumento", "clase"],
    "emisor": ["emisor", "entidad emisora", "contraparte", "emisor / contraparte"],
    "calificacion": ["calificacion", "rating", "calif", "calificacion riesgo"],
    "portafolio": ["portafolio", "libro", "fondo"],
    "clasificacion": ["clasificacion contable", "clasificacion", "categoria contable"],
    "moneda": ["moneda"],
    "valor_nominal": ["valor nominal", "nominal", "vn", "monto nominal", "saldo",
                      "unidades", "cantidad"],
    "tasa_facial": ["tasa facial", "tasa", "cupon", "tasa cupon", "tasa efectiva"],
    "margen": ["margen", "margen ibr", "spread", "puntos adicionales"],
    "base_tasa": ["modalidad", "base tasa", "modalidad tasa", "modalidad de tasa"],
    "frecuencia": ["periodicidad", "frecuencia", "frecuencia de pago", "pagos al ano"],
    "fecha_emision": ["fecha emision", "fecha de emision", "emision", "fecha compra"],
    "fecha_vencimiento": ["fecha vencimiento", "fecha de vencimiento", "vencimiento",
                          "f vcto", "fecha vcto"],
    "valor_mercado": ["valor de mercado", "valor mercado", "valor presente", "vpn",
                      "valor razonable", "valor de mercado cop"],
    "beta": ["beta"],
    "restringido": ["restringido", "garantia", "en garantia", "gravado"],
}
COLUMNAS_FLUJOS = {
    "fecha": ["fecha", "fecha flujo", "fecha de pago"],
    "concepto": ["concepto", "descripcion", "detalle"],
    "sentido": ["sentido", "tipo", "entrada/salida", "entrada salida", "tipo de flujo"],
    "monto": ["monto", "monto cop", "monto (cop)", "valor", "valor cop"],
}
COLUMNAS_DEPOSITOS = {
    "producto": ["producto", "concepto", "tipo de deposito"],
    "saldo": ["saldo", "saldo cop", "saldo (cop)", "valor"],
}

# Hojas esperadas en el Excel mensual (se aceptan alias)
HOJAS = {
    "inversiones": ["inversiones", "portafolio", "posiciones"],
    "flujos": ["flujos_liquidez", "flujos liquidez", "flujos"],
    "depositos": ["depositos_vista", "depositos vista", "depositos"],
    "generales": ["datos_generales", "datos generales", "generales"],
}
