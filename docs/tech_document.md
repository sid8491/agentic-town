# Gurgaon Town Life — Technical Document

## 1. Project Overview

A multi-agent autonomous simulation set in modern Gurgaon, India. Ten AI-powered characters live, work, and interact in a persistent virtual town. Each agent has a unique personality, daily needs, and long-term goals. They make decisions autonomously using a local LLM (Ollama) or cloud LLM (Gemini). The simulation runs continuously — observers watch via an Arcade desktop window or a browser-based web viewer.

---

## 2. Tech Stack

| Layer | Technology | Version | Reason |
|-------|-----------|---------|--------|
| Language | Python | 3.12 | Stable, fast asyncio, broad library support |
| Agent framework | LangGraph | latest | Graph-based agent state machines, async-native |
| LLM abstraction | litellm | latest | Unified API for Ollama + Gemini |
| LLM (primary) | Ollama | local | Free, fast, GPU-accelerated (qwen3:27b) |
| LLM (secondary) | Google Gemini | API | Cloud fallback, richer reasoning |
| Desktop renderer | Arcade | 3.x | Python-native, OpenGL, sprites + tile maps |
| Web server | FastAPI | latest | Async, WebSocket support, serves web viewer |
| Web viewer | HTML5 Canvas | — | Simple, zero-framework JS (I write, you ignore) |
| Persistence | JSON files | — | Human-readable, easy to inspect/edit |
| Environment | python-dotenv | latest | API key management |

**Python path:** `C:\Python312\python.exe`
**Virtual env:** `D:\work\develop\agentic_simulation\.venv`

---

## 3. Project Structure

```
agentic_simulation/
├── .venv/                        # Python 3.12 virtual environment
├── .env                          # API keys (never commit)
├── .env.example                  # Template for keys
├── requirements.txt
│
├── agents/                       # One folder per agent — their entire mind
│   ├── arjun/
│   │   ├── soul.md               # Fixed personality (read-only at runtime)
│   │   ├── memory.md             # Long-term beliefs and relationships
│   │   ├── diary.md              # Daily journal (append-only)
│   │   └── goals.md              # Current priorities (rewritten by agent)
│   ├── priya/
│   ├── rahul/
│   └── ... (10 agents total)
│
├── world/
│   ├── map.json                  # Locations, connections, properties
│   └── state.json                # Live world state (positions, inventories, time)
│
├── engine/
│   ├── __init__.py
│   ├── world.py                  # World state management, tick loop
│   ├── agent.py                  # LangGraph agent definition, tool execution
│   ├── tools.py                  # All tool implementations
│   ├── llm.py                    # LLM abstraction (Ollama / Gemini toggle)
│   └── needs.py                  # Hunger, energy, mood decay logic
│
├── server.py                     # FastAPI app (web viewer + WebSocket)
├── viewer.html                   # Browser viewer (standalone, no framework)
├── main.py                       # Entry point — starts Arcade + engine + server
└── docs/
    ├── tech_document.md
    └── tech_stories.md
```

---

## 4. The World — Gurgaon Map

### Locations

| ID | Name | Type | What happens here |
|----|------|------|-------------------|
| `apartment` | Sector 56 Apartments | Home | Sleep, rest, privacy |
| `cyber_hub` | Cyber Hub | Social | Eat, drink, socialize, gossip |
| `cyber_city` | DLF Cyber City | Work | Earn money, stress builds |
| `sector29` | Sector 29 Market | Shopping | Buy essentials, street food |
| `dhaba` | Sharma Ji ka Dhaba | Food | Cheap meals, local gossip |
| `metro` | MG Road Metro | Transit | Pass through, chance encounters |
| `park` | Leisure Valley Park | Leisure | Relax, jog, reduce stress |
| `supermarket` | Big Bazaar | Shopping | Buy groceries, household items |

### Map Connections (walkable paths)
```
apartment ↔ metro ↔ cyber_city
apartment ↔ sector29 ↔ dhaba
sector29 ↔ supermarket
metro ↔ cyber_hub ↔ park
cyber_hub ↔ sector29
```

### Time System
- 1 real second = 5 game minutes
- Each tick (3 real seconds) = 15 game minutes
- Full game day (24 hours) = 1440 game min ÷ 5 = 288 real seconds ≈ 5 minutes
- Tick interval: ~3 real seconds (agent decisions run async in parallel)

### Per-Agent Schedules

Each agent has an **archetype** that drives time-aware behaviour without LLM cost:

| Archetype | Agents | Sleep window | Work hours |
|-----------|--------|--------------|------------|
| office_worker | arjun, priya, neha | 11pm – 6am | 9am – 6pm |
| vendor | suresh | 10pm – 5am | 8am – 8pm |
| retired | vikram | 9pm – 5am | — |
| homemaker | deepa | 10pm – 6am | — |
| entrepreneur | anita | 12am – 6am | 10am – 10pm |
| student | kavya | 1am – 7am | — |
| night_owl | rahul, rohan | 3am – 9am | 6pm – 3am |

