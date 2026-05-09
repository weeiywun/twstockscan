// ═══════════════════════════════════════════════════════════════
//  突破策略：盤整突破 + 動能突破
// ═══════════════════════════════════════════════════════════════
function renderRightTop(strat, main) {
  const rawData = DATA.right_top_data || [];
  const industryStats = DATA.right_top_industry || [];

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
          <div class="coming-icon" style="font-size:28px">▲</div>
          <div class="coming-title">資料尚未生成</div>
          <div class="coming-desc">
            請至 GitHub Actions → <b>每日選股掃描</b> → <b>Run workflow</b><br>
            手動觸發首次掃描，或等待盤後自動執行。
          </div>
        </div>
      </div>`;
    return;
  }

  const rtSortCol = window._rtSortCol || 'quality_score';
  const rtSortAsc = window._rtSortAsc !== undefined ? window._rtSortAsc : false;
  const rtView = window._rtView || 'stock';
  const rtFilter = window._rtFilter || 'all';

  function rtCompare(a, b) {
    const va = a[rtSortCol] != null ? a[rtSortCol] : '';
    const vb = b[rtSortCol] != null ? b[rtSortCol] : '';
    const isDate = /^\d{4}-\d{2}-\d{2}/.test(va) || /^\d{4}-\d{2}-\d{2}/.test(vb);
    const numA = parseFloat(va);
    const numB = parseFloat(vb);
    const cmp = isDate
      ? String(va).localeCompare(String(vb))
      : (!isNaN(numA) && !isNaN(numB))
        ? numA - numB
        : String(va).localeCompare(String(vb));
    return rtSortAsc ? cmp : -cmp;
  }

  function rtSort(col) {
    if (window._rtSortCol === col) window._rtSortAsc = !window._rtSortAsc;
    else { window._rtSortCol = col; window._rtSortAsc = false; }
    renderStrategy();
  }
  window.rtSort = rtSort;

  function setRtView(v) {
    window._rtView = v;
    renderStrategy();
  }
  window.setRtView = setRtView;

  function setRtFilter(v) {
    window._rtFilter = v;
    window._rtSortCol = window._rtSortCol || 'quality_score';
    renderStrategy();
  }
  window.setRtFilter = setRtFilter;

  function sortIcon(col) {
    const isActive = rtSortCol === col;
    return `<span class="sort-icon">${isActive ? (rtSortAsc ? '↑' : '↓') : '·'}</span>`;
  }

  function matchFilter(d) {
    if (rtFilter === 'consolidation') return !!d.is_consolidation_breakout;
    if (rtFilter === 'momentum') return !!d.is_momentum_breakout;
    if (rtFilter === 'dual') return !!d.is_consolidation_breakout && !!d.is_momentum_breakout;
    if (rtFilter === 'whale') return !!d.whale_3w_up || !!d.whale_400_3w_up;
    return true;
  }

  const filtered = rawData.filter(matchFilter);
  const data = filtered.slice().sort(rtCompare);
  const consolidationCount = rawData.filter(d => d.is_consolidation_breakout).length;
  const momentumCount = rawData.filter(d => d.is_momentum_breakout).length;
  const dualCount = rawData.filter(d => d.is_consolidation_breakout && d.is_momentum_breakout).length;
  const whaleCount = rawData.filter(d => d.whale_3w_up || d.whale_400_3w_up).length;
  const topIndustry = industryStats[0];

  function fmtNum(v, digits = 2) {
    return v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(digits);
  }

  function fmtPct(v, digits = 2) {
    return v == null || Number.isNaN(Number(v)) ? '—' : `${v >= 0 ? '+' : ''}${Number(v).toFixed(digits)}%`;
  }

  function tagBadges(tags) {
    // 語意分組：突破類(藍) / 量能類(琥珀) / 籌碼類(青) / 輔助(灰)
    const colorMap = {
      '盤整突破':    '#2563eb',
      '動能突破':    '#2563eb',
      '雙重符合':    '#2563eb',
      '週量強放大':  '#b7791f',
      '日量強放大':  '#b7791f',
      '日線啟動':    '#b7791f',
      '千張大戶連增':'#0f766e',
      '400張同步':   '#0f766e',
      '低乖離':      '#64748b',
    };
    function rgba(hex, a) {
      const r = parseInt(hex.slice(1,3),16), g = parseInt(hex.slice(3,5),16), b = parseInt(hex.slice(5,7),16);
      return `rgba(${r},${g},${b},${a})`;
    }
    return (tags || []).map(t => {
      const c = colorMap[t] || '#64748b';
      return `<span class="tag-badge" style="color:${c};border-color:${rgba(c,.3)};background:${rgba(c,.08)}">${t}</span>`;
    }).join('');
  }

  function exportRtCSV() {
    const headers = [
      '代號', '名稱', '產業', '市場', '訊號類型', '品質分數', '標籤',
      '收盤', '週量比', '週漲幅(%)', '10週前高',
      '日量比', 'MA20乖離(%)', 'MA20', 'MA60', '60日前高',
      '千張大戶連增', '400張同步', '千張3週變化', '400張3週變化', '訊號日'
    ];
    const rows = data.map(d => [
      d.stock_id, d.name, d.industry, d.market,
      (d.signal_types || []).join(' / '),
      d.quality_score ?? '',
      (d.tags || []).join(' / '),
      d.close ?? '',
      d.vol_ratio ?? '',
      d.change_pct ?? '',
      d.high_10w ?? '',
      d.daily_vol_ratio ?? '',
      d.bias_ma20 ?? '',
      d.ma20 ?? '',
      d.ma60 ?? '',
      d.high_60d ?? '',
      d.whale_3w_up ? 'Y' : '',
      d.whale_400_3w_up ? 'Y' : '',
      d.big_1000_chg_3w ?? '',
      d.big_400_chg_3w ?? '',
      d.signal_date ?? d.week_date ?? '',
    ]);
    const csv = [headers, ...rows]
      .map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
      .join('\r\n');
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement('a'), { href: url, download: `breakout_${strat.dataUpdated}.csv` });
    a.click();
    URL.revokeObjectURL(url);
  }
  window.exportRtCSV = exportRtCSV;

  function stockTable() {
    return `
      <div class="table-wrap">
        <div class="table-toolbar">
          <span class="table-title">突破策略標的池</span>
          <div class="toolbar-right">
            <span class="updated-tag">更新：${strat.dataUpdated}</span>
            <button class="btn-csv" onclick="exportRtCSV()">匯出 CSV</button>
          </div>
        </div>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th onclick="rtSort('stock_id')" style="cursor:pointer">代號 / 名稱${sortIcon('stock_id')}</th>
                <th onclick="rtSort('quality_score')" style="cursor:pointer">品質${sortIcon('quality_score')}</th>
                <th onclick="rtSort('industry')" style="cursor:pointer">產業${sortIcon('industry')}</th>
                <th onclick="rtSort('close')" style="cursor:pointer">收盤${sortIcon('close')}</th>
                <th onclick="rtSort('vol_ratio')" style="cursor:pointer" data-tip="最新週量 ÷ 前20週均量">週量比${sortIcon('vol_ratio')}</th>
                <th onclick="rtSort('daily_vol_ratio')" style="cursor:pointer" data-tip="今日量 ÷ 前5日均量">日量比${sortIcon('daily_vol_ratio')}</th>
                <th onclick="rtSort('bias_ma20')" style="cursor:pointer" data-tip="(收盤-MA20)/MA20">MA20乖離${sortIcon('bias_ma20')}</th>
                <th onclick="rtSort('big_1000_chg_3w')" style="cursor:pointer">大戶3週${sortIcon('big_1000_chg_3w')}</th>
                <th>訊號標籤</th>
              </tr>
            </thead>
            <tbody>
              ${data.map(d => {
                const mkt = d.market === 'TPEX' ? 'TPEX' : 'TWSE';
                const tvSymbol = `${mkt}:${d.stock_id}`;
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
                  <td>
                    <span style="font-family:var(--mono);font-size:16px;font-weight:700;color:var(--green)">${d.quality_score ?? '—'}</span>
                  </td>
                  <td><span style="font-size:12px;color:var(--text2)">${d.industry || '—'}</span></td>
                  <td><span class="price-cell">${fmtNum(d.close)}</span></td>
                  <td>
                    <span style="font-family:var(--mono);font-size:13px;font-weight:600;color:${d.is_consolidation_breakout ? 'var(--red)' : 'var(--text3)'}">${d.vol_ratio ? `${fmtNum(d.vol_ratio)}x` : '—'}</span><br>
                    <span style="font-size:10px;color:var(--text3)">${d.vol_20w_avg ? Math.round(d.vol_20w_avg).toLocaleString() + '張均' : '—'}</span>
                  </td>
                  <td>
                    <span style="font-family:var(--mono);font-size:13px;font-weight:600;color:${d.is_momentum_breakout ? 'var(--amber)' : 'var(--text3)'}">${d.daily_vol_ratio ? `${fmtNum(d.daily_vol_ratio)}x` : '—'}</span><br>
                    <span style="font-size:10px;color:var(--text3)">${d.daily_vol_today ? Math.round(d.daily_vol_today).toLocaleString() + '張' : '—'}</span>
                  </td>
                  <td><span class="deviation ${(d.bias_ma20 || 0) >= 0 ? 'pos' : 'neg'}" style="font-size:13px">${fmtPct(d.bias_ma20)}</span></td>
                  <td>
                    <span style="font-family:var(--mono);font-size:12px;color:${d.whale_3w_up ? 'var(--green)' : 'var(--text3)'}">${fmtPct(d.big_1000_chg_3w)}</span><br>
                    <span style="font-size:10px;color:var(--text3)">千張</span>
                  </td>
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
          <span class="table-title">產業分布統計</span>
          <div class="toolbar-right"><span class="updated-tag">共 ${industryStats.length} 個產業</span></div>
        </div>
        <div style="padding:16px;display:flex;flex-direction:column;gap:10px">
          ${industryStats.map((ind, idx) => {
            const barPct = maxCount > 0 ? (ind.count / maxCount * 100).toFixed(1) : 0;
            const rankColor = idx === 0 ? 'var(--green)' : idx === 1 ? 'var(--amber)' : idx === 2 ? 'var(--blue)' : 'var(--text3)';
            return `
              <div style="background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:12px 16px">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
                  <div style="display:flex;align-items:center;gap:10px">
                    <span style="font-size:11px;font-weight:700;font-family:var(--mono);color:${rankColor};min-width:24px">#${idx + 1}</span>
                    <span style="font-weight:600;font-size:14px">${ind.industry}</span>
                    <span style="font-size:12px;color:var(--green);font-weight:600">${ind.count} 檔</span>
                  </div>
                </div>
                <div style="background:var(--bg3);border-radius:4px;height:6px;margin-bottom:8px">
                  <div style="background:${rankColor};width:${barPct}%;height:100%;border-radius:4px;transition:width .3s"></div>
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
          <div class="summary-sub">盤整突破 + 動能突破</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">盤整突破</div>
          <div class="summary-value blue">${consolidationCount}</div>
          <div class="summary-sub">原右上角嚴謹條件</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">動能突破</div>
          <div class="summary-value amber">${momentumCount}</div>
          <div class="summary-sub">日線多頭啟動</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">最強族群</div>
          <div class="summary-value" style="font-size:16px">${topIndustry ? topIndustry.industry : '—'}</div>
          <div class="summary-sub">${topIndustry ? `${topIndustry.count} 檔同步突破` : '尚無資料'} · 大戶 ${whaleCount} 檔</div>
        </div>
      </div>

      <div style="display:flex;gap:8px;padding:0 0 10px 0;flex-wrap:wrap">
        <button class="view-btn ${rtFilter === 'all' ? 'active' : ''}" onclick="setRtFilter('all')">全部</button>
        <button class="view-btn ${rtFilter === 'consolidation' ? 'active' : ''}" onclick="setRtFilter('consolidation')">盤整突破</button>
        <button class="view-btn ${rtFilter === 'momentum' ? 'active' : ''}" onclick="setRtFilter('momentum')">動能突破</button>
        <button class="view-btn ${rtFilter === 'dual' ? 'active' : ''}" onclick="setRtFilter('dual')">雙重符合 ${dualCount}</button>
        <button class="view-btn ${rtFilter === 'whale' ? 'active' : ''}" onclick="setRtFilter('whale')">大戶加持</button>
      </div>

      <div style="display:flex;gap:8px;padding:0 0 12px 0">
        <button class="view-btn ${rtView === 'stock' ? 'active' : ''}" onclick="setRtView('stock')">個股列表</button>
        <button class="view-btn ${rtView === 'industry' ? 'active' : ''}" onclick="setRtView('industry')">產業統計</button>
      </div>

      ${rtView === 'stock' ? stockTable() : industryView()}
    </div>`;
}

function _applyPriceToRightTop(priceMap) {
  if (!priceMap || !DATA.right_top_data) return;
  DATA.right_top_data.forEach(item => {
    const p = priceMap[item.stock_id];
    if (p && p.close != null) item.close = p.close;
  });
}
