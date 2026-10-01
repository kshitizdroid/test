#!/usr/bin/env python3
"""
Umeed — a tiny, dependency-free app for organising cleanliness drives.

Why this exists
---------------
NGO drives are currently coordinated on WhatsApp: a drive is announced and then
dozens of "+1 / add my name" messages bury the thread. Umeed replaces that with
a shared app where the manager announces a drive once and members tap a single
button to say whether they are coming. Each drive shows a clean, de-duplicated
attendee list.

Design goals
------------
* **Light to run.** Locally it uses the Python standard library only (http.server
  + sqlite3) — `python3 server.py` with no pip, no venv, no external DB.
* **Persistent in production.** If a `DATABASE_URL` environment variable is set
  (e.g. a free Neon/Render Postgres), the app uses Postgres instead of the local
  SQLite file, so members and drives survive restarts and redeploys. The only
  extra dependency, `pg8000` (a pure-Python Postgres driver), is used only on
  that path.
* **Mobile-first.** The frontend (served from ./frontend) is a small single-page
  app that works well on the phones NGO members already use.
* **Honest MVP.** Real push/WhatsApp delivery is not wired up yet; reminders are
  surfaced in-app and there is a documented hook (`notify`) + a `--send-reminders`
  command so a developer can connect a provider later without touching the core.

Run it:     python3 server.py
Reminders:  python3 server.py --send-reminders    (dry-run preview of reminders)
Config:     UMEED_MANAGER_PASSCODE, UMEED_PORT, UMEED_DB, DATABASE_URL (env vars)
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
DEFAULT_DB = BASE_DIR / "data" / "umeed.db"

DB_PATH = Path(os.environ.get("UMEED_DB", str(DEFAULT_DB)))
# When DATABASE_URL is set we use Postgres (persistent); otherwise local SQLite.
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_PG = bool(DATABASE_URL)
# Hosting platforms (Render, Railway, Heroku, …) tell the app which port to use
# via $PORT. Fall back to $UMEED_PORT, then 8000 for local use.
PORT = int(os.environ.get("PORT") or os.environ.get("UMEED_PORT") or "8000")
# The passcode that turns an ordinary member into a manager (drive organiser).
# CHANGE THIS in production via the UMEED_MANAGER_PASSCODE environment variable.
MANAGER_PASSCODE = os.environ.get("UMEED_MANAGER_PASSCODE", "umeed2025")

# A drive is considered "soon" (reminder-worthy) within this window.
REMINDER_WINDOW_HOURS = 48

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webmanifest": "application/manifest+json",
}


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def normalize_phone(raw: str) -> str:
    """Keep digits and a single leading + so the same person maps to one record.

    This is deliberately forgiving (NGO members type numbers many ways) rather
    than strictly validating country codes.
    """
    raw = (raw or "").strip()
    plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    return ("+" if plus else "") + digits


def parse_dt(value: str) -> datetime | None:
    """Parse an ISO-8601 string (incl. the 'YYYY-MM-DDTHH:MM' from <input>)."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


# --------------------------------------------------------------------------- #
# Database — works with SQLite (local) or Postgres (production, via DATABASE_URL)
# --------------------------------------------------------------------------- #
# The app code is written once using '?' placeholders and standard SQL. The thin
# layer below translates placeholders for Postgres and returns rows as plain
# dicts from either backend, so nothing above here needs to know which is in use.

