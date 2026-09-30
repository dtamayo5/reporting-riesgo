"""Lectura y validación de los Excel de entrada.

Aquí está buena parte del valor del servicio: los Excel reales llegan con
encabezados en cualquier fila, nombres de columnas distintos, fechas escritas
como texto, tasas en porcentaje o en decimal, el mismo emisor escrito de tres
maneras, filas de totales y duplicados. Este módulo lo normaliza todo y deja
una bitácora de cada corrección con la hoja y la fila de origen.

Severidades:
  ERROR        la fila se excluye del cálculo (debe corregirse en el origen)
  ADVERTENCIA  se corrigió automáticamente (verificar)
  INFO         conversión de formato sin impacto
"""
from __future__ import annotations

import difflib
import re
from datetime import date, datetime

import numpy as np
import pandas as pd

from . import config as C
from .utilidades import Hallazgos, normalizar, num, pct, sin_tildes


class ErrorEntrada(Exception):
    pass


def _vacio(x) -> bool:
    if x is None:
        return True
    if isinstance(x, float) and np.isnan(x):
        return True
    if isinstance(x, str) and x.strip() in {"", "-", "—", "nan", "NaN", "None"}:
        return True
    return x is pd.NaT


# ------------------------------------------------------ conversión de celdas
def a_numero(x, contexto: str = "monto"):
    """Convierte una celda a número. Devuelve (valor, venía_como_texto).

    Entiende formato colombiano ('1.500.000.000', '12,5%') y anglosajón
    ('1,500,000,000', '12.5'). En montos, un grupo final de tres dígitos
    ('2.000') se interpreta como miles; en tasas, como decimales."""
    if _vacio(x):
        return np.nan, False
    if isinstance(x, (bool, np.bool_)):
        return np.nan, True
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x), False
    s = str(x).strip().replace("$", "").replace("COP", "").replace(" ", "").replace(" ", "")
    es_pct = s.endswith("%")
    s = s.rstrip("%")
    if s in {"", "-", "—"}:
        return np.nan, True
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        partes = s.split(",")
        miles = len(partes) > 2 or (contexto == "monto" and len(partes[-1]) == 3)
        s = s.replace(",", "") if miles else s.replace(",", ".")
    elif "." in s:
        partes = s.split(".")
        if len(partes) > 2 or (contexto == "monto" and len(partes[-1]) == 3):
            s = s.replace(".", "")
    try:
        v = float(s)
    except ValueError:
        return np.nan, True
    return (v / 100 if es_pct else v), True


_MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7,
          "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
          "jan": 1, "apr": 4, "aug": 8, "dec": 12}


def a_fecha(x):
    """Convierte una celda a fecha. Devuelve (fecha, venía_como_texto)."""
    if _vacio(x):
        return pd.NaT, False
    if isinstance(x, (datetime, date, pd.Timestamp)):
        return pd.Timestamp(x).normalize(), False
    if isinstance(x, (int, float, np.integer, np.floating)):
        if 20000 < float(x) < 80000:      # número de serie de Excel
            return pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(x)), True
        return pd.NaT, True
    s = sin_tildes(str(x)).strip().lower().split(" ")[0] if re.match(r"^\d{4}-", str(x)) \
        else sin_tildes(str(x)).strip().lower()
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%y"):
        try:
            return pd.Timestamp(datetime.strptime(s, formato)), True
        except ValueError:
            pass
    m = re.match(r"^(\d{1,2})[\s\-/.]*(?:de\s+)?([a-z]{3})[a-z]*[\s\-/.]*(?:de\s+)?(\d{2,4})$", s)
    if m and m.group(2) in _MESES:
        anio = int(m.group(3))
        anio = anio + 2000 if anio < 100 else anio
        try:
            return pd.Timestamp(anio, _MESES[m.group(2)], int(m.group(1))), True
        except ValueError:
            return pd.NaT, True
    return pd.NaT, True


