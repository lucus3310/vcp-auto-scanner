const isStaticMode = window.location.hostname.includes('github.io') || window.location.hostname.includes('githubusercontent.com');
// VCP Stock Scanner Frontend Controller

let presets = {};
let scanResults = [];
let liveScanResults = [];
let activeFilter = 'all';
let searchKeyword = '';

let tickerNames = {};
let currentActiveSymbol = null;
let watchlistSymbols = [];
let progressInterval = null;
let chartInstance = null;
let candleSeries = null;
let emaSeries = null;
let upperKcSeries = null;
let lowerKcSeries = null;
let volumeSeries = null;

// DOM Elements
const presetSelect = document.getElementById('preset-select');
const symbolsInput = document.getElementById('symbols-input');
const lookbackSelect = document.getElementById('lookback-select');
const minBaseInput = document.getElementById('min-base-input');
const volSpikeInput = document.getElementById('vol-spike-input');
const contractionRatioInput = document.getElementById('contraction-ratio-input');
const minVolumeInput = document.getElementById('min-volume-input');
const btnStartScan = document.getElementById('btn-start-scan');
const btnCancelScan = document.getElementById('btn-cancel-scan');
const btnSaveWatchlist = document.getElementById('btn-save-watchlist');
const btnClearWatchlist = document.getElementById('btn-clear-watchlist');

const progressSection = document.getElementById('progress-section');
const progressStatus = document.getElementById('progress-status');
const progressPercentage = document.getElementById('progress-percentage');
const progressFill = document.getElementById('progress-fill');

const valTotal = document.getElementById('val-total');
const valVcp = document.getElementById('val-vcp');
const valBreakout = document.getElementById('val-breakout');
const valAnomaly = document.getElementById('val-anomaly');

const searchInput = document.getElementById('search-input');
const filterAllBtn = document.getElementById('filter-all');
const filterVcpBtn = document.getElementById('filter-vcp');
const filterMinerviniBtn = document.getElementById('filter-minervini');
const filterBreakoutBtn = document.getElementById('filter-breakout');
const resultsTbody = document.getElementById('results-tbody');
const historySelect = document.getElementById('history-select');

const chartTitle = document.getElementById('chart-title');
const chartVcpBadge = document.getElementById('chart-vcp-badge');
const chartSourceBadge = document.getElementById('chart-source-badge');
const chartEmpty = document.getElementById('chart-empty');
const priceChartDiv = document.getElementById('price-chart');
const detailsSection = document.getElementById('details-section');
const contractionCardsContainer = document.getElementById('contraction-cards-container');
const minerviniSection = document.getElementById('minervini-section');
const minerviniChecklistContainer = document.getElementById('minervini-checklist-container');

const watchlistAddInput = document.getElementById('watchlist-add-input');
const btnWatchlistAdd = document.getElementById('btn-watchlist-add');
const watchlistItemsContainer = document.getElementById('watchlist-items-container');
const btnWatchlistScan = document.getElementById('btn-watchlist-scan');
const btnWatchlistClear = document.getElementById('btn-watchlist-clear');
const watchlistCount = document.getElementById('watchlist-count');
const btnChartStar = document.getElementById('btn-chart-star');

const contextMenu = document.getElementById('custom-context-menu');
const ctxLoadChart = document.getElementById('ctx-load-chart');
const ctxToggleWatchlist = document.getElementById('ctx-toggle-watchlist');
let activeContextSymbol = null;

const tabLiveScan = document.getElementById('tab-live-scan');
const tabHistoryData = document.getElementById('tab-history-data');
const liveScanContainer = document.getElementById('live-scan-container');
const historyDataContainer = document.getElementById('history-data-container');
const historyRunsTbody = document.getElementById('history-runs-tbody');
const btnClearAllHistory = document.getElementById('btn-clear-all-history');

// Initialize App
window.addEventListener('DOMContentLoaded', async () => {
    await loadTickerNames();
    await fetchPresets();
    await fetchHistoryDates();
    await loadWatchlistSidebar();
    setupEventListeners();
    
    // Autoload the latest pre-fetched / historical scan if available
    if (historySelect.options.length > 1) {
        historySelect.selectedIndex = 1;
        await loadHistoricalScan();
    }
    
    checkActiveScan();
});

