-- Cross-venue price dispersion per candle: how far apart the venues closed at the
-- same moment. This is the analytical payoff of normalizing three incompatible feeds
-- onto one contract.
--
-- Only settled candles are used. The newest candle per venue is still forming, and
-- its close is whatever the price happened to be mid-interval — comparing a settled
-- close on one venue against a partial close on another manufactures dislocation
-- that is not there. See docs/brief-addendum.md §11.

with ranked as (

    select
        *,
        row_number() over (
            partition by venue, venue_symbol, granularity
            order by candle_start desc
        ) as recency_rank
    from {{ ref('fct_ohlc_candles') }}

),

settled as (

    select * from ranked where recency_rank > 1

),

per_candle as (

    select
        asset_pair,
        granularity,
        candle_start,

        count(*) as venue_count,
        min(close) as min_close,
        max(close) as max_close,
        avg(close) as mean_close,
        sum(volume) as total_volume

    from settled
    group by asset_pair, granularity, candle_start

)

select
    asset_pair,
    granularity,
    candle_start,
    venue_count,

    min_close,
    max_close,
    mean_close,
    max_close - min_close as spread_abs,

    -- Basis points of the cross-venue mean. mean_close is a positive traded price,
    -- so the only way it reaches zero is an upstream data fault; guard rather than
    -- divide by it blindly.
    case
        when mean_close > 0 then (max_close - min_close) / mean_close * 10000
    end as spread_bps,

    total_volume

from per_candle

-- A single venue cannot be dislocated from anything.
where venue_count > 1
