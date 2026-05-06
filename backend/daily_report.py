"""
StockAI Daily Trading Report — 每日交易建議報告生成器
StockAI v1.7 | 2026-04-24

功能:
  1. 讀取 Paper Trading 當前持倉
  2. 調用富途 OpenD 獲取即時 K 線數據
  3. 跑 5 個回測策略信號投票
  4. 計算支撐位/阻力位/ATR 止損
  5. 生成 Markdown 報告 + JSON 結果
  6. 單股資金流向分析報告 (--mode single)
  7. Top 200 體檢+資金流向掃描排行榜 (--mode scan)

用法:
  python daily_report.py                          # 默認（持倉報告）
  python daily_report.py --output ./             # 指定輸出目錄
  python daily_report.py --no-futu               # 不連富途（測試用）
  python daily_report.py --mode single --code 00700  # 單股分析
  python daily_report.py --mode scan                 # Top200 掃描
"""

import json, os, sys, math, argparse, logging, time
from datetime import datetime, timedelta
from pathlib import Path

# 加入 backend 目錄到 path
BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

import pandas as pd
import numpy as np
from futu import *

# ── 導入現有模組 ──
from backtest_engine import (
    BacktestEngine, STRATEGIES,
    EMACrossStrategy, MACDStrategy, RSIStrategy, BollingerStrategy, CompositeStrategy
)
from paper_trading_agent import PaperAccount
from fundamental_analyzer import FundamentalAnalyzer

# ═══════════════════════════════════════════
#  資料庫路徑
# ═══════════════════════════════════════════

CACHE_DIR = Path('C:/Users/MarcoMa/stockai_data/cache')
WATCHLIST_PATH = Path('C:/Users/MarcoMa/stockai_data/watchlist.json')


def load_watchlist():
    """加載自選股列表"""
    if WATCHLIST_PATH.exists():
        data = json.loads(WATCHLIST_PATH.read_text(encoding='utf-8'))
        stocks = data.get('stocks', [])
        return [s.replace('.HK', '').replace('.hk', '') for s in stocks]
    return []


def load_health_scores(fa_analyzer, stock_codes, top_n=200, quote_ctx=None):
    """
    對自選股做體檢評分，返回 Top N
    
    Args:
        fa_analyzer: FundamentalAnalyzer 实例
        stock_codes: 股票代码列表
        top_n: 返回 Top N
        quote_ctx: 可选的富途连接上下文（避免重复创建连接）
    
    Returns:
        list: [{'code': '00700', 'name': '騰訊控股', 'score': 8, 'total': 9, 'grade': 'A+', ...}, ...]
    """
    results = []
    total = len(stock_codes)
    for i, code in enumerate(stock_codes):
        if (i + 1) % 20 == 0:
            logger.info(f"體檢進度: {i+1}/{total}...")
        try:
            hc = fa_analyzer.health_check(code, quote_ctx=quote_ctx)
            if 'error' in hc and not hc.get('no_financial_data'):
                continue
            score = hc.get('score', 0)
            if score <= 0:
                continue
            results.append({
                'code': code,
                'name': hc.get('company_name', code),
                'score': score,
                'total': hc.get('total', 9),
                'grade': hc.get('grade', 'N/A'),
                'checks': hc.get('checks', []),
            })
        except Exception as e:
            logger.debug(f"體檢失敗 {code}: {e}")

    # 按 score 降序，score 同按 grade
    grade_rank = {'A+': 10, 'A': 9, 'B+': 8, 'B': 7, 'C+': 6, 'C': 5, 'D': 4, 'N/A': 0}
    results.sort(key=lambda x: (x['score'], grade_rank.get(x['grade'], 0)), reverse=True)
    return results[:top_n]


def fmt_amount(val):
    """格式化金額"""
    if val is None or val == 0:
        return '0'
    if abs(val) >= 1e9:
        return f"{'+' if val > 0 else ''}{val/1e9:.1f}B"
    elif abs(val) >= 1e6:
        return f"{'+' if val > 0 else ''}{val/1e6:.1f}M"
    elif abs(val) >= 1e3:
        return f"{'+' if val > 0 else ''}{val/1e3:.1f}K"
    else:
        return f"{'+' if val > 0 else ''}{val:.0f}"

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
#  配置
# ═══════════════════════════════════════════

INITIAL_CASH = 1_000_000
FUTU_HOST = '127.0.0.1'
FUTU_PORT = 11111
LOT_SIZE = 100  # 港股每手 100 股
COMMISSION_RATE = 0.001  # 佣金 0.1%
STAMP_DUTY = 0.0013  # 印花稅 0.13%
DEFAULT_DAYS = 365  # 回測 K 線天數（一年）


# ═══════════════════════════════════════════
#  數據獲取層
# ═══════════════════════════════════════════

class DataFetcher:
    """富途數據獲取器"""

    def __init__(self):
        self.quote_ctx = None

    def connect(self):
        try:
            self.quote_ctx = OpenQuoteContext(FUTU_HOST, FUTU_PORT)
            logger.info("富途 OpenD 連接成功")
            return True
        except Exception as e:
            logger.error(f"富途連接失敗: {e}")
            return False

    def close(self):
        if self.quote_ctx:
            self.quote_ctx.close()
            self.quote_ctx = None

    @staticmethod
    def convert_symbol(code):
        """轉換股票代碼為富途格式"""
        code = code.strip()
        # 已經是 HK.xxxxx 格式
        if code.upper().startswith('HK.') or code.upper().startswith('HK.'):
            num = code.split('.')[-1]
            if num.isdigit():
                return f"HK.{num.zfill(5)}"
            return code.upper()
        if code.upper().endswith('.HK'):
            num = code.replace('.HK', '').replace('.hk', '').zfill(5)
            return f"HK.{num}"
        if code.upper().endswith('.hk'):
            num = code.replace('.hk', '').zfill(5)
            return f"HK.{num}"
        if code.isdigit():
            return f"HK.{code.zfill(5)}"
        return code

    def get_kline(self, symbol, days=DEFAULT_DAYS):
        """獲取日 K 線 DataFrame"""
        futu_sym = self.convert_symbol(symbol)
        try:
            self.quote_ctx.subscribe([futu_sym], [SubType.K_DAY])
            ret, data = self.quote_ctx.get_cur_kline(futu_sym, num=days, ktype=KLType.K_DAY)
            if ret == RET_OK and not data.empty:
                df = pd.DataFrame()
                df['Open'] = data['open'].astype(float)
                df['High'] = data['high'].astype(float)
                df['Low'] = data['low'].astype(float)
                df['Close'] = data['close'].astype(float)
                df['Volume'] = data['volume'].astype(float)
                df.index = pd.to_datetime(data['time_key'])
                df = df.sort_index(ascending=True)
                return df
        except Exception as e:
            logger.error(f"K線獲取失敗 {symbol}: {e}")
        return pd.DataFrame()

    def get_quote(self, symbol):
        """獲取即時報價"""
        futu_sym = self.convert_symbol(symbol)
        try:
            ret, data = self.quote_ctx.get_market_snapshot([futu_sym])
            if ret == RET_OK and not data.empty:
                row = data.iloc[0]
                return {
                    'price': float(row.get('last_price', 0)),
                    'prev_close': float(row.get('prev_close_price', 0)),
                    'high': float(row.get('high_price', 0)),
                    'low': float(row.get('low_price', 0)),
                    'open': float(row.get('open_price', 0)),
                    'volume': int(row.get('volume', 0)),
                    'pe': row.get('pe_ratio', None),
                    'turnover_rate': float(row.get('turnover_rate', 0)),
                }
        except Exception as e:
            logger.error(f"報價獲取失敗 {symbol}: {e}")
        return None

    def get_capital_flow(self, symbol):
        """獲取個股真實資金流向 (富途 get_capital_flow API)"""
        futu_sym = self.convert_symbol(symbol)
        try:
            ret, data = self.quote_ctx.get_capital_flow(futu_sym, period_type=PeriodType.INTRADAY)
            if ret == RET_OK and not data.empty:
                latest = data.iloc[-1]
                in_flow = float(latest['in_flow'])
                details = {
                    'super': float(latest.get('super_in_flow', 0)),
                    'big': float(latest.get('big_in_flow', 0)),
                    'mid': float(latest.get('mid_in_flow', 0)),
                    'sml': float(latest.get('sml_in_flow', 0)),
                }
                signal = "正流入" if in_flow > 0 else "負流出" if in_flow < 0 else "中性"

                # 格式化
                if abs(in_flow) >= 1e9:
                    value = f"{'+' if in_flow > 0 else ''}{in_flow/1e9:.1f}B"
                elif abs(in_flow) >= 1e6:
                    value = f"{'+' if in_flow > 0 else ''}{in_flow/1e6:.1f}M"
                elif abs(in_flow) >= 1e3:
                    value = f"{'+' if in_flow > 0 else ''}{in_flow/1e3:.1f}K"
                else:
                    value = f"{'+' if in_flow > 0 else ''}{in_flow:.0f}"

                return {'value': value, 'signal': signal, 'raw': in_flow, 'details': details}
        except Exception as e:
            logger.warning(f'資金流向獲取失敗 {symbol}: {e}')
        return None

    def get_stock_name(self, symbol):
        """獲取股票名稱"""
        futu_sym = self.convert_symbol(symbol)
        try:
            market = futu_sym.split('.')[0]
            ret, data = self.quote_ctx.get_stock_basicinfo(market, futu_sym)
            if ret == RET_OK and not data.empty:
                return data.iloc[0]['name']
        except:
            pass
        return symbol


# ═══════════════════════════════════════════
#  技術指標計算器
# ═══════════════════════════════════════════

class IndicatorCalculator:
    """純技術指標計算，不依賴外部 API"""

    @staticmethod
    def ema(data, period):
        if len(data) < period:
            return [None] * len(data)
        k = 2 / (period + 1)
        result = [None] * (period - 1)
        first = sum(data[:period]) / period
        result.append(first)
        for i in range(period, len(data)):
            result.append(data[i] * k + result[-1] * (1 - k))
        return result

    @staticmethod
    def sma(data, period):
        result = [None] * (period - 1)
        for i in range(period - 1, len(data)):
            result.append(sum(data[i - period + 1:i + 1]) / period)
        return result

    @staticmethod
    def rsi(data, period=14):
        if len(data) < period + 1:
            return [None] * len(data)
        result = [None] * period
        gains, losses = [], []
        for i in range(period, len(data)):
            change = data[i] - data[i - 1]
            gains.append(max(change, 0))
            losses.append(max(-change, 0))
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for i in range(period):
            if avg_loss == 0:
                result.append(100)
            else:
                result.append(100 - 100 / (1 + avg_gain / avg_loss))
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            if avg_loss == 0:
                result.append(100)
            else:
                result.append(100 - 100 / (1 + avg_gain / avg_loss))
        return result

    @staticmethod
    def macd(data, fast=12, slow=26, signal=9):
        fast_ema = IndicatorCalculator.ema(data, fast)
        slow_ema = IndicatorCalculator.ema(data, slow)
        macd_line = []
        for f, s in zip(fast_ema, slow_ema):
            if f is not None and s is not None:
                macd_line.append(f - s)
            else:
                macd_line.append(None)
        valid = [(i, v) for i, v in enumerate(macd_line) if v is not None]
        signal_line = [None] * len(data)
        if len(valid) >= signal:
            vals = [v for _, v in valid]
            sig_ema = IndicatorCalculator.ema(vals, signal)
            for j, (orig_idx, _) in enumerate(valid):
                if j >= signal - 1 and j < len(sig_ema):
                    signal_line[orig_idx] = sig_ema[j]
        hist = []
        for i in range(len(data)):
            if macd_line[i] is not None and signal_line[i] is not None:
                hist.append(macd_line[i] - signal_line[i])
            else:
                hist.append(None)
        return macd_line, signal_line, hist

    @staticmethod
    def bollinger(data, period=20, std_mult=2.0):
        upper, middle, lower = [], [], []
        for i in range(len(data)):
            if i < period - 1:
                upper.append(None); middle.append(None); lower.append(None)
            else:
                window = data[i - period + 1:i + 1]
                sma = sum(window) / period
                std = math.sqrt(sum((x - sma) ** 2 for x in window) / period)
                upper.append(sma + std_mult * std)
                middle.append(sma)
                lower.append(sma - std_mult * std)
        return upper, middle, lower

    @staticmethod
    def atr(highs, lows, closes, period=14):
        """Average True Range"""
        trs = [highs[0] - lows[0]]
        for i in range(1, len(closes)):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            trs.append(tr)
        # EMA smoothing
        atr_vals = [None] * (period - 1)
        first_atr = sum(trs[:period]) / period
        atr_vals.append(first_atr)
        k = 2 / (period + 1)
        for i in range(period, len(trs)):
            atr_vals.append(trs[i] * k + atr_vals[-1] * (1 - k))
        return atr_vals


# ═══════════════════════════════════════════
#  策略信號投票
# ═══════════════════════════════════════════

