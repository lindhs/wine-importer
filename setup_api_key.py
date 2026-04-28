#!/usr/bin/env python3
"""
Helper script to safely configure and verify OpenAI API key.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

def load_env():
    """Load .env file if it exists."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return False

    loaded = False
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        if key not in os.environ:
            os.environ[key] = value
            loaded = True

    return loaded

def check_api_key():
    """Check if API key is configured."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None, "Not set"
    if not api_key.startswith("sk-"):
        return None, "Invalid format (should start with 'sk-')"
    return api_key, "Valid"

def verify_openai_connection():
    """Test connection to OpenAI API."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return False, "✗ Connection failed: OPENAI_API_KEY is not configured"

    try:
        request = urllib.request.Request(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            json.loads(response.read().decode("utf-8"))
        return True, "✓ Connection successful"
    except Exception as e:
        if isinstance(e, urllib.error.HTTPError):
            body = e.read().decode("utf-8", errors="ignore")
            try:
                payload = json.loads(body)
                message = payload.get("error", {}).get("message", body)
            except json.JSONDecodeError:
                message = body or str(e)
            return False, f"✗ Connection failed: {message}"
        if isinstance(e, urllib.error.URLError):
            return False, f"✗ Connection failed: {e.reason}"
        return False, f"✗ Connection failed: {e}"

def main():
    print("=" * 70)
    print("Wine-Importer: OpenAI API Key Configuration")
    print("=" * 70)

    # Step 1: Load .env
    print("\n[Step 1] Loading .env file...")
    if load_env():
        print("✓ .env file loaded")
    else:
        print("ℹ No .env file found (will use shell environment)")

    # Step 2: Check API key
    print("\n[Step 2] Checking API key...")
    api_key, status = check_api_key()
    if api_key:
        print("✓ API key found")
        print(f"  Status: {status}")
    else:
        print(f"✗ API key not configured: {status}")
        print("\n  Quick fix:")
        print("  1. Copy template: cp .env.example .env")
        print("  2. Edit file:     nano .env")
        print("  3. Add your key:  OPENAI_API_KEY=sk-proj-...")
        print("\n  Or set in shell:")
        print("  export OPENAI_API_KEY='sk-proj-...'")
        return False

    # Step 3: Verify connection
    print("\n[Step 3] Testing OpenAI connection...")
    success, message = verify_openai_connection()
    print(f"  {message}")

    if not success:
        print("\n  Troubleshooting:")
        print("  - Verify API key is correct (try on platform.openai.com)")
        print("  - Check internet connection")
        print("  - Ensure key has sufficient credits")
        return False

    print("\n" + "=" * 70)
    print("✓ All checks passed! Ready to use --use-ai flag")
    print("=" * 70)
    print("\nQuick start:")
    print("  wine-importer run data.csv --canonical wines.csv \\")
    print("    --out-dir output/ --use-ai")
    print()
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
