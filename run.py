#!/usr/bin/env python3
"""
StockAI 智能分析系統啟動腳本 v1.4.6
使用方法: python run.py 或 雙擊 start_system.bat
"""

import os
import sys
import webbrowser
import threading
import time
from pathlib import Path

# 獲取當前腳本所在目錄（根目錄）
BASE_DIR = Path(__file__).parent.absolute()
BACKEND_DIR = BASE_DIR / 'backend'
FRONTEND_DIR = BASE_DIR / 'frontend'

# 將 backend 目錄加入系統路徑
sys.path.insert(0, str(BACKEND_DIR))

def check_environment():
    """檢查系統環境"""
    print("🔍 檢查系統環境...")
    print(f"📁 根目錄: {BASE_DIR}")
    
    # 檢查必要目錄
    dirs = [
        BACKEND_DIR,
        FRONTEND_DIR,
        FRONTEND_DIR / 'css',
        FRONTEND_DIR / 'js'
    ]
    
    for dir_path in dirs:
        if dir_path.exists():
            print(f"  ✅ 目錄存在: {dir_path.relative_to(BASE_DIR)}")
        else:
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"  📁 創建目錄: {dir_path.relative_to(BASE_DIR)}")
    
    # 檢查必要文件
    required_files = [
        BACKEND_DIR / 'app.py',
        BACKEND_DIR / 'stock_analyzer.py',
        BACKEND_DIR / 'intraday_analyzer.py',
        FRONTEND_DIR / 'index.html',
        FRONTEND_DIR / 'css' / 'style.css',
        FRONTEND_DIR / 'js' / 'app.js',
        FRONTEND_DIR / 'js' / 'intraday.js'
    ]
    
    missing_files = []
    for file_path in required_files:
        if file_path.exists():
            print(f"  ✅ 文件存在: {file_path.relative_to(BASE_DIR)}")
        else:
            missing_files.append(str(file_path.relative_to(BASE_DIR)))
            print(f"  ❌ 文件缺失: {file_path.relative_to(BASE_DIR)}")
    
    if missing_files:
        print("\n⚠️  警告: 以下文件缺失，系統可能無法正常運行:")
        for file in missing_files:
            print(f"     - {file}")
        response = input("\n是否繼續啟動？(y/n): ")
        if response.lower() != 'y':
            print("❌ 系統啟動取消")
            return False
    
    return True

def install_dependencies():
    """檢查並安裝依賴"""
    print("\n📦 檢查 Python 依賴...")
    
    # 檢查必要庫
    required_packages = ['flask', 'flask_cors', 'requests', 'pandas', 'numpy']
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"  ✅ {package} 已安裝")
        except ImportError:
            missing_packages.append(package)
            print(f"  ❌ {package} 未安裝")
    
    if missing_packages:
        print(f"\n⚠️  需要安裝以下依賴: {', '.join(missing_packages)}")
        response = input("是否自動安裝？(y/n): ")
        if response.lower() == 'y':
            for package in missing_packages:
                print(f"  正在安裝 {package}...")
                os.system(f"{sys.executable} -m pip install {package} -q")
            print("  ✅ 依賴安裝完成")
        else:
            print("  ⚠️ 請手動安裝依賴: pip install flask flask-cors requests pandas numpy")
    
    # 檢查富途 API（可選）
    try:
        import futu
        print("  ✅ futu-api 已安裝")
    except ImportError:
        print("  ⚠️ futu-api 未安裝（日內交易功能受限）")
        print("     安裝命令: pip install futu-api")
    
    print("  ✅ 依賴檢查完成")

def open_browser():
    """延遲打開瀏覽器"""
    time.sleep(2)
    print("\n🌐 正在打開瀏覽器...")
    webbrowser.open('http://localhost:5000')

def start_server():
    """啟動服務器"""
    print("\n" + "="*60)
    print("🚀 StockAI 智能分析系統啟動中...")
    print("="*60)
    
    try:
        # 切換到 backend 目錄
        os.chdir(BACKEND_DIR)
        print(f"📂 工作目錄: {os.getcwd()}")
        
        # 導入 app
        from app import app
        
        print("\n📊 系統信息:")
        print(f"  - 後端 API: http://localhost:5000")
        print(f"  - 前端界面: http://localhost:5000")
        print(f"  - DeepSeek AI: 已集成")
        
        print("\n⏳ 正在啟動服務器...")
        print("   (按下 Ctrl+C 可以停止服務器)\n")
        
        # 啟動瀏覽器
        threading.Thread(target=open_browser, daemon=True).start()
        
        # 啟動 Flask 服務器
        app.run(
            host='0.0.0.0',
            port=5000,
            debug=True,
            use_reloader=False
        )
        
    except ImportError as e:
        print(f"\n❌ 導入錯誤: {e}")
        print("請確保所有依賴已安裝: pip install flask flask-cors requests pandas numpy")
    except Exception as e:
        print(f"\n❌ 啟動失敗: {e}")
        import traceback
        traceback.print_exc()
        print("\n💡 提示:")
        print("  1. 確保富途 OpenD 已啟動 (127.0.0.1:11111)")
        print("  2. 檢查端口 5000 是否被佔用")
        print("  3. 嘗試以管理員身份運行")

def main():
    """主函數"""
    print("""
    ╔══════════════════════════════════════════════════════╗
    ║                                                      ║
    ║     StockAI 智能分析系統 v1.4.6                      ║
    ║     Real-time Stock Analysis with DeepSeek AI        ║
    ║                                                      ║
    ║     🤖 DeepSeek AI 智能分析助手已集成                ║
    ║     📊 支持長線分析 + 日內交易                       ║
    ║                                                      ║
    ╚══════════════════════════════════════════════════════╝
    """)
    
    # 檢查環境
    if not check_environment():
        return
    
    # 檢查依賴
    install_dependencies()
    
    # 啟動服務器
    try:
        start_server()
    except KeyboardInterrupt:
        print("\n\n👋 系統已停止")
        print("感謝使用 StockAI 智能分析系統！")
    except Exception as e:
        print(f"\n❌ 系統錯誤: {e}")

if __name__ == '__main__':
    main()