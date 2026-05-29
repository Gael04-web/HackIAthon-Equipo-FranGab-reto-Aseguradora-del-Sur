FROM python:3.11-slim

# Evitar que Python genere archivos .pyc
ENV PYTHONDONTWRITEBYTECODE=1
# Evitar buffering para ver logs en tiempo real
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencias del sistema necesarias para scikit-learn y fpdf2
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el proyecto completo (incluye data/dataset/ con el Excel)
COPY . .

# Generar el CSV de fallback a partir del dataset real durante el build.
# Si el Excel no existe, el script falla con un mensaje claro.
# Supabase NO se usa aquí (solo genera el CSV local para fallback).
RUN python src/ingestion/load_data.py || echo "⚠️  CSV no generado: coloca el Excel en data/dataset/ antes de hacer docker build"

# Puerto de Streamlit
EXPOSE 8501

CMD ["streamlit", "run", "src/app/main.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
