"""
engine/tools.py — Agent tool implementations for Gurgaon Town Life simulation.

Tools are the only way agents affect the world. Each tool is an async function
that takes agent_name as its first argument, performs an action, updates world
state or agent files, and returns a human-readable result string.
"""

import asyncio
import json
import os
from datetime import datetime

from engine.world import WorldState
from engine.llm import build_tool_schema

# ---------------------------------------------------------------------------
# Module-level WorldState instance (shared with agent.py later)
# ---------------------------------------------------------------------------

world = WorldState()
world.load()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_READ_FILES = {"soul.md", "memory.md", "diary.md", "goals.md"}
ALLOWED_EDIT_FILES = {"memory.md", "goals.md"}

ITEM_PRICES = {
    "bread": 5,
    "chai": 3,
    "water": 2,
    "meal": 15,
    "groceries": 20,
    "essentials": 25,
}

FOOD_HUNGER_RESTORE = {
    "bread": 30,
    "chai": 10,
    "water": 5,
    "meal": 50,
    "groceries": 40,
}

AGENT_WORK_PAY = {
    "priya": 50,
    "arjun": 45,
    "kavya": 35,
    "neha": 40,
}
DEFAULT_WORK_PAY = 25

# All 8 location IDs from map.json
ALL_LOCATION_IDS = [
    "apartment",
    "metro",
    "cyber_city",
    "sector29",
    "dhaba",
    "supermarket",
    "cyber_hub",
    "park",
]

# ---------------------------------------------------------------------------
# Helper: agent file path
# ---------------------------------------------------------------------------


def _agent_file_path(agent_name: str, filename: str) -> str:
    """Return the absolute path to an agent's markdown file."""
    return os.path.join("agents", agent_name, filename)


# ---------------------------------------------------------------------------
# FILE TOOLS
# ---------------------------------------------------------------------------


async def read_file(agent_name: str, filename: str) -> str:
    """Read one of the agent's markdown files and return its content."""
    if filename not in ALLOWED_READ_FILES:
        return "Cannot read that file."
    path = _agent_file_path(agent_name, filename)
    if not os.path.exists(path):
        return "File not found."
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