// Event Listeners Setup
function setupEventListeners() {
    // Preset change handler
    presetSelect.addEventListener('change', async () => {
        const val = presetSelect.value;
        if (val === 'CUSTOM') {
            symbolsInput.value = '';
            symbolsInput.disabled = false;
        } else if (val === 'WATCHLIST') {
            await loadWatchlistPreset();
        } else if (presets[val]) {
            symbolsInput.value = presets[val].join(', ');
            symbolsInput.disabled = true;
        }
    });

    // Watchlist Actions
    btnSaveWatchlist.addEventListener('click', saveToWatchlist);
    btnClearWatchlist.addEventListener('click', clearWatchlist);

    // Start Scan
    btnStartScan.addEventListener('click', startScan);

    // Cancel Scan
    btnCancelScan.addEventListener('click', cancelScan);

    // Search and Filters
    searchInput.addEventListener('input', (e) => {
        searchKeyword = e.target.value.trim().toUpperCase();
        renderTable();
    });

    filterAllBtn.addEventListener('click', () => setFilter('all'));
    filterVcpBtn.addEventListener('click', () => setFilter('vcp'));
    filterMinerviniBtn.addEventListener('click', () => setFilter('minervini'));
    filterBreakoutBtn.addEventListener('click', () => setFilter('breakout'));

    // Scan History Selector
    historySelect.addEventListener('change', loadHistoricalScan);

    // Watchlist Sidebar Add Event
    btnWatchlistAdd.addEventListener('click', addWatchlistItem);
    watchlistAddInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            addWatchlistItem();
        }
    });

    // Chart Header Star Toggle Event
    btnChartStar.addEventListener('click', toggleChartStar);

    // Watchlist Footer Actions
    btnWatchlistScan.addEventListener('click', scanWatchlistOnly);
    btnWatchlistClear.addEventListener('click', clearWatchlistSidebar);

    // Hide context menu on any document click or window resize
    document.addEventListener('click', hideContextMenu);
    window.addEventListener('resize', hideContextMenu);

    // Context Menu Action Listeners
    ctxLoadChart.addEventListener('click', () => {
        if (activeContextSymbol) {
            loadStockChart(activeContextSymbol);
            hideContextMenu();
        }
    });

    ctxToggleWatchlist.addEventListener('click', async () => {
        if (activeContextSymbol) {
            const sym = activeContextSymbol;
            if (watchlistSymbols.includes(sym)) {
                await removeWatchlistItem(sym);
            } else {
                watchlistSymbols.push(sym);
                renderWatchlistSidebar();
                updateChartStarStatus();
                
                try {
                    const res = await fetch('/api/watchlist', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ symbol: sym })
                    });
                    if (res.ok) {
                        const data = await res.json();
                        watchlistSymbols = data.watchlist;
                        renderWatchlistSidebar();
                        updateChartStarStatus();
                    }
                } catch (e) {
                    console.error("Failed to save to watchlist via context menu", e);
                }
                
                if (presetSelect.value === 'WATCHLIST') {
                    await loadWatchlistPreset();
                }
            }
            hideContextMenu();
        }
    });

    // Dashboard Tabs Toggling
    tabLiveScan.addEventListener('click', () => {
        tabLiveScan.classList.add('active');
        tabHistoryData.classList.remove('active');
        liveScanContainer.style.display = 'block';
        historyDataContainer.style.display = 'none';
    });

    tabHistoryData.addEventListener('click', () => {
        tabHistoryData.classList.add('active');
        tabLiveScan.classList.remove('active');
        historyDataContainer.style.display = 'block';
        liveScanContainer.style.display = 'none';
        loadHistorySummary();
    });

    btnClearAllHistory.addEventListener('click', clearAllHistoryData);
}

// Fetch Preset Lists from API
async function fetchPresets() {
    try {
        const res = await fetch('/api/presets');
        presets = await res.json();
        
        // Load default preset list (ALL)
        if (presets["ALL"]) {
            presetSelect.value = "ALL";
            symbolsInput.value = presets["ALL"].join(', ');
            symbolsInput.disabled = true;
        } else {
            symbolsInput.value = "AAPL, MSFT, NVDA, TSLA, AMD, LLY, AVGO, NFLX";
        }
    } catch (e) {
        console.error("Failed to load symbol presets", e);
    }
}

// Set Filter View
function setFilter(filterType) {
    activeFilter = filterType;
    [filterAllBtn, filterVcpBtn, filterMinerviniBtn, filterBreakoutBtn].forEach(btn => btn.classList.remove('active'));
    
    if (filterType === 'all') filterAllBtn.classList.add('active');
    if (filterType === 'vcp') filterVcpBtn.classList.add('active');
    if (filterType === 'minervini') filterMinerviniBtn.classList.add('active');
    if (filterType === 'breakout') filterBreakoutBtn.classList.add('active');
    
    renderTable();
}

// Start Scan Request
async function startScan() {
    const symbolText = symbolsInput.value;
    const symbols = symbolText.split(/[\s,;\n]+/).map(s => s.trim()).filter(s => s.length > 0);
    
    if (symbols.length === 0) {
        alert("請輸入至少一個股票代號！");
        return;
    }

    const payload = {
        symbols: symbols,
        lookback_period: lookbackSelect.value,
        min_base_duration: parseInt(minBaseInput.value),
        volume_spike_multiplier: parseFloat(volSpikeInput.value),
        contraction_ratio_threshold: parseFloat(contractionRatioInput.value),
        min_volume: parseInt(minVolumeInput.value)
    };

    try {
        btnStartScan.disabled = true;
        btnCancelScan.disabled = false;
        progressSection.style.display = 'flex';
        
        const res = await fetch('/api/scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "啟動掃描失敗");
        }

        // Start Polling Status
        pollProgress();
    } catch (e) {
        alert(`掃描啟動錯誤: ${e.message}`);
        btnStartScan.disabled = false;
        btnCancelScan.disabled = true;
        progressSection.style.display = 'none';
    }
}

// Cancel Scan Request
async function cancelScan() {
    try {
        await fetch('/api/cancel', { method: 'POST' });
        progressStatus.innerText = "正在取消...";
    } catch (e) {
        console.error("Failed to cancel scan", e);
    }
}

