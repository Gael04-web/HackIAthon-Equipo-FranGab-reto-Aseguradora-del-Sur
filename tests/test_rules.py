import sys
import os
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.rules.fraud_rules import calculate_rule_score

class TestFraudRules(unittest.TestCase):
    
    def test_rf_01_borde_vigencia(self):
        # Inicio <= 10 dias (+8)
        siniestro = {"dias_desde_inicio_poliza": 5, "dias_desde_fin_poliza": 100}
        res = calculate_rule_score(siniestro)
        self.assertIn("RF-01-A", res["reglas_activadas"])
        self.assertEqual(res["score_reglas"], 8)
        
        # Fin <= 10 dias (+8)
        siniestro = {"dias_desde_inicio_poliza": 100, "dias_desde_fin_poliza": 2}
        res = calculate_rule_score(siniestro)
        self.assertIn("RF-01-C", res["reglas_activadas"])
        self.assertEqual(res["score_reglas"], 8)
        
    def test_rf_02_demora_robo(self):
        # Robo > 2 dias (+8)
        siniestro = {"cobertura": "Robo", "dias_entre_ocurrencia_reporte": 5}
        res = calculate_rule_score(siniestro)
        self.assertIn("RF-02-A", res["reglas_activadas"])
        self.assertIn("RF-06-B", res["reglas_activadas"]) # También activa reporte tardío general 4-7
        self.assertEqual(res["score_reglas"], 8 + 3)

    def test_rf_03_alta_frecuencia(self):
        # Frecuencia >= 3 (+8)
        siniestro = {"historial_siniestros_asegurado": 4}
        res = calculate_rule_score(siniestro)
        self.assertIn("RF-03-A", res["reglas_activadas"])
        self.assertEqual(res["score_reglas"], 8)
        
    def test_rf_04_proveedor_restrictivo(self):
        # Lista restrictiva (+10)
        siniestro = {"en_lista_restrictiva": True}
        res = calculate_rule_score(siniestro)
        self.assertIn("RF-04-A", res["reglas_activadas"])
        self.assertEqual(res["score_reglas"], 10)
        
    def test_rf_05_documentos(self):
        # Docs incompletos (+4)
        siniestro = {"documentos_completos": False}
        res = calculate_rule_score(siniestro)
        self.assertIn("RF-05-A", res["reglas_activadas"])
        self.assertEqual(res["score_reglas"], 4)

    def test_rf_07_monto_atipico(self):
        # Monto > 95% suma asegurada (+5)
        siniestro = {"monto_reclamado": 9600, "suma_asegurada": 10000}
        res = calculate_rule_score(siniestro)
        self.assertIn("RF-07-A", res["reglas_activadas"])
        self.assertEqual(res["score_reglas"], 5)
        
    def test_rf_08_nlp(self):
        # NLP similitud > 85% (+8)
        siniestro = {"max_similarity_nlp": 0.90, "id_siniestro_similar": "SIN-123"}
        res = calculate_rule_score(siniestro)
        self.assertIn("RF-08-A", res["reglas_activadas"])
        self.assertEqual(res["score_reglas"], 8)

    def test_rf_10_chasis_repetido(self):
        # Chasis en >= 2 siniestros distintos (+10, CRÍTICO)
        siniestro = {"chasis_en_otros_siniestros": 3}
        res = calculate_rule_score(siniestro)
        self.assertIn("RF-10-A", res["reglas_activadas"])
        self.assertEqual(res["score_reglas"], 10)

    def test_rf_11_beneficiario_recurrente(self):
        # Beneficiario en >= 3 siniestros (+8)
        siniestro = {"beneficiario_en_otros_siniestros": 4}
        res = calculate_rule_score(siniestro)
        self.assertIn("RF-11-A", res["reglas_activadas"])
        self.assertEqual(res["score_reglas"], 8)

    def test_rf_12_frecuencia_rc_sin_tercero(self):
        # > 2 reclamos RC sin tercero (+6)
        siniestro = {"reclamos_rc_sin_tercero": 3}
        res = calculate_rule_score(siniestro)
        self.assertIn("RF-12-A", res["reglas_activadas"])
        self.assertEqual(res["score_reglas"], 6)

    def test_rf_13_evento_rc_sin_tercero(self):
        # Cobertura RC + historial sin tercero (+5)
        # rc_sin_tercero=1 dispara RF-12-B (+3) y RF-13-A (+5) = 8
        siniestro = {"cobertura": "Responsabilidad Civil", "reclamos_rc_sin_tercero": 1}
        res = calculate_rule_score(siniestro)
        self.assertIn("RF-13-A", res["reglas_activadas"])
        self.assertIn("RF-12-B", res["reglas_activadas"])
        self.assertEqual(res["score_reglas"], 3 + 5)


if __name__ == '__main__':
    unittest.main()