def a_bool(x):
    if _vacio(x):
        return False, True
    s = normalizar(x)
    if s in {"si", "s", "x", "1", "true", "verdadero", "yes", "y", "restringido"}:
        return True, True
    if s in {"no", "n", "0", "false", "falso"}:
        return False, True
    return False, False


def normalizar_tipo(x):
    """Devuelve (código de tipo, motivo si no se reconoce)."""
    if _vacio(x):
        return None, "tipo de instrumento vacío"
    s = normalizar(x)
    for codigo, alias in C.TIPOS.items():
        if s in {normalizar(a) for a in alias}:
            return codigo, ""
    if "uvr" in s:
        return None, "TES/bonos en UVR: el módulo UVR no está incluido en esta versión"
    if "ibr" in s and "cdt" in s:
        return "CDT_IBR", ""
    if "cdt" in s:
        return "CDT_TF", ""
    if "tes" in s.split():
        return "TES_TF", ""
    if "bono" in s and not any(k in s for k in ("ibr", "ipc", "uvr")):
        return "BONO_TF", ""
    if any(k in s for k in ("accion", "etf")):
        return "RENTA_VARIABLE", ""
    if any(k in s for k in ("usd", "dolar", "divisa")):
        return "DIVISA", ""
    if any(k in s for k in ("ahorro", "corriente", "fic", "caja", "disponible")):
        return "LIQUIDEZ", ""
    return None, f"tipo de instrumento no soportado: '{x}'"


def normalizar_frecuencia(x):
    if _vacio(x):
        return None
    if isinstance(x, (int, float, np.integer, np.floating)):
        v = int(round(float(x)))
        return v if v in {0, 1, 2, 3, 4, 6, 12} else None
    s = normalizar(x).upper().replace(" ", "")
    return C.FRECUENCIAS.get(s)


def normalizar_base_tasa(x) -> str:
    if _vacio(x):
        return "EA"
    s = normalizar(x).replace(" ", "")
    if s.startswith("n") or s in {"na", "natv", "nasv", "namv", "naav"}:
        return "NOMINAL"
    return "EA"


def normalizar_calificacion(x):
    """Devuelve el código de calificación ('AAA', 'BRC1+', 'NACION'...),
    None si está vacía o '?' si no se reconoce."""
    if _vacio(x):
        return None
    s = sin_tildes(str(x)).upper()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"[^A-Z0-9+\-]", "", s)
    if s in {"", "NA", "NAN", "NONE", "SC"}:
        return None
    if s in C.SINONIMOS_NACION:
        return "NACION"
    if s in C.ESCALA or s in C.EQUIVALENCIA_CORTO_PLAZO:
        return s
    return "?"


def calificacion_lp(codigo):
    if codigo is None or codigo == "?":
        return None
    return C.EQUIVALENCIA_CORTO_PLAZO.get(codigo, codigo)


def mas_conservadora(a: str, b: str) -> str:
    return a if C.ESCALA.index(calificacion_lp(a)) >= C.ESCALA.index(calificacion_lp(b)) else b


# ------------------------------------------------------------ emisores ----
_ABREVIATURAS = {"BCO": "BANCO", "CIA": "COMPANIA", "CORP": "CORPORACION",
                 "FIN": "FINANCIERA", "FDO": "FONDO", "COOP": "COOPERATIVA",
                 "FIDU": "FIDUCIARIA", "FIDUC": "FIDUCIARIA"}
_SUFIJOS = {"S", "A", "SA", "SAS", "ESP", "E", "P", "LTDA", "BIC", "SCA"}


def clave_emisor(nombre) -> str:
    """'Bco. Cordillera S.A.' -> 'BANCO CORDILLERA' (mayúsculas, sin tildes,
    sin puntuación, abreviaturas expandidas y sin sufijos societarios)."""
    tokens = [_ABREVIATURAS.get(t, t) for t in normalizar(nombre).upper().split()]
    while tokens and tokens[-1] in _SUFIJOS:
        tokens.pop()
    return " ".join(tokens)


