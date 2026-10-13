# Pinak Institute — Faculty Attendance (build & run guide)

A QR-based faculty attendance system on Google Forms + Google Sheets.
Faculty scan one QR at reception from their own phones to mark **Check-in** /
**Check-out**; date & time are captured automatically. The Sheet computes a
daily dashboard, late arrivals, missing entries, corrections, and monthly reports.

---

## Why you (the owner) must do the first click

I can't sign in to your Google account for you — that needs your password / 2FA,
and I never enter anyone's credentials. So the sign-in in the browser panel is
your step. Once you're signed in, the script below builds **everything** itself
(Form, Sheet, all tabs, QR image, triggers). You won't have to create anything by hand.

---

## Build it (one time, ~3 minutes)

1. **Sign in** to the Google account that will own the system (the browser panel).
2. Open **https://script.google.com** → **New project**.
3. Delete the sample code. Open `Code.gs` from this folder, copy the **whole** file,
   paste it in, and **Save** (💾).
4. In the toolbar function dropdown pick **`setupSystem`** → click **Run** ▶.
5. Google asks for permissions the first time → **Review permissions** → choose your
   account → **Advanced** → **Go to (project) → Allow**. (Normal for your own scripts.)
6. Open **View → Logs** (or `Ctrl/Cmd+Enter`). You'll see three links:
   - **FORM (QR link)** — what the QR points to
   - **SHEET** — your dashboard workbook
   - **QR IMAGE** — a ready-made QR PNG in your Drive → print it, stick it at reception.

That's it. From now on you work **inside the Sheet**, using the **"Pinak Attendance"**
menu (it appears after you reload the Sheet). You never reopen the script editor.

> Changed a detail (hours, late rule, a name)? Edit the `FACULTY_CONFIG` block at the
> top of `Code.gs` and run `setupSystem` again — it's safe to re-run and keeps all
> response history.

---

## What gets built (tabs in the Sheet)

| Tab | What it's for |
|---|---|
| **Form Responses 1** | Raw submissions. Append-only. **Never edited** — your original record of truth. |
| **Config** | Faculty, subject, working hours, late threshold per session. |
| **Leave** | Admin enters leave / institute holidays here. |
| **Corrections** | Fix missed or wrong entries *without* touching originals. |
| **Processed** | Auto-computed: effective time (after corrections) + late flag. |
| **Daily Dashboard** | Pick a date → who's present, late arrivals, missing entries. |
| **Monthly Report** | Pick a month → present / absent / leave / late count per faculty. |

### Faculty rules baked in

| Faculty | Subject | Hours | Late after |
|---|---|---|---|
| Prajjwal Gupta | Maths | 4:20–7:30 PM (Evening) | 4:25 PM |
| Mohit Pal | Physics | 11:30 AM–1:00 PM (Morning) **and** 4:20–7:30 PM (Evening) | 11:35 AM / 4:25 PM |
| Aakanksha | Biology | Flexible | — (recorded only) |
| Ajeet Sir | English | Flexible | — (recorded only) |

Week = **Mon–Sat**, Sunday off. Mohit makes **four** submissions/day (check-in + check-out
for both sessions) by picking the matching **Session** each time.

---

## Daily operation

**Faculty:** scan the QR → pick **Name**, **Session**, **Check-in/Check-out** → submit. Done.

**Reception verification:** open **Daily Dashboard**, set **Date** (B2), run
**Pinak Attendance → Refresh dashboards**. Colour key:
- 🟩 Complete (in + out) · 🟨 Missing check-in/out · 🟥 Absent · 🟦 On leave · **LATE** in red.

**Management review:** same dashboard each evening; the daily safety-refresh also runs
automatically at 8 PM so "Absent"/missing rows appear even if nobody submitted.

---

## Correction process (originals preserved)

Never edit *Form Responses 1*. Instead add a row in **Corrections**:

| Column | Example | Meaning |
|---|---|---|
| Date | `2026-10-13` | the day being fixed |
| Faculty | `Mohit Pal` | |
| Session | `Morning` | `Morning` / `Evening` / `Flexible` |
| Action | `Check-in` | `Check-in` / `Check-out` |
| Corrected Time | `11:32` | 24-hour HH:MM (leave blank for VOID) |
| Mode | `SET` | `SET` = add/overwrite · `VOID` = cancel a wrong entry |
| Reason | `Phone battery died` | audit trail |
| Approved By | `Reception/Admin name` | audit trail |

Then **Refresh dashboards**. The *Processed* tab shows both **Original Time** and
**Effective Time**, and the **Source** column marks which rows were corrected — the
original submission stays untouched in *Form Responses 1*.

---

## Monthly report

Open **Monthly Report**, set **Month** (B2) as `YYYY-MM` (e.g. `2026-10`),
run **Refresh dashboards**. Per faculty you get: Working Days (Mon–Sat minus holidays),
Present, Absent, Leave, Late Count. Declare leave/holidays in the **Leave** tab first
(use faculty `ALL` + type `Holiday` for an institute-wide closure).

---

## QR code

The script saves a 600×600 PNG to your Drive (link in the Logs, and under
**Pinak Attendance → Show links**). If you'd rather regenerate it, the QR just needs
to encode the **FORM (QR link)** URL — any QR tool works.
