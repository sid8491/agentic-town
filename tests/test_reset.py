"""
Story 5.2 — Reset Command Tests

Verifies:
  - _parse_default_goals extracts the right body
  - reset_world deletes state.json
  - reset_world deletes memory.md / diary.md but preserves soul.md
  - reset_world re-seeds goals.md from soul.md's `# Default Goals`
  - reset_world tolerates missing per-agent files
  - reset_world counts days from state.json for the prompt
  - reset_world(confirm=False) does not call input()

Run with:
    .venv/Scripts/python.exe tests/test_reset.py
"""

import builtins
import io
import json
import os
import pathlib
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import _parse_default_goals, reset_world, ALL_AGENT_NAMES

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


SAMPLE_SOUL = """# Identity
I am Arjun.

# Default Goals
- Stabilize the auth service before Q2
- Build human connections in this city
- Stop skipping dinner
- Save 20 coins a week

# Voice
Calm, terse.
"""

SAMPLE_SOUL_NO_OTHER = """# Identity
I am Arjun.

# Default Goals
- Goal one
- Goal two
- Goal three
- Goal four
"""

SAMPLE_SOUL_NO_GOALS = """# Identity
I am Arjun.

# Voice
Calm, terse.
"""


def _make_agent_tree(agents_dir: Path, name: str, soul_text: str,
                     with_memory: bool = True, with_diary: bool = True,
                     with_goals: bool = True) -> None:
    adir = agents_dir / name
    adir.mkdir(parents=True, exist_ok=True)
    (adir / "soul.md").write_text(soul_text, encoding="utf-8")
    if with_memory:
        (adir / "memory.md").write_text("old memory\n", encoding="utf-8")
    if with_diary:
        (adir / "diary.md").write_text("Day 1: stuff happened\n", encoding="utf-8")
    if with_goals:
        (adir / "goals.md").write_text("# Goals\n\n- old goal\n", encoding="utf-8")


def _make_full_agent_tree(agents_dir: Path, soul_text: str = SAMPLE_SOUL) -> None:
    """Create dirs for all 10 agents with the given soul text."""
    for name in ALL_AGENT_NAMES:
        _make_agent_tree(agents_dir, name, soul_text)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_01_parse_default_goals_basic():
    """Parser returns just the 4 bullet lines from `# Default Goals`."""
    body = _parse_default_goals(SAMPLE_SOUL_NO_OTHER)
    expected = "\n".join([
        "- Goal one",
        "- Goal two",
        "- Goal three",
        "- Goal four",
    ])
    assert body == expected, f"Expected 4 bullets, got: {body!r}"


def test_02_parse_default_goals_stops_at_next_header():
    """Parser stops at the next H1/H2 header."""
    body = _parse_default_goals(SAMPLE_SOUL)
    # Should NOT include the `# Voice` line or anything below it
    assert "Voice" not in body, f"Body leaked into next section: {body!r}"
    assert "Calm, terse." not in body, f"Body leaked: {body!r}"
    # Should include the bullets
    assert "- Stabilize the auth service before Q2" in body
    assert "- Save 20 coins a week" in body


def test_03_parse_default_goals_missing_section():
    """Parser returns empty string when no `# Default Goals` header exists."""
    body = _parse_default_goals(SAMPLE_SOUL_NO_GOALS)
    assert body == "", f"Expected empty, got: {body!r}"


def test_04_reset_deletes_state_json():
    """reset_world removes the state.json file."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        state_path = td_path / "world" / "state.json"
        state_path.parent.mkdir(parents=True)
        state_path.write_text(json.dumps({"day": 3, "agents": {}}), encoding="utf-8")

        agents_dir = td_path / "agents"
        _make_full_agent_tree(agents_dir)

        with redirect_stdout(io.StringIO()):
            reset_world(confirm=False, agents_dir=agents_dir, state_path=state_path)

        assert not state_path.exists(), "state.json should be deleted"


def test_05_reset_deletes_memory_and_diary():
    """memory.md and diary.md are deleted; soul.md preserved; goals.md rewritten."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        agents_dir = td_path / "agents"
        _make_agent_tree(agents_dir, "arjun", SAMPLE_SOUL)
        # Need to provide all 10 to avoid skip warnings — but the test only
        # checks arjun, so create the rest as bare dirs with soul.
        for name in ALL_AGENT_NAMES:
            if name == "arjun":
                continue
            _make_agent_tree(agents_dir, name, SAMPLE_SOUL)

        state_path = td_path / "world" / "state.json"

        with redirect_stdout(io.StringIO()):
            reset_world(confirm=False, agents_dir=agents_dir, state_path=state_path)

        arjun = agents_dir / "arjun"
        assert not (arjun / "memory.md").exists(), "memory.md should be gone"
        assert not (arjun / "diary.md").exists(), "diary.md should be gone"
        assert (arjun / "soul.md").exists(), "soul.md must remain"
        assert (arjun / "goals.md").exists(), "goals.md should be present"
        contents = (arjun / "goals.md").read_text(encoding="utf-8")
        assert "Stabilize the auth service before Q2" in contents, (
            f"goals.md missing default goals: {contents!r}"
        )


