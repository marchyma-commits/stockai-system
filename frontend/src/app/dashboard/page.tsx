'use client';

import { useState, useEffect } from 'react';
import { ThemeProvider, useTheme } from '@/components/theme/ThemeProvider';
import { I18nProvider, useI18n, locales } from '@/lib/i18n';
import { getStocks, getStock, type StockInfo } from '@/lib/api';

function KLineChart({ height = 280 }: { height?: number }) {
  return (
    <div className="flex items-end gap-[2px]" style={{ height }}>
      {Array.from({length: 30}).map((_, i) => {
        const h = 20 + Math.sin(i * 0.5) * 20 + Math.cos(i * 0.3) * 10 + Math.random() * 15;
        return (
          <div key={i} className="flex-1 rounded-t-sm transition-all duration-300"
            style={{height: `${Math.max(h,5)}%`, background: i % 3 === 0 ? 'linear-gradient(to top, var(--chart-candle-down), transparent)' : 'linear-gradient(to top, var(--chart-candle-up), transparent)', opacity: 0.7 + (i/30)*0.3}} />
        );
      })}
    </div>
  );
}

function MarketStrip() {
  const markets = [
    { name: 'HSI', price: '22,148.6', change: '+248.2', pct: '+1.13%', up: true },
    { name: 'TECH', price: '5,326.8', change: '+89.4', pct: '+1.71%', up: true },
    { name: 'A50', price: '12,886.2', change: '-32.5', pct: '-0.25%', up: false },
    { name: 'SHCOMP', price: '3,286.5', change: '+12.8', pct: '+0.39%', up: true },
  ];
  return (
    <div className="flex gap-3 mb-6 overflow-x-auto pb-1">
      {markets.map(m => (
        <div key={m.name} className="flex-shrink-0 rounded-xl px-5 py-3 min-w-[170px] card-hover" style={{background:'var(--bg-card)', border:'1px solid var(--border-color)'}}>
          <div className="text-xs font-semibold tracking-wider uppercase" style={{color:'var(--text-muted)'}}>{m.name}</div>
          <div className="text-xl font-bold my-1">{m.price}</div>
          <div className="text-sm font-medium" style={{color: m.up ? 'var(--accent-green)' : 'var(--accent-red)'}}>{m.up ? '▲' : '▼'} {m.change} ({m.pct})</div>
        </div>
      ))}
    </div>
  );
}

