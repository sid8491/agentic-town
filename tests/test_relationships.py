"""
Story 7.1 -- Relationship Indicators Tests

Verifies the engine.relationships parser:
  - whole-word positive / negative keyword detection
  - balanced score yields neutral
  - per-agent block parsing from a `# Relationships` section
  - graceful handling of missing files / sections
  - unknown names are ignored
  - section terminates at the next H1/H2 header
  - the all-agents graph contains no self-loops

Run with:
    .venv/Scripts/python.exe tests/test_relationships.py
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.relationships import (
    ALL_AGENTS,
    _score_text,
    parse_agent_relationships,
    parse_all_relationships,
)


results: list[tuple[str, bool, str | None]] = []


def ok(name: str) -> None:
    results.append((name, True, None))
    print(f"  PASS  {name}")


def fail(name: str, reason: str) -> None:
    results.append((name, False, reason))
    print(f"  FAIL  {name}")
    print(f"        {reason}")


def run(name: str, fn) -> None:
    try:
        fn()
        ok(name)
    except AssertionError as exc:
        fail(name, str(exc))
    except Exception as exc:
        fail(name, f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent_dir(root: pathlib.Path, name: str, memory_text: str | None) -> None:
    """Create agents/<name>/ inside root, optionally writing memory.md."""
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    if memory_text is not None:
        (d / "memory.md").write_text(memory_text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_01_score_text_positive_keywords():
    """Positive keywords push the score above zero."""
    score = _score_text("I like Rohan and trust him deeply.")
    assert score >= 1, f"expected >=1, got {score}"


def test_02_score_text_negative_keywords():
    """Negative keywords push the score below zero."""
    score = _score_text("I avoid Priya and distrust her motives.")
    assert score <= -1, f"expected <=-1, got {score}"


def test_03_score_text_neutral_when_balanced():
    """One positive and one negative keyword cancel out to zero."""
    score = _score_text("I trust her but I'm wary of her motives.")
    assert score == 0, f"expected 0, got {score}"


def test_04_score_text_whole_word_match():
    """`like` inside `likely` must NOT count as a positive keyword."""
    score = _score_text("She's likely to call.")
    assert score == 0, (
        f"`likely` should not match `like` whole-word; got score {score}"
    )


def test_05_parse_agent_relationships_basic():
    """Two blocks parsed correctly: friendly Rohan + neutral Priya."""
    memory = (
        "# Relationships\n"
        "\n"
        "**Rohan** — He is a kind friend who I trust completely.\n"
        "I admire how warm he is.\n"
        "\n"
        "**Priya** — Met her once. She mentioned her job.\n"
    )
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        _make_agent_dir(root, "arjun", memory)
        out = parse_agent_relationships("arjun", agents_dir=root)
    assert out == {"rohan": "friendly", "priya": "neutral"}, f"got {out}"


def test_06_parse_agent_relationships_missing_section():
    """memory.md without a `# Relationships` header → empty dict."""
    memory = "# Knowledge\n\n- A fact.\n\n**Rohan** — should not be parsed.\n"
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        _make_agent_dir(root, "arjun", memory)
        out = parse_agent_relationships("arjun", agents_dir=root)
    assert out == {}, f"expected empty dict, got {out}"


def test_07_parse_agent_relationships_missing_file():
    """Missing memory.md → empty dict, no exception."""
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        # Note: no memory.md written — directory may or may not exist
        out = parse_agent_relationships("arjun", agents_dir=root)
    assert out == {}, f"expected empty dict, got {out}"


def test_08_parse_agent_relationships_unknown_name_ignored():
    """A `**Stranger**` block is ignored; only known agents survive."""
    memory = (
        "# Relationships\n"
        "\n"
        "**Stranger** — Some person I like a lot, very friendly.\n"
        "\n"
        "**Rohan** — We trust each other.\n"
    )
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        _make_agent_dir(root, "arjun", memory)
        out = parse_agent_relationships("arjun", agents_dir=root)
    assert "stranger" not in out, "unknown name leaked into result"
    assert "rohan" in out, "known name missing"
    assert all(k in {a.lower() for a in ALL_AGENTS} for k in out), (
        f"non-known key in result: {out}"
    )


def test_09_parse_agent_relationships_stops_at_next_h1():
    """`# Knowledge` terminates the relationships section."""
    memory = (
        "# Relationships\n"
        "\n"
        "**Rohan** — A kind friend I trust.\n"
        "\n"
        "# Knowledge\n"
        "\n"
        "**Arjun** — This block is in the wrong section and must be ignored.\n"
    )
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        _make_agent_dir(root, "arjun", memory)
        out = parse_agent_relationships("arjun", agents_dir=root)
    assert "arjun" not in out, f"self-block leaked from Knowledge section: {out}"
    assert out.get("rohan") == "friendly", f"expected friendly Rohan, got {out}"


def test_10_parse_all_relationships_no_self_loops():
    """A fully sandboxed agents/ tree must not yield (name, name) keys."""
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        for name in ALL_AGENTS:
            # Each agent self-mentions plus mentions one other to make
            # the section non-empty.
            other = "rohan" if name != "rohan" else "arjun"
            memory = (
                "# Relationships\n"
                "\n"
                f"**{name.capitalize()}** — I like myself, friendly thoughts.\n"
                "\n"
                f"**{other.capitalize()}** — A trusted friend.\n"
            )
            _make_agent_dir(root, name, memory)

        edges = parse_all_relationships(agents_dir=root)
    for (a, b) in edges:
        assert a != b, f"self-loop present: ({a}, {b})"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    ("1.  _score_text positive keywords yield positive score",         test_01_score_text_positive_keywords),
    ("2.  _score_text negative keywords yield negative score",         test_02_score_text_negative_keywords),
    ("3.  _score_text neutral when positives and negatives balance",   test_03_score_text_neutral_when_balanced),
    ("4.  _score_text whole-word boundary (likely != like)",           test_04_score_text_whole_word_match),
    ("5.  parse_agent_relationships parses two blocks correctly",      test_05_parse_agent_relationships_basic),
    ("6.  parse_agent_relationships returns {} when section missing",  test_06_parse_agent_relationships_missing_section),
    ("7.  parse_agent_relationships returns {} when file missing",     test_07_parse_agent_relationships_missing_file),
    ("8.  parse_agent_relationships ignores unknown names",            test_08_parse_agent_relationships_unknown_name_ignored),
    ("9.  parse_agent_relationships stops at next H1 header",          test_09_parse_agent_relationships_stops_at_next_h1),
    ("10. parse_all_relationships has no self-loops",                  test_10_parse_all_relationships_no_self_loops),
]


if __name__ == "__main__":
    print("=" * 70)
    print("Story 7.1 -- Relationship Indicators Tests")
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
