"""
StockAI Signal Tracker — 策略信號追蹤器
StockAI v1.7 | 2026-04-26

核心功能:
  - 每日記錄所有策略的信號（BUY/SELL/HOLD）
  - N 日後對比實際走勢，統計信號準確率
  - 支持批量掃描自選股
  - 數據持久化到 JSON

使用方式:
  - 獨立腳本: python signal_tracker.py
  - API 調用: from signal_tracker import SignalTracker

信號追蹤邏輯:
  1. 拉取 K 線數據（60 日）
  2. 對每隻股票跑 6 個策略，提取最後一個信號
  3. 記錄日期、股票、策略、信號、當時收盤價
  4. 回填：對歷史信號，計算 N 日後的實際漲跌幅
  5. 統計每個策略的信號勝率
"""

import json, os, time, logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# 數據目錄
DATA_DIR = Path(__file__).parent / 'signal_logs'
DAILY_DIR = DATA_DIR / 'daily'


class SignalTracker:
    """策略信號追蹤器"""

    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.daily_dir = self.data_dir / 'daily'
        self.daily_dir.mkdir(parents=True, exist_ok=True)

    def run_daily_scan(self, stock_analyzer, codes, top_n=50):
        """
        每日掃描 — 對每隻股票跑所有策略，記錄信號

        Args:
            stock_analyzer: StockAnalyzer 實例
            codes: list[str] — 股票代碼列表
            top_n: int — 最多掃描幾隻

        Returns:
            dict — 今日掃描結果
        """
        from backtest_engine import STRATEGIES

        today = datetime.now().strftime('%Y-%m-%d')
        results = []
        total = min(len(codes), top_n)

        logger.info(f"信號追蹤: 開始掃描 {total} 隻股票, {len(STRATEGIES)} 個策略")

        for i, code in enumerate(codes[:top_n]):
            if (i + 1) % 10 == 0:
                logger.info(f"信號追蹤進度: {i+1}/{total}...")

            try:
                # 拉取 K 線
                df = stock_analyzer.get_kline_data(code, days=60)
                if df is None or len(df) < 30:
                    continue

                close = float(df['Close'].iloc[-1])
                date_str = df.index[-1].strftime('%Y-%m-%d')

                # 跑所有策略
                signals = {}
                for strat_key, strat_cls in STRATEGIES.items():
                    try:
                        strategy = strat_cls()
                        sig_list = strategy.generate_signals(df)
                        last_signal = sig_list[-1] if sig_list else 'HOLD'
                        signals[strat_key] = {
                            'signal': last_signal,
                            'strategy_name': strategy.name,
                        }
                    except Exception as e:
                        logger.debug(f"策略 {strat_key} 失敗 {code}: {e}")

                results.append({
                    'code': code,
                    'date': date_str,
                    'price': close,
                    'signals': signals,
                })

                time.sleep(0.3)  # 富途 API 頻率控制

            except Exception as e:
                logger.debug(f"信號追蹤失敗 {code}: {e}")

        # 保存
        record = {
            'scan_date': today,
            'scan_time': datetime.now().strftime('%H:%M:%S'),
            'total_stocks': len(results),
            'stocks': results,
        }

        filepath = self.daily_dir / f"signals_{today}.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        logger.info(f"信號追蹤完成: {len(results)} 隻股票, 保存到 {filepath}")
        return record

    def backfill_outcomes(self, stock_analyzer, lookback_days=None):
        """
        回填歷史信號的實際走勢

        對過去的信號記錄，拉取後續價格，計算 N 日後的漲跌幅。
        N = [3, 5, 10] 個交易日。

        Args:
            stock_analyzer: StockAnalyzer 實例
            lookback_days: int | None — 回填多少天前的記錄（默認全部）

        Returns:
            int — 回填了多少條記錄
        """
        records = self._load_all_records()
        if not records:
            return 0

        horizon_days = [3, 5, 10]  # 觀察窗口
        updated = 0
        today = datetime.now()

        for record in records:
            rec_date = datetime.strptime(record['scan_date'], '%Y-%m-%d')

            # 跳過太新的（還沒有足夠的後續數據）和已經回填的
            if (today - rec_date).days < max(horizon_days) + 2:
                continue
            if record.get('outcomes'):
                continue

            code = record['code']
            entry_price = record.get('price', 0)
            if entry_price <= 0:
                continue

            try:
                # 拉取信號日之後的 K 線
                df = stock_analyzer.get_kline_data(code, days=60)
                if df is None or len(df) < 5:
                    continue

                outcomes = {}
                for h in horizon_days:
                    # 找到信號日之後第 h 個交易日的收盤價
                    sig_date = rec_date
                    future_dates = [d for d in df.index if d > pd.Timestamp(sig_date)]
                    if len(future_dates) >= h:
                        future_price = float(df.loc[future_dates[h - 1], 'Close'])
                        change_pct = round((future_price - entry_price) / entry_price * 100, 2)
                        outcomes[f'day_{h}'] = {
                            'future_price': future_price,
                            'change_pct': change_pct,
                            'direction': 'up' if change_pct > 0 else 'down' if change_pct < 0 else 'flat',
                        }

                if outcomes:
                    record['outcomes'] = outcomes
                    updated += 1

                time.sleep(0.3)

            except Exception as e:
                logger.debug(f"回填失敗 {code} {record['scan_date']}: {e}")

        if updated > 0:
            # 重新保存所有記錄（按日期分組）
            self._save_records(records)
            logger.info(f"回填完成: {updated} 條記錄")

        return updated

    def get_strategy_stats(self, horizon=5):
        """
        統計每個策略的信號勝率

        Args:
            horizon: int — 觀察窗口（3/5/10 天）

        Returns:
            dict — 每個策略的統計數據
        """
        records = self._load_all_records()
        key = f'day_{horizon}'

        stats = {}
        all_records = [r for r in records if r.get('outcomes', {}).get(key)]

        for record in all_records:
            entry_signal = record.get('signals', {})
            outcome = record['outcomes'][key]
            actual_dir = outcome['direction']

            for strat_key, sig_info in entry_signal.items():
                signal = sig_info.get('signal', 'HOLD')
                strat_name = sig_info.get('strategy_name', strat_key)

                if strat_key not in stats:
                    stats[strat_key] = {
                        'name': strat_name,
                        'total': 0,
                        'correct': 0,
                        'buy_signals': {'total': 0, 'win': 0, 'avg_change': 0, 'changes': []},
                        'sell_signals': {'total': 0, 'win': 0, 'avg_change': 0, 'changes': []},
                    }

                s = stats[strat_key]
                s['total'] += 1

                change = outcome['change_pct']

                if signal == 'BUY':
                    s['buy_signals']['total'] += 1
                    s['buy_signals']['changes'].append(change)
                    if actual_dir == 'up':
                        s['buy_signals']['win'] += 1
                        s['correct'] += 1
                elif signal == 'SELL':
                    s['sell_signals']['total'] += 1
                    s['sell_signals']['changes'].append(change)
                    if actual_dir == 'down':
                        s['sell_signals']['win'] += 1
                        s['correct'] += 1

        # 計算勝率和平均變化
        for strat_key, s in stats.items():
            s['win_rate'] = round(s['correct'] / max(s['total'], 1) * 100, 1)

            for sig_type in ['buy_signals', 'sell_signals']:
                changes = s[sig_type]['changes']
                s[sig_type]['avg_change'] = round(np.mean(changes), 2) if changes else 0
                s[sig_type]['win_rate'] = round(
                    s[sig_type]['win'] / max(s[sig_type]['total'], 1) * 100, 1
                )
                # 刪掉原始 changes 列表（太大）
                del s[sig_type]['changes']

        return stats

    def get_recent_signals(self, days=7):
        """
        獲取最近 N 天的信號記錄

        Returns:
            list — 最近的信號記錄
        """
        records = self._load_all_records()
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        return [r for r in records if r['scan_date'] >= cutoff]

    def get_stock_consensus(self, days=1):
        """
        股票級信號聚合 — 對每隻股票聚合所有策略投票，生成可執行交易候選

        核心邏輯:
          - 6 個策略對每隻股票各出一個信號 (BUY/SELL/HOLD)
          - 計算買入票數、賣出票數、持有票數
          - 共識度 = max(買入票數, 賣出票數) / 6 × 100
          - 按共識度排序，共識度 ≥ 67% 為強信號

        Args:
            days: int — 取最近幾天的掃描數據（默認今天）

        Returns:
            dict — {
                'scan_date': str,
                'stocks': [
                    {
                        'code': str,
                        'price': float,
                        'buy_count': int,
                        'sell_count': int,
                        'hold_count': int,
                        'consensus': float,       # 0-100
                        'direction': str,         # bullish / bearish / neutral
                        'signal_strength': str,   # strong / moderate / weak / divergence
                        'buy_strategies': [str],
                        'sell_strategies': [str],
                        'hold_strategies': [str],
                    }
                ]
            }
        """
        records = self._load_all_records()
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        recent = [r for r in records if r.get('scan_date', '') >= cutoff]

        if not recent:
            return {'scan_date': datetime.now().strftime('%Y-%m-%d'), 'stocks': []}

        # 取最新的掃描日期
        latest_date = max(r.get('scan_date', '') for r in recent)

        # 按股票分組，取最新日期的記錄
        stock_map = {}
        for r in recent:
            if r.get('scan_date') != latest_date:
                continue
            code = r.get('code', '')
            if code not in stock_map:
                stock_map[code] = {
                    'code': code,
                    'price': r.get('price', 0),
                    'signals': {},
                }
            # 合併策略信號
            for sig_key, sig_info in r.get('signals', {}).items():
                stock_map[code]['signals'][sig_key] = sig_info

        # 聚合投票
        results = []
        for code, data in stock_map.items():
            buy_list = []
            sell_list = []
            hold_list = []

            for strat_key, sig_info in data['signals'].items():
                sig = sig_info.get('signal', 'HOLD')
                name = sig_info.get('strategy_name', strat_key)
                if sig == 'BUY':
                    buy_list.append(name)
                elif sig == 'SELL':
                    sell_list.append(name)
                else:
                    hold_list.append(name)

            buy_count = len(buy_list)
            sell_count = len(sell_list)
            hold_count = len(hold_list)
            total = buy_count + sell_count + hold_count

            if total == 0:
                continue

            # 共識度 = max(買入, 賣出) / 總票數
            consensus = round(max(buy_count, sell_count) / total * 100, 0) if total > 0 else 0

            # 方向判斷
            if buy_count > sell_count:
                direction = 'bullish'
            elif sell_count > buy_count:
                direction = 'bearish'
            else:
                direction = 'neutral'

            # 信號強度
            if consensus >= 83:  # ≥5/6
                signal_strength = 'strong'
            elif consensus >= 67:  # ≥4/6
                signal_strength = 'moderate'
            elif consensus >= 50:  # ≥3/6
                signal_strength = 'weak'
            else:
                signal_strength = 'divergence'

            results.append({
                'code': code,
                'price': data['price'],
                'buy_count': buy_count,
                'sell_count': sell_count,
                'hold_count': hold_count,
                'consensus': consensus,
                'direction': direction,
                'signal_strength': signal_strength,
                'buy_strategies': buy_list,
                'sell_strategies': sell_list,
                'hold_strategies': hold_list,
            })

        # 按共識度降序，bullish 優先
        results.sort(key=lambda x: (
            0 if x['direction'] == 'bullish' else 1 if x['direction'] == 'neutral' else 2,
            -x['consensus'],
        ))

        return {
            'scan_date': latest_date,
            'stocks': results,
        }

    def get_signal_accuracy_trend(self, horizon=5):
        """
        信號準確率趨勢 — 按週統計

        Returns:
            list — 每週的勝率數據
        """
        records = self._load_all_records()
        key = f'day_{horizon}'

        # 按週分組
        weekly = {}
        for r in records:
            if not r.get('outcomes', {}).get(key):
                continue
            date = r['scan_date']
            week_start = (datetime.strptime(date, '%Y-%m-%d') - timedelta(days=datetime.strptime(date, '%Y-%m-%d').weekday())).strftime('%Y-%m-%d')

            if week_start not in weekly:
                weekly[week_start] = {'correct': 0, 'total': 0}

            outcome = r['outcomes'][key]
            for strat_key, sig_info in r.get('signals', {}).items():
                signal = sig_info.get('signal', 'HOLD')
                actual = outcome['direction']
                weekly[week_start]['total'] += 1
                if (signal == 'BUY' and actual == 'up') or (signal == 'SELL' and actual == 'down'):
                    weekly[week_start]['correct'] += 1

        trend = []
        for week in sorted(weekly.keys()):
            w = weekly[week]
            trend.append({
                'week': week,
                'win_rate': round(w['correct'] / max(w['total'], 1) * 100, 1),
                'total_signals': w['total'],
            })

        return trend

    # ── 內部方法 ──

    def _load_all_records(self):
        """加載所有日誌記錄，展平為列表"""
        records = []
        if not self.daily_dir.exists():
            return records

        for filepath in sorted(self.daily_dir.glob('signals_*.json')):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    stocks = data.get('stocks', [])
                    for s in stocks:
                        s['scan_date'] = data.get('scan_date', s.get('scan_date', ''))
                    records.extend(stocks)
            except Exception as e:
                logger.debug(f"加載失敗 {filepath}: {e}")

        return records

    def _save_records(self, records):
        """按 scan_date 分組保存回文件"""
        grouped = {}
        for r in records:
            date = r.get('scan_date', '')
            if date not in grouped:
                grouped[date] = {
                    'scan_date': date,
                    'stocks': [],
                }
            # 清理內部字段
            clean = {k: v for k, v in r.items() if not k.startswith('_')}
            grouped[date]['stocks'].append(clean)

        for date, data in grouped.items():
            filepath = self.daily_dir / f"signals_{date}.json"
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════
#  CLI 入口 — 獨立運行
# ═══════════════════════════════════════════

