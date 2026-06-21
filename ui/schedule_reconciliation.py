"""
ui/schedule_reconciliation.py — Módulo de Agendamento de Conciliação
Permite configurar agendamentos periódicos baseados em arquivos com caminhos completos.
"""

from __future__ import annotations
import os
import json
import time
import threading
from datetime import datetime, date
from pathlib import Path
import streamlit as st

# Imports da aplicação
from core.config import load_config
from core.file_handler import read_file, get_file_info, compute_md5
from core.code_executor import execute_code
from database.db import list_workflows, get_workflow, save_execution
from agents.analysis_agent import analyze_results, extract_stats_from_excel, get_divergences_sample

SCHEDULES_PATH = Path(__file__).parent.parent / "database" / "schedules.json"

# ── Funções de Persistência ───────────────────────────────────────────────────

def load_schedules() -> list[dict]:
    if SCHEDULES_PATH.exists():
        try:
            with open(SCHEDULES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_schedules(schedules: list[dict]) -> None:
    SCHEDULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SCHEDULES_PATH, "w", encoding="utf-8") as f:
        json.dump(schedules, f, indent=2, ensure_ascii=False)


def translate_weekday(day_name: str) -> str:
    mapping = {
        "Monday": "Segunda-feira",
        "Tuesday": "Terça-feira",
        "Wednesday": "Quarta-feira",
        "Thursday": "Quinta-feira",
        "Friday": "Sexta-feira",
        "Saturday": "Sábado",
        "Sunday": "Domingo"
    }
    return mapping.get(day_name, day_name)


# ── Thread do Agendador (Background) ──────────────────────────────────────────

def scheduler_loop():
    """Loop em segundo plano que roda continuamente procurando tarefas agendadas."""
    while True:
        try:
            now = datetime.now()
            current_time_str = now.strftime("%H:%M")
            current_date_str = now.strftime("%Y-%m-%d")
            weekday_name = now.strftime("%A")
            day_of_month = now.day

            schedules = load_schedules()
            updated = False

            for s in schedules:
                if not s.get("active", True):
                    continue

                # Evita executar se já rodou hoje no mesmo horário
                last_run_str = s.get("last_run", "")
                if last_run_str and last_run_str.startswith(current_date_str):
                    continue

                # Verifica se o horário programado coincide com o atual
                sched_time = s.get("time", "")
                if sched_time != current_time_str:
                    continue

                # Verifica se todos os arquivos correspondem à frequência de hoje
                all_frequencies_match = True
                files_config = s.get("files", [])
                
                # Se não houver arquivos configurados, não executa
                if not files_config:
                    continue

                for f in files_config:
                    freq = f.get("frequency", "diario")
                    detail = f.get("frequency_detail", "")

                    if freq == "semanal":
                        if detail.lower() not in (weekday_name.lower(), translate_weekday(weekday_name).lower()):
                            all_frequencies_match = False
                            break
                    elif freq == "mensal":
                        try:
                            if int(detail) != day_of_month:
                                all_frequencies_match = False
                                break
                        except ValueError:
                            all_frequencies_match = False
                            break
                    elif freq == "data_especifica":
                        if detail != current_date_str:
                            all_frequencies_match = False
                            break
                    # 'diario' sempre bate

                if not all_frequencies_match:
                    continue

                # Verifica se todos os arquivos configurados com caminhos completos existem
                input_paths = []
                all_files_exist = True
                for f in files_config:
                    filepath = f.get("filepath", "")
                    if not filepath or not os.path.isfile(filepath):
                        all_files_exist = False
                        break
                    input_paths.append(filepath)

                if not all_files_exist:
                    continue

                # Carrega o workflow do banco
                wf = get_workflow(s["workflow_id"])
                if not wf:
                    continue

                # Executa
                cfg = load_config()
                timeout_sec = cfg.get("timeout_minutes", 5) * 60
                output_dir = cfg.get("output_dir", "outputs")

                input_files_meta = []
                for p in input_paths:
                    try:
                        p_path = Path(p)
                        with open(p, "rb") as fh:
                            raw = fh.read()
                        size = len(raw)
                        md5 = compute_md5(raw)
                        df, _, meta = read_file(raw, p_path.name)
                        rows = len(df) if df is not None else meta.get("rows", 0)
                        input_files_meta.append({
                            "name": p_path.name,
                            "size": size,
                            "md5": md5,
                            "rows": rows
                        })
                    except Exception:
                        input_files_meta.append({
                            "name": os.path.basename(p),
                            "size": os.path.getsize(p),
                            "md5": "",
                            "rows": 0
                        })

                # Executa subprocess
                exec_result = execute_code(
                    code=wf["code"],
                    input_paths=input_paths,
                    output_dir=output_dir,
                    timeout_seconds=timeout_sec,
                    log_dir="logs"
                )

                status_run = exec_result["status"]
                output_path = exec_result["output_path"]

                # Processa estatísticas do Excel
                stats = {}
                analysis_text = ""
                if status_run == "success" and output_path:
                    stats = extract_stats_from_excel(output_path)
                    try:
                        divergences = get_divergences_sample(output_path)
                        log_content = {}
                        if exec_result.get("log_path") and Path(exec_result["log_path"]).exists():
                            with open(exec_result["log_path"], "r", encoding="utf-8") as f_log:
                                log_content = json.load(f_log)
                        analysis_text = analyze_results(
                            stats=stats,
                            divergences_sample=divergences,
                            log_content=log_content,
                            workflow_name=wf["name"],
                            config=cfg
                        )
                    except Exception as e:
                        analysis_text = f"Erro na análise automática do Agente 2: {e}"

                # Salva no banco de dados de execuções
                save_execution(
                    workflow_id=wf["id"],
                    status=status_run,
                    duration_seconds=exec_result["duration_seconds"],
                    input_files=input_files_meta,
                    output_path=output_path,
                    stats=stats,
                    agent2_analysis=analysis_text,
                    error_message=exec_result.get("error"),
                    log_path=exec_result.get("log_path", "")
                )

                # Atualiza status de execução do agendamento
                s["last_run"] = now.isoformat()
                updated = True

            if updated:
                save_schedules(schedules)

        except Exception:
            pass

        time.sleep(30)


