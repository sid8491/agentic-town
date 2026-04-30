"""
engine/plots.py — Plot Threads Tracker (Story 10.4)

Pure-logic detector that scans the current WorldState for narrative threads
worth surfacing in the viewer sidebar. No LLM calls. No mutation.

Each thread is a dict:
    {
      "id":           str,    # stable per-thread key (used for de-dupe / UI)
      "title":        str,
      "participants": [str],
      "status_text":  str,
      "progress":     float,  # 0.0-1.0
      "last_updated": int,    # absolute minutes (day*1440 + sim_time)
      "type":         str,    # one of: pending_plan / awkwardness / financial /
                              #         mood_spiral / chat_streak / disagreement
    }

Threads expire 24 game hours after `last_updated` if no fresh signal.
Caller (server.py) sorts by last_updated desc and caps to 5.
"""

from __future__ import annotations

import re
from typing import Optional

# 24 game hours, in game minutes
_EXPIRY_MINUTES = 24 * 60
# 4 game hours window for a "pending" plan progress bar (matches spec).
_PLAN_HORIZON_MINUTES = 240
# 3 game hours window for chat streak detection.
_CHAT_STREAK_WINDOW = 3 * 60
# Mood threshold used by the spiral detector. We deliberately ignore the
# "for >=6 game hours" duration component: the simulation has no per-tick
# mood history, and adding one would couple this detector to the tick loop.
# A snapshot mood < 30 is the simplest defensible signal — once mood climbs
# above 30 the thread will naturally drop off via 24h expiry.
_MOOD_SPIRAL_THRESHOLD = 30
# Days-behind window for rent crisis progress (4 days = 1.0).
_RENT_CRISIS_DAYS = 4


_EVENT_TIME_RE = re.compile(
    r"^\s*(\d{1,2}):(\d{2})\s*(am|pm)\s+Day\s+(\d+)\s*$",
    re.IGNORECASE,
)


def _parse_event_time(time_str: str) -> Optional[int]:
    """Convert an event timestamp like '6:30am Day 2' to absolute minutes.

    Returns None if the string doesn't match the expected format.
    """
    if not isinstance(time_str, str):
        return None
    m = _EVENT_TIME_RE.match(time_str)
    if not m:
        return None
    hour, minute, suffix, day = int(m.group(1)), int(m.group(2)), m.group(3).lower(), int(m.group(4))
    hour12 = hour % 12
    if suffix == "pm":
        hour12 += 12
    sim_time = hour12 * 60 + minute
    return day * 1440 + sim_time


def _abs_now(world_state) -> int:
    return world_state._state["day"] * 1440 + world_state._state["sim_time"]


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------


def _detect_pending_plans(ws, now_abs: int) -> list[dict]:
    threads: list[dict] = []
    for plan in ws.get_shared_plans():
        if plan.get("status") != "pending":
            continue
        participants = plan.get("participants", [])
        if len(participants) < 2:
            continue
        a, b = participants[0], participants[1]
        location = plan.get("location", "?")
        target_time = int(plan.get("target_time", now_abs))
        remaining = max(0, target_time - now_abs)
        progress = 1.0 - (remaining / _PLAN_HORIZON_MINUTES)
        progress = max(0.0, min(1.0, progress))
        last_updated = int(plan.get("created_at", now_abs))
        threads.append({
            "id": f"plan:{plan.get('id')}",
            "title": f"Will {a.capitalize()} and {b.capitalize()} actually meet at {location}?",
            "participants": [a, b],
            "status_text": (
                f"Pending — target in {remaining} min" if remaining > 0
                else "Pending — overdue"
            ),
            "progress": progress,
            "last_updated": last_updated,
            "type": "pending_plan",
        })
    return threads


def _detect_awkward_plans(ws, now_abs: int) -> list[dict]:
    threads: list[dict] = []
    # Match decline_plan event text: "<who> declined plan #<id>: <reason>"
    decline_re = re.compile(r"^([a-z_]+) declined plan #(\d+)")
    for ev in ws._state.get("events", []):
        text = ev.get("text", "")
        m = decline_re.match(text)
        if not m:
            continue
        decliner = m.group(1)
        plan_id = int(m.group(2))
        plan = ws.get_plan(plan_id)
        if plan is None:
            continue
        participants = plan.get("participants", [])
        if len(participants) < 2:
            continue
        ts = _parse_event_time(ev.get("time", ""))
        if ts is None:
            continue
        if now_abs - ts > _EXPIRY_MINUTES:
            continue
        a, b = participants[0], participants[1]
        threads.append({
            "id": f"awkward:plan:{plan_id}",
            "title": f"Awkwardness between {a.capitalize()} and {b.capitalize()}",
            "participants": [a, b],
            "status_text": f"{decliner.capitalize()} declined plan #{plan_id}",
            "progress": 1.0 - (now_abs - ts) / _EXPIRY_MINUTES,
            "last_updated": ts,
            "type": "awkwardness",
        })
    return threads


def _detect_financial_stress(ws, now_abs: int) -> list[dict]:
    threads: list[dict] = []
    current_day = ws._state["day"]
    for name, agent in ws.get_all_agents().items():
        if not agent.get("financial_stress"):
            continue
        until_day = int(agent.get("financial_stress_until_day", 0))
        # financial_stress_until_day = current_day + 4 at the moment rent
        # collection put the agent under water. Days-behind grows from 0
        # (just collected) toward 4 (window expires) — that's our progress.
        days_behind = max(0, _RENT_CRISIS_DAYS - max(0, until_day - current_day))
        progress = max(0.0, min(1.0, days_behind / _RENT_CRISIS_DAYS))
        threads.append({
            "id": f"financial:{name}",
            "title": f"{name.capitalize()}'s rent crisis",
            "participants": [name],
            "status_text": (
                f"Balance {agent.get('coins', 0)} coins — "
                f"{days_behind}/{_RENT_CRISIS_DAYS} days behind"
            ),
            "progress": progress,
            "last_updated": now_abs,
            "type": "financial",
        })
    return threads


