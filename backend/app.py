from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from stock_analyzer import StockAnalyzer
from intraday_analyzer import IntradayAnalyzer
import os
import json
import math
import logging
import requests  # 添加 requests 库
from datetime import datetime
from pathlib import Path

# watchlist.json 路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("STOCKAI_DATA_DIR", os.path.join(os.path.dirname(BASE_DIR), "data"))
os.makedirs(DATA_DIR, exist_ok=True)
WATCHLIST_PATH = os.environ.get("WATCHLIST_PATH", os.path.join(DATA_DIR, "watchlist.json"))

# 導入新增模組 - 多模型AI分析
from multi_model_ai import MultiModelAIAnalyst
# 導入新聞輿情模組
from news_fetcher import fetch_stock_news, fetch_market_news
from sentiment_analyzer import analyze_news_sentiment

# 導入港交所財務報表模組
from hkex_financials import get_hkex_financial_data, get_financial_summary

# 導入基本面分析引擎
from fundamental_analyzer import FundamentalAnalyzer

# 導入模擬交易 AI 決策引擎
from paper_trading_agent import (
    get_account, ai_decide, PaperAccount, RiskManager
)

# 導入回測引擎
from backtest_engine import BacktestEngine, get_available_strategies, STRATEGIES
from signal_tracker import SignalTracker
from strategy_observer import run_batch_backtest, aggregate_strategy_performance, generate_observer_html

# 導入模組重載工具
import importlib

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, 
            static_folder='../frontend',
            static_url_path='')
CORS(app, origins='*', supports_credentials=True)

# 掃描緩存（供 refresh-missing 合併使用）
_scan_cache = None

# 初始化分析器（使用富途）
try:
    analyzer = StockAnalyzer(futu_host='127.0.0.1', futu_port=11111)
    intraday_analyzer = IntradayAnalyzer(analyzer.quote_ctx)
    multi_ai = MultiModelAIAnalyst()  # 初始化多模型AI分析器
    print("✅ StockAnalyzer 初始化成功")
    print("✅ Multi-Model AI 分析器 初始化成功")
except Exception as e:
    print(f"❌ StockAnalyzer 初始化失敗: {e}")
    analyzer = None
    intraday_analyzer = None
    multi_ai = None

# ==================== DeepSeek AI 配置 ====================
# 已迁移至 .env — 由 config_keys.py 读取环境变量
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")

# ==================== DeepSeek AI 分析函数 ====================
def get_deepseek_analysis(stock_data, question=""):
    """调用 DeepSeek API 分析股票"""
    
    tech = stock_data.get('technicals', {})
    
    # 构建提示词
    prompt = f"""你是一位专业的股票分析师，请根据以下股票数据回答问题。

【股票基本信息】
- 股票代码: {stock_data.get('symbol')}
- 股票名称: {stock_data.get('name')}
- 当前价格: ${stock_data.get('price')}
- 涨跌幅: {stock_data.get('change_percent')}%
- 今日高低: ${stock_data.get('low')} - ${stock_data.get('high')}
- 52周高低: ${stock_data.get('week_low')} - ${stock_data.get('week_high')}

【技术指标】
- MA5: ${tech.get('ma5', '--')}
- MA10: ${tech.get('ma10', '--')}
- MA20: ${tech.get('ma20', '--')}
- RSI(14): {tech.get('rsi14', '--')}
- MACD: DIF={tech.get('macd_dif', '--')}, DEA={tech.get('macd_dea', '--')}
- 成交量比: {tech.get('volume_ratio', '--')}
- 布林带上轨: ${tech.get('bb_upper', '--')}
- 布林带下轨: ${tech.get('bb_lower', '--')}
- KDJ: K={tech.get('kdj_k', '--')}, D={tech.get('kdj_d', '--')}, J={tech.get('kdj_j', '--')}
- ATR: {tech.get('atr', '--')}

【用户问题】
{question if question else '请给出完整的技术面分析报告，包括趋势判断、关键价位、操作建议。'}

请用专业、详细的语言回答，使用繁体中文，不要截断输出。"""

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
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
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=90)
        result = response.json()
        
        if 'choices' in result and len(result['choices']) > 0:
            return result['choices'][0]['message']['content']
        else:
            error_msg = result.get('error', {}).get('message', '未知错误')
            return f"分析失败: {error_msg}"
    except requests.exceptions.Timeout:
        return "API 调用超时，请稍后重试。"
    except requests.exceptions.ConnectionError:
        return "网络连接失败，请检查网络。"
    except Exception as e:
        return f"API 调用失败: {str(e)}"


@app.route('/')
def index():
    """首頁"""
    return send_from_directory('../frontend', 'index.html')


@app.route('/observer')
def observer_page():
    """策略觀察頁面"""
    return send_from_directory('../frontend', 'strategy_observer.html')


@app.route('/reports/<path:filename>')
def serve_report(filename):
    """提供報告文件"""
    return send_from_directory('../backend/reports', filename)


