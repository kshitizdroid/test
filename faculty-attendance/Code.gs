/**
 * Pinak Institute — Digital Faculty Attendance
 * ================================================
 * One Apps Script that builds the ENTIRE system in YOUR Google account:
 *   • A Google Form (the thing the QR code points to)
 *   • A linked Google Sheet with these tabs:
 *       - Form Responses 1   (raw, append-only — original records, never edited)
 *       - Config             (faculty + working hours + late rules)
 *       - Leave              (admin-declared leave / institute holidays)
 *       - Corrections        (fix missed/wrong entries WITHOUT touching originals)
 *       - Processed          (computed: effective time + late flag, rebuilt on each submit)
 *       - Daily Dashboard    (pick a date → attendance, late arrivals, missing entries)
 *       - Monthly Report     (pick a month → present / absent / leave / late per faculty)
 *   • A QR code image saved to your Drive (points at the Form)
 *   • Triggers so everything stays up to date automatically
 *
 * HOW TO USE
 *   1. Sign in to the Google account that will OWN this system.
 *   2. Go to https://script.google.com  →  New project.
 *   3. Delete the sample code, paste this whole file, Save.
 *   4. Run  ▶ setupSystem  once. Approve the permissions it asks for.
 *   5. Read the Logs (View → Logs). They print the Form link, Sheet link,
 *      and the QR image link. Print the QR and stick it at reception.
 *
 * After setup you never touch this editor again — manage everything from the
 * "Pinak Attendance" menu that appears inside the Sheet.
 */

/* ============================ CONFIGURATION ============================ *
 * Edit these if details change, then re-run setupSystem (safe to re-run —
 * it rewrites Config without deleting response history).
 * Times are 24-hour "HH:MM". "fixed" faculty get late detection;
 * "flexible" faculty are recorded only (no late flag, no absent penalty).
 */
var TIMEZONE = 'Asia/Kolkata';

// One row per faculty+session slot that we expect each working day.
var FACULTY_CONFIG = [
  // Faculty,          Subject,   Session,   Start,   End,     LateAfter, Type
  ['Prajjwal Gupta',  'Maths',   'Evening', '16:20', '19:30', '16:25',  'fixed'],
  ['Mohit Pal',       'Physics', 'Morning', '11:30', '13:00', '11:35',  'fixed'],
  ['Mohit Pal',       'Physics', 'Evening', '16:20', '19:30', '16:25',  'fixed'],
  ['Aakanksha',       'Biology', 'Flexible','',      '',      '',       'flexible'],
  ['Ajeet Sir',       'English', 'Flexible','',      '',      '',       'flexible']
];

// Working week: 1=Mon ... 6=Sat (Sunday excluded).
var WORKING_DAYS = [1, 2, 3, 4, 5, 6];

var FACULTY_NAMES = ['Prajjwal Gupta', 'Mohit Pal', 'Aakanksha', 'Ajeet Sir'];
var SESSIONS = ['Morning', 'Evening', 'Flexible'];
var ACTIONS = ['Check-in', 'Check-out'];

// Property keys (so the script remembers what it built).
var P_FORM = 'FORM_ID';
var P_SHEET = 'SHEET_ID';
var P_QR = 'QR_FILE_ID';

/* ============================ SETUP ============================ */

