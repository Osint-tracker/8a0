"""
=============================================================================
  UCL Historical Roster Extractor (1955–2012)
  Two-Level Async Pipeline: Match Discovery → Roster Extraction
  
  Powered by UEFA's undocumented Match API (v5).
  Output: historical_rosters_1955_2012.json
=============================================================================
"""

import asyncio
import json
import logging
import random
import sys
from json import JSONDecodeError
from pathlib import Path

import aiohttp
from aiohttp import ClientError

# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE CONFIGURATION — hardcoded per specification
# ─────────────────────────────────────────────────────────────────────────────
PIPELINE_CONFIG = {
    "pipeline_config": {
        "start_year": 1955,
        "end_year": 2012,
        "level_1_url": (
            "https://match.uefa.com/v5/matches"
            "?competitionId=1&seasonYear={year}&limit=200&offset=0"
        ),
        "level_2_url": (
            "https://match.uefa.com/v5/matches/{match_id}/lineups"
        ),
    },
    "uefa_headers": {
        "accept": "application/json, text/plain, */*",
        "accept-language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        "origin": "https://www.uefa.com",
        "referer": "https://www.uefa.com/",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/148.0.0.0 Safari/537.36"
        ),
        "x-api-key": (
            "ceeee1a5bb209502c6c438abd8f30aef179ce669bb9288f2d1cf2fa276de03f4"
        ),
    },
}

# Extract shorthand references
_CFG = PIPELINE_CONFIG["pipeline_config"]
_HEADERS = PIPELINE_CONFIG["uefa_headers"]
START_YEAR: int = _CFG["start_year"]
END_YEAR: int = _CFG["end_year"]
LEVEL_1_URL: str = _CFG["level_1_url"]
LEVEL_2_URL: str = _CFG["level_2_url"]
OUTPUT_FILE = Path(__file__).parent / "historical_rosters_1955_2012.json"

# Concurrency limiter — max 2 parallel requests to avoid WAF triggers
SEMAPHORE = asyncio.Semaphore(2)

# ─────────────────────────────────────────────────────────────────────────────
# DYNAMIC HARD FILTER — round types that qualify per era
# ─────────────────────────────────────────────────────────────────────────────
# Pre-2006: only knockout rounds from quarter-finals onwards
ROUNDS_PRE_2006 = {"QUARTER_FINALS", "SEMIFINAL", "FINAL"}
# 2006+: include Round of 16 (format change that season)
ROUNDS_2006_PLUS = {"ROUND_OF_16", "QUARTER_FINALS", "SEMIFINAL", "FINAL"}

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("ucl-extractor")


# ─────────────────────────────────────────────────────────────────────────────
# HELPER: safe nested dict access
# ─────────────────────────────────────────────────────────────────────────────
def _deep_get(obj: dict, *keys, default=None):
    """Walk into nested dicts/lists without raising on missing keys."""
    current = obj
    for k in keys:
        if isinstance(current, dict):
            current = current.get(k)
        elif isinstance(current, list) and isinstance(k, int) and k < len(current):
            current = current[k]
        else:
            return default
        if current is None:
            return default
    return current


def _extract_round_type(match: dict) -> str | None:
    """
    Try multiple known paths to locate the round type string.
    UEFA's schema has shifted across API versions, so we probe defensively.
    """
    # Primary path: round.metaData.type
    rt = _deep_get(match, "round", "metaData", "type")
    if rt:
        return rt.upper()

    # Fallback: round.phase (seen in older payloads)
    rt = _deep_get(match, "round", "phase")
    if rt:
        return rt.upper()

    # Fallback: round.translations.name.EN
    rt = _deep_get(match, "round", "translations", "name", "EN")
    if rt:
        # Normalize free-text like "Quarter-finals" → "QUARTER_FINALS"
        return rt.upper().replace("-", "_").replace(" ", "_")

    return None


# ─────────────────────────────────────────────────────────────────────────────
# LEVEL 1: Match Discovery
# ─────────────────────────────────────────────────────────────────────────────
async def discover_matches_for_year(
    session: aiohttp.ClientSession, year: int
) -> list[str]:
    """
    Hit the Tournament Map endpoint for a given season year.
    Apply the dynamic hard filter and return qualifying match IDs.
    """
    url = LEVEL_1_URL.format(year=year)
    allowed_rounds = ROUNDS_PRE_2006 if year < 2006 else ROUNDS_2006_PLUS

    async with SEMAPHORE:
        try:
            async with session.get(url) as resp:
                if resp.status == 404:
                    log.warning("Year %d → 404 (no data for this season)", year)
                    return []
                resp.raise_for_status()
                data = await resp.json()
        except (ClientError, JSONDecodeError) as exc:
            log.warning("Year %d → request/parse error: %s", year, exc)
            return []

    # data should be a list of match objects
    if not isinstance(data, list):
        log.warning("Year %d → unexpected response type: %s", year, type(data))
        return []

    match_ids: list[str] = []
    for match in data:
        round_type = _extract_round_type(match)
        if round_type and round_type in allowed_rounds:
            mid = match.get("id")
            if mid is not None:
                match_ids.append(str(mid))

    log.info(
        "Year %d │ %d total matches │ %d passed hard filter %s",
        year,
        len(data),
        len(match_ids),
        sorted(allowed_rounds),
    )
    return match_ids


