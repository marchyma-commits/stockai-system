# Plan: Fix Price Sync Across Endpoints

## Issue
Watchlist, K-line chart, stock detail, and realtime endpoints all show **different prices** for the same stock within the same session, because each endpoint generates prices independently.

## Root Cause (3 discrepancies)

### 1. `get_stock_history` ignores cached price
- `get_stock_info()` caches a price via `_stock_info_cache` (session-level)
- `get_stock_history()` generates OHLCV from `base * 0.8` with independent drift
- **Last candle close ≠ cached price** → chart last close mismatches watchlist price

### 2. `get_realtime` adds micro_change
- Calls `get_stock_info()` (cached price = 546.0)
- Then adds `micro_change = ±1%` → realtime price = 545.5 or 546.5
- **Realtime price ≠ stock info price**

### 3. Analysis page calls both endpoints
- `GET /api/stock/{symbol}` → uses cached price
- `GET /api/stock/{symbol}/history` → independent price sequence
- **Price shown ≠ chart last candle close**

## Solution

### File: `backend/app/services/mock_data_provider.py`

#### Change A — `get_stock_history()`: scale history to converge with cached price

After generating the raw OHLCV sequence, calculate a `scale_factor = cached_price / last_close` and apply it to **all** price fields (open/high/low/close) in the entire history.

This preserves the **relative shape** (volatility, trend direction) while ensuring the **last close matches** the watchlist price.

#### Change B — `get_realtime()`: remove artificial micro_change

Use the exact `base_info["price"]` from cache instead of adding micro_change. Keep the deterministic `_seeded_random` only for volume and bid/ask spread.

## Files Changed

| File | Change |
|------|--------|
| `backend/app/services/mock_data_provider.py` | A: `get_stock_history()` — add post-generation scaling |
| `backend/app/services/mock_data_provider.py` | B: `get_realtime()` — remove micro_change on price |

## Risk Assessment

- **Low risk** — mock data only, no real market data paths affected
- History shape preserved, only absolute values aligned
- No new dependencies, no config changes, no API contract changes
- All existing tests should pass (no functional change)

## Estimated Effort
- Code: ~30 min
- Testing: ~15 min (manual verify browser UI)
- Total: ~45 min
