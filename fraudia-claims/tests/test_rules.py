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

if __name__ == '__main__':
    unittest.main()
