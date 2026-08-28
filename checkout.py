import asyncio
import os
import platform
import random
import subprocess
import time
from pathlib import Path
from playwright.async_api import async_playwright

# --- CONFIGURATION ---
PRODUCT_URL = "https://www.target.com/p/-/A-1011960739"
ITEM_QUANTITY = 2                                           # Target quantity to purchase
CVV_CODE = "123"                                            # Replace with your card's 3/4-digit CVV
ARM_PLACE_ORDER = True                                     # Set to True to execute final purchase

POLL_INTERVAL_MIN = 3.0                                     # Min delay between stock checks (sec)
POLL_INTERVAL_MAX = 5.0                                     # Max delay (sec)
MAX_WAIT_MINUTES = 180                                      # Stops polling after 3 hours
SHUTDOWN_AFTER_TIMEOUT = True                               # Shut down macOS after the wait expires
MAX_ATTEMPTS = None                                         # Continue polling until the time limit or stock is found

BASE_DIR = Path(__file__).resolve().parent
SESSION_FILE = BASE_DIR / "target_session.json"

async def human_delay(min_sec=0.8, max_sec=1.8):
    """Adds randomized delays to mimic human reaction timing."""
    await asyncio.sleep(random.uniform(min_sec, max_sec))

def shutdown_computer():
    """Requests a shutdown on macOS or Windows."""
    operating_system = platform.system()

    if operating_system == "Darwin":
        print("Three-hour wait expired. Shutting down the Mac...")
        subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to shut down'],
            check=False,
        )
    elif operating_system == "Windows":
        print("Three-hour wait expired. Shutting down the PC...")
        subprocess.run(["shutdown", "/s", "/t", "0"], check=False)
    else:
        print(f"Shutdown is not configured for {operating_system}.")

