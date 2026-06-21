"""
agents/analysis_agent.py — Agente 2: Análise interpretativa dos resultados da conciliação.
Só é ativado após execução bem-sucedida.
"""

from __future__ import annotations
import json
import pandas as pd
from agents.base_agent import call_llm


SYSTEM_PROMPT = """Você é um analista financeiro sênior especialista em conciliação de dados.
Sua tarefa é interpretar os resultados de uma conciliação de dados e gerar uma análise
executiva clara, objetiva e acionável para usuários de negócio (não técnicos).

A análise deve conter:
1. Resumo executivo (2-3 frases sobre o que foi encontrado)
2. Principais números: total processado, taxa de conciliação, divergências
3. Análise das principais divergências (com exemplos reais se disponíveis)
4. Alertas e pontos de atenção
5. Sugestões de próximos passos

Tom: profissional, direto, sem jargão técnico de programação.
Formato: Markdown formatado com títulos, bullets e destaques em negrito."""


def analyze_results(
    stats: dict,
    divergences_sample: list[dict],
    log_content: dict,
    workflow_name: str,
    config: dict,
) -> str:
    """
    Gera análise interpretativa dos resultados.
    Retorna texto em Markdown.
    """
    include_next_steps = config.get("agent2_include_next_steps", True)
    include_anomalies = config.get("agent2_include_anomalies", True)

    extra_instructions = ""
    if not include_next_steps:
        extra_instructions += "\nNão inclua a seção de próximos passos.\n"
    if not include_anomalies:
        extra_instructions += "\nNão inclua alertas de anomalias.\n"

    system = SYSTEM_PROMPT + extra_instructions
    if config.get("agent2_system_instructions", "").strip():
        system += "\n\nINSTRUÇÕES ADICIONAIS:\n" + config["agent2_system_instructions"]

    sample_str = json.dumps(divergences_sample[:20], ensure_ascii=False, indent=2)
    stats_str = json.dumps(stats, ensure_ascii=False, indent=2)
    log_str = json.dumps({k: v for k, v in log_content.items()
                          if k not in ("stdout", "stderr")}, ensure_ascii=False, indent=2)

    user_message = f"""WORKFLOW: {workflow_name}

ESTATÍSTICAS DA EXECUÇÃO:
{stats_str}

LOG DE EXECUÇÃO:
{log_str}

AMOSTRA DAS DIVERGÊNCIAS ENCONTRADAS (primeiras 20 linhas):
{sample_str}

Gere a análise interpretativa completa em Markdown."""

    provider = config.get("agent2_provider", "anthropic")
    model = config.get("agent2_model", "claude-haiku-4")
    api_key = config.get(f"{provider}_api_key", "")
    temperature = config.get("agent2_temperature", 0.5)

    return call_llm(provider, model, api_key, system, user_message,
                    temperature=temperature, max_tokens=3000)