def get_strategy_votes(df):
    """
    5 策略信號投票

    用最新信號為主，結合最近 5 個信號的趨勢做加權
    """
    engine = BacktestEngine()
    votes = {}
    bullish = 0
    bearish = 0
    hold = 0

    for name, StrategyClass in STRATEGIES.items():
        strat = StrategyClass()
        signals = strat.generate_signals(df)
        last_signal = signals[-1] if signals else 'HOLD'

        # 最近 5 個信號的趨勢
        recent = signals[-5:] if len(signals) >= 5 else signals
        buy_count = sum(1 for s in recent if s == 'BUY')
        sell_count = sum(1 for s in recent if s == 'SELL')
        total_recent = len(recent)

        # 最新信號為主，但需要趨勢支持（至少 2/5 同方向才算有效）
        if last_signal == 'BUY' and buy_count >= 2:
            effective = 'BUY'
            bullish += 1
        elif last_signal == 'SELL' and sell_count >= 2:
            effective = 'SELL'
            bearish += 1
        elif last_signal == 'BUY':
            # 最新是 BUY 但趨勢不支持 → 弱買入（算半票）
            effective = 'BUY'
            bullish += 0.5
            hold += 0.5
        elif last_signal == 'SELL':
            effective = 'SELL'
            bearish += 0.5
            hold += 0.5
        else:
            effective = 'HOLD'
            hold += 1

        votes[name] = {
            'signal': effective,
            'last_raw': last_signal,
        }

    # 共識判斷（降低門檻：bullish >= 2 就算看漲）
    if bullish >= 2 and bullish > bearish:
        consensus = 'BULLISH'
    elif bearish >= 2 and bearish > bullish:
        consensus = 'BEARISH'
    elif bullish >= 1.5 and bullish > bearish:
        consensus = 'BULLISH'
    elif bearish >= 1.5 and bearish > bullish:
        consensus = 'BEARISH'
    else:
        consensus = 'NEUTRAL'

    # strength 直接數各策略顯示嘅信號（唔用半票，對得住投票面板）
    disp_buy = sum(1 for v in votes.values() if v['signal'] == 'BUY')
    disp_sell = sum(1 for v in votes.values() if v['signal'] == 'SELL')
    disp_hold = sum(1 for v in votes.values() if v['signal'] == 'HOLD')
    strength = f'{disp_buy}B/{disp_sell}S/{disp_hold}H'

    return {
        'votes': votes,
        'bullish': bullish,
        'bearish': bearish,
        'hold': hold,
        'consensus': consensus,
        'strength': strength,
    }


# ═══════════════════════════════════════════
#  支撐/阻力位計算
# ═══════════════════════════════════════════

def calc_support_resistance(df, current_price):
    """
    多維度支撐/阻力位

    Returns:
        dict with supports, resistances, atr_stop_loss
    """
    closes = df['Close'].values
    highs = df['High'].values
    lows = df['Low'].values
    n = len(closes)
    if n < 20:
        return {'supports': [], 'resistances': [], 'atr_stop_loss': None, 'atr': None}

    result = {}

    # 1. 布林帶
    bb_upper, bb_mid, bb_lower = IndicatorCalculator.bollinger(closes, 20, 2.0)
    bb_u = bb_upper[-1] if bb_upper[-1] else current_price * 1.05
    bb_l = bb_lower[-1] if bb_lower[-1] else current_price * 0.95
    bb_m = bb_mid[-1] if bb_mid[-1] else current_price

    # 2. EMA20, EMA60
    ema20 = IndicatorCalculator.ema(closes, 20)
    ema60 = IndicatorCalculator.ema(closes, 60)
    e20 = ema20[-1] if ema20[-1] else current_price
    e60 = ema60[-1] if ema60[-1] else current_price

    # 3. SMA60
    sma60 = IndicatorCalculator.sma(closes, 60)
    s60 = sma60[-1] if sma60[-1] else current_price

    # 4. ATR
    atr_vals = IndicatorCalculator.atr(highs, lows, closes, 14)
    atr_val = atr_vals[-1] if atr_vals[-1] else current_price * 0.02

    # 5. 近期高低點（20日）
    recent_high = max(highs[-20:])
    recent_low = min(lows[-20:])

    # 6. RSI
    rsi_vals = IndicatorCalculator.rsi(closes, 14)
    rsi_val = rsi_vals[-1] if rsi_vals[-1] else 50

    # 7. MACD
    _, _, hist = IndicatorCalculator.macd(closes)
    macd_hist = hist[-1] if hist[-1] else 0

    # ── 支撐位（由近到遠排序）──
    supports = []
    if bb_l < current_price:
        supports.append({'level': round(bb_l, 2), 'source': '布林下軌', 'strength': 'strong'})
    if e20 < current_price:
        supports.append({'level': round(e20, 2), 'source': 'EMA20', 'strength': 'medium'})
    if e60 < current_price:
        supports.append({'level': round(e60, 2), 'source': 'EMA60', 'strength': 'strong'})
    if s60 < current_price:
        supports.append({'level': round(s60, 2), 'source': 'SMA60', 'strength': 'strong'})
    # 近期低點
    if recent_low < current_price:
        supports.append({'level': round(recent_low, 2), 'source': '20日最低', 'strength': 'weak'})

    # ── 阻力位（由近到遠排序）──
    resistances = []
    if bb_u > current_price:
        resistances.append({'level': round(bb_u, 2), 'source': '布林上軌', 'strength': 'strong'})
    if e20 > current_price:
        resistances.append({'level': round(e20, 2), 'source': 'EMA20', 'strength': 'medium'})
    if e60 > current_price:
        resistances.append({'level': round(e60, 2), 'source': 'EMA60', 'strength': 'strong'})
    if s60 > current_price:
        resistances.append({'level': round(s60, 2), 'source': 'SMA60', 'strength': 'strong'})
    if recent_high > current_price:
        resistances.append({'level': round(recent_high, 2), 'source': '20日最高', 'strength': 'weak'})

    # 去重（價差 < 0.5% 的合併）
    supports = _dedupe_levels(supports, current_price)
    resistances = _dedupe_levels(resistances, current_price)

    # 按距離排序
    supports.sort(key=lambda x: abs(x['level'] - current_price))
    resistances.sort(key=lambda x: abs(x['level'] - current_price))

    # 止損位：2×ATR below entry or recent support
    atr_stop = round(current_price - 2 * atr_val, 2)

    result = {
        'supports': supports[:5],
        'resistances': resistances[:5],
        'atr': round(atr_val, 2),
        'atr_stop_loss': atr_stop,
        'bb_upper': round(bb_u, 2),
        'bb_lower': round(bb_l, 2),
        'bb_mid': round(bb_m, 2),
        'ema20': round(e20, 2),
        'ema60': round(e60, 2),
        'sma60': round(s60, 2),
        'rsi': round(rsi_val, 1),
        'macd_hist': round(macd_hist, 4),
        'recent_high': round(recent_high, 2),
        'recent_low': round(recent_low, 2),
    }
    return result


def _dedupe_levels(levels, price, threshold=0.005):
    """去重：價差 < threshold 的合併"""
    if not levels:
        return []
    deduped = [levels[0]]
    for lv in levels[1:]:
        if all(abs(lv['level'] - d['level']) / price >= threshold for d in deduped):
            deduped.append(lv)
    return deduped


# ═══════════════════════════════════════════
#  回測勝率分析
# ═══════════════════════════════════════════

def analyze_strategy_winrate(df, symbol):
    """
    5 策略各跑一次回測，比較勝率和回報

    Returns:
        dict: {strategy_name: {win_rate, total_return, sharpe, best_strategy}}
    """
    results = {}
    best_name = None
    best_score = -999

    for name in STRATEGIES:
        engine = BacktestEngine()
        bt = engine.run(df.copy(), name)
        if 'error' in bt:
            continue

        metrics = bt.get('metrics', {})
        win_rate = metrics.get('win_rate', 0) or 0
        total_ret = metrics.get('total_return', 0) or 0
        sharpe = metrics.get('sharpe_ratio', 0) or 0
        max_dd = metrics.get('max_drawdown', 0) or 0

        # 綜合評分：勝率×0.4 + 回報×0.3 + 夏普×0.2 - 最大回撤×0.1
        score = win_rate * 0.4 + min(total_ret, 50) * 0.3 + min(sharpe, 3) * 5 * 0.2 - max(max_dd, -50) * 0.1

        results[name] = {
            'win_rate': round(win_rate, 1),
            'total_return': round(total_ret, 2),
            'sharpe': round(sharpe, 2),
            'max_drawdown': round(max_dd, 2),
            'trades': len(bt.get('trades', [])),
            'score': round(score, 2),
        }

        if score > best_score:
            best_score = score
            best_name = name

    results['best_strategy'] = best_name
    return results


# ═══════════════════════════════════════════
#  持倉讀取
# ═══════════════════════════════════════════

def load_portfolio(price_map=None):
    """
    讀取 Paper Trading 持倉（通過 PaperAccount，與 UI 完全一致）
    
    Args:
        price_map: {code: current_price} 即時價格映射，None 則用成本價
    
    Returns:
        dict: {
            'cash', 'initial_cash', 'total_assets', 'market_value',
            'realized_pnl', 'unrealized_pnl', 'total_pnl', 'total_return_pct',
            'holdings': [{code, name, quantity, avg_cost, current_price, market_value, ...}]
        }
    """
    try:
        account = PaperAccount(data_dir=str(BACKEND_DIR / 'paper_trading_data'))
        portfolio = account.get_portfolio(price_map)
        portfolio['initial_cash'] = account.INITIAL_CASH
        return portfolio
    except Exception as e:
        logger.error(f"讀取 PaperAccount 失敗: {e}", exc_info=True)
        return None


# ═══════════════════════════════════════════
#  報告生成
# ═══════════════════════════════════════════

def generate_stock_analysis(fetcher, code, quantity, avg_cost):
    """
    分析單隻股票

    Returns:
        dict: 完整分析結果
    """
    # 1. 獲取數據
    df = fetcher.get_kline(code, DEFAULT_DAYS)
    quote = fetcher.get_quote(code)
    name = fetcher.get_stock_name(code)
    capital_flow = fetcher.get_capital_flow(code)

    if df.empty:
        return {'code': code, 'name': name, 'error': 'K線數據不足'}

    current_price = quote['price'] if quote else df['Close'].iloc[-1]

    # 2. 技術指標
    indicators = calc_support_resistance(df, current_price)

    # 3. 策略投票
    votes = get_strategy_votes(df)

    # 4. 回測勝率
    winrate = analyze_strategy_winrate(df, code)

    # 5. 生成交易建議
    advice = generate_advice(
        current_price, avg_cost, quantity,
        indicators, votes, winrate
    )

    return {
        'code': code,
        'name': name,
        'quantity': quantity,
        'avg_cost': avg_cost,
        'current_price': current_price,
        'pnl': round((current_price - avg_cost) * quantity, 2),
        'pnl_pct': round((current_price - avg_cost) / avg_cost * 100, 2) if avg_cost > 0 else 0,
        'indicators': indicators,
        'votes': votes,
        'winrate': winrate,
        'capital_flow': capital_flow,
        'advice': advice,
        'quote': quote,
    }


def generate_advice(price, avg_cost, quantity, indicators, votes, winrate):
    """生成交易建議"""
    consensus = votes['consensus']
    rsi = indicators.get('rsi', 50)
    macd_hist = indicators.get('macd_hist', 0)
    best_strat = winrate.get('best_strategy', 'N/A')
    best_strat_data = winrate.get(best_strat, {})
    atr = indicators.get('atr', price * 0.02)

    supports = indicators.get('supports', [])
    resistances = indicators.get('resistances', [])
    atr_stop = indicators.get('atr_stop_loss', price * 0.95)

    # 買入區：第一個支撐位附近
    buy_zone_low = supports[0]['level'] if supports else round(price * 0.97, 2)
    buy_zone_high = round((buy_zone_low + price) / 2, 2)

    # 賣出區：第一個阻力位附近
    sell_zone_low = round(price + atr * 0.5, 2)
    sell_zone_high = resistances[0]['level'] if resistances else round(price * 1.05, 2)

    # 止損位：ATR 止損 或 成本價以下 3%
    cost_stop = round(avg_cost * 0.97, 2) if avg_cost > 0 else atr_stop
    stop_loss = max(atr_stop, cost_stop) if consensus != 'BEARISH' else atr_stop

    # 動作建議
    actions = []

    if consensus == 'BULLISH':
        if rsi < 40:
            actions.append(f"RSI={rsi:.0f} 偏低，可考慮在 {buy_zone_low}-{buy_zone_high} 加倉")
        elif rsi > 65:
            actions.append(f"RSI={rsi:.0f} 偏高，暫不加倉，持有觀望")
        else:
            actions.append(f"趨勢向好，可在回調至 {buy_zone_low} 附近加倉")

        if macd_hist > 0:
            actions.append("MACD 柱狀圖正值，動能充足")
        else:
            actions.append("MACD 柱狀圖翻負，留意動能衰竭")

        if resistances:
            actions.append(f"上方阻力 {resistances[0]['level']}，突破可看更高")

    elif consensus == 'BEARISH':
        if rsi > 60:
            actions.append(f"RSI={rsi:.0f} + 策略看空，建議減倉")
        else:
            actions.append(f"策略看空但 RSI={rsi:.0f} 未超買，觀望為主")

        if macd_hist < 0:
            actions.append("MACD 柱狀圖負值擴大，下跌動能增強")

    else:  # NEUTRAL
        actions.append("多空分歧，暫不加減倉")
        if supports:
            actions.append(f"支撐位 {supports[0]['level']}，跌破需止損")
        if resistances:
            actions.append(f"阻力位 {resistances[0]['level']}，突破可追")

    # 最佳策略建議
    if best_strat_data:
        wr = best_strat_data.get('win_rate', 0)
        ret = best_strat_data.get('total_return', 0)
        actions.append(f"歷史最優策略: {best_strat} (勝率{wr}%, 回報{ret}%)")

    # 距離成本
    if avg_cost > 0:
        dist_from_cost = (price - avg_cost) / avg_cost * 100
        if dist_from_cost < -5:
            actions.append(f"⚠️ 當前價格距成本 {dist_from_cost:+.1f}%，已跌破安全邊際")

    return {
        'consensus': consensus,
        'strength': votes['strength'],
        'buy_zone': {'low': buy_zone_low, 'high': buy_zone_high},
        'sell_zone': {'low': sell_zone_low, 'high': sell_zone_high},
        'stop_loss': stop_loss,
        'best_strategy': best_strat,
        'actions': actions,
    }


