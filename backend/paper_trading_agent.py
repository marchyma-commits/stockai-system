"""
StockAI Paper Trading Agent — AI 模拟交易决策引擎
StockAI v1.7 | 2026-04-13

模块:
  - TechnicalScorer   : 技术面评分 (趋势30 + 动量25 + MACD20 + 布林带15 + 量价10 = 100)
  - FundamentalScorer : 基本面评分 (ROE30 + PE25 + 股息率25 + 负债率20 = 100)
  - DecisionEngine    : 综合决策 (tech×0.65 + fund×0.35 → STRONG_BUY/BUY/HOLD/SELL/STRONG_SELL)
  - RiskManager       : 风控 (单股≤5%、≤20只、最低佣金HKD50)
  - PaperAccount      : 模拟账户 (初始HKD 100万、JSON持久化)
  - ai_decide()       : 一站式 AI 决策入口
"""

import json, os, math, logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
#  TechnicalScorer — 技术面评分
# ═══════════════════════════════════════════

class TechnicalScorer:
    """基于 pandas DataFrame K线数据计算技术面评分"""

    def __init__(self, df):
        """
        df 需包含列: Open, High, Low, Close, Volume
        df.index 为 DatetimeIndex
        """
        self.df = df
        self.closes = df['Close'].values
        self.highs  = df['High'].values
        self.lows   = df['Low'].values
        self.volumes = df['Volume'].values

    def calc_sma(self, period):
        """简单移动平均"""
        return [None] * (period - 1) + list(self._sma(self.closes, period))

    def _sma(self, data, period):
        result = []
        for i in range(len(data)):
            if i < period - 1:
                result.append(None)
            else:
                result.append(sum(data[i - period + 1:i + 1]) / period)
        return result

    def calc_ema(self, period):
        """指数移动平均"""
        k = 2 / (period + 1)
        result = [None] * (period - 1)
        # 首个 EMA = 前 period 个值的 SMA
        first_ema = sum(self.closes[:period]) / period
        result.append(first_ema)
        for i in range(period, len(self.closes)):
            result.append(self.closes[i] * k + result[-1] * (1 - k))
        return result

    def calc_rsi(self, period=14):
        """RSI"""
        if len(self.closes) < period + 1:
            return [None] * len(self.closes)
        result = [None] * period
        gains, losses = [], []
        for i in range(period, len(self.closes)):
            change = self.closes[i] - self.closes[i - 1]
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

    def calc_macd(self):
        """MACD (12, 26, 9)"""
        ema12 = self.calc_ema(12)
        ema26 = self.calc_ema(26)
        offset = 25  # EMA26 从第26个值开始
        macd_line = []
        for i in range(len(self.closes)):
            if i < offset or i >= len(ema12) or ema12[i] is None or ema26[i - 25 + 25] is None:
                # 对齐: ema12[i] 和 ema26[i] — ema26 偏移了25个位置
                pass
            macd_line.append(None)
        # 重新对齐
        macd_vals = []
        for i in range(offset, len(self.closes)):
            e12 = ema12[i] if i < len(ema12) else None
            e26 = ema26[i] if i < len(ema26) else None
            if e12 is not None and e26 is not None:
                macd_vals.append(e12 - e26)
            else:
                macd_vals.append(None)
        # MACD signal line (9-period EMA of MACD)
        macd_signal = []
        if len(macd_vals) >= 9:
            k = 2 / 10
            first_signal = sum(macd_vals[:9]) / 9
            macd_signal = [None] * (offset + 8)
            macd_signal.append(first_signal)
            for i in range(1, len(macd_vals)):
                macd_signal.append(macd_vals[i + offset - 1] if i + offset - 1 < len(macd_vals) else None)
        # 简化: 直接返回最新的 MACD 值和 histogram
        hist = []
        for i in range(len(macd_vals)):
            if macd_vals[i] is not None and i >= 8:
                signal_val = sum(macd_vals[max(0, i - 8):i + 1]) / min(9, i + 1)
                hist.append(macd_vals[i] - signal_val)
            else:
                hist.append(None)
        return macd_vals, hist

    def calc_bollinger(self, period=20, std_mult=2):
        """布林带"""
        upper, middle, lower, percent_b = [], [], [], []
        for i in range(len(self.closes)):
            if i < period - 1:
                upper.append(None); middle.append(None); lower.append(None); percent_b.append(None)
            else:
                window = self.closes[i - period + 1:i + 1]
                sma = sum(window) / period
                std = math.sqrt(sum((x - sma) ** 2 for x in window) / period)
                upper.append(sma + std_mult * std)
                middle.append(sma)
                lower.append(sma - std_mult * std)
                if (upper[-1] - lower[-1]) != 0:
                    percent_b.append((self.closes[i] - lower[-1]) / (upper[-1] - lower[-1]))
                else:
                    percent_b.append(0.5)
        return upper, middle, lower, percent_b

    def score(self):
        """返回 (总分, 各分量详情dict)"""
        if len(self.closes) < 30:
            return 50, {}

        n = len(self.closes)
        details = {}

        # ── 1. 趋势 (30分) ──
        # 设计: 以15分为中性基准，多空双向各15分空间
        sma5  = self.calc_sma(5)[-1]
        sma20 = self.calc_sma(20)[-1]
        sma60 = self.calc_sma(60) if n >= 60 else None
        sma60_val = sma60[-1] if sma60 and sma60[-1] is not None else None
        price = self.closes[-1]

        trend_score = 15  # 中性基准

        # 短期均线方向 (±6分)
        if price > sma5 and sma5 > sma20:
            trend_score += 6
        elif price > sma20:
            trend_score += 3
        else:
            trend_score -= 3

        # 长期趋势 (±6分)
        if sma60_val:
            if price > sma60_val:
                trend_score += 6
            else:
                trend_score -= 3
        # 无60日数据不给分, 保持基准

        # EMA60 趋势 (±4分)
        ema60 = self.calc_ema(60)
        ema60_val = ema60[-1] if ema60 and ema60[-1] is not None else None
        if ema60_val:
            if price > ema60_val:
                trend_score += 4
            else:
                trend_score -= 2

        # 均线多头/空头排列 (±3分)
        sma10 = self.calc_sma(10)[-1]
        if sma5 > sma10 > sma20:
            trend_score += 3  # 短期均线多头排列
        elif sma5 < sma10 < sma20:
            trend_score -= 3  # 短期均线空头排列

        # 近期涨幅 (±6分, 缓和)
        chg_5d = (self.closes[-1] - self.closes[-6]) / self.closes[-6] * 100 if n >= 6 else 0
        trend_score += min(max(chg_5d * 1.2, -6), 6)

        trend_score = round(max(0, min(30, trend_score)), 2)
        details['trend'] = {
            'score': trend_score,
            'detail': f'价格{"↑" if price > sma20 else "↓"}MA20 | {"↑" if ema60_val and price > ema60_val else "↓" if ema60_val else "N/A"}EMA60 | 5日涨跌{chg_5d:+.1f}%'
        }

        # ── 2. 动量 (25分) ──
        rsi = self.calc_rsi()
        rsi_val = rsi[-1] if rsi and rsi[-1] is not None else 50
        if rsi_val < 30:
            mom_score = 25
        elif rsi_val < 45:
            mom_score = 20
        elif rsi_val < 65:
            mom_score = 15
        elif rsi_val < 75:
            mom_score = 8
        else:
            mom_score = 3
        details['momentum'] = {
            'score': mom_score,
            'detail': f'RSI(14)={rsi_val:.1f}'
        }

        # ── 3. MACD (20分) ──
        macd_vals, hist = self.calc_macd()
        # 取最近3个有效的 histogram 值
        valid_hist = [h for h in hist[-5:] if h is not None]
        macd_score = 10  # 中性起步
        if len(valid_hist) >= 2:
            if valid_hist[-1] > 0 and valid_hist[-1] > valid_hist[-2]:
                macd_score = 20
            elif valid_hist[-1] > 0:
                macd_score = 15
            elif valid_hist[-1] < 0 and valid_hist[-1] < valid_hist[-2]:
                macd_score = 3
            elif valid_hist[-1] < 0:
                macd_score = 7
        macd_score = max(0, min(20, macd_score))
        details['macd'] = {
            'score': macd_score,
            'detail': f'Histogram {"多头" if valid_hist and valid_hist[-1] > 0 else "空头"}'
        }

        # ── 4. 布林带 (15分) ──
        upper, middle, lower, percent_b = self.calc_bollinger()
        pb_val = percent_b[-1] if percent_b and percent_b[-1] is not None else 0.5
        if pb_val < 0.1:
            bb_score = 18
        elif pb_val < 0.2:
            bb_score = 15
        elif pb_val < 0.8:
            bb_score = 10
        elif pb_val < 0.9:
            bb_score = 5
        else:
            bb_score = 2
        bb_score = max(0, min(15, bb_score))
        details['bollinger'] = {
            'score': bb_score,
            'detail': f'%B={pb_val:.2f} {"超卖" if pb_val < 0.2 else "超买" if pb_val > 0.8 else "中性"}'
        }

        # ── 5. 量价 (10分) → 增强为完整量能分析 ──
        # 5a. 量比 (20日均量)
        vol_score = 5  # 中性基准
        vol_detail_parts = []

        if n >= 20:
            avg_vol_20 = sum(self.volumes[-20:-1]) / 20  # 不含今天
            vol_ratio = self.volumes[-1] / avg_vol_20 if avg_vol_20 > 0 else 1

            # 量比+价格方向综合判断
            price_chg_today = (self.closes[-1] - self.closes[-2]) / self.closes[-2] * 100 if n >= 2 else 0

            if vol_ratio >= 2.0 and price_chg_today > 0:
                vol_score = 10  # 放量大涨 = 强买讯
                vol_detail_parts.append(f'量比{vol_ratio:.1f}放量大漲')
            elif vol_ratio >= 1.8 and price_chg_today > 0:
                vol_score = 8
                vol_detail_parts.append(f'量比{vol_ratio:.1f}溫和放量')
            elif vol_ratio >= 2.0 and price_chg_today < 0:
                vol_score = 2   # 放量下跌 = 警告
                vol_detail_parts.append(f'量比{vol_ratio:.1f}放量下跌')
            elif vol_ratio < 0.5:
                vol_score = 4   # 极度缩量
                vol_detail_parts.append(f'量比{vol_ratio:.1f}極度縮量')
            else:
                vol_detail_parts.append(f'量比{vol_ratio:.1f}')

            # 5b. Vol MA5 / Vol MA20 交叉
            if n >= 21:
                vol_ma5 = sum(self.volumes[-5:]) / 5
                vol_ma5_prev = sum(self.volumes[-6:-1]) / 5
                vol_ma20 = sum(self.volumes[-20:]) / 20
                vol_ma20_prev = sum(self.volumes[-21:-1]) / 20

                if vol_ma5_prev <= vol_ma20_prev and vol_ma5 > vol_ma20:
                    vol_score = min(vol_score + 2, 10)  # Vol 金叉加分
                    vol_detail_parts.append('Vol金叉')
                elif vol_ma5_prev >= vol_ma20_prev and vol_ma5 < vol_ma20:
                    vol_score = max(vol_score - 3, 0)  # Vol 死叉减分
                    vol_detail_parts.append('Vol死叉')

            # 5c. 量价背离检测
            if n >= 5:
                price_chg_5d = (self.closes[-1] - self.closes[-6]) / self.closes[-6]
                vol_chg_5d = (self.volumes[-1] - self.volumes[-6]) / max(self.volumes[-6], 1)
                if price_chg_5d > 0.03 and vol_chg_5d < -0.2:
                    vol_score = max(vol_score - 3, 0)  # 价涨量缩
                    vol_detail_parts.append('⚠量價背離')
                elif price_chg_5d < -0.03 and vol_chg_5d < -0.3:
                    vol_score = min(vol_score + 2, 10)  # 价跌量缩 = 可能见底
                    vol_detail_parts.append('價跌量縮')
        else:
            # 数据不足时用简单的量比
            avg_vol = sum(self.volumes[-20:]) / 20
            vol_ratio = self.volumes[-1] / avg_vol if avg_vol > 0 else 1
            vol_detail_parts.append(f'量比{vol_ratio:.2f}')
            if vol_ratio > 1.5:
                vol_score = 7
            elif vol_ratio > 0.8:
                vol_score = 5
            else:
                vol_score = 3

        vol_score = max(0, min(10, vol_score))
        details['volume'] = {
            'score': vol_score,
            'detail': ' | '.join(vol_detail_parts) if vol_detail_parts else f'量比{self.volumes[-1] / sum(self.volumes[-20:]) / 20:.2f}' if n >= 20 else '數據不足'
        }

        total = trend_score + mom_score + macd_score + bb_score + vol_score
        total = max(0, min(100, total))

        return total, details


