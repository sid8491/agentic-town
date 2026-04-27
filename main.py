"""
main.py — Entry point for Gurgaon Town Life simulation.

Story 2.2 stub: starts the FastAPI server in a background thread and prints
status.  The full Arcade renderer arrives in Epic 4; this file lays the
groundwork by reserving the Arcade key-handler TODO and the threading pattern.

Usage
-----
    python main.py            # normal start
    python main.py --reset    # (not yet implemented — Epic 5)
    python main.py --reset-all
"""

import argparse
import threading

import uvicorn

from engine.llm import llm_config
from server import app


def start_server() -> None:
    """Run the FastAPI / uvicorn server (blocking call, intended for a daemon thread)."""
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gurgaon Town Life simulation")
    parser.add_argument("--reset", action="store_true", help="Reset agent state (Epic 5)")
    parser.add_argument("--reset-all", action="store_true", help="Full world reset (Epic 5)")
    args = parser.parse_args()

    if args.reset or getattr(args, "reset_all", False):
        print("[main] Reset not yet implemented — coming in Epic 5")
        return

    # Start FastAPI in background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    print(f"[main] Web viewer: http://localhost:8000")
    print(f"[main] LLM: {llm_config.get_primary()} ({llm_config.get_model()})")
    print(f"[main] Arcade renderer coming in Epic 4. Press Ctrl+C to stop.")

    # TODO Epic 4: start Arcade window here
    # TODO Epic 4: on key 'L' → llm_config.set_primary("gemini" if current == "ollama" else "ollama")

    try:
        threading.Event().wait()  # block until Ctrl+C
    except KeyboardInterrupt:
        print("\n[main] Shutting down.")


if __name__ == "__main__":
    main()
