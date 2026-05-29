import os
import json
import pandas as pd
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Estado global accesible por las tools (se inicializa en ClaimsAgent.__init__)
# ---------------------------------------------------------------------------
_df: pd.DataFrame = pd.DataFrame()
_sb = None  # cliente Supabase


# ---------------------------------------------------------------------------
# TOOLS — Gemini decide cuándo y cómo usar cada una
# ---------------------------------------------------------------------------

def apply_business_rules(
    dias_desde_inicio_poliza: int = 999,
    dias_desde_fin_poliza: int = 999,
    dias_entre_ocurrencia_reporte: int = 0,
    monto_reclamado: float = 0.0,
    suma_asegurada: float = 1.0,
    historial_siniestros_asegurado: int = 0,
    documentos_completos: bool = True,
    en_lista_restrictiva: bool = False,
    pct_casos_observados_proveedor: float = 0.0,
    reclamos_asociados_proveedor: int = 0,
    cobertura: str = "",
    max_similarity_nlp: float = 0.0,
    id_siniestro_similar: str = "N/A",
) -> dict:
    """
    Aplica las 8 reglas de negocio antifraude del sector asegurador al siniestro.
    Retorna score_reglas (puntuación acumulada 0-64), alertas (lista de señales
    detectadas con su nivel de gravedad) y reglas_activadas (IDs disparados).
    Úsala siempre como primer paso del análisis.
    """
    from src.rules.fraud_rules import calculate_rule_score
    return calculate_rule_score({
        "dias_desde_inicio_poliza":       dias_desde_inicio_poliza,
        "dias_desde_fin_poliza":          dias_desde_fin_poliza,
        "dias_entre_ocurrencia_reporte":  dias_entre_ocurrencia_reporte,
        "monto_reclamado":                monto_reclamado,
        "suma_asegurada":                 suma_asegurada,
        "historial_siniestros_asegurado": historial_siniestros_asegurado,
        "documentos_completos":           documentos_completos,
        "en_lista_restrictiva":           en_lista_restrictiva,
        "pct_casos_observados_proveedor": pct_casos_observados_proveedor,
        "reclamos_asociados_proveedor":   reclamos_asociados_proveedor,
        "cobertura":                      cobertura,
        "max_similarity_nlp":             max_similarity_nlp,
        "id_siniestro_similar":           id_siniestro_similar,
    })


def search_similar_claims(description: str, top_k: int = 5) -> list:
    """
    Busca en la base de datos histórica los siniestros cuyas descripciones sean
    más similares a la descripción dada usando NLP (TF-IDF + cosine similarity).
    Úsala para detectar si alguien copió una narrativa de fraude conocida.
    Retorna lista con id_siniestro, similitud_pct, descripcion, decision_analista
    y nivel_riesgo de cada caso similar encontrado.
    """
    global _df
    if _df.empty or "descripcion" not in _df.columns:
        return []
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    textos = _df["descripcion"].fillna("").tolist()
    try:
        vec  = TfidfVectorizer(stop_words=None).fit_transform(textos + [description])
        sims = cosine_similarity(vec[-1], vec[:-1])[0]
        idxs = sims.argsort()[-(top_k):][::-1]
        results = []
        for i in idxs:
            if sims[i] > 0.05:
                r = _df.iloc[i]
                results.append({
                    "id_siniestro":     str(r.get("id_siniestro", ""))[:8],
                    "similitud_pct":    round(float(sims[i]) * 100, 1),
                    "descripcion":      str(r.get("descripcion", ""))[:200],
                    "decision_analista": str(r.get("decision_analista", "Pendiente")),
                    "nivel_riesgo":     str(r.get("nivel_riesgo", "N/A")),
                    "score_ml":         float(r.get("score_final", 0)),
                })
        return results
    except Exception:
        return []


