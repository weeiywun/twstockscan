function fdNum(value, digits = 0) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return Number(value).toLocaleString('zh-TW', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function fdSigned(value, digits = 0) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const n = Number(value);
  return `${n > 0 ? '+' : ''}${fdNum(n, digits)}`;
}

function fdPct(value, digits = 2) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `${fdSigned(value, digits)}%`;
}

function fdTone(value, invert = false) {
  if (value == null || Number.isNaN(Number(value)) || Number(value) === 0) return 'flat';
  const positive = Number(value) > 0;
  return (invert ? !positive : positive) ? 'pos' : 'neg';
}

function fdMetric(label, value, sub = '', tone = 'flat') {
  return `
    <div class="fd-metric">
      <div class="fd-metric-label">${label}</div>
      <div class="fd-metric-value ${tone}">${value}</div>
      ${sub ? `<div class="fd-metric-sub">${sub}</div>` : ''}
    </div>`;
}

function fdChangeChip(value, suffix = '', invert = false, digits = 0) {
  if (value == null || Number.isNaN(Number(value)) || Number(value) === 0) return '';
  const tone = fdTone(value, invert);
  return `<span class="fd-change-chip ${tone}">${fdSigned(value, digits)}${suffix}</span>`;
}

function fdMetricLine(label, value, aux = '', sub = '', tone = 'flat') {
  return `
    <div class="fd-metric">
      <div class="fd-metric-label">${label}</div>
      <div class="fd-metric-line">
        <span class="fd-metric-value ${tone}">${value}</span>
        ${aux || ''}
      </div>
      ${sub ? `<div class="fd-metric-sub">${sub}</div>` : ''}
    </div>`;
}

function fdGaugeAngle(gaugeValue) {
  const value = Math.max(0, Math.min(100, Number(gaugeValue ?? 50)));
  return -72 + value * 1.44;
}

function fdMiniGauge({ value, label, sub }) {
  const score = Number(value ?? 50);
  const angle = fdGaugeAngle(score);
  return `
    <div class="fd-mini-gauge" style="--needle:${angle}deg">
      <div class="fd-mini-gauge-copy">
        <div class="fd-metric-label">${label}</div>
        <div class="fd-gauge-value ${fdTone(score - 50)}">${value == null ? '—' : fdNum(score, 0)}</div>
        <div class="fd-metric-sub">${sub || ''}</div>
      </div>
      <div class="fd-gauge-wrap">
        <div class="fd-gauge-track"></div>
        <div class="fd-gauge-needle"></div>
        <div class="fd-gauge-hub"></div>
        <div class="fd-gauge-scale"><span>FEAR</span><span>NEUTRAL</span><span>GREED</span></div>
      </div>
    </div>`;
}

function fdIndexMetric(key, fallbackName) {
  const item = DATA.market_index_data?.indices?.[key] || {};
  const change = item.change_pct;
  return fdMetricLine(
    item.name || fallbackName,
    fdNum(item.close, 2),
    change == null ? '' : fdChangeChip(change, '%', false, 2),
    item.date || DATA.market_index_data?.date || '等待更新',
    fdTone(change)
  );
}

function fdTable(title, meta, headers, body, className = '') {
  return `
    <section class="fd-panel ${className}">
      <div class="fd-panel-hd">
        <div>
          <div class="fd-panel-title">${title}</div>
          <div class="fd-panel-meta">${meta || '等待更新'}</div>
        </div>
      </div>
      <div class="table-scroll">
        <table class="fd-table">
          <thead><tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    </section>`;
}

function fdFuturesCombinedRows(dayTx, nightTx) {
  const dayTraders = dayTx?.traders || {};
  const dayChanges = dayTx?.trader_changes || {};
  const nightTraders = nightTx?.traders || {};
  const order = ['foreign', 'investment_trust', 'dealer', 'total'];
  return order.map(key => {
    const day = dayTraders[key] || {};
    const night = nightTraders[key] || {};
    const oiChange = dayChanges[key]?.oi_net_lots;
    const label = key === 'total' ? '合計' : (day.label || night.label || key);
    return `
      <tr>
        <td data-label="法人">${label}</td>
        <td data-label="日盤買賣超" class="mono ${fdTone(day.net_lots)}">${fdSigned(day.net_lots)}</td>
        <td data-label="日盤未平倉淨額" class="mono ${fdTone(day.oi_net_lots)}">
          <span class="fd-oi-cell">
            <span class="fd-oi-main">${fdSigned(day.oi_net_lots)}</span>
            ${fdChangeChip(oiChange, '口')}
          </span>
        </td>
        <td data-label="夜盤買賣超" class="mono ${fdTone(night.net_lots)}">${fdSigned(night.net_lots)}</td>
      </tr>`;
  }).join('');
}

