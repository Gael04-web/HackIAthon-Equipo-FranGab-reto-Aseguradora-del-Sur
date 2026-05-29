# Fraudia Claims — Detección de Fraude en Siniestros

Proyecto desarrollado para el HackIAthon de Aseguradora del Sur. La idea nació de un problema real: los analistas de siniestros reciben decenas de casos al día y es imposible revisar cada uno con el mismo nivel de atención. Fraudia Claims le da a cada analista un segundo par de ojos — uno que nunca se cansa, que consulta la base de datos en tiempo real y que aprende de cada fraude que el equipo confirma.

La app combina un pipeline de machine learning para clasificar el portafolio completo con un agente de IA (Gemini 2.5 Flash) que analiza casos individuales en profundidad, tiene acceso directo a Supabase y se vuelve más preciso conforme los analistas van tomando decisiones.

---

## Lo que hace

**Pipeline ML (scoring del portafolio):**
- Aplica 8 reglas de negocio antifraude codificadas por expertos del sector
- Detecta descripciones de siniestros sospechosamente parecidas entre sí usando NLP (TF-IDF)
- Entrena un Random Forest e Isolation Forest con los datos históricos
- Combina todo en un score ML de 0 a 100 para los 500 siniestros del portafolio

**Agente Gemini (análisis profundo por demanda):**
- Consulta Supabase en tiempo real: historial del asegurado, perfil del proveedor, casos similares
- Lee los fraudes ya confirmados por analistas humanos y aprende de sus patrones
- Decide autónomamente qué información necesita (9 herramientas disponibles)
- Produce su propio score independiente con justificación detallada
- Responde preguntas libres sobre el portafolio en el chat del Inspector FRAUDIA

**Flujo del analista:**
- Dashboard con KPIs, gráficos y tabla filtrable del portafolio completo
- Detalle de cada siniestro con Score ML + Score Gemini para comparar
- Descarga de reporte en PDF con la conclusión del agente
- Registro de decisión (Fraude / Investigación / Legítimo) que se guarda en Supabase y retroalimenta al agente
- Formulario para registrar siniestros nuevos con análisis en tiempo real

---

## Requisitos previos

