import requests
import time
import subprocess

BASE_URL = 'http://localhost:5000'

def check_server():
    try:
        response = requests.get(f'{BASE_URL}/api/observer/strategy-stats', timeout=5)
        return response.status_code == 200
    except requests.exceptions.ConnectionError:
        return False
    except Exception as e:
        print(f'检查服务器时出错: {e}')
        return False

def start_server():
    backend_dir = r'C:\Users\MarcoMa\stockai_system_v1.7\backend'
    print('启动Flask服务器...')
    subprocess.Popen(
        ['python', 'app.py'],
        cwd=backend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    print('等待服务器启动（5秒）...')
    time.sleep(5)

def main():
    if not check_server():
        start_server()
        if not check_server():
            print('无法启动服务器，请手动检查')
            return
    
    print('=== 开始执行StockAI信号追踪扫描 ===')
    
    # 步骤1：回填历史信号
    print('\n步骤1：回填历史信号...')
    try:
        backfill_resp = requests.post(f'{BASE_URL}/api/observer/backfill', timeout=30)
        print('回填接口原始返回:', backfill_resp.text)
        backfill_data = backfill_resp.json()
        updated_count = backfill_data.get('updated', 0)
        print(f'回填完成：{backfill_data.get("message", "无消息")}，共回填 {updated_count} 条')
    except Exception as e:
        print(f'回填失败: {e}')
        return
    
    # 步骤2：执行今日信号扫描
    print('\n步骤2：执行今日信号扫描（top_n=200）...')
    try:
        scan_resp = requests.post(
            f'{BASE_URL}/api/observer/signal-scan',
            json={'top_n': 200},
            timeout=180
        )
        print('扫描接口原始返回:', scan_resp.text[:500])  # 只打印前500字符避免过长
        scan_data = scan_resp.json()
        # 解析扫描结果
        scanned_count = scan_data.get('data', {}).get('total_stocks', 0)
        # 统计非HOLD信号数量
        signal_count = 0
        stocks = scan_data.get('data', {}).get('stocks', [])
        for stock in stocks:
            signals = stock.get('signals', {})
            for strategy, signal_info in signals.items():
                if signal_info.get('signal', 'HOLD') != 'HOLD':
                    signal_count += 1
        print(f'扫描完成：共扫描 {scanned_count} 只股票，生成 {signal_count} 条有效信号')
    except Exception as e:
        print(f'扫描失败: {e}')
        return
    
    # 步骤3：查看策略统计
    print('\n步骤3：查看策略统计...')
    try:
        stats_resp = requests.get(f'{BASE_URL}/api/observer/strategy-stats', timeout=10)
        print('策略统计接口原始返回:', stats_resp.text)
        stats_data = stats_resp.json()
        print('策略统计概览：')
        print(f'  最近信号总数：{stats_data.get("recent_signal_count", "N/A")}')
        stats_detail = stats_data.get('stats', {})
        if stats_detail:
            for strategy, stat in stats_detail.items():
                print(f'  {strategy}：胜率 {stat.get("win_rate", "N/A")}，信号数 {stat.get("count", "N/A")}')
        else:
            print('  暂无策略胜率数据（可能需要更多信号积累）')
    except Exception as e:
        print(f'获取统计失败: {e}')
        return
    
    print('\n=== 扫描任务全部完成 ===')

if __name__ == '__main__':
    main()