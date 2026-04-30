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
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# engine modules read world/state.json relative to cwd at import time.
os.chdir(ROOT)

# ---------------------------------------------------------------------------
# Import the modules under test
# ---------------------------------------------------------------------------

from engine.agent import (
    AgentRunner,
    AgentState,
    agent_graph,
    consolidate_memory,
    gather_context,
    night_reflection,
    personality_modifier,
)
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
# Test 7: gather_context injects per-pair conversation history (Story 9.1)
# ---------------------------------------------------------------------------


def test_gather_context_injects_conversation_history():
    """When unread inbox messages are present, the prompt includes a
    `=== RECENT EXCHANGES WITH {SENDER} ===` block with the last messages
    between this agent and that sender (Story 9.1)."""
    _reset_world()

    # Seed conversation history between arjun and kavya
    asyncio.run(world.add_conversation("arjun", "kavya", "coffee at cyber hub?"))
    asyncio.run(world.add_conversation("kavya", "arjun", "haan but kab"))
    asyncio.run(world.add_conversation("arjun", "kavya", "kal evening?"))

    # Drop a fresh message into arjun's inbox from kavya so the history block fires
    asyncio.run(world.add_to_inbox("arjun", {
        "from": "kavya", "type": "message", "text": "ok done, 6pm",
        "day": 1, "sim_time": world.get_time()["sim_time"],
    }))

    initial: AgentState = AgentState(
        agent_name="arjun", soul="", goals="", needs_summary="",
        surroundings="", inbox_messages=[], memory_snippets="",
        llm_prompt="", tool_name=None, tool_args=None,
        tool_result="", diary_entry="", tick_count=0,
    )

    try:
        result = _run(gather_context(initial))
        prompt = result["llm_prompt"]
        has_block = "=== RECENT EXCHANGES WITH KAVYA ===" in prompt
        has_seeded_msg = "coffee at cyber hub?" in prompt and "kal evening?" in prompt
        has_advance_directive = "STOP messaging" in prompt or "say something NEW" in prompt

        check(
            "Test 7a: prompt includes RECENT EXCHANGES WITH KAVYA block",
            has_block,
            "block missing" if not has_block else "ok",
        )
        check(
            "Test 7b: prompt includes the seeded conversation lines",
            has_seeded_msg,
            "seeded messages missing" if not has_seeded_msg else "ok",
        )
        check(
            "Test 7c: prompt includes the advance-or-stop directive",
            has_advance_directive,
            "directive missing" if not has_advance_directive else "ok",
        )
    except Exception as exc:
        for label in ("7a", "7b", "7c"):
            check(f"Test {label}: history injection", False, str(exc))


# ---------------------------------------------------------------------------
# Test 8: gather_context injects yesterday_reflection block (Story 9.2)
# ---------------------------------------------------------------------------


def test_gather_context_injects_yesterday_reflection():
    """When yesterday_reflection is set, prompt contains the YESTERDAY YOU WROTE
    block, the reflection text, and the new decision-ladder directive."""
    _reset_world()

    reflection_text = (
        "Aaj realize hua I never actually talked to anyone properly. "
        "Kal I will go to dhaba at lunch and say hi to whoever is there."
    )
    asyncio.run(world.set_yesterday_reflection("arjun", reflection_text))

    initial: AgentState = AgentState(
        agent_name="arjun", soul="", goals="", needs_summary="",
        surroundings="", inbox_messages=[], memory_snippets="",
        llm_prompt="", tool_name=None, tool_args=None,
        tool_result="", diary_entry="", tick_count=0,
    )

    try:
        result = _run(gather_context(initial))
        prompt = result["llm_prompt"]
        has_block = "=== YESTERDAY YOU WROTE ===" in prompt
        has_text = reflection_text[:40] in prompt
        has_directive = "honors it" in prompt or "behavior to change" in prompt

        check(
            "Test 8a: prompt includes YESTERDAY YOU WROTE block",
            has_block,
            "block missing" if not has_block else "ok",
        )
        check(
            "Test 8b: prompt includes the reflection text",
            has_text,
            "reflection text missing" if not has_text else "ok",
        )
        check(
            "Test 8c: prompt includes the honor-yesterday directive",
            has_directive,
            "directive missing" if not has_directive else "ok",
        )
    except Exception as exc:
        for label in ("8a", "8b", "8c"):
            check(f"Test {label}: yesterday_reflection injection", False, str(exc))


