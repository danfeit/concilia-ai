"""
agents/base_agent.py — Interface unificada multi-provider (Anthropic/Google/OpenAI).
Inclui retry automático com backoff exponencial (3 tentativas).
"""

from __future__ import annotations
import time
from typing import Any


def call_llm(provider: str, model: str, api_key: str,
             system_prompt: str, user_message: str,
             temperature: float = 0.2, max_tokens: int = 8000) -> str:
    """
    Chama o LLM do provider especificado.
    Retorna o texto da resposta ou lança exceção após 3 tentativas.
    """
    last_error = None
    for attempt in range(3):
        try:
            if provider == "anthropic":
                return _call_anthropic(model, api_key, system_prompt, user_message,
                                       temperature, max_tokens)
            elif provider == "google":
                return _call_google(model, api_key, system_prompt, user_message,
                                    temperature, max_tokens)
            elif provider == "openai":
                return _call_openai(model, api_key, system_prompt, user_message,
                                    temperature, max_tokens)
            else:
                raise ValueError(f"Provider desconhecido: {provider}")
        except Exception as e:
            last_error = e
            if attempt < 2:
                wait = 2 ** attempt  # 1s, 2s
                time.sleep(wait)
    raise RuntimeError(f"Falha após 3 tentativas: {last_error}")


def _call_anthropic(model: str, api_key: str, system: str, user: str,
                    temperature: float, max_tokens: int) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text


def _call_google(model: str, api_key: str, system: str, user: str,
                 temperature: float, max_tokens: int) -> str:
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    gen_model = genai.GenerativeModel(
        model_name=model,
        system_instruction=system,
        generation_config=genai.GenerationConfig(
            temperature=temperature, max_output_tokens=max_tokens
        ),
    )
    response = gen_model.generate_content(user)
    try:
        return response.text
    except Exception as e:
        try:
            if response.candidates:
                candidate = response.candidates[0]
                finish_reason = getattr(candidate, "finish_reason", None)
                # 3 correspond a SAFETY (bloqueio de segurança)
                if finish_reason == 3:
                    return "❌ Erro: A resposta foi bloqueada pelos filtros de segurança (Safety) da API Gemini."
                
                parts = getattr(candidate.content, "parts", [])
                text_parts = [part.text for part in parts if hasattr(part, "text") and part.text]
                if text_parts:
                    return "".join(text_parts)
        except Exception:
            pass
        raise e


def _call_openai(model: str, api_key: str, system: str, user: str,
                 temperature: float, max_tokens: int) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    # Modelos mais novos da OpenAI (o1, o3, gpt-4.1, gpt-5.4-mini, etc.)
    # exigem 'max_completion_tokens' em vez de 'max_tokens'.
    # Alguns modelos de raciocínio (o1, o3) também não suportam 'temperature'.
    _REASONING_PREFIXES = ("o1", "o3", "o4")
    model_lower = model.lower()
    is_reasoning = any(model_lower.startswith(p) for p in _REASONING_PREFIXES)

    try:
        params: dict[str, Any] = dict(
            model=model,
            messages=messages,
            max_completion_tokens=max_tokens,
        )
        # Modelos de raciocínio não suportam temperature
        if not is_reasoning:
            params["temperature"] = temperature
        response = client.chat.completions.create(**params)
        return response.choices[0].message.content
    except Exception as e:
        err_msg = str(e).lower()
        # Se o modelo não suporta max_completion_tokens, tenta com max_tokens
        if "max_completion_tokens" in err_msg and "unsupported" in err_msg:
            response = client.chat.completions.create(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=messages,
            )
            return response.choices[0].message.content
        raise


def test_connection(provider: str, api_key: str, model: str) -> tuple[bool, str]:
    """Faz chamada mínima para testar se a chave é válida."""
    try:
        result = call_llm(provider, model, api_key,
                          system_prompt="You are a helpful assistant.",
                          user_message="Say 'OK' and nothing else.",
                          temperature=0.0, max_tokens=10)
        return True, f"Conectado ✅ — resposta: {result.strip()}"
    except Exception as e:
        return False, f"Erro: {str(e)}"