def _schema_statements() -> list[str]:
    # The only dialect difference is how an auto-incrementing primary key is
    # declared. Booleans are stored as 0/1 integers in both to keep code uniform.
    pk = "SERIAL PRIMARY KEY" if USE_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"
    return [
        f"""CREATE TABLE IF NOT EXISTS members (
            id          {pk},
            name        TEXT NOT NULL,
            phone       TEXT NOT NULL UNIQUE,
            is_manager  INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS drives (
            id           {pk},
            title        TEXT NOT NULL,
            description  TEXT NOT NULL DEFAULT '',
            location     TEXT NOT NULL DEFAULT '',
            start_time   TEXT NOT NULL,
            end_time     TEXT,
            cancelled    INTEGER NOT NULL DEFAULT 0,
            created_by   INTEGER,
            created_at   TEXT NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS rsvps (
            id          {pk},
            drive_id    INTEGER NOT NULL,
            member_id   INTEGER NOT NULL,
            status      TEXT NOT NULL CHECK (status IN ('going','maybe','no')),
            updated_at  TEXT NOT NULL,
            UNIQUE (drive_id, member_id),
            FOREIGN KEY (drive_id)  REFERENCES drives(id)  ON DELETE CASCADE,
            FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
        )""",
    ]


_local = threading.local()


def _pg_connect():
    """Open a new Postgres connection from DATABASE_URL (pure-Python pg8000).

    SSL is used by default (hosted databases such as Neon require it). Append
    ?sslmode=disable to the URL to turn it off (e.g. for a local Postgres).
    """
    import ssl
    import pg8000.dbapi
    from urllib.parse import urlparse, unquote, parse_qs

    u = urlparse(DATABASE_URL)
    sslmode = (parse_qs(u.query).get("sslmode", ["require"])[0]).lower()
    ssl_context = None if sslmode in ("disable", "allow") else ssl.create_default_context()
    return pg8000.dbapi.connect(
        user=unquote(u.username or ""),
        password=unquote(u.password or ""),
        host=u.hostname,
        port=u.port or 5432,
        database=(u.path or "/").lstrip("/"),
        ssl_context=ssl_context,
    )


def open_conn():
    """Get a connection to use for one request.

    SQLite: one long-lived connection per thread. Postgres: a fresh connection
    per request (simple and robust against idle-timeouts on serverless hosts).
    """
    if USE_PG:
        return _pg_connect()
    conn = getattr(_local, "conn", None)
    if conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("PRAGMA foreign_keys = ON")
        _local.conn = conn
    return conn


def close_conn(conn) -> None:
    if USE_PG and conn is not None:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    # SQLite connections are reused per-thread, so we leave them open.


def _sql(sql: str) -> str:
    return sql.replace("?", "%s") if USE_PG else sql


def fetch_all(conn, sql: str, params: tuple = ()) -> list[dict]:
    cur = conn.cursor()
    try:
        cur.execute(_sql(sql), params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        cur.close()


def fetch_one(conn, sql: str, params: tuple = ()) -> dict | None:
    cur = conn.cursor()
    try:
        cur.execute(_sql(sql), params)
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))
    finally:
        cur.close()


def execute(conn, sql: str, params: tuple = ()) -> None:
    """Run a write (INSERT/UPDATE/DELETE/DDL) and commit."""
    cur = conn.cursor()
    try:
        cur.execute(_sql(sql), params)
        conn.commit()
    finally:
        cur.close()


def insert_returning_id(conn, sql: str, params: tuple = ()) -> int:
    """Run an INSERT that ends in 'RETURNING id' and return the new id."""
    cur = conn.cursor()
    try:
        cur.execute(_sql(sql), params)
        new_id = cur.fetchone()[0]
        conn.commit()
        return new_id
    finally:
        cur.close()


def init_db() -> None:
    conn = open_conn()
    try:
        for stmt in _schema_statements():
            execute(conn, stmt)
    finally:
        close_conn(conn)


# --------------------------------------------------------------------------- #
# Serialisation
# --------------------------------------------------------------------------- #

def member_public(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "phone": row["phone"],
        "is_manager": bool(row["is_manager"]),
    }


