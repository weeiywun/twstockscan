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

  const saSortCol = window._saSortCol || 'composite_score';
  const saSortAsc = window._saSortAsc !== undefined ? window._saSortAsc : false;

  function saCompare(a, b) {
    const va = a[saSortCol] != null ? a[saSortCol] : '';
    const vb = b[saSortCol] != null ? b[saSortCol] : '';
    const isDate = /^\d{4}-\d{2}-\d{2}/.test(va) || /^\d{4}-\d{2}-\d{2}/.test(vb);
    const numA = parseFloat(va), numB = parseFloat(vb);
    const cmp = isDate
      ? String(va).localeCompare(String(vb))
      : (!isNaN(numA) && !isNaN(numB))
        ? numA - numB
        : String(va).localeCompare(String(vb));
    return saSortAsc ? cmp : -cmp;
  }

  function saSort(col) {
    if (window._saSortCol === col) window._saSortAsc = !window._saSortAsc;
    else { window._saSortCol = col; window._saSortAsc = false; }
    renderStrategy();
  }
  window.saSort = saSort;

  function sortIcon(col) {
    const isActive = saSortCol === col;
    return `<span class="sort-icon">${isActive ? (saSortAsc ? '↑' : '↓') : '·'}</span>`;
  }

  const active  = (saData.active  || []).slice().sort(saCompare);
  const expired = saData.expired || [];

  const buyCount   = active.filter(s => s.recommendation === 'buy').length;
  const watchCount = active.filter(s => s.recommendation === 'watch').length;
  const avoidCount = active.filter(s => s.recommendation === 'avoid').length;

  const top3 = active.slice(0, 3);
  const rest  = active.slice(3);

  const recLabel = { buy: '積極買進', watch: '觀察', avoid: '迴避' };

  function scoreColor(score) {
    if (score >= 70) return 'var(--green)';
    if (score >= 55) return 'var(--amber)';
    return 'var(--text2)';
  }

  function revGradeBadge(grade) {
    const cfg = {
      S: { bg: 'rgba(46,213,115,0.15)', color: 'var(--green)',  text: 'S 雙增加速' },
      A: { bg: 'rgba(46,213,115,0.10)', color: 'var(--green)',  text: 'A 年月雙增' },
      B: { bg: 'rgba(240,136,62,0.12)', color: 'var(--amber)',  text: 'B 長穩短弱' },
      C: { bg: 'rgba(240,136,62,0.12)', color: 'var(--amber)',  text: 'C 谷底翻揚' },
      D: { bg: 'rgba(248,81,73,0.10)',  color: 'var(--red)',    text: 'D 年月雙減' },
    };
    const c = cfg[grade] || { bg: 'var(--bg3)', color: 'var(--text3)', text: grade || '—' };
    return `<span style="font-size:10px;padding:2px 7px;border-radius:4px;background:${c.bg};color:${c.color};font-weight:600">${c.text}</span>`;
  }

  function actionBadge(log, multiplier) {
    if (!log || log === '基礎計分') return '';
    const isBoost   = multiplier > 1;
    const bg    = isBoost ? 'rgba(46,213,115,0.12)' : 'rgba(248,81,73,0.10)';
    const color = isBoost ? 'var(--green)' : 'var(--red)';
    return `<div style="font-size:10px;padding:4px 8px;border-radius:5px;background:${bg};color:${color};margin-top:6px">${log}</div>`;
  }

  // ── 大卡片（前3名）
  function renderCard(s) {
    const market   = s.market || guessMarket(s.ticker);
    const tvSymbol = `${market}:${s.ticker}`;
    const pnlClass = s.pnl_pct >= 0 ? 'sa-pnl-pos' : 'sa-pnl-neg';
    const pnlSign  = s.pnl_pct >= 0 ? '+' : '';

    const repeatBadge = s.repeat
      ? `<span class="sa-repeat-badge">↺ 第${s.repeat_count}次</span>` : '';

    // v1.6 評分維度
    const dims = [
      { label: '新聞事件', val: s.ai_scores?.ai_news_score },
      { label: '產業趨勢', val: s.ai_scores?.ai_industry_score },
      { label: '籌碼趨勢', val: s.quant_scores?.trend_score },
      { label: '籌碼集中', val: s.quant_scores?.chip_score },
      { label: '營收動能', val: s.quant_scores?.rev_score },
    ];
    const scoreRows = dims.map(({ label, val }) => {
      const v = val ?? 5;
      return `<div class="sa-bar-row">
        <span class="sa-bar-label">${label}</span>
        <div class="sa-bar-track">
          <div class="sa-bar-fill" style="width:${Math.round(v * 10)}%"></div>
        </div>
        <span class="sa-bar-val">${v}</span>
      </div>`;
    }).join('');

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
          <span class="sa-days-badge">入選 ${s.trigger_date || s.entry_date || '—'}</span>
        </div>
      </div>

      <div class="sa-score-section">
        <div style="flex:0 0 auto;text-align:center">
          <div class="sa-composite" style="color:${scoreColor(s.composite_score)}">${s.composite_score}</div>
          <div class="sa-composite-label">綜合評分</div>
          <div style="margin-top:6px">${revGradeBadge(s.rev_grade)}</div>
        </div>
        <div class="sa-score-bars">${scoreRows}</div>
      </div>

      ${actionBadge(s.action_log, s.multiplier)}
      <div class="sa-summary">${s.summary}</div>
      <div class="sa-risk"><span style="flex-shrink:0">⚠</span> ${s.risk}</div>

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

  // ── 縮排列表（第4名以後）
  function renderRestRows(stocks) {
    return stocks.map((s, i) => {
      const rank     = i + 4;
      const market   = s.market || guessMarket(s.ticker);
      const tvSymbol = `${market}:${s.ticker}`;
      const pnlClass = s.pnl_pct >= 0 ? 'sa-pnl-pos' : 'sa-pnl-neg';
      const pnlSign  = s.pnl_pct >= 0 ? '+' : '';

      const dims = [
        { label: '新聞事件', val: s.ai_scores?.ai_news_score },
        { label: '產業趨勢', val: s.ai_scores?.ai_industry_score },
        { label: '籌碼趨勢', val: s.quant_scores?.trend_score },
        { label: '籌碼集中', val: s.quant_scores?.chip_score },
        { label: '營收動能', val: s.quant_scores?.rev_score },
      ];
      const expandBars = dims.map(({ label, val }) => {
        const v = val ?? 5;
        return `<div class="sa-bar-row">
          <span class="sa-bar-label">${label}</span>
          <div class="sa-bar-track"><div class="sa-bar-fill" style="width:${Math.round(v * 10)}%"></div></div>
          <span class="sa-bar-val">${v}</span>
        </div>`;
      }).join('');

      return `
        <tr onclick="toggleExpand('sa-${s.ticker}')" id="row-sa-${s.ticker}" style="cursor:pointer">
          <td style="font-family:var(--mono);font-size:11px;color:var(--text3);width:28px">${rank}</td>
          <td>
            <a href="https://www.tradingview.com/chart/?symbol=${tvSymbol}"
              onclick="openTV('${tvSymbol}', event)"
              style="text-decoration:none">
              <span class="stock-code" style="font-size:12px;display:flex;align-items:center;gap:3px">
                ${s.ticker}<span style="font-size:9px;opacity:.45;font-family:var(--mono)">↗</span>
              </span>
              <span style="font-size:12px;color:var(--text2)">${s.name}</span>
            </a>
            <div style="font-size:10px;color:var(--text3)">${s.industry || ''}</div>
          </td>
          <td><span style="font-family:var(--mono);font-size:14px;font-weight:700;color:${scoreColor(s.composite_score)}">${s.composite_score}</span></td>
          <td><span class="sa-rec-badge ${s.recommendation}" style="font-size:10px">${recLabel[s.recommendation]}</span></td>
          <td>${revGradeBadge(s.rev_grade)}</td>
          <td style="font-family:var(--mono);font-size:12px;color:var(--text3)">${s.trigger_date || s.entry_date || '—'}</td>
          <td style="font-family:var(--mono);font-size:12px">${s.entry_price.toFixed(1)}</td>
          <td>
            <span style="font-family:var(--mono);font-size:12px">${s.current_price.toFixed(1)}</span>
            <span class="${pnlClass}" style="font-family:var(--mono);font-size:11px;margin-left:4px">${pnlSign}${s.pnl_pct.toFixed(2)}%</span>
          </td>
        </tr>
        <tr class="expand-row" id="expand-sa-${s.ticker}" style="display:none">
          <td colspan="8">
            <div class="expand-content">
              <div class="expand-section" style="flex:2;min-width:180px">
                <h4>AI 評分明細</h4>
                <div style="margin-bottom:8px">${expandBars}</div>
                ${s.action_log && s.action_log !== '基礎計分' ? actionBadge(s.action_log, s.multiplier) : ''}
                <div style="font-size:11px;color:var(--text3);margin-top:6px">
                  基礎分 ${s.base_score} × ${s.multiplier} = <b style="color:${scoreColor(s.composite_score)}">${s.composite_score}</b>
                </div>
              </div>
              <div class="expand-section" style="flex:3;min-width:200px">
                <h4>AI 分析</h4>
                <div style="font-size:12px;color:var(--text2);line-height:1.7;margin-bottom:6px">${s.summary}</div>
                <div style="font-size:11px;color:var(--text3);display:flex;gap:5px;align-items:flex-start">
                  <span style="flex-shrink:0">⚠</span>${s.risk}
                </div>
              </div>
              <div class="expand-section" style="flex:1;min-width:100px">
                <h4>操作</h4>
                <a href="https://tw.stock.yahoo.com/quote/${s.ticker}" target="_blank"
                  onclick="event.stopPropagation()"
                  style="display:block;text-align:center;background:var(--bg3);border:1px solid var(--border);color:var(--text2);padding:8px 14px;border-radius:6px;font-size:12px;text-decoration:none;margin-bottom:6px">
                  Yahoo 股市 ↗
                </a>
              </div>
            </div>
          </td>
        </tr>`;
    }).join('');
  }

  // ── 組合 active 區塊
  let activeHTML = '';
  if (active.length === 0) {
    activeHTML = `<div class="coming-soon" style="padding:48px 20px">
      <div class="coming-icon">◎</div>
      <div class="coming-title">等待觸發</div>
      <div class="coming-desc">籌碼集中入池標的觸發量增訊號後自動啟動分析。</div>
    </div>`;
  } else {
    const top3HTML = top3.length > 0 ? `
      <div class="sa-section-label">✦ AI 精選前 ${top3.length} 名</div>
      <div class="sa-cards-grid">${top3.map(renderCard).join('')}</div>` : '';

    const restHTML = rest.length > 0 ? `
      <div class="sa-section-label" style="margin-top:20px">其餘追蹤標的</div>
      <div class="table-wrap" style="margin-top:8px">
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th style="width:28px">#</th>
                <th onclick="saSort('ticker')" style="cursor:pointer">代號 / 名稱${sortIcon('ticker')}</th>
                <th onclick="saSort('composite_score')" style="cursor:pointer">評分${sortIcon('composite_score')}</th>
                <th onclick="saSort('recommendation')" style="cursor:pointer">建議${sortIcon('recommendation')}</th>
                <th onclick="saSort('rev_grade')" style="cursor:pointer">營收等級${sortIcon('rev_grade')}</th>
                <th onclick="saSort('trigger_date')" style="cursor:pointer">入選日${sortIcon('trigger_date')}</th>
                <th onclick="saSort('entry_price')" style="cursor:pointer">入選價${sortIcon('entry_price')}</th>
                <th onclick="saSort('pnl_pct')" style="cursor:pointer">現價 / 損益${sortIcon('pnl_pct')}</th>
              </tr>
            </thead>
            <tbody>${renderRestRows(rest)}</tbody>
          </table>
        </div>
      </div>` : '';

    activeHTML = top3HTML + restHTML;
  }

  // ── 歷史區
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
              <th>代號 / 名稱</th><th>入選日</th><th>入選收盤</th>
              <th>評分</th><th>現價</th><th>損益</th>
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
