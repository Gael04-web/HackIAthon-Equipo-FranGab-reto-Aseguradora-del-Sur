# Limitaciones del Modelo — Fraudia Claims

Este documento declara de forma transparente las limitaciones del prototipo, sus posibles falsos positivos/negativos, sesgos y el alcance no decisorio de la solución. Forma parte del compromiso ético del reto: **el sistema genera alertas de revisión, nunca acusaciones automáticas de fraude.**

---

## 1. Alcance de la solución

| El sistema SÍ hace | El sistema NO hace |
|--------------------|--------------------|
| Asigna un score de riesgo (0-100) | Acusar formalmente de fraude |
| Clasifica en semáforo Verde/Amarillo/Rojo | Rechazar automáticamente un siniestro |
| Genera alertas explicables | Tomar decisiones de pago o rechazo |
| Prioriza casos para revisión humana | Sustituir al analista especializado |
| Detecta patrones y anomalías | Emitir conclusiones legales definitivas |

**Toda decisión final recae en un analista humano.** El score es una herramienta de priorización, no un veredicto.

---

## 2. Limitaciones de los datos

- **Datos 100% sintéticos.** El dataset (`Evento Datasets_Sinteticos_Fraude_500_v2.xlsx`) no contiene información personal real. Los nombres, placas, montos y narrativas son generados. Esto cumple el requisito ético del reto, pero implica que los patrones aprendidos no reflejan necesariamente el comportamiento de fraude real del mercado ecuatoriano.
- **Volumen limitado.** 500 siniestros, 174 asegurados, 33 proveedores. Suficiente para un prototipo, pero pequeño para entrenar un modelo de producción robusto.
- **Campos generados para cumplir el alcance.** Chasis, motor, marca, modelo, año y beneficiarios fueron generados sintéticamente (el Excel original solo traía la placa). Las repeticiones de chasis/motor y beneficiario se introdujeron deliberadamente (~8%) para demostrar las reglas RF-10 y RF-11; no provienen de fraude observado real.
- **Etiqueta de fraude aproximada.** No existe una columna `etiqueta_fraude` verificada. El modelo supervisado deriva la etiqueta del campo `estado` (`Investigación` y `Negativa` = sospechoso). Esta es una aproximación razonable pero imperfecta: un caso en investigación no es necesariamente fraude, y un caso liquidado podría haber sido fraude no detectado.

---

## 3. Limitaciones del modelo de Machine Learning

- **Random Forest sobre etiqueta proxy.** Como la etiqueta se deriva del estado, el modelo aprende a predecir "casos en investigación/negativa", no fraude confirmado. Las métricas (precision, recall, F1, AUC-ROC) deben leerse en ese contexto.
- **Isolation Forest con contaminación fija.** El parámetro `contamination=0.28` es un supuesto. Un valor mal calibrado puede marcar como anómalos casos legítimos atípicos (ej. un siniestro de monto alto pero válido).
- **Sin validación temporal.** El split train/test es aleatorio, no cronológico. En producción, un modelo debe validarse con datos posteriores en el tiempo para evitar fuga de información.
- **Normalización del anomaly score.** Se usa min-max sobre el lote actual; si el portafolio cambia, los rangos se recalibran y un mismo caso podría obtener distinto score.

---

## 4. Limitaciones de las reglas de negocio

- **Pesos referenciales.** Los puntajes de RF-01 a RF-13 son un esquema propio justificado, no un estándar actuarial validado. Pueden requerir recalibración con datos reales y feedback de analistas.
- **Umbrales fijos.** Por ejemplo, "monto > 95% de la suma asegurada" o "≥ 3 siniestros previos" son cortes arbitrarios. Casos legítimos cercanos al umbral pueden generar falsos positivos.
- **Reglas dependientes de calidad de datos.** RF-10 (chasis/motor) y RF-11 (beneficiario) solo funcionan si esos campos están completos y normalizados. Errores de digitación (un chasis mal escrito) evaden la detección.

---

## 5. Limitaciones del agente de IA (Gemini)

