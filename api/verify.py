from http.server import BaseHTTPRequestHandler
import json
import time
import os
import hmac
import hashlib
import base64
from urllib.parse import urlparse, parse_qs

SECRET_KEY = os.getenv('SECRET_KEY', 'nexora-verify-secret-2024')

def decode_token(token_str):
    """Decode and verify a signed token. Returns (user_id, shortener_link, time_left) or raises."""
    if '.' not in token_str:
        return None, None, None
    payload_b64, sig = token_str.rsplit('.', 1)

    # Verify signature
    expected_sig = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None, None, None

    # Decode payload
    padding = 4 - len(payload_b64) % 4
    payload_str = base64.urlsafe_b64decode((payload_b64 + '=' * padding).encode()).decode()
    data = json.loads(payload_str)

    user_id = data['uid']
    shortener_link = data['link']
    timestamp = data['ts']

    time_left = 300 - (int(time.time()) - timestamp)
    return user_id, shortener_link, time_left

class handler(BaseHTTPRequestHandler):
    
    def do_GET(self):
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

            # Decode + verify signed token (no DB needed)
            user_id, shortener_link, time_left = decode_token(token)

            if user_id is None:
                self.send_error_page("Invalid or expired verification link")
                return

            if time_left <= 0:
                self.send_error_page("Verification link has expired")
                return

            self.send_verification_page(token, user_id_param, time_left, path_prefix)
        else:
            self.send_error_page("Invalid URL")
    
    def do_POST(self):
        """Handle verification submission"""
        path = self.path
        path_parts = path.split('/')

        # Extract token: /pre-verify/TOKEN/submit or /verify/TOKEN/submit
        if len(path_parts) >= 4 and path_parts[1] in ('pre-verify', 'verify') and path_parts[3] == 'submit':
            token = path_parts[2]

            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            user_id = data.get('user_id', 'anonymous')
            interaction_time = data.get('interaction_time', 0)

            if interaction_time < 10:
                self.send_json_response({'success': False, 'message': 'Please wait for the full countdown'})
                return

            # Decode + verify signed token (no DB needed)
            token_user_id, shortener_link, time_left = decode_token(token)

            if token_user_id is None or time_left <= 0:
                self.send_json_response({'success': False, 'message': 'Invalid or expired verification link'})
                return

            # Return shortener link directly from token
            self.send_json_response({'success': True, 'redirect_url': shortener_link})
        else:
            self.send_json_response({'success': False, 'message': 'Invalid request'})
    
    def send_verification_page(self, token, user_id, time_left, path_prefix='pre-verify'):
        """Send verification HTML page"""
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔐 Verification Required</title>
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
        const VERIFICATION_TIME = 10;
        let timeLeft = VERIFICATION_TIME;
        let selectedAnswer = null;
        let interactionTime = 0;
        
        const challenges = [
            {{ q: "What is 5 + 3?", a: ["6", "8", "9", "7"], correct: "8" }},
            {{ q: "What is 10 - 4?", a: ["5", "6", "7", "8"], correct: "6" }},
            {{ q: "What is 3 × 4?", a: ["10", "12", "14", "16"], correct: "12" }},
            {{ q: "What is 15 ÷ 3?", a: ["3", "4", "5", "6"], correct: "5" }},
            {{ q: "What is 7 + 8?", a: ["14", "15", "16", "17"], correct: "15" }},
            {{ q: "What is 20 - 8?", a: ["10", "11", "12", "13"], correct: "12" }},
            {{ q: "What is 6 × 2?", a: ["10", "11", "12", "13"], correct: "12" }},
            {{ q: "What is 18 ÷ 2?", a: ["7", "8", "9", "10"], correct: "9" }},
            {{ q: "What is 9 + 6?", a: ["13", "14", "15", "16"], correct: "15" }},
            {{ q: "What is 25 - 10?", a: ["13", "14", "15", "16"], correct: "15" }}
        ];
        
        const challenge = challenges[Math.floor(Math.random() * challenges.length)];
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
            if (interactionTime >= VERIFICATION_TIME && selectedAnswer) {{
                btn.classList.add('active');
                btn.disabled = false;
            }}
        }}
        
        document.getElementById('verifyBtn').onclick = async () => {{
            if (selectedAnswer !== challenge.correct) {{
                showError('❌ Incorrect answer! Please try again.');
                document.querySelectorAll('.challenge-btn').forEach(b => b.classList.remove('selected'));
                selectedAnswer = null;
                checkVerifyButton();
                return;
            }}
            
            document.getElementById('loading').classList.add('active');
            document.getElementById('verifyBtn').disabled = true;
            
            try {{
                const response = await fetch(`/${path_prefix}/${{TOKEN}}/submit`, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        user_id: USER_ID,
                        interaction_time: interactionTime,
                        challenge_answer: selectedAnswer
                    }})
                }});
                
                const data = await response.json();
                
                if (data.success) {{
                    document.getElementById('loading').innerHTML = '<div style="color: #4caf50; font-size: 24px; margin-bottom: 10px;">✓</div><p style="color: #4caf50; font-weight: 600;">Verification Successful!</p><p style="color: #666; font-size: 14px;">Redirecting to download link...</p>';
                    setTimeout(() => window.location.href = data.redirect_url, 1000);
                }} else {{
                    showError(data.message || 'Verification failed');
                    document.getElementById('loading').classList.remove('active');
                    document.getElementById('verifyBtn').disabled = false;
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
    
    def send_json_response(self, data):
        """Send JSON response"""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
