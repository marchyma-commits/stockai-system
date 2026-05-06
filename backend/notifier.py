"""
股票通知系統 - 價格提醒 + 每日報告
"""

import time
import threading
from datetime import datetime, timedelta


class StockNotifier:
    """股票通知系統"""
    
    def __init__(self):
        self.alerts = []
        self.watchlist = []
        self.notification_callback = None
        self.running = False
        self.check_thread = None
    
    def set_notification_callback(self, callback):
        """設置通知回調函數"""
        self.notification_callback = callback
    
    def add_price_alert(self, symbol, target_price, condition='above'):
        """添加價格提醒
        
        Args:
            symbol: 股票代碼
            target_price: 目標價
            condition: 'above' (高於) 或 'below' (低於)
        """
        alert = {
            'symbol': symbol,
            'target_price': target_price,
            'condition': condition,
            'triggered': False,
            'created_at': datetime.now()
        }
        self.alerts.append(alert)
        return alert
    
    def remove_price_alert(self, symbol, target_price=None):
        """移除價格提醒"""
        self.alerts = [a for a in self.alerts 
                      if not (a['symbol'] == symbol and 
                             (target_price is None or a['target_price'] == target_price))]
    
    def add_to_watchlist(self, symbol, name=None):
        """添加到自選列表"""
        item = {'symbol': symbol, 'name': name or symbol}
        if item not in self.watchlist:
            self.watchlist.append(item)
    
    def remove_from_watchlist(self, symbol):
        """從自選列表移除"""
        self.watchlist = [w for w in self.watchlist if w['symbol'] != symbol]
    
    def get_watchlist(self):
        """獲取自選列表"""
        return self.watchlist
    
    def check_alerts(self, stock_data_func):
        """檢查所有提醒（需要傳入獲取股票數據的函數）"""
        triggered = []
        
        for alert in self.alerts:
            if alert['triggered']:
                continue
            
            try:
                data = stock_data_func(alert['symbol'])
                if not data:
                    continue
                
                current_price = data.get('price', 0)
                
                if alert['condition'] == 'above' and current_price >= alert['target_price']:
                    triggered.append(alert)
                    alert['triggered'] = True
                elif alert['condition'] == 'below' and current_price <= alert['target_price']:
                    triggered.append(alert)
                    alert['triggered'] = True
                    
            except Exception as e:
                print(f"檢查提醒失敗 {alert['symbol']}: {e}")
        
        return triggered
    
    def generate_daily_report(self, stock_data_func):
        """生成每日收市報告"""
        report = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'stocks': []
        }
        
        for item in self.watchlist:
            try:
                data = stock_data_func(item['symbol'])
                if data:
                    report['stocks'].append({
                        'symbol': item['symbol'],
                        'name': data.get('name', item['name']),
                        'price': data.get('price'),
                        'change': data.get('change'),
                        'change_percent': data.get('change_percent'),
                        'volume': data.get('volume')
                    })
            except Exception as e:
                print(f"生成報告失敗 {item['symbol']}: {e}")
        
        return report
    
    def send_notification(self, title, message, notification_type='info'):
        """發送通知"""
        if self.notification_callback:
            self.notification_callback(title, message, notification_type)
        else:
            # 默認輸出到控制台
            print(f"\n📢 [{title}] {message}")
    
    def start_background_check(self, stock_data_func, interval=60):
        """啟動後台檢查線程"""
        if self.running:
            return
        
        self.running = True
        
        def check_loop():
            while self.running:
                try:
                    triggered = self.check_alerts(stock_data_func)
                    for alert in triggered:
                        condition_text = "突破" if alert['condition'] == 'above' else "跌破"
                        self.send_notification(
                            f"🔔 價格提醒",
                            f"{alert['symbol']} {condition_text} ${alert['target_price']}！",
                            'alert'
                        )
                except Exception as e:
                    print(f"後台檢查錯誤: {e}")
                
                time.sleep(interval)
        
        self.check_thread = threading.Thread(target=check_loop, daemon=True)
        self.check_thread.start()
    
    def stop_background_check(self):
        """停止後台檢查"""
        self.running = False