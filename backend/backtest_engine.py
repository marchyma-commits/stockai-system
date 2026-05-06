"""
StockAI Backtest Engine — 回测引擎
StockAI v1.7 | 2026-04-21

核心能力:
  - 多策略回测 (EMA交叉 / MACD / RSI / 布林带 / 成交量突破 / 综合评分)
  - 完整绩效指标 (夏普/Sortino/Calmar/最大回撤/胜率/Beta/Alpha)
  - 逐日净值曲线 + 交易记录
  - Walk-Forward 验证 (防过拟合)

数据源: 富途 OpenD K线 (通过 StockAnalyzer.get_kline_data)
"""

import json, math, logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from copy import deepcopy

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
#  PerformanceMetrics — 绩效指标计算
# ═══════════════════════════════════════════

class PerformanceMetrics:
    """纯函数式绩效计算，不依赖外部状态"""

    @staticmethod
    def calc_all(daily_returns, benchmark_returns=None, risk_free_rate=0.02):
        """
        计算全部绩效指标

        Args:
            daily_returns: list[float] — 策略每日收益率序列
            benchmark_returns: list[float] | None — 基准每日收益率 (恒指)
            risk_free_rate: float — 无风险年利率 (默认2%)
        Returns:
            dict — 所有绩效指标
        """
        if not daily_returns or len(daily_returns) < 5:
            return PerformanceMetrics._empty()

        returns = np.array(daily_returns, dtype=float)
        n_trading_days = len(returns)

        # --- 基础统计 ---
        total_return = float(np.prod(1 + returns) - 1)
        trading_years = max(n_trading_days / 252, 0.01)
        annual_return = float((1 + total_return) ** (1 / trading_years) - 1)
        daily_vol = float(np.std(returns, ddof=1)) if n_trading_days > 1 else 0
        annual_vol = float(daily_vol * math.sqrt(252))

        # --- 夏普比率 (年化) ---
        daily_rf = risk_free_rate / 252
        excess_returns = returns - daily_rf
        sharpe = float(np.mean(excess_returns) / daily_vol * math.sqrt(252)) if daily_vol > 0 else 0

        # --- Sortino 比率 (只惩罚下行波动) ---
        downside = returns[returns < 0]
        downside_vol = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0001
        sortino = float(np.mean(excess_returns) / downside_vol * math.sqrt(252))

        # --- 最大回撤 ---
        cumulative = np.cumprod(1 + returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = (cumulative - running_max) / running_max
        max_drawdown = float(np.min(drawdowns))
        max_dd_duration = PerformanceMetrics._max_drawdown_duration(drawdowns)

        # --- Calmar 比率 ---
        calmar = abs(annual_return / max_drawdown) if max_drawdown != 0 else 0

        # --- Beta / Alpha (vs 基准) ---
        beta = 0.0
        alpha = 0.0
        if benchmark_returns and len(benchmark_returns) == n_trading_days:
            bm = np.array(benchmark_returns, dtype=float)
            cov_mat = np.cov(returns, bm)
            bm_var = np.var(bm, ddof=1)
            if bm_var > 0:
                beta = float(cov_mat[0][1] / bm_var)
                bm_annual = float((1 + np.prod(1 + bm) - 1) ** (1 / trading_years) - 1)
                alpha = annual_return - (risk_free_rate + beta * (bm_annual - risk_free_rate))

        # --- 胜率 / 盈亏比 (基于正负收益日) ---
        win_days = int(np.sum(returns > 0))
        loss_days = int(np.sum(returns < 0))
        total_wl = win_days + loss_days
        win_rate = win_days / total_wl if total_wl > 0 else 0
        avg_win = float(np.mean(returns[returns > 0])) if win_days > 0 else 0
        avg_loss = float(abs(np.mean(returns[returns < 0]))) if loss_days > 0 else 0.0001
        profit_loss_ratio = avg_win / avg_loss

        return {
            'total_return': round(total_return * 100, 2),
            'annual_return': round(annual_return * 100, 2),
            'annual_volatility': round(annual_vol * 100, 2),
            'max_drawdown': round(max_drawdown * 100, 2),
            'max_dd_duration_days': max_dd_duration,
            'sharpe_ratio': round(sharpe, 2),
            'sortino_ratio': round(sortino, 2),
            'calmar_ratio': round(calmar, 2),
            'win_rate': round(win_rate * 100, 1),
            'profit_loss_ratio': round(profit_loss_ratio, 2),
            'beta': round(beta, 2),
            'alpha': round(alpha * 100, 2),
            'trading_days': n_trading_days,
            'win_days': win_days,
            'loss_days': loss_days,
        }

    @staticmethod
    def _max_drawdown_duration(drawdowns):
        """计算最大回撤持续天数"""
        in_drawdown = False
        max_duration = 0
        current_duration = 0
        for dd in drawdowns:
            if dd < 0:
                if not in_drawdown:
                    in_drawdown = True
                    current_duration = 1
                else:
                    current_duration += 1
                max_duration = max(max_duration, current_duration)
            else:
                in_drawdown = False
                current_duration = 0
        return max_duration

    @staticmethod
    def _empty():
        return {k: None for k in [
            'total_return', 'annual_return', 'annual_volatility',
            'max_drawdown', 'max_dd_duration_days', 'sharpe_ratio',
            'sortino_ratio', 'calmar_ratio', 'win_rate',
            'profit_loss_ratio', 'beta', 'alpha',
            'trading_days', 'win_days', 'loss_days',
        ]}


# ═══════════════════════════════════════════
#  Strategy — 策略基类 & 内置策略
# ═══════════════════════════════════════════

class Signal:
    """交易信号"""
    BUY = 'BUY'
    SELL = 'SELL'
    HOLD = 'HOLD'


class BaseStrategy:
    """策略基类"""

    name = 'base'
    description = ''

    def __init__(self, params=None):
        self.params = params or {}

    def generate_signals(self, df):
        """
        生成交易信号序列

        Args:
            df: pd.DataFrame — 需含 Open, High, Low, Close, Volume
        Returns:
            list[str] — 每个bar的信号 (BUY/SELL/HOLD)，长度与df相同
        """
        raise NotImplementedError


class EMACrossStrategy(BaseStrategy):
    """EMA 交叉策略 — 短期 EMA 上穿长期 EMA 买入，下穿卖出"""

    name = 'EMA Cross'
    description = '短期EMA上穿长期EMA买入，下穿卖出'

    def __init__(self, params=None):
        super().__init__(params)
        self.fast_period = self.params.get('fast_period', 12)
        self.slow_period = self.params.get('slow_period', 26)

    def generate_signals(self, df):
        closes = df['Close'].values
        fast_ema = self._calc_ema(closes, self.fast_period)
        slow_ema = self._calc_ema(closes, self.slow_period)
        signals = [Signal.HOLD] * len(closes)

        for i in range(max(self.fast_period, self.slow_period), len(closes)):
            if fast_ema[i] is not None and slow_ema[i] is not None:
                prev_fast = fast_ema[i - 1] if fast_ema[i - 1] is not None else fast_ema[i]
                prev_slow = slow_ema[i - 1] if slow_ema[i - 1] is not None else slow_ema[i]
                # 金叉
                if prev_fast <= prev_slow and fast_ema[i] > slow_ema[i]:
                    signals[i] = Signal.BUY
                # 死叉
                elif prev_fast >= prev_slow and fast_ema[i] < slow_ema[i]:
                    signals[i] = Signal.SELL

        return signals

    @staticmethod
    def _calc_ema(data, period):
        if len(data) < period:
            return [None] * len(data)
        k = 2 / (period + 1)
        result = [None] * (period - 1)
        first_ema = sum(data[:period]) / period
        result.append(first_ema)
        for i in range(period, len(data)):
            result.append(data[i] * k + result[-1] * (1 - k))
        return result


class MACDStrategy(BaseStrategy):
    """MACD 策略 — MACD 柱状图翻正买入，翻负卖出"""

    name = 'MACD'
    description = 'MACD柱状图翻正买入，翻负卖出'

    def __init__(self, params=None):
        super().__init__(params)
        self.fast = self.params.get('fast', 12)
        self.slow = self.params.get('slow', 26)
        self.signal_period = self.params.get('signal', 9)

    def generate_signals(self, df):
        closes = df['Close'].values
        macd_line = self._calc_macd(closes)
        signals = [Signal.HOLD] * len(closes)

        # signal_line: 对 macd_line 中有效值做 EMA，结果对齐回原索引
        valid_macd = [(i, v) for i, v in enumerate(macd_line) if v is not None]
        if len(valid_macd) < self.signal_period:
            return signals

        # 提取有效 MACD 值计算 signal EMA
        macd_values = [v for _, v in valid_macd]
        signal_ema_vals = self._calc_ema(macd_values, self.signal_period)

        # 建立 index → signal value 映射
        signal_line = [None] * len(closes)
        for j, (orig_idx, _) in enumerate(valid_macd):
            if j >= self.signal_period - 1 and j < len(signal_ema_vals):
                signal_line[orig_idx] = signal_ema_vals[j]

        start = self.fast + self.slow - 1 + self.signal_period - 1

        for i in range(start, len(closes)):
            if macd_line[i] is not None and signal_line[i] is not None and macd_line[i-1] is not None and signal_line[i-1] is not None:
                prev_hist = macd_line[i-1] - signal_line[i-1]
                curr_hist = macd_line[i] - signal_line[i]
                if prev_hist <= 0 and curr_hist > 0:
                    signals[i] = Signal.BUY
                elif prev_hist >= 0 and curr_hist < 0:
                    signals[i] = Signal.SELL

        return signals

    def _calc_macd(self, data):
        fast_ema = self._calc_ema(data, self.fast)
        slow_ema = self._calc_ema(data, self.slow)
        if not fast_ema or not slow_ema:
            return []
        return [f - s if (f is not None and s is not None) else None
                for f, s in zip(fast_ema, slow_ema)]

    @staticmethod
    def _calc_ema(data, period):
        if len(data) < period:
            return [None] * len(data)
        k = 2 / (period + 1)
        result = [None] * (period - 1)
        first_ema = sum(data[:period]) / period
        result.append(first_ema)
        for i in range(period, len(data)):
            result.append(data[i] * k + result[-1] * (1 - k))
        return result


class RSIStrategy(BaseStrategy):
    """RSI 策略 — RSI 超卖买入，超买卖出"""

    name = 'RSI'
    description = 'RSI低于超卖线买入，高于超买线卖出'

    def __init__(self, params=None):
        super().__init__(params)
        self.period = self.params.get('period', 14)
        self.oversold = self.params.get('oversold', 30)
        self.overbought = self.params.get('overbought', 70)

    def generate_signals(self, df):
        closes = df['Close'].values
        rsi = self._calc_rsi(closes, self.period)
        signals = [Signal.HOLD] * len(closes)

        for i in range(self.period, len(closes)):
            if rsi[i] is not None:
                if rsi[i-1] is not None:
                    # 从超卖区域回升
                    if rsi[i-1] < self.oversold and rsi[i] >= self.oversold:
                        signals[i] = Signal.BUY
                    # 从超买区域回落
                    elif rsi[i-1] > self.overbought and rsi[i] <= self.overbought:
                        signals[i] = Signal.SELL
                # 直接进入极端区域也触发
                elif rsi[i] < self.oversold:
                    signals[i] = Signal.BUY
                elif rsi[i] > self.overbought:
                    signals[i] = Signal.SELL

        return signals

    @staticmethod
    def _calc_rsi(data, period):
        if len(data) < period + 1:
            return [None] * len(data)
        result = [None] * period
        gains, losses = [], []
        for i in range(period, len(data)):
            change = data[i] - data[i-1]
            gains.append(max(change, 0))
            losses.append(max(-change, 0))
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for i in range(period):
            if avg_loss == 0:
                result.append(100)
            else:
                rs = avg_gain / avg_loss
                result.append(100 - 100 / (1 + rs))
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            if avg_loss == 0:
                result.append(100)
            else:
                rs = avg_gain / avg_loss
                result.append(100 - 100 / (1 + rs))
        return result


class BollingerStrategy(BaseStrategy):
    """布林带策略 — 触及下轨买入，触及上轨卖出"""

    name = 'Bollinger Bands'
    description = '触及布林下轨买入，触及上轨卖出'

    def __init__(self, params=None):
        super().__init__(params)
        self.period = self.params.get('period', 20)
        self.num_std = self.params.get('num_std', 2.0)

    def generate_signals(self, df):
        closes = df['Close'].values
        signals = [Signal.HOLD] * len(closes)

        for i in range(self.period, len(closes)):
            window = closes[i - self.period:i + 1]
            mean = sum(window) / len(window)
            variance = sum((x - mean) ** 2 for x in window) / len(window)
            std = math.sqrt(variance)
            upper = mean + self.num_std * std
            lower = mean - self.num_std * std

            # 收盘价触下轨买入
            if closes[i] <= lower and i > 0:
                prev_window = closes[i - self.period:i]
                if len(prev_window) == self.period:
                    prev_mean = sum(prev_window) / len(prev_window)
                    prev_var = sum((x - prev_mean) ** 2 for x in prev_window) / len(prev_window)
                    prev_std = math.sqrt(prev_var)
                    prev_lower = prev_mean - self.num_std * prev_std
                    if closes[i-1] > prev_lower:
                        signals[i] = Signal.BUY

            # 收盘价触上轨卖出
            if closes[i] >= upper and i > 0:
                prev_window = closes[i - self.period:i]
                if len(prev_window) == self.period:
                    prev_mean = sum(prev_window) / len(prev_window)
                    prev_var = sum((x - prev_mean) ** 2 for x in prev_window) / len(prev_window)
                    prev_std = math.sqrt(prev_var)
                    prev_upper = prev_mean + self.num_std * prev_std
                    if closes[i-1] < prev_upper:
                        signals[i] = Signal.SELL

        return signals


class VolumeBreakoutStrategy(BaseStrategy):
    """
    成交量突破策略 — 量比 + 價格方向 + Vol MA 交叉

    买入訊號:
      - 量比 > 1.8 且收盤價 > 開盤價 (放量上漲)
      - 或 Vol MA5 上穿 Vol MA20 (量能啟動)
    賣出訊號:
      - 量比 > 2.0 且收盤價 < 開盤價 (放量下跌)
      - 或 Vol MA5 下穿 Vol MA20 (量能萎縮)
    """

    name = 'Volume Breakout'
    description = '量比突破策略，放量上漲買入/放量下跌賣出，Vol MA交叉確認'

    def __init__(self, params=None):
        super().__init__(params)
        self.vol_ratio_buy = self.params.get('vol_ratio_buy', 1.8)
        self.vol_ratio_sell = self.params.get('vol_ratio_sell', 2.0)
        self.vol_ma_short = self.params.get('vol_ma_short', 5)
        self.vol_ma_long = self.params.get('vol_ma_long', 20)

    def generate_signals(self, df):
        closes = df['Close'].values
        opens = df['Open'].values
        volumes = df['Volume'].values
        n = len(closes)
        signals = [Signal.HOLD] * n

        long_ma = max(self.vol_ma_short, self.vol_ma_long)

        # 預計算日均量
        vol_ma_short = [None] * (self.vol_ma_short - 1)
        vol_ma_long = [None] * (self.vol_ma_long - 1)
        for i in range(n):
            if i >= self.vol_ma_short - 1:
                vol_ma_short.append(sum(volumes[i - self.vol_ma_short + 1:i + 1]) / self.vol_ma_short)
            else:
                vol_ma_short.append(None)
            if i >= self.vol_ma_long - 1:
                vol_ma_long.append(sum(volumes[i - self.vol_ma_long + 1:i + 1]) / self.vol_ma_long)
            else:
                vol_ma_long.append(None)

        for i in range(long_ma, n):
            avg_vol_20 = vol_ma_long[i]
            if avg_vol_20 is None or avg_vol_20 == 0:
                continue

            vol_ratio = volumes[i] / avg_vol_20
            price_up = closes[i] > opens[i]  # 收陽
            price_down = closes[i] < opens[i]  # 收陰

            # Vol MA 交叉
            vm_short = vol_ma_short[i]
            vm_long = vol_ma_long[i]
            vm_short_prev = vol_ma_short[i - 1] if i > 0 else None
            vm_long_prev = vol_ma_long[i - 1] if i > 0 else None
            vol_golden = (vm_short_prev and vm_long_prev and
                         vm_short_prev <= vm_long_prev and vm_short > vm_long)
            vol_dead = (vm_short_prev and vm_long_prev and
                       vm_short_prev >= vm_long_prev and vm_short < vm_long)

            # 買入訊號：放量上漲 或 Vol 金叉 + 價格確認
            if vol_ratio >= self.vol_ratio_buy and price_up:
                signals[i] = Signal.BUY
            elif vol_golden and price_up:
                signals[i] = Signal.BUY

            # 賣出訊號：放量下跌 或 Vol 死叉 + 價格確認
            elif vol_ratio >= self.vol_ratio_sell and price_down:
                signals[i] = Signal.SELL
            elif vol_dead and price_down:
                signals[i] = Signal.SELL

        return signals



class CompositeStrategy(BaseStrategy):
    """
    综合评分策略 — 复用 Paper Trading 的技术面+基本面评分逻辑
    信号: 综合评分 >= 75 → BUY, <= 30 → SELL
    """

    name = 'Composite Score'
    description = '技术面+基本面综合评分，>=75买入，<=30卖出'

    def __init__(self, params=None):
        super().__init__(params)
        self.buy_threshold = self.params.get('buy_threshold', 75)
        self.sell_threshold = self.params.get('sell_threshold', 30)
        self.tech_weight = self.params.get('tech_weight', 0.65)

    def generate_signals(self, df):
        """基于技术指标的综合评分 (纯技术面，不依赖 API)"""
        closes = df['Close'].values
        highs = df['High'].values
        lows = df['Low'].values
        volumes = df['Volume'].values
        n = len(closes)
        signals = [Signal.HOLD] * n

        for i in range(60, n):  # 需要足够历史数据
            tech_score = self._calc_tech_score(closes, highs, lows, volumes, i)
            composite = tech_score  # 纯回测不调基本面 API，100% 技术面

            if composite >= self.buy_threshold:
                signals[i] = Signal.BUY
            elif composite <= self.sell_threshold:
                signals[i] = Signal.SELL

        return signals

    def _calc_tech_score(self, closes, highs, lows, volumes, idx):
        """简化版技术评分 (0-100)"""
        score = 50  # 中性基准

        # 趋势 (30分): 收盘价 vs SMA20 vs SMA60
        window20 = closes[idx-20:idx]
        window60 = closes[idx-60:idx]
        sma20 = sum(window20) / 20
        sma60 = sum(window60) / 60
        price = closes[idx]

        if price > sma20 > sma60:
            score += 20  # 强上升趋势
        elif price > sma20:
            score += 12  # 中等上升
        elif price < sma20 < sma60:
            score -= 20  # 强下降
        elif price < sma20:
            score -= 12

        # 动量 (25分): 5日涨跌幅
        if idx >= 5:
            momentum = (price - closes[idx-5]) / closes[idx-5]
            score += max(min(momentum * 200, 20), -20)

        # RSI (20分)
        rsi = self._quick_rsi(closes, idx, 14)
        if rsi is not None:
            if rsi < 30:
                score += 15  # 超卖 = 机会
            elif rsi > 70:
                score -= 15  # 超买 = 风险
            elif 40 <= rsi <= 60:
                score += 5  # 中性偏好

        # 量价 (25分): 量比 + Vol MA 交叉 + 量价背离
        vol_score = 0
        price_change = (price - closes[idx-1]) / max(closes[idx-1], 0.01) if idx >= 1 else 0
        if idx >= 20:
            avg_vol_20 = sum(volumes[idx-20:idx]) / 20
            vol_ratio = volumes[idx] / avg_vol_20 if avg_vol_20 > 0 else 1

            # 量比评分 (10分)
            if vol_ratio >= 2.0 and price_change > 0:
                vol_score = 10  # 放量大涨 = 强买讯
            elif vol_ratio >= 1.5 and price_change > 0:
                vol_score = 7   # 温和放量上涨
            elif vol_ratio < 0.5:
                vol_score = 4   # 极度缩量
            elif vol_ratio >= 1.0:
                vol_score = 5   # 正常成交量
            else:
                vol_score = 3   # 低于均量

            # Vol MA5 vs Vol MA20 交叉 (8分)
            avg_vol_5 = sum(volumes[idx-5:idx]) / 5
            if idx >= 21:
                avg_vol_5_prev = sum(volumes[idx-6:idx-1]) / 5
                avg_vol_20_prev = sum(volumes[idx-21:idx-1]) / 20
                if avg_vol_5_prev <= avg_vol_20_prev and avg_vol_5 > avg_vol_20:
                    vol_score += 8  # Vol 金叉
                elif avg_vol_5_prev >= avg_vol_20_prev and avg_vol_5 < avg_vol_20:
                    vol_score -= 5  # Vol 死叉

            # 量价背离 (7分)
            if idx >= 5:
                price_chg_5d = (closes[idx] - closes[idx-5]) / closes[idx-5]
                vol_chg_5d = (volumes[idx] - volumes[idx-5]) / max(volumes[idx-5], 1)
                if price_chg_5d > 0.02 and vol_chg_5d < -0.2:
                    vol_score -= 7  # 价涨量缩 = 背离警告
                elif price_chg_5d < -0.02 and vol_chg_5d < -0.3:
                    vol_score += 5   # 价跌量缩 = 可能见底
        elif idx >= 1:
            vol_change = (volumes[idx] - volumes[idx-1]) / max(volumes[idx-1], 1)
            if vol_change > 0.3 and price_change > 0:
                vol_score = 15
            elif vol_change > 0.3 and price_change < 0:
                vol_score = -5

        return max(0, min(100, score))

    @staticmethod
    def _quick_rsi(closes, idx, period):
        if idx < period:
            return None
        gains, losses = [], []
        for j in range(idx - period + 1, idx + 1):
            change = closes[j] - closes[j-1]
            gains.append(max(change, 0))
            losses.append(max(-change, 0))
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - 100 / (1 + rs)


# 策略注册表
STRATEGIES = {
    'ema_cross': EMACrossStrategy,
    'macd': MACDStrategy,
    'rsi': RSIStrategy,
    'bollinger': BollingerStrategy,
    'volume_breakout': VolumeBreakoutStrategy,
    'composite': CompositeStrategy,
}


# ═══════════════════════════════════════════
#  BacktestEngine — 回测引擎
# ═══════════════════════════════════════════

class BacktestEngine:
    """
    核心回测引擎

    工作流:
    1. 接收 K线 DataFrame + 策略
    2. 逐 bar 生成信号 → 模拟交易
    3. 计算绩效指标 + 净值曲线 + 交易记录
    """

    def __init__(self, initial_cash=1000000, commission_rate=0.001,
                 stamp_duty_rate=0.0013, slippage=0.001):
        """
        Args:
            initial_cash: 初始资金 (HKD)
            commission_rate: 佣金费率 (默认 0.1%)
            stamp_duty_rate: 印花税 (默认 0.13%)
            slippage: 滑点 (默认 0.1%)
        """
        self.initial_cash = initial_cash
        self.commission_rate = commission_rate
        self.stamp_duty_rate = stamp_duty_rate
        self.slippage = slippage

    def run(self, df, strategy, strategy_params=None):
        """
        执行回测

        Args:
            df: pd.DataFrame — K线数据 (需含 Open, High, Low, Close, Volume)
            strategy: str — 策略名 (ema_cross/macd/rsi/bollinger/composite)
            strategy_params: dict — 策略参数
        Returns:
            dict — 完整回测结果
        """
        if df is None or len(df) < 30:
            return self._error_result('K线数据不足 (至少需要30个交易日)')

        # 确保按时间升序排列 (富途 get_cur_kline 默认倒序)
        df = df.sort_index(ascending=True).copy()

        # 实例化策略
        StrategyClass = STRATEGIES.get(strategy)
        if not StrategyClass:
            return self._error_result(f'未知策略: {strategy}')

        # 确保 Close 列为 float 且无 NaN (pandas 2.x 兼容写法)
        closes = pd.to_numeric(df['Close'], errors='coerce')
        closes = closes.ffill().bfill()
        df = df.copy()
        df['Close'] = closes

        strat = StrategyClass(params=strategy_params)
        signals = strat.generate_signals(df)

        # 逐 bar 模拟
        cash = float(self.initial_cash)
        position = 0  # 持仓股数
        trades = []   # 交易记录
        equity_curve = []  # 每日净值
        daily_returns_list = []

        dates = [str(d.date()) if hasattr(d, 'date') else str(d) for d in df.index]

        for i in range(len(df)):
            price = float(df['Close'].values[i])
            if not price or price <= 0 or math.isnan(price):
                equity_curve.append({
                    'date': dates[i], 'equity': cash, 'cash': cash,
                    'position_value': 0, 'position_shares': position,
                })
                continue
            signal = signals[i]
            date = dates[i]

            # 执行交易
            if signal == Signal.BUY and position == 0 and cash > 0:
                # 买入 (全仓)
                buy_price = price * (1 + self.slippage)
                # 预留手续费空间 (commission 0.1% + stamp 0.13% + buffer)
                fee_rate = self.commission_rate + self.stamp_duty_rate
                available_for_shares = cash / (1 + fee_rate + 0.002)  # 多留 0.2% buffer
                shares = int(available_for_shares / (buy_price * 100)) * 100  # 港股按手 (100股)
                if shares > 0:
                    cost = shares * buy_price
                    commission = max(cost * self.commission_rate, 50)  # 最低 HKD50
                    stamp = cost * self.stamp_duty_rate
                    total_cost = cost + commission + stamp
                    if total_cost <= cash:
                        cash -= total_cost
                        position = shares
                        trades.append({
                            'date': date,
                            'action': 'BUY',
                            'price': round(buy_price, 3),
                            'shares': shares,
                            'commission': round(commission, 2),
                            'stamp_duty': round(stamp, 2),
                            'reason': f'{strat.name} 买入信号',
                        })

            elif signal == Signal.SELL and position > 0:
                # 卖出 (清仓)
                sell_price = price * (1 - self.slippage)
                revenue = position * sell_price
                commission = max(revenue * self.commission_rate, 50)
                stamp = revenue * self.stamp_duty_rate
                net_revenue = revenue - commission - stamp
                cash += net_revenue
                pnl = net_revenue - (trades[-1]['shares'] * trades[-1]['price'] +
                                      trades[-1]['commission'] + trades[-1]['stamp_duty']) if trades else 0
                trades.append({
                    'date': date,
                    'action': 'SELL',
                    'price': round(sell_price, 3),
                    'shares': position,
                    'commission': round(commission, 2),
                    'stamp_duty': round(stamp, 2),
                    'pnl': round(pnl, 2),
                    'reason': f'{strat.name} 卖出信号',
                })
                position = 0

            # 记录净值
            equity = cash + position * price
            equity_curve.append({
                'date': date,
                'equity': round(equity, 2),
                'cash': round(cash, 2),
                'position_value': round(position * price, 2),
                'position_shares': position,
            })

        # 计算每日收益率
        for i in range(1, len(equity_curve)):
            prev_eq = equity_curve[i-1]['equity']
            curr_eq = equity_curve[i]['equity']
            if prev_eq > 0:
                daily_returns_list.append((curr_eq - prev_eq) / prev_eq)

        # 绩效指标
        metrics = PerformanceMetrics.calc_all(daily_returns_list)

        # 交易统计 — 全仓模式，BUY/SELL 严格交替，顺序配对
        completed_trades = []
        pending_buy = None
        for t in trades:
            if t['action'] == 'BUY':
                pending_buy = t
            elif t['action'] == 'SELL' and pending_buy is not None:
                bt = pending_buy
                st = t
                total_cost = bt['shares'] * bt['price'] + bt['commission'] + bt['stamp_duty']
                total_revenue = st['shares'] * st['price'] - st['commission'] - st['stamp_duty']
                # 计算持仓天数
                try:
                    d_buy = datetime.strptime(bt['date'], '%Y-%m-%d')
                    d_sell = datetime.strptime(st['date'], '%Y-%m-%d')
                    holding_days = (d_sell - d_buy).days
                except:
                    holding_days = 0
                completed_trades.append({
                    'buy_date': bt['date'],
                    'sell_date': st['date'],
                    'buy_price': bt['price'],
                    'sell_price': st['price'],
                    'shares': bt['shares'],
                    'pnl': round(total_revenue - total_cost, 2),
                    'pnl_pct': round((total_revenue - total_cost) / total_cost * 100, 2),
                    'holding_days': holding_days,
                })
                pending_buy = None

        win_trades = [t for t in completed_trades if t['pnl'] > 0]
        loss_trades = [t for t in completed_trades if t['pnl'] <= 0]

        final_equity = equity_curve[-1]['equity'] if equity_curve else self.initial_cash

        return {
            'success': True,
            'strategy': strat.name,
            'strategy_key': strategy,
            'strategy_params': strategy_params,
            'description': strat.description,
            'period': {
                'start': dates[0] if dates else None,
                'end': dates[-1] if dates else None,
                'trading_days': len(dates),
            },
            'capital': {
                'initial': self.initial_cash,
                'final': round(final_equity, 2),
                'total_pnl': round(final_equity - self.initial_cash, 2),
                'total_pnl_pct': round((final_equity - self.initial_cash) / self.initial_cash * 100, 2),
            },
            'metrics': metrics,
            'trade_stats': {
                'total_trades': len(completed_trades),
                'win_trades': len(win_trades),
                'loss_trades': len(loss_trades),
                'trade_win_rate': round(len(win_trades) / len(completed_trades) * 100, 1) if completed_trades else 0,
                'avg_pnl_pct': round(
                    sum(t['pnl_pct'] for t in completed_trades) / len(completed_trades), 2
                ) if completed_trades else 0,
            },
            'equity_curve': equity_curve,
            'trades': completed_trades,
            'all_signals': [
                {'date': dates[i], 'signal': signals[i], 'price': round(float(df['Close'].values[i]), 3)}
                for i in range(len(dates)) if signals[i] != Signal.HOLD
            ],
        }

    def run_multi(self, df, strategies=None, strategy_params=None):
        """
        多策略对比回测

        Args:
            df: K线数据
            strategies: list[str] — 策略列表，默认全部
            strategy_params: dict — 统一参数
        Returns:
            dict — 各策略结果 + 排名
        """
        if strategies is None:
            strategies = list(STRATEGIES.keys())

        results = []
        for s in strategies:
            r = self.run(df, s, strategy_params)
            if r.get('success'):
                results.append(r)

        # 按夏普比率排名
        results.sort(key=lambda x: x['metrics'].get('sharpe_ratio') or -999, reverse=True)

        return {
            'success': True,
            'count': len(results),
            'rankings': [
                {
                    'rank': i + 1,
                    'strategy': r['strategy'],
                    'annual_return': r['metrics'].get('annual_return'),
                    'sharpe_ratio': r['metrics'].get('sharpe_ratio'),
                    'max_drawdown': r['metrics'].get('max_drawdown'),
                    'win_rate': r['metrics'].get('win_rate'),
                    'total_pnl_pct': r['capital']['total_pnl_pct'],
                    'total_trades': r['trade_stats']['total_trades'],
                }
                for i, r in enumerate(results)
            ],
            'details': results,
        }

    def walk_forward(self, df, strategy, strategy_params=None,
                     train_pct=0.7, n_splits=3):
        """
        Walk-Forward 验证 — 防过拟合

        将数据分成多段，每段用前 train_pct 训练(找参数)、后 (1-train_pct) 验证(测试绩效)
        简化版: 固定参数，滚动验证

        Args:
            df: K线数据
            strategy: 策略名
            strategy_params: 策略参数
            train_pct: 训练集比例
            n_splits: 分割数
        Returns:
            dict — 各折结果 + 平均绩效
        """
        # 确保按时间升序排列 (防御性，walk_forward 依赖 iloc 切片)
        df = df.sort_index(ascending=True)
        n = len(df)
        fold_size = n // n_splits
        folds = []

        for i in range(n_splits):
            start = i * fold_size
            end = min(start + fold_size, n)
            fold_df = df.iloc[start:end]

            if len(fold_df) < 30:
                continue

            result = self.run(fold_df, strategy, strategy_params)
            if result.get('success'):
                folds.append(result)

        if not folds:
            return self._error_result('数据不足以进行 Walk-Forward 验证')

        # 计算平均指标
        avg_metrics = {}
        metric_keys = ['annual_return', 'sharpe_ratio', 'max_drawdown',
                       'win_rate', 'total_return']
        for key in metric_keys:
            values = [f['metrics'].get(key) for f in folds if f['metrics'].get(key) is not None]
            if values:
                avg_metrics[f'avg_{key}'] = round(sum(values) / len(values), 2)

        return {
            'success': True,
            'strategy': strategy,
            'n_splits': len(folds),
            'avg_metrics': avg_metrics,
            'fold_details': [
                {
                    'fold': i + 1,
                    'period': f['period'],
                    'annual_return': f['metrics'].get('annual_return'),
                    'sharpe_ratio': f['metrics'].get('sharpe_ratio'),
                    'max_drawdown': f['metrics'].get('max_drawdown'),
                    'total_trades': f['trade_stats'].get('total_trades'),
                }
                for i, f in enumerate(folds)
            ],
        }

    def _error_result(self, msg):
        return {'success': False, 'error': msg}


# ═══════════════════════════════════════════
#  便捷入口
# ═══════════════════════════════════════════

def get_available_strategies():
    """获取所有可用策略列表"""
    return [
        {'key': k, 'name': v.name, 'description': v.description}
        for k, v in STRATEGIES.items()
    ]
