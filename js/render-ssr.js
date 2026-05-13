// ═══════════════════════════════════════════════════════════════
//  SSR：Strategy Signal Radar
//  彙整籌碼集中 / VCP / 突破策略，找出跨策略共振標的。
// ═══════════════════════════════════════════════════════════════
function buildSSRRows() {
  const rows = new Map();

  function ensure(stockId, seed = {}) {
    const id = String(stockId || '').trim();
    if (!id) return null;
    if (!rows.has(id)) {
      rows.set(id, {
        stock_id: id,
        name: seed.name || '',
        industry: seed.industry || '',
        market: seed.market || guessMarket(id),
        close: seed.close ?? null,
        strategies: [],
        score: 0,
        chips: null,
        vcp: null,
        breakout: null,
        tags: [],
        signal_dates: [],
      });
    }
    const row = rows.get(id);
    row.name = row.name || seed.name || '';
    row.industry = row.industry || seed.industry || '';
    row.market = row.market || seed.market || guessMarket(id);
    if (row.close == null && seed.close != null) row.close = seed.close;
    return row;
  }

  (DATA.chips_big_holder_data || []).forEach(d => {
    const row = ensure(d.stock_id, d);
    if (!row) return;
    row.chips = d;
    row.strategies.push('chips');
    row.score += 35;
    if (d.quality_score != null) row.score += Math.min(Number(d.quality_score) / 10, 10);
    if (d.chg_2w_1000 != null && Number(d.chg_2w_1000) > 0) row.score += 4;
    if (d.chg_2w_400 != null && Number(d.chg_2w_400) > 0) row.score += 3;
    row.tags.push('籌碼集中');
  });

  [...(DATA.vcp_data || []), ...(DATA.vcp_potential_data || [])].forEach(d => {
    const row = ensure(d.stock_id, d);
    if (!row) return;
    row.vcp = d;
    row.strategies.push('vcp');
    row.score += d.vcp_tier === 'vcp' ? 40 : 28;
    if (d.quality_score != null) row.score += Math.min(Number(d.quality_score) / 12, 8);
    if (d.is_near_pivot) row.score += 5;
    if (d.dry_up_ratio != null && d.dry_up_ratio <= 0.8) row.score += 5;
    row.tags.push(d.vcp_tier === 'vcp' ? 'VCP' : '潛在VCP');
  });

  (DATA.right_top_data || []).forEach(d => {
    const row = ensure(d.stock_id, d);
    if (!row) return;
    row.breakout = d;
    row.strategies.push('breakout');
    row.score += 35;
    if (d.quality_score != null) row.score += Math.min(Number(d.quality_score) / 10, 10);
    if (d.is_consolidation_breakout && d.is_momentum_breakout) row.score += 6;
    row.tags.push(...(d.signal_types || d.tags || ['突破策略']).slice(0, 3));
    if (d.signal_date || d.week_date) row.signal_dates.push(d.signal_date || d.week_date);
  });

  return [...rows.values()]
    .map(row => {
      row.strategies = [...new Set(row.strategies)];
      row.strategy_count = row.strategies.length;
      row.tags = [...new Set(row.tags)];
      row.signal_dates = [...new Set(row.signal_dates)].filter(Boolean);
      row.combo_key = [
        row.chips ? '大戶' : null,
        row.vcp ? 'VCP' : null,
        row.breakout ? '突破' : null,
      ].filter(Boolean).join('+');
      row.score = Math.round(row.score);
      return row;
    })
    .filter(row => row.strategy_count >= 2)
    .sort((a, b) => b.strategy_count - a.strategy_count || b.score - a.score);
}

