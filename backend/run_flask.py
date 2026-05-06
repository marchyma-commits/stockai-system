# -*- coding: utf-8 -*-
"""Start Flask server and test it"""
import subprocess
import time
import requests
import sys

# Start Flask
print("Starting Flask...")
proc = subprocess.Popen(
    [sys.executable, "app.py"],
    cwd="C:/Users/MarcoMa/stockai_system_v1.7/backend",
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)
time.sleep(6)

# Check if running
try:
    r = requests.get("http://localhost:5000/api/hkex/financial/00005.HK", timeout=15)
    d = r.json()
    rd = d["data"][0]["data"][0]
    ratios = rd["ratios"]
    print(f"EPS: {ratios.get('eps')}")
    print(f"EPS USD: {ratios.get('epsUsd')}")
    print(f"BPS: {ratios.get('bps')}")
    print(f"BPS USD: {ratios.get('bpsUsd')}")
    print(f"USD财报: {ratios.get('_isUsdReport')}")
    print(f"股息率: {ratios.get('dividendYield')}%")
    print(f"派息率: {ratios.get('payoutRatio')}%")
except Exception as e:
    print(f"Error: {e}")
    stdout, stderr = proc.communicate(timeout=1)
    if stdout:
        print("STDOUT:", stdout.decode()[:500])
    if stderr:
        print("STDERR:", stderr.decode()[:500])
