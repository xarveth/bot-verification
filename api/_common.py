"""Shared security helpers for bot-verification (Vercel, Python stdlib + pymongo).

What lives here (LinkForge-style security, adapted to this repo):
  1. Chrome-only gate  -- server-side User-Agent + Sec-CH-UA check.
     NOTE: this is friction, not unbreakable security -- a User-Agent
     string can be spoofed. It stops casual non-Chrome browsers, it does
     not stop a determined client.
  2. Cloudflare Turnstile -- human check, verified server-side at
     https://challenges.cloudflare.com/turnstile/v0/siteverify.
     Turnstile is only enforced when BOTH TURNSTILE_SITE_KEY and
     TURNSTILE_SECRET_KEY are set. If they are missing the step is
     skipped and the session is flagged turnstile_skipped=True, so a
     deploy without keys does not break the live flow -- set the keys
     in Vercel to enforce it.
  3. MongoDB session tracking -- one session document per verification
     visit (verification_sessions), plus one-time-token enforcement
     (used_tokens / verification_tokens). If DB_URI is missing or
     Mongo is unreachable, handlers degrade to the old stateless
     signed-token flow and log a warning -- sessions are then not
     tracked server-side (Vercel functions are stateless, there is no
     in-memory store to fall back to).
  4. Rate limiting -- 10/min and 70/hour per IP hash (LinkForge's
     limits), counted from the sessions collection.
  5. Server-side math challenge -- the challenge is generated on the
     server, signed with HMAC, and the answer is verified on the
     server. The old code only checked the answer in the browser.

Env vars:
  SECRET_KEY            required -- HMAC key for tokens/challenges.
                        NO hardcoded fallback (the old public default
                        was removed).
  DB_URI                MongoDB connection string (required for
                        session tracking / one-time tokens).
  TURNSTILE_SITE_KEY / TURNSTILE_SECRET_KEY
  CHROME_ONLY           'true' (default) / 'false'
  ADMIN_KEY             key for GET /api/sessions
  RATE_LIMIT_PER_MINUTE / RATE_LIMIT_PER_HOUR (defaults 10 / 70)
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

SECRET_KEY = os.getenv("SECRET_KEY") or None
DB_URI = os.getenv("DB_URI") or None
TURNSTILE_SITE_KEY = os.getenv("TURNSTILE_SITE_KEY") or None
TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY") or None
ADMIN_KEY = os.getenv("ADMIN_KEY") or None
CHROME_ONLY = os.getenv("CHROME_ONLY", "true").lower() in ("1", "true", "yes")
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "70"))
SESSION_TTL_SECONDS = 300
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

# Turnstile is enforced only when both keys are configured.
TURNSTILE_ENABLED = bool(TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY)
if os.getenv("TURNSTILE_ENABLED"):
    TURNSTILE_ENABLED = os.getenv("TURNSTILE_ENABLED").lower() in ("1", "true", "yes")

_mongo_client = None
_mongo_db = None


def now():
    return datetime.now(timezone.utc)


def get_secret_key():
    """Return SECRET_KEY, or None if it was never configured."""
    return SECRET_KEY or os.getenv("SECRET_KEY") or None


# ---------------------------------------------------------------- IP / hashing

def get_client_ip(headers):
    """First public IP from X-Forwarded-For (Vercel), else X-Real-IP."""
    if headers is None:
        return ""
    forwarded = headers.get("X-Forwarded-For") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()
    return (headers.get("X-Real-IP") or "").strip()


def hash_value(value):
    """One-way hash for IPs / tokens. Raw IPs are never stored."""
    salt = get_secret_key() or "bot-verification-no-secret"
    return hashlib.sha256(f"{salt}|{value}".encode()).hexdigest()


def hash_ip(ip):
    return hash_value(ip or "")[:32]


def hash_token(token):
    return hash_value(token or "")


# ---------------------------------------------------------------- Chrome gate

_NON_CHROME_TOKENS = (
    "Edg/", "OPR/", "Opera", "SamsungBrowser", "Whale",
    "Vivaldi", "YaBrowser", "Headless", "Brave",
)

_CHROME_VERSION_RE = re.compile(r"Chrome/(\d+)")


def is_chrome(user_agent, sec_ch_ua=""):
    """Return (allowed, chrome_version, reason).

    Real Chrome sends a UA containing 'Chrome/<major>' and, when it
    sends Sec-CH-UA, a '"Google Chrome"' brand. Edge/Opera/Brave/
    Samsung all carry a Chrome token in the UA too, so they are
    excluded by their own brand tokens. Telegram's in-app browser
    and Safari/Firefox have no Chrome token and are rejected.
    """
    ua = user_agent or ""
    if not ua:
        return False, None, "no-user-agent"
    for token in _NON_CHROME_TOKENS:
        if token in ua:
            return False, None, f"non-chrome-browser:{token}"
    match = _CHROME_VERSION_RE.search(ua)
    if not match:
        return False, None, "not-chrome"
    version = match.group(1)
    # Brave's User-Agent has no "Brave" token -- it just says Chrome --
    # so the server can only tell it apart from Sec-CH-UA. If that
    # header is missing, do NOT let the request through: real Chrome
    # always sends Sec-CH-UA (low-entropy brands) by default, so a
    # missing header means the browser is hiding its identity, and
    # letting it through is exactly how Brave was loading the page
    # and only failing later at submit (2026-11-16 live test).
    if not sec_ch_ua:
        return False, version, "sec-ch-ua-missing"
    if '"Brave"' in sec_ch_ua:
        return False, version, "non-chrome-browser:Brave"
    # Chrome advertises '"Google Chrome"'; Chromium-only builds,
    # Brave and Edge advertise Chromium / their own brand instead.
    if '"Google Chrome"' not in sec_ch_ua:
        return False, version, "sec-ch-ua-not-chrome"
    return True, version, "ok"


def chrome_block_page(reason=""):
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chrome Required</title>
<style>body{{font-family:Arial,sans-serif;background:linear-gradient(135deg,#667eea,#764ba2);min-height:100vh;display:flex;justify-content:center;align-items:center;padding:20px;margin:0}}
.container{{background:#fff;padding:40px;border-radius:20px;text-align:center;max-width:480px;box-shadow:0 20px 60px rgba(0,0,0,.3)}}
h1{{color:#dc3545}}p{{color:#666;line-height:1.6}}
a{{display:inline-block;margin-top:16px;padding:12px 24px;background:#667eea;color:#fff;border-radius:10px;text-decoration:none;font-weight:700}}</style>
</head><body><div class="container">
<h1>🌐 Please open this link in Google Chrome</h1>
<p>This verification page only works in Google Chrome on desktop or
Android. Copy the link from Telegram and paste it into Chrome, or tap
your browser's "Open in Chrome" option.</p>
<p style="font-size:13px;color:#999">If you are already in Chrome, make
sure you are not using an in-app browser or an Edge/Opera/Brave
window.</p>
</div></body></html>"""