def extract_stats_from_excel(output_path: str) -> dict:
    """Lê o Excel de resultado e extrai estatísticas por aba, de forma flexível."""
    try:
        xf = pd.ExcelFile(output_path)
        stats = {"matched": 0, "only_a": 0, "only_b": 0, "divergent": 0, "raw_counts": {}}
        
        def map_status(k, v):
            k_lower = k.lower()
            if "conciliad" in k_lower or "ok" in k_lower:
                stats["matched"] += v
            elif "diverg" in k_lower or "diferen" in k_lower:
                stats["divergent"] += v
            elif "apenas em a" in k_lower or "extrato" in k_lower or "fonte a" in k_lower:
                stats["only_a"] += v
            elif "apenas em b" in k_lower or "contab" in k_lower or "razão" in k_lower or "razao" in k_lower or "fonte b" in k_lower:
                stats["only_b"] += v

        parsed = False
        
        # 1. Look for a detailed sheet (Aba com dados granulares) ou aba única
        for sheet in xf.sheet_names:
            lower_sheet = sheet.lower()
            is_single_sheet = (len(xf.sheet_names) == 1)
            
            if is_single_sheet or "detalhe" in lower_sheet or "completo" in lower_sheet or "resultado" in lower_sheet:
                df = pd.read_excel(output_path, sheet_name=sheet)
                
                # Ignora linhas de Total inseridas pela IA (geralmente primeira coluna contém 'Total')
                if len(df.columns) > 0:
                    df = df[~df.iloc[:, 0].astype(str).str.lower().str.contains("total", na=False)]
                
                # Procura por qualquer coluna que contenha 'status' no nome (ex: Status, Status_Conciliacao)
                status_cols = [c for c in df.columns if "status" in str(c).lower()]
                if status_cols:
                    status_col = status_cols[0]
                    raw_counts = df[status_col].astype(str).value_counts().to_dict()
                    for original_k, v in raw_counts.items():
                        stats["raw_counts"][original_k] = stats["raw_counts"].get(original_k, 0) + v
                        map_status(original_k, v)
                    parsed = True
                    break
                    
        # 2. Se não achar aba granular, tenta pela aba de resumo
        if not parsed:
            for sheet in xf.sheet_names:
                lower_sheet = sheet.lower()
                if "resumo" in lower_sheet:
                    df = pd.read_excel(output_path, sheet_name=sheet)
                    status_cols = [c for c in df.columns if "status" in str(c).lower()]
                    if status_cols:
                        status_col = status_cols[0]
                        quant_col = next((c for c in df.columns if "quant" in str(c).lower() or "count" in str(c).lower()), None)
                        if quant_col:
                            for _, row in df.iterrows():
                                original_k = str(row[status_col])
                                if "total" in original_k.lower(): continue
                                v = int(row[quant_col])
                                stats["raw_counts"][original_k] = stats["raw_counts"].get(original_k, 0) + v
                                map_status(original_k, v)
                            parsed = True
                            break

        # 3. Fallback: Uma aba por status
        if not parsed:
            for sheet in xf.sheet_names:
                lower_sheet = sheet.lower()
                if "resumo" in lower_sheet or "detalhe" in lower_sheet: continue
                df = pd.read_excel(output_path, sheet_name=sheet)
                v = len(df)
                if v == 0: continue
                stats["raw_counts"][sheet] = stats["raw_counts"].get(sheet, 0) + v
                map_status(sheet, v)

        stats["total"] = sum(v for k, v in stats.items() if k in ["matched", "only_a", "only_b", "divergent"])
        matched = stats.get("matched", 0)
        total_possible = matched + stats.get("only_a", 0) + stats.get("only_b", 0) + stats.get("divergent", 0)
        stats["match_rate"] = round(matched / total_possible * 100, 1) if total_possible > 0 else 0
        return stats
    except Exception as e:
        return {"error": str(e)}


def get_divergences_sample(output_path: str, n: int = 20) -> list[dict]:
    """Extrai amostra da aba de Divergências para análise."""
    try:
        df = pd.read_excel(output_path, sheet_name="Divergências")
        sample = df.head(n).fillna("").astype(str)
        return sample.to_dict(orient="records")
    except Exception:
        return []


def analyze_automation_results(
    stats: dict,
    log_content: dict,
    workflow_name: str,
    config: dict,
) -> str:
    """
    Gera análise interpretativa de uma execução de automação (ETL/Relatório).
    """
    system = """Você é um analista de negócios e engenheiro de dados sênior.
Sua tarefa é analisar o resultado de uma execução de automação/ETL e gerar uma análise executiva estruturada e clara em Markdown.
A análise deve resumir:
1. O que foi processado (conforme o log e estatísticas).
2. Resultados gerados (arquivos, contagem de registros/linhas, sheets).
3. Pontos de atenção ou validações bem-sucedidas.
4. Conclusão se o processo ocorreu conforme o esperado.

Tom: profissional, amigável e focado em valor de negócio, sem jargões de programação."""

    stats_str = json.dumps(stats, ensure_ascii=False, indent=2)
    log_str = json.dumps({k: v for k, v in log_content.items() if k not in ("stdout", "stderr")}, ensure_ascii=False, indent=2)
    stdout_sample = log_content.get("stdout", "")[-2000:]
    stderr_sample = log_content.get("stderr", "")[-2000:]

    user_message = f"""WORKFLOW DE AUTOMAÇÃO: {workflow_name}

ESTATÍSTICAS DA EXECUÇÃO:
{stats_str}

LOG DE EXECUÇÃO:
{log_str}

AMOSTRA DO CONSOLE (STDOUT):
{stdout_sample}

AMOSTRA DE ERROS (STDERR):
{stderr_sample}

Gere o relatório de análise em Markdown."""

    provider = config.get("agent2_provider", "anthropic")
    model = config.get("agent2_model", "claude-haiku-4")
    api_key = config.get(f"{provider}_api_key", "")
    temperature = config.get("agent2_temperature", 0.5)

    return call_llm(provider, model, api_key, system, user_message,
                    temperature=temperature, max_tokens=3000)
