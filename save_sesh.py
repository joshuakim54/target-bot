import asyncio
import os
from pathlib import Path
import platform
import subprocess
import time
from playwright.async_api import async_playwright

SESSION_FILE = Path(__file__).resolve().parent / "target_session.json"
CHROME_USER_DATA_DIR = Path(
    os.environ.get(
        "TARGET_CHROME_USER_DATA_DIR",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data",
    )
)
CHROME_PROFILE_DIRECTORY = os.environ.get("TARGET_CHROME_PROFILE", "Default")
CLOSE_CHROME_PROCESSES = True

def close_chrome_processes():
    """Close running Chrome processes before opening the selected profile."""
    if not CLOSE_CHROME_PROCESSES:
        return

    if platform.system() != "Windows":
        raise RuntimeError(
            "Automatic Chrome process cleanup is only supported on Windows."
        )

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Get-Process chrome -ErrorAction SilentlyContinue | "
                "ForEach-Object { Stop-Process -Id $_.Id -Force }"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or "PowerShell returned a failure status."
        raise RuntimeError(f"Could not close Chrome processes: {details}")
    time.sleep(1)

async def save_session():
    try:
        close_chrome_processes()
    except RuntimeError as error:
        print(f"\n{error}")
        return

    async with async_playwright() as p:
        # Reuse the selected real Chrome profile so its existing login can be used.
        print(f"Using Chrome data directory: {CHROME_USER_DATA_DIR}")
        print(f"Using Chrome profile: {CHROME_PROFILE_DIRECTORY}")
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(CHROME_USER_DATA_DIR),
                channel="chrome",
                headless=False,
                no_viewport=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                    f"--profile-directory={CHROME_PROFILE_DIRECTORY}",
                ],
            )
        except Exception as error:
            print("\nCould not open the selected Chrome profile.")
            print("Close every Chrome window and try again.")
            print(f"Chrome profile error: {error}")
            return

        page = await context.new_page()

        print("\nOpening Target Sign-In Page...")
        try:
            response = await page.goto(
                "https://www.target.com/account",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            print(f"Opened {page.url} (HTTP {response.status if response else 'unknown'})")
        except Exception as error:
            print(f"\nCould not open Target: {error}")
            print(f"Current browser URL: {page.url}")
            await context.close()
            return

        print("\n" + "=" * 60)
        print(
            ">>> ACTION REQUIRED: Log into Target in the browser window now! <<<"
        )
        print("The script will finish automatically after login is detected.")
        print("=" * 60 + "\n")

        try:
            await page.wait_for_function(
                """() => /sign out|log out/i.test(document.body.innerText)""",
                timeout=120000,
            )
            print("Login detected. Saving the session and closing the script...")
        except Exception:
            print("Login was not detected within 120 seconds. Saving the session anyway.")

        # Save storage state
        await context.storage_state(path=str(SESSION_FILE))
        print(f"\nSUCCESS: Session saved to {SESSION_FILE}!")
        await context.close()


if __name__ == "__main__":
    asyncio.run(save_session())
