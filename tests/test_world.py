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
# Some engine modules (engine.tools, engine.agent) load world/state.json at
# import time using a cwd-relative path. chdir into project root so the import
# succeeds regardless of where this test is invoked from.
os.chdir(ROOT)

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


def test_16_get_conversation_history():
    """get_conversation_history returns messages between a pair, oldest-first, limited."""
    ws = make_world()
    # Seed conversations: arjun<->kavya pair, plus one unrelated pair
    asyncio.run(ws.add_conversation("arjun",  "kavya", "msg 1"))
    asyncio.run(ws.add_conversation("kavya",  "arjun", "msg 2"))
    asyncio.run(ws.add_conversation("priya",  "rohan", "unrelated"))
    asyncio.run(ws.add_conversation("arjun",  "kavya", "msg 3"))
    asyncio.run(ws.add_conversation("kavya",  "arjun", "msg 4"))
    asyncio.run(ws.add_conversation("arjun",  "kavya", "msg 5"))

    # Both directions returned, oldest first
    history = ws.get_conversation_history("arjun", "kavya", limit=10)
    texts = [c["text"] for c in history]
    assert texts == ["msg 1", "msg 2", "msg 3", "msg 4", "msg 5"], \
        f"Wrong messages or order: {texts}"

    # Limit is honoured
    last2 = ws.get_conversation_history("arjun", "kavya", limit=2)
    assert [c["text"] for c in last2] == ["msg 4", "msg 5"], \
        f"Limit not honoured: {[c['text'] for c in last2]}"

    # Unrelated pair is excluded
    assert all("unrelated" not in c["text"] for c in history)

    # Empty pair returns empty list
    empty = ws.get_conversation_history("arjun", "vikram", limit=10)
    assert empty == [], f"Expected empty list, got {empty}"


def test_17_yesterday_reflection_persists():
    """set_yesterday_reflection writes a value retrievable via get_yesterday_reflection."""
    ws = make_world()
    text = "Aaj realize hua I keep going to cyber_city without reason. Kal try something different."
    asyncio.run(ws.set_yesterday_reflection("arjun", text))
    assert ws.get_yesterday_reflection("arjun") == text, \
        "get_yesterday_reflection should return the text just stored"
    # Also visible directly on the agent dict so persistence carries through state.json
    assert ws.get_agent("arjun").get("yesterday_reflection") == text, \
        "yesterday_reflection should live on the agent dict"

    # Default for an agent that has never reflected — empty string, not KeyError
    # Reset by reloading fresh state from disk
    ws2 = make_world()
    val = ws2.get_yesterday_reflection("priya")
    assert val == "" or val is None or isinstance(val, str), \
        f"get_yesterday_reflection should return string for any agent, got {type(val)}"


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
# Story 9.5 — Shared plans + SimulationLoop resolution
# ---------------------------------------------------------------------------


def test_18_shared_plans_in_fresh_state():
    """Fresh state contains shared_plans (list) and next_plan_id (int)."""
    from engine.world import WorldState
    ws = WorldState(state_path=STATE_PATH, map_path=MAP_PATH)
    ws._build_fresh_state()
    assert "shared_plans" in ws._state, "fresh state missing shared_plans"
    assert isinstance(ws._state["shared_plans"], list), \
        "shared_plans must be a list"
    assert ws._state["shared_plans"] == [], \
        "shared_plans should be empty in a fresh state"
    assert "next_plan_id" in ws._state, "fresh state missing next_plan_id"
    assert isinstance(ws._state["next_plan_id"], int)