function TopBar() {
  const { t, locale, setLocale } = useI18n();
  const { theme, toggleTheme } = useTheme();
  const navItems = [t('nav','dashboard'), t('nav','analysis'), t('nav','capitalFlow'), t('nav','strategy'), t('nav','reports')];
  return (
    <div className="glass rounded-xl px-6 py-3 flex items-center justify-between mb-6">
      <div className="flex items-center gap-8">
        <div className="text-xl font-black tracking-wider">
          <span style={{color:'var(--accent-green)'}}>STOCK</span><span style={{color:'var(--accent-blue)'}}>AI</span>
          <span className="ml-2 text-xs font-normal" style={{color:'var(--text-muted)'}}>v2</span>
        </div>
        <div className="hidden md:flex gap-1">
          {navItems.map((item, i) => (
            <a key={i} href="#" className="px-3 py-1.5 text-sm rounded-lg transition-all" style={{color: i===0 ? 'var(--accent-green)' : 'var(--text-secondary)', background: i===0 ? 'rgba(0,212,170,0.1)' : 'transparent', fontWeight: i===0 ? 600 : 400}}>{item}</a>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <div className="flex gap-0.5 rounded-lg p-0.5" style={{background:'var(--bg-primary)'}}>
          {locales.map(l => (
            <button key={l} onClick={() => setLocale(l)}
              className="px-2 py-1 text-[10px] rounded-md cursor-pointer transition-all font-medium"
              style={{background: locale===l ? 'var(--accent-blue)' : 'transparent', color: locale===l ? '#fff' : 'var(--text-muted)'}}>
              {l === 'zh-hk' ? '繁' : l === 'zh-cn' ? '简' : 'EN'}
            </button>
          ))}
        </div>
        <button onClick={toggleTheme} className="px-2.5 py-1.5 text-xs rounded-lg cursor-pointer border" style={{background:'var(--bg-card)', borderColor:'var(--border-color)', color:'var(--text-secondary)'}}>
          {theme === 'dark' ? '☀️' : '🌙'}
        </button>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm border" style={{background:'var(--bg-hover)', borderColor:'var(--border-light)'}}>
          <span className="w-2 h-2 rounded-full" style={{background:'var(--accent-green)'}} />
          <span>Admin</span>
        </div>
      </div>
    </div>
  );
}

function Watchlist({ stocks, selected, onSelect }: { stocks: StockInfo[]; selected: string; onSelect: (s:string)=>void }) {
  const { t } = useI18n();
  return (
    <div className="rounded-xl p-4" style={{background:'var(--bg-card)', border:'1px solid var(--border-color)'}}>
      <div className="flex justify-between items-center mb-3">
        <span className="text-sm font-semibold" style={{color:'var(--accent-blue)'}}>📋 {t('dashboard','watchlist')}</span>
        <span className="text-xs" style={{color:'var(--text-muted)'}}>{stocks.length} {t('dashboard','stocks')}</span>
      </div>
      {stocks.slice(0,7).map(s => {
        const isUp = s.change_percent >= 0;
        const isSel = s.symbol === selected;
        return (
          <div key={s.symbol} onClick={() => onSelect(s.symbol)}
            className="flex justify-between items-center py-2.5 cursor-pointer rounded-lg transition-all border-b"
            style={{borderColor:'var(--border-color)', background: isSel ? 'var(--bg-hover)' : 'transparent', margin: isSel ? '0 -8px' : '0', padding: isSel ? '10px 16px' : '10px 0'}}>
            <div>
              <div className="text-sm font-semibold">{s.symbol}</div>
              <div className="text-xs" style={{color:'var(--text-muted)'}}>{s.name}</div>
            </div>
            <div className="text-right">
              <div className="text-sm font-semibold">${s.price.toFixed(2)}</div>
              <div className="text-xs font-medium" style={{color: isUp ? 'var(--accent-green)' : 'var(--accent-red)'}}>{isUp ? '▲' : '▼'} {s.change_percent.toFixed(1)}%</div>
            </div>
          </div>
        );
      })}
      <div className="text-center mt-2"><span className="text-xs cursor-pointer" style={{color:'var(--accent-blue)'}}>{t('dashboard','addStock')}</span></div>
    </div>
  );
}

function CapitalFlowPanel() {
  const { t } = useI18n();
  const flows = [
    { label: t('dashboard','mainInflow'), value: '+128.5億', up: true, pct: 75 },
    { label: t('dashboard','retailInflow'), value: '-32.8億', up: false, pct: 25 },
    { label: t('dashboard','northbound'), value: '+45.2億', up: true, pct: 55 },
    { label: t('dashboard','southbound'), value: '+18.6億', up: true, pct: 30 },
  ];
  const sectors = [
    { name: '科技', value: '+42.3億', up: true, pct: 80 },
    { name: '金融', value: '+18.7億', up: true, pct: 45 },
    { name: '醫藥', value: '-12.5億', up: false, pct: 30 },
    { name: '消費', value: '-8.2億', up: false, pct: 20 },
  ];
  return (
    <div className="space-y-3">
      <div className="rounded-xl p-4" style={{background:'var(--bg-card)', border:'1px solid var(--border-color)'}}>
        <div className="flex justify-between mb-3"><span className="text-sm font-semibold">💰 {t('dashboard','capitalFlow')}</span><span className="text-xs" style={{color:'var(--text-muted)'}}>{t('dashboard','today')}</span></div>
        {flows.map(f => (
          <div key={f.label} className="mb-2.5">
            <div className="flex justify-between text-xs mb-1" style={{color:'var(--text-muted)'}}>
              <span>{f.label}</span><span style={{color: f.up ? 'var(--accent-green)' : 'var(--accent-red)'}}>{f.value}</span>
            </div>
            <div className="h-1.5 rounded-full overflow-hidden" style={{background:'var(--bg-primary)'}}>
              <div className="h-full rounded-full transition-all duration-700" style={{width:`${f.pct}%`, background: f.up ? 'var(--gradient-green)' : 'linear-gradient(90deg, var(--accent-red), #ff4444)'}} />
            </div>
          </div>
        ))}
      </div>
      <div className="rounded-xl p-4" style={{background:'var(--bg-card)', border:'1px solid var(--border-color)'}}>
        <div className="flex justify-between mb-3"><span className="text-sm font-semibold">🏭 {t('dashboard','sectorRotation')}</span><span className="text-xs" style={{color:'var(--text-muted)'}}>{t('dashboard','days5')}</span></div>
        {sectors.map(s => (
          <div key={s.name} className="mb-2">
            <div className="flex justify-between text-xs mb-1" style={{color:'var(--text-muted)'}}>
              <span>{s.name}</span><span style={{color: s.up ? 'var(--accent-green)' : 'var(--accent-red)'}}>{s.value}</span>
            </div>
            <div className="h-1.5 rounded-full overflow-hidden" style={{background:'var(--bg-primary)'}}>
              <div className="h-full rounded-full" style={{width:`${s.pct}%`, background: s.up ? 'var(--gradient-green)' : 'linear-gradient(90deg, var(--accent-red), #ff4444)'}} />
            </div>
          </div>
        ))}
      </div>
      <div className="rounded-xl p-4" style={{background:'var(--bg-card)', border:'1px solid var(--border-color)'}}>
        <div className="flex justify-between mb-3"><span className="text-sm font-semibold">🔥 {t('dashboard','stockDetail')}</span><span className="text-xs" style={{color:'var(--text-muted)'}}>{t('dashboard','realtime')}</span></div>
        {[
          { label: '超大單淨流入', value: '+3.2億', up: true },
          { label: '大單淨流入', value: '+1.8億', up: true },
          { label: '中單淨流入', value: '-0.5億', up: false },
          { label: '小單淨流入', value: '-1.2億', up: false },
        ].map(item => (
          <div key={item.label} className="flex justify-between text-xs py-1.5" style={{color:'var(--text-muted)'}}>
            <span>{item.label}</span><span style={{color: item.up ? 'var(--accent-green)' : 'var(--accent-red)'}}>{item.value}</span>
          </div>
        ))}
        <div className="mt-2 pt-2 text-xs border-t" style={{borderColor:'var(--border-color)', color:'var(--text-muted)'}}>
          {t('dashboard','mainForce')}: <span style={{color:'var(--accent-green)'}}>+5.0億</span> | {t('dashboard','mainRatio')}: <span style={{color:'var(--accent-green)'}}>62%</span>
        </div>
      </div>
    </div>
  );
}

function BottomPanels() {
  const { t } = useI18n();
  const signals = [
    { tag: '買入', cls: 'rgba(0,212,170,0.15)', color: 'var(--accent-green)', text: '0700.HK — DeepSeek R1 模型建議強勢買入，目標 $460' },
    { tag: '賣出', cls: 'rgba(255,107,107,0.15)', color: 'var(--accent-red)', text: '0941.HK — 資金流出信號，建議減持' },
    { tag: '觀察', cls: 'rgba(74,140,255,0.15)', color: 'var(--accent-blue)', text: '1211.HK — 技術指標金叉，成交量放大' },
  ];
  const news = [
    { tag: '利好', cls: 'rgba(0,212,170,0.1)', color: 'var(--accent-green)', text: '騰訊 AI 晶片訂單超預期，大行上調目標價' },
    { tag: '利淡', cls: 'rgba(255,107,107,0.1)', color: 'var(--accent-red)', text: '美團遭大股東減持套現 $50 億' },
    { tag: '中性', cls: 'rgba(74,140,255,0.1)', color: 'var(--accent-blue)', text: '恒指季檢結果出爐，成份股不變' },
  ];
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
      <div className="rounded-xl p-4 card-hover" style={{background:'var(--bg-card)', border:'1px solid var(--border-color)'}}>
        <div className="text-sm font-semibold mb-3" style={{color:'var(--accent-blue)'}}>🤖 {t('dashboard','aiSignals')}</div>
        {signals.map((item,i) => (
          <div key={i} className="flex gap-2 py-2 text-sm items-start border-b" style={{borderColor:'var(--border-color)'}}>
            <span className="text-[10px] px-1.5 py-0.5 rounded font-medium whitespace-nowrap mt-0.5" style={{background:item.cls, color:item.color}}>{item.tag}</span>
            <span style={{color:'var(--text-primary)'}}>{item.text}</span>
          </div>
        ))}
      </div>
      <div className="rounded-xl p-4 card-hover" style={{background:'var(--bg-card)', border:'1px solid var(--border-color)'}}>
        <div className="text-sm font-semibold mb-3" style={{color:'var(--accent-blue)'}}>📰 {t('dashboard','hotNews')}</div>
        {news.map((item,i) => (
          <div key={i} className="flex gap-2 py-2 text-sm items-start border-b" style={{borderColor:'var(--border-color)'}}>
            <span className="text-[10px] px-1.5 py-0.5 rounded font-medium whitespace-nowrap mt-0.5" style={{background:item.cls, color:item.color}}>{item.tag}</span>
            <span style={{color:'var(--text-primary)'}}>{item.text}</span>
          </div>
        ))}
      </div>
      <div className="rounded-xl p-4 card-hover" style={{background:'var(--bg-card)', border:'1px solid var(--border-color)'}}>
        <div className="text-sm font-semibold mb-3" style={{color:'var(--accent-blue)'}}>⚡ {t('dashboard','quickActions')}</div>
        <div className="flex flex-wrap gap-2">
          {['🔍 分析新股票', '📊 生成日報', '📈 Paper Trade', '💾 匯出報告'].map(a => (
            <span key={a} className="px-3 py-1.5 rounded-lg text-xs cursor-pointer hover:opacity-70 transition-all" style={{background:'var(--bg-primary)', border:'1px solid var(--border-light)', color:'var(--text-secondary)'}}>{a}</span>
          ))}
        </div>
        <div className="mt-4 p-3 rounded-lg" style={{background:'linear-gradient(135deg, rgba(0,212,170,0.05), rgba(74,140,255,0.05))', border:'1px solid var(--border-color)'}}>
          <div className="text-xs" style={{color:'var(--text-muted)'}}>{t('dashboard','quota')}</div>
          <div className="flex justify-between mt-1"><span className="font-semibold text-sm">42 / 100</span><span className="text-xs" style={{color:'var(--accent-green)'}}>{t('dashboard','remaining')} 58 {t('dashboard','times')}</span></div>
          <div className="h-1.5 rounded-full mt-2 overflow-hidden" style={{background:'var(--bg-primary)'}}><div className="h-full w-[42%] rounded-full" style={{background:'var(--gradient-green)'}} /></div>
        </div>
      </div>
    </div>
  );
}

function ComplianceFooter() {
  const { t } = useI18n();
  return (
    <footer className="mt-8 pt-6 border-t text-center" style={{borderColor:'var(--border-color)'}}>
      <div className="max-w-3xl mx-auto space-y-2">
        <p className="text-xs leading-relaxed" style={{color:'var(--text-muted)'}}>{t('compliance','disclaimer')}</p>
        <p className="text-xs" style={{color:'var(--text-muted)'}}>{t('compliance','dataSource')}</p>
        <div className="flex justify-center gap-4 mt-3">
          <span className="text-xs cursor-pointer hover:underline" style={{color:'var(--accent-blue)'}}>{t('compliance','privacy')}</span>
          <span className="text-xs cursor-pointer hover:underline" style={{color:'var(--accent-blue)'}}>{t('compliance','terms')}</span>
          <span className="text-xs cursor-pointer hover:underline" style={{color:'var(--accent-blue)'}}>{t('compliance','contact')}</span>
        </div>
        <p className="text-xs mt-2" style={{color:'var(--text-muted)'}}>{t('compliance','copyright')}</p>
      </div>
    </footer>
  );
}

function DashboardContent() {
  const { t } = useI18n();
  const [stocks, setStocks] = useState<StockInfo[]>([]);
  const [selectedStock, setSelectedStock] = useState('0700.HK');
  const [stockDetail, setStockDetail] = useState<StockInfo | null>(null);
  const [chartTab, setChartTab] = useState('日線');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getStocks().then(s => {
      setStocks(s);
      if (s.length > 0) getStock(s[0].symbol).then(d => { setStockDetail(d); setSelectedStock(s[0].symbol); });
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  async function handleSelect(symbol: string) {
    setSelectedStock(symbol);
    try { setStockDetail(await getStock(symbol)); } catch {}
  }

  return (
    <div className="min-h-screen p-4 md:p-6" style={{background:'var(--bg-primary)'}}>
      <div className="max-w-[1600px] mx-auto">
        <TopBar />
        <MarketStrip />
        <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr_300px] gap-4 mb-5">
          <Watchlist stocks={stocks} selected={selectedStock} onSelect={handleSelect} />
          <div className="rounded-xl p-5 relative overflow-hidden" style={{background:'var(--bg-card)', border:'1px solid var(--border-color)'}}>
            <div className="flex justify-between items-center mb-4 flex-wrap gap-2">
              <div className="flex items-center gap-3 flex-wrap">
                <span className="text-xl font-bold">{selectedStock}</span>
                {stockDetail && <span className="text-sm" style={{color:'var(--text-muted)'}}>{stockDetail.name}</span>}
                {stockDetail && (
                  <>
                    <span className="text-xl font-bold" style={{color: stockDetail.change >= 0 ? 'var(--accent-green)' : 'var(--accent-red)'}}>${stockDetail.price.toFixed(2)}</span>
                    <span className="text-sm font-medium px-2 py-0.5 rounded" style={{background: stockDetail.change >= 0 ? 'rgba(0,212,170,0.1)' : 'rgba(255,107,107,0.1)', color: stockDetail.change >= 0 ? 'var(--accent-green)' : 'var(--accent-red)'}}>{stockDetail.change_percent > 0 ? '+' : ''}{stockDetail.change_percent.toFixed(2)}%</span>
                  </>
                )}
              </div>
              <div className="flex gap-1">
                {['日線', '週線', '月線', '1分', '5分'].map(t => (
                  <button key={t} onClick={() => setChartTab(t)}
                    className="px-3 py-1 text-xs rounded-lg cursor-pointer transition-all"
                    style={{background: chartTab===t ? 'var(--gradient-accent)' : 'var(--bg-primary)', border:'1px solid var(--border-light)', color: chartTab===t ? '#fff' : 'var(--text-secondary)'}}>{t}</button>
                ))}
              </div>
            </div>
            {stockDetail && (
              <div className="flex flex-wrap gap-4 mb-3 text-xs" style={{color:'var(--text-muted)'}}>
                <span>開 <strong style={{color:'var(--text-primary)'}}>${stockDetail.open.toFixed(2)}</strong></span>
                <span>高 <strong style={{color:'var(--text-primary)'}}>${stockDetail.high.toFixed(2)}</strong></span>
                <span>低 <strong style={{color:'var(--text-primary)'}}>${stockDetail.low.toFixed(2)}</strong></span>
                <span>成交量 <strong style={{color:'var(--text-primary)'}}>{stockDetail.volume}</strong></span>
                <span>市值 <strong style={{color:'var(--text-primary)'}}>${(stockDetail.market_cap/1e12).toFixed(2)}T</strong></span>
              </div>
            )}
            <KLineChart height={280} />
            <div className="flex flex-wrap gap-4 mt-3 text-xs" style={{color:'var(--text-muted)'}}>
              <span>MA5: <strong style={{color:'var(--text-primary)'}}>418.30</strong></span>
              <span>MA20: <strong style={{color:'var(--text-primary)'}}>402.15</strong></span>
              <span>MA60: <strong style={{color:'var(--text-primary)'}}>385.40</strong></span>
              <span className="px-1.5 py-0.5 rounded" style={{background:'rgba(0,212,170,0.1)', color:'var(--accent-green)'}}>RSI: 62.5</span>
              <span className="px-1.5 py-0.5 rounded" style={{background:'rgba(74,140,255,0.1)', color:'var(--accent-blue)'}}>MACD: 買入信號</span>
            </div>
            {loading && (
              <div className="absolute inset-0 flex items-center justify-center rounded-xl" style={{background:'rgba(13,21,32,0.7)'}}>
                <div className="text-center"><div className="w-8 h-8 border-2 rounded-full animate-spin mx-auto mb-2" style={{borderColor:'var(--accent-blue)', borderTopColor:'transparent'}} /><div className="text-xs" style={{color:'var(--text-muted)'}}>Loading...</div></div>
              </div>
            )}
          </div>
          <CapitalFlowPanel />
        </div>
        <BottomPanels />
        <ComplianceFooter />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <I18nProvider><ThemeProvider><DashboardContent /></ThemeProvider></I18nProvider>
  );
}
