# GAS 觸發每日選股掃描

每日選股掃描 workflow 不使用 GitHub Actions 內建 `schedule`，改由 Google Apps Script 在台灣時間下午 5 點觸發 `repository_dispatch` 的 `daily_scan_1700` 事件。

## Apps Script

```javascript
const GITHUB_OWNER = 'weeiywun';
const GITHUB_REPO = 'twstockscan';
const GITHUB_TOKEN = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');

function triggerDailyScan1700() {
  const url = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/dispatches`;
  const res = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    headers: {
      Authorization: `Bearer ${GITHUB_TOKEN}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
    payload: JSON.stringify({
      event_type: 'daily_scan_1700',
      client_payload: {
        source: 'google_apps_script',
        triggered_at: new Date().toISOString(),
      },
    }),
    muteHttpExceptions: true,
  });

  const code = res.getResponseCode();
  if (code < 200 || code >= 300) {
    throw new Error(`GitHub dispatch failed: ${code} ${res.getContentText()}`);
  }
}
```

## 設定步驟

1. 建立 GitHub fine-grained token，授權此 repo 的 `Contents: Read and write`。
2. 在 Apps Script 的 Script properties 新增 `GITHUB_TOKEN`。
3. 新增 time-driven trigger，執行 `triggerDailyScan1700`，時區選 `Asia/Taipei`，時間選下午 5 點附近。
4. workflow 仍保留 `workflow_dispatch`，需要回填月份或臨時重跑時可手動執行。