class MaestroEmisores:
    def __init__(self, tabla: pd.DataFrame):
        self.tabla = tabla.set_index("emisor")
        self.indice = {}
        for emisor, fila in self.tabla.iterrows():
            self.indice[clave_emisor(emisor)] = emisor
            for alias in str(fila.get("alias", "") or "").split(";"):
                if alias.strip():
                    self.indice[clave_emisor(alias)] = emisor

    def resolver(self, nombre):
        """Devuelve (emisor oficial o None, método: exacto | similitud | desconocido)."""
        clave = clave_emisor(nombre)
        if clave in self.indice:
            return self.indice[clave], "exacto"
        parecido = difflib.get_close_matches(clave, list(self.indice), n=1, cutoff=0.85)
        if parecido:
            return self.indice[parecido[0]], "similitud"
        return None, "desconocido"

    def dato(self, emisor, campo, defecto=None):
        if emisor in self.tabla.index:
            v = self.tabla.loc[emisor, campo]
            return defecto if _vacio(v) else v
        return defecto


# ------------------------------------------------------- lectura de hojas
def abrir_libro(ruta) -> dict:
    try:
        return pd.read_excel(ruta, sheet_name=None, header=None, dtype=object)
    except PermissionError as e:
        raise ErrorEntrada(f"No se pudo abrir {ruta.name}: ciérrelo en Excel y vuelva a intentar.") from e
    except Exception as e:  # noqa: BLE001
        raise ErrorEntrada(f"No se pudo leer {ruta.name}: {e}") from e


def buscar_hoja(libro: dict, alias: list):
    objetivo = {normalizar(a) for a in alias}
    for nombre, df in libro.items():
        if normalizar(nombre) in objetivo:
            return nombre, df
    return None, None


def extraer_tabla(crudo: pd.DataFrame, mapa: dict, hoja: str, hallazgos: Hallazgos,
                  minimo: int = 2) -> pd.DataFrame:
    """Encuentra la fila de encabezados (en cualquiera de las primeras 25 filas),
    traduce los nombres de columna con el mapa de alias y devuelve la tabla con
    columnas canónicas más 'fila_excel' (número de fila real en Excel)."""
    alias_norm = {c: {normalizar(a) for a in lista} for c, lista in mapa.items()}
    mejor_fila, mejor_n = None, 0
    for i in range(min(25, len(crudo))):
        celdas = {normalizar(v) for v in crudo.iloc[i].tolist() if not _vacio(v)}
        n = sum(1 for c in alias_norm.values() if c & celdas)
        if n > mejor_n:
            mejor_fila, mejor_n = i, n
    if mejor_fila is None or mejor_n < minimo:
        raise ErrorEntrada(f"No se encontraron los encabezados esperados en la hoja '{hoja}'.")

    columnas = {}
    for j, v in enumerate(crudo.iloc[mejor_fila].tolist()):
        texto = normalizar(v)
        for canon, alias in alias_norm.items():
            if texto in alias and canon not in columnas:
                columnas[canon] = j
                break
    datos = crudo.iloc[mejor_fila + 1:, list(columnas.values())].copy()
    datos.columns = list(columnas.keys())
    for canon in mapa:
        if canon not in datos.columns:
            datos[canon] = np.nan
    datos["fila_excel"] = datos.index + 1
    vacias = datos.drop(columns="fila_excel").apply(lambda col: col.map(_vacio)).all(axis=1)
    return datos.loc[~vacias].reset_index(drop=True)