def test_gather_context_includes_refuse_directive():
    """Story 9.3: prompt contains the 'you are allowed to refuse' directive."""
    _reset_world()

    initial: AgentState = AgentState(
        agent_name="arjun", soul="", goals="", needs_summary="",
        surroundings="", inbox_messages=[], memory_snippets="",
        llm_prompt="", tool_name=None, tool_args=None,
        tool_result="", diary_entry="", tick_count=0,
    )

    try:
        result = _run(gather_context(initial))
        prompt = result["llm_prompt"]
        has_allowed = "allowed to refuse" in prompt
        has_refuse_tool = "`refuse`" in prompt
        has_disagree_tool = "`disagree`" in prompt

        check(
            "Test 9.3a: prompt includes 'allowed to refuse' directive",
            has_allowed,
            "directive missing" if not has_allowed else "ok",
        )
        check(
            "Test 9.3b: prompt mentions the refuse tool by name",
            has_refuse_tool,
            "refuse tool reference missing" if not has_refuse_tool else "ok",
        )
        check(
            "Test 9.3c: prompt mentions the disagree tool by name",
            has_disagree_tool,
            "disagree tool reference missing" if not has_disagree_tool else "ok",
        )
    except Exception as exc:
        for label in ("9.3a", "9.3b", "9.3c"):
            check(f"Test {label}: refuse directive in prompt", False, str(exc))


def test_gather_context_omits_block_when_empty():
    """When yesterday_reflection is empty, the YESTERDAY YOU WROTE block is absent."""
    _reset_world()
    asyncio.run(world.set_yesterday_reflection("arjun", ""))

    initial: AgentState = AgentState(
        agent_name="arjun", soul="", goals="", needs_summary="",
        surroundings="", inbox_messages=[], memory_snippets="",
        llm_prompt="", tool_name=None, tool_args=None,
        tool_result="", diary_entry="", tick_count=0,
    )

    try:
        result = _run(gather_context(initial))
        prompt = result["llm_prompt"]
        check(
            "Test 8d: empty reflection -> YESTERDAY YOU WROTE block absent",
            "=== YESTERDAY YOU WROTE ===" not in prompt,
            "block unexpectedly present" if "=== YESTERDAY YOU WROTE ===" in prompt else "ok",
        )
    except Exception as exc:
        check("Test 8d: empty reflection omits block", False, str(exc))


# ---------------------------------------------------------------------------
# Test 9: night_reflection writes the result to world state (Story 9.2)
# ---------------------------------------------------------------------------


