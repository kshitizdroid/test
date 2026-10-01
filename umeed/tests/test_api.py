"""End-to-end tests for the Umeed API.

Zero test dependencies: spins up the real server on an ephemeral port against a
temporary SQLite database and drives it over HTTP. Runs under pytest *or* as a
plain script:

    python3 tests/test_api.py
    pytest umeed/tests/
"""

import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

# Configure the server BEFORE importing it (config is read at import time).
_TMP = tempfile.mkdtemp(prefix="umeed-test-")
os.environ["UMEED_DB"] = str(Path(_TMP) / "test.db")
os.environ["UMEED_MANAGER_PASSCODE"] = "test-pass"
os.environ["UMEED_PORT"] = "0"

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402

BASE = None
_HTTPD = None


def _start_server():
    global BASE, _HTTPD
    if _HTTPD is not None:
        return
    server.init_db()
    _HTTPD = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    port = _HTTPD.server_address[1]
    BASE = f"http://127.0.0.1:{port}"
    threading.Thread(target=_HTTPD.serve_forever, daemon=True).start()
    time.sleep(0.1)


def call(method, path, body=None, member=None):
    """Return (status, json_dict)."""
    headers = {"Content-Type": "application/json"}
    if member:
        headers["X-Member-Id"] = str(member["id"])
        headers["X-Member-Phone"] = member["phone"]
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def test_full_flow():
    _start_server()

    # --- join (new member) ---
    st, data = call("POST", "/api/join", {"name": "Aarti", "phone": "+91 98765 43210"})
    assert st == 200, data
    assert data["returning"] is False
    aarti = data["member"]
    assert aarti["phone"] == "+919876543210"      # normalised
    assert aarti["is_manager"] is False

    # --- join again with same phone -> returning member, name updated ---
    st, data = call("POST", "/api/join", {"name": "Aarti S", "phone": "+919876543210"})
    assert st == 200 and data["returning"] is True
    assert data["member"]["name"] == "Aarti S"
    assert data["member"]["id"] == aarti["id"]
    aarti = data["member"]

    # --- validation errors ---
    st, data = call("POST", "/api/join", {"name": "", "phone": "123"})
    assert st == 400

    # --- a non-manager cannot create a drive ---
    st, data = call("POST", "/api/drives",
                    {"title": "X", "start_time": "2099-01-01T10:00"}, member=aarti)
    assert st == 403, data

    # --- unlock manager with wrong then right passcode ---
    st, data = call("POST", "/api/manager/unlock", {"passcode": "nope"}, member=aarti)
    assert st == 403
    st, data = call("POST", "/api/manager/unlock", {"passcode": "test-pass"}, member=aarti)
    assert st == 200 and data["member"]["is_manager"] is True
    aarti = data["member"]

    # --- create a drive (now a manager) ---
    st, data = call("POST", "/api/drives", {
        "title": "Yamuna Ghat Clean-up",
        "start_time": "2099-03-15T07:30",
        "location": "Gate 3, Lodhi Garden",
        "description": "Bring gloves.",
    }, member=aarti)
    assert st == 200, data
    drive = data["drive"]
    assert drive["counts"] == {"going": 0, "maybe": 0, "no": 0}

    # --- a second member joins and RSVPs ---
    st, data = call("POST", "/api/join", {"name": "Ravi", "phone": "9000000000"})
    ravi = data["member"]
    st, data = call("POST", f"/api/drives/{drive['id']}/rsvp", {"status": "going"}, member=ravi)
    assert st == 200 and data["drive"]["counts"]["going"] == 1
    assert data["drive"]["my_status"] == "going"

    # RSVP is idempotent / updatable (going -> maybe), not additive
    st, data = call("POST", f"/api/drives/{drive['id']}/rsvp", {"status": "maybe"}, member=ravi)
    assert data["drive"]["counts"] == {"going": 0, "maybe": 1, "no": 0}

    # invalid status rejected
    st, data = call("POST", f"/api/drives/{drive['id']}/rsvp", {"status": "perhaps"}, member=ravi)
    assert st == 400

    # must be joined to RSVP
    st, data = call("POST", f"/api/drives/{drive['id']}/rsvp", {"status": "going"})
    assert st == 401

    # --- drive detail shows attendee names ---
    st, data = call("GET", f"/api/drives/{drive['id']}", member=aarti)
    assert st == 200
    assert data["drive"]["attendees"]["maybe"] == ["Ravi"]

    # --- upcoming list contains the drive; past list does not ---
    st, data = call("GET", "/api/drives?scope=upcoming", member=ravi)
    assert any(d["id"] == drive["id"] for d in data["drives"])
    st, data = call("GET", "/api/drives?scope=past", member=ravi)
    assert all(d["id"] != drive["id"] for d in data["drives"])

    # --- edit + cancel a drive (manager only) ---
    st, data = call("PATCH", f"/api/drives/{drive['id']}", {"cancelled": True}, member=ravi)
    assert st == 403
    st, data = call("PATCH", f"/api/drives/{drive['id']}", {"title": "Renamed", "cancelled": True}, member=aarti)
    assert st == 200 and data["drive"]["cancelled"] is True and data["drive"]["title"] == "Renamed"

    # --- members list (manager only) ---
    st, data = call("GET", "/api/members", member=ravi)
    assert st == 403
    st, data = call("GET", "/api/members", member=aarti)
    assert {m["name"] for m in data["members"]} == {"Aarti S", "Ravi"}

    print("test_full_flow: OK")


def test_reminders_window():
    _start_server()
    # join a manager-less member just to have identity
    st, data = call("POST", "/api/join", {"name": "Meena", "phone": "8111111111"})
    meena = data["member"]
    st, data = call("GET", "/api/reminders", member=meena)
    assert st == 200 and isinstance(data["reminders"], list)
    # cancelled/far-future drives from the other test must not leak into the 48h window
    assert all(r["title"] != "Renamed" for r in data["reminders"])
    print("test_reminders_window: OK")


if __name__ == "__main__":
    test_full_flow()
    test_reminders_window()
    print("\nAll tests passed ✅")
