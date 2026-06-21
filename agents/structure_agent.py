"""
agents/structure_agent.py — Agente 1: Análise de estrutura de arquivos.
Detecta schema de arquivos estruturados e faz engenharia reversa de arquivos legados (TXT/PDF).
"""

from __future__ import annotations
import json
from agents.base_agent import call_llm


SYSTEM_PROMPT = """Você é um especialista em análise de dados e engenharia de dados.
Sua tarefa é analisar amostras de arquivos de dados e retornar um JSON estruturado com:
1. Schema de cada arquivo (colunas, tipos, exemplos)
2. Chaves de relacionamento sugeridas entre os arquivos (com nível de confiança)
3. Padrões de formatação detectados (datas, moedas, separadores)
4. Alertas de qualidade (nulos, duplicatas, inconsistências)
5. Estratégia proposta de conciliação em linguagem natural

PARA ARQUIVOS LEGADOS (TXT/PDF de sistemas legados):
- Mapeie a arquitetura visual/textual do documento
- Identifique estruturas posicionais (colunas de largura fixa)
- Detecte cabeçalhos recorrentes, rodapés, separadores de seção
- Identifique onde os dados úteis começam e terminam
- Descreva como converter o arquivo em uma tabela estruturada

SEMPRE retorne um JSON válido sem markdown, sem explicações fora do JSON."""


def analyze_structure(
    files_data: list[dict],  # [{"filename": str, "type": str, "sample": str/dict, "is_legacy": bool}]
    user_objective: str,
    config: dict,
) -> dict:
    """
    Chama o LLM para analisar a estrutura dos arquivos.
    Retorna o JSON de análise parseado.
    """
    files_json = json.dumps(files_data, ensure_ascii=False, indent=2)

    user_message = f"""OBJETIVO DA CONCILIAÇÃO:
{user_objective}

ARQUIVOS PARA ANÁLISE:
{files_json}

Retorne APENAS um JSON válido com esta estrutura:
{{
  "files": [
    {{
      "filename": "...",
      "type": "structured|legacy_txt|legacy_pdf",
      "detected_columns": [...],
      "key_columns": [...],
      "format_patterns": {{"dates": "...", "currency": "...", "encoding": "..."}},
      "quality_alerts": [...],
      "legacy_architecture": {{
        "description": "...",
        "fixed_width": true/false,
        "header_lines": 0,
        "footer_lines": 0,
        "data_start_line": 0,
        "column_positions": [...],
        "record_separator": "...",
        "parser_strategy": "..."
      }}
    }}
  ],
  "relationship_keys": [
    {{"key": "...", "file_a_column": "...", "file_b_column": "...", "confidence": "alto|médio|baixo"}}
  ],
  "quality_alerts": [...],
  "strategy": "Descrição da estratégia de conciliação em linguagem natural"
}}"""

    provider = config.get("agent1_provider", "anthropic")
    model = config.get("agent1_model", "claude-haiku-4-5")
    api_key = config.get(f"{provider}_api_key", "")
    temperature = config.get("agent1_temperature", 0.2)

    sys_prompt = SYSTEM_PROMPT
    add_sys = config.get("agent1_system_instructions", "")
    if add_sys:
        sys_prompt += f"\n\nInstruções Adicionais do Sistema:\n{add_sys}"

    raw = call_llm(provider, model, api_key, sys_prompt, user_message,
                   temperature=temperature, max_tokens=6000)

    # Extrai JSON da resposta de forma robusta
    import re
    raw = raw.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        raw_json = match.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw_json = raw[start:end+1]
        else:
            raw_json = raw

    try:
        return json.loads(raw_json)
    except json.JSONDecodeError:
        return {"error": "Resposta do agente não é JSON válido.", "raw": raw_json}
