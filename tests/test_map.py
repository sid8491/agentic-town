"""
Story 1.2 — World Map & State Tests
Verifies world/map.json and world/state.json correctness.
Run with: .venv/Scripts/python.exe tests/test_map.py
"""

import json
import os
import sys

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_PATH = os.path.join(ROOT, "world", "map.json")
STATE_PATH = os.path.join(ROOT, "world", "state.json")

REQUIRED_LOCATION_FIELDS = {"id", "name", "type", "connected_to", "services", "tile_x", "tile_y"}
REQUIRED_AGENT_FIELDS = {"location", "hunger", "energy", "mood", "coins", "inventory", "inbox"}
EXPECTED_AGENT_COUNT = 10
EXPECTED_LOCATION_COUNT = 8

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


# ---------------------------------------------------------------------------
# Load data (done once; tests that need data reference these globals)
# ---------------------------------------------------------------------------

map_data = None
state_data = None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_map_loads_as_valid_json():
    global map_data
    with open(MAP_PATH, "r", encoding="utf-8") as f:
        map_data = json.load(f)
    assert isinstance(map_data, dict), "map.json root must be a JSON object"
    assert "locations" in map_data, "map.json must have a 'locations' key"


def test_all_8_locations_exist_with_required_fields():
    assert map_data is not None, "map.json was not loaded (prior test failed)"
    locs = map_data["locations"]
    assert len(locs) == EXPECTED_LOCATION_COUNT, (
        f"Expected {EXPECTED_LOCATION_COUNT} locations, found {len(locs)}"
    )
    for loc in locs:
        missing = REQUIRED_LOCATION_FIELDS - set(loc.keys())
        assert not missing, (
            f"Location '{loc.get('id', '?')}' missing fields: {missing}"
        )


def test_all_connections_are_bidirectional():
    assert map_data is not None, "map.json was not loaded (prior test failed)"
    locs = map_data["locations"]
    loc_map = {loc["id"]: loc for loc in locs}
    for loc in locs:
        for neighbour_id in loc["connected_to"]:
            neighbour = loc_map.get(neighbour_id)
            assert neighbour is not None, (
                f"Location '{loc['id']}' connects to unknown id '{neighbour_id}'"
            )
            assert loc["id"] in neighbour["connected_to"], (
                f"Connection is not bidirectional: '{loc['id']}' → '{neighbour_id}' "
                f"but '{neighbour_id}' does not list '{loc['id']}' in connected_to"
            )


def test_no_location_connects_to_itself():
    assert map_data is not None, "map.json was not loaded (prior test failed)"
    for loc in map_data["locations"]:
        assert loc["id"] not in loc["connected_to"], (
            f"Location '{loc['id']}' connects to itself"
        )


def test_all_connected_to_references_are_valid():
    assert map_data is not None, "map.json was not loaded (prior test failed)"
    valid_ids = {loc["id"] for loc in map_data["locations"]}
    for loc in map_data["locations"]:
        for ref in loc["connected_to"]:
            assert ref in valid_ids, (
                f"Location '{loc['id']}' references unknown id '{ref}' in connected_to"
            )


def test_state_loads_as_valid_json():
    global state_data
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        state_data = json.load(f)
    assert isinstance(state_data, dict), "state.json root must be a JSON object"


def test_all_10_agents_exist_with_required_fields():
    assert state_data is not None, "state.json was not loaded (prior test failed)"
    agents = state_data.get("agents", {})
    assert len(agents) == EXPECTED_AGENT_COUNT, (
        f"Expected {EXPECTED_AGENT_COUNT} agents, found {len(agents)}"
    )
    for name, agent in agents.items():
        missing = REQUIRED_AGENT_FIELDS - set(agent.keys())
        assert not missing, (
            f"Agent '{name}' missing fields: {missing}"
        )


def test_agent_locations_are_valid():
    assert map_data is not None, "map.json was not loaded (prior test failed)"
    assert state_data is not None, "state.json was not loaded (prior test failed)"
    valid_ids = {loc["id"] for loc in map_data["locations"]}
    agents = state_data.get("agents", {})
    for name, agent in agents.items():
        loc = agent.get("location")
        assert loc in valid_ids, (
            f"Agent '{name}' has invalid starting location '{loc}' "
            f"(valid ids: {sorted(valid_ids)})"
        )


def test_agent_needs_values_in_range():
    assert state_data is not None, "state.json was not loaded (prior test failed)"
    agents = state_data.get("agents", {})
    needs_fields = ["hunger", "energy", "mood"]
    for name, agent in agents.items():
        for field in needs_fields:
            value = agent.get(field)
            assert value is not None, f"Agent '{name}' missing needs field '{field}'"
            assert 0 <= value <= 100, (
                f"Agent '{name}' field '{field}' = {value} is out of range [0, 100]"
            )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    ("1. map.json loads as valid JSON", test_map_loads_as_valid_json),
    ("2. All 8 locations exist with required fields", test_all_8_locations_exist_with_required_fields),
    ("3. All connections are bidirectional", test_all_connections_are_bidirectional),
    ("4. No location connects to itself", test_no_location_connects_to_itself),
    ("5. All connected_to references point to valid location IDs", test_all_connected_to_references_are_valid),
    ("6. state.json loads as valid JSON", test_state_loads_as_valid_json),
    ("7. All 10 agents exist with required fields", test_all_10_agents_exist_with_required_fields),
    ("8. All agent starting locations are valid location IDs", test_agent_locations_are_valid),
    ("9. All needs values (hunger, energy, mood) are between 0 and 100", test_agent_needs_values_in_range),
]


if __name__ == "__main__":
    print("=" * 60)
    print("Story 1.2 — World Map & State Tests")
    print("=" * 60)

    for test_name, test_fn in TESTS:
        run_test(test_name, test_fn)

    print()
    print("=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    total = len(results)
    print(f"Results: {passed}/{total} passed, {failed} failed")
    print("=" * 60)

    if failed:
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
        sys.exit(0)
