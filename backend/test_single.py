"""测试个股分析端到端"""
from daily_report import DataFetcher, generate_single_stock_report, render_single_html
from datetime import datetime

f = DataFetcher()
ok = f.connect()
print(f'Connect: {ok}')
if ok:
    try:
        a = generate_single_stock_report(f, '00700')
        if 'error' in a:
            print(f'Error: {a.get("error")}')
        else:
            print(f'OK: {a.get("name")} price={a.get("current_price")} cf={a.get("capital_flow")}')
            h = render_single_html(a, datetime.now())
            print(f'HTML length: {len(h)}')
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        f.close()
