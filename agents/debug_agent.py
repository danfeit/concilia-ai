"""
agents/debug_agent.py — Agente 3: Auto-diagnóstico e correção de código com erro.

Quando uma execução falha, este agente:
1. Analisa o erro (traceback, log, stderr)
2. Lê o código original
3. Propõe um código corrigido pronto para execução
"""

from __future__ import annotations
import json
from agents.base_agent import call_llm


SYSTEM_PROMPT = """Você é um especialista em debugging e engenharia de dados com Python/pandas.
O código de conciliação atual falhou.

Sua tarefa é analisar o erro, o código atual, e a estrutura dos arquivos de entrada, 
e fornecer o **CÓDIGO PYTHON COMPLETO E CORRIGIDO**.

DIRETRIZES DE CORREÇÃO:
1. Mantenha a estrutura geral do código, faça apenas as alterações necessárias para resolver o bug.
2. Não altere os nomes das funções principais (main, parse_structured_file, etc).
3. Se o erro for um `KeyError` em colunas (ex: não encontrou 'chave_conciliacao' ou similar), **SEMPRE LIMPE OS NOMES DAS COLUNAS** no momento da leitura para remover BOM (ex: \\ufeff) ou espaços invisíveis: `df.columns = [str(c).replace('\\ufeff', '').strip() for c in df.columns]`.
4. Em falhas de leitura de CSV, garanta que a leitura está robusta com detecção automática de separador (sep=None, engine='python') e use primariamente o encoding 'utf-8-sig'.
5. Valide que as conversões de tipos e normalizações ocorram sem quebrar se existirem valores nulos.
6. A saída DEVE ser um JSON válido contendo as chaves 'diagnosis', 'what_was_fixed' e 'corrected_code'. NUNCA retorne blocos de código com ```json ou markdown ao redor do JSON.
7. **RESTRIÇÃO DE IMPORTAÇÃO**: O código corrigido DEVE utilizar exclusivamente dependências do `requirements.txt` (`pandas`, `openpyxl`, `pdfplumber`, `fitz` / `PyMuPDF`, `sqlalchemy`, `pyarrow`, `plotly`). **É TERMINANTEMENTE PROIBIDO importar ou utilizar `xlsxwriter`**. Se o código original utilizava `xlsxwriter` para gravar arquivos Excel, mude obrigatoriamente para `openpyxl` (ex: `with pd.ExcelWriter(OUTPUT_PATH, engine='openpyxl') as writer:`).
8. **CÓDIGO 100% COMPLETO (OBRIGATÓRIO)**: O código retornado no campo `corrected_code` do JSON deve ser o script **INTEIRO E COMPLETO**, de ponta a ponta. NUNCA utilize reticências (`...`), atalhos ou comentários como "# [resto do código igual]". Você deve reescrever TODAS as linhas de código e funções por completo.

REGRAS OBRIGATÓRIAS:
- Use as variáveis INPUT_FILES, OUTPUT_PATH e LOG_PATH já presentes no escopo (NÃO redefina)
- O script deve terminar com sucesso E gerar o arquivo Excel em OUTPUT_PATH usando openpyxl
- Inclua tratamento de erro com `raise` ao final do bloco except (para que o executor detecte falhas)
- O script deve ser executável: NUNCA DEIXE a chamada para a função principal como comentário. O código corrigido OBRIGATORIAMENTE DEVE incluir `if __name__ == "__main__": main()` funcional ao final.

AUTO-REVISÃO ANTES DE ENTREGAR (FAÇA MENTALMENTE):
- Revise as alterações linha a linha para garantir que o bug foi realmente resolvido.
- Certifique-se de que não foi importado `xlsxwriter` e que a engine do ExcelWriter é `openpyxl`.
- Verifique se não foram introduzidos novos erros de sintaxe ou de recuo (indentação).
- Verifique se a chamada principal do script está presente e executável.
- Certifique-se de que o código em `corrected_code` não contém placeholders ou partes omitidas.
Resolva quaisquer falhas notadas durante a sua auto-revisão mental antes de gerar a saída final em JSON.

FORMATO DE RESPOSTA (JSON puro, sem markdown):
{
  "diagnosis": "Causa raiz do erro em 2-3 frases diretas",
  "what_was_fixed": ["Item 1 corrigido", "Item 2 corrigido"],
  "corrected_code": "import pandas as pd\\n..."
}"""


