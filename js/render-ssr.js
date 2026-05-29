function buildSSRRows() {
  return DATA.momentum_candidates_data?.focus_results || [];
}

function renderSSR(strat, main) {
  const momentumData = DATA.momentum_candidates_data || {};
  const focusRows = momentumData.focus_results || [];
  const sourceFilter = window._stockPoolSourceFilter || 'all';
  const sortCol = window._ssrSortCol || 'score';
  const sortAsc = window._ssrSortAsc !== undefined ? window._ssrSortAsc : false;

  window.setStockPoolSourceFilter = function setStockPoolSourceFilter(v) {
    window._stockPoolSourceFilter = v;
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

  function sourceLabel(src) {
    return ({
      chips: '大戶',
      volume_signal: '量增',
      right_top_track: '突破追蹤',
      volume_pullback: '量增回測',
      stock_analysis: '標的追蹤',
      momentum_candidates: '標的池',
    }[src] || src);
  }

  function matchesSource(row, filter) {
    const sources = new Set(row.sources || []);
    if (filter === 'chips') return sources.has('chips');
    if (filter === 'volume_signal') return sources.has('volume_signal');
    if (filter === 'right_top_track') return sources.has('right_top_track');
    if (filter === 'volume_pullback') return sources.has('volume_pullback');
    return true;
  }

  function sourceCount(filter) {
    return focusRows.filter(row => matchesSource(row, filter)).length;
  }

  function value(row, col) {
    const m = row.metrics || {};
    if (col === 'score') return row.pattern_score ?? row.context_score ?? row.unified_score ?? row.score ?? 0;
    if (col === 'pattern_state') return stateOrder[row.pattern_state] ?? 9;
    if (col === 'primary_metric') return m.ignition_vol_ratio ?? m.today_vol_ratio ?? m.track_vol_ratio ?? 0;
    if (col === 'track_pnl_pct') return m.track_pnl_pct ?? -999;
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
    return `<span class="sort-icon">${sortCol === col ? (sortAsc ? '↑' : '↓') : '·'}</span>`;
  }

  function stateColor(state) {
    if (state === '值得看圖') return 'var(--green)';
    if (state === '太遠不追') return 'var(--amber)';
    if (state === '型態破壞') return '#dc2626';
    return 'var(--text2)';
  }

  const filters = [
    { key: 'all', label: '全部', count: focusRows.length },
    { key: 'chips', label: '大戶', count: sourceCount('chips') },
    { key: 'volume_signal', label: '量增', count: sourceCount('volume_signal') },
    { key: 'right_top_track', label: '突破', count: sourceCount('right_top_track') },
    { key: 'volume_pullback', label: '回測', count: sourceCount('volume_pullback') },
  ];

  const filterButtons = filters.map(opt => `
    <button class="view-btn ${sourceFilter === opt.key ? 'active' : ''}"
      onclick="setStockPoolSourceFilter('${opt.key}')">${opt.label} ${opt.count}</button>
  `).join('');

  const rows = focusRows
    .filter(row => matchesSource(row, sourceFilter))
    .sort(compare);

  const rowsHTML = rows.map(row => {
    const m = row.metrics || {};
    const tvSymbol = getTVSymbol(row);
    const patState = row.pattern_state || '先觀察';
    const patScore = row.pattern_score ?? 0;
    const patTags = (row.pattern_tags || []).join(' ');
    const patternList = (row.patterns || []).join(' / ');
    const keyLevel = row.key_level;
    const invalidation = row.invalidation;
    const ctxScore = row.context_score ?? row.unified_score ?? row.score ?? 0;
    const vol = m.today_vol_ratio ?? m.ignition_vol_ratio ?? m.track_vol_ratio;
    const track = m.track_pnl_pct;
    const color = stateColor(patState);

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
        <span style="font-family:var(--mono)">${fmtNum(ctxScore, 0)}</span> ctx
        ${vol != null ? ` · 量 ${fmtNum(vol, 2)}x` : ''}
        ${track != null ? ` · <span class="${Number(track) >= 0 ? 'pos' : 'neg'}">${fmtPct(track, 1)}</span>` : ''}
        <br>${(row.sources || []).map(s => `<span class="tag-badge" style="color:var(--text3);border-color:rgba(80,90,110,.25)">${sourceLabel(s)}</span>`).join('')}
      </td>
    </tr>`;
  }).join('');

  window.exportFocusCSV = function exportFocusCSV() {
    const headers = [
      '代號', '名稱', '產業', '市場',
      '型態狀態', '型態分', '型態標籤', '關鍵價', '失效價', '型態可信度',
      '收盤', '量比', '追蹤損益(%)', '週漲跌(%)', 'BBW', 'context_score', '來源',
    ];
    const csvRows = rows.map(row => {
      const m = row.metrics || {};
      const vol = m.today_vol_ratio ?? m.ignition_vol_ratio ?? m.track_vol_ratio;
      return [
        row.stock_id,
        row.name || '',
        row.industry || '',
        row.market || '',
        row.pattern_state || '',
        row.pattern_score != null ? Number(row.pattern_score).toFixed(1) : '',
        (row.pattern_tags || []).join(' '),
        row.key_level != null ? Number(row.key_level).toFixed(2) : '',
        row.invalidation != null ? Number(row.invalidation).toFixed(2) : '',
        row.pattern_confidence != null ? Number(row.pattern_confidence).toFixed(2) : '',
        row.close ?? '',
        vol != null ? Number(vol).toFixed(2) : '',
        m.track_pnl_pct != null ? Number(m.track_pnl_pct).toFixed(2) : '',
        m.week_chg_pct != null ? Number(m.week_chg_pct).toFixed(2) : '',
        m.bbw != null ? Number(m.bbw).toFixed(1) : '',
        row.context_score ?? row.unified_score ?? row.score ?? '',
        (row.sources || []).map(sourceLabel).join(' / '),
      ];
    });
    const csv = [headers, ...csvRows]
      .map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
      .join('\r\n');
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const updated = (momentumData.updated || '').slice(0, 10) || strat.dataUpdated || 'export';
    const a = Object.assign(document.createElement('a'), { href: url, download: `focus_pool_${updated}.csv` });
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
          <span class="table-title">標的池</span>
          <div class="toolbar-right">
            <span class="updated-tag">值得看圖 ${momentumData.summary?.pattern_watch ?? focusRows.length} / 全 ${momentumData.summary?.total || focusRows.length}</span>
            <span class="updated-tag">更新：${(momentumData.updated || '').slice(0, 10) || strat.dataUpdated}</span>
            <button class="btn-csv" onclick="exportFocusCSV()">匯出 CSV</button>
          </div>
        </div>
        <div style="padding:10px 14px;border-bottom:1px solid var(--border);font-size:12px;color:var(--text3);line-height:1.7">
          僅顯示 pattern_state＝值得看圖 的標的，依型態分排序；context_score 與來源標籤為次要參考。
        </div>
        <div style="display:flex;gap:8px;padding:10px 14px;border-bottom:1px solid var(--border);flex-wrap:wrap">
          ${filterButtons}
        </div>
        <div class="table-scroll ${rows.length > 10 ? 'table-vscroll' : ''}">
          <table>
            <thead>
              <tr>
                <th onclick="ssrSort('stock_id')" style="cursor:pointer">代號 / 名稱${sortIcon('stock_id')}</th>
                <th onclick="ssrSort('pattern_state')" style="cursor:pointer">型態狀態${sortIcon('pattern_state')}</th>
                <th onclick="ssrSort('score')" style="cursor:pointer">型態分${sortIcon('score')}</th>
                <th>型態標籤</th>
                <th>關鍵 / 失效</th>
                <th onclick="ssrSort('close')" style="cursor:pointer">收盤${sortIcon('close')}</th>
                <th>來源 / 背景</th>
              </tr>
            </thead>
            <tbody>${rowsHTML || `<tr><td colspan="7" style="text-align:center;color:var(--text3);padding:28px">目前沒有標的池候選（型態狀態＝值得看圖）</td></tr>`}</tbody>
          </table>
        </div>
      </div>
    </div>`;
}
