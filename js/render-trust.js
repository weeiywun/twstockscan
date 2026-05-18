// ═══════════════════════════════════════════════════════════════
//  投信動能：追蹤投信連買與買超占量
// ═══════════════════════════════════════════════════════════════
function renderTrustMomentum(strat, main) {
  const rawData = DATA.trust_momentum_data || [];
  const industryStats = DATA.trust_momentum_industry || [];

  if (rawData.length === 0) {
    main.innerHTML = `
      <div class="strategy-panel active">
        <div class="strat-header">
          <div class="strat-title">${strat.icon} ${strat.name}</div>
          <div class="strat-desc">${strat.description}</div>
        </div>
        <div class="conditions">
          ${strat.conditions.map(c => `<div class="cond"><span class="cond-dot"></span>${c}</div>`).join('')}
        </div>
        <div class="coming-soon" style="padding:48px 20px">
          <div class="coming-icon" style="font-size:28px">◆</div>
          <div class="coming-title">投信動能資料尚未生成</div>
          <div class="coming-desc">
            請至 GitHub Actions → <b>每日選股掃描</b> → <b>Run workflow</b><br>
            或等待盤後資料更新後自動產生。
          </div>
        </div>
      </div>`;
    return;
  }

  const tmSortCol = window._tmSortCol || 'quality_score';
  const tmSortAsc = window._tmSortAsc !== undefined ? window._tmSortAsc : false;
  const tmView = window._tmView || 'stock';
  const tmFilter = window._tmFilter || 'all';

  function tmCompare(a, b) {
    const va = a[tmSortCol] != null ? a[tmSortCol] : '';
    const vb = b[tmSortCol] != null ? b[tmSortCol] : '';
    const numA = parseFloat(va);
    const numB = parseFloat(vb);
    const cmp = (!isNaN(numA) && !isNaN(numB))
      ? numA - numB
      : String(va).localeCompare(String(vb));
    return tmSortAsc ? cmp : -cmp;
  }

  function tmSort(col) {
    if (window._tmSortCol === col) window._tmSortAsc = !window._tmSortAsc;
    else { window._tmSortCol = col; window._tmSortAsc = false; }
    renderStrategy();
  }
  window.tmSort = tmSort;

  function setTmView(v) { window._tmView = v; renderStrategy(); }
  window.setTmView = setTmView;

  function setTmFilter(v) { window._tmFilter = v; renderStrategy(); }
  window.setTmFilter = setTmFilter;

  function sortIcon(col) {
    return `<span class="sort-icon">${tmSortCol === col ? (tmSortAsc ? '↑' : '↓') : '·'}</span>`;
  }

  function matchFilter(d) {
    if (tmFilter === 'strong') return d.trust_buy_days_10d >= 8;
    if (tmFilter === 'volume') return d.trust_vol_ratio_5d >= 0.2;
    if (tmFilter === 'new_high') return !!d.is_new_20d_high;
    if (tmFilter === 'low_bias') return d.bias_ma20 != null && d.bias_ma20 <= 10;
    return true;
  }

  const filtered = rawData.filter(matchFilter);
  const data = filtered.slice().sort(tmCompare);
  const strongCount = rawData.filter(d => d.trust_buy_days_10d >= 8).length;
  const volumeCount = rawData.filter(d => d.trust_vol_ratio_5d >= 0.2).length;
  const highCount = rawData.filter(d => d.is_new_20d_high).length;
  const lowBiasCount = rawData.filter(d => d.bias_ma20 != null && d.bias_ma20 <= 10).length;
  const topIndustry = industryStats[0];

  function fmtNum(v, digits = 2) {
    return v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(digits);
  }

  function fmtPct(v, digits = 2) {
    return v == null || Number.isNaN(Number(v)) ? '—' : `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(digits)}%`;
  }

  function fmtLots(v) {
    return v == null || Number.isNaN(Number(v)) ? '—' : Math.round(Number(v)).toLocaleString();
  }

  function tagBadges(tags) {
    const meta = {
      '投信動能':   { color: '#0f766e', order: 0 },
      '投信強連買': { color: '#dc2626', order: 0 },
      '投信連買':   { color: '#ea7317', order: 0 },
      '買超占量高': { color: '#dc2626', order: 1 },
      '買超占量增': { color: '#ea7317', order: 1 },
      '20日新高':   { color: '#3b82f6', order: 2 },
      '低乖離':     { color: '#64748b', order: 3 },
      '短線偏熱':   { color: '#9ca3af', order: 4 },
    };
    return (tags || [])
      .slice()
      .sort((a, b) => (meta[a]?.order ?? 9) - (meta[b]?.order ?? 9))
      .map(t => {
        const c = meta[t]?.color || '#9ca3af';
        return `<span class="tag-badge" style="color:${c};border-color:${c}4d">${t}</span>`;
      }).join('');
  }

  function seriesBars(series) {
    const vals = (series || []).map(x => Number(x.net || 0));
    const maxAbs = Math.max(...vals.map(v => Math.abs(v)), 1);
    return `<div style="display:flex;align-items:flex-end;gap:2px;height:28px;min-width:68px">
      ${vals.map(v => {
        const h = Math.max(Math.round(Math.abs(v) / maxAbs * 24), 2);
        const c = v >= 0 ? 'var(--market-up)' : 'var(--market-down)';
        return `<span title="${fmtLots(v)}張" style="width:5px;height:${h}px;background:${c};opacity:.85;border-radius:2px"></span>`;
      }).join('')}
    </div>`;
  }

  function exportTrustCSV() {
    const headers = [
      '代號', '名稱', '產業', '市場', '品質分數', '標籤',
      '收盤', '投信5日買超', '投信10日買超', '5日買超天數', '10日買超天數',
      '買超占20日均量', '5日漲幅(%)', 'MA20乖離(%)', '20日新高', '訊號日'
    ];
    const rows = data.map(d => [
      d.stock_id, d.name, d.industry, d.market,
      d.quality_score ?? '',
      (d.tags || []).join(' / '),
      d.close ?? '',
      d.trust_net_5d ?? '',
      d.trust_net_10d ?? '',
      d.trust_buy_days_5d ?? '',
      d.trust_buy_days_10d ?? '',
      d.trust_vol_ratio_5d ?? '',
      d.price_chg_5d ?? '',
      d.bias_ma20 ?? '',
      d.is_new_20d_high ? 'Y' : '',
      d.signal_date ?? '',
    ]);
    const csv = [headers, ...rows]
      .map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
      .join('\r\n');
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement('a'), { href: url, download: `trust_momentum_${strat.dataUpdated}.csv` });
    a.click();
    URL.revokeObjectURL(url);
  }
  window.exportTrustCSV = exportTrustCSV;

  function stockTable() {
    return `
      <div class="table-wrap">
        <div class="table-toolbar">
          <span class="table-title">投信動能標的池</span>
          <div class="toolbar-right">
            <span class="updated-tag">更新：${strat.dataUpdated}</span>
            <button class="btn-csv" onclick="exportTrustCSV()">匯出 CSV</button>
          </div>
        </div>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th onclick="tmSort('stock_id')" style="cursor:pointer">代號 / 名稱${sortIcon('stock_id')}</th>
                <th onclick="tmSort('quality_score')" style="cursor:pointer">品質${sortIcon('quality_score')}</th>
                <th onclick="tmSort('industry')" style="cursor:pointer">產業${sortIcon('industry')}</th>
                <th onclick="tmSort('close')" style="cursor:pointer">收盤${sortIcon('close')}</th>
                <th onclick="tmSort('trust_net_5d')" style="cursor:pointer">投信5日${sortIcon('trust_net_5d')}</th>
                <th onclick="tmSort('trust_buy_days_10d')" style="cursor:pointer">連買${sortIcon('trust_buy_days_10d')}</th>
                <th onclick="tmSort('trust_vol_ratio_5d')" style="cursor:pointer" data-tip="投信近5日買超張數 / 近20日均量 × 5">買超占量${sortIcon('trust_vol_ratio_5d')}</th>
                <th onclick="tmSort('price_chg_5d')" style="cursor:pointer">5日漲幅${sortIcon('price_chg_5d')}</th>
                <th onclick="tmSort('bias_ma20')" style="cursor:pointer">MA20乖離${sortIcon('bias_ma20')}</th>
                <th>10日投信</th>
                <th>標籤</th>
              </tr>
            </thead>
            <tbody>
              ${data.map(d => {
                const tvSymbol = getTVSymbol(d);
                return `<tr>
                  <td>
                    <a href="https://www.tradingview.com/chart/?symbol=${tvSymbol}"
                       onclick="openTV('${tvSymbol}', event)" style="text-decoration:none;display:inline-block">
                      <div class="stock-code" style="display:flex;align-items:center;gap:5px">
                        ${d.stock_id}<span style="font-size:9px;opacity:.45;font-family:var(--mono)">↗</span>
                      </div>
                      <div class="stock-name">${d.name}</div>
                    </a>
                    <div class="stock-industry" style="font-size:10px;color:var(--text3)">${d.market || '—'}</div>
                  </td>
                  <td><span style="font-family:var(--mono);font-size:16px;font-weight:700;color:var(--green)">${d.quality_score ?? '—'}</span></td>
                  <td><span style="font-size:12px;color:var(--text2)">${d.industry || '—'}</span></td>
                  <td><span class="price-cell">${fmtNum(d.close)}</span></td>
                  <td>
                    <span style="font-family:var(--mono);font-size:13px;font-weight:700;color:${d.trust_net_5d >= 0 ? 'var(--market-up)' : 'var(--market-down)'}">${fmtLots(d.trust_net_5d)}</span><br>
                    <span style="font-size:10px;color:var(--text3)">10日 ${fmtLots(d.trust_net_10d)}</span>
                  </td>
                  <td>
                    <span style="font-family:var(--mono);font-size:13px;font-weight:700">${d.trust_buy_days_5d}/5</span><br>
                    <span style="font-size:10px;color:var(--text3)">${d.trust_buy_days_10d}/10</span>
                  </td>
                  <td><span style="font-family:var(--mono);font-size:13px;font-weight:700;color:${d.trust_vol_ratio_5d >= 0.2 ? 'var(--red)' : 'var(--amber)'}">${fmtPct(d.trust_vol_ratio_5d * 100, 1)}</span></td>
                  <td><span class="deviation ${(d.price_chg_5d || 0) >= 0 ? 'pos' : 'neg'}">${fmtPct(d.price_chg_5d)}</span></td>
                  <td><span class="deviation ${(d.bias_ma20 || 0) >= 0 ? 'pos' : 'neg'}">${fmtPct(d.bias_ma20)}</span></td>
                  <td>${seriesBars(d.trust_series_10d)}</td>
                  <td><div class="tag-cell">${tagBadges(d.tags)}</div></td>
                </tr>`;
              }).join('')}
            </tbody>
          </table>
        </div>
      </div>`;
  }

  function industryView() {
    if (industryStats.length === 0) {
      return `<div style="padding:48px 20px;text-align:center;color:var(--text3)">尚無產業統計資料</div>`;
    }
    const maxCount = industryStats[0].count;
    return `
      <div class="table-wrap">
        <div class="table-toolbar">
          <span class="table-title">投信動能產業分布</span>
          <div class="toolbar-right"><span class="updated-tag">共 ${industryStats.length} 個產業</span></div>
        </div>
        <div style="padding:16px;display:flex;flex-direction:column;gap:10px">
          ${industryStats.map((ind, idx) => {
            const barPct = maxCount > 0 ? (ind.count / maxCount * 100).toFixed(1) : 0;
            const rankColor = idx === 0 ? 'var(--green)' : idx === 1 ? 'var(--amber)' : idx === 2 ? 'var(--blue)' : 'var(--text3)';
            return `
              <div style="background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:12px 16px">
                <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
                  <span style="font-size:11px;font-weight:700;font-family:var(--mono);color:${rankColor};min-width:24px">#${idx + 1}</span>
                  <span style="font-weight:600;font-size:14px">${ind.industry}</span>
                  <span style="font-size:12px;color:var(--green);font-weight:600">${ind.count} 檔</span>
                </div>
                <div style="background:var(--bg3);border-radius:4px;height:6px;margin-bottom:8px">
                  <div style="background:${rankColor};width:${barPct}%;height:100%;border-radius:4px"></div>
                </div>
                <div style="display:flex;flex-wrap:wrap;gap:4px">
                  ${ind.stocks.map(s => `
                    <span style="background:var(--bg3);border:1px solid var(--border);border-radius:4px;
                                 padding:2px 7px;font-size:11px;font-family:var(--mono);cursor:pointer;color:var(--text2)"
                          onclick="openTV('${s.stock_id}', event)" title="${s.name}">
                      ${s.stock_id} ${s.name}
                    </span>`).join('')}
                </div>
              </div>`;
          }).join('')}
        </div>
      </div>`;
  }

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
          <div class="summary-label">全部命中</div>
          <div class="summary-value green">${rawData.length}</div>
          <div class="summary-sub">投信連買且買超占量有感</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">強連買</div>
          <div class="summary-value blue">${strongCount}</div>
          <div class="summary-sub">近10日買超 ≥ 8 日</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">買超占量高</div>
          <div class="summary-value amber">${volumeCount}</div>
          <div class="summary-sub">近5日買超占 20日均量 ≥ 20%</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">最強族群</div>
          <div class="summary-value" style="font-size:16px">${topIndustry ? topIndustry.industry : '—'}</div>
          <div class="summary-sub">${topIndustry ? `${topIndustry.count} 檔` : '尚無資料'} · 20日新高 ${highCount} 檔</div>
        </div>
      </div>

      <div style="display:flex;gap:8px;padding:0 0 10px 0;flex-wrap:wrap">
        <button class="view-btn ${tmFilter === 'all' ? 'active' : ''}" onclick="setTmFilter('all')">全部</button>
        <button class="view-btn ${tmFilter === 'strong' ? 'active' : ''}" onclick="setTmFilter('strong')">強連買 ${strongCount}</button>
        <button class="view-btn ${tmFilter === 'volume' ? 'active' : ''}" onclick="setTmFilter('volume')">買超占量高 ${volumeCount}</button>
        <button class="view-btn ${tmFilter === 'new_high' ? 'active' : ''}" onclick="setTmFilter('new_high')">20日新高 ${highCount}</button>
        <button class="view-btn ${tmFilter === 'low_bias' ? 'active' : ''}" onclick="setTmFilter('low_bias')">低乖離 ${lowBiasCount}</button>
      </div>

      <div style="display:flex;gap:8px;padding:0 0 12px 0">
        <button class="view-btn ${tmView === 'stock' ? 'active' : ''}" onclick="setTmView('stock')">個股列表</button>
        <button class="view-btn ${tmView === 'industry' ? 'active' : ''}" onclick="setTmView('industry')">產業統計</button>
      </div>

      ${tmView === 'stock' ? stockTable() : industryView()}
    </div>`;
}

function _applyPriceToTrustMomentum(priceMap) {
  if (!priceMap || !DATA.trust_momentum_data) return;
  DATA.trust_momentum_data.forEach(item => {
    const p = priceMap[item.stock_id];
    const close = typeof p === 'number' ? p : p?.close;
    if (close != null) item.close = close;
  });
}