# ═══════════════════════════════════════════
#  FundamentalScorer — 基本面评分
# ═══════════════════════════════════════════

class FundamentalScorer:
    """基于财务数据字典计算基本面评分"""

    def score(self, financials=None):
        """
        financials: dict, 包含以下可选字段:
            - roe: float (ROE 百分比, e.g. 15.2)
            - pe_ratio: float (市盈率)
            - dividend_yield: float (股息率 百分比)
            - debt_ratio: float (负债率 百分比)
        如果为 None 或缺少数据, 返回中性分 50
        """
        if not financials:
            return 50, self._neutral_details()

        details = {}

        # ── 1. ROE (30分) ──
        roe = financials.get('roe')
        if roe is not None:
            if roe >= 20:   roe_score = 30
            elif roe >= 15: roe_score = 25
            elif roe >= 10: roe_score = 18
            elif roe >= 5:  roe_score = 12
            else:           roe_score = 5
            details['roe'] = {'score': roe_score, 'detail': f'ROE={roe:.1f}%'}
        else:
            roe_score = 15
            details['roe'] = {'score': roe_score, 'detail': 'ROE: 无数据'}

        # ── 2. PE估值 (25分) ──
        pe = financials.get('pe_ratio')
        if pe is not None and pe > 0:
            if pe < 10:     pe_score = 25
            elif pe < 15:   pe_score = 22
            elif pe < 25:   pe_score = 16
            elif pe < 40:   pe_score = 8
            else:           pe_score = 3
            details['pe'] = {'score': pe_score, 'detail': f'PE={pe:.1f}'}
        elif pe is not None and pe < 0:
            pe_score = 5
            details['pe'] = {'score': pe_score, 'detail': f'PE={pe:.1f}(亏损)'}
        else:
            pe_score = 12
            details['pe'] = {'score': pe_score, 'detail': 'PE: 无数据'}

        # ── 3. 股息率 (25分) ──
        div = financials.get('dividend_yield')
        if div is not None:
            if div >= 5:     div_score = 25
            elif div >= 3:   div_score = 20
            elif div >= 1.5: div_score = 13
            elif div >= 0.5: div_score = 7
            else:            div_score = 3
            details['dividend'] = {'score': div_score, 'detail': f'股息率={div:.2f}%'}
        else:
            div_score = 12
            details['dividend'] = {'score': div_score, 'detail': '股息率: 无数据'}

        # ── 4. 负债率 (20分) ──
        debt = financials.get('debt_ratio')
        if debt is not None:
            if debt < 30:     debt_score = 20
            elif debt < 50:   debt_score = 16
            elif debt < 70:   debt_score = 10
            elif debt < 85:   debt_score = 5
            else:             debt_score = 2
            details['debt_ratio'] = {'score': debt_score, 'detail': f'负债率={debt:.1f}%'}
        else:
            debt_score = 10
            details['debt_ratio'] = {'score': debt_score, 'detail': '负债率: 无数据'}

        total = roe_score + pe_score + div_score + debt_score
        total = max(0, min(100, total))

        return total, details

    def _neutral_details(self):
        return {
            'roe':        {'score': 15, 'detail': 'ROE: 无数据'},
            'pe':         {'score': 12, 'detail': 'PE: 无数据'},
            'dividend':   {'score': 12, 'detail': '股息率: 无数据'},
            'debt_ratio': {'score': 10, 'detail': '负债率: 无数据'},
        }