function setupSystem() {
  var props = PropertiesService.getScriptProperties();

  // ---- Spreadsheet ----
  var ss;
  var sid = props.getProperty(P_SHEET);
  if (sid) {
    try { ss = SpreadsheetApp.openById(sid); } catch (e) { ss = null; }
  }
  if (!ss) {
    ss = SpreadsheetApp.create('Pinak Institute — Faculty Attendance');
    props.setProperty(P_SHEET, ss.getId());
  }

  // ---- Form ----
  var form;
  var fid = props.getProperty(P_FORM);
  if (fid) {
    try { form = FormApp.openById(fid); } catch (e) { form = null; }
  }
  if (!form) {
    form = FormApp.create('Pinak Institute — Faculty Attendance');
    props.setProperty(P_FORM, form.getId());

    form.setDescription(
      'Scan this QR at reception from your own phone to mark attendance.\n' +
      '• Pick your name.\n' +
      '• Pick the session (Morning = 11:30 AM slot, Evening = 4:20 PM slot; ' +
      'flexible faculty just pick the slot you are attending).\n' +
      '• Pick Check-in or Check-out.\n' +
      'The date and time are recorded automatically when you submit.');

    form.setCollectEmail(false)          // faculty may not have Google accounts
        .setLimitOneResponsePerUser(false) // multiple submissions per day expected
        .setAllowResponseEdits(false)
        .setShowLinkToRespondAgain(true)
        .setConfirmationMessage('Recorded. Thank you!');

    var qName = form.addListItem();
    qName.setTitle('Faculty Name').setRequired(true)
         .setChoiceValues(FACULTY_NAMES);

    var qSession = form.addMultipleChoiceItem();
    qSession.setTitle('Session').setRequired(true)
            .setHelpText('Morning = 11:30 AM slot · Evening = 4:20 PM slot · ' +
                         'Flexible faculty pick either.')
            .setChoiceValues(SESSIONS);

    var qAction = form.addMultipleChoiceItem();
    qAction.setTitle('Action').setRequired(true)
           .setChoiceValues(ACTIONS);

    form.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId());
  }

  // Give the response tab a moment / normalise it.
  SpreadsheetApp.flush();

  buildConfigSheet_(ss);
  buildLeaveSheet_(ss);
  buildCorrectionsSheet_(ss);
  buildProcessedSheet_(ss);
  buildDailyDashboardSheet_(ss);
  buildMonthlyReportSheet_(ss);
  removeDefaultSheet1_(ss);

  installTriggers_(form, ss);
  rebuildProcessed();

  var qrId = generateQrCode_(form.getPublishedUrl());

  Logger.log('================ SETUP COMPLETE ================');
  Logger.log('FORM (edit):     ' + form.getEditUrl());
  Logger.log('FORM (QR link):  ' + form.getPublishedUrl());
  Logger.log('SHEET:           ' + ss.getUrl());
  if (qrId) Logger.log('QR IMAGE:        ' + 'https://drive.google.com/file/d/' + qrId + '/view');
  Logger.log('===============================================');
  Logger.log('Open the SHEET and use the "Pinak Attendance" menu from now on.');
}

/* ============================ SHEET BUILDERS ============================ */

function buildConfigSheet_(ss) {
  var sh = getOrCreate_(ss, 'Config');
  sh.clear();
  var header = ['Faculty', 'Subject', 'Session', 'Start', 'End', 'Late After', 'Type'];
  sh.getRange(1, 1, 1, header.length).setValues([header]).setFontWeight('bold');
  sh.getRange(2, 1, FACULTY_CONFIG.length, header.length).setValues(FACULTY_CONFIG);
  sh.setFrozenRows(1);
  sh.autoResizeColumns(1, header.length);
}

function buildLeaveSheet_(ss) {
  var sh = getOrCreate_(ss, 'Leave');
  if (sh.getLastRow() >= 1 && sh.getRange(1, 1).getValue() === 'Date') return; // keep data
  sh.clear();
  var header = ['Date', 'Faculty', 'Type', 'Note'];
  sh.getRange(1, 1, 1, header.length).setValues([header]).setFontWeight('bold');
  sh.getRange('A2').setNote('Date as YYYY-MM-DD. Type = Leave (one faculty) or Holiday ' +
    '(institute closed — use faculty "ALL"). Absent days are never counted against ' +
    'a faculty with a Leave/Holiday on that date.');
  sh.setFrozenRows(1);
  sh.autoResizeColumns(1, header.length);
}

