"""
Live smoke test: 1 tick of SimulationLoop with real Ollama calls.
Runs a single _tick() directly — no background task, no cancel.
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

from engine.world import WorldState, SimulationLoop

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

async def main():
    ws = WorldState(
        state_path=os.path.join(ROOT, "world/state.json"),
        map_path=os.path.join(ROOT, "world/map.json"),
    )
    ws.load()
    loop = SimulationLoop(ws)

    print("\n" + "=" * 60)
    before = ws.get_time()
    print(f"Before: Day {before['day']}  {before['time_str']}  (sim_time={before['sim_time']})")
    print("Running one tick (real LLM calls)...")
    print("=" * 60)

    await loop._tick()

    after = ws.get_time()
    print("\n" + "=" * 60)
    print(f"After:  Day {after['day']}  {after['time_str']}  (sim_time={after['sim_time']})")
    print("=" * 60)

    # Show each agent's last diary line
    agents = SimulationLoop.AGENTS
    print("\nDiary snippets:")
    for name in agents:
        diary_path = os.path.join(ROOT, f"agents/{name}/diary.md")
        if os.path.exists(diary_path):
            with open(diary_path, encoding="utf-8") as f:
                lines = [l.strip() for l in f.readlines() if l.strip()]
            last = lines[-1] if lines else "(empty)"
            print(f"  {name:10s}: {last[:80]}")
        else:
            print(f"  {name:10s}: (no diary)")

    print("\nSMOKE TEST PASSED")

asyncio.run(main())
