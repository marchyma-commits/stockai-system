import requests
import json

base = 'http://localhost:5000'

# 重新調用 signal-scan 拿原始數據（含 name）
r = requests.post(f'{base}/api/observer/signal-scan', json={'top_n': 200}, timeout=300)
data = r.json()
stocks = data.get('data', {}).get('stocks', [])

# 只看 strong buy 和 strong sell 的股票
strong_buys = []
strong_sells = []

for s in stocks:
    code = s.get('code', '?')
    price = s.get('price', '')
    signals = s.get('signals', {})
    
    if not isinstance(signals, dict):
        continue
    
    buy_votes = sum(1 for sd in signals.values() if isinstance(sd, dict) and 'BUY' in str(sd.get('signal', '')).upper())
    sell_votes = sum(1 for sd in signals.values() if isinstance(sd, dict) and 'SELL' in str(sd.get('signal', '')).upper())
    
    info = {'code': code, 'price': price, 'B': buy_votes, 'S': sell_votes}
    
    # 看原始數據有冇 name
    for k in ['name', 'stock_name', 'company_name']:
        if k in s and s[k]:
            info['name'] = s[k]
            break
    
    # 看 signals 裡有冇嵌套的 name
    if 'name' not in info:
        for sn, sd in signals.items():
            if isinstance(sd, dict) and 'name' in sd:
                info['name'] = sd['name']
                break
    
    if buy_votes >= 2:
        strong_buys.append(info)
    elif sell_votes >= 2:
        strong_sells.append(info)

print('=== Strong BUY stocks (raw data) ===')
for sb in strong_buys:
    print(f'  {sb}')

print('\n=== Strong SELL stocks (raw data) ===')
for ss in strong_sells:
    print(f'  {ss}')