# ---------------------------------------------------------------- MongoDB

def get_db():
    """Return the Mongo database, or None if DB_URI/pymongo is missing
    or the server cannot be reached. Never raises for callers."""
    global _mongo_client, _mongo_db
    if _mongo_db is not None:
        return _mongo_db
    uri = os.getenv("DB_URI") or DB_URI
    if not uri:
        return None
    try:
        import pymongo
    except ImportError:
        print("WARNING: pymongo not installed; session tracking disabled",
              file=sys.stderr)
        return None
    try:
        _mongo_client = pymongo.MongoClient(
            uri, serverSelectionTimeoutMS=3000, connectTimeoutMS=3000)
        _mongo_client.admin.command("ping")
        try:
            _mongo_db = _mongo_client.get_default_database()
        except Exception:
            _mongo_db = _mongo_client["bot_verification"]
        _ensure_indexes(_mongo_db)
        return _mongo_db
    except Exception as exc:  # unreachable / bad URI -- degrade gracefully
        print(f"WARNING: MongoDB unavailable, session tracking disabled: {exc}",
              file=sys.stderr)
        _mongo_client = None
        _mongo_db = None
        return None


def _ensure_indexes(db):
    try:
        db["verification_sessions"].create_index("session_id", unique=True)
        db["verification_sessions"].create_index("expires_at", expireAfterSeconds=0)
        db["verification_sessions"].create_index([("ip_hash", 1), ("created_at", -1)])
        db["used_tokens"].create_index("token_hash", unique=True)
        db["used_tokens"].create_index("expires_at", expireAfterSeconds=0)
        db["verification_tokens"].create_index("token_hash", unique=True)
        db["verification_tokens"].create_index("expires_at", expireAfterSeconds=0)
    except Exception as exc:
        print(f"WARNING: could not create Mongo indexes: {exc}", file=sys.stderr)


def new_session_id():
    return secrets.token_urlsafe(32)


