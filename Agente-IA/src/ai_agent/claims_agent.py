import os
import json
import pandas as pd
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

class ClaimsAgent:
    def __init__(self, df_siniestros: pd.DataFrame):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key or api_key == "your_gemini_api_key_here":
            print("ADVERTENCIA: GEMINI_API_KEY no configurada. El agente no funcionará correctamente.")
        else:
            genai.configure(api_key=api_key)
            
        self.df_siniestros = df_siniestros
        self.model = genai.GenerativeModel("gemini-2.5-flash")
        self.system_context = self._build_system_context()
        self.chat = self.model.start_chat(history=[])

    def _build_system_context(self) -> str:
        """
        Construye el contexto para Gemini con un resumen estadístico del DataFrame.
        """
        df = self.df_siniestros
        
        # Resumen general
        total = len(df)
        dist_riesgo = df['nivel_riesgo'].value_counts().to_dict()
        
        # Top 5 siniestros críticos
        if 'score_final' in df.columns:
            top_siniestros_df = df.sort_values(by='score_final', ascending=False).head(5)
            # Para esto calculamos alertas en el vuelo si no están en df, o tomamos los campos clave
            from src.rules.fraud_rules import calculate_rule_score
            top_siniestros = []
            for _, row in top_siniestros_df.iterrows():
                d = row.to_dict()
                alertas = calculate_rule_score(d)["alertas"]
                top_siniestros.append({
                    "id": d["id_siniestro"][:8],
                    "score": d["score_final"],
                    "alertas": alertas
                })
        else:
            top_siniestros = []
            
        # Top proveedores con alertas (simulado contando casos de proveedores en rojos)
        rojos = df[df['nivel_riesgo'] == 'Rojo']
        top_proveedores = rojos['id_proveedor'].value_counts().head(5).to_dict() if len(rojos) > 0 else {}
        
        # Resumen por ramo
        resumen_ramo = df.groupby('ramo')['id_siniestro'].count().to_dict()
        
        context_data = {
            "total_siniestros": total,
            "distribucion_riesgo": dist_riesgo,
            "top_5_siniestros_criticos": top_siniestros,
            "top_proveedores_con_casos_rojos_count": top_proveedores,
            "resumen_por_ramo": resumen_ramo
        }
        
        system_prompt = (
            "Eres un asistente especializado en análisis antifraude para Aseguradora del Sur.\n"
            "Tu función es ayudar al analista a revisar siniestros sospechosos generando ALERTAS "
            "de revisión, no acusaciones. Siempre usa lenguaje como 'posible irregularidad', "
            "'requiere revisión', 'señal de alerta'. Nunca afirmes que un cliente cometió fraude.\n\n"
            "Datos actuales del sistema:\n"
            f"{json.dumps(context_data, indent=2, ensure_ascii=False)}\n\n"
            "Utiliza este contexto para responder a las preguntas del analista. "
            "Cuando se te pregunte por IDs, asume que se refieren a los que tienes en el top 5 o los prefijos."
        )
        return system_prompt

    def ask(self, pregunta: str) -> str:
        try:
            prompt = f"{self.system_context}\n\nPregunta del analista: {pregunta}"
            response = self.chat.send_message(prompt)
            return response.text
        except Exception as e:
            return f"Error al comunicarse con Gemini: {str(e)}"

    def reset(self):
        """Reinicia el historial del chat."""
        self.chat = self.model.start_chat(history=[])

    def analyze_single_claim(self, claim_data: dict) -> str:
        """
        Analiza un único siniestro haciendo que Gemini redacte todas las alertas y la conclusión.
        """
        prompt = (
            "Eres el motor central de Inteligencia Artificial (Gemini 2.5 Flash) de Aseguradora del Sur.\n"
            "Tu tarea es analizar los datos de un siniestro y generar un reporte detallado.\n"
            f"DATOS DEL SINIESTRO: {str(claim_data)}\n\n"
            "Por favor, redacta tu análisis estructurado exactamente en dos partes:\n\n"
            "### 🚨 Factores de Riesgo Detectados por la IA\n"
            "(Crea una lista de viñetas mencionando las cosas sospechosas que encuentres en los datos, por ejemplo: "
            "si los días desde inicio de póliza son muy pocos, si el monto reclamado es casi igual a la suma asegurada, "
            "si el historial de siniestros es alto, o si faltan documentos. Si el score_riesgo_calculado es alto, menciónalo como un patrón anómalo detectado).\n\n"
            "### 📋 Conclusión Ejecutiva\n"
            "(Un párrafo resumiendo tu recomendación: si el caso parece un fraude o si es seguro proceder con el pago)."
        )
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Error generando resumen con IA: {str(e)}"
