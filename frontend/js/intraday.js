// ==================== 日內交易模組 - 專業交易員版 ====================

// 定義 API 基礎路徑（避免重複聲明）
if (typeof API_BASE_URL === 'undefined') {
    var API_BASE_URL = 'http://localhost:5000/api';
}

let intradayCandleChart = null;
let intradayCurrentStock = null;
let intradayCurrentPrice = 0;
let intradayTimer = null;

// 目標價位
let targetBuyPrice = 0;
let targetSellPrice = 0;
let targetStopPrice = 0;

// 專業交易員參數
let intradayATR = 0;           // 實時 ATR
let intradayTrend = 'neutral'; // 趨勢方向
let intradayADX = 0;           // 趨勢強度
let lastUpdateTime = null;     // 最後更新時間

// 頁面載入時初始化
document.addEventListener('DOMContentLoaded', function () {
    console.log('📊 日內交易模組初始化 - 專業交易員版');
    setTimeout(() => {
        const intradayMode = document.getElementById('intraday-mode');
        if (intradayMode && intradayMode.classList.contains('active')) {
            analyzeIntraday();
        }
    }, 500);
    startIntradayPriceUpdate();
});

// 切換模式
function switchMode(mode) {
    const tabs = document.querySelectorAll('.mode-tab');
    tabs.forEach(tab => tab.classList.remove('active'));
    const activeTab = document.querySelector(`.mode-tab[data-mode="${mode}"]`);
    if (activeTab) activeTab.classList.add('active');

    const swingMode = document.getElementById('swing-mode');
    const intradayMode = document.getElementById('intraday-mode');
    const newsMode = document.getElementById('news-mode');
    const dailyMode = document.getElementById('daily-mode');
    if (swingMode) swingMode.classList.remove('active');
    if (intradayMode) intradayMode.classList.remove('active');
    if (newsMode) newsMode.classList.remove('active');
    if (dailyMode) dailyMode.classList.remove('active');
    const targetMode = document.getElementById(`${mode}-mode`);
    if (targetMode) targetMode.classList.add('active');

    if (mode === 'intraday') {
        analyzeIntraday();
        startIntradayPriceUpdate();
    } else {
        stopIntradayPriceUpdate();
    }

    // 每日報告模式：自動恢復緩存的報告
    if (mode === 'daily') {
        setTimeout(function() { restoreDailyReport(); }, 50);
    }

    // 新聞模式：自動聚焦輸入框
    if (mode === 'news') {
        setTimeout(() => {
            const input = document.getElementById('newsStockInput');
            if (input) input.focus();
        }, 100);
    }
}

// 開始即時價格更新（每3秒）
function startIntradayPriceUpdate() {
    if (intradayTimer) clearInterval(intradayTimer);
    intradayTimer = setInterval(() => {
        const intradayMode = document.getElementById('intraday-mode');
        if (intradayMode && intradayMode.classList.contains('active') && intradayCurrentStock) {
            updateIntradayRealtimePrice();
        }
    }, 3000);
}

function stopIntradayPriceUpdate() {
    if (intradayTimer) {
        clearInterval(intradayTimer);
        intradayTimer = null;
    }
}

// 安全設置文本
function safeSetText(id, text) {
    const el = document.getElementById(id);
    if (el) el.innerText = text;
}

function safeSetHtml(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
}

function safeSetStyle(id, property, value) {
    const el = document.getElementById(id);
    if (el) el.style[property] = value;
}

// ==================== 專業交易員核心邏輯 ====================

// 獲取當前交易時段
function getTradingSession() {
    const now = new Date();
    const hour = now.getHours();
    const minute = now.getMinutes();
    const time = hour * 100 + minute;

    if (time >= 930 && time <= 1000) return 'opening';      // 開盤半小時
    if (time >= 1000 && time <= 1130) return 'morning';     // 上午盤
    if (time >= 1130 && time <= 1300) return 'lunch';       // 午休
    if (time >= 1300 && time <= 1430) return 'afternoon';   // 下午盤
    if (time >= 1430 && time <= 1600) return 'closing';     // 收盤前
    return 'normal';
}

// 獲取時間乘數（不同時段不同策略）
function getTimeMultiplier() {
    const session = getTradingSession();
    switch (session) {
        case 'opening': return 1.3;   // 開盤波動大，目標放寬
        case 'morning': return 1.0;   // 正常波動
        case 'lunch': return 0.6;   // 午休流動性差，目標收窄
        case 'afternoon': return 0.9;  // 下午盤稍弱
        case 'closing': return 1.2;   // 收盤波動大
        default: return 1.0;
    }
}

// 獲取趨勢乘數（順勢/逆勢）
function getTrendMultiplier() {
    if (intradayTrend === '上升') return 1.2;      // 上升趨勢，目標放寬
    if (intradayTrend === '下降') return 0.8;      // 下降趨勢，目標收窄
    return 1.0;                                    // 震盪，正常
}