def drive_summary(conn, row: dict, member_id: int | None) -> dict:
    counts = {"going": 0, "maybe": 0, "no": 0}
    for r in fetch_all(
        conn,
        "SELECT status, COUNT(*) c FROM rsvps WHERE drive_id=? GROUP BY status",
        (row["id"],),
    ):
        counts[r["status"]] = r["c"]

    my_status = None
    if member_id is not None:
        mr = fetch_one(
            conn,
            "SELECT status FROM rsvps WHERE drive_id=? AND member_id=?",
            (row["id"], member_id),
        )
        my_status = mr["status"] if mr else None

    start = parse_dt(row["start_time"])
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "location": row["location"],
        "start_time": row["start_time"],
        "end_time": row["end_time"],
        "cancelled": bool(row["cancelled"]),
        "is_past": bool(start and start < now_utc()),
        "counts": counts,
        "my_status": my_status,
    }


# --------------------------------------------------------------------------- #
# Auth: lightweight, phone-based
# --------------------------------------------------------------------------- #
# Members identify themselves with their member id + phone (stored in the
# browser after joining) and send both on each request. This is intentionally
# light for an MVP; see README "Security notes" before using with sensitive data.

def current_member(conn, handler: "Handler") -> dict | None:
    mid = handler.headers.get("X-Member-Id")
    phone = handler.headers.get("X-Member-Phone")
    if not mid or not phone:
        return None
    try:
        mid_int = int(mid)
    except ValueError:
        return None
    row = fetch_one(conn, "SELECT * FROM members WHERE id=?", (mid_int,))
    if row and row["phone"] == normalize_phone(phone):
        return row
    return None


def require_member(conn, handler) -> dict:
    m = current_member(conn, handler)
    if not m:
        raise ApiError(401, "Please join first.")
    return m


def require_manager(conn, handler) -> dict:
    m = require_member(conn, handler)
    if not m["is_manager"]:
        raise ApiError(403, "Only a manager can do that.")
    return m


# --------------------------------------------------------------------------- #
# API handlers (return a JSON-serialisable object; raise ApiError on failure)
# --------------------------------------------------------------------------- #

def api_join(conn, handler, body, params):
    name = (body.get("name") or "").strip()
    phone = normalize_phone(body.get("phone", ""))
    if not name:
        raise ApiError(400, "Name is required.")
    if len(phone.lstrip("+")) < 7:
        raise ApiError(400, "Please enter a valid phone number.")

    existing = fetch_one(conn, "SELECT * FROM members WHERE phone=?", (phone,))
    if existing:
        # Returning member — update their display name if it changed, then log in.
        if existing["name"] != name:
            execute(conn, "UPDATE members SET name=? WHERE id=?", (name, existing["id"]))
            existing = fetch_one(conn, "SELECT * FROM members WHERE id=?", (existing["id"],))
        return {"member": member_public(existing), "returning": True}

    new_id = insert_returning_id(
        conn,
        "INSERT INTO members (name, phone, is_manager, created_at) VALUES (?,?,0,?) RETURNING id",
        (name, phone, iso(now_utc())),
    )
    row = fetch_one(conn, "SELECT * FROM members WHERE id=?", (new_id,))
    return {"member": member_public(row), "returning": False}


def api_unlock_manager(conn, handler, body, params):
    m = require_member(conn, handler)
    if (body.get("passcode") or "") != MANAGER_PASSCODE:
        raise ApiError(403, "Incorrect manager passcode.")
    execute(conn, "UPDATE members SET is_manager=1 WHERE id=?", (m["id"],))
    row = fetch_one(conn, "SELECT * FROM members WHERE id=?", (m["id"],))
    return {"member": member_public(row)}


def api_list_drives(conn, handler, body, params):
    me = current_member(conn, handler)
    scope = (params.get("scope", ["upcoming"])[0]).lower()
    rows = fetch_all(conn, "SELECT * FROM drives ORDER BY start_time ASC")
    drives = [drive_summary(conn, r, me["id"] if me else None) for r in rows]

    if scope == "upcoming":
        drives = [d for d in drives if not d["is_past"]]
    elif scope == "past":
        drives = [d for d in drives if d["is_past"]]
        drives.reverse()  # most recent past first
    # scope == "all" -> everything, chronological
    return {"drives": drives}


