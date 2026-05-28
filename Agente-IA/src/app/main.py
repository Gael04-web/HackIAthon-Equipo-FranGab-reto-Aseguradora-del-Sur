import sys
import os
import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client, Client

# Asegurar que src sea importable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.models.fraud_model import FraudModelPipeline
from src.explainability.explain_score import explain_score
from src.ai_agent.claims_agent import ClaimsAgent
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Fraudia Claims - Aseguradora del Sur", layout="wide", page_icon="🛡️")

# --- DATA LOADING ---
@st.cache_data
def load_data():
    """Carga los datos de Supabase o CSV como fallback."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    df_siniestros = None
    if url and key and "your_" not in key:
        try:
            supabase: Client = create_client(url, key)
            # Para el prototipo, traemos siniestros y hacemos un join básico con otras tablas
            # Lo más fácil es traer todo y mergear en pandas
            sin = supabase.table("siniestros").select("*").execute().data
            prov = supabase.table("proveedores").select("id_proveedor,nombre,en_lista_restrictiva,pct_casos_observados,reclamos_asociados").execute().data
            
            df_sin = pd.DataFrame(sin)
            df_prov = pd.DataFrame(prov)
            df_prov = df_prov.rename(columns={'nombre': 'nombre_proveedor', 'reclamos_asociados': 'reclamos_asociados_proveedor'})
            
            if not df_sin.empty and not df_prov.empty:
                df_siniestros = df_sin.merge(df_prov, on="id_proveedor", how="left")
        except Exception as e:
            st.warning(f"Error conectando a Supabase ({e}). Usando datos locales.")
    
    if df_siniestros is None or df_siniestros.empty:
        csv_path = os.path.join(os.path.dirname(__file__), '../../data/synthetic/siniestros.csv')
        if os.path.exists(csv_path):
            df_siniestros = pd.read_csv(csv_path)
            # Simulamos datos de proveedor que normalmente vendrían de un JOIN
            if 'en_lista_restrictiva' not in df_siniestros.columns:
                df_siniestros['en_lista_restrictiva'] = False
                df_siniestros['pct_casos_observados'] = 0.0
                df_siniestros['reclamos_asociados_proveedor'] = 0
                df_siniestros['nombre_proveedor'] = "Proveedor Fallback"
        else:
            st.error("No se encontraron datos en la BD ni el archivo CSV.")
            return pd.DataFrame()
            
    return df_siniestros

# --- MODEL PROCESSING ---
@st.cache_resource
def get_processed_data_and_model(df):
    model = FraudModelPipeline(df)
    model.train_models()
    df_processed = model.predict_all()
    return df_processed, model

# Cargar
raw_df = load_data()
if raw_df.empty:
    st.stop()

df, model = get_processed_data_and_model(raw_df)

# --- SIDEBAR NAV ---
st.sidebar.image("https://via.placeholder.com/300x100.png?text=Aseguradora+del+Sur", use_container_width=True)
st.sidebar.title("Fraudia Claims")
page = st.sidebar.radio("Navegación", [
    "Dashboard Principal", 
    "Detalle de Siniestro", 
    "Asistente IA (Gemini)", 
    "Métricas del Modelo",
    "✍️ Registrar Siniestro"
])

# Funciones auxiliares UI
def get_color_for_riesgo(riesgo):
    if riesgo == "Rojo": return "red"
    if riesgo == "Amarillo": return "orange"
    return "green"

if page == "Dashboard Principal":
    st.title("🛡️ Dashboard de Siniestros")
    
    # KPIs
    col1, col2, col3, col4 = st.columns(4)
    total_siniestros = len(df)
    pct_rojos = (len(df[df['nivel_riesgo'] == 'Rojo']) / total_siniestros) * 100 if total_siniestros else 0
    pct_amarillos = (len(df[df['nivel_riesgo'] == 'Amarillo']) / total_siniestros) * 100 if total_siniestros else 0
    monto_riesgo = df[df['nivel_riesgo'].isin(['Rojo', 'Amarillo'])]['monto_reclamado'].sum()
    
    col1.metric("Total Siniestros", total_siniestros)
    col2.metric("% Nivel Rojo", f"{pct_rojos:.1f}%")
    col3.metric("% Nivel Amarillo", f"{pct_amarillos:.1f}%")
    col4.metric("Monto en Riesgo ($)", f"${monto_riesgo:,.2f}")
    
    st.markdown("---")
    
    # Gráficos
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Distribución por Nivel de Riesgo")
        dist = df['nivel_riesgo'].value_counts().reset_index()
        dist.columns = ['Nivel de Riesgo', 'Cantidad']
        fig = px.bar(dist, x='Nivel de Riesgo', y='Cantidad', color='Nivel de Riesgo', 
                     color_discrete_map={"Rojo": "red", "Amarillo": "orange", "Verde": "green"})
        st.plotly_chart(fig, use_container_width=True)
        
    with c2:
        st.subheader("Reclamos por Ramo")
        fig2 = px.pie(df, names='ramo', hole=0.3)
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("---")
    
    # Filtros y Tabla
    st.subheader("Buscador de Siniestros")
    f_col1, f_col2, f_col3 = st.columns(3)
    riesgo_filter = f_col1.multiselect("Nivel de Riesgo", ["Verde", "Amarillo", "Rojo"], default=["Rojo", "Amarillo"])
    ramo_filter = f_col2.multiselect("Ramo", df['ramo'].unique(), default=df['ramo'].unique())
    score_filter = f_col3.slider("Rango de Score", 0, 100, (0, 100))
    
    filtered_df = df[
        (df['nivel_riesgo'].isin(riesgo_filter)) &
        (df['ramo'].isin(ramo_filter)) &
        (df['score_final'] >= score_filter[0]) & 
        (df['score_final'] <= score_filter[1])
    ]
    
    view_df = filtered_df[['id_siniestro', 'ramo', 'monto_reclamado', 'score_final', 'nivel_riesgo', 'fecha_ocurrencia']]
    
    # Mostrar tabla con estilo de Pandas Styler
    def highlight_riesgo(s):
        if s.nivel_riesgo == 'Rojo': return ['background-color: #ffcccc']*len(s)
        elif s.nivel_riesgo == 'Amarillo': return ['background-color: #fff3cd']*len(s)
        return ['background-color: #d4edda']*len(s)

    st.dataframe(view_df.style.apply(highlight_riesgo, axis=1), use_container_width=True, hide_index=True)

elif page == "Detalle de Siniestro":
    st.title("🔍 Detalle de Siniestro")
    
    # Seleccionar siniestro (ordenados por score descendente)
    siniestros_list = df.sort_values('score_final', ascending=False)['id_siniestro'].tolist()
    selected_id = st.selectbox("Seleccione un Siniestro a evaluar:", siniestros_list)
    
    if selected_id:
        row = df[df['id_siniestro'] == selected_id].iloc[0]
        
        c1, c2 = st.columns([2, 1])
        
        with c1:
            st.subheader("Datos del Siniestro")
            st.write(f"**Asegurado ID:** {row.get('id_asegurado', 'N/A')}")
            st.write(f"**Ramo:** {row.get('ramo', 'N/A')} | **Cobertura:** {row.get('cobertura', 'N/A')}")
            st.write(f"**Fecha Ocurrencia:** {row.get('fecha_ocurrencia', 'N/A')} | **Fecha Reporte:** {row.get('fecha_reporte', 'N/A')}")
            st.write(f"**Monto Reclamado:** ${row.get('monto_reclamado', 0):,.2f}")
            st.write(f"**Proveedor:** {row.get('nombre_proveedor', row.get('id_proveedor', 'N/A'))}")
            st.write(f"**Descripción:** {row.get('descripcion', 'N/A')}")
            
        with c2:
            st.subheader("Evaluación de Riesgo")
            st.metric("Score de Fraude", f"{row['score_final']:.2f}/100")
            
            nivel = row['nivel_riesgo']
            if nivel == "Rojo":
                st.error("NIVEL ROJO - ALTO RIESGO")
            elif nivel == "Amarillo":
                st.warning("NIVEL AMARILLO - REVISIÓN NECESARIA")
            else:
                st.success("NIVEL VERDE - RIESGO BAJO")
                
        st.markdown("---")
        st.subheader("Análisis de IA y Explicabilidad")
        
        dict_row = row.to_dict()
        explicacion = explain_score(dict_row)
        
        st.info(explicacion)

elif page == "Asistente IA (Gemini)":
    st.title("🤖 Asistente Antifraude Gemini")
    st.write("Consulta al agente conversacional sobre los siniestros o patrones detectados.")
    
    # Inicializar agente en session state
    if "agent" not in st.session_state:
        st.session_state.agent = ClaimsAgent(df)
        
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Sugerencias
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("¿Top 10 casos críticos?"):
        prompt = "¿Cuáles son los 10 casos más críticos?"
        st.session_state.messages.append({"role": "user", "content": prompt})
    if c2.button("¿Proveedores con más alertas?"):
        prompt = "¿Qué proveedores concentran más alertas?"
        st.session_state.messages.append({"role": "user", "content": prompt})
    if c3.button("Resumen ejecutivo"):
        prompt = "Genera un resumen ejecutivo de los casos críticos."
        st.session_state.messages.append({"role": "user", "content": prompt})
    if c4.button("¿Qué revisar primero?"):
        prompt = "¿Qué casos revisar primero?"
        st.session_state.messages.append({"role": "user", "content": prompt})

    # Mostrar historial
    for msg in st.session_state.messages:
        st.chat_message(msg["role"]).write(msg["content"])
        
    # Procesar último mensaje sugerido o nuevo input
    user_input = st.chat_input("Escribe tu pregunta...")
    
    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        st.chat_message("user").write(user_input)

    # Solo si el último mensaje es del usuario, generar respuesta
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
        with st.spinner("Generando respuesta..."):
            last_prompt = st.session_state.messages[-1]["content"]
            response = st.session_state.agent.ask(last_prompt)
            st.session_state.messages.append({"role": "assistant", "content": response})
            st.chat_message("assistant").write(response)

elif page == "Métricas del Modelo":
    st.title("📊 Rendimiento del Modelo Predictivo")
    st.write("Métricas del Random Forest evaluado en los datos etiquetados (simulados).")
    
    metrics = model.get_metrics()
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Precision", f"{metrics.get('precision', 0):.3f}")
    col2.metric("Recall", f"{metrics.get('recall', 0):.3f}")
    col3.metric("F1 Score", f"{metrics.get('f1', 0):.3f}")
    col4.metric("AUC-ROC", f"{metrics.get('auc_roc', 0):.3f}")
    
    st.markdown("---")
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Feature Importance")
        fi = model.get_feature_importances()
        fig_fi = px.bar(fi.head(10), x='importance', y='feature', orientation='h')
        fig_fi.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_fi, use_container_width=True)
        
    with c2:
        st.subheader("Matriz de Confusión")
        cm = metrics.get('confusion_matrix', [[0,0],[0,0]])
        cm_df = pd.DataFrame(cm, index=['Real Normal', 'Real Fraude'], columns=['Pred Normal', 'Pred Fraude'])
        st.dataframe(cm_df, use_container_width=True)

elif page == "✍️ Registrar Siniestro":
    import uuid
    from datetime import date, datetime
    from src.rules.fraud_rules import calculate_rule_score

    st.title("✍️ Registrar Nuevo Siniestro")
    st.write("Ingresa los datos del siniestro. El sistema calculará el score de riesgo en tiempo real.")
    st.markdown("---")

    with st.form("form_siniestro", clear_on_submit=False):
        st.subheader("📄 Datos Básicos del Siniestro")
        c1, c2, c3 = st.columns(3)
        ramo = c1.selectbox("Ramo", ["Vehiculos", "Salud", "Vida", "Hogar", "Generales"])
        cobertura = c2.selectbox("Cobertura", ["Choque", "Robo", "Enfermedad", "Incendio", "RC"])
        estado = c3.selectbox("Estado", ["Reportado", "En Analisis", "Aprobado", "Rechazado"])

        c1b, c2b = st.columns(2)
        fecha_ocurrencia = c1b.date_input("Fecha de Ocurrencia", value=date.today())
        fecha_reporte    = c2b.date_input("Fecha de Reporte",    value=date.today())

        st.subheader("💰 Montos")
        c1c, c2c, c3c = st.columns(3)
        monto_reclamado  = c1c.number_input("Monto Reclamado ($)", min_value=0.0, value=5000.0, step=100.0)
        monto_estimado   = c2c.number_input("Monto Estimado ($)",  min_value=0.0, value=4500.0, step=100.0)
        suma_asegurada   = c3c.number_input("Suma Asegurada de la Póliza ($)", min_value=1.0, value=20000.0, step=500.0)

        st.subheader("👤 Datos del Asegurado y Proveedor")
        c1d, c2d, c3d = st.columns(3)
        historial        = c1d.number_input("Siniestros previos del asegurado", min_value=0, value=0, step=1)
        docs_completos   = c2d.checkbox("Documentos completos", value=True)
        lista_restrictiva= c3d.checkbox("Proveedor en lista restrictiva", value=False)

        c1e, c2e = st.columns(2)
        pct_obs          = c1e.slider("% casos observados del proveedor", 0.0, 1.0, 0.05, 0.01)
        reclamos_prov    = c2e.number_input("Reclamos asociados al proveedor", min_value=0, value=5, step=1)

        st.subheader("📅 Tiempos")
        c1f, c2f, c3f = st.columns(3)
        dias_desde_inicio = c1f.number_input("Días desde inicio de la póliza", min_value=0, value=90, step=1)
        dias_desde_fin    = c2f.number_input("Días hasta fin de la póliza", min_value=0, value=275, step=1)
        dias_reporte      = c3f.number_input("Días entre ocurrencia y reporte", min_value=0, value=1, step=1)

        descripcion = st.text_area("📝 Descripción del siniestro", height=100,
                                   placeholder="Describe brevemente cómo ocurrió el siniestro...")
        beneficiario = st.text_input("👨‍👩‍👧 Beneficiario")

        submitted = st.form_submit_button("📊 Calcular Score de Riesgo", use_container_width=True)

    if submitted:
        # Calcular similitud NLP con los siniestros existentes
        nlp_score = 0.0
        id_similar = "N/A"
        if descripcion.strip() and 'descripcion' in df.columns:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            import numpy as np
            textos_existentes = df['descripcion'].fillna("").tolist()
            todos = textos_existentes + [descripcion]
            try:
                vec = TfidfVectorizer(stop_words='english').fit_transform(todos)
                sims = cosine_similarity(vec[-1], vec[:-1])[0]
                nlp_score = float(sims.max())
                idx_similar = int(sims.argmax())
                id_similar = df['id_siniestro'].iloc[idx_similar][:8]
            except Exception:
                nlp_score = 0.0

        # Armar el dict para el motor de reglas
        siniestro_input = {
            "dias_desde_inicio_poliza":          dias_desde_inicio,
            "dias_desde_fin_poliza":             dias_desde_fin,
            "dias_entre_ocurrencia_reporte":      dias_reporte,
            "monto_reclamado":                   monto_reclamado,
            "monto_estimado":                    monto_estimado,
            "suma_asegurada":                    suma_asegurada,
            "historial_siniestros_asegurado":    historial,
            "documentos_completos":              docs_completos,
            "en_lista_restrictiva":              lista_restrictiva,
            "pct_casos_observados_proveedor":    pct_obs,
            "reclamos_asociados_proveedor":      reclamos_prov,
            "cobertura":                         cobertura,
            "max_similarity_nlp":                nlp_score,
            "id_siniestro_similar":              id_similar,
        }

        res_reglas = calculate_rule_score(siniestro_input)
        score_reglas = res_reglas["score_reglas"]
        alertas      = res_reglas["alertas"]

        # Score final simplificado (sin RF/IF ya que es un caso nuevo)
        # Usamos reglas (60%) + NLP (40%) como proxy para el registro nuevo
        score_final = min(100, round((score_reglas * 0.60) + (nlp_score * 100 * 0.40), 1))

        if score_final <= 40:
            nivel = "Verde"
        elif score_final <= 75:
            nivel = "Amarillo"
        else:
            nivel = "Rojo"

        # --- Resultado visual ---
        st.markdown("---")
        st.subheader("🏥 Resultado del Análisis")

        rc1, rc2 = st.columns([2, 1])
        with rc2:
            st.metric("Score de Fraude", f"{score_final}/100")
            if nivel == "Rojo":
                st.error("🔴 NIVEL ROJO — ALTO RIESGO\nEscalar a Unidad Antifraude.")
            elif nivel == "Amarillo":
                st.warning("🟡 NIVEL AMARILLO — REVISIÓN NECESARIA\nEl analista debe revisar antes de autorizar.")
            else:
                st.success("🟢 NIVEL VERDE — RIESGO BAJO\nProceder por flujo estándar.")

        with rc1:
            st.subheader("Alertas detectadas")
            if alertas:
                for alerta in alertas:
                    if "CRÍTICO" in alerta:
                        st.error(alerta)
                    elif "ALTO" in alerta:
                        st.warning(alerta)
                    else:
                        st.info(alerta)
            else:
                st.success("✅ No se detectaron alertas en este siniestro.")

            if nlp_score > 0.70:
                st.warning(f"🔍 Descripción con {int(nlp_score*100)}% de similitud al siniestro `{id_similar}`.")

        # --- Guardar en Supabase (si está configurado) ---
        st.markdown("---")
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if url and key and "your_" not in key:
            if st.button("💾 Guardar siniestro en Supabase"):
                try:
                    supabase: Client = create_client(url, key)
                    nuevo_id = str(uuid.uuid4())
                    nuevo_registro = {
                        "id_siniestro":                       nuevo_id,
                        "ramo":                               ramo,
                        "cobertura":                          cobertura,
                        "fecha_ocurrencia":                   fecha_ocurrencia.isoformat(),
                        "fecha_reporte":                      fecha_reporte.isoformat(),
                        "monto_reclamado":                    monto_reclamado,
                        "monto_estimado":                     monto_estimado,
                        "estado":                             estado,
                        "descripcion":                        descripcion,
                        "documentos_completos":               docs_completos,
                        "beneficiario":                       beneficiario,
                        "dias_desde_inicio_poliza":           dias_desde_inicio,
                        "dias_desde_fin_poliza":              dias_desde_fin,
                        "dias_entre_ocurrencia_reporte":      dias_reporte,
                        "historial_siniestros_asegurado":     historial,
                        "etiqueta_fraude_simulada":           0,
                        "monto_pagado":                       0.0,
                    }
                    supabase.table("siniestros").insert(nuevo_registro).execute()
                    st.success(f"✅ Siniestro guardado con ID: `{nuevo_id[:8]}...`")
                    # Limpiar caché para que el dashboard se actualice
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Error al guardar en Supabase: {e}")
        else:
            st.info("ℹ️ Configura SUPABASE_URL y SUPABASE_KEY en el .env para guardar el siniestro en la base de datos.")