def generate_markdown_report(portfolio, analyses, report_time):
    """生成 Markdown 報告"""
    lines = []
    t = report_time

    lines.append(f"# 📊 StockAI 每日交易建議報告")
    lines.append(f"")
    lines.append(f"**時間**: {t.strftime('%Y-%m-%d %H:%M')} | **港股開盤前分析**")
    lines.append(f"")

    # 帳戶概覽
    cash = portfolio['cash']
    total_mv = portfolio['market_value']
    total_assets = portfolio['total_assets']
    realized_pnl = portfolio.get('realized_pnl', 0)
    unrealized_pnl = portfolio.get('unrealized_pnl', 0)
    total_pnl = portfolio.get('total_pnl', 0)
    total_return_pct = portfolio.get('total_return_pct', 0)
    initial_cash = portfolio.get('initial_cash', INITIAL_CASH)

    lines.append("---")
    lines.append("")
    lines.append("## 💰 帳戶概覽")
    lines.append("")
    lines.append(f"| 項目 | 金額 |")
    lines.append(f"|------|------|")
    lines.append(f"| 初始資金 | HKD {initial_cash:,.0f} |")
    lines.append(f"| 現金 | HKD {cash:,.0f} |")
    lines.append(f"| 持倉市值 | HKD {total_mv:,.0f} |")
    lines.append(f"| 總資產 | HKD {total_assets:,.0f} |")
    lines.append(f"| 已實現盈虧 | HKD {realized_pnl:+,.0f} |")
    lines.append(f"| 未實現盈虧 | HKD {unrealized_pnl:+,.0f} |")
    lines.append(f"| **總盈虧** | **HKD {total_pnl:+,.0f} ({total_return_pct:+.2f}%)** |")
    lines.append(f"| 持倉數量 | {len(analyses)} 只 |")
    lines.append("")

    # 各股分析
    for a in analyses:
        if 'error' in a:
            lines.append(f"## ❌ {a['name']} ({a['code']})")
            lines.append(f"")
            lines.append(f"**錯誤**: {a['error']}")
            lines.append("")
            continue

        code = a['code']
        name = a['name']
        price = a['current_price']
        pnl = a['pnl']
        pnl_pct = a['pnl_pct']
        qty = a['quantity']
        avg = a['avg_cost']
        ind = a['indicators']
        votes = a['votes']
        wr = a['winrate']
        adv = a['advice']

        # 共識 emoji
        emoji_map = {'BULLISH': '🟢', 'BEARISH': '🔴', 'NEUTRAL': '🟡'}
        emoji = emoji_map.get(adv['consensus'], '⚪')
        label_map = {'BULLISH': '看漲', 'BEARISH': '看跌', 'NEUTRAL': '中性'}
        label = label_map.get(adv['consensus'], '未知')

        lines.append("---")
        lines.append("")
        lines.append(f"## {emoji} {name} ({code})")
        lines.append("")
        lines.append(f"**持倉**: {qty:,} 股 @ HKD {avg:.2f} | **現價**: HKD {price:.2f} | **盈虧**: HKD {pnl:,.0f} ({pnl_pct:+.2f}%)")
        lines.append("")

        # 技術指標
        lines.append("### 📈 技術指標")
        lines.append("")
        lines.append("| 指標 | 數值 | 解讀 |")
        lines.append("|------|------|------|")

        # RSI
        rsi = ind.get('rsi', 50)
        rsi_status = "超賣" if rsi < 30 else "超買" if rsi > 70 else "中性"
        lines.append(f"| RSI(14) | {rsi:.1f} | {rsi_status} |")

        # MACD
        mh = ind.get('macd_hist', 0)
        mh_status = "多頭" if mh > 0 else "空頭"
        lines.append(f"| MACD 柱狀圖 | {mh:.4f} | {mh_status} |")

        # 布林帶
        lines.append(f"| 布林上軌 | {ind.get('bb_upper', 'N/A')} | 阻力位 |")
        lines.append(f"| 布林中軌 | {ind.get('bb_mid', 'N/A')} | 中軸 |")
        lines.append(f"| 布林下軌 | {ind.get('bb_lower', 'N/A')} | 支撐位 |")

        # EMA
        e20 = ind.get('ema20', price)
        e60 = ind.get('ema60', price)
        e20_diff = (price - e20) / e20 * 100 if e20 else 0
        e60_diff = (price - e60) / e60 * 100 if e60 else 0
        lines.append(f"| EMA20 | {e20:.2f} | {'價格在上方 ✅' if price > e20 else '價格在下方 ⚠️'} ({e20_diff:+.1f}%) |")
        lines.append(f"| EMA60 | {e60:.2f} | {'價格在上方 ✅' if price > e60 else '價格在下方 ⚠️'} ({e60_diff:+.1f}%) |")

        # ATR
        lines.append(f"| ATR(14) | {ind.get('atr', 0):.2f} | 日均波幅 |")
        lines.append("")

        # 策略投票
        lines.append("### 🗳️ 策略信號投票")
        lines.append("")
        lines.append(f"**共識**: {emoji} **{label}** ({adv['strength']})")
        lines.append("")
        lines.append("| 策略 | 信號 |")
        lines.append("|------|------|")
        sig_emoji = {'BUY': '🟢 買入', 'SELL': '🔴 賣出', 'HOLD': '🟡 持有'}
        for sname, sdata in votes['votes'].items():
            lines.append(f"| {sname.replace('_', ' ').title()} | {sig_emoji.get(sdata['signal'], sdata['signal'])} |")
        lines.append("")

        # 回測勝率
        lines.append("### 🏆 歷史回測勝率 (近一年)")
        lines.append("")
        lines.append("| 策略 | 勝率 | 回報 | 夏普 | 最大回撤 | 交易次數 |")
        lines.append("|------|------|------|------|----------|----------|")
        for sname, sdata in wr.items():
            if sname == 'best_strategy':
                continue
            best_mark = ' ⭐' if sname == wr.get('best_strategy') else ''
            lines.append(
                f"| {sname.replace('_', ' ').title()}{best_mark} | "
                f"{sdata['win_rate']}% | {sdata['total_return']}% | "
                f"{sdata['sharpe']} | {sdata['max_drawdown']}% | "
                f"{sdata['trades']} |"
            )
        lines.append("")

        # 支撐/阻力位
        lines.append("### 📊 支撐位 / 阻力位")
        lines.append("")
        sups = ind.get('supports', [])
        ress = ind.get('resistances', [])
        if sups:
            lines.append("**支撐位 (由近到遠):**")
            for s in sups:
                dist = (price - s['level']) / price * 100
                lines.append(f"  - HKD {s['level']:.2f} ({s['source']}) — 距現價 {dist:.1f}%")
        else:
            lines.append("**支撐位**: 無明顯支撐")
        lines.append("")
        if ress:
            lines.append("**阻力位 (由近到遠):**")
            for r in ress:
                dist = (r['level'] - price) / price * 100
                lines.append(f"  - HKD {r['level']:.2f} ({r['source']}) — 距現價 +{dist:.1f}%")
        else:
            lines.append("**阻力位**: 無明顯阻力")
        lines.append("")

        # 資金流向
        cf = a.get('capital_flow')
        if cf:
            lines.append("### 💰 資金流向")
            lines.append("")
            cf_signal_icon = '🟢' if cf['signal'] == '正流入' else '🔴' if cf['signal'] == '負流出' else '⚪'
            lines.append(f"**淨流入**: {cf_signal_icon} {cf['value']} ({cf['signal']})")
            details = cf.get('details', {})
            if details:
                lines.append(f"| 分類 | 淨流入 |")
                lines.append(f"|:--|--:|")
                for label, key in [('特大單', 'super'), ('大單', 'big'), ('中單', 'mid'), ('小單', 'sml')]:
                    val = details.get(key, 0)
                    if abs(val) >= 1e6:
                        v = f"{'+' if val > 0 else ''}{val/1e6:.1f}M"
                    elif abs(val) >= 1e3:
                        v = f"{'+' if val > 0 else ''}{val/1e3:.1f}K"
                    else:
                        v = f"{'+' if val > 0 else ''}{val:.0f}"
                    lines.append(f"| {label} | {v} |")
            lines.append("")

        # 交易建議
        lines.append("### 💡 今日交易建議")
        lines.append("")
        bz = adv['buy_zone']
        sz = adv['sell_zone']
        sl = adv['stop_loss']
        lines.append(f"- **加倉區**: HKD {bz['low']:.2f} - {bz['high']:.2f}")
        lines.append(f"- **減倉區**: HKD {sz['low']:.2f} - {sz['high']:.2f}")
        lines.append(f"- **止損位**: HKD {sl:.2f}")
        for action in adv['actions']:
            lines.append(f"- {action}")
        lines.append("")

    # 免責聲明
    lines.append("---")
    lines.append("")
    lines.append("*⚠️ 免責聲明: 本報告僅基於技術指標和歷史回測，不構成投資建議。市場有風險，投資需謹慎。*")
    lines.append("")

    return '\n'.join(lines)


# ═══════════════════════════════════════════
#  HTML 報告模板
# ═══════════════════════════════════════════

