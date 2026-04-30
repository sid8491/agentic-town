"""
Story 10.5 — Drama-Driven Auto-Pacing Tests
Verifies compute_drama_score / pick_speed and the SimulationLoop integration.

Run with:
    .venv/Scripts/python.exe tests/test_pacing.py

No live LLM, no Arcade — fake world states and patched agents only.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.world import (
    SimulationLoop,
    WorldState,
    compute_drama_score,
    pick_speed,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(ROOT, "world", "state.json")
MAP_PATH = os.path.join(ROOT, "world", "map.json")

results = []


def run_test(name, coro_or_fn):
    try:
        if asyncio.iscoroutinefunction(coro_or_fn):
            asyncio.run(coro_or_fn())
        else:
            coro_or_fn()
        results.append((name, True, None))
        print(f"  PASS  {name}")
    except Exception as exc:
        results.append((name, False, str(exc)))
        print(f"  FAIL  {name}")
        print(f"        {exc}")


def make_world() -> WorldState:
    ws = WorldState(state_path=STATE_PATH, map_path=MAP_PATH)
    ws.load()
    return ws


def fake_state(
    *,
    events=None,
    agents=None,
    plans=None,
    sim_time=600,
    day=1,
):
    """Build a minimal world_state dict for compute_drama_score()."""
    return {
        "events":       list(events or []),
        "agents":       dict(agents or {}),
        "shared_plans": list(plans or []),
        "sim_time":     sim_time,
        "day":          day,
    }


# ---------------------------------------------------------------------------
# compute_drama_score tests
# ---------------------------------------------------------------------------


def test_01_empty_state_score_zero():
    score = compute_drama_score(fake_state())
    assert score == 0, f"Expected 0, got {score}"


def test_02_single_talk_event_scores_5():
    state = fake_state(
        events=[{"time": "10:00am Day 1", "text": "arjun says to priya: hi"}],
        agents={"a": {"mood": 50, "last_action": "looking around..."}},
    )
    score = compute_drama_score(state)
    # 5 from talk_to. Mood 50 is in the calm band, no motion.
    assert score == 5, f"Expected 5, got {score}"


def test_03_conflict_event_scores_8():
    state = fake_state(
        events=[{"time": "10:00am Day 1", "text": "conflict: rohan vs vikram on rent — too high"}],
        agents={"a": {"mood": 50, "last_action": ""}},
    )
    score = compute_drama_score(state)
    assert score == 8, f"Expected 8, got {score}"


def test_04_imminent_plan_scores_10():
    # Plan starts 20 sim-minutes from now → counts.
    state = fake_state(
        plans=[{
            "status": "pending",
            "target_time": 1 * 1440 + 620,  # 20min after sim_time=600 day=1
        }],
        sim_time=600,
        day=1,
    )
    score = compute_drama_score(state)
    assert score == 10, f"Expected 10, got {score}"


def test_05_distant_plan_does_not_score():
    # Plan starts 90 sim-minutes from now → does NOT count.
    state = fake_state(
        plans=[{
            "status": "pending",
            "target_time": 1 * 1440 + 690,
        }],
        sim_time=600,
        day=1,
    )
    score = compute_drama_score(state)
    assert score == 0, f"Expected 0 (plan too far), got {score}"


def test_06_completed_plan_does_not_score():
    state = fake_state(
        plans=[{
            "status": "completed",
            "target_time": 1 * 1440 + 605,
        }],
        sim_time=600, day=1,
    )
    score = compute_drama_score(state)
    assert score == 0, f"Expected 0 (plan completed), got {score}"


def test_07_extreme_mood_scores_3_each():
    state = fake_state(agents={
        "a": {"mood": 20, "last_action": ""},  # < 30 → +3
        "b": {"mood": 80, "last_action": ""},  # > 75 → +3
        "c": {"mood": 50, "last_action": ""},  # calm  → 0
    })
    score = compute_drama_score(state)
    assert score == 6, f"Expected 6, got {score}"


def test_08_motion_scores_2_each():
    state = fake_state(agents={
        "a": {"mood": 50, "last_action": "moving to metro..."},
        "b": {"mood": 50, "last_action": "moving to dhaba..."},
        "c": {"mood": 50, "last_action": "looking around..."},
    })
    score = compute_drama_score(state)
    assert score == 4, f"Expected 4, got {score}"


def test_09_combined_score_sums_components():
    state = fake_state(
        events=[
            {"time": "t", "text": "arjun says to priya: hi"},        # +5
            {"time": "t", "text": "conflict: a vs b on x — y"},      # +8
            {"time": "t", "text": "kavya says to neha: yo"},         # +5
        ],
        agents={
            "a": {"mood": 10, "last_action": "moving to park..."},   # +3 +2
            "b": {"mood": 90, "last_action": ""},                    # +3
            "c": {"mood": 50, "last_action": "moving to dhaba..."},  # +2
        },
        plans=[{
            "status": "confirmed",
            "target_time": 1 * 1440 + 615,  # 15min away → +10
        }],
        sim_time=600, day=1,
    )
    score = compute_drama_score(state)
    # 5+8+5 + 10 + 3+2 + 3 + 2 = 38
    assert score == 38, f"Expected 38, got {score}"


# ---------------------------------------------------------------------------
# pick_speed tests
# ---------------------------------------------------------------------------


def test_10_locked_returns_default():
    assert pick_speed(score=0, sleeping_count=0, locked=True, low_score_since=None) == (1.0, None)
    # Even at high drama, locked still returns 1.0 / None (caller skips anyway).
    assert pick_speed(score=99, sleeping_count=10, locked=True, low_score_since=None) == (1.0, None)


def test_11_night_override_beats_drama():
    # 7+ sleeping → 4x even when drama is high.
    speed, label = pick_speed(score=20, sleeping_count=7, locked=False, low_score_since=None)
    assert speed == 4.0 and label is None


def test_12_high_drama_live():
    speed, label = pick_speed(score=15, sleeping_count=0, locked=False, low_score_since=None)
    assert speed == 1.0 and label is None
    speed, label = pick_speed(score=42, sleeping_count=0, locked=False, low_score_since=None)
    assert speed == 1.0 and label is None


def test_13_default_band_8_to_14():
    speed, label = pick_speed(score=8, sleeping_count=0, locked=False, low_score_since=None)
    assert speed == 1.0 and label is None
    speed, label = pick_speed(score=14, sleeping_count=0, locked=False, low_score_since=None)
    assert speed == 1.0 and label is None


def test_14_quiet_stretch_2x_with_label():
    speed, label = pick_speed(score=3, sleeping_count=0, locked=False, low_score_since=None)
    assert speed == 2.0
    assert label == "⏩ quiet stretch"
    speed, label = pick_speed(score=7, sleeping_count=0, locked=False, low_score_since=None)
    assert speed == 2.0 and label == "⏩ quiet stretch"


def test_15_low_score_waits_for_dwell():
    # No dwell yet → still 1x.
    speed, label = pick_speed(
        score=1, sleeping_count=0, locked=False,
        low_score_since=100.0, now_monotonic=120.0,  # 20s elapsed
    )
    assert speed == 1.0 and label is None


def test_16_low_score_after_dwell_skips_ahead():
    speed, label = pick_speed(
        score=0, sleeping_count=0, locked=False,
        low_score_since=100.0, now_monotonic=170.0,  # 70s elapsed
    )
    assert speed == 4.0
    assert label == "⏩⏩ skipping ahead"


def test_17_low_score_no_timestamp_stays_1x():
    speed, label = pick_speed(
        score=0, sleeping_count=0, locked=False, low_score_since=None,
    )
    assert speed == 1.0 and label is None


# ---------------------------------------------------------------------------
# SimulationLoop integration
# ---------------------------------------------------------------------------


async def test_18_tick_sets_speed_for_quiet_stretch():
    world = make_world()
    # Wipe events / agents into a calm but not dead state to land at score 3-7.
    world._state["events"] = []
    for name, agent in world._state["agents"].items():
        agent["mood"] = 50
        agent["last_action"] = "looking around..."
    # Two extreme-mood agents → score = 6 (in the 3-7 band).
    world._state["agents"]["arjun"]["mood"] = 10
    world._state["agents"]["priya"]["mood"] = 90

    world._state["speed"] = 1.0
    world._state.pop("_speed_locked", None)

    loop = SimulationLoop(world)
    with patch("engine.agent.AgentRunner.tick", new_callable=AsyncMock):
        with patch("engine.needs.decay_all_agents", new_callable=AsyncMock):
            await loop._tick()

    assert world._state["speed"] == 2.0, f"expected 2x, got {world._state['speed']}"
    assert world._state.get("_pacing_label") == "⏩ quiet stretch"


async def test_19_tick_keeps_1x_under_high_drama():
    world = make_world()
    # Stack the events tail with talk_to + conflict so drama_score >= 15.
    world._state["events"] = [
        {"time": "t", "text": "a says to b: hi"} for _ in range(2)
    ] + [
        {"time": "t", "text": "conflict: x vs y on z — w"} for _ in range(2)
    ]
    for agent in world._state["agents"].values():
        agent["mood"] = 50
        agent["last_action"] = ""
    world._state["speed"] = 4.0  # something non-1x to verify it gets reset
    world._state.pop("_speed_locked", None)
    # No agents sleeping.

    loop = SimulationLoop(world)
    with patch("engine.agent.AgentRunner.tick", new_callable=AsyncMock):
        with patch("engine.needs.decay_all_agents", new_callable=AsyncMock):
            await loop._tick()

    assert world._state["speed"] == 1.0, f"expected 1x, got {world._state['speed']}"
    assert world._state.get("_pacing_label") is None


async def test_20_manual_lock_blocks_auto_pacing():
    world = make_world()
    world._state["events"] = []
    for agent in world._state["agents"].values():
        agent["mood"] = 50
        agent["last_action"] = "looking around..."
    world._state["speed"] = 3.0
    world._state["_speed_locked"] = True

    loop = SimulationLoop(world)
    with patch("engine.agent.AgentRunner.tick", new_callable=AsyncMock):
        with patch("engine.needs.decay_all_agents", new_callable=AsyncMock):
            await loop._tick()

    # Speed is whatever the user set; no pacing label should appear.
    assert world._state["speed"] == 3.0, f"manual speed clobbered: {world._state['speed']}"
    assert "_pacing_label" not in world._state


async def test_21_night_auto_speed_still_works():
    world = make_world()
    world._state["events"] = []
    # 8 of 10 agents sleeping → night override → 4x regardless of drama.
    sleepers = list(world._state["agents"].keys())[:8]
    for name, agent in world._state["agents"].items():
        agent["mood"] = 50
        agent["last_action"] = "sleeping..." if name in sleepers else "looking around..."
    world._state["speed"] = 1.0
    world._state.pop("_speed_locked", None)

    loop = SimulationLoop(world)
    with patch("engine.agent.AgentRunner.tick", new_callable=AsyncMock):
        with patch("engine.needs.decay_all_agents", new_callable=AsyncMock):
            await loop._tick()

    assert world._state["speed"] == 4.0, f"expected night 4x, got {world._state['speed']}"
    # Night-only override does NOT set a pacing label.
    assert world._state.get("_pacing_label") is None


async def test_22_pacing_state_keys_not_persisted():
    """`_pacing_label` and `_speed_locked` must be stripped from state.json."""
    import json
    import tempfile
    import shutil

    # Use a temp state_path so we don't trash the real file.
    with tempfile.TemporaryDirectory() as td:
        tmp_state = os.path.join(td, "state.json")
        shutil.copy(STATE_PATH, tmp_state)
        ws = WorldState(state_path=tmp_state, map_path=MAP_PATH)
        ws.load()
        ws._state["_pacing_label"] = "⏩ quiet stretch"
        ws._state["_speed_locked"] = True
        ws.save()

        with open(tmp_state, "r", encoding="utf-8") as f:
            on_disk = json.load(f)
        assert "_pacing_label" not in on_disk, "_pacing_label leaked into state.json"
        assert "_speed_locked" not in on_disk, "_speed_locked leaked into state.json"


async def test_23_low_score_dwell_tracking():
    """After a tick with score<=2, _low_score_since is set; once score climbs, it resets."""
    world = make_world()
    world._state["events"] = []
    for agent in world._state["agents"].values():
        agent["mood"] = 50
        agent["last_action"] = "looking around..."
    world._state["speed"] = 1.0
    world._state.pop("_speed_locked", None)

    loop = SimulationLoop(world)
    assert loop._low_score_since is None

    with patch("engine.agent.AgentRunner.tick", new_callable=AsyncMock):
        with patch("engine.needs.decay_all_agents", new_callable=AsyncMock):
            await loop._tick()
    # After a tick at score 0 the timestamp should be set.
    assert loop._low_score_since is not None, "expected _low_score_since to be initialised"

    # Now bump drama and tick again; timestamp should reset.
    world._state["events"] = [
        {"time": "t", "text": "a says to b: hi"} for _ in range(2)
    ] + [
        {"time": "t", "text": "conflict: x vs y on z — w"} for _ in range(2)
    ]
    with patch("engine.agent.AgentRunner.tick", new_callable=AsyncMock):
        with patch("engine.needs.decay_all_agents", new_callable=AsyncMock):
            await loop._tick()
    assert loop._low_score_since is None, "expected _low_score_since to reset on drama"


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

TESTS = [
    ("01. compute_drama_score: empty state -> 0",                 test_01_empty_state_score_zero),
    ("02. compute_drama_score: single talk_to -> 5",              test_02_single_talk_event_scores_5),
    ("03. compute_drama_score: conflict -> 8",                    test_03_conflict_event_scores_8),
    ("04. compute_drama_score: imminent plan -> 10",              test_04_imminent_plan_scores_10),
    ("05. compute_drama_score: distant plan -> 0",                test_05_distant_plan_does_not_score),
    ("06. compute_drama_score: completed plan -> 0",              test_06_completed_plan_does_not_score),
    ("07. compute_drama_score: extreme mood -> +3 each",          test_07_extreme_mood_scores_3_each),
    ("08. compute_drama_score: motion -> +2 each",                test_08_motion_scores_2_each),
    ("09. compute_drama_score: combined sums correctly",          test_09_combined_score_sums_components),
    ("10. pick_speed: locked always returns (1.0, None)",         test_10_locked_returns_default),
    ("11. pick_speed: night override beats drama",                test_11_night_override_beats_drama),
    ("12. pick_speed: high drama (>=15) -> 1x live",              test_12_high_drama_live),
    ("13. pick_speed: 8-14 default band -> 1x",                   test_13_default_band_8_to_14),
    ("14. pick_speed: 3-7 -> 2x quiet stretch",                   test_14_quiet_stretch_2x_with_label),
    ("15. pick_speed: 0-2 within dwell -> 1x",                    test_15_low_score_waits_for_dwell),
    ("16. pick_speed: 0-2 after 60s dwell -> 4x skipping ahead",  test_16_low_score_after_dwell_skips_ahead),
    ("17. pick_speed: 0-2 with no timestamp -> 1x",               test_17_low_score_no_timestamp_stays_1x),
    ("18. _tick: quiet stretch sets speed=2x and label",          test_18_tick_sets_speed_for_quiet_stretch),
    ("19. _tick: high drama returns to 1x, no label",             test_19_tick_keeps_1x_under_high_drama),
    ("20. _tick: manual lock blocks auto-pacing",                 test_20_manual_lock_blocks_auto_pacing),
    ("21. _tick: night auto-speed (>=7 sleeping) still 4x",       test_21_night_auto_speed_still_works),
    ("22. _pacing_label / _speed_locked not persisted to state.json", test_22_pacing_state_keys_not_persisted),
    ("23. _tick: _low_score_since tracks/resets correctly",       test_23_low_score_dwell_tracking),
]


if __name__ == "__main__":
    print("=" * 70)
    print("Story 10.5 — Drama-Driven Auto-Pacing Tests")
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
