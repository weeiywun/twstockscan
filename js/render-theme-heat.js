function themeHeatNum(value, digits = 1) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return n.toFixed(digits);
}

function themeHeatPct(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
}

function themeHeatSourcePills(labels) {
  return (labels || []).slice(0, 3).map(label => (
    `<span class="tag-badge" style="color:var(--green);background:var(--green-dim);border-color:var(--green-glow)">${label}</span>`
  )).join('');
}

function renderThemeHeat(strat, main) {
  const data = DATA.theme_heat_data || {};
  const themes = data.themes || [];
  const selected = data.selected || [];
  const topThemes = themes.slice(0, 5);
  const activeTheme = window._themeHeatFilter || (topThemes[0]?.theme || '');
  const shownRows = selected
    .filter(row => !activeTheme || (row.themes || []).includes(activeTheme))
    .slice(0, 12);

  window.setThemeHeatFilter = function setThemeHeatFilter(theme) {
    window._themeHeatFilter = theme;
    renderStrategy();
  };

  const themeCards = topThemes.map((theme, index) => {
    const reps = (theme.representatives || []).slice(0, 3)
      .map(item => `${item.stock_id} ${item.name || ''}`.trim())
      .join(' / ');
    const isActive = theme.theme === activeTheme;
    return `<button class="theme-card ${isActive ? 'active' : ''}" onclick="setThemeHeatFilter('${theme.theme}')">
      <div class="theme-rank">#${index + 1}</div>
      <div class="theme-name">${theme.theme}</div>
      <div class="theme-score">${themeHeatNum(theme.score, 0)}</div>
      <div class="theme-meta">
        <span>${theme.count} 檔</span>
        <span>量比 ${themeHeatNum(theme.avg_volume_ratio, 2)}</span>
        <span>${themeHeatPct(theme.avg_week_chg_pct)}</span>
      </div>
      <div class="theme-reps">${reps || '等待訊號'}</div>
    </button>`;
  }).join('');

  const selectedRows = shownRows.map(row => {
    const tvSymbol = getTVSymbol(row);
    return `<tr>
      <td>
        <div style="display:flex;align-items:center;gap:6px">
          <button onclick="openTV('${tvSymbol}', event)" title="Open TradingView"
            style="border:none;background:none;color:var(--green);cursor:pointer;font-family:var(--mono);font-weight:700">
            ${row.stock_id} ↗
          </button>
          <span style="font-weight:600">${row.name || ''}</span>
        </div>
        <div class="stock-industry">${row.industry || ''}</div>
      </td>
      <td>${(row.themes || []).join(' / ')}</td>
      <td class="mono">${themeHeatNum(row.theme_score, 1)}</td>
      <td class="mono">${row.close ?? '—'}</td>
      <td class="mono market-alert">${themeHeatNum(row.volume_ratio, 2)}x</td>
      <td class="mono" style="color:${Number(row.week_chg_pct) >= 0 ? 'var(--market-up)' : 'var(--market-down)'}">${themeHeatPct(row.week_chg_pct)}</td>
      <td><div class="tag-cell">${themeHeatSourcePills(row.source_labels)}</div></td>
      <td>${row.status || ''}</td>
    </tr>`;
  }).join('');

  main.innerHTML = `<section class="strategy-panel active">
    <div class="strat-header">
      <div class="strat-title">${strat.icon} ${strat.name}</div>
      <div class="strat-desc">${strat.description}</div>
    </div>

    <div class="summary-row">
      <div class="summary-card">
        <div class="summary-label">主線題材</div>
        <div class="summary-value green">${data.summary?.themes ?? 0}</div>
        <div class="summary-sub">依既有策略結果統計</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">候選標的</div>
        <div class="summary-value">${data.summary?.selected ?? 0}</div>
        <div class="summary-sub">Top 主線內精選</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">已降噪</div>
        <div class="summary-value amber">${data.summary?.excluded_by_industry ?? 0}</div>
        <div class="summary-sub">金融/食品/傳產等預設隱藏</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">資料日期</div>
        <div class="summary-value" style="font-size:16px">${data.source_date || '—'}</div>
        <div class="summary-sub">最後更新 ${(data.updated || '').slice(0, 16).replace('T', ' ')}</div>
      </div>
    </div>

    <div class="theme-grid">${themeCards || '<div class="empty-state">目前沒有題材熱度資料</div>'}</div>

    <div class="table-wrap">
      <div class="table-toolbar">
        <span class="table-title">${activeTheme || '主線'} 代表標的</span>
        <span class="updated-tag">只顯示 Top 主線內較高分標的</span>
      </div>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>代號 / 名稱</th>
              <th>題材</th>
              <th>主線分</th>
              <th>收盤價</th>
              <th>量比</th>
              <th>周漲跌</th>
              <th>來源</th>
              <th>狀態</th>
            </tr>
          </thead>
          <tbody>${selectedRows || '<tr><td colspan="8" style="text-align:center;color:var(--text3);padding:18px">此主線暫無代表標的</td></tr>'}</tbody>
        </table>
      </div>
    </div>
  </section>`;
}