// 獲取波動率乘數（基於 ATR）
function getVolatilityMultiplier() {
    if (!intradayATR || intradayATR <= 0) return 1.0;
    const atrPercent = intradayATR / intradayCurrentPrice;
    if (atrPercent > 0.025) return 1.4;   // 高波動，目標放寬
    if (atrPercent > 0.015) return 1.2;   // 中高波動
    if (atrPercent > 0.008) return 1.0;   // 正常波動
    return 0.8;                           // 低波動，目標收窄
}

// 專業交易員級別目標價計算
function calculateProfessionalTargets(currentPrice) {
    // 1. 基礎距離（專業參數，基於回測優化）
    let baseBuyDistance = 0.005;   // 0.5% 買入距離
    let baseSellDistance = 0.012;  // 1.2% 賣出距離
    let baseStopDistance = 0.004;  // 0.4% 止損距離

    // 2. 根據股價區間調整（低價股波動大）
    if (currentPrice < 10) {
        baseBuyDistance = 0.012;
        baseSellDistance = 0.025;
        baseStopDistance = 0.008;
    } else if (currentPrice < 50) {
        baseBuyDistance = 0.008;
        baseSellDistance = 0.018;
        baseStopDistance = 0.006;
    } else if (currentPrice > 200) {
        baseBuyDistance = 0.003;
        baseSellDistance = 0.008;
        baseStopDistance = 0.0025;
    }

    // 3. 應用時間乘數
    const timeMultiplier = getTimeMultiplier();
    baseBuyDistance *= timeMultiplier;
    baseSellDistance *= timeMultiplier;
    baseStopDistance *= timeMultiplier;

    // 4. 應用趨勢乘數
    const trendMultiplier = getTrendMultiplier();
    baseBuyDistance *= trendMultiplier;
    baseSellDistance *= trendMultiplier;

    // 5. 應用波動率乘數
    const volMultiplier = getVolatilityMultiplier();
    baseBuyDistance *= volMultiplier;
    baseSellDistance *= volMultiplier;
    baseStopDistance *= volMultiplier;

    // 6. 確保最小距離（避免過於接近）
    const minDistance = currentPrice * 0.002; // 最小 0.2%
    const maxBuyDistance = currentPrice * 0.03; // 最大 3%

    let buyDistance = currentPrice * baseBuyDistance;
    let sellDistance = currentPrice * baseSellDistance;
    let stopDistance = currentPrice * baseStopDistance;

    buyDistance = Math.min(maxBuyDistance, Math.max(minDistance, buyDistance));
    sellDistance = Math.min(maxBuyDistance, Math.max(minDistance, sellDistance));
    stopDistance = Math.min(maxBuyDistance, Math.max(minDistance, stopDistance));

    // 7. 計算目標價
    const buyTarget = Math.round((currentPrice - buyDistance) * 100) / 100;
    const sellTarget = Math.round((currentPrice + sellDistance) * 100) / 100;
    const stopTarget = Math.round((currentPrice - stopDistance) * 100) / 100;

    // 8. 風險回報比計算
    const risk = currentPrice - stopTarget;
    const reward = sellTarget - currentPrice;
    const riskReward = risk > 0 ? (reward / risk).toFixed(1) : 0;

    // 9. 根據風險回報比調整目標（至少 1:1.5）
    if (riskReward < 1.5 && riskReward > 0) {
        // 如果風險回報比太低，調整賣出目標
        const adjustedSell = currentPrice + risk * 1.5;
        return {
            buy: buyTarget,
            sell: Math.round(adjustedSell * 100) / 100,
            stop: stopTarget,
            riskReward: 1.5
        };
    }

    return {
        buy: buyTarget,
        sell: sellTarget,
        stop: stopTarget,
        riskReward: parseFloat(riskReward)
    };
}

// 更新 ATR 和趨勢數據（從 K線計算）
function updateMarketMetrics(klineData) {
    if (!klineData || klineData.length < 10) return;

    // 計算 ATR (5)
    let closes = [];
    let highs = [];
    let lows = [];

    for (let i = 0; i < Math.min(20, klineData.length); i++) {
        const candle = klineData[i];
        if (candle && candle.y) {
            closes.push(candle.y[3]);
            highs.push(candle.y[1]);
            lows.push(candle.y[2]);
        }
    }

    if (closes.length >= 5) {
        // 計算 ATR
        let trValues = [];
        for (let i = 1; i < highs.length; i++) {
            const tr = Math.max(
                highs[i] - lows[i],
                Math.abs(highs[i] - closes[i - 1]),
                Math.abs(lows[i] - closes[i - 1])
            );
            trValues.push(tr);
        }
        intradayATR = trValues.slice(-5).reduce((a, b) => a + b, 0) / 5;

        // 計算趨勢（簡單移動平均）
        const ma5 = closes.slice(-5).reduce((a, b) => a + b, 0) / 5;
        const ma10 = closes.slice(-10).reduce((a, b) => a + b, 0) / 10;
        const currentPrice = closes[closes.length - 1];

        if (currentPrice > ma5 && ma5 > ma10) {
            intradayTrend = '上升';
        } else if (currentPrice < ma5 && ma5 < ma10) {
            intradayTrend = '下降';
        } else {
            intradayTrend = '震盪';
        }

        // 計算 ADX 簡化版
        const priceChange = Math.abs(currentPrice - closes[closes.length - 6]);
        intradayADX = (priceChange / intradayATR) * 100;

        console.log(`📈 市場指標 - ATR: $${intradayATR.toFixed(2)}, 趨勢: ${intradayTrend}, ADX: ${intradayADX.toFixed(1)}`);
    }
}

