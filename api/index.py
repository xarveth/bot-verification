from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bot Verification Service</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .container {
            background: white;
            padding: 60px 40px;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
            max-width: 600px;
            animation: fadeIn 0.5s ease-out;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        h1 {
            color: #667eea;
            font-size: 36px;
            margin-bottom: 20px;
        }
        .status {
            display: inline-block;
            background: #4caf50;
            color: white;
            padding: 10px 25px;
            border-radius: 25px;
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 30px;
            box-shadow: 0 4px 15px rgba(76, 175, 80, 0.3);
        }
        .description {
            color: #666;
            font-size: 18px;
            line-height: 1.8;
            margin-bottom: 20px;
        }
        .features {
            background: #f8f9fa;
            padding: 30px;
            border-radius: 15px;
            margin: 30px 0;
            text-align: left;
        }
        .features h2 {
            color: #667eea;
            font-size: 20px;
            margin-bottom: 20px;
            text-align: center;
        }
        .feature-item {
            display: flex;
            align-items: center;
            margin-bottom: 15px;
            color: #555;
        }
        .feature-item::before {
            content: "✓";
            color: #4caf50;
            font-weight: bold;
            font-size: 20px;
            margin-right: 15px;
        }
        .footer {
            margin-top: 40px;
            padding-top: 30px;
            border-top: 2px solid #eee;
            color: #999;
            font-size: 14px;
        }
        .tech-stack {
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-top: 20px;
            flex-wrap: wrap;
        }
        .tech-badge {
            background: #667eea;
            color: white;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
        }
        .api-info {
            background: #e3f2fd;
            padding: 20px;
            border-radius: 10px;
            margin-top: 20px;
            border-left: 4px solid #2196f3;
        }
        .api-info h3 {
            color: #1976d2;
            margin-bottom: 10px;
        }
        .api-info code {
            background: #fff;
            padding: 2px 8px;
            border-radius: 4px;
            color: #d32f2f;
            font-family: 'Courier New', monospace;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔐 Bot Verification Service</h1>
        <div class="status">✓ ACTIVE & RUNNING</div>
        
        <p class="description">
            Advanced pre-shortener verification system for Telegram bots.
            Protects your shortener links with time-based challenges and user validation.
        </p>
        
        <div class="features">
            <h2>🎯 Features</h2>
            <div class="feature-item">10-second countdown verification</div>
            <div class="feature-item">Random math challenge questions</div>
            <div class="feature-item">One-time use security tokens</div>
            <div class="feature-item">User-specific validation</div>
            <div class="feature-item">5-minute token expiry</div>
            <div class="feature-item">Beautiful responsive UI</div>
            <div class="feature-item">MongoDB integration</div>
            <div class="feature-item">Server-side validation</div>
        </div>
        
        <div class="api-info">
            <h3>📡 API Endpoints</h3>
            <p style="color: #555; margin-top: 10px;">
                <strong>Verification:</strong> <code>/pre-verify/{token}</code><br>
                <strong>Create Token:</strong> <code>/api/create-token</code>
            </p>
        </div>
        
        <div class="tech-stack">
            <span class="tech-badge">Python</span>
            <span class="tech-badge">Vercel</span>
            <span class="tech-badge">MongoDB</span>
            <span class="tech-badge">Serverless</span>
        </div>
        
        <div class="footer">
            <p>🛡️ Protected by Advanced Anti-Bypass Technology</p>
            <p style="margin-top: 10px;">Deployed on Vercel | Powered by Python</p>
        </div>
    </div>
</body>
</html>
        """
        
        self.wfile.write(html.encode())
