# 🔐 Bot Verification Service

Pre-shortener verification system for Telegram file-sharing bot. Deployed on Vercel.

## 🎯 Features

- ✅ **10-second countdown** verification
- ✅ **Math challenge** to prevent bots (answer verified **server-side**)
- ✅ **Cloudflare Turnstile** human check, verified server-side (LinkForge-style)
- ✅ **Chrome-only access** — server-side browser gate, non-Chrome gets an "open in Chrome" page
- ✅ **MongoDB session tracking** — every visit is a session (browser, IP hash, Turnstile result, attempts, status)
- ✅ **Rate limiting** — 10/min and 70/hour per IP hash (LinkForge's limits)
- ✅ **MongoDB integration** for token storage
- ✅ **Beautiful responsive UI**
- ✅ **One-time use tokens** (enforced in MongoDB)
- ✅ **5-minute token expiry**
- ✅ **User-specific validation**
- ✅ **Admin sessions endpoint** — `GET /api/sessions` with `ADMIN_KEY`

## 🚀 Quick Deploy to Vercel

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/xarveth/bot-verification)

### Manual Deployment

1. **Fork this repository**

2. **Go to [Vercel Dashboard](https://vercel.com/dashboard)**

3. **Click "Add New" → "Project"**

4. **Import your forked repository**

5. **Add Environment Variables** (all of them — see table below; at minimum `SECRET_KEY` and `DB_URI`):
   - Key: `SECRET_KEY` — Value: a long random string (generate one, e.g. `openssl rand -hex 32`)
   - Key: `DB_URI` — Value: Your MongoDB connection string

6. **Click "Deploy"**

7. **Done!** You'll get a URL like: `https://your-project.vercel.app`

> ⚠️ `SECRET_KEY` has **no default** any more. The old hardcoded fallback was removed — if it is not set, token creation and verification refuse to work instead of silently using a public secret. Rotate it if the old default was ever live: old tokens stop working, which is the point.

## 🔧 Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SECRET_KEY` | HMAC key for signed tokens + math challenges. **No default — must be set.** | Yes |
| `DB_URI` | MongoDB connection string (session tracking + one-time tokens) | Yes |
| `TURNSTILE_SITE_KEY` | Cloudflare Turnstile site key | For Turnstile |
| `TURNSTILE_SECRET_KEY` | Cloudflare Turnstile secret key | For Turnstile |
| `CHROME_ONLY` | `true` (default) / `false` — Chrome-only gate | No |
| `BOT_API_KEY` | If set, bot must send it as `X-Api-Key` to `POST /api/create-token` | No |
| `ADMIN_KEY` | Key for `GET /api/sessions` (send as `X-Admin-Key` header) | For sessions API |
| `RATE_LIMIT_PER_MINUTE` | Default `10` | No |
| `RATE_LIMIT_PER_HOUR` | Default `70` | No |

Example:
```
SECRET_KEY=<long random string>
DB_URI=mongodb+srv://username:password@cluster.mongodb.net/bot_database?retryWrites=true&w=majority
TURNSTILE_SITE_KEY=0x4AAAAAA...
TURNSTILE_SECRET_KEY=0x4AAAAAA...
CHROME_ONLY=true
ADMIN_KEY=<long random string>
```

### Cloudflare Turnstile setup (free)

1. Go to [Cloudflare Dashboard → Turnstile](https://dash.cloudflare.com/?to=/:account/turnstile) → Add site.
2. Widget type: **Managed** (invisible check, like LinkForge). Domain: your Vercel domain.
3. Copy the **Site Key** → `TURNSTILE_SITE_KEY`, and the **Secret Key** → `TURNSTILE_SECRET_KEY` in Vercel.
4. Redeploy. Turnstile is only enforced when **both** keys are set — until then the widget is hidden, the step is skipped, and the session is flagged `turnstile_skipped: true`, so a deploy without keys does not break the live flow.

### Chrome-only — honest note

The gate checks the `User-Agent` (+ `Sec-CH-UA` when present) on the server for every verification page and submit. It stops casual non-Chrome browsers, but a User-Agent can be spoofed, so it is friction, not unbreakable security. Brave is caught twice: its `Sec-CH-UA` brand is not "Google Chrome", and the page also checks `navigator.brave.isBrave()` + `userAgentData` brands in JavaScript and reports the result on submit (Brave's desktop User-Agent alone mimics Chrome, which is how the freeshare site catches it too). It also affects Telegram's in-app browser: on Android Telegram usually opens links in a Chrome Custom Tab (passes), on iOS it opens Safari WebView (blocked — user must tap "Open in Chrome/Safari" / copy the link into Chrome). Set `CHROME_ONLY=false` in Vercel to turn the gate off without redeploying code.

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
Validates user verification and returns a one-time finish URL (not the shortener link itself — see step 4).

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
  "redirect_url": "/finish?t=<one-time-finish-token>"
}
```

### 4. Finish — anti-bypass re-check (like freeshare's /finish)
```
GET /finish?t=<token>   -> "Continue securely" page
POST /finish?t=<token>  -> 302 redirect to the shortener link
```
The verify token is only base64, so anyone could decode it and read the shortener link without verifying. The link is therefore never returned by submit: instead the browser gets a one-time finish token whose link is encrypted server-side. `/finish` re-checks it before releasing the link — token signature + 5-minute expiry, one-time use, the session that earned it must have status `verified`, and the IP / browser must match that session. A tampered, reused, expired, or skipped-verification finish link gets a "Verification required" error instead of the link.

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

If `BOT_API_KEY` is set, send it as `X-Api-Key` header.

### 5. List Sessions (Admin)
```
GET /api/sessions?limit=50&status=verified
Header: X-Admin-Key: <ADMIN_KEY>
```
Returns recent sessions, sanitised (IP hash only, no raw IP, no token). Requires `ADMIN_KEY` and MongoDB.

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

- **Turnstile human check**: Cloudflare Turnstile widget on the verification page, token verified server-side against Cloudflare before the submit is accepted.
- **Chrome-only gate**: server-side User-Agent + Sec-CH-UA check on every page/submit; non-Chrome gets a "Please open this link in Google Chrome" page.
- **Session tracking (MongoDB)**: one `verification_sessions` document per visit — session ID, Telegram user, IP **hash** (raw IPs are never stored), browser + Chrome version, Turnstile result, attempts, status (`created` → `page_viewed` → `verified` / `blocked`), event timeline, 5-minute TTL. View them at `GET /api/sessions` with `X-Admin-Key: <ADMIN_KEY>` (supports `?limit=&status=&session_id=`).
- **Rate limiting**: 10 requests/min and 70/hour per IP hash, counted from sessions.
- **Time-based validation**: Must wait full 10 seconds — measured **server-side** from page-view to submit, not just the client-reported timer.
- **Math challenge**: Random questions, generated and signed on the server; the answer is verified server-side. The correct answer is never sent to the page.
- **One-time tokens**: Each token can only be used once — enforced in MongoDB (`used_tokens`), even inside its 5-minute window. Reusing a verified link shows "already been used".
- **User-specific**: Tokens tied to specific user IDs, and the submit session must match the token.
- **Expiry**: Tokens expire after 5 minutes
- **Server-side validation**: All checks happen on server
- **No hardcoded secrets**: `SECRET_KEY` must come from env vars.

## 📊 Database Schema

### Collection: `verification_sessions`

```javascript
{
  "session_id": "…",            // bv_session cookie, HttpOnly + Secure + SameSite=Lax
  "user_id": "123456789",
  "token_hash": "…",            // sha256 of the verification token
  "created_at": ISODate("…"),
  "expires_at": ISODate("…"),   // +5 min, TTL index
  "last_seen_at": ISODate("…"),
  "ip_hash": "…",               // sha256, raw IP never stored
  "user_agent": "Mozilla/5.0 … Chrome/…",
  "is_chrome": true,
  "chrome_version": "131",
  "turnstile_verified": true,
  "turnstile_skipped": false,
  "status": "verified",         // created | page_viewed | verified | blocked
  "attempts": 0,
  "interaction_time": 10,
  "events": [{ "ts": ISODate("…"), "event": "page_viewed" }]
}
```

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
