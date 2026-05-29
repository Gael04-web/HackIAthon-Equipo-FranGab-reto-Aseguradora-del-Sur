import sys
import os
import uuid
import json
import requests
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
from dotenv import load_dotenv
from fpdf import FPDF
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.models.fraud_model import FraudModelPipeline
from src.ai_agent.claims_agent import ClaimsAgent
from src.rules.fraud_rules import calculate_rule_score

load_dotenv()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sb_headers():
    key = os.getenv("SUPABASE_KEY", "")
    return {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
    }

def _sb_url(table: str, params: str = "") -> str:
    base = os.getenv("SUPABASE_URL", "").rstrip("/") + f"/rest/v1/{table}"
    return base + (f"?{params}" if params else "")

def _sb_configured() -> bool:
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    return bool(url and key and "your_" not in key)

def get_supabase_client():
    """Compatibilidad — devuelve True si Supabase está configurado."""
    return _sb_configured() or None

def guardar_decision_supabase(id_siniestro: str, decision: str):
    """Persiste la decisión en Supabase y actualiza el estado local sin reentrenar."""
    if _sb_configured():
        try:
            requests.patch(
                _sb_url("siniestros", f"id_siniestro=eq.{id_siniestro}"),
                data=json.dumps({"decision_analista": decision}),
                headers=_sb_headers(),
                timeout=10,
            ).raise_for_status()
        except Exception as e:
            st.warning(f"No se pudo guardar en Supabase: {e}")
    if "decisions" not in st.session_state:
        st.session_state.decisions = {}
    st.session_state.decisions[id_siniestro] = decision

def generate_pdf_report(claim_id, risk_level, score, ai_text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "Reporte de Analisis de Siniestro - Fraudia Claims", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"ID de Siniestro: {claim_id}", ln=True)
    pdf.cell(0, 10, f"Nivel de Riesgo Calculado: {risk_level.upper()}", ln=True)
    pdf.cell(0, 10, f"Score de Fraude: {int(score)}/100", ln=True)
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Conclusion Ejecutiva (Inspector FRAUDIA):", ln=True)
    pdf.set_font("Arial", '', 11)
    safe_text = ai_text.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 8, safe_text)
    return bytes(pdf.output())

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Fraudia Claims - Aseguradora del Sur",
    layout="wide",
    page_icon="🛡️"
)