@app.route('/watchlist.json')
def get_watchlist():
    """获取自选股列表"""
    try:
        if os.path.exists(WATCHLIST_PATH):
            with open(WATCHLIST_PATH, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        return jsonify({'stocks': [], 'error': 'watchlist.json not found'})
    except Exception as e:
        return jsonify({'stocks': [], 'error': str(e)}), 500


@app.route('/css/<path:path>')
def send_css(path):
    """CSS 文件"""
    return send_from_directory('../frontend/css', path)


@app.route('/js/<path:path>')
def send_js(path):
    """JS 文件"""
    return send_from_directory('../frontend/js', path)


@app.route('/api/status')
def get_status():
    """獲取系統狀態"""
    if analyzer is None:
        return jsonify({
            'success': False,
            'error': 'StockAnalyzer 未初始化'
        }), 500
    
    return jsonify({
        'success': True,
        'data': {
            'futu_connected': analyzer.quote_ctx is not None,
            'cache_size': len(analyzer.cache)
        }
    })


@app.route('/api/stock/<symbol>')
def get_stock(symbol):
    data = analyzer.get_stock_data(symbol)
    if data:
        def clean_value(v):
            if v is None:
                return None
            if isinstance(v, float):
                if math.isnan(v) or math.isinf(v):
                    return None
            if isinstance(v, dict):
                return {k: clean_value(vk) for k, vk in v.items()}
            if isinstance(v, list):
                return [clean_value(item) for item in v]
            return v
        
        cleaned_data = clean_value(data)
        
        # 確保 pe 唔係 NaN
        if 'pe' in cleaned_data and cleaned_data['pe'] is None:
            cleaned_data['pe'] = 'N/A'
        
        return app.response_class(
            response=json.dumps({'success': True, 'data': cleaned_data}, default=str, ensure_ascii=False),
            status=200,
            mimetype='application/json'
        )
    return jsonify({'success': False, 'error': '無法獲取股票數據'}), 404


@app.route('/api/stock/<symbol>/history')
def get_stock_history(symbol):
    """獲取歷史K線數據（用於圖表）"""
    if analyzer is None:
        return jsonify({
            'success': False,
            'error': '系統未就緒'
        }), 500
    
    period = request.args.get('period', '1mo')
    data = analyzer.get_kline_for_chart(symbol, period)
    
    return jsonify({
        'success': True,
        'data': data
    })


@app.route('/api/stock/<symbol>/bb')
def get_bollinger_bands(symbol):
    """獲取保力加通道數據"""
    period = request.args.get('period', '1mo')
    timestamps, upper, middle, lower = analyzer.get_bb_bands_for_chart(symbol, period)
    
    return jsonify({
        'success': True,
        'timestamps': [int(ts.timestamp() * 1000) for ts in timestamps],
        'upper': upper,
        'middle': middle,
        'lower': lower
    })


# 熱門股票列表
HOT_STOCKS = [
    {'code': '0700.HK', 'name': '騰訊控股'},
    {'code': '9988.HK', 'name': '阿里巴巴'},
    {'code': '0005.HK', 'name': '匯豐控股'},
    {'code': 'AAPL', 'name': '蘋果'},
    {'code': 'TSLA', 'name': '特斯拉'},
    {'code': 'BTC-USD', 'name': '比特幣'},
    {'code': 'MSFT', 'name': '微軟'},
    {'code': 'GOOGL', 'name': '谷歌'},
    {'code': 'NVDA', 'name': '英偉達'},
    {'code': 'AMD', 'name': '超微半導體'},
    {'code': '600519.SS', 'name': '貴州茅台'},
    {'code': '000858.SZ', 'name': '五糧液'},
    {'code': '1810.HK', 'name': '小米集團'},
    {'code': '3690.HK', 'name': '美團'},
    {'code': '9618.HK', 'name': '京東集團'}
]


@app.route('/api/predict/<symbol>')
def get_prediction(symbol):
    """獲取 AI 預測"""
    try:
        prediction = analyzer.get_ai_prediction(symbol)
        if prediction:
            return jsonify({'success': True, 'data': prediction})
        return jsonify({'success': False, 'error': '無法獲取預測數據'}), 404
    except Exception as e:
        print(f"預測錯誤: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/hot-stocks')
def get_hot_stocks():
    """獲取熱門股票列表"""
    return jsonify({
        'success': True,
        'data': HOT_STOCKS
    })


@app.route('/api/search')
def search_stock():
    """搜尋股票（在熱門列表中搜尋）"""
    query = request.args.get('q', '').upper().strip()
    if not query:
        return jsonify({'success': True, 'data': []})
    
    results = [
        stock for stock in HOT_STOCKS 
        if query in stock['code'] or query in stock['name']
    ]
    
    return jsonify({
        'success': True,
        'data': results
    })


@app.route('/api/realtime/<symbol>')
def get_realtime(symbol):
    """獲取即時報價（簡化版）"""
    if analyzer is None:
        return jsonify({
            'success': False,
            'error': '系統未就緒'
        }), 500
    
    data = analyzer.get_stock_data(symbol)
    
    if data:
        return jsonify({
            'success': True,
            'data': {
                'price': data['price'],
                'change': data['change'],
                'change_percent': data['change_percent'],
                'volume': data['volume']
            }
        })
    else:
        return jsonify({
            'success': False,
            'error': '無法獲取數據'
        }), 404


# ==================== DeepSeek AI 分析路由 ====================
@app.route('/api/ai/analyze/<symbol>', methods=['GET'])
def ai_analyze_stock(symbol):
    """AI 分析股票（DeepSeek）"""
    if analyzer is None:
        return jsonify({
            'success': False,
            'error': '系統未就緒'
        }), 500
    
    try:
        # 獲取股票數據
        stock_data = analyzer.get_stock_data(symbol)
        if not stock_data:
            return jsonify({'success': False, 'error': '無法獲取股票數據'}), 404
        
        # 獲取用戶問題（可選）
        question = request.args.get('q', '')
        
        # 調用 DeepSeek API 分析
        analysis = get_deepseek_analysis(stock_data, question)
        
        return jsonify({
            'success': True,
            'data': {
                'analysis': analysis,
                'symbol': symbol,
                'question': question,
                'model': 'deepseek-chat'
            }
        })
        
    except Exception as e:
        logger.error(f"AI 分析失敗: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/analyze', methods=['POST'])
def ai_analyze_with_custom_data():
    """AI 分析（使用自定義數據）"""
    try:
        data = request.get_json()
        stock_data = data.get('stock_data', {})
        question = data.get('question', '')
        
        if not stock_data:
            return jsonify({'success': False, 'error': '缺少股票數據'}), 400
        
        analysis = get_deepseek_analysis(stock_data, question)
        
        return jsonify({
            'success': True,
            'data': {
                'analysis': analysis,
                'question': question
            }
        })
        
    except Exception as e:
        logger.error(f"AI 分析失敗: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 每日交易建議 API 路由 ====================

@app.route('/api/daily-report/single', methods=['POST'])
def daily_report_single():
    """
    單股完整分析 (技術指標 + 資金流向 + 交易建議)
    
    Body: { "code": "00700" }
    Returns: { "success": true, "html": "...", "data": {...} }
    """
    try:
        from daily_report import DataFetcher, generate_single_stock_report, render_single_html
        params = request.get_json() or {}
        code = params.get('code', '').strip()
        if not code:
            return jsonify({'success': False, 'error': '缺少股票代碼'}), 400

        fetcher = DataFetcher()
        if not fetcher.connect():
            return jsonify({'success': False, 'error': '富途連接失敗，請確認 OpenD 已啟動'}), 503

        try:
            analysis = generate_single_stock_report(fetcher, code)
            if 'error' in analysis:
                return jsonify({'success': False, 'error': analysis['error']}), 404

            report_time = datetime.now()
            html = render_single_html(analysis, report_time)

            # 也保存到 reports 目錄
            from pathlib import Path
            output_dir = Path(__file__).resolve().parent / 'reports'
            output_dir.mkdir(parents=True, exist_ok=True)
            date_str = report_time.strftime('%Y%m%d_%H%M')
            html_path = output_dir / f"single_{code}_{date_str}.html"
            html_path.write_text(html, encoding='utf-8')
            logger.info(f"單股報告已保存: {html_path}")

            return jsonify({
                'success': True,
                'html': html,
                'data': {
                    'code': code,
                    'name': analysis.get('name', code),
                    'price': analysis.get('current_price'),
                    'change_pct': analysis.get('change_pct'),
                    'cf_signal': analysis.get('capital_flow', {}).get('signal'),
                    'votes_consensus': analysis.get('votes', {}).get('consensus'),
                }
            })
        finally:
            fetcher.close()

    except Exception as e:
        logger.error(f"單股報告生成失敗: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/daily-report/scan', methods=['POST'])
def daily_report_scan():
    """
    Top N 體檢 + 資金流向掃描
    
    Body: { "top": 200 }
    Returns: { "success": true, "html": "...", "count": 200 }
    """
    try:
        from daily_report import DataFetcher, run_scan_mode, render_scan_html
        params = request.get_json() or {}
        top_n = min(int(params.get('top', 200)), 300)

        fetcher = DataFetcher()
        if not fetcher.connect():
            return jsonify({'success': False, 'error': '富途連接失敗'}), 503

        try:
            stocks, missing_codes = run_scan_mode(fetcher, top_n)
            if not stocks:
                return jsonify({'success': False, 'error': '無有效掃描結果'}), 404

            report_time = datetime.now()
            html = render_scan_html(stocks, report_time)

            # 模組級緩存，供 refresh-missing 合併使用
            global _scan_cache
            _scan_cache = {'stocks': stocks, 'report_time': report_time}

            # 保存
            from pathlib import Path
            output_dir = Path(__file__).resolve().parent / 'reports'
            output_dir.mkdir(parents=True, exist_ok=True)
            date_str = report_time.strftime('%Y%m%d_%H%M')
            html_path = output_dir / f"scan_top{top_n}_{date_str}.html"
            html_path.write_text(html, encoding='utf-8')
            logger.info(f"掃描報告已保存: {html_path}")

            return jsonify({
                'success': True,
                'html': html,
                'count': len(stocks),
                'missing': missing_codes,
                'missing_count': len(missing_codes),
                'inst_inflow': len([s for s in stocks if s.get('cf_institution', 0) > 0]),
            })
        finally:
            fetcher.close()

    except Exception as e:
        logger.error(f"掃描報告生成失敗: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/daily-report/refresh-missing', methods=['POST'])
def daily_report_refresh_missing():
    """
    只重拉指定股票的資金流向，合併到上次掃描結果並重新渲染完整 HTML
    
    Body: { "codes": ["00700", "09988", ...] }
    Returns: { "success": true, "html": "...", "refreshed": N, "still_missing": [...] }
    """
    try:
        from daily_report import DataFetcher, render_scan_html
        global _scan_cache
        params = request.get_json() or {}
        codes = params.get('codes', [])
        if not codes:
            return jsonify({'success': False, 'error': '缺少股票代碼列表'}), 400
        if not _scan_cache:
            return jsonify({'success': False, 'error': '無緩存數據，請重新掃描'}), 400

        fetcher = DataFetcher()
        if not fetcher.connect():
            return jsonify({'success': False, 'error': '富途連接失敗'}), 503

        try:
            import time
            refreshed = 0
            still_missing = []
            stocks = _scan_cache['stocks']

            for code in codes:
                cf = fetcher.get_capital_flow(code)
                if cf:
                    # 合併到緩存的 stocks 列表
                    details = cf.get('details', {})
                    for s in stocks:
                        if s['code'] == code:
                            s['capital_flow'] = cf
                            s['cf_raw'] = cf.get('raw', 0)
                            s['cf_super'] = details.get('super', 0)
                            s['cf_big'] = details.get('big', 0)
                            s['cf_mid'] = details.get('mid', 0)
                            s['cf_sml'] = details.get('sml', 0)
                            s['cf_institution'] = details.get('super', 0) + details.get('big', 0)
                            break
                    refreshed += 1
                else:
                    still_missing.append(code)
                time.sleep(0.4)

            # 重新渲染完整 HTML（包含更新後的數據）
            html = render_scan_html(stocks, _scan_cache['report_time'])

            # 更新緩存
            _scan_cache['stocks'] = stocks

            # 重新排序（按機構淨流入）
            # 注意：不需要重新排序，保持原始排名

            return jsonify({
                'success': True,
                'html': html,
                'refreshed': refreshed,
                'still_missing': still_missing,
                'still_missing_count': len(still_missing),
            })
        finally:
            fetcher.close()

    except Exception as e:
        logger.error(f"刷新缺失數據失敗: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/daily-report/portfolio', methods=['POST'])
def daily_report_portfolio():
    """
    持倉報告（原有 default 模式）
    
    Body: {} (optional)
    Returns: { "success": true, "html": "..." }
    """
    try:
        from daily_report import (
            DataFetcher, load_portfolio, generate_stock_analysis,
            generate_html_report
        )
        from pathlib import Path

        report_time = datetime.now()
        output_dir = Path(__file__).resolve().parent / 'reports'
        output_dir.mkdir(parents=True, exist_ok=True)

        portfolio = load_portfolio()
        if not portfolio:
            return jsonify({'success': False, 'error': '無法讀取持倉數據'}), 404

        holdings = portfolio.get('holdings', [])
        if not holdings:
            return jsonify({'success': False, 'error': '當前無持倉'}), 404

        fetcher = DataFetcher()
        if not fetcher.connect():
            return jsonify({'success': False, 'error': '富途連接失敗'}), 503

        try:
            analyses = []
            price_map = {}
            for h in holdings:
                code = h.get('code', '')
                qty = h.get('quantity', 0)
                avg = h.get('avg_cost', 0)
                logger.info(f"分析 {code}...")
                try:
                    analysis = generate_stock_analysis(fetcher, code, qty, avg)
                    analyses.append(analysis)
                    if 'error' not in analysis:
                        price_map[code] = analysis['current_price']
                except Exception as e:
                    analyses.append({'code': code, 'error': str(e)})

            if price_map:
                portfolio = load_portfolio(price_map)

            html = generate_html_report(portfolio, analyses, report_time)

            date_str = report_time.strftime('%Y%m%d_%H%M')
            html_path = output_dir / f"report_{date_str}.html"
            html_path.write_text(html, encoding='utf-8')
            logger.info(f"持倉報告已保存: {html_path}")

            return jsonify({
                'success': True,
                'html': html,
                'holdings_count': len(holdings),
                'total_assets': portfolio.get('total_assets', 0),
            })
        finally:
            fetcher.close()

    except Exception as e:
        logger.error(f"持倉報告生成失敗: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    """404 錯誤處理"""
    return jsonify({
        'success': False,
        'error': 'API 不存在'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """500 錯誤處理"""
    return jsonify({
        'success': False,
        'error': '伺服器內部錯誤'
    }), 500


# ==================== 日內交易 API 路由 ====================

@app.route('/api/intraday/kline/<symbol>')
def get_intraday_kline(symbol):
    """獲取日內 K線數據"""
    if intraday_analyzer is None:
        return jsonify({'success': False, 'error': '日內分析器未初始化'}), 500
    
    period = request.args.get('period', '15m')
    days = int(request.args.get('days', 5))
    
    try:
        data = intraday_analyzer.get_intraday_kline(symbol, period, days)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        logger.error(f"獲取日內 K線失敗: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/intraday/vwap/<symbol>')
def get_intraday_vwap(symbol):
    """獲取 VWAP 數據"""
    if intraday_analyzer is None:
        return jsonify({'success': False, 'error': '日內分析器未初始化'}), 500
    
    try:
        data = intraday_analyzer.calculate_vwap(symbol)
        if data:
            return jsonify({'success': True, 'data': data})
        return jsonify({'success': False, 'error': '無法計算 VWAP'}), 404
    except Exception as e:
        logger.error(f"獲取 VWAP 失敗: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/intraday/indicators/<symbol>')
def get_intraday_indicators(symbol):
    """獲取日內技術指標"""
    if intraday_analyzer is None:
        return jsonify({'success': False, 'error': '日內分析器未初始化'}), 500
    
    try:
        data = intraday_analyzer.calculate_intraday_indicators(symbol)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        logger.error(f"獲取日內指標失敗: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/intraday/orderbook/<symbol>')
def get_intraday_orderbook(symbol):
    """獲取 Level 2 盤口數據（需要權限）"""
    if intraday_analyzer is None:
        return jsonify({'success': False, 'error': '日內分析器未初始化'}), 500
    
    num = request.args.get('num', 10, type=int)
    try:
        data = intraday_analyzer.get_order_book(symbol, num)
        if data:
            return jsonify({'success': True, 'data': data})
        return jsonify({'success': False, 'error': '無法獲取盤口數據'}), 404
    except Exception as e:
        logger.error(f"獲取盤口數據失敗: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/intraday/ticker/<symbol>')
def get_intraday_ticker(symbol):
    """獲取即時 Tick 數據（需要權限）"""
    if intraday_analyzer is None:
        return jsonify({'success': False, 'error': '日內分析器未初始化'}), 500
    
    num = request.args.get('num', 100, type=int)
    try:
        data = intraday_analyzer.get_realtime_ticker(symbol, num)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        logger.error(f"獲取 Tick 數據失敗: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/intraday/price-levels/<symbol>')
def get_intraday_price_levels(symbol):
    """獲取買賣價位建議（AI 生成）"""
    if analyzer is None or intraday_analyzer is None:
        return jsonify({'success': False, 'error': '分析器未初始化'}), 500
    
    try:
        # 獲取股票數據
        stock_data = analyzer.get_stock_data(symbol)
        if not stock_data:
            return jsonify({'success': False, 'error': '無法獲取股票數據'}), 404
        
        current_price = stock_data['price']
        tech = stock_data['technicals']
        
        # 基於 ATR 計算建議價位
        atr = tech.get('atr', current_price * 0.01)
        
        # 建議買入價 = 現價 - 1.5倍 ATR
        suggested_buy = round(current_price - atr * 1.5, 2)
        # 建議賣出價 = 現價 + 2倍 ATR
        suggested_sell = round(current_price + atr * 2, 2)
        # 建議止損價 = 現價 - 1倍 ATR
        suggested_stop = round(current_price - atr, 2)
        
        # 計算風險回報比
        risk = current_price - suggested_stop
        reward = suggested_sell - current_price
        risk_reward_ratio = round(reward / risk, 1) if risk > 0 else 0
        
        # 生成建議
        if risk_reward_ratio >= 2:
            suggestion = "強烈買入"
            confidence = "高"
        elif risk_reward_ratio >= 1.5:
            suggestion = "買入"
            confidence = "中"
        elif risk_reward_ratio >= 1:
            suggestion = "中性"
            confidence = "中"
        else:
            suggestion = "觀望"
            confidence = "低"
        
        return jsonify({
            'success': True,
            'data': {
                'current_price': current_price,
                'suggested_buy': suggested_buy,
                'suggested_sell': suggested_sell,
                'suggested_stop': suggested_stop,
                'risk': round(risk, 2),
                'reward': round(reward, 2),
                'risk_reward_ratio': risk_reward_ratio,
                'suggestion': suggestion,
                'confidence': confidence,
                'atr': atr
            }
        })
        
    except Exception as e:
        logger.error(f"獲取買賣價位建議失敗: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 多模型 AI 分析 API (v1.5 新增) ====================

@app.route('/api/multi-ai/analyze/<symbol>', methods=['GET'])
def multi_ai_analyze_stock(symbol):
    """多模型 AI 分析股票（Claude + DeepSeek 对比）"""
    if analyzer is None or multi_ai is None:
        return jsonify({
            'success': False,
            'error': '系統未就緒'
        }), 500
    
    try:
        # 獲取股票數據
        stock_data = analyzer.get_stock_data(symbol)
        if not stock_data:
            return jsonify({'success': False, 'error': '無法獲取股票數據'}), 404
        
        # 獲取用戶問題（可選）
        question = request.args.get('q', '')
        
        # 調用多模型分析
        result = multi_ai.analyze_both(stock_data, question)
        
        return jsonify({
            'success': True,
            'data': result
        })
        
    except Exception as e:
        logger.error(f"多模型 AI 分析失敗: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/multi-ai/claude/<symbol>', methods=['GET'])
def claude_analyze_stock(symbol):
    """僅使用 Claude 分析股票"""
    if analyzer is None or multi_ai is None:
        return jsonify({
            'success': False,
            'error': '系統未就緒'
        }), 500
    
    try:
        stock_data = analyzer.get_stock_data(symbol)
        if not stock_data:
            return jsonify({'success': False, 'error': '無法獲取股票數據'}), 404
        
        question = request.args.get('q', '')
        result = multi_ai.analyze_with_claude(stock_data, question)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Claude 分析失敗: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/multi-ai/deepseek/<symbol>', methods=['GET'])
def deepseek_analyze_stock(symbol):
    """僅使用 DeepSeek 分析股票"""
    if analyzer is None or multi_ai is None:
        return jsonify({
            'success': False,
            'error': '系統未就緒'
        }), 500
    
    try:
        stock_data = analyzer.get_stock_data(symbol)
        if not stock_data:
            return jsonify({'success': False, 'error': '無法獲取股票數據'}), 404
        
        question = request.args.get('q', '')
        result = multi_ai.analyze_with_deepseek(stock_data, question)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"DeepSeek 分析失敗: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/multi-ai/strategy/<symbol>', methods=['GET'])
def generate_strategy(symbol):
    """自動生成交易策略"""
    if analyzer is None or multi_ai is None:
        return jsonify({
            'success': False,
            'error': '系統未就緒'
        }), 500
    
    try:
        stock_data = analyzer.get_stock_data(symbol)
        if not stock_data:
            return jsonify({'success': False, 'error': '無法獲取股票數據'}), 404
        
        strategy = multi_ai.generate_trading_strategy(stock_data)
        
        return jsonify({
            'success': True,
            'data': strategy
        })
        
    except Exception as e:
        logger.error(f"策略生成失敗: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/multi-ai/config', methods=['GET', 'POST'])
def configure_multi_ai():
    """配置多模型 AI"""
    global multi_ai
    
    if request.method == 'GET':
        return jsonify({
            'success': True,
            'data': {
                'claude_enabled': multi_ai.enabled_models.get('claude', False) if multi_ai else False,
                'deepseek_enabled': multi_ai.enabled_models.get('deepseek', True) if multi_ai else True,
                'claude_configured': bool(multi_ai.claude_api_key) if multi_ai else False
            }
        })
    
    # POST - 配置 API Key
    try:
        data = request.get_json()
        if 'claude_api_key' in data:
            api_key = data['claude_api_key']
            if multi_ai:
                multi_ai.set_claude_api_key(api_key)
                return jsonify({
                    'success': True,
                    'message': 'Claude API Key 配置成功',
                    'claude_enabled': multi_ai.enabled_models.get('claude', False)
                })
            else:
                return jsonify({'success': False, 'error': 'AI 分析器未初始化'}), 500
        
        return jsonify({'success': False, 'error': '無效的參數'}), 400
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/multi-ai/chat', methods=['POST'])
def multi_ai_chat():
    """智能問答 - 支持多模型對比"""
    if analyzer is None or multi_ai is None:
        return jsonify({
            'success': False,
            'error': '系統未就緒'
        }), 500
    
    try:
        data = request.get_json()
        symbol = data.get('symbol', '')
        question = data.get('question', '')
        
        if not symbol:
            return jsonify({'success': False, 'error': '缺少股票代碼'}), 400
        
        stock_data = analyzer.get_stock_data(symbol)
        if not stock_data:
            return jsonify({'success': False, 'error': '無法獲取股票數據'}), 404
        
        # 多模型分析
        result = multi_ai.analyze_both(stock_data, question)
        
        return jsonify({
            'success': True,
            'data': {
                'question': question,
                'symbol': symbol,
                'stock_name': stock_data.get('name', symbol),
                'current_price': stock_data.get('price'),
                'analysis': result
            }
        })
        
    except Exception as e:
        logger.error(f"智能問答失敗: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 新聞輿情 API 路由 ====================

@app.route('/api/news/<stock_code>')
def get_stock_news(stock_code):
    """獲取個股新聞/公告"""
    try:
        limit = int(request.args.get('limit', 10))
        result = fetch_stock_news(stock_code, limit=limit, allow_market_fallback=False)
        return jsonify({
            'success': True,
            'data': result['news'],
            'count': len(result['news']),
            'is_related': result['is_related']
        })
    except Exception as e:
        logger.error(f"獲取新聞失敗: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/news/market')
def get_market_news():
    """獲取市場快訊（不指定股票）"""
    try:
        limit = int(request.args.get('limit', 15))
        result = fetch_market_news(limit=limit)
        return jsonify({
            'success': True,
            'data': result['news'],
            'count': len(result['news']),
            'is_related': result['is_related']
        })
    except Exception as e:
        logger.error(f"獲取市場快訊失敗: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/sentiment/<stock_code>')
def get_stock_sentiment(stock_code):
    """獲取個股新聞情緒分析"""
    try:
        # 先獲取新聞（不允许降级到市场快讯）
        result = fetch_stock_news(stock_code, limit=10, allow_market_fallback=False)
        news = result['news']
        is_related = result['is_related']

        # 分析情緒（即使没有新闻也进行分析，空列表会使用默认情绪）
        sentiment = analyze_news_sentiment(stock_code, news)

        return jsonify({
            'success': True,
            'data': {
                'sentiment': sentiment,
                'news': news,
                'is_related': is_related
            }
        })
    except Exception as e:
        logger.error(f"情緒分析失敗: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/sentiment/enhanced/<stock_code>')
def get_enhanced_analysis(stock_code):
    """增強版分析：新聞情緒 + 技術面 + AI 評分"""
    try:
        # 1. 新聞數據（不允许降级）
        result = fetch_stock_news(stock_code, limit=10, allow_market_fallback=False)
        news = result['news']
        is_related = result['is_related']
        sentiment = analyze_news_sentiment(stock_code, news)

        # 2. 技術面數據
        stock_data = None
        if analyzer:
            stock_data = analyzer.get_stock_data(stock_code)

        # 3. 構造增強版分析結果
        enhanced = {
            'stock_code': stock_code,
            'sentiment': sentiment,
            'news': news,
            'is_related': is_related,
            'stock_data': stock_data,
            'analysis_time': __import__('datetime').datetime.now().isoformat()
        }

        return jsonify({
            'success': True,
            'data': enhanced
        })

    except Exception as e:
        logger.error(f"增強分析失敗: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 港交所財務報表 API 路由 ====================

@app.route('/api/hkex/financial/<stock_code>')
def get_hkex_financial(stock_code):
    """獲取港股財務報表（年度/季度）"""
    try:
        report_type = request.args.get('type', 'annual')  # annual 或 quarterly
        result = get_hkex_financial_data(stock_code, report_type)
        return jsonify(result)
    except Exception as e:
        logger.error(f"獲取財務報表失敗: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/hkex/summary/<stock_code>')
def get_hkex_summary(stock_code):
    """獲取港股財務摘要（年度+季度）"""
    try:
        result = get_financial_summary(stock_code)
        return jsonify(result)
    except Exception as e:
        logger.error(f"獲取財務摘要失敗: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/system/reload', methods=['POST'])
def reload_modules():
    """熱重載模組（不重启服务器）"""
    global multi_ai
    try:
        import multi_model_ai
        importlib.reload(multi_model_ai)
        from multi_model_ai import MultiModelAIAnalyst
        multi_ai = MultiModelAIAnalyst()
        
        return jsonify({
            'success': True,
            'message': 'multi_model_ai 模組已重載',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"模組重載失敗: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/hkex/verify/<stock_code>')
def get_hkex_verify(stock_code):
    """
    财务数据核实 API - 返回完整数据来源透明信息
    用于 verify_financials.html 核实工具
    """
    try:
        import os
        from pathlib import Path
        
        # 获取财务摘要
        summary = get_financial_summary(stock_code)
        
        # 检查本地数据文件状态
        local_data_dir = Path("/home/openclaw/data/stockai_data/cache")
        code_clean = str(stock_code).upper().replace('.HK', '').strip().zfill(5)
        local_file = local_data_dir / f"{code_clean}_financial.json"
        
        local_file_info = {
            "exists": local_file.exists(),
            "path": str(local_file),
            "size_kb": round(local_file.stat().st_size / 1024, 1) if local_file.exists() else None,
            "modified": local_file.stat().st_mtime if local_file.exists() else None,
        }
        
        if local_file.exists() and local_file_info["modified"]:
            import datetime
            mtime = datetime.datetime.fromtimestamp(local_file_info["modified"])
            local_file_info["modified_str"] = mtime.strftime("%Y-%m-%d %H:%M")
        
        # 构建核实响应
        verify_result = {
            **summary,
            "verify": {
                "local_file": local_file_info,
                "data_pipeline": [
                    {"step": 1, "name": "港交所披露易（本地缓存）",    "active": summary.get("source") == "local",     "desc": "stockai_data/cache 目录，由 hkex_crawler_v3.py 从港交所披露易定期下载，秒开体验"},
                    {"step": 2, "name": "富途 OpenD API (估值指标)",   "active": True,                                 "desc": "PE/PB/PS 实时行情，优先从富途获取"},
                    {"step": 3, "name": "应用内部缓存 (pickle)",       "active": summary.get("source") == "cache",     "desc": "backend/cache 目录，24小时有效（备用）"},
                    {"step": 4, "name": "演示数据 (DEMO)",             "active": summary.get("source") == "demo",      "desc": "⚠️ 本地数据不可用时显示，非真实数据"},
                ],
                "actual_source": summary.get("source", "unknown"),
                "recommendation": (
                    "✅ 财务数据来自港交所披露易（本地缓存），与官方财报一致，准确可靠。"
                    if summary.get("source") == "local" else
                    "✅ 数据来自缓存，可正常使用。"
                    if summary.get("source") == "cache" else
                    "⚠️ 当前为演示数据，请先同步该股票的财务数据。"
                    if summary.get("source") == "demo" else
                    "📋 数据来源正常。"
                )
            }
        }
        
        return jsonify(verify_result)
    except Exception as e:
        logger.error(f"核实 API 失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 基本面分析 API (v1.7 新增) ====================

@app.route('/api/fundamental/<stock_code>')
def get_fundamental_analysis(stock_code):
    """
    基本面分析 API
    返回多维度基本面评分 + AI 研判
    
    Query params:
        pe: 富途实时 PE (可选，自动从 /api/tradingview/price 获取)
        pb: 富途实时 PB (可选)
    """
    if fundamental_analyzer is None:
        return jsonify({
            'success': False,
            'error': '基本面分析器未初始化'
        }), 500
    
    try:
        # 获取富途实时数据（股价 + PE + PB + TTM 股息率）
        realtime_data = {}
        pe_ratio = None
        pb_ratio = None
        stock_name = ''  # 富途简称
        try:
            if kline_adapter:
                price_data = kline_adapter.get_price(stock_code)
                if price_data.get('success'):
                    stock_name = price_data.get('name', '')  # 富途返回简称（如"复星医药"）
                    pe_ratio = price_data.get('pe')
                    pb_ratio = price_data.get('pb')
                    # 注入实时数据给基本面分析器
                    if price_data.get('last_price') and price_data['last_price'] > 0:
                        realtime_data['last_price'] = price_data['last_price']
                    if price_data.get('dividend_yield') and price_data['dividend_yield'] > 0:
                        realtime_data['dividend_yield'] = price_data['dividend_yield']
                    if pe_ratio and pe_ratio > 0:
                        realtime_data['pe'] = pe_ratio
                    if pb_ratio and pb_ratio > 0:
                        realtime_data['pb'] = pb_ratio
                    # 保存完整价格数据，用于返回给前端（避免前端单独请求）
                    realtime_data['_raw_price'] = price_data
        except Exception:
            pass  # 富途数据不可用时继续
        
        # 执行基本面分析（传入实时数据）
        result = fundamental_analyzer.analyze(stock_code, realtime=realtime_data if realtime_data else None)
        
        if not result.get('success'):
            error_resp = {
                'success': False,
                'error': result.get('error', '基本面分析失败'),
                'stock_code': stock_code,
            }
            if result.get('no_financial_data'):
                error_resp['no_financial_data'] = True
            # 即使失败也返回 stock_name
            if stock_name:
                error_resp['stock_name'] = stock_name
            return jsonify(error_resp), 404
        
        # 补充富途实时 PE/PB
        if pe_ratio is not None and pe_ratio > 0:
            result['valuation']['details']['PE_实时(富途)'] = f"{pe_ratio:.2f}"
            result['valuation']['futu_pe'] = pe_ratio
        if pb_ratio is not None and pb_ratio > 0:
            result['valuation']['details']['PB_实时(富途)'] = f"{pb_ratio:.2f}"
            result['valuation']['futu_pb'] = pb_ratio
        
        # 将实时价格数据直接返回给前端，避免前端额外调用 /api/tradingview/price
        if realtime_data.get('_raw_price'):
            raw = realtime_data['_raw_price']
            result['realtime_price'] = {
                'price': raw.get('last_price', 0),
                'change': raw.get('change', 0),
                'change_percent': raw.get('change_percent', 0),
                'volume': raw.get('volume', 0),
                'turnover': raw.get('turnover', 0),
                'price_available': True,
            }
        else:
            # 富途不可用时也返回字段，让前端知道价格不可用（可从缓存 fallback）
            result['realtime_price'] = {
                'price': 0,
                'change': 0,
                'change_percent': 0,
                'volume': 0,
                'turnover': 0,
                'price_available': False,
            }
        
        # 添加数据来源信息
        result['data_source'] = {
            'financial_data': '港交所披露易（本地缓存）',
            'pe_pb': '富途 OpenD 实时行情' if pe_ratio else '财务报告数据',
            'dividend_yield': '富途实时股价计算' if realtime_data.get('last_price') else '财报静态数据',
            'updated': datetime.now().isoformat()
        }
        
        # 股票简称（优先富途简称，回退到财报全称）
        result['stock_name'] = stock_name or result.get('company_name', '')
        
        return jsonify({
            'success': True,
            'stock_code': stock_code,
            'data': result
        })
        
    except Exception as e:
        logger.error(f"基本面分析失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/fundamental/<stock_code>/summary')
def get_fundamental_summary(stock_code):
    """
    基本面简明摘要 API
    返回评分卡片所需的核心数据
    """
    if fundamental_analyzer is None:
        return jsonify({'success': False, 'error': '基本面分析器未初始化'}), 500
    
    try:
        # 获取富途实时数据（股价 + PE + PB + TTM 股息率）
        realtime_data = {}
        pe_ratio = None
        pb_ratio = None
        try:
            if kline_adapter:
                price_data = kline_adapter.get_price(stock_code)
                if price_data.get('success'):
                    pe_ratio = price_data.get('pe')
                    pb_ratio = price_data.get('pb')
                    if price_data.get('last_price') and price_data['last_price'] > 0:
                        realtime_data['last_price'] = price_data['last_price']
                    if price_data.get('dividend_yield') and price_data['dividend_yield'] > 0:
                        realtime_data['dividend_yield'] = price_data['dividend_yield']
                    if pe_ratio and pe_ratio > 0:
                        realtime_data['pe'] = pe_ratio
                    if pb_ratio and pb_ratio > 0:
                        realtime_data['pb'] = pb_ratio
        except Exception:
            pass

        result = fundamental_analyzer.analyze(stock_code, realtime=realtime_data if realtime_data else None)
        if not result.get('success'):
            return jsonify({'success': False, 'error': result.get('error')}), 404

        summary = {
            'stock_code': stock_code,
            'company_name': result.get('company_name', ''),
            'overall': result.get('overall', {}),
            'growth': {'score': result.get('growth', {}).get('score', 0), 'grade': result.get('growth', {}).get('grade', 'N/A')},
            'profitability': {'score': result.get('profitability', {}).get('score', 0), 'grade': result.get('profitability', {}).get('grade', 'N/A')},
            'financial_health': {'score': result.get('financial_health', {}).get('score', 0), 'grade': result.get('financial_health', {}).get('grade', 'N/A')},
            'valuation': {'score': result.get('valuation', {}).get('score', 0), 'grade': result.get('valuation', {}).get('grade', 'N/A')},
            'dividend': {'score': result.get('dividend', {}).get('score', 0), 'grade': result.get('dividend', {}).get('grade', 'N/A')},
            'ai_judgment': result.get('ai_judgment', {}),
            'pe': pe_ratio,
            'pb': pb_ratio,
            'latest_report': result.get('latest_report', '')
        }
        
        return jsonify({'success': True, 'data': summary})
        
    except Exception as e:
        logger.error(f"基本面摘要失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/health-check/<stock_code>')
def get_health_check(stock_code):
    """
    长线投资体检清单 API
    返回 9 项核心指标的逐一检查结果
    """
    if fundamental_analyzer is None:
        return jsonify({'success': False, 'error': '基本面分析器未初始化'}), 500
    
    try:
        result = fundamental_analyzer.health_check(stock_code)
        if 'error' in result:
            return jsonify({'success': False, 'error': result['error']}), 404
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f"体检清单失败 {stock_code}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500




# ==================== 富途 + TradingView MCP 融合适配器 ====================
# 使用富途数据源 + TradingView MCP 官方算法
try:
    from tradingview_adapter import FutuTradingViewAdapter, get_adapter
    kline_adapter = get_adapter()
    algo_name = kline_adapter.indicators.tv_available
    print(f"✅ 融合适配器 初始化成功")
    print(f"   技术指标算法: {'TradingView MCP (官方)' if algo_name else 'Pandas (备用)'}")
except ImportError as e:
    print(f"⚠️ 融合适配器 初始化失败: {e}")
    kline_adapter = None

# 初始化基本面分析器
try:
    fundamental_analyzer = FundamentalAnalyzer(data_dir="/home/openclaw/data/stockai_data/cache")
    print("✅ 基本面分析引擎 初始化成功")
except Exception as e:
    print(f"⚠️ 基本面分析引擎 初始化失败: {e}")
    fundamental_analyzer = None

# 旧版 TradingView 适配器（保留兼容性）
try:
    from tradingview_adapter import TradingViewAdapter
    tv_adapter = TradingViewAdapter()
    print("✅ TradingView 适配器 初始化成功")
except ImportError as e:
    print(f"⚠️ TradingView 适配器 未安装: {e}")
    tv_adapter = None


# ==================== 富途 K线 API ====================
@app.route('/api/kline/<stock_code>')
def get_kline(stock_code):
    """
    富途 K线数据 API
    获取K线数据用于绘制K线图

    Query params:
        days: 获取天数 (默认 90)
    """
    if kline_adapter is None:
        return jsonify({
            'success': False,
            'error': '富途 K线适配器未初始化'
        }), 503

    try:
        days = int(request.args.get('days', 90))
        result = kline_adapter.get_kline_data(stock_code, days=days)
        return jsonify({
            'success': True,
            'stock_code': stock_code,
            'data': result
        })
    except Exception as e:
        logger.error(f"K线获取失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/indicators/<stock_code>')
def get_indicators(stock_code):
    """
    技术指标 API
    计算32+技术指标

    Query params:
        days: 数据天数 (默认 90)
    """
    if kline_adapter is None:
        return jsonify({
            'success': False,
            'error': '富途 K线适配器未初始化'
        }), 503

    try:
        days = int(request.args.get('days', 90))
        result = kline_adapter.calculate_technical_indicators(stock_code, days=days)
        return jsonify({
            'success': True,
            'stock_code': stock_code,
            'data': result
        })
    except Exception as e:
        logger.error(f"技术指标计算失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/analysis/<stock_code>')
def get_analysis(stock_code):
    """
    综合分析 API
    返回 K线 + 技术指标 + 实时价格
    """
    if kline_adapter is None:
        return jsonify({
            'success': False,
            'error': '富途 K线适配器未初始化'
        }), 503

    try:
        # 并行获取数据
        kline_data = kline_adapter.get_kline_data(stock_code, days=90)
        indicators_data = kline_adapter.calculate_technical_indicators(stock_code, days=90)
        price_data = kline_adapter.get_price(stock_code)

        return jsonify({
            'success': True,
            'stock_code': stock_code,
            'data': {
                'kline': kline_data,
                'indicators': indicators_data,
                'price': price_data
            }
        })
    except Exception as e:
        logger.error(f"综合分析失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tradingview/technical/<stock_code>')
def get_tradingview_technical(stock_code):
    """
    TradingView 技术分析 API
    获取30+技术指标分析
    """
    if tv_adapter is None:
        return jsonify({
            'success': False,
            'error': 'TradingView MCP 未安装，请运行: pip install tradingview-mcp-server'
        }), 503

    try:
        result = tv_adapter.get_technical_analysis(stock_code)
        return jsonify({
            'success': True,
            'stock_code': stock_code,
            'converter': tv_adapter.converter.convert_all(stock_code),
            'data': result
        })
    except Exception as e:
        logger.error(f"TradingView 技术分析失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tradingview/multitimeframe/<stock_code>')
def get_tradingview_multitimeframe(stock_code):
    """
    TradingView 多时间框架分析 API
    获取 周→日→4H→1H→15m 多时间框架对齐分析
    """
    if tv_adapter is None:
        return jsonify({
            'success': False,
            'error': 'TradingView MCP 未安装'
        }), 503

    try:
        result = tv_adapter.get_multi_timeframe(stock_code)
        return jsonify({
            'success': True,
            'stock_code': stock_code,
            'data': result
        })
    except Exception as e:
        logger.error(f"TradingView 多时间框架分析失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tradingview/price/<stock_code>')
def get_tradingview_price(stock_code):
    """
    富途 OpenD 实时价格 API

    数据源:
    - 实时价格: 富途 OpenD (本地，不限流)
    """
    if kline_adapter is None:
        return jsonify({
            'success': False,
            'error': '富途 K线适配器未初始化'
        }), 503

    try:
        result = kline_adapter.get_price(stock_code)
        return jsonify({
            'success': True,
            'stock_code': stock_code,
            'data': result
        })
    except Exception as e:
        logger.error(f"富途 OpenD 价格获取失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tradingview/sentiment')
def get_tradingview_sentiment():
    """
    TradingView 市场情绪 API
    获取 Reddit 社区情绪评分
    """
    if tv_adapter is None:
        return jsonify({
            'success': False,
            'error': 'TradingView MCP 未安装'
        }), 503

    try:
        result = tv_adapter.get_sentiment('')
        return jsonify({
            'success': True,
            'data': result
        })
    except Exception as e:
        logger.error(f"TradingView 情绪分析失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tradingview/news')
def get_tradingview_news():
    """
    TradingView 财经新闻 API
    获取 Reuters、CoinDesk 等实时新闻
    """
    if tv_adapter is None:
        return jsonify({
            'success': False,
            'error': 'TradingView MCP 未安装'
        }), 503

    try:
        query = request.args.get('q', 'stock market')
        result = tv_adapter.get_news(query)
        return jsonify({
            'success': True,
            'query': query,
            'data': result
        })
    except Exception as e:
        logger.error(f"TradingView 新闻获取失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tradingview/combined/<stock_code>')
def get_tradingview_combined(stock_code):
    """
    TradingView 综合分析 API
    技术指标 + 情绪 + 新闻 → AI 决策
    输出: STRONG BUY / BUY / HOLD / SELL / STRONG SELL
    """
    if tv_adapter is None:
        return jsonify({
            'success': False,
            'error': 'TradingView MCP 未安装'
        }), 503

    try:
        result = tv_adapter.get_combined_analysis(stock_code)
        return jsonify({
            'success': True,
            'stock_code': stock_code,
            'data': result
        })
    except Exception as e:
        logger.error(f"TradingView 综合分析失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tradingview/backtest/<stock_code>')
def get_tradingview_backtest(stock_code):
    """
    TradingView 策略回测 API
    支持: RSI, MACD, EMA, Bollinger, Supertrend, Donchian
    """
    if tv_adapter is None:
        return jsonify({
            'success': False,
            'error': 'TradingView MCP 未安装'
        }), 503

    try:
        strategy = request.args.get('strategy', 'RSI')
        result = tv_adapter.backtest(stock_code, strategy)
        return jsonify({
            'success': True,
            'stock_code': stock_code,
            'strategy': strategy,
            'data': result
        })
    except Exception as e:
        logger.error(f"TradingView 回测失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tradingview/all/<stock_code>')
def get_tradingview_all(stock_code):
    """
    TradingView 全功能 API
    返回所有可用数据
    """
    if tv_adapter is None:
        return jsonify({
            'success': False,
            'error': 'TradingView MCP 未安装'
        }), 503

    try:
        result = tv_adapter.get_all_indicators(stock_code)
        return jsonify({
            'success': True,
            'stock_code': stock_code,
            'converter': tv_adapter.converter.convert_all(stock_code),
            'data': result
        })
    except Exception as e:
        logger.error(f"TradingView 全功能获取失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tradingview/status')
def get_tradingview_status():
    """
    TradingView MCP 状态检查
    """
    return jsonify({
        'success': True,
        'available': tv_adapter is not None,
        'mcp_installed': tv_adapter._tradingview_available if tv_adapter else False,
        'features': [
            '30+ technical indicators',
            'Multi-timeframe analysis',
            'Sentiment analysis',
            'News aggregation',
            'Strategy backtesting',
            'AI combined analysis'
        ] if tv_adapter else []
    })


# ═══════════════════════════════════════════════════
#  模拟交易 API 路由 (Paper Trading)
# ═══════════════════════════════════════════════════

@app.route('/api/paper/decide/<path:stock_code>', methods=['POST'])
def paper_ai_decide(stock_code):
    """AI 智能决策: K线 + 基本面 → 评分 + 操作建议"""
    try:
        # 1. 获取 K 线数据 (通过 StockAnalyzer)
        if analyzer is None:
            return jsonify({'success': False, 'error': 'StockAnalyzer 未初始化，无法获取行情'}), 503

        kline_df = analyzer.get_kline_data(stock_code, days=120)
        if kline_df.empty:
            return jsonify({'success': False, 'error': f'无法获取 {stock_code} 的K线数据'}), 404

        # 2. 获取股票名称
        stock_name = stock_code
        try:
            futu_code = analyzer._convert_symbol(stock_code)
            if analyzer.quote_ctx:
                from futu import SubType
                analyzer.quote_ctx.subscribe([futu_code], [SubType.QUOTE])
                ret, snap = analyzer.quote_ctx.get_market_snapshot([futu_code])
                if ret == 0 and not snap.empty:
                    stock_name = snap.iloc[0].get('stock_name', stock_code)
        except Exception as e:
            logger.warning(f'获取股票名称失败 {stock_code}: {e}')

        # 3. 获取基本面数据 (通过 FundamentalAnalyzer)
        financials = None
        try:
            # 复用全局 fundamental_analyzer 实例（如果可用），否则新建
            fa = None
            try:
                if fundamental_analyzer is not None:
                    fa = fundamental_analyzer
            except NameError:
                pass
            if fa is None:
                from fundamental_analyzer import FundamentalAnalyzer
                fa = FundamentalAnalyzer()

            # 构建富途实时数据（复用已获取的 snapshot）
            rt_data = {}
            try:
                if analyzer.quote_ctx:
                    from futu import SubType
                    futu_code_rt = analyzer._convert_symbol(stock_code)
                    analyzer.quote_ctx.subscribe([futu_code_rt], [SubType.QUOTE])
                    ret_rt, snap_rt = analyzer.quote_ctx.get_market_snapshot([futu_code_rt])
                    if ret_rt == 0 and not snap_rt.empty:
                        rt_price = snap_rt.iloc[0].get('last_price', 0)
                        if rt_price and rt_price > 0:
                            rt_data['last_price'] = rt_price
            except Exception as e:
                logger.debug(f'paper/decide 获取实时股价失败: {e}')

            # 注入富途实时 PE/PB（与 get_fundamental_analysis 路由一致）
            try:
                if kline_adapter:
                    price_data = kline_adapter.get_price(stock_code)
                    if price_data.get('success'):
                        if price_data.get('pe') and price_data['pe'] > 0:
                            rt_data['pe'] = price_data['pe']
                        if price_data.get('pb') and price_data['pb'] > 0:
                            rt_data['pb'] = price_data['pb']
                        if price_data.get('dividend_yield') and price_data['dividend_yield'] > 0:
                            rt_data['dividend_yield'] = price_data['dividend_yield']
            except Exception as e:
                logger.debug(f'paper/decide 注入富途 PE/PB 失败: {e}')

            # 直接传 stock_code，load_financial_data 内部会处理格式转换
            fin_result = fa.analyze(stock_code, realtime=rt_data if rt_data else None)
            logger.info(f'基本面分析结果 {stock_code}: success={fin_result.get("success") if fin_result else None}')
            if fin_result and isinstance(fin_result, dict) and fin_result.get('success'):
                # 从基本面分析结果获取公司名称（比 snapshot 更可靠）
                cn = fin_result.get('company_name', '')
                if cn and stock_name == stock_code:
                    stock_name = cn
                financials = {}

                # 从 profitability.details 提取 ROE (格式: "18.50%")
                prof = fin_result.get('profitability', {})
                prof_details = prof.get('details', {}) if isinstance(prof, dict) else {}
                roe_str = prof_details.get('ROE', '')
                if roe_str and roe_str != 'N/A':
                    try:
                        financials['roe'] = float(str(roe_str).replace('%', '').replace(',', ''))
                    except (ValueError, TypeError):
                        pass

                # 从 valuation.details 提取 PE (格式: "15.20")
                val = fin_result.get('valuation', {})
                val_details = val.get('details', {}) if isinstance(val, dict) else {}

                # 优先使用富途实时 PE（与 tradingview 基本面分析一致）
                pe_str = val_details.get('PE_实时(富途)') or val_details.get('PE', '')
                if not pe_str or pe_str == 'N/A':
                    # 回退：直接从富途 get_price 获取 PE
                    try:
                        if kline_adapter:
                            futu_price = kline_adapter.get_price(stock_code)
                            if futu_price.get('success') and futu_price.get('pe') and futu_price['pe'] > 0:
                                financials['pe_ratio'] = float(futu_price['pe'])
                    except Exception:
                        pass
                if not financials.get('pe_ratio') and pe_str and pe_str not in ('N/A', ''):
                    try:
                        financials['pe_ratio'] = float(str(pe_str).replace(',', ''))
                    except (ValueError, TypeError):
                        pass

                # 从 dividend.details 提取股息率 (优先使用实时计算的值)
                div = fin_result.get('dividend', {})
                div_details = div.get('details', {}) if isinstance(div, dict) else {}
                div_str = div_details.get('股息率_实时') or div_details.get('股息率', '')
                if div_str and div_str != 'N/A':
                    try:
                        financials['dividend_yield'] = float(str(div_str).replace('%', '').replace(',', ''))
                    except (ValueError, TypeError):
                        pass

                # 从 financial_health.details 提取负债率 (格式: "35.00%")
                fh = fin_result.get('financial_health', {})
                fh_details = fh.get('details', {}) if isinstance(fh, dict) else {}
                debt_str = fh_details.get('资产负债率', '')
                if debt_str and debt_str != 'N/A':
                    try:
                        financials['debt_ratio'] = float(str(debt_str).replace('%', '').replace(',', ''))
                    except (ValueError, TypeError):
                        pass

                # 清除 None/0 值（0 表示无数据，不参与评分）
                financials = {k: v for k, v in financials.items() if v is not None and v != 0}
                if not financials:
                    financials = None
        except Exception as e:
            logger.error(f'基本面数据获取失败 {stock_code}: {e}', exc_info=True)

        # 4. AI 决策
        report = ai_decide(stock_code, stock_name, kline_df, financials)

        return jsonify({'success': True, 'data': report})

    except Exception as e:
        logger.error(f'AI 决策失败 {stock_code}: {e}', exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/paper/execute', methods=['POST'])
def paper_execute_trade():
    """执行模拟交易 (买入/卖出)"""
    try:
        params = request.get_json()
        code     = params.get('code', '')
        name     = params.get('name', code)
        price    = float(params.get('price', 0))
        quantity = int(params.get('quantity', 0))
        action   = params.get('action', '').upper()

        if not code or price <= 0 or quantity <= 0 or action not in ('BUY', 'SELL'):
            return jsonify({'success': False, 'error': '参数无效: 需要 code/price/quantity/action'}), 400

        account = get_account()

        if action == 'BUY':
            ok, msg = RiskManager.check_buy(account, code, price, quantity)
            if not ok:
                return jsonify({'success': False, 'message': msg})
            success, msg, trade = account.buy(code, name, price, quantity)
        else:
            ok, msg = RiskManager.check_sell(account, code, quantity)
            if not ok:
                return jsonify({'success': False, 'message': msg})
            success, msg, trade = account.sell(code, name, price, quantity)

        if success:
            return jsonify({'success': True, 'message': msg, 'trade': trade})
        else:
            return jsonify({'success': False, 'message': msg})

    except Exception as e:
        logger.error(f'模拟交易执行失败: {e}', exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/paper/portfolio', methods=['GET'])
def paper_portfolio():
    """获取持仓概览 (含实时价格)"""
    try:
        account = get_account()
        price_map = {}

        # 获取持仓股票的实时价格
        if analyzer and analyzer.quote_ctx and account.holdings:
            try:
                futu_codes = []
                code_map = {}
                for code in account.holdings:
                    futu_code = analyzer._convert_symbol(code)
                    futu_codes.append(futu_code)
                    code_map[futu_code] = code

                ret, snap = analyzer.quote_ctx.get_market_snapshot(futu_codes)
                if ret == 0 and not snap.empty:
                    for _, row in snap.iterrows():
                        fc = row.get('code', '')
                        c = code_map.get(fc)
                        if c:
                            price_map[c] = float(row.get('last_price', 0) or row.get('open_price', 0))
            except Exception as e:
                logger.warning(f'获取实时价格失败: {e}')

        portfolio = account.get_portfolio(price_map)
        return jsonify({'success': True, 'data': portfolio})

    except Exception as e:
        logger.error(f'获取持仓失败: {e}', exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/paper/history', methods=['GET'])
def paper_history():
    """获取交易历史"""
    try:
        account = get_account()
        limit = request.args.get('limit', 50, type=int)
        # 按时间倒序
        history = sorted(account.history, key=lambda x: x.get('timestamp', ''), reverse=True)
        history = history[:limit]

        return jsonify({
            'success': True,
            'total': len(account.history),
            'data': history,
        })

    except Exception as e:
        logger.error(f'获取交易历史失败: {e}', exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/paper/auto_scan', methods=['POST'])
def paper_auto_scan():
    """批量 AI 扫描自选股"""
    try:
        params = request.get_json()
        stocks = params.get('stocks', [])

        if not stocks or not isinstance(stocks, list):
            return jsonify({'success': False, 'error': '请提供股票代码列表'}), 400

        if analyzer is None:
            return jsonify({'success': False, 'error': 'StockAnalyzer 未初始化'}), 503

        results = []
        for code in stocks:
            try:
                # 获取 K 线
                kline_df = analyzer.get_kline_data(code, days=90)
                if kline_df.empty:
                    results.append({'code': code, 'error': '无法获取K线数据'})
                    continue

                # 获取名称 + 实时股价（一次性 snapshot）
                stock_name = code
                last_price = None
                try:
                    futu_code = analyzer._convert_symbol(code)
                    if analyzer.quote_ctx:
                        from futu import SubType
                        analyzer.quote_ctx.subscribe([futu_code], [SubType.QUOTE])
                        ret, snap = analyzer.quote_ctx.get_market_snapshot([futu_code])
                        if ret == 0 and not snap.empty:
                            stock_name = snap.iloc[0].get('stock_name', code)
                            last_price = snap.iloc[0].get('last_price')
                except Exception as e:
                    logger.warning(f'获取股票名称失败 {code}: {e}')

                # 获取基本面数据
                financials = None
                try:
                    fa = None
                    try:
                        if fundamental_analyzer is not None:
                            fa = fundamental_analyzer
                    except NameError:
                        pass
                    if fa is None:
                        from fundamental_analyzer import FundamentalAnalyzer
                        fa = FundamentalAnalyzer()
                    # 传入实时股价 + PE/PB（与 paper_ai_decide 一致）
                    rt_data = {}
                    if last_price and last_price > 0:
                        rt_data['last_price'] = last_price
                    try:
                        if kline_adapter:
                            price_data = kline_adapter.get_price(code)
                            if price_data.get('success'):
                                if price_data.get('pe') and price_data['pe'] > 0:
                                    rt_data['pe'] = price_data['pe']
                                if price_data.get('pb') and price_data['pb'] > 0:
                                    rt_data['pb'] = price_data['pb']
                                if price_data.get('dividend_yield') and price_data['dividend_yield'] > 0:
                                    rt_data['dividend_yield'] = price_data['dividend_yield']
                    except: pass
                    fin_result = fa.analyze(code, realtime=rt_data if rt_data else None)
                    if fin_result and isinstance(fin_result, dict) and fin_result.get('success'):
                        # 从基本面分析获取公司名称
                        cn = fin_result.get('company_name', '')
                        if cn and stock_name == code:
                            stock_name = cn
                        financials = {}
                        prof = fin_result.get('profitability', {})
                        prof_details = prof.get('details', {}) if isinstance(prof, dict) else {}
                        roe_str = prof_details.get('ROE', '')
                        if roe_str and roe_str != 'N/A':
                            try: financials['roe'] = float(str(roe_str).replace('%', '').replace(',', ''))
                            except: pass
                        val = fin_result.get('valuation', {})
                        val_details = val.get('details', {}) if isinstance(val, dict) else {}
                        # 优先使用富途实时 PE（与 tradingview 基本面分析一致）
                        pe_str = val_details.get('PE_实时(富途)') or val_details.get('PE', '')
                        if not pe_str or pe_str == 'N/A':
                            try:
                                if kline_adapter:
                                    futu_price = kline_adapter.get_price(code)
                                    if futu_price.get('success') and futu_price.get('pe') and futu_price['pe'] > 0:
                                        financials['pe_ratio'] = float(futu_price['pe'])
                            except: pass
                        if not financials.get('pe_ratio') and pe_str and pe_str not in ('N/A', ''):
                            try: financials['pe_ratio'] = float(str(pe_str).replace(',', ''))
                            except: pass
                        div = fin_result.get('dividend', {})
                        div_details = div.get('details', {}) if isinstance(div, dict) else {}
                        # 优先使用实时计算的股息率，回退到静态值
                        div_str = div_details.get('股息率_实时') or div_details.get('股息率', '')
                        if div_str and div_str != 'N/A':
                            try: financials['dividend_yield'] = float(str(div_str).replace('%', '').replace(',', ''))
                            except: pass
                        fh = fin_result.get('financial_health', {})
                        fh_details = fh.get('details', {}) if isinstance(fh, dict) else {}
                        debt_str = fh_details.get('资产负债率', '')
                        if debt_str and debt_str != 'N/A':
                            try: financials['debt_ratio'] = float(str(debt_str).replace('%', '').replace(',', ''))
                            except: pass
                        financials = {k: v for k, v in financials.items() if v is not None and v != 0}
                        if not financials:
                            financials = None
                except Exception as e:
                    logger.warning(f'批量扫描基本面数据获取失败 {code}: {e}')

                # AI 决策
                report = ai_decide(code, stock_name, kline_df, financials)
                results.append(report)

            except Exception as e:
                results.append({'code': code, 'error': str(e)})

        # 按综合评分降序排序
        results.sort(key=lambda x: x.get('combined_score', 0), reverse=True)

        return jsonify({
            'success': True,
            'count': len(results),
            'data': results,
        })

    except Exception as e:
        logger.error(f'批量扫描失败: {e}', exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/paper/reset', methods=['POST'])
def paper_reset():
    """重置模拟账户"""
    try:
        account = get_account()
        account.reset()
        return jsonify({
            'success': True,
            'message': '模拟账户已重置为 HKD 1,000,000',
        })
    except Exception as e:
        logger.error(f'重置账户失败: {e}', exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ═══════════════════════════════════════════
#  回測 API
# ═══════════════════════════════════════════

@app.route('/api/backtest/strategies', methods=['GET'])
def backtest_strategies():
    """获取所有可用回测策略"""
    return jsonify({
        'success': True,
        'strategies': get_available_strategies(),
    })


@app.route('/api/backtest/run', methods=['POST'])
def backtest_run():
    """
    执行单策略回测

    Body:
        stock_code: str — 股票代码
        strategy: str — 策略名 (ema_cross/macd/rsi/bollinger/composite)
        days: int — 回测天数 (默认365)
        params: dict — 策略参数 (可选)
    """
    try:
        data = request.get_json() or {}
        stock_code = data.get('stock_code', '').strip()
        strategy = data.get('strategy', 'ema_cross')
        days = min(int(data.get('days', 365)), 730)  # 最多2年
        params = data.get('params', {})

        if not stock_code:
            return jsonify({'success': False, 'error': '请输入股票代码'}), 400

        # 获取K线数据
        kline = analyzer.get_kline_data(stock_code, days=days)
        if kline is None or kline.empty:
            return jsonify({'success': False, 'error': f'无法获取 {stock_code} 的K线数据，请确认富途连接正常'}), 404

        # 执行回测
        engine = BacktestEngine(initial_cash=1000000)
        result = engine.run(kline, strategy, params)

        return jsonify(result)

    except Exception as e:
        logger.error(f'回测失败: {e}', exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/backtest/multi', methods=['POST'])
def backtest_multi():
    """
    多策略对比回测

    Body:
        stock_code: str — 股票代码
        strategies: list — 策略列表 (可选，默认全部)
        days: int — 回测天数 (默认365)
        params: dict — 策略参数 (可选)
    """
    try:
        data = request.get_json() or {}
        stock_code = data.get('stock_code', '').strip()
        strategies = data.get('strategies') or list(STRATEGIES.keys())
        days = min(int(data.get('days', 365)), 730)
        params = data.get('params', {})

        if not stock_code:
            return jsonify({'success': False, 'error': '请输入股票代码'}), 400

        kline = analyzer.get_kline_data(stock_code, days=days)
        if kline is None or kline.empty:
            return jsonify({'success': False, 'error': f'无法获取 {stock_code} 的K线数据'}), 404

        engine = BacktestEngine(initial_cash=1000000)
        result = engine.run_multi(kline, strategies, params)

        return jsonify(result)

    except Exception as e:
        logger.error(f'多策略回测失败: {e}', exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/backtest/walkforward', methods=['POST'])
def backtest_walkforward():
    """
    Walk-Forward 验证 (防过拟合)

    Body:
        stock_code: str
        strategy: str
        days: int (默认730)
        params: dict (可选)
    """
    try:
        data = request.get_json() or {}
        stock_code = data.get('stock_code', '').strip()
        strategy = data.get('strategy', 'ema_cross')
        days = min(int(data.get('days', 730)), 730)
        params = data.get('params', {})

        if not stock_code:
            return jsonify({'success': False, 'error': '请输入股票代码'}), 400

        kline = analyzer.get_kline_data(stock_code, days=days)
        if kline is None or kline.empty:
            return jsonify({'success': False, 'error': f'无法获取 {stock_code} 的K线数据'}), 404

        engine = BacktestEngine(initial_cash=1000000)
        result = engine.walk_forward(kline, strategy, params, n_splits=3)

        return jsonify(result)

    except Exception as e:
        logger.error(f'Walk-Forward 验证失败: {e}', exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500



if __name__ == '__main__':
    print("="*60)
    print("🚀 StockAI 智能分析系統 v1.7 (TradingView MCP)")
    print("="*60)
    print("📊 後端 API: http://localhost:5000")
    print("📈 前端界面: http://localhost:5000")
    print("🤖 AI 分析引擎:")
    print("   • DeepSeek Chat: 已集成")
    print("   • SiliconFlow Qwen2.5: 已集成")
    print("   • Claude Sonnet 4: 待配置 API Key")
    print("   • 多模型对比分析: 已启用")
    print("   • 自动策略生成: 已启用")
    print("📈 TradingView MCP (v0.7.0):")
    print("   • 30+ 技术指标: /api/tradingview/technical/<code>")
    print("   • 多时间框架: /api/tradingview/multitimeframe/<code>")
    print("   • 情绪分析: /api/tradingview/sentiment")
    print("   • 财经新闻: /api/tradingview/news")
    print("   • 综合分析: /api/tradingview/combined/<code>")
    print("   • 策略回测: /api/tradingview/backtest/<code>")
    print("💰 模拟交易 (Paper Trading):")
    print("   • AI 决策: /api/paper/decide/<code>")
    print("   • 执行交易: /api/paper/execute")
    print("   • 持仓查询: /api/paper/portfolio")
    print("   • 交易历史: /api/paper/history")
    print("   • 批量扫描: /api/paper/auto_scan")
    print("   • 每日報告(個股): /api/daily-report/single")
    print("   • 每日報告(掃描): /api/daily-report/scan")
    print("   • 每日報告(持倉): /api/daily-report/portfolio")
    print("🔍 策略觀察:")
    print("   • 信號追蹤掃描: /api/observer/signal-scan")
    print("   • 回填信號結果: /api/observer/backfill")
    print("   • 批量策略回測: /api/observer/batch-backtest")
    print("   • 策略勝率統計: /api/observer/strategy-stats")
    print("   • 觀察報表 HTML: /api/observer/report")
    print("="*60)


# ═══════════════════════════════════════════
#  策略觀察 API (Strategy Observer)
# ═══════════════════════════════════════════

# 全局 tracker 實例
_observer_tracker = SignalTracker()


@app.route('/api/observer/signal-scan', methods=['POST'])
def observer_signal_scan():
    """
    信號追蹤掃描 — 對自選股跑所有策略，記錄今日信號

    Body:
        top_n: int (默認 50)
    """
    try:
        data = request.get_json() or {}
        top_n = data.get('top_n', 50)

        from daily_report import load_watchlist
        codes = load_watchlist()

        if not codes:
            return jsonify({'error': '自選股列表為空'}), 400

        result = _observer_tracker.run_daily_scan(analyzer, codes, top_n=top_n)
        return jsonify({'success': True, 'message': f"掃描完成: {result['total_stocks']} 隻股票", 'data': result})
    except Exception as e:
        logger.error(f"信號掃描失敗: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/observer/backfill', methods=['POST'])
def observer_backfill():
    """
    回填歷史信號的實際走勢

    Body:
        lookback_days: int (默認全部)
    """
    try:
        data = request.get_json(silent=True) or {}
        lookback = data.get('lookback_days', None)
        updated = _observer_tracker.backfill_outcomes(analyzer, lookback_days=lookback)
        return jsonify({'success': True, 'updated': updated})
    except Exception as e:
        logger.error(f"回填失敗: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/observer/batch-backtest', methods=['POST'])
def observer_batch_backtest():
    """
    批量策略回測 — 對自選股跑所有策略回測

    Body:
        top_n: int (默認 30)
        period_days: int (默認 252 = 1 年)
    """
    try:
        data = request.get_json() or {}
        top_n = data.get('top_n', 30)
        period_days = data.get('period_days', 252)

        from daily_report import load_watchlist
        codes = load_watchlist()

        if not codes:
            return jsonify({'error': '自選股列表為空'}), 400

        result = run_batch_backtest(analyzer, codes, top_n=top_n, period_days=period_days)
        perf = aggregate_strategy_performance(result)

        return jsonify({
            'success': True,
            'message': f"回測完成: {len(result)} 隻股票",
            'strategy_performance': perf,
            'stock_results': result,
        })
    except Exception as e:
        logger.error(f"批量回測失敗: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/observer/strategy-stats', methods=['GET'])
def observer_strategy_stats():
    """
    策略勝率統計 — 從信號追蹤日誌中統計

    Query:
        horizon: int (3/5/10, 默認 5)
    """
    try:
        horizon = int(request.args.get('horizon', 5))
        stats = _observer_tracker.get_strategy_stats(horizon=horizon)
        trend = _observer_tracker.get_signal_accuracy_trend(horizon=horizon)
        recent = _observer_tracker.get_recent_signals(days=7)

        return jsonify({
            'success': True,
            'horizon': horizon,
            'stats': stats,
            'trend': trend,
            'recent_signal_count': len(recent),
        })
    except Exception as e:
        logger.error(f"策略統計失敗: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/observer/consensus', methods=['GET'])
def observer_consensus():
    """
    股票級信號聚合 — 每隻股票的 6 策略投票結果，可執行交易候選

    Query:
        days: int (默認 1，即今天)
    """
    try:
        days = int(request.args.get('days', 1))
        result = _observer_tracker.get_stock_consensus(days=days)

        # 分類統計
        stocks = result['stocks']
        strong_bull = [s for s in stocks if s['direction'] == 'bullish' and s['consensus'] >= 67]
        strong_bear = [s for s in stocks if s['direction'] == 'bearish' and s['consensus'] >= 67]
        divergence = [s for s in stocks if s['signal_strength'] == 'divergence']

        return jsonify({
            'success': True,
            'scan_date': result['scan_date'],
            'total_stocks': len(stocks),
            'strong_bull_count': len(strong_bull),
            'strong_bear_count': len(strong_bear),
            'divergence_count': len(divergence),
            'strong_bull': strong_bull,
            'strong_bear': strong_bear,
            'divergence': divergence,
            'all_stocks': stocks,
        })
    except Exception as e:
        logger.error(f"信號聚合失敗: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/observer/report', methods=['GET'])
def observer_report():
    """
    生成策略觀察報表 HTML

    Query:
        top_n: int (默認 30)
        period_days: int (默認 252)
    """
    try:
        top_n = int(request.args.get('top_n', 30))
        period_days = int(request.args.get('period_days', 252))

        # 1. 批量回測
        from daily_report import load_watchlist
        codes = load_watchlist()

        strategy_perf = {}
        if codes:
            batch_results = run_batch_backtest(analyzer, codes, top_n=top_n, period_days=period_days)
            strategy_perf = aggregate_strategy_performance(batch_results)

        # 2. 信號追蹤統計
        signal_stats = _observer_tracker.get_strategy_stats(horizon=5)
        signal_trend = _observer_tracker.get_signal_accuracy_trend(horizon=5)

        # 3. 生成 HTML
        html = generate_observer_html(strategy_perf, signal_stats, signal_trend)

        # 4. 保存
        reports_dir = Path(__file__).resolve().parent / 'reports'
        reports_dir.mkdir(exist_ok=True)
        report_path = reports_dir / f"strategy_observer_{datetime.now().strftime('%Y%m%d_%H%M')}.html"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html)

        return jsonify({
            'success': True,
            'report_url': f'/reports/{report_path.name}',
            'report_path': str(report_path),
        })
    except Exception as e:
        logger.error(f"觀察報表生成失敗: {e}")
        return jsonify({'error': str(e)}), 500



# ==================== Project Status API ====================
# 統一進度查詢端點 — 同步 WeChat 與 Web 狀態

PROGRESS_FILE = os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), '.openclaw', 'workspace', 'stockai_progress.md')

@app.route('/api/status', methods=['GET'])
def get_project_status():
    """返回 StockAI v1.7 當前進度狀態"""
    try:
        if os.path.exists(PROGRESS_FILE):
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse sections
            sections = {}
            current_section = None
            current_items = []
            
            for line in content.split('\n'):
                if line.startswith('## ✅'):
                    if current_section:
                        sections[current_section] = current_items
                    current_section = 'completed'
                    current_items = []
                elif line.startswith('## 🚧'):
                    if current_section:
                        sections[current_section] = current_items
                    current_section = 'in_progress'
                    current_items = []
                elif line.startswith('## ⏳'):
                    if current_section:
                        sections[current_section] = current_items
                    current_section = 'pending'
                    current_items = []
                elif line.startswith('-') and current_section:
                    current_items.append(line.strip('- '))
            
            if current_section:
                sections[current_section] = current_items
            
            # Get update time
            date_match = re.search(r'更新時間: ([\d:]+)', content)
            update_time = date_match.group(1) if date_match else ''
            
            return jsonify({
                'success': True,
                'project': 'StockAI v1.7',
                'update_time': update_time,
                'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'sections': sections
            })
        else:
            return jsonify({'success': False, 'error': 'Progress file not found'}), 404
    except Exception as e:
        logger.error(f"Status API 錯誤: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)