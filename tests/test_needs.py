"""
Story 3.1 — Needs Decay System Tests
Verifies engine/needs.py behaviour using a real WorldState (no mocking).

Run with:
    .venv/Scripts/python.exe tests/test_needs.py
"""

import asyncio
import os
import sys

# Ensure project root is on sys.path so `engine` can be imported
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Import world first so we can reload it between tests that mutate state
from engine.tools import world
from engine.needs import decay_needs, decay_all_agents, get_needs_warnings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

STATE_PATH = os.path.join(ROOT, "world", "state.json")
MAP_PATH   = os.path.join(ROOT, "world", "map.json")

results = []


def run_test(name: str, fn):
    """Execute a test function and record PASS / FAIL."""
    try:
        fn()
        results.append((name, True, None))
        print(f"  PASS  {name}")
    except Exception as exc:
        results.append((name, False, str(exc)))
        print(f"  FAIL  {name}")
        print(f"        {exc}")


def reload_world():
    """Reload fresh state from disk so each test starts from a clean slate."""
    world.load()


# ---------------------------------------------------------------------------
# Individual tests
# ---------------------------------------------------------------------------

def test_01_one_hour_decay_hunger_energy():
    """
    decay_needs('arjun', 60) — after 1 game hour, hunger increases by ~8,
    energy decreases by ~5.
    """
    reload_world()
    initial = world.get_agent("arjun")
    initial_hunger = initial["hunger"]   # 20.0
    initial_energy = initial["energy"]   # 90.0

    result = asyncio.run(decay_needs("arjun", 60.0))

    # Expected deltas: +8.0 hunger, -5.0 energy
    assert abs(result["hunger_delta"] - 8.0) < 0.001, \
        f"Expected hunger_delta ≈ 8.0, got {result['hunger_delta']}"
    assert abs(result["energy_delta"] - (-5.0)) < 0.001, \
        f"Expected energy_delta ≈ -5.0, got {result['energy_delta']}"

    # Verify actual new values (accounting for initial state)
    expected_hunger = min(100.0, initial_hunger + 8.0)
    expected_energy = max(0.0, initial_energy - 5.0)
    assert abs(result["hunger"] - expected_hunger) < 0.001, \
        f"Expected hunger ≈ {expected_hunger}, got {result['hunger']}"
    assert abs(result["energy"] - expected_energy) < 0.001, \
        f"Expected energy ≈ {expected_energy}, got {result['energy']}"


def test_02_standard_tick_decay():
    """
    decay_needs('arjun', 15) — standard 15-min tick produces small correct deltas.
    hunger_delta = 8/60*15 = 2.0, energy_delta = -5/60*15 = -1.25
    """
    reload_world()
    initial = world.get_agent("arjun")
    initial_hunger = initial["hunger"]
    initial_energy = initial["energy"]

    result = asyncio.run(decay_needs("arjun", 15.0))

    expected_hunger_delta = 8.0 / 60.0 * 15.0   # 2.0
    expected_energy_delta = -(5.0 / 60.0 * 15.0) # -1.25

    assert abs(result["hunger_delta"] - expected_hunger_delta) < 0.001, \
        f"Expected hunger_delta ≈ {expected_hunger_delta}, got {result['hunger_delta']}"
    assert abs(result["energy_delta"] - expected_energy_delta) < 0.001, \
        f"Expected energy_delta ≈ {expected_energy_delta}, got {result['energy_delta']}"

    expected_new_hunger = min(100.0, initial_hunger + expected_hunger_delta)
    expected_new_energy = max(0.0,   initial_energy + expected_energy_delta)
    assert abs(result["hunger"] - expected_new_hunger) < 0.001, \
        f"Expected hunger ≈ {expected_new_hunger}, got {result['hunger']}"
    assert abs(result["energy"] - expected_new_energy) < 0.001, \
        f"Expected energy ≈ {expected_new_energy}, got {result['energy']}"


def test_03_hunger_clamps_at_100():
    """
    Hunger clamps at 100: set arjun hunger to 98, decay 60 min → stays at 100.
    """
    reload_world()
    # Set hunger to 98 (would exceed 100 after +8 delta)
    asyncio.run(world.update_agent("arjun", {"hunger": 98.0}))
    assert world.get_agent("arjun")["hunger"] == 98.0

    result = asyncio.run(decay_needs("arjun", 60.0))

    assert result["hunger"] == 100.0, \
        f"Expected hunger clamped to 100.0, got {result['hunger']}"


