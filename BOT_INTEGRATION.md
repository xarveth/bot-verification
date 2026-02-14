# 🤖 Bot Integration Guide

Complete guide to integrate Vercel verification system with your Telegram bot.

---

## 📋 Prerequisites

- ✅ Vercel deployment complete
- ✅ MongoDB connected
- ✅ Vercel URL obtained (e.g., `https://your-project.vercel.app`)
- ✅ Bot running on VPS

---

## 🚀 Quick Integration (3 Steps)

### Step 1: Set Environment Variable

```bash
# On your VPS
cd /root/fileb2

# Set Vercel URL
export BOT_URL=https://your-project.vercel.app

# Make it permanent (add to .bashrc)
echo 'export BOT_URL=https://your-project.vercel.app' >> ~/.bashrc
source ~/.bashrc

# Or use .env file
echo "BOT_URL=https://your-project.vercel.app" >> .env
```

### Step 2: Install Dependencies

```bash
# Install requests library
pip3 install requests

# Add to requirements.txt
echo "requests" >> requirements.txt
```

### Step 3: Create Helper File

Create `plugins/vercel_helper.py`:

```bash
cat > plugins/vercel_helper.py << 'EOF'
import requests
import os

def create_verification_link(user_id, shortener_link):
    """
    Create verification link via Vercel API
    
    Args:
        user_id: Telegram user ID
        shortener_link: Already shortened URL
    
    Returns:
        Verification link or None if failed
    """
    vercel_url = os.getenv('BOT_URL', '')
    
    if not vercel_url:
        print("❌ Error: BOT_URL environment variable not set!")
        return None
    
    try:
        # Call Vercel API to create token
        response = requests.post(
            f"{vercel_url}/api/create-token",
            json={
                'user_id': str(user_id),
                'shortener_link': shortener_link
            },
            timeout=10
        )
        
        # Check response
        if response.status_code != 200:
            print(f"❌ Vercel API error: {response.status_code}")
            return None
        
        data = response.json()
        
        if data.get('success'):
            token = data['token']
            verification_link = f"{vercel_url}/pre-verify/{token}?uid={user_id}"
            print(f"✅ Verification link created for user {user_id}")
            return verification_link
        else:
            print(f"❌ Token creation failed: {data.get('message')}")
            return None
            
    except requests.exceptions.Timeout:
        print("❌ Vercel API timeout")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None
EOF
```

---

## 🔧 Update Bot Code

### Option A: Modify `plugins/start.py`

Find the shortener section (around line 50-100) and replace with:

```python
# Add import at top of file
from plugins.vercel_helper import create_verification_link

# ... existing code ...

# In the /start command handler, find shortener section:
if not is_user_pro and user_id != OWNER_ID and not is_short_link and shortner_enabled:
    try:
        # Step 1: Create bot link (normal)
        bot_link = f"https://t.me/{client.username}?start=yu3elk{base64_string}7"
        
        # Step 2: Create shortener link from bot link
        shortener_link = get_short(bot_link, client)
        
        if not shortener_link:
            return await message.reply("Failed to create shortener link.")
        
        # Step 3: Create verification link (verification BEFORE shortener)
        verification_link = create_verification_link(
            user_id=user_id,
            shortener_link=shortener_link
        )
        
        if not verification_link:
            return await message.reply(
                "⚠️ Verification system temporarily unavailable. Please try again."
            )
        
        # Step 4: Send verification link to user
        short_photo = client.messages.get("SHORT_PIC", "")
        short_caption = client.messages.get("SHORT_MSG", "")
        tutorial_link = getattr(client, 'tutorial_link', "https://t.me/How_to_Download_7x/26")
        
        await client.send_photo(
            chat_id=message.chat.id,
            photo=short_photo,
            caption=short_caption,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("• ᴏᴘᴇɴ ʟɪɴᴋ", url=verification_link),
                    InlineKeyboardButton("ᴛᴜᴛᴏʀɪᴀʟ •", url=tutorial_link)
                ],
                [
                    InlineKeyboardButton(" • ʙᴜʏ ᴘʀᴇᴍɪᴜᴍ •", url="https://t.me/Premium_Fliix/21")
                ]
            ])
        )
        return
        
    except Exception as e:
        print(f"Error in verification flow: {e}")
        return await message.reply("An error occurred. Please try again.")
```

---

## 🎯 Complete Flow Explanation

### What Happens:

