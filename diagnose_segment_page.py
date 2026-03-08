"""
Diagnose Segment Page
Check what's actually on the Zerodha segment page
"""
from segment_automation import ZerodhaSegmentAutomation
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def diagnose():
    """Diagnose the segment page"""
    print("=" * 60)
    print("SEGMENT PAGE DIAGNOSTIC")
    print("=" * 60)
    print()
    print("This will:")
    print("  1. Login to Zerodha")
    print("  2. Navigate to segment page")
    print("  3. Show what elements are on the page")
    print("  4. Take screenshots")
    print()
    print("Browser will be VISIBLE so you can see what's happening")
    print("=" * 60)
    print()
    
    input("Press Enter to continue...")
    
    automation = ZerodhaSegmentAutomation(headless=False)  # Visible browser
    
    try:
        # Step 1: Login
        print("\n1. Logging in with Selenium...")
        if not automation.login_to_zerodha_selenium():
            print("❌ Login failed")
            return
        
        print("✅ Login successful")
        
        # Step 2: Navigate to segment page
        print("\n2. Navigating to segment page...")
        automation.driver.get("https://console.zerodha.com/account/segment-activation")
        time.sleep(5)
        
        # Check current URL
        current_url = automation.driver.current_url
        print(f"   Current URL: {current_url}")
        
        if "login" in current_url.lower():
            print("   ⚠️  Redirected to login page - session not working!")
        else:
            print("   ✅ On segment page")
        
        # Step 3: Take screenshot
        print("\n3. Taking screenshot...")
        automation.take_screenshot("diagnose_segment_page.png")
        print("   ✅ Screenshot saved: diagnose_segment_page.png")
        
        # Step 4: Check for checkboxes
        print("\n4. Looking for checkboxes...")
        
        from selenium.webdriver.common.by import By
        
        # Try to find specific IDs
        ids_to_check = ['NSE_EQ', 'BSE_EQ', 'NSE_FO', 'BSE_FO']
        
        for checkbox_id in ids_to_check:
            try:
                element = automation.driver.find_element(By.ID, checkbox_id)
                is_checked = element.is_selected()
                print(f"   ✅ Found {checkbox_id}: {'Checked' if is_checked else 'Unchecked'}")
            except:
                print(f"   ❌ NOT FOUND: {checkbox_id}")
        
        # Find all checkboxes
        print("\n5. Finding all checkboxes on page...")
        try:
            all_checkboxes = automation.driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
            print(f"   Found {len(all_checkboxes)} checkbox(es)")
            
            for i, cb in enumerate(all_checkboxes[:10], 1):  # Show first 10
                cb_id = cb.get_attribute('id')
                cb_name = cb.get_attribute('name')
                cb_class = cb.get_attribute('class')
                is_checked = cb.is_selected()
                
                print(f"   {i}. ID: '{cb_id}', Name: '{cb_name}', Class: '{cb_class}', Checked: {is_checked}")
        except Exception as e:
            print(f"   ❌ Error finding checkboxes: {e}")
        
        # Find all inputs
        print("\n6. Finding all input elements...")
        try:
            all_inputs = automation.driver.find_elements(By.TAG_NAME, "input")
            print(f"   Found {len(all_inputs)} input element(s)")
            
            for i, inp in enumerate(all_inputs[:10], 1):  # Show first 10
                inp_type = inp.get_attribute('type')
                inp_id = inp.get_attribute('id')
                inp_name = inp.get_attribute('name')
                
                print(f"   {i}. Type: '{inp_type}', ID: '{inp_id}', Name: '{inp_name}'")
        except Exception as e:
            print(f"   ❌ Error finding inputs: {e}")
        
        # Save page source
        print("\n7. Saving page source...")
        try:
            with open("diagnose_page_source.html", "w", encoding="utf-8") as f:
                f.write(automation.driver.page_source)
            print("   ✅ Page source saved: diagnose_page_source.html")
        except Exception as e:
            print(f"   ❌ Error saving page source: {e}")
        
        # Check page title
        print("\n8. Page information...")
        print(f"   Title: {automation.driver.title}")
        print(f"   URL: {automation.driver.current_url}")
        
        print("\n" + "=" * 60)
        print("DIAGNOSTIC COMPLETE")
        print("=" * 60)
        print()
        print("Files created:")
        print("  - diagnose_segment_page.png (screenshot)")
        print("  - diagnose_page_source.html (HTML source)")
        print()
        print("Next steps:")
        print("  1. Check the screenshot to see what's on the page")
        print("  2. Check the HTML source to find the correct element IDs")
        print("  3. If checkboxes are found, note their IDs")
        print("  4. Update segment_automation.py with correct IDs")
        print()
        
        input("\nPress Enter to close browser...")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        automation.close()

if __name__ == "__main__":
    diagnose()
