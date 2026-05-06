@echo off
echo ========================================
echo   StockAI 智能分析系統 - 安裝腳本
echo ========================================
echo.

echo 步驟 1: 升級 pip
python -m pip install --upgrade pip
echo.

echo 步驟 2: 卸載有問題的 setuptools
pip uninstall setuptools -y
echo.

echo 步驟 3: 安裝指定版本的 setuptools
pip install setuptools==70.0.0 wheel==0.38.4
echo.

echo 步驟 4: 安裝 numpy
pip install numpy==1.24.3
echo.

echo 步驟 5: 安裝 pandas
pip install pandas==2.0.3
echo.

echo 步驟 6: 安裝其他依賴
pip install -r backend\requirements.txt
echo.

echo ========================================
echo ✅ 安裝完成！
echo.
echo 現在可以運行: python run.py
echo ========================================
pause