def test_06_reset_preserves_soul_md():
    """soul.md must be byte-identical before and after reset."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        agents_dir = td_path / "agents"
        _make_full_agent_tree(agents_dir, SAMPLE_SOUL)

        before = (agents_dir / "arjun" / "soul.md").read_bytes()

        state_path = td_path / "world" / "state.json"
        with redirect_stdout(io.StringIO()):
            reset_world(confirm=False, agents_dir=agents_dir, state_path=state_path)

        after = (agents_dir / "arjun" / "soul.md").read_bytes()
        assert before == after, "soul.md was modified by reset"


def test_07_reset_writes_default_goals_to_goals_md():
    """goals.md content matches the parsed `# Default Goals` body with header prepended."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        agents_dir = td_path / "agents"
        _make_full_agent_tree(agents_dir, SAMPLE_SOUL)

        state_path = td_path / "world" / "state.json"
        with redirect_stdout(io.StringIO()):
            reset_world(confirm=False, agents_dir=agents_dir, state_path=state_path)

        goals = (agents_dir / "arjun" / "goals.md").read_text(encoding="utf-8")
        body = _parse_default_goals(SAMPLE_SOUL)
        expected = f"# Goals\n\n{body}\n"
        assert goals == expected, (
            f"goals.md mismatch.\nExpected:\n{expected!r}\nGot:\n{goals!r}"
        )


def test_08_reset_handles_missing_files_gracefully():
    """reset_world should not crash when memory/diary/goals don't exist; goals.md created."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        agents_dir = td_path / "agents"
        # Create all 10 dirs with ONLY soul.md
        for name in ALL_AGENT_NAMES:
            _make_agent_tree(
                agents_dir, name, SAMPLE_SOUL,
                with_memory=False, with_diary=False, with_goals=False,
            )

        state_path = td_path / "world" / "state.json"  # doesn't exist
        with redirect_stdout(io.StringIO()):
            reset_world(confirm=False, agents_dir=agents_dir, state_path=state_path)

        arjun = agents_dir / "arjun"
        assert (arjun / "goals.md").exists(), "goals.md should be created"
        contents = (arjun / "goals.md").read_text(encoding="utf-8")
        assert "Stabilize" in contents, f"goals.md missing defaults: {contents!r}"


def test_09_reset_count_days_from_state():
    """Confirmation message should mention the day count from state.json."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        agents_dir = td_path / "agents"
        _make_full_agent_tree(agents_dir)

        state_path = td_path / "world" / "state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({"day": 7, "agents": {}}), encoding="utf-8")

        # Capture stdout while feeding 'n' to input()
        original_input = builtins.input
        builtins.input = lambda *a, **kw: "n"
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                reset_world(confirm=True, agents_dir=agents_dir, state_path=state_path)
        finally:
            builtins.input = original_input

        out = buf.getvalue()
        assert "7 days" in out, f"Confirmation message missing day count: {out!r}"
        # And aborting should keep state.json
        assert state_path.exists(), "Abort should not delete state.json"


def test_11_reset_deletes_daily_log_files():
    """daily_log_day_*.txt files are LLM-generated runtime output and must be wiped."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        agents_dir = td_path / "agents"
        _make_full_agent_tree(agents_dir)

        world_dir = td_path / "world"
        world_dir.mkdir(parents=True, exist_ok=True)
        state_path = world_dir / "state.json"
        state_path.write_text(json.dumps({"day": 3, "agents": {}}), encoding="utf-8")

        # Authored content that must be preserved
        map_path = world_dir / "map.json"
        map_path.write_text('{"locations": []}', encoding="utf-8")

        # Runtime output that must be deleted
        log1 = world_dir / "daily_log_day_1.txt"
        log2 = world_dir / "daily_log_day_2.txt"
        log1.write_text("Day 1 summary\n", encoding="utf-8")
        log2.write_text("Day 2 summary\n", encoding="utf-8")

        with redirect_stdout(io.StringIO()):
            reset_world(confirm=False, agents_dir=agents_dir, state_path=state_path)

        assert not log1.exists(), "daily_log_day_1.txt should be deleted"
        assert not log2.exists(), "daily_log_day_2.txt should be deleted"
        assert map_path.exists(), "map.json must be preserved (authored content)"


def test_10_reset_with_confirm_false_skips_input():
    """confirm=False must not invoke input()."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        agents_dir = td_path / "agents"
        _make_full_agent_tree(agents_dir)
        state_path = td_path / "world" / "state.json"

        original_input = builtins.input

        def boom(*a, **kw):
            raise RuntimeError("input() should not be called when confirm=False")

        builtins.input = boom
        try:
            with redirect_stdout(io.StringIO()):
                reset_world(confirm=False, agents_dir=agents_dir, state_path=state_path)
        finally:
            builtins.input = original_input

        # If we got here without RuntimeError, the test passes.
        # Sanity check: goals.md got rewritten.
        assert (agents_dir / "arjun" / "goals.md").exists()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    ("1.  _parse_default_goals returns 4 bullet lines",                test_01_parse_default_goals_basic),
    ("2.  _parse_default_goals stops at next H1/H2 header",            test_02_parse_default_goals_stops_at_next_header),
    ("3.  _parse_default_goals returns empty when section missing",    test_03_parse_default_goals_missing_section),
    ("4.  reset_world deletes state.json",                             test_04_reset_deletes_state_json),
    ("5.  reset_world deletes memory.md and diary.md",                 test_05_reset_deletes_memory_and_diary),
    ("6.  reset_world preserves soul.md byte-for-byte",                test_06_reset_preserves_soul_md),
    ("7.  reset_world writes default goals to goals.md",               test_07_reset_writes_default_goals_to_goals_md),
    ("8.  reset_world handles missing files gracefully",               test_08_reset_handles_missing_files_gracefully),
    ("9.  reset_world prompt mentions day count from state.json",      test_09_reset_count_days_from_state),
    ("10. reset_world(confirm=False) skips input()",                   test_10_reset_with_confirm_false_skips_input),
    ("11. reset_world deletes daily_log_day_*.txt files",              test_11_reset_deletes_daily_log_files),
]


if __name__ == "__main__":
    print("=" * 70)
    print("Story 5.2 -- Reset Command Tests")
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
