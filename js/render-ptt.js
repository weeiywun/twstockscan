// ════════════════════════════════════════════════════
//  PTT Stock 版 [標的] 鄉民選股
// ════════════════════════════════════════════════════

const SENTIMENT_LABEL = { bullish: '多', bearish: '空', neutral: '中性' };
const SENTIMENT_STYLE = {
  bullish: 'color:var(--market-up);border-color:rgba(var(--market-up-rgb,34,197,94),0.45)',
  bearish: 'color:var(--market-down);border-color:rgba(var(--market-down-rgb,239,68,68),0.45)',
  neutral: 'color:var(--text3);border-color:rgba(136,136,136,0.35)',
};

function _pttSentimentBadge(sentiment) {
  if (!sentiment || !SENTIMENT_LABEL[sentiment]) return '';
  return `<span class="tag-badge" style="${SENTIMENT_STYLE[sentiment]}">${SENTIMENT_LABEL[sentiment]}</span>`;
}

function _pttMarketBadge(market) {
  if (market === 'US') return `<span class="tag-badge" style="color:#6366f1;border-color:rgba(99,102,241,0.4);font-size:9px">US</span>`;
  return '';
}

let pttSortCol = 'latest_date';
let pttSortAsc  = false;

function pttSort(col) {
  if (pttSortCol === col) pttSortAsc = !pttSortAsc;
  else { pttSortCol = col; pttSortAsc = false; }
  const strat = STRATEGIES.find(s => s.id === 'ptt_stock');
  renderPttStock(strat, document.getElementById('mainContent'));
}

