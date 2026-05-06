"""
AI 股票預測器 - 多模型融合系統
包含 4 個專業交易模型
"""

import numpy as np
import pandas as pd


class TrendModel:
    """模型 1: 趨勢追蹤模型"""
    
    def __init__(self):
        self.name = "📈 趨勢追蹤"
    
    def analyze(self, hist):
        if hist.empty or len(hist) < 60:
            return self._default_result()
        
        closes = hist['Close'].values
        highs = hist['High'].values
        lows = hist['Low'].values
        
        ma5 = np.mean(closes[-5:])
        ma20 = np.mean(closes[-20:])
        ma60 = np.mean(closes[-60:])
        ma120 = np.mean(closes[-120:]) if len(closes) >= 120 else ma60
        
        current_price = closes[-1]
        
        if ma5 > ma20 > ma60 > ma120 and current_price > ma5:
            signal = "買入"
            score = 85
            action = "BUY"
            detail = f"多頭排列，MA5({ma5:.2f}) > MA20({ma20:.2f})"
        elif ma5 < ma20 < ma60 < ma120 and current_price < ma5:
            signal = "賣出"
            score = 15
            action = "SELL"
            detail = f"空頭排列，MA5({ma5:.2f}) < MA20({ma20:.2f})"
        elif ma5 > ma20 and current_price > ma20:
            signal = "買入"
            score = 70
            action = "BUY"
            detail = f"短期趨勢向上"
        elif ma5 < ma20 and current_price < ma20:
            signal = "賣出"
            score = 30
            action = "SELL"
            detail = f"短期趨勢向下"
        else:
            signal = "持有"
            score = 50
            action = "HOLD"
            detail = "趨勢不明朗"
        
        # ADX 確認
        adx = self._calculate_adx(highs, lows, closes)
        if adx == "強趨勢" and action == "BUY":
            score = min(100, score + 5)
            detail += f"，{adx}確認"
        
        return {
            'name': self.name,
            'signal': signal,
            'score': score,
            'action': action,
            'detail': detail
        }
    
    def _calculate_adx(self, highs, lows, closes, period=14):
        if len(highs) < period + 1:
            return "數據不足"
        
        plus_dm = np.zeros(len(highs))
        minus_dm = np.zeros(len(highs))
        
        for i in range(1, len(highs)):
            up_move = highs[i] - highs[i-1]
            down_move = lows[i-1] - lows[i]
            if up_move > down_move and up_move > 0:
                plus_dm[i] = up_move
            if down_move > up_move and down_move > 0:
                minus_dm[i] = down_move
        
        tr = np.zeros(len(highs))
        for i in range(1, len(highs)):
            tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        
        plus_dm_smooth = np.mean(plus_dm[-period:])
        minus_dm_smooth = np.mean(minus_dm[-period:])
        
        if (plus_dm_smooth + minus_dm_smooth) > 0:
            dx = 100 * abs(plus_dm_smooth - minus_dm_smooth) / (plus_dm_smooth + minus_dm_smooth)
        else:
            dx = 0
        
        if dx > 25:
            return "強趨勢"
        elif dx > 20:
            return "中等趨勢"
        return "弱趨勢"
    
    def _default_result(self):
        return {'name': self.name, 'signal': '持有', 'score': 50, 'action': 'HOLD', 'detail': '數據不足'}


