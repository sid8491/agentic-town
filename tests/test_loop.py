"""
Story 3.2 — SimulationLoop Tests
Verifies the multi-agent async tick loop in engine/world.py.

Run with:
    .venv/Scripts/python.exe tests/test_loop.py

All tests mock AgentRunner.tick and decay_all_agents so no live LLM is needed.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.world import WorldState, SimulationLoop

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(ROOT, "world", "state.json")
MAP_PATH = os.path.join(ROOT, "world", "map.json")

results = []


def run_test(name, coro_or_fn):
    """Execute a sync or async test and record PASS / FAIL."""
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
    """Create and load a fresh WorldState for each test."""
    ws = WorldState(state_path=STATE_PATH, map_path=MAP_PATH)
    ws.load()
    return ws


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_01_instantiates():
    """SimulationLoop instantiates with a WorldState without error."""
    world = make_world()
    loop = SimulationLoop(world)
    assert loop is not None
    assert loop.world is world


def test_02_running_false_before_start():
    """loop.running is False before start() is called."""
    world = make_world()
    loop = SimulationLoop(world)
    assert loop.running is False, f"Expected running=False, got {loop.running}"


async def test_03_running_true_after_start():
    """After loop.start(), loop.running is True."""
    world = make_world()
    loop = SimulationLoop(world)

    with patch("engine.agent.AgentRunner.tick", new_callable=AsyncMock):
        with patch("engine.needs.decay_all_agents", new_callable=AsyncMock):
            task = loop.start()
            # Give the event loop a moment to schedule the coroutine
            await asyncio.sleep(0)
            assert loop.running is True, f"Expected running=True after start(), got {loop.running}"
            loop.stop()
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass


async def test_04_stop_sets_running_false():
    """loop.stop() sets running to False."""
    world = make_world()
    loop = SimulationLoop(world)

    with patch("engine.agent.AgentRunner.tick", new_callable=AsyncMock):
        with patch("engine.needs.decay_all_agents", new_callable=AsyncMock):
            task = loop.start()
            await asyncio.sleep(0)
            loop.stop()
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            assert loop.running is False, f"Expected running=False after stop(), got {loop.running}"


async def test_05_tick_advances_time_15_minutes():
    """One tick advances sim_time by exactly 15 game minutes."""
    world = make_world()
    start_time = world.get_time()["sim_time"]
    loop = SimulationLoop(world)

    with patch("engine.agent.AgentRunner.tick", new_callable=AsyncMock):
        with patch("engine.needs.decay_all_agents", new_callable=AsyncMock):
            await loop._tick()

    end_time = world.get_time()["sim_time"]
    # Handle day-rollover: compute delta mod 1440
    delta = (end_time - start_time) % 1440
    assert delta == 15, f"Expected sim_time to advance by 15, got {delta}"


async def test_06_tick_calls_decay_all_agents():
    """One tick calls decay_all_agents exactly once."""
    world = make_world()
    loop = SimulationLoop(world)

    with patch("engine.agent.AgentRunner.tick", new_callable=AsyncMock):
        with patch("engine.needs.decay_all_agents", new_callable=AsyncMock) as mock_decay:
            await loop._tick()

    mock_decay.assert_called_once()
    # Verify it was called with the correct tick minutes
    args, kwargs = mock_decay.call_args
    assert args[0] == SimulationLoop.TICK_MINUTES, (
        f"Expected decay_all_agents({SimulationLoop.TICK_MINUTES}), "
        f"got decay_all_agents({args[0] if args else '?'})"
    )


async def test_07_tick_calls_all_10_agents():
    """One tick calls AgentRunner.tick exactly 10 times (one per agent)."""
    world = make_world()
    loop = SimulationLoop(world)

    with patch("engine.agent.AgentRunner.tick", new_callable=AsyncMock) as mock_tick:
        with patch("engine.needs.decay_all_agents", new_callable=AsyncMock):
            await loop._tick()

    assert mock_tick.call_count == 10, (
        f"Expected AgentRunner.tick called 10 times, got {mock_tick.call_count}"
    )


async def test_08_paused_state_does_not_advance_time():
    """When world.paused=True, the loop does NOT advance sim_time after 0.6 seconds."""
    world = make_world()
    # Set world to paused
    world._state["paused"] = True
    start_time = world.get_time()["sim_time"]
    loop = SimulationLoop(world)

    with patch("engine.agent.AgentRunner.tick", new_callable=AsyncMock):
        with patch("engine.needs.decay_all_agents", new_callable=AsyncMock):
            task = loop.start()
            # Wait longer than the pause sleep (0.5s) but time should NOT advance
            await asyncio.sleep(0.6)
            loop.stop()
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    end_time = world.get_time()["sim_time"]
    assert end_time == start_time, (
        f"Expected sim_time unchanged while paused. "
        f"start={start_time}, end={end_time}"
    )


async def test_09_speed_multiplier_affects_interval():
    """At speed=2.0, tick interval is BASE_INTERVAL/2 = 1.5 seconds."""
    world = make_world()
    world._state["speed"] = 2.0
    world._state["paused"] = False
    loop = SimulationLoop(world)

    tick_count = 0

    async def fake_tick():
        nonlocal tick_count
        tick_count += 1

    loop._tick = fake_tick  # replace with lightweight version

    task = loop.start()
    # At 2x speed: interval = 1.5s. After 4 seconds we expect at least 2 ticks.
    await asyncio.sleep(4.0)
    loop.stop()
    try:
        await asyncio.wait_for(task, timeout=1.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass

    # At 1.5s interval: 4s / 1.5s ≈ 2-3 ticks
    assert tick_count >= 2, (
        f"At speed=2.0 (interval=1.5s), expected >=2 ticks in 4s, got {tick_count}"
    )
    # And NOT as many as at 1x speed (would be ~1 tick/3s → ~1)
    # The key check is that it's faster than 1x
    base_ticks_in_4s = 4.0 / SimulationLoop.BASE_INTERVAL  # ~1.33 at 1x
    assert tick_count >= base_ticks_in_4s, (
        f"Expected more ticks at 2x speed than 1x speed. "
        f"Got {tick_count}, 1x would yield ~{base_ticks_in_4s:.1f}"
    )


async def test_10_failed_agent_does_not_stop_others():
    """One agent raising an exception does NOT prevent the other 9 from running."""
    world = make_world()
    loop = SimulationLoop(world)

    call_count = 0

    async def sometimes_fails():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Simulated agent failure")

    with patch("engine.agent.AgentRunner.tick", side_effect=sometimes_fails):
        with patch("engine.needs.decay_all_agents", new_callable=AsyncMock):
            # Should not raise — exception is caught internally
            await loop._tick()

    # All 10 agents should have been attempted despite 1 failure
    assert call_count == 10, (
        f"Expected 10 agent tick attempts (even with 1 failure), got {call_count}"
    )


async def test_11_save_async_called_after_tick():
    """After one tick, world.save_async() is called exactly once."""
    world = make_world()
    loop = SimulationLoop(world)

    with patch("engine.agent.AgentRunner.tick", new_callable=AsyncMock):
        with patch("engine.needs.decay_all_agents", new_callable=AsyncMock):
            with patch.object(world, "save_async", new_callable=AsyncMock) as mock_save:
                await loop._tick()

    mock_save.assert_called_once()


async def test_12_start_idempotent():
    """Calling loop.start() twice returns the same task (idempotent)."""
    world = make_world()
    loop = SimulationLoop(world)

    with patch("engine.agent.AgentRunner.tick", new_callable=AsyncMock):
        with patch("engine.needs.decay_all_agents", new_callable=AsyncMock):
            task1 = loop.start()
            task2 = loop.start()
            assert task1 is task2, (
                "start() called twice must return the same Task object"
            )
            loop.stop()
            try:
                await asyncio.wait_for(task1, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

TESTS = [
    ("1.  SimulationLoop instantiates with WorldState without error", test_01_instantiates),
    ("2.  loop.running is False before start()", test_02_running_false_before_start),
    ("3.  loop.running is True after start()", test_03_running_true_after_start),
    ("4.  loop.stop() sets running to False", test_04_stop_sets_running_false),
    ("5.  One tick advances sim_time by 15 game minutes", test_05_tick_advances_time_15_minutes),
    ("6.  One tick calls decay_all_agents once with TICK_MINUTES", test_06_tick_calls_decay_all_agents),
    ("7.  One tick calls AgentRunner.tick 10 times (all agents)", test_07_tick_calls_all_10_agents),
    ("8.  Paused state: sim_time does NOT advance after 0.6s", test_08_paused_state_does_not_advance_time),
    ("9.  Speed=2.0: tick interval is ~1.5s (faster than 1x)", test_09_speed_multiplier_affects_interval),
    ("10. Failed agent tick is caught — others still run (10 attempts)", test_10_failed_agent_does_not_stop_others),
    ("11. After one tick, world.save_async() is called once", test_11_save_async_called_after_tick),
    ("12. loop.start() called twice returns same task (idempotent)", test_12_start_idempotent),
]


if __name__ == "__main__":
    print("=" * 70)
    print("Story 3.2 — SimulationLoop Tests")
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
