"""
engine/llm.py — LLM abstraction layer
Single entry-point for all LLM calls in the Gurgaon Town Life simulation.

Supports two providers:
  - ollama  (local, free)   — default
  - gemini  (Google Cloud)

The active provider is controlled by ``llm_config`` (a module-level singleton)
and can be switched at runtime without restarting.

Environment variables (loaded from .env on import):
  LLM_PRIMARY      — "ollama" or "gemini"   (default: "ollama")
  OLLAMA_BASE_URL  — Ollama server URL       (default: "http://localhost:11434")
  GEMINI_API_KEY   — required for Gemini provider

Usage
-----
    from engine.llm import call_llm, build_tool_schema, llm_config

    # Optional: switch provider at runtime
    llm_config.set_primary("gemini")

    response = await call_llm("What should I do next?", system="You are an NPC.")
    print(response.text)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

import litellm
from dotenv import load_dotenv

# Load .env from project root (two levels up from this file: engine/ → project/)
load_dotenv()

logger = logging.getLogger(__name__)

_VALID_PROVIDERS = ("ollama", "gemini")


# ---------------------------------------------------------------------------
# LLMConfig — runtime singleton
# ---------------------------------------------------------------------------


class LLMConfig:
    """
    Runtime configuration for LLM provider selection.

    One instance (``llm_config``) is created at module load and seeded from
    environment variables.  Callers may call ``set_primary()`` at any time to
    switch providers without restarting.
    """

    def __init__(self) -> None:
        self._primary: str = "ollama"
        self._models: dict[str, str] = {
            "ollama": "ollama/gemma4:e4b",
            "gemini": "gemini/gemini-2.5-flash",
        }
        self._ollama_base_url: str = "http://localhost:11434"

        # Seed from environment
        env_primary = os.getenv("LLM_PRIMARY", "").strip().lower()
        if env_primary in _VALID_PROVIDERS:
            self._primary = env_primary

        env_base_url = os.getenv("OLLAMA_BASE_URL", "").strip()
        if env_base_url:
            self._ollama_base_url = env_base_url

    # ------------------------------------------------------------------
    # Accessors / mutators
    # ------------------------------------------------------------------

    def set_primary(self, provider: str) -> None:
        """
        Switch the active LLM provider.

        Parameters
        ----------
        provider : str
            Must be one of "ollama" or "gemini".

        Raises
        ------
        ValueError
            If *provider* is not a recognised value.
        """
        if provider not in _VALID_PROVIDERS:
            raise ValueError(
                f"Unknown provider {provider!r}. "
                f"Valid choices: {list(_VALID_PROVIDERS)}"
            )
        self._primary = provider

    def get_primary(self) -> str:
        """Return the name of the currently active provider."""
        return self._primary

    def get_model(self) -> str:
        """Return the litellm model string for the active provider."""
        return self._models[self._primary]

    def get_ollama_base_url(self) -> str:
        """Return the Ollama server base URL."""
        return self._ollama_base_url


# Module-level singleton — all other code imports this object.
llm_config = LLMConfig()


# ---------------------------------------------------------------------------
# LLMResponse — typed return value
# ---------------------------------------------------------------------------


@dataclass
class LLMResponse:
    """
    Structured result from a single LLM call.

    Exactly one of ``text`` or ``tool_name`` / ``tool_args`` will be populated
    depending on whether the model returned plain text or a tool call.
    """

    text: str | None  # plain-text response (no tool call)
    tool_name: str | None  # name of tool invoked (tool-call response)
    tool_args: dict | None  # parsed arguments for the tool call
    provider: str  # "ollama" or "gemini"
    input_tokens: int
    output_tokens: int
    raw: dict = field(repr=False)  # full litellm response dict (for debugging)


# ---------------------------------------------------------------------------
# build_tool_schema() — helper
# ---------------------------------------------------------------------------


def build_tool_schema(
    name: str,
    description: str,
    parameters: dict,
    required: list[str],
) -> dict:
    """
    Build an OpenAI-format tool schema dict.

    Parameters
    ----------
    name : str
        Function name (snake_case recommended).
    description : str
        Short description shown to the model.
    parameters : dict
        JSON Schema ``properties`` dict mapping parameter names to their schemas.
    required : list[str]
        Names of parameters that are required.

    Returns
    -------
    dict
        ``{"type": "function", "function": {...}}`` ready for litellm's
        ``tools`` parameter.
    """
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": parameters,
                "required": required,
            },
        },
    }


# ---------------------------------------------------------------------------
# call_llm() — main entry point
# ---------------------------------------------------------------------------


async def call_llm(
    prompt: str,
    tools: list[dict] | None = None,
    system: str | None = None,
    max_tokens: int = 300,
) -> LLMResponse:
    """
    Send *prompt* to the active LLM provider and return a structured response.

    Parameters
    ----------
    prompt : str
        The user-facing prompt text.
    tools : list[dict] | None
        Optional list of OpenAI-format tool schemas (use ``build_tool_schema``
        to build them).  When provided the model may elect to call one.
    system : str | None
        Optional system message prepended before the user message.
    max_tokens : int
        Maximum number of tokens to generate.

    Returns
    -------
    LLMResponse
        Parsed response with text or tool_call fields populated.

    Raises
    ------
    Exception
        Any exception from litellm is logged then re-raised so callers can
        handle retries / fallbacks as appropriate.
    """
    provider = llm_config.get_primary()
    model = llm_config.get_model()

    # Build messages list
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # Keyword arguments for litellm
    kwargs: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }

    if provider == "ollama":
        kwargs["api_base"] = llm_config.get_ollama_base_url()

    if tools:
        kwargs["tools"] = tools

    try:
        response = await litellm.acompletion(**kwargs)
    except Exception as exc:
        logger.error("[LLM] %s call failed: %s", provider, exc)
        raise

    # Parse token counts (default to 0 if missing)
    usage = getattr(response, "usage", None)
    input_tokens: int = getattr(usage, "prompt_tokens", 0) or 0
    output_tokens: int = getattr(usage, "completion_tokens", 0) or 0

    # Parse text vs tool call
    message = response.choices[0].message
    tool_calls = getattr(message, "tool_calls", None)

    text: str | None = None
    tool_name: str | None = None
    tool_args: dict | None = None

    if tool_calls:
        first_call = tool_calls[0]
        tool_name = first_call.function.name
        raw_args = first_call.function.arguments
        # arguments is a JSON string per OpenAI spec
        tool_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
    else:
        text = getattr(message, "content", None)

    # Log one line per call
    logger.info(
        "[LLM] %s | %din %dout | tool=%s",
        provider,
        input_tokens,
        output_tokens,
        tool_name or "text",
    )

    # Serialise the raw response for debugging (litellm objects support __dict__)
    try:
        raw_dict: dict = (
            response.model_dump() if hasattr(response, "model_dump") else dict(response)
        )
    except Exception:
        raw_dict = {}

    return LLMResponse(
        text=text,
        tool_name=tool_name,
        tool_args=tool_args,
        provider=provider,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        raw=raw_dict,
    )