function buildCorrectionsSheet_(ss) {
  var sh = getOrCreate_(ss, 'Corrections');
  if (sh.getLastRow() >= 1 && sh.getRange(1, 1).getValue() === 'Date') return; // keep data
  sh.clear();
  var header = ['Date', 'Faculty', 'Session', 'Action', 'Corrected Time', 'Mode', 'Reason', 'Approved By', 'Logged At'];
  sh.getRange(1, 1, 1, header.length).setValues([header]).setFontWeight('bold');
  sh.getRange('A2').setNote(
    'Fix missed / wrong entries here. Originals in "Form Responses 1" are NEVER changed.\n' +
    'Date = YYYY-MM-DD.  Corrected Time = HH:MM (24h).\n' +
    'Mode:\n' +
    '  SET   = add or overwrite this slot with Corrected Time (use for missed or wrong entries)\n' +
    '  VOID  = cancel a wrong entry for this slot (leave Corrected Time blank)\n' +
    'Reason + Approved By are required for the audit trail.');
  sh.setFrozenRows(1);
  sh.autoResizeColumns(1, header.length);
}

function buildProcessedSheet_(ss) {
  var sh = getOrCreate_(ss, 'Processed');
  sh.clear();
  var header = ['Date', 'Faculty', 'Subject', 'Session', 'Action',
                'Original Time', 'Effective Time', 'Late?', 'Source', 'Note'];
  sh.getRange(1, 1, 1, header.length).setValues([header]).setFontWeight('bold');
  sh.setFrozenRows(1);
}

function buildDailyDashboardSheet_(ss) {
  var sh = getOrCreate_(ss, 'Daily Dashboard');
  sh.clear();
  sh.getRange('A1').setValue('Daily Attendance Dashboard').setFontWeight('bold').setFontSize(14);
  sh.getRange('A2').setValue('Date:');
  sh.getRange('B2').setValue(todayStr_()).setNote('Type a date as YYYY-MM-DD, then menu → Refresh dashboards.');
  sh.getRange('A2').setFontWeight('bold');
  var header = ['Faculty', 'Subject', 'Session', 'Check-in', 'Late?', 'Check-out', 'Status'];
  sh.getRange(4, 1, 1, header.length).setValues([header]).setFontWeight('bold');
  sh.setFrozenRows(4);
  sh.autoResizeColumns(1, header.length);
}

function buildMonthlyReportSheet_(ss) {
  var sh = getOrCreate_(ss, 'Monthly Report');
  sh.clear();
  sh.getRange('A1').setValue('Monthly Attendance Report').setFontWeight('bold').setFontSize(14);
  sh.getRange('A2').setValue('Month:');
  sh.getRange('B2').setValue(monthStr_()).setNote('Type a month as YYYY-MM, then menu → Refresh dashboards.');
  sh.getRange('A2').setFontWeight('bold');
  var header = ['Faculty', 'Subject', 'Working Days', 'Present', 'Absent', 'Leave', 'Late Count'];
  sh.getRange(4, 1, 1, header.length).setValues([header]).setFontWeight('bold');
  sh.setFrozenRows(4);
  sh.autoResizeColumns(1, header.length);
}

/* ============================ CORE LOGIC ============================ */

