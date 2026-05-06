"""
StockAI Strategy Observer — 策略觀察報表生成器
StockAI v1.7 | 2026-04-26

功能:
  - 對 Top 50 體檢股批量回測，生成策略績效排行榜
  - 結合信號追蹤數據，顯示歷史信號勝率
  - 生成 HTML 觀察報表

數據來源:
  - 回測: backtest_engine.py
  - 信號追蹤: signal_tracker.py
  - K 線: stock_analyzer.py（富途 OpenD）
"""

import json, os, time, logging
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def run_batch_backtest(stock_analyzer, codes, top_n=30, period_days=252):
    """
    批量回測 — 對每隻股票跑所有策略

    Args:
        stock_analyzer: StockAnalyzer 實例
        codes: list[str] — 股票代碼
        top_n: int — 最多回測幾隻
        period_days: int — 回測天數（默認 1 年 = 252 個交易日）

    Returns:
        dict — 每隻股票的回測結果
    """
    from backtest_engine import BacktestEngine, STRATEGIES

    results = []
    total = min(len(codes), top_n)

    logger.info(f"批量回測: {total} 隻股票, {len(STRATEGIES)} 個策略, {period_days} 天")

    for i, code in enumerate(codes[:top_n]):
        if (i + 1) % 5 == 0:
            logger.info(f"批量回測進度: {i+1}/{total}...")

        try:
            df = stock_analyzer.get_kline_data(code, days=period_days + 30)
            if df is None or len(df) < 60:
                continue

            stock_result = {
                'code': code,
                'strategies': {},
            }

            for strat_key in STRATEGIES:
                try:
                    engine = BacktestEngine(initial_cash=100000)
                    report = engine.run(df, strat_key)
                    if report and report.get('success'):
                        m = report.get('metrics', {})
                        all_signals = report.get('all_signals', [])
                        last_sig = all_signals[-1]['signal'] if all_signals else 'HOLD'
                        stock_result['strategies'][strat_key] = {
                            'total_return': m.get('total_return', 0),
                            'win_rate': m.get('win_rate', 0),
                            'sharpe': m.get('sharpe_ratio', 0),
                            'max_drawdown': m.get('max_drawdown', 0),
                            'total_trades': report.get('trade_stats', {}).get('total_trades', 0),
                            'last_signal': last_sig,
                        }
                except Exception as e:
                    logger.debug(f"回測失敗 {code} {strat_key}: {e}")

            if stock_result['strategies']:
                results.append(stock_result)

            time.sleep(0.3)

        except Exception as e:
            logger.debug(f"回測失敗 {code}: {e}")

    logger.info(f"批量回測完成: {len(results)} 隻股票")
    return results


def aggregate_strategy_performance(batch_results):
    """
    匯總批量回測結果，生成策略排行

    Args:
        batch_results: list — run_batch_backtest 的返回值

    Returns:
        dict — 每個策略的匯總績效
    """
    from backtest_engine import STRATEGIES

    agg = {}
    for strat_key, strat_cls in STRATEGIES.items():
        agg[strat_key] = {
            'name': strat_cls.name,
            'description': strat_cls.description,
            'stocks_tested': 0,
            'avg_return': [],
            'avg_win_rate': [],
            'avg_sharpe': [],
            'avg_max_dd': [],
            'buy_signals': 0,
            'sell_signals': 0,
        }

    for stock in batch_results:
        for strat_key, perf in stock.get('strategies', {}).items():
            if strat_key not in agg:
                continue
            a = agg[strat_key]
            a['stocks_tested'] += 1
            if perf.get('total_return') is not None:
                a['avg_return'].append(perf['total_return'])
            if perf.get('win_rate') is not None:
                a['avg_win_rate'].append(perf['win_rate'])
            if perf.get('sharpe') is not None:
                a['avg_sharpe'].append(perf['sharpe'])
            if perf.get('max_drawdown') is not None:
                a['avg_max_dd'].append(perf['max_drawdown'])
            if perf.get('last_signal') == 'BUY':
                a['buy_signals'] += 1
            elif perf.get('last_signal') == 'SELL':
                a['sell_signals'] += 1

    # 計算平均值
    for strat_key, a in agg.items():
        a['avg_return'] = round(np.mean(a['avg_return']), 2) if a['avg_return'] else 0
        a['avg_win_rate'] = round(np.mean(a['avg_win_rate']), 1) if a['avg_win_rate'] else 0
        a['avg_sharpe'] = round(np.mean(a['avg_sharpe']), 2) if a['avg_sharpe'] else 0
        a['avg_max_dd'] = round(np.mean(a['avg_max_dd']), 2) if a['avg_max_dd'] else 0
        # 綜合評分 = 收益*0.3 + 勝率*0.3 + 夏普*20*0.2 - 最大回撤*0.2
        a['composite_score'] = round(
            a['avg_return'] * 0.3
            + a['avg_win_rate'] * 0.3
            + a['avg_sharpe'] * 20 * 0.2
            - abs(a['avg_max_dd']) * 0.2,
            1
        )

    return agg


