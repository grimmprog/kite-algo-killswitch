"""
Enhanced Scanner - Scans for both Bullish (CE) and Bearish (PE) setups
Finds ATM and ITM option strikes for SENSEX and NIFTY 50
"""
import logging
import pandas as pd
import datetime
from connect import get_kite_session
import config

# Free data sources
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

logger = logging.getLogger(__name__)

class EnhancedScanner:
    def __init__(self):
        self.kite = get_kite_session()
        # Updated watchlist with SENSEX
        self.watchlist = [
            {"name": "NIFTY 50", "ticker": "^NSEI", "exchange": "NSE", "strike_step": 50},
            {"name": "SENSEX", "ticker": "^BSESN", "exchange": "BSE", "strike_step": 100},
            {"name": "NIFTY BANK", "ticker": "^NSEBANK", "exchange": "NSE", "strike_step": 100}
        ]
        
    def fetch_index_data(self, ticker, name):
        """Fetch index data from Yahoo Finance"""
        try:
            if not YFINANCE_AVAILABLE:
                logger.error("yfinance not installed")
                return pd.DataFrame()
            
            logger.info(f"Fetching {name} data...")
            stock = yf.Ticker(ticker)
            df = stock.history(period="1mo", interval="1d")
            
            if df.empty:
                return pd.DataFrame()
            
            # Rename columns
            df = df.rename(columns={
                'Open': 'open', 'High': 'high', 'Low': 'low',
                'Close': 'close', 'Volume': 'volume'
            })
            df = df.reset_index()
            df = df.rename(columns={'Date': 'date'})
            df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
            
            logger.info(f"✅ {name}: ₹{df.iloc[-1]['close']:.2f}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching {name}: {e}")
            return pd.DataFrame()
    
    def calculate_indicators(self, df):
        """Calculate technical indicators"""
        if len(df) < 20:
            return df
        
        # VWAP
        df['vwap'] = (df['close'] * df['volume']).cumsum() / df['volume'].cumsum()
        
        # EMA 20
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        
        # MACD
        ema_12 = df['close'].ewm(span=12, adjust=False).mean()
        ema_26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema_12 - ema_26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # Volume MA
        df['vol_ma'] = df['volume'].rolling(window=10).mean()
        
        # Candle metrics
        df['body_size'] = abs(df['close'] - df['open'])
        df['color'] = df.apply(lambda x: 'GREEN' if x['close'] > x['open'] else 'RED', axis=1)
        
        return df
    
    def check_bullish_trend(self, df):
        """Check for bullish trend (for CE/Call options)"""
        if len(df) < 5:
            return False, "Insufficient data"
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Bullish conditions
        checks = {
            'price_above_vwap': last['close'] > last['vwap'],
            'ema_up': last['ema_20'] > prev['ema_20'],
            'macd_positive': last['macd'] > 0,
            'price_above_ema': last['close'] > last['ema_20']
        }
        
        passed = sum(checks.values())
        
        if passed >= 3:  # At least 3 out of 4 conditions
            return True, f"Bullish Trend ({passed}/4 checks)"
        
        return False, f"Not bullish ({passed}/4 checks)"
    
    def check_bearish_trend(self, df):
        """Check for bearish trend (for PE/Put options)"""
        if len(df) < 5:
            return False, "Insufficient data"
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Bearish conditions
        checks = {
            'price_below_vwap': last['close'] < last['vwap'],
            'ema_down': last['ema_20'] < prev['ema_20'],
            'macd_negative': last['macd'] < 0,
            'price_below_ema': last['close'] < last['ema_20']
        }
        
        passed = sum(checks.values())
        
        if passed >= 3:  # At least 3 out of 4 conditions
            return True, f"Bearish Trend ({passed}/4 checks)"
        
        return False, f"Not bearish ({passed}/4 checks)"
    
    def find_option_strikes(self, spot_price, strike_step, option_type):
        """
        Find ATM and ITM strikes
        option_type: 'CE' for calls, 'PE' for puts
        """
        # Round to nearest strike
        atm_strike = round(spot_price / strike_step) * strike_step
        
        if option_type == 'CE':
            # For calls: ITM is below spot, ATM is at spot
            itm_strike = atm_strike - strike_step
            strikes = {
                'ATM': atm_strike,
                'ITM': itm_strike
            }
        else:  # PE
            # For puts: ITM is above spot, ATM is at spot
            itm_strike = atm_strike + strike_step
            strikes = {
                'ATM': atm_strike,
                'ITM': itm_strike
            }
        
        return strikes
    
    def calculate_confidence(self, df, trend_type):
        """Calculate confidence score"""
        score = 50
        last = df.iloc[-1]
        
        # Volume strength
        recent_vol_max = df['volume'].iloc[-10:].max()
        avg_vol = df['vol_ma'].iloc[-1]
        if recent_vol_max > (2 * avg_vol):
            score += 10
        
        # Proximity to EMA
        dist = abs(last['close'] - last['ema_20']) / last['close']
        if dist < 0.001:
            score += 15
        elif dist < 0.002:
            score += 10
        
        # Time early (9:30-10:30)
        now = datetime.datetime.now().time()
        if datetime.time(9, 30) <= now <= datetime.time(10, 30):
            score += 10
        
        # Trend strength
        if trend_type == 'bullish':
            if last['close'] > last['vwap'] and last['macd'] > 0:
                score += 10
        else:  # bearish
            if last['close'] < last['vwap'] and last['macd'] < 0:
                score += 10
        
        return min(100, score)
    
    def scan(self):
        """Scan for both bullish and bearish setups"""
        signals = []
        
        logger.info("=" * 60)
        logger.info("ENHANCED SCANNER - Scanning for CE and PE setups")
        logger.info("=" * 60)
        
        if not YFINANCE_AVAILABLE:
            logger.error("yfinance not installed. Run: pip install yfinance")
            return signals
        
        # Check market time
        now = datetime.datetime.now().time()
        if not (config.START_TIME <= now <= config.END_TIME):
            logger.info(f"Outside trading hours ({now.strftime('%H:%M')})")
            logger.info(f"Trading window: {config.START_TIME} - {config.END_TIME}")
            return signals
        
        for index in self.watchlist:
            name = index['name']
            ticker = index['ticker']
            exchange = index['exchange']
            strike_step = index['strike_step']
            
            logger.info(f"\n{'='*60}")
            logger.info(f"Analyzing: {name} ({exchange})")
            logger.info(f"{'='*60}")
            
            # Fetch data
            df = self.fetch_index_data(ticker, name)
            if df.empty:
                continue
            
            # Calculate indicators
            df = self.calculate_indicators(df)
            if len(df) < 20:
                logger.warning(f"Insufficient data for {name}")
                continue
            
            last = df.iloc[-1]
            spot_price = last['close']
            
            logger.info(f"Spot Price: ₹{spot_price:.2f}")
            logger.info(f"VWAP: ₹{last['vwap']:.2f}")
            logger.info(f"EMA 20: ₹{last['ema_20']:.2f}")
            logger.info(f"MACD: {last['macd']:.4f}")
            
            # Check BULLISH trend (for CE/Call options)
            bullish_ok, bullish_msg = self.check_bullish_trend(df)
            if bullish_ok:
                confidence = self.calculate_confidence(df, 'bullish')
                if confidence >= config.CONFIDENCE_THRESHOLD:
                    strikes = self.find_option_strikes(spot_price, strike_step, 'CE')
                    
                    signal = {
                        'index': name,
                        'exchange': exchange,
                        'spot_price': spot_price,
                        'direction': 'BULLISH',
                        'option_type': 'CE',
                        'strikes': strikes,
                        'confidence': confidence,
                        'reason': bullish_msg,
                        'stop_loss': last['low'],
                        'target': spot_price + (spot_price - last['low']) * 2
                    }
                    signals.append(signal)
                    logger.info(f"🔥 BULLISH Signal: {name} CE")
                    logger.info(f"   ATM Strike: {strikes['ATM']}")
                    logger.info(f"   ITM Strike: {strikes['ITM']}")
                    logger.info(f"   Confidence: {confidence}%")
            
            # Check BEARISH trend (for PE/Put options)
            bearish_ok, bearish_msg = self.check_bearish_trend(df)
            if bearish_ok:
                confidence = self.calculate_confidence(df, 'bearish')
                if confidence >= config.CONFIDENCE_THRESHOLD:
                    strikes = self.find_option_strikes(spot_price, strike_step, 'PE')
                    
                    signal = {
                        'index': name,
                        'exchange': exchange,
                        'spot_price': spot_price,
                        'direction': 'BEARISH',
                        'option_type': 'PE',
                        'strikes': strikes,
                        'confidence': confidence,
                        'reason': bearish_msg,
                        'stop_loss': last['high'],
                        'target': spot_price - (last['high'] - spot_price) * 2
                    }
                    signals.append(signal)
                    logger.info(f"🔥 BEARISH Signal: {name} PE")
                    logger.info(f"   ATM Strike: {strikes['ATM']}")
                    logger.info(f"   ITM Strike: {strikes['ITM']}")
                    logger.info(f"   Confidence: {confidence}%")
            
            if not bullish_ok and not bearish_ok:
                logger.info(f"No clear trend for {name}")
                logger.info(f"  Bullish: {bullish_msg}")
                logger.info(f"  Bearish: {bearish_msg}")
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Scan Complete: {len(signals)} signal(s) found")
        logger.info(f"{'='*60}")
        
        return signals

# Global instance
enhanced_scanner = EnhancedScanner()
