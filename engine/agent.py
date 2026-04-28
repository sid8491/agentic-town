"""
engine/agent.py — LangGraph-based agent decision loop for Gurgaon Town Life.

Each agent runs a four-node graph every tick:
    gather_context → llm_decide → execute_tool → reflect

The graph is compiled once at module load (``agent_graph``) and reused by
every ``AgentRunner.tick()`` call.

Usage
-----
    from engine.agent import AgentRunner, agent_graph

    runner = AgentRunner("arjun")
    result = await runner.tick()

Direct execution (requires Ollama running with qwen3:27b):
    .venv/Scripts/python.exe -m engine.agent arjun 3
"""

from __future__ import annotations

import logging
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

import engine.tools as tools
from engine.llm import call_llm
from engine.tools import (
    TOOL_SCHEMAS,
    append_diary,
    check_needs,
    execute_tool,
    grep_memory,
    look_around,
    read_file,
    world,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------


class AgentState(TypedDict):
    agent_name: str
    soul: str
    goals: str
    needs_summary: str
    surroundings: str
    inbox_messages: list[dict]
    memory_snippets: str
    llm_prompt: str
    tool_name: Optional[str]
    tool_args: Optional[dict]
    tool_result: str
    diary_entry: str
    tick_count: int


# ---------------------------------------------------------------------------
# Node 1: gather_context
# ---------------------------------------------------------------------------


async def gather_context(state: AgentState) -> AgentState:
    """
    Assemble everything the agent needs to make a decision.

    Reads soul.md, goals.md, current needs, surroundings, inbox, and
    relevant memory snippets, then builds the LLM prompt.
    """
    agent_name = state["agent_name"]

    # Read soul and goals
    soul = await read_file(agent_name, "soul.md")
    goals = await read_file(agent_name, "goals.md")

    # Current needs
    needs_summary = await check_needs(agent_name)

    # Surroundings
    surroundings = await look_around(agent_name)

    # Inbox — drain and return messages
    inbox_messages = await world.clear_inbox(agent_name)

    # Build a memory query from current location + time of day
    try:
        agent = world.get_agent(agent_name)
        location_id = agent["location"]
        time_info = world.get_time()
        sim_time = time_info["sim_time"]
        # Rough time-of-day label
        if sim_time < 360:
            time_label = "night"
        elif sim_time < 720:
            time_label = "morning"
        elif sim_time < 960:
            time_label = "afternoon"
        elif sim_time < 1200:
            time_label = "evening"
        else:
            time_label = "night"
        memory_query = f"{location_id} {time_label}"
    except Exception:
        memory_query = "morning"

    memory_snippets = await grep_memory(agent_name, memory_query)
    # If the primary query returned nothing, fall back to location alone
    if "Nothing found" in memory_snippets:
        try:
            memory_snippets = await grep_memory(agent_name, location_id)
        except Exception:
            pass

    # Format inbox for the prompt
    if inbox_messages:
        formatted_inbox = "\n".join(
            f"  From {msg.get('from', '?')} [{msg.get('type', 'message')}]: {msg.get('text', '')}"
            for msg in inbox_messages
        )
    else:
        formatted_inbox = "No new messages."

    # Format memory snippets for the prompt
    memory_text = memory_snippets if memory_snippets and "Nothing found" not in memory_snippets else "Nothing specific."

    # Trim soul to first 300 chars to keep prompt concise
    soul_summary = soul[:300].rsplit("\n", 1)[0] if len(soul) > 300 else soul

    # Build the LLM prompt
    llm_prompt = (
        "=== WHO YOU ARE ===\n"
        f"{soul_summary}\n\n"
        "=== YOUR GOALS ===\n"
        f"{goals}\n\n"
        "=== RIGHT NOW ===\n"
        f"{needs_summary}\n"
        f"{surroundings}\n\n"
        "=== MESSAGES RECEIVED ===\n"
        f"{formatted_inbox}\n\n"
        "=== RELEVANT MEMORIES ===\n"
        f"{memory_text}\n\n"
        "=== WHAT DO YOU DO? ===\n"
        "Choose exactly one tool to call. Be true to your character."
    )

    return {
        **state,
        "soul": soul,
        "goals": goals,
        "needs_summary": needs_summary,
        "surroundings": surroundings,
        "inbox_messages": inbox_messages,
        "memory_snippets": memory_text,
        "llm_prompt": llm_prompt,
    }


# ---------------------------------------------------------------------------
# Node 2: llm_decide
# ---------------------------------------------------------------------------


async def llm_decide(state: AgentState) -> AgentState:
    """
    Ask the LLM what to do next.

    If the model returns a tool call, use it directly. If it returns plain
    text, attempt a simple keyword parse to extract a tool name; fall back
    to ``look_around`` with no args if parsing fails.
    """
    agent_name = state["agent_name"]

    response = await call_llm(
        state["llm_prompt"],
        tools=TOOL_SCHEMAS,
        system=(
            f"You are {agent_name.capitalize()}, a character in a Gurgaon town "
            "simulation. Stay in character. Call exactly one tool."
        ),
        max_tokens=200,
        thinking=False,
    )

    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None

    if response.tool_name:
        # Clean structured tool call from the LLM
        tool_name = response.tool_name
        tool_args = response.tool_args or {}
    else:
        # Text-only response: try to find a tool name mentioned in the text
        text = (response.text or "").lower()
        # Walk through known tool names and pick the first match
        known_tools = [schema["function"]["name"] for schema in TOOL_SCHEMAS]
        for candidate in known_tools:
            if candidate.replace("_", " ") in text or candidate in text:
                tool_name = candidate
                tool_args = {}
                break

        # Ultimate fallback: look_around with no args
        if tool_name is None:
            tool_name = "look_around"
            tool_args = {}

        logger.debug(
            "[%s] LLM returned text-only; parsed tool=%s from: %s",
            agent_name,
            tool_name,
            (response.text or "")[:80],
        )

    logger.info("[%s] decided: %s(%s)", agent_name, tool_name, tool_args)

    return {
        **state,
        "tool_name": tool_name,
        "tool_args": tool_args,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _action_label(tool_name: str, tool_args: dict) -> str:
    """Convert a tool name + args into a short human-readable bubble string."""
    _simple: dict[str, str] = {
        "look_around":     "looking around...",
        "check_needs":     "checking needs...",
        "check_inventory": "checking inventory...",
        "append_diary":    "writing diary...",
        "grep_memory":     "recalling memory...",
        "sleep_action":    "sleeping...",
        "work":            "working...",
    }
    if tool_name in _simple:
        return _simple[tool_name]
    if tool_name == "read_file":
        return f"reading {tool_args.get('filename', 'notes')}..."
    if tool_name == "edit_file":
        return f"editing {tool_args.get('filename', 'notes')}..."
    if tool_name == "move_to":
        return f"moving to {tool_args.get('location', 'somewhere')}..."
    if tool_name == "talk_to":
        return f"talking to {tool_args.get('target', 'someone')}..."
    if tool_name == "ask_about":
        return f"asking {tool_args.get('target', 'someone')}..."
    if tool_name == "give_item":
        return f"giving {tool_args.get('item', 'something')}..."
    if tool_name == "buy":
        return f"buying {tool_args.get('item', 'something')}..."
    if tool_name == "sell":
        return f"selling {tool_args.get('item', 'something')}..."
    if tool_name == "eat":
        return f"eating {tool_args.get('item', 'food')}..."
    return tool_name.replace("_", " ") + "..."


# ---------------------------------------------------------------------------
# Node 3: execute_tool_node
# ---------------------------------------------------------------------------


async def execute_tool_node(state: AgentState) -> AgentState:
    """
    Execute the chosen tool and record the result in world events.
    """
    agent_name = state["agent_name"]
    tool_name = state["tool_name"] or "look_around"
    tool_args = state["tool_args"] or {}

    try:
        tool_result = await execute_tool(agent_name, tool_name, tool_args)
    except TypeError as exc:
        tool_result = f"Tool call failed (missing args): {exc}"
        logger.warning("[%s] tool %s bad args %s: %s", agent_name, tool_name, tool_args, exc)

    # Record event in world history (truncated for readability)
    await tools.world.add_event(
        f"{agent_name} → {tool_name}: {tool_result[:60]}"
    )

    # Update last-action label for the renderer (thought bubble)
    await tools.world.set_agent_last_action(agent_name, _action_label(tool_name, tool_args))

    logger.info("[%s] result: %s", agent_name, tool_result)

    return {
        **state,
        "tool_result": tool_result,
    }


# ---------------------------------------------------------------------------
# Node 4: reflect
# ---------------------------------------------------------------------------


async def reflect(state: AgentState) -> AgentState:
    """
    Write a private diary entry reflecting on what just happened.

    Makes a second LLM call (no tool schemas) to generate a short,
    first-person diary entry, then appends it to diary.md.
    """
    agent_name = state["agent_name"]
    tool_name = state["tool_name"] or "look_around"
    tool_args = state["tool_args"] or {}
    tool_result = state["tool_result"]

    reflection_prompt = (
        f"You are {agent_name}. You just did: {tool_name}({tool_args})\n"
        f"Result: {tool_result}\n\n"
        "Write ONE short diary entry (2-4 sentences) in your personal voice "
        "about what just happened and how you feel. Be specific, be human. "
        "No need to repeat what you did mechanically — write how it felt."
    )

    response = await call_llm(
        reflection_prompt,
        system=f"You are {agent_name}, writing in your private diary.",
        max_tokens=500,
        thinking=False,
    )

    # Use text response; fall back to a minimal entry if LLM fails silently
    diary_text = response.text or f"Did {tool_name}. Life continues."

    # Persist to diary.md
    await append_diary(agent_name, diary_text)

    logger.info("[%s] diary: %s...", agent_name, diary_text[:80])

    return {
        **state,
        "diary_entry": diary_text,
    }


# ---------------------------------------------------------------------------
# Build and compile the graph
# ---------------------------------------------------------------------------


def build_agent_graph():
    """Construct and compile the four-node LangGraph agent graph."""
    graph = StateGraph(AgentState)

    graph.add_node("gather_context", gather_context)
    graph.add_node("llm_decide", llm_decide)
    graph.add_node("execute_tool", execute_tool_node)
    graph.add_node("reflect", reflect)

    graph.set_entry_point("gather_context")
    graph.add_edge("gather_context", "llm_decide")
    graph.add_edge("llm_decide", "execute_tool")
    graph.add_edge("execute_tool", "reflect")
    graph.add_edge("reflect", END)

    return graph.compile()


# Module-level compiled graph — imported and reused by AgentRunner
agent_graph = build_agent_graph()


# ---------------------------------------------------------------------------
# AgentRunner
# ---------------------------------------------------------------------------


class AgentRunner:
    """
    Convenience wrapper around the compiled agent graph.

    Parameters
    ----------
    agent_name : str
        The name of the agent (must exist in world state and agents/ directory).
    """

    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name

    async def tick(self) -> AgentState:
        """
        Run one full tick of the agent decision loop.

        Returns the final ``AgentState`` after all four nodes have executed.
        """
        initial_state: AgentState = AgentState(
            agent_name=self.agent_name,
            soul="",
            goals="",
            needs_summary="",
            surroundings="",
            inbox_messages=[],
            memory_snippets="",
            llm_prompt="",
            tool_name=None,
            tool_args=None,
            tool_result="",
            diary_entry="",
            tick_count=0,
        )
        result = await agent_graph.ainvoke(initial_state)
        return result


# ---------------------------------------------------------------------------
# __main__ entry point (requires live Ollama — do not run in CI)
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import asyncio
    import sys

    agent_name = sys.argv[1] if len(sys.argv) > 1 else "arjun"
    ticks = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    async def run() -> None:
        from engine.tools import world as _world

        _world.load()
        runner = AgentRunner(agent_name)
        for i in range(ticks):
            print(f"\n{'=' * 50}")
            print(f"TICK {i + 1} — {agent_name}")
            print("=" * 50)
            result = await runner.tick()
            _world.advance_time(15)
            _world.save()
            print(f"Action: {result['tool_name']}")
            print(f"Diary: {result['diary_entry'][:200]}")

    asyncio.run(run())
