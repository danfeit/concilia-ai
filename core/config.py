"""
core/config.py — Gerenciamento do arquivo config.json local.
"""

import json
import os
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config.json"

DEFAULTS = {
    "anthropic_api_key": "",
    "google_api_key": "",
    "openai_api_key": "",
    "agent1_provider": "anthropic",
    "agent1_model": "claude-haiku-4",
    "agent1_temperature": 0.2,
    "agent1_sample_pct": 0.20,
    "agent1_system_instructions": "",
    "agent2_provider": "anthropic",
    "agent2_model": "claude-haiku-4",
    "agent2_temperature": 0.5,
    "agent2_system_instructions": "",
    "agent2_include_next_steps": True,
    "agent2_include_anomalies": True,
    "timeout_minutes": 5,
    "output_dir": "outputs",
    "save_input_copies": False,
    "agent3_provider": "google",
    "agent3_model": "gemini-3.5-flash",
    "agent3_temperature": 0.1,
    "agent3_system_instructions": "Atenção: Ao processar o CSV ou tratar nomes de colunas, sempre use strip() e force conversão para float ou string de forma segura antes do merge. Trate campos numéricos removendo . e ,",
    "agent4_provider": "google",
    "agent4_model": "gemini-3.5-flash",
    "agent4_temperature": 0.2,
    "agent4_system_instructions": "",
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # Preenche defaults para chaves ausentes
            for k, v in DEFAULTS.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
        except Exception:
            pass
    return DEFAULTS.copy()


def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def export_config_without_keys(cfg: dict) -> dict:
    """Remove chaves de API antes de exportar."""
    safe = cfg.copy()
    for k in ("anthropic_api_key", "google_api_key", "openai_api_key"):
        safe[k] = ""
    return safe