# ----------------------------------------------------------- la política
def leer_politica(ruta) -> dict:
    if not ruta.exists():
        raise ErrorEntrada(f"No existe el archivo de política {ruta}.")
    libro = abrir_libro(ruta)
    h = Hallazgos()

    def tabla(alias, mapa):
        nombre, crudo = buscar_hoja(libro, alias)
        if crudo is None:
            raise ErrorEntrada(f"Al archivo de política le falta la hoja '{alias[0]}'.")
        return extraer_tabla(crudo, mapa, nombre, h)

    ent = tabla(["Entidad"], {"parametro": ["parametro"], "valor": ["valor"]})
    entidad = {normalizar(r["parametro"]): r["valor"] for _, r in ent.iterrows()}

    lim = tabla(["Limites"], {
        "codigo": ["codigo"], "indicador": ["indicador"], "categoria": ["categoria"],
        "tipo": ["tipo de limite", "tipo"], "limite": ["limite"], "alerta": ["alerta", "umbral de alerta"],
        "unidad": ["unidad"]})
    for c in ["limite", "alerta"]:
        lim[c] = [a_numero(v, "tasa")[0] for v in lim[c]]
    lim["tipo"] = ["MIN" if normalizar(t).startswith("min") else "MAX" for t in lim["tipo"]]

    emi = tabla(["Emisores"], {
        "emisor": ["emisor oficial", "emisor"], "alias": ["alias", "otros nombres"],
        "sector": ["sector"], "calificacion": ["calificacion"],
        "exento": ["exento de limite", "exento"]})
    emi["exento"] = [a_bool(v)[0] for v in emi["exento"]]
    emi["calificacion"] = [normalizar_calificacion(v) for v in emi["calificacion"]]

    hc = tabla(["Haircuts"], {"categoria": ["categoria"], "descripcion": ["descripcion"],
                              "haircut": ["haircut", "descuento"]})
    haircuts = {r["categoria"]: a_numero(r["haircut"], "tasa")[0] for _, r in hc.iterrows()}

    liq = tabla(["Liquidez"], {"parametro": ["parametro", "banda"], "valor": ["valor", "factor"]})
    parametros_liq = {normalizar(r["parametro"]): a_numero(r["valor"], "tasa")[0]
                      for _, r in liq.iterrows()}

    esc = tabla(["Escenarios_estres", "Escenarios"], {
        "codigo": ["codigo"], "nombre": ["nombre", "escenario"], "tipo": ["tipo"],
        "paralelo_bp": ["paralelo pb", "paralelo"], "corto_bp": ["corto pb", "tramo corto pb"],
        "largo_bp": ["largo pb", "tramo largo pb"], "spr_aaa_bp": ["spread aaa pb"],
        "spr_aa_bp": ["spread aa pb"], "trm_pct": ["trm", "trm %"], "rv_pct": ["renta variable", "renta variable %"],
        "desde": ["desde"], "hasta": ["hasta"], "descripcion": ["descripcion"]})
    for c in ["paralelo_bp", "corto_bp", "largo_bp", "spr_aaa_bp", "spr_aa_bp", "trm_pct", "rv_pct"]:
        esc[c] = [0.0 if _vacio(v) else a_numero(v, "tasa")[0] for v in esc[c]]
    esc["historico"] = [normalizar(t).startswith("hist") for t in esc["tipo"]]
    esc["desde"] = [a_fecha(v)[0] for v in esc["desde"]]
    esc["hasta"] = [a_fecha(v)[0] for v in esc["hasta"]]

    return {
        "nombre": str(entidad.get("nombre de la entidad", "Entidad")),
        "tipo_entidad": str(entidad.get("tipo de entidad", "")),
        "organo": str(entidad.get("organo que aprueba", "")),
        "fecha_politica": entidad.get("fecha de aprobacion de la politica", ""),
        "nota_pie": "" if _vacio(entidad.get("nota de pie de pagina")) else str(entidad["nota de pie de pagina"]),
        "demo": a_bool(entidad.get("modo demostracion"))[0],
        "limites": lim, "maestro": MaestroEmisores(emi), "emisores": emi,
        "haircuts": haircuts, "liquidez": parametros_liq, "escenarios": esc,
    }


