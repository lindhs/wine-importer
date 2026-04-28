from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
DEFAULT_AI_MODEL = "gpt-4o-mini"


def load_project_env(env_path: str | Path | None = None) -> bool:
    if env_path is not None:
        path = Path(env_path)
    else:
        cwd_path = Path.cwd() / ".env"
        package_path = Path(__file__).resolve().parents[1] / ".env"
        path = cwd_path if cwd_path.exists() else package_path
    if not path.exists():
        return False

    loaded = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        if key not in os.environ:
            os.environ[key] = value
            loaded = True

    return loaded


def resolve_api_key(api_key: str | None = None) -> str | None:
    if api_key:
        return api_key
    if os.getenv("OPENAI_API_KEY"):
        return os.getenv("OPENAI_API_KEY")

    load_project_env()
    return os.getenv("OPENAI_API_KEY")


def _extract_error_message(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        body = exc.read().decode("utf-8", errors="ignore")
        try:
            payload = json.loads(body)
            return payload.get("error", {}).get("message", str(exc))
        except json.JSONDecodeError:
            return body or str(exc)
    if isinstance(exc, urllib.error.URLError):
        return str(exc.reason)
    return str(exc)


def _build_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _request_json(
    url: str,
    *,
    api_key: str,
    payload: dict[str, Any] | None = None,
    method: str = "POST",
    timeout: float = 30.0,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers=_build_headers(api_key),
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _extract_chat_content(response_payload: dict[str, Any]) -> str:
    choices = response_payload.get("choices") or []
    if not choices:
        raise RuntimeError("OpenAI response did not include any choices")

    message = choices[0].get("message") or {}
    content = message.get("content")

    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        if parts:
            return "\n".join(parts).strip()

    raise RuntimeError("OpenAI response did not include text content")


def create_json_completion(
    prompt: str,
    *,
    api_key: str | None = None,
    model: str = DEFAULT_AI_MODEL,
    max_output_tokens: int = 500,
    temperature: float = 0.1,
) -> dict[str, Any]:
    resolved_api_key = resolve_api_key(api_key)
    if not resolved_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "max_completion_tokens": max_output_tokens,
        "temperature": temperature,
    }
    response_payload = _request_json(
        OPENAI_CHAT_COMPLETIONS_URL,
        api_key=resolved_api_key,
        payload=payload,
    )
    content = _extract_chat_content(response_payload)
    return json.loads(content)


def verify_api_connection(api_key: str | None = None) -> tuple[bool, str]:
    resolved_api_key = resolve_api_key(api_key)
    if not resolved_api_key:
        return False, "OPENAI_API_KEY is not configured"

    try:
        _request_json(
            OPENAI_MODELS_URL,
            api_key=resolved_api_key,
            payload=None,
            method="GET",
            timeout=15.0,
        )
        return True, "✓ Connection successful"
    except Exception as exc:
        return False, f"✗ Connection failed: {_extract_error_message(exc)}"
