import sys, json, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, 'backend')

import pandas as pd
import numpy as np
from tradingview_adapter import TradingViewIndicators

si = TradingViewIndicators()

scenarios = [
    ("腾讯 00700", 380, 20000000, 0.3, 1.5),
    ("美团 03690", 150, 8000000, 0.25, 1.2),
    ("中芯 00981", 18, 30000000, 0.15, 1.0),
    ("细价股", 2.5, 5000000, 0.05, 0.8),
]

for desc, base_close, base_vol, trend, vol_mult in scenarios:
    np.random.seed(int(base_close * 100))
    n = 250
    close = np.cumsum(np.random.randn(n) * trend * 5) + base_close
    df = pd.DataFrame({
        'open': close + np.random.randn(n) * base_close * 0.005,
        'high': close + abs(np.random.randn(n)) * base_close * 0.02,
        'low': close - abs(np.random.randn(n)) * base_close * 0.02,
        'close': close,
        'volume': np.random.randint(int(base_vol * 0.5), int(base_vol * 1.5), n)
    })

    indicators = si.calculate_all(df)
    latest = df.iloc[-1].to_dict()
    setup = si.compute_trade_setup_from_indicators(indicators, latest)
    if not setup:
        print(f"{desc}: NO SETUP")
        continue

    hk = si.compute_trade_quality_hk(indicators, latest, setup)
    bd = hk['breakdown']
    stop_pct = setup.get('stop_distance_pct', 0)
    rr2 = setup.get('risk_reward', {}).get('to_target_2', 0)
    print(f"{desc}: {hk['trade_quality_score']}分 {hk['quality']} | stop={stop_pct:.1f}% R:R={rr2}")
    print(f"  结构 {bd['structure_quality']}/30 | R:R {bd['risk_reward']}/30 | 量能 {bd['volume_confirmation']}/20 | 止损 {bd['stop_quality']}/10 | 流动 {bd['liquidity']}/10")
