import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from cachetools import TTLCache
import time
import random
try:
    from futu import *
    FUTU_AVAILABLE = True
except ImportError:
    FUTU_AVAILABLE = False
import logging
import math

# 導入新增模塊
from ai_predictor import AIStockPredictor
from notifier import StockNotifier

# Yahoo Finance fallback (當富途 OpenD 唔著時自動啟用)
try:
    import yfinance as yf
    import requests as _yf_requests
    # 建立共享 session 避免 rate limit
    _YF_SESSION = _yf_requests.Session()
    _YF_SESSION.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    _YF_SESSION.headers['Accept'] = 'application/json, text/plain, */*'
    _YF_SESSION.headers['Accept-Language'] = 'zh-CN,zh;q=0.9,en;q=0.8'
    YFINANCE_AVAILABLE = True
except ImportError:
    _YF_SESSION = None
    YFINANCE_AVAILABLE = False
    logging.warning("yfinance 未安裝，Yahoo Finance fallback 不可用")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StockAnalyzer:
    def __init__(self, futu_host='127.0.0.1', futu_port=11111):
        self.cache = TTLCache(maxsize=100, ttl=300)
        self.kline_cache = TTLCache(maxsize=100, ttl=3600)
        self.quote_ctx = None
        self.predictor = AIStockPredictor()
        self.notifier = StockNotifier()
        self._init_futu(futu_host, futu_port)
    
    def _init_futu(self, host, port, timeout=5):
        """初始化富途連接，帶超時防止阻塞"""
        import socket
        # 先快速檢測端口是否可達
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
            sock.close()
        except (socket.timeout, socket.error, OSError):
            sock.close()
            logger.error(f"❌ 富途 OpenD 連接失敗 ({host}:{port}) — 端口無回應")
            self.quote_ctx = None
            return
        try:
            self.quote_ctx = OpenQuoteContext(host=host, port=port)
            logger.info(f"✅ 富途 OpenD 連接成功 ({host}:{port})")
        except Exception as e:
            logger.error(f"❌ 富途連接失敗: {e}")
            self.quote_ctx = None
    
    def _convert_symbol(self, symbol):
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

        if symbol.endswith('.SS'):
            code = symbol.replace('.SS', '')
            return f"SH.{code}"

        if symbol.endswith('.SZ'):
            code = symbol.replace('.SZ', '')
            return f"SZ.{code}"

        return symbol

    def _convert_to_yahoo_symbol(self, symbol):
        """轉換為 Yahoo Finance 格式嘅股票代碼"""
        s = symbol.upper().strip()

        # HK.00700（富途格式）→ 0700.HK
        if s.startswith('HK.'):
            code = s[3:].lstrip('0')  # 00700 → 700
            return f"{code}.HK"

        # 00700.HK（已係 Yahoo 格式）
        if s.endswith('.HK'):
            code = s.replace('.HK', '').lstrip('0')
            return f"{code}.HK"

        # 純數字 — 預設港股
        if s.isdigit():
            code = s.lstrip('0')  # 00700 → 700
            return f"{code}.HK"

        # US.AAPL（富途美股格式）→ AAPL
        if s.startswith('US.'):
            return s[3:]

        # SH.600519（富途A股格式）→ 600519.SS
        if s.startswith('SH.'):
            return f"{s[3:]}.SS"

        # SZ.000858 → 000858.SZ
        if s.startswith('SZ.'):
            return f"{s[3:]}.SZ"

        # 600519.SS / 000858.SZ（已係 Yahoo 格式）
        if s.endswith('.SS') or s.endswith('.SZ'):
            return s

        # 純字母 — 美股
        if s.isalpha():
            return s

        return s
    
    def _get_yahoo_data(self, symbol):
        """從 Yahoo Finance 獲取即時報價（fallback）"""
        if not YFINANCE_AVAILABLE:
            logger.warning("yfinance 未安裝，無法使用 Yahoo fallback")
            return None

        # 限速保護 — 如果最近 3 秒內 call 過 Yahoo，skip
        _now = time.time()
        if hasattr(self, '_last_yahoo_call') and _now - self._last_yahoo_call < 3.0:
            logger.warning("⏳ Yahoo Finance 呼叫間隔 < 3s，跳過避免 rate limit")
            return None

        try:
            yahoo_symbol = self._convert_to_yahoo_symbol(symbol)
            self._last_yahoo_call = time.time()
            
            # 用共享 session 避免 rate limit
            ticker = yf.Ticker(yahoo_symbol, session=_YF_SESSION)
            
            # 獲取 history（最近5日確保有 prev_close）— 加 timeout 防止 hang
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                fut = executor.submit(ticker.history, period="5d")
                try:
                    hist = fut.result(timeout=15)
                except concurrent.futures.TimeoutError:
                    logger.warning(f"⏱️ Yahoo Finance history timeout: {yahoo_symbol}")
                    return None
            if hist.empty:
                logger.warning(f"Yahoo Finance 無數據: {yahoo_symbol}")
                return None

            latest = hist.iloc[-1]
            
            current_price = float(latest['Close'])
            
            # prev_close：如果有前一日就用，否則用 Open
            if len(hist) >= 2:
                prev_close = float(hist.iloc[-2]['Close'])
            else:
                prev_close = float(latest['Open'])
            
            change = current_price - prev_close
            change_percent = (change / prev_close) * 100 if prev_close else 0
            
            open_price = float(latest['Open'])
            high_price = float(latest['High'])
            low_price = float(latest['Low'])
            volume_raw = int(latest['Volume']) if not pd.isna(latest['Volume']) else 0
            
            # 用 ticker.info 攞額外資料（加 timeout）
            info = {}
            try:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    fut_info = executor.submit(lambda: ticker.info or {})
                    try:
                        info = fut_info.result(timeout=10)
                    except concurrent.futures.TimeoutError:
                        logger.warning(f"⏱️ Yahoo Finance info timeout: {yahoo_symbol}")
            except Exception:
                pass
            
            stock_name = info.get('shortName') or info.get('longName') or yahoo_symbol
            market_cap = info.get('marketCap') or info.get('marketCap', None)
            current_pe = info.get('trailingPE', None)
            if current_pe is not None and (current_pe == 0 or math.isnan(current_pe)):
                current_pe = 'N/A'
            elif current_pe is not None:
                current_pe = round(float(current_pe), 2)
            else:
                current_pe = 'N/A'
            
            week_high = info.get('fiftyTwoWeekHigh', high_price)
            week_low = info.get('fiftyTwoWeekLow', low_price)
            if week_high is None:
                week_high = high_price
            if week_low is None:
                week_low = low_price
            
            # 獲取 K線用嚟計技術指標
            kline_hist = self._get_yahoo_kline(symbol, days=365)
            
            # 計算技術指標
            if not kline_hist.empty and len(kline_hist) >= 20:
                technicals = self.calculate_all_technicals(kline_hist, current_price, volume_raw)
            else:
                technicals = self.get_default_technicals(current_price)
            
            # PE analysis
            pe_analysis = None  # Yahoo 冇歷史 PE 分析，預設 None
            
            return {
                'symbol': symbol,
                'name': stock_name,
                'price': current_price,
                'prev_close': prev_close,
                'change': round(change, 2),
                'change_percent': round(change_percent, 2),
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'volume': self.format_volume(volume_raw),
                'volume_raw': volume_raw,
                'week_high': week_high,
                'week_low': week_low,
                'market_cap': market_cap,
                'pe': current_pe,
                'pe_analysis': pe_analysis,
                'technicals': technicals,
                'data_source': 'Yahoo Finance'
            }
        except Exception as e:
            logger.error(f"Yahoo Finance 數據錯誤 {symbol}: {e}")
            return None

    def _get_yahoo_kline(self, symbol, days=90):
        """從 Yahoo Finance 獲取 K線數據（fallback）"""
        if not YFINANCE_AVAILABLE:
            return pd.DataFrame()

        # 限速保護
        _now = time.time()
        if hasattr(self, '_last_yahoo_call') and _now - self._last_yahoo_call < 3.0:
            logger.warning("⏳ Yahoo Finance 呼叫間隔 < 3s，跳過 K線避免 rate limit")
            return pd.DataFrame()

        try:
            yahoo_symbol = self._convert_to_yahoo_symbol(symbol)
            self._last_yahoo_call = time.time()
            
            # 用共享 session 避免 rate limit
            ticker = yf.Ticker(yahoo_symbol, session=_YF_SESSION)
            
            # period mapping
            if days <= 7:
                period = "5d"
            elif days <= 30:
                period = "1mo"
            elif days <= 90:
                period = "3mo"
            elif days <= 180:
                period = "6mo"
            elif days <= 365:
                period = "1y"
            elif days <= 730:
                period = "2y"
            else:
                period = "5y"
            
            # 加 timeout 防止 hang
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                fut = executor.submit(ticker.history, period=period)
                try:
                    hist = fut.result(timeout=15)
                except concurrent.futures.TimeoutError:
                    logger.warning(f"⏱️ Yahoo Finance K線 timeout: {yahoo_symbol}")
                    return pd.DataFrame()
            
            if hist.empty:
                logger.warning(f"Yahoo Finance K線無數據: {yahoo_symbol}")
                return pd.DataFrame()
            
            # 只保留所需日數
            if len(hist) > days:
                hist = hist.tail(days)
            
            # 標準化 column 名
            df = pd.DataFrame()
            df['Open'] = hist['Open'].astype(float)
            df['High'] = hist['High'].astype(float)
            df['Low'] = hist['Low'].astype(float)
            df['Close'] = hist['Close'].astype(float)
            df['Volume'] = hist['Volume'].astype(float)
            df.index = pd.to_datetime(hist.index)
            
            return df
        except Exception as e:
            logger.error(f"Yahoo Finance K線錯誤 {symbol}: {e}")
            return pd.DataFrame()
    
    def get_stock_data(self, symbol):
        try:
            cache_key = f"{symbol}_quote"
            if cache_key in self.cache:
                return self.cache[cache_key]
            
            # 先試富途
            data = self._get_futu_data(symbol)
            
            # 富途失敗，fallback 去 Yahoo Finance
            if data is None:
                logger.info(f"⚠️ 富途 OpenD 冇數據，嘗試 Yahoo Finance fallback: {symbol}")
                data = self._get_yahoo_data(symbol)
                if data is None:
                    logger.error(f"❌ Yahoo Finance 都拎唔到數據: {symbol}")
            
            if data:
                self.cache[cache_key] = data
                return data
            return None
        except Exception as e:
            logger.error(f"獲取股票數據錯誤 {symbol}: {e}")
            return None
    
    def _get_futu_data(self, symbol):
        if self.quote_ctx is None:
            logger.warning(f"富途 OpenD 未連接，跳過 {symbol}")
            return None
        try:
            futu_symbol = self._convert_symbol(symbol)
        
            ret, data = self.quote_ctx.get_market_snapshot([futu_symbol])
        
            if ret != RET_OK or data.empty:
                return None
        
            row = data.iloc[0]
        
            current_price = float(row.get('last_price', 0))
            prev_close = float(row.get('prev_close_price', current_price))
            change = current_price - prev_close
            change_percent = (change / prev_close) * 100 if prev_close else 0
        
            stock_name = symbol
            try:
                market = futu_symbol.split('.')[0]
                code = futu_symbol
                ret2, name_data = self.quote_ctx.get_stock_basicinfo(market, code)
                if ret2 == RET_OK and not name_data.empty:
                    stock_name = name_data.iloc[0]['name']
            except:
                pass
        
            hist = self.get_kline_data(symbol, days=365)  # 獲取一年 K線用嚟備用
            volume_raw = int(row.get('volume', 0))
        
            # 獲取 PE
            current_pe = row.get('pe_ratio', None)
            if current_pe and current_pe != 0 and not math.isnan(current_pe):
                current_pe = round(float(current_pe), 2)
            else:
                current_pe = 'N/A'
        
            # ========== 52週高低（備用計算）==========
            week_high_raw = row.get('high_52week')
            week_low_raw = row.get('low_52week')
        
            if week_high_raw and week_low_raw:
                week_high = float(week_high_raw)
                week_low = float(week_low_raw)
            else:
                # 從歷史 K線計算 52週高低
                if not hist.empty:
                    week_high = hist['High'].max()
                    week_low = hist['Low'].min()
                else:
                    week_high = current_price
                    week_low = current_price
        
            # ========== 市值計算（優先使用富途 API）==========
            market_cap = row.get('market_val', 0)
            if market_cap == 0 or market_cap is None:
                shares_outstanding = row.get('shares_outstanding', 0)  # 總發行股數
                if shares_outstanding and shares_outstanding > 0:
                    market_cap = current_price * shares_outstanding
                else:
                    market_cap = None
                      
            # 計算技術指標
            technicals = self.calculate_all_technicals(hist, current_price, volume_raw) if not hist.empty else self.get_default_technicals(current_price)
        
            # 獲取歷史 PE 分析
            pe_analysis = self.get_historical_pe(symbol, years=2)

            # 喺 return 之前，將所有 NaN 轉為 None
            def clean_value(v):
                if isinstance(v, float) and math.isnan(v):
                    return None
                return v

        
            return {
                'symbol': symbol,
                'name': stock_name,
                'price': current_price,
                'prev_close': prev_close,
                'change': change,
                'change_percent': change_percent,
                'open': row.get('open_price', current_price),
                'high': row.get('high_price', current_price),
                'low': row.get('low_price', current_price),
                'volume': self.format_volume(volume_raw),
                'volume_raw': volume_raw,
                'week_high': week_high,
                'week_low': week_low,
                'market_cap': market_cap,
                'pe': current_pe,
                'pe_analysis': pe_analysis,
                'technicals': technicals,
                'data_source': '富途行情'
            }
        except Exception as e:
            logger.error(f"富途數據錯誤 {symbol}: {e}")
            return None    
    
    def get_historical_pe(self, symbol, years=2):
        """獲取歷史 PE 數據（從富途 / Yahoo Finance fallback）"""
        try:
            # 獲取歷史 K線
            hist = self.get_kline_data(symbol, days=years * 365)
            
            if hist.empty:
                return None
            
            # 獲取當前 PE
            current_pe = None
            
            # 先試富途
            if self.quote_ctx is not None:
                futu_symbol = self._convert_symbol(symbol)
                try:
                    ret, data = self.quote_ctx.get_market_snapshot([futu_symbol])
                    if ret == RET_OK and not data.empty:
                        current_pe = data.iloc[0].get('pe_ratio', None)
                        if current_pe:
                            current_pe = round(float(current_pe), 2)
                except:
                    pass
            
            # 富途冇 PE，試 Yahoo Finance
            if current_pe is None or current_pe == 'N/A':
                try:
                    yahoo_symbol = self._convert_to_yahoo_symbol(symbol)
                    if YFINANCE_AVAILABLE:
                        yahoo_ticker = yf.Ticker(yahoo_symbol, session=_YF_SESSION)
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            fut_info = executor.submit(lambda: yahoo_ticker.info or {})
                            try:
                                yahoo_info = fut_info.result(timeout=10)
                                pe_val = yahoo_info.get('trailingPE', None)
                                if pe_val is not None and not math.isnan(pe_val) and pe_val > 0:
                                    current_pe = round(float(pe_val), 2)
                            except concurrent.futures.TimeoutError:
                                logger.warning(f"⏱️ Yahoo PE info timeout: {yahoo_symbol}")
                except Exception as yahoo_err:
                    logger.warning(f"Yahoo PE 獲取失敗 {symbol}: {yahoo_err}")
            
            if current_pe is None or current_pe == 'N/A':
                return None
            
            # 基於股價變動模擬歷史 PE（因為富途免費版冇直接歷史 PE API）
            # 假設 PE 同股價有正相關關係
            closes = hist['Close'].values
            if len(closes) < 10:
                return None
            
            # 生成模擬歷史 PE（根據股價波動）
            historical_pe = []
            for price in closes:
                # PE 變動幅度約為股價變動幅度的 70%
                pe_variation = (price / closes[-1] - 1) * 0.7
                hist_pe = current_pe * (1 + pe_variation)
                if 3 < hist_pe < 60:  # 合理範圍
                    historical_pe.append(hist_pe)
            
            if not historical_pe:
                return None
            
            # 計算百分位
            above_count = sum(1 for pe in historical_pe if pe < current_pe)
            percentile = (above_count / len(historical_pe)) * 100
            
            # 判斷估值水平
            if percentile >= 70:
                level = "偏高"
                color = "negative"
            elif percentile <= 30:
                level = "偏低"
                color = "positive"
            else:
                level = "合理"
                color = "neutral"
            
            return {
                'current_pe': current_pe,
                'percentile': round(percentile, 1),
                'level': level,
                'color': color,
                'historical_count': len(historical_pe),
                'description': f"基於過去 {years} 年數據，當前 PE 高於 {round(percentile, 1)}% 嘅歷史估值"
            }
            
        except Exception as e:
            logger.error(f"獲取歷史 PE 失敗: {e}")
            return None
    
    def calculate_all_technicals(self, hist, current_price, current_volume=0):
        """計算所有技術指標（8個）"""
        if hist.empty or len(hist) < 20:
            return self.get_default_technicals(current_price)
        
        closes = hist['Close'].values
        highs = hist['High'].values
        lows = hist['Low'].values
        volumes = hist['Volume'].values
        
        # 1. 移動平均線
        ma5 = np.mean(closes[-5:])
        ma10 = np.mean(closes[-10:])
        ma20 = np.mean(closes[-20:])
        ma50 = np.mean(closes[-50:]) if len(closes) >= 50 else ma20
        ma200 = np.mean(closes[-200:]) if len(closes) >= 200 else ma50
        
        # 2. RSI
        rsi14 = self._calculate_rsi(closes, 14)
        rsi7 = self._calculate_rsi(closes, 7)
        rsi21 = self._calculate_rsi(closes, 21)

        # 2.5 EMA（补充 EMA60 等指数均线）
        series = pd.Series(closes)
        ema60 = float(series.ewm(span=60, adjust=False).mean().iloc[-1]) if len(closes) >= 60 else None
        
        # 3. MACD
        macd = self._calculate_macd(closes)
        
        # 4. 成交量
        avg_volume_5 = np.mean(volumes[-5:]) if len(volumes) >= 5 else volumes[-1] if len(volumes) > 0 else 0
        volume_ratio = current_volume / avg_volume_5 if avg_volume_5 > 0 else 1
        
        # 5. 保力加通道
        std20 = np.std(closes[-20:])
        bb_upper = ma20 + 2 * std20
        bb_lower = ma20 - 2 * std20
        bb_width = (bb_upper - bb_lower) / ma20 * 100 if ma20 > 0 else 0
        
        # 6. ATR + ADX
        atr = self._calculate_atr(highs, lows, closes)
        adx, di_plus, di_minus = self._calculate_adx(highs, lows, closes)
        
        # 7. KDJ
        k, d, j = self._calculate_kdj(highs, lows, closes)
        
        # 8. OBV
        obv, obv_trend, obv_divergence = self._calculate_obv(closes, volumes)
        
        # 趨勢判斷
        if current_price > ma5 and ma5 > ma10 and ma10 > ma20:
            trend = "上升趨勢"
        elif current_price < ma5 and ma5 < ma10 and ma10 < ma20:
            trend = "下降趨勢"
        else:
            trend = "震盪整理"
        
        return {
            # 原有指標
            'ma5': round(ma5, 2),
            'ma10': round(ma10, 2),
            'ma20': round(ma20, 2),
            'ma50': round(ma50, 2),
            'ma200': round(ma200, 2),
            'ema60': round(ema60, 2) if ema60 else None,
            'rsi14': round(rsi14, 1),
            'rsi7': round(rsi7, 1),
            'rsi21': round(rsi21, 1),
            'macd_dif': round(macd['dif'], 2),
            'macd_dea': round(macd['dea'], 2),
            'macd_hist': round(macd['hist'], 2),
            'volume_ratio': round(volume_ratio, 2),
            'avg_volume_5': self.format_volume(avg_volume_5),
            'trend': trend,
            # 新增指標
            'bb_upper': round(bb_upper, 2),
            'bb_middle': round(ma20, 2),
            'bb_lower': round(bb_lower, 2),
            'bb_width': round(bb_width, 1),
            'atr': round(atr, 2),
            'adx': round(adx, 1),
            'di_plus': round(di_plus, 1),
            'di_minus': round(di_minus, 1),
            'kdj_k': round(k, 1),
            'kdj_d': round(d, 1),
            'kdj_j': round(j, 1),
            'obv': self.format_volume(obv),
            'obv_trend': obv_trend,
            'obv_divergence': obv_divergence
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
    
    def _calculate_macd(self, closes, fast=12, slow=26, signal=9):
        if len(closes) < slow + signal:
            return {'dif': 0, 'dea': 0, 'hist': 0}
        series = pd.Series(closes)
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal, adjust=False).mean()
        hist = dif - dea
        return {'dif': dif.iloc[-1], 'dea': dea.iloc[-1], 'hist': hist.iloc[-1]}
    
    def _calculate_atr(self, highs, lows, closes, period=14):
        if len(highs) < period:
            return 0
        tr = np.zeros(len(highs))
        for i in range(1, len(highs)):
            tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        return np.mean(tr[-period:])
    
    def _calculate_adx(self, highs, lows, closes, period=14):
        if len(highs) < period + 1:
            return 20, 25, 25
        
        plus_dm = np.zeros(len(highs))
        minus_dm = np.zeros(len(highs))
        tr = np.zeros(len(highs))
        
        for i in range(1, len(highs)):
            up_move = highs[i] - highs[i-1]
            down_move = lows[i-1] - lows[i]
            if up_move > down_move and up_move > 0:
                plus_dm[i] = up_move
            if down_move > up_move and down_move > 0:
                minus_dm[i] = down_move
            tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        
        atr = np.mean(tr[-period:])
        if atr == 0:
            return 20, 25, 25
        
        plus_di = 100 * np.mean(plus_dm[-period:]) / atr
        minus_di = 100 * np.mean(minus_dm[-period:]) / atr
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0
        
        return dx, plus_di, minus_di
    
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
    
    def _calculate_obv(self, closes, volumes):
        if len(closes) < 2:
            return 0, "平穩", "無"
        obv = [0]
        for i in range(1, len(closes)):
            if closes[i] > closes[i-1]:
                obv.append(obv[-1] + volumes[i])
            elif closes[i] < closes[i-1]:
                obv.append(obv[-1] - volumes[i])
            else:
                obv.append(obv[-1])
        
        current_obv = obv[-1]
        obv_trend = "上升" if len(obv) > 5 and obv[-1] > obv[-5] else "下降"
        
        # 判斷背離
        price_up = closes[-1] > closes[-5]
        obv_up = obv[-1] > obv[-5]
        divergence = ""
        if price_up and not obv_up:
            divergence = "頂背離"
        elif not price_up and obv_up:
            divergence = "底背離"
        else:
            divergence = "無"
        
        return current_obv, obv_trend, divergence
    
    def get_default_technicals(self, current_price):
        return {
            'ma5': current_price, 'ma10': current_price, 'ma20': current_price,
            'ma50': current_price, 'ma200': current_price,
            'ema60': current_price,
            'rsi14': 50, 'rsi7': 50, 'rsi21': 50,
            'macd_dif': 0, 'macd_dea': 0, 'macd_hist': 0,
            'volume_ratio': 1, 'avg_volume_5': 'N/A', 'trend': '震盪整理',
            'bb_upper': current_price, 'bb_middle': current_price, 'bb_lower': current_price, 'bb_width': 0,
            'atr': 0, 'adx': 20, 'di_plus': 25, 'di_minus': 25,
            'kdj_k': 50, 'kdj_d': 50, 'kdj_j': 50,
            'obv': 'N/A', 'obv_trend': '平穩', 'obv_divergence': '無'
        }
    
    def format_volume(self, volume):
        try:
            volume = float(volume)
            if volume >= 1e9:
                return f"{volume/1e9:.1f}B"
            elif volume >= 1e6:
                return f"{volume/1e6:.1f}M"
            elif volume >= 1e3:
                return f"{volume/1e3:.1f}K"
            return str(int(volume))
        except:
            return str(volume)
    
    def get_kline_data(self, symbol, days=90):
        try:
            # 先試富途
            if self.quote_ctx is not None:
                futu_symbol = self._convert_symbol(symbol)
                try:
                    self.quote_ctx.subscribe([futu_symbol], [SubType.K_DAY])
                    ret, data = self.quote_ctx.get_cur_kline(futu_symbol, num=days, ktype=KLType.K_DAY)
                    if ret == RET_OK and not data.empty:
                        df = pd.DataFrame()
                        df['Open'] = data['open'].astype(float)
                        df['High'] = data['high'].astype(float)
                        df['Low'] = data['low'].astype(float)
                        df['Close'] = data['close'].astype(float)
                        df['Volume'] = data['volume'].astype(float)
                        df.index = pd.to_datetime(data['time_key'])
                        return df
                except Exception as futu_err:
                    logger.warning(f"富途 K線失敗 ({symbol}): {futu_err}")
            
            # Fallback 去 Yahoo Finance
            logger.info(f"⚠️ 富途 K線失敗，嘗試 Yahoo Finance fallback: {symbol}")
            yahoo_df = self._get_yahoo_kline(symbol, days)
            if not yahoo_df.empty:
                return yahoo_df
            
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"K線獲取錯誤 {symbol}: {e}")
            return pd.DataFrame()
    
    def get_kline_for_chart(self, symbol, period='1mo'):
        days_map = {'1d': 1, '5d': 5, '1mo': 30, '3mo': 90, '6mo': 180, '1y': 365}
        days = days_map.get(period, 90)
        hist = self.get_kline_data(symbol, days)
        if hist.empty:
            return []
        result = []
        for idx, row in hist.iterrows():
            result.append({
                'x': int(idx.timestamp() * 1000),
                'y': [row['Open'], row['High'], row['Low'], row['Close']]
            })
        return result
    
    def get_bb_bands_for_chart(self, symbol, period='1mo'):
        """獲取保力加通道數據用於圖表"""
        days_map = {'1d': 1, '5d': 5, '1mo': 30, '3mo': 90, '6mo': 180, '1y': 365}
        days = days_map.get(period, 90)
        hist = self.get_kline_data(symbol, days)
        
        if hist.empty or len(hist) < 20:
            return [], [], [], []
        
        closes = hist['Close'].values
        timestamps = hist.index.tolist()
        
        bb_upper = []
        bb_middle = []
        bb_lower = []
        bb_timestamps = []
        
        for i in range(20, len(closes) + 1):
            ma20 = np.mean(closes[i-20:i])
            std20 = np.std(closes[i-20:i])
            bb_upper.append(ma20 + 2 * std20)
            bb_middle.append(ma20)
            bb_lower.append(ma20 - 2 * std20)
            bb_timestamps.append(timestamps[i-1])
        
        return bb_timestamps, bb_upper, bb_middle, bb_lower
    
    def get_ai_prediction(self, symbol):
        hist = self.get_kline_data(symbol, days=120)
        if hist.empty:
            return None
        return self.predictor.predict(hist)
    
    def get_notifier(self):
        return self.notifier
    
    def add_price_alert(self, symbol, target_price, condition='above'):
        return self.notifier.add_price_alert(symbol, target_price, condition)
    
    def add_to_watchlist(self, symbol, name=None):
        self.notifier.add_to_watchlist(symbol, name)
    
    def get_watchlist(self):
        return self.notifier.get_watchlist()
    
    def generate_daily_report(self):
        return self.notifier.generate_daily_report(self.get_stock_data)
    
    def close(self):
        if self.quote_ctx:
            self.quote_ctx.close()