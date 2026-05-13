// ═══════════════════════════════════════════════════════════════
//  VCP 選股策略：Volatility Contraction Pattern
// ═══════════════════════════════════════════════════════════════
function renderVCP(strat, main) {
  const rawData = DATA.vcp_data || [];
  const industryStats = DATA.vcp_industry || [];

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
          <div class="coming-icon" style="font-size:28px">◈</div>
          <div class="coming-title">資料尚未生成</div>
          <div class="coming-desc">
            請至 GitHub Actions → <b>每日選股掃描</b> → <b>Run workflow</b><br>
            手動觸發首次掃描，或等待盤後自動執行。
          </div>
        </div>
      </div>`;
    return;
  }

  const vcpSortCol = window._vcpSortCol || 'quality_score';
  const vcpSortAsc = window._vcpSortAsc !== undefined ? window._vcpSortAsc : false;
  const vcpView   = window._vcpView   || 'stock';
  const vcpFilter = window._vcpFilter || 'all';

  function vcpCompare(a, b) {
    const va = a[vcpSortCol] != null ? a[vcpSortCol] : '';
    const vb = b[vcpSortCol] != null ? b[vcpSortCol] : '';
    const numA = parseFloat(va), numB = parseFloat(vb);
    const cmp = (!isNaN(numA) && !isNaN(numB)) ? numA - numB : String(va).localeCompare(String(vb));
    return vcpSortAsc ? cmp : -cmp;
  }

  function vcpSort(col) {
    if (window._vcpSortCol === col) window._vcpSortAsc = !window._vcpSortAsc;
    else { window._vcpSortCol = col; window._vcpSortAsc = false; }
    renderStrategy();
  }
  window.vcpSort = vcpSort;

  function setVcpView(v) { window._vcpView = v; renderStrategy(); }
  window.setVcpView = setVcpView;

  function setVcpFilter(v) { window._vcpFilter = v; renderStrategy(); }
  window.setVcpFilter = setVcpFilter;

  function sortIcon(col) {
    return `<span class="sort-icon">${vcpSortCol === col ? (vcpSortAsc ? '↑' : '↓') : '·'}</span>`;
  }

  function matchFilter(d) {
    if (vcpFilter === 'near_pivot')   return !!d.is_near_pivot;
    if (vcpFilter === 'strong')       return d.contractions >= 3;
    if (vcpFilter === 'tight_pivot')  return d.pivot_range_pct != null && d.pivot_range_pct < 10;
    if (vcpFilter === 'whale')        return !!d.whale_3w_up || !!d.whale_400_3w_up;
    return true;
  }

  const TAG_META = {
    'VCP':       { color: '#3b82f6', order: 0 },
    '靠近樞紐':   { color: '#dc2626', order: 0 },
    '2段收縮':   { color: '#10b981', order: 1 },
    '3段收縮':   { color: '#10b981', order: 1 },
    '4段收縮':   { color: '#10b981', order: 1 },
    '量縮到位':   { color: '#ea7317', order: 2 },
    '樞紐緊縮':   { color: '#8b5cf6', order: 2 },
    '千張大戶連增': { color: '#d97706', order: 3 },
    '400張同步':  { color: '#d97706', order: 3 },
  };

  function tagBadges(tags) {
    return (tags || [])
      .slice()
      .sort((a, b) => (TAG_META[a]?.order ?? 9) - (TAG_META[b]?.order ?? 9))
      .map(t => {
        const c = TAG_META[t]?.color || '#9ca3af';
        return `<span class="tag-badge" style="color:${c};border-color:${c}4d">${t}</span>`;
      }).join('');
  }

  function depthChain(depths) {
    if (!depths || !depths.length) return '—';
    const colors = ['#f87171', '#fb923c', '#facc15', '#4ade80'];
    return depths.map((d, i) => {
      const c = colors[Math.min(i, colors.length - 1)];
      return `<span style="font-family:var(--mono);font-size:11px;font-weight:600;color:${c}">${d}%</span>`;
    }).join('<span style="color:var(--text3);font-size:10px;margin:0 2px">→</span>');
  }

  function fmtNum(v, digits = 2) {
    return v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(digits);
  }

  function fmtPct(v, digits = 1) {
    return v == null || Number.isNaN(Number(v)) ? '—' : `${v >= 0 ? '+' : ''}${Number(v).toFixed(digits)}%`;
  }

  const filtered = rawData.filter(matchFilter);
  const data = filtered.slice().sort(vcpCompare);

  const nearPivotCount = rawData.filter(d => d.is_near_pivot).length;
  const strongCount    = rawData.filter(d => d.contractions >= 3).length;
  const tightCount     = rawData.filter(d => d.pivot_range_pct != null && d.pivot_range_pct < 10).length;
  const whaleCount     = rawData.filter(d => d.whale_3w_up || d.whale_400_3w_up).length;
  const topIndustry    = industryStats[0];

  function exportVcpCSV() {
    const headers = [
      '代號', '名稱', '產業', '市場', '品質分數', '標籤',
      '收盤', '距MA100(%)', 'MA100',
      '收縮段數', '收縮深度序列',
      '量縮比', '樞紐高點', '樞紐振幅(%)', '靠近樞紐',
      '千張大戶連增', '400張同步', '千張3週變化', '400張3週變化', '訊號日'
    ];
    const rows = rawData.map(d => [
      d.stock_id, d.name, d.industry, d.market,
      d.quality_score ?? '',
      (d.tags || []).join(' / '),
      d.close ?? '',
      d.bias_ma100 ?? '',
      d.ma100 ?? '',
      d.contractions ?? '',
      (d.contraction_depths || []).join(' → ') + '%',
      d.vol_contraction_ratio ?? '',
      d.pivot_high ?? '',
      d.pivot_range_pct ?? '',
      d.is_near_pivot ? 'Y' : '',
      d.whale_3w_up ? 'Y' : '',
      d.whale_400_3w_up ? 'Y' : '',
      d.big_1000_chg_3w ?? '',
      d.big_400_chg_3w ?? '',
      d.signal_date ?? '',
    ]);
    const csv = [headers, ...rows]
      .map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
      .join('\r\n');
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement('a'), { href: url, download: `vcp_${strat.dataUpdated}.csv` });
    a.click();
    URL.revokeObjectURL(url);
  }
  window.exportVcpCSV = exportVcpCSV;

  function stockTable() {
    return `
      <div class="table-wrap">
        <div class="table-toolbar">
          <span class="table-title">VCP 標的池</span>
          <div class="toolbar-right">
            <span class="updated-tag">更新：${strat.dataUpdated}</span>
            <button class="btn-csv" onclick="exportVcpCSV()">匯出 CSV</button>
          </div>
        </div>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th onclick="vcpSort('stock_id')" style="cursor:pointer">代號 / 名稱${sortIcon('stock_id')}</th>
                <th onclick="vcpSort('quality_score')" style="cursor:pointer">品質${sortIcon('quality_score')}</th>
                <th onclick="vcpSort('industry')" style="cursor:pointer">產業${sortIcon('industry')}</th>
                <th onclick="vcpSort('close')" style="cursor:pointer">收盤${sortIcon('close')}</th>
                <th onclick="vcpSort('bias_ma100')" style="cursor:pointer" data-tip="(收盤 - MA100) / MA100">距MA100${sortIcon('bias_ma100')}</th>
                <th onclick="vcpSort('contractions')" style="cursor:pointer" data-tip="偵測到的 VCP 收縮段數（2~4）">段數${sortIcon('contractions')}</th>
                <th data-tip="各段回調深度（由大到小）">收縮深度</th>
                <th onclick="vcpSort('vol_contraction_ratio')" style="cursor:pointer" data-tip="最後一段均量 / 第一段均量；越小代表量縮越明顯">量縮比${sortIcon('vol_contraction_ratio')}</th>
                <th onclick="vcpSort('pivot_range_pct')" style="cursor:pointer" data-tip="最後一段收縮深度（越小代表樞紐越緊縮）">樞紐緊縮${sortIcon('pivot_range_pct')}</th>
                <th onclick="vcpSort('big_1000_chg_3w')" style="cursor:pointer" data-tip="千張大戶持股比例近 3 週變化">大戶3週${sortIcon('big_1000_chg_3w')}</th>
                <th>標籤</th>
              </tr>
            </thead>
            <tbody>
              ${data.map(d => {
                const mkt = d.market === 'TPEX' ? 'TPEX' : 'TWSE';
                const tvSymbol = `${mkt}:${d.stock_id}`;
                const pivotDist = d.pivot_high && d.close
                  ? ((d.close - d.pivot_high) / d.pivot_high * 100).toFixed(1)
                  : null;
                const pivotColor = d.is_near_pivot ? 'var(--red)' : 'var(--text3)';
                return `<tr>
                  <td>
                    <a href="https://www.tradingview.com/chart/?symbol=${tvSymbol}"
                       onclick="openTV('${tvSymbol}', event)" style="text-decoration:none;display:inline-block">
                      <div class="stock-code" style="display:flex;align-items:center;gap:5px">
                        ${d.stock_id}<span style="font-size:9px;opacity:.45;font-family:var(--mono)">↗</span>
                      </div>
                      <div class="stock-name">${d.name}</div>
                    </a>
                    <div style="font-size:10px;color:var(--text3)">${d.market || '—'}</div>
                  </td>
                  <td>
                    <span style="font-family:var(--mono);font-size:16px;font-weight:700;color:var(--blue)">${d.quality_score ?? '—'}</span>
                  </td>
                  <td><span style="font-size:12px;color:var(--text2)">${d.industry || '—'}</span></td>
                  <td><span class="price-cell">${fmtNum(d.close)}</span></td>
                  <td>
                    <span class="deviation ${(d.bias_ma100 || 0) >= 0 ? 'pos' : 'neg'}" style="font-size:13px">${fmtPct(d.bias_ma100)}</span><br>
                    <span style="font-size:10px;color:var(--text3)">MA100：${fmtNum(d.ma100)}</span>
                  </td>
                  <td>
                    <span style="font-family:var(--mono);font-size:20px;font-weight:700;color:var(--green)">${d.contractions ?? '—'}</span>
                  </td>
                  <td>${depthChain(d.contraction_depths)}</td>
                  <td>
                    <span style="font-family:var(--mono);font-size:13px;font-weight:600;color:${(d.vol_contraction_ratio || 1) < 0.6 ? 'var(--amber)' : 'var(--text2)'}">
                      ${d.vol_contraction_ratio != null ? d.vol_contraction_ratio.toFixed(2) : '—'}
                    </span>
                  </td>
                  <td>
                    <span style="font-family:var(--mono);font-size:13px;font-weight:600;color:${(d.pivot_range_pct || 99) < 10 ? 'var(--green)' : 'var(--text2)'}">
                      ${d.pivot_range_pct != null ? d.pivot_range_pct + '%' : '—'}
                    </span><br>
                    <span style="font-size:10px;color:${pivotColor}">
                      ${pivotDist != null ? (pivotDist >= 0 ? '+' : '') + pivotDist + '% 樞紐' : '—'}
                    </span>
                  </td>
                  <td>
                    <span style="font-family:var(--mono);font-size:12px;color:${d.whale_3w_up ? 'var(--green)' : 'var(--text3)'}">
                      ${d.big_1000_chg_3w != null ? (d.big_1000_chg_3w >= 0 ? '+' : '') + d.big_1000_chg_3w.toFixed(2) + '%' : '—'}
                    </span><br>
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
            const rankColor = idx === 0 ? 'var(--blue)' : idx === 1 ? 'var(--green)' : idx === 2 ? 'var(--amber)' : 'var(--text3)';
            return `
              <div style="background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:12px 16px">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
                  <div style="display:flex;align-items:center;gap:10px">
                    <span style="font-size:11px;font-weight:700;font-family:var(--mono);color:${rankColor};min-width:24px">#${idx + 1}</span>
                    <span style="font-weight:600;font-size:14px">${ind.industry}</span>
                    <span style="font-size:12px;color:var(--blue);font-weight:600">${ind.count} 檔</span>
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
          <div class="summary-label">VCP 命中</div>
          <div class="summary-value blue">${rawData.length}</div>
          <div class="summary-sub">符合完整 VCP 條件</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">靠近樞紐</div>
          <div class="summary-value" style="color:var(--red)">${nearPivotCount}</div>
          <div class="summary-sub">距突破點 5% 以內</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">強型 VCP</div>
          <div class="summary-value green">${strongCount}</div>
          <div class="summary-sub">3 段以上收縮</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">最強族群</div>
          <div class="summary-value" style="font-size:16px">${topIndustry ? topIndustry.industry : '—'}</div>
          <div class="summary-sub">${topIndustry ? `${topIndustry.count} 檔同步形成 VCP` : '尚無資料'} · 大戶加持 ${whaleCount} 檔</div>
        </div>
      </div>

      <div style="display:flex;gap:8px;padding:0 0 10px 0;flex-wrap:wrap">
        <button class="view-btn ${vcpFilter === 'all' ? 'active' : ''}" onclick="setVcpFilter('all')">全部</button>
        <button class="view-btn ${vcpFilter === 'near_pivot' ? 'active' : ''}" onclick="setVcpFilter('near_pivot')">靠近樞紐 ${nearPivotCount}</button>
        <button class="view-btn ${vcpFilter === 'strong' ? 'active' : ''}" onclick="setVcpFilter('strong')">3段以上 ${strongCount}</button>
        <button class="view-btn ${vcpFilter === 'tight_pivot' ? 'active' : ''}" onclick="setVcpFilter('tight_pivot')">樞紐緊縮 ${tightCount}</button>
        <button class="view-btn ${vcpFilter === 'whale' ? 'active' : ''}" onclick="setVcpFilter('whale')">大戶加持 ${whaleCount}</button>
      </div>

      <div style="display:flex;gap:8px;padding:0 0 12px 0">
        <button class="view-btn ${vcpView === 'stock' ? 'active' : ''}" onclick="setVcpView('stock')">個股列表</button>
        <button class="view-btn ${vcpView === 'industry' ? 'active' : ''}" onclick="setVcpView('industry')">產業統計</button>
      </div>

      ${vcpView === 'stock' ? stockTable() : industryView()}
    </div>`;
}

function _applyPriceToVCP(priceMap) {
  if (!priceMap || !DATA.vcp_data) return;
  DATA.vcp_data.forEach(item => {
    const p = priceMap[item.stock_id];
    const close = typeof p === 'number' ? p : p?.close;
    if (close != null) item.close = close;
  });
}