def test_19_add_and_query_plan():
    """add_shared_plan assigns id and is queryable via get_plan/get_plans_for."""
    ws = make_world()
    ws._state["shared_plans"] = []
    ws._state["next_plan_id"] = 1
    plan = asyncio.run(ws.add_shared_plan({
        "participants": ["arjun", "kavya"],
        "location": "dhaba",
        "target_time": ws._abs_minutes() + 30,
        "activity": "lunch",
    }))
    assert plan["id"] == 1
    assert plan["status"] == "pending"
    assert ws.get_plan(1) is not None
    plans = ws.get_plans_for("arjun")
    assert len(plans) == 1, f"expected 1 plan for arjun, got {len(plans)}"
    assert plans[0]["id"] == 1
    # Counter increments
    plan2 = asyncio.run(ws.add_shared_plan({
        "participants": ["priya", "rohan"],
        "location": "cyber_hub",
        "target_time": ws._abs_minutes() + 60,
        "activity": "drinks",
    }))
    assert plan2["id"] == 2


def test_20_update_plan_status():
    """update_plan_status flips status and supports extra fields."""
    ws = make_world()
    ws._state["shared_plans"] = []
    ws._state["next_plan_id"] = 1
    p = asyncio.run(ws.add_shared_plan({
        "participants": ["arjun", "kavya"],
        "location": "dhaba",
        "target_time": ws._abs_minutes() + 30,
        "activity": "lunch",
    }))
    ok = asyncio.run(ws.update_plan_status(p["id"], "confirmed"))
    assert ok is True
    assert ws.get_plan(p["id"])["status"] == "confirmed"
    # decline with reason
    ws._state["shared_plans"] = []
    ws._state["next_plan_id"] = 1
    p2 = asyncio.run(ws.add_shared_plan({
        "participants": ["arjun", "kavya"],
        "location": "dhaba",
        "target_time": ws._abs_minutes() + 30,
        "activity": "lunch",
    }))
    asyncio.run(ws.update_plan_status(p2["id"], "declined", decline_reason="busy"))
    stored = ws.get_plan(p2["id"])
    assert stored["status"] == "declined"
    assert stored["decline_reason"] == "busy"


def test_21_resolve_plan_completes_when_both_present():
    """Sim loop completion path: both at location → completed, +8 mood, +50% hunger at food spot."""
    from engine.world import SimulationLoop
    ws = make_world()
    ws._state["shared_plans"] = []
    ws._state["next_plan_id"] = 1
    # Move both to dhaba (a food spot). arjun at apartment → sector29 → dhaba.
    asyncio.run(ws.move_agent("arjun", "sector29"))
    asyncio.run(ws.move_agent("arjun", "dhaba"))
    asyncio.run(ws.move_agent("kavya", "sector29"))
    asyncio.run(ws.move_agent("kavya", "dhaba"))
    # Set both moods to 50, hunger to 80 so we can detect changes.
    ws._state["agents"]["arjun"]["mood"] = 50.0
    ws._state["agents"]["kavya"]["mood"] = 50.0
    ws._state["agents"]["arjun"]["hunger"] = 80.0
    ws._state["agents"]["kavya"]["hunger"] = 80.0

    # Plan with target_time in the past so it elapses immediately.
    plan = asyncio.run(ws.add_shared_plan({
        "participants": ["arjun", "kavya"],
        "location": "dhaba",
        "target_time": ws._abs_minutes() - 1,
        "activity": "lunch",
        "status": "confirmed",
    }))

    loop = SimulationLoop(ws)
    asyncio.run(loop._resolve_shared_plans())

    stored = ws.get_plan(plan["id"])
    assert stored["status"] == "completed", f"expected completed, got {stored['status']}"
    assert ws.get_agent("arjun")["mood"] == 58.0, \
        f"arjun mood should be 50+8=58, got {ws.get_agent('arjun')['mood']}"
    assert ws.get_agent("kavya")["mood"] == 58.0
    # Hunger 80 - 50 = 30
    assert ws.get_agent("arjun")["hunger"] == 30.0, \
        f"hunger should be 30, got {ws.get_agent('arjun')['hunger']}"
    assert ws.get_agent("kavya")["hunger"] == 30.0


