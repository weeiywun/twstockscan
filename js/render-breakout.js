//  大量追蹤：渲染器
// ════════════════════════════════════════════════════
function renderVolumeBreakout(strat, main) {
  const rawData = DATA.volume_breakout_data || [];

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
          <div class="coming-icon" style="font-size:28px">◆</div>
          <div class="coming-title">資料尚未生成</div>
          <div class="coming-desc">
            請至 GitHub Actions → <b>大量追蹤選股</b> → <b>Run workflow</b><br>
            手動觸發首次掃描，或等待盤後 15:30 自動執行。
          </div>
        </div>
      </div>`;
    return;
  }

  // 排序（預設：T日量比倒序）
  const vbSortCol = window._vbSortCol || 't_vol_ratio';
  const vbSortAsc = window._vbSortAsc || false;
  const data = rawData.slice().sort((a, b) => {
    const va = a[vbSortCol] ?? 0, vb = b[vbSortCol] ?? 0;
    return vbSortAsc ? va - vb : vb - va;
  });

  const phase4Count = data.filter(d => d.phase4_activated).length;

  function sortIcon(col) {
    const active = vbSortCol === col;
    return `<span class="sort-icon">${active ? (vbSortAsc ? '↑' : '↓') : '·'}</span>`;
  }

  function vbSort(col) {
    if (window._vbSortCol === col) window._vbSortAsc = !window._vbSortAsc;
    else { window._vbSortCol = col; window._vbSortAsc = false; }
    renderStrategy();
  }
  window.vbSort = vbSort;

  function exportVbCSV() {
    const headers = ['代號','名稱','市場','今日收盤','偏離60MA(%)','T日日期','T日漲幅(%)','T日量比','洗盤天數','模組四','今日量比'];
    const rows = data.map(d => [
      d.stock_id, d.name, d.market,
      d.close, (d.deviation_ma60 >= 0 ? '+' : '') + d.deviation_ma60.toFixed(2),
      d.t_date, (d.t_change_pct >= 0 ? '+' : '') + d.t_change_pct.toFixed(2),
      d.t_vol_ratio.toFixed(1) + 'x',
      d.days_since_t + '天',
      d.phase4_activated ? '★是' : '否',
      d.cond9_vol_ratio.toFixed(2) + 'x'
    ]);
    const csv = [headers, ...rows]
      .map(r => r.map(v => `"${String(v).replace(/"/g,'""')}"`).join(',')).join('\r\n');
    const blob = new Blob(['\uFEFF' + csv], {type:'text/csv;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `volume_breakout_${strat.dataUpdated}.csv`;
    a.click(); URL.revokeObjectURL(url);
  }
  window.exportVbCSV = exportVbCSV;

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
          <div class="summary-sub">符合模組一~三條件</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">★ 模組四啟動</div>
          <div class="summary-value amber">${phase4Count}</div>
          <div class="summary-sub">放量突破洗盤區最高</div>
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
          <span class="table-title">大量追蹤結果</span>
          <div class="toolbar-right">
            <span class="updated-tag">更新：${strat.dataUpdated}</span>
            <button class="btn-csv" onclick="exportVbCSV()">↓ 匯出 CSV</button>
          </div>
        </div>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th onclick="vbSort('stock_id')" style="cursor:pointer">代號 / 名稱${sortIcon('stock_id')}</th>
                <th onclick="vbSort('close')" style="cursor:pointer" data-tip="今日收盤價">今日收${sortIcon('close')}</th>
                <th onclick="vbSort('deviation_ma60')" style="cursor:pointer" data-tip="(今日收 − 60MA) / 60MA">偏離60MA${sortIcon('deviation_ma60')}</th>
                <th onclick="vbSort('t_date')" style="cursor:pointer" data-tip="爆量突破日日期">T日${sortIcon('t_date')}</th>
                <th onclick="vbSort('t_vol_ratio')" style="cursor:pointer" data-tip="T日量 ÷ T日前20日均量">T日量比${sortIcon('t_vol_ratio')}</th>
                <th onclick="vbSort('t_change_pct')" style="cursor:pointer" data-tip="T日收盤漲幅">T日漲幅${sortIcon('t_change_pct')}</th>
                <th onclick="vbSort('days_since_t')" style="cursor:pointer" data-tip="T+1 到今日共幾個交易日">洗盤天${sortIcon('days_since_t')}</th>
                <th data-tip="模組四：今日溫和放量且突破洗盤區最高價">模組四</th>
              </tr>
            </thead>
            <tbody>
              ${data.map(d => {
                const devClass = d.deviation_ma60 < 0 ? 'neg' : 'pos';
                const devSign  = d.deviation_ma60 > 0 ? '+' : '';
                const mkt = d.market === 'TWSE' ? 'TWSE' : 'TPEX';
                const tvSymbol = `${mkt}:${d.stock_id}`;
                const p4badge = d.phase4_activated
                  ? `<span style="background:rgba(240,136,62,0.15);color:var(--amber);border:1px solid rgba(240,136,62,0.4);border-radius:4px;padding:2px 6px;font-size:11px;font-weight:600">★ 發動</span>`
                  : `<span style="color:var(--text3);font-size:11px">—</span>`;
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
                  <td><span class="price-cell">${d.close.toFixed(2)}</span></td>
                  <td>
                    <span class="ema-cell">${d.ma60.toFixed(2)}</span><br>
                    <span class="deviation ${devClass}">${devSign}${d.deviation_ma60.toFixed(2)}%</span>
                  </td>
                  <td>
                    <span style="font-family:var(--mono);font-size:12px">${d.t_date}</span><br>
                    <span style="font-size:11px;color:var(--text3)">${d.days_since_t} 天前</span>
                  </td>
                  <td>
                    <span style="font-family:var(--mono);font-size:14px;font-weight:600;color:var(--red)">${d.t_vol_ratio.toFixed(1)}x</span>
                  </td>
                  <td>
                    <span style="font-family:var(--mono);font-size:13px;color:var(--red)">+${d.t_change_pct.toFixed(2)}%</span>
                  </td>
                  <td>
                    <span style="font-family:var(--mono);font-size:13px">${d.days_since_t}</span>
                  </td>
                  <td>${p4badge}</td>
                </tr>`;
              }).join('')}
            </tbody>
          </table>
        </div>
      </div>
    </div>`;
}

