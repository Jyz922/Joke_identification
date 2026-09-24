"""LLM Provider abstraction and API key compatibility layer.

Supports major LLM providers:
- Google (Gemini): GEMINI_API_KEY, GOOGLE_API_KEY
- Anthropic (Claude): ANTHROPIC_API_KEY
- OpenAI: OPENAI_API_KEY
- DeepSeek: DEEPSEEK_API_KEY
- Groq: GROQ_API_KEY
- Mistral AI: MISTRAL_API_KEY
- Alibaba DashScope (Qwen): DASHSCOPE_API_KEY, QWEN_API_KEY
- Moonshot AI (Kimi): MOONSHOT_API_KEY, KIMI_API_KEY
- Zhipu AI (GLM): ZHIPUAI_API_KEY, GLM_API_KEY
- SiliconFlow: SILICONFLOW_API_KEY
- OpenAI-compatible / Local / Custom: OPENAI_API_KEY, LLM_API_KEY with custom base_url
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Literal

_LOG = logging.getLogger(__name__)

BackendType = Literal[
    "auto",
    "gemini",
    "anthropic",
    "openai",
    "deepseek",
    "groq",
    "mistral",
    "dashscope",
    "moonshot",
    "zhipu",
    "siliconflow",
    "compatible",
]


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    env_vars: tuple[str, ...]
    default_base_url: str | None
    default_model_l4: str
    default_model_l5: str
    sdk_family: Literal["gemini", "anthropic", "openai"]


PROVIDERS: dict[str, ProviderSpec] = {
    "gemini": ProviderSpec(
        name="gemini",
        env_vars=("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        default_base_url=None,
        default_model_l4="gemini-3.6-flash",
        default_model_l5="gemini-3.6-flash",
        sdk_family="gemini",
    ),
    "anthropic": ProviderSpec(
        name="anthropic",
        env_vars=("ANTHROPIC_API_KEY",),
        default_base_url=None,
        default_model_l4="claude-sonnet-5",
        default_model_l5="claude-sonnet-5",
        sdk_family="anthropic",
    ),
    "openai": ProviderSpec(
        name="openai",
        env_vars=("OPENAI_API_KEY",),
        default_base_url=None,
        default_model_l4="gpt-4o-mini",
        default_model_l5="gpt-4o-mini",
        sdk_family="openai",
    ),
    "deepseek": ProviderSpec(
        name="deepseek",
        env_vars=("DEEPSEEK_API_KEY",),
        default_base_url="https://api.deepseek.com",
        default_model_l4="deepseek-chat",
        default_model_l5="deepseek-chat",
        sdk_family="openai",
    ),
    "groq": ProviderSpec(
        name="groq",
        env_vars=("GROQ_API_KEY",),
        default_base_url="https://api.groq.com/openai/v1",
        default_model_l4="llama-3.3-70b-versatile",
        default_model_l5="llama-3.3-70b-versatile",
        sdk_family="openai",
    ),
    "mistral": ProviderSpec(
        name="mistral",
        env_vars=("MISTRAL_API_KEY",),
        default_base_url="https://api.mistral.ai/v1",
        default_model_l4="mistral-small-latest",
        default_model_l5="mistral-small-latest",
        sdk_family="openai",
    ),
    "dashscope": ProviderSpec(
        name="dashscope",
        env_vars=("DASHSCOPE_API_KEY", "QWEN_API_KEY"),
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model_l4="qwen-plus",
        default_model_l5="qwen-plus",
        sdk_family="openai",
    ),
    "moonshot": ProviderSpec(
        name="moonshot",
        env_vars=("MOONSHOT_API_KEY", "KIMI_API_KEY"),
        default_base_url="https://api.moonshot.cn/v1",
        default_model_l4="moonshot-v1-8k",
        default_model_l5="moonshot-v1-8k",
        sdk_family="openai",
    ),
    "zhipu": ProviderSpec(
        name="zhipu",
        env_vars=("ZHIPUAI_API_KEY", "GLM_API_KEY"),
        default_base_url="https://open.bigmodel.cn/api/paas/v4/",
        default_model_l4="glm-4-flash",
        default_model_l5="glm-4-flash",
        sdk_family="openai",
    ),
    "siliconflow": ProviderSpec(
        name="siliconflow",
        env_vars=("SILICONFLOW_API_KEY",),
        default_base_url="https://api.siliconflow.cn/v1",
        default_model_l4="deepseek-ai/DeepSeek-V3",
        default_model_l5="deepseek-ai/DeepSeek-V3",
        sdk_family="openai",
    ),
    "compatible": ProviderSpec(
        name="compatible",
        env_vars=("OPENAI_API_KEY", "LLM_API_KEY"),
        default_base_url=None,
        default_model_l4="gpt-4o-mini",
        default_model_l5="gpt-4o-mini",
        sdk_family="openai",
    ),
}

_ALIASES: dict[str, str] = {
    "qwen": "dashscope",
    "kimi": "moonshot",
    "glm": "zhipu",
    "zhipuai": "zhipu",
    "claude": "anthropic",
    "google": "gemini",
    "custom": "compatible",
}

# Detection order when backend == "auto"
_AUTO_DETECTION_ORDER: tuple[str, ...] = (
    "gemini",
    "openai",
    "deepseek",
    "anthropic",
    "groq",
    "mistral",
    "dashscope",
    "moonshot",
    "zhipu",
    "siliconflow",
)


def normalize_backend_name(backend: str) -> str:
    """Normalize aliases (e.g. 'qwen' -> 'dashscope', 'kimi' -> 'moonshot')."""
    key = backend.lower().strip()
    return _ALIASES.get(key, key)


def resolve_backend(backend: str, settings: Any = None) -> str:
    """Resolve backend name, performing auto-detection if backend == 'auto'."""
    norm = normalize_backend_name(backend)
    if norm != "auto":
        return norm

    # Auto-detect from settings or environment variables
    for name in _AUTO_DETECTION_ORDER:
        spec = PROVIDERS[name]
        for var in spec.env_vars:
            if settings and getattr(settings, var, None):
                return name
            if os.environ.get(var):
                return name

    # Fallback default
    return "gemini"


def resolve_api_key_name(backend: str) -> str:
    """Return primary environment variable name for a backend."""
    norm = normalize_backend_name(backend)
    if norm in PROVIDERS:
        return PROVIDERS[norm].env_vars[0]
    return f"{norm.upper()}_API_KEY"


def resolve_api_key(backend: str, settings: Any = None) -> tuple[str | None, str]:
    """Resolve API key value and the associated env var name.

    Returns (api_key_value, env_var_name).
    """
    norm = resolve_backend(backend, settings)
    primary_name = resolve_api_key_name(norm)

    if norm not in PROVIDERS:
        # Generic fallback
        val = os.environ.get(primary_name) or os.environ.get("LLM_API_KEY")
        return val, primary_name

    spec = PROVIDERS[norm]

    # 1. Check settings attributes
    if settings:
        for var in spec.env_vars:
            val = getattr(settings, var, None)
            if val:
                return val, var

    # 2. Check environment variables
    for var in spec.env_vars:
        val = os.environ.get(var)
        if val:
            return val, var

    # 3. Check generic fallback env vars
    generic = os.environ.get("LLM_API_KEY") or os.environ.get("DOUBLETAKE_API_KEY")
    if generic:
        return generic, "LLM_API_KEY"

    return None, primary_name


def resolve_base_url(backend: str, settings: Any = None) -> str | None:
    """Resolve base URL for OpenAI-compatible providers."""
    norm = resolve_backend(backend, settings)
    spec = PROVIDERS.get(norm)

    # Specific settings / env overrides
    if norm == "deepseek":
        url = getattr(settings, "DEEPSEEK_BASE_URL", None) or os.environ.get("DEEPSEEK_BASE_URL")
        if url:
            return url
    elif norm in ("openai", "compatible"):
        url = getattr(settings, "OPENAI_BASE_URL", None) or os.environ.get("OPENAI_BASE_URL") or os.environ.get("LLM_BASE_URL")
        if url:
            return url

    # Generic env var override: <BACKEND>_BASE_URL
    override_env = os.environ.get(f"{norm.upper()}_BASE_URL")
    if override_env:
        return override_env

    return spec.default_base_url if spec else None


def resolve_model(backend: str, layer: str, settings: Any) -> str:
    """Resolve default model for a given layer ('L4' or 'L5') and backend."""
    norm = resolve_backend(backend, settings)

    # 1. Check explicit per-layer override (e.g. settings.L4_MODEL or settings.L5_MODEL)
    custom_model = getattr(settings, f"{layer.upper()}_MODEL", None)
    if custom_model:
        return custom_model

    # 2. Check backend-specific settings attribute
    attr_name = f"{layer.upper()}_MODEL_{norm.upper()}"
    val = getattr(settings, attr_name, None)
    if val:
        return val

    # 3. Provider default
    spec = PROVIDERS.get(norm)
    if spec:
        return spec.default_model_l4 if layer.upper() in ("L4", "L6", "L7", "L8") else spec.default_model_l5

    return "gpt-4o-mini"


def create_client(
    backend: str,
    settings: Any = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> Any:
    """Instantiate and return the appropriate LLM client."""
    norm = resolve_backend(backend, settings)
    spec = PROVIDERS.get(norm)

    if api_key is None:
        api_key, key_name = resolve_api_key(norm, settings)
        if not api_key:
            raise ValueError(f"{key_name} not set")

    if base_url is None:
        base_url = resolve_base_url(norm, settings)

    if spec and spec.sdk_family == "gemini":
        import google.genai as genai
        return genai.Client(api_key=api_key)

    if spec and spec.sdk_family == "anthropic":
        import anthropic
        return anthropic.Anthropic(api_key=api_key)

    # Default: OpenAI SDK (works for OpenAI, DeepSeek, Groq, Mistral, DashScope, Moonshot, Zhipu, etc.)
    import openai
    kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return openai.OpenAI(**kwargs)


def _extract_json(raw: str) -> dict[str, Any]:
    """Robustly extract JSON dictionary from raw model text."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def call_openai_compatible(
    client: Any,
    model: str,
    prompt_text: str,
    *,
    max_output_tokens: int = 4096,
    temperature: float = 0.0,
    required_keys: frozenset[str] | None = None,
    retry_suffix: str = "\n\nRespond with valid JSON only matching the schema.",
    validate_fn: Callable[[dict[str, Any], int], None] | None = None,
) -> tuple[dict[str, Any] | None, int, bool]:
    """Call an OpenAI-compatible model with retry on rate-limits, 5xx, or parse failures.

    Returns: (parsed_json_dict, retries_count, fallback_used).
    """
    total_retries = 0
    delays = (2, 4, 8)

    # Try 2 prompt attempts (initial + retry with retry_suffix)
    for attempt in range(2):
        suffix = "" if attempt == 0 else retry_suffix
        messages = [{"role": "user", "content": prompt_text + suffix}]

        # Try API call with backoff on transient errors
        raw_text = ""
        for backoff_idx in range(len(delays) + 1):
            if backoff_idx > 0:
                time.sleep(delays[backoff_idx - 1])
                total_retries += 1
            try:
                # Try with json_object response format
                try:
                    resp = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_output_tokens,
                        response_format={"type": "json_object"},
                    )
                except Exception as fmt_err:
                    # Some endpoints (or models) reject response_format={"type": "json_object"}
                    err_msg = str(fmt_err).lower()
                    if "response_format" in err_msg or "unsupported" in err_msg or "json_object" in err_msg:
                        resp = client.chat.completions.create(
                            model=model,
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_output_tokens,
                        )
                    else:
                        raise

                raw_text = getattr(resp.choices[0].message, "content", "") or ""
                break
            except Exception as e:
                err_str = str(e).lower()
                is_transient = "429" in err_str or "500" in err_str or "502" in err_str or "503" in err_str or "rate limit" in err_str
                if is_transient and backoff_idx < len(delays):
                    continue
                # If exhausted or non-transient, re-raise or return None
                if backoff_idx == len(delays):
                    _LOG.warning("OpenAI-compatible call exhausted retries: %s", e)
                    return None, total_retries, False
                raise

        try:
            parsed = _extract_json(raw_text)
            if validate_fn is not None:
                validate_fn(parsed, attempt)
            elif required_keys:
                missing = set(required_keys) - set(parsed.keys())
                if missing:
                    raise ValueError(f"Missing required keys: {sorted(missing)}")
            return parsed, total_retries, False
        except (json.JSONDecodeError, ValueError, IndexError) as parse_err:
            if attempt == 1:
                _LOG.warning("Failed to parse JSON on retry: %s", parse_err)
                return None, total_retries, False

    return None, total_retries, False
