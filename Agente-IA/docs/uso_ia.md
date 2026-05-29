# Uso de Inteligencia Artificial — Fraudia Claims

## Componentes de IA

El sistema combina cuatro capas de inteligencia que producen un único `score_final` (0–100).

---

## 1. Procesamiento de Lenguaje Natural (NLP)

**Archivo:** `src/models/fraud_model.py → _calc_nlp_similarity()`

**Tecnología:** TF-IDF Vectorizer + Cosine Similarity (scikit-learn)

**Proceso:**
1. Se vectorizan las descripciones de todos los siniestros con TF-IDF.
2. Se calcula la matriz de similitud coseno entre todos los pares.
3. Para cada siniestro se guarda la similitud máxima con cualquier otro (`max_similarity_nlp`) y el ID del siniestro más similar.

**Uso en score:** Las narrativas idénticas o muy parecidas son señal de fraude organizado (se usa el mismo texto para múltiples reclamaciones). Contribuye un 10% al score final.

**Regla activada:** RF-08 (ver `docs/reglas_negocio.md`).

---

## 2. Modelo Supervisado — Random Forest

**Archivo:** `src/models/fraud_model.py → train_models()`

**Tecnología:** `RandomForestClassifier(n_estimators=100, class_weight='balanced')`

**Features de entrada:**
- `dias_desde_inicio_poliza`
- `dias_desde_fin_poliza`
- `dias_entre_ocurrencia_reporte`
- `monto_reclamado`
- `monto_estimado`
- `historial_siniestros_asegurado`
- `documentos_completos_num`
- `pct_casos_observados`
- `en_lista_restrictiva_num`
- `score_reglas` (salida del motor de reglas)
- `max_similarity_nlp` (salida del NLP)

**Salida:** `prob_rf` — probabilidad (0.0 a 1.0) de que el siniestro sea fraude.

**Contribución al score final:** 35% (`prob_rf * 100 * 0.35`)

**Métricas:** Precision, Recall, F1, AUC-ROC — visibles en la página "Métricas del Modelo".

---

## 3. Detección de Anomalías — Isolation Forest

**Archivo:** `src/models/fraud_model.py → train_models()`

**Tecnología:** `IsolationForest(contamination=0.15)`

**Descripción:** Detecta siniestros que se comportan de forma estadísticamente atípica respecto al portafolio, sin necesitar etiquetas de fraude. Complementa al Random Forest con casos no vistos anteriormente.

**Salida:** `anomaly_score` normalizado 0–1 (1 = muy anómalo).

**Contribución al score final:** 15% (`anomaly_score * 100 * 0.15`)

---

## 4. Agente Conversacional — Gemini 2.5 Flash

**Archivo:** `src/ai_agent/claims_agent.py`

**Modelo:** `gemini-2.5-flash` vía `google.generativeai`

**Dos modos de uso:**

### 4a. Chatbot del Inspector FRAUDIA
- El agente recibe un contexto con estadísticas del portafolio (total siniestros, distribución de riesgo, top 5 críticos, proveedores problemáticos, resumen por ramo).
- El analista puede hacer preguntas en lenguaje natural: "¿qué casos revisar primero?", "¿qué proveedores generan más alertas?".
- El historial de la conversación se mantiene en `st.session_state`.

### 4b. Análisis Individual de Siniestro
- Recibe los datos crudos de un siniestro y genera un reporte estructurado con:
  - **Factores de Riesgo Detectados** (lista de viñetas)
  - **Conclusión Ejecutiva** (recomendación de pago o escalamiento)
- El reporte puede descargarse en PDF.

**Instrucción de seguridad:** El prompt del sistema instruye a Gemini a usar siempre lenguaje de "posible irregularidad" o "requiere revisión", nunca afirmar directamente fraude, protegiendo al asegurado y a la aseguradora de implicancias legales.

---

## Fórmula del Score Final

```
score_final =
    (score_reglas * 2.5).clip(max=100) * 0.40   ← Motor de reglas
  + prob_rf * 100                        * 0.35   ← Random Forest
  + anomaly_score * 100                  * 0.15   ← Isolation Forest
  + max_similarity_nlp * 100             * 0.10   ← NLP similitud
```

| Rango score_final | Nivel de Riesgo | Acción |
|-------------------|----------------|--------|
| 0 – 40 | Verde | Flujo estándar de pago |
| 41 – 75 | Amarillo | Revisión por el analista |
| 76 – 100 | Rojo | Escalar a Unidad Antifraude |

---

## Configuración de API Keys

Las credenciales se gestionan vía variables de entorno (ver `.env.example`):

```
GEMINI_API_KEY=tu_clave_aqui
```

Si la clave no está configurada, el sistema opera sin el agente conversacional pero mantiene las capas de ML y reglas.
