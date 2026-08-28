import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SESSION_FILE = Path(__file__).resolve().parent / "target_session.json"

async def save_session():
    async with async_playwright() as p:
        # Launch real installed Google Chrome with a persistent user data directory
        context = await p.chromium.launch_persistent_context(
            user_data_dir="./chrome_user_data",  # Separate directory for Chrome context
            channel="chrome",  # Uses real installed Google Chrome
            headless=False,
            no_viewport=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
        )

        page = context.pages[0] if context.pages else await context.new_page()

        print("\nOpening Target Sign-In Page...")
        await page.goto(
            "https://www.target.com/account", wait_until="domcontentloaded"
        )

        print("\n" + "=" * 60)
        print(
            ">>> ACTION REQUIRED: Log into Target in the browser window now! <<<"
        )
        print("You have 120 seconds to sign in and handle any 2FA codes.")
        print("=" * 60 + "\n")

        await asyncio.sleep(120)

        # Save storage state
        await context.storage_state(path=str(SESSION_FILE))
        print(f"\nSUCCESS: Session saved to {SESSION_FILE}!")
        await context.close()


if __name__ == "__main__":
    asyncio.run(save_session())
