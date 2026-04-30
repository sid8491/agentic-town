"""
tests/test_narrator.py — Story 10.2 live narrator.

call_llm is mocked everywhere so no live Ollama is required.

Run:
    .venv/Scripts/python.exe tests/test_narrator.py
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from engine.world import WorldState
from engine import narrator as narrator_mod
from engine.narrator import (
    _build_prompt,
    _qualitative_descriptors,
    _soul_one_liner,
    generate_narration,
    get_cached_narration,
    narrator_loop,
)

_pass = 0
_fail = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global _pass, _fail
    status = "PASS" if ok else "FAIL"
    if ok:
        _pass += 1
    else:
        _fail += 1
    extra = f" — {detail}" if detail else ""
    print(f"[{status}] {name}{extra}")


def _mock_response(text: str) -> MagicMock:
    m = MagicMock()
    m.text = text
    m.tool_name = None
    m.tool_args = None
    m.provider = "ollama"
    m.input_tokens = 80
    m.output_tokens = 30
    return m


def _make_world() -> WorldState:
    ws = WorldState(
        state_path=os.path.join(ROOT, "world", "state.json"),
        map_path=os.path.join(ROOT, "world", "map.json"),
    )
    ws.load_or_init()
    return ws


def test_soul_one_liner_returns_first_paragraph():
    text = _soul_one_liner("arjun")
    check(
        "soul one-liner is non-empty and mentions Arjun",
        bool(text) and "Arjun" in text,
        f"text[:60]={text[:60]!r}",
    )


def test_qualitative_descriptors_no_numbers():
    desc = _qualitative_descriptors({
        "energy": 20,
        "hunger": 90,
        "mood": 80,
        "financial_stress": True,
    })
    check(
        "qualitative descriptors include 'tired'",
        "tired" in desc,
        repr(desc),
    )
    check(
        "qualitative descriptors include 'hungry'",
        "hungry" in desc,
        repr(desc),
    )
    check(
        "qualitative descriptors include 'lifted' for high mood",
        "lifted" in desc,
        repr(desc),
    )
    check(
        "qualitative descriptors include 'financially anxious'",
        "financially anxious" in desc,
        repr(desc),
    )
    # No raw numbers should leak into descriptor strings
    joined = " ".join(desc)
    has_digit = any(ch.isdigit() for ch in joined)
    check(
        "descriptors contain no raw digit characters",
        not has_digit,
        repr(joined),
    )


def test_build_prompt_includes_required_fields():
    ws = _make_world()
    a = ws.get_agent("arjun")
    a["last_action"] = "pacing near cyber hub"
    a["location"] = "cyber_hub"
    a["mood"] = 50
    a["energy"] = 80
    a["hunger"] = 30
    prompt = _build_prompt(ws, "arjun", ["[6:00am Day 1] arjun moved to cyber_hub"])
    for needle in ("Protagonist: arjun", "Last action: pacing", "Location: cyber_hub", "Recent events"):
        check(
            f"prompt contains: {needle}",
            needle in prompt,
            prompt[:160],
        )


def test_generate_narration_returns_text():
    ws = _make_world()
    mock = _mock_response("Arjun stares at his laptop, jaw tight.")
    with patch("engine.narrator.call_llm", new=AsyncMock(return_value=mock)):
        result = asyncio.run(generate_narration(ws, [], "arjun"))
    check(
        "generate_narration returns the LLM text",
        result == "Arjun stares at his laptop, jaw tight.",
        f"got={result!r}",
    )


def test_generate_narration_returns_empty_on_failure():
    ws = _make_world()
    async def boom(*args, **kwargs):
        raise RuntimeError("LLM is down")
    with patch("engine.narrator.call_llm", new=boom):
        result = asyncio.run(generate_narration(ws, [], "arjun"))
    check(
        "generate_narration returns '' when LLM raises",
        result == "",
        f"got={result!r}",
    )


def test_narrator_loop_caches_and_skips_redundant_calls():
    """Identical (protagonist, last_action, location) → only one LLM call."""
    ws = _make_world()
    # Stabilise so pick_protagonist returns the same agent across iterations.
    for name, ag in ws.get_all_agents().items():
        ag["mood"] = 50
        ag["energy"] = 80
        ag["hunger"] = 30
        ag["financial_stress"] = False
        ag["last_action"] = "idle"
    ws._state["events"] = []
    ws._state["shared_plans"] = []

    call_count = {"n": 0}
    async def fake_call_llm(*args, **kwargs):
        call_count["n"] += 1
        return _mock_response(f"narration #{call_count['n']}")

    async def run_briefly():
        with patch("engine.narrator.call_llm", new=fake_call_llm):
            stop = asyncio.Event()
            # interval=0 → asyncio.sleep(0) yields control without blocking.
            task = asyncio.create_task(narrator_loop(ws, interval=0, stop_event=stop))
            # Let the loop spin a handful of iterations.
            for _ in range(20):
                await asyncio.sleep(0)
            stop.set()
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    asyncio.run(run_briefly())

    cached = get_cached_narration(ws)
    check(
        "narrator_loop wrote a narration to the cache",
        bool(cached["narration"]),
        f"cache={cached}",
    )
    check(
        "narrator_loop made exactly one LLM call across iterations with same key",
        call_count["n"] == 1,
        f"call_count={call_count['n']}",
    )


def test_narrator_loop_calls_again_when_state_changes():
    """When last_action changes, narrator_loop re-issues an LLM call."""
    ws = _make_world()
    for name, ag in ws.get_all_agents().items():
        ag["mood"] = 50
        ag["energy"] = 80
        ag["hunger"] = 30
        ag["financial_stress"] = False
        ag["last_action"] = "idle"
    ws._state["events"] = []
    ws._state["shared_plans"] = []

    call_count = {"n": 0}
    async def fake_call_llm(*args, **kwargs):
        call_count["n"] += 1
        return _mock_response(f"narration #{call_count['n']}")

    async def run_with_change():
        with patch("engine.narrator.call_llm", new=fake_call_llm):
            stop = asyncio.Event()
            task = asyncio.create_task(narrator_loop(ws, interval=0, stop_event=stop))
            for _ in range(10):
                await asyncio.sleep(0)
            # Mutate the protagonist's last_action — pick_protagonist still
            # returns the same agent (alphabetical tiebreak when all neutral)
            # but the cache key changes so a fresh LLM call must fire.
            pick_name = "anita"
            ws.get_agent(pick_name)["last_action"] = "buying chai"
            for _ in range(20):
                await asyncio.sleep(0)
            stop.set()
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    asyncio.run(run_with_change())

    check(
        "narrator_loop made >=2 LLM calls when cache key changed",
        call_count["n"] >= 2,
        f"call_count={call_count['n']}",
    )


def test_get_cached_narration_default_shape():
    """When nothing has been cached, get_cached_narration still returns the right shape."""
    ws = _make_world()
    ws._state.pop("_narration", None)
    cached = get_cached_narration(ws)
    check(
        "default cached narration has all keys with empty values",
        cached == {"narration": "", "protagonist": "", "ts": 0.0},
        f"got={cached}",
    )


def test_narration_cache_not_persisted_to_disk():
    """The underscore-prefixed _narration key must not survive a save round-trip."""
    import tempfile, json
    td = tempfile.TemporaryDirectory()
    try:
        state_path = os.path.join(td.name, "state.json")
        ws = WorldState(
            state_path=state_path,
            map_path=os.path.join(ROOT, "world", "map.json"),
        )
        ws.load_or_init()
        ws._state["_narration"] = {"text": "x", "protagonist": "arjun", "ts": 1.0}
        ws.save()
        with open(state_path, "r", encoding="utf-8") as f:
            persisted = json.load(f)
        check(
            "_narration key is excluded from state.json",
            "_narration" not in persisted,
            f"keys={list(persisted.keys())[:8]}",
        )
    finally:
        td.cleanup()


if __name__ == "__main__":
    print("=" * 60)
    print("Story 10.2 — narrator tests")
    print("=" * 60)
    print()
    test_soul_one_liner_returns_first_paragraph()
    test_qualitative_descriptors_no_numbers()
    test_build_prompt_includes_required_fields()
    test_generate_narration_returns_text()
    test_generate_narration_returns_empty_on_failure()
    test_narrator_loop_caches_and_skips_redundant_calls()
    test_narrator_loop_calls_again_when_state_changes()
    test_get_cached_narration_default_shape()
    test_narration_cache_not_persisted_to_disk()
    print()
    print("=" * 60)
    print(f"Results: {_pass} passed, {_fail} failed")
    print("=" * 60)
    if _fail > 0:
        sys.exit(1)
