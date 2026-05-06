"""
news_fetcher.py — 股票新闻数据获取模块 v2.1
支持: A股（沪/深/北交所）、港股、美股

数据源策略（2026-04-02 更新）：
  1. 港股: Yahoo Finance (yfinance) → 实时个股新闻
  2. A股: 新浪财经个股新闻 + 东方财富公告（双重保障）
  3. 美股: Yahoo Finance (yfinance)

时间修复：统一使用北京时间，显示正确日期
"""

import requests
import time
import re
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# 尝试导入 yfinance（支持港股/美股新闻）
try:
    import yfinance as _yf
except ImportError:
    _yf = None
    logger.warning("yfinance 未安装，港股/美股新闻功能不可用")

# 全局缓存（同一股票 10 分钟内不重复请求）
_news_cache = TTLCache(maxsize=200, ttl=600)

# 北京时区
BJ_TZ = timezone(timedelta(hours=8))


# ============ 工具函数 ============

def _get_beijing_time():
    """获取当前北京时间"""
    return datetime.now(BJ_TZ)


def _to_local_date(ctime_str: str) -> str:
    """
    统一时间格式：返回 YYYY-MM-DD（北京时间）
    修复未来日期问题：确保返回的日期不超过今天
    """
    today = _get_beijing_time().date()

    if not ctime_str:
        return str(today)

    # 清理字符串
    ctime_str = str(ctime_str).strip()

    # 可能是 Unix 时间戳（秒）
    if ctime_str.isdigit() and len(ctime_str) == 10:
        try:
            ts = int(ctime_str)
            dt = datetime.fromtimestamp(ts, tz=BJ_TZ)
            result_date = dt.date()
            # 防止未来日期
            if result_date > today:
                return str(today)
            return str(result_date)
        except:
            return str(today)

    # 可能是 Unix 时间戳（毫秒）
    if ctime_str.isdigit() and len(ctime_str) == 13:
        try:
            ts = int(ctime_str) / 1000
            dt = datetime.fromtimestamp(ts, tz=BJ_TZ)
            result_date = dt.date()
            if result_date > today:
                return str(today)
            return str(result_date)
        except:
            return str(today)

    # 可能是完整时间字符串
    try:
        # 尝试多种格式
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d",
            "%Y-%m-%d",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(ctime_str[:19], fmt)
                dt = dt.replace(tzinfo=BJ_TZ)
                result_date = dt.date()
                if result_date > today:
                    return str(today)
                return str(result_date)
            except:
                continue

        # 如果是其他格式，尝试提取日期部分
        date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', ctime_str)
        if date_match:
            date_str = date_match.group(1).replace('/', '-')
            parts = date_str.split('-')
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            result_date = datetime(year, month, day).date()
            if result_date > today:
                return str(today)
            return str(result_date)
    except:
        pass

    return str(today)


def _to_local_datetime(ctime_str: str) -> str:
    """转换时间戳为可读日期时间格式（北京时间）"""
    today = _get_beijing_time().date()

    if not ctime_str:
        return ""

    ctime_str = str(ctime_str).strip()

    # Unix 时间戳（秒）
    if ctime_str.isdigit() and len(ctime_str) == 10:
        try:
            ts = int(ctime_str)
            dt = datetime.fromtimestamp(ts, tz=BJ_TZ)
            result_date = dt.date()
            if result_date > today:
                return str(today) + " " + dt.strftime("%H:%M")
            return dt.strftime("%Y-%m-%d %H:%M")
        except:
            return ""

    # Unix 时间戳（毫秒）
    if ctime_str.isdigit() and len(ctime_str) == 13:
        try:
            ts = int(ctime_str) / 1000
            dt = datetime.fromtimestamp(ts, tz=BJ_TZ)
            result_date = dt.date()
            if result_date > today:
                return str(today) + " " + dt.strftime("%H:%M")
            return dt.strftime("%Y-%m-%d %H:%M")
        except:
            return ""

    return ctime_str[:16]


# ============ 数据源 1: Yahoo Finance (港股/美股) ============

