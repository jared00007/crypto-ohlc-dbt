"""Venue definitions for OHLC capture and ingestion.

The three venues return three incompatible payload shapes, and none of that is
reconciled here. Python lands what the venue returned; dbt does the reshaping in
`stg_<venue>__ohlc`. See docs/brief-addendum.md §9.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


def _count_rows(payload: Any) -> int:
    """Binance and Coinbase both return a bare list of candles."""
    return len(payload)


def _count_kraken(payload: Any) -> int:
    """Kraken nests candles under result.<pair>, alongside a scalar `last` cursor.

    The echoed pair key is not the one requested (XBTUSD comes back as XXBTZUSD),
    so select the one non-`last` key rather than hardcoding it.
    """
    for key, value in payload["result"].items():
        if key != "last":
            return len(value)
    return 0


@dataclass(frozen=True)
class Venue:
    name: str
    venue_symbol: str
    granularity: str
    url: str
    params: dict[str, Any]
    fixture_name: str
    count_candles: Callable[[Any], int]
    shape: str


VENUES: tuple[Venue, ...] = (
    Venue(
        name="binance",
        venue_symbol="BTCUSDT",
        granularity="1h",
        url="https://api.binance.com/api/v3/klines",
        params={"symbol": "BTCUSDT", "interval": "1h", "limit": 500},
        fixture_name="btcusdt_1h.json",
        count_candles=_count_rows,
        shape="list of arrays; open time first, milliseconds; prices as strings",
    ),
    Venue(
        name="coinbase",
        venue_symbol="BTC-USD",
        granularity="1h",
        url="https://api.exchange.coinbase.com/products/BTC-USD/candles",
        params={"granularity": 3600},
        fixture_name="btc-usd_1h.json",
        count_candles=_count_rows,
        shape="list of arrays; seconds epoch; low/high/open/close order; prices as floats",
    ),
    Venue(
        name="kraken",
        venue_symbol="XBTUSD",
        granularity="1h",
        url="https://api.kraken.com/0/public/OHLC",
        params={"pair": "XBTUSD", "interval": 60},
        fixture_name="xbtusd_1h.json",
        count_candles=_count_kraken,
        shape="object; candles nested under result.<pair>; seconds epoch; prices as strings",
    ),
)
