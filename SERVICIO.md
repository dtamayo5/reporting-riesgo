# Servicio: automatización del reporting de riesgos de tesorería

**En una frase:** tomo el informe de riesgos que su equipo arma a mano cada mes
en Excel y lo convierto en un proceso que se genera solo, con más controles,
menos errores y trazabilidad para auditoría.

---

## Para quién

Entidades con portafolio de inversiones y reporte mensual de riesgos, pero sin
un equipo cuantitativo propio:

- Cooperativas financieras y de ahorro y crédito
- Fondos de empleados y mutuales con portafolio relevante
- Fiduciarias y administradores de fondos de inversión colectiva pequeños
- Fintechs y compañías de financiamiento con tesorería
- Tesorerías corporativas con inversiones y comité de riesgos

La señal de que el cliente encaja: alguien del área de riesgos o tesorería pasa
uno o varios días al mes "armando el informe del comité" en Excel.

## El problema que resuelve

1. **Tiempo:** el informe consume de 4 a 16 horas por mes de una persona calificada.
2. **Errores silenciosos:** fórmulas rotas, datos pegados en la fila equivocada,
   un emisor escrito de tres formas que parte la concentración en tres.
3. **Métricas débiles:** VaR simplificado o inexistente, sin backtesting ni
   escenarios históricos.
4. **Riesgo de persona clave:** el proceso vive en la cabeza de quien arma el Excel.
5. **Auditoría:** no hay forma de probar qué datos produjeron qué cifra.

## Qué recibe el cliente

- Informe mensual en PDF para el comité: resumen ejecutivo con mensajes
  redactados automáticamente, **plan de acción con montos** (cuánto reducir o
  mover para volver al límite), guía de lectura y glosario para el consejo, semáforo de límites, VaR y ES, backtesting,
  estrés, concentración, liquidez, calidad de datos y metodología.
- Anexo en Excel con todo el detalle y fórmulas vivas para auditoría.
- Bitácora de calidad de datos con hoja y fila de cada problema.
- Historial de indicadores y gráficas de evolución.
- Instalación en su propio computador: **los datos nunca salen de la entidad**.

## Cómo se implementa

| Fase | Duración | Qué pasa | Entregable |
|---|---|---|---|
| 0. Diagnóstico | 1 semana | Revisión del Excel e informe actuales; se corre la demo con un corte real del cliente | Informe de hallazgos + demo con sus datos |
| 1. Implementación | 3-5 semanas | Mapeo de su Excel, configuración de la política, conexión a curvas del proveedor de precios, ajuste del IRL a su supervisor | Motor instalado y configurado |
| 2. Paralelo | 1-2 cortes | Se corre junto al proceso manual y se concilian diferencias | Acta de conciliación |
| 3. Operación | Mensual | Ejecución, mantenimiento y soporte | Informe mensual |

El diagnóstico (fase 0) es la puerta de entrada: ver su propio mes procesado en
segundos, con los hallazgos que su Excel no mostraba, es el argumento de venta.

## Modelo comercial (hipótesis a validar con los primeros 2-3 clientes)

| Componente | Alcance | Rango de referencia |
|---|---|---|
| Diagnóstico | Revisión + demo con un corte real | COP 0 a 3 M (acreditable a la implementación) |
| Implementación | Fases 1 y 2, precio fijo | COP 12 a 30 M según instrumentos y fuentes |
| Retainer básico | Mantenimiento, actualizaciones, soporte | COP 1,5 a 2,5 M / mes |
| Retainer estándar | Básico + ejecución mensual + revisión del informe | COP 3 a 5 M / mes |
| Retainer premium | Estándar + presentación al comité + nuevos análisis | COP 6 a 9 M / mes |

Referencia de valor para el cliente: el costo total de un analista de riesgos
dedicado, el tiempo que se libera cada mes y el riesgo de reportar un límite
excedido como "cumple". Cobrar por proyecto y retainer, no por hora.

## Qué necesita el cliente