def test_04_energy_clamps_at_0():
    """
    Energy clamps at 0: set arjun energy to 3, decay 60 min → stays at 0.
    """
    reload_world()
    # Set energy to 3 (would go below 0 after -5 delta)
    asyncio.run(world.update_agent("arjun", {"energy": 3.0}))
    assert world.get_agent("arjun")["energy"] == 3.0

    result = asyncio.run(decay_needs("arjun", 60.0))

    assert result["energy"] == 0.0, \
        f"Expected energy clamped to 0.0, got {result['energy']}"


def test_05_warning_when_hunger_critical():
    """
    Warning generated when hunger > 80: set hunger to 75, decay 60 min → warning present.
    After decay: 75 + 8 = 83 > 80 → should trigger URGENT hunger warning.
    """
    reload_world()
    asyncio.run(world.update_agent("arjun", {"hunger": 75.0}))

    result = asyncio.run(decay_needs("arjun", 60.0))

    # 75 + 8 = 83 > 80 → URGENT warning expected
    assert result["hunger"] > 80.0, \
        f"Expected hunger > 80 after decay, got {result['hunger']}"
    assert len(result["warnings"]) > 0, \
        "Expected at least one warning when hunger > 80"
    hunger_warning = any("hungry" in w.lower() or "starv" in w.lower()
                         for w in result["warnings"])
    assert hunger_warning, \
        f"Expected hunger warning in warnings, got: {result['warnings']}"


def test_06_warning_when_energy_critical():
    """
    Warning generated when energy < 20: set energy to 25, decay 60 min → warning present.
    After decay: 25 - 5 = 20, which equals ENERGY_CRITICAL (20) — not below it.
    Use energy=24 → 24 - 5 = 19 < 20 → triggers warning.
    """
    reload_world()
    asyncio.run(world.update_agent("arjun", {"energy": 24.0}))

    result = asyncio.run(decay_needs("arjun", 60.0))

    # 24 - 5 = 19 < 20 → URGENT warning expected
    assert result["energy"] < 20.0, \
        f"Expected energy < 20 after decay, got {result['energy']}"
    assert len(result["warnings"]) > 0, \
        "Expected at least one warning when energy < 20"
    energy_warning = any("exhaust" in w.lower() or "collapse" in w.lower()
                         for w in result["warnings"])
    assert energy_warning, \
        f"Expected energy warning in warnings, got: {result['warnings']}"


def test_07_no_warnings_when_moderate():
    """
    No warnings when needs are moderate: set hunger=30, energy=60 → no warnings after small decay.
    After 15-min tick: hunger = 32, energy = 58.75 — both within safe range.
    """
    reload_world()
    asyncio.run(world.update_agent("arjun", {"hunger": 30.0, "energy": 60.0, "mood": 65.0}))

    result = asyncio.run(decay_needs("arjun", 15.0))

    assert result["warnings"] == [], \
        f"Expected no warnings with moderate needs, got: {result['warnings']}"


def test_08_decay_all_agents_keys():
    """
    decay_all_agents(15) returns dict with all 10 agent names as keys.
    """
    reload_world()
    expected_agents = {
        "arjun", "priya", "rahul", "kavya", "suresh",
        "neha", "vikram", "deepa", "rohan", "anita",
    }

    results_dict = asyncio.run(decay_all_agents(15.0))

    assert isinstance(results_dict, dict), \
        f"decay_all_agents must return a dict, got {type(results_dict)}"
    assert set(results_dict.keys()) == expected_agents, \
        f"Expected agent keys {expected_agents}, got {set(results_dict.keys())}"


def test_09_decay_all_agents_hunger_increased():
    """
    decay_all_agents(15) — all 10 agents' hunger values increased after call.
    """
    reload_world()
    # Record initial hunger for all agents
    initial_hunger = {
        name: world.get_agent(name)["hunger"]
        for name in ["arjun", "priya", "rahul", "kavya", "suresh",
                     "neha", "vikram", "deepa", "rohan", "anita"]
    }

    results_dict = asyncio.run(decay_all_agents(15.0))

    for name, result in results_dict.items():
        if initial_hunger[name] < 100.0:
            # Hunger should have increased (unless already at 100)
            assert result["hunger"] > initial_hunger[name], \
                f"Expected {name}'s hunger to increase from {initial_hunger[name]}, got {result['hunger']}"
        else:
            assert result["hunger"] == 100.0, \
                f"Expected {name}'s hunger to stay at 100, got {result['hunger']}"


