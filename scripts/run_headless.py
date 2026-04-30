"""Run SimulationLoop + FastAPI server with no Arcade window.

Usage:
    .venv/Scripts/python.exe scripts/run_headless.py [--speed N]

The Arcade renderer is not started — useful for headless smoke runs,
CI, or letting the web viewer drive the experience.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402

from engine.world import SimulationLoop, WorldState  # noqa: E402
import server  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("run_headless")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--speed", type=float, default=1.0,
                        help="Simulation speed multiplier (0.25, 0.5, 1.0, 2.0, 4.0). Default 1.0.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--lock-speed", action="store_true",
                        help="Pin the speed against drama auto-pacing.")
    args = parser.parse_args()

    ws = WorldState()
    ws.load_or_init()
    ws._state["speed"] = args.speed
    if args.lock_speed:
        ws._state["_speed_locked"] = True
    ws.save()
    server.set_world(ws)

    # Start uvicorn on a daemon thread so it shuts down with main.
    config = uvicorn.Config(server.app, host="127.0.0.1", port=args.port, log_level="warning")
    srv = uvicorn.Server(config)
    threading.Thread(target=srv.run, daemon=True).start()
    logger.info("server up at http://127.0.0.1:%d  speed=%sx", args.port, args.speed)

    # Run the SimulationLoop in the main thread's event loop.
    loop = SimulationLoop(ws)
    try:
        asyncio.run(loop._loop())
    except KeyboardInterrupt:
        logger.info("shutting down")


if __name__ == "__main__":
    main()
