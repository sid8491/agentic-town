"""
tests/test_server.py — FastAPI endpoint tests.

Originally Story 2.2 (health + LLM endpoints), extended for Story 6.1
(state, map, diary, viewer endpoints).

Uses fastapi.testclient.TestClient so no live server is needed.

Run:
    .venv/Scripts/python.exe tests/test_server.py
"""

import os
import pathlib
import sys
import tempfile

# Ensure project root is on sys.path so that `server` and `engine` are importable.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient

import server
from server import app
from engine.world import WorldState

MAP_PATH = pathlib.Path(ROOT) / "world" / "map.json"

ALL_AGENTS = {
    "arjun", "priya", "rahul", "kavya", "suresh",
    "neha", "vikram", "deepa", "rohan", "anita",
}

PASS = "PASS"
FAIL = "FAIL"


def run_test(name: str, fn) -> bool:
    try:
        fn()
        print(f"  {PASS}  {name}")
        return True
    except AssertionError as exc:
        print(f"  {FAIL}  {name}: {exc}")
        return False
    except Exception as exc:
        print(f"  {FAIL}  {name}: unexpected error — {type(exc).__name__}: {exc}")
        return False


def _make_world(state_path: str) -> WorldState:
    ws = WorldState(state_path=state_path, map_path=str(MAP_PATH))
    ws.load_or_init()
    return ws


def _client_with_fresh_world() -> tuple[TestClient, WorldState, tempfile.TemporaryDirectory]:
    """Build a TestClient with a freshly initialised WorldState wired in."""
    td = tempfile.TemporaryDirectory()
    state_path = os.path.join(td.name, "state.json")
    ws = _make_world(state_path)
    server.set_world(ws)
    return TestClient(app), ws, td


# ---------------------------------------------------------------------------
# Story 2.2 — Health + LLM endpoints (kept for regression)
# ---------------------------------------------------------------------------


def test_health_200():
    """GET /api/health returns HTTP 200."""
    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code == 200, f"expected 200, got {r.status_code}"
    data = r.json()
    assert data["status"] == "ok", f"expected status='ok', got {data.get('status')!r}"


def test_health_has_llm_primary():
    """GET /api/health includes llm_primary field."""
    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert "llm_primary" in data, f"llm_primary key missing from: {data}"


def test_get_llm_returns_provider_and_model():
    """GET /api/llm returns current provider and model."""
    client = TestClient(app)
    r = client.get("/api/llm")
    assert r.status_code == 200, f"expected 200, got {r.status_code}"
    data = r.json()
    assert "provider" in data, f"provider key missing from: {data}"
    assert "model" in data, f"model key missing from: {data}"
    assert isinstance(data["provider"], str) and data["provider"], "provider must be a non-empty string"
    assert isinstance(data["model"], str) and data["model"], "model must be a non-empty string"


def test_post_llm_gemini_returns_200():
    """POST /api/llm/gemini returns 200 with provider='gemini'."""
    client = TestClient(app)
    r = client.post("/api/llm/gemini")
    assert r.status_code == 200, f"expected 200, got {r.status_code} — body: {r.text}"
    data = r.json()
    assert data.get("provider") == "gemini", f"expected provider='gemini', got {data.get('provider')!r}"


def test_post_llm_ollama_returns_200():
    """POST /api/llm/ollama returns 200 with provider='ollama'."""
    client = TestClient(app)
    r = client.post("/api/llm/ollama")
    assert r.status_code == 200, f"expected 200, got {r.status_code} — body: {r.text}"
    data = r.json()
    assert data.get("provider") == "ollama", f"expected provider='ollama', got {data.get('provider')!r}"


def test_post_llm_invalid_returns_400():
    """POST /api/llm/invalid returns HTTP 400."""
    client = TestClient(app)
    r = client.post("/api/llm/invalid_provider")
    assert r.status_code == 400, f"expected 400, got {r.status_code} — body: {r.text}"


def test_after_post_gemini_get_returns_gemini():
    """After POST /api/llm/gemini, GET /api/llm returns gemini."""
    client = TestClient(app)
    client.post("/api/llm/gemini")
    r = client.get("/api/llm")
    assert r.status_code == 200
    data = r.json()
    assert data.get("provider") == "gemini", (
        f"expected provider='gemini' after switching, got {data.get('provider')!r}"
    )


