# StockAI v1.7 升级说明

## 升级日期: 2026-04-10

## 新增功能

### 1. TradingView MCP 集成
- 30+ 技术指标
- 多时间框架分析
- AI 情绪分析
- 策略回测功能

### 2. 港股代码自动转换
- 自动将 00005.HK 转换为 TradingView 可识别的格式
- 支持 Yahoo Finance 格式

### 3. 并行数据源架构
- 现有层: akshare + 富途 OpenD
- 新增层: TradingView MCP

## 技术架构

```
StockAI v1.7
├── backend/
│   ├── app.py                    # Flask 主应用
│   ├── hkex_crawler_v3.py       # 港交所数据爬虫
│   ├── futu_quote.py             # 富途行情
│   └── tradingview_adapter.py    # [NEW] TradingView 适配器
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── stockai_data/
│   ├── watchlist.json
│   ├── cache/
│   └── [NEW] hk_ticker_mapping.json  # 港股代码映射表
└── [NEW] stockai_mcp/           # MCP Server 配置
    └── config.json
```

## 使用方法

### 启动 MCP Server
```bash
cd C:/Users/MarcoMa/stockai_mcp
uvx tradingview-mcp-server
```

### 查询港股技术分析
- 输入: 00005.HK
- 系统自动转换为: HSBC Holdings (或 Yahoo Finance 格式)
- 返回: TradingView 技术分析 + 本地财务数据

## 备份位置
- C:/Users/MarcoMa/stockai_backup/
  - stockai_system_v1.6D_20260410_122034/
  - stockai_data_20260410_122034/