/** Rebuilds the Processed sheet from raw responses + corrections. */
function rebuildProcessed() {
  var ss = openSheet_();
  var cfg = readConfig_(ss);                 // key faculty|session -> {lateAfter, type, subject}
  var records = {};                          // key date|faculty|session|action -> record

  // 1) Raw responses (originals, never edited).
  var resp = readResponses_(ss);
  resp.forEach(function (r) {
    var date = fmtDate_(r.timestamp);
    var time = fmtTime_(r.timestamp);
    var key = [date, r.faculty, r.session, r.action].join('|');
    records[key] = {
      date: date, faculty: r.faculty, session: r.session, action: r.action,
      original: time, effective: time, source: 'Form', note: ''
    };
  });

  // 2) Corrections override (originals preserved above and in Form Responses 1).
  var corr = readCorrections_(ss);
  corr.forEach(function (c) {
    var key = [c.date, c.faculty, c.session, c.action].join('|');
    var existing = records[key];
    if (c.mode === 'VOID') {
      if (existing) {
        existing.effective = '';
        existing.source = 'Correction (VOID)';
        existing.note = c.reason + ' — by ' + c.approvedBy;
      }
      return;
    }
    // SET (default): add missing or overwrite wrong.
    if (existing) {
      existing.effective = c.time;
      existing.source = 'Correction (SET)';
      existing.note = c.reason + ' — by ' + c.approvedBy;
    } else {
      records[key] = {
        date: c.date, faculty: c.faculty, session: c.session, action: c.action,
        original: '', effective: c.time, source: 'Correction (SET)',
        note: c.reason + ' — by ' + c.approvedBy
      };
    }
  });

  // 3) Flatten + compute late + sort.
  var rows = [];
  Object.keys(records).forEach(function (k) {
    var r = records[k];
    var subject = '', late = '';
    var slot = cfg[r.faculty + '|' + r.session];
    if (slot) subject = slot.subject;
    if (!subject) {
      var any = cfg[r.faculty + '|Flexible'];
      if (any) subject = any.subject;
    }
    if (slot && slot.type === 'fixed' && r.action === 'Check-in' && r.effective) {
      late = (r.effective > slot.lateAfter) ? 'LATE' : 'On time';
    }
    rows.push([r.date, r.faculty, subject, r.session, r.action,
               r.original, r.effective, late, r.source, r.note]);
  });

  rows.sort(function (a, b) {
    if (a[0] !== b[0]) return a[0] < b[0] ? -1 : 1;     // date
    if (a[1] !== b[1]) return a[1] < b[1] ? -1 : 1;     // faculty
    if (a[3] !== b[3]) return a[3] < b[3] ? -1 : 1;     // session
    return a[4] < b[4] ? -1 : 1;                        // action
  });

  var sh = ss.getSheetByName('Processed');
  var header = sh.getRange(1, 1, 1, 10).getValues();
  sh.clearContents();
  sh.getRange(1, 1, 1, 10).setValues(header).setFontWeight('bold');
  if (rows.length) sh.getRange(2, 1, rows.length, 10).setValues(rows);
}

/** Fills the Daily Dashboard for the date in B2. */
function buildDailyDashboard() {
  var ss = openSheet_();
  var sh = ss.getSheetByName('Daily Dashboard');
  var date = normDate_(sh.getRange('B2').getValue());
  var cfg = FACULTY_CONFIG;
  var proc = readProcessed_(ss);

  var out = [];
  cfg.forEach(function (c) {
    var faculty = c[0], subject = c[1], session = c[2];
    var inRec = findProc_(proc, date, faculty, session, 'Check-in');
    var outRec = findProc_(proc, date, faculty, session, 'Check-out');
    var inTime = inRec ? inRec.effective : '';
    var late = inRec ? inRec.late : '';
    var outTime = outRec ? outRec.effective : '';

    var status;
    if (!inTime && !outTime) status = isOnLeave_(ss, date, faculty) ? 'Leave' : 'Absent';
    else if (inTime && outTime) status = 'Complete';
    else if (inTime && !outTime) status = 'Missing check-out';
    else status = 'Missing check-in';

    out.push([faculty, subject, session, inTime, late, outTime, status]);
  });

  var startRow = 5;
  var lastRow = sh.getLastRow();
  if (lastRow >= startRow) sh.getRange(startRow, 1, lastRow - startRow + 1, 7).clearContent();
  if (out.length) {
    sh.getRange(startRow, 1, out.length, 7).setValues(out);
    colorDaily_(sh, startRow, out);
  }
  sh.getRange('D2').setValue('(updated ' + fmtDateTime_(new Date()) + ')');
}