def generate_html_report(portfolio, analyses, report_time):
    """生成自包含 HTML 報告（深色主題，響應式）"""
    t = report_time

    # 帳戶數據
    cash = portfolio['cash']
    total_mv = portfolio['market_value']
    total_assets = portfolio['total_assets']
    realized_pnl = portfolio.get('realized_pnl', 0)
    unrealized_pnl = portfolio.get('unrealized_pnl', 0)
    total_pnl = portfolio.get('total_pnl', 0)
    total_return_pct = portfolio.get('total_return_pct', 0)
    initial_cash = portfolio.get('initial_cash', INITIAL_CASH)

    # 各股卡片 HTML
    stock_cards = ''
    for a in analyses:
        if 'error' in a:
            stock_cards += f'''
            <div class="stock-card card-error">
                <div class="card-header"><h3>❌ {a['code']}</h3></div>
                <div class="card-body"><p>{a['error']}</p></div>
            </div>'''
            continue

        ind = a['indicators']
        votes = a['votes']
        wr = a['winrate']
        adv = a['advice']

        # 共識配色
        cs_map = {
            'BULLISH': ('#10b981', '看漲', '🟢'),
            'BEARISH': ('#ef4444', '看跌', '🔴'),
            'NEUTRAL': ('#f59e0b', '中性', '🟡'),
        }
        cs_color, cs_label, cs_emoji = cs_map.get(adv['consensus'], ('#94a3b8', '未知', '⚪'))

        # 盈虧配色
        pnl_color = '#10b981' if a['pnl'] >= 0 else '#ef4444'

        # RSI 狀態
        rsi = ind.get('rsi', 50)
        if rsi < 30:
            rsi_badge = '<span class="badge badge-green">超賣</span>'
        elif rsi > 70:
            rsi_badge = '<span class="badge badge-red">超買</span>'
        else:
            rsi_badge = '<span class="badge badge-yellow">中性</span>'

        # MACD
        mh = ind.get('macd_hist', 0)
        macd_badge = '<span class="badge badge-green">多頭</span>' if mh > 0 else '<span class="badge badge-red">空頭</span>'

        # 支撐/阻力
        sups_html = ''
        for s in ind.get('supports', [])[:3]:
            dist = (a['current_price'] - s['level']) / a['current_price'] * 100
            sups_html += f'<div class="level-item level-support"><span class="level-label">{s["source"]}</span><span class="level-val">{s["level"]:.2f}</span><span class="level-dist">{dist:.1f}%</span></div>'

        ress_html = ''
        for r in ind.get('resistances', [])[:3]:
            dist = (r['level'] - a['current_price']) / a['current_price'] * 100
            ress_html += f'<div class="level-item level-resist"><span class="level-label">{r["source"]}</span><span class="level-val">{r["level"]:.2f}</span><span class="level-dist">+{dist:.1f}%</span></div>'

        # 策略投票
        votes_html = ''
        sig_icon = {'BUY': '🟢', 'SELL': '🔴', 'HOLD': '🟡'}
        for sname, sdata in votes['votes'].items():
            nice = sname.replace('_', ' ').title()
            votes_html += f'<div class="vote-item"><span class="vote-name">{nice}</span><span class="vote-sig">{sig_icon.get(sdata["signal"], "⚪")} {sdata["signal"]}</span></div>'

        # 資金流向
        cf = a.get('capital_flow')
        if cf:
            cf_color = '#10b981' if cf['signal'] == '正流入' else '#ef4444' if cf['signal'] == '負流出' else '#94a3b8'
            cf_icon = '🟢' if cf['signal'] == '正流入' else '🔴' if cf['signal'] == '負流出' else '⚪'
            cf_html = f'<span class="cf-value" style="color:{cf_color}">{cf_icon} {cf["value"]}</span>'
            details = cf.get('details', {})
            if details:
                cf_detail_items = []
                for label, key in [('特大單', 'super'), ('大單', 'big'), ('中單', 'mid'), ('小單', 'sml')]:
                    val = details.get(key, 0)
                    if abs(val) >= 1e6:
                        v = f"{'+' if val > 0 else ''}{val/1e6:.1f}M"
                    elif abs(val) >= 1e3:
                        v = f"{'+' if val > 0 else ''}{val/1e3:.1f}K"
                    else:
                        v = f"{'+' if val > 0 else ''}{val:.0f}"
                    c = '#10b981' if val > 0 else '#ef4444' if val < 0 else '#94a3b8'
                    cf_detail_items.append(f'<div class="cf-detail-item"><span class="cf-detail-label">{label}</span><span class="cf-detail-val" style="color:{c}">{v}</span></div>')
                cf_detail_html = ''.join(cf_detail_items)
            else:
                cf_detail_html = '<span style="color:#64748b;font-size:12px;">無詳細分類</span>'
        else:
            cf_html = '<span style="color:#64748b;">N/A</span>'
            cf_detail_html = ''

        # 回測勝率表
        wr_rows = ''
        best = wr.get('best_strategy', '')
        for sname, sdata in wr.items():
            if sname == 'best_strategy':
                continue
            star = ' ⭐' if sname == best else ''
            nice = sname.replace('_', ' ').title()
            wr_color = '#10b981' if sdata['total_return'] > 0 else '#ef4444'
            wr_rows += f'''<tr class="{"best-strat" if sname == best else ""}">
                <td>{nice}{star}</td>
                <td>{sdata['win_rate']}%</td>
                <td style="color:{wr_color}">{sdata['total_return']}%</td>
                <td>{sdata['sharpe']}</td>
                <td>{sdata['max_drawdown']}%</td>
                <td>{sdata['trades']}</td>
            </tr>'''

        # 建議列表
        actions_html = ''
        for act in adv['actions']:
            actions_html += f'<li>{act}</li>'

        stock_cards += f'''
        <div class="stock-card">
            <div class="card-header">
                <div class="header-left">
                    <h3>{a['name']} <small>({a['code']})</small></h3>
                </div>
                <div class="header-right">
                    <div class="consensus-badge" style="background:{cs_color}20; border-color:{cs_color}; color:{cs_color}">
                        {cs_emoji} {cs_label}
                    </div>
                    <div class="consensus-strength">{adv['strength']}</div>
                </div>
            </div>
            <div class="card-top">
                <div class="price-block">
                    <div class="price-now">HKD {a['current_price']:.2f}</div>
                    <div class="pnl" style="color:{pnl_color}">{a['pnl']:+,.0f} ({a['pnl_pct']:+.2f}%)</div>
                </div>
                <div class="holding-info">
                    <div class="info-row"><span class="info-label">持倉</span><span class="info-val">{a['quantity']:,} 股</span></div>
                    <div class="info-row"><span class="info-label">成本</span><span class="info-val">{a['avg_cost']:.2f}</span></div>
                    <div class="info-row"><span class="info-label">市值</span><span class="info-val">{a['current_price']*a['quantity']:,.0f}</span></div>
                </div>
            </div>
            <div class="card-grid">
                <div class="grid-section">
                    <h4>📈 技術指標</h4>
                    <div class="ind-groups">
                        <!-- 動量 -->
                        <div class="ind-group">
                            <div class="ind-group-title">動量</div>
                            <div class="ind-group-items">
                                <div class="ind-item"><span class="ind-label">RSI(14)</span><span class="ind-val">{rsi:.1f}</span>{rsi_badge}</div>
                                <div class="ind-item"><span class="ind-label">MACD</span><span class="ind-val">{mh:.4f}</span>{macd_badge}</div>
                            </div>
                        </div>
                        <!-- 均線 -->
                        <div class="ind-group">
                            <div class="ind-group-title">均線</div>
                            <div class="ind-group-items">
                                <div class="ind-item"><span class="ind-label">EMA20</span><span class="ind-val">{ind.get("ema20",0):.2f}</span><span class="badge {'badge-green' if a['current_price']>ind.get('ema20',0) else 'badge-red'}">{'上✅' if a['current_price']>ind.get('ema20',0) else '下⚠️'}</span></div>
                                <div class="ind-item"><span class="ind-label">EMA60</span><span class="ind-val">{ind.get("ema60",0):.2f}</span><span class="badge {'badge-green' if a['current_price']>ind.get('ema60',0) else 'badge-red'}">{'上✅' if a['current_price']>ind.get('ema60',0) else '下⚠️'}</span></div>
                            </div>
                        </div>
                        <!-- 布林帶 -->
                        <div class="ind-group">
                            <div class="ind-group-title">布林帶</div>
                            <div class="ind-group-items">
                                <div class="ind-item"><span class="ind-label">上軌</span><span class="ind-val">{ind.get("bb_upper",0):.2f}</span></div>
                                <div class="ind-item"><span class="ind-label">中軌</span><span class="ind-val">{ind.get("bb_mid",0):.2f}</span></div>
                                <div class="ind-item"><span class="ind-label">下軌</span><span class="ind-val">{ind.get("bb_lower",0):.2f}</span></div>
                            </div>
                        </div>
                        <!-- 波動/區間 -->
                        <div class="ind-group">
                            <div class="ind-group-title">區間</div>
                            <div class="ind-group-items">
                                <div class="ind-item"><span class="ind-label">ATR(14)</span><span class="ind-val">{ind.get("atr",0):.2f}</span></div>
                                <div class="ind-item"><span class="ind-label">20日高</span><span class="ind-val">{ind.get("recent_high",0):.2f}</span></div>
                                <div class="ind-item"><span class="ind-label">20日低</span><span class="ind-val">{ind.get("recent_low",0):.2f}</span></div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="grid-section">
                    <h4>📊 支撐 / 阻力位</h4>
                    <div class="levels-container">
                        <div class="levels-col">
                            <div class="levels-title resist-title">🔺 阻力位</div>
                            {ress_html or '<div class="level-empty">無明顯阻力</div>'}
                        </div>
                        <div class="levels-col">
                            <div class="levels-title support-title">🔻 支撐位</div>
                            {sups_html or '<div class="level-empty">無明顯支撐</div>'}
                        </div>
                    </div>
                    <div class="wr-section">
                        <h4>🏆 回測勝率 (近一年)</h4>
                        <table class="wr-table">
                            <thead><tr><th>策略</th><th>勝率</th><th>回報</th><th>夏普</th><th>回撤</th><th>次數</th></tr></thead>
                            <tbody>{wr_rows}</tbody>
                        </table>
                    </div>
                    <div class="votes-section">
                        <h4>🗳️ 策略投票 <small>({votes['consensus']})</small></h4>
                        <div class="votes-row">{votes_html}</div>
                    </div>
                </div>
            </div>
            <div class="capital-flow-section">
                <h4>💰 資金流向</h4>
                <div class="cf-main">{cf_html}</div>
                <div class="cf-details">{cf_detail_html}</div>
            </div>
            <div class="card-advice">
                <h4>💡 今日交易建議</h4>
                <div class="advice-zones">
                    <div class="zone buy-zone">
                        <span class="zone-label">🟢 加倉區</span>
                        <span class="zone-range">{adv['buy_zone']['low']:.2f} — {adv['buy_zone']['high']:.2f}</span>
                    </div>
                    <div class="zone sell-zone">
                        <span class="zone-label">🔴 減倉區</span>
                        <span class="zone-range">{adv['sell_zone']['low']:.2f} — {adv['sell_zone']['high']:.2f}</span>
                    </div>
                    <div class="zone stop-zone">
                        <span class="zone-label">⏹ 止損位</span>
                        <span class="zone-range">{adv['stop_loss']:.2f}</span>
                    </div>
                </div>
                <ul class="advice-list">{actions_html}</ul>
            </div>
        </div>'''

    pnl_color_total = '#10b981' if total_pnl >= 0 else '#ef4444'
    realized_color = '#10b981' if realized_pnl >= 0 else '#ef4444'
    unrealized_color = '#10b981' if unrealized_pnl >= 0 else '#ef4444'

    html = f'''<!DOCTYPE html>
<html lang="zh-HK">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>StockAI 每日交易建議 | {t.strftime('%Y-%m-%d')}</title>
<style>
:root {{
    --bg: #0b1120;
    --bg-card: #111827;
    --bg-card-hover: #1a2332;
    --border: #1e293b;
    --accent: #3b82f6;
    --green: #10b981;
    --red: #ef4444;
    --yellow: #f59e0b;
    --text: #e2e8f0;
    --text-muted: #94a3b8;
    --radius: 12px;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; line-height: 1.6; }}

.container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}

/* 頂部 */
.report-header {{
    text-align: center; padding: 30px 0 20px; border-bottom: 1px solid var(--border); margin-bottom: 30px;
}}
.report-header h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
.report-header .subtitle {{ color: var(--text-muted); font-size: 14px; }}

/* 概覽卡片 */
.overview {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 30px; }}
.ov-card {{
    background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 20px; text-align: center; transition: border-color 0.2s;
}}
.ov-card:hover {{ border-color: var(--accent); }}
.ov-label {{ font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }}
.ov-val {{ font-size: 24px; font-weight: 700; }}
.ov-val.green {{ color: var(--green); }}
.ov-val.red {{ color: var(--red); }}

/* 股票卡片 */
.stock-card {{
    background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius);
    margin-bottom: 24px; overflow: hidden; transition: border-color 0.2s;
}}
.stock-card:hover {{ border-color: var(--accent); }}
.card-error {{ background: #1a0a0a; border-color: #7f1d1d; }}

.card-header {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 16px 24px; border-bottom: 1px solid var(--border);
}}
.card-header h3 {{ font-size: 20px; font-weight: 600; }}
.card-header small {{ color: var(--text-muted); font-size: 14px; }}
.header-right {{ display: flex; align-items: center; gap: 10px; }}
.consensus-badge {{
    padding: 4px 14px; border-radius: 20px; font-size: 14px; font-weight: 600;
    border: 1.5px solid; display: inline-block;
}}
.consensus-strength {{ font-size: 12px; color: var(--text-muted); }}

.card-top {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 16px 24px; border-bottom: 1px solid var(--border);
}}
.price-now {{ font-size: 28px; font-weight: 700; }}
.pnl {{ font-size: 16px; font-weight: 600; margin-top: 4px; }}
.holding-info {{ text-align: right; }}
.info-row {{ margin-bottom: 2px; }}
.info-label {{ color: var(--text-muted); font-size: 13px; margin-right: 12px; }}
.info-val {{ font-size: 14px; font-weight: 500; }}

.card-grid {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 0;
}}
.grid-section {{
    padding: 20px 24px; border-right: 1px solid var(--border);
}}
.grid-section:last-child {{ border-right: none; }}
.grid-section h4 {{ font-size: 15px; color: var(--text-muted); margin-bottom: 14px; font-weight: 600; }}
.grid-section small {{ font-weight: 400; color: var(--text-muted); }}

/* 指標 - 分組細格 */
.ind-groups {{ display: flex; flex-direction: column; gap: 10px; }}
.ind-group {{ }}
.ind-group-title {{ font-size: 11px; color: var(--accent); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; font-weight: 600; }}
.ind-group-items {{ display: flex; flex-direction: column; gap: 4px; }}
.ind-item {{
    display: flex; align-items: center; gap: 8px; padding: 5px 10px;
    background: rgba(255,255,255,0.03); border-radius: 6px; font-size: 13px;
}}
.ind-item:hover {{ background: rgba(255,255,255,0.06); }}
.ind-label {{ color: var(--text-muted); min-width: 55px; }}
.ind-val {{ font-weight: 700; font-variant-numeric: tabular-nums; }}

.badge {{
    display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11px; font-weight: 600;
}}
.badge-green {{ background: rgba(16,185,129,0.15); color: #10b981; }}
.badge-red {{ background: rgba(239,68,68,0.15); color: #ef4444; }}
.badge-yellow {{ background: rgba(245,158,11,0.15); color: #f59e0b; }}

/* 投票 - 橫排 inline */
.votes-row {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.vote-item {{
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: 8px 16px; background: rgba(255,255,255,0.03); border-radius: 8px;
    font-size: 13px; min-width: 90px; border: 1px solid var(--border);
}}
.vote-item:hover {{ background: rgba(255,255,255,0.06); border-color: var(--accent); }}
.vote-name {{ color: var(--text-muted); font-size: 11px; margin-bottom: 2px; }}
.vote-sig {{ font-weight: 700; font-size: 14px; }}

/* 支撐阻力 - 左右並排，各自上下細格 */
.levels-container {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
.levels-col {{ }}
.levels-title {{ font-size: 12px; font-weight: 600; margin-bottom: 6px; padding-bottom: 3px; border-bottom: 1px solid var(--border); }}
.support-title {{ color: var(--green); }}
.resist-title {{ color: var(--red); }}
.level-item {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 4px 8px; font-size: 12px;
    background: rgba(255,255,255,0.03); border-radius: 4px; margin-bottom: 2px;
}}
.level-item:hover {{ background: rgba(255,255,255,0.06); }}
.level-label {{ color: var(--text-muted); }}
.level-val {{ font-weight: 600; font-variant-numeric: tabular-nums; }}
.level-dist {{ color: var(--text-muted); font-size: 11px; }}
.level-empty {{ color: var(--text-muted); font-size: 12px; padding: 6px 0; }}

/* 回測勝率 - 嵌在支撐/阻力位下方 */
.wr-section {{ margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--border); }}
.wr-section h4 {{ font-size: 13px; color: var(--text-muted); margin-bottom: 8px; font-weight: 600; }}

/* 策略投票 - 嵌在回測勝率下方 */
.votes-section {{ margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--border); }}
.votes-section h4 {{ font-size: 13px; color: var(--text-muted); margin-bottom: 8px; font-weight: 600; }}

/* 資金流向 */
.capital-flow-section {{ margin-top: 12px; padding: 14px; background: rgba(255,255,255,0.02); border-radius: 8px; border: 1px solid var(--border); }}
.capital-flow-section h4 {{ font-size: 15px; color: var(--text-muted); margin-bottom: 10px; font-weight: 600; }}
.cf-main {{ font-size: 20px; font-weight: 700; font-variant-numeric: tabular-nums; }}
.cf-details {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 10px; }}
.cf-detail-item {{ display: flex; flex-direction: column; gap: 3px; padding: 8px 10px; background: rgba(255,255,255,0.03); border-radius: 6px; }}
.cf-detail-label {{ font-size: 12px; color: var(--text-muted); }}
.cf-detail-val {{ font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; }}
.full-width-section {{ grid-column: 1 / -1; }}

/* 勝率表 */
.wr-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
.wr-table th {{ color: var(--text-muted); font-weight: 600; text-align: left; padding: 4px 6px; border-bottom: 1px solid var(--border); }}
.wr-table td {{ padding: 4px 6px; border-bottom: 1px solid rgba(255,255,255,0.03); font-variant-numeric: tabular-nums; }}
.wr-table tr.best-strat {{ background: rgba(59,130,246,0.08); }}
.wr-table tr.best-strat td:first-child {{ color: var(--accent); font-weight: 600; }}

/* 建議 */
.card-advice {{
    padding: 20px 24px; border-top: 1px solid var(--border); background: rgba(255,255,255,0.01);
}}
.card-advice h4 {{ font-size: 15px; color: var(--text-muted); margin-bottom: 14px; font-weight: 600; }}
.advice-zones {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; margin-bottom: 14px; }}
.zone {{
    padding: 12px 16px; border-radius: 10px; text-align: center;
    border: 1px solid var(--border); background: var(--bg-card);
}}
.zone-label {{ display: block; font-size: 12px; color: var(--text-muted); margin-bottom: 4px; }}
.zone-range {{ display: block; font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; }}
.buy-zone .zone-range {{ color: var(--green); }}
.sell-zone .zone-range {{ color: var(--red); }}
.stop-zone .zone-range {{ color: var(--yellow); }}
.advice-list {{ padding-left: 20px; color: var(--text-muted); font-size: 13px; }}
.advice-list li {{ margin-bottom: 4px; }}

/* 底部 */
.footer {{ text-align: center; padding: 20px; color: var(--text-muted); font-size: 12px; border-top: 1px solid var(--border); margin-top: 20px; }}

/* 響應式 */
@media (max-width: 768px) {{
    .card-grid {{ grid-template-columns: 1fr; }}
    .grid-section {{ border-right: none; border-bottom: 1px solid var(--border); }}
    .advice-zones {{ grid-template-columns: 1fr; }}
    .overview {{ grid-template-columns: 1fr 1fr; }}
    .ind-row .ind-label {{ min-width: 100px; }}
}}
</style>
</head>
<body>
<div class="container">
    <div class="report-header">
        <h1>📊 StockAI 每日交易建議</h1>
        <div class="subtitle">{t.strftime('%Y-%m-%d %H:%M')} | 港股開盤前分析</div>
    </div>

    <div class="overview">
        <div class="ov-card">
            <div class="ov-label">現金</div>
            <div class="ov-val">HKD {cash:,.0f}</div>
        </div>
        <div class="ov-card">
            <div class="ov-label">持倉市值</div>
            <div class="ov-val">HKD {total_mv:,.0f}</div>
        </div>
        <div class="ov-card">
            <div class="ov-label">總資產</div>
            <div class="ov-val">HKD {total_assets:,.0f}</div>
        </div>
        <div class="ov-card">
            <div class="ov-label">總盈虧</div>
            <div class="ov-val {'green' if total_pnl >= 0 else 'red'}">HKD {total_pnl:+,.0f} ({total_return_pct:+.2f}%)</div>
        </div>
        <div class="ov-card">
            <div class="ov-label">已實現盈虧</div>
            <div class="ov-val" style="color:{realized_color}">HKD {realized_pnl:+,.0f}</div>
        </div>
        <div class="ov-card">
            <div class="ov-label">未實現盈虧</div>
            <div class="ov-val" style="color:{unrealized_color}">HKD {unrealized_pnl:+,.0f}</div>
        </div>
        <div class="ov-card">
            <div class="ov-label">持倉數量</div>
            <div class="ov-val">{len(analyses)}</div>
        </div>
    </div>

    {stock_cards}

    <div class="footer">
        ⚠️ 免責聲明: 本報告僅基於技術指標和歷史回測，不構成投資建議。市場有風險，投資需謹慎。<br>
        Powered by StockAI v1.7 | Generated at {t.strftime('%Y-%m-%d %H:%M:%S')}
    </div>
</div>
</body>
</html>'''
    return html


