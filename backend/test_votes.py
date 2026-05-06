"""调试 votes 数据结构"""
from daily_report import DataFetcher, get_strategy_votes
import json

f = DataFetcher()
ok = f.connect()
if ok:
    try:
        df = f.get_kline('00700')
        print(f'K线 rows: {len(df)}')
        votes = get_strategy_votes(df)
        print(f'Votes keys: {list(votes.keys())}')
        for k, v in votes.items():
            print(f'  {k}: {v}')
            if isinstance(v, dict):
                print(f'    -> keys: {list(v.keys())}')
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        f.close()
