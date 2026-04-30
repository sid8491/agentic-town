"""
tests/test_cliffhanger.py — Story 10.9 backend slice.

call_llm is mocked everywhere so no live Ollama is required.

Run:
    .venv/Scripts/python.exe tests/test_cliffhanger.py
"""

import asyncio
import os
import pathlib
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from fastapi.testclient import TestClient

import server
from server import app
from engine.world import WorldState
from engine.cliffhanger import (
    _FALLBACK,
    generate_cliffhanger,
    run_cliffhanger,
)

_pass = 0
_fail = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global _pass, _fail
    status = "PASS" if ok else "FAIL"
    if ok:
        _pass += 1
    else:
        _fail += 1
    extra = f" — {detail}" if detail else ""
    print(f"[{status}] {name}{extra}")


def _mock_response(text: str) -> MagicMock:
    m = MagicMock()
    m.text = text
    m.tool_name = None
    m.tool_args = None
    m.provider = "ollama"
    m.input_tokens = 80
    m.output_tokens = 30
    return m


def _make_world(state_path: str | None = None) -> WorldState:
    if state_path is None:
        state_path = os.path.join(ROOT, "world", "state.json")
    ws = WorldState(
        state_path=state_path,
        map_path=os.path.join(ROOT, "world", "map.json"),
    )
    ws.load_or_init()
    return ws


def test_fresh_state_has_daily_cliffhangers_dict():
    with tempfile.TemporaryDirectory() as td:
        sp = os.path.join(td, "state.json")
        ws = _make_world(sp)
        check(
            "fresh state initialises daily_cliffhangers={}",
            ws._state.get("daily_cliffhangers") == {},
            f"got={ws._state.get('daily_cliffhangers')!r}",
        )


def test_empty_input_fallback_skips_llm():
    """No threads + no plans → fallback string, no LLM call."""
    with tempfile.TemporaryDirectory() as td:
        sp = os.path.join(td, "state.json")
        ws = _make_world(sp)
        # Strip out anything that could trigger detect_plot_threads.
        ws._state["events"] = []
        ws._state["shared_plans"] = []
        ws._state["conversations"] = []
        for _, ag in ws.get_all_agents().items():
            ag["mood"] = 65
            ag["financial_stress"] = False
            ag["financial_stress_until_day"] = 0

        called = {"n": 0}
        async def fake_call_llm(*args, **kwargs):
            called["n"] += 1
            return _mock_response("should not be used")

        with patch("engine.cliffhanger.call_llm", new=fake_call_llm):
            text = asyncio.run(generate_cliffhanger(ws, completed_day=1))

        check(
            "fallback returned when no threads + no plans",
            text == _FALLBACK,
            f"got={text!r}",
        )
        check(
            "no LLM call made for empty-input case",
            called["n"] == 0,
            f"call_count={called['n']}",
        )


def test_generate_cliffhanger_happy_path():
    """With pending plan, LLM is called and result is returned (trimmed)."""
    with tempfile.TemporaryDirectory() as td:
        sp = os.path.join(td, "state.json")
        ws = _make_world(sp)
        ws._state["events"] = []
        ws._state["shared_plans"] = [{
            "id": 1,
            "participants": ["arjun", "priya"],
            "location": "dhaba",
            "target_time": ws._state["day"] * 1440 + ws._state["sim_time"] + 60,
            "activity": "lunch",
            "status": "pending",
            "created_at": ws._abs_minutes(),
        }]

        mock = _mock_response(
            "  Tomorrow on Gurgaon: Arjun and Priya may finally share that lunch. "
            "Or one of them won't show.  "
        )
        with patch("engine.cliffhanger.call_llm", new=AsyncMock(return_value=mock)):
            text = asyncio.run(generate_cliffhanger(ws, completed_day=1))

        check(
            "happy-path text starts with 'Tomorrow on Gurgaon:'",
            text.startswith("Tomorrow on Gurgaon:"),
            f"got={text!r}",
        )
        check(
            "happy-path text is stripped of leading/trailing whitespace",
            text == text.strip(),
            f"got={text!r}",
        )


def test_generate_cliffhanger_caps_long_output():
    """Excessively long LLM responses are truncated to ~200 chars."""
    with tempfile.TemporaryDirectory() as td:
        sp = os.path.join(td, "state.json")
        ws = _make_world(sp)
        ws._state["shared_plans"] = [{
            "id": 1,
            "participants": ["arjun", "priya"],
            "location": "dhaba",
            "target_time": ws._abs_minutes() + 60,
            "activity": "lunch",
            "status": "pending",
            "created_at": ws._abs_minutes(),
        }]
        long_text = "Tomorrow on Gurgaon: " + ("x " * 300)
        mock = _mock_response(long_text)
        with patch("engine.cliffhanger.call_llm", new=AsyncMock(return_value=mock)):
            text = asyncio.run(generate_cliffhanger(ws, completed_day=1))
        check(
            "long output capped at 200 chars",
            len(text) <= 200,
            f"len={len(text)}",
        )


