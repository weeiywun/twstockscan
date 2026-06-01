// ════════════════════════════════════════════════════
//  趨勢大戶標的追蹤：渲染器
// ════════════════════════════════════════════════════
const GH_BHT_TRACK = 'data/big_holder_trend_track.json';

function renderBigHolderTrendTrack(strat, main) {
  const trackData = DATA.big_holder_trend_track_data;

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
          <div class="coming-desc">每週六大戶掃描後自動加入追蹤。</div>
        </div>
      </div>`;
    return;
  }

  function getValue(s, col) {
    if (col === 'score') return s.pattern_score ?? s.score ?? -1;
    if (col === 'entry_date') return s.entry_date || '';
    return s[col] ?? '';
  }

  function sortRows(arr, col, asc) {
    return arr.slice().sort((a, b) => {
      const va = getValue(a, col), vb = getValue(b, col);
      const isDate = /^\d{4}-\d{2}-\d{2}/.test(String(va));
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

  if (window._bhtActSortCol === undefined) { window._bhtActSortCol = 'pnl_pct'; window._bhtActSortAsc = false; }
  if (window._bhtHistSortCol === undefined) { window._bhtHistSortCol = 'entry_date'; window._bhtHistSortAsc = false; }
  const aC = window._bhtActSortCol, aA = window._bhtActSortAsc;
  const hC = window._bhtHistSortCol, hA = window._bhtHistSortAsc;

  window.bhtActSort = col => {
    window._bhtActSortAsc = (window._bhtActSortCol === col) ? !window._bhtActSortAsc : false;
    window._bhtActSortCol = col;
    renderStrategy();
  };
  window.bhtHistSort = col => {
    window._bhtHistSortAsc = (window._bhtHistSortCol === col) ? !window._bhtHistSortAsc : false;
    window._bhtHistSortCol = col;
    renderStrategy();
  };

  const active  = sortRows(trackData.active  || [], aC, aA);
  const expired = sortRows(trackData.expired || [], hC, hA);

  window.bhtTogglePin = async (stockId) => {
    const lists = [trackData.active || [], trackData.expired || []];
    const item = lists.flat().find(s => s.stock_id === stockId);
    if (!item) return;
    item.pinned = !item.pinned;
    const ok = await ghWriteJson(GH_BHT_TRACK, trackData, `data: pin trend big holder ${stockId}`);
    if (ok) renderStrategy();
  };

  window.exportBhtCSV = () => {
    const headers = ['代號', '名稱', '產業', '入池日', '到期日', '入池收盤', '現價', '損益%', '20均量', '千張比例', '訊號', '釘選'];
    const rows = (trackData.expired || []).map(s => [
      s.stock_id, s.name, s.industry || '',
      s.entry_date || '', s.exit_date || '',
      s.entry_price   != null ? s.entry_price.toFixed(2)   : '',
      s.current_price != null ? s.current_price.toFixed(2) : '',
      s.pnl_pct       != null ? s.pnl_pct.toFixed(2)       : '',
      s.vol_20d_avg   != null ? s.vol_20d_avg               : '',
      s.big_pct_1000  != null ? s.big_pct_1000.toFixed(1)  : '',
      (s.tags || []).join(' / '),
      s.pinned ? 'Y' : '',
    ]);
    const csv = [headers, ...rows]
      .map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
      .join('\n');
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
    const a = Object.assign(document.createElement('a'), {
      href: URL.createObjectURL(blob),
      download: `trend_big_holder_track_${trackData.last_updated || 'export'}.csv`,
    });
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  };

  function pnlCls(pct) { return (pct || 0) >= 0 ? 'sa-pnl-pos' : 'sa-pnl-neg'; }
  function pnlStr(pct) {
    if (pct == null) return '—';
    return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
  }
  function fmtLots(v) { return v == null ? '—' : Math.round(Number(v)).toLocaleString(); }
  function tagBadges(tags) {
    return (tags || []).map(t => `<span class="tag-badge compact">${t}</span>`).join('');
  }
  function pinBtn(s) {
    const pinned = !!s.pinned;
    return `<button onclick="bhtTogglePin('${s.stock_id}')"
      title="${pinned ? '取消釘選（到期後自動移除）' : '釘選（永久保留）'}"
      style="font-size:14px;width:28px;height:26px;border-radius:4px;border:1px solid ${pinned ? 'var(--amber)' : 'var(--border)'};background:${pinned ? 'rgba(240,136,62,0.12)' : 'var(--bg3)'};color:${pinned ? 'var(--amber)' : 'var(--text3)'};cursor:pointer">
      ${pinned ? '★' : '☆'}
    </button>`;
  }

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

  let activeHTML;
  if (active.length === 0) {
    activeHTML = `<div class="coming-soon" style="padding:48px 20px">
      <div class="coming-icon">◉</div>
      <div class="coming-title">目前無追蹤標的</div>
      <div class="coming-desc">每週六大戶掃描後自動加入，觀察期 2 週。釘選標的永久保留。</div>
    </div>`;
  } else {
    const rows = active.map((s, i) => {
      const market = s.market || guessMarket(s.stock_id);
      const tvSym  = `${market}:${s.stock_id}`;
      const daysLabel = s.pinned ? '★ 釘選' : `${s.days_remaining ?? '—'} 天`;
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
        <td style="font-family:var(--mono);font-size:12px;color:var(--text3)">${s.entry_date || '—'}</td>
        <td style="font-family:var(--mono);font-size:12px">${s.entry_price?.toFixed(2) ?? '—'}</td>
        <td style="font-family:var(--mono);font-size:12px">${s.current_price?.toFixed(2) ?? '—'}</td>
        <td><span class="${pnlCls(s.pnl_pct)}" style="font-family:var(--mono);font-size:12px">${pnlStr(s.pnl_pct)}</span></td>
        <td style="font-family:var(--mono);font-size:12px">${fmtLots(s.vol_20d_avg)}</td>
        <td style="font-family:var(--mono);font-size:12px">${s.big_pct_1000?.toFixed(1) ?? '—'}%</td>
        <td>${tagBadges(s.tags)}</td>
        <td style="font-family:var(--mono);font-size:11px;color:${s.pinned ? 'var(--amber)' : 'var(--red)'};font-weight:600;text-align:center">${daysLabel}</td>
        <td style="text-align:center">${pinBtn(s)}</td>
      </tr>`;
    }).join('');

    activeHTML = `<div class="table-wrap" style="margin-top:16px">
      <div class="table-scroll">
        <table>
          <thead><tr>
            <th style="width:28px">#</th>
            <th>代號 / 名稱</th>
            <th onclick="bhtActSort('entry_date')" style="cursor:pointer">入池日${sortIcon(aC, aA, 'entry_date')}</th>
            <th onclick="bhtActSort('entry_price')" style="cursor:pointer">入池收盤${sortIcon(aC, aA, 'entry_price')}</th>
            <th onclick="bhtActSort('current_price')" style="cursor:pointer">現價${sortIcon(aC, aA, 'current_price')}</th>
            <th onclick="bhtActSort('pnl_pct')" style="cursor:pointer">損益${sortIcon(aC, aA, 'pnl_pct')}</th>
            <th onclick="bhtActSort('vol_20d_avg')" style="cursor:pointer">20均量${sortIcon(aC, aA, 'vol_20d_avg')}</th>
            <th onclick="bhtActSort('big_pct_1000')" style="cursor:pointer">千張比例${sortIcon(aC, aA, 'big_pct_1000')}</th>
            <th>籌碼訊號</th>
            <th onclick="bhtActSort('days_remaining')" style="cursor:pointer">剩餘${sortIcon(aC, aA, 'days_remaining')}</th>
            <th>釘選</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>`;
  }

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
        <td style="font-family:var(--mono);font-size:12px;color:var(--text3)">${s.entry_date || '—'}</td>
        <td style="font-family:var(--mono);font-size:12px">${s.entry_price?.toFixed(2) ?? '—'}</td>
        <td style="font-family:var(--mono);font-size:12px">${s.current_price?.toFixed(2) ?? '—'}</td>
        <td><span class="${pnlCls(s.pnl_pct)}" style="font-family:var(--mono);font-size:12px">${pnlStr(s.pnl_pct)}</span></td>
        <td style="font-family:var(--mono);font-size:12px">${fmtLots(s.vol_20d_avg)}</td>
        <td style="font-family:var(--mono);font-size:12px">${s.big_pct_1000?.toFixed(1) ?? '—'}%</td>
        <td>${tagBadges(s.tags)}</td>
        <td style="text-align:center">${pinBtn(s)}</td>
      </tr>`;
    }).join('');

    historyHTML = `<div class="sa-history-wrap">
      <div class="sa-history-header">
        <span class="sa-history-title">歷史紀錄（未釘選保留 7 曆日）</span>
        <div style="display:flex;align-items:center;gap:8px">
          <span class="sa-history-count">${expired.length} 筆</span>
          <button onclick="exportBhtCSV()"
            style="font-size:11px;padding:3px 10px;border-radius:4px;border:1px solid var(--border);background:var(--bg3);color:var(--text2);cursor:pointer">
            匯出 CSV
          </button>
        </div>
      </div>
      <div class="table-scroll">
        <table class="sa-history-table">
          <thead><tr>
            <th onclick="bhtHistSort('stock_id')" style="cursor:pointer">代號 / 名稱${sortIcon(hC, hA, 'stock_id')}</th>
            <th onclick="bhtHistSort('entry_date')" style="cursor:pointer">入池日${sortIcon(hC, hA, 'entry_date')}</th>
            <th onclick="bhtHistSort('entry_price')" style="cursor:pointer">入池收盤${sortIcon(hC, hA, 'entry_price')}</th>
            <th onclick="bhtHistSort('current_price')" style="cursor:pointer">現價${sortIcon(hC, hA, 'current_price')}</th>
            <th onclick="bhtHistSort('pnl_pct')" style="cursor:pointer">損益${sortIcon(hC, hA, 'pnl_pct')}</th>
            <th onclick="bhtHistSort('vol_20d_avg')" style="cursor:pointer">20均量${sortIcon(hC, hA, 'vol_20d_avg')}</th>
            <th onclick="bhtHistSort('big_pct_1000')" style="cursor:pointer">千張比例${sortIcon(hC, hA, 'big_pct_1000')}</th>
            <th>籌碼訊號</th>
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
