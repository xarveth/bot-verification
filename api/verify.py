import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from datetime import timedelta
from http.server import BaseHTTPRequestHandler
import json
import time
import hmac
import hashlib
import base64
from urllib.parse import urlparse, parse_qs

import _common as sec

# SECRET_KEY has NO hardcoded fallback any more. If it is not set in
# Vercel env vars, token creation / verification refuse to work
# instead of silently using a public default.
SECRET_KEY = os.getenv('SECRET_KEY')


def decode_token(token_str):
    """Decode and verify a signed token. Returns (user_id, shortener_link, time_left) or raises."""
    if not SECRET_KEY:
        return None, None, None
    if '~' not in token_str:
        return None, None, None
    payload_b64, sig = token_str.rsplit('~', 1)

    # Verify signature
    expected_sig = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None, None, None

    # Decode payload — correct padding: (4 - n%4) % 4 avoids adding 4 chars when already aligned
    padding = (4 - len(payload_b64) % 4) % 4
    payload_str = base64.urlsafe_b64decode((payload_b64 + '=' * padding).encode()).decode()
    data = json.loads(payload_str)

    user_id = data['uid']
    shortener_link = data['link']
    timestamp = data['ts']

    time_left = 300 - (int(time.time()) - timestamp)
    return user_id, shortener_link, time_left


