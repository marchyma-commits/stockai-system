/* =============================================================
   StockAI v2.0 — New Dashboard UI (Design Spec 2026-05-07)
   =============================================================
   Architecture: Tab-based dashboard with:
     - Market bar / Watchlist (left) / K-line chart (center) / Capital flow (right)
     - Bottom strip: AI signals / News sentiment / Quick actions
     - Standalone pages: 個股分析 / 資金流向 / 策略 / 報告
   ============================================================= */

// ── Configuration ──
if (typeof API_BASE_URL === 'undefined') {
    var API_BASE_URL = '/api';
}

// ── State ──
let currentSymbol = '0700.HK';
let mainChart = null;
let capitalTrendChart = null;
let activeIndicators = { ma: true, rsi: true, macd: true, bollinger: false };
let klinePeriod = 'daily';
let capDays = 20;
let watchlistData = [];
let stockCache = {};

// ── Init ──
document.addEventListener('DOMContentLoaded', function () {
    console.log('🚀 StockAI v2.0 New UI Starting...');
    initDashboard();
});

async function initDashboard() {
    try {
        await Promise.all([
            loadMarketOverview(),
            loadWatchlist(),
            loadCapitalFlowMarket(),
            loadAISignals(),
            loadNewsSentiment(),
        ]);
        // Default: select first watchlist item
        if (watchlistData.length > 0) {
            selectWatchlistItem(watchlistData[0].symbol);
        } else {
            loadKlineChart('0700.HK');
        }
    } catch (e) {
        console.warn('⚠️ Init error, using fallback:', e.message);
        loadFallbackData();
    }

    // Auto-refresh every 60s
    setInterval(() => {
        loadMarketOverview();
        loadWatchlist();
        loadCapitalFlowMarket();
    }, 60000);
}

function loadFallbackData() {
    renderMarketOverview(getMockMarketOverview());
    renderWatchlist(getMockWatchlist());
    renderCapitalFlowMarket(getMockCapitalFlowMarket());
    renderAISignals(getMockAISignals());
    renderNewsSentiment(getMockNewsSentiment());
    loadKlineChart('0700.HK');
}

// ════════════════════════════════════════════════════════════════
// 1. TAB SWITCHING
// ════════════════════════════════════════════════════════════════

function switchTab(pageId) {
    // Update nav tabs
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.page === pageId);
    });
    // Show page
    document.querySelectorAll('.tab-page').forEach(page => {
        page.classList.toggle('active', page.id === 'page-' + pageId);
    });
    // Lazy load data for specific pages
    if (pageId === 'capital-flow') {
        loadCapitalFlowPage();
    }
    console.log('📂 Tab switched to:', pageId);
}

// ════════════════════════════════════════════════════════════════
// 2. MARKET OVERVIEW BAR
// ════════════════════════════════════════════════════════════════

async function loadMarketOverview() {
    try {
        const res = await fetch(`${API_BASE_URL}/market/overview`);
        const json = await res.json();
        if (json.success && json.data) {
            renderMarketOverview(json.data);
        } else {
            renderMarketOverview(getMockMarketOverview());
        }
    } catch (e) {
        console.warn('Market overview fetch failed:', e.message);
        renderMarketOverview(getMockMarketOverview());
    }
}

function renderMarketOverview(data) {
    const indices = data.indices || [];
    const map = {
        'HSI': { val: 'hsiValue', chg: 'hsiChange' },
        'TECH': { val: 'techValue', chg: 'techChange' },
        'A50': { val: 'a50Value', chg: 'a50Change' },
        'SHCOMP': { val: 'shcompValue', chg: 'shcompChange' },
    };
    indices.forEach(idx => {
        const ids = map[idx.name];
        if (!ids) return;
        const elVal = document.getElementById(ids.val);
        const elChg = document.getElementById(ids.chg);
        if (elVal) elVal.textContent = idx.value.toLocaleString();
        if (elChg) {
            const arrow = idx.direction === 'up' ? '▲' : '▼';
            const cls = idx.direction === 'up' ? 'up' : 'down';
            elChg.textContent = `${arrow} ${idx.change.toFixed(0)}`;
            elChg.className = `market-change ${cls}`;
        }
    });
    const timeEl = document.getElementById('marketTime');
    if (timeEl) timeEl.textContent = new Date().toLocaleTimeString('zh-HK');
}

function getMockMarketOverview() {
    return {
        indices: [
            { name: 'HSI', value: 22148, change: 128, direction: 'up' },
            { name: 'TECH', value: 5326, change: 86, direction: 'up' },
            { name: 'A50', value: 12886, change: -44, direction: 'down' },
            { name: 'SHCOMP', value: 3286, change: 18, direction: 'up' },
        ]
    };
}

// ════════════════════════════════════════════════════════════════
// 3. WATCHLIST
// ════════════════════════════════════════════════════════════════

async function loadWatchlist() {
    try {
        const res = await fetch(`${API_BASE_URL}/watchlist`);
        const json = await res.json();
        if (json.success && json.data) {
            watchlistData = json.data;
            renderWatchlist(json.data);
        } else {
            const mock = getMockWatchlist();
            watchlistData = mock;
            renderWatchlist(mock);
        }
    } catch (e) {
        console.warn('Watchlist fetch failed:', e.message);
        const mock = getMockWatchlist();
        watchlistData = mock;
        renderWatchlist(mock);
    }
}

function renderWatchlist(data) {
    const container = document.getElementById('watchlistContainer');
    if (!container) return;
    if (!data || data.length === 0) {
        container.innerHTML = '<div style="color:var(--text-dim);text-align:center;padding:20px;font-size:13px;">暫無自選股</div>';
        return;
    }
    container.innerHTML = data.map(item => {
        const dir = item.change >= 0 ? 'up' : 'down';
        const arrow = dir === 'up' ? '▲' : '▼';
        return `
            <div class="watchlist-item ${currentSymbol === item.symbol ? 'active' : ''}"
                 onclick="selectWatchlistItem('${item.symbol}')"
                 data-symbol="${item.symbol}">
                <div class="wl-left">
                    <span class="wl-arrow ${dir}">${arrow}</span>
                    <div>
                        <div class="wl-symbol">${item.symbol}</div>
                        <div class="wl-name">${item.name || ''}</div>
                    </div>
                </div>
                <div>
                    <div class="wl-price">$${formatPrice(item.price, item.symbol)}</div>
                    <div class="wl-change ${dir}">${item.change >= 0 ? '+' : ''}${item.change_percent?.toFixed(2)}%</div>
                </div>
            </div>
        `;
    }).join('');
}

function getMockWatchlist() {
    return [
        { symbol: '0700.HK', name: '騰訊', price: 522.0, change: 3.5, change_percent: 0.68 },
        { symbol: '9988.HK', name: '阿里', price: 86.5, change: 1.2, change_percent: 1.41 },
        { symbol: '0941.HK', name: '中移動', price: 71.0, change: -0.4, change_percent: -0.56 },
        { symbol: '1211.HK', name: '比亞迪', price: 282.0, change: 4.8, change_percent: 1.73 },
        { symbol: '3690.HK', name: '美團', price: 162.5, change: 2.1, change_percent: 1.31 },
    ];
}

function selectWatchlistItem(symbol) {
    currentSymbol = symbol;
    // Re-render watchlist with active state
    document.querySelectorAll('.watchlist-item').forEach(el => {
        el.classList.toggle('active', el.dataset.symbol === symbol);
    });
    // Load chart & capital flow for selected stock
    loadKlineChart(symbol);
    loadStockCapitalFlow(symbol);
    updateStockInfoBar(symbol);
}