def test_after_post_ollama_get_returns_ollama():
    """After POST /api/llm/ollama, GET /api/llm returns ollama (resets state)."""
    client = TestClient(app)
    client.post("/api/llm/ollama")
    r = client.get("/api/llm")
    assert r.status_code == 200
    data = r.json()
    assert data.get("provider") == "ollama", (
        f"expected provider='ollama' after switching back, got {data.get('provider')!r}"
    )


# ---------------------------------------------------------------------------
# Story 6.1 — State + Map + Diary + Viewer
# ---------------------------------------------------------------------------


def test_01_health_still_works():
    """/api/health remains 200 OK regardless of world wiring."""
    server._world = None
    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code == 200, f"got {r.status_code}"
    body = r.json()
    assert body.get("status") == "ok", f"unexpected body: {body!r}"


def test_02_state_returns_503_without_world():
    """GET /api/state without set_world() returns 503."""
    server._world = None
    client = TestClient(app)
    r = client.get("/api/state")
    assert r.status_code == 503, f"expected 503, got {r.status_code}"


def test_03_state_basic_shape():
    """GET /api/state returns expected top-level keys, all 10 agents, no inbox."""
    client, _ws, td = _client_with_fresh_world()
    try:
        r = client.get("/api/state")
        assert r.status_code == 200, f"got {r.status_code}"
        body = r.json()
        for key in ("day", "sim_time", "time_str", "paused", "speed",
                    "llm_primary", "agents", "events"):
            assert key in body, f"missing key {key!r} in response"

        agents = body["agents"]
        assert set(agents.keys()) == ALL_AGENTS, (
            f"expected agents {ALL_AGENTS}, got {set(agents.keys())}"
        )
        for name, ag in agents.items():
            assert "inbox" not in ag, f"agent {name} should not contain inbox"
    finally:
        td.cleanup()
        server._world = None


def test_04_state_events_capped_at_30():
    """/api/state truncates events to the last 30 entries."""
    client, ws, td = _client_with_fresh_world()
    try:
        ws._state["events"] = [
            {"time": f"t{i}", "text": f"event-{i}"} for i in range(50)
        ]
        r = client.get("/api/state")
        assert r.status_code == 200
        events = r.json()["events"]
        assert len(events) == 30, f"expected 30, got {len(events)}"
        # The last 30 from a 50-list are events 20..49
        assert events[0]["text"] == "event-20", f"first should be event-20, got {events[0]}"
        assert events[-1]["text"] == "event-49", f"last should be event-49, got {events[-1]}"
    finally:
        td.cleanup()
        server._world = None


def test_05_map_endpoint():
    """/api/map returns {"locations": [...]} with id + connected_to fields."""
    client, _ws, td = _client_with_fresh_world()
    try:
        r = client.get("/api/map")
        assert r.status_code == 200, f"got {r.status_code}"
        body = r.json()
        assert "locations" in body, f"missing 'locations' key: {body!r}"
        locs = body["locations"]
        assert isinstance(locs, list) and len(locs) > 0, "expected non-empty list"
        first = locs[0]
        assert "id" in first, f"location missing 'id': {first!r}"
        assert "connected_to" in first, f"location missing 'connected_to': {first!r}"
    finally:
        td.cleanup()
        server._world = None


def test_06_diary_unknown_agent_404():
    """/api/agent/xyz/diary returns 404 for an unknown name."""
    client, _ws, td = _client_with_fresh_world()
    try:
        r = client.get("/api/agent/xyz/diary")
        assert r.status_code == 404, f"expected 404, got {r.status_code}"
    finally:
        td.cleanup()
        server._world = None


def test_07_diary_empty_when_missing():
    """Diary parser returns empty entries when diary.md is absent."""
    with tempfile.TemporaryDirectory() as td:
        agents_dir = pathlib.Path(td) / "agents"
        (agents_dir / "arjun").mkdir(parents=True)
        # No diary.md created
        entries = server._read_diary_entries("arjun", n=5, agents_dir=agents_dir)
        assert entries == [], f"expected [], got {entries!r}"


