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
- `soul.md` is never touched. It's developer-authored and never mutated at runtime,
  so `--reset` already gives a true factory-fresh sim. To replace souls themselves,
  use `git checkout agents/`.

**Done when:** After `--reset`, simulation starts at Day 1 with fresh memories but same personalities.

---

### Story 5.3 — Time-Aware Schedules + Night Auto-Speed
**As an observer**, I want agents to follow believable daily routines and quiet nights to fast-forward so the sim is interesting at any hour.

**Tasks:**
- Per-agent `archetype` mapping (office_worker, vendor, retired, student, night_owl, homemaker, entrepreneur)
- Sleep window + work hours per archetype, used to compose a `schedule_guidance` string
- Inject the guidance into the agent prompt (separate `=== SCHEDULE ===` section before the decision ladder)
- During sleep window: instruct sleep unless hunger > 85 or energy < 10
- During work hours (office_worker, vendor, entrepreneur): instruct work
- Within 90 min after wake-up: morning routine
- Within 2 hrs before sleep: evening wind-down
- `SimulationLoop._tick` checks `last_action` of all 10 agents; if ≥7 contain "sleep",
  auto-bump speed to 4x. If <5 are sleeping and speed is currently ≥4x, drop back to 1x.

**Done when:** At 3am all 10 agents sleep and the clock visibly fast-forwards; at 9am most are
out and about and the clock returns to 1x.

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

---

## Epic 8: Spectator Experience

Stories in this epic are all `viewer.html`-only changes unless noted. No backend changes required for 8.1–8.5. Build in order — 8.4 depends on the conversation detection introduced in 8.3.

---

### Story 8.1 — Floating Action Labels on Map Sprites
**As a spectator**, I want to see what each agent is doing directly on the map so I don't have to click anyone to understand the scene.

**Tasks:**
- Below each sprite on the canvas, draw a small pill label: `[icon] [short action text]`
- Text is the same `act.label` already computed by `detectActivity()` (e.g., "Eating", "Working", "Chatting")
- Label fades to 30% opacity after 8 real seconds of no state change (agent idle), returns to full opacity on next action change
- Label truncated to ~18 characters max to avoid overlap
- Font: 9px Inter, background: semi-transparent dark pill (like the existing `pill` CSS class), text color matches agent color
- Keep name tag above sprite; label goes below

**Done when:** All 10 agents show a readable activity label below their sprite. Label updates within 2 seconds of action change. No label overlaps the location box name text.

---

### Story 8.2 — Needs Crisis Visual Alerts
**As a spectator**, I want a visual warning when an agent is about to collapse from hunger or exhaustion so I can follow the tension without opening the inspector.

**Tasks:**
- After drawing each sprite circle, check `ag.hunger` and `ag.energy` from state
- If `hunger > 75`: draw a pulsing orange halo around the sprite (`ctx.shadowColor`, `ctx.shadowBlur` animated via `animT`)
- If `energy < 25`: draw a pulsing blue-white halo (different color from hunger to distinguish)
- If both: orange takes priority (hunger is more urgent)
- Pulse period: ~2 real seconds (use `Math.sin(animT / 1000)` to drive blur radius between 8–18px)
- No halo when agent is in crisis and sleeping — they're already handling it

**Done when:** An agent with hunger > 75 visibly pulses orange on the map. Two different crises (hunger vs energy) show different halo colors. Halo disappears once need is resolved.

---

### Story 8.3 — Narrative Event Feed
**As a spectator**, I want the event feed to read like a gossip column rather than a raw log so the drama feels real.

**Tasks:**
- Replace raw event text rendering with a `narrativise(ev)` function that reformats each entry:
  - If text matches `"{name}: moved to {loc}"` → *"{Name} heads to {loc display name}"*
  - If text matches talk/chat/gossip → prefix with 💬 and style the entry with the `--blue` accent
  - If text matches eat/food → prefix with 🍛
  - If text matches sleep → prefix with 💤, mute the color
  - If text matches work/earn → prefix with 💼
  - All other events → keep as-is but capitalize first letter
- Add a thin left-border color strip per agent (already have agent color — apply it as a 3px left border on the `event-item` div)
- Tag high-drama events (talk + two agents at same location) with a small 🔥 badge in the top-right corner of the event pill
- Timestamp shown as game time (already in `ev.time`) — format as `HH:MM` without seconds

**Done when:** Event feed reads like short news items. A "talk" event between two agents shows the 🔥 tag. Feed is noticeably more readable than before.

---

### Story 8.4 — Live Speech Bubbles for Conversations
**As a spectator**, I want to see active conversations rendered on the map between agent sprites so the social dynamics feel spatially real.

**Tasks:**
- Each poll cycle, detect pairs of agents at the same location where both have `last_action` containing "talk", "chat", "gossip", or "conversat"
- For each such pair, draw a speech bubble arc between their two sprite positions on the canvas:
  - A rounded rectangle anchored midway between the two sprites
  - Content: first 40 characters of either agent's last_action text (whichever is longer), truncated with `…`
  - Background: `rgba(30,30,50,0.88)`, border: `rgba(208,191,255,0.5)` (soft purple), font: 9px Inter
  - Small triangle pointer toward the initiating agent
- Bubble fades out after 6 real seconds if the agents stop talking
- Maximum 3 bubbles shown simultaneously (most recent pairs win) to avoid clutter
- Do not draw bubbles for sleeping agents

**Done when:** When Neha and Arjun are both at a location and talking, a speech bubble appears between their sprites showing a fragment of their conversation. Bubble disappears when they part ways.

---

