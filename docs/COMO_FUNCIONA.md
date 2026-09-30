# Cómo funciona el motor, archivo por archivo

Guía de estudio del código. Para cada módulo: qué problema resuelve, cómo lo
resuelve, las fórmulas que usa y qué mirar al leer el código. Orden recomendado
de lectura: el mismo en que corre un corte.

```
generar_reporte.py
   └─ proceso.procesar_corte()
        1. lectura.leer_posiciones()        Excel -> tabla limpia + bitácora de hallazgos
        2. valoracion.Portafolio            tabla -> flujos de caja -> valor y sensibilidades
        3. riesgo_mercado                   VaR, ES, backtesting, estrés
        4. concentracion / liquidez         emisores, HHI, IRL
        5. limites / narrativa / acciones   semáforo, mensajes y plan de acción
   └─ graficas, informe_pdf, anexo_excel    salidas
```

---

## 0. `config.py`: las decisiones técnicas en un solo lugar

- **Rutas relativas a la carpeta del proyecto** (`RAIZ = Path(__file__).resolve().parent.parent`):
  el motor funciona sin importar desde dónde se ejecute.
- **Factores de riesgo:** 8 nodos de la curva cero cupón TES (3M a 15A), 2 spreads
  (AAA y AA), TRM e índice accionario. Todo el riesgo del portafolio se expresa
  como sensibilidad a estos 12 números.
- **Metodología:** VaR 99%, ES 97,5%, 500 días de simulación histórica, 250 de
  backtesting, lambda EWMA 0,94.
- **Alias de columnas (`COLUMNAS_INVERSIONES`):** aquí se "enseña" al motor el
  Excel de cada cliente. Ejemplo: si el cliente llama "F. Vcto" a la fecha de
  vencimiento, basta agregar `"f vcto"` a la lista.
- **Calificaciones:** escala de mejor a peor (`ESCALA`) y equivalencias de corto
  plazo (F1+ = AAA). El índice en la lista permite decidir cuál es "más
  conservadora".

Regla de diseño: lo técnico vive en `config.py`; lo que aprueba la entidad
(límites, emisores, haircuts, escenarios) vive en `politica_riesgo.xlsx`.

## 1. `lectura.py`: del Excel desordenado a una tabla confiable

Es donde está buena parte del valor comercial: los Excel reales vienen sucios.

**`extraer_tabla()`: encontrar los encabezados.** Recorre las primeras 25 filas,
normaliza cada celda (minúsculas, sin tildes, sin puntuación) y cuenta cuántas
coinciden con algún alias. La fila con más coincidencias es el encabezado. Así
funciona aunque el cliente tenga tres filas de títulos arriba. Guarda
`fila_excel` para que cada hallazgo apunte a la fila exacta.

**`a_numero()`: números en formato colombiano.** `"1.500.000.000"` y `"12,5%"`
se convierten bien. Regla clave: si hay punto y coma, el último separador es el
decimal; si solo hay puntos y el último grupo tiene 3 dígitos, en un monto son miles.

**`a_fecha()`:** acepta fechas reales de Excel, números de serie, `15/12/2027`,
`2027-12-15` y `15-dic-2027`.

**Convención de tasas:** si la mediana de la columna es mayor que 1, toda la
columna viene en porcentaje; si solo una fila supera 1, esa fila se escribió en
porcentaje por error (advertencia).

**`clave_emisor()` y `MaestroEmisores`: el hallazgo estrella.**
`"Bco. Cordillera S.A."` -> mayúsculas, sin puntuación -> `BCO CORDILLERA S A`
-> expande abreviaturas (`BCO` -> `BANCO`) -> quita sufijos societarios -> `BANCO
CORDILLERA`. Si la clave está en el maestro (o en sus alias) se unifica; si no,
se busca por similitud (`difflib`, umbral 0,85) y se advierte.

**`validar_inversiones()`:** en orden: ignora filas de totales, elimina
duplicados exactos, detecta la convención de tasas y luego valida fila por fila:
tipo soportado, emisor, calificación (si la del archivo y la del maestro no
coinciden, gana la más conservadora), montos, fechas, título vencido, y reglas
por instrumento (un CDT IBR necesita margen; un título que paga al vencimiento
necesita fecha de emisión).

Severidades: **ERROR** excluye la fila; **ADVERTENCIA** corrige y avisa;
**INFO** es una conversión de formato.

## 2. `mercado.py`: factores y escenarios

**Unidades (clave para leer todo el motor):** tasas en % con cambios en puntos
básicos; spreads en pb; TRM e índice con cambios en retorno logarítmico.

- `cambios()`: niveles diarios -> cambios diarios en esas unidades.
- `aplicar()`: niveles de hoy + cambios -> niveles de escenario. Es la operación
  central de la simulación histórica: *"¿qué valdría mi portafolio de hoy si
  mañana el mercado se moviera como se movió el 31 de marzo de 2026?"*.
- `covarianzas_ewma()`: `S_t = 0,94·S_{t-1} + 0,06·x_t·x_t'`. Es un IGARCH sin
  constante: la misma idea de persistencia total que apareció en el GARCH de la TRM.

## 3. `valoracion.py`: todo es un flujo de caja

**Idea central:** cada título se descompone en flujos `(plazo t, monto)` y

```
VP = suma( monto_i / (1 + y(t_i) + s)^t_i )
```

`y(t)` es la curva TES interpolada linealmente al plazo del flujo; `s` es el
spread de la calificación del emisor (`SPREAD_POR_CALIFICACION`). TES: `s = 0`.

**Calendario (`fechas_cupon`):** se construye hacia atrás desde el vencimiento
cada 12/f meses. Tasa por periodo: `(1+r)^(1/f) - 1` si es EA, `r/f` si es nominal.

