# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Gurgaon Town Life** — an autonomous multi-agent simulation set in modern Gurgaon, India. Ten AI characters with distinct personalities live, work, and interact in a persistent virtual town. Agents make decisions via LLM (Ollama locally or Gemini via API). Observers watch via an Arcade desktop window or browser-based web viewer. No player control — pure observation.

Full spec: `docs/tech_document.md`. Ordered build stories: `docs/tech_stories.md`.

---

## Environment

- **Python:** 3.12 only — `C:\Python312\python.exe`
- **Venv:** `.venv\` in project root
- **Activate (Windows bash):** `source .venv/Scripts/activate`
- **Install deps:** `pip install -r requirements.txt`
- **API keys:** `.env` file (never commit) — see `.env.example`

---

## Running the Project

```bash
# Full simulation (Arcade window + background web server)
python main.py

# Reset world state but keep agent personalities
python main.py --reset
# (soul.md is never modified at runtime, so --reset is the only factory-fresh
#  command needed. To replace souls themselves, use `git checkout agents/`.)

# Test a single agent decision loop (no Arcade)
python -m engine.agent arjun

# Web viewer only (no Arcade window)
python server.py
```

Web viewer available at `http://localhost:8000` once `server.py` or `main.py` is running.

---

## Architecture

Three layers that are strictly separated:

**1. Engine** (`engine/`) — all simulation logic, no rendering
- `world.py` — `WorldState` singleton: owns `world/state.json`, thread-safe via asyncio Lock. Single source of truth for all agent positions, needs, inventories, inboxes, and sim time.
- `agent.py` — `AgentRunner` per agent: LangGraph graph with nodes `gather_context → llm_decide → execute_tool → reflect`. Agents run concurrently each tick via `asyncio.gather`.
- `tools.py` — all tool functions: `(agent_name, **kwargs) → str`. Tools either mutate `WorldState` or read/write agent files. No LLM calls inside tools. `move_to` runs full BFS and walks every hop in one call — agents can be sent to any location, not just adjacent ones; `look_around` shows all reachable locations so the LLM picks freely.
- `llm.py` — `LLMConfig` singleton + `call_llm(prompt, tools=None)`. Abstracts Ollama and Gemini behind one interface via `litellm`. Toggle provider at runtime via `LLMConfig.set_primary("ollama"|"gemini")`.
- `needs.py` — `decay_needs(agent_name, minutes_elapsed)`: hunger +8%/hr, energy -5%/hr, mood event-driven.

**2. Renderer** (`main.py`) — Arcade window, reads `WorldState` every frame, never writes to it directly. All rendering code lives here. Keyboard/click handlers call engine methods or `LLMConfig.set_primary()`.

**3. Web server** (`server.py`) — FastAPI app runs in a background thread. Exposes `GET /api/state`, `GET /api/agent/{name}/diary`, `GET /api/agent/{name}/avatar`, `GET /api/relationships`, `POST /api/llm/{provider}`. Serves `viewer.html`. No simulation logic here — reads `WorldState` and proxies to `LLMConfig`.

---

## Agent File System

Each agent lives in `agents/{name}/` with four files:

| File | Written by | Changes at runtime |
|------|-----------|-------------------|
| `soul.md` | Developer | Never — treat as read-only |
| `memory.md` | Agent (LLM) | Yes — agent rewrites after significant events |
| `diary.md` | Agent (LLM) | Append-only — one entry per game day |
| `goals.md` | Agent (LLM) | Yes — agent rewrites each morning |

Portrait images live alongside the agent directories as `agents/{name}.png` (jpg/jpeg/webp also supported). Drop a file there and the web viewer picks it up immediately via `GET /api/agent/{name}/avatar` — no restart needed.

The 10 agents: `arjun`, `priya`, `rahul`, `kavya`, `suresh`, `neha`, `vikram`, `deepa`, `rohan`, `anita`.

---

## Time System

- 1 real second = 5 game minutes
- 1 tick = 3 real seconds = 15 game minutes
- Full 24-hour game day ≈ 5 real minutes (96 ticks)
- Tick loop: advance time → decay needs → run all 10 agents in parallel → save state → sleep
- **Per-agent schedules**: `engine/agent.py` injects a `=== SCHEDULE ===` section into the
  LLM prompt based on the agent's archetype (office_worker, vendor, retired, homemaker,
  entrepreneur, student, night_owl) and `sim_time` — sleep window, work hours, morning
  routine, evening wind-down. No extra LLM calls.
- **Night auto-speed**: `SimulationLoop._tick` bumps `world.speed` to 4x when ≥7 agents
  have `last_action` containing "sleep", and drops back to 1x when <5 are sleeping.
  Effective fast-forward window: ~3am – 5am.

---

## Key Design Constraints

- **Never call the Claude/Anthropic API** — LLM calls go through `engine/llm.py` using Ollama (`gemma4:e4b`) or Gemini (`gemini-2.5-flash`) via `litellm`.
- **`soul.md` is never modified at runtime** — it defines personality and is injected read-only into agent context.
- **Tools never call the LLM** — tool functions are pure Python that mutate state or files.
- **WorldState writes always go through the asyncio Lock** — never write `state.json` directly from multiple coroutines.
- **Web viewer (`viewer.html`) is vanilla JS + HTML5 Canvas only** — no npm, no frameworks, no build step.
- **Rendering is always a consumer of state, never a producer** — Arcade and the web viewer only read, never write world state.

---

## Parallelisation Hints for Sub-Agents

These tasks are independent and can be delegated to parallel sub-agents:

- Writing `soul.md` / `memory.md` / `goals.md` files for agents (split into batches of 3–4)
- `engine/llm.py` and `engine/tools.py` (no shared code)
- `world/map.json` and `world/state.json` schema
- `viewer.html` and `engine/needs.py`
- Any two agents' file sets are fully independent
