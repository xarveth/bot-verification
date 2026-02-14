from http.server import BaseHTTPRequestHandler
from pymongo import MongoClient
import json
import time
import hashlib
import secrets
import os

DB_URI = os.getenv('DB_URI', '')

def get_db():
    """Get MongoDB database"""
    if not DB_URI:
        return None
    client = MongoClient(DB_URI)
    return client['bot_database']

class handler(BaseHTTPRequestHandler):
    
    def do_POST(self):
        """Create verification token"""
        try:
            # Read POST data
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            user_id = data.get('user_id')
            shortener_link = data.get('shortener_link')
            
            if not user_id or not shortener_link:
                self.send_json_response({
                    'success': False,
                    'message': 'Missing user_id or shortener_link'
                })
                return
            
            # Generate unique token
            timestamp = int(time.time())
            token_data = f"{user_id}:{shortener_link}:{timestamp}:{secrets.token_hex(16)}"
            token = hashlib.sha256(token_data.encode()).hexdigest()
            
            # Store in database
            db = get_db()
            if not db:
                self.send_json_response({
                    'success': False,
                    'message': 'Database connection error'
                })
                return
            
            # Insert token into database
            db.verification_tokens.insert_one({
                'token': token,
                'user_id': str(user_id),
                'shortener_link': shortener_link,
                'created_at': timestamp,
                'verified': False
            })
            
            # Return token
            self.send_json_response({
                'success': True,
                'token': token,
                'expires_in': 300  # 5 minutes
            })
            
        except Exception as e:
            self.send_json_response({
                'success': False,
                'message': f'Error: {str(e)}'
            })
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def send_json_response(self, data):
        """Send JSON response"""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
