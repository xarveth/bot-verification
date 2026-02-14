# ⚡ Quick Start Guide

Get your verification system running in 5 minutes!

---

## 🎯 What You'll Get

```
User → Verification (10s) → Shortener → Bot → Files
```

**Benefits:**
- ✅ Shortener link hidden until verification
- ✅ 10-second user engagement
- ✅ Math challenge prevents bots
- ✅ Beautiful professional UI
- ✅ Free hosting on Vercel

---

## 🚀 5-Minute Setup

### 1️⃣ Deploy to Vercel (2 minutes)

Click this button:

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/xarveth/bot-verification)

1. Sign in to Vercel
2. Click "Create"
3. Add environment variable:
   - **Name:** `DB_URI`
   - **Value:** Your MongoDB URI
4. Click "Deploy"
5. **Copy your Vercel URL** (e.g., `https://bot-verification-xyz.vercel.app`)

**Don't have MongoDB?** Get free MongoDB:
- Go to [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
- Create free account → Create cluster → Get connection string

---

### 2️⃣ Configure Bot (2 minutes)

On your VPS:

```bash
# Navigate to bot directory
cd /root/fileb2

# Set Vercel URL
export BOT_URL=https://your-vercel-url.vercel.app

# Install requests
pip3 install requests
```

---

### 3️⃣ Add Helper File (1 minute)

Create `plugins/vercel_helper.py`:

```bash
curl -o plugins/vercel_helper.py https://raw.githubusercontent.com/xarveth/bot-verification/main/examples/vercel_helper.py
```

Or create manually:

```python
import requests
import os

def create_verification_link(user_id, shortener_link):
    vercel_url = os.getenv('BOT_URL', '')
    if not vercel_url:
        return None
    
    try:
        response = requests.post(
            f"{vercel_url}/api/create-token",
            json={'user_id': str(user_id), 'shortener_link': shortener_link},
            timeout=10
        )
        data = response.json()
        if data.get('success'):
            return f"{vercel_url}/pre-verify/{data['token']}?uid={user_id}"
    except:
        pass
    return None
```

---

### 4️⃣ Update Bot Code (30 seconds)

Edit `plugins/start.py`:

**Add import at top:**
```python
from plugins.vercel_helper import create_verification_link
```

**Replace shortener section with:**
```python
if not is_user_pro and shortner_enabled:
    shortener_link = get_short(bot_link, client)
    verification_link = create_verification_link(user_id, shortener_link)
    
    if not verification_link:
        return await message.reply("Verification unavailable. Try again.")
    
    # Send verification_link instead of shortener_link
    await client.send_photo(
        chat_id=message.chat.id,
        photo=short_photo,
        caption=short_caption,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("• ᴏᴘᴇɴ ʟɪɴᴋ", url=verification_link)
        ]])
    )
    return
```

---

### 5️⃣ Restart Bot (10 seconds)

```bash
systemctl restart filebot
# OR
python3 main.py
```

---

## ✅ Test It!

1. Request file from bot (as non-premium user)
2. Click "ᴏᴘᴇɴ ʟɪɴᴋ" button
3. Verification page opens (10-second countdown)
4. Wait 10 seconds
5. Answer math question
6. Click "Verify & Continue"
7. Redirects to shortener
8. Complete shortener
9. Get files!

---

## 🎉 Done!

Your verification system is now live!

**What's Next?**

- 📖 Read [DEPLOYMENT.md](DEPLOYMENT.md) for advanced setup
- 🤖 Read [BOT_INTEGRATION.md](BOT_INTEGRATION.md) for customization
- 🐛 Check [README.md](README.md) for troubleshooting

---

## 🆘 Quick Troubleshooting

### "BOT_URL not set"
```bash
export BOT_URL=https://your-vercel-url.vercel.app
```

### "Database connection error"
Check MongoDB URI in Vercel dashboard → Settings → Environment Variables

### "Verification unavailable"
```bash
# Test Vercel is running
curl https://your-vercel-url.vercel.app
```

### Bot not sending verification link
```bash
# Check helper file exists
ls plugins/vercel_helper.py

# Check import works
python3 -c "from plugins.vercel_helper import create_verification_link; print('OK')"
```

---

## 📊 Architecture

```
┌─────────────────────────────────────────────┐
│              YOUR SETUP                     │
├─────────────────────────────────────────────┤
│                                             │
│  VPS (Your Server)                          │
│  ├─ Telegram Bot                            │
│  └─ Calls Vercel API                        │
│                                             │
│  Vercel (Free Hosting)                      │
│  ├─ Verification Pages                      │
│  ├─ Token Creation API                      │
│  └─ Connects to MongoDB                     │
│                                             │
│  MongoDB Atlas (Free)                       │
│  └─ Stores verification tokens              │
│                                             │
└─────────────────────────────────────────────┘
```

---

## 💰 Cost

- **Vercel:** FREE
- **MongoDB:** FREE
- **Total:** $0/month

---

## 🔗 Useful Links

- **Vercel Dashboard:** https://vercel.com/dashboard
- **MongoDB Atlas:** https://www.mongodb.com/cloud/atlas
- **Full Documentation:** [README.md](README.md)
- **Deployment Guide:** [DEPLOYMENT.md](DEPLOYMENT.md)
- **Integration Guide:** [BOT_INTEGRATION.md](BOT_INTEGRATION.md)

---

**Need help? Open an issue on GitHub!** 🚀