async def run_full_auto_bot(product_url):
    async with async_playwright() as p:
        if not SESSION_FILE.exists():
            print(f"Error: {SESSION_FILE} not found. Please run your 1-time login script first!")
            return

        # Load the session saved by save_sesh.py instead of opening a separate profile.
        browser = await p.chromium.launch(
            channel="chrome",  # Uses actual Google Chrome to bypass Akamai bot detection
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized"
            ]
        )
        context = await browser.new_context(
            storage_state=str(SESSION_FILE),
            viewport=None,
        )
        
        page = context.pages[0] if context.pages else await context.new_page()

        print(f"[{time.strftime('%H:%M:%S')}] Navigating to product page with authenticated session...")
        await page.goto(product_url, wait_until="domcontentloaded")

        start_time = time.time()
        max_duration = MAX_WAIT_MINUTES * 60
        attempts = 0
        
        # Target button selectors
        cart_button_selector = '[data-test="shippingButton"], [data-test="addToCartButton"], button:has-text("Add to cart")'

        # --- STEP 1: POLLING LOOP ---
        in_stock = False
        while ((time.time() - start_time) < max_duration and
               (MAX_ATTEMPTS is None or attempts < MAX_ATTEMPTS)):
            attempts += 1
            print(f"[{time.strftime('%H:%M:%S')}] Polling stock... (Attempt #{attempts})")

            try:
                cart_button = page.locator(cart_button_selector).first
                if await cart_button.is_visible(timeout=2000) and await cart_button.is_enabled():
                    print(f"\nSUCCESS: Item detected IN STOCK at {time.strftime('%H:%M:%S')}\n")
                    in_stock = True
                    break
            except Exception:
                pass # Still out of stock

            await asyncio.sleep(random.uniform(POLL_INTERVAL_MIN, POLL_INTERVAL_MAX))
            try:
                await page.reload(wait_until="domcontentloaded")
            except Exception:
                print("Reload failed, retrying on next loop...")

        if not in_stock:
            print("Time limit reached. Stock drop did not occur. Exiting.")
            await context.close()
            await browser.close()
            if SHUTDOWN_AFTER_TIMEOUT:
                shutdown_computer()
            return

        # --- STEP 2: SET QUANTITY & ADD TO CART ---
        try:
            # Set Quantity to 2
            qty_selector = '[data-test="fulfillment-qty-select"], select[aria-label*="quantity"], select[id*="quantity"]'
            qty_element = page.locator(qty_selector).first

            if await qty_element.is_visible(timeout=3000):
                print(f"Action: Setting quantity to {ITEM_QUANTITY}...")
                
                # Check if element is a native HTML select dropdown
                tag_name = await qty_element.evaluate("el => el.tagName.toLowerCase()")
                if tag_name == "select":
                    await qty_element.select_option(str(ITEM_QUANTITY))
                else:
                    # Target custom UI dropdown handling
                    await qty_element.click()
                    await human_delay(0.3, 0.6)
                    option = page.locator(f'option[value="{ITEM_QUANTITY}"], li:has-text("{ITEM_QUANTITY}")').first
                    await option.click()
                    
                await human_delay(0.5, 1.0)
            else:
                print(f"Quantity dropdown not found. Defaulting to standard stock quantity.")

            # Click Add to Cart
            cart_button = page.locator(cart_button_selector).first
            await cart_button.click()
            print(f"Action: Clicked 'Add to Cart' (Qty: {ITEM_QUANTITY})")
            await human_delay(1.0, 1.5)

            # Route to Cart Page
            cart_modal_selector = '[data-test="content-cell-view-cart-checkout"], a:has-text("View cart & checkout")'
            try:
                view_cart_btn = page.locator(cart_modal_selector).first
                await view_cart_btn.wait_for(state="visible", timeout=5000)
                await view_cart_btn.click()
            except Exception:
                print("Modal bypassed, jumping directly to /cart...")
                await page.goto("https://www.target.com/cart")

            await human_delay(1.0, 1.5)

            # --- STEP 3: NAVIGATE TO CHECKOUT ---
            checkout_selector = '[data-test="checkout-button"], button:has-text("Ready to checkout")'
            checkout_btn = page.locator(checkout_selector).first
            await checkout_btn.wait_for(state="visible", timeout=7000)
            await checkout_btn.click()
            print("Action: Navigating through Checkout screen...")
            await human_delay(1.5, 2.5)

            # --- STEP 4: AUTOMATED PAYMENT & CVV INJECTION ---
            print("Action: Checking for CVV security confirmation...")
            
            try:
                cvv_input = page.frame_locator('iframe[title*="credit card"], iframe[title*="payment"]').locator('input[id*="cvv"], input[name*="cvv"]')
                
                if not await cvv_input.is_visible(timeout=3000):
                    cvv_input = page.locator('input[name="cvvValue"], input[id*="cvv"], input[aria-label*="CVV"]').first

                if await cvv_input.is_visible(timeout=3000):
                    print("CVV prompt found. Typing CVV code...")
                    await cvv_input.fill(CVV_CODE)
                    await human_delay(0.5, 1.0)
                else:
                    print("No explicit CVV prompt required. Proceeding with saved default card.")
            except Exception:
                print("Skipping CVV step, attempting to proceed...")

            # --- STEP 5: PLACE ORDER ---
            place_order_selector = '[data-test="placeOrderButton"], button:has-text("Place your order")'
            place_order_btn = page.locator(place_order_selector).first
            await place_order_btn.wait_for(state="visible", timeout=10000)

            if ARM_PLACE_ORDER:
                print("Placing order now...")
                await place_order_btn.click()
                print("Order successfully submitted!")
                await human_delay(3.0, 5.0)
            else:
                print("[SAFETY MODE]: Reached 'Place Order' stage. Set ARM_PLACE_ORDER = True to complete purchases.")

        except Exception as e:
            print(f"Checkout failed or hit a roadblock: {e}. Aborting mission.")

        # Cleanly shut down browser and finish script
        await context.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_full_auto_bot(PRODUCT_URL))
