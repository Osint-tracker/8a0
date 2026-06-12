"""
rate_players.py
───────────────
Reads database_7a0_master.json, computes a deterministic overall_rating
for each player based on their tier, and writes database_7a0_rated.json.

Determinism is achieved by seeding random.Random() per-player using a
composite key of player_id + year. A dedicated RNG instance is used so
the global random state is never touched.
"""

import json
import hashlib
import random
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────
INPUT_FILE  = Path(__file__).parent.parent / "Downloads" / "database_7a0_master.json"
OUTPUT_FILE = Path(__file__).parent / "database_7a0_rated.json"

TIER_RANGES: dict[str, tuple[int, int]] = {
    "S": (94, 99),
    "A": (88, 93),
    "B": (80, 87),
    "C": (75, 79),
    "D": (65, 74),
}
FALLBACK_RATING = 70


def compute_rating(player: dict) -> int:
    """Return a deterministic overall_rating for a single player."""
    tier = player.get("tier", "")
    low, high = TIER_RANGES.get(tier, (FALLBACK_RATING, FALLBACK_RATING))

    # Build a deterministic seed from player_id + year
    seed_string = f"{player['player_id']}_{player['year']}"
    # Use a hash so the seed is always a well-distributed integer
    seed_value = int(hashlib.sha256(seed_string.encode("utf-8")).hexdigest(), 16)

    # Per-player RNG — never touches the global state
    rng = random.Random(seed_value)
    return rng.randint(low, high)


def main() -> None:
    print(f"[*] Loading  : {INPUT_FILE}")
    with open(INPUT_FILE, "r", encoding="utf-8") as fh:
        players: list[dict] = json.load(fh)
    print(f"[*] Players  : {len(players):,}")

    for player in players:
        player["overall_rating"] = compute_rating(player)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(players, fh, ensure_ascii=False, indent=4)
    print(f"[OK] Saved   : {OUTPUT_FILE}")

    # Quick sanity check — show first 5 entries
    for p in players[:5]:
        print(f"    {p['name']:30s}  tier={p['tier']}  rating={p['overall_rating']}")


if __name__ == "__main__":
    main()