# ═══════════════════════════════════════════
#  DecisionEngine — 综合决策
# ═══════════════════════════════════════════

class DecisionEngine:

    SIGNALS = ['STRONG_BUY', 'BUY', 'HOLD', 'SELL', 'STRONG_SELL']
    SIGNAL_LABELS = {
        'STRONG_BUY': '强烈买入', 'BUY': '买入',
        'HOLD': '持有观望', 'SELL': '卖出', 'STRONG_SELL': '强烈卖出'
    }

    def decide(self, tech_score, fund_score, current_price=None, cash=None):
        """
        返回 dict: {signal, action, action_type, combined_score, ...}
        """
        combined = round(tech_score * 0.65 + fund_score * 0.35, 2)

        # 信号映射
        if combined >= 75:
            signal = 'STRONG_BUY'
        elif combined >= 58:
            signal = 'BUY'
        elif combined >= 42:
            signal = 'HOLD'
        elif combined >= 25:
            signal = 'SELL'
        else:
            signal = 'STRONG_SELL'

        action = self.SIGNAL_LABELS[signal]
        action_type = 'BUY' if signal in ('STRONG_BUY', 'BUY') else 'SELL' if signal in ('SELL', 'STRONG_SELL') else 'NEUTRAL'

        result = {
            'signal': signal,
            'action': action,
            'action_type': action_type,
            'combined_score': combined,
            'tech_score': tech_score,
            'fund_score': fund_score,
            'buy_quantity': 0,
            'sell_quantity': 0,
        }

        return result

    def calc_position_size(self, signal, current_price, cash, max_pct=0.05):
        """计算建议买入股数 (港股按100股整手)"""
        if current_price <= 0 or cash <= 0:
            return 0
        budget = cash * max_pct
        shares = int(budget / current_price / 100) * 100
        return max(shares, 100) if signal in ('STRONG_BUY', 'BUY') else 0


