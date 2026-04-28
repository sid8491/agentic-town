"""
Story 7.2 — Daily Summary Notification Tests

Verifies:
  1. set_daily_summary + pop_daily_summary round-trip
  2. pop_daily_summary returns None when nothing is pending
  3. Second pop after a set returns None (value cleared)
  4. _write_state excludes _pending_summary from saved JSON
  5. _generate_daily_summary saves a log file when LLM succeeds
  6. _generate_daily_summary is a no-op when events list is empty
  7. _generate_daily_summary sets _pending_summary via set_daily_summary
  8. advance_time increments day counter when sim_time crosses midnight

Run with:
    .venv/Scripts/python.exe tests/test_daily_summary.py
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys
import tempfile
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT     = pathlib.Path(__file__).parent.parent
MAP_PATH = ROOT / "world" / "map.json"

from engine.world import WorldState, SimulationLoop
from engine.llm import LLMResponse

results: list[tuple[str, bool, str | None]] = []


def ok(name: str) -> None:
    results.append((name, True, None))
    print(f"  PASS  {name}")


def fail(name: str, reason: str) -> None:
    results.append((name, False, reason))
    print(f"  FAIL  {name}")
    print(f"        {reason}")


def run(name: str, coro_or_fn):
    try:
        if asyncio.iscoroutinefunction(coro_or_fn):
            asyncio.run(coro_or_fn())
        else:
            coro_or_fn()
        ok(name)
    except AssertionError as exc:
        fail(name, str(exc))
    except Exception as exc:
        fail(name, f"{type(exc).__name__}: {exc}")


def make_world(state_path: str) -> WorldState:
    ws = WorldState(state_path=state_path, map_path=str(MAP_PATH))
    ws._build_fresh_state()
    return ws


def make_stub_response(text: str) -> LLMResponse:
    return LLMResponse(
        text=text,
        tool_name=None,
        tool_args=None,
        provider="ollama",
        input_tokens=10,
        output_tokens=20,
        raw={},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_01_set_and_pop_summary():
    """set_daily_summary then pop_daily_summary returns the correct dict."""
    ws = make_world("/nonexistent/state.json")
    ws.set_daily_summary("hello", 3)
    result = ws.pop_daily_summary()
    assert result == {"text": "hello", "day": 3}, f"unexpected result: {result!r}"


def test_02_pop_returns_none_when_empty():
    """pop_daily_summary on a fresh WorldState returns None."""
    ws = make_world("/nonexistent/state.json")
    result = ws.pop_daily_summary()
    assert result is None, f"expected None, got {result!r}"


def test_03_pop_clears_the_value():
    """set then pop twice — second pop returns None."""
    ws = make_world("/nonexistent/state.json")
    ws.set_daily_summary("first summary", 1)
    first = ws.pop_daily_summary()
    assert first is not None, "first pop should return the summary"
    second = ws.pop_daily_summary()
    assert second is None, f"second pop should return None, got {second!r}"


def test_04_write_state_excludes_pending_summary():
    """_pending_summary must not appear in the saved state.json."""
    with tempfile.TemporaryDirectory() as td:
        state_path = os.path.join(td, "state.json")
        ws = make_world(state_path)
        ws.set_daily_summary("some summary", 2)
        ws.save()
        saved = json.loads(pathlib.Path(state_path).read_text(encoding="utf-8"))
        assert "_pending_summary" not in saved, (
            f"_pending_summary should not be in state.json, but found: {saved.get('_pending_summary')!r}"
        )


async def test_05_generate_daily_summary_saves_file():
    """_generate_daily_summary writes daily_log_day_1.txt when LLM succeeds."""
    with tempfile.TemporaryDirectory() as td:
        state_path = os.path.join(td, "state.json")
        ws = make_world(state_path)

        # Add some events so the summary runs
        ws._state["events"] = [
            {"time": "6:00am Day 1", "text": "Arjun woke up"},
            {"time": "7:00am Day 1", "text": "Priya went to cyber_city"},
        ]

        sim = SimulationLoop(ws)
        output_dir = pathlib.Path(td)

        stub_text = "It was a busy day in Gurgaon."
        stub_response = make_stub_response(stub_text)

        with patch("engine.llm.call_llm", new=AsyncMock(return_value=stub_response)):
            await sim._generate_daily_summary(1, output_dir=output_dir)

        log_path = output_dir / "daily_log_day_1.txt"
        assert log_path.exists(), f"Log file not created at {log_path}"
        content = log_path.read_text(encoding="utf-8")
        assert content == stub_text, f"unexpected content: {content!r}"


async def test_06_generate_daily_summary_no_events_skips():
    """_generate_daily_summary returns without writing a file when events is empty."""
    with tempfile.TemporaryDirectory() as td:
        state_path = os.path.join(td, "state.json")
        ws = make_world(state_path)
        ws._state["events"] = []

        sim = SimulationLoop(ws)
        output_dir = pathlib.Path(td)

        with patch("engine.llm.call_llm", new=AsyncMock()) as mock_llm:
            await sim._generate_daily_summary(1, output_dir=output_dir)

        # LLM should never have been called
        mock_llm.assert_not_called()

        # No log file should exist
        log_path = output_dir / "daily_log_day_1.txt"
        assert not log_path.exists(), "Log file should not be created when events is empty"


async def test_07_generate_daily_summary_sets_pending():
    """After a successful LLM call, pop_daily_summary returns the summary."""
    with tempfile.TemporaryDirectory() as td:
        state_path = os.path.join(td, "state.json")
        ws = make_world(state_path)
        ws._state["events"] = [
            {"time": "9:00am Day 1", "text": "Rahul visited the dhaba"},
        ]

        sim = SimulationLoop(ws)
        output_dir = pathlib.Path(td)

        stub_text = "Rahul had a productive visit to the dhaba today."
        stub_response = make_stub_response(stub_text)

        with patch("engine.llm.call_llm", new=AsyncMock(return_value=stub_response)):
            await sim._generate_daily_summary(1, output_dir=output_dir)

        pending = ws.pop_daily_summary()
        assert pending is not None, "pop_daily_summary should return the pending summary"
        assert pending["text"] == stub_text, f"unexpected text: {pending['text']!r}"
        assert pending["day"] == 1, f"unexpected day: {pending['day']!r}"


def test_08_day_rollover_detected_in_tick():
    """advance_time from sim_time=1425 by 15 minutes increments day to 2."""
    ws = make_world("/nonexistent/state.json")
    ws._state["sim_time"] = 1425
    ws._state["day"] = 1

    ws.advance_time(15)

    assert ws._state["day"] == 2, (
        f"expected day=2 after midnight rollover, got {ws._state['day']}"
    )
    assert ws._state["sim_time"] == 0, (
        f"expected sim_time=0 after rollover, got {ws._state['sim_time']}"
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    ("1.  set_daily_summary + pop_daily_summary round-trip",          test_01_set_and_pop_summary),
    ("2.  pop_daily_summary returns None on fresh WorldState",         test_02_pop_returns_none_when_empty),
    ("3.  Second pop returns None (value cleared after first pop)",    test_03_pop_clears_the_value),
    ("4.  _write_state excludes _pending_summary from state.json",    test_04_write_state_excludes_pending_summary),
    ("5.  _generate_daily_summary saves log file on LLM success",     test_05_generate_daily_summary_saves_file),
    ("6.  _generate_daily_summary skips when no events",              test_06_generate_daily_summary_no_events_skips),
    ("7.  _generate_daily_summary sets _pending_summary via world",   test_07_generate_daily_summary_sets_pending),
    ("8.  advance_time detects midnight rollover (1425 + 15 -> day 2)", test_08_day_rollover_detected_in_tick),
]


if __name__ == "__main__":
    print("=" * 70)
    print("Story 7.2 -- Daily Summary Notification Tests")
    print("=" * 70)

    for test_name, test_fn in TESTS:
        run(test_name, test_fn)

    print()
    print("=" * 70)
    passed = sum(1 for _, ok_, _ in results if ok_)
    failed = sum(1 for _, ok_, _ in results if not ok_)
    print(f"Results: {passed}/{len(results)} passed, {failed} failed")
    print("=" * 70)

    if failed:
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
        sys.exit(0)