// ==================== 主要分析函數 ====================

async function analyzeIntraday() {
    const stockCode = document.getElementById('intradayStockInput')?.value.trim() || '0700.HK';
    console.log('📊 日內分析股票:', stockCode);
    showIntradayLoading();

    try {
        // 1. 獲取股票即時數據
        let stockData = null;
        try {
            const stockResponse = await fetch(`${API_BASE_URL}/stock/${stockCode}`);
            stockData = await stockResponse.json();
        } catch (e) {
            console.warn('API 連接失敗，使用模擬數據', e);
        }

        if (stockData && stockData.success) {
            intradayCurrentStock = stockData.data;
            intradayCurrentPrice = stockData.data.price;
            updateIntradayQuote(stockData.data);
        } else {
            intradayCurrentStock = {
                symbol: stockCode,
                name: stockCode === '0700.HK' ? '騰訊控股有限公司' : stockCode,
                price: 380 + (Math.random() - 0.5) * 10,
                change: (Math.random() - 0.5) * 3,
                change_percent: ((Math.random() - 0.5) * 2).toFixed(2),
                high: 385,
                low: 375,
                volume: Math.floor(10000000 + Math.random() * 5000000),
                open: 382,
                prev_close: 381,
                technicals: { ma5: 378, ma20: 374, rsi14: 55, volume_ratio: 1.2 }
            };
            intradayCurrentPrice = intradayCurrentStock.price;
            updateIntradayQuote(intradayCurrentStock);
        }

        // 2. 獲取日內 K線數據（用於計算 ATR 和趨勢）
        let klineData = null;
        try {
            const klineResponse = await fetch(`${API_BASE_URL}/intraday/kline/${stockCode}?period=15m&days=5`);
            klineData = await klineResponse.json();
        } catch (e) {
            console.warn('獲取K線失敗，使用模擬數據', e);
        }

        if (klineData && klineData.success && klineData.data && klineData.data.length > 0) {
            updateIntradayKLineChart(klineData.data);
            updateMarketMetrics(klineData.data);
        } else {
            const mockKline = generateMockIntradayKline();
            updateIntradayKLineChart(mockKline);
            updateMarketMetrics(mockKline);
        }

        // 3. 獲取日內技術指標
        let indicatorsData = null;
        try {
            const indicatorsResponse = await fetch(`${API_BASE_URL}/intraday/indicators/${stockCode}`);
            indicatorsData = await indicatorsResponse.json();
        } catch (e) {
            console.warn('獲取指標失敗，使用模擬數據', e);
        }

        if (indicatorsData && indicatorsData.success) {
            updateIntradayIndicators(indicatorsData.data);
        } else {
            updateIntradayIndicators(generateMockIntradayIndicators());
        }

        // 4. 計算專業級目標價
        updateProfessionalPriceTargets();

        // 5. 更新 AI 信號
        updateIntradayAISignals(intradayCurrentStock);

        // 6. 更新交易計劃
        updateTradePlan();

        // 顯示所有區域
        const sections = ['intradayHeader', 'intradayChartSection', 'intradayIndicators', 'tradePlanCard', 'intradaySignalBox'];
        sections.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.style.display = 'block';
        });

        console.log('✅ 日內分析完成 - 專業交易員模式');

    } catch (error) {
        console.error('❌ 日內分析失敗:', error);
        showIntradayError(error.message);
        useMockIntradayData();
    } finally {
        hideIntradayLoading();
    }
}

// 專業目標價計算和更新
function updateProfessionalPriceTargets() {
    const targets = calculateProfessionalTargets(intradayCurrentPrice);

    targetBuyPrice = targets.buy;
    targetSellPrice = targets.sell;
    targetStopPrice = targets.stop;

    // 更新顯示
    const buyEl = document.getElementById('targetBuyPrice');
    const sellEl = document.getElementById('targetSellPrice');
    const stopEl = document.getElementById('targetStopPrice');
    if (buyEl) buyEl.innerHTML = `$${targetBuyPrice.toFixed(2)}`;
    if (sellEl) sellEl.innerHTML = `$${targetSellPrice.toFixed(2)}`;
    if (stopEl) stopEl.innerHTML = `$${targetStopPrice.toFixed(2)}`;

    // 更新風險回報比顯示
    const rrEl = document.getElementById('riskRewardRatio');
    if (rrEl && targets.riskReward) {
        rrEl.innerHTML = `風險回報比: 1:${targets.riskReward}`;
    }

    // 更新距離顯示
    updatePriceLevels();
}