def api_create_drive(conn, handler, body, params):
    mgr = require_manager(conn, handler)
    title = (body.get("title") or "").strip()
    start = parse_dt(body.get("start_time", ""))
    if not title:
        raise ApiError(400, "Drive title is required.")
    if not start:
        raise ApiError(400, "A valid date & time is required.")
    end = parse_dt(body.get("end_time", "")) if body.get("end_time") else None

    new_id = insert_returning_id(
        conn,
        """INSERT INTO drives (title, description, location, start_time, end_time, created_by, created_at)
           VALUES (?,?,?,?,?,?,?) RETURNING id""",
        (
            title,
            (body.get("description") or "").strip(),
            (body.get("location") or "").strip(),
            iso(start),
            iso(end) if end else None,
            mgr["id"],
            iso(now_utc()),
        ),
    )
    row = fetch_one(conn, "SELECT * FROM drives WHERE id=?", (new_id,))
    return {"drive": drive_summary(conn, row, mgr["id"])}


def api_get_drive(conn, handler, body, params, drive_id):
    me = current_member(conn, handler)
    row = fetch_one(conn, "SELECT * FROM drives WHERE id=?", (drive_id,))
    if not row:
        raise ApiError(404, "Drive not found.")
    detail = drive_summary(conn, row, me["id"] if me else None)

    # Attendee lists grouped by status (names only — the clean replacement for
    # the WhatsApp pile-up).
    attendees = {"going": [], "maybe": [], "no": []}
    for r in fetch_all(
        conn,
        """SELECT m.name, r.status FROM rsvps r
           JOIN members m ON m.id = r.member_id
           WHERE r.drive_id=? ORDER BY r.updated_at ASC""",
        (drive_id,),
    ):
        attendees[r["status"]].append(r["name"])
    detail["attendees"] = attendees
    return {"drive": detail}


def api_update_drive(conn, handler, body, params, drive_id):
    require_manager(conn, handler)
    row = fetch_one(conn, "SELECT * FROM drives WHERE id=?", (drive_id,))
    if not row:
        raise ApiError(404, "Drive not found.")

    fields, values = [], []
    if "title" in body:
        title = (body.get("title") or "").strip()
        if not title:
            raise ApiError(400, "Drive title cannot be empty.")
        fields.append("title=?"); values.append(title)
    for key in ("description", "location"):
        if key in body:
            fields.append(f"{key}=?"); values.append((body.get(key) or "").strip())
    if "start_time" in body:
        start = parse_dt(body.get("start_time", ""))
        if not start:
            raise ApiError(400, "A valid date & time is required.")
        fields.append("start_time=?"); values.append(iso(start))
    if "end_time" in body:
        end = parse_dt(body.get("end_time", "")) if body.get("end_time") else None
        fields.append("end_time=?"); values.append(iso(end) if end else None)
    if "cancelled" in body:
        fields.append("cancelled=?"); values.append(1 if body.get("cancelled") else 0)

    if fields:
        values.append(drive_id)
        execute(conn, f"UPDATE drives SET {', '.join(fields)} WHERE id=?", tuple(values))
    row = fetch_one(conn, "SELECT * FROM drives WHERE id=?", (drive_id,))
    return {"drive": drive_summary(conn, row, None)}


def api_rsvp(conn, handler, body, params, drive_id):
    me = require_member(conn, handler)
    status = (body.get("status") or "").lower()
    if status not in ("going", "maybe", "no"):
        raise ApiError(400, "Status must be one of: going, maybe, no.")
    drive = fetch_one(conn, "SELECT * FROM drives WHERE id=?", (drive_id,))
    if not drive:
        raise ApiError(404, "Drive not found.")

    execute(
        conn,
        """INSERT INTO rsvps (drive_id, member_id, status, updated_at)
           VALUES (?,?,?,?)
           ON CONFLICT(drive_id, member_id)
           DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at""",
        (drive_id, me["id"], status, iso(now_utc())),
    )
    row = fetch_one(conn, "SELECT * FROM drives WHERE id=?", (drive_id,))
    return {"drive": drive_summary(conn, row, me["id"])}