def test_run_cliffhanger_persists_and_appends_log():
    """run_cliffhanger writes to world._state and appends to daily_log_day_N.txt."""
    with tempfile.TemporaryDirectory() as td:
        sp = os.path.join(td, "state.json")
        ws = _make_world(sp)
        ws._state["shared_plans"] = [{
            "id": 1,
            "participants": ["arjun", "priya"],
            "location": "dhaba",
            "target_time": ws._abs_minutes() + 60,
            "activity": "lunch",
            "status": "pending",
            "created_at": ws._abs_minutes(),
        }]

        out_dir = pathlib.Path(td) / "logs"
        out_dir.mkdir()
        # Pre-existing summary content from Story 7.2 — should be preserved.
        log_path = out_dir / "daily_log_day_3.txt"
        log_path.write_text("Day 3 was sunny. People moved around.", encoding="utf-8")

        mock = _mock_response(
            "Tomorrow on Gurgaon: Arjun waits at the dhaba. Priya hesitates."
        )
        with patch("engine.cliffhanger.call_llm", new=AsyncMock(return_value=mock)):
            asyncio.run(run_cliffhanger(ws, completed_day=3, output_dir=out_dir))

        stored = ws._state.get("daily_cliffhangers", {}).get("3", "")
        check(
            "cliffhanger persisted to world._state['daily_cliffhangers']['3']",
            stored.startswith("Tomorrow on Gurgaon:"),
            f"stored={stored!r}",
        )

        contents = log_path.read_text(encoding="utf-8")
        check(
            "existing summary preserved in daily_log_day_3.txt",
            "Day 3 was sunny" in contents,
            f"contents={contents!r}",
        )
        check(
            "cliffhanger appended to daily_log_day_3.txt",
            "Tomorrow on Gurgaon: Arjun waits at the dhaba" in contents,
            f"contents={contents!r}",
        )


def test_run_cliffhanger_persists_to_state_json_round_trip():
    """daily_cliffhangers survives a save/reload round-trip (no underscore prefix)."""
    import json
    with tempfile.TemporaryDirectory() as td:
        sp = os.path.join(td, "state.json")
        ws = _make_world(sp)
        ws._state["shared_plans"] = [{
            "id": 1,
            "participants": ["arjun", "priya"],
            "location": "dhaba",
            "target_time": ws._abs_minutes() + 60,
            "activity": "lunch",
            "status": "pending",
            "created_at": ws._abs_minutes(),
        }]
        out_dir = pathlib.Path(td) / "logs"
        out_dir.mkdir()

        mock = _mock_response("Tomorrow on Gurgaon: things may shift.")
        with patch("engine.cliffhanger.call_llm", new=AsyncMock(return_value=mock)):
            asyncio.run(run_cliffhanger(ws, completed_day=2, output_dir=out_dir))
        ws.save()

        with open(sp, "r", encoding="utf-8") as f:
            persisted = json.load(f)
        check(
            "daily_cliffhangers survives state.json round-trip",
            persisted.get("daily_cliffhangers", {}).get("2", "").startswith("Tomorrow"),
            f"persisted_keys={list(persisted.keys())[:8]}",
        )


def test_run_cliffhanger_swallows_llm_failure():
    """LLM exception → log warning + skip persistence (no crash, no state mutation)."""
    with tempfile.TemporaryDirectory() as td:
        sp = os.path.join(td, "state.json")
        ws = _make_world(sp)
        ws._state["shared_plans"] = [{
            "id": 1,
            "participants": ["arjun", "priya"],
            "location": "dhaba",
            "target_time": ws._abs_minutes() + 60,
            "activity": "lunch",
            "status": "pending",
            "created_at": ws._abs_minutes(),
        }]
        out_dir = pathlib.Path(td) / "logs"
        out_dir.mkdir()

        async def boom(*args, **kwargs):
            raise RuntimeError("LLM is down")

        with patch("engine.cliffhanger.call_llm", new=boom):
            # Must not raise.
            asyncio.run(run_cliffhanger(ws, completed_day=4, output_dir=out_dir))

        store = ws._state.get("daily_cliffhangers", {})
        check(
            "no entry persisted on LLM failure",
            "4" not in store,
            f"store={store!r}",
        )
        log_path = out_dir / "daily_log_day_4.txt"
        check(
            "no log file created on LLM failure",
            not log_path.exists(),
            f"exists={log_path.exists()}",
        )


def test_endpoint_returns_404_when_missing():
    with tempfile.TemporaryDirectory() as td:
        sp = os.path.join(td, "state.json")
        ws = _make_world(sp)
        server.set_world(ws)
        try:
            client = TestClient(app)
            r = client.get("/api/cliffhanger/7")
            check(
                "GET /api/cliffhanger/7 returns 404 when absent",
                r.status_code == 404,
                f"status={r.status_code}",
            )
        finally:
            server._world = None


def test_endpoint_returns_200_with_text():
    with tempfile.TemporaryDirectory() as td:
        sp = os.path.join(td, "state.json")
        ws = _make_world(sp)
        ws._state.setdefault("daily_cliffhangers", {})["5"] = (
            "Tomorrow on Gurgaon: trouble at the dhaba."
        )
        server.set_world(ws)
        try:
            client = TestClient(app)
            r = client.get("/api/cliffhanger/5")
            check(
                "GET /api/cliffhanger/5 returns 200 when present",
                r.status_code == 200,
                f"status={r.status_code}",
            )
            body = r.json()
            check(
                "endpoint payload contains day + text",
                body.get("day") == 5 and body.get("text", "").startswith("Tomorrow"),
                f"body={body!r}",
            )
        finally:
            server._world = None


if __name__ == "__main__":
    print("=" * 60)
    print("Story 10.9 — cliffhanger backend tests")
    print("=" * 60)
    print()
    test_fresh_state_has_daily_cliffhangers_dict()
    test_empty_input_fallback_skips_llm()
    test_generate_cliffhanger_happy_path()
    test_generate_cliffhanger_caps_long_output()
    test_run_cliffhanger_persists_and_appends_log()
    test_run_cliffhanger_persists_to_state_json_round_trip()
    test_run_cliffhanger_swallows_llm_failure()
    test_endpoint_returns_404_when_missing()
    test_endpoint_returns_200_with_text()
    print()
    print("=" * 60)
    print(f"Results: {_pass} passed, {_fail} failed")
    print("=" * 60)
    if _fail > 0:
        sys.exit(1)