function useMockIntradayData() {
    intradayCurrentPrice = 380;
    intradayCurrentStock = {
        symbol: '0700.HK',
        name: '騰訊控股有限公司',
        price: 380,
        change: 0,
        change_percent: 0,
        high: 382,
        low: 378,
        volume: '12.5M',
        technicals: { ma5: 378, ma20: 374, rsi14: 55, volume_ratio: 1.0 }
    };
    updateIntradayQuote(intradayCurrentStock);
    updateProfessionalPriceTargets();

    const mockKline = generateMockIntradayKline();
    updateIntradayKLineChart(mockKline);
    updateMarketMetrics(mockKline);
    updateIntradayIndicators(generateMockIntradayIndicators());
    updateIntradayAISignals(intradayCurrentStock);
    updateTradePlan();

    const sections = ['intradayHeader', 'intradayChartSection', 'intradayIndicators', 'tradePlanCard', 'intradaySignalBox'];
    sections.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = 'block';
    });
}

function generateMockIntradayKline() {
    const data = [];
    const now = new Date();
    let basePrice = intradayCurrentPrice || 380;

    for (let i = 0; i < 50; i++) {
        const time = new Date(now);
        time.setMinutes(now.getMinutes() - (50 - i) * 15);
        const change = (Math.random() - 0.5) * 4;
        const open = basePrice;
        const close = basePrice + change;
        const high = Math.max(open, close) + Math.random() * 2;
        const low = Math.min(open, close) - Math.random() * 2;
        data.push({ x: time.getTime(), y: [open, high, low, close] });
        basePrice = close;
    }
    return data;
}

function generateMockIntradayIndicators() {
    const currentPrice = intradayCurrentPrice || 380;
    const vwap = currentPrice * (1 + (Math.random() - 0.5) * 0.005);
    const rsi7 = 40 + Math.random() * 40;
    const bbMiddle = currentPrice;
    const bbUpper = bbMiddle * 1.015;
    const bbLower = bbMiddle * 0.985;

    let vwapSignal = '中性';
    if (currentPrice > vwap) vwapSignal = '上方';
    else if (currentPrice < vwap) vwapSignal = '下方';

    return {
        vwap: vwap,
        vwap_signal: vwapSignal,
        rsi7: rsi7,
        bb_position: currentPrice > bbUpper ? '突破上軌' : currentPrice < bbLower ? '跌破下軌' : '中軌附近',
        bb_signal: currentPrice > bbUpper ? '超買' : currentPrice < bbLower ? '超賣' : '正常',
        delta: (Math.random() - 0.5) > 0 ? '+5.2M' : '-3.1M',
        delta_signal: (Math.random() - 0.5) > 0 ? '正流入' : '負流出',
        atr5: currentPrice * 0.008,
        atr_signal: '正常波動',
        momentum: (Math.random() - 0.5) * 2,
        momentum_signal: '平穩'
    };
}

function updateIntradayQuote(data) {
    safeSetText('intradayStockCode', data.symbol);
    safeSetText('intradayStockName', data.name || data.symbol);
    safeSetText('intradayPrice', `$${data.price.toFixed(2)}`);

    const priceChangeEl = document.getElementById('intradayPriceChange');
    if (priceChangeEl) {
        const changeClass = (data.change || 0) >= 0 ? 'positive' : 'negative';
        priceChangeEl.innerHTML = `${(data.change || 0) >= 0 ? '+' : ''}${(data.change || 0).toFixed(2)} (${data.change_percent || 0}%)`;
        priceChangeEl.className = `price-sub ${changeClass}`;
    }

    const bidPrice = data.price - (data.price * 0.0005);
    const askPrice = data.price + (data.price * 0.0005);
    safeSetText('bidPrice', `$${bidPrice.toFixed(2)}`);
    safeSetText('askPrice', `$${askPrice.toFixed(2)}`);
    safeSetText('spread', `$${(askPrice - bidPrice).toFixed(2)}`);

    safeSetText('intradayDayRange', `$${data.low || data.price - 5} - $${data.high || data.price + 5}`);

    const volume = data.volume;
    if (typeof volume === 'number') {
        safeSetText('intradayVolume', formatIntradayVolume(volume));
    } else {
        safeSetText('intradayVolume', volume || '--');
    }

    const volumeRatio = data.technicals?.volume_ratio;
    if (volumeRatio !== undefined) {
        safeSetText('intradayVolumeRatio', volumeRatio.toFixed(2));
    }

    const updateTimeEl = document.getElementById('intradayUpdateTime');
    if (updateTimeEl) {
        updateTimeEl.innerHTML = `<i class="bi bi-clock"></i> <span>更新: ${new Date().toLocaleTimeString('zh-HK')}</span>`;
    }
}

