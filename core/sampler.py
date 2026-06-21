"""
core/sampler.py — Amostragem reprodutível de DataFrames (seed fixo).
Para arquivos legados (TXT/PDF), amostra linhas de texto bruto.
"""

import math
import pandas as pd


FIXED_SEED = 42


def sample_dataframe(df: pd.DataFrame, pct: float = 0.20) -> pd.DataFrame:
    """
    Retorna amostra aleatória de pct% do DataFrame.
    Seed fixo (42) para reprodutibilidade.
    Garante mínimo de 50 linhas ou todo o DF se menor.
    """
    n = max(min(int(len(df) * pct), len(df)), min(50, len(df)))
    return df.sample(n=n, random_state=FIXED_SEED) if n < len(df) else df.copy()


def sample_text(raw_text: str, pct: float = 0.20, max_chars: int = 8000) -> str:
    """
    Para arquivos legados (TXT/PDF), extrai uma amostra representativa:
    - Primeiras 30 linhas (cabeçalho/estrutura)
    - Amostra aleatória do meio
    - Últimas 10 linhas (rodapé)
    Limita ao max_chars para controle de tokens.
    """
    lines = raw_text.splitlines()
    total = len(lines)

    if total <= 80:
        sample = "\n".join(lines)
    else:
        head = lines[:30]
        tail = lines[-10:]
        mid_count = max(10, int(total * pct))
        mid_start = 30
        mid_end = total - 10
        step = max(1, (mid_end - mid_start) // mid_count)
        mid = lines[mid_start:mid_end:step][:mid_count]
        sample = "\n".join(head + ["[... AMOSTRA DO MEIO ...]"] + mid + ["[... FIM ...]"] + tail)

    return sample[:max_chars]


def describe_dataframe(df: pd.DataFrame) -> dict:
    """Gera um resumo compacto do DataFrame para envio ao agente."""
    desc = {
        "total_rows": len(df),
        "columns": [],
    }
    for col in df.columns:
        col_info = {
            "name": col,
            "dtype": str(df[col].dtype),
            "null_pct": round(df[col].isna().mean() * 100, 1),
            "unique_count": int(df[col].nunique()),
        }
        if df[col].dtype in ("object", "string"):
            sample_vals = df[col].dropna().head(5).tolist()
            col_info["sample_values"] = [str(v) for v in sample_vals]
        elif pd.api.types.is_numeric_dtype(df[col]):
            col_info["min"] = float(df[col].min()) if not df[col].isna().all() else None
            col_info["max"] = float(df[col].max()) if not df[col].isna().all() else None
        desc["columns"].append(col_info)
    return desc
