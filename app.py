"""
app.py — Entry point do ConciliaAI
Aplicação Streamlit com navegação lateral e roteamento entre páginas.
"""

import streamlit as st

# Configuração da página — deve ser a primeira chamada Streamlit
st.set_page_config(
    page_title="ConciliaAI",
    page_icon="🔀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS global
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

h1, h2, h3, h4, h5, h6 {
    font-family: 'Outfit', sans-serif !important;
    color: #000B3D !important;
    font-weight: 700 !important;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: #000B3D;
    border-right: 1px solid #C5A88033;
}
[data-testid="stSidebar"] .stButton button {
    width: 100%;
    text-align: left !important;
    background: transparent;
    border: none;
    color: #E2E8F0 !important;
    font-size: 0.95rem;
    padding: 0.6rem 1rem;
    border-radius: 6px;
    transition: all 0.25s ease;
    font-family: 'Inter', sans-serif;
    display: flex !important;
    justify-content: flex-start !important;
    align-items: center !important;
    gap: 10px !important;
}
[data-testid="stSidebar"] .stButton button div[data-testid="stMarkdownContainer"] {
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    width: 100% !important;
}
[data-testid="stSidebar"] .stButton button p {
    display: flex !important;
    align-items: center !important;
    gap: 10px !important;
    margin: 0 !important;
    padding: 0 !important;
    font-size: 0.95rem !important;
    font-weight: 500 !important;
    color: #E2E8F0 !important;
}
[data-testid="stSidebar"] .stButton button * {
    color: #E2E8F0 !important;
    text-align: left !important;
}
[data-testid="stSidebar"] .stButton button:hover {
    background: rgba(197, 168, 128, 0.15) !important;
    color: #FFFFFF !important;
}
[data-testid="stSidebar"] .stButton button:hover * {
    color: #FFFFFF !important;
}

/* Botão ativo */
.nav-active button {
    background: rgba(197, 168, 128, 0.25) !important;
    color: #C5A880 !important;
    border-left: 4px solid #C5A880 !important;
    font-weight: 600 !important;
    border-radius: 0px 6px 6px 0px !important;
}
.nav-active button * {
    color: #C5A880 !important;
    font-weight: 600 !important;
}

/* Botões primários */
.stButton button[kind="primary"] {
    background: #000B3D;
    color: #FFFFFF;
    border: 1px solid #C5A880;
    font-weight: 600;
    border-radius: 4px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    font-size: 0.85rem;
    transition: all 0.2s ease;
}
.stButton button[kind="primary"]:hover {
    background: #C5A880;
    color: #000B3D;
    box-shadow: 0 4px 12px rgba(197, 168, 128, 0.2);
}

/* Botões secundários */
.stButton button[kind="secondary"] {
    background: transparent;
    color: #000B3D;
    border: 1px solid #000B3D;
    font-weight: 500;
    border-radius: 4px;
    transition: all 0.2s ease;
}
.stButton button[kind="secondary"]:hover {
    background: rgba(0, 11, 61, 0.05);
    border-color: #C5A880;
    color: #C5A880;
}

/* Divisor */
hr { border-color: #C5A88033 !important; }

/* Expanders */
details summary { color: #000B3D !important; font-weight: 600; }

/* Dataframes */
[data-testid="stDataFrame"] { 
    border-radius: 8px; 
    overflow: hidden; 
    border: 1px solid #E5E7EB;
}

/* Métricas */
[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #C5A88044;
    border-radius: 6px;
    padding: 1rem;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.03), 0 2px 4px -1px rgba(0, 0, 0, 0.02);
}

[data-testid="stMetric"] label {
    color: #4B5563 !important;
    font-family: 'Outfit', sans-serif !important;
    font-weight: 500 !important;
}

[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: #000B3D !important;
    font-family: 'Outfit', sans-serif !important;
    font-weight: 700 !important;
}

/* Alertas */
[data-testid="stAlert"] { border-radius: 8px; border-left: 4px solid #C5A880; }

/* Status box */
[data-testid="stStatus"] { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# ── Inicialização ──────────────────────────────────────────────────────────────
from database.db import init_db
from pathlib import Path

# Garante que o banco e diretórios existam
init_db()
Path("outputs").mkdir(exist_ok=True)
Path("logs").mkdir(exist_ok=True)

# ── Navegação ──────────────────────────────────────────────────────────────────
if "current_page" not in st.session_state:
    st.session_state["current_page"] = "Início"

PAGES = {
    "Início":              ("🏠", "ui.home"),
    "Nova Conciliação":    ("➕", "ui.new_reconciliation"),
    "Nova Automação":      ("⚡", "ui.new_automation"),
    "Meus Workflows":      ("📂", "ui.my_workflows"),
    "Executar Workflow":   ("▶️", "ui.execute_workflow"),
    "Agendar Conciliação": ("⏰", "ui.schedule_reconciliation"),
    "Histórico":           ("📋", "ui.history"),
    "Configurações":       ("⚙️", "ui.settings"),
}

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:1.2rem 0.5rem 1rem; border-bottom: 1px solid rgba(197,168,128,0.2); margin-bottom: 1rem;">
        <div style="font-family:'Outfit', sans-serif; font-size:1.65rem; font-weight:800; color:#FFFFFF; display:flex; align-items:center; gap: 8px;">
            <span style="color:#C5A880;">Safra</span> Concilia
        </div>
        <div style="color:#E5E7EB; font-family:'Inter', sans-serif; font-size:0.7rem; letter-spacing: 0.12em; text-transform: uppercase; margin-top:0.2rem;">Intelligent Operations</div>
    </div>
    """, unsafe_allow_html=True)

    for page_name, (icon, _) in PAGES.items():
        is_active = st.session_state["current_page"] == page_name
        container = st.container()
        if is_active:
            container.markdown('<div class="nav-active">', unsafe_allow_html=True)
        with container:
            if st.button(f"{icon} {page_name}", key=f"nav_{page_name}"):
                st.session_state["current_page"] = page_name
                # Limpa estado de execução ao trocar de página
                for k in ["exec_result","exec_wf","exec_input_meta","agent2_analysis","exec_saved"]:
                    st.session_state.pop(k, None)
                st.rerun()
        if is_active:
            container.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<hr style='margin: 1.5rem 0 1rem 0; border-color: rgba(197, 168, 128, 0.2) !important;'>", unsafe_allow_html=True)

    # Status das APIs
    from core.config import load_config
    cfg = load_config()
    st.markdown("<div style='color:#FFFFFF; font-family:\"Inter\", sans-serif; font-size:0.75rem; font-weight:700; padding:0.3rem 0.5rem; text-transform:uppercase; letter-spacing:0.05em;'>Status das APIs</div>",
                unsafe_allow_html=True)
    for provider, key_field in [("Anthropic","anthropic_api_key"),
                                  ("Google","google_api_key"),
                                  ("OpenAI","openai_api_key")]:
        has_key = bool(cfg.get(key_field,"").strip())
        icon = "🟢" if has_key else "⚪"
        color = "#FFFFFF" if has_key else "rgba(255, 255, 255, 0.45)"
        st.markdown(
            f"<div style='color:{color}; font-family:\"Inter\", sans-serif; font-size:0.8rem; padding:0.2rem 0.5rem; display:flex; align-items:center; gap:6px;'>"
            f"<span>{icon}</span> <span>{provider}</span></div>",
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        "<div style='color:#C5A880; font-family:\"Inter\", sans-serif; font-size:0.7rem; font-weight:500; text-align:center; opacity:0.8; letter-spacing:0.05em;'>🔒 AMBIENTE 100% SEGURO</div>",
        unsafe_allow_html=True
    )

# ── Roteamento ─────────────────────────────────────────────────────────────────
current = st.session_state["current_page"]

import importlib
_, module_path = PAGES[current]
module = importlib.import_module(module_path)
module.render()