// Check if a scan is already running on page load
async function checkActiveScan() {
    try {
        const res = await fetch('/api/progress');
        const state = await res.json();
        if (state.running) {
            btnStartScan.disabled = true;
            btnCancelScan.disabled = false;
            progressSection.style.display = 'flex';
            pollProgress();
        }
    } catch (e) {
        console.error("Failed to check active scan state", e);
    }
}

// Poll scan progress and updates UI
function pollProgress() {
    if (progressInterval) clearInterval(progressInterval);
    
    progressInterval = setInterval(async () => {
        try {
            const res = await fetch('/api/progress');
            const state = await res.json();
            
            // Update Progress UI
            progressPercentage.innerText = `${state.progress}%`;
            progressFill.style.width = `${state.progress}%`;
            
            if (state.running) {
                progressStatus.innerText = `正在掃描 ${state.current_symbol}... (${state.results.length}/${state.total})`;
            }
            
            // Render partial/complete results
            if (state.results && state.results.length > 0) {
                scanResults = state.results;
                liveScanResults = [...state.results];
                updateStats();
                renderTable();
            }

            if (!state.running) {
                clearInterval(progressInterval);
                progressInterval = null;
                btnStartScan.disabled = false;
                btnCancelScan.disabled = true;
                
                if (state.cancelled) {
                    progressStatus.innerText = "已取消掃描";
                    progressFill.style.backgroundColor = "var(--accent-red)";
                } else {
                    progressStatus.innerText = "掃描完成！";
                    progressFill.style.backgroundColor = "var(--accent-green)";
                }
                
                // Automatically select first row to plot chart if VCP stocks exist
                const vcpStocks = scanResults.filter(r => r.VCP);
                if (vcpStocks.length > 0) {
                    loadStockChart(vcpStocks[0].Symbol);
                } else if (scanResults.length > 0) {
                    loadStockChart(scanResults[0].Symbol);
                }
            }
        } catch (e) {
            console.error("Error polling scan progress", e);
        }
    }, 1000);
}

// Update Header Stats Cards
function updateStats() {
    valTotal.innerText = scanResults.length;
    valVcp.innerText = scanResults.filter(r => r.VCP).length;
    valBreakout.innerText = scanResults.filter(r => r.Breakout_Detected).length;
    valAnomaly.innerText = scanResults.filter(r => r.Anomaly_Free).length;
}

// Render Results Table
function renderTable() {
    resultsTbody.innerHTML = '';
    
    // Filter results
    let filtered = scanResults;
    
    if (activeFilter === 'vcp') {
        filtered = filtered.filter(r => r.VCP);
    } else if (activeFilter === 'minervini') {
        filtered = filtered.filter(r => r.Minervini);
    } else if (activeFilter === 'breakout') {
        filtered = filtered.filter(r => r.Breakout_Detected);
    }
    
    if (searchKeyword) {
        filtered = filtered.filter(r => r.Symbol.includes(searchKeyword));
    }
    
    if (filtered.length === 0) {
        resultsTbody.innerHTML = `<tr><td colspan="10" class="empty-state">無符合篩選條件之股票項目</td></tr>`;
        return;
    }
    
    filtered.forEach(row => {
        const tr = document.createElement('tr');
        
        // Highlight VCP-positive rows slightly
        if (row.VCP) {
            tr.style.borderLeft = "4px solid var(--accent-green)";
        }
        
        tr.innerHTML = `
            <td>
                <div style="font-weight: 700;">${row.Symbol}</div>
                ${row.Name ? `<div style="font-size: 11px; color: var(--text-secondary); font-weight: normal; margin-top: 2px;">${row.Name}</div>` : ''}
            </td>
            <td>
                <span class="badge ${row.VCP ? 'badge-vcp-yes' : 'badge-vcp-no'}">
                    ${row.VCP ? '成立' : '無'}
                </span>
            </td>
            <td>
                <span class="badge ${row.Minervini ? 'badge-vcp-yes' : 'badge-vcp-no'}">
                    ${row.Minervini ? '符合' : '未達標'}
                </span>
            </td>
            <td class="${row.Price_Increase_6M.startsWith('-') ? 'text-red' : 'text-green'}">
                ${row.Price_Increase_6M}
            </td>
            <td>${row.Contractions}</td>
            <td>${row.Volatility_Decrease}</td>
            <td>${row.Volume_Contraction ? '📉 收縮' : '無'}</td>
            <td>${row.Breakout_Detected ? '🚀 爆量突破' : '無'}</td>
            <td>${row.RSI_Value}</td>
            <td style="font-size: 11px; color: var(--text-secondary); max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${row.Reason}">
                ${row.Reason}
            </td>
        `;
        
        tr.addEventListener('click', () => loadStockChart(row.Symbol));
        tr.addEventListener('dblclick', (e) => {
            e.preventDefault();
            showContextMenu(e, row.Symbol);
        });
        tr.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            showContextMenu(e, row.Symbol);
        });
        resultsTbody.appendChild(tr);
    });
}