Each tick, `gather_context` builds a `schedule_guidance` string (sleep / morning routine /
work / wind-down / empty) based on `sim_time` and the agent's archetype, and injects it
as a `=== SCHEDULE ===` section in the LLM prompt. The agent will deviate from the
guidance only if needs are critical (hunger > 85 or energy < 10).

### Night Auto-Speed

After every tick, `SimulationLoop._tick` counts agents whose `last_action` contains
"sleep". If ≥7 agents are sleeping the simulation speed auto-bumps to 4x; once <5
remain asleep it drops back to 1x. Effective dead-quiet window is roughly 3am – 5am.

---

## 5. The Agents

### The 10 Characters

| Agent | Persona | Starting Location | Core Trait |
|-------|---------|-------------------|------------|
| **Arjun** | Software engineer, 28, startup | apartment | Ambitious but anxious |
| **Priya** | Product manager, 32, MNC | cyber_city | Organized networker |
| **Rahul** | Delivery boy, 22, Zomato | metro | Street-smart, observant |
| **Kavya** | Freelance designer, 26 | apartment | Creative, works odd hours |
| **Suresh** | Cab driver, 45 | sector29 | Wise, knows everyone |
| **Neha** | HR professional, 30 | cyber_hub | Cheerful, gossip queen |
| **Vikram** | Retired colonel, 62 | park | Disciplined, opinionated |
| **Deepa** | Homemaker, 38 | apartment | Resourceful, community anchor |
| **Rohan** | MDI student, 24 | dhaba | Idealistic, always broke |
| **Anita** | Boutique owner, 41 | sector29 | Entrepreneurial, proud |

### Agent File Formats

**`soul.md`** — Written once by the developer. Never changed at runtime.
```markdown
# Arjun Sharma

Age: 28. Backend engineer at a Series-A startup in Cyber City.
Grew up in Jaipur, moved to Gurgaon two years ago. Still adjusting.

Works too hard. Skips lunch often. Feels guilty when he's not productive.
Secretly afraid his startup will fail. Puts up a confident front.
Values loyalty. Generous with close friends, guarded with strangers.
Doesn't trust people who talk too much about money.

Voice: Technical, slightly formal. Uses startup jargon without realizing.
Occasionally slips into Hindi when emotional.
```

**`memory.md`** — Agent reads and rewrites this.
```markdown
# Relationships
- Priya: We met at Cyber Hub last week. Seems sharp. Not sure I trust her yet.
- Rohan: Reminds me of myself at that age. Bought him chai yesterday.

# Knowledge  
- Rahul delivers faster if you tip upfront (learned Day 2)
- Sharma Ji's dhaba has the best rajma in the sector

# Recent Events
- Day 3: Got into argument with Neha about office politics
```

**`diary.md`** — Agent appends one entry per game day.
```markdown
# Day 4 — Tuesday, 9:30pm
Terrible day. The deployment failed at 3pm and I had to fix it alone.
Went to Cyber Hub afterward, ran into Neha. She was her usual self — all smiles,
but I could tell she was fishing for information about our funding round.
Told her nothing. Had one beer, came home. Too tired to eat properly.
Need to buy groceries tomorrow or I'll be eating Maggi again.
Energy is at rock bottom. Sleep.
```

**`goals.md`** — Agent reads and updates this each morning.
```markdown
# Current Goals
1. Get the API deployment stable before Thursday standup
2. Save 500 coins this week (need buffer for next month's rent)
3. Figure out if Priya is worth trusting — she knows a lot of people
4. Actually eat proper meals this week
```

---

## 6. Agent Decision Loop

Each agent runs one LangGraph graph per tick:

```
START
  │
  ▼
read_file("soul.md")         → who am I?
  │
  ▼
check_needs()                → hunger %, energy %, mood
  │
  ▼
look_around()                → who/what is nearby, time of day
  │
  ▼
grep_memory(relevant_topic)  → what do I know that matters right now?
  │
  ▼
read_file("goals.md")        → what do I want?
  │
  ▼
[LLM DECIDES]                → picks ONE world action tool
  │
  ├── move_to(location)
  ├── talk_to(agent, message)
  ├── buy(item) / sell(item)
  ├── eat(item) / sleep()
  ├── work() / look_around()
  └── give_item(agent, item)
  │
  ▼
execute tool → world state updates
  │
  ▼
append_diary(reflection)     → agent journals about what happened
  │
  ▼
[if significant event]
edit_file("memory.md", ...)  → update beliefs
edit_file("goals.md", ...)   → adjust priorities
  │
  ▼
END (wait for next tick)
```

---

## 7. Agent Tools

### File Tools
| Tool | Description |
|------|-------------|
| `read_file(filename)` | Read soul.md / memory.md / diary.md / goals.md |
| `edit_file(filename, content)` | Overwrite memory.md or goals.md |
| `append_diary(entry)` | Add dated entry to diary.md |
| `grep_memory(query)` | Search memory.md for matching lines |

