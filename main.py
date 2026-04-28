"""
main.py — Gurgaon Town Life: Arcade renderer + simulation backbone.

Architecture
------------
  Main thread  : Arcade/pyglet event loop (rendering, key input)
  Sim thread   : asyncio event loop running SimulationLoop (all 10 agents)
  Server thread: uvicorn / FastAPI web viewer + LLM toggle API

WorldState writes always happen inside the asyncio sim thread via the Lock.
Arcade reads WorldState freely — dict reads are GIL-safe for rendering.

Controls
--------
  SPACE      Pause / resume
  ← / →      Slow down / speed up (0.25x → 0.5x → 1x → 2x → 4x)
  L          Toggle LLM (Ollama ↔ Gemini)
  ESC        Close window
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import pathlib
import threading
import time
from pathlib import Path
from typing import Optional

import arcade

from engine.llm import llm_config
from engine.world import WorldState, SimulationLoop

ALL_AGENT_NAMES = [
    "arjun", "priya", "rahul", "kavya", "suresh",
    "neha", "vikram", "deepa", "rohan", "anita",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

TILE_SIZE: int = 32
MAP_COLS: int = 30
MAP_ROWS: int = 20
HUD_HEIGHT: int = 50          # bottom strip reserved for HUD (Story 4.4)

WINDOW_W: int = TILE_SIZE * MAP_COLS           # 960 px
WINDOW_H: int = TILE_SIZE * MAP_ROWS + HUD_HEIGHT  # 690 px

ZONE_RADIUS: int = 36         # pixel radius for each location circle

# Location-type colours (RGB)
_ZONE_COLORS: dict[str, tuple[int, int, int]] = {
    "home":     (70,  130, 200),
    "work":     (90,  95,  120),
    "food":     (220, 120,  40),
    "social":   (55,  160,  75),
    "transit":  (200, 175,  35),
    "shopping": (155,  75, 175),
    "leisure":  (55,  185, 145),
}

_BUBBLE_FADE_SECS: float = 5.0    # seconds before thought bubble fully fades

# Event log overlay (top-right corner of the map area)
_LOG_W: int   = 250          # content width in px
_LOG_LINE_H: int = 13        # px per log line
_LOG_MAX: int = 10           # max entries displayed at once
_LOG_X: int   = WINDOW_W - _LOG_W - 10   # left edge of log text

# Agent inspect panel (right side overlay)
_PANEL_W: int = 280
_PANEL_X: int = WINDOW_W - _PANEL_W   # left edge of panel = 680

_MAP_BG        = (18,  20,  28)
_GRID_COLOR    = (38,  40,  52)
_CONN_COLOR    = (80,  85, 115, 150)
_BORDER_COLOR  = (230, 230, 230, 140)
_LABEL_COLOR   = (210, 215, 220, 255)

# ---------------------------------------------------------------------------
# Agent visual constants (Story 4.2)
# ---------------------------------------------------------------------------

AGENT_RADIUS: int = 13          # pixel radius of each agent circle
LERP_SPEED: float = 2.0         # lerp factor per second (arrives in ~0.5 s)

# Unique colours per agent — bright enough to read against dark zones
_AGENT_COLORS: dict[str, tuple[int, int, int]] = {
    "arjun":  (255,  88,  65),
    "priya":  (255, 138, 200),
    "rahul":  ( 65, 210, 240),
    "kavya":  (115, 228,  80),
    "suresh": (255, 200,  48),
    "neha":   (255,  72, 165),
    "vikram": (125, 142, 228),
    "deepa":  (255, 150,  95),
    "rohan":  ( 62, 205, 182),
    "anita":  (178,  88, 228),
}

# Two-letter initials shown inside each agent circle
_AGENT_INITIALS: dict[str, str] = {
    "arjun":  "AR",
    "priya":  "PR",
    "rahul":  "RA",
    "kavya":  "KA",
    "suresh": "SU",
    "neha":   "NE",
    "vikram": "VI",
    "deepa":  "DE",
    "rohan":  "RO",
    "anita":  "AN",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tile_to_pixel(tile_x: int, tile_y: int) -> tuple[int, int]:
    """Map tile coordinates → pixel centre (above the HUD strip)."""
    px = tile_x * TILE_SIZE + TILE_SIZE // 2
    py = HUD_HEIGHT + tile_y * TILE_SIZE + TILE_SIZE // 2
    return px, py


def _display_label(display_name: str) -> str:
    """Shorten a display name to two short lines for the map label."""
    words = display_name.split()
    if len(words) <= 2:
        return display_name
    mid = len(words) // 2
    return " ".join(words[:mid]) + "\n" + " ".join(words[mid:])


def _compute_spread(n: int) -> list[tuple[float, float]]:
    """
    Return pixel offsets for n agents co-located at the same zone.

    Places agents evenly on a ring whose radius guarantees no two circles
    overlap (center separation >= 2 * AGENT_RADIUS + 2 px).
    Single agent stays at centre; 2+ agents orbit around it.
    """
    if n == 1:
        return [(0.0, 0.0)]
    min_sep = AGENT_RADIUS * 2 + 2
    ring_r = max(20.0, min_sep / (2 * math.sin(math.pi / n)))
    return [
        (
            ring_r * math.cos(math.tau * i / n - math.pi / 2),
            ring_r * math.sin(math.tau * i / n - math.pi / 2),
        )
        for i in range(n)
    ]


def _name_tag_color(mood: float) -> tuple[int, int, int, int]:
    """Return RGBA name-tag color based on agent mood."""
    if mood < 30:
        return (255, 80, 80, 255)    # red — distressed
    if mood > 70:
        return (100, 220, 100, 255)  # green — happy
    return (220, 220, 220, 255)      # neutral gray


def _format_event_log_line(event: dict, max_len: int = 36) -> str:
    """Format a world event dict into one short display string for the event log."""
    time_full = event.get("time", "")
    text = event.get("text", "")
    time_short = time_full.split()[0] if time_full else ""
    if "→" in text:                      # "agent → tool: ..."
        parts = text.split("→", 1)
        agent = parts[0].strip()
        rest = parts[1].strip()
        tool = rest.split(":")[0].strip() if ":" in rest else rest[:14]
        line = f"{time_short} {agent}: {tool}"
    else:
        line = f"{time_short} {text}"
    return line[:max_len]


def _parse_diary_entries(text: str, n: int = 3) -> list[tuple[str, str]]:
    """Return the last *n* (header, body) pairs from a diary.md string."""
    entries: list[tuple[str, str]] = []
    current_header: str | None = None
    current_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("# Day"):
            if current_header is not None:
                body = "\n".join(current_lines).strip()
                if body:
                    entries.append((current_header, body))
            current_header = line[2:].strip()   # strip "# " prefix
            current_lines = []
        elif current_header is not None:
            current_lines.append(line)
    if current_header is not None:
        body = "\n".join(current_lines).strip()
        if body:
            entries.append((current_header, body))
    return entries[-n:] if entries else []


def _agent_hit(
    agent_cur: dict[str, list[float]],
    x: float,
    y: float,
    radius: int = AGENT_RADIUS + 6,
) -> str | None:
    """Return the first agent whose circle contains pixel (x, y), or None."""
    for name, cur in agent_cur.items():
        dx = cur[0] - x
        dy = cur[1] - y
        if dx * dx + dy * dy <= radius * radius:
            return name
    return None


def _draw_hud_btn(x1: int, x2: int, cy: int, label: str, disabled: bool = False) -> None:
    """Draw a labelled rectangular button in the HUD strip."""
    bg     = (16, 18, 28) if disabled else (22, 26, 44)
    border = (38, 42, 60) if disabled else (60, 65, 98)
    fg     = (50, 55, 75) if disabled else (140, 148, 182)
    arcade.draw_lrbt_rectangle_filled(x1, x2, cy - 13, cy + 13, bg)
    arcade.draw_lrbt_rectangle_outline(x1, x2, cy - 13, cy + 13, border, 1)
    arcade.draw_text(label, (x1 + x2) // 2, cy, color=fg,
                     font_size=9, anchor_x="center", anchor_y="center")


# ---------------------------------------------------------------------------
# Arcade window
# ---------------------------------------------------------------------------


class GurgaonWindow(arcade.Window):
    """Arcade window — renders the town map and relays control keys."""

    def __init__(self, world: WorldState) -> None:
        super().__init__(
            WINDOW_W, WINDOW_H,
            "Gurgaon Town Life",
            resizable=False,
            draw_rate=1 / 30,
            update_rate=1 / 30,
        )
        arcade.set_background_color(_MAP_BG)
        self.world = world

        # Pre-compute pixel centres for each location
        self._loc_pixels: dict[str, tuple[int, int]] = {}
        self._loc_meta: dict[str, dict] = {}
        for loc in world.get_all_locations():
            lid = loc["id"]
            self._loc_pixels[lid] = _tile_to_pixel(loc["tile_x"], loc["tile_y"])
            self._loc_meta[lid] = loc

        # Build static Text objects for location labels (created once)
        self._loc_labels: list[arcade.Text] = []
        for loc in world.get_all_locations():
            px, py = self._loc_pixels[loc["id"]]
            self._loc_labels.append(
                arcade.Text(
                    _display_label(loc["display_name"]),
                    px,
                    py - ZONE_RADIUS - 6,
                    color=_LABEL_COLOR,
                    font_size=9,
                    anchor_x="center",
                    anchor_y="top",
                    multiline=True,
                    width=140,
                    align="center",
                )
            )

        # Agent positions — initialised from current world state (no animation lag)
        self._agent_cur: dict[str, list[float]] = {}
        tgts = self._compute_agent_targets()
        for name in _AGENT_COLORS:
            tx, ty = tgts.get(name, (WINDOW_W / 2, WINDOW_H / 2))
            self._agent_cur[name] = [tx, ty]

        # Thought-bubble tracking (action string → real-clock stamp of last change)
        self._agent_last_action_seen: dict[str, str] = {}
        self._agent_action_stamp: dict[str, float] = {name: 0.0 for name in _AGENT_COLORS}

        # LLM toggle button bounding box (x1, x2) — used for mouse-click detection
        self._llm_btn: tuple[int, int] = (WINDOW_W - 190, WINDOW_W - 8)

        # Currently inspected agent (None = panel closed)
        self._inspect_agent: str | None = None

    # ------------------------------------------------------------------
    # Update (lerp agent positions)
    # ------------------------------------------------------------------

    def on_update(self, dt: float) -> None:
        factor = min(1.0, dt * LERP_SPEED)
        targets = self._compute_agent_targets()
        now = time.time()
        for name, cur in self._agent_cur.items():
            tx, ty = targets.get(name, (cur[0], cur[1]))
            cur[0] += (tx - cur[0]) * factor
            cur[1] += (ty - cur[1]) * factor

            # Detect new action → reset fade timer
            try:
                new_action = self.world.get_agent_last_action(name)
            except Exception:
                new_action = ""
            if new_action != self._agent_last_action_seen.get(name):
                self._agent_last_action_seen[name] = new_action
                self._agent_action_stamp[name] = now

    def _compute_agent_targets(self) -> dict[str, tuple[float, float]]:
        """Read world state and assign spread-out target pixel positions."""
        by_loc: dict[str, list[str]] = {}
        for name in _AGENT_COLORS:
            try:
                loc_id = self.world.get_agent_location(name)
            except Exception:
                loc_id = "apartment"
            by_loc.setdefault(loc_id, []).append(name)

        targets: dict[str, tuple[float, float]] = {}
        for loc_id, agents in by_loc.items():
            base_px, base_py = self._loc_pixels.get(loc_id, (WINDOW_W / 2, WINDOW_H / 2))
            offsets = _compute_spread(len(agents))
            for i, name in enumerate(sorted(agents)):
                ox, oy = offsets[i]
                targets[name] = (base_px + ox, base_py + oy)
        return targets

    # ------------------------------------------------------------------
    # Draw pipeline
    # ------------------------------------------------------------------

    def on_draw(self) -> None:
        self.clear()
        self._draw_grid()
        self._draw_connections()
        self._draw_zones()
        for label in self._loc_labels:
            label.draw()
        self._draw_agents()
        self._draw_event_log()
        self._draw_hud()
        self._draw_inspect_panel()

    def _draw_grid(self) -> None:
        """Faint tile grid — gives the map a graph-paper feel."""
        for col in range(0, WINDOW_W + 1, TILE_SIZE):
            arcade.draw_line(col, HUD_HEIGHT, col, WINDOW_H, _GRID_COLOR, 1)
        for row in range(HUD_HEIGHT, WINDOW_H + 1, TILE_SIZE):
            arcade.draw_line(0, row, WINDOW_W, row, _GRID_COLOR, 1)

    def _draw_connections(self) -> None:
        """Muted lines between connected locations."""
        drawn: set[frozenset] = set()
        for lid, loc in self._loc_meta.items():
            x1, y1 = self._loc_pixels[lid]
            for nid in loc.get("connected_to", []):
                pair: frozenset = frozenset({lid, nid})
                if pair in drawn or nid not in self._loc_pixels:
                    continue
                drawn.add(pair)
                x2, y2 = self._loc_pixels[nid]
                arcade.draw_line(x1, y1, x2, y2, _CONN_COLOR, 3)

    def _draw_zones(self) -> None:
        """Coloured circles for each location, bordered in white."""
        for lid, loc in self._loc_meta.items():
            px, py = self._loc_pixels[lid]
            rgb = _ZONE_COLORS.get(loc.get("type", "home"), (110, 110, 110))
            arcade.draw_circle_filled(px, py, ZONE_RADIUS, (*rgb, 215))
            arcade.draw_circle_outline(px, py, ZONE_RADIUS, _BORDER_COLOR, 2)

    def _draw_agents(self) -> None:
        """Draw each agent: circle + initials + name tag + fading thought bubble."""
        now = time.time()
        for name, cur in self._agent_cur.items():
            px, py = cur[0], cur[1]
            rgb = _AGENT_COLORS.get(name, (180, 180, 180))
            initials = _AGENT_INITIALS.get(name, name[:2].upper())

            # Drop shadow for legibility
            arcade.draw_circle_filled(px + 2, py - 2, AGENT_RADIUS, (0, 0, 0, 100))
            # Filled circle
            arcade.draw_circle_filled(px, py, AGENT_RADIUS, (*rgb, 235))
            # White border
            arcade.draw_circle_outline(px, py, AGENT_RADIUS, (255, 255, 255, 180), 1)
            # Initials
            arcade.draw_text(
                initials,
                px, py,
                color=(20, 20, 20),
                font_size=7,
                bold=True,
                anchor_x="center",
                anchor_y="center",
            )

            # Name tag above circle — color reflects mood
            try:
                mood = self.world.get_agent(name).get("mood", 65.0)
            except Exception:
                mood = 65.0
            arcade.draw_text(
                name.capitalize(),
                px, py + AGENT_RADIUS + 4,
                color=_name_tag_color(mood),
                font_size=8,
                bold=True,
                anchor_x="center",
                anchor_y="bottom",
            )

            # Thought bubble — fades linearly over BUBBLE_FADE_SECS
            elapsed = now - self._agent_action_stamp.get(name, 0.0)
            alpha = max(0, int(255 * (1.0 - elapsed / _BUBBLE_FADE_SECS)))
            if alpha > 0:
                action_text = self._agent_last_action_seen.get(name, "")
                if action_text:
                    arcade.draw_text(
                        action_text,
                        px, py - AGENT_RADIUS - 4,
                        color=(240, 240, 160, alpha),
                        font_size=7,
                        anchor_x="center",
                        anchor_y="top",
                    )

    def _draw_hud(self) -> None:
        """HUD strip — time, speed controls, LLM toggle button."""
        arcade.draw_lrbt_rectangle_filled(0, WINDOW_W, 0, HUD_HEIGHT, (10, 12, 18))
        arcade.draw_line(0, HUD_HEIGHT, WINDOW_W, HUD_HEIGHT, (50, 55, 80), 1)
        cy = HUD_HEIGHT // 2

        # Time (left)
        try:
            t = self.world.get_time()
            time_label = f"Day {t['day']}  {t['time_str']}"
        except Exception:
            time_label = "Day 1  6:00am"
        arcade.draw_text(time_label, 10, cy,
                         color=(180, 195, 220), font_size=11, bold=True,
                         anchor_x="left", anchor_y="center")

        # Speed controls (center-left)
        paused = self.world._state.get("paused", False)
        speed  = self.world._state.get("speed", 1.0)
        speeds = [0.25, 0.5, 1.0, 2.0, 4.0]
        at_min = abs(speed - speeds[0]) < 0.01
        at_max = abs(speed - speeds[-1]) < 0.01

        _draw_hud_btn(208, 268, cy, "SLOW", disabled=at_min)

        status_bg  = (50, 22, 22) if paused else (20, 24, 40)
        status_clr = (255, 110, 80) if paused else (200, 215, 140)
        arcade.draw_lrbt_rectangle_filled(274, 396, cy - 13, cy + 13, status_bg)
        arcade.draw_lrbt_rectangle_outline(274, 396, cy - 13, cy + 13, (70, 75, 108), 1)
        arcade.draw_text("PAUSED" if paused else f"{speed:.2g}x",
                         335, cy, color=status_clr,
                         font_size=10, bold=True, anchor_x="center", anchor_y="center")

        _draw_hud_btn(402, 462, cy, "FAST", disabled=at_max)

        # Tiny key hint
        arcade.draw_text("SPC / L / ESC", 472, cy, color=(60, 65, 92),
                         font_size=8, anchor_x="left", anchor_y="center")

        # LLM toggle button (right, clickable)
        provider = llm_config.get_primary().upper()
        lx1, lx2 = self._llm_btn
        arcade.draw_lrbt_rectangle_filled(lx1, lx2, cy - 14, cy + 14, (18, 26, 52))
        arcade.draw_lrbt_rectangle_outline(lx1, lx2, cy - 14, cy + 14, (55, 88, 168), 1)
        arcade.draw_text(f"LLM: {provider}", (lx1 + lx2) // 2, cy,
                         color=(95, 148, 240), font_size=10, bold=True,
                         anchor_x="center", anchor_y="center")

    def _draw_event_log(self) -> None:
        """Semi-transparent event log panel in the top-right corner of the map."""
        events = self.world._state.get("events", [])
        recent = events[-_LOG_MAX:]
        if not recent:
            return
        n = len(recent)
        panel_h = n * _LOG_LINE_H + 12
        py_bot  = WINDOW_H - 4 - panel_h
        px_left = _LOG_X - 8

        arcade.draw_lrbt_rectangle_filled(
            px_left, WINDOW_W - 2, py_bot, WINDOW_H - 2, (6, 8, 18, 210))
        arcade.draw_lrbt_rectangle_outline(
            px_left, WINDOW_W - 2, py_bot, WINDOW_H - 2, (32, 38, 62), 1)

        for i, event in enumerate(recent):
            line = _format_event_log_line(event)
            y = py_bot + 6 + i * _LOG_LINE_H
            arcade.draw_text(line, _LOG_X, y, color=(105, 118, 158),
                             font_size=8, anchor_x="left", anchor_y="bottom")

    def _draw_inspect_panel(self) -> None:
        """Right-side panel showing selected agent's needs + last 3 diary entries."""
        name = self._inspect_agent
        if name is None:
            return

        cx = _PANEL_X           # left edge of panel
        mx = cx + 12            # content left margin
        cw = _PANEL_W - 24      # usable content width
        y  = WINDOW_H - 10      # current draw cursor (top → down)

        # Panel background + left border
        arcade.draw_lrbt_rectangle_filled(cx, WINDOW_W, HUD_HEIGHT, WINDOW_H, (7, 9, 20, 238))
        arcade.draw_line(cx, HUD_HEIGHT, cx, WINDOW_H, (48, 54, 82), 2)

        # --- Agent name ---
        y -= 28
        agent_rgb = _AGENT_COLORS.get(name, (180, 180, 180))
        arcade.draw_text(name.upper(), mx, y, color=(*agent_rgb, 255),
                         font_size=16, bold=True, anchor_x="left", anchor_y="center")

        # Location
        y -= 20
        try:
            loc_id = self.world.get_agent_location(name)
            loc_display = self.world.get_location(loc_id).get("display_name", loc_id)
        except Exception:
            loc_display = "Unknown"
        arcade.draw_text(f"@ {loc_display}", mx, y,
                         color=(110, 122, 158), font_size=8,
                         anchor_x="left", anchor_y="center")

        # Separator
        y -= 12
        arcade.draw_line(cx + 6, y, WINDOW_W - 6, y, (42, 48, 72), 1)

        # --- Needs bars ---
        y -= 18
        arcade.draw_text("NEEDS", mx, y, color=(125, 136, 175), font_size=9, bold=True,
                         anchor_x="left", anchor_y="center")
        try:
            ag = self.world.get_agent(name)
            hunger = float(ag.get("hunger", 0))
            energy = float(ag.get("energy", 0))
            mood   = float(ag.get("mood", 0))
        except Exception:
            hunger = energy = mood = 50.0

        bar_x   = mx + 54
        bar_w   = 148
        bar_h   = 6
        for lbl, val, clr in [
            ("Hunger", hunger, (215, 85,  50)),
            ("Energy", energy, (65,  145, 225)),
            ("Mood",   mood,   (75,  195, 105)),
        ]:
            y -= 20
            arcade.draw_text(lbl, mx, y, color=(145, 152, 185), font_size=8,
                             anchor_x="left", anchor_y="center")
            arcade.draw_lrbt_rectangle_filled(bar_x, bar_x + bar_w, y - bar_h, y + bar_h, (26, 28, 44))
            fill = max(0, int(bar_w * val / 100))
            if fill:
                arcade.draw_lrbt_rectangle_filled(bar_x, bar_x + fill, y - bar_h, y + bar_h, clr)
            arcade.draw_text(f"{int(val)}%", bar_x + bar_w + 6, y,
                             color=(95, 105, 138), font_size=8,
                             anchor_x="left", anchor_y="center")

        # Separator
        y -= 14
        arcade.draw_line(cx + 6, y, WINDOW_W - 6, y, (42, 48, 72), 1)

        # --- Diary entries ---
        y -= 18
        arcade.draw_text("DIARY", mx, y, color=(125, 136, 175), font_size=9, bold=True,
                         anchor_x="left", anchor_y="center")

        diary_path = pathlib.Path("agents") / name / "diary.md"
        entries = []
        if diary_path.exists():
            entries = _parse_diary_entries(diary_path.read_text(encoding="utf-8"), n=3)

        if not entries:
            y -= 18
            arcade.draw_text("No diary entries yet.", mx, y,
                             color=(72, 78, 108), font_size=8,
                             anchor_x="left", anchor_y="center")
        else:
            for header, body in entries:
                y -= 18
                arcade.draw_text(header, mx, y, color=(148, 168, 218), font_size=8, bold=True,
                                 anchor_x="left", anchor_y="top")
                y -= 14
                # Cap body length and strip reasoning chains
                display = body[:220].split("\n")[0]   # first paragraph, 220 chars
                arcade.draw_text(display, mx, y, color=(128, 136, 168), font_size=7,
                                 multiline=True, width=cw, anchor_x="left", anchor_y="top")
                lines = max(1, len(display) // 38 + 1)
                y -= lines * 10 + 8

        # Close hint
        arcade.draw_line(cx + 6, HUD_HEIGHT + 22, WINDOW_W - 6, HUD_HEIGHT + 22, (42, 48, 72), 1)
        arcade.draw_text("Click elsewhere or ESC to close",
                         cx + _PANEL_W // 2, HUD_HEIGHT + 11,
                         color=(62, 68, 98), font_size=7,
                         anchor_x="center", anchor_y="center")

    # ------------------------------------------------------------------
    # Input handlers
    # ------------------------------------------------------------------

    def _toggle_llm(self) -> None:
        current = llm_config.get_primary()
        new = "gemini" if current == "ollama" else "ollama"
        try:
            llm_config.set_primary(new)
            logger.info("[window] LLM switched to %s", new)
        except ValueError as exc:
            logger.warning("[window] LLM switch failed: %s", exc)

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        if button == 1:  # left click
            # LLM button in HUD strip
            lx1, lx2 = self._llm_btn
            cy = HUD_HEIGHT // 2
            if lx1 <= x <= lx2 and (cy - 14) <= y <= (cy + 14):
                self._toggle_llm()
                return

            # Agent sprite click (map area only)
            if y > HUD_HEIGHT:
                hit = _agent_hit(self._agent_cur, x, y)
                if hit:
                    self._inspect_agent = hit
                    return
                self._inspect_agent = None   # click elsewhere closes panel

    def on_key_press(self, key: int, modifiers: int) -> None:
        if key == arcade.key.SPACE:
            paused = self.world._state.get("paused", False)
            self.world._state["paused"] = not paused
            logger.info("[window] %s", "paused" if not paused else "resumed")

        elif key == arcade.key.L:
            self._toggle_llm()

        elif key == arcade.key.LEFT:
            speeds = [0.25, 0.5, 1.0, 2.0, 4.0]
            cur = self.world._state.get("speed", 1.0)
            idx = next((i for i, s in enumerate(speeds) if abs(s - cur) < 0.01), 2)
            new = speeds[max(0, idx - 1)]
            self.world._state["speed"] = new
            logger.info("[window] speed -> %.2gx", new)

        elif key == arcade.key.RIGHT:
            speeds = [0.25, 0.5, 1.0, 2.0, 4.0]
            cur = self.world._state.get("speed", 1.0)
            idx = next((i for i, s in enumerate(speeds) if abs(s - cur) < 0.01), 2)
            new = speeds[min(len(speeds) - 1, idx + 1)]
            self.world._state["speed"] = new
            logger.info("[window] speed -> %.2gx", new)

        elif key == arcade.key.ESCAPE:
            if self._inspect_agent is not None:
                self._inspect_agent = None
            else:
                self.close()


# ---------------------------------------------------------------------------
# Background threads
# ---------------------------------------------------------------------------


def _run_sim_thread(world: WorldState) -> None:
    """Run SimulationLoop in its own asyncio event loop (daemon thread)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    sim = SimulationLoop(world)
    try:
        loop.run_until_complete(sim._loop())
    except Exception as exc:
        logger.error("[sim] loop crashed: %s", exc)
    finally:
        loop.close()


def _run_server_thread() -> None:
    """Start the FastAPI/uvicorn web viewer (daemon thread)."""
    import uvicorn
    from server import app
    try:
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
    except OSError as exc:
        logger.warning("[server] Could not bind port 8000: %s — web viewer disabled", exc)


# ---------------------------------------------------------------------------
# Reset (Story 5.2)
# ---------------------------------------------------------------------------


def _parse_default_goals(soul_text: str) -> str:
    """Extract the body of the `# Default Goals` H1 section from a soul.md.

    Returns lines between `# Default Goals` and the next H1/H2 header (or EOF),
    with trailing blank lines stripped. Returns an empty string if no such
    section is present.
    """
    lines = soul_text.splitlines()
    collected: list[str] = []
    in_section = False
    for line in lines:
        if not in_section:
            if line == "# Default Goals":
                in_section = True
            continue
        # Stop on next H1 or H2 header
        if line.startswith("# ") or line.startswith("## "):
            break
        collected.append(line)

    # Strip trailing blank lines
    while collected and collected[-1].strip() == "":
        collected.pop()
    # Strip leading blank lines too for clean output
    while collected and collected[0].strip() == "":
        collected.pop(0)

    return "\n".join(collected)


def _read_state_day(state_path: Path) -> int:
    """Return the `day` field from state.json, or 0 if file missing/unreadable."""
    if not state_path.exists():
        return 0
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return int(data.get("day", 0))
    except (json.JSONDecodeError, OSError, ValueError):
        return 0


def reset_world(
    confirm: bool = True,
    agents_dir: Optional[Path] = None,
    state_path: Optional[Path] = None,
) -> None:
    """Wipe simulation state and per-agent runtime files; re-seed goals.md.

    - Deletes `state.json` (if present).
    - For each of the 10 agents: deletes `memory.md` and `diary.md` (if present),
      and rewrites `goals.md` from the `# Default Goals` section of `soul.md`.
    - Never touches `soul.md`.

    Args:
        confirm: When True (CLI default), prompt the user before proceeding.
                 Tests pass `confirm=False` to skip the input() call.
        agents_dir: Path to the agents/ tree (defaults to `Path("agents")`).
        state_path: Path to world/state.json (defaults to `Path("world/state.json")`).
    """
    agents_dir = agents_dir if agents_dir is not None else Path("agents")
    state_path = state_path if state_path is not None else Path("world") / "state.json"

    days = _read_state_day(state_path)

    if confirm:
        print(
            f"Reset will clear {days} days of history "
            "(memories, diaries, goals, world state). Continue? [y/N] ",
            end="",
            flush=True,
        )
        try:
            answer = input().strip().lower()
        except EOFError:
            answer = ""
        if answer not in {"y", "yes"}:
            print("Aborted.")
            return

    # Delete state.json
    if state_path.exists():
        try:
            state_path.unlink()
        except OSError as exc:
            print(f"[reset] Could not delete {state_path}: {exc}")

    # Reset each agent
    for name in ALL_AGENT_NAMES:
        agent_dir = agents_dir / name
        if not agent_dir.exists():
            print(f"[reset] Agent dir missing: {agent_dir} — skipping")
            continue

        for fname in ("memory.md", "diary.md"):
            target = agent_dir / fname
            if target.exists():
                try:
                    target.unlink()
                except OSError as exc:
                    print(f"[reset] Could not delete {target}: {exc}")

        soul_path = agent_dir / "soul.md"
        goals_path = agent_dir / "goals.md"
        if soul_path.exists():
            soul_text = soul_path.read_text(encoding="utf-8")
            body = _parse_default_goals(soul_text)
            if not body:
                print(
                    f"[reset] Warning: {soul_path} has no `# Default Goals` "
                    "section — writing empty goals.md"
                )
                goals_path.write_text("# Goals\n\n", encoding="utf-8")
            else:
                goals_path.write_text(f"# Goals\n\n{body}\n", encoding="utf-8")
        else:
            print(f"[reset] Warning: {soul_path} missing — writing empty goals.md")
            goals_path.write_text("# Goals\n\n", encoding="utf-8")

    print(
        f"Reset complete. {len(ALL_AGENT_NAMES)} agents reset. "
        "Run `python main.py` to start fresh."
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Gurgaon Town Life simulation")
    parser.add_argument("--reset", action="store_true",
                        help="Reset world state and agent runtime files (preserves soul.md)")
    args = parser.parse_args()

    if args.reset:
        reset_world()
        return

    world = WorldState()
    world.load_or_init()

    threading.Thread(target=_run_server_thread, daemon=True).start()
    threading.Thread(target=_run_sim_thread, args=(world,), daemon=True).start()

    logger.info("[main] Web viewer: http://localhost:8000")
    logger.info("[main] LLM: %s (%s)", llm_config.get_primary(), llm_config.get_model())
    logger.info("[main] Controls: SPACE=pause  L=LLM  ←/→=speed  ESC=quit")

    window = GurgaonWindow(world)
    try:
        arcade.run()
    except KeyboardInterrupt:
        logger.info("[main] interrupted")
    finally:
        logger.info("[main] saving state on exit")
        world.save()


if __name__ == "__main__":
    main()
