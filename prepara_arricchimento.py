"""
=============================================================================
  prepara_arricchimento.py
  Splits historical_rosters_1955_2012.json into decade-based text batches
  ready for LLM enrichment (team fix + rating assignment).
=============================================================================
"""

import json
import sys
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
INPUT_FILE = Path(__file__).parent / "historical_rosters_1955_2012.json"
OUTPUT_DIR = Path(__file__).parent / "output_batches"

# ── Decade boundaries ────────────────────────────────────────────────────────
DECADES = [
    (1955, 1964),
    (1965, 1974),
    (1975, 1984),
    (1985, 1994),
    (1995, 2004),
    (2005, 2012),
]


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    # 1. Load the JSON roster
    print(f"Loading {INPUT_FILE} ...")
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        roster: list[dict] = json.load(f)
    print(f"  -> {len(roster)} raw player-year records loaded.")

    # 2. Deduplicate exact (player_id, year) pairs — keep first occurrence
    seen: set[tuple[str, int]] = set()
    unique: list[dict] = []
    for entry in roster:
        key = (str(entry["player_id"]), int(entry["year"]))
        if key not in seen:
            seen.add(key)
            unique.append(entry)

    dupes_removed = len(roster) - len(unique)
    print(f"  → {len(unique)} unique after dedup (removed {dupes_removed} exact duplicates).")

    # 3. Bucket players into decades
    buckets: dict[tuple[int, int], list[dict]] = {d: [] for d in DECADES}
    orphans = 0
    for entry in unique:
        year = int(entry["year"])
        placed = False
        for start, end in DECADES:
            if start <= year <= end:
                buckets[(start, end)].append(entry)
                placed = True
                break
        if not placed:
            orphans += 1

    if orphans:
        print(f"  ⚠ {orphans} records fell outside all decade ranges.")

    # 4. Write one text file per decade
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for (start, end), players in buckets.items():
        if not players:
            print(f"  Decade {start}-{end}: empty, skipping.")
            continue

        # Sort by year then by name for readability
        players.sort(key=lambda p: (int(p["year"]), p.get("name", "")))

        out_path = OUTPUT_DIR / f"batch_{start}_{end}.txt"
        with open(out_path, "w", encoding="utf-8") as f:
            for p in players:
                pid = p.get("player_id", "")
                name = p.get("name", "Unknown")
                year = p.get("year", "")
                position = p.get("position", "") or ""
                team_name = p.get("team_name", "") or "Unknown"
                f.write(f"{pid} | {name} | {year} | {position} | {team_name}\n")

        print(f"  Decade {start}-{end}: {len(players)} records → {out_path.name}")

    print("\nDone. Batch files ready in:", OUTPUT_DIR)


if __name__ == "__main__":
    main()
