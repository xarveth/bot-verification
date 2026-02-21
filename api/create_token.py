from http.server import BaseHTTPRequestHandler
import json
import time
import hmac
import hashlib
import base64
import os

SECRET_KEY = os.getenv('SECRET_KEY', 'nexora-verify-secret-2024')

class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            user_id = data.get('user_id')
            shortener_link = data.get('shortener_link')

            if not user_id or not shortener_link:
                self.send_json({'success': False, 'message': 'Missing user_id or shortener_link'})
                return

            # Build a signed, self-contained token (no DB needed)
            timestamp = int(time.time())
            payload = base64.urlsafe_b64encode(
                json.dumps({'uid': str(user_id), 'link': shortener_link, 'ts': timestamp}).encode()
            ).decode().rstrip('=')

            sig = hmac.new(
                SECRET_KEY.encode(),
                payload.encode(),
                hashlib.sha256
            ).hexdigest()

            token = f"{payload}.{sig}"

            self.send_json({'success': True, 'token': token, 'expires_in': 300})

        except Exception as e:
            self.send_json({'success': False, 'message': f'Error: {str(e)}'})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