### World Tools
| Tool | Description |
|------|-------------|
| `move_to(location)` | Walk to a location (takes 1 tick if adjacent) |
| `look_around()` | See nearby agents, items, time of day |
| `check_needs()` | Get hunger %, energy %, mood score |
| `check_inventory()` | List coins and items held |
| `talk_to(agent, message)` | Deliver message; recipient reads it next tick |
| `ask_about(agent, topic)` | Request gossip/info from nearby agent |
| `give_item(agent, item, qty)` | Transfer item to another agent |
| `buy(item, qty)` | Purchase at market/supermarket |
| `sell(item, qty, price)` | Sell at market |
| `eat(item)` | Consume food; restores hunger |
| `sleep()` | Restore energy (home only, night only) |
| `work()` | Earn coins at workplace |

---

## 8. Needs System

Each agent has three decaying values (0–100):

| Need | Decay Rate | Effect when critical |
|------|-----------|---------------------|
| `hunger` | +8% per game hour | >80%: agent prioritizes food above all goals |
| `energy` | -5% per game hour | <20%: agent tries to go home and sleep |
| `mood` | varies by events | <30%: agent seeks social contact or solitude (per soul.md) |

Mood modifiers:
- +10: successful social interaction
- +15: received gift / help
- -10: argument / ignored
- -5: skipped meal
- +5: reached a goal

---

## 9. LLM Integration

### Abstraction Layer (`engine/llm.py`)

```python
# Supports runtime switching between Ollama and Gemini
PRIMARY = "ollama"  # or "gemini" — toggled via UI or env var

MODELS = {
    "ollama": "ollama/qwen3:27b",    # local, free
    "gemini": "gemini/gemini-2.5-flash",  # cloud, fast + cheap
}
```

Uses `litellm` for unified API — same call signature regardless of provider.

### Prompt Structure (per agent tick)
```
[soul.md content]           ← cached, rarely changes
[memory summary]            ← key relationships + recent events  
[current state]             ← needs, location, nearby agents, time
[available tools]           ← JSON schema
[task]                      → "What do you do? Call exactly one tool."
```

### Token Budget (per tick, per agent)
| Section | Approx tokens |
|---------|--------------|
| soul.md | ~200 |
| memory | ~300 |
| current state | ~150 |
| tools schema | ~400 |
| **Total input** | **~1050** |
| Output (action) | ~100 |

10 agents × 1150 tokens × N ticks/day = manageable on Ollama (free).

---

## 10. Persistence

### What persists between runs
- `agents/*/soul.md` — permanent (never auto-changed)
- `agents/*/memory.md` — grows over time
- `agents/*/diary.md` — append-only log
- `agents/*/goals.md` — rewritten by agent each morning
- `world/state.json` — positions, inventories, sim time

### Reset
```bash
python main.py --reset        # wipes state.json + memory + diary + goals
                              # soul.md is preserved (personality stays)
```

`soul.md` is developer-authored and never mutated at runtime, so `--reset` already
yields a true factory-fresh sim. To replace souls themselves, use `git checkout agents/`.

---

## 11. Rendering — Arcade (Desktop)

### Window Layout
```
┌─────────────────────────────────────────┬──────────────┐
│                                         │  EVENT LOG   │
│           TOWN MAP (800×600)            │  Day 4 2:30pm│
│   [agents as sprites on tile grid]      │  ─────────── │
│   [name tags + thought bubbles]         │  Arjun→Dhaba │
│                                         │  Neha bought │
│                                         │  chai...     │
├─────────────────────────────────────────┴──────────────┤
│  ⏸ PAUSE  ◀ SLOW  ▶▶ FAST   LLM: [OLLAMA▼]  Day 4    │
└────────────────────────────────────────────────────────┘
```

### Interactions
- **Spacebar** — pause / resume
- **← →** — slow down / speed up time
- **Click agent** — open diary panel (see their last 3 journal entries)
- **L key** — toggle LLM between Ollama and Gemini

---

## 12. Web Viewer

FastAPI serves `viewer.html` at `http://localhost:8000`. The HTML file polls `/api/state` (JSON) every second and redraws the canvas. No framework. ~150 lines of JS total — written once, never touched.

Anyone on the local network can open `http://<your-ip>:8000` to watch live.

---

## 13. Development Phases

| Phase | What gets built | Goal |
|-------|----------------|------|
| **1 — Foundation** | Project setup, world map, agent files | Structure in place |
| **2 — LLM + Tools** | litellm abstraction, tool engine, single agent | One agent thinks |
| **3 — Engine** | Multi-agent async loop, needs decay | 10 agents run |
| **4 — Rendering** | Arcade map + sprites + HUD | Watchable |
| **5 — Persistence** | Save/load/reset | Survives restart |
| **6 — Web Viewer** | FastAPI + HTML canvas | Others can watch |
| **7 — Polish** | Diary panel, event log, LLM toggle | Feels complete |
