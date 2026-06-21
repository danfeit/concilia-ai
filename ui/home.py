"""
pages/home.py — Tela de Início do ConciliaAI
"""

import streamlit as st
from database.db import get_stats
from core.config import load_config


def render():
    st.markdown("""
    <style>
    .metric-card {
        background: #FFFFFF;
        border: 1px solid #C5A88044;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.03), 0 2px 4px -1px rgba(0, 0, 0, 0.02);
        height: 130px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
    }
    .metric-value { font-size: 2.2rem; font-weight: 800; color: #000B3D; font-family: 'Outfit', sans-serif; line-height: 1.2; }
    .metric-label { font-size: 0.85rem; color: #4B5563; margin-top: 0.25rem; font-family: 'Inter', sans-serif; }
    .hero-title {
        font-family: 'Outfit', sans-serif;
        font-size: 3rem; font-weight: 800;
        color: #000B3D;
    }
    .hero-title span {
        color: #C5A880;
    }
    .feature-card {
        background: #FFFFFF; 
        border: 1px solid #C5A88022;
        border-radius: 8px; 
        padding: 1rem 1.2rem; 
        margin: 0.4rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.01);
    }
    </style>
    """, unsafe_allow_html=True)

    # ── Hero ─────────────────────────────────────────────────────────────────
    col_logo, col_text = st.columns([1, 4])
    with col_text:
        st.markdown('<div class="hero-title"><span>KoreBI</span> Concilia</div>', unsafe_allow_html=True)
        st.markdown(
            "<p style='color:#4B5563; font-size:1.15rem; font-family: \"Inter\", sans-serif;'>"
            "Conciliação e Automação inteligente de dados assistida por IA — "
            "sem código, sem planilhas manuais, com rastreabilidade total.</p>",
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Alerta de API ─────────────────────────────────────────────────────────
    cfg = load_config()
    has_key = any([
        cfg.get("anthropic_api_key", "").strip(),
        cfg.get("google_api_key", "").strip(),
        cfg.get("openai_api_key", "").strip(),
    ])
    if not has_key:
        st.warning(
            "⚠️ Nenhuma chave de API configurada. "
            "Configure em **⚙️ Configurações** antes de criar workflows.",
            icon="🔑",
        )

    # ── Métricas ──────────────────────────────────────────────────────────────
    stats = get_stats()
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{stats['total_workflows']}</div>
            <div class="metric-label">Workflows Salvos</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{stats['total_executions']}</div>
            <div class="metric-label">Execuções Realizadas</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        last = stats.get("last_execution") or "—"
        if last != "—":
            last = last[:16].replace("T", " ")
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value" style="font-size:1.4rem;">{last}</div>
            <div class="metric-label">Última Execução</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Ações Rápidas ─────────────────────────────────────────────────────────
    st.subheader("🚀 Ações Rápidas")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("➕ Nova Conciliação", use_container_width=True, type="primary"):
            st.session_state["current_page"] = "Nova Conciliação"
            st.rerun()
    with col_b:
        if st.button("▶️ Executar Workflow", use_container_width=True):
            st.session_state["current_page"] = "Executar Workflow"
            st.rerun()
    with col_c:
        if st.button("📂 Meus Workflows", use_container_width=True):
            st.session_state["current_page"] = "Meus Workflows"
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Como Funciona ─────────────────────────────────────────────────────────
    st.subheader("💡 Como Funciona")
    steps = [
        ("1️⃣", "Upload dos Arquivos", "Suba de 2 a 5 arquivos (CSV, Excel, JSON, Parquet, TXT ou PDF de sistemas legados)."),
        ("2️⃣", "IA Analisa a Estrutura", "O Agente 1 mapeia schemas, identifica chaves de relacionamento e detecta a arquitetura de arquivos legados."),
        ("3️⃣", "Código Python Gerado", "O agente gera um script completo de conciliação, incluindo parsers para arquivos não estruturados."),
        ("4️⃣", "Salve como Workflow", "Dê um nome, adicione tags e salve para reutilização futura com novos arquivos."),
        ("5️⃣", "Execute e Analise", "Execute o workflow, veja os resultados e deixe o Agente 2 gerar uma análise executiva."),
    ]
    for icon, title, desc in steps:
        st.markdown(f"""
        <div class="feature-card">
            <strong style="color: #000B3D; font-family: 'Outfit', sans-serif;">{icon} {title}</strong><br>
            <span style="color:#4B5563; font-size:0.9rem; font-family: 'Inter', sans-serif;">{desc}</span>
        </div>""", unsafe_allow_html=True)