- **Dependencia de API externa.** El agente requiere `GEMINI_API_KEY` y conexión a internet. Si la API falla o se agota la cuota, el agente no responde. **Mitigación:** el pipeline ML, las reglas y el dashboard funcionan sin Gemini; solo se pierde el análisis conversacional y el de documentos.
- **Posibles alucinaciones.** Aunque el agente se apoya en herramientas que consultan datos reales, un LLM puede malinterpretar o sobre-interpretar. Por eso el system prompt lo obliga a justificar cada factor con datos concretos de las tools, y su salida es siempre una alerta para revisión humana.
- **Análisis de PDF.** La lectura de facturas/partes policiales depende de la calidad del documento. PDFs escaneados de baja resolución o manuscritos pueden producir lecturas incompletas.
- **No determinístico.** El score de Gemini puede variar ligeramente entre ejecuciones del mismo caso. Por eso se muestra junto al score ML (determinístico) para que el analista compare.

---

## 6. Falsos positivos y falsos negativos

- **Falsos positivos (marcar como sospechoso un caso legítimo):** un cliente honesto con un siniestro legítimo de monto alto, reportado con demora justificada (ej. hospitalización), puede acumular puntos y caer en Amarillo/Rojo. **Mitigación:** revisión humana obligatoria + explicación de cada alerta para que el analista descarte rápido.
- **Falsos negativos (no detectar un fraude):** un fraude sofisticado con documentación completa, montos moderados y narrativa original puede pasar como Verde. El sistema reduce el riesgo combinando reglas + ML + NLP + anomalías, pero no lo elimina.

---

## 7. Sesgos potenciales

- **Sesgo por proveedor/ciudad.** Si históricamente ciertos talleres o sucursales concentran más casos en investigación, el modelo puede penalizarlos de más, perjudicando a proveedores legítimos de esas zonas.
- **Sesgo por perfil de riesgo.** RF-09 usa el `perfil_riesgo` histórico del asegurado. Si ese perfil arrastra sesgos previos, se perpetúan.
- **Mitigación:** todas las variables usadas son explicables (no hay caja negra), lo que permite auditar y discutir cada decisión. Se recomienda un análisis de sesgo formal antes de cualquier uso real.

---

## 8. Limitaciones técnicas

- **Escalabilidad del entrenamiento.** El modelo se reentrena en memoria al cargar la app. Con cientos de miles de siniestros esto sería lento; en producción se separaría el entrenamiento (batch/offline) del scoring (online).
- **Concurrencia.** Streamlit con caché en memoria sirve bien para demo y pocos analistas simultáneos, no para alta concurrencia.
- **Storage de documentos.** Los PDFs viven en Supabase Storage (bucket público para la demo). En producción el bucket debería ser privado con URLs firmadas temporales.

---

## 9. Cumplimiento ético y de seguridad (sección 17 del reto)

- ✅ No se usan datos personales reales.
- ✅ No se exponen credenciales (`.env` ignorado por git, `.env.example` como plantilla).
- ✅ Identificadores anonimizados (IDs tipo SIN-0001, ASEG-0010).
- ✅ El resultado se comunica siempre como "posible irregularidad" / "requiere revisión".
- ✅ Revisión humana obligatoria antes de cualquier decisión.
- ✅ Limitaciones y falsos positivos documentados (este archivo).
- ✅ **Row Level Security (RLS) habilitado** en Supabase con políticas explícitas para el rol `anon` (lectura del portafolio, registro de siniestros y decisiones). La seguridad de la base de datos queda activa, no desactivada.

**Nota de seguridad para producción:** la app usa la `anon public key` con políticas que permiten lectura pública del portafolio (apropiado para un prototipo con datos sintéticos). En producción se recomienda separar roles: `service_role` para la ingesta, y políticas RLS más restrictivas por usuario/rol para el frontend, además de un bucket de Storage privado con URLs firmadas.

---

## 10. Próximos pasos para producción

1. Sustituir datos sintéticos por datos reales anonimizados con etiquetas de fraude verificadas por la Unidad Antifraude.
2. Validación temporal y monitoreo de drift del modelo.
3. Análisis formal de sesgo y fairness por segmento (proveedor, ciudad, perfil).
4. Bucket de documentos privado con URLs firmadas y control de acceso por rol.
5. Separar entrenamiento offline del scoring online; exponer el score vía API.
6. Registro de auditoría: trazabilidad de cada score, regla activada y decisión del analista.
7. Bucle de retroalimentación: las decisiones confirmadas reentrenan/recalibran el sistema periódicamente.