if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent))

    from stock_analyzer import StockAnalyzer
    from daily_report import load_watchlist

    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    tracker = SignalTracker()

    # 1. 回填歷史信號（先回填，再掃描今天）
    analyzer = StockAnalyzer()
    print("=== 回填歷史信號 ===")
    filled = tracker.backfill_outcomes(analyzer)
    print(f"回填了 {filled} 條記錄")

    # 2. 今日掃描
    codes = load_watchlist()
    print(f"\n=== 今日信號掃描 ({len(codes)} 隻股票) ===")
    result = tracker.run_daily_scan(analyzer, codes, top_n=50)

    # 3. 顯示統計
    print("\n=== 策略勝率統計 (5日窗口) ===")
    stats = tracker.get_strategy_stats(horizon=5)
    for key, s in stats.items():
        buy_wr = s['buy_signals']['win_rate']
        sell_wr = s['sell_signals']['win_rate']
        print(f"  {s['name']:20s} | 總信號: {s['total']:4d} | 買入勝率: {buy_wr:5.1f}% | 賣出勝率: {sell_wr:5.1f}%")

    # 4. 勝率趨勢
    print("\n=== 週勝率趨勢 ===")
    trend = tracker.get_signal_accuracy_trend(horizon=5)
    for t in trend[-4:]:
        print(f"  {t['week']} | 勝率: {t['win_rate']}% | 信號數: {t['total_signals']}")