// ════════════════════════════════════════════════════════════════
// 4. K-LINE CHART (ApexCharts Candlestick)
// ════════════════════════════════════════════════════════════════

async function loadKlineChart(symbol) {
    const chartEl = document.getElementById('mainChart');
    if (!chartEl) return;
    chartEl.innerHTML = '<div style="text-align:center;padding:120px 0;color:var(--text-dim);"><div class="loading-spinner"></div><br>載入K線圖...</div>';

    try {
        const days = klinePeriod === 'daily' ? 90 : klinePeriod === 'weekly' ? 365 : klinePeriod === 'monthly' ? 730 : 90;
        const res = await fetch(`${API_BASE_URL}/stock/${symbol}/history?days=${days}`);
        const json = await res.json();
        if (json.success && json.data && json.data.length > 0) {
            renderCandlestickChart(json.data, symbol);
        } else {
            renderCandlestickChart(getMockKlineData(symbol), symbol);
        }
    } catch (e) {
        console.warn('K-line fetch failed:', e.message);
        renderCandlestickChart(getMockKlineData(symbol), symbol);
    }
}

function renderCandlestickChart(klineData, symbol) {
    const chartEl = document.getElementById('mainChart');
    if (!chartEl) return;

    // Format data for ApexCharts
    const candleData = klineData.map(item => ({
        x: new Date(item.date || item.x).getTime(),
        y: [item.open, item.high, item.low, item.close].map(v => parseFloat(v))
    }));

    const options = {
        series: [{ name: 'K線', type: 'candlestick', data: candleData }],
        chart: {
            type: 'candlestick',
            height: 340,
            background: 'transparent',
            foreColor: '#99aabc',
            toolbar: { show: true, tools: { download: true, selection: true, zoom: true, pan: true, reset: true } },
            animations: { enabled: true, dynamicAnimation: { speed: 500 } },
        },
        plotOptions: {
            candlestick: {
                colors: { upward: '#10b981', downward: '#ef4444' },
                wick: { useFillColor: true }
            }
        },
        xaxis: {
            type: 'datetime',
            labels: { format: 'dd MMM', style: { colors: '#99aabc' }, datetimeUTC: false },
            axisBorder: { show: false },
            axisTicks: { show: false },
        },
        yaxis: {
            labels: {
                style: { colors: '#99aabc' },
                formatter: (v) => '$' + v.toFixed(1)
            }
        },
        grid: { borderColor: 'rgba(153,170,188,0.08)', strokeDashArray: 3 },
        tooltip: { theme: 'dark' },
        theme: { mode: 'dark' },
    };

    // Add MA lines if active
    if (activeIndicators.ma) {
        const closes = klineData.map(d => parseFloat(d.close || d.y?.[3]));
        const ma5 = calculateMA(closes, 5);
        const ma20 = calculateMA(closes, 20);
        const timestamps = klineData.map(d => new Date(d.date || d.x).getTime());

        options.series.push({
            name: 'MA5', type: 'line', data: ma5.map((v, i) => ({ x: timestamps[i], y: v })),
            color: '#fbbf24', stroke: { width: 1.5, dashArray: 0 }
        });
        options.series.push({
            name: 'MA20', type: 'line', data: ma20.map((v, i) => ({ x: timestamps[i], y: v })),
            color: '#60a5fa', stroke: { width: 1.5, dashArray: 0 }
        });
    }

    if (activeIndicators.bollinger) {
        const closes = klineData.map(d => parseFloat(d.close || d.y?.[3]));
        const bb = calculateBollinger(closes, 20, 2);
        const timestamps = klineData.map(d => new Date(d.date || d.x).getTime());
        options.series.push({
            name: 'BB上軌', type: 'line',
            data: bb.upper.map((v, i) => ({ x: timestamps[i], y: v })),
            color: '#10b981', stroke: { width: 1, dashArray: 3 }
        });
        options.series.push({
            name: 'BB中軌', type: 'line',
            data: bb.middle.map((v, i) => ({ x: timestamps[i], y: v })),
            color: '#3b82f6', stroke: { width: 1, dashArray: 3 }
        });
        options.series.push({
            name: 'BB下軌', type: 'line',
            data: bb.lower.map((v, i) => ({ x: timestamps[i], y: v })),
            color: '#ef4444', stroke: { width: 1, dashArray: 3 }
        });
    }

    // RSI sub-chart
    if (activeIndicators.rsi) {
        const closes = klineData.map(d => parseFloat(d.close || d.y?.[3]));
        const rsi = calculateRSI(closes, 14);
        const timestamps = klineData.map(d => new Date(d.date || d.x).getTime());
        options.series.push({
            name: 'RSI(14)', type: 'line',
            data: rsi.map((v, i) => ({ x: timestamps[i], y: v })),
            color: '#a78bfa', stroke: { width: 1.5 }
        });
    }

    if (activeIndicators.macd) {
        const closes = klineData.map(d => parseFloat(d.close || d.y?.[3]));
        const macd = calculateMACD(closes);
        const timestamps = klineData.map(d => new Date(d.date || d.x).getTime());
        const macdData = macd.macd.map((v, i) => ({ x: timestamps[i], y: v }));
        const signalData = macd.signal.map((v, i) => ({ x: timestamps[i], y: v }));
        const histData = macd.histogram.map((v, i) => ({ x: timestamps[i], y: v }));
        options.series.push({
            name: 'MACD', type: 'line', data: macdData, color: '#3b82f6', stroke: { width: 1 }
        });
        options.series.push({
            name: '信號', type: 'line', data: signalData, color: '#f59e0b', stroke: { width: 1 }
        });
        // Use bar type for histogram
        options.series.push({
            name: '柱', type: 'bar', data: histData, color: '#a78bfa'
        });
    }

    if (mainChart) mainChart.destroy();
    mainChart = new ApexCharts(chartEl, options);
    mainChart.render();
}

// ── Technical indicator calculations ──
function calculateMA(data, period) {
    const result = [];
    for (let i = 0; i < data.length; i++) {
        if (i < period - 1) { result.push(null); continue; }
        let sum = 0;
        for (let j = i - period + 1; j <= i; j++) sum += data[j];
        result.push(parseFloat((sum / period).toFixed(2)));
    }
    return result;
}

function calculateRSI(data, period = 14) {
    const result = [];
    let gains = 0, losses = 0;
    for (let i = 1; i <= period && i < data.length; i++) {
        const diff = data[i] - data[i - 1];
        if (diff >= 0) gains += diff;
        else losses -= diff;
    }
    let avgGain = gains / period;
    let avgLoss = losses / period;

    for (let i = 0; i < data.length; i++) {
        if (i <= period) { result.push(50); continue; }
        const diff = data[i] - data[i - 1];
        if (diff >= 0) { avgGain = (avgGain * (period - 1) + diff) / period; avgLoss = (avgLoss * (period - 1)) / period; }
        else { avgLoss = (avgLoss * (period - 1) - diff) / period; avgGain = (avgGain * (period - 1)) / period; }
        const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
        result.push(parseFloat((100 - 100 / (1 + rs)).toFixed(1)));
    }
    return result;
}

function calculateMACD(data, fast = 12, slow = 26, signal = 9) {
    const emaFast = calcEMA(data, fast);
    const emaSlow = calcEMA(data, slow);
    const macdLine = emaFast.map((v, i) => v - emaSlow[i]);
    const signalLine = calcEMA(macdLine, signal);
    const histogram = macdLine.map((v, i) => v - signalLine[i]);
    return { macd: macdLine, signal: signalLine, histogram };
}

