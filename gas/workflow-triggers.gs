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