# ═══════════════════════════════════════════
#  RiskManager — 风控
# ═══════════════════════════════════════════

class RiskManager:
    MAX_HOLDINGS = 20
    MAX_SINGLE_STOCK_PCT = 0.05
    MIN_COMMISSION = 50  # HKD

    @staticmethod
    def check_buy(account, code, price, quantity):
        """
        返回 (ok:bool, message:str)
        """
        amount = price * quantity
        commission = max(amount * 0.001, RiskManager.MIN_COMMISSION)
        stamp_duty = amount * 0.0013
        total_cost = amount + commission + stamp_duty

        if account.cash < total_cost:
            return False, f'现金不足: 需要 HKD {total_cost:,.0f}, 可用 HKD {account.cash:,.0f}'

        if len(account.holdings) >= RiskManager.MAX_HOLDINGS and code not in account.holdings:
            return False, f'持仓已满 ({RiskManager.MAX_HOLDINGS}只), 无法新增'

        # 仓位占比检查
        total_assets = account.cash + account.market_value
        if total_assets > 0:
            position_pct = amount / total_assets
            if position_pct > RiskManager.MAX_SINGLE_STOCK_PCT:
                return False, f'仓位超限: {position_pct*100:.1f}% > {RiskManager.MAX_SINGLE_STOCK_PCT*100:.0f}%'

        return True, 'OK'

    @staticmethod
    def check_sell(account, code, quantity):
        if code not in account.holdings:
            return False, f'未持有 {code}'
        holding = account.holdings[code]
        if holding['quantity'] < quantity:
            return False, f'持仓不足: 持有{holding["quantity"]}股, 欲卖{quantity}股'
        return True, 'OK'


