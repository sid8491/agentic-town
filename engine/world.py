"""
engine/world.py — WorldState
Single source of truth for the Gurgaon Town Life simulation.

All reads come from the in-memory _state / _map dicts.
All async mutations acquire self._lock before writing.
"""

import asyncio
import json
import logging
import os
import pathlib

logger = logging.getLogger(__name__)


class WorldState:
    """
    Central state object for the simulation.

    Parameters
    ----------
    state_path : str
        Path to world/state.json (relative to the project root, or absolute).
    map_path : str
        Path to world/map.json (relative to the project root, or absolute).
    """

    def __init__(
        self,
        state_path: str = "world/state.json",
        map_path: str = "world/map.json",
    ) -> None:
        self._state_path = state_path
        self._map_path = map_path
        self._state: dict = {}
        self._map: dict = {}
        # Pre-build a location lookup dict after load() is called.
        self._loc_index: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    # Default starting positions / coins for a fresh world (Epic 5)
    _FRESH_AGENTS: dict[str, dict] = {
        "arjun":  {"location": "apartment",   "coins": 150},
        "priya":  {"location": "cyber_city",  "coins": 300},
        "rahul":  {"location": "metro",       "coins": 80},
        "kavya":  {"location": "apartment",   "coins": 120},
        "suresh": {"location": "sector29",    "coins": 200},
        "neha":   {"location": "cyber_hub",   "coins": 180},
        "vikram": {"location": "park",        "coins": 160},
        "deepa":  {"location": "apartment",   "coins": 130},
        "rohan":  {"location": "dhaba",       "coins": 40},
        "anita":  {"location": "sector29",    "coins": 250},
    }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_map_file(self) -> None:
        """Load map.json and rebuild the location index."""
        with open(self._map_path, "r", encoding="utf-8") as f:
            self._map = json.load(f)
        self._loc_index = {loc["id"]: loc for loc in self._map["locations"]}

    def load(self) -> None:
        """Load state and map JSON files into memory."""
        with open(self._state_path, "r", encoding="utf-8") as f:
            self._state = json.load(f)
        self._load_map_file()

    def _build_fresh_state(self) -> None:
        """Populate self._state with clean Day-1 defaults for all agents."""
        agents = {
            name: {
                "location":         defaults["location"],
                "hunger":           20.0,
                "energy":           90.0,
                "mood":             65.0,
                "coins":            defaults["coins"],
                "inventory":        [],
                "inbox":            [],
                "last_action":      "waking up",
                "last_action_time": 360,
            }
            for name, defaults in self._FRESH_AGENTS.items()
        }
        self._state = {
            "sim_time":    360,
            "day":         1,
            "paused":      False,
            "speed":       1.0,
            "llm_primary": "ollama",
            "events":      [],
            "daily_events": [],
            "agents":      agents,
        }

    def load_or_init(self) -> None:
        """Load state.json if it exists; otherwise build fresh defaults and save."""
        self._load_map_file()
        if os.path.exists(self._state_path):
            with open(self._state_path, "r", encoding="utf-8") as f:
                self._state = json.load(f)
            logger.info("[world] loaded %s", self._state_path)
        else:
            self._build_fresh_state()
            self._write_state()
            logger.info("[world] initialised fresh state at %s", self._state_path)

    def _write_state(self) -> None:
        """Write the current in-memory state back to disk (pretty-printed).

        Internal helper shared by both save() and save_async().
        Callers are responsible for holding the lock when needed.

        Keys starting with ``_`` (such as ``_pending_summary``) are excluded
        from the saved JSON so they never pollute state.json.
        """
        state_copy = {k: v for k, v in self._state.items() if not k.startswith("_")}
        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(state_copy, f, indent=2)

    def save(self) -> None:
        """Write the current in-memory state back to disk (sync, no lock)."""
        self._write_state()

    async def save_async(self) -> None:
        """Asyncio-safe save — acquires the lock before writing."""
        async with self._lock:
            self._write_state()

    # ------------------------------------------------------------------
    # Time helpers
    # ------------------------------------------------------------------

    def time_to_str(self, sim_time: int) -> str:
        """
        Convert simulation time (minutes since midnight) to a human-readable
        string such as "6:30am" or "1:00pm".

        Examples
        --------
        0    → "12:00am"
        360  → "6:00am"
        390  → "6:30am"
        720  → "12:00pm"
        780  → "1:00pm"
        1380 → "11:00pm"
        """
        sim_time = sim_time % 1440  # guard against values >= 1440
        hour24 = sim_time // 60
        minute = sim_time % 60
        suffix = "am" if hour24 < 12 else "pm"
        hour12 = hour24 % 12
        if hour12 == 0:
            hour12 = 12
        return f"{hour12}:{minute:02d}{suffix}"

    def get_time(self) -> dict:
        """
        Return the current simulation time as a dict.

        Returns
        -------
        {
            "day": int,
            "sim_time": int,       # minutes since midnight
            "time_str": "6:30am",
            "paused": bool,
        }
        """
        return {
            "day": self._state["day"],
            "sim_time": self._state["sim_time"],
            "time_str": self.time_to_str(self._state["sim_time"]),
            "paused": self._state["paused"],
        }

    def advance_time(self, minutes: int) -> None:
        """
        Advance sim_time by *minutes*.

        Handles day rollover: if sim_time reaches 1440 (midnight) or beyond,
        the day counter increments and sim_time wraps to the remainder.
        """
        self._state["sim_time"] += minutes
        if self._state["sim_time"] >= 1440:
            self._state["day"] += 1
            self._state["sim_time"] %= 1440

    # ------------------------------------------------------------------
    # Agent queries
    # ------------------------------------------------------------------

    def get_agent(self, name: str) -> dict:
        """Return the agent dict for *name* (raises KeyError if absent)."""
        return self._state["agents"][name]

    def get_all_agents(self) -> dict:
        """Return the full agents dict (name → agent_dict)."""
        return self._state["agents"]

    def get_agent_location(self, name: str) -> str:
        """Return the location id where *name* currently is."""
        return self._state["agents"][name]["location"]

    def get_agent_last_action(self, name: str) -> str:
        """Return the last-action label for *name* (empty string if absent)."""
        return self._state["agents"][name].get("last_action", "")

    def get_nearby_agents(self, name: str) -> list[str]:
        """
        Return the names of all agents sharing *name*'s current location,
        excluding *name* itself.
        """
        my_loc = self.get_agent_location(name)
        return [
            agent_name
            for agent_name, agent in self._state["agents"].items()
            if agent_name != name and agent["location"] == my_loc
        ]

    # ------------------------------------------------------------------
    # Agent mutations  (all async, all acquire self._lock)
    # ------------------------------------------------------------------

    async def update_agent(self, name: str, updates: dict) -> None:
        """Merge *updates* into the agent dict for *name*."""
        async with self._lock:
            self._state["agents"][name].update(updates)

    async def set_agent_last_action(self, name: str, label: str) -> None:
        """Record a human-readable action label for *name* (used by renderer)."""
        async with self._lock:
            self._state["agents"][name]["last_action"] = label

    async def move_agent(self, name: str, location: str) -> bool:
        """
        Move *name* to *location*.

        Validation rules
        ----------------
        1. *location* must exist in the map.
        2. *location* must be in the agent's current location's ``connected_to``
           list.  Exception: if the agent's current location id is not found in
           the map index (e.g. agent starts at an unknown location), allow the
           move so that agents can always be bootstrapped to valid nodes.

        Returns True on success, False if validation fails.
        """
        # Destination must exist in the map
        if location not in self._loc_index:
            return False

        async with self._lock:
            current_loc_id = self._state["agents"][name]["location"]
            current_loc = self._loc_index.get(current_loc_id)

            # If the current location is not in the map, allow move (bootstrap case)
            if current_loc is None:
                self._state["agents"][name]["location"] = location
                return True

            # Destination must be reachable from current location
            if location not in current_loc.get("connected_to", []):
                return False

            self._state["agents"][name]["location"] = location
            return True

    async def update_needs(
        self, name: str, hunger_delta: float, energy_delta: float
    ) -> None:
        """
        Apply *hunger_delta* and *energy_delta* to the agent, clamping both
        resulting values to [0, 100].
        """
        async with self._lock:
            agent = self._state["agents"][name]
            agent["hunger"] = max(0.0, min(100.0, agent["hunger"] + hunger_delta))
            agent["energy"] = max(0.0, min(100.0, agent["energy"] + energy_delta))

    async def add_to_inbox(self, name: str, message: dict) -> None:
        """Append *message* to the agent's inbox list."""
        async with self._lock:
            self._state["agents"][name]["inbox"].append(message)

    async def add_conversation(self, sender: str, recipient: str, message: str) -> None:
        """Persist a talk_to message in the rolling conversation log (last 300)."""
        async with self._lock:
            if "conversations" not in self._state:
                self._state["conversations"] = []
            ts = f"{self.time_to_str(self._state['sim_time'])} Day {self._state['day']}"
            self._state["conversations"].append({
                "from": sender,
                "to": recipient,
                "text": message,
                "time": ts,
                "sim_time": self._state["sim_time"],
                "day": self._state["day"],
            })
            if len(self._state["conversations"]) > 300:
                self._state["conversations"] = self._state["conversations"][-300:]

    async def clear_inbox(self, name: str) -> list:
        """Return fresh messages in *name*'s inbox, then clear it.

        Messages older than 2 game hours (120 sim_minutes) are silently
        discarded so stale gossip never pollutes an agent's context.
        """
        _MAX_AGE_MINUTES = 120
        async with self._lock:
            current_abs = self._state["day"] * 1440 + self._state["sim_time"]
            fresh = []
            for msg in self._state["agents"][name]["inbox"]:
                msg_day = msg.get("day", self._state["day"])
                msg_sim = msg.get("sim_time", self._state["sim_time"])
                msg_abs = msg_day * 1440 + msg_sim
                if current_abs - msg_abs <= _MAX_AGE_MINUTES:
                    fresh.append(msg)
            self._state["agents"][name]["inbox"] = []
            return fresh

    async def add_event(self, event: str) -> None:
        """
        Append an event to state["events"].

        Format: {"time": "6:30am Day 1", "text": event_string}
        """
        async with self._lock:
            timestamp = f"{self.time_to_str(self._state['sim_time'])} Day {self._state['day']}"
            self._state["events"].append({"time": timestamp, "text": event})

    # ------------------------------------------------------------------
    # Map queries
    # ------------------------------------------------------------------

    def get_location(self, location_id: str) -> dict:
        """Return the location dict for *location_id* (raises KeyError if absent)."""
        return self._loc_index[location_id]

    def get_all_locations(self) -> list:
        """Return the list of all location dicts."""
        return self._map["locations"]

    def get_connected_locations(self, location_id: str) -> list[str]:
        """Return the list of location ids connected to *location_id*."""
        return self._loc_index[location_id].get("connected_to", [])

    def location_has_service(self, location_id: str, service: str) -> bool:
        """Return True if *location_id* offers *service*."""
        loc = self._loc_index.get(location_id)
        if loc is None:
            return False
        return service in loc.get("services", [])

    # ------------------------------------------------------------------
    # Simulation control
    # ------------------------------------------------------------------

    async def set_paused(self, paused: bool) -> None:
        """Pause or unpause the simulation."""
        async with self._lock:
            self._state["paused"] = paused

    async def set_speed(self, speed: float) -> None:
        """Set the simulation speed multiplier."""
        async with self._lock:
            self._state["speed"] = speed

    async def set_llm_primary(self, provider: str) -> None:
        """Set the primary LLM provider (e.g. 'ollama', 'gemini')."""
        async with self._lock:
            self._state["llm_primary"] = provider

    # ------------------------------------------------------------------
    # Daily summary (Story 7.2)
    # ------------------------------------------------------------------

    def set_daily_summary(self, summary: str, day: int) -> None:
        """Store a completed day's summary for the Arcade renderer to pick up.

        Stored under ``_pending_summary`` (underscore prefix = excluded from
        state.json by ``_write_state``).  GIL-safe for cross-thread use.
        """
        self._state["_pending_summary"] = {"text": summary, "day": day}

    def pop_daily_summary(self) -> dict | None:
        """Return and clear the pending daily summary, or None if absent.

        Called from the Arcade main thread each frame; safe under the GIL.
        """
        return self._state.pop("_pending_summary", None)


