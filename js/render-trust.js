// ═══════════════════════════════════════════════════════════════
//  法人動能：投信 / 外資 / 雙法人共振
// ═══════════════════════════════════════════════════════════════
function renderTrustMomentum(strat, main) {
  const activePane = window._imPane || 'trust';
  const paneMeta = {
    trust: {
      label: '投信動能',
      data: DATA.trust_momentum_data || [],
      industry: DATA.trust_momentum_industry || [],
      netLabel: '投信5日',
      csvPrefix: 'trust_momentum',
    },
    foreign: {
      label: '外資動能',
      data: DATA.foreign_momentum_data || [],
      industry: DATA.foreign_momentum_industry || [],
      netLabel: '外資5日',
      csvPrefix: 'foreign_momentum',
    },
    confluence: {
      label: '雙法人共振',
      data: DATA.institutional_confluence_data || [],
      industry: DATA.institutional_confluence_industry || [],
      netLabel: '法人5日',
      csvPrefix: 'institutional_confluence',
    },
  };
  const pane = paneMeta[activePane] || paneMeta.trust;
  const rawData = pane.data;
  const industryStats = pane.industry;

  if (!rawData.length && !DATA.trust_momentum_data?.length && !DATA.foreign_momentum_data?.length) {
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
          <div class="coming-title">法人動能資料尚未生成</div>
          <div class="coming-desc">請至 GitHub Actions → 每日選股掃描 → Run workflow，或等待盤後資料更新。</div>
        </div>
      </div>`;
    return;
  }

  const sortCol = window._imSortCol || 'quality_score';
  const sortAsc = window._imSortAsc !== undefined ? window._imSortAsc : false;
  const view = window._imView || 'stock';
  const filter = window._imFilter || 'all';

  function setImPane(v) { window._imPane = v; window._imFilter = 'all'; renderStrategy(); }
  function setImView(v) { window._imView = v; renderStrategy(); }
  function setImFilter(v) { window._imFilter = v; renderStrategy(); }
  function imSort(col) {
    if (window._imSortCol === col) window._imSortAsc = !window._imSortAsc;
    else { window._imSortCol = col; window._imSortAsc = false; }
    renderStrategy();
  }
  window.setImPane = setImPane;
  window.setImView = setImView;
  window.setImFilter = setImFilter;
  window.imSort = imSort;

  function sortIcon(col) {
    return `<span class="sort-icon">${sortCol === col ? (sortAsc ? '↑' : '↓') : '·'}</span>`;
  }

  function compare(a, b) {
    const va = a[sortCol] != null ? a[sortCol] : '';
    const vb = b[sortCol] != null ? b[sortCol] : '';
    const numA = parseFloat(va);
    const numB = parseFloat(vb);
    const cmp = (!isNaN(numA) && !isNaN(numB))
      ? numA - numB
      : String(va).localeCompare(String(vb));
    return sortAsc ? cmp : -cmp;
  }

  function matchFilter(d) {
    if (filter === 'attack') return d.flow_regime === 'attack' || (d.tags || []).some(t => t.includes('攻擊'));
    if (filter === 'absorption') return d.flow_regime === 'absorption' || (d.tags || []).some(t => t.includes('承接'));
    if (filter === 'high_volume') return (d.inst_vol_ratio_5d || 0) >= 0.2;
    if (filter === 'ema120') return (d.bias_ema120 || 0) > 0;
    if (filter === 'hot') return (d.tags || []).includes('短線過熱');
    return true;
  }

  const filtered = rawData.filter(matchFilter).sort(compare);
  const attackCount = rawData.filter(d => d.flow_regime === 'attack' || (d.tags || []).some(t => t.includes('攻擊'))).length;
  const absorptionCount = rawData.filter(d => d.flow_regime === 'absorption' || (d.tags || []).some(t => t.includes('承接'))).length;
  const highVolCount = rawData.filter(d => (d.inst_vol_ratio_5d || 0) >= 0.2).length;
  const emaCount = rawData.filter(d => (d.bias_ema120 || 0) > 0).length;
  const hotCount = rawData.filter(d => (d.tags || []).includes('短線過熱')).length;
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
      '雙法人共振': { color: '#7c3aed', order: 0 },
      '雙法人攻擊': { color: '#dc2626', order: 0 },
      '投信動能': { color: '#0f766e', order: 0 },
      '外資動能': { color: '#2563eb', order: 0 },
      '投信攻擊': { color: '#dc2626', order: 1 },
      '外資攻擊': { color: '#dc2626', order: 1 },
      '投信承接': { color: '#b7791f', order: 1 },
      '外資承接': { color: '#b7791f', order: 1 },
      '買超占量高': { color: '#dc2626', order: 2 },
      '買超占量增': { color: '#ea7317', order: 2 },
      '站上EMA120': { color: '#0284c7', order: 3 },
      '區間高檔': { color: '#3b82f6', order: 3 },
      '短線過熱': { color: '#9ca3af', order: 4 },
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

  function exportInstitutionalCSV() {
    const headers = [
      '代號', '名稱', '產業', '市場', '品質分數', '分類', '標籤',
      '收盤', 'EMA120', '乖離EMA120(%)', '法人5日買超', '法人10日買超',
      '5日買超天數', '10日買超天數', '買超占量', '5日漲幅(%)', '區間位置(%)', '訊號日'
    ];
    const rows = filtered.map(d => [
      d.stock_id, d.name, d.industry, d.market, d.quality_score ?? '',
      d.flow_regime || '', (d.tags || []).join(' / '), d.close ?? '', d.ema120 ?? '',
      d.bias_ema120 ?? '', d.inst_net_5d ?? '', d.inst_net_10d ?? '',
      d.inst_buy_days_5d ?? '', d.inst_buy_days_10d ?? '', d.inst_vol_ratio_5d ?? '',
      d.price_chg_5d ?? '', d.range_pos_20d ?? '', d.signal_date ?? '',
    ]);
    const csv = [headers, ...rows]
      .map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
      .join('\r\n');
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement('a'), { href: url, download: `${pane.csvPrefix}_${strat.dataUpdated}.csv` });
    a.click();
    URL.revokeObjectURL(url);
  }
  window.exportInstitutionalCSV = exportInstitutionalCSV;

  function paneTabs() {
    return `
      <div style="display:flex;gap:8px;padding:0 0 12px 0;flex-wrap:wrap">
        <button class="view-btn ${activePane === 'trust' ? 'active' : ''}" onclick="setImPane('trust')">投信動能 ${paneMeta.trust.data.length}</button>
        <button class="view-btn ${activePane === 'foreign' ? 'active' : ''}" onclick="setImPane('foreign')">外資動能 ${paneMeta.foreign.data.length}</button>
        <button class="view-btn ${activePane === 'confluence' ? 'active' : ''}" onclick="setImPane('confluence')">雙法人共振 ${paneMeta.confluence.data.length}</button>
      </div>`;
  }

  function stockTable() {
    return `
      <div class="table-wrap">
        <div class="table-toolbar">
          <span class="table-title">${pane.label}標的池</span>
          <div class="toolbar-right">
            <span class="updated-tag">更新：${strat.dataUpdated}</span>
            <button class="btn-csv" onclick="exportInstitutionalCSV()">匯出 CSV</button>
          </div>
        </div>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th onclick="imSort('stock_id')" style="cursor:pointer">代號 / 名稱${sortIcon('stock_id')}</th>
                <th onclick="imSort('quality_score')" style="cursor:pointer">品質${sortIcon('quality_score')}</th>
                <th onclick="imSort('industry')" style="cursor:pointer">產業${sortIcon('industry')}</th>
                <th onclick="imSort('close')" style="cursor:pointer">收盤${sortIcon('close')}</th>
                <th onclick="imSort('bias_ema120')" style="cursor:pointer">EMA120${sortIcon('bias_ema120')}</th>
                <th onclick="imSort('inst_net_5d')" style="cursor:pointer">${pane.netLabel}${sortIcon('inst_net_5d')}</th>
                <th onclick="imSort('inst_buy_days_10d')" style="cursor:pointer">買超天數${sortIcon('inst_buy_days_10d')}</th>
                <th onclick="imSort('inst_vol_ratio_5d')" style="cursor:pointer">買超占量${sortIcon('inst_vol_ratio_5d')}</th>
                <th onclick="imSort('price_chg_5d')" style="cursor:pointer">5日漲幅${sortIcon('price_chg_5d')}</th>
                <th onclick="imSort('range_pos_20d')" style="cursor:pointer">20日位置${sortIcon('range_pos_20d')}</th>
                <th>10日法人</th>
                <th>標籤</th>
              </tr>
            </thead>
            <tbody>
              ${filtered.map(d => {
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
                    <span style="font-family:var(--mono);font-size:12px">${fmtNum(d.ema120)}</span><br>
                    <span class="deviation ${(d.bias_ema120 || 0) >= 0 ? 'pos' : 'neg'}">${fmtPct(d.bias_ema120)}</span>
                  </td>
                  <td>
                    <span style="font-family:var(--mono);font-size:13px;font-weight:700;color:${d.inst_net_5d >= 0 ? 'var(--market-up)' : 'var(--market-down)'}">${fmtLots(d.inst_net_5d)}</span><br>
                    <span style="font-size:10px;color:var(--text3)">10日 ${fmtLots(d.inst_net_10d)}</span>
                  </td>
                  <td>
                    <span style="font-family:var(--mono);font-size:13px;font-weight:700">${d.inst_buy_days_5d || 0}/5</span><br>
                    <span style="font-size:10px;color:var(--text3)">${d.inst_buy_days_10d || 0}/10</span>
                  </td>
                  <td><span style="font-family:var(--mono);font-size:13px;font-weight:700;color:${(d.inst_vol_ratio_5d || 0) >= 0.2 ? 'var(--red)' : 'var(--amber)'}">${fmtPct((d.inst_vol_ratio_5d || 0) * 100, 1)}</span></td>
                  <td><span class="deviation ${(d.price_chg_5d || 0) >= 0 ? 'pos' : 'neg'}">${fmtPct(d.price_chg_5d)}</span></td>
                  <td><span style="font-family:var(--mono);font-size:12px">${fmtPct(d.range_pos_20d, 1)}</span></td>
                  <td>${seriesBars(d.inst_series_10d)}</td>
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
          <span class="table-title">${pane.label}產業分布</span>
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

      ${paneTabs()}

      <div class="summary-row">
        <div class="summary-card">
          <div class="summary-label">${pane.label}</div>
          <div class="summary-value green">${rawData.length}</div>
          <div class="summary-sub">站上 EMA120 且法人買超占量有感</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">攻擊型</div>
          <div class="summary-value blue">${attackCount}</div>
          <div class="summary-sub">買盤與價格同步轉強</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">承接型</div>
          <div class="summary-value amber">${absorptionCount}</div>
          <div class="summary-sub">法人買但價格仍弱</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">最強族群</div>
          <div class="summary-value" style="font-size:16px">${topIndustry ? topIndustry.industry : '—'}</div>
          <div class="summary-sub">${topIndustry ? `${topIndustry.count} 檔` : '尚無資料'} · 占量高 ${highVolCount} 檔</div>
        </div>
      </div>

      <div style="display:flex;gap:8px;padding:0 0 10px 0;flex-wrap:wrap">
        <button class="view-btn ${filter === 'all' ? 'active' : ''}" onclick="setImFilter('all')">全部</button>
        <button class="view-btn ${filter === 'attack' ? 'active' : ''}" onclick="setImFilter('attack')">攻擊 ${attackCount}</button>
        <button class="view-btn ${filter === 'absorption' ? 'active' : ''}" onclick="setImFilter('absorption')">承接 ${absorptionCount}</button>
        <button class="view-btn ${filter === 'high_volume' ? 'active' : ''}" onclick="setImFilter('high_volume')">買超占量高 ${highVolCount}</button>
        <button class="view-btn ${filter === 'ema120' ? 'active' : ''}" onclick="setImFilter('ema120')">站上EMA120 ${emaCount}</button>
        <button class="view-btn ${filter === 'hot' ? 'active' : ''}" onclick="setImFilter('hot')">短線過熱 ${hotCount}</button>
      </div>

      <div style="display:flex;gap:8px;padding:0 0 12px 0">
        <button class="view-btn ${view === 'stock' ? 'active' : ''}" onclick="setImView('stock')">個股列表</button>
        <button class="view-btn ${view === 'industry' ? 'active' : ''}" onclick="setImView('industry')">產業統計</button>
      </div>

      ${view === 'stock' ? stockTable() : industryView()}
    </div>`;
}

function _applyPriceToTrustMomentum(priceMap) {
  if (!priceMap) return;
  [
    DATA.trust_momentum_data,
    DATA.foreign_momentum_data,
    DATA.institutional_confluence_data,
  ].forEach(list => {
    (list || []).forEach(item => {
      const p = priceMap[item.stock_id];
      const close = typeof p === 'number' ? p : p?.close;
      if (close != null) item.close = close;
    });
  });
}
