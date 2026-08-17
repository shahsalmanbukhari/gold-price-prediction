#!/usr/bin/env python3
"""
Diagnostic script to test MetalpriceAPI connection
"""

import asyncio
import sys
import os
from pathlib import Path

# Add project to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

print("="*70)
print("METALPRICE API DIAGNOSTIC")
print("="*70)
print()

# Step 1: Check API key
api_key = os.getenv('METALPRICE_API_KEY')
if api_key:
    print(f"✅ API Key found: {api_key[:10]}...")
else:
    print("❌ API Key NOT found in .env")
    print()
    print("SOLUTION: Add to .env file:")
    print("  METALPRICE_API_KEY=your_api_key_here")
    sys.exit(1)

print()

# Step 2: Test direct API call
print("Testing direct API call...")
try:
    import requests
    import certifi

    url = "https://api.metalpriceapi.com/v1/latest"
    params = {
        'api_key': api_key,
        'base': 'XAU',
        'currencies': 'USD'
    }

    response = requests.get(url, params=params, timeout=10, verify=certifi.where())

    print(f"   Status Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"   Full Response:")
        import json
        print(json.dumps(data, indent=2))
        print()

        # Check success field
        if data.get('success') == False:
            print(f"❌ API returned success=false")
            error_info = data.get('error', {})
            print(f"   Error: {error_info}")
            print()
            print("SOLUTION: Your API key may be invalid, expired, or the free tier has limits.")
            print("   Get a new key from: https://metalpriceapi.com/")
            sys.exit(1)

        if 'rates' in data and 'USD' in data['rates']:
            price = 1 / data['rates']['USD']
            print(f"✅ Direct API call successful!")
            print(f"   XAU Price: ${price:.2f}")
        else:
            print(f"⚠️  Unexpected response format")
            print(f"   Expected 'rates.USD' but got: {list(data.keys())}")
    elif response.status_code == 401:
        print()
        print(f"❌ Authentication failed!")
        print(f"   Your API key may be invalid or expired")
        print(f"   Get a new key from: https://metalpriceapi.com/")
    else:
        print()
        print(f"❌ API request failed")
        print(f"   Response: {response.text[:200]}")

except Exception as e:
    print()
    print(f"❌ Connection error: {e}")
    import traceback
    traceback.print_exc()

print()
print("="*70)

# Step 3: Test provider
print("Testing MetalpriceProvider class...")
print()

try:
    from realtime.providers.metalprice_provider import MetalpriceProvider

    async def test_provider():
        provider = MetalpriceProvider()

        print(f"   Provider created: {provider.name}")

        # Connect
        await provider.connect()
        print(f"   Connected: {provider.is_connected}")

        # Health check
        health = await provider.health_check()
        print(f"   Health check: {health}")

        if health:
            # Get quote
            quote = await provider.get_quote('XAU')
            if quote:
                print(f"   ✅ Got quote: ${quote.price_usd:.2f}")
            else:
                print(f"   ❌ get_quote() returned None")

        await provider.disconnect()

    asyncio.run(test_provider())

except Exception as e:
    print(f"❌ Provider test failed: {e}")
    import traceback
    traceback.print_exc()

print()
print("="*70)
print("DIAGNOSTIC COMPLETE")
print("="*70)