function fdStockRows(stock) {
  const rows = (stock?.history || []).slice(0, 4);
  return rows.map(row => {
    const t = row.traders || {};
    return `
      <tr>
        <td data-label="日期" class="mono">${row.date || '—'}</td>
        <td data-label="外資" class="mono ${fdTone(t.foreign?.net_amount)}">${fdSigned((t.foreign?.net_amount || 0) / 100000000, 2)}</td>
        <td data-label="投信" class="mono ${fdTone(t.investment_trust?.net_amount)}">${fdSigned((t.investment_trust?.net_amount || 0) / 100000000, 2)}</td>
        <td data-label="自營商" class="mono ${fdTone(t.dealer?.net_amount)}">${fdSigned((t.dealer?.net_amount || 0) / 100000000, 2)}</td>
        <td data-label="合計" class="mono ${fdTone(t.total?.net_amount)}">${fdSigned((t.total?.net_amount || 0) / 100000000, 2)}</td>
      </tr>`;
  }).join('');
}

function fdSentimentValue(row, field) {
  const value = row?.[field];
  if (value == null || Number.isNaN(Number(value))) return '—';
  return row.format === 'percent' ? `${fdNum(value, 2)}%` : fdNum(value, 2);
}

function fdRetailSummary(retailDash, retail) {
  const rows = (retailDash?.rows || []).filter(row => ['mtx', 'tmf'].includes(row.key));
  const summaryRows = rows.length ? rows : [{
    key: 'mtx',
    label: '小台散戶多空比',
    today: retail?.ratio,
    change: null,
    format: 'percent',
  }];
  return `
    <div class="fd-retail-inline">
      ${summaryRows.map(row => {
        const label = row.key === 'tmf' ? '微台' : '小台';
        return `
          <div class="fd-retail-row">
            <span class="fd-retail-name">${label}</span>
            <span class="fd-retail-value">
              <span class="fd-metric-value ${fdTone(row.today)}">${fdSentimentValue(row, 'today')}</span>
              ${fdChangeChip(row.change, row.format === 'percent' ? '%' : '', false, 2)}
            </span>
          </div>`;
      }).join('')}
    </div>`;
}

function fdMarketReadNote(retailDash, pc, marginData) {
  const mtx = (retailDash?.rows || []).find(row => row.key === 'mtx');
  const retail = Number(mtx?.today);
  const retailChange = Number(mtx?.change);
  const pcValue = Number(pc?.open_interest_ratio);
  const marginChange = Number(marginData?.summary?.total_change_thousand_twd);
  const notes = [];
  if (!Number.isNaN(retail) && retail >= 20) notes.push('散戶偏多偏高，追價時更需要等回測。');
  if (!Number.isNaN(retailChange) && retailChange >= 8) notes.push('散戶多方部位快速升溫，留意短線震盪。');
  if (!Number.isNaN(pcValue) && pcValue >= 140) notes.push('P/C 偏高，避險需求仍在。');
  if (!Number.isNaN(marginChange) && marginChange > 0) notes.push('融資餘額增加，市場槓桿正在升溫。');
  if (!notes.length) notes.push('目前市場情緒沒有明顯極端值，回到個股結構判斷。');
  return notes.join(' ');
}