def get_confirmed_fraud_cases(limit: int = 15) -> list:
    """
    Consulta la base de datos para obtener casos que analistas humanos ya
    confirmaron como fraude (decision_analista = 'Fraude Confirmado').
    Úsala para aprender de los patrones de fraude ya validados y calibrar
    tu score. Retorna los campos clave de cada caso confirmado.
    """
    global _df, _sb
    limit = min(limit, 20)
    if _sb:
        try:
            data = _sb.table("siniestros").select(
                "id_siniestro,ramo,cobertura,monto_reclamado,dias_desde_inicio_poliza,"
                "dias_desde_fin_poliza,dias_entre_ocurrencia_reporte,"
                "historial_siniestros_asegurado,documentos_completos,descripcion"
            ).eq("decision_analista", "Fraude Confirmado").limit(limit).execute().data
            return data
        except Exception:
            pass
    if not _df.empty and "decision_analista" in _df.columns:
        cols = [
            "id_siniestro", "ramo", "cobertura", "monto_reclamado",
            "dias_desde_inicio_poliza", "historial_siniestros_asegurado", "descripcion",
        ]
        frauds = _df[_df["decision_analista"] == "Fraude Confirmado"].head(limit)
        avail  = [c for c in cols if c in frauds.columns]
        return frauds[avail].to_dict("records")
    return []


def get_insured_history(id_asegurado: str) -> dict:
    """
    Consulta el historial completo de siniestros de un asegurado en la base de datos.
    Retorna total de siniestros, cuántos fueron confirmados como fraude,
    montos reclamados y estados. Úsala para detectar asegurados reincidentes.
    """
    global _df, _sb
    if _sb:
        try:
            data = _sb.table("siniestros").select(
                "id_siniestro,ramo,monto_reclamado,estado,decision_analista,fecha_ocurrencia"
            ).eq("id_asegurado", id_asegurado).execute().data
            n_fraude = sum(1 for d in data if d.get("decision_analista") == "Fraude Confirmado")
            return {
                "total_siniestros":   len(data),
                "fraudes_confirmados": n_fraude,
                "siniestros_recientes": data[:10],
            }
        except Exception:
            pass
    if not _df.empty:
        hist = _df[_df["id_asegurado"] == id_asegurado]
        return {
            "total_siniestros":  len(hist),
            "montos_reclamados": hist["monto_reclamado"].tolist() if "monto_reclamado" in hist.columns else [],
        }
    return {"total_siniestros": 0}


def get_provider_risk(id_proveedor: str) -> dict:
    """
    Consulta la base de datos para obtener el perfil de riesgo de un proveedor
    (taller, clínica, médico o perito): si está en lista restrictiva, su porcentaje
    de casos con irregularidades y el total de reclamos que ha tramitado.
    """
    global _df, _sb
    if _sb:
        try:
            data = _sb.table("proveedores").select(
                "nombre,tipo,en_lista_restrictiva,pct_casos_observados,reclamos_asociados,antiguedad_anios"
            ).eq("id_proveedor", id_proveedor).execute().data
            return data[0] if data else {"error": "Proveedor no encontrado"}
        except Exception:
            pass
    if not _df.empty:
        rows = _df[_df["id_proveedor"] == id_proveedor]
        if len(rows) > 0:
            r = rows.iloc[0]
            return {
                "nombre":                 str(r.get("nombre_proveedor", "N/A")),
                "en_lista_restrictiva":   bool(r.get("en_lista_restrictiva", False)),
                "pct_casos_observados":   float(r.get("pct_casos_observados", 0)),
                "reclamos_asociados":     int(r.get("reclamos_asociados_proveedor", 0)),
            }
    return {"error": "Proveedor no encontrado"}


def get_portfolio_stats() -> dict:
    """
    Retorna estadísticas generales del portafolio: total de siniestros,
    distribución por nivel de riesgo, monto en riesgo, distribución por ramo
    y cantidad de fraudes ya confirmados. Úsala para contextualizar el análisis
    de un caso individual respecto al resto del portafolio.
    """
    global _df
    if _df.empty:
        return {}
    df = _df
    return {
        "total_siniestros":    len(df),
        "distribucion_riesgo": df["nivel_riesgo"].value_counts().to_dict() if "nivel_riesgo" in df.columns else {},
        "monto_total_en_riesgo": float(
            df[df.get("nivel_riesgo", pd.Series(["Verde"] * len(df))).isin(["Rojo", "Amarillo"])]["monto_reclamado"].sum()
        ) if "monto_reclamado" in df.columns else 0,
        "por_ramo":            df["ramo"].value_counts().to_dict() if "ramo" in df.columns else {},
        "fraudes_confirmados": int((df.get("decision_analista", pd.Series(["Pendiente"] * len(df))) == "Fraude Confirmado").sum()),
    }


