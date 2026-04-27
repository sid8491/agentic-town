"""
tests/test_tools.py — Tests for all 16 agent tools in engine/tools.py

Run with:
    .venv/Scripts/python.exe tests/test_tools.py
"""

import asyncio
import io
import os
import sys

# Force UTF-8 output on Windows so Unicode test names/content print correctly
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Make sure project root is on the path so engine imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine.tools as tools_module
from engine.tools import (
    read_file,
    edit_file,
    append_diary,
    grep_memory,
    move_to,
    look_around,
    check_needs,
    check_inventory,
    talk_to,
    ask_about,
    give_item,
    buy,
    sell,
    eat,
    sleep_action,
    work,
    execute_tool,
    world,
)

# ---------------------------------------------------------------------------
# Test harness helpers
# ---------------------------------------------------------------------------

_pass = 0
_fail = 0
_results = []


def _reset_world():
    """Reload world state from disk to undo any mutations."""
    world.load()


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def check(test_name: str, passed: bool, detail: str = ""):
    global _pass, _fail
    status = "PASS" if passed else "FAIL"
    if passed:
        _pass += 1
    else:
        _fail += 1
    extra = f" — {detail}" if detail else ""
    print(f"[{status}] {test_name}{extra}")
    _results.append((test_name, passed, detail))


# ---------------------------------------------------------------------------
# 1. read_file — allowed file, contains expected text
# ---------------------------------------------------------------------------

def test_read_file_valid():
    _reset_world()
    result = _run(read_file("arjun", "soul.md"))
    check(
        "read_file: soul.md contains 'Arjun'",
        isinstance(result, str) and len(result) > 0 and "Arjun" in result,
        repr(result[:80]),
    )


# ---------------------------------------------------------------------------
# 2. read_file — forbidden filename
# ---------------------------------------------------------------------------

def test_read_file_forbidden():
    result = _run(read_file("arjun", "secrets.md"))
    check(
        "read_file: secrets.md returns 'Cannot read that file.'",
        result == "Cannot read that file.",
        repr(result),
    )


# ---------------------------------------------------------------------------
# 3. edit_file — allowed file, content persists
# ---------------------------------------------------------------------------

def test_edit_file_allowed():
    _reset_world()
    new_content = "# Test\n1. Test goal"
    result = _run(edit_file("arjun", "goals.md", new_content))
    check(
        "edit_file: goals.md returns 'Updated goals.md.'",
        result == "Updated goals.md.",
        repr(result),
    )
    # Verify the file was actually changed
    path = os.path.join("agents", "arjun", "goals.md")
    with open(path, "r", encoding="utf-8") as f:
        on_disk = f.read()
    check(
        "edit_file: goals.md content matches what was written",
        on_disk == new_content,
        repr(on_disk[:60]),
    )


# ---------------------------------------------------------------------------
# 4. edit_file — forbidden file (soul.md)
# ---------------------------------------------------------------------------

def test_edit_file_forbidden():
    result = _run(edit_file("arjun", "soul.md", "hacked"))
    check(
        "edit_file: soul.md returns 'Cannot edit soul.md.'",
        result == "Cannot edit soul.md.",
        repr(result),
    )


# ---------------------------------------------------------------------------
# 5. append_diary — entry appears in diary.md
# ---------------------------------------------------------------------------

def test_append_diary():
    _reset_world()
    marker = "UNIQUE_TEST_ENTRY_XYZ"
    result = _run(append_diary("arjun", marker))
    check(
        "append_diary: returns 'Diary updated.'",
        result == "Diary updated.",
        repr(result),
    )
    path = os.path.join("agents", "arjun", "diary.md")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    check(
        "append_diary: entry appears in diary.md",
        marker in content,
        f"searched for {marker!r} in diary",
    )


# ---------------------------------------------------------------------------
# 6. grep_memory — existing term returns matching lines
# ---------------------------------------------------------------------------

def test_grep_memory_found():
    _reset_world()
    result = _run(grep_memory("arjun", "Rohan"))
    check(
        "grep_memory: 'Rohan' returns matched lines",
        isinstance(result, str) and "Rohan" in result,
        repr(result[:100]),
    )


# ---------------------------------------------------------------------------
# 7. grep_memory — non-existent term returns "Nothing found"
# ---------------------------------------------------------------------------

def test_grep_memory_not_found():
    result = _run(grep_memory("arjun", "xyznotfound"))
    check(
        "grep_memory: 'xyznotfound' returns nothing-found message",
        "Nothing found" in result and "xyznotfound" in result,
        repr(result),
    )


