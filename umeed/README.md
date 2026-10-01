# 🌱 Umeed — Cleanliness Drive Organiser

A tiny web app for NGOs that run regular cleanliness drives. It replaces the
WhatsApp "a drive is announced → 40 people type their name" chaos with a clean,
one-tap RSVP app.

- **The manager** announces a drive once (title, date/time, location, details).
- **Members** open the app and tap **Going / Maybe / Can't** — a single tap, no
  pile of messages.
- Every drive shows a **de-duplicated list of who's coming**.
- **In-app reminders** nudge members about drives in the next 48 hours, and there
  is a ready-to-wire hook for real WhatsApp/SMS/push reminders.

Built to be effortless to run: **no dependencies**, just Python 3. Data lives in a
single SQLite file.

---

## Quick start

```bash
cd umeed
./run.sh
# or:  python3 server.py
```

Open **http://localhost:8000** on your phone or computer.

> On the same Wi-Fi, members can reach it at `http://<your-computer-ip>:8000`.
> For real public access, see **Deploying** below.

### Try it out
1. Open the app and **join** with a name + phone number.
2. Open the account menu (top-right circle) → **Become a manager** → enter the
   passcode (default `umeed2025`).
3. Tap **+** to announce a drive.
4. Open the app as another "member" (e.g. an incognito window), join, and tap
   **Going** — watch the count and attendee list update.

---

## Configuration

All optional, set as environment variables:

| Variable                  | Default        | Purpose                                             |
| ------------------------- | -------------- | --------------------------------------------------- |
| `UMEED_MANAGER_PASSCODE`  | `umeed2025`    | Passcode that turns a member into a manager. **Change this.** |
| `UMEED_PORT`              | `8000`         | Port to listen on.                                  |
| `UMEED_DB`                | `data/umeed.db`| SQLite database file path.                          |

Example:

```bash
UMEED_MANAGER_PASSCODE="ourNGOsecret" UMEED_PORT=8080 ./run.sh
```

---

## Reminders

Members see upcoming-drive reminders **inside the app** automatically.

To preview the reminder messages that *would* be sent to each member:

```bash
python3 server.py --send-reminders          # dry run, prints messages
python3 server.py --send-reminders --live   # calls the notify() hook for real
```

Run it on a schedule (e.g. a daily cron job):

```cron
0 18 * * *  cd /path/to/umeed && python3 server.py --send-reminders --live
```

### Wiring up real WhatsApp / SMS / push
Delivery is isolated in one function — `notify(member, message)` in `server.py`.
It currently prints to the console. To go live, replace its body with a call to
your provider (WhatsApp Cloud API, Twilio SMS, Web Push, …) using
`member["phone"]`. Nothing else in the app needs to change.

---

## How it works

```
umeed/
├── server.py            # Backend: HTTP + JSON API + static file server (stdlib only)
├── frontend/
│   ├── index.html       # Single-page app shell
│   ├── styles.css       # Mobile-first styles (light + dark)
│   └── app.js           # UI logic, talks to the JSON API
├── tests/
│   └── test_api.py      # End-to-end API tests (no pytest required)
├── run.sh               # One-command launcher
└── data/umeed.db        # SQLite database (created on first run, git-ignored)
```

**Data model:** `members` (name, phone, is_manager), `drives` (title, time,
location, …), `rsvps` (one row per member per drive — updating is in-place, so
nobody's name ever appears twice).

### API summary

| Method | Path                      | Who        | Does                                  |
| ------ | ------------------------- | ---------- | ------------------------------------- |
| POST   | `/api/join`               | anyone     | Join / sign in with name + phone      |
| POST   | `/api/manager/unlock`     | member     | Become a manager with the passcode    |
| GET    | `/api/drives?scope=…`     | anyone     | List drives (`upcoming`/`past`/`all`) |
| POST   | `/api/drives`             | manager    | Announce a drive                      |
| GET    | `/api/drives/{id}`        | anyone     | Drive detail + attendee lists         |
| PATCH  | `/api/drives/{id}`        | manager    | Edit / cancel a drive                 |
| POST   | `/api/drives/{id}/rsvp`   | member     | Set your RSVP (going/maybe/no)        |
| GET    | `/api/members`            | manager    | List all members                      |
| GET    | `/api/reminders`          | member     | Your upcoming-drive reminders         |

---

## Running the tests

```bash
python3 tests/test_api.py      # plain
# or
pytest umeed/tests/            # if you have pytest
```

---

## Security notes (read before going public)

This is an MVP focused on getting your drives organised. Members are identified
by their member id + phone number stored on their device — light-touch by design,
suitable for a trusted community group. Before using it for anything sensitive or
exposing it widely, consider:

- **Phone-OTP or password login** instead of the current trust-based identity.
- **HTTPS** (put it behind a reverse proxy such as Caddy/Nginx, or a host that
  terminates TLS).
- Keeping the **manager passcode** private and rotating it if it leaks.

---

## Deploying

Because it is a single Python process with an SQLite file, Umeed runs anywhere
Python does:

- **A small VPS / home server:** `UMEED_MANAGER_PASSCODE=… python3 server.py`
  behind Nginx/Caddy for HTTPS.
- **A free/cheap PaaS:** start command `python3 server.py` (it reads `UMEED_PORT`),
  with a persistent volume for `data/umeed.db`.

Back up `data/umeed.db` to keep your members and drive history.