function calcEMA(data, period) {
    const result = [];
    const k = 2 / (period + 1);
    let ema = data[0];
    for (let i = 0; i < data.length; i++) {
        if (i === 0) { ema = data[i]; }
        else { ema = data[i] * k + ema * (1 - k); }
        result.push(parseFloat(ema.toFixed(3)));
    }
    return result;
}

function calculateBollinger(data, period = 20, stdDev = 2) {
    const upper = [], middle = [], lower = [];
    for (let i = 0; i < data.length; i++) {
        if (i < period - 1) {
            upper.push(null); middle.push(null); lower.push(null);
            continue;
        }
        const ma = calculateMA(data, period)[i];
        const slice = data.slice(i - period + 1, i + 1);
        const variance = slice.reduce((sum, v) => sum + Math.pow(v - ma, 2), 0) / period;
        const std = Math.sqrt(variance);
        upper.push(parseFloat((ma + stdDev * std).toFixed(2)));
        middle.push(ma);
        lower.push(parseFloat((ma - stdDev * std).toFixed(2)));
    }
    return { upper, middle, lower };
}

function getMockKlineData(symbol) {
    const data = [];
    const now = new Date();
    let basePrice = { '0700.HK': 520, '9988.HK': 86, '0941.HK': 71, '1211.HK': 282, '3690.HK': 162 }[symbol] || 100;
    for (let i = 90; i >= 0; i--) {
        const date = new Date(now);
        date.setDate(now.getDate() - i);
        if (date.getDay() === 0 || date.getDay() === 6) continue;
        const change = (Math.random() - 0.5) * 8;
        const open = basePrice;
        const close = basePrice + change;
        const high = Math.max(open, close) + Math.random() * 3;
        const low = Math.min(open, close) - Math.random() * 3;
        data.push({ date: date.toISOString().split('T')[0], open: +open.toFixed(2), high: +high.toFixed(2), low: +low.toFixed(2), close: +close.toFixed(2), volume: Math.floor(Math.random() * 30 + 5) * 1000000 });
        basePrice = close;
    }
    return data;
}

