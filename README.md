# Gurgaon Town Life

An autonomous multi-agent simulation set in modern Gurgaon, India. Ten AI characters with distinct personalities live, work, and interact in a persistent virtual town — completely on their own. No player control. Just watch the drama unfold.

Each character is powered by a local LLM (Ollama) or Google Gemini. They read their own soul files, keep a private diary, form opinions about each other, and make decisions every few seconds based on hunger, energy, mood, and personal goals.

---

## Characters

| Agent | Who they are |
|-------|-------------|
| Arjun | Software engineer, 28 — startup, anxious, overworked |
| Priya | Product manager, 32 — MNC, organized, networker |
| Rahul | Delivery boy, 22 — Zomato, street-smart, observant |
| Kavya | Freelance designer, 26 — creative, works odd hours |
| Suresh | Cab driver, 45 — wise, knows everyone's secrets |
| Neha | HR professional, 30 — cheerful, gossip queen |
| Vikram | Retired colonel, 62 — disciplined, very opinionated |
| Deepa | Homemaker, 38 — resourceful, community anchor |
| Rohan | MDI student, 24 — idealistic, always broke |
| Anita | Boutique owner, 41 — entrepreneurial, proud |

---

## Setup

**Requirements:** Python 3.12, [Ollama](https://ollama.com) running locally with `gemma4:e4b` pulled.

```bash
# 1. Create virtual environment
C:/Python312/python.exe -m venv .venv
source .venv/Scripts/activate      # Windows bash
# or: .venv\Scripts\activate.bat   # Windows cmd

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — add GEMINI_API_KEY if you want Gemini as fallback
```

---

## Running

```bash
# Start the simulation (Arcade window + web viewer)
python main.py

# Start in fullscreen
python main.py --fullscreen

# Start at a specific in-game time (e.g. 8:00am)
python main.py --time 480

# Web viewer only (no Arcade window)
python server.py

# Reset world to Day 1 (keeps agent personalities)
python main.py --reset
# soul.md is never changed at runtime, so --reset already gives a true factory-fresh
# sim. To replace souls themselves, use `git checkout agents/`.
```

Web viewer: open `http://localhost:8000` in any browser. Works from other devices on the same network.

---

## Controls

| Key / Action | Effect |
|---|---|
| `Space` | Pause / resume |
| `←` / `→` | Slow down / speed up time |
| `F11` | Toggle fullscreen (Arcade window) |
| `L` | Toggle LLM between Ollama and Gemini |
| Click an agent | Open inspector — diary, needs, last action |
| `Escape` | Close inspector panel |
| Hover an avatar | Show enlarged portrait (web viewer) |

---

## Time

- 1 real second = 5 game minutes
- 1 tick (every 3 real seconds) = 15 game minutes
- Full game day = ~5 real minutes
- **Schedules:** every agent has an archetype (office worker, vendor, retired, student,
  night owl, homemaker, entrepreneur). Each tick the agent is given a short
  time-of-day directive — sleep, morning routine, work, or wind-down — and overrides
  it only when hunger or energy is critical.
- **Night auto-speed:** when ≥7 agents are sleeping the simulation auto-bumps to 4x
  so the deep-night window (~3am – 5am) compresses to about a real-time minute. It
  snaps back to 1x as agents wake.

---

## How Agents Think

Every tick, each agent:
1. Reads their `soul.md` (who am I?)
2. Checks their needs (hungry? tired? lonely?)
3. Looks around (who's nearby? what time is it?)
4. Searches their memory for relevant context
5. Asks the LLM: *what do I do?*
6. Executes one action (move, eat, talk, work, buy, sleep…)
7. Writes a diary entry reflecting on what happened
8. Updates memory and goals if something significant occurred

Each agent's "mind" is just files in their folder — you can read them any time:

```bash
# Watch Alice's diary update in real time
tail -f agents/arjun/diary.md

# Read Neha's current goals
cat agents/neha/goals.md
```

---

## Agent Files

Each agent lives in `agents/{name}/`:

| File | What it is | Who writes it |
|------|-----------|---------------|
| `soul.md` | Core personality — never changes | You (developer) |
| `memory.md` | Long-term beliefs, relationships | The agent (LLM) |
| `diary.md` | Daily journal — append only | The agent (LLM) |
| `goals.md` | Current priorities | The agent (LLM) |
| `../{name}.png` | Portrait image (optional) | You (developer) |

Portrait images live at `agents/{name}.png` (jpg/jpeg/webp also work). The web viewer serves them via `/api/agent/{name}/avatar` and displays them on the map, in the sidebar, the overview bar, and the inspector panel. Hover any avatar to see an enlarged version. Drop a file in and it appears immediately — no restart needed.

---

## LLM Configuration

Edit `.env` to configure:

```env
LLM_PRIMARY=ollama          # or: gemini
OLLAMA_BASE_URL=http://localhost:11434
GEMINI_API_KEY=your_key_here
```

Default model: `gemma4:e4b` (Ollama), `gemini-2.5-flash` (Gemini).
Switch at runtime by pressing `L` in the Arcade window or via `POST /api/llm/{provider}`.

---

## Running Tests

```bash
# Map + world state integrity
.venv/Scripts/python.exe tests/test_map.py
```

---

## Docs

- [`docs/tech_document.md`](docs/tech_document.md) — full technical specification
- [`docs/tech_stories.md`](docs/tech_stories.md) — build stories by phase
- [`CLAUDE.md`](CLAUDE.md) — guidance for AI coding assistants