# ═══════════════════════════════════════════
#  PaperAccount — 模拟账户
# ═══════════════════════════════════════════

class PaperAccount:
    INITIAL_CASH = 1_000_000  # HKD

    def __init__(self, data_dir='paper_trading_data'):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cash = self.INITIAL_CASH
        self.holdings = {}   # {code: {name, quantity, avg_cost, buy_time}}
        self.history = []    # [{timestamp, type, code, name, price, quantity, amount, commission, pnl}]
        self._load()

    @property
    def market_value(self):
        """持仓市值 (需要外部传入实时价格来更新, 这里返回成本市值)"""
        return sum(h['quantity'] * h['avg_cost'] for h in self.holdings.values())

    @property
    def total_assets(self):
        return self.cash + self.market_value

    @property
    def holdings_count(self):
        return len(self.holdings)

    def buy(self, code, name, price, quantity):
        """买入股票, 返回 (success, message, trade_record)"""
        amount = price * quantity
        commission = max(amount * 0.001, 50)  # 最低佣金 HKD 50
        stamp_duty = amount * 0.0013           # 印花税 0.13%
        total_cost = amount + commission + stamp_duty

        if self.cash < total_cost:
            return False, f'现金不足', None

        self.cash -= total_cost

        if code in self.holdings:
            h = self.holdings[code]
            total_qty = h['quantity'] + quantity
            h['avg_cost'] = (h['avg_cost'] * h['quantity'] + price * quantity) / total_qty
            h['quantity'] = total_qty
        else:
            self.holdings[code] = {
                'name': name or code,
                'quantity': quantity,
                'avg_cost': price,
                'buy_time': datetime.now().isoformat(),
            }

        trade = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'BUY',
            'code': code,
            'name': name or code,
            'price': round(price, 3),
            'quantity': quantity,
            'amount': round(amount, 2),
            'commission': round(commission + stamp_duty, 2),
            'pnl': None,
        }
        self.history.append(trade)
        self._save()
        return True, f'买入 {name or code} {quantity}股 @ {price:.3f}', trade

    def sell(self, code, name, price, quantity):
        """卖出股票, 返回 (success, message, trade_record)"""
        if code not in self.holdings:
            return False, f'未持有 {code}', None

        h = self.holdings[code]
        if quantity > h['quantity']:
            return False, f'持仓不足: 持有{h["quantity"]}股', None

        amount = price * quantity
        commission = max(amount * 0.001, 50)
        stamp_duty = amount * 0.0013
        proceeds = amount - commission - stamp_duty
        cost_basis = h['avg_cost'] * quantity
        pnl = proceeds - cost_basis

        self.cash += proceeds
        h['quantity'] -= quantity
        if h['quantity'] == 0:
            del self.holdings[code]

        trade = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'SELL',
            'code': code,
            'name': name or code,
            'price': round(price, 3),
            'quantity': quantity,
            'amount': round(amount, 2),
            'commission': round(commission + stamp_duty, 2),
            'pnl': round(pnl, 2),
        }
        self.history.append(trade)
        self._save()
        return True, f'卖出 {name or code} {quantity}股 @ {price:.3f}, 盈亏 HKD {pnl:+,.0f}', trade

    def get_portfolio(self, price_map=None):
        """获取持仓概览, price_map: {code: current_price}"""
        holdings_list = []
        total_market_value = 0
        total_cost = 0

        for code, h in self.holdings.items():
            current_price = (price_map or {}).get(code, h['avg_cost'])
            mv = h['quantity'] * current_price
            cost = h['quantity'] * h['avg_cost']
            unrealized = mv - cost
            unrealized_pct = (unrealized / cost * 100) if cost > 0 else 0

            holdings_list.append({
                'code': code,
                'name': h['name'],
                'quantity': h['quantity'],
                'avg_cost': round(h['avg_cost'], 3),
                'current_price': round(current_price, 3),
                'market_value': round(mv, 2),
                'unrealized_pnl': round(unrealized, 2),
                'unrealized_pnl_pct': round(unrealized_pct, 2),
            })
            total_market_value += mv
            total_cost += cost

        # 已实现盈亏: 从交易历史中累加所有 SELL 的 pnl
        realized_pnl = sum(t.get('pnl', 0) or 0 for t in self.history if t.get('type') == 'SELL' and t.get('pnl') is not None)
        # 未实现盈亏
        unrealized_pnl_total = total_market_value - total_cost
        # 总盈亏 = 已实现 + 未实现
        total_pnl = realized_pnl + unrealized_pnl_total
        total_return_pct = (total_pnl / self.INITIAL_CASH * 100) if self.INITIAL_CASH > 0 else 0

        return {
            'cash': round(self.cash, 2),
            'market_value': round(total_market_value, 2),
            'total_assets': round(self.cash + total_market_value, 2),
            'realized_pnl': round(realized_pnl, 2),
            'unrealized_pnl': round(unrealized_pnl_total, 2),
            'total_pnl': round(total_pnl, 2),
            'total_return_pct': round(total_return_pct, 2),
            'holdings': holdings_list,
            'holdings_count': len(self.holdings),
        }

    def reset(self):
        self.cash = self.INITIAL_CASH
        self.holdings = {}
        self.history = []
        self._save()

    # ── 持久化 ──
    def _data_path(self):
        return self.data_dir / 'account.json'

    def _save(self):
        data = {
            'cash': self.cash,
            'holdings': self.holdings,
            'history': self.history,
            'last_updated': datetime.now().isoformat(),
        }
        try:
            with open(self._data_path(), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f'保存模拟账户失败: {e}')

    def _load(self):
        path = self._data_path()
        if not path.exists():
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.cash = data.get('cash', self.INITIAL_CASH)
            self.holdings = data.get('holdings', {})
            self.history = data.get('history', [])
        except Exception as e:
            logger.error(f'加载模拟账户失败: {e}, 使用默认值')


