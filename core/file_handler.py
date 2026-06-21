"""
core/file_handler.py — Leitura e detecção de todos os formatos suportados.
Suporta: CSV, XLSX, XLS, JSON, Parquet, TXT (legado), PDF (legado).
"""

import io
import json
import hashlib
from pathlib import Path
from typing import Any

import pandas as pd


def detect_file_type(filename: str) -> str:
    """Retorna o tipo de arquivo baseado na extensão."""
    ext = Path(filename).suffix.lower()
    type_map = {
        ".csv": "csv",
        ".xlsx": "xlsx",
        ".xls": "xls",
        ".json": "json",
        ".parquet": "parquet",
        ".txt": "txt_legacy",
        ".pdf": "pdf_legacy",
    }
    return type_map.get(ext, "unknown")


def read_file(file_bytes: bytes, filename: str) -> tuple[pd.DataFrame | None, str, dict]:
    """
    Lê qualquer arquivo suportado e retorna (DataFrame, tipo, metadata).
    Para TXT/PDF não estruturados, retorna DataFrame=None e o texto bruto em metadata.
    """
    file_type = detect_file_type(filename)
    metadata = {"type": file_type, "filename": filename}

    try:
        if file_type == "csv":
            return _read_csv(file_bytes, metadata)
        elif file_type in ("xlsx", "xls"):
            return _read_excel(file_bytes, metadata)
        elif file_type == "json":
            return _read_json(file_bytes, metadata)
        elif file_type == "parquet":
            return _read_parquet(file_bytes, metadata)
        elif file_type == "txt_legacy":
            return _read_txt_legacy(file_bytes, metadata)
        elif file_type == "pdf_legacy":
            return _read_pdf_legacy(file_bytes, metadata)
        else:
            raise ValueError(f"Formato não suportado: {filename}")
    except Exception as e:
        metadata["error"] = str(e)
        return None, file_type, metadata


def _read_csv(data: bytes, meta: dict) -> tuple:
    """Tenta diferentes encodings e separadores."""
    for encoding in ("utf-8", "latin-1", "cp1252"):
        for sep in (",", ";", "\t", "|"):
            try:
                df = pd.read_csv(io.BytesIO(data), encoding=encoding, sep=sep, low_memory=False)
                if df.shape[1] > 1:
                    meta.update({"encoding": encoding, "separator": sep,
                                 "rows": len(df), "cols": df.shape[1],
                                 "columns": list(df.columns)})
                    return df, "csv", meta
            except Exception:
                continue
    raise ValueError("Não foi possível ler o CSV com os encodings/separadores testados.")


def _read_excel(data: bytes, meta: dict) -> tuple:
    df = pd.read_excel(io.BytesIO(data), engine="openpyxl")
    meta.update({"rows": len(df), "cols": df.shape[1], "columns": list(df.columns)})
    return df, "excel", meta


def _read_json(data: bytes, meta: dict) -> tuple:
    text = data.decode("utf-8", errors="replace")
    parsed = json.loads(text)
    if isinstance(parsed, list):
        df = pd.DataFrame(parsed)
    elif isinstance(parsed, dict):
        # Tenta normalizar dicionário aninhado
        try:
            df = pd.json_normalize(parsed)
        except Exception:
            df = pd.DataFrame([parsed])
    else:
        raise ValueError("JSON não é uma lista ou objeto suportado.")
    meta.update({"rows": len(df), "cols": df.shape[1], "columns": list(df.columns)})
    return df, "json", meta


def _read_parquet(data: bytes, meta: dict) -> tuple:
    df = pd.read_parquet(io.BytesIO(data))
    meta.update({"rows": len(df), "cols": df.shape[1], "columns": list(df.columns)})
    return df, "parquet", meta


def _read_txt_legacy(data: bytes, meta: dict) -> tuple:
    """
    Extrai o conteúdo bruto de um TXT de sistema legado.
    Retorna DataFrame=None; o texto fica em meta['raw_text'] para o Agente 1 analisar.
    """
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            text = data.decode(encoding)
            lines = text.splitlines()
            meta.update({
                "raw_text": text,
                "line_count": len(lines),
                "encoding_detected": encoding,
                "preview_lines": lines[:30],
                "is_legacy": True,
            })
            return None, "txt_legacy", meta
        except Exception:
            continue
    raise ValueError("Não foi possível decodificar o arquivo TXT.")


def _read_pdf_legacy(data: bytes, meta: dict) -> tuple:
    """
    Extrai texto de PDF usando pdfplumber; fallback para PyMuPDF.
    Retorna DataFrame=None; o texto fica em meta['raw_text'].
    """
    text = ""
    pages_text = []
    page_count = 0

    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                pt = page.extract_text() or ""
                pages_text.append(pt)
            text = "\n".join(pages_text)
    except Exception:
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=data, filetype="pdf")
            page_count = len(doc)
            for page in doc:
                pt = page.get_text()
                pages_text.append(pt)
            text = "\n".join(pages_text)
        except Exception as e:
            raise ValueError(f"Não foi possível extrair texto do PDF: {e}")

    lines = text.splitlines()
    meta.update({
        "raw_text": text,
        "page_count": page_count,
        "line_count": len(lines),
        "preview_lines": lines[:30],
        "is_legacy": True,
    })
    return None, "pdf_legacy", meta


def compute_md5(file_bytes: bytes) -> str:
    return hashlib.md5(file_bytes).hexdigest()


def get_file_info(df: pd.DataFrame | None, meta: dict, file_bytes: bytes) -> dict:
    """Retorna um dicionário de metadados consolidados para exibição."""
    size_kb = round(len(file_bytes) / 1024, 2)
    md5 = compute_md5(file_bytes)
    info = {
        "filename": meta.get("filename", "?"),
        "type": meta.get("type", "?"),
        "size_kb": size_kb,
        "md5": md5,
        "is_legacy": meta.get("is_legacy", False),
    }
    if df is not None:
        info.update({
            "rows": len(df),
            "cols": df.shape[1],
            "columns": list(df.columns),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        })
    else:
        info.update({
            "rows": None,
            "cols": None,
            "line_count": meta.get("line_count"),
            "page_count": meta.get("page_count"),
            "preview_lines": meta.get("preview_lines", []),
        })
    return info
