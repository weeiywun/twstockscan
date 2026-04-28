//  STRATEGY REGISTRY
//  新增選股策略只需在這裡加一筆 + 提供 data
// ════════════════════════════════════════════════════
const PERF_UNLOCKED = new URLSearchParams(location.search).get('unlock') === 'perf';
const STRATEGIES = [
  {
    id: "performance",
    name: "績效追蹤",
    shortName: "績效追蹤",
    icon: "◐",
    group: null,   // null = 不屬於任何策略群組，獨立置頂
    available: true,
    description: "記錄建倉出場，追蹤整體投組績效。",
    conditions: [],
  },
  // ── 策略一：籌碼選股 ──
  {
    id: "chips_big_holder",
    name: "籌碼集中",
    shortName: "籌碼集中",
    icon: "◈",
    group: "chips",
    available: true,
    description: "週末籌碼海選：追蹤千張大戶與 400 張大戶持股相對成長率（R），標記持續成長、雙軌觸發、單周增幅三類標籤，篩選低基期且量能充足的標的。",
    conditions: [
      "5日均量 > 500 張",
      "千張大戶比例 > 30%",
      "股價乖離 EMA120：±10% 以內",
      "布林帶寬 BBW ≤ 15%",
      "持續成長：連續兩週 R > 0%",
      "雙軌觸發：R_400 ≥ 1.0% 且 R_1000 ≥ 1.0%",
      "單周增幅：任一門檻單週 R > 3.0%",
    ],
    dataUpdated: "載入中...",
    dataSource: "集保開放資料 + FinMind",
    dataKey: "chips_big_holder_data",
  },
  {
    id: "volume_signal",
    name: "量增訊號",
    shortName: "量增訊號",
    icon: "◆",
    group: "chips",
    available: true,
    description: "每日盤後針對籌碼集中入池標的掃描量能突破訊號，捕捉主力啟動時機。",
    conditions: [
      "來源：籌碼集中入池標的",
      "當日成交量 ≥ 10日均量 × 1.5",
      "收盤價 > EMA5",
    ],
    dataUpdated: "載入中...",
    dataSource: "FinMind（每日盤後）",
    dataKey: "volume_signal_data",
  },
  {
    id: "stock_analysis",
    name: "標的分析",
    shortName: "標的分析",
    icon: "◎",
    group: "chips",
    available: true,
    description: "籌碼集中入池標的首次觸發量增訊號時啟動 AI 分析，結合新聞與量化數據評分，追蹤觀察 10 天。",
    conditions: [],
  },
  // ── 策略二：右上角 ──
  {
    id: "right_top",
    name: "右上角",
    shortName: "右上角",
    icon: "▲",
    group: "right_top",
    available: true,
    description: "全市場掃描週K第一根突破近 10 週收盤新高，且週量能同步放大的標的，並統計族群共振效應。",
    conditions: [
      "最新週收盤 > 前 10 週最高收盤（週K創新高）",
      "前 3 週皆未創10週新高（排除強勢延續，確認第一根）",
      "突破前10週價格波動幅度 < 20%（橫盤打底確認）",
      "突破前10週均線斜率 < 5%（排除均線已走揚的趨勢股）",
      "最新週成交量 ≥ 20週均量 × 1.5",
      "20週均量 ≥ 500 張（流動性門檻）",
      "掃描範圍：全市場上市 + 上櫃一般股（排除 ETF）",
    ],
    dataUpdated: "載入中...",
    dataSource: "FinMind（每日盤後）",
    dataKey: "right_top_data",
  },
];


// ════════════════════════════════════════════════════
//  DATA
// ════════════════════════════════════════════════════
const DATA = {
  chips_big_holder_data:  [],
  volume_signal_data:     [],
  stock_analysis_data:    null,
  performance_data:       null,
  right_top_data:         [],
  right_top_industry:     [],
};
let DATE_LABELS = [];

