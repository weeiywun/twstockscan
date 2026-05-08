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

function fdBiasTone(label) {
  if (label === '偏多') return 'pos';
  if (label === '偏空') return 'neg';
  return 'flat';
}

function fdGaugeCard({ eyebrow, title, value, sub, gauge, tone = 'flat', left = 'FEAR', center = 'NEUTRAL', right = 'GREED' }) {
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
    </section>`;
}

function fdBiasComponentRows(marketBias) {
  const rows = marketBias?.components || [];
  if (!rows.length) return '<tr><td colspan="4" style="text-align:center;color:var(--text3)">尚無評分細項</td></tr>';
  return rows.map(row => `
    <tr>
      <td>${row.label || '—'}</td>
      <td class="mono">${row.value == null ? '—' : `${fdSigned(row.value, row.unit === '%' ? 2 : 0)}${row.unit || ''}`}</td>
      <td class="mono">${row.weight || 0}%</td>
      <td class="mono ${fdTone(row.score)}">${fdSigned(row.score, 1)}</td>
    </tr>`).join('');
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
        <td class="mono">${fdNum(item.oi_long_lots)}</td>
        <td class="mono">${fdNum(item.oi_short_lots)}</td>
        <td class="mono ${fdTone(item.oi_net_lots)}">
          <span class="fd-inline-value">${fdSigned(item.oi_net_lots)}${fdChangeChip(oiChange, '口')}</span>
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
  const rows = (stock?.history || []).slice(0, 4);
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

function fdTable(title, meta, headers, body) {
  return `
    <section class="fd-panel">
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
    return '<tr><td colspan="4" style="text-align:center;color:var(--text3)">尚無散戶多空比資料</td></tr>';
  }
  return rows.map(row => `
    <tr>
      <td>${row.label || '—'}</td>
      <td class="mono ${fdTone(row.today)}">${fdSentimentValue(row, 'today')}</td>
      <td class="mono ${fdTone(row.previous)}">${fdSentimentValue(row, 'previous')}</td>
      <td class="mono ${fdTrendTone(row.trend)}">${row.trend || '—'}</td>
    </tr>`).join('');
}

function renderFutureDashboard(strat, main) {
  const fd = DATA.futures_dashboard_data || {};
  const dayTx = fd.futures?.day_session?.tx;
  const nightTx = fd.futures?.night_session?.tx;
  const retail = fd.sentiment?.retail_long_short;
  const retailDash = fd.sentiment?.retail_dashboard;
  const pc = fd.sentiment?.pc_ratio;
  const stock = fd.stock_institutional;
  const bias = fd.summary?.bias || '等待更新';
  const marketBias = fd.summary?.market_bias || {};
  const fearGreed = fd.us_sentiment?.fear_greed || {};
  const updated = fd.updated ? fd.updated.slice(0, 16).replace('T', ' ') : '尚未更新';
  const txTotal = dayTx?.traders?.total || {};
  const nightTotal = nightTx?.traders?.total || {};

  const dayHeaders = ['法人', '買賣超(口)', '未平倉多(口)', '未平倉空(口)', '未平倉淨(口)'];
  const nightHeaders = ['法人', '夜盤買賣超(口)'];
  const stockHeaders = ['日期', '外資(億)', '投信(億)', '自營商(億)', '合計(億)'];

  main.innerHTML = `
    <div class="strategy-panel active">
      <div class="strat-header fd-header">
        <div>
          <div class="strat-title">${strat.icon} FUTURE DASHBOARD</div>
          <div class="strat-desc">${strat.description}</div>
        </div>
      </div>

      <div class="fd-hero-grid">
        ${fdGaugeCard({
          eyebrow: 'MARKET BIAS',
          title: '台股期權籌碼溫度',
          value: bias,
          sub: `Score ${fdSigned(marketBias.score, 1)} · Confidence ${fdNum(marketBias.confidence, 1)}`,
          gauge: marketBias.gauge,
          tone: fdBiasTone(bias),
          left: 'BEAR',
          center: 'NEUTRAL',
          right: 'BULL'
        })}
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
        <section class="fd-panel fd-bias-detail">
          <div class="fd-panel-title">Bias 評分依據</div>
          <div class="fd-panel-meta">${marketBias.definition || '等待資料更新'}</div>
          <div class="table-scroll">
            <table class="fd-table fd-bias-table">
              <thead><tr><th>項目</th><th>數值</th><th>權重</th><th>分數</th></tr></thead>
              <tbody>${fdBiasComponentRows(marketBias)}</tbody>
            </table>
          </div>
        </section>
      </div>

      <div class="fd-grid fd-grid-6">
        ${fdIndexMetric('TXF_NEAR', '台指近全')}
        ${fdIndexMetric('TAIEX', '台灣加權指數')}
        ${fdIndexMetric('TPEX', '櫃買加權指數')}
        ${fdIndexMetric('NASDAQ', '那斯達克')}
        ${fdIndexMetric('DOW', '道瓊')}
        ${fdIndexMetric('SOX', '費半')}
      </div>

      <div class="fd-grid fd-grid-4">
        ${fdMetricLine(
          '外資台指期未平倉淨額(口)',
          fdSigned(dayTx?.traders?.foreign?.oi_net_lots),
          fdChangeChip(dayTx?.trader_changes?.foreign?.oi_net_lots, '口'),
          dayTx?.date || '',
          fdTone(dayTx?.traders?.foreign?.oi_net_lots)
        )}
        ${fdMetricLine(
          '三大法人台指期未平倉淨額(口)',
          fdSigned(txTotal.oi_net_lots),
          fdChangeChip(dayTx?.trader_changes?.total?.oi_net_lots, '口'),
          dayTx?.date || '',
          fdTone(txTotal.oi_net_lots)
        )}
        ${fdMetric('夜盤三大法人買賣超(口)', fdSigned(nightTotal.net_lots), `${nightTx?.date || ''} · 期交所公告值`, fdTone(nightTotal.net_lots))}
        ${fdMetric('散戶多空比', retail?.ratio == null ? '—' : `${fdNum(retail.ratio, 2)}%`, retail?.date || '', fdTone(retail?.ratio, true))}
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
          fdNightRows(nightTx)
        )}
      </div>

      <div class="fd-grid fd-grid-3">
        <section class="fd-panel fd-compact-panel">
          <div class="fd-panel-title">散戶多空比</div>
          <div class="fd-panel-meta">${retailDash?.date || retail?.date || '等待更新'} · ${retailDash?.source || retail?.source || 'TAIFEX'}</div>
          <div class="table-scroll">
            <table class="fd-table">
              <thead><tr><th></th><th>今日</th><th>前一日</th><th>增減</th></tr></thead>
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
            <div>來源：${fd.source || 'TAIFEX + FinMind'}</div>
          </div>
        </section>
      </div>

    </div>`;
}
