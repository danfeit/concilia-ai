"""
pages/settings.py — Tela de Configurações do ConciliaAI
"""

import json
import streamlit as st
from core.config import load_config, save_config, export_config_without_keys
from agents.base_agent import test_connection

MODELS = {
    "anthropic": ["claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-4-5"],
    "google":    [
        "gemini-3.0-pro", 
        "gemini-2.5-pro", 
        "gemini-3.5-flash", 
        "gemini-2.5-flash", 
        "gemini-3.1-flash-lite", 
        "gemini-2.5-flash-lite", 
        "gemini-2.5-flash-live"
    ],
    "openai":    ["gpt-5.4-mini", "gpt-4o", "gpt-4o-mini", "o1", "o1-mini", "o3-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"],
}


def render():
    st.title("⚙️ Configurações")
    cfg = load_config()
    changed = False

    # ── Provedores de IA ──────────────────────────────────────────────────────
    st.subheader("🤖 Provedores de IA")
    tab_ant, tab_goo, tab_oai = st.tabs(["Anthropic", "Google", "OpenAI"])

    with tab_ant:
        key_ant = st.text_input("Chave de API Anthropic", value=cfg.get("anthropic_api_key", ""),
                                type="password", key="ant_key")
        if st.button("🔌 Testar conexão", key="test_ant"):
            if key_ant.strip():
                with st.spinner("Testando..."):
                    ok, msg = test_connection("anthropic", key_ant, MODELS["anthropic"][-1])
                st.success(msg) if ok else st.error(msg)
            else:
                st.warning("Informe a chave antes de testar.")
        cfg["anthropic_api_key"] = key_ant

    with tab_goo:
        key_goo = st.text_input("Chave de API Google", value=cfg.get("google_api_key", ""),
                                type="password", key="goo_key")
        if st.button("🔌 Testar conexão", key="test_goo"):
            if key_goo.strip():
                with st.spinner("Testando..."):
                    ok, msg = test_connection("google", key_goo, MODELS["google"][1])
                st.success(msg) if ok else st.error(msg)
            else:
                st.warning("Informe a chave antes de testar.")
        cfg["google_api_key"] = key_goo

    with tab_oai:
        key_oai = st.text_input("Chave de API OpenAI", value=cfg.get("openai_api_key", ""),
                                type="password", key="oai_key")
        if st.button("🔌 Testar conexão", key="test_oai"):
            if key_oai.strip():
                with st.spinner("Testando..."):
                    ok, msg = test_connection("openai", key_oai, MODELS["openai"][0])
                st.success(msg) if ok else st.error(msg)
            else:
                st.warning("Informe a chave antes de testar.")
        cfg["openai_api_key"] = key_oai

    st.divider()

    # ── Configuração dos Agentes ──────────────────────────────────────────────
    st.subheader("🧠 Configuração dos Agentes")

    row1_col1, row1_col2 = st.columns(2)

    with row1_col1:
        st.markdown("**Agente 1 — Gerador de Código**")
        a1_prov = st.selectbox("Provedor", ["anthropic", "google", "openai"],
                               index=["anthropic","google","openai"].index(cfg.get("agent1_provider","anthropic")),
                               key="a1_prov")
        a1_model = st.selectbox("Modelo", MODELS[a1_prov],
                                index=min(MODELS[a1_prov].index(cfg.get("agent1_model", MODELS[a1_prov][0]))
                                          if cfg.get("agent1_model") in MODELS[a1_prov] else 0,
                                          len(MODELS[a1_prov])-1),
                                key="a1_model")
        a1_temp = st.slider("Temperatura", 0.0, 1.0, float(cfg.get("agent1_temperature", 0.2)),
                            step=0.05, key="a1_temp",
                            help="Baixo = mais determinístico (recomendado para código)")
        a1_pct = st.slider("Amostragem dos dados (%)", 10, 50,
                           int(cfg.get("agent1_sample_pct", 0.20)*100), step=5, key="a1_pct")
        a1_sys = st.text_area("Instruções adicionais do sistema",
                              value=cfg.get("agent1_system_instructions",""), key="a1_sys", height=80)

        cfg.update({"agent1_provider": a1_prov, "agent1_model": a1_model,
                    "agent1_temperature": a1_temp, "agent1_sample_pct": a1_pct/100,
                    "agent1_system_instructions": a1_sys})

    with row1_col2:
        st.markdown("**Agente 2 — Analista (Resultados)**")
        a2_prov = st.selectbox("Provedor", ["anthropic", "google", "openai"],
                               index=["anthropic","google","openai"].index(cfg.get("agent2_provider","anthropic")),
                               key="a2_prov")
        a2_model = st.selectbox("Modelo", MODELS[a2_prov],
                                index=min(MODELS[a2_prov].index(cfg.get("agent2_model", MODELS[a2_prov][0]))
                                          if cfg.get("agent2_model") in MODELS[a2_prov] else 0,
                                          len(MODELS[a2_prov])-1),
                                key="a2_model")
        a2_temp = st.slider("Temperatura", 0.0, 1.0, float(cfg.get("agent2_temperature", 0.5)),
                            step=0.05, key="a2_temp",
                            help="Mais alto = análise mais criativa")
        a2_sys = st.text_area("Instruções adicionais do sistema",
                              value=cfg.get("agent2_system_instructions",""), key="a2_sys", height=80)
        a2_next = st.checkbox("Incluir próximos passos",
                              value=cfg.get("agent2_include_next_steps", True), key="a2_next")
        a2_anom = st.checkbox("Incluir alertas anomalias",
                              value=cfg.get("agent2_include_anomalies", True), key="a2_anom")

        cfg.update({"agent2_provider": a2_prov, "agent2_model": a2_model,
                    "agent2_temperature": a2_temp, "agent2_system_instructions": a2_sys,
                    "agent2_include_next_steps": a2_next, "agent2_include_anomalies": a2_anom})

    st.markdown("<br>", unsafe_allow_html=True)
    row2_col1, row2_col2 = st.columns(2)

    with row2_col1:
        st.markdown("**Agente 3 — Auto-Correção**")
        a3_prov = st.selectbox("Provedor", ["anthropic", "google", "openai"],
                               index=["anthropic","google","openai"].index(cfg.get("agent3_provider","google")),
                               key="a3_prov")
        a3_model = st.selectbox("Modelo", MODELS[a3_prov],
                                index=min(MODELS[a3_prov].index(cfg.get("agent3_model", MODELS[a3_prov][0]))
                                          if cfg.get("agent3_model") in MODELS[a3_prov] else 0,
                                          len(MODELS[a3_prov])-1),
                                key="a3_model")
        a3_temp = st.slider("Temperatura", 0.0, 1.0, float(cfg.get("agent3_temperature", 0.1)),
                            step=0.05, key="a3_temp",
                            help="Baixo = mais determinístico (para correções exatas)")
        a3_sys = st.text_area("Instruções adicionais do sistema",
                              value=cfg.get("agent3_system_instructions",""), key="a3_sys", height=80)

        cfg.update({"agent3_provider": a3_prov, "agent3_model": a3_model,
                    "agent3_temperature": a3_temp, "agent3_system_instructions": a3_sys})

    with row2_col2:
        st.markdown("**Agente 4 — Automação & ETL**")
        a4_prov = st.selectbox("Provedor", ["anthropic", "google", "openai"],
                               index=["anthropic","google","openai"].index(cfg.get("agent4_provider","google")),
                               key="a4_prov")
        a4_model = st.selectbox("Modelo", MODELS[a4_prov],
                                index=min(MODELS[a4_prov].index(cfg.get("agent4_model", MODELS[a4_prov][0]))
                                          if cfg.get("agent4_model") in MODELS[a4_prov] else 0,
                                          len(MODELS[a4_prov])-1),
                                key="a4_model")
        a4_temp = st.slider("Temperatura", 0.0, 1.0, float(cfg.get("agent4_temperature", 0.2)),
                            step=0.05, key="a4_temp",
                            help="Baixo = mais determinístico (para código e ETL exatos)")
        a4_sys = st.text_area("Instruções adicionais do sistema",
                              value=cfg.get("agent4_system_instructions",""), key="a4_sys", height=80)

        cfg.update({"agent4_provider": a4_prov, "agent4_model": a4_model,
                    "agent4_temperature": a4_temp, "agent4_system_instructions": a4_sys})

    st.divider()

    # ── Preferências Gerais ───────────────────────────────────────────────────
    st.subheader("⚙️ Preferências Gerais")
    col3, col4 = st.columns(2)

    with col3:
        timeout = st.selectbox("Timeout de execução (minutos)", [1, 3, 5, 10],
                               index=[1,3,5,10].index(cfg.get("timeout_minutes",5)), key="timeout")
        output_dir = st.text_input("Diretório de saída", value=cfg.get("output_dir","outputs"), key="outdir")
        cfg.update({"timeout_minutes": timeout, "output_dir": output_dir})

    with col4:
        save_copies = st.checkbox("Salvar cópia dos arquivos de entrada em cada execução",
                                  value=cfg.get("save_input_copies", False), key="save_copies")
        cfg["save_input_copies"] = save_copies

    st.divider()

    # ── Botões de ação ────────────────────────────────────────────────────────
    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("💾 Salvar Configurações", type="primary", use_container_width=True):
            save_config(cfg)
            st.success("✅ Configurações salvas com sucesso!")

    with b2:
        if st.button("📤 Exportar (sem chaves)", use_container_width=True):
            safe = export_config_without_keys(cfg)
            st.download_button(
                "⬇️ Baixar config_backup.json",
                data=json.dumps(safe, indent=2, ensure_ascii=False),
                file_name="config_backup.json",
                mime="application/json",
            )

    with b3:
        if st.button("🔄 Restaurar Padrões", use_container_width=True):
            from core.config import DEFAULTS, save_config as sc
            sc(DEFAULTS.copy())
            st.success("Padrões restaurados. Recarregue a página.")
