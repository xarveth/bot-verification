"""
Vercel Verification Helper
--------------------------
Helper function to create verification links via Vercel API.

Usage:
    from plugins.vercel_helper import create_verification_link
    
    verification_link = create_verification_link(
        user_id=123456789,
        shortener_link="https://linkshortify.com/abc123"
    )
"""

import requests
import os
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_verification_link(user_id, shortener_link):
    """
    Create verification link via Vercel API
    
    Args:
        user_id (int/str): Telegram user ID
        shortener_link (str): Already shortened URL
    
    Returns:
        str: Verification link or None if failed
    
    Example:
        >>> link = create_verification_link(123456789, "https://short.link/abc")
        >>> print(link)
        https://your-project.vercel.app/pre-verify/token123?uid=123456789
    """
    
    # Get Vercel URL from environment
    vercel_url = os.getenv('BOT_URL', '')
    
    if not vercel_url:
        logger.error("❌ BOT_URL environment variable not set!")
        logger.error("Set it with: export BOT_URL=https://your-project.vercel.app")
        return None
    
    # Remove trailing slash
    vercel_url = vercel_url.rstrip('/')
    
    try:
        logger.info(f"Creating verification link for user {user_id}")
        
        # Call Vercel API to create token
        response = requests.post(
            f"{vercel_url}/api/create-token",
            json={
                'user_id': str(user_id),
                'shortener_link': shortener_link
            },
            timeout=10,
            headers={'Content-Type': 'application/json'}
        )
        
        # Check HTTP status
        if response.status_code != 200:
            logger.error(f"❌ Vercel API returned status {response.status_code}")
            logger.error(f"Response: {response.text}")
            return None
        
        # Parse JSON response
        data = response.json()
        
        # Check if successful
        if data.get('success'):
            token = data['token']
            verification_link = f"{vercel_url}/pre-verify/{token}?uid={user_id}"
            logger.info(f"✅ Verification link created successfully")
            return verification_link
        else:
            error_msg = data.get('message', 'Unknown error')
            logger.error(f"❌ Token creation failed: {error_msg}")
            return None
    
    except requests.exceptions.Timeout:
        logger.error("❌ Vercel API request timed out (>10 seconds)")
        logger.error("Check if Vercel is running: curl " + vercel_url)
        return None
    
    except requests.exceptions.ConnectionError:
        logger.error("❌ Could not connect to Vercel")
        logger.error("Check BOT_URL is correct: " + vercel_url)
        return None
    
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Network error: {e}")
        return None
    
    except ValueError as e:
        logger.error(f"❌ Invalid JSON response: {e}")
        return None
    
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return None


def test_connection():
    """
    Test connection to Vercel API
    
    Returns:
        bool: True if connection successful
    """
    vercel_url = os.getenv('BOT_URL', '')
    
    if not vercel_url:
        print("❌ BOT_URL not set")
        return False
    
    try:
        response = requests.get(vercel_url, timeout=5)
        if response.status_code == 200:
            print(f"✅ Vercel is reachable: {vercel_url}")
            return True
        else:
            print(f"⚠️ Vercel returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot reach Vercel: {e}")
        return False


# Test if run directly
if __name__ == "__main__":
    print("🧪 Testing Vercel Helper...")
    print()
    
    # Test 1: Check environment
    print("Test 1: Environment Variable")
    bot_url = os.getenv('BOT_URL', '')
    if bot_url:
        print(f"✅ BOT_URL is set: {bot_url}")
    else:
        print("❌ BOT_URL is not set")
        print("Set it with: export BOT_URL=https://your-project.vercel.app")
        exit(1)
    
    print()
    
    # Test 2: Connection
    print("Test 2: Connection to Vercel")
    if test_connection():
        print("✅ Connection successful")
    else:
        print("❌ Connection failed")
        exit(1)
    
    print()
    
    # Test 3: Create token
    print("Test 3: Create Verification Link")
    test_link = create_verification_link(
        user_id="123456789",
        shortener_link="https://example.com/test"
    )
    
    if test_link:
        print(f"✅ Verification link created:")
        print(f"   {test_link}")
    else:
        print("❌ Failed to create verification link")
        exit(1)
    
    print()
    print("🎉 All tests passed!")
