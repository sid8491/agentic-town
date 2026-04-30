"""
engine/protagonist.py — Director-mode protagonist scoring.

Used by Story 10.2 (Live Narrator) and Story 10.1 (Director Mode camera) to
pick whichever agent has the most narrative weight at the current moment.

Pure logic: no LLM calls, no I/O. All inputs come from a WorldState instance.
"""

from __future__ import annotations

from typing import Iterable

# Tools whose `last_action` text marks the agent as actively talking.
# Kept loose on purpose — we just need a substring hit.
_TALK_TAGS = ("talk_to", "talks to", "says to", "asks", "ask_about", "share_news")

# How long ago a refuse/disagree event still counts (game minutes).
_REFUSAL_LOOKBACK_MIN = 20

# Window for counting general events involving an agent (game minutes).
_RECENT_EVENT_WINDOW_MIN = 30


def _abs_minutes(world) -> int:
    return world._state["day"] * 1440 + world._state["sim_time"]


def _event_abs_minutes(world, event_text_time: str) -> int | None:
    """Best-effort parse of an event's "h:mmam Day N" timestamp into abs minutes.

    Events are stored as ``{"time": "6:30am Day 1", "text": "..."}``. We don't
    need perfect parsing — fall back to None when shape is unexpected.
    """
    if not event_text_time:
        return None
    try:
        time_part, _day_word, day_str = event_text_time.rsplit(" ", 2)
        day = int(day_str)
        # time_part like "6:30am" or "12:00pm"
        if time_part.endswith("am") or time_part.endswith("pm"):
            suffix = time_part[-2:]
            hh, mm = time_part[:-2].split(":")
            hour = int(hh) % 12
            if suffix == "pm":
                hour += 12
            minute = int(mm)
            return day * 1440 + hour * 60 + minute
    except Exception:
        return None
    return None


def _events_for(world, name: str) -> Iterable[dict]:
    events = world._state.get("events", [])
    lname = name.lower()
    for ev in events:
        text = (ev.get("text") or "").lower()
        if lname in text:
            yield ev


def _last_action_is_talk(last_action: str) -> bool:
    if not last_action:
        return False
    la = last_action.lower()
    return any(tag in la for tag in _TALK_TAGS)


def _is_in_active_conversation(world, name: str) -> bool:
    """True if any other agent at the same location has a talk-tagged last_action.

    Either side of the exchange counts — partner talking towards us, or us
    talking towards them.
    """
    try:
        my_loc = world.get_agent_location(name)
    except KeyError:
        return False
    me_talking = _last_action_is_talk(world.get_agent_last_action(name))
    for other_name, other in world.get_all_agents().items():
        if other_name == name:
            continue
        if other.get("location") != my_loc:
            continue
        if me_talking or _last_action_is_talk(other.get("last_action", "")):
            return True
    return False


def _imminent_shared_plan(world, name: str) -> bool:
    """Confirmed plan involving *name* whose target_time is within 30 game min."""
    try:
        plans = world.get_confirmed_plans_for(name)
    except Exception:
        plans = []
    if not plans:
        return False
    now = _abs_minutes(world)
    for p in plans:
        target = p.get("target_time", 0)
        if 0 <= (target - now) < 30:
            return True
    return False


def _recent_refusal(world, name: str) -> bool:
    now = _abs_minutes(world)
    cutoff = now - _REFUSAL_LOOKBACK_MIN
    lname = name.lower()
    for ev in world._state.get("events", []):
        text = (ev.get("text") or "").lower()
        if lname not in text:
            continue
        if "refuse" not in text and "disagree" not in text:
            continue
        when = _event_abs_minutes(world, ev.get("time", ""))
        if when is None:
            # If timestamp unparseable, fall back to including it — events list
            # is already truncated so this stays bounded.
            return True
        if when >= cutoff:
            return True
    return False


def _recent_event_count(world, name: str) -> int:
    now = _abs_minutes(world)
    cutoff = now - _RECENT_EVENT_WINDOW_MIN
    count = 0
    for ev in _events_for(world, name):
        when = _event_abs_minutes(world, ev.get("time", ""))
        if when is None or when >= cutoff:
            count += 1
    return count


def score_agent(world, name: str) -> float:
    """Return the narrative-priority score for *name* given the current world.

    See Story 10.1 spec — combines social, emotional, financial, and
    plan-related signals into a single comparable number.
    """
    try:
        agent = world.get_agent(name)
    except KeyError:
        return 0.0

    score = 0.0

    if _is_in_active_conversation(world, name):
        score += 10

    if _imminent_shared_plan(world, name):
        score += 8

    mood = float(agent.get("mood", 50.0))
    if mood < 25 or mood > 80:
        score += 7

    if bool(agent.get("financial_stress", False)):
        score += 6

    hunger = float(agent.get("hunger", 0.0))
    energy = float(agent.get("energy", 100.0))
    if hunger > 80 or energy < 20:
        score += 5

    if _recent_refusal(world, name):
        score += 4

    score += 2 * _recent_event_count(world, name)

    return score


def pick_protagonist(world) -> str:
    """Return the agent name with the highest score; ties broken alphabetically.

    Falls back to the first agent name if the agents dict is empty (which
    shouldn't happen in practice).
    """
    agents = world.get_all_agents()
    if not agents:
        return ""
    scored = [(score_agent(world, n), n) for n in agents.keys()]
    # Highest score first; alphabetical tiebreak so the result is deterministic.
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return scored[0][1]
