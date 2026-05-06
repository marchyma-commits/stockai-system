# -*- coding: utf-8 -*-
"""
港股财务报表数据获取模块 v1.6D-Optimized

数据来源（按优先级）：
  1. 本地缓存（港交所披露易下载）- 秒开体验
  2. 富途 OpenD API - 估值指标优先

⚠️ 财务比率数据来源：港交所披露易（本地缓存）
⚠️ 估值指标由富途 OpenD API 提供

优化说明（v1.6D）：
- 删除 Yahoo Finance/东方财富 等网页下载功能
- 估值指标：富途 OpenD API 优先 → 本地数据备用
- 其他指标：直接从本地数据摄取
- 响应速度更快，秒开体验
"""

import requests
import json
import re
import time
import pickle
from datetime import datetime, timedelta
from pathlib import Path

# 禁用警告
requests.packages.urllib3.disable_warnings()

# 缓存目录
CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
CACHE_EXPIRY_HOURS = 24

# 本地财务数据存储路径 (与 auto_sync.py 共享)
LOCAL_DATA_DIR = Path("C:/Users/MarcoMa/stockai_data")
LOCAL_CACHE_DIR = LOCAL_DATA_DIR / "cache"

# 尝试导入高速缓存系统 v2.0 (借鉴 Claude Code 架构)
_FAST_CACHE_AVAILABLE = False
try:
    import sys
    sys.path.insert(0, str(LOCAL_DATA_DIR))
    from financial_cache_v2 import load_financial_data_fast, init_cache_system, get_cache_stats
    _FAST_CACHE_AVAILABLE = True
    # 启动时初始化高速缓存（后台预热）
    import threading
    def _warmup_cache():
        try:
            init_cache_system()
            print("✅ 高速缓存系统 v2.0 已就绪 (借鉴 Claude Code 架构)")
        except Exception as e:
            print(f"⚠️ 高速缓存初始化失败: {e}")
    threading.Thread(target=_warmup_cache, daemon=True).start()
except ImportError:
    print("ℹ️ 高速缓存模块不可用，使用传统磁盘读取")


def get_cache_path(stock_code, data_type):
    return CACHE_DIR / f"{stock_code}_{data_type}.pkl"


def decimal_to_percent(value):
    """
    将小数格式转换为百分比格式
    例如: 0.017 -> 1.7, -0.352 -> -35.2
    如果值已经是百分比格式（绝对值 > 1），则保持不变
    """
    if value is None:
        return None
    try:
        num = float(value)
        # 如果绝对值 <= 1，认为是小数格式，需要乘以 100
        # 如果绝对值 > 1，认为已经是百分比格式，保持不变
        if abs(num) <= 1:
            return round(num * 100, 2)
        return round(num, 2)
    except (ValueError, TypeError):
        return value


def _convert_growth_rates_in_cache(cached_data):
    """
    转换缓存数据中的同比增长率格式（小数 -> 百分比）
    用于兼容旧缓存数据
    """
    try:
        if cached_data and 'data' in cached_data:
            for item in cached_data['data']:
                if 'ratios' in item:
                    ratios = item['ratios']
                    if 'revenueGrowth' in ratios:
                        ratios['revenueGrowth'] = decimal_to_percent(ratios['revenueGrowth'])
                    if 'earningsGrowth' in ratios:
                        ratios['earningsGrowth'] = decimal_to_percent(ratios['earningsGrowth'])
    except Exception:
        pass  # 转换失败不影响原数据


def load_cache(stock_code, data_type):
    """加载缓存数据"""
    cache_path = get_cache_path(stock_code, data_type)
    if not cache_path.exists():
        return None
    
    try:
        with open(cache_path, 'rb') as f:
            cached = pickle.load(f)
        
        cache_time = cached.get('timestamp')
        if cache_time:
            age = datetime.now() - cache_time
            if age < timedelta(hours=CACHE_EXPIRY_HOURS):
                print(f"✅ 使用缓存数据: {stock_code}")
                return cached.get('data')
    except Exception as e:
        print(f"加载缓存失败: {e}")
    
    return None


def save_cache(stock_code, data_type, data):
    """保存数据到缓存"""
    cache_path = get_cache_path(stock_code, data_type)
    try:
        with open(cache_path, 'wb') as f:
            pickle.dump({'timestamp': datetime.now(), 'data': data}, f)
    except Exception as e:
        print(f"保存缓存失败: {e}")