// Load Stock Candlestick Chart via API
async function loadStockChart(symbol) {
    currentActiveSymbol = symbol;
    updateChartStarStatus();
    
    chartEmpty.style.display = 'none';
    chartTitle.innerText = `正在載入 ${symbol}...`;
    chartVcpBadge.style.display = 'none';
    detailsSection.style.display = 'none';
    minerviniSection.style.display = 'none';
    minerviniSection.style.display = 'none';
    
    const lookback = lookbackSelect.value;
    
    try {
        const res = await fetch(`/api/chart-data?symbol=${symbol}&lookback_period=${lookback}`);
        if (!res.ok) {
            throw new Error("無法取得圖表資料");
        }
        const data = await res.json();
        
        // Update Chart Headers
        chartTitle.innerText = data.name ? `${data.symbol} - ${data.name} 互動式 K 線分析` : `${data.symbol} 互動式 K 線分析`;
        chartVcpBadge.style.display = 'inline-block';
        chartVcpBadge.className = `badge ${data.analysis.VCP ? 'badge-vcp-yes' : 'badge-vcp-no'}`;
        chartVcpBadge.innerText = data.analysis.VCP ? 'VCP 成立' : '未成形態';
        
        // Update chart source badge
        if (data.data_source === 'local_cache') {
            chartSourceBadge.innerText = "本地快取 (Cache)";
            chartSourceBadge.style.backgroundColor = "rgba(0, 230, 118, 0.1)";
            chartSourceBadge.style.color = "var(--accent-green)";
            chartSourceBadge.style.border = "1px solid rgba(0, 230, 118, 0.2)";
            chartSourceBadge.style.display = 'inline-block';
        } else if (data.data_source === 'live_download') {
            chartSourceBadge.innerText = "即時下載 (Live)";
            chartSourceBadge.style.backgroundColor = "rgba(0, 114, 255, 0.1)";
            chartSourceBadge.style.color = "var(--accent-cyan)";
            chartSourceBadge.style.border = "1px solid rgba(0, 114, 255, 0.2)";
            chartSourceBadge.style.display = 'inline-block';
        } else {
            chartSourceBadge.style.display = 'none';
        }
        
        renderTradingViewChart(data.chart_data, data.analysis);
        renderContractionsDetails(data.analysis.Contraction_List);
        
        if (data.analysis.Minervini_Trend) {
            renderMinerviniChecklist(data.analysis.Minervini_Trend);
        }
        
    } catch (e) {
        chartTitle.innerText = `載入失敗: ${symbol}`;
        chartEmpty.style.display = 'flex';
        chartEmpty.querySelector('p').innerText = `圖表載入錯誤: ${e.message}`;
    }
}

// Render TradingView Lightweight Chart
function renderTradingViewChart(chartData, analysis) {
    // Clear previous chart
    if (chartInstance) {
        chartInstance.remove();
        chartInstance = null;
    }
    
    priceChartDiv.innerHTML = '';
    
    const width = priceChartDiv.clientWidth || 500;
    const height = priceChartDiv.clientHeight || 350;
    
    // Create new chart instance
    chartInstance = LightweightCharts.createChart(priceChartDiv, {
        width: width,
        height: height,
        layout: {
            background: {
                type: 'solid',
                color: '#121829',
            },
            textColor: '#94a3b8',
            fontSize: 11,
            fontFamily: 'Inter, sans-serif',
        },
        grid: {
            vertLines: { color: 'rgba(36, 47, 76, 0.2)' },
            horzLines: { color: 'rgba(36, 47, 76, 0.2)' },
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
        },
        rightPriceScale: {
            borderColor: '#242f4c',
        },
        timeScale: {
            borderColor: '#242f4c',
        },
    });

    // Add Candlestick Series
    candleSeries = chartInstance.addSeries(LightweightCharts.CandlestickSeries, {
        upColor: '#00e676',
        downColor: '#ff1744',
        borderDownColor: '#ff1744',
        borderUpColor: '#00e676',
        wickDownColor: '#ff1744',
        wickUpColor: '#00e676',
    });
    
    // Map data for candle series
    const candleData = chartData.map(d => ({
        time: d.time,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close
    }));
    candleSeries.setData(candleData);
    
    // Add EMA20 Line Series
    emaSeries = chartInstance.addSeries(LightweightCharts.LineSeries, {
        color: '#ffc107',
        lineWidth: 1.5,
        title: 'EMA 20'
    });
    const emaData = chartData.filter(d => d.ema20 !== null).map(d => ({
        time: d.time,
        value: d.ema20
    }));
    emaSeries.setData(emaData);

    // Add Keltner Channel boundaries
    upperKcSeries = chartInstance.addSeries(LightweightCharts.LineSeries, {
        color: 'rgba(0, 242, 254, 0.25)',
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        title: 'KC Upper'
    });
    const upperKcData = chartData.filter(d => d.upper_kc !== null).map(d => ({
        time: d.time,
        value: d.upper_kc
    }));
    upperKcSeries.setData(upperKcData);
    
    lowerKcSeries = chartInstance.addSeries(LightweightCharts.LineSeries, {
        color: 'rgba(0, 242, 254, 0.25)',
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        title: 'KC Lower'
    });
    const lowerKcData = chartData.filter(d => d.lower_kc !== null).map(d => ({
        time: d.time,
        value: d.lower_kc
    }));
    lowerKcSeries.setData(lowerKcData);

    // Prepare Chart Markers for Contractions and Breakout
    const markers = [];
    
    // Contraction peaks and troughs
    if (analysis.Contraction_List && analysis.Contraction_List.length > 0) {
        analysis.Contraction_List.forEach((c, idx) => {
            markers.push({
                time: c.high_date,
                position: 'aboveBar',
                color: '#ff1744',
                shape: 'arrowDown',
                text: `C${idx+1} Peak (${(c.retracement * 100).toFixed(1)}%)`
            });
            markers.push({
                time: c.low_date,
                position: 'belowBar',
                color: '#00e676',
                shape: 'arrowUp',
                text: `C${idx+1} Trough`
            });
        });
    }
    
    // Breakout marker
    if (analysis.Breakout_Detected && chartData.length > 0) {
        const lastBar = chartData[chartData.length - 1];
        markers.push({
            time: lastBar.time,
            position: 'aboveBar',
            color: '#00f2fe',
            shape: 'star',
            text: 'BREAKOUT!'
        });
    }
    
    // Apply markers sorted by time
    markers.sort((a, b) => a.time.localeCompare(b.time));
    candleSeries.setMarkers = (m) => LightweightCharts.createSeriesMarkers(candleSeries, m);
    candleSeries.setMarkers(markers);
    
    // Fit chart content
    chartInstance.timeScale().fitContent();
    
    // Handle window resizing
    window.addEventListener('resize', () => {
        if (chartInstance && priceChartDiv.clientWidth > 0) {
            chartInstance.resize(priceChartDiv.clientWidth, height);
        }
    });

    // Handle deferred layout sizing
    setTimeout(() => {
        if (chartInstance && priceChartDiv.clientWidth > 0) {
            chartInstance.resize(priceChartDiv.clientWidth, height);
        }
    }, 100);
}

