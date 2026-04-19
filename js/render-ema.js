// ════════════════════════════════════════════════════
//  均線糾結：渲染器
// ════════════════════════════════════════════════════
function renderEmaTangling(strat, main) {
  const rawData = DATA.ema_tangling_data || [];

  // 尚未有資料時的提示
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
          <div class="coming-icon" style="font-size:28px">◇</div>
          <div class="coming-title">資料尚未生成</div>
          <div class="coming-desc">
            請至 GitHub Actions → <b>PHASE3 均線糾結選股</b> → <b>Run workflow</b><br>
            手動觸發首次掃描，或等待盤後 15:40 自動執行。
          </div>
        </div>
      </div>`;
    return;
  }

  // 排序（預設：糾結程度升序，越小越好）
  const etSortCol = window._etSortCol || 'tangle_pct';
  const etSortAsc = (window._etSortAsc !== undefined) ? window._etSortAsc : true;
  const data = rawData.slice().sort((a, b) => {
    const va = a[etSortCol] ?? 0, vb = b[etSortCol] ?? 0;
    if (typeof va === 'string') return etSortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
    return etSortAsc ? va - vb : vb - va;
  });

  const avgTangle = data.length ? data.reduce((s, d) => s + d.tangle_pct, 0) / data.length : 0;

  function sortIcon(col) {
    const active = etSortCol === col;
    return `<span class="sort-icon">${active ? (etSortAsc ? '↑' : '↓') : '·'}</span>`;
  }

  function etSort(col) {
    if (window._etSortCol === col) window._etSortAsc = !window._etSortAsc;
    else { window._etSortCol = col; window._etSortAsc = (col === 'tangle_pct'); }
    renderStrategy();
  }
  window.etSort = etSort;

  function exportEtCSV() {
    const headers = ['代號','名稱','市場','今日收盤','EMA20','EMA60','EMA120','糾結%','20日均量(張)'];
    const rows = data.map(d => [
      d.stock_id, d.name, d.market,
      d.close.toFixed(2),
      d.ema20.toFixed(2), d.ema60.toFixed(2), d.ema120.toFixed(2),
      d.tangle_pct.toFixed(2),
      d.vol_20ma.toFixed(0)
    ]);
    const csv = [headers, ...rows]
      .map(r => r.map(v => `"${String(v).replace(/"/g,'""')}"`).join(',')).join('\r\n');
    const blob = new Blob(['\uFEFF' + csv], {type:'text/csv;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `ema_tangling_${strat.dataUpdated}.csv`;
    a.click(); URL.revokeObjectURL(url);
  }
  window.exportEtCSV = exportEtCSV;

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
          <div class="summary-label">篩選結果</div>
          <div class="summary-value green">${data.length}</div>
          <div class="summary-sub">符合全部條件</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">平均糾結度</div>
          <div class="summary-value amber">${avgTangle.toFixed(2)}%</div>
          <div class="summary-sub">三線乖離均值（越小越緊）</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">資料日期</div>
          <div class="summary-value" style="font-size:16px;font-family:var(--mono)">${strat.dataUpdated}</div>
          <div class="summary-sub">${strat.dataSource}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">掃描範圍</div>
          <div class="summary-value" style="font-size:16px">全市場</div>
          <div class="summary-sub">上市 + 上櫃</div>
        </div>
      </div>

      <!-- Table -->
      <div class="table-wrap">
        <div class="table-toolbar">
          <span class="table-title">均線糾結結果</span>
          <div class="toolbar-right">
            <span class="updated-tag">更新：${strat.dataUpdated}</span>
            <button class="btn-csv" onclick="exportEtCSV()">↓ 匯出 CSV</button>
          </div>
        </div>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th onclick="etSort('stock_id')" style="cursor:pointer">代號 / 名稱${sortIcon('stock_id')}</th>
                <th onclick="etSort('close')" style="cursor:pointer" data-tip="今日收盤價">今日收${sortIcon('close')}</th>
                <th onclick="etSort('tangle_pct')" style="cursor:pointer" data-tip="(EMA最大值 − EMA最小值) / EMA最小值 × 100%">糾結%${sortIcon('tangle_pct')}</th>
                <th onclick="etSort('ema20')" style="cursor:pointer" data-tip="EMA20 值">EMA20${sortIcon('ema20')}</th>
                <th onclick="etSort('ema60')" style="cursor:pointer" data-tip="EMA60 值">EMA60${sortIcon('ema60')}</th>
                <th onclick="etSort('ema120')" style="cursor:pointer" data-tip="EMA120 值">EMA120${sortIcon('ema120')}</th>
                <th onclick="etSort('vol_20ma')" style="cursor:pointer" data-tip="20 日平均成交量（張）">均量(張)${sortIcon('vol_20ma')}</th>
              </tr>
            </thead>
            <tbody>
              ${data.map(d => {
                const mkt = d.market === 'TWSE' ? 'TWSE' : 'TPEX';
                const tvSymbol = `${mkt}:${d.stock_id}`;
                const inWatch = watchlist.includes(d.stock_id);
                const tangleColor = d.tangle_pct <= 2 ? 'var(--green)' : d.tangle_pct <= 4 ? 'var(--amber)' : 'var(--text2)';
                return `<tr onclick="etToggleExpand('${d.stock_id}')" id="et-row-${d.stock_id}">
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
                  <td><span class="price-cell">${d.close.toFixed(2)}</span></td>
                  <td>
                    <span style="font-family:var(--mono);font-size:14px;font-weight:600;color:${tangleColor}">${d.tangle_pct.toFixed(2)}%</span>
                  </td>
                  <td><span class="ema-cell">${d.ema20.toFixed(2)}</span></td>
                  <td><span class="ema-cell">${d.ema60.toFixed(2)}</span></td>
                  <td><span class="ema-cell">${d.ema120.toFixed(2)}</span></td>
                  <td><span style="font-family:var(--mono);font-size:12px">${d.vol_20ma.toFixed(0)}</span></td>
                </tr>
                <tr class="expand-row" id="et-expand-${d.stock_id}" style="display:none">
                  <td colspan="7">
                    <div class="expand-content" style="grid-template-columns:1fr 1fr 1fr">
                      <div class="expand-section">
                        <h4>均線數值</h4>
                        <div style="display:flex;flex-direction:column;gap:6px;font-family:var(--mono);font-size:12px">
                          <div style="display:flex;justify-content:space-between"><span style="color:var(--text3)">EMA20</span><span>${d.ema20.toFixed(2)}</span></div>
                          <div style="display:flex;justify-content:space-between"><span style="color:var(--text3)">EMA60</span><span>${d.ema60.toFixed(2)}</span></div>
                          <div style="display:flex;justify-content:space-between"><span style="color:var(--text3)">EMA120</span><span>${d.ema120.toFixed(2)}</span></div>
                          <div style="display:flex;justify-content:space-between"><span style="color:var(--text3)">收盤</span><span style="color:var(--green);font-weight:600">${d.close.toFixed(2)}</span></div>
                        </div>
                      </div>
                      <div class="expand-section">
                        <h4>糾結分析</h4>
                        <div style="display:flex;flex-direction:column;gap:6px;font-family:var(--mono);font-size:12px">
                          <div style="display:flex;justify-content:space-between"><span style="color:var(--text3)">糾結度</span><span style="color:${tangleColor};font-weight:600">${d.tangle_pct.toFixed(2)}%</span></div>
                          <div style="display:flex;justify-content:space-between"><span style="color:var(--text3)">20日均量</span><span>${d.vol_20ma.toFixed(0)} 張</span></div>
                          <div style="display:flex;justify-content:space-between"><span style="color:var(--text3)">市場</span><span>${d.market}</span></div>
                        </div>
                      </div>
                      <div class="expand-section">
                        <h4>操作</h4>
                        <button onclick="event.stopPropagation();toggleWatch('${d.stock_id}','${d.name}')"
                          style="background:${inWatch?'var(--green-dim)':'var(--bg3)'};border:1px solid ${inWatch?'var(--green)':'var(--border)'};color:${inWatch?'var(--green)':'var(--text2)'};padding:8px 14px;border-radius:6px;cursor:pointer;font-size:12px;font-family:var(--sans);width:100%;margin-bottom:8px"
                          id="watchBtn-${d.stock_id}">
                          ${inWatch ? '✓ 已加入觀察清單' : '+ 加入觀察清單'}
                        </button>
                        <a href="https://tw.stock.yahoo.com/quote/${d.stock_id}" target="_blank"
                          onclick="event.stopPropagation()"
                          style="display:block;text-align:center;background:var(--bg3);border:1px solid var(--border);color:var(--text2);padding:8px 14px;border-radius:6px;font-size:12px;text-decoration:none">
                          Yahoo 股市 ↗
                        </a>
                      </div>
                    </div>
                  </td>
                </tr>`;
              }).join('')}
            </tbody>
          </table>
        </div>
      </div>
    </div>`;

  const grid = document.getElementById('watchlistGrid');
  if (grid) grid.innerHTML = renderWatchlist();
}

let etExpandedRow = null;

function etToggleExpand(sid) {
  const prev = etExpandedRow;
  if (prev) {
    const prevExp = document.getElementById(`et-expand-${prev}`);
    const prevRow = document.getElementById(`et-row-${prev}`);
    if (prevExp) prevExp.style.display = 'none';
    if (prevRow) prevRow.classList.remove('expanded');
  }
  if (prev !== sid) {
    const expEl = document.getElementById(`et-expand-${sid}`);
    const rowEl = document.getElementById(`et-row-${sid}`);
    if (expEl) expEl.style.display = 'table-row';
    if (rowEl) rowEl.classList.add('expanded');
    etExpandedRow = sid;
  } else {
    etExpandedRow = null;
  }
}

// ════════════════════════════════════════════════════