**CDT IBR (flotante):** el próximo cupón ya está fijado con el IBR del último
reprecio. Después de esa fecha el título vale su nominal más el valor presente
de la diferencia entre el margen pactado `m` y el spread de mercado `s`:

```
VP = (N + c1)·FD(t1) + suma_k N·(m - s)/f · FD(t_k)
```

Por eso su duración frente a tasas es casi cero (solo hasta el reprecio) pero su
duración frente al spread es larga. En el código: `cf_coef = -N/f` multiplica el
spread del escenario.

**Vectorización (`valorar`):** recibe una matriz de escenarios (S x 12) y
devuelve el valor de cada posición en cada escenario (S x P) con álgebra de
matrices: `W` interpola la curva a cada flujo, `Sel` elige el factor de spread
de cada flujo e `Inc` suma los flujos de cada posición. Valorar 500 escenarios
cuesta lo mismo que valorar uno.

**Sensibilidades:** diferencias finitas centrales (golpe de +1 pb y -1 pb en cada
factor). `DV01 = -(suma de sensibilidades a los nodos)`; `duración modificada =
DV01 x 10.000 / valor`.

## 4. `riesgo_mercado.py`: cuánto se puede perder

**VaR histórico (medida principal):** los 500 cambios diarios reales se aplican
al portafolio de hoy, se revalúa todo y se toma el percentil 1% de las pérdidas
y ganancias. Con 500 escenarios, el VaR queda entre la 5.ª y la 6.ª peor pérdida.
**ES 97,5%:** promedio de las pérdidas del peor 2,5%.

**Contribuciones al ES:** promedio de la pérdida de cada posición en los
escenarios de la cola; suman exactamente el ES total.

**VaR por factor:** se repite la simulación moviendo solo un grupo de factores.
La suma de los VaR individuales menos el total es el beneficio de diversificación.

**VaR paramétrico:** `VaR = 2,326 · raíz(s'·Σ·s)`, con `s` las sensibilidades y
`Σ` la covarianza EWMA. Descomposición de Euler: `contribución_p = z·s_p'Σs / σ`.

**Backtesting (`backtesting`):** para cada uno de los últimos 250 días calcula el
VaR usando SOLO la información del día anterior y lo compara con la pérdida
hipotética real del portafolio de hoy mantenido fijo.
- **Kupiec:** `LR = -2·ln[(1-p)^(N-x)·p^x] + 2·ln[(1-x/N)^(N-x)·(x/N)^x]`, con
  distribución chi-cuadrado de 1 grado de libertad.
- **Christoffersen:** prueba si una excepción aumenta la probabilidad de otra al día siguiente.
- **Zonas de Basilea:** verde si P(X <= x) < 95%, amarilla si < 99,99%.

**Estrés:** hipotéticos (choques instantáneos definidos en la política) e
históricos (la peor ventana de 20 días de un periodo de crisis, aplicada al
portafolio de hoy).

## 5. `concentracion.py` y `liquidez.py`

- Exposición por emisor = títulos + depósitos a la vista con esa contraparte.
- **HHI** = suma de (participación)² x 10.000 sobre emisores privados;
  `10.000/HHI` = número equivalente de emisores del mismo tamaño.
- `emisor_max_pct_manual`: lo que habría mostrado un control por nombre escrito
  (sin distinguir mayúsculas, como Excel). Alimenta el mensaje "el control manual lo mostraba en 10,2%".
- **IRL:** ALAC = suma de valor x (1 - haircut) de activos no restringidos. Por
  banda: RLN = salidas contractuales + retiros estimados (saldo a la vista x
  factor) - entradas (con tope del 75% de las salidas). IRL = ALAC / RLN acumulado.

## 6. `limites.py`, `narrativa.py` y `acciones.py`

- `calcular_indicadores()` reúne todo en un diccionario con las unidades de la política.
- `evaluar_limites()`: máximo -> rojo si valor > límite, ámbar si valor > alerta;
  mínimo -> al revés.
- `narrativa.py`: reglas que redactan frases. El color de cada mensaje sale del
  semáforo del límite relacionado.
- `acciones.py`: cuánto mover. Concentración: `X = E - L·T` (exposición menos
  límite por total). Liquidez: `ΔALAC = L·RLN - ALAC`. Tasas: `ΔDV01 = DV01·(1 - D_objetivo/D)`,
  llevado a pesos del TES de mayor duración.

## 7. Salidas

- `graficas.py`: una serie = un color; texto siempre en tinta; rojo y ámbar solo
  cuando significan estado; líneas punteadas solo para umbrales.
- `informe_pdf.py`: ReportLab. Cada sección es una función que devuelve una lista
  de elementos (`historia`); `tabla()` aplica el estilo común.
- `anexo_excel.py`: openpyxl. La simulación se escribe como valores; la
  aritmética como fórmulas vivas para que auditoría pueda rastrearla.
- `proceso.py`: orquesta un corte y guarda el historial (una fila por corte en
  `historial_indicadores.csv`), de donde salen la evolución y "frente al corte anterior".

## Ejercicios para dominarlo

1. Valora a mano en Excel el TES 7,75% sep-2030 con la curva de `factores_mercado.csv`
   al corte y compáralo con el anexo (debe cuadrar al peso).
2. En la hoja Backtesting del anexo, ordena el P&G y ubica el VaR entre la 5.ª y
   6.ª peor pérdida de la ventana.
3. Escribe "BANCO  CORDILLERA S.A.S." en el Excel y predice qué hará `clave_emisor`.
4. Baja el límite por emisor a 10% en la política y predice qué acciones aparecerán.
5. Agrega un CDT de COP 5.000 M de Banco Altiplano y predice el nuevo semáforo.
