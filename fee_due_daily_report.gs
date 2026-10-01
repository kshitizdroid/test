/**
 * Daily Student Fee-Due Report
 * -----------------------------
 * Reads your student fee sheet and emails a summary of everyone who still
 * owes money. Designed to run automatically once a day via a time trigger.
 *
 * SETUP (one time):
 *   1. Open your Google Sheet.
 *   2. Extensions ▸ Apps Script.
 *   3. Delete anything in the editor and paste this whole file.
 *   4. Adjust the CONFIG block below to match your sheet.
 *   5. Click Save (disk icon).
 *   6. Run the function "sendFeeDueReport" once (choose it in the dropdown,
 *      click Run). Approve the permissions it asks for. Check your inbox.
 *   7. Run "createDailyTrigger" once to schedule it every morning.
 *
 * That's it — it will now email you daily, no further action needed.
 */

// ======================= CONFIG — EDIT THESE ===========================
var CONFIG = {
  // Who receives the report:
  RECIPIENT: 'jatingaur1811@gmail.com',

  // The tab (sheet) name holding the data. Leave '' to use the first tab.
  SHEET_NAME: '',

  // Column HEADER TEXT (exactly as written in row 1 of your sheet).
  // The script finds the columns by these names, so column order can change.
  NAME_HEADER: 'Name',          // e.g. 'Student Name'
  FEE_DUE_HEADER: 'Fee Due',    // e.g. 'Due Amount', 'Balance', 'Pending Fee'

  // Optional extra columns to include in the email if present (set to '' to skip)
  CLASS_HEADER: 'Class',        // e.g. 'Class', 'Grade', 'Section'
  CONTACT_HEADER: 'Contact',    // e.g. 'Phone', 'Parent Contact'

  // Currency symbol shown in the email
  CURRENCY: '₹',

  // Send an email even when nobody owes money? (true = daily confirmation,
  // false = only email when at least one student has dues)
  SEND_WHEN_NOTHING_DUE: true,

  // What hour (0-23, your local time) to send the daily email
  SEND_HOUR: 8
};
// =======================================================================


/**
 * Main function: reads the sheet and emails the fee-due summary.
 */
function sendFeeDueReport() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = CONFIG.SHEET_NAME ? ss.getSheetByName(CONFIG.SHEET_NAME) : ss.getSheets()[0];
  if (!sheet) {
    throw new Error('Sheet not found: "' + CONFIG.SHEET_NAME + '". Check CONFIG.SHEET_NAME.');
  }

  var values = sheet.getDataRange().getValues();
  if (values.length < 2) {
    Logger.log('No data rows found.');
    return;
  }

  var headers = values[0].map(function (h) { return String(h).trim().toLowerCase(); });

  function colIndex(headerText) {
    if (!headerText) return -1;
    return headers.indexOf(String(headerText).trim().toLowerCase());
  }

  var nameCol = colIndex(CONFIG.NAME_HEADER);
  var feeCol = colIndex(CONFIG.FEE_DUE_HEADER);
  var classCol = colIndex(CONFIG.CLASS_HEADER);
  var contactCol = colIndex(CONFIG.CONTACT_HEADER);

  if (nameCol === -1) {
    throw new Error('Could not find the name column "' + CONFIG.NAME_HEADER +
      '". Your headers are: ' + values[0].join(', '));
  }
  if (feeCol === -1) {
    throw new Error('Could not find the fee-due column "' + CONFIG.FEE_DUE_HEADER +
      '". Your headers are: ' + values[0].join(', '));
  }

  var due = [];
  var totalDue = 0;

  for (var r = 1; r < values.length; r++) {
    var row = values[r];
    var name = String(row[nameCol]).trim();
    if (!name) continue; // skip blank rows

    var amount = parseAmount(row[feeCol]);
    if (amount > 0) {
      due.push({
        name: name,
        amount: amount,
        klass: classCol !== -1 ? String(row[classCol]).trim() : '',
        contact: contactCol !== -1 ? String(row[contactCol]).trim() : ''
      });
      totalDue += amount;
    }
  }

  // Sort by highest amount owed first
  due.sort(function (a, b) { return b.amount - a.amount; });

  if (due.length === 0 && !CONFIG.SEND_WHEN_NOTHING_DUE) {
    Logger.log('Nothing due; email suppressed by config.');
    return;
  }

  var today = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'EEEE, d MMMM yyyy');
  var subject = due.length === 0
    ? '✅ Fee Dues (' + today + '): All clear'
    : '📋 Fee Dues (' + today + '): ' + due.length + ' student' +
      (due.length > 1 ? 's' : '') + ' — ' + CONFIG.CURRENCY + formatMoney(totalDue) + ' total';

  var html = buildHtml(due, totalDue, today, classCol !== -1, contactCol !== -1);

  MailApp.sendEmail({
    to: CONFIG.RECIPIENT,
    subject: subject,
    htmlBody: html
  });

  Logger.log('Report sent to ' + CONFIG.RECIPIENT + ' — ' + due.length + ' due, total ' + totalDue);
}