// Render Contraction detail cards underneath chart
function renderContractionsDetails(contractions) {
    contractionCardsContainer.innerHTML = '';
    
    if (!contractions || contractions.length === 0) {
        detailsSection.style.display = 'none';
        return;
    }
    
    detailsSection.style.display = 'block';
    
    contractions.forEach((c, idx) => {
        const card = document.createElement('div');
        card.className = 'contraction-card';
        card.innerHTML = `
            <span class="card-num">第 ${idx + 1} 次收縮 (C${idx + 1})</span>
            <span class="card-val">${(c.retracement * 100).toFixed(1)}%</span>
            <span class="card-dates">${c.high_date} 至 ${c.low_date}</span>
            <span style="font-size: 10px; color: var(--text-secondary); margin-top: 4px;">
                高點: $${c.high_val.toFixed(2)}<br>
                低點: $${c.low_val.toFixed(2)}<br>
                波寬: ${(c.kc_width * 100).toFixed(2)}%
            </span>
        `;
        contractionCardsContainer.appendChild(card);
    });
}

// Render Minervini Checklist
function renderMinerviniChecklist(trend) {
    minerviniChecklistContainer.innerHTML = '';
    
    if (!trend || !trend.values || Object.keys(trend.values).length === 0) {
        minerviniSection.style.display = 'none';
        return;
    }
    
    minerviniSection.style.display = 'block';
    
    const rulesDef = [
        { key: 'rule1_close_above_ma150_200', text: '股價在 150MA 與 200MA 之上', desc: `股價: $${trend.values.close.toFixed(2)} (150MA: $${trend.values.ma150.toFixed(2)}, 200MA: $${trend.values.ma200.toFixed(2)})` },
        { key: 'rule2_ma150_above_ma200', text: '150MA 高於 200MA', desc: `150MA: $${trend.values.ma150.toFixed(2)} > 200MA: $${trend.values.ma200.toFixed(2)}` },
        { key: 'rule3_ma200_trending_up', text: '200MA 處於上升趨勢 (1M)', desc: `MA200 較 20 天前變動: ${trend.values.ma200_pct_change >= 0 ? '+' : ''}${trend.values.ma200_pct_change.toFixed(2)}%` },
        { key: 'rule4_ma50_above_ma150_200', text: '50MA 高於 150MA 與 200MA', desc: `50MA: $${trend.values.ma50.toFixed(2)}` },
        { key: 'rule5_close_above_ma50', text: '股價在 50MA 之上', desc: `股價: $${trend.values.close.toFixed(2)} > 50MA: $${trend.values.ma50.toFixed(2)}` },
        { key: 'rule6_above_52w_low_30pct', text: '股價高於 52 週低點至少 30%', desc: `較低點高出: ${trend.values.pct_above_52w_low.toFixed(1)}% (52W 低: $${trend.values.low_52w.toFixed(2)})` },
        { key: 'rule7_within_52w_high_25pct', text: '股價距離 52 週高點在 25% 以內', desc: `距離高點: ${trend.values.pct_below_52w_high.toFixed(1)}% (52W 高: $${trend.values.high_52w.toFixed(2)})` }
    ];
    
    rulesDef.forEach(r => {
        const isMet = trend.rules[r.key];
        const card = document.createElement('div');
        card.style.display = 'flex';
        card.style.alignItems = 'flex-start';
        card.style.gap = '10px';
        card.style.backgroundColor = 'var(--bg-card)';
        card.style.border = `1px solid ${isMet ? 'rgba(0, 230, 118, 0.2)' : 'var(--border-color)'}`;
        card.style.borderRadius = '8px';
        card.style.padding = '12px';
        card.style.transition = 'var(--transition-smooth)';
        
        card.innerHTML = `
            <div style="font-size: 16px; color: ${isMet ? 'var(--accent-green)' : 'var(--text-muted)'}; line-height: 1;">
                ${isMet ? '✅' : '❌'}
            </div>
            <div style="display: flex; flex-direction: column; gap: 4px;">
                <span style="font-size: 12px; font-weight: 600; color: ${isMet ? 'var(--text-primary)' : 'var(--text-secondary)'};">
                    ${r.text}
                </span>
                <span style="font-size: 10px; color: var(--text-muted);">
                    ${r.desc}
                </span>
            </div>
        `;
        minerviniChecklistContainer.appendChild(card);
    });
}

