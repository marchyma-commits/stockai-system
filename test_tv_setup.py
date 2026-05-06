import sys, json, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, 'backend')

from tradingview_adapter import FutuTradingViewAdapter

adapter = FutuTradingViewAdapter()

# 测试 00700 腾讯
result = adapter.calculate_technical_indicators('00700')
if result.get('success'):
    ts = result.get('trade_setup')
    tq = result.get('trade_quality')
    print(f'=== 00700 ===')
    print(f'close = {result["indicators"].get("close"):.2f}')
    print(f'ema_20 = {result["indicators"].get("ema_20")}')
    print(f'ema_50 = {result["indicators"].get("ema_50")}')
    print(f'ema_200 = {result["indicators"].get("ema_200")}')
    print(f'adx = {result["indicators"].get("adx")}')
    print(f'\ntrade_setup = {json.dumps(ts, indent=2, default=str) if ts else "None"}')
    print(f'\ntrade_quality = {json.dumps(tq, indent=2, default=str) if tq else "None"}')
else:
    print(f'00700 FAILED: {result.get("error")}')
    # 试试从 OHLC 缓存加载
    print('\nTrying with cached data...')
    import pandas as pd
    kline = adapter.get_kline_data('00700', days=250)
    if kline.get('success'):
        df = pd.DataFrame(kline['ohlc'])
        indicators = adapter.indicators.calculate_all(df)
        latest = df.iloc[-1].to_dict()
        ts = adapter.indicators.compute_trade_setup_from_indicators(indicators, latest)
        tq = adapter.indicators.compute_trade_quality_from_indicators(indicators, latest, ts) if ts else None
        print(f'close = {indicators.get("close"):.2f}')
        print(f'ema_20 = {indicators.get("ema_20")}')
        print(f'ema_50 = {indicators.get("ema_50")}')
        print(f'ema_200 = {indicators.get("ema_200")}')
        print(f'adx = {indicators.get("adx")}')
        print(f'\ntrade_setup = {json.dumps(ts, indent=2, default=str) if ts else "None"}')
        print(f'\ntrade_quality = {json.dumps(tq, indent=2, default=str) if tq else "None"}')
    else:
        print(f'No kline data: {kline.get("error")}')
