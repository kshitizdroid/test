/**
 * Pinak Institute — Faculty Attendance (simple form, late logic behind the scenes)
 * ================================================================================
 * The Google Form stays minimal — faculty only tap their NAME (shown as options,
 * not a dropdown) and Check-in / Check-out. Date & time are automatic.
 *
 * LATE DETECTION happens inside the Sheet, never on the form:
 *   - The session (Morning/Evening) is inferred from the CHECK-IN TIME
 *     (before SESSION_SPLIT = Morning, at/after = Evening).
 *   - Prajjwal Gupta: Evening only, late after 4:25 PM.
 *   - Mohit Pal: Morning late after 11:35 AM, Evening late after 4:25 PM.
 *   - Aakanksha, Ajeet Sir: flexible — recorded only, never flagged late.
 *
 * Sheet tabs: Form Responses 1 (raw, never edited), Leave, Corrections,
 * Daily Dashboard, Monthly Report. Plus a QR image in your Drive.
 *
 * FIRST TIME:  paste this file, Save, Run ▶ setupSystem.
 * REPLACING AN OLDER VERSION:  Run ▶ resetAndSetup (trashes old Form & Sheet,
 * builds this one — you get a new QR). Day to day use the "Pinak Attendance" menu.
 */

var TIMEZONE = 'Asia/Kolkata';

// Faculty + subject (subject is only for display in reports).
var FACULTY = [
  ['Prajjwal Gupta', 'Maths'],
  ['Mohit Pal',      'Physics'],
  ['Aakanksha',      'Biology'],
  ['Ajeet Sir',      'English']
];

// Late rules per faculty (hidden from the form). Session inferred from check-in time.
// Faculty absent from this map are flexible (never flagged late).
var LATE_RULES = {
  'Prajjwal Gupta': [{ session: 'Evening', lateAfter: '16:25' }],
  'Mohit Pal':      [{ session: 'Morning', lateAfter: '11:35' },
                     { session: 'Evening', lateAfter: '16:25' }]
};
var SESSION_SPLIT = '14:30';   // check-in before this = Morning, at/after = Evening

var ACTIONS = ['Check-in', 'Check-out'];
var WORKING_DAYS = [1, 2, 3, 4, 5, 6];   // Mon–Sat (Sun off)

var P_FORM = 'FORM_ID', P_SHEET = 'SHEET_ID', P_QR = 'QR_FILE_ID';

/* ============================ SETUP ============================ */

/** Build everything (or re-run safely — keeps response history). */
function setupSystem() {
  var props = PropertiesService.getScriptProperties();

  var ss = null, sid = props.getProperty(P_SHEET);
  if (sid) { try { ss = SpreadsheetApp.openById(sid); } catch (e) {} }
  if (!ss) { ss = SpreadsheetApp.create('Pinak Institute — Faculty Attendance'); props.setProperty(P_SHEET, ss.getId()); }

  var form = null, fid = props.getProperty(P_FORM);
  if (fid) { try { form = FormApp.openById(fid); } catch (e) {} }
  if (!form) {
    form = FormApp.create('Pinak Institute — Faculty Attendance');
    props.setProperty(P_FORM, form.getId());
    form.setDescription(
      'Scan at reception from your own phone.\n' +
      '1) Tap your name.  2) Tap Check-in or Check-out.  3) Submit.\n' +
      'Date and time are recorded automatically.');
    form.setCollectEmail(false).setLimitOneResponsePerUser(false)
        .setAllowResponseEdits(false).setShowLinkToRespondAgain(true)
        .setConfirmationMessage('Recorded. Thank you!');

    form.addMultipleChoiceItem().setTitle('Faculty Name').setRequired(true)
        .setChoiceValues(FACULTY.map(function (f) { return f[0]; }));
    form.addMultipleChoiceItem().setTitle('Action').setRequired(true)
        .setChoiceValues(ACTIONS);

    form.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId());
  }

  SpreadsheetApp.flush();
  buildLeaveSheet_(ss);
  buildCorrectionsSheet_(ss);
  buildDailyDashboardSheet_(ss);
  buildMonthlyReportSheet_(ss);
  removeDefaultSheet1_(ss);
  installTriggers_(form, ss);
  refreshAll();
  var qrId = generateQrCode_(form.getPublishedUrl());

  Logger.log('================ SETUP COMPLETE ================');
  Logger.log('FORM (QR link):  ' + form.getPublishedUrl());
  Logger.log('FORM (edit):     ' + form.getEditUrl());
  Logger.log('SHEET:           ' + ss.getUrl());
  if (qrId) Logger.log('QR IMAGE:        https://drive.google.com/file/d/' + qrId + '/view');
  Logger.log('===============================================');
  Logger.log('Reload the Sheet and use the "Pinak Attendance" menu.');
}