### Story 8.5 — "What's Happening Now" Spotlight Strip
**As a spectator**, I want a live editorial summary of the most interesting thing happening right now so I have a focal point at any moment.

**Tasks:**
- Add a slim horizontal strip (28px tall) between the overview bar and the map area in `viewer.html`
- Every poll cycle, compute a "spotlight sentence" from current state using this priority ladder:
  1. If any agent has both `hunger > 80` AND is not at a food location → *"⚠️ {Name} is starving and hasn't found food yet"*
  2. If 3+ agents are at the same social/food location → *"🎉 {Names} are all gathered at {location}"*
  3. If a talk event appears in the last 3 events involving 2 named agents → *"💬 {Name} and {Name} are having a conversation at {location}"*
  4. If ≥7 agents are sleeping → *"🌙 The town is quiet — {N} of 10 are asleep"*
  5. Fallback → *"📍 {most-active-location} is the busiest spot right now ({N} agents)"*
- Strip scrolls the sentence in via a CSS slide-up transition when it changes
- Background: `var(--surface)`, subtle left accent bar in `var(--accent)` color
- Strip is purely client-side computed — no new API endpoint needed

**Done when:** The spotlight strip always shows a meaningful sentence. It updates within 2 seconds of a state change. The sentence changes when the most interesting situation changes.

---

### Story 8.6 — Day-Change Recap Overlay
**As a spectator**, I want a brief dramatic recap when a new game day begins so I feel the passage of time and can catch up on what I missed.

