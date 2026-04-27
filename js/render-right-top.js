// ════════════════════════════════════════════════════
//  右上角：渲染器
// ════════════════════════════════════════════════════
function renderRightTop(strat, main) {
  const rawData       = DATA.right_top_data || [];
  const industryStats = DATA.right_top_industry || [];

  if (rawData.length === 0) {
    main.innerHTML = `
      <div class="strategy-panel active">
        <div class="strat-header">
          <div class="strat-title">${strat.icon} ${strat.name}策略</div>
          <div class="strat-desc">${strat.description}</div>
        </div>
        <div class="conditions">
          ${strat.conditions.map(c => `<div class="cond"><span class="cond-dot"></span>${c}</div>`).join('')}
        </div>
        <div class="coming-soon" style="padding:48px 20px">
          <div class="coming-icon" style="font-size:28px">▲</div>
          <div class="coming-title">資料尚未生成</div>
          <div class="coming-desc">
            請至 GitHub Actions → <b>右上角選股掃描</b> → <b>Run workflow</b><br>
            手動觸發首次掃描，或等待盤後自動執行。
          </div>
        </div>
      </div>`;
    const grid = document.getElementById('watchlistGrid');
    if (grid) grid.innerHTML = renderWatchlist();
    return;
  }

  // ── 排序 ──
  const rtSortCol = window._rtSortCol || 'vol_ratio';
  const rtSortAsc = window._rtSortAsc !== undefined ? window._rtSortAsc : false;

  function rtCompare(a, b) {
    const va = a[rtSortCol] != null ? a[rtSortCol] : '';
    const vb = b[rtSortCol] != null ? b[rtSortCol] : '';
    const isDate = /^\d{4}-\d{2}-\d{2}/.test(va) || /^\d{4}-\d{2}-\d{2}/.test(vb);
    const numA = parseFloat(va), numB = parseFloat(vb);
    const cmp = isDate
      ? String(va).localeCompare(String(vb))
      : (!isNaN(numA) && !isNaN(numB))
        ? numA - numB
        : String(va).localeCompare(String(vb));
    return rtSortAsc ? cmp : -cmp;
  }

  function rtSort(col) {
    if (window._rtSortCol === col) window._rtSortAsc = !window._rtSortAsc;
    else { window._rtSortCol = col; window._rtSortAsc = false; }
    renderStrategy();
  }
  window.rtSort = rtSort;

  function sortIcon(col) {
    const isActive = rtSortCol === col;
    return `<span class="sort-icon">${isActive ? (rtSortAsc ? '↑' : '↓') : '·'}</span>`;
  }

  const data = rawData.slice().sort(rtCompare);

  // ── 視圖切換 ──
  const rtView = window._rtView || 'stock';
  function setRtView(v) { window._rtView = v; renderStrategy(); }
  window.setRtView = setRtView;

  // ── 產業統計 ──
  const topIndustry = industryStats[0];
  const twseCount = data.filter(d => d.market === 'TWSE').length;
  const tpexCount = data.filter(d => d.market === 'TPEX').length;

  // ── CSV 匯出 ──
  function exportRtCSV() {
    const headers = ['代號','名稱','產業','市場','收盤','90日高','量比','漲幅(%)','訊號日'];
    const rows = data.map(d => [
      d.stock_id, d.name, d.industry, d.market,
      d.close, d.high_90d,
      d.vol_ratio.toFixed(2) + 'x',
      (d.change_pct >= 0 ? '+' : '') + d.change_pct.toFixed(2) + '%',
      d.signal_date,
    ]);
    const csv = [headers, ...rows]
      .map(r => r.map(v => `"${String(v).replace(/"/g,'""')}"`).join(',')).join('\r\n');
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
    const url  = URL.createObjectURL(blob);
    const a    = Object.assign(document.createElement('a'), { href: url, download: `right_top_${strat.dataUpdated}.csv` });
    a.click(); URL.revokeObjectURL(url);
  }
  window.exportRtCSV = exportRtCSV;

  // ── 個股列表 ──
  function stockTable() {
    return `
      <div class="table-wrap">
        <div class="table-toolbar">
          <span class="table-title">右上角觸發標的</span>
          <div class="toolbar-right">
            <span class="updated-tag">更新：${strat.dataUpdated}</span>
            <button class="btn-csv" onclick="exportRtCSV()">↓ 匯出 CSV</button>
          </div>
        </div>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th onclick="rtSort('stock_id')" style="cursor:pointer">代號 / 名稱${sortIcon('stock_id')}</th>
                <th onclick="rtSort('industry')" style="cursor:pointer">產業${sortIcon('industry')}</th>
                <th onclick="rtSort('close')" style="cursor:pointer" data-tip="今日收盤價">收盤${sortIcon('close')}</th>
                <th onclick="rtSort('high_90d')" style="cursor:pointer" data-tip="前 90 個交易日最高收盤（已被今日突破）">90日前高${sortIcon('high_90d')}</th>
                <th onclick="rtSort('vol_ratio')" style="cursor:pointer" data-tip="今日量 ÷ 10日均量">量比${sortIcon('vol_ratio')}</th>
                <th onclick="rtSort('change_pct')" style="cursor:pointer" data-tip="今日漲幅">漲幅${sortIcon('change_pct')}</th>
                <th onclick="rtSort('signal_date')" style="cursor:pointer">訊號日${sortIcon('signal_date')}</th>
              </tr>
            </thead>
            <tbody>
              ${data.map(d => {
                const mkt      = d.market === 'TWSE' ? 'TWSE' : 'TPEX';
                const tvSymbol = `${mkt}:${d.stock_id}`;
                const chgClass = d.change_pct >= 0 ? 'pos' : 'neg';
                const chgSign  = d.change_pct >= 0 ? '+' : '';
                return `<tr>
                  <td>
                    <a href="https://www.tradingview.com/chart/?symbol=${tvSymbol}"
                       onclick="openTV('${tvSymbol}', event)" style="text-decoration:none;display:inline-block">
                      <div class="stock-code" style="display:flex;align-items:center;gap:5px">
                        ${d.stock_id}<span style="font-size:9px;opacity:.45;font-family:var(--mono)">↗</span>
                      </div>
                      <div class="stock-name">${d.name}</div>
                    </a>
                    <div class="stock-industry" style="font-size:10px;color:var(--text3)">${d.market}</div>
                  </td>
                  <td><span style="font-size:12px;color:var(--text2)">${d.industry || '—'}</span></td>
                  <td><span class="price-cell">${d.close.toFixed(2)}</span></td>
                  <td>
                    <span style="font-family:var(--mono);font-size:12px;color:var(--text3)">${d.high_90d.toFixed(2)}</span><br>
                    <span style="font-size:10px;color:var(--green)">↑ 已突破</span>
                  </td>
                  <td>
                    <span style="font-family:var(--mono);font-size:14px;font-weight:600;color:var(--red)">${d.vol_ratio.toFixed(2)}x</span><br>
                    <span style="font-size:10px;color:var(--text3)">${Math.round(d.vol_10d_avg)}張均</span>
                  </td>
                  <td>
                    <span class="deviation ${chgClass}" style="font-size:13px">${chgSign}${d.change_pct.toFixed(2)}%</span>
                  </td>
                  <td>
                    <span style="font-family:var(--mono);font-size:12px;color:var(--text3)">${d.signal_date}</span>
                  </td>
                </tr>`;
              }).join('')}
            </tbody>
          </table>
        </div>
      </div>`;
  }

  // ── 產業統計 ──
  function industryView() {
    if (industryStats.length === 0) {
      return `<div style="padding:48px 20px;text-align:center;color:var(--text3)">尚無產業統計資料</div>`;
    }
    const maxCount = industryStats[0].count;
    return `
      <div class="table-wrap">
        <div class="table-toolbar">
          <span class="table-title">產業分布統計</span>
          <div class="toolbar-right">
            <span class="updated-tag">共 ${industryStats.length} 個產業</span>
          </div>
        </div>
        <div style="padding:16px;display:flex;flex-direction:column;gap:10px">
          ${industryStats.map((ind, idx) => {
            const barPct = maxCount > 0 ? (ind.count / maxCount * 100).toFixed(1) : 0;
            const rankColor = idx === 0 ? 'var(--green)' : idx === 1 ? 'var(--amber)' : idx === 2 ? 'var(--blue)' : 'var(--text3)';
            return `
              <div style="background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:12px 16px">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
                  <div style="display:flex;align-items:center;gap:10px">
                    <span style="font-size:11px;font-weight:700;font-family:var(--mono);color:${rankColor};min-width:24px">#${idx + 1}</span>
                    <span style="font-weight:600;font-size:14px">${ind.industry}</span>
                    <span style="font-size:12px;color:var(--green);font-weight:600">${ind.count} 支</span>
                  </div>
                </div>
                <div style="background:var(--bg3);border-radius:4px;height:6px;margin-bottom:8px">
                  <div style="background:${rankColor};width:${barPct}%;height:100%;border-radius:4px;transition:width .3s"></div>
                </div>
                <div style="display:flex;flex-wrap:wrap;gap:4px">
                  ${ind.stocks.map(s => `
                    <span style="background:var(--bg3);border:1px solid var(--border);border-radius:4px;
                                 padding:2px 7px;font-size:11px;font-family:var(--mono);cursor:pointer;
                                 color:var(--text2)"
                          onclick="openTV('${s.stock_id}', event)"
                          title="${s.name}">
                      ${s.stock_id} ${s.name}
                    </span>`).join('')}
                </div>
              </div>`;
          }).join('')}
        </div>
      </div>`;
  }

  main.innerHTML = `
    <div class="strategy-panel active">
      <div class="strat-header">
        <div class="strat-title">${strat.icon} ${strat.name}策略</div>
        <div class="strat-desc">${strat.description}</div>
      </div>
      <div class="conditions">
        ${strat.conditions.map(c => `<div class="cond"><span class="cond-dot"></span>${c}</div>`).join('')}
      </div>

      <!-- Summary -->
      <div class="summary-row">
        <div class="summary-card">
          <div class="summary-label">觸發標的</div>
          <div class="summary-value green">${data.length}</div>
          <div class="summary-sub">今日創90日新高 + 量增</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">最強族群</div>
          <div class="summary-value amber" style="font-size:16px">${topIndustry ? topIndustry.industry : '—'}</div>
          <div class="summary-sub">${topIndustry ? `${topIndustry.count} 支同步觸發` : '尚無資料'}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">資料日期</div>
          <div class="summary-value" style="font-size:16px;font-family:var(--mono)">${strat.dataUpdated}</div>
          <div class="summary-sub">${strat.dataSource}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">市場分布</div>
          <div class="summary-value" style="font-size:15px">
            <span style="color:var(--green)">${twseCount}</span>
            <span style="font-size:11px;color:var(--text3);margin:0 4px">上市</span>
            <span style="color:var(--amber)">${tpexCount}</span>
            <span style="font-size:11px;color:var(--text3)">上櫃</span>
          </div>
          <div class="summary-sub">上市 + 上櫃</div>
        </div>
      </div>

      <!-- View toggle -->
      <div style="display:flex;gap:8px;padding:0 0 12px 0">
        <button class="view-btn ${rtView === 'stock' ? 'active' : ''}" onclick="setRtView('stock')">個股列表</button>
        <button class="view-btn ${rtView === 'industry' ? 'active' : ''}" onclick="setRtView('industry')">產業統計</button>
      </div>

      ${rtView === 'stock' ? stockTable() : industryView()}
    </div>`;

  const grid = document.getElementById('watchlistGrid');
  if (grid) grid.innerHTML = renderWatchlist();
}
