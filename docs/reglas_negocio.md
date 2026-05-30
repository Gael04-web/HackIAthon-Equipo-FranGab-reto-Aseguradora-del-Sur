# Reglas de Negocio Antifraude — Fraudia Claims

**Archivo:** `src/rules/fraud_rules.py → calculate_rule_score()`

El motor de reglas evalúa cada siniestro y retorna:
- `score_reglas`: puntuación acumulada (sin tope)
- `alertas`: lista de mensajes legibles para el analista
- `reglas_activadas`: IDs de reglas disparadas (ej. `RF-01-A`)

El `score_reglas` se escala con `* 2.5` y se topa en 100 antes de entrar al score final.

> **Nota de trazabilidad:** estas reglas RF-01…RF-13 son la implementación propia del equipo, alineadas con las señales de fraude y reglas críticas sugeridas en el documento del reto (secciones 7 y 8). El esquema de pesos es referencial y está justificado caso por caso, como permite el reto.

---

## Catálogo de Reglas

### RF-01 — Borde de Vigencia de Póliza
Siniestros reportados muy cerca del inicio o fin de la vigencia, patrón clásico de fraude oportunista.

| Regla | Condición | Puntos | Nivel |
|-------|-----------|--------|-------|
| RF-01-A | `dias_desde_inicio_poliza` ≤ 10 | +8 | ALTO |
| RF-01-B | 11 ≤ `dias_desde_inicio_poliza` ≤ 30 | +4 | MEDIO |
| RF-01-C | `dias_desde_fin_poliza` ≤ 10 | +8 | ALTO |

### RF-02 — Demora en Denuncia (Robo / Pérdida Total)
Aplica a coberturas `Robo`, `Robo de Accesorios` y `Pérdida Total`. Un robo legítimo se denuncia de inmediato.

| Regla | Condición | Puntos | Nivel |
|-------|-----------|--------|-------|
| RF-02-A | `dias_entre_ocurrencia_reporte` > 2 | +8 | ALTO |
| RF-02-B | 1 ≤ `dias_entre_ocurrencia_reporte` ≤ 2 | +4 | MEDIO |

### RF-03 — Alta Frecuencia del Asegurado
Asegurado con múltiples siniestros previos: posible esquema recurrente.

| Regla | Condición | Puntos | Nivel |
|-------|-----------|--------|-------|
| RF-03-A | `historial_siniestros_asegurado` ≥ 3 | +8 | ALTO |
| RF-03-B | `historial_siniestros_asegurado` = 2 | +4 | MEDIO |

### RF-04 — Proveedor en Lista Restrictiva
Talleres, clínicas o peritos fichados por irregularidades previas.

| Regla | Condición | Puntos | Nivel |
|-------|-----------|--------|-------|
| RF-04-A | `en_lista_restrictiva` = True | +10 | CRÍTICO |

### RF-05 — Documentación Incompleta
La falta de documentación puede indicar intento de evadir verificación.

| Regla | Condición | Puntos | Nivel |
|-------|-----------|--------|-------|
| RF-05-A | `documentos_completos` = False | +4 | MEDIO |

### RF-06 — Reporte Tardío
Aplica a todas las coberturas. Puede acumularse con RF-02.

| Regla | Condición | Puntos | Nivel |
|-------|-----------|--------|-------|
| RF-06-A | `dias_entre_ocurrencia_reporte` > 7 | +5 | ALTO |
| RF-06-B | 4 ≤ `dias_entre_ocurrencia_reporte` ≤ 7 | +3 | MEDIO |

### RF-07 — Monto Atípico
Reclamar casi la totalidad de la suma asegurada sugiere conocimiento previo del límite.

| Regla | Condición | Puntos | Nivel |
|-------|-----------|--------|-------|
| RF-07-A | `monto_reclamado` > `suma_asegurada` × 0.95 | +5 | ALTO |
| RF-07-B | `monto_reclamado` > `suma_asegurada` × 0.80 | +3 | MEDIO |

### RF-08 — Similitud de Narrativa (NLP)
Detecta copias o plantillas en la descripción, indicador de fraude organizado.

| Regla | Condición | Puntos | Nivel |
|-------|-----------|--------|-------|
| RF-08-A | `max_similarity_nlp` > 0.85 | +8 | ALTO |
| RF-08-B | 0.70 ≤ `max_similarity_nlp` ≤ 0.85 | +4 | MEDIO |

