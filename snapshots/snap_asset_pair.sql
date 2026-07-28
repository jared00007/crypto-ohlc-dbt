{% snapshot snap_asset_pair %}

{{
    config(
        unique_key='venue_pair_key',
        strategy='check',
        check_cols=['asset_pair', 'base_asset', 'quote_asset'],
    )
}}

{#
    SCD2 history of how each venue's native symbol maps to a canonical asset pair.

    Strategy is `check`, not `timestamp`, because the source is a hand-maintained
    seed with no trustworthy updated_at column. `timestamp` needs a field the source
    reliably bumps on every edit; inventing one on a seed would mean the snapshot
    silently misses changes whenever the column was not updated by hand. `check`
    compares the tracked columns instead, which is the honest choice when the source
    cannot vouch for its own modification time. The trade is cost — every run
    compares column values rather than one timestamp — which is irrelevant at three
    rows and would matter at scale.

    Stated plainly, per docs/brief-addendum.md §12: this is a learning exercise for
    SCD2 mechanics. Public candle endpoints expose almost no genuinely drifting pair
    metadata, so the drift this captures is drift we introduce by editing the seed.
    It is not load-bearing for any downstream model.
#}

select
    {{ dbt_utils.generate_surrogate_key(['venue', 'venue_symbol']) }} as venue_pair_key,
    venue,
    venue_symbol,
    asset_pair,
    base_asset,
    quote_asset
from {{ ref('venue_pair_map') }}

{% endsnapshot %}
