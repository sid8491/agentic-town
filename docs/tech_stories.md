6# Gurgaon Town Life — Tech Stories

Stories are grouped by Epic/Phase. Each story has a clear definition of done.
Start Phase 1 first — later phases depend on earlier ones.

---

## Epic 1: Foundation

### Story 1.1 — Project Setup
**As a developer**, I want a clean Python 3.12 environment with all dependencies installed so I can start building immediately.

**Tasks:**
- Create `.venv` using `C:\Python312\python.exe -m venv .venv`
- Create `requirements.txt` with pinned versions:
  - `arcade>=3.0`
  - `fastapi`
  - `uvicorn`
  - `langgraph`
  - `litellm`
  - `google-generativeai`
  - `python-dotenv`
  - `websockets`
- Create `.env.example` with `GEMINI_API_KEY=` placeholder
- Create `.env` (gitignored) with actual key
- Verify: `python -c "import arcade, fastapi, langgraph, litellm"` passes

**Done when:** `pip install -r requirements.txt` succeeds with no errors on Python 3.12.

---

### Story 1.2 — World Map Definition
**As the engine**, I need a structured map of Gurgaon locations so agents know where they can go and what each place offers.

**Tasks:**
- Create `world/map.json` with all 8 locations
- Each location has: `id`, `name`, `type`, `description`, `connected_to[]`, `services[]`
- Services example: `["buy_food", "socialize"]` at cyber_hub
- Create `world/state.json` schema with: `sim_time`, `day`, `agents{}`, `events[]`

**Done when:** `world/map.json` loads without error and all locations are connected correctly.

---

### Story 1.3 — Agent Folder + Soul Files
**As a simulation designer**, I want all 10 agent folders created with rich, distinct soul files so each character feels genuinely different.

**Tasks:**
- Create `agents/{name}/` folders for all 10 agents
- Write `soul.md` for each agent (min 80 words, distinct voice and backstory):
  - arjun, priya, rahul, kavya, suresh, neha, vikram, deepa, rohan, anita
- Write starter `memory.md` for each (2–3 seed relationships + 1–2 known facts)
- Write starter `goals.md` for each (3 goals that fit their persona)
- Create empty `diary.md` for each

**Done when:** All 10 agents have all 4 files. Reading any soul.md feels like a distinct human being.

---

### Story 1.4 — World State Manager
**As the engine**, I need a class that owns and mutates world state so all agent tools have one source of truth.

**Tasks:**
- Create `engine/world.py` with `WorldState` class
- Methods: `load()`, `save()`, `get_agent(name)`, `update_agent(name, data)`, `get_nearby_agents(name)`, `move_agent(name, location)`, `get_time()`, `advance_time(minutes)`
- State lives in `world/state.json` and is loaded on startup
- Thread-safe (asyncio Lock for writes)

**Done when:** Unit test: create WorldState, move arjun to cyber_hub, save, reload — position persists.

---

## Epic 2: LLM + Tools

### Story 2.1 — LLM Abstraction Layer
**As the agent engine**, I need a single function to call either Ollama or Gemini so I never write provider-specific code in agent logic.

**Tasks:**
- Create `engine/llm.py` with `call_llm(prompt, tools=None)` function
- Reads `LLM_PRIMARY` from env/runtime config (`"ollama"` or `"gemini"`)
- Uses `litellm.completion()` under the hood
- Ollama model: `ollama/qwen3:27b`
- Gemini model: `gemini/gemini-1.5-flash`
- Returns structured response (tool call or text)
- Logs which provider was used + token count

**Done when:** `call_llm("Say hello in one word")` works with both providers when toggled.

---

### Story 2.2 — Runtime LLM Toggle
**As an observer**, I want to switch between Ollama and Gemini while the simulation is running without restarting.

**Tasks:**
- Add a global `LLMConfig` singleton in `engine/llm.py`
- Expose `set_primary(provider)` function
- Arcade: pressing `L` calls `set_primary()` and updates HUD display
- FastAPI: `POST /api/llm/{provider}` endpoint for web viewer control

**Done when:** Pressing L mid-sim switches provider. Next agent tick uses the new one. HUD shows active provider.

---

### Story 2.3 — Tool Engine
**As an agent**, I need all my tools implemented so my decisions actually change the world.

**Tasks:**
- Create `engine/tools.py` with all tools as Python functions
- File tools: `read_file`, `edit_file`, `append_diary`, `grep_memory`
- World tools: `move_to`, `look_around`, `check_needs`, `check_inventory`, `talk_to`, `ask_about`, `give_item`, `buy`, `sell`, `eat`, `sleep`, `work`
- Each tool takes `(agent_name, **kwargs)` and returns a string result
- `talk_to` deposits message into recipient's `world/state.json` inbox
- Define JSON schema for all tools (used in LLM prompt)