def analyze_and_fix(
    original_code: str,
    error_message: str,
    stderr: str,
    log_content: dict,
    input_files_info: list[dict],
    config: dict,
) -> dict:
    """
    Analisa o erro e retorna código corrigido.

    Retorna:
        {
            "diagnosis": str,
            "what_was_fixed": list[str],
            "corrected_code": str,
            "raw": str  (se JSON inválido)
        }
    """
    files_summary = json.dumps(input_files_info, ensure_ascii=False, indent=2)
    log_summary = json.dumps(
        {k: v for k, v in log_content.items() if k not in ("stdout",)},
        ensure_ascii=False, indent=2
    )

    # Evita truncar o código original para que o agente veja todo o script e não apague trechos dele
    code_snippet = original_code
    err_snippet = (error_message or "")[:4000]
    stderr_snippet = (stderr or "")[:4000]

    user_message = f"""CÓDIGO ORIGINAL QUE FALHOU:
```python
{code_snippet}
```

MENSAGEM DE ERRO:
{err_snippet}

STDERR:
{stderr_snippet}

LOG DE EXECUÇÃO:
{log_summary}

INFORMAÇÕES DOS ARQUIVOS DE ENTRADA:
{files_summary}

Analise o erro, identifique a causa raiz e retorne o JSON com o código corrigido completo de ponta a ponta (escreva todas as funções por extenso, sem utilizar nenhum placeholder, reticências ou omitir partes do código)."""

    provider = config.get("agent3_provider", "anthropic")
    model    = config.get("agent3_model", "claude-haiku-4-5")
    api_key  = config.get(f"{provider}_api_key", "")
    temp     = float(config.get("agent3_temperature", 0.1))

    sys_prompt = SYSTEM_PROMPT
    add_sys = config.get("agent3_system_instructions", "")
    if add_sys:
        sys_prompt += f"\n\nInstruções Adicionais do Sistema:\n{add_sys}"

    raw = call_llm(
        provider, model, api_key,
        system_prompt=sys_prompt,
        user_message=user_message,
        temperature=temp,
        max_tokens=8000,
    )

    # Extrai JSON da resposta de forma robusta
    import re
    raw = raw.strip()
    
    # 1. Tenta achar bloco ```json ... ``` ou ``` ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        raw_json = match.group(1)
    else:
        # 2. Tenta extrair da primeira { até a última }
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw_json = raw[start:end+1]
        else:
            raw_json = raw
            
    try:
        result = json.loads(raw_json)
        
        # Lida com casos em que o modelo traduz as chaves para português
        code = result.get("corrected_code", "")
        if not code:
            code = result.get("codigo_corrigido", "")
        if not code:
            code = result.get("code", "")
            
        diagnosis = result.get("diagnosis", "")
        if not diagnosis:
            diagnosis = result.get("diagnostico", "Sem diagnóstico detalhado.")
            
        what_was_fixed = result.get("what_was_fixed", [])
        if not what_was_fixed:
            what_was_fixed = result.get("o_que_foi_corrigido", [])
            
        # Garante que o código não está envolvido em bloco markdown
        if isinstance(code, str):
            code = re.sub(r"^```(?:python)?\s*\n?", "", code, flags=re.IGNORECASE)
            code = re.sub(r"\n?```\s*$", "", code)
            code = code.strip()
            
        return {
            "diagnosis": diagnosis,
            "what_was_fixed": what_was_fixed if isinstance(what_was_fixed, list) else [str(what_was_fixed)],
            "corrected_code": code,
            "raw": raw
        }
        
    except json.JSONDecodeError:
        # Fallback: tentar extrair código com regex se JSON for inválido
        extracted_code = ""
        # 1. Tenta extrair bloco ```python ... ``` do raw
        match_md = re.search(r"```(?:python)?\s*\n(.*?)\n```", raw, re.DOTALL | re.IGNORECASE)
        if match_md:
            extracted_code = match_md.group(1).strip()
        else:
            # 2. Tenta encontrar a chave "corrected_code" / "codigo_corrigido" e o que vem depois
            match_json_key = re.search(r'"(?:corrected_code|codigo_corrigido)"\s*:\s*"(.*?)"(?:\s*\}|\s*,)', raw, re.DOTALL)
            if match_json_key:
                extracted_code = match_json_key.group(1)
                # Reverte escapes
                extracted_code = extracted_code.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
                
        return {
            "diagnosis": "Aviso: O modelo não retornou um formato JSON estrito, o resultado foi recuperado.",
            "what_was_fixed": ["Recuperação automática do texto devido à falha de formatação JSON."],
            "corrected_code": extracted_code,
            "raw": raw,
        }


def extract_input_info_from_paths(input_paths: list[str]) -> list[dict]:
    """
    Lê os arquivos de entrada e extrai colunas + amostra para o agente.
    Tolerante a falhas — retorna o máximo possível mesmo se um arquivo não abre.
    """
    import os
    import pandas as pd

    result = []
    for path in input_paths:
        info = {"path": path, "filename": os.path.basename(path)}
        try:
            fname = path.lower()
            if fname.endswith(".csv"):
                # Tenta separadores comuns
                df = None
                for enc in ("utf-8-sig", "latin-1", "cp1252"):
                    for sep in (";", ",", "\t", "|"):
                        try:
                            df = pd.read_csv(path, encoding=enc, sep=sep, nrows=5)
                            if df.shape[1] > 1:
                                break
                        except Exception:
                            continue
                    if df is not None and df.shape[1] > 1:
                        break
            elif fname.endswith((".xlsx", ".xls")):
                df = pd.read_excel(path, nrows=5)
            else:
                df = None

            if df is not None:
                info["columns"] = list(df.columns)
                info["dtypes"] = {col: str(df[col].dtype) for col in df.columns}
                info["sample_rows"] = df.head(3).fillna("").astype(str).to_dict(orient="records")
                info["shape"] = list(df.shape)
        except Exception as e:
            info["read_error"] = str(e)

        result.append(info)

    return result
