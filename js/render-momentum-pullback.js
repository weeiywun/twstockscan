let momentumPullbackSortCol = 'score';
let momentumPullbackSortAsc = false;
let momentumPullbackZoneFilter = 'all';

function renderMomentumPullback(strat, main) {
  const model = DATA.momentum_pullback_data || {};
  const rawRows = model.results || [];

  if (!rawRows.length) {
    main.innerHTML = `<div class="strategy-panel active">
      <div class="strat-header">
        <div class="strat-title">${strat.icon} ${strat.name}</div>
        <div class="strat-desc">${strat.description}</div>
      </div>
      <div class="coming-soon" style="padding:56px 20px">
        <div class="coming-icon">${strat.icon}</div>
        <div class="coming-title">目前沒有動能回測候選</div>
        <div class="coming-desc">模型只顯示已轉強後回測到 Fib / 均線共振區，且風險距離可控的標的。</div>
      </div>
    </div>`;
    return;
  }

  function sortValue(row, col) {
    if (col === 'score') return row.unified_score ?? row.score;
    if (col === 'ma_confluence') return Math.abs(Number(row.ma_distance_pct ?? 999));
    if (col === 'fib_zone') return { '23.6%-38.2%': 1, '38.2%-50%': 2, '50%-61.8%': 3 }[row.fib_zone] || 9;
    return row[col];
  }

  function compareRows(a, b, col, asc) {
    const va = sortValue(a, col);
    const vb = sortValue(b, col);
    const na = Number(va);
    const nb = Number(vb);
    const cmp = !Number.isNaN(na) && !Number.isNaN(nb)
      ? na - nb
      : String(va ?? '').localeCompare(String(vb ?? ''));
    return asc ? cmp : -cmp;
  }

  const filteredRows = momentumPullbackZoneFilter === 'all'
    ? rawRows.slice()
    : rawRows.filter(row => row.fib_zone === momentumPullbackZoneFilter);
  const rowsData = filteredRows.sort((a, b) => compareRows(a, b, momentumPullbackSortCol, momentumPullbackSortAsc));
  const sortIcon = col => `<span class="sort-icon">${momentumPullbackSortCol === col ? (momentumPullbackSortAsc ? '↑' : '↓') : '·'}</span>`;
  const fmt = (v, digits = 1) => v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(digits);
  const fmtPct = (v, digits = 1) => v == null || Number.isNaN(Number(v)) ? '—' : `${Number(v) > 0 ? '+' : ''}${Number(v).toFixed(digits)}%`;
  const countByZone = zone => rawRows.filter(row => row.fib_zone === zone).length;
  const zoneColor = zone => ({
    '23.6%-38.2%': 'var(--green)',
    '38.2%-50%': 'var(--amber)',
    '50%-61.8%': 'var(--red)',
  }[zone] || 'var(--text2)');
  const zoneButton = (zone, label) => {
    const count = zone === 'all' ? rawRows.length : countByZone(zone);
    if (zone !== 'all' && count === 0) return '';
    const active = momentumPullbackZoneFilter === zone;
    const activeStyle = active
      ? 'background:var(--green);border-color:var(--green);color:#fff'
      : 'background:var(--bg);border-color:var(--border);color:var(--text2)';
    return `<button onclick="setMomentumPullbackZoneFilter('${zone}')" style="${activeStyle};border-width:1px;border-style:solid;border-radius:6px;padding:6px 10px;font-size:12px;cursor:pointer">${label} ${count}</button>`;
  };

  const body = rowsData.map((row, idx) => {
    const tvSym = getTVSymbol(row);
    const maText = `${row.ma_confluence || '—'} ${fmtPct(row.ma_distance_pct, 1)}`;
    const volText = row.volume_cooldown_pct != null ? `量縮 ${fmt(row.volume_cooldown_pct, 0)}%` : '—';
    const riskColor = Number(row.risk_to_support_pct || 0) <= 5 ? 'var(--green)' : (Number(row.risk_to_support_pct || 0) <= 8 ? 'var(--amber)' : 'var(--red)');
    return `<tr onclick="toggleExpand('mpb-${row.stock_id}')" id="row-mpb-${row.stock_id}">
      <td style="font-family:var(--mono);font-size:12px;color:var(--text3)">${idx + 1}</td>
      <td>
        <a href="https://www.tradingview.com/chart/?symbol=${tvSym}"
          onclick="openTV('${tvSym}', event)"
          style="text-decoration:none;display:inline-block">
          <div class="stock-code" style="display:flex;align-items:center;gap:5px">
            ${row.stock_id}<span style="font-size:9px;opacity:.45;font-family:var(--mono)">↗</span>
          </div>
          <div class="stock-name">${row.name || ''}</div>
        </a>
        <div class="stock-industry">${row.industry || (row.sources || []).join(' / ')}</div>
      </td>
      <td>
        <span style="font-family:var(--mono);font-weight:700;color:var(--green)">${fmt(row.unified_score ?? row.score, 1)}</span>
        <span style="font-size:10px;color:var(--text3);margin-left:4px">${row.unified_score_grade || ''}</span>
      </td>
      <td><span style="font-family:var(--mono);font-size:12px;font-weight:700">${fmt(row.close, 1)}</span></td>
      <td><span style="font-family:var(--mono);font-size:12px;color:var(--text)">${Number(row.volume_lots || 0).toLocaleString()} 張</span></td>
      <td><span style="font-family:var(--mono);font-size:12px;color:var(--text2)">${Number(row.vol20 || 0).toLocaleString()} 張</span></td>
      <td>
        <span class="tag-badge" style="color:${zoneColor(row.fib_zone)};border-color:rgba(80,90,110,.35)">${row.fib_zone || '—'}</span><br>
        <span style="font-size:11px;color:var(--text3)">回落 ${fmt(row.pullback_from_high_pct, 1)}%</span>
      </td>
      <td>
        <span style="font-family:var(--mono);font-size:12px">${maText}</span>
      </td>
      <td>
        <span style="font-family:var(--mono);font-size:12px;color:var(--text2)">${volText}</span><br>
        <span style="font-size:11px;color:var(--text3)">點火 ${Number(row.attack_volume_lots || 0).toLocaleString()} 張</span>
      </td>
      <td><span class="tag-badge" style="color:var(--text);border-color:rgba(80,90,110,.35)">${row.reversal_signal || '等待轉強'}</span></td>
      <td>
        <span style="font-family:var(--mono);font-size:12px;color:${riskColor}">${row.defense_label || '—'} ${fmt(row.defense_price, 1)}</span><br>
        <span style="font-size:11px;color:var(--text3)">風險 ${fmt(row.risk_to_support_pct, 1)}% / 前高 ${fmt(row.upside_to_high_pct, 1)}%</span>
      </td>
    </tr>
    <tr class="expand-row" id="expand-mpb-${row.stock_id}" style="display:none">
      <td colspan="11">
        <div class="expand-content">
          <div class="expand-section" style="flex:1;min-width:190px">
            <h4>推升波</h4>
            <div style="font-size:12px;color:var(--text2);line-height:1.9">
              <div>低點：<b>${row.swing_low_date || '—'} / ${fmt(row.swing_low, 1)}</b></div>
              <div>高點：<b>${row.swing_high_date || '—'} / ${fmt(row.swing_high, 1)}</b></div>
              <div>波段漲幅：<b>${fmt(row.advance_pct, 1)}%</b></div>
              <div>距高點：<b>${row.high_age_days ?? '—'} 個交易日</b></div>
            </div>
          </div>
          <div class="expand-section" style="flex:1;min-width:190px">
            <h4>Fib 支撐</h4>
            <div style="font-size:12px;color:var(--text2);line-height:1.9">
              <div>23.6%：<b>${fmt(row.fib_levels?.['23.6'], 1)}</b></div>
              <div>38.2%：<b>${fmt(row.fib_levels?.['38.2'], 1)}</b></div>
              <div>50%：<b>${fmt(row.fib_levels?.['50'], 1)}</b></div>
              <div>61.8%：<b>${fmt(row.fib_levels?.['61.8'], 1)}</b></div>
            </div>
          </div>
          <div class="expand-section" style="flex:1.4;min-width:220px">
            <h4>均線 / 來源</h4>
            <div style="font-size:12px;color:var(--text2);line-height:1.9">
              <div>EMA5 / 20 / 60：<b>${fmt(row.ema5, 1)} / ${fmt(row.ema20, 1)} / ${fmt(row.ema60, 1)}</b></div>
              <div>來源：<b>${(row.sources || []).join(' / ') || '全市場價格模型'}</b></div>
              <div>標籤：<b>${(row.tags || []).join(' / ') || '—'}</b></div>
            </div>
          </div>
        </div>
      </td>
    </tr>`;
  }).join('');

  main.innerHTML = `<div class="strategy-panel active">
    <div class="strat-header">
      <div class="strat-title">${strat.icon} ${strat.name}</div>
      <div class="strat-desc">${strat.description}</div>
    </div>
    <div class="conditions">
      ${strat.conditions.map(c => `<div class="cond"><span class="cond-dot"></span>${c}</div>`).join('')}
    </div>
    <div class="summary-row">
      <div class="summary-card">
        <div class="summary-label">候選</div>
        <div class="summary-value green">${rawRows.length}</div>
        <div class="summary-sub">只列動能回測</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">強勢區</div>
        <div class="summary-value green">${countByZone('23.6%-38.2%')}</div>
        <div class="summary-sub">Fib 23.6%-38.2%</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">健康區</div>
        <div class="summary-value amber">${countByZone('38.2%-50%')}</div>
        <div class="summary-sub">Fib 38.2%-50%</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">資料日</div>
        <div class="summary-value" style="font-size:16px;font-family:var(--mono)">${model.source_date || strat.dataUpdated}</div>
        <div class="summary-sub">price_cache</div>
      </div>
    </div>
    <div class="table-wrap">
      <div class="table-toolbar">
        <span class="table-title">動能回測候選</span>
        <div class="toolbar-right"><span class="updated-tag">顯示：${rowsData.length} / ${rawRows.length}</span><span class="updated-tag">更新：${strat.dataUpdated}</span></div>
      </div>
      <div class="sub-filter-row" style="padding:10px 14px;border-bottom:1px solid var(--border);display:flex;gap:8px;flex-wrap:wrap">
        ${zoneButton('all', '全部')}
        ${zoneButton('23.6%-38.2%', '強勢回測')}
        ${zoneButton('38.2%-50%', '健康回測')}
        ${zoneButton('50%-61.8%', '深回測')}
      </div>
      <div class="table-scroll ${rowsData.length > 10 ? 'table-vscroll' : ''}">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th onclick="momentumPullbackSort('stock_id')" style="cursor:pointer">代號 / 名稱${sortIcon('stock_id')}</th>
              <th onclick="momentumPullbackSort('score')" style="cursor:pointer">分數${sortIcon('score')}</th>
              <th onclick="momentumPullbackSort('close')" style="cursor:pointer">收盤${sortIcon('close')}</th>
              <th onclick="momentumPullbackSort('volume_lots')" style="cursor:pointer">成交量${sortIcon('volume_lots')}</th>
              <th onclick="momentumPullbackSort('vol20')" style="cursor:pointer">20日均量${sortIcon('vol20')}</th>
              <th onclick="momentumPullbackSort('fib_zone')" style="cursor:pointer">回測區${sortIcon('fib_zone')}</th>
              <th onclick="momentumPullbackSort('ma_confluence')" style="cursor:pointer">均線共振${sortIcon('ma_confluence')}</th>
              <th onclick="momentumPullbackSort('volume_cooldown_pct')" style="cursor:pointer">回測量能${sortIcon('volume_cooldown_pct')}</th>
              <th>轉強</th>
              <th onclick="momentumPullbackSort('risk_to_support_pct')" style="cursor:pointer">防守${sortIcon('risk_to_support_pct')}</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    </div>
  </div>`;
}

function momentumPullbackSort(col) {
  if (momentumPullbackSortCol === col) momentumPullbackSortAsc = !momentumPullbackSortAsc;
  else { momentumPullbackSortCol = col; momentumPullbackSortAsc = col === 'risk_to_support_pct' || col === 'ma_confluence'; }
  renderStrategy();
}

function setMomentumPullbackZoneFilter(zone) {
  momentumPullbackZoneFilter = zone;
  renderStrategy();
}
