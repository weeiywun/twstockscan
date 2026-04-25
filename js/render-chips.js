// ════════════════════════════════════════════════════
//  族群柱狀圖 TOP 6（按入選數量，同數量以平均增幅排序）
// ════════════════════════════════════════════════════
function renderIndustryChart(allData) {
  const groups = {};
  allData.forEach(d => {
    const ind = d.industry || '其他';
    if (!groups[ind]) groups[ind] = [];
    groups[ind].push(d);
  });
  const top6 = Object.entries(groups)
    .map(([name, items]) => ({
      name,
      count: items.length,
      avg: items.reduce((s, d) => s + (d.cumulative_3w || 0), 0) / items.length
    }))
    .sort((a, b) => b.count !== a.count ? b.count - a.count : b.avg - a.avg)
    .slice(0, 6);
  if (!top6.length) return '';
  const maxCount = top6[0].count;
  const bars = top6.map(g => {
    const pct = (g.count / maxCount * 100).toFixed(1);
    const avgSign = g.avg >= 0 ? '+' : '';
    return `<div class="ind-bar-row">
      <div class="ind-bar-label" title="${g.name}">${g.name}</div>
      <div class="ind-bar-track">
        <div class="ind-bar-fill" style="width:${pct}%">
          <span class="ind-bar-count">${g.count} 支</span>
        </div>
      </div>
      <div class="ind-bar-avg">${avgSign}${g.avg.toFixed(2)}%</div>
    </div>`;
  }).join('');
  return `<div class="industry-chart">
    <div class="industry-chart-hd">族群分布 TOP 6　<span style="font-weight:400;color:var(--text3)">依入選數量 / 同數量以平均3週增幅排序</span></div>
    ${bars}
  </div>`;
}