**Tasks:**
- Track `lastDay` in viewer JS state (initialized from first `/api/state` response)
- When `stateData.day > lastDay`, trigger recap overlay:
  - Full-screen semi-transparent overlay (`rgba(12,13,20,0.88)`)
  - Large centered card showing:
    - `"Day {N} — Complete"` headline
    - Most-visited location (computed from events: count `moved to` mentions per location)
    - Most active agent (agent with most events in last day's event history)
    - Event count for the day
    - One randomly selected event from the day as a pull-quote
  - Dismiss automatically after 6 real seconds, or on any click/keypress
- All data derived purely from the existing `/api/state` event list — no new backend endpoint
- Overlay uses a CSS fade-in/out transition

**Done when:** When Day 1 → Day 2 transitions, the overlay appears for 6 seconds with a populated recap card. It dismisses cleanly and doesn't block the next poll cycle.

---

### Story 8.7 — Conversation History Panel
**As a spectator**, I want to read the full back-and-forth between two agents so I can follow the story arc of their relationship.

**Tasks:**
- Add a `GET /api/conversations` endpoint to `server.py` — returns the rolling log of all `talk_to` messages (last 300, stored in `world/state.json["conversations"]`); optional `?a=&b=` query params filter by agent pair
- In `tools.py`, call `world.add_conversation(sender, recipient, message)` inside `talk_to()` whenever a message is delivered
- In `viewer.html`, add a `#convo-panel` overlay (chat-bubble style, sent=right/blue, received=left/neutral)
- Clicking a live speech bubble on the map opens the panel filtered to that pair
- Clicking the activity card in the inspector sidebar (when the agent is talking) also opens the panel for that pair
- Panel fetches `GET /api/conversations?a=X&b=Y` on open and re-fetches every 4 seconds while visible
- Close button + click-outside dismisses; no state is persisted — purely ephemeral UI

**Done when:** Clicking a "Neha is talking to Arjun" speech bubble opens a scrollable chat panel showing their full message history from the current session. Replies from both sides are visible.

---

### Story 8.8 — Hinglish Agent Speech
**As a spectator**, I want agents to speak and write in modern Indian English (Hinglish) — a natural mix of English and Hindi romanised — so the simulation feels authentically set in urban India.

**Tasks:**
- In `engine/agent.py`, add a `=== HOW YOU SPEAK ===` section to the main decision prompt:
  - Instruct the agent to mix Hindi words/phrases naturally into English sentences
  - Provide ~10 example words (yaar, bhai, kya, acha, nahi, haan, sahi, thoda, zyada, arrey)
  - Ratio guidance: ~70% English, ~30% Hindi; no Devanagari script — romanised only
  - Apply to all `talk_to` messages and internal monologue
- Update the `reflect()` diary prompt system message to `"a Gurgaon resident writing in your private diary in Hinglish"` and include a short example Hinglish diary line

**Done when:** After a few ticks, `talk_to` messages and diary entries contain Hindi words interspersed naturally in English sentences. No Devanagari appears. The tone matches how a young urban Delhiite actually texts.

---

## Epic 9: Emergent Behavior & Story Depth

This epic addresses the "diary repetition / conversation trap" problem identified in audit:
agents currently default to messaging each other every tick, recycle the same 1–2 relationships,
write near-identical diary entries, and have no cross-day continuity. The world has no
friction (instant travel, free food, no bills), no conflict (nobody can refuse), and no
memory of yesterday. These stories give agents stakes, memory, and the ability to disagree,
so the same well-written souls can produce actual stories instead of positivity loops.

Build in order — 9.1 and 9.2 unlock the rest. 9.3–9.5 are independent of each other and
can be parallelised after 9.2 lands.

---

### Story 9.1 — Per-Pair Conversation History in Agent Context
**As an agent**, I want to remember what I said to someone yesterday so I don't restart
the same conversation every tick.

**Tasks:**
- In `engine/world.py`, add `get_conversation_history(agent_a, agent_b, limit=10)` that
  reads from the existing `conversations` rolling log and returns the last N messages
  between this specific pair (most recent first), formatted as `"[time] sender: text"`.
- In `engine/agent.py`'s `gather_context` node, for each unread inbox sender, fetch the
  last 10 messages with that sender and inject them as a `=== RECENT EXCHANGES WITH {name} ===`
  block in the prompt (one block per unread sender, max 3 blocks to stay under token budget).
- Replace the current "Have unread messages? → reply with talk_to — acknowledge what they said"
  directive with: *"Have unread messages? Read the full thread above first. Has this loop
  been circling for 3+ exchanges with no concrete plan? Either propose something specific
  (time + place + activity) or stop messaging and do something else."*
- Add a hard rule: *"Do NOT send a message that repeats the gist of your last 3 messages
  to the same person. If you have nothing new to say, take an action instead."*

**Done when:** Across 20 ticks, no two consecutive `talk_to` messages from the same agent
to the same recipient have a cosine-similarity > 0.85 on bag-of-words. Diary entries stop
showing "finally messaged X" repeatedly within a single game day.

---

### Story 9.2 — Night Reflection + Yesterday's Lesson
**As an agent**, I want yesterday's reflection to shape today's behavior so I'm not
running Groundhog Day.

**Tasks:**
- In `engine/agent.py`, add a `night_reflection(agent_name)` async function called once
  per agent at the day-boundary tick (when `sim_time` rolls past midnight).
- The function makes one LLM call with: soul.md, today's diary entries, today's events
  involving this agent. Prompt: *"Write 2–3 sentences. What surprised you today? What
  pattern in your own behavior do you notice? What's one concrete thing you want to do
  differently tomorrow?"*
- Store the result in `world/state.json` under `agents[name].yesterday_reflection`
  (overwrite each day — only the most recent is kept).
- In `gather_context`, if `yesterday_reflection` is set, inject it as a
  `=== YESTERDAY YOU WROTE ===` block immediately above the decision ladder.
- Add to the decision ladder: *"If yesterday's reflection names a behavior to change,
  pick an action that honors it — even if it's harder than the default."*

**Done when:** At the Day 1 → Day 2 boundary, every agent has a non-empty
`yesterday_reflection` field. On Day 2, at least 3 agents take an action that
verifiably differs from their Day 1 default pattern (e.g., Arjun who messaged Kavya 9
times on Day 1 messages her ≤3 times on Day 2, OR sends a concrete plan on first contact).

---

### Story 9.3 — Refuse / Disagree Tools
**As an agent**, I want to be able to say no, push back, or set boundaries so the
simulation produces conflict, not just compliance.

**Tasks:**
- Add `refuse(target, reason)` to `engine/tools.py`: deposits a structured "refusal"
  message into target's inbox. Marks the sender's `last_action` as
  `"declined to {target}: {reason}"`. Costs the sender -2 mood; costs the target -3 mood.
- Add `disagree(target, topic, position)`: deposits a stronger pushback message into
  target's inbox, tagged with `event_type: "conflict"`. Both parties get a small
  short-term mood hit (-4 each) but the relationship trust score (per Story 7.1) is
  modulated based on whether they later reconcile.
- In the decision ladder prompt, add: *"You are allowed to refuse. If a request conflicts
  with your goals or values, use `refuse` — agreeing to everything is not in character.
  If you genuinely disagree about something that matters, use `disagree` rather than
  pretending to agree."*
- In each soul.md, ensure there's at least one explicit "things I push back on" line
  (e.g., Priya: *"I don't pretend to enjoy small talk when I'm tired"*; Arjun: *"I
  resist commitments that pull me away from the startup"*). Audit and add where missing.

**Done when:** Across 100 ticks, at least 5 `refuse` and 2 `disagree` calls are made
across the 10 agents organically (no scripted prompts). Diary entries reflect the
emotional impact ("Kavya said no. I'm trying not to read into it.").

---

### Story 9.4 — Rent + Daily Bills (Economic Pressure)
**As the simulation**, I need agents to face real money pressure so working and
spending become meaningful choices.

**Tasks:**
- Add `monthly_rent` (int, coins) per agent in `world/state.json`, sized to archetype:
  office_worker 60, vendor 25, retired 40, student 20, entrepreneur 50, homemaker 0
  (paid by partner), night_owl 35.
- Every 4 game days at midnight, deduct rent from each agent's coin balance. If the
  agent goes negative, set `agent.financial_stress = true` for the next 4 days.
- When `financial_stress` is true, inject into the prompt: *"You are behind on rent.
  Consider working extra, eating cheap (eat at home, skip eat_out), or asking someone
  you trust for help."*
- Audit starting balances: Rohan, Rahul, Deepa, Anita should start with 1–1.5x rent
  (tight); Vikram, Priya can start with 3–4x (comfortable). This creates baseline
  inequality that drives behavior diversity.
- Add a viewer indicator: agents with `financial_stress = true` show a small ₹! badge
  next to their sprite (purely cosmetic, drawn in viewer.html).

**Done when:** By Day 5, at least 2 agents have hit `financial_stress`. Their next-day
behavior shows an observable shift toward `work` actions and away from `eat_out`. At
least one agent uses `talk_to` to ask another agent for help with money.

---

### Story 9.5 — Shared Plans + Joint Actions
**As two agents**, when we agree to meet, we should actually meet — and feel
disappointment if the other doesn't show.

**Tasks:**
- Add `shared_plans` array in `world/state.json`, each entry:
  `{participants: [a, b], location, target_time, status: "pending"|"completed"|"failed", created_at}`.
- Add `propose_plan(target, location, time, activity)` tool — writes a pending plan
  and a `talk_to` message asking confirmation.
- Add `confirm_plan(plan_id)` and `decline_plan(plan_id, reason)` tools — target
  responds; plan flips to `confirmed` or `declined`.
- At each tick, the engine checks pending/confirmed plans:
  - If `target_time` reached and both participants are at `location` → mark `completed`,
    grant +8 mood to both, restore +50% hunger if location offers food, log a narrative
    event ("Arjun and Kavya had coffee at cyber_hub, as planned").
  - If `target_time` reached and one or both absent → mark `failed`. The agent who
    showed up gets -10 mood and a memory entry: *"{Other} didn't show up at {location}
    today. Need to figure out what that means."* The absent agent gets a soft reminder
    in their next prompt: *"You missed your plan with {other} at {location}. They
    waited."*
- In the decision ladder, add above social directives: *"If you have a confirmed plan
  in the next 30 game minutes, prioritize moving toward `{plan.location}` over
  everything except critical hunger/energy."*

**Done when:** Within 100 ticks, at least 3 plans are proposed organically. At least
one completes successfully (both show up, both get mood boost). At least one fails
(one shows, one doesn't) and the resulting diary entries reflect real disappointment
and not "felt light."

---

### Story 9.6 — Personality-Weighted Decision Ladder
**As distinct characters**, we should make distinct choices in the same situation —
not all follow the identical default flowchart.

**Tasks:**
- In `engine/agent.py`, add `personality_modifier(agent_name, mood, archetype) -> str`
  returning a short prompt fragment injected just before the decision ladder.
- Per-archetype directives:
  - office_worker (Arjun, Priya, Neha): *"You instinctively prefer working through
    problems over socializing about them. When tired, you'd rather be alone than in a
    crowd."*
  - vendor (Suresh, Rahul): *"You read your surroundings before acting. Notice who's
    around. You initiate small interactions easily."*
  - retired (Vikram): *"You move at your own pace. You don't chase anyone. You prefer
    being asked over asking."*
  - homemaker (Deepa, Anita): *"Your default radius is family/household. You step
    outside that radius rarely and deliberately."*
  - student (Kavya): *"You're reactive and emotional. You text first, think later.
    Big mood swings are normal."*
  - night_owl (Rohan): *"Daytime drains you. Evenings energize you. You avoid
    morning crowds."*
  - entrepreneur (others): *"You're constantly evaluating people for usefulness or
    signal. You initiate strategically, not warmly."*
- Add mood-based overrides:
  - mood < 30: *"You're depleted. Doing the reach-out is harder than usual but might
    matter more. Or — protect yourself. Both are valid."*
  - mood > 75: *"You're flowing. Take the harder action you've been postponing."*

**Done when:** Across 50 ticks, the 10 agents show measurable behavioral spread on
identical situations (e.g., when 3+ agents are at cyber_hub, the office_workers are
significantly more likely to leave or sit alone than the vendors/students). Diary
voice differences sharpen — readers can identify agent from a single anonymized
diary entry with >70% accuracy.

---

### Story 9.7 — Memory Consolidation (Daily Pattern Recognition)
**As an agent**, I want my long-term memory to grow with what I've actually
learned, not just seed facts from Day 1.

**Tasks:**
- At the day-boundary tick (same hook as Story 9.2), after `night_reflection`,
  trigger `consolidate_memory(agent_name)` if it's been ≥3 days since the last
  consolidation for that agent.
- The function makes one LLM call with: current `memory.md`, last 3 days of diary
  entries, last 3 days of events involving this agent. Prompt: *"You are this agent
  reviewing your recent past. Update your memory.md. Add new observations about
  yourself or others. Sharpen or correct existing entries that turned out wrong.
  Keep entries terse — one to two lines each. Do not delete the seed relationships,
  but you can refine them."*
- Write the result back to `agents/{name}/memory.md`, replacing the file.
- Log a `memory_updated` event to the world event log so observers can see when an
  agent's understanding shifted.

**Done when:** By Day 6, at least 5 agents have a `memory.md` that differs
materially from its Day 1 starting state. The diffs include at least one new
observation about another agent that wasn't in the seed (e.g., *"Priya talks
about burnout but never asks for help — that's a pattern"*).

---

### Story 9.8 — Scheduled External Events
**As the world**, I should occasionally throw something at the agents so they
adapt instead of grinding the same routine.

**Tasks:**
- Create `world/scheduled_events.json` with a list of events:
  `{day, hour, location, type, description, affected_agents: [...] | "all" | "archetype:office_worker"}`.
- Seed examples:
  - Day 3, 13:00, cyber_hub, "meetup", *"A small startup meetup is happening — relevant
    for entrepreneurs and office_workers"*, affected: `archetype:office_worker,entrepreneur`.
  - Day 4, 09:00–18:00, all outdoor locations, "monsoon", *"Heavy rain. Movement to
    outdoor locations is unappealing. Most people are staying inside."*, affected: `"all"`.
  - Day 5, 19:00, dhaba, "festival_prep", *"Locals are gathering at dhaba ahead of a
    small festival. Crowded, lively."*, affected: `"all"`.
- In `gather_context`, if an active scheduled event matches the agent (by archetype or
  "all"), inject a `=== TODAY ===` section above the schedule guidance.
- For monsoon-type events, also add a soft mechanical effect: `move_to` outdoor
  locations costs +1 mood (reluctance) for the duration.
- Surface upcoming events in the viewer's spotlight strip (Story 8.5) when within
  2 game hours.

**Done when:** Day 3's meetup pulls at least 3 office_worker/entrepreneur agents to
cyber_hub at 13:00 organically. Day 4's monsoon visibly reduces outdoor location
visits compared to baseline. Diary entries reference the events ("had to skip my
walk because of the rain").

---

## Epic 10: Make It a Show, Not a Simulator

This epic addresses the "spectator boredom" problem identified after Epic 8 shipped:
even with characters talking, writing diaries, and emergent behavior, watching the
web viewer is dull. The root cause is *format* — the current viewer is built like a
debug UI for someone who already understands the simulation. To entertain a stranger
who tunes in for 90 seconds, the experience has to do three jobs the current viewer
does not: **tell them where to look**, **tell them why it matters**, **skip the
boring parts**.

This epic turns the simulation viewer into a show. Stories 10.1–10.5 are the core
moves. 10.6–10.10 are cheap dressing that punches above its weight. Story 10.11
folds in the Epic 9 visual indicators (₹! financial-stress badge, scheduled-event
surfacing) that were deferred during Epic 9.

Build 10.1 (Director Mode) and 10.2 (Narrator) first — they're the highest-impact
moves and everything else layers on top. 10.5 (auto-pacing) should land early too
because dead-air is the single biggest reason viewers drop. The rest can be
parallelised.

### How to edit `viewer.html`

`viewer.html` is a **single self-contained HTML file** with three regions:

| Lines | Contents |
|------|----------|
| 1–168 | HTML shell + JS bootloader that decodes the bundle at runtime |
| 171 | `__bundler/manifest` — JSON dict of UUID → `{data: base64, mime, compressed}`. Holds **dependencies only**: fonts, React, ReactDOM, Babel-standalone, agent portraits. **You almost never touch this.** |
| 179 | `__bundler/template` — JSON-escaped string of the actual HTML+CSS+JS. **This is where the UI code lives.** |

To modify the UI, edit the JSON-escaped string on line 179: `json.loads()` it, change
the markup/script, then `json.dumps()` it back and replace line 179. Asset references
in the template use UUIDs (e.g., `src="def6a65e-..."`) which the bootloader rewrites
to `blob:` URLs at runtime — leave those UUIDs alone.

There is no build toolchain in the repo. No npm, no bundler. Just decode → edit →
re-encode. A 20-line Python helper is sufficient. Reusable helper scripts for
viewer edits should live in `scripts/viewer_edit.py` (not yet created — first
Epic 10 implementer should add it).

---

---

### Story 10.1 — Cinematic Director Mode (Auto-Protagonist Camera)
**As a spectator**, I want the camera to follow whoever is most interesting *right
now* so I always know where to look — instead of staring at 10 dots with equal
weight.

**Tasks:**
- In `viewer.html`, add a `directorMode` boolean (default `true`) and a toggle
  button in the HUD (`🎬 Director` ↔ `🗺️ Overview`).
- When director mode is on, the canvas zooms into a smaller bounding box around
  the current "protagonist" agent. Other agents and locations still render but at
  reduced opacity (~40%).
- Compute `protagonist_score` per agent each poll cycle as a weighted sum:
  - `+10` if part of an active conversation (any other agent at same location with
    talk-tagged `last_action`)
  - `+8` if a confirmed `shared_plan` (Story 9.5) is starting in <30 game minutes
  - `+7` if mood < 25 or > 80 (emotional extreme)
  - `+6` if `financial_stress = true` (Story 9.4)
  - `+5` if hunger > 80 or energy < 20 (crisis halo from Story 8.2)
  - `+4` if just received a `refuse` or `disagree` event (Story 9.3) within last
    20 game minutes
  - `+2` per event involving this agent in the last 30 game minutes (recency boost)
- Pick the highest-scoring agent as protagonist. Hold focus for **at least** 20
  real seconds before allowing a cut, to avoid jitter. Auto-cut to the new top
  scorer after that, with a smooth 600ms ease-in pan.
- Show a small "📺 Following: {Name}" pill in the top-left corner during director
  mode, with portrait thumbnail.
- Clicking any agent forces them as protagonist for 60 real seconds (manual
  override), then auto-resumes scoring.

**Done when:** Director mode keeps the viewer on a meaningful agent at all times.
Within 5 minutes of watching, the camera has cut to at least 3 different agents
based on actual events. No focus-thrash (no cuts faster than every 20 seconds
unless manually overridden).

---

### Story 10.2 — LLM-Generated Live Narrator
**As a spectator**, I want voiceover-style commentary on what's happening so the
sim feels like a documentary, not surveillance footage.

**Tasks:**
- Add `engine/narrator.py` with `generate_narration(world_state, recent_events,
  protagonist_name) -> str` returning 1–2 sentences.
- Prompt template: *"You are a calm, observant narrator describing a slice-of-life
  show set in modern Gurgaon. In 1–2 sentences (max 30 words total), describe what
  {protagonist} is doing right now and the emotional subtext. Use present tense.
  Be specific. Do not summarize, do not editorialize, do not name internal stats
  like 'mood'. Examples: 'Arjun has been pacing near Cyber Hub for ten minutes. He's
  checking his phone. Kavya hasn't replied.' / 'Priya finally took a break — she's
  at the coffee shop alone, watching the rain.'"*
- Inputs to the prompt: protagonist soul (one-line summary), protagonist's
  `last_action`, location, `recent_events` involving this agent (last 5), current
  mood/hunger/energy as qualitative descriptors only ("tired", "hungry", "low",
  "lifted").
- Trigger one narration call every 30 real seconds, OR immediately on a director
  cut (Story 10.1), whichever comes first. Cache by `(protagonist, last_action,
  location)` tuple to avoid redundant calls.
- Add `GET /api/narration` endpoint in `server.py` returning the latest narration
  string + timestamp.
- In `viewer.html`, add a 36px tall narration bar at the bottom of the canvas
  area. New narrations slide in from the right and out to the left. Optional
  small "🔊" button to enable browser TTS (`window.speechSynthesis`) — off by
  default to avoid surprising the viewer.

**Done when:** A 5-minute watch produces ~10 distinct narration lines, each
accurately reflecting what the protagonist is doing. Narration changes within 5
seconds of a director cut. TTS works when enabled. No more than ~12 LLM calls per
5 minutes (cost ceiling).

---

### Story 10.3 — Scene Staging for Dramatic Moments
**As a spectator**, I want dramatic moments to *interrupt* the normal view with a
cinematic cut-in so I don't miss them.

**Tasks:**
- Define "moment triggers" detected each poll cycle:
  - Two agents with confirmed `shared_plan` (Story 9.5) both arriving at the
    location → "the meet-up"
  - A `refuse` or `disagree` event landing → "the rejection"
  - First `talk_to` between two agents who haven't spoken in ≥1 game day → "the
    reconnection"
  - Mood crash (Δmood ≤ -15 in one tick) → "the moment it hit"
  - Plan failure (one shows, one doesn't, per Story 9.5) → "the no-show"
- On trigger, render a Scene Card overlay (centered modal, dimmed background):
  - Both agents' portrait thumbnails facing each other (or one alone for mood crash)
  - Caption strip: a short phrase from `engine/narrator.py` framed as a scene
    heading (e.g., *"Cyber Hub — afternoon. Arjun arrives. Kavya is already
    there."*)
  - The actual `talk_to` message text typed character-by-character (~25 chars/sec)
    in chat-bubble style
  - Soft musical sting on open (Story 10.8 dependency — graceful no-op if absent)
- Hold for 8 real seconds (longer if dialogue is still typing), then ease-out and
  return to director mode.
- Maximum one scene card per 30 real seconds — queue triggers if multiple fire close
  together. Pick the highest-scoring trigger when queueing (use the same priority
  order listed above).
- Add a `🎬 Replay last scene` button in the HUD that re-shows the most recent
  scene card.

**Done when:** Within a 10-minute watch, at least 2 scene cards trigger on real
moments (no test fixtures). Dialogue types out legibly, the scene returns cleanly
to director mode, and no two scene cards fire within 30 seconds of each other.

---

### Story 10.4 — Plot Threads Tracker (Sidebar)
**As a spectator**, I want a persistent sidebar of active storylines so I always
have something to root for or against.

**Tasks:**
- Add `engine/plots.py` with `detect_plot_threads(world_state) -> list[PlotThread]`,
  where a thread is `{id, title, participants, status_text, progress: 0-1, last_updated}`.
- Auto-detect threads from existing state (no LLM needed):
  - **Pending shared plans** (Story 9.5): *"Will {A} and {B} actually meet at
    {location}?"* — progress = (game_minutes_remaining / 240) inverted
  - **Refused/declined plans**: *"Awkwardness between {A} and {B}"* — surfaces for
    24 game hours after a `refuse` or `decline_plan` event
  - **Financial stress** (Story 9.4): *"{Name}'s rent crisis"* — progress = days
    behind / 4
  - **Mood spirals**: any agent with mood < 30 for ≥ 6 game hours → *"{Name} is
    sinking"*
  - **Conversation streaks**: 5+ messages between same pair in last 3 game hours →
    *"{A} and {B} can't stop messaging"*
  - **Active disagreements** (Story 9.3): unresolved `disagree` events → *"{A}
    and {B} are arguing about {topic}"*
- Add `GET /api/plot_threads` endpoint returning the current list.
- In `viewer.html`, add a 280px-wide right sidebar showing up to 5 threads sorted
  by `last_updated` desc:
  - Each thread: title (1 line, bold), participant portrait thumbnails, progress
    bar (or status badge for non-progressable threads), a "tap to focus camera"
    affordance that forces the participants as protagonist (Story 10.1 override).
- Threads auto-expire 24 game hours after `last_updated` if no new events.
- Closing a thread (X button) hides it for the rest of the session.

**Done when:** After 5 game days of simulation, the sidebar consistently shows 3–5
threads. Tapping a thread cuts the camera to its participants. Threads update or
expire correctly as state changes — no stale entries linger past 24 game hours.

---

### Story 10.5 — Drama-Driven Auto-Pacing
**As a spectator**, I want the sim to fast-forward boring stretches automatically
so I'm never staring at nothing happening.

**Tasks:**
- Extend the existing night auto-speed logic in `engine/world.py`'s
  `SimulationLoop._tick` with a more general "drama detector".
- Each tick, compute `drama_score`:
  - `+5` per `talk_to` event in the last 4 ticks
  - `+8` per `refuse`/`disagree` event in the last 4 ticks (Story 9.3)
  - `+10` per active scene card or unresolved shared plan in <30 game minutes
  - `+3` per agent with mood < 30 or > 75
  - `+2` per agent in motion (between locations)
- Speed mapping:
  - `drama_score >= 15`: speed 1x (live)
  - `drama_score 8–14`: speed 1x (default, no change)
  - `drama_score 3–7`: speed 2x with a "⏩ quiet stretch" pill in the HUD
  - `drama_score 0–2` for ≥ 60 real seconds: speed 4x with "⏩⏩ skipping ahead"
    pill, soft visual desaturation
- The existing night auto-speed (Story 5.3) still applies and overrides drama-based
  speed when ≥7 agents are sleeping.
- Any scene card trigger (Story 10.3) immediately drops speed back to 1x for the
  duration of the card.
- Manual speed override (Story 7.3) wins over auto-pacing — show a "🔒 Speed locked"
  indicator while the manual override is active.

**Done when:** During a 10-minute watch with no active conflict, the sim spends
≥ 30% of the time at 2x or 4x. The moment a `talk_to` event between two agents
fires, speed is back at 1x within 1 tick. Manual speed lock fully disables
auto-pacing and is reflected in the HUD.

---

### Story 10.6 — Portraits Everywhere
**As a spectator**, I want to see the agents' faces in every UI element so the
characters feel like people, not colored dots.

**Tasks:**
- Audit every place agent identity is rendered in `viewer.html` and replace text
  initials with the portrait avatar (already served by `GET /api/agent/{name}/avatar`):
  - Event feed (Story 8.3): 18px circular avatar at the start of each event line
  - Spotlight strip (Story 8.5): inline avatars next to named agents
  - Speech bubbles (Story 8.4): tiny avatar on the bubble pointer side
  - Narration bar (Story 10.2): protagonist's avatar at the left edge
  - Scene cards (Story 10.3): full-size portraits (already specified)
  - Plot thread sidebar (Story 10.4): participant avatars (already specified)
  - Day-change recap overlay (Story 8.6): "most active agent" shown with portrait
- Cache avatar fetches client-side in a `Map<name, HTMLImageElement>` populated
  on first poll. Fall back to colored circle + initials if image fails to load.
- Avatars should match agent color via a 2px ring border so identity is still
  legible at small sizes.

**Done when:** No piece of UI in the viewer references an agent purely by name
or initials when their portrait could be shown instead. Avatars load once and
are reused across all UI elements without flicker.

---

### Story 10.7 — Mood Emoji Floaters
**As a spectator**, I want big visual cues when agents have emotional shifts so I
catch the drama without reading text.

**Tasks:**
- In `viewer.html`, track per-agent `previousMood` across poll cycles. On each
  poll, compute `Δmood = currentMood - previousMood`.
- Emit a floating emoji from the agent's sprite when:
  - `Δmood >= +10` → 😍 (mood spike up)
  - `Δmood >= +5` → 🙂
  - `Δmood <= -10` → 😞 (mood crash)
  - `Δmood <= -5` → 😕
  - Just received a `refuse` event → 😶
  - Just received a `disagree` event → 😤
  - Hunger crossed 80 going up → 🍛
  - Energy dropped below 20 → 🥱
- Render as a 24px emoji that floats up 60px over 1.5s with ease-out, fading from
  opacity 1 → 0. Stack with 6px horizontal offset if multiple fire on same agent
  in same poll.
- Limit one floater per agent per poll to avoid spam.

**Done when:** When an agent's mood drops sharply, a 😞 visibly floats up from
their sprite. When they receive a refusal, a 😶 floater appears. Across a
10-minute watch, at least 8 floaters appear across all agents, accurately
reflecting state changes.

---

### Story 10.8 — Sound Design
**As a spectator**, I want ambient sound and audio cues for events so the show
has texture and I notice things even when not staring at the screen.

**Tasks:**
- Add `static/audio/` directory with royalty-free assets:
  - `ambient_city.mp3` — looping low-volume city background (auto, traffic, faint
    voices). Plays continuously when sim is running.
  - `ui_event.mp3` — short tick on new event_feed entry
  - `ui_message.mp3` — soft chime on new `talk_to` event
  - `sting_drama.mp3` — 1.5s musical sting for scene card open (Story 10.3)
  - `sting_refusal.mp3` — slightly dissonant sting for `refuse`/`disagree` events
  - `chime_dayboundary.mp3` — bell on day-change overlay (Story 8.6)
- Add a 🔊 audio toggle button in the HUD (default: **off** — never auto-play
  audio without explicit consent, browsers will block it anyway).
- All audio at 30% default volume, with a slider in a settings popover.
- Add a per-channel mute (ambient / UI / stings) so viewers can keep ambient and
  mute stings, or vice versa.
- Use the Web Audio API directly — no library dependency.

**Done when:** Toggling audio on plays the city ambient loop. Each event type
triggers its specific cue (verifiable by inspecting the audio queue). All cues
respect master volume and per-channel mutes. Audio survives a poll-cycle refresh
without re-triggering existing loops.

---

### Story 10.9 — End-of-Day Highlight Reel + Cliffhanger
**As a spectator**, I want a 20-second montage at the end of each game day with a
cliffhanger for tomorrow so the experience has shape.

**Tasks:**
- Extend the day-change overlay (Story 8.6) into a full highlight reel sequence.
- At day-boundary, compute `top_moments[5]` from the day's events using the same
  scoring as Story 10.1's protagonist score, but applied retrospectively over the
  full day. Each moment captures: timestamp, location, participants, event text.
- Render the reel as a 20-second sequence:
  - Title card: *"Day {N} — Recap"* (2s, large fade)
  - For each of the top 5 moments: 3.5s card showing participant portraits, a
    short caption derived from the event (LLM-generated one-liner OR the raw
    event text reformatted via Story 8.3's `narrativise()`), location name
  - Final cliffhanger card: 1 LLM call generates *"Tomorrow on Gurgaon: {2 short
    teasers}"* based on unresolved plot threads (Story 10.4) and pending shared
    plans (Story 9.5)
- Music: optional `sting_dayboundary.mp3` extended loop while reel plays, fade
  out on close.
- Skip button (Esc or click) — but the reel auto-dismisses after the cliffhanger
  card holds for 4 seconds.
- Append the cliffhanger text to `world/daily_log_day_{N}.txt` for archival.

**Done when:** At Day 1 → Day 2 transition, a 20-second reel plays showing 5
moments with portraits and captions, followed by a coherent cliffhanger card
that names actual unresolved threads. Skipping works. The cliffhanger persists
in the daily log.

---

### Story 10.10 — Daily Gossip Headlines
**As a spectator**, I want playful tabloid-style headlines about the day's events
so the show has comic relief and a distinct voice.

**Tasks:**
- Add `engine/headlines.py` with `generate_headlines(day_events, agent_souls) ->
  list[str]` returning 2–3 short headline strings.
- Triggered once per game day at 18:00 (early evening). One LLM call per day.
- Prompt: *"You write the gossip column for a fictional Gurgaon neighborhood
  newsletter. Given today's notable events, write 2–3 cheeky tabloid-style
  headlines (max 12 words each). Be playful, slightly dramatic, never mean.
  Examples: 'Local Founder Spotted Leaving Cyber Hub Alone — Again' / 'Drama at
  the Dhaba: Two Friends, One Awkward Silence' / 'Mystery Solved: Why Vikram
  Skipped His Morning Walk'. Avoid using any agent's full name more than once
  across the set."*
- Store headlines in `world/state.json` under `daily_headlines: {day_N: [...]}`.
- Add `GET /api/headlines/today` endpoint.
- In `viewer.html`, add a horizontal scrolling ticker (24px tall, top of viewport,
  beneath the overview bar) that cycles through today's headlines with a 6-second
  hold per headline and 400ms slide transition.
- Once a new day starts (and the reel finishes, Story 10.9), the ticker swaps to
  the new day's headlines.

**Done when:** By 18:00 on Day 1, the ticker shows 2–3 distinct headlines that
plausibly reference actual events from the day. Headlines have personality (not
dry summaries). Ticker scrolls smoothly without jitter. New day produces new
headlines without restart.

---

### Story 10.11 — Epic 9 Visual Indicators (Deferred Items)
**As a spectator**, I want the Epic 9 state changes (financial stress, scheduled
events) to be visible on the map, since they currently affect agent *behavior*
without leaving any visual trace.

These items were drafted as part of Stories 9.4 and 9.8 but deferred during Epic 9
because the implementers misjudged `viewer.html` as un-editable. With the file
structure now documented in this epic's preamble, they're cheap to add. Group them
into one PR alongside the first Epic 10 viewer change (likely 10.1 Director Mode)
to amortise the decode/re-encode round-trip.

**Tasks:**
- **₹! financial-stress badge (from Story 9.4):** for each agent sprite in the map
  render loop, if `agent.financial_stress === true`, draw a small `₹!` glyph on a
  semi-transparent red pill (12px, 9px Inter font) immediately to the right of the
  sprite circle, just above any existing crisis halo from Story 8.2. The data
  already flows through `/api/state`. No backend change needed.
- **Scheduled-event surfacing in the spotlight strip (from Story 9.8):** extend the
  existing spotlight strip (Story 8.5) priority ladder with a new top-priority case:
  *"if a scheduled event from `world/scheduled_events.json` is active or starting
  within 2 game hours and matches `affected_agents` for any visible agent → show:
  '🌧️ Monsoon: most agents staying inside' / '☕ Startup meetup at Cyber Hub at
  1pm — Arjun, Priya, Anita might show up' / '🎉 Festival prep at Pappu Dhaba this
  evening'."*
  - Add `GET /api/scheduled_events/active?day=X` to `server.py` — proxies
    `WorldState._scheduled_events` filtered by current day. Returns
    `{events: [...]}` with the same schema as the file.
  - In the viewer template, the spotlight strip JS calls this endpoint each poll
    cycle (or on day change) and uses the highest-priority active event when
    available.
- **Memory-update event tag (from Story 9.7):** the `memory_updated` event is
  already added to the world event log by `consolidate_memory()`. In the
  narrativised event feed (Story 8.3), add a 🧠 prefix and the line *"{Name}
  reflected on the past few days."* No new endpoint needed.

**Done when:** A financially stressed agent shows a ₹! badge next to their sprite.
The spotlight strip shows the active scheduled event when one is in effect or
imminent. The event feed shows a 🧠 line whenever an agent consolidates memory.
All three changes are made in one decode/re-encode pass on `viewer.html`.

---

## Summary — Story Count by Phase

| Phase | Stories | Priority |
|-------|---------|---------|
| Epic 1: Foundation | 4 | Must have |
| Epic 2: LLM + Tools | 4 | Must have |
| Epic 3: Agent Engine | 3 | Must have |
| Epic 4: Arcade Rendering | 5 | Must have |
| Epic 5: Persistence | 3 | Must have |
| Epic 6: Web Viewer | 2 | Should have |
| Epic 7: Polish | 3 | Nice to have |
| Epic 8: Spectator Experience | 8 | Nice to have |
| Epic 9: Emergent Behavior & Story Depth | 8 | Should have |
| Epic 10: Make It a Show, Not a Simulator | 11 | Should have |
| **Total** | **51** | |

Build order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10. Never skip ahead.

Within Epic 9: build 9.1 first (unblocks all others by giving agents conversation memory),
then 9.2 (yesterday's reflection — needed for cross-day differentiation). 9.3, 9.4, 9.5,
9.6, 9.7, 9.8 can then be built in any order or in parallel.

Within Epic 10: build 10.1 (Director Mode), 10.2 (Narrator), and 10.5 (auto-pacing) first
— they are the highest-impact moves and unlock the rest. 10.3 (scene staging) depends on
10.1. 10.4, 10.6, 10.7, 10.8, 10.9, 10.10, 10.11 can then be parallelised in any order.
Land 10.11 alongside the first viewer-touching story (likely 10.1) to amortise the
decode/re-encode round-trip — don't make it a standalone PR.