def normalize_hk_code(stock_code):
    """
    标准化港股代码为完整数字格式（支持4位和5位代码）
    
    港股代码格式：
    - 4位代码：0700.HK (腾讯), 09988.HK (阿里巴巴)
    - 5位代码：00700.HK (腾讯), 09999.HK (网易), 09988.HK (阿里巴巴)
    """
    if not stock_code:
        return None
    
    code = str(stock_code).upper().strip()
    code = code.replace('.HK', '').replace('.hk', '')
    
    numbers = re.findall(r'\d+', code)
    if not numbers:
        return None
    
    # 获取完整数字代码（不限制位数）
    num = numbers[-1]
    
    # 标准化为5位格式（前面补0）
    return num.zfill(5)


def format_number(value):
    """格式化大数字"""
    if value is None:
        return None
    try:
        num = float(value)
        if abs(num) >= 1e12:
            return f"{num/1e12:.2f}万亿"
        elif abs(num) >= 1e8:
            return f"{num/1e8:.2f}亿"
        elif abs(num) >= 1e4:
            return f"{num/1e4:.2f}万"
        else:
            return f"{num:.2f}"
    except:
        return str(value)


# ==================== 辅助：富途 OpenD API 估值指标 ====================

def _fetch_futu_valuation(stock_code: str) -> dict:
    """
    从富途 OpenD API 获取实时估值指标（PE/PB/PS）
    这是估值指标的第1优先数据源
    
    stock_code: 原始股票代码格式，如 "0700.HK" 或 "0700"
    返回: {"peRatio": xx, "priceToBook": xx, "priceToSales": xx, "forwardPE": xx}
    """
    result = {k: None for k in ("peRatio", "forwardPE", "priceToBook", "priceToSales", "currentPrice")}
    
    try:
        from futu import OpenQuoteContext, RET_OK
        # 使用富途连接获取估值
        with OpenQuoteContext(host='127.0.0.1', port=11111) as ctx:
            # 标准化代码
            code = normalize_hk_code(stock_code)
            if not code:
                return result
            
            futu_code = f"HK.{code.zfill(5)}"
            ret, data = ctx.get_market_snapshot([futu_code])
            
            if ret == RET_OK and not data.empty:
                row = data.iloc[0]
                
                def safe_float(v):
                    try:
                        f = float(v)
                        return f if f > 0 else None
                    except:
                        return None
                
                result["peRatio"] = safe_float(row.get('pe_ratio'))
                result["priceToBook"] = safe_float(row.get('pb_ratio'))
                result["priceToSales"] = safe_float(row.get('ps_ratio'))
                result["forwardPE"] = safe_float(row.get('pe_ratio_forecast'))
                result["currentPrice"] = safe_float(row.get('last_price'))  # 添加当前股价
                
                print(f"✅ 富途估值指标: {code}  PE={result['peRatio']}  PB={result['priceToBook']}  股价={result['currentPrice']}")
                return result
                
    except Exception as e:
        print(f"⚠️ 富途估值获取失败: {e}")
    
    return result


# ==================== 数据源：模拟数据结构 ====================

def generate_demo_data(hk_code):
    """
    生成演示数据结构
    当所有数据源都失败时返回，确保前端能显示界面
    """
    demo_stocks = {
        "0700": {"name": "腾讯控股", "sector": "科技", "industry": "互联网"},
        "3690": {"name": "美团", "sector": "科技", "industry": "本地服务"},
        "9988": {"name": "阿里巴巴", "sector": "科技", "industry": "电商"},
        "2318": {"name": "中国平安", "sector": "金融", "industry": "保险"},
        "0005": {"name": "汇丰控股", "sector": "金融", "industry": "银行"},
    }
    
    stock_info = demo_stocks.get(hk_code, {"name": f"股票 {hk_code}", "sector": "", "industry": ""})
    
    result = {
        "source": "demo",
        "symbol": hk_code,
        "company_name": stock_info["name"],
        "sector": stock_info["sector"],
        "industry": stock_info["industry"],
        "note": "当前数据源暂时不可用，显示示例数据",
        "data": [{
            "symbol": hk_code,
            "period": "annual",
            "data": {
                "totalRevenue": None,
                "netIncome": None,
                "note": "数据获取中，请稍后重试"
            },
            "ratios": {}
        }]
    }
    
    return result


# ==================== 主入口函数 ====================

