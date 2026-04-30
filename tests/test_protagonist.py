"""
tests/test_protagonist.py — Story 10.1 / 10.2 protagonist scoring.

Pure logic tests — no LLM, no I/O beyond loading map+state from disk.

Run:
    .venv/Scripts/python.exe tests/test_protagonist.py
"""

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from engine.world import WorldState
from engine.protagonist import pick_protagonist, score_agent

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


def _make_world() -> WorldState:
    ws = WorldState(
        state_path=os.path.join(ROOT, "world", "state.json"),
        map_path=os.path.join(ROOT, "world", "map.json"),
    )
    ws.load_or_init()
    return ws


def test_neutral_score_is_low():
    """An agent with neutral stats and no events scores under 5."""
    ws = _make_world()
    ws._state["events"] = []
    ws._state["shared_plans"] = []
    a = ws.get_agent("arjun")
    a["mood"] = 50
    a["energy"] = 80
    a["hunger"] = 30
    a["financial_stress"] = False
    a["last_action"] = "looking around"
    score = score_agent(ws, "arjun")
    check(
        "neutral score is < 5",
        score < 5,
        f"score={score}",
    )


def test_low_mood_adds_seven():
    ws = _make_world()
    ws._state["events"] = []
    a = ws.get_agent("arjun")
    a["mood"] = 50
    a["energy"] = 80
    a["hunger"] = 30
    a["financial_stress"] = False
    a["last_action"] = "looking around"
    base = score_agent(ws, "arjun")
    a["mood"] = 10
    high_low = score_agent(ws, "arjun")
    check(
        "low mood adds 7",
        high_low - base == 7,
        f"base={base}, low={high_low}",
    )


def test_high_mood_adds_seven():
    ws = _make_world()
    ws._state["events"] = []
    a = ws.get_agent("arjun")
    a["mood"] = 50
    a["energy"] = 80
    a["hunger"] = 30
    a["financial_stress"] = False
    a["last_action"] = "looking around"
    base = score_agent(ws, "arjun")
    a["mood"] = 90
    high = score_agent(ws, "arjun")
    check(
        "high mood adds 7",
        high - base == 7,
        f"base={base}, high={high}",
    )


def test_financial_stress_adds_six():
    ws = _make_world()
    ws._state["events"] = []
    a = ws.get_agent("arjun")
    a["mood"] = 50
    a["energy"] = 80
    a["hunger"] = 30
    a["financial_stress"] = False
    a["last_action"] = "looking around"
    base = score_agent(ws, "arjun")
    a["financial_stress"] = True
    after = score_agent(ws, "arjun")
    check(
        "financial_stress adds 6",
        after - base == 6,
        f"base={base}, after={after}",
    )


def test_hunger_or_low_energy_adds_five():
    ws = _make_world()
    ws._state["events"] = []
    a = ws.get_agent("arjun")
    a["mood"] = 50
    a["energy"] = 80
    a["hunger"] = 30
    a["financial_stress"] = False
    a["last_action"] = "looking around"
    base = score_agent(ws, "arjun")
    a["hunger"] = 90
    after_hunger = score_agent(ws, "arjun")
    check(
        "hunger > 80 adds 5",
        after_hunger - base == 5,
        f"base={base}, hunger90={after_hunger}",
    )
    a["hunger"] = 30
    a["energy"] = 10
    after_energy = score_agent(ws, "arjun")
    check(
        "energy < 20 adds 5",
        after_energy - base == 5,
        f"base={base}, energy10={after_energy}",
    )


def test_active_conversation_adds_ten():
    """Two agents at the same location with talk-tagged last_action add +10."""
    ws = _make_world()
    ws._state["events"] = []
    # Park agents into the same location and stage a conversation.
    arjun = ws.get_agent("arjun")
    kavya = ws.get_agent("kavya")
    arjun["location"] = "dhaba"
    kavya["location"] = "dhaba"
    arjun["last_action"] = "looking around"
    kavya["last_action"] = "looking around"
    arjun["mood"] = 50
    arjun["energy"] = 80
    arjun["hunger"] = 30
    arjun["financial_stress"] = False
    base = score_agent(ws, "arjun")
    kavya["last_action"] = "talk_to arjun"
    after = score_agent(ws, "arjun")
    check(
        "active conversation adds 10",
        after - base == 10,
        f"base={base}, talking={after}",
    )


