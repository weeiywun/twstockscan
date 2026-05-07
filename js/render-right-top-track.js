// ════════════════════════════════════════════════════
//  右上角標的追蹤：渲染器
// ════════════════════════════════════════════════════
function renderRightTopTrack(strat, main) {
  const trackData = DATA.right_top_track_data;

  if (!trackData) {
    main.innerHTML = `
      <div class="strategy-panel active">
        <div class="strat-header">
          <div class="strat-title">${strat.icon} ${strat.name}</div>
          <div class="strat-desc">${strat.description}</div>
        </div>
        <div class="coming-soon" style="padding:64px 20px">
          <div class="coming-icon">◉</div>
          <div class="coming-title">等待資料</div>
          <div class="coming-desc">右上角策略觸發後盤後自動加入追蹤。</div>
        </div>
      </div>`;
    return;
  }

  // ── 排序輔助 ──
  function getValue(s, col) {
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
    return `<span class="sort-icon">${stateCol === col ? (stateAsc ? '↑' : '↓') : '·'}</span>`;
  }

  // Active 排序狀態
  if (window._rttActSortCol === undefined) { window._rttActSortCol = 'pnl_pct'; window._rttActSortAsc = false; }
  const aC = window._rttActSortCol, aA = window._rttActSortAsc;
  window.rttActSort = col => {
    window._rttActSortAsc = (window._rttActSortCol === col) ? !window._rttActSortAsc : false;
    window._rttActSortCol = col;
    renderStrategy();
  };

  // History 排序狀態
  if (window._rttHistSortCol === undefined) { window._rttHistSortCol = 'trigger_date'; window._rttHistSortAsc = false; }
  const hC = window._rttHistSortCol, hA = window._rttHistSortAsc;
  window.rttHistSort = col => {
    window._rttHistSortAsc = (window._rttHistSortCol === col) ? !window._rttHistSortAsc : false;
    window._rttHistSortCol = col;
    renderStrategy();
  };

  const active  = sortRows(trackData.active  || [], aC, aA);
  const expired = sortRows(trackData.expired || [], hC, hA);

  window.rttTogglePin = async (stockId) => {
    const lists = [trackData.active || [], trackData.expired || []];
    const item = lists.flat().find(s => s.stock_id === stockId);
    if (!item) return;
    item.pinned = !item.pinned;
    if (!item.pinned && item.remove_date) item.remove_date = addTradingDaysTW(5);
    const ok = await ghWriteJson(GH_RTT_TRACK, trackData, `data: pin right top ${stockId}`);
    if (ok) renderStrategy();
  };

  // ── CSV 匯出 ──
  window.exportRttCSV = () => {
    const headers = ['代號', '名稱', '產業', '市場', '觸發日', '訊號週', '入選收盤', '現價', '損益%', '量比', '釘選'];
    const rows = (trackData.expired || []).map(s => [
      s.stock_id, s.name, s.industry || '', s.market || '',
      s.trigger_date || '',
      s.week_date || '',
      s.entry_price   != null ? s.entry_price.toFixed(2)   : '',
      s.current_price != null ? s.current_price.toFixed(2) : '',
      s.pnl_pct       != null ? s.pnl_pct.toFixed(2)       : '',
      s.vol_ratio     != null ? s.vol_ratio.toFixed(2)      : '',
      s.pinned ? 'Y' : '',
    ]);
    const csv = [headers, ...rows]
      .map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
      .join('\n');
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url;
    a.download = `right_top_track_${trackData.last_updated || 'export'}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ── 顯示輔助 ──
  function pnlCls(pct) { return (pct || 0) >= 0 ? 'sa-pnl-pos' : 'sa-pnl-neg'; }
  function pnlStr(pct) {
    if (pct == null) return '—';
    return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
  }
  function pinBtn(s) {
    const pinned = !!s.pinned;
    return `<button onclick="rttTogglePin('${s.stock_id}')"
      title="${pinned ? '取消釘選' : '釘選觀察'}"
      style="font-size:14px;width:28px;height:26px;border-radius:4px;border:1px solid ${pinned ? 'var(--amber)' : 'var(--border)'};background:${pinned ? 'rgba(240,136,62,0.12)' : 'var(--bg3)'};color:${pinned ? 'var(--amber)' : 'var(--text3)'};cursor:pointer">
      ${pinned ? '★' : '☆'}
    </button>`;
  }

  // ── 統計 ──
  const avgPnl = active.length
    ? active.reduce((s, r) => s + (r.pnl_pct || 0), 0) / active.length
    : null;

  const summaryHTML = `<div class="summary-row">
    <div class="summary-card">
      <div class="summary-label">追蹤中</div>
      <div class="summary-value green">${active.length}</div>
      <div class="summary-sub">支標的</div>
    </div>
    <div class="summary-card">
      <div class="summary-label">平均損益</div>
      <div class="summary-value" style="color:${avgPnl == null ? 'var(--text2)' : avgPnl >= 0 ? 'var(--market-up)' : 'var(--market-down)'}">
        ${avgPnl != null ? `${avgPnl >= 0 ? '+' : ''}${avgPnl.toFixed(2)}%` : '—'}
      </div>
      <div class="summary-sub">本批平均</div>
    </div>
    <div class="summary-card">
      <div class="summary-label">歷史紀錄</div>
      <div class="summary-value">${expired.length}</div>
      <div class="summary-sub">筆結束追蹤</div>
    </div>
    <div class="summary-card">
      <div class="summary-label">資料日期</div>
      <div class="summary-value" style="font-size:16px;font-family:var(--mono)">${trackData.last_updated || '—'}</div>
      <div class="summary-sub">最後更新</div>
    </div>
  </div>`;

  // ── 主動標的表格 ──
  let activeHTML;
  if (active.length === 0) {
    activeHTML = `<div class="coming-soon" style="padding:48px 20px">
      <div class="coming-icon">◉</div>
      <div class="coming-title">目前無追蹤標的</div>
      <div class="coming-desc">右上角策略觸發標的盤後自動加入追蹤，觀察 10 個交易日。</div>
    </div>`;
  } else {
    const rows = active.map((s, i) => {
      const market = s.market || guessMarket(s.stock_id);
      const tvSym  = `${market}:${s.stock_id}`;
      return `<tr>
        <td style="font-family:var(--mono);font-size:11px;color:var(--text3)">${i + 1}</td>
        <td>
          <a href="https://www.tradingview.com/chart/?symbol=${tvSym}"
            onclick="openTV('${tvSym}', event)" style="text-decoration:none">
            <span class="stock-code" style="font-size:12px">${s.stock_id}</span>
            <span style="font-size:9px;opacity:.45;font-family:var(--mono)">↗</span>
          </a>
          <span style="font-size:12px;color:var(--text2);margin-left:4px">${s.name}</span>
          <div style="font-size:10px;color:var(--text3)">${s.industry || ''}</div>
        </td>
        <td style="font-family:var(--mono);font-size:12px;color:var(--text3)">${s.trigger_date || '—'}</td>
        <td style="font-family:var(--mono);font-size:12px;color:var(--text3)">${s.week_date || '—'}</td>
        <td style="font-family:var(--mono);font-size:12px">${s.entry_price?.toFixed(2) ?? '—'}</td>
        <td style="font-family:var(--mono);font-size:12px">${s.current_price?.toFixed(2) ?? '—'}</td>
        <td><span class="${pnlCls(s.pnl_pct)}" style="font-family:var(--mono);font-size:12px">${pnlStr(s.pnl_pct)}</span></td>
        <td style="font-family:var(--mono);font-size:12px;color:var(--red);font-weight:600">${s.vol_ratio?.toFixed(2) ?? '—'}x</td>
        <td style="font-family:var(--mono);font-size:11px;color:var(--text3);text-align:center">${s.days_remaining ?? '—'}</td>
        <td style="text-align:center">${pinBtn(s)}</td>
      </tr>`;
    }).join('');

    activeHTML = `<div class="table-wrap" style="margin-top:16px">
      <div class="table-scroll">
        <table>
          <thead><tr>
            <th style="width:28px">#</th>
            <th>代號 / 名稱</th>
            <th onclick="rttActSort('trigger_date')" style="cursor:pointer">觸發日${sortIcon(aC, aA, 'trigger_date')}</th>
            <th onclick="rttActSort('week_date')" style="cursor:pointer">訊號週${sortIcon(aC, aA, 'week_date')}</th>
            <th onclick="rttActSort('entry_price')" style="cursor:pointer">入選收盤${sortIcon(aC, aA, 'entry_price')}</th>
            <th onclick="rttActSort('current_price')" style="cursor:pointer">現價${sortIcon(aC, aA, 'current_price')}</th>
            <th onclick="rttActSort('pnl_pct')" style="cursor:pointer">損益${sortIcon(aC, aA, 'pnl_pct')}</th>
            <th onclick="rttActSort('vol_ratio')" style="cursor:pointer">量比${sortIcon(aC, aA, 'vol_ratio')}</th>
            <th onclick="rttActSort('days_remaining')" style="cursor:pointer">剩餘天${sortIcon(aC, aA, 'days_remaining')}</th>
            <th>釘選</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>`;
  }

  // ── 歷史表格 ──
  let historyHTML = '';
  if (expired.length > 0) {
    const histRows = expired.map(s => {
      const market = s.market || guessMarket(s.stock_id);
      const tvSym  = `${market}:${s.stock_id}`;
      return `<tr>
        <td>
          <a href="https://www.tradingview.com/chart/?symbol=${tvSym}"
            onclick="openTV('${tvSym}', event)" style="text-decoration:none">
            <span class="stock-code" style="font-size:12px">${s.stock_id}</span>
            <span style="font-size:9px;opacity:.45;font-family:var(--mono)">↗</span>
          </a>
          <span style="font-size:12px;color:var(--text2);margin-left:4px">${s.name}</span>
          <div style="font-size:10px;color:var(--text3)">${s.industry || ''}</div>
        </td>
        <td style="font-family:var(--mono);font-size:12px;color:var(--text3)">${s.trigger_date || '—'}</td>
        <td style="font-family:var(--mono);font-size:12px;color:var(--text3)">${s.week_date || '—'}</td>
        <td style="font-family:var(--mono);font-size:12px">${s.entry_price?.toFixed(2) ?? '—'}</td>
        <td style="font-family:var(--mono);font-size:12px">${s.current_price?.toFixed(2) ?? '—'}</td>
        <td><span class="${pnlCls(s.pnl_pct)}" style="font-family:var(--mono);font-size:12px">${pnlStr(s.pnl_pct)}</span></td>
        <td style="font-family:var(--mono);font-size:12px;color:var(--red);font-weight:600">${s.vol_ratio?.toFixed(2) ?? '—'}x</td>
        <td style="text-align:center">${pinBtn(s)}</td>
      </tr>`;
    }).join('');

    historyHTML = `<div class="sa-history-wrap">
      <div class="sa-history-header">
        <span class="sa-history-title">歷史紀錄（未釘選保留 5 個交易日）</span>
        <div style="display:flex;align-items:center;gap:8px">
          <span class="sa-history-count">${expired.length} 筆</span>
          <button onclick="exportRttCSV()"
            style="font-size:11px;padding:3px 10px;border-radius:4px;border:1px solid var(--border);background:var(--bg3);color:var(--text2);cursor:pointer">
            匯出 CSV
          </button>
        </div>
      </div>
      <div class="table-scroll">
        <table class="sa-history-table">
          <thead><tr>
            <th onclick="rttHistSort('stock_id')" style="cursor:pointer">代號 / 名稱${sortIcon(hC, hA, 'stock_id')}</th>
            <th onclick="rttHistSort('trigger_date')" style="cursor:pointer">觸發日${sortIcon(hC, hA, 'trigger_date')}</th>
            <th onclick="rttHistSort('week_date')" style="cursor:pointer">訊號週${sortIcon(hC, hA, 'week_date')}</th>
            <th onclick="rttHistSort('entry_price')" style="cursor:pointer">入選收盤${sortIcon(hC, hA, 'entry_price')}</th>
            <th onclick="rttHistSort('current_price')" style="cursor:pointer">現價${sortIcon(hC, hA, 'current_price')}</th>
            <th onclick="rttHistSort('pnl_pct')" style="cursor:pointer">損益${sortIcon(hC, hA, 'pnl_pct')}</th>
            <th onclick="rttHistSort('vol_ratio')" style="cursor:pointer">量比${sortIcon(hC, hA, 'vol_ratio')}</th>
            <th>釘選</th>
          </tr></thead>
          <tbody>${histRows}</tbody>
        </table>
      </div>
    </div>`;
  }

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

// ════════════════════════════════════════════════════
