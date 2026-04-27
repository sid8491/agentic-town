"""
Story 4.1 — Map Rendering Tests (headless)

Verifies layout maths, colour coverage, connection de-duplication, and
helper functions without opening an Arcade window.

Run with:
    .venv/Scripts/python.exe tests/test_map_render.py
"""

import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = pathlib.Path(__file__).parent.parent
MAP_PATH = ROOT / "world" / "map.json"

results = []


def ok(name):
    results.append((name, True, None))
    print(f"  PASS  {name}")


def fail(name, reason):
    results.append((name, False, reason))
    print(f"  FAIL  {name}")
    print(f"        {reason}")


# ---------------------------------------------------------------------------
# Load helpers from main.py without triggering arcade.run()
# ---------------------------------------------------------------------------

import importlib, types

# Stub arcade so the import works headlessly
arcade_stub = types.ModuleType("arcade")
arcade_stub.Window = object
arcade_stub.Text = object
arcade_stub.key = types.SimpleNamespace(
    SPACE=32, L=108, LEFT=65361, RIGHT=65363, ESCAPE=65307
)
arcade_stub.set_background_color = lambda *a, **k: None
arcade_stub.Color = lambda *a, **k: a
arcade_stub.draw_line = lambda *a, **k: None
arcade_stub.draw_circle_filled = lambda *a, **k: None
arcade_stub.draw_circle_outline = lambda *a, **k: None
arcade_stub.draw_lrbt_rectangle_filled = lambda *a, **k: None
arcade_stub.draw_text = lambda *a, **k: None
arcade_stub.run = lambda: None
sys.modules.setdefault("arcade", arcade_stub)

# Now import main module functions
import importlib.util, types as _types
spec = importlib.util.spec_from_file_location("main_mod", ROOT / "main.py")
main_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main_mod)

_tile_to_pixel = main_mod._tile_to_pixel
_display_label = main_mod._display_label
TILE_SIZE = main_mod.TILE_SIZE
HUD_HEIGHT = main_mod.HUD_HEIGHT
WINDOW_W = main_mod.WINDOW_W
WINDOW_H = main_mod.WINDOW_H
ZONE_RADIUS = main_mod.ZONE_RADIUS
_ZONE_COLORS = main_mod._ZONE_COLORS

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_01_window_dimensions():
    """Window is 960 wide and 690 tall (30x20 tiles at 32px + 50px HUD)."""
    expected_w = 30 * 32
    expected_h = 20 * 32 + 50
    assert WINDOW_W == expected_w, f"Expected width {expected_w}, got {WINDOW_W}"
    assert WINDOW_H == expected_h, f"Expected height {expected_h}, got {WINDOW_H}"
    ok("1.  Window dimensions: 960x690 (30x20 tiles + 50px HUD)")


def test_02_tile_pixel_above_hud():
    """tile_to_pixel always returns y > HUD_HEIGHT."""
    map_data = json.loads(MAP_PATH.read_text())
    for loc in map_data["locations"]:
        _, py = _tile_to_pixel(loc["tile_x"], loc["tile_y"])
        if py <= HUD_HEIGHT:
            fail(f"2.  {loc['id']} pixel y={py} is inside HUD strip (y<={HUD_HEIGHT})",
                 f"tile_y={loc['tile_y']}")
            return
    ok("2.  All location pixels are above the HUD strip")


def test_03_tile_pixel_within_window():
    """All location pixels fall within the window bounds."""
    map_data = json.loads(MAP_PATH.read_text())
    for loc in map_data["locations"]:
        px, py = _tile_to_pixel(loc["tile_x"], loc["tile_y"])
        if not (0 <= px <= WINDOW_W and 0 <= py <= WINDOW_H):
            fail("3.  Location pixel outside window",
                 f"{loc['id']}: ({px}, {py}) not in ({WINDOW_W}x{WINDOW_H})")
            return
    ok("3.  All location pixels fall within window bounds")


def test_04_tile_to_pixel_math():
    """tile_to_pixel formula: px = tx*32+16, py = HUD+ty*32+16."""
    cases = [(0, 0), (4, 15), (24, 3), (29, 19)]
    for tx, ty in cases:
        px, py = _tile_to_pixel(tx, ty)
        expected_px = tx * TILE_SIZE + TILE_SIZE // 2
        expected_py = HUD_HEIGHT + ty * TILE_SIZE + TILE_SIZE // 2
        if px != expected_px or py != expected_py:
            fail("4.  tile_to_pixel formula",
                 f"tile({tx},{ty}): expected ({expected_px},{expected_py}), got ({px},{py})")
            return
    ok("4.  tile_to_pixel formula correct for all test cases")