- Su Excel mensual de posiciones (o la plantilla incluida).
- La política de riesgos vigente (límites, contrapartes, escenarios).
- Acceso a las curvas de su proveedor de precios.
- Proyección de flujos de liquidez y saldos de depósitos a la vista.
- Un computador con Windows y Python (la instalación es de doble clic).

## Módulos adicionales (ingresos futuros)

- Títulos en UVR (TES UVR) y bonos indexados al IPC
- Derivados: forwards de tasa de cambio (conecta con el diagnóstico cambiario)
- IRL exacto según la metodología de la Superintendencia Financiera o de la Supersolidaria
- Riesgo de crédito de la cartera (pérdida esperada, matrices de transición)
- Conexión automática al proveedor de precios y envío del informe por correo
- Tablero web para la gerencia

## Guion de la demostración (15 minutos)

1. Abrir `entrada\posiciones_2026-09-30.xlsx`, hoja *Resumen_manual*: todos los
   emisores "Cumple". Preguntar: "¿así se ve hoy su informe?".
2. Doble clic en `generar_informe.bat`: el informe sale en segundos.
3. Página 1: Banco Cordillera excede el límite (17,6%); el Excel manual lo
   mostraba en 10,2% porque el nombre está escrito de 4 formas.
4. Sección 9: cada error del archivo con su fila exacta (un título vencido que
   seguía en el portafolio, una tasa en porcentaje, un duplicado).
5. Backtesting: el VaR paramétrico normal falla la prueba de Kupiec; el
   histórico se sostiene. "¿Su modelo actual se ha probado alguna vez?"
6. Anexo Excel: fórmulas vivas; auditoría puede rastrear cada cifra.
7. Cierre: "¿Cuánto tiempo le toma hoy a su equipo? ¿Quién revisa que un
   emisor no esté escrito de tres formas?"

## Preguntas difíciles (si las respondes sin mirar, estás listo para vender)

1. **¿Por qué VaR histórico y no paramétrico?** Porque los factores tienen colas
   pesadas; el backtesting lo prueba: el paramétrico falla Kupiec, el histórico no.
2. **¿Qué es el ES y por qué lo reportan?** Promedio de las pérdidas más allá del
   VaR; es la medida que Basilea adoptó en FRTB porque mira dentro de la cola.
3. **¿Cómo valoran un CDT IBR?** Próximo cupón fijado con el IBR del último
   reprecio; después, nominal más el valor presente de (margen pactado - spread).
4. **¿Sus precios cuadran con los del proveedor (Precia / PiP)?** En producción se
   usan sus curvas; el motor alerta cualquier diferencia mayor al 2%.
5. **¿Esto cumple con la Superfinanciera / Supersolidaria?** Apoya la gestión del
   SIAR; el IRL se ajusta a la metodología exacta de su supervisor en la implementación.
   La responsabilidad regulatoria sigue siendo de la entidad.
6. **¿Dónde quedan nuestros datos?** En su computador. Nada se sube a internet.
7. **¿Qué pasa si cambia el formato de nuestro Excel?** Se agregan alias de
   columnas en la configuración; el motor ubica el encabezado donde esté.
8. **¿Y si una calificación del archivo no coincide con el maestro?** Se usa la
   más conservadora y queda registrado.
9. **¿Por qué 500 días de historia?** Equilibrio entre estabilidad del percentil
   (5 observaciones en la cola del 1%) y relevancia de los datos.
10. **¿Qué pasa si el VaR falla el backtesting?** El informe lo muestra, sugiere
    revisar el modelo y complementar con ES y VaR estresado.
11. **¿Quién mantiene esto si usted no está?** Código documentado, parámetros de
    negocio en Excel, y el retainer cubre continuidad.
12. **¿Cuánto tarda?** Segundos por corte; el cuello de botella es cargar el Excel.

## Honestidad comercial

- El IRL incluido es simplificado; en la implementación se ajusta al supervisor
  de cada entidad.
- La demostración usa entidad y emisores ficticios y mercado sintético.
- El motor apoya al área de riesgos; la responsabilidad de los reportes
  regulatorios sigue siendo de la entidad.
