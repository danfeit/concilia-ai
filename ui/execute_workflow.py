"""
pages/execute_workflow.py — Execução de Workflow com novos arquivos.
4 passos: seleção → upload → execução → análise final (Agente 2).
"""

from __future__ import annotations
import io
import json
import tempfile
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.config import load_config
from core.file_handler import read_file, get_file_info, compute_md5
from core.schema_validator import validate_files_against_schema
from core.code_executor import execute_code
from agents.analysis_agent import analyze_results, extract_stats_from_excel, get_divergences_sample
from database.db import list_workflows, get_workflow, save_execution, update_workflow


def render():
    st.title("▶️ Executar Workflow")

    cfg = load_config()
    workflows = list_workflows()

    if not workflows:
        st.info("Nenhum workflow salvo ainda. Crie um em **➕ Nova Conciliação**.")
        return

    # ── Passo 1: Seleção do Workflow ──────────────────────────────────────────
    st.subheader("1️⃣ Selecionar Workflow")

    wf_names = [w["name"] for w in workflows]
    preselect_id = st.session_state.get("preselect_workflow")
    default_idx = 0
    if preselect_id:
        for i, w in enumerate(workflows):
            if w["id"] == preselect_id:
                default_idx = i
                break

    selected_name = st.selectbox("Workflow", wf_names, index=default_idx, key="exec_wf_select")
    wf = next((w for w in workflows if w["name"] == selected_name), None)

    if not wf:
        return

    full_wf = get_workflow(wf["id"])
    if not full_wf:
        st.error("Workflow não encontrado no banco.")
        return

    with st.expander("ℹ️ Informações do Workflow", expanded=False):
        st.markdown(f"**Descrição:** {full_wf.get('description') or '—'}")
        st.markdown(f"**Criado em:** {str(full_wf.get('created_at',''))[:16]}")
        st.markdown(f"**Versão:** {full_wf.get('version',1)}")
        st.markdown(f"**Agente:** {full_wf.get('llm_provider','?')}/{full_wf.get('llm_model','?')}")
        if full_wf.get("agent_summary"):
            st.markdown(f"**Resumo:** {full_wf['agent_summary']}")

    st.divider()

    # ── Passo 2: Upload dos Arquivos ──────────────────────────────────────────
    st.subheader("2️⃣ Upload dos Arquivos para Execução")

    schema_info = full_wf.get("schema_info", {})
    expected_files = schema_info.get("files", [])
    wf_type = schema_info.get("type", "reconciliation")
    output_extension = schema_info.get("output_extension", "xlsx")
    is_automation = (wf_type == "automation")

    if not expected_files:
        st.warning("⚠️ Este workflow não possui schema de arquivos definido.")

    st.markdown("**Arquivos esperados por este workflow:**")
    for ef in expected_files:
        legacy = " 🗂️ (legado)" if ef.get("is_legacy") else ""
        keys = ", ".join(ef.get("key_columns", [])) if ef.get("key_columns") else ""
        st.markdown(f"- `{ef['filename']}`{legacy}" + (f" | chaves: `{keys}`" if keys else ""))

    uploaded = st.file_uploader(
        "Envie os arquivos na mesma ordem listada acima",
        accept_multiple_files=True,
        type=["csv","xlsx","xls","json","parquet","txt","pdf"],
        key="exec_uploader",
    )

    if not uploaded:
        return

    # Lê os arquivos
    uploaded_data = []
    for up in uploaded:
        raw = up.read()
        df, ftype, meta = read_file(raw, up.name)
        info = get_file_info(df, meta, raw)
        uploaded_data.append({"name": up.name, "bytes": raw, "df": df, "meta": meta, "info": info})

        with st.expander(f"👁️ Prévia: {up.name}", expanded=False):
            if df is not None:
                st.dataframe(df.head(5), use_container_width=True)
            else:
                preview = "\n".join(meta.get("preview_lines", [])[:10])
                st.code(preview, language=None)

    # Validação de schema — apenas informativa, nunca bloqueia a execução.
    # O código gerado pelo Agente 1 já inclui normalização de colunas (strip, lower,
    # remoção de acentos), portanto diferenças de nome/case/acento nas chaves são
    # tratadas internamente pelo script de conciliação.
    validation = validate_files_against_schema(
        [{"name": u["name"], "bytes": u["bytes"]} for u in uploaded_data],
        schema_info,
    )

    if validation["warnings"]:
        for w in validation["warnings"]:
            st.warning(f"⚠️ {w}")

    if not validation["ok"]:
        with st.expander("⚠️ Avisos de compatibilidade de schema (clique para ver)", expanded=True):
            st.info(
                "ℹ️ **O código gerado pelo Agente 1 já normaliza as colunas automaticamente** "
                "(strip, lowercase, remoção de acentos e caracteres especiais). "
                "Diferenças de nome entre o schema esperado e o arquivo enviado são normalmente "
                "tratadas pelo script — você pode prosseguir com a execução."
            )
            st.markdown("**Divergências detectadas:**")
            for e in validation["errors"]:
                st.markdown(f"- ⚠️ {e}")
    else:
        st.success("✅ Schema validado — todos os arquivos estão compatíveis.")

    st.divider()

    # ── Passo 3: Execução ─────────────────────────────────────────────────────
    action_label = "Automação" if is_automation else "Conciliação"
    st.subheader(f"3️⃣ Executar {action_label}")

    if st.button(f"▶️ Executar {action_label}", type="primary", use_container_width=True,
                 key="btn_exec"):
        # Salva arquivos em temp
        timeout_sec = cfg.get("timeout_minutes", 5) * 60
        output_dir = cfg.get("output_dir", "outputs")

        action_gerund = "Executando automação..." if is_automation else "Executando conciliação..."
        with st.status(f"⚙️ {action_gerund}", expanded=True) as status_box:
            st.write("📁 Salvando arquivos de entrada...")
            tmp_dir = tempfile.mkdtemp()
            input_paths = []
            input_files_meta = []

            for u in uploaded_data:
                tmp_path = os.path.join(tmp_dir, u["name"])
                with open(tmp_path, "wb") as f:
                    f.write(u["bytes"])
                input_paths.append(tmp_path)
                input_files_meta.append({
                    "name": u["name"],
                    "size": len(u["bytes"]),
                    "md5": compute_md5(u["bytes"]),
                    "rows": u["info"].get("rows"),
                })

            st.write("🚀 Executando script...")
            exec_result = execute_code(
                code=full_wf["code"],
                input_paths=input_paths,
                output_dir=output_dir,
                timeout_seconds=timeout_sec,
                log_dir="logs",
                output_extension=output_extension,
            )

            if exec_result["status"] == "success":
                status_box.update(label=f"✅ {action_label} concluída!", state="complete")
                st.session_state["exec_result"] = exec_result
                st.session_state["exec_wf"] = full_wf
                st.session_state["exec_input_meta"] = input_files_meta
                st.session_state.pop("last_failed_exec", None)
                st.session_state.pop("agent3_result", None)

            elif exec_result["status"] == "timeout":
                status_box.update(label="⏱️ Timeout!", state="error")
                st.error(f"❌ A execução excedeu o tempo limite de {cfg.get('timeout_minutes',5)} minutos.")
                save_execution(full_wf["id"], "timeout", exec_result["duration_seconds"],
                               input_files_meta, None, {}, None,
                               exec_result["error"], exec_result["log_path"])
                # Salva detalhes para o Agente 3
                st.session_state["last_failed_exec"] = {
                    "workflow_id": full_wf["id"],
                    "code": full_wf["code"],
                    "error_message": "Timeout de execução do script.",
                    "stderr": exec_result.get("stderr", ""),
                    "log_path": exec_result.get("log_path", ""),
                    "input_paths": input_paths,
                }
                st.session_state.pop("exec_result", None)

            else:
                status_box.update(label="❌ Erro na execução", state="error")
                st.error("❌ Erro durante a execução do script.")
                with st.expander("📋 Log de erro técnico", expanded=True):
                    st.text(exec_result.get("stderr","") or exec_result.get("error",""))
                save_execution(full_wf["id"], "error", exec_result["duration_seconds"],
                               input_files_meta, None, {}, None,
                               exec_result["error"], exec_result["log_path"])
                # Salva detalhes para o Agente 3
                st.session_state["last_failed_exec"] = {
                    "workflow_id": full_wf["id"],
                    "code": full_wf["code"],
                    "error_message": exec_result.get("error", ""),
                    "stderr": exec_result.get("stderr", ""),
                    "log_path": exec_result.get("log_path", ""),
                    "input_paths": input_paths,
                }
                st.session_state.pop("exec_result", None)

    # ── Passo 4: Análise Final ────────────────────────────────────────────────
    if st.session_state.get("exec_result"):
        exec_result = st.session_state["exec_result"]
        full_wf = st.session_state["exec_wf"]
        input_files_meta = st.session_state["exec_input_meta"]

        st.divider()
        st.subheader("4️⃣ Resultados e Análise")

        output_path = exec_result["output_path"]

        # Determina comportamento baseado no tipo de workflow
        is_automation = (full_wf.get("schema_info", {}).get("type", "reconciliation") == "automation")
        stats = {}

        if not is_automation:
            stats = extract_stats_from_excel(output_path)

            if "error" not in stats:
                # Métricas em cards dinâmicas
                raw_counts = stats.get("raw_counts", {})
                base_metrics = [
                    ("Total Processado", stats.get("total", 0), "#6C63FF"),
                    ("Taxa Conciliação", f"{stats.get('match_rate',0)}%", "#10B981")
                ]
                
                dynamic_metrics = []
                if raw_counts:
                    # Usa os status gerados pela IA como nomes dos cards
                    base_colors = ["#10B981", "#F59E0B", "#EF4444", "#3B82F6", "#EC4899", "#8B5CF6"]
                    for i, (status_name, count) in enumerate(raw_counts.items()):
                        color = base_colors[i % len(base_colors)]
                        dynamic_metrics.append((str(status_name).title(), count, color))
                else:
                    # Fallback estático caso não encontre detalhamento raw
                    dynamic_metrics = [
                        ("Conciliados", stats.get("matched", 0), "#10B981"),
                        ("Divergências", stats.get("divergent", 0), "#F59E0B"),
                        ("Só em A / Só em B", f"{stats.get('only_a',0)} / {stats.get('only_b',0)}", "#EF4444"),
                    ]
                
                all_metrics = base_metrics + dynamic_metrics
                
                # Renderizar grid quebrando em múltiplas linhas se houver mais de 5 itens
                for i in range(0, len(all_metrics), 5):
                    cols = st.columns(min(len(all_metrics) - i, 5))
                    for j, col in enumerate(cols):
                        label, val, color = all_metrics[i + j]
                        with col:
                            st.markdown(f"""
                            <div style="background:#FFFFFF;border:1px solid {color}55;border-radius:6px;
                                        padding:0.9rem;text-align:center;margin-bottom:1rem;height:100%;
                                        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02);">
                                <div style="font-size:1.6rem;font-weight:800;color:{color};font-family:'Outfit',sans-serif;">{val}</div>
                                <div style="font-size:0.75rem;color:#4B5563;font-family:'Inter',sans-serif;font-weight:500;">{label}</div>
                            </div>""", unsafe_allow_html=True)

                # Gráfico de barras dinâmico
                st.markdown("<br>", unsafe_allow_html=True)
                
                raw_counts = stats.get("raw_counts", {})
                if raw_counts:
                    x_labels = list(raw_counts.keys())
                    y_values = list(raw_counts.values())
                    
                    # Paleta de cores moderna (Safra themed)
                    base_colors = ["#10B981", "#000B3D", "#C5A880", "#F59E0B", "#3B82F6", "#EC4899", "#8B5CF6"]
                    marker_colors = [base_colors[i % len(base_colors)] for i in range(len(x_labels))]
                else:
                    x_labels = ["Conciliados","Apenas em A","Apenas em B","Divergências"]
                    y_values = [stats.get("matched",0), stats.get("only_a",0),
                                stats.get("only_b",0), stats.get("divergent",0)]
                    marker_colors = ["#10B981","#000B3D","#C5A880","#F59E0B"]

                fig = go.Figure(go.Bar(
                    x=x_labels,
                    y=y_values,
                    marker_color=marker_colors,
                    text=y_values,
                    textposition='auto'
                ))
                fig.update_layout(
                    plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
                    font_color="#000B3D", title="Distribuição dos Resultados",
                    showlegend=False, height=300,
                    margin=dict(l=20, r=20, t=40, b=20)
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            # Processamento de estatísticas simples para automações
            file_ext = Path(output_path).suffix.lower()
            stats = {"total_rows": 0, "status": "success", "file_type": file_ext.replace(".", "").upper()}
            if file_ext in (".xlsx", ".xls"):
                try:
                    excel_file = pd.ExcelFile(output_path)
                    sheet_info = []
                    total_rows = 0
                    for s_name in excel_file.sheet_names:
                        df_sheet = pd.read_excel(output_path, sheet_name=s_name)
                        sheet_info.append(f"Aba `{s_name}`: {len(df_sheet)} linhas")
                        total_rows += len(df_sheet)
                    stats["total_rows"] = total_rows
                    stats["sheet_info"] = sheet_info
                except Exception as e:
                    stats["error"] = str(e)
            elif file_ext == ".csv":
                try:
                    with open(output_path, "r", encoding="utf-8", errors="ignore") as f:
                        row_count = sum(1 for line in f) - 1
                    stats["total_rows"] = max(0, row_count)
                except Exception as e:
                    stats["error"] = str(e)

            # Card de sucesso premium
            st.markdown(f"""
            <div style="background:#FFFFFF;border:1px solid #10B98155;border-radius:6px;
                        padding:1.2rem;text-align:center;margin-bottom:1.2rem;box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02);">
                <div style="font-size:1.8rem;font-weight:800;color:#10B981;font-family:'Outfit',sans-serif;">✅ Automação Concluída</div>
                <div style="font-size:0.85rem;color:#4B5563;font-family:'Inter',sans-serif;font-weight:500;margin-top:0.3rem;">
                    O script de automação rodou perfeitamente e o arquivo final de saída foi gerado.
                </div>
            </div>""", unsafe_allow_html=True)

            # Grid de métricas da automação
            cols = st.columns(3)
            with cols[0]:
                st.markdown(f"""
                <div style="background:#FFFFFF;border:1px solid #C5A88055;border-radius:6px;
                            padding:0.9rem;text-align:center;height:100%;box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02);">
                    <div style="font-size:1.6rem;font-weight:800;color:#C5A880;font-family:'Outfit',sans-serif;">{stats['file_type']}</div>
                    <div style="font-size:0.75rem;color:#4B5563;font-family:'Inter',sans-serif;font-weight:500;">Formato do Arquivo</div>
                </div>""", unsafe_allow_html=True)
            with cols[1]:
                row_val = stats.get('total_rows', 'N/A')
                st.markdown(f"""
                <div style="background:#FFFFFF;border:1px solid #000B3D55;border-radius:6px;
                            padding:0.9rem;text-align:center;height:100%;box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02);">
                    <div style="font-size:1.6rem;font-weight:800;color:#000B3D;font-family:'Outfit',sans-serif;">{row_val}</div>
                    <div style="font-size:0.75rem;color:#4B5563;font-family:'Inter',sans-serif;font-weight:500;">Total de Linhas Geradas</div>
                </div>""", unsafe_allow_html=True)
            with cols[2]:
                st.markdown(f"""
                <div style="background:#FFFFFF;border:1px solid #6C63FF55;border-radius:6px;
                            padding:0.9rem;text-align:center;height:100%;box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02);">
                    <div style="font-size:1.6rem;font-weight:800;color:#6C63FF;font-family:'Outfit',sans-serif;">{exec_result['duration_seconds']}s</div>
                    <div style="font-size:0.75rem;color:#4B5563;font-family:'Inter',sans-serif;font-weight:500;">Tempo de Execução</div>
                </div>""", unsafe_allow_html=True)

            if stats.get("sheet_info"):
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown("**Detalhamento das abas do Excel:**")
                for s_info in stats["sheet_info"]:
                    st.markdown(f"- 📊 {s_info}")

        # Análise do Agente 2
        cfg = load_config()
        st.markdown("### 🤖 Análise do Agente 2")

        if "agent2_analysis" not in st.session_state:
            with st.spinner("🧠 Agente 2 gerando análise interpretativa..."):
                try:
                    log_content = {}
                    if exec_result.get("log_path") and Path(exec_result["log_path"]).exists():
                        with open(exec_result["log_path"], "r", encoding="utf-8") as f:
                            log_content = json.load(f)
                    
                    if is_automation:
                        from agents.analysis_agent import analyze_automation_results
                        analysis_text = analyze_automation_results(
                            stats=stats,
                            log_content=log_content,
                            workflow_name=full_wf["name"],
                            config=cfg,
                        )
                    else:
                        divergences = get_divergences_sample(output_path)
                        analysis_text = analyze_results(
                            stats=stats,
                            divergences_sample=divergences,
                            log_content=log_content,
                            workflow_name=full_wf["name"],
                            config=cfg,
                        )
                    st.session_state["agent2_analysis"] = analysis_text
                except Exception as e:
                    st.session_state["agent2_analysis"] = f"❌ Erro ao gerar análise: {e}"

        analysis_text = st.session_state.get("agent2_analysis", "")
        st.markdown(analysis_text)

        # Preview dinâmico dos resultados
        st.markdown("### 📊 Prévia dos Resultados")
        file_ext = Path(output_path).suffix.lower()
        if file_ext in (".xlsx", ".xls"):
            try:
                xf = pd.ExcelFile(output_path)
                tabs = st.tabs(xf.sheet_names)
                for tab, sheet in zip(tabs, xf.sheet_names):
                    with tab:
                        df_sheet = pd.read_excel(output_path, sheet_name=sheet)
                        st.dataframe(df_sheet.head(20), use_container_width=True)
            except Exception as e:
                st.warning(f"Não foi possível exibir prévia: {e}")
        elif file_ext == ".csv":
            try:
                df_csv = pd.read_csv(output_path)
                st.dataframe(df_csv.head(20), use_container_width=True)
            except Exception as e:
                st.warning(f"Não foi possível exibir prévia: {e}")
        elif file_ext in (".json", ".txt"):
            try:
                with open(output_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                st.code(content[:3000], language="json" if file_ext == ".json" else None)
            except Exception as e:
                st.warning(f"Não foi possível exibir prévia: {e}")
        elif file_ext == ".pdf":
            st.info("📄 O arquivo PDF foi gerado com sucesso! Faça o download abaixo para visualizar.")

        # Downloads
        st.markdown("### ⬇️ Downloads")
        col_dl1, col_dl2 = st.columns(2)
        
        # Mapeamento do nome de exibição e tipo MIME para downloads
        download_labels = {
            ".xlsx": ("Excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ".xls": ("Excel", "application/vnd.ms-excel"),
            ".csv": ("CSV", "text/csv"),
            ".pdf": ("PDF", "application/pdf"),
            ".json": ("JSON", "application/json"),
            ".txt": ("Texto", "text/plain"),
        }
        dl_label, dl_mime = download_labels.get(file_ext, ("Arquivo", "application/octet-stream"))
        
        with col_dl1:
            with open(output_path, "rb") as f:
                st.download_button(f"⬇️ Baixar Resultado ({dl_label})", data=f.read(),
                                   file_name=Path(output_path).name,
                                   mime=dl_mime,
                                   use_container_width=True)
        with col_dl2:
            report = f"# Relatório de Execução — {full_wf['name']}\n\n{analysis_text}"
            st.download_button("⬇️ Baixar Relatório (Markdown)", data=report.encode("utf-8"),
                               file_name="relatorio_execucao.md", mime="text/markdown",
                               use_container_width=True)

        # Salva execução no banco (primeira vez)
        if not st.session_state.get("exec_saved"):
            save_execution(
                workflow_id=full_wf["id"],
                status="success",
                duration_seconds=exec_result["duration_seconds"],
                input_files=input_files_meta,
                output_path=output_path,
                stats=stats,
                agent2_analysis=analysis_text,
                error_message=None,
                log_path=exec_result.get("log_path",""),
            )
            st.session_state["exec_saved"] = True

        if st.button("🔄 Nova Execução", use_container_width=True):
            for k in ["exec_result","exec_wf","exec_input_meta","agent2_analysis","exec_saved","last_failed_exec","agent3_result"]:
                st.session_state.pop(k, None)
            st.rerun()

    # ── Diagnóstico e Auto-Correção Automatizada (Agente 3) ───────────────────
    if st.session_state.get("last_failed_exec"):
        failed = st.session_state["last_failed_exec"]
        st.divider()
        st.subheader("🤖 Diagnóstico e Auto-Correção por IA (Agente 3)")
        
        st.info(
            "Detectamos uma falha na execução deste workflow. "
            "Você pode solicitar ao Agente 3 que analise o erro, inspecione a estrutura dos arquivos de entrada "
            "e tente gerar uma versão corrigida do código automaticamente."
        )
        
        if st.button("🧠 Iniciar Auto-Diagnóstico e Correção", type="primary", key="btn_agent3_fix", use_container_width=True):
            with st.spinner("🧠 Agente 3 analisando arquivos e erros..."):
                try:
                    from agents.debug_agent import analyze_and_fix, extract_input_info_from_paths
                    
                    # 1. Carrega o log JSON se existir
                    log_content = {}
                    if failed.get("log_path") and Path(failed["log_path"]).exists():
                        with open(failed["log_path"], "r", encoding="utf-8") as f:
                            try:
                                log_content = json.load(f)
                            except Exception:
                                pass
                    
                    # 2. Extrai metadados dos inputs
                    input_info = extract_input_info_from_paths(failed["input_paths"])
                    
                    # 3. Executa o Agente 3
                    result = analyze_and_fix(
                        original_code=failed["code"],
                        error_message=failed["error_message"],
                        stderr=failed["stderr"],
                        log_content=log_content,
                        input_files_info=input_info,
                        config=cfg
                    )
                    
                    st.session_state["agent3_result"] = result
                    st.success("✅ Diagnóstico concluído com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao executar Agente 3: {e}")
                    
        if st.session_state.get("agent3_result"):
            res = st.session_state["agent3_result"]
            
            # Mostra o diagnóstico
            st.markdown("### 📋 Diagnóstico da IA")
            st.warning(res.get("diagnosis", "Sem diagnóstico detalhado."))
            
            # Mostra itens corrigidos
            if res.get("what_was_fixed"):
                st.markdown("**O que foi corrigido:**")
                for fix in res["what_was_fixed"]:
                    st.markdown(f"- ✅ {fix}")
            
            # Mostra código corrigido
            st.markdown("### 💻 Código Corrigido Proposto")
            st.code(res.get("corrected_code", ""), language="python")
            
            # Permite editar ou salvar
            edited_corrected_code = st.text_area(
                "Editar código corrigido (opcional)",
                value=res.get("corrected_code", ""),
                height=300,
                key="agent3_edited_code"
            )
            
            c_save, c_cancel = st.columns(2)
            with c_save:
                if st.button("💾 Salvar Como Nova Versão", type="primary", use_container_width=True, key="save_agent3_fix"):
                    update_workflow(
                        failed["workflow_id"],
                        code=edited_corrected_code
                    )
                    st.success("✅ Código atualizado com sucesso no banco!")
                    # Limpa estados para permitir re-executar
                    for k in ["last_failed_exec", "agent3_result"]:
                        st.session_state.pop(k, None)
                    st.rerun()
            with c_cancel:
                if st.button("Descartar Correção", use_container_width=True, key="cancel_agent3_fix"):
                    st.session_state.pop("agent3_result", None)
                    st.rerun()