/** Fills the Monthly Report for the month (YYYY-MM) in B2. */
function buildMonthlyReport() {
  var ss = openSheet_();
  var sh = ss.getSheetByName('Monthly Report');
  var month = String(sh.getRange('B2').getValue()).trim();  // YYYY-MM
  var proc = readProcessed_(ss);
  var leaves = readLeave_(ss);

  var workingDays = workingDaysInMonth_(month, leaves);  // Mon–Sat minus Holidays
  var faculties = uniqueFaculty_();

  var out = [];
  faculties.forEach(function (f) {
    var subject = subjectOf_(f);
    var presentDates = {}, lateCount = 0, leaveDates = {};

    proc.forEach(function (r) {
      if (r.faculty !== f) return;
      if (r.date.indexOf(month) !== 0) return;
      if (r.action === 'Check-in' && r.effective) presentDates[r.date] = true;
      if (r.late === 'LATE') lateCount++;
    });

    leaves.forEach(function (lv) {
      if (lv.date.indexOf(month) !== 0) return;
      if (lv.type === 'Holiday') return; // holidays reduce working days, not "leave" per faculty
      if (lv.faculty === f || lv.faculty === 'ALL') leaveDates[lv.date] = true;
    });

    var present = Object.keys(presentDates).length;
    var leave = Object.keys(leaveDates).length;
    var absent = Math.max(0, workingDays - present - leave);
    out.push([f, subject, workingDays, present, absent, leave, lateCount]);
  });

  var startRow = 5;
  var lastRow = sh.getLastRow();
  if (lastRow >= startRow) sh.getRange(startRow, 1, lastRow - startRow + 1, 7).clearContent();
  if (out.length) sh.getRange(startRow, 1, out.length, 7).setValues(out);
  sh.getRange('D2').setValue('(updated ' + fmtDateTime_(new Date()) + ')');
}

function refreshAll() {
  rebuildProcessed();
  buildDailyDashboard();
  buildMonthlyReport();
}

/* ============================ TRIGGERS / MENU ============================ */

function onFormSubmit(e) {
  refreshAll();
}

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Pinak Attendance')
    .addItem('Refresh dashboards', 'refreshAll')
    .addItem('Rebuild processed data', 'rebuildProcessed')
    .addSeparator()
    .addItem('Show links (Form / QR)', 'showLinks')
    .addToUi();
}

function showLinks() {
  var props = PropertiesService.getScriptProperties();
  var form = FormApp.openById(props.getProperty(P_FORM));
  var qr = props.getProperty(P_QR);
  var msg = 'Form (for the QR): ' + form.getPublishedUrl() +
            '\n\nForm editor: ' + form.getEditUrl();
  if (qr) msg += '\n\nQR image: https://drive.google.com/file/d/' + qr + '/view';
  SpreadsheetApp.getUi().alert(msg);
}

function installTriggers_(form, ss) {
  var existing = ScriptApp.getProjectTriggers();
  var haveSubmit = false, haveDaily = false;
  existing.forEach(function (t) {
    if (t.getHandlerFunction() === 'onFormSubmit') haveSubmit = true;
    if (t.getHandlerFunction() === 'buildDailyDashboard') haveDaily = true;
  });
  if (!haveSubmit) {
    ScriptApp.newTrigger('onFormSubmit').forForm(form).onFormSubmit().create();
  }
  if (!haveDaily) {
    // Daily safety rebuild so "Absent"/missing entries show even with no submission.
    ScriptApp.newTrigger('refreshAll').timeBased().everyDays(1).atHour(20).create();
  }
}

/* ============================ QR CODE ============================ */

