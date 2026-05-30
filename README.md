# Fraudia Claims — Detección de Fraude en Siniestros

Proyecto desarrollado para el HackIAthon de Aseguradora del Sur. La idea nació de un problema real: los analistas de siniestros reciben decenas de casos al día y es imposible revisar cada uno con el mismo nivel de atención. Fraudia Claims le da a cada analista un segundo par de ojos — uno que nunca se cansa, que consulta la base de datos en tiempo real y que aprende de cada fraude que el equipo confirma.

La app combina un pipeline de machine learning para clasificar el portafolio completo con un agente de IA (Gemini 2.5 Flash) que analiza casos individuales en profundidad, tiene acceso directo a Supabase y se vuelve más preciso conforme los analistas van tomando decisiones.

---

## Lo que hace

**Pipeline ML (scoring del portafolio):**
- Aplica 13 reglas de negocio antifraude (RF-01 a RF-13), incluyendo chasis/motor repetido, beneficiario recurrente y reclamos RC sin tercero
- Detecta descripciones de siniestros sospechosamente parecidas entre sí usando NLP (TF-IDF)
- Entrena un Random Forest e Isolation Forest con los datos históricos
- Combina todo en un score ML de 0 a 100 para los 500 siniestros del portafolio

**Agente Gemini (análisis profundo por demanda):**
- Consulta Supabase en tiempo real: historial del asegurado, perfil del proveedor, datos del vehículo, casos similares
- Lee los fraudes ya confirmados por analistas humanos y aprende de sus patrones
- Decide autónomamente qué información necesita (12 herramientas disponibles)
- Produce su propio score independiente con justificación detallada
- Responde preguntas libres sobre el portafolio en el chat del Inspector FRAUDIA
- Lee los documentos PDF (facturas, partes policiales) y detecta inconsistencias

**Flujo del analista:**
- Dashboard con KPIs, gráficos y tabla filtrable del portafolio completo
- Detalle de cada siniestro con Score ML + Score Gemini, datos del vehículo (placa, chasis, motor) y visor de documentos PDF
- Indicador 📎 y filtro para ubicar al instante los siniestros con documentos adjuntos
- Descarga de reporte en PDF con la conclusión del agente
- Registro de decisión (Fraude / Investigación / Legítimo) que se guarda en Supabase y retroalimenta al agente
- Formulario para registrar siniestros nuevos (ID correlativo SIN-XXXX) con análisis en tiempo real y adjuntar PDFs de respaldo

---

## Requisitos previos

