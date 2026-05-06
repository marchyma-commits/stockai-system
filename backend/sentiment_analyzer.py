"""
sentiment_analyzer.py — AI 新闻情绪分析模块
使用 DeepSeek API 分析新闻情绪，输出 -1（利空）到 +1（利好）的评分
"""

import requests
import logging
from typing import List, Dict, Optional
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# 缓存：同一股票的情绪评分 30 分钟有效
_sentiment_cache = TTLCache(maxsize=200, ttl=1800)


# ============ 情绪标签映射 ============

def _score_to_label(score: float) -> Dict:
    """
    将 -1~+1 的分数转换为标签、颜色、图标
    """
    if score >= 0.5:
        return {"label": "利好", "color": "#10b981", "bg": "rgba(16,185,129,0.15)", "icon": "↑", "badge_class": "badge-buy"}
    elif score >= 0.15:
        return {"label": "偏利好", "color": "#84cc16", "bg": "rgba(132,204,22,0.15)", "icon": "↗", "badge_class": "badge-buy"}
    elif score >= -0.15:
        return {"label": "中性", "color": "#94a3b8", "bg": "rgba(148,163,184,0.15)", "icon": "→", "badge_class": "badge-neutral"}
    elif score >= -0.5:
        return {"label": "偏利空", "color": "#f97316", "bg": "rgba(249,115,22,0.15)", "icon": "↘", "badge_class": "badge-sell"}
    else:
        return {"label": "利空", "color": "#ef4444", "bg": "rgba(239,68,68,0.15)", "icon": "↓", "badge_class": "badge-sell"}


# ============ DeepSeek 情绪分析 ============