# ---------------------------------------------------------------------------
# 8. look_around — returns Location and Time
# ---------------------------------------------------------------------------

def test_look_around():
    _reset_world()
    result = _run(look_around("arjun"))
    check(
        "look_around: contains 'Location:' and 'Time:'",
        "Location:" in result and "Time:" in result,
        repr(result[:150]),
    )


# ---------------------------------------------------------------------------
# 9. check_needs — returns Hunger and Energy
# ---------------------------------------------------------------------------

def test_check_needs():
    _reset_world()
    result = _run(check_needs("arjun"))
    check(
        "check_needs: contains 'Hunger:' and 'Energy:'",
        "Hunger:" in result and "Energy:" in result,
        repr(result[:150]),
    )


# ---------------------------------------------------------------------------
# 10. check_inventory — returns Coins:
# ---------------------------------------------------------------------------

def test_check_inventory():
    _reset_world()
    result = _run(check_inventory("arjun"))
    check(
        "check_inventory: contains 'Coins:'",
        "Coins:" in result,
        repr(result),
    )


# ---------------------------------------------------------------------------
# 11. move_to — valid connected location (apartment → metro)
# ---------------------------------------------------------------------------

def test_move_to_connected():
    _reset_world()
    # arjun starts at apartment; metro is directly connected
    result = _run(move_to("arjun", "metro"))
    check(
        "move_to: apartment to metro returns success message",
        "Moved to" in result,
        repr(result),
    )
    # Confirm location updated
    loc = world.get_agent_location("arjun")
    check(
        "move_to: arjun location is now 'metro'",
        loc == "metro",
        f"location={loc}",
    )


# ---------------------------------------------------------------------------
# 12. move_to — non-connected location returns error
# ---------------------------------------------------------------------------

def test_move_to_not_connected():
    _reset_world()
    # arjun starts at apartment; cyber_city is NOT directly connected (requires metro)
    result = _run(move_to("arjun", "cyber_city"))
    check(
        "move_to: apartment to cyber_city returns error",
        "Cannot move to" in result,
        repr(result),
    )


# ---------------------------------------------------------------------------
# 13. talk_to — valid target: message in inbox
# ---------------------------------------------------------------------------

def test_talk_to_valid():
    _reset_world()
    result = _run(talk_to("arjun", "priya", "Hello!"))
    check(
        "talk_to: returns 'Message sent to priya.'",
        result == "Message sent to priya.",
        repr(result),
    )
    # Verify inbox
    priya = world.get_agent("priya")
    inbox = priya["inbox"]
    found = any(
        msg.get("from") == "arjun" and msg.get("text") == "Hello!"
        for msg in inbox
    )
    check(
        "talk_to: message appears in priya's inbox",
        found,
        f"inbox has {len(inbox)} messages",
    )


# ---------------------------------------------------------------------------
# 14. talk_to — invalid target returns error
# ---------------------------------------------------------------------------

def test_talk_to_invalid():
    result = _run(talk_to("arjun", "nobody", "Hello!"))
    check(
        "talk_to: unknown target returns error",
        "No one named nobody" in result,
        repr(result),
    )


# ---------------------------------------------------------------------------
# 15. buy — rohan at dhaba (which has eat_cheap/socialize but not buy_food)
#    Dhaba services: eat_cheap, gossip, socialize
#    sector29 services: buy_essentials, street_food, socialize
#    Move rohan to sector29 first (dhaba→sector29 is connected), then buy
# ---------------------------------------------------------------------------

def test_buy():
    _reset_world()
    # rohan starts at dhaba; sector29 is connected from dhaba
    # First move rohan to sector29 which has buy_essentials and street_food
    move_result = _run(move_to("rohan", "sector29"))
    check(
        "buy setup: rohan moved to sector29",
        "Moved to" in move_result,
        repr(move_result),
    )
    # sector29 has street_food → our buy check includes street_food
    rohan_before = world.get_agent("rohan")
    coins_before = rohan_before["coins"]

    result = _run(buy("rohan", "chai", 1))
    check(
        "buy: chai purchase at sector29 returns success",
        "Bought" in result and "chai" in result,
        repr(result),
    )
    rohan_after = world.get_agent("rohan")
    check(
        "buy: rohan coins deducted correctly",
        rohan_after["coins"] == coins_before - 3,
        f"before={coins_before}, after={rohan_after['coins']}",
    )
    check(
        "buy: chai in rohan inventory",
        "chai" in rohan_after.get("inventory", []),
        f"inventory={rohan_after.get('inventory')}",
    )


