'use client';

import { useEffect, useState } from 'react';
import { TrendingUp, TrendingDown, Search, Bell, Settings, Wallet, Newspaper, Zap, BarChart3, Activity, DollarSign, Users, Building2, ArrowUpRight, ArrowDownRight } from 'lucide-react';
import { getStocks, getStock, getStockHistory, getHotStocks, type StockInfo } from '@/lib/api';

// ── Types ──
interface KlineData { x: string; y: number[]; }

// ── Market Strip Component ──
function MarketStrip() {
  const markets = [
    { name: 'HSI', price: '22,148.6', change: '+248.2', pct: '+1.13%', up: true },
    { name: 'TECH', price: '5,326.8', change: '+89.4', pct: '+1.71%', up: true },
    { name: 'A50', price: '12,886.2', change: '-32.5', pct: '-0.25%', up: false },
    { name: 'SHCOMP', price: '3,286.5', change: '+12.8', pct: '+0.39%', up: true },
  ];
  return (
    <div className="flex gap-4 mb-5 overflow-x-auto pb-1">
      {markets.map(m => (
        <div key={m.name} className="flex-shrink-0 bg-[#0d1520] border border-[#1e2d45] rounded-xl px-5 py-3 min-w-[180px]">
          <div className="text-xs text-[#667799] uppercase tracking-wider">{m.name}</div>
          <div className="text-xl font-bold my-1">{m.price}</div>
          <div className={`text-sm ${m.up ? 'text-[#00d4aa]' : 'text-[#ff6b6b]'}`}>
            {m.up ? '▲' : '▼'} {m.change} ({m.pct})
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Top Bar ──
function TopBar() {
  return (
    <div className="bg-gradient-to-r from-[#0d1520] to-[#141d2e] border border-[#1e2d45] rounded-xl px-6 py-3 flex items-center justify-between mb-5">
      <div className="text-xl font-black tracking-wider">
        <span className="text-[#00d4aa]">STOCK</span><span className="text-[#4a8cff]">AI</span>
        <span className="ml-2 text-xs text-[#667799] font-normal">v2</span>
      </div>
      <div className="hidden md:flex gap-6">
        {['📊 儀表板', '🔍 個股分析', '💰 資金流向', '📈 策略', '📋 報告'].map(item => (
          <a key={item} href="#" className={`text-sm text-[#8899bb] hover:text-[#00d4aa] transition px-3 py-1.5 rounded-md ${item.includes('儀表板') ? 'text-[#00d4aa] bg-[rgba(0,212,170,0.08)] border-b-2 border-[#00d4aa]' : ''}`}>
            {item}
          </a>
        ))}
      </div>
      <div className="flex items-center gap-3 bg-[#1a2538] px-3.5 py-1.5 rounded-lg border border-[#2a3a55] text-sm">
        <span className="w-2 h-2 bg-[#00d4aa] rounded-full"></span>
        <span>Admin</span>
        <span className="text-[#667799] text-xs">▼</span>
      </div>
    </div>
  );
}

// ── Simulated Chart ──
function SimChart({ data }: { data: KlineData[] }) {
  if (!data.length) {
    return (
      <div className="flex items-end gap-[3px] h-[300px] mt-2.5">
        {Array.from({length: 30}).map((_, i) => {
          const h = 30 + Math.sin(i * 0.5) * 25 + Math.random() * 20;
          return <div key={i} className="flex-1 rounded-t-sm bg-gradient-to-b from-[#00d4aa] to-[rgba(0,212,170,0.3)]" style={{height: `${h}%`}} />;
        })}
      </div>
    );
  }
  return (
    <div className="flex items-end gap-[3px] h-[300px] mt-2.5">
      {data.slice(-30).map((c, i) => {
        const [, hi, lo, cl] = c.y;
        const isUp = cl >= lo;
        const maxP = Math.max(...data.slice(-30).map(d => d.y[1]));
        const minP = Math.min(...data.slice(-30).map(d => d.y[2]));
        const h = ((cl - minP) / (maxP - minP || 1)) * 85 + 10;
        return (
          <div
            key={i}
            className={`flex-1 rounded-t-sm ${
              isUp
                ? 'bg-gradient-to-b from-[#00d4aa] to-[rgba(0,212,170,0.3)]'
                : 'bg-gradient-to-b from-[rgba(255,107,107,0.3)] to-[#ff6b6b]'
            }`}
            style={{height: `${h}%`}}
            title={`O:${c.y[0]} H:${hi} L:${lo} C:${cl}`}
          />
        );
      })}
    </div>
  );
}

// ── Watchlist ──
function Watchlist({ stocks, selected, onSelect }: { stocks: StockInfo[]; selected: string; onSelect: (s: string) => void }) {
  return (
    <div className="bg-[#0d1520] border border-[#1e2d45] rounded-xl p-4">
      <div className="flex justify-between items-center mb-3">
        <span className="text-sm font-semibold text-[#4a8cff]">📋 自選股</span>
        <span className="text-xs text-[#667799]">{stocks.length} 隻</span>
      </div>
      {stocks.slice(0, 8).map(s => {
        const isUp = s.change_percent >= 0;
        const isSelected = s.symbol === selected;
        return (
          <div
            key={s.symbol}
            onClick={() => onSelect(s.symbol)}
            className={`flex justify-between items-center py-2.5 border-b border-[#1a2538] cursor-pointer transition rounded-md ${
              isSelected ? 'bg-[rgba(74,140,255,0.08)] mx-[-12px] px-3' : 'hover:bg-[rgba(74,140,255,0.04)] hover:mx-[-12px] hover:px-3 hover:rounded-md'
            }`}
          >
            <div>
              <div className="flex items-center gap-2">
                {s.symbol === '9988.HK' && <span className="w-1.5 h-1.5 bg-[#ff6b6b] rounded-full"></span>}
                <div className="text-sm font-semibold">{s.symbol}</div>
              </div>
              <div className="text-xs text-[#667799]">{s.name}</div>
            </div>
            <div className="text-right">
              <div className="text-sm font-semibold">${s.price.toFixed(2)}</div>
              <div className={`text-xs ${isUp ? 'text-[#00d4aa]' : 'text-[#ff6b6b]'}`}>
                {isUp ? '▲' : '▼'} {s.change_percent.toFixed(1)}%
              </div>
            </div>
          </div>
        );
      })}
      <div className="mt-2 text-center">
        <span className="text-[#4a8cff] text-xs cursor-pointer">+ 新增自選股</span>
      </div>
    </div>
  );
}

// ── Capital Flow Card ──
function CapitalFlow() {
  const flows = [
    { label: '主力淨流入', value: '+128.5億', up: true, pct: 75 },
    { label: '散戶淨流入', value: '-32.8億', up: false, pct: 25 },
    { label: '北向資金', value: '+45.2億', up: true, pct: 55 },
    { label: '南向資金', value: '+18.6億', up: true, pct: 30 },
  ];
  const sectors = [
    { name: '科技', value: '+42.3億', up: true, pct: 80 },
    { name: '金融', value: '+18.7億', up: true, pct: 45 },
    { name: '醫藥', value: '-12.5億', up: false, pct: 30 },
    { name: '消費', value: '-8.2億', up: false, pct: 20 },
  ];
  return (
    <div className="space-y-3">
      {/* Market Flow */}
      <div className="bg-[#0d1520] border border-[#1e2d45] rounded-xl p-4">
        <div className="flex justify-between mb-2">
          <span className="text-sm font-semibold">💰 大市資金流向</span>
          <span className="text-xs text-[#667799]">今日</span>
        </div>
        {flows.map(f => (
          <div key={f.label} className="mb-2.5">
            <div className="flex justify-between text-xs text-[#667799] mb-1">
              <span>{f.label}</span>
              <span className={f.up ? 'text-[#00d4aa]' : 'text-[#ff6b6b]'}>{f.value}</span>
            </div>
            <div className="h-1.5 bg-[#1a2538] rounded-full overflow-hidden">
              <div className={`h-full rounded-full transition-all duration-500 ${f.up ? 'bg-gradient-to-r from-[#00d4aa] to-[#00e6b8]' : 'bg-gradient-to-r from-[#ff6b6b] to-[#ff4444]'}`} style={{width: `${f.pct}%`}} />
            </div>
          </div>
        ))}
      </div>

      {/* Sector Rotation */}
      <div className="bg-[#0d1520] border border-[#1e2d45] rounded-xl p-4">
        <div className="flex justify-between mb-2">
          <span className="text-sm font-semibold">🏭 板塊資金輪動</span>
          <span className="text-xs text-[#667799]">5日</span>
        </div>
        {sectors.map(s => (
          <div key={s.name} className="mb-2">
            <div className="flex justify-between text-xs text-[#667799] mb-1">
              <span>{s.name}</span>
              <span className={s.up ? 'text-[#00d4aa]' : 'text-[#ff6b6b]'}>{s.value}</span>
            </div>
            <div className="h-1.5 bg-[#1a2538] rounded-full overflow-hidden">
              <div className={`h-full rounded-full ${s.up ? 'bg-gradient-to-r from-[#00d4aa] to-[#00e6b8]' : 'bg-gradient-to-r from-[#ff6b6b] to-[#ff4444]'}`} style={{width: `${s.pct}%`}} />
            </div>
          </div>
        ))}
        <div className="mt-2.5 text-center">
          <span className="text-[#4a8cff] text-xs cursor-pointer">查看完整板塊流向 →</span>
        </div>
      </div>

      {/* Stock Detail Flow */}
      <div className="bg-[#0d1520] border border-[#1e2d45] rounded-xl p-4">
        <div className="flex justify-between mb-2">
          <span className="text-sm font-semibold">🔥 個股資金細節</span>
          <span className="text-xs text-[#667799]">即時</span>
        </div>
        {[
          { label: '超大單淨流入', value: '+3.2億', up: true },
          { label: '大單淨流入', value: '+1.8億', up: true },
          { label: '中單淨流入', value: '-0.5億', up: false },
          { label: '小單淨流入', value: '-1.2億', up: false },
        ].map(item => (
          <div key={item.label} className="flex justify-between text-xs text-[#667799] py-1.5">
            <span>{item.label}</span>
            <span className={item.up ? 'text-[#00d4aa]' : 'text-[#ff6b6b]'}>{item.value}</span>
          </div>
        ))}
        <div className="mt-2 pt-1.5 border-t border-[#1a2538] text-xs text-[#667799]">
          主力淨額: <span className="text-[#00d4aa]">+5.0億</span> | 主力佔比: <span className="text-[#00d4aa]">62%</span>
        </div>
      </div>
    </div>
  );
}

// ── Bottom Panel ──
function BottomPanel() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-5">
      {/* AI Signals */}
      <div className="bg-[#0d1520] border border-[#1e2d45] rounded-xl p-4">
        <div className="text-sm font-semibold text-[#4a8cff] mb-2.5">🤖 AI 信號</div>
        {[
          { tag: '買入', cls: 'bg-[rgba(0,212,170,0.15)] text-[#00d4aa]', text: '0700.HK — DeepSeek R1 模型建議強勢買入，目標 $460' },
          { tag: '賣出', cls: 'bg-[rgba(255,107,107,0.15)] text-[#ff6b6b]', text: '0941.HK — 資金流出信號，建議減持' },
          { tag: '觀察', cls: 'bg-[rgba(74,140,255,0.15)] text-[#4a8cff]', text: '1211.HK — 技術指標金叉，成交量放大' },
        ].map((item, i) => (
          <div key={i} className="flex gap-2 py-2 border-b border-[#1a2538] text-sm items-start">
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium whitespace-nowrap mt-0.5 ${item.cls}`}>{item.tag}</span>
            <span className="text-[#e0e6f0]">{item.text}</span>
          </div>
        ))}
      </div>

      {/* News */}
      <div className="bg-[#0d1520] border border-[#1e2d45] rounded-xl p-4">
        <div className="text-sm font-semibold text-[#4a8cff] mb-2.5">📰 熱門新聞</div>
        {[
          { tag: '利好', cls: 'bg-[rgba(0,212,170,0.1)] text-[#00d4aa]', text: '騰訊 AI 晶片訂單超預期，大行上調目標價' },
          { tag: '利淡', cls: 'bg-[rgba(255,107,107,0.1)] text-[#ff6b6b]', text: '美團遭大股東減持套現 $50 億' },
          { tag: '中性', cls: 'bg-[rgba(74,140,255,0.1)] text-[#4a8cff]', text: '恒指季檢結果出爐，成份股不變' },
        ].map((item, i) => (
          <div key={i} className="flex gap-2 py-2 border-b border-[#1a2538] text-sm items-start">
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium whitespace-nowrap mt-0.5 ${item.cls}`}>{item.tag}</span>
            <span className="text-[#e0e6f0]">{item.text}</span>
          </div>
        ))}
      </div>

      {/* Quick Actions */}
      <div className="bg-[#0d1520] border border-[#1e2d45] rounded-xl p-4">
        <div className="text-sm font-semibold text-[#4a8cff] mb-2.5">⚡ 快速操作</div>
        <div className="flex flex-wrap gap-2">
          {['🔍 分析新股票', '📊 生成日報', '📈 Paper Trade', '💾 匯出報告'].map(action => (
            <span key={action} className="px-3.5 py-1.5 bg-[#1a2538] border border-[#2a3a55] rounded-md text-xs cursor-pointer hover:bg-[#2a3a55] transition">
              {action}
            </span>
          ))}
        </div>
        <div className="mt-3 p-2.5 bg-gradient-to-r from-[rgba(0,212,170,0.05)] to-[rgba(74,140,255,0.05)] rounded-lg border border-[#1e2d45]">
          <div className="text-xs text-[#667799]">今日 AI 分析配額</div>
          <div className="flex justify-between mt-1">
            <span className="font-semibold">42 / 100</span>
            <span className="text-[#00d4aa] text-xs">還剩 58 次</span>
          </div>
          <div className="h-1.5 bg-[#1a2538] rounded-full mt-1.5 overflow-hidden">
            <div className="h-full w-[42%] bg-gradient-to-r from-[#00d4aa] to-[#00e6b8] rounded-full" />
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main Page ──
export default function Home() {
  const [stocks, setStocks] = useState<StockInfo[]>([]);
  const [selectedStock, setSelectedStock] = useState('0700.HK');
  const [stockDetail, setStockDetail] = useState<StockInfo | null>(null);
  const [klineData, setKlineData] = useState<KlineData[]>([]);
  const [loading, setLoading] = useState(true);
  const [chartTab, setChartTab] = useState('日線');

  useEffect(() => {
    async function load() {
      try {
        const s = await getStocks();
        setStocks(s);
        if (s.length > 0) {
          const detail = await getStock(s[0].symbol);
          setStockDetail(detail);
          setSelectedStock(s[0].symbol);
          const hist = await getStockHistory(s[0].symbol, '1mo');
          setKlineData(hist);
        }
      } catch (e) {
        console.log('API unavailable, using demo layout');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  async function handleSelectStock(symbol: string) {
    setSelectedStock(symbol);
    try {
      const detail = await getStock(symbol);
      setStockDetail(detail);
      const period = chartTab === '日線' ? '1mo' : chartTab === '週線' ? '3mo' : '1y';
      const hist = await getStockHistory(symbol, period);
      setKlineData(hist);
    } catch (e) {
      console.log('Error loading stock');
    }
  }

  return (
    <div className="p-4 md:p-5 max-w-[1600px] mx-auto">
      <TopBar />
      <MarketStrip />

      {/* Main 3-Column Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr_320px] gap-4 mb-5">
        {/* Left: Watchlist */}
        <Watchlist stocks={stocks} selected={selectedStock} onSelect={handleSelectStock} />

        {/* Center: Chart */}
        <div className="bg-[#0d1520] border border-[#1e2d45] rounded-xl p-4 min-h-[400px] relative">
          <div className="flex justify-between items-center mb-4">
            <div>
              <span className="text-lg font-bold">{selectedStock}</span>
              <span className="text-[#667799] text-sm ml-2">
                {stockDetail?.name || '載入中...'}
              </span>
              {stockDetail && (
                <span className={`ml-3 text-lg font-bold ${stockDetail.change >= 0 ? 'text-[#00d4aa]' : 'text-[#ff6b6b]'}`}>
                  ${stockDetail.price.toFixed(2)}
                </span>
              )}
            </div>
            <div className="flex gap-2">
              {['日線', '週線', '月線', '1分', '5分'].map(tab => (
                <button
                  key={tab}
                  onClick={() => setChartTab(tab)}
                  className={`px-3 py-1 rounded-md text-xs cursor-pointer transition ${
                    chartTab === tab
                      ? 'bg-[#4a8cff] text-white border border-[#4a8cff]'
                      : 'bg-[#1a2538] text-[#667799] border border-[#2a3a55] hover:text-[#e0e6f0]'
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>
          </div>

          {/* Price Info */}
          {stockDetail && (
            <div className="flex gap-5 mb-2 text-xs text-[#667799]">
              <span>開 <span className="font-semibold text-[#e0e6f0]">${stockDetail.open.toFixed(2)}</span></span>
              <span>高 <span className="font-semibold text-[#e0e6f0]">${stockDetail.high.toFixed(2)}</span></span>
              <span>低 <span className="font-semibold text-[#e0e6f0]">${stockDetail.low.toFixed(2)}</span></span>
              <span>成交量 <span className="font-semibold text-[#e0e6f0]">{stockDetail.volume}</span></span>
              <span>市值 <span className="font-semibold text-[#e0e6f0]">${(stockDetail.market_cap / 1e12).toFixed(2)}T</span></span>
            </div>
          )}

          {/* K-Line Chart */}
          <SimChart data={klineData} />

          {/* Moving Averages */}
          <div className="mt-2.5 flex gap-5 text-xs text-[#667799]">
            <span>MA5: 418.30</span>
            <span>MA20: 402.15</span>
            <span>MA60: 385.40</span>
            <span className="text-[#00d4aa]">RSI: 62.5</span>
            <span className="text-[#4a8cff]">MACD: 買入信號</span>
          </div>

          {loading && (
            <div className="absolute inset-0 flex items-center justify-center bg-[rgba(13,21,32,0.8)] rounded-xl">
              <div className="text-center">
                <div className="w-8 h-8 border-2 border-[#4a8cff] border-t-transparent rounded-full animate-spin mx-auto mb-2" />
                <div className="text-xs text-[#667799]">載入中...</div>
              </div>
            </div>
          )}
        </div>

        {/* Right: Capital Flow */}
        <CapitalFlow />
      </div>

      {/* Bottom Row */}
      <BottomPanel />

      {/* Footer */}
      <div className="text-center mt-6 text-[#334466] text-xs">
        StockAI v2 — Intelligent Stock Analysis System
      </div>
    </div>
  );
}
