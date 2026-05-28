from src.rules.fraud_rules import calculate_rule_score

def explain_score(siniestro_row: dict) -> str:
    """
    Genera un párrafo legible explicando el nivel de riesgo y los factores que lo activaron.
    siniestro_row debe contener datos del siniestro enriquecidos con modelos (score_final, nivel_riesgo).
    """
    id_sin = siniestro_row.get("id_siniestro", "N/A")[:8] # Mostramos un ID corto
    nivel = siniestro_row.get("nivel_riesgo", "Desconocido").upper()
    score = int(siniestro_row.get("score_final", 0))
    
    # Recalcular reglas para obtener las alertas exactas
    # (También podríamos pasarlas ya calculadas en el dict, pero esto asegura consistencia)
    res_reglas = calculate_rule_score(siniestro_row)
    alertas = res_reglas["alertas"]
    
    explicacion = f"El siniestro {id_sin} fue clasificado como {nivel} (score: {score}/100) por los siguientes factores:\n\n"
    
    if alertas:
        for alerta in alertas:
            explicacion += f"- {alerta}\n"
    else:
        explicacion += "- No se detectaron alertas críticas en reglas de negocio.\n"
        
    # Añadir info del modelo RF e IF si contribuyeron mucho
    prob_rf = siniestro_row.get("prob_rf", 0.0)
    if prob_rf > 0.6:
        explicacion += f"- [ALTO] El modelo predictivo indica alta probabilidad ({int(prob_rf*100)}%) basada en patrones históricos.\n"
        
    anomaly = siniestro_row.get("anomaly_score", 0.0)
    if anomaly > 0.8:
        explicacion += f"- [MEDIO] Anomalía detectada en los datos en comparación al comportamiento habitual del portafolio.\n"

    explicacion += "\nRecomendación: "
    if nivel == "ROJO":
        explicacion += "Escalar inmediatamente a la Unidad Antifraude para revisión especializada de campo."
    elif nivel == "AMARILLO":
        explicacion += "Requiere revisión adicional por el analista de siniestros antes de autorizar pagos."
    else:
        explicacion += "Procesar pago por flujo estándar."
        
    return explicacion
