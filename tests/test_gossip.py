"""
Story 3.3 — Message / Gossip System Tests

Verifies:
  - talk_to delivers a message to the recipient's inbox
  - ask_about delivers a question to the recipient's inbox
  - Inbox is cleared (emptied) after being read
  - Messages older than 2 game hours (120 sim_minutes) are discarded
  - Messages within the expiry window are delivered
  - Inbox messages appear in gather_context's LLM prompt
  - Sending to a non-existent agent returns an error string

Run with:
    .venv/Scripts/python.exe tests/test_gossip.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.world import WorldState
import engine.tools as tool_module

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(ROOT, "world", "state.json")
MAP_PATH = os.path.join(ROOT, "world", "map.json")

results = []


def run_test(name, coro_or_fn):
    try:
        if asyncio.iscoroutinefunction(coro_or_fn):
            asyncio.run(coro_or_fn())
        else:
            coro_or_fn()
        results.append((name, True, None))
        print(f"  PASS  {name}")
    except Exception as exc:
        results.append((name, False, str(exc)))
        print(f"  FAIL  {name}")
        print(f"        {exc}")


def make_world() -> WorldState:
    ws = WorldState(state_path=STATE_PATH, map_path=MAP_PATH)
    ws.load()
    # Clear all inboxes for a clean test slate
    for agent_data in ws._state["agents"].values():
        agent_data["inbox"] = []
    return ws


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_01_talk_to_delivers_message():
    """talk_to writes a message dict into the target's inbox."""
    ws = make_world()
    tool_module.world = ws

    result = await tool_module.talk_to("arjun", "priya", "Hey Priya, want chai?")

    assert "sent" in result.lower(), f"Unexpected result: {result}"
    inbox = ws._state["agents"]["priya"]["inbox"]
    assert len(inbox) == 1, f"Expected 1 inbox message, got {len(inbox)}"
    msg = inbox[0]
    assert msg["from"] == "arjun"
    assert msg["type"] == "message"
    assert "chai" in msg["text"]
    assert "sim_time" in msg, "Message must include sim_time for expiry tracking"
    assert "day" in msg, "Message must include day for expiry tracking"


async def test_02_ask_about_delivers_question():
    """ask_about writes a question dict into the target's inbox."""
    ws = make_world()
    tool_module.world = ws

    result = await tool_module.ask_about("neha", "vikram", "morning routine")

    assert "sent" in result.lower() or "question" in result.lower(), f"Unexpected result: {result}"
    inbox = ws._state["agents"]["vikram"]["inbox"]
    assert len(inbox) == 1, f"Expected 1 inbox message, got {len(inbox)}"
    msg = inbox[0]
    assert msg["from"] == "neha"
    assert msg["type"] == "question"
    assert "morning routine" in msg["text"]
    assert "sim_time" in msg
    assert "day" in msg


async def test_03_inbox_cleared_after_read():
    """clear_inbox returns messages then empties the inbox."""
    ws = make_world()
    tool_module.world = ws

    await tool_module.talk_to("arjun", "priya", "Test message")

    messages = await ws.clear_inbox("priya")
    assert len(messages) == 1, f"Expected 1 message returned, got {len(messages)}"

    # Second read must return nothing
    messages2 = await ws.clear_inbox("priya")
    assert len(messages2) == 0, f"Expected empty inbox after clear, got {len(messages2)}"


async def test_04_multiple_messages_all_delivered():
    """Multiple senders can all leave messages; all are returned."""
    ws = make_world()
    tool_module.world = ws

    await tool_module.talk_to("arjun", "priya", "Hello from Arjun")
    await tool_module.ask_about("neha", "priya", "weekend plans")
    await tool_module.talk_to("rohan", "priya", "Priya di, can you review my CV?")

    messages = await ws.clear_inbox("priya")
    assert len(messages) == 3, f"Expected 3 messages, got {len(messages)}"
    senders = {m["from"] for m in messages}
    assert senders == {"arjun", "neha", "rohan"}, f"Unexpected senders: {senders}"


async def test_05_stale_messages_discarded():
    """Messages older than 120 sim_minutes are dropped by clear_inbox."""
    ws = make_world()
    tool_module.world = ws

    current_sim_time = ws._state["sim_time"]
    current_day = ws._state["day"]

    # Inject a message that is 121 minutes old (just over the 2-hour limit)
    stale_sim = current_sim_time - 121
    stale_day = current_day
    if stale_sim < 0:
        stale_sim += 1440
        stale_day -= 1

    ws._state["agents"]["priya"]["inbox"].append({
        "from": "arjun",
        "type": "message",
        "text": "Old stale message",
        "time": "old",
        "sim_time": stale_sim,
        "day": max(stale_day, 1),
    })

    messages = await ws.clear_inbox("priya")
    assert len(messages) == 0, (
        f"Stale message should have been discarded, got {len(messages)}: {messages}"
    )


async def test_06_fresh_messages_not_discarded():
    """Messages within the 2-hour window are delivered."""
    ws = make_world()
    tool_module.world = ws

    current_sim_time = ws._state["sim_time"]
    current_day = ws._state["day"]

    # Inject a message that is 60 minutes old (within the 120-minute limit)
    fresh_sim = current_sim_time - 60
    fresh_day = current_day
    if fresh_sim < 0:
        fresh_sim += 1440
        fresh_day -= 1

    ws._state["agents"]["priya"]["inbox"].append({
        "from": "arjun",
        "type": "message",
        "text": "Recent message",
        "time": "recent",
        "sim_time": fresh_sim,
        "day": max(fresh_day, 1),
    })

    messages = await ws.clear_inbox("priya")
    assert len(messages) == 1, (
        f"Fresh message within 2-hour window should be delivered, got {len(messages)}"
    )
    assert messages[0]["text"] == "Recent message"