# ------------------------------------------------ el archivo de posiciones
def leer_posiciones(ruta, corte: pd.Timestamp, politica: dict, h: Hallazgos) -> dict:
    libro = abrir_libro(ruta)

    # Datos generales (fecha de corte y patrimonio técnico)
    nombre, crudo = buscar_hoja(libro, C.HOJAS["generales"])
    if crudo is None:
        raise ErrorEntrada("Falta la hoja 'Datos_generales' con el patrimonio técnico.")
    pt = np.nan
    for i in range(len(crudo)):
        fila = crudo.iloc[i].tolist()
        etiqueta = normalizar(fila[0]) if fila else ""
        if "patrimonio tecnico" in etiqueta and len(fila) > 1:
            pt = a_numero(fila[1], "monto")[0]
        if "fecha de corte" in etiqueta and len(fila) > 1:
            f = a_fecha(fila[1])[0]
            if pd.notna(f) and f != corte:
                h.agregar("ADVERTENCIA", nombre, i + 1, "fecha de corte", fila[1],
                          f"La fecha del archivo ({f.date()}) no coincide con el nombre del archivo "
                          f"({corte.date()}).", "Se usa la fecha del nombre del archivo.")
    if not pt or np.isnan(pt) or pt <= 0:
        raise ErrorEntrada("No se encontró un patrimonio técnico válido en 'Datos_generales'.")

    nombre, crudo = buscar_hoja(libro, C.HOJAS["inversiones"])
    if crudo is None:
        raise ErrorEntrada("Falta la hoja 'Inversiones'.")
    inversiones = validar_inversiones(extraer_tabla(crudo, C.COLUMNAS_INVERSIONES, nombre, h, 4),
                                      nombre, corte, politica, h)

    flujos = _leer_flujos(libro, corte, h)
    nombre, crudo = buscar_hoja(libro, C.HOJAS["depositos"])
    depositos = pd.DataFrame(columns=["producto", "saldo"])
    if crudo is not None:
        d = extraer_tabla(crudo, C.COLUMNAS_DEPOSITOS, nombre, h)
        d["saldo"] = [a_numero(v)[0] for v in d["saldo"]]
        depositos = d.dropna(subset=["saldo"])[["producto", "saldo"]]
    else:
        h.agregar("ADVERTENCIA", "-", None, "Depositos_vista", "", "No existe la hoja de depósitos "
                  "a la vista: el IRL no incluirá retiros no contractuales.", "")
    return {"inversiones": inversiones, "flujos": flujos, "depositos": depositos,
            "patrimonio_tecnico": pt}


def _leer_flujos(libro, corte, h) -> pd.DataFrame:
    nombre, crudo = buscar_hoja(libro, C.HOJAS["flujos"])
    vacio = pd.DataFrame(columns=["fecha", "concepto", "sentido", "monto", "dias"])
    if crudo is None:
        h.agregar("ADVERTENCIA", "-", None, "Flujos_liquidez", "",
                  "No existe la hoja de flujos: el IRL solo tendrá retiros no contractuales.", "")
        return vacio
    t = extraer_tabla(crudo, C.COLUMNAS_FLUJOS, nombre, h)
    filas = []
    for _, r in t.iterrows():
        fecha, _ = a_fecha(r["fecha"])
        monto, _ = a_numero(r["monto"])
        s = normalizar(r["sentido"])
        sentido = "ENTRADA" if s.startswith(("e", "ing")) else "SALIDA" if s.startswith(("s", "egr")) else None
        if sentido is None and not np.isnan(monto):
            sentido = "SALIDA" if monto < 0 else None
        if pd.isna(fecha) or np.isnan(monto) or sentido is None:
            h.agregar("ERROR", nombre, r["fila_excel"], "fecha/monto/sentido",
                      f"{r['fecha']} | {r['monto']} | {r['sentido']}",
                      "Flujo incompleto o ilegible.", "Fila excluida del IRL.")
            continue
        dias = (fecha - corte).days
        if dias <= 0:
            h.agregar("ADVERTENCIA", nombre, r["fila_excel"], "fecha", str(fecha.date()),
                      "Flujo con fecha igual o anterior al corte.", "Fila excluida del IRL.")
            continue
        filas.append({"fecha": fecha, "concepto": r["concepto"], "sentido": sentido,
                      "monto": abs(monto), "dias": dias})
    return pd.DataFrame(filas, columns=vacio.columns) if filas else vacio


