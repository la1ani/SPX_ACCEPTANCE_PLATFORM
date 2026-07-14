"""
Run this ONCE, manually, to log into TradingView and save the session.
After this, run_live.py reuses the saved session automatically — you don't
need to log in again unless the session expires.

This opens a real (non-headless) browser window so you can log in by hand
(including any 2FA), then saves the session to disk.

Run: python save_tradingview_session.py
"""

from playwright.sync_api import sync_playwright

OUTPUT_PATH = "tradingview_session.json"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.tradingview.com/#signin")

        print("A browser window has opened.")
        print("Log into TradingView normally in that window.")
        input("Once you're logged in and can see your charts, press Enter here to save the session...")

        context.storage_state(path=OUTPUT_PATH)
        print(f"Session saved to {OUTPUT_PATH}. You can close the browser window now.")
        browser.close()


if __name__ == "__main__":
    main()
