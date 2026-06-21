"""
pages/new_reconciliation.py — Wizard de Nova Conciliação (4 etapas).
Etapa 1: Upload → Etapa 2: Análise IA → Etapa 3: Código → Etapa 4: Salvar
"""

from __future__ import annotations
import io
import json
import tempfile
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from core.config import load_config
from core.file_handler import read_file, get_file_info, compute_md5
from core.sampler import sample_dataframe, sample_text, describe_dataframe
from core.schema_validator import check_syntax
from agents.structure_agent import analyze_structure
from agents.codegen_agent import generate_code, generate_summary
from database.db import save_workflow, get_workflow_by_name


def render():
    st.title("➕ Nova Conciliação")

    # Estado do wizard
    if "wizard_step" not in st.session_state:
        st.session_state.wizard_step = 1
    if "wizard_files" not in st.session_state:
        st.session_state.wizard_files = []
    if "wizard_analysis" not in st.session_state:
        st.session_state.wizard_analysis = None
    if "wizard_code" not in st.session_state:
        st.session_state.wizard_code = ""
    if "wizard_summary" not in st.session_state:
        st.session_state.wizard_summary = ""
    if "wizard_objective" not in st.session_state:
        st.session_state.wizard_objective = ""

    _render_progress_bar()

    step = st.session_state.wizard_step
    if step == 1:
        _step1_upload()
    elif step == 2:
        _step2_analysis()
    elif step == 3:
        _step3_code()
    elif step == 4:
        _step4_save()


def _render_progress_bar():
    step = st.session_state.wizard_step
    labels = ["1 Upload", "2 Análise IA", "3 Código", "4 Salvar"]
    cols = st.columns(4)
    for i, (col, label) in enumerate(zip(cols, labels), 1):
        with col:
            color = "#000B3D" if i <= step else "#F3F4F6"
            text_color = "#C5A880" if i <= step else "#9CA3AF"
            border = "1px solid #C5A880" if i <= step else "1px solid #E5E7EB"
            st.markdown(
                f'<div style="background:{color};color:{text_color};border:{border};padding:8px;'
                f'border-radius:4px;text-align:center;font-size:0.85rem;font-weight:600;font-family:\'Outfit\',sans-serif;">'
                f'{label}</div>',
                unsafe_allow_html=True,
            )
    st.markdown("<br>", unsafe_allow_html=True)


# ─── ETAPA 1: UPLOAD ──────────────────────────────────────────────────────────

def _step1_upload():
    st.subheader("📂 Etapa 1 — Upload dos Arquivos")

    uploaded = st.file_uploader(
        "Arraste ou selecione os arquivos (mín. 2, máx. 5)",
        accept_multiple_files=True,
        type=["csv","xlsx","xls","json","parquet","txt","pdf"],
        key="uploader_step1",
    )

    if uploaded:
        if len(uploaded) < 2:
            st.warning("⚠️ Envie pelo menos **2 arquivos** para prosseguir.")
        elif len(uploaded) > 5:
            st.error("❌ Máximo de **5 arquivos** por conciliação no MVP.")
        else:
            files_data = []
            valid = True
            for up in uploaded:
                raw = up.read()
                df, ftype, meta = read_file(raw, up.name)
                info = get_file_info(df, meta, raw)
                files_data.append({
                    "name": up.name,
                    "bytes": raw,
                    "df": df,
                    "type": ftype,
                    "meta": meta,
                    "info": info,
                })

                # Card de preview por arquivo
                with st.expander(f"📄 {up.name} — {info['size_kb']} KB", expanded=True):
                    col_a, col_b = st.columns([2, 3])
                    with col_a:
                        st.markdown(f"**Tipo:** `{ftype}`")
                        if info.get("is_legacy"):
                            st.markdown("**Formato:** 🗂️ Arquivo Legado (TXT/PDF)")
                            st.markdown(f"**Linhas de texto:** {info.get('line_count', '?')}")
                            if info.get("page_count"):
                                st.markdown(f"**Páginas:** {info['page_count']}")
                        else:
                            st.markdown(f"**Linhas:** {info.get('rows', '?')}")
                            st.markdown(f"**Colunas:** {info.get('cols', '?')}")
                        st.markdown(f"**MD5:** `{info['md5'][:12]}...`")

                    with col_b:
                        if df is not None:
                            st.dataframe(df.head(5), use_container_width=True)
                        else:
                            preview = "\n".join(meta.get("preview_lines", [])[:15])
                            st.code(preview, language=None)

            if valid and len(files_data) >= 2:
                st.markdown("<br>", unsafe_allow_html=True)
                objective = st.text_area(
                    "📝 Descreva o objetivo desta conciliação",
                    value=st.session_state.wizard_objective,
                    placeholder="Ex: Quero cruzar os pagamentos do banco com as notas fiscais emitidas e identificar divergências",
                    height=100,
                    key="objective_input",
                )

                if st.button("Analisar Arquivos →", type="primary", use_container_width=False,
                             disabled=not objective.strip()):
                    if not objective.strip():
                        st.warning("Descreva o objetivo da conciliação antes de prosseguir.")
                    else:
                        st.session_state.wizard_files = files_data
                        st.session_state.wizard_objective = objective
                        st.session_state.wizard_step = 2
                        st.rerun()


