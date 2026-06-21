import pandas as pd
import numpy as np
import os
import json
import re
import unicodedata
from datetime import datetime

# ==============================================================================
# FUNÇÕES AUXILIARES DE PARSING E NORMALIZAÇÃO
# ==============================================================================

def normalize_text(text: str) -> str:
    """
    Normaliza uma string: remove acentos, caracteres especiais,
    converte para minúsculas e remove espaços extras.
    """
    if not isinstance(text, str):
        return ''
    try:
        # Remove acentos
        text = ''.join(c for c in unicodedata.normalize('NFD', text)
                       if unicodedata.category(c) != 'Mn')
        # Remove caracteres especiais, mantendo alfanuméricos, hífens e espaços
        text = re.sub(r'[^a-zA-Z0-9\s-]', '', text)
        # Converte para minúsculas e remove espaços no início/fim
        text = text.lower().strip()
        return text
    except Exception:
        return ''

def read_csv_with_fallback(path: str) -> pd.DataFrame:
    """
    Tenta ler um arquivo CSV com diferentes encodings e detecta o separador automaticamente.
    """
    encodings_to_try = ['utf-8', 'latin-1', 'cp1252']
    for encoding in encodings_to_try:
        try:
            # Adicionado sep=None e engine='python' para detecção automática do separador
            return pd.read_csv(path, encoding=encoding, sep=None, engine='python')
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    raise ValueError(f"Não foi possível ler o arquivo {os.path.basename(path)} com os encodings testados: {encodings_to_try}")

def parse_structured_file(path: str) -> pd.DataFrame:
    """
    Lê um arquivo estruturado (CSV, XLSX) e retorna um DataFrame.
    """
    _, extension = os.path.splitext(path)
    if extension.lower() == '.csv':
        return read_csv_with_fallback(path)
    elif extension.lower() in ['.xlsx', '.xls']:
        return pd.read_excel(path)
    else:
        raise ValueError(f"Formato de arquivo não suportado: {extension}")

# Funções de parser para arquivos legados (placeholders)
# Estas funções não serão usadas nesta execução específica, mas demonstram
# a capacidade de estender o script para formatos legados.

def parse_legacy_txt(path: str) -> pd.DataFrame:
    """
    Parser para um arquivo TXT de formato legado.
    (Implementação dependeria da estrutura específica do arquivo)
    """
    raise NotImplementedError("Parser para TXT legado não implementado.")

def parse_legacy_pdf(path: str) -> pd.DataFrame:
    """
    Parser para um arquivo PDF de formato legado.
    (Implementação dependeria da estrutura específica do arquivo)
    """
    raise NotImplementedError("Parser para PDF legado não implementado.")


# ==============================================================================
# FUNÇÃO PRINCIPAL DE EXECUÇÃO
# ==============================================================================

