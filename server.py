"""
server.py — FastAPI app for Gurgaon Town Life web viewer.

Exposes:
  GET  /                    — serves viewer.html (Story 6.2)
  GET  /api/health          — liveness check
  GET  /api/state           — dynamic world state (polled every 2s)
  GET  /api/map             — static location data (fetched once on load)
  GET  /api/agent/{name}/diary — last 5 diary entries for an agent
  GET  /api/llm             — current LLM provider + model
  POST /api/llm/{provider}  — switch active LLM provider at runtime

The shared WorldState is wired in via `set_world(world)` from main.py
before the uvicorn thread starts. Endpoints that need world state
return HTTP 503 until set_world() has been called.
"""

from __future__ import annotations

import pathlib
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from engine.llm import llm_config
from engine.world import WorldState

app = FastAPI(title="Gurgaon Town Life")

# CORS — allow all origins for local network access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Shared world wiring
# ---------------------------------------------------------------------------

_world: Optional[WorldState] = None

# All known agents — used to validate /api/agent/{name}/diary
ALL_AGENT_NAMES = {
    "arjun", "priya", "rahul", "kavya", "suresh",
    "neha", "vikram", "deepa", "rohan", "anita",
}


def set_world(world: WorldState) -> None:
    """Inject the running WorldState. Call once before starting uvicorn."""
    global _world
    _world = world


def _require_world() -> WorldState:
    if _world is None:
        raise HTTPException(status_code=503, detail={"error": "World not initialised"})
    return _world


# ---------------------------------------------------------------------------
# Viewer (Story 6.2 will create viewer.html)
# ---------------------------------------------------------------------------

VIEWER_PATH = pathlib.Path(__file__).parent / "viewer.html"


@app.get("/")
def serve_viewer():
    if VIEWER_PATH.exists():
        return FileResponse(str(VIEWER_PATH))
    raise HTTPException(status_code=404, detail={"error": "viewer.html not found"})


# ---------------------------------------------------------------------------
# Health + LLM endpoints (existing — unchanged behaviour)
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "llm_primary": llm_config.get_primary()}


@app.post("/api/llm/{provider}")
def set_llm_provider(provider: str) -> dict:
    """
    Switch the active LLM provider.

    Returns {"provider": "<name>", "model": "<litellm-model-string>"} on success.
    Returns HTTP 400 with {"error": "..."} if the provider name is invalid.
    """
    try:
        llm_config.set_primary(provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})
    return {"provider": llm_config.get_primary(), "model": llm_config.get_model()}


@app.get("/api/llm")
def get_llm_provider() -> dict:
    return {"provider": llm_config.get_primary(), "model": llm_config.get_model()}


# ---------------------------------------------------------------------------
# /api/state — dynamic world state (Story 6.1)
# ---------------------------------------------------------------------------


@app.get("/api/state")
def get_state() -> dict:
    """Return the current dynamic state for the viewer."""
    world = _require_world()
    t = world.get_time()

    # Filter agents — strip 'inbox' (internal routing), keep everything else.
    agents_out: dict = {}
    for name, agent in world.get_all_agents().items():
        agents_out[name] = {k: v for k, v in agent.items() if k != "inbox"}

    events = world._state.get("events", [])
    last_30 = events[-30:]

    return {
        "day": t["day"],
        "sim_time": t["sim_time"],
        "time_str": t["time_str"],
        "paused": t["paused"],
        "speed": world._state.get("speed", 1.0),
        "llm_primary": world._state.get("llm_primary", "ollama"),
        "agents": agents_out,
        "events": last_30,
    }


# ---------------------------------------------------------------------------
# /api/map — static map (Story 6.1)
# ---------------------------------------------------------------------------


@app.get("/api/map")
def get_map() -> dict:
    """Return the full list of map locations."""
    world = _require_world()
    return {"locations": world.get_all_locations()}


# ---------------------------------------------------------------------------
# /api/agent/{name}/diary — last 5 diary entries (Story 6.1)
# ---------------------------------------------------------------------------


def _read_diary_entries(
    name: str,
    n: int = 5,
    agents_dir: pathlib.Path = pathlib.Path("agents"),
) -> list[dict]:
    """Parse `agents/{name}/diary.md` into entries.

    Each entry: {"day_header": "# Day N", "body": "..."}.
    Returns the last *n* entries, most-recent-first.
    Returns [] if the file doesn't exist or is empty.
    """
    diary_path = agents_dir / name / "diary.md"
    if not diary_path.exists():
        return []
    try:
        text = diary_path.read_text(encoding="utf-8")
    except OSError:
        return []
    if not text.strip():
        return []

    entries: list[dict] = []
    current_header: Optional[str] = None
    current_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("# Day"):
            if current_header is not None:
                entries.append({
                    "day_header": current_header,
                    "body": "\n".join(current_lines).strip(),
                })
            current_header = line
            current_lines = []
        elif current_header is not None:
            current_lines.append(line)
    if current_header is not None:
        entries.append({
            "day_header": current_header,
            "body": "\n".join(current_lines).strip(),
        })

    if not entries:
        return []
    last_n = entries[-n:]
    last_n.reverse()  # most-recent-first
    return last_n


@app.get("/api/agent/{name}/diary")
def get_agent_diary(name: str) -> dict:
    """Return the last 5 diary entries for *name*, most recent first."""
    if name not in ALL_AGENT_NAMES:
        raise HTTPException(status_code=404, detail={"error": f"Unknown agent: {name}"})
    entries = _read_diary_entries(name, n=5)
    return {"agent": name, "entries": entries}
