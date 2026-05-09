// ═══════════════════════════════════════════
//  每日報告 - 前端邏輯
// ═══════════════════════════════════════════

// 清除舊版三槽緩存（已廢棄，改用新窗口方案）
(function cleanupOldCache() {
    try {
        localStorage.removeItem('stockai_daily_cache_v2');
        localStorage.removeItem('stockai_daily_cache');
    } catch (e) {}
})();

// ═══════════════════════════════════════════
//  報告生成
// ═══════════════════════════════════════════

// 個股分析
async function generateSingleReport() {
    var code = document.getElementById('dailyStockInput').value.trim();
    if (!code) {
        showDailyError('請輸入股票代碼');
        return;
    }

    showDailyLoading('正在分析 ' + code + ' (技術指標 + 資金流向 + 交易建議)...');
    disableDailyButtons(true);
    hideRefreshBtn();

    try {
        var resp = await fetch('/api/daily-report/single', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code: code })
        });
        var data = await resp.json();

        if (data.success) {
            showDailyReport(data.html);
        } else {
            showDailyError(data.error || '分析失敗');
        }
    } catch (e) {
        showDailyError('網絡錯誤: ' + e.message);
    } finally {
        hideDailyLoading();
        disableDailyButtons(false);
    }
}

// Top N 掃描 — 在新窗口顯示
async function generateScanReport() {
    showDailyLoading('正在掃描自選股體檢 Top 200 + 資金流向...');
    disableDailyButtons(true);
    hideRefreshBtn();

    try {
        var resp = await fetch('/api/daily-report/scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ top: 200 })
        });
        var data = await resp.json();

        if (data.success) {
            // 在新窗口打開掃描結果（不再緩存到主頁）
            _openScanWindow(data.html, data.missing || [], data.missing_count || 0);
        } else {
            showDailyError(data.error || '掃描失敗');
        }
    } catch (e) {
        showDailyError('網絡錯誤: ' + e.message);
    } finally {
        hideDailyLoading();
        disableDailyButtons(false);
    }
}

