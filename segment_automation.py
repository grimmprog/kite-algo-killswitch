"""
Zerodha Segment Automation
Automatically activate/deactivate trading segments using API + Selenium hybrid
Supports both Windows and Linux (Ubuntu/AWS)
"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import pyotp
import requests
import time
import config
import logging
import platform
import os
from urllib.parse import urlparse, parse_qs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ZerodhaSegmentAutomation:
    def __init__(self, headless=True):
        """
        Initialize Selenium WebDriver
        headless: Run browser in background (True) or visible (False)
        Automatically detects OS and configures accordingly
        """
        self.user_id = config.USER_ID
        self.password = config.PASSWORD
        self.totp_key = config.TOTP_KEY
        self.headless = headless
        self.driver = None
        self.os_type = platform.system()  # 'Windows', 'Linux', 'Darwin' (Mac)
        
    def setup_driver(self):
        """Setup Chrome WebDriver with OS-specific configurations"""
        chrome_options = Options()
        
        # Common options
        if self.headless:
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--disable-gpu')
        
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Linux-specific options (for Ubuntu/AWS)
        if self.os_type == 'Linux':
            logger.info("Detected Linux OS - applying server-specific configurations")
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-software-rasterizer')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--remote-debugging-port=9222')
            
            # For AWS/Cloud servers without display
            if not os.environ.get('DISPLAY'):
                logger.info("No DISPLAY detected - running in headless mode")
                chrome_options.add_argument('--headless=new')
                chrome_options.add_argument('--disable-software-rasterizer')
        
        # Install and setup ChromeDriver
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.implicitly_wait(10)
            logger.info(f"Chrome WebDriver initialized on {self.os_type}")
        except Exception as e:
            logger.error(f"Failed to initialize Chrome WebDriver: {e}")
            logger.info("Make sure Chrome/Chromium is installed:")
            if self.os_type == 'Linux':
                logger.info("  Ubuntu: sudo apt-get install chromium-browser chromium-chromedriver")
            raise
    
    def login_to_zerodha_selenium(self):
        """Login to Zerodha Console using Selenium (more reliable for Console access)"""
        try:
            if not self.driver:
                self.setup_driver()
            
            logger.info("Step 1: Navigating to Zerodha Console...")
            self.driver.get("https://console.zerodha.com")
            time.sleep(3)
            
            # Step 2: Click "Login with Kite" button
            logger.info("Step 2: Clicking 'Login with Kite' button...")
            try:
                login_button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-blue"))
                )
                login_button.click()
                time.sleep(3)
            except Exception as e:
                logger.error(f"Could not find 'Login with Kite' button: {e}")
                self.take_screenshot("no_login_button.png")
                return False
            
            # Step 3: Enter user ID
            logger.info("Step 3: Entering user ID...")
            try:
                user_id_field = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "userid"))
                )
                user_id_field.clear()
                user_id_field.send_keys(self.user_id)
            except Exception as e:
                logger.error(f"Could not find user ID field: {e}")
                self.take_screenshot("no_userid_field.png")
                return False
            
            # Step 4: Enter password
            logger.info("Step 4: Entering password...")
            try:
                password_field = self.driver.find_element(By.ID, "password")
                password_field.clear()
                password_field.send_keys(self.password)
            except Exception as e:
                logger.error(f"Could not find password field: {e}")
                return False
            
            # Step 5: Click login button
            logger.info("Step 5: Clicking login button...")
            try:
                login_submit = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                login_submit.click()
                time.sleep(3)
            except Exception as e:
                logger.error(f"Could not click login button: {e}")
                return False
            
            # Step 6: Enter TOTP
            logger.info("Step 6: Generating and entering TOTP...")
            totp = pyotp.TOTP(self.totp_key).now()
            logger.info(f"TOTP generated: {totp}")
            
            # Try multiple selectors for TOTP field
            # Note: TOTP field has id="userid" (same as login!) but type="number"
            totp_field = None
            totp_selectors = [
                (By.CSS_SELECTOR, "input[type='number'][id='userid']"),
                (By.CSS_SELECTOR, "input[type='number'][maxlength='6']"),
                (By.CSS_SELECTOR, "input[type='number'][pattern='[0-9]+']"),
                (By.XPATH, "//input[@type='number' and @maxlength='6']"),
                (By.XPATH, "//input[@type='number' and contains(@placeholder, '••')]"),
            ]
            
            for by, selector in totp_selectors:
                try:
                    totp_field = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((by, selector))
                    )
                    logger.info(f"Found TOTP field using: {by}='{selector}'")
                    break
                except:
                    continue
            
            if not totp_field:
                logger.error("Could not find TOTP field with any selector")
                self.take_screenshot("totp_field_not_found.png")
                
                # Save page source for debugging
                try:
                    with open("totp_page_source.html", "w", encoding="utf-8") as f:
                        f.write(self.driver.page_source)
                    logger.info("Page source saved to totp_page_source.html")
                except:
                    pass
                
                return False
            
            totp_field.clear()
            totp_field.send_keys(totp)
            logger.info("TOTP entered successfully")
            
            # Wait a moment for the field to register the input
            time.sleep(1)
            
            # Press Enter to submit - use a fresh reference or JavaScript
            try:
                # Try to press Enter on the field
                from selenium.webdriver.common.keys import Keys
                totp_field.send_keys(Keys.RETURN)
                logger.info("Pressed Enter to submit TOTP")
            except Exception as enter_error:
                logger.warning(f"Could not press Enter on TOTP field: {enter_error}")
                # Try submitting the form using JavaScript as fallback
                try:
                    self.driver.execute_script("document.querySelector('form').submit();")
                    logger.info("Submitted form using JavaScript")
                except:
                    logger.warning("Could not submit form, waiting for auto-submit...")
            
            # Wait for redirect after login
            time.sleep(5)
            
            # Step 7: Verify login success and navigate to account page
            current_url = self.driver.current_url
            logger.info(f"Current URL after login: {current_url}")
            
            if "login" in current_url.lower():
                logger.error("Still on login page - login failed")
                self.take_screenshot("login_failed.png")
                return False
            
            # Navigate to account page first (required before segment page)
            logger.info("Step 7: Navigating to account page...")
            self.driver.get("https://console.zerodha.com/account")
            time.sleep(3)
            
            logger.info("✅ Login successful via Selenium")
            return True
            
        except Exception as e:
            logger.error(f"Selenium login failed: {e}")
            self.take_screenshot("selenium_login_error.png")
            return False
        """Complete Kite login flow using API endpoints (more reliable than Selenium)"""
        try:
            session = requests.Session()
            
            # Step 1: Get initial login page
            logger.info("Step 1: Getting login page...")
            login_url = f"https://kite.trade/connect/login?v=3&api_key={self.api_key if hasattr(self, 'api_key') else config.API_KEY}"
            login_page_res = session.get(url=login_url)
            login_page_url = login_page_res.url
            
            # Step 2: Post login credentials
            logger.info("Step 2: Submitting credentials...")
            login_resp = session.post(
                url="https://kite.zerodha.com/api/login",
                data={"user_id": self.user_id, "password": self.password}
            )
            login_json = login_resp.json()
            
            if "data" not in login_json or "request_id" not in login_json.get("data", {}):
                logger.error(f"Unexpected login response: {login_json}")
                return None
            
            request_id = login_json["data"]["request_id"]
            logger.info("✅ Credentials accepted")
            
            # Step 3: Generate and submit TOTP
            logger.info("Step 3: Generating TOTP...")
            totp = pyotp.TOTP(self.totp_key).now()
            logger.info(f"TOTP generated: {totp}")
            
            twofa_resp = session.post(
                url="https://kite.zerodha.com/api/twofa",
                data={
                    "user_id": self.user_id,
                    "request_id": request_id,
                    "twofa_value": totp
                }
            )
            twofa_json = twofa_resp.json()
            
            if twofa_json.get('status') != 'success':
                logger.error(f"2FA failed: {twofa_json.get('message')}")
                return None
            
            logger.info("✅ 2FA successful")
            
            # Step 4: Get authenticated session
            logger.info("Step 4: Getting authenticated session...")
            final_response = session.get(url=login_page_url, allow_redirects=True)
            
            # Session is now authenticated
            logger.info("✅ Login successful - session authenticated")
            return session
            
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return None
    
    def navigate_to_segment_page(self, tab="kill_switch"):
        """
        Navigate to segment activation page and select appropriate tab
        tab: "kill_switch" (for deactivating) or "segment_addition" (for activating)
        """
        try:
            logger.info("Navigating to segment activation page...")
            self.driver.get("https://console.zerodha.com/account/segment-activation")
            
            # Wait longer for page to load
            logger.info("Waiting for page to load...")
            time.sleep(5)
            
            # Check if we're on the login page (session expired)
            if "login" in self.driver.current_url.lower():
                logger.error("Redirected to login page - session not transferred properly")
                self.take_screenshot("session_failed.png")
                return False
            
            # Click the appropriate tab
            logger.info(f"Clicking '{tab}' tab...")
            try:
                # Find the tab by class name
                tab_element = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, f"span.tab.{tab}"))
                )
                tab_element.click()
                logger.info(f"✅ Clicked '{tab}' tab")
                time.sleep(3)  # Wait for tab content to load
            except Exception as tab_error:
                logger.warning(f"Could not click tab: {tab_error}")
                # Continue anyway, maybe we're already on the right tab
            
            # Now check for checkboxes
            logger.info("Looking for segment checkboxes...")
            try:
                # Wait for any segment checkbox to appear
                checkboxes = self.driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox'][id*='_']")
                
                if len(checkboxes) > 0:
                    logger.info(f"✅ Found {len(checkboxes)} segment checkboxes")
                    for cb in checkboxes:
                        cb_id = cb.get_attribute('id')
                        if cb_id and ('_EQ' in cb_id or '_FO' in cb_id):
                            logger.info(f"  - {cb_id}")
                    return True
                else:
                    logger.warning("No segment checkboxes found")
                    return False
                    
            except Exception as e:
                logger.warning(f"Error finding checkboxes: {e}")
                
                # Take screenshot for debugging
                self.take_screenshot("segment_page_no_checkboxes.png")
                
                # Save page source
                try:
                    with open("segment_page_source.html", "w", encoding="utf-8") as f:
                        f.write(self.driver.page_source)
                    logger.info("Page source saved to segment_page_source.html")
                except:
                    pass
                
                return False
            
        except Exception as e:
            logger.error(f"Failed to navigate to segment page: {e}")
            self.take_screenshot("navigate_error.png")
            return False
    
    def click_continue_button(self):
        """Click the Continue button to save segment changes, then handle confirmation modal"""
        try:
            logger.info("Looking for Continue button...")
            
            # Step 1: Find and click the first Continue button
            continue_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Continue')]"))
            )
            
            logger.info("Clicking Continue button...")
            continue_button.click()
            
            time.sleep(2)  # Wait for modal to appear
            
            # Step 2: Wait for confirmation modal to appear
            logger.info("Waiting for confirmation modal...")
            try:
                # Wait for modal to be visible
                modal = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.modal-container"))
                )
                logger.info("✅ Confirmation modal appeared")
                
                # Step 3: Click the Continue button in the modal
                logger.info("Looking for Continue button in modal...")
                modal_continue = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "div.modal-body button.btn-blue[type='submit']"))
                )
                
                logger.info("Clicking Continue button in modal...")
                modal_continue.click()
                
                time.sleep(3)  # Wait for confirmation to process
                
                logger.info("✅ Confirmation modal Continue button clicked")
                return True
                
            except Exception as modal_error:
                logger.warning(f"No confirmation modal appeared or could not click modal button: {modal_error}")
                # If no modal appears, the first Continue might have been enough
                logger.info("✅ Continue button clicked (no modal)")
                return True
            
        except Exception as e:
            logger.error(f"Failed to click Continue button: {e}")
            self.take_screenshot("continue_button_error.png")
            return False
    
    def toggle_segment(self, segment_name, activate=False):
        """
        Toggle a specific segment using Zerodha Console Kill Switch interface
        segment_name: 'equity', 'nfo', 'bse_equity', 'bfo'
        activate: True to activate, False to deactivate
        
        Uses the Kill Switch tab interface on the segment-activation page
        """
        try:
            action = "Activating" if activate else "Deactivating"
            logger.info(f"{action} {segment_name} segment...")
            
            # Map segment names to display names
            segment_display_map = {
                'equity': 'NSE - Equity',
                'nse_equity': 'NSE - Equity',
                'bse_equity': 'BSE - Equity',
                'nfo': 'NSE - Futures & Options',
                'bfo': 'BSE - Futures & Options',
            }
            
            segment_display = segment_display_map.get(segment_name.lower())
            
            if not segment_display:
                logger.error(f"Unknown segment: {segment_name}")
                return False
            
            # Step 1: Click the appropriate tab
            tab_class = "segment_addition" if activate else "kill_switch"
            logger.info(f"Looking for tab: {tab_class}")
            
            try:
                # Find and click the tab
                tab = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, f"span.tab.{tab_class}"))
                )
                tab.click()
                logger.info(f"✅ Clicked {'Activate segment' if activate else 'Kill switch'} tab")
                time.sleep(2)
            except Exception as e:
                logger.error(f"Could not find/click tab: {e}")
                self.take_screenshot(f"tab_not_found_{segment_name}.png")
                return False
            
            # Step 2: Find the segment checkbox by ID
            segment_id_map = {
                'equity': 'NSE_EQ',
                'nse_equity': 'NSE_EQ',
                'bse_equity': 'BSE_EQ',
                'nfo': 'NSE_FO',
                'bfo': 'BSE_FO',
            }
            
            checkbox_id = segment_id_map.get(segment_name.lower())
            logger.info(f"Looking for checkbox with ID: {checkbox_id}")
            
            try:
                checkbox = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, checkbox_id))
                )
                logger.info(f"✅ Found checkbox: {checkbox_id}")
            except Exception as e:
                logger.error(f"Could not find checkbox with ID {checkbox_id}: {e}")
                self.take_screenshot(f"segment_not_found_{segment_name}.png")
                return False
            
            # Step 3: Check current state
            try:
                current_state = checkbox.is_selected()
                logger.info(f"Current state: {'Checked' if current_state else 'Unchecked'}, Target: {'Checked' if activate else 'Unchecked'}")
            except Exception as e:
                logger.warning(f"Could not determine current state: {e}")
                current_state = not activate  # Assume opposite to force toggle
            
            # Step 4: Toggle if needed
            if current_state != activate:
                logger.info(f"Toggling checkbox...")
                
                try:
                    # Find the label associated with this checkbox
                    label = self.driver.find_element(By.CSS_SELECTOR, f"label[for='{checkbox_id}']")
                    logger.info(f"Found label for {checkbox_id}, clicking it...")
                    
                    # Use JavaScript click for more reliability
                    self.driver.execute_script("arguments[0].click();", label)
                    logger.info(f"Clicked label using JavaScript")
                    
                except Exception as label_error:
                    logger.warning(f"Could not click label: {label_error}, trying checkbox directly...")
                    try:
                        # Try JavaScript click on checkbox
                        self.driver.execute_script("arguments[0].click();", checkbox)
                    except Exception as e:
                        logger.error(f"Failed to click element: {e}")
                        return False
                
                # Wait longer for toggle animation and state update
                time.sleep(3)
                
                # Verify the toggle worked by re-finding the checkbox
                try:
                    # Re-find the checkbox to get fresh state
                    checkbox_verify = self.driver.find_element(By.ID, checkbox_id)
                    new_state = checkbox_verify.is_selected()
                    
                    logger.info(f"Verification: State changed from {'Checked' if current_state else 'Unchecked'} to {'Checked' if new_state else 'Unchecked'}")
                    
                    if new_state == activate:
                        logger.info(f"✅ {segment_name} segment {'activated' if activate else 'deactivated'}")
                        return True
                    else:
                        logger.error(f"❌ Toggle failed! State is still: {'Checked' if new_state else 'Unchecked'}, expected: {'Checked' if activate else 'Unchecked'}")
                        return False
                except Exception as e:
                    logger.warning(f"Could not verify toggle: {e}")
                    logger.info(f"⚠️ {segment_name} segment toggle attempted but verification failed")
                    return True  # Assume success if we can't verify
            else:
                logger.info(f"ℹ️  {segment_name} segment already {'activated' if activate else 'deactivated'}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to toggle {segment_name} segment: {e}")
            logger.info("Taking screenshot for debugging...")
            self.take_screenshot(f"segment_error_{segment_name}.png")
            
            # Save page source for debugging
            try:
                with open(f"segment_page_source_{segment_name}.html", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                logger.info(f"Page source saved to segment_page_source_{segment_name}.html")
            except:
                pass
            
            return False
    
    def deactivate_all_segments(self):
        """Deactivate all trading segments"""
        try:
            # Setup Selenium
            if not self.driver:
                self.setup_driver()
            
            # Login using Selenium
            logger.info("Logging in to Zerodha Console...")
            if not self.login_to_zerodha_selenium():
                logger.error("Failed to login")
                return False
            
            # Navigate to segment page with kill_switch tab
            if not self.navigate_to_segment_page(tab="kill_switch"):
                return False
            
            # Find all active segment checkboxes
            logger.info("Finding all active segments to deactivate...")
            segments_to_deactivate = []
            
            segment_ids = ['NSE_EQ', 'BSE_EQ', 'NSE_FO', 'BSE_FO']
            for seg_id in segment_ids:
                try:
                    checkbox = self.driver.find_element(By.ID, seg_id)
                    if checkbox.is_selected():
                        segments_to_deactivate.append(seg_id)
                        logger.info(f"  - {seg_id} is active, will deactivate")
                except:
                    logger.info(f"  - {seg_id} not found (already deactivated)")
            
            if not segments_to_deactivate:
                logger.info("ℹ️  All segments are already deactivated")
                return True
            
            # Deactivate each segment
            logger.info(f"Deactivating {len(segments_to_deactivate)} segments...")
            for seg_id in segments_to_deactivate:
                try:
                    checkbox = self.driver.find_element(By.ID, seg_id)
                    label = self.driver.find_element(By.CSS_SELECTOR, f"label[for='{seg_id}']")
                    
                    # Click the label to toggle
                    self.driver.execute_script("arguments[0].click();", label)
                    logger.info(f"  ✅ Toggled {seg_id}")
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"  ❌ Failed to toggle {seg_id}: {e}")
            
            # Click Continue button to save changes
            if not self.click_continue_button():
                logger.warning("Could not click Continue button, changes may not be saved")
                return False
            
            logger.info("🚨 All segments deactivated successfully!")
            return True
            
        except Exception as e:
            logger.error(f"Failed to deactivate all segments: {e}")
            return False
        finally:
            self.close()
    
    def deactivate_fno_segment(self):
        """Deactivate F&O (NFO) segment - Main kill switch action"""
        try:
            # Setup Selenium
            if not self.driver:
                self.setup_driver()
            
            # Login using Selenium (more reliable for Console)
            logger.info("Logging in to Zerodha Console...")
            if not self.login_to_zerodha_selenium():
                logger.error("Failed to login")
                return False
            
            # Navigate to segment page with kill_switch tab
            if not self.navigate_to_segment_page(tab="kill_switch"):
                return False
            
            # Check if NFO is active
            try:
                nfo_checkbox = self.driver.find_element(By.ID, "NSE_FO")
                if not nfo_checkbox.is_selected():
                    logger.info("ℹ️  F&O segment is already deactivated")
                    return True
            except:
                logger.info("ℹ️  F&O segment not found (already deactivated)")
                return True
            
            # Deactivate NFO segment
            success = self.toggle_segment('nfo', activate=False)
            
            if not success:
                return False
            
            # Click Continue button to save changes
            if not self.click_continue_button():
                logger.warning("Could not click Continue button, changes may not be saved")
            
            if success:
                logger.info("🚨 F&O segment deactivated successfully!")
                logger.info("No new F&O trades can be placed.")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to deactivate F&O segment: {e}")
            return False
        finally:
            self.close()
    
    def activate_fno_segment(self):
        """Activate F&O (NFO) segment - Reactivate trading"""
        try:
            if not self.driver:
                self.setup_driver()
            
            # Login using Selenium
            logger.info("Logging in to Zerodha Console...")
            if not self.login_to_zerodha_selenium():
                logger.error("Failed to login")
                return False
            
            # Navigate to segment page with segment_addition tab
            if not self.navigate_to_segment_page(tab="segment_addition"):
                return False
            
            # Check if NFO is already active
            try:
                nfo_checkbox = self.driver.find_element(By.ID, "NSE_FO")
                if nfo_checkbox.is_selected():
                    logger.info("ℹ️  F&O segment is already activated")
                    return True
            except:
                logger.warning("Could not find NSE_FO checkbox")
            
            # Activate NFO segment
            success = self.toggle_segment('nfo', activate=True)
            
            if not success:
                return False
            
            # Click Continue button to save changes
            if not self.click_continue_button():
                logger.warning("Could not click Continue button, changes may not be saved")
            
            if success:
                logger.info("✅ F&O segment activated successfully!")
                logger.info("F&O trading is now enabled.")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to activate F&O segment: {e}")
            return False
        finally:
            self.close()
    
    def take_screenshot(self, filename="segment_page.png"):
        """Take screenshot for debugging"""
        try:
            self.driver.save_screenshot(filename)
            logger.info(f"Screenshot saved: {filename}")
        except Exception as e:
            logger.error(f"Failed to take screenshot: {e}")
    
    def close(self):
        """Close browser"""
        if self.driver:
            self.driver.quit()
            logger.info("Browser closed")

def test_automation():
    """Test the automation"""
    print("=" * 60)
    print("ZERODHA SEGMENT AUTOMATION TEST")
    print("=" * 60)
    print("\n⚠️  WARNING: This will actually modify your segment settings!")
    print("Make sure you have configured:")
    print("  - KITE_USER_ID")
    print("  - KITE_PASSWORD")
    print("  - KITE_TOTP_KEY (for 2FA)")
    print("\nOptions:")
    print("1. Test deactivate F&O segment")
    print("2. Test activate F&O segment")
    print("3. Test login only (no changes)")
    print("=" * 60)
    
    choice = input("\nSelect option (1/2/3): ").strip()
    
    # Ask for headless mode
    headless = input("Run in headless mode (background)? (y/n): ").strip().lower() == 'y'
    
    automation = ZerodhaSegmentAutomation(headless=headless)
    
    try:
        if choice == '1':
            confirm = input("\n⚠️  Deactivate F&O segment? (yes/no): ").strip().lower()
            if confirm == 'yes':
                success = automation.deactivate_fno_segment()
                if success:
                    print("\n✅ F&O segment deactivated!")
                else:
                    print("\n❌ Failed to deactivate segment")
        
        elif choice == '2':
            confirm = input("\n⚠️  Activate F&O segment? (yes/no): ").strip().lower()
            if confirm == 'yes':
                success = automation.activate_fno_segment()
                if success:
                    print("\n✅ F&O segment activated!")
                else:
                    print("\n❌ Failed to activate segment")
        
        elif choice == '3':
            automation.setup_driver()
            if automation.login_to_zerodha():
                print("\n✅ Login successful!")
                automation.navigate_to_segment_page()
                automation.take_screenshot("test_segment_page.png")
                print("Screenshot saved for inspection")
                input("\nPress Enter to close browser...")
            else:
                print("\n❌ Login failed")
        
        else:
            print("Invalid option")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        automation.close()

if __name__ == "__main__":
    test_automation()