// ── Period & Indicator toggles ──
function changeKlinePeriod(period) {
    klinePeriod = period;
    document.querySelectorAll('#klineTabs .chart-tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`#klineTabs .chart-tab[onclick*="${period}"]`)?.classList.add('active');
    loadKlineChart(currentSymbol);
}

function toggleIndicator(name) {
    activeIndicators[name] = !activeIndicators[name];
    const tag = document.querySelector(`.indicator-tag[data-indicator="${name}"]`);
    if (tag) tag.classList.toggle('active');
    loadKlineChart(currentSymbol);
}

// ════════════════════════════════════════════════════════════════
// 5. STOCK INFO BAR
// ════════════════════════════════════════════════════════════════

async function updateStockInfoBar(symbol) {
    try {
        const res = await fetch(`${API_BASE_URL}/stock/${symbol}`);
        const json = await res.json();
        if (json.success && json.data) {
            renderStockInfoBar(json.data);
        }
    } catch (e) {
        // Use watchlist data
        const wl = watchlistData.find(w => w.symbol === symbol);
        if (wl) {
            const el = document.getElementById('mainPrice');
            if (el) el.textContent = '$' + formatPrice(wl.price, symbol);
            const chg = document.getElementById('mainChange');
            if (chg) { chg.textContent = (wl.change >= 0 ? '+' : '') + wl.change_percent?.toFixed(2) + '%'; chg.style.color = wl.change >= 0 ? '#10b981' : '#ef4444'; }
        }
    }
}

function renderStockInfoBar(data) {
    const p = document.getElementById('mainPrice');
    if (p) p.textContent = '$' + formatPrice(data.price, data.symbol);
    const chg = document.getElementById('mainChange');
    if (chg) { chg.textContent = (data.change >= 0 ? '+' : '') + data.change.toFixed(2) + ' (' + (data.change_percent || 0).toFixed(2) + '%)'; chg.style.color = data.change >= 0 ? '#10b981' : '#ef4444'; }
    const open = document.getElementById('mainOpen');
    if (open) open.textContent = '$' + formatPrice(data.open, data.symbol);
    const range = document.getElementById('mainRange');
    if (range) range.textContent = '$' + formatPrice(data.low_52w || data.low, data.symbol) + ' - $' + formatPrice(data.high_52w || data.high, data.symbol);
    const vol = document.getElementById('mainVolume');
    if (vol) vol.textContent = typeof data.volume === 'number' ? formatVolume(data.volume) : (data.volume || '--');
}

// ════════════════════════════════════════════════════════════════
// 6. CAPITAL FLOW (Right Panel)
// ════════════════════════════════════════════════════════════════

async function loadCapitalFlowMarket() {
    try {
        const res = await fetch(`${API_BASE_URL}/capital-flow/market`);
        const json = await res.json();
        if (json.success && json.data) {
            renderCapitalFlowMarket(json.data);
        } else {
            renderCapitalFlowMarket(getMockCapitalFlowMarket());
        }
    } catch (e) {
        renderCapitalFlowMarket(getMockCapitalFlowMarket());
    }
}

function renderCapitalFlowMarket(data) {
    // Market total flow
    const container = document.getElementById('marketCapFlow');
    if (container && data.total) {
        container.innerHTML = `
            <div class="cf-row"><span class="cf-label">主力</span><span class="cf-value positive">+${data.total.main_force}億</span></div>
            <div class="cf-row"><span class="cf-label">散戶</span><span class="cf-value negative">${data.total.retail >= 0 ? '+' : ''}${data.total.retail}億</span></div>
        `;
    }

    // Sector flow
    const sectorEl = document.getElementById('sectorFlow');
    if (sectorEl && data.sectors) {
        sectorEl.innerHTML = data.sectors.map(s => `
            <div class="cf-sector">
                <span class="cf-sector-name">${s.name}</span>
                <span class="cf-value ${s.flow >= 0 ? 'positive' : 'negative'}">${s.flow >= 0 ? '+' : ''}${s.flow}億</span>
            </div>
        `).join('');
    }
}

function getMockCapitalFlowMarket() {
    return {
        total: { main_force: 128, retail: -32 },
        sectors: [
            { name: '科技', flow: 42 }, { name: '金融', flow: 18 },
            { name: '醫藥', flow: -5 }, { name: '消費', flow: -8 }, { name: '能源', flow: 3 }
        ]
    };
}

async function loadStockCapitalFlow(symbol) {
    try {
        const res = await fetch(`${API_BASE_URL}/capital-flow/stock/${symbol}`);
        const json = await res.json();
        if (json.success && json.data) {
            renderStockCapitalFlow(json.data);
        } else {
            renderStockCapitalFlow(getMockStockCapitalFlow(symbol));
        }
    } catch (e) {
        renderStockCapitalFlow(getMockStockCapitalFlow(symbol));
    }
}

function renderStockCapitalFlow(data) {
    const container = document.getElementById('stockCapFlow');
    if (!container || !data.details) return;
    container.innerHTML = `
        <div style="font-size:12px;color:var(--text-dim);margin-bottom:6px;">${data.symbol} ${data.name || ''}</div>
        ${Object.entries(data.details).map(([label, val]) => `
            <div class="cf-detail-item">
                <span class="cf-label">${label}</span>
                <span class="cf-value ${val >= 0 ? 'positive' : 'negative'}">${val >= 0 ? '+' : ''}${val}億</span>
            </div>
        `).join('')}
    `;
}

function getMockStockCapitalFlow(symbol) {
    return {
        symbol: symbol,
        name: symbol,
        details: { '超大單': 3.2, '大單': 1.8, '中單': -0.6, '小單': -1.2 }
    };
}

// ════════════════════════════════════════════════════════════════
// 7. AI SIGNALS (Bottom Left)
// ════════════════════════════════════════════════════════════════

async function loadAISignals() {
    try {
        const res = await fetch(`${API_BASE_URL}/ai/signals`);
        const json = await res.json();
        if (json.success && json.data) {
            renderAISignals(json.data);
        } else {
            renderAISignals(getMockAISignals());
        }
    } catch (e) {
        renderAISignals(getMockAISignals());
    }
}

function renderAISignals(data) {
    const container = document.getElementById('aiSignalsContainer');
    if (!container) return;
    if (!data || data.length === 0) {
        container.innerHTML = '<div style="color:var(--text-dim);font-size:12px;">暫無信號</div>';
        return;
    }
    container.innerHTML = data.map(s => {
        const signalClass = s.signal === '買入' ? 'buy' : s.signal === '賣出' ? 'sell' : 'hold';
        return `
            <div class="ai-signal-item" onclick="selectWatchlistItem('${s.symbol}')" style="cursor:pointer;">
                <div><strong>${s.symbol}</strong> <span style="color:var(--text-dim);font-size:12px;">${s.reason || ''}</span></div>
                <div style="display:flex;align-items:center;gap:8px;">
                    <span class="signal-badge ${signalClass}">${s.signal}</span>
                    <span class="signal-conf">${s.confidence || ''}</span>
                </div>
            </div>
        `;
    }).join('');
}

function getMockAISignals() {
    return [
        { symbol: '0700.HK', signal: '買入', confidence: '85%', reason: 'AI利好' },
        { symbol: '0941.HK', signal: '賣出', confidence: '72%', reason: '資金流出' },
        { symbol: '9988.HK', signal: '買入', confidence: '78%', reason: '業績改善' },
        { symbol: '1211.HK', signal: '持有', confidence: '65%', reason: '觀望' },
    ];
}

// ════════════════════════════════════════════════════════════════
// 8. NEWS SENTIMENT (Bottom Middle)
// ════════════════════════════════════════════════════════════════

async function loadNewsSentiment() {
    try {
        const res = await fetch(`${API_BASE_URL}/news/sentiment-summary`);
        const json = await res.json();
        if (json.success && json.data) {
            renderNewsSentiment(json.data);
        } else {
            renderNewsSentiment(getMockNewsSentiment());
        }
    } catch (e) {
        renderNewsSentiment(getMockNewsSentiment());
    }
}

function renderNewsSentiment(data) {
    const container = document.getElementById('newsSentimentContainer');
    if (!container) return;
    if (!data || data.length === 0) {
        container.innerHTML = '<div style="color:var(--text-dim);font-size:12px;">暫無新聞</div>';
        return;
    }
    container.innerHTML = data.map(n => `
        <div class="news-item-sm">
            <span class="news-dot ${n.sentiment === 'positive' ? 'positive' : n.sentiment === 'negative' ? 'negative' : 'neutral'}"></span>
            <span class="news-sm-title"><strong>${n.symbol}</strong> ${n.title}</span>
        </div>
    `).join('');
}

function getMockNewsSentiment() {
    return [
        { symbol: '0700.HK', title: '騰訊AI業務利好', sentiment: 'positive' },
        { symbol: '3690.HK', title: '美團外賣業務受壓', sentiment: 'negative' },
        { symbol: '9988.HK', title: '阿里雲收入超預期', sentiment: 'positive' },
    ];
}

// ════════════════════════════════════════════════════════════════
// 9. CAPITAL FLOW PAGE (Full Page)
// ════════════════════════════════════════════════════════════════

async function loadCapitalFlowPage() {
    await Promise.all([
        loadCapitalTrendChart(capDays),
        loadTopStockFlow(),
        loadSouthNorthFlow(),
    ]);
}

function changeCapPeriod(days) {
    capDays = days;
    document.querySelectorAll('#page-capital-flow .chart-tab').forEach(t => t.classList.remove('active'));
    // Re-render active state
    const tabs = document.querySelectorAll('#page-capital-flow .chart-tab');
    tabs.forEach(t => {
        if (t.textContent.includes(days + '日') || (days === 60 && t.textContent.includes('年初'))) {
            t.classList.add('active');
        }
    });
    loadCapitalTrendChart(days);
}

async function loadCapitalTrendChart(days) {
    try {
        const res = await fetch(`${API_BASE_URL}/capital-flow/history?days=${days}`);
        const json = await res.json();
        if (json.success && json.data) {
            renderCapitalTrendChart(json.data);
        } else {
            renderCapitalTrendChart(getMockCapitalHistory(days));
        }
    } catch (e) {
        renderCapitalTrendChart(getMockCapitalHistory(days));
    }
}

function renderCapitalTrendChart(data) {
    const chartEl = document.getElementById('capitalTrendChart');
    if (!chartEl) return;

    if (capitalTrendChart) capitalTrendChart.destroy();

    const options = {
        series: [
            { name: '主力資金', type: 'bar', data: data.map(d => ({ x: d.date, y: d.main_force })) },
            { name: '散戶資金', type: 'bar', data: data.map(d => ({ x: d.date, y: d.retail })) },
        ],
        chart: {
            height: 250,
            type: 'bar',
            background: 'transparent',
            foreColor: '#99aabc',
            toolbar: { show: false },
            stacked: false,
        },
        colors: ['#10b981', '#ef4444'],
        plotOptions: {
            bar: { horizontal: false, columnWidth: '55%' },
        },
        xaxis: {
            type: 'datetime',
            labels: { format: 'dd MMM', style: { colors: '#99aabc' } },
            axisBorder: { show: false },
        },
        yaxis: {
            labels: {
                style: { colors: '#99aabc' },
                formatter: (v) => v + '億'
            }
        },
        grid: { borderColor: 'rgba(153,170,188,0.06)' },
        tooltip: { theme: 'dark', y: { formatter: (v) => (v >= 0 ? '+' : '') + v + '億' } },
        legend: { labels: { colors: '#99aabc' } },
    };

    capitalTrendChart = new ApexCharts(chartEl, options);
    capitalTrendChart.render();
}

function getMockCapitalHistory(days) {
    const data = [];
    const now = new Date();
    for (let i = days; i >= 0; i--) {
        const date = new Date(now);
        date.setDate(now.getDate() - i);
        if (date.getDay() === 0 || date.getDay() === 6) continue;
        data.push({
            date: date.toISOString().split('T')[0],
            main_force: Math.round(Math.random() * 200 - 30),
            retail: Math.round(Math.random() * 100 - 50),
        });
    }
    return data;
}

async function loadTopStockFlow() {
    try {
        const res = await fetch(`${API_BASE_URL}/capital-flow/top-stocks?limit=5`);
        const json = await res.json();
        if (json.success && json.data) {
            renderTopStockFlow(json.data);
        } else {
            renderTopStockFlow(getMockTopStockFlow());
        }
    } catch (e) {
        renderTopStockFlow(getMockTopStockFlow());
    }
}

function renderTopStockFlow(data) {
    const container = document.getElementById('topStockFlow');
    if (!container) return;
    container.innerHTML = data.map(s => `
        <div class="top-stock-item">
            <div><strong>${s.symbol}</strong><span style="color:var(--text-dim);font-size:12px;margin-left:6px;">${s.name || ''}</span></div>
            <div>
                <span class="cf-value ${s.net_flow >= 0 ? 'positive' : 'negative'}">${s.net_flow >= 0 ? '+' : ''}${s.net_flow}億</span>
                <span style="color:var(--text-dim);font-size:12px;margin-left:8px;">${s.change_pct?.toFixed(2) || 0}%</span>
            </div>
        </div>
    `).join('');
}

function getMockTopStockFlow() {
    return [
        { symbol: '0700.HK', name: '騰訊', net_flow: 8.2, change_pct: 0.68 },
        { symbol: '9988.HK', name: '阿里', net_flow: 5.6, change_pct: 1.41 },
        { symbol: '3690.HK', name: '美團', net_flow: 4.1, change_pct: 1.31 },
        { symbol: '1211.HK', name: '比亞迪', net_flow: 3.8, change_pct: 1.73 },
        { symbol: '2318.HK', name: '中國平安', net_flow: 2.5, change_pct: 0.42 },
    ];
}

async function loadSouthNorthFlow() {
    try {
        const res = await fetch(`${API_BASE_URL}/capital-flow/south-north`);
        const json = await res.json();
        if (json.success && json.data) {
            renderSouthNorthFlow(json.data);
        } else {
            renderSouthNorthFlow(getMockSouthNorthFlow());
        }
    } catch (e) {
        renderSouthNorthFlow(getMockSouthNorthFlow());
    }
}

function renderSouthNorthFlow(data) {
    const container = document.getElementById('southNorthFlow');
    if (!container) return;
    const items = [
        { label: '滬股通', key: '滬股通' },
        { label: '深股通', key: '深股通' },
        { label: '港股通(滬)', key: '港股通(滬)' },
        { label: '港股通(深)', key: '港股通(深)' },
    ];
    container.innerHTML = `
        <div class="south-north-grid">
            ${items.map(item => `
                <div class="sn-item">
                    <div class="sn-label">${item.label}</div>
                    <div class="sn-value ${(data[item.key] || 0) >= 0 ? 'positive' : 'negative'}">
                        ${(data[item.key] || 0) >= 0 ? '+' : ''}${data[item.key] || 0}億
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

function getMockSouthNorthFlow() {
    return { '滬股通': 18.5, '深股通': 12.3, '港股通(滬)': 25.6, '港股通(深)': 18.2 };
}

// ════════════════════════════════════════════════════════════════
// 10. ANALYSIS PAGE
// ════════════════════════════════════════════════════════════════

async function analyzeSingleStock() {
    const symbol = document.getElementById('analysisStockInput')?.value.trim() || '0700.HK';
    const container = document.getElementById('analysisResult');
    if (!container) return;

    container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-dim);"><div class="loading-spinner"></div><br>分析中...</div>';

    try {
        const [stockRes, historyRes, predRes] = await Promise.all([
            fetch(`${API_BASE_URL}/stock/${symbol}`).then(r => r.json()).catch(() => ({ success: false })),
            fetch(`${API_BASE_URL}/stock/${symbol}/history?days=90`).then(r => r.json()).catch(() => ({ success: false })),
            fetch(`${API_BASE_URL}/predict/${symbol}`).then(r => r.json()).catch(() => ({ success: false })),
        ]);

        const stock = stockRes.success ? stockRes.data : null;
        const history = historyRes.success ? historyRes.data : getMockKlineData(symbol);
        const pred = predRes.success ? predRes.data : null;

        // Build analysis result
        let html = '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;">';

        // Stock info card
        if (stock) {
            html += `
                <div class="cf-full-card" style="grid-column:1/-1;">
                    <div style="display:flex;align-items:center;gap:20px;flex-wrap:wrap;">
                        <div><span style="font-size:24px;font-weight:700;">${stock.symbol}</span><span style="color:var(--text-dim);margin-left:10px;">${stock.name || ''}</span></div>
                        <div style="flex:1;"></div>
                        <div style="text-align:right;">
                            <div style="font-size:32px;font-weight:700;">$${formatPrice(stock.price, symbol)}</div>
                            <div style="font-size:16px;font-weight:600;color:${(stock.change || 0) >= 0 ? '#10b981' : '#ef4444'}">
                                ${(stock.change || 0) >= 0 ? '+' : ''}${(stock.change || 0).toFixed(2)} (${(stock.change_percent || 0).toFixed(2)}%)
                            </div>
                        </div>
                    </div>
                </div>
            `;

            // Metrics grid
            const metrics = [
                { label: '開盤', value: '$' + formatPrice(stock.open, symbol) },
                { label: '市值', value: formatMarketCap(stock.market_cap) },
                { label: '成交量', value: typeof stock.volume === 'number' ? formatVolume(stock.volume) : (stock.volume || '--') },
                { label: 'PE', value: stock.pe_ratio ? stock.pe_ratio.toFixed(2) : '--' },
            ];
            metrics.forEach(m => {
                html += `<div class="cf-full-card" style="text-align:center;"><div style="color:var(--text-dim);font-size:12px;">${m.label}</div><div style="font-size:24px;font-weight:700;margin-top:4px;">${m.value}</div></div>`;
            });
        }

        // Prediction card
        if (pred) {
            const predColor = pred.prediction === 'bullish' ? '#10b981' : pred.prediction === 'bearish' ? '#ef4444' : '#fbbf24';
            html += `
                <div class="cf-full-card" style="grid-column:1/-1;margin-top:8px;">
                    <div class="cf-page-title"><i class="bi bi-robot"></i> AI 預測</div>
                    <div style="display:flex;gap:20px;align-items:center;flex-wrap:wrap;">
                        <div><span style="color:var(--text-dim);font-size:13px;">方向</span><div style="font-size:20px;font-weight:700;color:${predColor};">${pred.prediction === 'bullish' ? '📈 看漲' : pred.prediction === 'bearish' ? '📉 看跌' : '➡️ 中性'}</div></div>
                        <div><span style="color:var(--text-dim);font-size:13px;">信心度</span><div style="font-size:20px;font-weight:700;">${(pred.confidence * 100).toFixed(0)}%</div></div>
                        <div><span style="color:var(--text-dim);font-size:13px;">目標價</span><div style="font-size:20px;font-weight:700;">$${formatPrice(pred.target_price, symbol)}</div></div>
                        <div><span style="color:var(--text-dim);font-size:13px;">現價</span><div style="font-size:20px;font-weight:700;">$${formatPrice(pred.current_price, symbol)}</div></div>
                    </div>
                </div>
            `;
        }

        // Mini chart
        html += `
            <div class="cf-full-card" style="grid-column:1/-1;">
                <div class="cf-page-title"><i class="bi bi-graph-up"></i> 價格走勢</div>
                <div id="analysisMiniChart" style="height:200px;"></div>
            </div>
        `;

        html += '</div>';
        container.innerHTML = html;

        // Render mini chart
        const miniData = history.map(d => ({ x: new Date(d.date || d.x).getTime(), y: [d.open, d.high, d.low, d.close] }));
        const miniOptions = {
            series: [{ name: 'K線', type: 'candlestick', data: miniData }],
            chart: { type: 'candlestick', height: 200, background: 'transparent', foreColor: '#99aabc', toolbar: { show: false } },
            plotOptions: { candlestick: { colors: { upward: '#10b981', downward: '#ef4444' } } },
            xaxis: { type: 'datetime', labels: { format: 'dd MMM', style: { colors: '#99aabc' } } },
            yaxis: { labels: { style: { colors: '#99aabc' }, formatter: (v) => '$' + v.toFixed(1) } },
            grid: { borderColor: 'rgba(153,170,188,0.06)' },
            tooltip: { theme: 'dark' },
        };
        const miniChart = new ApexCharts(document.getElementById('analysisMiniChart'), miniOptions);
        miniChart.render();

    } catch (e) {
        container.innerHTML = `<div style="text-align:center;padding:40px;color:#ef4444;">分析失敗: ${e.message}</div>`;
    }
}

// ════════════════════════════════════════════════════════════════
// 11. STRATEGY PAGE
// ════════════════════════════════════════════════════════════════

async function loadStrategy() {
    const symbol = document.getElementById('strategyStockInput')?.value.trim() || '0700.HK';
    const container = document.getElementById('strategyResult');
    if (!container) return;

    container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-dim);"><div class="loading-spinner"></div><br>生成策略中...</div>';

    try {
        const res = await fetch(`${API_BASE_URL}/ai/strategy/${symbol}`);
        const json = await res.json();
        if (json.success && json.data) {
            renderStrategy(json.data, container);
        } else {
            renderStrategy(getMockStrategy(symbol), container);
        }
    } catch (e) {
        renderStrategy(getMockStrategy(symbol), container);
    }
}

