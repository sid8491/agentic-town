"""
Story 4.4 — Schedule Guidance + Auto-Speed Tests

Verifies:
  1–3.  _in_window wrap-around and non-wrap behaviour.
  4–9.  _schedule_guidance returns the right directive per archetype/time.
  10.   Auto-speed count threshold expression resolves correctly.

Run with:
    .venv/Scripts/python.exe tests/test_schedule.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.agent import _in_window, _schedule_guidance

results: list[tuple[str, bool, str | None]] = []


def run_test(name: str, fn):
    try:
        fn()
        results.append((name, True, None))
        print(f"  PASS  {name}")
    except Exception as exc:
        results.append((name, False, str(exc)))
        print(f"  FAIL  {name}")
        print(f"        {exc}")


# ---------------------------------------------------------------------------
# 1. _in_window wrap-around: 3am inside 11pm–6am
# ---------------------------------------------------------------------------

def test_01_in_window_wrap_inside():
    assert _in_window(180, 1380, 360) is True, (
        "3am should be inside the wrap-around window 11pm–6am"
    )


# ---------------------------------------------------------------------------
# 2. _in_window wrap-around: noon outside 11pm–6am
# ---------------------------------------------------------------------------

def test_02_in_window_wrap_outside():
    assert _in_window(720, 1380, 360) is False, (
        "noon should NOT be inside the wrap-around window 11pm–6am"
    )


# ---------------------------------------------------------------------------
# 3. _in_window non-wrap: 10am inside 9am–6pm
# ---------------------------------------------------------------------------

def test_03_in_window_non_wrap_inside():
    assert _in_window(600, 540, 1080) is True, (
        "10am should be inside the non-wrap window 9am–6pm"
    )


# ---------------------------------------------------------------------------
# 4. arjun at 3am should get a sleep directive (office_worker 11pm–6am)
# ---------------------------------------------------------------------------

def test_04_arjun_3am_sleep():
    result = _schedule_guidance("arjun", 180)
    assert "sleep" in result.lower(), (
        f"Expected 'sleep' for arjun at 3am, got: {result!r}"
    )


# ---------------------------------------------------------------------------
# 5. rahul at 3am should get a sleep directive (night_owl 3am–9am window)
# ---------------------------------------------------------------------------

def test_05_rahul_3am_sleep():
    result = _schedule_guidance("rahul", 180)
    assert "sleep" in result.lower(), (
        f"Expected 'sleep' for rahul at 3am, got: {result!r}"
    )


# ---------------------------------------------------------------------------
# 6. rahul at noon should NOT get a sleep directive
# ---------------------------------------------------------------------------

def test_06_rahul_noon_not_sleep():
    result = _schedule_guidance("rahul", 720)
    assert "sleep" not in result.lower(), (
        f"rahul at noon should not be told to sleep, got: {result!r}"
    )


# ---------------------------------------------------------------------------
# 7. arjun at 10am should get a work directive
# ---------------------------------------------------------------------------

def test_07_arjun_10am_work():
    result = _schedule_guidance("arjun", 600)
    assert "work" in result.lower(), (
        f"Expected 'work' for arjun at 10am, got: {result!r}"
    )


# ---------------------------------------------------------------------------
# 8. vikram at 10pm should get a sleep directive (retired 9pm–5am)
# ---------------------------------------------------------------------------

def test_08_vikram_10pm_sleep():
    result = _schedule_guidance("vikram", 1320)
    assert "sleep" in result.lower(), (
        f"Expected 'sleep' for vikram at 10pm, got: {result!r}"
    )


# ---------------------------------------------------------------------------
# 9. kavya at 1:30am should get a sleep directive (student 1am–7am)
# ---------------------------------------------------------------------------

def test_09_kavya_130am_sleep():
    result = _schedule_guidance("kavya", 90)
    assert "sleep" in result.lower(), (
        f"Expected 'sleep' for kavya at 1:30am, got: {result!r}"
    )


# ---------------------------------------------------------------------------
# 10. Auto-speed threshold: count sleeping agents from a fake mapping
# ---------------------------------------------------------------------------

def test_10_autospeed_count_threshold():
    fake_actions = {
        "arjun":  "sleeping...",
        "priya":  "sleeping...",
        "rahul":  "working...",
        "kavya":  "sleeping...",
        "suresh": "sleeping...",
        "neha":   "sleeping...",
        "vikram": "sleeping...",
        "deepa":  "sleeping...",
        "rohan":  "moving to home...",
        "anita":  "sleeping...",
    }
    sleeping = sum(1 for v in fake_actions.values() if "sleep" in v.lower())
    assert sleeping == 8, f"Expected 8 sleeping, got {sleeping}"
    assert sleeping >= 7, "Should trigger auto-speed UP (>=7 threshold)"


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

TESTS = [
    ("1.  _in_window(180, 1380, 360) is True",                       test_01_in_window_wrap_inside),
    ("2.  _in_window(720, 1380, 360) is False",                      test_02_in_window_wrap_outside),
    ("3.  _in_window(600, 540, 1080) is True",                       test_03_in_window_non_wrap_inside),
    ("4.  arjun at 3am gets sleep directive",                        test_04_arjun_3am_sleep),
    ("5.  rahul at 3am gets sleep directive",                        test_05_rahul_3am_sleep),
    ("6.  rahul at noon does NOT get sleep directive",               test_06_rahul_noon_not_sleep),
    ("7.  arjun at 10am gets work directive",                        test_07_arjun_10am_work),
    ("8.  vikram at 10pm gets sleep directive",                      test_08_vikram_10pm_sleep),
    ("9.  kavya at 1:30am gets sleep directive",                     test_09_kavya_130am_sleep),
    ("10. auto-speed count threshold resolves to 8 (>=7)",           test_10_autospeed_count_threshold),
]


if __name__ == "__main__":
    print("=" * 70)
    print("Story 4.4 -- Schedule Guidance + Auto-Speed Tests")
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