# ---------------------------------------------------------------------------
# SimulationLoop
# ---------------------------------------------------------------------------


class SimulationLoop:
    """
    Runs the autonomous tick loop for the full Gurgaon Town Life simulation.

    Each tick:
      1. Check if paused — if so, sleep and retry
      2. Advance sim time by 15 game minutes
      3. Decay all agents' needs
      4. Run all 10 agents concurrently (asyncio.gather)
      5. Save world state
      6. Sleep for tick_interval real seconds

    Tick interval = 3.0 / speed_multiplier
    """

    AGENTS = ["arjun", "priya", "rahul", "kavya", "suresh",
              "neha", "vikram", "deepa", "rohan", "anita"]
    TICK_MINUTES = 15      # game minutes advanced per tick
    BASE_INTERVAL = 3.0    # real seconds per tick at 1x speed

    def __init__(self, world: WorldState) -> None:
        self.world = world
        self._running = False
        self._task: asyncio.Task | None = None
        self._runners: dict = {}   # populated lazily on first run

        # Wire all engine modules to the shared WorldState instance so that
        # tool calls, needs decay, and agent decisions all mutate the same
        # object that the Arcade renderer reads. Must happen before any
        # engine module creates its own WorldState at module level.
        import engine.tools as _tools
        _tools.world = world
        import engine.needs as _needs
        _needs.world = world
        import engine.agent as _agent
        _agent.world = world

    def _get_runner(self, agent_name: str):
        """Lazily import and create AgentRunner to avoid circular imports."""
        if agent_name not in self._runners:
            from engine.agent import AgentRunner
            self._runners[agent_name] = AgentRunner(agent_name)
        return self._runners[agent_name]

    async def _run_agent_safe(self, agent_name: str) -> None:
        """Run one agent tick, catching and logging any exception."""
        try:
            runner = self._get_runner(agent_name)
            await runner.tick()
        except Exception as exc:
            logger.error("[loop] agent %s tick failed: %s", agent_name, exc)

    async def _tick(self) -> None:
        """Execute one full simulation tick."""
        time_info = self.world.get_time()
        logger.info(
            "[loop] tick — Day %d %s | speed=%.1fx",
            time_info["day"],
            time_info["time_str"],
            self.world._state.get("speed", 1.0),
        )

        # 1. Advance game time (detect day rollover for daily summary)
        old_day = self.world._state["day"]
        self.world.advance_time(self.TICK_MINUTES)
        new_day = self.world._state["day"]
        if new_day != old_day:
            asyncio.create_task(self._generate_daily_summary(old_day))

        # 2. Decay all agent needs
        from engine.needs import decay_all_agents
        await decay_all_agents(self.TICK_MINUTES)

        # 3. Run all agents concurrently
        await asyncio.gather(*[
            self._run_agent_safe(name) for name in self.AGENTS
        ])

        # 4. Save world state
        await self.world.save_async()

        # 5. Auto-speed: fast-forward through quiet night periods
        sleeping_count = sum(
            1 for name in self.AGENTS
            if "sleep" in self.world.get_agent_last_action(name).lower()
        )
        current_speed = self.world._state.get("speed", 1.0)
        if sleeping_count >= 7 and current_speed < 4.0:
            await self.world.set_speed(4.0)
            logger.info(
                "[loop] auto-speed UP: %d/10 sleeping → 4x", sleeping_count
            )
        elif sleeping_count < 5 and current_speed >= 4.0:
            await self.world.set_speed(1.0)
            logger.info(
                "[loop] auto-speed DOWN: only %d sleeping → 1x", sleeping_count
            )

    async def _generate_daily_summary(
        self,
        completed_day: int,
        output_dir: pathlib.Path | None = None,
    ) -> None:
        """Generate a narrative summary of the completed day via LLM.

        Saves to ``world/daily_log_day_{completed_day}.txt`` (or *output_dir*
        if provided, for testing).  Also signals the Arcade renderer by calling
        ``world.set_daily_summary()``.
        """
        from engine.llm import call_llm

        events = self.world._state.get("events", [])
        if not events:
            return

        # Use last 60 events
        recent = events[-60:]
        events_text = "\n".join(f"- [{e['time']}] {e['text']}" for e in recent)
        prompt = (
            f"Day {completed_day} of Gurgaon Town Life has ended.\n\n"
            f"Here are the key events:\n{events_text}\n\n"
            "Write a 3-5 sentence narrative summary of the day as if you were a journalist "
            "writing about this small community. Be specific about who did what, and note any "
            "interesting interactions or patterns. Keep it warm and human."
        )

        try:
            response = await call_llm(
                prompt,
                system="You are a journalist summarising a day in a small Gurgaon community.",
                max_tokens=300,
                thinking=False,
            )
            summary = response.text or f"Day {completed_day}: events recorded."
        except Exception as exc:
            logger.warning("[loop] daily summary failed: %s", exc)
            summary = f"Day {completed_day}: {len(events)} events recorded."

        # Save to file
        save_dir = output_dir if output_dir is not None else pathlib.Path("world")
        log_path = save_dir / f"daily_log_day_{completed_day}.txt"
        try:
            log_path.write_text(summary, encoding="utf-8")
            logger.info("[loop] daily summary saved to %s", log_path)
        except Exception as exc:
            logger.warning("[loop] could not write summary: %s", exc)

        # Signal the Arcade renderer to display the modal
        self.world.set_daily_summary(summary, completed_day)

    async def _autosave_loop(self) -> None:
        """Save world state every 5 real seconds, independent of tick timing."""
        _INTERVAL = 5.0
        while True:
            await asyncio.sleep(_INTERVAL)
            try:
                await self.world.save_async()
                logger.debug("[loop] autosaved")
            except Exception as exc:
                logger.warning("[loop] autosave failed: %s", exc)

    async def _loop(self) -> None:
        """Main loop — runs until self._running is False."""
        self._running = True
        logger.info("[loop] simulation started")
        autosave = asyncio.create_task(self._autosave_loop())
        try:
            while self._running:
                paused = self.world._state.get("paused", False)
                if paused:
                    await asyncio.sleep(0.5)
                    continue

                await self._tick()

                speed = self.world._state.get("speed", 1.0)
                interval = self.BASE_INTERVAL / max(speed, 0.1)
                await asyncio.sleep(interval)
        finally:
            autosave.cancel()

        logger.info("[loop] simulation stopped")

    def start(self) -> asyncio.Task:
        """Start the loop as a background asyncio task. Returns the task."""
        if self._task and not self._task.done():
            return self._task
        self._task = asyncio.create_task(self._loop())
        return self._task

    def stop(self) -> None:
        """Signal the loop to stop after the current tick completes."""
        self._running = False
        if self._task:
            self._task.cancel()

    @property
    def running(self) -> bool:
        return self._running and bool(self._task) and not self._task.done()