```
1. User requests file
   ↓
2. Bot checks: Premium user?
   ├─ YES → Direct bot link (no verification)
   └─ NO  → Continue to step 3
   ↓
3. Bot creates bot link
   Example: https://t.me/YourBot?start=yu3elk...7
   ↓
4. Bot creates shortener link from bot link
   Example: https://linkshortify.com/abc123
   ↓
5. Bot calls Vercel API to create verification token
   POST https://your-project.vercel.app/api/create-token
   Body: {"user_id": "123", "shortener_link": "https://linkshortify.com/abc123"}
   ↓
6. Vercel creates token and stores in MongoDB
   Token: abc123def456...
   ↓
7. Vercel returns token to bot
   Response: {"success": true, "token": "abc123def456..."}
   ↓
8. Bot creates verification link
   Example: https://your-project.vercel.app/pre-verify/abc123def456...?uid=123
   ↓
9. Bot sends verification link to user
   User sees: "• ᴏᴘᴇɴ ʟɪɴᴋ" button
   ↓
10. User clicks verification link
    Opens: Vercel verification page
    ↓
11. User completes verification (10 seconds + math)
    ↓
12. Vercel redirects to shortener link
    Opens: https://linkshortify.com/abc123
    ↓
13. User completes shortener
    ↓
14. Shortener redirects to bot link
    Opens: https://t.me/YourBot?start=yu3elk...7
    ↓
15. Bot delivers files
    Success!
```

---

## 🧪 Testing

### Test 1: Check Environment Variable

```bash
echo $BOT_URL
# Should output: https://your-project.vercel.app
```

### Test 2: Test Helper Function

```bash
python3 << 'EOF'
from plugins.vercel_helper import create_verification_link

# Test
link = create_verification_link(
    user_id="123456789",
    shortener_link="https://example.com"
)

print(f"Verification link: {link}")
EOF
```

Expected output:
```
✅ Verification link created for user 123456789
Verification link: https://your-project.vercel.app/pre-verify/abc123...?uid=123456789
```

### Test 3: Test Complete Flow

1. Start bot: `python3 main.py`
2. Request file as non-premium user
3. Check bot sends verification link
4. Click verification link
5. Complete verification
6. Should redirect to shortener
7. Complete shortener
8. Should get files

---

## 🔍 Debugging

### Enable Debug Logging

Add to `plugins/vercel_helper.py`:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def create_verification_link(user_id, shortener_link):
    logger.debug(f"Creating verification link for user {user_id}")
    logger.debug(f"Shortener link: {shortener_link}")
    
    # ... rest of code ...
    
    logger.debug(f"Vercel response: {data}")
    return verification_link
```

### Check Logs

```bash
# Bot logs
tail -f bot.log

# Vercel logs
vercel logs --follow
```

### Common Issues

**Issue 1: "BOT_URL not set"**
```bash
# Solution:
export BOT_URL=https://your-project.vercel.app
```

**Issue 2: "Vercel API timeout"**
```bash
# Solution: Check Vercel is running
curl https://your-project.vercel.app
```

**Issue 3: "Token creation failed"**
```bash
# Solution: Check MongoDB connection
# In Vercel dashboard → Settings → Environment Variables
# Verify DB_URI is set correctly
```

**Issue 4: "Module not found: vercel_helper"**
```bash
# Solution: Check file exists
ls plugins/vercel_helper.py

# If not, create it again
```

---

## 📊 Monitoring

### Track Verification Success Rate

Add to `plugins/vercel_helper.py`:

```python
import time

verification_stats = {
    'total_requests': 0,
    'successful': 0,
    'failed': 0
}

def create_verification_link(user_id, shortener_link):
    verification_stats['total_requests'] += 1
    
    # ... existing code ...
    
    if verification_link:
        verification_stats['successful'] += 1
    else:
        verification_stats['failed'] += 1
    
    # Log stats every 100 requests
    if verification_stats['total_requests'] % 100 == 0:
        success_rate = (verification_stats['successful'] / verification_stats['total_requests']) * 100
        print(f"📊 Verification Stats: {success_rate:.1f}% success rate")
    
    return verification_link
```

---

## 🎨 Customization

### Change Verification Time

Edit `api/verify.py` on Vercel:
```python
# Line ~30
if interaction_time < 15:  # Change from 10 to 15 seconds
```

### Custom Error Messages

Edit `plugins/vercel_helper.py`:
```python
if not verification_link:
    return await message.reply(
        "🔐 Verification system is busy. Please try again in a moment."
    )
```

### Add Retry Logic

```python
def create_verification_link(user_id, shortener_link, max_retries=3):
    for attempt in range(max_retries):
        try:
            # ... existing code ...
            return verification_link
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)  # Wait 1 second before retry
                continue
            else:
                print(f"Failed after {max_retries} attempts")
                return None
```

---

## ✅ Checklist

- [ ] BOT_URL environment variable set
- [ ] requests library installed
- [ ] vercel_helper.py created
- [ ] start.py updated with new import
- [ ] start.py updated with verification flow
- [ ] Bot restarted
- [ ] Tested with non-premium user
- [ ] Verification page loads
- [ ] Redirects to shortener after verification
- [ ] Files delivered successfully

---

## 🚀 Go Live

```bash
# Final checks
echo $BOT_URL
python3 -c "from plugins.vercel_helper import create_verification_link; print('✅ Import successful')"

# Restart bot
systemctl restart filebot

# Monitor logs
tail -f bot.log
```

---

**Integration complete! Your bot now uses Vercel for pre-shortener verification!** 🎉
