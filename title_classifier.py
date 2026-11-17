"""Classify hunt mode and party size from a YouTube video title."""

from __future__ import annotations

import re
from dataclasses import dataclass


# Require token boundaries. This accepts `x2`, `Team x3`, and `-x4-`, but
# rejects `2x loot`, `x2fast`, and occurrences embedded in larger words.
TEAM_SIZE_RE = re.compile(r"(?<![a-z0-9])x([2-5])(?![a-z0-9])", re.IGNORECASE)
DUO_RE = re.compile(r"(?<![a-z0-9])duo(?![a-z0-9])", re.IGNORECASE)
SOLO_RE = re.compile(r"(?<![a-z0-9])solo(?![a-z0-9])", re.IGNORECASE)
TEAM_HUNT_RE = re.compile(r"(?<![a-z0-9])(?:team[\s-]*hunt|th)(?![a-z0-9])", re.IGNORECASE)
ROSTER_LINE_RE = re.compile(
    r"^\s*(?:(?P<name>[^\n:–-]{2,50})\s*[-–:]\s*)?"
    r"(?P<vocation>MS|EK|ED|RP|EM|Monk|Master\s+Sorcerer|Elite\s+Knight|"
    r"Elder\s+Druid|Royal\s+Paladin)\s*(?:(?:level|lvl|lv\.?)\s*)?"
    r"(?P<level>\d{2,4})\+?\s*$",
    re.IGNORECASE,
)
NON_TEAM_MULTIPLIER_CONTEXT_RE = re.compile(
    r"^\s*(?:dmg|damage|loot|prey|preys|attack|experience|exp|boost|charms?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class HuntTitle:
    hunt_type: str | None
    players_count: int | None
    needs_review: bool
    review_reason: str | None = None


def _roster_count(description: str) -> int:
    members = set()
    for line in (description or "").splitlines():
        match = ROSTER_LINE_RE.match(line)
        if not match:
            continue
        name = (match.group("name") or "").strip().casefold()
        vocation = re.sub(r"\s+", " ", match.group("vocation").casefold())
        level = int(match.group("level"))
        members.add((name, vocation, level) if name else (vocation, level))
    return len(members)


def classify_hunt_title(title: str, description: str = "") -> HuntTitle:
    """Classify x4/x5 as Team Hunt, duo/x2 as Duo, and x3 as Trio.

    The largest group indicator wins when categories conflict. Conflicts and
    contradictions with `solo` are marked for human review.
    """
    text = title or ""
    team_matches = [
        match for match in TEAM_SIZE_RE.finditer(text)
        if not NON_TEAM_MULTIPLIER_CONTEXT_RE.match(text[match.end():match.end() + 36])
    ]
    team_indicators = [(match.start(), int(match.group(1))) for match in team_matches]
    for match in DUO_RE.finditer(text):
        # Do not count "duo" twice when an explicit x2 immediately follows it.
        has_nearby_x2 = any(
            team.group(1) == "2" and abs(team.start() - match.start()) <= 8
            for team in team_matches
        )
        if not has_nearby_x2:
            team_indicators.append((match.start(), 2))
    team_indicators.sort(key=lambda item: item[0])
    has_solo = SOLO_RE.search(title or "") is not None
    has_team_hunt = TEAM_HUNT_RE.search(text) is not None or TEAM_HUNT_RE.search(description or "") is not None

    if team_indicators:
        sizes = [size for _, size in team_indicators]
        if any(size >= 4 for size in sizes):
            category = "Team Hunt (PT)"
            players_count = next(size for size in sizes if size >= 4)
        elif 3 in sizes:
            category = "Trio"
            players_count = 3
        else:
            category = "Duo"
            players_count = 2

        categories = {
            "Team Hunt (PT)" if size >= 4 else "Trio" if size == 3 else "Duo"
            for size in sizes
        }
        reasons = []
        if len(categories) > 1 or len(set(sizes)) > 1:
            reasons.append("title contains conflicting team indicators")
        if has_solo:
            reasons.append("title contains both a team indicator and solo")
        return HuntTitle(category, players_count, bool(reasons), "; ".join(reasons) or None)

    if has_team_hunt:
        players_count = _roster_count(description)
        if players_count >= 4:
            category = "Team Hunt (PT)"
        elif players_count == 3:
            category = "Trio"
        elif players_count == 2:
            category = "Duo"
        else:
            return HuntTitle(
                "Team Hunt (PT)", None, True,
                "team hunt marker found but player roster could not be counted",
            )
        if players_count > 5:
            return HuntTitle(
                category, players_count, True,
                "team hunt roster has more than five players",
            )
        if has_solo:
            return HuntTitle(category, players_count, True, "title contains both a team indicator and solo")
        return HuntTitle(category, players_count, False)

    # When there is no valid group marker, classify as Solo by default,
    # including titles that do not explicitly contain the word "solo".
    return HuntTitle("Solo", 1, False)
