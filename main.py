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
import logging
import math
import threading

import arcade

from engine.llm import llm_config
from engine.world import WorldState, SimulationLoop

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

    # ------------------------------------------------------------------
    # Update (lerp agent positions)
    # ------------------------------------------------------------------

    def on_update(self, dt: float) -> None:
        factor = min(1.0, dt * LERP_SPEED)
        targets = self._compute_agent_targets()
        for name, cur in self._agent_cur.items():
            tx, ty = targets.get(name, (cur[0], cur[1]))
            cur[0] += (tx - cur[0]) * factor
            cur[1] += (ty - cur[1]) * factor

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
        self._draw_hud()

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
        """Draw each agent as a coloured circle with two-letter initials."""
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

    def _draw_hud(self) -> None:
        """Minimal HUD strip at the bottom (fully fleshed out in Story 4.4)."""
        # Background bar
        arcade.draw_lrbt_rectangle_filled(0, WINDOW_W, 0, HUD_HEIGHT, (10, 12, 18))
        arcade.draw_line(0, HUD_HEIGHT, WINDOW_W, HUD_HEIGHT, (50, 55, 80), 1)

        # Sim time + day
        try:
            t = self.world.get_time()
            time_label = f"Day {t['day']}  {t['time_str']}"
        except Exception:
            time_label = "Day 1  6:00am"

        paused = self.world._state.get("paused", False)
        speed = self.world._state.get("speed", 1.0)
        provider = llm_config.get_primary().upper()

        hud_text = (
            f"{time_label}    "
            f"{'[PAUSED]' if paused else f'{speed:.2g}x'}    "
            f"LLM: {provider}    "
            "SPACE=pause  L=LLM  ←/→=speed  ESC=quit"
        )
        arcade.draw_text(
            hud_text,
            10, HUD_HEIGHT // 2,
            color=(160, 165, 185),
            font_size=10,
            anchor_x="left",
            anchor_y="center",
        )

    # ------------------------------------------------------------------
    # Key input
    # ------------------------------------------------------------------

    def on_key_press(self, key: int, modifiers: int) -> None:
        if key == arcade.key.SPACE:
            paused = self.world._state.get("paused", False)
            self.world._state["paused"] = not paused
            logger.info("[window] %s", "paused" if not paused else "resumed")

        elif key == arcade.key.L:
            current = llm_config.get_primary()
            new = "gemini" if current == "ollama" else "ollama"
            try:
                llm_config.set_primary(new)
                logger.info("[window] LLM switched to %s", new)
            except ValueError as exc:
                logger.warning("[window] LLM switch failed: %s", exc)

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
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Gurgaon Town Life simulation")
    parser.add_argument("--reset", action="store_true",
                        help="Reset agent state — Epic 5")
    parser.add_argument("--reset-all", dest="reset_all", action="store_true",
                        help="Full factory reset — Epic 5")
    args = parser.parse_args()

    if args.reset or args.reset_all:
        print("[main] Reset not yet implemented — coming in Epic 5")
        return

    world = WorldState()
    world.load()

    threading.Thread(target=_run_server_thread, daemon=True).start()
    threading.Thread(target=_run_sim_thread, args=(world,), daemon=True).start()

    logger.info("[main] Web viewer: http://localhost:8000")
    logger.info("[main] LLM: %s (%s)", llm_config.get_primary(), llm_config.get_model())
    logger.info("[main] Controls: SPACE=pause  L=LLM  ←/→=speed  ESC=quit")

    window = GurgaonWindow(world)
    arcade.run()


if __name__ == "__main__":
    main()
