#!/usr/bin/env python3
"""Verify reset state without modifying database or artifacts."""

import argparse
import json
from pathlib import Path

from reset_database import DatabaseResetter
from reset_artifacts import ArtifactResetter


def verify(minimum_candles=1_000_000):
    resetter = DatabaseResetter()
    tables, counts, candles = resetter.inspect()
    artifacts = ArtifactResetter().artifacts()
    marker = Path(__file__).resolve().parents[1] / "models" / ".clean_state"
    clean = all(counts[table] == 0 for table in tables) and candles[0] >= minimum_candles and not artifacts and marker.exists()
    return {"clean": clean, "table_counts": counts, "gold_price_candles": {
        "count": candles[0], "minimum": candles[1], "maximum": candles[2]},
        "remaining_artifacts": [str(path) for path in artifacts], "clean_state_marker": str(marker) if marker.exists() else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minimum-candles", type=int, default=1_000_000)
    args = parser.parse_args()
    result = verify(args.minimum_candles)
    print(json.dumps(result, indent=2, default=str))
    raise SystemExit(0 if result["clean"] else 1)


if __name__ == "__main__":
    main()