def test_08_diary_parses_entries():
    """3 # Day blocks → 3 entries with correct headers + bodies, most recent first."""
    with tempfile.TemporaryDirectory() as td:
        agents_dir = pathlib.Path(td) / "agents"
        (agents_dir / "arjun").mkdir(parents=True)
        diary = (
            "# Day 1\n"
            "First day body line one.\n"
            "First day body line two.\n"
            "\n"
            "# Day 2\n"
            "Second day body.\n"
            "\n"
            "# Day 3\n"
            "Third day body line.\n"
        )
        (agents_dir / "arjun" / "diary.md").write_text(diary, encoding="utf-8")
        entries = server._read_diary_entries("arjun", n=5, agents_dir=agents_dir)
        assert len(entries) == 3, f"expected 3 entries, got {len(entries)}"
        # Most recent first
        assert entries[0]["day_header"] == "# Day 3", f"got {entries[0]!r}"
        assert entries[1]["day_header"] == "# Day 2", f"got {entries[1]!r}"
        assert entries[2]["day_header"] == "# Day 1", f"got {entries[2]!r}"
        assert "Third day body line." in entries[0]["body"]
        assert "Second day body." in entries[1]["body"]
        assert "First day body line one." in entries[2]["body"]
        assert "First day body line two." in entries[2]["body"]


def test_09_diary_caps_at_5():
    """A diary with 8 # Day blocks returns exactly 5 entries (8,7,6,5,4)."""
    with tempfile.TemporaryDirectory() as td:
        agents_dir = pathlib.Path(td) / "agents"
        (agents_dir / "arjun").mkdir(parents=True)
        chunks = [f"# Day {i}\nBody for day {i}.\n" for i in range(1, 9)]
        (agents_dir / "arjun" / "diary.md").write_text("\n".join(chunks), encoding="utf-8")

        entries = server._read_diary_entries("arjun", n=5, agents_dir=agents_dir)
        assert len(entries) == 5, f"expected 5, got {len(entries)}"
        headers = [e["day_header"] for e in entries]
        assert headers == ["# Day 8", "# Day 7", "# Day 6", "# Day 5", "# Day 4"], (
            f"unexpected ordering: {headers}"
        )


def test_11_state_includes_pacing_label():
    """/api/state surfaces world._state['_pacing_label'] as 'pacing_label'."""
    client, ws, td = _client_with_fresh_world()
    try:
        # default: empty string
        r = client.get("/api/state")
        assert r.status_code == 200
        body = r.json()
        assert "pacing_label" in body, f"pacing_label missing: {list(body.keys())}"
        assert body["pacing_label"] == "", f"expected empty default, got {body['pacing_label']!r}"

        ws._state["_pacing_label"] = "⏩ quiet stretch"
        r2 = client.get("/api/state")
        assert r2.json()["pacing_label"] == "⏩ quiet stretch"
    finally:
        td.cleanup()
        server._world = None


def test_12_scheduled_events_endpoint_shape():
    """/api/scheduled_events/active returns {"events": [...]} filtered by day/hour."""
    client, ws, td = _client_with_fresh_world()
    try:
        ws._state["day"] = 3
        ws._state["sim_time"] = 13 * 60  # 1:00pm
        ws._scheduled_events = [
            # Day 3, 13:00-14:00 — currently active
            {"day": 3, "start_hour": 13, "end_hour": 14, "type": "meetup",
             "location": "cyber_hub", "description": "Startup meetup",
             "affected_agents": "all"},
            # Day 3, 15:00-18:00 — starts in 2 hours, should be included
            {"day": 3, "start_hour": 15, "end_hour": 18, "type": "festival_prep",
             "location": "dhaba", "description": "Prep at dhaba",
             "affected_agents": "all"},
            # Day 3, 20:00-22:00 — too far in future, excluded
            {"day": 3, "start_hour": 20, "end_hour": 22, "type": "festival_prep",
             "location": "dhaba", "description": "Late prep",
             "affected_agents": "all"},
            # Day 4 — wrong day, excluded
            {"day": 4, "start_hour": 9, "end_hour": 18, "type": "monsoon",
             "description": "Rain", "affected_agents": "all"},
        ]
        r = client.get("/api/scheduled_events/active")
        assert r.status_code == 200, f"got {r.status_code}"
        body = r.json()
        assert "events" in body, f"events missing: {body}"
        types = sorted(ev["type"] for ev in body["events"])
        assert types == ["festival_prep", "meetup"], f"unexpected events: {types}"
    finally:
        td.cleanup()
        server._world = None


