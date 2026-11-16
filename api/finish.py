"""Anti-bypass finish stage (like freeshare's /finish page).

After a successful verification, the browser is sent here with a
one-time finish token -- never with the shortener link itself.
GET shows a "Continue securely" page; the link is only released on
POST, after the server re-checks the finish token, the verified
session, the IP and the browser. Anyone who tries to skip the
verification in the middle -- decoding the verify token, guessing
a /finish URL, or reusing an old one -- gets an error page instead.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import html

import _common as sec


def _page(title, body, status=200):
    return status, f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<style>body{{font-family:'Segoe UI',Tahoma,sans-serif;background:#0f1115;min-height:100vh;display:flex;justify-content:center;align-items:center;padding:20px;margin:0}}
.card{{background:#1c2333;border:1px solid #2a3348;border-radius:16px;padding:36px;max-width:460px;width:100%;text-align:center;color:#e8ecf3}}
h1{{font-size:22px;margin:14px 0 10px}}p{{color:#9aa3b5;line-height:1.6;font-size:14px}}
button{{display:block;width:100%;margin-top:22px;padding:14px;border:0;border-radius:10px;background:#fff;color:#111;font-weight:700;font-size:15px;cursor:pointer}}
a{{color:#7aa2ff}} .err h1{{color:#ff6b6b}}</style>
</head><body><div class="card">{body}</div></body></html>"""


class handler(BaseHTTPRequestHandler):
    def _context(self):
        ip = sec.get_client_ip(self.headers)
        ua = self.headers.get('User-Agent') or ''
        sec_ch_ua = self.headers.get('Sec-CH-UA') or ''
        chrome_ok, _, _ = sec.is_chrome(ua, sec_ch_ua)
        return ip, sec.hash_ip(ip), ua, chrome_ok

    def _token(self):
        qs = parse_qs(urlparse(self.path).query)
        return (qs.get('t') or [''])[0]

    def _chrome_gate(self):
        if not sec.CHROME_ONLY:
            return True
        _ip, _iph, _ua, chrome_ok = self._context()
        if chrome_ok:
            return True
        self._send(*_page("Chrome Required",
                          '<div class="err"><h1>🌐 Please open this link in Google Chrome</h1>'
                          '<p>This page only works in Google Chrome. Copy the link and paste it into Chrome.</p></div>',
                          status=403))
        return False

    def _send(self, status, body):
        data = body.encode()
        self.send_response(status)
        self.send_header('Content-type', 'text/html')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            self._handle_get()
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR in finish do_GET: {exc}", file=sys.stderr)
            self._send(*_page("Server error",
                              '<div class="err"><h1>Something went wrong</h1>'
                              '<p>Please go back and start the verification again.</p></div>',
                              status=500))

    def _handle_get(self):
        if not self._chrome_gate():
            return
        token = self._token()
        _ip, ip_hash, _ua, _chrome_ok = self._context()
        link, _session, reason = sec.validate_finish_token(token, ip_hash, _ua)
        if link is None:
            self._send(*_page("Verification required",
                              '<div class="err"><h1>🛡️ Verification required</h1>'
                              '<p>This link could not be verified. It may have been '
                              'opened without completing verification, reused, or expired. '
                              'Please go back and complete the verification first.</p></div>',
                              status=403))
            return
        # Valid so far -- show the freeshare-style re-check page.
        # The link is NOT in this page; it is only released on POST.
        self._send(*_page("Continue securely",
                          '<div style="font-size:28px">🛡️</div>'
                          '<h1>Continue securely</h1>'
                          '<p>Your browser session needs to be checked again. '
                          'If necessary, the protected advertisement will restart.</p>'
                          '<form method="POST" action="/finish?t=' + html.escape(token, quote=True) + '">'
                          '<button type="submit">Continue in this browser</button>'
                          '</form>'))

    def do_POST(self):
        try:
            self._handle_post()
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR in finish do_POST: {exc}", file=sys.stderr)
            try:
                self._send(*_page("Server error",
                                  '<div class="err"><h1>Something went wrong</h1>'
                                  '<p>Please go back and start the verification again.</p></div>',
                                  status=500))
            except Exception:
                pass

    def _handle_post(self):
        if not self._chrome_gate():
            return
        token = self._token()
        _ip, ip_hash, _ua, _chrome_ok = self._context()
        link, _session, reason = sec.validate_finish_token(token, ip_hash, _ua)
        if link is None:
            self._send(*_page("Verification required",
                              '<div class="err"><h1>🛡️ Verification required</h1>'
                              '<p>This link could not be verified. It may have been '
                              'opened without completing verification, reused, or expired. '
                              'Please go back and complete the verification first.</p></div>',
                              status=403))
            return
        # One-time: consume before redirecting, so a replayed POST
        # cannot release the link a second time.
        sec.consume_finish_token(token)
        self.send_response(302)
        self.send_header('Location', link)
        self.send_header('Content-Length', '0')
        self.end_headers()
