"""tests/test_viewer_round2.py — Epic 10 Round 2 viewer assertions.

These tests verify that viewer.html was patched with the Round-2 features.
We do NOT execute the JS — instead we assert the presence of expected
anchor strings inside the decoded template, plus the absence of the
"trivially equal" baseline (i.e., the file actually changed compared to
a hypothetical un-patched template that has none of the markers).

Run with:
    .venv/Scripts/python.exe tests/test_viewer_round2.py
"""

import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts.viewer_edit import ViewerBundle

VIEWER = os.path.join(ROOT, "viewer.html")

results = []


def run_test(name, fn):
    try:
        fn()
        results.append((name, True, None))
        print(f"  PASS  {name}")
    except Exception as exc:
        results.append((name, False, str(exc)))
        print(f"  FAIL  {name}")
        print(f"        {exc}")


def _template():
    return ViewerBundle.read(VIEWER).template


def test_01_marker_present():
    t = _template()
    assert "EPIC10R2_MARK" in t, "Round-2 marker missing"


def test_02_director_anchors():
    t = _template()
    for needle in ("directorMode", "Following:", "director-toggle",
                   "_setProtagonist", "directorOverrideUntilMs"):
        assert needle in t, f"missing director-mode anchor: {needle!r}"


def test_03_narration_anchors():
    t = _template()
    for needle in ("narration-bar", "_pushNarration",
                   "speechSynthesis", "/api/narration"):
        assert needle in t, f"missing narration anchor: {needle!r}"


def test_04_plot_threads_anchors():
    t = _template()
    for needle in ("plot_threads", "threads-sidebar",
                   "thread-card", "_threadsHidden"):
        assert needle in t, f"missing plot-threads anchor: {needle!r}"


def test_05_pacing_label_anchors():
    t = _template()
    for needle in ("pacing_label", "pacing-pill", "_refreshPacingPill"):
        assert needle in t, f"missing pacing anchor: {needle!r}"


def test_06_mood_floater_anchors():
    t = _template()
    for needle in ("mood-floater", "_emitFloater", "_prevMood",
                   "_checkMoodFloaters"):
        assert needle in t, f"missing mood-floater anchor: {needle!r}"


def test_07_epic9_indicators_anchors():
    t = _template()
    for needle in ("financial_stress", "scheduled_events",
                   "_refreshFinancialStressBadges",
                   "_formatScheduledSpotlight",
                   "updated their memory"):
        assert needle in t, f"missing Epic-9 indicator anchor: {needle!r}"


def test_08_template_is_no_longer_trivially_equal():
    """The file changed: marker is in there. Trivially: a fresh read+to_html
    must still byte-match the file (roundtrip). And the marker isn't in any
    other source we shipped before round 2 (sanity: it doesn't appear twice
    accidentally)."""
    b = ViewerBundle.read(VIEWER)
    on_disk = Path(VIEWER).read_text(encoding="utf-8")
    assert b.to_html() == on_disk, "roundtrip identity broken"
    # The marker appears multiple times (CSS open/close, JS open/close).
    assert b.template.count("EPIC10R2_MARK") >= 4
    assert "=== END" in b.template
    assert "=== BEGIN" in b.template


def test_09_fenced_regions_present():
    t = _template()
    assert "=== BEGIN" in t, "missing fenced BEGIN region"
    assert "=== END" in t, "missing fenced END region"
    assert t.count("EPIC10R2_MARK") >= 4, "expected marker in CSS+JS open/close"


TESTS = [
    ("1. EPIC10R2_MARK marker present",                 test_01_marker_present),
    ("2. Story 10.1 director-mode anchors",             test_02_director_anchors),
    ("3. Story 10.2 narration anchors",                 test_03_narration_anchors),
    ("4. Story 10.4 plot-threads anchors",              test_04_plot_threads_anchors),
    ("5. Story 10.5 pacing-label anchors",              test_05_pacing_label_anchors),
    ("6. Story 10.7 mood floater anchors",              test_06_mood_floater_anchors),
    ("7. Story 10.11 Epic-9 indicator anchors",         test_07_epic9_indicators_anchors),
    ("8. Roundtrip identity preserved after Round 2",   test_08_template_is_no_longer_trivially_equal),
    ("9. Fenced BEGIN/END regions present",             test_09_fenced_regions_present),
]


if __name__ == "__main__":
    print("=" * 70)
    print("viewer.html — Epic 10 Round 2 anchor tests")
    print("=" * 70)
    for name, fn in TESTS:
        run_test(name, fn)
    print()
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print("=" * 70)
    print(f"Results: {passed}/{len(results)} passed, {failed} failed")
    print("=" * 70)
    if failed:
        sys.exit(1)
    print("ALL TESTS PASSED")
