"""
tests/test_server.py — FastAPI endpoint tests for Story 2.2.

Uses fastapi.testclient.TestClient so no live server is needed.

Run:
    .venv/Scripts/python.exe tests/test_server.py
"""

import sys
import os

# Ensure project root is on sys.path so that `server` and `engine` are importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from server import app
from engine.llm import llm_config

client = TestClient(app)

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
        print(f"  {FAIL}  {name}: unexpected error — {exc}")
        return False


# ---------------------------------------------------------------------------
# Test definitions
# ---------------------------------------------------------------------------


def test_health_200():
    """GET /api/health returns HTTP 200."""
    r = client.get("/api/health")
    assert r.status_code == 200, f"expected 200, got {r.status_code}"
    data = r.json()
    assert data["status"] == "ok", f"expected status='ok', got {data.get('status')!r}"


def test_health_has_llm_primary():
    """GET /api/health includes llm_primary field."""
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert "llm_primary" in data, f"llm_primary key missing from: {data}"


def test_get_llm_returns_provider_and_model():
    """GET /api/llm returns current provider and model."""
    r = client.get("/api/llm")
    assert r.status_code == 200, f"expected 200, got {r.status_code}"
    data = r.json()
    assert "provider" in data, f"provider key missing from: {data}"
    assert "model" in data, f"model key missing from: {data}"
    # Values must be non-empty strings
    assert isinstance(data["provider"], str) and data["provider"], "provider must be a non-empty string"
    assert isinstance(data["model"], str) and data["model"], "model must be a non-empty string"


def test_post_llm_gemini_returns_200():
    """POST /api/llm/gemini returns 200 with provider='gemini'."""
    r = client.post("/api/llm/gemini")
    assert r.status_code == 200, f"expected 200, got {r.status_code} — body: {r.text}"
    data = r.json()
    assert data.get("provider") == "gemini", f"expected provider='gemini', got {data.get('provider')!r}"


def test_post_llm_ollama_returns_200():
    """POST /api/llm/ollama returns 200 with provider='ollama'."""
    r = client.post("/api/llm/ollama")
    assert r.status_code == 200, f"expected 200, got {r.status_code} — body: {r.text}"
    data = r.json()
    assert data.get("provider") == "ollama", f"expected provider='ollama', got {data.get('provider')!r}"


def test_post_llm_invalid_returns_400():
    """POST /api/llm/invalid returns HTTP 400."""
    r = client.post("/api/llm/invalid_provider")
    assert r.status_code == 400, f"expected 400, got {r.status_code} — body: {r.text}"


def test_after_post_gemini_get_returns_gemini():
    """After POST /api/llm/gemini, GET /api/llm returns gemini."""
    client.post("/api/llm/gemini")
    r = client.get("/api/llm")
    assert r.status_code == 200
    data = r.json()
    assert data.get("provider") == "gemini", (
        f"expected provider='gemini' after switching, got {data.get('provider')!r}"
    )


def test_after_post_ollama_get_returns_ollama():
    """After POST /api/llm/ollama, GET /api/llm returns ollama (resets state)."""
    client.post("/api/llm/ollama")
    r = client.get("/api/llm")
    assert r.status_code == 200
    data = r.json()
    assert data.get("provider") == "ollama", (
        f"expected provider='ollama' after switching back, got {data.get('provider')!r}"
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    ("GET /api/health returns 200 with status='ok'", test_health_200),
    ("GET /api/health includes llm_primary field", test_health_has_llm_primary),
    ("GET /api/llm returns provider and model", test_get_llm_returns_provider_and_model),
    ("POST /api/llm/gemini returns 200 with provider='gemini'", test_post_llm_gemini_returns_200),
    ("POST /api/llm/ollama returns 200 with provider='ollama'", test_post_llm_ollama_returns_200),
    ("POST /api/llm/invalid returns 400", test_post_llm_invalid_returns_400),
    ("After POST gemini, GET /api/llm returns gemini", test_after_post_gemini_get_returns_gemini),
    ("After POST ollama, GET /api/llm returns ollama", test_after_post_ollama_get_returns_ollama),
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
