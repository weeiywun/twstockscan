//  STRATEGY REGISTRY
//  新增選股策略只需在這裡加一筆 + 提供 data
// ════════════════════════════════════════════════════
// WARNING: Access control - do not remove. Do not document the parameter value in any public file.
// Tab id=performance requires a specific URL parameter to be visible. Keep parameter value private.
const PERF_UNLOCKED = new URLSearchParams(location.search).get('unlock') === 'perf';
const STRATEGIES = [
  {
    id: "future_dashboard",
    name: "FUTURE DASHBOARD",
    shortName: "FUTURE DASHBOARD",
    icon: "▣",
    group: null,
    available: true,
    description: "整合台股夜盤、美股收盤、三大法人期貨多空、散戶多空比與 PC Ratio，作為進場前的市場溫度計。",
    conditions: [],
    dataUpdated: "載入中...",
    dataSource: "TAIFEX + FinMind",
  },
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
  {
    id: "ssr",
    name: "SSR 交集雷達",
    shortName: "SSR",
    icon: "✦",
    group: "ssr",
    available: true,
    description: "彙整籌碼集中、VCP、突破策略、投信動能四組核心選股，找出同時命中 2 組以上的高共振標的。",
    conditions: [
      "C4 取 2：籌碼集中、VCP、突破策略、投信動能任兩組同時命中",
      "三組以上：四組核心策略任三組以上同時命中",
      "VCP 命中含嚴格 VCP 與潛在 VCP，並在表格中保留分級",
      "此頁只做交集總覽，不改變各策略原本的篩選邏輯",
    ],
    dataUpdated: "載入中...",
    dataSource: "前端彙整既有策略結果",
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
      "股價乖離 EMA120：0%～10%",
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
    name: "量增訊號標的追蹤",
    shortName: "標的追蹤",
    icon: "◎",
    group: "chips",
    available: true,
    description: "籌碼集中入池標的首次觸發量增訊號後，維護月營收評級、現價損益與 10 個交易日觀察期。",
    conditions: [],
  },
  // ── 策略二：突破策略 ──
  {
    id: "vcp",
    name: "VCP 選股",
    shortName: "VCP",
    icon: "◈",
    group: "vcp",
    available: true,
    description: "掃描符合 Mark Minervini《超級績效》VCP 型態（Volatility Contraction Pattern）的標的，分成潛在 VCP 與嚴格 VCP：先找 Stage 2 上升趨勢、波動遞減收縮、量能萎縮與緊縮樞紐，再依段數、pivot 位置與量縮品質分級。",
    conditions: [
      "潛在 VCP：已完成週 K 出現 2 段以上 H→L 收縮，深度遞減",
      "VCP：至少 3 段收縮，最後一段 ≤ 10%，且靠近 pivot",
      "Stage 2：收盤 > MA50 > MA100，且 MA100 在過去 20 個交易日上升",
      "Pivot：VCP 需在樞紐下方 5% 到上方 3% 內，避免過早或已延伸",
      "量縮：最後收縮段量 ≤ 第一段 70%，近 5 日均量 ≤ 50 日均量 80%",
    ],
    dataUpdated: "載入中...",
    dataSource: "FinMind（每日盤後）",
    dataKey: "vcp_data",
  },
  {
    id: "right_top",
    name: "突破策略",
    shortName: "突破策略",
    icon: "▲",
    group: "right_top",
    available: true,
    description: "整合原右上角的盤整突破與日線動能突破，區分低波動打底後發動與強勢多頭續攻兩種型態。",
    conditions: [
      "盤整突破：週收盤突破前 10 週高點，且突破前 10 週波動 < 20%",
      "盤整突破：前 3 週未創 10 週新高，保留原本第一根突破精神",
      "動能突破：Close > MA20 > MA60，日線突破前 60 日高",
      "動能突破：突破前 10 日貼近 MA20 整理，今日量 ≥ 前 5 日均量 × 1.5",
      "風險控制：MA20 乖離 < 10%，並以大戶近 3 週連增作為品質標籤",
    ],
    dataUpdated: "載入中...",
    dataSource: "FinMind + 集保大戶資料",
    dataKey: "right_top_data",
  },
  {
    id: "right_top_track",
    name: "標的追蹤",
    shortName: "標的追蹤",
    icon: "◉",
    group: "right_top",
    available: true,
    description: "突破策略觸發標的的後續追蹤，記錄入選收盤、現價、損益，觀察期 10 個交易日。",
    conditions: [],
  },
  // ── 策略三：資金動能 ──
  {
    id: "trust_momentum",
    name: "投信動能",
    shortName: "投信動能",
    icon: "◆",
    group: "funds",
    available: true,
    description: "追蹤投信近 5～10 日買超動能，找出連續買、買超占成交量有感，且股價尚未過度延伸的資金推升標的。",
    conditions: [
      "投信近 5 日買超 ≥ 3 日，或近 10 日買超 ≥ 6 日",
      "近 5 日與近 10 日投信累計買超皆為正",
      "投信近 5 日買超 / 近 20 日均量 × 5 ≥ 8%",
      "20 日均量 ≥ 500 張",
      "排除 5 日漲幅 > 25% 或 MA20 乖離 > 18% 的過熱標的",
    ],
    dataUpdated: "載入中...",
    dataSource: "TWSE/TPEx 官方投信買賣超 + price_cache",
    dataKey: "trust_momentum_data",
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
  market_index_data:      null,
  futures_dashboard_data: null,
  vcp_data:               [],
  vcp_potential_data:     [],
  vcp_industry:           [],
  vcp_potential_industry: [],
  right_top_data:         [],
  right_top_industry:     [],
  right_top_track_data:   null,
  trust_momentum_data:    [],
  trust_momentum_industry: [],
};
let DATE_LABELS = [];

// ════════════════════════════════════════════════════
//  STATE
// ════════════════════════════════════════════════════
let activeStratId = (PERF_UNLOCKED ? STRATEGIES[0] : (STRATEGIES.find(s => s.id !== "performance") || STRATEGIES[0])).id;
let sortCol = "chg_2w_1000";
let sortAsc = false;
let chipsViewMode = "stock"; // "stock" | "industry"
let expandedRow = null;
let aiData = null;

function dateTW(offsetDays = 0) {
  const date = new Date(Date.now() + offsetDays * 86400000);
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Taipei',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map(p => [p.type, p.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function formatLocalDate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function addTradingDaysTW(days) {
  const [year, month, day] = dateTW().split('-').map(Number);
  const date = new Date(year, month - 1, day);
  let added = 0;
  while (added < days) {
    date.setDate(date.getDate() + 1);
    const day = date.getDay();
    if (day !== 0 && day !== 6) added++;
  }
  return formatLocalDate(date);
}

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
  ssr:       'SSR',
  chips:     '籌碼選股',
  vcp:       'VCP',
  right_top: '突破策略',
  funds:     '資金動能',
};