# ═══════════════════════════════════════════
#  單股資金流向分析報告 (--mode single)
# ═══════════════════════════════════════════

def generate_single_stock_report(fetcher, code):
    """
    生成單股完整分析報告（技術指標 + 資金流向 + 交易建議）
    無需持倉，任意股票可搜尋
    """
    # 1. 獲取數據
    df = fetcher.get_kline(code, DEFAULT_DAYS)
    quote = fetcher.get_quote(code)
    name = fetcher.get_stock_name(code)
    capital_flow = fetcher.get_capital_flow(code)

    if df.empty:
        return {'code': code, 'name': name, 'error': 'K線數據不足'}

    current_price = quote['price'] if quote else df['Close'].iloc[-1]
    prev_close = quote['prev_close'] if quote else df['Close'].iloc[-2] if len(df) >= 2 else current_price
    change = current_price - prev_close
    change_pct = change / prev_close * 100 if prev_close > 0 else 0
    turnover = quote.get('turnover_rate', 0) if quote else 0

    # 2. 技術指標
    indicators = calc_support_resistance(df, current_price)
    votes = get_strategy_votes(df)
    winrate = analyze_strategy_winrate(df, code)

    # 3. 交易建議 (用當前價作為「成本」，數量0=純觀察)
    advice = generate_advice(current_price, current_price, 0, indicators, votes, winrate)

    return {
        'code': code,
        'name': name,
        'current_price': current_price,
        'prev_close': prev_close,
        'change': change,
        'change_pct': change_pct,
        'turnover': turnover,
        'indicators': indicators,
        'votes': votes,
        'winrate': winrate,
        'capital_flow': capital_flow,
        'advice': advice,
        'quote': quote,
    }


