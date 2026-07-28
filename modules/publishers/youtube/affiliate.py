import time
import logging
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

def tag_products(page: Page, product_recommendations: list[dict]):
    """
    Automate the YouTube Shopping 'Tag products' feature inside the Video Elements tab.
    """
    if not product_recommendations:
        return
        
    try:
        # First, we need to get to the Video elements tab.
        # Typically, YouTube upload flow is: Details -> Video elements
        # If we are on Details, we click next.
        next_selectors = [
            '#next-button',
            'ytcp-button[id="next-button"]',
            'ytcp-button:has-text("NEXT")',
            'button:has-text("Next")'
        ]
        
        # Click next to go to Video Elements
        next_clicked = False
        for sel in next_selectors:
            if page.locator(sel).first.is_visible():
                page.locator(sel).first.click()
                next_clicked = True
                time.sleep(2)
                break
                
        if not next_clicked:
            logger.warning("[YouTube Affiliate] Could not find Next button to reach Video Elements tab.")
            return

        # Check if "Tag products" is available
        tag_button_sel = 'ytcp-button:has-text("Add")'
        # We need a more robust way to find the "Add" button specifically for "Tag products".
        # It's usually in a row containing the text "Tag products".
        tag_row = page.locator('div').filter(has_text="Tag products").last
        if not tag_row.is_visible(timeout=5000):
            logger.info("[YouTube Affiliate] 'Tag products' option not available (channel might not be eligible). Skipping.")
            return
            
        add_btn = tag_row.locator('ytcp-button').filter(has_text="Add").first
        if not add_btn.is_visible():
            logger.info("[YouTube Affiliate] 'Add' button for 'Tag products' not visible. Skipping.")
            return
            
        add_btn.click()
        time.sleep(2)
        
        # Now the Tag products modal is open
        # Let's search for the first product
        prod = product_recommendations[0]
        search_query = prod.get("search_query", prod.get("product_name"))
        
        search_input = page.locator('input[placeholder*="Search"]').first
        if not search_input.is_visible():
            search_input = page.locator('input').filter(has_text="Search").first
            
        if search_input.is_visible():
            search_input.fill(search_query)
            search_input.press("Enter")
            time.sleep(4) # Wait for results
            
            # Click the first product's add button (usually a + icon or text 'Drag to add')
            # Look for an add/plus button within the search results list
            add_product_btn = page.locator('ytcp-button[icon="add"]').first
            if not add_product_btn.is_visible():
                add_product_btn = page.locator('button[aria-label*="Add"]').first
                
            if add_product_btn.is_visible():
                add_product_btn.click()
                time.sleep(1)
                logger.info(f"[YouTube Affiliate] Successfully tagged product: {search_query}")
            else:
                logger.warning(f"[YouTube Affiliate] Could not find the + button to add the product from search results.")
                
        else:
            logger.warning("[YouTube Affiliate] Could not find the product search input in the modal.")
            
        # Click Save/Done in the modal
        save_btn = page.locator('ytcp-button[id="save-button"]').first
        if not save_btn.is_visible():
            save_btn = page.locator('ytcp-button:has-text("SAVE")').first
            
        if save_btn.is_visible():
            save_btn.click()
            time.sleep(2)
            
    except Exception as e:
        logger.error(f"[YouTube Affiliate] Error during product tagging flow: {e}")