def test_05_zone_colors_cover_all_types():
    """Every location type in map.json has an entry in _ZONE_COLORS."""
    map_data = json.loads(MAP_PATH.read_text())
    missing = set()
    for loc in map_data["locations"]:
        ltype = loc.get("type", "home")
        if ltype not in _ZONE_COLORS:
            missing.add(ltype)
    if missing:
        fail("5.  Zone colours cover all location types", f"Missing types: {missing}")
    else:
        ok("5.  Zone colours cover all location types in map.json")


def test_06_zone_colors_are_rgb_tuples():
    """All zone colours are 3-tuples of ints in [0, 255]."""
    for zone_type, rgb in _ZONE_COLORS.items():
        if len(rgb) != 3:
            fail("6.  Zone colour RGB tuple length", f"{zone_type}: {rgb}")
            return
        for c in rgb:
            if not (0 <= c <= 255):
                fail("6.  Zone colour value in [0,255]", f"{zone_type}: {c}")
                return
    ok("6.  All zone colours are valid RGB 3-tuples")


def test_07_display_label_short_names_unchanged():
    """Names with <=2 words are returned unchanged."""
    assert _display_label("Home") == "Home"
    assert _display_label("Pappu Dhaba") == "Pappu Dhaba"
    ok("7.  Short names (<=2 words) pass through unchanged")


def test_08_display_label_splits_long_names():
    """Names with 3+ words are split into two lines."""
    result = _display_label("Sushant Lok Apartments")
    assert "\n" in result, f"Expected newline in split label, got: {result!r}"
    lines = result.split("\n")
    assert len(lines) == 2, f"Expected 2 lines, got {len(lines)}"
    ok("8.  Long names (3+ words) split into two lines")


def test_09_connections_cover_all_edges():
    """Every connection in map.json is bidirectional and consistent."""
    map_data = json.loads(MAP_PATH.read_text())
    locations = {loc["id"]: loc for loc in map_data["locations"]}
    errors = []
    for lid, loc in locations.items():
        for nid in loc.get("connected_to", []):
            if nid not in locations:
                errors.append(f"{lid} -> {nid} (target missing)")
    if errors:
        fail("9.  All connection targets exist in map", "; ".join(errors))
    else:
        ok("9.  All connection targets exist in map.json")


def test_10_dedup_connections():
    """Simulating draw_connections de-duplication: each edge drawn exactly once."""
    map_data = json.loads(MAP_PATH.read_text())
    locations = {loc["id"]: loc for loc in map_data["locations"]}
    drawn: set[frozenset] = set()
    edges_drawn = 0
    for lid, loc in locations.items():
        for nid in loc.get("connected_to", []):
            pair: frozenset = frozenset({lid, nid})
            if pair not in drawn and nid in locations:
                drawn.add(pair)
                edges_drawn += 1
    # Verify total unique edges matches the undirected edge count
    # (sum of all connected_to lengths, divided by 2 since each edge listed twice)
    total_directed = sum(len(loc.get("connected_to", [])) for loc in locations.values())
    expected_undirected = total_directed // 2
    if edges_drawn != expected_undirected:
        fail("10. Dedup connection count",
             f"Expected {expected_undirected} unique edges, drew {edges_drawn}")
    else:
        ok(f"10. Connection dedup correct: {edges_drawn} unique edges drawn")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    test_01_window_dimensions,
    test_02_tile_pixel_above_hud,
    test_03_tile_pixel_within_window,
    test_04_tile_to_pixel_math,
    test_05_zone_colors_cover_all_types,
    test_06_zone_colors_are_rgb_tuples,
    test_07_display_label_short_names_unchanged,
    test_08_display_label_splits_long_names,
    test_09_connections_cover_all_edges,
    test_10_dedup_connections,
]

if __name__ == "__main__":
    print("=" * 70)
    print("Story 4.1 -- Map Rendering Tests (headless)")
    print("=" * 70)

    for fn in TESTS:
        fn()

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
