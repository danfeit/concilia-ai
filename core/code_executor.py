"""
core/code_executor.py — Execução isolada do código Python gerado via subprocess.
"""

from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def execute_code(
    code: str,
    input_paths: list[str],
    output_dir: str,
    timeout_seconds: int = 300,
    log_dir: str = "logs",
    output_extension: str = "xlsx",
) -> dict:
    """
    Executa o código Python gerado em subprocess isolado.
    Retorna dict com: status, duration, output_path, log_path, stdout, stderr, error.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = str(Path(log_dir) / f"exec_{timestamp}.log")
    output_path = str(Path(output_dir) / f"resultado_{timestamp}.{output_extension}")

    # Injeta os caminhos no topo do script
    preamble = (
        f"# === VARIÁVEIS INJETADAS PELO EXECUTOR ===\n"
        f"INPUT_FILES = {json.dumps(input_paths)}\n"
        f"OUTPUT_PATH = {json.dumps(output_path)}\n"
        f"LOG_PATH    = {json.dumps(log_path)}\n"
        f"# ==========================================\n\n"
    )
    full_code = preamble + code

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                     delete=False, encoding="utf-8") as tmp:
        tmp.write(full_code)
        tmp_path = tmp.name

    start = time.time()
    result = {
        "status": "error",
        "duration_seconds": 0.0,
        "output_path": None,
        "log_path": log_path,
        "stdout": "",
        "stderr": "",
        "error": None,
    }

    try:
        proc = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        result["stdout"] = proc.stdout
        result["stderr"] = proc.stderr

        if proc.returncode == 0:
            if Path(output_path).exists():
                result["status"] = "success"
                result["output_path"] = output_path
            else:
                result["status"] = "error"
                result["error"] = "Arquivo de saída não foi gerado pelo script."
        else:
            result["status"] = "error"
            result["error"] = proc.stderr[-2000:] if proc.stderr else "Erro desconhecido."

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["error"] = f"Execução excedeu o timeout de {timeout_seconds}s."
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    finally:
        result["duration_seconds"] = round(time.time() - start, 2)
        os.unlink(tmp_path)

        # Salva log estruturado
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": timestamp,
                "status": result["status"],
                "duration_seconds": result["duration_seconds"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "error": result["error"],
                "input_files": input_paths,
                "output_path": result["output_path"],
            }, f, indent=2, ensure_ascii=False)

    return result


def run_preview(code: str, input_paths: list[str], output_dir: str = "outputs", output_extension: str = "xlsx") -> dict:
    """Execução rápida sobre amostra para prévia do resultado."""
    return execute_code(code, input_paths, output_dir, timeout_seconds=60, output_extension=output_extension)
