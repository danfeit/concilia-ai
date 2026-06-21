"""
agents/codegen_agent.py — Agente 1: Geração do script Python de conciliação.
Gera código completo incluindo parsers para arquivos legados (TXT/PDF).
"""

from __future__ import annotations
from agents.base_agent import call_llm


SYSTEM_PROMPT = """Você é um engenheiro de dados sênior especialista em Python e pandas.
Sua tarefa é gerar um script Python COMPLETO e FUNCIONAL de conciliação de dados.

════════════════════════════════════════
ESTRUTURA OBRIGATÓRIA DO SCRIPT (nesta ordem)
════════════════════════════════════════
1. Imports (todos na parte superior — NUNCA importe dentro de funções)
2. Constantes e configurações
3. Funções auxiliares (parsers, normalização, etc.)
4. Função principal `main()`
5. Bloco de entrada: `if __name__ == "__main__": main()`  ← OBRIGATÓRIO, NUNCA COMENTADO

════════════════════════════════════════
VARIÁVEIS DE ESCOPO (JÁ DEFINIDAS — NÃO REDECLARE)
════════════════════════════════════════
- INPUT_FILES  → list[str]: caminhos dos arquivos de entrada
- OUTPUT_PATH  → str: caminho do Excel de saída
- LOG_PATH     → str: caminho do log JSON de saída

════════════════════════════════════════
LEITURA DE ARQUIVOS
════════════════════════════════════════
CSV/TXT delimitados:
  df = pd.read_csv(path, sep=None, engine='python', encoding='utf-8-sig')
  df.columns = [c.replace('\ufeff', '').strip() for c in df.columns]

Encoding fallback (use nesta ordem): utf-8-sig → utf-8 → latin-1 → cp1252
  Implemente com try/except encadeado, nunca assuma um único encoding.

PDF legado:
  Use pdfplumber. Itere pdfplumber.open(path).pages, extraia tabelas com
  page.extract_table() ou texto com page.extract_text(). Trate retorno None.

TXT posicional/legado:
  Baseie o parser EXATAMENTE na `legacy_architecture` fornecida na análise.
  Use slicing de string por posição (linha[ini:fim]) conforme o layout descrito.

════════════════════════════════════════
NORMALIZAÇÃO DE COLUNAS-CHAVE
════════════════════════════════════════
Aplique em TODAS as colunas usadas como chave de conciliação:
  import unicodedata
  def normalize(val):
      if pd.isna(val): return ""
      s = str(val).strip().lower()
      s = unicodedata.normalize('NFKD', s)
      s = ''.join(c for c in s if not unicodedata.combining(c))
      return re.sub(r'[^a-z0-9]', '', s)

════════════════════════════════════════
SAÍDA EXCEL (4 ABAS OBRIGATÓRIAS)
════════════════════════════════════════
Use pd.ExcelWriter(OUTPUT_PATH, engine='openpyxl') com as abas:
  - "Conciliados"   → registros com match nos dois lados
  - "Apenas em A"   → registros sem correspondência no arquivo A
  - "Apenas em B"   → registros sem correspondência no arquivo B
  - "Divergências"  → registros com match na chave mas valores divergentes

Se um DataFrame estiver vazio, grave-o mesmo assim (aba com cabeçalho, sem linhas).
NUNCA omita uma aba.

════════════════════════════════════════
LOG JSON (LOG_PATH)
════════════════════════════════════════
Salve ao final de main(), dentro de bloco try/except:
{
  "timestamp": "<ISO 8601>",
  "status": "success" | "error",
  "totais": {
    "arquivo_a": <int>,
    "arquivo_b": <int>,
    "conciliados": <int>,
    "apenas_a": <int>,
    "apenas_b": <int>,
    "divergencias": <int>
  },
  "erros": []
}

════════════════════════════════════════
TRATAMENTO DE ERROS
════════════════════════════════════════
- Valide existência de cada arquivo em INPUT_FILES com os.path.exists() antes de ler.
  Se ausente, registre em erros[] do log e encerre com sys.exit(1).
- Envolva cada leitura de arquivo em try/except com mensagem descritiva.
- Erros não fatais (ex: linha malformada) → registre no log e continue.
- Erros fatais → registre no log, salve LOG_PATH e relance a exceção.

════════════════════════════════════════
CHECKLIST MENTAL — REVISE ANTES DE RESPONDER
════════════════════════════════════════
[ ] Todos os imports estão no topo do arquivo?
[ ] unicodedata e re foram importados (usados na normalização)?
[ ] Nenhuma variável é usada antes de ser declarada?
[ ] OUTPUT_PATH está sendo salvo via ExcelWriter com todas as 4 abas?
[ ] LOG_PATH está sendo salvo ao final de main()?
[ ] O bloco `if __name__ == "__main__": main()` está presente e NÃO comentado?
[ ] Nenhum código está fora de função (exceto imports e constantes)?

Corrija qualquer item marcado como falho antes de gerar a resposta.

════════════════════════════════════════
FORMATO DE SAÍDA
════════════════════════════════════════
RETORNE APENAS O CÓDIGO PYTHON PURO.
Sem explicações. Sem markdown. Sem blocos de código. Sem comentários introdutórios.
A primeira linha da resposta deve ser um import ou um comentário de shebang."""