// ════════════════════════════════════════════════════
//  STATE
// ════════════════════════════════════════════════════
let activeStratId = STRATEGIES[0].id;
let sortCol = "chg_2w_1000";
let sortAsc = false;
let chipsViewMode = "stock"; // "stock" | "industry"
let expandedRow = null;
let watchlist = JSON.parse(localStorage.getItem("watchlist") || "[]");
let aiData = null;

// ════════════════════════════════════════════════════
//  TRADINGVIEW APP DEEP LINK
//  手機上優先呼出 TradingView App（需已安裝），
//  未安裝時 fallback 到網頁版；桌機直接開新分頁。
// ════════════════════════════════════════════════════
function openTV(tvSymbol, event) {
  event.stopPropagation();
  event.preventDefault();
  const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
  // 使用完整 https URL；iOS/Android 上 TradingView 已註冊 universal link，
  // 安裝後會自動攔截並在 App 內開啟正確標的圖表。
  const webUrl = `https://www.tradingview.com/chart/?symbol=${tvSymbol}`;
  if (isMobile) {
    // 先嘗試 custom scheme（冒號不編碼，App 才能正確解析 symbol）
    const appUrl = `tradingview://chart?symbol=${tvSymbol}`;
    const t0 = Date.now();
    window.location.href = appUrl;
    // App 未安裝時 300ms 後 fallback 到網頁版（universal link）
    setTimeout(() => {
      if (Date.now() - t0 < 800) window.open(webUrl, '_blank');
    }, 300);
  } else {
    window.open(webUrl, '_blank');
  }
}

// ════════════════════════════════════════════════════
//  EXCHANGE DETECTION
//  資料若有 market 欄位（"TWSE"/"TPEX"）優先採用，
//  否則依代號範圍推算（非 100% 精確）
// ════════════════════════════════════════════════════
function guessMarket(stockId) {
  const n = parseInt(stockId, 10);
  if (n >= 1000 && n <= 2999) return 'TWSE';   // 上市
  if (n >= 3000 && n <= 3499) return 'TWSE';   // 上市居多
  if (n >= 3500 && n <= 3999) return 'TPEX';   // 上櫃居多
  if (n >= 4000 && n <= 4999) return 'TPEX';   // 上櫃
  if (n >= 5000 && n <= 5999) return 'TPEX';   // 上櫃居多
  if (n >= 6000 && n <= 6999) return 'TPEX';   // 上櫃居多
  if (n >= 7000 && n <= 9999) return 'TPEX';   // 上櫃
  return 'TWSE';                                 // fallback
}

function getTVSymbol(d) {
  const market = d.market || guessMarket(d.stock_id);
  return `${market}:${d.stock_id}`;
}

// ════════════════════════════════════════════════════
//  RENDER HELPERS
// ════════════════════════════════════════════════════
function sparkBars(trend) {
  const min = Math.min(...trend), max = Math.max(...trend);
  const range = max - min || 1;
  return trend.map(v => {
    const h = Math.round(((v - min) / range) * 18) + 6;
    return `<span class="spark-bar" style="height:${h}px"></span>`;
  }).join('');
}

function trendBars(trend, label, colorClass) {
  const max = Math.max(...trend);
  return [...trend].reverse().map((v, i) => `
    <div class="trend-row">
      <span class="trend-date">${DATE_LABELS[DATE_LABELS.length - 1 - i]}</span>
      <div class="trend-bar-wrap">
        <div class="trend-bar ${colorClass}" style="width:${(v/max*100).toFixed(1)}%"></div>
      </div>
      <span class="trend-val">${v.toFixed(2)}%</span>
    </div>`).join('');
}

// ════════════════════════════════════════════════════
//  RENDER STRATEGY TABS
// ════════════════════════════════════════════════════
const NAV_GROUP_LABELS = {
  chips:     '籌碼選股',
  right_top: '右上角',
};

function _navBadge(s) {
  if (!s.available) return '—';
  if (s.id === 'performance') return (DATA.performance_data?.positions || []).filter(p => !p.confirmed).length;
  if (s.id === 'stock_analysis') return DATA.stock_analysis_data?.active?.length ?? '—';
  return (DATA[s.dataKey] || []).length;
}

