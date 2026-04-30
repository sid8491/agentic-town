"""
tests/test_headlines.py — Story 10.10 daily gossip headlines (backend slice).

call_llm is mocked everywhere so no live Ollama is required.

Run:
    .venv/Scripts/python.exe tests/test_headlines.py
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from fastapi.testclient import TestClient

import server
from engine.world import WorldState, SimulationLoop
from engine import headlines as headlines_mod
from engine.headlines import (
    filter_events_for_day,
    generate_headlines,
    get_today_headlines,
    maybe_generate_and_cache,
    parse_headlines,
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
    ws._state.setdefault("daily_headlines", {})
    return ws


# ---------------------------------------------------------------------------
# parse_headlines — handles bullets / numbering / quotes / length cap
# ---------------------------------------------------------------------------

def test_parser_strips_bullets_and_numbers():
    raw = (
        "- Local Founder Spotted Leaving Cyber Hub Alone — Again\n"
        "* Drama at the Dhaba: Two Friends, One Awkward Silence\n"
        "1. Mystery Solved: Why Vikram Skipped His Morning Walk\n"
    )
    parsed = parse_headlines(raw)
    check(
        "parser strips - prefix",
        any("Local Founder Spotted" in h and not h.startswith("-") for h in parsed),
        repr(parsed),
    )
    check(
        "parser strips * prefix",
        any("Drama at the Dhaba" in h and not h.startswith("*") for h in parsed),
        repr(parsed),
    )
    check(
        "parser strips '1.' numbering",
        any("Mystery Solved" in h and not h.startswith("1") for h in parsed),
        repr(parsed),
    )
    check("parser produced 3 headlines", len(parsed) == 3, repr(parsed))


def test_parser_caps_at_three_and_drops_long_lines():
    long_line = "X" * 120
    raw = "\n".join([
        "First headline",
        "Second headline",
        "Third headline",
        "Fourth headline (should be dropped)",
        long_line,
    ])
    parsed = parse_headlines(raw)
    check("parser caps at 3 entries", len(parsed) == 3, repr(parsed))
    check(
        "parser dropped overly long line entirely",
        long_line not in parsed,
        repr(parsed),
    )


def test_parser_handles_empty_or_whitespace():
    check("empty string -> []", parse_headlines("") == [], "")
    check("whitespace-only -> []", parse_headlines("   \n   \n") == [], "")


def test_parser_strips_surrounding_quotes():
    parsed = parse_headlines('"Cheeky Headline One"\n\'Cheeky Headline Two\'')
    check(
        "parser strips double quotes",
        "Cheeky Headline One" in parsed,
        repr(parsed),
    )
    check(
        "parser strips single quotes",
        "Cheeky Headline Two" in parsed,
        repr(parsed),
    )


# ---------------------------------------------------------------------------
# filter_events_for_day
# ---------------------------------------------------------------------------

def test_filter_events_by_day():
    events = [
        {"time": "6:00am Day 1", "text": "a"},
        {"time": "9:30am Day 2", "text": "b"},
        {"time": "11:45pm Day 2", "text": "c"},
        {"time": "12:15am Day 3", "text": "d"},
        {"time": "garbage", "text": "e"},
    ]
    day2 = filter_events_for_day(events, 2)
    check(
        "filter_events_for_day returns only matching day",
        [e["text"] for e in day2] == ["b", "c"],
        repr(day2),
    )


# ---------------------------------------------------------------------------
# generate_headlines — happy / failure paths
# ---------------------------------------------------------------------------

def test_generate_headlines_happy_path():
    events = [{"time": "10:00am Day 1", "text": "arjun met priya at cyber_hub"}]
    souls = {"arjun": "Backend engineer.", "priya": "Founder."}
    raw = (
        "- Local Founder Spotted Leaving Cyber Hub Alone — Again\n"
        "- Drama at the Dhaba: Two Friends, One Awkward Silence\n"
    )
    with patch(
        "engine.headlines.call_llm",
        new=AsyncMock(return_value=_mock_response(raw)),
    ):
        out = asyncio.run(generate_headlines(events, souls))
    check(
        "happy path returns 2 headlines",
        len(out) == 2,
        repr(out),
    )
    check(
        "happy path stripped bullets",
        all(not h.startswith("-") for h in out),
        repr(out),
    )


def test_generate_headlines_returns_empty_on_failure():
    async def boom(*args, **kwargs):
        raise RuntimeError("LLM is down")
    with patch("engine.headlines.call_llm", new=boom):
        out = asyncio.run(generate_headlines(
            [{"time": "10:00am Day 1", "text": "x"}],
            {"arjun": "Engineer."},
        ))
    check("LLM failure -> [] (no crash)", out == [], repr(out))


# ---------------------------------------------------------------------------
# maybe_generate_and_cache — fallback / dedup / persist behaviour
# ---------------------------------------------------------------------------

def test_empty_events_uses_quiet_day_fallback():
    ws = _make_world()
    ws._state["events"] = []
    ws._state["daily_headlines"] = {}
    ws._state["day"] = 1

    called = {"n": 0}
    async def fake_llm(*a, **kw):
        called["n"] += 1
        return _mock_response("nope")

    with patch("engine.headlines.call_llm", new=fake_llm):
        out = asyncio.run(maybe_generate_and_cache(ws, 1))

    check("quiet-day fallback skips LLM", called["n"] == 0, f"calls={called['n']}")
    check(
        "quiet-day fallback returns 1 headline",
        len(out) == 1 and "quiet day" in out[0].lower(),
        repr(out),
    )
    check(
        "quiet-day fallback cached on world",
        ws._state["daily_headlines"]["1"] == out,
        repr(ws._state["daily_headlines"]),
    )


def test_fires_only_once_per_day():
    ws = _make_world()
    ws._state["events"] = [{"time": "10:00am Day 2", "text": "arjun met priya"}]
    ws._state["daily_headlines"] = {}
    ws._state["day"] = 2

    call_count = {"n": 0}
    async def fake_llm(*a, **kw):
        call_count["n"] += 1
        return _mock_response("Headline One\nHeadline Two")

    with patch("engine.headlines.call_llm", new=fake_llm):
        first = asyncio.run(maybe_generate_and_cache(ws, 2))
        second = asyncio.run(maybe_generate_and_cache(ws, 2))

    check(
        "first call hit LLM exactly once",
        call_count["n"] == 1,
        f"calls={call_count['n']}",
    )
    check(
        "second call short-circuits and returns cached value",
        first == second and len(first) >= 1,
        f"first={first} second={second}",
    )


def test_llm_failure_leaves_cache_unset():
    ws = _make_world()
    ws._state["events"] = [{"time": "10:00am Day 3", "text": "arjun met priya"}]
    ws._state["daily_headlines"] = {}
    ws._state["day"] = 3

    async def boom(*a, **kw):
        raise RuntimeError("LLM is down")

    with patch("engine.headlines.call_llm", new=boom):
        out = asyncio.run(maybe_generate_and_cache(ws, 3))

    check("failure path returns []", out == [], repr(out))
    check(
        "failure path leaves daily_headlines[day] unset (so endpoint stays empty)",
        "3" not in ws._state["daily_headlines"],
        repr(ws._state["daily_headlines"]),
    )


def test_get_today_headlines_shape():
    ws = _make_world()
    ws._state["day"] = 5
    ws._state["daily_headlines"] = {"5": ["A", "B"]}
    out = get_today_headlines(ws)
    check(
        "get_today_headlines returns {day, headlines}",
        out == {"day": 5, "headlines": ["A", "B"]},
        repr(out),
    )


def test_get_today_headlines_empty_when_unset():
    ws = _make_world()
    ws._state["day"] = 7
    ws._state["daily_headlines"] = {}
    out = get_today_headlines(ws)
    check(
        "get_today_headlines empty for ungenerated day",
        out == {"day": 7, "headlines": []},
        repr(out),
    )


# ---------------------------------------------------------------------------
# state schema + persistence
# ---------------------------------------------------------------------------

def test_fresh_state_has_daily_headlines_dict():
    import tempfile
    td = tempfile.TemporaryDirectory()
    try:
        state_path = os.path.join(td.name, "state.json")
        ws = WorldState(
            state_path=state_path,
            map_path=os.path.join(ROOT, "world", "map.json"),
        )
        ws.load_or_init()
        check(
            "_build_fresh_state initialises daily_headlines = {}",
            ws._state.get("daily_headlines") == {},
            repr(ws._state.get("daily_headlines")),
        )
    finally:
        td.cleanup()


def test_daily_headlines_persists_to_disk():
    import json
    import tempfile
    td = tempfile.TemporaryDirectory()
    try:
        state_path = os.path.join(td.name, "state.json")
        ws = WorldState(
            state_path=state_path,
            map_path=os.path.join(ROOT, "world", "map.json"),
        )
        ws.load_or_init()
        ws._state["daily_headlines"]["1"] = ["only one"]
        ws.save()
        with open(state_path, "r", encoding="utf-8") as f:
            persisted = json.load(f)
        check(
            "daily_headlines round-trips through state.json",
            persisted.get("daily_headlines", {}).get("1") == ["only one"],
            repr(persisted.get("daily_headlines")),
        )
    finally:
        td.cleanup()


# ---------------------------------------------------------------------------
# SimulationLoop hook — fires once when sim_time crosses 1080
# ---------------------------------------------------------------------------

async def _async_test_loop_fires_at_18_once():
    import tempfile
    td = tempfile.TemporaryDirectory()
    try:
        state_path = os.path.join(td.name, "state.json")
        ws = WorldState(
            state_path=state_path,
            map_path=os.path.join(ROOT, "world", "map.json"),
        )
        ws.load_or_init()
        ws._state["sim_time"] = 1065  # 17:45
        ws._state["daily_headlines"] = {}

        loop = SimulationLoop(ws)
        called = {"day": None, "n": 0}

        async def fake_run(day: int):
            called["day"] = day
            called["n"] += 1
            ws._state["daily_headlines"][str(day)] = ["x"]

        loop._run_daily_headlines = fake_run  # type: ignore[assignment]

        with patch("engine.agent.AgentRunner.tick", new_callable=AsyncMock):
            with patch("engine.needs.decay_all_agents", new_callable=AsyncMock):
                await loop._tick()  # 1065 -> 1080: should fire
                # Yield so the create_task'd hook runs.
                for _ in range(5):
                    await asyncio.sleep(0)
                await loop._tick()  # 1080 -> 1095: cache already set -> skip
                for _ in range(5):
                    await asyncio.sleep(0)

        check(
            "loop hook fired once when sim_time crossed 18:00",
            called["n"] == 1 and called["day"] == ws._state["day"],
            f"called={called} day={ws._state['day']}",
        )
    finally:
        td.cleanup()


def test_loop_fires_at_18_once():
    asyncio.run(_async_test_loop_fires_at_18_once())


async def _async_test_loop_does_not_fire_before_18():
    import tempfile
    td = tempfile.TemporaryDirectory()
    try:
        state_path = os.path.join(td.name, "state.json")
        ws = WorldState(
            state_path=state_path,
            map_path=os.path.join(ROOT, "world", "map.json"),
        )
        ws.load_or_init()
        ws._state["sim_time"] = 600  # 10:00am
        ws._state["daily_headlines"] = {}

        loop = SimulationLoop(ws)
        called = {"n": 0}

        async def fake_run(day: int):
            called["n"] += 1

        loop._run_daily_headlines = fake_run  # type: ignore[assignment]

        with patch("engine.agent.AgentRunner.tick", new_callable=AsyncMock):
            with patch("engine.needs.decay_all_agents", new_callable=AsyncMock):
                await loop._tick()
                for _ in range(3):
                    await asyncio.sleep(0)

        check(
            "hook does not fire before 18:00",
            called["n"] == 0,
            f"calls={called['n']}",
        )
    finally:
        td.cleanup()


def test_loop_does_not_fire_before_18():
    asyncio.run(_async_test_loop_does_not_fire_before_18())


# ---------------------------------------------------------------------------
# Server endpoint
# ---------------------------------------------------------------------------

def test_server_endpoint_returns_today_headlines():
    import tempfile
    td = tempfile.TemporaryDirectory()
    try:
        state_path = os.path.join(td.name, "state.json")
        ws = WorldState(
            state_path=state_path,
            map_path=os.path.join(ROOT, "world", "map.json"),
        )
        ws.load_or_init()
        ws._state["day"] = 4
        ws._state["daily_headlines"] = {"4": ["one", "two"]}
        server.set_world(ws)

        client = TestClient(server.app)
        r = client.get("/api/headlines/today")
        check(
            "endpoint returns 200",
            r.status_code == 200,
            f"status={r.status_code}",
        )
        body = r.json()
        check(
            "endpoint returns today's headlines",
            body == {"day": 4, "headlines": ["one", "two"]},
            repr(body),
        )

        ws._state["day"] = 5
        r2 = client.get("/api/headlines/today")
        body2 = r2.json()
        check(
            "endpoint returns empty list when day not yet generated",
            body2 == {"day": 5, "headlines": []},
            repr(body2),
        )
    finally:
        td.cleanup()


if __name__ == "__main__":
    print("=" * 60)
    print("Story 10.10 — headlines tests")
    print("=" * 60)
    print()
    test_parser_strips_bullets_and_numbers()
    test_parser_caps_at_three_and_drops_long_lines()
    test_parser_handles_empty_or_whitespace()
    test_parser_strips_surrounding_quotes()
    test_filter_events_by_day()
    test_generate_headlines_happy_path()
    test_generate_headlines_returns_empty_on_failure()
    test_empty_events_uses_quiet_day_fallback()
    test_fires_only_once_per_day()
    test_llm_failure_leaves_cache_unset()
    test_get_today_headlines_shape()
    test_get_today_headlines_empty_when_unset()
    test_fresh_state_has_daily_headlines_dict()
    test_daily_headlines_persists_to_disk()
    test_loop_fires_at_18_once()
    test_loop_does_not_fire_before_18()
    test_server_endpoint_returns_today_headlines()
    print()
    print("=" * 60)
    print(f"Results: {_pass} passed, {_fail} failed")
    print("=" * 60)
    if _fail > 0:
        sys.exit(1)