- Python 3.11 o superior
- Una cuenta en [Supabase](https://supabase.com) (gratis)
- Una API Key de [Google AI Studio](https://aistudio.google.com) para Gemini (gratis)

---

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/Gael04-web/HackIAthon-Equipo-FranGab-reto-Aseguradora-del-Sur.git
cd HackIAthon-Equipo-FranGab-reto-Aseguradora-del-Sur
```

### 2. Crear entorno virtual e instalar dependencias

```bash
python -m venv venv
```

```bash
# Windows
venv\Scripts\activate

# Mac / Linux
source venv/bin/activate
```

```bash
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

```bash
# Windows
copy .env.example .env

# Mac / Linux
cp .env.example .env
```

Abre el archivo `.env` y completa las tres variables:

```
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_KEY=eyJhbGci...
GEMINI_API_KEY=AIzaSy...
```

**¿Dónde están las credenciales de Supabase?**
Proyecto en [supabase.com](https://supabase.com) → *Project Settings* → *API* → copia *Project URL* y *anon public key*.

**¿Dónde está la API Key de Gemini?**
Entra a [aistudio.google.com](https://aistudio.google.com) → *Get API Key* → crea una nueva (es gratis).

### 4. Colocar el dataset y los documentos PDF

Copia el archivo Excel del dataset en la carpeta del proyecto:

```
data/
├── dataset/
│   └── Evento_Datasets_Sinteticos_Fraude_500_v2.xlsx   ← aquí
└── docs/
    ├── DA_SIN-0378_DOC-0952.pdf                        ← PDFs del dataset
    ├── Muestras_Facturas_Siniestros-SIN-0001.pdf
    └── PP_SIN-0005_DOC-0012.pdf
    └── ... (26 PDFs en total)
```

Los PDFs se subirán automáticamente a Supabase Storage cuando corras el script de carga.

---

## Configurar la base de datos y Storage

### Tablas (SQL Editor de Supabase)

Ejecuta el contenido de `docs/schema.sql`. Eso crea las 5 tablas: `asegurados`, `polizas`, `proveedores`, `siniestros` y `documentos`.

Si ya tenías datos anteriores y quieres empezar limpio:

```sql
DROP TABLE IF EXISTS documentos, siniestros, polizas, proveedores, asegurados CASCADE;
```

Luego vuelve a ejecutar el schema.

### Bucket de Storage (para los PDFs)

En tu proyecto Supabase → **Storage** → **New bucket**:
- Nombre: `siniestros-docs`
- Activar **Public bucket** ✅

Esto permite que la app sirva los PDFs directamente desde Supabase sin necesitar los archivos locales.

---

## Cargar los datos reales a Supabase

El dataset contiene 500 siniestros, 174 asegurados, 33 proveedores, 1.263 documentos y 26 PDFs reales de Ecuador (facturas, partes policiales y declaraciones de accidente).

Corre este script **una sola vez** para subir todo:

```bash
python src/ingestion/load_data.py
```

El script hace tres cosas:
1. Sube las 5 tablas de datos a Supabase (upsert — no falla si ya existen)
2. Sube los 26 PDFs al bucket `siniestros-docs` de Supabase Storage
3. Guarda un CSV local en `data/synthetic/siniestros.csv` como fallback

---

## Ejecutar la aplicación

### Opción A — Local (desarrollo)

```bash
streamlit run src/app/main.py
```

Se abre en `http://localhost:8501`. La primera carga tarda 5-15 segundos porque entrena los modelos ML con los datos de Supabase.

### Opción B — Docker (producción)

```bash
docker-compose up --build
```

El contenedor lee los datos directamente de Supabase al arrancar usando las credenciales del `.env`. No necesita el Excel ni correr `load_data.py` — eso ya se hizo una vez antes.

---

## Demo — cómo usar la app

### Dashboard Principal

Muestra el resumen del portafolio completo: KPIs de riesgo, estado de las revisiones del analista y tabla filtrable por nivel de riesgo, ramo y score. Para una demo rápida, filtra solo Rojo y Amarillo para ver los casos que el sistema considera prioritarios.

### Detalle de Siniestro

Selecciona un siniestro del dropdown. Cada opción muestra su nivel de riesgo (🔴🟡🟢) y un 📎 si tiene documentos adjuntos; con el checkbox **"Solo con PDF"** filtras al instante los que tienen documentos. Verás nombre del asegurado, datos del vehículo (placa, marca, chasis, motor), número de parte policial, proveedor con su motivo de restricción, y el score calculado.

**Análisis con IA:** haz click en **"Análisis Profundo con Agente IA"** y Gemini va a:
1. Aplicar las 13 reglas de negocio al caso
2. Buscar narrativas similares en la base de datos
3. Consultar el historial del asegurado y los datos del vehículo en Supabase
4. Revisar el perfil del proveedor
5. Leer los fraudes ya confirmados por el equipo para calibrar su juicio
6. Producir su propio score con factores detallados y conclusión ejecutiva

La UI muestra los dos scores lado a lado (Score ML vs Score Gemini). Si divergen, el agente encontró algo que el modelo estadístico no ponderó igual.

**Documentos PDF:** si el siniestro tiene documentos adjuntos (facturas, partes policiales o declaraciones de accidente), aparece una sección **📁 Documentos del Siniestro** con dos opciones por cada archivo:
- **👁️ Ver documento** — muestra el PDF embebido directamente desde Supabase Storage
- **🤖 Analizar con IA** — Gemini lee el PDF y lo compara con los datos registrados buscando inconsistencias: montos en factura vs monto reclamado, fechas en el parte policial vs fecha de ocurrencia, placa en la declaración vs la registrada

Desde ahí puedes descargar el reporte en PDF y registrar la decisión final (Fraude / Investigación / Legítimo).

### Inspector FRAUDIA (chat)

El mismo agente responde preguntas libres sobre el portafolio. Tiene acceso a todas las herramientas, así que puede responder cosas como:

- *"¿Qué proveedores concentran más alertas?"* → consulta todos los proveedores ordenados por riesgo
- *"¿Qué ciudades concentran más alertas?"* → agrupa el portafolio por sucursal
- *"¿Cuáles son los 10 casos más urgentes para revisar hoy?"* → trae los de mayor score
- *"¿Qué documentos faltan en los casos críticos?"* → revisa la documentación incompleta
- *"¿Cuántos siniestros rojos hay en Vehículos?"* → filtra el portafolio

Los cuatro botones de sugerencias son un buen punto de partida para una demo.

### Métricas del Modelo

Muestra el rendimiento del Random Forest: precisión, recall, F1 y AUC-ROC, junto con la importancia de cada feature.

### Registrar Siniestro

Formulario para ingresar un siniestro nuevo y ver el análisis en tiempo real. Útil para demostrar el sistema con un caso inventado en el momento. El agente calcula el score y Gemini genera la conclusión. Puedes **adjuntar PDFs de respaldo** (factura, parte policial, fotografías) que se suben a Supabase Storage; al guardar, el siniestro recibe un **ID correlativo** (SIN-0501...) y aparece en el dashboard con su 📎 y sus documentos listos para analizar.

---

## Cómo aprende el agente

No es fine-tuning. El agente aprende por recuperación: cada vez que analiza un caso, consulta los siniestros que el equipo ya confirmó como fraude en Supabase y compara patrones. A medida que el equipo toma más decisiones, el agente tiene más ejemplos reales para calibrar su juicio. No hace falta reentrenar nada.

---

## Estructura del proyecto

Todo el código fuente vive dentro de la carpeta `src/`. Ahí es donde está el núcleo del sistema, incluyendo el agente de IA.

```
├── src/
│   ├── ai_agent/
│   │   └── claims_agent.py   → AGENTE IA: Gemini 2.5 Flash con 12 tools y loop agéntico.
│   │                            Aquí está toda la lógica de consulta a Supabase, aprendizaje
│   │                            de fraudes confirmados y scoring autónomo por demanda.
│   │
│   ├── app/
│   │   └── main.py           → Aplicación Streamlit: Dashboard, Detalle, Inspector FRAUDIA,
│   │                            Métricas y Registrar Siniestro.
│   │
│   ├── models/
│   │   └── fraud_model.py    → Pipeline ML batch: TF-IDF NLP, Random Forest, Isolation Forest.
│   │                            Genera el score_ml para los 500 siniestros del portafolio.
│   │
│   ├── ingestion/
│   │   └── load_data.py      → Lee el Excel real, genera vehículos, sube tablas + PDFs a Supabase.
│   │
│   ├── rules/
│   │   └── fraud_rules.py    → Motor de reglas: 13 reglas antifraude codificadas por expertos
│   │                            (RF-01 a RF-13). También las usa el agente como tool.
│   │
│   ├── explainability/
│   │   └── explain_score.py  → Genera explicaciones legibles del score ML para el analista.
│   │
│   └── utils/
│       └── pdf_utils.py      → Visor de PDFs (Supabase Storage o local) y análisis con Gemini.
│
├── data/
│   ├── dataset/
│   │   └── Evento_Datasets_Sinteticos_Fraude_500_v2.xlsx  → Dataset real (agregar manualmente, no versionado)
│   ├── docs/
│   │   └── *.pdf             → PDFs locales como fallback (no versionados, se sirven desde Supabase Storage)
│   └── synthetic/
│       └── siniestros.csv    → CSV generado automáticamente como fallback local.
│
├── docs/
│   ├── schema.sql            → Script SQL para crear las tablas en Supabase
│   ├── arquitectura.md       → Diagrama y descripción completa del sistema
│   ├── modelo_datos.md       → Esquema detallado de tablas y campos
│   ├── uso_ia.md             → Documentación del agente, sus 12 tools y cómo aprende
│   ├── reglas_negocio.md     → Catálogo de las 13 reglas antifraude con condiciones y puntos
│   └── limitaciones.md       → Limitaciones, falsos positivos, sesgos y alcance no decisorio
│
├── tests/
│   └── test_rules.py         → Tests unitarios del motor de reglas
│
├── .streamlit/
│   └── config.toml           → Tema oscuro fijo de la interfaz
├── .env.example              → Plantilla de variables de entorno
├── requirements.txt          → Dependencias del proyecto
├── Dockerfile / docker-compose.yml → Despliegue en contenedor
└── README.md
```

---

## Tecnologías usadas

| Componente | Tecnología |
|-----------|-----------|
| Frontend | Streamlit + Plotly (tema oscuro) |
| Pipeline ML | scikit-learn — Random Forest, Isolation Forest, TF-IDF |
| Agente IA | Google Gemini 2.5 Flash con function calling (12 tools) |
| Base de datos | Supabase (PostgreSQL) via REST API |
| Almacenamiento | Supabase Storage (bucket de PDFs) |
| Generación de reportes | fpdf2 |
| Dataset | Excel real — 500 siniestros Ecuador (`openpyxl`) |
| Despliegue | Docker + docker-compose |

---

## Equipo

Desarrollado por **FranGab** para el HackIAthon — Aseguradora del Sur.
