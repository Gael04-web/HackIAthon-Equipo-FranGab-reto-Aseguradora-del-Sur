# Uso de Inteligencia Artificial — Fraudia Claims

El sistema tiene dos capas de IA que trabajan en paralelo y se complementan:

- **Pipeline ML** (scikit-learn): scoring rápido y determinístico para los 500 siniestros del portafolio, visible en el Dashboard.
- **Agente Gemini** (Google Gemini 2.5 Flash): análisis profundo y autónomo por demanda, con acceso a la base de datos en tiempo real y aprendizaje de casos confirmados.

---

## Capa 1 — Pipeline ML (scoring de portafolio)

El pipeline ML corre una vez al iniciar la app y produce el `score_ml` para todos los siniestros. Es la capa que alimenta el Dashboard Principal.

### 1a. NLP — Similitud de Narrativas

**Archivo:** `src/models/fraud_model.py → _calc_nlp_similarity()`

Convierte todas las descripciones de siniestros en vectores TF-IDF y calcula similitud coseno entre todos los pares. Para cada siniestro guarda la similitud máxima con cualquier otro (`max_similarity_nlp`). Las narrativas copiadas o muy parecidas son señal de fraude organizado.

### 1b. Motor de Reglas

**Archivo:** `src/rules/fraud_rules.py`

8 reglas codificadas por expertos del sector asegurador. Producen un `score_reglas` (0–64 puntos) y una lista de alertas textuales. Ver `docs/reglas_negocio.md` para el catálogo completo.

### 1c. Random Forest

`RandomForestClassifier(n_estimators=100, class_weight='balanced')` entrenado con los siniestros históricos (15% etiquetados como fraude). Produce `prob_rf` (probabilidad 0–1).

### 1d. Isolation Forest

`IsolationForest(contamination=0.15)` sin supervisión. Detecta siniestros estadísticamente atípicos respecto al portafolio. Produce `anomaly_score` normalizado (0–1).

### Fórmula del Score ML

```
score_ml =
    min(score_reglas × 2.5, 100) × 0.40   ← reglas de negocio
  + prob_rf × 100                 × 0.35   ← Random Forest
  + anomaly_score × 100           × 0.15   ← Isolation Forest
  + max_similarity_nlp × 100      × 0.10   ← similitud NLP
```

| Rango | Nivel | Acción |
|-------|-------|--------|
| 0–40 | Verde | Flujo estándar |
| 41–75 | Amarillo | Revisión del analista |
| 76–100 | Rojo | Escalar a Unidad Antifraude |

---

## Capa 2 — Agente Gemini (análisis profundo por demanda)

**Archivo:** `src/ai_agent/claims_agent.py`  
**Modelo:** `gemini-2.5-flash` con function calling

El agente se activa cuando el analista hace click en **"Análisis Profundo con Agente IA"** en la página de Detalle de Siniestro, o cuando escribe en el chat del Inspector FRAUDIA. A diferencia del pipeline ML, el agente:

- Consulta Supabase en tiempo real durante el análisis
- Decide autónomamente qué información necesita
- Aprende de los fraudes ya confirmados por analistas humanos
- Produce su propio score independiente del score ML

### Las 9 Tools que Gemini controla

Gemini invoca estas funciones de forma autónoma, en el orden que considere necesario, según la pregunta o el caso que está analizando:

| Tool | Qué hace | Cuándo la usa Gemini |
|------|---------|---------------------|
| `apply_business_rules` | Ejecuta las 8 reglas antifraude | Siempre, como primer paso del análisis |
| `search_similar_claims` | NLP sobre todas las descripciones en BD | Para detectar narrativas copiadas |
| `get_confirmed_fraud_cases` | Lee fraudes confirmados por analistas | Para calibrar su score con patrones reales |
| `get_insured_history` | Historial de siniestros del asegurado en Supabase | Para detectar reincidencia |
| `get_provider_risk` | Perfil de riesgo de un proveedor en Supabase | Para evaluar el proveedor del caso |
| `get_all_providers_risk` | Todos los proveedores ordenados por riesgo | Preguntas como "¿qué proveedores generan más alertas?" |
| `get_top_critical_claims` | Top N siniestros por score | Preguntas como "casos más urgentes" |
| `get_claims_by_filter` | Filtra siniestros por nivel, ramo o decisión | Preguntas como "cuántos rojos hay en Salud" |
| `get_portfolio_stats` | Estadísticas generales del portafolio | Para contextualizar un caso individual |

### Loop Agéntico

```
Analista solicita análisis del siniestro X
              │
              ▼
        Gemini recibe prompt
              │
              ▼
    ┌─── ¿Necesita más info? ───┐
    │                           │
    │  Sí → invoca tool         │
    │        ↓                  │
    │  Ejecutamos la función    │
    │  Devolvemos resultado     │
    │        ↓                  │
    └──── Gemini evalúa ────────┘
              │
              │  No necesita más info
              ▼
    Gemini produce: score + nivel + factores + conclusión
```

El loop continúa hasta que Gemini tiene suficiente información para emitir su veredicto. Típicamente invoca entre 4 y 6 tools por análisis.

### Cómo aprende de los datos

No es fine-tuning — es aprendizaje por recuperación (RAG). Cada vez que Gemini analiza un siniestro, llama a `get_confirmed_fraud_cases()` y lee los casos que analistas humanos ya validaron como fraude. Compara patrones:

> *"Los últimos 12 fraudes confirmados tenían menos de 5 días desde inicio de póliza. Este caso tiene 3 días. Patrón coincidente."*

Conforme el equipo va tomando decisiones en la app (`Fraude Confirmado`, `En Investigación`, `Legítimo`), la base de conocimiento que Gemini consulta crece automáticamente — sin reentrenar ningún modelo.

### Output del agente

Para análisis de siniestro individual, el agente retorna:
```json
{
  "score": 87,
  "nivel_riesgo": "Rojo",
  "factores": [
    "Siniestro reportado 3 días después de iniciar la póliza (patrón en 8/12 fraudes confirmados)",
    "Proveedor con 42% de casos observados, figurando en lista restrictiva",
    "Narrativa 91% similar al siniestro abc12345, confirmado como fraude en marzo"
  ],
  "conclusion": "El caso presenta múltiples señales que requieren revisión especializada..."
}
```

La app muestra los dos scores en paralelo para que el analista pueda compararlos:

```
Score ML (pipeline)   Score Gemini (agente)   Nivel según Gemini
      72/100                87/100  (+15)           Rojo
```

### Modo Chat — Inspector FRAUDIA

El mismo agente con las mismas tools responde preguntas libres del analista sobre el portafolio completo. Mantiene historial de conversación dentro de la sesión.

---

## Conducta del agente

El system prompt instruye a Gemini a:
- Nunca afirmar que un cliente cometió fraude — siempre usar lenguaje como "posible irregularidad", "requiere revisión", "señal de alerta"
- Ser específico y cuantitativo: citar los valores exactos y compararlos con patrones de fraudes confirmados
- No usar más tools de las necesarias para responder

---

## Configuración

```
GEMINI_API_KEY=tu_clave_aqui   ← Google AI Studio (aistudio.google.com)
```

Sin esta clave el agente devuelve un mensaje de error pero el pipeline ML sigue funcionando. El Dashboard, las métricas y el motor de reglas no dependen de Gemini.
