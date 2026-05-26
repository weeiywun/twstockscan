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

function fdGaugeCard({ eyebrow, title, value, sub, gauge, tone = 'flat', left = 'FEAR', center = 'NEUTRAL', right = 'GREED', commentary = '' }) {
  const angle = fdGaugeAngle(gauge);
  return `
    <section class="fd-gauge-card ${tone}">
      <div class="fd-gauge-copy">
        <div class="fd-gauge-eyebrow">${eyebrow}</div>
        <div class="fd-gauge-title">${title}</div>
        <div class="fd-gauge-value ${tone}">${value}</div>
        <div class="fd-gauge-sub">${sub || ''}</div>
      </div>
      <div class="fd-gauge-wrap" style="--needle:${angle}deg">
        <div class="fd-gauge-track"></div>
        <div class="fd-gauge-needle"></div>
        <div class="fd-gauge-hub"></div>
        <div class="fd-gauge-scale">
          <span>${left}</span><span>${center}</span><span>${right}</span>
        </div>
      </div>
      ${commentary ? `<div class="fd-gauge-commentary">${commentary}</div>` : ''}
    </section>`;
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

function fdTraderRows(contract) {
  const traders = contract?.traders || {};
  const changes = contract?.trader_changes || {};
  const order = ['foreign', 'investment_trust', 'dealer', 'total'];
  return order.map(key => {
    const item = traders[key] || {};
    const oiChange = changes[key]?.oi_net_lots;
    const label = key === 'total' ? '合計' : (item.label || key);
    return `
      <tr>
        <td>${label}</td>
        <td class="mono ${fdTone(item.net_lots)}">${fdSigned(item.net_lots)}</td>
        <td class="mono ${fdTone(item.oi_net_lots)}">
          <span class="fd-oi-cell">
            <span class="fd-oi-main">${fdSigned(item.oi_net_lots)}</span>
            ${fdChangeChip(oiChange, '口')}
          </span>
        </td>
      </tr>`;
  }).join('');
}

function fdNightRows(contract) {
  const traders = contract?.traders || {};
  const order = ['foreign', 'investment_trust', 'dealer', 'total'];
  return order.map(key => {
    const item = traders[key] || {};
    const label = key === 'total' ? '合計' : (item.label || key);
    return `
      <tr>
        <td>${label}</td>
        <td class="mono ${fdTone(item.net_lots)}">${fdSigned(item.net_lots)}</td>
      </tr>`;
  }).join('');
}

function fdStockRows(stock) {
  const rows = (stock?.history || []).slice(0, 5);
  return rows.map(row => {
    const t = row.traders || {};
    return `
      <tr>
        <td class="mono">${row.date || '—'}</td>
        <td class="mono ${fdTone(t.foreign?.net_amount)}">${fdSigned((t.foreign?.net_amount || 0) / 100000000, 2)}</td>
        <td class="mono ${fdTone(t.investment_trust?.net_amount)}">${fdSigned((t.investment_trust?.net_amount || 0) / 100000000, 2)}</td>
        <td class="mono ${fdTone(t.dealer?.net_amount)}">${fdSigned((t.dealer?.net_amount || 0) / 100000000, 2)}</td>
        <td class="mono ${fdTone(t.total?.net_amount)}">${fdSigned((t.total?.net_amount || 0) / 100000000, 2)}</td>
      </tr>`;
  }).join('');
}

function fdSentimentValue(row, field) {
  const value = row?.[field];
  if (value == null || Number.isNaN(Number(value))) return '—';
  return row.format === 'percent' ? `${fdNum(value, 2)}%` : fdNum(value, 2);
}

function fdTrendTone(trend) {
  if (trend === '上升') return 'pos';
  if (trend === '下降') return 'neg';
  return 'flat';
}

function fdSentimentRows(retailDash) {
  const rows = retailDash?.rows || [];
  if (!rows.length) {
    return '<tr><td colspan="4" style="text-align:center;color:var(--text3)">尚無散戶情緒資料</td></tr>';
  }
  return rows.map(row => `
    <tr>
      <td>${row.label || '—'}</td>
      <td class="mono ${fdTone(row.today)}">${fdSentimentValue(row, 'today')}</td>
      <td class="mono ${fdTone(row.change)}">${row.change == null ? '—' : fdSigned(row.change, row.format === 'percent' ? 2 : 2)}</td>
      <td class="mono ${fdTrendTone(row.trend)}">${row.trend || '—'}</td>
    </tr>`).join('');
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
    <div class="fd-metric fd-retail-summary">
      <div class="fd-metric-label">散戶多空比</div>
      <div class="fd-retail-rows">
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
      </div>
      <div class="fd-metric-sub">${retailDash?.date || retail?.date || ''}</div>
    </div>`;
}

function fdRetailChart(retailDash) {
  const mtx = (retailDash?.rows || []).find(row => row.key === 'mtx');
  const tmf = (retailDash?.rows || []).find(row => row.key === 'tmf');
  const taiExHistory = DATA.market_index_data?.history?.TAIEX || {};
  const baseHistory = (mtx?.history || []).slice().reverse();
  const points = baseHistory.map(item => ({
    date: item.date,
    mtx: Number(item.ratio),
    tmf: Number((tmf?.history || []).find(row => row.date === item.date)?.ratio),
    taiex: Number(taiExHistory[item.date]),
  })).filter(item => item.date && !Number.isNaN(item.mtx));

  if (points.length < 2) {
    return `
      <section class="fd-panel fd-chart-panel">
        <div class="fd-panel-title">散戶多空比 × 大盤走勢</div>
        <div class="fd-panel-meta">等待足夠歷史資料</div>
      </section>`;
  }

  const width = 620;
  const height = 240;
  const pad = { left: 42, right: 34, top: 24, bottom: 34 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const x = index => pad.left + (points.length === 1 ? 0 : index * innerW / (points.length - 1));
  const retailValues = points.flatMap(p => [p.mtx, p.tmf]).filter(v => !Number.isNaN(v));
  const indexValues = points.map(p => p.taiex).filter(v => !Number.isNaN(v));
  const retailMin = Math.min(...retailValues, 0);
  const retailMax = Math.max(...retailValues, 1);
  const indexMin = Math.min(...indexValues);
  const indexMax = Math.max(...indexValues);
  const scale = (value, min, max) => {
    if (value == null || Number.isNaN(value)) return null;
    if (max === min) return pad.top + innerH / 2;
    return pad.top + innerH - ((value - min) / (max - min)) * innerH;
  };
  const path = (key, min, max) => points.map((p, i) => {
    const y = scale(p[key], min, max);
    return y == null ? '' : `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y.toFixed(1)}`;
  }).filter(Boolean).join(' ');
  const zeroY = scale(0, retailMin, retailMax);
  const last = points[points.length - 1];
  const firstIndex = indexValues[0];
  const indexChange = firstIndex ? (last.taiex / firstIndex - 1) * 100 : null;

  return `
    <section class="fd-panel fd-chart-panel">
      <div class="fd-panel-hd">
        <div>
          <div class="fd-panel-title">散戶多空比 × 大盤走勢</div>
          <div class="fd-panel-meta">${points[0].date} - ${last.date}，觀察散戶情緒是否跟大盤同向過熱</div>
        </div>
        <div class="fd-chart-legend">
          <span><i class="fd-dot retail"></i>小台</span>
          <span><i class="fd-dot micro"></i>微台</span>
          <span><i class="fd-dot index"></i>大盤</span>
        </div>
      </div>
      <div class="fd-chart-wrap">
        <svg class="fd-retail-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="散戶多空比與加權指數走勢">
          <line x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}" class="fd-chart-axis" />
          <line x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}" class="fd-chart-axis" />
          ${zeroY != null ? `<line x1="${pad.left}" y1="${zeroY}" x2="${width - pad.right}" y2="${zeroY}" class="fd-chart-zero" />` : ''}
          <path d="${path('taiex', indexMin, indexMax)}" class="fd-chart-line index" />
          <path d="${path('mtx', retailMin, retailMax)}" class="fd-chart-line retail" />
          <path d="${path('tmf', retailMin, retailMax)}" class="fd-chart-line micro" />
          ${points.map((p, i) => `<text x="${x(i)}" y="${height - 12}" class="fd-chart-label" text-anchor="${i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle'}">${p.date.slice(5)}</text>`).join('')}
        </svg>
      </div>
      <div class="fd-chart-summary">
        <div>${mtx?.label || '小台散戶多空比'}：<b class="${fdTone(last.mtx)}">${fdPct(last.mtx)}</b></div>
        <div>${tmf?.label || '微台散戶多空比'}：<b class="${fdTone(last.tmf)}">${fdPct(last.tmf)}</b></div>
        <div>大盤區間：<b class="${fdTone(indexChange)}">${fdPct(indexChange)}</b></div>
      </div>
    </section>`;
}

function fdMarketReadNote(retailDash, pc, fearGreed) {
  const mtx = (retailDash?.rows || []).find(row => row.key === 'mtx');
  const retail = Number(mtx?.today);
  const retailChange = Number(mtx?.change);
  const pcValue = Number(pc?.open_interest_ratio);
  const fg = Number(fearGreed?.score);
  const notes = [];
  if (!Number.isNaN(retail) && retail >= 20) notes.push('散戶偏多偏高，追價時更需要等回測。');
  if (!Number.isNaN(retailChange) && retailChange >= 8) notes.push('散戶多方部位快速升溫，留意短線震盪。');
  if (!Number.isNaN(pcValue) && pcValue >= 140) notes.push('P/C 偏高，避險需求仍在。');
  if (!Number.isNaN(fg) && fg >= 75) notes.push('美股情緒偏貪婪，隔日開盤容易受外盤帶動。');
  if (!notes.length) notes.push('目前市場情緒沒有明顯極端值，回到個股結構判斷。');
  return notes.join(' ');
}

function renderFutureDashboard(strat, main) {
  const fd = DATA.futures_dashboard_data || {};
  const dayTx = fd.futures?.day_session?.tx;
  const nightTx = fd.futures?.night_session?.tx;
  const retail = fd.sentiment?.retail_long_short;
  const retailDash = fd.sentiment?.retail_dashboard;
  const pc = fd.sentiment?.pc_ratio;
  const stock = fd.stock_institutional;
  const fearGreed = fd.us_sentiment?.fear_greed || {};
  const updated = fd.updated ? fd.updated.slice(0, 16).replace('T', ' ') : '尚未更新';
  const txTotal = dayTx?.traders?.total || {};
  const nightTotal = nightTx?.traders?.total || {};

  const dayHeaders = ['法人', '買賣超', '未平倉淨額'];
  const nightHeaders = ['法人', '夜盤買賣超'];
  const stockHeaders = ['日期', '外資(億)', '投信(億)', '自營商(億)', '合計(億)'];

  main.innerHTML = `
    <div class="strategy-panel active">
      <div class="strat-header fd-header">
        <div>
          <div class="strat-title">${strat.icon} FUTURE DASHBOARD</div>
          <div class="strat-desc">保留外部風險溫度與台股籌碼情緒，移除原本 Market Bias 綜合評分。</div>
        </div>
      </div>

      <div class="fd-hero-grid fd-hero-grid-simple">
        ${fdGaugeCard({
          eyebrow: 'CNN FEAR & GREED',
          title: '美股風險情緒',
          value: fearGreed.score == null ? '—' : fdNum(fearGreed.score, 0),
          sub: `${fearGreed.rating_zh || fearGreed.rating || '等待更新'} · 極度恐懼 <25 · 極度貪婪 >75${fearGreed.timestamp ? ' · ' + String(fearGreed.timestamp).slice(0, 16).replace('T', ' ') : ''}`,
          gauge: fearGreed.score,
          tone: fdTone((fearGreed.score ?? 50) - 50),
          left: 'FEAR',
          center: 'NEUTRAL',
          right: 'GREED'
        })}
        <section class="fd-panel fd-market-brief">
          <div class="fd-panel-title">台股盤面</div>
          <div class="fd-panel-meta">只做環境參考，不再輸出 Bias 多空判斷</div>
          <div class="fd-market-brief-grid">
            ${fdIndexMetric('TXF_NEAR', '台指近月')}
            ${fdIndexMetric('TAIEX', '台灣加權')}
            ${fdIndexMetric('TPEX', '櫃買指數')}
            ${fdIndexMetric('SOX', '費半')}
          </div>
        </section>
      </div>

      <div class="fd-grid fd-grid-4">
        ${fdMetricLine(
          '外資台指期未平倉淨額',
          fdSigned(dayTx?.traders?.foreign?.oi_net_lots),
          fdChangeChip(dayTx?.trader_changes?.foreign?.oi_net_lots, '口'),
          dayTx?.date || '',
          fdTone(dayTx?.traders?.foreign?.oi_net_lots)
        )}
        ${fdMetricLine(
          '三大法人台指期未平倉淨額',
          fdSigned(txTotal.oi_net_lots),
          fdChangeChip(dayTx?.trader_changes?.total?.oi_net_lots, '口'),
          dayTx?.date || '',
          fdTone(txTotal.oi_net_lots)
        )}
        ${fdMetricLine(
          '夜盤三大法人買賣超',
          fdSigned(nightTotal.net_lots),
          '',
          `${nightTx?.date || ''} · 期交所公告值`,
          fdTone(nightTotal.net_lots)
        )}
        ${fdRetailSummary(retailDash, retail)}
      </div>

      <div class="fd-grid fd-focus-grid">
        ${fdRetailChart(retailDash)}
        <section class="fd-panel fd-read-panel">
          <div class="fd-panel-title">今日解讀</div>
          <div class="fd-panel-meta">${retailDash?.date || fd.date || '等待更新'}</div>
          <div class="fd-read-text">${fdMarketReadNote(retailDash, pc, fearGreed)}</div>
          <div class="fd-read-hint">這裡只判斷市場情緒是否過熱；進出仍回到價格突破、量增回測與持倉紀律。</div>
        </section>
      </div>

      <div class="fd-grid fd-market-flow">
        ${fdTable(
          '台指期法人多空（日盤）',
          `${dayTx?.date || '等待更新'} · ${dayTx?.source || 'TAIFEX'}`,
          dayHeaders,
          fdTraderRows(dayTx)
        )}
        ${fdTable(
          '三大法人現貨買賣超金額',
          `${stock?.date || '等待 TWSE 更新'} · ${stock?.source || 'TWSE'} · 單位：億元`,
          stockHeaders,
          stock ? fdStockRows(stock) : '<tr><td colspan="5" style="text-align:center;color:var(--text3)">尚無 TWSE 現貨法人金額資料</td></tr>'
        )}
        ${fdTable(
          '台指期法人多空（夜盤）',
          `${nightTx?.date || '等待更新'} · ${nightTx?.source || 'TAIFEX'}`,
          nightHeaders,
          fdNightRows(nightTx),
          'fd-compact-panel'
        )}
      </div>

      <div class="fd-grid fd-grid-3">
        <section class="fd-panel fd-compact-panel">
          <div class="fd-panel-title">散戶情緒摘要</div>
          <div class="fd-panel-meta">${retailDash?.date || retail?.date || '等待更新'} · ${retailDash?.source || retail?.source || 'TAIFEX'}</div>
          <div class="table-scroll">
            <table class="fd-table">
              <thead><tr><th></th><th>今日</th><th>增減</th><th>趨勢</th></tr></thead>
              <tbody>${fdSentimentRows(retailDash)}</tbody>
            </table>
          </div>
        </section>
        <section class="fd-panel">
          <div class="fd-panel-title">PC Ratio</div>
          <div class="fd-sentiment">
            ${fdMetric('成交量 P/C', pc?.volume_ratio == null ? '—' : `${fdNum(pc.volume_ratio, 2)}%`, pc?.date || '', fdTone(pc?.volume_ratio - 100))}
            ${fdMetric('未平倉 P/C', pc?.open_interest_ratio == null ? '—' : `${fdNum(pc.open_interest_ratio, 2)}%`, pc?.source || '', fdTone(pc?.open_interest_ratio - 100))}
          </div>
        </section>
        <section class="fd-panel">
          <div class="fd-panel-title">資料狀態</div>
          <div class="fd-note">
            <div>更新：${updated}</div>
            <div>資料日：${fd.date || '等待更新'}</div>
            <div>來源：${fd.source || 'TAIFEX + CNN + TWSE'}</div>
          </div>
        </section>
      </div>
    </div>`;
}
