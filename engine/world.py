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
import time

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Story 10.5 — Drama-driven auto-pacing
# ---------------------------------------------------------------------------

# Lookback window (in ticks) for counting talk_to / conflict events.
_DRAMA_EVENT_WINDOW_TICKS = 4
# Game-minute threshold for "imminent" shared plans.
_DRAMA_PLAN_HORIZON_MIN = 30
# Real-time dwell required at score <=2 before fast-forwarding to 4x.
# Real seconds (monotonic), NOT sim_time: we want fast-forward to kick in
# only after a sustained quiet stretch in *observer* time, regardless of
# whatever speed the sim is currently running at.
_DRAMA_QUIET_DWELL_SECONDS = 60.0


def compute_drama_score(world_state: dict, now_monotonic: float | None = None) -> float:
    """Compute an unbounded drama score for the current world snapshot.

    Components (additive):
      * +5 per `talk_to` event in the last 4 ticks
      * +8 per `conflict:` event in the last 4 ticks (Story 9.3)
      * +10 per pending/confirmed shared plan starting in <30 game minutes
      * +3 per agent with mood < 30 or > 75
      * +2 per agent currently in motion (last_action starts with "moving")
    """
    score = 0.0

    events = world_state.get("events", [])
    agents = world_state.get("agents", {})
    # Approximate "last 4 ticks" by scanning the tail of the events list:
    # each tick yields up to ~len(agents) events (one tool call per agent).
    n_agents = max(len(agents), 1)
    tail = events[-(_DRAMA_EVENT_WINDOW_TICKS * n_agents):]
    for ev in tail:
        text = ev.get("text", "")
        if " says to " in text:
            score += 5
        if text.startswith("conflict:"):
            score += 8

    plans = world_state.get("shared_plans", [])
    sim_time = world_state.get("sim_time", 0)
    day = world_state.get("day", 0)
    current_abs = day * 1440 + sim_time
    for plan in plans:
        if plan.get("status") not in ("pending", "confirmed"):
            continue
        target_time = plan.get("target_time", 0)
        delta = target_time - current_abs
        if 0 <= delta < _DRAMA_PLAN_HORIZON_MIN:
            score += 10

    for agent in agents.values():
        mood = agent.get("mood", 50)
        if mood < 30 or mood > 75:
            score += 3
        last_action = (agent.get("last_action") or "").lower()
        if last_action.startswith("moving"):
            score += 2

    return score