def test_night_reflection_writes_state():
    """night_reflection makes one LLM call and stores the text on the agent dict."""
    _reset_world()
    # Clear any previous reflection
    asyncio.run(world.set_yesterday_reflection("arjun", ""))

    mock_text = (
        "Bohot tired aaj. Kept defaulting to apartment-metro-cyber-city loop. "
        "Kal lunch break pe dhaba try karunga, see who's around."
    )
    reflection_mock = _make_text_only_mock(mock_text)

    async def run_reflection():
        with patch("engine.agent.call_llm", new=AsyncMock(return_value=reflection_mock)):
            return await night_reflection("arjun", completed_day=1)

    try:
        returned = _run(run_reflection())
        stored = world.get_yesterday_reflection("arjun")
        check(
            "Test 9a: night_reflection returns the LLM text",
            returned == mock_text,
            f"returned[:40]={returned[:40]!r}",
        )
        check(
            "Test 9b: yesterday_reflection persisted on agent dict",
            stored == mock_text,
            f"stored[:40]={stored[:40]!r}",
        )
        # Overwrite — second call replaces, doesn't append
        new_text = "Day 2 over. Kal I will work less and rest more."
        with patch("engine.agent.call_llm", new=AsyncMock(return_value=_make_text_only_mock(new_text))):
            _run(night_reflection("arjun", completed_day=2))
        check(
            "Test 9c: subsequent reflection overwrites previous",
            world.get_yesterday_reflection("arjun") == new_text,
            f"got={world.get_yesterday_reflection('arjun')[:40]!r}",
        )
    except Exception as exc:
        for label in ("9a", "9b", "9c"):
            check(f"Test {label}: night_reflection state", False, str(exc))


# ---------------------------------------------------------------------------
# Test 10: gather_context injects UPCOMING PLANS block (Story 9.5)
# ---------------------------------------------------------------------------


def test_gather_context_injects_upcoming_plans():
    """When the agent has a pending or confirmed plan, the prompt includes the
    UPCOMING PLANS block and the priority directive when imminent."""
    _reset_world()
    world._state["shared_plans"] = []
    world._state["next_plan_id"] = 1
    cur = world.get_time()
    target_abs = cur["day"] * 1440 + cur["sim_time"] + 15
    asyncio.run(world.add_shared_plan({
        "participants": ["arjun", "kavya"],
        "location": "dhaba",
        "target_time": target_abs,
        "activity": "lunch",
        "status": "confirmed",
    }))

    initial: AgentState = AgentState(
        agent_name="arjun", soul="", goals="", needs_summary="",
        surroundings="", inbox_messages=[], memory_snippets="",
        llm_prompt="", tool_name=None, tool_args=None,
        tool_result="", diary_entry="", tick_count=0,
    )

    try:
        result = _run(gather_context(initial))
        prompt = result["llm_prompt"]
        check(
            "Test 10a: prompt contains UPCOMING PLANS block",
            "=== UPCOMING PLANS ===" in prompt,
            "block missing" if "=== UPCOMING PLANS ===" not in prompt else "ok",
        )
        check(
            "Test 10b: prompt mentions kavya, dhaba, and lunch",
            "kavya" in prompt and "dhaba" in prompt and "lunch" in prompt,
            "fields missing",
        )
        check(
            "Test 10c: prompt includes the 30-min priority directive",
            "next 30 min" in prompt or "prioritise" in prompt or "prioritize" in prompt,
            "priority directive missing",
        )
    except Exception as exc:
        for label in ("10a", "10b", "10c"):
            check(f"Test {label}: upcoming plans injection", False, str(exc))


def test_gather_context_omits_upcoming_plans_when_none():
    """When the agent has no pending/confirmed plans, the UPCOMING PLANS block is absent."""
    _reset_world()
    world._state["shared_plans"] = []
    world._state["next_plan_id"] = 1

    initial: AgentState = AgentState(
        agent_name="arjun", soul="", goals="", needs_summary="",
        surroundings="", inbox_messages=[], memory_snippets="",
        llm_prompt="", tool_name=None, tool_args=None,
        tool_result="", diary_entry="", tick_count=0,
    )

    try:
        result = _run(gather_context(initial))
        check(
            "Test 10d: no plans -> UPCOMING PLANS block absent",
            "=== UPCOMING PLANS ===" not in result["llm_prompt"],
            "block unexpectedly present",
        )
    except Exception as exc:
        check("Test 10d: no plans omits block", False, str(exc))


# ---------------------------------------------------------------------------
# Test 11: gather_context injects FINANCIAL STRESS block (Story 9.4)
# ---------------------------------------------------------------------------