def create_session(user_id, token, ip_hash, user_agent, is_chrome_flag,
                   chrome_version, turnstile_skipped=False):
    """Create a session document. Returns the session dict; when Mongo
    is unavailable it returns an ephemeral dict (not persisted)."""
    session_id = new_session_id()
    created = now()
    doc = {
        "session_id": session_id,
        "user_id": str(user_id),
        "token_hash": hash_token(token) if token else None,
        "created_at": created,
        "expires_at": created + timedelta(seconds=SESSION_TTL_SECONDS),
        "last_seen_at": created,
        "ip_hash": ip_hash,
        "user_agent": (user_agent or "")[:512],
        "is_chrome": bool(is_chrome_flag),
        "chrome_version": chrome_version,
        "turnstile_verified": False,
        "turnstile_skipped": bool(turnstile_skipped),
        "turnstile_checked_at": None,
        "status": "created",
        "attempts": 0,
        "interaction_time": 0,
        "page_viewed_at": None,
        "verified_at": None,
        "events": [{"ts": created, "event": "created"}],
    }
    db = get_db()
    if db is None:
        doc["_persisted"] = False
        return doc
    try:
        db["verification_sessions"].insert_one(dict(doc))
        doc["_persisted"] = True
    except Exception as exc:
        print(f"WARNING: could not persist session: {exc}", file=sys.stderr)
        doc["_persisted"] = False
    return doc


def get_session(session_id):
    if not session_id:
        return None
    db = get_db()
    if db is None:
        return None
    try:
        doc = db["verification_sessions"].find_one({"session_id": session_id})
    except Exception:
        return None
    if not doc:
        return None
    if doc.get("expires_at") and doc["expires_at"] < now():
        return None
    return doc


def update_session(session_id, updates, event=None):
    """$set updates + append one event. Returns True if persisted."""
    if not session_id:
        return False
    db = get_db()
    if db is None:
        return False
    try:
        patch = dict(updates or {})
        patch["last_seen_at"] = now()
        update = {"$set": patch}
        if event:
            update["$push"] = {"events": {"ts": now(), "event": event}}
        if updates and "attempts" in updates:
            pass  # attempts is set explicitly by the caller
        db["verification_sessions"].update_one(
            {"session_id": session_id}, update)
        return True
    except Exception as exc:
        print(f"WARNING: could not update session: {exc}", file=sys.stderr)
        return False


def bump_attempts(session_id):
    db = get_db()
    if db is None or not session_id:
        return
    try:
        db["verification_sessions"].update_one(
            {"session_id": session_id},
            {"$inc": {"attempts": 1}, "$set": {"last_seen_at": now()}})
    except Exception:
        pass


def check_rate_limit(ip_hash):
    """(limited, per_minute_count, per_hour_count) from sessions in
    the last 60s / 3600s. Without Mongo there is nothing to count
    against, so it returns not-limited."""
    db = get_db()
    if db is None or not ip_hash:
        return False, 0, 0
    try:
        minute_ago = now() - timedelta(seconds=60)
        hour_ago = now() - timedelta(hours=1)
        per_minute = db["verification_sessions"].count_documents(
            {"ip_hash": ip_hash, "created_at": {"$gte": minute_ago}})
        per_hour = db["verification_sessions"].count_documents(
            {"ip_hash": ip_hash, "created_at": {"$gte": hour_ago}})
        limited = per_minute >= RATE_LIMIT_PER_MINUTE or per_hour >= RATE_LIMIT_PER_HOUR
        return limited, per_minute, per_hour
    except Exception:
        return False, 0, 0


def is_token_used(token):
    db = get_db()
    if db is None:
        return False
    try:
        return db["used_tokens"].find_one(
            {"token_hash": hash_token(token)}) is not None
    except Exception:
        return False


def mark_token_used(token, user_id, session_id, expires_at):
    db = get_db()
    if db is None:
        return False
    try:
        db["used_tokens"].insert_one({
            "token_hash": hash_token(token),
            "user_id": str(user_id),
            "session_id": session_id,
            "used_at": now(),
            "expires_at": expires_at or now() + timedelta(seconds=SESSION_TTL_SECONDS),
        })
        return True
    except Exception:
        return False  # duplicate key == already used


def record_token_created(token, user_id, shortener_link, expires_at):
    db = get_db()
    if db is None:
        return False
    try:
        db["verification_tokens"].insert_one({
            "token_hash": hash_token(token),
            "user_id": str(user_id),
            "shortener_link": shortener_link,
            "created_at": now(),
            "expires_at": expires_at,
            "used": False,
        })
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- Turnstile