function _navBadge(s) {
  if (!s.available) return '—';
  if (s.id === 'future_dashboard') return DATA.futures_dashboard_data?.summary?.bias || '—';
  if (s.id === 'performance') return (DATA.performance_data?.positions || []).filter(p => !p.confirmed).length;
  if (s.id === 'ssr') return typeof buildSSRRows === 'function' ? buildSSRRows().length : '—';
  if (s.id === 'stock_analysis') return DATA.stock_analysis_data?.active?.length ?? '—';
  if (s.id === 'vcp')             return (DATA.vcp_data || []).length + (DATA.vcp_potential_data || []).length;
  if (s.id === 'right_top_track') return DATA.right_top_track_data?.active?.length ?? '—';
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

function _updateHdrBtns() {
  const btnFuture = document.getElementById('hdrBtnFuture');
  const btnPerf   = document.getElementById('hdrBtnPerf');
  if (!btnFuture) return;

  // 績效按鈕：需解鎖才顯示
  if (btnPerf) btnPerf.style.display = PERF_UNLOCKED ? '' : 'none';

  [btnFuture, btnPerf].forEach(btn => {
    if (!btn || btn.style.display === 'none') return;
    const isActive = btn.id === 'hdrBtnFuture'
      ? activeStratId === 'future_dashboard'
      : activeStratId === 'performance';
    btn.style.background     = isActive ? 'var(--bg3)' : 'none';
    btn.style.borderColor    = isActive ? 'var(--border)' : 'transparent';
    btn.style.color          = isActive ? 'var(--text)'  : 'var(--text2)';
  });
}

function renderNav() {
  const nav = document.getElementById('strategyNav');
  let html = '';

  _updateHdrBtns();

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
    const label = NAV_GROUP_LABELS[g];
    const collapsed = localStorage.getItem(`nav_group_collapsed_${g}`) === '1';
    if (label) {
      const totalCount = grouped[g].reduce((n, s) => { const b = _navBadge(s); return n + (+b || 0); }, 0);
      html += `<button onclick="toggleNavGroup('${g}')"
        style="display:flex;align-items:center;gap:4px;padding:0 8px 0 6px;font-size:10px;font-weight:600;
               color:var(--text3);letter-spacing:.06em;white-space:nowrap;background:none;border:none;
               cursor:pointer;height:100%;transition:color .15s;font-family:var(--sans)"
        onmouseover="this.style.color='var(--text1)'" onmouseout="this.style.color='var(--text3)'">
        ${label}${collapsed ? `<span class="badge" style="margin-left:2px">${totalCount}</span>` : ''}
        <span style="font-size:9px;opacity:.7">${collapsed ? '▶' : '▼'}</span>
      </button>`;
    }
    if (!collapsed) {
      grouped[g].forEach(s => { html += _navTab(s); });
    }
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
  if (strat.id === 'future_dashboard') { renderFutureDashboard(strat, main); return; }
  if (strat.id === 'ssr')              { renderSSR(strat, main);             return; }
  if (strat.id === 'chips_big_holder') { renderChipsHolder(strat, main);    return; }
  if (strat.id === 'volume_signal')    { renderVolumeSignal(strat, main);   return; }
  if (strat.id === 'stock_analysis')   { renderStockAnalysis(strat, main);  return; }
  if (strat.id === 'vcp')              { renderVCP(strat, main);               return; }
  if (strat.id === 'right_top')        { renderRightTop(strat, main);          return; }
  if (strat.id === 'right_top_track') { renderRightTopTrack(strat, main);     return; }
  if (strat.id === 'trust_momentum')   { renderTrustMomentum(strat, main);     return; }
  if (strat.id === 'performance')      { renderPerformance(strat, main);    return; }
}

function toggleNavGroup(g) {
  const key = `nav_group_collapsed_${g}`;
  localStorage.setItem(key, localStorage.getItem(key) === '1' ? '0' : '1');
  renderNav();
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
  if (id === "performance" && !PERF_UNLOCKED) return;
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
    const [chipsRes, vsRes, aiRes, saRes, perfRes, miRes, fdRes, vcpRes, rtRes, rttRes, tmRes] = await Promise.all([
      fetch(`data/chips_big_holder.json?t=${timestamp}`,   { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`data/volume_signal.json?t=${timestamp}`,      { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`data/ai_recommendations.json?t=${timestamp}`, { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`data/ai_analysis.json?t=${timestamp}`,        { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`data/performance.json?t=${timestamp}`,        { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`data/market_index.json?t=${timestamp}`,        { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`data/futures_dashboard.json?t=${timestamp}`,   { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`data/vcp.json?t=${timestamp}`,                { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`data/right_top.json?t=${timestamp}`,          { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`data/right_top_track.json?t=${timestamp}`,    { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`data/trust_momentum.json?t=${timestamp}`,     { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
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
      if (strat) {
        strat.dataUpdated  = (chipsRes.updated      || '').slice(0, 10) || strat.dataUpdated;
        strat.priceUpdated = (chipsRes.price_updated || '').slice(0, 10) || '';
      }
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

    if (miRes && miRes.indices) {
      DATA.market_index_data = miRes;
    }

    if (fdRes) {
      DATA.futures_dashboard_data = fdRes;
      const strat = STRATEGIES.find(s => s.id === 'future_dashboard');
      if (strat) strat.dataUpdated = (fdRes.date || fdRes.updated || '').slice(0, 10) || strat.dataUpdated;
    }

    if (vcpRes && vcpRes.results) {
      DATA.vcp_data     = vcpRes.results;
      DATA.vcp_potential_data = vcpRes.potential_results || [];
      DATA.vcp_industry = vcpRes.industry_stats || [];
      DATA.vcp_potential_industry = vcpRes.potential_industry_stats || [];
      const strat = STRATEGIES.find(s => s.id === 'vcp');
      if (strat) strat.dataUpdated = (vcpRes.updated || '').slice(0, 10) || strat.dataUpdated;
    }

    if (rtRes && rtRes.results) {
      DATA.right_top_data     = rtRes.results;
      DATA.right_top_industry = rtRes.industry_stats || [];
      const strat = STRATEGIES.find(s => s.id === 'right_top');
      if (strat) strat.dataUpdated = (rtRes.updated || '').slice(0, 10) || strat.dataUpdated;
    }

    if (tmRes && tmRes.results) {
      DATA.trust_momentum_data = tmRes.results;
      DATA.trust_momentum_industry = tmRes.industry_stats || [];
      const strat = STRATEGIES.find(s => s.id === 'trust_momentum');
      if (strat) strat.dataUpdated = (tmRes.source_date || tmRes.updated || '').slice(0, 10) || strat.dataUpdated;
    }

    const ssrStrat = STRATEGIES.find(s => s.id === 'ssr');
    if (ssrStrat) {
      const dates = ['chips_big_holder', 'vcp', 'right_top', 'trust_momentum']
        .map(id => STRATEGIES.find(s => s.id === id)?.dataUpdated)
        .filter(d => d && d !== '載入中...');
      ssrStrat.dataUpdated = dates.length ? dates.sort().slice(-1)[0] : ssrStrat.dataUpdated;
    }

    if (rttRes && (rttRes.active || rttRes.expired)) {
      DATA.right_top_track_data = rttRes;
    }

  } catch (e) {
    console.error('資料載入失敗:', e);
  }

  // 套用最新現價（若 current_prices.json 存在且日期在今日或昨日）
  try {
    const cpRes = await fetch(`data/current_prices.json?t=${timestamp}`, { cache: 'no-store' }).catch(() => null);
    if (cpRes && cpRes.ok) {
      const cpData = await cpRes.json();
      if (cpData && cpData.prices) {
        const today = dateTW();
        const yesterday = dateTW(-1);
        if (cpData.date === today || cpData.date === yesterday) {
          if (typeof _applyPriceToChips    === 'function') _applyPriceToChips(cpData.prices);
          if (typeof _applyPriceToVolumeSignal === 'function') _applyPriceToVolumeSignal(cpData.prices);
          if (typeof _applyPriceToVCP       === 'function') _applyPriceToVCP(cpData.prices);
          if (typeof _applyPriceToRightTop === 'function') _applyPriceToRightTop(cpData.prices);
          if (typeof _applyPriceToRttTrack === 'function') _applyPriceToRttTrack(cpData.prices);
          if (typeof _applyPriceToTrustMomentum === 'function') _applyPriceToTrustMomentum(cpData.prices);
          if (typeof _applyPriceToAnalysis === 'function') _applyPriceToAnalysis(cpData.prices);
          if (typeof _applyPriceToPerf === 'function') await _applyPriceToPerf(cpData.prices, cpData.date, false);
        }
      }
    }
  } catch (e) {
    console.warn('current_prices.json 套用失敗:', e);
  }

  // 資料載入完成後渲染
  renderNav();
  renderStrategy();
}

loadData();
