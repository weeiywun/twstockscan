function buildSSRRows() {
  return DATA.momentum_candidates_data?.focus_results || [];
}

function renderSSR(strat, main) {
  const momentumData = DATA.momentum_candidates_data || {};
  const sourceRows = momentumData.results || [];
  const focusRows = momentumData.focus_results || [];
  const lowBaseRows = momentumData.low_base_results || [];
  const trendRows = momentumData.trend_results || [];
  const view = window._stockPoolView || 'focus';
  const sortCol = window._ssrSortCol || 'pattern_score';
  const sortAsc = window._ssrSortAsc !== undefined ? window._ssrSortAsc : false;

  window.setStockPoolView = function setStockPoolView(v) {
    window._stockPoolView = v;
    renderStrategy();
  };

  window.ssrSort = function ssrSort(col) {
    if (window._ssrSortCol === col) window._ssrSortAsc = !window._ssrSortAsc;
    else { window._ssrSortCol = col; window._ssrSortAsc = false; }
    renderStrategy();
  };

  const stateOrder = { '值得看圖': 0, '先觀察': 1, '太遠不追': 2, '型態破壞': 3 };

  function fmtNum(v, digits = 2) {
    return v == null || Number.isNaN(Number(v)) ? '-' : Number(v).toFixed(digits);
  }

  function fmtPct(v, digits = 2) {
    return v == null || Number.isNaN(Number(v)) ? '-' : `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(digits)}%`;
  }

  function rowsForView() {
    if (view === 'low_base') return lowBaseRows;
    if (view === 'trend') return trendRows;
    if (view === 'all') return sourceRows;
    return focusRows;
  }

  function value(row, col) {
    const m = row.metrics || {};
    if (col === 'pattern_score') return row.pattern_score ?? 0;
    if (col === 'pattern_state') return stateOrder[row.pattern_state] ?? 9;
    if (col === 'volume_alert') return row.volume_alert ? 1 : 0;
    if (col === 'pool_type') return row.pool_type === 'low_base' ? 0 : 1;
    return row[col] ?? m[col];
  }

  function compare(a, b) {
    const va = value(a, sortCol);
    const vb = value(b, sortCol);
    const na = Number(va);
    const nb = Number(vb);
    const cmp = !Number.isNaN(na) && !Number.isNaN(nb)
      ? na - nb
      : String(va ?? '').localeCompare(String(vb ?? ''));
    return sortAsc ? cmp : -cmp;
  }

  function sortIcon(col) {
    if (sortCol !== col) return '<span class="sort-icon">·</span>';
    return `<span class="sort-icon">${sortAsc ? '↑' : '↓'}</span>`;
  }

  function stateColor(state) {
    if (state === '值得看圖') return 'var(--green)';
    if (state === '太遠不追') return 'var(--amber)';
    if (state === '型態破壞') return '#dc2626';
    return 'var(--text2)';
  }

  const viewOptions = [
    { key: 'focus', label: '值得看圖', count: focusRows.length },
    { key: 'low_base', label: '低基期', count: lowBaseRows.length },
    { key: 'trend', label: '趨勢', count: trendRows.length },
    { key: 'all', label: '全部', count: sourceRows.length },
  ];

  const viewButtons = viewOptions.map(opt => `
    <button class="view-btn ${view === opt.key ? 'active' : ''}"
      onclick="setStockPoolView('${opt.key}')">${opt.label} ${opt.count}</button>
  `).join('');

  const rows = rowsForView().slice().sort(compare);

  const rowsHTML = rows.map(row => {
    const m = row.metrics || {};
    const tvSymbol = getTVSymbol(row);
    const patState = row.pattern_state || '先觀察';
    const patScore = row.pattern_score ?? 0;
    const patTags = (row.pattern_tags || []).join(' ');
    const patternList = (row.patterns || []).join(' / ');
    const keyLevel = row.key_level;
    const invalidation = row.invalidation;
    const vol = m.today_vol_ratio;
    const color = stateColor(patState);
    const poolColor = row.pool_type === 'low_base' ? 'var(--green)' : 'var(--blue)';

    return `<tr>
      <td>
        <a href="https://www.tradingview.com/chart/?symbol=${tvSymbol}"
           onclick="openTV('${tvSymbol}', event)" style="text-decoration:none;display:inline-block">
          <div class="stock-code" style="display:flex;align-items:center;gap:5px">
            ${row.stock_id}<span style="font-size:9px;opacity:.45;font-family:var(--mono)">↗</span>
          </div>
          <div class="stock-name">${row.name || '-'}</div>
        </a>
        <div class="stock-industry" style="font-size:10px;color:var(--text3)">${row.industry || '-'}</div>
      </td>
      <td><span class="tag-badge" style="color:${poolColor};border-color:rgba(80,90,110,.35)">${row.pool_label || '-'}</span></td>
      <td><span class="tag-badge" style="color:${color};border-color:rgba(80,90,110,.35)">${patState}</span></td>
      <td>
        <span style="font-family:var(--mono);font-weight:700;color:${color}">${fmtNum(patScore, 1)}</span>
        ${row.pattern_confidence != null && Number(row.pattern_confidence) < 0.9
          ? `<br><span style="font-size:10px;color:var(--text3)">cf ${fmtNum(row.pattern_confidence, 2)}</span>`
          : ''}
      </td>
      <td style="font-size:11px;line-height:1.5;max-width:120px">
        ${patTags ? `<span style="color:var(--text)">${patTags}</span>` : ''}
        ${patternList ? `<br><span style="color:var(--text3)">${patternList}</span>` : ''}
        ${!patTags && !patternList ? '-' : ''}
      </td>
      <td style="font-family:var(--mono);font-size:12px;white-space:nowrap">
        ${keyLevel != null ? `<span style="color:var(--green);font-weight:700">${fmtNum(keyLevel, 2)}</span>` : '-'}
        ${invalidation != null ? `<br><span style="font-size:10px;color:#dc2626">↓ ${fmtNum(invalidation, 2)}</span>` : ''}
      </td>
      <td><span class="price-cell">${fmtNum(row.close, 1)}</span></td>
      <td style="font-size:11px;color:var(--text2);line-height:1.6">
        ${row.volume_alert ? `<span class="tag-badge" style="color:var(--amber);border-color:rgba(80,90,110,.35)">量增</span>` : '<span style="color:var(--text3)">-</span>'}
        ${vol != null ? `<span style="font-family:var(--mono);margin-left:4px">${fmtNum(vol, 2)}x</span>` : ''}
        <br>
        <span style="color:var(--text3)">EMA120 ${fmtPct(m.deviation, 1)} / BBW ${fmtNum(m.bbw, 1)}</span>
      </td>
    </tr>`;
  }).join('');

  window.exportFocusCSV = function exportFocusCSV() {
    const headers = [
      '代號', '名稱', '產業', '市場', '類型',
      '型態狀態', '型態分數', '型態標籤', '關鍵價', '失效價', '型態可信度',
      '收盤', '量增提醒', '量比', 'EMA120乖離(%)', '週漲跌(%)', 'BBW',
    ];
    const csvRows = rows.map(row => {
      const m = row.metrics || {};
      return [
        row.stock_id,
        row.name || '',
        row.industry || '',
        row.market || '',
        row.pool_label || '',
        row.pattern_state || '',
        row.pattern_score != null ? Number(row.pattern_score).toFixed(1) : '',
        (row.pattern_tags || []).join(' '),
        row.key_level != null ? Number(row.key_level).toFixed(2) : '',
        row.invalidation != null ? Number(row.invalidation).toFixed(2) : '',
        row.pattern_confidence != null ? Number(row.pattern_confidence).toFixed(2) : '',
        row.close ?? '',
        row.volume_alert ? 'Y' : '',
        m.today_vol_ratio != null ? Number(m.today_vol_ratio).toFixed(2) : '',
        m.deviation != null ? Number(m.deviation).toFixed(2) : '',
        m.week_chg_pct != null ? Number(m.week_chg_pct).toFixed(2) : '',
        m.bbw != null ? Number(m.bbw).toFixed(1) : '',
      ];
    });
    const csv = [headers, ...csvRows]
      .map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
      .join('\r\n');
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const updated = (momentumData.updated || '').slice(0, 10) || strat.dataUpdated || 'export';
    const a = Object.assign(document.createElement('a'), { href: url, download: `pattern_pool_${updated}.csv` });
    a.click();
    URL.revokeObjectURL(url);
  };

  main.innerHTML = `
    <div class="strategy-panel active">
      <div class="strat-header">
        <div class="strat-title">${strat.icon} ${strat.name}</div>
        <div class="strat-desc">${strat.description}</div>
      </div>
      <div class="table-wrap">
        <div class="table-toolbar">
          <span class="table-title">型態標的池</span>
          <div class="toolbar-right">
            <span class="updated-tag">值得看圖 ${momentumData.summary?.focus ?? focusRows.length} / 全部 ${momentumData.summary?.total || sourceRows.length}</span>
            <span class="updated-tag">更新：${(momentumData.updated || '').slice(0, 10) || strat.dataUpdated}</span>
            <button class="btn-csv" onclick="exportFocusCSV()">匯出 CSV</button>
          </div>
        </div>
        <div style="padding:10px 14px;border-bottom:1px solid var(--border);font-size:12px;color:var(--text3);line-height:1.7">
          標的池只以型態狀態與型態分數排序；量增只作提醒，低基期與趨勢只作分類。
        </div>
        <div style="display:flex;gap:8px;padding:10px 14px;border-bottom:1px solid var(--border);flex-wrap:wrap">
          ${viewButtons}
        </div>
        <div class="table-scroll ${rows.length > 10 ? 'table-vscroll' : ''}">
          <table>
            <thead>
              <tr>
                <th onclick="ssrSort('stock_id')" style="cursor:pointer">代號 / 名稱${sortIcon('stock_id')}</th>
                <th onclick="ssrSort('pool_type')" style="cursor:pointer">類型${sortIcon('pool_type')}</th>
                <th onclick="ssrSort('pattern_state')" style="cursor:pointer">型態狀態${sortIcon('pattern_state')}</th>
                <th onclick="ssrSort('pattern_score')" style="cursor:pointer">型態分數${sortIcon('pattern_score')}</th>
                <th>型態標籤</th>
                <th>關鍵 / 失效</th>
                <th onclick="ssrSort('close')" style="cursor:pointer">收盤${sortIcon('close')}</th>
                <th onclick="ssrSort('volume_alert')" style="cursor:pointer">量增提醒${sortIcon('volume_alert')}</th>
              </tr>
            </thead>
            <tbody>${rowsHTML || `<tr><td colspan="8" style="text-align:center;color:var(--text3);padding:28px">目前沒有符合此分類的標的</td></tr>`}</tbody>
          </table>
        </div>
      </div>
    </div>`;
}
