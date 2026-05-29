# Arquitectura del Sistema — Fraudia Claims

## Visión General

Fraudia Claims es una plataforma antifraude para Aseguradora del Sur. Combina un pipeline de ML para scoring masivo del portafolio con un agente de IA generativa (Gemini 2.5 Flash) que analiza casos individuales en profundidad, consulta la base de datos en tiempo real y aprende de los fraudes que los analistas van confirmando.

---

## Diagrama de Componentes

```
┌──────────────────────────────────────────────────────────────────────┐
│                        CAPA DE PRESENTACIÓN                          │
│                  Streamlit App  (src/app/main.py)                    │
│   Dashboard │ Detalle Siniestro │ Inspector FRAUDIA │ Métricas │ Registrar │
└───────┬──────────────────────────────────┬───────────────────────────┘
        │                                  │
        │  scoring de portafolio           │  análisis profundo por demanda
        ▼                                  ▼
┌───────────────────┐            ┌─────────────────────────────────────┐
│   PIPELINE ML     │            │         AGENTE GEMINI               │
│  fraud_model.py   │            │       claims_agent.py               │
│                   │            │                                     │
│  TF-IDF NLP       │            │  9 tools que Gemini invoca solo:    │
│  Random Forest    │            │  ├─ apply_business_rules            │
│  Isolation Forest │            │  ├─ search_similar_claims           │
│  Motor de Reglas  │            │  ├─ get_confirmed_fraud_cases       │
│                   │            │  ├─ get_insured_history             │
│  → score_ml       │            │  ├─ get_provider_risk               │
│  → nivel_riesgo   │            │  ├─ get_all_providers_risk          │
│  (batch, 500 sin) │            │  ├─ get_top_critical_claims         │
└────────┬──────────┘            │  ├─ get_claims_by_filter            │
         │                       │  └─ get_portfolio_stats             │
         │                       │                                     │
         │                       │  → score_gemini (0-100)             │
         │                       │  → factores detectados              │
         │                       │  → conclusión ejecutiva             │
         └────────────┬──────────┘                                     │
                      │          └─────────────────┬───────────────────┘
                      │                            │ consultas en tiempo real
                      ▼                            ▼
           ┌──────────────────────────────────────────┐
           │              CAPA DE DATOS               │
           │     Supabase (PostgreSQL en nube)        │
           │                                          │
           │  asegurados │ polizas │ proveedores      │
           │  siniestros │ documentos                 │
           │  (decision_analista → retroalimenta IA)  │
           └──────────────────────────────────────────┘
                              ▲
                     Fallback │ (sin Supabase)
                              │
                   ┌──────────────────┐
                   │  CSV local       │
                   │  data/synthetic/ │
                   └──────────────────┘
```

---

## Dos Scores, Una Decisión

La arquitectura produce dos scores independientes que el analista puede comparar:

```
┌─────────────────────────────────────────────────────────────┐
│  Score ML  (pipeline batch — siempre disponible)            │
│  = reglas×40% + RF×35% + IF×15% + NLP×10%                  │
│  Determinístico, rápido, calculado para todos los 500 casos │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Score Gemini  (agente por demanda)                         │
│  Razonado: Gemini consulta BD, compara con fraudes          │
│  confirmados y justifica cada factor con datos reales       │
│  Se activa solo cuando el analista lo solicita              │
└─────────────────────────────────────────────────────────────┘
```

Si los dos scores divergen significativamente, es información útil para el analista: el agente encontró algo en la BD que el modelo estadístico no ponderó de la misma manera.

---

## Flujo de Datos

### Al iniciar la app

```
Supabase / CSV
      │
      ▼  load_data()  (@st.cache_data)
  DataFrame crudo (siniestros + proveedores merge)
      │
      ▼  get_processed_data_and_model()  (@st.cache_data)
  Pipeline ML: NLP → Reglas → RF → IF → score_ml → nivel_riesgo
      │
      ▼
  Dashboard muestra portafolio completo con scores ML
```

### Al analizar un siniestro con Gemini

```
Analista selecciona siniestro → click "Análisis Profundo"
      │
      ▼
  ClaimsAgent.analyze_single_claim(datos)
      │
      ▼  Loop agéntico (hasta 10 rondas)
  Gemini invoca tools → ejecutamos → devolvemos resultado
  Gemini invoca más tools si necesita más información
      │
      ▼
  Gemini emite: score + nivel + factores + conclusión
      │
      ▼
  UI muestra Score ML vs Score Gemini + descarga PDF
```

### Al confirmar una decisión

```
Analista click "Fraude Confirmado"
      │
      ├──► Supabase: UPDATE siniestros SET decision_analista = 'Fraude Confirmado'
      │    (permanente — retroalimenta el aprendizaje del agente)
      │
      └──► st.session_state.decisions[id] = 'Fraude Confirmado'
           (instantáneo — sin reentrenar el modelo)
```

---

## Decisiones de Diseño

**¿Por qué dos scores y no uno?**
El pipeline ML es rápido y necesario para mostrar el portafolio completo. Llamar a Gemini 500 veces al cargar la app sería lento y costoso. El agente se usa en profundidad donde importa: en el análisis individual.

**¿Por qué `@st.cache_data` para el modelo?**
`@st.cache_data` serializa con pickle y soporta DataFrames nativamente. Evita reentrenar el modelo en cada rerun de Streamlit y desacopla el modelo de las actualizaciones de `decision_analista`.

**¿Por qué session_state para las decisiones?**
Permite que los cambios de `decision_analista` se reflejen instantáneamente en la UI sin limpiar el caché del modelo (lo cual forzaría un reentrenamiento completo de 20-40 segundos).

**¿Cómo aprende Gemini sin fine-tuning?**
A través de recuperación: `get_confirmed_fraud_cases()` lee los casos validados por humanos en Supabase y los inyecta como contexto en cada análisis. A medida que los analistas van confirmando fraudes, la base de conocimiento crece automáticamente.

---

## Stack Tecnológico

| Capa | Tecnología |
|------|-----------|
| Frontend | Streamlit + Plotly |
| ML batch | scikit-learn (RandomForest, IsolationForest, TF-IDF) |
| Agente IA | Google Gemini 2.5 Flash con function calling |
| Base de Datos | Supabase (PostgreSQL) |
| Generación PDF | fpdf2 |
| Datos Sintéticos | Faker (locale `es_ES`) |
| Config | python-dotenv |

---

## Estructura de Directorios

```
Agente-IA/
├── src/
│   ├── app/            → Streamlit entry point (main.py)
│   ├── ingestion/      → Generación y carga de datos sintéticos
│   ├── models/         → Pipeline ML (RF, IF, NLP)
│   ├── rules/          → Motor de reglas antifraude (RF-01 a RF-08)
│   ├── ai_agent/       → Agente Gemini con 9 tools y loop agéntico
│   └── explainability/ → Explicaciones legibles del score ML
├── data/
│   └── synthetic/      → CSV local (fallback sin Supabase)
├── docs/
│   ├── schema.sql      → Tablas de Supabase
│   ├── arquitectura.md → Este archivo
│   ├── modelo_datos.md → Esquema de tablas y campos
│   ├── uso_ia.md       → Documentación detallada de IA
│   └── reglas_negocio.md → Catálogo RF-01 a RF-08
├── tests/
│   └── test_rules.py   → Tests unitarios del motor de reglas
├── .env.example        → Plantilla de variables de entorno
└── requirements.txt    → Dependencias
```
