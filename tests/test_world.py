"""
Story 1.4 — WorldState Tests
Verifies engine/world.py WorldState class behaviour.

Run with:
    .venv/Scripts/python.exe tests/test_world.py
"""

import asyncio
import os
import sys

# Ensure project root is on sys.path so `engine` can be imported
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.world import WorldState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

STATE_PATH = os.path.join(ROOT, "world", "state.json")
MAP_PATH = os.path.join(ROOT, "world", "map.json")

results = []


def run_test(name, fn):
    """Execute a test function and record PASS / FAIL."""
    try:
        fn()
        results.append((name, True, None))
        print(f"  PASS  {name}")
    except Exception as exc:
        results.append((name, False, str(exc)))
        print(f"  FAIL  {name}")
        print(f"        {exc}")


def make_world() -> WorldState:
    """Create and load a fresh WorldState for each test."""
    ws = WorldState(state_path=STATE_PATH, map_path=MAP_PATH)
    ws.load()
    return ws


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_01_loads_without_error():
    """WorldState loads without raising any exception."""
    ws = make_world()
    assert ws._state, "State dict must be non-empty after load()"
    assert ws._map, "Map dict must be non-empty after load()"


def test_02_get_time_structure():
    """get_time() returns dict with required keys and correct types."""
    ws = make_world()
    t = ws.get_time()
    assert isinstance(t, dict), "get_time() must return a dict"
    assert "day" in t, "get_time() result must have 'day'"
    assert "sim_time" in t, "get_time() result must have 'sim_time'"
    assert "time_str" in t, "get_time() result must have 'time_str'"
    assert "paused" in t, "get_time() result must have 'paused'"
    assert isinstance(t["day"], int), "'day' must be an int"
    assert isinstance(t["sim_time"], int), "'sim_time' must be an int"
    assert isinstance(t["time_str"], str), "'time_str' must be a str"
    assert isinstance(t["paused"], bool), "'paused' must be a bool"


def test_03_time_to_str_conversions():
    """time_to_str() converts sim_time (minutes) to correct 12-hour format."""
    ws = make_world()
    assert ws.time_to_str(0) == "12:00am", f"Expected '12:00am', got '{ws.time_to_str(0)}'"
    assert ws.time_to_str(360) == "6:00am",  f"Expected '6:00am', got '{ws.time_to_str(360)}'"
    assert ws.time_to_str(780) == "1:00pm",  f"Expected '1:00pm', got '{ws.time_to_str(780)}'"
    assert ws.time_to_str(1380) == "11:00pm", f"Expected '11:00pm', got '{ws.time_to_str(1380)}'"
    # Extra: noon and minute-granularity
    assert ws.time_to_str(720) == "12:00pm", f"Expected '12:00pm', got '{ws.time_to_str(720)}'"
    assert ws.time_to_str(390) == "6:30am",  f"Expected '6:30am', got '{ws.time_to_str(390)}'"


def test_04_get_agent_arjun():
    """get_agent('arjun') returns dict with all required keys."""
    ws = make_world()
    agent = ws.get_agent("arjun")
    assert isinstance(agent, dict), "Agent must be a dict"
    required = {"location", "hunger", "energy", "mood", "coins", "inventory", "inbox"}
    missing = required - set(agent.keys())
    assert not missing, f"Agent 'arjun' missing keys: {missing}"


def test_05_get_all_agents_returns_10():
    """get_all_agents() returns all 10 agents."""
    ws = make_world()
    agents = ws.get_all_agents()
    assert isinstance(agents, dict), "get_all_agents() must return a dict"
    assert len(agents) == 10, f"Expected 10 agents, got {len(agents)}"


def test_06_get_nearby_agents_arjun():
    """
    get_nearby_agents('arjun') returns agents at the same location.
    arjun, kavya, and deepa all start at 'apartment', so arjun's
    nearby list must contain both kavya and deepa.
    """
    ws = make_world()
    nearby = ws.get_nearby_agents("arjun")
    assert isinstance(nearby, list), "get_nearby_agents() must return a list"
    assert "arjun" not in nearby, "get_nearby_agents() must exclude self"
    assert "kavya" in nearby, f"Expected 'kavya' in nearby, got {nearby}"
    assert "deepa" in nearby, f"Expected 'deepa' in nearby, got {nearby}"


def test_07_get_location_cyber_hub():
    """get_location('cyber_hub') returns dict with required fields."""
    ws = make_world()
    loc = ws.get_location("cyber_hub")
    assert isinstance(loc, dict), "Location must be a dict"
    required = {"id", "name", "type", "connected_to", "services", "tile_x", "tile_y"}
    missing = required - set(loc.keys())
    assert not missing, f"cyber_hub missing fields: {missing}"
    assert loc["id"] == "cyber_hub"


def test_08_dhaba_has_eat_cheap():
    """location_has_service('dhaba', 'eat_cheap') returns True."""
    ws = make_world()
    assert ws.location_has_service("dhaba", "eat_cheap"), \
        "'dhaba' should offer 'eat_cheap'"


def test_09_park_does_not_have_work():
    """location_has_service('park', 'work') returns False."""
    ws = make_world()
    assert not ws.location_has_service("park", "work"), \
        "'park' should not offer 'work'"


def test_10_connected_locations_apartment():
    """get_connected_locations('apartment') returns the correct list."""
    ws = make_world()
    connected = ws.get_connected_locations("apartment")
    assert isinstance(connected, list), "connected_to must be a list"
    # From map.json: apartment → ["metro", "sector29"]
    assert set(connected) == {"metro", "sector29"}, \
        f"Expected {{'metro', 'sector29'}}, got {set(connected)}"