class handler(BaseHTTPRequestHandler):

    # -- helpers ------------------------------------------------------
    def _request_context(self):
        """(ip, ip_hash, user_agent, sec_ch_ua, chrome_ok, chrome_version, chrome_reason)"""
        ip = sec.get_client_ip(self.headers)
        ua = self.headers.get('User-Agent') or ''
        sec_ch_ua = self.headers.get('Sec-CH-UA') or ''
        chrome_ok, chrome_version, chrome_reason = sec.is_chrome(ua, sec_ch_ua)
        return ip, sec.hash_ip(ip), ua, chrome_ok, chrome_version, chrome_reason

    def _chrome_gate(self):
        """Return True if the request may continue, else send the
        Chrome-only page and return False."""
        if not sec.CHROME_ONLY:
            return True
        _ip, _iph, ua, chrome_ok, _ver, reason = self._request_context()
        if chrome_ok:
            return True
        self.send_response(403)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(sec.chrome_block_page(reason).encode())
        return False

    # -- GET / POST wrappers: an unhandled exception must never turn
    # into Vercel's HTML 500 page -- the browser's fetch() then fails
    # to parse JSON and the user only sees "Network error". Return a
    # readable JSON / error page instead (live bug, 2026-11-16).
    def do_GET(self):
        try:
            self._handle_get()
        except Exception as exc:  # noqa: BLE001 - report, never crash
            print(f"ERROR in do_GET: {exc}", file=sys.stderr)
            try:
                self.send_error_page(f"Server error ({exc}). Please refresh and try again.")
            except Exception:
                pass

    def do_POST(self):
        try:
            self._handle_post()
        except Exception as exc:  # noqa: BLE001 - report, never crash
            print(f"ERROR in do_POST: {exc}", file=sys.stderr)
            try:
                self.send_json_response(
                    {'success': False,
                     'message': f'Server error ({exc}). Please refresh and try again.'},
                    status=500)
            except Exception:
                pass

    # -- GET: verification page ---------------------------------------
    def _handle_get(self):
        """Handle verification page requests"""
        path = self.path
        parsed = urlparse(path)
        path_parts = parsed.path.split('/')

        # Extract token: /pre-verify/TOKEN or /verify/TOKEN
        if len(path_parts) >= 3 and path_parts[1] in ('pre-verify', 'verify'):
            token = path_parts[2]
            path_prefix = path_parts[1]
            query_params = parse_qs(parsed.query)
            user_id_param = query_params.get('uid', ['anonymous'])[0]

            # 1) Chrome-only gate (before any DB work)
            if not self._chrome_gate():
                return

            ip, ip_hash, ua, chrome_ok, chrome_version, _reason = self._request_context()

            # 2) Rate limit: 10/min, 70/hour per IP hash (LinkForge limits)
            limited, per_min, per_hour = sec.check_rate_limit(ip_hash)
            if limited:
                self.send_error_page(
                    f"Too many verification attempts from your network "
                    f"({per_min} in the last minute, {per_hour} in the last hour). "
                    f"Please wait a few minutes and try again.")
                return

            # 3) Decode + verify signed token (no DB needed)
            if not SECRET_KEY:
                self.send_error_page("Server is not configured (SECRET_KEY missing).")
                return
            user_id, shortener_link, time_left = decode_token(token)

            if user_id is None:
                self.send_error_page("Invalid or expired verification link")
                return

            if time_left <= 0:
                self.send_error_page("Verification link has expired")
                return

            # 4) One-time use: a token that already verified is dead,
            #    even inside its 5-minute window.
            if sec.is_token_used(token):
                self.send_error_page("This verification link has already been used.")
                return

            # 5) Session tracking: one Mongo document per visit.
            session = sec.create_session(
                user_id_param, token, ip_hash, ua, chrome_ok, chrome_version,
                turnstile_skipped=not sec.TURNSTILE_ENABLED)
            session_id = session["session_id"]
            sec.update_session(session_id, {"status": "page_viewed",
                                            "page_viewed_at": sec.now()},
                               event="page_viewed")

            # 6) Server-side math challenge: generated here, signed,
            #    answer verified on POST (never trusted from the client).
            challenge = sec.generate_challenge()
            challenge_token = sec.sign_challenge(challenge, session_id)
            if challenge_token is None:
                self.send_error_page("Server is not configured (SECRET_KEY missing).")
                return

            self.send_verification_page(token, user_id_param, time_left,
                                        path_prefix, session_id, challenge,
                                        challenge_token)
        else:
            self.send_error_page("Invalid URL")

    # -- POST: verification submission --------------------------------
    def _handle_post(self):
        """Handle verification submission"""
        path = self.path
        path_parts = path.split('/')

        # Extract token: /pre-verify/TOKEN/submit or /verify/TOKEN/submit
        if len(path_parts) >= 4 and path_parts[1] in ('pre-verify', 'verify') and path_parts[3] == 'submit':
            token = path_parts[2]

            # 1) Chrome-only gate, JSON flavour for the fetch call.
            if sec.CHROME_ONLY:
                _ip, _iph, _ua, chrome_ok, _ver, reason = self._request_context()
                if not chrome_ok:
                    self.send_json_response(
                        {'success': False,
                         'message': 'This verification only works in Google Chrome.',
                         'reason': reason}, status=403)
                    return

            ip, ip_hash, ua, chrome_ok, chrome_version, _reason = self._request_context()

            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
            except Exception:
                self.send_json_response({'success': False, 'message': 'Invalid request body'})
                return

            user_id = data.get('user_id', 'anonymous')
            interaction_time = data.get('interaction_time', 0)
            challenge_answer = data.get('challenge_answer')
            challenge_token = data.get('challenge_token')
            turnstile_token = data.get('turnstile_token')

            # 1b) Client-reported browser (navigator.brave / userAgentData).
            # Brave's desktop User-Agent mimics Chrome, so the server
            # UA check alone can miss it -- the page reports
            # navigator.brave.isBrave() and the high-entropy brands,
            # and the server rejects Brave/Edge/etc. here too.
            if data.get('is_brave'):
                self.send_json_response(
                    {'success': False,
                     'message': 'This verification only works in Google Chrome (Brave is not supported).'},
                    status=403)
                return
            client_brands = data.get('client_brands') or []
            if client_brands:
                brand_names = [str(b.get('brand', '')) for b in client_brands
                               if isinstance(b, dict)]
                if brand_names and 'Google Chrome' not in brand_names:
                    self.send_json_response(
                        {'success': False,
                         'message': 'This verification only works in Google Chrome.'},
                        status=403)
                    return

            # 2) Session: the bv_session cookie set on GET must match
            #    this token. Without a session there is nothing to track
            #    and the request is rejected.
            cookies = sec.parse_cookies(self.headers)
            session_id = cookies.get('bv_session')
            session = sec.get_session(session_id) if session_id else None
            if session_id and session is None:
                self.send_json_response({'success': False,
                                         'message': 'Session expired. Please reopen the verification link.'})
                return
            if session is not None and session.get('token_hash') != sec.hash_token(token):
                self.send_json_response({'success': False,
                                         'message': 'Session does not match this verification link.'})
                return

            def _fail(message):
                if session_id:
                    sec.bump_attempts(session_id)
                self.send_json_response({'success': False, 'message': message})

            # 3) Server-side elapsed time: at least 10s between the
            #    page view and the submit, measured on the server.
            #    The client-reported interaction_time alone is not trusted.
            if session is not None and session.get('page_viewed_at'):
                elapsed = (sec.now() - sec.as_aware(session['page_viewed_at'])).total_seconds()
            elif session is not None and session.get('created_at'):
                elapsed = (sec.now() - sec.as_aware(session['created_at'])).total_seconds()
            else:
                elapsed = interaction_time
            if elapsed < 10 or interaction_time < 10:
                _fail('Please wait for the full countdown')
                return

            # 4) Turnstile, verified server-side (skipped only when the
            #    keys are not configured -- see _common.py).
            turnstile_ok, turnstile_detail = sec.verify_turnstile(turnstile_token, ip)
            if session_id:
                sec.update_session(session_id, {
                    'turnstile_verified': bool(turnstile_ok),
                    'turnstile_checked_at': sec.now(),
                    'interaction_time': int(interaction_time),
                }, event='turnstile_checked')
            if not turnstile_ok:
                _fail('Human verification failed. Please refresh and try again.')
                return

            # 5) Math challenge, verified server-side.
            if session_id:
                challenge_ok, challenge_reason = sec.verify_challenge_answer(
                    challenge_token, session_id, challenge_answer)
            else:
                challenge_ok, challenge_reason = False, 'missing-session'
            if not challenge_ok:
                _fail('Incorrect answer! Please try again.'
                      if challenge_reason == 'wrong-answer'
                      else f'Verification failed ({challenge_reason}). Please refresh and try again.')
                return

            # 6) Decode + verify signed token (no DB needed)
            if not SECRET_KEY:
                _fail('Server is not configured (SECRET_KEY missing).')
                return
            token_user_id, shortener_link, time_left = decode_token(token)

            if token_user_id is None or time_left <= 0:
                _fail('Invalid or expired verification link')
                return

            # 7) One-time use, enforced atomically-ish in Mongo:
            #    re-check right before issuing the redirect, then mark used.
            if sec.is_token_used(token):
                _fail('This verification link has already been used.')
                return
            expires_at = sec.now() + timedelta(seconds=max(time_left, 0))
            sec.mark_token_used(token, token_user_id, session_id, expires_at)

            if session_id:
                sec.update_session(session_id, {
                    'status': 'verified',
                    'verified_at': sec.now(),
                    'interaction_time': int(interaction_time),
                }, event='verified')

            # Return shortener link directly from token
            self.send_json_response({'success': True, 'redirect_url': shortener_link})
        else:
            self.send_json_response({'success': False, 'message': 'Invalid request'})

    def send_verification_page(self, token, user_id, time_left, path_prefix='pre-verify',
                               session_id='', challenge=None, challenge_token=''):
        """Send verification HTML page"""
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_header('Access-Control-Allow-Origin', '*')
        if session_id:
            self.send_header('Set-Cookie', sec.session_cookie_header(session_id))
        self.end_headers()

        challenge = challenge or {"q": "What is 5 + 3?", "a": ["6", "8", "9", "7"], "correct": "8"}
        # Public copy only -- the correct answer must never reach the page.
        challenge_json = json.dumps({"q": challenge["q"], "a": challenge["a"]})
        turnstile_site_key = sec.TURNSTILE_SITE_KEY or ''
        turnstile_widget = ''
        turnstile_script = ''
        if sec.TURNSTILE_ENABLED:
            turnstile_widget = (
                '<div class="cf-turnstile" data-sitekey="' + turnstile_site_key +
                '" data-theme="light" style="display:flex;justify-content:center;margin-bottom:20px"></div>'
            )
            turnstile_script = '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>'

        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔐 Verification Required</title>
    {turnstile_script}
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        .container {{
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 500px;
            width: 100%;
            padding: 40px;
            animation: slideIn 0.5s ease-out;
        }}
        @keyframes slideIn {{
            from {{ opacity: 0; transform: translateY(-30px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .header h1 {{ color: #667eea; font-size: 28px; margin-bottom: 10px; }}
        .header p {{ color: #666; font-size: 14px; }}
        .timer {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 15px;
            padding: 30px;
            text-align: center;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.3);
        }}
        .timer-label {{ color: white; font-size: 16px; margin-bottom: 15px; font-weight: 500; }}
        .timer-value {{
            font-size: 48px;
            font-weight: bold;
            color: white;
            font-family: 'Courier New', monospace;
            text-shadow: 0 2px 10px rgba(0,0,0,0.2);
        }}
        .progress-bar {{
            width: 100%;
            height: 12px;
            background: #e0e0e0;
            border-radius: 10px;
            overflow: hidden;
            margin-bottom: 30px;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            width: 0%;
            transition: width 0.3s ease;
        }}
        .challenge {{ margin-bottom: 30px; }}
        .challenge-question {{
            background: linear-gradient(135deg, #e3f2fd 0%, #f3e5f5 100%);
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            text-align: center;
            font-size: 20px;
            color: #1976d2;
            font-weight: 600;
            border: 2px solid #2196f3;
        }}
        .challenge-options {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }}
        .challenge-btn {{
            padding: 18px;
            border: 2px solid #e0e0e0;
            background: white;
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 18px;
            font-weight: 600;
            color: #333;
        }}
        .challenge-btn:hover {{
            border-color: #667eea;
            background: #f8f9fa;
            transform: translateY(-3px);
        }}
        .challenge-btn.selected {{
            border-color: #667eea;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            transform: scale(1.05);
        }}
        .verify-btn {{
            width: 100%;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 18px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s ease;
            opacity: 0.5;
            pointer-events: none;
        }}
        .verify-btn.active {{
            opacity: 1;
            pointer-events: all;
        }}
        .verify-btn.active:hover {{
            transform: translateY(-3px);
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.5);
        }}
        .loading {{ display: none; text-align: center; margin-top: 20px; }}
        .loading.active {{ display: block; }}
        .spinner {{
            border: 4px solid #f3f3f3;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            animation: spin 1s linear infinite;
            margin: 0 auto 15px;
        }}
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
        .error {{
            background: #ffebee;
            color: #c62828;
            padding: 15px;
            border-radius: 10px;
            margin-top: 20px;
            display: none;
        }}
        .error.active {{ display: block; }}
        .info-box {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 8px;
        }}
        .info-box p {{
            color: #856404;
            font-size: 14px;
            margin: 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔐 Verification Required</h1>
            <p>Complete verification to proceed to download link</p>
        </div>

        <div class="info-box">
            <p><strong>⚡ Quick Process:</strong> Wait 10 seconds → Answer question → Get your link!</p>
        </div>

        <div class="timer">
            <div class="timer-label">⏱️ Please Wait</div>
            <div class="timer-value" id="timer">10s</div>
        </div>

        <div class="progress-bar">
            <div class="progress-fill" id="progress"></div>
        </div>

        <div class="challenge">
            <div class="challenge-question" id="question">Loading challenge...</div>
            <div class="challenge-options" id="options"></div>
        </div>

        {turnstile_widget}

        <button class="verify-btn" id="verifyBtn" disabled>
            🔓 Verify & Continue
        </button>

        <div class="loading" id="loading">
            <div class="spinner"></div>
            <p style="color: #667eea; font-weight: 600;">Verifying... Please wait</p>
        </div>

        <div class="error" id="error"></div>
    </div>

    <script>
        const TOKEN = '{token}';
        const USER_ID = '{user_id}';
        const path_prefix = '{path_prefix}';
        const CHALLENGE_TOKEN = '{challenge_token}';
        const CHALLENGE = {challenge_json};
        const TURNSTILE_ENABLED = {str(sec.TURNSTILE_ENABLED).lower()};
        const VERIFICATION_TIME = 10;
        let timeLeft = VERIFICATION_TIME;
        let selectedAnswer = null;
        let interactionTime = 0;
        let isBrave = false;
        let clientBrands = [];
        let browserBlocked = false;

        // Brave (and Edge/Opera) look like Chrome in the User-Agent,
        // so check the browser itself: navigator.brave.isBrave() is
        // Brave-only, and userAgentData brands list the real browser.
        // This is how sites like freeshare catch Brave -- the server
        // re-checks the same report on submit, so hiding it in the
        // page alone is not enough to get through.
        async function detectBrowser() {{
            try {{
                if (navigator.brave && navigator.brave.isBrave) {{
                    isBrave = await navigator.brave.isBrave();
                }}
            }} catch (e) {{}}
            try {{
                if (navigator.userAgentData && navigator.userAgentData.getHighEntropyValues) {{
                    const data = await navigator.userAgentData.getHighEntropyValues(['brands']);
                    clientBrands = data.brands || [];
                }}
            }} catch (e) {{}}
            const brandNames = clientBrands.map(b => b.brand || '');
            const looksNonChrome = isBrave
                || (brandNames.length > 0 && !brandNames.includes('Google Chrome'))
                || /Edg\\/|OPR\\/|SamsungBrowser|Vivaldi|YaBrowser/.test(navigator.userAgent || '');
            if (looksNonChrome) {{
                browserBlocked = true;
                const name = isBrave ? 'Brave' : 'this browser';
                showError('🌐 Please open this link in Google Chrome — ' + name + ' is not supported here.');
                document.getElementById('verifyBtn').disabled = true;
            }}
        }}
        detectBrowser();

        // Challenge is generated on the server and signed -- the
        // correct answer is never in this page, only the question.
        const challenge = {{ q: CHALLENGE.q, a: CHALLENGE.a }};
        document.getElementById('question').textContent = challenge.q;

        const optionsContainer = document.getElementById('options');
        challenge.a.forEach(option => {{
            const btn = document.createElement('button');
            btn.className = 'challenge-btn';
            btn.textContent = option;
            btn.onclick = () => {{
                document.querySelectorAll('.challenge-btn').forEach(b => b.classList.remove('selected'));
                btn.classList.add('selected');
                selectedAnswer = option;
                checkVerifyButton();
            }};
            optionsContainer.appendChild(btn);
        }});

        setInterval(() => {{
            timeLeft--;
            interactionTime++;
            document.getElementById('timer').textContent = timeLeft > 0 ? timeLeft + 's' : '✓ Ready';
            document.getElementById('progress').style.width = ((VERIFICATION_TIME - timeLeft) / VERIFICATION_TIME * 100) + '%';
            if (timeLeft <= 0) checkVerifyButton();
        }}, 1000);

        function checkVerifyButton() {{
            const btn = document.getElementById('verifyBtn');
            if (browserBlocked) return;
            if (interactionTime >= VERIFICATION_TIME && selectedAnswer) {{
                btn.classList.add('active');
                btn.disabled = false;
            }}
        }}

        document.getElementById('verifyBtn').onclick = async () => {{
            if (browserBlocked) {{
                showError('🌐 Please open this link in Google Chrome.');
                return;
            }}
            document.getElementById('loading').classList.add('active');
            document.getElementById('verifyBtn').disabled = true;

            let turnstileToken = '';
            if (TURNSTILE_ENABLED && window.turnstile) {{
                try {{ turnstileToken = turnstile.getResponse() || ''; }} catch (e) {{}}
            }}

            try {{
                const response = await fetch('/' + path_prefix + '/' + TOKEN + '/submit', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        user_id: USER_ID,
                        interaction_time: interactionTime,
                        challenge_answer: selectedAnswer,
                        challenge_token: CHALLENGE_TOKEN,
                        turnstile_token: turnstileToken,
                        is_brave: isBrave,
                        client_brands: clientBrands
                    }})
                }});

                // Read as text first: if the server ever returns a
                // non-JSON error page, show its status instead of a
                // generic "Network error" (live bug, 2026-11-16).
                const rawText = await response.text();
                let data;
                try {{
                    data = JSON.parse(rawText);
                }} catch (e) {{
                    showError('Server error (HTTP ' + response.status + '). Please try again.');
                    document.getElementById('loading').classList.remove('active');
                    document.getElementById('verifyBtn').disabled = false;
                    return;
                }}

                if (data.success) {{
                    document.getElementById('loading').innerHTML = '<div style="color: #4caf50; font-size: 24px; margin-bottom: 10px;">✓</div><p style="color: #4caf50; font-weight: 600;">Verification Successful!</p><p style="color: #666; font-size: 14px;">Redirecting to download link...</p>';
                    setTimeout(() => window.location.href = data.redirect_url, 1000);
                }} else {{
                    showError(data.message || 'Verification failed');
                    document.getElementById('loading').classList.remove('active');
                    document.getElementById('verifyBtn').disabled = false;
                    document.querySelectorAll('.challenge-btn').forEach(b => b.classList.remove('selected'));
                    selectedAnswer = null;
                }}
            }} catch (error) {{
                showError('❌ Network error. Please try again.');
                document.getElementById('loading').classList.remove('active');
                document.getElementById('verifyBtn').disabled = false;
            }}
        }};

        function showError(message) {{
            const errorDiv = document.getElementById('error');
            errorDiv.textContent = message;
            errorDiv.classList.add('active');
            setTimeout(() => errorDiv.classList.remove('active'), 5000);
        }}

        document.addEventListener('contextmenu', e => e.preventDefault());
        document.addEventListener('keydown', e => {{
            if (e.key === 'F12' || (e.ctrlKey && e.shiftKey && e.key === 'I')) {{
                e.preventDefault();
            }}
        }});
    </script>
</body>
</html>
        """

        self.wfile.write(html.encode())

    def send_error_page(self, message):
        """Send error page"""
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Error</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 20px;
            text-align: center;
            max-width: 500px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }}
        h1 {{ color: #dc3545; margin-bottom: 20px; }}
        p {{ color: #666; line-height: 1.6; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>⚠️ Verification Error</h1>
        <p>{message}</p>
    </div>
</body>
</html>
        """

        self.wfile.write(html.encode())

    def send_json_response(self, data, status=200):
        """Send JSON response"""
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
