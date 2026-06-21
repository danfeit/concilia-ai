"""
Script de diagnóstico + geração do código corrigido para o workflow Firts_example.
Executar via: python _fix_workflow.py
"""

import sqlite3
import json

FIXED_CODE = '''
import pandas as pd
import numpy as np
import json
import os
import re
import unicodedata
from datetime import datetime


def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    try:
        text = "".join(
            c for c in unicodedata.normalize("NFD", text)
            if unicodedata.category(c) != "Mn"
        )
        text = text.lower().strip()
        text = re.sub(r"[^a-z0-9-]", "", text)
        return text
    except Exception:
        return ""


def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    new_cols = {}
    for col in df.columns:
        c = str(col).strip().lower()
        c = c.replace(" ", "_").replace("(", "").replace(")", "")
        c = c.replace("r$", "").replace("$", "")
        c = "".join(
            x for x in unicodedata.normalize("NFD", c)
            if unicodedata.category(x) != "Mn"
        )
        c = re.sub(r"_+", "_", c).strip("_")
        new_cols[col] = c
    return df.rename(columns=new_cols)


def read_csv_smart(file_path: str) -> pd.DataFrame:
    """Detecta encoding e separador automaticamente."""
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        for sep in (";", ",", "\\t", "|"):
            try:
                df = pd.read_csv(file_path, encoding=encoding, sep=sep, low_memory=False)
                if df.shape[1] > 1:
                    return df
            except Exception:
                continue
    # Última tentativa: sep=None (pandas auto-detect)
    return pd.read_csv(file_path, sep=None, engine="python", encoding="latin-1")


def load_file(file_path: str) -> pd.DataFrame:
    fname = os.path.basename(file_path).lower()
    if fname.endswith(".csv"):
        df = read_csv_smart(file_path)
    elif fname.endswith((".xlsx", ".xls")):
        df = pd.read_excel(file_path)
    else:
        raise ValueError(f"Formato nao suportado: {fname}")

    df = normalize_column_names(df)

    # Normaliza a coluna de data
    for candidate in ("data_lancamento", "data", "dt_lancamento", "data_lanamento"):
        if candidate in df.columns:
            df[candidate] = pd.to_datetime(df[candidate], dayfirst=True, errors="coerce")
            df.rename(columns={candidate: "data"}, inplace=True)
            break

    # Normaliza a coluna de valor
    for candidate in ("valor_original", "valor_r", "valor", "valor_r$", "valor_contabil"):
        if candidate in df.columns:
            df[candidate] = pd.to_numeric(
                df[candidate].astype(str)
                .str.replace(".", "", regex=False)
                .str.replace(",", ".", regex=False)
                .str.strip(),
                errors="coerce",
            )
            df.rename(columns={candidate: "valor"}, inplace=True)
            break

    # Normaliza a coluna de histórico
    for candidate in ("historico_banco", "historico_contabil", "historico",
                      "descricao", "historico_contbil"):
        if candidate in df.columns:
            df.rename(columns={candidate: "historico"}, inplace=True)
            break

    # Identifica a chave de conciliação
    chave_found = None
    for candidate in ("chave_conciliacao", "chave_conciliacao_norm", "chave"):
        if candidate in df.columns:
            chave_found = candidate
            break

    if chave_found is None:
        raise KeyError(
            f"Coluna de chave de conciliacao nao encontrada em {os.path.basename(file_path)}. "
            f"Colunas disponíveis: {list(df.columns)}"
        )

    df["chave_norm"] = df[chave_found].apply(normalize_text)
    df = df[df["chave_norm"].str.len() > 0].copy()

    return df


def main():
    log_data = {
        "timestamp_inicio": datetime.now().isoformat(),
        "status_execucao": "INICIADO",
        "arquivos_processados": [os.path.basename(f) for f in INPUT_FILES],
        "estatisticas_entrada": {},
        "estatisticas_conciliacao": {},
        "erros": [],
    }

    try:
        if len(INPUT_FILES) != 2:
            raise ValueError("Esperado exatamente 2 arquivos de entrada.")
        for fp in INPUT_FILES:
            if not os.path.exists(fp):
                raise FileNotFoundError(f"Arquivo nao encontrado: {fp}")

        # Leitura e preparo
        df_a = load_file(INPUT_FILES[0])
        df_b = load_file(INPUT_FILES[1])

        log_data["estatisticas_entrada"][os.path.basename(INPUT_FILES[0])] = {
            "linhas": len(df_a), "colunas": list(df_a.columns)
        }
        log_data["estatisticas_entrada"][os.path.basename(INPUT_FILES[1])] = {
            "linhas": len(df_b), "colunas": list(df_b.columns)
        }

        # Merge outer pela chave normalizada
        merged = pd.merge(
            df_a, df_b,
            on="chave_norm",
            how="outer",
            suffixes=("_a", "_b"),
            indicator=True,
        )

        # Coluna de valor (pode não existir se ambos os arquivos não tiverem)
        has_valor_a = "valor_a" in merged.columns
        has_valor_b = "valor_b" in merged.columns
        has_valor   = "valor" in merged.columns  # sem sufixo (coluna idêntica nos dois)

        def get_valor(row, side):
            """Pega o valor de um lado do merge com fallback seguro."""
            col_sided  = f"valor_{side}"
            col_direct = "valor"
            if col_sided in row.index and pd.notna(row[col_sided]):
                return row[col_sided]
            if col_direct in row.index and pd.notna(row[col_direct]):
                return row[col_direct]
            return np.nan

        # Classifica cada linha
        def classify(row):
            m = row["_merge"]
            if m == "left_only":
                return "Apenas em A"
            if m == "right_only":
                return "Apenas em B"
            # both — verifica divergência de valor
            va = get_valor(row, "a") if has_valor_a else (row.get("valor") if has_valor else np.nan)
            vb = get_valor(row, "b") if has_valor_b else (row.get("valor") if has_valor else np.nan)
            if pd.isna(va) or pd.isna(vb):
                return "Divergencias"  # valor ausente em um dos lados
            if np.isclose(va, vb, atol=0.01):
                return "Conciliados"
            return "Divergencias"

        merged["status"] = merged.apply(classify, axis=1)

        # Diferença de valor (segura)
        if has_valor_a and has_valor_b:
            merged["diferenca_valor"] = (
                merged["valor_a"].fillna(0) - merged["valor_b"].fillna(0)
            )

        # Separa abas
        conciliados   = merged[merged["status"] == "Conciliados"]
        apenas_a      = merged[merged["status"] == "Apenas em A"]
        apenas_b      = merged[merged["status"] == "Apenas em B"]
        divergencias  = merged[merged["status"] == "Divergencias"]

        # Exporta Excel
        with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
            conciliados.to_excel(writer,  sheet_name="Conciliados",   index=False)
            apenas_a.to_excel(writer,     sheet_name="Apenas em A",   index=False)
            apenas_b.to_excel(writer,     sheet_name="Apenas em B",   index=False)
            divergencias.to_excel(writer, sheet_name="Divergencias",  index=False)

        log_data["status_execucao"] = "SUCESSO"
        log_data["estatisticas_conciliacao"] = {
            "conciliados":  len(conciliados),
            "apenas_em_a":  len(apenas_a),
            "apenas_em_b":  len(apenas_b),
            "divergencias": len(divergencias),
            "total":        len(merged),
        }

    except Exception as e:
        import traceback
        log_data["status_execucao"] = "FALHA"
        log_data["erros"].append({
            "tipo": type(e).__name__,
            "mensagem": str(e),
            "traceback": traceback.format_exc(),
        })
        raise  # Relança para que o executor detecte exit code != 0

    finally:
        log_data["timestamp_fim"] = datetime.now().isoformat()
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=4, ensure_ascii=False)


if __name__ == "__main__":
    main()
'''

# Atualiza o banco
conn = sqlite3.connect("database/concilia.db")
conn.execute(
    "UPDATE workflows SET code = ?, version = version + 1, updated_at = datetime('now') WHERE id = 1",
    (FIXED_CODE,)
)
conn.commit()

# Verifica
row = conn.execute("SELECT version, updated_at FROM workflows WHERE id=1").fetchone()
print(f"Workflow ID=1 atualizado: versão={row[0]}, updated_at={row[1]}")
conn.close()
