"""
tests/test_agent.py — Tests for engine/agent.py (Story 2.4)

Mocks engine.llm.call_llm so no live Ollama is required.
Uses real tools and WorldState for everything else.

Run with:
    .venv/Scripts/python.exe tests/test_agent.py
"""

import asyncio
import io
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Force UTF-8 output on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Import the modules under test
# ---------------------------------------------------------------------------

from engine.agent import AgentRunner, AgentState, agent_graph, gather_context
from engine.tools import world

# ---------------------------------------------------------------------------
# Test harness helpers
# ---------------------------------------------------------------------------

_pass = 0
_fail = 0


def _reset_world() -> None:
    """Reload world state from disk to undo any in-memory mutations."""
    world.load()


def _run(coro):
    """Run an async coroutine synchronously in a fresh event loop."""
    return asyncio.run(coro)


def check(test_name: str, passed: bool, detail: str = "") -> None:
    global _pass, _fail
    status = "PASS" if passed else "FAIL"
    if passed:
        _pass += 1
    else:
        _fail += 1
    extra = f" — {detail}" if detail else ""
    print(f"[{status}] {test_name}{extra}")


# ---------------------------------------------------------------------------
# Mock factory helpers
# ---------------------------------------------------------------------------


def _make_tool_call_mock(tool_name: str, tool_args: dict) -> MagicMock:
    """Return a mock LLMResponse that looks like a structured tool call."""
    mock_resp = MagicMock()
    mock_resp.tool_name = tool_name
    mock_resp.tool_args = tool_args
    mock_resp.text = None
    mock_resp.provider = "ollama"
    mock_resp.input_tokens = 100
    mock_resp.output_tokens = 50
    return mock_resp


def _make_text_only_mock(text: str) -> MagicMock:
    """Return a mock LLMResponse with plain text and no tool call."""
    mock_resp = MagicMock()
    mock_resp.tool_name = None
    mock_resp.tool_args = None
    mock_resp.text = text
    mock_resp.provider = "ollama"
    mock_resp.input_tokens = 80
    mock_resp.output_tokens = 40
    return mock_resp


def _make_diary_mock(text: str = "Spent the morning looking at the world around me.") -> MagicMock:
    """Return a mock LLMResponse for the diary/reflect node."""
    return _make_text_only_mock(text)


# ---------------------------------------------------------------------------
# Test 1: AgentRunner instantiates without error
# ---------------------------------------------------------------------------


def test_runner_instantiation():
    """AgentRunner can be created with a valid agent name."""
    try:
        runner = AgentRunner("arjun")
        check(
            "Test 1: AgentRunner instantiates without error",
            isinstance(runner, AgentRunner) and runner.agent_name == "arjun",
            f"agent_name={runner.agent_name}",
        )
    except Exception as exc:
        check("Test 1: AgentRunner instantiates without error", False, str(exc))


# ---------------------------------------------------------------------------
# Test 2: gather_context populates soul, goals, needs_summary, surroundings
# ---------------------------------------------------------------------------


def test_gather_context_populates_fields():
    """gather_context fills in soul, goals, needs_summary, and surroundings."""
    _reset_world()

    initial: AgentState = AgentState(
        agent_name="arjun",
        soul="",
        goals="",
        needs_summary="",
        surroundings="",
        inbox_messages=[],
        memory_snippets="",
        llm_prompt="",
        tool_name=None,
        tool_args=None,
        tool_result="",
        diary_entry="",
        tick_count=0,
    )

    try:
        result = _run(gather_context(initial))
        soul_ok = bool(result["soul"]) and "Arjun" in result["soul"]
        goals_ok = bool(result["goals"])
        needs_ok = "Hunger:" in result["needs_summary"]
        surroundings_ok = "Location:" in result["surroundings"]
        prompt_ok = "=== WHO YOU ARE ===" in result["llm_prompt"]

        check(
            "Test 2a: soul is populated and mentions 'Arjun'",
            soul_ok,
            repr(result["soul"][:60]),
        )
        check(
            "Test 2b: goals is populated",
            goals_ok,
            repr(result["goals"][:60]),
        )
        check(
            "Test 2c: needs_summary contains 'Hunger:'",
            needs_ok,
            repr(result["needs_summary"][:80]),
        )
        check(
            "Test 2d: surroundings contains 'Location:'",
            surroundings_ok,
            repr(result["surroundings"][:80]),
        )
        check(
            "Test 2e: llm_prompt contains section headers",
            prompt_ok,
            repr(result["llm_prompt"][:80]),
        )
    except Exception as exc:
        for label in ("2a", "2b", "2c", "2d", "2e"):
            check(f"Test {label}: gather_context", False, str(exc))


# ---------------------------------------------------------------------------
# Test 3: Full tick with LLM returning look_around tool call
# ---------------------------------------------------------------------------


def test_full_tick_look_around():
    """Full tick completes and diary_entry is non-empty when LLM calls look_around."""
    _reset_world()

    look_mock = _make_tool_call_mock("look_around", {})
    diary_mock = _make_diary_mock("Just looked around. The apartment corridor smelled of dal again.")

    # call_llm is called twice: once in llm_decide (tool call), once in reflect (diary)
    side_effects = [look_mock, diary_mock]

    async def run_tick():
        with patch("engine.agent.call_llm", new_callable=AsyncMock, side_effect=side_effects):
            runner = AgentRunner("arjun")
            return await runner.tick()

    try:
        result = _run(run_tick())
        check(
            "Test 3a: tick completes (tool_name == 'look_around')",
            result["tool_name"] == "look_around",
            f"tool_name={result['tool_name']}",
        )
        check(
            "Test 3b: diary_entry is non-empty",
            bool(result["diary_entry"]),
            repr(result["diary_entry"][:80]),
        )
        check(
            "Test 3c: tool_result is non-empty",
            bool(result["tool_result"]),
            repr(result["tool_result"][:80]),
        )
    except Exception as exc:
        for label in ("3a", "3b", "3c"):
            check(f"Test {label}: full tick look_around", False, str(exc))


