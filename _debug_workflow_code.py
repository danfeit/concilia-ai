import pandas as pd
import numpy as np
import json
import os
import re
import unicodedata
from datetime import datetime

# ==============================================================================
# CONFIGURAÇÃO - Estas variáveis são injetadas no escopo de execução
# Para testes locais, descomente e ajuste os caminhos abaixo.
# ==============================================================================
# SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# INPUT_FILES = [
#     os.path.join(SCRIPT_DIR, 'extrato_bancario_sistema.csv'),
#     os.path.join(SCRIPT_DIR, 'razao_contabil_sistema (1).xlsx')
# ]
# OUTPUT_PATH = os.path.join(SCRIPT_DIR, 'resultado_conciliacao.xlsx')
# LOG_PATH = os.path.join(SCRIPT_DIR, 'log_execucao.json')
# ==============================================================================


def normalize_text(text: str) -> str:
    """Normaliza uma string: remove acentos, converte para minúsculas,
    remove caracteres especiais e espaços extras."""
    if not isinstance(text, str):
        return ""
    try:
        # Remove acentos
        text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
        # Converte para minúsculas
        text = text.lower()
        # Remove caracteres não alfanuméricos (exceto hífen)
        text = re.sub(r'[^a-z0-9-]', '', text)
        # Remove espaços extras no início e fim
        text = text.strip()
        return text
    except Exception:
        return ""

