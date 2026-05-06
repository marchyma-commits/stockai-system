# StockAI v1.6D 平滑重启脚本
# 创建时间: 2026-04-08
# 用途: 安全重启Flask服务器并加载最新代码

param(
    [switch]$Rollback,  # 回滚模式
    [string]$BackupDir = ""  # 指定备份目录
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   StockAI v1.6D 服务器重启工具" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 设置路径
$ProjectDir = "C:/Users/MarcoMa/stockai_system_v1.6D"
$BackendDir = "$ProjectDir/backend"

# 回滚模式
if ($Rollback) {
    if (-not $BackupDir -or -not (Test-Path $BackupDir)) {
        # 查找最新的备份
        $latestBackup = Get-ChildItem -Path $ProjectDir -Filter "backup_*" -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if (-not $latestBackup) {
            Write-Host "❌ 未找到备份目录" -ForegroundColor Red
            exit 1
        }
        $BackupDir = $latestBackup.FullName
    }
    
    Write-Host "🔄 回滚模式" -ForegroundColor Yellow
    Write-Host "📁 备份目录: $BackupDir" -ForegroundColor Gray
    Write-Host ""
    
    # 停止服务器
    Write-Host "⏹️  停止当前服务器..." -ForegroundColor Yellow
    $pythonProcesses = Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object { 
        $_.Path -like "*$BackendDir*" 
    }
    if ($pythonProcesses) {
        $pythonProcesses | Stop-Process -Force
        Write-Host "✅ 已停止 Python 进程" -ForegroundColor Green
    } else {
        Write-Host "⚠️  未找到运行中的 Python 进程" -ForegroundColor Yellow
    }
    Start-Sleep -Seconds 2
    
    # 恢复备份
    Write-Host "📦 恢复备份文件..." -ForegroundColor Yellow
    Copy-Item "$BackupDir/app.py" "$BackendDir/app.py" -Force
    Copy-Item "$BackupDir/multi_model_ai.py" "$BackendDir/multi_model_ai.py" -Force
    Copy-Item "$BackupDir/hkex_financials.py" "$BackendDir/hkex_financials.py" -Force
    Write-Host "✅ 备份文件已恢复" -ForegroundColor Green
    
    # 重新启动
    Write-Host ""
    Write-Host "🚀 重新启动服务器..." -ForegroundColor Green
    Start-Sleep -Seconds 1
    
    Set-Location $BackendDir
    Start-Process python -ArgumentList "app.py" -NoNewWindow
    
    Write-Host ""
    Write-Host "✅ 回滚完成！服务器已重启" -ForegroundColor Green
    Write-Host "🌐 访问: http://localhost:5000" -ForegroundColor Cyan
    exit 0
}

# 正常重启模式
Write-Host "🚀 正常重启模式" -ForegroundColor Green
Write-Host ""

# 1. 检查当前服务器状态
Write-Host "📊 步骤 1/5: 检查当前服务器状态..." -ForegroundColor Cyan
$pythonProcesses = Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object { 
    $_.Path -like "*$BackendDir*" 
}

if ($pythonProcesses) {
    Write-Host "   发现运行中的 Python 进程:" -ForegroundColor Gray
    $pythonProcesses | ForEach-Object {
        $duration = (Get-Date) - $_.StartTime
        Write-Host "   - PID: $($_.Id), 运行时长: $($duration.Hours)小时 $($duration.Minutes)分钟" -ForegroundColor Gray
    }
} else {
    Write-Host "   ⚠️  未找到运行中的 Python 进程" -ForegroundColor Yellow
}
Write-Host ""

# 2. 创建备份
Write-Host "📦 步骤 2/5: 创建代码备份..." -ForegroundColor Cyan
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = "$ProjectDir/backup_$timestamp"
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Copy-Item "$BackendDir/app.py" $backupDir -Force
Copy-Item "$BackendDir/multi_model_ai.py" $backupDir -Force
Copy-Item "$BackendDir/hkex_financials.py" $backupDir -Force
Write-Host "   ✅ 备份已创建: $backupDir" -ForegroundColor Green
Write-Host ""

# 3. 停止服务器
Write-Host "⏹️  步骤 3/5: 停止当前服务器..." -ForegroundColor Cyan
if ($pythonProcesses) {
    $pythonProcesses | Stop-Process -Force
    Write-Host "   ✅ 服务器已停止" -ForegroundColor Green
} else {
    Write-Host "   ⚠️  没有需要停止的进程" -ForegroundColor Yellow
}
Start-Sleep -Seconds 2

# 验证端口释放
$portCheck = netstat -ano | findstr ":5000"
if ($portCheck) {
    Write-Host "   ⚠️  端口 5000 仍被占用，强制释放..." -ForegroundColor Yellow
    # 强制结束占用端口的进程
    $portCheck | ForEach-Object {
        $parts = $_ -split '\s+'
        $procId = $parts[-1]
        if ($procId -match '^\d+$') {
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 1
}
Write-Host ""

# 4. 验证代码
Write-Host "🔍 步骤 4/5: 验证代码更新..." -ForegroundColor Cyan
Set-Location $BackendDir

# 检查 multi_model_ai.py 是否包含新方法
$hasNewCode = Select-String -Path "multi_model_ai.py" -Pattern "_get_financial_data" -Quiet
if ($hasNewCode) {
    Write-Host "   ✅ multi_model_ai.py 包含财务数据获取逻辑" -ForegroundColor Green
} else {
    Write-Host "   ❌ multi_model_ai.py 缺少财务数据获取逻辑" -ForegroundColor Red
    Write-Host "   请先修复代码再重启" -ForegroundColor Red
    exit 1
}

# 检查 app.py 是否包含热重载端点
$hasReloadEndpoint = Select-String -Path "app.py" -Pattern "reload_modules" -Quiet
if ($hasReloadEndpoint) {
    Write-Host "   ✅ app.py 包含热重载端点" -ForegroundColor Green
} else {
    Write-Host "   ⚠️  app.py 缺少热重载端点（可选）" -ForegroundColor Yellow
}
Write-Host ""

# 5. 启动服务器
Write-Host "🚀 步骤 5/5: 启动新服务器..." -ForegroundColor Cyan
Start-Sleep -Seconds 1

# 使用 Start-Process 启动，不阻塞当前终端
Start-Process python -ArgumentList "app.py" -NoNewWindow -WorkingDirectory $BackendDir

# 等待服务器启动
Write-Host "   ⏳ 等待服务器启动..." -ForegroundColor Gray
Start-Sleep -Seconds 3

# 验证服务器是否启动成功
try {
    $response = Invoke-RestMethod -Uri "http://localhost:5000/api/hkex/summary/0700" -Method GET -TimeoutSec 5
    Write-Host "   ✅ 服务器启动成功" -ForegroundColor Green
    Write-Host "   📊 API 测试: /api/hkex/summary/0700 响应正常" -ForegroundColor Green
} catch {
    Write-Host "   ⚠️  服务器可能仍在启动中，请稍后再验证" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   ✅ 重启完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "🌐 访问地址: http://localhost:5000" -ForegroundColor Cyan
Write-Host ""
Write-Host "📋 验证清单:" -ForegroundColor White
Write-Host "   1. 打开 http://localhost:5000" -ForegroundColor Gray
Write-Host "   2. 搜索 0700.HK (腾讯)" -ForegroundColor Gray
Write-Host "   3. 检查 AI 分析师是否显示财务数据" -ForegroundColor Gray
Write-Host "   4. 检查评分是否为动态计算（非固定38/100）" -ForegroundColor Gray
Write-Host ""
Write-Host "🔄 如需回滚，请运行:" -ForegroundColor Yellow
Write-Host "   .\restart_server.ps1 -Rollback -BackupDir '$backupDir'" -ForegroundColor Yellow
Write-Host ""