def _detect_mood_spirals(ws, now_abs: int) -> list[dict]:
    threads: list[dict] = []
    for name, agent in ws.get_all_agents().items():
        mood = float(agent.get("mood", 50.0))
        if mood >= _MOOD_SPIRAL_THRESHOLD:
            continue
        # Progress: how deep below the threshold (0 = just at 30, 1 = at 0).
        progress = max(0.0, min(1.0, (_MOOD_SPIRAL_THRESHOLD - mood) / _MOOD_SPIRAL_THRESHOLD))
        threads.append({
            "id": f"mood:{name}",
            "title": f"{name.capitalize()} is spiralling",
            "participants": [name],
            "status_text": f"Mood {int(mood)} — {agent.get('last_action', '')}".strip(" —"),
            "progress": progress,
            "last_updated": now_abs,
            "type": "mood_spiral",
        })
    return threads


def _detect_chat_streaks(ws, now_abs: int) -> list[dict]:
    convos = ws._state.get("conversations", [])
    if not convos:
        return []
    pair_counts: dict[tuple[str, str], dict] = {}
    for c in convos:
        c_day = c.get("day")
        c_sim = c.get("sim_time")
        if c_day is None or c_sim is None:
            continue
        c_abs = c_day * 1440 + c_sim
        if now_abs - c_abs > _CHAT_STREAK_WINDOW:
            continue
        a, b = c.get("from"), c.get("to")
        if not a or not b:
            continue
        key = tuple(sorted([a, b]))
        slot = pair_counts.setdefault(key, {"count": 0, "last": 0})
        slot["count"] += 1
        if c_abs > slot["last"]:
            slot["last"] = c_abs

    threads: list[dict] = []
    for (a, b), info in pair_counts.items():
        if info["count"] < 5:
            continue
        threads.append({
            "id": f"chat:{a}:{b}",
            "title": f"{a.capitalize()} and {b.capitalize()} can't stop messaging",
            "participants": [a, b],
            "status_text": f"{info['count']} messages in last 3 hours",
            "progress": min(1.0, info["count"] / 10.0),
            "last_updated": info["last"],
            "type": "chat_streak",
        })
    return threads


def _detect_disagreements(ws, now_abs: int) -> list[dict]:
    """Surface unresolved disagree events tagged 'conflict:' in the event log.

    A conflict is "unresolved" if no later event whose text contains
    'reconcile' mentions both parties. We expire the thread 24 game hours
    after the most recent conflict event for the pair anyway.
    """
    events = ws._state.get("events", [])
    # Pattern: "conflict: A vs B on TOPIC — POSITION"
    conflict_re = re.compile(r"^conflict:\s+([a-z_]+)\s+vs\s+([a-z_]+)\s+on\s+(.+?)\s+—")

    pair_latest: dict[tuple[str, str], dict] = {}
    for ev in events:
        text = ev.get("text", "")
        m = conflict_re.match(text)
        if not m:
            continue
        a, b, topic = m.group(1), m.group(2), m.group(3)
        ts = _parse_event_time(ev.get("time", ""))
        if ts is None:
            continue
        key = tuple(sorted([a, b]))
        existing = pair_latest.get(key)
        if existing is None or ts > existing["ts"]:
            pair_latest[key] = {"a": a, "b": b, "topic": topic, "ts": ts}

    # Drop pairs that later reconciled (look for "reconcile" mentioning both).
    reconciled: set[tuple[str, str]] = set()
    for ev in events:
        text = ev.get("text", "").lower()
        if "reconcile" not in text:
            continue
        ts = _parse_event_time(ev.get("time", ""))
        if ts is None:
            continue
        for key, info in pair_latest.items():
            if info["a"] in text and info["b"] in text and ts > info["ts"]:
                reconciled.add(key)

    threads: list[dict] = []
    for key, info in pair_latest.items():
        if key in reconciled:
            continue
        if now_abs - info["ts"] > _EXPIRY_MINUTES:
            continue
        a, b, topic, ts = info["a"], info["b"], info["topic"], info["ts"]
        threads.append({
            "id": f"conflict:{a}:{b}:{topic}",
            "title": f"{a.capitalize()} vs {b.capitalize()} over {topic}",
            "participants": [a, b],
            "status_text": "Unresolved disagreement",
            "progress": 1.0 - (now_abs - ts) / _EXPIRY_MINUTES,
            "last_updated": ts,
            "type": "disagreement",
        })
    return threads


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_plot_threads(world_state) -> list[dict]:
    """Return all currently active plot threads, unsorted, uncapped.

    The server endpoint applies sort + cap; tests can introspect raw output.
    """
    now_abs = _abs_now(world_state)
    threads: list[dict] = []
    threads.extend(_detect_pending_plans(world_state, now_abs))
    threads.extend(_detect_awkward_plans(world_state, now_abs))
    threads.extend(_detect_financial_stress(world_state, now_abs))
    threads.extend(_detect_mood_spirals(world_state, now_abs))
    threads.extend(_detect_chat_streaks(world_state, now_abs))
    threads.extend(_detect_disagreements(world_state, now_abs))
    # Generic 24-hour expiry guard (most detectors already filter, but this
    # protects future detectors that forget).
    threads = [t for t in threads if now_abs - t["last_updated"] <= _EXPIRY_MINUTES]
    return threads
