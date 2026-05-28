let bigHolderTrendSortCol = 'score';
let bigHolderTrendSortAsc = false;

function renderBigHolderTrend(strat, main) {
  const data = DATA.big_holder_trend_data || [];
  if (!data.length) {
    main.innerHTML = `<div class="coming-soon">
      <div class="coming-icon">${strat.icon}</div>
      <div class="coming-title">${strat.name}</div>
      <div class="coming-desc">尚未產生大戶趨勢池資料。請先執行每週大戶掃描。</div>
    </div>`;
    return;
  }

  const fmt = (v, digits = 2) => v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(digits);
  const fmtPct = v => v == null || Number.isNaN(Number(v)) ? '—' : `${Number(v) > 0 ? '+' : ''}${Number(v).toFixed(2)}%`;
  const fmtLots = v => v == null || Number.isNaN(Number(v)) ? '—' : Math.round(Number(v)).toLocaleString();
  const sortIcon = col => `<span class="sort-icon">${bigHolderTrendSortCol === col ? (bigHolderTrendSortAsc ? '↑' : '↓') : '·'}</span>`;
  const trendLine = (label, values) => {
    const parts = Array.isArray(values) && values.length
      ? values.map(v => `${fmt(v)}%`).join(' → ')
      : '—';
    return `<div style="white-space:nowrap"><span style="color:var(--text3);margin-right:4px">${label}</span>${parts}</div>`;
  };
  const sortValue = row => {
    if (bigHolderTrendSortCol === 'score') return row.unified_score ?? row.score ?? 0;
    if (bigHolderTrendSortCol === 'entry_close') return row.entry_close ?? row.close ?? 0;
    if (bigHolderTrendSortCol === 'latest_close') return row.latest_close ?? row.close ?? 0;
    if (bigHolderTrendSortCol === 'since_entry_pct') return row.since_entry_pct ?? 0;
    if (bigHolderTrendSortCol === 'week_chg_pct') return row.week_chg_pct ?? 0;
    return row[bigHolderTrendSortCol];
  };
  const rows = data.slice().sort((a, b) => {
    const va = sortValue(a) ?? -9999;
    const vb = sortValue(b) ?? -9999;
    if (typeof va === 'string' || typeof vb === 'string') {
      return bigHolderTrendSortAsc
        ? String(va).localeCompare(String(vb))
        : String(vb).localeCompare(String(va));
    }
    return bigHolderTrendSortAsc ? va - vb : vb - va;
  });

  const avgScore = rows.reduce((sum, row) => sum + Number(row.unified_score ?? row.score ?? 0), 0) / rows.length;
  const avgReturn = rows.reduce((sum, row) => sum + Number(row.since_entry_pct ?? 0), 0) / rows.length;
  const sourceDate = strat.dataUpdated || '—';
  const priceUpdated = DATA.big_holder_trend_meta?.price_updated || rows[0]?.latest_price_date || sourceDate;

  const tableRows = rows.map(row => {
    const score = row.unified_score ?? row.score;
    const grade = row.unified_score_grade || '';
    const entryClose = row.entry_close ?? row.close;
    const latestClose = row.latest_close ?? row.close;
    const sinceEntryClass = (row.since_entry_pct ?? 0) >= 0 ? 'pos' : 'neg';
    const weekClass = (row.week_chg_pct ?? 0) >= 0 ? 'pos' : 'neg';
    const tags = (row.tags || []).map(tag => `<span class="tag-badge">${tag}</span>`).join('');
    return `<tr>
      <td>
        <a href="https://www.tradingview.com/chart/?symbol=${getTVSymbol(row)}"
          onclick="openTV('${getTVSymbol(row)}', event)"
          style="text-decoration:none;display:inline-block">
          <div class="stock-code" style="display:flex;align-items:center;gap:5px">
            ${row.stock_id}<span style="font-size:9px;opacity:.45;font-family:var(--mono)">↗</span>
          </div>
          <div class="stock-name">${row.name || ''}</div>
        </a>
        <div class="stock-industry">${row.industry || ''}</div>
      </td>
      <td>
        <span style="font-family:var(--mono);font-weight:700;color:var(--green)">${score != null ? fmt(score, 1) : '—'}</span>
        <span style="font-size:10px;color:var(--text3);margin-left:4px">${grade}</span>
      </td>
      <td>
        <span class="price-cell">${fmt(entryClose, 1)}</span><br>
        <span style="font-size:11px;color:var(--text3)">${row.entry_date || sourceDate}</span>
      </td>
      <td>
        <span class="price-cell">${fmt(latestClose, 1)}</span><br>
        <span style="font-size:11px;color:var(--text3)">${row.latest_price_date || priceUpdated}</span>
      </td>
      <td><span class="deviation ${sinceEntryClass}">${fmtPct(row.since_entry_pct)}</span></td>
      <td><span style="font-family:var(--mono);font-size:12px">${fmtLots(row.vol_20d_avg)}</span></td>
      <td><span class="deviation pos">${fmtPct(row.max_gain_60d)}</span></td>
      <td><span class="deviation ${weekClass}">${fmtPct(row.week_chg_pct)}</span></td>
      <td><div style="display:flex;gap:4px;flex-wrap:wrap">${tags}</div></td>
      <td style="font-family:var(--mono);font-size:11px;line-height:1.7">
        ${trendLine('千張', row.big_trend_1000)}
        ${trendLine('400', row.big_trend_400)}
      </td>
    </tr>`;
  }).join('');

  main.innerHTML = `
    <div class="strategy-panel active">
      <div class="strat-header">
        <div class="strat-title">${strat.icon} ${strat.name}</div>
        <div class="strat-desc">${strat.description}</div>
      </div>
      <div class="conditions">
        ${strat.conditions.map(c => `<div class="cond"><span class="cond-dot"></span>${c}</div>`).join('')}
      </div>
      <div class="summary-row">
        <div class="summary-card">
          <div class="summary-label">入池標的</div>
          <div class="summary-value green">${rows.length}</div>
          <div class="summary-sub">週六固定名單</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">平均分數</div>
          <div class="summary-value amber">${fmt(avgScore, 1)}</div>
          <div class="summary-sub">統一分數模型</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">入池後平均漲幅</div>
          <div class="summary-value ${avgReturn >= 0 ? 'green' : 'red'}">${fmtPct(avgReturn)}</div>
          <div class="summary-sub">即時價 vs 入池現價</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">資料日期</div>
          <div class="summary-value" style="font-size:16px;font-family:var(--mono)">${sourceDate}</div>
          <div class="summary-sub">收盤更新 ${priceUpdated}</div>
        </div>
      </div>
      <div class="table-wrap">
        <div class="table-toolbar">
          <span class="table-title">篩選結果</span>
          <div class="toolbar-right">
            <span class="updated-tag">篩選：${sourceDate}　收盤：${priceUpdated}</span>
            <button class="btn-csv" onclick="exportCSVBigHolderTrend()" title="匯出 CSV">↥ 匯出 CSV</button>
          </div>
        </div>
        <div class="table-scroll ${rows.length > 10 ? 'table-vscroll' : ''}">
          <table id="bigHolderTrendTable">
            <thead>
              <tr>
                <th onclick="bigHolderTrendSort('stock_id')">代號 / 名稱${sortIcon('stock_id')}</th>
                <th onclick="bigHolderTrendSort('score')">分數${sortIcon('score')}</th>
                <th onclick="bigHolderTrendSort('entry_close')">現價${sortIcon('entry_close')}</th>
                <th onclick="bigHolderTrendSort('latest_close')">即時${sortIcon('latest_close')}</th>
                <th onclick="bigHolderTrendSort('since_entry_pct')">漲幅${sortIcon('since_entry_pct')}</th>
                <th onclick="bigHolderTrendSort('vol_20d_avg')">20均量${sortIcon('vol_20d_avg')}</th>
                <th onclick="bigHolderTrendSort('max_gain_60d')">60日漲幅${sortIcon('max_gain_60d')}</th>
                <th onclick="bigHolderTrendSort('week_chg_pct')">單周增幅${sortIcon('week_chg_pct')}</th>
                <th>訊號</th>
                <th>大戶比例</th>
              </tr>
            </thead>
            <tbody>${tableRows}</tbody>
          </table>
        </div>
      </div>
    </div>`;
}