# ═══════════════════════════════════════════
#  全局实例 & 一站式 AI 决策
# ═══════════════════════════════════════════

_account = None
_account_mtime = 0.0


def get_account():
    """获取/创建全局 PaperAccount 单例（文件有变化时自动重载）"""
    global _account, _account_mtime
    if _account is None:
        _account = PaperAccount()
        _account_mtime = os.path.getmtime(_account._data_path())
    else:
        try:
            mtime = os.path.getmtime(_account._data_path())
            if mtime > _account_mtime:
                logger.info('account.json 文件有更新，重新加载...')
                _account._load()
                _account_mtime = mtime
        except OSError:
            pass
    return _account


def ai_decide(stock_code, stock_name, kline_df, financials=None):
    """
    一站式 AI 决策: K线 + 财务数据 → 完整决策报告

    Args:
        stock_code:  str, e.g. 'HK.00700'
        stock_name:  str, e.g. '腾讯控股'
        kline_df:    pd.DataFrame (Open/High/Low/Close/Volume, DatetimeIndex)
        financials:  dict or None

    Returns:
        dict: 完整决策报告
    """
    account = get_account()
    engine = DecisionEngine()

    # 技术面评分
    tech_scorer = TechnicalScorer(kline_df)
    tech_score, tech_detail = tech_scorer.score()

    # 基本面评分
    fund_scorer = FundamentalScorer()
    fund_score, fund_detail = fund_scorer.score(financials)

    # 综合决策
    decision = engine.decide(tech_score, fund_score)

    # 当前价格
    current_price = float(kline_df['Close'].iloc[-1]) if not kline_df.empty else 0

    # 结合持仓给出操作建议
    holding = account.holdings.get(stock_code)
    if holding:
        # 已持仓
        h_qty = holding['quantity']
        h_cost = holding['avg_cost']
        if current_price > 0:
            pnl_pct = (current_price - h_cost) / h_cost * 100
        else:
            pnl_pct = 0

        if decision['signal'] in ('STRONG_SELL', 'SELL'):
            decision['sell_quantity'] = h_qty
            decision['action'] = f'建议卖出 {h_qty}股 (持仓盈亏 {pnl_pct:+.1f}%)'
            decision['action_type'] = 'SELL'
        elif decision['signal'] == 'HOLD':
            decision['action'] = f'继续持有 {h_qty}股 (盈亏 {pnl_pct:+.1f}%)'
        else:
            # 信号看多但已持仓, 不加仓
            decision['action'] = f'继续持有 {h_qty}股 (盈亏 {pnl_pct:+.1f}%), AI 信号看多'
    else:
        # 未持仓
        if decision['signal'] in ('STRONG_BUY', 'BUY'):
            buy_qty = engine.calc_position_size(decision['signal'], current_price, account.cash)
            decision['buy_quantity'] = buy_qty
            decision['action'] = f'建议买入 {buy_qty}股 (约 HKD {buy_qty * current_price:,.0f})'
            decision['action_type'] = 'BUY'
        else:
            decision['action'] = '暂不操作, 观望为主'

    # 组装最终报告
    report = {
        'code': stock_code,
        'name': stock_name or stock_code,
        'current_price': round(current_price, 3),
        'signal': decision['signal'],
        'action': decision['action'],
        'action_type': decision['action_type'],
        'combined_score': decision['combined_score'],
        'tech_score': tech_score,
        'tech_detail': tech_detail,
        'fund_score': fund_score,
        'fund_detail': fund_detail,
        'buy_quantity': decision.get('buy_quantity', 0),
        'sell_quantity': decision.get('sell_quantity', 0),
        'holding_info': {
            'held': stock_code in account.holdings,
            'quantity': holding['quantity'] if holding else 0,
            'avg_cost': round(holding['avg_cost'], 3) if holding else 0,
        } if holding else {'held': False, 'quantity': 0, 'avg_cost': 0},
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }

    return report
