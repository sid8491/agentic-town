"""
engine/cliffhanger.py — End-of-day cliffhanger generator (Story 10.9, backend).

At day-boundary, summarise unresolved plot threads (Story 10.4) and pending
shared plans (Story 9.5) into a short "Tomorrow on Gurgaon: ..." teaser.

Persisted to ``world._state["daily_cliffhangers"][str(completed_day)]`` so the
recap survives a restart and the viewer can fetch it via
``GET /api/cliffhanger/{day}``.
"""

from __future__ import annotations

import logging
import os
import pathlib
from typing import Optional

from engine.llm import call_llm
from engine.plots import detect_plot_threads

logger = logging.getLogger(__name__)

_MAX_LEN = 200
_FALLBACK = "Tomorrow on Gurgaon: another quiet day. Or maybe not."

_SYSTEM_PROMPT = (
    "You are the narrator of a slice-of-life show set in modern Gurgaon. "
    "Tomorrow's previews — write 'Tomorrow on Gurgaon:' followed by 2 short "
    "teaser sentences. Reference the unresolved threads and pending plans "
    "listed below. Keep each teaser under 18 words. Be evocative, slightly "
    "dramatic. Don't moralize."
)


def _summarise_threads(threads: list[dict]) -> list[str]:
    lines: list[str] = []
    for t in threads:
        title = (t.get("title") or "").strip()
        status = (t.get("status_text") or "").strip()
        if title and status:
            lines.append(f"- {title} ({status})")
        elif title:
            lines.append(f"- {title}")
    return lines


def _summarise_plans(plans: list[dict]) -> list[str]:
    lines: list[str] = []
    for p in plans:
        if p.get("status") not in ("pending", "confirmed"):
            continue
        participants = p.get("participants", [])
        if len(participants) < 2:
            continue
        a, b = participants[0], participants[1]
        location = p.get("location", "?")
        activity = p.get("activity", "meet")
        lines.append(
            f"- {a.capitalize()} and {b.capitalize()} plan to {activity} at {location}"
        )
    return lines


def _build_prompt(thread_lines: list[str], plan_lines: list[str], completed_day: int) -> str:
    threads_block = "\n".join(thread_lines) if thread_lines else "- (none)"
    plans_block = "\n".join(plan_lines) if plan_lines else "- (none)"
    return (
        f"Day {completed_day} just ended in Gurgaon.\n\n"
        f"Unresolved threads:\n{threads_block}\n\n"
        f"Pending shared plans:\n{plans_block}\n\n"
        "Write the teaser now."
    )


async def generate_cliffhanger(world, completed_day: int) -> str:
    """Build the cliffhanger text for the day that just ended.

    Returns a fallback string when there are no unresolved threads and no
    pending plans (no LLM call is made in that case).
    """
    threads = detect_plot_threads(world)
    plans = [
        p for p in world.get_shared_plans()
        if p.get("status") in ("pending", "confirmed")
    ]
    thread_lines = _summarise_threads(threads)
    plan_lines = _summarise_plans(plans)

    if not thread_lines and not plan_lines:
        return _FALLBACK

    prompt = _build_prompt(thread_lines, plan_lines, completed_day)
    resp = await call_llm(
        prompt,
        system=_SYSTEM_PROMPT,
        max_tokens=180,
        thinking=False,
    )
    text = (resp.text or "").strip()
    if not text:
        return _FALLBACK
    if len(text) > _MAX_LEN:
        text = text[:_MAX_LEN].rstrip()
    return text


async def run_cliffhanger(
    world,
    completed_day: int,
    output_dir: Optional[pathlib.Path] = None,
) -> None:
    """Generate, persist, and append the cliffhanger for *completed_day*.

    Failures during LLM call are logged and swallowed; nothing is persisted in
    that case so a future tick or restart can retry.
    """
    try:
        text = await generate_cliffhanger(world, completed_day)
    except Exception as exc:
        logger.warning("[cliffhanger] generation failed for Day %d: %s", completed_day, exc)
        return

    if not text:
        return

    store = world._state.setdefault("daily_cliffhangers", {})
    store[str(completed_day)] = text

    save_dir = output_dir if output_dir is not None else pathlib.Path("world")
    log_path = save_dir / f"daily_log_day_{completed_day}.txt"
    try:
        os.makedirs(save_dir, exist_ok=True)
        existing = ""
        if log_path.exists():
            existing = log_path.read_text(encoding="utf-8")
        sep = "" if not existing or existing.endswith("\n") else "\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(sep + text + "\n")
    except Exception as exc:
        logger.warning("[cliffhanger] could not append to %s: %s", log_path, exc)

    logger.info("[cliffhanger] Day %d: %s", completed_day, text)
