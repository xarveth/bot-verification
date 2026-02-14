# 🚀 Deployment Guide

## Quick Deploy to Vercel (5 Minutes)

### Step 1: Fork or Clone This Repository

Click the "Fork" button on GitHub or clone:
```bash
git clone https://github.com/xarveth/bot-verification.git
```

### Step 2: Deploy to Vercel

#### Option A: One-Click Deploy (Easiest)

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/xarveth/bot-verification)

1. Click the button above
2. Sign in to Vercel (or create account)
3. Click "Create"
4. Add environment variable:
   - **Name:** `DB_URI`
   - **Value:** Your MongoDB connection string
5. Click "Deploy"
6. Wait 1-2 minutes
7. Done! Copy your Vercel URL

#### Option B: Manual Deploy via Dashboard

1. Go to [Vercel Dashboard](https://vercel.com/dashboard)
2. Click "Add New" → "Project"
3. Import your forked repository
4. Configure:
   - **Framework Preset:** Other
   - **Root Directory:** `./`
   - **Build Command:** (leave empty)
   - **Output Directory:** (leave empty)
5. Add Environment Variable:
   - **Key:** `DB_URI`
   - **Value:** `mongodb+srv://username:password@cluster.mongodb.net/bot_database`
6. Click "Deploy"
7. Copy your deployment URL (e.g., `https://bot-verification.vercel.app`)

#### Option C: Deploy via CLI

```bash
# Install Vercel CLI
npm install -g vercel

# Login to Vercel
vercel login

# Navigate to project
cd bot-verification

# Deploy
vercel

# Add environment variable
vercel env add DB_URI production
# Paste your MongoDB URI when prompted

# Deploy to production
vercel --prod
```

### Step 3: Get Your MongoDB URI

If you don't have MongoDB:

1. Go to [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
2. Create free account
3. Create free cluster (M0)
4. Click "Connect"
5. Choose "Connect your application"
6. Copy connection string
7. Replace `<password>` with your database password
8. Replace `<dbname>` with `bot_database`

Example:
```
mongodb+srv://myuser:mypassword@cluster0.mongodb.net/bot_database?retryWrites=true&w=majority
```

### Step 4: Verify Deployment

Visit your Vercel URL:
```
https://your-project.vercel.app
```

You should see: "🔐 Bot Verification Service - ✓ ACTIVE & RUNNING"

### Step 5: Test API

Test token creation:
```bash
curl -X POST https://your-project.vercel.app/api/create-token \
  -H "Content-Type: application/json" \
  -d '{"user_id":"123456789","shortener_link":"https://example.com"}'
```

Expected response:
```json
{
  "success": true,
  "token": "abc123def456...",
  "expires_in": 300
}
```

---

## 🔧 Configure Your Bot (VPS)

### Step 1: Update Bot Environment

```bash
# On your VPS
cd /root/fileb2

# Set Vercel URL
export BOT_URL=https://your-project.vercel.app

# Or add to .env file
echo "BOT_URL=https://your-project.vercel.app" >> .env
```

### Step 2: Install Required Package

```bash
pip3 install requests

# Add to requirements.txt
echo "requests" >> requirements.txt
```

### Step 3: Add Helper Function to Bot

Create `plugins/vercel_helper.py`:

```python
import requests
import os

def create_verification_link(user_id, shortener_link):
    """Create verification link via Vercel API"""
    vercel_url = os.getenv('BOT_URL', '')
    
    if not vercel_url:
        print("Error: BOT_URL not set!")
        return None
    
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
            print(f"Error creating token: {data.get('message')}")
            return None
            
    except Exception as e:
        print(f"Error calling Vercel API: {e}")
        return None
```

### Step 4: Update `plugins/start.py`

Add import at top:
```python
from plugins.vercel_helper import create_verification_link
```

Replace shortener section with:
```python
if not is_user_pro and user_id != OWNER_ID and not is_short_link and shortner_enabled:
    # Create shortener link first
    shortener_link = get_short(bot_link, client)
    
    # Create verification link (verification BEFORE shortener)
    verification_link = create_verification_link(
        user_id=user_id,
        shortener_link=shortener_link
    )
    
    if not verification_link:
        return await message.reply("Failed to generate verification link. Please try again.")
    
    # Send verification link to user
    await client.send_photo(
        chat_id=message.chat.id,
        photo=short_photo,
        caption=short_caption,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("• ᴏᴘᴇɴ ʟɪɴᴋ", url=verification_link),
                InlineKeyboardButton("ᴛᴜᴛᴏʀɪᴀʟ •", url=tutorial_link)
            ]
        ])
    )
    return
```

### Step 5: Restart Bot

```bash
systemctl restart filebot
# OR
python3 main.py
```

---

## ✅ Testing Complete Flow

1. **Request file from bot** (as non-premium user)
2. **Bot sends verification link** (Vercel URL)
3. **Click verification link**
4. **Verification page loads** (10-second countdown)
5. **Wait 10 seconds**
6. **Answer math question**
7. **Click "Verify & Continue"**
8. **Redirects to shortener**
9. **Complete shortener**
10. **Get files from bot**

---

## 🔄 Update Deployment

### Update Code

```bash
# Make changes to your code
git add .
git commit -m "Update verification system"
git push origin main
```

Vercel will automatically redeploy!

### Update Environment Variables

```bash
# Via CLI
vercel env rm DB_URI production
vercel env add DB_URI production

# Or via Dashboard:
# 1. Go to project settings
# 2. Click "Environment Variables"
# 3. Edit or add variables
# 4. Redeploy
```

---

## 🐛 Troubleshooting

### Issue: "Database connection error"

**Solution:** Check your MongoDB URI
```bash
# Test MongoDB connection
vercel env ls

# Update if needed
vercel env add DB_URI production
```

### Issue: "Invalid URL"

**Solution:** Check Vercel routes in `vercel.json`
```json
{
  "routes": [
    {
      "src": "/pre-verify/([^/]+)",
      "dest": "/api/verify.py"
    }
  ]
}
```

### Issue: Bot can't connect to Vercel

**Solution:** Check BOT_URL is set correctly
```bash
echo $BOT_URL
# Should output: https://your-project.vercel.app

# If empty, set it:
export BOT_URL=https://your-project.vercel.app
```

### Issue: Verification page shows error

**Solution:** Check MongoDB has data
```javascript
// In MongoDB Atlas, check collection:
db.verification_tokens.find()
```

---

## 📊 Monitoring

### View Logs

```bash
# Via CLI
vercel logs

# Or in Vercel Dashboard:
# Project → Deployments → Click deployment → View Logs
```

### Check Database

```javascript
// MongoDB Atlas → Collections → verification_tokens
{
  "token": "abc123...",
  "user_id": "123456789",
  "shortener_link": "https://...",
  "created_at": 1234567890,
  "verified": false
}
```

---

## 🎯 Custom Domain (Optional)

### Add Custom Domain

1. Go to Vercel Dashboard
2. Select your project
3. Click "Settings" → "Domains"
4. Add your domain (e.g., `verify.yourdomain.com`)
5. Update DNS records as shown
6. Update BOT_URL in your bot:
   ```bash
   export BOT_URL=https://verify.yourdomain.com
   ```

---

## 💰 Cost

- **Vercel:** FREE (Hobby plan)
- **MongoDB:** FREE (M0 cluster)
- **Total:** $0/month

**Limits:**
- Vercel: 100GB bandwidth/month
- MongoDB: 512MB storage
- More than enough for most bots!

---

## 🔐 Security Best Practices

1. **Keep DB_URI secret** - Never commit to Git
2. **Use environment variables** - Don't hardcode credentials
3. **Enable MongoDB IP whitelist** - Restrict access
4. **Monitor logs** - Check for suspicious activity
5. **Update dependencies** - Keep packages up to date

---

## 📞 Support

- **Issues:** [GitHub Issues](https://github.com/xarveth/bot-verification/issues)
- **Documentation:** [README.md](README.md)
- **Vercel Docs:** [vercel.com/docs](https://vercel.com/docs)

---

**Deployment complete! Your verification system is now live on Vercel!** 🎉
