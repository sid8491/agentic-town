"""
engine/world.py — WorldState
Single source of truth for the Gurgaon Town Life simulation.

All reads come from the in-memory _state / _map dicts.
All async mutations acquire self._lock before writing.
"""

import asyncio
import json
import os


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

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load state and map JSON files into memory."""
        with open(self._state_path, "r", encoding="utf-8") as f:
            self._state = json.load(f)
        with open(self._map_path, "r", encoding="utf-8") as f:
            self._map = json.load(f)
        # Build fast location lookup
        self._loc_index = {loc["id"]: loc for loc in self._map["locations"]}

    def save(self) -> None:
        """Write the current in-memory state back to disk (pretty-printed)."""
        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2)

    async def save_async(self) -> None:
        """asyncio-safe save: acquires lock then delegates to save()."""
        async with self._lock:
            self.save()

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

    async def clear_inbox(self, name: str) -> list:
        """Return all messages in *name*'s inbox, then clear it."""
        async with self._lock:
            messages = list(self._state["agents"][name]["inbox"])
            self._state["agents"][name]["inbox"] = []
            return messages

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
