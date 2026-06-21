"""
core/schema_validator.py — Valida compatibilidade dos arquivos com o schema do workflow.
"""

from __future__ import annotations
import pandas as pd
from core.file_handler import read_file


def validate_files_against_schema(uploaded_files: list[dict], schema_info: dict) -> dict:
    """
    uploaded_files: [{"name": str, "bytes": bytes}]
    schema_info: salvo no workflow (dict com "files": [...])
    Retorna: {"ok": bool, "errors": [...], "warnings": [...], "file_results": [...]}
    """
    errors, warnings, file_results = [], [], []
    expected_files = schema_info.get("files", [])

    if len(uploaded_files) != len(expected_files):
        errors.append(
            f"Número de arquivos incorreto: esperado {len(expected_files)}, recebido {len(uploaded_files)}."
        )

    for i, (uploaded, expected) in enumerate(zip(uploaded_files, expected_files)):
        result = {"index": i, "filename": uploaded["name"], "issues": [], "ok": True}
        df, ftype, meta = read_file(uploaded["bytes"], uploaded["name"])

        if meta.get("is_legacy"):
            result["note"] = "Arquivo legado: validação delegada ao parser gerado."
            file_results.append(result)
            continue

        if df is None:
            result["ok"] = False
            result["issues"].append(f"Erro de leitura: {meta.get('error')}")
            errors.append(f"{uploaded['name']}: erro de leitura.")
            file_results.append(result)
            continue

        expected_cols = expected.get("key_columns", [])
        actual_lower = [c.lower().strip() for c in df.columns]
        missing = [c for c in expected_cols if c.lower().strip() not in actual_lower]

        if missing:
            result["ok"] = False
            msg = f"Colunas chave ausentes: {missing}"
            result["issues"].append(msg)
            errors.append(f"{uploaded['name']}: {msg}")
        else:
            result["note"] = "Todas as colunas chave encontradas ✅"

        if len(df) == 0:
            result["ok"] = False
            issue = "Arquivo vazio (0 linhas)."
            result["issues"].append(issue)
            errors.append(f"{uploaded['name']}: {issue}")

        for col in df.columns:
            if df[col].isna().mean() > 0.5:
                w = f"Coluna '{col}' com mais de 50% de nulos."
                result["issues"].append(f"⚠️ {w}")
                warnings.append(f"{uploaded['name']}: {w}")

        file_results.append(result)

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings, "file_results": file_results}


def check_syntax(code: str) -> tuple[bool, str]:
    import ast
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, f"Erro de sintaxe na linha {e.lineno}: {e.msg}"