async def edit_file(agent_name: str, filename: str, content: str) -> str:
    """Overwrite an editable agent file with new content."""
    if filename not in ALLOWED_EDIT_FILES:
        return f"Cannot edit {filename}."
    path = _agent_file_path(agent_name, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Updated {filename}."


async def append_diary(agent_name: str, entry: str) -> str:
    """Append a timestamped entry to the agent's diary.md."""
    time_info = world.get_time()
    day = time_info["day"]
    time_str = time_info["time_str"]

    if not entry.startswith("#"):
        header = f"# Day {day} — {time_str}\n"
        full_entry = header + entry
    else:
        full_entry = entry

    path = _agent_file_path(agent_name, "diary.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n" + full_entry + "\n")
    return "Diary updated."


async def grep_memory(agent_name: str, query: str) -> str:
    """Search the agent's memory.md for lines containing query (case-insensitive)."""
    path = _agent_file_path(agent_name, "memory.md")
    if not os.path.exists(path):
        return f"Nothing found for '{query}'."
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    matched = [line.rstrip("\n") for line in lines if query.lower() in line.lower()]
    if not matched:
        return f"Nothing found for '{query}'."
    return "\n".join(matched)


# ---------------------------------------------------------------------------
# WORLD TOOLS
# ---------------------------------------------------------------------------


def _find_path(start: str, goal: str) -> list[str]:
    """BFS shortest path between two location IDs. Returns [] if unreachable."""
    if start == goal:
        return [start]
    all_locs = world.get_all_locations()
    adjacency = {loc["id"]: set(loc.get("connected_to", [])) for loc in all_locs}
    queue = [[start]]
    visited = {start}
    while queue:
        path = queue.pop(0)
        current = path[-1]
        for neighbor in adjacency.get(current, set()):
            if neighbor == goal:
                return path + [neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(path + [neighbor])
    return []


async def move_to(agent_name: str, location: str) -> str:
    """Move the agent to any location, routing through intermediate hops automatically."""
    current_id = world.get_agent_location(agent_name)
    if location == current_id:
        loc = world.get_location(current_id)
        return f"You are already at {loc.get('display_name', current_id)}."

    # Try direct move first (fast path for adjacent locations)
    success = await world.move_agent(agent_name, location)
    if success:
        loc = world.get_location(location)
        return f"Moved to {loc.get('display_name', location)}."

    # Not adjacent — find BFS path and walk every hop to reach the destination
    path = _find_path(current_id, location)
    if len(path) >= 2:
        for hop in path[1:]:
            await world.move_agent(agent_name, hop)

        target_loc = world.get_location(location)
        if len(path) > 2:
            via_names = [
                world.get_location(p).get("display_name", p) for p in path[1:-1]
            ]
            return (
                f"Traveled to {target_loc.get('display_name', location)} "
                f"via {' → '.join(via_names)}."
            )
        return f"Moved to {target_loc.get('display_name', location)}."

    connected = world.get_connected_locations(current_id)
    return (
        f"Cannot reach {location} from {current_id}. "
        f"Connected: {connected}."
    )


async def look_around(agent_name: str) -> str:
    """Return a readable summary of the agent's current surroundings."""
    agent = world.get_agent(agent_name)
    location_id = agent["location"]
    loc = world.get_location(location_id)
    time_info = world.get_time()
    nearby = world.get_nearby_agents(agent_name)
    inbox_count = len(agent["inbox"])
    services = loc.get("services", [])
    display = loc.get("display_name", location_id)
    loc_type = loc.get("type", "unknown")

    nearby_str = ", ".join(nearby) if nearby else "no one"
    services_str = ", ".join(services) if services else "none"
    # Show all other locations — move_to handles routing automatically
    all_other = [
        l["id"] for l in world.get_all_locations() if l["id"] != location_id
    ]
    can_move_str = ", ".join(all_other) if all_other else "none"

    return (
        f"Location: {display} ({loc_type})\n"
        f"Time: Day {time_info['day']} — {time_info['time_str']}\n"
        f"Nearby: {nearby_str}\n"
        f"Services available: {services_str}\n"
        f"Can move to (routing is automatic): {can_move_str}\n"
        f"Messages in inbox: {inbox_count}"
    )


async def check_needs(agent_name: str) -> str:
    """Return a formatted summary of the agent's needs."""
    agent = world.get_agent(agent_name)
    hunger = agent["hunger"]
    energy = agent["energy"]
    mood = agent["mood"]
    coins = agent["coins"]

    # Hunger labels (higher hunger = more hungry)
    if hunger < 30:
        hunger_label = "low"
    elif hunger <= 70:
        hunger_label = "moderate"
    else:
        hunger_label = "high"

    # Energy labels
    if energy < 25:
        energy_label = "critical"
    elif energy <= 60:
        energy_label = "low"
    else:
        energy_label = "good"

    # Mood labels
    if mood < 30:
        mood_label = "low — consider socializing or resting"
    elif mood <= 60:
        mood_label = "neutral"
    else:
        mood_label = "good"

    return (
        f"Hunger: {hunger:.0f}% ({hunger_label})\n"
        f"Energy: {energy:.0f}% ({energy_label})\n"
        f"Mood: {mood:.0f}% ({mood_label})\n"
        f"Coins: {coins}"
    )


async def check_inventory(agent_name: str) -> str:
    """Return a formatted list of the agent's inventory and coins."""
    agent = world.get_agent(agent_name)
    coins = agent["coins"]
    inventory = agent.get("inventory", [])

    if not inventory:
        items_str = "none"
    else:
        # Count occurrences of each item
        counts: dict[str, int] = {}
        for item in inventory:
            counts[item] = counts.get(item, 0) + 1
        items_str = ", ".join(
            f"{name} (x{count})" for name, count in counts.items()
        )

    return f"Coins: {coins}\nItems: {items_str}"


async def talk_to(agent_name: str, target: str, message: str) -> str:
    """Send a direct message to another agent."""
    all_agents = world.get_all_agents()
    if target not in all_agents:
        return f"No one named {target} here."
    time_info = world.get_time()
    await world.add_to_inbox(
        target,
        {
            "from": agent_name,
            "type": "message",
            "text": message,
            "time": time_info["time_str"],
            "sim_time": time_info["sim_time"],
            "day": time_info["day"],
        },
    )
    return f"Message sent to {target}."


async def ask_about(agent_name: str, target: str, topic: str) -> str:
    """Send a question to another agent about a specific topic."""
    all_agents = world.get_all_agents()
    if target not in all_agents:
        return f"No one named {target} here."
    time_info = world.get_time()
    await world.add_to_inbox(
        target,
        {
            "from": agent_name,
            "type": "question",
            "text": f"Question from {agent_name}: {topic}",
            "time": time_info["time_str"],
            "sim_time": time_info["sim_time"],
            "day": time_info["day"],
        },
    )
    return f"Question sent to {target} about '{topic}'."


async def give_item(agent_name: str, target: str, item: str, quantity: int = 1) -> str:
    """Give one or more of an item from this agent's inventory to another agent."""
    all_agents = world.get_all_agents()
    if target not in all_agents:
        return f"No agent named {target} found."

    agent = world.get_agent(agent_name)
    inventory = list(agent.get("inventory", []))

    # Count how many the agent has
    count = inventory.count(item)
    if count < quantity:
        return f"You don't have {quantity}x {item}. You have {count}."

    # Remove items from giver
    for _ in range(quantity):
        inventory.remove(item)
    await world.update_agent(agent_name, {"inventory": inventory})

    # Add items to receiver
    target_agent = world.get_agent(target)
    target_inventory = list(target_agent.get("inventory", []))
    for _ in range(quantity):
        target_inventory.append(item)
    await world.update_agent(target, {"inventory": target_inventory})

    return f"Gave {quantity}x {item} to {target}."


async def buy(agent_name: str, item: str, quantity: int = 1) -> str:
    """Buy items from a shop at the current location."""
    if item not in ITEM_PRICES:
        return f"'{item}' is not available for purchase."

    location_id = world.get_agent_location(agent_name)

    # Determine which service allows buying this item
    can_buy = (
        world.location_has_service(location_id, "buy_food")
        or world.location_has_service(location_id, "buy_essentials")
        or world.location_has_service(location_id, "buy_groceries")
        or world.location_has_service(location_id, "eat_cheap")
        or world.location_has_service(location_id, "street_food")
    )
    if not can_buy:
        return f"No shop available at {location_id}. You need a location with buy_food, buy_essentials, or buy_groceries service."

    price_per_unit = ITEM_PRICES[item]
    total_cost = price_per_unit * quantity

    agent = world.get_agent(agent_name)
    if agent["coins"] < total_cost:
        return f"Not enough coins. {item} costs {total_cost} coins but you have {agent['coins']}."

    # Deduct coins and add items
    new_coins = agent["coins"] - total_cost
    inventory = list(agent.get("inventory", []))
    for _ in range(quantity):
        inventory.append(item)

    await world.update_agent(agent_name, {"coins": new_coins, "inventory": inventory})
    return f"Bought {quantity}x {item} for {total_cost} coins."


async def sell(agent_name: str, item: str, quantity: int = 1, price: int = 10) -> str:
    """Sell items informally at the current location (requires socialize service)."""
    location_id = world.get_agent_location(agent_name)
    if not world.location_has_service(location_id, "socialize"):
        return f"No informal market available at {location_id}. You need a location with socialize service."

    agent = world.get_agent(agent_name)
    inventory = list(agent.get("inventory", []))
    count = inventory.count(item)
    if count < quantity:
        return f"You don't have {quantity}x {item}. You have {count}."

    # Remove items and add coins
    for _ in range(quantity):
        inventory.remove(item)
    total_earned = price * quantity
    new_coins = agent["coins"] + total_earned

    await world.update_agent(agent_name, {"coins": new_coins, "inventory": inventory})
    return f"Sold {quantity}x {item} for {total_earned} coins."


async def eat(agent_name: str, item: str) -> str:
    """Eat a food item to reduce hunger."""
    if item not in FOOD_HUNGER_RESTORE:
        return f"Cannot eat {item}."

    agent = world.get_agent(agent_name)
    inventory = list(agent.get("inventory", []))
    if item not in inventory:
        return f"You don't have {item} in your inventory."

    inventory.remove(item)
    await world.update_agent(agent_name, {"inventory": inventory})

    restored = FOOD_HUNGER_RESTORE[item]
    # Negative hunger_delta means less hungry (hunger goes down)
    await world.update_needs(agent_name, hunger_delta=-restored, energy_delta=0)
    return f"Ate {item}. Hunger reduced by {restored}%."


_EAT_OUT_SERVICES = {"eat", "eat_cheap", "street_food", "buy_food"}
_EAT_OUT_COST = 15
_EAT_OUT_HUNGER_RESTORE = 60


async def eat_out(agent_name: str) -> str:
    """Eat a meal directly at a food/social location — no inventory needed. Costs 15 coins."""
    location_id = world.get_agent_location(agent_name)
    can_eat = any(world.location_has_service(location_id, s) for s in _EAT_OUT_SERVICES)
    if not can_eat:
        return (
            "No food service here. Go to dhaba (eat_cheap), cyber_hub (eat), "
            "or sector29 (street_food) to eat out."
        )

    agent = world.get_agent(agent_name)
    if agent["coins"] < _EAT_OUT_COST:
        return f"Not enough coins. A meal costs {_EAT_OUT_COST} coins; you have {agent['coins']}."

    new_coins = agent["coins"] - _EAT_OUT_COST
    await world.update_agent(agent_name, {"coins": new_coins})
    await world.update_needs(agent_name, hunger_delta=-_EAT_OUT_HUNGER_RESTORE, energy_delta=3)
    return f"Had a meal. Hunger -60%, energy +3%. Spent {_EAT_OUT_COST} coins ({new_coins} remaining)."


async def sleep_action(agent_name: str) -> str:
    """Sleep at the apartment to restore energy (only valid at night)."""
    location_id = world.get_agent_location(agent_name)
    if location_id != "apartment":
        return "You can only sleep at the apartment."

    time_info = world.get_time()
    sim_time = time_info["sim_time"]
    # Valid sleep window: 10pm (1320) or later, OR 6am (360) or earlier
    if not (sim_time >= 1320 or sim_time <= 360):
        return f"It's {time_info['time_str']}. Sleep is only possible between 10pm and 6am."

    await world.update_needs(agent_name, hunger_delta=0, energy_delta=40)
    return "Slept. Energy restored by 40%."


async def work(agent_name: str) -> str:
    """Work at current location to earn coins (requires earn_money service)."""
    location_id = world.get_agent_location(agent_name)
    if not world.location_has_service(location_id, "earn_money"):
        return f"Can't work here ({location_id} has no earn_money service). Go to your designated workplace."

    coins_earned = AGENT_WORK_PAY.get(agent_name.lower(), DEFAULT_WORK_PAY)

    agent = world.get_agent(agent_name)
    new_coins = agent["coins"] + coins_earned
    await world.update_agent(agent_name, {"coins": new_coins})
    await world.add_event(f"{agent_name} worked and earned {coins_earned} coins.")

    return f"Worked. Earned {coins_earned} coins."


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, callable] = {
    "read_file": read_file,
    "edit_file": edit_file,
    "append_diary": append_diary,
    "grep_memory": grep_memory,
    "move_to": move_to,
    "look_around": look_around,
    "check_needs": check_needs,
    "check_inventory": check_inventory,
    "talk_to": talk_to,
    "ask_about": ask_about,
    "give_item": give_item,
    "buy": buy,
    "sell": sell,
    "eat": eat,
    "eat_out": eat_out,
    "sleep": sleep_action,
    "work": work,
}

# ---------------------------------------------------------------------------
# Tool schemas (OpenAI format)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    build_tool_schema(
        name="read_file",
        description="Read one of the agent's personal markdown files (soul, memory, diary, goals).",
        parameters={
            "filename": {
                "type": "string",
                "description": "The file to read.",
                "enum": ["soul.md", "memory.md", "diary.md", "goals.md"],
            }
        },
        required=["filename"],
    ),
    build_tool_schema(
        name="edit_file",
        description="Overwrite the agent's memory.md or goals.md with new content. Soul and diary cannot be edited this way.",
        parameters={
            "filename": {
                "type": "string",
                "description": "The file to overwrite (memory.md or goals.md only).",
                "enum": ["memory.md", "goals.md"],
            },
            "content": {
                "type": "string",
                "description": "The full new content for the file (markdown format).",
            },
        },
        required=["filename", "content"],
    ),
    build_tool_schema(
        name="append_diary",
        description="Append a new entry to the agent's diary. A timestamp header is added automatically.",
        parameters={
            "entry": {
                "type": "string",
                "description": "The diary entry text to append.",
            }
        },
        required=["entry"],
    ),
    build_tool_schema(
        name="grep_memory",
        description="Search the agent's memory.md for lines containing a keyword or phrase.",
        parameters={
            "query": {
                "type": "string",
                "description": "The search term (case-insensitive).",
            }
        },
        required=["query"],
    ),
    build_tool_schema(
        name="move_to",
        description=(
            "Move the agent to any location on the map by name — routing through "
            "intermediate stops is automatic. You do NOT need to be adjacent. "
            "Just name your destination and you will arrive there."
        ),
        parameters={
            "location": {
                "type": "string",
                "description": "The destination location ID.",
                "enum": ALL_LOCATION_IDS,
            }
        },
        required=["location"],
    ),
    build_tool_schema(
        name="look_around",
        description="Get a summary of the agent's current location, time, nearby agents, services, and inbox count.",
        parameters={},
        required=[],
    ),
    build_tool_schema(
        name="check_needs",
        description="Check the agent's current hunger, energy, mood, and coin balance.",
        parameters={},
        required=[],
    ),
    build_tool_schema(
        name="check_inventory",
        description="List all items in the agent's inventory and their coin balance.",
        parameters={},
        required=[],
    ),
    build_tool_schema(
        name="talk_to",
        description="Send a message to another agent in the simulation.",
        parameters={
            "target": {
                "type": "string",
                "description": "The name of the agent to message.",
            },
            "message": {
                "type": "string",
                "description": "The message text to send.",
            },
        },
        required=["target", "message"],
    ),
    build_tool_schema(
        name="ask_about",
        description="Send a question to another agent about a specific topic.",
        parameters={
            "target": {
                "type": "string",
                "description": "The name of the agent to ask.",
            },
            "topic": {
                "type": "string",
                "description": "The topic or question to ask about.",
            },
        },
        required=["target", "topic"],
    ),
    build_tool_schema(
        name="give_item",
        description="Give one or more items from this agent's inventory to another agent.",
        parameters={
            "target": {
                "type": "string",
                "description": "The name of the agent to give items to.",
            },
            "item": {
                "type": "string",
                "description": "The item to give.",
            },
            "quantity": {
                "type": "integer",
                "description": "How many to give (default 1).",
                "default": 1,
            },
        },
        required=["target", "item"],
    ),
    build_tool_schema(
        name="buy",
        description="Buy food or essentials from a shop at the current location. Available items: bread (5), chai (3), water (2), meal (15), groceries (20), essentials (25).",
        parameters={
            "item": {
                "type": "string",
                "description": "The item to buy.",
                "enum": list(ITEM_PRICES.keys()),
            },
            "quantity": {
                "type": "integer",
                "description": "How many to buy (default 1).",
                "default": 1,
            },
        },
        required=["item"],
    ),
    build_tool_schema(
        name="sell",
        description="Sell items informally at a location with socialize service.",
        parameters={
            "item": {
                "type": "string",
                "description": "The item to sell.",
            },
            "quantity": {
                "type": "integer",
                "description": "How many to sell (default 1).",
                "default": 1,
            },
            "price": {
                "type": "integer",
                "description": "Price per unit in coins (default 10).",
                "default": 10,
            },
        },
        required=["item"],
    ),
    build_tool_schema(
        name="eat",
        description="Eat a food item from inventory to reduce hunger.",
        parameters={
            "item": {
                "type": "string",
                "description": "The food item to eat.",
                "enum": list(FOOD_HUNGER_RESTORE.keys()),
            }
        },
        required=["item"],
    ),
    build_tool_schema(
        name="eat_out",
        description=(
            "Eat a meal directly at a food or social location — no inventory needed. "
            "Costs 15 coins. Reduces hunger by 60%. Works at dhaba, cyber_hub, sector29. "
            "Use this when hungry and at a food location instead of buy+eat."
        ),
        parameters={},
        required=[],
    ),
    build_tool_schema(
        name="sleep",
        description="Sleep at the apartment to restore energy. Only possible between 10pm and 6am.",
        parameters={},
        required=[],
    ),
    build_tool_schema(
        name="work",
        description="Work at your current location to earn coins. Requires the earn_money service here — your SCHEDULE section tells you which location is your workplace.",
        parameters={},
        required=[],
    ),
]

# ---------------------------------------------------------------------------
# Dispatch function
# ---------------------------------------------------------------------------


async def execute_tool(agent_name: str, tool_name: str, tool_args: dict) -> str:
    """Dispatch a named tool call for the given agent."""
    if tool_name not in TOOL_REGISTRY:
        return f"Unknown tool: {tool_name}"
    fn = TOOL_REGISTRY[tool_name]
    return await fn(agent_name, **tool_args)