/** Trash the old Form & Sheet, then build this version fresh. */
function resetAndSetup() {
  var props = PropertiesService.getScriptProperties();
  ['FORM_ID', 'SHEET_ID', 'QR_FILE_ID'].forEach(function (k) {
    var id = props.getProperty(k);
    if (id) { try { DriveApp.getFileById(id).setTrashed(true); } catch (e) {} }
    props.deleteProperty(k);
  });
  ScriptApp.getProjectTriggers().forEach(function (t) { try { ScriptApp.deleteTrigger(t); } catch (e) {} });
  setupSystem();
}

/* ============================ SHEET BUILDERS ============================ */

function buildLeaveSheet_(ss) {
  var sh = getOrCreate_(ss, 'Leave');
  if (sh.getLastRow() >= 1 && sh.getRange(1, 1).getValue() === 'Date') return;
  sh.clear();
  sh.getRange(1, 1, 1, 4).setValues([['Date', 'Faculty', 'Type', 'Note']]).setFontWeight('bold');
  sh.getRange('A2').setNote('Date = YYYY-MM-DD. Type = Leave (one faculty) or Holiday ' +
    '(institute closed — faculty "ALL"). Keeps absent-counts honest.');
  sh.setFrozenRows(1); sh.autoResizeColumns(1, 4);
}

function buildCorrectionsSheet_(ss) {
  var sh = getOrCreate_(ss, 'Corrections');
  if (sh.getLastRow() >= 1 && sh.getRange(1, 1).getValue() === 'Date') return;
  sh.clear();
  sh.getRange(1, 1, 1, 7).setValues([['Date', 'Faculty', 'Action', 'Corrected Time', 'Mode', 'Reason', 'Approved By']]).setFontWeight('bold');
  sh.getRange('A2').setNote(
    'Fix missed/wrong entries here. Originals in "Form Responses 1" are NEVER changed.\n' +
    'Date = YYYY-MM-DD.  Corrected Time = HH:MM (24h) — late is re-checked from this time.\n' +
    'Mode: SET = add/overwrite this entry · VOID = cancel a wrong entry (leave time blank).\n' +
    'Reason + Approved By = audit trail.');
  sh.setFrozenRows(1); sh.autoResizeColumns(1, 7);
}

function buildDailyDashboardSheet_(ss) {
  var sh = getOrCreate_(ss, 'Daily Dashboard');
  sh.clear();
  sh.getRange('A1').setValue('Daily Attendance').setFontWeight('bold').setFontSize(14);
  sh.getRange('A2').setValue('Date:').setFontWeight('bold');
  sh.getRange('B2').setValue(todayStr_()).setNote('Type YYYY-MM-DD, then menu → Refresh dashboards.');
  sh.getRange(4, 1, 1, 6).setValues([['Faculty', 'Subject', 'Check-in', 'Check-out', 'Late?', 'Status']]).setFontWeight('bold');
  sh.setFrozenRows(4); sh.autoResizeColumns(1, 6);
}

