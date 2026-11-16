import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from http.server import BaseHTTPRequestHandler
import json
import time
import hmac
import hashlib
import base64
from datetime import datetime, timedelta, timezone

import _common as sec

SECRET_KEY = os.getenv('SECRET_KEY')
BOT_API_KEY = os.getenv('BOT_API_KEY') or None


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        try:
            # Optional bot auth: if BOT_API_KEY is set in Vercel, the
            # calling bot must send it as X-Api-Key (or Bearer token).
            # If it is not set, the endpoint stays open as before
            # (backward compatible) -- set the key to lock it down.
            if BOT_API_KEY:
                supplied = (self.headers.get('X-Api-Key') or '').strip()
                auth = (self.headers.get('Authorization') or '').strip()
                if auth.lower().startswith('bearer '):
                    supplied = supplied or auth[7:].strip()
                if not supplied or not hmac.compare_digest(supplied, BOT_API_KEY):
                    self.send_json({'success': False, 'message': 'Unauthorized'}, status=401)
                    return

            if not SECRET_KEY:
                self.send_json({'success': False,
                                'message': 'Server is not configured (SECRET_KEY missing)'},
                               status=500)
                return

            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            user_id = data.get('user_id')
            shortener_link = data.get('shortener_link')

            if not user_id or not shortener_link:
                self.send_json({'success': False, 'message': 'Missing user_id or shortener_link'})
                return

            # Build a signed, self-contained token (no DB needed to verify it)
            timestamp = int(time.time())
            payload = base64.urlsafe_b64encode(
                json.dumps({'uid': str(user_id), 'link': shortener_link, 'ts': timestamp}).encode()
            ).decode().rstrip('=')

            sig = hmac.new(
                SECRET_KEY.encode(),
                payload.encode(),
                hashlib.sha256
            ).hexdigest()

            token = f"{payload}~{sig}"
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=300)

            # Audit + one-time-use record in Mongo (best effort: if
            # Mongo is down the signed token still works, but reuse
            # cannot be enforced for that token -- see _common.py).
            sec.record_token_created(token, user_id, shortener_link, expires_at)

            self.send_json({'success': True, 'token': token, 'expires_in': 300})

        except Exception as e:
            self.send_json({'success': False, 'message': f'Error: {str(e)}'})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Api-Key, Authorization')
        self.end_headers()

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