function renderStrategy(strategy, container) {
    const actionColor = strategy.action === 'buy' ? '#10b981' : strategy.action === 'sell' ? '#ef4444' : '#fbbf24';
    const actionText = strategy.action === 'buy' ? '📈 買入' : strategy.action === 'sell' ? '📉 賣出' : '➡️ 持有';
    const scoreColor = strategy.overall_score >= 70 ? '#10b981' : strategy.overall_score >= 50 ? '#fbbf24' : '#ef4444';

    container.innerHTML = `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
            <!-- Action card -->
            <div class="cf-full-card" style="text-align:center;">
                <div style="font-size:14px;color:var(--text-dim);margin-bottom:8px;">操作建議</div>
                <div style="font-size:36px;font-weight:700;color:${actionColor};">${actionText}</div>
                <div style="margin-top:10px;">
                    <span style="font-size:14px;">信心度: </span>
                    <span style="font-size:18px;font-weight:700;color:${scoreColor};">${strategy.confidence || '中'}</span>
                </div>
            </div>

            <!-- Score card -->
            <div class="cf-full-card" style="text-align:center;">
                <div style="font-size:14px;color:var(--text-dim);margin-bottom:8px;">綜合評分</div>
                <div style="font-size:48px;font-weight:800;color:${scoreColor};">${strategy.overall_score}</div>
                <div style="font-size:14px;color:var(--text-dim);">/100</div>
            </div>

            <!-- Entry -->
            <div class="cf-full-card" style="border:1px solid rgba(16,185,129,0.2);">
                <div style="font-size:14px;color:#10b981;margin-bottom:10px;"><i class="bi bi-arrow-down-circle"></i> 買入計劃</div>
                <div class="cf-row"><span class="cf-label">買入價</span><span class="cf-value">$${strategy.entry?.buy_price || '--'}</span></div>
                <div class="cf-row"><span class="cf-label">止損價</span><span class="cf-value" style="color:#ef4444;">$${strategy.entry?.stop_loss || '--'}</span></div>
                <div class="cf-row"><span class="cf-label">建議倉位</span><span class="cf-value">${strategy.recommended_position || '--'}</span></div>
            </div>

            <!-- Exit -->
            <div class="cf-full-card" style="border:1px solid rgba(239,68,68,0.2);">
                <div style="font-size:14px;color:#ef4444;margin-bottom:10px;"><i class="bi bi-arrow-up-circle"></i> 賣出計劃</div>
                <div class="cf-row"><span class="cf-label">目標一</span><span class="cf-value">$${strategy.exit?.target_1 || '--'}</span></div>
                <div class="cf-row"><span class="cf-label">目標二</span><span class="cf-value">$${strategy.exit?.target_2 || '--'}</span></div>
                <div class="cf-row"><span class="cf-label">風險回報比</span><span class="cf-value">${strategy.risk_reward || '--'}:1</span></div>
            </div>

            <!-- Signals -->
            <div class="cf-full-card" style="grid-column:1/-1;">
                <div style="font-size:14px;color:var(--text-dim);margin-bottom:10px;">技術信號</div>
                <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;">
                    ${renderSignalCard('趨勢', strategy.signals?.trend)}
                    ${renderSignalCard('RSI', strategy.signals?.rsi)}
                    ${renderSignalCard('MACD', strategy.signals?.macd)}
                    ${renderSignalCard('KDJ', strategy.signals?.kdj)}
                    ${renderSignalCard('布林帶', strategy.signals?.bollinger)}
                </div>
            </div>
        </div>
    `;
}

