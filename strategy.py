import pandas as pd
import datetime
import config
from indicators import calculate_ema, calculate_vwap, calculate_macd, calculate_volume_ma, add_candle_metrics
import logging

logger = logging.getLogger(__name__)

class TrendPullbackStrategy:
    def __init__(self):
        self.name = config.STRATEGY_NAME

    def prepare_data(self, df):
        """Calculates all indicators needed for the strategy."""
        # Check if we have enough data
        if len(df) < 20:
            logger.warning(f"Insufficient data for indicators: {len(df)} rows (need 20+)")
            # For live trading with NSEpy quotes, we might only have 1 row
            # In this case, we'll use simplified logic
            if len(df) == 1:
                # Single quote - add basic metrics
                df['vwap'] = df['close']  # Use close as proxy
                df['ema_20'] = df['close']  # Use close as proxy
                df['macd'] = 0
                df['macd_signal'] = 0
                df['macd_hist'] = 0
                df['vol_ma'] = df['volume']
                df = add_candle_metrics(df)
                return df
        
        df = calculate_vwap(df)
        df = calculate_ema(df, period=20, target_column='ema_20')
        df = calculate_macd(df)
        df = calculate_volume_ma(df, period=10)
        df = add_candle_metrics(df)
        return df

    def check_market_time(self):
        """1️⃣ MARKET & TIME CONDITIONS"""
        now = datetime.datetime.now().time()
        
        # trade ONLY 09:25 – 11:15
        if not (config.START_TIME <= now <= config.END_TIME):
            # Optional: 12:30–13:30 (Not implemented as secondary gate for simplicity first, STRICT first)
            return False, "Outside Trading Hours"
            
        # ❌ NO weekly expiry afternoon (Thursday > 12:00) - Assuming Thursday is expiry
        # This requires knowing if today is expiry. Simple check for Thursday afternoon:
        if datetime.datetime.today().weekday() == 3 and now > datetime.time(12, 0):
            return False, "Expiry Afternoon"
            
        return True, "Time OK"

    def check_trend_bearish(self, df):
        """2️⃣ TREND CONDITIONS (Bearish)"""
        if len(df) < 5: return False, "Not enough data"
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Price below VWAP
        if not (last['close'] < last['vwap']):
            return False, "Price above VWAP"
            
        # 20 EMA sloping down (Current < Previous)
        if not (last['ema_20'] < prev['ema_20']):
            return False, "EMA 20 not sloping down"
            
        # MACD Below zero
        if not (last['macd'] < 0):
            return False, "MACD above 0"
            
        # Structure: Lower Lows (Simple check over last few candles)
        # Checking if recent low is lower than previous significant low is hard on just 5 min candles without fractal logic.
        # Simplified: Price < EMA 20 generally ensures structure in strong trend.
        if not (last['close'] < last['ema_20']):
             return False, "Price not below 20 EMA"

        return True, "Bearish Trend Confirmed"

    def check_impulse(self, df):
        """3️⃣ IMPULSE CONDITIONS"""
        # Look back X candles to find a valid impulse
        lookback = 10 
        subset = df.iloc[-lookback:]
        
        # Valid Impulse: Large body (top 30% of day range... simplistic proxy: > 1.5x Avg Body)
        # Volume > last 10-candle avg
        # Breaks VWAP or Support
        
        has_impulse = False
        avg_body = df['body_size'].rolling(20).mean().iloc[-1]
        
        for i in range(len(subset)):
            idx = subset.index[i]
            row = subset.iloc[i]
            
            is_large_body = row['body_size'] > (avg_body * 1.5)
            is_high_volume = row['volume'] > row['vol_ma']
            is_breakout = (row['close'] < row['vwap'] and row['open'] > row['vwap']) # Crossed VWAP down
            
            if is_large_body and is_high_volume and row['color'] == 'RED':
                has_impulse = True
                break # Found at least one recent impulse
        
        if not has_impulse:
            return False, "No valid impulse found"
            
        return True, "Impulse Found"

    def check_pullback(self, df):
        """4️⃣ PULLBACK CONDITIONS"""
        # We assume we are IN a pullback if the current/previous candles are 'weak' and moving up towards EMA
        
        last = df.iloc[-1]
        # prev = df.iloc[-2]
        
        # Pullback location: Below VWAP (Already checked in Trend)
        # Near 20 EMA (e.g. within 0.1% or just close)
        dist_to_ema = abs(last['ema_20'] - last['close'])
        price_threshold = last['close'] * 0.002 # 0.2% tolerance
        
        near_ema = dist_to_ema < price_threshold
        
        # Pullback candles: Small bodies (Green or weak Red)
        avg_body = df['body_size'].rolling(20).mean().iloc[-1]
        is_small_body = last['body_size'] < avg_body
        
        # if not near_ema:
        #    return False, "Not near EMA"
        
        if not is_small_body:
             return False, "Candle body too large for pullback"

        return True, "Valid Pullback State"

    def check_entry_trigger(self, df):
        """5️⃣ ENTRY TRIGGER"""
        # Scenario: We had a pullback candle (previous), and NOW we are breaking its low?
        # Actually proper bot flow: 
        # 1. Identify valid pullback complete (previous candle was the pullback high).
        # 2. CURRENT candle breaks the low of that pullback candle.
        
        curr = df.iloc[-1]
        prev = df.iloc[-2] # Potential Pullback Candle
        
        # Previous candle should be close to EMA (Pullback top)
        # And Current Price < Prev Low
        
        trigger = curr['close'] < prev['low'] 
        
        # Entry Candle must close bearish? 
        # "Enter ONLY when: Pullback candle completes. Next candle breaks pullback low."
        # If we wait for close, we might miss the move.
        # But instructions say "Entry candle: Closes bearish". This implies we trade ON CLOSE.
        
        if curr['color'] != 'RED':
            return False, "Entry candle not bearish"
            
        if not trigger:
             return False, "Did not break previous low"
             
        # Volume >= pullback candle (prev)
        if not (curr['volume'] >= prev['volume']):
            # This is strict. Maybe relax? User said >=
            return False, "Volume low"

        return True, "Entry Triggered"

    def calculate_confidence(self, df):
        """9️⃣ CONFIDENCE FILTER
        Score out of 100.
        Base: 50
        +10 if Impulse Volume > 2x Avg
        +10 if Pullback is perfectly riding EMA (very close)
        +10 if Trend is strong (MACD Hist expanding?)
        +10 if Time is early (09:30-10:30)
        +10 if Distance to VWAP is healthy (room to move)
        """
        score = 50
        last = df.iloc[-1]
        
        # 1. Volume Impulse Strength
        # We need to find the impulse candle again or just check recent max volume
        recent_vol_max = df['volume'].iloc[-10:].max()
        avg_vol = df['vol_ma'].iloc[-1]
        if recent_vol_max > (2 * avg_vol):
            score += 10
            
        # 2. Proximity to EMA (The closer the better entry)
        dist = abs(last['close'] - last['ema_20']) / last['close']
        if dist < 0.001: # extremely close
            score += 15
        elif dist < 0.002:
            score += 10
            
        # 3. Time Early
        now = datetime.datetime.now().time()
        if datetime.time(9, 30) <= now <= datetime.time(10, 30):
            score += 10
            
        # 4. Trend Quality (Price well below VWAP but not extended?)
        # If price is too far from VWAP, mean reversion risk? 
        # Actually user wants "Trend Pullback".
        score += 10 # Base trend points if checks passed
        
        return min(100, score)

    def get_signal(self, df):
        """Integrates all checks to generate signal."""
        df = self.prepare_data(df)
        
        # 1. Time
        ok, msg = self.check_market_time()
        if not ok: return None, msg
        
        # 2. Trend
        ok, msg = self.check_trend_bearish(df)
        if not ok: return None, msg
        
        # 3. Impulse
        ok, msg = self.check_impulse(df)
        if not ok: return None, msg
        
        # 4. Pullback & 5. Trigger
        ok, msg = self.check_entry_trigger(df)
        if not ok: return None, msg
        
        # 6. Confidence
        confidence = self.calculate_confidence(df)
        if confidence < config.CONFIDENCE_THRESHOLD:
            return None, f"Low Confidence: {confidence}"
        
        # If all pass
        signal = {
            "signal": "SELL", # We are buying PUTs, so signal is Bearish on Index
            "symbol": "NIFTY", # Placeholder, handled by scanner
            "type": "PE",
            "stop_loss": df.iloc[-2]['high'], # SL = High of pullback candle
            "confidence": confidence,
            "price": df.iloc[-1]['close'] 
        }
        
        return signal, "GO"
        
strategy_engine = TrendPullbackStrategy()