def _analyze_with_deepseek(news_list: List[Dict]) -> Optional[Dict]:
    """
    调用 DeepSeek API 分析新闻情绪
    返回: {"overall_score": 0.65, "label": "偏利好", "summary": "...", "news_scores": [...]}
    """
    try:
        from config_keys import DEEPSEEK_API_KEY, DEEPSEEK_API_URL
    except ImportError:
        logger.warning("[情绪分析] 无法导入 config_keys，使用默认分析")
        return None

    if not DEEPSEEK_API_KEY:
        logger.warning("[情绪分析] DeepSeek API Key 未配置，跳过 AI 分析")
        return None

    if not news_list:
        return None

    # 构建 prompt
    news_text = "\n".join([
        f"{i+1}. [{n.get('time','')}] {n.get('title','')}"
        for i, n in enumerate(news_list[:8])
    ])

    prompt = f"""你是一个专业的股票新闻情绪分析师。请分析以下新闻对相关股票的影响，并给出量化评分。

新闻列表：
{news_text}

请严格按照以下 JSON 格式返回（只返回JSON，不要任何其他文字）：
{{
  "overall_score": 0.5,
  "label": "利好",
  "summary": "简要分析（50字以内）",
  "news_scores": [
    {{"index": 1, "score": 0.8, "label": "利好", "reason": "原因（20字以内）"}},
    ...
  ]
}}

评分规则：
- overall_score: -1（极度利空）到 +1（极度利好），0为中性
- label: 利好/偏利好/中性/偏利空/利空
- 每条新闻的 score: -1 到 +1

只返回 JSON！"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是一个专业的股票情绪分析师，只返回 JSON，不要返回任何其他文字。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 1500
    }

    try:
        response = requests.post(
            DEEPSEEK_API_URL,
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

        # 提取 JSON
        import json as _json
        # 尝试去除 markdown 代码块
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        data = _json.loads(content)

        # 标准化标签
        label_info = _score_to_label(data.get("overall_score", 0))
        data["label"] = label_info["label"]
        data["color"] = label_info["color"]
        data["icon"] = label_info["icon"]
        data["badge_class"] = label_info["badge_class"]

        return data

    except _json.JSONDecodeError as e:
        logger.warning(f"[情绪分析] JSON 解析失败: {e}, content: {content[:200]}")
        return None
    except Exception as e:
        logger.warning(f"[情绪分析] DeepSeek API 调用失败: {e}")
        return None


# ============ 规则基础情绪分析（无 API Key 时的降级方案）============

def _rule_based_sentiment(news_list: List[Dict]) -> Dict:
    """
    基于规则的简易情绪分析（无 API 时使用）
    关键词打分
    """
    positive_keywords = [
        "增长", "盈利", "超预期", "突破", "创新高", "加码", "扩张", "增持",
        "利好", "推荐", "买入", "上调", "首次覆盖", "业绩", "利润", "营收",
        "分红", "回购", "战略", "合作", "订单", "签约", "中标"
    ]
    negative_keywords = [
        "下降", "亏损", "不及预期", "减持", "风险", "利空", "下调", "卖出",
        "终止", "取消", "诉讼", "调查", "违规", "处罚", "警示", "质疑",
        "清仓", "减产", "停产", "裁员", "降级", "警告", "衰退"
    ]

    scores = []
    for news in news_list[:8]:
        title = news.get("title", "")
        content = news.get("content", "")
        text = title + " " + content

        score = 0
        reasons = []
        for kw in positive_keywords:
            if kw in text:
                score += 1
                reasons.append(f"含正面词「{kw}」")
        for kw in negative_keywords:
            if kw in text:
                score -= 1
                reasons.append(f"含负面词「{kw}」")

        normalized = max(-1, min(1, score / 3)) if score != 0 else 0
        scores.append({
            "index": len(scores) + 1,
            "score": normalized,
            "label": _score_to_label(normalized)["label"],
            "reason": "; ".join(reasons[:2]) if reasons else "无明显情绪词",
            "title": title[:40]
        })

    overall = sum(s["score"] for s in scores) / len(scores) if scores else 0
    overall = max(-1, min(1, overall))
    label_info = _score_to_label(overall)

    summaries = {
        "利好": "整体消息偏正面",
        "偏利好": "近期消息略偏正面",
        "中性": "消息面较为中性",
        "偏利空": "近期消息略偏负面",
        "利空": "整体消息偏负面"
    }

    return {
        "overall_score": round(overall, 2),
        "label": label_info["label"],
        "color": label_info["color"],
        "icon": label_info["icon"],
        "badge_class": label_info["badge_class"],
        "summary": summaries.get(label_info["label"], "消息面中性"),
        "news_scores": scores,
        "method": "rule_based"
    }


# ============ 主入口 ============

def analyze_news_sentiment(stock_code: str, news_list: List[Dict]) -> Dict:
    """
    分析新闻情绪（统一入口）

    Args:
        stock_code: 股票代码
        news_list: 新闻列表 from fetch_stock_news()

    Returns:
        Dict: {
            "overall_score": float,   # -1 ~ +1
            "label": str,            # 利好/偏利好/中性/偏利空/利空
            "color": str,            # CSS颜色
            "icon": str,            # 图标
            "badge_class": str,     # Bootstrap badge class
            "summary": str,         # AI 分析摘要
            "news_scores": List[Dict],  # 每条新闻的评分
            "method": str,          # "deepseek" 或 "rule_based"
        }
    """
    cache_key = f"{stock_code}:{len(news_list)}"
    if cache_key in _sentiment_cache:
        logger.info(f"[情绪分析] 缓存命中: {stock_code}")
        return _sentiment_cache[cache_key]

    logger.info(f"[情绪分析] 分析中: {stock_code}, {len(news_list)} 条新闻")

    # 优先用 DeepSeek AI 分析
    ai_result = _analyze_with_deepseek(news_list)
    if ai_result:
        ai_result["method"] = "deepseek"
        _sentiment_cache[cache_key] = ai_result
        return ai_result

    # 降级：规则基础分析
    logger.info(f"[情绪分析] 使用规则基础分析: {stock_code}")
    result = _rule_based_sentiment(news_list)
    _sentiment_cache[cache_key] = result
    return result


def get_sentiment_summary(sentiment: Dict) -> str:
    """
    生成情绪摘要文字（用于展示）
    """
    if not sentiment:
        return "暂无数据"
    icon = sentiment.get("icon", "")
    label = sentiment.get("label", "")
    score = sentiment.get("overall_score", 0)
    summary = sentiment.get("summary", "")
    method = "(AI)" if sentiment.get("method") == "deepseek" else "(规则)"
    return f"{icon} {label} {method} | 综合评分 {score:.2f} | {summary}"


# ============ 测试 ============
if __name__ == "__main__":
    test_news = [
        {"title": "某公司营收增长30%，业绩超预期", "time": "2026-04-02", "content": "业绩超预期"},
        {"title": "行业龙头获得重大订单", "time": "2026-04-01", "content": "利好订单"},
        {"title": "市场传闻公司涉嫌违规被调查", "time": "2026-03-31", "content": "利空调查"},
    ]
    print("=== 规则基础情绪分析 ===")
    result = _rule_based_sentiment(test_news)
    print(f"综合评分: {result['overall_score']:.2f} ({result['label']})")
    print(f"摘要: {result['summary']}")
    print("\n各条新闻评分:")
    for ns in result["news_scores"]:
        print(f"  [{ns['score']:+.1f}] {ns['label']}: {ns['title']} - {ns['reason']}")
