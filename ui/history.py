"""
pages/history.py — Histórico de Execuções com auditoria e rastreabilidade.
"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from database.db import list_executions, list_workflows, get_execution


def render():
    st.title("📋 Histórico de Execuções")

    # ── Filtros ───────────────────────────────────────────────────────────────
    workflows = list_workflows()
    wf_names = ["Todos"] + [w["name"] for w in workflows]

    col1, col2, col3 = st.columns(3)
    with col1:
        wf_filter = st.selectbox("Filtrar por Workflow", wf_names, key="hist_wf")
    with col2:
        status_filter = st.selectbox("Status", ["Todos", "success", "error", "timeout"], key="hist_status")
    with col3:
        limit = st.number_input("Máx. registros", min_value=10, max_value=500, value=100, step=10, key="hist_limit")

    # Monta filtros
    wf_id_filter = None
    if wf_filter != "Todos":
        wf_match = next((w for w in workflows if w["name"] == wf_filter), None)
        if wf_match:
            wf_id_filter = wf_match["id"]

    status_val = None if status_filter == "Todos" else status_filter

    executions = list_executions(workflow_id=wf_id_filter, status_filter=status_val, limit=int(limit))

    if not executions:
        st.info("Nenhuma execução encontrada com os filtros aplicados.")
        return

    # ── Tabela Resumo ─────────────────────────────────────────────────────────
    st.markdown(f"**{len(executions)} execução(ões) encontrada(s)**")

    status_icons = {"success": "✅ Sucesso", "error": "❌ Erro", "timeout": "⏱️ Timeout"}

    table_data = []
    for ex in executions:
        stats = ex.get("stats", {})
        table_data.append({
            "ID": ex["id"],
            "Workflow": ex.get("workflow_name", "?"),
            "Data/Hora": str(ex.get("executed_at",""))[:16].replace("T"," "),
            "Status": status_icons.get(ex.get("status",""), ex.get("status","")),
            "Duração": f"{ex.get('duration_seconds',0):.1f}s",
            "Conciliados": stats.get("matched", "—"),
            "Divergências": stats.get("divergent", "—"),
            "Taxa %": f"{stats.get('match_rate',0)}%" if "match_rate" in stats else "—",
        })

    df_table = pd.DataFrame(table_data)
    selected_row = st.dataframe(
        df_table, use_container_width=True,
        column_config={"ID": st.column_config.NumberColumn(width="small")},
        hide_index=True,
    )

    st.divider()

    # ── Detalhes de Execução Selecionada ──────────────────────────────────────
    st.subheader("🔍 Ver Detalhes de uma Execução")
    exec_id = st.number_input("ID da Execução", min_value=1, step=1, key="detail_exec_id")

    if st.button("📂 Carregar Detalhes", key="load_exec_detail"):
        ex = get_execution(int(exec_id))
        if not ex:
            st.error(f"Execução #{exec_id} não encontrada.")
        else:
            _render_execution_detail(ex)


def _render_execution_detail(ex: dict):
    st.markdown(f"### Execução #{ex['id']} — {ex.get('workflow_name','?')}")

    # Status e duração
    status_color = {"success": "#10B981", "error": "#EF4444", "timeout": "#F59E0B"}.get(
        ex.get("status",""), "#4B5563"
    )
    st.markdown(
        f'<span style="background:{status_color}18;color:{status_color};padding:4px 12px;'
        f'border-radius:4px;font-weight:700;font-family:\'Inter\',sans-serif;font-size:0.8rem;">{ex.get("status","").upper()}</span>'
        f' &nbsp; <span style="color:#4B5563;font-family:\'Inter\',sans-serif;font-size:0.85rem;">Duração: <strong>{ex.get("duration_seconds",0):.1f}s</strong></span>'
        f' &nbsp; <span style="color:#4B5563;font-family:\'Inter\',sans-serif;font-size:0.85rem;">Data: <strong>{str(ex.get("executed_at",""))[:16].replace("T"," ")}</strong></span>',
        unsafe_allow_html=True,
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # Arquivos de entrada
    input_files = ex.get("input_files", [])
    if input_files:
        st.markdown("**📁 Arquivos de Entrada:**")
        for f in input_files:
            st.markdown(
                f"- `{f.get('name','?')}` &nbsp; "
                f"MD5: `{f.get('md5','?')[:16]}...` &nbsp; "
                f"Linhas: {f.get('rows','?')}"
            )

    # Estatísticas
    stats = ex.get("stats", {})
    if stats and "total" in stats:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", stats.get("total","—"))
        c2.metric("Conciliados", stats.get("matched","—"))
        c3.metric("Divergências", stats.get("divergent","—"))
        c4.metric("Taxa", f"{stats.get('match_rate',0)}%")

    # Análise do Agente 2
    if ex.get("agent2_analysis"):
        st.markdown("**🤖 Análise do Agente 2:**")
        st.markdown(ex["agent2_analysis"])

    # Arquivo de saída
    output_path = ex.get("output_path")
    if output_path and Path(output_path).exists():
        with open(output_path, "rb") as f:
            st.download_button(
                "⬇️ Baixar Resultado (Excel)",
                data=f.read(),
                file_name=Path(output_path).name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    else:
        st.info("Arquivo de resultado não disponível (pode ter sido movido ou excluído).")

    # Log técnico
    log_path = ex.get("log_path")
    if log_path and Path(log_path).exists():
        with st.expander("📋 Log técnico completo"):
            with open(log_path, "r", encoding="utf-8") as f:
                try:
                    log_data = json.load(f)
                    st.json(log_data)
                except Exception:
                    st.text(f.read())

    # Erro
    if ex.get("error_message"):
        with st.expander("❌ Mensagem de erro"):
            st.code(ex["error_message"])

    # Re-execução
    st.divider()
    if st.button("🔄 Re-executar este Workflow com novos arquivos", key=f"reexec_{ex['id']}"):
        st.session_state["current_page"] = "Executar Workflow"
        from database.db import get_workflow
        wf = get_workflow(ex.get("workflow_id"))
        if wf:
            workflows = list_workflows()
            for w in workflows:
                if w["id"] == wf["id"]:
                    st.session_state["preselect_workflow"] = wf["id"]
                    break
        st.rerun()