def render_single_html(a, report_time):
    """渲染單股分析 HTML 報告"""
    t = report_time
    cf = a.get('capital_flow')
    ind = a.get('indicators', {})
    votes = a.get('votes', {})
    wr = a.get('winrate', {})
    adv = a.get('advice', {})
    quote = a.get('quote', {})

    # 顏色
    pnl_color = '#10b981' if a['change'] >= 0 else '#ef4444'
    pnl_sign = '+' if a['change'] >= 0 else ''

    # RSI / MACD
    rsi = ind.get('rsi', 50)
    mh = ind.get('macd_hist', 0)
    rsi_badge = '<span class="badge badge-green">超買</span>' if rsi > 70 else '<span class="badge badge-red">超賣</span>' if rsi < 30 else '<span class="badge badge-yellow">中性</span>'
    macd_badge = '<span class="badge badge-green">金叉</span>' if mh > 0 else '<span class="badge badge-red">死叉</span>'

    # Consensus
    cs = adv.get('consensus', 'NEUTRAL')
    cs_map = {'BULLISH': ('🟢', '看漲', '#10b981'), 'BEARISH': ('🔴', '看跌', '#ef4444'), 'NEUTRAL': ('⚪', '中性', '#f59e0b')}
    cs_emoji, cs_label, cs_color = cs_map.get(cs, ('⚪', '中性', '#f59e0b'))

    # 支撐/阻力
    sups = ind.get('supports', [])
    ress = ind.get('resistances', [])
    sups_html = ''
    for s in sups[:3]:
        dist = (a['current_price'] - s['level']) / a['current_price'] * 100
        sups_html += f'<div class="level-item"><span class="level-label">{s["source"]}</span><span class="level-val">{s["level"]:.2f}</span><span class="level-dist">{dist:.1f}%</span></div>'
    ress_html = ''
    for r in ress[:3]:
        dist = (r['level'] - a['current_price']) / a['current_price'] * 100
        ress_html += f'<div class="level-item"><span class="level-label">{r["source"]}</span><span class="level-val">{r["level"]:.2f}</span><span class="level-dist">+{dist:.1f}%</span></div>'

    # 投票 (votes 是嵌套結構: {'votes': {strat: {signal, last_raw}}, 'consensus', 'strength', ...})
    sig_icon = {'BULLISH': '🟢', 'BEARISH': '🔴', 'NEUTRAL': '⚪'}
    vote_map = {'BUY': '🟢 買入', 'SELL': '🔴 賣出', 'HOLD': '⚪ 觀望'}
    votes_html = ''
    strat_votes = votes.get('votes', votes) if isinstance(votes, dict) else {}
    for sname, sdata in strat_votes.items():
        if not isinstance(sdata, dict):
            continue
        nice = sname.replace('_', ' ').title()
        sig = sdata.get('signal', 'HOLD')
        votes_html += f'<div class="vote-item"><span class="vote-name">{nice}</span><span class="vote-sig">{vote_map.get(sig, "⚪ " + sig)}</span></div>'

    # 回測勝率表
    wr_rows = ''
    best = wr.get('best_strategy', '')
    for sname, sdata in wr.items():
        if sname == 'best_strategy':
            continue
        star = ' ⭐' if sname == best else ''
        nice = sname.replace('_', ' ').title()
        wr_color = '#10b981' if sdata['total_return'] > 0 else '#ef4444'
        wr_rows += f'''<tr class="{"best-strat" if sname == best else ""}">
            <td>{nice}{star}</td><td>{sdata['win_rate']}%</td>
            <td style="color:{wr_color}">{sdata['total_return']}%</td>
            <td>{sdata['sharpe']}</td><td>{sdata['max_drawdown']}%</td><td>{sdata['trades']}</td></tr>'''

    # 資金流向
    if cf:
        cf_color = '#10b981' if cf['signal'] == '正流入' else '#ef4444' if cf['signal'] == '負流出' else '#94a3b8'
        cf_icon = '🟢' if cf['signal'] == '正流入' else '🔴' if cf['signal'] == '負流出' else '⚪'
        cf_signal_cls = 'inflow' if cf['signal'] == '正流入' else 'outflow' if cf['signal'] == '負流出' else 'neutral'
        details = cf.get('details', {})
        d_sup = details.get('super', 0)
        d_big = details.get('big', 0)
        d_mid = details.get('mid', 0)
        d_sml = details.get('sml', 0)
        institution_flow = d_sup + d_big
        retail_flow = d_mid + d_sml
        # 機構佔比
        total_abs = abs(d_sup) + abs(d_big) + abs(d_mid) + abs(d_sml)
        inst_pct = (abs(d_sup) + abs(d_big)) / total_abs * 100 if total_abs > 0 else 0
        # 機構 vs 散户 判定
        if institution_flow > 0 and retail_flow < 0:
            iv_class, iv_text = 'bullish', '📈 機構吸貨、散户拋售 — 歷史此現象後3日上漲概率偏高'
        elif institution_flow < 0 and retail_flow > 0:
            iv_class, iv_text = 'bearish', '📉 機構出貨、散户接盤 — 需警惕短期下行風險'
        else:
            iv_class, iv_text = 'neutral', '⚖️ 資金方向不明確，觀望為主'
        # 各分類 bar
        max_abs = max(abs(d_sup), abs(d_big), abs(d_mid), abs(d_sml), 1)
        cf_cats_html = f'''
        <div class="cf-cat-item"><span class="cf-cat-label">🏢 特大單 (機構)</span>
            <span class="cf-cat-val" style="color:{'#10b981' if d_sup>0 else '#ef4444' if d_sup<0 else '#94a3b8'}">{fmt_amount(d_sup)}</span>
            <div class="cf-cat-bar-wrap"><div class="cf-cat-bar" style="width:{abs(d_sup)/max_abs*100:.0f}%; background:{'#10b981' if d_sup>0 else '#ef4444'}"></div></div></div>
        <div class="cf-cat-item"><span class="cf-cat-label">🏦 大單 (大戶)</span>
            <span class="cf-cat-val" style="color:{'#10b981' if d_big>0 else '#ef4444' if d_big<0 else '#94a3b8'}">{fmt_amount(d_big)}</span>
            <div class="cf-cat-bar-wrap"><div class="cf-cat-bar" style="width:{abs(d_big)/max_abs*100:.0f}%; background:{'#10b981' if d_big>0 else '#ef4444'}"></div></div></div>
        <div class="cf-cat-item"><span class="cf-cat-label">👤 中單 (中產)</span>
            <span class="cf-cat-val" style="color:{'#10b981' if d_mid>0 else '#ef4444' if d_mid<0 else '#94a3b8'}">{fmt_amount(d_mid)}</span>
            <div class="cf-cat-bar-wrap"><div class="cf-cat-bar" style="width:{abs(d_mid)/max_abs*100:.0f}%; background:{'#10b981' if d_mid>0 else '#ef4444'}"></div></div></div>
        <div class="cf-cat-item"><span class="cf-cat-label">. 小單 (散户)</span>
            <span class="cf-cat-val" style="color:{'#10b981' if d_sml>0 else '#ef4444' if d_sml<0 else '#94a3b8'}">{fmt_amount(d_sml)}</span>
            <div class="cf-cat-bar-wrap"><div class="cf-cat-bar" style="width:{abs(d_sml)/max_abs*100:.0f}%; background:{'#10b981' if d_sml>0 else '#ef4444'}"></div></div></div>'''
    else:
        cf = {'value': 'N/A', 'signal': '中性', 'raw': 0}
        cf_color = '#94a3b8'; cf_icon = '⚪'; cf_signal_cls = 'neutral'
        cf_cats_html = '<span style="color:#64748b;">無資金流向數據</span>'
        iv_class = 'neutral'; iv_text = '無數據'
        institution_flow = retail_flow = inst_pct = 0

    # 動作建議
    actions_html = ''.join(f'<li>{act}</li>' for act in adv.get('actions', []))

    stock_card = f'''<div class="stock-card">
        <div class="card-header">
            <div class="header-left">
                <h3>{a['name']} <small>({a['code']})</small></h3>
            </div>
            <div class="header-right">
                <div class="consensus-badge" style="background:{cs_color}20; border-color:{cs_color}; color:{cs_color}">
                    {cs_emoji} {cs_label}
                </div>
                <div class="consensus-strength">{adv.get('strength', '')}</div>
            </div>
        </div>
        <div class="card-top">
            <div class="price-block">
                <div class="price-now">HKD {a['current_price']:.2f}</div>
                <div class="pnl" style="color:{pnl_color}">{pnl_sign}{a['change']:.2f} ({pnl_sign}{a['change_pct']:.2f}%)</div>
            </div>
            <div class="holding-info">
                <div class="info-row"><span class="info-label">換手率</span><span class="info-val">{a['turnover']:.2f}%</span></div>
                <div class="info-row"><span class="info-label">策略共識</span><span class="info-val">{votes.get('consensus', 'N/A')}</span></div>
                <div class="info-row"><span class="info-label">最優策略</span><span class="info-val">{best or 'N/A'}</span></div>
            </div>
        </div>
        <div class="card-grid">
            <div class="grid-section">
                <h4>📈 技術指標</h4>
                <div class="ind-groups">
                    <div class="ind-group"><div class="ind-group-title">動量</div><div class="ind-group-items">
                        <div class="ind-item"><span class="ind-label">RSI(14)</span><span class="ind-val">{rsi:.1f}</span>{rsi_badge}</div>
                        <div class="ind-item"><span class="ind-label">MACD</span><span class="ind-val">{mh:.4f}</span>{macd_badge}</div>
                    </div></div>
                    <div class="ind-group"><div class="ind-group-title">均線</div><div class="ind-group-items">
                        <div class="ind-item"><span class="ind-label">EMA20</span><span class="ind-val">{ind.get("ema20",0):.2f}</span><span class="badge {'badge-green' if a['current_price']>ind.get('ema20',0) else 'badge-red'}">{'上✅' if a['current_price']>ind.get('ema20',0) else '下⚠️'}</span></div>
                        <div class="ind-item"><span class="ind-label">EMA60</span><span class="ind-val">{ind.get("ema60",0):.2f}</span><span class="badge {'badge-green' if a['current_price']>ind.get('ema60',0) else 'badge-red'}">{'上✅' if a['current_price']>ind.get('ema60',0) else '下⚠️'}</span></div>
                    </div></div>
                    <div class="ind-group"><div class="ind-group-title">布林帶</div><div class="ind-group-items">
                        <div class="ind-item"><span class="ind-label">上軌</span><span class="ind-val">{ind.get("bb_upper",0):.2f}</span></div>
                        <div class="ind-item"><span class="ind-label">中軌</span><span class="ind-val">{ind.get("bb_mid",0):.2f}</span></div>
                        <div class="ind-item"><span class="ind-label">下軌</span><span class="ind-val">{ind.get("bb_lower",0):.2f}</span></div>
                    </div></div>
                    <div class="ind-group"><div class="ind-group-title">區間</div><div class="ind-group-items">
                        <div class="ind-item"><span class="ind-label">ATR(14)</span><span class="ind-val">{ind.get("atr",0):.2f}</span></div>
                        <div class="ind-item"><span class="ind-label">20日高</span><span class="ind-val">{ind.get("recent_high",0):.2f}</span></div>
                        <div class="ind-item"><span class="ind-label">20日低</span><span class="ind-val">{ind.get("recent_low",0):.2f}</span></div>
                    </div></div>
                </div>
            </div>
            <div class="grid-section">
                <h4>📊 支撐 / 阻力位</h4>
                <div class="levels-container">
                    <div class="levels-col"><div class="levels-title resist-title">🔺 阻力位</div>{ress_html or '<div class="level-empty">無明顯阻力</div>'}</div>
                    <div class="levels-col"><div class="levels-title support-title">🔻 支撐位</div>{sups_html or '<div class="level-empty">無明顯支撐</div>'}</div>
                </div>
                <div class="wr-section">
                    <h4>🏆 回測勝率 (近一年)</h4>
                    <table class="wr-table"><thead><tr><th>策略</th><th>勝率</th><th>回報</th><th>夏普</th><th>回撤</th><th>次數</th></tr></thead><tbody>{wr_rows}</tbody></table>
                </div>
                <div class="votes-section">
                    <h4>🗳️ 策略投票 <small>({votes.get('consensus', 'N/A')})</small></h4>
                    <div class="votes-row">{votes_html}</div>
                </div>
            </div>
        </div>
        <div class="capital-flow-main">
            <h4>💰 資金流向分析</h4>
            <div class="cf-overview">
                <div><div class="cf-net-label">今日淨流入</div><div class="cf-net-value" style="color:{cf_color}">{cf_icon} {cf.get('value','N/A')}</div></div>
                <span class="cf-net-signal {cf_signal_cls}">{cf.get('signal','N/A')}</span>
            </div>
            <div class="cf-categories">{cf_cats_html}</div>
            <div class="cf-compare-section">
                <h4>⚖️ 機構 vs 散户 對比</h4>
                <div class="cf-compare-grid">
                    <div class="cf-compare-card"><div class="label">🏢 機構 (特大+大單)</div>
                        <div class="value" style="color:{'#10b981' if institution_flow>0 else '#ef4444' if institution_flow<0 else '#94a3b8'}">{fmt_amount(institution_flow)}</div>
                        <div class="pct">佔成交 {inst_pct:.1f}%</div></div>
                    <div class="cf-compare-card"><div class="label">👤 散户 (中單+小單)</div>
                        <div class="value" style="color:{'#10b981' if retail_flow>0 else '#ef4444' if retail_flow<0 else '#94a3b8'}">{fmt_amount(retail_flow)}</div>
                        <div class="pct">佔成交 {100-inst_pct:.1f}%</div></div>
                </div>
                <div class="cf-compare-verdict {iv_class}">{iv_text}</div>
            </div>
        </div>
        <div class="card-advice">
            <h4>💡 交易建議</h4>
            <div class="advice-zones">
                <div class="zone buy-zone"><span class="zone-label">🟢 加倉區</span><span class="zone-range">{adv['buy_zone']['low']:.2f} — {adv['buy_zone']['high']:.2f}</span></div>
                <div class="zone sell-zone"><span class="zone-label">🔴 減倉區</span><span class="zone-range">{adv['sell_zone']['low']:.2f} — {adv['sell_zone']['high']:.2f}</span></div>
                <div class="zone stop-zone"><span class="zone-label">⏹ 止損位</span><span class="zone-range">{adv['stop_loss']:.2f}</span></div>
            </div>
            <ul class="advice-list">{actions_html}</ul>
        </div>
    </div>'''

    # 嵌入單股報告的完整 CSS（包含新增的資金流向區塊樣式）
    html = f'''<!DOCTYPE html>
<html lang="zh-HK">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>StockAI 個股分析 | {a['name']} ({a['code']}) | {t.strftime('%Y-%m-%d')}</title>
<style>
:root {{ --bg: #0b1120; --bg-card: #111827; --border: #1e293b; --accent: #3b82f6; --green: #10b981; --red: #ef4444; --yellow: #f59e0b; --text: #e2e8f0; --text-muted: #94a3b8; --radius: 12px; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; line-height: 1.6; }}
.container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
.report-header {{ text-align: center; padding: 30px 0 20px; border-bottom: 1px solid var(--border); margin-bottom: 30px; }}
.report-header h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
.report-header .subtitle {{ color: var(--text-muted); font-size: 14px; }}
.search-bar {{ display: flex; align-items: center; gap: 12px; max-width: 500px; margin: 0 auto 30px; }}
.search-bar input {{ flex: 1; padding: 12px 18px; border-radius: 10px; border: 1px solid var(--border); background: var(--bg-card); color: var(--text); font-size: 15px; outline: none; transition: border-color 0.2s; }}
.search-bar input:focus {{ border-color: var(--accent); }}
.search-bar input::placeholder {{ color: var(--text-muted); }}
.search-bar button {{ padding: 12px 28px; border-radius: 10px; border: none; background: var(--accent); color: #fff; font-size: 15px; font-weight: 600; cursor: pointer; }}
.search-bar button:hover {{ background: #2563eb; }}

.stock-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); margin-bottom: 24px; overflow: hidden; }}
.card-header {{ display: flex; justify-content: space-between; align-items: center; padding: 16px 24px; border-bottom: 1px solid var(--border); }}
.card-header h3 {{ font-size: 20px; font-weight: 600; }}
.card-header small {{ color: var(--text-muted); font-size: 14px; }}
.header-right {{ display: flex; align-items: center; gap: 10px; }}
.consensus-badge {{ padding: 4px 14px; border-radius: 20px; font-size: 14px; font-weight: 600; border: 1.5px solid; }}
.consensus-strength {{ font-size: 12px; color: var(--text-muted); }}
.card-top {{ display: flex; justify-content: space-between; align-items: center; padding: 16px 24px; border-bottom: 1px solid var(--border); }}
.price-now {{ font-size: 28px; font-weight: 700; }}
.pnl {{ font-size: 16px; font-weight: 600; margin-top: 4px; }}
.holding-info {{ text-align: right; }}
.info-row {{ margin-bottom: 2px; }}
.info-label {{ color: var(--text-muted); font-size: 13px; margin-right: 12px; }}
.info-val {{ font-size: 14px; font-weight: 500; }}
.card-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0; }}
.grid-section {{ padding: 20px 24px; border-right: 1px solid var(--border); }}
.grid-section:last-child {{ border-right: none; }}
.grid-section h4 {{ font-size: 15px; color: var(--text-muted); margin-bottom: 14px; font-weight: 600; }}

.ind-groups {{ display: flex; flex-direction: column; gap: 10px; }}
.ind-group {{ }}
.ind-group-title {{ font-size: 11px; color: var(--accent); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; font-weight: 600; }}
.ind-group-items {{ display: flex; flex-direction: column; gap: 4px; }}
.ind-item {{ display: flex; align-items: center; gap: 8px; padding: 5px 10px; background: rgba(255,255,255,0.03); border-radius: 6px; font-size: 13px; }}
.ind-label {{ color: var(--text-muted); min-width: 55px; }}
.ind-val {{ font-weight: 700; font-variant-numeric: tabular-nums; }}
.badge {{ display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }}
.badge-green {{ background: rgba(16,185,129,0.15); color: #10b981; }}
.badge-red {{ background: rgba(239,68,68,0.15); color: #ef4444; }}
.badge-yellow {{ background: rgba(245,158,11,0.15); color: #f59e0b; }}

.votes-row {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.vote-item {{ display: flex; flex-direction: column; align-items: center; padding: 8px 16px; background: rgba(255,255,255,0.03); border-radius: 8px; font-size: 13px; min-width: 90px; border: 1px solid var(--border); }}
.vote-name {{ color: var(--text-muted); font-size: 11px; margin-bottom: 2px; }}
.vote-sig {{ font-weight: 700; font-size: 14px; }}

.levels-container {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
.levels-col {{ }}
.levels-title {{ font-size: 12px; font-weight: 600; margin-bottom: 6px; padding-bottom: 3px; border-bottom: 1px solid var(--border); }}
.support-title {{ color: var(--green); }}
.resist-title {{ color: var(--red); }}
.level-item {{ display: flex; justify-content: space-between; padding: 4px 8px; font-size: 12px; background: rgba(255,255,255,0.03); border-radius: 4px; margin-bottom: 2px; }}
.level-label {{ color: var(--text-muted); }}
.level-val {{ font-weight: 600; font-variant-numeric: tabular-nums; }}
.level-dist {{ color: var(--text-muted); font-size: 11px; }}
.level-empty {{ color: var(--text-muted); font-size: 12px; padding: 6px 0; }}

.wr-section {{ margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--border); }}
.wr-section h4 {{ font-size: 13px; color: var(--text-muted); margin-bottom: 8px; font-weight: 600; }}
.wr-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
.wr-table th {{ color: var(--text-muted); font-weight: 600; text-align: left; padding: 4px 6px; border-bottom: 1px solid var(--border); }}
.wr-table td {{ padding: 4px 6px; border-bottom: 1px solid rgba(255,255,255,0.03); font-variant-numeric: tabular-nums; }}
.wr-table tr.best-strat {{ background: rgba(59,130,246,0.08); }}
.wr-table tr.best-strat td:first-child {{ color: var(--accent); font-weight: 600; }}

.votes-section {{ margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--border); }}
.votes-section h4 {{ font-size: 13px; color: var(--text-muted); margin-bottom: 8px; font-weight: 600; }}

/* 資金流向 */
.capital-flow-main {{ padding: 20px 24px; border-top: 1px solid var(--border); }}
.capital-flow-main h4 {{ font-size: 15px; color: var(--text-muted); margin-bottom: 14px; font-weight: 600; }}
.cf-overview {{ display: flex; align-items: center; gap: 20px; margin-bottom: 18px; padding: 16px 20px; background: rgba(255,255,255,0.02); border-radius: 10px; border: 1px solid var(--border); }}
.cf-net-label {{ font-size: 13px; color: var(--text-muted); }}
.cf-net-value {{ font-size: 28px; font-weight: 700; font-variant-numeric: tabular-nums; }}
.cf-net-signal {{ padding: 4px 12px; border-radius: 16px; font-size: 13px; font-weight: 600; }}
.cf-net-signal.inflow {{ background: rgba(16,185,129,0.15); color: #10b981; border: 1px solid rgba(16,185,129,0.3); }}
.cf-net-signal.outflow {{ background: rgba(239,68,68,0.15); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); }}
.cf-net-signal.neutral {{ background: rgba(148,163,184,0.15); color: #94a3b8; border: 1px solid rgba(148,163,184,0.3); }}
.cf-categories {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 18px; }}
.cf-cat-item {{ display: flex; flex-direction: column; gap: 4px; padding: 12px 14px; background: rgba(255,255,255,0.03); border-radius: 8px; border: 1px solid var(--border); transition: border-color 0.2s; }}
.cf-cat-item:hover {{ border-color: var(--accent); }}
.cf-cat-label {{ font-size: 12px; color: var(--text-muted); }}
.cf-cat-val {{ font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; }}
.cf-cat-bar-wrap {{ height: 4px; background: rgba(255,255,255,0.06); border-radius: 2px; margin-top: 2px; overflow: hidden; }}
.cf-cat-bar {{ height: 100%; border-radius: 2px; }}
.cf-compare-section {{ margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--border); }}
.cf-compare-section h4 {{ font-size: 15px; color: var(--text-muted); margin-bottom: 14px; font-weight: 600; }}
.cf-compare-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
.cf-compare-card {{ padding: 14px 16px; border-radius: 10px; text-align: center; border: 1px solid var(--border); background: var(--bg-card); }}
.cf-compare-card .label {{ font-size: 12px; color: var(--text-muted); margin-bottom: 4px; }}
.cf-compare-card .value {{ font-size: 20px; font-weight: 700; font-variant-numeric: tabular-nums; }}
.cf-compare-card .pct {{ font-size: 12px; color: var(--text-muted); margin-top: 2px; }}
.cf-compare-verdict {{ margin-top: 12px; padding: 10px 16px; border-radius: 8px; text-align: center; font-size: 14px; font-weight: 600; }}
.cf-compare-verdict.bullish {{ background: rgba(16,185,129,0.1); color: var(--green); border: 1px solid rgba(16,185,129,0.2); }}
.cf-compare-verdict.bearish {{ background: rgba(239,68,68,0.1); color: var(--red); border: 1px solid rgba(239,68,68,0.2); }}
.cf-compare-verdict.neutral {{ background: rgba(148,163,184,0.1); color: var(--text-muted); border: 1px solid rgba(148,163,184,0.2); }}

.card-advice {{ padding: 20px 24px; border-top: 1px solid var(--border); background: rgba(255,255,255,0.01); }}
.card-advice h4 {{ font-size: 15px; color: var(--text-muted); margin-bottom: 14px; font-weight: 600; }}
.advice-zones {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; margin-bottom: 14px; }}
.zone {{ padding: 12px 16px; border-radius: 10px; text-align: center; border: 1px solid var(--border); background: var(--bg-card); }}
.zone-label {{ display: block; font-size: 12px; color: var(--text-muted); margin-bottom: 4px; }}
.zone-range {{ display: block; font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; }}
.buy-zone .zone-range {{ color: var(--green); }}
.sell-zone .zone-range {{ color: var(--red); }}
.stop-zone .zone-range {{ color: var(--yellow); }}
.advice-list {{ padding-left: 20px; color: var(--text-muted); font-size: 13px; }}
.advice-list li {{ margin-bottom: 4px; }}

.footer {{ text-align: center; padding: 20px; color: var(--text-muted); font-size: 12px; border-top: 1px solid var(--border); margin-top: 20px; }}
@media (max-width: 768px) {{
    .card-grid {{ grid-template-columns: 1fr; }}
    .grid-section {{ border-right: none; border-bottom: 1px solid var(--border); }}
    .advice-zones {{ grid-template-columns: 1fr; }}
    .cf-categories {{ grid-template-columns: 1fr 1fr; }}
    .cf-compare-grid {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>
<div class="container">
    <div class="report-header">
        <h1>💰 StockAI 個股資金流向分析</h1>
        <div class="subtitle">{t.strftime('%Y-%m-%d %H:%M')} | 港股資金流動態追踪</div>
    </div>
    {stock_card}
    <div class="footer">
        ⚠️ 免責聲明: 本報告僅基於技術指標和資金流向數據，不構成投資建議。市場有風險，投資需謹慎。<br>
        Powered by StockAI v1.7 | Generated at {t.strftime('%Y-%m-%d %H:%M:%S')}
    </div>
</div>
</body></html>'''
    return html