def test_11_move_agent_arjun_to_metro():
    """
    move_agent('arjun', 'metro') succeeds because metro is in apartment's
    connected_to list, and arjun starts at apartment.
    """
    ws = make_world()
    result = asyncio.run(ws.move_agent("arjun", "metro"))
    assert result is True, "move_agent should return True for a valid connected move"
    assert ws.get_agent_location("arjun") == "metro", \
        f"arjun should now be at 'metro', got '{ws.get_agent_location('arjun')}'"


def test_12_move_agent_arjun_invalid_from_metro():
    """
    After moving arjun to metro, move_agent('arjun', 'sector29') fails
    because sector29 is NOT in metro's connected_to list
    (metro connects to: apartment, cyber_city, cyber_hub).
    """
    ws = make_world()
    # First move arjun to metro (valid)
    asyncio.run(ws.move_agent("arjun", "metro"))
    assert ws.get_agent_location("arjun") == "metro"

    # Now try to jump to sector29 which is not connected from metro
    result = asyncio.run(ws.move_agent("arjun", "sector29"))
    assert result is False, \
        "move_agent should return False: sector29 is not connected to metro"
    assert ws.get_agent_location("arjun") == "metro", \
        "arjun's location should remain 'metro' after a failed move"


def test_13_update_needs_clamping():
    """
    update_needs clamps hunger to [0, 100].
    Set hunger to 95, apply +10 delta → result must be 100, not 105.
    """
    ws = make_world()
    # Directly set arjun's hunger to 95 for test setup
    ws._state["agents"]["arjun"]["hunger"] = 95.0
    asyncio.run(ws.update_needs("arjun", hunger_delta=10.0, energy_delta=0.0))
    hunger = ws.get_agent("arjun")["hunger"]
    assert hunger == 100.0, f"Expected hunger clamped to 100.0, got {hunger}"

    # Also verify clamping at 0
    ws._state["agents"]["arjun"]["energy"] = 5.0
    asyncio.run(ws.update_needs("arjun", hunger_delta=0.0, energy_delta=-20.0))
    energy = ws.get_agent("arjun")["energy"]
    assert energy == 0.0, f"Expected energy clamped to 0.0, got {energy}"


def test_14_inbox_add_and_clear():
    """add_to_inbox and clear_inbox correctly round-trip messages."""
    ws = make_world()
    msg1 = {"from": "kavya", "text": "Hello Arjun!"}
    msg2 = {"from": "deepa", "text": "Coming to metro?"}

    asyncio.run(ws.add_to_inbox("arjun", msg1))
    asyncio.run(ws.add_to_inbox("arjun", msg2))

    # Verify messages are in inbox
    inbox = ws.get_agent("arjun")["inbox"]
    assert len(inbox) == 2, f"Expected 2 messages in inbox, got {len(inbox)}"

    # clear_inbox should return the messages and empty the inbox
    returned = asyncio.run(ws.clear_inbox("arjun"))
    assert returned == [msg1, msg2], f"clear_inbox returned unexpected messages: {returned}"
    assert ws.get_agent("arjun")["inbox"] == [], \
        "Inbox should be empty after clear_inbox()"


def test_15_advance_time_day_rollover():
    """
    advance_time with day rollover:
    sim_time = 1430, advance by 20 → day increments, sim_time = 10.
    """
    ws = make_world()
    ws._state["sim_time"] = 1430
    ws._state["day"] = 1
    ws.advance_time(20)
    assert ws._state["day"] == 2, \
        f"Expected day=2 after rollover, got day={ws._state['day']}"
    assert ws._state["sim_time"] == 10, \
        f"Expected sim_time=10 after rollover, got sim_time={ws._state['sim_time']}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    ("1.  WorldState loads without error", test_01_loads_without_error),
    ("2.  get_time() returns correct structure with 'time_str' key", test_02_get_time_structure),
    ("3.  time_to_str() converts correctly: 0->'12:00am', 360->'6:00am', 780->'1:00pm', 1380->'11:00pm'", test_03_time_to_str_conversions),
    ("4.  get_agent('arjun') returns dict with required keys", test_04_get_agent_arjun),
    ("5.  get_all_agents() returns all 10 agents", test_05_get_all_agents_returns_10),
    ("6.  get_nearby_agents('arjun') includes kavya and deepa (all at apartment)", test_06_get_nearby_agents_arjun),
    ("7.  get_location('cyber_hub') returns dict with required fields", test_07_get_location_cyber_hub),
    ("8.  location_has_service('dhaba', 'eat_cheap') returns True", test_08_dhaba_has_eat_cheap),
    ("9.  location_has_service('park', 'work') returns False", test_09_park_does_not_have_work),
    ("10. get_connected_locations('apartment') returns {metro, sector29}", test_10_connected_locations_apartment),
    ("11. move_agent('arjun', 'metro') succeeds (metro connected to apartment)", test_11_move_agent_arjun_to_metro),
    ("12. move_agent('arjun', 'sector29') fails from metro (not connected)", test_12_move_agent_arjun_invalid_from_metro),
    ("13. update_needs clamps: hunger 95 + 10 = 100, energy 5 - 20 = 0", test_13_update_needs_clamping),
    ("14. add_to_inbox and clear_inbox round-trip correctly", test_14_inbox_add_and_clear),
    ("15. advance_time day rollover: sim_time 1430 + 20 -> day+1, sim_time=10", test_15_advance_time_day_rollover),
]


if __name__ == "__main__":
    print("=" * 70)
    print("Story 1.4 — WorldState Tests")
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
