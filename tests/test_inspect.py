"""
Story 4.5 — Click to Inspect Agent Tests (headless)

Verifies:
  - _parse_diary_entries splits correctly on # Day headers
  - Returns last N entries (not more)
  - Skips entries with no body text
  - Handles empty / missing diary gracefully
  - _agent_hit returns correct agent within click radius
  - _agent_hit returns None for clicks outside all radii
  - _PANEL_X + _PANEL_W == WINDOW_W (panel spans to right edge)
  - Panel constants do not overflow window

Run with:
    .venv/Scripts/python.exe tests/test_inspect.py
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

_parse_diary_entries = main_mod._parse_diary_entries
_agent_hit           = main_mod._agent_hit
AGENT_RADIUS         = main_mod.AGENT_RADIUS
WINDOW_W             = main_mod.WINDOW_W
WINDOW_H             = main_mod.WINDOW_H
HUD_HEIGHT           = main_mod.HUD_HEIGHT
_PANEL_W             = main_mod._PANEL_W
_PANEL_X             = main_mod._PANEL_X


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

_SAMPLE_DIARY = """
# Day 1 — 6:00am
Woke up feeling restless. The corridor smelled of dal.

# Day 1 — 9:15am
Sent a message to Kavya. Fingers crossed.

# Day 1 — 1:00pm
The afternoon felt long but grounding. Needed the quiet.

# Day 2 — 8:00am
Fresh day. The morning air was cooler than expected.
"""

_DIARY_WITH_EMPTY = """
# Day 1 — 6:00am

# Day 1 — 9:00am
This entry has content.

# Day 1 — 3:00pm
Another entry.
"""


def test_01_parse_returns_last_n():
    """_parse_diary_entries returns at most n entries."""
    entries = _parse_diary_entries(_SAMPLE_DIARY, n=3)
    assert len(entries) == 3, f"Expected 3, got {len(entries)}"


def test_02_parse_newest_last():
    """The last returned entry is the newest one in the file."""
    entries = _parse_diary_entries(_SAMPLE_DIARY, n=3)
    last_header, _ = entries[-1]
    assert "Day 2" in last_header, f"Expected Day 2 entry last, got: {last_header!r}"


def test_03_parse_header_strips_prefix():
    """Headers have the '# ' prefix stripped."""
    entries = _parse_diary_entries(_SAMPLE_DIARY, n=1)
    header, _ = entries[0]
    assert not header.startswith("#"), f"Header still has '#': {header!r}"
    assert "Day" in header


def test_04_parse_skips_empty_bodies():
    """Entries with no body text are silently skipped."""
    entries = _parse_diary_entries(_DIARY_WITH_EMPTY, n=10)
    # Only 2 of the 3 headers have bodies
    assert len(entries) == 2, f"Expected 2 non-empty entries, got {len(entries)}"
    for _, body in entries:
        assert body.strip(), "Body should not be empty"


def test_05_parse_empty_string():
    """Empty text returns an empty list without error."""
    entries = _parse_diary_entries("", n=3)
    assert entries == [], f"Expected [], got {entries}"


def test_06_parse_no_headers():
    """Text with no # Day headers returns an empty list."""
    entries = _parse_diary_entries("Just some random text\nNo headers here.", n=3)
    assert entries == [], f"Expected [], got {entries}"


def test_07_parse_n_larger_than_entries():
    """Requesting more entries than exist returns all available."""
    entries = _parse_diary_entries(_SAMPLE_DIARY, n=10)
    assert len(entries) == 4, f"Expected 4 entries, got {len(entries)}"


def test_08_agent_hit_inside_radius():
    """_agent_hit returns agent name when click is inside the circle."""
    agent_cur = {"arjun": [100.0, 200.0], "priya": [400.0, 300.0]}
    # Click exactly on arjun's centre
    result = _agent_hit(agent_cur, 100.0, 200.0)
    assert result == "arjun", f"Expected 'arjun', got {result!r}"


def test_09_agent_hit_outside_radius():
    """_agent_hit returns None when click misses all agents."""
    agent_cur = {"arjun": [100.0, 200.0], "priya": [400.0, 300.0]}
    result = _agent_hit(agent_cur, 500.0, 500.0)
    assert result is None, f"Expected None, got {result!r}"


def test_10_agent_hit_edge_of_radius():
    """_agent_hit returns name when click is exactly at the hit radius."""
    radius = AGENT_RADIUS + 6
    agent_cur = {"arjun": [100.0, 200.0]}
    # Click at exactly (radius, 0) offset — should be included
    result = _agent_hit(agent_cur, 100.0 + radius, 200.0)
    assert result == "arjun", f"Expected 'arjun' at edge, got {result!r}"


def test_11_panel_spans_to_right_edge():
    """_PANEL_X + _PANEL_W equals WINDOW_W (panel goes to the right window edge)."""
    assert _PANEL_X + _PANEL_W == WINDOW_W, (
        f"Panel doesn't reach right edge: {_PANEL_X} + {_PANEL_W} = "
        f"{_PANEL_X + _PANEL_W} != {WINDOW_W}"
    )


def test_12_panel_x_positive():
    """Panel starts well inside the window (leaves map space on the left)."""
    assert _PANEL_X > 400, f"Panel too wide, starts at x={_PANEL_X}"
    assert _PANEL_X < WINDOW_W, "Panel starts outside window"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    ("1.  parse_diary_entries: returns at most n entries",               test_01_parse_returns_last_n),
    ("2.  parse_diary_entries: newest entry is last",                    test_02_parse_newest_last),
    ("3.  parse_diary_entries: header has no '#' prefix",                test_03_parse_header_strips_prefix),
    ("4.  parse_diary_entries: skips entries with empty bodies",         test_04_parse_skips_empty_bodies),
    ("5.  parse_diary_entries: empty string returns []",                 test_05_parse_empty_string),
    ("6.  parse_diary_entries: text with no headers returns []",         test_06_parse_no_headers),
    ("7.  parse_diary_entries: n > available entries returns all",       test_07_parse_n_larger_than_entries),
    ("8.  agent_hit: click inside circle returns agent name",            test_08_agent_hit_inside_radius),
    ("9.  agent_hit: click outside all circles returns None",            test_09_agent_hit_outside_radius),
    ("10. agent_hit: click exactly at edge of hit radius is a hit",      test_10_agent_hit_edge_of_radius),
    ("11. Panel spans from _PANEL_X to right window edge",               test_11_panel_spans_to_right_edge),
    ("12. Panel x-start leaves map space (> 400px from left)",           test_12_panel_x_positive),
]


if __name__ == "__main__":
    print("=" * 70)
    print("Story 4.5 -- Click to Inspect Agent Tests (headless)")
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