# ═══════════════════════════════════════════
#  Top 200 體檢+資金流向掃描 (--mode scan)
# ═══════════════════════════════════════════

def run_scan_mode(fetcher, top_n=200, quote_ctx=None):
    """
    Step 1: 體檢評分 → Top N
    Step 2: 拉資金流向
    Step 3: 出排行榜 HTML
    
    Args:
        fetcher: DataFetcher 实例
        top_n: 返回 Top N
        quote_ctx: 可选的富途连接上下文（避免重复创建连接）
    """
    # 1. 體檢評分
    logger.info("=" * 60)
    logger.info("Step 1: 體檢評分掃描")
    logger.info("=" * 60)
    watchlist = load_watchlist()
    logger.info(f"自選股總數: {len(watchlist)}")
    if not watchlist:
        return None

    fa = FundamentalAnalyzer()
    top_stocks = load_health_scores(fa, watchlist, top_n, quote_ctx=quote_ctx)
    logger.info(f"有效體檢數: {len(top_stocks)}, 取 Top {top_n}")

    if not top_stocks:
        return None

    # 2. 拉資金流向 + 報價 + 量比（固定 0.4s 間隔）
    logger.info("Step 2: 拉取資金流向 + 量比...")
    missing_codes = []
    for i, s in enumerate(top_stocks):
        code = s['code']
        rank = i + 1
        logger.info(f"  [{rank}/{len(top_stocks)}] {s['name']} ({code})...")
        
        # 2a. 資金流向
        cf = fetcher.get_capital_flow(code)
        if cf:
            s['capital_flow'] = cf
            s['cf_raw'] = cf.get('raw', 0)
            details = cf.get('details', {})
            s['cf_super'] = details.get('super', 0)
            s['cf_big'] = details.get('big', 0)
            s['cf_mid'] = details.get('mid', 0)
            s['cf_sml'] = details.get('sml', 0)
            s['cf_institution'] = details.get('super', 0) + details.get('big', 0)
        else:
            s['capital_flow'] = None
            s['cf_raw'] = 0
            s['cf_super'] = s['cf_big'] = s['cf_mid'] = s['cf_sml'] = s['cf_institution'] = 0
            missing_codes.append({'code': code, 'name': s.get('name', code), 'rank': rank})
            logger.info(f"    {code} 無資金流向數據，加入缺失列表")

        # 2b. 報價（價格、成交量、換手率）
        quote = fetcher.get_quote(code)
        if quote:
            s['price'] = quote.get('price', 0)
            s['prev_close'] = quote.get('prev_close', 0)
            s['change_pct'] = ((quote.get('price', 0) - quote.get('prev_close', 0)) / quote.get('prev_close', 1) * 100) if quote.get('prev_close', 0) > 0 else 0
            s['volume'] = quote.get('volume', 0)
            s['turnover'] = quote.get('turnover_rate', 0)
        else:
            s['price'] = 0
            s['prev_close'] = 0
            s['change_pct'] = 0
            s['volume'] = 0
            s['turnover'] = 0

        # 2c. 量比（需 K 線計算 20 日均量）
        vol_ratio = None
        kline_df = fetcher.get_kline(code, days=25)
        if kline_df is not None and len(kline_df) >= 21:
            avg_vol_20 = kline_df['Volume'].iloc[-21:-1].mean()
            today_vol = kline_df['Volume'].iloc[-1]
            vol_ratio = round(today_vol / avg_vol_20, 2) if avg_vol_20 > 0 else None
            # Vol MA5/MA20 交叉
            vol_ma5 = kline_df['Volume'].iloc[-5:].mean()
            vol_ma5_prev = kline_df['Volume'].iloc[-6:-1].mean()
            vol_ma20 = kline_df['Volume'].iloc[-20:].mean()
            vol_ma20_prev = kline_df['Volume'].iloc[-21:-1].mean()
            s['vol_ma_cross'] = 'gold' if vol_ma5_prev <= vol_ma20_prev and vol_ma5 > vol_ma20 else 'dead' if vol_ma5_prev >= vol_ma20_prev and vol_ma5 < vol_ma20 else None
        else:
            s['vol_ma_cross'] = None
        s['vol_ratio'] = vol_ratio

        time.sleep(0.4)

    # 3. 按機構淨流入排序（機構在買 = 最信號）
    top_stocks.sort(key=lambda x: x.get('cf_institution', 0), reverse=True)

    return top_stocks, missing_codes


def render_scan_html(stocks, report_time):
    """渲染 Top 200 掃描排行榜 HTML"""
    t = report_time
    n = len(stocks)

    # 概覽統計
    inst_inflow = sum(1 for s in stocks if s.get('cf_institution', 0) > 0)
    inst_outflow = sum(1 for s in stocks if s.get('cf_institution', 0) < 0)
    total_net = sum(s.get('cf_raw', 0) for s in stocks)
    vol_breakout_count = sum(1 for s in stocks if s.get('vol_ratio') and s['vol_ratio'] >= 1.8)

    # 表格行
    rows = ''
    for i, s in enumerate(stocks):
        cf = s.get('capital_flow')
        score = s['score']
        grade = s['grade']
        no_data = cf is None
        
        if no_data:
            cf_val = '⚠️ 無數據'
            cf_sig = '無數據'
            cf_icon = '⚠️'
            cf_color = '#f59e0b'
            row_bg = 'background: rgba(245,158,11,0.06); opacity: 0.7;'
        else:
            cf_val = cf.get('value', 'N/A')
            cf_sig = cf.get('signal', 'N/A')
            cf_icon = '🟢' if cf_sig == '正流入' else '🔴' if cf_sig == '負流出' else '⚪'
            cf_color = '#10b981' if cf_sig == '正流入' else '#ef4444' if cf_sig == '負流出' else '#94a3b8'
            row_bg = 'background: rgba(16,185,129,0.05);' if s.get('cf_institution', 0) > 0 else ''
        inst_val = fmt_amount(s.get('cf_institution', 0))
        inst_color = '#10b981' if s.get('cf_institution', 0) > 0 else '#ef4444' if s.get('cf_institution', 0) < 0 else '#94a3b8'

        # 背景高亮：機構淨流入 > 0
        row_bg = 'background: rgba(16,185,129,0.05);' if s.get('cf_institution', 0) > 0 else ''

        # 價格 & 漲跌幅
        price_val = f"{s.get('price', 0):.2f}" if s.get('price', 0) > 0 else 'N/A'
        chg_pct = s.get('change_pct', 0)
        if chg_pct > 0:
            chg_str = f'+{chg_pct:.2f}%'
            chg_color = '#ef4444'  # 港股紅漲
        elif chg_pct < 0:
            chg_str = f'{chg_pct:.2f}%'
            chg_color = '#10b981'  # 港股綠跌
        else:
            chg_str = '0.00%'
            chg_color = '#94a3b8'

        # 量比
        vol_ratio = s.get('vol_ratio')
        vol_cross = s.get('vol_ma_cross')
        if vol_ratio is not None:
            if vol_ratio >= 2.0:
                vr_color = '#ef4444'
                vr_tag = '🔥' if chg_pct > 0 else '⚠️'
            elif vol_ratio >= 1.5:
                vr_color = '#f59e0b'
                vr_tag = '📈'
            else:
                vr_color = '#94a3b8'
                vr_tag = ''
            cross_tag = ''
            if vol_cross == 'gold':
                cross_tag = ' <span style="color:#ef4444; font-size:10px;">Vol↑</span>'
            elif vol_cross == 'dead':
                cross_tag = ' <span style="color:#10b981; font-size:10px;">Vol↓</span>'
            vol_str = f'{vr_tag}<span style="color:{vr_color}; font-weight:600;">{vol_ratio:.1f}</span>{cross_tag}'
        else:
            vol_str = '<span style="color:#4b5563;">N/A</span>'

        rows += f'''<tr data-code="{s['code']}" style="{row_bg}">
            <td style="font-weight:600; color:var(--accent)">{i+1}</td>
            <td style="font-weight:600">{s['name']}</td>
            <td>{s['code']}</td>
            <td><span style="font-weight:700">{score}/{s['total']}</span> <small style="color:var(--yellow)">{grade}</small></td>
            <td style="font-weight:600">{price_val}</td>
            <td style="color:{chg_color}; font-weight:600">{chg_str}</td>
            <td>{vol_str}</td>
            <td style="color:{cf_color}; font-weight:700">{cf_icon} {cf_val}</td>
            <td style="color:{'#10b981' if s.get('cf_super',0)>0 else '#ef4444' if s.get('cf_super',0)<0 else '#94a3b8'}">{fmt_amount(s.get('cf_super', 0))}</td>
            <td style="color:{'#10b981' if s.get('cf_big',0)>0 else '#ef4444' if s.get('cf_big',0)<0 else '#94a3b8'}">{fmt_amount(s.get('cf_big', 0))}</td>
            <td style="color:{inst_color}; font-weight:700">{inst_val}</td>
        </tr>'''

    html = f'''<!DOCTYPE html>
<html lang="zh-HK">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>StockAI 資金流向掃描 | {t.strftime('%Y-%m-%d')}</title>
<style>
:root {{ --bg: #0b1120; --bg-card: #111827; --border: #1e293b; --accent: #3b82f6; --green: #10b981; --red: #ef4444; --yellow: #f59e0b; --text: #e2e8f0; --text-muted: #94a3b8; --radius: 12px; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; line-height: 1.6; }}
.container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
.report-header {{ text-align: center; padding: 30px 0 20px; border-bottom: 1px solid var(--border); margin-bottom: 30px; }}
.report-header h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
.report-header .subtitle {{ color: var(--text-muted); font-size: 14px; }}

.overview {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin-bottom: 24px; }}
.ov-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px 20px; text-align: center; }}
.ov-label {{ font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }}
.ov-val {{ font-size: 24px; font-weight: 700; }}
.ov-val.green {{ color: var(--green); }}
.ov-val.red {{ color: var(--red); }}
.ov-val.yellow {{ color: var(--yellow); }}

.scan-note {{ padding: 14px 20px; background: rgba(59,130,246,0.08); border: 1px solid rgba(59,130,246,0.2); border-radius: 10px; margin-bottom: 24px; font-size: 14px; color: var(--text-muted); }}
.scan-note strong {{ color: var(--accent); }}

.scan-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
.scan-table thead {{ position: sticky; top: 0; z-index: 10; }}
.scan-table th {{ background: var(--bg-card); color: var(--text-muted); font-weight: 600; text-align: left; padding: 10px 8px; border-bottom: 2px solid var(--border); font-size: 12px; white-space: nowrap; }}
.scan-table td {{ padding: 8px; border-bottom: 1px solid rgba(255,255,255,0.03); font-variant-numeric: tabular-nums; white-space: nowrap; }}
.scan-table tr:hover {{ background: rgba(255,255,255,0.04); }}

.legend {{ display: flex; gap: 20px; margin-bottom: 16px; font-size: 12px; color: var(--text-muted); }}
.legend span {{ display: flex; align-items: center; gap: 4px; }}
.legend .dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}

.footer {{ text-align: center; padding: 20px; color: var(--text-muted); font-size: 12px; border-top: 1px solid var(--border); margin-top: 20px; }}
@media (max-width: 768px) {{
    .overview {{ grid-template-columns: 1fr 1fr; }}
    .scan-table {{ font-size: 11px; }}
    .scan-table th, .scan-table td {{ padding: 6px 4px; }}
}}
</style>
</head>
<body>
<div class="container">
    <div class="report-header">
        <h1>💰 StockAI 資金流向掃描排行榜</h1>
        <div class="subtitle">{t.strftime('%Y-%m-%d %H:%M')} | 體檢 Top {n} + 資金流向篩選</div>
    </div>
    <div class="overview">
        <div class="ov-card"><div class="ov-label">掃描股票數</div><div class="ov-val">{n}</div></div>
        <div class="ov-card"><div class="ov-label">機構淨流入</div><div class="ov-val green">{inst_inflow}</div></div>
        <div class="ov-card"><div class="ov-label">機構淨流出</div><div class="ov-val red">{inst_outflow}</div></div>
        <div class="ov-card"><div class="ov-label">總淨流入</div><div class="ov-val {'green' if total_net>=0 else 'red'}">{fmt_amount(total_net)}</div></div>
        <div class="ov-card"><div class="ov-label">🔥 放量股</div><div class="ov-val yellow">{vol_breakout_count}</div></div>
    </div>
    <div class="scan-note">
        <strong>筛选逻辑:</strong> 體檢評分排序取 Top {n} → 拉取資金流向+量比 → 按機構淨流入（特大單+大單）降序排列<br>
        <strong>🔥</strong> = 量比≥2.0 放量股（紅色=放量漲，⚠️=放量跌）&nbsp;|&nbsp;<strong>Vol↑/Vol↓</strong> = Vol MA5/MA20 金叉/死叉<br>
        <strong>绿色高亮行</strong> = 機構正在買入的股票，值得關注
    </div>
    <div class="legend">
        <span><span class="dot" style="background:var(--green)"></span> 機構淨流入 (關注)</span>
        <span><span class="dot" style="background:var(--red)"></span> 機構淨流出 (警惕)</span>
        <span><span class="dot" style="background:var(--text-muted)"></span> 無明顯方向</span>
        <span>🔥<span class="dot" style="background:var(--yellow)"></span> 量比≥1.5</span>
    </div>
    <table class="scan-table">
        <thead><tr>
            <th>#</th><th>股票名稱</th><th>代碼</th><th>體檢評分</th>
            <th>價格</th><th>漲跌幅</th><th>量比</th>
            <th>淨流入</th><th>特大單</th><th>大單</th><th>機構淨流入</th>
        </tr></thead>
        <tbody>{rows}</tbody>
    </table>
    <div class="footer">
        ⚠️ 免責聲明: 本報告僅基於體檢評分和資金流向數據，不構成投資建議。市場有風險，投資需謹慎。<br>
        Powered by StockAI v1.7 | Generated at {t.strftime('%Y-%m-%d %H:%M:%S')}
    </div>
</div>
</body></html>'''
    return html

