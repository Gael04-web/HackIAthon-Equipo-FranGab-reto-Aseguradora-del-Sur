def calculate_rule_score(siniestro_dict: dict) -> dict:
    """
    Calcula el score de reglas de negocio para un siniestro.
    Devuelve un diccionario con el score total, las alertas generadas y los IDs de reglas activadas.
    """
    score = 0
    alertas = []
    reglas = []

    # SEÑAL 1 — Borde de vigencia
    dias_inicio = siniestro_dict.get("dias_desde_inicio_poliza", 999)
    dias_fin = siniestro_dict.get("dias_desde_fin_poliza", 999)
    
    if dias_inicio <= 10:
        score += 8
        alertas.append("[ALTO] Siniestro reportado en los primeros 10 días de vigencia de la póliza (+8 pts).")
        reglas.append("RF-01-A")
    elif 11 <= dias_inicio <= 30:
        score += 4
        alertas.append("[MEDIO] Siniestro reportado en el primer mes de vigencia de la póliza (+4 pts).")
        reglas.append("RF-01-B")
        
    if dias_fin <= 10:
        score += 8
        alertas.append("[ALTO] Siniestro reportado a 10 días o menos del fin de vigencia (+8 pts).")
        reglas.append("RF-01-C")

    # SEÑAL 2 — Demora denuncia robo (solo cobertura=Robo)
    cobertura = siniestro_dict.get("cobertura", "")
    dias_reporte = siniestro_dict.get("dias_entre_ocurrencia_reporte", 0)
    
    if cobertura.lower() == "robo":
        if dias_reporte > 2:
            score += 8
            alertas.append("[ALTO] Demora mayor a 2 días en denuncia de robo (+8 pts).")
            reglas.append("RF-02-A")
        elif 1 <= dias_reporte <= 2:
            score += 4
            alertas.append("[MEDIO] Demora de 1-2 días en denuncia de robo (+4 pts).")
            reglas.append("RF-02-B")

    # SEÑAL 3 — Alta frecuencia asegurado
    historial = siniestro_dict.get("historial_siniestros_asegurado", 0)
    if historial >= 3:
        score += 8
        alertas.append(f"[ALTO] El asegurado registra alta frecuencia ({historial} siniestros previos) (+8 pts).")
        reglas.append("RF-03-A")
    elif historial == 2:
        score += 4
        alertas.append("[MEDIO] El asegurado registra 2 siniestros previos (+4 pts).")
        reglas.append("RF-03-B")

    # SEÑAL 4 — Proveedor en lista restrictiva
    lista_rest = siniestro_dict.get("en_lista_restrictiva", False)
    pct_obs = siniestro_dict.get("pct_casos_observados_proveedor", 0.0)
    reclamos_prov = siniestro_dict.get("reclamos_asociados_proveedor", 0)
    
    if lista_rest:
        score += 10
        alertas.append("[CRÍTICO] Proveedor figura en lista restrictiva (+10 pts).")
        reglas.append("RF-04-A")
    elif pct_obs > 0.2 and reclamos_prov > 2:
        score += 5
        alertas.append("[ALTO] Proveedor con alto porcentaje de casos observados (+5 pts).")
        reglas.append("RF-04-B")

    # SEÑAL 5 — Documentos incompletos
    docs_completos = siniestro_dict.get("documentos_completos", True)
    if not docs_completos:
        score += 4
        alertas.append("[MEDIO] Documentación incompleta (+4 pts).")
        reglas.append("RF-05-A")

    # SEÑAL 6 — Reporte tardío
    if dias_reporte > 7:
        score += 5
        alertas.append("[ALTO] Reporte tardío: más de 7 días desde la ocurrencia (+5 pts).")
        reglas.append("RF-06-A")
    elif 4 <= dias_reporte <= 7:
        score += 3
        alertas.append("[MEDIO] Reporte tardío: 4-7 días desde la ocurrencia (+3 pts).")
        reglas.append("RF-06-B")

    # SEÑAL 7 — Monto atípico
    monto_recl = siniestro_dict.get("monto_reclamado", 0.0)
    suma_aseg = siniestro_dict.get("suma_asegurada", 1.0)
    # Evitar division by zero si suma_aseg = 0
    if suma_aseg > 0 and monto_recl > (suma_aseg * 0.95):
        score += 5
        alertas.append("[ALTO] Monto reclamado muy cercano a la suma asegurada total (>95%) (+5 pts).")
        reglas.append("RF-07-A")

    # SEÑAL 8 — Narrativa similar (resultado del NLP)
    similitud = siniestro_dict.get("max_similarity_nlp", 0.0)
    id_similar = siniestro_dict.get("id_siniestro_similar", "N/A")
    if similitud > 0.85:
        score += 8
        alertas.append(f"[ALTO] La descripción presenta alta similitud ({int(similitud*100)}%) con el siniestro {id_similar} (+8 pts).")
        reglas.append("RF-08-A")
    elif 0.70 <= similitud <= 0.85:
        score += 4
        alertas.append(f"[MEDIO] La descripción presenta similitud moderada ({int(similitud*100)}%) con el siniestro {id_similar} (+4 pts).")
        reglas.append("RF-08-B")

    return {
        "score_reglas": score,
        "alertas": alertas,
        "reglas_activadas": reglas
    }
