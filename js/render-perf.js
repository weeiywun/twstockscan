//  GITHUB API HELPERS
// ════════════════════════════════════════════════════
const GH_OWNER = 'weeiywun';
const GH_REPO  = 'twstockscan';
const GH_PERF  = 'data/performance.json';

function ghToken() { return localStorage.getItem('gh_token') || ''; }

async function ghWritePerf(data) {
  const token = ghToken();
  if (!token) { alert('請先設定 GitHub Token'); return false; }
  try {
    const infoRes = await fetch(
      `https://api.github.com/repos/${GH_OWNER}/${GH_REPO}/contents/${GH_PERF}`,
      { headers: { Authorization: `token ${token}`, Accept: 'application/vnd.github.v3+json' } }
    );
    if (!infoRes.ok) throw new Error('讀取 SHA 失敗，請確認 Token 權限');
    const { sha } = await infoRes.json();
    const content = btoa(unescape(encodeURIComponent(JSON.stringify(data, null, 2))));
    const writeRes = await fetch(
      `https://api.github.com/repos/${GH_OWNER}/${GH_REPO}/contents/${GH_PERF}`,
      {
        method: 'PUT',
        headers: { Authorization: `token ${token}`, 'Content-Type': 'application/json', Accept: 'application/vnd.github.v3+json' },
        body: JSON.stringify({
          message: `perf: update ${new Date().toISOString().slice(0, 10)}`,
          content, sha
        })
      }
    );
    if (!writeRes.ok) { const e = await writeRes.json(); throw new Error(e.message || '寫入失敗'); }
    return true;
  } catch(e) { alert('儲存失敗：' + e.message); return false; }
}

function openTokenModal() {
  const m = document.getElementById('tokenModal');
  if (m) { m.style.display = 'flex'; const inp = document.getElementById('tokenInput'); if(inp) inp.value = ghToken(); }
}
function closeTokenModal() {
  const m = document.getElementById('tokenModal'); if (m) m.style.display = 'none';
}
function saveToken() {
  const val = document.getElementById('tokenInput')?.value?.trim();
  if (val) localStorage.setItem('gh_token', val); else localStorage.removeItem('gh_token');
  closeTokenModal(); renderStrategy();
}

// ════════════════════════════════════════════════════
//  PERFORMANCE — 指標計算
// ════════════════════════════════════════════════════
function computePortfolioMetrics(pd) {
  const startCap = pd?.starting_capital || 450000;
  const positions = pd?.positions || [];
  const priceHistory = pd?.price_history || {};
  const today = new Date().toISOString().slice(0, 10);
  let totalCost = 0, mktValue = 0, realizedPnl = 0;
  positions.forEach(p => {
    const cost = p.shares * p.cost_price;
    totalCost += cost;
    if (p.confirmed && p.exit_price != null) {
      const val = p.shares * p.exit_price;
      mktValue += val; realizedPnl += val - cost;
    } else {
      const hist = priceHistory[p.stock_id] || {};
      const dates = Object.keys(hist).filter(d => d <= today).sort();
      const price = dates.length ? hist[dates[dates.length - 1]] : p.cost_price;
      mktValue += p.shares * price;
    }
  });
  const cash = startCap - totalCost;
  const portfolioValue = cash + mktValue;
  const returnPct = positions.length ? ((portfolioValue / startCap) - 1) * 100 : 0;
  return { startCap, portfolioValue, returnPct, realizedPnl };
}

