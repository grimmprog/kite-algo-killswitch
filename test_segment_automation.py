"""
Test Segment Automation
Quick test to verify segment automation is working
"""
from segment_automation import ZerodhaSegmentAutomation
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_login_and_page_load():
    """Test 1: Login and load segment page"""
    print("=" * 60)
    print("TEST 1: Login and Page Load")
    print("=" * 60)
    
    automation = ZerodhaSegmentAutomation(headless=False)  # Visible browser for testing
    
    try:
        # Test login
        print("\n1. Testing login...")
        session = automation.login_to_zerodha()
        
        if not session:
            print("❌ Login failed")
            return False
        
        print("✅ Login successful")
        
        # Setup browser
        print("\n2. Setting up browser...")
        automation.setup_driver()
        automation.driver.get("https://console.zerodha.com")
        
        # Transfer cookies
        print("3. Transferring session...")
        for cookie in session.cookies:
            cookie_dict = {
                'name': cookie.name,
                'value': cookie.value,
                'domain': cookie.domain,
                'path': cookie.path,
            }
            try:
                automation.driver.add_cookie(cookie_dict)
            except:
                pass
        
        # Navigate to segment page
        print("\n4. Loading segment page...")
        if not automation.navigate_to_segment_page():
            print("❌ Failed to load segment page")
            return False
        
        print("✅ Segment page loaded")
        
        # Take screenshot
        print("\n5. Taking screenshot...")
        automation.take_screenshot("test_segment_page.png")
        print("✅ Screenshot saved: test_segment_page.png")
        
        # Check if checkboxes exist
        print("\n6. Checking for segment checkboxes...")
        try:
            nse_eq = automation.driver.find_element("id", "NSE_EQ")
            bse_eq = automation.driver.find_element("id", "BSE_EQ")
            nse_fo = automation.driver.find_element("id", "NSE_FO")
            bse_fo = automation.driver.find_element("id", "BSE_FO")
            
            print("✅ Found all segment checkboxes:")
            print(f"   - NSE_EQ: {'Checked' if nse_eq.is_selected() else 'Unchecked'}")
            print(f"   - BSE_EQ: {'Checked' if bse_eq.is_selected() else 'Unchecked'}")
            print(f"   - NSE_FO: {'Checked' if nse_fo.is_selected() else 'Unchecked'}")
            print(f"   - BSE_FO: {'Checked' if bse_fo.is_selected() else 'Unchecked'}")
        except Exception as e:
            print(f"❌ Could not find checkboxes: {e}")
            return False
        
        print("\n" + "=" * 60)
        print("TEST 1: PASSED ✅")
        print("=" * 60)
        
        input("\nPress Enter to close browser...")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return False
    finally:
        automation.close()

def test_segment_toggle_dry_run():
    """Test 2: Dry run of segment toggle (no actual changes)"""
    print("\n" + "=" * 60)
    print("TEST 2: Segment Toggle Dry Run")
    print("=" * 60)
    print("\n⚠️  This test will NOT make actual changes")
    print("It will just verify the toggle mechanism works\n")
    
    automation = ZerodhaSegmentAutomation(headless=False)
    
    try:
        # Login and setup
        session = automation.login_to_zerodha()
        if not session:
            print("❌ Login failed")
            return False
        
        automation.setup_driver()
        automation.driver.get("https://console.zerodha.com")
        
        for cookie in session.cookies:
            cookie_dict = {
                'name': cookie.name,
                'value': cookie.value,
                'domain': cookie.domain,
                'path': cookie.path,
            }
            try:
                automation.driver.add_cookie(cookie_dict)
            except:
                pass
        
        if not automation.navigate_to_segment_page():
            print("❌ Failed to load segment page")
            return False
        
        # Test finding and checking state of NSE F&O
        print("\n1. Testing NSE F&O segment detection...")
        
        try:
            checkbox = automation.driver.find_element("id", "NSE_FO")
            label = automation.driver.find_element("css selector", "label[for='NSE_FO']")
            
            current_state = checkbox.is_selected()
            
            print(f"✅ Found NSE F&O checkbox")
            print(f"   Current state: {'Active' if current_state else 'Inactive'}")
            print(f"   Checkbox element: {checkbox}")
            print(f"   Label element: {label}")
            
        except Exception as e:
            print(f"❌ Could not find NSE F&O elements: {e}")
            return False
        
        print("\n2. Testing Continue button detection...")
        
        try:
            continue_btn = automation.driver.find_element("xpath", "//button[contains(text(), 'Continue')]")
            print(f"✅ Found Continue button")
            print(f"   Button text: {continue_btn.text}")
            print(f"   Button enabled: {continue_btn.is_enabled()}")
        except Exception as e:
            print(f"❌ Could not find Continue button: {e}")
            return False
        
        print("\n" + "=" * 60)
        print("TEST 2: PASSED ✅")
        print("=" * 60)
        print("\nAll elements found successfully!")
        print("The automation should work correctly.")
        
        input("\nPress Enter to close browser...")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return False
    finally:
        automation.close()

def main():
    """Run tests"""
    print("\n" + "=" * 60)
    print("SEGMENT AUTOMATION TEST SUITE")
    print("=" * 60)
    print("\nThis will test the segment automation without making changes")
    print("Browser will be visible so you can see what's happening")
    print("\n⚠️  Make sure:")
    print("  - .env file has correct credentials")
    print("  - TOTP key is synced")
    print("  - Chrome/Chromium is installed")
    print("\n" + "=" * 60)
    
    choice = input("\nSelect test:\n1. Login and Page Load\n2. Segment Toggle Dry Run\n3. Both\n\nChoice (1/2/3): ").strip()
    
    if choice == '1':
        test_login_and_page_load()
    elif choice == '2':
        test_segment_toggle_dry_run()
    elif choice == '3':
        if test_login_and_page_load():
            print("\n\nMoving to Test 2...\n")
            test_segment_toggle_dry_run()
    else:
        print("Invalid choice")

if __name__ == "__main__":
    main()