function _navTab(s) {
  const badge = `<span class="badge">${_navBadge(s)}</span>`;
  return `<button class="strat-tab ${s.id===activeStratId?'active':''} ${!s.available?'locked':''}"
    onclick="${s.available ? `setStrategy('${s.id}')` : ''}"
    title="${!s.available ? (s.comingSoon||'即將推出') : ''}">
    ${s.icon} ${s.shortName}${badge}
  </button>`;
}

function renderNav() {
  const nav = document.getElementById('strategyNav');
  let html = '';

  // 績效：獨立置頂（需解鎖）
  const perf = STRATEGIES.find(s => s.id === 'performance');
  if (PERF_UNLOCKED && perf) {
    html += _navTab(perf);
    html += `<div style="width:1px;background:var(--border);margin:10px 6px;align-self:stretch;flex-shrink:0"></div>`;
  }

  // 依 group 分組渲染
  const groupOrder = [];
  const grouped = {};
  STRATEGIES.filter(s => s.group !== null).forEach(s => {
    const g = s.group;
    if (!grouped[g]) { grouped[g] = []; groupOrder.push(g); }
    grouped[g].push(s);
  });

  groupOrder.forEach((g, i) => {
    if (i > 0) {
      html += `<div style="width:1px;background:var(--border);margin:10px 6px;align-self:stretch;flex-shrink:0"></div>`;
    }
    if (NAV_GROUP_LABELS[g]) {
      html += `<div style="display:flex;align-items:center;padding:0 6px 0 4px;font-size:10px;font-weight:600;
                            color:var(--text3);letter-spacing:.06em;white-space:nowrap;user-select:none">
                 ${NAV_GROUP_LABELS[g]}
               </div>`;
    }
    grouped[g].forEach(s => { html += _navTab(s); });
  });

  nav.innerHTML = html;
}

// ════════════════════════════════════════════════════
//  RENDER ACTIVE STRATEGY
// ════════════════════════════════════════════════════
function renderStrategy() {
  const strat = STRATEGIES.find(s => s.id === activeStratId);
  const main = document.getElementById('mainContent');

  if (!strat.available) {
    main.innerHTML = `<div class="coming-soon">
      <div class="coming-icon">${strat.icon}</div>
      <div class="coming-title">${strat.name}</div>
      <div class="coming-desc">${strat.description}<br><br><span style="color:var(--amber)">${strat.comingSoon}</span></div>
    </div>`;
    return;
  }

  if (strat.id !== 'performance' && typeof setPerfSidebarMode === 'function') setPerfSidebarMode(false);
  if (strat.id === 'chips_big_holder') { renderChipsHolder(strat, main);    return; }
  if (strat.id === 'volume_signal')    { renderVolumeSignal(strat, main);   return; }
  if (strat.id === 'stock_analysis')   { renderStockAnalysis(strat, main);  return; }
  if (strat.id === 'right_top')        { renderRightTop(strat, main);       return; }
  if (strat.id === 'performance')      { renderPerformance(strat, main);    return; }
}

function renderWatchlist() {
  if (watchlist.length === 0) {
    return `<div class="watch-empty">點擊結果列<br>加入觀察清單</div>`;
  }
  // 跨策略查找名稱：遍歷所有有資料的策略
  function findName(sid) {
    for (const s of STRATEGIES) {
      if (!s.available || !s.dataKey) continue;
      const item = (DATA[s.dataKey] || []).find(d => d.stock_id === sid);
      if (item) return item.name;
    }
    return '—';
  }
  return watchlist.map(sid => {
    const name = findName(sid);
    return `<div class="watch-card">
      <span class="watch-card-code">${sid}</span>
      <span class="watch-card-name">${name}</span>
      <span class="watch-card-remove" onclick="event.stopPropagation();removeWatch('${sid}')">×</span>
    </div>`;
  }).join('');
}