def pick_speed(
    score: float,
    sleeping_count: int,
    locked: bool,
    low_score_since: float | None,
    now_monotonic: float | None = None,
) -> tuple[float, str | None]:
    """Choose the auto-pacing speed for the next tick.

    Returns ``(speed, label)`` where ``label`` is None if no pacing label
    should be displayed.

    Precedence: manual lock > night auto-speed > drama brackets.
      * locked              → 1.0, None  (caller usually skips this entirely)
      * sleeping_count >=7  → 4.0, None
      * score >= 15         → 1.0, None  ("live")
      * score 8-14          → 1.0, None  (default)
      * score 3-7           → 2.0, "⏩ quiet stretch"
      * score 0-2 sustained → 4.0, "⏩⏩ skipping ahead" (after dwell)
      * score 0-2 fresh     → 1.0, None  (waiting on dwell)
    """
    if locked:
        return 1.0, None

    if sleeping_count >= 7:
        return 4.0, None

    if score >= 15:
        return 1.0, None
    if score >= 8:
        return 1.0, None
    if score >= 3:
        return 2.0, "⏩ quiet stretch"
    if (
        low_score_since is not None
        and now_monotonic is not None
        and (now_monotonic - low_score_since) >= _DRAMA_QUIET_DWELL_SECONDS
    ):
        return 4.0, "⏩⏩ skipping ahead"
    return 1.0, None


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
        scheduled_events_path: str = "world/scheduled_events.json",
    ) -> None:
        self._state_path = state_path
        self._map_path = map_path
        # --- Story 9.8 BEGIN ---
        self._scheduled_events_path = scheduled_events_path
        self._scheduled_events: list[dict] = []
        # --- Story 9.8 END ---
        self._state: dict = {}
        self._map: dict = {}
        # Pre-build a location lookup dict after load() is called.
        self._loc_index: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    # Default starting positions / coins / monthly_rent for a fresh world.
    # Rents per archetype (Story 9.4): office_worker 60, vendor 25,
    # retired 40, student 20, entrepreneur 50, homemaker 0, night_owl 35.
    # Starting balances tuned to create baseline economic inequality:
    # Rohan/Rahul/Deepa/Anita start tight (~1–1.5x rent);
    # Vikram/Priya start comfortable (~3–4x rent).
    _FRESH_AGENTS: dict[str, dict] = {
        "arjun":  {"location": "apartment",   "coins": 150, "monthly_rent": 60, "last_consolidation_day": 0},
        "priya":  {"location": "cyber_city",  "coins": 240, "monthly_rent": 60, "last_consolidation_day": 0},
        "rahul":  {"location": "metro",       "coins": 50,  "monthly_rent": 35, "last_consolidation_day": 0},
        "kavya":  {"location": "apartment",   "coins": 60,  "monthly_rent": 20, "last_consolidation_day": 0},
        "suresh": {"location": "sector29",    "coins": 100, "monthly_rent": 25, "last_consolidation_day": 0},
        "neha":   {"location": "cyber_hub",   "coins": 180, "monthly_rent": 60, "last_consolidation_day": 0},
        "vikram": {"location": "park",        "coins": 160, "monthly_rent": 40, "last_consolidation_day": 0},
        "deepa":  {"location": "apartment",   "coins": 0,   "monthly_rent": 0,  "last_consolidation_day": 0},
        "rohan":  {"location": "dhaba",       "coins": 50,  "monthly_rent": 35, "last_consolidation_day": 0},
        "anita":  {"location": "sector29",    "coins": 60,  "monthly_rent": 50, "last_consolidation_day": 0},
    }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_map_file(self) -> None:
        """Load map.json and rebuild the location index."""
        with open(self._map_path, "r", encoding="utf-8") as f:
            self._map = json.load(f)
        self._loc_index = {loc["id"]: loc for loc in self._map["locations"]}
        # --- Story 9.8 BEGIN: load authored scheduled events alongside map ---
        self._load_scheduled_events()
        # --- Story 9.8 END ---

    # --- Story 9.8 BEGIN: scheduled external events --------------------
    # Outdoor location types — used by tools.move_to to apply a small mood
    # penalty on monsoon days. "transit" + "social" + "leisure" cover the
    # locations that feel exposed to weather (metro, sector29, cyber_hub, park).
    _OUTDOOR_LOCATION_TYPES = {"transit", "social", "leisure"}

    def _load_scheduled_events(self) -> None:
        """Load world/scheduled_events.json if present.

        Authored content (like map.json) — survives --reset. Missing or
        malformed file is treated as "no scheduled events" rather than fatal.
        """
        try:
            with open(self._scheduled_events_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            events = payload.get("events", [])
            if isinstance(events, list):
                self._scheduled_events = events
            else:
                self._scheduled_events = []
        except FileNotFoundError:
            self._scheduled_events = []
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "[world] could not load scheduled events: %s", exc
            )
            self._scheduled_events = []

    def _event_matches_agent(
        self,
        event: dict,
        agent_name: str,
        archetype: str,
    ) -> bool:
        """Return True if *event*'s affected_agents spec matches this agent."""
        spec = event.get("affected_agents")
        if spec is None:
            return False
        if isinstance(spec, str):
            if spec == "all":
                return True
            if spec.startswith("archetype:"):
                allowed = {a.strip() for a in spec[len("archetype:"):].split(",") if a.strip()}
                return archetype in allowed
            # Fallback: bare string is a single agent name
            return spec == agent_name
        if isinstance(spec, list):
            return agent_name in spec
        return False

    def get_active_events_for(
        self,
        agent_name: str,
        archetype: str,
        current_day: int,
        current_sim_time: int,
    ) -> list[dict]:
        """Return scheduled events currently in effect for this agent.

        An event is active when:
          * event["day"] == current_day, AND
          * (current_sim_time // 60) ∈ [start_hour, end_hour), AND
          * affected_agents matches by "all" / "archetype:..." / list of names.
        """
        if not self._scheduled_events:
            return []
        current_hour = (current_sim_time % 1440) // 60
        active: list[dict] = []
        for event in self._scheduled_events:
            if event.get("day") != current_day:
                continue
            start = event.get("start_hour", 0)
            end = event.get("end_hour", 24)
            if not (start <= current_hour < end):
                continue
            if not self._event_matches_agent(event, agent_name, archetype):
                continue
            active.append(event)
        return active

    def get_active_monsoon(
        self, current_day: int, current_sim_time: int
    ) -> dict | None:
        """Return the active monsoon event (matching everyone) if any.

        Used by tools.move_to to detect that outdoor moves should incur a mood
        penalty. We match using "all" semantics — pass any archetype since the
        seeded monsoon event has affected_agents="all".
        """
        if not self._scheduled_events:
            return None
        current_hour = (current_sim_time % 1440) // 60
        for event in self._scheduled_events:
            if event.get("type") != "monsoon":
                continue
            if event.get("day") != current_day:
                continue
            start = event.get("start_hour", 0)
            end = event.get("end_hour", 24)
            if start <= current_hour < end:
                return event
        return None

    def is_outdoor_location(self, location_id: str) -> bool:
        """Return True if *location_id*'s map type is in the outdoor set."""
        loc = self._loc_index.get(location_id)
        if loc is None:
            return False
        return loc.get("type") in self._OUTDOOR_LOCATION_TYPES
    # --- Story 9.8 END --------------------------------------------------

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
                "yesterday_reflection": "",
                "monthly_rent":            defaults["monthly_rent"],
                "financial_stress":        False,
                "financial_stress_until_day": 0,
                # --- Story 9.7 BEGIN ---
                "last_consolidation_day":  defaults.get("last_consolidation_day", 0),
                # --- Story 9.7 END ---
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
            # --- Story 9.5: shared plans ---
            "shared_plans":  [],
            "next_plan_id":  1,
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

    async def adjust_mood(self, name: str, delta: float) -> None:
        """Apply *delta* to the agent's mood, clamping the result to [0, 100]."""
        async with self._lock:
            agent = self._state["agents"][name]
            agent["mood"] = max(0.0, min(100.0, agent.get("mood", 50.0) + delta))

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

    def get_conversation_history(
        self, agent_a: str, agent_b: str, limit: int = 10
    ) -> list[dict]:
        """Return the last *limit* messages between *agent_a* and *agent_b*.

        Order: oldest first (chronological), so the agent reads the thread
        top-to-bottom. Both directions of the pair are included.

        Synchronous read — does not acquire the lock. Safe because callers
        only inspect the returned list; mutations all go through
        ``add_conversation()`` which is locked.
        """
        convos = self._state.get("conversations", [])
        pair = [
            c for c in convos
            if (c["from"] == agent_a and c["to"] == agent_b)
            or (c["from"] == agent_b and c["to"] == agent_a)
        ]
        return pair[-limit:]

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
    # Shared plans (Story 9.5)
    # ------------------------------------------------------------------
    # Plan shape:
    #   {
    #     "id":           int,                  # monotonic counter
    #     "participants": [proposer, target],
    #     "location":     "dhaba",
    #     "target_time":  abs_minutes,          # day*1440 + sim_time
    #     "activity":     "lunch",              # free-form short label
    #     "status":       "pending"|"confirmed"|"declined"|"completed"|"failed",
    #     "decline_reason": str (optional),
    #     "created_at":   abs_minutes,
    #   }

    def _abs_minutes(self) -> int:
        """Current sim time as absolute minutes since Day 0 / 12am."""
        return self._state["day"] * 1440 + self._state["sim_time"]

    async def add_shared_plan(self, plan: dict) -> dict:
        """Append a new shared plan, assigning it a fresh id. Returns the stored plan."""
        async with self._lock:
            plans = self._state.setdefault("shared_plans", [])
            pid = self._state.get("next_plan_id", 1)
            self._state["next_plan_id"] = pid + 1
            stored = dict(plan)
            stored["id"] = pid
            stored.setdefault("status", "pending")
            stored.setdefault("created_at", self._abs_minutes())
            plans.append(stored)
            return stored

    def get_shared_plans(self) -> list[dict]:
        """Return the raw shared_plans list (read-only view)."""
        return self._state.get("shared_plans", [])

    def get_pending_plans(self) -> list[dict]:
        """All plans currently in 'pending' status."""
        return [p for p in self.get_shared_plans() if p.get("status") == "pending"]

    def get_plan(self, plan_id: int) -> dict | None:
        """Return the plan with the given id, or None."""
        for p in self.get_shared_plans():
            if p.get("id") == plan_id:
                return p
        return None

    def get_plans_for(self, agent_name: str, statuses: tuple[str, ...] = ("pending", "confirmed")) -> list[dict]:
        """All plans involving *agent_name* matching *statuses*."""
        return [
            p for p in self.get_shared_plans()
            if agent_name in p.get("participants", []) and p.get("status") in statuses
        ]

    def get_confirmed_plans_for(self, agent_name: str) -> list[dict]:
        """Convenience: confirmed plans involving *agent_name*."""
        return self.get_plans_for(agent_name, statuses=("confirmed",))

    async def update_plan_status(self, plan_id: int, status: str, **extra) -> bool:
        """Set the status (and any extra fields) on a plan. Returns True if found."""
        async with self._lock:
            for p in self._state.get("shared_plans", []):
                if p.get("id") == plan_id:
                    p["status"] = status
                    for k, v in extra.items():
                        p[k] = v
                    return True
            return False

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
    # Yesterday's reflection (Story 9.2)
    # ------------------------------------------------------------------

    async def set_yesterday_reflection(self, name: str, text: str) -> None:
        """Persist a 2-3 sentence reflection on the day that just ended.

        Overwrites any previous value — only the most recent day's reflection
        is kept on the agent dict. Saved automatically with state.json.
        """
        async with self._lock:
            self._state["agents"][name]["yesterday_reflection"] = text

    def get_yesterday_reflection(self, name: str) -> str:
        """Return the agent's most recent night reflection, or empty string."""
        return self._state["agents"][name].get("yesterday_reflection", "")

    # --- Story 9.7 BEGIN: memory consolidation bookkeeping ---------------
    async def set_last_consolidation_day(self, name: str, day: int) -> None:
        """Record the day on which *name*'s memory.md was last consolidated."""
        async with self._lock:
            self._state["agents"][name]["last_consolidation_day"] = int(day)

    def get_last_consolidation_day(self, name: str) -> int:
        """Return the day of the agent's last memory consolidation (0 if never)."""
        return int(self._state["agents"][name].get("last_consolidation_day", 0))
    # --- Story 9.7 END ---------------------------------------------------

    # ------------------------------------------------------------------
    # Rent cycle / financial stress (Story 9.4)
    # ------------------------------------------------------------------

    async def apply_rent_cycle(self, current_day: int) -> dict:
        """Deduct each agent's monthly_rent from coins and update financial_stress.

        For every agent:
          * Subtract ``monthly_rent`` (default 0) from ``coins``.
          * If the resulting balance is negative, set ``financial_stress = True``
            and ``financial_stress_until_day = current_day + 4``.
          * If ``financial_stress`` is already True but the until-day has passed,
            clear the flag.

        Returns a dict mapping agent_name -> {"rent": int, "balance": int,
        "stressed": bool} for diagnostics / logging.
        """
        result: dict[str, dict] = {}
        async with self._lock:
            for name, agent in self._state["agents"].items():
                rent = int(agent.get("monthly_rent", 0))
                if rent > 0:
                    agent["coins"] = int(agent.get("coins", 0)) - rent
                if agent["coins"] < 0:
                    agent["financial_stress"] = True
                    agent["financial_stress_until_day"] = current_day + 4
                else:
                    until = int(agent.get("financial_stress_until_day", 0))
                    if agent.get("financial_stress", False) and current_day >= until:
                        agent["financial_stress"] = False
                        agent["financial_stress_until_day"] = 0
                result[name] = {
                    "rent": rent,
                    "balance": agent["coins"],
                    "stressed": bool(agent.get("financial_stress", False)),
                }
        return result

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
        # Story 10.5 — wall-clock timestamp when drama_score first dropped to <=2.
        # Reset to None as soon as score climbs above 2. monotonic() is preferred
        # over sim_time so the dwell measures real-world observer dullness.
        self._low_score_since: float | None = None

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
            asyncio.create_task(self._run_night_reflections(old_day))
            # --- Story 9.7 BEGIN: memory consolidation after reflection ---
            asyncio.create_task(self._run_memory_consolidations(old_day))
            # --- Story 9.7 END --------------------------------------------
            # Story 9.4 — collect rent every 4 game days at midnight rollover.
            if new_day > 1 and new_day % 4 == 1:
                asyncio.create_task(self._run_rent_cycle(new_day))

        # 2. Decay all agent needs
        from engine.needs import decay_all_agents
        await decay_all_agents(self.TICK_MINUTES)

        # 3. Run all agents concurrently
        await asyncio.gather(*[
            self._run_agent_safe(name) for name in self.AGENTS
        ])

        # 3b. Story 9.5 — resolve any shared plans whose target_time has elapsed
        try:
            await self._resolve_shared_plans()
        except Exception as exc:
            logger.warning("[loop] plan resolution failed: %s", exc)

        # 4. Save world state
        await self.world.save_async()

        # 5. Auto-pacing (Story 10.5): drama-aware speed + night override.
        await self._apply_auto_pacing()

    async def _apply_auto_pacing(self) -> None:
        """Compute drama score and set world.speed accordingly.

        Honours the manual-lock flag set by the keyboard speed handlers.
        """
        # Manual override always wins.
        if self.world._state.get("_speed_locked"):
            self.world._state.pop("_pacing_label", None)
            return

        sleeping_count = sum(
            1 for name in self.AGENTS
            if "sleep" in self.world.get_agent_last_action(name).lower()
        )

        now = time.monotonic()
        score = compute_drama_score(self.world._state, now_monotonic=now)

        # Track sustained-quiet dwell.
        if score <= 2:
            if self._low_score_since is None:
                self._low_score_since = now
        else:
            self._low_score_since = None

        new_speed, label = pick_speed(
            score=score,
            sleeping_count=sleeping_count,
            locked=False,
            low_score_since=self._low_score_since,
            now_monotonic=now,
        )

        current_speed = self.world._state.get("speed", 1.0)
        if abs(new_speed - current_speed) > 0.01:
            await self.world.set_speed(new_speed)
            logger.info(
                "[loop] auto-pace: drama=%.1f sleeping=%d -> %.1fx (%s)",
                score, sleeping_count, new_speed, label or "—",
            )

        if label is None:
            self.world._state.pop("_pacing_label", None)
        else:
            self.world._state["_pacing_label"] = label

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

    async def _run_night_reflections(self, completed_day: int) -> None:
        """Spawn night_reflection for all 10 agents in parallel (Story 9.2)."""
        from engine.agent import night_reflection
        try:
            await asyncio.gather(*[
                night_reflection(name, completed_day) for name in self.AGENTS
            ], return_exceptions=True)
            logger.info("[loop] night reflections completed for Day %d", completed_day)
        except Exception as exc:
            logger.warning("[loop] night reflections failed: %s", exc)

    # --- Story 9.7 BEGIN: memory consolidation orchestration -------------
    async def _run_memory_consolidations(self, completed_day: int) -> None:
        """Run consolidate_memory for any agent ≥3 days past last consolidation.

        Skips agents whose last_consolidation_day is too recent. Updates the
        bookkeeping field after each successful run so the next gate works.
        """
        from engine.agent import consolidate_memory

        async def _maybe_consolidate(name: str) -> None:
            last = self.world.get_last_consolidation_day(name)
            if completed_day - last < 3:
                return
            try:
                await consolidate_memory(name, completed_day)
                await self.world.set_last_consolidation_day(name, completed_day)
            except Exception as exc:
                logger.warning(
                    "[loop] consolidate_memory(%s) failed: %s", name, exc
                )

        try:
            await asyncio.gather(*[
                _maybe_consolidate(name) for name in self.AGENTS
            ], return_exceptions=True)
            logger.info(
                "[loop] memory consolidations completed for Day %d", completed_day
            )
        except Exception as exc:
            logger.warning("[loop] memory consolidations failed: %s", exc)
    # --- Story 9.7 END ---------------------------------------------------

    async def _run_rent_cycle(self, current_day: int) -> None:
        """Apply the 4-day rent cycle and log resulting balances (Story 9.4)."""
        try:
            results = await self.world.apply_rent_cycle(current_day)
            stressed = [n for n, r in results.items() if r["stressed"]]
            await self.world.add_event(
                f"Rent collected (Day {current_day}). "
                f"{len(stressed)} agent(s) under financial stress."
                + (f" Stressed: {', '.join(sorted(stressed))}" if stressed else "")
            )
            logger.info(
                "[loop] rent cycle Day %d — stressed: %s", current_day, stressed
            )
        except Exception as exc:
            logger.warning("[loop] rent cycle failed: %s", exc)

    # ------------------------------------------------------------------
    # Story 9.5 — Shared plan resolution
    # ------------------------------------------------------------------

    # Locations whose services include any food offering — a successful
    # rendezvous here also restores hunger.
    _FOOD_SERVICES = {"eat", "eat_cheap", "street_food", "buy_food"}

    def _location_offers_food(self, location_id: str) -> bool:
        for svc in self._FOOD_SERVICES:
            if self.world.location_has_service(location_id, svc):
                return True
        return False

    async def _resolve_shared_plans(self) -> None:
        """Mark elapsed plans complete or failed and apply mood/hunger effects.

        A plan is "elapsed" once the current absolute minute is >= target_time.
        Only plans in status 'pending' or 'confirmed' are considered.
        """
        current_abs = self.world._abs_minutes()
        plans = list(self.world.get_shared_plans())
        for plan in plans:
            status = plan.get("status")
            if status not in ("pending", "confirmed"):
                continue
            target_time = plan.get("target_time", 0)
            if current_abs < target_time:
                continue

            participants = plan.get("participants", [])
            if len(participants) < 2:
                # Malformed plan — drop it.
                await self.world.update_plan_status(
                    plan["id"], "failed", failure_reason="malformed"
                )
                continue
            a, b = participants[0], participants[1]
            location = plan.get("location")
            try:
                a_loc = self.world.get_agent_location(a)
                b_loc = self.world.get_agent_location(b)
            except KeyError:
                await self.world.update_plan_status(
                    plan["id"], "failed", failure_reason="missing_agent"
                )
                continue

            both_present = (a_loc == location and b_loc == location)

            if both_present:
                # Success: +8 mood each, +50% hunger restore at food spots
                await self.world.update_plan_status(plan["id"], "completed")
                await self.world.adjust_mood(a, 8)
                await self.world.adjust_mood(b, 8)
                if self._location_offers_food(location):
                    # +50% hunger means hunger goes DOWN by 50 points
                    await self.world.update_needs(a, hunger_delta=-50, energy_delta=0)
                    await self.world.update_needs(b, hunger_delta=-50, energy_delta=0)
                activity = plan.get("activity", "meet")
                await self.world.add_event(
                    f"{a.capitalize()} and {b.capitalize()} had {activity} at "
                    f"{location}, as planned."
                )
                logger.info(
                    "[loop] plan %s completed: %s & %s at %s",
                    plan["id"], a, b, location,
                )
            else:
                # Failure: at least one didn't show up.
                present = [p for p, loc in ((a, a_loc), (b, b_loc)) if loc == location]
                absent = [p for p, loc in ((a, a_loc), (b, b_loc)) if loc != location]
                await self.world.update_plan_status(
                    plan["id"], "failed",
                    present=present, absent=absent,
                )
                # Present agents: -10 mood + memory entry
                for shower in present:
                    await self.world.adjust_mood(shower, -10)
                    other = absent[0] if absent else (b if shower == a else a)
                    try:
                        await self._append_memory(
                            shower,
                            f"- {other.capitalize()} didn't show up at {location} today. "
                            "Need to figure out what that means."
                        )
                    except Exception as exc:
                        logger.warning(
                            "[loop] could not append memory for %s: %s", shower, exc
                        )
                # Absent agents: queue a soft reminder for next gather_context.
                for missed in absent:
                    other = present[0] if present else (b if missed == a else a)
                    try:
                        await self.world.add_to_inbox(missed, {
                            "from": "_system",
                            "type": "missed_plan",
                            "text": (
                                f"You missed your plan with {other} at {location}. "
                                "They waited."
                            ),
                            "other": other,
                            "location": location,
                            "plan_id": plan["id"],
                            "time": self.world.time_to_str(self.world._state["sim_time"]),
                            "sim_time": self.world._state["sim_time"],
                            "day": self.world._state["day"],
                        })
                    except Exception as exc:
                        logger.warning(
                            "[loop] could not deliver missed-plan reminder to %s: %s",
                            missed, exc,
                        )
                await self.world.add_event(
                    f"plan failed: {a} & {b} did not meet at {location} "
                    f"(present={present}, absent={absent})"
                )
                logger.info(
                    "[loop] plan %s failed: present=%s absent=%s",
                    plan["id"], present, absent,
                )

    async def _append_memory(self, agent_name: str, line: str) -> None:
        """Append *line* (already prefixed if desired) to the agent's memory.md."""
        path = os.path.join("agents", agent_name, "memory.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Synchronous file IO — these writes are short and infrequent.
        try:
            existing = ""
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    existing = f.read()
            sep = "" if existing.endswith("\n") or not existing else "\n"
            with open(path, "a", encoding="utf-8") as f:
                f.write(sep + line + "\n")
        except Exception as exc:
            logger.warning("[loop] memory append failed (%s): %s", agent_name, exc)

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
        # Story 10.2 — live narrator runs alongside the tick loop.
        from engine.narrator import narrator_loop
        narrator = asyncio.create_task(narrator_loop(self.world))
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
            narrator.cancel()

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
