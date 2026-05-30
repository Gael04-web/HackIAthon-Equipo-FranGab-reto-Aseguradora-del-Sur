def calculate_rule_score(siniestro_dict: dict) -> dict:
    """
    Calcula el score de reglas de negocio para un siniestro.
    Devuelve score_reglas, alertas y reglas_activadas.
    Calibrado para las 15 coberturas reales del dataset v2.
    """
    score   = 0
    alertas = []
    reglas  = []

    # ------------------------------------------------------------------
    # RF-01 — Borde de vigencia de póliza
    # ------------------------------------------------------------------
    dias_inicio = siniestro_dict.get("dias_desde_inicio_poliza", 999)
    dias_fin    = siniestro_dict.get("dias_desde_fin_poliza",    999)

    if dias_inicio <= 10:
        score += 8
        alertas.append("[ALTO] Siniestro en los primeros 10 días de vigencia (+8 pts).")
        reglas.append("RF-01-A")
    elif 11 <= dias_inicio <= 30:
        score += 4
        alertas.append("[MEDIO] Siniestro en el primer mes de vigencia (+4 pts).")
        reglas.append("RF-01-B")

    if dias_fin <= 10:
        score += 8
        alertas.append("[ALTO] Siniestro a 10 días o menos del vencimiento de la póliza (+8 pts).")
        reglas.append("RF-01-C")

    # ------------------------------------------------------------------
    # RF-02 — Demora en denuncia (Robo, Robo de Accesorios, Pérdida Total)
    # ------------------------------------------------------------------
    cobertura    = siniestro_dict.get("cobertura", "")
    dias_reporte = siniestro_dict.get("dias_entre_ocurrencia_reporte", 0)

    coberturas_robo = {"Robo", "Robo de Accesorios", "Pérdida Total"}
    if cobertura in coberturas_robo:
        if dias_reporte > 2:
            score += 8
            alertas.append(f"[ALTO] Demora de {dias_reporte} días en reportar '{cobertura}' (+8 pts).")
            reglas.append("RF-02-A")
        elif dias_reporte in (1, 2):
            score += 4
            alertas.append(f"[MEDIO] Demora de {dias_reporte} días en reportar '{cobertura}' (+4 pts).")
            reglas.append("RF-02-B")

    # ------------------------------------------------------------------
    # RF-03 — Alta frecuencia de siniestros del asegurado
    # ------------------------------------------------------------------
    historial = siniestro_dict.get("historial_siniestros_asegurado", 0)

    if historial >= 3:
        score += 8
        alertas.append(f"[ALTO] Asegurado con {historial} siniestros previos (+8 pts).")
        reglas.append("RF-03-A")
    elif historial == 2:
        score += 4
        alertas.append("[MEDIO] Asegurado con 2 siniestros previos (+4 pts).")
        reglas.append("RF-03-B")

    # ------------------------------------------------------------------
    # RF-04 — Proveedor en lista restrictiva
    # ------------------------------------------------------------------
    lista_rest = siniestro_dict.get("en_lista_restrictiva", False)

    if lista_rest:
        score += 10
        alertas.append("[CRÍTICO] El proveedor figura en lista restrictiva (+10 pts).")
        reglas.append("RF-04-A")

    # ------------------------------------------------------------------
    # RF-05 — Documentación incompleta
    # ------------------------------------------------------------------
    docs_completos = siniestro_dict.get("documentos_completos", True)

    if not docs_completos:
        score += 4
        alertas.append("[MEDIO] Documentación incompleta o faltante (+4 pts).")
        reglas.append("RF-05-A")

    # ------------------------------------------------------------------
    # RF-06 — Reporte tardío (aplica a todas las coberturas)
    # ------------------------------------------------------------------
    if dias_reporte > 7:
        score += 5
        alertas.append(f"[ALTO] Reporte tardío: {dias_reporte} días desde la ocurrencia (+5 pts).")
        reglas.append("RF-06-A")
    elif 4 <= dias_reporte <= 7:
        score += 3
        alertas.append(f"[MEDIO] Reporte tardío: {dias_reporte} días desde la ocurrencia (+3 pts).")
        reglas.append("RF-06-B")

    # ------------------------------------------------------------------
    # RF-07 — Monto reclamado atípico respecto a la suma asegurada
    # ------------------------------------------------------------------
    monto_recl = siniestro_dict.get("monto_reclamado", 0.0)
    suma_aseg  = siniestro_dict.get("suma_asegurada",  1.0)

    if suma_aseg > 0:
        ratio = monto_recl / suma_aseg
        if ratio > 0.95:
            score += 5
            alertas.append(f"[ALTO] Monto reclamado es el {ratio*100:.0f}% de la suma asegurada (+5 pts).")
            reglas.append("RF-07-A")
        elif ratio > 0.80:
            score += 3
            alertas.append(f"[MEDIO] Monto reclamado supera el 80% de la suma asegurada (+3 pts).")
            reglas.append("RF-07-B")

    # ------------------------------------------------------------------
    # RF-08 — Similitud de narrativa (NLP)
    # ------------------------------------------------------------------
    similitud  = siniestro_dict.get("max_similarity_nlp",   0.0)
    id_similar = siniestro_dict.get("id_siniestro_similar", "N/A")

    if similitud > 0.85:
        score += 8
        alertas.append(f"[ALTO] Descripción {int(similitud*100)}% similar al siniestro {id_similar} (+8 pts).")
        reglas.append("RF-08-A")
    elif 0.70 <= similitud <= 0.85:
        score += 4
        alertas.append(f"[MEDIO] Descripción {int(similitud*100)}% similar al siniestro {id_similar} (+4 pts).")
        reglas.append("RF-08-B")

    # ------------------------------------------------------------------
    # RF-09 — Perfil de riesgo histórico Alto (campo real del dataset)
    # ------------------------------------------------------------------
    perfil = siniestro_dict.get("perfil_riesgo", "")
    if perfil == "Alto":
        score += 6
        alertas.append("[ALTO] El asegurado tiene perfil de riesgo histórico ALTO (+6 pts).")
        reglas.append("RF-09-A")

    # ------------------------------------------------------------------
    # RF-10 — Chasis o motor repetido en múltiples siniestros
    # ------------------------------------------------------------------
    chasis_count = siniestro_dict.get("chasis_en_otros_siniestros", 0)
    motor_count  = siniestro_dict.get("motor_en_otros_siniestros",  0)

    if chasis_count >= 2:
        score += 10
        alertas.append(f"[CRÍTICO] El número de chasis aparece en {chasis_count} siniestros diferentes (+10 pts).")
        reglas.append("RF-10-A")
    elif chasis_count == 1:
        score += 5
        alertas.append("[ALTO] El número de chasis aparece en otro siniestro (+5 pts).")
        reglas.append("RF-10-B")

    if motor_count >= 1 and chasis_count == 0:
        score += 5
        alertas.append(f"[ALTO] El número de motor aparece en {motor_count} siniestro(s) adicional(es) (+5 pts).")
        reglas.append("RF-10-C")

    # ------------------------------------------------------------------
    # RF-11 — Beneficiario repetido en múltiples siniestros
    # ------------------------------------------------------------------
    beneficiario_count = siniestro_dict.get("beneficiario_en_otros_siniestros", 0)

    if beneficiario_count >= 3:
        score += 8
        alertas.append(f"[ALTO] El beneficiario aparece en {beneficiario_count} siniestros distintos (+8 pts).")
        reglas.append("RF-11-A")
    elif beneficiario_count in (1, 2):
        score += 4
        alertas.append(f"[MEDIO] El beneficiario aparece en {beneficiario_count} siniestro(s) adicional(es) (+4 pts).")
        reglas.append("RF-11-B")

    # ------------------------------------------------------------------
    # RF-12 — Alta frecuencia de reclamos RC sin tercero identificado
    # (patrón típico de siniestros simulados de Responsabilidad Civil)
    # ------------------------------------------------------------------
    rc_sin_tercero = siniestro_dict.get("reclamos_rc_sin_tercero", 0)

    if rc_sin_tercero > 2:
        score += 6
        alertas.append(f"[ALTO] El asegurado acumula {rc_sin_tercero} reclamos previos de RC sin tercero identificado (+6 pts).")
        reglas.append("RF-12-A")
    elif rc_sin_tercero == 1:
        score += 3
        alertas.append("[MEDIO] El asegurado registra 1 reclamo previo de RC sin tercero identificado (+3 pts).")
        reglas.append("RF-12-B")

    # ------------------------------------------------------------------
    # RF-13 — Evento de Responsabilidad Civil sin tercero identificado
    # (el vehículo asegurado resulta afectado pero el tercero huyó o no existe)
    # ------------------------------------------------------------------
    coberturas_rc = {"Responsabilidad Civil", "RC"}
    if cobertura in coberturas_rc and rc_sin_tercero >= 1:
        score += 5
        alertas.append("[ALTO] Siniestro de Responsabilidad Civil con patrón de eventos sin tercero identificado (+5 pts).")
        reglas.append("RF-13-A")

    return {
        "score_reglas":     score,
        "alertas":          alertas,
        "reglas_activadas": reglas,
    }
