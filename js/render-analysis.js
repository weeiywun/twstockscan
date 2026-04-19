// ════════════════════════════════════════════════════
//  標的分析：渲染器
// ════════════════════════════════════════════════════
function renderStockAnalysis(strat, main) {
  const saData = DATA.stock_analysis_data;

  if (!saData) {
    main.innerHTML = `
      <div class="strategy-panel active">
        <div class="strat-header">
          <div class="strat-title">${strat.icon} ${strat.name}</div>
          <div class="strat-desc">${strat.description}</div>
        </div>
        <div class="coming-soon" style="padding:64px 20px">
          <div class="coming-icon">◎</div>
          <div class="coming-title">等待觸發</div>
          <div class="coming-desc">籌碼集中入池標的首次觸發量增訊號後自動啟動 AI 分析。</div>
        </div>
      </div>`;
    const grid = document.getElementById('watchlistGrid');
    if (grid) grid.innerHTML = renderWatchlist();
    return;
  }

  const active  = saData.active  || [];
  const expired = saData.expired || [];

  const buyCount   = active.filter(s => s.recommendation === 'buy').length;
  const watchCount = active.filter(s => s.recommendation === 'watch').length;
  const avoidCount = active.filter(s => s.recommendation === 'avoid').length;

  // 按 trigger_date 分組，組內依 composite_score 降序
  const groups = {};
  active.forEach(s => {
    if (!groups[s.trigger_date]) groups[s.trigger_date] = [];
    groups[s.trigger_date].push(s);
  });
  Object.values(groups).forEach(g => g.sort((a, b) => b.composite_score - a.composite_score));
  const sortedDates = Object.keys(groups).sort((a, b) => b.localeCompare(a));

  const recLabel = { buy: '積極買進', watch: '觀察', avoid: '迴避' };

  function scoreColor(score) {
    if (score >= 70) return 'var(--green)';
    if (score >= 55) return 'var(--amber)';
    return 'var(--text2)';
  }

  function renderCard(s) {
    const market    = s.market || guessMarket(s.ticker);
    const tvSymbol  = `${market}:${s.ticker}`;
    const pnlClass  = s.pnl_pct >= 0 ? 'sa-pnl-pos' : 'sa-pnl-neg';
    const pnlSign   = s.pnl_pct >= 0 ? '+' : '';

    const repeatBadge = s.repeat
      ? `<span class="sa-repeat-badge">↺ 第${s.repeat_count}次</span>` : '';

    const analysisMeta = s.ai_analysis_date && s.ai_analysis_date !== s.trigger_date
      ? `<div class="sa-analysis-date">分析日：${s.ai_analysis_date}（沿用上次結果）</div>` : '';

    const scoreRows = Object.entries(s.scores || {}).map(([label, val]) => `
      <div class="sa-bar-row">
        <span class="sa-bar-label">${label}</span>
        <div class="sa-bar-track">
          <div class="sa-bar-fill" style="width:${Math.round(val * 10)}%"></div>
        </div>
        <span class="sa-bar-val">${val}</span>
      </div>`).join('');

    return `<div class="sa-card">
      <div class="sa-card-top">
        <div>
          <div class="sa-stock-header">
            <a href="https://www.tradingview.com/chart/?symbol=${tvSymbol}"
              onclick="openTV('${tvSymbol}', event)"
              style="text-decoration:none;display:flex;align-items:center;gap:4px">
              <span class="stock-code">${s.ticker}</span>
              <span style="font-size:9px;opacity:.45;font-family:var(--mono)">↗</span>
            </a>
            <span class="stock-name">${s.name}</span>
            ${repeatBadge}
          </div>
          <div style="font-size:11px;color:var(--text3);margin-top:2px">${s.industry || ''}</div>
        </div>
        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:5px;flex-shrink:0">
          <span class="sa-rec-badge ${s.recommendation}">${recLabel[s.recommendation] || s.recommendation}</span>
          <span class="sa-days-badge">剩 ${s.days_remaining} 天</span>
        </div>
      </div>

      <div class="sa-score-section">
        <div style="flex:0 0 auto;text-align:center">
          <div class="sa-composite" style="color:${scoreColor(s.composite_score)}">${s.composite_score}</div>
          <div class="sa-composite-label">綜合評分</div>
        </div>
        <div class="sa-score-bars">${scoreRows}</div>
      </div>

      <div class="sa-summary">${s.summary}</div>
      <div class="sa-risk"><span style="flex-shrink:0">⚠</span> ${s.risk}</div>
      ${analysisMeta}

      <div class="sa-price-row">
        <span>入選</span>
        <span class="sa-price-val">${s.entry_price.toFixed(1)}</span>
        <span style="color:var(--border2)">|</span>
        <span>現價</span>
        <span class="sa-price-val">${s.current_price.toFixed(1)}</span>
        <span class="${pnlClass}">${pnlSign}${s.pnl_pct.toFixed(2)}%</span>
      </div>
    </div>`;
  }

  const activeHTML = sortedDates.length === 0
    ? `<div class="coming-soon" style="padding:48px 20px">
        <div class="coming-icon">◎</div>
        <div class="coming-title">等待觸發</div>
        <div class="coming-desc">籌碼集中入池標的觸發量增訊號後自動啟動分析。</div>
      </div>`
    : sortedDates.map(date => `
        <div class="sa-date-group">
          <div class="sa-date-header">
            ${date} 入選
            <span class="sa-date-count">${groups[date].length} 支</span>
          </div>
          <div class="sa-cards-grid">
            ${groups[date].map(renderCard).join('')}
          </div>
        </div>`).join('');

  // 歷史區
  let historyHTML = '';
  if (expired.length > 0) {
    const histRows = expired.map(s => {
      const pnlClass = s.pnl_pct >= 0 ? 'sa-pnl-pos' : 'sa-pnl-neg';
      const pnlSign  = s.pnl_pct >= 0 ? '+' : '';
      return `<tr>
        <td>
          <span class="stock-code" style="font-size:12px">${s.ticker}</span>
          <span style="font-size:12px;color:var(--text2);margin-left:5px">${s.name}</span>
        </td>
        <td style="font-family:var(--mono);font-size:12px;color:var(--text3)">${s.entry_date}</td>
        <td style="font-family:var(--mono);font-size:12px">${s.entry_price.toFixed(1)}</td>
        <td><span style="font-family:var(--mono);font-size:12px;color:${scoreColor(s.composite_score)};font-weight:600">${s.composite_score}</span></td>
        <td style="font-family:var(--mono);font-size:12px">${s.current_price.toFixed(1)}</td>
        <td><span class="${pnlClass}" style="font-family:var(--mono);font-size:12px">${pnlSign}${s.pnl_pct.toFixed(2)}%</span></td>
      </tr>`;
    }).join('');

    historyHTML = `<div class="sa-history-wrap">
      <div class="sa-history-header">
        <span class="sa-history-title">歷史紀錄（保留一個月）</span>
        <span class="sa-history-count">${expired.length} 筆</span>
      </div>
      <div class="table-scroll">
        <table class="sa-history-table">
          <thead>
            <tr>
              <th>代號 / 名稱</th>
              <th>入選日</th>
              <th>入選收盤</th>
              <th>評分</th>
              <th>現價</th>
              <th>損益</th>
            </tr>
          </thead>
          <tbody>${histRows}</tbody>
        </table>
      </div>
    </div>`;
  }

  main.innerHTML = `
    <div class="strategy-panel active">
      <div class="strat-header">
        <div class="strat-title">${strat.icon} ${strat.name}</div>
        <div class="strat-desc">${strat.description}</div>
      </div>

      <div class="summary-row">
        <div class="summary-card">
          <div class="summary-label">觀察中</div>
          <div class="summary-value green">${active.length}</div>
          <div class="summary-sub">支標的</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">積極買進</div>
          <div class="summary-value amber">${buyCount}</div>
          <div class="summary-sub">AI 推薦</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">觀察 / 迴避</div>
          <div class="summary-value" style="font-size:18px">${watchCount} / ${avoidCount}</div>
          <div class="summary-sub">持續追蹤中</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">更新時間</div>
          <div class="summary-value" style="font-size:16px;font-family:var(--mono)">${saData.last_updated}</div>
          <div class="summary-sub">盤後自動更新</div>
        </div>
      </div>

      ${activeHTML}
      ${historyHTML}
    </div>`;

  const grid = document.getElementById('watchlistGrid');
  if (grid) grid.innerHTML = renderWatchlist();
}

// ════════════════════════════════════════════════════
