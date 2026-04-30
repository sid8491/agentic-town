"""
tests/test_plots.py — Story 10.4 Plot Threads Tracker tests.

Run with:
    .venv/Scripts/python.exe tests/test_plots.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from fastapi.testclient import TestClient

import server
from server import app
from engine.world import WorldState
from engine.plots import detect_plot_threads, _parse_event_time

STATE_PATH = os.path.join(ROOT, "world", "state.json")
MAP_PATH = os.path.join(ROOT, "world", "map.json")

results = []


def run_test(name, fn):
    try:
        fn()
        results.append((name, True, None))
        print(f"  PASS  {name}")
    except AssertionError as exc:
        results.append((name, False, str(exc)))
        print(f"  FAIL  {name}: {exc}")
    except Exception as exc:
        results.append((name, False, str(exc)))
        print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")


def make_world() -> WorldState:
    ws = WorldState(state_path=STATE_PATH, map_path=MAP_PATH)
    ws.load_or_init()
    # Pin a known sim time for deterministic timestamps.
    ws._state["day"] = 2
    ws._state["sim_time"] = 720  # 12:00pm Day 2 → abs = 2*1440+720 = 3600
    # Reset event/conversation/plan lists so detector starts clean.
    ws._state["events"] = []
    ws._state["conversations"] = []
    ws._state["shared_plans"] = []
    ws._state["next_plan_id"] = 1
    # Reset agent transient fields used by detectors.
    for ag in ws._state["agents"].values():
        ag["mood"] = 65.0
        ag["financial_stress"] = False
        ag["financial_stress_until_day"] = 0
        ag["last_action"] = "idle"
    return ws


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_01_parse_event_time():
    assert _parse_event_time("12:00am Day 1") == 1 * 1440 + 0
    assert _parse_event_time("6:30am Day 2") == 2 * 1440 + 6 * 60 + 30
    assert _parse_event_time("12:00pm Day 1") == 1 * 1440 + 720
    assert _parse_event_time("1:15pm Day 3") == 3 * 1440 + 13 * 60 + 15
    assert _parse_event_time("nonsense") is None


def test_02_no_threads_on_empty_state():
    ws = make_world()
    assert detect_plot_threads(ws) == []


def test_03_pending_plan_thread():
    ws = make_world()
    now_abs = ws._abs_minutes()
    plan = {
        "participants": ["arjun", "priya"],
        "location": "dhaba",
        "target_time": now_abs + 120,  # 2 hours from now
        "activity": "lunch",
        "status": "pending",
        "created_at": now_abs - 30,
    }
    ws._state["shared_plans"].append({**plan, "id": 1})
    ws._state["next_plan_id"] = 2

    threads = detect_plot_threads(ws)
    assert len(threads) == 1, f"got {threads}"
    t = threads[0]
    assert t["type"] == "pending_plan"
    assert "Arjun" in t["title"] and "Priya" in t["title"] and "dhaba" in t["title"]
    # remaining = 120, horizon = 240 → progress = 1 - 0.5 = 0.5
    assert abs(t["progress"] - 0.5) < 1e-6, f"progress was {t['progress']}"
    assert set(t["participants"]) == {"arjun", "priya"}


def test_04_awkward_plan_thread_after_decline():
    ws = make_world()
    now_abs = ws._abs_minutes()
    ws._state["shared_plans"].append({
        "id": 7,
        "participants": ["rahul", "kavya"],
        "location": "park",
        "target_time": now_abs + 60,
        "activity": "walk",
        "status": "declined",
        "created_at": now_abs - 30,
    })
    ws._state["events"].append({
        "time": "11:00am Day 2",
        "text": "kavya declined plan #7: too tired",
    })

    threads = detect_plot_threads(ws)
    awk = [t for t in threads if t["type"] == "awkwardness"]
    assert len(awk) == 1, f"awkwardness threads: {awk}"
    t = awk[0]
    assert "Awkwardness" in t["title"]
    assert set(t["participants"]) == {"rahul", "kavya"}


def test_05_awkward_plan_expires_after_24h():
    ws = make_world()
    # Now: Day 2 12pm. Decline event Day 1 11am → 25 hours ago → expired.
    ws._state["shared_plans"].append({
        "id": 8,
        "participants": ["rahul", "kavya"],
        "location": "park",
        "target_time": 0,
        "activity": "walk",
        "status": "declined",
        "created_at": 0,
    })
    ws._state["events"].append({
        "time": "11:00am Day 1",
        "text": "kavya declined plan #8: nope",
    })
    threads = detect_plot_threads(ws)
    assert all(t["type"] != "awkwardness" for t in threads), threads


def test_06_financial_stress_thread():
    ws = make_world()
    ws._state["agents"]["rohan"]["financial_stress"] = True
    # current_day=2, until_day=4 → 4-2=2 → days_behind = 4-2 = 2 → progress 0.5
    ws._state["agents"]["rohan"]["financial_stress_until_day"] = 4
    ws._state["agents"]["rohan"]["coins"] = -20

    threads = detect_plot_threads(ws)
    fin = [t for t in threads if t["type"] == "financial"]
    assert len(fin) == 1, fin
    t = fin[0]
    assert "Rohan" in t["title"] and "rent crisis" in t["title"]
    assert abs(t["progress"] - 0.5) < 1e-6, t["progress"]


def test_07_mood_spiral_thread():
    ws = make_world()
    ws._state["agents"]["deepa"]["mood"] = 12
    ws._state["agents"]["deepa"]["last_action"] = "lying in bed"

    threads = detect_plot_threads(ws)
    mood = [t for t in threads if t["type"] == "mood_spiral"]
    assert len(mood) == 1, mood
    t = mood[0]
    assert "Deepa" in t["title"]
    assert t["participants"] == ["deepa"]
    # mood=12, threshold=30 → progress = (30-12)/30 = 0.6
    assert abs(t["progress"] - 0.6) < 1e-6, t["progress"]


def test_08_mood_above_threshold_no_thread():
    ws = make_world()
    ws._state["agents"]["deepa"]["mood"] = 30  # exactly at threshold → not spiralling
    threads = detect_plot_threads(ws)
    assert all(t["type"] != "mood_spiral" for t in threads)


def test_09_chat_streak_thread():
    ws = make_world()
    now_day = ws._state["day"]
    now_sim = ws._state["sim_time"]
    # 6 messages in last hour between arjun & priya
    for i in range(6):
        ws._state["conversations"].append({
            "from": "arjun" if i % 2 == 0 else "priya",
            "to": "priya" if i % 2 == 0 else "arjun",
            "text": f"hi {i}",
            "time": "11:30am Day 2",
            "sim_time": now_sim - 30,
            "day": now_day,
        })

    threads = detect_plot_threads(ws)
    chat = [t for t in threads if t["type"] == "chat_streak"]
    assert len(chat) == 1, chat
    assert set(chat[0]["participants"]) == {"arjun", "priya"}


def test_10_chat_streak_below_threshold():
    ws = make_world()
    for i in range(4):  # only 4 messages — under the 5+ bar
        ws._state["conversations"].append({
            "from": "arjun",
            "to": "priya",
            "text": f"hi {i}",
            "sim_time": ws._state["sim_time"] - 30,
            "day": ws._state["day"],
        })
    threads = detect_plot_threads(ws)
    assert all(t["type"] != "chat_streak" for t in threads)


def test_11_disagreement_thread():
    ws = make_world()
    ws._state["events"].append({
        "time": "11:00am Day 2",
        "text": "conflict: arjun vs rohan on rent — you should pay your share",
    })
    threads = detect_plot_threads(ws)
    dis = [t for t in threads if t["type"] == "disagreement"]
    assert len(dis) == 1, dis
    assert set(dis[0]["participants"]) == {"arjun", "rohan"}


def test_12_disagreement_resolved_drops():
    ws = make_world()
    ws._state["events"].append({
        "time": "11:00am Day 2",
        "text": "conflict: arjun vs rohan on rent — you should pay your share",
    })
    ws._state["events"].append({
        "time": "11:30am Day 2",
        "text": "arjun and rohan reconcile after the rent fight",
    })
    threads = detect_plot_threads(ws)
    assert all(t["type"] != "disagreement" for t in threads), threads


def test_13_endpoint_returns_threads_sorted_capped():
    """GET /api/plot_threads returns sorted+capped threads."""
    ws = make_world()
    now_abs = ws._abs_minutes()
    # Create 6 mood spirals and 1 plan — total 7 candidates, capped at 5.
    for name in ws.get_all_agents().keys():
        ws._state["agents"][name]["mood"] = 10
    ws._state["shared_plans"].append({
        "id": 1,
        "participants": ["arjun", "priya"],
        "location": "dhaba",
        "target_time": now_abs + 60,
        "activity": "lunch",
        "status": "pending",
        "created_at": now_abs,
    })
    server.set_world(ws)
    try:
        client = TestClient(app)
        r = client.get("/api/plot_threads")
        assert r.status_code == 200, r.status_code
        body = r.json()
        assert "threads" in body
        threads = body["threads"]
        assert len(threads) <= 5, f"expected ≤5, got {len(threads)}"
        # Sorted desc by last_updated.
        last_updates = [t["last_updated"] for t in threads]
        assert last_updates == sorted(last_updates, reverse=True), last_updates
    finally:
        server._world = None


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


TESTS = [
    ("parse_event_time covers am/pm/noon/midnight",      test_01_parse_event_time),
    ("empty state → no threads",                          test_02_no_threads_on_empty_state),
    ("pending shared plan → thread w/ correct progress",  test_03_pending_plan_thread),
    ("declined plan → awkwardness thread",                test_04_awkward_plan_thread_after_decline),
    ("declined plan expires after 24 game hours",         test_05_awkward_plan_expires_after_24h),
    ("financial_stress agent → rent-crisis thread",       test_06_financial_stress_thread),
    ("mood < 30 → spiral thread",                         test_07_mood_spiral_thread),
    ("mood ≥ 30 → no spiral thread",                      test_08_mood_above_threshold_no_thread),
    ("5+ messages in 3h → chat-streak thread",            test_09_chat_streak_thread),
    ("<5 messages → no chat-streak thread",               test_10_chat_streak_below_threshold),
    ("conflict event → disagreement thread",              test_11_disagreement_thread),
    ("later reconcile → disagreement drops",              test_12_disagreement_resolved_drops),
    ("/api/plot_threads sorted desc, capped at 5",        test_13_endpoint_returns_threads_sorted_capped),
]


if __name__ == "__main__":
    print(f"\nRunning {len(TESTS)} plot-thread tests...\n")
    for name, fn in TESTS:
        run_test(name, fn)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    print(f"\n{'='*50}")
    print(f"Results: {passed}/{len(results)} passed", end="")
    if failed:
        print(f"  ({failed} FAILED)")
        sys.exit(1)
    else:
        print("  — all PASS")
        sys.exit(0)
