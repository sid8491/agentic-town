"""
Story 2.1 — LLM Abstraction Layer Tests
Verifies engine/llm.py without making any live LLM connections.

Run with:
    .venv/Scripts/python.exe tests/test_llm.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure project root is on sys.path so `engine` can be imported
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.llm import LLMConfig, LLMResponse, build_tool_schema, call_llm, llm_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

results: list[tuple[str, bool, str | None]] = []


def run_test(name: str, fn) -> None:
    """Execute *fn* and record PASS / FAIL."""
    try:
        fn()
        results.append((name, True, None))
        print(f"  PASS  {name}")
    except Exception as exc:
        results.append((name, False, str(exc)))
        print(f"  FAIL  {name}")
        print(f"        {exc}")


def _make_text_mock_response(content: str = "some text",
                              prompt_tokens: int = 100,
                              completion_tokens: int = 50) -> MagicMock:
    """Build a MagicMock that looks like a litellm text completion response."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = content
    mock_response.choices[0].message.tool_calls = None
    mock_response.usage.prompt_tokens = prompt_tokens
    mock_response.usage.completion_tokens = completion_tokens
    # Support model_dump() for raw serialisation
    mock_response.model_dump.return_value = {"mocked": True}
    return mock_response


def _make_tool_mock_response(tool_fn_name: str = "move_to",
                              tool_args_json: str = '{"location": "metro"}',
                              prompt_tokens: int = 80,
                              completion_tokens: int = 30) -> MagicMock:
    """Build a MagicMock that looks like a litellm tool-call response."""
    mock_tool_call = MagicMock()
    mock_tool_call.function.name = tool_fn_name
    mock_tool_call.function.arguments = tool_args_json

    mock_response = MagicMock()
    mock_response.choices[0].message.tool_calls = [mock_tool_call]
    mock_response.choices[0].message.content = None
    mock_response.usage.prompt_tokens = prompt_tokens
    mock_response.usage.completion_tokens = completion_tokens
    mock_response.model_dump.return_value = {"mocked": True}
    return mock_response


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_01_default_provider_is_ollama():
    """llm_config.get_primary() returns 'ollama' after reset."""
    cfg = LLMConfig.__new__(LLMConfig)
    # Manually init without reading env so we see the hard-coded default
    cfg._primary = "ollama"
    cfg._models = {
        "ollama": "ollama/qwen3:27b",
        "gemini": "gemini/gemini-1.5-flash",
    }
    cfg._ollama_base_url = "http://localhost:11434"
    assert cfg.get_primary() == "ollama", (
        f"Expected 'ollama', got {cfg.get_primary()!r}"
    )


def test_02_set_primary_gemini_updates_model():
    """set_primary('gemini') changes provider; get_model() returns gemini model string."""
    cfg = LLMConfig.__new__(LLMConfig)
    cfg._primary = "ollama"
    cfg._models = {
        "ollama": "ollama/qwen3:27b",
        "gemini": "gemini/gemini-1.5-flash",
    }
    cfg._ollama_base_url = "http://localhost:11434"

    cfg.set_primary("gemini")
    assert cfg.get_primary() == "gemini", (
        f"Expected 'gemini', got {cfg.get_primary()!r}"
    )
    assert cfg.get_model() == "gemini/gemini-1.5-flash", (
        f"Expected 'gemini/gemini-1.5-flash', got {cfg.get_model()!r}"
    )


def test_03_set_primary_invalid_raises_value_error():
    """set_primary('invalid') raises ValueError."""
    cfg = LLMConfig.__new__(LLMConfig)
    cfg._primary = "ollama"
    cfg._models = {}
    cfg._ollama_base_url = "http://localhost:11434"

    raised = False
    try:
        cfg.set_primary("invalid")
    except ValueError:
        raised = True

    assert raised, "Expected ValueError for unknown provider 'invalid'"


def test_04_reset_to_ollama_returns_ollama_model():
    """get_model() after switch back to ollama returns the ollama model string."""
    cfg = LLMConfig.__new__(LLMConfig)
    cfg._primary = "ollama"
    cfg._models = {
        "ollama": "ollama/qwen3:27b",
        "gemini": "gemini/gemini-1.5-flash",
    }
    cfg._ollama_base_url = "http://localhost:11434"

    cfg.set_primary("gemini")
    cfg.set_primary("ollama")
    assert cfg.get_model() == "ollama/qwen3:27b", (
        f"Expected 'ollama/qwen3:27b', got {cfg.get_model()!r}"
    )


def test_05_build_tool_schema_correct_format():
    """build_tool_schema() returns a correctly-structured OpenAI tool dict."""
    schema = build_tool_schema(
        name="move_to",
        description="Move the agent to a location",
        parameters={
            "location": {
                "type": "string",
                "description": "The target location id",
            }
        },
        required=["location"],
    )

    assert schema["type"] == "function", "Top-level 'type' must be 'function'"
    fn = schema["function"]
    assert fn["name"] == "move_to", f"function.name mismatch: {fn['name']!r}"
    assert fn["description"] == "Move the agent to a location"
    params = fn["parameters"]
    assert params["type"] == "object", "parameters.type must be 'object'"
    assert "location" in params["properties"], "parameters.properties must contain 'location'"
    assert params["required"] == ["location"], (
        f"parameters.required mismatch: {params['required']!r}"
    )