def _fetch_yahoo_news(stock_code: str) -> List[Dict]:
    """
    使用 yfinance 获取个股新闻（支持港股和美股）
    stock_code: e.g. "0700.HK", "AAPL", "TSLA"
    """
    if _yf is None:
        logger.warning("[Yahoo新闻] yfinance 未安装")
        return []

    max_retries = 2
    for attempt in range(max_retries):
        try:
            # 每次重试都创建新的 Ticker 实例，避免缓存问题
            ticker = _yf.Ticker(stock_code)
            news_list = ticker.news

            if not news_list:
                if attempt < max_retries - 1:
                    time.sleep(1)  # 等待后重试
                    continue
                logger.info(f"[Yahoo新闻] {stock_code} 无新闻")
                return []

            results = []
            seen_titles = set()

            for item in news_list[:15]:
                if not isinstance(item, dict):
                    continue

                # 新的 Yahoo Finance 数据结构：title 在 content.title
                content = item.get("content", {})
                title = content.get("title", "") or item.get("title", "")
                pub_date = content.get("pubDate", "") or item.get("pubDate", "")
                summary = content.get("summary", "") or item.get("summary", "")

                # 提取 URL
                link = ""
                if content.get("canonicalUrl"):
                    link = content["canonicalUrl"].get("url", "")
                elif content.get("clickThroughUrl"):
                    link = content["clickThroughUrl"].get("url", "")

                # 来源
                providers = content.get("providers", []) or item.get("providers", [])
                source = providers[0].get("name", "Yahoo Finance") if providers else "Yahoo Finance"

                # 避免重复标题
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)

                results.append({
                    "title": title.strip(),
                    "time": _to_local_date(str(pub_date)),
                    "time_full": _to_local_datetime(str(pub_date)),
                    "source": source,
                    "url": link,
                    "content": summary or title,
                })

            logger.info(f"[Yahoo新闻] {stock_code} → {len(results)} 条")
            return results

        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            logger.warning(f"[Yahoo新闻] {stock_code} 获取失败: {e}")
            return []

    return []


# ============ 数据源 2: 新浪财经 A 股个股新闻 ============

def _fetch_sina_stock_news(stock_code: str) -> List[Dict]:
    """
    获取新浪财经指定股票的个股新闻
    stock_code: e.g. "sh600519" 或 "sz000858"
    """
    # 转换股票代码格式
    code_lower = stock_code.lower().strip()
    if code_lower.endswith(".sh") or code_lower.endswith(".sz"):
        sina_code = code_lower
    else:
        # 纯数字代码，判断沪/深
        if stock_code.startswith(("6", "5", "9")):
            sina_code = f"sh{stock_code}"
        elif stock_code.startswith(("0", "1", "2", "3")):
            sina_code = f"sz{stock_code}"
        else:
            sina_code = f"sh{stock_code}"

    # 新浪个股新闻接口
    url = f"https://feed.mix.sina.com.cn/api/news/get"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.sina.com.cn/",
    }
    params = {
        "id": sina_code,
        "type": "stock",
        "num": 10,
        "page": 1,
    }

    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        if data.get("status") != 0:
            return []

        items = data.get("result", {}).get("data", [])
        results = []
        for item in items:
            results.append({
                "title": item.get("title", "").strip(),
                "time": _to_local_date(item.get("ctime", "")),
                "time_full": _to_local_datetime(item.get("ctime", "")),
                "source": item.get("media_name", "新浪财经") or "新浪财经",
                "url": item.get("url", ""),
                "content": item.get("intro", "") or item.get("title", ""),
            })
        return results
    except Exception as e:
        logger.warning(f"[新浪个股新闻] {stock_code} 获取失败: {e}")
        return []


# ============ 数据源 3: 东方财富 A 股公告 ============

def _fetch_em_announcements(page_size: int = 80) -> List[Dict]:
    """获取东方财富最新 A 股公告（默认第1页）"""
    return _fetch_em_announcements_page(1, page_size)


