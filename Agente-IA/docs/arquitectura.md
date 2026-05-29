# Arquitectura del Sistema — Fraudia Claims

## Visión General

Fraudia Claims es una plataforma de detección antifraude para Aseguradora del Sur. Combina reglas de negocio, modelos de machine learning y un agente de IA generativa (Gemini) para clasificar siniestros según su nivel de riesgo.

## Componentes Principales

```
┌─────────────────────────────────────────────────────────────┐
│                    CAPA DE PRESENTACIÓN                      │
│              Streamlit App  (src/app/main.py)                │
│  Dashboard │ Detalle Siniestro │ Inspector IA │ Métricas     │
└──────────────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌──────────────┐  ┌────────────────┐  ┌──────────────────┐
│  MODELO ML   │  │  AGENTE IA     │  │  MOTOR DE REGLAS │
│ fraud_model  │  │ claims_agent   │  │  fraud_rules     │
│ (RF + IF +   │  │ Gemini 2.5     │  │  RF-01…RF-08     │
│  TF-IDF NLP) │  │ Flash          │  │                  │
└──────┬───────┘  └───────┬────────┘  └───────┬──────────┘
       │                  │                   │
       └──────────────────┼───────────────────┘
                          ▼
        ┌─────────────────────────────────┐
        │         CAPA DE DATOS           │
        │  Supabase (PostgreSQL en nube)  │
        │  + CSV local como fallback      │
        └─────────────────────────────────┘
```

## Flujo de Datos

1. **Ingesta** (`src/ingestion/load_data.py`): genera datos sintéticos con Faker y los sube a Supabase.
2. **Carga** (`main.py → load_data()`): lee de Supabase o CSV; hace JOIN de siniestros con proveedores.
3. **Procesamiento** (`FraudModelPipeline`):
   - Calcula similitud NLP entre descripciones (TF-IDF + cosine similarity).
   - Aplica reglas de negocio (score_reglas).
   - Entrena Random Forest e Isolation Forest.
   - Genera `score_final` (0–100) y `nivel_riesgo` (Verde / Amarillo / Rojo).
4. **Presentación**: la app Streamlit muestra dashboards, permite analizar un siniestro con Gemini y registrar decisiones del analista en Supabase.

## Stack Tecnológico

| Capa | Tecnología |
|------|-----------|
| Frontend | Streamlit + Plotly |
| ML | scikit-learn (RandomForest, IsolationForest, TF-IDF) |
| IA Generativa | Google Gemini 2.5 Flash (`google-generativeai`) |
| Base de Datos | Supabase (PostgreSQL) |
| Generación PDF | fpdf2 |
| Datos Sintéticos | Faker (locale `es_ES`) |
| Config | python-dotenv |

## Estructura de Directorios

```
Agente-IA/
├── src/
│   ├── app/            # Streamlit entry point
│   ├── ingestion/      # Generación y carga de datos sintéticos
│   ├── models/         # Pipeline ML (RF, IF, NLP)
│   ├── rules/          # Motor de reglas de negocio
│   └── explainability/ # Explicación legible del score
├── data/
│   └── synthetic/      # CSV de siniestros (fallback local)
├── docs/               # Documentación técnica
├── tests/              # Tests unitarios
└── .env                # Variables de entorno (no versionado)
```
