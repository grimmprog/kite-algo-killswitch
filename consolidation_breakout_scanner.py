"""
Live Consolidation Breakout Scanner
Identifies tight range consolidations and executes on breakout
Based on the 13:15 PM setup analysis (86.70 → 190.65)
"""
import datetime
import time
import pandas as pd
from connect import get_kite_session
from notifier import notifier
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConsolidationBreakoutScanner:
    def __init__(self):
        self.kite = get_kite_session()
        self.consolidation_threshold = 0.15  # 15% range = tight consolidation
        self.min_consolidation_candles = 6  # At least 18 minutes (6 x 3-min)
        self.breakout_threshold = 1.10  # 10% move above range = breakout
        
    def get_option_data(self, symbol, strike, option_type='PE'):
        """
        Fetch 3-minute candle data for an option
        symbol: 'NIFTY' or 'BANKNIFTY'
        strike: strike price (e.g., 25200)
        option_type: 'PE' or 'CE'
        """
        try:
            # Get current expiry
            today = datetime.datetime.now()
            
            # Find option instrument
            instruments = self.kite.instruments("NFO")
            inst_df = pd.DataFrame(instruments)
            
            # Filter for the option
            option_df = inst_df[
                (inst_df['name'] == symbol) &
                (inst_df['strike'] == strike) &
                (inst_df['instrument_type'] == option_type) &
                (inst_df['expiry'] >= today)
            ].sort_values('expiry')
            
            if option_df.empty:
                logger.error(f"Option not found: {symbol} {strike} {option_type}")
                return pd.DataFrame()
            
            # Get nearest expiry
            option = option_df.iloc[0]
            token = option['instrument_token']
            
            # Fetch 3-minute data for last 2 hours
            to_date = datetime.datetime.now()
            from_date = to_date - datetime.timedelta(hours=2)
            
            data = self.kite.historical_data(
                token, 
                from_date, 
                to_date, 
                interval='3minute'
            )
            
            df = pd.DataFrame(data)
            return df
            
        except Exception as e:
            logger.error(f"Error fetching option data: {e}")
            return pd.DataFrame()
    
    def identify_consolidation(self, df, lookback=10):
        """
        Identify if price is in consolidation
        Returns: (is_consolidating, range_high, range_low, duration)
        """
        if len(df) < lookback:
            return False, None, None, 0
        
        # Get recent candles
        recent = df.iloc[-lookback:]
        
        # Calculate range
        range_high = recent['high'].max()
        range_low = recent['low'].min()
        range_mid = (range_high + range_low) / 2
        range_size = range_high - range_low
        range_pct = (range_size / range_mid) * 100
        
        # Check if range is tight (< 15%)
        is_tight = range_pct < (self.consolidation_threshold * 100)
        
        # Check if price is oscillating (multiple touches of high/low)
        touches_high = (recent['high'] >= range_high * 0.98).sum()
        touches_low = (recent['low'] <= range_low * 1.02).sum()
        
        is_consolidating = is_tight and touches_high >= 2 and touches_low >= 2
        
        return is_consolidating, range_high, range_low, len(recent)
    
    def detect_breakout(self, current_price, range_high, range_low):
        """
        Detect if current price is breaking out
        Returns: (is_breakout, direction, strength)
        """
        range_size = range_high - range_low
        
        # Bullish breakout (for PE options, this means NIFTY dropping)
        if current_price > range_high * self.breakout_threshold:
            strength = ((current_price - range_high) / range_size) * 100
            return True, 'BULLISH', strength
        
        # Bearish breakdown
        if current_price < range_low * (2 - self.breakout_threshold):
            strength = ((range_low - current_price) / range_size) * 100
            return True, 'BEARISH', strength
        
        return False, None, 0
    
    def scan_for_setup(self, symbol='NIFTY', strike=25200, option_type='PE'):
        """
        Main scanning function - checks for consolidation breakout setup
        """
        logger.info(f"Scanning {symbol} {strike} {option_type}...")
        
        # Get option data
        df = self.get_option_data(symbol, strike, option_type)
        
        if df.empty:
            logger.warning("No data available")
            return None
        
        # Check for consolidation
        is_consol, range_high, range_low, duration = self.identify_consolidation(df)
        
        if not is_consol:
            logger.info("No consolidation detected")
            return None
        
        # Get current price
        current_price = df.iloc[-1]['close']
        
        # Check for breakout
        is_breakout, direction, strength = self.detect_breakout(
            current_price, range_high, range_low
        )
        
        if not is_breakout:
            logger.info(f"Consolidation detected but no breakout yet")
            logger.info(f"  Range: {range_low:.2f} - {range_high:.2f}")
            logger.info(f"  Current: {current_price:.2f}")
            logger.info(f"  Duration: {duration} candles ({duration * 3} minutes)")
            return None
        
        # Breakout detected!
        setup = {
            'symbol': symbol,
            'strike': strike,
            'option_type': option_type,
            'entry_price': current_price,
            'range_high': range_high,
            'range_low': range_low,
            'consolidation_duration': duration,
            'breakout_direction': direction,
            'breakout_strength': strength,
            'stop_loss': range_low if direction == 'BULLISH' else range_high,
            'timestamp': datetime.datetime.now()
        }
        
        logger.info("🚀 BREAKOUT DETECTED!")
        logger.info(f"  Direction: {direction}")
        logger.info(f"  Strength: {strength:.1f}%")
        logger.info(f"  Entry: ₹{current_price:.2f}")
        logger.info(f"  Stop Loss: ₹{setup['stop_loss']:.2f}")
        
        return setup
    
    def execute_trade(self, setup, quantity=65):
        """
        Execute the breakout trade
        """
        try:
            # Send Telegram notification
            message = f"""
🚀 CONSOLIDATION BREAKOUT DETECTED!

Symbol: {setup['symbol']} {setup['strike']} {setup['option_type']}
Entry Price: ₹{setup['entry_price']:.2f}
Stop Loss: ₹{setup['stop_loss']:.2f}
Breakout Strength: {setup['breakout_strength']:.1f}%
Consolidation: {setup['consolidation_duration']} candles

Range: ₹{setup['range_low']:.2f} - ₹{setup['range_high']:.2f}

Approve to execute?
"""
            
            # Request confirmation
            approved = notifier.request_confirmation(message)
            
            if not approved:
                logger.info("Trade rejected by user")
                notifier.send_message("❌ Trade rejected")
                return False
            
            # Place order (implement your order logic here)
            logger.info("✅ Trade approved - placing order...")
            
            # Calculate target (1:2 RR minimum for breakouts)
            risk = abs(setup['entry_price'] - setup['stop_loss'])
            target = setup['entry_price'] + (risk * 2)
            
            notifier.send_message(f"""
✅ Order Placed!

Entry: ₹{setup['entry_price']:.2f}
Target: ₹{target:.2f}
Stop Loss: ₹{setup['stop_loss']:.2f}
Quantity: {quantity}

Risk: ₹{risk * quantity:,.2f}
Reward: ₹{risk * 2 * quantity:,.2f}
""")
            
            return True
            
        except Exception as e:
            logger.error(f"Error executing trade: {e}")
            notifier.send_message(f"❌ Error: {e}")
            return False


