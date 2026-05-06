import sys, json, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, 'backend')

import pandas as pd
import numpy as np
from tradingview_adapter import TradingViewIndicators

si = TradingViewIndicators()

# 测试多种 R:R 场景
scenarios = [
    # (desc, close, trend_factor, vol_factor)
    ("强趋势高波动", 380, 0.3, 1.5),
    ("中等趋势", 100, 0.15, 1.0),
    ("弱趋势低波动", 50, 0.05, 0.8),
    ("横盘整理", 200, 0.02, 0.7),
]

for desc, base_close, trend, vol_mult in scenarios:
    np.random.seed(int(base_close))
    n = 250
    close = np.cumsum(np.random.randn(n) * trend * 10) + base_close
    df = pd.DataFrame({
        'open': close + np.random.randn(n) * base_close * 0.005,
        'high': close + abs(np.random.randn(n)) * base_close * 0.015,
        'low': close - abs(np.random.randn(n)) * base_close * 0.015,
        'close': close,
        'volume': np.random.randint(500000, 5000000, n) * vol_mult
    })

    indicators = si.calculate_all(df)
    latest = df.iloc[-1].to_dict()

    setup = si.compute_trade_setup_from_indicators(indicators, latest)
    if not setup:
        print(f"\n=== {desc} (close={close[-1]:.1f}) === NO SETUP")
        continue

    rr2 = setup.get('risk_reward', {}).get('to_target_2')
    print(f"\n=== {desc} (close={close[-1]:.1f}, R:R2={rr2}) ===")

    # 原版 TV MCP
    from tradingview_mcp.core.services.indicators import compute_trade_quality
    tv = si.to_tv_format(indicators, latest)
    stock_score = si._quick_stock_score(indicators, latest)
    orig = compute_trade_quality(tv, stock_score, setup)
    print(f"  TV原版: {orig['trade_quality_score']}分 {orig['quality']}")
    print(f"    breakdown: {orig['breakdown']}")

    # 港股适配版
    hk = si.compute_trade_quality_hk(indicators, latest, setup)
    print(f"  港股版: {hk['trade_quality_score']}分 {hk['quality']}")
    print(f"    breakdown: {hk['breakdown']}")