> `max_similarity_nlp` se calcula con TF-IDF + cosine similarity antes de ejecutar el motor de reglas.

### RF-09 — Perfil de Riesgo Histórico Alto
Usa el campo `perfil_riesgo` del asegurado (dato del dataset real).

| Regla | Condición | Puntos | Nivel |
|-------|-----------|--------|-------|
| RF-09-A | `perfil_riesgo` = "Alto" | +6 | ALTO |

### RF-10 — Chasis o Motor Repetido
Mismo número de chasis (VIN) o motor en varios siniestros: señal de vehículo clonado o fraude de partes.

| Regla | Condición | Puntos | Nivel |
|-------|-----------|--------|-------|
| RF-10-A | chasis aparece en ≥ 2 siniestros distintos | +10 | CRÍTICO |
| RF-10-B | chasis aparece en 1 siniestro adicional | +5 | ALTO |
| RF-10-C | motor aparece en otro siniestro (sin chasis repetido) | +5 | ALTO |

### RF-11 — Beneficiario Recurrente
Mismo beneficiario en varios siniestros: posible red de fraude.

| Regla | Condición | Puntos | Nivel |
|-------|-----------|--------|-------|
| RF-11-A | beneficiario aparece en ≥ 3 siniestros distintos | +8 | ALTO |
| RF-11-B | beneficiario aparece en 1-2 siniestros adicionales | +4 | MEDIO |

### RF-12 — Alta Frecuencia de Reclamos RC sin Tercero
Acumulación de reclamos de Responsabilidad Civil sin tercero identificado: patrón de siniestros simulados.

| Regla | Condición | Puntos | Nivel |
|-------|-----------|--------|-------|
| RF-12-A | `reclamos_rc_sin_tercero` > 2 | +6 | ALTO |
| RF-12-B | `reclamos_rc_sin_tercero` = 1 | +3 | MEDIO |

### RF-13 — Evento de RC sin Tercero Identificado
El siniestro actual es de Responsabilidad Civil y el asegurado tiene historial de eventos sin tercero (el tercero huyó o no existe).

| Regla | Condición | Puntos | Nivel |
|-------|-----------|--------|-------|
| RF-13-A | `cobertura` ∈ {Responsabilidad Civil, RC} **y** `reclamos_rc_sin_tercero` ≥ 1 | +5 | ALTO |

---

## Resumen de Puntuaciones Máximas

| Regla | Señal | Máx. pts |
|-------|-------|---------|
| RF-01 | Borde de vigencia | 16 |
| RF-02 | Demora denuncia robo | 8 |
| RF-03 | Frecuencia asegurado | 8 |
| RF-04 | Proveedor restrictivo | 10 |
| RF-05 | Documentos incompletos | 4 |
| RF-06 | Reporte tardío | 5 |
| RF-07 | Monto atípico | 5 |
| RF-08 | Similitud narrativa | 8 |
| RF-09 | Perfil de riesgo alto | 6 |
| RF-10 | Chasis/motor repetido | 10 |
| RF-11 | Beneficiario recurrente | 8 |
| RF-12 | Frecuencia RC sin tercero | 6 |
| RF-13 | Evento RC sin tercero | 5 |
| **TOTAL** | | **99** |

El `score_reglas` se multiplica por 2.5 y se recorta a 100 antes de ponderarse en el score final.

---

## Cobertura de las señales del reto

| Señal del documento (sección 7) | Regla implementada |
|---------------------------------|--------------------|
| Reclamo cercano al borde de vigencia | RF-01 |
| Demora denuncia por robo | RF-02 |
| Alta frecuencia de reclamos asegurado | RF-03 |
| Alta frecuencia de reclamos vehículo | RF-10 (chasis/motor) |
| Alta frecuencia reclamos solo RC | RF-12 |
| Beneficiario / proveedor recurrente | RF-04 + RF-11 |
| Documentos incompletos | RF-05 |
| Eventos sin tercero identificado | RF-13 |
| Documentos inconsistentes | Análisis de PDF con Gemini |
| Reporte tardío | RF-06 |
| Narrativas similares | RF-08 |
| Monto cercano/superior a suma asegurada | RF-07 |
| Perfil de riesgo histórico | RF-09 |