function renderSignalCard(label, value) {
    let color = '#99aabc';
    let text = value || '--';
    if (typeof value === 'string') {
        if (value.includes('bullish') || value.includes('golden')) color = '#10b981';
        else if (value.includes('bearish') || value.includes('death')) color = '#ef4444';
    }
    if (typeof value === 'number') {
        text = value.toFixed(0);
        color = value > 60 ? '#10b981' : value < 40 ? '#ef4444' : '#fbbf24';
    }
    return `
        <div style="background:rgba(0,0,0,0.2);border-radius:10px;padding:12px;text-align:center;">
            <div style="font-size:11px;color:var(--text-dim);margin-bottom:4px;">${label}</div>
            <div style="font-size:16px;font-weight:700;color:${color};">${text}</div>
        </div>
    `;
}

function getMockStrategy(symbol) {
    return {
        action: 'buy', overall_score: 78, confidence: '高',
        recommended_position: '30%', risk_reward: 3.2,
        entry: { buy_price: 515.0, stop_loss: 495.0 },
        exit: { target_1: 545.0, target_2: 570.0 },
        signals: { trend: 'bullish', rsi: 58, macd: 'golden_cross', kdj: 62, bollinger: 'middle' }
    };
}

// ════════════════════════════════════════════════════════════════
// 12. REPORT PAGE
// ════════════════════════════════════════════════════════════════

