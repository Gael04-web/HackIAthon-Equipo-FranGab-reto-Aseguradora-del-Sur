"""
Utilidades para localizar, mostrar y analizar con IA los PDFs del dataset.

Fuentes soportadas (en orden de prioridad):
  1. URL pública de Supabase Storage  (url_pdf en tabla documentos)
  2. Archivo local en data/docs/      (fallback sin internet)
"""
import os
import base64
import glob
import requests as req

_BASE       = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
DOCS_FOLDER = os.path.join(_BASE, "data", "docs")

DOC_TYPES = {
    "DA_":               "📋 Declaración de Accidente",
    "PP_":               "🚔 Parte Policial",
    "Muestras_Facturas": "🧾 Factura de Reparación",
}


# ---------------------------------------------------------------------------
# Localizar documentos
# ---------------------------------------------------------------------------

def get_docs_for_siniestro(id_siniestro: str, sb_docs: list = None) -> list[dict]:
    """
    Retorna los documentos disponibles para un siniestro.

    Args:
        id_siniestro: p.ej. "SIN-0001"
        sb_docs: lista de registros de la tabla `documentos` de Supabase
                 (si se pasa, se usa para obtener url_pdf directamente)

    Returns:
        Lista de dicts: {nombre, tipo, url, source}
          source = "supabase" | "local"
    """
    found = []

    # 1) Desde Supabase Storage (url_pdf)
    if sb_docs:
        for doc in sb_docs:
            if doc.get("id_siniestro") != id_siniestro:
                continue
            url = doc.get("url_pdf", "")
            nombre = doc.get("nombre_archivo", "") or doc.get("id_documento", "")
            if not url:
                continue
            tipo = _detect_type(nombre)
            found.append({
                "nombre": nombre,
                "tipo":   tipo,
                "url":    url,
                "source": "supabase",
            })

    # 2) Fallback: archivos locales en data/docs/
    if not found and os.path.exists(DOCS_FOLDER):
        for pdf_path in glob.glob(os.path.join(DOCS_FOLDER, "*.pdf")):
            nombre = os.path.basename(pdf_path)
            if id_siniestro in nombre:
                found.append({
                    "nombre": nombre,
                    "tipo":   _detect_type(nombre),
                    "url":    None,
                    "path":   pdf_path,
                    "source": "local",
                })

    return sorted(found, key=lambda x: x["tipo"])


def _detect_type(nombre: str) -> str:
    for prefix, label in DOC_TYPES.items():
        if nombre.startswith(prefix):
            return label
    return "📄 Documento"


# ---------------------------------------------------------------------------
# Obtener bytes del PDF (URL o local)
# ---------------------------------------------------------------------------

def get_pdf_bytes(doc: dict) -> bytes:
    """Descarga o lee el PDF y retorna sus bytes."""
    if doc.get("source") == "supabase" and doc.get("url"):
        resp = req.get(doc["url"], timeout=20)
        resp.raise_for_status()
        return resp.content
    elif doc.get("path"):
        with open(doc["path"], "rb") as f:
            return f.read()
    raise ValueError(f"No hay fuente disponible para el documento: {doc.get('nombre')}")


# ---------------------------------------------------------------------------
# Renderizado en Streamlit
# ---------------------------------------------------------------------------

def render_pdf_iframe(doc: dict, height: int = 620) -> str:
    """
    Genera HTML iframe para mostrar el PDF.
    Si hay URL de Supabase la usa directamente.
    Si es local la convierte a base64.
    """
    if doc.get("source") == "supabase" and doc.get("url"):
        # URL pública → iframe directo (sin base64, más rápido)
        url = doc["url"]
        return (
            f'<iframe src="{url}" width="100%" height="{height}px" '
            f'style="border:none;border-radius:8px;"></iframe>'
        )
    else:
        # Archivo local → base64
        pdf_bytes = get_pdf_bytes(doc)
        b64 = base64.b64encode(pdf_bytes).decode("utf-8")
        return (
            f'<iframe src="data:application/pdf;base64,{b64}" '
            f'width="100%" height="{height}px" '
            f'style="border:none;border-radius:8px;"></iframe>'
        )