# ---------------------------------------------------------------------------
# Data loading & model — cache separado para no reentrenar en decisiones
# ---------------------------------------------------------------------------
@st.cache_data
def load_data():
    """Carga datos de Supabase o CSV como fallback."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    df_siniestros = None
    if _sb_configured():
        try:
            def sb_get(table, select="*", limit=2000):
                r = requests.get(
                    _sb_url(table, f"select={select}&limit={limit}"),
                    headers=_sb_headers(), timeout=20
                )
                r.raise_for_status()
                return r.json()

            sin  = sb_get("siniestros")
            prov = sb_get("proveedores", "id_proveedor,nombre,en_lista_restrictiva,motivo_restriccion,reclamos_asociados")
            aseg = sb_get("asegurados",  "id_asegurado,nombre_asegurado,perfil_riesgo")

            df_sin       = pd.DataFrame(sin)
            df_prov      = pd.DataFrame(prov)
            df_aseg_mini = pd.DataFrame(aseg)

            df_prov = df_prov.rename(columns={
                'nombre':             'nombre_proveedor',
                'reclamos_asociados': 'reclamos_asociados_proveedor',
                'motivo_restriccion': 'motivo_restriccion_proveedor',
            })

            if 'decision_analista' not in df_sin.columns:
                df_sin['decision_analista'] = 'Pendiente'
            else:
                df_sin['decision_analista'] = df_sin['decision_analista'].fillna('Pendiente')

            if not df_sin.empty and not df_prov.empty:
                df_siniestros = df_sin.merge(df_prov, on="id_proveedor", how="left")
                if not df_aseg_mini.empty:
                    df_siniestros = df_siniestros.merge(df_aseg_mini, on="id_asegurado", how="left")
        except Exception as e:
            st.warning(f"Error conectando a Supabase ({e}). Usando datos locales.")

    if df_siniestros is None or df_siniestros.empty:
        csv_path = os.path.join(os.path.dirname(__file__), '../../data/synthetic/siniestros.csv')
        if os.path.exists(csv_path):
            df_siniestros = pd.read_csv(csv_path)
            if 'en_lista_restrictiva' not in df_siniestros.columns:
                df_siniestros['en_lista_restrictiva'] = False
                df_siniestros['reclamos_asociados_proveedor'] = 0
                df_siniestros['nombre_proveedor'] = "Proveedor Fallback"
                df_siniestros['motivo_restriccion_proveedor'] = ''
            if 'nombre_asegurado' not in df_siniestros.columns:
                df_siniestros['nombre_asegurado'] = ''
            if 'perfil_riesgo' not in df_siniestros.columns:
                df_siniestros['perfil_riesgo'] = ''
            if 'placa_vehiculo' not in df_siniestros.columns:
                df_siniestros['placa_vehiculo'] = ''
            if 'numero_parte_policial' not in df_siniestros.columns:
                df_siniestros['numero_parte_policial'] = ''
            if 'decision_analista' not in df_siniestros.columns:
                df_siniestros['decision_analista'] = 'Pendiente'
        else:
            st.error("No se encontraron datos en la BD ni el archivo CSV.")
            return pd.DataFrame()

    return df_siniestros


@st.cache_data(show_spinner="Entrenando modelos de detección de fraude…")
def get_processed_data_and_model(df):
    """Entrena el pipeline ML. Usa @st.cache_data para compatibilidad con DataFrames."""
    model = FraudModelPipeline(df)
    model.train_models()
    df_processed = model.predict_all()
    return df_processed, model


# ---------------------------------------------------------------------------
# Cargar datos y modelo
# ---------------------------------------------------------------------------
raw_df = load_data()
if raw_df.empty:
    st.stop()

df, model = get_processed_data_and_model(raw_df)

# Aplicar decisiones locales del analista encima del df cacheado (sin reentrenar)
if "decisions" not in st.session_state:
    st.session_state.decisions = {}
if st.session_state.decisions:
    df = df.copy()
    for sid, dec in st.session_state.decisions.items():
        df.loc[df['id_siniestro'] == sid, 'decision_analista'] = dec

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.markdown("## 🛡️ Fraudia Claims")
st.sidebar.markdown("**Aseguradora del Sur**")
st.sidebar.markdown("---")
page = st.sidebar.radio("Navegación", [
    "Dashboard Principal",
    "Detalle de Siniestro",
    "Inspector FRAUDIA (Asistente)",
    "Métricas del Modelo",
    "✍️ Registrar Siniestro",
])

# ---------------------------------------------------------------------------
# Dashboard Principal
# ---------------------------------------------------------------------------
if page == "Dashboard Principal":
    st.title("🛡️ Dashboard de Siniestros")

    total_siniestros = len(df)
    pct_rojos     = (len(df[df['nivel_riesgo'] == 'Rojo'])     / total_siniestros * 100) if total_siniestros else 0
    pct_amarillos = (len(df[df['nivel_riesgo'] == 'Amarillo']) / total_siniestros * 100) if total_siniestros else 0
    monto_riesgo  = df[df['nivel_riesgo'].isin(['Rojo', 'Amarillo'])]['monto_reclamado'].sum()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Siniestros",    total_siniestros)
    col2.metric("% Nivel Rojo",        f"{pct_rojos:.1f}%")
    col3.metric("% Nivel Amarillo",    f"{pct_amarillos:.1f}%")
    col4.metric("Monto en Riesgo ($)", f"${monto_riesgo:,.2f}")

    st.markdown("##### 📊 Estado de Revisión por el Analista")
    n_fraude       = len(df[df['decision_analista'] == 'Fraude Confirmado'])
    n_legitimo     = len(df[df['decision_analista'] == 'Legítimo'])
    n_investigacion = len(df[df['decision_analista'] == 'En Investigación'])
    n_pendiente    = total_siniestros - n_fraude - n_legitimo - n_investigacion

    d1, d2, d3, d4 = st.columns(4)
    d1.metric("⏳ Pendientes",          n_pendiente,      help="Sin decisión del analista aún.")
    d2.metric("🚨 Fraudes Confirmados", n_fraude,         help="Fraude verificado. Pago bloqueado.")
    d3.metric("🔍 En Investigación",    n_investigacion,  help="Requieren revisión de campo.")
    d4.metric("✅ Legítimos",            n_legitimo,       help="Cliente honesto. Pago aprobado.")

    st.markdown("---")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Distribución por Nivel de Riesgo")
        dist = df['nivel_riesgo'].value_counts().reset_index()
        dist.columns = ['Nivel de Riesgo', 'Cantidad']
        fig = px.bar(
            dist, x='Nivel de Riesgo', y='Cantidad', color='Nivel de Riesgo',
            color_discrete_map={"Rojo": "red", "Amarillo": "orange", "Verde": "green"}
        )
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("Reclamos por Ramo")
        fig2 = px.pie(df, names='ramo', hole=0.3)
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("---")
    st.subheader("Buscador de Siniestros")
    f1, f2, f3 = st.columns(3)
    riesgo_filter = f1.multiselect("Nivel de Riesgo", ["Verde", "Amarillo", "Rojo"], default=["Rojo", "Amarillo"])
    ramo_filter   = f2.multiselect("Ramo", df['ramo'].unique(), default=df['ramo'].unique())
    score_filter  = f3.slider("Rango de Score", 0, 100, (0, 100))

    filtered_df = df[
        df['nivel_riesgo'].isin(riesgo_filter) &
        df['ramo'].isin(ramo_filter) &
        (df['score_final'] >= score_filter[0]) &
        (df['score_final'] <= score_filter[1])
    ]
    view_df = filtered_df[['id_siniestro', 'ramo', 'monto_reclamado', 'score_final', 'nivel_riesgo', 'fecha_ocurrencia']]

    def highlight_riesgo(s):
        if s.nivel_riesgo == 'Rojo':      return ['background-color: #ffcccc; color: black'] * len(s)
        elif s.nivel_riesgo == 'Amarillo': return ['background-color: #fff3cd; color: black'] * len(s)
        return ['background-color: #d4edda; color: black'] * len(s)

    st.dataframe(view_df.style.apply(highlight_riesgo, axis=1), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Detalle de Siniestro
# ---------------------------------------------------------------------------
elif page == "Detalle de Siniestro":
    st.title("🔍 Detalle de Siniestro")

    siniestros_list = df.sort_values('score_final', ascending=False)['id_siniestro'].tolist()
    selected_id = st.selectbox("Seleccione un Siniestro a evaluar:", siniestros_list)

    if selected_id:
        row = df[df['id_siniestro'] == selected_id].iloc[0]

        c1, c2 = st.columns([2, 1])
        with c1:
            st.subheader("Datos del Siniestro")

            nombre_aseg  = row.get('nombre_asegurado', '') or row.get('id_asegurado', 'N/A')
            perfil_riesgo = row.get('perfil_riesgo', '')
            perfil_badge = {"Alto": "🔴 Alto", "Medio": "🟡 Medio", "Bajo": "🟢 Bajo"}.get(perfil_riesgo, perfil_riesgo)

            st.write(f"**Asegurado:** {nombre_aseg}  |  Perfil histórico: {perfil_badge}")
            st.write(f"**Ramo:** {row.get('ramo', 'N/A')}  |  **Cobertura:** {row.get('cobertura', 'N/A')}")

            placa = row.get('placa_vehiculo', '')
            if placa:
                st.write(f"**Placa vehículo:** {placa}")

            st.write(f"**Fecha Ocurrencia:** {row.get('fecha_ocurrencia', 'N/A')}  |  **Fecha Reporte:** {row.get('fecha_reporte', 'N/A')}")
            st.write(f"**Monto Reclamado:** ${row.get('monto_reclamado', 0):,.2f}  |  **Estimado:** ${row.get('monto_estimado', 0):,.2f}")
            st.write(f"**Estado:** {row.get('estado', 'N/A')}  |  **Sucursal:** {row.get('sucursal', 'N/A')}")

            nombre_prov = row.get('nombre_proveedor', row.get('id_proveedor', 'N/A'))
            motivo_prov = row.get('motivo_restriccion_proveedor', '')
            prov_str    = nombre_prov + (f"  ⚠️ *{motivo_prov}*" if motivo_prov else "")
            st.write(f"**Proveedor:** {prov_str}")

            parte = row.get('numero_parte_policial', '')
            if parte:
                st.write(f"**N° Parte Policial:** {parte}")

            st.write(f"**Descripción:** {row.get('descripcion', 'N/A')}")
        with c2:
            st.subheader("Evaluación de Riesgo")
            st.metric("Score de Fraude", f"{row['score_final']:.2f}/100")
            nivel = row['nivel_riesgo']
            if nivel == "Rojo":      st.error("NIVEL ROJO - ALTO RIESGO")
            elif nivel == "Amarillo": st.warning("NIVEL AMARILLO - REVISIÓN NECESARIA")
            else:                     st.success("NIVEL VERDE - RIESGO BAJO")

        st.markdown("---")

        if st.button("✨ Análisis Profundo con Agente IA (Gemini)"):
            with st.spinner("El agente está consultando la base de datos, aplicando reglas y aprendiendo de fraudes confirmados..."):
                if "agent" not in st.session_state:
                    st.session_state.agent = ClaimsAgent(df, get_supabase_client())
                datos_clave = {
                    "id_siniestro":                   selected_id,
                    "id_asegurado":                   row.get("id_asegurado"),
                    "id_proveedor":                   row.get("id_proveedor"),
                    "ramo":                           row.get("ramo"),
                    "cobertura":                      row.get("cobertura"),
                    "monto_reclamado":                row.get("monto_reclamado"),
                    "monto_estimado":                 row.get("monto_estimado"),
                    "suma_asegurada":                 row.get("suma_asegurada"),
                    "dias_desde_inicio_poliza":       row.get("dias_desde_inicio_poliza"),
                    "dias_desde_fin_poliza":          row.get("dias_desde_fin_poliza"),
                    "dias_entre_ocurrencia_reporte":  row.get("dias_entre_ocurrencia_reporte"),
                    "historial_siniestros_asegurado": row.get("historial_siniestros_asegurado"),
                    "documentos_completos":           row.get("documentos_completos"),
                    "en_lista_restrictiva":           row.get("en_lista_restrictiva"),
                    "pct_casos_observados_proveedor": row.get("pct_casos_observados"),
                    "reclamos_asociados_proveedor":   row.get("reclamos_asociados_proveedor"),
                    "descripcion":                    row.get("descripcion"),
                    "score_ml":                       row.get("score_final"),
                }
                analysis = st.session_state.agent.analyze_single_claim(datos_clave)
                st.session_state[f"analysis_{selected_id}"] = analysis

        # Mostrar análisis de Gemini si ya fue generado
        if f"analysis_{selected_id}" in st.session_state:
            analysis = st.session_state[f"analysis_{selected_id}"]

            st.markdown("---")
            st.subheader("🤖 Resultado del Agente IA")

            # Comparativa de scores: ML vs Gemini
            sa, sb_col, sc = st.columns(3)
            sa.metric("Score ML (pipeline)", f"{row['score_final']:.0f}/100",
                      help="Calculado por Random Forest + Isolation Forest + Reglas")
            gemini_score = analysis.get("score", 0)
            gemini_nivel = analysis.get("nivel_riesgo", "N/A")
            delta = gemini_score - int(row['score_final'])
            sb_col.metric("Score Gemini (agente)", f"{gemini_score}/100",
                          delta=f"{delta:+d} vs ML",
                          help="Calculado por Gemini tras consultar la BD y aprender de fraudes confirmados")
            sc.metric("Nivel según Gemini", gemini_nivel)

            # Factores detectados por Gemini
            factores = analysis.get("factores", [])
            if factores:
                st.markdown("**Factores de riesgo identificados por el agente:**")
                for f_item in factores:
                    st.markdown(f"- {f_item}")

            # Conclusión ejecutiva
            conclusion = analysis.get("conclusion", "")
            if conclusion:
                st.success(conclusion)

            # PDF con score de Gemini
            pdf_nivel = gemini_nivel if gemini_nivel != "N/A" else row["nivel_riesgo"]
            pdf_bytes = generate_pdf_report(
                selected_id[:8], pdf_nivel, gemini_score, conclusion
            )
            st.download_button(
                label="📄 Descargar Informe en PDF",
                data=pdf_bytes,
                file_name=f"Reporte_Siniestro_{selected_id[:8]}.pdf",
                mime="application/pdf"
            )

        st.markdown("---")
        st.subheader("👨‍⚖️ Decisión del Analista")
        st.write("Luego de revisar el análisis de la IA, confirma la decisión final sobre este siniestro:")

        # Leer decisión desde overlay local primero, luego del df de Supabase
        decision_actual = st.session_state.decisions.get(
            selected_id, row.get('decision_analista', 'Pendiente')
        )

        if decision_actual and decision_actual != 'Pendiente':
            if decision_actual == 'Fraude Confirmado':
                st.error(f"🚨 Decisión registrada: **{decision_actual}** — El pago ha sido bloqueado.")
            elif decision_actual == 'En Investigación':
                st.warning(f"🔍 Decisión registrada: **{decision_actual}** — Se abrió expediente de campo. Pago suspendido.")
            else:
                st.success(f"✅ Decisión registrada: **{decision_actual}** — El pago puede proceder.")
            if st.button("🔄 Cambiar decisión"):
                guardar_decision_supabase(selected_id, 'Pendiente')
                st.rerun()
        else:
            bc1, bc2, bc3 = st.columns(3)
            if bc1.button("🚨 Confirmar como FRAUDE", use_container_width=True):
                guardar_decision_supabase(selected_id, 'Fraude Confirmado')
                st.rerun()
            if bc2.button("🔍 Enviar a INVESTIGACIÓN", use_container_width=True):
                guardar_decision_supabase(selected_id, 'En Investigación')
                st.rerun()
            if bc3.button("✅ Marcar como CLIENTE LEGÍTIMO", use_container_width=True):
                guardar_decision_supabase(selected_id, 'Legítimo')
                st.rerun()

# ---------------------------------------------------------------------------
# Inspector FRAUDIA
# ---------------------------------------------------------------------------
elif page == "Inspector FRAUDIA (Asistente)":
    st.title("🤖 Inspector FRAUDIA - Asistente Antifraude")
    st.markdown("Chatea con tu analista virtual experto sobre los datos del portafolio y patrones detectados.")

    if "agent" not in st.session_state:
        st.session_state.agent = ClaimsAgent(df, get_supabase_client())
    if "messages" not in st.session_state:
        st.session_state.messages = []

    c1, c2, c3, c4 = st.columns(4)
    if c1.button("¿Top 10 casos críticos?"):
        st.session_state.messages.append({"role": "user", "content": "¿Cuáles son los 10 casos más críticos?"})
    if c2.button("¿Proveedores con más alertas?"):
        st.session_state.messages.append({"role": "user", "content": "¿Qué proveedores concentran más alertas?"})
    if c3.button("Resumen ejecutivo"):
        st.session_state.messages.append({"role": "user", "content": "Genera un resumen ejecutivo de los casos críticos."})
    if c4.button("¿Qué revisar primero?"):
        st.session_state.messages.append({"role": "user", "content": "¿Qué casos revisar primero?"})

    for msg in st.session_state.messages:
        st.chat_message(msg["role"]).write(msg["content"])

    user_input = st.chat_input("Escribe tu pregunta...")
    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        st.chat_message("user").write(user_input)

    if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
        with st.spinner("Generando respuesta..."):
            response = st.session_state.agent.ask(st.session_state.messages[-1]["content"])
            st.session_state.messages.append({"role": "assistant", "content": response})
            st.chat_message("assistant").write(response)

# ---------------------------------------------------------------------------
# Métricas del Modelo
# ---------------------------------------------------------------------------
elif page == "Métricas del Modelo":
    st.title("📊 Examen de la IA (Rendimiento del Sistema)")
    st.write("Le tomamos un 'examen sorpresa' al cerebro matemático dándole casos viejos para ver si logra identificar los fraudes.")

    metrics = model.get_metrics()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🎯 Efectividad al Acusar", f"{metrics.get('precision', 0)*100:.1f}%",
                help="Cuando la IA dice '¡Es fraude!', ¿qué tan seguido tiene razón?")
    col2.metric("🕵️ Fraudes Atrapados",    f"{metrics.get('recall', 0)*100:.1f}%",
                help="De TODOS los fraudes, ¿cuántos detectó la IA?")
    col3.metric("⭐ Nota Final",            f"{metrics.get('f1', 0)*100:.1f}%",
                help="Nota global. Cerca al 100% = excelente.")
    col4.metric("👁️ Ojo Crítico",           f"{metrics.get('auc_roc', 0)*100:.1f}%",
                help="100% = distingue perfectamente fraude vs legítimo.")

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🧠 ¿En qué se fija la IA?")
        st.write("Las barras más largas son las pistas que el modelo considera más determinantes.")
        fi = model.get_feature_importances()
        fig_fi = px.bar(fi.head(10), x='importance', y='feature', orientation='h')
        fig_fi.update_layout(yaxis={'categoryorder': 'total ascending'})
        st.plotly_chart(fig_fi, use_container_width=True)
    with c2:
        st.subheader("📝 Resultados del Examen")
        st.write("Exactamente en qué acertó y en qué se equivocó la IA durante la prueba:")
        cm = metrics.get('confusion_matrix', [[0, 0], [0, 0]])
        cm_df = pd.DataFrame(
            cm,
            index=['Realmente: CLIENTE HONESTO', 'Realmente: FRAUDE'],
            columns=['IA dijo: NORMAL', 'IA dijo: FRAUDE']
        )
        st.dataframe(cm_df, use_container_width=True)

# ---------------------------------------------------------------------------
# Registrar Siniestro
# ---------------------------------------------------------------------------
elif page == "✍️ Registrar Siniestro":
    st.title("✍️ Registrar Nuevo Siniestro")
    st.write("Ingresa los datos del siniestro. El sistema calculará el score de riesgo en tiempo real.")
    st.markdown("---")

    with st.form("form_siniestro", clear_on_submit=False):
        st.subheader("📄 Datos Básicos del Siniestro")
        c1, c2, c3 = st.columns(3)
        ramo      = c1.selectbox("Ramo", ["Vehiculos", "Salud", "Vida", "Hogar", "Generales"],
                                  help="Categoría del seguro.")
        cobertura = c2.selectbox("Cobertura", ["Choque", "Robo", "Enfermedad", "Incendio", "RC"],
                                  help="Tipo de evento cubierto.")
        estado    = c3.selectbox("Estado", ["Reportado", "En Analisis", "Aprobado", "Rechazado"])

        c1b, c2b = st.columns(2)
        fecha_ocurrencia = c1b.date_input("Fecha de Ocurrencia", value=date.today(),
                                          help="¿Cuándo ocurrió el accidente?")
        fecha_reporte    = c2b.date_input("Fecha de Reporte",    value=date.today(),
                                          help="¿Cuándo se comunicó el cliente?")

        st.subheader("💰 Montos")
        c1c, c2c, c3c = st.columns(3)
        monto_reclamado = c1c.number_input("Monto Reclamado ($)",             min_value=0.0,  value=5000.0,  step=100.0)
        monto_estimado  = c2c.number_input("Monto Estimado ($)",              min_value=0.0,  value=4500.0,  step=100.0)
        suma_asegurada  = c3c.number_input("Suma Asegurada de la Póliza ($)", min_value=1.0,  value=20000.0, step=500.0)

        st.subheader("👤 Datos del Asegurado y Proveedor")
        c1d, c2d, c3d = st.columns(3)
        historial         = c1d.number_input("Siniestros previos del asegurado", min_value=0, value=0, step=1,
                                             help="Mayor a 3 es muy sospechoso.")
        docs_completos    = c2d.checkbox("Documentos completos", value=True,
                                         help="Desmarca si el cliente no entrega la documentación.")
        lista_restrictiva = c3d.checkbox("Proveedor en lista restrictiva", value=False,
                                          help="Marca si el proveedor está fichado por fraudes previos.")

        c1e, c2e = st.columns(2)
        pct_obs       = c1e.slider("% casos observados del proveedor", 0.0, 1.0, 0.05, 0.01)
        reclamos_prov = c2e.number_input("Reclamos asociados al proveedor", min_value=0, value=5, step=1)

        st.subheader("📅 Tiempos (Análisis Predictivo)")
        c1f, c2f, c3f = st.columns(3)
        dias_desde_inicio = c1f.number_input("Días desde inicio de la póliza",    min_value=0, value=90, step=1,
                                             help="Primeros 10-30 días = máxima alerta de fraude oportunista.")
        dias_desde_fin    = c2f.number_input("Días hasta fin de la póliza",        min_value=0, value=275, step=1)
        dias_reporte      = c3f.number_input("Días entre ocurrencia y reporte",    min_value=0, value=1,  step=1)

        descripcion  = st.text_area("📝 Descripción del siniestro", height=100,
                                    placeholder="Describe brevemente cómo ocurrió el siniestro...",
                                    help="La IA buscará similitudes con historias de fraude conocidas.")
        beneficiario = st.text_input("👨‍👩‍👧 Beneficiario", help="Persona o entidad que recibirá el pago.")

        submitted = st.form_submit_button("📊 Calcular Score de Riesgo", use_container_width=True)

    # Al enviar el formulario calculamos todo y lo guardamos en session_state
    if submitted:
        nlp_score  = 0.0
        id_similar = "N/A"
        if descripcion.strip() and 'descripcion' in df.columns:
            textos_existentes = df['descripcion'].fillna("").tolist()
            try:
                vec  = TfidfVectorizer(stop_words=None).fit_transform(textos_existentes + [descripcion])
                sims = cosine_similarity(vec[-1], vec[:-1])[0]
                nlp_score  = float(sims.max())
                id_similar = df['id_siniestro'].iloc[int(sims.argmax())][:8]
            except Exception:
                nlp_score = 0.0

        siniestro_input = {
            "dias_desde_inicio_poliza":       dias_desde_inicio,
            "dias_desde_fin_poliza":          dias_desde_fin,
            "dias_entre_ocurrencia_reporte":  dias_reporte,
            "monto_reclamado":                monto_reclamado,
            "monto_estimado":                 monto_estimado,
            "suma_asegurada":                 suma_asegurada,
            "historial_siniestros_asegurado": historial,
            "documentos_completos":           docs_completos,
            "en_lista_restrictiva":           lista_restrictiva,
            "pct_casos_observados_proveedor": pct_obs,
            "reclamos_asociados_proveedor":   reclamos_prov,
            "cobertura":                      cobertura,
            "max_similarity_nlp":             nlp_score,
            "id_siniestro_similar":           id_similar,
        }

        res_reglas            = calculate_rule_score(siniestro_input)
        score_reglas          = res_reglas["score_reglas"]
        alertas               = res_reglas["alertas"]
        score_reglas_escalado = min(100.0, score_reglas * 2.5)
        score_final           = min(100, round((score_reglas_escalado * 0.60) + (nlp_score * 100 * 0.40), 1))
        nivel                 = "Rojo" if score_final > 75 else ("Amarillo" if score_final > 40 else "Verde")

        if "agent" not in st.session_state:
            st.session_state.agent = ClaimsAgent(df)

        datos_clave = {
            "ramo": ramo, "monto_reclamado": monto_reclamado, "cobertura": cobertura,
            "dias_desde_inicio_poliza":       dias_desde_inicio,
            "dias_entre_ocurrencia_reporte":  dias_reporte,
            "historial_siniestros_asegurado": historial,
            "documentos_completos":           docs_completos,
            "descripcion":                    descripcion,
            "score_riesgo_calculado":         score_final,
        }
        with st.spinner("Generando análisis completo con Gemini IA..."):
            conclusion = st.session_state.agent.analyze_single_claim(datos_clave)

        # Guardar resultado en session state → persiste cuando el usuario clique "Guardar"
        st.session_state['registrar_result'] = {
            'score_final':      score_final,
            'nivel':            nivel,
            'alertas':          alertas,
            'conclusion':       conclusion,
            'ramo':             ramo,
            'cobertura':        cobertura,
            'estado':           estado,
            'fecha_ocurrencia': fecha_ocurrencia,
            'fecha_reporte':    fecha_reporte,
            'monto_reclamado':  monto_reclamado,
            'monto_estimado':   monto_estimado,
            'dias_desde_inicio': dias_desde_inicio,
            'dias_desde_fin':   dias_desde_fin,
            'dias_reporte':     dias_reporte,
            'descripcion':      descripcion,
            'beneficiario':     beneficiario,
            'docs_completos':   docs_completos,
        }

    # Mostrar resultado (fuera del bloque if submitted → sobrevive el rerun del botón Guardar)
    if 'registrar_result' in st.session_state:
        r           = st.session_state['registrar_result']
        score_final = r['score_final']
        nivel       = r['nivel']
        alertas     = r['alertas']
        conclusion  = r['conclusion']

        st.markdown("---")
        st.subheader("🏥 Resultado del Análisis")

        rc1, rc2 = st.columns([2, 1])
        with rc2:
            st.metric("Score de Fraude", f"{score_final}/100")
            if nivel == "Rojo":
                st.error("🔴 NIVEL ROJO — ALTO RIESGO\nEscalar a Unidad Antifraude.")
            elif nivel == "Amarillo":
                st.warning("🟡 NIVEL AMARILLO — REVISIÓN NECESARIA")
            else:
                st.success("🟢 NIVEL VERDE — RIESGO BAJO\nProceder por flujo estándar.")

        with rc1:
            st.subheader("Alertas detectadas")
            if alertas:
                for alerta in alertas:
                    if "CRÍTICO" in alerta:   st.error(alerta)
                    elif "ALTO" in alerta:     st.warning(alerta)
                    else:                      st.info(alerta)
            else:
                st.success("✅ No se detectaron alertas en este siniestro.")

        st.success(conclusion)
        pdf_bytes = generate_pdf_report("NUEVO", nivel, score_final, conclusion)
        st.download_button(
            label="📄 Descargar Informe en PDF",
            data=pdf_bytes,
            file_name="Reporte_Siniestro_Nuevo.pdf",
            mime="application/pdf"
        )

        st.markdown("---")
        if _sb_configured():
            if st.button("💾 Guardar siniestro en Supabase"):
                try:
                    nuevo_id = str(uuid.uuid4())
                    nuevo_registro = {
                        "id_siniestro":                   nuevo_id,
                        "ramo":                           r['ramo'],
                        "cobertura":                      r['cobertura'],
                        "fecha_ocurrencia":               r['fecha_ocurrencia'].isoformat(),
                        "fecha_reporte":                  r['fecha_reporte'].isoformat(),
                        "monto_reclamado":                r['monto_reclamado'],
                        "monto_estimado":                 r['monto_estimado'],
                        "estado":                         r['estado'],
                        "descripcion":                    r['descripcion'],
                        "documentos_completos":           r['docs_completos'],
                        "dias_desde_inicio_poliza":       r['dias_desde_inicio'],
                        "dias_desde_fin_poliza":          r['dias_desde_fin'],
                        "dias_entre_ocurrencia_reporte":  r['dias_reporte'],
                        "historial_siniestros_asegurado": 0,
                        "monto_pagado":                   0.0,
                        "decision_analista":              "Pendiente",
                    }
                    resp = requests.post(
                        _sb_url("siniestros"),
                        data=json.dumps(nuevo_registro, default=str),
                        headers={**_sb_headers(), "Prefer": "return=minimal"},
                        timeout=15,
                    )
                    resp.raise_for_status()
                    st.success(f"✅ Siniestro guardado con ID: `{nuevo_id[:8]}...`")
                    del st.session_state['registrar_result']
                    load_data.clear()
                except Exception as e:
                    st.error(f"Error al guardar en Supabase: {e}")
        else:
            st.info("ℹ️ Configura SUPABASE_URL y SUPABASE_KEY en el .env para guardar el siniestro en la base de datos.")
