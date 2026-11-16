"""Admin session viewer: GET /api/sessions

Protected by ADMIN_KEY (env var). Send it as the X-Admin-Key header
or ?admin_key=... -- never put it in a public link.

Query params:
  limit       max sessions to return (default 50, max 100)
  status      filter by session status (created/page_viewed/verified/...)
  session_id  return one session

Response is sanitised: no raw IP (only its hash), user-agent truncated,
no token (only its hash). Requires MongoDB -- without DB_URI this
endpoint returns 503, because there is nothing to list.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from http.server import BaseHTTPRequestHandler
import json
import hmac
from urllib.parse import urlparse, parse_qs

import _common as sec


def _sanitise(doc):
    out = {}
    for key in ("session_id", "user_id", "token_hash", "status",
                "is_chrome", "chrome_version", "turnstile_verified",
                "turnstile_skipped", "attempts", "interaction_time",
                "ip_hash"):
        if key in doc:
            out[key] = doc[key]
    for key in ("created_at", "expires_at", "last_seen_at",
                "page_viewed_at", "verified_at", "turnstile_checked_at"):
        if doc.get(key) is not None:
            try:
                out[key] = doc[key].isoformat()
            except Exception:
                out[key] = str(doc[key])
    if doc.get("user_agent"):
        out["user_agent"] = str(doc["user_agent"])[:120]
    events = doc.get("events") or []
    out["events"] = [
        {"ts": (e.get("ts").isoformat() if hasattr(e.get("ts"), "isoformat") else str(e.get("ts"))),
         "event": e.get("event")}
        for e in events[-10:]
    ]
    return out


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        admin_key = sec.ADMIN_KEY or os.getenv("ADMIN_KEY")
        if not admin_key:
            self._json({"success": False,
                        "message": "ADMIN_KEY is not configured on the server"},
                       status=503)
            return

        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        supplied = (self.headers.get("X-Admin-Key") or "").strip()
        if not supplied:
            supplied = (params.get("admin_key", [""])[0] or "").strip()
        if not supplied or not hmac.compare_digest(supplied, admin_key):
            self._json({"success": False, "message": "Unauthorized"}, status=401)
            return

        db = sec.get_db()
        if db is None:
            self._json({"success": False,
                        "message": "Session tracking unavailable (MongoDB not configured/reachable)"},
                       status=503)
            return

        try:
            limit = min(max(int(params.get("limit", ["50"])[0]), 1), 100)
        except ValueError:
            limit = 50
        query = {}
        status = params.get("status", [""])[0]
        if status:
            query["status"] = status
        session_id = params.get("session_id", [""])[0]
        if session_id:
            query["session_id"] = session_id

        try:
            docs = list(db["verification_sessions"].find(query)
                        .sort("created_at", -1).limit(limit))
        except Exception as exc:
            self._json({"success": False, "message": f"Database error: {exc}"},
                       status=500)
            return

        self._json({"success": True, "count": len(docs),
                    "sessions": [_sanitise(d) for d in docs]})

    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())
