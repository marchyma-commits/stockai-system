import requests
import json
import time

BASE = "http://localhost:5000"

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

results = {}

# Step 1: Backfill
print_section("步驟 1: 回填歷史信號 (POST /api/observer/backfill)")
try:
    resp = requests.post(f"{BASE}/api/observer/backfill", timeout=120)
    data = resp.json()
    print(f"狀態碼: {resp.status_code}")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    results['backfill'] = data
except Exception as e:
    print(f"錯誤: {e}")
    results['backfill'] = {'error': str(e)}

time.sleep(1)

# Step 2: Signal Scan
print_section("步驟 2: 執行今日信號掃描 (POST /api/observer/signal-scan, top_n=200)")
try:
    resp = requests.post(
        f"{BASE}/api/observer/signal-scan",
        json={"top_n": 200},
        timeout=120
    )
    data = resp.json()
    print(f"狀態碼: {resp.status_code}")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    results['signal_scan'] = data
except Exception as e:
    print(f"錯誤: {e}")
    results['signal_scan'] = {'error': str(e)}

time.sleep(1)

# Step 3: Strategy Stats
print_section("步驟 3: 查看策略統計 (GET /api/observer/strategy-stats)")
try:
    resp = requests.get(f"{BASE}/api/observer/strategy-stats", timeout=30)
    data = resp.json()
    print(f"狀態碼: {resp.status_code}")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    results['strategy_stats'] = data
except Exception as e:
    print(f"錯誤: {e}")
    results['strategy_stats'] = {'error': str(e)}

# Step 4: Summary
print_section("掃描結果總結")
bf = results.get('backfill', {})
sc = results.get('signal_scan', {})
st = results.get('strategy_stats', {})

bf_count = bf.get('signals_added', bf.get('count', 'N/A')) if isinstance(bf, dict) else 'N/A'
sc_count = sc.get('signals_found', sc.get('count', 'N/A')) if isinstance(sc, dict) else 'N/A'
sc_total = sc.get('total_scanned', 'N/A') if isinstance(sc, dict) else 'N/A'

print(f"回填信號數量 : {bf_count}")
print(f"掃描股票數量 : {sc_total}")
print(f"今日新信號數 : {sc_count}")

if isinstance(st, dict) and 'strategies' in st:
    print("\n策略勝率概覽:")
    for s in st['strategies']:
        name = s.get('name', s.get('strategy', 'N/A'))
        win = s.get('win_rate', s.get('winRate', 'N/A'))
        total = s.get('total_trades', s.get('totalTrades', 'N/A'))
        print(f"  {name}: 勝率={win}, 交易數={total}")
elif isinstance(st, dict):
    print(f"\n策略統計: {json.dumps(st, ensure_ascii=False)[:300]}")

print_section("完成")