def _fetch_em_announcements_page(page_index: int, page_size: int = 80) -> List[Dict]:
    """
    获取东方财富 A 股公告（支持分页）
    page_index: 页码（从1开始）
    """
    url = "https://np-anotice-stock.eastmoney.com/api/security/ann"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://data.eastmoney.com/",
        "Accept": "application/json",
    }
    params = {
        "sr": "-1",
        "page_size": page_size,
        "page_index": page_index,
        "ann_type": "SHA,SZA,BJA",
        "client_source": "web",
    }

    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        items = data.get("data", {}).get("list", [])
        results = []
        for item in items:
            codes = item.get("codes", [])
            stock_codes = [c.get("stock_code", "") for c in codes]
            short_names = [c.get("short_name", "") for c in codes]
            notice_date = item.get("notice_date", "") or item.get("art_time", "")
            results.append({
                "title": item.get("title", "").strip(),
                "time": _to_local_date(notice_date),
                "source": "东方财富",
                "url": f"https://data.eastmoney.com/notime/sk/{item.get('id', '')}.html",
                "content": item.get("summary", "") or item.get("title", ""),
                "stock_codes": stock_codes,
                "stock_names": short_names,
            })
        return results
    except Exception as e:
        logger.warning(f"[东方财富公告] 第{page_index}页请求失败: {e}")
        return []


def _filter_by_stock(news_list: List[Dict], stock_code: str) -> List[Dict]:
    """从公告列表中过滤指定股票"""
    normalized = stock_code.replace(".HK", "").replace(".US", "").replace(".SH", "").replace(".SZ", "").strip()
    results = []
    for item in news_list:
        codes = item.get("stock_codes", [])
        if normalized in codes:
            results.append(item)
    return results


# ============ 数据源 4: 新浪市场快讯（备用） ============

def _fetch_sina_market_news(limit: int = 15) -> List[Dict]:
    """获取新浪财经市场快讯"""
    url = "https://feed.mix.sina.com.cn/api/roll/get"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.sina.com.cn/",
    }
    params = {
        "pageid": "153",
        "lid": "2517",
        "num": limit,
        "page": 1,
        "callback": "",
    }
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        items = data.get("result", {}).get("data", [])
        results = []
        for item in items:
            results.append({
                "title": item.get("title", "").strip(),
                "time": _to_local_date(item.get("ctime", "")),
                "time_full": _to_local_datetime(item.get("ctime", "")),
                "source": item.get("media_name", "新浪财经") or "新浪财经",
                "url": item.get("url", ""),
                "content": item.get("intro", "") or item.get("title", ""),
                "stock_codes": [],
                "stock_names": [],
            })
        return results
    except Exception as e:
        logger.warning(f"[新浪快讯] 请求失败: {e}")
        return []


# ============ 主入口函数 ============