function buildMonthlyReportSheet_(ss) {
  var sh = getOrCreate_(ss, 'Monthly Report');
  sh.clear();
  sh.getRange('A1').setValue('Monthly Report').setFontWeight('bold').setFontSize(14);
  sh.getRange('A2').setValue('Month:').setFontWeight('bold');
  sh.getRange('B2').setValue(monthStr_()).setNote('Type YYYY-MM, then menu → Refresh dashboards.');
  sh.getRange(4, 1, 1, 7).setValues([['Faculty', 'Subject', 'Working Days', 'Present', 'Absent', 'Leave', 'Late Count']]).setFontWeight('bold');
  sh.setFrozenRows(4); sh.autoResizeColumns(1, 7);
}

/* ============================ LATE LOGIC (hidden from form) ============================ */

function sessionOf_(time) { return time < SESSION_SPLIT ? 'Morning' : 'Evening'; }

/** For a check-in time, returns {session, late} if this faculty has a rule for that
 *  session, else null (flexible / no rule → never late). */
function lateInfo_(faculty, time) {
  var rules = LATE_RULES[faculty];
  if (!rules || !time) return null;
  var sess = sessionOf_(time);
  for (var i = 0; i < rules.length; i++) {
    if (rules[i].session === sess) return { session: sess, late: time > rules[i].lateAfter };
  }
  return null;
}

/* ============================ DATA ============================ */

/** Collapse raw responses + corrections into per date/faculty check-in & check-out lists. */
function buildDaily_(ss) {
  var map = {};
  function slot(d, f) { var k = d + '|' + f; return map[k] || (map[k] = { in: [], out: [] }); }

  readResponses_(ss).forEach(function (r) {
    var s = slot(fmtDate_(r.timestamp), r.faculty);
    (r.action === 'Check-out' ? s.out : s.in).push(fmtTime_(r.timestamp));
  });

  readCorrections_(ss).forEach(function (c) {
    var s = slot(c.date, c.faculty);
    if (c.mode === 'VOID') { if (c.action === 'Check-out') s.out = []; else s.in = []; }
    else if (c.time) (c.action === 'Check-out' ? s.out : s.in).push(c.time);
  });

  return map;
}

function buildDailyDashboard() {
  var ss = openSheet_();
  var sh = ss.getSheetByName('Daily Dashboard');
  var date = normDate_(sh.getRange('B2').getValue());
  var map = buildDaily_(ss);

  var out = FACULTY.map(function (f) {
    var s = map[date + '|' + f[0]] || { in: [], out: [] };
    var ins = s.in.slice().sort(), outs = s.out.slice().sort();

    // Late across all of today's check-ins for this faculty.
    var lateSessions = [], hasRuleHit = false;
    ins.forEach(function (t) {
      var li = lateInfo_(f[0], t);
      if (li) { hasRuleHit = true; if (li.late && lateSessions.indexOf(li.session) === -1) lateSessions.push(li.session); }
    });
    var lateCell = lateSessions.length ? 'LATE (' + lateSessions.join(', ') + ')'
                 : (hasRuleHit ? 'On time' : '');

    var status;
    if (!ins.length && !outs.length) status = isOnLeave_(ss, date, f[0]) ? 'Leave' : 'Absent';
    else if (ins.length && outs.length) status = 'Complete';
    else status = ins.length ? 'Missing check-out' : 'Missing check-in';

    return [f[0], f[1], ins.join(', '), outs.join(', '), lateCell, status];
  });

  var start = 5, last = sh.getLastRow();
  if (last >= start) sh.getRange(start, 1, last - start + 1, 6).clearContent().setBackground(null).setFontColor(null);
  if (out.length) { sh.getRange(start, 1, out.length, 6).setValues(out); colorDaily_(sh, start, out); }
  sh.getRange('E2').setValue('(updated ' + fmtDateTime_(new Date()) + ')');
}

