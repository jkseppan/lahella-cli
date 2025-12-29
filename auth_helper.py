#!/usr/bin/env python3
"""
Shared authentication helper for lahella.fi automation.

Handles token refresh and session management.
"""

import re
import sys
import time
from pathlib import Path

import httpx
import tomllib


AUTH_FILE = Path(__file__).parent / "auth.toml"
BASE_URL = "https://hallinta.lahella.fi"


def load_auth_config() -> dict:
    """Load auth configuration from auth.toml."""
    if not AUTH_FILE.exists():
        print(f"Error: {AUTH_FILE} not found")
        sys.exit(1)

    with open(AUTH_FILE, "rb") as f:
        config = tomllib.load(f)

    auth = config.get("auth", {})
    if not auth.get("cookies"):
        print("Error: No cookies found in auth.toml")
        print("Run login.py first to authenticate.")
        sys.exit(1)

    return auth


def parse_cookies(cookie_string: str) -> dict:
    """Parse cookie string into dict."""
    cookies = {}
    if cookie_string:
        for item in cookie_string.split(";"):
            item = item.strip()
            if "=" in item:
                key, value = item.split("=", 1)
                cookies[key.strip()] = value.strip()
    return cookies


def cookies_to_string(cookies: dict) -> str:
    """Convert cookies dict back to string format."""
    return ";".join(f"{k}={v}" for k, v in cookies.items())


def update_cookies_in_file(cookies: dict) -> None:
    """Update the cookies line in auth.toml."""
    cookie_str = cookies_to_string(cookies)
    content = AUTH_FILE.read_text()

    new_content = re.sub(
        r'^cookies = ".*"$',
        f'cookies = "{cookie_str}"',
        content,
        flags=re.MULTILINE
    )

    AUTH_FILE.write_text(new_content)
    print("Updated cookies in auth.toml")


def try_refresh_token(session: httpx.Client) -> bool:
    """
    Attempt to refresh the auth token using the refresh token.
    Returns True if successful, False otherwise.
    """
    url = f"{BASE_URL}/api/v1/auth/token"

    try:
        response = session.post(
            url,
            json={"grant_type": "refresh_token"},
            headers={
                "Content-Type": "application/json",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/login",
            }
        )

        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "Success":
                print("Token refreshed successfully")

                # Extract updated cookies from session
                updated_cookies = {}
                for cookie in session.cookies.jar:
                    if any(x in cookie.name for x in ["AUTH_TOKEN", "REFRESH_TOKEN", "EXP_"]):
                        updated_cookies[cookie.name] = cookie.value

                # Save to file if we got new cookies
                if updated_cookies:
                    update_cookies_in_file(updated_cookies)

                return True

        print(f"Token refresh failed: {response.status_code}")
        return False

    except Exception as e:
        print(f"Error refreshing token: {e}")
        return False


def get_authenticated_session(auto_refresh: bool = True) -> httpx.Client:
    """
    Get an authenticated httpx.Client session.

    Args:
        auto_refresh: If True, will attempt to refresh token if auth fails

    Returns:
        Authenticated httpx.Client session
    """
    auth_config = load_auth_config()
    cookies = parse_cookies(auth_config["cookies"])

    session = httpx.Client(timeout=60.0)
    session.cookies.update(cookies)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Origin": BASE_URL,
    })

    # Test authentication by checking a protected endpoint
    if auto_refresh:
        test_url = f"{BASE_URL}/v1/activities"
        try:
            response = session.get(test_url, params={"limit": 1})

            if response.status_code == 401:
                print("Auth token expired, attempting refresh...")
                if try_refresh_token(session):
                    # Reload cookies after refresh
                    auth_config = load_auth_config()
                    cookies = parse_cookies(auth_config["cookies"])
                    session.cookies.clear()
                    session.cookies.update(cookies)
                else:
                    print("Token refresh failed. Please run login.py to re-authenticate.")
                    sys.exit(1)
        except Exception as e:
            print(f"Warning: Could not test authentication: {e}")

    return session


if __name__ == "__main__":
    # Test the auth helper
    print("Testing authentication...")
    session = get_authenticated_session()

    # Try a simple API call
    response = session.get(f"{BASE_URL}/v1/activities", params={"limit": 1})
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        print("Authentication successful!")
    else:
        print("Authentication failed!")
        sys.exit(1)