# ---------------------------------------------------------------------------
# Test 4: Full tick with move_to — arjun moves to metro
# ---------------------------------------------------------------------------


def test_full_tick_move_to_metro():
    """Full tick with move_to(metro) actually moves arjun to metro in world state."""
    _reset_world()
    # arjun starts at apartment — metro is a valid connected location

    move_mock = _make_tool_call_mock("move_to", {"location": "metro"})
    diary_mock = _make_diary_mock("Took the metro today. The commute felt routine but grounding.")

    side_effects = [move_mock, diary_mock]

    async def run_tick():
        with patch("engine.agent.call_llm", new_callable=AsyncMock, side_effect=side_effects):
            runner = AgentRunner("arjun")
            return await runner.tick()

    try:
        result = _run(run_tick())
        check(
            "Test 4a: tool_name is 'move_to'",
            result["tool_name"] == "move_to",
            f"tool_name={result['tool_name']}",
        )
        arjun_location = world.get_agent_location("arjun")
        check(
            "Test 4b: arjun is now at 'metro'",
            arjun_location == "metro",
            f"location={arjun_location}",
        )
        check(
            "Test 4c: tool_result mentions 'Moved'",
            "Moved" in result["tool_result"],
            repr(result["tool_result"]),
        )
    except Exception as exc:
        for label in ("4a", "4b", "4c"):
            check(f"Test {label}: full tick move_to metro", False, str(exc))


# ---------------------------------------------------------------------------
# Test 5: Fallback — LLM returns text-only (no tool call)
# ---------------------------------------------------------------------------


def test_fallback_text_only_response():
    """When LLM returns text only, tick still completes via look_around fallback."""
    _reset_world()

    text_mock = _make_text_only_mock("I think I should look around.")
    diary_mock = _make_diary_mock("Ended up just taking stock of where I am. That's enough for now.")

    side_effects = [text_mock, diary_mock]

    async def run_tick():
        with patch("engine.agent.call_llm", new_callable=AsyncMock, side_effect=side_effects):
            runner = AgentRunner("arjun")
            return await runner.tick()

    try:
        result = _run(run_tick())
        check(
            "Test 5a: tick completes without error (tool_name is not None)",
            result["tool_name"] is not None,
            f"tool_name={result['tool_name']}",
        )
        check(
            "Test 5b: fallback tool is 'look_around'",
            result["tool_name"] == "look_around",
            f"tool_name={result['tool_name']}",
        )
        check(
            "Test 5c: diary_entry is non-empty",
            bool(result["diary_entry"]),
            repr(result["diary_entry"][:80]),
        )
    except Exception as exc:
        for label in ("5a", "5b", "5c"):
            check(f"Test {label}: fallback text-only", False, str(exc))


# ---------------------------------------------------------------------------
# Test 6: After 3 ticks, diary.md has 3 entries
# ---------------------------------------------------------------------------


def test_three_ticks_diary_entries():
    """After 3 ticks, arjun's diary.md gains exactly 3 new entries."""
    _reset_world()

    diary_path = os.path.join("agents", "arjun", "diary.md")

    # Record how many entries exist before the test
    try:
        with open(diary_path, "r", encoding="utf-8") as f:
            before_content = f.read()
        entries_before = before_content.count("# Day ")
    except FileNotFoundError:
        before_content = ""
        entries_before = 0

    look_mock = _make_tool_call_mock("look_around", {})
    diary_mock_text = "Another tick done. Gurgaon keeps moving."

    # We need 6 side effects: 2 call_llm calls per tick × 3 ticks
    side_effects = []
    for _ in range(3):
        side_effects.append(_make_tool_call_mock("look_around", {}))
        side_effects.append(_make_text_only_mock(diary_mock_text))

    async def run_three_ticks():
        runner = AgentRunner("arjun")
        with patch("engine.agent.call_llm", new_callable=AsyncMock, side_effect=side_effects):
            for _ in range(3):
                await runner.tick()

    try:
        _run(run_three_ticks())

        with open(diary_path, "r", encoding="utf-8") as f:
            after_content = f.read()
        entries_after = after_content.count("# Day ")
        new_entries = entries_after - entries_before

        check(
            "Test 6a: diary.md has 3 new entries after 3 ticks",
            new_entries == 3,
            f"new_entries={new_entries} (before={entries_before}, after={entries_after})",
        )
        check(
            "Test 6b: diary text is present in diary.md",
            diary_mock_text in after_content,
            repr(after_content[-200:]),
        )
    except Exception as exc:
        for label in ("6a", "6b"):
            check(f"Test {label}: 3-tick diary", False, str(exc))


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    print("=" * 60)
    print("Running engine/agent.py tests  (Story 2.4)")
    print("=" * 60)
    print()

    test_runner_instantiation()          # Test 1
    print()
    test_gather_context_populates_fields()  # Test 2
    print()
    test_full_tick_look_around()         # Test 3
    print()
    test_full_tick_move_to_metro()       # Test 4
    print()
    test_fallback_text_only_response()   # Test 5
    print()
    test_three_ticks_diary_entries()     # Test 6

    print()
    print("=" * 60)
    print(f"Results: {_pass} passed, {_fail} failed out of {_pass + _fail} checks")
    print("=" * 60)

    if _fail > 0:
        sys.exit(1)