# ---------------------------------------------------------------------------
# 16. eat — give arjun bread directly, then eat
# ---------------------------------------------------------------------------

def test_eat():
    _reset_world()
    # Directly add bread to arjun's inventory via world.update_agent
    _run(world.update_agent("arjun", {"inventory": ["bread"]}))
    hunger_before = world.get_agent("arjun")["hunger"]

    result = _run(eat("arjun", "bread"))
    check(
        "eat: bread returns success message",
        "Ate bread" in result,
        repr(result),
    )
    arjun_after = world.get_agent("arjun")
    check(
        "eat: bread removed from inventory",
        "bread" not in arjun_after.get("inventory", []),
        f"inventory={arjun_after.get('inventory')}",
    )
    # hunger should have decreased (gone down) — hunger_delta was -30
    check(
        "eat: hunger level decreased",
        arjun_after["hunger"] < hunger_before or arjun_after["hunger"] == 0,
        f"before={hunger_before}, after={arjun_after['hunger']}",
    )


# ---------------------------------------------------------------------------
# 17. work — priya starts at cyber_city (has earn_money service)
# ---------------------------------------------------------------------------

def test_work():
    _reset_world()
    priya_before = world.get_agent("priya")
    coins_before = priya_before["coins"]

    result = _run(work("priya"))
    check(
        "work: priya at cyber_city returns success",
        "Worked" in result and "coins" in result.lower(),
        repr(result),
    )
    priya_after = world.get_agent("priya")
    # priya earns 50 coins
    check(
        "work: priya coins increased by 50",
        priya_after["coins"] == coins_before + 50,
        f"before={coins_before}, after={priya_after['coins']}",
    )


# ---------------------------------------------------------------------------
# 18. execute_tool — valid tool dispatch
# ---------------------------------------------------------------------------

def test_execute_tool_valid():
    _reset_world()
    result = _run(execute_tool("arjun", "check_needs", {}))
    check(
        "execute_tool: 'check_needs' dispatched correctly",
        "Hunger:" in result and "Energy:" in result,
        repr(result[:80]),
    )


# ---------------------------------------------------------------------------
# 19. execute_tool — unknown tool name
# ---------------------------------------------------------------------------

def test_execute_tool_unknown():
    result = _run(execute_tool("arjun", "unknown_tool", {}))
    check(
        "execute_tool: unknown_tool returns 'Unknown tool: unknown_tool'",
        result == "Unknown tool: unknown_tool",
        repr(result),
    )


# ---------------------------------------------------------------------------
# BONUS EDGE CASES
# ---------------------------------------------------------------------------

def test_eat_no_item():
    _reset_world()
    result = _run(eat("arjun", "bread"))
    check(
        "eat: eating item not in inventory returns error",
        "don't have" in result,
        repr(result),
    )


def test_eat_non_food():
    result = _run(eat("arjun", "sword"))
    check(
        "eat: non-food item returns 'Cannot eat'",
        "Cannot eat" in result,
        repr(result),
    )


def test_buy_insufficient_coins():
    _reset_world()
    # rohan has 40 coins, move him to sector29
    _run(move_to("rohan", "sector29"))
    # Try to buy groceries (20 coins) 3 times = 60 coins total, rohan has 40
    result = _run(buy("rohan", "groceries", 3))
    check(
        "buy: insufficient coins returns error",
        "Not enough coins" in result,
        repr(result),
    )


def test_sleep_wrong_location():
    _reset_world()
    # priya is at cyber_city, not apartment
    result = _run(sleep_action("priya"))
    check(
        "sleep: wrong location returns error",
        "only sleep at the apartment" in result,
        repr(result),
    )


def test_sleep_valid_time_at_apartment():
    _reset_world()
    # arjun is at apartment. Force time to 11pm (1380 minutes)
    world._state["sim_time"] = 1380
    result = _run(sleep_action("arjun"))
    check(
        "sleep: valid time at apartment restores energy",
        "Slept" in result and "40%" in result,
        repr(result),
    )