def get_hkex_financial_data(stock_code, report_type="annual"):
    """
    获取港股财务报表数据 (v1.6D 优化版)

    数据来源（按优先级）：
    1. 本地缓存（港交所披露易下载）- 秒开体验
    2. 富途 OpenD API - 估值指标优先
    
    ⚠️ 删除：Yahoo Finance、东方财富等网页下载功能
    """
    hk_code = normalize_hk_code(stock_code)
    if not hk_code:
        return {"success": False, "error": "无效的股票代码"}
    
    print(f"🔍 正在获取 {hk_code} 财务数据...")
    
    # 第1层: 优先读取本地 stockai_data (秒开体验)
    local_data = load_local_financial_data(stock_code)
    if local_data:
        return {
            "success": True,
            "data": [local_data],
            "count": 1,
            "source": "local_stockai_data",
            "is_local": True,
            "cached_at": local_data.get("cached_at"),
            "data_age_days": local_data.get("data_age_days")
        }
    
    # 第2层: 检查应用缓存
    cache_key = f"financials_{report_type}"
    cached = load_cache(hk_code, cache_key)
    if cached:
        # 转换缓存数据中的同比格式（兼容旧缓存的小数格式）
        _convert_growth_rates_in_cache(cached)
        return {
            "success": True,
            "data": [cached],
            "count": 1,
            "source": "cache"
        }
    
    # 第3层: 演示数据 (确保前端有东西显示)
    demo_data = generate_demo_data(hk_code)
    return {
        "success": True,
        "data": [demo_data],
        "count": 1,
        "source": "demo",
        "note": "本地数据暂不可用，请先同步数据"
    }