function buildMonthlyReport() {
  var ss = openSheet_();
  var sh = ss.getSheetByName('Monthly Report');
  var month = String(sh.getRange('B2').getValue()).trim();
  var map = buildDaily_(ss);
  var leaves = readLeave_(ss);
  var workingDays = workingDaysInMonth_(month, leaves);

  var out = FACULTY.map(function (f) {
    var present = {}, leave = {}, lateCount = 0;
    Object.keys(map).forEach(function (k) {
      var parts = k.split('|');
      if (parts[1] !== f[0] || parts[0].indexOf(month) !== 0) return;
      var s = map[k];
      if (s.in.length || s.out.length) present[parts[0]] = true;
      s.in.forEach(function (t) { var li = lateInfo_(f[0], t); if (li && li.late) lateCount++; });
    });
    leaves.forEach(function (lv) {
      if (lv.date.indexOf(month) !== 0 || lv.type === 'Holiday') return;
      if (lv.faculty === f[0] || lv.faculty === 'ALL') leave[lv.date] = true;
    });
    var p = Object.keys(present).length, l = Object.keys(leave).length;
    return [f[0], f[1], workingDays, p, Math.max(0, workingDays - p - l), l, lateCount];
  });

  var start = 5, last = sh.getLastRow();
  if (last >= start) sh.getRange(start, 1, last - start + 1, 7).clearContent();
  if (out.length) sh.getRange(start, 1, out.length, 7).setValues(out);
  sh.getRange('E2').setValue('(updated ' + fmtDateTime_(new Date()) + ')');
}

function refreshAll() { buildDailyDashboard(); buildMonthlyReport(); }

/* ============================ TRIGGERS / MENU ============================ */

function onFormSubmit(e) { refreshAll(); }

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Pinak Attendance')
    .addItem('Refresh dashboards', 'refreshAll')
    .addItem('Show links (Form / QR)', 'showLinks')
    .addToUi();
}

function showLinks() {
  var props = PropertiesService.getScriptProperties();
  var form = FormApp.openById(props.getProperty(P_FORM));
  var qr = props.getProperty(P_QR);
  var msg = 'Form (for the QR): ' + form.getPublishedUrl() + '\n\nForm editor: ' + form.getEditUrl();
  if (qr) msg += '\n\nQR image: https://drive.google.com/file/d/' + qr + '/view';
  SpreadsheetApp.getUi().alert(msg);
}

function installTriggers_(form, ss) {
  var subs = false, daily = false;
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'onFormSubmit') subs = true;
    if (t.getHandlerFunction() === 'refreshAll') daily = true;
  });
  if (!subs) ScriptApp.newTrigger('onFormSubmit').forForm(form).onFormSubmit().create();
  if (!daily) ScriptApp.newTrigger('refreshAll').timeBased().everyDays(1).atHour(20).create();
}

/* ============================ QR ============================ */

function generateQrCode_(url) {
  try {
    var api = 'https://api.qrserver.com/v1/create-qr-code/?size=600x600&margin=16&data=' + encodeURIComponent(url);
    var blob = UrlFetchApp.fetch(api).getBlob().setName('Pinak Attendance QR.png');
    var props = PropertiesService.getScriptProperties(), old = props.getProperty(P_QR);
    if (old) { try { DriveApp.getFileById(old).setTrashed(true); } catch (e) {} }
    var file = DriveApp.createFile(blob);
    file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
    props.setProperty(P_QR, file.getId());
    return file.getId();
  } catch (err) {
    Logger.log('QR generation failed (' + err + '). Make one from the Form link manually.');
    return null;
  }
}

/* ============================ READ HELPERS ============================ */

function openSheet_() { return SpreadsheetApp.openById(PropertiesService.getScriptProperties().getProperty(P_SHEET)); }

function readResponses_(ss) {
  var sh = findResponsesSheet_(ss);
  if (!sh) return [];
  var vals = sh.getDataRange().getValues();
  if (vals.length < 2) return [];
  var col = indexer_(vals[0]);
  var ci = col('Timestamp'), cf = col('Faculty Name'), ca = col('Action');
  var out = [];
  for (var i = 1; i < vals.length; i++) {
    if (!vals[i][ci]) continue;
    out.push({ timestamp: new Date(vals[i][ci]), faculty: String(vals[i][cf]).trim(), action: String(vals[i][ca]).trim() });
  }
  return out;
}