function fdSeriesChart({ title, meta, lines, summary, className = '' }) {
  const mergedDates = Array.from(new Set(lines.flatMap(line => line.points.map(point => point.date)))).sort();
  const values = lines.flatMap(line => line.points.map(point => point.value)).filter(v => v != null && !Number.isNaN(Number(v)));
  if (mergedDates.length < 2 || !values.length) {
    return `
      <section class="fd-panel fd-chart-panel ${className}">
        <div class="fd-panel-title">${title}</div>
        <div class="fd-panel-meta">等待足夠歷史資料</div>
      </section>`;
  }

  const width = 620;
  const height = 240;
  const pad = { left: 42, right: 34, top: 24, bottom: 34 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const x = index => pad.left + (mergedDates.length === 1 ? 0 : index * innerW / (mergedDates.length - 1));
  const y = value => {
    if (value == null || Number.isNaN(Number(value))) return null;
    if (max === min) return pad.top + innerH / 2;
    return pad.top + innerH - ((Number(value) - min) / (max - min)) * innerH;
  };
  const dateIndex = Object.fromEntries(mergedDates.map((date, idx) => [date, idx]));
  const path = line => line.points.map(point => {
    const yi = y(point.value);
    const xi = x(dateIndex[point.date]);
    return yi == null ? '' : `${point.date === line.points[0].date ? 'M' : 'L'} ${xi.toFixed(1)} ${yi.toFixed(1)}`;
  }).filter(Boolean).join(' ');
  const zeroY = y(0);

  return `
    <section class="fd-panel fd-chart-panel ${className}">
      <div class="fd-panel-hd">
        <div>
          <div class="fd-panel-title">${title}</div>
          <div class="fd-panel-meta">${meta || `${mergedDates[0]} - ${mergedDates[mergedDates.length - 1]}`}</div>
        </div>
        <div class="fd-chart-legend">
          ${lines.map(line => `<span><i class="fd-dot ${line.key}"></i>${line.label}</span>`).join('')}
        </div>
      </div>
      <div class="fd-chart-wrap">
        <svg class="fd-retail-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${title}">
          <line x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}" class="fd-chart-axis" />
          <line x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}" class="fd-chart-axis" />
          ${zeroY != null ? `<line x1="${pad.left}" y1="${zeroY}" x2="${width - pad.right}" y2="${zeroY}" class="fd-chart-zero" />` : ''}
          ${lines.map(line => `<path d="${path(line)}" class="fd-chart-line ${line.key}" />`).join('')}
          ${mergedDates.map((date, i) => `<text x="${x(i)}" y="${height - 12}" class="fd-chart-label" text-anchor="${i === 0 ? 'start' : i === mergedDates.length - 1 ? 'end' : 'middle'}">${date.slice(5)}</text>`).join('')}
        </svg>
      </div>
      ${summary ? `<div class="fd-chart-summary">${summary}</div>` : ''}
    </section>`;
}

function fdMarginRows(marginData) {
  const rows = (marginData?.history || []).slice(-4).reverse();
  if (!rows.length) {
    return '<tr><td colspan="5" style="text-align:center;color:var(--text3)">尚無融資餘額資料</td></tr>';
  }
  return rows.map(row => {
    const twseChange = row.twse?.finance_balance_thousand_twd != null && row.twse?.previous_balance_thousand_twd != null
      ? row.twse.finance_balance_thousand_twd - row.twse.previous_balance_thousand_twd
      : null;
    const tpexChange = row.tpex?.finance_balance_thousand_twd != null && row.tpex?.previous_balance_thousand_twd != null
      ? row.tpex.finance_balance_thousand_twd - row.tpex.previous_balance_thousand_twd
      : null;
    return `
      <tr>
        <td data-label="日期" class="mono">${row.date || '—'}</td>
        <td data-label="融資餘額" class="mono">${row.total_finance_balance_thousand_twd == null ? '—' : fdNum(row.total_finance_balance_thousand_twd / 100000, 1)}</td>
        <td data-label="日增減" class="mono ${fdTone(row.total_change_thousand_twd)}">${row.total_change_thousand_twd == null ? '—' : fdSigned(row.total_change_thousand_twd / 100000, 1)}</td>
        <td data-label="上市增減" class="mono ${fdTone(twseChange)}">${twseChange == null ? '—' : fdSigned(twseChange / 100000, 1)}</td>
        <td data-label="上櫃增減" class="mono ${fdTone(tpexChange)}">${tpexChange == null ? '—' : fdSigned(tpexChange / 100000, 1)}</td>
      </tr>`;
  }).join('');
}

function fdMarginTable(marginData) {
  const latest = marginData?.summary || {};
  const summary = latest.date
    ? `餘額 ${latest.total_finance_balance_thousand_twd == null ? '—' : fdNum(latest.total_finance_balance_thousand_twd / 100000, 1) + ' 億'} · 日增減 ${latest.total_change_thousand_twd == null ? '—' : fdSigned(latest.total_change_thousand_twd / 100000, 1) + ' 億'}`
    : '等待更新';
  return fdTable(
    '融資餘額變化',
    `${marginData?.date || '等待更新'} · ${summary} · 單位：億`,
    ['日期', '融資餘額', '日增減', '上市增減', '上櫃增減'],
    fdMarginRows(marginData),
    'fd-margin-table'
  );
}

function renderFutureDashboard(strat, main) {
  const fd = DATA.futures_dashboard_data || {};
  const marginData = DATA.margin_balance_data || {};
  const dayTx = fd.futures?.day_session?.tx;
  const nightTx = fd.futures?.night_session?.tx;
  const retail = fd.sentiment?.retail_long_short;
  const retailDash = fd.sentiment?.retail_dashboard;
  const pc = fd.sentiment?.pc_ratio;
  const stock = fd.stock_institutional;
  const fearGreed = fd.us_sentiment?.fear_greed || {};
  const updated = fd.updated ? fd.updated.slice(0, 16).replace('T', ' ') : '尚未更新';

  main.innerHTML = `
    <div class="strategy-panel active">
      <div class="strat-header fd-header">
        <div>
          <div class="strat-title">${strat.icon} FUTURE DASHBOARD</div>
          <div class="strat-desc">市場溫度、籌碼情緒與槓桿變化，只做環境判斷，不取代個股策略。</div>
        </div>
      </div>

      <div class="fd-grid fd-top-grid">
        <section class="fd-panel fd-dashboard-card">
          <div class="fd-panel-title">台股盤面</div>
          <div class="fd-panel-meta">${fd.date || '等待更新'} · 盤面 + 散戶情緒 + 解讀</div>
          <div class="fd-market-brief-grid fd-market-brief-grid-tw">
            ${fdIndexMetric('TXF_NEAR', '台指近月')}
            ${fdIndexMetric('TAIEX', '台灣加權')}
            ${fdIndexMetric('TPEX', '櫃買指數')}
            ${fdMetric('成交量 P/C', pc?.volume_ratio == null ? '—' : `${fdNum(pc.volume_ratio, 2)}%`, pc?.date || '', fdTone(pc?.volume_ratio - 100))}
            ${fdMetric('未平倉 P/C', pc?.open_interest_ratio == null ? '—' : `${fdNum(pc.open_interest_ratio, 2)}%`, pc?.source || '', fdTone(pc?.open_interest_ratio - 100))}
          </div>
          <div class="fd-inline-section">
            <div>
              <div class="fd-panel-title">散戶多空比</div>
              ${fdRetailSummary(retailDash, retail)}
            </div>
            <div>
              <div class="fd-panel-title">今日解讀</div>
              <div class="fd-read-text">${fdMarketReadNote(retailDash, pc, marginData)}</div>
            </div>
          </div>
        </section>

        <section class="fd-panel fd-dashboard-card">
          <div class="fd-panel-title">美股盤面</div>
          <div class="fd-panel-meta">外盤風險溫度，隔日開盤參考</div>
          <div class="fd-market-brief-grid fd-market-brief-grid-us">
            ${fdIndexMetric('NASDAQ', 'NASDAQ')}
            ${fdIndexMetric('DOW', 'DOW')}
            ${fdIndexMetric('SOX', 'SOX')}
          </div>
          ${fdMiniGauge({
            label: 'CNN Fear & Greed',
            value: fearGreed.score,
            sub: `${fearGreed.rating_zh || fearGreed.rating || '等待更新'}${fearGreed.timestamp ? ' · ' + String(fearGreed.timestamp).slice(0, 16).replace('T', ' ') : ''}`,
          })}
        </section>
      </div>

      <div class="fd-grid fd-core-grid">
        ${fdTable(
          '三大法人現貨買賣超金額',
          `${stock?.date || '等待 TWSE 更新'} · ${stock?.source || 'TWSE'} · 單位：億元`,
          ['日期', '外資', '投信', '自營商', '合計'],
          stock ? fdStockRows(stock) : '<tr><td colspan="5" style="text-align:center;color:var(--text3)">尚無 TWSE 現貨法人金額資料</td></tr>'
        )}
        ${fdMarginTable(marginData)}
        ${fdTable(
          '台指期法人多空（日 / 夜）',
          `${dayTx?.date || '等待日盤'} / ${nightTx?.date || '等待夜盤'} · TAIFEX`,
          ['法人', '日盤買賣超', '日盤未平倉淨額', '夜盤買賣超'],
          fdFuturesCombinedRows(dayTx, nightTx),
          'fd-futures-combined'
        )}
      </div>

      <section class="fd-panel fd-status-panel">
        <div class="fd-panel-title">資料狀態</div>
        <div class="fd-note">
          <div>期權更新：${updated}</div>
          <div>期權資料日：${fd.date || '等待更新'}</div>
          <div>融資資料日：${marginData.date || '等待更新'}</div>
          <div>來源：${fd.source || 'TAIFEX + CNN + TWSE'} / ${marginData.source || 'TWSE + TPEx'}</div>
        </div>
      </section>
    </div>`;
}
