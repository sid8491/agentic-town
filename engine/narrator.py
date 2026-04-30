"""
engine/narrator.py — Live narrator for Story 10.2.

Generates a 1–2 sentence present-tense narration of whatever the current
protagonist is doing, including emotional subtext but never raw stat numbers.

The narration is cached on ``world._state["_narration"]`` (underscore prefix
keeps it out of state.json — same trick as ``_pending_summary``).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

from engine.llm import call_llm
from engine.protagonist import pick_protagonist

logger = logging.getLogger(__name__)

# Real-seconds between narrator polls. Spec: ~30s.
NARRATION_INTERVAL_SEC: float = 30.0

_SYSTEM_PROMPT = (
    "You are a calm, observant narrator describing a slice-of-life show set "
    "in modern Gurgaon. In 1–2 sentences (max 30 words total), describe what "
    "{protagonist} is doing right now and the emotional subtext. Use present "
    "tense. Be specific. Do not summarize, do not editorialize, do not name "
    "internal stats like 'mood'. Examples: 'Arjun has been pacing near Cyber "
    "Hub for ten minutes. He's checking his phone. Kavya hasn't replied.' / "
    "'Priya finally took a break — she's at the coffee shop alone, watching "
    "the rain.'"
)


def _soul_one_liner(agent_name: str) -> str:
    """Return the first non-empty paragraph of the agent's soul.md, or ''."""
    path = os.path.join("agents", agent_name, "soul.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return ""
    paragraphs: list[str] = []
    buf: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        if line.strip() == "":
            if buf:
                paragraphs.append(" ".join(s.strip() for s in buf).strip())
                buf = []
            continue
        buf.append(line)
    if buf:
        paragraphs.append(" ".join(s.strip() for s in buf).strip())
    for p in paragraphs:
        if p:
            return p
    return ""


def _qualitative_descriptors(agent: dict) -> list[str]:
    """Convert raw stats into adjective phrases — never expose numbers."""
    out: list[str] = []
    energy = float(agent.get("energy", 100.0))
    hunger = float(agent.get("hunger", 0.0))
    mood = float(agent.get("mood", 50.0))
    if energy < 30:
        out.append("tired")
    elif energy > 85:
        out.append("rested")
    if hunger > 80:
        out.append("hungry")
    if mood > 75:
        out.append("lifted")
    elif mood < 30:
        out.append("low")
    if bool(agent.get("financial_stress", False)):
        out.append("financially anxious")
    return out


def _events_for_agent(world, name: str, limit: int = 5) -> list[str]:
    """Return up to *limit* most-recent event texts mentioning *name*."""
    events = world._state.get("events", [])
    lname = name.lower()
    matched = [
        ev for ev in events
        if lname in (ev.get("text") or "").lower()
    ]
    last = matched[-limit:]
    return [f"[{ev.get('time', '')}] {ev.get('text', '')}" for ev in last]


def _build_prompt(world, protagonist: str, recent_events: list[str]) -> str:
    """Assemble the user prompt fed to call_llm."""
    try:
        agent = world.get_agent(protagonist)
    except KeyError:
        agent = {}
    soul = _soul_one_liner(protagonist)
    last_action = agent.get("last_action", "") or "(idle)"
    location = agent.get("location", "") or "(unknown)"
    descriptors = _qualitative_descriptors(agent)
    desc_line = ", ".join(descriptors) if descriptors else "steady"
    events_block = "\n".join(f"- {e}" for e in recent_events) or "- (none)"

    return (
        f"Protagonist: {protagonist}\n"
        f"Soul (one-liner): {soul}\n"
        f"Last action: {last_action}\n"
        f"Location: {location}\n"
        f"Feeling: {desc_line}\n"
        f"Recent events involving {protagonist}:\n{events_block}\n"
    )


def _cache_key(world, protagonist: str) -> tuple[str, str, str]:
    try:
        agent = world.get_agent(protagonist)
    except KeyError:
        return (protagonist, "", "")
    return (
        protagonist,
        agent.get("last_action", "") or "",
        agent.get("location", "") or "",
    )


async def generate_narration(
    world,
    recent_events: list[str],
    protagonist_name: str,
) -> str:
    """Call the LLM to produce 1–2 sentences of live narration.

    Returns an empty string if the model produces nothing usable. Callers are
    responsible for caching the result on the world.
    """
    prompt = _build_prompt(world, protagonist_name, recent_events)
    system = _SYSTEM_PROMPT.format(protagonist=protagonist_name)
    try:
        resp = await call_llm(
            prompt,
            system=system,
            max_tokens=120,
            thinking=False,
        )
    except Exception as exc:
        logger.warning("[narrator] call_llm failed: %s", exc)
        return ""
    text = (resp.text or "").strip()
    return text


def get_cached_narration(world) -> dict:
    """Return the dict cached at world._state['_narration'] (or empty default)."""
    cached = world._state.get("_narration")
    if not cached:
        return {"narration": "", "protagonist": "", "ts": 0.0}
    return {
        "narration": cached.get("text", ""),
        "protagonist": cached.get("protagonist", ""),
        "ts": cached.get("ts", 0.0),
    }


async def narrator_loop(
    world,
    interval: float = NARRATION_INTERVAL_SEC,
    stop_event: Optional[asyncio.Event] = None,
) -> None:
    """Background task: regenerate narration every *interval* real seconds.

    Cache is keyed on (protagonist, last_action, location). When the key hasn't
    changed since the last successful call we skip the LLM entirely so the
    same idle scene doesn't burn tokens.
    """
    last_key: tuple[str, str, str] | None = None
    while True:
        if stop_event is not None and stop_event.is_set():
            return
        try:
            protagonist = pick_protagonist(world)
            if not protagonist:
                await asyncio.sleep(interval)
                continue
            key = _cache_key(world, protagonist)
            if key == last_key:
                # Same protagonist + same last_action + same location → cache hit.
                logger.debug("[narrator] cache hit, skipping LLM call")
            else:
                events = _events_for_agent(world, protagonist, limit=5)
                text = await generate_narration(world, events, protagonist)
                if text:
                    world._state["_narration"] = {
                        "text": text,
                        "protagonist": protagonist,
                        "ts": time.time(),
                    }
                    last_key = key
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[narrator] loop iteration failed: %s", exc)
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
