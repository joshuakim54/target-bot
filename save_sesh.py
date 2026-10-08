import asyncio
import os
import platform
import subprocess
from pathlib import Path
from playwright.async_api import async_playwright

SESSION_FILE = Path(__file__).resolve().parent / "target_session.json"
CHROME_USER_DATA_DIR = Path(
    os.environ.get(
        "TARGET_CHROME_USER_DATA_DIR",
        Path(__file__).resolve().parent / "chrome_user_data",
    )
)
CHROME_PROFILE_DIRECTORY = os.environ.get("TARGET_CHROME_PROFILE", "Default")
CHROME_EXTENSIONS_DIRECTORY = Path(
    os.environ.get(
        "TARGET_CHROME_EXTENSIONS_DIR",
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Google"
        / "Chrome"
        / "User Data"
        / CHROME_PROFILE_DIRECTORY
        / "Extensions",
    )
)

def close_chrome_instances():
    """Close all running Chrome processes before opening the selected profile."""
    if platform.system() != "Windows":
        return

    subprocess.run(
        ["taskkill", "/F", "/IM", "chrome.exe", "/T"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

def installed_extension_paths():
    if not CHROME_EXTENSIONS_DIRECTORY.is_dir():
        return []

    return [
        extension_version
        for extension_version in CHROME_EXTENSIONS_DIRECTORY.glob("*/*")
        if (extension_version / "manifest.json").is_file()
    ]

async def save_session():
    async with async_playwright() as p:
        # Reuse the selected real Chrome profile so its existing login can be used.
        print(f"Using Chrome data directory: {CHROME_USER_DATA_DIR}")
        print(f"Using Chrome profile: {CHROME_PROFILE_DIRECTORY}")
        close_chrome_instances()
        extension_paths = installed_extension_paths()
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
                    *(
                        [
                            "--load-extension="
                            + ",".join(str(path) for path in extension_paths)
                        ]
                        if extension_paths
                        else []
                    ),
                ],
            )
        except Exception as error:
            print("\nCould not open the selected Chrome profile.")
            print("Close every Chrome window and try again.")
            print(f"Chrome profile error: {error}")
            return

        page = context.pages[0] if context.pages else await context.new_page()

        print("\nOpening Target Sign-In Page...")
        await page.goto(
            "https://www.target.com/account", wait_until="domcontentloaded"
        )

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