async function generateReport() {
    const symbol = document.getElementById('reportStockInput')?.value.trim() || '0700.HK';
    const container = document.getElementById('reportResult');
    if (!container) return;

    container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-dim);"><div class="loading-spinner"></div><br>生成報告中...</div>';

    try {
        const [stockRes, predRes] = await Promise.all([
            fetch(`${API_BASE_URL}/stock/${symbol}`).then(r => r.json()).catch(() => ({ success: false })),
            fetch(`${API_BASE_URL}/predict/${symbol}`).then(r => r.json()).catch(() => ({ success: false })),
        ]);

        const stock = stockRes.success ? stockRes.data : null;
        const pred = predRes.success ? predRes.data : null;

        const now = new Date();
        const reportDate = now.toLocaleDateString('zh-HK', { year: 'numeric', month: 'long', day: 'numeric' });
        const reportTime = now.toLocaleTimeString('zh-HK');

        let html = `
            <div style="max-width:800px;margin:0 auto;">
                <div style="text-align:center;margin-bottom:24px;">
                    <div style="font-size:24px;font-weight:700;">📊 StockAI 智能分析報告</div>
                    <div style="color:var(--text-dim);font-size:13px;">${reportDate} ${reportTime} | ${symbol}</div>
                    ${stock ? `<div style="font-size:14px;color:#99aabc;margin-top:4px;">${stock.name || ''}</div>` : ''}
                </div>
                <div style="height:1px;background:rgba(153,170,188,0.1);margin-bottom:20px;"></div>
        `;

        if (stock) {
            const changeClass = (stock.change || 0) >= 0 ? 'positive' : 'negative';
            html += `
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px;">
                    <div class="cf-full-card">
                        <div style="font-size:13px;color:var(--text-dim);margin-bottom:4px;">現價</div>
                        <div style="font-size:28px;font-weight:700;">$${formatPrice(stock.price, symbol)}</div>
                        <div style="font-size:14px;font-weight:600;color:${changeClass === 'positive' ? '#10b981' : '#ef4444'}">
                            ${(stock.change || 0) >= 0 ? '+' : ''}${(stock.change || 0).toFixed(2)} (${(stock.change_percent || 0).toFixed(2)}%)
                        </div>
                    </div>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                        <div class="cf-full-card" style="text-align:center;"><div style="font-size:11px;color:var(--text-dim);">開盤</div><div style="font-size:18px;font-weight:700;">$${formatPrice(stock.open, symbol)}</div></div>
                        <div class="cf-full-card" style="text-align:center;"><div style="font-size:11px;color:var(--text-dim);">市值</div><div style="font-size:18px;font-weight:700;">${formatMarketCap(stock.market_cap)}</div></div>
                        <div class="cf-full-card" style="text-align:center;"><div style="font-size:11px;color:var(--text-dim);">PE</div><div style="font-size:18px;font-weight:700;">${stock.pe_ratio?.toFixed(2) || '--'}</div></div>
                        <div class="cf-full-card" style="text-align:center;"><div style="font-size:11px;color:var(--text-dim);">成交量</div><div style="font-size:18px;font-weight:700;">${typeof stock.volume === 'number' ? formatVolume(stock.volume) : (stock.volume || '--')}</div></div>
                    </div>
                </div>
            `;
        }

        if (pred) {
            const predDir = pred.prediction === 'bullish' ? '📈 看漲' : pred.prediction === 'bearish' ? '📉 看跌' : '➡️ 中性';
            const gainPct = pred.target_price && pred.current_price
                ? (((pred.target_price - pred.current_price) / pred.current_price) * 100).toFixed(1)
                : '--';
            html += `
                <div class="cf-full-card" style="margin-bottom:20px;">
                    <div style="font-size:14px;font-weight:600;margin-bottom:10px;">🤖 AI 預測總結</div>
                    <div style="display:flex;gap:24px;flex-wrap:wrap;">
                        <div><span style="color:var(--text-dim);">方向:</span> <strong>${predDir}</strong></div>
                        <div><span style="color:var(--text-dim);">信心度:</span> <strong>${(pred.confidence * 100).toFixed(0)}%</strong></div>
                        <div><span style="color:var(--text-dim);">目標價:</span> <strong>$${formatPrice(pred.target_price, symbol)}</strong></div>
                        <div><span style="color:var(--text-dim);">潛在升幅:</span> <strong style="color:#10b981;">+${gainPct}%</strong></div>
                    </div>
                </div>
            `;
        }

        // Disclaimer
        html += `
            <div style="background:rgba(239,68,68,0.05);border:1px solid rgba(239,68,68,0.1);border-radius:12px;padding:16px;margin-top:20px;">
                <div style="font-size:12px;font-weight:600;color:#ef4444;margin-bottom:6px;">⚠️ 風險免責聲明</div>
                <div style="font-size:11px;color:var(--text-dim);line-height:1.6;">
                    本報告由 StockAI 系統自動生成，僅供參考，不構成任何投資建議。<br>
                    股市有風險，投資需謹慎。過往表現不代表未來回報。<br>
                    數據來源：模擬數據 (Mock)，請以實際市場數據為準。
                </div>
            </div>
            <div style="text-align:center;margin-top:16px;">
                <button onclick="window.print()" class="quick-action-btn" style="display:inline-block;width:auto;padding:8px 24px;">
                    <i class="bi bi-printer"></i> 打印報告
                </button>
            </div>
        `;

        html += '</div>';
        container.innerHTML = html;

    } catch (e) {
        container.innerHTML = `<div style="text-align:center;padding:40px;color:#ef4444;">生成報告失敗: ${e.message}</div>`;
    }
}

// ════════════════════════════════════════════════════════════════
// 13. QUICK ACTIONS
// ════════════════════════════════════════════════════════════════

function quickAnalyzeStock() {
    const symbol = prompt('輸入股票代碼 (e.g. 0700.HK, AAPL):', '0700.HK');
    if (symbol && symbol.trim()) {
        currentSymbol = symbol.trim().toUpperCase();
        selectWatchlistItem(currentSymbol);
        switchTab('dashboard');
    }
}

function generateDailyReport() {
    switchTab('report');
    setTimeout(() => generateReport(), 300);
}

// ════════════════════════════════════════════════════════════════
// 14. UTILITY FUNCTIONS
// ════════════════════════════════════════════════════════════════

function formatPrice(price, symbol) {
    if (!price && price !== 0) return '--';
    if (price < 0.25) return price.toFixed(3);
    if (price < 2) return price.toFixed(2);
    if (price < 10) return price.toFixed(2);
    return price.toFixed(2);
}

function formatVolume(volume) {
    if (!volume && volume !== 0) return '--';
    if (volume >= 1e9) return (volume / 1e9).toFixed(2) + 'B';
    if (volume >= 1e6) return (volume / 1e6).toFixed(2) + 'M';
    if (volume >= 1e3) return (volume / 1e3).toFixed(2) + 'K';
    return volume.toString();
}

function formatMarketCap(value) {
    if (!value && value !== 0) return '--';
    const num = parseFloat(value);
    if (isNaN(num)) return '--';
    if (num >= 1e12) return '$' + (num / 1e12).toFixed(2) + 'T';
    if (num >= 1e9) return '$' + (num / 1e9).toFixed(2) + 'B';
    if (num >= 1e6) return '$' + (num / 1e6).toFixed(2) + 'M';
    return '$' + num.toFixed(0);
}

// ════════════════════════════════════════════════════════════════
// 15. SEARCH AUTOCOMPLETE SYSTEM
// ════════════════════════════════════════════════════════════════

// Active autocomplete state
let autocompleteState = {
    activeInputId: null,
    selectedIndex: -1,
    results: [],
    dropdownEl: null,
};

/**
 * Set up search autocomplete for an input element.
 * @param {string} inputId - ID of the input element
 * @param {object} options
 * @param {function} options.onSelect - Callback when user selects an item (receives symbol)
 * @param {function} options.onSearch - Callback when user presses Enter without selection
 * @param {string} options.placeholder - Placeholder text
 */