def api_list_members(conn, handler, body, params):
    require_manager(conn, handler)
    rows = fetch_all(conn, "SELECT * FROM members ORDER BY LOWER(name)")
    return {"members": [member_public(r) for r in rows]}


def api_reminders(conn, handler, body, params):
    """In-app reminders for the current member: soon-upcoming drives plus whether
    they still need to RSVP."""
    me = require_member(conn, handler)
    window_end = now_utc() + timedelta(hours=REMINDER_WINDOW_HOURS)
    out = []
    for row in fetch_all(conn, "SELECT * FROM drives WHERE cancelled=0 ORDER BY start_time ASC"):
        start = parse_dt(row["start_time"])
        if not start or start < now_utc() or start > window_end:
            continue
        mr = fetch_one(
            conn,
            "SELECT status FROM rsvps WHERE drive_id=? AND member_id=?",
            (row["id"], me["id"]),
        )
        out.append({
            "drive_id": row["id"],
            "title": row["title"],
            "start_time": row["start_time"],
            "location": row["location"],
            "my_status": mr["status"] if mr else None,
            "needs_rsvp": mr is None,
        })
    return {"reminders": out}


# --------------------------------------------------------------------------- #
# Notification hook (stub)
# --------------------------------------------------------------------------- #

def notify(member: dict, message: str) -> None:
    """Deliver a reminder to a member.

    MVP behaviour: print to stdout. To go live, replace the body with a call to
    your provider of choice — e.g. WhatsApp Cloud API, Twilio SMS, or Web Push —
    using `member["phone"]`. Keeping delivery behind this one function means the
    rest of the app does not change when you wire up a real channel.
    """
    print(f"[reminder] -> {member['name']} ({member['phone']}): {message}")


def collect_and_send_reminders(dry_run: bool = True) -> list[str]:
    """Build reminder messages for every member with a drive in the next
    REMINDER_WINDOW_HOURS and (unless dry_run) deliver them via notify().

    Intended to be run from a scheduler (cron / systemd timer):
        python3 server.py --send-reminders
    """
    init_db()
    conn = open_conn()
    messages: list[str] = []
    window_end = now_utc() + timedelta(hours=REMINDER_WINDOW_HOURS)
    try:
        members = fetch_all(conn, "SELECT * FROM members")
        drives = fetch_all(
            conn, "SELECT * FROM drives WHERE cancelled=0 ORDER BY start_time ASC"
        )
        for drive in drives:
            start = parse_dt(drive["start_time"])
            if not start or start < now_utc() or start > window_end:
                continue
            when = start.astimezone().strftime("%a %d %b, %I:%M %p")
            for member in members:
                rsvp = fetch_one(
                    conn,
                    "SELECT status FROM rsvps WHERE drive_id=? AND member_id=?",
                    (drive["id"], member["id"]),
                )
                if rsvp and rsvp["status"] == "no":
                    continue  # don't nag people who already declined
                if rsvp and rsvp["status"] == "going":
                    msg = f"Reminder: '{drive['title']}' is coming up on {when}. See you there!"
                else:
                    msg = (f"'{drive['title']}' is on {when}"
                           f"{' at ' + drive['location'] if drive['location'] else ''}. "
                           f"Are you joining? Open Umeed to RSVP.")
                messages.append(f"{member['name']}: {msg}")
                if not dry_run:
                    notify(member, msg)
    finally:
        close_conn(conn)
    return messages


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #
# Each route: (METHOD, compiled-path-regex, handler). Named groups in the regex
# are passed to the handler as keyword arguments (coerced to int for *_id).

