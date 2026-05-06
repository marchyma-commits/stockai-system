"""
Multi-Model AI Analyst for StockAI v1.6D-Optimized
Supports Claude + DeepSeek + SiliconFlow (Qwen/Kimi) multi-model analysis

数据来源（按优先级）：
  1. 本地缓存（港交所披露易下载）- 秒开体验
  2. 富途 OpenD API - 估值指标优先

⚠️ 财务比率数据来源：港交所披露易（本地缓存）
⚠️ 估值指标由富途 OpenD API 提供
"""

import requests
import logging
from typing import Dict, Any, Optional, List

# 尝试导入 Anthropic SDK (推荐方式)
try:
    from anthropic import Anthropic
    ANTHROPIC_SDK_AVAILABLE = True
except ImportError:
    ANTHROPIC_SDK_AVAILABLE = False
    print("⚠️ Anthropic SDK 未安装，将使用 requests 方式调用 Claude API")

# 尝试导入 OpenAI SDK (用于 SiliconFlow)
try:
    from openai import OpenAI
    OPENAI_SDK_AVAILABLE = True
except ImportError:
    OPENAI_SDK_AVAILABLE = False
    print("⚠️ OpenAI SDK 未安装，SiliconFlow 将使用 requests 方式调用")

logger = logging.getLogger(__name__)

# 尝试从配置文件读取 API Key
try:
    from config_keys import CLAUDE_API_KEY, DEEPSEEK_API_KEY, SILICONFLOW_API_KEY, SILICONFLOW_MODELS
except ImportError:
    CLAUDE_API_KEY = ""
    DEEPSEEK_API_KEY = "sk-a28f20ce1dad414daf17ad88981e540b"
    SILICONFLOW_API_KEY = ""
    SILICONFLOW_MODELS = {}