def main():
    parser = argparse.ArgumentParser(description='StockAI 每日交易建議報告')
    parser.add_argument('--output', '-o', default=None, help='輸出目錄 (默認: backend/reports/)')
    parser.add_argument('--no-futu', action='store_true', help='不連接富途 (測試用)')
    parser.add_argument('--mode', choices=['default', 'single', 'scan'], default='default',
                        help='報告模式: default=持倉報告, single=單股分析, scan=Top50掃描')
    parser.add_argument('--code', default=None, help='股票代碼 (--mode single 時必填)')
    parser.add_argument('--top', type=int, default=200, help='掃描模式取 Top N (默認: 200)')
    args = parser.parse_args()

    report_time = datetime.now()
    output_dir = Path(args.output) if args.output else BACKEND_DIR / 'reports'
    output_dir.mkdir(parents=True, exist_ok=True)

    # ═══════════════════════════════════════════
    #  --mode single: 單股資金流向分析
    # ═══════════════════════════════════════════
    if args.mode == 'single':
        if not args.code:
            logger.error("--mode single 需要 --code 參數 (例: --code 00700)")
            sys.exit(1)
        code = args.code.strip()
        logger.info("=" * 60)
        logger.info(f"單股分析: {code}")
        logger.info("=" * 60)

        fetcher = DataFetcher()
        if not args.no_futu:
            if not fetcher.connect():
                logger.error("富途連接失敗")
                sys.exit(1)
        else:
            logger.warning("測試模式: 不連接富途")

        analysis = generate_single_stock_report(fetcher, code)
        if 'error' in analysis:
            logger.error(f"分析失敗: {analysis['error']}")
            fetcher.close()
            sys.exit(1)

        html = render_single_html(analysis, report_time)
        date_str = report_time.strftime('%Y%m%d_%H%M')
        html_path = output_dir / f"single_{code}_{date_str}.html"
        html_path.write_text(html, encoding='utf-8')
        logger.info(f"HTML 報告: {html_path}")

        cf = analysis.get('capital_flow', {})
        print(f"\n📊 {analysis['name']} ({code}) @ HKD {analysis['current_price']:.2f}")
        print(f"   涨跌: {analysis['change']:+.2f} ({analysis['change_pct']:+.2f}%)")
        print(f"   資金流向: {cf.get('value', 'N/A')} ({cf.get('signal', 'N/A')})")
        print(f"   策略共識: {analysis['votes'].get('consensus', 'N/A')}")
        print(f"\n🌐 報告: {html_path}")

        fetcher.close()
        return str(html_path)

    # ═══════════════════════════════════════════
    #  --mode scan: Top N 體檢+資金流向掃描
    # ═══════════════════════════════════════════
    if args.mode == 'scan':
        logger.info("=" * 60)
        logger.info(f"Top {args.top} 資金流向掃描")
        logger.info("=" * 60)

        fetcher = DataFetcher()
        if not args.no_futu:
            if not fetcher.connect():
                logger.error("富途連接失敗")
                sys.exit(1)
        else:
            logger.warning("測試模式: 不連接富途")

        stocks = run_scan_mode(fetcher, args.top, quote_ctx=fetcher.quote_ctx)
        if not stocks:
            logger.error("無有效掃描結果")
            fetcher.close()
            sys.exit(1)

        html = render_scan_html(stocks, report_time)
        date_str = report_time.strftime('%Y%m%d_%H%M')
        html_path = output_dir / f"scan_top{args.top}_{date_str}.html"
        html_path.write_text(html, encoding='utf-8')
        logger.info(f"HTML 報告: {html_path}")

        # 輸出 Top 10 摘要
        inst_pos = [s for s in stocks if s.get('cf_institution', 0) > 0]
        print(f"\n📊 掃描完成: {len(stocks)} 只股票")
        print(f"   機構淨流入: {len(inst_pos)} 只")
        print(f"\n🏆 Top 5 機構淨流入:")
        for s in stocks[:5]:
            print(f"   {s['name']} ({s['code']}) 體檢{s['score']}/{s['total']} {s['grade']} | 機構: {fmt_amount(s.get('cf_institution', 0))}")
        print(f"\n🌐 報告: {html_path}")

        fetcher.close()
        return str(html_path)

    # ═══════════════════════════════════════════
    #  --mode default: 原有持倉報告
    # ═══════════════════════════════════════════

    report_time = datetime.now()
    output_dir = Path(args.output) if args.output else BACKEND_DIR / 'reports'
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("StockAI 每日交易建議報告")
    logger.info("=" * 60)

    # 1. 讀持倉（先用成本價，連富途後用即時價更新）
    portfolio = load_portfolio()
    if not portfolio:
        logger.error("無法讀取持倉數據，退出")
        sys.exit(1)

    # holdings 已經是 list 格式（來自 PaperAccount.get_portfolio）
    holdings = portfolio.get('holdings', [])

    logger.info(f"持倉數量: {len(holdings)}, 現金: HKD {portfolio['cash']:,.0f}")
    logger.info(f"總資產: HKD {portfolio['total_assets']:,.0f}, 已實現盈虧: {portfolio['realized_pnl']:+,.0f}")

    if not holdings:
        logger.info("當前無持倉，無需生成報告")
        md = f"# 📊 StockAI 每日交易建議報告\n\n{report_time.strftime('%Y-%m-%d %H:%M')}\n\n當前無持倉。"
        report_path = output_dir / f"report_{report_time.strftime('%Y%m%d_%H%M')}.md"
        report_path.write_text(md, encoding='utf-8')
        print(f"空報告已保存: {report_path}")
        return

    # 2. 連接富途
    fetcher = DataFetcher()
    if not args.no_futu:
        if not fetcher.connect():
            logger.error("富途連接失敗，請確認 OpenD 已啟動")
            sys.exit(1)
    else:
        logger.warning("測試模式: 不連接富途")

    # 3. 逐股分析
    analyses = []
    price_map = {}  # 收集即時價格
    for h in holdings:
        code = h.get('code', '')
        qty = h.get('quantity', 0)
        avg = h.get('avg_cost', 0)
        logger.info(f"分析 {code} ({qty}股 @ {avg})...")

        if args.no_futu:
            analyses.append({'code': code, 'name': code, 'error': '測試模式，未連接富途'})
            continue

        analysis = generate_stock_analysis(fetcher, code, qty, avg)
        analyses.append(analysis)

        # 收集即時價格
        if 'error' not in analysis:
            price_map[code] = analysis['current_price']
            consensus = analysis['advice']['consensus']
            logger.info(f"  → {analysis['name']} | 現價 {analysis['current_price']} | 共識 {consensus}")

    # 用即時價格重新計算 portfolio（浮動盈虧準確）
    if price_map:
        portfolio = load_portfolio(price_map)
        holdings = portfolio.get('holdings', [])

    # 4. 生成報告
    md = generate_markdown_report(portfolio, analyses, report_time)
    html = generate_html_report(portfolio, analyses, report_time)

    # 保存 Markdown
    date_str = report_time.strftime('%Y%m%d_%H%M')
    md_path = output_dir / f"report_{date_str}.md"
    md_path.write_text(md, encoding='utf-8')
    logger.info(f"Markdown 報告: {md_path}")

    # 保存 JSON
    json_path = output_dir / f"report_{date_str}.json"
    json_data = {
        'report_time': report_time.isoformat(),
        'portfolio': {
            'cash': portfolio['cash'],
            'initial_cash': portfolio.get('initial_cash', INITIAL_CASH),
            'total_assets': portfolio.get('total_assets', 0),
            'market_value': portfolio.get('market_value', 0),
            'realized_pnl': portfolio.get('realized_pnl', 0),
            'unrealized_pnl': portfolio.get('unrealized_pnl', 0),
            'total_pnl': portfolio.get('total_pnl', 0),
            'total_return_pct': portfolio.get('total_return_pct', 0),
            'holdings_count': len(holdings),
        },
        'analyses': analyses,
    }
    json_path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding='utf-8')
    logger.info(f"JSON 數據: {json_path}")

    # 保存 HTML
    html_path = output_dir / f"report_{date_str}.html"
    html_path.write_text(html, encoding='utf-8')
    logger.info(f"HTML 報告: {html_path}")

    # 5. 輸出到控制台（摘要）
    print("\n" + "=" * 60)
    print(f"📊 報告已生成: {report_time.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    print(f"💰 總資產: HKD {portfolio['total_assets']:,.0f} | "
          f"已實現: {portfolio['realized_pnl']:+,.0f} | "
          f"未實現: {portfolio['unrealized_pnl']:+,.0f} | "
          f"總盈虧: {portfolio['total_pnl']:+,.0f} ({portfolio['total_return_pct']:+.2f}%)")
    print()
    for a in analyses:
        if 'error' in a:
            print(f"  ❌ {a['code']}: {a['error']}")
            continue
        emoji_map = {'BULLISH': '🟢', 'BEARISH': '🔴', 'NEUTRAL': '🟡'}
        emoji = emoji_map.get(a['advice']['consensus'], '⚪')
        bz = a['advice']['buy_zone']
        sz = a['advice']['sell_zone']
        sl = a['advice']['stop_loss']
        print(f"  {emoji} {a['name']} ({a['code']}) @ {a['current_price']}")
        print(f"     持倉 {a['quantity']}股 | 盈虧 {a['pnl']:+,.0f} ({a['pnl_pct']:+.2f}%)")
        print(f"     加倉: {bz['low']}-{bz['high']} | 減倉: {sz['low']}-{sz['high']} | 止損: {sl}")
        print(f"     策略共識: {a['votes']['consensus']} ({a['votes']['strength']}) | 最優: {a['winrate'].get('best_strategy', 'N/A')}")
        print()

    print(f"📄 完整報告: {md_path}")
    print(f"🌐 HTML 報告: {html_path}")

    # 關閉連接
    fetcher.close()

    return md_path


if __name__ == '__main__':
    main()
