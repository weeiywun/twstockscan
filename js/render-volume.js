//  量增訊號：渲染器
// ════════════════════════════════════════════════════
function renderVolumeSignal(strat, main) {
  const data = DATA.volume_signal_data || [];

  if (data.length === 0) {
    main.innerHTML = `<div class="coming-soon">
      <div class="coming-icon">${strat.icon}</div>
      <div class="coming-title">${strat.name}</div>
      <div class="coming-desc">今日無量增訊號，或資料尚未更新。<br>資料每個交易日 16:10 後自動更新。</div>
    </div>`;
    return;
  }

  const tagColor = { '持續成長': '#3a86ff', '雙軌觸發': '#e66e29', '單周增幅': '#e63946', '外資連買': '#f0b429', '投信連買': '#f0b429' };
  function tagBadges(tags) {
    return (tags || []).map(t => `<span class="tag-badge" style="background:${tagColor[t]||'#888'}">${t}</span>`).join('');
  }

  const sortIcon = col => `<span class="sort-icon">${sortCol===col ? (sortAsc?'↑':'↓') : '·'}</span>`;

  const sortedData = data.slice().sort((a, b) => {
    const va = a[sortCol] ?? -9999, vb = b[sortCol] ?? -9999;
    if (va !== vb) return sortAsc ? va - vb : vb - va;
    return (b.cumulative_3w || 0) - (a.cumulative_3w || 0);
  });

  const rows = sortedData.map(d => {
    const ratioClass = d.vol_ratio >= 2.5 ? 'neg' : 'amber-text';
    return `<tr onclick="toggleExpand('vs-${d.stock_id}')" id="row-vs-${d.stock_id}">
      <td>
        <a href="https://www.tradingview.com/chart/?symbol=${getTVSymbol(d)}"
          onclick="openTV('${getTVSymbol(d)}', event)"
          style="text-decoration:none;display:inline-block">
          <div class="stock-code" style="display:flex;align-items:center;gap:5px">
            ${d.stock_id}<span style="font-size:9px;opacity:.45;font-family:var(--mono)">↗</span>
          </div>
          <div class="stock-name">${d.name}</div>
        </a>
        <div class="stock-industry">${d.industry || ''}</div>
      </td>
      <td><span class="price-cell">${d.close?.toFixed(1) || '—'}</span></td>
      <td>
        <span class="${ratioClass}" style="font-weight:600">${d.vol_ratio != null ? d.vol_ratio.toFixed(2) + 'x' : '—'}</span><br>
        <span style="font-size:11px;color:var(--text3)">${d.vol_today != null ? (d.vol_today).toLocaleString() : '—'} 張</span>
      </td>
      <td><span class="ema-cell">${d.ema5?.toFixed(2) || '—'}</span></td>
      <td><span class="big-pct">${d.big_pct_1000 != null ? d.big_pct_1000.toFixed(2) + '%' : '—'}</span></td>
      <td><span class="big-pct ${(d.cumulative_3w||0)>=0?'pos':'neg'}">${d.cumulative_3w != null ? ((d.cumulative_3w>=0?'+':'') + d.cumulative_3w.toFixed(2) + '%') : '—'}</span></td>
      <td><div class="tag-cell">${tagBadges(d.tags)}</div></td>
    </tr>
    <tr class="expand-row" id="expand-vs-${d.stock_id}" style="display:none">
      <td colspan="7">
        <div class="expand-content">
          <div class="expand-section" style="flex:1;min-width:140px">
            <h4>量能</h4>
            <div style="font-size:12px;color:var(--text2);line-height:1.9">
              <div>當日量：<b>${d.vol_today?.toLocaleString() || '—'} 張</b></div>
              <div>10日均量：<b>${d.vol_10d_avg?.toLocaleString() || '—'} 張</b></div>
              <div>量比：<b style="color:${d.vol_ratio>=2?'var(--green)':'var(--text)'}">${d.vol_ratio?.toFixed(2) || '—'}x</b></div>
              <div>EMA5：<b>${d.ema5?.toFixed(2) || '—'}</b></div>
              <div style="color:var(--text3);font-size:11px">訊號日：${d.signal_date || '—'}</div>
            </div>
          </div>
          <div class="expand-section" style="flex:1;min-width:140px">
            <h4>籌碼</h4>
            <div style="font-size:12px;color:var(--text2);line-height:1.9">
              <div>千張大戶比：<b>${d.big_pct_1000 != null ? d.big_pct_1000.toFixed(2) + '%' : '—'}</b></div>
              <div>3週累積增幅：<b class="${(d.cumulative_3w||0)>=0?'pos':'neg'}">${d.cumulative_3w != null ? (d.cumulative_3w>=0?'+':'') + d.cumulative_3w.toFixed(2) + '%' : '—'}</b></div>
              <div style="margin-top:4px">${(d.tags||[]).map(t=>`<span class="tag-badge" style="background:${{'持續成長':'#3a86ff','雙軌觸發':'#e66e29','單周增幅':'#e63946'}[t]||'#888'}">${t}</span>`).join(' ')}</div>
            </div>
          </div>
          <div class="expand-section" style="flex:1;min-width:100px">
            <h4>操作</h4>
            <a href="https://tw.stock.yahoo.com/quote/${d.stock_id}" target="_blank"
              onclick="event.stopPropagation()"
              style="display:block;text-align:center;background:var(--bg3);border:1px solid var(--border);color:var(--text2);padding:8px 14px;border-radius:6px;font-size:12px;text-decoration:none;margin-bottom:6px">
              Yahoo 股市 ↗
            </a>
            <a href="https://www.tradingview.com/chart/?symbol=${getTVSymbol(d)}"
              onclick="openTV('${getTVSymbol(d)}', event)"
              style="display:block;text-align:center;background:var(--bg3);border:1px solid var(--border);color:var(--text2);padding:8px 14px;border-radius:6px;font-size:12px;text-decoration:none">
              TradingView ↗
            </a>
          </div>
        </div>
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
          <div class="summary-label">今日訊號</div>
          <div class="summary-value green">${data.length}</div>
          <div class="summary-sub">量增入池標的</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">最高量比</div>
          <div class="summary-value amber">${Math.max(...data.map(d => d.vol_ratio||0)).toFixed(2)}x</div>
          <div class="summary-sub">當日量 / 10日均量</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">資料日期</div>
          <div class="summary-value" style="font-size:16px;font-family:var(--mono)">${strat.dataUpdated}</div>
          <div class="summary-sub">${strat.dataSource}</div>
        </div>
      </div>
      <div class="table-wrap">
        <div class="table-toolbar">
          <span class="table-title">量增訊號標的</span>
          <div class="toolbar-right"><span class="updated-tag">更新：${strat.dataUpdated}</span></div>
        </div>
        <div class="table-scroll ${data.length > 10 ? 'table-vscroll' : ''}">
        <table>
          <thead>
            <tr>
              <th onclick="vsSort('stock_id')" style="cursor:pointer">代號 / 名稱${sortIcon('stock_id')}</th>
              <th onclick="vsSort('close')" style="cursor:pointer">現價${sortIcon('close')}</th>
              <th onclick="vsSort('vol_ratio')" style="cursor:pointer" data-tip="當日量/10日均量">量比 / 當日量${sortIcon('vol_ratio')}</th>
              <th onclick="vsSort('ema5')" style="cursor:pointer">EMA5${sortIcon('ema5')}</th>
              <th onclick="vsSort('big_pct_1000')" style="cursor:pointer">大戶比例${sortIcon('big_pct_1000')}</th>
              <th onclick="vsSort('cumulative_3w')" style="cursor:pointer" data-tip="千張大戶3週累積增幅">三周累積增幅${sortIcon('cumulative_3w')}</th>
              <th>籌碼標籤</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
        </div>
      </div>
    </div>`;

  const grid = document.getElementById('watchlistGrid');
  if (grid) grid.innerHTML = renderWatchlist();
}

