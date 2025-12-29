#!/usr/bin/env python3
"""
Automate login to hallinta.lahella.fi and update auth.toml with fresh cookies.

Usage:
    python login.py
"""

import re
import sys
import time
from pathlib import Path

import tomllib
from playwright.sync_api import sync_playwright


AUTH_FILE = Path(__file__).parent / "auth.toml"
LOGIN_URL = "https://hallinta.lahella.fi/login"


def load_credentials() -> tuple[str, str]:
    """Load email and password from auth.toml."""
    with open(AUTH_FILE, "rb") as f:
        config = tomllib.load(f)
    auth = config.get("auth", {})
    email = auth.get("email")
    password = auth.get("password")
    if not email or not password:
        print("Error: email and password must be set in auth.toml")
        sys.exit(1)
    return email, password


def update_cookies(cookies: str) -> None:
    """Update the cookies line in auth.toml."""
    content = AUTH_FILE.read_text()

    # Replace the cookies line
    new_content = re.sub(
        r'^cookies = ".*"$',
        f'cookies = "{cookies}"',
        content,
        flags=re.MULTILINE
    )

    AUTH_FILE.write_text(new_content)
    print(f"Updated {AUTH_FILE}")


def login() -> None:
    """Perform login and extract cookies."""
    email, password = load_credentials()

    print(f"Logging in as {email}...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Go to login page
        page.goto(LOGIN_URL)
        page.wait_for_load_state("networkidle")

        # Fill in credentials
        page.fill('input[name="username"]', email)
        page.fill('input[name="password"]', password)

        # Click login button (the one with "Kirjaudu sisään" text)
        page.click('button[type="submit"]:has-text("Kirjaudu")')

        # Wait for redirect after successful login (goes to home page)
        try:
            page.wait_for_url(lambda url: "login" not in url, timeout=30000)
            print("Login successful!")
        except Exception:
            print("Login failed - check credentials or CAPTCHA might have triggered")
            browser.close()
            sys.exit(1)

        # Give the app a moment to store tokens
        time.sleep(1)

        # Extract cookies from local storage (they store tokens there)
        cookies = context.cookies()

        # Build cookie string from relevant auth cookies
        cookie_parts = []
        for cookie in cookies:
            if "AUTH_TOKEN" in cookie["name"] or "REFRESH_TOKEN" in cookie["name"] or "EXP_" in cookie["name"]:
                cookie_parts.append(f"{cookie['name']}={cookie['value']}")

        if not cookie_parts:
            # Try localStorage instead
            storage = page.evaluate("() => Object.entries(localStorage)")
            for key, value in storage:
                if "AUTH_TOKEN" in key or "REFRESH_TOKEN" in key or "EXP_" in key:
                    cookie_parts.append(f"{key}={value}")

        browser.close()

        if cookie_parts:
            cookie_str = ";".join(cookie_parts)
            update_cookies(cookie_str)
            print("Cookies extracted and saved!")
        else:
            print("Warning: No auth cookies found. Login may have failed.")
            sys.exit(1)


if __name__ == "__main__":
    login()
