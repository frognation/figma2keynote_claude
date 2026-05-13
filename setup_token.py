#!/usr/bin/env python3
"""
Set up the Figma access token for figma2keynote_claude.

Usage:
    python setup_token.py figd_xxxxxxxxx
    OR
    FIGMA_ACCESS_TOKEN=figd_xxx python setup_token.py
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from figma_extractor.api_client import FigmaClient


def main():
    # Get token from arg or env
    if len(sys.argv) > 1:
        token = sys.argv[1].strip()
    else:
        token = os.environ.get("FIGMA_ACCESS_TOKEN", "").strip()
        if not token:
            print("Usage: python setup_token.py <token>")
            print("       OR: FIGMA_ACCESS_TOKEN=figd_xxx python setup_token.py")
            return 1

    if not token.startswith("figd_"):
        print("Warning: Token doesn't start with 'figd_'. Continuing anyway...")

    print(f"Verifying token...")
    try:
        user = FigmaClient.verify_token(token)
        print(f"  ✓ Token valid")
        print(f"    User: {user.get('email', 'unknown')}")
        print(f"    Handle: @{user.get('handle', 'unknown')}")
    except Exception as e:
        print(f"  ✗ Token verification failed: {e}")
        return 1

    config_path = FigmaClient.save_token(token)
    print(f"\nToken saved to {config_path} (chmod 600)")
    print("\nYou can now run:")
    print("  python main.py export --file-key <KEY> --output out.pptx")
    return 0


if __name__ == "__main__":
    sys.exit(main())
