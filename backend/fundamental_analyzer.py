"""
基本面分析引擎 v1.0
==================
采用 Claude Code + TradingView MCP 思维的设计理念：

【创新分析框架】
1. 趋势分析 - 类似 TradingView 的多周期分析
2. 成长质量 - 量化成长持续性与稳定性
3. 估值定位 - 与行业/历史比较
4. 财务健康 - 多维度风险评估
5. 股息质量 - 股息可持续性分析
6. 创新指标 - PEG、PSY、M-Score 等

【Claude Code 思维】
- 模块化、可测试
- 清晰的评分体系
- 多维度交叉验证
"""

import json
import os
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass
import math

@dataclass
class AnalysisScore:
    """分析评分数据类"""
    score: float          # 综合评分 0-100
    grade: str            # 评级 A/B/C/D
    trend: str            # 趋势 bullish/bearish/neutral
    summary: str          # 简短总结
    signals: List[str]    # 关键信号
    details: Dict         # 详细分析


class FundamentalAnalyzer:
    """
    基本面分析引擎
    采用多维度评分体系
    """
    
    def __init__(self, data_dir: str = "C:/Users/MarcoMa/stockai_data/cache"):
        self.data_dir = data_dir
        
    def load_financial_data(self, stock_code: str) -> Optional[Dict]:
        """加载财务数据，支持多种代码格式：HK.00700, 00700.HK, 00700"""
        # 统一提取纯数字代码
        import re
        digits = re.sub(r'[^0-9]', '', stock_code)
        if not digits:
            return None
        code = digits.zfill(5)
        filepath = os.path.join(self.data_dir, f"{code}_financial.json")
        
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
    
    def analyze(self, stock_code: str, realtime: Dict[str, Any] = None) -> Dict[str, Any]:
        """执行完整基本面分析
        
        Args:
            stock_code: 股票代码
            realtime: 富途实时数据 (可选)，包含:
                - last_price: 当前股价
                - dividend_yield: 富途 TTM 股息率
                - pe: 实时 PE
                - pb: 实时 PB
        """
        data = self.load_financial_data(stock_code)
        if not data:
            return {"success": False, "error": f"未找到 {stock_code} 的财务数据"}
        
        summary = data.get("financial_summary", {})
        # 检查 summary 是否为空（REIT/ETF/基金类股票，东方财富无财务指标数据）
        if not summary or (isinstance(summary, dict) and len(summary) <= 1 and not summary.get("报告期")):
            company_name = data.get("company_profile", {}).get("公司名称", stock_code)
            return {
                "success": False,
                "error": f"该股票({company_name})无财务指标数据，可能是 REIT/ETF/基金类产品，东方财富不提供财务分析指标",
                "stock_code": stock_code,
                "no_financial_data": True
            }
        history = data.get("indicator_history", [])
        profile = data.get("company_profile", {})
        
        # 如果有富途实时数据，计算实时股息率
        if realtime and realtime.get('last_price') and realtime.get('last_price') > 0:
            per_share_div_str = summary.get("每股派息", "N/A")
            # 兼容旧格式 "0.22元" 和新格式 "0.2167港元"
            if isinstance(per_share_div_str, str):
                per_share_div_str = per_share_div_str.replace("港元", "").replace("元", "")
            per_share_div = self._parse_number(per_share_div_str)
            if per_share_div > 0:
                rt_div_yield = round(per_share_div / realtime['last_price'] * 100, 2)
                # 用实时计算的股息率覆盖 cache 中的静态值
                summary = dict(summary)  # 避免修改原始数据
                summary["股息率_实时"] = f"{rt_div_yield:.2f}%"
                summary["_实时股价"] = realtime['last_price']

        # 注入富途实时 PE/PB 到 summary（用于 _analyze_valuation）
        if realtime:
            need_copy = (realtime.get('pe') and realtime['pe'] > 0) or (realtime.get('pb') and realtime['pb'] > 0)
            if need_copy:
                summary = dict(summary)
            if realtime.get('pe') and realtime['pe'] > 0:
                summary["PE"] = float(realtime['pe'])
            if realtime.get('pb') and realtime['pb'] > 0:
                summary["PB"] = float(realtime['pb'])
        
        # 执行各类分析
        growth_analysis = self._analyze_growth(history)
        profitability_analysis = self._analyze_profitability(summary)
        financial_health = self._analyze_financial_health(summary)
        valuation = self._analyze_valuation(summary)
        dividend = self._analyze_dividend(summary, history, realtime=realtime)
        innovation = self._innovation_metrics(summary, history)
        
        # 计算综合评分
        overall_score = self._calculate_overall_score(
            growth_analysis, profitability_analysis, 
            financial_health, valuation, dividend
        )
        
        return {
            "success": True,
            "stock_code": stock_code,
            "company_name": profile.get("公司名称", ""),
            "industry": profile.get("所属行业", ""),
            "latest_report": summary.get("报告期", ""),
            
            # 各维度分析
            "growth": growth_analysis,
            "profitability": profitability_analysis,
            "financial_health": financial_health,
            "valuation": valuation,
            "dividend": dividend,
            "innovation": innovation,
            
            # 综合评分
            "overall": overall_score,
            
            # 趋势分析
            "trend_analysis": self._analyze_trend(history),
            
            # AI 研判
            "ai_judgment": self._generate_ai_judgment(
                growth_analysis, profitability_analysis,
                financial_health, valuation, dividend, overall_score
            )
        }
    
    def _parse_number(self, value: Any) -> float:
        """解析带单位的数字"""
        if value is None or value == "N/A" or value == "--":
            return 0.0
        
        if isinstance(value, (int, float)):
            return float(value)
        
        value_str = str(value).strip()
        
        # 处理百分比
        if "%" in value_str:
            return float(value_str.replace("%", ""))
        
        # 处理单位 (优先匹配长单位)
        multipliers = [
            ("亿", 1e8),
            ("万", 1e4),
            ("千", 1e3),
            ("百万", 1e6),
            ("B", 1e9),
            ("M", 1e6),
            ("K", 1e3),
            ("元", 1),  # 处理 "24.749元"
        ]
        
        for unit, mult in multipliers:
            if unit in value_str:
                num_str = value_str.replace(unit, "").replace(",", "").strip()
                try:
                    return float(num_str) * mult
                except:
                    pass
        
        try:
            return float(value_str.replace(",", ""))
        except:
            return 0.0
    
    def _parse_percent(self, value: Any) -> float:
        """解析百分比"""
        if value is None or value == "N/A" or value == "--":
            return 0.0
        
        value_str = str(value).strip()
        if "%" in value_str:
            return float(value_str.replace("%", ""))
        
        try:
            return float(value_str)
        except:
            return 0.0
    
    def _parse_amount_yi(self, value: Any) -> float:
        """解析金额（如 '3030.52亿' → 3030.52）"""
        if value is None or value == "N/A" or value == "--":
            return 0.0
        import re
        s = str(value).strip()
        # 匹配 "3030.52亿" 格式
        m = re.match(r'([-\d.]+)\s*亿', s)
        if m:
            return float(m.group(1))
        try:
            return float(s)
        except:
            return 0.0
    
    def _analyze_growth(self, history: List[Dict]) -> Dict[str, Any]:
        """
        成长性分析
        ==========
        【TradingView 思维】多周期趋势判断
        
        指标:
        - 营收增长率趋势 (CAGR)
        - 净利润增长率稳定性
        - 增长加速度
        """
        if len(history) < 2:
            return {"score": 0, "grade": "N/A", "signals": [], "details": {}}
        
        scores = []
        signals = []
        details = {}
        
        # 提取增长率数据（过滤无效值 0.0 → 仅保留有实际数据的年份）
        revenue_growth = []
        profit_growth = []
        
        for item in history[:5]:  # 最近5年
            rev_raw = item.get("营收同比", None)
            prof_raw = item.get("净利润同比", None)
            # 仅当字段有实际值时才加入（避免把 "N/A"/missing 当 0 处理）
            if rev_raw not in (None, "", "N/A", "--", 0, "0", "0%"):
                revenue_growth.append(self._parse_percent(rev_raw))
            if prof_raw not in (None, "", "N/A", "--", 0, "0", "0%"):
                profit_growth.append(self._parse_percent(prof_raw))
        
        # 始终在 details 中显示原始数据（方便前端展示，即使 signals 为空）
        for i, item in enumerate(history[:3]):
            yr = item.get("报告期", f"Year-{i+1}")
            rv = item.get("营收同比", "N/A")
            pf = item.get("净利润同比", "N/A")
            details[f"营收增长 ({yr[:4]})"] = str(rv) if rv not in (None, "") else "N/A"
            details[f"净利润增长 ({yr[:4]})"] = str(pf) if pf not in (None, "") else "N/A"
        
        # 1. 营收增长趋势（需要至少1年有效数据）
        rev_score = 0
        if len(revenue_growth) >= 1:
            recent_avg = sum(revenue_growth[:2]) / min(2, len(revenue_growth))
            historical_avg = sum(revenue_growth[2:]) / max(1, len(revenue_growth) - 2) if len(revenue_growth) > 2 else recent_avg
            
            details["营收近期均增"] = f"{recent_avg:.1f}%"
            if len(revenue_growth) > 2:
                details["营收历史均增"] = f"{historical_avg:.1f}%"
            
            if recent_avg > 10 and recent_avg > historical_avg:
                rev_score = 100
                signals.append("✅ 营收加速增长")
            elif recent_avg > 10:
                rev_score = 85
                signals.append("✅ 营收双位数增长")
            elif recent_avg > 5:
                rev_score = 70
                signals.append("📈 营收稳定增长")
            elif recent_avg > 0:
                rev_score = 50
                signals.append("📊 营收微增")
            elif recent_avg > -5:
                rev_score = 30
                signals.append("⚠️ 营收轻微下滑")
            else:
                rev_score = 15
                signals.append("⚠️ 营收同比下滑")
            scores.append(rev_score)
        
        # 2. 净利润增长趋势（需要至少1年有效数据）
        prof_score = 0
        if len(profit_growth) >= 1:
            recent_profit = profit_growth[0]
            details["最新净利润增长"] = f"{recent_profit:+.1f}%"
            
            if len(profit_growth) >= 2:
                profit_stability = self._calculate_stability(profit_growth)
                details["净利润增长稳定性"] = f"{profit_stability:.0f}%"
            
            # 净利润与营收增速比较（需要两者都有数据）
            if len(revenue_growth) >= 1:
                profit_vs_revenue = profit_growth[0] - revenue_growth[0]
                details["净利润 vs 营收增速差"] = f"{profit_vs_revenue:+.1f}%"
                
                if profit_vs_revenue > 10:
                    prof_score = 100
                    signals.append("✅ 净利润增速超越营收 (提效)")
                elif profit_vs_revenue > 0:
                    prof_score = 75
                elif profit_vs_revenue > -10:
                    prof_score = 50
                else:
                    prof_score = 25
                    signals.append("⚠️ 净利润增速落后营收")
            else:
                # 仅用净利润绝对值评分
                if recent_profit > 15:
                    prof_score = 90
                    signals.append("✅ 净利润高增长")
                elif recent_profit > 5:
                    prof_score = 70
                    signals.append("📈 净利润稳定增长")
                elif recent_profit > 0:
                    prof_score = 50
                elif recent_profit > -10:
                    prof_score = 30
                else:
                    prof_score = 15
                    signals.append("⚠️ 净利润下滑")
            scores.append(prof_score)
        
        # 3. 增长持续性评分（需要至少2年净利润数据）
        if len(profit_growth) >= 2:
            positive_years = sum(1 for g in profit_growth if g > 0)
            total_years = len(profit_growth)
            details["正增长年数"] = f"{positive_years}/{total_years}年"
            
            if positive_years >= 4:
                scores.append(100)
                signals.append("✅ 连续4年以上正增长")
            elif positive_years >= 3:
                scores.append(80)
                signals.append("📈 近3年以上正增长")
            elif positive_years >= 2:
                scores.append(60)
            elif positive_years == 1:
                scores.append(35)
                signals.append(f"⚠️ 仅{positive_years}年正增长")
            else:
                scores.append(10)
                signals.append("⚠️ 近年均为负增长")
        
        # 计算综合评分：按实际有效子项数量平均（修复原先固定除3导致分数偏低的问题）
        base_score = sum(scores) / len(scores) if scores else 0
        score = min(100, max(0, base_score))
        
        # 评级（与港股实际质量匹配的阈值）
        if score >= 75:
            grade = "A"
        elif score >= 55:
            grade = "B"
        elif score >= 35:
            grade = "C"
        else:
            grade = "D"
        
        # 若无任何信号，补充一条中性说明
        if not signals:
            signals.append("📊 成长数据不足，仅供参考")
        
        return {
            "score": round(score, 1),
            "grade": grade,
            "signals": signals,
            "details": details,
            "trend": "bullish" if score >= 60 else ("bearish" if score < 40 else "neutral")
        }
    
    def _calculate_stability(self, values: List[float]) -> float:
        """
        计算稳定性评分 (0-100)
        
        综合两个维度:
        1. 正增长持续性 (60%权重) — 正增长年数占比
        2. 波动温和度 (40%权重) — 变异系数的温和映射，不直接钳制到0
        
        修复: 旧算法用纯 CV 导致科技公司(利润波动大)永远显示 0%
        """
        if len(values) < 2:
            return 100.0
        
        n = len(values)
        
        # 维度1: 正增长持续性 (60%)
        positive_count = sum(1 for v in values if v > 0)
        positive_ratio = positive_count / n
        continuity_score = positive_ratio * 100  # 0~100
        
        # 维度2: 波动温和度 (40%) — 用 sigmoid 映射 CV，避免极端值
        mean = sum(values) / n
        if mean != 0:
            variance = sum((x - mean) ** 2 for x in values) / n
            std_dev = math.sqrt(variance)
            cv = abs(std_dev / mean) * 100  # 变异系数
            
            # sigmoid 映射: CV=0 → 100分, CV=50 → 73分, CV=100 → 50分, CV=200 → 27分, CV=300 → 12分
            # 公式: 100 / (1 + (cv/100)^1.5)
            volatility_score = 100.0 / (1.0 + (cv / 100.0) ** 1.5)
        else:
            volatility_score = 50.0
        
        # 加权综合
        stability = continuity_score * 0.6 + volatility_score * 0.4
        return max(0, min(100, stability))
    
    def _analyze_profitability(self, summary: Dict) -> Dict[str, Any]:
        """
        盈利能力分析
        ==========
        【创新指标】
        - ROE 杜邦分解
        - 毛利率趋势
        - 净利率质量
        """
        signals = []
        details = {}
        scores = []
        
        # 1. ROE 分析
        roe = self._parse_percent(summary.get("ROE", 0))
        details["ROE"] = f"{roe:.2f}%"
        
        if roe >= 25:
            scores.append(30)
            signals.append("⭐ ROE > 25% (优秀)")
        elif roe >= 20:
            scores.append(27)
            signals.append("⭐ ROE > 20% (优秀)")
        elif roe >= 15:
            scores.append(22)
            signals.append("✅ ROE > 15% (良好)")
        elif roe >= 10:
            scores.append(15)
        elif roe >= 5:
            scores.append(8)
        else:
            scores.append(3)
            signals.append("⚠️ ROE < 5% (较弱)")
        
        # 2. ROA 分析
        roa = self._parse_percent(summary.get("ROA", 0))
        details["ROA"] = f"{roa:.2f}%"
        
        if roa >= 15:
            scores.append(25)
            signals.append("⭐ ROA > 15% (资产效率极佳)")
        elif roa >= 10:
            scores.append(20)
            signals.append("✅ ROA > 10% (资产效率高)")
        elif roa >= 5:
            scores.append(14)
        else:
            scores.append(7)
        
        # 3. 毛利率分析
        gross_margin = self._parse_percent(summary.get("毛利率", 0))
        if gross_margin > 0:
            details["毛利率"] = f"{gross_margin:.2f}%"
            
            if gross_margin >= 60:
                scores.append(28)
                signals.append("⭐ 毛利率 > 60% (极强定价权)")
            elif gross_margin >= 50:
                scores.append(25)
                signals.append("⭐ 毛利率 > 50% (定价权强)")
            elif gross_margin >= 30:
                scores.append(18)
            elif gross_margin >= 15:
                scores.append(12)
            else:
                scores.append(8)
        
        # 4. 净利率分析
        net_margin = self._parse_percent(summary.get("净利率", 0))
        if net_margin > 0:
            details["净利率"] = f"{net_margin:.2f}%"
            
            if net_margin >= 30:
                scores.append(27)
                signals.append("⭐ 净利率 > 30% (盈利能力强)")
            elif net_margin >= 20:
                scores.append(22)
            elif net_margin >= 10:
                scores.append(16)
            else:
                scores.append(10)
        
        # 综合评分 - 标准化到100分满分
        max_possible = 30 + 25 + 28 + 27  # 各项满分
        raw_score = sum(scores) if scores else 0
        score = min(100, (raw_score / max_possible * 100) if max_possible > 0 else 0)
        
        if score >= 80:
            grade = "A"
        elif score >= 60:
            grade = "B"
        elif score >= 40:
            grade = "C"
        else:
            grade = "D"
        
        return {
            "score": score,
            "grade": grade,
            "signals": signals,
            "details": details,
            "trend": "bullish" if score >= 60 else ("bearish" if score < 40 else "neutral")
        }
    
    def _analyze_financial_health(self, summary: Dict) -> Dict[str, Any]:
        """
        财务健康分析
        ==========
        【多维度风险评估】
        - 资产负债率
        - 流动比率
        - 速动比率
        - 综合健康评分
        """
        signals = []
        details = {}
        scores = []
        
        # 1. 资产负债率
        debt_ratio = self._parse_percent(summary.get("资产负债率", 0))
        details["资产负债率"] = f"{debt_ratio:.2f}%"
        
        if summary.get("_is_bank_stock"):
            # 银行股特殊处理
            if 80 <= debt_ratio <= 95:
                scores.append(25)
            else:
                scores.append(18)
        else:
            if debt_ratio <= 30:
                scores.append(30)
                signals.append("✅ 低负债 (资产负债率 < 30%)")
            elif debt_ratio <= 50:
                scores.append(25)
            elif debt_ratio <= 70:
                scores.append(15)
            else:
                scores.append(5)
                signals.append("⚠️ 高负债风险 (资产负债率 > 70%)")
        
        # 2. 流动比率
        current_ratio = self._parse_number(summary.get("流动比率", 0))
        details["流动比率"] = f"{current_ratio:.2f}"
        
        if summary.get("_is_bank_stock"):
            scores.append(20)  # 银行股流动比率参考意义不大
        else:
            if current_ratio >= 2:
                scores.append(25)
                signals.append("✅ 短期偿债能力强")
            elif current_ratio >= 1.5:
                scores.append(22)
            elif current_ratio >= 1:
                scores.append(18)
            else:
                scores.append(8)
                signals.append("⚠️ 短期偿债压力")
        
        # 3. 速动比率
        quick_ratio = self._parse_number(summary.get("速动比率", 0))
        details["速动比率"] = f"{quick_ratio:.2f}"
        
        if quick_ratio >= 1.5:
            scores.append(25)
            signals.append("✅ 速动比率优秀")
        elif quick_ratio >= 1:
            scores.append(22)
        elif quick_ratio >= 0.8:
            scores.append(15)
        elif quick_ratio >= 0.5:
            scores.append(10)
        else:
            scores.append(5)
            signals.append("⚠️ 速动比率偏低")
        
        # 综合评分 - 标准化到100分满分
        max_possible = 30 + 25 + 25  # 各项满分
        raw_score = sum(scores) if scores else 0
        score = min(100, (raw_score / max_possible * 100) if max_possible > 0 else 0)
        
        if score >= 80:
            grade = "A"
        elif score >= 60:
            grade = "B"
        elif score >= 40:
            grade = "C"
        else:
            grade = "D"
        
        return {
            "score": score,
            "grade": grade,
            "signals": signals,
            "details": details,
            "health_status": "优秀" if score >= 80 else ("良好" if score >= 60 else ("一般" if score >= 40 else "较弱"))
        }
    
    def _analyze_valuation(self, summary: Dict) -> Dict[str, Any]:
        """
        估值分析
        ==========
        【创新: 与历史和行业比较】
        - PE 估值分位
        - PB 与 ROE 关系
        - PS 营收倍数
        """
        signals = []
        details = {}
        scores = []
        
        # PE 分析
        pe = self._parse_number(summary.get("PE", summary.get("pe_ratio", 0)))
        if pe > 0:
            details["PE"] = f"{pe:.2f}"
            # 如果 PE 来自富途实时注入（float 而非原始字符串），标记来源
            raw_pe = summary.get("PE", "")
            if isinstance(raw_pe, float):
                details["PE_实时(富途)"] = f"{pe:.2f}"
            
            if pe <= 10:
                scores.append(30)
                signals.append("💰 PE < 10 (估值偏低)")
            elif pe <= 15:
                scores.append(25)
            elif pe <= 20:
                scores.append(22)
            elif pe <= 30:
                scores.append(18)
            elif pe <= 40:
                scores.append(12)
            else:
                scores.append(5)
                signals.append("⚠️ PE > 40 (估值偏高)")
        else:
            # 无PE数据，给中等分
            scores.append(15)
            details["PE"] = "N/A"
        
        # PB 分析
        pb = self._parse_number(summary.get("PB", summary.get("pb_ratio", 0)))
        if pb > 0:
            details["PB"] = f"{pb:.2f}"
            
            # PB 与 ROE 关系分析
            roe = self._parse_percent(summary.get("ROE", 0))
            if roe > 0:
                # 理论 PB = ROE / r (假设折现率 r=10%)
                theoretical_pb = roe / 10
                pb_vs_theory = pb / theoretical_pb if theoretical_pb > 0 else 1
                details["PB_vs_ROE"] = f"{pb_vs_theory:.2f}x"
                
                if pb_vs_theory <= 0.8:
                    scores.append(30)
                    signals.append("⭐ PB/ROE 比值 < 0.8 (价值显著)")
                elif pb_vs_theory <= 1.2:
                    scores.append(25)
                elif pb_vs_theory <= 2:
                    scores.append(18)
                else:
                    scores.append(10)
        else:
            scores.append(15)
            details["PB"] = "N/A"
        
        # 综合评分 - 标准化到100分满分
        max_possible = 30 + 30  # 各项满分
        raw_score = sum(scores) if scores else 0
        score = min(100, (raw_score / max_possible * 100) if max_possible > 0 else 0)
        
        if score >= 80:
            grade = "A"
        elif score >= 60:
            grade = "B"
        elif score >= 40:
            grade = "C"
        else:
            grade = "D"
        
        return {
            "score": score,
            "grade": grade,
            "signals": signals,
            "details": details,
            "valuation_level": "低估" if score >= 70 else ("合理" if score >= 50 else "高估")
        }
    
    def _analyze_dividend(self, summary: Dict, history: List[Dict], realtime: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        股息分析
        ==========
        【创新: 股息质量评估】
        - 股息率（优先使用富途实时数据）
        - 派息率健康度
        - 派息稳定性
        - 股东总回报率（股息率 + 估算回购率）
        """
        signals = []
        details = {}
        scores = []
        
        # 1. 股息率 — 优先使用实时数据
        # 优先级: 实时计算 > 富途 TTM > cache 静态值
        div_yield = self._parse_percent(summary.get("股息率_实时", 0))  # 实时计算值（analyze() 中注入）
        div_yield_source = "实时计算"
        
        if div_yield <= 0 and realtime:
            # 使用富途 TTM 股息率
            futu_div = realtime.get('dividend_yield')
            if futu_div and futu_div > 0:
                div_yield = round(float(futu_div), 2)
                div_yield_source = "富途TTM"
        
        if div_yield <= 0:
            # 回退到 cache 静态值
            div_yield = self._parse_percent(summary.get("股息率", 0))
            div_yield_source = "财报静态"
        
        details["股息率"] = f"{div_yield:.2f}%"
        details["股息率_来源"] = div_yield_source
        
        # 如果有 cache 静态值，也显示对比
        cache_div = self._parse_percent(summary.get("股息率", 0))
        if cache_div > 0 and div_yield_source != "财报静态":
            details["股息率_财报"] = f"{cache_div:.2f}%"
        
        if div_yield >= 8:
            scores.append(30)
            signals.append("💰 股息率 > 8% (极高息)")
        elif div_yield >= 5:
            scores.append(28)
            signals.append("💰 股息率 > 5% (高息)")
        elif div_yield >= 3:
            scores.append(24)
            signals.append("✅ 股息率 > 3% (良好)")
        elif div_yield >= 1:
            scores.append(18)
        elif div_yield > 0:
            scores.append(12)
        else:
            scores.append(8)
            signals.append("⚠️ 暂无股息")
        
        # 2. 派息率分析
        payout_ratio = self._parse_percent(summary.get("派息率", 0))
        details["派息率"] = f"{payout_ratio:.2f}%"
        
        if payout_ratio > 0:
            if payout_ratio <= 30:
                scores.append(30)
                signals.append("✅ 派息率 < 30% (留存资金多)")
            elif payout_ratio <= 50:
                scores.append(25)
            elif payout_ratio <= 70:
                scores.append(18)
            elif payout_ratio <= 100:
                scores.append(12)
            else:
                scores.append(5)
                signals.append("⚠️ 派息率 > 100% (不可持续)")
        else:
            scores.append(10)
        
        # 3. 每股派息
        per_share_div_raw = summary.get("每股派息", "N/A")
        if isinstance(per_share_div_raw, str):
            # 兼容旧格式 "0.22元" 和新格式 "0.2167港元"
            per_share_div_clean = per_share_div_raw.replace("港元", "").replace("元", "")
        else:
            per_share_div_clean = per_share_div_raw
        per_share_div = self._parse_number(per_share_div_clean)
        if per_share_div > 0:
            details["每股派息"] = f"{per_share_div:.2f}元"
        
        # 4. 派息稳定性 (从历史数据)
        stability_score = 15  # 默认中等
        if len(history) >= 3:
            recent_years = min(3, len(history))
            div_history = []
            
            for item in history[:recent_years]:
                eps = self._parse_number(item.get("EPS", 0))
                payout = self._parse_percent(item.get("派息率", summary.get("派息率", 0)))
                if eps > 0:
                    est_div = eps * payout / 100
                    div_history.append(est_div)
            
            if len(div_history) >= 2:
                stability = self._calculate_stability(div_history)
                details["派息稳定性"] = f"{stability:.1f}%"
                
                if stability >= 90:
                    stability_score = 30
                    signals.append("⭐ 派息非常稳定")
                elif stability >= 75:
                    stability_score = 25
                    signals.append("✅ 派息稳定")
                elif stability >= 60:
                    stability_score = 18
                else:
                    stability_score = 10
                    signals.append("⚠️ 派息波动较大")
        
        scores.append(stability_score)
        
        # 5. 股东总回报率（股息率 + 估算回购率）
        # 港股回购数据非公开 API 可直接获取，使用 PE 和 ROE 间接估算
        # 估算逻辑: 如果公司 ROE 高于 PE 的倒数(盈利收益率)，说明有超额利润可能用于回购
        if div_yield > 0:
            roe = self._parse_percent(summary.get("ROE", 0))
            pe = self._parse_number(summary.get("PE", 0))
            if pe > 0:
                earning_yield = 100.0 / pe  # 盈利收益率 = 1/PE
                # 回购率 ≈ max(0, ROE - 盈利收益率 × 派息率/100) 
                # 粗略估算: 公司可能用多余利润回购
                estimated_buyback = max(0, round(roe - div_yield - earning_yield * (1 - payout_ratio/100), 2))
                if estimated_buyback > 0.5:  # 只显示有意义的回购率
                    total_return = round(div_yield + estimated_buyback, 2)
                    details["估算回购率"] = f"{estimated_buyback:.2f}%"
                    details["股东总回报率"] = f"{total_return:.2f}%"
                    signals.append(f"📊 股东总回报率 ≈ {total_return:.1f}% (股息{div_yield:.1f}%+回购{estimated_buyback:.1f}%)")
        
        # 综合评分 - 标准化到100分满分
        max_possible = 30 + 30 + 30  # 各项满分
        raw_score = sum(scores) if scores else 0
        score = min(100, (raw_score / max_possible * 100) if max_possible > 0 else 0)
        
        if score >= 80:
            grade = "A"
        elif score >= 60:
            grade = "B"
        elif score >= 40:
            grade = "C"
        else:
            grade = "D"
        
        return {
            "score": score,
            "grade": grade,
            "signals": signals,
            "details": details,
            "dividend_quality": "优质" if score >= 70 else ("一般" if score >= 50 else "较差")
        }
    
    def _innovation_metrics(self, summary: Dict, history: List[Dict]) -> Dict[str, Any]:
        """
        创新指标分析
        ==========
        【专业级指标】
        - PEG 比率 (成长调整估值)
        - 资产周转率趋势
        - 经营现金流质量
        """
        details = {}
        signals = []
        
        # 1. PEG 比率
        pe = self._parse_number(summary.get("PE", summary.get("pe_ratio", 0)))
        if len(history) >= 2:
            # 使用最近2年净利润增长率
            recent_growth = self._parse_percent(history[0].get("净利润同比", 0))
            hist_growth = self._parse_percent(history[1].get("净利润同比", 0))
            avg_growth = (recent_growth + hist_growth) / 2
            
            if pe > 0 and avg_growth > 0:
                peg = pe / avg_growth
                details["PEG"] = f"{peg:.2f}"
                
                if peg <= 1:
                    signals.append("⭐ PEG < 1 (成长被低估)")
        
        # 2. ROE 趋势
        if len(history) >= 3:
            roe_trend = []
            for item in history[:3]:
                roe = self._parse_percent(item.get("ROE", 0))
                if roe > 0:
                    roe_trend.append(roe)
            
            if len(roe_trend) >= 2:
                roe_change = roe_trend[0] - roe_trend[-1]
                details["ROE_趋势"] = f"{roe_change:+.2f}%"
                
                if roe_change > 3:
                    signals.append("📈 ROE 持续改善")
                elif roe_change < -3:
                    signals.append("⚠️ ROE 有所下滑")
        
        # 3. 净利润率趋势
        if len(history) >= 3:
            margin_trend = []
            for item in history[:3]:
                margin = self._parse_percent(item.get("净利率", 0))
                if margin > 0:
                    margin_trend.append(margin)
            
            if len(margin_trend) >= 2:
                margin_change = margin_trend[0] - margin_trend[-1]
                details["净利率趋势"] = f"{margin_change:+.2f}%"
                
                if margin_change > 3:
                    signals.append("📈 盈利能力提升")
                elif margin_change < -3:
                    signals.append("⚠️ 盈利能力下滑")
        
        return {
            "signals": signals,
            "details": details
        }
    
    def _analyze_trend(self, history: List[Dict]) -> Dict[str, Any]:
        """
        趋势分析 (类似 TradingView 多周期)
        """
        if len(history) < 2:
            return {"short_term": "N/A", "medium_term": "N/A", "long_term": "N/A"}
        
        trends = {}
        
        # 短期: 最近1年
        if len(history) >= 1:
            recent = history[0]
            price_change = self._parse_percent(recent.get("净利润同比", 0))
            trends["short_term"] = "上升" if price_change > 5 else ("下降" if price_change < -5 else "震荡")
        
        # 中期: 最近3年平均
        if len(history) >= 3:
            avg_growth = sum(self._parse_percent(h.get("净利润同比", 0)) for h in history[:3]) / 3
            trends["medium_term"] = "上升" if avg_growth > 5 else ("下降" if avg_growth < -5 else "震荡")
        
        # 长期: 最近5年平均
        if len(history) >= 5:
            avg_growth = sum(self._parse_percent(h.get("净利润同比", 0)) for h in history[:5]) / 5
            trends["long_term"] = "上升" if avg_growth > 5 else ("下降" if avg_growth < -5 else "震荡")
        
        return trends
    
    def _calculate_overall_score(
        self, growth: Dict, profitability: Dict, 
        health: Dict, valuation: Dict, dividend: Dict
    ) -> Dict[str, Any]:
        """计算综合评分"""
        
        # 权重配置
        weights = {
            "growth": 0.20,        # 成长性 20%
            "profitability": 0.25, # 盈利能力 25%
            "financial_health": 0.20, # 财务健康 20%
            "valuation": 0.15,      # 估值 15%
            "dividend": 0.20        # 股息 20%
        }
        
        scores = {
            "growth": growth.get("score", 50),
            "profitability": profitability.get("score", 50),
            "financial_health": health.get("score", 50),
            "valuation": valuation.get("score", 50),
            "dividend": dividend.get("score", 50)
        }
        
        # 加权平均
        overall = sum(scores[k] * weights[k] for k in weights)
        
        # 评级
        if overall >= 80:
            grade = "A"
            recommendation = "强烈推荐"
        elif overall >= 70:
            grade = "A-"
            recommendation = "推荐买入"
        elif overall >= 60:
            grade = "B+"
            recommendation = "建议关注"
        elif overall >= 50:
            grade = "B"
            recommendation = "谨慎观望"
        elif overall >= 40:
            grade = "B-"
            recommendation = "建议回避"
        else:
            grade = "C"
            recommendation = "不推荐"
        
        return {
            "score": overall,
            "grade": grade,
            "recommendation": recommendation,
            "weighted_scores": scores,
            "weights": weights
        }
    
    def _generate_ai_judgment(
        self, growth: Dict, profitability: Dict,
        health: Dict, valuation: Dict, dividend: Dict,
        overall: Dict
    ) -> Dict[str, Any]:
        """生成 AI 研判"""
        
        all_signals = []
        all_signals.extend(growth.get("signals", []))
        all_signals.extend(profitability.get("signals", []))
        all_signals.extend(health.get("signals", []))
        all_signals.extend(valuation.get("signals", []))
        all_signals.extend(dividend.get("signals", []))
        
        # 分类信号
        bullish_signals = [s for s in all_signals if "✅" in s or "⭐" in s or "📈" in s or "💰" in s]
        bearish_signals = [s for s in all_signals if "⚠️" in s or "❌" in s]
        
        # 核心逻辑
        core_logic = []
        
        if len(bullish_signals) > len(bearish_signals):
            core_logic.append(f"✅ 积极信号占优 ({len(bullish_signals)} vs {len(bearish_signals)})")
        elif len(bearish_signals) > len(bullish_signals):
            core_logic.append(f"⚠️ 风险信号较多 ({len(bearish_signals)} vs {len(bullish_signals)})")
        else:
            core_logic.append("⚖️ 多空信号均衡")
        
        # 成长质量判断
        if growth.get("trend") == "bullish":
            core_logic.append("📈 成长趋势向好")
        
        # 盈利质量判断
        if profitability.get("grade") in ["A", "B"]:
            core_logic.append("💰 盈利能力优秀")
        
        # 财务健康判断
        if health.get("health_status") == "优秀":
            core_logic.append("🏦 财务状况稳健")
        
        # 估值判断
        if valuation.get("valuation_level") == "低估":
            core_logic.append("🎯 估值处于低位")
        elif valuation.get("valuation_level") == "高估":
            core_logic.append("⏰ 估值偏高，注意风险")
        
        return {
            "grade": overall.get("grade", "N/A"),
            "recommendation": overall.get("recommendation", "N/A"),
            "overall_score": overall.get("score", 0),
            "bullish_signals": bullish_signals,
            "bearish_signals": bearish_signals,
            "core_logic": core_logic,
            "summary": f"基本面{overall.get('grade', 'N/A')}级，{overall.get('recommendation', 'N/A')}"
        }


    def health_check(self, stock_code: str, quote_ctx=None) -> Dict[str, Any]:
        """
        长线投资体检清单 — 9 项核心指标逐一检查
        
        每年财报季花 15 分钟检查这 9 个指标，形成「投资体检表」：
        1. 经营现金流是否为正？是否大于净利润？
        2. ROE 是否 > 10%？近 3 年趋势是上升还是下降？
        3. 资产负债率是否在安全范围内？
        4. 毛利率是否稳定或上升？
        5. 派息率是否在 30-60% 健康区间？
        6. EPS 是否连续增长？
        7. 股息率 TTM 是否达到 4-6% 目标？
        8. 流动比率是否 > 1.0？
        9. ROA 是否 > 5%？
        
        Args:
            stock_code: 股票代码
            quote_ctx: 可选的富途连接上下文（避免重复创建连接）

        Returns:
            {
                "stock_code": "00700",
                "company_name": "腾讯控股",
                "checks": [
                    {"id": 1, "name": "经营现金流", "icon": "💰", "status": "pass|warn|fail|na",
                     "value": "523亿 > 净利润", "detail": "...", "weight": 1},
                    ...
                ],
                "score": 8,          # 通过数
                "total": 9,          # 总项数
                "grade": "A+",       # 9/9=A+, 8/9=A, 7/9=B+, 6/9=B, ...
                "summary": "8/9 项通过..."
            }
        """
        cache_data = self.load_financial_data(stock_code)
        if not cache_data:
            return {"stock_code": stock_code, "error": "无缓存数据", "checks": [], "score": 0, "total": 9, "grade": "N/A", "summary": "无数据"}
        
        summary = cache_data.get("financial_summary", {})
        # 检查 summary 是否为空（REIT/ETF/基金类股票）
        if not summary or (isinstance(summary, dict) and len(summary) <= 1 and not summary.get("报告期")):
            company_name = cache_data.get("company_profile", {}).get("公司名称", stock_code)
            return {
                "stock_code": stock_code,
                "company_name": company_name,
                "error": "该股票无财务指标数据，可能是 REIT/ETF/基金类产品",
                "no_financial_data": True,
                "checks": [],
                "score": 0,
                "total": 9,
                "grade": "N/A",
                "summary": "无财务数据（REIT/ETF/基金类）"
            }
        history = cache_data.get("indicator_history", [])
        company_name = cache_data.get("company_profile", {}).get("公司名称", stock_code)
        is_bank = summary.get("_is_bank_stock", False)
        
        checks = []
        
        # ─────────────────────────────────────────
        # 1. 经营现金流是否为正？是否大于净利润？
        # ─────────────────────────────────────────
        cashflow_hist = cache_data.get("cashflow_history", [])
        ocf_str = summary.get("经营现金流", "")
        ocf_vs_profit_str = summary.get("经营现金流/净利润", "")

        if cashflow_hist and ocf_str and ocf_str != "N/A":
            ocf_val = self._parse_amount_yi(ocf_str)  # 解析 "3030.52亿" → 3030.52
            ocf_ratio = None
            if ocf_vs_profit_str and ocf_vs_profit_str != "N/A":
                ocf_ratio = float(ocf_vs_profit_str)

            ocf_status = "fail"
            ocf_value = f"{ocf_val:.1f}亿"
            ocf_detail = ""

            if ocf_val <= 0:
                ocf_status = "fail"
                ocf_detail = f"经营现金流 {ocf_val:.1f}亿 ≤ 0，盈利质量堪忧"
            elif ocf_ratio is not None and ocf_ratio >= 1.0:
                ocf_status = "pass"
                ocf_detail = f"经营现金流 {ocf_val:.1f}亿 > 净利润（比率 {ocf_ratio:.2f}）✅"
            elif ocf_ratio is not None and ocf_ratio >= 0.7:
                ocf_status = "pass"
                ocf_detail = f"经营现金流 {ocf_val:.1f}亿，为净利润的 {ocf_ratio:.2f} 倍（尚可）"
            elif ocf_ratio is not None and ocf_ratio >= 0.5:
                ocf_status = "warn"
                ocf_detail = f"经营现金流 {ocf_val:.1f}亿，仅为净利润的 {ocf_ratio:.2f} 倍 ⚠️ 偏低"
            else:
                ocf_status = "warn"
                ocf_detail = f"经营现金流 {ocf_val:.1f}亿，远低于净利润 ⚠️"

            # 近 3 年趋势
            if len(cashflow_hist) >= 2:
                vals = [c["经营业务现金净额"] for c in cashflow_hist[:3] if c.get("经营业务现金净额")]
                if len(vals) >= 2:
                    trend = vals[0] - vals[-1]
                    if trend > 0:
                        ocf_detail += f" | 趋势 ↗"
                    elif trend < 0:
                        ocf_detail += f" | 趋势 ↘"

            checks.append({
                "id": 1, "name": "经营现金流", "icon": "💰",
                "status": ocf_status, "value": ocf_value,
                "detail": ocf_detail, "weight": 1
            })
        else:
            checks.append({
                "id": 1, "name": "经营现金流", "icon": "💰",
                "status": "na",
                "value": "数据源暂无",
                "detail": "缓存中无现金流量表数据，请重跑 auto_sync.py 刷新",
                "weight": 1
            })
        
        # ─────────────────────────────────────────
        # 2. ROE 是否 > 10%？近 3 年趋势是上升还是下降？
        # ─────────────────────────────────────────
        roe_current = self._parse_percent(summary.get("ROE", 0))
        roe_status = "fail"
        roe_value = f"{roe_current:.1f}%"
        roe_detail = ""
        
        if roe_current > 10:
            roe_status = "pass"
            roe_detail = f"ROE {roe_current:.1f}% > 10% ✅"
        elif roe_current > 0:
            roe_status = "warn"
            roe_detail = f"ROE {roe_current:.1f}% 低于 10% 阈值"
        else:
            roe_detail = f"ROE {roe_current:.1f}% 为负"
        
        # 近 3 年趋势
        if len(history) >= 3:
            roe_vals = [self._parse_percent(h.get("ROE", 0)) for h in history[:3] if self._parse_percent(h.get("ROE", 0)) > 0]
            if len(roe_vals) >= 2:
                roe_trend = roe_vals[0] - roe_vals[-1]
                if roe_trend > 1:
                    roe_detail += f" | 近3年趋势 ↗ +{roe_trend:.1f}%"
                elif roe_trend < -1:
                    roe_status = "warn" if roe_status == "pass" else roe_status
                    roe_detail += f" | 近3年趋势 ↘ {roe_trend:.1f}%"
                else:
                    roe_detail += f" | 近3年趋势 → {roe_trend:+.1f}%"
        
        checks.append({
            "id": 2, "name": "ROE", "icon": "📈",
            "status": roe_status, "value": roe_value,
            "detail": roe_detail, "weight": 1
        })
        
        # ─────────────────────────────────────────
        # 3. 资产负债率是否在安全范围内？
        # ─────────────────────────────────────────
        debt_ratio = self._parse_percent(summary.get("资产负债率", 0))
        debt_status = "pass"
        debt_detail = ""
        
        if is_bank:
            # 银行股资产负债率普遍 90%+，属正常
            debt_status = "pass"
            debt_detail = f"银行股 资产负债率 {debt_ratio:.1f}%（行业特性，属正常）"
        elif debt_ratio > 80:
            debt_status = "fail"
            debt_detail = f"资产负债率 {debt_ratio:.1f}% > 80% ⚠️ 高风险"
        elif debt_ratio > 70:
            debt_status = "warn"
            debt_detail = f"资产负债率 {debt_ratio:.1f}% 70-80% 偏高"
        elif debt_ratio > 60:
            debt_status = "warn"
            debt_detail = f"资产负债率 {debt_ratio:.1f}% 60-70% 中等"
        else:
            debt_detail = f"资产负债率 {debt_ratio:.1f}% < 60% 安全"
        
        checks.append({
            "id": 3, "name": "资产负债率", "icon": "🏦",
            "status": debt_status, "value": f"{debt_ratio:.1f}%",
            "detail": debt_detail, "weight": 1
        })
        
        # ─────────────────────────────────────────
        # 4. 毛利率是否稳定或上升？
        # ─────────────────────────────────────────
        gm_current = self._parse_percent(summary.get("毛利率", 0))
        gm_status = "na"
        gm_detail = ""
        
        gm_value = "N/A"  # 默认值，防止 is_bank 分支未赋值
        
        # 银行股毛利率不适用
        if is_bank:
            gm_detail = "银行股毛利率不适用"
        elif gm_current > 0:
            gm_value = f"{gm_current:.1f}%"
            if len(history) >= 3:
                gm_vals = [self._parse_percent(h.get("毛利率", 0)) for h in history[:3] if self._parse_percent(h.get("毛利率", 0)) > 0]
                if len(gm_vals) >= 2:
                    gm_trend = gm_vals[0] - gm_vals[-1]
                    gm_std = (sum((v - sum(gm_vals)/len(gm_vals))**2 for v in gm_vals) / len(gm_vals)) ** 0.5
                    
                    if gm_trend > 1:
                        gm_status = "pass"
                        gm_detail = f"毛利率 {gm_current:.1f}% ↗ 上升趋势"
                    elif gm_trend >= -1 and gm_std < 5:
                        gm_status = "pass"
                        gm_detail = f"毛利率 {gm_current:.1f}% → 稳定（波动{gm_std:.1f}%）"
                    elif gm_trend < -3:
                        gm_status = "warn"
                        gm_detail = f"毛利率 {gm_current:.1f}% ↘ 下降{abs(gm_trend):.1f}%"
                    else:
                        gm_status = "pass"
                        gm_detail = f"毛利率 {gm_current:.1f}% 基本稳定"
                else:
                    gm_status = "pass"
                    gm_detail = f"毛利率 {gm_current:.1f}%（历史数据不足）"
            else:
                gm_status = "pass"
                gm_detail = f"毛利率 {gm_current:.1f}%（历史数据不足）"
        else:
            gm_detail = "毛利率数据缺失"
            gm_value = "N/A"
        
        checks.append({
            "id": 4, "name": "毛利率", "icon": "📊",
            "status": gm_status, "value": gm_value if gm_current > 0 else "N/A",
            "detail": gm_detail, "weight": 1
        })
        
        # ─────────────────────────────────────────
        # 5. 派息率是否在 30-60% 健康区间？
        # ─────────────────────────────────────────
        payout = self._parse_percent(summary.get("派息率", 0))
        payout_status = "fail"
        payout_detail = ""
        
        if payout <= 0:
            payout_status = "warn"
            payout_detail = f"派息率 {payout:.1f}% — 未派息或数据缺失"
        elif payout < 20:
            payout_status = "warn"
            payout_detail = f"派息率 {payout:.1f}% < 20% — 分红偏少"
        elif payout <= 60:
            payout_status = "pass"
            payout_detail = f"派息率 {payout:.1f}% — 在 30-60% 健康区间 ✅"
        elif payout <= 80:
            payout_status = "warn"
            payout_detail = f"派息率 {payout:.1f}% — 偏高，留意可持续性"
        else:
            payout_status = "fail"
            payout_detail = f"派息率 {payout:.1f}% > 80% ⚠️ 可能不可持续"
        
        checks.append({
            "id": 5, "name": "派息率", "icon": "💵",
            "status": payout_status, "value": f"{payout:.1f}%",
            "detail": payout_detail, "weight": 1
        })
        
        # ─────────────────────────────────────────
        # 6. EPS 是否连续增长？
        # ─────────────────────────────────────────
        eps_status = "na"
        eps_detail = ""
        
        if len(history) >= 2:
            eps_vals = []
            for h in history[:min(5, len(history))]:
                eps = self._parse_number(h.get("EPS", 0))
                if eps > 0:
                    eps_vals.append(eps)
            
            if len(eps_vals) >= 2:
                eps_growth_count = sum(1 for i in range(1, len(eps_vals)) if eps_vals[i-1] >= eps_vals[i])
                eps_latest = eps_vals[0]
                eps_total_growth = ((eps_vals[0] - eps_vals[-1]) / eps_vals[-1] * 100) if eps_vals[-1] > 0 else 0
                
                if eps_growth_count == len(eps_vals) - 1:
                    eps_status = "pass"
                    eps_detail = f"EPS {eps_latest:.2f} 连续{len(eps_vals)-1}年增长 ↗（累计+{eps_total_growth:.0f}%）"
                elif eps_growth_count >= len(eps_vals) // 2:
                    eps_status = "pass"
                    eps_detail = f"EPS {eps_latest:.2f} 大部分年份增长（{eps_growth_count}/{len(eps_vals)-1}年）"
                else:
                    eps_status = "warn"
                    eps_detail = f"EPS {eps_latest:.2f} 增长不稳定（{eps_growth_count}/{len(eps_vals)-1}年增长）"
                
                if eps_total_growth < -10:
                    eps_status = "fail"
                    eps_detail = f"EPS {eps_latest:.2f} 累计下降{abs(eps_total_growth):.0f}% ⚠️"
            else:
                eps_detail = "EPS 历史数据不足"
        else:
            eps_detail = "EPS 历史数据不足"
        
        eps_current = self._parse_number(history[0].get("EPS", 0)) if history else 0
        checks.append({
            "id": 6, "name": "EPS", "icon": "📝",
            "status": eps_status, "value": f"{eps_current:.2f}" if eps_current > 0 else "N/A",
            "detail": eps_detail, "weight": 1
        })
        
        # ─────────────────────────────────────────
        # 7. 股息率 TTM 是否达到 4-6% 目标？
        # ─────────────────────────────────────────
        # 計算順序: 即時計算(每股派息/即時股價) > 富途TTM > cache靜態值
        div_yield = 0
        div_source = ""
        
        # 嘗試即時計算（與 analyze() 保持一致）
        per_share_div_str = summary.get("每股派息", "N/A")
        if isinstance(per_share_div_str, str):
            per_share_div_str = per_share_div_str.replace("港元", "").replace("元", "")
        per_share_div = self._parse_number(per_share_div_str)
        
        # 嘗試從富途獲取即時股價
        try:
            from futu import RET_OK
            code = stock_code.replace("HK.", "")
            # 重用傳入的 quote_ctx，避免重複創建連接
            if quote_ctx is not None:
                ret, snap = quote_ctx.get_market_snapshot([f"HK.{code}"])
            else:
                # 回退：創建臨時連接（不推薦，僅作兜底）
                import stock_analyzer
                sa = stock_analyzer.StockAnalyzer()
                if sa.quote_ctx:
                    ret, snap = sa.quote_ctx.get_market_snapshot([f"HK.{code}"])
                    sa.quote_ctx.close()  # 立即關閉臨時連接
                else:
                    ret, snap = None, None
            
            if ret == RET_OK and not snap.empty:
                live_price = float(snap.iloc[0].get('last_price', 0))
                if per_share_div > 0 and live_price > 0:
                    div_yield = round(per_share_div / live_price * 100, 2)
                    div_source = f"即時計算({per_share_div}/{live_price})"
                # 富途 TTM 股息率
                if div_yield <= 0:
                    futu_div = snap.iloc[0].get('dividend_yield')
                    if futu_div and futu_div > 0:
                        div_yield = round(float(futu_div), 2)
                        div_source = "富途TTM"
        except Exception as e:
            logger.debug(f"股息率即時計算失敗 {stock_code}: {e}")

        # 回退: 嘗試從 kline_adapter 獲取即時股價
        if div_yield <= 0 and per_share_div > 0:
            try:
                import requests as req
                r = req.get(f'http://localhost:5000/api/tradingview/price/{stock_code}', timeout=3)
                if r.status_code == 200:
                    pd = r.json()
                    price = pd.get('data', {}).get('price', 0)
                    if price and price > 0:
                        div_yield = round(per_share_div / price * 100, 2)
                        div_source = "即時計算(Yahoo)"
            except Exception:
                pass

        # 最終回退: cache 靜態值
        if div_yield <= 0:
            div_yield = self._parse_percent(summary.get("股息率", 0))
            div_source = "cache靜態" if div_yield > 0 else "無數據"
        div_status = "fail"
        div_detail = ""
        
        if div_yield <= 0:
            div_status = "fail"
            div_detail = f"股息率 N/A — 无派息"
        elif div_yield < 2:
            div_status = "fail"
            div_detail = f"股息率 {div_yield:.2f}% < 2% — 偏低 ({div_source})"
        elif div_yield < 4:
            div_status = "warn"
            div_detail = f"股息率 {div_yield:.2f}% — 未达 4% 目标 ({div_source})"
        elif div_yield <= 6:
            div_status = "pass"
            div_detail = f"股息率 {div_yield:.2f}% — 达到 4-6% 目标 ✅ ({div_source})"
        elif div_yield <= 8:
            div_status = "pass"
            div_detail = f"股息率 {div_yield:.2f}% — 丰厚回报 ✅ ({div_source})"
        else:
            div_status = "warn"
            div_detail = f"股息率 {div_yield:.2f}% > 8% — 需警惕可持续性 ({div_source})"
        
        checks.append({
            "id": 7, "name": "股息率TTM", "icon": "🎯",
            "status": div_status, "value": f"{div_yield:.2f}%",
            "detail": div_detail, "weight": 1
        })
        
        # ─────────────────────────────────────────
        # 8. 流动比率是否 > 1.0？
        # ─────────────────────────────────────────
        current_ratio = self._parse_number(summary.get("流动比率", 0))
        cr_status = "na"
        cr_detail = ""
        
        if is_bank:
            cr_detail = "银行股流动比率不适用（行业特性）"
        elif current_ratio > 0:
            if current_ratio >= 1.5:
                cr_status = "pass"
                cr_detail = f"流动比率 {current_ratio:.2f} > 1.5 充裕 ✅"
            elif current_ratio >= 1.0:
                cr_status = "pass"
                cr_detail = f"流动比率 {current_ratio:.2f} > 1.0 合格 ✅"
            elif current_ratio >= 0.8:
                cr_status = "warn"
                cr_detail = f"流动比率 {current_ratio:.2f} 接近 1.0 临界线"
            else:
                cr_status = "fail"
                cr_detail = f"流动比率 {current_ratio:.2f} < 1.0 ⚠️ 短期偿债风险"
        else:
            cr_detail = "流动比率数据缺失"
        
        checks.append({
            "id": 8, "name": "流动比率", "icon": "⚖️",
            "status": cr_status, "value": f"{current_ratio:.2f}" if current_ratio > 0 else "N/A",
            "detail": cr_detail, "weight": 1
        })
        
        # ─────────────────────────────────────────
        # 9. ROA 是否 > 5%？
        # ─────────────────────────────────────────
        roa = self._parse_percent(summary.get("ROA", 0))
        roa_status = "fail"
        roa_detail = ""
        
        if is_bank:
            # 银行股 ROA 普遍 0.5-1.5%，用不同标准
            if roa >= 0.8:
                roa_status = "pass"
                roa_detail = f"银行股 ROA {roa:.2f}% ≥ 0.8% 良好 ✅"
            elif roa >= 0.5:
                roa_status = "warn"
                roa_detail = f"银行股 ROA {roa:.2f}% 中等"
            else:
                roa_status = "fail"
                roa_detail = f"银行股 ROA {roa:.2f}% 偏低"
        elif roa >= 5:
            roa_status = "pass"
            roa_detail = f"ROA {roa:.2f}% > 5% 资产运用效率高 ✅"
        elif roa >= 3:
            roa_status = "warn"
            roa_detail = f"ROA {roa:.2f}% 3-5% 中等"
        elif roa > 0:
            roa_status = "warn"
            roa_detail = f"ROA {roa:.2f}% < 3% 偏低"
        else:
            roa_detail = f"ROA {roa:.2f}% 为负 ⚠️"
        
        checks.append({
            "id": 9, "name": "ROA", "icon": "🏭",
            "status": roa_status, "value": f"{roa:.2f}%",
            "detail": roa_detail, "weight": 1
        })
        
        # ─────────────────────────────────────────
        # 计算总分和评级
        # ─────────────────────────────────────────
        pass_count = sum(1 for c in checks if c["status"] == "pass")
        warn_count = sum(1 for c in checks if c["status"] == "warn")
        fail_count = sum(1 for c in checks if c["status"] == "fail")
        na_count = sum(1 for c in checks if c["status"] == "na")
        effective_total = sum(1 for c in checks if c["status"] != "na")
        
        # 评级: 全通过=A+, 8/9=A, 7/9=B+, 6/9=B, 5/9=C+, 4/9=C, <4=D
        if effective_total == 0:
            grade = "N/A"
        elif pass_count == effective_total:
            grade = "A+"
        elif pass_count >= effective_total * 0.88:
            grade = "A"
        elif pass_count >= effective_total * 0.75:
            grade = "B+"
        elif pass_count >= effective_total * 0.62:
            grade = "B"
        elif pass_count >= effective_total * 0.5:
            grade = "C+"
        elif pass_count >= effective_total * 0.37:
            grade = "C"
        else:
            grade = "D"
        
        # 生成摘要
        summary_parts = []
        if pass_count > 0:
            summary_parts.append(f"{pass_count}项通过")
        if warn_count > 0:
            summary_parts.append(f"{warn_count}项警告")
        if fail_count > 0:
            summary_parts.append(f"{fail_count}项不达标")
        if na_count > 0:
            summary_parts.append(f"{na_count}项暂无数据")
        
        grade_emoji = {"A+": "🏆", "A": "🥇", "B+": "🥈", "B": "🥉", "C+": "📊", "C": "⚠️", "D": "🔴", "N/A": "❓"}
        
        return {
            "stock_code": stock_code,
            "company_name": company_name,
            "checks": checks,
            "score": pass_count,
            "effective_total": effective_total,
            "total": 9,
            "warn_count": warn_count,
            "fail_count": fail_count,
            "na_count": na_count,
            "grade": grade,
            "grade_emoji": grade_emoji.get(grade, ""),
            "summary": f"{pass_count}/{effective_total} 项通过 | {grade} {grade_emoji.get(grade, '')}"
        }


# 测试
if __name__ == "__main__":
    analyzer = FundamentalAnalyzer()
    
    # 测试腾讯
    result = analyzer.analyze("00700")
    
    print("=" * 60)
    print(f"【{result['company_name']}】基本面分析")
    print("=" * 60)
    
    print(f"\n📊 综合评分: {result['overall']['score']:.1f}/100")
    print(f"🏆 评级: {result['overall']['grade']}")
    print(f"📋 建议: {result['overall']['recommendation']}")
    
    print("\n📈 各维度分析:")
    print(f"  成长性: {result['growth']['score']:.1f} ({result['growth']['grade']})")
    print(f"  盈利能力: {result['profitability']['score']:.1f} ({result['profitability']['grade']})")
    print(f"  财务健康: {result['financial_health']['score']:.1f} ({result['financial_health']['grade']})")
    print(f"  估值水平: {result['valuation']['score']:.1f} ({result['valuation']['grade']})")
    print(f"  股息质量: {result['dividend']['score']:.1f} ({result['dividend']['grade']})")
    
    print("\n🤖 AI 研判:")
    judgment = result['ai_judgment']
    print(f"  {judgment['summary']}")
    print(f"  积极信号: {len(judgment['bullish_signals'])}")
    print(f"  风险信号: {len(judgment['bearish_signals'])}")
    
    print("\n📌 核心逻辑:")
    for logic in judgment['core_logic']:
        print(f"  {logic}")
    
    print("\n💡 创新指标:")
    for signal in result['innovation']['signals']:
        print(f"  {signal}")