# ─────────────────────────────────────────────────────────────────────────────
# LEVEL 2: Roster Extraction
# ─────────────────────────────────────────────────────────────────────────────
def _extract_player(player_node: dict, team_node: dict, year: int) -> dict:
    """
    Flatten a single player object into the required output schema.
    Applies fallback logic for name and image fields.
    """
    player = player_node.get("player", player_node)

    # Name: prefer internationalName, fallback to translations
    name = player.get("internationalName")
    if not name:
        translations = player.get("translations", {})
        display = translations.get("displayName", {})
        name = display.get("EN") or player.get("name", {}).get("EN", "Unknown")

    # Image: nullable
    image_url = player.get("imageUrl") or None

    # Position: fieldPosition is canonical
    position = player.get("fieldPosition") or player.get("position") or None

    # Team metadata
    team_name = team_node.get("internationalName")
    if not team_name:
        t_translations = team_node.get("translations", {})
        t_display = t_translations.get("displayName", {})
        team_name = t_display.get("EN") or team_node.get("teamName", "Unknown")

    return {
        "player_id": str(player.get("id", "")),
        "name": name,
        "position": position,
        "image_url": image_url,
        "team_id": str(team_node.get("id", team_node.get("teamId", ""))),
        "team_name": team_name,
        "year": year,
    }


def _extract_team_players(
    team_data: dict, year: int
) -> list[dict]:
    """
    Extract all players (field + bench) from a single team node.
    """
    players: list[dict] = []
    for group_key in ("field", "bench"):
        group = team_data.get(group_key, [])
        if not isinstance(group, list):
            continue
        for entry in group:
            try:
                players.append(_extract_player(entry, team_data, year))
            except (KeyError, TypeError) as exc:
                log.warning(
                    "Year %d │ Skipping malformed player in %s: %s",
                    year,
                    group_key,
                    exc,
                )
    return players


async def extract_roster_for_match(
    session: aiohttp.ClientSession, match_id: str, year: int
) -> list[dict]:
    """
    Hit the Lineups endpoint for a single match.
    Parse homeTeam + awayTeam → flattened player records.
    """
    url = LEVEL_2_URL.format(match_id=match_id)

    async with SEMAPHORE:
        # Throttle to stay under the radar
        await asyncio.sleep(random.uniform(2.0, 4.0))
        try:
            async with session.get(url) as resp:
                if resp.status == 404:
                    log.warning(
                        "Match %s (year %d) → 404 (no lineup data)", match_id, year
                    )
                    return []
                resp.raise_for_status()
                data = await resp.json()
        except (ClientError, JSONDecodeError) as exc:
            log.warning(
                "Match %s (year %d) → request/parse error: %s", match_id, year, exc
            )
            return []

    players: list[dict] = []

    for team_key in ("homeTeam", "awayTeam"):
        team_data = data.get(team_key)
        if not team_data or not isinstance(team_data, dict):
            log.warning(
                "Match %s (year %d) → missing or malformed '%s' node",
                match_id,
                year,
                team_key,
            )
            continue
        players.extend(_extract_team_players(team_data, year))

    log.info(
        "Match %s (year %d) │ extracted %d player records", match_id, year, len(players)
    )
    return players


# ─────────────────────────────────────────────────────────────────────────────
# DEDUPLICATION
# ─────────────────────────────────────────────────────────────────────────────
def deduplicate(roster: list[dict]) -> list[dict]:
    """
    Remove duplicate entries based on composite key (player_id, year).
    Retains the first occurrence.
    """
    seen: set[tuple[str, int]] = set()
    unique: list[dict] = []
    for entry in roster:
        key = (entry["player_id"], entry["year"])
        if key not in seen:
            seen.add(key)
            unique.append(entry)
    return unique


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────
async def run_pipeline():
    """
    Two-stage extraction pipeline:
      Stage 1 → Discover qualifying match IDs per season year
      Stage 2 → Extract rosters for every discovered match
    """
    log.info("=" * 70)
    log.info("UCL Historical Roster Extractor — Pipeline Start")
    log.info("Coverage: %d → %d", START_YEAR, END_YEAR)
    log.info("Output:   %s", OUTPUT_FILE)
    log.info("=" * 70)

    master_roster: list[dict] = []

    # Use a single persistent session with pre-configured headers
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(headers=_HEADERS, timeout=timeout) as session:

        # ── LEVEL 1: Match Discovery ─────────────────────────────────────
        year_matches: dict[int, list[str]] = {}
        for year in range(START_YEAR, END_YEAR + 1):
            ids = await discover_matches_for_year(session, year)
            year_matches[year] = ids
            # Small courtesy delay between Level 1 requests
            await asyncio.sleep(random.uniform(1.0, 2.0))

        total_matches = sum(len(v) for v in year_matches.values())
        log.info("─" * 70)
        log.info(
            "Level 1 complete │ %d qualifying matches across %d seasons",
            total_matches,
            END_YEAR - START_YEAR + 1,
        )
        log.info("─" * 70)

        if total_matches == 0:
            log.warning("No matches discovered. Exiting.")
            return

        # ── LEVEL 2: Roster Extraction ───────────────────────────────────
        processed = 0
        for year, match_ids in year_matches.items():
            for mid in match_ids:
                processed += 1
                log.info(
                    "Level 2 │ Processing match %d/%d (id=%s, year=%d)",
                    processed,
                    total_matches,
                    mid,
                    year,
                )
                players = await extract_roster_for_match(session, mid, year)
                master_roster.extend(players)

    # ── DEDUPLICATION ────────────────────────────────────────────────────
    raw_count = len(master_roster)
    master_roster = deduplicate(master_roster)
    deduped_count = len(master_roster)
    log.info("─" * 70)
    log.info(
        "Deduplication │ %d raw → %d unique (removed %d duplicates)",
        raw_count,
        deduped_count,
        raw_count - deduped_count,
    )

    # ── PERSIST ──────────────────────────────────────────────────────────
    OUTPUT_FILE.write_text(
        json.dumps(master_roster, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.info("Output saved → %s (%d player-year records)", OUTPUT_FILE, deduped_count)
    log.info("=" * 70)
    log.info("Pipeline complete.")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(run_pipeline())