// ════════════════════════════════════════════════════
//  AI 推薦卡片
// ════════════════════════════════════════════════════
function renderAICard() {
  if (!aiData) {
    return `<div class="ai-card">
      <div class="ai-card-header">
        <span class="ai-card-title">✦ AI 選股推薦</span>
        <span class="ai-card-meta">尚未載入</span>
      </div>
      <div class="ai-card-empty">AI 分析資料尚未產生，下次選股後自動更新</div>
    </div>`;
  }
  if (!aiData.ranked || aiData.ranked.length === 0) {
    return `<div class="ai-card">
      <div class="ai-card-header">
        <span class="ai-card-title">✦ AI 選股推薦</span>
      </div>
      <div class="ai-card-empty">本週無推薦標的</div>
    </div>`;
  }

  const top3 = aiData.ranked.slice(0, 3);
  const rankColors  = ['var(--green)', 'var(--amber)', 'var(--blue)'];
  const genTime = (aiData.generated_at || '').slice(0, 16).replace('T', ' ');

  const itemsHTML = top3.map((item, i) => `
    <div class="ai-rank-item">
      <div class="ai-rank-badge" style="color:${rankColors[i]};border-color:${rankColors[i]}">#${item.rank}</div>
      <div class="ai-rank-info">
        <div class="ai-rank-stock">
          <span class="stock-code">${item.stock_id}</span>
          <span style="font-size:13px;font-weight:500;color:var(--text)">${item.name}</span>
        </div>
        <div class="ai-rank-reason">${item.reason}</div>
      </div>
      <div class="ai-score">
        <span class="ai-score-val" style="color:${rankColors[i]}">${item.score}</span>
        <span class="ai-score-label">分</span>
      </div>
    </div>`).join('');

  return `<div class="ai-card">
    <div class="ai-card-header">
      <span class="ai-card-title">✦ AI 選股推薦</span>
      <span class="ai-card-meta">${aiData.model || 'gemini-2.0-flash'} · ${genTime}</span>
    </div>
    <div class="ai-card-body">${itemsHTML}</div>
    <div class="ai-card-footer">依波段偏好排序：大戶增持幅度 · 低乖離 · 基本面獲利能力</div>
  </div>`;
}

// ════════════════════════════════════════════════════
//  INTERACTIONS
// ════════════════════════════════════════════════════
function setStrategy(id) {
  activeStratId = id;
  expandedRow = null;
  renderNav();
  renderStrategy();
}

function sort(col) {
  if (sortCol === col) sortAsc = !sortAsc;
  else { sortCol = col; sortAsc = false; }
  renderStrategy();
}

function toggleExpand(sid) {
  const prev = expandedRow;
  if (prev) {
    document.getElementById(`expand-${prev}`).style.display = 'none';
    document.getElementById(`row-${prev}`).classList.remove('expanded');
  }
  if (prev !== sid) {
    document.getElementById(`expand-${sid}`).style.display = 'table-row';
    document.getElementById(`row-${sid}`).classList.add('expanded');
    expandedRow = sid;
  } else {
    expandedRow = null;
  }
}


function toggleWatch(sid, name) {
  if (watchlist.includes(sid)) {
    watchlist = watchlist.filter(s => s !== sid);
  } else {
    watchlist.push(sid);
  }
  localStorage.setItem("watchlist", JSON.stringify(watchlist));
  const btn = document.getElementById(`watchBtn-${sid}`);
  if (btn) {
    const inWatch = watchlist.includes(sid);
    btn.textContent = inWatch ? '✓ 已加入觀察清單' : '+ 加入觀察清單';
    btn.style.background = inWatch ? 'var(--green-dim)' : 'var(--bg3)';
    btn.style.borderColor = inWatch ? 'var(--green)' : 'var(--border)';
    btn.style.color = inWatch ? 'var(--green)' : 'var(--text2)';
  }
  const grid = document.getElementById('watchlistGrid');
  if (grid) grid.innerHTML = renderWatchlist();
}

function removeWatch(sid) {
  watchlist = watchlist.filter(s => s !== sid);
  localStorage.setItem("watchlist", JSON.stringify(watchlist));
  const grid = document.getElementById('watchlistGrid');
  if (grid) grid.innerHTML = renderWatchlist();
}