// Watchlist API Calls
async function loadWatchlistPreset() {
    try {
        const res = await fetch('/api/watchlist');
        const list = await res.json();
        symbolsInput.value = list.join(', ');
        symbolsInput.disabled = true;
    } catch (e) {
        console.error("Failed to load watchlist preset", e);
        symbolsInput.value = "";
        symbolsInput.disabled = false;
        alert("無法讀取自選股清單");
    }
}

async function saveToWatchlist() {
    const symbolText = symbolsInput.value;
    const symbols = symbolText.split(/[\s,;\n]+/).map(s => s.trim().toUpperCase()).filter(s => s.length > 0);
    if (symbols.length === 0) {
        alert("請輸入要加入自選股的股票代號！");
        return;
    }
    
    btnSaveWatchlist.disabled = true;
    const oldText = btnSaveWatchlist.innerText;
    btnSaveWatchlist.innerText = "儲存中...";
    
    try {
        for (const symbol of symbols) {
            await fetch('/api/watchlist', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ symbol })
            });
        }
        alert("已成功儲存至自選股！");
        if (presetSelect.value === 'WATCHLIST') {
            await loadWatchlistPreset();
        }
    } catch (e) {
        console.error("Failed to save to watchlist", e);
        alert("儲存自選股失敗");
    } finally {
        btnSaveWatchlist.disabled = false;
        btnSaveWatchlist.innerText = oldText;
    }
}

async function clearWatchlist() {
    if (!confirm("確定要清空所有自選股嗎？")) {
        return;
    }
    
    btnClearWatchlist.disabled = true;
    const oldText = btnClearWatchlist.innerText;
    btnClearWatchlist.innerText = "清空中...";
    
    try {
        const res = await fetch('/api/watchlist');
        const list = await res.json();
        
        for (const symbol of list) {
            await fetch(`/api/watchlist/${encodeURIComponent(symbol)}`, {
                method: 'DELETE'
            });
        }
        alert("已清空自選股清單！");
        if (presetSelect.value === 'WATCHLIST') {
            symbolsInput.value = '';
        }
    } catch (e) {
        console.error("Failed to clear watchlist", e);
        alert("清空自選股失敗");
    } finally {
        btnClearWatchlist.disabled = false;
        btnClearWatchlist.innerText = oldText;
    }
}

// Historical Scan API Calls
async function fetchHistoryDates() {
    try {
        if (isStaticMode) {
            historySelect.innerHTML = \'<option value="LATEST">最新結果 (Static Mode)</option>\';
            return;
        }
        const res = await fetch('/api/history-dates');
        const dates = await res.json();
        
        historySelect.innerHTML = '<option value="LATEST">當前掃描結果 (Live Scan)</option>';
        
        dates.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d;
            opt.innerText = d;
            historySelect.appendChild(opt);
        });
    } catch (e) {
        console.error("Failed to fetch scan history dates", e);
    }
}