function bigHolderTrendSort(col) {
  if (bigHolderTrendSortCol === col) bigHolderTrendSortAsc = !bigHolderTrendSortAsc;
  else {
    bigHolderTrendSortCol = col;
    bigHolderTrendSortAsc = false;
  }
  const strat = STRATEGIES.find(s => s.id === 'big_holder_trend');
  renderBigHolderTrend(strat, document.getElementById('mainContent'));
}

function exportCSVBigHolderTrend() {
  const data = DATA.big_holder_trend_data || [];
  if (!data.length) return;
  const headers = [
    '代號', '名稱', '產業', '分數', '現價', '現價日期', '即時', '即時日期', '漲幅(%)',
    '20均量', '60日漲幅(%)', '單周增幅(%)', '訊號', '千張近四週', '400張近四週',
  ];
  const rows = data.map(row => [
    row.stock_id || '',
    row.name || '',
    row.industry || '',
    row.unified_score ?? row.score ?? '',
    row.entry_close ?? row.close ?? '',
    row.entry_date ?? '',
    row.latest_close ?? row.close ?? '',
    row.latest_price_date ?? '',
    row.since_entry_pct ?? '',
    row.vol_20d_avg ?? '',
    row.max_gain_60d ?? '',
    row.week_chg_pct ?? '',
    (row.tags || []).join(' / '),
    (row.big_trend_1000 || []).join(' / '),
    (row.big_trend_400 || []).join(' / '),
  ]);
  const csv = [headers, ...rows].map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\r\n');
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' });
  const a = Object.assign(document.createElement('a'), {
    href: URL.createObjectURL(blob),
    download: `big_holder_trend_${dateTW()}.csv`,
  });
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}
