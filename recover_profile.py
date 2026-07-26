import sys
import shutil
from playwright.sync_api import sync_playwright
from modules.publishers.youtube.publisher import PROFILE_DIR, get_channel_profile_dir, extract_channel_info_from_page, _launch_persistent_context
import time

def recover_profile():
    if not PROFILE_DIR.exists():
        print("No PROFILE_DIR found.")
        return

    with sync_playwright() as playwright:
        print("Launching browser with PROFILE_DIR...")
        context, proc = _launch_persistent_context(
            playwright=playwright,
            user_data_dir=str(PROFILE_DIR),
            headless=True,
            viewport={"width": 1280, "height": 800},
            cdp_port=None
        )
        page = context.pages[0] if context.pages else context.new_page()
        
        page.goto("https://studio.youtube.com/")
        print("Waiting to see if logged in...")
        time.sleep(5)
        
        name, handle, channel_id = extract_channel_info_from_page(page)
        
        context.close()
        if proc and proc.poll() is None:
            proc.terminate()
            proc.wait(3)
            
        if channel_id:
            print(f"Extracted channel_id: {channel_id}")
            target_dir = get_channel_profile_dir(channel_id)
            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
            shutil.copytree(PROFILE_DIR, target_dir)
            print(f"Copied PROFILE_DIR to {target_dir}")
        else:
            print("Failed to extract channel_id. Maybe not logged in?")

if __name__ == "__main__":
    recover_profile()