// ════════════════════════════════════════════════════
//  PERFORMANCE — 圖表資料
// ════════════════════════════════════════════════════
function buildPerfChartData(pd) {
  if (!pd || !(pd.positions || []).length) return null;
  const startCap = pd.starting_capital || 450000;
  const positions = pd.positions || [];
  const priceHistory = pd.price_history || {};
  const allDates = new Set();
  Object.values(priceHistory).forEach(h => Object.keys(h).forEach(d => allDates.add(d)));
  positions.forEach(p => { if (p.entry_date) allDates.add(p.entry_date); });
  const sorted = [...allDates].sort();
  if (sorted.length < 2) return null;
  const totalCost = positions.reduce((s, p) => s + p.shares * p.cost_price, 0);
  const cash = startCap - totalCost;
  const totalLine = [], realizedLine = [];
  sorted.forEach(date => {
    let mktVal = 0, realVal = 0;
    positions.forEach(p => {
      const cost = p.shares * p.cost_price;
      if (date < p.entry_date) { mktVal += cost; realVal += cost; return; }
      if (p.confirmed && p.exit_date && date >= p.exit_date) {
        const ev = p.shares * p.exit_price;
        mktVal += ev; realVal += ev;
      } else {
        const hist = priceHistory[p.stock_id] || {};
        const dates = Object.keys(hist).filter(d => d <= date).sort();
        const price = dates.length ? hist[dates[dates.length - 1]] : cost / p.shares;
        mktVal += p.shares * price; realVal += cost;
      }
    });
    totalLine.push(parseFloat(((cash + mktVal) / startCap * 100 - 100).toFixed(2)));
    realizedLine.push(parseFloat(((cash + realVal) / startCap * 100 - 100).toFixed(2)));
  });
  return { labels: sorted, totalLine, realizedLine };
}

// ════════════════════════════════════════════════════
//  PERFORMANCE — 圖表初始化
// ════════════════════════════════════════════════════
let perfChart = null;
function initPerfChart(pd) {
  const canvas = document.getElementById('perfChart');
  if (!canvas || typeof Chart === 'undefined') return;
  if (perfChart) { perfChart.destroy(); perfChart = null; }
  const cd = buildPerfChartData(pd);
  perfChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: cd ? cd.labels : [],
      datasets: [
        {
          label: '總報酬（含持倉）',
          data: cd ? cd.totalLine : [],
          borderColor: '#f0883e', backgroundColor: 'transparent',
          borderWidth: 2, borderDash: [5, 4],
          pointRadius: cd && cd.labels.length < 30 ? 3 : 1, tension: 0.3,
        },
        {
          label: '已實現損益',
          data: cd ? cd.realizedLine : [],
          borderColor: '#e8a838', backgroundColor: 'rgba(232,168,56,0.1)',
          borderWidth: 2, fill: true,
          pointRadius: cd && cd.labels.length < 30 ? 3 : 1, tension: 0.3,
        }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#8b949e', font: { size: 11 } } },
        tooltip: {
          backgroundColor: '#1c2128', titleColor: '#e6edf3',
          bodyColor: '#8b949e', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1,
          callbacks: { label: ctx => ` ${ctx.dataset.label}：${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toFixed(2)}%` }
        }
      },
      scales: {
        x: { ticks: { color: '#6e7681', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' } },
        y: {
          ticks: { color: '#6e7681', font: { size: 10 }, callback: v => (v >= 0 ? '+' : '') + v.toFixed(1) + '%' },
          grid: { color: 'rgba(255,255,255,0.04)' }
        }
      }
    }
  });
}

// ════════════════════════════════════════════════════
//  PERFORMANCE — 渲染主頁
// ════════════════════════════════════════════════════
function setPerfSidebarMode(on) {
  const layout = document.querySelector('.page-layout');
  const watchlistPanel = document.getElementById('watchlistPanel');
  const journalPanel   = document.getElementById('journalPanel');
  if (on) {
    layout?.classList.add('perf-mode');
    if (watchlistPanel) watchlistPanel.style.display = 'none';
    if (journalPanel)   journalPanel.style.display   = 'block';
  } else {
    layout?.classList.remove('perf-mode');
    if (watchlistPanel) watchlistPanel.style.display = 'block';
    if (journalPanel)   journalPanel.style.display   = 'none';
  }
}