function exportCSV() {
  const strat = STRATEGIES.find(s => s.id === activeStratId);
  const data = DATA[strat.dataKey] || [];
  if (!data.length) return;

  const dateRow = DATE_LABELS.length ? DATE_LABELS.join(' / ') : strat.dataUpdated;
  const headers = [
    '代號', '名稱', '產業',
    '現價', '乖離EMA120(%)',
    '大戶比例(%)', '4週增幅(%)',
    `大戶趨勢(${dateRow})`,
    `散戶趨勢(${dateRow})`,
    '資料日期'
  ];

  const rows = data.map(d => [
    d.stock_id,
    d.name,
    d.industry || '',
    d.close.toFixed(1),
    (d.deviation >= 0 ? '+' : '') + d.deviation.toFixed(2),
    d.big_pct_latest.toFixed(2),
    (d.big_4w_chg >= 0 ? '+' : '') + d.big_4w_chg.toFixed(2),
    d.big_trend   ? d.big_trend.map(v => v.toFixed(2)).join(' / ')   : '',
    d.retail_trend? d.retail_trend.map(v => v.toFixed(2)).join(' / '): '',
    strat.dataUpdated
  ]);

  const csv = [headers, ...rows]
    .map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
    .join('\r\n');

  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = `${strat.id}_${strat.dataUpdated}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}


//  INIT — 從 JSON 載入資料後再渲染
// ════════════════════════════════════════════════════
async function loadData() {
  // 加入時間戳避免快取問題（瀏覽器 + CDN）
  const timestamp = new Date().getTime();

  try {
    const [chipsRes, vsRes, aiRes, saRes, perfRes, rtRes] = await Promise.all([
      fetch(`data/chips_big_holder.json?t=${timestamp}`,   { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`data/volume_signal.json?t=${timestamp}`,      { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`data/ai_recommendations.json?t=${timestamp}`, { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`data/ai_analysis.json?t=${timestamp}`,        { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`data/performance.json?t=${timestamp}`,        { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`data/right_top.json?t=${timestamp}`,          { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
    ]);

    if (chipsRes && chipsRes.results) {
      DATA.chips_big_holder_data = chipsRes.results.map(d => {
        const t1 = d.big_trend_1000;
        const t4 = d.big_trend_400;
        return {
          ...d,
          chg_2w_1000: t1 && t1.length >= 4 ? +(t1[3] - t1[1]).toFixed(2) : null,
          chg_2w_400:  t4 && t4.length >= 4 ? +(t4[3] - t4[1]).toFixed(2) : null,
        };
      });
      const strat = STRATEGIES.find(s => s.id === 'chips_big_holder');
      if (strat) strat.dataUpdated = (chipsRes.updated || '').slice(0, 10) || strat.dataUpdated;
    }

    if (vsRes && vsRes.results) {
      DATA.volume_signal_data = vsRes.results;
      const strat = STRATEGIES.find(s => s.id === 'volume_signal');
      if (strat) strat.dataUpdated = (vsRes.updated || '').slice(0, 10) || strat.dataUpdated;
    }

    if (aiRes && aiRes.ranked) {
      aiData = aiRes;
    }

    if (saRes && (saRes.active || saRes.expired)) {
      DATA.stock_analysis_data = saRes;
    }

    if (perfRes) {
      DATA.performance_data = perfRes;
    }

    if (rtRes && rtRes.results) {
      DATA.right_top_data     = rtRes.results;
      DATA.right_top_industry = rtRes.industry_stats || [];
      const strat = STRATEGIES.find(s => s.id === 'right_top');
      if (strat) strat.dataUpdated = (rtRes.updated || '').slice(0, 10) || strat.dataUpdated;
    }
  } catch (e) {
    console.error('資料載入失敗:', e);
  }

  // 資料載入完成後渲染
  renderNav();
  renderStrategy();
  document.getElementById('headerMeta').textContent =
    `策略數 ${STRATEGIES.filter(s=>s.available).length} / 觀察 ${watchlist.length}`;
}

loadData();
