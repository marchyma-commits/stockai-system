"""启动服务器并查看日志"""
import subprocess
import sys
import time

print("启动 Flask 服务器...")
proc = subprocess.Popen(
    [sys.executable, 'app.py'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1
)

# 实时输出日志
for line in proc.stdout:
    print(line, end='')
    # 如果服务器启动完成，等待一下再终止
    if "Running on" in line:
        print("\n服务器已启动，按 Ctrl+C 停止...")
        time.sleep(3)
        break

proc.terminate()
stdout, _ = proc.communicate(timeout=3)
print("\n--- 剩余日志 ---")
print(stdout)