function renderPerformance(strat, main) {
  const pd = DATA.performance_data;
  const token = ghToken();
  const positions = pd?.positions || [];
  const priceHistory = pd?.price_history || {};
  const startCap = pd?.starting_capital || 450000;
  const today = new Date().toISOString().slice(0, 10);
  const active = positions.filter(p => !p.confirmed);
  const closed  = positions.filter(p => p.confirmed);
  const { portfolioValue, returnPct, realizedPnl } = computePortfolioMetrics(pd);

  function getLatestPrice(stockId) {
    const hist = priceHistory[stockId] || {};
    const dates = Object.keys(hist).filter(d => d <= today).sort();
    return dates.length ? hist[dates[dates.length - 1]] : null;
  }

  function activeRow(p) {
    const cp = getLatestPrice(p.stock_id);
    const posVal = (cp ?? p.cost_price) * p.shares;
    const posCost = p.cost_price * p.shares;
    const pnlPct = ((posVal / posCost) - 1) * 100;
    const pc = pnlPct >= 0 ? 'var(--green)' : 'var(--red)';
    const ps = pnlPct >= 0 ? '+' : '';
    return `
      <tr class="perf-pos-row">
        <td><span class="stock-code">${p.stock_id}</span>${p.name && p.name !== p.stock_id ? `<span style="font-size:11px;color:var(--text3);margin-left:5px">${p.name}</span>` : ''}</td>
        <td style="font-family:var(--mono);font-size:12px">${p.entry_date}</td>
        <td style="font-family:var(--mono)">${p.shares.toLocaleString()}</td>
        <td style="font-family:var(--mono)">${p.cost_price.toFixed(2)}</td>
        <td style="font-family:var(--mono)">${cp != null ? cp.toFixed(2) : '<span style="color:var(--text3)">—</span>'}</td>
        <td><span style="font-family:var(--mono);color:${pc};font-weight:600">${ps}${pnlPct.toFixed(2)}%</span><br><span style="font-family:var(--mono);font-size:11px;color:${pc}">${ps}${Math.round(posVal - posCost).toLocaleString()}</span></td>
        <td style="font-family:var(--mono);font-size:12px;color:var(--green)">${p.tp_price != null ? p.tp_price.toFixed(2) : '<span style="color:var(--text3)">—</span>'}</td>
        <td style="font-family:var(--mono);font-size:12px;color:var(--red)">${p.sl_price != null ? p.sl_price.toFixed(2) : '<span style="color:var(--text3)">—</span>'}</td>
        <td style="white-space:nowrap">
          <button class="perf-btn perf-btn-exit" onclick="perfShowExitForm('${p.id}')">出場</button>
          <button class="perf-btn perf-btn-del" style="margin-left:4px" onclick="perfDeletePos('${p.id}')">刪除</button>
        </td>
      </tr>
      <tr id="exit-form-${p.id}" style="display:none">
        <td colspan="9" style="padding:12px 16px;background:var(--bg3);border-bottom:1px solid var(--border)">
          <div style="display:flex;align-items:flex-end;gap:12px;flex-wrap:wrap">
            <span style="font-size:12px;color:var(--text2);font-weight:600;padding-bottom:2px">出場資訊</span>
            <div><div class="perf-input-label">賣出價格 *</div>
              <input id="ep-${p.id}" type="number" step="0.01" class="perf-input" placeholder="0.00" style="width:110px"></div>
            <div><div class="perf-input-label">賣出日期 *</div>
              <input id="ed-${p.id}" type="date" class="perf-input" value="${today}" style="width:140px"></div>
            <div style="display:flex;gap:6px">
              <button class="perf-btn perf-btn-confirm" onclick="perfConfirmExit('${p.id}')">確認賣出</button>
              <button class="perf-btn" onclick="document.getElementById('exit-form-${p.id}').style.display='none'">取消</button>
            </div>
          </div>
          <div style="margin-top:8px;font-size:11px;color:var(--text3)">
            ⚠ 確認後損益將鎖定，此筆移至「已出場」，並自動寫入 Repo（需先設定 Token）
          </div>
        </td>
      </tr>`;
  }

  function closedRow(p) {
    const exitVal = p.shares * p.exit_price;
    const costVal = p.shares * p.cost_price;
    const pnl = exitVal - costVal;
    const pnlPct = ((exitVal / costVal) - 1) * 100;
    const c = pnl >= 0 ? 'var(--green)' : 'var(--red)';
    const s = pnl >= 0 ? '+' : '';
    return `<tr>
      <td><span class="stock-code">${p.stock_id}</span>${p.name && p.name !== p.stock_id ? `<span style="font-size:11px;color:var(--text3);margin-left:5px">${p.name}</span>` : ''}</td>
      <td style="font-family:var(--mono);font-size:12px">${p.entry_date}</td>
      <td style="font-family:var(--mono);font-size:12px">${p.exit_date}</td>
      <td style="font-family:var(--mono)">${p.shares.toLocaleString()}</td>
      <td style="font-family:var(--mono)">${p.cost_price.toFixed(2)}</td>
      <td style="font-family:var(--mono)">${p.exit_price.toFixed(2)}</td>
      <td><span style="font-family:var(--mono);color:${c};font-weight:700">${s}${Math.round(pnl).toLocaleString()}</span></td>
      <td><span style="font-family:var(--mono);color:${c}">${s}${pnlPct.toFixed(2)}%</span></td>
    </tr>`;
  }

  const pnlColor = returnPct >= 0 ? 'var(--green)' : 'var(--red)';
  const pnlSign  = returnPct >= 0 ? '+' : '';
  const rColor = realizedPnl >= 0 ? 'var(--green)' : 'var(--red)';
  const rSign  = realizedPnl >= 0 ? '+' : '';

  main.innerHTML = `
    <div id="tokenModal" class="perf-modal" style="display:none" onclick="if(event.target===this)closeTokenModal()">
      <div class="perf-modal-box">
        <div class="perf-modal-title">⚙ 設定 GitHub Token</div>
        <p class="perf-modal-desc">
          貼上你的 <code>Personal Access Token (PAT)</code>，需要 <code>Contents: Read &amp; Write</code> 權限。<br>
          Token 僅存於本裝置 <code>localStorage</code>，不傳送至任何第三方伺服器。
        </p>
        <a href="https://github.com/settings/tokens/new?scopes=repo&description=twstockscan-perf" target="_blank"
          style="font-size:12px;color:var(--blue);display:block;margin-bottom:14px">→ 點此前往 GitHub 產生 Token（勾選 repo 權限）</a>
        <input id="tokenInput" type="password" class="perf-input" placeholder="ghp_xxxxxxxxxxxxxxxxxxxx" style="width:100%;margin-bottom:16px">
        <div style="display:flex;gap:8px;justify-content:flex-end">
          <button class="perf-btn" onclick="closeTokenModal()">取消</button>
          <button class="perf-btn perf-btn-confirm" onclick="saveToken()">儲存</button>
        </div>
      </div>
    </div>

    <div class="strategy-panel active">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;flex-wrap:wrap;gap:10px">
        <div class="strat-title">◐ 績效追蹤</div>
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <span style="font-size:11px;color:${token ? 'var(--green)' : 'var(--text3)'}">
            ${token ? '● Token 已設定' : '○ 未設定 Token（僅可瀏覽，無法儲存）'}
          </span>
          <button class="perf-btn" onclick="openTokenModal()">⚙ 設定 Token</button>
          <button class="perf-btn" onclick="perfSyncData()">↻ 同步資料</button>
        </div>
      </div>

      <div class="summary-row" style="grid-template-columns:repeat(4,minmax(140px,1fr))">
        <div class="summary-card">
          <div class="summary-label">起始資金</div>
          <div class="summary-value" style="font-size:16px">$${startCap.toLocaleString()}</div>
          <div class="summary-sub">NT$，於 performance.json 設定</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">投組總值</div>
          <div class="summary-value" style="font-size:16px">${pd ? '$' + Math.round(portfolioValue).toLocaleString() : '—'}</div>
          <div class="summary-sub">含未實現持倉估值</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">整體報酬率</div>
          <div class="summary-value" style="color:${pnlColor}">${pd ? pnlSign + returnPct.toFixed(2) + '%' : '—'}</div>
          <div class="summary-sub">相對起始資金</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">已實現損益</div>
          <div class="summary-value" style="font-size:16px;color:${rColor}">${pd ? rSign + '$' + Math.abs(Math.round(realizedPnl)).toLocaleString() : '—'}</div>
          <div class="summary-sub">出場標的加總</div>
        </div>
      </div>

      <div class="perf-chart-wrap">
        <canvas id="perfChart" style="width:100%;height:100%"></canvas>
        ${!pd || !positions.length ? `<div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--text3);font-size:13px;pointer-events:none">新增持倉並同步資料後，圖表將自動產生</div>` : ''}
      </div>

      <div class="perf-section">
        <div class="perf-section-hd">
          <span class="section-title">持倉中　<span style="font-weight:400;color:var(--text3);font-size:12px">${active.length} 檔</span></span>
          <button class="perf-btn perf-btn-add" onclick="perfShowAddForm()">＋ 新增持倉</button>
        </div>
        <div class="table-wrap">
          <div class="table-scroll">
            <table>
              <thead><tr>
                <th>股票</th><th>建倉日</th><th>股數</th><th>成本</th>
                <th>現價</th><th>損益%</th><th>停利</th><th>停損</th><th>操作</th>
              </tr></thead>
              <tbody id="perfActiveBody">
                ${active.length ? active.map(activeRow).join('') : `<tr id="perfEmptyRow"><td colspan="9" style="text-align:center;color:var(--text3);padding:24px 16px;font-size:13px">尚無持倉，點擊右上角「新增持倉」開始記錄</td></tr>`}
                <tr id="perfAddFormRow" style="display:none">
                  <td colspan="9" style="padding:14px 16px;background:var(--bg3);border-top:1px solid var(--border)">
                    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px 12px;margin-bottom:12px">
                      <div><div class="perf-input-label">股票代號 *</div><input id="af-sid" class="perf-input" placeholder="2330" style="width:100%"></div>
                      <div><div class="perf-input-label">名稱</div><input id="af-name" class="perf-input" placeholder="台積電" style="width:100%"></div>
                      <div><div class="perf-input-label">建倉日期 *</div><input id="af-date" type="date" class="perf-input" value="${today}" style="width:100%"></div>
                      <div><div class="perf-input-label">股數 *</div><input id="af-shares" type="number" class="perf-input" placeholder="1000" style="width:100%"></div>
                      <div><div class="perf-input-label">成本價 *</div><input id="af-cost" type="number" step="0.01" class="perf-input" placeholder="850.00" style="width:100%"></div>
                      <div><div class="perf-input-label">停利價</div><input id="af-tp" type="number" step="0.01" class="perf-input" placeholder="950.00" style="width:100%"></div>
                      <div><div class="perf-input-label">停損價</div><input id="af-sl" type="number" step="0.01" class="perf-input" placeholder="800.00" style="width:100%"></div>
                    </div>
                    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                      <button class="perf-btn perf-btn-confirm" onclick="perfSaveAdd()">儲存並寫入 Repo</button>
                      <button class="perf-btn" onclick="document.getElementById('perfAddFormRow').style.display='none'">取消</button>
                      <span style="font-size:11px;color:var(--text3)">⚠ 需先設定 GitHub Token 才能寫入</span>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="perf-section">
        <div class="perf-section-hd">
          <span class="section-title">已出場　<span style="font-weight:400;color:var(--text3);font-size:12px">${closed.length} 檔</span></span>
        </div>
        <div class="table-wrap">
          <div class="table-scroll">
            <table>
              <thead><tr>
                <th>股票</th><th>建倉日</th><th>出場日</th><th>股數</th>
                <th>成本</th><th>賣出價</th><th>損益（NT$）</th><th>損益率</th>
              </tr></thead>
              <tbody>
                ${closed.length ? closed.map(closedRow).join('') : `<tr><td colspan="8" style="text-align:center;color:var(--text3);padding:24px 16px;font-size:13px">尚無出場記錄</td></tr>`}
              </tbody>
            </table>
          </div>
        </div>
      </div>

    </div>`;

  setTimeout(() => initPerfChart(pd), 60);

  // 切換側欄為周記模式，並渲染列表
  setPerfSidebarMode(true);
  const jfDate = document.getElementById('jf-date');
  if (jfDate && !jfDate.value) jfDate.value = today;
  const journalList = document.getElementById('journalList');
  if (journalList) journalList.innerHTML = renderJournalList(pd?.journal || []);
}

// ════════════════════════════════════════════════════
//  PERFORMANCE — 互動函式
// ════════════════════════════════════════════════════
function perfShowAddForm() {
  const row = document.getElementById('perfAddFormRow');
  const emptyRow = document.getElementById('perfEmptyRow');
  if (row) { row.style.display = 'table-row'; if (emptyRow) emptyRow.style.display = 'none'; }
  document.getElementById('af-sid')?.focus();
}

function perfShowExitForm(id) {
  const row = document.getElementById(`exit-form-${id}`);
  if (row) row.style.display = row.style.display === 'none' ? 'table-row' : 'none';
}

async function perfSaveAdd() {
  const sid    = document.getElementById('af-sid')?.value.trim();
  const name   = document.getElementById('af-name')?.value.trim();
  const date   = document.getElementById('af-date')?.value;
  const shares = parseFloat(document.getElementById('af-shares')?.value);
  const cost   = parseFloat(document.getElementById('af-cost')?.value);
  const tp     = parseFloat(document.getElementById('af-tp')?.value) || null;
  const sl     = parseFloat(document.getElementById('af-sl')?.value) || null;
  if (!sid || !date || !shares || !cost) { alert('請填寫必填欄位（標記 * 的欄位）'); return; }
  if (!DATA.performance_data) {
    DATA.performance_data = { starting_capital: 450000, last_updated: '', positions: [], price_history: {} };
  }
  const newPos = {
    id: 'p' + Date.now(), stock_id: sid, name: name || sid,
    entry_date: date, shares, cost_price: cost,
    tp_price: tp, sl_price: sl,
    exit_price: null, exit_date: null, confirmed: false
  };
  DATA.performance_data.positions.push(newPos);
  DATA.performance_data.last_updated = new Date().toISOString().slice(0, 10);
  const ok = await ghWritePerf(DATA.performance_data);
  if (ok) renderStrategy(); else DATA.performance_data.positions.pop();
}

async function perfConfirmExit(id) {
  const exitPrice = parseFloat(document.getElementById(`ep-${id}`)?.value);
  const exitDate  = document.getElementById(`ed-${id}`)?.value;
  if (!exitPrice || exitPrice <= 0 || !exitDate) { alert('請填寫賣出價格與日期'); return; }
  const pd  = DATA.performance_data;
  const pos = pd.positions.find(p => p.id === id);
  if (!pos) return;
  const prev = { exit_price: pos.exit_price, exit_date: pos.exit_date, confirmed: pos.confirmed };
  pos.exit_price = exitPrice; pos.exit_date = exitDate; pos.confirmed = true;
  pd.last_updated = new Date().toISOString().slice(0, 10);
  const ok = await ghWritePerf(pd);
  if (ok) renderStrategy(); else Object.assign(pos, prev);
}

async function perfDeletePos(id) {
  if (!confirm('確認刪除此持倉記錄？此操作無法復原。')) return;
  const pd  = DATA.performance_data;
  const idx = pd.positions.findIndex(p => p.id === id);
  if (idx === -1) return;
  const [removed] = pd.positions.splice(idx, 1);
  pd.last_updated = new Date().toISOString().slice(0, 10);
  const ok = await ghWritePerf(pd);
  if (ok) renderStrategy(); else pd.positions.splice(idx, 0, removed);
}

async function perfSyncData() {
  try {
    const res = await fetch(`data/performance.json?t=${Date.now()}`, { cache: 'no-store' });
    if (res.ok) { DATA.performance_data = await res.json(); renderStrategy(); }
    else alert('同步失敗，請確認 performance.json 已建立於 data/ 目錄');
  } catch(e) { alert('同步失敗：' + e.message); }
}

// ════════════════════════════════════════════════════
//  交易日誌
// ════════════════════════════════════════════════════

function renderJournalList(entries) {
  if (!entries.length) return `
    <div style="text-align:center;color:var(--text3);padding:28px 12px;font-size:12px">
      尚無周記，點擊右上角「＋ 新增」開始撰寫
    </div>`;
  return [...entries]
    .sort((a, b) => b.date.localeCompare(a.date))
    .map(e => {
      const tags = (e.tags || []).map(t =>
        `<span style="font-size:10px;padding:1px 6px;border-radius:8px;background:var(--bg2);color:var(--text3);border:1px solid var(--border)">${t}</span>`
      ).join('');
      const preview = (e.content || '').replace(/\n/g, ' ').slice(0, 50);
      const hasMore = (e.content || '').length > 50;
      return `
        <div class="journal-entry" id="je-${e.id}">
          <div class="journal-header" onclick="journalToggle('${e.id}')">
            <div class="journal-title-wrap">
              <span class="journal-date">${e.date}</span>
              <span class="journal-title">${e.title}</span>
              <span class="journal-tags">${tags}</span>
              <span class="journal-preview" id="jp-${e.id}">${preview}${hasMore ? '…' : ''}</span>
            </div>
            <span class="journal-arrow" id="ja-${e.id}">▼</span>
          </div>
          <div class="journal-body" id="jb-${e.id}" style="display:none">
            <div id="jview-${e.id}" class="journal-content">${(e.content||'').replace(/\n/g,'<br>')}</div>
            <div id="jedit-${e.id}" style="display:none">
              <input id="jet-${e.id}" class="perf-input" value="${(e.title||'').replace(/"/g,'&quot;')}"
                style="width:100%;margin-bottom:6px;font-size:12px" placeholder="標題">
              <input id="jeta-${e.id}" class="perf-input" value="${(e.tags||[]).join(', ')}"
                style="width:100%;margin-bottom:6px;font-size:12px" placeholder="標籤（逗號分隔）">
              <textarea id="jec-${e.id}" class="perf-input" rows="7"
                style="width:100%;resize:vertical;font-family:var(--sans);line-height:1.7;font-size:12px"
              >${e.content||''}</textarea>
            </div>
            <div class="journal-actions" style="margin-top:8px">
              <button class="perf-btn" style="font-size:11px" id="jbtn-edit-${e.id}" onclick="journalStartEdit('${e.id}')">編輯</button>
              <button class="perf-btn perf-btn-confirm" style="font-size:11px;display:none" id="jbtn-save-${e.id}" onclick="journalSaveEdit('${e.id}')">儲存</button>
              <button class="perf-btn" style="font-size:11px;display:none" id="jbtn-cancel-${e.id}" onclick="journalCancelEdit('${e.id}')">取消</button>
              <button class="perf-btn perf-btn-del" style="font-size:11px" onclick="journalDelete('${e.id}')">刪除</button>
            </div>
          </div>
        </div>`;
    }).join('');
}

function journalToggle(id) {
  const body    = document.getElementById(`jb-${id}`);
  const arrow   = document.getElementById(`ja-${id}`);
  const preview = document.getElementById(`jp-${id}`);
  if (!body) return;
  const open = body.style.display === 'none';
  body.style.display    = open ? 'block' : 'none';
  arrow.textContent     = open ? '▲' : '▼';
  if (preview) preview.style.display = open ? 'none' : '';
}

function journalShowAdd(show = true) {
  const form = document.getElementById('journalAddForm');
  if (!form) return;
  form.style.display = show ? 'block' : 'none';
  if (show) document.getElementById('jf-title')?.focus();
}

async function journalSaveAdd() {
  const date    = document.getElementById('jf-date')?.value;
  const title   = document.getElementById('jf-title')?.value.trim();
  const tagsRaw = document.getElementById('jf-tags')?.value.trim();
  const content = document.getElementById('jf-content')?.value.trim();
  if (!date || !title) { alert('請填寫日期與標題'); return; }
  const tags = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [];
  if (!DATA.performance_data) {
    DATA.performance_data = { starting_capital: 450000, last_updated: '', positions: [], price_history: {}, journal: [] };
  }
  if (!DATA.performance_data.journal) DATA.performance_data.journal = [];
  const entry = { id: 'j' + Date.now(), date, title, tags, content };
  DATA.performance_data.journal.push(entry);
  DATA.performance_data.last_updated = new Date().toISOString().slice(0, 10);
  const ok = await ghWritePerf(DATA.performance_data);
  if (ok) renderStrategy(); else DATA.performance_data.journal.pop();
}

function journalStartEdit(id) {
  document.getElementById(`jview-${id}`).style.display  = 'none';
  document.getElementById(`jedit-${id}`).style.display  = 'block';
  document.getElementById(`jbtn-edit-${id}`).style.display   = 'none';
  document.getElementById(`jbtn-save-${id}`).style.display   = 'inline-block';
  document.getElementById(`jbtn-cancel-${id}`).style.display = 'inline-block';
}

function journalCancelEdit(id) {
  document.getElementById(`jview-${id}`).style.display  = 'block';
  document.getElementById(`jedit-${id}`).style.display  = 'none';
  document.getElementById(`jbtn-edit-${id}`).style.display   = 'inline-block';
  document.getElementById(`jbtn-save-${id}`).style.display   = 'none';
  document.getElementById(`jbtn-cancel-${id}`).style.display = 'none';
}

async function journalSaveEdit(id) {
  const title   = document.getElementById(`jet-${id}`)?.value.trim();
  const tagsRaw = document.getElementById(`jeta-${id}`)?.value.trim();
  const content = document.getElementById(`jec-${id}`)?.value.trim();
  if (!title) { alert('標題不可空白'); return; }
  const pd    = DATA.performance_data;
  const entry = pd.journal.find(e => e.id === id);
  if (!entry) return;
  const prev  = { ...entry };
  entry.title   = title;
  entry.tags    = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [];
  entry.content = content;
  pd.last_updated = new Date().toISOString().slice(0, 10);
  const ok = await ghWritePerf(pd);
  if (ok) renderStrategy(); else Object.assign(entry, prev);
}

async function journalDelete(id) {
  if (!confirm('確認刪除此日誌？此操作無法復原。')) return;
  const pd  = DATA.performance_data;
  const idx = pd.journal.findIndex(e => e.id === id);
  if (idx === -1) return;
  const [removed] = pd.journal.splice(idx, 1);
  pd.last_updated = new Date().toISOString().slice(0, 10);
  const ok = await ghWritePerf(pd);
  if (ok) renderStrategy(); else pd.journal.splice(idx, 0, removed);
}

// ════════════════════════════════════════════════════
