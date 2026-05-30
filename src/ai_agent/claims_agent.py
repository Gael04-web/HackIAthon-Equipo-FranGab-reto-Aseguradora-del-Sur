import os
import json
import requests
import pandas as pd
import google.generativeai as genai
from dotenv import load_dotenv

def _sb_get(table: str, select: str = "*", filters: str = "", limit: int = 500):
    """Consulta REST directa a Supabase sin supabase-py."""
    url = os.getenv("SUPABASE_URL", "").rstrip("/") + f"/rest/v1/{table}"
    key = os.getenv("SUPABASE_KEY", "")
    params = f"select={select}&limit={limit}"
    if filters:
        params += f"&{filters}"
    try:
        r = requests.get(
            url + "?" + params,
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return []

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
    Aplica las 13 reglas de negocio antifraude del sector asegurador al siniestro
    (RF-01 a RF-13: borde de vigencia, demora denuncia, frecuencia, proveedor
    restrictivo, documentos, monto atípico, narrativa, perfil de riesgo,
    chasis/motor repetido, beneficiario recurrente y reclamos RC sin tercero).
    Retorna score_reglas (puntuación acumulada), alertas (señales con su nivel de
    gravedad) y reglas_activadas (IDs disparados). Úsala como primer paso del análisis.
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
    top_k = int(top_k)
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
    global _df
    limit = min(int(limit), 20)
    data = _sb_get(
        "siniestros",
        select="id_siniestro,ramo,cobertura,monto_reclamado,dias_desde_inicio_poliza,dias_desde_fin_poliza,dias_entre_ocurrencia_reporte,historial_siniestros_asegurado,documentos_completos,descripcion",
        filters="decision_analista=eq.Fraude Confirmado",
        limit=limit,
    )
    if data:
        return data
    if not _df.empty and "decision_analista" in _df.columns:
        cols   = ["id_siniestro", "ramo", "cobertura", "monto_reclamado",
                  "dias_desde_inicio_poliza", "historial_siniestros_asegurado", "descripcion"]
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
    global _df
    data = _sb_get(
        "siniestros",
        select="id_siniestro,ramo,monto_reclamado,estado,decision_analista,fecha_ocurrencia",
        filters=f"id_asegurado=eq.{id_asegurado}",
    )
    if data:
        n_fraude = sum(1 for d in data if d.get("decision_analista") == "Fraude Confirmado")
        return {"total_siniestros": len(data), "fraudes_confirmados": n_fraude, "siniestros_recientes": data[:10]}
    if not _df.empty:
        hist = _df[_df["id_asegurado"] == id_asegurado]
        return {"total_siniestros": len(hist),
                "montos_reclamados": hist["monto_reclamado"].tolist() if "monto_reclamado" in hist.columns else []}
    return {"total_siniestros": 0}


def get_provider_risk(id_proveedor: str) -> dict:
    """
    Consulta la base de datos para obtener el perfil de riesgo de un proveedor
    (taller, clínica, médico o perito): si está en lista restrictiva,
    su motivo de restricción y el total de reclamos que ha tramitado.
    """
    global _df
    data = _sb_get("proveedores",
                   select="nombre,tipo,en_lista_restrictiva,motivo_restriccion,reclamos_asociados",
                   filters=f"id_proveedor=eq.{id_proveedor}")
    if data:
        return data[0]
    if not _df.empty:
        rows = _df[_df["id_proveedor"] == id_proveedor]
        if len(rows) > 0:
            r = rows.iloc[0]
            return {
                "nombre":               str(r.get("nombre_proveedor", "N/A")),
                "en_lista_restrictiva": bool(r.get("en_lista_restrictiva", False)),
                "reclamos_asociados":   int(r.get("reclamos_asociados_proveedor", 0)),
            }
    return {"error": "Proveedor no encontrado"}


def get_top_critical_claims(limit: int = 10) -> list:
    """
    Retorna los siniestros con mayor score de riesgo del portafolio completo.
    Úsala cuando el analista pregunta por los casos más críticos, urgentes o
    prioritarios para revisar. Incluye id, ramo, monto, score, nivel de riesgo
    y decisión actual del analista.
    """
    global _df
    limit = int(limit)
    if not _df.empty:
        cols  = ["id_siniestro", "ramo", "cobertura", "monto_reclamado",
                 "score_final", "nivel_riesgo", "decision_analista"]
        avail = [c for c in cols if c in _df.columns]
        sort_col = "score_final" if "score_final" in _df.columns else "monto_reclamado"
        return _df.sort_values(sort_col, ascending=False).head(limit)[avail].to_dict("records")
    return []


def get_all_providers_risk() -> list:
    """
    Retorna el listado completo de proveedores con sus métricas de riesgo:
    nombre, tipo, si están en lista restrictiva, porcentaje de casos observados,
    total de reclamos y ciudad. Úsala cuando el analista pregunta qué proveedores
    concentran más alertas, cuáles son más riesgosos o quiere comparar proveedores.
    Los resultados vienen ordenados de mayor a menor riesgo.
    """
    global _df, _sb
    if _sb:
        try:
            data = _sb.table("proveedores").select(
                "id_proveedor,nombre,tipo,ciudad,en_lista_restrictiva,"
                "pct_casos_observados,reclamos_asociados,antiguedad_anios"
            ).order("pct_casos_observados", desc=True).execute().data
            return data
        except Exception:
            pass
    if not _df.empty:
        prov_cols = ["id_proveedor", "nombre_proveedor", "en_lista_restrictiva",
                     "pct_casos_observados", "reclamos_asociados_proveedor"]
        avail = [c for c in prov_cols if c in _df.columns]
        if avail:
            provs = _df[avail].drop_duplicates(subset=["id_proveedor"] if "id_proveedor" in avail else avail[:1])
            sort_col = "pct_casos_observados" if "pct_casos_observados" in provs.columns else avail[0]
            return provs.sort_values(sort_col, ascending=False).to_dict("records")
    return []


def get_claims_by_filter(
    nivel_riesgo: str = "",
    ramo: str = "",
    decision_analista: str = "",
    limit: int = 20,
) -> list:
    """
    Filtra siniestros del portafolio por nivel de riesgo (Verde/Amarillo/Rojo),
    ramo (Vehiculos/Salud/Vida/Hogar) o decisión del analista
    (Pendiente/Fraude Confirmado/En Investigación/Legítimo).
    Úsala para responder preguntas como '¿cuántos casos rojos hay en Salud?'
    o '¿qué casos están pendientes de revisión?'.
    """
    global _df
    limit = int(limit)
    if not _df.empty:
        mask = pd.Series([True] * len(_df), index=_df.index)
        if nivel_riesgo and "nivel_riesgo" in _df.columns:
            mask &= _df["nivel_riesgo"] == nivel_riesgo
        if ramo and "ramo" in _df.columns:
            mask &= _df["ramo"] == ramo
        if decision_analista and "decision_analista" in _df.columns:
            mask &= _df["decision_analista"] == decision_analista
        cols = ["id_siniestro", "ramo", "cobertura", "monto_reclamado",
                "score_final", "nivel_riesgo", "decision_analista"]
        avail = [c for c in cols if c in _df.columns]
        return _df[mask][avail].head(limit).to_dict("records")
    return []


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


def get_vehicle_info(id_siniestro: str) -> dict:
    """
    Consulta los datos del vehículo asegurado en un siniestro: placa, marca,
    modelo, año, número de chasis y número de motor. También verifica si el
    mismo chasis o motor aparece en otros siniestros del portafolio, lo cual
    es señal de fraude de partes o vehículos clonados.
    """
    global _df
    # Consultar vehículo específico
    veh_data = _sb_get("vehiculos", filters=f"id_siniestro=eq.{id_siniestro}")
    if not veh_data:
        # Fallback al df si tiene columnas de vehículo
        if not _df.empty and 'chasis' in _df.columns:
            rows = _df[_df['id_siniestro'] == id_siniestro]
            if len(rows) > 0:
                r = rows.iloc[0]
                veh_data = [{"placa": r.get("placa_vehiculo"), "chasis": r.get("chasis"),
                             "motor": r.get("motor"), "marca": r.get("veh_marca")}]

    if not veh_data:
        return {"error": "Vehículo no encontrado"}

    v = veh_data[0]
    result = dict(v)

    # Verificar repetición de chasis en otros siniestros
    if v.get("chasis"):
        otros_chasis = _sb_get("vehiculos",
                               select="id_siniestro",
                               filters=f"chasis=eq.{v['chasis']}")
        otros_ids = [x['id_siniestro'] for x in otros_chasis if x['id_siniestro'] != id_siniestro]
        result["chasis_en_otros_siniestros"] = len(otros_ids)
        result["otros_siniestros_mismo_chasis"] = otros_ids

    # Verificar repetición de motor
    if v.get("motor"):
        otros_motor = _sb_get("vehiculos",
                               select="id_siniestro",
                               filters=f"motor=eq.{v['motor']}")
        otros_ids_m = [x['id_siniestro'] for x in otros_motor if x['id_siniestro'] != id_siniestro]
        result["motor_en_otros_siniestros"] = len(otros_ids_m)

    return result


def get_alerts_by_city() -> list:
    """
    Agrupa los siniestros por ciudad/sucursal y cuenta cuántos están en nivel
    de riesgo Rojo o Amarillo en cada una. Úsala cuando el analista pregunta
    qué ciudades o sucursales concentran más alertas o casos sospechosos.
    Retorna lista ordenada de mayor a menor concentración de alertas.
    """
    global _df
    if _df.empty:
        return []
    col_ciudad = "sucursal" if "sucursal" in _df.columns else ("ciudad" if "ciudad" in _df.columns else None)
    if col_ciudad is None or "nivel_riesgo" not in _df.columns:
        return []

    resultados = []
    for ciudad, grupo in _df.groupby(col_ciudad):
        total     = len(grupo)
        rojos     = int((grupo["nivel_riesgo"] == "Rojo").sum())
        amarillos = int((grupo["nivel_riesgo"] == "Amarillo").sum())
        alertas   = rojos + amarillos
        monto     = float(grupo[grupo["nivel_riesgo"].isin(["Rojo", "Amarillo"])]["monto_reclamado"].sum()) \
                    if "monto_reclamado" in grupo.columns else 0.0
        resultados.append({
            "ciudad":            str(ciudad),
            "total_siniestros":  total,
            "alertas_rojo_amarillo": alertas,
            "rojos":             rojos,
            "amarillos":         amarillos,
            "pct_alertas":       round(alertas / total * 100, 1) if total else 0,
            "monto_en_riesgo":   round(monto, 2),
        })
    return sorted(resultados, key=lambda x: x["alertas_rojo_amarillo"], reverse=True)


def get_missing_documents(solo_criticos: bool = True) -> list:
    """
    Identifica los siniestros con documentación incompleta. Si solo_criticos=True
    (por defecto) filtra solo los casos en nivel Rojo o Amarillo, que son los que
    el analista debe priorizar. Úsala cuando pregunten qué documentos faltan en
    los casos críticos o qué siniestros tienen documentación incompleta.
    Retorna id, ramo, cobertura, nivel de riesgo y los documentos que tiene el caso.
    """
    global _df
    if _df.empty or "documentos_completos" not in _df.columns:
        return []

    df = _df.copy()
    # Casos con docs incompletos
    incompletos = df[df["documentos_completos"] == False]
    if solo_criticos and "nivel_riesgo" in incompletos.columns:
        incompletos = incompletos[incompletos["nivel_riesgo"].isin(["Rojo", "Amarillo"])]

    resultados = []
    for _, r in incompletos.head(20).iterrows():
        sid = r.get("id_siniestro", "")
        # Consultar qué documentos SÍ tiene en Supabase
        docs = _sb_get("documentos", select="tipo_documento", filters=f"id_siniestro=eq.{sid}")
        tipos_presentes = [d.get("tipo_documento") for d in docs] if docs else []
        resultados.append({
            "id_siniestro":      str(sid),
            "ramo":              str(r.get("ramo", "")),
            "cobertura":         str(r.get("cobertura", "")),
            "nivel_riesgo":      str(r.get("nivel_riesgo", "")),
            "score":             float(r.get("score_final", 0)),
            "documentos_presentes": tipos_presentes,
            "nota":              "Documentación marcada como incompleta",
        })
    return resultados


# ---------------------------------------------------------------------------
# Lista de tools que Gemini puede invocar
# ---------------------------------------------------------------------------
TOOLS = [
    apply_business_rules,
    search_similar_claims,
    get_confirmed_fraud_cases,
    get_insured_history,
    get_provider_risk,
    get_all_providers_risk,
    get_top_critical_claims,
    get_claims_by_filter,
    get_vehicle_info,
    get_alerts_by_city,
    get_missing_documents,
    get_portfolio_stats,
]

SYSTEM_INSTRUCTION = """
Eres el motor central de Inteligencia Artificial de Fraudia Claims, el sistema antifraude de Aseguradora del Sur.

Tu misión es analizar siniestros de seguros y responder preguntas del analista sobre el portafolio.
Tienes acceso a las siguientes herramientas — úsalas con criterio:

HERRAMIENTAS DISPONIBLES:
- apply_business_rules: aplica las 13 reglas antifraude a un siniestro específico
- search_similar_claims: busca narrativas similares en la BD con NLP
- get_confirmed_fraud_cases: obtiene fraudes ya confirmados por humanos (para aprender)
- get_insured_history: historial de siniestros de un asegurado (por id)
- get_provider_risk: perfil de riesgo de un proveedor individual (por id)
- get_all_providers_risk: TODOS los proveedores con sus métricas, ordenados por riesgo
- get_top_critical_claims: los N siniestros con mayor score
- get_claims_by_filter: filtra siniestros por nivel_riesgo, ramo o decision_analista
- get_vehicle_info: datos del vehículo (placa, marca, modelo, año, chasis, motor) y si el chasis/motor aparece en otros siniestros → úsala siempre en siniestros de Vehículos
- get_alerts_by_city: ciudades/sucursales ordenadas por concentración de alertas → usa cuando pregunten "qué ciudades concentran más alertas/casos sospechosos"
- get_missing_documents: siniestros con documentación incompleta (por defecto solo críticos) → usa cuando pregunten "qué documentos faltan en los casos críticos"
- get_portfolio_stats: estadísticas generales del portafolio

PROCESO DE ANÁLISIS DE UN SINIESTRO:
1. apply_business_rules con los datos del caso
2. Si es ramo Vehículos: get_vehicle_info para verificar chasis/motor repetido
3. search_similar_claims con la descripción
3. get_insured_history con el id del asegurado
4. get_provider_risk con el id del proveedor
5. get_confirmed_fraud_cases para calibrar con patrones reales
6. Sintetiza todo en un score 0-100 y conclusión

SCORING:
- 0-40: Verde (proceder normal)
- 41-75: Amarillo (revisar antes de autorizar)
- 76-100: Rojo (escalar a Unidad Antifraude)

APRENDIZAJE:
Al revisar get_confirmed_fraud_cases, analiza los patrones comunes: días desde inicio de póliza,
coberturas frecuentes, montos típicos, proveedores recurrentes. Usa esos patrones para
justificar tu score con comparaciones concretas.

CONDUCTA:
- Nunca afirmes fraude directamente. Usa "posible irregularidad", "requiere revisión", "señal de alerta"
- Sé específico y cuantitativo: cita los valores exactos y compáralos con los patrones encontrados
- Si una tool te da información suficiente para responder, no llames más tools innecesariamente
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
