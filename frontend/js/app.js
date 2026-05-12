// 定義 API 基礎路徑（避免重複聲明）
if (typeof API_BASE_URL === 'undefined') {
    var API_BASE_URL = '/api';
}

let currentStock = null;
let candleChart = null;
let bollingerData = null;
let currentStrategy = null;  // 新增：存储当前策略

document.addEventListener('DOMContentLoaded', function () {
    console.log('🚀 StockAI 系統啟動');
    analyzeStock();
    setupEventListeners();
});

function setupEventListeners() {
    const searchInput = document.getElementById('stockInput');
    if (searchInput) {
        searchInput.addEventListener('keypress', function (e) {
            if (e.key === 'Enter') {
                analyzeStock();
            }
        });
    }
}

async function analyzeStock() {
    const stockCode = document.getElementById('stockInput').value.trim() || '0700.HK';
    console.log('📊 分析股票:', stockCode);
    showLoading();

    try {
        console.log(`🔍 請求 URL: ${API_BASE_URL}/stock/${stockCode}`);
        const response = await fetch(`${API_BASE_URL}/stock/${stockCode}`);
        console.log('📡 狀態:', response.status, response.statusText);

        if (!response.ok) {
            console.error(`❌ HTTP 錯誤: ${response.status}`);
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const rawText = await response.text();
        console.log('📄 原始回應長度:', rawText.length);
        console.log('📄 原始回應前200字符:', rawText.substring(0, 200));

        if (!rawText || rawText.trim() === '') {
            throw new Error('伺服器返回空回應');
        }

        let data;
        try {
            data = JSON.parse(rawText);
        } catch (e) {
            console.error('❌ JSON 解析失敗:', e);
            console.error('原始回應內容:', rawText);
            throw new Error(`JSON 解析失敗: ${e.message}`);
        }

        if (data.success && data.data) {
            console.log('✅ 成功獲取數據, 股票:', data.data.symbol, '價格:', data.data.price);
            currentStock = data.data;

            updateStockDisplay(currentStock);
            updateIndicators(currentStock);
            updateRecommendation(currentStock);

            // 獲取歷史數據
            console.log(`🔍 獲取歷史數據: ${API_BASE_URL}/stock/${stockCode}/history?period=1mo`);
            try {
                const historyRes = await fetch(`${API_BASE_URL}/stock/${stockCode}/history?period=1mo`);
                const historyData = await historyRes.json();
                if (historyData.success && historyData.data && historyData.data.length > 0) {
                    console.log(`✅ 歷史數據獲取成功，共 ${historyData.data.length} 條`);
                    updateKLineChart(historyData.data);
                } else {
                    console.warn('⚠️ 無歷史數據，使用模擬數據');
                    generateMockKLineData();
                }
            } catch (historyError) {
                console.warn('⚠️ 獲取歷史數據失敗:', historyError.message);
                generateMockKLineData();
            }

            // 獲取 AI 預測（可选）
            try {
                const predictRes = await fetch(`${API_BASE_URL}/predict/${stockCode}`);
                const predictData = await predictRes.json();
                if (predictData.success && predictData.data) {
                    updateAIPredictionUI(predictData.data);
                    console.log('✅ AI預測數據獲取成功');
                }
            } catch (e) {
                console.warn('⚠️ AI 預測失敗:', e.message);
            }

            // 顯示 UI 區域
            const uiElements = ['stockHeader', 'chartSection', 'indicatorsGrid', 'recommendationBox'];
            uiElements.forEach(id => {
                const el = document.getElementById(id);
                if (el) el.style.display = 'block';
            });

            console.log('✅ 長線分析完成');
        } else {
            console.error('❌ API 返回失敗:', data);
            throw new Error(data.error || '無法獲取股票數據');
        }
    } catch (error) {
        console.error('❌ 分析失敗:', error);
        showErrorMessage('分析失敗: ' + error.message);
        useMockDataForDemo();
    } finally {
        hideLoading();
    }
}

function showElement(elementId) {
    const el = document.getElementById(elementId);
    if (el) el.style.display = 'block';
}

function showErrorMessage(message) {
    const errorDiv = document.getElementById('errorMessage');
    if (errorDiv) {
        errorDiv.style.display = 'block';
        errorDiv.innerHTML = `<i class="bi bi-exclamation-triangle"></i> ${message}`;
        setTimeout(() => {
            errorDiv.style.display = 'none';
        }, 5000);
    } else {
        console.error(message);
    }
}

function useMockDataForDemo() {
    const mockData = {
        symbol: '0700.HK',
        name: '騰訊控股有限公司',
        price: 380.00,
        prev_close: 378.50,
        change: 1.50,
        change_percent: 0.40,
        open: 379.00,
        high: 382.00,
        low: 378.00,
        volume: '15.0M',
        week_high: 420.00,
        week_low: 320.00,
        market_cap: 3500000000000,
        pe: 18.5,
        technicals: {
            ma5: 378.00, ma10: 376.50, ma20: 374.00, ma50: 365.00, ma200: 350.00,
            trend: '上升趨勢',
            rsi14: 55, rsi7: 52, rsi21: 58,
            macd_dif: 1.2, macd_dea: 0.8, macd_hist: 0.4,
            volume_ratio: 1.2, avg_volume_5: '12.0M',
            bb_upper: 390.00, bb_middle: 374.00, bb_lower: 358.00, bb_width: 8.5,
            atr: 5.50, adx: 28, di_plus: 25, di_minus: 20,
            kdj_k: 55, kdj_d: 50, kdj_j: 65,
            obv: '125.0M', obv_trend: '上升', obv_divergence: '無'
        }
    };

    currentStock = mockData;
    updateStockDisplay(mockData);
    updateIndicators(mockData);
    updateRecommendation(mockData);

    showElement('stockHeader');
    showElement('chartSection');
    showElement('indicatorsGrid');
    showElement('recommendationBox');

    generateMockKLineData();
}

function generateMockKLineData() {
    const data = [];
    const now = new Date();
    let basePrice = 380;

    for (let i = 0; i < 60; i++) {
        const date = new Date(now);
        date.setDate(now.getDate() - (60 - i));
        const change = (Math.random() - 0.5) * 8;
        const open = basePrice;
        const close = basePrice + change;
        const high = Math.max(open, close) + Math.random() * 3;
        const low = Math.min(open, close) - Math.random() * 3;
        data.push({ x: date.getTime(), y: [open, high, low, close] });
        basePrice = close;
    }
    renderCandlestickChart(data);
}

function formatPrice(price, symbol) {
    if (!price && price !== 0) return '--';
    if (symbol?.includes('BTC') || symbol?.includes('ETH')) return price.toFixed(0);
    if (price < 0.25) return price.toFixed(3);
    if (price < 0.5) return price.toFixed(3);
    if (price < 2) return price.toFixed(2);
    if (price < 5) return price.toFixed(2);
    if (price < 10) return price.toFixed(2);
    return price.toFixed(2);
}

function formatVolume(volume) {
    if (!volume) return '--';
    if (typeof volume === 'string') return volume;
    if (volume >= 1e9) return `${(volume / 1e9).toFixed(2)}B`;
    if (volume >= 1e6) return `${(volume / 1e6).toFixed(2)}M`;
    if (volume >= 1e3) return `${(volume / 1e3).toFixed(2)}K`;
    return volume.toString();
}

function formatMarketCap(value) {
    if (!value || value === 0 || value === '--' || value === null || value === 'N/A') return '--';
    const num = parseFloat(value);
    if (isNaN(num)) return '--';
    if (num >= 1e12) return `$${(num / 1e12).toFixed(2)}T`;
    if (num >= 1e9) return `$${(num / 1e9).toFixed(2)}B`;
    if (num >= 1e6) return `$${(num / 1e6).toFixed(2)}M`;
    return `$${num.toFixed(0)}`;
}

function setTextContent(elementId, text) {
    const el = document.getElementById(elementId);
    if (el) el.innerText = text;
}

function updateStockDisplay(data) {
    setTextContent('stockCode', data.symbol);
    setTextContent('stockName', data.name || data.symbol);
    setTextContent('currentPrice', `$${formatPrice(data.price, data.symbol)}`);

    const changeElement = document.getElementById('priceChange');
    if (changeElement) {
        const changeClass = (data.change || 0) >= 0 ? 'positive' : 'negative';
        changeElement.innerHTML = `${(data.change || 0) >= 0 ? '+' : ''}${(data.change || 0).toFixed(3)} (${data.change_percent || 0}%)`;
        changeElement.className = `price-sub ${changeClass}`;
    }

    setTextContent('openPrice', `$${formatPrice(data.open, data.symbol)}`);
    setTextContent('prevClose', `前收: $${formatPrice(data.prev_close || (data.price - (data.change || 0)), data.symbol)}`);
    setTextContent('dayRange', `$${formatPrice(data.low, data.symbol)} - $${formatPrice(data.high, data.symbol)}`);
    setTextContent('volume', `成交量: ${data.volume || '--'}`);
    setTextContent('weekRange', `$${formatPrice(data.week_low, data.symbol)} - $${formatPrice(data.week_high, data.symbol)}`);
    setTextContent('marketCap', `市值: ${formatMarketCap(data.market_cap)}`);

    const updateTimeEl = document.getElementById('updateTime');
    if (updateTimeEl) {
        updateTimeEl.innerHTML = `<i class="bi bi-clock"></i> <span>更新: ${new Date().toLocaleTimeString('zh-HK')}</span>`;
    }
}

function updateIndicators(data) {
    const tech = data.technicals || {};
    const price = data.price;
    const getVal = (val, defaultVal = '--') => (val !== undefined && val !== null) ? val : defaultVal;

    const maListEl = document.getElementById('maList');
    if (maListEl) {
        maListEl.innerHTML = `
            <div class="ma-item"><div class="ma-period">MA5</div><div class="ma-value">$${getVal(tech.ma5, price)}</div></div>
            <div class="ma-item"><div class="ma-period">MA10</div><div class="ma-value">$${getVal(tech.ma10, price)}</div></div>
            <div class="ma-item"><div class="ma-period">MA20</div><div class="ma-value">$${getVal(tech.ma20, price)}</div></div>
            <div class="ma-item"><div class="ma-period">MA50</div><div class="ma-value">$${getVal(tech.ma50, price)}</div></div>
            <div class="ma-item"><div class="ma-period">MA200</div><div class="ma-value">$${getVal(tech.ma200, price)}</div></div>
        `;
    }

    const trendSignal = document.getElementById('trendSignal');
    if (trendSignal) {
        const trend = tech.trend || (price > (tech.ma20 || price) ? '上升趨勢' : '下降趨勢');
        trendSignal.innerText = trend;
        trendSignal.className = `indicator-badge ${trend === '上升趨勢' ? 'badge-buy' : trend === '下降趨勢' ? 'badge-sell' : 'badge-neutral'}`;
    }

    setTextContent('rsiValue', getVal(tech.rsi14));
    setTextContent('rsi7', getVal(tech.rsi7));
    setTextContent('rsi21', getVal(tech.rsi21));

    const rsiMarker = document.getElementById('rsiMarker');
    if (rsiMarker) rsiMarker.style.left = (tech.rsi14 || 50) + '%';

    const rsiSignal = document.getElementById('rsiSignal');
    if (rsiSignal) {
        const rsi = tech.rsi14 || 50;
        if (rsi > 70) {
            rsiSignal.innerText = '超買區';
            rsiSignal.className = 'indicator-badge badge-sell';
        } else if (rsi < 30) {
            rsiSignal.innerText = '超賣區';
            rsiSignal.className = 'indicator-badge badge-buy';
        } else {
            rsiSignal.innerText = '中性區';
            rsiSignal.className = 'indicator-badge badge-neutral';
        }
    }

    setTextContent('macdDif', (tech.macd_dif || 0) > 0 ? `+${tech.macd_dif}` : tech.macd_dif);
    setTextContent('macdDea', (tech.macd_dea || 0) > 0 ? `+${tech.macd_dea}` : tech.macd_dea);
    setTextContent('macdHist', (tech.macd_hist || 0) > 0 ? `+${tech.macd_hist}` : tech.macd_hist);

    const macdCrossEl = document.getElementById('macdCross');
    if (macdCrossEl) {
        const macdCross = (tech.macd_dif || 0) > (tech.macd_dea || 0) ? '黃金交叉' : '死亡交叉';
        macdCrossEl.innerHTML = macdCross;
    }

    const macdSignal = document.getElementById('macdSignal');
    if (macdSignal) {
        if ((tech.macd_dif || 0) > (tech.macd_dea || 0) && (tech.macd_hist || 0) > 0) {
            macdSignal.innerText = '買入信號';
            macdSignal.className = 'indicator-badge badge-buy';
        } else if ((tech.macd_dif || 0) < (tech.macd_dea || 0) && (tech.macd_hist || 0) < 0) {
            macdSignal.innerText = '賣出信號';
            macdSignal.className = 'indicator-badge badge-sell';
        } else {
            macdSignal.innerText = '中性';
            macdSignal.className = 'indicator-badge badge-neutral';
        }
    }

    setTextContent('volumeToday', data.volume || '--');
    setTextContent('volumeAvg5', tech.avg_volume_5 || '--');
    setTextContent('volumeRatio', getVal(tech.volume_ratio));

    const volumeSignal = document.getElementById('volumeSignal');
    if (volumeSignal) {
        const ratio = tech.volume_ratio || 1;
        if (ratio > 1.5) {
            volumeSignal.innerText = '明顯放量';
            volumeSignal.className = 'indicator-badge badge-buy';
        } else if (ratio < 0.5) {
            volumeSignal.innerText = '明顯縮量';
            volumeSignal.className = 'indicator-badge badge-neutral';
        } else {
            volumeSignal.innerText = '正常';
            volumeSignal.className = 'indicator-badge badge-neutral';
        }
    }

    setTextContent('bbUpper', `$${getVal(tech.bb_upper, price * 1.02)}`);
    setTextContent('bbMiddle', `$${getVal(tech.bb_middle, price)}`);
    setTextContent('bbLower', `$${getVal(tech.bb_lower, price * 0.98)}`);
    setTextContent('bbWidth', `${getVal(tech.bb_width, 5)}%`);

    const bbSignal = document.getElementById('bbSignal');
    if (bbSignal) {
        const upper = tech.bb_upper || price * 1.02;
        const lower = tech.bb_lower || price * 0.98;
        const width = tech.bb_width || 5;
        if (price > upper) {
            bbSignal.innerText = '突破上軌';
            bbSignal.className = 'indicator-badge badge-sell';
        } else if (price < lower) {
            bbSignal.innerText = '跌破下軌';
            bbSignal.className = 'indicator-badge badge-buy';
        } else if (width < 10) {
            bbSignal.innerText = '通道收窄';
            bbSignal.className = 'indicator-badge badge-neutral';
        } else {
            bbSignal.innerText = '正常區間';
            bbSignal.className = 'indicator-badge badge-neutral';
        }
    }

    setTextContent('atrValue', `$${getVal(tech.atr, 0)}`);
    setTextContent('adxValue', getVal(tech.adx));
    setTextContent('diPlus', getVal(tech.di_plus));
    setTextContent('diMinus', getVal(tech.di_minus));

    const atrAdxSignal = document.getElementById('atrAdxSignal');
    if (atrAdxSignal) {
        const adx = tech.adx || 20;
        if (adx > 25) {
            atrAdxSignal.innerText = (tech.di_plus || 0) > (tech.di_minus || 0) ? '強趨勢上升' : '強趨勢下降';
            atrAdxSignal.className = (tech.di_plus || 0) > (tech.di_minus || 0) ? 'indicator-badge badge-buy' : 'indicator-badge badge-sell';
        } else if (adx < 20) {
            atrAdxSignal.innerText = '無趨勢';
            atrAdxSignal.className = 'indicator-badge badge-neutral';
        } else {
            atrAdxSignal.innerText = '中等趨勢';
            atrAdxSignal.className = 'indicator-badge badge-neutral';
        }
    }

    setTextContent('kdjK', getVal(tech.kdj_k));
    setTextContent('kdjD', getVal(tech.kdj_d));
    setTextContent('kdjJ', getVal(tech.kdj_j));

    const kdjSignal = document.getElementById('kdjSignal');
    const kdjActionEl = document.getElementById('kdjAction');
    const k = tech.kdj_k || 50;
    const d = tech.kdj_d || 50;
    const j = tech.kdj_j || 50;

    if (kdjSignal) {
        if (k > 80 && j > 80) {
            kdjSignal.innerText = '超買區';
            kdjSignal.className = 'indicator-badge badge-sell';
            if (kdjActionEl) { kdjActionEl.innerHTML = '賣出信號'; kdjActionEl.className = 'detail-value negative'; }
        } else if (k < 20 && j < 20) {
            kdjSignal.innerText = '超賣區';
            kdjSignal.className = 'indicator-badge badge-buy';
            if (kdjActionEl) { kdjActionEl.innerHTML = '買入信號'; kdjActionEl.className = 'detail-value positive'; }
        } else if (k > d) {
            kdjSignal.innerText = '黃金交叉';
            kdjSignal.className = 'indicator-badge badge-buy';
            if (kdjActionEl) { kdjActionEl.innerHTML = '買入'; kdjActionEl.className = 'detail-value positive'; }
        } else {
            kdjSignal.innerText = '中性區';
            kdjSignal.className = 'indicator-badge badge-neutral';
            if (kdjActionEl) { kdjActionEl.innerHTML = '觀望'; kdjActionEl.className = 'detail-value'; }
        }
    }

    setTextContent('obvValue', getVal(tech.obv));
    setTextContent('obvTrend', getVal(tech.obv_trend));

    const obvSignal = document.getElementById('obvSignal');
    const obvPriceRelationEl = document.getElementById('obvPriceRelation');
    const obvDivergenceEl = document.getElementById('obvDivergence');

    if (obvSignal) {
        const obvTrendVal = tech.obv_trend || '平穩';
        if (obvTrendVal === '上升' && (data.change || 0) > 0) {
            obvSignal.innerText = '量價齊升';
            obvSignal.className = 'indicator-badge badge-buy';
            if (obvPriceRelationEl) { obvPriceRelationEl.innerHTML = '價漲量增'; obvPriceRelationEl.className = 'detail-value positive'; }
        } else if (obvTrendVal === '下降' && (data.change || 0) < 0) {
            obvSignal.innerText = '量價齊跌';
            obvSignal.className = 'indicator-badge badge-sell';
            if (obvPriceRelationEl) { obvPriceRelationEl.innerHTML = '價跌量縮'; obvPriceRelationEl.className = 'detail-value negative'; }
        } else {
            obvSignal.innerText = '背離';
            obvSignal.className = 'indicator-badge badge-neutral';
            if (obvPriceRelationEl) { obvPriceRelationEl.innerHTML = '價量背離'; obvPriceRelationEl.className = 'detail-value'; }
        }
    }

    if (obvDivergenceEl) obvDivergenceEl.innerHTML = tech.obv_divergence || '無';
}

function updateRecommendation(data) {
    const tech = data.technicals || {};
    const price = data.price;
    let score = 50;

    if (price > (tech.ma5 || price) && (tech.ma5 || price) > (tech.ma20 || price)) score += 15;
    const rsi = tech.rsi14 || 50;
    if (rsi < 30) score += 15;
    else if (rsi > 70) score -= 10;
    else if (rsi > 50) score += 10;
    if ((tech.macd_dif || 0) > (tech.macd_dea || 0)) score += 15;
    score = Math.min(100, Math.max(0, Math.round(score)));

    setTextContent('totalScore', score);
    setTextContent('targetPrice', `$${Math.round(price * 1.15)}`);
    setTextContent('potentialGain', `+${Math.round((price * 1.15 - price) / price * 100)}%`);

    const signalTrend = document.getElementById('signalTrend');
    if (signalTrend) {
        const isBullish = price > (tech.ma5 || price);
        signalTrend.innerHTML = isBullish ? '買入' : '賣出';
        signalTrend.className = `signal-value ${isBullish ? 'positive' : 'negative'}`;
    }

    const signalRsi = document.getElementById('signalRsi');
    if (signalRsi) signalRsi.innerHTML = rsi > 50 ? '買入' : '賣出';

    const signalMacd = document.getElementById('signalMacd');
    if (signalMacd) signalMacd.innerHTML = (tech.macd_dif || 0) > (tech.macd_dea || 0) ? '買入' : '賣出';

    const signalVolume = document.getElementById('signalVolume');
    if (signalVolume) signalVolume.innerHTML = (tech.volume_ratio || 1) > 1 ? '積極' : '觀望';

    setTextContent('supportLevels', `$${tech.ma20 || price} (MA20) / $${tech.ma50 || price} (MA50)`);
    setTextContent('resistanceLevels', `$${Math.round(price * 1.05)} / $${data.week_high || price * 1.1}`);

    // ========== PE 估值分析（帶進度條）==========
    let peValue = data.pe !== undefined && data.pe !== null && data.pe !== 'N/A' ? data.pe : 'N/A';
    let peAnalysis = data.pe_analysis || null;

    let pePercentile = null;
    let peLevel = '合理';
    let peDesc = '';
    let peAdvice = '';
    let historicalCount = 0;

    if (peAnalysis && peValue !== 'N/A') {
        pePercentile = peAnalysis.percentile;
        peLevel = peAnalysis.level;
        peDesc = peAnalysis.description;
        historicalCount = peAnalysis.historical_count;

        if (peLevel === '偏低') {
            peAdvice = '✅ 估值吸引，建議關注買入機會';
        } else if (peLevel === '偏高') {
            peAdvice = '⚠️ 估值偏高，注意風險控制';
        } else {
            peAdvice = '🔍 估值合理，持有觀望';
        }
    } else if (peValue !== 'N/A') {
        // 如果沒有真實數據，使用模擬數據
        let peMin = 8;
        let peMax = 25;
        pePercentile = Math.min(95, Math.max(5, ((peValue - peMin) / (peMax - peMin)) * 100));
        if (pePercentile > 70) {
            peLevel = "偏高";
            peDesc = `當前 PE ${peValue}倍，高於 ${Math.round(pePercentile)}% 嘅歷史數據，估值偏貴，注意風險`;
            peAdvice = '⚠️ 估值偏高，注意風險控制';
        } else if (pePercentile < 30) {
            peLevel = "偏低";
            peDesc = `當前 PE ${peValue}倍，低於 ${Math.round(100 - pePercentile)}% 嘅歷史數據，估值吸引，買入機會`;
            peAdvice = '✅ 估值吸引，建議關注買入機會';
        } else {
            peLevel = "合理";
            peDesc = `當前 PE ${peValue}倍，處於歷史 ${Math.round(pePercentile)}% 位置，估值合理，持有觀望`;
            peAdvice = '🔍 估值合理，持有觀望';
        }
    }

    // 更新 PE 估值 UI
    const peValueEl = document.getElementById('peValue');
    if (peValueEl) peValueEl.innerHTML = `PE ${peValue}倍`;

    const peLevelBadge = document.getElementById('peLevelBadge');
    if (peLevelBadge) {
        peLevelBadge.innerHTML = peLevel === '偏低' ? '💰 估值吸引' : peLevel === '偏高' ? '⚠️ 估值偏高' : '📊 估值合理';
        peLevelBadge.className = `badge ${peLevel === '偏低' ? 'badge-buy' : peLevel === '偏高' ? 'badge-sell' : 'badge-neutral'}`;
    }

    const peMarker = document.getElementById('peMarker');
    if (peMarker && pePercentile !== null) {
        peMarker.style.left = `${pePercentile}%`;
    }

    const peLevelText = document.getElementById('peLevelText');
    if (peLevelText) {
        peLevelText.innerHTML = peLevel === '偏低' ? '📉 便宜區' : peLevel === '偏高' ? '📈 昂貴區' : '📊 合理區';
        peLevelText.style.color = peLevel === '偏低' ? '#10b981' : peLevel === '偏高' ? '#ef4444' : '#fbbf24';
    }

    const pePercentileEl = document.getElementById('pePercentile');
    if (pePercentileEl && pePercentile !== null) {
        pePercentileEl.innerHTML = `歷史百分位: ${Math.round(pePercentile)}%`;
        pePercentileEl.style.color = peLevel === '偏低' ? '#10b981' : peLevel === '偏高' ? '#ef4444' : '#fbbf24';
    }

    const peDescriptionEl = document.getElementById('peDescription');
    if (peDescriptionEl) {
        peDescriptionEl.innerHTML = `<span style="font-size: 12px; color: #99aabc;">${peDesc || '估值數據分析中...'}</span>`;
        if (historicalCount > 0) {
            peDescriptionEl.innerHTML += `<span style="font-size: 11px; color: #99aabc; display: block; margin-top: 4px;">📊 基於 ${historicalCount} 個歷史數據點</span>`;
        }
    }

    const peAdviceEl = document.getElementById('peAdvice');
    if (peAdviceEl) {
        peAdviceEl.innerHTML = `<span class="badge ${peLevel === '偏低' ? 'badge-buy' : peLevel === '偏高' ? 'badge-sell' : 'badge-neutral'}" style="font-size: 12px; display: inline-block;">${peAdvice || '估值分析中'}</span>`;
    }

    setTextContent('investmentAdvice', score >= 70 ? '分批建倉，5-8%倉位' : '觀望為主，控制風險');

    let recommendation = '';
    let recColorClass = '';
    if (score >= 80) {
        recommendation = '📈 強烈買入信號：多項技術指標顯示強勢，建議積極關注。';
        recColorClass = 'positive';
    } else if (score >= 60) {
        recommendation = '📊 買入信號：技術面向好，可考慮分批建倉。';
        recColorClass = 'positive';
    } else if (score >= 40) {
        recommendation = '⚖️ 中性觀望：指標信號混亂，建議等待明確趨勢。';
        recColorClass = '';
    } else {
        recommendation = '📉 賣出信號：多項指標轉弱，建議減倉觀望。';
        recColorClass = 'negative';
    }

    const recText = document.getElementById('recommendationText');
    if (recText) {
        const statusText = score >= 70 ? '<span class="positive">技術面強勢，建議積極關注</span>' : score < 50 ? '<span class="negative">技術面偏弱，建議謹慎</span>' : '技術面中性，建議觀望';
        recText.innerHTML = `
            <strong>${data.name || data.symbol} (${data.symbol})</strong> - ${statusText}<br><br>
            <span class="${recColorClass}">${recommendation}</span><br><br>
            <span style="color: #99aabc;">• 支撐位：$${tech.ma20 || price} / $${tech.ma50 || price}</span><br>
            <span style="color: #99aabc;">• 阻力位：$${Math.round(price * 1.05)} / ${data.week_high || price * 1.1}</span><br>
            <span style="color: #99aabc;">• RSI：${rsi} (${rsi > 70 ? '超買' : rsi < 30 ? '超賣' : '正常'})</span><br>
            <span style="color: #99aabc;">• MACD：${(tech.macd_dif || 0) > (tech.macd_dea || 0) ? '黃金交叉' : '死亡交叉'}</span>
        `;
    }
}

function updateKLineChart(klineData) {
    renderCandlestickChart(klineData);
    const stockCode = document.getElementById('stockInput').value.trim() || '0700.HK';
    setTimeout(() => loadBollingerBands(stockCode, klineData), 500);
}

async function loadBollingerBands(symbol, klineData) {
    try {
        const response = await fetch(`${API_BASE_URL}/stock/${symbol}/bb?period=1mo`);
        const data = await response.json();
        if (data.success && data.upper && data.upper.length > 0) {
            console.log('✅ 布林帶數據獲取成功');
            bollingerData = {
                upper: data.upper.map((y, i) => ({ x: data.timestamps[i], y: y })),
                middle: data.middle.map((y, i) => ({ x: data.timestamps[i], y: y })),
                lower: data.lower.map((y, i) => ({ x: data.timestamps[i], y: y }))
            };
            if (klineData) renderCandlestickChart(klineData);
        }
    } catch (error) {
        console.error('載入保力加通道失敗:', error);
    }
}

function renderCandlestickChart(klineData) {
    const chartElement = document.querySelector("#candlestickChart");
    if (!chartElement) {
        console.error('找不到 candlestickChart 元素');
        return;
    }

    const candleData = klineData.map(item => ({ x: item.x, y: item.y }));
    const series = [{ name: 'K線', type: 'candlestick', data: candleData }];

    if (bollingerData && bollingerData.upper && bollingerData.upper.length > 0) {
        series.push({ name: '上軌 (+2σ)', data: bollingerData.upper, type: 'line', color: '#10b981' });
        series.push({ name: '中軌 (MA20)', data: bollingerData.middle, type: 'line', color: '#3b82f6' });
        series.push({ name: '下軌 (-2σ)', data: bollingerData.lower, type: 'line', color: '#ef4444' });
    }

    const options = {
        series: series,
        chart: {
            type: 'candlestick',
            height: 400,
            background: 'transparent',
            foreColor: '#f8fafc',
            toolbar: { show: true, tools: { download: true, selection: true, zoom: true, pan: true, reset: true } }
        },
        plotOptions: { candlestick: { colors: { upward: '#10b981', downward: '#ef4444' }, wick: { useFillColor: true } } },
        xaxis: { type: 'datetime', labels: { style: { colors: '#f8fafc' }, format: 'dd MMM', rotate: -45 } },
        yaxis: { labels: { style: { colors: '#f8fafc' }, formatter: (v) => `$${v.toFixed(2)}` } },
        grid: { borderColor: '#334155' },
        tooltip: { theme: 'dark' }
    };

    if (candleChart) candleChart.destroy();
    candleChart = new ApexCharts(chartElement, options);
    candleChart.render();
}

async function changeTimeframe(period) {
    const btns = document.querySelectorAll('.timeframe-btn');
    btns.forEach(btn => btn.classList.remove('active'));
    if (event && event.target) event.target.classList.add('active');

    const stockCode = document.getElementById('stockInput').value.trim() || '0700.HK';
    const backendPeriod = { '1d': '1d', '5d': '5d', '1mo': '1mo', '3mo': '3mo', '1y': '1y' }[period] || '1mo';

    try {
        const response = await fetch(`${API_BASE_URL}/stock/${stockCode}/history?period=${backendPeriod}`);
        const data = await response.json();
        if (data.success && data.data && data.data.length > 0) {
            bollingerData = null;
            updateKLineChart(data.data);
        }
    } catch (error) {
        console.error('載入 K線失敗:', error);
        generateMockKLineData();
    }
}

function updateAIPredictionUI(prediction) {
    const container = document.getElementById('aiPredictionContainer');
    if (!container) return;

    let modelsHtml = '';
    if (prediction.models && prediction.models.length > 0) {
        modelsHtml = prediction.models.map(model => {
            const signalClass = model.signal === '買入' ? 'badge-buy' : model.signal === '賣出' ? 'badge-sell' : 'badge-neutral';
            return `<div style="background:rgba(0,0,0,0.2);border-radius:12px;padding:12px;margin-bottom:8px;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div><span style="font-weight:600;">${model.name}</span><span style="color:#99aabc;font-size:12px;margin-left:8px;">${model.detail || ''}</span></div>
                    <div><span class="badge ${signalClass}">${model.signal}</span><span style="margin-left:8px;">${model.score}/100</span></div>
                </div>
            </div>`;
        }).join('');
    } else {
        modelsHtml = '<div style="color:#99aabc;text-align:center;padding:20px;">AI預測數據載入中...</div>';
    }

    container.innerHTML = `
        <div style="margin-top:20px;border-top:1px solid var(--border-color);padding-top:20px;">
            <div style="font-size:16px;font-weight:600;margin-bottom:15px;"><i class="bi bi-robot"></i> AI 多模型預測</div>
            ${modelsHtml}
        </div>
    `;
    container.style.display = 'block';
}

function quickSearch(code) {
    const input = document.getElementById('stockInput');
    if (input) input.value = code;
    analyzeStock();
}

function showLoading() {
    const btn = document.getElementById('analyzeBtn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="loading-spinner"></span> 分析中...';
    }
}

function hideLoading() {
    const btn = document.getElementById('analyzeBtn');
    if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-search"></i> 智能分析';
    }
}