def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza os nomes das colunas de um DataFrame."""
    new_columns = {}
    for col in df.columns:
        new_col = str(col).strip().lower()
        new_col = new_col.replace(' ', '_').replace('(', '').replace(')', '').replace('r$', '')
        new_col = ''.join(c for c in unicodedata.normalize('NFD', new_col) if unicodedata.category(c) != 'Mn')
        new_col = re.sub(r'_+', '_', new_col)
        new_columns[col] = new_col
    df = df.rename(columns=new_columns)
    return df

def read_csv_with_fallback_encoding(file_path: str) -> pd.DataFrame:
    """Tenta ler um CSV com diferentes encodings."""
    encodings_to_try = ['utf-8', 'latin-1', 'cp1252']
    for encoding in encodings_to_try:
        try:
            return pd.read_csv(file_path, encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Não foi possível decodificar o arquivo {os.path.basename(file_path)} com os encodings testados.")

def parse_legacy_txt(file_path: str) -> pd.DataFrame:
    """Função de parser para arquivos TXT legados."""
    # Esta função é um placeholder. A lógica de parsing específica
    # baseada na arquitetura do arquivo legado seria implementada aqui.
    raise NotImplementedError(f"Parser para TXT legado não implementado para {file_path}")

def parse_legacy_pdf(file_path: str) -> pd.DataFrame:
    """Função de parser para arquivos PDF legados."""
    # Esta função é um placeholder. A lógica de parsing específica
    # baseada na arquitetura do arquivo legado seria implementada aqui.
    raise NotImplementedError(f"Parser para PDF legado não implementado para {file_path}")

def load_and_prepare_data(file_path: str) -> pd.DataFrame:
    """Carrega, parseia e prepara um arquivo de entrada."""
    filename = os.path.basename(file_path)
    
    if filename.endswith('.csv'):
        df = read_csv_with_fallback_encoding(file_path)
    elif filename.endswith(('.xlsx', '.xls')):
        df = pd.read_excel(file_path)
    elif filename.endswith('.txt'):
        df = parse_legacy_txt(file_path)
    elif filename.endswith('.pdf'):
        df = parse_legacy_pdf(file_path)
    else:
        raise ValueError(f"Formato de arquivo não suportado: {filename}")

    df = normalize_column_names(df)
    
    # Mapeamento específico baseado na análise dos arquivos
    rename_map = {}
    if 'chave_conciliacao' in df.columns: # CSV
        rename_map = {
            'chave_conciliacao': 'chave_conciliacao_norm',
            'data_lancamento': 'data',
            'valor_original': 'valor',
            'historico_banco': 'historico'
        }
    elif 'chave_conciliacao' in df.columns: # XLSX
        rename_map = {
            'chave_conciliacao': 'chave_conciliacao_norm',
            'data_lancamento': 'data',
            'valor_': 'valor',
            'historico_contabil': 'historico'
        }
    
    df = df.rename(columns=rename_map)
    
    if 'chave_conciliacao_norm' not in df.columns:
        raise KeyError(f"Coluna de chave 'chave_conciliacao' não encontrada em {filename} após normalização.")
        
    # Higienização e normalização dos dados
    df['chave_conciliacao_norm'] = df['chave_conciliacao_norm'].apply(normalize_text)
    df = df.dropna(subset=['chave_conciliacao_norm'])
    df = df[df['chave_conciliacao_norm'] != '']

    if 'data' in df.columns:
        df['data'] = pd.to_datetime(df['data'], dayfirst=True, errors='coerce')
    
    if 'valor' in df.columns:
        df['valor'] = pd.to_numeric(df['valor'], errors='coerce')

    return df

def main():
    """Função principal que orquestra o processo de conciliação."""
    log_data = {
        "timestamp_inicio": datetime.now().isoformat(),
        "status_execucao": "INICIADO",
        "arquivos_processados": [os.path.basename(f) for f in INPUT_FILES],
        "estatisticas_entrada": {},
        "estatisticas_conciliacao": {},
        "erros": []
    }

    try:
        # 1. Validação dos arquivos de entrada
        if len(INPUT_FILES) != 2:
            raise ValueError("Esperado exatamente 2 arquivos de entrada.")
        for file_path in INPUT_FILES:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Arquivo de entrada não encontrado: {file_path}")

        # 2. Leitura e preparação dos dados
        df_a_raw = load_and_prepare_data(INPUT_FILES[0])
        df_b_raw = load_and_prepare_data(INPUT_FILES[1])

        log_data["estatisticas_entrada"][os.path.basename(INPUT_FILES[0])] = {
            "linhas_lidas": len(df_a_raw),
            "colunas_originais": list(pd.read_csv(INPUT_FILES[0]).columns) if INPUT_FILES[0].endswith('.csv') else list(pd.read_excel(INPUT_FILES[0]).columns)
        }
        log_data["estatisticas_entrada"][os.path.basename(INPUT_FILES[1])] = {
            "linhas_lidas": len(df_b_raw),
            "colunas_originais": list(pd.read_csv(INPUT_FILES[1]).columns) if INPUT_FILES[1].endswith('.csv') else list(pd.read_excel(INPUT_FILES[1]).columns)
        }

        # 3. Execução da conciliação (Merge)
        merged_df = pd.merge(
            df_a_raw,
            df_b_raw,
            on='chave_conciliacao_norm',
            how='outer',
            suffixes=('_a', '_b'),
            indicator=True
        )

        # 4. Classificação dos resultados
        conditions = [
            (merged_df['_merge'] == 'both') & (np.isclose(merged_df['valor_a'], merged_df['valor_b'])),
            (merged_df['_merge'] == 'both') & (~np.isclose(merged_df['valor_a'], merged_df['valor_b'])),
            (merged_df['_merge'] == 'left_only'),
            (merged_df['_merge'] == 'right_only')
        ]
        choices = ['Conciliados', 'Divergências', 'Apenas em A', 'Apenas em B']
        merged_df['status'] = np.select(conditions, choices, default='Erro')
        
        merged_df['diferenca_valor'] = (merged_df['valor_a'] - merged_df['valor_b']).fillna(0)
        merged_df['data_conciliacao'] = merged_df['data_a'].fillna(merged_df['data_b'])
        
        # Ordenar por data para visão cronológica
        merged_df = merged_df.sort_values(by='data_conciliacao', ascending=True)

        # 5. Geração dos DataFrames de saída
        conciliados_df = merged_df[merged_df['status'] == 'Conciliados']
        apenas_a_df = merged_df[merged_df['status'] == 'Apenas em A']
        apenas_b_df = merged_df[merged_df['status'] == 'Apenas em B']
        divergencias_df = merged_df[merged_df['status'] == 'Divergências']

        # 6. Geração do arquivo Excel de saída
        with pd.ExcelWriter(OUTPUT_PATH, engine='openpyxl') as writer:
            conciliados_df.to_excel(writer, sheet_name='Conciliados', index=False)
            apenas_a_df.to_excel(writer, sheet_name='Apenas em A', index=False)
            apenas_b_df.to_excel(writer, sheet_name='Apenas em B', index=False)
            divergencias_df.to_excel(writer, sheet_name='Divergências', index=False)

        # 7. Atualização do log com sucesso
        log_data["status_execucao"] = "SUCESSO"
        log_data["caminho_saida_excel"] = OUTPUT_PATH
        log_data["estatisticas_conciliacao"] = {
            "total_conciliados": len(conciliados_df),
            "total_apenas_em_a": len(apenas_a_df),
            "total_apenas_em_b": len(apenas_b_df),
            "total_divergencias": len(divergencias_df),
            "total_chaves_unicas_processadas": len(merged_df)
        }

    except Exception as e:
        log_data["status_execucao"] = "FALHA"
        log_data["erros"].append({
            "tipo": type(e).__name__,
            "mensagem": str(e)
        })
        # Imprime o erro no console para debug
        print(f"ERRO: {type(e).__name__} - {e}")

    finally:
        # 8. Salvamento do log JSON
        log_data["timestamp_fim"] = datetime.now().isoformat()
        with open(LOG_PATH, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=4, ensure_ascii=False)

if __name__ == '__main__':
    # Bloco para execução standalone do script.
    # As variáveis INPUT_FILES, OUTPUT_PATH e LOG_PATH devem ser definidas aqui
    # se o script não for executado em um ambiente onde elas já existem.
    
    # Exemplo de definição para teste:
    # Criando arquivos dummy para o teste
    try:
        os.makedirs("test_data", exist_ok=True)
        
        csv_data = """Chave_Conciliacao,Data_Lancamento,Valor_Original,Historico_Banco
