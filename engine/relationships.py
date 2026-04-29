"""
engine/relationships.py — Relationship sentiment parser.

Parses each agent's memory.md to score how they feel about each other agent,
yielding a directed graph of friendly / neutral / hostile sentiment.

Usage
-----
    from engine.relationships import parse_all_relationships
    edges = parse_all_relationships()    # {(from, to): "friendly"|"neutral"|"hostile"}

Format expected in memory.md
----------------------------
    # Relationships

    **Rohan** — free-form prose about Rohan ...
                spanning one or more lines until the next **Name** block
                or the next H1/H2 header (e.g. `# Knowledge`).

    **Priya** — more prose ...

The agent's own name is skipped if it ever appears.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

Sentiment = Literal["romantic", "friendly", "neutral", "hostile"]

ALL_AGENTS: list[str] = [
    "arjun", "priya", "rahul", "kavya", "suresh",
    "neha", "vikram", "deepa", "rohan", "anita",
]
_ALL_AGENTS_SET = set(ALL_AGENTS)

# ---------------------------------------------------------------------------
# Sentiment vocabulary
# ---------------------------------------------------------------------------

# Words that specifically signal romantic interest — scored separately so that a
# single "crush" or "attracted" lifts an edge to "romantic" without needing the
# full positive-word threshold.
ROMANTIC_WORDS: set[str] = {
    "crush", "attracted", "attraction",
    "beautiful", "handsome", "gorgeous",
    "heart", "heartbeat",
    "miss", "missed", "missing",
    "feelings", "feeling for",
    "romantic", "romance",
    "intimate", "intimacy",
    "adore", "adores", "adored",
    "longing", "desire", "desires", "yearning",
    "affection", "affectionate",
    "tender", "passionate", "passion",
    "flirt", "flirting", "flirted",
    "butterflies",
}

_ROM_RE = re.compile(
    r"\b(" + "|".join(sorted(map(re.escape, ROMANTIC_WORDS), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

POSITIVE_WORDS: set[str] = {
    "like", "likes", "liked",
    "friend", "friends", "friendly",
    "trust", "trusts", "trusted",
    "respect", "respects", "respected",
    "admire", "admires", "admired",
    "enjoy", "enjoys", "enjoyed",
    "appreciate", "appreciates", "appreciated",
    "kind", "warm", "fond",
    "love", "loves", "loved",
    "cherish", "cherished",
    "hope",
}

NEGATIVE_WORDS: set[str] = {
    "avoid", "avoids", "avoided",
    "distrust", "distrusts", "distrusted",
    "argued",
    "dislike", "dislikes", "disliked",
    "wary", "annoying", "annoyed",
    "fight", "fought",
    "hate", "hates", "hated",
    "cautious", "suspicious",
    "resent", "resents", "resented",
    "irritate", "irritates", "irritated",
    "fake", "manipulative",
}

# Pre-compile a single alternation regex per polarity for whole-word matching.
_POS_RE = re.compile(
    r"\b(" + "|".join(sorted(map(re.escape, POSITIVE_WORDS), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_NEG_RE = re.compile(
    r"\b(" + "|".join(sorted(map(re.escape, NEGATIVE_WORDS), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def _score_text(text: str) -> int:
    """Return positive_count - negative_count using whole-word matching."""
    pos = len(_POS_RE.findall(text))
    neg = len(_NEG_RE.findall(text))
    return pos - neg


def _score_romantic(text: str) -> int:
    """Return count of romantic-vocabulary hits."""
    return len(_ROM_RE.findall(text))


def _classify(score: int, romantic: int = 0) -> Sentiment:
    # Any romantic signal + overall positive tone → romantic
    if romantic >= 1 and score >= 1:
        return "romantic"
    if score >= 1:
        return "friendly"
    if score <= -1:
        return "hostile"
    return "neutral"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# Match the start of a relationship block: a line beginning with **Name**
# where Name is bolded markdown. Captures the inner name.
_BLOCK_HEADER_RE = re.compile(r"^\*\*([A-Za-z][A-Za-z\-']*)\*\*\s*", re.MULTILINE)


def _extract_relationships_section(text: str) -> str:
    """
    Return the body of the `# Relationships` section, terminated at the
    next H1 or H2 header (or EOF). Returns "" if no such section exists.
    """
    lines = text.splitlines()
    in_section = False
    collected: list[str] = []
    for line in lines:
        if not in_section:
            if line.strip() == "# Relationships":
                in_section = True
            continue
        # Stop on next H1 (`# `) or H2 (`## `) header — but the
        # `# Relationships` line itself was already consumed above.
        stripped = line.lstrip()
        if stripped.startswith("# ") or stripped.startswith("## "):
            break
        collected.append(line)
    return "\n".join(collected)


def parse_agent_relationships(
    agent_name: str,
    agents_dir: Path = Path("agents"),
) -> dict[str, Sentiment]:
    """
    Return {other_agent_name: sentiment} for *agent_name* based on their memory.md.

    Returns an empty dict if memory.md is missing, has no `# Relationships`
    section, or contains no recognisable per-person blocks.
    """
    memory_path = Path(agents_dir) / agent_name / "memory.md"
    if not memory_path.exists():
        return {}

    try:
        text = memory_path.read_text(encoding="utf-8")
    except OSError:
        return {}

    section = _extract_relationships_section(text)
    if not section.strip():
        return {}

    # Find all block headers within the section; their character offsets
    # bound the body text of each block.
    headers = list(_BLOCK_HEADER_RE.finditer(section))
    if not headers:
        return {}

    out: dict[str, Sentiment] = {}
    for i, m in enumerate(headers):
        other = m.group(1).lower()
        if other not in _ALL_AGENTS_SET:
            continue
        if other == agent_name.lower():
            continue   # skip self-references defensively

        # Body extends from end of header match to start of next header
        # (or to end of section).
        body_start = m.end()
        body_end = headers[i + 1].start() if i + 1 < len(headers) else len(section)
        body = section[body_start:body_end]

        out[other] = _classify(_score_text(body), _score_romantic(body))

    return out


def parse_all_relationships(
    agents_dir: Path = Path("agents"),
) -> dict[tuple[str, str], Sentiment]:
    """
    Return {(from, to): sentiment} across all 10 agents. Skips self-references.
    """
    edges: dict[tuple[str, str], Sentiment] = {}
    for name in ALL_AGENTS:
        rels = parse_agent_relationships(name, agents_dir=agents_dir)
        for other, sentiment in rels.items():
            if other == name:
                continue
            edges[(name, other)] = sentiment
    return edges
