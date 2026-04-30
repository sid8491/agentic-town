"""
engine/headlines.py — Story 10.10 Daily Gossip Headlines (backend slice).

Once per game day at 18:00, generate 2–3 cheeky tabloid-style headlines
summarising the day's notable events. Cached in
``world._state["daily_headlines"][str(day)]`` so a viewer ticker can fetch
"today's" headlines without re-hitting the LLM.

A live LLM call only fires when the day actually has events. Empty days
produce a deterministic "quiet day" fallback so early Day 1 ticks don't
blow tokens generating gossip about nothing.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Iterable

from engine.llm import call_llm

logger = logging.getLogger(__name__)

_MAX_HEADLINES = 3
_MAX_HEADLINE_CHARS = 100

_AGENTS_DIR = "agents"

_SYSTEM_PROMPT = (
    "You write the gossip column for a fictional Gurgaon neighborhood "
    "newsletter. Given today's notable events, write 2–3 cheeky tabloid-style "
    "headlines (max 12 words each). Be playful, slightly dramatic, never mean. "
    "Examples: 'Local Founder Spotted Leaving Cyber Hub Alone — Again' / "
    "'Drama at the Dhaba: Two Friends, One Awkward Silence' / 'Mystery "
    "Solved: Why Vikram Skipped His Morning Walk'. Avoid using any agent's "
    "full name more than once across the set. Return one headline per line, "
    "no numbering, no bullets."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DAY_RE = re.compile(r"Day\s+(\d+)", re.IGNORECASE)


def _parse_event_day(event: dict) -> int | None:
    """Extract the day number from an event's ``time`` string ('6:00am Day 3')."""
    raw = event.get("time") or ""
    m = _DAY_RE.search(raw)
    if not m:
        return None
    try:
        return int(m.group(1))
    except (TypeError, ValueError):
        return None


def filter_events_for_day(events: Iterable[dict], day: int) -> list[dict]:
    """Return events whose ``time`` field matches ``Day {day}``."""
    out: list[dict] = []
    for ev in events:
        if _parse_event_day(ev) == day:
            out.append(ev)
    return out


def _soul_one_liner(agent_name: str) -> str:
    """First non-empty content paragraph of the agent's soul.md (or '')."""
    path = os.path.join(_AGENTS_DIR, agent_name, "soul.md")
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


def collect_agent_souls(agent_names: Iterable[str]) -> dict[str, str]:
    """Build a name → one-line-soul mapping for prompt injection."""
    return {name: _soul_one_liner(name) for name in agent_names}


_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*•]+|\d+[.)])\s*")
_QUOTE_STRIP_CHARS = "\"'`“”‘’"


def parse_headlines(text: str) -> list[str]:
    """Turn raw LLM output into a list of headline strings.

    Splits on newlines, strips bullets / numbering / surrounding quotes,
    drops empties, caps at 3 entries, drops any longer than 100 chars.
    """
    if not text:
        return []
    out: list[str] = []
    for raw_line in text.splitlines():
        line = _BULLET_PREFIX_RE.sub("", raw_line).strip()
        line = line.strip(_QUOTE_STRIP_CHARS).strip()
        if not line:
            continue
        if len(line) > _MAX_HEADLINE_CHARS:
            continue
        out.append(line)
        if len(out) >= _MAX_HEADLINES:
            break
    return out


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


async def generate_headlines(
    day_events: list[dict],
    agent_souls: dict[str, str],
) -> list[str]:
    """Produce 2–3 short tabloid-style headlines for the day's events.

    Returns an empty list on LLM failure — the caller decides what to cache.
    Empty input is handled by the wrapper, not here.
    """
    events_block = "\n".join(
        f"- [{e.get('time', '')}] {e.get('text', '')}" for e in day_events
    ) or "- (none)"
    souls_block = "\n".join(
        f"- {name}: {desc}" for name, desc in agent_souls.items() if desc
    ) or "- (none)"

    prompt = (
        f"Cast (one-line bios):\n{souls_block}\n\n"
        f"Today's events:\n{events_block}\n\n"
        "Write 2–3 headlines now."
    )
    try:
        resp = await call_llm(
            prompt,
            system=_SYSTEM_PROMPT,
            max_tokens=200,
            thinking=False,
        )
    except Exception as exc:
        logger.warning("[headlines] call_llm failed: %s", exc)
        return []
    return parse_headlines(resp.text or "")


async def maybe_generate_and_cache(world, day: int) -> list[str]:
    """Fire-once-per-day wrapper used by the SimulationLoop hook.

    Returns the headlines stored on the world (empty list if generation failed).
    Skips the LLM entirely when the day has no events — emits a "quiet day"
    fallback instead so the cache still has something for the endpoint.
    """
    cache = world._state.setdefault("daily_headlines", {})
    key = str(day)
    if key in cache:
        return cache[key]

    all_events = world._state.get("events", [])
    day_events = filter_events_for_day(all_events, day)

    if not day_events:
        fallback = [f"Day {day}: A quiet day in Gurgaon — for now."]
        cache[key] = fallback
        logger.info("[headlines] day %d had no events — used quiet-day fallback", day)
        return fallback

    from engine.world import SimulationLoop  # local import to avoid cycles
    souls = collect_agent_souls(SimulationLoop.AGENTS)
    headlines = await generate_headlines(day_events, souls)
    if not headlines:
        # Failure path: leave the cache untouched so we can retry on the
        # next tick of the same day, and the endpoint reports empty.
        return []
    cache[key] = headlines
    logger.info("[headlines] cached %d headlines for day %d", len(headlines), day)
    return headlines


def get_today_headlines(world) -> dict:
    """Return ``{day, headlines}`` for the current sim day."""
    day = int(world._state.get("day", 1))
    cache = world._state.get("daily_headlines", {}) or {}
    return {"day": day, "headlines": list(cache.get(str(day), []))}