def generate_observer_html(strategy_perf, signal_stats=None, signal_trend=None):
    """
    生成策略觀察報表 HTML

    Args:
        strategy_perf: dict — aggregate_strategy_performance 的返回值
        signal_stats: dict | None — signal_tracker.get_strategy_stats 的返回值
        signal_trend: list | None — signal_tracker.get_signal_accuracy_trend 的返回值

    Returns:
        str — HTML 報表
    """
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    # 按綜合評分排序
    sorted_strats = sorted(strategy_perf.items(), key=lambda x: x[1].get('composite_score', 0), reverse=True)

    # 策略排行表
    rows = ''
    for rank, (key, s) in enumerate(sorted_strats, 1):
        # 回測顏色
        ret_color = '#ef4444' if s['avg_return'] > 0 else '#10b981' if s['avg_return'] < 0 else '#94a3b8'
        wr_color = '#10b981' if s['avg_win_rate'] >= 50 else '#f59e0b' if s['avg_win_rate'] >= 40 else '#ef4444'
        dd_color = '#ef4444' if s['avg_max_dd'] < -15 else '#f59e0b' if s['avg_max_dd'] < -10 else '#10b981'
        score_color = '#10b981' if s['composite_score'] >= 10 else '#f59e0b' if s['composite_score'] >= 0 else '#ef4444'

        # 信號追蹤勝率（如果有數據）
        sig_info = ''
        if signal_stats and key in signal_stats:
            ss = signal_stats[key]
            buy_wr = ss['buy_signals']['win_rate']
            sell_wr = ss['sell_signals']['win_rate']
            sig_info = f'''
                <td style="color:{'#10b981' if buy_wr >= 55 else '#f59e0b' if buy_wr >= 45 else '#ef4444'}; font-weight:600">{buy_wr}%</td>
                <td style="color:{'#10b981' if sell_wr >= 55 else '#f59e0b' if sell_wr >= 45 else '#ef4444'}; font-weight:600">{sell_wr}%</td>
                <td>{ss.get('total', 0)}</td>
            '''
        else:
            sig_info = '<td colspan="3" style="color:var(--text-muted)">累積中...</td>'

        # 最新信號統計
        signal_counts = f"{s['buy_signals']}🟢 / {s['sell_signals']}🔴"

        rows += f'''
        <tr>
            <td style="font-weight:600; color:var(--accent)">{rank}</td>
            <td style="font-weight:600">{s['name']}</td>
            <td style="color:var(--text-muted); font-size:12px">{s['description']}</td>
            <td>{s['stocks_tested']}</td>
            <td style="color:{ret_color}; font-weight:600">{s['avg_return']:+.2f}%</td>
            <td style="color:{wr_color}; font-weight:600">{s['avg_win_rate']:.1f}%</td>
            <td style="font-weight:600">{s['avg_sharpe']:.2f}</td>
            <td style="color:{dd_color}; font-weight:600">{s['avg_max_dd']:.2f}%</td>
            <td style="color:{score_color}; font-weight:700">{s['composite_score']:.1f}</td>
            {sig_info}
            <td>{signal_counts}</td>
        </tr>'''

    # 勝率趨勢圖表數據
    trend_chart = ''
    if signal_trend and len(signal_trend) > 1:
        weeks = [t['week'][5:] for t in signal_trend]  # MM-DD
        rates = [t['win_rate'] for t in signal_trend]
        counts = [t['total_signals'] for t in signal_trend]
        trend_chart = f'''
        <div class="section">
            <h3>📊 信號勝率趨勢（週）</h3>
            <div id="trend-chart" style="height:280px;"></div>
        </div>
        <script>
        var trendOptions = {{
            chart: {{ type: 'line', height: 280, toolbar: {{ show: false }}, background: 'transparent' }},
            series: [{{
                name: '勝率 %',
                data: {rates}
            }}],
            xaxis: {{
                categories: {json.dumps(weeks)},
                labels: {{ style: {{ colors: '#94a3b8', fontSize: '11px' }} }}
            }},
            yaxis: {{
                min: 30, max: 80,
                labels: {{ style: {{ colors: '#94a3b8' }}, formatter: function(v) {{ return v + '%'; }} }}
            }},
            stroke: {{ width: 3, curve: 'smooth' }},
            colors: ['#3b82f6'],
            fill: {{ type: 'gradient', gradient: {{ shadeIntensity: 1, opacityFrom: 0.4, opacityTo: 0.05 }} }},
            grid: {{ borderColor: '#1e293b', strokeDashArray: 3 }},
            annotations: {{
                yaxis: [{{ y: 50, borderColor: '#f59e0b', strokeDashArray: 5, label: {{ text: '50% 基準線', style: {{ color: '#f59e0b', fontSize: '11px' }} }} }}]
            }},
            tooltip: {{ theme: 'dark' }},
            dataLabels: {{ enabled: false }}
        }};
        var trendChart = new ApexCharts(document.querySelector("#trend-chart"), trendOptions);
        trendChart.render();
        </script>'''

    # 概覽卡片
    total_signals = sum(ss.get('total', 0) for ss in (signal_stats or {}).values())
    avg_wr = 0
    if signal_stats:
        all_correct = sum(ss.get('correct', 0) for ss in signal_stats.values())
        all_total = sum(ss.get('total', 0) for ss in signal_stats.values())
        avg_wr = round(all_correct / max(all_total, 1) * 100, 1)

    best_strat = sorted_strats[0] if sorted_strats else ('', {'name': 'N/A', 'composite_score': 0})

    html = f'''<!DOCTYPE html>
<html lang="zh-HK">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>StockAI 策略觀察報表 | {now.split()[0]}</title>
<script src="https://cdn.jsdelivr.net/npm/apexcharts"></script>
<style>
:root {{ --bg: #0b1120; --bg-card: #111827; --border: #1e293b; --accent: #3b82f6; --green: #10b981; --red: #ef4444; --yellow: #f59e0b; --text: #e2e8f0; --text-muted: #94a3b8; --radius: 12px; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; line-height: 1.6; }}
.container {{ max-width: 1500px; margin: 0 auto; padding: 20px; }}
.header {{ text-align: center; padding: 30px 0 20px; border-bottom: 1px solid var(--border); margin-bottom: 24px; }}
.header h1 {{ font-size: 26px; font-weight: 700; margin-bottom: 6px; }}
.header .subtitle {{ color: var(--text-muted); font-size: 13px; }}
.overview {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin-bottom: 24px; }}
.ov-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px 20px; text-align: center; }}
.ov-label {{ font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }}
.ov-val {{ font-size: 28px; font-weight: 700; }}
.ov-val.green {{ color: var(--green); }}
.ov-val.red {{ color: var(--red); }}
.ov-val.yellow {{ color: var(--yellow); }}
.ov-val.blue {{ color: var(--accent); }}
.section {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 20px; }}
.section h3 {{ font-size: 16px; font-weight: 600; margin-bottom: 14px; color: var(--accent); }}
.note {{ padding: 12px 16px; background: rgba(59,130,246,0.08); border: 1px solid rgba(59,130,246,0.2); border-radius: 10px; margin-bottom: 20px; font-size: 13px; color: var(--text-muted); }}
.note strong {{ color: var(--accent); }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
thead {{ position: sticky; top: 0; z-index: 10; }}
th {{ background: var(--bg-card); color: var(--text-muted); font-weight: 600; text-align: left; padding: 10px 8px; border-bottom: 2px solid var(--border); font-size: 11px; white-space: nowrap; }}
td {{ padding: 8px; border-bottom: 1px solid rgba(255,255,255,0.03); font-variant-numeric: tabular-nums; white-space: nowrap; }}
tr:hover {{ background: rgba(255,255,255,0.03); }}
.score-badge {{ display: inline-block; padding: 2px 8px; border-radius: 6px; font-weight: 700; font-size: 12px; }}
.score-high {{ background: rgba(16,185,129,0.15); color: #10b981; }}
.score-mid {{ background: rgba(245,158,11,0.15); color: #f59e0b; }}
.score-low {{ background: rgba(239,68,68,0.15); color: #ef4444; }}
.footer {{ text-align: center; padding: 20px; color: var(--text-muted); font-size: 12px; border-top: 1px solid var(--border); margin-top: 20px; }}
@media (max-width: 768px) {{ .overview {{ grid-template-columns: 1fr 1fr; }} table {{ font-size: 11px; }} th, td {{ padding: 6px 4px; }} }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>🔍 StockAI 策略觀察報表</h1>
        <div class="subtitle">{now} | {len(strategy_perf)} 個策略回測 + 信號追蹤 | 數據持續積累中</div>
    </div>

    <div class="overview">
        <div class="ov-card"><div class="ov-label">策略數量</div><div class="ov-val blue">{len(strategy_perf)}</div></div>
        <div class="ov-card"><div class="ov-label">累積信號數</div><div class="ov-val yellow">{total_signals}</div></div>
        <div class="ov-card"><div class="ov-label">平均信號勝率</div><div class="ov-val {'green' if avg_wr >= 50 else 'red'}">{avg_wr}%</div></div>
        <div class="ov-card"><div class="ov-label">最佳策略</div><div class="ov-val green">{best_strat[1]['name']}</div></div>
    </div>

    <div class="note">
        <strong>說明:</strong> 綜合評分 = 收益×0.3 + 勝率×0.3 + 夏普×20×0.2 - 最大回撤×0.2。<br>
        <strong>信號追蹤勝率</strong> = 買入信號後 N 日實際上漲的比例 / 賣出信號後實際下跌的比例。數據越多越準確，初期僅供參考。<br>
        <strong>回測 ≠ 預測。</strong> 歷史表現不代表未來收益，僅作為策略篩選參考。
    </div>

    <div class="section">
        <h3>🏆 策略績效排行榜</h3>
        <div style="overflow-x:auto;">
        <table>
            <thead><tr>
                <th>#</th><th>策略</th><th>說明</th><th>測試股數</th>
                <th>平均收益</th><th>平均勝率</th><th>平均夏普</th><th>平均最大回撤</th><th>綜合評分</th>
                <th colspan="3" style="text-align:center">📈 信號追蹤勝率 (5日)</th>
                <th>今日信號</th>
            </tr></thead>
            <tbody>{rows}</tbody>
        </table>
        </div>
    </div>

    {trend_chart}

    <div class="footer">
        ⚠️ 免責聲明: 本報表僅基於歷史回測和信號追蹤數據，不構成投資建議。市場有風險，投資需謹慎。<br>
        Powered by StockAI v1.7 | Generated at {now}
    </div>
</div>
</body></html>'''

    return html
