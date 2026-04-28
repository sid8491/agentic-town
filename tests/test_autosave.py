"""
Story 5.1 — Auto-Save World State Tests

Verifies:
  - load_or_init loads existing state.json when file is present
  - load_or_init creates fresh default state when file is absent
  - Fresh state has all 10 agents with required keys
  - Fresh agent locations are all valid map locations
  - save() / load() round-trip preserves data correctly
  - save_async() works inside an asyncio event loop
  - _autosave_loop is an async coroutine (called by _loop)
  - _build_fresh_state produces correct schema

Run with:
    .venv/Scripts/python.exe tests/test_autosave.py
"""

import asyncio
import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT     = pathlib.Path(__file__).parent.parent
MAP_PATH = ROOT / "world" / "map.json"

from engine.world import WorldState, SimulationLoop

results = []

REQUIRED_AGENT_KEYS = {
    "location", "hunger", "energy", "mood",
    "coins", "inventory", "inbox", "last_action",
}

REQUIRED_STATE_KEYS = {
    "sim_time", "day", "paused", "speed",
    "llm_primary", "events", "daily_events", "agents",
}

ALL_AGENTS = {
    "arjun", "priya", "rahul", "kavya", "suresh",
    "neha", "vikram", "deepa", "rohan", "anita",
}


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
    return WorldState(state_path=state_path, map_path=str(MAP_PATH))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_01_load_or_init_loads_existing():
    """load_or_init loads state.json when it already exists."""
    existing = ROOT / "world" / "state.json"
    ws = make_world(str(existing))
    ws.load_or_init()
    # Should have loaded the live agents dict
    assert "agents" in ws._state
    assert len(ws._state["agents"]) == 10


def test_02_load_or_init_creates_fresh_when_missing():
    """load_or_init builds fresh state when state.json is absent."""
    with tempfile.TemporaryDirectory() as td:
        missing = os.path.join(td, "state.json")
        ws = make_world(missing)
        ws.load_or_init()

        assert os.path.exists(missing), "Should have written state.json"
        assert "agents" in ws._state
        assert len(ws._state["agents"]) == 10


def test_03_fresh_state_has_all_agents():
    """_build_fresh_state includes all 10 agents by name."""
    ws = make_world("/nonexistent/state.json")
    ws._build_fresh_state()
    missing = ALL_AGENTS - set(ws._state["agents"].keys())
    assert not missing, f"Missing agents: {missing}"


def test_04_fresh_state_agent_keys():
    """Every agent in a fresh state has all required keys."""
    ws = make_world("/nonexistent/state.json")
    ws._build_fresh_state()
    for name, agent in ws._state["agents"].items():
        missing = REQUIRED_AGENT_KEYS - set(agent.keys())
        assert not missing, f"Agent {name} missing keys: {missing}"


def test_05_fresh_state_locations_in_map():
    """All fresh-state starting locations exist in map.json."""
    map_data = json.loads(MAP_PATH.read_text())
    valid_locs = {loc["id"] for loc in map_data["locations"]}
    ws = make_world("/nonexistent/state.json")
    ws._build_fresh_state()
    for name, agent in ws._state["agents"].items():
        loc = agent["location"]
        assert loc in valid_locs, f"{name} starts at unknown location: {loc!r}"


def test_06_fresh_state_schema():
    """Top-level keys of a fresh state match the required schema."""
    ws = make_world("/nonexistent/state.json")
    ws._build_fresh_state()
    missing = REQUIRED_STATE_KEYS - set(ws._state.keys())
    assert not missing, f"Top-level state missing keys: {missing}"
    assert ws._state["day"] == 1
    assert ws._state["sim_time"] == 360
    assert ws._state["paused"] is False


def test_07_save_load_round_trip():
    """save() then load() preserves the sim_time and agent locations."""
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "state.json")
        ws = make_world(path)
        ws.load_or_init()

        ws._state["sim_time"] = 999
        ws._state["agents"]["arjun"]["location"] = "dhaba"
        ws.save()

        ws2 = make_world(path)
        ws2.load_or_init()
        assert ws2._state["sim_time"] == 999, "sim_time not persisted"
        assert ws2._state["agents"]["arjun"]["location"] == "dhaba"


async def test_08_save_async_works():
    """save_async() writes to disk without raising inside asyncio."""
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "state.json")
        ws = make_world(path)
        ws.load_or_init()
        ws._state["day"] = 7
        await ws.save_async()

        saved = json.loads(pathlib.Path(path).read_text())
        assert saved["day"] == 7, "save_async did not persist day"


def test_09_autosave_loop_is_coroutine():
    """SimulationLoop._autosave_loop is an async coroutine function."""
    ws = WorldState(state_path=str(ROOT / "world" / "state.json"),
                    map_path=str(MAP_PATH))
    loop = SimulationLoop(ws)
    assert asyncio.iscoroutinefunction(loop._autosave_loop), (
        "_autosave_loop must be an async def"
    )


def test_10_fresh_state_needs_defaults():
    """Fresh state agent needs start at the expected defaults."""
    ws = make_world("/nonexistent/state.json")
    ws._build_fresh_state()
    for name, agent in ws._state["agents"].items():
        assert agent["hunger"] == 20.0, f"{name} hunger wrong"
        assert agent["energy"] == 90.0, f"{name} energy wrong"
        assert agent["mood"]   == 65.0, f"{name} mood wrong"
        assert agent["inventory"] == [], f"{name} inventory not empty"
        assert agent["inbox"]     == [], f"{name} inbox not empty"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    ("1.  load_or_init loads existing state.json",                    test_01_load_or_init_loads_existing),
    ("2.  load_or_init creates fresh state when file missing",        test_02_load_or_init_creates_fresh_when_missing),
    ("3.  Fresh state includes all 10 agents",                        test_03_fresh_state_has_all_agents),
    ("4.  Fresh state agents have all required keys",                  test_04_fresh_state_agent_keys),
    ("5.  Fresh state locations all exist in map.json",               test_05_fresh_state_locations_in_map),
    ("6.  Fresh state top-level schema is correct",                   test_06_fresh_state_schema),
    ("7.  save() + load_or_init() round-trip preserves data",         test_07_save_load_round_trip),
    ("8.  save_async() writes to disk inside asyncio",                test_08_save_async_works),
    ("9.  _autosave_loop is a coroutine function",                    test_09_autosave_loop_is_coroutine),
    ("10. Fresh state agent needs start at correct defaults",         test_10_fresh_state_needs_defaults),
]


if __name__ == "__main__":
    print("=" * 70)
    print("Story 5.1 -- Auto-Save World State Tests")
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
