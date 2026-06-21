"""
agents/automation_agent.py — Agente 4: Módulo de Automação & ETL.
Gera planos de execução (ETL) e scripts Python de automação baseados em solicitações customizadas.
"""

from __future__ import annotations
import json
import re
from agents.base_agent import call_llm

SYSTEM_PLAN_PROMPT = """Você é um arquiteto de dados e engenheiro de ETL sênior.
Sua tarefa é analisar os schemas e estruturas dos arquivos fornecidos e a necessidade descrita pelo usuário para montar um Plano de Execução detalhado e profissional.

O Plano de Execução deve ser escrito em Markdown e conter as seguintes seções:
1. **Objetivo da Automação**: Um resumo curto do que o usuário deseja alcançar.
2. **Mapeamento de Entrada**: Como cada arquivo de entrada será lido (encoding, delimitadores, campos-chave, seções legadas).
3. **Etapas de Transformação (ETL)**: Passos sequenciais de limpeza, filtragem, conversão de dados, cruzamentos (joins), agregações e cálculos.
4. **Formato de Saída**: Estrutura detalhada do arquivo final (colunas, formato do arquivo como CSV, Excel ou PDF, ordem das abas se Excel).
5. **Bibliotecas Necessárias**: Quais bibliotecas Python serão utilizadas (ex: pandas, openpyxl, fitz/PyMuPDF para PDFs, etc.).

Seja direto, técnico e preciso, focando na lógica de negócio e integridade de dados."""


SYSTEM_CODE_PROMPT = """Você é um engenheiro de dados sênior especialista em Python, pandas e manipulação de arquivos.
Sua tarefa é gerar um script Python COMPLETO, ROBUSTO e TOTALMENTE FUNCIONAL que implemente o Plano de Execução aprovado.

════════════════════════════════════════
ESTRUTURA OBRIGATÓRIA DO SCRIPT (nesta ordem)
1. Imports (todos na parte superior — NUNCA importe dentro de funções)
2. Constantes e configurações
3. Funções auxiliares (parsers, normalização, etc.)
4. Função principal `main()`
5. Bloco de entrada: `if __name__ == "__main__": main()`  ← OBRIGATÓRIO, NUNCA COMENTADO

════════════════════════════════════════
VARIÁVEIS DE ESCOPO (JÁ DEFINIDAS — NÃO REDECLARE)
As seguintes variáveis globais serão injetadas pelo executor antes de rodar o script. Use-as diretamente no seu código:
- INPUT_FILES  → list[str]: caminhos dos arquivos de entrada
- OUTPUT_PATH  → str: caminho do arquivo de saída gerado (pode ser .xlsx, .csv, .pdf, etc.)
- LOG_PATH     → str: caminho do log JSON de saída

════════════════════════════════════════
REGRAS DE LEITURA E ESCRITA DE ARQUIVOS
1. Delimitadores e Encodings:
   Use encodings robustos em cascata para ler arquivos de texto (utf-8-sig → utf-8 → latin-1 → cp1252).
2. Saída customizada:
   O código DEVE gravar o resultado final EXATAMENTE no caminho contido na variável `OUTPUT_PATH`.
   - Se for EXCEL: Use `pandas.ExcelWriter(OUTPUT_PATH, engine='openpyxl')` ou `df.to_excel(OUTPUT_PATH)`.
   - Se for CSV: Use `df.to_csv(OUTPUT_PATH, index=False, encoding='utf-8-sig')`.
   - Se for PDF: Use a biblioteca `fitz` (PyMuPDF, já instalada) para desenhar o relatório PDF e salvá-lo com `doc.save(OUTPUT_PATH)`.
3. Log JSON:
   Ao final do script, salve um log em formato JSON no caminho especificado em `LOG_PATH`:
   {
     "timestamp": "<ISO 8601>",
     "status": "success" | "error",
     "linhas_processadas": <int>,
     "detalhes": "...",
     "erros": []
   }

════════════════════════════════════════
TRATAMENTO DE ERROS
- Valide a existência dos arquivos em INPUT_FILES. Se faltar algum, registre no log e saia com sys.exit(1).
- Trate exceções em blocos try/except. Em caso de erro fatal, salve o log JSON com status "error" e a mensagem do erro antes de encerrar.

════════════════════════════════════════
FORMATO DE SAÍDA
RETORNE APENAS O CÓDIGO PYTHON PURO.
Sem explicações. Sem markdown (NÃO use blocos de código com ```python). Sem comentários introdutórios. A primeira linha deve ser um import ou comentário."""


