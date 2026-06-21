"""
pages/my_workflows.py — Biblioteca de Workflows Salvos
"""

import streamlit as st
from database.db import list_workflows, delete_workflow, update_workflow, get_workflow


def render():
    st.title("📂 Meus Workflows")

    # ── Busca e Filtros ───────────────────────────────────────────────────────
    col_search, col_tag, col_sort = st.columns([3, 2, 2])
    with col_search:
        search = st.text_input("🔍 Buscar por nome ou descrição", key="wf_search", placeholder="Digite para filtrar...")
    with col_tag:
        tag_filter = st.text_input("🏷️ Filtrar por tag", key="wf_tag_filter", placeholder="Ex: financeiro")
    with col_sort:
        sort_by = st.selectbox("Ordenar por", ["Mais recentes", "Nome A-Z", "Mais executados"], key="wf_sort")

    workflows = list_workflows(search=search.strip(), tag_filter=tag_filter.strip())

    if sort_by == "Nome A-Z":
        workflows.sort(key=lambda x: x["name"].lower())
    elif sort_by == "Mais executados":
        workflows.sort(key=lambda x: x.get("exec_count", 0), reverse=True)

    if not workflows:
        st.info("Nenhum workflow encontrado. Crie um em **➕ Nova Conciliação**.")
        return

    st.markdown(f"**{len(workflows)} workflow(s) encontrado(s)**")
    st.divider()

    # ── Lista de Workflows ────────────────────────────────────────────────────
    for wf in workflows:
        _render_workflow_card(wf)


def _render_workflow_card(wf: dict):
    status_icon = {"success": "✅", "error": "❌", None: "⚪"}.get(wf.get("last_status"), "⚪")
    exec_count = wf.get("exec_count", 0)
    last_exec = (wf.get("last_exec") or "—")
    if last_exec != "—":
        last_exec = last_exec[:16].replace("T", " ")

    tags_html = " ".join(
        f'<span style="background:rgba(197, 168, 128, 0.15);color:#8A7355;padding:2px 8px;'
        f'border-radius:4px;font-size:0.75rem;font-weight:600;font-family:\'Inter\',sans-serif;">{t}</span>'
        for t in (wf.get("tags") or [])
    )

    with st.container():
        st.markdown(
            f"""
            <div style="background:#FFFFFF;border:1px solid #C5A88044;border-radius:6px;
                        padding:1.2rem 1.4rem;margin-bottom:0.8rem;box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02);">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div>
                        <strong style="font-size:1.1rem;color:#000B3D;font-family:\'Outfit\',sans-serif;">{wf['name']}</strong>
                        &nbsp;&nbsp;{tags_html}
                    </div>
                    <div style="text-align:right;color:#6B7280;font-size:0.8rem;font-family:\'Inter\',sans-serif;">
                        {status_icon} {exec_count} execuções &nbsp;|&nbsp; Última: {last_exec}
                    </div>
                </div>
                <div style="color:#374151;font-size:0.88rem;margin-top:0.4rem;font-family:\'Inter\',sans-serif;">
                    {wf.get('description') or '<em style="color:#9CA3AF;">Sem descrição</em>'}
                </div>
                <div style="color:#6B7280;font-size:0.78rem;margin-top:0.4rem;font-family:\'Inter\',sans-serif;border-top:1px solid #E5E7EB;padding-top:0.4rem;">
                    Criado em {(wf.get('created_at') or '')[:10]} &nbsp;·&nbsp;
                    Versão {wf.get('version',1)} &nbsp;·&nbsp;
                    Modelo: <span style="color:#000B3D;font-weight:500;">{wf.get('llm_provider','?')}/{wf.get('llm_model','?')}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_exec, col_detail, col_edit, col_del = st.columns([2, 2, 2, 1])

        with col_exec:
            if st.button("▶️ Executar", key=f"exec_{wf['id']}", use_container_width=True):
                st.session_state["current_page"] = "Executar Workflow"
                st.session_state["preselect_workflow"] = wf["id"]
                st.rerun()

        with col_detail:
            if st.button("🔍 Ver Detalhes", key=f"detail_{wf['id']}", use_container_width=True):
                st.session_state[f"detail_open_{wf['id']}"] = not st.session_state.get(f"detail_open_{wf['id']}", False)
                st.rerun()

        with col_edit:
            if st.button("✏️ Editar", key=f"edit_{wf['id']}", use_container_width=True):
                st.session_state[f"edit_open_{wf['id']}"] = not st.session_state.get(f"edit_open_{wf['id']}", False)
                st.rerun()

        with col_del:
            if st.button("🗑️", key=f"del_{wf['id']}", help="Excluir workflow"):
                st.session_state[f"confirm_del_{wf['id']}"] = True
                st.rerun()

        # Confirmação de exclusão
        if st.session_state.get(f"confirm_del_{wf['id']}"):
            st.warning(f"⚠️ Confirma exclusão do workflow **'{wf['name']}'**?")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Sim, excluir", key=f"yes_del_{wf['id']}", type="primary"):
                    delete_workflow(wf["id"])
                    del st.session_state[f"confirm_del_{wf['id']}"]
                    st.success("Workflow excluído.")
                    st.rerun()
            with c2:
                if st.button("Cancelar", key=f"no_del_{wf['id']}"):
                    del st.session_state[f"confirm_del_{wf['id']}"]
                    st.rerun()

        # Painel de detalhes
        if st.session_state.get(f"detail_open_{wf['id']}"):
            with st.expander("📋 Detalhes do Workflow", expanded=True):
                full_wf = get_workflow(wf["id"])
                if full_wf:
                    st.markdown(f"**Resumo (Agente 1):**\n\n{full_wf.get('agent_summary') or '_Sem resumo_'}")
                    schema = full_wf.get("schema_info", {})
                    if schema.get("files"):
                        st.markdown("**Arquivos esperados:**")
                        for f in schema["files"]:
                            legacy = " 🗂️ legado" if f.get("is_legacy") else ""
                            keys = ", ".join(f.get("key_columns",[]))
                            st.markdown(f"- `{f['filename']}`{legacy} | chaves: `{keys}`")
                    st.code(full_wf.get("code",""), language="python")

        # Painel de edição
        if st.session_state.get(f"edit_open_{wf['id']}"):
            with st.expander("✏️ Editar Workflow", expanded=True):
                new_name = st.text_input("Nome", value=wf["name"], key=f"ename_{wf['id']}")
                new_desc = st.text_area("Descrição", value=wf.get("description",""), key=f"edesc_{wf['id']}", height=80)
                new_tags_raw = st.text_input("Tags (vírgula)", value=", ".join(wf.get("tags",[])), key=f"etags_{wf['id']}")
                new_tags = [t.strip() for t in new_tags_raw.split(",") if t.strip()]

                st.warning("⚠️ Editar o código é de responsabilidade do usuário. Alterações manuais criam uma nova versão.")
                full_wf = get_workflow(wf["id"])
                new_code = st.text_area("Código Python", value=full_wf.get("code","") if full_wf else "",
                                        height=300, key=f"ecode_{wf['id']}")

                if st.button("💾 Salvar Edição", key=f"save_edit_{wf['id']}", type="primary"):
                    code_changed = new_code != (full_wf.get("code","") if full_wf else "")
                    update_workflow(wf["id"], name=new_name, description=new_desc,
                                   tags=new_tags, code=new_code if code_changed else None)
                    st.success("✅ Workflow atualizado com nova versão!")
                    del st.session_state[f"edit_open_{wf['id']}"]
                    st.rerun()
