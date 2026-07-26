import os

api_key = os.getenv('COINBASE_API_KEY', '')
api_secret = os.getenv('COINBASE_API_SECRET', '')

print("=" * 80)
print("RAILWAY CREDENTIAL DEBUG")
print("=" * 80)
print(f"API_KEY length: {len(api_key)}")
print(f"API_KEY starts: {api_key[:30]}")
print(f"API_KEY ends: {api_key[-20:]}")
print(f"API_SECRET length: {len(api_secret)}")
print(f"API_SECRET starts: {api_secret[:15]}")
print(f"API_SECRET ends: {api_secret[-15:]}")
print(f"Has whitespace in key (leading/trailing): {api_key != api_key.strip()}")
print(f"Has whitespace in secret (leading/trailing): {api_secret != api_secret.strip()}")
print("=" * 80)

# Reference values from your known-working local .env
expected_key_len = 98
expected_secret_len = 88

print(f"\nExpected API_KEY length: {expected_key_len} -> Match: {len(api_key) == expected_key_len}")
print(f"Expected API_SECRET length: {expected_secret_len} -> Match: {len(api_secret) == expected_secret_len}")
print("=" * 80)