class MomentumModel:
    """模型 2: 動量反轉模型"""
    
    def __init__(self):
        self.name = "⚡ 動量反轉"
    
    def analyze(self, hist):
        if hist.empty or len(hist) < 20:
            return self._default_result()
        
        closes = hist['Close'].values
        volumes = hist['Volume'].values
        highs = hist['High'].values
        lows = hist['Low'].values
        
        current_price = closes[-1]
        
        rsi = self._calculate_rsi(closes)
        bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(closes)
        k, d, j = self._calculate_kdj(highs, lows, closes)
        
        ma20 = np.mean(closes[-20:])
        bias = (current_price - ma20) / ma20 * 100
        
        avg_volume = np.mean(volumes[-20:])
        volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 1
        
        score = 50
        detail_parts = []
        
        if rsi < 30:
            score += 20
            detail_parts.append(f"RSI超賣({rsi:.1f})")
        elif rsi > 70:
            score -= 20
            detail_parts.append(f"RSI超買({rsi:.1f})")
        
        if current_price < bb_lower:
            score += 15
            detail_parts.append("跌破下軌")
        elif current_price > bb_upper:
            score -= 15
            detail_parts.append("突破上軌")
        
        if k < 20 and j < 20:
            score += 15
            detail_parts.append("KDJ超賣")
        elif k > 80 and j > 80:
            score -= 15
            detail_parts.append("KDJ超買")
        
        if bias < -5:
            score += 10
            detail_parts.append(f"負乖離({bias:.1f}%)")
        elif bias > 5:
            score -= 10
            detail_parts.append(f"正乖離({bias:.1f}%)")
        
        if volume_ratio > 1.5 and score > 50:
            score += 5
            detail_parts.append("放量確認")
        
        score = max(0, min(100, score))
        
        if score >= 70:
            signal = "買入"
            action = "BUY"
        elif score <= 30:
            signal = "賣出"
            action = "SELL"
        else:
            signal = "持有"
            action = "HOLD"
        
        detail = "，".join(detail_parts) if detail_parts else "中性區間"
        
        return {
            'name': self.name,
            'signal': signal,
            'score': score,
            'action': action,
            'detail': detail
        }
    
    def _calculate_rsi(self, closes, period=14):
        if len(closes) < period + 1:
            return 50
        deltas = np.diff(closes[-period-1:])
        gains = deltas[deltas > 0].sum() / period
        losses = -deltas[deltas < 0].sum() / period
        if losses == 0:
            return 100
        if gains == 0:
            return 0
        rs = gains / losses
        return 100 - (100 / (1 + rs))
    
    def _calculate_bollinger_bands(self, closes, period=20):
        ma = np.mean(closes[-period:])
        std = np.std(closes[-period:])
        return ma + 2 * std, ma, ma - 2 * std
    
    def _calculate_kdj(self, highs, lows, closes, period=9):
        if len(highs) < period:
            return 50, 50, 50
        low_min = np.min(lows[-period:])
        high_max = np.max(highs[-period:])
        if high_max == low_min:
            return 50, 50, 50
        rsv = (closes[-1] - low_min) / (high_max - low_min) * 100
        k = rsv * 0.666 + 50 * 0.334
        d = k * 0.666 + 50 * 0.334
        j = 3 * k - 2 * d
        return k, d, j
    
    def _default_result(self):
        return {'name': self.name, 'signal': '持有', 'score': 50, 'action': 'HOLD', 'detail': '數據不足'}


class VolatilityModel:
    """模型 3: 波動率突破模型"""
    
    def __init__(self):
        self.name = "🌊 波動突破"
    
    def analyze(self, hist):
        if hist.empty or len(hist) < 20:
            return self._default_result()
        
        highs = hist['High'].values
        lows = hist['Low'].values
        closes = hist['Close'].values
        
        current_price = closes[-1]
        
        donchian_high = np.max(highs[-20:])
        donchian_low = np.min(lows[-20:])
        
        atr = self._calculate_atr(highs, lows, closes)
        bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(closes)
        bb_width = (bb_upper - bb_lower) / bb_middle * 100 if bb_middle > 0 else 0
        
        returns = np.diff(np.log(closes[-20:]))
        hist_vol = np.std(returns) * np.sqrt(252) * 100 if len(returns) > 0 else 0
        
        score = 50
        detail_parts = []
        
        if current_price > donchian_high:
            score += 30
            detail_parts.append(f"突破20日高點({donchian_high:.2f})")
        elif current_price < donchian_low:
            score -= 30
            detail_parts.append(f"跌破20日低點({donchian_low:.2f})")
        
        if bb_width > 20:
            score += 10 if score > 50 else -10
            detail_parts.append("波動放大")
        elif bb_width < 10:
            score += 5 if score < 50 else -5
            detail_parts.append("波動收窄")
        
        if atr[-1] > np.mean(atr[-10:]) * 1.2 if len(atr) >= 10 else False:
            detail_parts.append("波動增強")
        
        score = max(0, min(100, score))
        
        if score >= 70:
            signal = "買入"
            action = "BUY"
        elif score <= 30:
            signal = "賣出"
            action = "SELL"
        else:
            signal = "持有"
            action = "HOLD"
        
        detail = "，".join(detail_parts) if detail_parts else f"區間震盪，ATR({atr[-1]:.2f})"
        
        return {
            'name': self.name,
            'signal': signal,
            'score': score,
            'action': action,
            'detail': detail
        }
    
    def _calculate_atr(self, highs, lows, closes, period=14):
        tr = np.zeros(len(highs))
        for i in range(1, len(highs)):
            tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        return tr
    
    def _calculate_bollinger_bands(self, closes, period=20):
        ma = np.mean(closes[-period:])
        std = np.std(closes[-period:])
        return ma + 2 * std, ma, ma - 2 * std
    
    def _default_result(self):
        return {'name': self.name, 'signal': '持有', 'score': 50, 'action': 'HOLD', 'detail': '數據不足'}