function generateQrCode_(url) {
  try {
    var api = 'https://api.qrserver.com/v1/create-qr-code/?size=600x600&margin=16&data=' +
              encodeURIComponent(url);
    var blob = UrlFetchApp.fetch(api).getBlob().setName('Pinak Attendance QR.png');
    var props = PropertiesService.getScriptProperties();
    var oldId = props.getProperty(P_QR);
    if (oldId) { try { DriveApp.getFileById(oldId).setTrashed(true); } catch (e) {} }
    var file = DriveApp.createFile(blob);
    file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
    props.setProperty(P_QR, file.getId());
    return file.getId();
  } catch (err) {
    Logger.log('QR generation failed (' + err + '). Make one manually from the Form link.');
    return null;
  }
}

/* ============================ READ HELPERS ============================ */

function openSheet_() {
  return SpreadsheetApp.openById(PropertiesService.getScriptProperties().getProperty(P_SHEET));
}

function readConfig_(ss) {
  var sh = ss.getSheetByName('Config');
  var vals = sh.getDataRange().getValues();
  var map = {};
  for (var i = 1; i < vals.length; i++) {
    var r = vals[i];
    if (!r[0]) continue;
    map[r[0] + '|' + r[2]] = { subject: r[1], lateAfter: String(r[5]), type: r[6] };
  }
  return map;
}

function readResponses_(ss) {
  var sh = findResponsesSheet_(ss);
  if (!sh) return [];
  var vals = sh.getDataRange().getValues();
  if (vals.length < 2) return [];
  var head = vals[0];
  var col = indexer_(head);
  var ci = col('Timestamp'), cf = col('Faculty Name'), cs = col('Session'), ca = col('Action');
  var out = [];
  for (var i = 1; i < vals.length; i++) {
    var r = vals[i];
    if (!r[ci]) continue;
    out.push({
      timestamp: new Date(r[ci]),
      faculty: String(r[cf]).trim(),
      session: String(r[cs]).trim(),
      action: String(r[ca]).trim()
    });
  }
  return out;
}

function readCorrections_(ss) {
  var sh = ss.getSheetByName('Corrections');
  var vals = sh.getDataRange().getValues();
  var out = [];
  for (var i = 1; i < vals.length; i++) {
    var r = vals[i];
    if (!r[0]) continue;
    out.push({
      date: normDate_(r[0]), faculty: String(r[1]).trim(), session: String(r[2]).trim(),
      action: String(r[3]).trim(), time: normTime_(r[4]),
      mode: (String(r[5]).trim().toUpperCase() || 'SET'),
      reason: String(r[6]).trim(), approvedBy: String(r[7]).trim()
    });
  }
  return out;
}

function readLeave_(ss) {
  var sh = ss.getSheetByName('Leave');
  var vals = sh.getDataRange().getValues();
  var out = [];
  for (var i = 1; i < vals.length; i++) {
    var r = vals[i];
    if (!r[0]) continue;
    out.push({ date: normDate_(r[0]), faculty: String(r[1]).trim(), type: String(r[2]).trim() });
  }
  return out;
}

function readProcessed_(ss) {
  var sh = ss.getSheetByName('Processed');
  var vals = sh.getDataRange().getValues();
  var out = [];
  for (var i = 1; i < vals.length; i++) {
    var r = vals[i];
    if (!r[0]) continue;
    out.push({
      date: normDate_(r[0]), faculty: String(r[1]).trim(), session: String(r[3]).trim(),
      action: String(r[4]).trim(), effective: String(r[6]).trim(), late: String(r[7]).trim()
    });
  }
  return out;
}

function isOnLeave_(ss, date, faculty) {
  var leaves = readLeave_(ss);
  for (var i = 0; i < leaves.length; i++) {
    if (leaves[i].date === date && (leaves[i].faculty === faculty || leaves[i].faculty === 'ALL')) return true;
  }
  return false;
}

/* ============================ SMALL UTILITIES ============================ */

function getOrCreate_(ss, name) {
  return ss.getSheetByName(name) || ss.insertSheet(name);
}

function removeDefaultSheet1_(ss) {
  var s = ss.getSheetByName('Sheet1');
  if (s && ss.getSheets().length > 1) { try { ss.deleteSheet(s); } catch (e) {} }
}

