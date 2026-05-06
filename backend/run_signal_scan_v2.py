import requests
import json

BASE = "http://localhost:5000"

# Step 1: Backfill
print("=== 步驟1: 回填歷史信號 ===")
r1 = requests.post(f"{BASE}/api/observer/backfill", timeout=120)
bf = r1.json()
print(json.dumps(bf, ensure_ascii=False, indent=2))

# Step 2: Signal Scan
print("\n=== 步驟2: 今日信號掃描 (top_n=200) ===")
r2 = requests.post(f"{BASE}/api/observer/signal-scan", json={"top_n": 200}, timeout=120)
sc = r2.json()
print(json.dumps(sc, ensure_ascii=False, indent=2))

# Step 3: Strategy Stats
print("\n=== 步驟3: 策略統計 ===")
r3 = requests.get(f"{BASE}/api/observer/strategy-stats", timeout=30)
st = r3.json()
print(json.dumps(st, ensure_ascii=False, indent=2))

# Summary
print("\n\n" + "="*60)
print("  掃描結果總結")
print("="*60)

bf_updated = bf.get("updated", bf.get("signals_added", 0))
print(f"回填信號數量 : {bf_updated}")

if sc.get("success"):
    data = sc.get("data", {})
    total = data.get("total_stocks", "N/A")
    stocks = data.get("stocks", [])
    # Count actual BUY/SELL signals
    buy_count = 0
    sell_count = 0
    hold_count = 0
    for s in stocks:
        signals = s.get("signals", {})
        for strategy, info in signals.items():
            sig = info.get("signal", "HOLD")
            if sig == "BUY":
                buy_count += 1
            elif sig == "SELL":
                sell_count += 1
            else:
                hold_count += 1
    print(f"掃描股票數量 : {total}")
    print(f"有信號股票     : {len(stocks)} 隻")
    print(f"  BUY 信號總數 : {buy_count}")
    print(f"  SELL 信號總數: {sell_count}")
    print(f"  HOLD 信號總數: {hold_count}")
else:
    print(f"掃描失敗: {sc}")

print(f"\n近期信號總數 (5日): {st.get('recent_signal_count', 'N/A')}")
print(f"策略統計資料    : {json.dumps(st.get('stats', {}), ensure_ascii=False)}")
print("="*60)