# ---------------------------------------------------------------------------
# Lista de tools que Gemini puede invocar
# ---------------------------------------------------------------------------
TOOLS = [
    apply_business_rules,
    search_similar_claims,
    get_confirmed_fraud_cases,
    get_insured_history,
    get_provider_risk,
    get_portfolio_stats,
]

SYSTEM_INSTRUCTION = """
Eres el motor central de Inteligencia Artificial de Fraudia Claims, el sistema antifraude de Aseguradora del Sur.

Tu misión es analizar siniestros de seguros para detectar posibles fraudes. Tienes acceso a herramientas que te permiten consultar la base de datos en tiempo real, aplicar reglas de negocio, buscar narrativas similares y aprender de los casos que analistas humanos ya confirmaron como fraude.

PROCESO OBLIGATORIO DE ANÁLISIS:
1. Aplica siempre las reglas de negocio (apply_business_rules) para obtener señales objetivas
2. Busca siniestros con descripciones similares (search_similar_claims) para detectar narrativas copiadas
3. Consulta el historial del asegurado (get_insured_history) para detectar reincidencia
4. Consulta el perfil del proveedor (get_provider_risk) para evaluar su historial
5. Revisa casos de fraude ya confirmados (get_confirmed_fraud_cases) para calibrar tu juicio comparando patrones
6. Opcionalmente, consulta el contexto del portafolio (get_portfolio_stats) para contextualizar

CÓMO CALCULAR EL SCORE:
Basado en toda la evidencia recopilada, asigna un score de 0 a 100 donde:
- 0-40: Verde — riesgo bajo, proceder con flujo normal de pago
- 41-75: Amarillo — revisión necesaria antes de autorizar
- 76-100: Rojo — alto riesgo, escalar a Unidad Antifraude

CÓMO APRENDER DE LOS DATOS:
Cuando consultes los casos confirmados como fraude, analiza sus patrones:
¿Qué tienen en común? ¿Qué días desde inicio de póliza son típicos? ¿Qué coberturas aparecen más?
¿Qué proveedores están involucrados? Usa esos patrones para calibrar el score del caso actual.

REGLAS DE CONDUCTA:
- Nunca afirmes que un cliente cometió fraude. Usa siempre lenguaje como "posible irregularidad", "requiere revisión", "señal de alerta"
- Tu score debe estar justificado por evidencia concreta de las herramientas que usaste
- Sé específico: no digas "el monto es sospechoso", di "el monto reclamado ($9.800) representa el 98% de la suma asegurada ($10.000), patrón presente en X de los últimos fraudes confirmados"
"""


# ---------------------------------------------------------------------------
# Clase principal
# ---------------------------------------------------------------------------