def load_local_financial_data(stock_code: str) -> dict:
    """
    从本地 stockai_data 缓存读取财务数据 (v1.6D 优化版)
    
    数据获取逻辑：
    1. 估值指标（PE/PB/PS）：富途 OpenD API 优先 → 本地备用
    2. 其他指标（盈利能力/财务健康/成长性/股东回报）：直接从本地数据摄取
    
    优化: 使用高速缓存系统 v2.0 (借鉴 Claude Code 架构)
    - 内存 LRU 缓存: 热点数据常驻内存
    - SQLite 索引: 快速搜索
    - 异步预取: 后台预加载
    """
    try:
        # 标准化代码
        code = str(stock_code).upper().replace('.HK', '').strip()
        code = code.zfill(5)  # 转为5位格式，如 00700
        
        # ★★★ 优先使用高速缓存系统 v2.0 ★★★
        if _FAST_CACHE_AVAILABLE:
            local_data = load_financial_data_fast(code)
            if local_data:
                pass  # 继续处理...
            else:
                return None
        else:
            # 传统方式：从磁盘读取
            cache_file = LOCAL_CACHE_DIR / f"{code}_financial.json"
            if not cache_file.exists():
                return None
            with open(cache_file, 'r', encoding='utf-8') as f:
                local_data = json.load(f)
        
        # 转换为前端兼容格式
        financial_summary = local_data.get("financial_summary", {})
        indicator_history = local_data.get("indicator_history", [])
        
        # 构建 ratios - 包含更多财务指标
        def parse_percent(value):
            if not value:
                return None
            try:
                val_str = str(value).replace("%", "").replace(",", "").strip()
                # 过滤掉 nan/NaN 等无效值
                if val_str.lower() in ("nan", "none", ""):
                    return None
                result = float(val_str)
                # 过滤 Python NaN 和 Infinity
                if result != result:  # NaN check (NaN != NaN is True)
                    return None
                if abs(result) == float("inf"):
                    return None
                return result
            except:
                return None
        
        def parse_number(value):
            if not value:
                return None
            try:
                val_str = str(value).replace(",", "").replace("元", "").replace("%", "").strip()
                # 过滤掉 nan/NaN 等无效值
                if val_str.lower() in ("nan", "none", ""):
                    return None
                if "万亿" in val_str:
                    return float(val_str.replace("万亿", "")) * 1e12
                elif "亿" in val_str:
                    return float(val_str.replace("亿", "")) * 1e8
                elif "万" in val_str:
                    return float(val_str.replace("万", "")) * 1e4
                else:
                    return float(val_str)
            except:
                return None
        
        # ---- 第1优先：富途 OpenD API 获取估值指标 ----
        valuation = _fetch_futu_valuation(stock_code)
        futu_source = "富途行情" if valuation.get("peRatio") else None
        
        # ── 货币单位统一：检测汇丰等美元财报公司 ──
        # 已知美元财报港股：汇丰(00005)、友邦(01299)等
        # akshare对这些股票返回的EPS/BPS标注为HKD但实际是USD(另一套汇率换算)
        # 而净利润/营收是真正的HKD。需要统一换算
        hk_code_normalized = stock_code.replace('.HK', '').zfill(5)
        USD_REPORT_STOCKS = {'00005', '01299', '06060', '06690'}  # 汇丰、友邦等
        _is_usd_report = hk_code_normalized in USD_REPORT_STOCKS
        USD_FX = 7.78  # 固定参考汇率
        HKD_CNY_FX = 1.115  # 港币兑人民币汇率（约1.115，即1港币≈1.115人民币）
        
        # ── 尝试从本地数据的财务摘要获取 ──
        # ---- 其他指标：直接从本地数据摄取 ----
        
        # 盈利能力
        roe = parse_percent(financial_summary.get("ROE"))
        # ROA: 源数据是真实百分比 (0.68%)，转为小数形式 (0.0068) 供前端 formatPercent 正确显示
        raw_roa = parse_percent(financial_summary.get("ROA"))
        roa = round(raw_roa / 100, 6) if raw_roa else None
        profit_margin = parse_percent(financial_summary.get("净利率"))
        gross_margin = parse_percent(financial_summary.get("毛利率"))
        operating_margin = parse_percent(financial_summary.get("营业利润率"))
        
        # 财务健康
        debt_ratio = parse_percent(financial_summary.get("资产负债率"))
        current_ratio = parse_percent(financial_summary.get("流动比率"))
        quick_ratio = parse_percent(financial_summary.get("速动比率"))
        # 产权比率 = 负债/权益 = 资产负债率 / (1 - 资产负债率)
        equity_ratio = None
        if debt_ratio and debt_ratio < 100:
            equity_ratio = round(debt_ratio / (100 - debt_ratio) * 100, 2)
        
        # 成长性
        latest_indicator = indicator_history[0] if indicator_history else {}
        prev_indicator = indicator_history[1] if len(indicator_history) > 1 else {}
        revenue_growth = parse_percent(latest_indicator.get("营收同比"))
        earnings_growth = parse_percent(latest_indicator.get("净利润同比"))
        # 营业利润同比（使用毛利润同比作为近似）
        operating_profit_growth = parse_percent(latest_indicator.get("毛利润同比"))
        
        # 股东回报 - 优先从 indicator_history 获取
        eps_value = parse_number(latest_indicator.get("EPS") or financial_summary.get("基本每股收益") or financial_summary.get("每股收益"))
        bps = parse_number(latest_indicator.get("每股净资产") or financial_summary.get("每股净资产"))
        
        # ================================================================
        # EPS/BPS 货币换算（关键修复）：
        # akshare 对港股的 EPS/BPS 存的是 CNY 数值（尽管 CURRENCY="HKD"），
        # 对汇丰等美元股存的是 HKD 数值（需要转USD），对腾讯等人民币股直接是CNY。
        # 
        # 验证数据（0006.HK 电能实业）：
        #   akshare: EPS=2.646 CNY, BPS=38.452 CNY
        #   核实: EPS=2.93 HKD, BPS=42.9 HKD
        #   换算: 2.646 × 1.115 = 2.95 HKD ≈ 2.93 ✅
        #   换算: 38.452 × 1.115 = 42.87 HKD ≈ 42.9 ✅
        # ================================================================
        
        # EPS/BPS换算（针对汇丰等USD财报公司）
        # akshare EPS/BPS标注HKD但实际是USD(另一汇率)，转为真正USD用于一致性计算
        # 对于汇丰: EPS_display=8.50 / FX=7.78 → EPS_actual=1.09 USD
        eps_value_usd = None
        bps_usd = None
        if _is_usd_report and eps_value and bps:
            eps_value_usd = round(eps_value / USD_FX, 3)   # USD per share
            bps_usd = round(bps / USD_FX, 3)               # USD per share
        elif eps_value and bps:
            # 非美元报表公司（港股/A股）：akshare EPS/BPS 实际是 CNY，转为 HKD
            eps_value = round(eps_value * HKD_CNY_FX, 3)
            bps = round(bps * HKD_CNY_FX, 2)
        
        # EPS同比：从两期EPS计算
        eps_growth = None
        eps_current = eps_value
        if latest_indicator.get("EPS"):
            eps_current = parse_number(latest_indicator.get("EPS"))
        if prev_indicator.get("EPS"):
            eps_prev = parse_number(prev_indicator.get("EPS"))
            if eps_current and eps_prev and eps_prev != 0:
                eps_growth = round((eps_current / eps_prev - 1) * 100, 2)
        
        # ── 股息率和派息率：从 akshare 东方财富 API 获取 ──
        # 数据来源: stock_hk_dividend_payout_em (东方财富港股派息)
        dividend_yield = None
        payout_ratio = None
        
        try:
            import akshare as ak
            # 处理股票代码：00700.HK -> 00700 (保留前导0)
            hk_code = stock_code.replace('.HK', '')
            # 如果代码是纯数字且不足5位，补齐
            if hk_code.isdigit() and len(hk_code) < 5:
                hk_code = hk_code.zfill(5)

            df_payout = ak.stock_hk_dividend_payout_em(symbol=hk_code)
            if df_payout is not None and not df_payout.empty:
                # ============================================================
                # 派息数据获取逻辑（年度总额优先）：
                # 1. 取最新年度的"四季度分配"（2025年后部分股票用此记录全年总额）
                # 2. 若无，取"年度分配"（全年总额）
                # 3. 若无，取同年度"中期分配"+"年度分配"合并
                # 4. 若仍无，取最新"中期分配"（最常见的旧格式）
                # 修复：顺序改为 年度分配 > 中期分配（之前错误地先取中期）
                # ============================================================
                import re as re_module
                
                annual_df = df_payout[df_payout['分配类型'] == '年度分配']
                interim_df = df_payout[df_payout['分配类型'] == '中期分配']
                quarterly_df = df_payout[df_payout['分配类型'] == '四季度分配']
                
                def _parse_div(div_str):
                    """解析每股派息金额"""
                    # 优先匹配"相当于港币X元"（某些股票使用此格式）
                    match = re_module.search(r'相当于港币?([\d.]+)元', div_str)
                    if match:
                        return float(match.group(1))
                    # 匹配"每股派港币X元"（支持"可选择以股代息"等后缀）
                    match = re_module.search(r'每股派港币?([\d.]+)元', div_str)
                    if match:
                        return float(match.group(1))
                    return None
                
                per_share_div = None
                dividend_year = None
                
                # 策略1：取最新年度的"四季度分配"（2025年后部分股票用此记录全年总额）
                if not quarterly_df.empty:
                    latest = quarterly_df.iloc[0]
                    div_str = str(latest.get('分红方案', ''))
                    per_share_div = _parse_div(div_str)
                    if per_share_div:
                        dividend_year = str(latest.get('财政年度', ''))
                        print(f"✓ {hk_code} 派息: 四季度分配 {per_share_div}元 (年度={dividend_year})")
                
                # 策略2：若四季度分配为空，取"年度分配"（全年总额）
                if per_share_div is None and not annual_df.empty:
                    latest_annual = annual_df.iloc[0]
                    fiscal_year = str(latest_annual.get('财政年度', ''))
                    div_str = str(latest_annual.get('分红方案', ''))
                    per_share_div = _parse_div(div_str)
                    
                    if per_share_div:
                        dividend_year = fiscal_year
                        # 检查同年度是否有中期分配，如有则合并
                        same_year_interim = interim_df[interim_df['财政年度'].astype(str) == fiscal_year]
                        if not same_year_interim.empty:
                            interim_str = str(same_year_interim.iloc[0].get('分红方案', ''))
                            interim_div = _parse_div(interim_str)
                            if interim_div and interim_div > 0:
                                # 如果年度分配明显大于中期分配的1.5倍，说明这只是末期（末期+中期=全年）
                                # 例如：0006.HK 年度=2.04 > 中期=0.78*1.5=1.17 → 合并 → 全年=2.82
                                # 之前条件写反了！导致 0006.HK 股息率/派息率都算错了约27%
                                if per_share_div > interim_div * 1.5:
                                    per_share_div = per_share_div + interim_div
                                    print(f"  ↪ 合并中期{interim_div}元+年度→全年{per_share_div}元")
                        print(f"✓ {hk_code} 派息: 全年 {per_share_div}元 (年度={dividend_year})")
                
                # 策略3：若年度分配为空，取"中期分配"
                if per_share_div is None and not interim_df.empty:
                    latest_interim = interim_df.iloc[0]
                    div_str = str(latest_interim.get('分红方案', ''))
                    per_share_div = _parse_div(div_str)
                    if per_share_div:
                        dividend_year = str(latest_interim.get('财政年度', ''))
                        print(f"✓ {hk_code} 派息: 中期分配 {per_share_div}元 (年度={dividend_year})")


                if per_share_div:
                    # ============================================================
                    # 【关键修复】多重有效性检查：
                    # 1. 只有盈利公司才计算股息率/派息率
                    # 2. 派息数据超过2年未更新，不应视为当前派息
                    # ============================================================
                    is_profitable = eps_value and eps_value > 0
                    
                    # 检查派息数据的时效性
                    try:
                        div_year = int(str(dividend_year).strip()[:4])
                        current_year = datetime.now().year
                        years_since_dividend = current_year - div_year
                    except (ValueError, TypeError):
                        years_since_dividend = 999  # 无法解析时视为无效
                    
                    # 无效派息数据的情况
                    is_stale_dividend = years_since_dividend > 2  # 超过2年无派息
                    
                    if not is_profitable:
                        # 亏损公司：忽略历史派息数据
                        print(f"⚠️ {hk_code} 当前亏损(EPS={eps_value})，忽略历史派息数据")
                        per_share_div = None
                        dividend_yield = None
                        payout_ratio = None
                    elif is_stale_dividend:
                        # 长期无派息公司：akshare的旧派息记录不代表当前政策
                        # 例如：268.HK 最后派息 FY2019（7年前），不应计算股息率
                        print(f"⚠️ {hk_code} 已连续 {years_since_dividend} 年无派息(FY{dividend_year})，忽略旧数据")
                        per_share_div = None
                        dividend_yield = None
                        payout_ratio = None
                    else:
                        # 正常情况：盈利 + 最近2年内有派息
                        div_usd = per_share_div / USD_FX
                        if _is_usd_report and eps_value_usd:
                            payout_ratio = round(div_usd / eps_value_usd * 100, 2)
                        elif eps_value and eps_value > 0:
                            payout_ratio = round(per_share_div / eps_value * 100, 2)
                        # 股息率 = 每股派息 / 当前股价 × 100%
                        current_price = valuation.get("currentPrice")
                        # 东方财富 f43 对港股直接返回 HKD 格式（如 8.45），无需除以 100
                        # 添加合理性检查：港股股价应在 1-10000 HKD 之间
                        if not current_price or current_price < 1 or current_price > 10000:
                            try:
                                import requests
                                url = f"https://push2.eastmoney.com/api/qt/stock/get?secid=116.{hk_code}&fields=f43&fltt=2&invt=2"
                                resp = requests.get(url, timeout=5)
                                data = resp.json()
                                if data.get('data'):
                                    em_price = data['data'].get('f43')
                                    if em_price:
                                        em_price_f = float(em_price)
                                        # 合理性检查：港股股价不应 <1 HKD 或 >10000 HKD
                                        if 1 <= em_price_f <= 10000:
                                            current_price = em_price_f
                                        else:
                                            print(f"⚠️ {hk_code} 东方财富价格异常({em_price_f} HKD)，跳过")
                            except Exception as e:
                                print(f"⚠️ 东方财富股价获取失败: {e}")
                        if current_price and current_price > 0:
                            dividend_yield = round(per_share_div / current_price * 100, 2)
        except Exception as e:
            print(f"⚠️ akshare 股息率获取失败: {e}")
        
        ratios = {
            # ── 估值指标（富途 OpenD API / 本地备用）──
            "peRatio":       valuation.get("peRatio"),
            "forwardPE":     valuation.get("forwardPE"),
            "priceToBook":   valuation.get("priceToBook"),
            "priceToSales":  valuation.get("priceToSales"),
            # ── 盈利能力（本地财报）──
            "roe":            roe,
            "roa":            roa,
            "profitMargins": profit_margin,
            "grossMargins":  gross_margin,
            "operatingMargins": operating_margin,
            # ── 财务健康（本地财报）──
            "debtRatio":     debt_ratio,
            "currentRatio":  current_ratio,
            "quickRatio":    quick_ratio,
            "equityRatio":   equity_ratio,  # 产权比率 = 负债/权益
            # ── 成长性（本地财报 indicator_history）──
            "revenueGrowth": revenue_growth,
            "earningsGrowth": earnings_growth,
            "operatingProfitGrowth": operating_profit_growth,  # 营业利润同比
            "epsGrowth":     eps_growth,  # EPS同比
            # ── 股东回报（本地财报）──
            "dividendYield": dividend_yield,
            "payoutRatio":  payout_ratio,
            "eps":           eps_value,
            "bps":           bps,
            # ── 汇丰等美元财报公司：真实USD EPS/BPS ──
            "epsUsd":        eps_value_usd,   # USD per share (用于一致性计算)
            "bpsUsd":        bps_usd,          # USD per share
            "_isUsdReport":  _is_usd_report,  # 是否为美元财报公司
            # ── 数据来源标记 ──
            "_valuation_source": futu_source or "本地数据",  # 估值指标来源
            "_is_bank_stock": financial_summary.get("_is_bank_stock", False),  # 银行股标记
        }
        
        # 构建 financial data
        financial_data = {
            "totalRevenue": financial_summary.get("营业收入"),
            "netIncome": financial_summary.get("净利润"),
            "grossProfit": financial_summary.get("毛利润"),
            "operatingIncome": financial_summary.get("营业利润"),
            "totalAssets": financial_summary.get("总资产"),
            "totalLiabilities": financial_summary.get("总负债"),
            "shareholdersEquity": financial_summary.get("股东权益"),
            "eps": eps_value,
            "bps": bps,
        }
        
        # 把 financial_summary 的字段注入 indicator_history[0]，前端 latest 可直接读取
        # 同时注入所有需要计算同比变化的字段
        if indicator_history:
            indicator_history[0].setdefault("每股净资产",  bps)
            indicator_history[0].setdefault("基本每股收益", eps_value)
            indicator_history[0].setdefault("EPS",        eps_value)
            indicator_history[0].setdefault("毛利率",      gross_margin)
            indicator_history[0].setdefault("净利率",      profit_margin)
            indicator_history[0].setdefault("ROE",        roe)
            indicator_history[0].setdefault("ROA",         roa)
            indicator_history[0].setdefault("营业利润率",   operating_margin)
            indicator_history[0].setdefault("资产负债率",  debt_ratio)
            indicator_history[0].setdefault("流动比率",    current_ratio)
            indicator_history[0].setdefault("速动比率",    quick_ratio)
            indicator_history[0].setdefault("产权比率",    equity_ratio)
            indicator_history[0].setdefault("营业收入",    financial_summary.get("营业收入"))
            indicator_history[0].setdefault("净利润",      financial_summary.get("净利润"))
            indicator_history[0].setdefault("毛利润同比",   latest_indicator.get("毛利润同比"))
            
            # 为所有历史数据注入完整字段，确保同比计算正常工作
            for i in range(1, len(indicator_history)):
                hist_item = indicator_history[i]
                hist_item.setdefault("每股净资产", "")
                hist_item.setdefault("基本每股收益", "")
                hist_item.setdefault("EPS", "")
                hist_item.setdefault("毛利率", "")
                hist_item.setdefault("净利率", "")
                hist_item.setdefault("ROE", parse_percent(hist_item.get("ROE", "")))
                hist_item.setdefault("ROA", None)
                hist_item.setdefault("营业利润率", "")
                hist_item.setdefault("资产负债率", "")
                hist_item.setdefault("流动比率", None)
                hist_item.setdefault("速动比率", None)
                hist_item.setdefault("产权比率", None)
        
        result = {
            "source": "local_stockai_data",
            "symbol": code,
            "company_name": local_data.get("company_profile", {}).get("公司名称", ""),
            "sector": local_data.get("company_profile", {}).get("所属行业", ""),
            "industry": local_data.get("company_profile", {}).get("所属行业", ""),
            "data": [{
                "symbol": code,
                "period": "annual",
                "data": financial_data,
                "ratios": ratios,
                "indicator_history": indicator_history  # 额外提供历史数据
            }],
            "cached_at": local_data.get("cached_at"),
            "data_age_days": (datetime.now() - datetime.fromisoformat(local_data.get("cached_at", datetime.now().isoformat()))).days
        }
        
        print(f"✅ 从本地 stockai_data 读取成功: {code}")
        return result
        
    except Exception as e:
        print(f"⚠️ 读取本地数据失败: {e}")
        return None