def test_imminent_shared_plan_adds_eight():
    ws = _make_world()
    ws._state["events"] = []
    ws._state["shared_plans"] = []
    ws._state["next_plan_id"] = 1
    a = ws.get_agent("arjun")
    a["mood"] = 50
    a["energy"] = 80
    a["hunger"] = 30
    a["financial_stress"] = False
    a["last_action"] = "looking around"
    base = score_agent(ws, "arjun")
    cur = ws.get_time()
    target_abs = cur["day"] * 1440 + cur["sim_time"] + 15
    asyncio.run(ws.add_shared_plan({
        "participants": ["arjun", "kavya"],
        "location": "dhaba",
        "target_time": target_abs,
        "activity": "lunch",
        "status": "confirmed",
    }))
    after = score_agent(ws, "arjun")
    check(
        "imminent confirmed plan adds 8",
        after - base == 8,
        f"base={base}, after={after}",
    )


def test_recent_refusal_adds_four():
    ws = _make_world()
    ws._state["events"] = []
    a = ws.get_agent("arjun")
    a["mood"] = 50
    a["energy"] = 80
    a["hunger"] = 30
    a["financial_stress"] = False
    a["last_action"] = "looking around"
    base = score_agent(ws, "arjun")
    asyncio.run(ws.add_event("arjun refuses to meet kavya at dhaba"))
    after = score_agent(ws, "arjun")
    # +4 for refusal, +2 for "events involving this agent in last 30min" → +6
    check(
        "recent refusal contributes +4 (+2 from event lookup = +6 total)",
        after - base == 6,
        f"base={base}, after={after}",
    )


def test_pick_protagonist_returns_highest_scoring():
    ws = _make_world()
    ws._state["events"] = []
    # Reset all agents to a neutral baseline.
    for name, ag in ws.get_all_agents().items():
        ag["mood"] = 50
        ag["energy"] = 80
        ag["hunger"] = 30
        ag["financial_stress"] = False
        ag["last_action"] = "idle"
    # Spike priya's mood so she's the obvious winner.
    ws.get_agent("priya")["mood"] = 90
    pick = pick_protagonist(ws)
    check(
        "pick_protagonist returns the highest-scoring agent",
        pick == "priya",
        f"picked={pick!r}",
    )


def test_pick_protagonist_alphabetical_tiebreak():
    ws = _make_world()
    ws._state["events"] = []
    ws._state["shared_plans"] = []
    for name, ag in ws.get_all_agents().items():
        ag["mood"] = 50
        ag["energy"] = 80
        ag["hunger"] = 30
        ag["financial_stress"] = False
        ag["last_action"] = "idle"
        # Spread agents across distinct locations so the "active conversation"
        # heuristic stays at zero across the board.
        ag["location"] = name  # any unique value works for the test
    pick = pick_protagonist(ws)
    # All neutral → alphabetical: anita
    check(
        "alphabetical tiebreak when all scores equal",
        pick == "anita",
        f"picked={pick!r}",
    )


if __name__ == "__main__":
    print("=" * 60)
    print("Story 10.1 — protagonist scoring tests")
    print("=" * 60)
    print()
    test_neutral_score_is_low()
    test_low_mood_adds_seven()
    test_high_mood_adds_seven()
    test_financial_stress_adds_six()
    test_hunger_or_low_energy_adds_five()
    test_active_conversation_adds_ten()
    test_imminent_shared_plan_adds_eight()
    test_recent_refusal_adds_four()
    test_pick_protagonist_returns_highest_scoring()
    test_pick_protagonist_alphabetical_tiebreak()
    print()
    print("=" * 60)
    print(f"Results: {_pass} passed, {_fail} failed")
    print("=" * 60)
    if _fail > 0:
        sys.exit(1)