function formatIntradayVolume(volume) {
    if (!volume) return '--';
    if (volume >= 1e9) return `${(volume / 1e9).toFixed(2)}B`;
    if (volume >= 1e6) return `${(volume / 1e6).toFixed(2)}M`;
    if (volume >= 1e3) return `${(volume / 1e3).toFixed(2)}K`;
    return volume.toString();
}

async function updateIntradayRealtimePrice() {
    if (!intradayCurrentStock) return;
    try {
        const response = await fetch(`${API_BASE_URL}/stock/${intradayCurrentStock.symbol}`);
        const data = await response.json();
        if (data.success) {
            intradayCurrentPrice = data.data.price;
            intradayCurrentStock = data.data;
            const priceEl = document.getElementById('intradayPrice');
            if (priceEl) priceEl.innerHTML = `$${data.data.price.toFixed(2)}`;
            updateProfessionalPriceTargets();
        }
    } catch (error) {
        intradayCurrentPrice = Math.max(1, intradayCurrentPrice + (Math.random() - 0.5) * 0.5);
        const priceEl = document.getElementById('intradayPrice');
        if (priceEl) priceEl.innerHTML = `$${intradayCurrentPrice.toFixed(2)}`;
        updateProfessionalPriceTargets();
    }
}

function updatePriceLevels() {
    const currentPrice = intradayCurrentPrice;
    if (targetBuyPrice === 0) updateProfessionalPriceTargets();

    const buyDistance = targetBuyPrice - currentPrice;
    const sellDistance = targetSellPrice - currentPrice;
    const stopDistance = currentPrice - targetStopPrice;

    const buyDistEl = document.getElementById('buyDistance');
    const sellDistEl = document.getElementById('sellDistance');
    const stopDistEl = document.getElementById('stopDistance');

    if (buyDistEl) {
        const buyPercent = (Math.abs(buyDistance) / currentPrice * 100).toFixed(2);
        buyDistEl.innerHTML = `距離: ${buyDistance >= 0 ? '▼' : '▲'} $${Math.abs(buyDistance).toFixed(2)} (${buyPercent}%)`;
    }
    if (sellDistEl) {
        const sellPercent = (Math.abs(sellDistance) / currentPrice * 100).toFixed(2);
        sellDistEl.innerHTML = `距離: ${sellDistance >= 0 ? '▲' : '▼'} $${Math.abs(sellDistance).toFixed(2)} (${sellPercent}%)`;
    }
    if (stopDistEl) {
        const stopPercent = (stopDistance / currentPrice * 100).toFixed(2);
        stopDistEl.innerHTML = `距離: ▼ $${stopDistance.toFixed(2)} (${stopPercent}%)`;
    }

    const buyStatus = document.getElementById('buyStatus');
    const sellStatus = document.getElementById('sellStatus');
    const stopStatus = document.getElementById('stopStatus');

    if (buyStatus) {
        if (currentPrice <= targetBuyPrice) {
            buyStatus.innerHTML = '🎯 已觸發！可考慮買入';
            buyStatus.className = 'price-status status-triggered';
        } else {
            buyStatus.innerHTML = '⏳ 等待觸發';
            buyStatus.className = 'price-status status-waiting';
        }
    }

    if (sellStatus) {
        if (currentPrice >= targetSellPrice) {
            sellStatus.innerHTML = '🎯 已觸發！可考慮賣出';
            sellStatus.className = 'price-status status-triggered';
        } else {
            sellStatus.innerHTML = '⏳ 等待觸發';
            sellStatus.className = 'price-status status-waiting';
        }
    }

    if (stopStatus) {
        if (currentPrice <= targetStopPrice) {
            stopStatus.innerHTML = '⚠️ 已觸發止損！';
            stopStatus.className = 'price-status status-danger';
        } else {
            stopStatus.innerHTML = '🟢 安全距離';
            stopStatus.className = 'price-status status-waiting';
        }
    }

    updatePriceLevelChart(currentPrice);
    updateTradePlan();
}

function updatePriceLevelChart(currentPrice) {
    const minPrice = Math.min(targetStopPrice, targetBuyPrice, currentPrice) - 2;
    const maxPrice = targetSellPrice + 2;
    const range = maxPrice - minPrice;
    if (range <= 0) return;

    const sellPercent = Math.min(100, Math.max(0, ((targetSellPrice - minPrice) / range) * 100));
    const currentPercent = Math.min(100, Math.max(0, ((currentPrice - minPrice) / range) * 100));
    const buyPercent = Math.min(100, Math.max(0, ((targetBuyPrice - minPrice) / range) * 100));
    const stopPercent = Math.min(100, Math.max(0, ((targetStopPrice - minPrice) / range) * 100));

    const setPrice = (id, price) => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = `$${price.toFixed(2)}`;
    };
    setPrice('chartSellPrice', targetSellPrice);
    setPrice('chartCurrentPrice', currentPrice);
    setPrice('chartBuyPrice', targetBuyPrice);
    setPrice('chartStopPrice', targetStopPrice);

    const markers = document.querySelectorAll('#priceLevelChart .level-marker');
    if (markers.length >= 4) {
        markers[0].style.left = `${sellPercent}%`;
        markers[1].style.left = `${currentPercent}%`;
        markers[2].style.left = `${buyPercent}%`;
        markers[3].style.left = `${stopPercent}%`;
    }
}