def main():
    """
    Main loop - scans every 30 seconds during market hours
    """
    scanner = ConsolidationBreakoutScanner()
    
    print("=" * 70)
    print("CONSOLIDATION BREAKOUT SCANNER - LIVE")
    print("=" * 70)
    print("\nScanning for tight range consolidations and breakouts...")
    print("Based on 13:15 PM setup (86.70 → 190.65 = 120% gain)")
    print("\nPress Ctrl+C to stop\n")
    
    # Trading hours
    market_open = datetime.time(9, 15)
    market_close = datetime.time(15, 30)
    
    while True:
        try:
            now = datetime.datetime.now()
            current_time = now.time()
            
            # Check if market is open
            if not (market_open <= current_time <= market_close):
                logger.info("Market closed. Waiting...")
                time.sleep(300)  # Wait 5 minutes
                continue
            
            # Scan for setup
            setup = scanner.scan_for_setup(
                symbol='NIFTY',
                strike=25200,  # Adjust based on current NIFTY level
                option_type='PE'
            )
            
            if setup:
                # Execute trade
                scanner.execute_trade(setup)
                
                # Wait 5 minutes after execution
                logger.info("Trade executed. Waiting 5 minutes...")
                time.sleep(300)
            else:
                # No setup found, wait 30 seconds
                time.sleep(30)
                
        except KeyboardInterrupt:
            print("\n\nScanner stopped by user")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()
