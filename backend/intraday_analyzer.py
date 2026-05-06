"""
日內交易分析模組
提供 VWAP、累積 Delta、日內 K線等分析功能
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

try:
    from futu import *
    FUTU_AVAILABLE = True
except ImportError:
    FUTU_AVAILABLE = False
    print("[intraday_analyzer] futu not available - cloud mode")
import time

logger = logging.getLogger(__name__)


class IntradayAnalyzer:
    """日內交易分析器"""
    
    def __init__(self, quote_ctx):
        """
        初始化日內分析器
        
        Args:
            quote_ctx: 富途 OpenQuoteContext 實例
        """
        self.quote_ctx = quote_ctx
        self.subscribed_types = {}  # 記錄已訂閱的數據類型
    
    def _ensure_subscription(self, symbol, sub_type, timeout=5):
        """
        確保已訂閱指定數據類型
        
        Args:
            symbol: 股票代碼 (富途格式)
            sub_type: 訂閱類型 (SubType)
            timeout: 超時時間（秒）
        
        Returns:
            bool: 是否成功
        """
        cache_key = f"{symbol}_{sub_type}"
        
        # 檢查是否已訂閱
        if cache_key in self.subscribed_types:
            return True
        
        try:
            # 訂閱數據
            ret, err_msg = self.quote_ctx.subscribe([symbol], [sub_type])
            
            if ret != RET_OK:
                logger.warning(f"訂閱 {symbol} {sub_type} 失敗: {err_msg}")
                return False
            
            # 等待訂閱生效
            time.sleep(0.5)
            
            # 記錄已訂閱
            self.subscribed_types[cache_key] = True
            logger.info(f"成功訂閱 {symbol} {sub_type}")
            return True
            
        except Exception as e:
            logger.error(f"訂閱異常 {symbol}: {e}")
            return False
    
    def _convert_symbol(self, symbol):
        """轉換股票代碼為富途格式"""
        symbol = symbol.upper().strip()

        # HK.00700 前缀格式（富途格式直接输入）
        if symbol.startswith('HK.') and not symbol.endswith('.HK'):
            code = symbol[3:]
            if code.isdigit() and len(code) < 5:
                code = code.zfill(5)
            return f"HK.{code}"

        # 00700.HK 后缀格式（Yahoo/Tushare 风格）
        if symbol.endswith('.HK'):
            code = symbol.replace('.HK', '')
            if code.isdigit() and len(code) < 5:
                code = code.zfill(5)
            return f"HK.{code}"

        # 纯数字 — 默认港股
        if symbol.isdigit():
            code = symbol.zfill(5)
            return f"HK.{code}"

        if symbol.isalpha():
            return f"US.{symbol}"

        return symbol
    
    def get_intraday_kline(self, symbol, period='15m', days=5):
        """
        獲取日內 K線數據
        
        Args:
            symbol: 股票代碼 (如 '0700.HK')
            period: K線週期 ('1m', '5m', '15m', '30m', '60m')
            days: 獲取天數 (預設 5 天)
        
        Returns:
            list: K線數據列表，格式 [{x: timestamp, y: [open, high, low, close]}]
        """
        try:
            futu_symbol = self._convert_symbol(symbol)
            
            # 轉換 K線類型
            ktype_map = {
                '1m': KLType.K_1M,
                '5m': KLType.K_5M,
                '15m': KLType.K_15M,
                '30m': KLType.K_30M,
                '60m': KLType.K_60M,
            }
            ktype = ktype_map.get(period, KLType.K_15M)
            
            # 先訂閱對應的 K線數據
            if not self._ensure_subscription(futu_symbol, ktype):
                logger.warning(f"訂閱 {futu_symbol} {period} 失敗，嘗試使用歷史K線")
                # 如果訂閱失敗，嘗試使用歷史K線接口
                return self._get_history_kline(futu_symbol, period, days)
            
            # 計算獲取數量（每交易日約 6.5 小時 = 390 分鐘）
            num_map = {
                '1m': days * 390,
                '5m': days * 78,
                '15m': days * 26,
                '30m': days * 13,
                '60m': days * 7,
            }
            num = num_map.get(period, 100)
            
            # 獲取日內 K線
            ret, data = self.quote_ctx.get_cur_kline(futu_symbol, num=num, ktype=ktype)
            
            if ret != RET_OK:
                logger.warning(f"獲取日內 K線失敗: {data}")
                # 嘗試使用歷史K線
                return self._get_history_kline(futu_symbol, period, days)
            
            if data is None or data.empty:
                logger.warning(f"獲取日內 K線數據為空")
                return self._get_history_kline(futu_symbol, period, days)
            
            # 轉換為圖表格式
            result = []
            for _, row in data.iterrows():
                # 處理時間格式
                time_key = row['time_key']
                if hasattr(time_key, 'timestamp'):
                    timestamp = int(time_key.timestamp() * 1000)
                else:
                    timestamp = int(pd.Timestamp(time_key).timestamp() * 1000)
                
                result.append({
                    'x': timestamp,
                    'y': [
                        float(row['open']),
                        float(row['high']),
                        float(row['low']),
                        float(row['close'])
                    ]
                })
            
            logger.info(f"獲取 {symbol} 日內 K線成功，共 {len(result)} 條")
            return result
            
        except Exception as e:
            logger.error(f"獲取日內 K線錯誤 {symbol}: {e}")
            return []
    
    def _get_history_kline(self, futu_symbol, period='15m', days=5):
        """
        使用歷史K線接口獲取數據（備用方案）
        """
        try:
            # 轉換 K線類型
            ktype_map = {
                '1m': KLType.K_1M,
                '5m': KLType.K_5M,
                '15m': KLType.K_15M,
                '30m': KLType.K_30M,
                '60m': KLType.K_60M,
            }
            ktype = ktype_map.get(period, KLType.K_15M)
            
            # 計算開始日期
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # 獲取歷史K線
            ret, data = self.quote_ctx.request_history_kline(
                futu_symbol, 
                start=str(start_date.date()), 
                end=str(end_date.date()), 
                ktype=ktype
            )
            
            if ret != RET_OK or data.empty:
                logger.warning(f"獲取歷史K線失敗: {data if ret != RET_OK else 'empty'}")
                return []
            
            # 轉換為圖表格式
            result = []
            for _, row in data.iterrows():
                result.append({
                    'x': int(row['time_key'].timestamp() * 1000),
                    'y': [
                        float(row['open']),
                        float(row['high']),
                        float(row['low']),
                        float(row['close'])
                    ]
                })
            
            logger.info(f"使用歷史K線獲取成功，共 {len(result)} 條")
            return result
            
        except Exception as e:
            logger.error(f"獲取歷史K線失敗: {e}")
            return []
    
    def calculate_vwap(self, symbol, days=1):
        """
        計算 VWAP (成交量加權平均價)
        
        Args:
            symbol: 股票代碼
            days: 計算天數
        
        Returns:
            dict: VWAP 分析結果
        """
        try:
            futu_symbol = self._convert_symbol(symbol)
            
            # 訂閱 1分鐘 K線
            if not self._ensure_subscription(futu_symbol, KLType.K_1M):
                logger.warning(f"無法訂閱 {futu_symbol} 1分鐘K線")
                return self._calculate_vwap_from_15min(futu_symbol)
            
            # 獲取日內 K線 (1分鐘)
            ret, data = self.quote_ctx.get_cur_kline(futu_symbol, num=390, ktype=KLType.K_1M)
            
            if ret != RET_OK or data is None or data.empty:
                logger.warning("獲取1分鐘K線失敗，使用15分鐘K線計算VWAP")
                return self._calculate_vwap_from_15min(futu_symbol)
            
            # 計算 VWAP = Σ(典型價格 × 成交量) / Σ成交量
            typical_prices = (data['open'] + data['high'] + data['low'] + data['close']) / 4
            volume = data['volume']
            
            cumulative_pv = (typical_prices * volume).cumsum()
            cumulative_volume = volume.cumsum()
            vwap = cumulative_pv / cumulative_volume
            
            current_vwap = float(vwap.iloc[-1])
            current_price = float(data['close'].iloc[-1])
            
            # 判斷當前價格相對於 VWAP 的位置
            if current_price > current_vwap:
                position = "上方"
                signal = "偏多"
            elif current_price < current_vwap:
                position = "下方"
                signal = "偏空"
            else:
                position = "持平"
                signal = "中性"
            
            return {
                'vwap': round(current_vwap, 2),
                'position': position,
                'signal': signal,
                'deviation': round(((current_price - current_vwap) / current_vwap) * 100, 2)
            }
            
        except Exception as e:
            logger.error(f"計算 VWAP 失敗 {symbol}: {e}")
            return None
    
    def _calculate_vwap_from_15min(self, futu_symbol):
        """使用15分鐘K線計算VWAP（備用方案）"""
        try:
            ret, data = self.quote_ctx.get_cur_kline(futu_symbol, num=50, ktype=KLType.K_15M)
            
            if ret != RET_OK or data is None or data.empty:
                return None
            
            typical_prices = (data['open'] + data['high'] + data['low'] + data['close']) / 4
            volume = data['volume']
            
            cumulative_pv = (typical_prices * volume).cumsum()
            cumulative_volume = volume.cumsum()
            vwap = cumulative_pv / cumulative_volume
            
            current_vwap = float(vwap.iloc[-1])
            current_price = float(data['close'].iloc[-1])
            
            if current_price > current_vwap:
                position = "上方"
                signal = "偏多"
            elif current_price < current_vwap:
                position = "下方"
                signal = "偏空"
            else:
                position = "持平"
                signal = "中性"
            
            return {
                'vwap': round(current_vwap, 2),
                'position': position,
                'signal': signal,
                'deviation': round(((current_price - current_vwap) / current_vwap) * 100, 2)
            }
            
        except Exception as e:
            logger.error(f"15分鐘K線計算VWAP失敗: {e}")
            return None
    
    def calculate_intraday_indicators(self, symbol):
        """
        計算日內技術指標
        
        Args:
            symbol: 股票代碼
        
        Returns:
            dict: 技術指標結果
        """
        try:
            futu_symbol = self._convert_symbol(symbol)
            
            # 訂閱 15分鐘 K線
            self._ensure_subscription(futu_symbol, KLType.K_15M)
            
            # 獲取 15分鐘 K線數據（用於計算指標）
            ret, data = self.quote_ctx.get_cur_kline(futu_symbol, num=100, ktype=KLType.K_15M)
            
            if ret != RET_OK or data is None or data.empty:
                logger.warning(f"獲取15分鐘K線失敗，使用默認值")
                return self._get_default_indicators()
            
            closes = data['close'].astype(float).values
            highs = data['high'].astype(float).values
            lows = data['low'].astype(float).values
            volumes = data['volume'].astype(float).values
            
            current_price = closes[-1]
            current_volume = volumes[-1]
            
            # 1. VWAP
            vwap_result = self.calculate_vwap(symbol)
            
            # 2. RSI(7) - 短週期 RSI
            rsi7 = self._calculate_rsi(closes, 7)
            
            # 3. 布林帶 (20,2)
            bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(closes, 20)
            bb_position = "中軌附近"
            bb_signal = "正常"
            
            if current_price > bb_upper:
                bb_position = "突破上軌"
                bb_signal = "超買"
            elif current_price < bb_lower:
                bb_position = "跌破下軌"
                bb_signal = "超賣"
            
            # 4. 資金流向 (富途 get_capital_flow)
            capital_flow = self._get_real_capital_flow(symbol)
            
            # 5. ATR(5)
            atr5 = self._calculate_atr(highs, lows, closes, 5)
            
            # 6. 動量 (最近 5 根 K線)
            momentum = ((closes[-1] - closes[-5]) / closes[-5]) * 100 if len(closes) >= 5 else 0

             # 7. ATR 信號 - 修復這裡的錯誤
            atr_signal = '正常波動'
            if len(closes) >= 10:
                avg_atr = np.mean([self._calculate_atr(highs[:i+5], lows[:i+5], closes[:i+5], 5) for i in range(5, min(15, len(closes)))]) if len(closes) > 10 else atr5
                if atr5 > avg_atr * 1.2:
                    atr_signal = '高波動'
                elif atr5 < avg_atr * 0.8:
                    atr_signal = '低波動'
            
            return {
                'vwap': vwap_result['vwap'] if vwap_result else current_price,
                'vwap_signal': vwap_result['signal'] if vwap_result else '--',
                'vwap_position': vwap_result['position'] if vwap_result else '--',
                'rsi7': round(rsi7, 1),
                'bb_position': bb_position,
                'bb_signal': bb_signal,
                'bb_upper': round(bb_upper, 2),
                'bb_middle': round(bb_middle, 2),
                'bb_lower': round(bb_lower, 2),
                'delta': capital_flow['value'],
                'delta_signal': capital_flow['signal'],
                'capital_flow': capital_flow['value'],
                'capital_flow_signal': capital_flow['signal'],
                'capital_flow_details': capital_flow.get('details', {}),
                'atr5': round(atr5, 2),
                'atr_signal': atr_signal,
                'momentum': round(momentum, 2),
                'momentum_signal': '強動能' if momentum > 1 else '弱動能' if momentum < -1 else '平穩',
                'current_price': current_price,
                'current_volume': current_volume
            }
            
        except Exception as e:
            logger.error(f"計算日內指標失敗 {symbol}: {e}")
            return self._get_default_indicators()
    
    def _calculate_rsi(self, closes, period=14):
        """計算 RSI"""
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
        """計算布林帶"""
        if len(closes) < period:
            return closes[-1], closes[-1], closes[-1]
        ma = np.mean(closes[-period:])
        std = np.std(closes[-period:])
        return ma + 2 * std, ma, ma - 2 * std
    
    def _calculate_atr(self, highs, lows, closes, period=14):
        """計算 ATR"""
        if len(highs) < period + 1:
            return 0
        tr = np.zeros(len(highs))
        for i in range(1, len(highs)):
            tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        return np.mean(tr[-period:])
    
    def _get_real_capital_flow(self, symbol):
        """
        獲取真實資金流向 (富途 get_capital_flow API)
        返回: {value, signal, details: {super, big, mid, sml}}
        """
        try:
            futu_symbol = self._convert_symbol(symbol)
            ret, data = self.quote_ctx.get_capital_flow(futu_symbol, period_type=PeriodType.INTRADAY)
            if ret == RET_OK and not data.empty:
                # 取最新一條
                latest = data.iloc[-1]
                in_flow = float(latest['in_flow'])
                details = {
                    'super': float(latest.get('super_in_flow', 0)),
                    'big': float(latest.get('big_in_flow', 0)),
                    'mid': float(latest.get('mid_in_flow', 0)),
                    'sml': float(latest.get('sml_in_flow', 0)),
                }

                # 格式化顯示
                if abs(in_flow) >= 1e9:
                    value = f"{'+' if in_flow > 0 else ''}{in_flow/1e9:.1f}B"
                elif abs(in_flow) >= 1e6:
                    value = f"{'+' if in_flow > 0 else ''}{in_flow/1e6:.1f}M"
                elif abs(in_flow) >= 1e3:
                    value = f"{'+' if in_flow > 0 else ''}{in_flow/1e3:.1f}K"
                else:
                    value = f"{'+' if in_flow > 0 else ''}{in_flow:.0f}"

                signal = "正流入" if in_flow > 0 else "負流出" if in_flow < 0 else "中性"
                return {'value': value, 'signal': signal, 'details': details}
        except Exception as e:
            logger.warning(f'獲取資金流向失敗 {symbol}: {e}')

        return {'value': '--', 'signal': '中性', 'details': {}}
    
    def get_order_book(self, symbol, num=10):
        """
        獲取 Level 2 盤口數據 (需要 Level 2 權限)
        
        Args:
            symbol: 股票代碼
            num: 掛單檔數
        
        Returns:
            dict: 買盤和賣盤數據
        """
        try:
            futu_symbol = self._convert_symbol(symbol)
            
            # 訂閱盤口數據
            self._ensure_subscription(futu_symbol, SubType.ORDER_BOOK)
            
            ret, data = self.quote_ctx.get_order_book(futu_symbol, num=num)
            
            if ret != RET_OK or data is None or data.empty:
                return None
            
            bid_data = []
            ask_data = []
            
            # 解析買盤和賣盤
            if 'Bid' in data.columns:
                for _, row in data.iterrows():
                    bid_data.append({
                        'price': float(row['Bid']),
                        'volume': int(row['Bid_vol']) if 'Bid_vol' in data.columns else 0
                    })
            
            if 'Ask' in data.columns:
                for _, row in data.iterrows():
                    ask_data.append({
                        'price': float(row['Ask']),
                        'volume': int(row['Ask_vol']) if 'Ask_vol' in data.columns else 0
                    })
            
            return {
                'bids': bid_data[:num],
                'asks': ask_data[:num],
                'bid_volume': sum(b['volume'] for b in bid_data),
                'ask_volume': sum(a['volume'] for a in ask_data),
                'imbalance': sum(b['volume'] for b in bid_data) - sum(a['volume'] for a in ask_data)
            }
            
        except Exception as e:
            logger.error(f"獲取盤口數據失敗 {symbol}: {e}")
            return None
    
    def get_realtime_ticker(self, symbol, num=100):
        """
        獲取即時 Tick 數據 (需要 Level 2 權限)
        
        Args:
            symbol: 股票代碼
            num: Tick 數量
        
        Returns:
            list: Tick 數據列表
        """
        try:
            futu_symbol = self._convert_symbol(symbol)
            
            # 訂閱 Tick 數據
            self._ensure_subscription(futu_symbol, SubType.TICKER)
            
            ret, data = self.quote_ctx.get_rt_ticker(futu_symbol, num=num)
            
            if ret != RET_OK or data is None or data.empty:
                return []
            
            result = []
            for _, row in data.iterrows():
                result.append({
                    'time': row['time'],
                    'price': float(row['price']),
                    'volume': int(row['volume']),
                    'ticker_direction': row.get('ticker_direction', 'NEUTRAL')
                })
            
            return result
            
        except Exception as e:
            logger.error(f"獲取 Tick 數據失敗 {symbol}: {e}")
            return []
    
    def _get_default_indicators(self):
        """獲取默認指標值"""
        return {
            'vwap': None,
            'vwap_signal': '--',
            'vwap_position': '--',
            'rsi7': 50,
            'bb_position': '中軌附近',
            'bb_signal': '正常',
            'bb_upper': 0,
            'bb_middle': 0,
            'bb_lower': 0,
            'delta': '--',
            'delta_signal': '中性',
            'capital_flow': '--',
            'capital_flow_signal': '中性',
            'capital_flow_details': {},
            'atr5': 0,
            'atr_signal': '正常波動',
            'momentum': 0,
            'momentum_signal': '平穩',
            'current_price': 0,
            'current_volume': 0
        }