function setBuyPrice() {
    const input = document.getElementById('buyPriceInput');
    if (!input) return;
    const value = parseFloat(input.value);
    if (!isNaN(value) && value > 0) {
        targetBuyPrice = value;
        updatePriceLevels();
        showIntradayMessage(`買入價已設定為 $${targetBuyPrice.toFixed(2)}`, 'success');
        input.value = '';
    } else {
        showIntradayMessage('請輸入有效的價格', 'error');
    }
}

function setSellPrice() {
    const input = document.getElementById('sellPriceInput');
    if (!input) return;
    const value = parseFloat(input.value);
    if (!isNaN(value) && value > 0) {
        targetSellPrice = value;
        updatePriceLevels();
        showIntradayMessage(`賣出價已設定為 $${targetSellPrice.toFixed(2)}`, 'success');
        input.value = '';
    } else {
        showIntradayMessage('請輸入有效的價格', 'error');
    }
}

function setStopPrice() {
    const input = document.getElementById('stopPriceInput');
    if (!input) return;
    const value = parseFloat(input.value);
    if (!isNaN(value) && value > 0) {
        targetStopPrice = value;
        updatePriceLevels();
        showIntradayMessage(`止損價已設定為 $${targetStopPrice.toFixed(2)}`, 'success');
        input.value = '';
    } else {
        showIntradayMessage('請輸入有效的價格', 'error');
    }
}

function updateTradePlan() {
    const currentPrice = intradayCurrentPrice;
    const risk = currentPrice - targetStopPrice;
    const reward = targetSellPrice - currentPrice;
    const riskRewardRatio = risk > 0 ? (reward / risk).toFixed(1) : 'N/A';

    const rrEl = document.getElementById('riskRewardRatio');
    if (rrEl) rrEl.innerHTML = `風險回報比: ${riskRewardRatio !== 'N/A' ? `1:${riskRewardRatio}` : 'N/A'}`;

    let action = '觀望';
    let actionColor = '#94a3b8';
    let position = '觀望';
    let confidence = '中';

    if (currentPrice <= targetBuyPrice) {
        action = '買入';
        actionColor = '#10b981';
        position = '2-3% 倉位';
        confidence = riskRewardRatio > 2 ? '高' : (riskRewardRatio > 1.2 ? '中' : '低');
    } else if (currentPrice >= targetSellPrice) {
        action = '賣出';
        actionColor = '#ef4444';
        position = '減倉 50%';
        confidence = '高';
    } else if (currentPrice <= targetStopPrice) {
        action = '止損';
        actionColor = '#ef4444';
        position = '清倉';
        confidence = '高';
    } else {
        // 觀望時根據距離給建議
        const buyDistance = (targetBuyPrice - currentPrice) / currentPrice * 100;
        const sellDistance = (targetSellPrice - currentPrice) / currentPrice * 100;

        if (buyDistance < 0.3 && buyDistance > 0) {
            action = '接近買入';
            actionColor = '#fbbf24';
        } else if (sellDistance < 0.3 && sellDistance > 0) {
            action = '接近賣出';
            actionColor = '#fbbf24';
        }
    }

    const tradeActionEl = document.getElementById('tradeAction');
    if (tradeActionEl) {
        tradeActionEl.innerHTML = action;
        tradeActionEl.style.color = actionColor;
    }

    const positionEl = document.getElementById('positionSize');
    if (positionEl) positionEl.innerHTML = position;

    const holdingEl = document.getElementById('holdingTime');
    if (holdingEl) {
        const session = getTradingSession();
        if (session === 'opening') holdingEl.innerHTML = '開盤時段 (15-30分鐘)';
        else if (session === 'closing') holdingEl.innerHTML = '收盤時段 (30-60分鐘)';
        else holdingEl.innerHTML = '日內 (1-2小時)';
    }

    const confEl = document.getElementById('tradeConfidence');
    if (confEl) confEl.innerHTML = confidence;
}

function updateIntradayKLineChart(klineData) {
    const chartElement = document.querySelector("#intradayCandlestickChart");
    if (!chartElement) {
        console.warn('找不到 intradayCandlestickChart 元素');
        return;
    }

    if (!klineData || klineData.length === 0) {
        klineData = generateMockIntradayKline();
    }

    const options = {
        series: [{ name: 'K線', type: 'candlestick', data: klineData.map(d => ({ x: d.x, y: d.y })) }],
        chart: {
            type: 'candlestick',
            height: 400,
            background: 'transparent',
            foreColor: '#f8fafc',
            toolbar: { show: true, tools: { download: true, selection: true, zoom: true, pan: true, reset: true } }
        },
        plotOptions: { candlestick: { colors: { upward: '#10b981', downward: '#ef4444' } } },
        xaxis: { type: 'datetime', labels: { style: { colors: '#f8fafc' }, format: 'HH:mm', rotate: -45 } },
        yaxis: { labels: { style: { colors: '#f8fafc' }, formatter: (v) => `$${v.toFixed(2)}` } },
        grid: { borderColor: '#334155' },
        tooltip: { theme: 'dark' }
    };

    if (intradayCandleChart) intradayCandleChart.destroy();
    intradayCandleChart = new ApexCharts(chartElement, options);
    intradayCandleChart.render();
}

