"""tests/test_viewer_round3.py — Epic 10 Round 3b viewer assertions.

Anchor-string tests that verify the Round-3b features are present in the
patched viewer.html template. Mirrors test_viewer_round2.py.

Run with:
    .venv/Scripts/python.exe tests/test_viewer_round3.py
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
    assert "EPIC10R3_MARK" in t, "Round-3 marker missing"
    assert t.count("EPIC10R3_MARK") >= 4, (
        f"expected at least 4 EPIC10R3_MARK occurrences (CSS+JS open/close), "
        f"got {t.count('EPIC10R3_MARK')}"
    )


def test_02_scene_staging_anchors():
    t = _template()
    for needle in (
        "EPIC10R3_MARK: scene staging",
        "scene-modal",
        "SceneStaging",
        "scene-portraits",
        "scene-caption",
        "scene-dialogue",
        "replay-scene-btn",
        "Replay last scene",
    ):
        assert needle in t, f"missing scene-staging anchor: {needle!r}"


def test_03_portraits_everywhere_anchors():
    t = _template()
    for needle in (
        "avatar-thumbnail",
        "_avatarHtml",
        "_avatarCache",
        "_primeAvatarCache",
    ):
        assert needle in t, f"missing portrait anchor: {needle!r}"


def test_04_audio_anchors():
    t = _template()
    for needle in (
        "audio toggle",         # CSS comment / title in popover
        "audio-toggle",
        "audio-popover",
        "ambient_city.mp3",
        "ui_event.mp3",
        "sting_drama.mp3",
        "sting_refusal.mp3",
        "chime_dayboundary.mp3",
        "aud_master",
    ):
        assert needle in t, f"missing audio anchor: {needle!r}"


def test_05_highlight_reel_anchors():
    t = _template()
    for needle in (
        "renderHighlightReel",
        "highlight-reel",
        "reel-card",
        "reel-portraits",
        "/api/cliffhanger/",
    ):
        assert needle in t, f"missing highlight-reel anchor: {needle!r}"


def test_06_gossip_ticker_anchors():
    t = _template()
    for needle in (
        "gossipTicker",
        "gossip-ticker",
        "ticker-line",
        "/api/headlines/today",
        "GossipTicker",
    ):
        assert needle in t, f"missing gossip-ticker anchor: {needle!r}"


def test_07_roundtrip_identity_preserved():
    b = ViewerBundle.read(VIEWER)
    on_disk = Path(VIEWER).read_text(encoding="utf-8")
    assert b.to_html() == on_disk, "roundtrip identity broken"


def test_08_fenced_regions_present():
    t = _template()
    assert "=== BEGIN" in t, "missing fenced BEGIN region"
    assert "=== END" in t, "missing fenced END region"
    # Both R2 and R3 markers should coexist
    assert "EPIC10R2_MARK" in t, "R2 marker disappeared"
    assert "EPIC10R3_MARK" in t, "R3 marker missing"


def test_09_no_duplicate_round3_apply():
    """The patcher must be idempotent in the sense that we did not double-paste."""
    t = _template()
    # CSS BEGIN appears once
    css_begins = t.count("EPIC10R3_MARK — Stories 10.3/10.6/10.8/10.9/10.10 === BEGIN")
    assert css_begins == 1, f"CSS BEGIN appears {css_begins} times — expected 1"
    js_begins = t.count("EPIC10R3_MARK — Round 3b viewer features === BEGIN")
    assert js_begins == 1, f"JS BEGIN appears {js_begins} times — expected 1"


def test_10_iife_still_intact():
    """The Round-2 closing `})();` must still be present (we appended JS inside)."""
    t = _template()
    assert "})();" in t, "IIFE closure missing"
    # Round 3 JS sits inside the IIFE: marker should appear before })();
    assert t.index("EPIC10R3_MARK === END") < t.rindex("})();"), (
        "Round-3 JS must be inside the IIFE"
    )


def test_11_shared_plans_consumed():
    """Scene staging reads stateData.shared_plans (Round-3b server addition)."""
    t = _template()
    assert "stateData.shared_plans" in t or "shared_plans" in t, (
        "shared_plans field not referenced by viewer"
    )


TESTS = [
    ("1.  EPIC10R3_MARK marker present",                     test_01_marker_present),
    ("2.  Story 10.3 scene staging anchors",                 test_02_scene_staging_anchors),
    ("3.  Story 10.6 portraits-everywhere anchors",          test_03_portraits_everywhere_anchors),
    ("4.  Story 10.8 audio anchors",                         test_04_audio_anchors),
    ("5.  Story 10.9 highlight reel anchors",                test_05_highlight_reel_anchors),
    ("6.  Story 10.10 gossip ticker anchors",                test_06_gossip_ticker_anchors),
    ("7.  Roundtrip identity preserved",                     test_07_roundtrip_identity_preserved),
    ("8.  Fenced regions + R2 coexistence",                  test_08_fenced_regions_present),
    ("9.  Round-3 patch is idempotent (no duplicates)",      test_09_no_duplicate_round3_apply),
    ("10. IIFE closure still intact",                        test_10_iife_still_intact),
    ("11. shared_plans consumed by viewer",                  test_11_shared_plans_consumed),
]


if __name__ == "__main__":
    print("=" * 70)
    print("viewer.html — Epic 10 Round 3b anchor tests")
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
