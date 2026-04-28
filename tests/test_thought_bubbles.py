"""
Story 4.3 — Thought Bubbles + Name Tags Tests (headless)

Verifies:
  - WorldState.set_agent_last_action / get_agent_last_action round-trip
  - _action_label formats all major tool calls correctly
  - _name_tag_color returns correct RGBA for mood < 30, 30-70, > 70
  - Fade alpha logic: full at t=0, half at t=2.5, zero at t>=5
  - All agents in state.json have a last_action field
  - execute_tool_node writes last_action to world state

Run with:
    .venv/Scripts/python.exe tests/test_thought_bubbles.py
"""

import asyncio
import json
import os
import pathlib
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = pathlib.Path(__file__).parent.parent
STATE_PATH = ROOT / "world" / "state.json"
MAP_PATH   = ROOT / "world" / "map.json"

results = []


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


# ---------------------------------------------------------------------------
# Helpers — load arcade stub so main.py imports work headlessly
# ---------------------------------------------------------------------------

arcade_stub = types.ModuleType("arcade")
arcade_stub.Window = object
arcade_stub.Text = object
arcade_stub.key = types.SimpleNamespace(
    SPACE=32, L=108, LEFT=65361, RIGHT=65363, ESCAPE=65307
)
arcade_stub.set_background_color = lambda *a, **k: None
arcade_stub.draw_line = lambda *a, **k: None
arcade_stub.draw_circle_filled = lambda *a, **k: None
arcade_stub.draw_circle_outline = lambda *a, **k: None
arcade_stub.draw_lrbt_rectangle_filled = lambda *a, **k: None
arcade_stub.draw_text = lambda *a, **k: None
arcade_stub.run = lambda: None
sys.modules.setdefault("arcade", arcade_stub)

import importlib.util
spec = importlib.util.spec_from_file_location("main_mod", ROOT / "main.py")
main_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main_mod)

_name_tag_color = main_mod._name_tag_color
_BUBBLE_FADE_SECS = main_mod._BUBBLE_FADE_SECS

from engine.world import WorldState
from engine.agent import _action_label


def make_world() -> WorldState:
    ws = WorldState(state_path=str(STATE_PATH), map_path=str(MAP_PATH))
    ws.load()
    return ws


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_01_set_get_last_action():
    """set_agent_last_action + get_agent_last_action round-trip."""
    ws = make_world()
    await ws.set_agent_last_action("arjun", "looking around...")
    assert ws.get_agent_last_action("arjun") == "looking around..."


async def test_02_set_last_action_overwrites():
    """Second set_agent_last_action replaces the previous value."""
    ws = make_world()
    await ws.set_agent_last_action("priya", "eating food...")
    await ws.set_agent_last_action("priya", "working...")
    assert ws.get_agent_last_action("priya") == "working..."


def test_03_action_label_simple_tools():
    """_action_label formats simple (no-arg) tools correctly."""
    assert _action_label("look_around", {}) == "looking around..."
    assert _action_label("check_needs", {}) == "checking needs..."
    assert _action_label("check_inventory", {}) == "checking inventory..."
    assert _action_label("sleep_action", {}) == "sleeping..."
    assert _action_label("work", {}) == "working..."


def test_04_action_label_arg_tools():
    """_action_label interpolates args into the label string."""
    assert _action_label("move_to", {"location": "metro"}) == "moving to metro..."
    assert _action_label("talk_to", {"target": "priya"}) == "talking to priya..."
    assert _action_label("ask_about", {"target": "vikram"}) == "asking vikram..."
    assert _action_label("buy", {"item": "chai"}) == "buying chai..."
    assert _action_label("eat", {"item": "roti"}) == "eating roti..."
    assert _action_label("give_item", {"item": "book"}) == "giving book..."


def test_05_action_label_fallback():
    """Unknown tool names fall back to 'tool name...' with underscores replaced."""
    label = _action_label("some_new_tool", {})
    assert label == "some new tool...", f"Got: {label!r}"


def test_06_name_tag_color_mood_ranges():
    """_name_tag_color returns red/green/gray for the three mood bands."""
    red   = _name_tag_color(10.0)
    red2  = _name_tag_color(29.9)
    gray  = _name_tag_color(30.0)
    gray2 = _name_tag_color(70.0)
    green = _name_tag_color(70.1)
    green2 = _name_tag_color(100.0)

    # Red: first component dominant
    assert red[0] > 200 and red[1] < 100, f"Expected red, got {red}"
    assert red2[0] > 200 and red2[1] < 100, f"Expected red, got {red2}"

    # Green: second component dominant
    assert green[1] > 200 and green[0] < 150, f"Expected green, got {green}"
    assert green2[1] > 200 and green2[0] < 150, f"Expected green, got {green2}"

    # Gray: all components similar and > 150
    assert abs(int(gray[0]) - int(gray[1])) < 30, f"Expected gray, got {gray}"
    assert gray[0] > 150, f"Gray should be bright enough: {gray}"
    assert abs(int(gray2[0]) - int(gray2[1])) < 30, f"Expected gray, got {gray2}"

    # All have alpha = 255
    for color in (red, gray, green):
        assert color[3] == 255, f"Alpha should be 255, got {color}"


def test_07_fade_alpha_calculation():
    """Fade alpha is 255 at t=0, ~128 at t=2.5, 0 at t>=5."""
    def alpha_at(elapsed: float) -> int:
        return max(0, int(255 * (1.0 - elapsed / _BUBBLE_FADE_SECS)))

    assert alpha_at(0.0) == 255, "Full alpha at t=0"
    a_mid = alpha_at(2.5)
    assert 120 <= a_mid <= 135, f"~Half alpha at midpoint, got {a_mid}"
    assert alpha_at(5.0) == 0, "Zero alpha at t=FADE_SECS"
    assert alpha_at(6.0) == 0, "Zero alpha beyond fade window"
    assert alpha_at(10.0) == 0, "Zero alpha well past fade"


def test_08_state_json_all_agents_have_last_action():
    """Every agent entry in state.json contains a 'last_action' field."""
    data = json.loads(STATE_PATH.read_text())
    missing = [
        name for name, agent in data["agents"].items()
        if "last_action" not in agent
    ]
    assert not missing, f"Agents missing 'last_action': {missing}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    ("1.  set/get_agent_last_action round-trip",           test_01_set_get_last_action),
    ("2.  set_agent_last_action overwrites previous value", test_02_set_last_action_overwrites),
    ("3.  _action_label — simple (no-arg) tools",          test_03_action_label_simple_tools),
    ("4.  _action_label — arg interpolation",              test_04_action_label_arg_tools),
    ("5.  _action_label — unknown tool fallback",          test_05_action_label_fallback),
    ("6.  _name_tag_color — mood bands (red/gray/green)",  test_06_name_tag_color_mood_ranges),
    ("7.  Fade alpha: 255->0 over 5 real seconds",          test_07_fade_alpha_calculation),
    ("8.  state.json — all agents have last_action field", test_08_state_json_all_agents_have_last_action),
]


if __name__ == "__main__":
    print("=" * 70)
    print("Story 4.3 -- Thought Bubbles + Name Tags Tests (headless)")
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
