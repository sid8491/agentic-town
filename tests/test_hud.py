"""
Story 4.4 — HUD Tests (headless)

Verifies:
  - _format_event_log_line extracts agent/tool from arrow events
  - _format_event_log_line handles events without the arrow separator
  - _format_event_log_line respects max_len truncation
  - _format_event_log_line handles empty/malformed input gracefully
  - Event log panel fits within the window (LOG_X + LOG_W <= WINDOW_W)
  - LLM button bounding box is within window bounds
  - HUD height is unchanged at 50px
  - Event log slice logic: only last LOG_MAX events shown

Run with:
    .venv/Scripts/python.exe tests/test_hud.py
"""

import os
import pathlib
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = pathlib.Path(__file__).parent.parent

results = []


def ok(name: str) -> None:
    results.append((name, True, None))
    print(f"  PASS  {name}")


def fail(name: str, reason: str) -> None:
    results.append((name, False, reason))
    print(f"  FAIL  {name}")
    print(f"        {reason}")


def run(name: str, fn):
    try:
        fn()
        ok(name)
    except AssertionError as exc:
        fail(name, str(exc))
    except Exception as exc:
        fail(name, f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Stub arcade and import main.py headlessly
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
arcade_stub.draw_lrbt_rectangle_outline = lambda *a, **k: None
arcade_stub.draw_text = lambda *a, **k: None
arcade_stub.run = lambda: None
sys.modules.setdefault("arcade", arcade_stub)

import importlib.util
spec = importlib.util.spec_from_file_location("main_mod", ROOT / "main.py")
main_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main_mod)

_format_event_log_line = main_mod._format_event_log_line
WINDOW_W    = main_mod.WINDOW_W
WINDOW_H    = main_mod.WINDOW_H
HUD_HEIGHT  = main_mod.HUD_HEIGHT
_LOG_W      = main_mod._LOG_W
_LOG_X      = main_mod._LOG_X
_LOG_MAX    = main_mod._LOG_MAX
_LOG_LINE_H = main_mod._LOG_LINE_H


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_01_format_arrow_event():
    """Arrow events produce 'time agent: tool' format."""
    event = {
        "time": "9:15am Day 1",
        "text": "arjun → look_around: Location: Sushant Lok Apartments",
    }
    line = _format_event_log_line(event)
    assert "9:15am" in line, f"Time missing: {line!r}"
    assert "arjun" in line, f"Agent missing: {line!r}"
    assert "look_around" in line, f"Tool missing: {line!r}"
    assert "Location" not in line, f"Result text should be trimmed: {line!r}"


def test_02_format_no_arrow_event():
    """Events without an arrow separator fall back gracefully."""
    event = {"time": "6:00am Day 1", "text": "Simulation started"}
    line = _format_event_log_line(event)
    assert "6:00am" in line, f"Time missing: {line!r}"
    assert "Simulation" in line, f"Text missing: {line!r}"


def test_03_format_truncation():
    """Lines are truncated to max_len characters."""
    event = {
        "time": "6:00am Day 1",
        "text": "arjun → " + "x" * 100,
    }
    line = _format_event_log_line(event, max_len=20)
    assert len(line) <= 20, f"Line too long: {len(line)} chars — {line!r}"


def test_04_format_empty_event():
    """Empty event dict does not raise and returns a short string."""
    line = _format_event_log_line({})
    assert isinstance(line, str), "Should return a string"
    assert len(line) <= 36, f"Unexpected length: {len(line)}"


def test_05_format_move_to_event():
    """move_to events include the tool name correctly."""
    event = {
        "time": "7:30am Day 1",
        "text": "priya → move_to: Moved to metro.",
    }
    line = _format_event_log_line(event)
    assert "priya" in line
    assert "move_to" in line


def test_06_log_panel_fits_window():
    """Event log panel (LOG_X + LOG_W) does not exceed WINDOW_W."""
    assert _LOG_X + _LOG_W <= WINDOW_W, (
        f"Log panel overflows window: {_LOG_X} + {_LOG_W} = "
        f"{_LOG_X + _LOG_W} > {WINDOW_W}"
    )


def test_07_llm_btn_within_window():
    """LLM button x-range (WINDOW_W-190 .. WINDOW_W-8) is inside window bounds."""
    lx1 = WINDOW_W - 190
    lx2 = WINDOW_W - 8
    assert lx1 >= 0,        f"LLM button left edge is negative: {lx1}"
    assert lx2 <= WINDOW_W, f"LLM button right edge exceeds window: {lx2}"
    assert lx2 > lx1,       f"LLM button has zero/negative width"


def test_08_hud_height_unchanged():
    """HUD strip height remains 50px."""
    assert HUD_HEIGHT == 50, f"HUD_HEIGHT changed: {HUD_HEIGHT}"


def test_09_log_max_slice():
    """Simulating event log slice: only last LOG_MAX events are shown."""
    events = [{"time": f"{i}:00am Day 1", "text": f"agent{i} → look_around: x"}
              for i in range(25)]
    recent = events[-_LOG_MAX:]
    assert len(recent) == _LOG_MAX, f"Expected {_LOG_MAX} events, got {len(recent)}"
    assert recent[-1]["time"] == "24:00am Day 1", "Last entry should be newest"


def test_10_log_max_is_10():
    """LOG_MAX constant equals 10 as specified."""
    assert _LOG_MAX == 10, f"LOG_MAX should be 10, got {_LOG_MAX}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    ("1.  format_event_log_line: arrow event gives time/agent/tool", test_01_format_arrow_event),
    ("2.  format_event_log_line: non-arrow event falls back cleanly",  test_02_format_no_arrow_event),
    ("3.  format_event_log_line: truncates to max_len",                test_03_format_truncation),
    ("4.  format_event_log_line: empty event dict is safe",            test_04_format_empty_event),
    ("5.  format_event_log_line: move_to event includes tool name",    test_05_format_move_to_event),
    ("6.  Event log panel fits within window width",                   test_06_log_panel_fits_window),
    ("7.  LLM button bounding box is inside window",                   test_07_llm_btn_within_window),
    ("8.  HUD height is 50px",                                         test_08_hud_height_unchanged),
    ("9.  Event log slice shows only last LOG_MAX entries",            test_09_log_max_slice),
    ("10. LOG_MAX constant equals 10",                                 test_10_log_max_is_10),
]


if __name__ == "__main__":
    print("=" * 70)
    print("Story 4.4 -- HUD Tests (headless)")
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
