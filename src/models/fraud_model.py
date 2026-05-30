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
        Inicializa el pipeline con el DataFrame unificado (siniestros + proveedores).
        El label de fraude se deriva del campo 'estado':
          Investigación o Negativa → 1 (sospechoso/rechazado)
          Resto                    → 0 (normal)
        """
        self.df = df.copy()

        # Booleanos → numérico
        for col, new_col in [('documentos_completos', 'documentos_completos_num'),
                              ('en_lista_restrictiva',  'en_lista_restrictiva_num')]:
            if col in self.df.columns:
                self.df[new_col] = self.df[col].astype(bool).astype(int)

        # Derivar etiqueta de fraude desde 'estado'
        if 'etiqueta_fraude_simulada' not in self.df.columns:
            if 'estado' in self.df.columns:
                estados_fraude = {'Investigación', 'Negativa'}
                self.df['etiqueta_fraude_simulada'] = (
                    self.df['estado'].isin(estados_fraude).astype(int)
                )
            else:
                self.df['etiqueta_fraude_simulada'] = 0

        self.tfidf = TfidfVectorizer(stop_words=None)
        self.rf    = RandomForestClassifier(n_estimators=150, class_weight='balanced', random_state=42)
        self.iso   = IsolationForest(contamination=0.28, random_state=42)

        self.metrics            = {}
        self.feature_importances = None

        # Features disponibles en el dataset real (sin pct_casos_observados)
        self.features = [
            'dias_desde_inicio_poliza',
            'dias_desde_fin_poliza',
            'dias_entre_ocurrencia_reporte',
            'monto_reclamado',
            'monto_estimado',
            'historial_siniestros_asegurado',
            'documentos_completos_num',
            'en_lista_restrictiva_num',
            'score_reglas',
            'max_similarity_nlp',
        ]

    def _calc_nlp_similarity(self):
        """
        Recalcula similitud NLP a partir de las descripciones.
        Si el dataset ya trae max_similarity_nlp precalculado lo respeta,
        solo calcula id_siniestro_similar.
        """
        textos = self.df['descripcion'].fillna("")
        try:
            tfidf_matrix = self.tfidf.fit_transform(textos)
            cosine_sim   = cosine_similarity(tfidf_matrix)
            np.fill_diagonal(cosine_sim, 0)

            max_indices = cosine_sim.argmax(axis=1)
            ids         = self.df['id_siniestro'].values
            self.df['id_siniestro_similar'] = [ids[i] for i in max_indices]

            # Solo sobreescribir si no viene precalculado
            if 'max_similarity_nlp' not in self.df.columns or self.df['max_similarity_nlp'].sum() == 0:
                self.df['max_similarity_nlp'] = cosine_sim.max(axis=1)
        except Exception:
            self.df['max_similarity_nlp']    = 0.0
            self.df['id_siniestro_similar']  = 'N/A'

    def _enrich_vehicle_beneficiary(self):
        """
        Calcula cuántas veces aparece el mismo chasis, motor o beneficiario
        en otros siniestros del portafolio. Enriquece el df con esos conteos
        para que las reglas RF-10 y RF-11 puedan usarlos.
        """
        # Chasis repetido
        if 'chasis' in self.df.columns:
            chasis_counts = self.df[self.df['chasis'].notna()].groupby('chasis')['id_siniestro'].count()
            self.df['chasis_en_otros_siniestros'] = self.df['chasis'].map(chasis_counts).fillna(0).astype(int) - 1
            self.df['chasis_en_otros_siniestros'] = self.df['chasis_en_otros_siniestros'].clip(lower=0)
        else:
            self.df['chasis_en_otros_siniestros'] = 0

        # Motor repetido
        if 'motor' in self.df.columns:
            motor_counts = self.df[self.df['motor'].notna()].groupby('motor')['id_siniestro'].count()
            self.df['motor_en_otros_siniestros'] = self.df['motor'].map(motor_counts).fillna(0).astype(int) - 1
            self.df['motor_en_otros_siniestros'] = self.df['motor_en_otros_siniestros'].clip(lower=0)
        else:
            self.df['motor_en_otros_siniestros'] = 0

        # Beneficiario repetido
        if 'beneficiario' in self.df.columns:
            benef_counts = self.df[self.df['beneficiario'].notna() & (self.df['beneficiario'] != '')]\
                           .groupby('beneficiario')['id_siniestro'].count()
            self.df['beneficiario_en_otros_siniestros'] = self.df['beneficiario'].map(benef_counts).fillna(0).astype(int) - 1
            self.df['beneficiario_en_otros_siniestros'] = self.df['beneficiario_en_otros_siniestros'].clip(lower=0)
        else:
            self.df['beneficiario_en_otros_siniestros'] = 0

        # Reclamos RC sin tercero (campo del asegurado) — limpiar nulos para RF-12/RF-13
        if 'reclamos_rc_sin_tercero' in self.df.columns:
            self.df['reclamos_rc_sin_tercero'] = pd.to_numeric(
                self.df['reclamos_rc_sin_tercero'], errors='coerce'
            ).fillna(0).astype(int)
        else:
            self.df['reclamos_rc_sin_tercero'] = 0

    def _run_rules(self):
        """Calcula score_reglas para cada siniestro."""
        from src.rules.fraud_rules import calculate_rule_score
        self._enrich_vehicle_beneficiary()
        scores = []
        for _, row in self.df.iterrows():
            d = row.to_dict()
            scores.append(calculate_rule_score(d)['score_reglas'])
        self.df['score_reglas'] = scores

    def train_models(self):
        """Entrena NLP, Reglas, Random Forest e Isolation Forest."""
        self._calc_nlp_similarity()
        if 'score_reglas' not in self.df.columns:
            self._run_rules()

        # Garantizar que todas las features existan y no tengan nulos
        for f in self.features:
            if f not in self.df.columns:
                self.df[f] = 0
            self.df[f] = pd.to_numeric(self.df[f], errors='coerce').fillna(0)

        X = self.df[self.features]
        y = self.df['etiqueta_fraude_simulada']

        # Random Forest
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y
            )
        except ValueError:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )

        self.rf.fit(X_train, y_train)

        y_pred = self.rf.predict(X_test)
        probas  = self.rf.predict_proba(X_test)
        y_prob  = probas[:, 1] if probas.shape[1] > 1 else np.zeros(len(X_test))

        try:
            auc = roc_auc_score(y_test, y_prob)
        except ValueError:
            auc = 0.0

        self.metrics = {
            'precision':        precision_score(y_test, y_pred, zero_division=0),
            'recall':           recall_score(y_test, y_pred, zero_division=0),
            'f1':               f1_score(y_test, y_pred, zero_division=0),
            'auc_roc':          auc,
            'confusion_matrix': confusion_matrix(y_test, y_pred).tolist(),
        }

        self.feature_importances = pd.DataFrame({
            'feature':    self.features,
            'importance': self.rf.feature_importances_,
        }).sort_values('importance', ascending=False)

        # Isolation Forest
        self.iso.fit(X)

    def predict_all(self):
        """Genera score_final y nivel_riesgo para todos los siniestros."""
        X = self.df[self.features]

        # Probabilidad RF
        probas  = self.rf.predict_proba(X)
        prob_rf = probas[:, 1] if probas.shape[1] > 1 else np.zeros(len(X))

        # Anomaly score (Isolation Forest) normalizado 0-1
        iso_scores = self.iso.decision_function(X)
        iso_min, iso_max = iso_scores.min(), iso_scores.max()
        anomaly_norm = (iso_max - iso_scores) / (iso_max - iso_min + 1e-6)

        self.df['prob_rf']       = prob_rf
        self.df['anomaly_score'] = anomaly_norm

        # Score final ponderado
        score_reglas_esc = (self.df['score_reglas'] * 2.5).clip(upper=100)
        score_final = (
            score_reglas_esc                    * 0.40 +
            prob_rf           * 100             * 0.35 +
            anomaly_norm      * 100             * 0.15 +
            self.df['max_similarity_nlp'] * 100 * 0.10
        )
        self.df['score_final'] = score_final.round(2)

        # Nivel de riesgo
        conditions = [
            self.df['score_final'] <= 40,
            (self.df['score_final'] > 40) & (self.df['score_final'] <= 75),
            self.df['score_final'] > 75,
        ]
        self.df['nivel_riesgo'] = np.select(conditions, ['Verde', 'Amarillo', 'Rojo'], default='Verde')

        return self.df

    def get_metrics(self):
        return self.metrics

    def get_feature_importances(self):
        return self.feature_importances