def main():
    """
    Orquestra todo o processo de conciliação: leitura, normalização,
    processamento e geração de saídas.
    """
    start_time = datetime.now()
    log_data = {
        "timestamp_inicio": start_time.isoformat(),
        "status_execucao": "INICIADO",
        "arquivos_entrada": INPUT_FILES,
        "caminho_saida_excel": OUTPUT_PATH,
        "caminho_saida_log": LOG_PATH,
        "erros": [],
        "estatisticas": {
            "registros_originais": {},
            "registros_processados": {},
            "resultados_conciliacao": {}
        }
    }

    try:
        # 1. Validação dos arquivos de entrada
        for file_path in INPUT_FILES:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Arquivo de entrada não encontrado: {file_path}")

        # 2. Leitura e Parse dos arquivos
        dataframes = {}
        for file_path in INPUT_FILES:
            filename = os.path.basename(file_path)
            df = parse_structured_file(file_path)
            df.columns = [col.strip() for col in df.columns]
            log_data["estatisticas"]["registros_originais"][filename] = len(df)
            dataframes[filename] = df

        # Mapeamento e normalização específicos para cada arquivo
        # Arquivo A: Razão Contábil
        df_a = dataframes.get('razao_contabil_sistema (1).xlsx')
        if df_a is None:
            raise ValueError("Arquivo 'razao_contabil_sistema (1).xlsx' não encontrado na entrada.")
        
        df_a = df_a.rename(columns={
            "Chave Conciliação": "chave_conciliacao",
            "Data Lançamento": "data_lancamento_a",
            "Valor (R$)": "valor_a",
            "Histórico Contábil": "historico_a"
        })
        df_a['chave_conciliacao'] = df_a['chave_conciliacao'].astype(str).apply(normalize_text)
        df_a['valor_a'] = pd.to_numeric(df_a['valor_a'], errors='coerce')
        df_a['data_lancamento_a'] = pd.to_datetime(df_a['data_lancamento_a'], dayfirst=True, errors='coerce')
        df_a = df_a.dropna(subset=['chave_conciliacao', 'valor_a'])
        df_a = df_a.drop_duplicates(subset=['chave_conciliacao'], keep='first')
        log_data["estatisticas"]["registros_processados"]['razao_contabil_sistema (1).xlsx'] = len(df_a)

        # Arquivo B: Extrato Bancário
        df_b = dataframes.get('extrato_bancario_sistema.csv')
        if df_b is None:
            raise ValueError("Arquivo 'extrato_bancario_sistema.csv' não encontrado na entrada.")

        df_b = df_b.rename(columns={
            "Chave_Conciliacao": "chave_conciliacao",
            "Data_Lancamento": "data_lancamento_b",
            "Valor_Original": "valor_b",
            "Historico_Banco": "historico_b"
        })
        df_b['chave_conciliacao'] = df_b['chave_conciliacao'].astype(str).apply(normalize_text)
        df_b['valor_b'] = pd.to_numeric(df_b['valor_b'], errors='coerce')
        df_b['data_lancamento_b'] = pd.to_datetime(df_b['data_lancamento_b'], dayfirst=True, errors='coerce')
        df_b = df_b.dropna(subset=['chave_conciliacao', 'valor_b'])
        df_b = df_b.drop_duplicates(subset=['chave_conciliacao'], keep='first')
        log_data["estatisticas"]["registros_processados"]['extrato_bancario_sistema.csv'] = len(df_b)

        # 3. Conciliação
        df_merged = pd.merge(df_a, df_b, on='chave_conciliacao', how='outer')
        df_merged['diferenca'] = (df_merged['valor_a'].fillna(0) - df_merged['valor_b'].fillna(0)).round(2)

        conditions = [
            (df_merged['valor_a'].notna()) & (df_merged['valor_b'].notna()) & (df_merged['diferenca'] == 0),
            (df_merged['valor_a'].notna()) & (df_merged['valor_b'].notna()) & (df_merged['diferenca'] != 0),
            (df_merged['valor_b'].isna()),
            (df_merged['valor_a'].isna())
        ]
        choices = [
            'Conciliado',
            'Divergência de Valor',
            'Pendente no Extrato',
            'Pendente na Contabilidade'
        ]
        df_merged['status'] = np.select(conditions, choices, default='Erro Inesperado')

        # 4. Geração do Relatório Excel
        with pd.ExcelWriter(OUTPUT_PATH, engine='xlsxwriter') as writer:
            # Aba de Resumo
            summary = df_merged['status'].value_counts().reset_index()
            summary.columns = ['Status', 'Quantidade']
            summary.to_excel(writer, sheet_name='Resumo', index=False)
            log_data["estatisticas"]["resultados_conciliacao"] = summary.set_index('Status')['Quantidade'].to_dict()

            # Aba com todos os resultados
            df_merged.to_excel(writer, sheet_name='Resultado Completo', index=False)

            # Abas por status
            for status, group_df in df_merged.groupby('status'):
                group_df.to_excel(writer, sheet_name=status, index=False)

        log_data["status_execucao"] = "SUCESSO"

    except Exception as e:
        log_data["status_execucao"] = "ERRO"
        log_data["erros"].append(str(e))
        # Propaga a exceção para que o executor saiba que o script falhou
        raise
    finally:
        end_time = datetime.now()
        log_data["timestamp_fim"] = end_time.isoformat()
        log_data["duracao_segundos"] = (end_time - start_time).total_seconds()
        with open(LOG_PATH, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, ensure_ascii=False, indent=4)

# Bloco de execução principal
if __name__ == '__main__':
    # Estas variáveis seriam definidas pelo ambiente de execução
    # Para teste local, descomente e aponte para seus arquivos
    # INPUT_FILES = ['path/to/razao_contabil_sistema (1).xlsx', 'path/to/extrato_bancario_sistema.csv']
    # OUTPUT_PATH = 'conciliacao_resultado.xlsx'
    # LOG_PATH = 'conciliacao_log.json'
    main()