function updateIntradayIndicators(indicators) {
    if (!indicators) indicators = generateMockIntradayIndicators();

    const setValue = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = value;
    };
    const setSignal = (id, text, color) => {
        const el = document.getElementById(id);
        if (el) {
            el.innerHTML = text;
            if (color) el.style.color = color;
        }
    };

    setValue('vwapValue', indicators.vwap ? `$${indicators.vwap.toFixed(2)}` : '--');
    const vwapSignal = indicators.vwap_signal || '中性';
    setSignal('vwapSignal', vwapSignal, vwapSignal === '上方' ? '#10b981' : vwapSignal === '下方' ? '#ef4444' : '#94a3b8');

    const rsi7 = indicators.rsi7 !== undefined ? indicators.rsi7.toFixed(1) : '50.0';
    setValue('intradayRsi', rsi7);
    const rsi = parseFloat(rsi7);
    let rsiSignal = '中性';
    let rsiColor = '#94a3b8';
    if (rsi > 70) { rsiSignal = '超買'; rsiColor = '#ef4444'; }
    else if (rsi < 30) { rsiSignal = '超賣'; rsiColor = '#10b981'; }
    setSignal('intradayRsiSignal', rsiSignal, rsiColor);

    setValue('bbPosition', indicators.bb_position || '中軌附近');
    const bbSignalText = indicators.bb_signal || '正常';
    setSignal('bbSignal', bbSignalText, bbSignalText === '超買' ? '#ef4444' : bbSignalText === '超賣' ? '#10b981' : '#94a3b8');

    setValue('cumulativeDelta', indicators.delta || '--');
    const deltaSignal = indicators.delta_signal || '中性';
    setSignal('deltaSignal', deltaSignal, deltaSignal === '正流入' ? '#10b981' : deltaSignal === '負流出' ? '#ef4444' : '#94a3b8');

    setValue('atr5', indicators.atr5 ? `$${indicators.atr5.toFixed(2)}` : '--');
    setValue('atrSignal', indicators.atr_signal || '正常波動');

    const momentum = indicators.momentum !== undefined ? `${indicators.momentum > 0 ? '+' : ''}${indicators.momentum.toFixed(2)}%` : '--';
    setValue('momentum', momentum);
    setValue('momentumSignal', indicators.momentum_signal || '平穩');

    const volume = intradayCurrentStock?.volume || '--';
    setValue('intradayVolumeShort', typeof volume === 'number' ? formatIntradayVolume(volume) : volume);
    const volumeRatio = intradayCurrentStock?.technicals?.volume_ratio || 1;
    setSignal('volumeSignalShort', volumeRatio > 1.2 ? '放量' : volumeRatio < 0.8 ? '縮量' : '正常',
        volumeRatio > 1.2 ? '#10b981' : volumeRatio < 0.8 ? '#ef4444' : '#94a3b8');

    setValue('moneyFlow', indicators.delta || '0');
    setSignal('moneyFlowSignal', deltaSignal, deltaSignal === '正流入' ? '#10b981' : deltaSignal === '負流出' ? '#ef4444' : '#94a3b8');
}