def get_financial_summary(stock_code):
    """
    获取财务摘要（用于财务比率显示） (v1.6D 优化版)

    数据来源：港交所披露易（本地缓存）
    
    ⚠️ 删除：Yahoo Finance、东方财富等网页下载功能
    """
    hk_code = normalize_hk_code(stock_code)
    if not hk_code:
        return {"success": False, "error": "无效的股票代码"}
    
    print(f"🔍 正在获取 {hk_code} 财务摘要...")
    
    # 尝试获取数据
    result = None
    source = ""
    
    # 1. 优先读取本地 stockai_data (秒开)
    local_data = load_local_financial_data(hk_code)
    if local_data:
        result = local_data
        source = "local"
    else:
        # 2. 检查应用缓存
        cache_key = "financials_annual"
        cached = load_cache(hk_code, cache_key)
        if cached:
            # 转换缓存数据中的同比格式（兼容旧缓存的小数格式）
            _convert_growth_rates_in_cache(cached)
            result = cached
            source = "cache"
        else:
            # 3. 演示数据
            result = generate_demo_data(hk_code)
            source = "demo"
    
    # 构建前端兼容格式
    # load_local_financial_data 返回结构：
    # result["data"][0] = { symbol, period, data (financial_data), ratios, indicator_history }
    # 注意：ratios 嵌套在 result["data"][0]["ratios"]，不是直接在 result["ratios"]
    if source == "local":
        # 获取 data[0] 中的完整数据
        data_item = result.get("data", [{}])[0] if result.get("data") else {}
        ratios = data_item.get("ratios", {})
        indicator_history = data_item.get("indicator_history", [])
        
        annual_data = {
            "data": {
                "totalRevenue": data_item.get("data", {}).get("totalRevenue"),
                "netIncome": data_item.get("data", {}).get("netIncome"),
                "grossProfit": data_item.get("data", {}).get("grossProfit"),
                "operatingIncome": data_item.get("data", {}).get("operatingIncome"),
                "bps": ratios.get("bps"),
                "eps": ratios.get("eps"),
            },
            "period": "annual",
            "ratios": ratios,
            "indicator_history": indicator_history,
            "symbol": hk_code,
        }
        summary = {
            "success": True,
            "symbol": hk_code,
            "company_name": result.get("company_name", ""),
            "sector": result.get("sector", ""),
            "industry": result.get("industry", ""),
            "source": "local",
            "annual": {"success": True, "data": annual_data},
            "quarterly": {"success": False, "data": {}},
            "data_source": "港交所披露易（本地缓存）",
            "cached_at": result.get("cached_at"),
            "data_age_days": result.get("data_age_days"),
            "is_local": True,
        }
    else:
        summary = {
            "success": True,
            "symbol": hk_code,
            "company_name": result.get("company_name", ""),
            "sector": result.get("sector", ""),
            "industry": result.get("industry", ""),
            "source": source,
            "annual": {
                "success": source != "demo",
                "data": result.get("data", [{}])[0] if result.get("data") else {}
            },
            "quarterly": {
                "success": False,
                "data": {}
            }
        }
        if source == "demo":
            summary["note"] = "本地数据暂不可用，请先运行数据同步"
    
    # 添加本地数据特有的信息
    if source == "local":
        summary["data_source"] = "港交所披露易（本地缓存）"
        summary["cached_at"] = result.get("cached_at")
        summary["data_age_days"] = result.get("data_age_days")
        summary["is_local"] = True
    
    if source == "demo":
        summary["note"] = "本地数据暂不可用，请先运行数据同步"
    
    return summary


