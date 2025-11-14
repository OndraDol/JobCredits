"""
teamio_bootstrap_login.py
--------------------------

This script launches a persistent Playwright browser context and lets the user
log in to Teamio manually.  The session (cookies, localStorage, etc.)
is stored in a directory called ``teamio_profile`` inside the project root.

Why a persistent context?
~~~~~~~~~~~~~~~~~~~~~~~~~

Teamio occasionally enforces two‑factor authentication (2FA) via e‑mail.  If we
used a fresh, stateless browser each time we scrape, you would be prompted to
enter a 2FA code on every run.  A persistent context stores the cookies and
session tokens issued during the login, so subsequent scrapes can reuse the
session without repeated 2FA challenges.

Usage:

1. Activate your virtual environment in a terminal, e.g.::

       cd C:\job_portal_credits
       .\.venv\Scripts\Activate.ps1

2. Run this script once to bootstrap your session::

       python teamio_bootstrap_login.py

   A Chromium window will open.  Navigate to your Teamio login page (for
   example, ``https://my.teamio.com`` or your company‑specific URL) and log
   in as you normally do.  Complete any 2FA e‑mail verification when asked.
   Once you reach the Teamio dashboard where your remaining credits are
   visible, return to the terminal and press Enter.  The script will shut
   down the browser, saving the session into ``teamio_profile``.  You should
   only need to repeat this step when Teamio logs you out or invalidates
   your session.

Notes:

* **Do not** hard‑code your credentials into this script.  All interaction
  happens in the browser window, just as if you were using Teamio normally.
* The persistent profile directory is stored next to this script.  If you
  wish to reset your session (for example, to log in as a different user),
  simply delete the ``teamio_profile`` folder and re‑run the bootstrap.

"""

import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright


async def bootstrap_login() -> None:
    """Launch a persistent browser context so the user can log in to Teamio.

    This coroutine opens a Chromium window with its user data stored in
    ``teamio_profile``.  The user should log in manually and press Enter
    in the terminal when finished.  The context is then closed and the
    session persists on disk for reuse by other scripts.
    """
    # Determine the absolute path to the profile directory.  It lives in the
    # same directory as this script.
    project_root = Path(__file__).resolve().parent
    user_data_dir = project_root / "teamio_profile"
    user_data_dir.mkdir(parents=True, exist_ok=True)

    # Launch Playwright and create a persistent context.
    async with async_playwright() as p:
        print("Launching Chromium with persistent profile at:", user_data_dir)
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
        )
        try:
            page = await browser.new_page()
            # You can change this URL to your Teamio login page.  It can be
            # company‑specific (e.g. https://my.teamio.com or https://<company>.teamio.com).
            start_url = os.environ.get("TEAMIO_LOGIN_URL", "https://my.teamio.com/recruit/dashboard")
            print(f"Opening {start_url}...")
            await page.goto(start_url)
            print(
                "\nA Chromium window has opened.  Please log in to Teamio manually, "
                "including any two‑factor authentication (2FA) steps.  \n"
                "Once you reach your Teamio dashboard, return here and press Enter to "
                "save the session.\n"
            )
            # Wait for the user to press Enter in the console.
            input("Press Enter here once you have completed the login and are on the dashboard...")
        finally:
            # Always close the browser to flush the profile to disk.
            await browser.close()
        print("Session saved.  You can now run check_credits.py without logging in again (until the session expires).")


def main() -> None:
    """Entry point for running the bootstrap via the command line."""
    asyncio.run(bootstrap_login())


if __name__ == "__main__":
    main()