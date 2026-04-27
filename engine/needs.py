"""
engine/needs.py — Needs decay system for Gurgaon Town Life simulation.

Every tick (15 game minutes), agent needs decay automatically before the agent
makes any decisions. Hunger creeps up, energy drains, mood shifts based on
recent events. Critical levels inject urgent warning messages into the agent's
context so their decisions respond accordingly.
"""

from engine.tools import world
import asyncio

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HUNGER_PER_HOUR = 8.0      # hunger increases this much per game hour
ENERGY_PER_HOUR = 5.0      # energy decreases this much per game hour
MINUTES_PER_HOUR = 60.0

# Critical thresholds
HUNGER_CRITICAL = 80.0     # above this → urgent
ENERGY_CRITICAL = 20.0     # below this → urgent
MOOD_LOW = 30.0            # below this → social need flagged

# All 10 agent names in the simulation
ALL_AGENTS = [
    "arjun", "priya", "rahul", "kavya", "suresh",
    "neha", "vikram", "deepa", "rohan", "anita",
]


# ---------------------------------------------------------------------------
# Main decay function
# ---------------------------------------------------------------------------

async def decay_needs(agent_name: str, minutes_elapsed: float = 15.0) -> dict:
    """
    Decay an agent's needs for the given number of elapsed game minutes.

    Hunger increases, energy decreases. Mood is adjusted based on recent
    events in the world state (talking, working, eating). All values are
    clamped to [0, 100].

    Parameters
    ----------
    agent_name : str
        The name of the agent whose needs should decay.
    minutes_elapsed : float
        Number of game minutes to simulate. Default is 15 (one tick).

    Returns
    -------
    dict with keys: agent_name, hunger_delta, energy_delta, mood_delta,
    hunger, energy, mood, warnings.
    """
    # Calculate raw deltas
    hunger_delta = (HUNGER_PER_HOUR / MINUTES_PER_HOUR) * minutes_elapsed
    energy_delta = -(ENERGY_PER_HOUR / MINUTES_PER_HOUR) * minutes_elapsed

    # Apply hunger and energy deltas (world clamps to [0, 100])
    await world.update_needs(agent_name, hunger_delta, energy_delta)

    # Read updated agent state
    agent = world.get_agent(agent_name)
    new_hunger = agent["hunger"]
    new_energy = agent["energy"]
    current_mood = agent["mood"]

    # Calculate mood adjustment from recent events (last 5 entries)
    mood_delta = 0.0
    events = world._state.get("events", [])
    recent_events = events[-5:] if len(events) >= 5 else events

    for event in recent_events:
        text = event.get("text", "").lower()
        # Check if this event involves our agent
        if agent_name.lower() not in text:
            continue
        # Talking / receiving a message → mood +3
        if "message" in text or "talked" in text or "talk" in text or "sent" in text:
            mood_delta += 3.0
        # Working → mood -2 (stress)
        if "worked" in text or "work" in text or "earn" in text:
            mood_delta -= 2.0
        # Eating → mood +5
        if "ate" in text or "eat" in text or "food" in text or "hunger" in text:
            mood_delta += 5.0

    # Apply mood delta and clamp to [0, 100]
    new_mood = max(0.0, min(100.0, current_mood + mood_delta))

    # Only update mood if it actually changed
    if mood_delta != 0.0:
        await world.update_agent(agent_name, {"mood": new_mood})
    else:
        new_mood = current_mood

    # Generate warnings based on updated state
    warnings = []
    if new_hunger > 95:
        warnings.append("CRITICAL: Starving")
    elif new_hunger > HUNGER_CRITICAL:
        warnings.append("URGENT: Very hungry — must find food soon")

    if new_energy < 10:
        warnings.append("CRITICAL: About to collapse from exhaustion")
    elif new_energy < ENERGY_CRITICAL:
        warnings.append("URGENT: Exhausted — must rest soon")

    if new_mood < MOOD_LOW:
        warnings.append("Feeling low — consider socializing or taking a break")

    return {
        "agent_name": agent_name,
        "hunger_delta": hunger_delta,
        "energy_delta": energy_delta,
        "mood_delta": mood_delta,
        "hunger": new_hunger,
        "energy": new_energy,
        "mood": new_mood,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Batch decay — all agents concurrently
# ---------------------------------------------------------------------------

async def decay_all_agents(minutes_elapsed: float = 15.0) -> dict[str, dict]:
    """
    Run decay_needs() for all 10 agents concurrently.

    Parameters
    ----------
    minutes_elapsed : float
        Number of game minutes to simulate. Default is 15 (one tick).

    Returns
    -------
    dict of {agent_name: decay_result}
    """
    tasks = [decay_needs(name, minutes_elapsed) for name in ALL_AGENTS]
    results = await asyncio.gather(*tasks)
    return {result["agent_name"]: result for result in results}


# ---------------------------------------------------------------------------
# Context injection helper
# ---------------------------------------------------------------------------

def get_needs_warnings(decay_result: dict) -> str:
    """
    Format the warnings from a decay result into a string suitable for
    injection into an agent's LLM prompt.

    Parameters
    ----------
    decay_result : dict
        A dict as returned by decay_needs().

    Returns
    -------
    str — empty if no warnings, otherwise a formatted warning block.
    """
    warnings = decay_result.get("warnings", [])
    if not warnings:
        return ""
    return "\n=== URGENT NEEDS ===\n" + "\n".join(warnings)


# ---------------------------------------------------------------------------
# Simulate a full day — utility / testing helper
# ---------------------------------------------------------------------------

async def simulate_day_decay(agent_name: str) -> list[dict]:
    """
    Simulate 96 ticks (a full 24-hour game day at 15 min/tick) of decay
    for a single agent without saving state to disk.

    This function calls decay_needs() 96 times and collects the results.
    It does NOT call world.save() — the mutations happen in-memory only.

    Parameters
    ----------
    agent_name : str
        The agent whose needs to simulate.

    Returns
    -------
    list of 96 decay result dicts, one per tick.
    """
    snapshots = []
    for _ in range(96):
        result = await decay_needs(agent_name, minutes_elapsed=15.0)
        snapshots.append(result)
    return snapshots
