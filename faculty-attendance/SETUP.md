# Pinak Institute — Faculty Attendance (simple version)

QR-based attendance on Google Forms + Sheets. Faculty scan one QR, **tap their
name** (shown as options, not a dropdown), tap **Check-in** or **Check-out**,
submit. Date & time are captured automatically. No shifts, no late rules — it
just records check-in / check-out for everyone.

Faculty: Prajjwal Gupta (Maths), Mohit Pal (Physics), Aakanksha (Biology),
Ajeet Sir (English). Week = Mon–Sat, Sunday off.

---

## I can't sign in for you
Signing in needs your password/2FA, which I never enter. That one click is
yours. After that, the script builds everything itself.

## Build / rebuild (in Apps Script)
1. Sign in to the owning Google account.
2. **https://script.google.com** → your project (or **New project**).
3. Paste the whole `Code.gs` (use **Ctrl/Cmd+A** to select all before copying — a
   partial paste causes "Unexpected end of input"). Save 💾.
4. Function dropdown → **`resetAndSetup`** (first time ever: `setupSystem`) → **Run** ▶.
   - `resetAndSetup` trashes the old Form/Sheet and builds the simple one → **new QR**.
5. Approve permissions (**Advanced → Go to… → Allow** — normal for your own code).
6. **View → Logs**: copy the **FORM (QR link)**, **SHEET**, **QR IMAGE** links.
7. Open the SHEET, reload once → the **"Pinak Attendance"** menu appears.

## The Form (2 questions only)
- **Faculty Name** — all four names shown as tappable options.
- **Action** — Check-in / Check-out.

## Sheet tabs
| Tab | Purpose |
|---|---|
| **Form Responses 1** | Raw submissions, append-only — originals, never edited. |
| **Leave** | Admin enters leave / institute holidays. |
| **Corrections** | Fix missed/wrong entries without touching originals. |
| **Daily Dashboard** | Pick a date → check-in, check-out, status per faculty. |
| **Monthly Report** | Pick a month → working days, present, absent, leave. |

## Daily use
- **Reception/management:** Daily Dashboard → set **Date** (B2) → **Pinak
  Attendance → Refresh dashboards**. 🟩 Complete · 🟨 missing in/out · 🟥 Absent · 🟦 Leave.
  (Also auto-refreshes at 8 PM so absences show without a submission.)
- **Corrections:** add a row in **Corrections** — `SET` = add/overwrite a time,
  `VOID` = cancel a wrong entry. Date `YYYY-MM-DD`, time `HH:MM`. Originals stay intact.
- **Leave/holidays:** enter in **Leave** (`ALL` + `Holiday` = institute closed).
- **Monthly:** Monthly Report → set **Month** `YYYY-MM` → Refresh dashboards.

## QR
A 600×600 PNG is saved to your Drive (link in Logs / menu → Show links). Print it
for reception. It just encodes the **FORM (QR link)** — any QR tool works too.
