"""Venue definitions for OHLC capture and ingestion.

The three venues return three incompatible payload shapes, and none of that is
reconciled here. Python lands what the venue returned, under the venue's own
column names and order; dbt does the reshaping in `stg_<venue>__ohlc`.
See docs/brief-addendum.md §9.

Prices land as VARCHAR or DECIMAL, never FLOAT. Venues that quote prices as JSON
strings keep them as strings; Coinbase quotes them as JSON numbers, so the loader
parses with `Decimal` and lands DECIMAL — the text in the payload is preserved
exactly either way.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Wide enough for any crypto price or size we will see, and exact.
_DECIMAL = "DECIMAL(38,18)"


def _rows_as_returned(payload: Any) -> list[Any]:
    """Binance.US and Coinbase return a bare list of candles."""
    return payload


def _rows_from_kraken(payload: Any) -> list[Any]:
    """Kraken nests candles under result.<pair>, alongside a scalar `last` cursor.

    Unwrapping the envelope is navigation, not reshaping — the rows themselves are
    landed exactly as returned. The echoed pair key differs from the one requested
    (XBTUSD comes back as XXBTZUSD), so select the one non-`last` key.
    """
    for key, value in payload["result"].items():
        if key != "last":
            return value
    return []


@dataclass(frozen=True)
class Venue:
    name: str
    venue_symbol: str
    granularity: str
    url: str
    params: dict[str, Any]
    fixture_name: str
    extract_rows: Callable[[Any], list[Any]]
    shape: str
    columns: tuple[tuple[str, str], ...]

    @property
    def table(self) -> str:
        return f"{self.name}__ohlc"


VENUES: tuple[Venue, ...] = (
    Venue(
        # Binance.US, not Binance global: the latter answers 451 to US IPs. It is
        # also the more honest label — separate entity, separate liquidity, which
        # matters once we compare venues for dislocation.
        name="binance_us",
        venue_symbol="BTCUSDT",
        granularity="1h",
        url="https://api.binance.us/api/v3/klines",
        params={"symbol": "BTCUSDT", "interval": "1h", "limit": 500},
        fixture_name="btcusdt_1h.json",
        extract_rows=_rows_as_returned,
        shape="list of 12-element arrays; open time first, milliseconds; prices as strings",
        columns=(
            ("open_time", "BIGINT"),
            ("open", "VARCHAR"),
            ("high", "VARCHAR"),
            ("low", "VARCHAR"),
            ("close", "VARCHAR"),
            ("volume", "VARCHAR"),
            ("close_time", "BIGINT"),
            ("quote_asset_volume", "VARCHAR"),
            ("number_of_trades", "BIGINT"),
            ("taker_buy_base_asset_volume", "VARCHAR"),
            ("taker_buy_quote_asset_volume", "VARCHAR"),
            ("ignore", "VARCHAR"),
        ),
    ),
    Venue(
        name="coinbase",
        venue_symbol="BTC-USD",
        granularity="1h",
        url="https://api.exchange.coinbase.com/products/BTC-USD/candles",
        params={"granularity": 3600},
        fixture_name="btc-usd_1h.json",
        extract_rows=_rows_as_returned,
        # Note the column order: low and high precede open and close.
        shape="list of 6-element arrays; seconds epoch; low/high/open/close order; JSON numbers",
        columns=(
            ("time", "BIGINT"),
            ("low", _DECIMAL),
            ("high", _DECIMAL),
            ("open", _DECIMAL),
            ("close", _DECIMAL),
            ("volume", _DECIMAL),
        ),
    ),
    Venue(
        name="kraken",
        venue_symbol="XBTUSD",
        granularity="1h",
        url="https://api.kraken.com/0/public/OHLC",
        params={"pair": "XBTUSD", "interval": 60},
        fixture_name="xbtusd_1h.json",
        extract_rows=_rows_from_kraken,
        shape="object; candles nested under result.<pair>; seconds epoch; prices as strings",
        columns=(
            ("time", "BIGINT"),
            ("open", "VARCHAR"),
            ("high", "VARCHAR"),
            ("low", "VARCHAR"),
            ("close", "VARCHAR"),
            ("vwap", "VARCHAR"),
            ("volume", "VARCHAR"),
            ("count", "BIGINT"),
        ),
    ),
)

VENUES_BY_NAME = {venue.name: venue for venue in VENUES}
