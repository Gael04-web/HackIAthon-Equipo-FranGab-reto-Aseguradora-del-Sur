# Fraudia Claims

Prototipo de detección de posibles fraudes en siniestros de seguros para Aseguradora del Sur. Desarrollado como parte de un Hackathon de 24 horas.

## Tecnologías
- Python 3.11+
- Supabase (PostgreSQL)
- Streamlit
- Scikit-learn (Random Forest, Isolation Forest, TF-IDF, Cosine Similarity)
- Gemini 1.5 Flash (Google Generative AI)

## Instalación

1. Clona el repositorio.
2. Instala las dependencias:
   ```bash
   pip install -r requirements.txt
   ```
3. Copia el archivo de entorno y configura tus variables:
   ```bash
   cp .env.example .env
   ```
   Rellena `.env` con tus credenciales de Supabase y Gemini.

## Carga de Datos y Base de Datos

1. **Configurar Supabase**: Ejecuta el script SQL en `docs/schema.sql` en el SQL Editor de tu proyecto de Supabase.
2. **Generar Datos Sintéticos**: Ejecuta el siguiente comando para generar y subir datos a Supabase. Se guardará una copia local en `data/synthetic/siniestros.csv` por si falla Supabase.
   ```bash
   python src/ingestion/load_data.py
   ```

## Ejecución de la Aplicación

Inicia el dashboard principal con Streamlit:
```bash
streamlit run src/app/main.py
```