function renderSSR(strat, main) {
  const rows = buildSSRRows();
  const filter = window._ssrFilter || 'c3_2';
  const sortCol = window._ssrSortCol || 'score';
  const sortAsc = window._ssrSortAsc !== undefined ? window._ssrSortAsc : false;

  function setSSRFilter(v) {
    window._ssrFilter = v;
    renderStrategy();
  }
  window.setSSRFilter = setSSRFilter;

  function ssrSort(col) {
    if (window._ssrSortCol === col) window._ssrSortAsc = !window._ssrSortAsc;
    else { window._ssrSortCol = col; window._ssrSortAsc = false; }
    renderStrategy();
  }
  window.ssrSort = ssrSort;

  function matchFilter(row) {
    if (filter === 'triple') return row.strategy_count === 3;
    if (filter === 'chips_vcp') return row.chips && row.vcp;
    if (filter === 'chips_breakout') return row.chips && row.breakout;
    if (filter === 'vcp_breakout') return row.vcp && row.breakout;
    return row.strategy_count >= 2;
  }

  function compare(a, b) {
    const va = sortCol === 'strategy_count' ? a.strategy_count : a[sortCol];
    const vb = sortCol === 'strategy_count' ? b.strategy_count : b[sortCol];
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

  const filtered = rows.filter(matchFilter).sort(compare);
  const tripleCount = rows.filter(r => r.strategy_count === 3).length;
  const chipsVcpCount = rows.filter(r => r.chips && r.vcp).length;
  const chipsBreakoutCount = rows.filter(r => r.chips && r.breakout).length;
  const vcpBreakoutCount = rows.filter(r => r.vcp && r.breakout).length;
  const topIndustry = filtered.reduce((acc, row) => {
    const key = row.industry || '未分類';
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const topIndustryName = Object.entries(topIndustry).sort((a, b) => b[1] - a[1])[0];

  function fmtNum(v, digits = 2) {
    return v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(digits);
  }

  function fmtPct(v, digits = 2) {
    return v == null || Number.isNaN(Number(v)) ? '—' : `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(digits)}%`;
  }

  function strategyBadges(row) {
    const badges = [];
    if (row.chips) badges.push(`<span class="tag-badge" style="color:#d97706;border-color:#d977064d">大戶</span>`);
    if (row.vcp) {
      const isStrict = row.vcp.vcp_tier === 'vcp';
      badges.push(`<span class="tag-badge" style="color:${isStrict ? '#3b82f6' : '#0f766e'};border-color:${isStrict ? '#3b82f64d' : '#0f766e4d'}">${isStrict ? 'VCP' : '潛在VCP'}</span>`);
    }
    if (row.breakout) badges.push(`<span class="tag-badge" style="color:#dc2626;border-color:#dc26264d">突破</span>`);
    return badges.join('');
  }

  function detailText(row) {
    const parts = [];
    if (row.chips) {
      parts.push(`大戶2週：千張 ${fmtPct(row.chips.chg_2w_1000)} / 400張 ${fmtPct(row.chips.chg_2w_400)}`);
    }
    if (row.vcp) {
      const depths = (row.vcp.contraction_depths || []).join('→');
      parts.push(`VCP：${row.vcp.contractions || '—'}段 ${depths ? depths + '%' : ''}，距pivot ${fmtPct(row.vcp.pivot_dist_pct, 1)}`);
    }
    if (row.breakout) {
      const types = (row.breakout.signal_types || []).join('、') || '突破策略';
      parts.push(`突破：${types}`);
    }
    return parts.join('<br>');
  }

  function exportSSRCSV() {
    const headers = [
      '代號', '名稱', '產業', '市場', '共振分數', '命中策略數', '組合',
      '收盤', '大戶千張2週', '大戶400張2週',
      'VCP分級', 'VCP段數', '距Pivot(%)',
      '突破類型', '標籤'
    ];
    const csvRows = filtered.map(row => [
      row.stock_id,
      row.name,
      row.industry || '',
      row.market || '',
      row.score,
      row.strategy_count,
      row.combo_key,
      row.close ?? '',
      row.chips?.chg_2w_1000 ?? '',
      row.chips?.chg_2w_400 ?? '',
      row.vcp ? (row.vcp.vcp_tier === 'vcp' ? 'VCP' : '潛在VCP') : '',
      row.vcp?.contractions ?? '',
      row.vcp?.pivot_dist_pct ?? '',
      row.breakout ? ((row.breakout.signal_types || []).join(' / ') || '突破策略') : '',
      row.tags.join(' / '),
    ]);
    const csv = [headers, ...csvRows]
      .map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
      .join('\r\n');
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement('a'), { href: url, download: `ssr_${strat.dataUpdated}.csv` });
    a.click();
    URL.revokeObjectURL(url);
  }
  window.exportSSRCSV = exportSSRCSV;

  const emptyHTML = `
    <div class="coming-soon" style="padding:48px 20px">
      <div class="coming-icon" style="font-size:28px">✦</div>
      <div class="coming-title">目前沒有交集標的</div>
      <div class="coming-desc">三組策略同時命中的機率本來就低；等盤後資料更新後，這裡會自動彙整 C3 取 2 與三策略全中的標的。</div>
    </div>`;

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
          <div class="summary-label">C3 取 2</div>
          <div class="summary-value blue">${rows.length}</div>
          <div class="summary-sub">任兩組以上同時命中</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">三策略全中</div>
          <div class="summary-value green">${tripleCount}</div>
          <div class="summary-sub">大戶 + VCP + 突破</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">大戶 + VCP</div>
          <div class="summary-value" style="color:var(--amber)">${chipsVcpCount}</div>
          <div class="summary-sub">籌碼先行搭配型態收斂</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">目前分頁</div>
          <div class="summary-value" style="font-size:16px">${filtered.length}</div>
          <div class="summary-sub">${topIndustryName ? `${topIndustryName[0]} ${topIndustryName[1]} 檔` : '尚無產業聚集'}</div>
        </div>
      </div>

      <div style="display:flex;gap:8px;padding:0 0 10px 0;flex-wrap:wrap">
        <button class="view-btn ${filter === 'c3_2' ? 'active' : ''}" onclick="setSSRFilter('c3_2')">C3取2 ${rows.length}</button>
        <button class="view-btn ${filter === 'triple' ? 'active' : ''}" onclick="setSSRFilter('triple')">三策略全中 ${tripleCount}</button>
        <button class="view-btn ${filter === 'chips_vcp' ? 'active' : ''}" onclick="setSSRFilter('chips_vcp')">大戶+VCP ${chipsVcpCount}</button>
        <button class="view-btn ${filter === 'chips_breakout' ? 'active' : ''}" onclick="setSSRFilter('chips_breakout')">大戶+突破 ${chipsBreakoutCount}</button>
        <button class="view-btn ${filter === 'vcp_breakout' ? 'active' : ''}" onclick="setSSRFilter('vcp_breakout')">VCP+突破 ${vcpBreakoutCount}</button>
      </div>

      ${filtered.length === 0 ? emptyHTML : `
        <div class="table-wrap">
          <div class="table-toolbar">
            <span class="table-title">SSR 共振標的池</span>
            <div class="toolbar-right">
              <span class="updated-tag">更新：${strat.dataUpdated}</span>
              <button class="btn-csv" onclick="exportSSRCSV()">匯出 CSV</button>
            </div>
          </div>
          <div class="table-scroll">
            <table>
              <thead>
                <tr>
                  <th onclick="ssrSort('stock_id')" style="cursor:pointer">代號 / 名稱${sortIcon('stock_id')}</th>
                  <th onclick="ssrSort('score')" style="cursor:pointer">共振${sortIcon('score')}</th>
                  <th onclick="ssrSort('strategy_count')" style="cursor:pointer">命中${sortIcon('strategy_count')}</th>
                  <th onclick="ssrSort('industry')" style="cursor:pointer">產業${sortIcon('industry')}</th>
                  <th onclick="ssrSort('close')" style="cursor:pointer">收盤${sortIcon('close')}</th>
                  <th>策略組合</th>
                  <th>關鍵訊號</th>
                </tr>
              </thead>
              <tbody>
                ${filtered.map(row => {
                  const tvSymbol = getTVSymbol(row);
                  return `<tr>
                    <td>
                      <a href="https://www.tradingview.com/chart/?symbol=${tvSymbol}"
                         onclick="openTV('${tvSymbol}', event)" style="text-decoration:none;display:inline-block">
                        <div class="stock-code" style="display:flex;align-items:center;gap:5px">
                          ${row.stock_id}<span style="font-size:9px;opacity:.45;font-family:var(--mono)">↗</span>
                        </div>
                        <div class="stock-name">${row.name || '—'}</div>
                      </a>
                      <div class="stock-industry" style="font-size:10px;color:var(--text3)">${row.market || '—'}</div>
                    </td>
                    <td><span style="font-family:var(--mono);font-size:16px;font-weight:700;color:${row.strategy_count === 3 ? 'var(--green)' : 'var(--blue)'}">${row.score}</span></td>
                    <td><span style="font-family:var(--mono);font-weight:700">${row.strategy_count}/3</span></td>
                    <td><span style="font-size:12px;color:var(--text2)">${row.industry || '—'}</span></td>
                    <td><span class="price-cell">${fmtNum(row.close)}</span></td>
                    <td><div class="tag-cell">${strategyBadges(row)}</div></td>
                    <td><div style="font-size:11px;line-height:1.65;color:var(--text2)">${detailText(row)}</div></td>
                  </tr>`;
                }).join('')}
              </tbody>
            </table>
          </div>
        </div>`}
    </div>`;
}