def generate_execution_plan(
    files_analysis: dict,
    user_objective: str,
    config: dict,
) -> str:
    """
    Gera o plano de execução para a automação usando o Agente 4.
    """
    analysis_json = json.dumps(files_analysis, ensure_ascii=False, indent=2)

    user_message = f"""OBJETIVO DO USUÁRIO / NECESSIDADE:
{user_objective}

ESTRUTURA DETECTADA DOS ARQUIVOS DE ENTRADA:
{analysis_json}

Monte o Plano de Execução ETL detalhado em Markdown."""

    provider = config.get("agent4_provider", "google")
    model = config.get("agent4_model", "gemini-3.5-flash")
    api_key = config.get(f"{provider}_api_key", "")
    temperature = config.get("agent4_temperature", 0.3)
    sys_prompt = config.get("agent4_system_instructions", "")

    full_sys = SYSTEM_PLAN_PROMPT
    if sys_prompt.strip():
        full_sys += f"\n\nInstruções Adicionais do Sistema:\n{sys_prompt}"

    plan = call_llm(provider, model, api_key, full_sys, user_message,
                    temperature=temperature, max_tokens=4000)
    return plan


def generate_automation_code(
    files_analysis: dict,
    user_objective: str,
    approved_plan: str,
    adjustments: str,
    config: dict,
) -> str:
    """
    Gera o script Python de automação com base no plano de execução aprovado.
    """
    analysis_json = json.dumps(files_analysis, ensure_ascii=False, indent=2)

    user_message = f"""OBJETIVO:
{user_objective}

PLANO DE EXECUÇÃO APROVADO:
{approved_plan}

AJUSTES/INSTRUÇÕES ADICIONAIS:
{adjustments}

ESTRUTURA DOS ARQUIVOS:
{analysis_json}

Gere o código Python puro correspondente. Lembre-se: as variáveis INPUT_FILES, OUTPUT_PATH e LOG_PATH já estão disponíveis globalmente. Não as redefina. Não omita partes de lógica ou use reticências."""

    provider = config.get("agent4_provider", "google")
    model = config.get("agent4_model", "gemini-3.5-flash")
    api_key = config.get(f"{provider}_api_key", "")
    temperature = config.get("agent4_temperature", 0.2)
    sys_prompt = config.get("agent4_system_instructions", "")

    full_sys = SYSTEM_CODE_PROMPT
    if sys_prompt.strip():
        full_sys += f"\n\nInstruções Adicionais do Sistema:\n{sys_prompt}"

    code = call_llm(provider, model, api_key, full_sys, user_message,
                    temperature=temperature, max_tokens=8000)

    # Limpeza de markdown se o LLM ignorar a instrução
    code = code.strip()
    if code.startswith("```"):
        parts = code.split("```")
        code = parts[1] if len(parts) > 1 else code
        if code.startswith("python"):
            code = code[6:]
    code = code.strip().rstrip("```").strip()

    return code


def generate_automation_summary(code: str, objective: str, config: dict) -> str:
    """
    Gera um resumo legível por humanos sobre o que o script de automação realiza.
    """
    system = """Você é um especialista em comunicação técnica.
Explique em termos de negócios o que o script Python gerado faz para atingir o objetivo do usuário.
Seja conciso, amigável e profissional. Máximo 150 palavras."""

    user = f"""Objetivo do Usuário:
{objective}

Código Gerado:
{code}

Explique resumidamente o funcionamento desse script."""

    provider = config.get("agent4_provider", "google")
    model = config.get("agent4_model", "gemini-3.5-flash")
    api_key = config.get(f"{provider}_api_key", "")

    try:
        return call_llm(provider, model, api_key, system, user,
                        temperature=0.3, max_tokens=400)
    except Exception:
        return "Script de automação gerado com sucesso para processar e exportar os dados."