// ==================== DeepSeek AI 助手功能 ====================

let aiExpanded = false;

function toggleAIAssistant() {
    const minimized = document.getElementById('aiMinimized');
    const expanded = document.getElementById('aiExpanded');

    if (aiExpanded) {
        minimized.style.display = 'flex';
        expanded.style.display = 'none';
    } else {
        minimized.style.display = 'none';
        expanded.style.display = 'flex';
        // 自动显示当前股票名称
        const stockName = document.getElementById('stockName')?.innerText ||
            document.getElementById('intradayStockName')?.innerText ||
            '当前股票';
        document.getElementById('aiCurrentStock').innerText = stockName;
    }
    aiExpanded = !aiExpanded;
}

function closeAIAssistant() {
    document.getElementById('aiMinimized').style.display = 'flex';
    document.getElementById('aiExpanded').style.display = 'none';
    aiExpanded = false;
}

function handleAIKeyPress(event) {
    if (event.key === 'Enter') {
        askAI();
    }
}

function addMessage(role, text) {
    const messagesDiv = document.getElementById('aiChatMessages');
    if (!messagesDiv) return;

    const messageDiv = document.createElement('div');
    messageDiv.className = `ai-message ai-message-${role}`;

    const avatar = role === 'bot' ? '🤖' : '👤';
    const name = role === 'bot' ? 'DeepSeek AI' : '您';

    messageDiv.innerHTML = `
        <div class="ai-avatar">${avatar}</div>
        <div class="ai-content">
            <div class="ai-name">${name}</div>
            <div class="ai-text">${text.replace(/\n/g, '<br>')}</div>
        </div>
    `;

    messagesDiv.appendChild(messageDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

async function askAI() {
    const input = document.getElementById('aiQuestion');
    if (!input) return;

    const question = input.value.trim();
    if (!question) return;

    addMessage('user', question);
    input.value = '';

    const loadingDiv = document.getElementById('aiLoading');
    if (loadingDiv) loadingDiv.style.display = 'flex';

    // 获取当前股票代码（优先长线，其次日内）
    let stockCode = document.getElementById('stockInput')?.value.trim() ||
        document.getElementById('intradayStockInput')?.value.trim() ||
        '0700.HK';

    try {
        const response = await fetch(`${API_BASE_URL}/ai/analyze/${stockCode}?q=${encodeURIComponent(question)}`);
        const data = await response.json();

        if (loadingDiv) loadingDiv.style.display = 'none';

        if (data.success && data.data) {
            addMessage('bot', data.data.analysis);
        } else {
            addMessage('bot', '抱歉，分析失败，请稍后重试。');
        }
    } catch (error) {
        if (loadingDiv) loadingDiv.style.display = 'none';
        console.error('AI 分析失败:', error);
        addMessage('bot', '网络错误，请检查后端服务。');
    }
}

function quickAsk(type) {
    const questions = {
        '操作建议': '请根据当前技术指标给出具体的操作建议',
        '支撑位': '当前股票的支撑位在哪里？',
        '目标价': '建议的目标价是多少？',
        '风险提示': '当前股票有什么风险需要注意？',
        'RSI指标怎么看？': '请解读当前RSI指标并给出交易建议',
        'MACD信号': '请解读当前MACD信号并给出交易建议',
        '布林带解读': '请解读当前布林带指标并给出交易建议',
        'KDJ分析': '请解读当前KDJ指标并给出交易建议'
    };

    const question = questions[type] || type;
    const input = document.getElementById('aiQuestion');
    if (input) {
        input.value = question;
        askAI();
    }
}

// ==================== 港交所财务报告功能 (v1.6D新增) ====================

// 获取财务报告
async function fetchFinancialReport(reportType = 'annual') {
    const reportArea = document.getElementById('financialReportArea');
    const reportContent = document.getElementById('financialReportContent');
    
    if (!reportArea || !reportContent) {
        console.error('财务报表区域未找到');
        return;
    }
    
    // 获取当前股票代码
    let stockCode = document.getElementById('stockInput')?.value.trim() ||
        document.getElementById('intradayStockInput')?.value.trim() ||
        '0700.HK';
    
    // 显示加载状态
    reportArea.style.display = 'block';
    reportContent.innerHTML = '<div class="ai-loading" style="display: flex;"><div class="ai-typing"><span></span><span></span><span></span></div><span>正在获取财务数据...</span></div>';
    
    try {
        const response = await fetch(`${API_BASE_URL}/hkex/financial/${stockCode}?type=${reportType}`);
        const data = await response.json();
        
        if (data.success && data.data) {
            renderFinancialReport(data.data, reportContent);
        } else {
            reportContent.innerHTML = `<div style="padding: 10px; color: #ef4444;">⚠️ ${data.error || '无法获取财务数据'}</div>`;
        }
    } catch (error) {
        console.error('获取财务报告失败:', error);
        reportContent.innerHTML = '<div style="padding: 10px; color: #ef4444;">⚠️ 网络错误，请检查后端服务</div>';
    }
}

// 渲染财务报告内容
function renderFinancialReport(data, container) {
    if (!data || data.length === 0) {
        container.innerHTML = '<div style="padding: 10px; color: #99aabc;">暂无财务报告数据</div>';
        return;
    }
    
    let html = '';
    
    // 检查数据类型 - 新格式包含source字段
    if (Array.isArray(data)) {
        // 遍历所有数据源
        for (const item of data) {
            if (item.source === 'demo' || item.note) {
                // 提示信息
                html += `
                    <div style="background: rgba(255,193,7,0.1); border: 1px solid rgba(255,193,7,0.3); border-radius: 8px; padding: 12px; margin-bottom: 10px;">
                        <div style="color: #ffc107; font-size: 12px;">⚠️ ${item.note || '数据获取提示'}</div>
                        <div style="color: #99aabc; font-size: 11px; margin-top: 8px;">${item.suggestion || ''}</div>
                    </div>
                `;
                continue;
            }
            
            if (item.source === 'eastmoney' && item.data && Array.isArray(item.data)) {
                // 东方财富公告格式
                html += '<div style="display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px;">';
                html += '<div style="font-size: 11px; color: #a78bfa;">📢 财务公告</div>';
                item.data.slice(0, 6).forEach(ann => {
                    html += `
                        <div style="background: rgba(255,255,255,0.05); border-radius: 8px; padding: 10px;">
                            <div style="font-size: 12px; color: #e2e8f0; margin-bottom: 4px;">${ann.title || ''}</div>
                            <div style="font-size: 11px; color: #99aabc;">
                                <span style="color: #a78bfa;">📅 ${ann.date || ''}</span>
                            </div>
                        </div>
                    `;
                });
                html += '</div>';
            }
            
            if (item.source === 'yahoo' && item.data && Array.isArray(item.data)) {
                // Yahoo Finance格式
                const finData = item.data[0];
                if (finData && finData.data) {
                    const fin = finData.data;
                    html += '<div style="margin-bottom: 10px;">';
                    html += '<div style="font-size: 11px; color: #10b981; margin-bottom: 8px;">📊 财务数据 (Yahoo)</div>';
                    html += '<div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px;">';
                    
                    const finItems = [
                        ['总收入', fin.totalRevenue],
                        ['净利润', fin.netIncome],
                        ['毛利润', fin.grossProfit],
                        ['营业收入', fin.operatingIncome],
                        ['EBITDA', fin.ebitda],
                        ['总资产', fin.totalAssets],
                        ['总负债', fin.totalLiabilities],
                        ['现金', fin.cash]
                    ];
                    
                    finItems.forEach(([label, val]) => {
                        if (val) html += createFinItem(label, formatNumber(val));
                    });
                    
                    html += '</div></div>';
                }
            }
        }
        
        // 如果没有有效数据
        if (!html || html === '') {
            html = '<div style="padding: 10px; color: #99aabc;">暂无可用数据，请稍后重试</div>';
        }
    } else {
        html = '<div style="padding: 10px; color: #99aabc;">暂无可用数据</div>';
    }
    
    container.innerHTML = html;
}

// 创建财务项HTML
function createFinItem(label, value, changePercent = null) {
    const num = parseFloat(String(value).replace(/[^0-9.-]/g, ''));
    // 默认使用中性颜色
    let color = '#cbd5e1';
    
    // 如果有变化百分比，根据变化显示颜色
    let changeHtml = '';
    if (changePercent !== null && !isNaN(changePercent)) {
        const changeColor = changePercent > 0 ? '#10b981' : (changePercent < 0 ? '#ef4444' : '#99aabc');
        const changeIcon = changePercent > 0 ? '↑' : (changePercent < 0 ? '↓' : '-');
        changeHtml = `<div style="font-size: 11px; color: ${changeColor}; margin-top: 4px;">${changeIcon} ${Math.abs(changePercent).toFixed(2)}%</div>`;
    }
    
    return `
        <div style="background: rgba(255,255,255,0.05); border-radius: 8px; padding: 10px;">
            <div style="font-size: 11px; color: #99aabc;">${label}</div>
            <div style="font-size: 14px; font-weight: 600; color: ${color};">${value}</div>
            ${changeHtml}
        </div>
    `;
}

// 格式化数字
function formatNumber(num) {
    if (!num && num !== 0) return '--';
    if (num >= 1e12) return (num / 1e12).toFixed(2) + '万亿';
    if (num >= 1e8) return (num / 1e8).toFixed(2) + '亿';
    if (num >= 1e4) return (num / 1e4).toFixed(2) + '万';
    return num.toFixed(2);
}

// 获取财务比率
async function fetchFinancialRatios() {
    const reportArea = document.getElementById('financialReportArea');
    const reportContent = document.getElementById('financialReportContent');
    
    if (!reportArea || !reportContent) {
        console.error('财务报表区域未找到');
        return;
    }
    
    let stockCode = document.getElementById('stockInput')?.value.trim() ||
        document.getElementById('intradayStockInput')?.value.trim() ||
        '0700.HK';
    
    reportArea.style.display = 'block';
    reportContent.innerHTML = '<div class="ai-loading" style="display: flex;"><div class="ai-typing"><span></span><span></span><span></span></div><span>正在获取财务数据...</span></div>';
    
    try {
        const response = await fetch(`${API_BASE_URL}/hkex/summary/${stockCode}`);
        const data = await response.json();
        
        if (data.success && data.annual?.data) {
            const annualData = data.annual.data;
            const ratios = annualData.ratios || annualData[0]?.ratios;
            const indicatorHistory = annualData.indicator_history || annualData[0]?.indicator_history;
            
            if (ratios) {
                // 添加数据源信息
                let sourceInfo = '';
                if (data.is_local) {
                    const ageText = data.data_age_days ? `(${data.data_age_days}天前)` : '';
                    const valuationSource = ratios._valuation_source ? ` | 估值: ${ratios._valuation_source}` : '';
                    sourceInfo = `<div style="font-size: 11px; color: #10b981; margin-bottom: 12px; padding: 6px 10px; background: rgba(16,185,129,0.1); border-radius: 6px; display: flex; align-items: center; gap: 6px;">
                        <span>✓</span>
                        <span>港交所披露易（本地缓存）${ageText}${valuationSource}</span>
                    </div>`;
                } else if (data.source) {
                    sourceInfo = `<div style="font-size: 11px; color: #60a5fa; margin-bottom: 12px;">数据来源: ${data.source}</div>`;
                }
                
                renderFinancialRatios(ratios, reportContent, indicatorHistory);
                
                // 在内容前插入数据源信息
                if (sourceInfo) {
                    reportContent.insertAdjacentHTML('afterbegin', sourceInfo);
                }
            } else {
                reportContent.innerHTML = '<div style="padding: 10px; color: #99aabc;">暂无财务比率数据</div>';
            }
        } else {
            reportContent.innerHTML = `<div style="padding: 10px; color: #ef4444;">⚠️ ${data.error || '无法获取财务比率'}</div>`;
        }
    } catch (error) {
        console.error('获取财务比率失败:', error);
        reportContent.innerHTML = '<div style="padding: 10px; color: #ef4444;">⚠️ 网络错误</div>';
    }
}

// 渲染财务比率 - 增强版
function renderFinancialRatios(ratios, container, indicatorHistory = null) {
    if (!ratios) {
        container.innerHTML = '<div style="padding: 10px; color: #99aabc;">暂无数据</div>';
        return;
    }
    
    // 智能格式化百分比数值
    function formatPercent(value) {
        if (value === undefined || value === null) return null;
        const num = parseFloat(String(value).replace(/%/g, ''));
        if (isNaN(num)) return null;
        // 如果绝对值 > 1，认为已经是百分比形式（如30.57 → "30.57%"）
        // 如果绝对值 ≤ 1，认为是小数形式（如0.3057 → "30.57%"）
        const percentValue = Math.abs(num) > 1 ? num : num * 100;
        return percentValue.toFixed(2) + '%';
    }
    
    // 格式化倍数
    function formatMultiple(value) {
        if (value === undefined || value === null) return null;
        const num = parseFloat(value);
        if (isNaN(num)) return null;
        return num.toFixed(2) + 'x';
    }
    
    // 计算同比变化
    function getYoYChange(currentKey, history) {
        if (!history || history.length < 2) return null;
        const current = history[0];
        const previous = history[1];
        
        const currentVal = parseFloat(String(current[currentKey] || '0').replace(/[%亿万亿]/g, ''));
        const previousVal = parseFloat(String(previous[currentKey] || '0').replace(/[%亿万亿]/g, ''));
        
        if (isNaN(currentVal) || isNaN(previousVal) || previousVal === 0) return null;
        return ((currentVal - previousVal) / Math.abs(previousVal) * 100);
    }
    
    // 从 indicator_history 获取数据
    const latest = indicatorHistory && indicatorHistory[0] ? indicatorHistory[0] : {};
    const previous = indicatorHistory && indicatorHistory[1] ? indicatorHistory[1] : {};
    
    // 计算各项同比变化 - 为所有财务指标添加同比变化
    const roeChange = getYoYChange('ROE', indicatorHistory);
    const roaChange = getYoYChange('ROA', indicatorHistory);
    const grossMarginChange = getYoYChange('毛利率', indicatorHistory);
    const profitMarginChange = getYoYChange('净利率', indicatorHistory);
    const operatingMarginChange = getYoYChange('营业利润率', indicatorHistory);
    const debtRatioChange = getYoYChange('资产负债率', indicatorHistory);
    const currentRatioChange = getYoYChange('流动比率', indicatorHistory);
    const quickRatioChange = getYoYChange('速动比率', indicatorHistory);
    const revenueChange = getYoYChange('营业收入', indicatorHistory);
    const profitChange = getYoYChange('净利润', indicatorHistory);
    const epsChange = getYoYChange('EPS', indicatorHistory);
    const bpsChange = getYoYChange('每股净资产', indicatorHistory);
    const equityRatioChange = getYoYChange('产权比率', indicatorHistory);
    
    // 检查是否有估值指标
    const hasValuation = ratios.peRatio || ratios.priceToBook || ratios.priceToSales || ratios.forwardPE;
    
    // 检查是否为银行股
    const isBank = ratios._is_bank_stock === true;
    
    // 分类展示财务指标
    const categories = [
        {
            title: ratios._valuation_source ? `📊 估值指标 (${ratios._valuation_source})` : '📊 估值指标',
            icon: '💰',
            source: ratios._valuation_source ? '（数据来源：' + ratios._valuation_source + '）' : '',
            items: [
                { label: '市盈率 PE', value: ratios.peRatio, format: 'x', desc: '股价÷每股收益，越低越便宜。\n同业参考：互联网龙头15~25x，传统消费8~15x，科技成长25~40x' },
                { label: '前瞻 PE', value: ratios.forwardPE, format: 'x', desc: '基于未来盈利预测的市盈率，低于历史PE代表盈利预期增长。\n同业参考：前瞻PE < 历史PE为正面信号' },
                { label: '市净率 PB', value: ratios.priceToBook, format: 'x', desc: '股价÷每股净资产，<1倍为资产折价。\n同业参考：银行0.5~1x，消费品2~4x，科技3~8x' },
                { label: '市销率 PS', value: ratios.priceToSales, format: 'x', desc: '市值÷年度营收，适合亏损成长股估值。\n同业参考：互联网3~8x，SaaS5~15x，传统行业0.5~2x' }
            ]
        },
        {
            title: isBank ? '🏦 盈利能力（银行股）' : '💹 盈利能力',
            icon: '📈',
            items: [
                // 毛利率：银行股显示特殊说明，普通公司正常显示
                { 
                    label: '毛利率', 
                    value: isBank ? '不适用' : ratios.grossMargins, 
                    format: isBank ? 'bank_na' : '%', 
                    desc: isBank 
                        ? '银行主营业务为利息/非利息收入，无实体商品COGS，毛利率不适用。\n核心指标：净息差(NIM)是银行盈利能力参考'
                        : '（营收-成本）÷营收，越高竞争壁垒越强。\n同业参考：软件/平台>60%，消费品30~50%，制造业15~30%',
                    change: isBank ? null : grossMarginChange 
                },
                { label: '净利率', value: ratios.profitMargins, format: '%', desc: '扣除所有成本后真正赚到的比例，>15%属优质。\n同业参考：互联网20~35%，消费品10~20%，零售<5%', change: profitMarginChange },
                // 营业利润率：银行股显示为"税前利润率"（由TAX_EBT计算）
                { 
                    label: isBank ? '税前利润率' : '营业利润率', 
                    value: ratios.operatingMargins, 
                    format: '%', 
                    desc: isBank 
                        ? '银行股使用税前利润率（≈营业利润率），反映税前核心盈利能力。\n同业参考：银行税前利润率25~50%为正常水平'
                        : '营业利润÷营收，衡量核心经营盈利能力。\n同业参考：科技平台20~35%，消费品10~20%，制造业5~15%',
                    change: operatingMarginChange 
                },
                { label: 'ROE 净资产收益率', value: ratios.roe, format: '%', desc: '净利润÷净资产，巴菲特最看重指标，>15%为优质。\n同业参考：港股科技龙头15~25%，消费品10~20%，银行8~12%', change: roeChange },
                { label: 'ROA 总资产收益率', value: ratios.roa, format: '%', desc: '净利润÷总资产，衡量资产使用效率，>5%较好。\n同业参考：科技平台8~15%，消费品5~10%，银行<2%（正常）', change: roaChange }
            ]
        },
        {
            title: isBank ? '🏦 财务健康（银行高杠杆正常）' : '🏦 财务健康',
            icon: '🛡️',
            items: [
                { label: '资产负债率', value: ratios.debtRatio, format: '%', desc: isBank ? '银行高杠杆是正常商业模式，存款即负债。\n同业参考：银行90~95%为正常，>98%需关注' : '总负债÷总资产，越低越稳健，>80%高风险。\n同业参考：科技公司<40%，消费品40~60%，地产/银行天生高负债', change: debtRatioChange },
                { label: '产权比率', value: ratios.equityRatio, format: '%', desc: '负债÷股东权益，反映企业杠杆程度。\n同业参考：<100%为低杠杆，100~200%适中，>200%高杠杆', change: equityRatioChange },
                // 流动比率：银行股显示特殊说明，普通公司正常显示
                { 
                    label: '流动比率', 
                    value: isBank ? '不适用' : ratios.currentRatio, 
                    format: isBank ? 'bank_na' : 'raw', 
                    desc: isBank 
                        ? '银行流动性依赖存贷比/LCR等监管指标，传统流动比率不适用。\n核心参考：流动性覆盖率(LCR)>100%为监管要求'
                        : '流动资产÷流动负债，>1.5为健康，<1有流动性风险。\n同业参考：制造业1.5~2.5，零售1.0~1.5，科技>2.0', 
                    change: isBank ? null : currentRatioChange 
                },
                // 速动比率：银行股显示特殊说明，普通公司正常显示
                { 
                    label: '速动比率', 
                    value: isBank ? '不适用' : ratios.quickRatio, 
                    format: isBank ? 'bank_na' : 'raw', 
                    desc: isBank 
                        ? '银行速动比率无参考意义，流动性覆盖率(LCR)是银行核心指标。\n同业参考：LCR>100%为监管要求'
                        : '（流动资产-存货）÷流动负债，更严格的偿债指标，≥1为安全。\n同业参考：科技/服务业>1.5，制造业0.8~1.2', 
                    change: isBank ? null : quickRatioChange 
                }
            ]
        },
        {
            title: '📈 成长性',
            icon: '🚀',
            items: [
                { label: '营收同比', value: ratios.revenueGrowth || latest['营收同比'], format: '%', desc: '营业收入年增长率，>15%为快速增长。\n同业参考：互联网龙头10~20%，成熟消费品5~10%，高增长科技>25%', change: revenueChange },
                { label: '净利润同比', value: ratios.earningsGrowth || latest['净利润同比'], format: '%', desc: '净利润年增长率，>10%良好，>25%高速。\n同业参考：港科技龙头10~20%，消费品5~15%；利润增长>营收=盈利质量提升', change: profitChange },
                { label: '营业利润同比', value: ratios.operatingProfitGrowth, format: '%', desc: '核心业务利润增长，排除非经常损益影响。\n同业参考：与净利润同比对比，可判断盈利质量', change: null },
                { label: 'EPS同比', value: ratios.epsGrowth, format: '%', desc: '每股收益年增长率，反映股东权益增长能力。\n同业参考：EPS持续增长是股价长期上涨的根本动力', change: epsChange }
            ]
        },
        {
            title: '💵 股东回报',
            icon: '🎁',
            items: [
                { label: '每股收益 EPS', value: ratios._isUsdReport && ratios.epsUsd ? ratios.epsUsd : latest['EPS'], format: 'raw', desc: ratios._isUsdReport ? '净利润÷总股本(USD)，汇丰等美元财报公司。\n同业参考：港股蓝筹EPS逐年增长为优质，EPS×PE验证当前股价是否合理' : '净利润÷总股本，持续增长是股价上涨根本动力。\n同业参考：港股蓝筹EPS逐年增长为优质，EPS×PE验证当前股价是否合理', change: epsChange, unit: ratios._isUsdReport ? ' USD' : '' },
                { label: '每股净资产 BPS', value: ratios._isUsdReport && ratios.bpsUsd ? ratios.bpsUsd : latest['每股净资产'], format: 'raw', desc: ratios._isUsdReport ? '净资产÷总股本(USD)，汇丰等美元财报公司。\n同业参考：结合PB使用，BPS稳步增长说明公司真实财富在积累' : '净资产÷总股本，股价<BPS即PB<1为资产折价。\n同业参考：结合PB使用，BPS稳步增长说明公司真实财富在积累', change: bpsChange, unit: ratios._isUsdReport ? ' USD' : '' },
                { label: '股息率', value: ratios.dividendYield, format: '%', desc: '年派息÷股价，>3%为高息股，>5%需确认可持续性。\n同业参考：港股高息蓝筹3~6%，内银股4~8%，成长股<1%', change: null },
                { label: '派息率', value: ratios.payoutRatio, format: '%', desc: '股息÷净利润，50~80%为慷慨派息，>100%不可持续。\n同业参考：港股成熟蓝筹40~60%，内地科技<30%（留资再投资）', change: null }
            ]
        }
    ];
    
    let html = '<div class="financial-ratios-container" style="max-height: 500px; overflow-y: auto;">';
    
    categories.forEach(category => {
        // 过滤出有数据的项（包含银行股"不适用"标记）
        const validItems = category.items.filter(item => {
            const val = item.value;
            // 银行股特殊值 "不适用" 也显示（用不同样式）
            if (val === '不适用' || val === 'N/A') return true;
            return val !== undefined && val !== null && val !== '' && !isNaN(parseFloat(String(val).replace(/[%亿万亿x]/g, '')));
        });
        
        if (validItems.length === 0) return;
        
        html += `
            <div class="fin-category" style="margin-bottom: 16px;">
                <div style="font-size: 13px; font-weight: 600; color: #60a5fa; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                    <span>${category.icon}</span>
                    <span>${category.title}</span>
                </div>
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px;">
        `;
        
        validItems.forEach(item => {
            let displayValue;
            if (item.format === 'x') {
                displayValue = formatMultiple(item.value);
            } else if (item.format === '%') {
                displayValue = formatPercent(item.value);
            } else if (item.format === 'bank_na') {
                // 银行股"不适用"显示为灰色标注
                displayValue = '<span style="color: #9ca3af; font-size: 12px;">不适用</span>';
            } else {
                displayValue = item.value;
            }
            html += createFinItemV2(item.label, displayValue, item.desc, item.change, item.unit);
        });
        
        html += '</div></div>';
    });
    
    html += '</div>';
    
    // 添加AI财务健康评分
    const healthScore = calculateFinancialHealth(ratios, indicatorHistory);
    if (healthScore) {
        html += `
            <div class="fin-health-score" style="margin-top: 16px; padding: 12px; background: linear-gradient(135deg, ${healthScore.gradient} 0%, rgba(30,41,59,0.9) 100%); border-radius: 12px; border: 1px solid ${healthScore.borderColor};">
                <div style="display: flex; align-items: center; justify-content: space-between;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <div style="font-size: 28px;">${healthScore.emoji}</div>
                        <div>
                            <div style="font-size: 12px; color: #99aabc; margin-bottom: 2px;">AI 财务健康评分</div>
                            <div style="font-size: 20px; font-weight: 700; color: ${healthScore.color};">${healthScore.score}<span style="font-size: 12px; color: #99aabc;">/100</span></div>
                        </div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 14px; font-weight: 600; color: ${healthScore.color};">${healthScore.rating}</div>
                        <div style="font-size: 10px; color: #99aabc; max-width: 150px; margin-top: 4px;">${healthScore.comment}</div>
                    </div>
                </div>
                <div style="margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap;">
                    ${healthScore.strengths.map(s => `<span style="font-size: 10px; padding: 3px 8px; background: rgba(16,185,129,0.15); color: #10b981; border-radius: 4px;">✓ ${s}</span>`).join('')}
                    ${healthScore.warnings.map(w => `<span style="font-size: 10px; padding: 3px 8px; background: rgba(245,158,11,0.15); color: #f59e0b; border-radius: 4px;">! ${w}</span>`).join('')}
                </div>
            </div>
        `;
    }
    
    container.innerHTML = html;
}

// 计算财务健康评分
function calculateFinancialHealth(ratios, history) {
    if (!ratios) return null;
    
    let score = 50; // 基础分
    const strengths = [];
    const warnings = [];
    
    // ROE 评分 (优秀 >20%, 良好 15-20%, 一般 10-15%)
    const roe = parseFloat(ratios.roe || 0);
    if (roe > 20) {
        score += 15;
        strengths.push('ROE优秀');
    } else if (roe > 15) {
        score += 10;
        strengths.push('ROE良好');
    } else if (roe > 10) {
        score += 5;
    } else if (roe < 5) {
        score -= 10;
        warnings.push('ROE偏低');
    }
    
    // 毛利率评分
    const grossMargin = parseFloat(ratios.grossMargins || 0);
    if (grossMargin > 50) {
        score += 10;
        strengths.push('高毛利');
    } else if (grossMargin > 30) {
        score += 5;
    } else if (grossMargin < 10) {
        score -= 5;
        warnings.push('毛利率低');
    }
    
    // 净利率评分
    const profitMargin = parseFloat(ratios.profitMargins || 0);
    if (profitMargin > 20) {
        score += 10;
        strengths.push('高净利');
    } else if (profitMargin > 10) {
        score += 5;
    } else if (profitMargin < 0) {
        score -= 15;
        warnings.push('亏损状态');
    }
    
    // 资产负债率评分 (适中最好 40-60%)
    const debtRatio = parseFloat(ratios.debtToEquity || 0);
    if (debtRatio >= 30 && debtRatio <= 60) {
        score += 5;
        strengths.push('负债合理');
    } else if (debtRatio > 80) {
        score -= 10;
        warnings.push('负债过高');
    } else if (debtRatio < 20) {
        score += 3;
        strengths.push('低负债');
    }
    
    // 成长性评分
    const revenueGrowth = parseFloat(ratios.revenueGrowth || 0);
    const earningsGrowth = parseFloat(ratios.earningsGrowth || 0);
    if (revenueGrowth > 20 || earningsGrowth > 20) {
        score += 10;
        strengths.push('高成长');
    } else if (revenueGrowth > 10 || earningsGrowth > 10) {
        score += 5;
    } else if (revenueGrowth < 0 && earningsGrowth < 0) {
        score -= 10;
        warnings.push('业绩下滑');
    }
    
    // 确保分数在 0-100 之间
    score = Math.max(0, Math.min(100, score));
    
    // 评级和颜色
    let rating, color, emoji, gradient, borderColor, comment;
    if (score >= 80) {
        rating = '优秀';
        color = '#10b981';
        emoji = '🌟';
        gradient = 'rgba(16,185,129,0.2)';
        borderColor = 'rgba(16,185,129,0.3)';
        comment = '财务状况非常健康，具备持续竞争优势';
    } else if (score >= 60) {
        rating = '良好';
        color = '#3b82f6';
        emoji = '👍';
        gradient = 'rgba(59,130,246,0.2)';
        borderColor = 'rgba(59,130,246,0.3)';
        comment = '财务状况稳健，经营表现良好';
    } else if (score >= 40) {
        rating = '一般';
        color = '#f59e0b';
        emoji = '⚠️';
        gradient = 'rgba(245,158,11,0.2)';
        borderColor = 'rgba(245,158,11,0.3)';
        comment = '财务状况尚可，但存在改进空间';
    } else {
        rating = '关注';
        color = '#ef4444';
        emoji = '🔴';
        gradient = 'rgba(239,68,68,0.2)';
        borderColor = 'rgba(239,68,68,0.3)';
        comment = '财务状况需要关注，建议深入分析';
    }
    
    return {
        score,
        rating,
        color,
        emoji,
        gradient,
        borderColor,
        comment,
        strengths: strengths.slice(0, 3),
        warnings: warnings.slice(0, 2)
    };
}

// 创建财务项HTML - 简洁 title tooltip 版
function createFinItemV2(label, value, description = '', changePercent = null, unitSuffix = '') {
    // 变化颜色：增长为绿，下跌为红（符合中国股市习惯）
    let changeHtml = '';
    if (changePercent !== null && !isNaN(changePercent)) {
        const isPositive = changePercent > 0;
        const changeColor = isPositive ? '#10b981' : (changePercent < 0 ? '#ef4444' : '#99aabc');
        const changeIcon = isPositive ? '↗' : (changePercent < 0 ? '↘' : '→');
        const sign = isPositive ? '+' : '';
        changeHtml = `<div style="font-size: 10px; color: ${changeColor}; margin-top: 2px; font-weight: 500;">${changeIcon} ${sign}${changePercent.toFixed(1)}%</div>`;
    }

    return `
        <div class="fin-item-v2" style="background: linear-gradient(135deg, rgba(30,41,59,0.8) 0%, rgba(51,65,85,0.6) 100%); border: 1px solid rgba(153,170,188,0.1); border-radius: 10px; padding: 10px; transition: all 0.2s; cursor: help;" title="${description}">
            <div style="font-size: 10px; color: #99aabc; margin-bottom: 3px; display: flex; align-items: center; gap: 4px;">
                ${label}
                ${description ? '<span style="font-size: 9px; color: #60a5fa; opacity: 0.7;">ⓘ</span>' : ''}
            </div>
            <div style="font-size: 15px; font-weight: 700; color: #e2e8f0; letter-spacing: -0.3px;">${value}${unitSuffix ? `<span style="font-size: 11px; font-weight: 500; color: #60a5fa; margin-left: 2px;">${unitSuffix}</span>` : ''}</div>
            ${changeHtml}
        </div>
    `;
}

// ==================== 多模型 AI 分析 (v1.5 新增) ====================

// 扩展快捷问题列表
const enhancedQuestions = {
    '操作建议': '请根据当前技术指标给出具体的操作建议',
    '支撑位': '当前股票的支撑位在哪里？',
    '目标价': '建议的目标价是多少？',
    '风险提示': '当前股票有什么风险需要注意？',
    '多模型对比': '请同时使用两个AI模型分析，给出对比建议',
    '自动策略': '请根据所有指标自动生成完整的交易策略',
    '综合评估': '请从技术面、基本面、资金流向等多个角度全面评估',
    'RSI指标怎么看？': '请解读当前RSI指标并给出交易建议',
    'MACD信号': '请解读当前MACD信号并给出交易建议',
    '布林带解读': '请解读当前布林带指标并给出交易建议',
    'KDJ分析': '请解读当前KDJ指标并给出交易建议'
};

// 使用多模型分析
async function askMultiAI() {
    const input = document.getElementById('aiQuestion');
    if (!input) return;

    const question = input.value.trim();
    if (!question) return;

    // 检查是否需要触发多模型
    const multiModelTriggers = ['对比', '两个', '多模型', '策略', '综合', '评估', '完整分析'];
    const useMultiModel = multiModelTriggers.some(trigger => question.includes(trigger));

    if (useMultiModel) {
        await askWithMultiModel(question);
    } else {
        askAI(); // 降级到单模型
    }
}

// 多模型问答
async function askWithMultiModel(question) {
    let stockCode = document.getElementById('stockInput')?.value.trim() ||
        document.getElementById('intradayStockInput')?.value.trim() ||
        '0700.HK';

    addMessage('user', question);
    input.value = '';

    const loadingDiv = document.getElementById('aiLoading');
    if (loadingDiv) loadingDiv.style.display = 'flex';

    try {
        const response = await fetch(`${API_BASE_URL}/multi-ai/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: stockCode,
                question: question
            })
        });

        const data = await response.json();
        if (loadingDiv) loadingDiv.style.display = 'none';

        if (data.success && data.data) {
            const analysis = data.data.analysis;
            const results = analysis.results || {};

            // 构建多模型对比消息
            let responseText = '';

            if (results.deepseek?.success) {
                responseText += `📊 **DeepSeek 分析:**\n${results.deepseek.analysis}\n\n`;
            }

            if (results.siliconflow_qwen?.success) {
                responseText += `🤖 **SiliconFlow-Qwen2.5 分析:**\n${results.siliconflow_qwen.analysis}\n\n`;
            }

            if (results.claude?.success) {
                responseText += `🧠 **Claude 分析:**\n${results.claude.analysis}\n\n`;
            }

            if (analysis.consensus) {
                responseText += `✅ **综合结论:** ${analysis.final_signal}`;
            }

            addMessage('bot', responseText || '分析完成，但未能获取有效结果。');
        } else {
            addMessage('bot', '多模型分析失败，尝试单模型分析...');
            askAI(); // 降级
        }
    } catch (error) {
        if (loadingDiv) loadingDiv.style.display = 'none';
        console.error('多模型分析失败:', error);
        addMessage('bot', '网络错误，请检查后端服务。');
    }
}

// 获取并显示交易策略
async function loadTradingStrategy() {
    let stockCode = document.getElementById('stockInput')?.value.trim() ||
        document.getElementById('intradayStockInput')?.value.trim() ||
        '0700.HK';

    try {
        const response = await fetch(`${API_BASE_URL}/multi-ai/strategy/${stockCode}`);
        const data = await response.json();

        if (data.success && data.data) {
            currentStrategy = data.data;
            displayStrategy(data.data);
        }
    } catch (error) {
        console.error('获取策略失败:', error);
    }
}

// 显示策略
function displayStrategy(strategy) {
    // 创建或更新策略卡片
    let strategyCard = document.getElementById('strategyCard');
    if (!strategyCard) {
        // 在投资建议下方插入策略卡片
        const recBox = document.getElementById('recommendationBox');
        if (recBox) {
            strategyCard = document.createElement('div');
            strategyCard.id = 'strategyCard';
            strategyCard.className = 'recommendation-box';
            strategyCard.style.display = 'block';
            strategyCard.style.marginTop = '20px';
            recBox.parentNode.insertBefore(strategyCard, recBox.nextSibling);
        }
    }

    if (strategyCard) {
        const scoreColor = strategy.overall_score >= 70 ? '#10b981' :
            strategy.overall_score >= 50 ? '#fbbf24' : '#ef4444';

        const actionColor = strategy.action.includes('买') ? '#10b981' :
            strategy.action.includes('卖') ? '#ef4444' : '#99aabc';

        strategyCard.innerHTML = `
            <div class="recommendation-header">
                <div style="font-size: 20px; font-weight: 600;">
                    <i class="bi bi-lightning-charge" style="color: #fbbf24;"></i>
                    AI 自动交易策略
                </div>
                <div class="score-badge">
                    <span class="score-item" style="background: ${scoreColor}; padding: 4px 12px; border-radius: 20px; color: white;">
                        综合评分: ${strategy.overall_score}/100
                    </span>
                </div>
            </div>

            <div class="signal-grid" style="margin: 20px 0;">
                <div class="signal-item">
                    <div class="signal-label">操作建议</div>
                    <div class="signal-value" style="color: ${actionColor}; font-size: 18px; font-weight: 700;">
                        ${strategy.action}
                    </div>
                </div>
                <div class="signal-item">
                    <div class="signal-label">信心度</div>
                    <div class="signal-value" style="color: ${scoreColor};">
                        ${strategy.confidence}
                    </div>
                </div>
                <div class="signal-item">
                    <div class="signal-label">建议仓位</div>
                    <div class="signal-value">${strategy.recommended_position}</div>
                </div>
                <div class="signal-item">
                    <div class="signal-label">风险回报比</div>
                    <div class="signal-value">${strategy.risk_reward}:1</div>
                </div>
            </div>

            <!-- 指标信号汇总 -->
            <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin: 15px 0;">
                <div class="indicator-card" style="padding: 12px; text-align: center;">
                    <div style="font-size: 11px; color: #99aabc;">趋势</div>
                    <div style="font-size: 14px; font-weight: 600; margin-top: 5px;">
                        ${strategy.signals?.trend || '--'}
                    </div>
                </div>
                <div class="indicator-card" style="padding: 12px; text-align: center;">
                    <div style="font-size: 11px; color: #99aabc;">RSI</div>
                    <div style="font-size: 14px; font-weight: 600; margin-top: 5px;">
                        ${strategy.signals?.rsi || '--'}
                    </div>
                </div>
                <div class="indicator-card" style="padding: 12px; text-align: center;">
                    <div style="font-size: 11px; color: #99aabc;">MACD</div>
                    <div style="font-size: 14px; font-weight: 600; margin-top: 5px;">
                        ${strategy.signals?.macd || '--'}
                    </div>
                </div>
                <div class="indicator-card" style="padding: 12px; text-align: center;">
                    <div style="font-size: 11px; color: #99aabc;">KDJ</div>
                    <div style="font-size: 14px; font-weight: 600; margin-top: 5px;">
                        ${strategy.signals?.kdj || '--'}
                    </div>
                </div>
                <div class="indicator-card" style="padding: 12px; text-align: center;">
                    <div style="font-size: 11px; color: #99aabc;">布林带</div>
                    <div style="font-size: 14px; font-weight: 600; margin-top: 5px;">
                        ${strategy.signals?.bollinger || '--'}
                    </div>
                </div>
            </div>

            <!-- 买卖价位 -->
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin: 20px 0;">
                <div style="background: rgba(16, 185, 129, 0.1); border-radius: 12px; padding: 15px; border: 1px solid rgba(16, 185, 129, 0.3);">
                    <div style="font-size: 14px; color: #10b981; margin-bottom: 10px;">
                        <i class="bi bi-arrow-down-circle"></i> 买入计划
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                        <span style="color: #99aabc;">买入价:</span>
                        <span style="font-weight: 600; color: #10b981;">$${strategy.entry?.buy_price || '--'}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span style="color: #99aabc;">止损价:</span>
                        <span style="font-weight: 600; color: #ef4444;">$${strategy.entry?.stop_loss || '--'}</span>
                    </div>
                    <div style="font-size: 12px; color: #99aabc; margin-top: 8px;">
                        ${strategy.entry?.rationale || ''}
                    </div>
                </div>
                <div style="background: rgba(239, 68, 68, 0.1); border-radius: 12px; padding: 15px; border: 1px solid rgba(239, 68, 68, 0.3);">
                    <div style="font-size: 14px; color: #ef4444; margin-bottom: 10px;">
                        <i class="bi bi-arrow-up-circle"></i> 卖出计划
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                        <span style="color: #99aabc;">目标一:</span>
                        <span style="font-weight: 600; color: #ef4444;">$${strategy.exit?.target_1 || '--'}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span style="color: #99aabc;">目标二:</span>
                        <span style="font-weight: 600; color: #ef4444;">$${strategy.exit?.target_2 || '--'}</span>
                    </div>
                    <div style="font-size: 12px; color: #99aabc; margin-top: 8px;">
                        ${strategy.exit?.rationale || ''}
                    </div>
                </div>
            </div>

            <div style="text-align: center; margin-top: 15px;">
                <button onclick="askMultiAIWithContext('生成详细分析报告')"
                    style="background: linear-gradient(135deg, #3b82f6, #8b5cf6); border: none; color: white; padding: 10px 24px; border-radius: 25px; cursor: pointer; font-weight: 600;">
                    <i class="bi bi-file-earmark-text"></i> 生成详细分析报告
                </button>
            </div>
        `;
    }
}

// 带上下文的AI问答
async function askMultiAIWithContext(customQuestion) {
    const input = document.getElementById('aiQuestion');
    if (input && customQuestion) {
        input.value = customQuestion;
    }
    await askWithMultiModel(input?.value || customQuestion);
}

// 增强版快捷问题
function quickAskEnhanced(type) {
    const question = enhancedQuestions[type] || type;
    const input = document.getElementById('aiQuestion');
    if (input) {
        input.value = question;
        askMultiAI();
    }
}

// 在分析完成后自动加载策略
const originalAnalyzeStock = analyzeStock;
analyzeStock = async function() {
    await originalAnalyzeStock.apply(this, arguments);
    // 分析完成后自动加载策略
    setTimeout(loadTradingStrategy, 1000);
};

// 更新AI助手快捷问题显示
function updateAIQuickQuestions() {
    const suggestionsDiv = document.querySelector('.ai-suggestions');
    if (suggestionsDiv) {
        suggestionsDiv.innerHTML = `
            <span class="suggestion-tag" onclick="quickAskEnhanced('多模型对比')">🤖 多模型对比</span>
            <span class="suggestion-tag" onclick="quickAskEnhanced('自动策略')">📋 自动策略</span>
            <span class="suggestion-tag" onclick="quickAskEnhanced('综合评估')">📊 综合评估</span>
            <span class="suggestion-tag" onclick="quickAskEnhanced('操作建议')">💡 操作建议</span>
        `;
    }
};

// 页面加载完成后更新快捷问题
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(updateAIQuickQuestions, 500);
});

// 拦截回车键，使用增强版问答
const originalHandleAIKeyPress = handleAIKeyPress;
handleAIKeyPress = function(event) {
    if (event.key === 'Enter') {
        askMultiAI();
    }
};

// ==================== 新聞輿情 v1.6C ====================

// 查詢新聞按鈕
async function fetchNews() {
    const stockInput = document.getElementById('newsStockInput');
    const stockCode = stockInput ? stockInput.value.trim() : '';
    if (!stockCode) {
        showNewsError('請輸入股票代碼');
        return;
    }

    const btn = document.getElementById('newsFetchBtn');
    const errorMsg = document.getElementById('newsErrorMessage');
    const contentGrid = document.getElementById('newsContentGrid');
    const loading = document.getElementById('newsLoading');
    const empty = document.getElementById('newsEmpty');
    const listContainer = document.getElementById('newsListContainer');

    // 重置狀態
    if (errorMsg) errorMsg.style.display = 'none';
    if (contentGrid) contentGrid.style.display = 'none';
    if (empty) empty.style.display = 'none';
    if (loading) { loading.style.display = 'block'; }
    if (listContainer) listContainer.innerHTML = '';
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="bi bi-arrow-repeat"></i> 分析中...'; }

    try {
        const response = await fetch(`${API_BASE_URL}/sentiment/${stockCode}`);
        const data = await response.json();

        if (loading) loading.style.display = 'none';
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="bi bi-search"></i> 查詢新聞'; }

        if (data.success) {
            const isRelated = data.data.is_related !== false;
            const newsCount = data.data.news ? data.data.news.length : 0;

            if (contentGrid) contentGrid.style.display = 'grid';
            renderSentimentDashboard(data.data.sentiment, data.data.news, isRelated, stockCode);
        } else {
            showNewsError(data.error || '獲取新聞失敗，請稍後重試');
        }
    } catch (err) {
        if (loading) loading.style.display = 'none';
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="bi bi-search"></i> 查詢新聞'; }
        showNewsError('網絡錯誤，請檢查後端服務是否運行');
    }
}

function showNewsError(msg) {
    const el = document.getElementById('newsErrorMessage');
    if (el) {
        el.textContent = msg;
        el.style.display = 'block';
    }
}

// 渲染情緒儀表盤
function renderSentimentDashboard(sentiment, news, isRelated, stockCode) {
    // 处理没有相关新闻的情况
    const newsData = news || [];
    const hasRelatedNews = newsData.length > 0 && isRelated;

    // 更新空状态提示
    const empty = document.getElementById('newsEmpty');
    const emptyTitle = empty ? empty.querySelector('.news-empty-title') : null;
    const emptyText = empty ? empty.querySelector('.news-empty-text') : null;

    if (!hasRelatedNews) {
        // 没有相关新闻
        if (empty) {
            empty.style.display = 'flex';
            if (emptyTitle) emptyTitle.textContent = '📰 暫無相關新聞';
            if (emptyText) emptyText.textContent = `暫未找到「${stockCode}」的相關新聞或公告\n可能原因：\n• 該股票近期無重要公告\n• 股票代碼輸入有誤\n• 公告存在但尚未披露`;
        }

        // 显示默认的仪表盘状态
        const scoreEl = document.getElementById('sentimentScore');
        const labelEl = document.getElementById('sentimentLabel');
        const summaryEl = document.getElementById('sentimentSummary');
        const ringEl = document.getElementById('sentimentRing');
        const markerEl = document.getElementById('sentimentBarMarker');

        if (scoreEl) scoreEl.textContent = '--';
        if (labelEl) { labelEl.textContent = '無數據'; labelEl.style.color = '#99aabc'; }
        if (summaryEl) summaryEl.textContent = '暫無相關新聞，無法進行情緒分析';
        if (ringEl) ringEl.style.strokeDashoffset = 414.69;  // 重置为0%
        if (markerEl) { markerEl.style.left = '50%'; markerEl.style.borderColor = '#99aabc'; }

        // 重置计数器
        const positiveCountEl = document.getElementById('positiveCount');
        const negativeCountEl = document.getElementById('negativeCount');
        const neutralCountEl = document.getElementById('neutralCount');
        if (positiveCountEl) positiveCountEl.textContent = '--';
        if (negativeCountEl) negativeCountEl.textContent = '--';
        if (neutralCountEl) neutralCountEl.textContent = '--';

        // 重置元数据
        const scoreMetaEl = document.getElementById('sentimentScoreMeta');
        const newsCountMetaEl = document.getElementById('newsCountMeta');
        if (scoreMetaEl) { scoreMetaEl.textContent = '--'; scoreMetaEl.className = 'sentiment-meta-value'; }
        if (newsCountMetaEl) newsCountMetaEl.textContent = '0';

        // 更新新闻列表容器为空
        const container = document.getElementById('newsListContainer');
        if (container) container.innerHTML = '';
        const countBadge = document.getElementById('newsCountBadge');
        if (countBadge) countBadge.textContent = '0 條';
        return;
    }

    if (!sentiment) return;

    const score = sentiment.overall_score || 0;
    const label = sentiment.label || '中性';
    const summary = sentiment.summary || '暫無AI分析摘要';

    // 分數顯示（0-100映射到-1到+1）
    const displayScore = Math.round(((score + 1) / 2) * 100);
    const scoreEl = document.getElementById('sentimentScore');
    const labelEl = document.getElementById('sentimentLabel');
    const ringEl = document.getElementById('sentimentRing');
    const markerEl = document.getElementById('sentimentBarMarker');
    const summaryEl = document.getElementById('sentimentSummary');

    if (scoreEl) scoreEl.textContent = score.toFixed(2);

    // 顏色映射
    const colorMap = {
        '利好': '#10b981',
        '利多': '#10b981',
        '偏利好': '#10b981',
        '利空': '#ef4444',
        '偏利空': '#ef4444',
        '中性': '#99aabc',
    };
    const color = colorMap[label] || '#99aabc';
    if (labelEl) {
        labelEl.textContent = label;
        labelEl.style.color = color;
    }

    // 環形進度條
    const circumference = 2 * Math.PI * 66;
    const offset = circumference - (displayScore / 100) * circumference;
    if (ringEl) {
        ringEl.style.stroke = color;
        ringEl.style.strokeDashoffset = offset;
    }

    // 滑塊位置
    const markerPercent = ((score + 1) / 2) * 100;
    if (markerEl) {
        markerEl.style.left = markerPercent + '%';
        markerEl.style.borderColor = color;
    }

    // 摘要
    if (summaryEl) summaryEl.textContent = summary;

    // 分組計數
    const newsScores = sentiment.news_scores || [];
    const positiveCount = newsScores.filter(s => s.label === '利好' || s.label === '利多').length;
    const negativeCount = newsScores.filter(s => s.label === '利空').length;
    const neutralCount = newsScores.filter(s => s.label === '中性').length;

    const pcEl = document.getElementById('positiveCount');
    const ncEl = document.getElementById('negativeCount');
    const neutralEl = document.getElementById('neutralCount');
    if (pcEl) pcEl.textContent = positiveCount;
    if (ncEl) ncEl.textContent = negativeCount;
    if (neutralEl) neutralEl.textContent = neutralCount;

    // 元數據
    const scoreMetaEl = document.getElementById('sentimentScoreMeta');
    const newsCountMetaEl = document.getElementById('newsCountMeta');
    if (scoreMetaEl) {
        scoreMetaEl.textContent = score >= 0
            ? `+${score.toFixed(2)}`
            : score.toFixed(2);
        scoreMetaEl.className = 'sentiment-meta-value ' + (
            score > 0.1 ? 'positive' : score < -0.1 ? 'negative' : 'neutral'
        );
    }
    if (newsCountMetaEl) newsCountMetaEl.textContent = news ? news.length : 0;

    // 渲染新聞列表
    renderNewsList(news, sentiment.news_scores);
}

function renderNewsList(news, newsScores) {
    const container = document.getElementById('newsListContainer');
    const countBadge = document.getElementById('newsCountBadge');
    const stockLabel = document.getElementById('newsStockLabel');
    const empty = document.getElementById('newsEmpty');

    if (!container) return;

    const newsData = news || [];

    if (newsData.length === 0) {
        container.innerHTML = '';
        if (empty) empty.style.display = 'block';
        if (countBadge) countBadge.textContent = '0 條';
        return;
    }

    if (empty) empty.style.display = 'none';
    if (countBadge) countBadge.textContent = `${newsData.length} 條`;
    if (stockLabel) stockLabel.textContent = new Date().toLocaleString('zh-HK', { hour: '2-digit', minute: '2-digit' }) + ' 更新';

    // 建立標題→分數映射
    const scoreMap = {};
    if (newsScores) {
        newsScores.forEach(item => {
            scoreMap[item.title] = item;
        });
    }

    const html = newsData.map(item => {
        const scoreInfo = scoreMap[item.title] || { score: 0, label: '中性' };
        const sentimentColor = scoreInfo.score > 0.1 ? '#10b981'
            : scoreInfo.score < -0.1 ? '#ef4444' : '#99aabc';
        const iconClass = scoreInfo.score > 0.1 ? 'news-icon-positive'
            : scoreInfo.score < -0.1 ? 'news-icon-negative' : 'news-icon-neutral';
        const iconEmoji = scoreInfo.score > 0.1 ? '📈'
            : scoreInfo.score < -0.1 ? '📉' : '📊';
        const tagClass = scoreInfo.score > 0.1 ? 'news-tag-positive'
            : scoreInfo.score < -0.1 ? 'news-tag-negative' : 'news-tag-neutral';

        return `
        <div class="news-item">
            <div class="news-item-icon ${iconClass}">${iconEmoji}</div>
            <div class="news-item-body">
                <div class="news-item-title" onclick="window.open('${item.url || '#'}', '_blank')">${item.title}</div>
                <div class="news-item-meta">
                    <span class="news-item-source">${item.source || '未知來源'}</span>
                    <span class="news-item-time">${item.time || ''}</span>
                    <span class="news-item-tag ${tagClass}">
                        ${scoreInfo.score > 0.1 ? '利好' : scoreInfo.score < -0.1 ? '利空' : '中性'}
                        (${scoreInfo.score > 0 ? '+' : ''}${scoreInfo.score.toFixed(2)})
                    </span>
                </div>
            </div>
        </div>`;
    }).join('');

    container.innerHTML = html;
}

// Enter 鍵快速查詢
document.addEventListener('DOMContentLoaded', function() {
    const input = document.getElementById('newsStockInput');
    if (input) {
        input.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                fetchNews();
            }
        });
    }
});