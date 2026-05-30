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
from src.utils.pdf_utils import get_docs_for_siniestro, render_pdf_iframe, get_pdf_bytes, analyze_pdf_with_gemini

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
    page_icon="🛡️",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Estilo global — tema oscuro tecnológico
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* Importar fuente tecnológica */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"]  {
        font-family: 'Inter', -apple-system, sans-serif;
    }

    /* Fondo principal con gradiente sutil */
    .stApp {
        background: radial-gradient(ellipse at top, #0f1729 0%, #0a0e1a 50%, #070a12 100%);
    }

    /* Sidebar oscuro con borde brillante */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d1424 0%, #0a0f1c 100%);
        border-right: 1px solid rgba(56, 189, 248, 0.15);
    }

    /* Títulos con gradiente */
    h1 {
        background: linear-gradient(90deg, #38bdf8 0%, #818cf8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-weight: 800 !important;
        letter-spacing: -0.02em;
    }
    h2, h3 { color: #e2e8f0 !important; font-weight: 700 !important; }

    /* Cards de métricas (st.metric) */
    div[data-testid="stMetric"] {
        background: linear-gradient(145deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.7) 100%);
        border: 1px solid rgba(56, 189, 248, 0.18);
        border-radius: 16px;
        padding: 18px 20px;
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255,255,255,0.04);
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-3px);
        border-color: rgba(56, 189, 248, 0.45);
        box-shadow: 0 8px 32px rgba(56, 189, 248, 0.12);
    }
    div[data-testid="stMetricValue"] {
        font-weight: 800 !important;
        font-size: 1.9rem !important;
        color: #f1f5f9 !important;
    }
    div[data-testid="stMetricLabel"] { color: #94a3b8 !important; font-weight: 500 !important; }

    /* Botones con glow */
    .stButton > button {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid rgba(56, 189, 248, 0.3);
        border-radius: 12px;
        color: #e2e8f0;
        font-weight: 600;
        padding: 10px 20px;
        transition: all 0.2s ease;
    }
    .stButton > button:hover {
        border-color: #38bdf8;
        box-shadow: 0 0 20px rgba(56, 189, 248, 0.35);
        color: #ffffff;
        transform: translateY(-1px);
    }

    /* Inputs y selects */
    .stSelectbox > div > div, .stMultiSelect > div > div {
        background-color: rgba(15, 23, 42, 0.6);
        border-radius: 10px;
        border: 1px solid rgba(148, 163, 184, 0.2);
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background: rgba(30, 41, 59, 0.5);
        border-radius: 10px 10px 0 0;
        padding: 8px 18px;
        color: #94a3b8;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(56, 189, 248, 0.15) !important;
        color: #38bdf8 !important;
    }

    /* Expanders */
    .streamlit-expanderHeader, details summary {
        background: rgba(30, 41, 59, 0.5) !important;
        border-radius: 10px !important;
        border: 1px solid rgba(148, 163, 184, 0.15) !important;
    }

    /* Radio del sidebar como menú de navegación */
    section[data-testid="stSidebar"] .stRadio > div {
        gap: 4px;
    }
    section[data-testid="stSidebar"] .stRadio label {
        padding: 8px 12px;
        border-radius: 10px;
        transition: background 0.15s ease;
    }
    section[data-testid="stSidebar"] .stRadio label:hover {
        background: rgba(56, 189, 248, 0.1);
    }

    /* Dataframe */
    .stDataFrame { border-radius: 12px; overflow: hidden; }

    /* Divisores más sutiles */
    hr { border-color: rgba(148, 163, 184, 0.12) !important; }

    /* Tarjeta de datos personalizada */
    .info-card {
        background: linear-gradient(145deg, rgba(30, 41, 59, 0.55) 0%, rgba(15, 23, 42, 0.55) 100%);
        border: 1px solid rgba(56, 189, 248, 0.15);
        border-radius: 16px;
        padding: 22px 26px;
        margin-bottom: 8px;
    }
    .info-card .row { padding: 7px 0; border-bottom: 1px solid rgba(148,163,184,0.08); display:flex; }
    .info-card .row:last-child { border-bottom: none; }
    .info-card .lbl { color: #64748b; font-size: 0.82rem; min-width: 150px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em; }
    .info-card .val { color: #e2e8f0; font-size: 0.95rem; font-weight: 500; }
    .info-card .mono { font-family: 'JetBrains Mono', monospace; color: #7dd3fc; }

    /* Badge de nivel de riesgo */
    .risk-badge {
        display: inline-block; padding: 6px 16px; border-radius: 999px;
        font-weight: 700; font-size: 0.85rem; letter-spacing: 0.04em;
    }
    .risk-rojo { background: rgba(239,68,68,0.15); color:#fca5a5; border:1px solid rgba(239,68,68,0.4); }
    .risk-amarillo { background: rgba(245,158,11,0.15); color:#fcd34d; border:1px solid rgba(245,158,11,0.4); }
    .risk-verde { background: rgba(34,197,94,0.15); color:#86efac; border:1px solid rgba(34,197,94,0.4); }
</style>
""", unsafe_allow_html=True)


# Plantilla oscura para los gráficos de Plotly
PLOTLY_DARK = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#cbd5e1", family="Inter"),
    margin=dict(t=30, b=10, l=10, r=10),
)


def clean_val(v, default="—"):
    """Limpia valores NaN / 'nan' / vacíos para mostrar en la UI."""
    if v is None:
        return default
    s = str(v).strip()
    if s == "" or s.lower() == "nan" or s.lower() == "none":
        return default
    return s


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
            aseg = sb_get("asegurados",  "id_asegurado,nombre_asegurado,perfil_riesgo,reclamos_rc_sin_tercero")
            veh  = sb_get("vehiculos",   "id_siniestro,placa,marca,modelo,anio,chasis,motor")

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
                # Unir datos de vehículo
                if veh:
                    df_veh_mini = pd.DataFrame(veh).rename(columns={
                        'placa': 'veh_placa', 'marca': 'veh_marca', 'modelo': 'veh_modelo',
                        'anio': 'veh_anio', 'chasis': 'chasis', 'motor': 'motor',
                    })
                    df_siniestros = df_siniestros.merge(df_veh_mini, on="id_siniestro", how="left")
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
            if 'reclamos_rc_sin_tercero' not in df_siniestros.columns:
                df_siniestros['reclamos_rc_sin_tercero'] = 0
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
st.sidebar.markdown("""
<div style="text-align:center; padding: 12px 0 18px 0;">
    <div style="font-size: 2.6rem; line-height:1;">🛡️</div>
    <div style="font-size:1.45rem; font-weight:800; background:linear-gradient(90deg,#38bdf8,#818cf8);
                -webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-top:6px;">
        Fraudia Claims
    </div>
    <div style="color:#64748b; font-size:0.8rem; font-weight:500; letter-spacing:0.05em; margin-top:2px;">
        ASEGURADORA DEL SUR
    </div>
    <div style="margin-top:10px;">
        <span style="background:rgba(34,197,94,0.15);color:#86efac;border:1px solid rgba(34,197,94,0.35);
                     padding:3px 10px;border-radius:999px;font-size:0.7rem;font-weight:600;">
            ● Sistema Antifraude IA
        </span>
    </div>
</div>
""", unsafe_allow_html=True)
st.sidebar.markdown("---")
page = st.sidebar.radio("Navegación", [
    "Dashboard Principal",
    "Detalle de Siniestro",
    "Inspector FRAUDIA (Asistente)",
    "Métricas del Modelo",
    "✍️ Registrar Siniestro",
], label_visibility="collapsed")

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
            color_discrete_map={"Rojo": "#ef4444", "Amarillo": "#f59e0b", "Verde": "#22c55e"},
            text='Cantidad',
        )
        fig.update_traces(textposition='outside', marker_line_width=0)
        fig.update_layout(**PLOTLY_DARK, showlegend=False)
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(showgrid=True, gridcolor="rgba(148,163,184,0.1)")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("Reclamos por Ramo")
        fig2 = px.pie(df, names='ramo', hole=0.55,
                      color_discrete_sequence=["#38bdf8", "#818cf8", "#c084fc", "#f472b6", "#fbbf24"])
        fig2.update_traces(textinfo='percent+label', marker_line_width=2,
                           marker_line_color="#0a0e1a")
        fig2.update_layout(**PLOTLY_DARK)
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

            nombre_aseg   = clean_val(row.get('nombre_asegurado'), clean_val(row.get('id_asegurado')))
            perfil_riesgo = clean_val(row.get('perfil_riesgo'), '')
            perfil_badge  = {"Alto": "🔴 Alto", "Medio": "🟡 Medio", "Bajo": "🟢 Bajo"}.get(perfil_riesgo, perfil_riesgo or '—')

            # Construir filas de la tarjeta (solo las que tienen valor)
            rows_html = []
            def add_row(lbl, val, mono=False):
                cls = "val mono" if mono else "val"
                rows_html.append(f'<div class="row"><div class="lbl">{lbl}</div><div class="{cls}">{val}</div></div>')

            add_row("Asegurado", f"{nombre_aseg} &nbsp;·&nbsp; Perfil: {perfil_badge}")
            add_row("Ramo / Cobertura", f"{clean_val(row.get('ramo'))} &nbsp;·&nbsp; {clean_val(row.get('cobertura'))}")

            # Vehículo — solo si realmente hay datos válidos
            placa  = clean_val(row.get('placa_vehiculo'), clean_val(row.get('veh_placa'), ''))
            marca  = clean_val(row.get('veh_marca'), '')
            modelo = clean_val(row.get('veh_modelo'), '')
            anio   = clean_val(row.get('veh_anio'), '')
            chasis = clean_val(row.get('chasis'), '')
            motor  = clean_val(row.get('motor'), '')
            if placa or marca:
                veh = []
                if marca and modelo: veh.append(f"{marca} {modelo} {anio}".strip())
                if placa:  veh.append(f"Placa <span class='mono'>{placa}</span>")
                if chasis: veh.append(f"Chasis <span class='mono'>{chasis}</span>")
                if motor:  veh.append(f"Motor <span class='mono'>{motor}</span>")
                add_row("Vehículo", " &nbsp;·&nbsp; ".join(veh))

            add_row("Fechas", f"Ocurrencia {clean_val(row.get('fecha_ocurrencia'))} &nbsp;→&nbsp; Reporte {clean_val(row.get('fecha_reporte'))}")
            add_row("Montos", f"Reclamado <span class='mono'>&#36;{row.get('monto_reclamado', 0):,.0f}</span> &nbsp;·&nbsp; Estimado <span class='mono'>&#36;{row.get('monto_estimado', 0):,.0f}</span>")
            add_row("Estado / Sucursal", f"{clean_val(row.get('estado'))} &nbsp;·&nbsp; {clean_val(row.get('sucursal'))}")

            nombre_prov = clean_val(row.get('nombre_proveedor'), clean_val(row.get('id_proveedor')))
            motivo_prov = clean_val(row.get('motivo_restriccion_proveedor'), '')
            prov_str    = nombre_prov + (f" &nbsp;<span style='color:#fca5a5'>⚠️ {motivo_prov}</span>" if motivo_prov else "")
            add_row("Proveedor", prov_str)

            parte = clean_val(row.get('numero_parte_policial'), '')
            if parte:
                add_row("N° Parte Policial", f"<span class='mono'>{parte}</span>")

            add_row("Descripción", clean_val(row.get('descripcion')))

            st.markdown(f'<div class="info-card">{"".join(rows_html)}</div>', unsafe_allow_html=True)

        with c2:
            st.subheader("Evaluación de Riesgo")
            nivel = row['nivel_riesgo']
            colores = {"Rojo": "#ef4444", "Amarillo": "#f59e0b", "Verde": "#22c55e"}
            cls_map = {"Rojo": "risk-rojo", "Amarillo": "risk-amarillo", "Verde": "risk-verde"}
            txt_map = {"Rojo": "ALTO RIESGO", "Amarillo": "REVISIÓN NECESARIA", "Verde": "RIESGO BAJO"}
            color = colores.get(nivel, "#64748b")
            score = row['score_final']
            st.markdown(f"""
            <div class="info-card" style="text-align:center; border-color:{color}55;">
                <div style="color:#64748b;font-size:0.8rem;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Score de Fraude</div>
                <div style="font-size:3.2rem;font-weight:800;color:{color};line-height:1.1;margin:6px 0;">{score:.0f}<span style="font-size:1.3rem;color:#475569;">/100</span></div>
                <div class="risk-badge {cls_map.get(nivel,'')}">● NIVEL {nivel.upper()} — {txt_map.get(nivel,'')}</div>
                <div style="margin-top:16px;height:8px;background:rgba(148,163,184,0.15);border-radius:999px;overflow:hidden;">
                    <div style="width:{min(score,100)}%;height:100%;background:linear-gradient(90deg,{color}88,{color});border-radius:999px;"></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

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

        # ----------------------------------------------------------------
        # DOCUMENTOS PDF DEL SINIESTRO
        # ----------------------------------------------------------------
        # Consultar documentos desde Supabase (con url_pdf)
        @st.cache_data(ttl=300)
        def fetch_docs_supabase(id_sin: str):
            if not _sb_configured():
                return []
            try:
                r = requests.get(
                    _sb_url("documentos", f"id_siniestro=eq.{id_sin}&select=*"),
                    headers=_sb_headers(), timeout=10,
                )
                r.raise_for_status()
                return r.json()
            except Exception:
                return []

        sb_docs  = fetch_docs_supabase(selected_id)
        docs_pdf = get_docs_for_siniestro(selected_id, sb_docs=sb_docs)

        if docs_pdf:
            st.markdown("---")
            st.subheader("📁 Documentos del Siniestro")
            fuente = "☁️ Supabase Storage" if sb_docs else "💾 Archivo local"
            st.caption(f"{len(docs_pdf)} documento(s) · Fuente: {fuente}")

            datos_doc = {
                "id_siniestro":          selected_id,
                "ramo":                  row.get("ramo"),
                "cobertura":             row.get("cobertura"),
                "fecha_ocurrencia":      row.get("fecha_ocurrencia"),
                "fecha_reporte":         row.get("fecha_reporte"),
                "monto_reclamado":       row.get("monto_reclamado", 0),
                "monto_estimado":        row.get("monto_estimado", 0),
                "placa_vehiculo":        row.get("placa_vehiculo", ""),
                "numero_parte_policial": row.get("numero_parte_policial", ""),
                "nombre_proveedor":      row.get("nombre_proveedor", ""),
                "descripcion":           row.get("descripcion", ""),
            }

            for doc in docs_pdf:
                with st.expander(f"{doc['tipo']}  —  {doc['nombre']}"):
                    tab_ver, tab_ia = st.tabs(["👁️ Ver documento", "🤖 Analizar con IA"])

                    with tab_ver:
                        st.markdown(
                            render_pdf_iframe(doc, height=620),
                            unsafe_allow_html=True,
                        )
                        try:
                            pdf_bytes_dl = get_pdf_bytes(doc)
                            st.download_button(
                                label="⬇️ Descargar PDF",
                                data=pdf_bytes_dl,
                                file_name=doc["nombre"],
                                mime="application/pdf",
                                key=f"dl_{doc['nombre']}",
                            )
                        except Exception:
                            pass

                    with tab_ia:
                        key_analisis = f"doc_analysis_{selected_id}_{doc['nombre']}"
                        if st.button(
                            "🔍 Analizar inconsistencias con Gemini",
                            key=f"btn_{doc['nombre']}",
                        ):
                            with st.spinner("Gemini está leyendo el documento y comparando con los datos registrados..."):
                                if "agent" not in st.session_state:
                                    st.session_state.agent = ClaimsAgent(df, get_supabase_client())
                                resultado = analyze_pdf_with_gemini(
                                    doc,
                                    datos_doc,
                                    st.session_state.agent.model,
                                )
                                st.session_state[key_analisis] = resultado

                        if key_analisis in st.session_state:
                            st.markdown(st.session_state[key_analisis])

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
        fig_fi = px.bar(fi.head(10), x='importance', y='feature', orientation='h',
                        color='importance', color_continuous_scale=["#1e3a5f", "#38bdf8"])
        fig_fi.update_layout(yaxis={'categoryorder': 'total ascending'},
                             coloraxis_showscale=False, **PLOTLY_DARK)
        fig_fi.update_xaxes(showgrid=True, gridcolor="rgba(148,163,184,0.1)")
        fig_fi.update_yaxes(showgrid=False)
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
