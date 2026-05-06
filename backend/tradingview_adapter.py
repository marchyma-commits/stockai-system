"""
TradingView MCP 技术指标适配器
使用 TradingView MCP Server 内置的专业级算法

数据来源：
- K线数据：富途 OpenD
- 技术指标：TradingView MCP indicators_calc.py (官方算法)
"""

try:
    from futu import OpenQuoteContext, RET_OK
    FUTU_AVAILABLE = True
except ImportError:
    FUTU_AVAILABLE = False
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# 导入 TradingView MCP 的专业指标算法
try:
    from tradingview_mcp.core.services.indicators_calc import (
        calc_ema, calc_sma, calc_rsi, calc_bollinger,
        calc_macd, calc_atr, calc_supertrend, calc_donchian
    )
    TV_INDICATORS_AVAILABLE = True
except ImportError:
    TV_INDICATORS_AVAILABLE = False
    logger.warning("TradingView MCP indicators_calc 未安装，将使用备用算法")

# 导入 TradingView MCP 高级分析函数（交易设置 + 质量评分）
try:
    from tradingview_mcp.core.services.indicators import (
        compute_trade_setup, compute_trade_quality, compute_stock_score,
        extract_extended_indicators, analyze_timeframe_context,
        compute_fibonacci_levels, detect_trend_for_fibonacci,
        analyze_fibonacci_position
    )
    TV_ADVANCED_AVAILABLE = True
except ImportError:
    TV_ADVANCED_AVAILABLE = False
    logger.warning("TradingView MCP indicators (advanced) 未安装")