async function loadHistoricalScan() {
    const val = historySelect.value;
    if (val === \'LATEST\') {
        if (isStaticMode) {
            try {
                const res = await fetch(\'./latest_scan.json\');
                if (res.ok) {
                    const data = await res.json();
                    scanResults = data.results;
                    applyFilters();
                    lastScanTime.innerText = "掃描時間: " + data.date;
                    return;
                }
            } catch(e) {}
        }
        scanResults = liveScanResults;
        updateStats();
        renderTable();
        autoSelectFirstRow();
    } else {
        try {
            const res = await fetch(`/api/history-results?date=${encodeURIComponent(val)}`);
            if (!res.ok) throw new Error("無法取得歷史掃描資料");
            const data = await res.json();
            
            scanResults = data;
            updateStats();
            renderTable();
            autoSelectFirstRow();
        } catch (e) {
            alert(`載入歷史紀錄錯誤: ${e.message}`);
        }
    }
}

function autoSelectFirstRow() {
    const vcpStocks = scanResults.filter(r => r.VCP);
    if (vcpStocks.length > 0) {
        loadStockChart(vcpStocks[0].Symbol);
    } else if (scanResults.length > 0) {
        loadStockChart(scanResults[0].Symbol);
    } else {
        currentActiveSymbol = null;
        updateChartStarStatus();
        
        // Clear chart
        if (chartInstance) {
            chartInstance.remove();
            chartInstance = null;
        }
        priceChartDiv.innerHTML = '';
        chartTitle.innerText = "圖表分析 (點擊列表股票載入)";
        chartVcpBadge.style.display = 'none';
        chartSourceBadge.style.display = 'none';
        chartEmpty.style.display = 'flex';
        chartEmpty.querySelector('p').innerText = "點擊掃描結果列表中的股票以載入互動式 K 線圖與波動率收縮指標";
        detailsSection.style.display = 'none';
    }
}

// ==========================================
// WATCHLIST SIDEBAR & STAR BUTTON HANDLERS
// ==========================================

// Fetch and cache ticker names
async function loadTickerNames() {
    try {
        const res = await fetch('/api/ticker-names');
        if (res.ok) {
            tickerNames = await res.json();
        }
    } catch (e) {
        console.error("Failed to load ticker names map", e);
    }
}

// Load and render Watchlist Sidebar
async function loadWatchlistSidebar() {
    try {
        const res = await fetch('/api/watchlist');
        if (res.ok) {
            watchlistSymbols = await res.json();
            renderWatchlistSidebar();
            updateChartStarStatus();
        }
    } catch (e) {
        console.error("Failed to load watchlist sidebar", e);
    }
}

function renderWatchlistSidebar() {
    watchlistItemsContainer.innerHTML = '';
    watchlistCount.innerText = watchlistSymbols.length;
    
    if (watchlistSymbols.length === 0) {
        watchlistItemsContainer.innerHTML = '<div style="text-align: center; color: var(--text-muted); font-size: 11px; padding: 20px 0;">無自選股，請輸入代號新增</div>';
        return;
    }
    
    watchlistSymbols.forEach(sym => {
        const item = document.createElement('div');
        item.className = 'watchlist-item';
        item.dataset.symbol = sym;
        
        const name = tickerNames[sym] || "";
        
        item.innerHTML = `
            <div class="watchlist-item-info">
                <span class="watchlist-item-symbol">${sym}</span>
                ${name ? `<span class="watchlist-item-name">${name}</span>` : ''}
            </div>
            <button class="btn-delete-item" title="從自選股移除">🗑️</button>
        `;
        
        // Click to load chart
        item.addEventListener('click', (e) => {
            if (e.target.closest('.btn-delete-item')) return; // ignore delete click
            loadStockChart(sym);
        });
        
        // Delete button click
        item.querySelector('.btn-delete-item').addEventListener('click', async () => {
            await removeWatchlistItem(sym);
        });
        
        watchlistItemsContainer.appendChild(item);
    });
}

// Add item to watchlist
async function addWatchlistItem() {
    const text = watchlistAddInput.value.trim().toUpperCase();
    if (!text) return;
    
    const symbols = text.split(/[\s,;\n]+/).map(s => s.trim()).filter(s => s.length > 0);
    if (symbols.length === 0) return;
    
    watchlistAddInput.disabled = true;
    
    try {
        for (const sym of symbols) {
            if (!watchlistSymbols.includes(sym)) {
                const res = await fetch('/api/watchlist', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ symbol: sym })
                });
                if (res.ok) {
                    const data = await res.json();
                    watchlistSymbols = data.watchlist;
                }
            }
        }
        watchlistAddInput.value = '';
        renderWatchlistSidebar();
        updateChartStarStatus();
        
        if (presetSelect.value === 'WATCHLIST') {
            await loadWatchlistPreset();
        }
    } catch (e) {
        console.error("Failed to add watchlist item", e);
        alert("新增自選股失敗");
    } finally {
        watchlistAddInput.disabled = false;
        watchlistAddInput.focus();
    }
}