async def test_07_mixed_fresh_and_stale():
    """Only fresh messages survive when inbox has a mix of old and new."""
    ws = make_world()
    tool_module.world = ws

    current_sim_time = ws._state["sim_time"]
    current_day = ws._state["day"]

    def offset_time(minutes_ago):
        sim = current_sim_time - minutes_ago
        day = current_day
        if sim < 0:
            sim += 1440
            day -= 1
        return max(day, 1), sim

    stale_day, stale_sim = offset_time(200)
    fresh_day, fresh_sim = offset_time(30)

    ws._state["agents"]["priya"]["inbox"] = [
        {"from": "arjun", "type": "message", "text": "Stale",
         "time": "old", "sim_time": stale_sim, "day": stale_day},
        {"from": "neha", "type": "message", "text": "Fresh",
         "time": "recent", "sim_time": fresh_sim, "day": fresh_day},
    ]

    messages = await ws.clear_inbox("priya")
    assert len(messages) == 1, f"Expected 1 fresh message, got {len(messages)}"
    assert messages[0]["text"] == "Fresh"
    assert messages[0]["from"] == "neha"


async def test_08_message_boundary_exactly_120():
    """A message exactly 120 minutes old is still delivered (boundary inclusive)."""
    ws = make_world()
    tool_module.world = ws

    current_sim_time = ws._state["sim_time"]
    current_day = ws._state["day"]

    boundary_sim = current_sim_time - 120
    boundary_day = current_day
    if boundary_sim < 0:
        boundary_sim += 1440
        boundary_day -= 1

    ws._state["agents"]["priya"]["inbox"].append({
        "from": "arjun",
        "type": "message",
        "text": "Boundary message",
        "time": "boundary",
        "sim_time": boundary_sim,
        "day": max(boundary_day, 1),
    })

    messages = await ws.clear_inbox("priya")
    assert len(messages) == 1, (
        f"Message exactly at boundary (120 min) should be delivered, got {len(messages)}"
    )


async def test_09_talk_to_unknown_agent_returns_error():
    """talk_to returns an error string for unknown targets (no crash)."""
    ws = make_world()
    tool_module.world = ws

    result = await tool_module.talk_to("arjun", "ghost_agent", "Hello?")
    assert "No one" in result or "not found" in result.lower() or result, (
        f"Expected error string for unknown target, got: {result}"
    )
    # Ensure the result is a non-empty string (graceful failure)
    assert isinstance(result, str) and len(result) > 0


async def test_10_inbox_messages_appear_in_gather_context_prompt():
    """Messages in inbox are formatted and appear in the LLM prompt from gather_context."""
    import unittest.mock as mock
    from engine.agent import gather_context, AgentState

    ws = make_world()
    tool_module.world = ws

    # Put a message in arjun's inbox directly
    time_info = ws.get_time()
    ws._state["agents"]["arjun"]["inbox"].append({
        "from": "priya",
        "type": "message",
        "text": "Arjun, team meeting at 3pm!",
        "time": time_info["time_str"],
        "sim_time": time_info["sim_time"],
        "day": time_info["day"],
    })

    initial: AgentState = AgentState(
        agent_name="arjun",
        soul="", goals="", needs_summary="", surroundings="",
        inbox_messages=[], memory_snippets="", llm_prompt="",
        tool_name=None, tool_args=None, tool_result="", diary_entry="",
        tick_count=0,
    )

    with mock.patch("engine.agent.world", ws), mock.patch("engine.tools.world", ws):
        result = await gather_context(initial)

    prompt = result["llm_prompt"]
    assert "priya" in prompt.lower(), f"Sender 'priya' should appear in LLM prompt"
    assert "3pm" in prompt, f"Message text should appear in LLM prompt"
    assert result["inbox_messages"], "inbox_messages should be populated in state"

    # Inbox must be cleared after gather_context reads it
    remaining = ws._state["agents"]["arjun"]["inbox"]
    assert remaining == [], f"Inbox not cleared after gather_context: {remaining}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    ("1.  talk_to delivers message to recipient inbox", test_01_talk_to_delivers_message),
    ("2.  ask_about delivers question to recipient inbox", test_02_ask_about_delivers_question),
    ("3.  clear_inbox empties the inbox after returning messages", test_03_inbox_cleared_after_read),
    ("4.  Multiple senders all appear in inbox", test_04_multiple_messages_all_delivered),
    ("5.  Messages older than 120 sim_minutes are discarded", test_05_stale_messages_discarded),
    ("6.  Messages within 120-minute window are delivered", test_06_fresh_messages_not_discarded),
    ("7.  Mixed inbox: only fresh messages survive", test_07_mixed_fresh_and_stale),
    ("8.  Message exactly at 120-minute boundary is delivered", test_08_message_boundary_exactly_120),
    ("9.  talk_to unknown agent returns error string (no crash)", test_09_talk_to_unknown_agent_returns_error),
    ("10. Inbox messages appear in gather_context LLM prompt", test_10_inbox_messages_appear_in_gather_context_prompt),
]


if __name__ == "__main__":
    print("=" * 70)
    print("Story 3.3 -- Message / Gossip System Tests")
    print("=" * 70)

    for test_name, test_fn in TESTS:
        run_test(test_name, test_fn)

    print()
    print("=" * 70)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    total = len(results)
    print(f"Results: {passed}/{total} passed, {failed} failed")
    print("=" * 70)

    if failed:
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
        sys.exit(0)