def test_gather_context_injects_financial_stress():
    """When agent.financial_stress is True, the prompt contains the
    FINANCIAL STRESS block with the working/eating/asking-for-help directive."""
    _reset_world()
    arjun = world.get_agent("arjun")
    arjun["financial_stress"] = True
    arjun["financial_stress_until_day"] = 99

    initial: AgentState = AgentState(
        agent_name="arjun", soul="", goals="", needs_summary="",
        surroundings="", inbox_messages=[], memory_snippets="",
        llm_prompt="", tool_name=None, tool_args=None,
        tool_result="", diary_entry="", tick_count=0,
    )

    try:
        result = _run(gather_context(initial))
        prompt = result["llm_prompt"]
        check(
            "Test 11a: prompt includes FINANCIAL STRESS block",
            "=== FINANCIAL STRESS ===" in prompt,
            "block missing" if "=== FINANCIAL STRESS ===" not in prompt else "ok",
        )
        check(
            "Test 11b: prompt mentions behind on rent",
            "behind on rent" in prompt,
            "rent line missing" if "behind on rent" not in prompt else "ok",
        )
        check(
            "Test 11c: prompt includes work / eat-cheap / asking-for-help guidance",
            ("working extra" in prompt) and ("eat at home" in prompt)
            and ("asking someone" in prompt),
            "guidance text missing",
        )
    except Exception as exc:
        for label in ("11a", "11b", "11c"):
            check(f"Test {label}: financial_stress injection", False, str(exc))


def test_gather_context_omits_financial_stress_when_false():
    """When agent.financial_stress is False, the FINANCIAL STRESS block is absent."""
    _reset_world()
    arjun = world.get_agent("arjun")
    arjun["financial_stress"] = False

    initial: AgentState = AgentState(
        agent_name="arjun", soul="", goals="", needs_summary="",
        surroundings="", inbox_messages=[], memory_snippets="",
        llm_prompt="", tool_name=None, tool_args=None,
        tool_result="", diary_entry="", tick_count=0,
    )

    try:
        result = _run(gather_context(initial))
        check(
            "Test 11d: no stress -> FINANCIAL STRESS block absent",
            "=== FINANCIAL STRESS ===" not in result["llm_prompt"],
            "block unexpectedly present",
        )
    except Exception as exc:
        check("Test 11d: no stress omits block", False, str(exc))


# ---------------------------------------------------------------------------
# Test 12: personality_modifier returns the right text per archetype + mood (Story 9.6)
# ---------------------------------------------------------------------------


def test_personality_modifier_per_archetype():
    """personality_modifier returns the archetype-specific directive for each
    of the 7 archetypes when mood is in the neutral range."""
    cases = {
        "office_worker": "working through problems over socializing",
        "vendor":        "read your surroundings before acting",
        "retired":       "move at your own pace",
        "homemaker":     "default radius is family/household",
        "student":       "reactive and emotional",
        "night_owl":     "Daytime drains you",
        "entrepreneur":  "evaluating people for usefulness",
    }
    for archetype, expected_phrase in cases.items():
        text = personality_modifier("arjun", mood=50.0, archetype=archetype)
        check(
            f"Test 12.{archetype}: directive contains expected phrase",
            expected_phrase in text,
            f"got={text[:80]!r}",
        )


def test_personality_modifier_mood_low_override():
    """mood < 30 appends the depleted override on top of the base directive."""
    text = personality_modifier("arjun", mood=15, archetype="office_worker")
    check(
        "Test 12.low_a: depleted phrase present when mood<30",
        "depleted" in text,
        f"got={text[:120]!r}",
    )
    check(
        "Test 12.low_b: base directive still present when mood<30",
        "working through problems" in text,
        f"got={text[:120]!r}",
    )