def test_22_resolve_plan_fails_when_one_absent():
    """Sim loop failure path: only one shows → failed, present -10 mood, absent gets reminder."""
    from engine.world import SimulationLoop
    ws = make_world()
    ws._state["shared_plans"] = []
    ws._state["next_plan_id"] = 1
    # arjun goes to dhaba; kavya stays at apartment.
    asyncio.run(ws.move_agent("arjun", "sector29"))
    asyncio.run(ws.move_agent("arjun", "dhaba"))
    # Confirm kavya is NOT at dhaba
    assert ws.get_agent_location("kavya") != "dhaba"
    ws._state["agents"]["arjun"]["mood"] = 50.0

    plan = asyncio.run(ws.add_shared_plan({
        "participants": ["arjun", "kavya"],
        "location": "dhaba",
        "target_time": ws._abs_minutes() - 1,
        "activity": "lunch",
        "status": "confirmed",
    }))

    loop = SimulationLoop(ws)
    asyncio.run(loop._resolve_shared_plans())

    stored = ws.get_plan(plan["id"])
    assert stored["status"] == "failed", f"expected failed, got {stored['status']}"
    # Present agent -10 mood
    assert ws.get_agent("arjun")["mood"] == 40.0, \
        f"arjun mood should be 50-10=40, got {ws.get_agent('arjun')['mood']}"
    # Absent agent has soft reminder in inbox
    kavya_inbox = ws.get_agent("kavya")["inbox"]
    missed = [m for m in kavya_inbox if m.get("type") == "missed_plan"]
    assert len(missed) == 1, f"expected 1 missed_plan reminder, got {len(missed)}"
    assert "dhaba" in missed[0].get("text", "")
    # Memory file mentions arjun's disappointment about kavya
    import os as _os
    memory_path = _os.path.join("agents", "arjun", "memory.md")
    if _os.path.exists(memory_path):
        with open(memory_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "didn't show up" in content or "Kavya" in content, \
            "memory should mention the failed rendezvous"


# ---------------------------------------------------------------------------
# Story 9.4 — Rent + Daily Bills (Economic Pressure)
# ---------------------------------------------------------------------------


def test_23_apply_rent_cycle_deducts_and_flags_stress():
    """apply_rent_cycle deducts rent and flips financial_stress when balance goes negative."""
    ws = make_world()
    arjun = ws._state["agents"]["arjun"]
    arjun["coins"] = 30
    arjun["monthly_rent"] = 60
    arjun["financial_stress"] = False
    arjun["financial_stress_until_day"] = 0

    result = asyncio.run(ws.apply_rent_cycle(current_day=5))

    assert arjun["coins"] == -30, f"expected -30 coins after rent, got {arjun['coins']}"
    assert arjun["financial_stress"] is True, \
        "financial_stress should flip to True when balance goes negative"
    assert arjun["financial_stress_until_day"] == 9, \
        f"expected until_day=9, got {arjun['financial_stress_until_day']}"
    assert result["arjun"]["stressed"] is True
    assert result["arjun"]["rent"] == 60
    assert result["arjun"]["balance"] == -30


def test_24_apply_rent_cycle_clears_stress_after_window():
    """apply_rent_cycle clears financial_stress once the until-day has passed."""
    ws = make_world()
    priya = ws._state["agents"]["priya"]
    priya["coins"] = 200
    priya["monthly_rent"] = 60
    priya["financial_stress"] = True
    priya["financial_stress_until_day"] = 6

    asyncio.run(ws.apply_rent_cycle(current_day=8))

    assert priya["coins"] == 140, f"expected 140 coins, got {priya['coins']}"
    assert priya["financial_stress"] is False, \
        "financial_stress should clear once current_day >= until_day"
    assert priya["financial_stress_until_day"] == 0


# ---------------------------------------------------------------------------
# Story 9.7 — Memory Consolidation bookkeeping
# ---------------------------------------------------------------------------


def test_26_set_get_last_consolidation_day():
    """set_last_consolidation_day persists; get_last_consolidation_day returns int."""
    ws = make_world()
    # Default for an existing agent in fresh state should be 0.
    asyncio.run(ws.set_last_consolidation_day("arjun", 5))
    assert ws.get_last_consolidation_day("arjun") == 5, \
        f"expected 5, got {ws.get_last_consolidation_day('arjun')}"
    # Overwrite path
    asyncio.run(ws.set_last_consolidation_day("arjun", 9))
    assert ws.get_last_consolidation_day("arjun") == 9
    # Missing field falls back to 0 cleanly
    if "last_consolidation_day" in ws._state["agents"]["priya"]:
        del ws._state["agents"]["priya"]["last_consolidation_day"]
    assert ws.get_last_consolidation_day("priya") == 0


def test_27_fresh_agents_have_last_consolidation_day_zero():
    """Fresh state initialises last_consolidation_day=0 for every agent."""
    from engine.world import WorldState
    ws = WorldState(state_path=STATE_PATH, map_path=MAP_PATH)
    ws._build_fresh_state()
    for name, agent in ws._state["agents"].items():
        assert agent.get("last_consolidation_day") == 0, \
            f"{name} should start with last_consolidation_day=0"


def test_28_run_memory_consolidations_skips_recent():
    """_run_memory_consolidations skips agents whose last_consolidation_day < 3 days ago."""
    from engine.world import SimulationLoop
    from unittest.mock import AsyncMock, patch
    ws = make_world()
    # All agents already consolidated on day 5 — none should fire on day 6.
    for name in ws._state["agents"]:
        ws._state["agents"][name]["last_consolidation_day"] = 5

    loop = SimulationLoop(ws)
    fake_consolidate = AsyncMock(return_value="updated memory")
    with patch("engine.agent.consolidate_memory", new=fake_consolidate):
        asyncio.run(loop._run_memory_consolidations(completed_day=6))
    assert fake_consolidate.call_count == 0, \
        f"expected 0 calls (gate not met), got {fake_consolidate.call_count}"


def test_29_run_memory_consolidations_fires_and_updates_bookkeeping():
    """_run_memory_consolidations fires when ≥3 days elapsed and updates last_consolidation_day."""
    from engine.world import SimulationLoop
    from unittest.mock import AsyncMock, patch
    ws = make_world()
    for name in ws._state["agents"]:
        ws._state["agents"][name]["last_consolidation_day"] = 0

    loop = SimulationLoop(ws)
    fake_consolidate = AsyncMock(return_value="updated memory")
    with patch("engine.agent.consolidate_memory", new=fake_consolidate):
        asyncio.run(loop._run_memory_consolidations(completed_day=3))

    assert fake_consolidate.call_count == 10, \
        f"expected 10 calls (one per agent), got {fake_consolidate.call_count}"
    # Bookkeeping should now read 3 for every agent.
    for name in ws._state["agents"]:
        assert ws.get_last_consolidation_day(name) == 3, \
            f"{name} last_consolidation_day should be 3 after firing"


# ---------------------------------------------------------------------------
# Story 9.8 — Scheduled External Events
# ---------------------------------------------------------------------------


def _events_world_with(events):
    """Build a WorldState whose _scheduled_events is overridden in-memory."""
    ws = make_world()
    ws._scheduled_events = events
    return ws


def test_30_get_active_events_for_matched_agent():
    """get_active_events_for returns the event when day, hour, and archetype match."""
    events = [{
        "day": 3,
        "start_hour": 13,
        "end_hour": 14,
        "location": "cyber_hub",
        "type": "meetup",
        "description": "startup meetup",
        "affected_agents": "archetype:office_worker,entrepreneur",
    }]
    ws = _events_world_with(events)
    # 13:30 (sim_time = 13*60 + 30 = 810) on day 3
    active = ws.get_active_events_for(
        agent_name="arjun", archetype="office_worker",
        current_day=3, current_sim_time=810,
    )
    assert len(active) == 1, f"expected 1 active event, got {len(active)}"
    assert active[0]["type"] == "meetup"


def test_31_get_active_events_empty_when_outside_window():
    """Returns empty when day/hour/archetype don't match."""
    events = [{
        "day": 3,
        "start_hour": 13,
        "end_hour": 14,
        "location": "cyber_hub",
        "type": "meetup",
        "description": "startup meetup",
        "affected_agents": "archetype:office_worker,entrepreneur",
    }]
    ws = _events_world_with(events)
    # Wrong day
    assert ws.get_active_events_for("arjun", "office_worker", 4, 810) == []
    # Wrong hour (12:30 — before window)
    assert ws.get_active_events_for("arjun", "office_worker", 3, 750) == []
    # Wrong hour (14:00 — end_hour exclusive)
    assert ws.get_active_events_for("arjun", "office_worker", 3, 14 * 60) == []
    # Wrong archetype
    assert ws.get_active_events_for("vikram", "retired", 3, 810) == []


def test_32_get_active_events_all_matches_everyone():
    """affected_agents='all' matches every agent regardless of archetype."""
    events = [{
        "day": 4,
        "start_hour": 9,
        "end_hour": 18,
        "location": None,
        "type": "monsoon",
        "description": "Heavy rain.",
        "affected_agents": "all",
    }]
    ws = _events_world_with(events)
    for name, archetype in [
        ("arjun", "office_worker"), ("kavya", "student"),
        ("vikram", "retired"), ("rahul", "night_owl"),
        ("anita", "entrepreneur"), ("deepa", "homemaker"),
        ("suresh", "vendor"),
    ]:
        active = ws.get_active_events_for(name, archetype, 4, 12 * 60)
        assert len(active) == 1, f"{name} ({archetype}) should see the event"
        assert active[0]["type"] == "monsoon"


def test_33_get_active_events_archetype_match_specifics():
    """archetype:X,Y matches both X and Y but not Z."""
    events = [{
        "day": 3,
        "start_hour": 13,
        "end_hour": 14,
        "location": "cyber_hub",
        "type": "meetup",
        "description": "startup meetup",
        "affected_agents": "archetype:office_worker,entrepreneur",
    }]
    ws = _events_world_with(events)
    # office_worker matches
    assert ws.get_active_events_for("arjun", "office_worker", 3, 13 * 60)
    # entrepreneur matches
    assert ws.get_active_events_for("anita", "entrepreneur", 3, 13 * 60)
    # retired does NOT match
    assert not ws.get_active_events_for("vikram", "retired", 3, 13 * 60)
    # student does NOT match
    assert not ws.get_active_events_for("kavya", "student", 3, 13 * 60)


def test_34_authored_events_file_loaded():
    """The authored world/scheduled_events.json is loaded into _scheduled_events."""
    ws = make_world()
    types = {e.get("type") for e in ws._scheduled_events}
    # All three seeded events should be present
    assert "meetup" in types, f"expected meetup, got {types}"
    assert "monsoon" in types, f"expected monsoon, got {types}"
    assert "festival_prep" in types, f"expected festival_prep, got {types}"


def test_35_get_active_monsoon_and_outdoor_classification():
    """get_active_monsoon returns monsoon during window; is_outdoor_location classifies map types."""
    events = [{
        "day": 4, "start_hour": 9, "end_hour": 18,
        "location": None, "type": "monsoon",
        "description": "rain", "affected_agents": "all",
    }]
    ws = _events_world_with(events)
    assert ws.get_active_monsoon(4, 12 * 60) is not None
    # Outside the window — none active
    assert ws.get_active_monsoon(4, 8 * 60) is None
    assert ws.get_active_monsoon(5, 12 * 60) is None
    # Outdoor classification — covers the 4 outdoor locations on the map.
    assert ws.is_outdoor_location("park") is True       # leisure
    assert ws.is_outdoor_location("metro") is True      # transit
    assert ws.is_outdoor_location("sector29") is True   # social
    assert ws.is_outdoor_location("cyber_hub") is True  # social
    # Indoor: home / work / food / shopping
    assert ws.is_outdoor_location("apartment") is False
    assert ws.is_outdoor_location("cyber_city") is False
    assert ws.is_outdoor_location("dhaba") is False
    assert ws.is_outdoor_location("supermarket") is False


def test_25_fresh_agents_have_archetype_rents():
    """Each fresh agent has a sensible monthly_rent matching their archetype."""
    from engine.world import WorldState
    ws = WorldState(state_path=STATE_PATH, map_path=MAP_PATH)
    ws._build_fresh_state()
    rents = {n: a.get("monthly_rent") for n, a in ws._state["agents"].items()}
    # Office workers (arjun, priya, neha) → 60
    assert rents["arjun"] == 60
    assert rents["priya"] == 60
    assert rents["neha"]  == 60
    # Vendor (suresh) → 25, retired (vikram) → 40, student (kavya) → 20
    assert rents["suresh"] == 25
    assert rents["vikram"] == 40
    assert rents["kavya"]  == 20
    # Entrepreneur (anita) → 50, homemaker (deepa) → 0, night_owls (rahul/rohan) → 35
    assert rents["anita"] == 50
    assert rents["deepa"] == 0
    assert rents["rahul"] == 35
    assert rents["rohan"] == 35
    # All fresh agents start with the financial_stress flag false.
    for name, agent in ws._state["agents"].items():
        assert agent.get("financial_stress") is False, \
            f"{name} should start with financial_stress=False"
        assert agent.get("financial_stress_until_day") == 0


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
    ("16. get_conversation_history returns pair messages oldest-first, respects limit", test_16_get_conversation_history),
    ("17. set/get_yesterday_reflection round-trips on agent dict (Story 9.2)", test_17_yesterday_reflection_persists),
    ("18. fresh state contains shared_plans+next_plan_id (Story 9.5)", test_18_shared_plans_in_fresh_state),
    ("19. add_shared_plan assigns id; get_plan/get_plans_for query (Story 9.5)", test_19_add_and_query_plan),
    ("20. update_plan_status flips status + supports extras (Story 9.5)", test_20_update_plan_status),
    ("21. SimulationLoop._resolve_shared_plans completes when both present (Story 9.5)", test_21_resolve_plan_completes_when_both_present),
    ("22. SimulationLoop._resolve_shared_plans fails when one absent (Story 9.5)", test_22_resolve_plan_fails_when_one_absent),
    ("23. apply_rent_cycle deducts rent + sets financial_stress (Story 9.4)", test_23_apply_rent_cycle_deducts_and_flags_stress),
    ("24. apply_rent_cycle clears financial_stress after window (Story 9.4)", test_24_apply_rent_cycle_clears_stress_after_window),
    ("25. fresh agents have archetype-sized monthly_rent (Story 9.4)", test_25_fresh_agents_have_archetype_rents),
    ("26. set/get_last_consolidation_day round-trip (Story 9.7)", test_26_set_get_last_consolidation_day),
    ("27. fresh agents start with last_consolidation_day=0 (Story 9.7)", test_27_fresh_agents_have_last_consolidation_day_zero),
    ("28. _run_memory_consolidations skips when <3 days elapsed (Story 9.7)", test_28_run_memory_consolidations_skips_recent),
    ("29. _run_memory_consolidations fires + updates bookkeeping (Story 9.7)", test_29_run_memory_consolidations_fires_and_updates_bookkeeping),
    ("30. get_active_events_for returns events on matching day/hour/archetype (Story 9.8)", test_30_get_active_events_for_matched_agent),
    ("31. get_active_events_for returns empty when day/hour/archetype don't match (Story 9.8)", test_31_get_active_events_empty_when_outside_window),
    ("32. affected_agents='all' matches every agent (Story 9.8)", test_32_get_active_events_all_matches_everyone),
    ("33. archetype:X,Y matches X and Y but not Z (Story 9.8)", test_33_get_active_events_archetype_match_specifics),
    ("34. authored scheduled_events.json loads on world.load() (Story 9.8)", test_34_authored_events_file_loaded),
    ("35. get_active_monsoon + is_outdoor_location helpers (Story 9.8)", test_35_get_active_monsoon_and_outdoor_classification),
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
