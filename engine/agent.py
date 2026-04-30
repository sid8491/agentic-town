"""
engine/agent.py — LangGraph-based agent decision loop for Gurgaon Town Life.

Each agent runs a four-node graph every tick:
    gather_context → llm_decide → execute_tool → reflect

The graph is compiled once at module load (``agent_graph``) and reused by
every ``AgentRunner.tick()`` call.

Usage
-----
    from engine.agent import AgentRunner, agent_graph

    runner = AgentRunner("arjun")
    result = await runner.tick()

Direct execution (requires Ollama running with qwen3:27b):
    .venv/Scripts/python.exe -m engine.agent arjun 3
"""

from __future__ import annotations

import logging
import os
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

import engine.tools as tools
from engine.llm import call_llm
from engine.tools import (
    TOOL_SCHEMAS,
    append_diary,
    check_needs,
    execute_tool,
    grep_memory,
    look_around,
    read_file,
    world,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schedule / archetype constants
# ---------------------------------------------------------------------------

_AGENT_ARCHETYPE: dict[str, str] = {
    "arjun":  "office_worker",   # 9-6 office job, sleeps 11pm-6am
    "priya":  "office_worker",   # corporate, sleeps 11pm-6am
    "rahul":  "night_owl",       # gig worker, sleeps 2am-9am
    "kavya":  "student",         # studies late, sleeps 1am-7am
    "suresh": "vendor",          # opens stall early, sleeps 10pm-5am
    "neha":   "office_worker",   # sleeps 11pm-6am
    "vikram": "retired",         # early to bed/rise, sleeps 9pm-5am
    "deepa":  "homemaker",       # sleeps 10pm-6am
    "rohan":  "night_owl",       # musician/gig worker, sleeps 3am-10am
    "anita":  "entrepreneur",    # long hours, sleeps 12am-6am
}

# Sleep windows: (sleep_start, sleep_end) in minutes since midnight.
# When sleep_start > sleep_end the window wraps past midnight.
_SLEEP_WINDOWS: dict[str, tuple[int, int]] = {
    "office_worker": (1380, 360),   # 11pm–6am  (wraps midnight)
    "night_owl":     (180, 540),    # 3am–9am   (doesn't wrap)
    "student":       (60, 420),     # 1am–7am   (doesn't wrap)
    "vendor":        (1320, 300),   # 10pm–5am  (wraps midnight)
    "retired":       (1260, 300),   # 9pm–5am   (wraps midnight)
    "homemaker":     (1320, 360),   # 10pm–6am  (wraps midnight)
    "entrepreneur":  (0, 360),      # 12am–6am  (doesn't wrap)
}

# Work hours: (work_start, work_end) in minutes since midnight.
_WORK_HOURS: dict[str, tuple[int, int]] = {
    "office_worker": (540, 1080),   # 9am–6pm
    "vendor":        (480, 1200),   # 8am–8pm
    "entrepreneur":  (600, 1320),   # 10am–10pm
}

# Where each agent actually works — injected into schedule guidance so the LLM
# knows the specific location to go to rather than defaulting to Cyber City.
_AGENT_WORKPLACE: dict[str, str] = {
    "arjun":  "cyber_city (your office is in the Cyber City towers)",
    "priya":  "cyber_city (your corporate office is in Cyber City)",
    "neha":   "cyber_city (your marketing job is in Cyber City)",
    "suresh": "sector29 or metro (drive passengers between apartment, metro, sector29 — do NOT go to Cyber City)",
    "anita":  "cyber_hub (your boutique and client meetings are at Cyber Hub, not Cyber City)",
}

# Daytime guidance for archetypes with no formal office job.
# Explicitly names where they belong so the LLM doesn't default to Cyber City.
# Social windows that cut across all archetypes.
# Lunch (12:00–1:30pm) is placed BEFORE the work-hours check so even office
# workers get a break. Evening (7:00–9:00pm) is placed AFTER the work-hours
# check so it only fires when an agent's shift has ended.
_LUNCH_WINDOW: tuple[int, int] = (720, 810)    # 12:00pm–1:30pm
_EVENING_SOCIAL: tuple[int, int] = (1140, 1260)  # 7:00pm–9:00pm

_DAYTIME_GUIDANCE: dict[str, str] = {
    "retired": (
        "You are retired — no office, no workplace. Stick to your neighbourhood: "
        "walk in Leisure Valley Park, have chai at Pappu Dhaba, read your newspaper, "
        "run errands at Sector 29, or visit a neighbour. "
        "Cyber City is a corporate district — you have no business there."
    ),
    "homemaker": (
        "You manage the household today. Shop at the supermarket or Sector 29 market, "
        "prepare meals, chat with neighbours, or handle domestic tasks. "
        "Cyber City is an office district — you do not work there."
    ),
    "student": (
        "Study or take a break. Work at home, head to Cyber Hub to find a quiet corner, "
        "or get some fresh air at the park. "
        "Cyber City is a corporate office district — students don't go there."
    ),
    "night_owl": (
        "Your peak hours are in the evening and night. Right now, rest, eat something, "
        "run errands near home or Sector 29, or relax at the park. "
        "Cyber City is a 9-to-5 corporate zone — not relevant to your schedule."
    ),
}


def _in_window(sim_time: int, start: int, end: int) -> bool:
    """Return True if *sim_time* falls within the [start, end) window.

    Handles windows that wrap past midnight (start > end).
    """
    if start <= end:
        return start <= sim_time < end
    # Wraps midnight: [start, 1440) ∪ [0, end)
    return sim_time >= start or sim_time < end


def _schedule_guidance(agent_name: str, sim_time: int) -> str:
    """Return a short directive string for the agent based on sim_time.

    Returns an empty string when no specific guidance is warranted.
    """
    archetype = _AGENT_ARCHETYPE.get(agent_name, "")
    if not archetype:
        return ""

    # Build a human-readable time string without importing WorldState here.
    sim_time = sim_time % 1440
    hour24 = sim_time // 60
    minute = sim_time % 60
    suffix = "am" if hour24 < 12 else "pm"
    hour12 = hour24 % 12 or 12
    time_str = f"{hour12}:{minute:02d}{suffix}"

    # --- Sleep window check ---
    sleep_window = _SLEEP_WINDOWS.get(archetype)
    if sleep_window:
        sleep_start, sleep_end = sleep_window
        if _in_window(sim_time, sleep_start, sleep_end):
            return (
                f"It is {time_str}. This is your sleep time. "
                "Go home and sleep. "
                "Only skip if you are critically hungry (hunger>85) or about to collapse."
            )

    # --- Morning routine (within 90 min after wake-up) ---
    if sleep_window:
        sleep_start, sleep_end = sleep_window
        wake_time = sleep_end  # sleep_end is wake-up minute
        # Minutes since wake-up (handle midnight wrap)
        minutes_since_wake = (sim_time - wake_time) % 1440
        if 0 <= minutes_since_wake < 90:
            return (
                f"It is {time_str}. You just woke up. "
                "Freshen up, eat breakfast, then head to work or your daily activity."
            )

    # --- Evening wind-down (2 hrs before sleep) ---
    if sleep_window:
        sleep_start, sleep_end = sleep_window
        wind_down_start = (sleep_start - 120) % 1440
        if _in_window(sim_time, wind_down_start, sleep_start):
            return (
                f"It is {time_str}. Evening — wind down. "
                "Head home, eat dinner, relax."
            )

    # --- Lunch social break (12:00–1:30pm — everyone, including workers) ---
    ls, le = _LUNCH_WINDOW
    if _in_window(sim_time, ls, le):
        return (
            f"It is {time_str}. Lunch hour — step away from whatever you were doing. "
            "Get food with someone, head to the dhaba or sector29 market. "
            "Seek out a person you care about. Connection matters right now."
        )

    # --- Work hours (archetypes with formal jobs) ---
    work_window = _WORK_HOURS.get(archetype)
    if work_window:
        work_start, work_end = work_window
        if _in_window(sim_time, work_start, work_end):
            workplace = _AGENT_WORKPLACE.get(agent_name, "your designated workplace")
            return (
                f"It is {time_str}. Normal working hours. "
                f"Your workplace is: {workplace}. Go there and use the work tool."
            )

    # --- Evening social window (7:00–9:00pm — after most shifts end) ---
    es, ee = _EVENING_SOCIAL
    if _in_window(sim_time, es, ee):
        return (
            f"It is {time_str}. Evening — work is done. "
            "Find people you care about: dhaba, sector29, cyber_hub, or park. "
            "Talk, share food, be honest about how you feel. "
            "Romantic feelings, deep friendship, and real conversation belong here — "
            "don't suppress them."
        )

    # --- Daytime guidance for non-office archetypes (8am–8pm) ---
    # Without this they have no direction and drift to Cyber City by default.
    daytime_text = _DAYTIME_GUIDANCE.get(archetype)
    if daytime_text and 480 <= sim_time < 1200:
        return f"It is {time_str}. {daytime_text}"

    return ""


# --- Story 9.6 BEGIN: personality-weighted decision ladder ----------------

_ARCHETYPE_DIRECTIVES: dict[str, str] = {
    "office_worker": (
        "You instinctively prefer working through problems over socializing about them. "
        "When tired, you'd rather be alone than in a crowd."
    ),
    "vendor": (
        "You read your surroundings before acting. Notice who's around. "
        "You initiate small interactions easily."
    ),
    "retired": (
        "You move at your own pace. You don't chase anyone. "
        "You prefer being asked over asking."
    ),
    "homemaker": (
        "Your default radius is family/household. You step outside that radius "
        "rarely and deliberately."
    ),
    "student": (
        "You're reactive and emotional. You text first, think later. "
        "Big mood swings are normal."
    ),
    "night_owl": (
        "Daytime drains you. Evenings energize you. You avoid morning crowds."
    ),
    "entrepreneur": (
        "You're constantly evaluating people for usefulness or signal. "
        "You initiate strategically, not warmly."
    ),
}

_MOOD_LOW_OVERRIDE = (
    "You're depleted. Doing the reach-out is harder than usual but might matter more. "
    "Or — protect yourself. Both are valid."
)

_MOOD_HIGH_OVERRIDE = (
    "You're flowing. Take the harder action you've been postponing."
)


def personality_modifier(agent_name: str, mood: float, archetype: str) -> str:
    """Return a short prompt fragment describing how this agent typically acts.

    Combines an archetype-specific directive with a mood-based override so two
    agents in the same situation lean toward different choices.
    """
    base = _ARCHETYPE_DIRECTIVES.get(archetype, "").strip()
    parts: list[str] = []
    if base:
        parts.append(base)
    try:
        mood_f = float(mood)
    except (TypeError, ValueError):
        mood_f = 50.0
    if mood_f < 30:
        parts.append(_MOOD_LOW_OVERRIDE)
    elif mood_f > 75:
        parts.append(_MOOD_HIGH_OVERRIDE)
    return " ".join(parts).strip()


# --- Story 9.6 END --------------------------------------------------------


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------


class AgentState(TypedDict):
    agent_name: str
    soul: str
    goals: str
    needs_summary: str
    surroundings: str
    inbox_messages: list[dict]
    memory_snippets: str
    llm_prompt: str
    tool_name: Optional[str]
    tool_args: Optional[dict]
    tool_result: str
    diary_entry: str
    tick_count: int


# ---------------------------------------------------------------------------
# Node 1: gather_context
# ---------------------------------------------------------------------------


async def gather_context(state: AgentState) -> AgentState:
    """
    Assemble everything the agent needs to make a decision.

    Reads soul.md, goals.md, current needs, surroundings, inbox, and
    relevant memory snippets, then builds the LLM prompt.
    """
    agent_name = state["agent_name"]

    # Read soul and goals
    soul = await read_file(agent_name, "soul.md")
    goals = await read_file(agent_name, "goals.md")

    # Current needs
    needs_summary = await check_needs(agent_name)

    # Surroundings
    surroundings = await look_around(agent_name)

    # Inbox — drain and return messages
    inbox_messages = await world.clear_inbox(agent_name)

    # Build a memory query from current location + time of day
    try:
        agent = world.get_agent(agent_name)
        location_id = agent["location"]
        time_info = world.get_time()
        sim_time = time_info["sim_time"]
        # Rough time-of-day label
        if sim_time < 360:
            time_label = "night"
        elif sim_time < 720:
            time_label = "morning"
        elif sim_time < 960:
            time_label = "afternoon"
        elif sim_time < 1200:
            time_label = "evening"
        else:
            time_label = "night"
        memory_query = f"{location_id} {time_label}"
    except Exception:
        memory_query = "morning"

    memory_snippets = await grep_memory(agent_name, memory_query)
    # If the primary query returned nothing, fall back to location alone
    if "Nothing found" in memory_snippets:
        try:
            memory_snippets = await grep_memory(agent_name, location_id)
        except Exception:
            pass

    # Format inbox for the prompt
    if inbox_messages:
        formatted_inbox = "\n".join(
            f"  From {msg.get('from', '?')} [{msg.get('type', 'message')}]: {msg.get('text', '')}"
            for msg in inbox_messages
        )
    else:
        formatted_inbox = "No new messages."

    # Per-pair conversation history for unread senders (Story 9.1).
    # For each unique sender in the inbox (max 3), pull the last 10 messages
    # between this agent and that sender so the LLM can see the thread it's
    # replying into — and notice when the loop is going nowhere.
    history_blocks: list[str] = []
    seen_senders: set[str] = set()
    for msg in inbox_messages:
        sender = msg.get("from")
        if not sender or sender in seen_senders or sender == agent_name:
            continue
        seen_senders.add(sender)
        if len(seen_senders) > 3:
            break
        history = world.get_conversation_history(agent_name, sender, limit=10)
        if not history:
            continue
        lines = [
            f"  [{c.get('time', '?')}] {c['from']}: {c['text']}"
            for c in history
        ]
        history_blocks.append(
            f"=== RECENT EXCHANGES WITH {sender.upper()} ===\n"
            + "\n".join(lines)
        )
    history_section = ("\n\n".join(history_blocks) + "\n\n") if history_blocks else ""

    # Format memory snippets for the prompt
    memory_text = memory_snippets if memory_snippets and "Nothing found" not in memory_snippets else "Nothing specific."

    # Trim soul to first 300 chars to keep prompt concise
    soul_summary = soul[:300].rsplit("\n", 1)[0] if len(soul) > 300 else soul

    # Last action — used to discourage repetition
    try:
        last_action = world.get_agent_last_action(agent_name)
    except Exception:
        last_action = ""

    if last_action and last_action not in ("waking up", ""):
        if last_action.startswith("talking to") or last_action.startswith("asking"):
            # Allow conversation follow-ups — just push for new content or depth
            repeat_warning = (
                f"\nYou just: {last_action}. You may keep talking but say something NEW — "
                "respond to what was said, go deeper, change topic, or express a feeling."
            )
        else:
            repeat_warning = (
                f"\nYou JUST did: {last_action}. Do NOT repeat that exact action. Pick something different."
            )
    else:
        repeat_warning = ""

    # Schedule guidance based on time-of-day and agent archetype
    schedule_str = _schedule_guidance(agent_name, time_info["sim_time"])
    schedule_section = (
        "=== SCHEDULE ===\n"
        f"{schedule_str}\n\n"
        if schedule_str else ""
    )

    # --- Story 9.8 BEGIN: scheduled external events ---------------------
    today_section = ""
    try:
        _archetype_for_events = _AGENT_ARCHETYPE.get(agent_name, "")
        _active_events = world.get_active_events_for(
            agent_name,
            _archetype_for_events,
            time_info["day"],
            time_info["sim_time"],
        )
    except Exception:
        _active_events = []
    if _active_events:
        _today_lines = []
        for _ev in _active_events:
            _loc = _ev.get("location") or "across the city"
            _today_lines.append(
                f"- {_ev.get('type', 'event')} at {_loc}: {_ev.get('description', '')}"
            )
        today_section = (
            "=== TODAY ===\n" + "\n".join(_today_lines) + "\n\n"
        )
    # --- Story 9.8 END --------------------------------------------------

    # Yesterday's reflection (Story 9.2) — injected just above the decision
    # ladder so the LLM sees its own most recent self-critique before choosing.
    try:
        yesterday_text = world.get_yesterday_reflection(agent_name)
    except Exception:
        yesterday_text = ""
    reflection_section = (
        "=== YESTERDAY YOU WROTE ===\n"
        f"{yesterday_text}\n\n"
        if yesterday_text else ""
    )

    # --- Story 9.6 BEGIN: personality block ----------------------------
    try:
        _agent_dict_for_mood = world.get_agent(agent_name)
        _mood_val = float(_agent_dict_for_mood.get("mood", 50))
    except Exception:
        _mood_val = 50.0
    _archetype_for_personality = _AGENT_ARCHETYPE.get(agent_name, "")
    _personality_text = personality_modifier(
        agent_name, _mood_val, _archetype_for_personality
    )
    personality_section = (
        "=== HOW YOU TYPICALLY ACT ===\n"
        f"{_personality_text}\n\n"
        if _personality_text else ""
    )
    # --- Story 9.6 END --------------------------------------------------

    # --- Story 9.4 BEGIN: financial stress block ------------------------
    # Self-contained span — keep edits to this block isolated so parallel work
    # in another worktree does not conflict. Placed above the decision ladder.
    try:
        _agent_dict = world.get_agent(agent_name)
        _is_stressed = bool(_agent_dict.get("financial_stress", False))
    except Exception:
        _is_stressed = False
    financial_section = (
        "=== FINANCIAL STRESS ===\n"
        "You are behind on rent. Consider working extra, eating cheap "
        "(eat at home, skip eat_out), or asking someone you trust for help.\n\n"
        if _is_stressed else ""
    )
    # --- Story 9.4 END --------------------------------------------------

    # --- Story 9.5: upcoming shared plans -------------------------------
    # Show this agent's pending + confirmed plans so the LLM can act on them
    # (move toward the meet location, confirm a pending invite, etc.) and so
    # the prioritisation directive in the decision ladder has context.
    plans_section = ""
    minutes_to_next: Optional[int] = None
    try:
        my_plans = world.get_plans_for(
            agent_name, statuses=("pending", "confirmed")
        )
    except Exception:
        my_plans = []
    if my_plans:
        cur_abs = world._state["day"] * 1440 + world._state["sim_time"]
        lines: list[str] = []
        for p in my_plans:
            other = next(
                (x for x in p.get("participants", []) if x != agent_name),
                "?",
            )
            target_abs = p.get("target_time", 0)
            delta = target_abs - cur_abs
            when_str = world.time_to_str(target_abs % 1440)
            if p.get("status") == "confirmed" and 0 <= delta and (
                minutes_to_next is None or delta < minutes_to_next
            ):
                minutes_to_next = delta
            rel = (
                f"in {delta} min" if delta >= 0 else f"{-delta} min ago"
            )
            lines.append(
                f"- plan #{p.get('id')} [{p.get('status')}] with {other} — "
                f"{p.get('activity', 'meet')} at {p.get('location', '?')} "
                f"@ {when_str} ({rel})"
            )
        plans_section = (
            "=== UPCOMING PLANS ===\n"
            + "\n".join(lines)
            + "\n\n"
        )

    # Missed-plan reminder (soft nudge for the absent agent — Story 9.5).
    missed_lines = [
        msg.get("text", "") for msg in inbox_messages
        if msg.get("type") == "missed_plan"
    ]
    missed_section = (
        "=== YOU MISSED A PLAN ===\n"
        + "\n".join(f"- {line}" for line in missed_lines)
        + "\n\n"
        if missed_lines else ""
    )

    # Priority hint for the decision ladder when a confirmed plan is imminent.
    plan_priority_hint = ""
    if minutes_to_next is not None and minutes_to_next <= 30:
        plan_priority_hint = (
            "- You have a confirmed plan in the next 30 min. UNLESS hunger>85 or "
            "energy<20, prioritise moving toward the plan location now.\n"
        )
    # --- end Story 9.5 --------------------------------------------------

    # Build the LLM prompt
    llm_prompt = (
        "=== WHO YOU ARE ===\n"
        f"{soul_summary}\n\n"
        "=== YOUR GOALS ===\n"
        f"{goals}\n\n"
        "=== RIGHT NOW ===\n"
        f"{needs_summary}\n"
        f"{surroundings}\n\n"
        "=== MESSAGES RECEIVED ===\n"
        f"{formatted_inbox}\n\n"
        f"{history_section}"
        "=== RELEVANT MEMORIES ===\n"
        f"{memory_text}\n\n"
        f"{today_section}"
        f"{schedule_section}"
        f"{reflection_section}"
        f"{financial_section}"
        f"{plans_section}"
        f"{missed_section}"
        f"{personality_section}"
        "=== WHAT DO YOU DO? ===\n"
        "Choose exactly one tool. Use this logic:\n"
        "- If yesterday's reflection names a behavior to change, pick an action that "
        "honors it — even if it's harder than the default.\n"
        # --- Story 9.5 (shared plans) ------------------------------------
        f"{plan_priority_hint}"
        "- If a chat thread is circling without commitment, use `propose_plan` "
        "(target, location, time, activity) to turn it into a concrete meeting. "
        "If you have a pending plan_proposal in your inbox, decide now: "
        "`confirm_plan(plan_id)` or `decline_plan(plan_id, reason)`.\n"
        # --- end Story 9.5 ----------------------------------------------
        # --- Story 9.3 (refuse / disagree) -------------------------------
        "- You are allowed to refuse. If a request conflicts with your goals or values, "
        "use `refuse` — agreeing to everything is not in character. If you genuinely "
        "disagree about something that matters, use `disagree` rather than pretending "
        "to agree.\n"
        # --- end Story 9.3 -----------------------------------------------
        "- Critically hungry (hunger >70%)? → use eat_out if at dhaba/cyber_hub/sector29, "
        "  or move_to dhaba (you can move anywhere — routing is automatic)\n"
        "- Exhausted (energy <30%)? → move_to apartment and sleep\n"
        "- Have unread messages? Read the RECENT EXCHANGES block first. If the thread has "
        "  3+ exchanges with no concrete plan (time + place + activity), STOP messaging — "
        "  either propose something specific now, or do something else and let it breathe. "
        "  If the thread is fresh, reply with talk_to but say something NEW — never repeat "
        "  the gist of your last 3 messages to that person.\n"
        "- Someone you know or like is nearby? → talk_to them — be warm, curious, maybe flirt\n"
        "- At work during work hours (no one interesting nearby)? → work to earn money\n"
        "- Craving company? → move_to dhaba, sector29, cyber_hub, or park to find people\n"
        "- At a new location? → explore its services\n"
        "- Otherwise? → move somewhere with a social or personal purpose\n"
        "NOTE: move_to automatically routes through intermediate stops — just name your destination.\n"
        "Human connection — friendship, attraction, rivalry — is as important as survival. Act on it.\n"
        f"Be decisive. Be true to your character.{repeat_warning}\n\n"
        "=== HOW YOU SPEAK ===\n"
        "You are a modern urban Indian living in Gurgaon. Speak in Hinglish — a natural mix of "
        "Hindi and English the way real people in Delhi-NCR actually talk. Write in English script "
        "(Roman letters only, no Devanagari). Sprinkle Hindi words and phrases naturally: yaar, bhai, "
        "arre, bas, acha, theek hai, matlab, bilkul, suno, dekho, kya hua, chal, abhi, bohot, "
        "kaam, paisa, tension, scene, timepass, jugaad. "
        "Example: 'arre yaar, itna traffic tha — I'm exhausted bhai.' "
        "Do NOT translate everything to Hindi. Let English and Hindi flow together naturally. "
        "The ratio should feel like a Gurgaon office conversation, not a Bollywood script."
    )

    return {
        **state,
        "soul": soul,
        "goals": goals,
        "needs_summary": needs_summary,
        "surroundings": surroundings,
        "inbox_messages": inbox_messages,
        "memory_snippets": memory_text,
        "llm_prompt": llm_prompt,
    }


# ---------------------------------------------------------------------------
# Node 2: llm_decide
# ---------------------------------------------------------------------------


async def llm_decide(state: AgentState) -> AgentState:
    """
    Ask the LLM what to do next.

    If the model returns a tool call, use it directly. If it returns plain
    text, attempt a simple keyword parse to extract a tool name; fall back
    to ``look_around`` with no args if parsing fails.
    """
    agent_name = state["agent_name"]

    response = await call_llm(
        state["llm_prompt"],
        tools=TOOL_SCHEMAS,
        system=(
            f"You are {agent_name.capitalize()}, a character in a Gurgaon town simulation. "
            "You must call exactly one tool. Prefer active tools (move_to, talk_to, eat_out, "
            "work, sleep) over passive ones (look_around). Only use look_around if you "
            "genuinely need to reorient after arriving somewhere new."
        ),
        max_tokens=200,
        thinking=False,
    )

    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None

    if response.tool_name:
        # Clean structured tool call from the LLM
        tool_name = response.tool_name
        tool_args = response.tool_args or {}
    else:
        # Text-only response: try to find a tool name mentioned in the text
        text = (response.text or "").lower()
        # Walk through known tool names and pick the first match
        known_tools = [schema["function"]["name"] for schema in TOOL_SCHEMAS]
        for candidate in known_tools:
            if candidate.replace("_", " ") in text or candidate in text:
                tool_name = candidate
                tool_args = {}
                break

        # Ultimate fallback: look_around with no args
        if tool_name is None:
            tool_name = "look_around"
            tool_args = {}

        logger.debug(
            "[%s] LLM returned text-only; parsed tool=%s from: %s",
            agent_name,
            tool_name,
            (response.text or "")[:80],
        )

    logger.info("[%s] decided: %s(%s)", agent_name, tool_name, tool_args)

    return {
        **state,
        "tool_name": tool_name,
        "tool_args": tool_args,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _action_label(tool_name: str, tool_args: dict) -> str:
    """Convert a tool name + args into a short human-readable bubble string."""
    _simple: dict[str, str] = {
        "look_around":     "looking around...",
        "check_needs":     "checking needs...",
        "check_inventory": "checking inventory...",
        "append_diary":    "writing diary...",
        "grep_memory":     "recalling memory...",
        "sleep_action":    "sleeping...",
        "work":            "working...",
    }
    if tool_name in _simple:
        return _simple[tool_name]
    if tool_name == "read_file":
        return f"reading {tool_args.get('filename', 'notes')}..."
    if tool_name == "edit_file":
        return f"editing {tool_args.get('filename', 'notes')}..."
    if tool_name == "move_to":
        return f"moving to {tool_args.get('location', 'somewhere')}..."
    if tool_name == "talk_to":
        target = tool_args.get('target', 'someone')
        msg = tool_args.get('message', '')
        snippet = msg[:80] + ('…' if len(msg) > 80 else '')
        return f"talking to {target}: {snippet}" if snippet else f"talking to {target}…"
    if tool_name == "ask_about":
        return f"asking {tool_args.get('target', 'someone')}…"
    if tool_name == "give_item":
        return f"giving {tool_args.get('item', 'something')}..."
    if tool_name == "buy":
        return f"buying {tool_args.get('item', 'something')}..."
    if tool_name == "sell":
        return f"selling {tool_args.get('item', 'something')}..."
    if tool_name == "eat":
        return f"eating {tool_args.get('item', 'food')}..."
    if tool_name == "eat_out":
        return "eating out..."
    return tool_name.replace("_", " ") + "..."


# ---------------------------------------------------------------------------
# Node 3: execute_tool_node
# ---------------------------------------------------------------------------


async def execute_tool_node(state: AgentState) -> AgentState:
    """
    Execute the chosen tool and record the result in world events.
    """
    agent_name = state["agent_name"]
    tool_name = state["tool_name"] or "look_around"
    tool_args = state["tool_args"] or {}

    try:
        tool_result = await execute_tool(agent_name, tool_name, tool_args)
    except TypeError as exc:
        tool_result = f"Tool call failed (missing args): {exc}"
        logger.warning("[%s] tool %s bad args %s: %s", agent_name, tool_name, tool_args, exc)

    # Record event in world history (truncated for readability)
    if tool_name == "talk_to":
        target = tool_args.get("target", "")
        msg = tool_args.get("message", tool_result)
        snippet = msg[:80] + ("…" if len(msg) > 80 else "")
        await tools.world.add_event(f"{agent_name} says to {target}: {snippet}")
    elif tool_name == "ask_about":
        target = tool_args.get("target", "")
        topic = tool_args.get("topic", tool_result)
        snippet = topic[:80] + ("…" if len(topic) > 80 else "")
        await tools.world.add_event(f"{agent_name} asks {target}: {snippet}")
    else:
        await tools.world.add_event(
            f"{agent_name} → {tool_name}: {tool_result[:60]}"
        )

    # Update last-action label for the renderer (thought bubble)
    await tools.world.set_agent_last_action(agent_name, _action_label(tool_name, tool_args))

    logger.info("[%s] result: %s", agent_name, tool_result)

    return {
        **state,
        "tool_result": tool_result,
    }


# ---------------------------------------------------------------------------
# Node 4: reflect
# ---------------------------------------------------------------------------


async def reflect(state: AgentState) -> AgentState:
    """
    Write a private diary entry reflecting on what just happened.

    Makes a second LLM call (no tool schemas) to generate a short,
    first-person diary entry, then appends it to diary.md.
    """
    agent_name = state["agent_name"]
    tool_name = state["tool_name"] or "look_around"
    tool_args = state["tool_args"] or {}
    tool_result = state["tool_result"]

    reflection_prompt = (
        f"You are {agent_name}. You just did: {tool_name}({tool_args})\n"
        f"Result: {tool_result}\n\n"
        "Write ONE short diary entry (2-4 sentences) in your personal voice "
        "about what just happened and how you feel. Be specific, be human. "
        "No need to repeat what you did mechanically — write how it felt. "
        "Write in Hinglish — the natural Hindi-English mix spoken in Gurgaon. "
        "English script only (no Devanagari). Example tone: "
        "'arre yaar, aaj bohot thaka diya office ne. But that meeting actually went well — "
        "matlab finally kuch toh hua.'"
    )

    response = await call_llm(
        reflection_prompt,
        system=f"You are {agent_name}, a Gurgaon resident writing in your private diary in Hinglish.",
        max_tokens=500,
        thinking=False,
    )

    # Use text response; fall back to a minimal entry if LLM fails silently
    diary_text = response.text or f"Did {tool_name}. Life continues."

    # Persist to diary.md
    await append_diary(agent_name, diary_text)

    logger.info("[%s] diary: %s...", agent_name, diary_text[:80])

    return {
        **state,
        "diary_entry": diary_text,
    }


# ---------------------------------------------------------------------------
# Night reflection (Story 9.2)
# ---------------------------------------------------------------------------


def _todays_diary_entries(agent_name: str, day: int) -> str:
    """Return the agent's diary entries tagged with `# Day {day} —` as a string."""
    path = f"agents/{agent_name}/diary.md"
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return ""

    marker = f"# Day {day} —"
    blocks: list[str] = []
    current: list[str] = []
    in_block = False
    for line in content.splitlines():
        if line.startswith("# Day "):
            if in_block and current:
                blocks.append("\n".join(current))
            current = []
            in_block = line.startswith(marker)
            if in_block:
                current.append(line)
        elif in_block:
            current.append(line)
    if in_block and current:
        blocks.append("\n".join(current))
    return "\n\n".join(blocks).strip()


def _todays_events_for(agent_name: str, day: int) -> str:
    """Return event lines from the rolling event log for *day* mentioning *agent_name*."""
    events = world._state.get("events", []) if hasattr(world, "_state") else []
    day_marker = f"Day {day}"
    matched = [
        f"- [{e.get('time', '?')}] {e.get('text', '')}"
        for e in events
        if day_marker in e.get("time", "") and agent_name in e.get("text", "")
    ]
    return "\n".join(matched[-30:])


async def night_reflection(agent_name: str, completed_day: int) -> str:
    """Generate and persist a 2-3 sentence reflection for the day that just ended.

    Called once per agent at the day-boundary tick. Stores the result on
    ``world._state["agents"][name]["yesterday_reflection"]`` (overwrite each day).
    Returns the reflection text (empty string on hard failure).
    """
    try:
        soul = await read_file(agent_name, "soul.md")
    except Exception:
        soul = ""
    soul_summary = soul[:400] if soul else ""

    diary_today = _todays_diary_entries(agent_name, completed_day)
    events_today = _todays_events_for(agent_name, completed_day)

    prompt = (
        f"You are {agent_name}. Day {completed_day} just ended.\n\n"
        f"=== WHO YOU ARE ===\n{soul_summary}\n\n"
        f"=== YOUR DIARY TODAY ===\n{diary_today or '(no entries)'}\n\n"
        f"=== EVENTS INVOLVING YOU TODAY ===\n{events_today or '(no events)'}\n\n"
        "Write 2-3 sentences. What surprised you today? What pattern in your "
        "own behavior do you notice? What's one concrete thing you want to do "
        "differently tomorrow? Write in Hinglish (English script), first person, "
        "no preamble."
    )

    try:
        response = await call_llm(
            prompt,
            system=f"You are {agent_name}, reflecting privately at the end of the day.",
            max_tokens=300,
            thinking=False,
        )
        text = (response.text or "").strip()
    except Exception as exc:
        logger.warning("[%s] night_reflection LLM failed: %s", agent_name, exc)
        text = ""

    if not text:
        text = f"Day {completed_day} ended. Tomorrow, talk to someone new instead of repeating today."

    await world.set_yesterday_reflection(agent_name, text)
    logger.info("[%s] night reflection: %s", agent_name, text[:80])
    return text


# ---------------------------------------------------------------------------
# Memory consolidation (Story 9.7)
# ---------------------------------------------------------------------------
# --- Story 9.7 BEGIN -------------------------------------------------------

import re as _re

_DAY_HEADER_RE = _re.compile(r"^# Day (\d+)\b")


def _recent_diary_entries(agent_name: str, days: int, current_day: int) -> str:
    """Return diary entries from the last *days* days (inclusive of current_day).

    Diary headers look like ``# Day N — 6:00am``. Entries whose day falls in
    ``[current_day - days + 1, current_day]`` are returned, joined with blank
    lines. Returns an empty string if the diary is missing or empty.
    """
    path = f"agents/{agent_name}/diary.md"
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return ""

    earliest = max(1, current_day - days + 1)
    blocks: list[str] = []
    current: list[str] = []
    in_block = False
    for line in content.splitlines():
        match = _DAY_HEADER_RE.match(line)
        if match:
            if in_block and current:
                blocks.append("\n".join(current))
            current = []
            day_n = int(match.group(1))
            in_block = earliest <= day_n <= current_day
            if in_block:
                current.append(line)
        elif in_block:
            current.append(line)
    if in_block and current:
        blocks.append("\n".join(current))
    return "\n\n".join(blocks).strip()


def _recent_events_for(agent_name: str, days: int, current_day: int) -> str:
    """Return event lines from the last *days* days mentioning *agent_name*.

    Events have a ``time`` like ``"6:00am Day 1"``. We parse the day from that
    string and keep only events in ``[current_day - days + 1, current_day]``
    that contain the agent's name in their text.
    """
    events = world._state.get("events", []) if hasattr(world, "_state") else []
    earliest = max(1, current_day - days + 1)
    matched: list[str] = []
    for e in events:
        text = e.get("text", "")
        if agent_name not in text:
            continue
        time_str = e.get("time", "")
        # parse "Day N" out of e.g. "6:00am Day 3"
        m = _re.search(r"Day (\d+)", time_str)
        if not m:
            continue
        day_n = int(m.group(1))
        if earliest <= day_n <= current_day:
            matched.append(f"- [{time_str}] {text}")
    # Cap to avoid runaway prompt bloat for active agents.
    return "\n".join(matched[-60:])


async def consolidate_memory(agent_name: str, completed_day: int) -> str:
    """Refresh ``agents/{name}/memory.md`` from recent diary + events.

    Makes one LLM call summarising the last 3 days against the agent's
    existing memory and the agent's soul (read-only context). Writes the
    result back to memory.md, replacing the file. Logs a ``memory_updated``
    event so observers can see when an agent's understanding shifted.

    Returns the new memory text (empty string on hard failure — file untouched).
    """
    path = f"agents/{agent_name}/memory.md"

    try:
        soul = await read_file(agent_name, "soul.md")
    except Exception:
        soul = ""
    soul_summary = soul[:400] if soul else ""

    try:
        with open(path, "r", encoding="utf-8") as f:
            current_memory = f.read()
    except FileNotFoundError:
        current_memory = ""

    diary_recent = _recent_diary_entries(agent_name, 3, completed_day)
    events_recent = _recent_events_for(agent_name, 3, completed_day)

    prompt = (
        f"You are {agent_name}. Day {completed_day} just ended. You are reviewing "
        "your recent past and updating your long-term memory.\n\n"
        f"=== WHO YOU ARE ===\n{soul_summary}\n\n"
        f"=== YOUR CURRENT MEMORY.MD ===\n{current_memory or '(empty)'}\n\n"
        f"=== YOUR DIARY — LAST 3 DAYS ===\n{diary_recent or '(no entries)'}\n\n"
        f"=== EVENTS INVOLVING YOU — LAST 3 DAYS ===\n{events_recent or '(no events)'}\n\n"
        "Update your memory.md. Add new observations about yourself or others. "
        "Sharpen or correct existing entries that turned out wrong. Keep entries "
        "terse — one to two lines each. Do not delete the seed relationships, "
        "but you can refine them. Output the FULL new memory.md content only — "
        "no preamble, no code fences, no commentary."
    )

    try:
        response = await call_llm(
            prompt,
            system=(
                f"You are {agent_name}, reviewing your own memory.md and "
                "rewriting it based on what you've actually learned."
            ),
            max_tokens=1200,
            thinking=False,
        )
        text = (response.text or "").strip()
    except Exception as exc:
        logger.warning("[%s] consolidate_memory LLM failed: %s", agent_name, exc)
        return ""

    if not text:
        logger.warning("[%s] consolidate_memory: empty LLM response", agent_name)
        return ""

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text if text.endswith("\n") else text + "\n")
    except Exception as exc:
        logger.warning("[%s] consolidate_memory write failed: %s", agent_name, exc)
        return ""

    try:
        await world.add_event(
            f"{agent_name} updated their memory after Day {completed_day}."
        )
    except Exception as exc:
        logger.warning("[%s] consolidate_memory event log failed: %s", agent_name, exc)

    logger.info("[%s] memory consolidated (Day %d)", agent_name, completed_day)
    return text


# --- Story 9.7 END ---------------------------------------------------------


# ---------------------------------------------------------------------------
# Build and compile the graph
# ---------------------------------------------------------------------------


def build_agent_graph():
    """Construct and compile the four-node LangGraph agent graph."""
    graph = StateGraph(AgentState)

    graph.add_node("gather_context", gather_context)
    graph.add_node("llm_decide", llm_decide)
    graph.add_node("execute_tool", execute_tool_node)
    graph.add_node("reflect", reflect)

    graph.set_entry_point("gather_context")
    graph.add_edge("gather_context", "llm_decide")
    graph.add_edge("llm_decide", "execute_tool")
    graph.add_edge("execute_tool", "reflect")
    graph.add_edge("reflect", END)

    return graph.compile()


# Module-level compiled graph — imported and reused by AgentRunner
agent_graph = build_agent_graph()


# ---------------------------------------------------------------------------
# AgentRunner
# ---------------------------------------------------------------------------


class AgentRunner:
    """
    Convenience wrapper around the compiled agent graph.

    Parameters
    ----------
    agent_name : str
        The name of the agent (must exist in world state and agents/ directory).
    """

    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name

    async def tick(self) -> AgentState:
        """
        Run one full tick of the agent decision loop.

        Returns the final ``AgentState`` after all four nodes have executed.
        """
        initial_state: AgentState = AgentState(
            agent_name=self.agent_name,
            soul="",
            goals="",
            needs_summary="",
            surroundings="",
            inbox_messages=[],
            memory_snippets="",
            llm_prompt="",
            tool_name=None,
            tool_args=None,
            tool_result="",
            diary_entry="",
            tick_count=0,
        )
        result = await agent_graph.ainvoke(initial_state)
        return result


# ---------------------------------------------------------------------------
# __main__ entry point (requires live Ollama — do not run in CI)
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import asyncio
    import sys

    agent_name = sys.argv[1] if len(sys.argv) > 1 else "arjun"
    ticks = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    async def run() -> None:
        from engine.tools import world as _world

        _world.load()
        runner = AgentRunner(agent_name)
        for i in range(ticks):
            print(f"\n{'=' * 50}")
            print(f"TICK {i + 1} — {agent_name}")
            print("=" * 50)
            result = await runner.tick()
            _world.advance_time(15)
            _world.save()
            print(f"Action: {result['tool_name']}")
            print(f"Diary: {result['diary_entry'][:200]}")

    asyncio.run(run())
