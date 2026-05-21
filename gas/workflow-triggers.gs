const GITHUB_OWNER = 'weeiywun';
const GITHUB_REPO = 'twstockscan';
const GITHUB_TOKEN = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
const TIMEZONE = 'Asia/Taipei';

// Daily scan is triggered by Google Apps Script instead of GitHub schedule.
// Keep this at Taiwan time 17:00 so TWSE/TPEx institutional summaries are usually available.
function triggerDailyScan1700() {
  dispatchRepositoryEvent('daily_scan_1700');
}

function triggerIntradayVolumePullback1000() {
  dispatchRepositoryEvent('intraday_volume_pullback_1000');
}

function triggerHoldingsScanWeekly() {
  dispatchRepositoryEvent('holdings_scan_weekly');
}

function installDailyScan1700Trigger() {
  deleteTriggersFor_('triggerDailyScan1700');
  ScriptApp.newTrigger('triggerDailyScan1700')
    .timeBased()
    .everyDays(1)
    .atHour(17)
    .nearMinute(0)
    .inTimezone(TIMEZONE)
    .create();
}

function installIntradayVolumePullback1000Trigger() {
  deleteTriggersFor_('triggerIntradayVolumePullback1000');
  ScriptApp.newTrigger('triggerIntradayVolumePullback1000')
    .timeBased()
    .everyDays(1)
    .atHour(10)
    .nearMinute(0)
    .inTimezone(TIMEZONE)
    .create();
}

function installHoldingsScanWeeklyTrigger() {
  deleteTriggersFor_('triggerHoldingsScanWeekly');
  ScriptApp.newTrigger('triggerHoldingsScanWeekly')
    .timeBased()
    .onWeekDay(ScriptApp.WeekDay.SATURDAY)
    .atHour(9)
    .nearMinute(0)
    .inTimezone(TIMEZONE)
    .create();
}

function deleteTriggersFor_(handlerName) {
  ScriptApp.getProjectTriggers()
    .filter(trigger => trigger.getHandlerFunction() === handlerName)
    .forEach(trigger => ScriptApp.deleteTrigger(trigger));
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
