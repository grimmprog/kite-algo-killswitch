"""
Deactivate All Trading Segments
Forcefully deactivates all segments:
- NSE Equity
- BSE Equity  
- NSE F&O (NFO)
- BSE F&O (BFO)
"""
from segment_automation import ZerodhaSegmentAutomation
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Main function"""
    print()
    print("⚠️  WARNING: This will deactivate ALL trading segments!")
    print()
    print("Segments to be deactivated:")
    print("  1. NSE Equity")
    print("  2. BSE Equity")
    print("  3. NSE F&O (NFO)")
    print("  4. BSE F&O (BFO)")
    print()
    
    confirm = input("Continue? (yes/no): ").strip().lower()
    
    if confirm != 'yes':
        print("Cancelled.")
        return
    
    headless = input("\nRun in headless mode? (y/n): ").strip().lower() == 'y'
    
    print()
    print("=" * 60)
    print("DEACTIVATING ALL TRADING SEGMENTS")
    print("=" * 60)
    print()
    
    try:
        automation = ZerodhaSegmentAutomation(headless=headless)
        success = automation.deactivate_all_segments()
        
        if success:
            print()
            print("=" * 60)
            print("✅ All segments deactivated successfully!")
            print("=" * 60)
        else:
            print()
            print("=" * 60)
            print("❌ Failed to deactivate segments")
            print("Please deactivate manually at:")
            print("https://console.zerodha.com/account/segment-activation")
            print("=" * 60)
    
    except Exception as e:
        logger.error(f"Segment deactivation error: {e}")
        print(f"\n❌ Error: {e}")
        print("Please deactivate manually at:")
        print("https://console.zerodha.com/account/segment-activation")

if __name__ == "__main__":
    main()