**Done when:** Each tool can be called in isolation and returns expected string output. No LLM required.

---

### Story 2.4 — Single Agent Decision Loop
**As a developer**, I want one agent (Arjun) to complete a full decision cycle so I can verify the LLM → tool → world pipeline end-to-end.

**Tasks:**
- Create `engine/agent.py` with `AgentRunner` class using LangGraph
- Graph nodes: `gather_context` → `llm_decide` → `execute_tool` → `reflect`
- `gather_context`: reads soul + needs + look_around + goals
- `llm_decide`: calls `call_llm()` with context + tool schemas
- `execute_tool`: calls the chosen tool from `tools.py`
- `reflect`: appends diary entry, optionally updates memory/goals
- Run Arjun for 3 ticks manually in a test script

**Done when:** Running `python -m engine.agent arjun` produces 3 diary entries and a world state change.

---

## Epic 3: Agent Engine

### Story 3.1 — Needs Decay System
**As the simulation**, I need agent needs to decay over game time so agents are driven to eat, sleep, and socialize.

**Tasks:**
- Create `engine/needs.py` with `decay_needs(agent_name, minutes_elapsed)` 
- Hunger: +8% per game hour (capped at 100%)
- Energy: -5% per game hour (capped at 0%)
- Mood: adjusted by events (tracked in world state event log)
- Decay runs every tick before agent decisions
- Critical thresholds written into agent context automatically

**Done when:** After simulating 8 game hours, hunger is ~64%, energy ~60%. Critical messages appear in agent context.

---

### Story 3.2 — Multi-Agent Async Loop
**As the simulation**, I need all 10 agents to take turns autonomously so the town feels alive without blocking on any single agent.

**Tasks:**
- Create tick loop in `engine/world.py`
- Each tick: advance time → decay needs → run all agents in parallel (asyncio.gather)
- Tick pacing: sleep 3 real seconds between ticks
- Agent decisions run concurrently — no agent waits for another
- World state writes are serialized (Lock) to prevent conflicts
- `talk_to` messages are queued and delivered at tick start

**Done when:** All 10 agents complete one tick in under 8 real seconds. Diary files all update. World state is consistent.

---

### Story 3.3 — Message / Gossip System
**As agents**, we need to deliver and receive messages across ticks so conversations feel natural even in async mode.

**Tasks:**
- Add `inbox: []` per agent in world state
- `talk_to(agent, message)` writes to recipient's inbox
- `ask_about(agent, topic)` writes a question; agent responds next tick if nearby
- At tick start, each agent reads inbox and it becomes part of their context
- Inbox cleared after being read
- Messages older than 2 game hours are discarded

**Done when:** Arjun sends a message to Priya. Next tick, Priya's context includes the message and she responds.

---

## Epic 4: Arcade Rendering

### Story 4.1 — Map Rendering
**As an observer**, I want to see the Gurgaon town map so I can understand where agents are.

**Tasks:**
- Create `main.py` with `arcade.Window` subclass
- Draw tile grid (30×20 tiles, 32px each)
- Color-code location zones (home=blue, work=gray, food=orange, social=green, transit=yellow)
- Draw location name labels
- Draw path lines between connected locations

**Done when:** Window opens showing a recognizable town layout with labeled zones.

---

### Story 4.2 — Agent Sprites + Movement
**As an observer**, I want to see the 10 agents as colored icons moving around the map.

**Tasks:**
- Each agent: colored circle + 2-letter initials (AR for Arjun, PR for Priya, etc.)
- Position maps from location ID to tile coordinates
- Smooth lerp movement between positions (0.5 second transition)
- Agents at the same location spread out slightly so they don't overlap

**Done when:** All 10 agents visible. Moving Arjun from apartment to dhaba in state.json shows smooth animation.

---

### Story 4.3 — Thought Bubbles + Name Tags
**As an observer**, I want to see what each agent is currently doing without clicking on them.

