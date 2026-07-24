# V25 Integrity Diagnostics

This document describes the passive integrity diagnostics introduced in
V25.1.5 and the compact operational report introduced in V25.1.6.

## Safety boundary

Integrity diagnostics are observation-only.

Market-integrity observations are collected during fixture analysis, but they
must never feed back into the production decision path. The compact operational
report is built only after the existing model, value, pick-selection, staking
and portfolio-exposure flow has completed.

Neither the observations nor the report may alter:

- model probabilities or calibration;
- confidence, edge or data-quality thresholds;
- VALUE_PICK, WATCHLIST or NO_BET decisions;
- staking or exposure limits;
- bookmaker or odds selection;
- Telegram notifications;
- settlement behaviour;
- database-write policy.

The diagnostic output is added to `output/daily_summary.txt`.

## Daily-summary sections

### `integrity_diagnostics`

Market-level observations collected during fixture analysis.

Important fields:

- `fixtures_analyzed`
- `fixtures_with_any_odds`
- `fixtures_without_any_odds`
- `odds_rows_analyzed`
- `odds_fresh`
- `odds_not_fresh`
- `market_available`
- `market_complete`
- `market_incomplete`
- `market_cleansing_success`
- `market_cleansing_failed`
- `baseline_source_counts`
- `reason_counts`

Market counters are split by market, including:

- `1X2`
- `BTTS`
- `OVER_UNDER_2_5`

`baseline_source_counts` shows whether the market baseline used:

- `sharp`
- `all_bookmakers`

Use of `all_bookmakers` is diagnostic information. It does not change the
existing selection rules.

### `odds_discovery`

Observations collected by the bulk odds-discovery flow.

Important fields include:

- `enabled`
- `bulk_enabled`
- `fixtures_scanned_total`
- `fixtures_considered_for_odds`
- `fixtures_with_odds`
- `fixtures_without_odds`
- `odds_rows_discovered`
- `odds_rows_written`
- `odds_provider_errors`
- `selected_with_odds`
- `selected_without_odds`
- `request_limit_reached`
- `pagination_queries_truncated`
- `reason_counts`

### `operational_integrity`

V25.1.6 adds a compact view derived only from the two existing diagnostic
sections and the already-finalized pick summary.

Structure:

- `status`
- `picks`
- `fixtures`
- `odds`
- `markets`
- `alerts`
- `reason_counts`

The report does not recalculate or mutate picks.

## Operational statuses

### `HEALTHY`

No active operational alert was detected.

Expected discovery gaps can still be present in `reason_counts`. Examples
include fixtures outside the discovery window or fixtures for which bookmakers
have not yet published odds.

### `OBSERVE`

A non-critical condition should be followed across subsequent natural runs.

Current provisional `OBSERVE` alerts:

- `INCOMPLETE_MARKETS`
- `ALL_BOOKMAKERS_FALLBACK_USED`
- `ODDS_DISCOVERY_DISABLED`
- `ODDS_DISCOVERY_BULK_DISABLED`
- `ODDS_PROVIDER_DISABLED`

### `INVESTIGATE`

An active integrity condition requires inspection of the run logs and artifact.

Current provisional `INVESTIGATE` alerts:

- `STALE_ODDS`
- `MARKET_CLEANSING_FAILURE`
- `ODDS_PROVIDER_ERROR`
- `SELECTED_WITHOUT_ODDS`
- `ODDS_REQUEST_LIMIT_REACHED`
- `ODDS_PAGINATION_TRUNCATED`

`INVESTIGATE` is an operational label only. It does not block, downgrade or
rewrite picks.

## Preliminary signal thresholds

The V25.1.6 thresholds are intentionally conservative and binary.

| Signal | Preliminary rule | Status |
|---|---:|---|
| Stale analyzed odds | greater than 0 | `INVESTIGATE` |
| Market-cleansing failures | greater than 0 | `INVESTIGATE` |
| Provider request errors | greater than 0 | `INVESTIGATE` |
| Selected fixtures without odds | greater than 0 | `INVESTIGATE` |
| Odds request limit reached | true | `INVESTIGATE` |
| Truncated pagination queries | greater than 0 | `INVESTIGATE` |
| Incomplete analyzed markets | greater than 0 | `OBSERVE` |
| All-bookmakers fallback use | greater than 0 | `OBSERVE` |
| Discovery disabled | false-enabled state | `OBSERVE` |
| Bulk discovery disabled | false-enabled state | `OBSERVE` |
| Provider disabled | reason present | `OBSERVE` |

These thresholds are preliminary. They should be evaluated against several
natural scheduled runs before any future adjustment.

## Odds-discovery reason codes

The discovery flow can report:

- `MISSING_FIXTURE_API_ID`
- `INVALID_KICKOFF_UTC`
- `OUTSIDE_DISCOVERY_WINDOW`
- `MISSING_LEAGUE_API_ID`
- `ODDS_DISCOVERY_DISABLED`
- `ODDS_DISCOVERY_BULK_DISABLED`
- `ODDS_PROVIDER_DISABLED`
- `ODDS_PROVIDER_REQUEST_ERROR`
- `ODDS_PROVIDER_ZERO_RESULTS`
- `ODDS_REQUEST_LIMIT_REACHED`
- `ODDS_PAGINATION_TRUNCATED`
- `NO_DISCOVERED_ODDS_FOR_FIXTURE`

Not every discovery reason is an alert.

In particular, the following can occur normally during a broad fixture scan
and do not independently change a `HEALTHY` status:

- `OUTSIDE_DISCOVERY_WINDOW`
- `MISSING_FIXTURE_API_ID`
- `NO_DISCOVERED_ODDS_FOR_FIXTURE`
- `ODDS_PROVIDER_ZERO_RESULTS`

Their counts remain visible for trend analysis.

## Market-integrity reason codes

The analysis diagnostics can report:

- `NO_ODDS_AVAILABLE`
- `ODDS_NOT_FRESH`
- `<MARKET>_NOT_AVAILABLE`
- `<MARKET>_INCOMPLETE`
- `<MARKET>_CLEANSING_ERROR`

`<MARKET>` is replaced by the relevant market identifier, such as `1X2`,
`BTTS` or `OVER_UNDER_2_5`.

## Canary review

For each natural scheduled canary run:

1. Confirm the run used the expected branch and exact release commit.
2. Confirm the workflow completed successfully.
3. Inspect `operational_integrity.status`.
4. Review every entry in `alerts`.
5. Review both diagnostic `reason_counts` sections.
6. Compare counts with the preceding natural runs.
7. Confirm the output artifact was uploaded.

A single `OBSERVE` result is not automatically a release failure. Repeated or
unexpected changes should be investigated before promotion.

Any `INVESTIGATE` result must be inspected before the run is accepted as a
healthy canary run.