def test_13_scheduled_events_empty_when_no_world_data():
    """When _scheduled_events is empty, endpoint returns {'events': []}."""
    client, ws, td = _client_with_fresh_world()
    try:
        ws._scheduled_events = []
        r = client.get("/api/scheduled_events/active")
        assert r.status_code == 200
        assert r.json() == {"events": []}
    finally:
        td.cleanup()
        server._world = None


def test_10_root_serves_viewer_when_present():
    """GET / returns 200 with viewer.html content when the file exists."""
    sandbox = tempfile.NamedTemporaryFile(mode="w", suffix=".html",
                                          delete=False, encoding="utf-8")
    try:
        sandbox.write("<!DOCTYPE html><html><body>Sandbox viewer</body></html>")
        sandbox.close()
        original = server.VIEWER_PATH
        server.VIEWER_PATH = pathlib.Path(sandbox.name)
        try:
            client = TestClient(app)
            r = client.get("/")
            assert r.status_code == 200, f"got {r.status_code}"
            assert "Sandbox viewer" in r.text, f"unexpected body: {r.text!r}"
        finally:
            server.VIEWER_PATH = original
    finally:
        try:
            os.unlink(sandbox.name)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    # Story 2.2 (regression)
    ("GET /api/health returns 200 with status='ok'", test_health_200),
    ("GET /api/health includes llm_primary field", test_health_has_llm_primary),
    ("GET /api/llm returns provider and model", test_get_llm_returns_provider_and_model),
    ("POST /api/llm/gemini returns 200 with provider='gemini'", test_post_llm_gemini_returns_200),
    ("POST /api/llm/ollama returns 200 with provider='ollama'", test_post_llm_ollama_returns_200),
    ("POST /api/llm/invalid returns 400", test_post_llm_invalid_returns_400),
    ("After POST gemini, GET /api/llm returns gemini", test_after_post_gemini_get_returns_gemini),
    ("After POST ollama, GET /api/llm returns ollama", test_after_post_ollama_get_returns_ollama),
    # Story 6.1
    ("6.1 |  1. /api/health still works",                        test_01_health_still_works),
    ("6.1 |  2. /api/state returns 503 without world",           test_02_state_returns_503_without_world),
    ("6.1 |  3. /api/state basic shape",                         test_03_state_basic_shape),
    ("6.1 |  4. /api/state events capped at last 30",            test_04_state_events_capped_at_30),
    ("6.1 |  5. /api/map returns locations",                     test_05_map_endpoint),
    ("6.1 |  6. /api/agent/{unknown}/diary returns 404",         test_06_diary_unknown_agent_404),
    ("6.1 |  7. Diary empty when missing",                       test_07_diary_empty_when_missing),
    ("6.1 |  8. Diary parses entries (most recent first)",       test_08_diary_parses_entries),
    ("6.1 |  9. Diary caps at 5 (8 -> 8,7,6,5,4)",               test_09_diary_caps_at_5),
    ("6.1 | 10. GET / serves viewer.html when present",          test_10_root_serves_viewer_when_present),
    ("R2  | 11. /api/state includes pacing_label",                test_11_state_includes_pacing_label),
    ("R2  | 12. /api/scheduled_events/active filtering",          test_12_scheduled_events_endpoint_shape),
    ("R2  | 13. /api/scheduled_events/active empty when none",    test_13_scheduled_events_empty_when_no_world_data),
]


if __name__ == "__main__":
    print(f"\nRunning {len(TESTS)} server endpoint tests...\n")
    results = [run_test(name, fn) for name, fn in TESTS]
    passed = sum(results)
    failed = len(results) - passed
    print(f"\n{'='*50}")
    print(f"Results: {passed}/{len(results)} passed", end="")
    if failed:
        print(f"  ({failed} FAILED)")
        sys.exit(1)
    else:
        print("  — all PASS")
        sys.exit(0)
