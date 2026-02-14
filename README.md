# 🔐 Bot Verification Service

Pre-shortener verification system for Telegram file-sharing bot. Deployed on Vercel.

## 🎯 Features

- ✅ **10-second countdown** verification
- ✅ **Math challenge** to prevent bots
- ✅ **MongoDB integration** for token storage
- ✅ **Beautiful responsive UI**
- ✅ **One-time use tokens**
- ✅ **5-minute token expiry**
- ✅ **User-specific validation**

## 🚀 Quick Deploy to Vercel

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/xarveth/bot-verification)

### Manual Deployment

1. **Fork this repository**

2. **Go to [Vercel Dashboard](https://vercel.com/dashboard)**

3. **Click "Add New" → "Project"**

4. **Import your forked repository**

5. **Add Environment Variable:**
   - Key: `DB_URI`
   - Value: Your MongoDB connection string

6. **Click "Deploy"**

7. **Done!** You'll get a URL like: `https://your-project.vercel.app`

## 🔧 Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DB_URI` | MongoDB connection string | Yes |

Example:
```
DB_URI=mongodb+srv://username:password@cluster.mongodb.net/bot_database?retryWrites=true&w=majority
```

## 📡 API Endpoints

### 1. Home Page
```
GET /
```
Shows service status page.

### 2. Verification Page
```
GET /pre-verify/{token}?uid={user_id}
```
Displays verification page with countdown and challenge.

### 3. Submit Verification
```
POST /pre-verify/{token}/submit
```
Validates user verification and returns shortener link.

**Request Body:**
```json
{
  "user_id": "123456789",
  "interaction_time": 10,
  "challenge_answer": "8"
}
```

**Response:**
```json
{
  "success": true,
  "redirect_url": "https://shortener.link/abc123"
}
```

### 4. Create Token (For Bot)
```
POST /api/create-token
```
Creates verification token and stores in database.

**Request Body:**
```json
{
  "user_id": "123456789",
  "shortener_link": "https://shortener.link/abc123"
}
```

**Response:**
```json
{
  "success": true,
  "token": "abc123def456..."
}
```

## 🔗 Integration with Your Bot

### Install requests library:
```bash
pip install requests
```

### Add to your bot code:

```python
import requests
import os

def create_verification_link(user_id, shortener_link):
    """Create verification link via Vercel"""
    vercel_url = os.getenv('BOT_URL', 'https://your-project.vercel.app')
    
    try:
        response = requests.post(
            f"{vercel_url}/api/create-token",
            json={
                'user_id': str(user_id),
                'shortener_link': shortener_link
            },
            timeout=10
        )
        
        data = response.json()
        
        if data.get('success'):
            token = data['token']
            return f"{vercel_url}/pre-verify/{token}?uid={user_id}"
        else:
            return None
            
    except Exception as e:
        print(f"Error: {e}")
        return None

# Usage in your bot
shortener_link = get_short(bot_link)  # Your existing shortener function
verification_link = create_verification_link(user_id, shortener_link)

# Send verification_link to user (not shortener_link!)
```

## 🔄 User Flow

```
1. User requests file from bot
   ↓
2. Bot creates shortener link
   ↓
3. Bot calls Vercel API to create verification token
   ↓
4. Bot sends verification link to user
   ↓
5. User clicks verification link
   ↓
6. Vercel shows verification page (10-second countdown)
   ↓
7. User waits and answers math question
   ↓
8. User clicks "Verify & Continue"
   ↓
9. Vercel validates and redirects to shortener
   ↓
10. User completes shortener
   ↓
11. User gets bot link and files
```

## 🛡️ Security Features

- **Time-based validation**: Must wait full 10 seconds
- **Math challenge**: Random questions prevent automation
- **One-time tokens**: Each token can only be used once
- **User-specific**: Tokens tied to specific user IDs
- **Expiry**: Tokens expire after 5 minutes
- **Server-side validation**: All checks happen on server

## 📊 Database Schema

### Collection: `verification_tokens`

```javascript
{
  "token": "abc123def456...",
  "user_id": "123456789",
  "shortener_link": "https://shortener.link/abc123",
  "created_at": 1234567890,
  "verified": false
}
```

## 🎨 Customization

### Change verification time:

Edit `api/verify.py` line 30:
```python
# Change from 10 to your desired seconds
if interaction_time < 15:  # 15 seconds instead of 10
```

### Change token expiry:

Edit `api/verify.py` line 45:
```python
# Change from 300 (5 minutes) to your desired seconds
time_left = 600 - (current_time - token_data['created_at'])  # 10 minutes
```

### Add more math questions:

Edit `api/verify.py` in the HTML section:
```javascript
const challenges = [
    { q: "What is 5 + 3?", a: ["6", "8", "9", "7"], correct: "8" },
    { q: "Your question?", a: ["A", "B", "C", "D"], correct: "B" },
    // Add more...
];
```

## 🧪 Testing

### Test verification page:
```bash
curl https://your-project.vercel.app
```

### Test token creation:
```bash
curl -X POST https://your-project.vercel.app/api/create-token \
  -H "Content-Type: application/json" \
  -d '{"user_id":"123456789","shortener_link":"https://example.com"}'
```

## 📝 License

MIT License - Feel free to use and modify!

## 🤝 Support

For issues or questions:
- Open an issue on GitHub
- Check the documentation above
- Review the code in `api/` directory

## 🌟 Credits

Created for Telegram file-sharing bots with shortener protection.

---

**Deployed on Vercel** | **Powered by Python** | **Secured by Design**