class ClaimsAgent:
    def __init__(self, df_siniestros: pd.DataFrame, supabase_client=None):
        global _df, _sb
        _df = df_siniestros
        _sb = supabase_client

        api_key = os.getenv("GEMINI_API_KEY")
        self._configured = bool(api_key and "gemini_api_key" not in api_key.lower())
        if self._configured:
            genai.configure(api_key=api_key)
        else:
            print("ADVERTENCIA: GEMINI_API_KEY no configurada. El agente no funcionará.")

        self.model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            tools=TOOLS,
            system_instruction=SYSTEM_INSTRUCTION,
        )
        # Chat persistente para el asistente conversacional
        self.chat = self.model.start_chat(enable_automatic_function_calling=True)

    def _execute_tool(self, name: str, args: dict):
        """Ejecuta una tool por nombre y retorna el resultado."""
        tool_map = {f.__name__: f for f in TOOLS}
        fn = tool_map.get(name)
        if fn is None:
            return {"error": f"Tool desconocida: {name}"}
        try:
            return fn(**args)
        except Exception as e:
            return {"error": str(e)}

    def _run_agentic_loop(self, prompt: str) -> str:
        """
        Loop agentico manual: envía el prompt, ejecuta las tools que Gemini solicite
        y repite hasta obtener una respuesta de texto final.
        Compatible con todas las versiones del SDK.
        """
        # Chat fresco para cada análisis (sin historial previo contaminando)
        analysis_chat = self.model.start_chat()
        response = analysis_chat.send_message(prompt)

        max_rounds = 10  # evitar loops infinitos
        for _ in range(max_rounds):
            # Buscar function calls en la respuesta
            parts = response.candidates[0].content.parts
            fn_calls = [p for p in parts if p.function_call.name]

            if not fn_calls:
                # Gemini terminó — retornar texto final
                return response.text

            # Ejecutar cada tool y preparar respuestas
            fn_responses = []
            for part in fn_calls:
                fc     = part.function_call
                result = self._execute_tool(fc.name, dict(fc.args))
                fn_responses.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=fc.name,
                            response={"result": json.dumps(result, ensure_ascii=False, default=str)},
                        )
                    )
                )

            # Enviar resultados de vuelta a Gemini
            response = analysis_chat.send_message(fn_responses)

        return response.text

    def analyze_single_claim(self, claim_data: dict) -> dict:
        """
        Análisis profundo y autónomo de un siniestro.
        Gemini decide qué herramientas usar, consulta la BD, aprende de fraudes
        confirmados y produce su propio score con justificación completa.

        Retorna:
            score (int 0-100): score calculado por Gemini
            nivel_riesgo (str): Verde / Amarillo / Rojo
            factores (list[str]): factores de riesgo detectados
            conclusion (str): conclusión ejecutiva redactada
            herramientas_usadas (list[str]): tools que Gemini invocó
        """
        if not self._configured:
            return {
                "score": 0, "nivel_riesgo": "N/A",
                "factores": [], "conclusion": "GEMINI_API_KEY no configurada. Revisa el archivo .env",
                "herramientas_usadas": [],
            }

        prompt = f"""Analiza el siguiente siniestro y determina su nivel de riesgo de fraude.

DATOS DEL SINIESTRO:
{json.dumps(claim_data, ensure_ascii=False, indent=2, default=str)}

Sigue el proceso completo: aplica reglas, busca similares, consulta historial del asegurado
(id_asegurado: {claim_data.get('id_asegurado', 'N/A')}), perfil del proveedor
(id_proveedor: {claim_data.get('id_proveedor', 'N/A')}), y revisa fraudes confirmados
para aprender de ellos antes de emitir tu score.

Al terminar tu análisis incluye EXACTAMENTE este bloque en una línea (sin markdown):
SCORE_JSON:{{"score": <0-100>, "nivel_riesgo": "<Verde|Amarillo|Rojo>", "factores": ["factor1","factor2","factor3"], "conclusion": "<párrafo ejecutivo>"}}
"""

        try:
            full_text = self._run_agentic_loop(prompt)

            # Parsear el JSON estructurado del score
            result = {
                "score": 50, "nivel_riesgo": "Amarillo",
                "factores": [], "conclusion": full_text,
                "herramientas_usadas": [f.__name__ for f in TOOLS],
            }
            if "SCORE_JSON:" in full_text:
                try:
                    json_str = full_text.split("SCORE_JSON:")[1].strip().split("\n")[0]
                    parsed   = json.loads(json_str)
                    result["score"]        = int(parsed.get("score", 50))
                    result["nivel_riesgo"] = parsed.get("nivel_riesgo", "Amarillo")
                    result["factores"]     = parsed.get("factores", [])
                    result["conclusion"]   = parsed.get("conclusion", full_text.split("SCORE_JSON:")[0].strip())
                except Exception:
                    result["conclusion"] = full_text.split("SCORE_JSON:")[0].strip()

            return result

        except Exception as e:
            return {
                "score": 0, "nivel_riesgo": "N/A", "factores": [],
                "conclusion": f"Error al comunicarse con Gemini: {str(e)}",
                "herramientas_usadas": [],
            }

    def ask(self, pregunta: str) -> str:
        """
        Chat libre con el agente sobre el portafolio.
        Mantiene historial de la conversación y puede usar todas las tools.
        """
        if not self._configured:
            return "GEMINI_API_KEY no configurada. Verifica tu archivo .env"
        try:
            response = self.chat.send_message(pregunta)
            return response.text
        except Exception as e:
            return f"Error al comunicarse con Gemini: {str(e)}"

    def reset(self):
        """Reinicia el historial del chat conversacional."""
        self.chat = self.model.start_chat(enable_automatic_function_calling=True)