function setupSearchAutocomplete(inputId, options = {}) {
    const input = document.getElementById(inputId);
    if (!input) return;

    // Create dropdown container
    const wrapper = document.createElement('div');
    wrapper.style.position = 'relative';
    wrapper.style.flex = '1';
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);

    const dropdown = document.createElement('div');
    dropdown.className = 'search-autocomplete-dropdown';
    dropdown.style.cssText = `
        position: absolute;
        top: 100%;
        left: 0;
        right: 0;
        background: #1a2332;
        border: 1px solid rgba(59, 130, 246, 0.2);
        border-radius: 0 0 12px 12px;
        max-height: 320px;
        overflow-y: auto;
        z-index: 9999;
        display: none;
        box-shadow: 0 8px 24px rgba(0,0,0,0.4);
    `;
    wrapper.appendChild(dropdown);

    let debounceTimer = null;
    let lastQuery = '';

    // Input handler with debounce
    input.addEventListener('input', function () {
        const q = this.value.trim();
        if (q === lastQuery) return;
        lastQuery = q;

        clearTimeout(debounceTimer);
        autocompleteState.selectedIndex = -1;

        if (q.length < 1) {
            hideDropdown(inputId);
            return;
        }

        debounceTimer = setTimeout(() => performSearch(inputId, q, dropdown, options), 250);
    });

    // Focus handler
    input.addEventListener('focus', function () {
        if (this.value.trim().length >= 1 && autocompleteState.results.length > 0) {
            dropdown.style.display = 'block';
            autocompleteState.activeInputId = inputId;
        }
    });

    // Keyboard navigation
    input.addEventListener('keydown', function (e) {
        const items = dropdown.querySelectorAll('.search-item');

        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                if (items.length === 0) return;
                autocompleteState.selectedIndex = Math.min(autocompleteState.selectedIndex + 1, items.length - 1);
                updateHighlight(items, autocompleteState.selectedIndex);
                scrollToItem(items, autocompleteState.selectedIndex);
                break;

            case 'ArrowUp':
                e.preventDefault();
                if (items.length === 0) return;
                autocompleteState.selectedIndex = Math.max(autocompleteState.selectedIndex - 1, -1);
                updateHighlight(items, autocompleteState.selectedIndex);
                scrollToItem(items, autocompleteState.selectedIndex);
                break;

            case 'Enter':
                e.preventDefault();
                if (autocompleteState.selectedIndex >= 0 && autocompleteState.selectedIndex < items.length) {
                    // Select highlighted item
                    const selectedItem = items[autocompleteState.selectedIndex];
                    const symbol = selectedItem.dataset.symbol;
                    input.value = symbol;
                    hideDropdown(inputId);
                    if (options.onSelect) options.onSelect(symbol);
                } else {
                    // No selection — search directly
                    hideDropdown(inputId);
                    if (options.onSearch) options.onSearch(input.value.trim());
                }
                break;

            case 'Escape':
                e.preventDefault();
                hideDropdown(inputId);
                input.blur();
                break;
        }
    });

    // Click outside to close
    document.addEventListener('click', function (e) {
        if (!wrapper.contains(e.target)) {
            hideDropdown(inputId);
        }
    });

    // Store ref for cleanup
    input.dataset.autocomplete = 'true';
}

async function performSearch(inputId, query, dropdownEl, options) {
    try {
        const res = await fetch(`${API_BASE_URL}/search?q=${encodeURIComponent(query)}`);
        const json = await res.json();

        if (!json.success || !json.data) {
            dropdownEl.innerHTML = `<div class="search-item search-error">搜尋失敗，請重試</div>`;
            dropdownEl.style.display = 'block';
            autocompleteState.results = [];
            return;
        }

        const results = json.data;
        autocompleteState.results = results;
        autocompleteState.selectedIndex = -1;
        autocompleteState.activeInputId = inputId;

        if (results.length === 0) {
            dropdownEl.innerHTML = `<div class="search-item search-empty">'${query}' — 無匹配結果</div>`;
            dropdownEl.style.display = 'block';
            return;
        }

        // Build dropdown items
        let html = results.map((item, idx) => {
            const sym = item.symbol || '';
            const name = item.name || '';
            const price = item.price ? '$' + item.price.toFixed(2) : '';
            const change = item.change_percent != null ? item.change_percent.toFixed(2) + '%' : '';
            const changeCls = (item.change_percent || 0) >= 0 ? 'up' : 'down';
            const arrow = (item.change_percent || 0) >= 0 ? '▲' : '▼';
            return `<div class="search-item" data-symbol="${sym}" data-index="${idx}" onclick="selectSearchItem('${inputId}', '${sym}', this)">
                <div class="search-item-left">
                    <span class="search-item-symbol">${sym}</span>
                    <span class="search-item-name">${name}</span>
                </div>
                <div class="search-item-right">
                    <span class="search-item-price">${price}</span>
                    <span class="search-item-change ${changeCls}">${arrow} ${change}</span>
                </div>
            </div>`;
        }).join('');

        dropdownEl.innerHTML = html;
        dropdownEl.style.display = 'block';

    } catch (e) {
        console.warn('Search error:', e.message);
        dropdownEl.innerHTML = `<div class="search-item search-error">搜尋失敗，請重試</div>`;
        dropdownEl.style.display = 'block';
        autocompleteState.results = [];
    }
}

function selectSearchItem(inputId, symbol, el) {
    const input = document.getElementById(inputId);
    if (input) {
        input.value = symbol;
    }
    hideDropdown(inputId);
    // Find the onSelect callback from the input's autocomplete setup
    // We dispatch a custom event so the setup can listen
    input.dispatchEvent(new CustomEvent('autocomplete-select', { detail: { symbol } }));
}

function hideDropdown(inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;
    // Find the dropdown sibling
    const wrapper = input.parentElement;
    if (!wrapper) return;
    const dropdown = wrapper.querySelector('.search-autocomplete-dropdown');
    if (dropdown) {
        dropdown.style.display = 'none';
    }
    autocompleteState.activeInputId = null;
    autocompleteState.selectedIndex = -1;
}

function updateHighlight(items, index) {
    items.forEach((item, i) => {
        item.classList.toggle('search-item-highlighted', i === index);
    });
}

function scrollToItem(items, index) {
    if (index < 0 || index >= items.length) return;
    items[index].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

// ── Initialize autocomplete on all stock inputs ──
document.addEventListener('DOMContentLoaded', function () {
    // Delay to ensure other inits run first, then setup autocompletes
    setTimeout(() => {
        setupSearchAutocomplete('analysisStockInput', {
            onSelect: (symbol) => analyzeSingleStock(),
            onSearch: (query) => {
                const input = document.getElementById('analysisStockInput');
                if (input) input.value = query;
                analyzeSingleStock();
            },
            placeholder: '輸入股票代碼 (0700.HK, AAPL)'
        });

        setupSearchAutocomplete('strategyStockInput', {
            onSelect: (symbol) => loadStrategy(),
            onSearch: (query) => {
                const input = document.getElementById('strategyStockInput');
                if (input) input.value = query;
                loadStrategy();
            },
            placeholder: '股票代碼'
        });

        setupSearchAutocomplete('reportStockInput', {
            onSelect: (symbol) => generateReport(),
            onSearch: (query) => {
                const input = document.getElementById('reportStockInput');
                if (input) input.value = query;
                generateReport();
            },
            placeholder: '股票代碼'
        });

        // Nav search bar — navigates to analysis tab on select
        setupSearchAutocomplete('navSearchInput', {
            onSelect: (symbol) => {
                currentSymbol = symbol;
                switchTab('dashboard');
                selectWatchlistItem(symbol);
            },
            onSearch: (query) => {
                // Switch to analysis page with the query
                const analysisInput = document.getElementById('analysisStockInput');
                if (analysisInput) analysisInput.value = query;
                switchTab('analysis');
                setTimeout(() => analyzeSingleStock(), 300);
            },
            placeholder: '搜尋股票代碼 / 名稱 (e.g. 0700, tencent)'
        });
    }, 100);
});

console.log('✅ StockAI v2.0 app.js loaded successfully');
console.log('🔍 Search autocomplete enabled');