ROUTES = [
    ("POST", r"^/api/join$", api_join),
    ("POST", r"^/api/manager/unlock$", api_unlock_manager),
    ("GET",  r"^/api/drives$", api_list_drives),
    ("POST", r"^/api/drives$", api_create_drive),
    ("GET",  r"^/api/drives/(?P<drive_id>\d+)$", api_get_drive),
    ("PATCH", r"^/api/drives/(?P<drive_id>\d+)$", api_update_drive),
    ("POST", r"^/api/drives/(?P<drive_id>\d+)/rsvp$", api_rsvp),
    ("GET",  r"^/api/members$", api_list_members),
    ("GET",  r"^/api/reminders$", api_reminders),
]
COMPILED = [(m, re.compile(p), fn) for (m, p, fn) in ROUTES]


class Handler(BaseHTTPRequestHandler):
    server_version = "Umeed/1.0"

    # -- plumbing ---------------------------------------------------------- #
    def log_message(self, fmt, *args):  # quieter, single-line logs
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send_json(self, status: int, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "Request body must be valid JSON.")
        if not isinstance(parsed, dict):
            raise ApiError(400, "Request body must be a JSON object.")
        return parsed

    # -- dispatch ---------------------------------------------------------- #
    def _dispatch(self, method: str):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/"):
            params = parse_qs(parsed.query)
            for m, pattern, fn in COMPILED:
                if m != method:
                    continue
                match = pattern.match(path)
                if not match:
                    continue
                conn = None
                try:
                    conn = open_conn()
                    body = self._read_body() if method in ("POST", "PATCH") else {}
                    kwargs = {k: int(v) for k, v in match.groupdict().items()}
                    result = fn(conn, self, body, params, **kwargs)
                    self._send_json(200, result)
                except ApiError as e:
                    self._send_json(e.status, {"error": e.message})
                except Exception as e:  # noqa: BLE001 - last-resort guard
                    sys.stderr.write(f"[error] {method} {path}: {e!r}\n")
                    self._send_json(500, {"error": "Something went wrong."})
                finally:
                    close_conn(conn)
                return
            self._send_json(404, {"error": "Not found."})
            return

        # Non-API -> static files
        if method in ("GET", "HEAD"):
            self._serve_static(path)
        else:
            self._send_json(405, {"error": "Method not allowed."})

    def _serve_static(self, path: str):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (FRONTEND_DIR / rel).resolve()
        # Prevent path traversal outside the frontend directory.
        if FRONTEND_DIR not in target.parents and target != FRONTEND_DIR:
            self.send_error(403, "Forbidden")
            return
        if not target.is_file():
            target = FRONTEND_DIR / "index.html"  # SPA fallback
            if not target.is_file():
                self.send_error(404, "Not found")
                return
        ctype = STATIC_TYPES.get(target.suffix, "application/octet-stream")
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    # -- verbs ------------------------------------------------------------- #
    def do_GET(self):    self._dispatch("GET")
    def do_HEAD(self):   self._dispatch("HEAD")
    def do_POST(self):   self._dispatch("POST")
    def do_PATCH(self):  self._dispatch("PATCH")


# --------------------------------------------------------------------------- #
# Entrypoint
# --------------------------------------------------------------------------- #

def serve():
    init_db()
    if MANAGER_PASSCODE == "umeed2025":
        print("WARNING: using the default manager passcode. Set UMEED_MANAGER_PASSCODE "
              "to something private before sharing this app.")
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Umeed is running  ->  http://localhost:{PORT}")
    if USE_PG:
        print("Database: Postgres (persistent, via DATABASE_URL)")
    else:
        print(f"Database: SQLite file at {DB_PATH} (set DATABASE_URL for persistent Postgres)")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Umeed. Bye!")
        server.shutdown()


def main(argv: list[str]) -> int:
    if "--send-reminders" in argv:
        dry = "--live" not in argv
        msgs = collect_and_send_reminders(dry_run=dry)
        header = "DRY RUN (no messages sent) — pass --live to actually send:" if dry \
            else "Sent reminders:"
        print(header)
        if not msgs:
            print("  (no upcoming drives within the reminder window)")
        for m in msgs:
            print("  -", m)
        return 0
    serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
