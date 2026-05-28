import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.model_selection import train_test_split
from sklearn.metrics import precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix

class FraudModelPipeline:
    def __init__(self, df: pd.DataFrame):
        """
        Inicializa el pipeline con el DataFrame que debe contener toda la info (unión de siniestros, pólizas, proveedores).
        """
        self.df = df.copy()
        # Asegurar booleanos numéricos
        if 'documentos_completos' in self.df.columns:
            self.df['documentos_completos_num'] = self.df['documentos_completos'].astype(int)
        if 'en_lista_restrictiva' in self.df.columns:
            self.df['en_lista_restrictiva_num'] = self.df['en_lista_restrictiva'].astype(int)
            
        self.tfidf = TfidfVectorizer(stop_words='english')
        self.rf = RandomForestClassifier(n_estimators=100, class_weight='balanced', random_state=42)
        self.iso = IsolationForest(contamination=0.15, random_state=42)
        
        self.metrics = {}
        self.feature_importances = None
        self.features = [
            'dias_desde_inicio_poliza', 'dias_desde_fin_poliza', 'dias_entre_ocurrencia_reporte',
            'monto_reclamado', 'monto_estimado', 'historial_siniestros_asegurado',
            'documentos_completos_num', 'pct_casos_observados', 'en_lista_restrictiva_num',
            'score_reglas', 'max_similarity_nlp'
        ]

    def _calc_nlp_similarity(self):
        """
        Calcula TF-IDF y cosine similarity para encontrar descripciones similares.
        """
        # Rellenar nulos
        textos = self.df['descripcion'].fillna("")
        tfidf_matrix = self.tfidf.fit_transform(textos)
        cosine_sim = cosine_similarity(tfidf_matrix)
        
        # Para cada documento, el max similarity con OTRO documento
        np.fill_diagonal(cosine_sim, 0)
        
        max_sims = cosine_sim.max(axis=1)
        # Índice del más similar
        max_indices = cosine_sim.argmax(axis=1)
        
        self.df['max_similarity_nlp'] = max_sims
        # Guardar ID del similar
        ids = self.df['id_siniestro'].values
        self.df['id_siniestro_similar'] = [ids[i] for i in max_indices]
        
    def _run_rules(self):
        """Asegura que el df tenga score_reglas si no fue precalculado."""
        from src.rules.fraud_rules import calculate_rule_score
        scores = []
        for _, row in self.df.iterrows():
            d = row.to_dict()
            if 'pct_casos_observados' in d: d['pct_casos_observados_proveedor'] = d['pct_casos_observados']
            res = calculate_rule_score(d)
            scores.append(res['score_reglas'])
        self.df['score_reglas'] = scores

    def train_models(self):
        """
        Entrena NLP, Reglas, RF e IF.
        """
        # 1. Preparar features (NLP y Reglas)
        self._calc_nlp_similarity()
        if 'score_reglas' not in self.df.columns:
            self._run_rules()
            
        # Limpiar posibles nulos en features
        for f in self.features:
            if f not in self.df.columns:
                self.df[f] = 0
            self.df[f] = self.df[f].fillna(0)

        X = self.df[self.features]
        y = self.df['etiqueta_fraude_simulada']

        # 2. Random Forest
        try:
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
        except ValueError:
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        self.rf.fit(X_train, y_train)
        
        # Métricas RF
        y_pred = self.rf.predict(X_test)
        probas_test = self.rf.predict_proba(X_test)
        if probas_test.shape[1] == 1:
            y_prob = np.zeros(X_test.shape[0]) if self.rf.classes_[0] == 0 else np.ones(X_test.shape[0])
        else:
            y_prob = probas_test[:, 1]
        
        try:
            auc = roc_auc_score(y_test, y_prob)
        except ValueError:
            auc = 0.0 # Ocurre si hay solo 1 clase en el test set
            
        self.metrics = {
            'precision': precision_score(y_test, y_pred, zero_division=0),
            'recall': recall_score(y_test, y_pred, zero_division=0),
            'f1': f1_score(y_test, y_pred, zero_division=0),
            'auc_roc': auc,
            'confusion_matrix': confusion_matrix(y_test, y_pred).tolist()
        }
        
        self.feature_importances = pd.DataFrame({
            'feature': self.features,
            'importance': self.rf.feature_importances_
        }).sort_values('importance', ascending=False)

        # 3. Isolation Forest (Entrenamos con todos los datos o con los train)
        self.iso.fit(X)
        
    def predict_all(self):
        """
        Genera el score consolidado para todos los siniestros en el dataset.
        """
        X = self.df[self.features]
        
        # Prob RF (0 a 1)
        probas_all = self.rf.predict_proba(X)
        if probas_all.shape[1] == 1:
            prob_rf = np.zeros(X.shape[0]) if self.rf.classes_[0] == 0 else np.ones(X.shape[0])
        else:
            prob_rf = probas_all[:, 1]
        
        # Anomaly score normalizado 0-1 (decision_function da valores donde menor es más anómalo)
        iso_scores = self.iso.decision_function(X)
        # Invertir y normalizar aprox a 0-1
        # Valores negativos son anomalías. 
        # Transformación min-max manual para fines del prototipo:
        iso_min, iso_max = iso_scores.min(), iso_scores.max()
        # Normalizamos: 1 = anomalía fuerte (valor menor original), 0 = normal (valor mayor original)
        anomaly_score_norm = (iso_max - iso_scores) / (iso_max - iso_min + 1e-6)

        self.df['prob_rf'] = prob_rf
        self.df['anomaly_score'] = anomaly_score_norm
        
        # Calcular Score Final
        # Score final = (score_reglas * 0.40) + (prob_rf * 100 * 0.35) + (anomaly_score * 100 * 0.15) + (nlp_score * 100 * 0.10)
        score_final = (
            (self.df['score_reglas'].clip(upper=100) * 0.40) + 
            (prob_rf * 100 * 0.35) + 
            (anomaly_score_norm * 100 * 0.15) + 
            (self.df['max_similarity_nlp'] * 100 * 0.10)
        )
        self.df['score_final'] = score_final.round(2)
        
        # Niveles de riesgo
        conditions = [
            (self.df['score_final'] <= 40),
            (self.df['score_final'] > 40) & (self.df['score_final'] <= 75),
            (self.df['score_final'] > 75)
        ]
        choices = ['Verde', 'Amarillo', 'Rojo']
        self.df['nivel_riesgo'] = np.select(conditions, choices, default='Verde')
        
        return self.df

    def get_metrics(self):
        return self.metrics
    
    def get_feature_importances(self):
        return self.feature_importances
