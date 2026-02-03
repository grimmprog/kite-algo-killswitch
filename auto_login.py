"""
Automated Kite Login with TOTP
Generates access token automatically without manual intervention
"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import pyotp
import time
import config
import logging
import os
import platform
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AutoLogin:
    def __init__(self, headless=True):
        self.api_key = config.API_KEY
        self.api_secret = config.API_SECRET
        self.user_id = config.USER_ID
        self.password = config.PASSWORD
        self.totp_key = config.TOTP_KEY
        self.redirect_url = config.REDIRECT_URL
        self.headless = headless
        self.driver = None
        self.os_type = platform.system()
        
    def setup_driver(self):
        """Setup Chrome WebDriver"""
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--disable-gpu')
        
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Linux-specific options
        if self.os_type == 'Linux':
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-software-rasterizer')
            if not os.environ.get('DISPLAY'):
                chrome_options.add_argument('--headless=new')
        
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.implicitly_wait(10)
            logger.info(f"Chrome WebDriver initialized on {self.os_type}")
        except Exception as e:
            logger.error(f"Failed to initialize Chrome: {e}")
            raise
    
    def generate_totp(self):
        """Generate TOTP code"""
        if not self.totp_key or self.totp_key == "your_totp_key_if_automating_login":
            raise ValueError("TOTP key not configured in .env file")
        
        totp = pyotp.TOTP(self.totp_key)
        code = totp.now()
        logger.info(f"Generated TOTP code: {code}")
        return code
    
    def login_to_kite(self):
        """Complete Kite login flow"""
        try:
            # Build login URL
            login_url = f"https://kite.zerodha.com/connect/login?api_key={self.api_key}&v=3"
            logger.info("Navigating to Kite login page...")
            self.driver.get(login_url)
            
            # Wait for page load
            time.sleep(2)
            
            # Enter User ID
            logger.info("Entering user ID...")
            user_id_field = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.ID, "userid"))
            )
            user_id_field.clear()
            user_id_field.send_keys(self.user_id)
            
            # Enter Password
            logger.info("Entering password...")
            password_field = self.driver.find_element(By.ID, "password")
            password_field.clear()
            password_field.send_keys(self.password)
            
            # Click Login
            login_button = self.driver.find_element(By.XPATH, "//button[@type='submit']")
            login_button.click()
            
            # Wait for TOTP page
            logger.info("Waiting for TOTP page...")
            time.sleep(3)
            
            # Generate and enter TOTP
            totp_code = self.generate_totp()
            logger.info("Entering TOTP...")
            
            # Try multiple selectors for TOTP field
            # Note: TOTP field has id="userid" (same as login!) but type="number"
            totp_field = None
            totp_selectors = [
                (By.CSS_SELECTOR, "input[type='number'][id='userid']"),
                (By.CSS_SELECTOR, "input[type='number'][maxlength='6']"),
                (By.CSS_SELECTOR, "input[type='number'][pattern='[0-9]+']"),
                (By.XPATH, "//input[@type='number' and @maxlength='6']"),
                (By.XPATH, "//input[@type='number' and contains(@placeholder, '••')]"),
                (By.ID, "totp"),  # Fallback to old selector
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
                # Take screenshot for debugging
                screenshot_path = f"totp_field_not_found_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                self.driver.save_screenshot(screenshot_path)
                logger.info(f"Screenshot saved: {screenshot_path}")
                return None
            
            totp_field.clear()
            totp_field.send_keys(totp_code)
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
            
            # Wait for redirect
            logger.info("Waiting for redirect...")
            time.sleep(5)
            
            # Get current URL (should contain request_token)
            current_url = self.driver.current_url
            logger.info(f"Redirected to: {current_url}")
            
            # Extract request_token from URL
            if "request_token=" in current_url:
                request_token = current_url.split("request_token=")[1].split("&")[0]
                logger.info(f"✅ Request token obtained: {request_token[:10]}...")
                return request_token
            else:
                logger.error("Request token not found in URL")
                logger.error(f"Current URL: {current_url}")
                return None
                
        except Exception as e:
            logger.error(f"Login failed: {e}")
            # Take screenshot for debugging
            try:
                screenshot_path = f"login_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                self.driver.save_screenshot(screenshot_path)
                logger.info(f"Screenshot saved: {screenshot_path}")
            except:
                pass
            return None
    
    def generate_access_token(self, request_token):
        """Generate access token from request token"""
        try:
            from kiteconnect import KiteConnect
            
            kite = KiteConnect(api_key=self.api_key)
            logger.info("Generating session...")
            
            data = kite.generate_session(request_token, api_secret=self.api_secret)
            access_token = data["access_token"]
            
            logger.info("✅ Access token generated successfully")
            return access_token
            
        except Exception as e:
            logger.error(f"Failed to generate access token: {e}")
            return None
    
    def save_access_token(self, access_token):
        """Save access token to file"""
        try:
            token_path = os.path.join(config.BASE_DIR, "access_token.txt")
            with open(token_path, "w") as f:
                f.write(access_token)
            logger.info(f"✅ Access token saved to: {token_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save access token: {e}")
            return False
    
    def close(self):
        """Close browser"""
        if self.driver:
            self.driver.quit()
            logger.info("Browser closed")
    
    def run(self):
        """Complete auto-login flow"""
        logger.info("=" * 60)
        logger.info("AUTOMATED KITE LOGIN")
        logger.info("=" * 60)
        logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"User: {self.user_id}")
        logger.info("=" * 60)
        
        try:
            # Setup browser
            self.setup_driver()
            
            # Login and get request token
            request_token = self.login_to_kite()
            
            if not request_token:
                logger.error("❌ Failed to obtain request token")
                return False
            
            # Generate access token
            access_token = self.generate_access_token(request_token)
            
            if not access_token:
                logger.error("❌ Failed to generate access token")
                return False
            
            # Save access token
            if not self.save_access_token(access_token):
                logger.error("❌ Failed to save access token")
                return False
            
            logger.info("=" * 60)
            logger.info("✅ AUTO-LOGIN SUCCESSFUL!")
            logger.info("=" * 60)
            
            # Send Telegram notification
            try:
                from notifier import notifier
                notifier.send_message(
                    f"✅ **Auto-Login Successful**\n\n"
                    f"Time: {datetime.now().strftime('%H:%M:%S')}\n"
                    f"User: {self.user_id}\n"
                    f"Access token generated and saved.\n\n"
                    f"Bot is ready to trade!"
                )
            except Exception as e:
                logger.warning(f"Failed to send Telegram notification: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Auto-login failed: {e}")
            
            # Send error notification
            try:
                from notifier import notifier
                notifier.send_message(
                    f"❌ **Auto-Login Failed**\n\n"
                    f"Time: {datetime.now().strftime('%H:%M:%S')}\n"
                    f"Error: {str(e)}\n\n"
                    f"Please login manually:\n"
                    f"`python login.py`"
                )
            except:
                pass
            
            return False
            
        finally:
            self.close()

def main():
    """Main function"""
    # Check if it's a weekday
    today = datetime.now()
    if today.weekday() >= 5:  # Saturday = 5, Sunday = 6
        logger.info("Today is weekend. Skipping auto-login.")
        return
    
    # Run auto-login
    auto_login = AutoLogin(headless=True)
    success = auto_login.run()
    
    if success:
        logger.info("Auto-login completed successfully")
        exit(0)
    else:
        logger.error("Auto-login failed")
        exit(1)

if __name__ == "__main__":
    main()