/**
 * Turns a cell value into a number. Handles "₹1,200", "1200.50", "Rs 500", etc.
 */
function parseAmount(value) {
  if (value === '' || value === null || value === undefined) return 0;
  if (typeof value === 'number') return value;
  var cleaned = String(value).replace(/[^0-9.\-]/g, '');
  var n = parseFloat(cleaned);
  return isNaN(n) ? 0 : n;
}


function formatMoney(n) {
  // Indian-style grouping, 2 decimals only if needed
  var hasDecimals = Math.round(n) !== n;
  var fixed = hasDecimals ? n.toFixed(2) : String(Math.round(n));
  var parts = fixed.split('.');
  var intPart = parts[0];
  var lastThree = intPart.length > 3 ? intPart.slice(-3) : intPart;
  var otherNums = intPart.length > 3 ? intPart.slice(0, -3) : '';
  if (otherNums) {
    lastThree = ',' + lastThree;
  }
  var grouped = otherNums.replace(/\B(?=(\d{2})+(?!\d))/g, ',') + lastThree;
  return parts.length > 1 ? grouped + '.' + parts[1] : grouped;
}


function buildHtml(due, totalDue, today, showClass, showContact) {
  var style = 'font-family:Arial,Helvetica,sans-serif;color:#1a1a1a;';
  var html = '<div style="' + style + 'max-width:640px;">';
  html += '<h2 style="margin:0 0 4px;">Student Fee Dues</h2>';
  html += '<p style="color:#666;margin:0 0 16px;">' + today + '</p>';

  if (due.length === 0) {
    html += '<p style="font-size:16px;color:#16794a;">🎉 No fees are currently due. All students are paid up.</p>';
    html += '</div>';
    return html;
  }

  html += '<p style="font-size:15px;margin:0 0 16px;"><b>' + due.length +
    '</b> student' + (due.length > 1 ? 's have' : ' has') +
    ' outstanding fees totalling <b>' + CONFIG.CURRENCY + formatMoney(totalDue) + '</b>.</p>';

  html += '<table style="border-collapse:collapse;width:100%;font-size:14px;">';
  html += '<tr style="background:#f2f4f7;text-align:left;">';
  html += '<th style="padding:8px;border:1px solid #e0e0e0;">Student</th>';
  if (showClass) html += '<th style="padding:8px;border:1px solid #e0e0e0;">Class</th>';
  html += '<th style="padding:8px;border:1px solid #e0e0e0;text-align:right;">Fee Due</th>';
  if (showContact) html += '<th style="padding:8px;border:1px solid #e0e0e0;">Contact</th>';
  html += '</tr>';

  for (var i = 0; i < due.length; i++) {
    var d = due[i];
    var bg = i % 2 === 0 ? '#ffffff' : '#fafafa';
    html += '<tr style="background:' + bg + ';">';
    html += '<td style="padding:8px;border:1px solid #e0e0e0;">' + escapeHtml(d.name) + '</td>';
    if (showClass) html += '<td style="padding:8px;border:1px solid #e0e0e0;">' + escapeHtml(d.klass) + '</td>';
    html += '<td style="padding:8px;border:1px solid #e0e0e0;text-align:right;font-weight:bold;">' +
      CONFIG.CURRENCY + formatMoney(d.amount) + '</td>';
    if (showContact) html += '<td style="padding:8px;border:1px solid #e0e0e0;">' + escapeHtml(d.contact) + '</td>';
    html += '</tr>';
  }

  html += '<tr style="background:#f2f4f7;font-weight:bold;">';
  var span = 1 + (showClass ? 1 : 0);
  html += '<td style="padding:8px;border:1px solid #e0e0e0;" colspan="' + span + '">Total</td>';
  html += '<td style="padding:8px;border:1px solid #e0e0e0;text-align:right;">' +
    CONFIG.CURRENCY + formatMoney(totalDue) + '</td>';
  if (showContact) html += '<td style="padding:8px;border:1px solid #e0e0e0;"></td>';
  html += '</tr>';

  html += '</table>';
  html += '<p style="color:#999;font-size:12px;margin-top:16px;">Automated daily report from your Google Sheet.</p>';
  html += '</div>';
  return html;
}


function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}


/**
 * Run this ONCE to schedule the report every day.
 * Safe to re-run: it clears old triggers for this function first.
 */
function createDailyTrigger() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'sendFeeDueReport') {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
  ScriptApp.newTrigger('sendFeeDueReport')
    .timeBased()
    .everyDays(1)
    .atHour(CONFIG.SEND_HOUR)
    .create();
  Logger.log('Daily trigger created — report will send around ' + CONFIG.SEND_HOUR + ':00 each day.');
}
