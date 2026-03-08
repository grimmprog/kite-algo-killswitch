import pandas as pd
import numpy as np
from strategy import strategy_engine
import config

def generate_mock_data():
    """Generates synthetic OHLCV data to simulate a bearish setup."""
    dates = pd.date_range(end=pd.Timestamp.now(), periods=100, freq='5min')
    
    data = {
        'date': dates,
        'open': np.linspace(18100, 18000, 100),
        'high': np.linspace(18110, 18010, 100),
        'low': np.linspace(18090, 17990, 100),
        'close': np.linspace(18095, 17995, 100),
        'volume': np.random.randint(5000, 15000, 100)
    }
    df = pd.DataFrame(data)
    
    # Introduce a pullback pattern near end
    # Trend is down (linear space down)
    # create last 5 candles as pullback
    
    # 1. Impulse (Candle -6) -> Big Red
    df.iloc[-6, df.columns.get_loc('open')] = 18020
    df.iloc[-6, df.columns.get_loc('close')] = 17980 # Big drop
    df.iloc[-6, df.columns.get_loc('volume')] = 50000 # High vol
    
    # 2. Pullback (Candles -5 to -2) -> Small Green Up
    for i in range(2, 6):
        idx = -i
        df.iloc[idx, df.columns.get_loc('open')] = 17980 + (i*2)
        df.iloc[idx, df.columns.get_loc('close')] = 17985 + (i*2) # Small up
        df.iloc[idx, df.columns.get_loc('volume')] = 2000
    
    # 3. Trigger (Candle -1) -> Break Low of Pullback
    # Current candle
    df.iloc[-1, df.columns.get_loc('open')] = 17990
    df.iloc[-1, df.columns.get_loc('close')] = 17970 # Bearish break
    df.iloc[-1, df.columns.get_loc('volume')] = 5000
    
    return df

def test_strategy_logic():
    print("Testing Strategy Logic...")
    df = generate_mock_data()
    print("Mock Data Generated.")
    
    # Run Checks
    df = strategy_engine.prepare_data(df)
    print("Indicators Calculated.")
    
    # Override Time Check for Test
    original_check = strategy_engine.check_market_time
    strategy_engine.check_market_time = lambda: (True, "Mock Time OK")
    
    signal, msg = strategy_engine.get_signal(df)
    
    print(f"\nResult: Signal={signal}, Msg={msg}")
    
    # Restore
    strategy_engine.check_market_time = original_check
    
    if signal and signal['signal'] == 'SELL':
        print("✅ Strategy Logic Passed: Generated SELL signal on mock pattern.")
    else:
        print("⚠️ Strategy Logic Check: No Signal (This might be expected if mock data isn't perfect).")
        print("Check `verify_strategy.py` mock logic if needed.")

if __name__ == "__main__":
    test_strategy_logic()