def test_personality_modifier_mood_high_override():
    """mood > 75 appends the flowing override on top of the base directive."""
    text = personality_modifier("kavya", mood=90, archetype="student")
    check(
        "Test 12.high_a: flowing phrase present when mood>75",
        "flowing" in text,
        f"got={text[:120]!r}",
    )
    check(
        "Test 12.high_b: base directive still present when mood>75",
        "reactive and emotional" in text,
        f"got={text[:120]!r}",
    )


def test_personality_modifier_no_override_in_neutral_range():
    """mood in [30, 75] adds no mood override."""
    text = personality_modifier("vikram", mood=50, archetype="retired")
    check(
        "Test 12.neutral: no override phrase when mood is neutral",
        "depleted" not in text and "flowing" not in text,
        f"got={text[:120]!r}",
    )


def test_gather_context_injects_personality_block():
    """gather_context injects the HOW YOU TYPICALLY ACT block above the
    decision ladder, with the right archetype text for the agent."""
    _reset_world()

    initial: AgentState = AgentState(
        agent_name="arjun", soul="", goals="", needs_summary="",
        surroundings="", inbox_messages=[], memory_snippets="",
        llm_prompt="", tool_name=None, tool_args=None,
        tool_result="", diary_entry="", tick_count=0,
    )

    try:
        result = _run(gather_context(initial))
        prompt = result["llm_prompt"]
        has_block = "=== HOW YOU TYPICALLY ACT ===" in prompt
        has_directive = "working through problems over socializing" in prompt
        # Block must appear before the decision ladder
        block_idx = prompt.find("=== HOW YOU TYPICALLY ACT ===")
        ladder_idx = prompt.find("=== WHAT DO YOU DO? ===")
        ordered = block_idx != -1 and ladder_idx != -1 and block_idx < ladder_idx

        check(
            "Test 12.ctx_a: prompt includes HOW YOU TYPICALLY ACT block",
            has_block,
            "block missing" if not has_block else "ok",
        )
        check(
            "Test 12.ctx_b: prompt contains arjun's office_worker directive",
            has_directive,
            "directive missing" if not has_directive else "ok",
        )
        check(
            "Test 12.ctx_c: personality block appears before decision ladder",
            ordered,
            f"block_idx={block_idx}, ladder_idx={ladder_idx}",
        )
    except Exception as exc:
        for label in ("12.ctx_a", "12.ctx_b", "12.ctx_c"):
            check(f"Test {label}: personality block injection", False, str(exc))


# ---------------------------------------------------------------------------
# Story 9.7 — consolidate_memory tests
# ---------------------------------------------------------------------------


def _backup_memory(agent_name: str) -> tuple[str, str | None]:
    """Read and return current memory.md content (or None) so we can restore it."""
    path = os.path.join("agents", agent_name, "memory.md")
    if not os.path.exists(path):
        return path, None
    with open(path, "r", encoding="utf-8") as f:
        return path, f.read()


def _restore_memory(path: str, original: str | None) -> None:
    if original is None:
        if os.path.exists(path):
            os.remove(path)
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(original)


def test_consolidate_memory_writes_file():
    """consolidate_memory replaces memory.md with the LLM output."""
    _reset_world()
    path, original = _backup_memory("arjun")
    new_text = (
        "# Arjun's Memory (rewritten)\n"
        "- Office is draining; lunch with Kavya genuinely helps.\n"
        "- I should stop avoiding direct conversation.\n"
    )
    mock_resp = _make_text_only_mock(new_text)

    async def run_it():
        with patch("engine.agent.call_llm", new=AsyncMock(return_value=mock_resp)):
            return await consolidate_memory("arjun", completed_day=3)

    try:
        returned = _run(run_it())
        with open(path, "r", encoding="utf-8") as f:
            written = f.read()
        check(
            "Test 9.7a: consolidate_memory returns LLM text",
            returned.strip() == new_text.strip(),
            f"returned[:60]={returned[:60]!r}",
        )
        check(
            "Test 9.7b: memory.md content matches LLM output",
            new_text.strip() in written,
            f"written[:120]={written[:120]!r}",
        )
    except Exception as exc:
        for label in ("9.7a", "9.7b"):
            check(f"Test {label}: consolidate_memory write", False, str(exc))
    finally:
        _restore_memory(path, original)


