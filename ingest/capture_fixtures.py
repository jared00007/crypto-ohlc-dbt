"""Capture live venue payloads into data/fixtures/ so CI can build offline.

Run once from a machine with network access:

    uv run python -m ingest.capture_fixtures

Payloads are written exactly as the venue returned them — no reshaping, no key
reordering — so the committed fixtures exercise the same parsing path as a live
pull. Commit data/fixtures/ afterwards. See docs/brief-addendum.md §10.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

from ingest.venues import VENUES, Venue

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "data" / "fixtures"
TIMEOUT_SECONDS = 30.0
USER_AGENT = "crypto-ohlc-dbt/0.1 (fixture capture)"


def capture(client: httpx.Client, venue: Venue) -> tuple[Path, int]:
    """Fetch one venue's candles and write them verbatim to its fixture file."""
    response = client.get(venue.url, params=venue.params)
    response.raise_for_status()
    payload = response.json()

    destination = FIXTURE_ROOT / venue.name / venue.fixture_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2) + "\n")
    return destination, venue.count_candles(payload)


def main() -> int:
    failures: list[str] = []

    with httpx.Client(timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}) as client:
        for venue in VENUES:
            try:
                destination, candles = capture(client, venue)
            except Exception as exc:  # noqa: BLE001 - report and continue to the next venue
                failures.append(venue.name)
                print(f"  FAIL  {venue.name}: {exc}", file=sys.stderr)
                continue
            print(f"  ok    {venue.name:<9} {candles:>4} candles -> {destination.relative_to(REPO_ROOT)}")

    if failures:
        print(f"\n{len(failures)} of {len(VENUES)} venues failed: {', '.join(failures)}", file=sys.stderr)
        return 1

    print("\nAll fixtures captured. Commit data/fixtures/ to make CI reproducible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
