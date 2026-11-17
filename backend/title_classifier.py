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
VOCATION_PATTERN = r"MS|EK|ED|RP|(?-i:EM)|Monk|Master\s+Sorcerer|Elite\s+Knight|Elder\s+Druid|Royal\s+Paladin"
LEVEL_PATTERN = r"(?!(?:19|20)\d{2}\b)\d{2,4}"
ROSTER_LINE_RE = re.compile(
    rf"^\s*(?:(?P<name>[^\n:–-]{{2,50}})\s*[-–:]\s*)?"
    rf"(?P<vocation>{VOCATION_PATTERN})\s*[:=]?\s*(?:(?:level|lvl|lv\.?)\s*)?"
    rf"(?P<level>{LEVEL_PATTERN})\+?\s*$",
    re.IGNORECASE,
)
ROSTER_MEMBER_RE = re.compile(
    rf"(?<![\w])(?P<vocation>{VOCATION_PATTERN})\s*[:=]?\s*"
    rf"(?:(?:level|lvl|lv\.?)\s*)?(?P<level>{LEVEL_PATTERN})\+?(?!\d)",
    re.IGNORECASE,
)
TITLE_MEMBER_RE = ROSTER_MEMBER_RE
ROSTER_CONTEXT_RE = re.compile(r"\b(?:pt|party|players?|jogadores?|equipe|grupo|team[\s-]*hunt?)\b", re.IGNORECASE)
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


def _canonical_vocation(value: str) -> str:
    vocation = re.sub(r"\s+", " ", value.strip().casefold())
    return {
        "master sorcerer": "ms", "elite knight": "ek", "elder druid": "ed",
        "royal paladin": "rp", "monk": "em",
    }.get(vocation, vocation)


def _title_members(title: str) -> list[tuple[str, int]]:
    text = re.sub(r"\bEM\s+20\d{2}\b", " ", title or "", flags=re.IGNORECASE)
    matches = list(TITLE_MEMBER_RE.finditer(text))
    if matches:
        match = matches[0]
        return [(_canonical_vocation(match.group("vocation")), int(match.group("level")))]
    # Titles without a level still identify the POV vocation. Ignore EM when
    # it is part of the Portuguese phrase “em 2026”.
    vocation = re.search(rf"(?<!\w)(?:{VOCATION_PATTERN})(?!\w)", text, re.IGNORECASE)
    if vocation:
        return [(_canonical_vocation(vocation.group(0)), 0)]
    return []


def _description_members(description: str) -> list[tuple[str, int]]:
    candidates: list[tuple[str, int]] = []
    consecutive: list[tuple[str, int]] = []
    for line in (description or "").splitlines():
        matches = list(ROSTER_MEMBER_RE.finditer(line))
        if len(matches) >= 2 and len(line) <= 320:
            has_separator = bool(re.search(r"[,|/+&]", line[max(0, matches[0].end() - 1):matches[1].start()]))
            if has_separator or ROSTER_CONTEXT_RE.search(line):
                candidates.extend((_canonical_vocation(m.group("vocation")), int(m.group("level"))) for m in matches)

        full_line = ROSTER_LINE_RE.match(line)
        if full_line:
            consecutive.append((_canonical_vocation(full_line.group("vocation")), int(full_line.group("level"))))
        else:
            if len(consecutive) >= 2:
                candidates.extend(consecutive)
            consecutive = []
    if len(consecutive) >= 2:
        candidates.extend(consecutive)
    return list(dict.fromkeys(candidates))


def _roster_count(title: str, description: str) -> int:
    members = _description_members(description)
    for player in _title_members(title):
        same_vocation = [member for member in members if member[0] == player[0]]
        if player not in members and not (player[1] == 0 and same_vocation):
            members.append(player)
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
    roster_count = _roster_count(text, description)

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
        if roster_count >= 2 and roster_count != players_count:
            reasons.append("title team size conflicts with description roster")
        return HuntTitle(category, players_count, bool(reasons), "; ".join(reasons) or None)

    if has_team_hunt:
        players_count = roster_count
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

    if roster_count >= 2:
        if roster_count >= 4:
            category = "Team Hunt (PT)"
        elif roster_count == 3:
            category = "Trio"
        else:
            category = "Duo"
        if has_solo:
            return HuntTitle(category, roster_count, True, "description roster conflicts with solo in title")
        if roster_count > 5:
            return HuntTitle(category, roster_count, True, "description roster has more than five players")
        return HuntTitle(category, roster_count, False)

    # When there is no valid group marker, classify as Solo by default,
    # including titles that do not explicitly contain the word "solo".
    return HuntTitle("Solo", 1, False)