class MultiModelAIAnalyst:
    """多模型AI分析师 - Claude + DeepSeek + SiliconFlow"""

    def __init__(self):
        # DeepSeek 配置
        self.deepseek_api_key = DEEPSEEK_API_KEY
        self.deepseek_api_url = "https://api.deepseek.com/v1/chat/completions"

        # Claude 配置
        self.claude_api_key = CLAUDE_API_KEY
        self.claude_api_url = "https://api.anthropic.com/v1/messages"

        # SiliconFlow 配置
        self.siliconflow_api_key = SILICONFLOW_API_KEY
        self.siliconflow_api_url = "https://api.siliconflow.cn/v1/chat/completions"

        # 初始化 Anthropic 客户端 (如果 SDK 可用)
        self.anthropic_client = Anthropic(api_key=CLAUDE_API_KEY) if (ANTHROPIC_SDK_AVAILABLE and CLAUDE_API_KEY) else None

        # 初始化 SiliconFlow 客户端
        self.siliconflow_client = OpenAI(
            api_key=SILICONFLOW_API_KEY,
            base_url="https://api.siliconflow.cn/v1"
        ) if (OPENAI_SDK_AVAILABLE and SILICONFLOW_API_KEY) else None

        # 模型选择
        self.enabled_models = {
            'claude': bool(CLAUDE_API_KEY),  # Claude Sonnet 4
            'deepseek': bool(DEEPSEEK_API_KEY),  # DeepSeek Chat
            'siliconflow': bool(SILICONFLOW_API_KEY)  # SiliconFlow (Qwen/Kimi)
        }

        # SiliconFlow 可用模型
        self.siliconflow_available_models = [
            ('qwen', 'Qwen/Qwen2.5-72B-Instruct', '通义千问'),
            ('deepseek_r1', 'deepseek-ai/DeepSeek-R1', 'DeepSeek R1'),
        ]

    def set_claude_api_key(self, api_key: str):
        """设置 Claude API Key"""
        self.claude_api_key = api_key
        self.enabled_models['claude'] = bool(api_key)
        if ANTHROPIC_SDK_AVAILABLE and api_key:
            self.anthropic_client = Anthropic(api_key=api_key)

    def analyze_with_deepseek(self, stock_data: Dict[str, Any], question: str = "") -> Dict[str, Any]:
        """使用 DeepSeek 分析股票"""
        tech = stock_data.get('technicals', {})

        prompt = self._build_analysis_prompt(stock_data, question, model_type='deepseek')

        headers = {
            "Authorization": f"Bearer {self.deepseek_api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "你是专业的股票分析师，回答简洁专业，使用繁体中文。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 4000
        }

        try:
            response = requests.post(self.deepseek_api_url, headers=headers, json=payload, timeout=90)
            result = response.json()

            if 'choices' in result and len(result['choices']) > 0:
                return {
                    'success': True,
                    'model': 'DeepSeek',
                    'analysis': result['choices'][0]['message']['content'],
                    'signal': self._extract_signal(result['choices'][0]['message']['content'])
                }
            else:
                return {
                    'success': False,
                    'model': 'DeepSeek',
                    'error': result.get('error', {}).get('message', '未知错误')
                }
        except Exception as e:
            logger.error(f"DeepSeek API 错误: {e}")
            return {'success': False, 'model': 'DeepSeek', 'error': str(e)}

    def analyze_with_siliconflow(self, stock_data: Dict[str, Any], question: str = "", model_type: str = 'qwen') -> Dict[str, Any]:
        """使用 SiliconFlow (Qwen/Kimi) 分析股票"""
        if not self.siliconflow_api_key:
            return {
                'success': False,
                'model': 'SiliconFlow',
                'error': 'SiliconFlow API Key 未配置'
            }

        tech = stock_data.get('technicals', {})
        prompt = self._build_analysis_prompt(stock_data, question, model_type='siliconflow')

        # 从配置文件读取模型（强制使用 7B，避免误用 72B 产生高额费用）
        from config_keys import SILICONFLOW_MODELS
        model = SILICONFLOW_MODELS.get(model_type, SILICONFLOW_MODELS.get('qwen', 'Qwen/Qwen2.5-7B-Instruct'))
        model_display_map = {
            'qwen': 'Qwen2.5-7B(免费)',
            'deepseek_r1': 'DeepSeek-R1-Distill(免费)',
            'glm': 'GLM-4-9B(免费)'
        }
        model_display = model_display_map.get(model_type, model_type)

        try:
            if self.siliconflow_client:
                response = self.siliconflow_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "你是专业的股票分析师，回答简洁专业，使用繁体中文。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    max_tokens=3000
                )
                analysis_text = response.choices[0].message.content
            else:
                # 降级到 requests 方式
                headers = {
                    "Authorization": f"Bearer {self.siliconflow_api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "你是专业的股票分析师，回答简洁专业，使用繁体中文。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 3000
                }
                response = requests.post(self.siliconflow_api_url, headers=headers, json=payload, timeout=90)
                result = response.json()
                if 'choices' in result and len(result['choices']) > 0:
                    analysis_text = result['choices'][0]['message']['content']
                else:
                    return {
                        'success': False,
                        'model': f'SiliconFlow-{model_display}',
                        'error': result.get('error', {}).get('message', '未知错误')
                    }

            return {
                'success': True,
                'model': f'SiliconFlow-{model_display}',
                'analysis': analysis_text,
                'signal': self._extract_signal(analysis_text)
            }
        except Exception as e:
            logger.error(f"SiliconFlow API 错误: {e}")
            return {'success': False, 'model': f'SiliconFlow-{model_display}', 'error': str(e)}

    def analyze_with_claude(self, stock_data: Dict[str, Any], question: str = "") -> Dict[str, Any]:
        """使用 Claude 分析股票"""
        if not self.claude_api_key:
            return {
                'success': False,
                'model': 'Claude',
                'error': 'Claude API Key 未配置'
            }

        tech = stock_data.get('technicals', {})
        prompt = self._build_analysis_prompt(stock_data, question, model_type='claude')

        try:
            # 优先使用 SDK
            if self.anthropic_client:
                response = self.anthropic_client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=1024,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                )
                analysis_text = response.content[0].text
            else:
                # 降级到 requests 方式
                headers = {
                    "x-api-key": self.claude_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                payload = {
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}]
                }
                response = requests.post(self.claude_api_url, headers=headers, json=payload, timeout=30)
                result = response.json()
                if 'content' in result and len(result['content']) > 0:
                    analysis_text = result['content'][0].get('text', '')
                else:
                    error_msg = result.get('error', {}).get('message', '未知错误')
                    return {'success': False, 'model': 'Claude', 'error': error_msg}

            return {
                'success': True,
                'model': 'Claude',
                'analysis': analysis_text,
                'signal': self._extract_signal(analysis_text)
            }
        except Exception as e:
            logger.error(f"Claude API 错误: {e}")
            return {'success': False, 'model': 'Claude', 'error': str(e)}

    def analyze_both(self, stock_data: Dict[str, Any], question: str = "") -> Dict[str, Any]:
        """同时使用多个模型分析并对比"""
        results = {}
        signals = []

        # DeepSeek 分析
        deepseek_result = self.analyze_with_deepseek(stock_data, question)
        results['deepseek'] = deepseek_result
        if deepseek_result.get('success') and deepseek_result.get('signal'):
            signals.append(deepseek_result['signal'])

        # SiliconFlow (Qwen) 分析
        if self.enabled_models.get('siliconflow'):
            siliconflow_result = self.analyze_with_siliconflow(stock_data, question, 'qwen')
            results['siliconflow_qwen'] = siliconflow_result
            if siliconflow_result.get('success') and siliconflow_result.get('signal'):
                signals.append(siliconflow_result['signal'])

        # Claude 分析 (如果已配置)
        claude_result = self.analyze_with_claude(stock_data, question)
        results['claude'] = claude_result
        if claude_result.get('success') and claude_result.get('signal'):
            signals.append(claude_result['signal'])

        # 多数投票
        final_signal = self._vote_signal(signals) if signals else "观望"

        return {
            'success': True,
            'results': results,
            'final_signal': final_signal,
            'consensus': self._build_consensus(results, final_signal),
            'enabled_models': self.enabled_models
        }

    def _build_consensus(self, results: Dict, final_signal: str) -> str:
        """构建共识分析"""
        consensus = f"【综合分析结论: {final_signal}】\n\n"

        for name, result in results.items():
            if result.get('success'):
                model_emoji = {
                    'deepseek': '📊',
                    'siliconflow_qwen': '🤖',
                    'claude': '🧠'
                }.get(name, '📌')
                consensus += f"{model_emoji} {result.get('model', name)}: {result.get('signal', 'N/A')}\n"

        consensus += f"\n💡 最终建议: {final_signal}"

        return consensus

    def _get_financial_data(self, stock_code: str) -> Dict[str, Any]:
        """获取财务数据，优先从本地 stockai_data 读取"""
        try:
            # 尝试导入 hkex_financials 模块
            from hkex_financials import get_financial_summary
            financials = get_financial_summary(stock_code)
            if financials and financials.get('source') != 'demo':
                return financials
        except Exception as e:
            logger.warning(f"获取财务数据失败: {e}")
        
        return {}

    def _build_analysis_prompt(self, stock_data: Dict[str, Any], question: str, model_type: str) -> str:
        """构建分析提示词"""
        tech = stock_data.get('technicals', {})
        symbol = stock_data.get('symbol', '')
        
        # 获取财务数据
        financials = self._get_financial_data(symbol)
        
        # 提取财务指标（处理嵌套结构）
        annual_data = financials.get('annual', {}).get('data', {}) if financials else {}
        ratios = annual_data.get('ratios', {})
        indicator_history = annual_data.get('indicator_history', [])
        indicator = indicator_history[0] if indicator_history else {}
        
        # 构建财务数据字符串
        financial_section = ""
        if financials and financials.get('source') != 'demo':
            # 获取数据来源说明
            data_source = financials.get('data_source', '本地财务数据库')
            financial_section = f"""
【财务数据】
- 数据来源: 港交所披露易（{data_source}）
- 营业收入: {indicator.get('营业收入', '--')} ({indicator.get('营收同比', '--')})
- 净利润: {indicator.get('净利润', '--')} ({indicator.get('净利润同比', '--')})
- ROE: {ratios.get('roe', '--')}%
- ROA: {ratios.get('roa', '--')}%
- 毛利率: {ratios.get('grossMargins', '--')}%
- 净利率: {ratios.get('profitMargins', '--')}%
- 资产负债率: {ratios.get('debtRatio', '--')}%
- PE: {ratios.get('peRatio', '--')}
- PB: {ratios.get('priceToBook', '--')}
- 股息率: {ratios.get('dividendYield', '--')}
"""
        else:
            financial_section = """
【财务数据】
- 暂无财务数据可用
"""

        prompt = f"""你是一位专业的股票分析师，请根据以下数据进行分析。

【股票信息】
- 代码: {stock_data.get('symbol')}
- 名称: {stock_data.get('name')}
- 现价: ${stock_data.get('price')}
- 涨跌幅: {stock_data.get('change_percent')}%
- 今日高低: ${stock_data.get('low')} - ${stock_data.get('high')}

【技术指标】
- 趋势: {tech.get('trend', '--')}
- RSI(14): {tech.get('rsi14', '--')}
- MACD: DIF={tech.get('macd_dif', '--')}, DEA={tech.get('macd_dea', '--')}
- EMA60: {tech.get('ema60', '--')}
- 布林带: 上轨=${tech.get('bb_upper', '--')}, 下轨=${tech.get('bb_lower', '--')}
- 成交量比: {tech.get('volume_ratio', '--')}
- KDJ: K={tech.get('kdj_k', '--')}, D={tech.get('kdj_d', '--')}, J={tech.get('kdj_j', '--')}
{financial_section}
【用户问题】
{question if question else '请给出简短的投资建议（100字以内）。'}

请用专业、简洁的语言回答，使用繁体中文。"""

        return prompt

    def _extract_signal(self, text: str) -> str:
        """从分析文本中提取信号"""
        text = text.lower()

        # 看涨关键词
        buy_keywords = ['买入', '买入', '買入', '增持', '建議買入', '強烈買入', '买进', 'buy', 'bullish']
        sell_keywords = ['卖出', '賣出', '減持', '建議賣出', '拋售', 'sell', 'bearish']

        for kw in buy_keywords:
            if kw in text:
                return "买入"
        for kw in sell_keywords:
            if kw in text:
                return "卖出"

        return "观望"

    def _vote_signal(self, signals: List[str]) -> str:
        """多数投票"""
        if not signals:
            return "观望"

        buy_count = signals.count("买入")
        sell_count = signals.count("卖出")

        if buy_count > sell_count:
            return "买入"
        elif sell_count > buy_count:
            return "卖出"
        else:
            return "观望"

    def _build_consensus(self, results: Dict, final_signal: str) -> str:
        """构建共识分析"""
        consensus = f"【综合分析结论: {final_signal}】\n\n"

        for name, result in results.items():
            if result.get('success'):
                model_emoji = {
                    'deepseek': '📊',
                    'siliconflow_qwen': '🤖',
                    'claude': '🧠'
                }.get(name, '📌')
                consensus += f"{model_emoji} {result.get('model', name)}: {result.get('signal', 'N/A')}\n"

        consensus += f"\n💡 最终建议: {final_signal}"

        return consensus

    def generate_trading_strategy(self, stock_data: Dict[str, Any]) -> Dict[str, Any]:
        """根据数据自动生成交易策略"""
        tech = stock_data.get('technicals', {})
        price = stock_data.get('price', 0)
        atr = tech.get('atr', price * 0.01)

        # 基于多指标计算建议
        signals = {
            'trend': tech.get('trend', '震荡'),
            'rsi': tech.get('rsi14', 50),
            'macd': '买入' if (tech.get('macd_dif', 0) > tech.get('macd_dea', 0)) else '卖出',
            'ema60': '买入' if price and tech.get('ema60') and price > tech.get('ema60') else '卖出',
            'kdj': self._kdj_signal(tech.get('kdj_k', 50), tech.get('kdj_d', 50)),
            'bollinger': self._bollinger_signal(price, tech.get('bb_upper', price), tech.get('bb_lower', price))
        }

        # 计算各指标权重得分
        score = 50
        score += 15 if signals['trend'] == '上升趋势' else -10 if signals['trend'] == '下降趋势' else 0
        score += 10 if signals['rsi'] < 30 else -10 if signals['rsi'] > 70 else 0
        score += 10 if signals['macd'] == '买入' else -10
        score += 10 if signals['kdj'] == '买入' else -10

        score = max(0, min(100, score))

        # 生成策略
        if score >= 70:
            action = "积极买入"
            confidence = "高"
            position = "5-10%仓位"
        elif score >= 50:
            action = "谨慎买入"
            confidence = "中"
            position = "3-5%仓位"
        elif score >= 30:
            action = "观望"
            confidence = "中"
            position = "1-3%仓位"
        else:
            action = "减仓/观望"
            confidence = "高"
            position = "0%仓位"

        # 计算买卖价位
        buy_price = round(price - atr * 1.5, 2)
        sell_price = round(price + atr * 2, 2)
        stop_loss = round(price - atr, 2)
        target_1 = round(price * 1.05, 2)
        target_2 = round(price * 1.10, 2)

        return {
            'success': True,
            'overall_score': score,
            'action': action,
            'confidence': confidence,
            'recommended_position': position,
            'entry': {
                'buy_price': buy_price,
                'stop_loss': stop_loss,
                'rationale': f"在 ${buy_price} 附近买入，止损设于 ${stop_loss}"
            },
            'exit': {
                'target_1': target_1,
                'target_2': target_2,
                'sell_price': sell_price,
                'rationale': f"第一目标 ${target_1}，第二目标 ${target_2}"
            },
            'risk_reward': round((target_1 - price) / (price - stop_loss), 1) if (price > stop_loss) else 0,
            'signals': signals,
            'analysis': self._generate_strategy_text(signals, score, action)
        }

    def _kdj_signal(self, k: float, d: float) -> str:
        if k > 80 or d > 80:
            return "超买"
        elif k < 20 or d < 20:
            return "超卖"
        elif k > d:
            return "买入"
        else:
            return "卖出"

    def _bollinger_signal(self, price: float, upper: float, lower: float) -> str:
        if price > upper:
            return "突破上轨"
        elif price < lower:
            return "跌破下轨"
        else:
            return "正常区间"

    def _generate_strategy_text(self, signals: dict, score: int, action: str) -> str:
        """生成策略说明"""
        text = f"""📈 策略分析报告

综合评分: {score}/100 → {action}

指标信号:
• 趋势: {signals['trend']}
• RSI: {signals['rsi']:.1f}
• MACD: {signals['macd']}
• EMA60: {signals['ema60']}
• KDJ: {signals['kdj']}
• 布林带: {signals['bollinger']}

操作建议:
{action} - 信心度: {'高' if score >= 60 else '中' if score >= 40 else '低'}

⚠️ 风险提示: 请设置止损位，控制仓位不超过10%。"""
        return text


# 全局实例
ai_analyst = MultiModelAIAnalyst()
