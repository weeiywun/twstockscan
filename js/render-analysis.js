// ════════════════════════════════════════════════════
//  標的分析：渲染器
// ════════════════════════════════════════════════════
function renderStockAnalysis(strat, main) {
  const saData = DATA.stock_analysis_data;

  if (!saData) {
    main.innerHTML = `
      <div class="strategy-panel active">
        <div class="strat-header">
          <div class="strat-title">${strat.icon} ${strat.name}</div>
          <div class="strat-desc">${strat.description}</div>
        </div>
        <div class="coming-soon" style="padding:64px 20px">
          <div class="coming-icon">◎</div>
          <div class="coming-title">等待觸發</div>
          <div class="coming-desc">籌碼集中入池標的首次觸發量增訊號後加入追蹤。</div>
        </div>
      </div>`;
    const grid = document.getElementById('watchlistGrid');
    if (grid) grid.innerHTML = renderWatchlist();
    return;
  }

  // ── 排序輔助 ──
  function getValue(s, col) {
    if (col === 'chip_score') return s.quant_scores?.chip_score ?? -1;
    if (col === 'entry_date') return s.trigger_date || s.entry_date || '';
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

  // ── 主動標的排序狀態 ──
  if (window._actSortCol === undefined) { window._actSortCol = 'pnl_pct'; window._actSortAsc = false; }
  const aC = window._actSortCol, aA = window._actSortAsc;
  window.actSort = col => {
    window._actSortAsc = (window._actSortCol === col) ? !window._actSortAsc : false;
    window._actSortCol = col;
    renderStrategy();
  };

  // ── 歷史標的排序狀態 ──
  if (window._histSortCol === undefined) { window._histSortCol = 'entry_date'; window._histSortAsc = false; }
  const hC = window._histSortCol, hA = window._histSortAsc;
  window.histSort = col => {
    window._histSortAsc = (window._histSortCol === col) ? !window._histSortAsc : false;
    window._histSortCol = col;
    renderStrategy();
  };

  const active  = sortRows(saData.active  || [], aC, aA);
  const expired = sortRows(saData.expired || [], hC, hA);

  // ── CSV 匯出 ──
  window.exportHistoryCSV = () => {
    const headers = ['代號', '名稱', '產業', '入選日', '入選收盤', '現價', '損益%', '籌碼集中', '營收等級'];
    const rows = (saData.expired || []).map(s => [
      s.ticker,
      s.name,
      s.industry || '',
      s.trigger_date || s.entry_date || '',
      s.entry_price   != null ? s.entry_price.toFixed(2)   : '',
      s.current_price != null ? s.current_price.toFixed(2) : '',
      s.pnl_pct       != null ? s.pnl_pct.toFixed(2)       : '',
      s.quant_scores?.chip_score ?? '',
      s.rev_grade || '',
    ]);
    const csv = [headers, ...rows]
      .map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
      .join('\n');
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url;
    a.download = `history_${saData.last_updated || 'export'}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ── 顯示輔助 ──
  function pnlCls(pct) { return (pct || 0) >= 0 ? 'sa-pnl-pos' : 'sa-pnl-neg'; }
  function pnlStr(pct) {
    if (pct == null) return '—';
    return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
  }
  function revGradeBadge(grade) {
    const cfg = {
      S: { bg: 'rgba(46,213,115,0.15)', color: 'var(--green)' },
      A: { bg: 'rgba(46,213,115,0.10)', color: 'var(--green)' },
      B: { bg: 'rgba(240,136,62,0.12)', color: 'var(--amber)' },
      C: { bg: 'rgba(240,136,62,0.12)', color: 'var(--amber)' },
      D: { bg: 'rgba(248,81,73,0.10)',  color: 'var(--red)'   },
    };
    const c = cfg[grade] || { bg: 'var(--bg3)', color: 'var(--text3)' };
    return `<span style="font-size:10px;padding:2px 6px;border-radius:4px;background:${c.bg};color:${c.color};font-weight:600">${grade || '—'}</span>`;
  }

  // ── 主動標的表格 ──
  let activeHTML;
  if (active.length === 0) {
    activeHTML = `<div class="coming-soon" style="padding:48px 20px">
      <div class="coming-icon">◎</div>
      <div class="coming-title">目前無追蹤標的</div>
      <div class="coming-desc">籌碼集中入池標的觸發量增訊號後自動加入追蹤。</div>
    </div>`;
  } else {
    const rows = active.map((s, i) => {
      const market = s.market || guessMarket(s.ticker);
      const tvSym  = `${market}:${s.ticker}`;
      const eDate  = s.trigger_date || s.entry_date || '—';
      const chip   = s.quant_scores?.chip_score;
      return `<tr>
        <td style="font-family:var(--mono);font-size:11px;color:var(--text3)">${i + 1}</td>
        <td>
          <a href="https://www.tradingview.com/chart/?symbol=${tvSym}"
            onclick="openTV('${tvSym}', event)" style="text-decoration:none">
            <span class="stock-code" style="font-size:12px">${s.ticker}</span>
            <span style="font-size:9px;opacity:.45;font-family:var(--mono)">↗</span>
          </a>
          <span style="font-size:12px;color:var(--text2);margin-left:4px">${s.name}</span>
          <div style="font-size:10px;color:var(--text3)">${s.industry || ''}</div>
        </td>
        <td style="font-family:var(--mono);font-size:12px;color:var(--text3)">${eDate}</td>
        <td style="font-family:var(--mono);font-size:12px">${s.entry_price?.toFixed(1) ?? '—'}</td>
        <td style="font-family:var(--mono);font-size:12px">${s.current_price?.toFixed(1) ?? '—'}</td>
        <td><span class="${pnlCls(s.pnl_pct)}" style="font-family:var(--mono);font-size:12px">${pnlStr(s.pnl_pct)}</span></td>
        <td style="font-family:var(--mono);font-size:12px;color:var(--text2);text-align:center">${chip ?? '—'}</td>
        <td style="text-align:center">${revGradeBadge(s.rev_grade)}</td>
      </tr>`;
    }).join('');

    activeHTML = `<div class="table-wrap" style="margin-top:16px">
      <div class="table-scroll">
        <table>
          <thead><tr>
            <th style="width:28px">#</th>
            <th>代號 / 名稱</th>
            <th onclick="actSort('entry_date')" style="cursor:pointer">入選日${sortIcon(aC, aA, 'entry_date')}</th>
            <th onclick="actSort('entry_price')" style="cursor:pointer">入選收盤${sortIcon(aC, aA, 'entry_price')}</th>
            <th onclick="actSort('current_price')" style="cursor:pointer">現價${sortIcon(aC, aA, 'current_price')}</th>
            <th onclick="actSort('pnl_pct')" style="cursor:pointer">損益${sortIcon(aC, aA, 'pnl_pct')}</th>
            <th onclick="actSort('chip_score')" style="cursor:pointer">籌碼集中${sortIcon(aC, aA, 'chip_score')}</th>
            <th onclick="actSort('rev_grade')" style="cursor:pointer">營收等級${sortIcon(aC, aA, 'rev_grade')}</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>`;
  }

  // ── 歷史標的表格 ──
  let historyHTML = '';
  if (expired.length > 0) {
    const histRows = expired.map(s => {
      const eDate = s.trigger_date || s.entry_date || '—';
      const chip  = s.quant_scores?.chip_score;
      return `<tr>
        <td>
          <span class="stock-code" style="font-size:12px">${s.ticker}</span>
          <span style="font-size:12px;color:var(--text2);margin-left:5px">${s.name}</span>
          <div style="font-size:10px;color:var(--text3)">${s.industry || ''}</div>
        </td>
        <td style="font-family:var(--mono);font-size:12px;color:var(--text3)">${eDate}</td>
        <td style="font-family:var(--mono);font-size:12px">${s.entry_price?.toFixed(1) ?? '—'}</td>
        <td style="font-family:var(--mono);font-size:12px">${s.current_price?.toFixed(1) ?? '—'}</td>
        <td><span class="${pnlCls(s.pnl_pct)}" style="font-family:var(--mono);font-size:12px">${pnlStr(s.pnl_pct)}</span></td>
        <td style="font-family:var(--mono);font-size:12px;color:var(--text2);text-align:center">${chip ?? '—'}</td>
        <td style="text-align:center">${revGradeBadge(s.rev_grade)}</td>
      </tr>`;
    }).join('');

    historyHTML = `<div class="sa-history-wrap">
      <div class="sa-history-header">
        <span class="sa-history-title">歷史紀錄（保留一個月）</span>
        <div style="display:flex;align-items:center;gap:8px">
          <span class="sa-history-count">${expired.length} 筆</span>
          <button onclick="exportHistoryCSV()"
            style="font-size:11px;padding:3px 10px;border-radius:4px;border:1px solid var(--border);background:var(--bg3);color:var(--text2);cursor:pointer">
            匯出 CSV
          </button>
        </div>
      </div>
      <div class="table-scroll">
        <table class="sa-history-table">
          <thead><tr>
            <th onclick="histSort('ticker')" style="cursor:pointer">代號 / 名稱${sortIcon(hC, hA, 'ticker')}</th>
            <th onclick="histSort('entry_date')" style="cursor:pointer">入選日${sortIcon(hC, hA, 'entry_date')}</th>
            <th onclick="histSort('entry_price')" style="cursor:pointer">入選收盤${sortIcon(hC, hA, 'entry_price')}</th>
            <th onclick="histSort('current_price')" style="cursor:pointer">現價${sortIcon(hC, hA, 'current_price')}</th>
            <th onclick="histSort('pnl_pct')" style="cursor:pointer">損益${sortIcon(hC, hA, 'pnl_pct')}</th>
            <th onclick="histSort('chip_score')" style="cursor:pointer">籌碼集中${sortIcon(hC, hA, 'chip_score')}</th>
            <th onclick="histSort('rev_grade')" style="cursor:pointer">營收等級${sortIcon(hC, hA, 'rev_grade')}</th>
          </tr></thead>
          <tbody>${histRows}</tbody>
        </table>
      </div>
    </div>`;
  }

  // ── 統計列 ──
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
      <div class="summary-value" style="color:${avgPnl == null ? 'var(--text2)' : avgPnl >= 0 ? 'var(--green)' : 'var(--red)'}">
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
      <div class="summary-value" style="font-size:16px;font-family:var(--mono)">${saData.last_updated}</div>
      <div class="summary-sub">最後更新</div>
    </div>
  </div>`;

  main.innerHTML = `
    <div class="strategy-panel active">
      <div class="strat-header" style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:8px">
        <div>
          <div class="strat-title">${strat.icon} ${strat.name}</div>
          <div class="strat-desc">${strat.description}</div>
        </div>
        <button class="btn-csv" onclick="triggerPriceUpdate(this)" title="直接呼叫 FINMIND API 更新現價與損益" style="white-space:nowrap;align-self:center">↑ 更新現價</button>
      </div>
      ${summaryHTML}
      ${activeHTML}
      ${historyHTML}
    </div>`;

  const grid = document.getElementById('watchlistGrid');
  if (grid) grid.innerHTML = renderWatchlist();
}

// ════════════════════════════════════════════════════
