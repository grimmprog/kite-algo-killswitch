import pandas as pd
import numpy as np

def calculate_ema(df, period=20, column='close', target_column='ema_20'):
    """Calculates Exponential Moving Average."""
    df[target_column] = df[column].ewm(span=period, adjust=False).mean()
    return df

def calculate_vwap(df):
    """Calculates VWAP (Volume Weighted Average Price) for intraday data.
    Assumes dataframe is for a single day or we reset vwap daily if needed.
    For this bot, we often fetch daily data. If fetching multiple days, 
    group by date is needed.
    """
    # Simple cumulative VWAP calculation
    # Typical Price = (High + Low + Close) / 3
    v = df['volume'].values
    tp = (df['high'] + df['low'] + df['close']) / 3
    tp = tp.values
    df['vwap'] = df.assign(vwap=(tp * v).cumsum() / v.cumsum())['vwap']
    return df

def calculate_macd(df, fast=12, slow=26, signal=9):
    """Calculates MACD and Signal line."""
    exp1 = df['close'].ewm(span=fast, adjust=False).mean()
    exp2 = df['close'].ewm(span=slow, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['macd_signal'] = df['macd'].ewm(span=signal, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    return df

def calculate_volume_ma(df, period=10):
    """Calculates Volume Moving Average."""
    df['vol_ma'] = df['volume'].rolling(window=period).mean()
    return df

def calculate_atr(df, period=14):
    """Calculates Average True Range."""
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['atr'] = true_range.rolling(window=period).mean()
    return df

def add_candle_metrics(df):
    """Adds candle body size, wick information."""
    
    # Body Size (Absolute)
    df['body_size'] = abs(df['close'] - df['open'])
    
    # Range
    df['range'] = df['high'] - df['low']
    
    # Direction
    df['color'] = np.where(df['close'] < df['open'], 'RED', 'GREEN') # Bearish = RED
    
    # Wicks
    # Upper Wick: High - Max(Open, Close)
    df['upper_wick'] = df['high'] - df[['open', 'close']].max(axis=1)
    # Lower Wick: Min(Open, Close) - Low
    df['lower_wick'] = df[['open', 'close']].min(axis=1) - df['low']
    
    return df