def test_10_get_needs_warnings_with_warnings():
    """
    get_needs_warnings({..., 'warnings': ['URGENT: Very hungry']}) returns string containing 'URGENT'.
    """
    decay_result = {
        "agent_name": "arjun",
        "hunger_delta": 8.0,
        "energy_delta": -5.0,
        "mood_delta": 0.0,
        "hunger": 85.0,
        "energy": 60.0,
        "mood": 65.0,
        "warnings": ["URGENT: Very hungry — must find food soon"],
    }

    output = get_needs_warnings(decay_result)

    assert isinstance(output, str), f"get_needs_warnings must return str, got {type(output)}"
    assert "URGENT" in output, f"Expected 'URGENT' in output, got: {repr(output)}"
    assert output.startswith("\n=== URGENT NEEDS ===\n"), \
        f"Expected output to start with warning header, got: {repr(output)}"


def test_11_get_needs_warnings_empty():
    """
    get_needs_warnings({..., 'warnings': []}) returns empty string.
    """
    decay_result = {
        "agent_name": "arjun",
        "hunger_delta": 2.0,
        "energy_delta": -1.25,
        "mood_delta": 0.0,
        "hunger": 22.0,
        "energy": 88.75,
        "mood": 65.0,
        "warnings": [],
    }

    output = get_needs_warnings(decay_result)

    assert output == "", f"Expected empty string for no warnings, got: {repr(output)}"


def test_12_eight_hours_of_decay():
    """
    After 8 game hours of decay (32 calls × 15 min), check final values:
    - hunger ≈ start(20) + 8*8 = 84 (±5 tolerance)
    - energy ≈ start(90) - 8*5 = 50 (±5 tolerance)
    """
    reload_world()

    # Run 32 ticks of 15-minute decay (8 hours = 8 * 4 = 32 ticks)
    for _ in range(32):
        asyncio.run(decay_needs("arjun", 15.0))

    agent = world.get_agent("arjun")
    final_hunger = agent["hunger"]
    final_energy = agent["energy"]

    # Expected: hunger = 20 + 64 = 84, energy = 90 - 40 = 50
    expected_hunger = 84.0
    expected_energy = 50.0
    tolerance = 5.0

    assert abs(final_hunger - expected_hunger) <= tolerance, \
        f"Expected hunger ≈ {expected_hunger} (±{tolerance}), got {final_hunger}"
    assert abs(final_energy - expected_energy) <= tolerance, \
        f"Expected energy ≈ {expected_energy} (±{tolerance}), got {final_energy}"


# ---------------------------------------------------------------------------
# Test registry
# ---------------------------------------------------------------------------

TESTS = [
    ("1.  1-hour decay: hunger +8, energy -5", test_01_one_hour_decay_hunger_energy),
    ("2.  15-min tick decay: correct small deltas", test_02_standard_tick_decay),
    ("3.  Hunger clamps at 100: set to 98, decay 60 min -> 100", test_03_hunger_clamps_at_100),
    ("4.  Energy clamps at 0: set to 3, decay 60 min -> 0", test_04_energy_clamps_at_0),
    ("5.  Warning when hunger > 80: set to 75, decay 60 min -> warning", test_05_warning_when_hunger_critical),
    ("6.  Warning when energy < 20: set to 24, decay 60 min -> warning", test_06_warning_when_energy_critical),
    ("7.  No warnings with moderate needs (hunger=30, energy=60, 15-min tick)", test_07_no_warnings_when_moderate),
    ("8.  decay_all_agents(15) returns all 10 agent names as keys", test_08_decay_all_agents_keys),
    ("9.  decay_all_agents(15) -- all agents hunger increased", test_09_decay_all_agents_hunger_increased),
    ("10. get_needs_warnings returns string with URGENT when warnings present", test_10_get_needs_warnings_with_warnings),
    ("11. get_needs_warnings returns empty string when warnings list is empty", test_11_get_needs_warnings_empty),
    ("12. 8 hours decay (32 ticks): hunger ~84, energy ~50 (+/-5)", test_12_eight_hours_of_decay),
]

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Reconfigure stdout to UTF-8 so Unicode characters print correctly on
    # Windows terminals that default to cp1252.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 70)
    print("Story 3.1 -- Needs Decay System Tests")
    print("=" * 70)

    for test_name, test_fn in TESTS:
        run_test(test_name, test_fn)

    print()
    print("=" * 70)
    passed  = sum(1 for _, ok, _ in results if ok)
    failed  = sum(1 for _, ok, _ in results if not ok)
    total   = len(results)
    print(f"Results: {passed}/{total} passed, {failed} failed")
    print("=" * 70)

    if failed:
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
        sys.exit(0)