CONC-2026-001,10/05/2026,12500.00,COBRANCA ELETRONICA LIQ NF1024
CONC-2026-002,11/05/2026,500.50,PAGAMENTO FORNECEDOR ABC
CONC-2026-003,12/05/2026,3000.00,TRANSFERENCIA RECEBIDA
CONC-2026-005,14/05/2026,850.00,DEPOSITO IDENTIFICADO"""
        with open("test_data/extrato_bancario_sistema.csv", "w", encoding="utf-8") as f:
            f.write(csv_data)

        excel_data = {
            "Chave Conciliação": ["CONC-2026-001", "CONC-2026-002", "CONC-2026-004", "CONC-2026-003"],
            "Data Lançamento": ["10/05/2026", "11/05/2026", "13/05/2026", "12/05/2026"],
            "Valor (R$)": [12500.00, 500.75, 200.00, 3000.00],
            "Histórico Contábil": ["Recebimento Cliente - NF 1024", "Pgto Fornecedor ABC", "Recebimento PIX", "Transf. Recebida de Matriz"]
        }
        pd.DataFrame(excel_data).to_excel("test_data/razao_contabil_sistema.xlsx", index=False)

        # Definindo as variáveis globais para o teste
        INPUT_FILES = [
            "test_data/extrato_bancario_sistema.csv",
            "test_data/razao_contabil_sistema.xlsx"
        ]
        OUTPUT_PATH = "resultado_conciliacao.xlsx"
        LOG_PATH = "log_execucao.json"

        print("Iniciando processo de conciliação...")
        main()
        print(f"Processo concluído. Verifique os arquivos '{OUTPUT_PATH}' e '{LOG_PATH}'.")

    except Exception as e:
        print(f"Ocorreu um erro durante a execução do teste: {e}")