def fetch_stock_news(stock_code: str, limit: int = 10, allow_market_fallback: bool = False) -> Dict:
    """
    获取个股新闻/公告（统一入口，自动选择数据源）

    Args:
        stock_code: 股票代码
            - A股: "600519" / "000858"
            - 港股: "00700.HK" / "700.HK"
            - 美股: "AAPL.US"
        limit: 返回数量（默认10条）
        allow_market_fallback: 是否允许降级到市场快讯（默认False）

    Returns:
        Dict: {
            "news": List[Dict],      # 新闻列表
            "is_related": bool,      # 是否是与该股票相关的新闻
            "stock_code": str,       # 原始股票代码
        }
    """
    cache_key = f"{stock_code}:{limit}:{allow_market_fallback}"
    if cache_key in _news_cache:
        cached = _news_cache[cache_key]
        return cached

    logger.info(f"[新闻获取] 正在获取: {stock_code}")
    stock_code = stock_code.strip().upper()

    results = []
    is_related = True

    # === 港股 ===
    if stock_code.endswith(".HK"):
        # Yahoo Finance 要求港股代码格式为 "0700.HK"（4位数字）
        hk_code = stock_code.replace(".HK", "").strip()
        # 去掉前导零，然后补齐为4位
        hk_code = str(int(hk_code)).zfill(4)  # "00700" -> "700" -> "0700"
        yahoo_code = f"{hk_code}.HK"

        # 优先使用 Yahoo Finance
        results = _fetch_yahoo_news(yahoo_code)
        if not results and allow_market_fallback:
            # 降级到市场快讯
            results = _fetch_sina_market_news(limit)
            is_related = False

    # === 美股（纯大写字母代码，无数字） ===
    elif stock_code.endswith(".US") or (stock_code.isupper() and stock_code.isalpha() and not stock_code.isdigit()):
        # Yahoo Finance 对美股不需要 .US 后缀
        us_code = stock_code.replace(".US", "").strip()
        results = _fetch_yahoo_news(us_code)
        if not results and allow_market_fallback:
            results = _fetch_sina_market_news(limit)
            is_related = False

    # === A股 ===
    else:
        # 策略1：新浪个股新闻
        sina_news = _fetch_sina_stock_news(stock_code)
        if sina_news:
            results = sina_news

        # 策略2：如果新浪没有，尝试东方财富公告（多页获取）
        if not results:
            all_anns = []
            # 获取前3页公告（约240条），覆盖更多股票
            for page in range(1, 4):
                anns = _fetch_em_announcements_page(page, page_size=80)
                all_anns.extend(anns)

            filtered = _filter_by_stock(all_anns, stock_code)
            if filtered:
                results = filtered
            else:
                # 如果前3页没有，继续获取更多页
                for page in range(4, 8):
                    more_anns = _fetch_em_announcements_page(page, page_size=80)
                    if not more_anns:
                        break
                    all_anns.extend(more_anns)
                    new_filtered = _filter_by_stock(more_anns, stock_code)
                    if new_filtered:
                        filtered = new_filtered
                        break

                if filtered:
                    results = filtered

        # 策略3：降级到市场快讯（仅在 allow_market_fallback=True 时）
        if not results and allow_market_fallback:
            logger.info(f"[新闻获取] {stock_code} 无个股新闻，使用市场快讯")
            results = _fetch_sina_market_news(limit)
            is_related = False

    # 去重（基于标题）
    seen = set()
    unique = []
    for r in results:
        key = r.get("title", "")
        if key and key not in seen:
            seen.add(key)
            unique.append(r)

    # 统一格式化输出
    output = []
    for r in unique[:limit]:
        output.append({
            "title": r.get("title", ""),
            "time": r.get("time", ""),
            "time_full": r.get("time_full", ""),
            "source": r.get("source", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
            "stock_codes": r.get("stock_codes", []),
        })

    result = {
        "news": output,
        "is_related": is_related,
        "stock_code": stock_code,
    }
    _news_cache[cache_key] = result
    logger.info(f"[新闻获取] {stock_code} → {len(output)} 条, 相关: {is_related}")
    return result


def fetch_market_news(limit: int = 15) -> Dict:
    """获取市场快讯"""
    cache_key = f"market:{limit}"
    if cache_key in _news_cache:
        return _news_cache[cache_key]

    results = _fetch_sina_market_news(limit)
    result = {
        "news": results,
        "is_related": False,
        "stock_code": "market",
    }
    _news_cache[cache_key] = result
    return result


# ============ 测试 ============
if __name__ == "__main__":
    print("=" * 60)
    print(f"测试时间: {_get_beijing_time()}")
    print("=" * 60)

    print("\n=== 测试港股 Yahoo Finance (00700.HK 腾讯) ===")
    result = fetch_stock_news("00700.HK", 5)
    print(f"相关新闻: {result['is_related']}, 条数: {len(result['news'])}")
    for n in result['news'][:3]:
        print(f"  [{n['time']}] {n['title'][:50]}")
        print(f"        来源: {n['source']}")

    print("\n=== 测试A股新浪个股新闻 (600519 贵州茅台) ===")
    result = fetch_stock_news("600519", 5)
    print(f"相关新闻: {result['is_related']}, 条数: {len(result['news'])}")
    for n in result['news'][:3]:
        print(f"  [{n['time']}] {n['title'][:50]}")
        print(f"        来源: {n['source']}")

    print("\n=== 测试A股东方财富公告 (000858 五粮液) ===")
    result = fetch_stock_news("000858", 5)
    print(f"相关新闻: {result['is_related']}, 条数: {len(result['news'])}")
    for n in result['news'][:3]:
        print(f"  [{n['time']}] {n['title'][:50]}")

    print("\n=== 测试美股 Yahoo Finance (AAPL) ===")
    result = fetch_stock_news("AAPL", 5)
    print(f"相关新闻: {result['is_related']}, 条数: {len(result['news'])}")
    for n in result['news'][:3]:
        print(f"  [{n['time']}] {n['title'][:50]}")
        print(f"        来源: {n['source']}")

    print("\n=== 测试市场快讯 ===")
    result = fetch_market_news(5)
    print(f"条数: {len(result['news'])}")
    for n in result['news'][:3]:
        print(f"  [{n['time']}] {n['title'][:50]}")