def test_give_item_valid():
    _reset_world()
    # Give arjun 2 breads, then give 1 to priya
    _run(world.update_agent("arjun", {"inventory": ["bread", "bread"]}))
    result = _run(give_item("arjun", "priya", "bread", 1))
    check(
        "give_item: valid transfer returns success",
        "Gave 1x bread to priya" in result,
        repr(result),
    )
    arjun = world.get_agent("arjun")
    priya = world.get_agent("priya")
    check(
        "give_item: arjun now has 1 bread",
        arjun["inventory"].count("bread") == 1,
        f"arjun inventory={arjun['inventory']}",
    )
    check(
        "give_item: priya now has 1 bread",
        priya["inventory"].count("bread") == 1,
        f"priya inventory={priya['inventory']}",
    )


def test_give_item_insufficient():
    _reset_world()
    result = _run(give_item("arjun", "priya", "bread", 5))
    check(
        "give_item: not enough items returns error",
        "don't have" in result or "You have" in result,
        repr(result),
    )


def test_sell_valid():
    _reset_world()
    # arjun at apartment — not connected to socialize service
    # Move arjun to sector29 (apartment→metro impossible direct, use metro)
    # Actually apartment→sector29 IS connected directly!
    _run(move_to("arjun", "sector29"))
    _run(world.update_agent("arjun", {"inventory": ["bread"], "coins": 150}))
    coins_before = world.get_agent("arjun")["coins"]
    result = _run(sell("arjun", "bread", 1, 10))
    check(
        "sell: valid sale at sector29 returns success",
        "Sold" in result and "bread" in result,
        repr(result),
    )
    arjun = world.get_agent("arjun")
    check(
        "sell: arjun coins increased by price",
        arjun["coins"] == coins_before + 10,
        f"before={coins_before}, after={arjun['coins']}",
    )


def test_ask_about_valid():
    _reset_world()
    result = _run(ask_about("arjun", "priya", "the startup scene"))
    check(
        "ask_about: valid question returns success",
        "Question sent to priya" in result and "startup scene" in result,
        repr(result),
    )
    priya = world.get_agent("priya")
    found = any(
        msg.get("type") == "question" and "startup scene" in msg.get("text", "")
        for msg in priya["inbox"]
    )
    check(
        "ask_about: question appears in priya's inbox",
        found,
        f"inbox={priya['inbox']}",
    )


def test_tool_registry_complete():
    """All 16 tools registered."""
    expected = {
        "read_file", "edit_file", "append_diary", "grep_memory",
        "move_to", "look_around", "check_needs", "check_inventory",
        "talk_to", "ask_about", "give_item", "buy", "sell", "eat",
        "sleep", "work",
    }
    from engine.tools import TOOL_REGISTRY
    actual = set(TOOL_REGISTRY.keys())
    missing = expected - actual
    extra = actual - expected
    check(
        "TOOL_REGISTRY: all 16 tools present",
        not missing and not extra,
        f"missing={missing}, extra={extra}",
    )


def test_tool_schemas_count():
    from engine.tools import TOOL_SCHEMAS
    check(
        "TOOL_SCHEMAS: 16 schemas defined",
        len(TOOL_SCHEMAS) == 16,
        f"count={len(TOOL_SCHEMAS)}",
    )


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Running engine/tools.py tests")
    print("=" * 60)

    # Core required tests (numbered per spec)
    test_read_file_valid()           # 1
    test_read_file_forbidden()       # 2
    test_edit_file_allowed()         # 3 (counts as 2 checks: return val + file content)
    test_edit_file_forbidden()       # 4
    test_append_diary()              # 5
    test_grep_memory_found()         # 6
    test_grep_memory_not_found()     # 7
    test_look_around()               # 8
    test_check_needs()               # 9
    test_check_inventory()           # 10
    test_move_to_connected()         # 11
    test_move_to_not_connected()     # 12
    test_talk_to_valid()             # 13
    test_talk_to_invalid()           # 14
    test_buy()                       # 15
    test_eat()                       # 16
    test_work()                      # 17
    test_execute_tool_valid()        # 18
    test_execute_tool_unknown()      # 19

    # Edge case tests
    print()
    print("--- Edge Cases ---")
    test_eat_no_item()
    test_eat_non_food()
    test_buy_insufficient_coins()
    test_sleep_wrong_location()
    test_sleep_valid_time_at_apartment()
    test_give_item_valid()
    test_give_item_insufficient()
    test_sell_valid()
    test_ask_about_valid()
    test_tool_registry_complete()
    test_tool_schemas_count()

    print()
    print("=" * 60)
    print(f"Results: {_pass} passed, {_fail} failed out of {_pass + _fail} checks")
    print("=" * 60)

    if _fail > 0:
        sys.exit(1)
