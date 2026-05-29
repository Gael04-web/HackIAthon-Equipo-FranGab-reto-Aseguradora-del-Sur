# Fraudia Claims — Detección de Fraude en Siniestros

Proyecto desarrollado para el HackIAthon de Aseguradora del Sur. La idea nació de un problema real: los analistas de siniestros reciben decenas de casos al día y es imposible revisar cada uno con el mismo nivel de atención. Fraudia Claims le da a cada analista un segundo par de ojos — uno que nunca se cansa y que aprendió de miles de patrones de fraude.

La app combina reglas de negocio del sector asegurador, machine learning y un agente conversacional con Gemini 2.5 Flash para clasificar siniestros por nivel de riesgo (Verde, Amarillo, Rojo) y ayudar al analista a tomar decisiones más rápido y con más información.

---

## Lo que hace

- Analiza cada siniestro con 8 reglas de negocio antifraude (borde de vigencia, demora en denuncia, proveedores en lista negra, monto atípico, etc.)
- Detecta descripciones de siniestros sospechosamente parecidas entre sí usando NLP (TF-IDF)
- Entrena un Random Forest e Isolation Forest con los datos históricos para predecir fraude
- Combina todo en un score de 0 a 100 con nivel de riesgo visual
- Permite chatear con un agente de IA (Gemini) que conoce todo el portafolio
- Genera reportes en PDF con la conclusión del análisis
- Guarda la decisión final del analista (Fraude / Investigación / Legítimo) en Supabase

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

Copia el archivo de ejemplo y edítalo con tus credenciales:

```bash
cp .env.example .env
```

Abre `.env` y completa los tres valores:

```
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_KEY=eyJhbGci...  ← la clave "anon public" de tu proyecto
GEMINI_API_KEY=AIzaSy...
```

**¿Dónde encuentro las credenciales de Supabase?**
Entra a tu proyecto → *Project Settings* → *API* → copia *Project URL* y *anon public key*.

**¿Y la de Gemini?**
Entra a [aistudio.google.com](https://aistudio.google.com), ve a *Get API Key* y crea una.

---

## Configurar la base de datos

Entra al **SQL Editor** de tu proyecto en Supabase, pega el contenido de `docs/schema.sql` y ejecútalo. Eso crea las 5 tablas: `asegurados`, `polizas`, `proveedores`, `siniestros` y `documentos`.

Si ya tenías una versión anterior y quieres empezar desde cero:

```sql
DROP TABLE IF EXISTS documentos, siniestros, polizas, proveedores, asegurados CASCADE;
```

Y luego vuelve a ejecutar el schema.

---

## Cargar los datos de ejemplo

El proyecto incluye un generador de datos sintéticos que crea 500 siniestros con distribución realista (15% fraude, 20% sospechoso, 65% normal):

```bash
python src/ingestion/load_data.py
```

Vas a ver algo así en la consola:

```
Generando datos sintéticos...
Siniestros guardados localmente en data/synthetic/siniestros.csv
Conectado a Supabase. Subiendo datos...
Insertando 200 registros en asegurados...
Insertando 300 registros en polizas...
Insertando 50 registros en proveedores...
Insertando 500 registros en siniestros...
Insertando 1000 registros en documentos...
Carga a Supabase completada con éxito.
```

Si las credenciales de Supabase no están configuradas, igual genera un CSV local en `data/synthetic/siniestros.csv` que la app puede usar como fallback.

---

## Ejecutar la aplicación

```bash
streamlit run src/app/main.py
```

Se abre automáticamente en `http://localhost:8501`.

---

## Demo — cómo usar la app

### Primera vez que carga

Al abrir la app por primera vez descarga los datos de Supabase y entrena los modelos. Esto tarda entre 5 y 15 segundos dependiendo del hardware. Después queda en caché y la navegación es instantánea.

### Dashboard Principal

Aquí está el resumen de todo el portafolio. Arriba aparecen los KPIs clave: cuántos siniestros hay en total, qué porcentaje está en nivel Rojo o Amarillo, y cuánto dinero está "en riesgo". Más abajo hay dos gráficos (distribución de riesgo y reclamos por ramo) y una tabla donde puedes filtrar por nivel de riesgo, ramo y rango de score.

Para una demo rápida: filtra solo los niveles Rojo y Amarillo para ver los casos que el sistema considera prioritarios.

### Detalle de Siniestro

Selecciona cualquier siniestro del dropdown (aparecen ordenados de mayor a menor score de fraude). Verás los datos básicos, el score calculado y el nivel de riesgo con color.

Haz click en **"✨ Realizar Análisis Total con Inteligencia Artificial"** y Gemini va a leer todos los datos del siniestro y generar un reporte con los factores de riesgo detectados y una conclusión ejecutiva. Desde ahí puedes descargar el reporte en PDF.

Abajo aparecen los tres botones de decisión. Cuando el analista confirma una decisión, se guarda en Supabase y queda registrado en el dashboard.

### Inspector FRAUDIA (Asistente)

Es un chat con Gemini que conoce el estado completo del portafolio. Puedes preguntarle cosas como:

- *"¿Cuáles son los 10 casos más urgentes para revisar hoy?"*
- *"¿Hay algún proveedor que aparezca en varios siniestros rojos?"*
- *"Dame un resumen ejecutivo para presentar a gerencia"*

También hay cuatro botones de preguntas sugeridas para empezar rápido.

### Métricas del Modelo

Muestra el rendimiento del Random Forest: precisión, recall, F1 y AUC-ROC. También hay un gráfico de importancia de features que te dice en qué señales se apoya más el modelo para clasificar un siniestro.

Con los 500 siniestros de ejemplo deberías ver métricas alrededor de 85-95% dependiendo de la aleatoriedad de la generación.

### Registrar Siniestro

Formulario para ingresar un siniestro nuevo en tiempo real (útil para demostrar el sistema a alguien que trae un caso de prueba). Completa los campos, haz click en "Calcular Score de Riesgo" y el sistema aplica las reglas + Gemini al instante. Si quieres guardarlo en la base de datos, aparece el botón para hacerlo.

---

## Estructura del proyecto

```
Agente-IA/
├── src/
│   ├── app/            → Aplicación Streamlit (main.py)
│   ├── ingestion/      → Generador de datos sintéticos
│   ├── models/         → Pipeline ML (Random Forest, Isolation Forest, NLP)
│   ├── rules/          → Motor de reglas de negocio (RF-01 a RF-08)
│   ├── ai_agent/       → Agente conversacional con Gemini
│   └── explainability/ → Generador de explicaciones legibles
├── data/
│   └── synthetic/      → CSV local de siniestros (fallback sin Supabase)
├── docs/
│   ├── schema.sql      → Script SQL para crear las tablas en Supabase
│   ├── arquitectura.md → Diagrama y descripción del sistema
│   ├── modelo_datos.md → Esquema detallado de tablas y campos
│   ├── uso_ia.md       → Cómo funciona cada componente de IA
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
| Base de datos | Supabase (PostgreSQL) |
| Machine Learning | scikit-learn — Random Forest, Isolation Forest, TF-IDF |
| IA Generativa | Google Gemini 2.5 Flash |
| Generación de reportes | fpdf2 |
| Datos sintéticos | Faker (locale español) |

---

## Equipo

Desarrollado por **FranGab** para el HackIAthon — Aseguradora del Sur.