# ---------------------------------------------------------------------------
# Análisis con Gemini
# ---------------------------------------------------------------------------

def analyze_pdf_with_gemini(doc: dict, siniestro_data: dict, model) -> str:
    """
    Envía el PDF a Gemini y solicita análisis de inconsistencias
    comparando el contenido del documento con los datos registrados.
    """
    import google.generativeai as genai

    nombre = doc.get("nombre", "")
    pdf_bytes = get_pdf_bytes(doc)

    if nombre.startswith("DA_"):
        tipo = "Declaración de Accidente"
        checks = (
            "- ¿La fecha del accidente en el documento coincide con 'fecha_ocurrencia'?\n"
            "- ¿La placa del vehículo coincide con 'placa_vehiculo'?\n"
            "- ¿La descripción es coherente con la cobertura registrada?\n"
            "- ¿Hay indicios de alteración en el documento?"
        )
    elif nombre.startswith("PP_"):
        tipo = "Parte Policial"
        checks = (
            "- ¿El número de parte coincide con 'numero_parte_policial'?\n"
            "- ¿La fecha de la denuncia es coherente con 'fecha_ocurrencia'?\n"
            "- ¿Las circunstancias descritas coinciden con los datos del siniestro?\n"
            "- ¿Hay nombres, lugares o fechas inconsistentes?"
        )
    else:
        tipo = "Factura de Reparación"
        checks = (
            "- ¿El monto total de la factura es coherente con 'monto_reclamado'?\n"
            "- ¿La fecha de la factura es posterior a 'fecha_ocurrencia'?\n"
            "- ¿El nombre del taller coincide con el proveedor registrado?\n"
            "- ¿Los ítems facturados corresponden al tipo de daño reportado?\n"
            "- ¿Hay signos de alteración: montos borrados, fechas sobreescritas?"
        )

    prompt = f"""Eres un perito antifraude de Aseguradora del Sur analizando documentos de siniestros.

TIPO DE DOCUMENTO: {tipo}
ARCHIVO: {nombre}

DATOS REGISTRADOS DEL SINIESTRO:
- ID: {siniestro_data.get('id_siniestro', 'N/A')}
- Ramo: {siniestro_data.get('ramo', 'N/A')} | Cobertura: {siniestro_data.get('cobertura', 'N/A')}
- Fecha Ocurrencia: {siniestro_data.get('fecha_ocurrencia', 'N/A')}
- Fecha Reporte: {siniestro_data.get('fecha_reporte', 'N/A')}
- Monto Reclamado: ${siniestro_data.get('monto_reclamado', 0):,.2f}
- Monto Estimado: ${siniestro_data.get('monto_estimado', 0):,.2f}
- Placa Vehículo: {siniestro_data.get('placa_vehiculo', 'N/A')}
- N° Parte Policial: {siniestro_data.get('numero_parte_policial', 'N/A')}
- Proveedor: {siniestro_data.get('nombre_proveedor', 'N/A')}
- Descripción registrada: {siniestro_data.get('descripcion', 'N/A')}

PUNTOS A VERIFICAR:
{checks}

Redacta tu análisis en dos partes:

### 📄 Contenido del Documento
(Resume los datos principales que encuentras en el PDF)

### ⚠️ Inconsistencias Detectadas
(Lista las discrepancias encontradas. Si todo es consistente, dilo claramente.)
Usa siempre lenguaje de "posible irregularidad" o "requiere verificación", nunca afirmes fraude directamente.
"""

    try:
        import google.ai.generativelanguage as glm
        response = model.generate_content([
            glm.Part(inline_data=glm.Blob(mime_type="application/pdf", data=pdf_bytes)),
            glm.Part(text=prompt),
        ])
        return response.text
    except Exception as e1:
        try:
            import google.generativeai.types as gtypes
            response = model.generate_content([
                gtypes.Part(inline_data=gtypes.Blob(mime_type="application/pdf", data=pdf_bytes)),
                prompt,
            ])
            return response.text
        except Exception as e2:
            return f"Error al analizar el documento con Gemini: {e2}"