class SentimentModel:
    """模型 4: 市場情緒模型"""
    
    def __init__(self):
        self.name = "💰 市場情緒"
    
    def analyze(self, hist):
        if hist.empty or len(hist) < 20:
            return self._default_result()
        
        closes = hist['Close'].values
        volumes = hist['Volume'].values
        
        current_price = closes[-1]
        current_volume = volumes[-1]
        
        price_change = (closes[-1] - closes[-2]) / closes[-2] * 100 if len(closes) > 1 else 0
        
        avg_volume = np.mean(volumes[-20:])
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
        
        obv = self._calculate_obv(closes, volumes)
        obv_trend = "上升" if len(obv) > 5 and obv[-1] > obv[-5] else "下降"
        
        score = 50
        detail_parts = []
        
        if volume_ratio > 1.5 and price_change > 0:
            score += 15
            detail_parts.append(f"放量上漲(量比{volume_ratio:.2f})")
        elif volume_ratio > 1.5 and price_change < 0:
            score -= 15
            detail_parts.append(f"放量下跌(量比{volume_ratio:.2f})")
        elif volume_ratio < 0.5:
            detail_parts.append("縮量整理")
        
        if obv_trend == "上升" and price_change > 0:
            score += 10
            detail_parts.append("OBV上升，資金流入")
        elif obv_trend == "下降" and price_change < 0:
            score -= 10
            detail_parts.append("OBV下降，資金流出")
        
        score = max(0, min(100, score))
        
        if score >= 70:
            signal = "買入"
            action = "BUY"
        elif score <= 30:
            signal = "賣出"
            action = "SELL"
        else:
            signal = "持有"
            action = "HOLD"
        
        detail = "，".join(detail_parts) if detail_parts else f"量比{volume_ratio:.2f}，正常"
        
        return {
            'name': self.name,
            'signal': signal,
            'score': score,
            'action': action,
            'detail': detail
        }
    
    def _calculate_obv(self, closes, volumes):
        obv = [0]
        for i in range(1, len(closes)):
            if closes[i] > closes[i-1]:
                obv.append(obv[-1] + volumes[i])
            elif closes[i] < closes[i-1]:
                obv.append(obv[-1] - volumes[i])
            else:
                obv.append(obv[-1])
        return obv
    
    def _default_result(self):
        return {'name': self.name, 'signal': '持有', 'score': 50, 'action': 'HOLD', 'detail': '數據不足'}


class AIStockPredictor:
    """AI 股票預測器 - 多模型融合"""
    
    def __init__(self):
        self.models = [
            TrendModel(),
            MomentumModel(),
            VolatilityModel(),
            SentimentModel()
        ]
    
    def predict(self, hist):
        """綜合預測"""
        if hist.empty or len(hist) < 30:
            return self._default_prediction()
        
        predictions = []
        for model in self.models:
            result = model.analyze(hist)
            predictions.append(result)
        
        buy_votes = sum(1 for p in predictions if p['action'] == 'BUY')
        sell_votes = sum(1 for p in predictions if p['action'] == 'SELL')
        
        total_score = sum(p['score'] for p in predictions) / len(predictions)
        
        if buy_votes >= 3:
            final_action = "強烈買入"
            confidence = "高"
        elif buy_votes >= 2:
            final_action = "買入"
            confidence = "中"
        elif sell_votes >= 3:
            final_action = "強烈賣出"
            confidence = "高"
        elif sell_votes >= 2:
            final_action = "賣出"
            confidence = "中"
        else:
            final_action = "持有觀望"
            confidence = "低"
        
        return {
            'final_score': round(total_score, 1),
            'final_action': final_action,
            'confidence': confidence,
            'buy_votes': buy_votes,
            'sell_votes': sell_votes,
            'models': predictions
        }
    
    def _default_prediction(self):
        return {
            'final_score': 50,
            'final_action': '數據不足',
            'confidence': '低',
            'buy_votes': 0,
            'sell_votes': 0,
            'models': []
        }