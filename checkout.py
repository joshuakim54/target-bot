import asyncio
import os
import random
import time
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# --- CONFIGURATION ---
PRODUCT_URL = "https://www.target.com/p/example-product-id" # Replace with your product URL
CVV_CODE = "123"                                           # Replace with your card's 3/4-digit CVV
ARM_PLACE_ORDER = False                                     # Set to True to execute final purchase

POLL_INTERVAL_MIN = 3.0                                    # Min delay between stock checks (sec)
POLL_INTERVAL_MAX = 5.0                                    # Max delay (sec)
MAX_WAIT_MINUTES = 180                                     # Stops polling after 3 hours (e.g. 3 AM to 6 AM)

async def human_delay(min_sec=0.8, max_sec=1.8):
    """Adds randomized delays to mimic human reaction timing."""
    await asyncio.sleep(random.uniform(min_sec, max_sec))

async def run_full_auto_bot(product_url):
    async with async_playwright() as p:
        session_file = "target_session.json"
        if not os.path.exists(session_file):
            print(f"Error: {session_file} not found. Please run your 1-time login script first!")
            return

        # Launch browser with saved session state
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            storage_state=session_file,
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        page = await context.new_page()
        await stealth_async(page)

        print(f"[{time.strftime('%H:%M:%S')}] Navigating to product page with authenticated session...")
        await page.goto(product_url, wait_until="domcontentloaded")

        start_time = time.time()
        max_duration = MAX_WAIT_MINUTES * 60
        attempts = 0
        
        # Target button selectors
        cart_button_selector = '[data-test="shippingButton"], [data-test="addToCartButton"], button:has-text("Add to cart")'

        # --- STEP 1: POLLING LOOP ---
        in_stock = False
        while (time.time() - start_time) < max_duration:
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
            await browser.close()
            return

        # --- STEP 2: ADD TO CART ---
        try:
            cart_button = page.locator(cart_button_selector).first
            await cart_button.click()
            print("Action: Clicked 'Add to Cart'")
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
                # 1. Check inside credit card iframe
                cvv_input = page.frame_locator('iframe[title*="credit card"], iframe[title*="payment"]').locator('input[id*="cvv"], input[name*="cvv"]')
                
                # 2. Fallback check for root DOM CVV field
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
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_full_auto_bot(PRODUCT_URL))