// ════════════════════════════════════════════════════
//  籌碼集中：渲染器
// ════════════════════════════════════════════════════
function renderChipsHolder(strat, main) {
  const allData = DATA.chips_big_holder_data || [];

  if (allData.length === 0) {
    main.innerHTML = `<div class="coming-soon">
      <div class="coming-icon">${strat.icon}</div>
      <div class="coming-title">${strat.name}</div>
      <div class="coming-desc">資料尚未產生，請至 GitHub Actions → <b>大戶持股分析</b> → <b>Run workflow</b><br>執行後約 5 分鐘資料將自動更新。</div>
    </div>`;
    return;
  }

  // 排序（個股模式）
  function combined3w(d) { return (d.cumulative_3w || 0) + (d.cumulative_3w_400 || 0); }

  const sortedData = allData.slice().sort((a, b) => {
    const va = a[sortCol] ?? -9999;
    const vb = b[sortCol] ?? -9999;
    return sortAsc ? va - vb : vb - va;
  });

  // 族群模式：按族群平均三周累積增幅分組
  function buildIndustryGroups(data) {
    const groups = {};
    data.forEach(d => {
      const ind = d.industry || '其他';
      if (!groups[ind]) groups[ind] = [];
      groups[ind].push(d);
    });
    return Object.entries(groups).map(([name, items]) => {
      const avg = items.reduce((s, d) => s + combined3w(d), 0) / items.length;
      items.sort((a, b) => combined3w(b) - combined3w(a));
      return { name, items, avg: Math.round(avg * 100) / 100 };
    }).sort((a, b) => b.avg - a.avg);
  }

  const tagColor = { '持續成長': '#3a86ff', '雙軌觸發': '#e66e29', '單周增幅': '#e63946', '外資連買': '#00b894', '投信連買': '#a29bfe' };

  function tagBadges(tags) {
    if (!tags || !tags.length) return '';
    return tags.map(t =>
      `<span class="tag-badge" style="background:${tagColor[t] || '#888'}">${t}</span>`
    ).join('');
  }

  function consecutiveBadge(weeks) {
    if (!weeks || weeks < 2) return '';
    return `<span class="tag-badge" style="background:rgba(240,136,62,0.15);color:var(--amber);border:1px solid rgba(240,136,62,0.4);font-size:10px">連續${weeks}週</span>`;
  }

  function chipsRow(d) {
    const devSign  = d.deviation >= 0 ? '+' : '';
    const weekSign = (d.week_chg_pct >= 0) ? '+' : '';
    const weekClass = d.week_chg_pct >= 0 ? 'pos' : 'neg';
    const devClass  = d.deviation  >= 0 ? 'pos' : 'neg';
    const inWatch   = watchlist.includes(d.stock_id);
    return `
      <tr onclick="toggleExpand('${d.stock_id}')" id="row-${d.stock_id}">
        <td>
          <a href="https://www.tradingview.com/chart/?symbol=${getTVSymbol(d)}"
            onclick="openTV('${getTVSymbol(d)}', event)"
            style="text-decoration:none;display:inline-block">
            <div class="stock-code" style="display:flex;align-items:center;gap:5px">
              ${d.stock_id}<span style="font-size:9px;opacity:.45;font-family:var(--mono)">↗</span>
            </div>
            <div class="stock-name">${d.name}</div>
          </a>
          <div class="stock-industry">${d.industry || ''}</div>
          ${consecutiveBadge(d.consecutive_weeks)}
        </td>
        <td><span class="price-cell">${d.close != null ? d.close.toFixed(1) : '—'}</span></td>
        <td><span class="deviation ${weekClass}">${d.week_chg_pct != null ? weekSign + d.week_chg_pct.toFixed(2) + '%' : '—'}</span></td>
        <td>
          <span class="ema-cell">${d.ema120 != null ? d.ema120.toFixed(2) : '—'}</span><br>
          <span class="deviation ${devClass}">${d.deviation != null ? devSign + d.deviation.toFixed(2) + '%' : '—'}</span>
        </td>
        <td><span class="big-pct">${d.big_pct_1000 != null ? d.big_pct_1000.toFixed(2) + '%' : '—'}</span></td>
        <td><span class="big-pct ${d.chg_4w_1000 != null && d.chg_4w_1000 >= 0 ? 'pos' : 'neg'}">${d.chg_4w_1000 != null ? (d.chg_4w_1000 > 0 ? '+' : '') + d.chg_4w_1000.toFixed(2) + '%' : '—'}</span></td>
        <td><span class="big-pct ${d.chg_4w_400 != null && d.chg_4w_400 >= 0 ? 'pos' : 'neg'}">${d.chg_4w_400 != null ? (d.chg_4w_400 > 0 ? '+' : '') + d.chg_4w_400.toFixed(2) + '%' : '—'}</span></td>
        <td><div class="spark">${sparkBars(d.big_trend_1000 || [])}</div></td>
        <td><div class="tag-cell">${tagBadges(d.tags)}</div></td>
      </tr>
      <tr class="expand-row" id="expand-${d.stock_id}" style="display:none">
        <td colspan="9">
          <div class="expand-flat">
            <div class="expand-trend-wrap">
              ${(() => {
                const labels = d.date_labels || DATE_LABELS;
                const t1000  = d.big_trend_1000 || [];
                const t400   = d.big_trend_400  || [];
                const cum1000 = t1000.length >= 4 ? t1000[t1000.length-1] - t1000[0] : null;
                const cum400  = t400.length  >= 4 ? t400[t400.length-1]  - t400[0]  : null;
                const cum1000Sign = cum1000 != null && cum1000 >= 0 ? '+' : '';
                const cum400Sign  = cum400  != null && cum400  >= 0 ? '+' : '';
                const dateHdrs = [...labels].reverse().map(l => `<th>${l}</th>`).join('');
                const cells1000 = [...t1000].reverse().map(v => `<td>${v.toFixed(2)}%</td>`).join('');
                const cells400  = [...t400].reverse().map(v  => `<td>${v.toFixed(2)}%</td>`).join('');
                return `<table class="expand-table">
                  <thead><tr>
                    <th></th><th>4週增幅</th>${dateHdrs}
                  </tr></thead>
                  <tbody>
                    <tr>
                      <td>千張大戶</td>
                      <td class="expand-cum ${cum1000!=null&&cum1000>=0?'pos':'neg'}">${cum1000!=null?cum1000Sign+cum1000.toFixed(2)+'%':'—'}</td>
                      ${cells1000}
                    </tr>
                    <tr>
                      <td>400張大戶</td>
                      <td class="expand-cum ${cum400!=null&&cum400>=0?'pos':'neg'}">${cum400!=null?cum400Sign+cum400.toFixed(2)+'%':'—'}</td>
                      ${cells400}
                    </tr>
                  </tbody>
                </table>`;
              })()}
            </div>
            <div class="expand-actions">
              <button onclick="event.stopPropagation();toggleWatch('${d.stock_id}','${d.name}')"
                style="background:${inWatch?'var(--green-dim)':'var(--bg3)'};border:1px solid ${inWatch?'var(--green)':'var(--border)'};color:${inWatch?'var(--green)':'var(--text2)'};padding:8px 14px;border-radius:6px;cursor:pointer;font-size:12px;font-family:var(--sans);white-space:nowrap"
                id="watchBtn-${d.stock_id}">
                ${inWatch ? '✓ 已加入' : '+ 加入觀察清單'}
              </button>
            </div>
          </div>
        </td>
      </tr>`;
  }

  function industryGroupHTML(groups) {
    return groups.map(g => {
      const avgSign = g.avg >= 0 ? '+' : '';
      const rows = g.items.map(d => chipsRow(d)).join('');
      return `
        <tr class="industry-header-row">
          <td colspan="9">
            <span class="industry-name">${g.name}</span>
            <span class="industry-avg">平均3週增幅 ${avgSign}${g.avg.toFixed(2)}%</span>
            <span class="industry-count">${g.items.length} 支</span>
          </td>
        </tr>
        ${rows}`;
    }).join('');
  }

  const sortIcon = col => `<span class="sort-icon">${sortCol===col ? (sortAsc?'↑':'↓') : '·'}</span>`;
  const vscrollClass = allData.length > 10 ? 'table-vscroll' : '';
  const maxCum = Math.max(...allData.map(d => combined3w(d)));

  const tableBody = chipsViewMode === 'stock'
    ? sortedData.map(d => chipsRow(d)).join('')
    : industryGroupHTML(buildIndustryGroups(allData));

  main.innerHTML = `
    <div class="strategy-panel active">
      <div class="strat-header">
        <div class="strat-title">${strat.icon} ${strat.name}策略</div>
        <div class="strat-desc">${strat.description}</div>
      </div>
      <div class="conditions">
        ${strat.conditions.map(c => `<div class="cond"><span class="cond-dot"></span>${c}</div>`).join('')}
      </div>
      <div class="summary-row">
        <div class="summary-card">
          <div class="summary-label">入池標的</div>
          <div class="summary-value green">${allData.length}</div>
          <div class="summary-sub">符合全部條件</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">最高3週增幅</div>
          <div class="summary-value amber">${maxCum >= 0 ? '+' : ''}${maxCum.toFixed(2)}%</div>
          <div class="summary-sub">千張+400張累積增幅</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">資料日期</div>
          <div class="summary-value" style="font-size:16px;font-family:var(--mono)">${strat.dataUpdated}</div>
          <div class="summary-sub">${strat.dataSource}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">排列方式</div>
          <div style="display:flex;gap:6px;margin-top:6px">
            <button class="view-btn ${chipsViewMode==='stock'?'active':''}" onclick="setChipsView('stock')">個股</button>
            <button class="view-btn ${chipsViewMode==='industry'?'active':''}" onclick="setChipsView('industry')">族群</button>
          </div>
        </div>
      </div>
      ${renderIndustryChart(allData)}
      <div class="table-wrap">
        <div class="table-toolbar">
          <span class="table-title">篩選結果</span>
          <div class="toolbar-right">
            <span class="updated-tag">更新：${strat.dataUpdated}</span>
            <button class="btn-csv" onclick="exportCSVChips()" title="匯出 CSV">↓ 匯出 CSV</button>
          </div>
        </div>
        <div class="table-scroll ${vscrollClass}">
        <table id="resultsTable">
          <thead>
            <tr>
              <th onclick="chipsSort('stock_id')">代號 / 名稱${sortIcon('stock_id')}</th>
              <th onclick="chipsSort('close')">現價${sortIcon('close')}</th>
              <th onclick="chipsSort('week_chg_pct')">周漲跌${sortIcon('week_chg_pct')}</th>
              <th onclick="chipsSort('deviation')" data-tip="(現價-EMA120)/EMA120">乖離EMA120${sortIcon('deviation')}</th>
              <th onclick="chipsSort('big_pct_1000')" data-tip="千張大戶持股%">大戶比例${sortIcon('big_pct_1000')}</th>
              <th onclick="chipsSort('chg_4w_1000')" data-tip="千張大戶持股% [T日 − (T-28日)] 4週差值（百分點）">千張${sortIcon('chg_4w_1000')}</th>
              <th onclick="chipsSort('chg_4w_400')" data-tip="400張大戶持股% [T日 − (T-28日)] 4週差值（百分點）">400張${sortIcon('chg_4w_400')}</th>
              <th>趨勢</th>
              <th onclick="chipsSort('tag_score')" data-tip="依積分排序：單周增幅+5、雙軌觸發+3、持續成長+1">篩選條件${sortIcon('tag_score')}</th>
            </tr>
          </thead>
          <tbody>${tableBody}</tbody>
        </table>
        </div>
      </div>
    </div>`;

  const grid = document.getElementById('watchlistGrid');
  if (grid) grid.innerHTML = renderWatchlist();
}