class TradingViewIndicators:
    """
    使用 TradingView MCP 官方算法的技术指标计算器
    """

    def __init__(self):
        self.tv_available = TV_INDICATORS_AVAILABLE
        if self.tv_available:
            logger.info("✅ TradingView MCP 指标算法已加载")
        else:
            logger.warning("⚠️ 使用备用指标算法")

    def calculate_all(self, ohlc: pd.DataFrame) -> Dict[str, Any]:
        """
        计算所有技术指标

        Args:
            ohlc: DataFrame with columns [time, open, high, low, close, volume]

        Returns:
            技术指标字典
        """
        if len(ohlc) < 5:
            raise ValueError("需要至少5条K线数据")

        # 转换为列表格式（TradingView 算法需要）
        closes = ohlc['close'].tolist()
        highs = ohlc['high'].tolist()
        lows = ohlc['low'].tolist()
        volumes = ohlc['volume'].tolist()

        indicators = {}

        # === 趋势指标 ===
        # MA
        for period in [5, 10, 20, 30, 60, 200]:
            if len(closes) >= period:
                if self.tv_available:
                    ma_values = calc_sma(closes, period)
                    indicators[f'ma_{period}'] = self._last_valid(ma_values)
                else:
                    indicators[f'ma_{period}'] = self._pandas_ma(closes, period)

        # EMA（包含 TV MCP compute_trade_quality 所需的 EMA20/EMA50/EMA60）
        for period in [12, 20, 26, 50, 60, 200]:
            if len(closes) >= period:
                if self.tv_available:
                    ema_values = calc_ema(closes, period)
                    indicators[f'ema_{period}'] = self._last_valid(ema_values)
                else:
                    indicators[f'ema_{period}'] = self._pandas_ema(closes, period)

        # === MACD ===
        if len(closes) >= 35:
            if self.tv_available:
                macd_data = calc_macd(closes, fast=12, slow=26, signal=9)
                indicators['macd'] = self._last_valid(macd_data['macd'])
                indicators['macd_signal'] = self._last_valid(macd_data['signal'])
                indicators['macd_histogram'] = self._last_valid(macd_data['histogram'])
            else:
                self._pandas_macd(closes, indicators)

        # === RSI ===
        for period in [6, 12, 24]:
            if len(closes) >= period + 1:
                if self.tv_available:
                    rsi_values = calc_rsi(closes, period)
                    indicators[f'rsi_{period}'] = self._last_valid(rsi_values)
                else:
                    indicators[f'rsi_{period}'] = self._pandas_rsi(closes, period)

        # === 布林带 ===
        if len(closes) >= 20:
            if self.tv_available:
                bb_data = calc_bollinger(closes, period=20, std_mult=2.0)
                indicators['bb_upper'] = self._last_valid(bb_data['upper'])
                indicators['bb_middle'] = self._last_valid(bb_data['middle'])
                indicators['bb_lower'] = self._last_valid(bb_data['lower'])
            else:
                self._pandas_bollinger(closes, indicators)

        # === ATR ===
        if len(closes) >= 15:
            if self.tv_available:
                atr_values = calc_atr(highs, lows, closes, period=14)
                indicators['atr'] = self._last_valid(atr_values)
            else:
                indicators['atr'] = self._pandas_atr(highs, lows, closes)

        # === ADX / +DI / -DI（14期，供交易质量评分使用）===
        if len(closes) >= 28:
            adx_result = self._calc_adx(highs, lows, closes, period=14)
            if isinstance(adx_result, dict):
                indicators['adx'] = adx_result.get('adx')
                indicators['plus_di'] = adx_result.get('plus_di')
                indicators['minus_di'] = adx_result.get('minus_di')
            else:
                indicators['adx'] = adx_result

        # === Supertrend ===
        if len(closes) >= 12:
            if self.tv_available:
                st_data = calc_supertrend(highs, lows, closes, atr_period=10, multiplier=3.0)
                indicators['supertrend'] = self._last_valid(st_data['direction'])
                indicators['supertrend_upper'] = self._last_valid(st_data['upper'])
                indicators['supertrend_lower'] = self._last_valid(st_data['lower'])
            else:
                indicators['supertrend'] = 0

        # === KDJ (无 TradingView 版本，使用 pandas) ===
        self._kdj(highs, lows, closes, indicators)

        # === Williams %R ===
        self._williams_r(highs, lows, closes, indicators)

        # === CCI ===
        self._cci(highs, lows, closes, indicators)

        # === ROC ===
        self._roc(closes, indicators)

        # === 标准差 ===
        self._std_dev(closes, indicators)

        # === 成交量指标 ===
        self._volume_indicators(volumes, closes, indicators)

        # === Pivot Point ===
        self._pivot_point(highs, lows, closes, indicators)

        # === 最新 OHLCV（供 to_tv_format 使用）===
        indicators['close'] = float(closes[-1])
        indicators['open'] = float(ohlc['open'].iloc[-1])
        indicators['high'] = float(highs[-1])
        indicators['low'] = float(lows[-1])
        indicators['volume'] = float(volumes[-1])

        # === 标准化 NaN ===
        indicators = {k: (v if v is not None and not np.isnan(v) else None)
                      for k, v in indicators.items()}

        return indicators

    def _last_valid(self, values: List) -> Optional[float]:
        """获取最后一个有效值"""
        for v in reversed(values):
            if v is not None and not np.isnan(v):
                return float(v)
        return None

    # === 备用算法（当 TradingView MCP 不可用时） ===

    def _pandas_ma(self, closes: List[float], period: int) -> Optional[float]:
        if len(closes) < period:
            return None
        return float(np.mean(closes[-period:]))

    def _pandas_ema(self, closes: List[float], period: int) -> Optional[float]:
        if len(closes) < period:
            return None
        series = pd.Series(closes)
        return float(series.ewm(span=period, adjust=False).mean().iloc[-1])

    def _pandas_rsi(self, closes: List[float], period: int = 14) -> Optional[float]:
        if len(closes) < period + 1:
            return None
        deltas = pd.Series(closes).diff()
        gains = deltas.clip(lower=0).rolling(window=period).mean()
        losses = (-deltas.clip(upper=0)).rolling(window=period).mean()
        rs = gains / losses
        return float(100 - (100 / (1 + rs)).iloc[-1])

    def _pandas_macd(self, closes: List[float], indicators: Dict):
        ema12 = pd.Series(closes).ewm(span=12, adjust=False).mean()
        ema26 = pd.Series(closes).ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        indicators['macd'] = float(macd.iloc[-1])
        indicators['macd_signal'] = float(signal.iloc[-1])
        indicators['macd_histogram'] = float((macd - signal).iloc[-1])

    def _pandas_bollinger(self, closes: List[float], indicators: Dict, period: int = 20):
        series = pd.Series(closes)
        ma = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        indicators['bb_upper'] = float((ma + 2 * std).iloc[-1])
        indicators['bb_middle'] = float(ma.iloc[-1])
        indicators['bb_lower'] = float((ma - 2 * std).iloc[-1])

    def _pandas_atr(self, highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Optional[float]:
        if len(closes) < period + 1:
            return None
        high = pd.Series(highs)
        low = pd.Series(lows)
        close = pd.Series(closes)
        tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
        return float(tr.rolling(window=period).mean().iloc[-1])

    def _kdj(self, highs: List[float], lows: List[float], closes: List[float], indicators: Dict, period: int = 9):
        low_n = pd.Series(lows).rolling(window=period).min()
        high_n = pd.Series(highs).rolling(window=period).max()
        rsv = (pd.Series(closes) - low_n) / (high_n - low_n).replace(0, np.nan) * 100
        k = rsv.ewm(com=2, adjust=False).mean()
        d = k.ewm(com=2, adjust=False).mean()
        j = 3 * k - 2 * d
        indicators['kdj_k'] = float(k.iloc[-1])
        indicators['kdj_d'] = float(d.iloc[-1])
        indicators['kdj_j'] = float(j.iloc[-1])

    def _williams_r(self, highs: List[float], lows: List[float], closes: List[float], indicators: Dict, period: int = 14):
        high_n = pd.Series(highs).rolling(window=period).max()
        low_n = pd.Series(lows).rolling(window=period).min()
        wr = -100 * (high_n - pd.Series(closes)) / (high_n - low_n).replace(0, np.nan)
        indicators['williams_r'] = float(wr.iloc[-1])

    def _cci(self, highs: List[float], lows: List[float], closes: List[float], indicators: Dict, period: int = 14):
        tp = (pd.Series(highs) + pd.Series(lows) + pd.Series(closes)) / 3
        sma = tp.rolling(window=period).mean()
        mad = tp.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean())
        cci = (tp - sma) / (0.015 * mad)
        indicators['cci'] = float(cci.iloc[-1])

    def _roc(self, closes: List[float], indicators: Dict, period: int = 12):
        roc = pd.Series(closes).pct_change(periods=period) * 100
        indicators['roc'] = float(roc.iloc[-1])

    def _std_dev(self, closes: List[float], indicators: Dict, period: int = 20):
        if len(closes) >= period:
            indicators['std_dev'] = float(pd.Series(closes).rolling(window=period).std().iloc[-1])
        else:
            indicators['std_dev'] = None

    def _volume_indicators(self, volumes: List[float], closes: List[float], indicators: Dict):
        vol_series = pd.Series(volumes)
        close_series = pd.Series(closes)

        # 成交量移动平均
        for period in [5, 10, 20]:
            if len(volumes) >= period:
                indicators[f'vol_ma_{period}'] = float(vol_series.rolling(window=period).mean().iloc[-1])

        # OBV
        obv = (np.sign(close_series.diff()) * vol_series).cumsum()
        indicators['obv'] = float(obv.iloc[-1])

        # OBV 5日斜率（归一化，用于成交量确认判断）
        if len(closes) >= 6:
            obv_recent = obv.tail(5)
            if obv_recent.iloc[-1] != 0:
                obv_slope = (obv_recent.iloc[-1] - obv_recent.iloc[0]) / abs(obv_recent.iloc[-1])
                indicators['obv_slope_5'] = float(obv_slope)
            else:
                indicators['obv_slope_5'] = 0.0
        else:
            indicators['obv_slope_5'] = None

        # VR (Volume Ratio)
        if len(volumes) >= 26:
            up_vol = 0.0
            down_vol = 0.0
            equal_vol = 0.0
            for i in range(1, len(closes)):
                if closes[i] > closes[i-1]:
                    up_vol += volumes[i]
                elif closes[i] < closes[i-1]:
                    down_vol += volumes[i]
                else:
                    equal_vol += volumes[i]
            if down_vol + equal_vol * 0.5 > 0:
                vr = (up_vol + equal_vol * 0.5) / (down_vol + equal_vol * 0.5) * 100
                indicators['vr'] = float(vr)

    def _calc_adx(self, highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Optional[float]:
        """计算 ADX (Average Directional Index)，使用 Wilder 平滑法。"""
        try:
            import numpy as np
            h = np.array(highs, dtype=float)
            l = np.array(lows, dtype=float)
            c = np.array(closes, dtype=float)

            n = len(c)
            if n < 2 * period:
                return None

            # +DM / -DM
            up_move = h[1:] - h[:-1]
            down_move = l[:-1] - l[1:]
            plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
            minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

            # TR
            tr1 = h[1:] - l[1:]
            tr2 = np.abs(h[1:] - c[:-1])
            tr3 = np.abs(l[1:] - c[:-1])
            tr = np.maximum(tr1, np.maximum(tr2, tr3))

            # Wilder smoothing
            atr_arr = np.full(n - 1, np.nan)
            smooth_plus_dm = np.full(n - 1, np.nan)
            smooth_minus_dm = np.full(n - 1, np.nan)

            atr_arr[period - 1] = np.sum(tr[:period])
            smooth_plus_dm[period - 1] = np.sum(plus_dm[:period])
            smooth_minus_dm[period - 1] = np.sum(minus_dm[:period])

            for i in range(period, n - 1):
                atr_arr[i] = atr_arr[i - 1] - atr_arr[i - 1] / period + tr[i]
                smooth_plus_dm[i] = smooth_plus_dm[i - 1] - smooth_plus_dm[i - 1] / period + plus_dm[i]
                smooth_minus_dm[i] = smooth_minus_dm[i - 1] - smooth_minus_dm[i - 1] / period + minus_dm[i]

            # +DI / -DI
            plus_di = np.where(atr_arr > 0, 100 * smooth_plus_dm / atr_arr, 0.0)
            minus_di = np.where(atr_arr > 0, 100 * smooth_minus_dm / atr_arr, 0.0)

            # DX -> ADX
            di_sum = plus_di + minus_di
            dx = np.where(di_sum > 0, 100 * np.abs(plus_di - minus_di) / di_sum, 0.0)

            adx_arr = np.full(n - 1, np.nan)
            start = 2 * period - 2
            if start < n - 1:
                adx_arr[start] = np.mean(dx[period - 1:start + 1])
                for i in range(start + 1, n - 1):
                    adx_arr[i] = (adx_arr[i - 1] * (period - 1) + dx[i]) / period

            val = adx_arr[-1]
            adx_val = float(val) if not np.isnan(val) else None
            pdi_val = float(plus_di[-1]) if not np.isnan(plus_di[-1]) else None
            mdi_val = float(minus_di[-1]) if not np.isnan(minus_di[-1]) else None
            return {'adx': adx_val, 'plus_di': pdi_val, 'minus_di': mdi_val}
        except Exception:
            return {'adx': None, 'plus_di': None, 'minus_di': None}

    def _pivot_point(self, highs: List[float], lows: List[float], closes: List[float], indicators: Dict):
        if len(highs) < 1:
            return
        last_high = highs[-1]
        last_low = lows[-1]
        last_close = closes[-1]

        pivot = (last_high + last_low + last_close) / 3
        r1 = 2 * pivot - last_low
        s1 = 2 * pivot - last_high
        r2 = pivot + (last_high - last_low)
        s2 = pivot - (last_high - last_low)

        indicators['pivot'] = float(pivot)
        indicators['r1'] = float(r1)
        indicators['s1'] = float(s1)
        indicators['r2'] = float(r2)
        indicators['s2'] = float(s2)

    def to_tv_format(self, indicators: Dict, latest: Dict) -> Dict:
        """
        将内部指标字典映射为 TradingView MCP indicators.py 所需的格式。
        用于调用 compute_trade_setup / compute_trade_quality 等高级函数。
        """
        tv = {}
        # 价格
        tv['close'] = indicators.get('close', latest.get('close', 0))
        tv['open'] = indicators.get('open', latest.get('open', 0))
        tv['high'] = indicators.get('high', latest.get('high', 0))
        tv['low'] = indicators.get('low', latest.get('low', 0))
        tv['volume'] = indicators.get('volume', latest.get('volume', 0))

        # SMA
        for p in [10, 20, 30, 50, 100, 200]:
            v = indicators.get(f'ma_{p}')
            if v is not None:
                tv[f'SMA{p}'] = v
        # EMA
        for p in [9, 10, 20, 50, 60, 100, 200]:
            v = indicators.get(f'ema_{p}')
            if v is not None:
                tv[f'EMA{p}'] = v
        # MACD
        tv['MACD.macd'] = indicators.get('macd')
        tv['MACD.signal'] = indicators.get('macd_signal')
        # RSI
        tv['RSI'] = indicators.get('rsi_12')
        # ATR
        tv['ATR'] = indicators.get('atr')
        # Bollinger Bands
        tv['BB.upper'] = indicators.get('bb_upper')
        tv['BB.lower'] = indicators.get('bb_lower')
        tv['BB.middle'] = indicators.get('bb_middle')
        # Stochastic
        tv['Stoch.K'] = indicators.get('kdj_k')
        tv['Stoch.D'] = indicators.get('kdj_d')
        # CCI
        tv['CCI20'] = indicators.get('cci')
        # Williams %R
        tv['W.R'] = indicators.get('williams_r')
        # ADX
        tv['ADX'] = indicators.get('adx')
        tv['ADX+DI'] = indicators.get('plus_di')
        tv['ADX-DI'] = indicators.get('minus_di')
        # Volume
        tv['volume.SMA20'] = indicators.get('vol_ma_20')
        tv['volume.SMA5'] = indicators.get('vol_ma_5')
        tv['volume.SMA10'] = indicators.get('vol_ma_10')
        tv['OBV'] = indicators.get('obv')
        tv['VR'] = indicators.get('vr')
        # Parabolic SAR
        tv['P.SAR'] = None  # 我们系统暂无
        # Ichimoku
        tv['Ichimoku.BLine'] = None
        # Hull MA
        tv['HullMA9'] = None
        # VWMA
        tv['VWMA'] = None
        # Ultimate Oscillator
        tv['UO'] = None
        # Awesome Oscillator
        tv['AO'] = None
        # Momentum
        tv['Mom'] = indicators.get('roc')
        # Stochastic RSI
        tv['Stoch.RSI.K'] = None
        # Pivot Points
        tv['Pivot.M.Classic.Middle'] = indicators.get('pivot')
        tv['Pivot.M.Classic.R1'] = indicators.get('r1')
        tv['Pivot.M.Classic.R2'] = indicators.get('r2')
        tv['Pivot.M.Classic.S1'] = indicators.get('s1')
        tv['Pivot.M.Classic.S2'] = indicators.get('s2')
        # TradingView Recommendations (N/A)
        tv['Recommend.All'] = None
        tv['Recommend.MA'] = None
        tv['Recommend.Other'] = None

        return tv

    def compute_trade_setup_from_indicators(self, indicators: Dict, latest: Dict) -> Optional[Dict]:
        """
        基于已有指标计算交易设置（入场/止损/目标/支撑阻力）。
        调用 TradingView MCP compute_trade_setup()。
        """
        if not TV_ADVANCED_AVAILABLE:
            return None
        tv = self.to_tv_format(indicators, latest)
        try:
            return compute_trade_setup(tv)
        except Exception as e:
            logger.warning(f"compute_trade_setup 失败: {e}")
            return None

    def compute_trade_quality_from_indicators(self, indicators: Dict, latest: Dict,
                                                trade_setup: Dict) -> Optional[Dict]:
        """
        基于已有指标 + trade_setup 计算交易质量评分（100分制）。
        调用 TradingView MCP compute_trade_quality()。
        """
        if not TV_ADVANCED_AVAILABLE:
            return None
        tv = self.to_tv_format(indicators, latest)
        try:
            # stock_score 不直接使用 TV 版本，用简单估算
            stock_score = self._quick_stock_score(indicators, latest)
            return compute_trade_quality(tv, stock_score, trade_setup)
        except Exception as e:
            logger.warning(f"compute_trade_quality 失败: {e}")
            return None

    def _quick_stock_score(self, indicators: Dict, latest: Dict) -> int:
        """快速估算股票质量分（0-100），用于 compute_trade_quality 输入。"""
        close = latest.get('close', 0)
        if not close:
            return 50
        score = 50
        # EMA 趋势
        if indicators.get('ma_20') and close > indicators['ma_20']:
            score += 10
        if indicators.get('ma_60') and close > indicators['ma_60']:
            score += 10
        if indicators.get('ema_200') and close > indicators['ema_200']:
            score += 10
        # RSI
        rsi = indicators.get('rsi_12')
        if rsi and 40 <= rsi <= 65:
            score += 5
        elif rsi and rsi > 75:
            score -= 10
        # MACD
        if indicators.get('macd') and indicators.get('macd_signal'):
            if indicators['macd'] > indicators['macd_signal']:
                score += 10
            else:
                score -= 5
        return max(0, min(100, score))


    def compute_trade_quality_hk(self, indicators: Dict, latest: Dict,
                                  trade_setup: Dict) -> Dict:
        """
        港股专业版交易质量评分（100 分制）。

        基于 Ivan Krastins (TierOneTrading) 和 ICT (Inner Circle Trader) 的
        市场结构理论设计，结合 W.D. Gann 的支撑阻力框架。

        五维度评分：
        ┌─────────────────────┬──────┬────────────────────────────────────────┐
        │ 维度                │ 满分 │ 核心逻辑                               │
        ├─────────────────────┼──────┼────────────────────────────────────────┤
        │ 1. Structure Quality│  30  │ 多周期均线排列 + ADX趋势 + DI方向      │
        │ 2. Risk/Reward      │  30  │ 基于 Pivot/结构的盈亏比               │
        │ 3. Volume Confirm   │  20  │ 量比 + OBV趋势 + VR量能               │
        │ 4. Stop Quality     │  10  │ ATR适配 + 结构支撑保护                 │
        │ 5. Liquidity        │  10  │ 港股成交额（HKD）                     │
        └─────────────────────┴──────┴────────────────────────────────────────┘

        设计原则：
        - 大蓝筹横盘日不应得 0 分 — 中性结构也有合理底分
        - 成交量缩量不等于差 — 区分「缩量整理」和「缩量下跌」
        - 趋势评分用 +DI/-DI 而非单纯 EMA 排列（更精确）
        - 每个子维度独立打分，避免全有全无
        """
        if not trade_setup:
            return None

        tv = self.to_tv_format(indicators, latest)
        close = tv.get('close', 0)
        if not close or close <= 0:
            return None

        # ── 提取所有可用指标 ──────────────────────────────────
        ema20 = tv.get('EMA20')
        ema50 = tv.get('EMA50')
        ema60 = tv.get('EMA60')
        ema100 = tv.get('EMA100')
        ema200 = tv.get('EMA200')
        sma20 = tv.get('SMA20')
        adx = tv.get('ADX')
        plus_di = tv.get('ADX+DI')
        minus_di = tv.get('ADX-DI')
        atr = tv.get('ATR')
        rsi = tv.get('RSI')
        macd = tv.get('MACD.macd')
        macd_signal = tv.get('MACD.signal')
        volume = tv.get('volume', 0) or 0
        vol_sma5 = tv.get('volume.SMA5', 0) or 0
        vol_sma20 = tv.get('volume.SMA20', 0) or 0
        obv = tv.get('OBV')
        vr = tv.get('VR')
        bb_upper = tv.get('BB.upper')
        bb_middle = tv.get('BB.middle')
        bb_lower = tv.get('BB.lower')
        stoch_k = tv.get('Stoch.K')

        total = 0
        breakdown = {}
        notes = []

        # ════════════════════════════════════════════════════════
        # 1. Structure Quality — 30 pts
        # ════════════════════════════════════════════════════════
        # 子维度：A. 均线排列 (12) + B. ADX趋势强度 (8) + C. DI方向 (5) + D. 上方空间 (5)
        struct_pts = 0

        # ── A. 均线排列 (12 pts) ──────────────────────────────
        # 基于 Market Structure Theory:
        # - 多周期共振 > 单周期排列 > 中性 > 空头
        ma_pts = 0
        ma_bull_signals = 0
        ma_bear_signals = 0

        # 短期结构：close vs EMA20/SMA20
        if ema20 and sma20:
            if close > ema20 and close > sma20:
                ma_pts += 2
                ma_bull_signals += 1
            elif close < ema20 and close < sma20:
                ma_bear_signals += 1
        elif ema20:
            if close > ema20:
                ma_pts += 1
                ma_bull_signals += 1
            elif close < ema20:
                ma_bear_signals += 1

        # 中期结构：EMA20 vs EMA60（黄金/死亡交叉区域）
        if ema20 and ema60:
            if ema20 > ema60:
                ma_pts += 3
                ma_bull_signals += 1
            else:
                ma_bear_signals += 1

        # 中期结构：close vs EMA60
        if ema60:
            if close > ema60:
                ma_pts += 2
                ma_bull_signals += 1
            elif close < ema60:
                ma_bear_signals += 1

        # 长期结构：EMA60 vs EMA200（牛熊分界）
        if ema60 and ema200:
            if ema60 > ema200:
                ma_pts += 3
                ma_bull_signals += 1
            else:
                ma_bear_signals += 1

        # 长期结构：close vs EMA200
        if ema200:
            if close > ema200:
                ma_pts += 2
                ma_bull_signals += 1
            elif close < ema200:
                ma_bear_signals += 1

        # 多周期共振加分（3+ 周期看涨）
        if ma_bull_signals >= 4:
            ma_pts += 2  # 共振奖励
        if ma_bull_signals >= 5:
            ma_pts += 2  # 强共振

        # 中性基底分（均线无明确方向但非空头）
        if ma_bull_signals == 0 and ma_bear_signals == 0:
            ma_pts = 3  # 数据不足时给中性底分
        elif ma_bull_signals >= 2:
            ma_pts = max(ma_pts, 4)  # 至少2个看涨信号就有基础分
        elif ma_bear_signals >= 3 and ma_bull_signals == 0:
            ma_pts = max(0, ma_pts - 2)  # 空头扣分但不低于0

        ma_pts = max(0, min(12, ma_pts))
        struct_pts += ma_pts

        # 均线排列说明
        if ma_bull_signals >= 5:
            notes.append(f"多周期看涨 ({ma_bull_signals}/6)")
        elif ma_bull_signals >= 3:
            notes.append(f"中期偏强 ({ma_bull_signals}/6)")
        elif ma_bear_signals >= 4:
            notes.append(f"空头结构 ({ma_bear_signals}项看跌)")
        elif ma_bull_signals >= 2:
            notes.append(f"短期偏多 ({ma_bull_signals}/6)")
        else:
            notes.append("均线中性/无明确方向")

        # ── B. ADX 趋势强度 (8 pts) ─────────────────────────
        adx_pts = 0
        if adx is not None and adx > 0:
            # Wilder ADX 阈值 (专业标准)
            # < 20: 无趋势 / 盘整
            # 20-25: 趋势形成中
            # 25-50: 强趋势
            # 50-75: 极强趋势（少见）
            # > 75: 趋势可能过度延伸
            if 25 <= adx <= 50:
                adx_pts = 8
                notes.append(f"强趋势 ADX={adx:.0f}")
            elif 20 <= adx < 25:
                adx_pts = 5
                notes.append(f"趋势形成 ADX={adx:.0f}")
            elif 50 < adx <= 75:
                adx_pts = 7  # 极强但可能过热
                notes.append(f"极强趋势 ADX={adx:.0f}")
            elif adx > 75:
                adx_pts = 4  # 过度延伸，趋势衰竭风险
                notes.append(f"趋势过热 ADX={adx:.0f}")
            else:
                # ADX < 20: 盘整，但盘整不是坏事（横盘整理）
                adx_pts = 2
                notes.append(f"无明确趋势 ADX={adx:.0f}")
        else:
            adx_pts = 1  # 无数据时给最低分
        struct_pts += adx_pts

        # ── C. DI 方向性 (5 pts) ────────────────────────────
        # +DI > -DI = 多头主导, 反之空头
        di_pts = 0
        if plus_di is not None and minus_di is not None:
            di_diff = plus_di - minus_di
            di_sum_val = plus_di + minus_di
            # 方向性比率（避免绝对值偏差）
            if di_sum_val > 0:
                di_ratio = di_diff / di_sum_val  # -1 ~ +1
            else:
                di_ratio = 0

            if di_ratio > 0.3:
                di_pts = 5
                notes.append(f"多头主导 +DI{plus_di:.0f}>-DI{minus_di:.0f}")
            elif di_ratio > 0.1:
                di_pts = 3
                notes.append(f"偏多 +DI{plus_di:.0f}>-DI{minus_di:.0f}")
            elif di_ratio < -0.3:
                di_pts = 0  # 空头主导不加分
                notes.append(f"空头主导 -DI{minus_di:.0f}>+DI{plus_di:.0f}")
            elif di_ratio < -0.1:
                di_pts = 1
                notes.append(f"偏空 -DI{minus_di:.0f}>+DI{plus_di:.0f}")
            else:
                di_pts = 2  # 中性
                notes.append("多空均衡")
        else:
            di_pts = 1  # 无数据
        struct_pts += di_pts

        # ── D. 上方空间 (5 pts) ─────────────────────────────
        space_pts = 0
        resistances = trade_setup.get("resistances", [])
        supports = trade_setup.get("supports", [])
        if resistances and close:
            dist_to_r1 = ((resistances[0] - close) / close) * 100
            if dist_to_r1 > 5:
                space_pts = 5
                notes.append(f"空间充裕 (距R1 {dist_to_r1:.1f}%)")
            elif dist_to_r1 > 3:
                space_pts = 4
                notes.append(f"上方有空间 (距R1 {dist_to_r1:.1f}%)")
            elif dist_to_r1 > 1:
                space_pts = 2
                notes.append(f"接近阻力 (距R1 {dist_to_r1:.1f}%)")
            elif dist_to_r1 > 0:
                space_pts = 1
            # dist_to_r1 <= 0: 在阻力位上方，可能突破
            else:
                space_pts = 3
                notes.append("已突破R1，关注R2")
        elif not resistances:
            # 无阻力位数据，看支撑位距离判断波动空间
            if supports and close:
                support_dist = ((close - supports[0]) / close) * 100
                if support_dist > 3:
                    space_pts = 3
                    notes.append("无阻力数据，支撑保护充分")
                else:
                    space_pts = 1
            else:
                space_pts = 1  # 无结构数据
        struct_pts += space_pts

        breakdown["structure_quality"] = max(0, min(30, struct_pts))
        total += breakdown["structure_quality"]

        # ════════════════════════════════════════════════════════
        # 2. Risk/Reward — 30 pts（港股适配梯度）
        # ════════════════════════════════════════════════════════
        # 港股 R:R 特点：日波幅 1-3%，T1 目标通常 1-5%，止损 1-3%
        # 因此 R:R >= 1.0 已可接受，>= 2.0 是优秀
        rr_pts = 0
        rr2 = trade_setup.get("risk_reward", {}).get("to_target_2")
        if rr2 is not None:
            if rr2 >= 3.0:
                rr_pts = 30
                notes.append(f"卓越 R:R {rr2:.1f}")
            elif rr2 >= 2.0:
                rr_pts = 26
                notes.append(f"优秀 R:R {rr2:.1f}")
            elif rr2 >= 1.5:
                rr_pts = 20
                notes.append(f"良好 R:R {rr2:.1f}")
            elif rr2 >= 1.0:
                rr_pts = 14
                notes.append(f"可接受 R:R {rr2:.1f}")
            elif rr2 >= 0.7:
                rr_pts = 8
                notes.append(f"偏低 R:R {rr2:.1f}")
            elif rr2 >= 0.4:
                rr_pts = 4
                notes.append(f"弱势 R:R {rr2:.1f}")
            else:
                rr_pts = 1
                notes.append(f"极差 R:R {rr2:.1f}")
        else:
            rr_pts = 3  # 无数据给底分
        breakdown["risk_reward"] = rr_pts
        total += rr_pts

        # ════════════════════════════════════════════════════════
        # 3. Volume Confirmation — 20 pts
        # ════════════════════════════════════════════════════════
        # 子维度：A. 量比 (8) + B. OBV趋势 (7) + C. VR量能 (5)
        vol_pts = 0
        vol_notes = []

        # ── A. 量比 (8 pts) ─────────────────────────────────
        # 量比 = 当日成交量 / MA20成交量
        # 关键区分：缩量不一定差 — 需要结合价格方向
        vrb_pts = 0
        if volume and vol_sma20 and vol_sma20 > 0:
            ratio = volume / vol_sma20
            is_up_day = (tv.get('close', 0) or 0) >= (tv.get('open', 0) or 0)

            if ratio >= 2.0:
                vrb_pts = 8
                vol_notes.append(f"倍量{ratio:.1f}x")
            elif ratio >= 1.5:
                vrb_pts = 7
                vol_notes.append(f"放量{ratio:.1f}x")
            elif ratio >= 1.2:
                vrb_pts = 6
                vol_notes.append(f"温和放量{ratio:.1f}x")
            elif ratio >= 0.9:
                # 正常量 — 收阳给6分，收阴给4分
                vrb_pts = 6 if is_up_day else 4
                vol_notes.append("正常量")
            elif ratio >= 0.7:
                # 缩量 — 但如果是收阳缩量（缩量上涨）反而是好事
                if is_up_day:
                    vrb_pts = 5
                    vol_notes.append(f"缩量上涨{ratio:.1f}x（量价健康）")
                else:
                    vrb_pts = 3
                    vol_notes.append(f"缩量下跌{ratio:.1f}x")
            elif ratio >= 0.5:
                if is_up_day:
                    vrb_pts = 4
                    vol_notes.append(f"极度缩量上涨{ratio:.1f}x")
                else:
                    vrb_pts = 1
                    vol_notes.append(f"极度缩量{ratio:.1f}x")
            else:
                vrb_pts = 1
                vol_notes.append(f"地量{ratio:.1f}x")
        else:
            vrb_pts = 2  # 无成交量数据
        vol_pts += vrb_pts

        # ── B. OBV 趋势 (7 pts) ────────────────────────────
        # OBV (On Balance Volume) — 量能趋势的核心指标
        # 需要对比近期 OBV 走势与价格走势是否共振
        obv_pts = 0
        if obv is not None and indicators.get('obv_slope_5') is not None:
            obv_slope = indicators.get('obv_slope_5', 0)
            if obv_slope > 0.02:
                obv_pts = 7
                vol_notes.append("OBV上升（资金流入）")
            elif obv_slope > 0:
                obv_pts = 5
                vol_notes.append("OBV温和上升")
            elif obv_slope > -0.02:
                obv_pts = 3
                vol_notes.append("OBV平稳")
            else:
                obv_pts = 1
                vol_notes.append("OBV下降（资金流出）")
        elif obv is not None:
            # 没有 slope 数据，用简单判断
            # 如果 OBV > 0 说明历史上资金是净流入
            obv_pts = 3  # 中性
            vol_notes.append("OBV中性（无趋势数据）")
        else:
            obv_pts = 1
        vol_pts += obv_pts

        # ── C. VR 量能比 (5 pts) ────────────────────────────
        # VR (Volume Ratio) = 上涨日成交量 / 下跌日成交量 × 100
        # > 150: 过热, 80-150: 正常, < 80: 冷清
        vr_pts = 0
        if vr is not None:
            if 100 <= vr <= 150:
                vr_pts = 5
                vol_notes.append(f"VR{vr:.0f}（健康量能）")
            elif 80 <= vr < 100:
                vr_pts = 3
                vol_notes.append(f"VR{vr:.0f}（量能偏弱）")
            elif 150 < vr <= 250:
                vr_pts = 4
                vol_notes.append(f"VR{vr:.0f}（量能充沛）")
            elif vr > 250:
                vr_pts = 2
                vol_notes.append(f"VR{vr:.0f}（量能过热）")
            elif vr < 80:
                vr_pts = 2
                vol_notes.append(f"VR{vr:.0f}（量能萎缩）")
        else:
            vr_pts = 2  # 无数据
        vol_pts += vr_pts

        if vol_notes:
            notes.append(" | ".join(vol_notes))
        breakdown["volume_confirmation"] = max(0, min(20, vol_pts))
        total += breakdown["volume_confirmation"]

        # ════════════════════════════════════════════════════════
        # 4. Stop Placement Quality — 10 pts
        # ════════════════════════════════════════════════════════
        # 基于 ATR 的动态止损评估（Welles Wilder 方法）
        stop_pct = trade_setup.get("stop_distance_pct")
        stop_pts = 0
        if stop_pct is not None and atr and close > 0:
            supports = trade_setup.get("supports", [])
            atr_pct = (atr / close * 100)

            # 止损在结构支撑位下方（关键加分项）
            structural = False
            if supports:
                nearest_support = supports[0]
                support_dist = ((close - nearest_support) / close) * 100
                if stop_pct >= support_dist * 0.85:  # 止损接近或在支撑下方
                    structural = True

            # ATR 适配度 — 止损距离应与 ATR 匹配
            # 理想：1.0 ~ 2.0 ATR
            if atr_pct > 0:
                atr_ratio = stop_pct / atr_pct  # 止损是几倍 ATR
            else:
                atr_ratio = 0

            # 港股合理范围：1.0-3.5% (考虑100股一手)
            if 1.5 <= stop_pct <= 3.5 and structural and 1.0 <= atr_ratio <= 2.5:
                stop_pts = 10
                notes.append(f"优质止损 {stop_pct:.1f}%（{atr_ratio:.1f}ATR+支撑）")
            elif 1.5 <= stop_pct <= 3.5 and structural:
                stop_pts = 8
                notes.append(f"止损合理 {stop_pct:.1f}%（支撑保护）")
            elif 1.5 <= stop_pct <= 3.5 and 0.8 <= atr_ratio <= 3.0:
                stop_pts = 7
                notes.append(f"止损合理 {stop_pct:.1f}%（{atr_ratio:.1f}ATR）")
            elif 1.0 <= stop_pct < 1.5:
                stop_pts = 4
                notes.append(f"止损偏紧 {stop_pct:.1f}%（{atr_ratio:.1f}ATR）")
            elif 3.5 < stop_pct <= 5.0:
                stop_pts = 5
                notes.append(f"止损偏宽 {stop_pct:.1f}%（{atr_ratio:.1f}ATR）")
            elif stop_pct > 5.0:
                stop_pts = 2
                notes.append(f"止损过宽 {stop_pct:.1f}%")
            elif stop_pct < 1.0:
                stop_pts = 2
                notes.append(f"止损过紧 {stop_pct:.1f}%（易震出）")
            else:
                stop_pts = 3
                notes.append(f"止损一般 {stop_pct:.1f}%")
        else:
            stop_pts = 2  # 无数据
        breakdown["stop_quality"] = stop_pts
        total += stop_pts

        # ════════════════════════════════════════════════════════
        # 5. Liquidity — 10 pts（港股用成交额 HKD 衡量）
        # ════════════════════════════════════════════════════════
        # 港股流动性分级：
        # 大蓝筹 >5亿/天, 中型股 1-5亿, 小型股 3000万-1亿, 细价股 <3000万
        liq_pts = 0
        turnover = volume * close
        if turnover > 0:
            if turnover >= 1_000_000_000:      # ≥ 10 亿 HKD (超蓝筹)
                liq_pts = 10
                notes.append(f"极高流动性 {self._fmt_turnover(turnover)}/日")
            elif turnover >= 500_000_000:       # ≥ 5 亿 (大蓝筹)
                liq_pts = 9
                notes.append(f"高流动性 {self._fmt_turnover(turnover)}/日")
            elif turnover >= 200_000_000:       # ≥ 2 亿
                liq_pts = 7
                notes.append(f"流动性良好 {self._fmt_turnover(turnover)}/日")
            elif turnover >= 100_000_000:       # ≥ 1 亿
                liq_pts = 5
                notes.append(f"流动性中等 {self._fmt_turnover(turnover)}/日")
            elif turnover >= 30_000_000:        # ≥ 3000 万
                liq_pts = 3
                notes.append(f"流动性一般 {self._fmt_turnover(turnover)}/日")
            elif turnover >= 10_000_000:        # ≥ 1000 万
                liq_pts = 2
            else:
                liq_pts = 0
                notes.append(f"流动性不足 {self._fmt_turnover(turnover)}/日")
        else:
            liq_pts = 1
        breakdown["liquidity"] = liq_pts
        total += liq_pts

        # ════════════════════════════════════════════════════════
        # 汇总 & 评级
        # ════════════════════════════════════════════════════════
        total = max(0, min(100, total))

        if total >= 80:
            quality = "High Quality Setup"
        elif total >= 65:
            quality = "Tradable"
        elif total >= 50:
            quality = "Weak Setup"
        elif total >= 35:
            quality = "Low Confidence"
        else:
            quality = "Avoid Execution"

        return {
            "trade_quality_score": total,
            "quality": quality,
            "breakdown": breakdown,
            "notes": notes,
        }


    @staticmethod
    def _fmt_turnover(turnover: float) -> str:
        """格式化成交额为易读字符串"""
        if turnover >= 100_000_000:
            return f"{turnover / 100_000_000:.1f}亿"
        elif turnover >= 10_000:
            return f"{turnover / 10_000:.0f}万"
        else:
            return f"{turnover:.0f}"


class FutuTradingViewAdapter:
    """
    富途 + TradingView MCP 综合适配器

    功能：
    1. 富途 OpenD 获取 K 线数据
    2. TradingView MCP 官方算法计算技术指标
    3. 智能信号分析与 AI 决策
    """

    def __init__(self, futu_host: str = '127.0.0.1', futu_port: int = 11111):
        self.futu_host = futu_host
        self.futu_port = futu_port
        self.indicators = TradingViewIndicators()
        self._futu_ctx = None

    def _get_futu_context(self):
        """获取富途连接上下文"""
        if self._futu_ctx is None:
            self._futu_ctx = OpenQuoteContext(host=self.futu_host, port=self.futu_port)
        return self._futu_ctx

    def close(self):
        """关闭连接"""
        if self._futu_ctx:
            self._futu_ctx.close()
            self._futu_ctx = None

    def _normalize_code(self, stock_code: str) -> str:
        """标准化股票代码"""
        stock_code = stock_code.strip().upper()

        # 如果已经是 HK. 或 HK.00 格式，直接返回
        if stock_code.startswith('HK.'):
            return stock_code

        # 00700.HK -> HK.00700
        if stock_code.endswith('.HK'):
            num = stock_code.replace('.HK', '').zfill(5)
            return f'HK.{num}'

        # 700 -> HK.00700
        if stock_code.isdigit():
            num = stock_code.zfill(5)
            return f'HK.{num}'

        # 00005 -> HK.00005
        return f'HK.{stock_code.zfill(5)}'

    def get_kline_data(self, stock_code: str, days: int = 90) -> Dict[str, Any]:
        """
        获取K线数据

        Returns:
            {
                'success': bool,
                'count': int,
                'ohlc': [{'time': str, 'open': float, 'high': float, 'low': float, 'close': float, 'volume': float}],
                'latest': {...}
            }
        """
        try:
            ctx = self._get_futu_context()
            code = self._normalize_code(stock_code)

            # 计算日期范围
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=days * 2)).strftime('%Y-%m-%d')

            # 获取K线数据（新版富途API返回三元组）
            ret, data, extra = ctx.request_history_kline(
                code,
                start=start_date,
                end=end_date,
                ktype='K_DAY'
            )

            if ret != RET_OK:
                return {'success': False, 'error': f'富途API错误: {data}'}

            # 按日期排序
            data = data.sort_values('time_key').reset_index(drop=True)

            # 限制返回数量
            if len(data) > days:
                data = data.tail(days)

            # 转换为列表格式
            ohlc_list = []
            for _, row in data.iterrows():
                ohlc_list.append({
                    'time': row['time_key'],
                    'open': float(row['open']),
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'close': float(row['close']),
                    'volume': float(row['volume'])
                })

            return {
                'success': True,
                'count': len(ohlc_list),
                'ohlc': ohlc_list,
                'latest': ohlc_list[-1] if ohlc_list else None
            }

        except Exception as e:
            logger.error(f"获取K线失败: {e}")
            return {'success': False, 'error': str(e)}

    def calculate_technical_indicators(self, stock_code: str, days: int = 90) -> Dict[str, Any]:
        """
        计算技术指标（使用 TradingView MCP 官方算法）

        Returns:
            {
                'success': bool,
                'algorithm': str,  # 'TradingView MCP' or 'Pandas'
                'indicators': {...},
                'signals': {...}
            }
        """
        try:
            # 获取K线数据（至少250天以支持 MA200/EMA200）
            actual_days = max(days, 250)
            kline_result = self.get_kline_data(stock_code, days=actual_days)
            if not kline_result.get('success'):
                return kline_result

            # 转换为 DataFrame
            df = pd.DataFrame(kline_result['ohlc'])

            # 使用 TradingView MCP 算法计算指标
            indicators = self.indicators.calculate_all(df)

            # 生成交易信号
            signals = self._generate_signals(indicators, df)

            # 最新 K 线数据
            latest = df.iloc[-1].to_dict() if len(df) > 0 else {}

            # 计算交易设置（入场/止损/目标/支撑阻力）
            trade_setup = None
            trade_quality = None
            if TV_ADVANCED_AVAILABLE:
                trade_setup = self.indicators.compute_trade_setup_from_indicators(indicators, latest)
                if trade_setup:
                    # 使用港股适配版质量评分
                    trade_quality = self.indicators.compute_trade_quality_hk(
                        indicators, latest, trade_setup)

            return {
                'success': True,
                'algorithm': 'TradingView MCP' if self.indicators.tv_available else 'Pandas',
                'indicators': indicators,
                'signals': signals,
                'trade_setup': trade_setup,
                'trade_quality': trade_quality,
                'data_count': len(df)
            }

        except Exception as e:
            logger.error(f"指标计算失败: {e}")
            return {'success': False, 'error': str(e)}

    def _generate_signals(self, indicators: Dict, df: pd.DataFrame) -> Dict[str, Any]:
        """
        基于技术指标生成32+维度的交易信号

        信号分类：
        【趋势信号】8个：MA5/10/20/30/60 多头排列、MA 死叉/金叉、EMA12/26 关系
        【动量信号】8个：MACD 金叉/死叉/背离、RSI 超买/超卖/金叉/死叉、KDJ 超买超卖
        【波动信号】5个：布林带收口/张口、ATR 突破、Supertrend 方向变化、CCI 超买超卖
        【量价信号】6个：成交量放大/萎缩、OBV 趋势、VR 量能、量价背离
        【枢轴信号】5个：Pivot 支撑阻力、突破/跌破关键位

        Returns:
            {
                'trend': str,           # bullish/bearish/neutral
                'momentum': str,        # bullish/bearish/neutral
                'volatility': str,     # expanding/normal/contracting
                'volume': str,         # accumulation/distribution/neutral
                'overall': str,        # STRONG_BUY / BUY / HOLD / SELL / STRONG_SELL
                'recommendations': [], # 所有信号的详细列表
                'signal_summary': {},  # 信号统计
                'signals_32': {}       # 32个独立信号的详情
            }
        """
        signals = {
            'trend': 'neutral',
            'momentum': 'neutral',
            'volatility': 'normal',
            'volume': 'neutral',
            'overall': 'HOLD',
            'recommendations': [],
            'signal_summary': {},
            'signals_32': {}
        }

        all_signals = []  # 收集所有信号用于最终评分
        latest_close = df['close'].iloc[-1] if len(df) > 0 else 0
        prev_close = df['close'].iloc[-2] if len(df) > 1 else latest_close

        # =====================================================
        # 【趋势信号】Trend Signals
        # =====================================================

        # 1. MA 多头排列 (MA5 > MA10 > MA20)
        if all(indicators.get(k) for k in ['ma_5', 'ma_10', 'ma_20']):
            if indicators['ma_5'] > indicators['ma_10'] > indicators['ma_20']:
                all_signals.append({'type': 'trend', 'name': 'MA多头排列(5>10>20)', 'direction': 'bullish', 'strength': 3})
            elif indicators['ma_5'] < indicators['ma_10'] < indicators['ma_20']:
                all_signals.append({'type': 'trend', 'name': 'MA空头排列(5<10<20)', 'direction': 'bearish', 'strength': 3})

        # 2. MA10 与 MA20 交叉
        if all(indicators.get(k) for k in ['ma_10', 'ma_20']):
            if indicators['ma_10'] > indicators['ma_20']:
                all_signals.append({'type': 'trend', 'name': 'MA10>MA20', 'direction': 'bullish', 'strength': 2})
            else:
                all_signals.append({'type': 'trend', 'name': 'MA10<MA20', 'direction': 'bearish', 'strength': 2})

        # 3. MA20 与 MA60 交叉
        if all(indicators.get(k) for k in ['ma_20', 'ma_60']):
            if indicators['ma_20'] > indicators['ma_60']:
                all_signals.append({'type': 'trend', 'name': 'MA20>MA60(长期看涨)', 'direction': 'bullish', 'strength': 3})
            else:
                all_signals.append({'type': 'trend', 'name': 'MA20<MA60(长期看跌)', 'direction': 'bearish', 'strength': 3})

        # 4. EMA12 > EMA26 (快速EMA在慢速EMA上方)
        if all(indicators.get(k) for k in ['ema_12', 'ema_26']):
            if indicators['ema_12'] > indicators['ema_26']:
                all_signals.append({'type': 'trend', 'name': 'EMA12>EMA26', 'direction': 'bullish', 'strength': 2})
            else:
                all_signals.append({'type': 'trend', 'name': 'EMA12<EMA26', 'direction': 'bearish', 'strength': 2})

        # 5. 价格与 MA5 关系
        if indicators.get('ma_5'):
            if latest_close > indicators['ma_5']:
                all_signals.append({'type': 'trend', 'name': '价格>MA5', 'direction': 'bullish', 'strength': 1})
            else:
                all_signals.append({'type': 'trend', 'name': '价格<MA5', 'direction': 'bearish', 'strength': 1})

        # 6. 价格与 MA20 关系
        if indicators.get('ma_20'):
            if latest_close > indicators['ma_20']:
                all_signals.append({'type': 'trend', 'name': '价格>MA20', 'direction': 'bullish', 'strength': 2})
            else:
                all_signals.append({'type': 'trend', 'name': '价格<MA20', 'direction': 'bearish', 'strength': 2})

        # 7. 价格与 MA60 关系
        if indicators.get('ma_60'):
            if latest_close > indicators['ma_60']:
                all_signals.append({'type': 'trend', 'name': '价格>MA60(长期看涨)', 'direction': 'bullish', 'strength': 3})
            else:
                all_signals.append({'type': 'trend', 'name': '价格<MA60(长期看跌)', 'direction': 'bearish', 'strength': 3})

        # 8. MA30 趋势信号
        if indicators.get('ma_30'):
            if latest_close > indicators['ma_30']:
                all_signals.append({'type': 'trend', 'name': '价格>MA30', 'direction': 'bullish', 'strength': 2})
            else:
                all_signals.append({'type': 'trend', 'name': '价格<MA30', 'direction': 'bearish', 'strength': 2})

        # 9. 价格与 MA200 关系（牛熊分界线）
        if indicators.get('ma_200'):
            if latest_close > indicators['ma_200']:
                all_signals.append({'type': 'trend', 'name': '价格>MA200(牛市区域)', 'direction': 'bullish', 'strength': 4})
            else:
                all_signals.append({'type': 'trend', 'name': '价格<MA200(熊市区域)', 'direction': 'bearish', 'strength': 4})

        # 10. EMA200 信号
        if indicators.get('ema_200'):
            if latest_close > indicators['ema_200']:
                all_signals.append({'type': 'trend', 'name': '价格>EMA200(长线看涨)', 'direction': 'bullish', 'strength': 3})
            else:
                all_signals.append({'type': 'trend', 'name': '价格<EMA200(长线看跌)', 'direction': 'bearish', 'strength': 3})

        # 11. EMA60 信号（中线趋势核心）
        if indicators.get('ema_60'):
            if latest_close > indicators['ema_60']:
                all_signals.append({'type': 'trend', 'name': '价格>EMA60(中线看涨)', 'direction': 'bullish', 'strength': 3})
            else:
                all_signals.append({'type': 'trend', 'name': '价格<EMA60(中线看跌)', 'direction': 'bearish', 'strength': 3})

        # 12. EMA20 与 EMA60 交叉（黄金/死亡交叉）
        if all(indicators.get(k) for k in ['ema_20', 'ema_60']):
            if indicators['ema_20'] > indicators['ema_60']:
                all_signals.append({'type': 'trend', 'name': 'EMA20>EMA60(黄金交叉)', 'direction': 'bullish', 'strength': 3})
            else:
                all_signals.append({'type': 'trend', 'name': 'EMA20<EMA60(死亡交叉)', 'direction': 'bearish', 'strength': 3})

        # =====================================================
        # 【动量信号】Momentum Signals
        # =====================================================

        # 9. MACD 金叉 (DIF 上穿 DEA)
        if indicators.get('macd') and indicators.get('macd_signal'):
            if indicators['macd'] > indicators['macd_signal']:
                all_signals.append({'type': 'momentum', 'name': 'MACD金叉(DIF>DEA)', 'direction': 'bullish', 'strength': 3})
            else:
                all_signals.append({'type': 'momentum', 'name': 'MACD死叉(DIF<DEA)', 'direction': 'bearish', 'strength': 3})

        # 10. MACD 柱状图方向
        if indicators.get('macd_histogram'):
            if indicators['macd_histogram'] > 0:
                all_signals.append({'type': 'momentum', 'name': 'MACD柱状图>0(多头)', 'direction': 'bullish', 'strength': 2})
            else:
                all_signals.append({'type': 'momentum', 'name': 'MACD柱状图<0(空头)', 'direction': 'bearish', 'strength': 2})

        # 11. MACD 背离检测 (价格创新低但 MACD 没有)
        if len(df) >= 20 and indicators.get('macd'):
            recent_closes = df['close'].tail(20).tolist()
            prev_min_idx = recent_closes.index(min(recent_closes)) if min(recent_closes) else 0
            if prev_min_idx < 10 and indicators['macd'] > indicators.get('macd_histogram', 0):
                all_signals.append({'type': 'momentum', 'name': 'MACD底背离', 'direction': 'bullish', 'strength': 4})

        # 12. RSI 多周期信号
        for period, label in [(6, 'RSI(6)'), (12, 'RSI(12)'), (24, 'RSI(24)')]:
            rsi_key = f'rsi_{period}'
            if indicators.get(rsi_key):
                rsi = indicators[rsi_key]
                if rsi < 20:
                    all_signals.append({'type': 'momentum', 'name': f'{label}严重超卖(<20)', 'direction': 'bullish', 'strength': 4})
                elif rsi < 30:
                    all_signals.append({'type': 'momentum', 'name': f'{label}超卖(<30)', 'direction': 'bullish', 'strength': 3})
                elif rsi > 80:
                    all_signals.append({'type': 'momentum', 'name': f'{label}严重超买(>80)', 'direction': 'bearish', 'strength': 4})
                elif rsi > 70:
                    all_signals.append({'type': 'momentum', 'name': f'{label}超买(>70)', 'direction': 'bearish', 'strength': 3})

        # 13. KDJ 金叉/死叉
        if all(indicators.get(k) for k in ['kdj_k', 'kdj_d']):
            if indicators['kdj_k'] > indicators['kdj_d']:
                all_signals.append({'type': 'momentum', 'name': 'KDJ金叉(K>D)', 'direction': 'bullish', 'strength': 2})
            else:
                all_signals.append({'type': 'momentum', 'name': 'KDJ死叉(K<D)', 'direction': 'bearish', 'strength': 2})

        # 14. KDJ 超买超卖
        if indicators.get('kdj_j'):
            if indicators['kdj_j'] < 0:
                all_signals.append({'type': 'momentum', 'name': 'KDJ J值<0(严重超卖)', 'direction': 'bullish', 'strength': 4})
            elif indicators['kdj_j'] < 20:
                all_signals.append({'type': 'momentum', 'name': 'KDJ J值<20(超卖)', 'direction': 'bullish', 'strength': 3})
            elif indicators['kdj_j'] > 100:
                all_signals.append({'type': 'momentum', 'name': 'KDJ J值>100(严重超买)', 'direction': 'bearish', 'strength': 4})
            elif indicators['kdj_j'] > 80:
                all_signals.append({'type': 'momentum', 'name': 'KDJ J值>80(超买)', 'direction': 'bearish', 'strength': 3})

        # =====================================================
        # 【波动信号】Volatility Signals
        # =====================================================

        # 15. 布林带位置
        if indicators.get('bb_upper') and indicators.get('bb_lower'):
            bb_width = indicators['bb_upper'] - indicators['bb_lower']
            if bb_width > 0:
                bb_position = (latest_close - indicators['bb_lower']) / bb_width
                if bb_position < 0.15:
                    all_signals.append({'type': 'volatility', 'name': '触及布林下轨(超卖)', 'direction': 'bullish', 'strength': 3})
                elif bb_position > 0.85:
                    all_signals.append({'type': 'volatility', 'name': '触及布林上轨(超买)', 'direction': 'bearish', 'strength': 3})
                elif bb_position > 0.5:
                    all_signals.append({'type': 'volatility', 'name': '价格运行于布林上半段', 'direction': 'bullish', 'strength': 1})
                else:
                    all_signals.append({'type': 'volatility', 'name': '价格运行于布林下半段', 'direction': 'bearish', 'strength': 1})

        # 16. 布林带收口/张口 (与历史比较)
        if len(df) >= 20 and indicators.get('bb_upper') and indicators.get('bb_lower'):
            bb_width_current = indicators['bb_upper'] - indicators['bb_lower']
            prev_bbs = []
            for i in range(-20, -1):
                if len(df) + i >= 0:
                    row = df.iloc[i]
                    rolling_std = df['close'].iloc[max(0, i-19):i+1].std()
                    prev_bb_width = rolling_std * 4
                    prev_bbs.append(prev_bb_width)
            if prev_bbs and bb_width_current < sum(prev_bbs) / len(prev_bbs) * 0.7:
                all_signals.append({'type': 'volatility', 'name': '布林带收口(蓄势)', 'direction': 'neutral', 'strength': 2})
            elif prev_bbs and bb_width_current > sum(prev_bbs) / len(prev_bbs) * 1.3:
                all_signals.append({'type': 'volatility', 'name': '布林带张口(趋势加速)', 'direction': 'neutral', 'strength': 2})

        # 17. Supertrend 方向
        if indicators.get('supertrend') is not None:
            if indicators['supertrend'] > 0:
                all_signals.append({'type': 'volatility', 'name': 'Supertrend上涨', 'direction': 'bullish', 'strength': 2})
            else:
                all_signals.append({'type': 'volatility', 'name': 'Supertrend下跌', 'direction': 'bearish', 'strength': 2})

        # 18. CCI 超买超卖
        if indicators.get('cci'):
            cci = indicators['cci']
            if cci < -100:
                all_signals.append({'type': 'volatility', 'name': 'CCI严重超卖(<-100)', 'direction': 'bullish', 'strength': 3})
            elif cci < -50:
                all_signals.append({'type': 'volatility', 'name': 'CCI超卖(<-50)', 'direction': 'bullish', 'strength': 2})
            elif cci > 100:
                all_signals.append({'type': 'volatility', 'name': 'CCI严重超买(>100)', 'direction': 'bearish', 'strength': 3})
            elif cci > 50:
                all_signals.append({'type': 'volatility', 'name': 'CCI超买(>50)', 'direction': 'bearish', 'strength': 2})

        # 19. Williams %R
        if indicators.get('williams_r'):
            wr = indicators['williams_r']
            if wr < -80:
                all_signals.append({'type': 'volatility', 'name': 'Williams%R超卖(<-80)', 'direction': 'bullish', 'strength': 3})
            elif wr < -50:
                all_signals.append({'type': 'volatility', 'name': 'Williams%R低于中位', 'direction': 'bearish', 'strength': 1})
            elif wr > -20:
                all_signals.append({'type': 'volatility', 'name': 'Williams%R超买(>-20)', 'direction': 'bearish', 'strength': 3})
            elif wr > -50:
                all_signals.append({'type': 'volatility', 'name': 'Williams%R高于中位', 'direction': 'bullish', 'strength': 1})

        # =====================================================
        # 【量价信号】Volume Signals
        # =====================================================

        # 20. 成交量 MA 关系
        if all(indicators.get(k) for k in ['vol_ma_5', 'vol_ma_20']):
            if indicators.get('volume_ma_5'):
                all_signals.append({'type': 'volume', 'name': 'Vol MA5存在', 'direction': 'neutral', 'strength': 1})

        # 21. OBV 趋势
        if indicators.get('obv') and len(df) >= 10:
            recent_vol = df['volume'].tail(10).tolist()
            recent_close = df['close'].tail(10).tolist()
            obv_direction = 'neutral'
            for i in range(1, len(recent_close)):
                if recent_close[i] > recent_close[i-1] and recent_vol[i] > recent_vol[i-1]:
                    obv_direction = 'bullish'
                    break
                elif recent_close[i] < recent_close[i-1] and recent_vol[i] > recent_vol[i-1]:
                    obv_direction = 'bearish'
                    break
            if obv_direction == 'bullish':
                all_signals.append({'type': 'volume', 'name': '量价齐升(健康上涨)', 'direction': 'bullish', 'strength': 3})
            elif obv_direction == 'bearish':
                all_signals.append({'type': 'volume', 'name': '价跌量增(恐慌抛售)', 'direction': 'bearish', 'strength': 3})

        # 22. VR 量能指标
        if indicators.get('vr'):
            vr = indicators['vr']
            if vr > 300:
                all_signals.append({'type': 'volume', 'name': f'VR量能饱满({vr:.0f})', 'direction': 'bullish', 'strength': 2})
            elif vr < 80:
                all_signals.append({'type': 'volume', 'name': f'VR量能萎缩({vr:.0f})', 'direction': 'neutral', 'strength': 2})

        # 23. ROC 变化率
        if indicators.get('roc'):
            roc = indicators['roc']
            if roc > 10:
                all_signals.append({'type': 'volume', 'name': f'ROC加速上涨({roc:+.1f}%)', 'direction': 'bullish', 'strength': 3})
            elif roc > 5:
                all_signals.append({'type': 'volume', 'name': f'ROC稳步上升({roc:+.1f}%)', 'direction': 'bullish', 'strength': 2})
            elif roc < -10:
                all_signals.append({'type': 'volume', 'name': f'ROC加速下跌({roc:+.1f}%)', 'direction': 'bearish', 'strength': 3})
            elif roc < -5:
                all_signals.append({'type': 'volume', 'name': f'ROC稳步下降({roc:+.1f}%)', 'direction': 'bearish', 'strength': 2})

        # =====================================================
        # 【枢轴信号】Pivot Point Signals
        # =====================================================

        # 24. 价格与 Pivot 关系
        if indicators.get('pivot'):
            pivot = indicators['pivot']
            if latest_close > pivot:
                all_signals.append({'type': 'pivot', 'name': '价格>Pivot(偏多)', 'direction': 'bullish', 'strength': 2})
            else:
                all_signals.append({'type': 'pivot', 'name': '价格<Pivot(偏空)', 'direction': 'bearish', 'strength': 2})

        # 25. R1 阻力突破
        if indicators.get('r1'):
            if latest_close > indicators['r1']:
                all_signals.append({'type': 'pivot', 'name': '突破R1阻力位', 'direction': 'bullish', 'strength': 3})

        # 26. S1 支撑跌破
        if indicators.get('s1'):
            if latest_close < indicators['s1']:
                all_signals.append({'type': 'pivot', 'name': '跌破S1支撑位', 'direction': 'bearish', 'strength': 3})

        # 27. R2 阻力测试
        if indicators.get('r2'):
            r2_dist = abs(latest_close - indicators['r2']) / latest_close * 100 if latest_close else 999
            if r2_dist < 2:
                all_signals.append({'type': 'pivot', 'name': '接近R2强阻力', 'direction': 'bearish', 'strength': 2})

        # 28. S2 支撑测试
        if indicators.get('s2'):
            s2_dist = abs(latest_close - indicators['s2']) / latest_close * 100 if latest_close else 999
            if s2_dist < 2:
                all_signals.append({'type': 'pivot', 'name': '接近S2强支撑', 'direction': 'bullish', 'strength': 2})

        # =====================================================
        # 【综合评分】
        # =====================================================

        # 计算总分
        bullish_score = sum(s['strength'] for s in all_signals if s['direction'] == 'bullish')
        bearish_score = sum(s['strength'] for s in all_signals if s['direction'] == 'bearish')
        total_score = bullish_score + bearish_score

        # 趋势判断
        trend_bull = sum(1 for s in all_signals if s['type'] == 'trend' and s['direction'] == 'bullish')
        trend_bear = sum(1 for s in all_signals if s['type'] == 'trend' and s['direction'] == 'bearish')
        signals['trend'] = 'bullish' if trend_bull > trend_bear else ('bearish' if trend_bear > trend_bull else 'neutral')

        # 动量判断
        momo_bull = sum(1 for s in all_signals if s['type'] == 'momentum' and s['direction'] == 'bullish')
        momo_bear = sum(1 for s in all_signals if s['type'] == 'momentum' and s['direction'] == 'bearish')
        signals['momentum'] = 'bullish' if momo_bull > momo_bear else ('bearish' if momo_bear > momo_bull else 'neutral')

        # 波动判断
        vol_bull = sum(1 for s in all_signals if s['type'] == 'volatility' and s['direction'] == 'bullish')
        vol_bear = sum(1 for s in all_signals if s['type'] == 'volatility' and s['direction'] == 'bearish')
        signals['volatility'] = 'bullish' if vol_bull > vol_bear else ('bearish' if vol_bear > vol_bull else 'normal')

        # 量能判断
        vol_sgn_bull = sum(1 for s in all_signals if s['type'] == 'volume' and s['direction'] == 'bullish')
        vol_sgn_bear = sum(1 for s in all_signals if s['type'] == 'volume' and s['direction'] == 'bearish')
        signals['volume'] = 'accumulation' if vol_sgn_bull > vol_sgn_bear else ('distribution' if vol_sgn_bear > vol_sgn_bull else 'neutral')

        # 生成推荐信号文本
        for sig in all_signals:
            emoji = '📈' if sig['direction'] == 'bullish' else ('📉' if sig['direction'] == 'bearish' else '⚖️')
            strength_bar = '●●●' if sig['strength'] >= 3 else ('●●' if sig['strength'] >= 2 else '●')
            signals['recommendations'].append(f"{emoji} {strength_bar} {sig['name']}")

        # 汇总统计
        signals['signal_summary'] = {
            'total_signals': len(all_signals),
            'bullish_signals': sum(1 for s in all_signals if s['direction'] == 'bullish'),
            'bearish_signals': sum(1 for s in all_signals if s['direction'] == 'bearish'),
            'neutral_signals': sum(1 for s in all_signals if s['direction'] == 'neutral'),
            'bullish_score': bullish_score,
            'bearish_score': bearish_score,
            'trend_signals': trend_bull + trend_bear,
            'momentum_signals': momo_bull + momo_bear,
            'volatility_signals': vol_bull + vol_bear,
            'volume_signals': vol_sgn_bull + vol_sgn_bear,
            'pivot_signals': sum(1 for s in all_signals if s['type'] == 'pivot')
        }

        # 保存32+独立信号
        signals['signals_32'] = {
            'trend_signals': [s for s in all_signals if s['type'] == 'trend'],
            'momentum_signals': [s for s in all_signals if s['type'] == 'momentum'],
            'volatility_signals': [s for s in all_signals if s['type'] == 'volatility'],
            'volume_signals': [s for s in all_signals if s['type'] == 'volume'],
            'pivot_signals': [s for s in all_signals if s['type'] == 'pivot']
        }

        # 综合判断
        score_diff = bullish_score - bearish_score
        if score_diff >= 6:
            signals['overall'] = 'STRONG_BUY'
        elif score_diff >= 2:
            signals['overall'] = 'BUY'
        elif score_diff <= -6:
            signals['overall'] = 'STRONG_SELL'
        elif score_diff <= -2:
            signals['overall'] = 'SELL'
        else:
            signals['overall'] = 'HOLD'

        return signals

    def get_price(self, stock_code: str) -> Dict[str, Any]:
        """获取实时价格"""
        try:
            ctx = self._get_futu_context()
            code = self._normalize_code(stock_code)

            ret, data = ctx.get_market_snapshot([code])
            if ret == RET_OK and len(data) > 0:
                row = data.iloc[0]
                return {
                    'success': True,
                    'code': stock_code,
                    'name': row.get('name', stock_code),
                    'last_price': float(row.get('last_price', 0)),
                    'open': float(row.get('open_price', 0)),
                    'high': float(row.get('high_price', 0)),
                    'low': float(row.get('low_price', 0)),
                    'volume': float(row.get('volume', 0)),
                    'turnover': float(row.get('turnover', 0)),
                    'change': float(row.get('change_val', 0)),
                    'change_pct': float(row.get('change_rate', 0)),
                    # 修正富途字段名: pe_ttm_ratio / pb_ratio
                    'pe': float(row.get('pe_ttm_ratio', 0)) if row.get('pe_ttm_ratio') and row.get('pe_ttm_ratio') != 'N/A' else None,
                    'pb': float(row.get('pb_ratio', 0)) if row.get('pb_ratio') and row.get('pb_ratio') != 'N/A' else None,
                    # 额外估值数据
                    'pe_ratio': float(row.get('pe_ratio', 0)) if row.get('pe_ratio') and row.get('pe_ratio') != 'N/A' else None,
                    'ey_ratio': float(row.get('ey_ratio', 0)) if row.get('ey_ratio') and row.get('ey_ratio') != 'N/A' else None,  # 盈利收益率
                    'dividend_yield': float(row.get('dividend_ratio_ttm', 0)) if row.get('dividend_ratio_ttm') and row.get('dividend_ratio_ttm') != 'N/A' else None,  # TTM股息率
                    'bps': float(row.get('net_asset_per_share', 0)) if row.get('net_asset_per_share') and row.get('net_asset_per_share') != 'N/A' else None,  # 每股净资产
                    'timestamp': datetime.now().isoformat()
                }
            else:
                return {'success': False, 'error': '获取行情失败'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_full_analysis(self, stock_code: str) -> Dict[str, Any]:
        """
        获取完整分析报告（K线 + 技术指标 + 实时价格 + AI信号）
        """
        kline = self.get_kline_data(stock_code, days=90)
        indicators = self.calculate_technical_indicators(stock_code, days=90)
        price = self.get_price(stock_code)

        return {
            'success': kline.get('success') and indicators.get('success'),
            'stock_code': stock_code,
            'algorithm': indicators.get('algorithm', 'Unknown'),
            'kline': kline,
            'indicators': indicators,
            'price': price,
            'timestamp': datetime.now().isoformat()
        }


# === 全局实例 ===
_adapter = None

def get_adapter() -> FutuTradingViewAdapter:
    """获取全局适配器实例"""
    global _adapter
    if _adapter is None:
        _adapter = FutuTradingViewAdapter()
    return _adapter
