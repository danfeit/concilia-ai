"""
ui/new_automation.py — Wizard de Nova Automacao (6 etapas).
Etapa 1: Upload -> Etapa 2: Analise IA -> Etapa 3: Plano ETL -> Etapa 4: Codigo -> Etapa 5: Teste & Preview -> Etapa 6: Salvar
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
from core.code_executor import execute_code
from agents.structure_agent import analyze_structure
from agents.automation_agent import generate_execution_plan, generate_automation_code, generate_automation_summary
from database.db import save_workflow, get_workflow_by_name


def render():
    st.title("⚡ Nova Automacao")

    # Estado do wizard isolado para Automacao
    if "aut_step" not in st.session_state:
        st.session_state.aut_step = 1
    if "aut_files" not in st.session_state:
        st.session_state.aut_files = []
    if "aut_analysis" not in st.session_state:
        st.session_state.aut_analysis = None
    if "aut_plan" not in st.session_state:
        st.session_state.aut_plan = ""
    if "aut_code" not in st.session_state:
        st.session_state.aut_code = ""
    if "aut_summary" not in st.session_state:
        st.session_state.aut_summary = ""
    if "aut_objective" not in st.session_state:
        st.session_state.aut_objective = ""
    if "aut_extension" not in st.session_state:
        st.session_state.aut_extension = "xlsx"
    if "aut_plan_adjustments" not in st.session_state:
        st.session_state.aut_plan_adjustments = ""
    if "aut_test_result" not in st.session_state:
        st.session_state.aut_test_result = None

    _render_progress_bar()

    step = st.session_state.aut_step
    if step == 1:
        _step1_upload()
    elif step == 2:
        _step2_analysis()
    elif step == 3:
        _step3_plan()
    elif step == 4:
        _step4_code()
    elif step == 5:
        _step5_test_preview()
    elif step == 6:
        _step6_save()


def _render_progress_bar():
    step = st.session_state.aut_step
    labels = ["1 Upload", "2 Analise IA", "3 Plano ETL", "4 Codigo", "5 Teste", "6 Salvar"]
    cols = st.columns(6)
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


# --- ETAPA 1: UPLOAD -------------------------------------------------------

def _step1_upload():
    st.subheader("📂 Etapa 1 — Upload dos Arquivos e Objetivo")

    uploaded = st.file_uploader(
        "Arraste ou selecione os arquivos (min. 1, max. 5)",
        accept_multiple_files=True,
        type=["csv","xlsx","xls","json","parquet","txt","pdf"],
        key="uploader_aut_step1",
    )

    if uploaded:
        if len(uploaded) > 5:
            st.error("❌ Maximo de 5 arquivos por automacao.")
        else:
            files_data = []
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
                            st.markdown(f"**Linhas:** {info.get('line_count', '?')}")
                            if info.get("page_count"):
                                st.markdown(f"**Paginas:** {info['page_count']}")
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

            st.markdown("<br>", unsafe_allow_html=True)

            # Detalhamento do objetivo da automacao
            objective = st.text_area(
                "📝 Descreva a sua necessidade de automacao (ETL/Relatorio)",
                value=st.session_state.aut_objective,
                placeholder="Ex: Preciso ler a planilha de vendas, filtrar somente os registros de 'Junho', agrupar o faturamento por Vendedor e gerar um relatorio final em PDF.",
                height=120,
                key="aut_objective_input",
            )

            # Escolha da extensao de saida
            output_ext = st.selectbox(
                "🎯 Qual o formato do arquivo de saida desejado?",
                ["xlsx", "csv", "pdf", "json", "txt"],
                index=["xlsx", "csv", "pdf", "json", "txt"].index(st.session_state.aut_extension),
                key="aut_ext_select"
            )

            if st.button("Analisar Arquivos →", type="primary", disabled=not objective.strip()):
                st.session_state.aut_files = files_data
                st.session_state.aut_objective = objective
                st.session_state.aut_extension = output_ext
                st.session_state.aut_step = 2
                st.rerun()


# --- ETAPA 2: ANALISE IA ---------------------------------------------------

def _step2_analysis():
    st.subheader("🧠 Etapa 2 — Analise Estrutural pela IA")

    cfg = load_config()
    files_data = st.session_state.aut_files

    if st.session_state.aut_analysis is None:
        with st.spinner("🔍 Analisando a estrutura dos arquivos..."):
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

                analysis = analyze_structure(files_for_agent, st.session_state.aut_objective, cfg)
                st.session_state.aut_analysis = analysis
            except Exception as e:
                err_msg = str(e)
                if "dunning" in err_msg.lower() or "billing" in err_msg.lower() or "403" in err_msg:
                    st.error("❌ Erro de Faturamento / Permissao da API (403 Forbidden)")
                    st.markdown(
                        "⚠️ A chave de API configurada retornou um erro de faturamento suspenso ou bloqueado (**dunning decision is deny**).\n\n"
                        "**Como resolver:**\n"
                        "1. Acesse a pagina **⚙️ Configuracoes** no menu lateral.\n"
                        "2. Verifique se a chave do provedor ativo esta correta.\n"
                        "3. Verifique se o faturamento no painel do provedor (Google AI Studio ou Google Cloud Platform) esta ativo e sem faturas pendentes."
                    )
                else:
                    st.error(f"❌ Erro ao analisar arquivos: {e}")
                if st.button("← Voltar ao Upload"):
                    st.session_state.aut_step = 1
                    st.rerun()
                return

    analysis = st.session_state.aut_analysis

    if "error" in analysis:
        st.error(f"❌ Agente retornou erro: {analysis.get('error')}")
        if st.button("← Voltar"):
            st.session_state.aut_step = 1
            st.session_state.aut_analysis = None
            st.rerun()
        return

    st.success("✅ Estrutura dos arquivos analisada!")

    # Exibe informacoes estruturais
    for f in analysis.get("files", []):
        with st.expander(f"📄 {f.get('filename', '?')}", expanded=True):
            st.markdown(f"**Tipo detectado:** `{f.get('type', '?')}`")
            cols = f.get("detected_columns", [])
            if cols:
                st.markdown(f"**Colunas detectadas:** {', '.join(str(c) for c in cols[:15])}")
            alerts = f.get("quality_alerts", [])
            if alerts:
                st.markdown("**Alertas de qualidade:**")
                for a in alerts:
                    st.markdown(f"- {a}")

    st.markdown("### 🎯 Estrategia de Estruturacao Sugerida")
    st.info(analysis.get("strategy", "Estrategia nao definida."))

    st.markdown("<br>", unsafe_allow_html=True)
    col_back, col_fwd = st.columns([1, 3])
    with col_back:
        if st.button("← Voltar"):
            st.session_state.aut_step = 1
            st.session_state.aut_analysis = None
            st.rerun()
    with col_fwd:
        if st.button("Montar Plano de ETL →", type="primary"):
            st.session_state.aut_step = 3
            st.session_state.aut_plan = ""
            st.rerun()


# --- ETAPA 3: PLANO ETL ----------------------------------------------------

def _step3_plan():
    st.subheader("📋 Etapa 3 — Plano de Execucao ETL")

    cfg = load_config()
    analysis = st.session_state.aut_analysis

    # Gera plano se nao houver
    if not st.session_state.aut_plan:
        with st.spinner("🧠 Gerando plano de execucao da automacao..."):
            try:
                # Se houver ajustes salvos, nos os anexamos ao objetivo para a IA levar em conta
                objective_input = st.session_state.aut_objective
                if st.session_state.aut_plan_adjustments:
                    objective_input += f"\n\nAJUSTES AO PLANO ANTERIOR SOLICITADOS:\n{st.session_state.aut_plan_adjustments}"

                plan = generate_execution_plan(analysis, objective_input, cfg)
                st.session_state.aut_plan = plan
            except Exception as e:
                st.error(f"❌ Erro ao gerar plano ETL: {e}")
                if st.button("← Voltar"):
                    st.session_state.aut_step = 2
                    st.rerun()
                return

    st.markdown("### 📝 Plano de Transformacao IA")
    st.info("Abaixo esta o plano gerado pelo Agente 4. Revise-o cuidadosamente antes de gerar o codigo.")
    st.markdown(st.session_state.aut_plan)

    st.divider()

    # Ajustes do plano
    adjustments = st.text_area(
        "💬 Algum ajuste para o Plano de ETL?",
        value="",
        placeholder="Ex: Altere o formato da data na saida para DD/MM/AAAA. Nao use o campo X, use o Y...",
        key="plan_adj_field"
    )

    col_back, col_regen, col_approve = st.columns([1, 2, 2])

    with col_back:
        if st.button("← Voltar"):
            st.session_state.aut_step = 2
            st.session_state.aut_plan = ""
            st.rerun()

    with col_regen:
        if st.button("🔄 Regenerar Plano com Ajustes", disabled=not adjustments.strip()):
            st.session_state.aut_plan_adjustments = adjustments
            st.session_state.aut_plan = ""
            st.rerun()

    with col_approve:
        if st.button("✅ Plano OK! Gerar Codigo →", type="primary"):
            st.session_state.aut_step = 4
            st.session_state.aut_code = ""
            st.rerun()


# --- ETAPA 4: CODIGO -------------------------------------------------------

def _step4_code():
    st.subheader("⚙️ Etapa 4 — Codigo Python Gerado")

    cfg = load_config()
    analysis = st.session_state.aut_analysis
    plan = st.session_state.aut_plan

    # Ajustes de ultima hora para a geracao do codigo
    code_adjustments = st.text_area(
        "💬 Instrucoes adicionais para a geracao do codigo (opcional)",
        value="",
        placeholder="Ex: Use codificacao latin-1 para ler o CSV. Converta valores para float usando replace('.', '').",
        height=70,
        key="code_adj_input",
    )

    if not st.session_state.aut_code:
        with st.spinner("⚙️ Gerando o codigo de automacao..."):
            try:
                code = generate_automation_code(
                    analysis,
                    st.session_state.aut_objective,
                    plan,
                    code_adjustments,
                    cfg
                )

                # Verifica sintaxe
                ok, err = check_syntax(code)
                if not ok:
                    st.warning(f"⚠️ Erro de sintaxe detectado: {err}. Corrigindo...")
                    fix_adj = f"Corrija o seguinte erro de sintaxe do Python e re-gere o script funcional completo: {err}"
                    code = generate_automation_code(analysis, st.session_state.aut_objective, plan, fix_adj, cfg)

                st.session_state.aut_code = code

                with st.spinner("Gerando resumo executivo..."):
                    summary = generate_automation_summary(code, st.session_state.aut_objective, cfg)
                    st.session_state.aut_summary = summary

            except Exception as e:
                st.error(f"❌ Erro ao gerar o codigo: {e}")
                if st.button("← Voltar ao Plano"):
                    st.session_state.aut_step = 3
                    st.rerun()
                return

    code = st.session_state.aut_code

    # Resumo em linguagem natural
    st.markdown("### 📖 O que este script faz")
    st.info(st.session_state.aut_summary)

    # Checklist
    st.markdown("### ✅ Validacoes da Automacao")
    st.markdown(f"- ✅ Gerara um arquivo de saida no formato **`.{st.session_state.aut_extension}`**")
    st.markdown("- ✅ Verifica integridade dos arquivos de entrada")
    st.markdown("- ✅ Grava log estruturado da execucao em JSON")
    st.markdown("- ✅ Tratamento de multiplos encodings e erros de parsing")

    # Editor de codigo
    st.markdown("### 🖊️ Codigo Python (editavel)")
    with st.expander("Ver e editar codigo", expanded=False):
        edited_code = st.text_area("Codigo Python", value=code, height=500, key="aut_code_editor")
        if edited_code != code:
            ok, err = check_syntax(edited_code)
            if ok:
                st.session_state.aut_code = edited_code
                st.success("✅ Sintaxe valida")
            else:
                st.error(f"❌ {err}")

    st.markdown("<br>", unsafe_allow_html=True)
    col_back, col_regen, col_fwd = st.columns([1, 2, 2])

    with col_back:
        if st.button("← Voltar"):
            st.session_state.aut_step = 3
            st.session_state.aut_code = ""
            st.rerun()

    with col_regen:
        if st.button("⚠️ Regenerar Codigo"):
            st.session_state.aut_code = ""
            st.rerun()

    with col_fwd:
        if st.button("🧪 Testar Codigo →", type="primary"):
            st.session_state.aut_test_result = None
            st.session_state.aut_step = 5
            st.rerun()


# --- ETAPA 5: TESTE & PREVIEW ----------------------------------------------

def _step5_test_preview():
    st.subheader("🧪 Etapa 5 — Teste & Preview dos Resultados")

    code = st.session_state.aut_code
    files_data = st.session_state.aut_files
    ext = st.session_state.aut_extension

    # Salva os arquivos de upload em diretorio temporario para o executor
    if st.session_state.aut_test_result is None:
        with st.spinner("🔄 Executando o codigo com os seus arquivos para teste..."):
            try:
                test_dir = tempfile.mkdtemp(prefix="aut_test_")
                input_paths = []
                for fd in files_data:
                    fpath = os.path.join(test_dir, fd["name"])
                    with open(fpath, "wb") as f:
                        f.write(fd["bytes"])
                    input_paths.append(fpath)

                output_dir = os.path.join(test_dir, "output")
                log_dir = os.path.join(test_dir, "logs")

                result = execute_code(
                    code=code,
                    input_paths=input_paths,
                    output_dir=output_dir,
                    timeout_seconds=120,
                    log_dir=log_dir,
                    output_extension=ext,
                )

                st.session_state.aut_test_result = result

            except Exception as e:
                st.session_state.aut_test_result = {
                    "status": "error",
                    "error": str(e),
                    "duration_seconds": 0,
                    "output_path": None,
                    "stdout": "",
                    "stderr": "",
                }

    result = st.session_state.aut_test_result

    # --- Status do teste ---
    if result["status"] == "success":
        st.success(f"✅ Teste executado com sucesso em {result['duration_seconds']:.1f}s")
    elif result["status"] == "timeout":
        st.error(f"⏱️ Timeout: o codigo excedeu o limite de tempo (120s).")
    else:
        st.error(f"❌ Erro na execucao do teste")
        if result.get("error"):
            with st.expander("Ver detalhes do erro", expanded=True):
                st.code(result["error"], language=None)
        if result.get("stderr"):
            with st.expander("Stderr"):
                st.code(result["stderr"][-3000:], language=None)

    # --- Stdout do script (se houver prints) ---
    if result.get("stdout", "").strip():
        with st.expander("📋 Saida do console (stdout)"):
            st.code(result["stdout"][-3000:], language=None)

    # --- Estatisticas e Preview do output ---
    output_path = result.get("output_path")
    output_df = None

    if output_path and os.path.exists(output_path):
        file_size_kb = round(os.path.getsize(output_path) / 1024, 1)

        st.markdown("---")
        st.markdown("### 📊 Estatisticas do Arquivo de Saida")

        # Tenta ler o output como DataFrame para mostrar estatisticas
        try:
            if ext in ("xlsx", "xls"):
                output_df = pd.read_excel(output_path, engine="openpyxl")
            elif ext == "csv":
                output_df = pd.read_csv(output_path, encoding="utf-8-sig", nrows=5000)
            elif ext == "json":
                output_df = pd.read_json(output_path)
        except Exception:
            output_df = None

        if output_df is not None:
            # Metricas em cards
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric("📄 Registros", f"{len(output_df):,}")
            with m2:
                st.metric("📐 Colunas", f"{len(output_df.columns)}")
            with m3:
                nulls_pct = round(output_df.isnull().mean().mean() * 100, 1)
                st.metric("🕳️ Nulos (%)", f"{nulls_pct}%")
            with m4:
                st.metric("💾 Tamanho", f"{file_size_kb} KB")

            # Tipos de dados
            with st.expander("📋 Tipos de dados por coluna"):
                dtype_df = pd.DataFrame({
                    "Coluna": output_df.columns,
                    "Tipo": [str(dt) for dt in output_df.dtypes],
                    "Nao-Nulos": [int(output_df[c].notna().sum()) for c in output_df.columns],
                    "Nulos": [int(output_df[c].isna().sum()) for c in output_df.columns],
                    "Exemplo": [str(output_df[c].dropna().iloc[0])[:60] if output_df[c].notna().any() else "—" for c in output_df.columns],
                })
                st.dataframe(dtype_df, use_container_width=True, hide_index=True)

            # Preview dos dados
            st.markdown("### 👀 Preview dos Dados (primeiras 20 linhas)")
            st.dataframe(output_df.head(20), use_container_width=True, hide_index=True)

            # Estatisticas descritivas (numericas)
            numeric_cols = output_df.select_dtypes(include=["number"]).columns
            if len(numeric_cols) > 0:
                with st.expander("📈 Estatisticas descritivas (colunas numericas)"):
                    st.dataframe(output_df[numeric_cols].describe().T, use_container_width=True)

        else:
            # Arquivo nao-tabular (PDF, TXT, etc.)
            st.info(f"Arquivo gerado: **{os.path.basename(output_path)}** ({file_size_kb} KB)")
            st.markdown("_Preview nao disponivel para este formato de saida._")

            # Tenta mostrar preview de texto
            if ext == "txt":
                try:
                    with open(output_path, "r", encoding="utf-8") as f:
                        txt_preview = f.read(5000)
                    st.markdown("### 👀 Preview do Conteudo")
                    st.code(txt_preview, language=None)
                except Exception:
                    pass

    elif result["status"] == "success":
        st.warning("⚠️ O script finalizou com sucesso, mas o arquivo de saida nao foi encontrado no caminho esperado.")

    # --- Botoes de acao ---
    st.markdown("---")

    if result["status"] == "success" and output_path and os.path.exists(output_path):
        st.markdown(
            '<div style="background:#0a2e0a;border:1px solid #2d6b2d;border-radius:8px;padding:16px;margin-bottom:16px;">'
            '<span style="color:#4ade80;font-weight:600;font-size:1.05rem;">✅ Resultado aprovado? Siga para salvar o workflow.</span>'
            '</div>',
            unsafe_allow_html=True,
        )

    # Campo de correcao
    st.markdown("### 💬 Nao ficou como esperado? Descreva a correcao")
    correction = st.text_area(
        "Descreva o que precisa ser ajustado no resultado:",
        value="",
        placeholder="Ex: Esta filtrando registros demais, deveria manter tambem os que tem dataencerramento nula. A coluna 'valor' esta com formato errado, deveria ser moeda BRL...",
        height=100,
        key="aut_test_correction",
    )

    st.markdown("<br>", unsafe_allow_html=True)

    col_back, col_regen, col_fwd = st.columns([1, 2, 2])

    with col_back:
        if st.button("← Voltar ao Codigo"):
            st.session_state.aut_step = 4
            st.session_state.aut_test_result = None
            st.rerun()

    with col_regen:
        if st.button("🔄 Regenerar Codigo com Correcao", type="secondary",
                      disabled=not correction.strip()):
            # Volta para etapa 4 com as correcoes como ajuste
            cfg = load_config()
            analysis = st.session_state.aut_analysis
            plan = st.session_state.aut_plan

            # Inclui contexto do resultado do teste na correcao
            correction_context = correction.strip()
            if result.get("error"):
                correction_context += f"\n\nERRO DO TESTE ANTERIOR:\n{result['error'][-1500:]}"
            if result.get("stderr"):
                correction_context += f"\n\nSTDERR:\n{result['stderr'][-1000:]}"

            with st.spinner("🔄 Regenerando codigo com as correcoes..."):
                try:
                    new_code = generate_automation_code(
                        analysis,
                        st.session_state.aut_objective,
                        plan,
                        correction_context,
                        cfg,
                    )

                    # Verifica sintaxe
                    ok, err = check_syntax(new_code)
                    if not ok:
                        fix_adj = f"Corrija o seguinte erro de sintaxe do Python e re-gere o script funcional completo: {err}"
                        new_code = generate_automation_code(
                            analysis, st.session_state.aut_objective, plan, fix_adj, cfg
                        )

                    st.session_state.aut_code = new_code
                    st.session_state.aut_test_result = None

                    # Atualiza resumo
                    with st.spinner("Atualizando resumo..."):
                        summary = generate_automation_summary(new_code, st.session_state.aut_objective, cfg)
                        st.session_state.aut_summary = summary

                    st.rerun()

                except Exception as e:
                    st.error(f"❌ Erro ao regenerar codigo: {e}")

    with col_fwd:
        can_save = result["status"] == "success" and output_path and os.path.exists(output_path)
        if st.button("✅ Aprovar e Salvar Workflow →", type="primary", disabled=not can_save):
            st.session_state.aut_step = 6
            st.rerun()


# --- ETAPA 6: SALVAR -------------------------------------------------------

def _step6_save():
    st.subheader("💾 Etapa 6 — Salvar Workflow de Automacao")

    cfg = load_config()
    analysis = st.session_state.aut_analysis
    code = st.session_state.aut_code

    st.markdown("### 📋 Resumo da Automacao")
    files_info = [fd["info"] for fd in st.session_state.aut_files]

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Arquivos esperados:**")
        for fi in files_info:
            st.markdown(f"- `{fi['filename']}`")
    with col2:
        st.markdown(f"**Formato de Saida:** `.{st.session_state.aut_extension}`")

    st.info(f"**Estrategia ETL:** {analysis.get('strategy', 'N/A')}")

    # Mostra estatisticas do ultimo teste bem-sucedido
    test_result = st.session_state.get("aut_test_result")
    if test_result and test_result["status"] == "success" and test_result.get("output_path"):
        try:
            ext = st.session_state.aut_extension
            if ext in ("xlsx", "xls"):
                preview_df = pd.read_excel(test_result["output_path"], engine="openpyxl")
            elif ext == "csv":
                preview_df = pd.read_csv(test_result["output_path"], encoding="utf-8-sig")
            else:
                preview_df = None
            if preview_df is not None:
                st.success(f"🧪 Ultimo teste: **{len(preview_df):,} registros** gerados com sucesso em {test_result['duration_seconds']:.1f}s")
        except Exception:
            pass

    st.divider()

    name = st.text_input("📌 Nome do Workflow *", placeholder="Ex: Relatorio de Vendas Mensais por Vendedor", key="aut_wf_name")
    desc = st.text_area("📝 Descricao (opcional)", placeholder="Descreva o proposito deste workflow...", height=80, key="aut_wf_desc")
    tags_raw = st.text_input("🏷️ Tags (opcional, separadas por virgula)", placeholder="etl, vendas, relatorio", key="aut_wf_tags")
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

    # Adiciona a tag 'automacao' automaticamente para facilitar filtragem
    if "automacao" not in tags:
        tags.append("automacao")

    st.markdown("<br>", unsafe_allow_html=True)

    col_back, col_save = st.columns([1, 3])
    with col_back:
        if st.button("← Voltar"):
            st.session_state.aut_step = 5
            st.rerun()

    with col_save:
        if st.button("💾 Salvar Workflow de Automacao", type="primary", disabled=not name.strip()):
            if not name.strip():
                st.error("O nome do workflow e obrigatorio.")
                return

            existing = get_workflow_by_name(name.strip())
            if existing:
                st.error(f"❌ Ja existe um workflow com o nome '{name}'. Escolha outro nome.")
                return

            # Monta schema_info com o tipo 'automation' e a extensao
            schema_info = {
                "type": "automation",
                "output_extension": st.session_state.aut_extension,
                "files": [
                    {
                        "filename": fi["filename"],
                        "type": fi["type"],
                        "is_legacy": fi.get("is_legacy", False),
                    }
                    for fi in files_info
                ]
            }

            wf_id = save_workflow(
                name=name.strip(),
                description=desc.strip(),
                tags=tags,
                code=code,
                schema_info=schema_info,
                agent_summary=st.session_state.aut_summary,
                sample_pct=cfg.get("agent1_sample_pct", 0.20),
                llm_provider=cfg.get("agent4_provider", "?"),
                llm_model=cfg.get("agent4_model", "?"),
            )

            st.success(f"✅ Workflow de Automacao **'{name}'** salvo com sucesso! (ID: {wf_id})")
            st.balloons()

            # Reseta estado do wizard de automacao
            for k in ["aut_step", "aut_files", "aut_analysis", "aut_plan",
                      "aut_code", "aut_summary", "aut_objective", "aut_extension",
                      "aut_plan_adjustments", "aut_test_result"]:
                if k in st.session_state:
                    del st.session_state[k]

            col_x, col_y = st.columns(2)
            with col_x:
                if st.button("▶️ Ir para Executar"):
                    st.session_state["current_page"] = "Executar Workflow"
                    st.session_state["preselect_workflow"] = wf_id
                    st.rerun()
            with col_y:
                if st.button("⚡ Criar Outra Automacao"):
                    st.rerun()