def test_consolidate_memory_logs_event():
    """consolidate_memory adds a memory_updated event to world events."""
    _reset_world()
    path, original = _backup_memory("priya")
    events_before = len(world._state.get("events", []))
    mock_resp = _make_text_only_mock("- Refreshed memory for priya.")

    async def run_it():
        with patch("engine.agent.call_llm", new=AsyncMock(return_value=mock_resp)):
            return await consolidate_memory("priya", completed_day=4)

    try:
        _run(run_it())
        events = world._state.get("events", [])
        new_events = events[events_before:]
        matched = [
            e for e in new_events
            if "priya" in e.get("text", "") and "updated their memory" in e.get("text", "")
        ]
        check(
            "Test 9.7c: memory_updated event appears in world events",
            len(matched) >= 1,
            f"new_events_count={len(new_events)}, matched={len(matched)}",
        )
    except Exception as exc:
        check("Test 9.7c: memory_updated event logged", False, str(exc))
    finally:
        _restore_memory(path, original)


def test_consolidate_memory_skips_on_empty_llm():
    """consolidate_memory leaves memory.md untouched when LLM returns empty text."""
    _reset_world()
    path, original = _backup_memory("kavya")
    empty_resp = _make_text_only_mock("")

    async def run_it():
        with patch("engine.agent.call_llm", new=AsyncMock(return_value=empty_resp)):
            return await consolidate_memory("kavya", completed_day=3)

    try:
        returned = _run(run_it())
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                after = f.read()
        else:
            after = None
        check(
            "Test 9.7d: empty LLM response returns empty string",
            returned == "",
            f"returned={returned!r}",
        )
        # File should be unchanged: either still missing (None) or matching original.
        unchanged = (after == original)
        check(
            "Test 9.7e: memory.md untouched on empty LLM response",
            unchanged,
            f"after_exists={after is not None}, original_exists={original is not None}",
        )
    except Exception as exc:
        for label in ("9.7d", "9.7e"):
            check(f"Test {label}: consolidate_memory empty path", False, str(exc))
    finally:
        _restore_memory(path, original)


# ---------------------------------------------------------------------------
# Story 9.8 — Scheduled External Events: TODAY block in gather_context
# ---------------------------------------------------------------------------


def test_gather_context_injects_today_block_when_event_active():
    """When a scheduled event matches the agent, gather_context injects
    `=== TODAY ===` above the schedule section, with the event description."""
    _reset_world()

    # Force a known sim time within the meetup window: Day 3, 13:30pm.
    world._state["day"] = 3
    world._state["sim_time"] = 13 * 60 + 30

    # Replace authored events with a single deterministic one in memory.
    world._scheduled_events = [{
        "day": 3,
        "start_hour": 13,
        "end_hour": 14,
        "location": "cyber_hub",
        "type": "meetup",
        "description": "startup meetup is happening",
        "affected_agents": "archetype:office_worker,entrepreneur",
    }]

    initial: AgentState = AgentState(
        agent_name="arjun", soul="", goals="", needs_summary="",
        surroundings="", inbox_messages=[], memory_snippets="",
        llm_prompt="", tool_name=None, tool_args=None,
        tool_result="", diary_entry="", tick_count=0,
    )
    try:
        result = _run(gather_context(initial))
        prompt = result["llm_prompt"]
        has_block = "=== TODAY ===" in prompt
        has_desc = "startup meetup is happening" in prompt
        has_loc = "cyber_hub" in prompt
        # TODAY should appear before SCHEDULE so the event frames the day.
        today_idx = prompt.find("=== TODAY ===")
        sched_idx = prompt.find("=== SCHEDULE ===")
        ordered = today_idx != -1 and (sched_idx == -1 or today_idx < sched_idx)

        check(
            "Test 9.8a: prompt includes TODAY block when event active",
            has_block,
            "block missing" if not has_block else "ok",
        )
        check(
            "Test 9.8b: TODAY block contains the event description",
            has_desc,
            "description missing" if not has_desc else "ok",
        )
        check(
            "Test 9.8c: TODAY block names the event location",
            has_loc,
            "location missing" if not has_loc else "ok",
        )
        check(
            "Test 9.8d: TODAY block precedes SCHEDULE block",
            ordered,
            f"today_idx={today_idx}, sched_idx={sched_idx}",
        )
    except Exception as exc:
        for label in ("9.8a", "9.8b", "9.8c", "9.8d"):
            check(f"Test {label}: TODAY block injection", False, str(exc))
    finally:
        _reset_world()