# ─── ETAPA 2: ANÁLISE IA ─────────────────────────────────────────────────────

def _step2_analysis():
    st.subheader("🧠 Etapa 2 — Análise pela IA")

    cfg = load_config()
    files_data = st.session_state.wizard_files

    # Se ainda não tem análise, executa o agente
    if st.session_state.wizard_analysis is None:
        with st.spinner("🔍 Agente 1 analisando a estrutura dos arquivos..."):
            try:
                sample_pct = cfg.get("agent1_sample_pct", 0.20)
                files_for_agent = []
                for fd in files_data:
                    entry = {"filename": fd["name"], "type": fd["type"],
                             "is_legacy": fd["info"].get("is_legacy", False)}
                    if fd["df"] is not None:
                        sampled = sample_dataframe(fd["df"], sample_pct)
                        entry["sample"] = describe_dataframe(sampled)
                    else:
                        entry["raw_text_sample"] = sample_text(
                            fd["meta"].get("raw_text", ""), sample_pct
                        )
                    files_for_agent.append(entry)

                analysis = analyze_structure(files_for_agent,
                                            st.session_state.wizard_objective, cfg)
                st.session_state.wizard_analysis = analysis
            except Exception as e:
                err_msg = str(e)
                if "dunning" in err_msg.lower() or "billing" in err_msg.lower() or "403" in err_msg:
                    st.error("❌ Erro de Faturamento / Permissão da API (403 Forbidden)")
                    st.markdown(
                        "⚠️ A chave de API configurada retornou um erro de faturamento suspenso ou bloqueado (**dunning decision is deny**).\n\n"
                        "**Como resolver:**\n"
                        "1. Acesse a página **⚙️ Configurações** no menu lateral.\n"
                        "2. Verifique se a chave do provedor ativo está correta.\n"
                        "3. Verifique se o faturamento no painel do provedor (Google AI Studio ou Google Cloud Platform) está ativo e sem faturas pendentes."
                    )
                else:
                    st.error(f"❌ Erro ao chamar o agente: {e}")
                if st.button("← Voltar ao Upload"):
                    st.session_state.wizard_step = 1
                    st.rerun()
                return

    analysis = st.session_state.wizard_analysis

    if "error" in analysis:
        st.error(f"❌ Agente retornou erro: {analysis.get('error')}")
        with st.expander("Resposta bruta"):
            st.text(analysis.get("raw", ""))
        if st.button("← Voltar"):
            st.session_state.wizard_step = 1
            st.session_state.wizard_analysis = None
            st.rerun()
        return

    # ── Exibição dos resultados ───────────────────────────────────────────────
    st.success("✅ Análise concluída!")

    # Arquivos detectados
    st.markdown("### 📋 Arquivos Detectados")
    for f in analysis.get("files", []):
        with st.expander(f"📄 {f.get('filename', '?')}", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Tipo detectado:** `{f.get('type', '?')}`")
                cols = f.get("detected_columns", [])
                if cols:
                    st.markdown(f"**Colunas:** {', '.join(str(c) for c in cols[:10])}")
                keys = f.get("key_columns", [])
                if keys:
                    st.markdown(f"**Chaves candidatas:** {', '.join(str(k) for k in keys)}")
            with col2:
                alerts = f.get("quality_alerts", [])
                if alerts:
                    st.markdown("**⚠️ Alertas de qualidade:**")
                    for a in alerts:
                        st.markdown(f"- {a}")
                legacy = f.get("legacy_architecture", {})
                if legacy and legacy.get("description"):
                    st.markdown(f"**🗂️ Arquitetura legada:** {legacy['description']}")

    # Chaves de relacionamento
    st.markdown("### 🔗 Chaves de Relacionamento Sugeridas")
    keys = analysis.get("relationship_keys", [])
    if keys:
        conf_colors = {"alto": "🟢", "médio": "🟡", "baixo": "🔴"}
        for k in keys:
            conf = k.get("confidence", "?")
            icon = conf_colors.get(conf, "⚪")
            st.markdown(
                f"{icon} **`{k.get('key')}`** — "
                f"Arquivo A: `{k.get('file_a_column')}` ↔ "
                f"Arquivo B: `{k.get('file_b_column')}` "
                f"*(Confiança: {conf})*"
            )
    else:
        st.info("Nenhuma chave de relacionamento identificada automaticamente.")

    # Alertas gerais
    quality_alerts = analysis.get("quality_alerts", [])
    if quality_alerts:
        st.markdown("### ⚠️ Alertas de Qualidade Geral")
        for a in quality_alerts:
            st.warning(a)

    # Estratégia
    st.markdown("### 🎯 Estratégia Proposta")
    st.info(analysis.get("strategy", "Estratégia não definida."))

    st.markdown("<br>", unsafe_allow_html=True)
    col_back, col_fwd = st.columns([1, 3])
    with col_back:
        if st.button("← Voltar"):
            st.session_state.wizard_step = 1
            st.session_state.wizard_analysis = None
            st.rerun()
    with col_fwd:
        if st.button("Gerar Código Python →", type="primary"):
            st.session_state.wizard_step = 3
            st.session_state.wizard_code = ""
            st.rerun()


# ─── ETAPA 3: CÓDIGO ─────────────────────────────────────────────────────────

def _step3_code():
    st.subheader("⚙️ Etapa 3 — Código Python Gerado")

    cfg = load_config()
    analysis = st.session_state.wizard_analysis

    # Ajustes do usuário
    adjustments = st.text_area(
        "💬 Algum ajuste ou instrução adicional para o agente? (opcional)",
        value="",
        placeholder="Ex: Use tolerância de R$ 0,01 em valores monetários. Ignore diferenças de CNPJ com/sem pontuação.",
        height=70,
        key="adj_input",
    )

    # Gera o código se ainda não existe
    if not st.session_state.wizard_code:
        with st.spinner("⚙️ Gerando script Python de conciliação..."):
            try:
                result = generate_code(analysis, st.session_state.wizard_objective,
                                       adjustments, cfg)
                code = result["code"]

                # Verifica sintaxe
                ok, syntax_err = check_syntax(code)
                if not ok:
                    st.warning(f"⚠️ Erro de sintaxe detectado: {syntax_err}. Tentando corrigir...")
                    fix_adj = f"Corrija o seguinte erro de sintaxe e retorne o código corrigido: {syntax_err}"
                    result = generate_code(analysis, st.session_state.wizard_objective, fix_adj, cfg)
                    code = result["code"]

                st.session_state.wizard_code = code

                # Gera resumo
                with st.spinner("Gerando resumo em linguagem natural..."):
                    summary = generate_summary(code, analysis, cfg)
                    st.session_state.wizard_summary = summary
            except Exception as e:
                st.error(f"❌ Erro ao gerar código: {e}")
                if st.button("← Voltar"):
                    st.session_state.wizard_step = 2
                    st.rerun()
                return

    code = st.session_state.wizard_code

    # Resumo em linguagem natural
    st.markdown("### 📖 O que este script faz")
    st.info(st.session_state.wizard_summary)

    # Checklist de validações
    st.markdown("### ✅ Validações Implementadas")
    checks = [
        "Verifica existência e integridade dos arquivos de entrada",
        "Trata múltiplos encodings automaticamente (UTF-8, Latin-1, CP1252)",
        "Normaliza colunas chave (strip, lower, remoção de acentos)",
        "Valida schema antes de processar",
        "Gera arquivo Excel de saída com 4 abas estruturadas",
        "Salva log JSON da execução (timestamps, totais, erros)",
        "Captura exceções com mensagens descritivas",
    ]
    if any(f.get("is_legacy") for f in st.session_state.wizard_files):
        checks.insert(1, "Parser específico para arquivo(s) de sistema legado (TXT/PDF)")

    for c in checks:
        st.markdown(f"✅ {c}")

    # Editor de código
    st.markdown("### 🖊️ Código Gerado (editável)")
    with st.expander("Ver e editar o código Python", expanded=False):
        edited_code = st.text_area("Código Python", value=code, height=500, key="code_editor")
        if edited_code != code:
            ok, err = check_syntax(edited_code)
            if ok:
                st.session_state.wizard_code = edited_code
                st.success("✅ Sintaxe válida")
            else:
                st.error(f"❌ {err}")

    st.markdown("<br>", unsafe_allow_html=True)
    col_back, col_regen, col_fwd = st.columns([1, 2, 2])

    with col_back:
        if st.button("← Voltar"):
            st.session_state.wizard_step = 2
            st.session_state.wizard_code = ""
            st.rerun()

    with col_regen:
        if st.button("⚠️ Regenerar com ajustes"):
            st.session_state.wizard_code = ""
            st.rerun()

    with col_fwd:
        if st.button("✅ Aprovar e Salvar Workflow →", type="primary"):
            st.session_state.wizard_step = 4
            st.rerun()


# ─── ETAPA 4: SALVAR ─────────────────────────────────────────────────────────

def _step4_save():
    st.subheader("💾 Etapa 4 — Salvar Workflow")

    cfg = load_config()
    analysis = st.session_state.wizard_analysis
    code = st.session_state.wizard_code

    # Resumo do que será salvo
    st.markdown("### 📋 Resumo do Workflow")
    files_info = [fd["info"] for fd in st.session_state.wizard_files]

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Arquivos esperados:**")
        for fi in files_info:
            legacy_tag = " 🗂️ legado" if fi.get("is_legacy") else ""
            st.markdown(f"- `{fi['filename']}`{legacy_tag}")
    with col2:
        keys = analysis.get("relationship_keys", [])
        if keys:
            st.markdown("**Chaves de relacionamento:**")
            for k in keys:
                st.markdown(f"- `{k.get('key')}` ({k.get('confidence')})")

    st.info(f"**Estratégia:** {analysis.get('strategy', 'N/A')}")

    st.divider()

    # Formulário de salvamento
    name = st.text_input("📌 Nome do Workflow *", placeholder="Ex: Conciliação Pagamentos × NFs Mensais",
                         key="wf_name")
    desc = st.text_area("📝 Descrição (opcional)", placeholder="Descreva o propósito deste workflow...",
                        height=80, key="wf_desc")
    tags_raw = st.text_input("🏷️ Tags (opcional, separadas por vírgula)",
                             placeholder="financeiro, fiscal, mensal", key="wf_tags")
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

    st.markdown("<br>", unsafe_allow_html=True)

    col_back, col_save = st.columns([1, 3])
    with col_back:
        if st.button("← Voltar"):
            st.session_state.wizard_step = 3
            st.rerun()

    with col_save:
        if st.button("💾 Salvar Workflow", type="primary", disabled=not name.strip()):
            if not name.strip():
                st.error("O nome do workflow é obrigatório.")
                return

            # Verifica duplicidade
            existing = get_workflow_by_name(name.strip())
            if existing:
                st.error(f"❌ Já existe um workflow com o nome '{name}'. Escolha outro nome.")
                return

            # Monta schema_info
            schema_info = {
                "files": [
                    {
                        "filename": fi["filename"],
                        "type": fi["type"],
                        "key_columns": next(
                            (f.get("key_columns", []) for f in analysis.get("files", [])
                             if f.get("filename") == fi["filename"]),
                            []
                        ),
                        "is_legacy": fi.get("is_legacy", False),
                    }
                    for fi in files_info
                ],
                "relationship_keys": analysis.get("relationship_keys", []),
            }

            wf_id = save_workflow(
                name=name.strip(),
                description=desc.strip(),
                tags=tags,
                code=code,
                schema_info=schema_info,
                agent_summary=st.session_state.wizard_summary,
                sample_pct=cfg.get("agent1_sample_pct", 0.20),
                llm_provider=cfg.get("agent1_provider", "?"),
                llm_model=cfg.get("agent1_model", "?"),
            )

            st.success(f"✅ Workflow **'{name}'** salvo com sucesso! (ID: {wf_id})")
            st.balloons()

            # Reset do wizard
            for k in ["wizard_step","wizard_files","wizard_analysis","wizard_code",
                      "wizard_summary","wizard_objective"]:
                if k in st.session_state:
                    del st.session_state[k]

            col_x, col_y = st.columns(2)
            with col_x:
                if st.button("▶️ Ir para Executar Workflow"):
                    st.session_state["current_page"] = "Executar Workflow"
                    st.session_state["preselect_workflow"] = wf_id
                    st.rerun()
            with col_y:
                if st.button("➕ Nova Conciliação"):
                    st.rerun()