def verify_turnstile(token, remote_ip=""):
    """(ok, detail). Skipped (ok=True) only when Turnstile is not
    configured -- see the module docstring."""
    if not TURNSTILE_ENABLED:
        return True, "skipped-not-configured"
    if not token:
        return False, "missing-turnstile-token"
    secret = TURNSTILE_SECRET_KEY
    payload = json.dumps({
        "secret": secret,
        "response": token,
        "remoteip": remote_ip or "",
    }).encode()
    req = urllib.request.Request(
        TURNSTILE_VERIFY_URL, data=payload,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return False, f"turnstile-verify-error:{exc}"
    if result.get("success"):
        return True, "ok"
    return False, "turnstile-failed:" + ",".join(result.get("error-codes", []))


# ---------------------------------------------------------------- Math challenge (server-side)

CHALLENGES = [
    {"q": "What is 5 + 3?", "a": ["6", "8", "9", "7"], "correct": "8"},
    {"q": "What is 10 - 4?", "a": ["5", "6", "7", "8"], "correct": "6"},
    {"q": "What is 3 × 4?", "a": ["10", "12", "14", "16"], "correct": "12"},
    {"q": "What is 15 ÷ 3?", "a": ["3", "4", "5", "6"], "correct": "5"},
    {"q": "What is 7 + 8?", "a": ["14", "15", "16", "17"], "correct": "15"},
    {"q": "What is 20 - 8?", "a": ["10", "11", "12", "13"], "correct": "12"},
    {"q": "What is 6 × 2?", "a": ["10", "11", "12", "13"], "correct": "12"},
    {"q": "What is 18 ÷ 2?", "a": ["7", "8", "9", "10"], "correct": "9"},
    {"q": "What is 9 + 6?", "a": ["13", "14", "15", "16"], "correct": "15"},
    {"q": "What is 25 - 10?", "a": ["13", "14", "15", "16"], "correct": "15"},
]


def generate_challenge():
    return dict(CHALLENGES[secrets.randbelow(len(CHALLENGES))])


def sign_challenge(challenge, session_id):
    """Signed challenge token the browser must send back with its answer."""
    secret = get_secret_key()
    if not secret:
        return None
    payload = {"q": challenge["q"], "correct": challenge["correct"],
               "sid": session_id, "ts": int(time.time())}
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(secret.encode(), payload_b64.encode(),
                   hashlib.sha256).hexdigest()
    return f"{payload_b64}~{sig}"


def verify_challenge_answer(challenge_token, session_id, answer):
    """(ok, reason). Verifies the HMAC, the session binding, the
    5-minute age, and the answer itself -- all server-side."""
    if not challenge_token or "~" not in challenge_token:
        return False, "missing-challenge-token"
    secret = get_secret_key()
    if not secret:
        return False, "server-secret-not-configured"
    payload_b64, sig = challenge_token.rsplit("~", 1)
    expected = hmac.new(secret.encode(), payload_b64.encode(),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False, "challenge-signature-invalid"
    try:
        padding = (4 - len(payload_b64) % 4) % 4
        data = json.loads(base64.urlsafe_b64decode(
            (payload_b64 + "=" * padding).encode()).decode())
    except Exception:
        return False, "challenge-decode-failed"
    if data.get("sid") != session_id:
        return False, "challenge-session-mismatch"
    if int(time.time()) - int(data.get("ts", 0)) > SESSION_TTL_SECONDS:
        return False, "challenge-expired"
    if str(answer) != str(data.get("correct")):
        return False, "wrong-answer"
    return True, "ok"


# ---------------------------------------------------------------- Cookies

def parse_cookies(headers):
    cookies = {}
    if headers is None:
        return cookies
    raw = headers.get("Cookie") or ""
    for part in raw.split(";"):
        if "=" in part:
            key, value = part.strip().split("=", 1)
            cookies[key.strip()] = value.strip()
    return cookies


def session_cookie_header(session_id):
    return (f"bv_session={session_id}; HttpOnly; Secure; SameSite=Lax; "
            f"Path=/; Max-Age={SESSION_TTL_SECONDS}")


# ---------------------------------------------------------------- Vercel entrypoint
# vercel.json builds "api/**/*.py" with @vercel/python, so every .py
# file under api/ is treated as a serverless function and must expose
# a top-level "handler". This file is a shared module, not a real
# endpoint, but without a handler the whole deployment fails with
# "Could not find a top-level 'app', 'application', or 'handler' in
# 'api/_common.py'". This dummy handler only ever answers 404; no
# route in vercel.json points at this file.
from http.server import BaseHTTPRequestHandler  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        self.send_response(404)
        self.end_headers()