function readCorrections_(ss) {
  var vals = ss.getSheetByName('Corrections').getDataRange().getValues();
  var out = [];
  for (var i = 1; i < vals.length; i++) {
    var r = vals[i];
    if (!r[0]) continue;
    out.push({ date: normDate_(r[0]), faculty: String(r[1]).trim(), action: String(r[2]).trim(),
               time: normTime_(r[3]), mode: (String(r[4]).trim().toUpperCase() || 'SET') });
  }
  return out;
}

function readLeave_(ss) {
  var vals = ss.getSheetByName('Leave').getDataRange().getValues();
  var out = [];
  for (var i = 1; i < vals.length; i++) {
    if (!vals[i][0]) continue;
    out.push({ date: normDate_(vals[i][0]), faculty: String(vals[i][1]).trim(), type: String(vals[i][2]).trim() });
  }
  return out;
}

function isOnLeave_(ss, date, faculty) {
  return readLeave_(ss).some(function (lv) {
    return lv.date === date && (lv.faculty === faculty || lv.faculty === 'ALL');
  });
}

/* ============================ UTILITIES ============================ */

function getOrCreate_(ss, name) { return ss.getSheetByName(name) || ss.insertSheet(name); }

function removeDefaultSheet1_(ss) {
  var s = ss.getSheetByName('Sheet1');
  if (s && ss.getSheets().length > 1) { try { ss.deleteSheet(s); } catch (e) {} }
}

function findResponsesSheet_(ss) {
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) if (/form responses/i.test(sheets[i].getName())) return sheets[i];
  var ours = { Leave: 1, Corrections: 1, 'Daily Dashboard': 1, 'Monthly Report': 1 };
  for (var j = 0; j < sheets.length; j++) {
    if (ours[sheets[j].getName()]) continue;
    if (String(sheets[j].getRange(1, 1).getValue()).trim() === 'Timestamp') return sheets[j];
  }
  return null;
}

function indexer_(head) {
  return function (name) { for (var i = 0; i < head.length; i++) if (String(head[i]).trim() === name) return i; return -1; };
}

function workingDaysInMonth_(month, leaves) {
  var p = month.split('-'), y = parseInt(p[0], 10), m = parseInt(p[1], 10);
  if (!y || !m) return 0;
  var holidays = {};
  leaves.forEach(function (lv) { if (lv.type === 'Holiday' && lv.date.indexOf(month) === 0) holidays[lv.date] = true; });
  var count = 0, d = new Date(y, m - 1, 1);
  while (d.getMonth() === m - 1) {
    var dow = d.getDay() === 0 ? 7 : d.getDay();
    if (WORKING_DAYS.indexOf(dow) !== -1 && !holidays[fmtDate_(d)]) count++;
    d.setDate(d.getDate() + 1);
  }
  return count;
}

function colorDaily_(sh, start, rows) {
  for (var i = 0; i < rows.length; i++) {
    var status = rows[i][5], late = rows[i][4], bg;
    if (status === 'Absent') bg = '#f4cccc';
    else if (status === 'Complete') bg = '#d9ead3';
    else if (status === 'Leave') bg = '#cfe2f3';
    else bg = '#fff2cc';
    sh.getRange(start + i, 1, 1, 6).setBackground(bg);
    if (late.indexOf('LATE') === 0) sh.getRange(start + i, 5).setFontColor('#cc0000').setFontWeight('bold');
  }
}

function fmtDate_(d) { return Utilities.formatDate(d, TIMEZONE, 'yyyy-MM-dd'); }
function fmtTime_(d) { return Utilities.formatDate(d, TIMEZONE, 'HH:mm'); }
function fmtDateTime_(d) { return Utilities.formatDate(d, TIMEZONE, 'yyyy-MM-dd HH:mm'); }
function todayStr_() { return fmtDate_(new Date()); }
function monthStr_() { return Utilities.formatDate(new Date(), TIMEZONE, 'yyyy-MM'); }

function normDate_(v) { return (v instanceof Date) ? fmtDate_(v) : String(v).trim(); }
function normTime_(v) {
  if (v instanceof Date) return fmtTime_(v);
  var m = String(v).trim().match(/^(\d{1,2}):(\d{2})/);
  return m ? ('0' + m[1]).slice(-2) + ':' + m[2] : String(v).trim();
}
