function renderTrendFollow(strat, main) {
  const data = DATA.trend_follow_data;

  if (!data) {
    main.innerHTML = `
      <div class="strategy-panel active">
        <div class="strat-header">
          <div class="strat-title">${strat.icon} ${strat.name}</div>
          <div class="strat-desc">${strat.description}</div>
        </div>
        <div class="coming-soon" style="padding:64px 20px">
          <div class="coming-icon">○</div>
          <div class="coming-title">等待資料</div>
          <div class="coming-desc">趨勢池標的出現量增提醒後會自動加入追蹤。</div>
        </div>
      </div>`;
    return;
  }

  function getValue(s, col) {
    if (col === 'pattern_score') return s.pattern_score ?? -1;
    if (col === 'trigger_date') return s.trigger_date || '';
    return s[col] ?? '';
  }

  function sortRows(arr, col, asc) {
    return arr.slice().sort((a, b) => {
      const va = getValue(a, col), vb = getValue(b, col);
      const isDate = /^\d{4}-\d{2}-\d{2}/.test(String(va)) || /^\d{4}-\d{2}-\d{2}/.test(String(vb));
      const na = parseFloat(va), nb = parseFloat(vb);
      const cmp = isDate
        ? String(va).localeCompare(String(vb))
        : (!isNaN(na) && !isNaN(nb)) ? na - nb
        : String(va).localeCompare(String(vb));
      return asc ? cmp : -cmp;
    });
  }

  function sortIcon(stateCol, stateAsc, col) {
    if (stateCol !== col) return '<span class="sort-icon">·</span>';
    return `<span class="sort-icon">${stateAsc ? '↑' : '↓'}</span>`;
  }

  if (window._tfActSortCol === undefined) { window._tfActSortCol = 'pnl_pct'; window._tfActSortAsc = false; }
  const aC = window._tfActSortCol, aA = window._tfActSortAsc;
  window.tfActSort = col => {
    window._tfActSortAsc = (window._tfActSortCol === col) ? !window._tfActSortAsc : false;
    window._tfActSortCol = col;
    renderStrategy();
  };

  if (window._tfHistSortCol === undefined) { window._tfHistSortCol = 'trigger_date'; window._tfHistSortAsc = false; }
  const hC = window._tfHistSortCol, hA = window._tfHistSortAsc;
  window.tfHistSort = col => {
    window._tfHistSortAsc = (window._tfHistSortCol === col) ? !window._tfHistSortAsc : false;
    window._tfHistSortCol = col;
    renderStrategy();
  };

  const active = sortRows(data.active || [], aC, aA);
  const expired = sortRows(data.expired || [], hC, hA);

  window.tfTogglePin = async (stockId) => {
    const item = [data.active || [], data.expired || []].flat().find(s => s.stock_id === stockId);
    if (!item) return;
    item.pinned = !item.pinned;
    if (!item.pinned && item.remove_date) item.remove_date = addTradingDaysTW(5);
    const ok = await ghWriteJson(GH_TREND_FOLLOW, data, `data: pin trend follow ${stockId}`);
    if (ok) renderStrategy();
  };

  window.exportTrendFollowCSV = () => {
    const headers = ['代號', '名稱', '產業', '觸發日', '型態分數', '型態狀態', '入池收盤', '現價', '損益%', '量比', '剩餘天數', '釘選'];
    const rows = (data.expired || []).map(s => [
      s.stock_id,
      s.name,
      s.industry || '',
      s.trigger_date || '',
      s.pattern_score ?? '',
      s.pattern_state || '',
      s.entry_price != null ? Number(s.entry_price).toFixed(2) : '',
      s.current_price != null ? Number(s.current_price).toFixed(2) : '',
      s.pnl_pct != null ? Number(s.pnl_pct).toFixed(2) : '',
      s.vol_ratio != null ? Number(s.vol_ratio).toFixed(2) : '',
      s.days_remaining ?? '',
      s.pinned ? 'Y' : '',
    ]);
    const csv = [headers, ...rows]
      .map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
      .join('\n');
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `trend_follow_${data.last_updated || 'export'}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  function pnlCls(pct) { return (pct || 0) >= 0 ? 'sa-pnl-pos' : 'sa-pnl-neg'; }
  function pnlStr(pct) {
    if (pct == null) return '-';
    return `${pct >= 0 ? '+' : ''}${Number(pct).toFixed(2)}%`;
  }
  function pinBtn(s) {
    const pinned = !!s.pinned;
    return `<button onclick="tfTogglePin('${s.stock_id}')"
      title="${pinned ? '取消釘選' : '釘選觀察'}"
      style="font-size:14px;width:28px;height:26px;border-radius:4px;border:1px solid ${pinned ? 'var(--amber)' : 'var(--border)'};background:${pinned ? 'rgba(240,136,62,0.12)' : 'var(--bg3)'};color:${pinned ? 'var(--amber)' : 'var(--text3)'};cursor:pointer">
      ${pinned ? '★' : '☆'}
    </button>`;
  }

  const avgPnl = active.length
    ? active.reduce((sum, row) => sum + (row.pnl_pct || 0), 0) / active.length
    : null;

  const summaryHTML = `<div class="summary-row">
    <div class="summary-card">
      <div class="summary-label">追蹤中</div>
      <div class="summary-value green">${active.length}</div>
      <div class="summary-sub">趨勢量增標的</div>
    </div>
    <div class="summary-card">
      <div class="summary-label">平均損益</div>
      <div class="summary-value" style="color:${avgPnl == null ? 'var(--text2)' : avgPnl >= 0 ? 'var(--market-up)' : 'var(--market-down)'}">
        ${avgPnl != null ? `${avgPnl >= 0 ? '+' : ''}${avgPnl.toFixed(2)}%` : '-'}
      </div>
      <div class="summary-sub">目前 active</div>
    </div>
    <div class="summary-card">
      <div class="summary-label">歷史紀錄</div>
      <div class="summary-value">${expired.length}</div>
      <div class="summary-sub">未釘選保留 5 交易日</div>
    </div>
    <div class="summary-card">
      <div class="summary-label">資料日期</div>
      <div class="summary-value" style="font-size:16px;font-family:var(--mono)">${data.last_updated || '-'}</div>
      <div class="summary-sub">最後更新</div>
    </div>
  </div>`;

  function rowHTML(s, i, history = false) {
    const market = s.market || guessMarket(s.stock_id);
    const tvSym = `${market}:${s.stock_id}`;
    const tags = (s.pattern_tags || []).join(' ');
    return `<tr>
      ${history ? '' : `<td style="font-family:var(--mono);font-size:11px;color:var(--text3)">${i + 1}</td>`}
      <td>
        <a href="https://www.tradingview.com/chart/?symbol=${tvSym}"
          onclick="openTV('${tvSym}', event)" style="text-decoration:none">
          <span class="stock-code" style="font-size:12px">${s.stock_id}</span>
          <span style="font-size:9px;opacity:.45;font-family:var(--mono)">↗</span>
        </a>
        <span style="font-size:12px;color:var(--text2);margin-left:4px">${s.name}</span>
        <div style="font-size:10px;color:var(--text3)">${s.industry || ''}</div>
      </td>
      <td style="font-family:var(--mono);font-size:12px;color:var(--text3)">${s.trigger_date || '-'}</td>
      <td>
        <span style="font-family:var(--mono);font-weight:700;color:var(--green)">${s.pattern_score != null ? Number(s.pattern_score).toFixed(1) : '-'}</span>
        <div style="font-size:10px;color:var(--text3)">${s.pattern_state || '-'}</div>
      </td>
      <td style="font-size:11px;color:var(--text2);max-width:120px">${tags || '-'}</td>
      <td style="font-family:var(--mono);font-size:12px">${s.entry_price != null ? Number(s.entry_price).toFixed(2) : '-'}</td>
      <td style="font-family:var(--mono);font-size:12px">${s.current_price != null ? Number(s.current_price).toFixed(2) : '-'}</td>
      <td><span class="${pnlCls(s.pnl_pct)}" style="font-family:var(--mono);font-size:12px">${pnlStr(s.pnl_pct)}</span></td>
      <td style="font-family:var(--mono);font-size:12px;color:var(--amber);font-weight:600">${s.vol_ratio != null ? Number(s.vol_ratio).toFixed(2) : '-'}x</td>
      ${history ? '' : `<td style="font-family:var(--mono);font-size:11px;color:var(--text3);text-align:center">${s.days_remaining ?? '-'}</td>`}
      <td style="text-align:center">${pinBtn(s)}</td>
    </tr>`;
  }

  const activeHTML = active.length === 0
    ? `<div class="coming-soon" style="padding:48px 20px">
        <div class="coming-icon">○</div>
        <div class="coming-title">目前無追蹤標的</div>
        <div class="coming-desc">趨勢池標的觸發量增提醒後，會自動加入 10 個交易日追蹤。</div>
      </div>`
    : `<div class="table-wrap" style="margin-top:16px">
        <div class="table-scroll">
          <table>
            <thead><tr>
              <th style="width:28px">#</th>
              <th>代號 / 名稱</th>
              <th onclick="tfActSort('trigger_date')" style="cursor:pointer">觸發日${sortIcon(aC, aA, 'trigger_date')}</th>
              <th onclick="tfActSort('pattern_score')" style="cursor:pointer">型態分數${sortIcon(aC, aA, 'pattern_score')}</th>
              <th>型態標籤</th>
              <th onclick="tfActSort('entry_price')" style="cursor:pointer">入池收盤${sortIcon(aC, aA, 'entry_price')}</th>
              <th onclick="tfActSort('current_price')" style="cursor:pointer">現價${sortIcon(aC, aA, 'current_price')}</th>
              <th onclick="tfActSort('pnl_pct')" style="cursor:pointer">損益${sortIcon(aC, aA, 'pnl_pct')}</th>
              <th onclick="tfActSort('vol_ratio')" style="cursor:pointer">量比${sortIcon(aC, aA, 'vol_ratio')}</th>
              <th onclick="tfActSort('days_remaining')" style="cursor:pointer">剩餘天${sortIcon(aC, aA, 'days_remaining')}</th>
              <th>釘選</th>
            </tr></thead>
            <tbody>${active.map((s, i) => rowHTML(s, i)).join('')}</tbody>
          </table>
        </div>
      </div>`;

  const historyHTML = expired.length === 0 ? '' : `<div class="sa-history-wrap">
    <div class="sa-history-header">
      <span class="sa-history-title">歷史紀錄</span>
      <div style="display:flex;align-items:center;gap:8px">
        <span class="sa-history-count">${expired.length} 筆</span>
        <button onclick="exportTrendFollowCSV()"
          style="font-size:11px;padding:3px 10px;border-radius:4px;border:1px solid var(--border);background:var(--bg3);color:var(--text2);cursor:pointer">
          匯出 CSV
        </button>
      </div>
    </div>
    <div class="table-scroll">
      <table class="sa-history-table">
        <thead><tr>
          <th onclick="tfHistSort('stock_id')" style="cursor:pointer">代號 / 名稱${sortIcon(hC, hA, 'stock_id')}</th>
          <th onclick="tfHistSort('trigger_date')" style="cursor:pointer">觸發日${sortIcon(hC, hA, 'trigger_date')}</th>
          <th onclick="tfHistSort('pattern_score')" style="cursor:pointer">型態分數${sortIcon(hC, hA, 'pattern_score')}</th>
          <th>型態標籤</th>
          <th onclick="tfHistSort('entry_price')" style="cursor:pointer">入池收盤${sortIcon(hC, hA, 'entry_price')}</th>
          <th onclick="tfHistSort('current_price')" style="cursor:pointer">現價${sortIcon(hC, hA, 'current_price')}</th>
          <th onclick="tfHistSort('pnl_pct')" style="cursor:pointer">損益${sortIcon(hC, hA, 'pnl_pct')}</th>
          <th onclick="tfHistSort('vol_ratio')" style="cursor:pointer">量比${sortIcon(hC, hA, 'vol_ratio')}</th>
          <th>釘選</th>
        </tr></thead>
        <tbody>${expired.map((s, i) => rowHTML(s, i, true)).join('')}</tbody>
      </table>
    </div>
  </div>`;

  main.innerHTML = `
    <div class="strategy-panel active">
      <div class="strat-header">
        <div class="strat-title">${strat.icon} ${strat.name}</div>
        <div class="strat-desc">${strat.description}</div>
      </div>
      ${summaryHTML}
      ${activeHTML}
      ${historyHTML}
    </div>`;
}