def generate_code(
    analysis: dict,
    user_objective: str,
    user_adjustments: str,
    config: dict,
) -> dict:
    """
    Gera o script Python de conciliação baseado na análise de estrutura.
    Retorna: {"code": str, "summary": str}
    """
    import json

    analysis_json = json.dumps(analysis, ensure_ascii=False, indent=2)

    adjustments_section = ""
    if user_adjustments.strip():
        adjustments_section = f"\nAJUSTES SOLICITADOS PELO USUÁRIO:\n{user_adjustments}\n"

    user_message = f"""OBJETIVO DA CONCILIAÇÃO:
{user_objective}
{adjustments_section}
ANÁLISE DE ESTRUTURA DOS ARQUIVOS:
{analysis_json}

Gere o script Python completo de conciliação.
Lembre-se: as variáveis INPUT_FILES, OUTPUT_PATH e LOG_PATH já estarão definidas no escopo quando o script for executado — use-as diretamente sem redefinir.

Para arquivos legados, baseie o parser exatamente na arquitetura descrita em legacy_architecture.

REQUISITO CRÍTICO DE INTEGRIDADE DO CÓDIGO:
1. Você OBRIGATORIAMENTE deve gerar o script COMPLETO do início ao fim.
2. NUNCA utilize reticências (...), atalhos ou comentários como "# [resto do código permanece igual]" ou "# [insira lógica de parser aqui]".
3. Escreva todas as funções auxiliares, parsers de arquivos estruturados e legados por extenso e com lógica funcional completa.
4. Qualquer omissão ou espaço reservado quebrará a execução automática e é considerado falha grave.
5. Siga rigorosamente a estrutura ordenada do script: imports no topo, constantes, funções auxiliares, main(), e o bloco `if __name__ == "__main__": main()` executável no final.

RETORNE APENAS O CÓDIGO PYTHON PURO."""

    provider = config.get("agent1_provider", "anthropic")
    model = config.get("agent1_model", "claude-haiku-4-5")
    api_key = config.get(f"{provider}_api_key", "")
    temperature = config.get("agent1_temperature", 0.2)

    sys_prompt = SYSTEM_PROMPT
    add_sys = config.get("agent1_system_instructions", "")
    if add_sys:
        sys_prompt += f"\n\nInstruções Adicionais do Sistema:\n{add_sys}"

    code = call_llm(provider, model, api_key, sys_prompt, user_message,
                    temperature=temperature, max_tokens=8000)

    # Remove blocos de markdown se presentes
    code = code.strip()
    if code.startswith("```"):
        parts = code.split("```")
        code = parts[1] if len(parts) > 1 else code
        if code.startswith("python"):
            code = code[6:]
    code = code.strip().rstrip("```").strip()

    return {"code": code}


def generate_summary(code: str, analysis: dict, config: dict) -> str:
    """
    Gera um resumo em linguagem natural do que o código faz.
    Chamada separada para não inflar o prompt de geração de código.
    """
    import json

    system = """Você é um especialista em comunicação técnica.
Explique o que um script Python de conciliação de dados faz em linguagem simples,
clara e amigável para usuários não técnicos. Máximo 200 palavras."""

    user = f"""Script de conciliação gerado. Estratégia: {analysis.get('strategy', 'N/A')}

Arquivos processados: {json.dumps([f['filename'] for f in analysis.get('files', [])], ensure_ascii=False)}

Resumo das chaves de relacionamento: {json.dumps(analysis.get('relationship_keys', []), ensure_ascii=False)}

Explique o que este script fará quando executado."""

    provider = config.get("agent1_provider", "anthropic")
    model = config.get("agent1_model", "claude-haiku-4")
    api_key = config.get(f"{provider}_api_key", "")

    try:
        return call_llm(provider, model, api_key, system, user,
                        temperature=0.3, max_tokens=500)
    except Exception:
        return "Script de conciliação gerado com sucesso."