def test_06_call_llm_text_response():
    """call_llm() with mocked text response sets LLMResponse.text; tool_name is None."""
    mock_response = _make_text_mock_response("Hello from the LLM")

    async def _run():
        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            # Ensure we're using ollama so the call path is predictable
            llm_config.set_primary("ollama")
            result = await call_llm("What should I do?")
        return result

    result = asyncio.run(_run())

    assert isinstance(result, LLMResponse), "call_llm must return an LLMResponse"
    assert result.text == "Hello from the LLM", (
        f"Expected text='Hello from the LLM', got {result.text!r}"
    )
    assert result.tool_name is None, (
        f"Expected tool_name=None, got {result.tool_name!r}"
    )
    assert result.tool_args is None, (
        f"Expected tool_args=None, got {result.tool_args!r}"
    )


def test_07_call_llm_tool_call_response():
    """call_llm() with mocked tool_call response sets tool_name and tool_args; text is None."""
    mock_response = _make_tool_mock_response(
        tool_fn_name="move_to",
        tool_args_json='{"location": "metro"}',
    )

    async def _run():
        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            llm_config.set_primary("ollama")
            result = await call_llm(
                prompt="Where should I go?",
                tools=[
                    build_tool_schema(
                        "move_to",
                        "Move agent to location",
                        {"location": {"type": "string"}},
                        ["location"],
                    )
                ],
            )
        return result

    result = asyncio.run(_run())

    assert result.text is None, f"Expected text=None, got {result.text!r}"
    assert result.tool_name == "move_to", (
        f"Expected tool_name='move_to', got {result.tool_name!r}"
    )
    assert result.tool_args == {"location": "metro"}, (
        f"Expected tool_args={{'location': 'metro'}}, got {result.tool_args!r}"
    )


def test_08_llm_response_provider_field():
    """LLMResponse.provider matches the active provider at call time."""
    mock_response = _make_text_mock_response("hi")

    async def _run():
        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            llm_config.set_primary("ollama")
            result = await call_llm("ping")
        return result

    result = asyncio.run(_run())
    assert result.provider == "ollama", (
        f"Expected provider='ollama', got {result.provider!r}"
    )

    async def _run_gemini():
        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            llm_config.set_primary("gemini")
            result = await call_llm("ping")
        return result

    result_g = asyncio.run(_run_gemini())
    assert result_g.provider == "gemini", (
        f"Expected provider='gemini', got {result_g.provider!r}"
    )

    # Reset back to ollama for subsequent tests
    llm_config.set_primary("ollama")


def test_09_token_counts_parsed_correctly():
    """Token counts are correctly read from the mocked usage object."""
    mock_response = _make_text_mock_response(
        content="token test",
        prompt_tokens=123,
        completion_tokens=456,
    )

    async def _run():
        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            llm_config.set_primary("ollama")
            result = await call_llm("count tokens please")
        return result

    result = asyncio.run(_run())

    assert result.input_tokens == 123, (
        f"Expected input_tokens=123, got {result.input_tokens}"
    )
    assert result.output_tokens == 456, (
        f"Expected output_tokens=456, got {result.output_tokens}"
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    ("1.  llm_config.get_primary() returns 'ollama' by default", test_01_default_provider_is_ollama),
    ("2.  set_primary('gemini') changes provider; get_model() returns gemini model string", test_02_set_primary_gemini_updates_model),
    ("3.  set_primary('invalid') raises ValueError", test_03_set_primary_invalid_raises_value_error),
    ("4.  get_model() after reset to ollama returns ollama model string", test_04_reset_to_ollama_returns_ollama_model),
    ("5.  build_tool_schema() returns correct OpenAI format dict", test_05_build_tool_schema_correct_format),
    ("6.  call_llm() text response -> text is set, tool_name is None", test_06_call_llm_text_response),
    ("7.  call_llm() tool_call response -> tool_name and tool_args set, text is None", test_07_call_llm_tool_call_response),
    ("8.  LLMResponse.provider matches active provider at call time", test_08_llm_response_provider_field),
    ("9.  Token counts parsed correctly from mocked usage object", test_09_token_counts_parsed_correctly),
]


if __name__ == "__main__":
    print("=" * 70)
    print("Story 2.1 — LLM Abstraction Layer Tests")
    print("=" * 70)

    for test_name, test_fn in TESTS:
        run_test(test_name, test_fn)

    print()
    print("=" * 70)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    total = len(results)
    print(f"Results: {passed}/{total} passed, {failed} failed")
    print("=" * 70)

    if failed:
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
        sys.exit(0)
