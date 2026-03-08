import logging
import pandas as pd
import datetime
from connect import get_kite_session
from strategy import strategy_engine
import config

# Free data sources for historical data
try:
    from nsepy import get_history as nsepy_get_history
    NSEPY_AVAILABLE = True
except ImportError:
    NSEPY_AVAILABLE = False

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

if not NSEPY_AVAILABLE and not YFINANCE_AVAILABLE:
    logger = logging.getLogger(__name__)
    logger.warning("No free data source available. Install: pip install yfinance")

logger = logging.getLogger(__name__)

class Scanner:
    def __init__(self):
        self.kite = get_kite_session()
        self.watchlist = config.WATCHLIST
        
    def fetch_ohlc_yfinance(self, symbol, period='5minute'):
        """
        Fetches OHLC data using yfinance (Yahoo Finance) - FREE and reliable.
        Symbol format: "NIFTY 50" or "NIFTY BANK"
        """
        try:
            if not YFINANCE_AVAILABLE:
                logger.error("yfinance not installed. Run: pip install yfinance")
                return pd.DataFrame()
            
            # Map Kite symbols to Yahoo Finance tickers
            symbol_map = {
                "NIFTY 50": "^NSEI",      # NIFTY 50 index
                "NIFTY BANK": "^NSEBANK"  # NIFTY BANK index
            }
            
            ticker = symbol_map.get(symbol)
            if not ticker:
                logger.error(f"Unknown symbol: {symbol}")
                return pd.DataFrame()
            
            logger.info(f"Fetching {symbol} data from Yahoo Finance...")
            
            # Get 30 days of data for indicators
            stock = yf.Ticker(ticker)
            df = stock.history(period="1mo", interval="1d")
            
            if df.empty:
                logger.warning(f"No data returned for {symbol}")
                return pd.DataFrame()
            
            # Rename columns to match expected format
            df = df.rename(columns={
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            })
            
            # Reset index to make date a column
            df = df.reset_index()
            df = df.rename(columns={'Date': 'date'})
            
            # Keep only required columns
            df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
            
            logger.info(f"✅ Fetched {len(df)} days of data for {symbol}")
            logger.info(f"   Latest Close: ₹{df.iloc[-1]['close']:.2f}")
            
            return df
            
        except Exception as e:
            logger.error(f"Error in yfinance fetch for {symbol}: {e}")
            return pd.DataFrame()
    
    def fetch_ohlc_nsepy(self, symbol, period='5minute'):
        """
        Fetches OHLC data from NSE using NSEpy (FREE).
        Symbol format: "NIFTY 50" or "NIFTY BANK"
        
        NSEpy provides:
        - Free historical data from NSE website
        - No API key required
        - Daily and intraday data
        """
        try:
            if not NSEPY_AVAILABLE:
                logger.error("NSEpy not installed. Run: pip install nsepy")
                return pd.DataFrame()
            
            # Map Kite symbols to NSEpy index names
            symbol_map = {
                "NIFTY 50": "NIFTY",
                "NIFTY BANK": "NIFTY BANK"
            }
            
            nse_symbol = symbol_map.get(symbol, symbol.replace(" 50", "").replace(" ", ""))
            
            # Get historical data
            to_date = datetime.datetime.now()
            from_date = to_date - datetime.timedelta(days=30)  # Get 30 days for indicators
            
            logger.info(f"Fetching {nse_symbol} data from NSE...")
            
            try:
                # For indices, use index=True
                df = nsepy_get_history(
                    symbol=nse_symbol,
                    start=from_date,
                    end=to_date,
                    index=True
                )
                
                if df is None or df.empty:
                    logger.warning(f"No data returned for {nse_symbol} (market might be closed)")
                    return pd.DataFrame()
                
                # Rename columns to match expected format
                df = df.rename(columns={
                    'Open': 'open',
                    'High': 'high',
                    'Low': 'low',
                    'Close': 'close',
                    'Volume': 'volume'
                })
                
                # Reset index to make date a column
                df = df.reset_index()
                df = df.rename(columns={'Date': 'date'})
                
                logger.info(f"✅ Fetched {len(df)} days of data for {nse_symbol}")
                logger.info(f"   Latest Close: ₹{df.iloc[-1]['close']:.2f}")
                
                return df
                
            except Exception as fetch_error:
                logger.error(f"Error fetching data for {nse_symbol}: {fetch_error}")
                return pd.DataFrame()
            
        except Exception as e:
            logger.error(f"Error in NSEpy fetch for {symbol}: {e}")
            return pd.DataFrame()
    
    def fetch_ohlc(self, symbol, period='5minute'):
        """
        Fetches OHLC data using free data sources.
        Priority: yfinance (most reliable) > NSEpy > Kite API
        """
        # Try yfinance first (most reliable, free)
        if YFINANCE_AVAILABLE:
            df = self.fetch_ohlc_yfinance(symbol, period)
            if not df.empty:
                return df
        
        # Try NSEpy second (free but sometimes has SSL issues)
        if NSEPY_AVAILABLE:
            df = self.fetch_ohlc_nsepy(symbol, period)
            if not df.empty:
                return df
        
        # Fallback to Kite API (requires subscription)
        logger.warning(f"Free data sources failed for {symbol}, trying Kite API...")
        return self.fetch_ohlc_kite(symbol, period)
    
    def fetch_ohlc_kite(self, symbol, period='5minute'):
        """
        Fetches OHLC data from Kite API (requires historical data subscription).
        This is kept as fallback option.
        """
        try:
            instruments = self.kite.instruments("NSE")
            inst_df = pd.DataFrame(instruments)
            
            token_row = inst_df[inst_df['tradingsymbol'] == symbol]
            
            if token_row.empty:
                logger.error(f"Symbol {symbol} not found in NSE instruments")
                return pd.DataFrame()
            
            token = token_row.iloc[0]['instrument_token']
            
            to_date = datetime.datetime.now()
            from_date = to_date - datetime.timedelta(days=5)
            
            try:
                records = self.kite.historical_data(token, from_date, to_date, interval=period)
                df = pd.DataFrame(records)
                return df
            except Exception as api_error:
                if "Insufficient permission" in str(api_error):
                    logger.warning(f"Historical data API not subscribed for {symbol}.")
                else:
                    logger.error(f"Kite API error for {symbol}: {api_error}")
                return pd.DataFrame()
            
        except Exception as e:
            logger.error(f"Error fetching Kite data for {symbol}: {e}")
            return pd.DataFrame()

    def scan(self):
        signals = []
        logger.info(f"Scanning watchlist: {self.watchlist}")
        
        # Check if any free data source is available
        if not YFINANCE_AVAILABLE and not NSEPY_AVAILABLE:
            logger.error("=" * 60)
            logger.error("NO FREE DATA SOURCE AVAILABLE")
            logger.error("=" * 60)
            logger.error("Install with: pip install yfinance")
            logger.error("Or run: pip install -r requirements.txt")
            logger.error("=" * 60)
            return signals
        
        if YFINANCE_AVAILABLE:
            logger.info("✅ Using Yahoo Finance for FREE historical data")
        elif NSEPY_AVAILABLE:
            logger.info("✅ Using NSEpy for FREE historical data from NSE")
        
        for symbol in self.watchlist:
            logger.info(f"Checking {symbol}...")
            df = self.fetch_ohlc(symbol)
            
            if df.empty:
                logger.warning(f"No data for {symbol}, skipping...")
                continue
                
            signal, msg = strategy_engine.get_signal(df)
            
            if signal:
                logger.info(f"🔥 Signal Found on {symbol}: {msg}")
                signal['symbol'] = symbol
                signals.append(signal)
            else:
                logger.debug(f"No signal on {symbol}: {msg}")
                
        return signals

# Global instance
market_scanner = Scanner()