function renderPttStock(strat, main) {
  const pd = DATA.ptt_data;
  const stocks = Object.values(pd?.stocks || {});
  const posts  = pd?.posts  || [];

  if (!stocks.length) {
    main.innerHTML = `<div class="coming-soon">
      <div class="coming-icon">${strat.icon}</div>
      <div class="coming-title">${strat.name}</div>
      <div class="coming-desc">資料尚未產生，請等待每日 17:00 自動更新，或至 GitHub Actions → <b>每日選股掃描</b> → <b>Run workflow</b> 手動執行。</div>
    </div>`;
    return;
  }

  // 排序
  const sorted = stocks.slice().sort((a, b) => {
    let va = a[pttSortCol], vb = b[pttSortCol];
    if (va == null) va = typeof vb === 'number' ? -Infinity : '';
    if (vb == null) vb = typeof va === 'number' ? -Infinity : '';
    if (va < vb) return pttSortAsc ? -1 : 1;
    if (va > vb) return pttSortAsc ? 1 : -1;
    return 0;
  });

  const pttSortIcon = col => `<span class="sort-icon">${pttSortCol === col ? (pttSortAsc ? '↑' : '↓') : '·'}</span>`;

  // 摘要數字
  const totalBullish = stocks.reduce((n, s) => n + s.bullish, 0);
  const totalBearish = stocks.reduce((n, s) => n + s.bearish, 0);
  const mostMentioned = stocks.slice().sort((a, b) => b.posts_30d - a.posts_30d)[0];

  function postsByStock(stockId) {
    return posts
      .filter(p => p.stock_id === stockId)
      .sort((a, b) => (b.date || '').localeCompare(a.date || ''));
  }

  function stockRow(s) {
    const sid = s.stock_id;
    const isTW = !isNaN(parseInt(sid, 10));
    const stockCodeHTML = isTW
      ? `<span class="stock-code">${sid}</span>`
      : `<span class="stock-code" style="letter-spacing:0.02em">${sid}</span>`;
    const marketBadge = _pttMarketBadge(isTW ? 'TW' : 'US');
    const bull = s.bullish, bear = s.bearish, neut = s.neutral + (s.unknown || 0);
    const sentHTML = [
      bull ? `<span class="tag-badge" style="${SENTIMENT_STYLE.bullish}">多 ${bull}</span>` : '',
      bear ? `<span class="tag-badge" style="${SENTIMENT_STYLE.bearish}">空 ${bear}</span>` : '',
      neut ? `<span class="tag-badge" style="${SENTIMENT_STYLE.neutral}">中 ${neut}</span>` : '',
    ].join('');
    const pushColor = s.net_pushes >= 0 ? 'var(--market-up)' : 'var(--market-down)';
    const pushSign  = s.net_pushes >= 0 ? '+' : '';

    return `
      <tr onclick="toggleExpand('ptt-${sid}')" id="row-ptt-${sid}" style="cursor:pointer">
        <td>
          <div style="display:flex;align-items:center;gap:5px">
            ${stockCodeHTML}${marketBadge}
          </div>
          <div class="stock-name">${s.stock_name !== sid ? (s.stock_name || '') : ''}</div>
        </td>
        <td style="font-family:var(--mono);font-weight:600">${s.posts_30d}</td>
        <td><div class="tag-cell">${sentHTML || '<span style="color:var(--text3)">—</span>'}</div></td>
        <td style="font-family:var(--mono);color:${pushColor}">${pushSign}${s.net_pushes}</td>
        <td style="font-family:var(--mono);font-size:12px;color:var(--text3)">${s.latest_date || '—'}</td>
      </tr>
      <tr class="expand-row" id="expand-ptt-${sid}" style="display:none">
        <td colspan="5" style="padding:0">
          <div class="expand-flat" style="padding:10px 16px 14px">
            <table style="width:100%;border-collapse:collapse;font-size:12px">
              <thead>
                <tr style="color:var(--text3);font-size:11px">
                  <th style="padding:4px 8px 6px 0;text-align:left;font-weight:500">日期</th>
                  <th style="padding:4px 8px 6px;text-align:left;font-weight:500">多空</th>
                  <th style="padding:4px 8px 6px;text-align:right;font-weight:500">推</th>
                  <th style="padding:4px 0 6px 8px;text-align:left;font-weight:500">標題</th>
                </tr>
              </thead>
              <tbody>
                ${postsByStock(sid).map(p => `
                  <tr style="border-top:1px solid var(--border)">
                    <td style="padding:6px 8px 6px 0;color:var(--text3);white-space:nowrap">${p.date || '—'}</td>
                    <td style="padding:6px 8px">${_pttSentimentBadge(p.sentiment)}</td>
                    <td style="padding:6px 8px;font-family:var(--mono);text-align:right;color:var(--market-up)">${p.pushes > 0 ? '+' + p.pushes : '—'}</td>
                    <td style="padding:6px 0 6px 8px">
                      <a href="${p.url}" target="_blank" rel="noopener"
                        style="color:var(--text1);text-decoration:none;font-size:12px;line-height:1.5"
                        onclick="event.stopPropagation()"
                        onmouseover="this.style.color='var(--blue)'" onmouseout="this.style.color='var(--text1)'">
                        ${p.title}
                      </a>
                    </td>
                  </tr>`).join('')}
              </tbody>
            </table>
          </div>
        </td>
      </tr>`;
  }

  main.innerHTML = `
    <div class="strategy-panel active">
      <div class="strat-header">
        <div class="strat-title">${strat.icon} ${strat.name}</div>
        <div class="strat-desc">${strat.description}</div>
      </div>

      <div class="summary-row">
        <div class="summary-card">
          <div class="summary-label">標的數</div>
          <div class="summary-value green">${stocks.length}</div>
          <div class="summary-sub">近 30 天出現過</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">文章總數</div>
          <div class="summary-value">${posts.length}</div>
          <div class="summary-sub">30 天 [標的] 篇數</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">多 / 空</div>
          <div class="summary-value" style="font-size:16px">
            <span style="color:var(--market-up)">${totalBullish}</span>
            <span style="font-size:12px;color:var(--text3);margin:0 4px">/</span>
            <span style="color:var(--market-down)">${totalBearish}</span>
          </div>
          <div class="summary-sub">篇有明確方向</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">最熱標的</div>
          <div class="summary-value amber" style="font-size:16px">${mostMentioned ? mostMentioned.stock_id : '—'}</div>
          <div class="summary-sub">${mostMentioned ? mostMentioned.posts_30d + ' 篇' : ''}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">資料日期</div>
          <div class="summary-value" style="font-size:16px;font-family:var(--mono)">${pd.updated || '—'}</div>
          <div class="summary-sub">PTT Stock 版</div>
        </div>
      </div>

      <div class="table-wrap">
        <div class="table-toolbar">
          <span class="table-title">標的熱度（近 30 天）</span>
          <span class="updated-tag">資料：${pd.updated || '—'}</span>
        </div>
        <div class="table-scroll">
          <table id="pttTable">
            <thead>
              <tr>
                <th>代號 / 名稱</th>
                <th onclick="pttSort('posts_30d')" style="cursor:pointer">篇數${pttSortIcon('posts_30d')}</th>
                <th>多空分佈</th>
                <th onclick="pttSort('net_pushes')" style="cursor:pointer">淨推文${pttSortIcon('net_pushes')}</th>
                <th onclick="pttSort('latest_date')" style="cursor:pointer">最新日期${pttSortIcon('latest_date')}</th>
              </tr>
            </thead>
            <tbody>${sorted.map(stockRow).join('')}</tbody>
          </table>
        </div>
      </div>
    </div>`;
}