def validar_inversiones(t: pd.DataFrame, hoja: str, corte: pd.Timestamp,
                        politica: dict, h: Hallazgos) -> pd.DataFrame:
    maestro: MaestroEmisores = politica["maestro"]
    campos = [c for c in C.COLUMNAS_INVERSIONES]

    # 1) Filas de totales y duplicados exactos
    firmas, conservar = {}, []
    for i, r in t.iterrows():
        texto = " ".join(normalizar(r[c]) for c in ("id", "especie", "tipo"))
        if _vacio(r["tipo"]) and "total" in texto:
            h.agregar("INFO", hoja, r["fila_excel"], "fila", "TOTAL",
                      "Fila de totales del Excel manual.", "Ignorada (el motor recalcula los totales).")
            continue
        firma = tuple(str(r[c]) for c in campos)
        if firma in firmas:
            h.agregar("ADVERTENCIA", hoja, r["fila_excel"], "fila completa", r["especie"],
                      f"Duplicado exacto de la fila {firmas[firma]}.", "Fila excluida.")
            continue
        firmas[firma] = r["fila_excel"]
        conservar.append(i)
    t = t.loc[conservar].reset_index(drop=True)

    # 2) Convención de tasas: ¿la columna completa viene en porcentaje?
    tasas = [a_numero(v, "tasa")[0] for v in t["tasa_facial"]]
    margenes = [a_numero(v, "tasa")[0] for v in t["margen"]]
    tasas_col_pct = np.nanmedian(tasas) > C.UMBRAL_PORCENTAJE_TASA if np.isfinite(tasas).any() else False
    margen_col_pct = (np.nanmedian(margenes) > C.UMBRAL_PORCENTAJE_MARGEN
                      if np.isfinite(margenes).any() else False)
    if tasas_col_pct:
        h.agregar("INFO", hoja, None, "tasa facial", "", "La columna de tasas está en porcentaje.",
                  "Convertida a decimal.")
    if margen_col_pct:
        h.agregar("INFO", hoja, None, "margen", "", "La columna de márgenes está en porcentaje.",
                  "Convertida a decimal.")

    salida = []
    for k, r in t.iterrows():
        fila = r["fila_excel"]
        err = lambda campo, valor, det: h.agregar("ERROR", hoja, fila, campo, valor, det, "Fila excluida.")  # noqa: E731

        tipo, motivo = normalizar_tipo(r["tipo"])
        if tipo is None:
            err("tipo", r["tipo"], motivo)
            continue

        # Emisor: unificación contra el maestro
        emisor_original = "" if _vacio(r["emisor"]) else str(r["emisor"]).strip()
        if not emisor_original:
            if tipo == "TES_TF":
                emisor_original = "Nación"
                h.agregar("INFO", hoja, fila, "emisor", "", "TES sin emisor.", "Se asignó la Nación.")
            else:
                err("emisor", "", "Emisor vacío.")
                continue
        emisor, metodo = maestro.resolver(emisor_original)
        if metodo == "similitud":
            h.agregar("ADVERTENCIA", hoja, fila, "emisor", emisor_original,
                      f"Emisor reconocido por similitud con '{emisor}'.", "Verificar y agregar el alias al maestro.")
        elif metodo == "desconocido":
            emisor = emisor_original
            h.agregar("ADVERTENCIA", hoja, fila, "emisor", emisor_original,
                      "Emisor no registrado en el maestro de emisores.",
                      "Se usa tal cual; agréguelo a la hoja Emisores de la política.")
        elif emisor_original != emisor:
            h.agregar("INFO", hoja, fila, "emisor", emisor_original,
                      f"Nombre unificado como '{emisor}'.", "")
        sector = maestro.dato(emisor, "sector", "Sin clasificar")
        exento = bool(maestro.dato(emisor, "exento", False))

        # Calificación: la del archivo contra la del maestro (gana la más conservadora)
        cal_arch = normalizar_calificacion(r["calificacion"])
        cal_maestro = maestro.dato(emisor, "calificacion")
        if cal_arch == "?":
            h.agregar("ADVERTENCIA", hoja, fila, "calificación", r["calificacion"],
                      "Calificación no reconocida.", "Se ignora el dato del archivo.")
            cal_arch = None
        if tipo == "TES_TF":
            calif = "NACION"
        elif cal_arch and cal_maestro and calificacion_lp(cal_arch) != calificacion_lp(cal_maestro):
            calif = mas_conservadora(cal_arch, cal_maestro)
            h.agregar("ADVERTENCIA", hoja, fila, "calificación", cal_arch,
                      f"No coincide con el maestro ({cal_maestro}).",
                      f"Se usa la más conservadora: {calif}.")
        elif cal_arch:
            calif = cal_arch
        elif cal_maestro:
            calif = cal_maestro
            if tipo in C.RENTA_FIJA:
                h.agregar("ADVERTENCIA", hoja, fila, "calificación", "",
                          "Calificación vacía.", f"Se tomó la del maestro: {calif}.")
        elif tipo in C.RENTA_FIJA:
            calif = C.CALIFICACION_DEFECTO
            h.agregar("ADVERTENCIA", hoja, fila, "calificación", "",
                      "Sin calificación en el archivo ni en el maestro.",
                      f"Se asume {calif} (conservadora).")
        else:
            calif = None

        # Montos
        nominal, txt_nom = a_numero(r["valor_nominal"], "monto")
        if txt_nom and not np.isnan(nominal):
            h.agregar("INFO", hoja, fila, "valor nominal", r["valor_nominal"],
                      "Número escrito como texto.", f"Convertido a {num(nominal)}.")
        v_mercado, _ = a_numero(r["valor_mercado"], "monto")

        # Tasas
        tasa, _ = a_numero(r["tasa_facial"], "tasa")
        if not np.isnan(tasa):
            if tasas_col_pct:
                tasa /= 100
            elif tasa > C.UMBRAL_PORCENTAJE_TASA:
                h.agregar("ADVERTENCIA", hoja, fila, "tasa facial", r["tasa_facial"],
                          "Tasa escrita en porcentaje en una columna en decimal.",
                          f"Interpretada como {pct(tasa / 100, 2)}.")
                tasa /= 100
        margen, _ = a_numero(r["margen"], "tasa")
        if not np.isnan(margen):
            if margen_col_pct:
                margen /= 100
            elif margen > C.UMBRAL_PORCENTAJE_MARGEN:
                h.agregar("ADVERTENCIA", hoja, fila, "margen", r["margen"],
                          "Margen escrito en porcentaje.", f"Interpretado como {pct(margen / 100, 2)}.")
                margen /= 100

        # Fechas
        venc, txt_v = a_fecha(r["fecha_vencimiento"])
        emision, txt_e = a_fecha(r["fecha_emision"])
        for campo, f, txt, orig in (("fecha vencimiento", venc, txt_v, r["fecha_vencimiento"]),
                                    ("fecha emisión", emision, txt_e, r["fecha_emision"])):
            if txt and pd.notna(f):
                h.agregar("INFO", hoja, fila, campo, orig, "Fecha escrita como texto.",
                          f"Interpretada como {f.date()}.")
            elif txt and pd.isna(f):
                h.agregar("ADVERTENCIA", hoja, fila, campo, orig, "Fecha ilegible.", "Se ignora el dato.")

        frecuencia = normalizar_frecuencia(r["frecuencia"])
        if tipo in C.RENTA_FIJA and frecuencia is None:
            frecuencia = C.FRECUENCIA_DEFECTO[tipo]
            if tipo != "TES_TF":
                h.agregar("ADVERTENCIA", hoja, fila, "periodicidad", r["frecuencia"],
                          "Periodicidad vacía o no reconocida.",
                          f"Se asume {frecuencia} pagos al año.")

        beta, _ = a_numero(r["beta"], "tasa")
        restringido, reconocido = a_bool(r["restringido"])
        if not reconocido:
            h.agregar("ADVERTENCIA", hoja, fila, "restringido", r["restringido"],
                      "Valor no reconocido (use Sí/No).", "Se asume No.")

        # Reglas de negocio por tipo de instrumento
        if tipo in C.RENTA_FIJA:
            if np.isnan(nominal) or nominal <= 0:
                err("valor nominal", r["valor_nominal"], "Valor nominal vacío, ilegible o no positivo.")
                continue
            if pd.isna(venc):
                err("fecha vencimiento", r["fecha_vencimiento"], "Fecha de vencimiento vacía o ilegible.")
                continue
            if venc <= corte:
                err("fecha vencimiento", str(venc.date()),
                    f"Título vencido: venció antes del corte ({corte.date()}) y sigue en el portafolio.")
                continue
            if tipo == "CDT_IBR":
                if np.isnan(margen):
                    err("margen", r["margen"], "CDT IBR sin margen.")
                    continue
                if frecuencia == 0:
                    frecuencia = 4
            else:
                if np.isnan(tasa):
                    err("tasa facial", r["tasa_facial"], "Tasa facial vacía o ilegible.")
                    continue
                if not 0 <= tasa <= C.TASA_MAXIMA_RAZONABLE:
                    err("tasa facial", r["tasa_facial"], "Tasa facial fuera de rango razonable.")
                    continue
                if frecuencia == 0 and pd.isna(emision):
                    err("fecha emisión", r["fecha_emision"],
                        "Título con pago al vencimiento sin fecha de emisión (no se pueden calcular los intereses).")
                    continue
        elif tipo == "RENTA_VARIABLE":
            if np.isnan(v_mercado) or v_mercado <= 0:
                err("valor de mercado", r["valor_mercado"], "Renta variable sin valor de mercado.")
                continue
            if np.isnan(beta):
                beta = 1.0
        elif tipo == "DIVISA":
            if np.isnan(nominal) or nominal <= 0:
                err("valor nominal", r["valor_nominal"], "Posición en divisas sin monto en USD.")
                continue
        elif tipo == "LIQUIDEZ":
            if (np.isnan(nominal) or nominal <= 0) and (np.isnan(v_mercado) or v_mercado <= 0):
                err("saldo", r["valor_nominal"], "Cuenta de liquidez sin saldo.")
                continue

        ident = r["id"]
        if isinstance(ident, float) and not np.isnan(ident) and ident.is_integer():
            ident = int(ident)
        salida.append({
            "id": "" if _vacio(ident) else str(ident).strip(),
            "especie": "" if _vacio(r["especie"]) else str(r["especie"]).strip(),
            "tipo": tipo, "emisor": emisor, "emisor_original": emisor_original,
            "sector": sector, "exento": exento,
            "calificacion": calif, "calificacion_lp": calificacion_lp(calif) if calif else None,
            "portafolio": "" if _vacio(r["portafolio"]) else str(r["portafolio"]).strip(),
            "clasificacion": "" if _vacio(r["clasificacion"]) else str(r["clasificacion"]).strip(),
            "moneda": "USD" if tipo == "DIVISA" else "COP",
            "valor_nominal": nominal, "tasa_facial": tasa, "margen": margen,
            "base_tasa": normalizar_base_tasa(r["base_tasa"]),
            "frecuencia": frecuencia if frecuencia is not None else 0,
            "fecha_emision": emision, "fecha_vencimiento": venc,
            "valor_mercado": v_mercado, "beta": 1.0 if np.isnan(beta) else beta,
            "restringido": bool(restringido), "fila_excel": fila,
        })

    df = pd.DataFrame(salida)
    if df.empty:
        raise ErrorEntrada("Ninguna fila de inversiones pasó la validación.")
    # 3) ID repetido con contenido distinto
    for ident, grupo in df[df["id"] != ""].groupby("id"):
        if len(grupo) > 1:
            h.agregar("ADVERTENCIA", hoja, int(grupo["fila_excel"].iloc[1]), "id", ident,
                      f"El ID {ident} aparece en las filas {', '.join(map(str, grupo['fila_excel']))} "
                      "con datos distintos.", "Se conservan ambas; verificar.")
    return df