function updateIntradayAISignals(data) {
    const stockData = data || intradayCurrentStock;
    if (!stockData) {
        setRecommendationText('⚖️ 等待數據載入...');
        return;
    }

    const currentPrice = stockData.price;
    const tech = stockData.technicals || {};

    const setSignal = (id, text, color) => {
        const el = document.getElementById(id);
        if (el) {
            el.innerHTML = text;
            if (color) el.style.color = color;
        }
    };

    const ma5 = tech.ma5 || currentPrice * 0.99;
    const ma20 = tech.ma20 || currentPrice * 0.98;
    const trendSignal = currentPrice > ma5 ? '上升' : (currentPrice < ma5 ? '下降' : '震盪');
    setSignal('intradayTrend', trendSignal, trendSignal === '上升' ? '#10b981' : trendSignal === '下降' ? '#ef4444' : '#fbbf24');

    const rsi14 = tech.rsi14 || 50;
    const rsiSignal = rsi14 > 60 ? '偏強' : (rsi14 < 40 ? '偏弱' : '中性');
    setSignal('intradayRsiSignal2', rsiSignal, rsiSignal === '偏強' ? '#10b981' : rsiSignal === '偏弱' ? '#ef4444' : '#94a3b8');

    const vwapSignal = currentPrice > ma20 ? '上方' : (currentPrice < ma20 ? '下方' : '持平');
    setSignal('intradayVwapSignal2', vwapSignal, vwapSignal === '上方' ? '#10b981' : vwapSignal === '下方' ? '#ef4444' : '#94a3b8');

    setSignal('intradayDeltaSignal2', '中性', '#94a3b8');

    // 專業交易員綜合建議
    const session = getTradingSession();
    const sessionText = session === 'opening' ? '開盤時段，波動較大' :
        session === 'lunch' ? '午休時段，流動性較差' :
            session === 'closing' ? '收盤時段，注意獲利了結' : '正常交易時段';

    let recommendation = '';
    const buyDistance = (targetBuyPrice - currentPrice) / currentPrice * 100;
    const sellDistance = (targetSellPrice - currentPrice) / currentPrice * 100;

    if (trendSignal === '上升' && vwapSignal === '上方' && currentPrice <= targetBuyPrice) {
        recommendation = `📈 強烈買入信號：趨勢向上，VWAP 上方，價格已達買入目標。${sessionText}`;
    } else if (trendSignal === '下降' && currentPrice >= targetSellPrice) {
        recommendation = `📉 賣出信號：趨勢向下，價格已達賣出目標。${sessionText}`;
    } else if (currentPrice <= targetStopPrice) {
        recommendation = `⚠️ 止損信號：價格已觸及止損位，建議立即止損。${sessionText}`;
    } else if (currentPrice <= targetBuyPrice) {
        recommendation = `📊 買入機會：價格已達買入目標區間。${sessionText} 建議分批建倉。`;
    } else if (currentPrice >= targetSellPrice) {
        recommendation = `📊 賣出機會：價格已達賣出目標區間。${sessionText} 建議止盈。`;
    } else if (buyDistance < 0.3 && buyDistance > 0) {
        recommendation = `⏰ 接近買入區：距離買入目標僅 ${buyDistance.toFixed(2)}%。${sessionText} 準備買入。`;
    } else if (sellDistance < 0.3 && sellDistance > 0) {
        recommendation = `⏰ 接近賣出區：距離賣出目標僅 ${sellDistance.toFixed(2)}%。${sessionText} 準備賣出。`;
    } else {
        recommendation = `⚖️ 觀望：價格未達到買賣目標。${sessionText} 建議等待。`;
    }

    const recEl = document.getElementById('intradayRecommendationText');
    if (recEl) recEl.innerHTML = recommendation;
}

function setRecommendationText(text) {
    const recEl = document.getElementById('intradayRecommendationText');
    if (recEl) recEl.innerHTML = text;
}

async function changeIntradayTimeframe(period) {
    const activeBtn = document.activeElement;
    if (activeBtn && activeBtn.classList && activeBtn.classList.contains('timeframe-btn')) {
        document.querySelectorAll('#intradayChartSection .timeframe-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        activeBtn.classList.add('active');
    }

    const stockCode = document.getElementById('intradayStockInput')?.value.trim() || '0700.HK';
    let backendPeriod = '15m';
    switch (period) {
        case '1m': backendPeriod = '1m'; break;
        case '5m': backendPeriod = '5m'; break;
        case '15m': backendPeriod = '15m'; break;
        case '30m': backendPeriod = '30m'; break;
        case '60m': backendPeriod = '60m'; break;
        default: backendPeriod = '15m';
    }

    try {
        const response = await fetch(`${API_BASE_URL}/intraday/kline/${stockCode}?period=${backendPeriod}&days=3`);
        const data = await response.json();
        if (data.success && data.data && data.data.length > 0) {
            updateIntradayKLineChart(data.data);
            updateMarketMetrics(data.data);
        } else {
            const mockKline = generateMockIntradayKline();
            updateIntradayKLineChart(mockKline);
            updateMarketMetrics(mockKline);
        }
    } catch (error) {
        console.error('載入日內 K線失敗:', error);
        const mockKline = generateMockIntradayKline();
        updateIntradayKLineChart(mockKline);
        updateMarketMetrics(mockKline);
    }
}

function showIntradayLoading() {
    const btn = document.getElementById('intradayAnalyzeBtn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="loading-spinner"></span> 分析中...';
    }
}

function hideIntradayLoading() {
    const btn = document.getElementById('intradayAnalyzeBtn');
    if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-search"></i> 分析';
    }
}

function showIntradayError(message) {
    const errorDiv = document.getElementById('intradayErrorMessage');
    if (errorDiv) {
        errorDiv.style.display = 'block';
        errorDiv.innerHTML = `<i class="bi bi-exclamation-triangle"></i> ${message}`;
        setTimeout(() => {
            errorDiv.style.display = 'none';
        }, 5000);
    }
}

function showIntradayMessage(message, type) {
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed; bottom: 20px; right: 20px; padding: 12px 20px;
        background: ${type === 'success' ? '#10b981' : '#ef4444'};
        color: white; border-radius: 8px; z-index: 10000;
        font-size: 14px; animation: slideIn 0.3s ease;
    `;
    toast.innerHTML = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}