// Remove item from watchlist
async function removeWatchlistItem(sym) {
    try {
        const res = await fetch(`/api/watchlist/${encodeURIComponent(sym)}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            const data = await res.json();
            watchlistSymbols = data.watchlist;
            renderWatchlistSidebar();
            updateChartStarStatus();
            
            if (presetSelect.value === 'WATCHLIST') {
                await loadWatchlistPreset();
            }
        }
    } catch (e) {
        console.error("Failed to delete watchlist item", e);
    }
}

// Toggle Star in Chart Header
async function toggleChartStar() {
    if (!currentActiveSymbol) return;
    
    const sym = currentActiveSymbol;
    if (watchlistSymbols.includes(sym)) {
        await removeWatchlistItem(sym);
    } else {
        watchlistSymbols.push(sym);
        renderWatchlistSidebar();
        updateChartStarStatus();
        
        try {
            const res = await fetch('/api/watchlist', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ symbol: sym })
            });
            if (res.ok) {
                const data = await res.json();
                watchlistSymbols = data.watchlist;
                renderWatchlistSidebar();
                updateChartStarStatus();
            }
        } catch (e) {
            console.error("Failed to save to watchlist via star", e);
        }
        
        if (presetSelect.value === 'WATCHLIST') {
            await loadWatchlistPreset();
        }
    }
}

// Update star button appearance
function updateChartStarStatus() {
    if (!btnChartStar) return;
    if (!currentActiveSymbol) {
        btnChartStar.style.display = 'none';
        return;
    }
    
    btnChartStar.style.display = 'inline-block';
    if (watchlistSymbols.includes(currentActiveSymbol)) {
        btnChartStar.innerText = '★';
        btnChartStar.title = '從自選股移除';
        btnChartStar.style.color = '#ffca28';
    } else {
        btnChartStar.innerText = '☆';
        btnChartStar.title = '加入自選股';
        btnChartStar.style.color = 'var(--text-muted)';
    }
}

// Scan watchlist only
async function scanWatchlistOnly() {
    if (watchlistSymbols.length === 0) {
        alert("您的自選股清單目前為空！請先加入一些股票。");
        return;
    }
    
    presetSelect.value = 'WATCHLIST';
    symbolsInput.value = watchlistSymbols.join(', ');
    symbolsInput.disabled = true;
    
    startScan();
}

// Clear all watchlist sidebar items
async function clearWatchlistSidebar() {
    if (watchlistSymbols.length === 0) return;
    if (!confirm("確定要清空所有自選股嗎？")) return;
    
    btnWatchlistClear.disabled = true;
    try {
        for (const sym of watchlistSymbols) {
            await fetch(`/api/watchlist/${encodeURIComponent(sym)}`, {
                method: 'DELETE'
            });
        }
        watchlistSymbols = [];
        renderWatchlistSidebar();
        updateChartStarStatus();
        
        if (presetSelect.value === 'WATCHLIST') {
            symbolsInput.value = '';
        }
    } catch (e) {
        console.error("Failed to clear watchlist", e);
        alert("清空失敗");
    } finally {
        btnWatchlistClear.disabled = false;
    }
}

// ==========================================
// CUSTOM CONTEXT MENU CONTROLLERS
// ==========================================

function showContextMenu(e, symbol) {
    activeContextSymbol = symbol;
    
    // Update context menu item based on whether symbol is in watchlist
    if (watchlistSymbols.includes(symbol)) {
        ctxToggleWatchlist.innerHTML = '⭐ 從自選股移除';
    } else {
        ctxToggleWatchlist.innerHTML = '⭐ 加入自選股';
    }
    
    // Position context menu at mouse coordinates
    contextMenu.style.left = `${e.pageX}px`;
    contextMenu.style.top = `${e.pageY}px`;
    contextMenu.style.display = 'block';
    
    // Slight entry animation
    contextMenu.style.opacity = '0';
    contextMenu.style.transform = 'scale(0.95)';
    setTimeout(() => {
        contextMenu.style.opacity = '1';
        contextMenu.style.transform = 'scale(1)';
    }, 10);
}

function hideContextMenu() {
    if (contextMenu.style.display === 'block') {
        contextMenu.style.opacity = '0';
        contextMenu.style.transform = 'scale(0.95)';
        setTimeout(() => {
            contextMenu.style.display = 'none';
        }, 150);
    }
}

// ==========================================
// SCAN HISTORY TAB CONTROLLERS
// ==========================================

async function loadHistorySummary() {
    historyRunsTbody.innerHTML = '<tr><td colspan="6" class="empty-state">載入歷史紀錄中...</td></tr>';
    try {
        const res = await fetch('/api/history-summary');
        if (!res.ok) throw new Error("HTTP error " + res.status);
        const data = await res.json();
        
        if (data.length === 0) {
            historyRunsTbody.innerHTML = '<tr><td colspan="6" class="empty-state">無過往篩選歷史紀錄</td></tr>';
            return;
        }
        
        historyRunsTbody.innerHTML = '';
        data.forEach(run => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td style="font-weight: 600;">${run.scan_date}</td>
                <td>${run.total_stocks}</td>
                <td style="color: var(--accent-green); font-weight: 600;">${run.vcp_count}</td>
                <td style="color: var(--accent-cyan); font-weight: 600;">${run.minervini_count}</td>
                <td style="color: var(--accent-pink); font-weight: 600;">${run.breakout_count}</td>
                <td>
                    <button class="btn-load-run" data-date="${run.scan_date}">🔍 載入此紀錄</button>
                    <button class="btn-delete-run" data-date="${run.scan_date}">🗑️ 刪除</button>
                </td>
            `;
            
            // Bind Load Action
            tr.querySelector('.btn-load-run').addEventListener('click', (e) => {
                const dateVal = e.target.getAttribute('data-date');
                // Switch back to scan tab
                tabLiveScan.click();
                // Select the date in dropdown
                historySelect.value = dateVal;
                // Trigger change manually
                const event = new Event('change');
                historySelect.dispatchEvent(event);
            });
            
            // Bind Delete Action
            tr.querySelector('.btn-delete-run').addEventListener('click', async (e) => {
                const dateVal = e.target.getAttribute('data-date');
                if (!confirm(`確定要刪除 ${dateVal} 的掃描紀錄嗎？`)) return;
                try {
                    const delRes = await fetch(`/api/history-scan?date=${encodeURIComponent(dateVal)}`, {
                        method: 'DELETE'
                    });
                    if (delRes.ok) {
                        await loadHistorySummary();
                        await fetchHistoryDates(); // Refresh dropdown select
                    } else {
                        alert("刪除失敗");
                    }
                } catch (err) {
                    console.error("Failed to delete run", err);
                    alert("刪除錯誤");
                }
            });
            
            historyRunsTbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Failed to load history summary", e);
        historyRunsTbody.innerHTML = '<tr><td colspan="6" class="empty-state" style="color: var(--accent-red);">載入失敗</td></tr>';
    }
}

async function clearAllHistoryData() {
    if (!confirm("確定要清空所有歷史數據嗎？此操作不可逆！")) return;
    btnClearAllHistory.disabled = true;
    try {
        const res = await fetch('/api/history-clear-all', { method: 'DELETE' });
        if (res.ok) {
            await loadHistorySummary();
            await fetchHistoryDates(); // Refresh dropdown select
        } else {
            alert("清空失敗");
        }
    } catch (e) {
        console.error("Failed to clear all history", e);
        alert("清空錯誤");
    } finally {
        btnClearAllHistory.disabled = false;
    }
}