// 在新窗口打開掃描結果（支持刷新缺失）
function _openScanWindow(html, missingCodes, missingCount) {
    var missingJson = JSON.stringify(missingCodes);

    // 刷新按鈕（始終注入，visible 由 JS 控制）
    var refreshDiv = '<div id="_refreshBar" style="position:fixed;top:0;left:0;right:0;z-index:9999;' +
        'padding:8px 16px;background:linear-gradient(135deg,#1e293b,#334155);' +
        'display:flex;align-items:center;justify-content:flex-end;gap:8px;' +
        'box-shadow:0 2px 12px rgba(0,0,0,0.3);">' +
        '<span id="_refreshStatus" style="color:#94a3b8;font-size:12px;"></span>' +
        '<button id="_refreshMissingBtn" style="padding:8px 18px;background:linear-gradient(135deg,#ef4444,#dc2626);' +
        'color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;' +
        'box-shadow:0 2px 8px rgba(239,68,68,0.3);transition:all 0.2s;">' +
        '&#x21bb; 刷新缺失數據 (' + missingCount + ')' +
        '</button></div>';

    // 完整的刷新腳本（自包含，刷新後仍可用）
    var refreshScript = '<scr' + 'ipt>' +
        'var _missingCodes = ' + missingJson + ';' +
        'var _missingCount = ' + missingCount + ';' +
        '(function _initRefresh() {' +
        '  var btn = document.getElementById("_refreshMissingBtn");' +
        '  if (!btn) return;' +
        '  if (_missingCount > 0) {' +
        '    btn.style.display = "inline-flex";' +
        '    btn.onclick = function() { _doRefresh(btn); };' +
        '  } else {' +
        '    btn.style.display = "none";' +
        '  }' +
        '})();' +
        'function _reInjectBar(html, newMissing, newCount) {' +
        '  _missingCodes = newMissing;' +
        '  _missingCount = newCount;' +
        '  var bar = document.getElementById("_refreshBar");' +
        '  var status = document.getElementById("_refreshStatus");' +
        '  if (bar) bar.remove();' +
        '  var div = document.createElement("div");' +
        '  div.id = "_refreshBar";' +
        '  div.style.cssText = "position:fixed;top:0;left:0;right:0;z-index:9999;padding:8px 16px;" + ' +
        '    "background:linear-gradient(135deg,#1e293b,#334155);display:flex;align-items:center;" + ' +
        '    "justify-content:flex-end;gap:8px;box-shadow:0 2px 12px rgba(0,0,0,0.3);";' +
        '  var span = document.createElement("span");' +
        '  span.id = "_refreshStatus";' +
        '  span.style.cssText = "color:#94a3b8;font-size:12px;";' +
        '  div.appendChild(span);' +
        '  var btn = document.createElement("button");' +
        '  btn.id = "_refreshMissingBtn";' +
        '  btn.style.cssText = "padding:8px 18px;background:linear-gradient(135deg,#ef4444,#dc2626);" + ' +
        '    "color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;" + ' +
        '    "box-shadow:0 2px 8px rgba(239,68,68,0.3);transition:all 0.2s;";' +
        '  btn.innerHTML = "\\u21bb 刷新缺失數據 (" + newCount + ")";' +
        '  if (newCount > 0) {' +
        '    btn.style.display = "inline-flex";' +
        '    btn.onclick = function() { _doRefresh(btn); };' +
        '  } else {' +
        '    btn.style.display = "none";' +
        '  }' +
        '  div.appendChild(btn);' +
        '  document.body.prepend(div);' +
        '  if (newCount === 0) {' +
        '    setTimeout(function(){ div.remove(); }, 3000);' +
        '  }' +
        '}' +
        'function _doRefresh(btn) {' +
        '  btn.disabled = true;' +
        '  btn.innerHTML = "\\u23f3 正在刷新 " + _missingCodes.length + " 只...";' +
        '  var codes = _missingCodes.map(function(m) { return m.code; });' +
        '  fetch(window.opener ? window.opener.location.origin + "/api/daily-report/refresh-missing" : "/api/daily-report/refresh-missing", {' +
        '    method: "POST",' +
        '    headers: { "Content-Type": "application/json" },' +
        '    body: JSON.stringify({ codes: codes })' +
        '  }).then(function(r) { return r.json(); }).then(function(data) {' +
        '    if (data.success) {' +
        '      var container = document.querySelector("div.container");' +
        '      var tmp = document.createElement("div");' +
        '      tmp.innerHTML = data.html;' +
        '      var newContent = tmp.querySelector("div.container");' +
        '      if (newContent && container) {' +
        '        container.innerHTML = newContent.innerHTML;' +
        '      } else {' +
        '        document.body.innerHTML = data.html;' +
        '      }' +
        '      var newMissing = [];' +
        '      if (data.still_missing_count > 0) {' +
        '        newMissing = _missingCodes.filter(function(m) {' +
        '          return data.still_missing.indexOf(m.code) >= 0;' +
        '        });' +
        '      }' +
        '      _reInjectBar(data.html, newMissing, data.still_missing_count || 0);' +
        '    } else {' +
        '      alert("刷新失敗: " + (data.error || ""));' +
        '      btn.disabled = false;' +
        '      btn.innerHTML = "\\u21bb 刷新缺失數據 (" + _missingCount + ") 重試";' +
        '    }' +
        '  }).catch(function(e) {' +
        '    alert("網絡錯誤: " + e.message);' +
        '    btn.disabled = false;' +
        '    btn.innerHTML = "\\u21bb 刷新缺失數據 (" + _missingCount + ") 重試";' +
        '  });' +
        '}' +
        '</scr' + 'ipt>';

    var wrappedHtml = html.replace('</body>', refreshDiv + refreshScript + '</body>');

    // 用 Blob URL 打開新窗口
    var blob = new Blob([wrappedHtml], { type: 'text/html; charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var win = window.open(url, 'stockai_scan_' + Date.now());

    if (!win) {
        showDailyReport(html);
        if (missingCount > 0) showRefreshBtn(missingCount, missingCodes);
        showDailyError('彈窗被瀏覽器攔截，請允許彈窗後重試');
        return;
    }
}

// 刷新缺失數據（主頁版本 — 僅供 showRefreshBtn 觸發，新窗口有自己的刷新邏輯）
async function refreshMissingData() {
    hideRefreshBtn();
    showDailyError('刷新功能已移至新窗口，請在掃描結果頁面操作');
}

// 持倉報告
async function generatePortfolioReport() {
    showDailyLoading('正在生成持倉報告...');
    disableDailyButtons(true);
    hideRefreshBtn();

    try {
        var resp = await fetch('/api/daily-report/portfolio', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        var data = await resp.json();

        if (data.success) {
            showDailyReport(data.html);
        } else {
            showDailyError(data.error || '生成失敗');
        }
    } catch (e) {
        showDailyError('網絡錯誤: ' + e.message);
    } finally {
        hideDailyLoading();
        disableDailyButtons(false);
    }
}

// ═══════════════════════════════════════════
//  緩存恢復 / 清除
// ═══════════════════════════════════════════

// 切回 daily mode 或頁面載入時，顯示空狀態（新窗口方案不再自動恢復）
function restoreDailyReport() {
    hideRefreshBtn();
    document.getElementById('dailyEmpty').style.display = 'flex';
}

// 清除緩存（保留接口兼容，實際已無緩存）
function clearDailyCache(type) {
    hideRefreshBtn();
}

// ═══════════════════════════════════════════
//  UI Helpers
// ═══════════════════════════════════════════

function showDailyLoading(text) {
    var el = document.getElementById('dailyLoading');
    var txt = document.getElementById('dailyLoadingText');
    if (txt) txt.textContent = text || '正在生成報告...';
    if (el) el.style.display = 'block';
    hideDailyError();
    document.getElementById('dailyEmpty').style.display = 'none';
    document.getElementById('dailyReportContainer').style.display = 'none';
}

function hideDailyLoading() {
    var el = document.getElementById('dailyLoading');
    if (el) el.style.display = 'none';
}

function showDailyError(msg) {
    var el = document.getElementById('dailyError');
    if (el) {
        el.textContent = msg;
        el.style.display = 'block';
    }
    hideDailyLoading();
    document.getElementById('dailyEmpty').style.display = 'none';
}

function showDailySuccess(msg) {
    var el = document.getElementById('dailyError');
    if (el) {
        el.textContent = msg;
        el.style.display = 'block';
        el.style.background = 'rgba(16,185,129,0.1)';
        el.style.borderColor = 'rgba(16,185,129,0.3)';
        el.style.color = '#10b981';
    }
    setTimeout(function() {
        el.style.display = 'none';
        el.style.background = '';
        el.style.borderColor = '';
        el.style.color = '';
    }, 3000);
}

function hideDailyError() {
    var el = document.getElementById('dailyError');
    if (el) {
        el.style.display = 'none';
        el.style.background = '';
        el.style.borderColor = '';
        el.style.color = '';
    }
}

function showDailyReport(html) {
    hideDailyLoading();
    hideDailyError();
    document.getElementById('dailyEmpty').style.display = 'none';

    var container = document.getElementById('dailyReportContainer');
    var frame = document.getElementById('dailyReportFrame');
    container.style.display = 'block';

    var blob = new Blob([html], { type: 'text/html; charset=utf-8' });
    var url = URL.createObjectURL(blob);
    frame.src = url;

    frame.onload = function () {
        try {
            var h = frame.contentDocument.documentElement.scrollHeight;
            frame.style.height = Math.max(800, h + 20) + 'px';
        } catch (e) {
            frame.style.height = '2000px';
        }
    };
}

function showRefreshBtn(count, missing) {
    var btn = document.getElementById('dailyRefreshBtn');
    if (!btn) {
        var scanBtn = document.getElementById('dailyScanBtn');
        btn = document.createElement('button');
        btn.id = 'dailyRefreshBtn';
        btn.className = 'btn-analyze';
        btn.style.cssText = 'background: linear-gradient(135deg, #ef4444, #dc2626); white-space: nowrap; display: none; max-width: 320px; overflow: hidden; text-overflow: ellipsis;';
        scanBtn.parentNode.insertBefore(btn, scanBtn.nextSibling);
    }
    var extra = count > 3 ? ' 等' + count + '只' : '';
    btn.innerHTML = '<i class="bi bi-arrow-clockwise"></i> 刷新缺失 (' + count + ')' + extra;
    btn.title = missing.map(function(m) { return m.name + '(' + m.code + ')'; }).join(', ');
    btn.style.display = 'inline-flex';
    btn.onclick = refreshMissingData;
}

function hideRefreshBtn() {
    var btn = document.getElementById('dailyRefreshBtn');
    if (btn) btn.style.display = 'none';
}

function disableDailyButtons(disabled) {
    ['dailySingleBtn', 'dailyScanBtn', 'dailyPortfolioBtn'].forEach(function(id) {
        var btn = document.getElementById(id);
        if (btn) {
            btn.disabled = disabled;
            btn.style.opacity = disabled ? '0.5' : '1';
            btn.style.pointerEvents = disabled ? 'none' : 'auto';
        }
    });
    var refBtn = document.getElementById('dailyRefreshBtn');
    if (refBtn) {
        refBtn.disabled = disabled;
        refBtn.style.opacity = disabled ? '0.5' : '1';
        refBtn.style.pointerEvents = disabled ? 'none' : 'auto';
    }
}

// 頁面載入時，如果在 daily mode 且有緩存，自動恢復
document.addEventListener('DOMContentLoaded', function () {
    var input = document.getElementById('dailyStockInput');
    if (input) {
        input.addEventListener('keypress', function (e) {
            if (e.key === 'Enter') {
                generateSingleReport();
            }
        });
    }
    // 如果 daily mode 是 active 的，自動恢復緩存
    var dailyMode = document.getElementById('daily-mode');
    if (dailyMode && dailyMode.classList.contains('active')) {
        setTimeout(function() { restoreDailyReport(); }, 100);
    }
});
