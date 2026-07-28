-- Coinbase lands 6-element arrays: epoch SECONDS, and the price columns arrive in
-- low/high/open/close order rather than OHLC. Selecting by name here is what makes
-- that harmless — the reorder happens implicitly in the projection below.

with source as (

    select * from {{ source('raw', 'coinbase__ohlc') }}

),

renamed as (

    select
        'coinbase' as venue,
        _venue_symbol as venue_symbol,
        _granularity as granularity,

        {{ epoch_seconds_to_timestamp('"time"') }} as candle_start,

        cast("open" as decimal(38, 18)) as open,
        cast(high as decimal(38, 18)) as high,
        cast(low as decimal(38, 18)) as low,
        cast("close" as decimal(38, 18)) as close,
        cast(volume as decimal(38, 18)) as volume,

        _loaded_at,
        _batch_id

    from source

)

select * from renamed

-- Landing is append-only, so the same candle appears once per batch. Keep the most
-- recently loaded copy: a re-read of a still-forming candle supersedes the earlier
-- one. See docs/brief-addendum.md §11.
qualify row_number() over (
    partition by venue, venue_symbol, granularity, candle_start
    order by _loaded_at desc, _batch_id desc
) = 1