- Python 3.11 o superior
- Una cuenta en [Supabase](https://supabase.com) (gratis)
- Una API Key de [Google AI Studio](https://aistudio.google.com) para Gemini (gratis)

---

## Instalación

### 1. Clonar el repositorio

```bash
git clone <url-del-repo>
cd Agente-IA
```

### 2. Crear entorno virtual e instalar dependencias

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Configurar variables de entorno

Copia el archivo de ejemplo y completa tus credenciales:

```bash
cp .env.example .env
```

```
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_KEY=eyJhbGci...        ← clave "anon public" de tu proyecto
GEMINI_API_KEY=AIzaSy...
```

**¿Dónde están las credenciales de Supabase?**
Proyecto → *Project Settings* → *API* → copia *Project URL* y *anon public key*.

**¿Y la de Gemini?**
Entra a [aistudio.google.com](https://aistudio.google.com) → *Get API Key* → crea una nueva.

---

## Configurar la base de datos

En el **SQL Editor** de tu proyecto Supabase, ejecuta el contenido de `docs/schema.sql`. Eso crea las 5 tablas: `asegurados`, `polizas`, `proveedores`, `siniestros` y `documentos`.

Si ya tenías datos de una versión anterior y quieres empezar limpio:

```sql
DROP TABLE IF EXISTS documentos, siniestros, polizas, proveedores, asegurados CASCADE;
```

Luego vuelve a ejecutar el schema.

---

## Cargar los datos de ejemplo

El generador crea 500 siniestros con distribución realista (15% fraude, 20% sospechoso, 65% normal) y 1.000 documentos asociados:

```bash
python src/ingestion/load_data.py
```

Si las credenciales de Supabase no están configuradas, genera igual un CSV local en `data/synthetic/siniestros.csv` que la app usa como fallback.

---

## Ejecutar la aplicación

```bash
streamlit run src/app/main.py
```

Se abre en `http://localhost:8501`. La primera carga tarda 5-15 segundos porque entrena los modelos ML.

---

## Demo — cómo usar la app

### Dashboard Principal

Muestra el resumen del portafolio completo: KPIs de riesgo, estado de las revisiones del analista y tabla filtrable por nivel de riesgo, ramo y score. Para una demo rápida, filtra solo Rojo y Amarillo para ver los casos que el sistema considera prioritarios.

### Detalle de Siniestro

Selecciona cualquier siniestro del dropdown (ordenados de mayor a menor score ML). Verás los datos del caso y el score calculado por el pipeline.

Haz click en **"Análisis Profundo con Agente IA"** para activar el agente. Gemini va a:
1. Aplicar las reglas de negocio al caso
2. Buscar narrativas similares en la base de datos
3. Consultar el historial del asegurado en Supabase
4. Revisar el perfil del proveedor
5. Leer los fraudes ya confirmados por el equipo para comparar patrones
6. Producir su propio score con factores y conclusión ejecutiva

La UI muestra los dos scores lado a lado para que el analista pueda comparar. Si divergen mucho, significa que el agente encontró algo en la BD que el modelo estadístico no ponderó igual.

Desde ahí puedes descargar el reporte en PDF y registrar la decisión final (Fraude / Investigación / Legítimo). Esa decisión se guarda en Supabase y automáticamente enriquece el conocimiento del agente para futuros análisis.

### Inspector FRAUDIA (chat)

El mismo agente responde preguntas libres sobre el portafolio. Tiene acceso a todas las herramientas, así que puede responder cosas como:

- *"¿Qué proveedores concentran más alertas?"* → consulta todos los proveedores ordenados por riesgo
- *"¿Cuáles son los 10 casos más urgentes para revisar hoy?"* → trae los de mayor score
- *"¿Cuántos siniestros rojos hay en Vehículos?"* → filtra el portafolio
- *"Dame un resumen ejecutivo de los fraudes confirmados este mes"*

Los cuatro botones de sugerencias son un buen punto de partida para una demo.

### Métricas del Modelo

Muestra el rendimiento del Random Forest: precisión, recall, F1 y AUC-ROC, junto con la importancia de cada feature. Con los 500 siniestros de ejemplo deberías ver métricas entre 85-95%.

### Registrar Siniestro

Formulario para ingresar un siniestro nuevo y ver el análisis en tiempo real. Útil para demostrar el sistema con un caso inventado en el momento. El agente calcula el score y Gemini genera la conclusión.

---

## Cómo aprende el agente

No es fine-tuning. El agente aprende por recuperación: cada vez que analiza un caso, consulta los siniestros que el equipo ya confirmó como fraude en Supabase y compara patrones. A medida que el equipo toma más decisiones, el agente tiene más ejemplos reales para calibrar su juicio. No hace falta reentrenar nada.

---

## Estructura del proyecto

```
Agente-IA/
├── src/
│   ├── app/            → Aplicación Streamlit (main.py)
│   ├── ingestion/      → Generador de datos sintéticos
│   ├── models/         → Pipeline ML (Random Forest, Isolation Forest, NLP)
│   ├── rules/          → Motor de reglas antifraude (RF-01 a RF-08)
│   ├── ai_agent/       → Agente Gemini con 9 tools y loop agéntico
│   └── explainability/ → Explicaciones legibles del score ML
├── data/
│   └── synthetic/      → CSV local de siniestros (fallback sin Supabase)
├── docs/
│   ├── schema.sql      → Script SQL para crear las tablas en Supabase
│   ├── arquitectura.md → Diagrama y descripción del sistema
│   ├── modelo_datos.md → Esquema detallado de tablas y campos
│   ├── uso_ia.md       → Documentación completa de IA y tools del agente
│   └── reglas_negocio.md → Catálogo de las 8 reglas antifraude
├── tests/
│   └── test_rules.py   → Tests unitarios del motor de reglas
├── .env.example        → Plantilla de variables de entorno
├── requirements.txt    → Dependencias del proyecto
└── README.md
```

---

## Tecnologías usadas

| Componente | Tecnología |
|-----------|-----------|
| Frontend | Streamlit + Plotly |
| Pipeline ML | scikit-learn — Random Forest, Isolation Forest, TF-IDF |
| Agente IA | Google Gemini 2.5 Flash con function calling (9 tools) |
| Base de datos | Supabase (PostgreSQL) |
| Generación de reportes | fpdf2 |
| Datos sintéticos | Faker (locale español) |

---

## Equipo

Desarrollado por **FranGab** para el HackIAthon — Aseguradora del Sur.