function findResponsesSheet_(ss) {
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    var n = sheets[i].getName();
    if (/form responses/i.test(n)) return sheets[i];
  }
  // Fallback: a sheet whose A1 is "Timestamp" and isn't one of ours.
  var ours = {Config:1, Leave:1, Corrections:1, Processed:1, 'Daily Dashboard':1, 'Monthly Report':1};
  for (var j = 0; j < sheets.length; j++) {
    if (ours[sheets[j].getName()]) continue;
    if (String(sheets[j].getRange(1, 1).getValue()).trim() === 'Timestamp') return sheets[j];
  }
  return null;
}

function indexer_(headerRow) {
  return function (name) {
    for (var i = 0; i < headerRow.length; i++) {
      if (String(headerRow[i]).trim() === name) return i;
    }
    return -1;
  };
}

function findProc_(proc, date, faculty, session, action) {
  for (var i = 0; i < proc.length; i++) {
    var r = proc[i];
    if (r.date === date && r.faculty === faculty && r.session === session && r.action === action) return r;
  }
  return null;
}

function uniqueFaculty_() {
  var seen = {}, out = [];
  FACULTY_CONFIG.forEach(function (c) { if (!seen[c[0]]) { seen[c[0]] = 1; out.push(c[0]); } });
  return out;
}

function subjectOf_(faculty) {
  for (var i = 0; i < FACULTY_CONFIG.length; i++) if (FACULTY_CONFIG[i][0] === faculty) return FACULTY_CONFIG[i][1];
  return '';
}

function workingDaysInMonth_(month, leaves) {
  var parts = month.split('-');
  var y = parseInt(parts[0], 10), m = parseInt(parts[1], 10);
  if (!y || !m) return 0;
  var holidays = {};
  leaves.forEach(function (lv) {
    if (lv.type === 'Holiday' && lv.date.indexOf(month) === 0) holidays[lv.date] = true;
  });
  var count = 0;
  var d = new Date(y, m - 1, 1);
  while (d.getMonth() === m - 1) {
    var dow = d.getDay() === 0 ? 7 : d.getDay(); // 1..7, Sun=7
    var ds = fmtDate_(d);
    if (WORKING_DAYS.indexOf(dow) !== -1 && !holidays[ds]) count++;
    d.setDate(d.getDate() + 1);
  }
  return count;
}

function colorDaily_(sh, startRow, rows) {
  for (var i = 0; i < rows.length; i++) {
    var status = rows[i][6], late = rows[i][4];
    var bg = null;
    if (status === 'Absent') bg = '#f4cccc';
    else if (status === 'Complete') bg = '#d9ead3';
    else if (status === 'Leave') bg = '#cfe2f3';
    else bg = '#fff2cc'; // missing something
    sh.getRange(startRow + i, 1, 1, 7).setBackground(bg);
    if (late === 'LATE') sh.getRange(startRow + i, 5).setFontColor('#cc0000').setFontWeight('bold');
  }
}

/* ---- date/time formatting ---- */
function fmtDate_(d) { return Utilities.formatDate(d, TIMEZONE, 'yyyy-MM-dd'); }
function fmtTime_(d) { return Utilities.formatDate(d, TIMEZONE, 'HH:mm'); }
function fmtDateTime_(d) { return Utilities.formatDate(d, TIMEZONE, 'yyyy-MM-dd HH:mm'); }
function todayStr_() { return fmtDate_(new Date()); }
function monthStr_() { return Utilities.formatDate(new Date(), TIMEZONE, 'yyyy-MM'); }

function normDate_(v) {
  if (v instanceof Date) return fmtDate_(v);
  return String(v).trim();
}
function normTime_(v) {
  if (v instanceof Date) return fmtTime_(v);
  var s = String(v).trim();
  var m = s.match(/^(\d{1,2}):(\d{2})/);
  if (m) return ('0' + m[1]).slice(-2) + ':' + m[2];
  return s;
}