function setChipsView(mode) {
  chipsViewMode = mode;
  const strat = STRATEGIES.find(s => s.id === 'chips_big_holder');
  renderChipsHolder(strat, document.getElementById('mainContent'));
}

function chipsSort(col) {
  if (sortCol === col) sortAsc = !sortAsc;
  else { sortCol = col; sortAsc = false; }
  const strat = STRATEGIES.find(s => s.id === 'chips_big_holder');
  renderChipsHolder(strat, document.getElementById('mainContent'));
}

function vsSort(col) {
  if (sortCol === col) sortAsc = !sortAsc;
  else { sortCol = col; sortAsc = false; }
  const strat = STRATEGIES.find(s => s.id === 'volume_signal');
  renderVolumeSignal(strat, document.getElementById('mainContent'));
}

function exportCSVChips() {
  const data = DATA.chips_big_holder_data || [];
  if (!data.length) return;
  const strat = STRATEGIES.find(s => s.id === 'chips_big_holder');
  const headers = ['代號','名稱','族群','現價','周漲跌(%)','乖離EMA120(%)','大戶比例(%)','三周累積增幅(%)','標籤','分數'];
  const rows = data.map(d => [
    d.stock_id, d.name, d.industry || '',
    d.close?.toFixed(1) || '',
    d.week_chg_pct != null ? d.week_chg_pct.toFixed(2) : '',
    d.deviation != null ? d.deviation.toFixed(2) : '',
    d.big_pct_1000?.toFixed(2) || '',
    combined3w(d).toFixed(2),
    (d.tags || []).join(' '),
    d.tag_score || 0,
  ]);
  const csv = [headers, ...rows].map(r => r.map(v => `"${String(v).replace(/"/g,'""')}"`).join(',')).join('\r\n');
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' });
  const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: `chips_${strat.dataUpdated}.csv` });
  a.click();
}

// ════════════════════════════════════════════════════