@st.cache_resource
def start_background_scheduler():
    """Inicia a thread persistente do scheduler."""
    thread = threading.Thread(target=scheduler_loop, daemon=True)
    thread.start()
    return thread


# ── Renderização da UI ────────────────────────────────────────────────────────

def render():
    # Inicializa thread do agendador
    start_background_scheduler()

    st.title("⏰ Agendar Conciliação")
    st.markdown(
        "<p style='color:#4B5563; font-size:1.1rem; font-family: \"Inter\", sans-serif;'>"
        "Configure regras automáticas para executar seus workflows a partir de caminhos de arquivos completos e frequências.</p>",
        unsafe_allow_html=True
    )

    workflows = list_workflows()
    if not workflows:
        st.info("Nenhum workflow salvo ainda. Crie um em **➕ Nova Conciliação**.")
        return

    # Estilos CSS
    st.markdown("""
    <style>
    .schedule-card {
        background: #FFFFFF;
        border: 1px solid #C5A88033;
        border-radius: 8px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02);
    }
    .schedule-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.8rem;
        border-bottom: 1px solid #F3F4F6;
        padding-bottom: 0.5rem;
    }
    .schedule-title {
        font-family: 'Outfit', sans-serif;
        font-size: 1.25rem;
        font-weight: 700;
        color: #000B3D;
    }
    .file-tag {
        background: #F3F4F6;
        color: #374151;
        padding: 0.2rem 0.5rem;
        border-radius: 4px;
        font-size: 0.8rem;
        font-family: monospace;
        margin-right: 0.4rem;
        display: inline-block;
    }
    </style>
    """, unsafe_allow_html=True)

    # Abas principais
    tab_list, tab_create = st.tabs(["📋 Agendamentos Ativos", "➕ Criar Agendamento"])

    # ──────────────── Aba 1: Lista de Agendamentos ────────────────────────────
    with tab_list:
        schedules = load_schedules()
        if not schedules:
            st.info("Nenhum agendamento ativo cadastrado.")
        else:
            for s_idx, s in enumerate(schedules):
                # Determina status
                is_active = s.get("active", True)
                status_tag = "🟢 Ativo" if is_active else "⚪ Inativo"
                
                with st.container():
                    st.markdown(f"""
                    <div class="schedule-card">
                        <div class="schedule-header">
                            <div class="schedule-title">{s['workflow_name']}</div>
                            <div style="font-weight: 600; font-size: 0.9rem; color: {'#10B981' if is_active else '#9CA3AF'}">{status_tag}</div>
                        </div>
                        <p style="margin: 0.2rem 0; font-size: 0.9rem;"><strong>Horário de Execução:</strong> {s['time']}</p>
                        <p style="margin: 0.2rem 0; font-size: 0.9rem;"><strong>Última Execução:</strong> {s.get('last_run', 'Nunca executado')[:16].replace('T', ' ')}</p>
                        <div style="margin-top: 0.6rem;">
                            <strong>Arquivos & Frequências:</strong><br>
                    """, unsafe_allow_html=True)
                    
                    for f in s.get("files", []):
                        freq_map = {
                            "diario": "Diário",
                            "semanal": "Semanal",
                            "mensal": "Mensal",
                            "data_especifica": "Data Específica"
                        }
                        freq_desc = freq_map.get(f.get("frequency", "diario"), f.get("frequency", "diario"))
                        
                        detail = f.get("frequency_detail", "")
                        if f.get("frequency") == "semanal":
                            detail = translate_weekday(detail)
                        elif f.get("frequency") == "data_especifica":
                            detail = detail
                        elif detail:
                            detail = f"Dia {detail}"
                        
                        detail_desc = f" ({detail})" if detail else ""
                        st.markdown(f"<span class='file-tag'>{f.get('filepath')}</span> ➔ {freq_desc}{detail_desc}", unsafe_allow_html=True)

                    st.markdown("</div></div>", unsafe_allow_html=True)
                    
                    # Ações para o agendamento
                    col_act1, col_act2, col_act3 = st.columns([2, 2, 8])
                    with col_act1:
                        toggle_label = "Desativar" if is_active else "Ativar"
                        if st.button(toggle_label, key=f"toggle_{s['id']}", use_container_width=True):
                            s["active"] = not is_active
                            save_schedules(schedules)
                            st.rerun()
                    with col_act2:
                        if st.button("Excluir", key=f"delete_{s['id']}", use_container_width=True, type="secondary"):
                            schedules.pop(s_idx)
                            save_schedules(schedules)
                            st.rerun()
                    with col_act3:
                        st.write("")
                    
                    st.divider()

    # ──────────────── Aba 2: Novo Agendamento ─────────────────────────────────
    with tab_create:
        st.subheader("Configurar Novo Agendamento")
        
        # Seleção de Workflow
        wf_names = [w["name"] for w in workflows]
        selected_name = st.selectbox("Selecione o Workflow", wf_names, key="sched_wf_select")
        wf = next((w for w in workflows if w["name"] == selected_name), None)
        
        if wf:
            full_wf = get_workflow(wf["id"])
            schema_info = full_wf.get("schema_info", {})
            expected_files = schema_info.get("files", [])
            
            # Mostra arquivos esperados pelo workflow
            if expected_files:
                st.info(
                    "💡 **Arquivos esperados pelo schema do workflow:**\n" +
                    "\n".join([f"- `{ef['filename']}`" for ef in expected_files])
                )
            
            # Inicializa a lista de arquivos no session_state se mudou o workflow
            selected_wf_id = wf["id"]
            if st.session_state.get("prev_selected_wf_id") != selected_wf_id:
                st.session_state["prev_selected_wf_id"] = selected_wf_id
                st.session_state["schedule_files"] = [
                    {
                        "expected_name": ef["filename"],
                        "filepath": "",
                        "frequency": "diario",
                        "frequency_detail": ""
                    }
                    for ef in expected_files
                ]
            
            st.markdown("---")
            st.markdown("#### Configuração de Frequência por Arquivo")
            
            # Renderiza as linhas de configuração de arquivos
            if not st.session_state.get("schedule_files"):
                st.session_state["schedule_files"] = []
                
            for idx, file_cfg in enumerate(st.session_state["schedule_files"]):
                cols = st.columns([4, 2, 2, 1])
                with cols[0]:
                    label = f"Caminho do arquivo ({file_cfg.get('expected_name', 'Personalizado')})"
                    file_cfg["filepath"] = st.text_input(
                        label,
                        value=file_cfg.get("filepath", ""),
                        placeholder="Ex: C:\\dados\\extrato.csv",
                        key=f"file_path_{idx}"
                    )
                with cols[1]:
                    file_cfg["frequency"] = st.selectbox(
                        "Frequência de Busca",
                        options=["diario", "semanal", "mensal", "data_especifica"],
                        format_func=lambda x: {
                            "diario": "Diário",
                            "semanal": "Semanal",
                            "mensal": "Mensal",
                            "data_especifica": "Data Específica"
                        }.get(x, x),
                        index=["diario", "semanal", "mensal", "data_especifica"].index(file_cfg.get("frequency", "diario")),
                        key=f"file_freq_{idx}"
                    )
                with cols[2]:
                    freq = file_cfg["frequency"]
                    if freq == "semanal":
                        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                        weekday_pt = {
                            "Monday": "Segunda-feira",
                            "Tuesday": "Terça-feira",
                            "Wednesday": "Quarta-feira",
                            "Thursday": "Quinta-feira",
                            "Friday": "Sexta-feira",
                            "Saturday": "Sábado",
                            "Sunday": "Domingo"
                        }
                        
                        default_val = file_cfg.get("frequency_detail", "Monday")
                        if default_val not in weekdays:
                            default_val = "Monday"
                        idx_weekday = weekdays.index(default_val)
                        
                        selected_weekday = st.selectbox(
                            "Dia da Semana",
                            options=weekdays,
                            format_func=lambda x: weekday_pt.get(x, x),
                            index=idx_weekday,
                            key=f"file_detail_{idx}"
                        )
                        file_cfg["frequency_detail"] = selected_weekday
                    elif freq == "mensal":
                        try:
                            default_val = int(file_cfg.get("frequency_detail", 1))
                        except ValueError:
                            default_val = 1
                        selected_day = st.number_input(
                            "Dia do Mês",
                            min_value=1,
                            max_value=31,
                            value=default_val,
                            key=f"file_detail_{idx}"
                        )
                        file_cfg["frequency_detail"] = str(selected_day)
                    elif freq == "data_especifica":
                        default_date = date.today()
                        if file_cfg.get("frequency_detail"):
                            try:
                                default_date = datetime.strptime(file_cfg["frequency_detail"], "%Y-%m-%d").date()
                            except ValueError:
                                pass
                        selected_date = st.date_input(
                            "Data da Execução",
                            value=default_date,
                            key=f"file_detail_{idx}"
                        )
                        file_cfg["frequency_detail"] = selected_date.strftime("%Y-%m-%d")
                    else:
                        st.markdown("<div style='margin-top:28px; color:#9CA3AF; font-size:0.85rem;'>Todos os dias</div>", unsafe_allow_html=True)
                        file_cfg["frequency_detail"] = ""
                        
                with cols[3]:
                    st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
                    if st.button("🗑️", key=f"remove_file_{idx}", use_container_width=True):
                        st.session_state["schedule_files"].pop(idx)
                        st.rerun()
            
            # Botão para adicionar mais arquivos
            if st.button("➕ Adicionar Arquivo"):
                st.session_state["schedule_files"].append({
                    "expected_name": "Personalizado",
                    "filepath": "",
                    "frequency": "diario",
                    "frequency_detail": ""
                })
                st.rerun()
                
            st.markdown("---")
            
            # Estabiliza o Horário de Início usando session_state para evitar reset ao atualizar hora
            if "default_time" not in st.session_state:
                st.session_state["default_time"] = datetime.now().time()
            
            execution_time = st.time_input(
                "Horário de Início da Execução",
                value=st.session_state["default_time"],
                key="sched_time_widget"
            )
            
            # Botão de Agendamento
            if st.button("💾 Agendar Workflow", type="primary", use_container_width=True):
                # Validações
                if not st.session_state["schedule_files"]:
                    st.error("Por favor, adicione ao menos um arquivo à configuração.")
                elif any(not f.get("filepath", "").strip() for f in st.session_state["schedule_files"]):
                    st.error("Todos os caminhos de arquivos configurados precisam estar preenchidos.")
                else:
                    # Valida se os caminhos informados existem e avisa se algum não for encontrado
                    missing_files = []
                    for f in st.session_state["schedule_files"]:
                        fp = f.get("filepath", "")
                        if not os.path.isfile(fp):
                            missing_files.append(fp)
                    
                    if missing_files:
                        st.warning(
                            "⚠️ Atenção: Os seguintes arquivos não existem no momento:\n" +
                            "\n".join([f"- `{p}`" for p in missing_files]) +
                            "\nO agendamento foi salvo, mas a execução automática falhará até que os arquivos estejam nos caminhos indicados."
                        )
                    
                    new_sched = {
                        "id": datetime.now().strftime("%Y%m%d%H%M%S"),
                        "workflow_id": wf["id"],
                        "workflow_name": wf["name"],
                        "files": st.session_state["schedule_files"],
                        "time": execution_time.strftime("%H:%M"),
                        "active": True,
                        "last_run": ""
                    }
                    
                    schedules = load_schedules()
                    schedules.append(new_sched)
                    save_schedules(schedules)
                    
                    st.success("✅ Workflow agendado com sucesso!")
                    time.sleep(1)
                    st.rerun()
