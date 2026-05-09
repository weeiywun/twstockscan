# GAS 觸發選股掃描

GitHub Actions 內建 `schedule` 偶爾會延遲或漏跑，因此主要排程交給 Google Apps Script：

- 每日選股掃描：台灣時間每日 17:00 左右觸發 `daily_scan_1700`
- 大戶籌碼選股：台灣時間每週六 09:10 左右觸發 `holdings_scan_weekly`

`holdings_scan.yml` 不再使用 GitHub 內建 `schedule`，避免延遲重跑造成重複 LINE 通知。

## Apps Script

Repo 內也保留同一份範本：`gas/workflow-triggers.gs`。

```javascript
const GITHUB_OWNER = 'weeiywun';
const GITHUB_REPO = 'twstockscan';
const GITHUB_TOKEN = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');

function triggerDailyScan1700() {
  dispatchRepositoryEvent('daily_scan_1700');
}

function triggerHoldingsScanWeekly() {
  dispatchRepositoryEvent('holdings_scan_weekly');
}

function dispatchRepositoryEvent(eventType) {
  const url = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/dispatches`;
  const res = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    headers: githubHeaders(),
    payload: JSON.stringify({
      event_type: eventType,
      client_payload: {
        source: 'google_apps_script',
        triggered_at: new Date().toISOString(),
      },
    }),
    muteHttpExceptions: true,
  });

  const code = res.getResponseCode();
  if (code < 200 || code >= 300) {
    throw new Error(`GitHub dispatch failed: ${eventType} ${code} ${res.getContentText()}`);
  }

  Logger.log(`GitHub dispatch accepted: ${eventType}`);
}

function githubHeaders() {
  if (!GITHUB_TOKEN) {
    throw new Error('Missing Script property: GITHUB_TOKEN');
  }
  return {
    Authorization: `Bearer ${GITHUB_TOKEN}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
  };
}
```

## 設定步驟

1. 建立 GitHub fine-grained token，授權此 repo 的 `Contents: Read and write`。
2. 在 Apps Script 的 Script properties 新增 `GITHUB_TOKEN`。
3. 新增 time-driven trigger：
   - `triggerDailyScan1700`：每日，時區 `Asia/Taipei`，下午 5 點附近。
   - `triggerHoldingsScanWeekly`：每週六，時區 `Asia/Taipei`，上午 9 點附近。
4. GitHub workflow 仍保留 `workflow_dispatch`，需要臨時重跑時可手動執行。

## 對應 Workflow

- `daily_scan.yml` 接收 `repository_dispatch` type: `daily_scan_1700`
- `holdings_scan.yml` 接收 `repository_dispatch` type: `holdings_scan_weekly`