**Tasks:**
- Name tag above each agent sprite (agent's first name, small font)
- Thought bubble below name: last action taken (e.g., "buying chai..." or "reading goals...")
- Thought bubble fades after 5 real seconds
- If mood < 30: name tag turns red. If > 70: green.

**Done when:** After each tick, all agents show their action in a thought bubble.

---

### Story 4.4 — HUD (Heads-Up Display)
**As an observer**, I want a control bar showing simulation status and controls.

**Tasks:**
- Bottom bar: Day number, game time (e.g., "Day 4 — 2:30pm")
- Buttons: PAUSE (spacebar), SLOW (←), FAST (→)
- LLM toggle: shows active provider, click or press L to switch
- Top-right: scrolling event log (last 10 events, 1 line each)

**Done when:** HUD visible. Spacebar pauses tick loop. L switches LLM and updates display.

---

### Story 4.5 — Click to Inspect Agent
**As an observer**, I want to click an agent to read their recent diary entries.

**Tasks:**
- Click detection on agent sprites
- Opens side panel showing: agent name, current needs bars, last 3 diary entries
- Close panel by clicking elsewhere or pressing Escape
- Panel shows diary entries formatted with day headers

**Done when:** Clicking Arjun opens panel with his last 3 diary entries displayed cleanly.

---

## Epic 5: Persistence

### Story 5.1 — Auto-Save World State
**As a user**, I want the simulation to save automatically so I never lose progress.

**Tasks:**
- Save `world/state.json` every 5 real seconds (background task)
- Save on graceful shutdown (Ctrl+C handler)
- On startup: load existing state if present, else initialize fresh

**Done when:** Run sim for 2 minutes, close window, reopen — agents are at their last positions.

---

### Story 5.2 — Reset Command
**As a developer**, I want to wipe the simulation back to day 1 without touching soul files.

**Tasks:**
- `python main.py --reset` clears: `world/state.json`, all `memory.md`, all `diary.md`, all `goals.md`
- Restores `goals.md` from defaults in each `soul.md` (parse `# Default Goals` section)
- Prints confirmation before wiping: "Reset will clear X days of history. Continue? [y/N]"
- `python main.py --reset-all` also wipes `soul.md` (full factory reset)

**Done when:** After `--reset`, simulation starts at Day 1 with fresh memories but same personalities.

---

## Epic 6: Web Viewer

### Story 6.1 — FastAPI State Endpoint
**As the web viewer**, I need a JSON endpoint that returns the full current world state.

**Tasks:**
- Add `GET /api/state` to `server.py` returning world state as JSON
- Add `GET /api/agent/{name}/diary` returning last 5 diary entries
- Add `POST /api/llm/{provider}` to switch LLM remotely
- Run FastAPI in background thread alongside Arcade
- CORS enabled for local network access

**Done when:** `curl http://localhost:8000/api/state` returns valid JSON with all agent positions.

---

### Story 6.2 — HTML Canvas Web Viewer
**As a remote observer**, I want to open a browser tab and watch the simulation live.

**Tasks:**
- Create `viewer.html` served at `GET /`
- Polls `/api/state` every 2 seconds
- Draws: color-coded location zones, path lines, agent circles + initials
- Shows: thought bubbles, name tags, event log sidebar, day/time header
- Click agent circle: fetches `/api/agent/{name}/diary` and shows in panel
- LLM toggle button calls `POST /api/llm/{provider}`
- No external JS libraries — vanilla HTML5 Canvas only

**Done when:** Open `http://localhost:8000` in browser. Sim visible and updating live. Works from another device on same network.

---

## Epic 7: Polish

### Story 7.1 — Relationship Indicators
**As an observer**, I want to see which agents have strong relationships so I can follow the drama.

**Tasks:**
- Parse `memory.md` for relationship mentions at startup + after each memory update
- Draw thin lines between agents who are at the same location with positive relationship
- Line color: green = friendly, red = hostile, gray = neutral/unknown
- Relationship detected by keywords in memory: "trust", "like", "friend" vs "avoid", "distrust", "argued"

**Done when:** Arjun and Rohan (seeded as friendly) show a green line when both at dhaba.

---

### Story 7.2 — Daily Summary Notification
**As an observer**, I want a brief summary at the end of each game day so I can catch up on what happened.

**Tasks:**
- At midnight game time, generate a 3–5 line daily summary using LLM
- Input: all events from the day's event log
- Output: narrative summary ("Day 4: Arjun had a rough day at work. Neha and Rahul met at Cyber Hub...")
- Display in Arcade as a modal overlay for 5 real seconds
- Append to `world/daily_log.txt`

**Done when:** At end of Day 1, a narrative summary appears on screen and saves to file.

---

### Story 7.3 — Configurable Simulation Speed
**As an observer**, I want fine-grained control over simulation speed.

**Tasks:**
- 5 speed levels: 0.25x, 0.5x, 1x (default), 2x, 4x
- 1x = 3 real seconds per tick
- Speed affects tick sleep interval only — LLM calls still async
- HUD shows current speed multiplier
- At 4x, thought bubbles update so fast they're replaced immediately (by design)

**Done when:** All 5 speeds work. At 4x, full day completes in under 2 real minutes.

---

## Summary — Story Count by Phase

| Phase | Stories | Priority |
|-------|---------|---------|
| Epic 1: Foundation | 4 | Must have |
| Epic 2: LLM + Tools | 4 | Must have |
| Epic 3: Agent Engine | 3 | Must have |
| Epic 4: Arcade Rendering | 5 | Must have |
| Epic 5: Persistence | 2 | Must have |
| Epic 6: Web Viewer | 2 | Should have |
| Epic 7: Polish | 3 | Nice to have |
| **Total** | **23** | |

Build order: 1 → 2 → 3 → 4 → 5 → 6 → 7. Never skip ahead.
