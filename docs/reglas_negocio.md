# Reglas de Negocio Antifraude — Fraudia Claims

**Archivo:** `src/rules/fraud_rules.py → calculate_rule_score()`

El motor de reglas evalúa cada siniestro y retorna:
- `score_reglas`: puntuación acumulada (sin tope)
- `alertas`: lista de mensajes legibles para el analista
- `reglas_activadas`: IDs de reglas disparadas (ej. `RF-01-A`)

El `score_reglas` se escala con `* 2.5` y se topa en 100 antes de entrar al score final.

---

## Catálogo de Reglas

### RF-01 — Borde de Vigencia de Póliza

Detecta siniestros reportados muy cerca del inicio o fin de la vigencia, patrón clásico de fraude oportunista.

| Regla | Condición | Puntos | Nivel |
|-------|-----------|--------|-------|
| RF-01-A | `dias_desde_inicio_poliza` ≤ 10 | +8 | ALTO |
| RF-01-B | 11 ≤ `dias_desde_inicio_poliza` ≤ 30 | +4 | MEDIO |
| RF-01-C | `dias_desde_fin_poliza` ≤ 10 | +8 | ALTO |

---

### RF-02 — Demora en Denuncia de Robo

Aplica únicamente cuando `cobertura = "Robo"`. Un robo legítimo se denuncia inmediatamente; la demora sugiere que el evento pudo no haber ocurrido.

| Regla | Condición | Puntos | Nivel |
|-------|-----------|--------|-------|
| RF-02-A | `dias_entre_ocurrencia_reporte` > 2 | +8 | ALTO |
| RF-02-B | 1 ≤ `dias_entre_ocurrencia_reporte` ≤ 2 | +4 | MEDIO |

---

### RF-03 — Alta Frecuencia del Asegurado

Un asegurado con múltiples siniestros previos tiene mayor probabilidad de estar en un esquema de fraude recurrente.

| Regla | Condición | Puntos | Nivel |
|-------|-----------|--------|-------|
| RF-03-A | `historial_siniestros_asegurado` ≥ 3 | +8 | ALTO |
| RF-03-B | `historial_siniestros_asegurado` = 2 | +4 | MEDIO |

---

### RF-04 — Proveedor Sospechoso

Talleres, clínicas o médicos en lista restrictiva o con alto porcentaje de irregularidades históricas.

| Regla | Condición | Puntos | Nivel |
|-------|-----------|--------|-------|
| RF-04-A | `en_lista_restrictiva` = True | +10 | CRÍTICO |
| RF-04-B | `pct_casos_observados_proveedor` > 0.20 **y** `reclamos_asociados_proveedor` > 2 | +5 | ALTO |

---

### RF-05 — Documentación Incompleta

La falta de documentación puede indicar intento de evadir verificación.

| Regla | Condición | Puntos | Nivel |
|-------|-----------|--------|-------|
| RF-05-A | `documentos_completos` = False | +4 | MEDIO |

---

### RF-06 — Reporte Tardío

Un reporte tardío dificulta la verificación de campo y es señal de alerta independiente del tipo de cobertura.

| Regla | Condición | Puntos | Nivel |
|-------|-----------|--------|-------|
| RF-06-A | `dias_entre_ocurrencia_reporte` > 7 | +5 | ALTO |
| RF-06-B | 4 ≤ `dias_entre_ocurrencia_reporte` ≤ 7 | +3 | MEDIO |

> **Nota:** RF-06 aplica a todas las coberturas; RF-02 aplica solo a Robo y puede acumularse con RF-06.

---

### RF-07 — Monto Atípico

Reclamar casi la totalidad de la suma asegurada es infrecuente en siniestros legítimos y sugiere conocimiento previo del límite.

| Regla | Condición | Puntos | Nivel |
|-------|-----------|--------|-------|
| RF-07-A | `monto_reclamado` > `suma_asegurada` × 0.95 | +5 | ALTO |

---

### RF-08 — Similitud de Narrativa (NLP)

Detecta copias o plantillas en la descripción del siniestro, indicador de fraude organizado o en red.

| Regla | Condición | Puntos | Nivel |
|-------|-----------|--------|-------|
| RF-08-A | `max_similarity_nlp` > 0.85 | +8 | ALTO |
| RF-08-B | 0.70 ≤ `max_similarity_nlp` ≤ 0.85 | +4 | MEDIO |

> El valor `max_similarity_nlp` es calculado por el módulo NLP (TF-IDF + cosine similarity) antes de que el motor de reglas se ejecute.

---

## Resumen de Puntuaciones Máximas

| Regla | Máx. pts |
|-------|---------|
| RF-01 (borde vigencia) | 16 |
| RF-02 (demora robo) | 8 |
| RF-03 (frecuencia) | 8 |
| RF-04 (proveedor) | 10 |
| RF-05 (documentos) | 4 |
| RF-06 (reporte tardío) | 5 |
| RF-07 (monto atípico) | 5 |
| RF-08 (similitud NLP) | 8 |
| **TOTAL** | **64** |

Un `score_reglas` de 64 equivale a `score_reglas_escalado = 100` (tope) tras multiplicar por 2.5 y recortar.