# ==================== 保留：akshare 股息率获取（轻量级）====================
# 注：此函数仅在需要获取股息率但本地数据缺失时调用
# 由于是本地 API 调用（非网页下载），保留作为最后备用

def _fetch_akshare_dividend(hk_code: str) -> dict:
    """
    通过 akshare 获取港股股息率（轻量级本地 API）
    仅在本地数据缺失股息率时调用
    hk_code: 5位数字格式，如 "00700"
    """
    result = {}
    try:
        import akshare as ak
        df = ak.stock_hk_spot_em()  # 东方财富港股实时行情（含股息率）
        if df is not None and not df.empty:
            row = df[df["代码"].astype(str).str.zfill(5) == hk_code]
            if not row.empty:
                r = row.iloc[0]
                def to_pct(v):
                    try:
                        return float(str(v).replace("%", "").replace(",", "")) if v not in (None, "", "None", "-") else None
                    except:
                        return None
                result["dividendYield"] = to_pct(r.get("股息率"))
                if result["dividendYield"]:
                    print(f"✅ akshare 股息率: {hk_code}  {result['dividendYield']}%")
    except Exception as e:
        print(f"⚠️ akshare 股息率获取失败: {e}")
    return result


# 测试入口
if __name__ == "__main__":
    import sys
    
    test_code = sys.argv[1] if len(sys.argv) > 1 else "0700.HK"
    
    print(f"\n{'='*50}")
    print(f"测试股票: {test_code}")
    print(f"版本: StockAI v1.6D 优化版")
    print(f"{'='*50}\n")
    
    print("📊 财务报表数据:")
    result = get_hkex_financial_data(test_code, "annual")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    print("\n📈 财务摘要:")
    summary = get_financial_summary(test_code)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
