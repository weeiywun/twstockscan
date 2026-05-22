//  量增回測：渲染器
// ════════════════════════════════════════════════════
let volumePullbackFilter = 'all';

function renderVolumePullback(strat, main) {
  const model = DATA.volume_pullback_data || {};
  const active = model.active || [];
  const intraday = DATA.intraday_volume_pullback_data || [];
  const intradayMeta = DATA.intraday_volume_pullback_meta || {};
  const intradayMap = new Map(intraday.map(row => [row.stock_id, row]));
  const momentum = DATA.momentum_candidates_data || {};
  const momentumRows = momentum.results || [];

  if (active.length === 0 && intraday.length === 0) {
    main.innerHTML = `<div class="coming-soon">
      <div class="coming-icon">${strat.icon}</div>
      <div class="coming-title">${strat.name}</div>
      <div class="coming-desc">目前沒有符合量增回測結構的標的，或資料尚未更新。<br>盤後建立候選池，10:00 再做盤中量能預警。</div>
    </div>`;
    return;
  }

  const counts = {
    all: active.length,
    reentry: active.filter(row => row.status === 'reentry').length,
    pullback: active.filter(row => row.status === 'pullback').length,
    ignition: active.filter(row => row.status === 'ignition').length,
    intraday: intraday.length,
  };
  if (volumePullbackFilter !== 'all' && !(counts[volumePullbackFilter] > 0)) {
    volumePullbackFilter = 'all';
  }

  const statusRank = { reentry: 1, pullback: 2, ignition: 3, watch: 4 };
  let rowsData = active.slice();
  if (volumePullbackFilter === 'intraday') {
    rowsData = rowsData.filter(row => intradayMap.has(row.stock_id));
  } else if (volumePullbackFilter !== 'all') {
    rowsData = rowsData.filter(row => row.status === volumePullbackFilter);
  }
  rowsData.sort((a, b) => {
    const ar = statusRank[a.status] || 9;
    const br = statusRank[b.status] || 9;
    if (ar !== br) return ar - br;
    return (b.score || 0) - (a.score || 0);
  });

  const filterButton = (id, label) => {
    const count = counts[id] || 0;
    if (count === 0) return '';
    const activeStyle = volumePullbackFilter === id
      ? 'background:var(--green);border-color:var(--green);color:#fff'
      : 'background:var(--bg);border-color:var(--border);color:var(--text2)';
    return `<button onclick="setVolumePullbackFilter('${id}')" style="${activeStyle};border-width:1px;border-style:solid;border-radius:6px;padding:6px 10px;font-size:12px;cursor:pointer">${label} ${count}</button>`;
  };

  const rows = rowsData.map(row => {
    const alert = intradayMap.get(row.stock_id);
    const statusStyle = row.status === 'reentry'
      ? 'color:var(--green)'
      : (row.status === 'pullback' ? 'color:var(--amber)' : 'color:var(--text)');
    const pullbackClass = row.pullback_from_ignition_close_pct >= 0 ? 'pos' : 'neg';
    const sourceText = (row.sources || []).map(src => ({
      chips: '籌碼集中',
      price_breakout_track: '價格突破追蹤',
      volume_signal: '量增訊號',
    }[src] || src)).join(' / ');
    return `<tr onclick="toggleExpand('vpb-${row.stock_id}')" id="row-vpb-${row.stock_id}">
      <td>
        <a href="https://www.tradingview.com/chart/?symbol=${getTVSymbol(row)}"
          onclick="openTV('${getTVSymbol(row)}', event)"
          style="text-decoration:none;display:inline-block">
          <div class="stock-code" style="display:flex;align-items:center;gap:5px">
            ${row.stock_id}<span style="font-size:9px;opacity:.45;font-family:var(--mono)">↗</span>
          </div>
          <div class="stock-name">${row.name || ''}</div>
        </a>
        <div class="stock-industry">${row.industry || sourceText || ''}</div>
      </td>
      <td>
        <span class="tag-badge" style="color:var(--text);border-color:rgba(80,90,110,.35)">${row.status_label || row.status}</span>
        ${alert ? `<span class="tag-badge" style="color:var(--green);border-color:rgba(20,160,100,.45)">10:00 放量</span>` : ''}
      </td>
      <td><span style="${statusStyle};font-family:var(--mono);font-weight:700">${row.score ?? '—'}</span></td>
      <td>
        <span class="price-cell">${row.close != null ? row.close.toFixed(1) : '—'}</span><br>
        <span style="font-size:11px;color:var(--text3)">EMA20 ${row.ema20 != null ? row.ema20.toFixed(1) : '—'}</span>
      </td>
      <td>
        <span class="amber-text" style="font-weight:600">${row.ignition_vol_ratio != null ? row.ignition_vol_ratio.toFixed(2) + 'x' : '—'}</span><br>
        <span style="font-size:11px;color:var(--text3)">${row.ignition_date || '—'}</span>
      </td>
      <td><span class="big-pct ${pullbackClass}">${row.pullback_from_ignition_close_pct != null ? row.pullback_from_ignition_close_pct.toFixed(2) + '%' : '—'}</span></td>
      <td>
        ${alert ? `<span style="color:var(--green);font-weight:600">${alert.intraday_vol_ratio_to_10d != null ? alert.intraday_vol_ratio_to_10d.toFixed(2) + 'x' : '—'}</span><br>
          <span style="font-size:11px;color:var(--text3)">${alert.intraday_volume_lots?.toLocaleString() || '—'} 張</span>` : '<span style="color:var(--text3)">—</span>'}
      </td>
    </tr>
    <tr class="expand-row" id="expand-vpb-${row.stock_id}" style="display:none">
      <td colspan="7">
        <div class="expand-content">
          <div class="expand-section" style="flex:1;min-width:160px">
            <h4>結構</h4>
            <div style="font-size:12px;color:var(--text2);line-height:1.9">
              <div>點火日：<b>${row.ignition_date || '—'}</b></div>
              <div>點火高/低：<b>${row.ignition_high ?? '—'} / ${row.ignition_low ?? '—'}</b></div>
              <div>距點火：<b>${row.days_since_ignition ?? '—'} 日</b></div>
              <div>支撐：<b>${row.support_ok ? '守住' : '待確認'}</b></div>
            </div>
          </div>
          <div class="expand-section" style="flex:1;min-width:160px">
            <h4>量能</h4>
            <div style="font-size:12px;color:var(--text2);line-height:1.9">
              <div>最新量比：<b>${row.vol_ratio != null ? row.vol_ratio.toFixed(2) + 'x' : '—'}</b></div>
              <div>10日均量：<b>${row.vol_10d_avg?.toLocaleString() || '—'} 張</b></div>
              <div>最新成交量：<b>${row.volume_lots?.toLocaleString() || '—'} 張</b></div>
              <div>量能降溫：<b>${row.volume_cools ? '是' : '否'}</b></div>
            </div>
          </div>
          <div class="expand-section" style="flex:1;min-width:160px">
            <h4>10:00 預警</h4>
            <div style="font-size:12px;color:var(--text2);line-height:1.9">
              <div>狀態：<b>${alert ? '已觸發' : '未觸發 / 尚未掃描'}</b></div>
              <div>盤中量：<b>${alert?.intraday_volume_lots?.toLocaleString() || '—'} 張</b></div>
              <div>觸發門檻：<b>${alert?.intraday_trigger_volume?.toLocaleString() || '—'} 張</b></div>
              <div>時間：<b>${alert?.intraday_time || '—'}</b></div>
            </div>
          </div>
        </div>
      </td>
    </tr>`;
  }).join('');

  const intradayRows = intraday.slice()
    .sort((a, b) => (b.intraday_vol_ratio_to_10d || 0) - (a.intraday_vol_ratio_to_10d || 0))
    .map(row => {
      const poolRow = intradayMap.get(row.stock_id) || row;
      const statusText = poolRow.status_label || row.status_label || row.status || '預警';
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
        <td><span class="tag-badge" style="color:var(--green);border-color:rgba(20,160,100,.45)">${statusText}</span></td>
        <td>
          <span style="color:var(--green);font-weight:700;font-family:var(--mono)">${row.intraday_vol_ratio_to_10d != null ? Number(row.intraday_vol_ratio_to_10d).toFixed(2) + 'x' : '—'}</span><br>
          <span style="font-size:11px;color:var(--text3)">${row.intraday_volume_lots?.toLocaleString() || '—'} 張</span>
        </td>
        <td>
          <span class="price-cell">${row.intraday_close != null ? Number(row.intraday_close).toFixed(1) : '—'}</span><br>
          <span style="font-size:11px;color:var(--text3)">昨收 ${row.yesterday_close != null ? Number(row.yesterday_close).toFixed(1) : '—'}</span>
        </td>
        <td>
          <span style="font-family:var(--mono)">${row.intraday_trigger_volume?.toLocaleString() || '—'} 張</span><br>
          <span style="font-size:11px;color:var(--text3)">${row.intraday_time || intradayMeta.scan_time || '10:00'}</span>
        </td>
      </tr>`;
    }).join('');

  const intradayUpdated = intradayMeta.updated
    ? intradayMeta.updated.slice(0, 16).replace('T', ' ')
    : '';
  const intradayPanel = `
      <div class="table-wrap" style="margin-bottom:16px;border-color:${intraday.length ? 'rgba(20,160,100,.35)' : 'var(--border)'}">
        <div class="table-toolbar">
          <span class="table-title">10:00 盤中量增預警</span>
          <div class="toolbar-right">
            <span class="updated-tag">${intradayUpdated || '尚未掃描'}</span>
          </div>
        </div>
        ${intraday.length ? `
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>代號 / 名稱</th>
                <th>結構</th>
                <th>盤中量比 / 量</th>
                <th>盤中價 / 昨收</th>
                <th>觸發門檻 / 時間</th>
              </tr>
            </thead>
            <tbody>${intradayRows}</tbody>
          </table>
        </div>` : `
        <div style="padding:16px;color:var(--text3);font-size:13px;line-height:1.8">
          ${intradayMeta.status === 'ok'
            ? '今日 10:00 掃描已完成，目前沒有候選標的達到盤中放量門檻。'
            : '尚未取得今日 10:00 盤中預警結果；workflow 完成後會自動顯示在這裡。'}
        </div>`}
      </div>`;

  const sourceLabel = src => ({
    chips: '籌碼',
    ignition: '點火',
    volume_signal: '量增',
    right_top_track: '突破追蹤',
    breakout_track: '突破',
    volume_pullback: '回測',
    pullback: '回測',
    stock_analysis: '追蹤',
    follow: '追蹤',
  }[src] || src);
  const metricText = row => {
    const m = row.metrics || {};
    const parts = [];
    if (m.ignition_vol_ratio != null) parts.push(`點火 ${Number(m.ignition_vol_ratio).toFixed(2)}x`);
    if (m.today_vol_ratio != null) parts.push(`今日 ${Number(m.today_vol_ratio).toFixed(2)}x`);
    if (m.track_pnl_pct != null) parts.push(`追蹤 ${Number(m.track_pnl_pct).toFixed(1)}%`);
    if (m.pullback_from_ignition_close_pct != null) parts.push(`距點火 ${Number(m.pullback_from_ignition_close_pct).toFixed(1)}%`);
    if (m.market_cap != null) parts.push(`市值 ${Number(m.market_cap).toFixed(1)}億`);
    if (m.bbw != null) parts.push(`BBW ${Number(m.bbw).toFixed(1)}`);
    return parts.join(' / ') || '—';
  };
  const momentumTop = momentumRows.slice(0, 10);
  const momentumTable = momentumTop.map((row, idx) => {
    const risk = (row.risk_flags || []).length
      ? `<span class="tag-badge" style="color:var(--amber);border-color:rgba(210,150,40,.45)">${row.risk_flags[0]}</span>`
      : '';
    const statusColor = row.status === '再啟動'
      ? 'var(--green)'
      : (row.status === '點火首日' ? 'var(--amber)' : 'var(--text)');
    return `<tr onclick="toggleExpand('mom-${row.stock_id}')" id="row-mom-${row.stock_id}">
      <td style="color:var(--text3);font-family:var(--mono);font-size:12px">${idx + 1}</td>
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
      <td><span class="tag-badge" style="color:${statusColor};border-color:rgba(80,90,110,.35)">${row.status || '—'}</span>${risk}</td>
      <td><span style="font-family:var(--mono);font-weight:700;color:var(--green)">${row.score ?? '—'}</span></td>
      <td><span class="price-cell">${row.close != null ? Number(row.close).toFixed(1) : '—'}</span></td>
      <td>${(row.sources || []).map(s => `<span class="tag-badge" style="color:var(--text2);border-color:rgba(80,90,110,.35)">${sourceLabel(s)}</span>`).join('')}</td>
      <td style="font-size:12px;color:var(--text2);line-height:1.7">${metricText(row)}</td>
    </tr>
    <tr class="expand-row" id="expand-mom-${row.stock_id}" style="display:none">
      <td colspan="7">
        <div class="expand-content">
          <div class="expand-section" style="flex:1;min-width:180px">
            <h4>分數來源</h4>
            <div style="font-size:12px;color:var(--text2);line-height:1.9">
              ${Object.entries(row.score_parts || {}).map(([k, v]) => `<div>${sourceLabel(k)}：<b>${v}</b></div>`).join('') || '<div>—</div>'}
            </div>
          </div>
          <div class="expand-section" style="flex:2;min-width:240px">
            <h4>標籤</h4>
            <div style="font-size:12px;color:var(--text2);line-height:1.9">${(row.tags || []).join(' / ') || '—'}</div>
          </div>
        </div>
      </td>
    </tr>`;
  }).join('');
  const momentumPanel = momentumRows.length ? `
      <div class="table-wrap" style="margin-bottom:16px">
        <div class="table-toolbar">
          <span class="table-title">短線強勢雷達 Top 10</span>
          <div class="toolbar-right"><span class="updated-tag">更新：${(momentum.updated || '').slice(0, 10) || strat.dataUpdated}</span></div>
        </div>
        <div class="filter-row" style="padding:10px 12px;border-bottom:1px solid var(--border);gap:8px;display:flex;flex-wrap:wrap;color:var(--text3);font-size:12px">
          整合籌碼集中、量增訊號、突破追蹤、量增回測與標的追蹤；VCP / 法人動能暫不納入。
        </div>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>代號 / 名稱</th>
                <th>狀態</th>
                <th>爆發分數</th>
                <th>收盤</th>
                <th>來源</th>
                <th>關鍵指標</th>
              </tr>
            </thead>
            <tbody>${momentumTable}</tbody>
          </table>
        </div>
      </div>` : '';

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
          <div class="summary-label">短線雷達</div>
          <div class="summary-value green">${momentum.summary?.total ?? momentumRows.length}</div>
          <div class="summary-sub">整合啟用策略</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">候選池</div>
          <div class="summary-value green">${active.length}</div>
          <div class="summary-sub">盤後量增回測</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">回測 / 再啟動</div>
          <div class="summary-value amber">${counts.pullback} / ${counts.reentry}</div>
          <div class="summary-sub">人工優先檢查區</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">10:00 預警</div>
          <div class="summary-value">${intraday.length}</div>
          <div class="summary-sub">盤中累積量達標</div>
        </div>
      </div>
      ${intradayPanel}
      ${momentumPanel}
      <div class="table-wrap">
        <div class="table-toolbar">
          <span class="table-title">量增回測候選名單</span>
          <div class="toolbar-right"><span class="updated-tag">更新：${strat.dataUpdated}</span></div>
        </div>
        <div class="filter-row" style="padding:10px 12px;border-bottom:1px solid var(--border);gap:8px;display:flex;flex-wrap:wrap">
          ${filterButton('all', '全部')}
          ${filterButton('reentry', '再啟動')}
          ${filterButton('pullback', '回測觀察')}
          ${filterButton('ignition', '點火')}
          ${filterButton('intraday', '10:00 放量')}
        </div>
        <div class="table-scroll ${rowsData.length > 10 ? 'table-vscroll' : ''}">
          <table>
            <thead>
              <tr>
                <th>代號 / 名稱</th>
                <th>狀態</th>
                <th>分數</th>
                <th>收盤 / EMA20</th>
                <th>點火量比 / 日期</th>
                <th>回落幅度</th>
                <th>盤中量比 / 量</th>
              </tr>
            </thead>
            <tbody>${rows || `<tr><td colspan="7" style="text-align:center;color:var(--text3);padding:28px">此分類目前沒有標的</td></tr>`}</tbody>
          </table>
        </div>
      </div>
    </div>`;
}

function setVolumePullbackFilter(filter) {
  volumePullbackFilter = filter;
  renderStrategy();
}