def test_gather_context_omits_today_block_when_no_active_events():
    """When no scheduled event matches the agent, the TODAY block is absent."""
    _reset_world()
    # Day 1 — none of the seeded events fire on day 1.
    world._state["day"] = 1
    world._state["sim_time"] = 10 * 60

    initial: AgentState = AgentState(
        agent_name="arjun", soul="", goals="", needs_summary="",
        surroundings="", inbox_messages=[], memory_snippets="",
        llm_prompt="", tool_name=None, tool_args=None,
        tool_result="", diary_entry="", tick_count=0,
    )
    try:
        result = _run(gather_context(initial))
        check(
            "Test 9.8e: no active event -> TODAY block absent",
            "=== TODAY ===" not in result["llm_prompt"],
            "block unexpectedly present",
        )
    except Exception as exc:
        check("Test 9.8e: TODAY omitted when no event", False, str(exc))
    finally:
        _reset_world()


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
    test_gather_context_injects_conversation_history()  # Test 7 (Story 9.1)
    print()
    test_gather_context_injects_yesterday_reflection()   # Test 8 (Story 9.2)
    print()
    test_gather_context_omits_block_when_empty()         # Test 8d (Story 9.2)
    print()
    test_gather_context_includes_refuse_directive()      # Test 9.3 (Story 9.3)
    print()
    test_night_reflection_writes_state()                 # Test 9 (Story 9.2)
    print()
    test_gather_context_injects_upcoming_plans()         # Test 10 (Story 9.5)
    print()
    test_gather_context_omits_upcoming_plans_when_none() # Test 10d (Story 9.5)
    print()
    test_gather_context_injects_financial_stress()       # Test 11 (Story 9.4)
    print()
    test_gather_context_omits_financial_stress_when_false()  # Test 11d (Story 9.4)
    print()
    test_personality_modifier_per_archetype()                # Test 12 (Story 9.6)
    print()
    test_personality_modifier_mood_low_override()            # Test 12.low (Story 9.6)
    print()
    test_personality_modifier_mood_high_override()           # Test 12.high (Story 9.6)
    print()
    test_personality_modifier_no_override_in_neutral_range() # Test 12.neutral (Story 9.6)
    print()
    test_gather_context_injects_personality_block()          # Test 12.ctx (Story 9.6)
    print()
    test_consolidate_memory_writes_file()                    # Test 9.7a/b (Story 9.7)
    print()
    test_consolidate_memory_logs_event()                     # Test 9.7c (Story 9.7)
    print()
    test_consolidate_memory_skips_on_empty_llm()             # Test 9.7d/e (Story 9.7)
    print()
    test_gather_context_injects_today_block_when_event_active()    # Story 9.8
    print()
    test_gather_context_omits_today_block_when_no_active_events()  # Story 9.8

    print()
    print("=" * 60)
    print(f"Results: {_pass} passed, {_fail} failed out of {_pass + _fail} checks")
    print("=" * 60)

    if _fail > 0:
        sys.exit(1)
